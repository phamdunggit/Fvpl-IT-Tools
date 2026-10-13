from __future__ import annotations

import os

import pytest

from fvpl_ittools.actions.model import CmdStep, PowerShellStep
from fvpl_ittools.core import executor
from fvpl_ittools.ui.pages import utilities


@pytest.mark.parametrize("host", ["8.8.8.8", "www.microsoft.com", "PC-01", "fe80::1", "dc01.corp.example"])
def test_valid_hosts(host):
    assert utilities.valid_host(host)


@pytest.mark.parametrize("host", ["", "8.8.8.8 & del x", "a|b", "-t", "x\"y", "máy-in", "a b", "a;b", "%PATH%"])
def test_hosts_that_could_inject_commands_are_rejected(host):
    assert not utilities.valid_host(host)
    with pytest.raises(ValueError):
        utilities.network_action("ping", host)


def test_network_actions_build_expected_commands(env):
    assert utilities.network_action("ping", "8.8.8.8").apply == (
        CmdStep(command="ping -n 4 8.8.8.8", messages=((1, "Không ping được"),)),
    )
    assert utilities.network_action("tracert", "8.8.8.8").apply[0].command == "tracert -d -h 20 -w 1000 8.8.8.8"
    port = utilities.network_action("port", "dc01.corp.example", 389)
    assert isinstance(port.apply[0], PowerShellStep)
    assert "$target = 'dc01.corp.example'" in port.apply[0].script
    assert "function Test-Port" in executor.describe_action(port, env, full=True)


def test_port_check_runs_for_real(ctx):
    closed = utilities.network_action("port", "127.0.0.1", 1)
    result = executor.run_batch([closed], ctx).results[0]
    assert result.status.value == "failed"
    assert result.message == "Cổng không mở hoặc bị chặn (mã 2)"


def test_shortcuts_resolve_to_existing_tools():
    resolved = {item.name: utilities.resolve(item) for items in utilities.SHORTCUTS.values() for item in items}
    for name in ("Control Panel", "Computer Management", "Services", "Device Manager", "Network Connections",
                 "Registry Editor"):
        command = resolved[name]
        assert command is not None and os.path.exists(command[0]), name
    assert resolved["Services"][1].lower().endswith("services.msc")
    assert resolved["Windows Update"] == ["ms-settings:windowsupdate"]
    missing = utilities.Shortcut("Không có", ("mmc.exe", "khong-co.msc"))
    assert utilities.resolve(missing) is None
