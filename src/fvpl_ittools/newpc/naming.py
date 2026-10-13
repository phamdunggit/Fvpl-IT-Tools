"""Bước 1 của wizard: tên máy theo quy ước <tiền tố><mã phòng><2 chữ số>, ví dụ FVPL-KT05 (PLAN.md mục 11).

Gợi ý số kế tiếp từ danh sách máy đã có trong AD. Máy chưa vào domain thì hỏi AD bằng tài khoản join (LDAP),
chỉ đọc. Không hỏi được AD thì IT tự gõ số.
"""

from __future__ import annotations

import json
import re
import threading
from typing import Iterable

from ..core import shell

NAME_MAX = 15  # tên NetBIOS của máy tối đa 15 ký tự
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]*$")
_PREFIX = re.compile(r"^[A-Za-z0-9-]{0,10}$")
_DOMAIN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.\-]{0,252}$")
AD_TIMEOUT = 60

_AD_SCRIPT = """\
$filter = '(&(objectCategory=computer)(cn={0}*))' -f $Prefix
if ($Credential) {
    $password = $Credential.GetNetworkCredential().Password
    $root = New-Object System.DirectoryServices.DirectoryEntry(('LDAP://' + $Domain), $Credential.UserName, $password)
}
else {
    $root = New-Object System.DirectoryServices.DirectoryEntry(('LDAP://' + $Domain))
}
$searcher = New-Object System.DirectoryServices.DirectorySearcher($root, $filter)
$searcher.PageSize = 500
[void]$searcher.PropertiesToLoad.Add('cn')
$names = @(foreach ($item in $searcher.FindAll()) { [string]$item.Properties['cn'][0] })
ConvertTo-Json -InputObject @($names) -Compress
"""


class NamingError(RuntimeError):
    pass


def name_problem(name: str) -> str | None:
    """Lý do tên máy không dùng được, hoặc None nếu được."""
    if not name:
        return "Chưa có tên máy."
    if len(name) > NAME_MAX:
        return f"Tên máy tối đa {NAME_MAX} ký tự (đang {len(name)})."
    if not _NAME.match(name) or name.endswith("-"):
        return "Tên máy chỉ gồm chữ không dấu, số và dấu gạch ngang, không bắt đầu / kết thúc bằng gạch ngang."
    if name.isdigit():
        return "Tên máy không được chỉ toàn số."
    return None


def base_name(prefix: str, department: str) -> str:
    return f"{prefix}{department}".upper()


def suggest_name(prefix: str, department: str, existing: Iterable[str]) -> str:
    """Số kế tiếp sau số lớn nhất đang có (không lấp chỗ trống: số cũ có thể là máy đang cất trong kho)."""
    base = base_name(prefix, department)
    pattern = re.compile(rf"^{re.escape(base)}(\d+)$", re.IGNORECASE)
    numbers = [int(match.group(1)) for name in existing if (match := pattern.match(name.strip()))]
    return f"{base}{max(numbers, default=0) + 1:02d}"


def taken(name: str, existing: Iterable[str]) -> bool:
    return name.upper() in {item.strip().upper() for item in existing}


def ad_script() -> str:
    return _AD_SCRIPT


def existing_names(domain: str, prefix: str, credential: tuple[str, str] | None = None,
                   cancel: threading.Event | None = None) -> list[str]:
    """Tên các máy trong AD bắt đầu bằng `prefix` (ví dụ FVPL-KT). Chỉ đọc."""
    if not _DOMAIN.match(domain):
        raise NamingError("Chưa có tên domain (khai báo domain trong site.yaml).")
    if not _PREFIX.match(prefix):
        raise NamingError(f"Tiền tố tên máy không hợp lệ: {prefix!r}")
    result = shell.run_powershell(_AD_SCRIPT, credential=credential, variables={"Domain": domain, "Prefix": prefix},
                                  timeout=AD_TIMEOUT, cancel=cancel)
    if result.cancelled:
        raise NamingError("Đã huỷ")
    if result.timed_out:
        raise NamingError(f"AD không trả lời sau {AD_TIMEOUT} giây")
    lines = [line for line in result.output.splitlines() if line.startswith("[")]
    if result.code != 0 or not lines:
        detail = result.output.strip().splitlines()[-1] if result.output.strip() else f"mã lỗi {result.code}"
        raise NamingError(detail)
    try:
        return [str(name) for name in json.loads(lines[-1])]
    except ValueError as exc:
        raise NamingError(f"Kết quả không đọc được: {exc}") from exc
