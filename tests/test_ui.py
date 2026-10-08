from __future__ import annotations

import time

import pytest

from fvpl_ittools.actions.loader import parse_action

QtWidgets = pytest.importorskip("PySide6.QtWidgets")


@pytest.fixture(scope="module")
def qt_app():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from fvpl_ittools.ui.theme import apply_theme
    apply_theme(app)
    return app


@pytest.fixture
def window(qt_app):
    from fvpl_ittools.app import build_context
    from fvpl_ittools.ui.main_window import MainWindow
    win = MainWindow(build_context())
    win.show()
    yield win
    win.close()


def wait_idle(qt_app, controller, timeout=30):
    deadline = time.monotonic() + timeout
    while controller.busy and time.monotonic() < deadline:
        qt_app.processEvents()
        time.sleep(0.02)
    qt_app.processEvents()
    assert not controller.busy


def test_every_page_renders(window, qt_app):
    for row in range(window.sidebar.count()):
        window.sidebar.setCurrentRow(row)
        qt_app.processEvents()
        assert not window.grab().isNull()


def test_fix_page_lists_actions_and_preview_writes_commands(window, qt_app):
    window.select_page("Sửa lỗi")
    page = window.stack.currentWidget()
    assert {action.id for action in page.actions} >= {"net.flush_dns", "sys.restart_explorer"}
    page.search.setText("cache dns")  # gõ không dấu vẫn tìm ra "Xoá cache DNS"
    visible = [action.id for action in page.actions if not page._items[action.id].isHidden()]
    assert visible == ["net.flush_dns"]
    window.controller.preview([page._by_id["net.flush_dns"]])
    assert "ipconfig /flushdns" in window.log_panel.plain_text()


def test_controller_runs_in_background_and_reports(window, qt_app):
    action = parse_action({
        "id": "test.echo", "name": "Thử in chữ", "category": "Test", "admin": False,
        "apply": [{"cmd": "echo xin chao tu test"}],
    })
    finished = []
    window.controller.finished.connect(finished.append)
    window.controller.run([action])
    wait_idle(qt_app, window.controller)
    log_text = window.log_panel.plain_text()
    assert "xin chao tu test" in log_text
    assert "Kết thúc: 1 xong." in log_text
    assert finished and finished[0].results[0].status.value == "ok"


def test_progress_lines_overwrite_previous(window):
    from fvpl_ittools.core.executor import Level, LogEvent
    panel = window.log_panel
    panel.clear()
    for percent in (10, 20, 30):
        panel.append(LogEvent(Level.OUTPUT, f"{percent}%", progress=True))
    panel.append(LogEvent(Level.OUTPUT, "xong"))
    lines = panel.plain_text().splitlines()
    assert [line.split("  ", 1)[-1].strip() for line in lines] == ["30%", "xong"]
