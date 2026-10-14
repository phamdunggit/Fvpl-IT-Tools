"""Xác định tài khoản đang chạy tool và người dùng thật đang đăng nhập.

Hai người này khác nhau khi IT mở tool bằng "Run as different user". Khi đó thiết lập
theo người dùng (HKCU) phải ghi vào HKEY_USERS\\<SID> của người dùng thật, xem PLAN.md mục 6.6.
"""

from __future__ import annotations

import os
import winreg
from dataclasses import dataclass

from . import winapi

_PROFILE_LIST = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\ProfileList"


@dataclass(frozen=True)
class UserIdentity:
    name: str
    sid: str
    profile_path: str | None = None

    @property
    def short_name(self) -> str:
        return self.name.rsplit("\\", 1)[-1]


def profile_path_for(sid: str) -> str | None:
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, f"{_PROFILE_LIST}\\{sid}") as key:
            value, _ = winreg.QueryValueEx(key, "ProfileImagePath")
    except OSError:
        return None
    return os.path.expandvars(value)


def hive_loaded(sid: str) -> bool:
    """True nếu registry của người dùng này đang được nạp (người đó đang đăng nhập)."""
    try:
        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_USERS, sid))
        return True
    except OSError:
        return False


def process_user() -> UserIdentity:
    sid = winapi.current_process_sid()
    name = winapi.lookup_account_sid(sid) or os.environ.get("USERNAME", sid)
    return UserIdentity(name=name, sid=sid, profile_path=profile_path_for(sid))


def session_user() -> UserIdentity | None:
    """Người đang đăng nhập vào phiên Windows chứa tool. None nếu không xác định được."""
    account = winapi.session_account()
    if account is None:
        return None
    domain, user = account
    name = f"{domain}\\{user}" if domain else user
    sid = winapi.lookup_account_name(name) or _sid_from_profiles(user)
    if sid is None:
        return None
    return UserIdentity(name=name, sid=sid, profile_path=profile_path_for(sid))


def user_profiles() -> list[UserIdentity]:
    """Người dùng (tài khoản máy / domain) có hồ sơ trên máy này, theo tên. Tên tra không được (mất kết nối DC) thì
    dùng tên thư mục hồ sơ."""
    result: list[UserIdentity] = []
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _PROFILE_LIST) as root:
            index = 0
            while True:
                try:
                    sid = winreg.EnumKey(root, index)
                except OSError:
                    break
                index += 1
                if not sid.startswith("S-1-5-21-") or sid.endswith(".bak"):
                    continue
                path = profile_path_for(sid)
                if not path or not os.path.isdir(path):
                    continue
                name = winapi.lookup_account_sid(sid) or os.path.basename(path)
                result.append(UserIdentity(name=name, sid=sid, profile_path=path))
    except OSError:
        return result
    return sorted(result, key=lambda user: user.short_name.lower())


def _sid_from_profiles(user: str) -> str | None:
    """Dự phòng khi không tra được SID (mất kết nối DC): dò ProfileList theo tên thư mục profile.

    Ưu tiên profile đang được nạp vì người dùng đó đang đăng nhập.
    """
    matches: list[str] = []
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _PROFILE_LIST) as root:
            index = 0
            while True:
                try:
                    sid = winreg.EnumKey(root, index)
                except OSError:
                    break
                index += 1
                path = profile_path_for(sid)
                if path and os.path.basename(path).lower() == user.lower():
                    matches.append(sid)
    except OSError:
        return None
    loaded = [sid for sid in matches if hive_loaded(sid)]
    return (loaded or matches or [None])[0]
