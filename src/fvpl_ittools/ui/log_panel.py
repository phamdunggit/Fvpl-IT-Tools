"""Khung log ở dưới cùng cửa sổ: hiện output trực tiếp, tiến độ của lượt đang chạy (mục n/N, %), có nút Huỷ."""

from __future__ import annotations

import html

from PySide6.QtCore import Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPlainTextEdit, QProgressBar, QPushButton, QVBoxLayout

from ..core import paths, progress
from ..core.executor import Level, LogEvent
from .theme import LOG_COLORS, OUTPUT_MARK_COLORS
from .widgets import open_path

MAX_LINES = 5000


class LogPanel(QFrame):
    cancel_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("LogPanel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(6)

        bar = QHBoxLayout()
        bar.addWidget(QLabel("Nhật ký chạy"))
        bar.addSpacing(16)
        # Tiến độ của mọi lượt chạy, dù đang ở trang nào.
        self.progress_label = QLabel()
        self.progress_label.setObjectName("LogProgress")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1000)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedSize(160, 6)
        bar.addWidget(self.progress_label)
        bar.addWidget(self.progress_bar)
        bar.addStretch(1)
        self.tracker: progress.Tracker | None = None
        self._show_progress(False)
        self.cancel_button = QPushButton("Huỷ")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_requested)
        clear_button = QPushButton("Xoá khung")
        clear_button.clicked.connect(self.clear)
        folder_button = QPushButton("Mở thư mục log")
        folder_button.clicked.connect(lambda: open_path(paths.logs_dir()))
        for button in (self.cancel_button, clear_button, folder_button):
            bar.addWidget(button)
        layout.addLayout(bar)

        self.view = QPlainTextEdit()
        self.view.setObjectName("LogView")
        self.view.setReadOnly(True)
        self.view.setMaximumBlockCount(MAX_LINES)
        layout.addWidget(self.view, 1)
        self._last_was_progress = False

    def append(self, event: LogEvent) -> None:
        color = LOG_COLORS.get(event.level, "#e2e8f0")
        if event.level is Level.OUTPUT:
            # Script chẩn đoán in ✔ / ✖ / ⚠ đầu dòng; chỉ dùng để tô màu, không dùng để quyết định kết quả.
            color = OUTPUT_MARK_COLORS.get(event.text.lstrip()[:1], color)
        weight = "font-weight:600;" if event.level is Level.HEADER else ""
        text = html.escape(event.text).replace("  ", "&nbsp; ")
        line = (
            f'<span style="color:#64748b">{event.time:%H:%M:%S}</span>&nbsp; '
            f'<span style="color:{color};{weight}">{text}</span>'
        )
        if event.progress and self._last_was_progress:
            # Dòng tiến độ (ví dụ "12%", "13%"…) ghi đè lên dòng trước thay vì thêm dòng mới.
            cursor = self.view.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
            cursor.removeSelectedText()
        self.view.appendHtml(line)
        self._last_was_progress = event.progress
        self.view.verticalScrollBar().setValue(self.view.verticalScrollBar().maximum())

    def clear(self) -> None:
        self.view.clear()
        self._last_was_progress = False

    def set_busy(self, busy: bool) -> None:
        self.cancel_button.setEnabled(busy)
        if not busy:
            self.tracker = None
            self._show_progress(False)

    def on_progress(self, event: object) -> None:
        if isinstance(event, progress.BatchStarted):
            self.tracker = progress.Tracker(event)
        elif not (isinstance(event, progress.ItemUpdate) and self.tracker is not None and self.tracker.apply(event)):
            return
        self.progress_label.setText(self.tracker.headline())
        self.progress_bar.setValue(int(self.tracker.fraction * 1000))
        self._show_progress(True)

    def _show_progress(self, visible: bool) -> None:
        self.progress_label.setVisible(visible)
        self.progress_bar.setVisible(visible)

    def plain_text(self) -> str:
        return self.view.toPlainText()
