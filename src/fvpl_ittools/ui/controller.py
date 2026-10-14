"""Cầu nối giữa giao diện và executor: chạy ở thread nền, đẩy log về giao diện qua Qt signal."""

from __future__ import annotations

import logging
import threading
from typing import Callable

from PySide6.QtCore import QObject, Signal

from ..actions.model import Action
from ..app import AppContext
from ..core import executor
from ..core.executor import ActionResult, BatchResult, Level, LogEvent, RunContext

log = logging.getLogger(__name__)


class RunController(QObject):
    event = Signal(object)              # LogEvent
    progress = Signal(object)           # progress.BatchStarted / progress.ItemUpdate
    busy_changed = Signal(bool)
    finished = Signal(object)           # BatchResult, list[bool] (hoàn tác) hoặc None khi lỗi
    journal_changed = Signal()
    restore_point_changed = Signal(bool)
    _done = Signal(object)

    def __init__(self, app: AppContext, parent: QObject | None = None):
        super().__init__(parent)
        self.app = app
        self._create_restore_point = True
        self._cancel = threading.Event()
        self._stop_after = threading.Event()
        self._worker: threading.Thread | None = None
        self.last_results: dict[str, ActionResult] = {}
        self._done.connect(self._on_done)

    # ------------------------------------------------------------ thiết lập

    @property
    def create_restore_point(self) -> bool:
        return self._create_restore_point

    def set_create_restore_point(self, value: bool) -> None:
        if value != self._create_restore_point:
            self._create_restore_point = value
            self.restore_point_changed.emit(value)

    @property
    def busy(self) -> bool:
        return self._worker is not None

    # ------------------------------------------------------------ lệnh

    def say(self, level: Level, text: str) -> None:
        self.event.emit(LogEvent(level, text))

    def preview(self, actions: list[Action]) -> None:
        for line in executor.preview(actions, self.app.env):
            self.say(Level.INFO, line)

    def run(self, actions: list[Action], credential: tuple[str, str] | None = None,
            stop_on_error: bool = False) -> None:
        """Chạy ở thread nền. `credential` chỉ sống trong lượt chạy này, không lưu lại."""
        if actions:
            ctx = self._context()
            ctx.credential = credential
            self._start(lambda: executor.run_batch(actions, ctx, stop_on_error=stop_on_error))

    def run_job(self, job: Callable[[RunContext], object]) -> None:
        """Chạy một việc viết bằng Python (ví dụ dọn rác) ở thread nền, dùng chung khung log, nút Huỷ, trạng thái bận."""
        ctx = self._context()
        self._start(lambda: job(ctx))

    def run_undo_steps(self, action: Action) -> None:
        ctx = self._context()
        self._start(lambda: BatchResult(results=[executor.run_undo_steps(action, ctx)]))

    def undo(self, entry_ids: list[str]) -> None:
        if entry_ids:
            ctx = self._context()
            self._start(lambda: [executor.undo_entry(entry_id, ctx) for entry_id in entry_ids])

    def cancel(self) -> None:
        if self.busy and not self._cancel.is_set():
            self._cancel.set()
            self.say(Level.WARN, "Đang huỷ…")

    def stop_after_current(self) -> None:
        """Chạy nốt mục đang chạy (không cắt ngang bộ cài), các mục sau không chạy nữa."""
        if self.busy and not self._stop_after.is_set():
            self._stop_after.set()
            self.say(Level.WARN, "Sẽ dừng sau khi xong mục đang chạy.")

    @property
    def stopping(self) -> bool:
        return self._stop_after.is_set() or self._cancel.is_set()

    def wait(self, timeout: float) -> None:
        worker = self._worker
        if worker is not None:
            worker.join(timeout)

    # ------------------------------------------------------------ nội bộ

    def _context(self) -> RunContext:
        return RunContext(
            env=self.app.env,
            journal=self.app.journal,
            emit=self.event.emit,
            cancel=self._cancel,
            create_restore_point=self._create_restore_point,
            report=self.progress.emit,
            stop_after=self._stop_after,
        )

    def _start(self, job: Callable[[], object]) -> None:
        if self.busy:
            self.say(Level.WARN, "Đang có việc chạy, chờ xong rồi bấm lại.")
            return
        self._cancel.clear()
        self._stop_after.clear()

        def worker() -> None:
            result = None
            try:
                result = job()
            except Exception:
                log.exception("Lỗi không mong muốn khi chạy")
                self.say(Level.ERROR, "Lỗi không mong muốn, xem chi tiết trong file log.")
            finally:
                self._done.emit(result)

        self._worker = threading.Thread(target=worker, name="fvpl-runner", daemon=True)
        self.busy_changed.emit(True)
        self._worker.start()

    def _on_done(self, result: object) -> None:
        self._worker = None
        if isinstance(result, BatchResult):
            for item in result.results:
                self.last_results[item.action.id] = item
        self.busy_changed.emit(False)
        self.journal_changed.emit()
        self.finished.emit(result)
