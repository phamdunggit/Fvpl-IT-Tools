"""Gỡ phần mềm đã cài (tab "Gỡ phần mềm" ở trang Tối ưu & dọn dẹp).

Đọc Programs and Features trong registry (cả máy 64 / 32-bit và phần mềm cài riêng cho người đang đăng nhập, như
WPS Office), đánh dấu phần mềm nên gỡ / nên giữ theo data/uninstall.yaml (cộng thêm `<kho>\\config\\uninstall.yaml`).

Lệnh gỡ chọn theo thứ tự: MSI (msiexec /x … /qn), QuietUninstallString, tham số im lặng khai báo trong YAML,
Inno Setup (/VERYSILENT), trình gỡ kiểu Chrome (--force-uninstall). Không biết cách gỡ im lặng thì mở trình gỡ của
hãng để IT bấm theo. Xong khi mục biến khỏi Programs and Features, không tin vào mã thoát của trình gỡ vì nhiều trình
gỡ (NSIS) chép mình ra thư mục tạm rồi thoát ngay.
"""

from __future__ import annotations

import fnmatch
import hashlib
import logging
import ntpath
import os
import re
import winreg
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from ..actions.model import Action, PowerShellStep, Risk
from ..core import paths, progress, shell
from ..core.migrate import expand_profile

log = logging.getLogger(__name__)

UNINSTALL = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
UNINSTALL_32 = r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"
BUNDLED_RULES = paths.DATA_DIR / "uninstall.yaml"
SHARE_RULES = Path("config") / "uninstall.yaml"
CATEGORY = "Gỡ phần mềm"

INNO_ARGS = "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART"
SILENT_MINUTES = 15
INTERACTIVE_MINUTES = 30

_GUID = re.compile(r"^\{[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}\}$")
_MSI_COMMAND = re.compile(r"(?i)msiexec(?:\.exe)?\"?\s.*?/[ix]\s*(\{[0-9A-F-]{36}\})")
_INNO_FILE = re.compile(r"(?i)^unins\d{3}\.exe$")
_UPDATES = {"update", "hotfix", "security update", "service pack"}


@dataclass(frozen=True)
class Program:
    name: str
    key: str                  # đường dẫn registry đầy đủ, ví dụ HKEY_LOCAL_MACHINE\SOFTWARE\...\Uninstall\{GUID}
    version: str = ""
    publisher: str = ""
    install_date: str = ""    # yyyymmdd như trong registry
    size_kb: int = 0
    uninstall: str = ""
    quiet: str = ""
    msi_code: str = ""
    inno: bool = False
    hidden: bool = False      # Programs and Features không hiện: thành phần, bản cập nhật, không có lệnh gỡ
    no_remove: bool = False
    user_sid: str = ""        # cài riêng cho người dùng này (khoá trong HKEY_USERS)

    @property
    def per_user(self) -> bool:
        return bool(self.user_sid)

    @property
    def date_text(self) -> str:
        text = self.install_date
        if len(text) == 8 and text.isdigit():
            return f"{text[6:]}/{text[4:6]}/{text[:4]}"
        return ""


@dataclass(frozen=True)
class Rule:
    patterns: tuple[str, ...]
    reason: str = ""
    args: str = ""

    def matches(self, name: str) -> bool:
        lowered = name.lower()
        return any(fnmatch.fnmatchcase(lowered, pattern) for pattern in self.patterns)


@dataclass
class Rules:
    unwanted: list[Rule] = field(default_factory=list)
    keep: list[Rule] = field(default_factory=list)
    silent: list[Rule] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @staticmethod
    def _first(rules: list[Rule], name: str) -> Rule | None:
        return next((rule for rule in rules if rule.matches(name)), None)

    def unwanted_reason(self, program: Program) -> str:
        rule = self._first(self.unwanted, program.name)
        return (rule.reason or "Nên gỡ") if rule else ""

    def keep_reason(self, program: Program) -> str:
        if self.unwanted_reason(program):
            return ""
        rule = self._first(self.keep, program.name)
        return (rule.reason or "Nên giữ") if rule else ""

    def silent_args(self, program: Program) -> str:
        rule = self._first(self.silent, program.name)
        return rule.args if rule else ""


# ---------------------------------------------------------------- danh sách quy tắc


def _parse_rules(data: object, source: str, rules: Rules) -> None:
    if not isinstance(data, dict) or set(data) - {"unwanted", "keep", "silent"}:
        rules.errors.append(f"{source}: file chỉ có các phần 'unwanted:', 'keep:', 'silent:'")
        return
    for section in ("unwanted", "keep", "silent"):
        entries = data.get(section) or []
        if not isinstance(entries, list):
            rules.errors.append(f"{source}: '{section}' phải là danh sách, mỗi mục bắt đầu bằng '- match: …'")
            continue
        for index, entry in enumerate(entries, start=1):
            if not isinstance(entry, dict) or not str(entry.get("match") or "").strip():
                rules.errors.append(f"{source}: mục {index} của '{section}' thiếu 'match'")
                continue
            patterns = tuple(part.strip().lower() for part in str(entry["match"]).split("|") if part.strip())
            args = str(entry.get("args") or "").strip()
            if section == "silent" and not args:
                rules.errors.append(f"{source}: mục {index} của 'silent' thiếu 'args'")
                continue
            getattr(rules, section).append(Rule(patterns, str(entry.get("reason") or "").strip(), args))


def load_rules(share_root: str = "") -> Rules:
    """Quy tắc của kho (nếu có) xét trước quy tắc đóng gói kèm tool. Gọi ở thread nền: kho có thể là share chậm."""
    rules = Rules()
    files = []
    if share_root:
        files.append(Path(share_root) / SHARE_RULES)
    files.append(BUNDLED_RULES)
    for file in files:
        try:
            if not file.is_file():
                continue
            data = yaml.safe_load(file.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError) as exc:
            rules.errors.append(f"{file}: không đọc được file ({exc})")
            continue
        _parse_rules(data, file.name if file == BUNDLED_RULES else str(file), rules)
    for error in rules.errors:
        log.warning("%s", error)
    return rules


# ---------------------------------------------------------------- đọc registry


def _value(key, name: str):
    try:
        return winreg.QueryValueEx(key, name)[0]
    except OSError:
        return None


def _text(key, name: str) -> str:
    value = _value(key, name)
    return str(value).strip() if value is not None else ""


def _read(root, path: str, subkey: str, view: int, user_sid: str = "") -> list[Program]:
    """`path`: đường dẫn thật của khoá (nhánh 32-bit đọc qua KEY_WOW64_32KEY nhưng nằm ở WOW6432Node)."""
    programs: list[Program] = []
    try:
        key = winreg.OpenKey(root, subkey, 0, winreg.KEY_READ | view)
    except OSError:
        return programs
    with key:
        index = 0
        while True:
            try:
                child_name = winreg.EnumKey(key, index)
            except OSError:
                break
            index += 1
            try:
                with winreg.OpenKey(key, child_name) as child:
                    name = _text(child, "DisplayName")
                    if not name:
                        continue
                    uninstall = _text(child, "UninstallString")
                    quiet = _text(child, "QuietUninstallString")
                    msi_code = ""
                    if _value(child, "WindowsInstaller") == 1 and _GUID.match(child_name):
                        msi_code = child_name.upper()
                    elif match := _MSI_COMMAND.search(uninstall):
                        msi_code = match.group(1).upper()
                    size = _value(child, "EstimatedSize")
                    hidden = (_value(child, "SystemComponent") == 1 or bool(_text(child, "ParentKeyName"))
                              or _text(child, "ReleaseType").lower() in _UPDATES
                              or not (uninstall or quiet or msi_code))
                    file_name = ntpath.basename(split_command(uninstall)[0]) if uninstall else ""
                    programs.append(Program(
                        name=name, key=f"{path}\\{child_name}", version=_text(child, "DisplayVersion"),
                        publisher=_text(child, "Publisher"), install_date=_text(child, "InstallDate"),
                        size_kb=size if isinstance(size, int) and size > 0 else 0, uninstall=uninstall, quiet=quiet,
                        msi_code=msi_code,
                        inno=bool(_value(child, "Inno Setup: App Path") is not None or _INNO_FILE.match(file_name)),
                        hidden=hidden, no_remove=_value(child, "NoRemove") == 1, user_sid=user_sid,
                    ))
            except OSError:
                continue
    return programs


def read_programs(user_sid: str | None = None) -> list[Program]:
    """Phần mềm cài cho cả máy (64-bit, 32-bit) và cho người dùng có SID `user_sid`, xếp theo tên."""
    machine = winreg.HKEY_LOCAL_MACHINE
    programs = _read(machine, f"HKEY_LOCAL_MACHINE\\{UNINSTALL}", UNINSTALL, winreg.KEY_WOW64_64KEY)
    programs += _read(machine, f"HKEY_LOCAL_MACHINE\\{UNINSTALL_32}", UNINSTALL, winreg.KEY_WOW64_32KEY)
    if user_sid:
        subkey = f"{user_sid}\\{UNINSTALL}"
        programs += _read(winreg.HKEY_USERS, f"HKEY_USERS\\{subkey}", subkey, 0, user_sid)
    return sorted(programs, key=lambda program: program.name.lower())


# ---------------------------------------------------------------- lệnh gỡ


def split_command(command: str) -> tuple[str, str]:
    """Tách lệnh trong UninstallString thành (file, tham số). Chấp nhận đường dẫn có dấu cách không đặt trong ngoặc."""
    command = command.strip()
    if command.startswith('"'):
        end = command.find('"', 1)
        if end > 0:
            return command[1:end], command[end + 1:].strip()
        return command.strip('"'), ""
    match = re.match(r"(?i)^(.+?\.exe)(?=\s|$)(.*)$", command)
    if match:
        return match.group(1), match.group(2).strip()
    file, _, args = command.partition(" ")
    return file, args.strip()


@dataclass(frozen=True)
class Plan:
    file: str
    args: str
    silent: bool
    msi: bool = False

    @property
    def how(self) -> str:
        return "Tự gỡ" if self.silent else "Bấm theo trình gỡ"


def plan(program: Program, rules: Rules, profile: str = "") -> Plan | None:
    """Cách gỡ một phần mềm, None khi không có lệnh gỡ."""
    if program.msi_code:
        return Plan("msiexec.exe", f"/x {program.msi_code} /qn /norestart", True, msi=True)
    expand = (lambda text: expand_profile(text, profile)) if program.per_user and profile else os.path.expandvars
    if program.quiet:
        file, args = split_command(program.quiet)
        return Plan(expand(file), args, True)
    if not program.uninstall:
        return None
    file, args = split_command(program.uninstall)
    file = expand(file)
    extra = rules.silent_args(program)
    if extra:
        return Plan(file, f"{args} {extra}".strip(), True)
    if program.inno:
        return Plan(file, f"{args} {INNO_ARGS}".strip(), True)
    if ntpath.basename(file).lower() in ("winget", "winget.exe") and "--silent" not in args.lower():
        return Plan(file, f"{args} --silent --disable-interactivity", True)  # phần mềm cài bằng winget (portable)
    if "--uninstall" in args.lower():  # Chrome, Cốc Cốc, Brave…: setup.exe --uninstall
        return Plan(file, args if "--force-uninstall" in args.lower() else f"{args} --force-uninstall", True)
    return Plan(file, args, False)


_MSI_SCRIPT = """\
if (-not (Test-Path -LiteralPath __KEY__)) { Write-Output ('{0} đã được gỡ trước đó.' -f __NAME__); exit 0 }
__MARK__
$process = Start-Process -FilePath msiexec.exe -ArgumentList __ARGS__ -Wait -PassThru
Write-Output ('msiexec trả mã {0}.' -f $process.ExitCode)
if ($process.ExitCode -in 0, 1605, 3010, 1641) { Write-Output ('Đã gỡ {0}.' -f __NAME__) }
exit $process.ExitCode
"""

# Chạy trình gỡ, chờ tới khi mục biến khỏi Programs and Features. Trình gỡ (và tiến trình nó chép ra thư mục tạm)
# đã đóng hết 15 giây mà mục vẫn còn thì coi như chưa gỡ được. Phần mềm cài riêng cho người đang đăng nhập mà tool
# chạy bằng tài khoản khác thì chạy trình gỡ bằng tài khoản người dùng qua một tác vụ chạy một lần.
_EXE_SCRIPT = """\
$key = __KEY__
$file = __FILE__
$arguments = __ARGS__
$asUser = __AS_USER__
if (-not (Test-Path -LiteralPath $key)) { Write-Output ('{0} đã được gỡ trước đó.' -f __NAME__); exit 0 }
if ((Split-Path -Path $file) -and -not (Test-Path -LiteralPath $file)) {
    Write-Output ('Không thấy trình gỡ: {0}' -f $file)
    exit 3
}
__MARK__
$start = Get-Date
$temps = @([IO.Path]::GetTempPath())
if ($TargetUserProfile) { $temps += Join-Path $TargetUserProfile 'AppData\\Local\\Temp' }
function Test-Helper {
    foreach ($item in Get-Process -ErrorAction SilentlyContinue) {
        try {
            if (-not $item.Path -or $item.StartTime -lt $start) { continue }
            foreach ($temp in $temps) { if ($item.Path.StartsWith($temp, 'OrdinalIgnoreCase')) { return $true } }
        } catch { }
    }
    return $false
}
$task = $null
try {
    if ($asUser) {
        $task = 'FVPL-ITTools-Uninstall-' + [guid]::NewGuid().ToString('N').Substring(0, 8)
        if ($arguments) { $taskAction = New-ScheduledTaskAction -Execute $file -Argument $arguments }
        else { $taskAction = New-ScheduledTaskAction -Execute $file }
        $principal = New-ScheduledTaskPrincipal -UserId $TargetUserName -LogonType Interactive -RunLevel Limited
        Register-ScheduledTask -TaskName $task -Action $taskAction -Principal $principal -Force | Out-Null
        Start-ScheduledTask -TaskName $task
        $running = { (Get-ScheduledTask -TaskName $task -ErrorAction SilentlyContinue).State -eq 'Running' }
    } else {
        if ($arguments) { $process = Start-Process -FilePath $file -ArgumentList $arguments -PassThru }
        else { $process = Start-Process -FilePath $file -PassThru }
        $running = { -not $process.HasExited }
    }
    $deadline = $start.AddMinutes(__MINUTES__)
    $idle = $null
    while ((Test-Path -LiteralPath $key) -and (Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 2
        if ((& $running) -or (Test-Helper)) { $idle = $null; continue }
        if (-not $idle) { $idle = Get-Date } elseif (((Get-Date) - $idle).TotalSeconds -ge 15) { break }
    }
} catch {
    Write-Output ('Không chạy được trình gỡ: {0}' -f $_.Exception.Message)
    exit 7
} finally {
    if ($task) { Unregister-ScheduledTask -TaskName $task -Confirm:$false -ErrorAction SilentlyContinue }
}
if (Test-Path -LiteralPath $key) {
    if ((Get-Date) -ge $deadline) { exit 6 }
    exit 5
}
Write-Output ('Đã gỡ {0}.' -f __NAME__)
"""

_MESSAGES_EXE = (
    (3, "Không thấy file trình gỡ, phần mềm có thể đã bị xoá dở. Gỡ trong Settings > Apps"),
    (5, "Trình gỡ đã đóng nhưng phần mềm vẫn còn: có thể đã bấm Huỷ, hoặc cần khởi động lại máy rồi xem lại"),
    (6, "Quá thời gian chờ, trình gỡ vẫn chưa xong"),
    (7, "Không chạy được trình gỡ"),
)
_MESSAGES_MSI = (
    (1602, "Đã huỷ gỡ"),
    (1603, "Gỡ lỗi (MSI 1603): đóng phần mềm này rồi thử lại, hoặc khởi động lại máy"),
    (1618, "Đang có bộ cài / gỡ khác chạy, chờ xong rồi thử lại"),
)


def action_id(program: Program) -> str:
    digest = hashlib.sha1(program.key.lower().encode("utf-8")).hexdigest()[:10]
    return f"soft.uninstall_{digest}"


def uninstall_action(program: Program, rules: Rules, as_user: bool = False, profile: str = "") -> Action | None:
    """Mục gỡ một phần mềm. `as_user`: phần mềm cài riêng cho người đang đăng nhập và tool chạy bằng tài khoản khác."""
    how = plan(program, rules, profile)
    if how is None:
        return None
    key = shell.ps_quote(f"Registry::{program.key}")
    name = shell.ps_quote(program.name)
    if how.msi:
        script = (_MSI_SCRIPT.replace("__KEY__", key).replace("__NAME__", name)
                  .replace("__ARGS__", shell.ps_quote(how.args)).replace("__MARK__", progress.marker("Đang gỡ")))
        step = PowerShellStep(script=script, timeout=SILENT_MINUTES * 60 + 60, ok_codes=(0, 1605),
                              messages=_MESSAGES_MSI)
    else:
        minutes = SILENT_MINUTES if how.silent else INTERACTIVE_MINUTES
        mark = progress.marker("Đang gỡ" if how.silent else "Làm theo cửa sổ gỡ cài đặt của phần mềm")
        script = (_EXE_SCRIPT.replace("__KEY__", key).replace("__NAME__", name)
                  .replace("__FILE__", shell.ps_quote(how.file)).replace("__ARGS__", shell.ps_quote(how.args))
                  .replace("__AS_USER__", "$true" if as_user else "$false").replace("__MINUTES__", str(minutes))
                  .replace("__MARK__", mark))
        step = PowerShellStep(script=script, timeout=minutes * 60 + 60, messages=_MESSAGES_EXE)
    return Action(
        id=action_id(program), name=f"Gỡ {program.name}", category=CATEGORY, page="optimize", apply=(step,),
        risk=Risk.CAUTION, admin=not program.per_user or as_user,
        description=f"Lệnh gỡ: {how.file} {how.args}".strip(),
    )


def unwanted(programs: list[Program], rules: Rules) -> list[tuple[Program, str]]:
    """Phần mềm nên gỡ đang có trên máy (chỉ mục hiện trong Programs and Features)."""
    return [(program, reason) for program in programs
            if not program.hidden and (reason := rules.unwanted_reason(program))]


def size_text(kb: int) -> str:
    if kb <= 0:
        return ""
    if kb < 1024:
        return f"{kb} KB"
    if kb < 1024 * 1024:
        return f"{kb / 1024:.0f} MB"
    return f"{kb / 1024 / 1024:.1f} GB"
