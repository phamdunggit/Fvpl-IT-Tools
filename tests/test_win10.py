"""Guards that keep the tool running on Windows 10 (docs/KE-HOACH-WIN10.md)."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import PySide6

from fvpl_ittools.__main__ import MIN_WINDOWS_BUILD, windows_too_old
from fvpl_ittools.actions import loader
from fvpl_ittools.actions.model import PowerShellStep

ROOT = Path(__file__).resolve().parent.parent
WIN11_FIRST_BUILD = 22000

# Cmdlets that some Windows 10 machines do not have (Home edition, missing updates): a script must check with
# Get-Command before calling them, so the user gets a Vietnamese explanation instead of a raw PowerShell error.
OPTIONAL_CMDLETS = ("Get-BitLockerVolume", "Get-LapsADPassword", "Invoke-LapsPolicyProcessing",
                    "Set-LapsADPasswordExpirationTime")


def test_qt_stays_on_a_release_that_supports_windows_10():
    major, minor = (int(part) for part in PySide6.__version__.split(".")[:2])
    assert (major, minor) < (6, 13), "Qt 6.13+ không chạy trên Windows 10"
    dependencies = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["dependencies"]
    assert any(dep.replace(" ", "").startswith("PySide6") and "<6.13" in dep for dep in dependencies)


def test_old_windows_gets_a_clear_message():
    assert MIN_WINDOWS_BUILD == 17763
    assert windows_too_old(19045) is None  # Win10 22H2
    assert windows_too_old(17763) is None  # Win10 1809
    message = windows_too_old(17134)       # Win10 1803
    assert message and "17134" in message and "1809" in message


def test_windows_11_only_actions_are_hidden_on_windows_10():
    actions, errors = loader.load_builtin_actions()
    assert errors == []
    for action in actions:
        if re.search(r"\(Win11\)", action.name):
            assert action.min_build is not None and action.min_build >= WIN11_FIRST_BUILD, action.id


def test_optional_cmdlets_are_checked_before_use():
    # Only apply steps: undo runs after apply succeeded, so the cmdlet is known to exist there.
    guard = re.compile(rf"Get-Command\s+({'|'.join(OPTIONAL_CMDLETS)})\b")
    actions, _ = loader.load_builtin_actions()
    for action in actions:
        for step in action.apply:
            if not isinstance(step, PowerShellStep):
                continue
            used = [cmdlet for cmdlet in OPTIONAL_CMDLETS if re.search(rf"\b{cmdlet}\b", guard.sub("", step.script))]
            assert not used or guard.search(step.script), f"{action.id}: kiểm tra Get-Command trước khi gọi {used}"
