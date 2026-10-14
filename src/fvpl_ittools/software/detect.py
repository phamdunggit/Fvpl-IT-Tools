"""Phát hiện phần mềm đã cài: đọc danh sách Programs and Features trong registry.

Không dùng `winget list`: chậm, phải có winget, và output là bảng chữ khó đọc chắc chắn. Mỗi ứng dụng so
tên theo mẫu `detect.uninstall_name` (mặc định là "<tên ứng dụng>*"), hoặc kiểm tra một file có tồn tại.
"""

from __future__ import annotations

import fnmatch
import os
import re
import shutil
import winreg
from dataclasses import dataclass

from .catalog import App, expand

_UNINSTALL = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
_NAME_VERSION = re.compile(r"\d+(?:\.\d+)+")


@dataclass(frozen=True)
class InstalledEntry:
    name: str
    version: str = ""
    publisher: str = ""
    hidden: bool = False  # Programs and Features không hiện: thành phần hệ thống, bản cập nhật của phần mềm khác
    click_to_run: bool = False  # Office / Microsoft 365 bản Click-to-Run (gỡ được bằng mục off.remove_c2r)


@dataclass(frozen=True)
class Detection:
    installed: bool
    version: str = ""
    matched: str = ""  # tên trong Programs and Features hoặc đường dẫn file đã khớp


def _read_entries(root, subkey: str, view: int = 0) -> list[InstalledEntry]:
    entries: list[InstalledEntry] = []
    try:
        key = winreg.OpenKey(root, subkey, 0, winreg.KEY_READ | view)
    except OSError:
        return entries
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
                    values = {}
                    for value_name in ("DisplayName", "DisplayVersion", "Publisher", "SystemComponent",
                                       "ParentKeyName", "UninstallString"):
                        try:
                            values[value_name] = str(winreg.QueryValueEx(child, value_name)[0]).strip()
                        except OSError:
                            values[value_name] = ""
            except OSError:
                continue
            if values["DisplayName"]:
                hidden = values["SystemComponent"] == "1" or bool(values["ParentKeyName"])
                click_to_run = "officeclicktorun.exe" in values["UninstallString"].lower()
                entries.append(InstalledEntry(values["DisplayName"], values["DisplayVersion"], values["Publisher"],
                                              hidden, click_to_run))
    return entries


def installed_programs(user_sid: str | None = None) -> list[InstalledEntry]:
    """Phần mềm cài cho cả máy (64-bit và 32-bit) và cho người dùng có SID `user_sid`."""
    entries = _read_entries(winreg.HKEY_LOCAL_MACHINE, _UNINSTALL, winreg.KEY_WOW64_64KEY)
    entries += _read_entries(winreg.HKEY_LOCAL_MACHINE, _UNINSTALL, winreg.KEY_WOW64_32KEY)
    if user_sid:
        entries += _read_entries(winreg.HKEY_USERS, f"{user_sid}\\{_UNINSTALL}")
    return entries


def detect(app: App, entries: list[InstalledEntry], share_root: str = "") -> Detection:
    if app.detect_file:
        path = expand(app.detect_file, share_root)
        if "{" not in path and os.path.exists(path):
            return Detection(True, matched=path)
        if not app.detect_names:
            return Detection(False)
    patterns = [pattern.lower() for pattern in (app.detect_names or (f"{app.name}*",))]
    matches = [entry for entry in entries if any(fnmatch.fnmatchcase(entry.name.lower(), pattern) for pattern in patterns)]
    if not matches:
        return Detection(False)
    best = max(matches, key=lambda entry: (_version_in_name(entry), _version_key(entry.version)))
    return Detection(True, best.version, best.name)


def conflicting_entries(app: App, entries: list[InstalledEntry]) -> list[InstalledEntry]:
    """Phần mềm đang cài (hiện trong Programs and Features) khớp mẫu `conflicts` của ứng dụng."""
    patterns = [pattern.lower() for pattern in app.conflict_names]
    if not patterns:
        return []
    return [entry for entry in entries
            if not entry.hidden and any(fnmatch.fnmatchcase(entry.name.lower(), pattern) for pattern in patterns)]


def conflicts(app: App, entries: list[InstalledEntry]) -> list[str]:
    return sorted({entry.name for entry in conflicting_entries(app, entries)})


def _version_in_name(entry: InstalledEntry) -> bool:
    """Một số phần mềm (như .NET) có hai dòng cùng tên, một dòng mang số phiên bản nội bộ của MSI.
    Ưu tiên dòng có DisplayVersion khớp với số phiên bản ghi trong tên."""
    found = _NAME_VERSION.search(entry.name)
    return bool(found and entry.version.startswith(found.group(0)))


def _version_key(version: str) -> tuple:
    parts = []
    for part in version.replace("-", ".").split("."):
        parts.append((0, int(part), "") if part.isdigit() else (1, 0, part))
    return tuple(parts)


def winget_path() -> str | None:
    """winget.exe của tài khoản đang chạy tool (App Execution Alias trong WindowsApps), hoặc None."""
    found = shutil.which("winget")
    if found:
        return found
    alias = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WindowsApps", "winget.exe")
    return alias if os.path.exists(alias) else None
