"""Dọn rác: chỉ thao tác trên thư mục tạm của test, không xoá gì thật trên máy."""

from __future__ import annotations

import _winapi
import os
import stat
import threading
import time
from dataclasses import replace

import pytest

from fvpl_ittools.cleanup import junk
from fvpl_ittools.core.session import UserIdentity

OLD = time.time() - 3 * 24 * 3600


def make(path, size=10, old=True):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    if old:
        os.utime(path, (OLD, OLD))
    return path


@pytest.fixture
def tree(tmp_path):
    """Thư mục rác mẫu, kèm một junction trỏ ra dữ liệu nằm ngoài mà tuyệt đối không được xoá."""
    root = tmp_path / "Temp"
    make(root / "old.tmp", 100)
    make(root / "new.tmp", 50, old=False)
    make(root / "sub" / "deep" / "old.log", 30)
    readonly = make(root / "readonly.tmp", 20)
    os.chmod(readonly, stat.S_IREAD)
    make(root / "desktop.ini", 5)
    outside = make(tmp_path / "Documents" / "important.docx", 1000)
    _winapi.CreateJunction(str(tmp_path / "Documents"), str(root / "link-to-documents"))
    return root, outside


def category(**overrides):
    values = dict(id="t", name="Thử", description="x")
    values.update(overrides)
    return junk.Category(**values)


def test_measure_skips_junctions_new_files_and_keep(tree):
    root, _ = tree
    size, files, readable = junk._measure(root, junk.DAY, ("desktop.ini",), time.time())
    assert (size, files, readable) == (150, 3, True)  # old.tmp + old.log + readonly.tmp
    size, files, _ = junk._measure(root, 0, (), time.time())
    assert (size, files) == (205, 5)


def test_clean_keeps_new_files_and_never_follows_junctions(tree):
    root, outside = tree
    stats = junk.clean_locations(category(min_age=junk.DAY, keep=("desktop.ini",)), [root], threading.Event())
    assert (stats.freed, stats.deleted, stats.failed) == (150, 3, 0)
    assert outside.exists(), "file nằm ngoài qua junction đã bị xoá!"
    assert (root / "link-to-documents").exists()
    assert (root / "new.tmp").exists() and (root / "desktop.ini").exists()
    assert not (root / "sub").exists()  # thư mục con rỗng được xoá
    assert root.exists()  # thư mục gốc giữ nguyên


def test_clean_root_junction_is_ignored(tmp_path):
    target = make(tmp_path / "data" / "keep.txt")
    _winapi.CreateJunction(str(tmp_path / "data"), str(tmp_path / "Temp"))
    stats = junk.clean_locations(category(), [tmp_path / "Temp"], threading.Event())
    assert stats.deleted == 0 and target.exists()
    assert junk._measure(tmp_path / "Temp", 0, (), time.time()) == (0, 0, True)


def test_clean_single_file_and_missing_paths(tmp_path):
    dump = make(tmp_path / "MEMORY.DMP", 70)
    stats = junk.clean_locations(category(), [dump, tmp_path / "khong-co"], threading.Event())
    assert stats.freed == 70 and not dump.exists()


def test_locked_file_is_counted_as_failed(tmp_path):
    locked = make(tmp_path / "Temp" / "locked.tmp", 10)
    with open(locked, "rb"):
        stats = junk.clean_locations(category(), [tmp_path / "Temp"], threading.Event())
    assert stats.failed == 1 and locked.exists()


def test_cancel_stops_cleaning(tree):
    root, _ = tree
    cancel = threading.Event()
    cancel.set()
    assert junk.clean_locations(category(), [root], cancel).deleted == 0


def test_locations_use_target_user(env):
    user = UserIdentity(name="CORP\\nva", sid="S-1-5-21-9", profile_path=r"C:\Users\nva")
    target_env = replace(env, target_user=user)
    assert junk.locations(junk.CATEGORY_BY_ID["user_temp"], target_env) == [
        junk.Path(r"C:\Users\nva\AppData\Local\Temp")]
    bins = junk.locations(junk.CATEGORY_BY_ID["recycle_bin"], target_env)
    assert bins and all(path.name == "S-1-5-21-9" and path.parent.name == "$Recycle.Bin" for path in bins)
    no_profile = replace(env, target_user=UserIdentity(name="x", sid="S-1"))
    assert junk.locations(junk.CATEGORY_BY_ID["user_temp"], no_profile) == []
    assert all(junk.locations(item, target_env) is not None for item in junk.CATEGORIES)


def test_clean_runs_categories_and_restarts_services(ctx, tmp_path, monkeypatch):
    make(tmp_path / "a" / "x.tmp", 40)
    make(tmp_path / "b" / "y.tmp", 60)
    first = category(id="a", name="A", services=("wuauserv",))
    second = category(id="b", name="B")
    monkeypatch.setattr(junk, "locations", lambda item, env: [tmp_path / item.id])
    calls = []
    monkeypatch.setattr(junk, "_set_services", lambda names, start, ctx: calls.append((names, start)))
    result = junk.clean([first, second], ctx)
    assert result.freed == 100 and not result.cancelled
    assert calls == [(("wuauserv",), False), (("wuauserv",), True)]
    text = "\n".join(event.text for event in ctx.events)
    assert "giải phóng 100 B" in text


def test_cleanmgr_category_reports_freed_space(ctx, monkeypatch):
    sizes = iter([junk.Scan(junk.CATEGORY_BY_ID["windows_old"], 5000, 9), junk.Scan(junk.CATEGORY_BY_ID["windows_old"], 1000, 2)])
    monkeypatch.setattr(junk, "scan", lambda item, env, cancel=None: next(sizes))
    monkeypatch.setattr(junk, "_run_cleanmgr", lambda item, ctx: "")
    stats = junk.clean_category(junk.CATEGORY_BY_ID["windows_old"], ctx)
    assert (stats.freed, stats.deleted) == (4000, 7)


def test_one_failing_category_does_not_stop_others(ctx, tmp_path, monkeypatch):
    make(tmp_path / "b" / "y.tmp", 60)
    monkeypatch.setattr(junk, "locations", lambda item, env: [tmp_path / item.id])
    original = junk.clean_locations

    def broken(item, paths, cancel):
        if item.id == "a":
            raise RuntimeError("hỏng")
        return original(item, paths, cancel)

    monkeypatch.setattr(junk, "clean_locations", broken)
    result = junk.clean([category(id="a", name="A"), category(id="b", name="B")], ctx)
    assert [item.message for item in result.results] == ["hỏng", ""]
    assert result.freed == 60


def test_browser_cache_paths_only_cache_folders(tmp_path):
    chrome = tmp_path / "Google" / "Chrome" / "User Data"
    for profile in ("Default", "Profile 1", "System Profile", "Crashpad"):
        (chrome / profile).mkdir(parents=True)
    (chrome / "Default" / "Login Data").write_text("mật khẩu", encoding="utf-8")
    paths = junk.browser_cache_paths(tmp_path)
    names = {str(path.relative_to(chrome)) for path in paths}
    assert "Default\\Cache" in names and "Profile 1\\GPUCache" in names and "ShaderCache" in names
    assert not any(name.startswith(("System Profile", "Crashpad")) for name in names)
    assert not any("Login Data" in name or "Bookmarks" in name or "Cookies" in name for name in names)
    assert junk.browser_cache_paths(tmp_path / "khong-co") == []


@pytest.mark.parametrize("size, text", [(0, "0 B"), (900, "900 B"), (2048, "2 KB"), (5 * 1024**2, "5,0 MB"),
                                        (int(3.46 * 1024**3), "3,5 GB")])
def test_size_text(size, text):
    assert junk.size_text(size) == text


def test_scan_all_on_this_machine_reads_only(env):
    scans = junk.scan_all(env)
    assert [scan.category.id for scan in scans] == [item.id for item in junk.CATEGORIES]
    assert all(scan.size >= 0 for scan in scans)
