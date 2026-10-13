"""Thông tin máy cho trang Tổng quan: thu thập bằng PowerShell, dựng thành các mục để hiển thị và xuất.

Chia 4 phần chạy song song (mỗi phần một tiến trình PowerShell), phần nào xong thì hiện phần đó.
Script nằm ở data/scripts/inventory/. Chỉ đọc, không đổi gì trên máy.
"""

from __future__ import annotations

import html
import json
import threading
from dataclasses import dataclass, field
from datetime import datetime

from . import paths, pslib, shell

PARTS = ("system", "storage", "network", "security")
SCRIPTS_DIR = paths.DATA_DIR / "scripts" / "inventory"
PART_TIMEOUT = 120

LICENSE_STATUS = {
    0: ("Chưa kích hoạt", "bad"),
    1: ("Đã kích hoạt", "ok"),
    2: ("Đang dùng thử, chưa kích hoạt", "warn"),
    3: ("Hết hạn kích hoạt, đang trong thời gian ân hạn", "warn"),
    4: ("Không chính hãng", "bad"),
    5: ("Cần kích hoạt lại", "bad"),
    6: ("Đang trong thời gian ân hạn mở rộng", "warn"),
}
DISK_MEDIA = {3: "HDD", 4: "SSD", 5: "SCM"}
DISK_BUS = {1: "SCSI", 3: "ATA", 7: "USB", 8: "RAID", 10: "SAS", 11: "SATA", 12: "SD", 13: "MMC", 17: "NVMe"}
DISK_HEALTH = {0: ("Tốt", "ok"), 1: ("Cảnh báo", "warn"), 2: ("Hỏng", "bad")}
BITLOCKER_SHELL = {
    1: ("Đang bật", "ok"), 2: ("Tắt", ""), 3: ("Đang mã hoá", "warn"), 4: ("Đang giải mã", "warn"),
    5: ("Tạm dừng bảo vệ", "warn"), 6: ("Đang bật", "ok"),
}
BITLOCKER_CONVERSION = {
    0: "Chưa mã hoá", 1: "Đã mã hoá", 2: "Đang mã hoá", 3: "Đang giải mã", 4: "Tạm dừng mã hoá", 5: "Tạm dừng giải mã",
}
SIGNATURE_MAX_DAYS = 7
UPDATE_MAX_DAYS = 45


class InventoryError(RuntimeError):
    pass


# ---------------------------------------------------------------- thu thập


def part_script(part: str) -> str:
    common = (SCRIPTS_DIR / "common.ps1").read_text(encoding="utf-8")
    body = (SCRIPTS_DIR / f"{part}.ps1").read_text(encoding="utf-8")
    return common + "\n" + pslib.with_helpers(body) + "\n$data | ConvertTo-Json -Depth 6 -Compress\n"


def _clean(value):
    """PowerShell 5.1 đôi khi xuất {} thay cho null; đổi lại cho dễ xử lý."""
    if isinstance(value, dict):
        return {key: _clean(item) for key, item in value.items()} or None
    if isinstance(value, list):
        return [_clean(item) for item in value]
    return value


def collect_part(part: str, cancel: threading.Event | None = None) -> dict:
    result = shell.run_powershell(part_script(part), timeout=PART_TIMEOUT, cancel=cancel)
    if result.cancelled:
        raise InventoryError("Đã huỷ")
    if result.timed_out:
        raise InventoryError(f"Quá {PART_TIMEOUT} giây chưa đọc xong")
    lines = [line for line in result.output.splitlines() if line.startswith("{")]
    if result.code != 0 or not lines:
        detail = result.output.strip().splitlines()[-1] if result.output.strip() else f"mã lỗi {result.code}"
        raise InventoryError(detail)
    try:
        return _clean(json.loads(lines[-1])) or {}
    except ValueError as exc:
        raise InventoryError(f"Kết quả không đọc được: {exc}") from exc


# ---------------------------------------------------------------- dựng mục hiển thị


@dataclass(frozen=True)
class Row:
    label: str
    value: str
    state: str = ""  # "" | ok | warn | bad | muted
    loading: bool = False  # phần này chưa đọc xong; không đưa vào bản copy / xuất


@dataclass(frozen=True)
class Section:
    key: str
    title: str
    rows: tuple[Row, ...]


@dataclass(frozen=True)
class Basics:
    """Thông tin Python đọc sẵn được ngay, không phải chờ PowerShell."""
    computer_name: str
    domain_label: str
    joined_domain: bool
    os_label: str
    target_user: str
    is_admin: bool
    now: datetime = field(default_factory=datetime.now)


LOADING = Row("", "Đang đọc…", "muted", loading=True)
DISKS_LOADING = Row("Ổ đĩa", "Đang đọc…", "muted", loading=True)
# Mục nào lấy dữ liệu từ phần thu thập nào, để báo lỗi đúng chỗ khi một phần đọc lỗi.
_SECTION_PART = {"system": "system", "hardware": "system", "network": "network", "security": "security"}


def _parse_time(value) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _date(value) -> str:
    moment = _parse_time(value)
    return moment.strftime("%d/%m/%Y") if moment else ""


def _days_since(value, now: datetime) -> int | None:
    moment = _parse_time(value)
    return (now - moment).days if moment else None


def _number(value: float, digits: int) -> str:
    return f"{value:.{digits}f}".replace(".", ",")


def size_label(size) -> str:
    if not isinstance(size, (int, float)) or size <= 0:
        return "?"
    gb = size / 1024**3
    if gb >= 1024:
        value, unit = gb / 1024, "TB"
    else:
        value, unit = gb, "GB"
    whole = value >= 100 or abs(value - round(value)) < 0.05
    return f"{_number(value, 0 if whole else 1)} {unit}"


def _speed_label(bits) -> str:
    if not isinstance(bits, (int, float)) or bits <= 0:
        return ""
    if bits >= 1_000_000_000:
        return f"{_number(bits / 1_000_000_000, 1).replace(',0', '')} Gbps"
    return f"{round(bits / 1_000_000)} Mbps"


def _duration(seconds: float) -> str:
    days, rest = divmod(int(seconds), 86400)
    hours, rest = divmod(rest, 3600)
    if days:
        return f"{days} ngày {hours} giờ"
    return f"{hours} giờ {rest // 60} phút"


def _join(items, sep: str = ", ") -> str:
    return sep.join(str(item) for item in items or [] if item)


def _system_section(data: dict, basics: Basics) -> Section:
    rows = [
        Row("Tên máy", basics.computer_name),
        Row("Domain / Workgroup", basics.domain_label, "" if basics.joined_domain else "warn"),
        Row("Người đang đăng nhập", basics.target_user),
    ]
    os_info = data.get("os")
    if not os_info:
        rows.append(Row("Windows", basics.os_label))
        return Section("system", "Hệ điều hành", tuple(rows + [LOADING]))
    version = _join([os_info.get("display_version"), f"build {os_info.get('build')}.{os_info.get('ubr')}"], " ")
    rows.append(Row("Windows", f"{os_info.get('caption', '')} {version}, {os_info.get('architecture', '')}".strip()))
    if os_info.get("install_date"):
        rows.append(Row("Ngày cài Windows", f"{_date(os_info['install_date'])} (hoặc ngày lên bản Windows mới nhất)"))
    boot = _parse_time(os_info.get("last_boot"))
    if boot:
        uptime = (basics.now - boot).total_seconds()
        state = "warn" if uptime > 14 * 86400 else ""
        note = ", nên khởi động lại" if state else ""
        rows.append(Row("Khởi động lúc", f"{boot:%d/%m/%Y %H:%M} (đã chạy {_duration(uptime)}{note})", state))

    licenses = data.get("licenses") or []
    windows = [item for item in licenses if item.get("product") == "windows"]
    if windows:
        best = max(windows, key=lambda item: item.get("status") == 1)
        label, state = LICENSE_STATUS.get(best.get("status"), (f"Trạng thái {best.get('status')}", "warn"))
        channel = f" ({best['channel']})" if best.get("channel") else ""
        rows.append(Row("Kích hoạt Windows", label + channel, state))
    elif "licenses" in data:
        rows.append(Row("Kích hoạt Windows", "Không đọc được", "warn"))

    office = data.get("office")
    office_licenses = [item for item in licenses if item.get("product") == "office"]
    if office:
        rows.append(Row("Office", f"{_join(str(office.get('products', '')).split(','))} {office.get('version', '')}, "
                                  f"bản {office.get('platform', '')} (Click-to-Run)"))
    for item in office_licenses:
        label, state = LICENSE_STATUS.get(item.get("status"), (f"Trạng thái {item.get('status')}", "warn"))
        rows.append(Row("Kích hoạt Office", f"{label}: {item.get('name', '')}", state))
    if office and not office_licenses:
        rows.append(Row("Kích hoạt Office", "Không dùng key; Microsoft 365 kích hoạt bằng tài khoản người dùng", "muted"))
    return Section("system", "Hệ điều hành", tuple(rows))


def _hardware_section(data: dict) -> Section:
    hardware = data.get("hardware")
    if not hardware:
        return Section("hardware", "Phần cứng", (LOADING,))
    maker = str(hardware.get("manufacturer") or "").strip()
    model = str(hardware.get("model") or "").strip()
    if "lenovo" in maker.lower() and hardware.get("model_version"):
        model = f"{hardware['model_version']} ({model})"
    laptop = hardware.get("pc_type") == 2 or hardware.get("has_battery")
    rows = [
        Row("Hãng / Model", f"{maker} {model}".strip()),
        Row("Loại máy", "Laptop" if laptop else "Máy bàn"),
        Row("Serial", str(hardware.get("serial") or "(không có)")),
        Row("BIOS", _join([hardware.get("bios_version"), _date(hardware.get("bios_date"))], ", ")),
    ]
    for cpu in hardware.get("cpu") or []:
        rows.append(Row("CPU", f"{cpu.get('name', '')} ({cpu.get('cores')} nhân, {cpu.get('threads')} luồng)"))

    modules = [item for item in hardware.get("ram_modules") or [] if item.get("size")]
    total = sum(item["size"] for item in modules) or hardware.get("ram_total")
    ram = size_label(total)
    if modules:
        sizes = sorted({size_label(item["size"]) for item in modules})
        speeds = sorted({item.get("speed") for item in modules if item.get("speed")})
        ram += f" ({len(modules)} thanh {'/'.join(sizes)}" + (f", {speeds[0]} MHz" if speeds else "") + ")"
        slots = hardware.get("ram_slots")
        if isinstance(slots, int) and slots >= len(modules):
            ram += f", dùng {len(modules)}/{slots} khe"
    rows.append(Row("RAM", ram, "warn" if isinstance(total, int) and total < 7.5 * 1024**3 else ""))

    disks = data.get("disks")
    if disks is None:
        rows.append(DISKS_LOADING)
    for number, disk in enumerate(disks or [], start=1):
        kind = _join([DISK_MEDIA.get(disk.get("media")), DISK_BUS.get(disk.get("bus"))], " ")
        health, state = DISK_HEALTH.get(disk.get("health"), ("Không rõ sức khoẻ", "muted"))
        rows.append(Row(f"Ổ đĩa {number}", _join([disk.get("name"), kind, size_label(disk.get("size")), health], " · "),
                        "bad" if state == "bad" else ("warn" if state == "warn" else "")))
    system_drive = str(data.get("system_drive") or "C:").upper()
    for volume in data.get("volumes") or []:
        size, free = volume.get("size") or 0, volume.get("free") or 0
        percent = round(free * 100 / size) if size else 0
        low = size and (percent < 10 or (str(volume.get("drive")).upper() == system_drive and free < 15 * 1024**3))
        drive = str(volume.get("drive") or "").rstrip(":")
        label = f"Phân vùng {drive}" + (f" ({volume['label']})" if volume.get("label") else "")
        rows.append(Row(label, f"còn trống {size_label(free)} / {size_label(size)} ({percent}%)", "warn" if low else ""))

    if hardware.get("gpu"):
        rows.append(Row("Card đồ hoạ", _join(hardware["gpu"], "; ")))
    if hardware.get("monitors"):
        rows.append(Row("Màn hình", _join(hardware["monitors"], "; ")))
    return Section("hardware", "Phần cứng", tuple(rows))


def _network_section(data: dict, basics: Basics) -> Section:
    adapters = data.get("network")
    if adapters is None:
        return Section("network", "Mạng", (LOADING,))
    rows = []
    if not adapters:
        rows.append(Row("Card mạng", "Không có card mạng nào đang kết nối", "bad"))
    for adapter in adapters:
        kind = "Wi-Fi" if adapter.get("wireless") else ("LAN" if adapter.get("speed") else "")
        label = adapter.get("name") or adapter.get("description") or "Card mạng"
        if kind and kind.lower() not in label.lower():
            label += f" ({kind})"
        parts = [
            f"IP {_join(adapter.get('ipv4'))}" + (" (DHCP)" if adapter.get("dhcp") else " (IP tĩnh)"),
            f"gateway {_join(adapter.get('gateway')) or 'không có'}",
            f"DNS {_join(adapter.get('dns')) or 'không có'}",
            f"MAC {adapter.get('mac') or '?'}",
            _speed_label(adapter.get("speed")),
            adapter.get("description") or "",
        ]
        rows.append(Row(label, _join(parts, " · ")))
    for check in data.get("dns_checks") or []:
        if check.get("finds_dc"):
            rows.append(Row(f"DNS {check.get('server')}", "Tìm được DC của domain", "ok"))
        else:
            rows.append(Row(f"DNS {check.get('server')}", "Không tìm được DC: DNS này không trỏ về DC", "bad"))
    if basics.joined_domain and adapters and not data.get("dns_checks"):
        rows.append(Row("DNS", "Card mạng không có DNS server nào", "bad"))
    return Section("network", "Mạng", tuple(rows))


def _antivirus_state(state: int) -> tuple[bool, bool]:
    """(đang bật, cập nhật) từ productState của Windows Security Center."""
    enabled = ((state >> 8) & 0xFF) in (0x10, 0x11)
    up_to_date = (state & 0xFF) == 0x00
    return enabled, up_to_date


def _security_section(data: dict, basics: Basics) -> Section:
    security = data.get("security")
    if not security:
        return Section("security", "Bảo mật", (LOADING,))
    rows = []
    others = [item for item in security.get("antivirus") or [] if "defender" not in str(item.get("name", "")).lower()]
    defender = security.get("defender")
    if defender is None:
        rows.append(Row("Microsoft Defender", "Không đọc được", "muted"))
    elif not defender.get("enabled") or "passive" in str(defender.get("mode", "")).lower() \
            or "not running" in str(defender.get("mode", "")).lower():
        if others:
            rows.append(Row("Microsoft Defender", "Không chạy, máy dùng phần mềm diệt virus khác", "muted"))
        else:
            rows.append(Row("Microsoft Defender", "Đang tắt và không có phần mềm diệt virus khác", "bad"))
    else:
        days = _days_since(defender.get("signature_date"), basics.now)
        realtime = "bảo vệ thời gian thực bật" if defender.get("realtime") else "bảo vệ thời gian thực TẮT"
        signature = f"chữ ký cập nhật {_date(defender.get('signature_date'))}" + (f" ({days} ngày trước)" if days else "")
        state = "ok"
        if not defender.get("realtime"):
            state = "bad"
        elif days is not None and days > SIGNATURE_MAX_DAYS:
            state = "warn"
        rows.append(Row("Microsoft Defender", f"Đang bật, {realtime}, {signature}", state))
    for item in others:
        enabled, up_to_date = _antivirus_state(int(item.get("state") or 0))
        text = ("đang bật" if enabled else "đang tắt") + (", đã cập nhật" if up_to_date else ", chưa cập nhật")
        rows.append(Row("Diệt virus", f"{item.get('name')}: {text}", "ok" if enabled and up_to_date else "bad"))

    firewall = security.get("firewall") or []
    if firewall:
        off = [item["profile"] for item in firewall if not item.get("enabled")]
        text = " · ".join(f"{item['profile']} {'bật' if item.get('enabled') else 'TẮT'}" for item in firewall)
        rows.append(Row("Firewall", text, "bad" if off else "ok"))

    bitlocker = security.get("bitlocker")
    if bitlocker and "conversion" in bitlocker:
        text = BITLOCKER_CONVERSION.get(bitlocker["conversion"], f"Trạng thái {bitlocker['conversion']}")
        if bitlocker["conversion"] in (2, 3, 4, 5):
            text += f" ({bitlocker.get('percent')}%)"
        state = ""
        if bitlocker["conversion"] == 1:
            state = "ok" if bitlocker.get("protection") == 1 else "warn"
            text += ", đang bảo vệ" if bitlocker.get("protection") == 1 else ", đang TẠM DỪNG bảo vệ"
        rows.append(Row("BitLocker ổ hệ thống", text, state))
    elif bitlocker and "shell_value" in bitlocker:
        text, state = BITLOCKER_SHELL.get(bitlocker["shell_value"], ("Không rõ", "muted"))
        rows.append(Row("BitLocker ổ hệ thống", text, state))
    else:
        rows.append(Row("BitLocker ổ hệ thống", "Không đọc được", "muted"))

    tpm = security.get("tpm")
    if tpm is None:
        rows.append(Row("TPM", "Cần quyền admin để đọc" if not security.get("is_admin") else "Không đọc được", "muted"))
    elif not tpm.get("present"):
        rows.append(Row("TPM", "Không có hoặc đang tắt trong BIOS", "warn"))
    else:
        version = f"TPM {tpm.get('version')}" if tpm.get("version") else "Có TPM"
        rows.append(Row("TPM", version + ("" if tpm.get("ready") else ", chưa sẵn sàng"), "ok" if tpm.get("ready") else "warn"))

    firmware = str(security.get("firmware") or "")
    secure_boot = security.get("secure_boot")
    if secure_boot == 1:
        rows.append(Row("Secure Boot", f"Bật ({firmware or 'UEFI'})", "ok"))
    elif secure_boot == 0:
        rows.append(Row("Secure Boot", f"Tắt ({firmware or 'UEFI'})", "warn"))
    elif firmware.lower() == "legacy":
        rows.append(Row("Secure Boot", "Không hỗ trợ: máy khởi động kiểu Legacy BIOS", "warn"))
    else:
        rows.append(Row("Secure Boot", "Không đọc được", "muted"))

    update = security.get("last_update")
    if update:
        days = _days_since(update.get("date"), basics.now)
        state = "warn" if days is not None and days > UPDATE_MAX_DAYS else ""
        rows.append(Row("Cập nhật Windows gần nhất", f"{_date(update.get('date'))}: {update.get('title', '')}", state))
    else:
        rows.append(Row("Cập nhật Windows gần nhất", "Không đọc được", "muted"))
    return Section("security", "Bảo mật", tuple(rows))


def build_sections(data: dict, basics: Basics, failed: dict[str, str] | None = None) -> list[Section]:
    """`failed`: phần thu thập bị lỗi → thông báo lỗi, hiện thay cho dòng "Đang đọc…"."""
    failed = failed or {}
    sections = [
        _system_section(data, basics),
        _hardware_section(data),
        _network_section(data, basics),
        _security_section(data, basics),
    ]
    result = []
    for section in sections:
        rows = []
        for row in section.rows:
            part = "storage" if row is DISKS_LOADING else _SECTION_PART[section.key]
            if row.loading and part in failed:
                row = Row(row.label, f"Không đọc được: {failed[part]}", "bad")
            rows.append(row)
        result.append(Section(section.key, section.title, tuple(rows)))
    return result


def alerts(data: dict, basics: Basics) -> list[str]:
    """Cảnh báo ngắn cho thanh trên cùng."""
    checks = data.get("dns_checks") or []
    if basics.joined_domain and checks and not any(check.get("finds_dc") for check in checks):
        return ["DNS không trỏ về DC"]
    return []


# ---------------------------------------------------------------- xuất


def to_text(sections: list[Section], basics: Basics) -> str:
    lines = [f"Thông tin máy {basics.computer_name} (lúc {basics.now:%d/%m/%Y %H:%M})"]
    for section in sections:
        lines.append("")
        lines.append(f"== {section.title} ==")
        for row in section.rows:
            if not row.loading:
                lines.append(f"{row.label}: {row.value}" if row.label else row.value)
    return "\n".join(lines)


_STATE_COLORS = {"ok": "#15803d", "warn": "#b45309", "bad": "#b91c1c", "muted": "#64748b"}


def to_html(sections: list[Section], basics: Basics, tool_version: str) -> str:
    def esc(text: str) -> str:
        return html.escape(str(text))

    parts = [
        "<!doctype html><html lang='vi'><head><meta charset='utf-8'>",
        f"<title>Thông tin máy {esc(basics.computer_name)}</title>",
        "<style>body{font-family:'Segoe UI',Arial,sans-serif;margin:24px;color:#1f2933;background:#f4f6f8}"
        "h1{font-size:20px;margin:0 0 4px}p.meta{color:#52606d;margin:0 0 16px}"
        "section{background:#fff;border:1px solid #dde3ea;border-radius:8px;padding:12px 16px;margin-bottom:14px}"
        "h2{font-size:15px;margin:0 0 8px;color:#102a43}table{border-collapse:collapse;width:100%}"
        "td{padding:4px 8px;vertical-align:top;border-top:1px solid #eef1f4}"
        "td.k{color:#52606d;width:220px;white-space:nowrap}</style></head><body>",
        f"<h1>Thông tin máy {esc(basics.computer_name)}</h1>",
        f"<p class='meta'>Xuất lúc {basics.now:%d/%m/%Y %H:%M} bằng FVPL IT Toolkit {esc(tool_version)}</p>",
    ]
    for section in sections:
        parts.append(f"<section><h2>{esc(section.title)}</h2><table>")
        for row in section.rows:
            if row.loading:
                continue
            color = _STATE_COLORS.get(row.state)
            style = f" style='color:{color}'" if color else ""
            parts.append(f"<tr><td class='k'>{esc(row.label)}</td><td{style}>{esc(row.value)}</td></tr>")
        parts.append("</table></section>")
    parts.append("</body></html>")
    return "\n".join(parts)
