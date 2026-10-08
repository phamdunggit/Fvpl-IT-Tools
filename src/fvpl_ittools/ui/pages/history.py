"""Trang Nhật ký: các thay đổi registry tool đã làm (hoàn tác được) và file log."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...app import AppContext
from ...core import paths
from ..controller import RunController
from ..widgets import open_path, page_header, selectable

ENTRY_ID_ROLE = Qt.ItemDataRole.UserRole
COLUMNS = ["Thời gian", "Mục", "Áp cho", "Chạy bởi", "Số thay đổi", "Trạng thái"]


class HistoryPage(QWidget):
    def __init__(self, app: AppContext, controller: RunController):
        super().__init__()
        self.app = app
        self.controller = controller
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 12)
        root.setSpacing(10)
        page_header(
            root, "Nhật ký",
            "Các thay đổi registry tool đã làm trên máy này. Chọn dòng rồi bấm Hoàn tác để trả về như cũ.",
        )

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        root.addWidget(self.table, 1)

        buttons = QHBoxLayout()
        self.undo_button = QPushButton("Hoàn tác mục đã chọn")
        self.undo_button.setObjectName("Primary")
        refresh_button = QPushButton("Làm mới")
        buttons.addWidget(self.undo_button)
        buttons.addWidget(refresh_button)
        buttons.addStretch(1)
        open_log = QPushButton("Mở file log phiên này")
        open_folder = QPushButton("Mở thư mục log")
        buttons.addWidget(open_log)
        buttons.addWidget(open_folder)
        root.addLayout(buttons)

        log_label = selectable(QLabel(f"File log phiên này: {app.log_file or '(không ghi log)'}"))
        log_label.setObjectName("PageSubtitle")
        root.addWidget(log_label)

        self.undo_button.clicked.connect(self._undo_selected)
        refresh_button.clicked.connect(self.refresh)
        open_log.clicked.connect(lambda: open_path(app.log_file))
        open_folder.clicked.connect(lambda: open_path(paths.logs_dir()))
        self.table.itemSelectionChanged.connect(self._update_buttons)
        controller.journal_changed.connect(self.refresh)
        controller.busy_changed.connect(lambda _busy: self._update_buttons())
        self.refresh()

    def refresh(self) -> None:
        entries = self.app.journal.entries()
        self.table.setRowCount(len(entries))
        for row, entry in enumerate(entries):
            status = f"Đã hoàn tác {entry.undone_label}" if entry.undone else "Đang áp dụng"
            values = [entry.time_label, entry.action_name, entry.target_user, entry.run_by, str(len(entry.changes)), status]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(ENTRY_ID_ROLE, entry.id)
                if entry.undone:
                    item.setForeground(QBrush(QColor("#94a3b8")))
                self.table.setItem(row, column, item)
        self._update_buttons()

    def showEvent(self, event) -> None:
        self.refresh()
        super().showEvent(event)

    def _selected_ids(self) -> list[str]:
        rows = sorted({index.row() for index in self.table.selectionModel().selectedRows()})
        ids = [self.table.item(row, 0).data(ENTRY_ID_ROLE) for row in rows]
        undone = {entry.id for entry in self.app.journal.entries() if entry.undone}
        return [entry_id for entry_id in ids if entry_id not in undone]

    def _update_buttons(self) -> None:
        self.undo_button.setEnabled(not self.controller.busy and bool(self._selected_ids()))

    def _undo_selected(self) -> None:
        ids = self._selected_ids()
        if not ids:
            return
        answer = QMessageBox.question(self, "Hoàn tác", f"Trả {len(ids)} lần chạy đã chọn về như trước?")
        if answer == QMessageBox.StandardButton.Yes:
            self.controller.undo(ids)
