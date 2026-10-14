from __future__ import annotations

from fvpl_ittools.actions.model import Risk, Scope, UndoMode
from fvpl_ittools.core import envpath


def test_analyze_marks_missing_duplicate_and_empty(tmp_path):
    one, two = tmp_path / "one", tmp_path / "Two"
    one.mkdir()
    two.mkdir()
    parts = [str(one), "", str(tmp_path / "khong-co"), str(one).upper() + "\\", "%FVPL_TEST_DIR%", "%CHUA_DAT%\\bin"]
    entries = envpath.analyze(parts, {"FVPL_TEST_DIR": str(two)})
    assert [entry.state for entry in entries] == ["ok", "empty", "missing", "duplicate", "ok", "missing"]
    assert entries[4].expanded == str(two) and entries[5].expanded == "%CHUA_DAT%\\bin"
    # Mục của người dùng trùng với PATH của máy cũng là trùng.
    user = envpath.analyze([str(two), str(tmp_path)], seen=envpath.keys_of(entries))
    assert [entry.state for entry in user] == ["duplicate", "ok"]
    assert envpath.cleaned(parts, {"FVPL_TEST_DIR": str(two)}) == [str(one), "%FVPL_TEST_DIR%"]  # giữ cách viết %…%


def test_join_split_and_overrides():
    assert envpath.split("a;;b") == ["a", "", "b"] and envpath.join(["a", " ", "b "]) == "a;b"
    overrides = envpath.user_overrides(r"C:\Users\an")
    assert envpath.expand(r"%USERPROFILE%\bin;%LocalAppData%\x", overrides) == r"C:\Users\an\bin;C:\Users\an\AppData\Local\x"
    assert envpath.user_overrides("") == {}


def test_action_writes_expand_string_with_undo_and_notify():
    machine = envpath.action(envpath.MACHINE, r"%SystemRoot%\system32;C:\Tools")
    step = machine.apply[0]
    assert step.type == "EXPAND_SZ" and step.name == "Path" and step.key.startswith("HKLM")
    assert machine.risk is Risk.CAUTION and machine.undo_mode is UndoMode.AUTO and machine.admin
    assert machine.after == ("notify_environment",)
    user = envpath.action(envpath.USER, r"C:\x")
    assert user.scope is Scope.USER and not user.admin and user.apply[0].key == r"HKCU\Environment"
