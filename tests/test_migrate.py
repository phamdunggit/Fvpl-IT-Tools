from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from fvpl_ittools.core import migrate, shell
from fvpl_ittools.software.catalog import parse_app

GB = 1024**3


def test_item_paths_follow_user_shell_folders():
    profile = r"C:\Users\an"
    folders = {"Personal": r"%USERPROFILE%\OneDrive\Documents", "Desktop": r"D:\Data\Desktop"}
    assert migrate.item_path(migrate.SPECS["documents"], profile, folders) == r"C:\Users\an\OneDrive\Documents"
    assert migrate.item_path(migrate.SPECS["desktop"], profile, folders) == r"D:\Data\Desktop"
    assert migrate.item_path(migrate.SPECS["pictures"], profile, {}) == r"C:\Users\an\Pictures"
    assert migrate.item_path(migrate.SPECS["chrome"], profile, {}).endswith(r"Google\Chrome\User Data\Default")
    assert migrate.item_path(migrate.SPECS["coccoc"], profile, {}).endswith(r"CocCoc\Browser\User Data\Default")
    assert migrate.item_path(migrate.SPECS["wifi"], profile, {}) == ""
    assert migrate.expand_profile(r"%LOCALAPPDATA%\x", profile) == r"C:\Users\an\AppData\Local\x"
    extra = migrate.extra_spec("C:\\KeToan\\Data\\")
    assert extra.folder == rf"Khac\C-Data-{extra.id[6:12]}" and extra.source == r"C:\KeToan\Data" and extra.kind == "extra"
    assert migrate.extra_spec(r"D:\Data").folder != extra.folder  # cùng tên khác chỗ: không chép chồng
    assert migrate.item_path(extra, profile, {}) == r"C:\KeToan\Data" and extra.id == migrate.extra_spec(r"c:\ketoan\data").id


def test_measure_counts_files_recursively(tmp_path):
    (tmp_path / "a" / "b").mkdir(parents=True)
    (tmp_path / "a" / "one.txt").write_bytes(b"12345")
    (tmp_path / "a" / "b" / "two.txt").write_bytes(b"123")
    (tmp_path / "a" / "thu.PST").write_bytes(b"12")
    assert migrate.measure(str(tmp_path)) == (10, 3)
    assert migrate.measure(str(tmp_path / "a"), pattern="*.pst") == (2, 1)  # chỉ thư mục đó, không đi xuống
    assert migrate.measure(str(tmp_path / "khong-co")) == (0, 0)


def test_root_folders_skip_windows_folders(tmp_path):
    drive = tmp_path / "drive"
    for name in ("KeToan", "Windows", "Program Files", "$Recycle.Bin", ".cache", "Users", "FVPL-SaoLuu"):
        (drive / name).mkdir(parents=True)
    (drive / "file.txt").write_text("x", encoding="utf-8")
    assert migrate.root_folders(str(drive)) == [str(drive / "KeToan")]


def test_scan_sources_with_extra_folder(tmp_path, monkeypatch):
    (tmp_path / "Desktop").mkdir()
    (tmp_path / "Desktop" / "a.txt").write_text("abc", encoding="utf-8")
    data = tmp_path / "KeToan"
    data.mkdir()
    (data / "so.xlsx").write_bytes(b"1234")
    monkeypatch.setattr(migrate, "shell_folders", lambda sid: {})
    sources = migrate.scan_sources("S-1-5-21-0", str(tmp_path), extras=[str(data)], machine_items=False)
    by_id = {source.spec.id: source for source in sources}
    assert "wifi" not in by_id and by_id["desktop"].usable and by_id["desktop"].size_label == "3 B · 1 file"
    assert not by_id["documents"].usable
    extra = sources[-1]
    assert extra.spec.kind == "extra" and (extra.bytes, extra.files) == (4, 1)
    drivers = migrate.Source(migrate.SPECS["drivers"], "", True)
    wifi = migrate.Source(migrate.SPECS["wifi"], "", True, 0, 3)
    assert drivers.usable and drivers.estimate == migrate.DRIVER_ESTIMATE and wifi.size_label == "3 mạng"


def test_pick_target_never_uses_system_drive(monkeypatch):
    monkeypatch.setenv("SystemDrive", "C:")
    c = migrate.Drive("C:\\", "fixed", 900 * GB)
    d = migrate.Drive("D:\\", "fixed", 300 * GB, "Data")
    e = migrate.Drive("E:\\", "removable", 50 * GB, "USB")
    f = migrate.Drive("F:\\", "removable", 900 * GB)
    w = migrate.Drive("W:\\", "network", 9000 * GB)
    assert migrate.pick_target([c, d, e, w], Path(r"E:\FVPL-ITTools"), 10 * GB) == Path(r"E:\FVPL-SaoLuu")
    assert migrate.pick_target([c, d, e], Path(r"E:\FVPL-ITTools"), 60 * GB) == Path(r"D:\FVPL-SaoLuu")
    assert migrate.pick_target([c, e, f], Path(r"C:\Tools"), 60 * GB) == Path(r"F:\FVPL-SaoLuu")
    assert migrate.pick_target([c, w], None, GB) is None  # chỉ có ổ C và ổ mạng: để IT chọn
    assert migrate.on_system_drive(Path(r"c:\x")) and not migrate.on_system_drive(r"D:\x")
    assert d.title == "Data (D:, ổ trong máy)" and e.title == "USB (E:, USB)"


def _sources(tmp_path: Path) -> list[migrate.Source]:
    extra = migrate.extra_spec(r"C:\KeToan")
    return [migrate.Source(migrate.SPECS["desktop"], str(tmp_path / "Desktop"), True, 10, 2),
            migrate.Source(migrate.SPECS["chrome"], str(tmp_path / "Chrome"), True, 5, 1),
            migrate.Source(extra, extra.source, True, 7, 1)]


def test_manifest_round_trip_and_listing(tmp_path):
    root = tmp_path / migrate.FOLDER
    old = migrate.new_backup_folder(root, "FVPL-KT05", "CORP\\an", datetime(2026, 10, 1, 9, 0))
    new = migrate.new_backup_folder(root, "FVPL KT06", "CORP\\binh", datetime(2026, 10, 2, 9, 0))
    assert old.name == "FVPL-KT05_an_20261001_0900" and new.name == "FVPL-KT06_binh_20261002_0900"
    migrate.write_manifest(old, "FVPL-KT05", "CORP\\an", "0.2.0", _sources(tmp_path),
                           [{"name": "HP", "where": "10.0.0.5"}], ["Zalo", "Google Chrome", "Zalo"],
                           now=datetime(2026, 10, 1, 9, 0))
    backup = migrate.read_backup(old)
    assert backup.computer == "FVPL-KT05" and [item["id"] for item in backup.items][:2] == ["desktop", "chrome"]
    assert backup.spec(backup.items[2]).source == r"C:\KeToan"
    assert backup.software == ["Google Chrome", "Zalo"] and backup.printers[0]["where"] == "10.0.0.5"
    (root / "rac").mkdir()
    assert [item.folder for item in migrate.list_backups(root)] == [old]
    assert migrate.list_backups(None) == [] and migrate.list_backups(tmp_path / "khong-co") == []
    usb = tmp_path / "usb"
    second = migrate.new_backup_folder(usb / migrate.FOLDER, "FVPL-KT05", "an", datetime(2026, 10, 3, 9, 0))
    migrate.write_manifest(second, "FVPL-KT05", "an", "0.2.0", [], [], [], now=datetime(2026, 10, 3, 9, 0))
    drives = [migrate.Drive(str(usb) + "\\", "removable", GB), migrate.Drive("W:\\", "network", GB)]
    found = migrate.find_backups(drives, [root, root])
    assert [item.folder for item in found] == [second, old]  # mới nhất trước, không trùng
    assert found[0].label.startswith("FVPL-KT05 · an · 03/10/2026 09:00")
    (old / migrate.MANIFEST).write_text(json.dumps({"x": 1}), encoding="utf-8")
    assert migrate.list_backups(root) == []  # manifest hỏng thì bỏ qua


def test_backup_and_restore_scripts(tmp_path):
    folder = tmp_path / "backup"
    sources = _sources(tmp_path) + [
        migrate.Source(migrate.SPECS["outlook_data"], r"C:\Users\an\AppData\Local\Microsoft\Outlook", True, 9, 1),
        migrate.Source(migrate.SPECS["wifi"], "", True, 0, 2),
        migrate.Source(migrate.SPECS["drivers"], "", True)]
    desktop, chrome, extra, pst, wifi, drivers = migrate.backup_actions(sources, folder)
    assert desktop.id == "move.backup_desktop" and "& robocopy $source $target /E" in desktop.apply[0].script
    assert shell.ps_quote(str(folder / "Desktop")) in desktop.apply[0].script
    assert "$target Bookmarks /R:1" in chrome.apply[0].script and "/E " not in chrome.apply[0].script
    assert desktop.apply[0].ok_codes == migrate.ROBOCOPY_OK and not desktop.admin
    assert shell.ps_quote(str(folder / migrate.extra_spec(r"C:\KeToan").folder)) in extra.apply[0].script
    assert "$target *.pst /R:1" in pst.apply[0].script
    assert not wifi.admin and "key=clear" in wifi.apply[0].script and wifi.category == migrate.CATEGORY
    assert drivers.id == "move.backup_drivers" and "pnputil.exe /export-driver" in drivers.apply[0].script
    assert str(folder / "Driver") in drivers.apply[0].script

    items = [{"id": "desktop"}, {"id": "chrome"}, {"id": "edge"}, {"id": "coccoc"}, {"id": "outlook_data"},
             {"id": "wifi"}, {"id": "drivers"},
             {"id": migrate.extra_spec(r"C:\KeToan").id, "kind": "extra", "source": r"C:\KeToan",
              "folder": r"Khac\C\KeToan"}]
    backup = migrate.Backup(folder, items=items)
    ids = ["desktop", "chrome", "coccoc", "outlook_data", "wifi", "drivers", items[-1]["id"]]
    restore = migrate.restore_actions(backup, ids, "S-1-5-21-0-0-0-9999", r"C:\Users\an")
    assert [action.id for action in restore] == [f"move.restore_{item}" for item in ids]
    assert "/XO /E" in restore[0].apply[0].script and r"C:\Users\an\Desktop" in restore[0].apply[0].script
    script = restore[1].apply[0].script
    assert "Get-Process -Name chrome" in script and "truoc-chuyen" in script and restore[1].apply[0].ok_codes == (0,)
    assert "-like '*CocCoc*'" in restore[2].apply[0].script
    assert "*.pst /XO" in restore[3].apply[0].script and "/E " not in restore[3].apply[0].script
    assert "wlan add profile" in restore[4].apply[0].script and not restore[4].admin
    assert "/add-driver" in restore[5].apply[0].script and restore[5].admin
    assert "$target = 'C:\\KeToan'" in restore[6].apply[0].script and "/XO" in restore[6].apply[0].script
    assert migrate.restore_target(migrate.SPECS["wifi"], r"C:\Users\an", {}) == "Thêm vào Windows"


def test_match_software_uses_names_only():
    apps = [parse_app({"id": "chrome", "name": "Google Chrome", "source": "winget", "winget_id": "Google.Chrome"}),
            parse_app({"id": "7zip", "name": "7-Zip", "source": "winget", "winget_id": "7zip.7zip",
                       "detect": {"uninstall_name": "7-Zip*"}}),
            parse_app({"id": "unikey", "name": "UniKey", "source": "share", "type": "portable", "path": r"{share}\U",
                       "exe": "UniKeyNT.exe"})]
    assert migrate.match_software(["Google Chrome", "7-Zip 24.08 (x64)", "Zalo"], apps) == ["chrome", "7zip"]
    assert migrate.size_text(1536) == "1.5 KB" and migrate.size_text(2 * 1024**3) == "2 GB"
