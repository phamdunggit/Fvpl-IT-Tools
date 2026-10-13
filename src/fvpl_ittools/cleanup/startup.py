"""Chương trình chạy cùng Windows: liệt kê và bật/tắt kiểu Task Manager (PLAN.md mục 5.4).

Bật/tắt bằng khoá StartupApproved (giống tab Startup của Task Manager), không xoá mục Run hay shortcut nào.
Mỗi lần bật/tắt là một mục registry chạy qua executor nên có nhật ký và hoàn tác được ở trang Nhật ký.

Giá trị StartupApproved là 12 byte: byte đầu chẵn (02, 06) là bật, lẻ (03, 07) là tắt; 8 byte cuối là thời điểm
tắt (FILETIME). Không có giá trị nghĩa là đang bật.
"""

from __future__ import annotations

import os
import struct
import time
import winreg
from dataclasses import dataclass
from pathlib import Path

from ..actions.model import Action, RegistryStep, Scope
from ..core import registry
from ..core.executor import Env

_RUN = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
_RUN32 = r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Run"
_APPROVED = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved"


@dataclass(frozen=True)
class StartupEntry:
    name: str             # tên giá trị Run hoặc tên file trong thư mục Startup
    command: str          # lệnh chạy hoặc đường dẫn file
    source: str           # nhãn hiện cho IT
    approved_key: str     # khoá StartupApproved tương ứng (HKLM\… hoặc HKCU\…)
    enabled: bool

    @property
    def for_user(self) -> bool:
        return self.approved_key.startswith("HKCU")

    @property
    def key(self) -> str:
        return f"{self.approved_key}|{self.name}"


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


def toggle_action(entry: StartupEntry, enable: bool) -> Action:
    """Mục registry bật/tắt một chương trình khởi động, chạy bằng executor (có nhật ký, hoàn tác được)."""
    verb = "Bật" if enable else "Tắt"
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
