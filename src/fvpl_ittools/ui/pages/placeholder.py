"""Trang chưa làm: ghi rõ sẽ làm ở giai đoạn nào và gồm những gì (theo PLAN.md)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from ..widgets import page_header


class PlaceholderPage(QWidget):
    def __init__(self, title: str, subtitle: str, phase: str, items: list[str]):
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 12)
        root.setSpacing(10)
        page_header(root, title, subtitle)
        bullets = "".join(f"<li>{item}</li>" for item in items)
        body = QLabel(f"<b>Sẽ làm ở {phase}</b> (xem PLAN.md):<ul>{bullets}</ul>")
        body.setObjectName("EmptyState")
        body.setWordWrap(True)
        body.setTextFormat(Qt.TextFormat.RichText)
        root.addWidget(body)
        root.addStretch(1)
