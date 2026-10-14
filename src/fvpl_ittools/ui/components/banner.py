"""Banner một dòng đầu trang: thông tin / cảnh báo / ổn, kèm một nút (ví dụ kho bộ cài + "Chọn kho…")."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

MARKS = {"ok": "✔", "warn": "⚠", "bad": "✖", "info": "ⓘ"}


class Banner(QFrame):
    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Banner")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(12)
        self.mark = QLabel()
        self.mark.setObjectName("BannerMark")
        texts = QVBoxLayout()
        texts.setSpacing(2)
        self.title = QLabel()
        self.title.setObjectName("BannerTitle")
        self.title.setWordWrap(True)
        self.text = QLabel()
        self.text.setObjectName("BannerText")
        self.text.setWordWrap(True)
        texts.addWidget(self.title)
        texts.addWidget(self.text)
        self.button = QPushButton()
        self.button.clicked.connect(self.clicked)
        layout.addWidget(self.mark)
        layout.addLayout(texts, 1)
        layout.addWidget(self.button)

    def show_state(self, kind: str, title: str, text: str = "", button: str = "", primary: bool = False) -> None:
        """kind: ok / warn / bad / info. `primary`: nút màu nhấn (việc nên làm ngay)."""
        self.setProperty("kind", kind)
        self.mark.setText(MARKS.get(kind, ""))
        self.title.setText(title)
        self.text.setText(text)
        self.text.setVisible(bool(text))
        self.button.setText(button)
        self.button.setVisible(bool(button))
        self.button.setObjectName("Primary" if primary else "")
        for widget in (self, self.mark, self.button):
            widget.style().unpolish(widget)
            widget.style().polish(widget)
