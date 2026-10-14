from __future__ import annotations

import json
from datetime import datetime

import pytest

from fvpl_ittools.core import drivers, eventlog, lockedfiles, paths, wifi

# ---------------------------------------------------------------- event log


def test_eventlog_parse_orders_and_hints():
    output = json.dumps([
        {"log": "System", "source": "Disk", "id": 7, "level": 2, "count": 2, "latest": "13/10/2026 09:00",
         "sort": "2026-10-13T09:00:00", "message": "The device has a bad block.\nMore"},
        {"log": "System", "source": "Microsoft-Windows-Kernel-Power", "id": 41, "level": 1, "count": 1,
         "latest": "12/10/2026 07:43", "sort": "2026-10-12T07:43:00", "message": "Rebooted"},
        {"log": "Application", "source": "Application Error", "id": 1000, "level": 2, "count": 2,
         "latest": "13/10/2026 10:00", "sort": "2026-10-13T10:00:00", "message": ""},
        {"log": "System", "source": "X", "id": 1, "level": 2, "count": 9, "latest": "01/10/2026 10:00",
         "sort": "2026-10-01T10:00:00", "message": "Lặp nhiều"},
    ])
    groups = eventlog.parse(output)
    assert [(group.source, group.event_id) for group in groups] == [
        ("Microsoft-Windows-Kernel-Power", 41),   # Critical lên đầu
        ("X", 1),                                 # rồi lỗi lặp nhiều
        ("Application Error", 1000),              # cùng số lần thì gần đây trước
        ("Disk", 7)]
    assert groups[0].critical and "tắt đột ngột" in groups[0].hint
    assert groups[3].summary == "The device has a bad block." and "bad block" in groups[3].hint
    assert groups[1].hint == ""
    one = eventlog.parse(json.dumps({"log": "System", "source": "NETLOGON", "id": 5719, "level": 2, "count": 1}))
    assert len(one) == 1 and "DC" in one[0].hint
    assert eventlog.parse("[]") == []


def test_eventlog_reads_this_machine():
    assert all(group.count > 0 for group in eventlog.read_errors(24))


# ---------------------------------------------------------------- Wi-Fi

_PROFILE = """<?xml version="1.0"?>
<WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">
  <name>{name}</name>
  <SSIDConfig><SSID><name>{ssid}</name></SSID></SSIDConfig>
  <MSM><security>
    <authEncryption><authentication>{auth}</authentication><encryption>AES</encryption></authEncryption>
    {key}
  </security></MSM>
</WLANProfile>"""


def test_wifi_parse_profile():
    key = "<sharedKey><keyType>passPhrase</keyType><protected>false</protected><keyMaterial>Mk@123456</keyMaterial></sharedKey>"
    profile = wifi.parse_profile(_PROFILE.format(name="Office", ssid="Office-5G", auth="WPA2PSK", key=key))
    assert profile == wifi.WifiProfile("Office", "Office-5G", "WPA2PSK", "Mk@123456")
    protected = key.replace("<protected>false", "<protected>true").replace("Mk@123456", "01000000D08C9DDF")
    assert wifi.parse_profile(_PROFILE.format(name="A", ssid="A", auth="WPA3SAE", key=protected)).password == ""
    assert wifi.parse_profile(_PROFILE.format(name="Free", ssid="Free", auth="open", key="")).password == ""
    assert wifi.parse_profile("không phải xml") is None


# ---------------------------------------------------------------- file bị khoá


def test_lockers_finds_this_process(tmp_path):
    file = tmp_path / "dang-mo.txt"
    with open(file, "w", encoding="utf-8") as handle:
        handle.write("x")
        found = lockedfiles.lockers(str(file))
        assert found and all(item.pid > 0 for item in found)
    assert lockedfiles.lockers(str(file)) == []
    assert lockedfiles.files_in(str(tmp_path)) == [str(file)]
    with pytest.raises(lockedfiles.LockError):
        lockedfiles.lockers(str(tmp_path / "khong-co"))


# ---------------------------------------------------------------- driver


def test_driver_backup_paths_and_actions(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "portable_root", lambda: tmp_path)
    folder = drivers.backup_dir("FVPL-KT05", datetime(2026, 10, 13, 9, 30))
    assert folder == tmp_path / "DriverBackup" / "FVPL-KT05_20261013_0930"
    backup = drivers.backup_action(folder)
    assert backup.id == "drv.backup" and "pnputil.exe /export-driver *" in backup.apply[0].script
    assert f"$Destination = '{folder}'" in backup.apply[0].script
    restore = drivers.restore_action(folder)
    assert 259 in restore.apply[0].ok_codes and 3010 in restore.apply[0].reboot_codes
    monkeypatch.setattr(paths, "portable_root", lambda: None)
    assert drivers.backup_root() == paths.state_dir() / "driver-backup"
