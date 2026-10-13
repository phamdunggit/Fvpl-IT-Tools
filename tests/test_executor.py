from __future__ import annotations

from dataclasses import replace

import pytest

from fvpl_ittools.actions.loader import parse_action
from fvpl_ittools.core import executor, registry
from fvpl_ittools.core.executor import Level, Status
from fvpl_ittools.core.safety import RestorePointResult
from fvpl_ittools.core.session import UserIdentity

from .conftest import read


def reg_action(key, value=0, **overrides):
    raw = {
        "id": "test.reg", "name": "Đổi registry", "category": "Test", "scope": "user", "admin": False,
        "apply": [{"registry": {"key": key, "name": "Flag", "type": "DWORD", "value": value}}],
    }
    raw.update(overrides)
    return parse_action(raw)


def cmd_action(command="exit /b 0", **overrides):
    raw = {"id": "test.cmd", "name": "Lệnh", "category": "Test", "admin": False, "apply": [{"cmd": command}]}
    raw.update(overrides)
    return parse_action(raw)


@pytest.fixture
def fake_explorer(monkeypatch):
    """Không bao giờ khởi động lại Explorer thật trong test."""
    calls = []
    monkeypatch.setitem(executor.BUILTINS, "restart_explorer", lambda ctx: calls.append(1) or executor.StepOutcome(changed=True))
    return calls


def test_registry_change_is_journaled_and_undone(ctx, test_key):
    batch = executor.run_batch([reg_action(test_key, 0)], ctx)
    result = batch.results[0]
    assert result.status is Status.OK and result.changed
    assert read(test_key, "Flag").value == 0

    entry = ctx.journal.get(result.journal_id)
    assert entry.changes[0].before == registry.MISSING
    assert executor.undo_entry(entry.id, ctx) is True
    assert read(test_key, "Flag") == registry.MISSING
    assert ctx.journal.get(entry.id).undone
    assert executor.undo_entry(entry.id, ctx) is False


def test_undo_restores_previous_value_and_warns_if_changed_since(ctx, test_key):
    path = registry.parse_key(test_key)
    registry.write_value(path, "Flag", registry.TYPES["DWORD"], 7)
    result = executor.run_batch([reg_action(test_key, 0)], ctx).results[0]
    registry.write_value(path, "Flag", registry.TYPES["DWORD"], 9)  # ai đó đổi sau lần chạy
    assert executor.undo_entry(result.journal_id, ctx)
    assert read(test_key, "Flag").value == 7
    assert any(event.level is Level.WARN and "đã bị đổi" in event.text for event in ctx.events)


def test_unchanged_value_is_not_journaled_and_skips_after_hooks(ctx, test_key, fake_explorer):
    registry.write_value(registry.parse_key(test_key), "Flag", registry.TYPES["DWORD"], 0)
    result = executor.run_batch([reg_action(test_key, 0, after=["restart_explorer"])], ctx).results[0]
    assert result.status is Status.OK and not result.changed
    assert result.journal_id is None
    assert fake_explorer == []


def test_after_hooks_run_once_per_batch(ctx, test_key, fake_explorer):
    first = reg_action(test_key, 1, after=["restart_explorer"])
    second = reg_action(test_key + "\\Sub", 1, id="test.reg2", after=["restart_explorer"])
    executor.run_batch([first, second], ctx)
    assert fake_explorer == [1]


def test_partial_failure_still_journals_changes(ctx, test_key):
    action = reg_action(test_key, 1, apply=[
        {"registry": {"key": test_key, "name": "Flag", "type": "DWORD", "value": 1}},
        {"cmd": "exit /b 4"},
    ])
    result = executor.run_batch([action], ctx).results[0]
    assert result.status is Status.FAILED
    assert "mã lỗi 4" in result.message
    assert result.journal_id is not None


def test_exit_codes(ctx):
    assert executor.run_batch([cmd_action("exit /b 2")], ctx).results[0].status is Status.FAILED
    ok = cmd_action("exit /b 2", apply=[{"cmd": "exit /b 2", "ok_codes": [0, 2]}])
    assert executor.run_batch([ok], ctx).results[0].status is Status.OK
    reboot = executor.run_batch([cmd_action("exit /b 3010")], ctx)
    assert reboot.results[0].status is Status.OK and reboot.reboot_required


def test_blocked_actions_are_skipped(ctx, env):
    needs_admin = cmd_action(admin=True)
    old_windows = cmd_action(id="test.old", os={"max_build": 19045})
    batch = executor.run_batch([needs_admin, old_windows], ctx)
    assert [result.status for result in batch.results] == [Status.SKIPPED, Status.SKIPPED]
    assert "quyền admin" in batch.results[0].message
    assert "build 26100" in batch.results[1].message


def test_gpo_managed_action_is_blocked(ctx, test_key):
    policy_key = test_key + "\\Policies"
    action = reg_action(test_key, 1, gpo=[{"key": policy_key, "name": "NoChange"}])
    assert executor.blocked_reason(action, ctx.env) is None
    registry.write_value(registry.parse_key(policy_key), "NoChange", registry.TYPES["DWORD"], 1)
    assert "GPO" in executor.blocked_reason(action, ctx.env)


def test_restore_point_only_for_risky_actions_when_admin(ctx, env):
    calls = []
    ctx.restore_point = lambda description, cancel=None: calls.append(description) or RestorePointResult(True, "ok")
    ctx.env = replace(env, is_admin=True)
    risky = cmd_action(risk="caution", undo="none")
    executor.run_batch([cmd_action()], ctx)
    assert calls == []
    executor.run_batch([risky, cmd_action(id="test.cmd2")], ctx)
    assert len(calls) == 1
    ctx.create_restore_point = False
    executor.run_batch([risky], ctx)
    assert len(calls) == 1


def test_restore_point_skipped_without_admin(ctx):
    calls = []
    ctx.restore_point = lambda description, cancel=None: calls.append(description)
    executor.run_batch([cmd_action(risk="advanced", undo="none")], ctx)
    assert calls == []
    assert any("không chạy bằng quyền admin" in event.text for event in ctx.events)


def test_cancel_before_start_marks_all_cancelled(ctx):
    ctx.cancel.set()
    batch = executor.run_batch([cmd_action(), cmd_action(id="test.cmd2")], ctx)
    assert batch.cancelled
    assert [result.status for result in batch.results] == [Status.CANCELLED, Status.CANCELLED]


def test_check_state(ctx, test_key):
    action = reg_action(test_key, 0, check={"registry": {"key": test_key, "name": "Flag", "on_value": 0}})
    assert executor.check_state(action, ctx.env) is False
    executor.run_batch([action], ctx)
    assert executor.check_state(action, ctx.env) is True


def test_user_scope_targets_logged_on_user_hive(env):
    other = replace(env, process_user=UserIdentity(name="TEST\\admin", sid="S-1-5-21-1-2-3-500"))
    assert str(other.resolve("HKCU\\Software\\X")) == f"HKU\\{env.target_user.sid}\\Software\\X"
    assert str(env.resolve("HKCU\\Software\\X")) == "HKCU\\Software\\X"


def test_preview_lists_commands_without_running(env, test_key):
    lines = executor.preview([cmd_action("ipconfig /flushdns"), reg_action(test_key, 0)], env)
    text = "\n".join(lines)
    assert "ipconfig /flushdns" in text
    assert f'reg add "{test_key}" /v "Flag" /t REG_DWORD /d "0" /f' in text
    assert read(test_key, "Flag") == registry.MISSING


def test_undo_steps(ctx):
    action = cmd_action(undo=[{"cmd": "exit /b 0"}])
    result = executor.run_undo_steps(action, ctx)
    assert result.status is Status.OK
    assert result.action.name.startswith("Hoàn tác:")


def test_secrets_are_masked_in_events(ctx):
    from fvpl_ittools.core import log
    log.register_secret("p@ss-123")
    try:
        executor.run_batch([cmd_action("echo p@ss-123")], ctx)
    finally:
        log.forget_secret("p@ss-123")
    assert not any("p@ss-123" in event.text for event in ctx.events)
    assert any(log.MASK in event.text for event in ctx.events)


def test_stop_on_error_skips_remaining_actions(ctx):
    actions = [cmd_action(id="test.a"), cmd_action("exit /b 5", id="test.b"), cmd_action(id="test.c")]
    batch = executor.run_batch(actions, ctx, stop_on_error=True)
    assert [result.status for result in batch.results] == [Status.OK, Status.FAILED, Status.SKIPPED]
    assert "Dừng vì" in batch.results[2].message
    keep_going = executor.run_batch(actions, ctx)
    assert keep_going.results[2].status is Status.OK


def test_exit_code_messages_explain_failure(ctx):
    action = cmd_action(apply=[{"cmd": "exit /b 3", "messages": {3: "Ổ đĩa có lỗi, cần chạy chkdsk /f"}}])
    result = executor.run_batch([action], ctx).results[0]
    assert result.status is Status.FAILED
    assert result.message == "Ổ đĩa có lỗi, cần chạy chkdsk /f (mã 3)"


def test_requires_domain(ctx, env):
    action = cmd_action(requires_domain=True)
    assert executor.blocked_reason(action, env) == "Máy chưa vào domain"
    assert executor.blocked_reason(action, replace(env, joined_domain=True)) is None


def ps_action(script, **overrides):
    raw = {"id": "test.ps", "name": "PowerShell", "category": "Test", "admin": False, "apply": [{"powershell": script}]}
    raw.update(overrides)
    return parse_action(raw)


def test_credential_is_passed_and_masked(ctx):
    action = ps_action(
        "Write-Output ($Credential.UserName + ' ' + $Credential.GetNetworkCredential().Password)",
        needs_credential="domain",
    )
    skipped = executor.run_batch([action], ctx).results[0]
    assert skipped.status is Status.SKIPPED and "tài khoản" in skipped.message

    ctx.credential = ("CORP\\join", "Bí-mật-123")
    result = executor.run_batch([action], ctx).results[0]
    assert result.status is Status.OK
    text = "\n".join(event.text for event in ctx.events)
    assert "CORP\\join ******" in text
    assert "Bí-mật-123" not in text
    from fvpl_ittools.core import log
    assert log.mask("Bí-mật-123") == "Bí-mật-123"  # chỉ che trong lượt chạy, xong thì quên


def test_credential_not_sent_to_actions_that_do_not_need_it(ctx):
    ctx.credential = ("CORP\\join", "secret")
    action = ps_action("if (Get-Variable Credential -ErrorAction SilentlyContinue) { exit 9 }")
    assert executor.run_batch([action], ctx).results[0].status is Status.OK


def test_powershell_gets_target_user_variables(ctx, state_dir):
    action = ps_action("Write-Output \"$TargetUserName|$TargetUserSid|$ReportDir\"")
    executor.run_batch([action], ctx)
    expected = f"TEST\\it|S-1-5-21-1-2-3-1001|{state_dir / 'reports'}"
    assert any(event.text == expected for event in ctx.events)


def test_describe_includes_used_variables_only(env):
    text = executor.describe_action(ps_action("Get-ChildItem $TargetUserProfile"), env)
    assert "$TargetUserProfile = ''" in text
    assert "$TargetUserSid" not in text


def test_check_helpers_only_in_full_description(env):
    action = ps_action("if (Test-Port dc 389) { Write-Ok 'ldap' }")
    short = executor.describe_action(action, env)
    full = executor.describe_action(action, env, full=True)
    assert "function Test-Port" not in short and "nút Copy lệnh" in short
    assert "function Test-Port" in full
    assert "function" not in executor.describe_action(ps_action("Get-Date"), env, full=True)
