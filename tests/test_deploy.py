"""Script chép tool ra USB / SSD: chỉ kiểm tra lệnh dựng ra, không chép gì."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("deploy", ROOT / "packaging" / "deploy.py")
deploy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)


def test_usb_copies_tool_and_site_without_soft():
    steps = deploy.commands("usb", Path("E:\\"), Path("D:\\Kho"), ROOT / "site.yaml")
    assert len(steps) == 3
    assert steps[0][2] == "E:\\FVPL-ITTools\\_internal" and "/MIR" in steps[0]
    assert steps[1][3] == "FVPL-ITTools.exe" and "/MIR" not in steps[1]
    assert steps[2][3] == "site.yaml"
    assert not any("SOFT" in part for step in steps for part in step)


def test_ssd_adds_soft_without_deleting():
    steps = deploy.commands("ssd", Path("F:\\"), Path("D:\\Kho"), None)
    soft = steps[-1]
    assert soft[1:3] == ["D:\\Kho", "F:\\FVPL-ITTools\\SOFT"]
    assert "/E" in soft and "/MIR" not in soft
    assert not any(step[-1] == "site.yaml" or "site.yaml" in step for step in steps)


def test_share_publishes_versioned_folder_zip_and_manifest():
    import datetime
    steps = deploy.commands("share", Path("S:/ITTools"), Path("D:/Kho"), None, "1.0.0")
    assert steps[0][2].endswith("FVPL-ITTools-v1.0.0") and "/MIR" in steps[0]
    assert steps[1][3] == "FVPL-ITTools-v1.0.0.zip" and not any("SOFT" in part for step in steps for part in step)
    manifest = deploy.release_manifest("1.0.0", [], datetime.date(2026, 10, 20))
    assert manifest == {"version": "1.0.0", "date": "2026-10-20", "folder": "FVPL-ITTools-v1.0.0",
                        "zip": "FVPL-ITTools-v1.0.0.zip", "notes": ["Xem CHANGELOG.md trong repo"]}
    assert deploy.read_version()
