"""Tìm chương trình đang giữ (khoá) một file, dùng Restart Manager của Windows (PLAN.md mục 5.7).

Không cần handle.exe. Chọn thư mục thì xét các file trong thư mục (tối đa MAX_FILES file). Chỉ đọc; kết thúc tiến
trình là việc riêng ở giao diện, có hỏi lại.
"""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path

MAX_FILES = 2000
ERROR_MORE_DATA = 234
CCH_RM_SESSION_KEY = 32
CCH_RM_MAX_APP_NAME = 255
CCH_RM_MAX_SVC_NAME = 63
APP_TYPES = {0: "", 1: "Ứng dụng", 2: "Ứng dụng", 3: "Dịch vụ", 4: "Explorer", 5: "Ứng dụng console",
             1000: "Không nên tắt"}  # RmCritical: tiến trình hệ thống (hoặc chính tool), tắt có thể làm treo máy


class RM_UNIQUE_PROCESS(ctypes.Structure):
    _fields_ = [("dwProcessId", wintypes.DWORD), ("ProcessStartTime", wintypes.FILETIME)]


class RM_PROCESS_INFO(ctypes.Structure):
    _fields_ = [
        ("Process", RM_UNIQUE_PROCESS),
        ("strAppName", wintypes.WCHAR * (CCH_RM_MAX_APP_NAME + 1)),
        ("strServiceShortName", wintypes.WCHAR * (CCH_RM_MAX_SVC_NAME + 1)),
        ("ApplicationType", ctypes.c_int),
        ("AppStatus", wintypes.ULONG),
        ("TSSessionId", wintypes.DWORD),
        ("bRestartable", wintypes.BOOL),
    ]


class LockError(RuntimeError):
    pass


@dataclass(frozen=True)
class Locker:
    pid: int
    name: str
    service: str
    kind: str


def _api():
    rm = ctypes.WinDLL("rstrtmgr")
    rm.RmStartSession.argtypes = [ctypes.POINTER(wintypes.DWORD), wintypes.DWORD, wintypes.LPWSTR]
    rm.RmRegisterResources.argtypes = [wintypes.DWORD, wintypes.UINT, ctypes.POINTER(wintypes.LPCWSTR),
                                       wintypes.UINT, ctypes.c_void_p, wintypes.UINT, ctypes.c_void_p]
    rm.RmGetList.argtypes = [wintypes.DWORD, ctypes.POINTER(wintypes.UINT), ctypes.POINTER(wintypes.UINT),
                             ctypes.POINTER(RM_PROCESS_INFO), ctypes.POINTER(wintypes.DWORD)]
    rm.RmEndSession.argtypes = [wintypes.DWORD]
    return rm


def files_in(target: str) -> list[str]:
    """File cần xét: chính file đó, hoặc các file trong thư mục (đệ quy, tối đa MAX_FILES)."""
    path = Path(target)
    if path.is_file():
        return [str(path)]
    if not path.is_dir():
        raise LockError(f"Không thấy file hoặc thư mục {target}")
    found: list[str] = []
    for root, _dirs, names in os.walk(path):
        for name in names:
            found.append(os.path.join(root, name))
            if len(found) >= MAX_FILES:
                return found
    return found


def lockers(target: str) -> list[Locker]:
    files = files_in(target)
    if not files:
        return []
    rm = _api()
    session = wintypes.DWORD()
    key = ctypes.create_unicode_buffer(CCH_RM_SESSION_KEY + 1)
    code = rm.RmStartSession(ctypes.byref(session), 0, key)
    if code:
        raise LockError(f"Không mở được phiên Restart Manager (mã {code})")
    try:
        array = (wintypes.LPCWSTR * len(files))(*files)
        code = rm.RmRegisterResources(session, len(files), array, 0, None, 0, None)
        if code:
            raise LockError(f"Không đăng ký được file với Restart Manager (mã {code})")
        needed, count, reasons = wintypes.UINT(0), wintypes.UINT(0), wintypes.DWORD(0)
        infos = (RM_PROCESS_INFO * 1)()
        code = rm.RmGetList(session, ctypes.byref(needed), ctypes.byref(count), infos, ctypes.byref(reasons))
        while code == ERROR_MORE_DATA:
            infos = (RM_PROCESS_INFO * max(needed.value, 1))()
            count = wintypes.UINT(needed.value)
            code = rm.RmGetList(session, ctypes.byref(needed), ctypes.byref(count), infos, ctypes.byref(reasons))
        if code:
            raise LockError(f"Restart Manager báo lỗi {code}")
        found = {}
        for info in infos[:count.value]:
            pid = int(info.Process.dwProcessId)
            found[pid] = Locker(pid, info.strAppName, info.strServiceShortName, APP_TYPES.get(info.ApplicationType, ""))
        return sorted(found.values(), key=lambda item: item.name.lower())
    finally:
        rm.RmEndSession(session)
