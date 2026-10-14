"""Nhóm thẻ chọn một (ví dụ chọn bản Office): mỗi thẻ có tên, một dòng ghi chú, có thể bị khoá kèm lý do."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

COLUMNS = 5


@dataclass(frozen=True)
class ChoiceOption:
    key: str           # "" = không chọn gì (ví dụ "Không cài")
    title: str
    note: str = ""
    enabled: bool = True
    tooltip: str = ""


def _repolish(widget: QWidget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)


class ChoiceCard(QFrame):
    def __init__(self, option: ChoiceOption, group: QButtonGroup):
        super().__init__()
        self.option = option
        self.setObjectName("ChoiceCard")
        self.setToolTip(option.tooltip)
        self.setCursor(Qt.CursorShape.PointingHandCursor if option.enabled else Qt.CursorShape.ArrowCursor)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(3)
        self.radio = QRadioButton(option.title)
        self.radio.setObjectName("ChoiceTitle")
        self.radio.setEnabled(option.enabled)
        self.note = QLabel(option.note)
        self.note.setObjectName("ChoiceNote")
        self.note.setWordWrap(True)
        layout.addWidget(self.radio)
        layout.addWidget(self.note)
        layout.addStretch(1)
        group.addButton(self.radio)
        self.radio.toggled.connect(self._toggled)
        self.setProperty("disabled", not option.enabled)
        self._toggled(False)

    def _toggled(self, checked: bool) -> None:
        self.setProperty("checked", checked)
        _repolish(self)

    def mousePressEvent(self, event) -> None:  # bấm vào chỗ nào trên thẻ cũng chọn
        if self.option.enabled:
            self.radio.setChecked(True)
        super().mousePressEvent(event)


class ChoiceGroup(QFrame):
    changed = Signal(str)  # key của thẻ vừa chọn

    def __init__(self, title: str, subtitle: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)
        head = QHBoxLayout()
        self.title = QLabel(title)
        self.title.setObjectName("CardTitle")
        self.subtitle = QLabel(subtitle)
        self.subtitle.setObjectName("PageSubtitle")
        self.subtitle.setWordWrap(True)
        head.addWidget(self.title)
        head.addSpacing(8)
        head.addWidget(self.subtitle, 1)
        layout.addLayout(head)
        self.grid = QGridLayout()
        self.grid.setSpacing(8)
        layout.addLayout(self.grid)
        self.warning = QFrame()
        self.warning.setObjectName("Banner")
        self.warning.setProperty("kind", "warn")
        warning_layout = QHBoxLayout(self.warning)
        warning_layout.setContentsMargins(12, 8, 12, 8)
        self.warning_text = QLabel()
        self.warning_text.setWordWrap(True)
        self.warning_check = QCheckBox()
        warning_layout.addWidget(self.warning_text, 1)
        warning_layout.addWidget(self.warning_check)
        self.warning.hide()
        layout.addWidget(self.warning)
        self.buttons = QButtonGroup(self)
        self.buttons.setExclusive(True)
        self.cards: list[ChoiceCard] = []

    def set_options(self, options: list[ChoiceOption], selected: str = "") -> None:
        for card in self.cards:
            self.buttons.removeButton(card.radio)
            card.deleteLater()
        self.cards = []
        for index, option in enumerate(options):
            card = ChoiceCard(option, self.buttons)
            card.radio.toggled.connect(lambda checked, key=option.key: checked and self.changed.emit(key))
            self.grid.addWidget(card, index // COLUMNS, index % COLUMNS)
            self.cards.append(card)
        for column in range(COLUMNS):
            self.grid.setColumnStretch(column, 1)
        if not self.select(selected):
            self.select("")

    def select(self, key: str) -> bool:
        """Chọn thẻ `key` nếu có và không bị khoá."""
        card = next((card for card in self.cards if card.option.key == key), None)
        if card is None or not card.option.enabled:
            return False
        card.radio.setChecked(True)
        return True

    def selected(self) -> str:
        return next((card.option.key for card in self.cards if card.radio.isChecked()), "")

    def show_warning(self, text: str, check_text: str = "", checked: bool = True) -> None:
        """Cảnh báo dưới các thẻ; `check_text` rỗng thì không có ô tick."""
        self.warning_text.setText(text)
        self.warning_check.setText(check_text)
        self.warning_check.setVisible(bool(check_text))
        self.warning_check.setChecked(checked)
        self.warning.show()

    def hide_warning(self) -> None:
        self.warning.hide()
