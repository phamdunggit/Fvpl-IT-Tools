"""Kiểm kê: lưu thông tin từng máy lên ổ mang theo và dựng file Excel tổng hợp (PLAN.md mục 11, câu 12).

Mỗi máy một file JSON trong thư mục `Inventory\\` cạnh tool trên USB / SSD (không gửi lên share). Máy đổi tên
(cùng serial) thì bản cũ được thay. Sau mỗi lần lưu, tool dựng lại `KiemKe.xlsx` từ mọi file JSON: một dòng một
máy, có lọc và cố định dòng tiêu đề. Ghi .xlsx thẳng (vài file XML nén zip), không cần Excel hay thư viện ngoài;
không dùng CSV vì Excel tiếng Việt mở CSV hay sai dấu phân cách và lỗi chữ có dấu.
"""

from __future__ import annotations

import json
import logging
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape

from . import inventory, paths

log = logging.getLogger(__name__)

FOLDER = "Inventory"
STATE_FOLDER = "inventory"
WORKBOOK = "KiemKe.xlsx"
SHEET = "Kiểm kê"
# Serial mặc định của bo mạch chưa được hãng ghi (máy tự ráp, máy ảo): không dùng để nhận ra máy.
_FAKE_SERIALS = {"", "none", "0", "default string", "to be filled by o.e.m.", "system serial number", "not specified"}


@dataclass(frozen=True)
class Column:
    key: str
    title: str
    width: int


COLUMNS = (
    Column("time", "Ngày kiểm kê", 17),
    Column("computer", "Tên máy", 16),
    Column("domain", "Domain / Workgroup", 18),
    Column("department", "Phòng ban", 12),
    Column("user", "Người dùng", 24),
    Column("manufacturer", "Hãng", 12),
    Column("model", "Model", 28),
    Column("serial", "Serial", 16),
    Column("kind", "Loại máy", 10),
    Column("cpu", "CPU", 36),
    Column("ram_gb", "RAM (GB)", 9),
    Column("disks", "Ổ đĩa", 30),
    Column("system_free_gb", "Ổ hệ thống còn trống (GB)", 12),
    Column("windows", "Windows", 34),
    Column("windows_license", "Kích hoạt Windows", 18),
    Column("office", "Office", 34),
    Column("ip", "IP", 16),
    Column("mac", "MAC", 18),
    Column("antivirus", "Diệt virus", 30),
    Column("bitlocker", "BitLocker", 18),
    Column("tpm", "TPM", 10),
    Column("last_update", "Cập nhật Windows gần nhất", 14),
    Column("bios", "BIOS", 24),
    Column("windows_installed", "Ngày cài Windows", 12),
    Column("tool_version", "Phiên bản tool", 10),
)


@dataclass
class SaveResult:
    folder: Path
    record_file: Path
    workbook: Path | None      # None nếu không ghi được (đang mở trong Excel...)
    count: int                 # số máy trong file tổng hợp
    error: str = ""


# ---------------------------------------------------------------- một máy


def _join(items, sep: str = ", ") -> str:
    return sep.join(str(item) for item in items or [] if item)


def _gb(size) -> float | str:
    return round(size / 1024**3, 1) if isinstance(size, (int, float)) and size > 0 else ""


def _office(data: dict) -> str:
    office = data.get("office")
    if office:
        return _join([_join(str(office.get("products", "")).split(",")), office.get("version")], " ")
    licenses = [item for item in data.get("licenses") or [] if item.get("product") == "office"]
    parts = []
    for item in licenses:
        label, _state = inventory.LICENSE_STATUS.get(item.get("status"), (f"trạng thái {item.get('status')}", ""))
        parts.append(f"{item.get('name', '')} ({label.lower()})")
    return "; ".join(parts)


def _antivirus(security: dict) -> str:
    parts = []
    defender = security.get("defender")
    if defender and defender.get("enabled") and "passive" not in str(defender.get("mode", "")).lower():
        parts.append("Microsoft Defender (bật)")
    for item in security.get("antivirus") or []:
        if "defender" in str(item.get("name", "")).lower():
            continue
        enabled, up_to_date = inventory._antivirus_state(int(item.get("state") or 0))
        parts.append(f"{item.get('name')} ({'bật' if enabled else 'TẮT'}{'' if up_to_date else ', chưa cập nhật'})")
    return "; ".join(parts)


def _bitlocker(security: dict) -> str:
    bitlocker = security.get("bitlocker") or {}
    if "conversion" in bitlocker:
        text = inventory.BITLOCKER_CONVERSION.get(bitlocker["conversion"], f"trạng thái {bitlocker['conversion']}")
        if bitlocker["conversion"] == 1 and bitlocker.get("protection") != 1:
            text += ", tạm dừng"
        return text
    if "shell_value" in bitlocker:
        return inventory.BITLOCKER_SHELL.get(bitlocker["shell_value"], ("không rõ", ""))[0]
    return ""


def record(data: dict, basics: inventory.Basics, tool_version: str, department: str = "",
           primary_user: str = "") -> dict:
    """Một dòng kiểm kê từ dữ liệu của trang Tổng quan (`data`: 4 phần đã đọc, phần nào lỗi thì để trống)."""
    hardware = data.get("hardware") or {}
    os_info = data.get("os") or {}
    security = data.get("security") or {}
    adapters = data.get("network") or []
    maker = str(hardware.get("manufacturer") or "").strip()
    model = str(hardware.get("model") or "").strip()
    if "lenovo" in maker.lower() and hardware.get("model_version"):
        model = f"{hardware['model_version']} ({model})"
    modules = [item for item in hardware.get("ram_modules") or [] if item.get("size")]
    ram = sum(item["size"] for item in modules) or hardware.get("ram_total")
    disks = [_join([inventory.DISK_MEDIA.get(disk.get("media")), inventory.DISK_BUS.get(disk.get("bus")),
                    inventory.size_label(disk.get("size"))], " ") for disk in data.get("disks") or []]
    system_drive = str(data.get("system_drive") or "C:").upper()
    system_volume = next((volume for volume in data.get("volumes") or []
                          if str(volume.get("drive", "")).upper() == system_drive), {})
    windows_licenses = [item for item in data.get("licenses") or [] if item.get("product") == "windows"]
    windows_license = ""
    if windows_licenses:
        best = max(windows_licenses, key=lambda item: item.get("status") == 1)
        windows_license = inventory.LICENSE_STATUS.get(best.get("status"), (f"trạng thái {best.get('status')}", ""))[0]
    tpm = security.get("tpm")
    if os_info:
        windows = f"{os_info.get('caption', '')} {os_info.get('display_version', '')} " \
                  f"(build {os_info.get('build')}.{os_info.get('ubr')})"
    else:
        windows = basics.os_label
    return {
        "time": f"{basics.now:%d/%m/%Y %H:%M}",
        "computer": basics.computer_name,
        "domain": basics.domain_label,
        "department": department,
        "user": primary_user or str(os_info.get("logged_on_user") or basics.target_user),
        "manufacturer": maker,
        "model": model,
        "serial": str(hardware.get("serial") or "").strip(),
        "kind": ("Laptop" if hardware.get("pc_type") == 2 or hardware.get("has_battery") else "Máy bàn")
        if hardware else "",
        "cpu": _join(cpu.get("name") for cpu in hardware.get("cpu") or []),
        "ram_gb": _gb(ram),
        "disks": "; ".join(disks),
        "system_free_gb": _gb(system_volume.get("free")),
        "windows": " ".join(windows.split()),
        "windows_license": windows_license,
        "office": _office(data),
        "ip": _join(ip for adapter in adapters for ip in adapter.get("ipv4") or []),
        "mac": _join(adapter.get("mac") for adapter in adapters),
        "antivirus": _antivirus(security),
        "bitlocker": _bitlocker(security),
        "tpm": (f"TPM {tpm.get('version')}" if tpm.get("present") else "Không có") if tpm else "",
        "last_update": inventory._date((security.get("last_update") or {}).get("date")),
        "bios": _join([hardware.get("bios_version"), inventory._date(hardware.get("bios_date"))]),
        "windows_installed": inventory._date(os_info.get("install_date")),
        "tool_version": tool_version,
    }


def real_serial(serial: str) -> bool:
    return len(serial.strip()) >= 4 and serial.strip().lower() not in _FAKE_SERIALS


# ---------------------------------------------------------------- lưu


def _writable(folder: Path) -> bool:
    try:
        folder.mkdir(parents=True, exist_ok=True)
        probe = folder / ".write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def inventory_dir(origin: str = "") -> Path:
    """`Inventory\\` cạnh tool trên ổ mang theo; tool chạy từ bản chép trong máy thì cạnh tool lúc bắt đầu wizard
    (`origin`) nếu ổ đó còn cắm; không được thì thư mục dữ liệu của tool trên máy."""
    candidates = []
    root = paths.portable_root()
    if root is not None:
        candidates.append(root / FOLDER)
    if origin and Path(origin).is_dir():
        candidates.append(Path(origin) / FOLDER)
    for candidate in candidates:
        if _writable(candidate):
            return candidate
    folder = paths.state_dir() / STATE_FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _file_name(computer: str) -> str:
    return (re.sub(r"[^A-Za-z0-9-]", "_", computer) or "may") + ".json"


def load_records(folder: Path) -> list[dict]:
    records = []
    for file in sorted(folder.glob("*.json")):
        try:
            data = json.loads(file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            log.warning("Bỏ qua file kiểm kê đọc không được: %s", file)
            continue
        if isinstance(data, dict) and data.get("computer"):
            records.append(data)
    return sorted(records, key=lambda item: str(item.get("computer", "")).lower())


def save_record(folder: Path, item: dict) -> Path:
    """Ghi bản ghi của một máy. Máy đổi tên (cùng serial thật) thì xoá bản ghi dưới tên cũ."""
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / _file_name(item["computer"])
    serial = str(item.get("serial") or "")
    if real_serial(serial):
        for other in folder.glob("*.json"):
            if other.name.lower() == target.name.lower():
                continue
            try:
                old = json.loads(other.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(old, dict) and str(old.get("serial") or "").strip().lower() == serial.strip().lower():
                other.unlink()
    target.write_text(json.dumps(item, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def save(item: dict, origin: str = "") -> SaveResult:
    folder = inventory_dir(origin)
    record_file = save_record(folder, item)
    records = load_records(folder)
    workbook = folder / WORKBOOK
    try:
        write_xlsx(workbook, records)
    except OSError as exc:
        log.warning("Không ghi được %s: %s", workbook, exc)
        return SaveResult(folder, record_file, None, len(records),
                          f"không ghi được {WORKBOOK} (đang mở trong Excel?), đóng file rồi lưu lại")
    return SaveResult(folder, record_file, workbook, len(records))


# ---------------------------------------------------------------- file .xlsx

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _column_name(index: int) -> str:
    name = ""
    index += 1
    while index:
        index, rest = divmod(index - 1, 26)
        name = chr(65 + rest) + name
    return name


def _cell(ref: str, value, style: int = 0) -> str:
    style_attr = f' s="{style}"' if style else ""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f'<c r="{ref}"{style_attr}><v>{value}</v></c>'
    text = escape(_CONTROL.sub("", str(value if value is not None else "")))
    # Chữ để dạng inline string: không bao giờ bị Excel hiểu là công thức (an toàn với giá trị bắt đầu bằng =).
    return f'<c r="{ref}" t="inlineStr"{style_attr}><is><t xml:space="preserve">{text}</t></is></c>'


_CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/xl/workbook.xml" '
    'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
    '<Override PartName="/xl/worksheets/sheet1.xml" '
    'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
    '<Override PartName="/xl/styles.xml" '
    'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
    '</Types>'
)
_ROOT_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" '
    'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
    'Target="xl/workbook.xml"/></Relationships>'
)
_WORKBOOK_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
    'Target="worksheets/sheet1.xml"/>'
    '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
    'Target="styles.xml"/></Relationships>'
)
_STYLES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
    '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font>'
    '<font><b/><sz val="11"/><name val="Calibri"/></font></fonts>'
    '<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill>'
    '<fill><patternFill patternType="solid"><fgColor rgb="FFDDE3EA"/><bgColor indexed="64"/></patternFill></fill>'
    '</fills>'
    '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
    '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
    '<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
    '<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"/></cellXfs>'
    '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
    '</styleSheet>'
)


def workbook_parts(records: list[dict]) -> dict[str, str]:
    """Các file XML của .xlsx (tách ra để test đọc lại được)."""
    last = _column_name(len(COLUMNS) - 1)
    last_row = max(len(records) + 1, 2)
    rows = ['<row r="1">' + "".join(_cell(f"{_column_name(index)}1", column.title, 1)
                                    for index, column in enumerate(COLUMNS)) + "</row>"]
    for number, item in enumerate(records, start=2):
        cells = "".join(_cell(f"{_column_name(index)}{number}", item.get(column.key, ""))
                        for index, column in enumerate(COLUMNS))
        rows.append(f'<row r="{number}">{cells}</row>')
    cols = "".join(f'<col min="{index}" max="{index}" width="{column.width}" customWidth="1"/>'
                   for index, column in enumerate(COLUMNS, start=1))
    sheet = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheetViews><sheetView workbookViewId="0">'
        '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
        f'<cols>{cols}</cols><sheetData>{"".join(rows)}</sheetData>'
        f'<autoFilter ref="A1:{last}{last_row}"/></worksheet>'
    )
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<sheets><sheet name="{escape(SHEET)}" sheetId="1" r:id="rId1"/></sheets>'
        '<definedNames><definedName name="_xlnm._FilterDatabase" localSheetId="0" hidden="1">'
        f"{escape(repr_sheet(SHEET))}!$A$1:${last}${last_row}</definedName></definedNames></workbook>"
    )
    return {
        "[Content_Types].xml": _CONTENT_TYPES,
        "_rels/.rels": _ROOT_RELS,
        "xl/workbook.xml": workbook,
        "xl/_rels/workbook.xml.rels": _WORKBOOK_RELS,
        "xl/styles.xml": _STYLES,
        "xl/worksheets/sheet1.xml": sheet,
    }


def repr_sheet(name: str) -> str:
    """Tên sheet trong công thức: đặt trong nháy đơn, nháy đơn bên trong nhân đôi."""
    return "'" + name.replace("'", "''") + "'"


def write_xlsx(file: Path, records: list[dict]) -> None:
    """Ghi ra file tạm rồi thay file cũ, để file đang mở trong Excel không bị ghi dở."""
    temp = file.with_name(file.stem + ".tmp")
    with zipfile.ZipFile(temp, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in workbook_parts(records).items():
            archive.writestr(name, content.encode("utf-8"))
    try:
        temp.replace(file)
    except OSError:
        temp.unlink(missing_ok=True)
        raise
