"""Khung "Tình trạng máy này" của Trang chủ: vài dòng dễ hiểu từ thông tin máy, dòng có vấn đề kèm một nút sửa.

Dữ liệu lấy từ các phần thu thập của trang Tổng quan (core/inventory.py), không chạy thêm lệnh nào.
"""

from __future__ import annotations

from dataclasses import dataclass

from .inventory import (
    LICENSE_STATUS,
    UPDATE_MAX_DAYS,
    Basics,
    _antivirus_state,
    _days_since,
    _parse_time,
    size_label,
)

UPTIME_MAX_DAYS = 14
LOW_FREE_PERCENT = 10
LOW_FREE_BYTES = 15 * 1024**3


@dataclass(frozen=True)
class HealthItem:
    text: str
    state: str            # ok | warn | bad
    button: str = ""      # chữ trên nút sửa
    target: str = ""      # đích điều hướng (giống kết quả tìm kiếm), ví dụ "page:optimize", "action:wu.scan_install"


def _system_drive(data: dict) -> HealthItem | None:
    drive = str(data.get("system_drive") or "C:").upper()
    for volume in data.get("volumes") or []:
        if str(volume.get("drive") or "").upper() != drive:
            continue
        size, free = volume.get("size") or 0, volume.get("free") or 0
        if not size:
            return None
        percent = round(free * 100 / size)
        letter = drive.rstrip(":")
        if percent < LOW_FREE_PERCENT or free < LOW_FREE_BYTES:
            state = "bad" if percent < 5 else "warn"
            return HealthItem(f"Ổ {letter} chỉ còn trống {size_label(free)} ({percent}%)", state, "Dọn rác", "page:optimize")
        return HealthItem(f"Ổ {letter} còn trống {size_label(free)} ({percent}%)", "ok")
    return None


def items(data: dict, basics: Basics) -> list[HealthItem]:
    """Dòng có vấn đề trước, dòng ổn sau. Phần nào chưa đọc xong thì chưa có dòng của phần đó."""
    result: list[HealthItem] = []
    if basics.joined_domain:
        checks = data.get("dns_checks") or []
        if checks and not any(check.get("finds_dc") for check in checks):
            result.append(HealthItem("Đã vào domain nhưng DNS không trỏ về máy chủ domain", "bad", "Sửa lỗi mạng",
                                     "fixes:Mạng & Internet"))
        else:
            result.append(HealthItem(f"Đã vào domain {basics.domain_label}", "ok"))
    else:
        result.append(HealthItem(f"Máy chưa vào domain ({basics.domain_label})", "warn", "Cài máy mới", "page:newpc"))

    if data.get("network") == []:
        result.append(HealthItem("Không có card mạng nào đang kết nối", "bad", "Sửa lỗi mạng", "fixes:Mạng & Internet"))

    drive = _system_drive(data)
    if drive is not None:
        result.append(drive)

    for disk in data.get("disks") or []:
        if disk.get("health") == 2:
            result.append(HealthItem(f"Ổ đĩa {disk.get('name') or ''} báo hỏng: sao lưu dữ liệu ngay".replace("  ", " "),
                                     "bad", "Xem thông tin máy", "page:overview"))

    licenses = data.get("licenses") or []
    windows = [item for item in licenses if item.get("product") == "windows"]
    if windows and not any(item.get("status") == 1 for item in windows):
        label, _ = LICENSE_STATUS.get(windows[0].get("status"), ("chưa kích hoạt", "warn"))
        result.append(HealthItem(f"Windows: {label.lower()}", "warn", "Xem thông tin máy", "page:overview"))
    office = [item for item in licenses if item.get("product") == "office"]
    if office:
        if any(item.get("status") == 1 for item in office):
            result.append(HealthItem("Office đã kích hoạt", "ok"))
        else:
            result.append(HealthItem("Office chưa kích hoạt", "warn", "Kích hoạt", "action:off.activate_volume"))

    security = data.get("security") or {}
    if security:
        others = [item for item in security.get("antivirus") or [] if "defender" not in str(item.get("name", "")).lower()]
        defender = security.get("defender") or {}
        protected = [item.get("name") for item in others if _antivirus_state(int(item.get("state") or 0)) == (True, True)]
        if protected:
            result.append(HealthItem(f"{protected[0]} đang bật, đã cập nhật", "ok"))
        elif others:
            result.append(HealthItem(f"{others[0].get('name')} đang tắt hoặc chưa cập nhật", "bad", "Xem thông tin máy",
                                     "page:overview"))
        elif defender.get("enabled") and defender.get("realtime"):
            result.append(HealthItem("Microsoft Defender đang bật", "ok"))
        elif defender:
            result.append(HealthItem("Diệt virus đang tắt", "bad", "Quét bằng Defender", "action:sec.defender_scan"))
        update = security.get("last_update") or {}
        days = _days_since(update.get("date"), basics.now)
        if days is not None and days > UPDATE_MAX_DAYS:
            result.append(HealthItem(f"Windows chưa cập nhật {days} ngày", "warn", "Cập nhật",
                                     "action:wu.scan_install"))

    os_info = data.get("os") or {}
    boot = _parse_time(os_info.get("last_boot"))
    if boot is not None:
        days = (basics.now - boot).days
        if days > UPTIME_MAX_DAYS:
            result.append(HealthItem(f"Máy chạy liên tục {days} ngày chưa khởi động lại", "warn"))

    order = {"bad": 0, "warn": 1, "ok": 2}
    return sorted(result, key=lambda item: order.get(item.state, 3))
