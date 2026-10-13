"""Tra mật khẩu Windows LAPS và khoá khôi phục BitLocker của một máy trong AD (trang Tiện ích).

Không đi qua executor: kết quả chỉ trả về giao diện, không vào khung log hay file log. Log chỉ ghi ai tra máy nào.
Mật khẩu LAPS đọc bằng module LAPS có sẵn trong Windows (Get-LapsADPassword, giải mã được mật khẩu đã mã hoá);
khoá BitLocker đọc thẳng bằng LDAP (DirectorySearcher), không cần cài RSAT. Xem docs/BITLOCKER-LAPS-GPO.md.
"""

from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass

from . import shell

COMPUTER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,14}$")
DOMAIN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.\-]{0,252}$")
TIMEOUT = 60

_LAPS = """\
if (-not (Get-Command Get-LapsADPassword -ErrorAction SilentlyContinue)) {
    Write-Output 'Máy đang chạy tool chưa có module LAPS của Windows (cần bản cập nhật Windows từ 04/2023).'
    exit 3
}
$options = @{ Identity = $Computer; AsPlainText = $true }
if ($Domain) { $options.Domain = $Domain }
if ($Credential) { $options.Credential = $Credential; $options.DecryptionCredential = $Credential }
try { $item = Get-LapsADPassword @options }
catch { Write-Output $_.Exception.Message; exit 4 }
if (-not $item) {
    Write-Output 'Máy này chưa có mật khẩu LAPS trong AD: chưa nhận GPO LAPS hoặc chưa tới lượt xử lý (mỗi giờ một lần).'
    exit 5
}
[pscustomobject]@{
    account = [string]$item.Account
    password = [string]$item.Password
    updated = $(if ($item.PasswordUpdateTime) { $item.PasswordUpdateTime.ToString('dd\\/MM\\/yyyy HH:mm') } else { '' })
    expires = $(if ($item.ExpirationTimestamp) { $item.ExpirationTimestamp.ToString('dd\\/MM\\/yyyy HH:mm') } else { '' })
    source = [string]$item.Source
    decryption = [string]$item.DecryptionStatus
} | ConvertTo-Json -Compress
"""

_EXPIRE = """\
if (-not (Get-Command Set-LapsADPasswordExpirationTime -ErrorAction SilentlyContinue)) {
    Write-Output 'Máy đang chạy tool chưa có module LAPS của Windows (cần bản cập nhật Windows từ 04/2023).'
    exit 3
}
$options = @{ Identity = $Computer }
if ($Domain) { $options.Domain = $Domain }
if ($Credential) { $options.Credential = $Credential }
try { Set-LapsADPasswordExpirationTime @options | Out-Null }
catch { Write-Output $_.Exception.Message; exit 4 }
Write-Output '{"ok": true}'
"""

_BITLOCKER = """\
$path = 'LDAP://' + $Domain
if ($Credential) {
    $root = New-Object System.DirectoryServices.DirectoryEntry($path, $Credential.UserName, $Credential.GetNetworkCredential().Password)
}
else { $root = New-Object System.DirectoryServices.DirectoryEntry($path) }
try {
    $finder = New-Object System.DirectoryServices.DirectorySearcher($root, ('(&(objectCategory=computer)(cn={0}))' -f $Computer))
    $found = $finder.FindOne()
}
catch { Write-Output $_.Exception.Message; exit 4 }
if (-not $found) { Write-Output ('Không thấy máy {0} trong AD.' -f $Computer); exit 4 }
$keysFinder = New-Object System.DirectoryServices.DirectorySearcher($found.GetDirectoryEntry(), '(objectClass=msFVE-RecoveryInformation)')
foreach ($name in 'cn', 'msFVE-RecoveryPassword', 'whenCreated') { [void]$keysFinder.PropertiesToLoad.Add($name) }
$keys = @(foreach ($item in $keysFinder.FindAll()) {
    $cn = [string]$item.Properties['cn'][0]
    $id = ''
    if ($cn -match '\\{([0-9A-Fa-f-]{36})\\}') { $id = $Matches[1].ToUpper() }
    $created = ''
    if ($item.Properties['whencreated'].Count) { $created = ([datetime]$item.Properties['whencreated'][0]).ToLocalTime().ToString('dd\\/MM\\/yyyy HH:mm') }
    [pscustomobject]@{ id = $id; password = [string]$item.Properties['msfve-recoverypassword'][0]; created = $created }
})
ConvertTo-Json -InputObject @($keys) -Compress
"""


class SecretLookupError(RuntimeError):
    pass


@dataclass(frozen=True)
class LapsPassword:
    computer: str
    account: str
    password: str
    updated: str
    expires: str
    encrypted: bool
    decryption: str


@dataclass(frozen=True)
class RecoveryKey:
    key_id: str        # Recovery key ID (màn hình xanh hiện 8 ký tự đầu)
    password: str      # 48 chữ số, rỗng nếu tài khoản không có quyền đọc
    created: str


def check_computer(name: str) -> str:
    name = name.strip().upper()
    if not COMPUTER.match(name):
        raise SecretLookupError("Tên máy chỉ gồm chữ không dấu, số, gạch ngang, tối đa 15 ký tự.")
    return name


def _run(script: str, computer: str, domain: str, credential: tuple[str, str] | None,
         cancel: threading.Event | None) -> str:
    if domain and not DOMAIN.match(domain):
        raise SecretLookupError(f"Tên domain không hợp lệ: {domain!r}")
    result = shell.run_powershell(script, credential=credential,
                                  variables={"Computer": computer, "Domain": domain},
                                  timeout=TIMEOUT, cancel=cancel)
    if result.cancelled:
        raise SecretLookupError("Đã huỷ")
    if result.timed_out:
        raise SecretLookupError(f"AD không trả lời sau {TIMEOUT} giây")
    lines = [line.strip() for line in result.output.splitlines() if line.strip()]
    if result.code != 0 or not lines:
        raise SecretLookupError(lines[-1] if lines else f"mã lỗi {result.code}")
    return lines[-1]


def laps_password(computer: str, domain: str, credential: tuple[str, str] | None = None,
                  cancel: threading.Event | None = None) -> LapsPassword:
    computer = check_computer(computer)
    data = json.loads(_run(_LAPS, computer, domain, credential, cancel))
    decryption = str(data.get("decryption") or "")
    if not data.get("password"):
        if decryption and decryption.lower() != "success":
            raise SecretLookupError(f"Có mật khẩu nhưng tài khoản này không được giải mã ({decryption}): cần thuộc nhóm "
                                    "trong 'Configure authorized password decryptors' của GPO LAPS.")
        raise SecretLookupError("Tài khoản này không có quyền đọc mật khẩu LAPS của máy đó.")
    return LapsPassword(computer, str(data.get("account") or ""), str(data["password"]), str(data.get("updated") or ""),
                        str(data.get("expires") or ""), "encrypted" in str(data.get("source") or "").lower(),
                        decryption)


def expire_laps_password(computer: str, domain: str, credential: tuple[str, str] | None = None,
                         cancel: threading.Event | None = None) -> None:
    _run(_EXPIRE, check_computer(computer), domain, credential, cancel)


def bitlocker_keys(computer: str, domain: str, credential: tuple[str, str] | None = None,
                   cancel: threading.Event | None = None) -> list[RecoveryKey]:
    computer = check_computer(computer)
    if not domain:
        raise SecretLookupError("Chưa biết domain (máy này chưa vào domain, site.yaml chưa có domain).")
    data = json.loads(_run(_BITLOCKER, computer, domain, credential, cancel))
    items = data if isinstance(data, list) else [data]
    keys = [RecoveryKey(str(item.get("id") or ""), str(item.get("password") or ""), str(item.get("created") or ""))
            for item in items if isinstance(item, dict)]
    return sorted(keys, key=lambda key: key.created[6:10] + key.created[3:5] + key.created[:2] + key.created[11:],
                  reverse=True)


def scripts() -> list[tuple[str, str]]:
    """Script của module này, để test soát cú pháp và độ dài."""
    return [("adsecrets LAPS", _LAPS), ("adsecrets đổi LAPS", _EXPIRE), ("adsecrets BitLocker", _BITLOCKER)]
