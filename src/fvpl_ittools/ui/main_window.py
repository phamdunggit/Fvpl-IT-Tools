"""Cửa sổ chính: thanh trên cùng, sidebar có icon, vùng trang, thanh trạng thái, ngăn kéo log.

Bố cục theo KE-HOACH-GIAO-DIEN.md mục 5.2. Mọi chỗ mở trang (Trang chủ, nút sửa, tìm kiếm Ctrl+K) đi qua
`navigate(đích)`: "page:<trang>", "fixes:<nhóm>", "action:<id>", "pack:<id>", "app:<id>", "tab:<trang>:<tab>",
"shortcut:<tên>", "store", "guide:<tình huống>".
"""

from __future__ import annotations

import subprocess

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QSystemTrayIcon,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .. import APP_NAME, __version__
from ..actions.model import Risk
from ..app import AppContext
from ..core import health, prefs, progress, scenarios, search, shell, taskbar, updates
from ..core.executor import BatchResult, Level, Status
from ..software import uninstall
from . import icons, theme
from .components.command_palette import CommandPalette
from .components.welcome import WelcomeDialog
from .controller import RunController
from .log_panel import LogPanel
from .pages.actions_page import ActionsPage
from .pages.history import HistoryPage
from .pages.home import HomePage
from .pages.newpc import NewPcPage
from .pages.optimize import OptimizePage
from .pages.overview import OverviewPage
from .pages.printers import PrintersPage
from .pages.scenario import ScenarioPage
from .pages.software import SoftwarePage
from .pages.utilities import SHORTCUTS, UtilitiesPage
from .widgets import Worker, chip

UI_MODE = "ui_mode"
WELCOME_SEEN = "welcome_seen"
MODES = ("basic", "expert")
PAGE_LABELS = {"fixes": "Sửa lỗi", "printers": "Máy in", "optimize": "Tối ưu & dọn dẹp", "config": "Cấu hình",
               "utilities": "Tiện ích"}
PAGE_ICONS = {"fixes": "wrench", "printers": "printer", "optimize": "gauge", "config": "settings", "utilities": "toolbox"}

# Công cụ không phải mục YAML, để tìm được bằng Ctrl+K: (tên, mô tả, đích, từ khoá, nâng cao, icon)
TOOLS = (
    ("Ping, tracert, nslookup, kiểm tra cổng", "Kiểm tra máy khác hoặc trang web có trả lời không",
     "tab:utilities:Công cụ mạng", "ping tracert nslookup port cổng mạng", False, "wifi"),
    ("Xem lỗi trong Event log", "Lỗi Windows gần đây gộp theo loại, kèm gợi ý cách xử lý",
     "tab:utilities:Event log", "event viewer nhật ký sự kiện crash màn hình xanh kernel-power", True, "toolbox"),
    ("Sao lưu / cài lại driver", "Lưu driver của máy ra ổ mang theo trước khi cài lại Windows",
     "tab:utilities:Công cụ khác", "driver backup pnputil cài lại windows", False, "toolbox"),
    ("Sửa file HOSTS", "Sao lưu rồi mở file hosts bằng Notepad", "tab:utilities:Công cụ khác",
     "hosts chặn web", False, "toolbox"),
    ("Sao lưu dữ liệu trước khi cài lại Windows", "Desktop, Documents, Downloads, thư mục ở ổ C, Wi-Fi, driver ra ổ D / USB",
     "tab:utilities:Sao lưu dữ liệu", "sao lưu backup cài lại win windows ghost format ổ c dữ liệu desktop documents "
     "download khôi phục restore", False, "download"),
    ("Chuyển dữ liệu máy cũ sang máy mới", "Sao lưu Desktop, Documents, bookmark, chữ ký Outlook rồi khôi phục",
     "tab:utilities:Sao lưu dữ liệu", "chuyển máy đổi máy máy mới máy cũ sao lưu backup khôi phục restore dữ liệu "
     "bookmark", False, "download"),
    ("Sửa biến PATH", "Bỏ thư mục không tồn tại / trùng, thêm hoặc gỡ thư mục trong PATH", "tab:utilities:Công cụ khác",
     "path biến môi trường environment is not recognized lệnh không chạy", True, "toolbox"),
    ("Tìm chương trình đang khoá file", "File / thư mục không xoá được vì đang mở", "tab:utilities:Công cụ khác",
     "file bị khoá không xoá được đang sử dụng in use", False, "toolbox"),
    ("Xem mật khẩu Wi-Fi đã lưu", "Lấy mật khẩu Wi-Fi để cài cho máy khác", "tab:utilities:Công cụ khác",
     "wifi mật khẩu password wlan", False, "wifi"),
    ("Tra mật khẩu LAPS, khoá BitLocker", "Mật khẩu admin cục bộ và khoá khôi phục BitLocker của một máy",
     "tab:utilities:LAPS && BitLocker", "laps bitlocker recovery key mật khẩu admin", True, "shield"),
    ("Dọn rác", "Quét dung lượng từng loại rác rồi mới xoá", "tab:optimize:Dọn rác",
     "dọn rác đầy ổ temp cleanup ổ c", False, "gauge"),
    ("Tìm file lớn", "Tìm file chiếm nhiều dung lượng", "tab:optimize:File lớn", "file lớn đầy ổ dung lượng", False, "disk"),
    ("Gỡ phần mềm", "Gỡ phần mềm đã cài, phần mềm rác tự cài kèm (WPS, 360…)", "tab:optimize:Gỡ phần mềm",
     "gỡ cài đặt uninstall xoá phần mềm wps kingsoft 360 mcafee adware phần mềm rác quảng cáo programs and features",
     False, "apps"),
    ("Chương trình chạy cùng Windows", "Tắt bớt chương trình khởi động cùng máy", "tab:optimize:Khởi động cùng Windows",
     "startup khởi động máy chậm", False, "gauge"),
    ("Thêm máy in", "Thêm máy in qua IP hoặc máy in share", "tab:printers:Thêm máy in",
     "máy in printer thêm ip share driver", False, "printer"),
    ("Danh sách máy in, gỡ máy in, in thử", "Máy in trên máy này", "tab:printers:Máy in trên máy",
     "máy in printer gỡ in thử", False, "printer"),
    ("Lưu kiểm kê (KiemKe.xlsx)", "Lưu thông tin máy vào file tổng hợp trên ổ mang theo", "page:overview",
     "kiểm kê inventory serial excel", False, "clipboard"),
    ("Chọn kho bộ cài", "Thư mục SOFT trên SSD, USB hoặc mạng", "store", "kho soft share bộ cài", False, "disk"),
    ("Hoàn tác thay đổi", "Trả lại registry như trước khi tool chạy", "page:history", "undo hoàn tác nhật ký", False,
     "history"),
    ("Xem lại hướng dẫn nhanh (F1)", "3 điều cần biết: Trang chủ, Ctrl+K, Cơ bản / Chuyên gia", "welcome",
     "hướng dẫn trợ giúp help cách dùng", False, "info"),
)


class SearchBox(QPushButton):
    """Ô tìm trên thanh trên cùng: bấm vào (hoặc Ctrl+K) để mở bảng tìm."""

    def __init__(self):
        super().__init__()
        self.setObjectName("SearchBox")
        self.setCursor(Qt.CursorShape.IBeamCursor)
        self.setAccessibleName("Tìm chức năng")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 8, 0)
        layout.setSpacing(8)
        mark = QLabel()
        mark.setPixmap(icons.pixmap("search", theme.TEXT_SECONDARY, 16))
        text = QLabel("Tìm chức năng (ví dụ: máy in, mạng chậm)")
        text.setStyleSheet(f"color: {theme.TEXT_SECONDARY}; background: transparent;")
        key = QLabel("Ctrl+K")
        key.setStyleSheet(f"color: {theme.TEXT_SECONDARY}; border: 1px solid {theme.BORDER_STRONG}; border-radius: 4px; "
                          "padding: 0 5px; background: #ffffff; font-size: 8.5pt;")
        for label in (mark, text, key):
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(mark)
        layout.addWidget(text, 1)
        layout.addWidget(key)
        self.setMinimumHeight(34)


class HeaderBar(QFrame):
    search_requested = Signal()
    mode_requested = Signal(str)

    def __init__(self, app: AppContext):
        super().__init__()
        self.setObjectName("Header")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 9, 16, 9)
        layout.setSpacing(10)
        logo = QLabel("IT")
        logo.setObjectName("AppLogo")
        logo.setFixedSize(30, 30)
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title = QLabel(APP_NAME)
        title.setObjectName("AppTitle")
        version = QLabel(f"v{__version__}")
        version.setObjectName("AppVersion")
        layout.addWidget(logo)
        layout.addWidget(title)
        layout.addWidget(version)
        layout.addSpacing(16)
        self.search = SearchBox()
        self.search.setMinimumWidth(240)
        self.search.setMaximumWidth(520)
        self.search.clicked.connect(self.search_requested)
        layout.addWidget(self.search, 1)
        layout.addStretch(0)

        machine, env = app.machine, app.env
        self.alerts = QHBoxLayout()
        self.alerts.setSpacing(8)
        layout.addLayout(self.alerts)
        system = chip(" · ".join(part for part in (machine.computer_name, machine.domain_label) if part),
                      "normal" if machine.joined_domain else "warn")
        system.setToolTip(f"{machine.os_name} {machine.display_version} (build {machine.build}.{machine.ubr})".strip())
        layout.addWidget(system)
        if app.runs_as_other_user:
            layout.addWidget(chip(f"Chạy bằng {env.process_user.name} · áp cho {env.target_user.short_name}", "warn"))
        layout.addWidget(chip("Quyền admin ✓", "ok") if env.is_admin else chip("Không có quyền admin", "bad"))

        self.mode_buttons: dict[str, QPushButton] = {}
        group = QButtonGroup(self)
        group.setExclusive(True)
        segment = QHBoxLayout()
        segment.setSpacing(0)
        for mode, label, tip, position in (
            ("basic", "Cơ bản", "Việc hay làm, tên dễ hiểu, ẩn mục Nâng cao", "first"),
            ("expert", "Chuyên gia", "Đủ mọi mục, mọi tab, mở sẵn chi tiết kỹ thuật (log)", "last"),
        ):
            button = QPushButton(label)
            button.setCheckable(True)
            button.setProperty("segment", position)
            button.setToolTip(tip)
            button.clicked.connect(lambda _checked=False, value=mode: self.mode_requested.emit(value))
            group.addButton(button)
            segment.addWidget(button)
            self.mode_buttons[mode] = button
        layout.addSpacing(6)
        layout.addLayout(segment)

    def set_mode(self, mode: str) -> None:
        self.mode_buttons[mode].setChecked(True)

    def set_alerts(self, texts: list[str]) -> None:
        """Cảnh báo phát hiện sau khi đọc thông tin máy, ví dụ DNS không trỏ về DC."""
        while self.alerts.count():
            widget = self.alerts.takeAt(0).widget()
            if widget is not None:
                widget.deleteLater()
        for text in texts:
            self.alerts.addWidget(chip(f"⚠ {text}", "warn"))


class StatusBar(QFrame):
    """Dưới cùng: đang làm gì (mục n/N, %), nút Huỷ, mở / đóng chi tiết kỹ thuật (log)."""

    def __init__(self, controller: RunController):
        super().__init__()
        self.setObjectName("StatusBar")
        self.tracker: progress.Tracker | None = None
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 5, 12, 5)
        layout.setSpacing(10)
        self.dot = QLabel()
        self.dot.setObjectName("StatusDot")
        self.dot.setFixedSize(8, 8)
        self.text = QLabel("Sẵn sàng")
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setTextVisible(False)
        self.bar.setFixedSize(160, 6)
        self.bar.hide()
        self.cancel_button = QPushButton("Huỷ")
        self.cancel_button.hide()
        self.cancel_button.clicked.connect(controller.cancel)
        self.log_button = QPushButton("Chi tiết kỹ thuật (log)")
        self.log_button.setObjectName("StatusLink")
        self.log_button.setCheckable(True)
        self.log_button.setCursor(Qt.CursorShape.PointingHandCursor)
        layout.addWidget(self.dot)
        layout.addWidget(self.text, 1)
        layout.addWidget(self.bar)
        layout.addWidget(self.cancel_button)
        layout.addWidget(self.log_button)
        controller.progress.connect(self.on_progress)
        controller.busy_changed.connect(self.set_busy)
        controller.finished.connect(self.on_finished)

    def _dot(self, kind: str) -> None:
        self.dot.setProperty("kind", kind)
        self.dot.style().unpolish(self.dot)
        self.dot.style().polish(self.dot)

    def set_busy(self, busy: bool) -> None:
        self.cancel_button.setVisible(busy)
        if busy:
            self.tracker = None
            self.text.setText("Đang chạy…")
            self._dot("busy")
        else:
            self.bar.hide()

    def on_progress(self, event: object) -> None:
        if isinstance(event, progress.BatchStarted):
            self.tracker = progress.Tracker(event)
        elif not (isinstance(event, progress.ItemUpdate) and self.tracker is not None and self.tracker.apply(event)):
            return
        self.text.setText(self.tracker.headline())
        self.bar.setValue(int(self.tracker.fraction * 1000))
        self.bar.show()

    def on_finished(self, result: object) -> None:
        if not isinstance(result, BatchResult) or not result.results:
            self.text.setText("Sẵn sàng")
            self._dot("")
            return
        ok, failed = result.count(Status.OK), result.count(Status.FAILED)
        text = f"Lượt vừa chạy: xong {ok}/{len(result.results)} mục"
        if failed:
            text += f", {failed} mục lỗi (xem chi tiết kỹ thuật)"
        if result.cancelled:
            text += ", đã dừng giữa chừng"
        if result.reboot_required:
            text += " · cần khởi động lại máy"
        self.text.setText(text)
        self._dot("warn" if failed or result.cancelled else "")


# (khoá, tên trên sidebar, icon)
PAGES = (
    ("home", "Trang chủ", "home"),
    ("overview", "Thông tin máy", "info"),
    ("newpc", "Cài máy mới", "newpc"),
    ("software", "Cài phần mềm", "apps"),
    ("fixes", "Sửa lỗi", "wrench"),
    ("printers", "Máy in", "printer"),
    ("optimize", "Tối ưu & dọn dẹp", "gauge"),
    ("config", "Cấu hình", "settings"),
    ("utilities", "Tiện ích", "toolbox"),
    ("history", "Nhật ký", "history"),
)
KEY_ROLE = Qt.ItemDataRole.UserRole


class MainWindow(QMainWindow):
    def __init__(self, app: AppContext, resume: bool = False):
        """`resume`: tool được tác vụ hẹn của wizard Cài máy mới mở lại sau khi khởi động lại máy."""
        super().__init__()
        self.app = app
        self.mode = "basic"
        self.tray: QSystemTrayIcon | None = None
        self.taskbar: taskbar.TaskbarProgress | None = None
        self.setWindowTitle(f"{APP_NAME} {__version__}")
        self.resize(1280, 820)
        self.setMinimumSize(1040, 660)
        self.controller = RunController(app, self)

        central = QWidget()
        central.setObjectName("Central")
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.header = HeaderBar(app)
        outer.addWidget(self.header)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self._build_nav())
        self.stack = QStackedWidget()
        self.stack.setObjectName("PageArea")
        self.pages: dict[str, QWidget] = {}
        self.scenarios, self.scenario_errors = scenarios.load()
        self._build_pages()

        self.log_panel = LogPanel()
        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.splitter.addWidget(self.stack)
        self.splitter.addWidget(self.log_panel)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setChildrenCollapsible(False)
        body.addWidget(self.splitter, 1)
        outer.addLayout(body, 1)
        self.status_bar = StatusBar(self.controller)
        outer.addWidget(self.status_bar)
        self.setCentralWidget(central)

        self.palette = CommandPalette(self, self.build_index, lambda: self.mode == "basic")
        self.palette.activated.connect(self.navigate)
        QShortcut(QKeySequence("Ctrl+K"), self, activated=self.open_search)
        QShortcut(QKeySequence("F1"), self, activated=self.show_welcome)
        for row in range(min(10, len(PAGES))):  # Ctrl+1 … Ctrl+0: mở trang thứ 1 … 10 trên sidebar
            QShortcut(QKeySequence(f"Ctrl+{(row + 1) % 10}"), self,
                      activated=lambda index=row: self.sidebar.setCurrentRow(index))
        self.header.search_requested.connect(self.open_search)
        self.header.mode_requested.connect(self.set_mode)
        self.status_bar.log_button.toggled.connect(self.show_log)

        self.sidebar.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.sidebar.setCurrentRow(0)
        self.controller.event.connect(self.log_panel.append)
        self.controller.busy_changed.connect(self.log_panel.set_busy)
        self.log_panel.cancel_requested.connect(self.controller.cancel)
        self.controller.finished.connect(self._finished)
        self.controller.finished.connect(self._notify_done)
        self.controller.busy_changed.connect(self._taskbar_busy)
        self.controller.progress.connect(self._taskbar_progress)
        self.controller.finished.connect(self._taskbar_finished)

        saved = prefs.get(UI_MODE)
        self.set_mode(saved if saved in MODES else "basic", save=False)
        self._update_store_box()
        self.update_worker = Worker(self)
        self.update_worker.done.connect(self._update_checked)
        self.unwanted: list[str] | None = None
        self.optimize.uninstall.unwanted_found.connect(self._unwanted_found)
        self.check_for_update()
        self.check_unwanted()

        self.controller.say(Level.INFO, f"Sẵn sàng. Log phiên này: {app.log_file or '(không ghi log)'}")
        if not app.env.is_admin:
            self.controller.say(Level.WARN, "Tool đang chạy không có quyền admin, các mục cần admin sẽ bị khoá.")
        if app.runs_as_other_user:
            self.controller.say(
                Level.WARN,
                f"Tool chạy bằng {app.env.process_user.name}; thiết lập người dùng sẽ áp cho {app.env.target_user.name}.",
            )
        for error in app.load_errors + self.scenario_errors:
            self.controller.say(Level.ERROR, f"Mục khai báo sai, đã bỏ qua: {error}")
        wizard = self.newpc.state
        if wizard is not None:
            self.controller.say(Level.WARN, f"Đang cài dở máy {wizard.computer_name or '(chưa đặt tên)'}: "
                                            "xem trang Cài máy mới để làm tiếp.")
            if resume:
                self.select_page("newpc")

    # ------------------------------------------------------------ dựng

    def _build_nav(self) -> QWidget:
        nav = QWidget()
        nav.setFixedWidth(224)
        layout = QVBoxLayout(nav)
        layout.setContentsMargins(0, 0, 0, 12)
        layout.setSpacing(8)
        self.sidebar = QListWidget()
        self.sidebar.setObjectName("Sidebar")
        self.sidebar.setIconSize(QSize(20, 20))
        self.sidebar.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        for row, (key, label, icon_name) in enumerate(PAGES):
            item = QListWidgetItem(icons.icon(icon_name, theme.TEXT, theme.ACCENT), label)
            item.setData(KEY_ROLE, key)
            if row < 10:
                item.setToolTip(f"Ctrl+{(row + 1) % 10}")
            item.setSizeHint(QSize(0, 38))
            self.sidebar.addItem(item)
        layout.addWidget(self.sidebar, 1)

        store = QFrame()
        store.setObjectName("StoreBox")
        store_layout = QVBoxLayout(store)
        store_layout.setContentsMargins(12, 10, 12, 10)
        store_layout.setSpacing(2)
        store_layout.addWidget(QLabel("Kho bộ cài"))
        self.store_name = QLabel()
        self.store_name.setObjectName("StoreName")
        self.store_name.setWordWrap(True)
        store_layout.addWidget(self.store_name)
        change = QPushButton("Đổi kho…")
        change.setObjectName("LinkButton")
        change.setCursor(Qt.CursorShape.PointingHandCursor)
        change.clicked.connect(lambda: self.navigate("store"))
        store_layout.addWidget(change)
        wrapper = QHBoxLayout()
        wrapper.setContentsMargins(10, 0, 10, 0)
        wrapper.addWidget(store)
        layout.addLayout(wrapper)
        return nav

    def _build_pages(self) -> None:
        app, controller = self.app, self.controller
        self.home = HomePage(app)
        self.overview = OverviewPage(app, controller)
        self.newpc = NewPcPage(app, controller)
        self.software = SoftwarePage(app, controller)
        self.fixes = ActionsPage(
            "fixes", "Sửa lỗi",
            "Các lỗi thường gặp: mạng, domain, Windows Update, hệ thống, Office (máy in có trang riêng). "
            "Không chắc lỗi ở đâu thì bấm một gói sửa nhanh.",
            "Chưa có mục sửa lỗi nào.", app, controller, packs=app.packs,
        )
        self.printers = PrintersPage(app, controller)
        self.optimize = OptimizePage(app, controller)
        self.config = ActionsPage(
            "config", "Cấu hình",
            "Cấu hình chuẩn cho máy mới và các tuỳ chọn Windows hay dùng. Mục có cột trạng thái cho biết "
            "đang bật hay tắt; mục đổi registry hoàn tác được.",
            "Chưa có mục cấu hình nào.", app, controller, packs=app.packs,
        )
        self.utilities = UtilitiesPage(app, controller)
        self.history = HistoryPage(app, controller)
        widgets = {"home": self.home, "overview": self.overview, "newpc": self.newpc, "software": self.software,
                   "fixes": self.fixes, "printers": self.printers, "optimize": self.optimize, "config": self.config,
                   "utilities": self.utilities, "history": self.history}
        for key, _label, _icon in PAGES:
            self.pages[key] = widgets[key]
            self.stack.addWidget(widgets[key])
        # Sửa lỗi theo tình huống: không có trên sidebar, mở từ Trang chủ, tìm kiếm, thanh trên trang Sửa lỗi.
        self.guide = ScenarioPage(app, controller, self.scenarios, log_text=lambda: self.log_panel.plain_text())
        self.guide.navigate.connect(self.navigate)
        self.stack.addWidget(self.guide)
        self.fixes.layout().insertWidget(2, self._guide_bar())

        self.home.navigate.connect(self.navigate)
        self.home.need_data.connect(self.overview.ensure_loaded)
        self.overview.data_changed.connect(self._update_health)
        self.overview.alerts_changed.connect(self.header.set_alerts)
        self.newpc.open_software.connect(self._open_software)
        self.software.store_changed.connect(self._update_store_box)
        self.utilities.migrate.software_wanted.connect(self._software_from_old_machine)

    def _guide_bar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("GuideBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 8, 12, 8)
        label = QLabel("Hướng dẫn từng bước")
        label.setObjectName("SectionLabel")
        layout.addWidget(label)
        for item in self.scenarios:
            button = QPushButton(icons.icon(item.icon, theme.ACCENT), item.short)
            button.setToolTip(f"{item.title}: {item.tile}")
            button.clicked.connect(lambda _checked=False, target=item.target: self.navigate(target))
            layout.addWidget(button)
        layout.addStretch(1)
        return bar

    # ------------------------------------------------------------ chế độ, log

    def set_mode(self, mode: str, save: bool = True) -> None:
        """Cơ bản: ẩn mục Nâng cao và các tab chuyên sâu, đóng log. Chuyên gia: đủ mọi thứ, mở log."""
        self.mode = mode
        self.header.set_mode(mode)
        for page in self.findChildren(ActionsPage):
            page.set_mode(mode)
        self.utilities.set_mode(mode)
        self.status_bar.log_button.setChecked(mode == "expert")
        self.show_log(mode == "expert")
        if save:
            try:
                prefs.put(UI_MODE, mode)
            except OSError:
                pass

    def show_log(self, visible: bool) -> None:
        self.log_panel.setVisible(visible)
        if visible:
            self.splitter.setSizes([max(300, self.splitter.height() - 210), 200])
        if self.status_bar.log_button.isChecked() != visible:
            self.status_bar.log_button.setChecked(visible)

    def _update_store_box(self) -> None:
        source = self.app.software
        self.store_name.setText(source.root or "Chưa có")
        self.store_name.setToolTip(source.label)

    def _update_health(self) -> None:
        overview = self.overview
        items = health.items(overview.data, overview.basics(), self.unwanted)
        self.home.set_health(items, loading=overview.loading)

    # ------------------------------------------------------------ tìm kiếm, điều hướng

    def open_search(self, query: str = "") -> None:
        self.palette.open_with(query if isinstance(query, str) else "")

    def build_index(self) -> search.Index:
        entries: list[search.Entry] = []
        descriptions = {"home": "Các việc hay làm và tình trạng máy", "overview": "Windows, phần cứng, mạng, bảo mật, serial",
                        "newpc": "Đặt tên, vào domain, cài phần mềm, cấu hình chuẩn, báo cáo",
                        "software": "Office, Symantec, UniKey, ứng dụng winget, kho bộ cài",
                        "fixes": "Mạng, domain, Windows Update, hệ thống, Office", "printers": "Thêm, gỡ, sửa máy in",
                        "optimize": "Dọn rác, khởi động cùng Windows, quảng cáo", "config": "Cấu hình chuẩn máy mới",
                        "utilities": "Công cụ quản trị, mạng, Event log, LAPS", "history": "Hoàn tác thay đổi"}
        for key, label, icon_name in PAGES:
            entries.append(search.Entry("page", label, f"page:{key}", descriptions.get(key, ""), icon=icon_name))
        basic = self.mode == "basic"
        for action in self.app.actions:
            if action.page not in PAGE_LABELS:
                continue
            page_label = PAGE_LABELS[action.page]
            where = page_label if action.category == page_label else f"{page_label} › {action.category}"
            entries.append(search.Entry(
                "action", action.title(basic), f"action:{action.id}", action.description, where,
                " ".join(action.keywords + (action.name, action.basic_name)),
                advanced=action.risk is Risk.ADVANCED, icon=PAGE_ICONS.get(action.page, "wrench")))
        for pack in self.app.packs:
            entries.append(search.Entry("pack", pack.name, f"pack:{pack.id}", pack.description,
                                        PAGE_LABELS.get(pack.page, ""), "gói sửa nhanh",
                                        icon=PAGE_ICONS.get(pack.page, "wrench")))
        for item in self.scenarios:
            entries.append(search.Entry("guide", item.title, item.target, item.tile, "Hướng dẫn từng bước",
                                        " ".join(item.keywords), icon=item.icon))
        for title, description, target, keywords, advanced, icon_name in TOOLS:
            entries.append(search.Entry("tool", title, target, description, "", keywords, advanced, icon_name))
        for group, shortcuts in SHORTCUTS.items():
            for shortcut in shortcuts:
                entries.append(search.Entry("tool", f"Mở {shortcut.name}", f"shortcut:{shortcut.name}", shortcut.note,
                                            f"Tiện ích › Mở nhanh › {group}", group, icon="toolbox"))
        state = self.software.state
        if state is None and not self.software.loading:
            self.software.rescan()  # lần sau mở bảng tìm sẽ có cả phần mềm
        for item in state.catalog.apps if state is not None else []:
            entries.append(search.Entry("app", f"Cài {item.name}", f"app:{item.id}", item.description or item.group,
                                        f"Cài phần mềm › {item.group}", f"cài đặt install {item.choice}", icon="apps"))
        return search.Index(entries)

    def select_page(self, name: str) -> None:
        """Mở trang theo khoá ("software") hoặc tên trên sidebar ("Cài phần mềm")."""
        for row in range(self.sidebar.count()):
            item = self.sidebar.item(row)
            if name in (item.data(KEY_ROLE), item.text()):
                self.sidebar.setCurrentRow(row)
                return

    def reveal(self, widget: QWidget) -> None:
        """Mở trang và tab chứa `widget`."""
        for index in range(self.stack.count()):
            page = self.stack.widget(index)
            if page is widget or page.isAncestorOf(widget):
                self.sidebar.setCurrentRow(index)
                break
        for tabs in self.findChildren(QTabWidget):
            for index in range(tabs.count()):
                page = tabs.widget(index)
                if page is widget or page.isAncestorOf(widget):
                    tabs.setCurrentIndex(index)

    def navigate(self, target: str) -> None:
        kind, _, rest = target.partition(":")
        if kind == "page":
            self.select_page(rest)
        elif kind == "fixes":
            self.select_page("fixes")
            self.fixes.show_category(rest)
        elif kind in ("action", "pack"):
            for page in self.findChildren(ActionsPage):
                found = rest in page._by_id if kind == "action" else rest in page.pack_buttons
                if found:
                    self.reveal(page)
                    page.focus_action(rest) if kind == "action" else page.focus_pack(rest)
                    return
        elif kind == "app":
            self.select_page("software")
            self.software.focus_app(rest)
        elif kind == "tab":
            page_key, _, tab = rest.partition(":")
            self.select_page(page_key)
            tabs = getattr(self.pages.get(page_key), "tabs", None)
            if isinstance(tabs, QTabWidget):
                for index in range(tabs.count()):
                    if tabs.tabText(index) == tab and tabs.isTabVisible(index):
                        tabs.setCurrentIndex(index)
        elif kind == "shortcut":
            self.select_page("utilities")
            shortcut = next((item for items in SHORTCUTS.values() for item in items if item.name == rest), None)
            if shortcut is not None:
                self.utilities.shortcuts.open(shortcut)
        elif kind == "store":
            self.select_page("software")
            self.software.choose_store()
        elif kind == "welcome":
            self.show_welcome()
        elif kind == "guide":
            if self.guide.start(rest):
                self.sidebar.blockSignals(True)
                self.sidebar.clearSelection()
                self.sidebar.setCurrentRow(-1)
                self.sidebar.blockSignals(False)
                self.stack.setCurrentWidget(self.guide)

    def _software_from_old_machine(self, names: list) -> None:
        """Chọn sẵn ở trang Cài phần mềm các ứng dụng máy cũ đã cài (khớp tên với danh mục)."""
        from ..core import migrate
        from ..software import catalog as catalog_module
        state = self.software.state
        catalog = state.catalog if state is not None else catalog_module.load_catalog(self.app.software.root)
        ids = migrate.match_software(list(names), catalog.apps)
        self.controller.say(Level.INFO, f"Máy cũ có {len(names)} phần mềm, {len(ids)} có trong danh mục: chọn sẵn ở trang "
                                        "Cài phần mềm.")
        self._open_software("", ids)

    def _open_software(self, profile_id: str, extra_apps: object) -> None:
        self.select_page("software")
        if profile_id or extra_apps:
            self.software.preselect_profile(profile_id, list(extra_apps or []))

    # ------------------------------------------------------------ chạy xong, đóng

    def _finished(self, result: object) -> None:
        if not isinstance(result, BatchResult) or not result.reboot_required:
            return
        answer = QMessageBox.question(
            self, "Cần khởi động lại",
            "Một số thay đổi cần khởi động lại máy mới có hiệu lực.\nKhởi động lại sau 30 giây?",
        )
        if answer == QMessageBox.StandardButton.Yes:
            subprocess.Popen(
                ["shutdown", "/r", "/t", "30", "/c", f"{APP_NAME}: khởi động lại để hoàn tất thay đổi"],
                creationflags=shell.CREATE_NO_WINDOW,
            )
            self.controller.say(Level.WARN, "Máy sẽ khởi động lại sau 30 giây (huỷ bằng lệnh: shutdown /a).")

    # ------------------------------------------------------------ bản mới

    def check_for_update(self) -> None:
        """Đọc version.json trên share ở thread nền; có bản mới thì báo ở Trang chủ."""
        folder = updates.release_dir(self.app.site.release_dir, self.app.software.root)
        if folder is not None:
            self.update_worker.run("update", lambda: updates.check(folder, __version__))

    def check_unwanted(self) -> None:
        """Phần mềm nên gỡ (WPS…) cho khung Tình trạng máy: đọc registry ở thread nền."""
        sid, root = self.app.env.target_user.sid, self.app.software.root
        self.update_worker.run("unwanted", lambda: [program.name for program, _reason in uninstall.unwanted(
            uninstall.read_programs(sid), uninstall.load_rules(root))])

    def _unwanted_found(self, names: list) -> None:
        self.unwanted = list(names)
        self._update_health()

    def _update_checked(self, name: str, result: object) -> None:
        if name == "unwanted":
            if isinstance(result, list):
                self._unwanted_found(result)
            return
        if isinstance(result, updates.Release):
            self.home.show_update(result)
            self.controller.say(Level.INFO, f"Có bản tool mới {result.version}: {result.folder}")
        elif isinstance(result, Exception):
            self.controller.say(Level.WARN, f"Không kiểm tra được bản tool mới: {result}")

    # ------------------------------------------------------------ hướng dẫn nhanh, taskbar

    def show_welcome(self) -> None:
        WelcomeDialog(self).exec()
        try:
            prefs.put(WELCOME_SEEN, True)
        except OSError:
            pass

    def maybe_show_welcome(self) -> None:
        """Lần đầu mở tool (trên tài khoản Windows này): hiện hướng dẫn nhanh 3 bước."""
        if not prefs.get(WELCOME_SEEN):
            self.show_welcome()

    def _taskbar(self) -> taskbar.TaskbarProgress | None:
        if self.taskbar is None and QGuiApplication.platformName() == "windows":
            self.taskbar = taskbar.TaskbarProgress(int(self.winId()))
        return self.taskbar if self.taskbar is not None and self.taskbar.available else None

    def _taskbar_busy(self, busy: bool) -> None:
        bar = self._taskbar()
        if bar is not None and busy:
            bar.set_state(taskbar.INDETERMINATE)

    def _taskbar_progress(self, _event: object) -> None:
        bar, tracker = self._taskbar(), self.status_bar.tracker
        if bar is not None and tracker is not None:
            bar.set_value(tracker.fraction)

    def _taskbar_finished(self, result: object) -> None:
        bar = self._taskbar()
        if bar is None:
            return
        if isinstance(result, BatchResult) and (result.count(Status.FAILED) or result.cancelled):
            bar.set_value(1.0, taskbar.ERROR)  # đỏ tới lượt chạy sau
        else:
            bar.set_state(taskbar.NONE)

    def _notify_done(self, result: object) -> None:
        """Chạy xong mà IT đang làm việc khác (cửa sổ thu nhỏ / ở sau): báo ở khay hệ thống."""
        if not isinstance(result, BatchResult) or not result.results or self.isActiveWindow():
            return
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        if self.tray is None:
            self.tray = QSystemTrayIcon(icons.icon("ok", theme.ACCENT), self)
            self.tray.setToolTip(APP_NAME)
            self.tray.messageClicked.connect(self._bring_to_front)
            self.tray.activated.connect(lambda _reason: self._bring_to_front())
        self.tray.show()
        failed = result.count(Status.FAILED)
        title = "Chạy xong, có mục lỗi" if failed else "Đã chạy xong"
        kind = QSystemTrayIcon.MessageIcon.Warning if failed else QSystemTrayIcon.MessageIcon.Information
        self.tray.showMessage(title, self.status_bar.text.text(), kind, 10000)

    def _bring_to_front(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event) -> None:
        if self.controller.busy:
            answer = QMessageBox.question(
                self, "Đang chạy", "Đang có việc chạy dở. Huỷ việc đó và thoát?",
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.controller.cancel()
            self.controller.wait(10)
        self.overview.stop()
        self.newpc.stop()
        self.optimize.stop()
        self.printers.stop()
        self.palette.hide()
        if self.tray is not None:
            self.tray.hide()
        event.accept()
