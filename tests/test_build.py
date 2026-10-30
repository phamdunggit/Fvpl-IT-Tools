"""Script đóng gói: chỉ kiểm tra lệnh ký số dựng ra, không build, không ký thật."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("build_script", ROOT / "packaging" / "build.py")
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


def test_sign_commands_use_sha256_and_timestamp():
    sign, verify = build.sign_commands(Path("signtool.exe"), Path("dist/FVPL-ITTools.exe"), "AB CD 12", "http://ts")
    assert sign[1:5] == ["sign", "/sha1", "ABCD12", "/fd"] and "SHA256" in sign
    assert sign[sign.index("/tr") + 1] == "http://ts" and sign[sign.index("/td") + 1] == "SHA256"
    assert verify[1:3] == ["verify", "/pa"]


def test_sign_is_skipped_without_thumbprint(monkeypatch, capsys):
    monkeypatch.delenv(build.SIGN_THUMBPRINT, raising=False)
    assert build.sign(Path("FVPL-ITTools.exe")) is False
    assert "Chưa ký số" in capsys.readouterr().out


def test_sha256_of_exe(tmp_path):
    file = tmp_path / "a.exe"
    file.write_bytes(b"abc")
    assert build.sha256(file) == "BA7816BF8F01CFEA414140DE5DAE2223B00361A396177A9CB410FF61F20015AD"


def test_find_signtool_honours_override(monkeypatch, tmp_path):
    tool = tmp_path / "signtool.exe"
    tool.write_bytes(b"")
    monkeypatch.setenv(build.SIGNTOOL, str(tool))
    assert build.find_signtool() == tool
    monkeypatch.setenv(build.SIGNTOOL, str(tmp_path / "khong-co.exe"))
    assert build.find_signtool() is None

def test_kept_items_survive_a_rebuild(tmp_path):
    folder, stash = tmp_path / "FVPL-ITTools", tmp_path / ".keep"
    (folder / "SOFT" / "config").mkdir(parents=True)
    (folder / "SOFT" / "Office.iso").write_bytes(b"iso")
    (folder / "site.yaml").write_text("domain: x", encoding="utf-8")
    (folder / "license-keys.json").write_text("{}", encoding="utf-8")
    (folder / "FVPL-ITTools.exe").write_bytes(b"old")
    moved = build.stash_kept(folder, stash)
    assert sorted(moved) == ["SOFT", "license-keys.json", "site.yaml"]
    assert [item.name for item in folder.iterdir()] == ["FVPL-ITTools.exe"]  # what goes into the zip
    import shutil
    shutil.rmtree(folder)  # PyInstaller --noconfirm wipes the output folder
    folder.mkdir()
    build.restore_kept(folder, stash)
    assert (folder / "SOFT" / "Office.iso").read_bytes() == b"iso"
    assert (folder / "site.yaml").is_file() and not stash.exists()


def test_interrupted_build_restores_kept_items_first(tmp_path):
    folder, stash = tmp_path / "FVPL-ITTools", tmp_path / ".keep"
    (stash / "SOFT").mkdir(parents=True)  # left over from a build that was killed
    folder.mkdir()
    assert build.stash_kept(folder, stash) == ["SOFT"]
    assert (stash / "SOFT").is_dir() and not (folder / "SOFT").exists()
    build.restore_kept(folder, stash)
    assert (folder / "SOFT").is_dir()
