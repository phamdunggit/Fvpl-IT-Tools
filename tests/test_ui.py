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
def window(qt_app, monkeypatch):
    from fvpl_ittools.app import build_context
    from fvpl_ittools.core import inventory
    from fvpl_ittools.ui.main_window import MainWindow

    from .test_inventory import SAMPLE

    # Trang Tổng quan dùng dữ liệu mẫu thay vì chạy PowerShell thật.
    parts = {"system": ("os", "licenses", "office", "hardware", "volumes", "system_drive"), "storage": ("disks",),
             "network": ("network", "dns_checks"), "security": ("security",)}
    monkeypatch.setattr(inventory, "collect_part",
                        lambda part, cancel=None: {key: SAMPLE[key] for key in parts[part]})
    # Trang Phần mềm: danh mục đóng gói, máy "đã cài" Chrome, chưa có share.
    from fvpl_ittools.software import catalog, detect, install, scan
    from fvpl_ittools.software.detect import InstalledEntry

    def fake_scan(app):
        loaded = catalog.load_catalog_file(catalog.BUNDLED_FILE)
        senv = install.SoftwareEnv(is_admin=True, runs_as_other_user=False, winget="winget.exe",
                                   share_root="", share_ok=False)
        entries = [InstalledEntry("Google Chrome", "130.0")]
        return scan.SoftwareState(loaded, senv, entries, {item.id: detect.detect(item, entries) for item in loaded.apps})

    monkeypatch.setattr(scan, "scan", fake_scan)
    # Trang Cài máy mới: dữ kiện mẫu, giờ lệch nhiều để có nút Đồng bộ giờ.
    from fvpl_ittools.newpc import precheck

    from .test_precheck import facts, network
    monkeypatch.setattr(precheck, "collect", lambda app, cancel=None: facts(network=network(offset=400)))
    # Trang Tối ưu: kết quả quét rác giả, không đọc ổ đĩa.
    from fvpl_ittools.cleanup import junk
    sizes = {"user_temp": 3 * 1024**3, "windows_old": 8 * 1024**3, "recycle_bin": 500 * 1024**2}
    monkeypatch.setattr(junk, "scan_all", lambda env, cancel=None: [
        junk.Scan(item, sizes.get(item.id, 0), 10 if item.id in sizes else 0) for item in junk.CATEGORIES])
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


def test_overview_loads_parts_copies_and_alerts(window, qt_app, state_dir, monkeypatch):
    from fvpl_ittools.ui.pages import overview as overview_module
    page = window.overview
    deadline = time.monotonic() + 10
    while page.loading and time.monotonic() < deadline:
        qt_app.processEvents()
        time.sleep(0.01)
    assert not page.loading and page.failed == {}
    assert "Cập nhật lúc" in page.status.text()
    shown = page.view.toPlainText()
    assert "Ổ đĩa 1" in shown and "Đang đọc" not in shown

    page.copy_text()
    copied = QtWidgets.QApplication.clipboard().text()
    assert copied.startswith("Thông tin máy") and "== Bảo mật ==" in copied

    opened = []
    monkeypatch.setattr(overview_module, "open_as_user", opened.append)
    page.export_html()
    assert opened and opened[0].parent == state_dir / "reports" and opened[0].read_text(encoding="utf-8").startswith("<!doctype")

    page.alerts_changed.emit(["DNS không trỏ về DC"])
    assert window.header.alerts.count() == 1


def test_utilities_page_opens_shortcuts_and_runs_network_tools(window, monkeypatch):
    from fvpl_ittools.ui.pages import utilities
    window.select_page("Tiện ích")
    page = window.stack.currentWidget()
    launched = []
    monkeypatch.setattr(utilities, "launch", launched.append)
    page.shortcuts.buttons["Services"].click()
    assert launched and launched[0][-1].lower().endswith("services.msc")
    assert "Đã mở Services." in window.log_panel.plain_text()

    runs = []
    monkeypatch.setattr(window.controller, "run", lambda actions, **kw: runs.append(actions))
    page.network.host.setText("8.8.8.8 & del")
    page.network.run("ping")
    assert runs == [] and page.network.error.text()
    page.network.host.setText("8.8.8.8")
    page.network.run("ping")
    assert runs[0][0].apply[0].command == "ping -n 4 8.8.8.8"


def test_software_page_profiles_and_install(window, qt_app, monkeypatch):
    from fvpl_ittools.core.executor import ActionResult, Status
    from fvpl_ittools.ui.pages import software as software_module
    window.select_page("Phần mềm")
    page = window.software
    deadline = time.monotonic() + 10
    while (page.loading or page.state is None) and time.monotonic() < deadline:
        qt_app.processEvents()
        time.sleep(0.01)
    assert page.state is not None
    assert page._items["chrome"].text(2) == "Đã cài 130.0"
    assert page._items["office"].text(2) == "Không cài được"  # chưa có share
    assert "share_root" in page._items["office"].toolTip(2)

    page.profile.setCurrentIndex(page.profile.findData("it"))
    page.pick_profile()
    picked = {app.id for app in page.checked_apps()}
    assert "putty" in picked and "foxit" in picked  # foxit kế thừa từ van-phong
    assert "chrome" not in picked and "office" not in picked and "unikey" not in picked

    runs, asked = [], []
    monkeypatch.setattr(window.controller, "run", lambda actions, **kw: runs.append([a.id for a in actions]))
    monkeypatch.setattr(software_module.QMessageBox, "question",
                        lambda parent, title, text: asked.append(text) or software_module.QMessageBox.StandardButton.Yes)
    page._items["office"].setCheckState(0, software_module.Qt.CheckState.Checked)
    page.install(page.checked_apps())
    assert runs and "app.putty" in runs[0] and "app.office" not in runs[0]
    assert "Bỏ qua Microsoft Office" in window.log_panel.plain_text()

    putty = page.state.catalog.app("putty")
    window.controller.last_results["app.putty"] = ActionResult(software_module.install_action(putty, ""), Status.FAILED, "lỗi")
    assert [app.id for app in page.failed_apps()] == ["putty"]
    page.refresh_states()
    assert page._items["putty"].text(2).startswith("✖ Lỗi")


def test_newpc_page_shows_checks_and_time_fix(window, qt_app, monkeypatch):
    window.select_page("Cài máy mới")
    page = window.newpc
    deadline = time.monotonic() + 10
    while (page.loading or not page.checks) and time.monotonic() < deadline:
        qt_app.processEvents()
        time.sleep(0.01)
    assert page.checks
    assert page.summary.property("state") == "bad"
    assert page.tree.topLevelItemCount() == len(page.checks)
    assert page.time_button.isEnabled()
    runs = []
    monkeypatch.setattr(window.controller, "run", lambda actions, **kw: runs.append([a.id for a in actions]))
    page.sync_time()
    assert runs == [["dom.time_sync"]]
    page.copy_text()
    assert QtWidgets.QApplication.clipboard().text().startswith("Kiểm tra trước khi cài máy")


def test_cleanup_scans_first_then_cleans_selected(window, qt_app, monkeypatch):
    from fvpl_ittools.ui.pages import optimize as optimize_module
    window.select_page("Tối ưu & dọn dẹp")
    panel = window.optimize.cleanup
    deadline = time.monotonic() + 10
    while (panel.loading or not panel.scans) and time.monotonic() < deadline:
        qt_app.processEvents()
        time.sleep(0.01)
    assert panel._items["user_temp"].text(1) == "3,0 GB"
    selected = {scan.category.id for scan in panel.selected()}
    assert selected == {"user_temp"}  # loại Cẩn thận không tick sẵn; loại 0 B không tick
    assert "Cẩn thận" in panel._items["windows_old"].text(3)
    assert "Đã chọn 3,0 GB" in panel.total.text()

    jobs, asked = [], []
    monkeypatch.setattr(window.controller, "run_job", jobs.append)
    monkeypatch.setattr(optimize_module.QMessageBox, "question",
                        lambda parent, title, text: asked.append(text) or optimize_module.QMessageBox.StandardButton.Yes)
    panel._items["recycle_bin"].setCheckState(0, optimize_module.Qt.CheckState.Checked)
    panel.clean()
    assert jobs and "Không lấy lại được: Thùng rác của người dùng" in asked[0]


def test_startup_tab_toggles_selected(window, qt_app, monkeypatch):
    from fvpl_ittools.cleanup import startup
    fake = [
        startup.StartupEntry("Spotify", r"C:\Spotify.exe", "Người dùng (Run)", r"HKCU\Software\X\StartupApproved\Run", True),
        startup.StartupEntry("Zalo", r"C:\Zalo.exe", "Người dùng (Run)", r"HKCU\Software\X\StartupApproved\Run", False),
    ]
    monkeypatch.setattr(startup, "entries", lambda env: fake)
    panel = window.optimize.startup
    panel.refresh()
    assert panel.tree.topLevelItemCount() == 2 and panel.tree.topLevelItem(1).text(1) == "Tắt"
    runs = []
    monkeypatch.setattr(window.controller, "run", lambda actions, **kw: runs.append([a.name for a in actions]))
    panel.tree.selectAll()
    assert panel.disable_button.isEnabled() and panel.enable_button.isEnabled()
    panel.toggle(False)
    assert runs == [["Tắt khởi động cùng Windows: Spotify"]]  # Zalo đã tắt sẵn thì bỏ qua


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


def test_pack_bar_runs_pack_with_stop_on_error(window, monkeypatch):
    from fvpl_ittools.ui.pages import actions_page
    window.select_page("Sửa lỗi")
    page = window.stack.currentWidget()
    assert set(page.pack_buttons) >= {"pack.network", "pack.printer", "pack.windows_update", "pack.domain"}

    calls = []
    asked = []
    monkeypatch.setattr(window.controller, "run", lambda actions, **kw: calls.append(([a.id for a in actions], kw)))
    monkeypatch.setattr(actions_page.QMessageBox, "question",
                        lambda parent, title, text: asked.append(text) or actions_page.QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(actions_page.QMessageBox, "information", lambda *args: asked.append(args[2]))
    pack = next(pack for pack in page.packs if pack.id == "pack.network")
    page.run_pack(pack)
    assert asked and "dừng nếu một bước lỗi" in asked[0]
    assert calls == [(list(pack.actions), {"credential": None, "stop_on_error": True})]


def test_config_page_pack_keeps_going_on_error(window, monkeypatch):
    from fvpl_ittools.ui.pages import actions_page
    window.select_page("Cấu hình")
    page = window.stack.currentWidget()
    assert list(page.pack_buttons) == ["pack.standard_config"]
    calls, asked = [], []
    monkeypatch.setattr(window.controller, "run", lambda actions, **kw: calls.append(kw))
    monkeypatch.setattr(actions_page.QMessageBox, "question",
                        lambda parent, title, text: asked.append(text) or actions_page.QMessageBox.StandardButton.Yes)
    page.run_pack(page.packs[0])
    assert "vẫn làm tiếp" in asked[0]
    assert calls == [{"credential": None, "stop_on_error": False}]
    fixes = window.stack.widget([window.sidebar.item(row).text() for row in range(window.sidebar.count())].index("Sửa lỗi"))
    assert "pack.standard_config" not in fixes.pack_buttons


def test_actions_needing_credential_ask_first(window, monkeypatch):
    from dataclasses import replace

    from fvpl_ittools.ui.pages import actions_page
    page = window.stack.widget([window.sidebar.item(row).text() for row in range(window.sidebar.count())].index("Sửa lỗi"))
    action = replace(page._all_actions["dom.repair_trust"], requires_domain=False, admin=False)
    calls = []
    monkeypatch.setattr(window.controller, "run", lambda actions, **kw: calls.append(kw))

    monkeypatch.setattr(actions_page, "ask_credential", lambda names, domain, parent: None)
    page._start([action], stop_on_error=False)
    assert calls == []
    assert "chưa nhập tài khoản" in window.log_panel.plain_text()

    monkeypatch.setattr(actions_page, "ask_credential", lambda names, domain, parent: ("CORP\\it", "pw"))
    page._start([action], stop_on_error=False)
    assert calls == [{"credential": ("CORP\\it", "pw"), "stop_on_error": False}]


def test_credential_dialog(qt_app):
    from fvpl_ittools.ui.credential_dialog import CredentialDialog, qualify_user
    assert qualify_user(" join ", "CORP") == "CORP\\join"
    assert qualify_user("OTHER\\join", "CORP") == "OTHER\\join"
    assert qualify_user("join@corp.example", "CORP") == "join@corp.example"
    assert qualify_user("join", "") == "join"

    dialog = CredentialDialog(["Sửa lỗi trust relationship"], "CORP")
    ok = dialog.buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Ok)
    assert not ok.isEnabled()
    dialog.user.setText("join")
    dialog.password.setText("bí mật")
    assert ok.isEnabled()
    dialog.done(1)
    assert dialog.result_credential == ("CORP\\join", "bí mật")
    assert dialog.password.text() == ""


def test_progress_lines_overwrite_previous(window):
    from fvpl_ittools.core.executor import Level, LogEvent
    panel = window.log_panel
    panel.clear()
    for percent in (10, 20, 30):
        panel.append(LogEvent(Level.OUTPUT, f"{percent}%", progress=True))
    panel.append(LogEvent(Level.OUTPUT, "xong"))
    lines = panel.plain_text().splitlines()
    assert [line.split("  ", 1)[-1].strip() for line in lines] == ["30%", "xong"]
