"""Trang Phần mềm: danh mục từ apps.yaml, đánh dấu đã cài, chọn theo profile, cài lần lượt (winget + share)."""

from __future__ import annotations

import logging
import threading

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...app import AppContext
from ...core.executor import BatchResult, Level, Status
from ...software import scan as scan_module
from ...software.catalog import App
from ...software.install import blocked_reason, install_action
from ..controller import RunController
from ..text import fold
from ..theme import STATE_COLORS
from ..widgets import page_header

log = logging.getLogger(__name__)
APP_ID_ROLE = Qt.ItemDataRole.UserRole


class ScanLoader(QObject):
    done = Signal(int, object, str)  # lượt, SoftwareState hoặc None, thông báo lỗi

    def __init__(self, app: AppContext, parent: QObject | None = None):
        super().__init__(parent)
        self.app = app
        self.generation = 0

    def start(self) -> None:
        self.generation += 1
        threading.Thread(target=self._work, args=(self.generation,), name="software-scan", daemon=True).start()

    def _work(self, generation: int) -> None:
        try:
            self.done.emit(generation, scan_module.scan(self.app), "")
        except Exception as exc:  # lỗi bất ngờ không được làm treo trang
            log.exception("Lỗi khi quét phần mềm")
            self.done.emit(generation, None, str(exc) or exc.__class__.__name__)


class SoftwarePage(QWidget):
    def __init__(self, app: AppContext, controller: RunController):
        super().__init__()
        self.app = app
        self.controller = controller
        self.state: scan_module.SoftwareState | None = None
        self.loading = False
        self._items: dict[str, QTreeWidgetItem] = {}
        self._started = False
        self.loader = ScanLoader(app, self)
        self.loader.done.connect(self._scanned)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 12)
        root.setSpacing(10)
        page_header(
            root, "Phần mềm",
            "Cài phần mềm từ winget và thư mục share. Tick từng ứng dụng hoặc chọn theo profile phòng ban, "
            "rồi bấm Cài. Các ứng dụng cài lần lượt; một ứng dụng lỗi thì vẫn cài tiếp ứng dụng sau.",
        )
        self.info = QLabel("Đang đọc danh mục…")
        self.info.setObjectName("PageSubtitle")
        self.info.setWordWrap(True)
        root.addWidget(self.info)

        profile_row = QHBoxLayout()
        profile_row.addWidget(QLabel("Profile"))
        self.profile = QComboBox()
        self.profile.setMinimumWidth(200)
        self.pick_button = QPushButton("Chọn theo profile")
        self.pick_button.setToolTip("Tick các ứng dụng của profile (kể cả profile được kế thừa) mà máy chưa có")
        self.search = QLineEdit()
        self.search.setPlaceholderText("Tìm ứng dụng, gõ không dấu cũng được…")
        self.search.setClearButtonEnabled(True)
        profile_row.addWidget(self.profile)
        profile_row.addWidget(self.pick_button)
        profile_row.addSpacing(12)
        profile_row.addWidget(self.search, 1)
        root.addLayout(profile_row)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Ứng dụng", "Nguồn", "Trạng thái"])
        self.tree.setUniformRowHeights(True)
        header = self.tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        root.addWidget(self.tree, 1)

        buttons = QHBoxLayout()
        self.rescan_button = QPushButton("Kiểm tra lại")
        self.preview_button = QPushButton("Xem trước")
        self.preview_button.setToolTip("Hiện lệnh cài của các ứng dụng đã tick, chưa chạy gì")
        self.retry_button = QPushButton("Thử lại mục lỗi")
        self.install_button = QPushButton("Cài mục đã chọn")
        self.install_button.setObjectName("Primary")
        buttons.addWidget(self.rescan_button)
        buttons.addStretch(1)
        buttons.addWidget(self.preview_button)
        buttons.addWidget(self.retry_button)
        buttons.addWidget(self.install_button)
        root.addLayout(buttons)

        self.rescan_button.clicked.connect(self.rescan)
        self.pick_button.clicked.connect(self.pick_profile)
        self.search.textChanged.connect(self._filter)
        self.preview_button.clicked.connect(self.preview)
        self.install_button.clicked.connect(lambda: self.install(self.checked_apps()))
        self.retry_button.clicked.connect(lambda: self.install(self.failed_apps()))
        controller.busy_changed.connect(lambda _busy: self._update_buttons())
        controller.finished.connect(self._run_finished)
        self._update_buttons()

    # ------------------------------------------------------------ quét

    def showEvent(self, event) -> None:
        if not self._started:
            self._started = True
            self.rescan()
        super().showEvent(event)

    def rescan(self) -> None:
        self.loading = True
        self.info.setText("Đang đọc danh mục và kiểm tra phần mềm đã cài…")
        self._update_buttons()
        self.loader.start()

    def _scanned(self, generation: int, state: object, error: str) -> None:
        if generation != self.loader.generation:
            return
        self.loading = False
        if state is None:
            self.info.setText(f"Không đọc được danh mục phần mềm: {error}")
            self.controller.say(Level.ERROR, f"Phần mềm: {error}")
            self._update_buttons()
            return
        first = self.state is None
        self.state = state
        if first:
            for error_text in state.catalog.errors:
                self.controller.say(Level.ERROR, f"Danh mục phần mềm khai báo sai, đã bỏ qua: {error_text}")
        self._populate()
        self.info.setText(self._info_text())
        self._update_buttons()

    def _info_text(self) -> str:
        state = self.state
        senv = state.senv
        installed = sum(1 for detection in state.detections.values() if detection.installed)
        source = self.app.software
        if not source.root:
            share = source.label
        elif senv.share_ok:
            share = source.label
        else:
            share = f"không vào được {source.label}"
        parts = [
            f"Danh mục: {state.catalog.source} ({len(state.catalog.apps)} ứng dụng, đã cài {installed})",
            f"winget: {'có' if senv.winget else 'không có'}",
            f"kho bộ cài: {share}",
        ]
        if state.catalog.errors:
            parts.append(f"{len(state.catalog.errors)} mục khai báo sai (xem khung log)")
        if not senv.is_admin:
            parts.append("cần mở tool bằng quyền admin để cài")
        return " · ".join(parts)

    # ------------------------------------------------------------ cây

    def _populate(self) -> None:
        state = self.state
        checked = {app.id for app in self.checked_apps()}
        current_profile = self.profile.currentData()
        self.tree.clear()
        self._items.clear()
        groups: dict[str, QTreeWidgetItem] = {}
        bold = QFont()
        bold.setBold(True)
        for app in state.catalog.apps:
            parent = groups.get(app.group)
            if parent is None:
                parent = QTreeWidgetItem(self.tree, [app.group])
                parent.setFlags(parent.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsAutoTristate)
                parent.setCheckState(0, Qt.CheckState.Unchecked)
                parent.setFont(0, bold)
                groups[app.group] = parent
            item = QTreeWidgetItem(parent, [app.name, app.source_label, ""])
            item.setData(0, APP_ID_ROLE, app.id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(0, Qt.CheckState.Checked if app.id in checked else Qt.CheckState.Unchecked)
            item.setToolTip(0, app.description or app.name)
            self._items[app.id] = item
        self.tree.expandAll()

        self.profile.clear()
        for profile in state.catalog.profiles:
            self.profile.addItem(profile.name, profile.id)
        if current_profile is not None:
            index = self.profile.findData(current_profile)
            if index >= 0:
                self.profile.setCurrentIndex(index)
        self.refresh_states()
        self._filter(self.search.text())

    def app_status(self, app: App) -> tuple[str, str, str]:
        """(chữ, loại màu, chú thích) cho cột Trạng thái."""
        state = self.state
        last = self.controller.last_results.get(f"app.{app.id}")
        if last is not None and last.status is Status.FAILED:
            return f"✖ Lỗi {last.finished_at:%H:%M}", "error", last.message
        detection = state.detections.get(app.id)
        if detection is not None and detection.installed:
            version = f" {detection.version}" if detection.version else ""
            return f"Đã cài{version}", "on", detection.matched
        reason = blocked_reason(app, state.senv)
        if reason:
            return "Không cài được", "blocked", reason
        if last is not None and last.status is Status.OK:
            return f"✔ Cài xong {last.finished_at:%H:%M}", "ok", "Chưa thấy trong Programs and Features, bấm Kiểm tra lại"
        return "Chưa cài", "off", ""

    def refresh_states(self) -> None:
        if self.state is None:
            return
        for app in self.state.catalog.apps:
            text, kind, note = self.app_status(app)
            item = self._items[app.id]
            item.setText(2, text)
            item.setToolTip(2, note)
            item.setForeground(2, QBrush(QColor(STATE_COLORS.get(kind, "#64748b"))))

    def _filter(self, text: str) -> None:
        needle = fold(text.strip())
        for index in range(self.tree.topLevelItemCount()):
            group = self.tree.topLevelItem(index)
            group_match = needle in fold(group.text(0))
            visible = 0
            for child_index in range(group.childCount()):
                child = group.child(child_index)
                app = self.state.catalog.app(child.data(0, APP_ID_ROLE))
                show = not needle or group_match or needle in fold(f"{app.name} {app.id} {app.description}")
                child.setHidden(not show)
                visible += show
            group.setHidden(visible == 0)

    # ------------------------------------------------------------ chọn

    def checked_apps(self) -> list[App]:
        if self.state is None:
            return []
        return [app for app in self.state.catalog.apps
                if (item := self._items.get(app.id)) is not None and item.checkState(0) == Qt.CheckState.Checked]

    def failed_apps(self) -> list[App]:
        if self.state is None:
            return []
        return [app for app in self.state.catalog.apps
                if (last := self.controller.last_results.get(f"app.{app.id}")) is not None
                and last.status is Status.FAILED]

    def pick_profile(self) -> None:
        if self.state is None or self.profile.currentData() is None:
            return
        wanted = {app.id for app in self.state.catalog.profile_apps(self.profile.currentData())}
        picked = 0
        for app in self.state.catalog.apps:
            installed = self.state.detections[app.id].installed
            check = app.id in wanted and not installed and blocked_reason(app, self.state.senv) is None
            self._items[app.id].setCheckState(0, Qt.CheckState.Checked if check else Qt.CheckState.Unchecked)
            picked += check
        skipped = len(wanted) - picked
        note = f", bỏ qua {skipped} ứng dụng đã cài hoặc không cài được" if skipped else ""
        self.controller.say(Level.INFO, f"Profile {self.profile.currentText()}: chọn {picked} ứng dụng{note}.")

    # ------------------------------------------------------------ cài

    def _split(self, apps: list[App]) -> tuple[list[App], list[tuple[App, str]]]:
        runnable, blocked = [], []
        for app in apps:
            reason = blocked_reason(app, self.state.senv)
            if reason:
                blocked.append((app, reason))
            else:
                runnable.append(app)
        return runnable, blocked

    def preview(self) -> None:
        apps = self.checked_apps()
        if not apps:
            QMessageBox.information(self, "Chưa chọn", "Tick vào ô vuông trước các ứng dụng cần xem.")
            return
        self.controller.preview([install_action(app, self.state.senv.share_root) for app in apps])

    def install(self, apps: list[App]) -> None:
        if self.state is None:
            return
        if not apps:
            QMessageBox.information(self, "Chưa chọn", "Tick vào ô vuông trước các ứng dụng cần cài.")
            return
        runnable, blocked = self._split(apps)
        for app, reason in blocked:
            self.controller.say(Level.WARN, f"Bỏ qua {app.name}: {reason}")
        if not runnable:
            QMessageBox.information(self, "Không cài được", "Không ứng dụng nào trong số đã chọn cài được trên máy này.")
            return
        names = "\n".join(f"• {app.name} ({app.source_label})" for app in runnable)
        needs_internet = any(app.source == "winget" for app in runnable)
        note = "\n\nỨng dụng winget cần Internet." if needs_internet else ""
        answer = QMessageBox.question(
            self, "Cài phần mềm",
            f"Cài lần lượt {len(runnable)} ứng dụng:\n{names}{note}\n\nCó thể mất nhiều phút. Tiếp tục?",
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.controller.run([install_action(app, self.state.senv.share_root) for app in runnable])

    def _run_finished(self, result: object) -> None:
        if not isinstance(result, BatchResult):
            return
        if any(item.action.id.startswith("app.") for item in result.results):
            self.rescan()
        else:
            self.refresh_states()

    def _update_buttons(self) -> None:
        ready = self.state is not None and not self.loading and not self.controller.busy
        for button in (self.install_button, self.preview_button, self.pick_button):
            button.setEnabled(ready)
        self.retry_button.setEnabled(ready and bool(self.failed_apps()))
        self.rescan_button.setEnabled(not self.loading and not self.controller.busy)
