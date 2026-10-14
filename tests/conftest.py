from __future__ import annotations

import os
import uuid
import winreg

import pytest

# Giao diện chạy không cần màn hình; dùng font của Windows để chụp ảnh có chữ.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen:fontengine=freetype")
os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "Fonts"))

from fvpl_ittools.core import paths, registry  # noqa: E402
from fvpl_ittools.core.executor import Env, RunContext  # noqa: E402
from fvpl_ittools.core.journal import UndoJournal  # noqa: E402
from fvpl_ittools.core.session import UserIdentity  # noqa: E402

TEST_ROOT = r"Software\FVPL-ITTools-Test"


@pytest.fixture(autouse=True)
def state_dir(tmp_path, monkeypatch):
    """Mỗi test có thư mục log / nhật ký hoàn tác riêng, không đụng %ProgramData%."""
    folder = tmp_path / "state"
    folder.mkdir()
    monkeypatch.setattr(paths, "_state_dir", folder)
    monkeypatch.setenv("FVPL_ITTOOLS_PREFS", str(tmp_path / "prefs.json"))  # không đụng %APPDATA% thật
    return folder


def _delete_tree(root, subkey: str) -> None:
    try:
        with winreg.OpenKey(root, subkey, 0, winreg.KEY_ALL_ACCESS) as key:
            while True:
                try:
                    child = winreg.EnumKey(key, 0)
                except OSError:
                    break
                _delete_tree(root, f"{subkey}\\{child}")
        winreg.DeleteKey(root, subkey)
    except FileNotFoundError:
        pass


@pytest.fixture
def test_key():
    """Khoá HKCU tạm cho test registry, tự xoá sau khi test xong."""
    subkey = f"{TEST_ROOT}\\{uuid.uuid4().hex[:8]}"
    yield f"HKCU\\{subkey}"
    _delete_tree(winreg.HKEY_CURRENT_USER, subkey)
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, TEST_ROOT)
    except OSError:
        pass  # còn khoá của test khác


@pytest.fixture
def user():
    return UserIdentity(name="TEST\\it", sid="S-1-5-21-1-2-3-1001")


@pytest.fixture
def env(user):
    return Env(is_admin=False, build=26100, process_user=user, target_user=user)


@pytest.fixture
def ctx(env, state_dir):
    events = []
    context = RunContext(env=env, journal=UndoJournal(state_dir / "journal.json"), emit=events.append)
    context.events = events
    return context


def read(key: str, name: str):
    return registry.read_value(registry.parse_key(key), name)
