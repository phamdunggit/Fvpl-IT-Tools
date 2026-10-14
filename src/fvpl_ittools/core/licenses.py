"""Key bản quyền Windows / Office của công ty (tab "Key bản quyền" ở trang Tiện ích).

Mọi key nằm trong một file JSON (`license-keys.json`): mặc định cạnh tool trên USB / SSD, IT chọn file khác thì tool
nhớ. Muốn dùng ở máy / USB khác thì chỉ cần chép file này. File KHÔNG bao giờ lên git (repo công khai, có trong
.gitignore). Mỗi sản phẩm có thể có nhiều key; mỗi lần kích hoạt bằng tool được ghi lại (máy nào, lúc nào, được
không) để biết key MAK nào còn lượt.

Key không bao giờ được ghi ra log: tool đăng ký mọi key đã nạp với log.register_secret (log và khung log hiện ******),
script kích hoạt cũng thay key trong output của slmgr / ospp trước khi in.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from ..actions.loader import parse_action
from ..actions.model import Action
from . import log, shell

FILE_NAME = "license-keys.json"
FORMAT = 1
PREF = "license_file"  # prefs.json: file key IT đã chọn
WINDOWS_APP_ID = "55c92734-d682-4d71-983e-d6ec3f16059f"
OFFICE_APP_ID = "0ff1ce15-a989-479d-af46-f275c6370663"

PRODUCTS = (
    "Windows 10/11 Pro", "Windows 10/11 Enterprise", "Windows 10/11 Education",
    "Office 2016 Standard", "Office 2016 Professional Plus", "Office 2013 Standard", "Office 2013 Professional Plus",
    "Office 2010 Standard", "Office 2010 Professional Plus", "Office LTSC 2021 Standard", "Office 2019 Standard",
)
TYPES = ("MAK", "Retail", "OEM", "KMS")
ABOUT = ("File key bản quyền của FVPL IT Toolkit. Chỉ để trên USB / share của IT. Không đưa lên git, không gửi qua "
         "Zalo / email.")

_KEY = re.compile(r"^[A-Z0-9]{5}(-[A-Z0-9]{5}){4}$")


class LicenseError(RuntimeError):
    pass


@dataclass
class Usage:
    computer: str
    date: str
    ok: bool
    message: str = ""


@dataclass
class LicenseKey:
    product: str
    key: str
    type: str = "MAK"
    note: str = ""
    added: str = ""
    used: list[Usage] = field(default_factory=list)

    @property
    def id(self) -> str:
        return hashlib.sha1(self.key.encode("ascii")).hexdigest()[:10]

    @property
    def kind(self) -> str:
        """windows | office: quyết định kích hoạt bằng slmgr hay ospp."""
        return "office" if "office" in self.product.lower() else "windows"

    @property
    def masked(self) -> str:
        return "•••••-•••••-•••••-•••••-" + self.key[-5:]

    @property
    def activations(self) -> int:
        """Số máy đã kích hoạt được bằng key này (đếm mỗi máy một lần)."""
        return len({usage.computer.lower() for usage in self.used if usage.ok})

    @property
    def used_text(self) -> str:
        if not self.used:
            return "Chưa dùng"
        last = self.used[-1]
        result = f"{self.activations} máy" if self.activations else "Chưa kích hoạt được máy nào"
        return f"{result} · lần cuối {last.computer} {last.date}" + ("" if last.ok else " (lỗi)")


def normalize_key(text: str) -> str | None:
    """Key dạng XXXXX-XXXXX-XXXXX-XXXXX-XXXXX (chấp nhận chữ thường, dấu cách, thiếu gạch). Sai thì None."""
    raw = re.sub(r"[\s\-]", "", text or "").upper()
    if len(raw) != 25 or not raw.isalnum():
        return None
    key = "-".join(raw[index:index + 5] for index in range(0, 25, 5))
    return key if _KEY.match(key) else None


def keys_in_text(text: str) -> list[str]:
    """Mọi key trong một đoạn chữ dán vào (mỗi dòng một key, hoặc lẫn chữ khác), không trùng."""
    found = []
    for match in re.finditer(r"(?i)\b[A-Z0-9]{5}(?:[\s-]?[A-Z0-9]{5}){4}\b", text or ""):
        key = normalize_key(match.group(0))
        if key and key not in found:
            found.append(key)
    return found


# ---------------------------------------------------------------- file


def default_path(chosen: str, portable_root: Path | None, fallback_dir: Path) -> Path:
    """File IT đã chọn; không thì cạnh tool trên USB / SSD; tool chạy từ bản chép trong máy thì thư mục dữ liệu."""
    if chosen:
        return Path(chosen)
    if portable_root is not None:
        return portable_root / FILE_NAME
    return fallback_dir / FILE_NAME


def _usage(data: object) -> Usage | None:
    if not isinstance(data, dict):
        return None
    return Usage(str(data.get("computer") or ""), str(data.get("date") or ""), bool(data.get("ok")),
                 str(data.get("message") or ""))


def load(path: Path) -> list[LicenseKey]:
    """Đọc file key (chưa có file thì danh sách rỗng). Key đọc được đều đăng ký để che trong log."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    except OSError as exc:
        raise LicenseError(f"Không đọc được {path}: {exc}") from exc
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise LicenseError(f"{path} sai định dạng JSON: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("keys"), list):
        raise LicenseError(f"{path} không phải file key của tool (thiếu phần \"keys\")")
    keys: list[LicenseKey] = []
    for item in data["keys"]:
        if not isinstance(item, dict):
            continue
        key = normalize_key(str(item.get("key") or ""))
        if key is None or any(existing.key == key for existing in keys):
            continue
        log.register_secret(key)
        keys.append(LicenseKey(str(item.get("product") or "Chưa đặt tên"), key, str(item.get("type") or "MAK"),
                               str(item.get("note") or ""), str(item.get("added") or ""),
                               [usage for usage in map(_usage, item.get("used") or []) if usage is not None]))
    return keys


def save(path: Path, keys: list[LicenseKey]) -> None:
    """Ghi cả file (ghi ra file tạm rồi thay, để mất điện giữa chừng không hỏng file cũ)."""
    data = {"about": ABOUT, "format": FORMAT, "updated": datetime.now().strftime("%d/%m/%Y %H:%M"),
            "keys": [{"product": key.product, "key": key.key, "type": key.type, "note": key.note, "added": key.added,
                      "used": [usage.__dict__ for usage in key.used]} for key in keys]}
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(path.name + ".tmp")
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp, path)
    except OSError as exc:
        raise LicenseError(f"Không ghi được {path}: {exc}") from exc
    for key in keys:
        log.register_secret(key.key)


def add_keys(keys: list[LicenseKey], product: str, new_keys: list[str], key_type: str, note: str,
             now: datetime | None = None) -> tuple[list[LicenseKey], list[str]]:
    """Thêm key cho một sản phẩm. Trả (danh sách mới, các key đã có sẵn nên bỏ qua)."""
    existing = {key.key for key in keys}
    skipped = [key for key in new_keys if key in existing]
    added = (now or datetime.now()).strftime("%d/%m/%Y")
    result = list(keys) + [LicenseKey(product.strip(), key, key_type, note.strip(), added)
                           for key in dict.fromkeys(new_keys) if key not in existing]
    return result, skipped


def record_usage(keys: list[LicenseKey], key_id: str, computer: str, ok: bool, message: str = "",
                 now: datetime | None = None) -> bool:
    for key in keys:
        if key.id == key_id:
            key.used.append(Usage(computer, (now or datetime.now()).strftime("%d/%m/%Y %H:%M"), ok, message))
            return True
    return False


def suggested(keys: list[LicenseKey], os_name: str) -> list[LicenseKey]:
    """Key Windows hợp với bản Windows của máy (Pro / Enterprise / Education), ít máy dùng nhất trước."""
    lowered = os_name.lower()
    edition = next((word for word in ("enterprise", "education", "pro") if word in lowered), "")
    matches = [key for key in keys if key.kind == "windows" and edition and edition in key.product.lower()]
    return sorted(matches, key=lambda key: key.activations)


# ---------------------------------------------------------------- kích hoạt

# Mã lỗi hay gặp của slmgr / ospp, giải thích tiếng Việt (in trong log; khung kết quả hiện câu theo mã thoát).
_ERRORS = """\
$Explain = @{
    'C004F050' = 'key không dùng được cho bản này (ví dụ key Pro cho máy Home, key Office cho Windows)'
    'C004C008' = 'key đã hết lượt kích hoạt (MAK đã dùng đủ số máy)'
    'C004C020' = 'key MAK đã vượt giới hạn kích hoạt'
    'C004C003' = 'Microsoft đã chặn key này'
    'C004C060' = 'key không còn hiệu lực'
    'C004C4CE' = 'key không còn hiệu lực'
    'C004E016' = 'key không khớp với sản phẩm'
    'C004F069' = 'key không khớp với bản Windows đang cài'
    'C004F210' = 'key không khớp với bản Windows đang cài'
    'C004F074' = 'không liên lạc được máy chủ KMS'
    '8007232B' = 'không tìm thấy máy chủ KMS (key KMS cần máy chủ KMS của công ty)'
    '8007007B' = 'key sai, hoặc là key KMS mà công ty không có máy chủ KMS'
    '80072EE7' = 'không vào được Internet'
    '80072EFD' = 'không vào được Internet'
    '80072F8F' = 'lỗi kết nối bảo mật: kiểm tra ngày giờ của máy'
    'C004F012' = 'thiếu thông tin bản quyền: chạy sfc /scannow rồi thử lại'
}
function Get-ErrorText([string]$Text) {
    $found = [regex]::Match($Text, '0x([0-9A-Fa-f]{8})')
    if (-not $found.Success) { return '' }
    $code = $found.Groups[1].Value.ToUpper()
    if ($Explain.ContainsKey($code)) { return ('0x{0}: {1}' -f $code, $Explain[$code]) }
    return ('mã lỗi 0x{0}' -f $code)
}
function Invoke-Script([string]$File, [string[]]$Arguments) {
    $output = (& cscript.exe //nologo $File @Arguments 2>&1 | Out-String)
    return $output.Replace($ProductKey, '*****')
}
"""

_WINDOWS = """\
$slmgr = Join-Path $env:SystemRoot 'System32\\slmgr.vbs'
Write-Line 'Nhập key vào Windows (slmgr /ipk)…'
$output = Invoke-Script $slmgr @('/ipk', $ProductKey)
$problem = Get-ErrorText $output
if ($problem) { Write-Bad ('Không nhập được key: ' + $problem); exit 4 }
Write-Line 'Kích hoạt qua Internet (slmgr /ato)…'
$output = Invoke-Script $slmgr @('/ato')
$problem = Get-ErrorText $output
$suffix = $ProductKey.Substring($ProductKey.Length - 5)
$product = Get-CimInstance SoftwareLicensingProduct -Filter "ApplicationID='__APP__' AND PartialProductKey IS NOT NULL" |
    Where-Object { $_.PartialProductKey -eq $suffix } | Select-Object -First 1
if ($product -and [int]$product.LicenseStatus -eq 1) { Write-Ok ('Windows đã kích hoạt: {0}' -f $product.Name); exit 0 }
if (-not $problem) { $problem = 'Windows chưa báo đã kích hoạt' }
Write-Bad ('Chưa kích hoạt được: ' + $problem)
exit 5
"""

_OFFICE = """\
$ospp = $null
foreach ($root in @($env:ProgramFiles, ${env:ProgramFiles(x86)})) {
    if (-not $root -or $ospp) { continue }
    foreach ($version in __VERSIONS__) {
        $path = Join-Path $root ('Microsoft Office\\{0}\\OSPP.VBS' -f $version)
        if (Test-Path -LiteralPath $path) { $ospp = $path; break }
    }
}
if (-not $ospp) { Write-Bad 'Không thấy OSPP.VBS: máy chưa cài Office bản volume (2010 / 2013 / 2016 / 2019 / 2021).'; exit 3 }
Write-Line ('Nhập key vào Office ({0} /inpkey)…' -f $ospp)
$output = Invoke-Script $ospp @("/inpkey:$ProductKey")
if ($output -match 'ERROR CODE') { Write-Bad ('Không nhập được key: ' + (Get-ErrorText $output)); exit 4 }
Write-Line 'Kích hoạt qua Internet (/act)…'
$output = Invoke-Script $ospp @('/act')
$suffix = $ProductKey.Substring($ProductKey.Length - 5)
$products = @()
try { $products += @(Get-CimInstance SoftwareLicensingProduct -ErrorAction Stop -Filter "ApplicationID='__APP__' AND PartialProductKey IS NOT NULL") } catch { }
try { $products += @(Get-CimInstance OfficeSoftwareProtectionProduct -ErrorAction Stop -Filter "ApplicationID='59a52881-a989-479d-af46-f275c6370663' AND PartialProductKey IS NOT NULL") } catch { }
$product = $products | Where-Object { $_.PartialProductKey -eq $suffix } | Select-Object -First 1
if ($product -and [int]$product.LicenseStatus -eq 1) { Write-Ok ('Office đã kích hoạt: {0}' -f $product.Name); exit 0 }
$problem = Get-ErrorText $output
if (-not $problem) { $problem = 'Office chưa báo đã kích hoạt' }
Write-Bad ('Chưa kích hoạt được: ' + $problem)
exit 5
"""

_STATUS = """\
$labels = @{ 0 = 'CHƯA kích hoạt'; 1 = 'đã kích hoạt'; 2 = 'đang dùng thử, CHƯA kích hoạt'; 3 = 'hết hạn, đang ân hạn'; 4 = 'không chính hãng'; 5 = 'cần kích hoạt lại'; 6 = 'ân hạn mở rộng' }
$products = @()
try { $products += @(Get-CimInstance SoftwareLicensingProduct -ErrorAction Stop -Filter "PartialProductKey IS NOT NULL AND (ApplicationID='__WINDOWS__' OR ApplicationID='__OFFICE__')") } catch { }
try { $products += @(Get-CimInstance OfficeSoftwareProtectionProduct -ErrorAction Stop -Filter "PartialProductKey IS NOT NULL") } catch { }
if (-not $products) { Write-Bad 'Không đọc được trạng thái kích hoạt.' }
foreach ($product in $products) {
    $text = '{0} (key …{1}, {2}): {3}' -f $product.Name, $product.PartialProductKey, $product.ProductKeyChannel, $labels[[int]$product.LicenseStatus]
    if ([int]$product.LicenseStatus -eq 1) { Write-Ok $text } else { Write-Bad $text }
}
Exit-Checks
"""

_MESSAGES = {
    3: "Máy chưa cài Office bản volume",
    4: "Không nhập được key (xem lý do ở dòng ✖ trong log)",
    5: "Đã nhập key nhưng chưa kích hoạt được (xem lý do ở dòng ✖ trong log: cần Internet, key có thể hết lượt)",
}


def office_versions(product: str) -> list[str]:
    """Thư mục Office có OSPP.VBS, đúng phiên bản của key trước (2016 / 2019 / 2021 cùng là Office16)."""
    lowered = product.lower()
    if "2013" in lowered:
        first = "Office15"
    elif "2010" in lowered:
        first = "Office14"
    else:
        first = "Office16"
    return [first] + [version for version in ("Office16", "Office15", "Office14") if version != first]


def activation_action(key: LicenseKey) -> Action:
    """Mục nhập key và kích hoạt máy này. Dòng đầu script là chú thích (log chỉ in dòng đầu), key nằm ở biến."""
    if key.kind == "office":
        versions = ", ".join(f"'{version}'" for version in office_versions(key.product))
        body = _OFFICE.replace("__VERSIONS__", versions).replace("__APP__", OFFICE_APP_ID)
    else:
        body = _WINDOWS.replace("__APP__", WINDOWS_APP_ID)
    script = (f"# Kích hoạt {key.product} bằng key …{key.key[-5:]} trong file key\n"
              + shell.ps_variable_lines({"ProductKey": key.key}) + _ERRORS + body)
    return parse_action({
        "id": f"lic.activate_{key.id}", "name": f"Kích hoạt {key.product} (key …{key.key[-5:]})",
        "category": "Key bản quyền", "page": "utilities", "risk": "caution", "undo": "none",
        "description": "Nhập key vào máy rồi kích hoạt qua Internet. Key trong file key bản quyền của IT.",
        "apply": [{"powershell": script, "timeout": 600, "messages": _MESSAGES}],
    })


def status_action() -> Action:
    script = _STATUS.replace("__WINDOWS__", WINDOWS_APP_ID).replace("__OFFICE__", OFFICE_APP_ID)
    return parse_action({
        "id": "lic.status", "name": "Xem trạng thái kích hoạt Windows và Office", "category": "Key bản quyền",
        "page": "utilities", "admin": False,
        "description": "Chỉ đọc: Windows và Office trên máy này đã kích hoạt chưa, key nào (5 ký tự cuối).",
        "apply": [{"powershell": script, "timeout": 120,
                   "messages": {2: "Có sản phẩm chưa kích hoạt (xem các dòng ✖)"}}],
    })


def scripts() -> list[tuple[str, str]]:
    """Script để test cú pháp PowerShell."""
    sample = LicenseKey("Office 2016 Standard", "AAAAA-BBBBB-CCCCC-DDDDD-EEEEE")
    windows = LicenseKey("Windows 10/11 Pro", "AAAAA-BBBBB-CCCCC-DDDDD-FFFFF")
    return [("key Office", activation_action(sample).apply[0].script),
            ("key Windows", activation_action(windows).apply[0].script),
            ("trạng thái kích hoạt", status_action().apply[0].script)]
