"""Thông tin máy đọc nhanh (registry + Windows API), dùng cho thanh trên cùng và trang Tổng quan."""

from __future__ import annotations

import winreg
from dataclasses import dataclass

from . import winapi

_CURRENT_VERSION = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion"
WIN11_FIRST_BUILD = 22000


@dataclass(frozen=True)
class MachineInfo:
    computer_name: str
    joined_domain: bool
    join_name: str
    dns_domain: str
    os_name: str
    display_version: str
    build: int
    ubr: int

    @property
    def domain_label(self) -> str:
        if self.joined_domain:
            return self.dns_domain or self.join_name
        return f"Workgroup {self.join_name}" if self.join_name else "Chưa vào domain"

    @property
    def os_label(self) -> str:
        version = f" {self.display_version}" if self.display_version else ""
        return f"{self.os_name}{version} (build {self.build}.{self.ubr})"


def _read(key, name: str, default=None):
    try:
        return winreg.QueryValueEx(key, name)[0]
    except OSError:
        return default


def windows_version() -> tuple[str, str, int, int]:
    """(tên, DisplayVersion, build, UBR). Win11 vẫn ghi ProductName là "Windows 10" nên phải sửa theo build."""
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _CURRENT_VERSION, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
        name = _read(key, "ProductName", "Windows")
        display = _read(key, "DisplayVersion") or _read(key, "ReleaseId", "")
        build = int(_read(key, "CurrentBuildNumber") or _read(key, "CurrentBuild", 0))
        ubr = int(_read(key, "UBR", 0))
    if build >= WIN11_FIRST_BUILD:
        name = name.replace("Windows 10", "Windows 11")
    return name, display, build, ubr


def manufacturer() -> str:
    """Hãng máy (SMBIOS), đọc từ registry nên không phải chờ WMI. Rỗng nếu không đọc được."""
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\BIOS") as key:
            return str(_read(key, "SystemManufacturer", "") or "").strip()
    except OSError:
        return ""


def quick_machine_info() -> MachineInfo:
    name, display, build, ubr = windows_version()
    join_name, status = winapi.join_information()
    return MachineInfo(
        computer_name=winapi.computer_name_ex(winapi.COMPUTER_NAME_NETBIOS),
        joined_domain=status == winapi.NETSETUP_DOMAIN,
        join_name=join_name,
        dns_domain=winapi.computer_name_ex(winapi.COMPUTER_NAME_DNS_DOMAIN),
        os_name=name,
        display_version=display,
        build=build,
        ubr=ubr,
    )
