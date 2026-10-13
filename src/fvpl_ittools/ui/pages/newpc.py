"""Trang Cài máy mới. Hiện có bước 0 "Kiểm tra trước"; các bước còn lại của wizard làm tiếp ở GĐ2."""

from __future__ import annotations

import logging
import threading

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QBrush, QColor, QGuiApplication
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...app import AppContext
from ...core.executor import BatchResult, Level
from ...newpc import precheck
from ..controller import RunController
from ..widgets import page_header

log = logging.getLogger(__name__)

STATE_MARKS = {"ok": "✔", "warn": "⚠", "bad": "✖", "skip": "–"}
STATE_TEXT_COLORS = {"ok": "#15803d", "warn": "#b45309", "bad": "#b91c1c", "skip": "#7b8794"}
NEXT_STEPS = [
    ("1. Thông tin máy", "Chọn phòng ban, gợi ý tên máy theo quy ước, kiểm tra tên đã có trong AD, chọn OU và profile",
     "cần quy ước tên máy và OU (PLAN mục 11, câu 2–3)"),
    ("2. Đổi tên + join domain", "Một lần khởi động lại; thêm nhóm IT vào Administrators; hẹn tool tự mở lại",
     "cần tài khoản join và OU (câu 3)"),
    ("3. Sau khởi động lại", "gpupdate, kiểm tra secure channel", ""),
    ("4. Cài phần mềm", "Theo profile phòng ban: đã có ở trang Phần mềm", "cần danh mục thật trên share (câu 4–5)"),
    ("5. Cấu hình chuẩn", "Múi giờ, power plan, tắt Fast Startup, .NET 3.5, restore point…", ""),
    ("6. Windows Update", "Quét và cài cập nhật", ""),
    ("7. Báo cáo", "HTML trên máy và trên share Inventory", "cần đường dẫn share (câu 4)"),
]


class PrecheckLoader(QObject):
    done = Signal(int, object, str)  # lượt, Facts hoặc None, thông báo lỗi

    def __init__(self, app: AppContext, parent: QObject | None = None):
        super().__init__(parent)
        self.app = app
        self.generation = 0
        self._cancel = threading.Event()

    def start(self) -> None:
        self._cancel.set()
        self._cancel = threading.Event()
        self.generation += 1
        threading.Thread(target=self._work, args=(self.generation, self._cancel), name="precheck", daemon=True).start()

    def stop(self) -> None:
        self._cancel.set()

    def _work(self, generation: int, cancel: threading.Event) -> None:
        try:
            facts, error = precheck.collect(self.app, cancel), ""
        except Exception as exc:
            log.exception("Lỗi khi kiểm tra trước")
            facts, error = None, str(exc) or exc.__class__.__name__
        if not cancel.is_set():
            self.done.emit(generation, facts, error)


class NewPcPage(QWidget):
    def __init__(self, app: AppContext, controller: RunController):
        super().__init__()
        self.app = app
        self.controller = controller
        self.checks: list[precheck.Check] = []
        self.loading = False
        self._started = False
        self.loader = PrecheckLoader(app, self)
        self.loader.done.connect(self._checked)
        self._actions = {action.id: action for action in app.actions}

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 12)
        root.setSpacing(10)
        page_header(
            root, "Cài máy mới",
            "Bước 0: kiểm tra máy trước khi đổi tên, join domain và cài phần mềm. Chỉ đọc, không đổi gì. "
            "Các bước còn lại của wizard đang làm (GĐ2).",
        )

        self.summary = QLabel("Đang kiểm tra…")
        self.summary.setObjectName("SummaryLine")
        self.summary.setWordWrap(True)
        root.addWidget(self.summary)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Kiểm tra", "Kết quả", "Cách xử lý"])
        self.tree.setRootIsDecorated(False)
        self.tree.setWordWrap(True)
        header = self.tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        root.addWidget(self.tree, 3)

        buttons = QHBoxLayout()
        self.recheck_button = QPushButton("Kiểm tra lại")
        self.time_button = QPushButton("Đồng bộ giờ")
        self.time_button.setToolTip("Chạy mục Đồng bộ giờ ở trang Sửa lỗi rồi kiểm tra lại")
        self.copy_button = QPushButton("Copy kết quả")
        self.steps_button = QPushButton("Các bước tiếp theo của wizard")
        self.steps_button.setCheckable(True)
        for button in (self.recheck_button, self.time_button, self.copy_button):
            buttons.addWidget(button)
        buttons.addStretch(1)
        buttons.addWidget(self.steps_button)
        root.addLayout(buttons)

        self.steps = steps = QFrame()
        steps.setObjectName("Card")
        steps_layout = QVBoxLayout(steps)
        steps_layout.setContentsMargins(16, 12, 16, 12)
        steps_layout.setSpacing(4)
        title = QLabel("Các bước tiếp theo của wizard (chưa làm)")
        title.setObjectName("SectionLabel")
        steps_layout.addWidget(title)
        for name, what, needs in NEXT_STEPS:
            line = QLabel(f"<b>{name}</b>: {what}" + (f" <span style='color:#b45309'>({needs})</span>" if needs else ""))
            line.setWordWrap(True)
            steps_layout.addWidget(line)
        steps.setVisible(False)
        root.addWidget(steps)
        self.steps_button.toggled.connect(steps.setVisible)

        self.recheck_button.clicked.connect(self.recheck)
        self.time_button.clicked.connect(self.sync_time)
        self.copy_button.clicked.connect(self.copy_text)
        controller.busy_changed.connect(lambda _busy: self._update_buttons())
        controller.finished.connect(self._run_finished)
        self._update_buttons()

    # ------------------------------------------------------------ kiểm tra

    def showEvent(self, event) -> None:
        if not self._started:
            self._started = True
            self.recheck()
        super().showEvent(event)

    def recheck(self) -> None:
        self.loading = True
        self.summary.setText("Đang kiểm tra (mạng, DNS, DC, giờ, share…)")
        self.summary.setProperty("state", "muted")
        self._restyle(self.summary)
        self._update_buttons()
        self.loader.start()

    def stop(self) -> None:
        self.loader.stop()

    def _checked(self, generation: int, facts: object, error: str) -> None:
        if generation != self.loader.generation:
            return
        self.loading = False
        if facts is None:
            self.checks = []
            self.summary.setText(f"Không kiểm tra được: {error}")
            self.summary.setProperty("state", "bad")
        else:
            self.checks = precheck.evaluate(facts)
            state, text = precheck.summary(self.checks)
            self.summary.setText(text)
            self.summary.setProperty("state", state)
        self._restyle(self.summary)
        self._populate()
        self._update_buttons()

    def _populate(self) -> None:
        self.tree.clear()
        for check in self.checks:
            item = QTreeWidgetItem(self.tree, [f"{STATE_MARKS[check.state]}  {check.name}", check.detail, check.hint])
            color = QBrush(QColor(STATE_TEXT_COLORS[check.state]))
            item.setForeground(0, color)
            item.setForeground(1, color)
            for column in range(3):
                item.setToolTip(column, item.text(column))

    @staticmethod
    def _restyle(widget: QWidget) -> None:
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    # ------------------------------------------------------------ xử lý

    def sync_time(self) -> None:
        action = self._actions.get("dom.time_sync")
        if action is not None:
            self.controller.run([action])

    def _run_finished(self, result: object) -> None:
        if isinstance(result, BatchResult) and any(item.action.id == "dom.time_sync" for item in result.results) \
                and self.isVisible():
            self.recheck()

    def copy_text(self) -> None:
        QGuiApplication.clipboard().setText(precheck.to_text(self.checks, self.app.machine.computer_name))
        self.controller.say(Level.INFO, "Đã copy kết quả kiểm tra vào clipboard.")

    def _update_buttons(self) -> None:
        busy = self.controller.busy
        self.recheck_button.setEnabled(not self.loading and not busy)
        self.copy_button.setEnabled(bool(self.checks))
        needs_time = any(check.fix == "dom.time_sync" for check in self.checks)
        self.time_button.setEnabled(needs_time and not busy and "dom.time_sync" in self._actions)
