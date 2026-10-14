from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from fvpl_ittools.core import licenses, log

KEY_A = "AAAAA-BBBBB-CCCCC-DDDDD-11111"
KEY_B = "AAAAA-BBBBB-CCCCC-DDDDD-22222"


def test_normalize_and_find_keys():
    assert licenses.normalize_key("aaaaa bbbbb ccccc ddddd 11111") == KEY_A
    assert licenses.normalize_key("AAAAABBBBBCCCCCDDDDD11111") == KEY_A
    assert licenses.normalize_key("AAAAA-BBBBB-CCCCC-DDDDD") is None
    assert licenses.normalize_key("AAAAA-BBBBB-CCCCC-DDDDD-1111!") is None
    text = f"Office 2016: {KEY_A}\n{KEY_B.lower()}\nlặp lại {KEY_A}\nkhông phải key: 12345-67890"
    assert licenses.keys_in_text(text) == [KEY_A, KEY_B]


def test_file_round_trip_masks_keys_in_log(tmp_path):
    path = tmp_path / "usb" / licenses.FILE_NAME
    assert licenses.load(path) == []  # chưa có file
    keys, skipped = licenses.add_keys([], " Office 2016 Standard ", [KEY_A, KEY_B, KEY_A], "MAK", "50 lượt",
                                      now=datetime(2026, 10, 14))
    assert skipped == [] and [key.key for key in keys] == [KEY_A, KEY_B] and keys[0].added == "14/10/2026"
    keys, skipped = licenses.add_keys(keys, "Office 2016 Standard", [KEY_B], "MAK", "")
    assert skipped == [KEY_B] and len(keys) == 2
    assert licenses.record_usage(keys, keys[0].id, "FVPL-KT05", True, now=datetime(2026, 10, 14, 9, 0))
    assert licenses.record_usage(keys, keys[0].id, "fvpl-kt05", True)
    assert licenses.record_usage(keys, keys[0].id, "FVPL-KT06", False, "hết lượt")
    assert not licenses.record_usage(keys, "khong-co", "X", True)
    licenses.save(path, keys)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["keys"][0]["product"] == "Office 2016 Standard" and "git" in data["about"]
    loaded = licenses.load(path)
    assert [key.key for key in loaded] == [KEY_A, KEY_B] and loaded[0].activations == 1
    assert loaded[0].used_text.startswith("1 máy · lần cuối FVPL-KT06") and loaded[0].used_text.endswith("(lỗi)")
    assert loaded[1].used_text == "Chưa dùng" and loaded[0].masked == "•••••-•••••-•••••-•••••-11111"
    assert loaded[0].kind == "office" and log.mask(f"key {KEY_A}") == f"key {log.MASK}"
    assert not list(path.parent.glob("*.tmp"))
    path.write_text("{không phải json", encoding="utf-8")
    with pytest.raises(licenses.LicenseError):
        licenses.load(path)
    path.write_text(json.dumps({"x": 1}), encoding="utf-8")
    with pytest.raises(licenses.LicenseError):
        licenses.load(path)


def test_default_path_and_gitignore(tmp_path):
    assert licenses.default_path(r"E:\keys.json", None, tmp_path) == Path(r"E:\keys.json")
    assert licenses.default_path("", Path(r"F:\Tool"), tmp_path) == Path(r"F:\Tool") / licenses.FILE_NAME
    assert licenses.default_path("", None, tmp_path) == tmp_path / licenses.FILE_NAME
    ignore = (Path(__file__).parent.parent / ".gitignore").read_text(encoding="utf-8")
    assert "license-keys*.json" in ignore  # chạy từ mã nguồn thì file key nằm ở gốc repo công khai


def test_suggested_keys_follow_windows_edition():
    keys = [licenses.LicenseKey("Windows 10/11 Pro", KEY_A), licenses.LicenseKey("Windows 10/11 Enterprise", KEY_B),
            licenses.LicenseKey("Office 2016 Standard", "AAAAA-BBBBB-CCCCC-DDDDD-33333")]
    keys[0].used.append(licenses.Usage("PC1", "", True))
    pro2 = licenses.LicenseKey("Windows 10/11 Pro", "AAAAA-BBBBB-CCCCC-DDDDD-44444")
    assert [key.key for key in licenses.suggested(keys + [pro2], "Windows 11 Pro")] == [pro2.key, KEY_A]
    assert [key.key for key in licenses.suggested(keys, "Windows 11 Enterprise")] == [KEY_B]
    assert licenses.suggested(keys, "Windows 11 Home") == []


def test_activation_actions_keep_key_out_of_first_line():
    windows = licenses.activation_action(licenses.LicenseKey("Windows 10/11 Pro", KEY_A))
    script = windows.apply[0].script
    assert windows.admin and windows.id.startswith("lic.activate_") and "slmgr.vbs" in script
    first = script.splitlines()[0]
    assert first.startswith("#") and KEY_A not in first and "11111" in first  # log chỉ in dòng đầu
    assert script.count(KEY_A) == 1 and "Replace($ProductKey" in script
    office = licenses.activation_action(licenses.LicenseKey("Office 2013 Standard", KEY_B)).apply[0].script
    assert "OSPP.VBS" in office and "'Office15', 'Office16', 'Office14'" in office
    assert licenses.office_versions("Office LTSC 2021 Standard")[0] == "Office16"
    status = licenses.status_action()
    assert not status.admin and licenses.WINDOWS_APP_ID in status.apply[0].script
