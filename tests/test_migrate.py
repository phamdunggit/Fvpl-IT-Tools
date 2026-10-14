from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from fvpl_ittools.core import migrate, shell
from fvpl_ittools.software.catalog import parse_app


def test_item_paths_follow_user_shell_folders():
    profile = r"C:\Users\an"
    folders = {"Personal": r"%USERPROFILE%\OneDrive\Documents", "Desktop": r"D:\Data\Desktop"}
    assert migrate.item_path(migrate.SPECS["documents"], profile, folders) == r"C:\Users\an\OneDrive\Documents"
    assert migrate.item_path(migrate.SPECS["desktop"], profile, folders) == r"D:\Data\Desktop"
    assert migrate.item_path(migrate.SPECS["pictures"], profile, {}) == r"C:\Users\an\Pictures"
    assert migrate.item_path(migrate.SPECS["chrome"], profile, {}).endswith(r"Google\Chrome\User Data\Default")
    assert migrate.expand_profile(r"%LOCALAPPDATA%\x", profile) == r"C:\Users\an\AppData\Local\x"


def test_measure_counts_files_recursively(tmp_path):
    (tmp_path / "a" / "b").mkdir(parents=True)
    (tmp_path / "a" / "one.txt").write_bytes(b"12345")
    (tmp_path / "a" / "b" / "two.txt").write_bytes(b"123")
    assert migrate.measure(str(tmp_path)) == (8, 2)
    assert migrate.measure(str(tmp_path / "khong-co")) == (0, 0)


def _sources(tmp_path: Path) -> list[migrate.Source]:
    return [migrate.Source(migrate.SPECS["desktop"], str(tmp_path / "Desktop"), True, 10, 2),
            migrate.Source(migrate.SPECS["chrome"], str(tmp_path / "Chrome"), True, 5, 1)]


def test_manifest_round_trip_and_listing(tmp_path):
    root = tmp_path / migrate.FOLDER
    old = migrate.new_backup_folder(root, "FVPL-KT05", "CORP\\an", datetime(2026, 10, 1, 9, 0))
    new = migrate.new_backup_folder(root, "FVPL KT06", "CORP\\binh", datetime(2026, 10, 2, 9, 0))
    assert old.name == "FVPL-KT05_an_20261001_0900" and new.name == "FVPL-KT06_binh_20261002_0900"
    migrate.write_manifest(old, "FVPL-KT05", "CORP\\an", "0.2.0", _sources(tmp_path),
                           [{"name": "HP", "where": "10.0.0.5"}], ["Zalo", "Google Chrome", "Zalo"])
    backup = migrate.read_backup(old)
    assert backup.computer == "FVPL-KT05" and [item["id"] for item in backup.items] == ["desktop", "chrome"]
    assert backup.software == ["Google Chrome", "Zalo"] and backup.printers[0]["where"] == "10.0.0.5"
    (root / "rac").mkdir()
    assert [item.folder for item in migrate.list_backups(root)] == [old]
    assert migrate.list_backups(None) == [] and migrate.list_backups(tmp_path / "khong-co") == []
    (old / migrate.MANIFEST).write_text(json.dumps({"x": 1}), encoding="utf-8")
    assert migrate.list_backups(root) == []  # manifest hỏng thì bỏ qua


def test_backup_and_restore_scripts(tmp_path):
    folder = tmp_path / "backup"
    desktop, chrome = migrate.backup_actions(_sources(tmp_path), folder)
    assert desktop.id == "move.backup_desktop" and "& robocopy $source $target /E" in desktop.apply[0].script
    assert shell.ps_quote(str(folder / "Desktop")) in desktop.apply[0].script
    assert "$target Bookmarks /R:1" in chrome.apply[0].script and "/E " not in chrome.apply[0].script
    assert desktop.apply[0].ok_codes == migrate.ROBOCOPY_OK and not desktop.admin
    backup = migrate.Backup(folder, items=[{"id": "desktop"}, {"id": "chrome"}, {"id": "edge"}])
    restore = migrate.restore_actions(backup, ["desktop", "chrome"], "S-1-5-21-0-0-0-9999", r"C:\Users\an")
    assert [action.id for action in restore] == ["move.restore_desktop", "move.restore_chrome"]
    assert "/XO /E" in restore[0].apply[0].script and r"C:\Users\an\Desktop" in restore[0].apply[0].script
    script = restore[1].apply[0].script
    assert "Get-Process -Name chrome" in script and "truoc-chuyen" in script and restore[1].apply[0].ok_codes == (0,)


def test_match_software_uses_names_only():
    apps = [parse_app({"id": "chrome", "name": "Google Chrome", "source": "winget", "winget_id": "Google.Chrome"}),
            parse_app({"id": "7zip", "name": "7-Zip", "source": "winget", "winget_id": "7zip.7zip",
                       "detect": {"uninstall_name": "7-Zip*"}}),
            parse_app({"id": "unikey", "name": "UniKey", "source": "share", "type": "portable", "path": r"{share}\U",
                       "exe": "UniKeyNT.exe"})]
    assert migrate.match_software(["Google Chrome", "7-Zip 24.08 (x64)", "Zalo"], apps) == ["chrome", "7zip"]
    assert migrate.size_text(1536) == "1.5 KB" and migrate.size_text(2 * 1024**3) == "2 GB"
