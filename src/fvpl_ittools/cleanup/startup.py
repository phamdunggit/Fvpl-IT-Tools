"""Chương trình chạy cùng Windows: liệt kê và bật/tắt kiểu Task Manager (PLAN.md mục 5.4).

Bật/tắt bằng khoá StartupApproved (giống tab Startup của Task Manager), không xoá mục Run hay shortcut nào.
Mỗi lần bật/tắt là một mục registry chạy qua executor nên có nhật ký và hoàn tác được ở trang Nhật ký.

Giá trị StartupApproved là 12 byte: byte đầu chẵn (02, 06) là bật, lẻ (03, 07) là tắt; 8 byte cuối là thời điểm
tắt (FILETIME). Không có giá trị nghĩa là đang bật.

Thêm task trong Task Scheduler chạy lúc đăng nhập / lúc bật máy (phần mềm hay dùng thay cho khoá Run, Task Manager
không hiện). Task thì bật / tắt chính task đó, không có nhật ký registry.
"""

from __future__ import annotations

import json
import os
import struct
import time
import winreg
from dataclasses import dataclass
from pathlib import Path

from ..actions.model import Action, PowerShellStep, RegistryStep, Scope
from ..core import registry, shell
from ..core.executor import Env

_RUN = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
_RUN32 = r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Run"
_APPROVED = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved"


@dataclass(frozen=True)
class StartupEntry:
    name: str             # tên giá trị Run, tên file trong thư mục Startup, hoặc tên task
    command: str          # lệnh chạy hoặc đường dẫn file
    source: str           # nhãn hiện cho IT
    approved_key: str     # khoá StartupApproved tương ứng (HKLM\… hoặc HKCU\…); rỗng với task
    enabled: bool
    task: str = ""        # đường dẫn đầy đủ của task trong Task Scheduler (\Thư mục\Tên)

    @property
    def for_user(self) -> bool:
        return self.approved_key.startswith("HKCU")

    @property
    def key(self) -> str:
        return f"task|{self.task}" if self.task else f"{self.approved_key}|{self.name}"


def _values(root, subkey: str, view: int = 0) -> list[tuple[str, object]]:
    try:
        key = winreg.OpenKey(root, subkey, 0, winreg.KEY_READ | view)
    except OSError:
        return []
    items = []
    with key:
        index = 0
        while True:
            try:
                name, value, _type = winreg.EnumValue(key, index)
            except OSError:
                break
            index += 1
            items.append((name, value))
    return items


def is_enabled(data: object) -> bool:
    if not isinstance(data, (bytes, bytearray)) or not data:
        return True
    return data[0] % 2 == 0


def approval_value(enabled: bool, now: float | None = None) -> bytes:
    if enabled:
        return bytes([2]) + bytes(11)
    filetime = int(((now if now is not None else time.time()) + 11644473600) * 10_000_000)
    return bytes([3, 0, 0, 0]) + struct.pack("<Q", filetime)


def _approved(env: Env, approved_key: str) -> dict[str, object]:
    path = env.resolve(approved_key)
    return {name.lower(): value for name, value in _values(path.root, path.subkey, winreg.KEY_WOW64_64KEY)}


def entries(env: Env) -> list[StartupEntry]:
    found: list[StartupEntry] = []

    def add_run(root, subkey: str, view: int, source: str, approved_key: str) -> None:
        approved = _approved(env, approved_key)
        for name, command in _values(root, subkey, view):
            if not name:
                continue  # giá trị mặc định của khoá Run không phải chương trình khởi động
            found.append(StartupEntry(name, str(command), source, approved_key,
                                      is_enabled(approved.get(name.lower()))))

    user_run = env.resolve(f"HKCU\\{_RUN}")
    add_run(winreg.HKEY_LOCAL_MACHINE, _RUN, winreg.KEY_WOW64_64KEY, "Cả máy (Run)", f"HKLM\\{_APPROVED}\\Run")
    add_run(winreg.HKEY_LOCAL_MACHINE, _RUN, winreg.KEY_WOW64_32KEY, "Cả máy (Run, 32-bit)", f"HKLM\\{_APPROVED}\\Run32")
    add_run(user_run.root, user_run.subkey, 0, "Người dùng (Run)", f"HKCU\\{_APPROVED}\\Run")

    def add_folder(folder: Path | None, source: str, approved_key: str) -> None:
        if folder is None or not folder.is_dir():
            return
        approved = _approved(env, approved_key)
        for item in sorted(folder.iterdir(), key=lambda path: path.name.lower()):
            if item.name.lower() == "desktop.ini" or not item.is_file():
                continue
            found.append(StartupEntry(item.name, str(item), source, approved_key,
                                      is_enabled(approved.get(item.name.lower()))))

    programdata = Path(os.environ.get("ProgramData", r"C:\ProgramData"))
    add_folder(programdata / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "StartUp",
               "Cả máy (thư mục Startup)", f"HKLM\\{_APPROVED}\\StartupFolder")
    profile = env.target_user.profile_path
    user_folder = (Path(profile) / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs"
                   / "Startup") if profile else None
    add_folder(user_folder, "Người dùng (thư mục Startup)", f"HKCU\\{_APPROVED}\\StartupFolder")
    return found


# ---------------------------------------------------------------- task chạy lúc đăng nhập / khởi động máy

# Task Scheduler qua COM (nhanh, không phải nạp module ScheduledTasks). Chỉ lấy task có trigger lúc đăng nhập (9)
# hoặc lúc khởi động máy (8); bỏ thư mục \Microsoft (task của Windows, Office...). Không có quyền đọc thư mục nào
# thì bỏ qua thư mục đó.
TASK_SCRIPT = """\
$service = New-Object -ComObject Schedule.Service
$service.Connect()
$found = New-Object System.Collections.ArrayList
function Read-TaskFolder($Folder) {
    try { $tasks = @($Folder.GetTasks(1)) } catch { $tasks = @() }
    foreach ($task in $tasks) {
        try {
            $definition = $task.Definition
            $kinds = @(foreach ($trigger in @($definition.Triggers)) {
                if ($trigger.Type -eq 9) { 'logon' } elseif ($trigger.Type -eq 8) { 'boot' }
            })
            if (-not $kinds) { continue }
            $commands = @(foreach ($action in @($definition.Actions)) {
                if ($action.Type -eq 0) { ('"{0}" {1}' -f $action.Path, $action.Arguments).Trim() }
            })
            [void]$found.Add([pscustomobject]@{
                path = [string]$task.Path; name = [string]$task.Name; enabled = [bool]$task.Enabled
                trigger = (@($kinds | Select-Object -Unique) -join ','); command = ($commands -join ' ; ')
            })
        }
        catch { }
    }
    try { $folders = @($Folder.GetFolders(0)) } catch { $folders = @() }
    foreach ($sub in $folders) {
        if ($sub.Path -like '\\Microsoft*') { continue }
        Read-TaskFolder $sub
    }
}
Read-TaskFolder ($service.GetFolder('\\'))
ConvertTo-Json -InputObject @($found) -Compress
"""

_TOGGLE_TASK = """\
$service = New-Object -ComObject Schedule.Service
$service.Connect()
$index = $TaskPath.LastIndexOf('\\')
$folderPath = '\\'
if ($index -gt 0) { $folderPath = $TaskPath.Substring(0, $index) }
$task = $service.GetFolder($folderPath).GetTask($TaskPath.Substring($index + 1))
$task.Enabled = ($Enable -eq '1')
if ($Enable -eq '1') { Write-Output ('Đã bật task {0}.' -f $TaskPath) } else { Write-Output ('Đã tắt task {0}.' -f $TaskPath) }
"""

TASK_SOURCES = {"logon": "Task lúc đăng nhập", "boot": "Task lúc bật máy", "logon,boot": "Task lúc bật máy, đăng nhập",
                "boot,logon": "Task lúc bật máy, đăng nhập"}


def parse_tasks(output: str) -> list[StartupEntry]:
    """Dòng JSON của TASK_SCRIPT thành danh sách mục (tách ra để test)."""
    data = json.loads(output) if output.strip() else []
    items = data if isinstance(data, list) else [data]
    entries = []
    for item in items:
        if not isinstance(item, dict) or not item.get("path"):
            continue
        trigger = str(item.get("trigger") or "")
        entries.append(StartupEntry(str(item.get("name") or item["path"]), str(item.get("command") or ""),
                                    TASK_SOURCES.get(trigger, "Task"), "", bool(item.get("enabled")),
                                    task=str(item["path"])))
    return sorted(entries, key=lambda entry: entry.name.lower())


def task_entries(cancel=None) -> list[StartupEntry]:
    """Task chạy lúc đăng nhập / bật máy (không gồm task của Windows). Lỗi thì OSError kèm lời báo."""
    result = shell.run_powershell(TASK_SCRIPT, timeout=60, cancel=cancel)
    lines = [line for line in result.output.splitlines() if line.startswith("[") or line.startswith("{")]
    if not result.ok or not lines:
        raise OSError(f"Không đọc được Task Scheduler: {result.output.strip()[-200:] or result.code}")
    return parse_tasks(lines[-1])


def toggle_action(entry: StartupEntry, enable: bool) -> Action:
    """Bật/tắt một chương trình khởi động, chạy bằng executor.

    Mục Run / thư mục Startup đổi khoá StartupApproved (có nhật ký, hoàn tác được ở trang Nhật ký). Task thì bật /
    tắt chính task đó; muốn quay lại thì bấm Bật / Tắt lần nữa.
    """
    verb = "Bật" if enable else "Tắt"
    if entry.task:
        script = shell.ps_variable_lines({"TaskPath": entry.task, "Enable": "1" if enable else ""}) + _TOGGLE_TASK
        return Action(
            id="startup.task_toggle", name=f"{verb} task khởi động: {entry.name}", category="Khởi động cùng Windows",
            apply=(PowerShellStep(script=script, timeout=60),), page="optimize", scope=Scope.MACHINE, admin=True,
            description=f"{entry.source}: {entry.command}",
        )
    step = RegistryStep(key=entry.approved_key, name=entry.name, type="BINARY", value=approval_value(enable))
    return Action(
        id="startup.toggle",
        name=f"{verb} khởi động cùng Windows: {entry.name}",
        category="Khởi động cùng Windows",
        apply=(step,),
        page="optimize",
        scope=Scope.USER if entry.for_user else Scope.MACHINE,
        admin=not entry.for_user,
        description=f"{entry.source}: {entry.command}",
    )


def describe(entry: StartupEntry) -> str:
    return registry.reg_exe_command(registry.parse_key(entry.approved_key), entry.name, "BINARY",
                                    approval_value(not entry.enabled), False)
