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
