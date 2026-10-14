"""Thẻ một phần mềm ở trang Cài phần mềm (mockup 4): chữ viết tắt, tên, một câu giải thích, trạng thái, ô chọn.

Bấm vào chỗ nào trên thẻ (hoặc phím cách khi thẻ đang được chọn bằng Tab) là chọn / bỏ chọn. Thẻ bị khoá (đã cài,
không cài được) thì không chọn được, dòng trạng thái nói lý do.
"""

from __future__ import annotations

import re

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout

from ...software.catalog import App
from .. import theme

STATE_COLORS = {"on": theme.OK, "ok": theme.OK, "off": theme.TEXT_SECONDARY, "blocked": theme.WARN, "error": theme.BAD}


def initials(name: str) -> str:
    """"Google Chrome" → "GC", "7-Zip" → "7Z", "UniKey" → "UK"."""
    words = [word for word in re.split(r"[\s\-_.|()]+", name) if word]
    if len(words) >= 2:
        return (words[0][0] + words[1][0]).upper()
    capitals = [char for char in name if char.isupper() or char.isdigit()]
    return ("".join(capitals[:2]) if len(capitals) >= 2 else name[:2]).upper()


def _repolish(widget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)


class AppCard(QFrame):
    toggled = Signal(bool)

    def __init__(self, app: App):
        super().__init__()
        self.app = app
        self._checked = False
        self._enabled = True
        self.setObjectName("AppCard")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName(app.name)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(12)
        mark = QLabel(initials(app.name))
        mark.setObjectName("AppMark")
        mark.setFixedSize(36, 36)
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        texts = QVBoxLayout()
        texts.setSpacing(2)
        self.name = QLabel(app.name)
        self.name.setObjectName("AppName")
        self.name.setWordWrap(True)
        description = (app.description or app.group).split(". ")[0].strip().rstrip(".")
        self.description = QLabel(description)
        self.description.setObjectName("AppText")
        self.description.setWordWrap(True)
        self.state = QLabel()
        self.state.setObjectName("AppState")
        texts.addWidget(self.name)
        texts.addWidget(self.description)
        texts.addWidget(self.state)
        texts.addStretch(1)
        self.box = QLabel()
        self.box.setObjectName("AppBox")
        self.box.setFixedSize(18, 18)
        self.box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(mark, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(texts, 1)
        layout.addWidget(self.box, 0, Qt.AlignmentFlag.AlignTop)
        self.setToolTip(app.description or app.name)
        self._paint()

    # ------------------------------------------------------------ trạng thái

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, checked: bool) -> None:
        checked = bool(checked) and self._enabled
        if checked != self._checked:
            self._checked = checked
            self._paint()
            self.toggled.emit(checked)

    def set_state(self, text: str, kind: str, note: str = "", enabled: bool = True) -> None:
        """Dòng trạng thái (Đã cài, Cần kho bộ cài…) và có chọn được không."""
        self.state.setText(text)
        self.state.setStyleSheet(f"color: {STATE_COLORS.get(kind, theme.TEXT_SECONDARY)}; font-size: 9pt;")
        self.state.setToolTip(note)
        self._enabled = enabled
        self.setCursor(Qt.CursorShape.PointingHandCursor if enabled else Qt.CursorShape.ArrowCursor)
        if not enabled and self._checked:
            self._checked = False
            self.toggled.emit(False)
        self._paint()

    @property
    def state_text(self) -> str:
        return self.state.text()

    def _paint(self) -> None:
        self.setProperty("checked", self._checked)
        self.setProperty("locked", not self._enabled)
        self.box.setText("✓" if self._checked else "")
        for widget in (self, self.box):
            _repolish(widget)

    # ------------------------------------------------------------ chuột, bàn phím

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._enabled:
            self.setChecked(not self._checked)
        super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter) and self._enabled:
            self.setChecked(not self._checked)
            return
        super().keyPressEvent(event)
