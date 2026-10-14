"""Bảng tìm chức năng (Ctrl+K): gõ việc cần làm, ra tình huống, mục sửa lỗi, công cụ, phần mềm, trang.

Enter hoặc bấm vào một dòng: đóng bảng và mở đúng chỗ (trang, tab, mục được chọn sẵn). Không tự chạy gì.
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QEvent, QObject, QSize, Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...core import search
from .. import icons, theme

TARGET_ROLE = Qt.ItemDataRole.UserRole
EMPTY_HINT = "Gõ việc cần làm, ví dụ: máy in không in được, mạng chậm, cài office, 0x0000011b"


class ResultRow(QWidget):
    def __init__(self, entry: search.Entry):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 7, 10, 7)
        layout.setSpacing(12)
        mark = QLabel()
        mark.setObjectName("PaletteKind")
        mark.setFixedSize(34, 34)
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark.setPixmap(icons.pixmap(entry.icon or "chevron", theme.ACCENT, 18))
        texts = QVBoxLayout()
        texts.setSpacing(1)
        title = QLabel(entry.title)
        title.setObjectName("PaletteTitle")
        texts.addWidget(title)
        if entry.description:
            description = QLabel(entry.description.split("\n")[0])
            description.setObjectName("PaletteText")
            metrics = description.fontMetrics()
            description.setText(metrics.elidedText(description.text(), Qt.TextElideMode.ElideRight, 600))
            texts.addWidget(description)
        where = QLabel(f"{entry.kind_label} · {entry.where}" if entry.where else entry.kind_label)
        where.setObjectName("PaletteWhere")
        texts.addWidget(where)
        layout.addWidget(mark, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(texts, 1)


class CommandPalette(QDialog):
    activated = Signal(str)  # đích, ví dụ "action:net.flush_dns"

    def __init__(self, parent: QWidget, build_index: Callable[[], search.Index], basic_mode: Callable[[], bool]):
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.build_index = build_index
        self.basic_mode = basic_mode
        self.index: search.Index | None = None
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        frame = QFrame()
        frame.setObjectName("Palette")
        outer.addWidget(frame)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.input = QLineEdit()
        self.input.setPlaceholderText("Tìm chức năng, gõ không dấu cũng được")
        self.input.addAction(icons.icon("search", theme.TEXT_SECONDARY), QLineEdit.ActionPosition.LeadingPosition)
        self.count = QLabel()
        self.count.setObjectName("PaletteCount")
        self.list = QListWidget()
        self.list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        foot = QLabel("↑ ↓ chọn · Enter mở · Esc đóng · tìm được cả mã lỗi (0x0000011b) và tên phần mềm")
        foot.setObjectName("PaletteFoot")
        layout.addWidget(self.input)
        layout.addWidget(self.count)
        layout.addWidget(self.list, 1)
        layout.addWidget(foot)
        self.input.textChanged.connect(self.refresh)
        self.input.installEventFilter(self)
        self.list.itemActivated.connect(self._activate_item)
        self.list.itemClicked.connect(self._activate_item)

    # ------------------------------------------------------------ mở / tìm

    def open_with(self, query: str = "") -> None:
        self.index = self.build_index()
        parent = self.parentWidget()
        width = min(760, max(520, parent.width() - 120))
        height = min(560, max(360, parent.height() - 140))
        top_left = parent.mapToGlobal(parent.rect().topLeft())
        self.setGeometry(top_left.x() + (parent.width() - width) // 2, top_left.y() + 64, width, height)
        self.input.setText(query)
        self.refresh(query)
        self.show()
        self.raise_()
        self.activateWindow()
        self.input.setFocus()
        self.input.selectAll()

    def refresh(self, query: str | None = None) -> None:
        query = self.input.text() if query is None else query
        self.list.clear()
        if self.index is None:
            return
        if not query.strip():
            self.count.setText(EMPTY_HINT)
            results = [entry for entry in self.index.entries if entry.kind == "page"]
            hidden = 0
        else:
            results, hidden = self.index.search(query, include_advanced=not self.basic_mode())
            text = f"{len(results)} kết quả" if results else "Không thấy chức năng nào khớp. Thử gõ ngắn hơn: máy in, mạng, office"
            if hidden:
                text += f" · {hidden} mục Nâng cao đang ẩn (bật chế độ Chuyên gia để thấy)"
            self.count.setText(text)
        for entry in results:
            row = ResultRow(entry)
            item = QListWidgetItem(self.list)
            item.setData(TARGET_ROLE, entry.target)
            item.setSizeHint(QSize(0, row.sizeHint().height()))
            self.list.setItemWidget(item, row)
        if self.list.count():
            self.list.setCurrentRow(0)

    def results(self) -> list[str]:
        return [self.list.item(row).data(TARGET_ROLE) for row in range(self.list.count())]

    # ------------------------------------------------------------ bàn phím

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self.input and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key in (Qt.Key.Key_Down, Qt.Key.Key_Up, Qt.Key.Key_PageDown, Qt.Key.Key_PageUp):
                step = {Qt.Key.Key_Down: 1, Qt.Key.Key_Up: -1, Qt.Key.Key_PageDown: 5, Qt.Key.Key_PageUp: -5}[key]
                if self.list.count():
                    row = max(0, min(self.list.count() - 1, self.list.currentRow() + step))
                    self.list.setCurrentRow(row)
                return True
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.activate_current()
                return True
        return super().eventFilter(watched, event)

    def activate_current(self) -> None:
        item = self.list.currentItem()
        if item is not None:
            self._activate_item(item)

    def _activate_item(self, item: QListWidgetItem) -> None:
        target = item.data(TARGET_ROLE)
        self.hide()
        self.activated.emit(target)
