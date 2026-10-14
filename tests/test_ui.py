from __future__ import annotations

import json
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
    # Tiện ích: event log giả.
    from fvpl_ittools.core import eventlog
    monkeypatch.setattr(eventlog, "read_errors", lambda hours, cancel=None: eventlog.parse(json.dumps([
        {"log": "System", "source": "Microsoft-Windows-Kernel-Power", "id": 41, "level": 1, "count": 2,
         "latest": "12/10/2026 07:43", "sort": "2026-10-12T07:43:00", "message": "The system has rebooted"}])))
    # Khởi động cùng Windows: không đọc Task Scheduler thật.
    from fvpl_ittools.cleanup import startup
    monkeypatch.setattr(startup, "task_entries", lambda cancel=None: [])
    # Trang Máy in: danh sách mẫu, không đọc máy thật.
    from fvpl_ittools.printers import manage

    from .test_printers import SNAPSHOT
    monkeypatch.setattr(manage, "snapshot", lambda env, cancel=None: manage.parse_snapshot(SNAPSHOT))
    # Sửa lỗi theo tình huống: không chạy script kiểm tra thật.
    from fvpl_ittools.core import scenarios
    monkeypatch.setattr(scenarios, "run_check", lambda scenario, variables, cancel=None: [
        scenarios.Finding("ok", "ok", "Ổn")])
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
    window.select_page("software")
    page = window.software
    deadline = time.monotonic() + 10
    while (page.loading or page.state is None) and time.monotonic() < deadline:
        qt_app.processEvents()
        time.sleep(0.01)
    assert page.state is not None
    assert page.cards["chrome"].state_text == "Đã cài 130.0"
    page.cards["chrome"].setChecked(True)
    assert not page.cards["chrome"].isChecked()  # đã cài: thẻ khoá, không chọn được
    assert page.store.title.text() == "Chưa có kho bộ cài" and page.store.button.text() == "Chọn kho…"

    # Office là nhóm chọn một, không nằm trong cây; bản trong kho bị khoá khi chưa có kho, bản winget chọn được.
    assert "office2016" not in page.cards
    office = page.choice_groups["office"]
    cards = {card.option.key: card.option for card in office.cards}
    assert list(cards) == ["", "office2016", "office2013", "office2010", "office365"]
    assert cards["office2016"].title == "Office 2016" and not cards["office2016"].enabled
    assert cards["office2016"].note == "Cần kho bộ cài" and "share_root" in cards["office2016"].tooltip
    assert cards["office365"].enabled and "Tải từ Internet" in cards["office365"].note
    assert office.selected() == ""

    page.profile.setCurrentIndex(page.profile.findData("it"))
    page.pick_profile()
    picked = {app.id for app in page.checked_apps()}
    assert "putty" in picked and "foxit" in picked  # foxit kế thừa từ van-phong
    assert "chrome" not in picked and "unikey" not in picked
    assert office.selected() == ""  # profile chọn Office 2016 nhưng chưa có kho

    assert office.select("office365") and not office.select("office2016")
    assert page.summary.text().endswith("(có Microsoft 365 Apps)")
    assert page.install_button.text() == f"Cài {len(picked) + 1} mục"

    runs, asked = [], []
    monkeypatch.setattr(window.controller, "run", lambda actions, **kw: runs.append([a.id for a in actions]))
    monkeypatch.setattr(software_module.QMessageBox, "question",
                        lambda parent, title, text: asked.append(text) or software_module.QMessageBox.StandardButton.Yes)
    page.install(page.selected_apps() + [page.state.catalog.app("unikey")])
    assert runs and runs[0][0] == "app.office365" and "app.putty" in runs[0] and "app.unikey" not in runs[0]
    assert "Bỏ qua UniKey" in window.log_panel.plain_text()
    assert page.views.currentIndex() == software_module.PROGRESS_VIEW and not page.bottom.isVisible()
    page.progress.dismissed.emit()
    assert page.views.currentIndex() == software_module.SELECT_VIEW

    putty = page.state.catalog.app("putty")
    window.controller.last_results["app.putty"] = ActionResult(software_module.install_action(putty, ""), Status.FAILED, "lỗi")
    assert [app.id for app in page.failed_apps()] == ["putty"]
    page.refresh_states()
    assert page.cards["putty"].state_text.startswith("✖ Lỗi")


def test_overview_saves_asset_record(window, qt_app, monkeypatch, tmp_path):
    from fvpl_ittools.core import paths
    page = window.overview
    deadline = time.monotonic() + 10
    while page.loading and time.monotonic() < deadline:
        qt_app.processEvents()
        time.sleep(0.01)
    assert page.asset_button.isEnabled()
    monkeypatch.setattr(paths, "portable_root", lambda: tmp_path)
    page.save_assets()
    name = window.app.machine.computer_name
    assert (tmp_path / "Inventory" / "KiemKe.xlsx").is_file()
    assert any(file.stem.upper() == name.upper() for file in (tmp_path / "Inventory").glob("*.json"))
    assert "có 1 máy" in window.log_panel.plain_text()


def test_secrets_panel_shows_password_but_never_logs_it(window, qt_app, monkeypatch):
    from dataclasses import replace

    from fvpl_ittools.core import adsecrets
    from fvpl_ittools.ui.pages import utilities as utilities_module
    panel = window.findChild(utilities_module.UtilitiesPage).secrets
    panel.app.machine = replace(panel.app.machine, joined_domain=True, dns_domain="corp.example")
    secret = "Xy7!kQ2#mP9vL4zR"
    monkeypatch.setattr(adsecrets, "laps_password", lambda computer, domain, credential=None: adsecrets.LapsPassword(
        computer, "Administrator", secret, "01/10/2026 08:00", "31/10/2026 08:00", True, "Success"))
    asked = []
    monkeypatch.setattr(utilities_module, "ask_credential", lambda names, domain, parent: asked.append(names) or None)

    panel.computer.setText("fvpl-kt05")
    panel.lookup("laps")
    deadline = time.monotonic() + 5
    while panel.busy and time.monotonic() < deadline:
        qt_app.processEvents()
        time.sleep(0.01)
    assert secret in panel.result.toPlainText() and "FVPL-KT05" in panel.result.toPlainText()
    log_text = window.log_panel.plain_text()
    assert "đã xem mật khẩu LAPS của FVPL-KT05" in log_text and secret not in log_text
    assert asked == []  # máy đã vào domain: dùng luôn tài khoản đang chạy tool
    panel.copy_secret()
    assert QtWidgets.QApplication.clipboard().text() == secret
    panel.clear()
    assert panel.result.toPlainText() == "" and not panel.copy_button.isEnabled()

    # Dùng tài khoản khác mà bấm Huỷ ở hộp thoại thì không tra.
    panel.other_account.setChecked(True)
    panel.lookup("bitlocker")
    assert len(asked) == 1 and not panel.busy
    panel.computer.setText("sai tên!")
    panel.lookup("laps")
    assert "Tên máy" in panel.result.toPlainText()


def _utilities(window):
    from fvpl_ittools.ui.pages import utilities as utilities_module
    return window.findChild(utilities_module.UtilitiesPage)


def _wait(qt_app, condition, timeout=5):
    deadline = time.monotonic() + timeout
    while not condition() and time.monotonic() < deadline:
        qt_app.processEvents()
        time.sleep(0.01)
    assert condition()


def test_event_log_tab(window, qt_app):
    window.select_page("Tiện ích")
    page = _utilities(window)
    page.tabs.setCurrentWidget(page.events)  # tab hiện lần đầu thì tự đọc
    _wait(qt_app, lambda: page.events.tree.topLevelItemCount() == 1)
    item = page.events.tree.topLevelItem(0)
    assert item.text(0) == "Critical" and item.text(1) == "2" and item.text(6).startswith("💡")
    page.events.tree.setCurrentItem(item)
    assert page.events.detail.toPlainText().startswith("Gợi ý: Máy tắt đột ngột")


def test_tools_tab_locked_file_wifi_hosts(window, qt_app, monkeypatch, tmp_path, state_dir):
    from fvpl_ittools.core import wifi
    from fvpl_ittools.ui.pages import system_tools
    tools = _utilities(window).tools

    file = tmp_path / "khoa.txt"
    with open(file, "w", encoding="utf-8") as handle:
        handle.write("x")
        tools.lock_path.setText(str(file))
        tools.find_lockers()
        _wait(qt_app, lambda: tools.find_button.isEnabled())
        assert tools.lock_tree.topLevelItemCount() >= 1
    runs = []
    monkeypatch.setattr(window.controller, "run", lambda actions, **kw: runs.append([a.apply[0].command for a in actions]))
    monkeypatch.setattr(system_tools.QMessageBox, "question", lambda *args: system_tools.QMessageBox.StandardButton.Yes)
    tools.lockers = [system_tools.lockedfiles.Locker(4321, "notepad.exe", "", "Ứng dụng")]
    tools._done("lockers", tools.lockers)
    tools.lock_tree.setCurrentItem(tools.lock_tree.topLevelItem(0))
    tools.kill_selected()
    assert runs == [["taskkill /PID 4321 /F"]]

    secret = "Mk@Wifi2026!"
    monkeypatch.setattr(wifi, "saved_profiles", lambda: [wifi.WifiProfile("Office", "Office-5G", "WPA2PSK", secret)])
    tools.show_wifi()
    _wait(qt_app, lambda: tools.wifi_tree.topLevelItemCount() == 1)
    assert tools.wifi_tree.topLevelItem(0).text(3) == secret
    assert secret not in window.log_panel.plain_text()
    tools.clear_wifi()
    assert tools.wifi_tree.topLevelItemCount() == 0

    opened = []
    monkeypatch.setattr(system_tools.subprocess, "Popen", opened.append)
    tools.edit_hosts()
    assert opened and opened[0][-1].lower().endswith("hosts")
    assert list((state_dir / "backup").glob("hosts_*"))  # đã sao lưu trước khi mở


def test_newpc_page_shows_checks_and_time_fix(window, qt_app, monkeypatch):
    window.select_page("Cài máy mới")
    page = window.newpc.check
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


def test_newpc_update_step_skips_vendor_tool_on_other_brands(window, monkeypatch):
    from fvpl_ittools.ui.pages import newpc as newpc_module
    page = window.newpc
    for vendor, expected in (("HP", ["wu.scan_install"]), ("LENOVO", ["drv.vendor_update", "wu.scan_install"]),
                             ("Dell Inc.", ["drv.vendor_update", "wu.scan_install"])):
        monkeypatch.setattr(newpc_module.sysinfo, "manufacturer", lambda value=vendor: value)
        assert [action.id for action in page.update_actions()] == expected


def test_newpc_templates(window, qt_app, monkeypatch, tmp_path):
    from fvpl_ittools.core import config
    from fvpl_ittools.newpc import templates
    from fvpl_ittools.ui.pages import newpc as newpc_module
    page = window.newpc
    site_file = tmp_path / "site.yaml"
    site_file.write_text("domain: corp.example\ndepartments:\n  KT: Kế toán\n  NS: Nhân sự\n", encoding="utf-8")
    page.app.site = config.load_site_config([site_file])
    page._fill_departments()
    page.catalog_apps = [("7zip", "7-Zip", "Tiện ích"), ("vlc", "VLC media player", "Tiện ích")]
    page._worker_done("catalog", ([("van-phong", "Văn phòng"), ("ke-toan", "Kế toán")], page.catalog_apps))

    # Chọn phần mềm thêm, lưu thành mẫu.
    class FakePicker:
        def __init__(self, apps, selected, parent):
            pass

        def exec(self):
            return QtWidgets.QDialog.DialogCode.Accepted

        def selected(self):
            return ["vlc"]
    monkeypatch.setattr(newpc_module, "AppPickerDialog", FakePicker)
    page.pick_extra_apps()
    assert page.extra_label.text() == "VLC media player"
    page.department.setCurrentIndex(page.department.findData("KT"))
    page.profile.setCurrentIndex(page.profile.findData("ke-toan"))
    monkeypatch.setattr(newpc_module.QInputDialog, "getText", lambda *args, **kw: ("Kế toán – Laptop", True))
    page.save_template()
    saved = templates.load(tmp_path / "wizard-templates.json")
    assert saved == [templates.Template("Kế toán – Laptop", "KT", "ke-toan", ["vlc"])]

    # Đổi hết rồi chọn lại mẫu: phòng, profile, phần mềm thêm quay về như mẫu.
    page.department.setCurrentIndex(page.department.findData("NS"))
    page.profile.setCurrentIndex(0)
    page.extra_apps = []
    page.template.setCurrentIndex(page.template.findData("Kế toán – Laptop"))
    page.apply_template()
    assert page.selected_department() == "KT" and page.profile.currentData() == "ke-toan"
    assert page.extra_apps == ["vlc"]

    page.computer_name.setText("FVPL-KT05")
    page.save_info()
    assert page.state.template == "Kế toán – Laptop" and page.state.extra_apps == ["vlc"]

    monkeypatch.setattr(newpc_module.QMessageBox, "question", lambda *args: newpc_module.QMessageBox.StandardButton.Yes)
    page.delete_template()
    assert templates.load(tmp_path / "wizard-templates.json") == [] and page.template.count() == 1


def test_software_page_preselects_extra_apps(window, qt_app):
    page = window.software
    window.select_page("software")
    deadline = time.monotonic() + 10
    while (page.loading or page.state is None) and time.monotonic() < deadline:
        qt_app.processEvents()
        time.sleep(0.01)
    page.preselect_profile("", ["7zip", "chrome", "khong-co", "office365"])
    checked = [app.id for app in page.checked_apps()]
    assert checked == ["7zip"]  # Chrome đã cài sẵn (dữ liệu giả của fixture), mục không có thì bỏ qua
    assert [app.id for app in page.chosen_apps()] == ["office365"]  # bản Office của mẫu chọn vào thẻ
    assert "khong-co" in window.log_panel.plain_text()


def _wait_scan(qt_app, page):
    deadline = time.monotonic() + 10
    while (page.loading or page.state is None) and time.monotonic() < deadline:
        qt_app.processEvents()
        time.sleep(0.01)


def test_software_page_removes_click_to_run_office_first(window, qt_app, monkeypatch, tmp_path):
    from fvpl_ittools.software import catalog, detect, install, scan
    from fvpl_ittools.software.detect import InstalledEntry
    from fvpl_ittools.ui.pages import software as software_module

    store = tmp_path / "SOFT"
    store.mkdir()

    def fake_scan(app):
        loaded = catalog.load_catalog_file(catalog.BUNDLED_FILE)
        entries = [InstalledEntry("Microsoft 365 Apps for business - en-us", "16.0", click_to_run=True)]
        senv = install.SoftwareEnv(
            is_admin=True, runs_as_other_user=False, winget="winget.exe", share_root=str(store), share_ok=True,
            conflicts=(("office2016", "Microsoft 365 Apps for business - en-us"),), removable=frozenset({"office2016"}))
        detections = {item.id: detect.Detection(False) for item in loaded.apps}
        return scan.SoftwareState(loaded, senv, entries, detections)

    monkeypatch.setattr(scan, "scan", fake_scan)
    page = window.software
    window.select_page("software")
    _wait_scan(qt_app, page)
    page.rescan()
    _wait_scan(qt_app, page)
    assert page.store.title.text().endswith(str(store))
    office = page.choice_groups["office"]
    assert office.select("office2016")
    assert not office.warning.isHidden() and office.warning_check.isChecked()
    assert "Microsoft 365 Apps for business" in office.warning_text.text()
    page.cards["7zip"].setChecked(True)
    actions, apps, blocked = page.plan(page.selected_apps())
    assert [action.id for action in actions] == ["off.remove_c2r", "app.7zip", "app.office2016"] and not blocked
    office.warning_check.setChecked(False)  # không cho gỡ thì Office 2016 bị bỏ qua
    actions, apps, blocked = page.plan(page.selected_apps())
    assert [action.id for action in actions] == ["app.7zip"] and blocked[0][0].id == "office2016"


def test_software_page_choose_store_remembers_folder(window, qt_app, monkeypatch, tmp_path):
    from fvpl_ittools.core import prefs
    from fvpl_ittools.ui.pages import software as software_module
    page = window.software
    window.select_page("software")
    _wait_scan(qt_app, page)
    store = tmp_path / "Kho"
    (store / "config").mkdir(parents=True)
    (store / "config" / "apps.yaml").write_text("apps: []\n", encoding="utf-8")
    monkeypatch.setattr(software_module.QFileDialog, "getExistingDirectory", lambda *args: str(store))
    rescans = []
    monkeypatch.setattr(page, "rescan", lambda: rescans.append(1))
    page.choose_store()
    assert prefs.get(prefs.SOFTWARE_ROOT) == str(store)
    assert window.app.software.root == str(store) and window.app.software.kind == "chosen"
    assert window.app.env.share_root == str(store) and rescans


def test_progress_panel_shows_items_and_result(window, qt_app, monkeypatch):
    from fvpl_ittools.core import progress
    from fvpl_ittools.core.executor import ActionResult, BatchResult, Status
    from fvpl_ittools.ui import main_window
    from fvpl_ittools.ui.components.progress_panel import ProgressPanel

    from .test_executor import cmd_action
    # Kết quả giả có "cần khởi động lại": cửa sổ chính hỏi khởi động lại, trả lời Không.
    monkeypatch.setattr(main_window.QMessageBox, "question", lambda *args: main_window.QMessageBox.StandardButton.No)
    controller = window.controller
    panel = ProgressPanel(controller)
    panel.can_retry = True
    controller.progress.emit(progress.BatchStarted(1, (progress.PlanItem("a", "Cài A"),)))
    assert panel.tracker is None  # chưa watch() thì không nhận lượt của trang khác
    panel.watch("Cài phần mềm")
    controller.progress.emit(progress.BatchStarted(2, (progress.PlanItem("a", "Cài A"), progress.PlanItem("b", "Cài B"),
                                                       progress.PlanItem("c", "Cài C", "Cần quyền admin"))))
    controller.progress.emit(progress.ItemUpdate(2, 0, progress.RUNNING))
    controller.progress.emit(progress.ItemUpdate(2, 0, progress.RUNNING, 40.0, progress.DOWNLOADING))
    assert panel.title.text() == "Cài phần mềm"
    assert panel.headline.text() == "Mục 1/3: Cài A · Đang tải về 40%"
    assert panel.rows[0].state.text() == "Đang tải về 40%" and not panel.rows[0].bar.isHidden()
    assert panel.rows[2].reason.text() == "Cần quyền admin"
    assert panel.bar.value() == int((1 + 0.4) / 3 * 1000)  # mục bị bỏ qua tính là xong
    controller.progress.emit(progress.ItemUpdate(2, 0, progress.OK))
    controller.progress.emit(progress.ItemUpdate(2, 1, progress.FAILED, message="Tải bộ cài lỗi"))
    assert panel.rows[0].bar.isHidden() and panel.rows[1].reason.text() == "Tải bộ cài lỗi"
    a, b = cmd_action(id="test.a"), cmd_action(id="test.b")
    controller.finished.emit(BatchResult(results=[ActionResult(a, Status.OK, reboot_required=True),
                                                  ActionResult(b, Status.FAILED, "Tải bộ cài lỗi")]))
    assert panel.headline.text() == "Xong 1/3 mục, 1 mục lỗi"
    assert "Tải bộ cài lỗi" in panel.result_box.text() and "Cần khởi động lại" in panel.result_box.text()
    assert not panel.retry_button.isHidden() and panel.stop_button.isHidden()
    panel.deleteLater()


def _finish_batch(window, actions, status):
    from fvpl_ittools.core.executor import ActionResult, BatchResult
    window.controller.finished.emit(BatchResult(results=[ActionResult(action, status) for action in actions]))


def test_newpc_wizard_flow(window, qt_app, monkeypatch, tmp_path):
    from dataclasses import replace

    from fvpl_ittools.core import config
    from fvpl_ittools.core.executor import Status
    from fvpl_ittools.newpc import naming, state
    from fvpl_ittools.ui.pages import newpc as newpc_module

    page = window.newpc
    window.select_page("Cài máy mới")
    assert page.state is None and page.step_list.currentRow() == 0
    # Máy chưa join, có quyền admin, site.yaml tạm có domain và OU.
    site_file = tmp_path / "site.yaml"
    site_file.write_text("domain: corp.example\nnetbios_domain: CORP\ncomputer_ou: OU=May,DC=corp,DC=example\n",
                         encoding="utf-8")
    page.app.site = config.load_site_config([site_file])
    page.app.machine = replace(page.app.machine, joined_domain=False, computer_name="DESKTOP-ABC",
                               join_name="WORKGROUP", dns_domain="")
    page.app.env = replace(page.app.env, is_admin=True)

    # Bước 1: thêm mã phòng (lưu vào site.yaml), gợi ý tên bằng AD giả.
    class FakeDialog:
        def __init__(self, parent):
            self.code, self.name = QtWidgets.QLineEdit("kt"), QtWidgets.QLineEdit("Kế toán")

        def exec(self):
            return QtWidgets.QDialog.DialogCode.Accepted
    monkeypatch.setattr(newpc_module, "DepartmentDialog", FakeDialog)
    page.add_department()
    assert "KT:" in site_file.read_text(encoding="utf-8") and page.selected_department() == "KT"

    asked = []
    monkeypatch.setattr(newpc_module, "ask_credential",
                        lambda names, domain, parent: asked.append(domain) or ("CORP\\join", "pw"))
    monkeypatch.setattr(naming, "existing_names", lambda domain, prefix, credential=None, cancel=None:
                        ["FVPL-KT01", "FVPL-KT04"])
    page.suggest_name()
    deadline = time.monotonic() + 5
    while not page.computer_name.text() and time.monotonic() < deadline:
        qt_app.processEvents()
        time.sleep(0.01)
    assert page.computer_name.text() == "FVPL-KT05" and asked == ["CORP"]
    page.computer_name.setText("FVPL-KT04")
    assert "đã có trong AD" in page.name_status.text()
    page.computer_name.setText("FVPL-KT05")
    page.primary_user.setText("Nguyễn Văn A")
    page.save_info()
    assert state.load().computer_name == "FVPL-KT05" and page.step_list.currentRow() == 2

    # Bước 2: join dùng lại tài khoản đã nhập ở bước 1, chạy xong thì ghi "chờ khởi động lại".
    runs = []
    monkeypatch.setattr(window.controller, "run", lambda actions, **kw: runs.append((actions, kw)))
    monkeypatch.setattr(newpc_module.QMessageBox, "question",
                        lambda *args: newpc_module.QMessageBox.StandardButton.Yes)
    page._update_buttons()
    assert page.join_button.isEnabled()
    page.join()
    actions, options = runs[-1]
    assert actions[0].id == "newpc.join" and options["credential"] == ("CORP\\join", "pw")
    assert page._credential is None
    _finish_batch(window, actions, Status.OK)
    assert page.state.steps["join"].note == "Chờ khởi động lại" and page.start_step() == "join"

    # Sau khởi động lại: máy đã đúng tên, ở domain → mở bước 3.
    page.app.machine = replace(page.app.machine, joined_domain=True, computer_name="FVPL-KT05",
                               dns_domain="corp.example")
    assert page.start_step() == "after"
    page.run_after_restart()
    actions, options = runs[-1]
    assert [action.id for action in actions][:1] == ["newpc.verify"] and options == {"stop_on_error": False}
    _finish_batch(window, actions, Status.OK)
    assert page.state.status("after") == "ok" and page.step_list.currentRow() == 4

    # Bước 4: mở trang Phần mềm; ghi kết quả khi có lượt cài phần mềm kết thúc.
    picked = []
    monkeypatch.setattr(window.software, "preselect_profile", lambda profile, extra: picked.append((profile, extra)))
    page.state.profile = "van-phong"
    page.state.extra_apps = ["7zip"]
    page.go_software()
    assert window.stack.currentWidget() is window.software and picked == [("van-phong", ["7zip"])]
    _finish_batch(window, [page._actions["dom.gpupdate"]], Status.OK)  # việc khác: chưa tính
    assert page.state.status("software") == ""
    from fvpl_ittools.software import catalog, install
    app = catalog.load_catalog_file(catalog.BUNDLED_FILE).apps[0]
    _finish_batch(window, [install.install_action(app, "")], Status.FAILED)
    assert page.state.status("software") == "failed"

    # Bước 5, 6, 7.
    page.run_config()
    assert runs[-1][1] == {"stop_on_error": False} and "cfg.region_vn" in [a.id for a in runs[-1][0]]
    assert page.right.currentWidget() is page.progress and page.progress.title.text() == ""  # chờ lượt chạy
    from fvpl_ittools.core import progress
    window.controller.progress.emit(progress.BatchStarted(99, tuple(progress.PlanItem(a.id, a.name) for a in runs[-1][0])))
    assert page.progress.title.text() == "Cấu hình chuẩn" and len(page.progress.rows) == len(runs[-1][0])
    _finish_batch(window, runs[-1][0], Status.OK)
    assert page.right.currentWidget() is page.progress  # kết quả vẫn hiện dù bước đã chuyển sang bước 6
    page.progress.dismissed.emit()
    assert page.right.currentWidget() is page.stack and page.stack.currentIndex() == 6
    page.record("update", "skipped", "IT bỏ qua")
    jobs = []
    monkeypatch.setattr(window.controller, "run_job", jobs.append)
    page.make_report()
    assert len(jobs) == 1
    opened = []
    monkeypatch.setattr(newpc_module, "open_as_user", opened.append)
    report_file = tmp_path / "CaiMay_FVPL-KT05.html"
    window.controller.finished.emit(newpc_module.ReportResult([report_file]))
    assert page.state.status("report") == "ok" and opened == [report_file]

    # Kết thúc: bỏ tác vụ mở lại tool, wizard không còn dở.
    page.finish()
    assert runs[-1][0][0].id == "newpc.finish" and page.state is None and state.active() is None


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


def test_startup_tab_adds_tasks_in_background(window, qt_app, monkeypatch):
    from fvpl_ittools.cleanup import startup
    monkeypatch.setattr(startup, "entries", lambda env: [
        startup.StartupEntry("Spotify", r"C:\Spotify.exe", "Người dùng (Run)", r"HKCU\Software\X\StartupApproved\Run", True)])
    task = startup.StartupEntry("Adobe Acrobat Update Task", r'"C:\AdobeARM.exe"', "Task lúc đăng nhập", "", True,
                                task=r"\Adobe Acrobat Update Task")
    monkeypatch.setattr(startup, "task_entries", lambda cancel=None: [task])
    panel = window.optimize.startup
    panel.refresh()
    assert panel.tree.topLevelItemCount() == 1  # task đọc ở nền, hiện sau
    deadline = time.monotonic() + 5
    while panel.tree.topLevelItemCount() < 2 and time.monotonic() < deadline:
        qt_app.processEvents()
        time.sleep(0.01)
    assert panel.tree.topLevelItem(1).text(2) == "Task lúc đăng nhập"
    runs = []
    monkeypatch.setattr(window.controller, "run", lambda actions, **kw: runs.append([a.id for a in actions]))
    panel.tree.setCurrentItem(panel.tree.topLevelItem(1))
    panel.toggle(False)
    assert runs == [["startup.task_toggle"]]


def test_big_files_tab_searches_in_background(window, qt_app, tmp_path):
    (tmp_path / "Data").mkdir()
    (tmp_path / "Data" / "backup.zip").write_bytes(b"x" * (11 * 1024**2))
    panel = window.optimize.bigfiles
    panel.root.setText(str(tmp_path))
    panel.min_mb.setValue(10)
    panel.search()
    deadline = time.monotonic() + 10
    while panel.searching and time.monotonic() < deadline:
        qt_app.processEvents()
        time.sleep(0.01)
    assert panel.files.topLevelItemCount() == 1
    assert panel.files.topLevelItem(0).text(0) == "11,0 MB"
    assert panel.status.text().startswith("Xong")
    panel.files.setCurrentItem(panel.files.topLevelItem(0))
    assert panel.selected_path().endswith("backup.zip") and panel.open_button.isEnabled()


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
    assert set(page.pack_buttons) >= {"pack.network", "pack.windows_update", "pack.domain"}
    assert "pack.printer" not in page.pack_buttons  # nằm ở trang Máy in

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


def _wait_printers(qt_app, page):
    deadline = time.monotonic() + 10
    while page.loading and time.monotonic() < deadline:
        qt_app.processEvents()
        time.sleep(0.01)
    assert not page.loading


def test_printers_page_lists_and_removes(window, qt_app, monkeypatch):
    from fvpl_ittools.ui.pages import printers as printers_module
    window.select_page("Máy in")
    page = window.printers
    _wait_printers(qt_app, page)
    panel = page.list
    assert panel.tree.topLevelItemCount() == 6
    assert panel.tree.topLevelItem(0).text(0) == "Contoso Laser (10.0.0.5)   (đang share: Laser)"
    assert panel.tree.topLevelItem(4).font(0).bold()  # máy in mặc định của người dùng
    assert "6 máy in" in panel.status.text()

    runs, asked = [], []
    monkeypatch.setattr(window.controller, "run", lambda actions, **kw: runs.append(actions))
    monkeypatch.setattr(printers_module.QMessageBox, "question",
                        lambda parent, title, text: asked.append(text) or printers_module.QMessageBox.StandardButton.Yes)
    panel.tree.setCurrentItem(panel.tree.topLevelItem(0))
    panel.driver_checkbox.setChecked(True)
    panel.remove()
    assert "đang share" in asked[0] and "Gỡ cả driver" in asked[0]
    assert runs[0][0].id == "prn.remove" and "$RemoveDriver = '1'" in runs[0][0].apply[0].script

    # Máy in share của người đang đăng nhập: tài khoản chạy tool không in thử / mở hàng đợi được.
    panel.tree.setCurrentItem(panel.tree.topLevelItem(4))
    assert not panel.test_button.isEnabled() and not panel.queue_button.isEnabled()
    panel.remove()
    assert "phải đang đăng nhập" in asked[1] and "$RemoveDriver = ''" in runs[1][0].apply[0].script


def test_printers_page_adds_printers(window, qt_app, monkeypatch, tmp_path):
    from .test_printers import SAMPLE_INF
    window.select_page("Máy in")
    page = window.printers
    _wait_printers(qt_app, page)
    add = page.add
    runs = []
    monkeypatch.setattr(window.controller, "run", lambda actions, **kw: runs.append(actions[0]))

    texts = [add.driver.itemText(index) for index in range(add.driver.count())]
    assert texts[1:3] == ["Contoso PCL6", "Microsoft IPP Class Driver"]
    assert "Generic / Text Only  (có sẵn trong Windows)" in texts

    add.address.setText("10.0.0.9 & calc")
    add.add_ip()
    assert runs == [] and "Nhập IP" in add.error.text()
    add.address.setText("10.0.0.9")
    add.add_ip()
    assert runs == [] and "Chọn driver" in add.error.text()

    file = tmp_path / "contoso.inf"
    file.write_bytes(SAMPLE_INF.replace("NTamd64.10.0, ", "").replace(
        '"Contoso Laser 100 PCL6" = INSTALL, WSDPRINT\\Contoso100\n', "").encode("utf-16"))
    from fvpl_ittools.ui.pages import printers as printers_module
    monkeypatch.setattr(printers_module.QInputDialog, "getItem",
                        lambda *args: ("Contoso Laser 200 PS", True))
    add.use_inf(str(file))
    assert add.selected_driver() == ("Contoso Laser 200 PS", str(file))
    add.set_drivers(["Contoso PCL6"])  # đọc lại danh sách vẫn giữ driver lấy từ file .inf
    assert add.selected_driver() == ("Contoso Laser 200 PS", str(file))
    add.add_ip()
    assert runs[-1].id == "prn.add_ip" and "$PrinterName = 'Máy in 10.0.0.9'" in runs[-1].apply[0].script

    add.share_path.setText("pc01/HP LaserJet")
    add.per_machine.setChecked(True)
    add.add_share()
    assert add.share_path.text() == "\\\\pc01\\HP LaserJet"
    assert runs[-1].id == "prn.add_share" and "$PerMachine = '1'" in runs[-1].apply[0].script


def test_printers_page_fix_tab_has_pack_and_share_fixes(window):
    fixes = window.printers.fixes
    assert list(fixes.pack_buttons) == ["pack.printer"]
    assert {"prn.share_check", "prn.share_host_fix", "prn.share_client_fix",
            "prn.share_host_privacy_off"} <= set(fixes._by_id)


def test_home_tiles_and_health_navigate(window, qt_app):
    home = window.home
    assert window.stack.currentWidget() is home and len(home.tiles) == 8
    deadline = time.monotonic() + 10
    while window.overview.loading and time.monotonic() < deadline:
        qt_app.processEvents()
        time.sleep(0.01)
    qt_app.processEvents()
    assert any(item.target == "page:optimize" for item in home.health_items)  # ổ C trong dữ liệu mẫu gần đầy
    network = next(tile for tile in home.tiles if tile.spec.title == "Không vào được mạng")
    network.click()
    assert window.stack.currentWidget() is window.guide and window.guide.scenario.id == "network"
    assert window.sidebar.currentRow() == -1
    window.navigate("fixes:Mạng & Internet")
    fixes = window.fixes
    assert window.stack.currentWidget() is fixes and fixes.search.text() == "Mạng & Internet"
    visible = [fixes.tree.topLevelItem(i).text(0) for i in range(fixes.tree.topLevelItemCount())
               if not fixes.tree.topLevelItem(i).isHidden()]
    assert visible == ["Mạng & Internet"]
    window.navigate("page:home")
    assert window.stack.currentWidget() is home and window.sidebar.currentRow() == 0


def test_mode_switch_hides_advanced_and_expert_tabs(window, qt_app):
    from fvpl_ittools.core import prefs
    assert window.mode == "basic" and window.log_panel.isHidden()
    fixes = window.fixes
    advanced = fixes._items["sys.reregister_shell"]
    assert advanced.isHidden() and not fixes.mode_note.isHidden()
    tabs = window.utilities.tabs
    titles = [tabs.tabText(i) for i in range(tabs.count()) if tabs.isTabVisible(i)]
    assert "Event log" not in titles and "Công cụ mạng" in titles
    window.header.mode_buttons["expert"].click()
    assert window.mode == "expert" and prefs.get("ui_mode") == "expert"
    assert not advanced.isHidden() and fixes.mode_note.isHidden() and not window.log_panel.isHidden()
    assert all(tabs.isTabVisible(i) for i in range(tabs.count()))
    window.set_mode("basic")
    window.navigate("action:sys.reregister_shell")  # mở từ tìm kiếm: vẫn hiện mục đó dù đang Cơ bản
    assert window.stack.currentWidget() is fixes and fixes.tree.currentItem() is advanced and not advanced.isHidden()


def test_command_palette_searches_and_opens(window, qt_app):
    window.open_search("xoa lenh in bi ket")
    palette = window.palette
    targets = palette.results()
    assert targets and targets[0] == "action:prn.clear_queue"
    palette.activate_current()
    printers = window.printers
    assert window.stack.currentWidget() is printers and printers.tabs.tabText(printers.tabs.currentIndex()) == "Sửa lỗi"
    assert printers.fixes.tree.currentItem() is printers.fixes._items["prn.clear_queue"]

    window.open_search("0x0000011b")
    assert "action:prn.share_check" in palette.results()
    window.open_search("windows update")  # chế độ Cơ bản: mục Nâng cao ẩn, có ghi chú
    assert "action:sys.reregister_shell" not in palette.results()
    window.open_search("event log")
    assert "Nâng cao" in palette.count.text()
    palette.hide()

    window.navigate("tab:optimize:File lớn")
    assert window.stack.currentWidget() is window.optimize
    assert window.optimize.tabs.tabText(window.optimize.tabs.currentIndex()) == "File lớn"
    window.navigate("app:7zip")
    software = window.software
    deadline = time.monotonic() + 10
    while (software.loading or software.state is None or software._wanted_focus) and time.monotonic() < deadline:
        qt_app.processEvents()
        time.sleep(0.01)
    assert window.stack.currentWidget() is software
    assert [app.id for app in software.checked_apps()] == ["7zip"]


def _wait(qt_app, condition, timeout=10):
    deadline = time.monotonic() + timeout
    while not condition() and time.monotonic() < deadline:
        qt_app.processEvents()
        time.sleep(0.01)
    qt_app.processEvents()


def test_scenario_guide_checks_fixes_and_verifies(window, qt_app, monkeypatch):
    from fvpl_ittools.core import scenarios
    from fvpl_ittools.core.executor import ActionResult, BatchResult, Status
    from fvpl_ittools.ui.pages import scenario as scenario_module
    checks = []

    def fake_check(scenario, variables, cancel=None):
        checks.append(scenario.id)
        if len(checks) == 1:
            return [scenarios.Finding("queue_stuck", "bad", "Có 2 lệnh in bị kẹt"),
                    scenarios.Finding("no_default", "warn", "Chưa chọn máy in mặc định"),
                    scenarios.Finding("spooler", "ok", "Dịch vụ in đang chạy")]
        return [scenarios.Finding("spooler", "ok", "Dịch vụ in đang chạy")]

    monkeypatch.setattr(scenarios, "run_check", fake_check)
    window.open_search("khong in duoc")
    assert window.palette.results()[0] == "guide:printing"  # tình huống lên đầu
    window.palette.activate_current()
    page = window.guide
    assert window.stack.currentWidget() is page and page.stage == "checking"
    _wait(qt_app, lambda: page.stage == "review")
    assert page.banner.title.text() == "Tìm thấy 2 vấn đề"
    assert [(row.item.action.id, row.check.isChecked()) for row in page.fix_rows] == [("prn.clear_queue", True)]
    assert not page.manual_card.isHidden()  # máy in mặc định: phải tự chọn
    runs = []
    monkeypatch.setattr(window.controller, "run", lambda actions, **kw: runs.append([a.id for a in actions]))
    page.fix_button.click()
    assert runs == [["prn.clear_queue"]] and page.stage == "fixing" and not page.progress.isHidden()
    window.controller.finished.emit(BatchResult(results=[ActionResult(window.app.actions[0], Status.OK)]))
    _wait(qt_app, lambda: page.stage == "result")
    assert checks == ["printing", "printing"]
    assert page.banner.title.text().startswith("Đã sửa xong") and not page.more_card.isHidden()

    monkeypatch.setattr(scenario_module.QMessageBox, "information", lambda *args: None)
    page.copy_report()
    copied = QtWidgets.QApplication.clipboard().text()
    assert "Tình huống: Không in được" in copied and "Đã chạy:" in copied
    assert "Đã chép báo cáo vào clipboard" in window.log_panel.plain_text()


def test_newpc_office_choice_syncs_with_extra_apps(window, qt_app):
    page = window.newpc
    apps = [("7zip", "7-Zip", "Tiện ích"), ("office2016", "Microsoft Office Standard 2016 (64-bit)", "Văn phòng"),
            ("office2013", "Microsoft Office Standard 2013 (64-bit)", "Văn phòng")]
    office = [("office2016", "Microsoft Office Standard 2016 (64-bit)", "share"),
              ("office2013", "Microsoft Office Standard 2013 (64-bit)", "share")]
    page._worker_done("catalog", ([("van-phong", "Văn phòng")], apps, office))
    titles = [card.option.title for card in page.office.cards]
    assert titles == ["Không cài", "Office 2016", "Office 2013"]
    page.extra_apps = ["7zip", "office2013"]
    page._show_extra_apps()
    assert page.office.selected() == "office2013" and page.extra_label.text() == "7-Zip"
    page.office.select("office2016")
    assert page.extra_apps == ["7zip", "office2016"]
    page.office.select("")
    assert page.extra_apps == ["7zip"]


def test_basic_mode_shows_plain_names(window):
    fixes = window.fixes
    item = fixes._items["wu.reset"]
    assert window.mode == "basic" and item.text(0) == "Sửa Windows Update bị kẹt (đặt lại Windows Update)"
    fixes.focus_action("wu.reset")
    assert fixes.detail.title.text() == item.text(0) and "Tên kỹ thuật: Reset Windows Update" in fixes.detail.description.text()
    window.set_mode("expert")
    assert item.text(0) == "Reset Windows Update" and fixes.detail.title.text() == "Reset Windows Update"
    fixes.search.setText("bị kẹt")  # tìm theo tên dễ hiểu cả ở chế độ Chuyên gia
    assert not item.isHidden()
