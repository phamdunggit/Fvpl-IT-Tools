"""Khung tiến độ của một lượt chạy (KE-HOACH-GIAO-DIEN.md mục 5.6 và 5.9).

Đang chạy: "Mục 4/8: Cài Google Chrome · Đang tải về 45%", thanh tổng, đếm Xong / Đang chạy / Chờ / Lỗi, từng mục
có trạng thái, mục đang chạy có thanh riêng (chạy qua lại khi không biết phần trăm), mục lỗi có lý do.
Chạy xong: thẻ kết quả (xong bao nhiêu, mục nào lỗi và vì sao, cần khởi động lại không) + Thử lại mục lỗi.

Trang muốn dùng thì gọi `watch()` ngay trước khi chạy; khung nhận lượt chạy kế tiếp của RunController.
"""

from __future__ import annotations

import html
from typing import Callable

from PySide6.QtCore import QElapsedTimer, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ...core import progress
from ...core.executor import BatchResult
from ..controller import RunController

MARKS = {progress.WAITING: "○", progress.RUNNING: "●", progress.OK: "✔", progress.FAILED: "✖",
         progress.SKIPPED: "–", progress.CANCELLED: "■"}


def _repolish(widget: QWidget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def elapsed_text(seconds: int) -> str:
    minutes, seconds = divmod(max(0, seconds), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes}:{seconds:02d}"


class ItemRow(QFrame):
    def __init__(self, name: str):
        super().__init__()
        self.setObjectName("ProgressRow")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 6, 0, 6)
        layout.setSpacing(10)
        self.mark = QLabel()
        self.mark.setObjectName("ProgressMark")
        self.mark.setFixedWidth(18)
        self.mark.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        body = QVBoxLayout()
        body.setSpacing(3)
        top = QHBoxLayout()
        top.setSpacing(10)
        self.name = QLabel(name)
        self.name.setObjectName("ProgressName")
        self.name.setWordWrap(True)
        self.state = QLabel()
        self.state.setObjectName("ProgressState")
        top.addWidget(self.name, 1)
        top.addWidget(self.state)
        self.bar = QProgressBar()
        self.bar.setObjectName("ItemBar")
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(6)
        self.bar.hide()
        self.reason = QLabel()
        self.reason.setObjectName("ProgressReason")
        self.reason.setWordWrap(True)
        self.reason.hide()
        body.addLayout(top)
        body.addWidget(self.bar)
        body.addWidget(self.reason)
        layout.addWidget(self.mark)
        layout.addLayout(body, 1)

    def show_item(self, item: progress.ItemState) -> None:
        self.setProperty("state", item.state)
        self.mark.setText(MARKS.get(item.state, ""))
        text = progress.STATE_LABELS.get(item.state, item.state)
        if item.state == progress.RUNNING:
            text = item.phase or text
            if item.percent is not None:
                text += f" {item.percent:.0f}%"
        elif item.state == progress.OK and item.reboot:
            text += " · cần khởi động lại"
        self.state.setText(text)
        running = item.state == progress.RUNNING
        self.bar.setVisible(running)
        if running:
            if item.percent is None:
                self.bar.setRange(0, 0)  # chạy qua lại
            else:
                self.bar.setRange(0, 100)
                self.bar.setValue(int(item.percent))
        show_reason = item.state in (progress.FAILED, progress.SKIPPED, progress.CANCELLED) and bool(item.message)
        self.reason.setText(item.message if show_reason else "")
        self.reason.setVisible(show_reason)
        for widget in (self, self.mark, self.state, self.name):
            _repolish(widget)


class ProgressPanel(QFrame):
    retry_requested = Signal()
    dismissed = Signal()
    completed = Signal(object)  # BatchResult của lượt khung đang theo dõi

    def __init__(self, controller: RunController, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.setObjectName("Card")
        self.tracker: progress.Tracker | None = None
        self._armed = False
        self._title = "Đang chạy"
        self.hint_for: Callable[[BatchResult], str] | None = None  # trang thêm gợi ý vào thẻ kết quả
        self.can_retry = False  # trang có xử lý retry_requested không
        self.result: BatchResult | None = None
        self._clock = QElapsedTimer()
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)
        head = QHBoxLayout()
        self.title = QLabel()
        self.title.setObjectName("CardTitle")
        self.clock = QLabel()
        self.clock.setObjectName("PageSubtitle")
        head.addWidget(self.title, 1)
        head.addWidget(self.clock)
        layout.addLayout(head)

        self.headline = QLabel()
        self.headline.setObjectName("ProgressHeadline")
        self.headline.setWordWrap(True)
        layout.addWidget(self.headline)
        self.bar = QProgressBar()
        self.bar.setObjectName("OverallBar")
        self.bar.setRange(0, 1000)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(10)
        layout.addWidget(self.bar)
        self.counts = QLabel()
        self.counts.setObjectName("PageSubtitle")
        layout.addWidget(self.counts)

        self.result_box = QLabel()
        self.result_box.setObjectName("ResultBox")
        self.result_box.setWordWrap(True)
        self.result_box.setTextFormat(Qt.TextFormat.RichText)
        self.result_box.hide()
        layout.addWidget(self.result_box)

        self.rows_widget = QWidget()
        self.rows_layout = QVBoxLayout(self.rows_widget)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(0)
        scroll = QScrollArea()
        scroll.setObjectName("ProgressList")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(self.rows_widget)
        layout.addWidget(scroll, 1)
        self.rows: list[ItemRow] = []

        buttons = QHBoxLayout()
        self.stop_button = QPushButton("Dừng sau mục đang chạy")
        self.stop_button.setToolTip("Chạy nốt mục đang chạy (không cắt ngang bộ cài), các mục sau không chạy nữa")
        self.cancel_button = QPushButton("Huỷ ngay")
        self.cancel_button.setObjectName("Danger")
        self.cancel_button.setToolTip("Dừng luôn mục đang chạy. Bộ cài bị cắt ngang có thể để lại phần mềm cài dở")
        self.retry_button = QPushButton("Thử lại mục lỗi")
        self.retry_button.setObjectName("Primary")
        self.close_button = QPushButton("Xong")
        buttons.addWidget(self.stop_button)
        buttons.addWidget(self.cancel_button)
        buttons.addStretch(1)
        buttons.addWidget(self.retry_button)
        buttons.addWidget(self.close_button)
        layout.addLayout(buttons)

        self.stop_button.clicked.connect(self._stop)
        self.cancel_button.clicked.connect(controller.cancel)
        self.retry_button.clicked.connect(self.retry_requested)
        self.close_button.clicked.connect(self.dismissed)
        controller.progress.connect(self._on_progress)
        controller.finished.connect(self._on_finished)

    # ------------------------------------------------------------ theo dõi

    @property
    def running(self) -> bool:
        return self.tracker is not None and self.result is None

    def watch(self, title: str) -> None:
        """Nhận lượt chạy kế tiếp. `title`: ví dụ "Cài phần mềm"."""
        self._armed = True
        self._title = title

    def _on_progress(self, event: object) -> None:
        if isinstance(event, progress.BatchStarted):
            if not self._armed:
                return
            self._armed = False
            self._start(event)
        elif isinstance(event, progress.ItemUpdate) and self.running and self.tracker.apply(event):
            if event.index == progress.BATCH:
                self._refresh()
            else:
                self.rows[event.index].show_item(self.tracker.items[event.index])
                self._refresh()

    def _start(self, started: progress.BatchStarted) -> None:
        self.tracker = progress.Tracker(started)
        self.result = None
        while self.rows_layout.count():
            widget = self.rows_layout.takeAt(0).widget()
            if widget is not None:
                widget.deleteLater()
        self.rows = []
        for item in self.tracker.items:
            row = ItemRow(item.item.name)
            row.show_item(item)
            self.rows_layout.addWidget(row)
            self.rows.append(row)
        self.rows_layout.addStretch(1)
        self.title.setText(self._title)
        self.result_box.hide()
        self.stop_button.setEnabled(True)
        for button in (self.stop_button, self.cancel_button):
            button.show()
        for button in (self.retry_button, self.close_button):
            button.hide()
        self._clock.start()
        self._timer.start()
        self._tick()
        self._refresh()

    def _on_finished(self, result: object) -> None:
        self._armed = False  # lượt vừa xong không phải lượt chạy mục (ví dụ việc Python) thì bỏ hẹn
        if not self.running:
            return
        self._timer.stop()
        self._tick()
        self.result = result if isinstance(result, BatchResult) else BatchResult()
        for button in (self.stop_button, self.cancel_button):
            button.hide()
        failed = self.tracker.count(progress.FAILED)
        self.retry_button.setVisible(self.can_retry and failed > 0)
        self.close_button.show()
        self._refresh()
        self._show_result()
        self.completed.emit(self.result)

    def _stop(self) -> None:
        self.controller.stop_after_current()
        self.stop_button.setEnabled(False)

    # ------------------------------------------------------------ vẽ

    def _tick(self) -> None:
        if self.tracker is not None:
            self.clock.setText(f"đã chạy {elapsed_text(self._clock.elapsed() // 1000)}")

    def _refresh(self) -> None:
        tracker = self.tracker
        if tracker is None:
            return
        done = self.result is not None
        self.headline.setText(self._summary() if done else tracker.headline())
        self.bar.setValue(int(tracker.fraction * 1000))
        parts = [f"Xong {tracker.count(progress.OK)}"]
        if not done:
            parts += [f"Đang chạy {tracker.count(progress.RUNNING)}", f"Chờ {tracker.count(progress.WAITING)}"]
        parts.append(f"Lỗi {tracker.count(progress.FAILED)}")
        for state, label in ((progress.SKIPPED, "Bỏ qua"), (progress.CANCELLED, "Đã dừng")):
            if tracker.count(state):
                parts.append(f"{label} {tracker.count(state)}")
        self.counts.setText(" · ".join(parts))
        kind = "running"
        if done:
            kind = "ok" if tracker.count(progress.FAILED) == 0 and not self.result.cancelled else "warn"
        self.bar.setProperty("kind", kind)
        _repolish(self.bar)

    def _summary(self) -> str:
        tracker = self.tracker
        ok, failed, total = tracker.count(progress.OK), tracker.count(progress.FAILED), tracker.total
        if self.result.cancelled:
            return f"Đã dừng: xong {ok}/{total} mục"
        if failed:
            return f"Xong {ok}/{total} mục, {failed} mục lỗi"
        return f"Đã xong {ok}/{total} mục" if ok == total else f"Xong {ok}/{total} mục (bỏ qua {total - ok})"

    def _show_result(self) -> None:
        tracker, result = self.tracker, self.result
        failed = [item for item in tracker.items if item.state == progress.FAILED]
        lines = []
        if failed:
            lines.append("<b>Mục lỗi:</b>")
            lines += [f"✖ {html.escape(item.item.name)}: "
                      f"{html.escape(item.message or 'lỗi, xem chi tiết trong khung log')}" for item in failed]
        if result.reboot_required:
            lines.append("<b>Cần khởi động lại máy</b> để hoàn tất.")
        hint = self.hint_for(result) if self.hint_for else ""
        if hint:
            lines.append(html.escape(hint))
        if not lines:
            lines.append("Mọi mục đã chạy xong, không có lỗi.")
        self.result_box.setProperty("kind", "warn" if failed or result.cancelled else "ok")
        self.result_box.setText("<br>".join(lines))
        self.result_box.show()
        _repolish(self.result_box)
