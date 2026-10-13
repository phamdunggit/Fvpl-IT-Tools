"""Cửa sổ chính: thanh trên cùng, sidebar, vùng trang, khung log."""

from __future__ import annotations

import subprocess

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .. import APP_NAME, __version__
from ..app import AppContext
from ..core import shell
from ..core.executor import BatchResult, Level
from .controller import RunController
from .log_panel import LogPanel
from .pages.actions_page import ActionsPage
from .pages.history import HistoryPage
from .pages.newpc import NewPcPage
from .pages.overview import OverviewPage
from .pages.software import SoftwarePage
from .pages.utilities import UtilitiesPage
from .widgets import chip


class HeaderBar(QFrame):
    def __init__(self, app: AppContext):
        super().__init__()
        self.setObjectName("Header")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 10, 18, 10)
        layout.setSpacing(8)
        title = QLabel(APP_NAME)
        title.setObjectName("AppTitle")
        version = QLabel(f"v{__version__}")
        version.setObjectName("AppVersion")
        layout.addWidget(title)
        layout.addWidget(version)
        layout.addStretch(1)

        machine, env = app.machine, app.env
        self.alerts = QHBoxLayout()
        self.alerts.setSpacing(8)
        layout.addLayout(self.alerts)
        layout.addWidget(chip(machine.computer_name))
        layout.addWidget(chip(machine.domain_label, "normal" if machine.joined_domain else "warn"))
        layout.addWidget(chip(f"{machine.os_name} {machine.display_version}".strip()))
        if app.runs_as_other_user:
            layout.addWidget(chip(f"Chạy bằng {env.process_user.name} · áp cho {env.target_user.short_name}", "warn"))
        layout.addWidget(chip("Admin ✔", "ok") if env.is_admin else chip("Không có quyền admin", "bad"))

    def set_alerts(self, texts: list[str]) -> None:
        """Cảnh báo phát hiện sau khi đọc thông tin máy, ví dụ DNS không trỏ về DC."""
        while self.alerts.count():
            widget = self.alerts.takeAt(0).widget()
            if widget is not None:
                widget.deleteLater()
        for text in texts:
            self.alerts.addWidget(chip(f"⚠ {text}", "warn"))


# (tên trên sidebar, hàm tạo trang)
def _pages(app: AppContext, controller: RunController) -> list[tuple[str, QWidget]]:
    return [
        ("Tổng quan", OverviewPage(app, controller)),
        ("Cài máy mới", NewPcPage(app, controller)),
        ("Sửa lỗi", ActionsPage(
            "fixes", "Sửa lỗi",
            "Các lỗi thường gặp: mạng, domain, máy in, Windows Update, hệ thống, Office. "
            "Không chắc lỗi ở đâu thì bấm một gói sửa nhanh.",
            "Chưa có mục sửa lỗi nào.", app, controller, packs=app.packs,
        )),
        ("Tối ưu & dọn dẹp", ActionsPage(
            "optimize", "Tối ưu & dọn dẹp", "Dọn rác có quét trước, quản lý startup, gỡ app rác, quyền riêng tư.",
            "Chưa có mục nào. Phần này làm ở GĐ3: dọn rác (quét trước rồi mới xoá), quản lý startup, "
            "gỡ app cài sẵn, tắt quảng cáo, power plan.", app, controller,
        )),
        ("Phần mềm", SoftwarePage(app, controller)),
        ("Cấu hình", ActionsPage(
            "config", "Cấu hình",
            "Cấu hình chuẩn cho máy mới và các tuỳ chọn Windows hay dùng. Mục có cột trạng thái cho biết "
            "đang bật hay tắt; mục đổi registry hoàn tác được.",
            "Chưa có mục cấu hình nào.", app, controller, packs=app.packs,
        )),
        ("Tiện ích", UtilitiesPage(app, controller)),
        ("Nhật ký", HistoryPage(app, controller)),
    ]


class MainWindow(QMainWindow):
    def __init__(self, app: AppContext):
        super().__init__()
        self.app = app
        self.setWindowTitle(f"{APP_NAME} {__version__}")
        self.resize(1240, 800)
        self.setMinimumSize(1000, 660)
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
        self.sidebar = QListWidget()
        self.sidebar.setObjectName("Sidebar")
        self.sidebar.setFixedWidth(200)
        self.sidebar.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.stack = QStackedWidget()
        self.stack.setObjectName("PageArea")
        for name, page in _pages(app, self.controller):
            item = QListWidgetItem(name)
            item.setSizeHint(QSize(0, 38))
            self.sidebar.addItem(item)
            self.stack.addWidget(page)
            if isinstance(page, OverviewPage):
                self.overview = page
            if isinstance(page, SoftwarePage):
                self.software = page
            if isinstance(page, NewPcPage):
                self.newpc = page
        self.overview.alerts_changed.connect(self.header.set_alerts)

        self.log_panel = LogPanel()
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self.stack)
        splitter.addWidget(self.log_panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([560, 190])
        splitter.setChildrenCollapsible(False)

        body.addWidget(self.sidebar)
        body.addWidget(splitter, 1)
        outer.addLayout(body, 1)
        self.setCentralWidget(central)

        self.sidebar.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.sidebar.setCurrentRow(0)
        self.controller.event.connect(self.log_panel.append)
        self.controller.busy_changed.connect(self.log_panel.set_busy)
        self.log_panel.cancel_requested.connect(self.controller.cancel)
        self.controller.finished.connect(self._finished)

        self.controller.say(Level.INFO, f"Sẵn sàng. Log phiên này: {app.log_file or '(không ghi log)'}")
        if not app.env.is_admin:
            self.controller.say(Level.WARN, "Tool đang chạy không có quyền admin, các mục cần admin sẽ bị khoá.")
        if app.runs_as_other_user:
            self.controller.say(
                Level.WARN,
                f"Tool chạy bằng {app.env.process_user.name}; thiết lập người dùng sẽ áp cho {app.env.target_user.name}.",
            )
        for error in app.load_errors:
            self.controller.say(Level.ERROR, f"Mục khai báo sai, đã bỏ qua: {error}")

    def select_page(self, name: str) -> None:
        for row in range(self.sidebar.count()):
            if self.sidebar.item(row).text() == name:
                self.sidebar.setCurrentRow(row)
                return

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
        event.accept()
