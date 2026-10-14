from __future__ import annotations

import json
from pathlib import Path

import pytest

from fvpl_ittools.core import updates


def test_version_compare():
    assert updates.version_key("1.2") == (1, 2, 0, 0)
    assert updates.is_newer("1.0.0", "0.2.0") and updates.is_newer("0.10.0", "0.9.9")
    assert not updates.is_newer("0.2.0", "0.2.0") and not updates.is_newer("1.0.0-rc1", "1.0.0")


def test_release_dir_prefers_site_setting():
    assert updates.release_dir(r"\\srv\IT$\Releases", r"F:\SOFT") == Path(r"\\srv\IT$\Releases")
    assert updates.release_dir("", r"F:\SOFT") == Path(r"F:\SOFT") / "ITTools"
    assert updates.release_dir("", "") is None


def test_check_reads_version_json(tmp_path):
    assert updates.check(tmp_path, "0.2.0") is None  # chưa có version.json
    (tmp_path / updates.VERSION_FILE).write_text(json.dumps(updates.manifest(
        "1.0.0", "2026-10-20", "FVPL-ITTools-v1.0.0", "FVPL-ITTools-v1.0.0.zip", ["Bản 1.0"])), encoding="utf-8")
    release = updates.check(tmp_path, "0.2.0")
    assert release.version == "1.0.0" and release.folder == tmp_path / "FVPL-ITTools-v1.0.0"
    assert release.zip == tmp_path / "FVPL-ITTools-v1.0.0.zip" and release.notes == ("Bản 1.0",)
    assert updates.check(tmp_path, "1.0.0") is None
    assert updates.check(None, "0.2.0") is None
    (tmp_path / updates.VERSION_FILE).write_text("{hỏng", encoding="utf-8")
    with pytest.raises(updates.UpdateError, match="sai định dạng"):
        updates.check(tmp_path, "0.2.0")
    (tmp_path / updates.VERSION_FILE).write_text("{}", encoding="utf-8")
    with pytest.raises(updates.UpdateError, match="version"):
        updates.check(tmp_path, "0.2.0")
