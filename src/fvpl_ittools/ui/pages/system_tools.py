"""Trang Tiện ích, tab "Event log" và "Công cụ khác" (PLAN.md mục 5.7).

Event log: lỗi Critical / Error gộp theo loại, kèm gợi ý. Công cụ khác: sao lưu / cài lại driver, sửa file HOSTS (có
sao lưu), tìm chương trình đang khoá file, xem mật khẩu Wi-Fi đã lưu (không ghi log).
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...actions.loader import parse_action
from ...app import AppContext
from ...core import drivers, eventlog, lockedfiles, paths, shell, wifi
from ...core.executor import Level
from ..controller import RunController
from ..widgets import Worker, open_path

log = logging.getLogger(__name__)
ROW_ROLE = Qt.ItemDataRole.UserRole


def _note(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("PageSubtitle")
    label.setWordWrap(True)
    return label


def _tree(headers: list[str], stretch: int) -> QTreeWidget:
    tree = QTreeWidget()
    tree.setHeaderLabels(headers)
    tree.setRootIsDecorated(False)
    tree.setUniformRowHeights(True)
    header = tree.header()
    header.setStretchLastSection(False)
    for column in range(len(headers)):
        mode = QHeaderView.ResizeMode.Stretch if column == stretch else QHeaderView.ResizeMode.ResizeToContents
        header.setSectionResizeMode(column, mode)
    return tree


# ---------------------------------------------------------------- event log


class EventLogPanel(QWidget):
    def __init__(self, controller: RunController):
        super().__init__()
        self.controller = controller
        self.groups: list[eventlog.EventGroup] = []
        self.loading = False
        self._started = False
        self.worker = Worker(self)
        self.worker.done.connect(self._loaded)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(_note("Lỗi Critical và Error trong log System, Application, gộp theo loại: lỗi lặp nhiều lên "
                               "trước. Chọn một dòng để xem đầy đủ và gợi ý. Chỉ đọc."))
        row = QHBoxLayout()
        row.addWidget(QLabel("Trong"))
        self.period = QComboBox()
        for label, hours in (("24 giờ qua", 24), ("7 ngày qua", 24 * 7), ("30 ngày qua", 24 * 30)):
            self.period.addItem(label, hours)
        self.read_button = QPushButton("Đọc")
        self.read_button.setObjectName("Primary")
        self.viewer_button = QPushButton("Mở Event Viewer")
        self.status = QLabel()
        self.status.setObjectName("SectionLabel")
        row.addWidget(self.period)
        row.addWidget(self.read_button)
        row.addSpacing(12)
        row.addWidget(self.status, 1)
        row.addWidget(self.viewer_button)
        layout.addLayout(row)

        splitter = QSplitter(Qt.Orientation.Vertical)
        self.tree = _tree(["Mức", "Số lần", "Lần cuối", "Log", "Nguồn", "Mã", "Nội dung"], 6)
        self.detail = QPlainTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setPlaceholderText("Chọn một dòng ở trên.")
        splitter.addWidget(self.tree)
        splitter.addWidget(self.detail)
        splitter.setSizes([320, 140])
        layout.addWidget(splitter, 1)

        self.read_button.clicked.connect(self.read)
        self.period.activated.connect(lambda _index: self.read())
        self.viewer_button.clicked.connect(self.open_viewer)
        self.tree.currentItemChanged.connect(self._show_detail)

    def showEvent(self, event) -> None:
        if not self._started:
            self._started = True
            self.read()
        super().showEvent(event)

    def read(self) -> None:
        hours = int(self.period.currentData())
        self.loading = True
        self.read_button.setEnabled(False)
        self.status.setText("Đang đọc event log…")
        self.worker.run("events", lambda: eventlog.read_errors(hours))

    def _loaded(self, _name: str, result: object) -> None:
        self.loading = False
        self.read_button.setEnabled(True)
        self.tree.clear()
        self.detail.clear()
        if isinstance(result, Exception):
            self.groups = []
            self.status.setText(f"Không đọc được: {result}")
            return
        self.groups = list(result)
        total = sum(group.count for group in self.groups)
        critical = sum(group.count for group in self.groups if group.critical)
        self.status.setText(f"{len(self.groups)} loại lỗi, {total} sự kiện" + (f", {critical} Critical" if critical else ""))
        for index, group in enumerate(self.groups):
            item = QTreeWidgetItem(self.tree, ["Critical" if group.critical else "Error", str(group.count),
                                               group.latest, group.log, group.source, str(group.event_id),
                                               ("💡 " if group.hint else "") + group.summary])
            item.setData(0, ROW_ROLE, index)
            item.setForeground(0, QBrush(QColor("#b91c1c" if group.critical else "#b45309")))
            item.setTextAlignment(1, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            item.setToolTip(6, group.hint or group.summary)

    def _show_detail(self, current: QTreeWidgetItem | None, _previous) -> None:
        if current is None:
            self.detail.clear()
            return
        group = self.groups[current.data(0, ROW_ROLE)]
        parts = []
        if group.hint:
            parts += [f"Gợi ý: {group.hint}", ""]
        parts += [f"{group.log} · {group.source} · mã {group.event_id} · {group.count} lần, lần cuối {group.latest}", "",
                  group.message]
        self.detail.setPlainText("\n".join(parts))

    def open_viewer(self) -> None:
        subprocess.Popen([os.path.join(shell.system_dir(), "mmc.exe"), os.path.join(shell.system_dir(), "eventvwr.msc")])


# ---------------------------------------------------------------- công cụ khác


class ToolsPanel(QWidget):
    WIFI_CLEAR_MS = 120_000

    def __init__(self, app: AppContext, controller: RunController):
        super().__init__()
        self.app = app
        self.controller = controller
        self.lockers: list[lockedfiles.Locker] = []
        self.wifi_profiles: list[wifi.WifiProfile] = []
        self.worker = Worker(self)
        self.worker.done.connect(self._done)
        self.wifi_timer = QTimer(self)
        self.wifi_timer.setSingleShot(True)
        self.wifi_timer.timeout.connect(self.clear_wifi)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 12, 12, 8)
        layout.setSpacing(12)

        # Driver
        card, box = self._card("Sao lưu và cài lại driver")
        box.addWidget(_note("Xuất driver của hãng (không gồm driver có sẵn trong Windows) để cài lại sau khi cài lại "
                            "Windows, hoặc dùng cho máy cùng model. Lưu vào thư mục DriverBackup cạnh tool trên USB / SSD; "
                            "thường vài trăm MB tới vài GB."))
        row = QHBoxLayout()
        self.backup_button = QPushButton("Sao lưu driver máy này")
        self.restore_button = QPushButton("Cài lại driver từ thư mục…")
        self.open_backup_button = QPushButton("Mở thư mục sao lưu")
        for button in (self.backup_button, self.restore_button, self.open_backup_button):
            row.addWidget(button)
        row.addStretch(1)
        box.addLayout(row)
        layout.addWidget(card)

        # HOSTS
        card, box = self._card("File HOSTS")
        box.addWidget(_note("Tool sao lưu file HOSTS hiện tại rồi mở bằng Notepad (quyền admin) để sửa. Sửa xong lưu "
                            "lại rồi chạy Xoá cache DNS. Muốn trả về mặc định thì dùng mục Khôi phục file HOSTS mặc định "
                            "ở trang Sửa lỗi."))
        row = QHBoxLayout()
        self.hosts_button = QPushButton("Sửa file HOSTS")
        self.hosts_backup_button = QPushButton("Mở thư mục bản sao lưu")
        row.addWidget(self.hosts_button)
        row.addWidget(self.hosts_backup_button)
        row.addStretch(1)
        box.addLayout(row)
        layout.addWidget(card)

        # File bị khoá
        card, box = self._card("Chương trình đang khoá file")
        box.addWidget(_note("Khi không xoá / đổi tên / chép đè được file vì \"đang được dùng\": chọn file hoặc thư mục "
                            "để xem chương trình nào đang giữ nó."))
        row = QHBoxLayout()
        self.lock_path = QLineEdit()
        self.lock_path.setPlaceholderText("Đường dẫn file hoặc thư mục")
        self.pick_file_button = QPushButton("Chọn file…")
        self.pick_folder_button = QPushButton("Chọn thư mục…")
        self.find_button = QPushButton("Tìm")
        self.find_button.setObjectName("Primary")
        row.addWidget(self.lock_path, 1)
        for button in (self.pick_file_button, self.pick_folder_button, self.find_button):
            row.addWidget(button)
        box.addLayout(row)
        self.lock_tree = _tree(["PID", "Chương trình", "Loại", "Dịch vụ"], 1)
        self.lock_tree.setMinimumHeight(110)
        box.addWidget(self.lock_tree)
        row = QHBoxLayout()
        self.lock_status = QLabel()
        self.kill_button = QPushButton("Kết thúc tiến trình đã chọn")
        row.addWidget(self.lock_status, 1)
        row.addWidget(self.kill_button)
        box.addLayout(row)
        layout.addWidget(card)

        # Wi-Fi
        card, box = self._card("Mật khẩu Wi-Fi đã lưu")
        box.addWidget(_note("Chỉ dành cho IT, ví dụ lấy mật khẩu Wi-Fi để cài cho máy khác. Không ghi vào log, tự xoá "
                            "khỏi màn hình sau 2 phút."))
        row = QHBoxLayout()
        self.wifi_button = QPushButton("Xem mật khẩu Wi-Fi")
        self.wifi_clear_button = QPushButton("Xoá")
        row.addWidget(self.wifi_button)
        row.addWidget(self.wifi_clear_button)
        row.addStretch(1)
        box.addLayout(row)
        self.wifi_tree = _tree(["Tên", "SSID", "Bảo mật", "Mật khẩu"], 3)
        self.wifi_tree.setMinimumHeight(110)
        box.addWidget(self.wifi_tree)
        layout.addWidget(card)
        layout.addStretch(1)

        self.backup_button.clicked.connect(self.backup_drivers)
        self.restore_button.clicked.connect(self.restore_drivers)
        self.open_backup_button.clicked.connect(lambda: open_path(drivers.backup_root()))
        self.hosts_button.clicked.connect(self.edit_hosts)
        self.hosts_backup_button.clicked.connect(lambda: open_path(self.hosts_backup_dir()))
        self.pick_file_button.clicked.connect(self.pick_file)
        self.pick_folder_button.clicked.connect(self.pick_folder)
        self.find_button.clicked.connect(self.find_lockers)
        self.lock_path.returnPressed.connect(self.find_lockers)
        self.kill_button.clicked.connect(self.kill_selected)
        self.lock_tree.itemSelectionChanged.connect(self._update_buttons)
        self.wifi_button.clicked.connect(self.show_wifi)
        self.wifi_clear_button.clicked.connect(self.clear_wifi)
        controller.busy_changed.connect(lambda _busy: self._update_buttons())
        self._update_buttons()

    @staticmethod
    def _card(title: str) -> tuple[QFrame, QVBoxLayout]:
        card = QFrame()
        card.setObjectName("Card")
        box = QVBoxLayout(card)
        box.setContentsMargins(16, 14, 16, 14)
        box.setSpacing(8)
        label = QLabel(title)
        label.setObjectName("CardTitle")
        box.addWidget(label)
        return card, box

    # driver

    def backup_drivers(self) -> None:
        destination = drivers.backup_dir(self.app.machine.computer_name)
        self.controller.run([drivers.backup_action(destination)])

    def restore_drivers(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Chọn thư mục driver (bản sao lưu hoặc driver đã giải nén)",
                                                  str(drivers.backup_root()))
        if not folder:
            return
        answer = QMessageBox.question(self, "Cài lại driver", f"Nạp và cài mọi driver (.inf) trong:\n{folder}\n\n"
                                                              "Driver chỉ được cài cho thiết bị khớp với nó.")
        if answer == QMessageBox.StandardButton.Yes:
            self.controller.run([drivers.restore_action(Path(folder))])

    # HOSTS

    @staticmethod
    def hosts_path() -> Path:
        return Path(shell.system_dir()) / "drivers" / "etc" / "hosts"

    @staticmethod
    def hosts_backup_dir() -> Path:
        folder = paths.state_dir() / "backup"
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def edit_hosts(self) -> None:
        hosts = self.hosts_path()
        if hosts.is_file():
            backup = self.hosts_backup_dir() / f"hosts_{datetime.now():%Y%m%d_%H%M%S}"
            try:
                shutil.copy2(hosts, backup)
            except OSError as exc:
                self.controller.say(Level.ERROR, f"Không sao lưu được file HOSTS, không mở để sửa: {exc}")
                return
            self.controller.say(Level.OK, f"Đã sao lưu file HOSTS: {backup}")
        if not self.app.env.is_admin:
            self.controller.say(Level.WARN, "Tool không có quyền admin: Notepad mở được nhưng không lưu được file HOSTS.")
        # Notepad mở bằng quyền của tool (admin) nên lưu được file HOSTS.
        subprocess.Popen([os.path.join(shell.system_dir(), "notepad.exe"), str(hosts)])

    # file bị khoá

    def pick_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Chọn file đang bị khoá")
        if path:
            self.lock_path.setText(os.path.normpath(path))
            self.find_lockers()

    def pick_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Chọn thư mục")
        if path:
            self.lock_path.setText(os.path.normpath(path))
            self.find_lockers()

    def find_lockers(self) -> None:
        target = self.lock_path.text().strip().strip('"')
        if not target:
            return
        self.lock_status.setText("Đang tìm…")
        self.find_button.setEnabled(False)
        self.worker.run("lockers", lambda: lockedfiles.lockers(target))

    def selected_locker(self) -> lockedfiles.Locker | None:
        items = self.lock_tree.selectedItems()
        return self.lockers[items[0].data(0, ROW_ROLE)] if items else None

    def kill_selected(self) -> None:
        locker = self.selected_locker()
        if locker is None or locker.pid <= 4:
            return
        warning = ("\n\nĐây là tiến trình hệ thống / dịch vụ: tắt có thể làm máy lỗi." if locker.kind in
                   ("Không nên tắt", "Dịch vụ") else "\nBài chưa lưu trong chương trình đó sẽ mất.")
        answer = QMessageBox.question(self, "Kết thúc tiến trình",
                                      f"Kết thúc {locker.name} (PID {locker.pid})?{warning}")
        if answer != QMessageBox.StandardButton.Yes:
            return
        action = parse_action({
            "id": "util.kill", "name": f"Kết thúc {locker.name} (PID {locker.pid})", "category": "Tiện ích",
            "page": "utilities", "description": "Kết thúc tiến trình đang khoá file.",
            "apply": [{"cmd": f"taskkill /PID {int(locker.pid)} /F", "messages": {128: "Không còn tiến trình này"}}],
        })
        self.controller.run([action])

    # Wi-Fi

    def show_wifi(self) -> None:
        self.wifi_button.setEnabled(False)
        self.worker.run("wifi", wifi.saved_profiles)

    def clear_wifi(self) -> None:
        self.wifi_profiles = []
        self.wifi_tree.clear()
        self.wifi_timer.stop()

    # chung

    def _done(self, name: str, result: object) -> None:
        if name == "lockers":
            self.find_button.setEnabled(True)
            self.lock_tree.clear()
            if isinstance(result, Exception):
                self.lockers = []
                self.lock_status.setText(f"Không tìm được: {result}")
            else:
                self.lockers = list(result)
                self.lock_status.setText(f"{len(self.lockers)} chương trình đang giữ" if self.lockers
                                         else "Không chương trình nào đang giữ file / thư mục này.")
                for index, locker in enumerate(self.lockers):
                    item = QTreeWidgetItem(self.lock_tree, [str(locker.pid), locker.name, locker.kind, locker.service])
                    item.setData(0, ROW_ROLE, index)
        elif name == "wifi":
            self.wifi_button.setEnabled(True)
            self.clear_wifi()
            if isinstance(result, Exception):
                self.controller.say(Level.WARN, str(result))
                return
            self.wifi_profiles = list(result)
            for profile in self.wifi_profiles:
                password = profile.password or ("(mạng mở)" if profile.security.lower() == "open" else
                                                "(không có / cần quyền admin / mạng doanh nghiệp)")
                QTreeWidgetItem(self.wifi_tree, [profile.name, profile.ssid, profile.security, password])
            log.info("%s đã xem mật khẩu Wi-Fi đã lưu trên máy", self.app.env.process_user.name)
            self.controller.say(Level.INFO, f"Đã đọc {len(self.wifi_profiles)} profile Wi-Fi (mật khẩu không ghi vào log).")
            self.wifi_timer.start(self.WIFI_CLEAR_MS)
        self._update_buttons()

    def _update_buttons(self) -> None:
        busy = self.controller.busy
        admin = self.app.env.is_admin
        for button in (self.backup_button, self.restore_button):
            button.setEnabled(not busy and admin)
            button.setToolTip("" if admin else "Cần mở tool bằng quyền admin")
        locker = self.selected_locker()
        self.kill_button.setEnabled(not busy and locker is not None and locker.pid > 4)


def scroll(widget: QWidget) -> QScrollArea:
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.Shape.NoFrame)
    area.setWidget(widget)
    return area
