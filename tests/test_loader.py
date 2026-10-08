from __future__ import annotations

import pytest

from fvpl_ittools.actions import loader
from fvpl_ittools.actions.model import BUILTIN_NAMES, CmdStep, RegistryStep, Risk, Scope, UndoMode
from fvpl_ittools.core import executor

HKCU_KEY = r"HKCU\Software\X"


def base(**overrides):
    raw = {"id": "test.sample", "name": "Mẫu", "category": "Test", "apply": [{"cmd": "echo ok"}]}
    raw.update(overrides)
    return raw


def test_bundled_actions_load_without_errors():
    actions, errors = loader.load_builtin_actions()
    assert errors == []
    assert {action.id for action in actions} >= {"net.flush_dns", "sys.restart_explorer", "ui.show_file_ext"}


def test_every_builtin_has_an_implementation():
    assert set(BUILTIN_NAMES) == set(executor.BUILTINS)


def test_defaults():
    action = loader.parse_action(base())
    assert action.page == "fixes"
    assert action.risk is Risk.SAFE
    assert action.scope is Scope.MACHINE
    assert action.admin is True
    assert action.undo_mode is UndoMode.NONE
    assert action.apply == (CmdStep(command="echo ok"),)


def test_registry_step_defaults_to_auto_undo_and_coerces_value():
    action = loader.parse_action(base(
        scope="user",
        apply=[{"registry": {"key": HKCU_KEY, "name": "A", "type": "dword", "value": "0x10"}}],
    ))
    assert action.undo_mode is UndoMode.AUTO
    step = action.apply[0]
    assert isinstance(step, RegistryStep)
    assert step.type == "DWORD" and step.value == 16


@pytest.mark.parametrize("overrides, message", [
    ({"descripton": "x"}, "không hiểu khoá descripton"),
    ({"id": "NoDot"}, "id phải có dạng"),
    ({"name": ""}, "thiếu 'name'"),
    ({"risk": "high"}, "'risk' chỉ nhận"),
    ({"apply": []}, "thiếu 'apply'"),
    ({"apply": [{"cmd": "a", "powershell": "b"}]}, "cần đúng một"),
    ({"apply": [{"builtin": "format_c"}]}, "builtin 'format_c' không có"),
    ({"risk": "caution"}, "phải khai báo 'undo'"),
    ({"undo": "auto"}, "undo: auto chỉ dùng được khi có bước registry"),
    ({"apply": [{"registry": {"key": HKCU_KEY, "name": "A", "type": "DWORD", "value": 1}}]}, "phải khai báo scope: user"),
    ({"scope": "user", "apply": [{"registry": {"key": r"HKLM\Software\X", "name": "A", "type": "DWORD", "value": 1}}]},
     "chỉ được ghi HKCU"),
    ({"scope": "user", "apply": [{"registry": {"key": HKCU_KEY, "name": "A", "type": "DWORD", "value": "abc"}}]},
     "DWORD cần số"),
    ({"apply": [{"registry": {"key": r"HKU\S-1\X", "name": "A", "type": "DWORD", "value": 1}}]}, "không ghi thẳng HKU"),
    ({"apply": [{"service": {"name": "Spooler", "action": "restart", "startup": "manual"}}]}, "chưa hỗ trợ đổi kiểu khởi động"),
    ({"os": {"min_build": "19045"}}, "os.min_build phải là số build"),
    ({"admin": "yes"}, "'admin' phải là true hoặc false"),
    ({"check": {"registry": {"key": HKCU_KEY, "name": "A", True: 0}}}, "check.registry cần đủ key, name, on_value"),
])
def test_invalid_actions_are_rejected_with_clear_message(overrides, message):
    with pytest.raises(loader.ActionError, match=message):
        loader.parse_action(base(**overrides))


def test_load_files_reports_errors_and_keeps_valid_actions(tmp_path):
    file = tmp_path / "mix.yaml"
    file.write_text(
        "- id: a.ok\n  name: Được\n  category: T\n  apply: [{cmd: echo 1}]\n"
        "- id: a.bad\n  name: Hỏng\n  category: T\n"
        "- id: a.ok\n  name: Trùng\n  category: T\n  apply: [{cmd: echo 2}]\n",
        encoding="utf-8",
    )
    actions, errors = loader.load_action_files([file])
    assert [action.id for action in actions] == ["a.ok"]
    assert len(errors) == 2
    assert "mix.yaml mục 2 (a.bad)" in errors[0]
    assert "trùng id" in errors[1]


def test_supports_build():
    action = loader.parse_action(base(os={"min_build": 22000, "max_build": 26100}))
    assert not action.supports_build(19045)
    assert action.supports_build(22631)
    assert not action.supports_build(26200)
