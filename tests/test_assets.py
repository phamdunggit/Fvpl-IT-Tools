from __future__ import annotations

import json
import zipfile
from datetime import datetime
from xml.etree import ElementTree

import pytest

from fvpl_ittools.core import assets, inventory, paths

from .test_inventory import SAMPLE

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def basics(name: str = "FVPL-KT05") -> inventory.Basics:
    return inventory.Basics(computer_name=name, domain_label="corp.example", joined_domain=True,
                            os_label="Windows 11 Pro 25H2 (build 26200.6584)", target_user="CORP\\it", is_admin=True,
                            now=datetime(2026, 10, 13, 9, 30))


def test_record_from_overview_data():
    item = assets.record(SAMPLE, basics(), "0.3.0", department="KT", primary_user="Nguyễn Văn A")
    assert item["time"] == "13/10/2026 09:30" and item["computer"] == "FVPL-KT05"
    assert item["department"] == "KT" and item["user"] == "Nguyễn Văn A"
    assert item["model"] == "ThinkPad E14 Gen 4 (21A0002XVN)" and item["serial"] == "PF3ABC12"
    assert item["kind"] == "Laptop" and item["ram_gb"] == 16.0 and item["system_free_gb"] == 9.0
    assert item["disks"].startswith("SSD NVMe") and "25H2" in item["windows"]
    assert item["windows_license"] == "Đã kích hoạt"
    assert "Office16StandardVL_MAK" in item["office"] and "chưa kích hoạt" in item["office"]
    assert item["ip"] == "10.0.0.25" and item["mac"] == "AA:BB:CC:DD:EE:FF"
    assert item["antivirus"] == "Microsoft Defender (bật)" and item["bitlocker"] == "Đã mã hoá, tạm dừng"
    assert item["tpm"] == "TPM 2.0" and item["last_update"] == "01/07/2026"
    assert set(item) == {column.key for column in assets.COLUMNS}


def test_record_when_every_part_failed():
    item = assets.record({}, basics(), "0.3.0")
    assert item["computer"] == "FVPL-KT05" and item["user"] == "CORP\\it"
    assert item["serial"] == "" and item["ram_gb"] == "" and item["windows"].startswith("Windows 11")


def test_save_replaces_renamed_machine(tmp_path):
    old = dict(assets.record(SAMPLE, basics("DESKTOP-ABC"), "0.3.0"))
    assets.save_record(tmp_path, old)
    other = dict(old, computer="FVPL-KT01", serial="ZZ999999")
    assets.save_record(tmp_path, other)
    assets.save_record(tmp_path, dict(old, computer="FVPL-KT05"))  # cùng serial, đã đổi tên
    assert sorted(file.name for file in tmp_path.glob("*.json")) == ["FVPL-KT01.json", "FVPL-KT05.json"]
    # Serial giả của bo mạch tự ráp không dùng để nhận ra máy.
    assets.save_record(tmp_path, dict(old, computer="PC-A", serial="To be filled by O.E.M."))
    assets.save_record(tmp_path, dict(old, computer="PC-B", serial="To be filled by O.E.M."))
    assert [item["computer"] for item in assets.load_records(tmp_path)] == ["FVPL-KT01", "FVPL-KT05", "PC-A", "PC-B"]
    (tmp_path / "hong.json").write_text("{không phải json", encoding="utf-8")
    assert len(assets.load_records(tmp_path)) == 4


def test_inventory_dir(tmp_path, monkeypatch, state_dir):
    monkeypatch.setattr(paths, "portable_root", lambda: tmp_path / "usb")
    assert assets.inventory_dir() == tmp_path / "usb" / "Inventory"
    monkeypatch.setattr(paths, "portable_root", lambda: None)
    (tmp_path / "ssd").mkdir()
    assert assets.inventory_dir(str(tmp_path / "ssd")) == tmp_path / "ssd" / "Inventory"
    assert assets.inventory_dir(str(tmp_path / "da-rut")) == state_dir / "inventory"


def test_portable_root_is_none_inside_app_copy(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "app_root", lambda: tmp_path / "app")
    monkeypatch.setattr(paths, "app_copy_dir", lambda: tmp_path / "app")
    assert paths.portable_root() is None
    monkeypatch.setattr(paths, "app_copy_dir", lambda: tmp_path / "khac")
    assert paths.portable_root() == tmp_path / "app"


def test_column_names():
    assert [assets._column_name(index) for index in (0, 25, 26, 27, 701)] == ["A", "Z", "AA", "AB", "ZZ"]


def test_xlsx_is_well_formed_and_safe(tmp_path):
    records = [
        assets.record(SAMPLE, basics(), "0.3.0"),
        dict(assets.record({}, basics("PC<2>&"), "0.3.0"), user="=HYPERLINK(\"x\")", office="a\x01b"),
    ]
    file = tmp_path / "KiemKe.xlsx"
    assets.write_xlsx(file, records)
    with zipfile.ZipFile(file) as archive:
        names = set(archive.namelist())
        assert names == set(assets.workbook_parts([]))
        for name in names:
            ElementTree.fromstring(archive.read(name))  # XML hợp lệ
        sheet = ElementTree.fromstring(archive.read("xl/worksheets/sheet1.xml"))
    rows = sheet.findall(".//m:sheetData/m:row", NS)
    assert len(rows) == 3
    header = [cell.findtext(".//m:t", namespaces=NS) for cell in rows[0]]
    assert header == [column.title for column in assets.COLUMNS]
    ram = rows[1][[column.key for column in assets.COLUMNS].index("ram_gb")]
    assert ram.get("t") is None and ram.findtext("m:v", namespaces=NS) == "16.0"  # số, Excel tự định dạng
    cells = {cell.get("r")[0]: cell for cell in rows[2]}
    assert cells["B"].findtext(".//m:t", namespaces=NS) == "PC<2>&"
    user = cells["E"]
    assert user.get("t") == "inlineStr" and user.findtext(".//m:t", namespaces=NS).startswith("=HYPERLINK")
    assert sheet.find("m:autoFilter", NS).get("ref") == "A1:Y3"


def test_save_reports_locked_workbook(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "portable_root", lambda: tmp_path)
    result = assets.save(assets.record(SAMPLE, basics(), "0.3.0"))
    assert result.workbook == tmp_path / "Inventory" / "KiemKe.xlsx" and result.count == 1
    assert json.loads(result.record_file.read_text(encoding="utf-8"))["serial"] == "PF3ABC12"

    def locked(file, records):
        raise PermissionError("đang mở")
    monkeypatch.setattr(assets, "write_xlsx", locked)
    result = assets.save(dict(assets.record(SAMPLE, basics("FVPL-KT06"), "0.3.0"), serial="PF3XYZ99"))
    assert result.workbook is None and "Excel" in result.error and result.count == 2
