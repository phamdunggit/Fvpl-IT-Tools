"""Các hàm Windows API gọi qua ctypes, để không phải kéo thêm pywin32."""

from __future__ import annotations

import ctypes
from ctypes import wintypes

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
wtsapi32 = ctypes.WinDLL("wtsapi32", use_last_error=True)
netapi32 = ctypes.WinDLL("netapi32")
shell32 = ctypes.WinDLL("shell32")

TOKEN_QUERY = 0x0008
TOKEN_USER_CLASS = 1
WTS_USER_NAME = 5
WTS_DOMAIN_NAME = 7
ERROR_INSUFFICIENT_BUFFER = 122
ERROR_MORE_DATA = 234

# GetComputerNameEx
COMPUTER_NAME_NETBIOS = 0
COMPUTER_NAME_DNS_DOMAIN = 2

# NetGetJoinInformation
NETSETUP_UNJOINED = 1
NETSETUP_WORKGROUP = 2
NETSETUP_DOMAIN = 3


class _SidAndAttributes(ctypes.Structure):
    _fields_ = [("Sid", ctypes.c_void_p), ("Attributes", wintypes.DWORD)]


class _TokenUser(ctypes.Structure):
    _fields_ = [("User", _SidAndAttributes)]


kernel32.GetCurrentProcess.restype = wintypes.HANDLE
kernel32.GetCurrentProcessId.restype = wintypes.DWORD
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.LocalFree.argtypes = [ctypes.c_void_p]
kernel32.LocalFree.restype = ctypes.c_void_p
kernel32.ProcessIdToSessionId.argtypes = [wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
kernel32.GetComputerNameExW.argtypes = [ctypes.c_int, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
kernel32.GetOEMCP.restype = wintypes.UINT

advapi32.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
advapi32.GetTokenInformation.argtypes = [
    wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
]
advapi32.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
advapi32.ConvertStringSidToSidW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_void_p)]
advapi32.LookupAccountSidW.argtypes = [
    wintypes.LPCWSTR, ctypes.c_void_p, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD),
    wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(ctypes.c_int),
]
advapi32.LookupAccountNameW.argtypes = [
    wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD),
    wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(ctypes.c_int),
]

wtsapi32.WTSQuerySessionInformationW.argtypes = [
    wintypes.HANDLE, wintypes.DWORD, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.DWORD),
]
wtsapi32.WTSFreeMemory.argtypes = [ctypes.c_void_p]

netapi32.NetGetJoinInformation.argtypes = [
    wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_int),
]
netapi32.NetGetJoinInformation.restype = wintypes.DWORD
netapi32.NetApiBufferFree.argtypes = [ctypes.c_void_p]


def _check(ok: int) -> None:
    if not ok:
        raise ctypes.WinError(ctypes.get_last_error())


def is_admin() -> bool:
    """True nếu tiến trình đang chạy với quyền admin (đã qua UAC)."""
    try:
        return bool(shell32.IsUserAnAdmin())
    except OSError:
        return False


def oem_codepage() -> int:
    return int(kernel32.GetOEMCP())


def sid_to_string(psid: int) -> str:
    buffer = ctypes.c_void_p()
    _check(advapi32.ConvertSidToStringSidW(psid, ctypes.byref(buffer)))
    try:
        return ctypes.wstring_at(buffer.value)
    finally:
        kernel32.LocalFree(buffer)


def current_process_sid() -> str:
    """SID của tài khoản đang chạy tool (có thể khác người đang đăng nhập nếu dùng Run as different user)."""
    token = wintypes.HANDLE()
    _check(advapi32.OpenProcessToken(kernel32.GetCurrentProcess(), TOKEN_QUERY, ctypes.byref(token)))
    try:
        size = wintypes.DWORD()
        advapi32.GetTokenInformation(token, TOKEN_USER_CLASS, None, 0, ctypes.byref(size))
        buffer = ctypes.create_string_buffer(size.value)
        _check(advapi32.GetTokenInformation(token, TOKEN_USER_CLASS, buffer, size, ctypes.byref(size)))
        token_user = ctypes.cast(buffer, ctypes.POINTER(_TokenUser)).contents
        return sid_to_string(token_user.User.Sid)
    finally:
        kernel32.CloseHandle(token)


def lookup_account_sid(sid: str) -> str | None:
    """Đổi SID thành tên dạng DOMAIN\\user. Trả về None nếu không tra được (ví dụ mất kết nối DC)."""
    psid = ctypes.c_void_p()
    if not advapi32.ConvertStringSidToSidW(sid, ctypes.byref(psid)):
        return None
    try:
        name = ctypes.create_unicode_buffer(256)
        domain = ctypes.create_unicode_buffer(256)
        name_len = wintypes.DWORD(len(name))
        domain_len = wintypes.DWORD(len(domain))
        use = ctypes.c_int()
        if not advapi32.LookupAccountSidW(
            None, psid, name, ctypes.byref(name_len), domain, ctypes.byref(domain_len), ctypes.byref(use)
        ):
            return None
        return f"{domain.value}\\{name.value}" if domain.value else name.value
    finally:
        kernel32.LocalFree(psid)


def lookup_account_name(account: str) -> str | None:
    """Đổi tên tài khoản (DOMAIN\\user) thành SID. Trả về None nếu không tra được."""
    sid_size = wintypes.DWORD(0)
    domain_len = wintypes.DWORD(0)
    use = ctypes.c_int()
    advapi32.LookupAccountNameW(
        None, account, None, ctypes.byref(sid_size), None, ctypes.byref(domain_len), ctypes.byref(use)
    )
    if ctypes.get_last_error() != ERROR_INSUFFICIENT_BUFFER or not sid_size.value:
        return None
    sid_buffer = ctypes.create_string_buffer(sid_size.value)
    domain = ctypes.create_unicode_buffer(domain_len.value)
    if not advapi32.LookupAccountNameW(
        None, account, sid_buffer, ctypes.byref(sid_size), domain, ctypes.byref(domain_len), ctypes.byref(use)
    ):
        return None
    return sid_to_string(ctypes.addressof(sid_buffer))


def session_account() -> tuple[str, str] | None:
    """(domain, user) của người đang đăng nhập vào phiên Windows mà tool đang chạy trong đó.

    Khi IT mở tool bằng "Run as different user", tiến trình vẫn nằm trong phiên của người dùng,
    nên hàm này trả về người dùng thật chứ không phải tài khoản IT.
    """
    session_id = wintypes.DWORD()
    if not kernel32.ProcessIdToSessionId(kernel32.GetCurrentProcessId(), ctypes.byref(session_id)):
        return None

    def query(info_class: int) -> str:
        buffer = ctypes.c_void_p()
        size = wintypes.DWORD()
        _check(wtsapi32.WTSQuerySessionInformationW(
            None, session_id.value, info_class, ctypes.byref(buffer), ctypes.byref(size)
        ))
        try:
            return ctypes.wstring_at(buffer.value) if buffer.value else ""
        finally:
            wtsapi32.WTSFreeMemory(buffer)

    try:
        user = query(WTS_USER_NAME)
        domain = query(WTS_DOMAIN_NAME)
    except OSError:
        return None
    return (domain, user) if user else None


def computer_name_ex(name_format: int) -> str:
    size = wintypes.DWORD(0)
    kernel32.GetComputerNameExW(name_format, None, ctypes.byref(size))
    if not size.value:
        return ""
    buffer = ctypes.create_unicode_buffer(size.value)
    if not kernel32.GetComputerNameExW(name_format, buffer, ctypes.byref(size)):
        return ""
    return buffer.value


def join_information() -> tuple[str, int]:
    """(tên domain/workgroup dạng NetBIOS, trạng thái NETSETUP_*)."""
    buffer = ctypes.c_void_p()
    status = ctypes.c_int()
    if netapi32.NetGetJoinInformation(None, ctypes.byref(buffer), ctypes.byref(status)) != 0:
        return "", 0
    try:
        return (ctypes.wstring_at(buffer.value) if buffer.value else ""), status.value
    finally:
        netapi32.NetApiBufferFree(buffer)
