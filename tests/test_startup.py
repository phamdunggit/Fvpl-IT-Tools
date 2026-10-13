from __future__ import annotations

import struct
from dataclasses import replace

import pytest

from fvpl_ittools.actions.model import RegistryStep, Scope
from fvpl_ittools.cleanup import startup
from fvpl_ittools.core import executor, registry
from fvpl_ittools.core.executor import Status
from fvpl_ittools.core.session import UserIdentity

from .conftest import read


@pytest.mark.parametrize("data, enabled", [
    (None, True), (b"", True), (bytes([2]) + bytes(11), True), (bytes([6]) + bytes(11), True),
    (bytes([3]) + bytes(11), False), (bytes([7]) + bytes(11), False), (5, True),
])
def test_is_enabled(data, enabled):
    assert startup.is_enabled(data) is enabled


def test_approval_value():
    assert startup.approval_value(True) == bytes([2]) + bytes(11)
    disabled = startup.approval_value(False, now=0)
    assert len(disabled) == 12 and disabled[:4] == bytes([3, 0, 0, 0])
    assert struct.unpack("<Q", disabled[4:])[0] == 116444736000000000  # 1/1/1970 tính theo FILETIME


def entry(approved_key, enabled=True, name="Spotify"):
    return startup.StartupEntry(name, r"C:\Spotify\Spotify.exe", "Người dùng (Run)", approved_key, enabled)


def test_toggle_action_shape():
    user = startup.toggle_action(entry(r"HKCU\Software\X\StartupApproved\Run"), enable=False)
    step = user.apply[0]
    assert isinstance(step, RegistryStep) and step.type == "BINARY" and step.value[0] == 3
    assert user.scope is Scope.USER and not user.admin
    assert user.name == "Tắt khởi động cùng Windows: Spotify"
    machine = startup.toggle_action(entry(r"HKLM\Software\X\StartupApproved\Run"), enable=True)
    assert machine.scope is Scope.MACHINE and machine.admin and machine.apply[0].value[0] == 2


def test_toggle_runs_journals_and_undoes(ctx, test_key):
    action = startup.toggle_action(entry(test_key), enable=False)
    result = executor.run_batch([action], ctx).results[0]
    assert result.status is Status.OK
    assert not startup.is_enabled(read(test_key, "Spotify").value)
    assert executor.undo_entry(result.journal_id, ctx)
    assert read(test_key, "Spotify") == registry.MISSING  # trước đó chưa có giá trị = đang bật


def test_entries_reads_run_keys_and_startup_folders(env, tmp_path, monkeypatch):
    profile = tmp_path / "nva"
    user_folder = profile / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    user_folder.mkdir(parents=True)
    (user_folder / "Tool.lnk").write_text("x")
    (user_folder / "desktop.ini").write_text("x")
    common = tmp_path / "ProgramData"
    monkeypatch.setenv("ProgramData", str(common))
    target_env = replace(env, target_user=UserIdentity(name="CORP\\nva", sid=env.target_user.sid, profile_path=str(profile)))

    def fake_values(root, subkey, view=0):
        if subkey.endswith(r"StartupApproved\Run"):
            return [("Spotify", bytes([3]) + bytes(11))]
        if subkey.endswith(r"StartupApproved\StartupFolder"):
            return [("tool.lnk", bytes([3]) + bytes(11))]
        if subkey.endswith("CurrentVersion\\Run") and view == 0:
            return [("", "mặc định"), ("Spotify", r"C:\Spotify.exe"), ("Zalo", r"C:\Zalo.exe")]
        return []

    monkeypatch.setattr(startup, "_values", fake_values)
    found = {(item.source, item.name): item for item in startup.entries(target_env)}
    assert not found[("Người dùng (Run)", "Spotify")].enabled
    assert found[("Người dùng (Run)", "Zalo")].enabled
    folder_item = found[("Người dùng (thư mục Startup)", "Tool.lnk")]
    assert not folder_item.enabled and folder_item.approved_key.endswith("StartupFolder")
    assert not any(name == "desktop.ini" or name == "" for _, name in found)


def test_entries_on_this_machine_reads_only(env):
    assert all(isinstance(item, startup.StartupEntry) for item in startup.entries(env))
