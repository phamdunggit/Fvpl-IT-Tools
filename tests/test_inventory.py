from __future__ import annotations

import threading
from datetime import datetime

import pytest

from fvpl_ittools.core import inventory

NOW = datetime(2026, 10, 13, 9, 0)

SAMPLE = {
    "os": {
        "caption": "Microsoft Windows 11 Pro", "display_version": "25H2", "build": "26200", "ubr": 6584,
        "architecture": "64-bit", "install_date": "2025-03-04T10:00:00", "last_boot": "2026-09-20T08:00:00",
        "logged_on_user": "CORP\\nva",
    },
    "licenses": [
        {"product": "windows", "name": "Windows(R), Professional edition", "status": 1, "channel": "Volume:MAK"},
        {"product": "office", "name": "Office 16, Office16StandardVL_MAK edition", "status": 0, "channel": "Volume:MAK"},
    ],
    "office": None,
    "hardware": {
        "manufacturer": "LENOVO", "model": "21A0002XVN", "model_version": "ThinkPad E14 Gen 4", "serial": "PF3ABC12",
        "bios_version": "R1EET59W", "bios_date": "2026-01-10T00:00:00", "pc_type": 2, "has_battery": True,
        "cpu": [{"name": "Intel(R) Core(TM) i5-1235U", "cores": 10, "threads": 12}],
        "ram_total": 16 * 1024**3 - 300 * 1024**2, "ram_slots": 2,
        "ram_modules": [{"slot": "DIMM 0", "size": 8 * 1024**3, "speed": 3200}, {"slot": "DIMM 1", "size": 8 * 1024**3, "speed": 3200}],
        "gpu": ["Intel(R) Iris(R) Xe Graphics"], "monitors": ["LEN 0x40B8"],
    },
    "volumes": [{"drive": "C:", "label": "", "size": 476 * 1024**3, "free": 9 * 1024**3}],
    "system_drive": "C:",
    "disks": [{"name": "SAMSUNG MZVL4512", "media": 4, "bus": 17, "size": 512 * 10**9, "health": 1}],
    "network": [{
        "name": "Ethernet", "description": "Intel(R) Ethernet Connection", "mac": "AA:BB:CC:DD:EE:FF", "wireless": False,
        "speed": 1_000_000_000, "ipv4": ["10.0.0.25"], "gateway": ["10.0.0.1"], "dns": ["10.0.0.10", "8.8.8.8"],
        "dhcp": True,
    }],
    "dns_checks": [{"server": "10.0.0.10", "finds_dc": True}, {"server": "8.8.8.8", "finds_dc": False}],
    "security": {
        "is_admin": True,
        "defender": {"enabled": True, "realtime": True, "mode": "Normal", "signature_date": "2026-09-30T07:00:00"},
        "antivirus": [{"name": "Windows Defender", "state": 397568}],
        "firewall": [{"profile": "Domain", "enabled": True}, {"profile": "Private", "enabled": True},
                     {"profile": "Public", "enabled": False}],
        "bitlocker": {"protection": 0, "conversion": 1, "percent": 100},
        "tpm": {"present": True, "ready": True, "version": "2.0"},
        "firmware": "UEFI", "secure_boot": 1,
        "last_update": {"date": "2026-07-01T10:00:00", "title": "2026-06 Cumulative Update"},
    },
}


def basics(joined=True, admin=True):
    return inventory.Basics("PC-01", "corp.example" if joined else "Workgroup WORKGROUP", joined,
                            "Windows 11 Pro 25H2", "CORP\\nva", admin, now=NOW)


def rows(sections, key):
    section = next(section for section in sections if section.key == key)
    return {row.label: row for row in section.rows}


def test_sections_from_sample():
    sections = inventory.build_sections(SAMPLE, basics())
    system = rows(sections, "system")
    assert system["Windows"].value == "Microsoft Windows 11 Pro 25H2 build 26200.6584, 64-bit"
    assert system["Khởi động lúc"].state == "warn"  # chạy hơn 14 ngày
    assert system["Kích hoạt Windows"] == inventory.Row("Kích hoạt Windows", "Đã kích hoạt (Volume:MAK)", "ok")
    assert system["Kích hoạt Office"].state == "bad"

    hardware = rows(sections, "hardware")
    assert hardware["Hãng / Model"].value == "LENOVO ThinkPad E14 Gen 4 (21A0002XVN)"
    assert hardware["Loại máy"].value == "Laptop"
    assert hardware["RAM"].value == "16 GB (2 thanh 8 GB, 3200 MHz), dùng 2/2 khe"
    assert hardware["Ổ đĩa 1"].value == "SAMSUNG MZVL4512 · SSD NVMe · 477 GB · Cảnh báo"
    assert hardware["Ổ đĩa 1"].state == "warn"
    assert hardware["Phân vùng C"].state == "warn"  # còn 9 GB

    network = rows(sections, "network")
    assert "IP 10.0.0.25 (DHCP)" in network["Ethernet (LAN)"].value
    assert "1 Gbps" in network["Ethernet (LAN)"].value
    assert network["DNS 10.0.0.10"].state == "ok"
    assert network["DNS 8.8.8.8"].state == "bad"

    security = rows(sections, "security")
    assert security["Microsoft Defender"].state == "warn"  # chữ ký cũ hơn 7 ngày
    assert security["Firewall"].state == "bad"
    assert security["BitLocker ổ hệ thống"].value == "Đã mã hoá, đang TẠM DỪNG bảo vệ"
    assert security["TPM"] == inventory.Row("TPM", "TPM 2.0", "ok")
    assert security["Secure Boot"].state == "ok"
    assert security["Cập nhật Windows gần nhất"].state == "warn"


def test_loading_and_failed_parts():
    sections = inventory.build_sections({}, basics(), failed={"security": "WMI hỏng"})
    assert rows(sections, "hardware")[""].loading
    assert rows(sections, "security")[""] == inventory.Row("", "Không đọc được: WMI hỏng", "bad")
    partial = {key: SAMPLE[key] for key in ("os", "hardware", "volumes")}
    hardware = rows(inventory.build_sections(partial, basics(), failed={"storage": "lỗi"}), "hardware")
    assert hardware["Ổ đĩa"].value == "Không đọc được: lỗi"
    text = inventory.to_text(inventory.build_sections(partial, basics()), basics())
    assert "Đang đọc" not in text


def test_third_party_antivirus_and_non_admin():
    data = dict(SAMPLE)
    data["security"] = dict(SAMPLE["security"], is_admin=False, tpm=None, bitlocker={"shell_value": 2},
                            defender={"enabled": False, "realtime": False, "mode": "Not running", "signature_date": None},
                            antivirus=[{"name": "Symantec Endpoint Protection", "state": 266240},
                                       {"name": "Windows Defender", "state": 393472}])
    security = rows(inventory.build_sections(data, basics(admin=False)), "security")
    assert security["Microsoft Defender"].state == "muted"
    assert security["Diệt virus"].value == "Symantec Endpoint Protection: đang bật, đã cập nhật"
    assert security["TPM"].value == "Cần quyền admin để đọc"
    assert security["BitLocker ổ hệ thống"].value == "Tắt"


def test_alerts_only_when_no_dns_finds_dc():
    assert inventory.alerts(SAMPLE, basics()) == []
    bad = dict(SAMPLE, dns_checks=[{"server": "8.8.8.8", "finds_dc": False}])
    assert inventory.alerts(bad, basics()) == ["DNS không trỏ về DC"]
    assert inventory.alerts(bad, basics(joined=False)) == []


def test_export_text_and_html_escape():
    data = dict(SAMPLE, hardware=dict(SAMPLE["hardware"], model="<script>"))
    sections = inventory.build_sections(data, basics())
    text = inventory.to_text(sections, basics())
    assert text.startswith("Thông tin máy PC-01 (lúc 13/10/2026 09:00)")
    assert "== Phần cứng ==" in text and "Serial: PF3ABC12" in text
    page = inventory.to_html(sections, basics(), "0.2.0")
    assert "&lt;script&gt;" in page and "<script>" not in page
    assert "color:#b91c1c" in page


@pytest.mark.parametrize("size, label", [
    (0, "?"), (8 * 1024**3, "8 GB"), (int(7.6 * 1024**3), "7,6 GB"), (476 * 1024**3, "476 GB"),
    (int(1.8 * 1024**4), "1,8 TB"),
])
def test_size_label(size, label):
    assert inventory.size_label(size) == label


def test_clean_turns_empty_objects_into_none():
    assert inventory._clean({"a": {}, "b": [{}, 1], "c": {"d": 2}}) == {"a": None, "b": [None, 1], "c": {"d": 2}}


def test_collect_real_parts_on_this_machine():
    """Chạy thật cả 4 script (chỉ đọc) để bắt lỗi script mà test parse không thấy."""
    data = {}
    for part in inventory.PARTS:
        data.update(inventory.collect_part(part))
    assert data["os"]["caption"]
    assert data["hardware"]["cpu"]
    assert isinstance(data["network"], list)
    assert "firewall" in data["security"]
    sections = inventory.build_sections(data, basics())
    assert not any(row.loading for section in sections for row in section.rows)


def test_collect_part_can_be_cancelled():
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(inventory.InventoryError, match="huỷ"):
        inventory.collect_part("system", cancel)
