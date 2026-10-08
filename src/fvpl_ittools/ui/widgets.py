"""Các widget nhỏ dùng chung giữa các trang."""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLayout, QWidget


def page_header(layout: QLayout, title: str, subtitle: str) -> None:
    title_label = QLabel(title)
    title_label.setObjectName("PageTitle")
    subtitle_label = QLabel(subtitle)
    subtitle_label.setObjectName("PageSubtitle")
    subtitle_label.setWordWrap(True)
    layout.addWidget(title_label)
    layout.addWidget(subtitle_label)


def badge(text: str, kind: str) -> QLabel:
    """Nhãn bo tròn; kind: safe / caution / advanced / neutral / warn (màu khai báo trong theme)."""
    label = QLabel(text)
    label.setProperty("badge", kind)
    return label


def chip(text: str, kind: str = "normal") -> QLabel:
    """Nhãn trên thanh trên cùng; kind: normal / ok / bad / warn."""
    label = QLabel(text)
    label.setProperty("chip", kind)
    return label


def badge_row(badges: list[QLabel]) -> QWidget:
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(6)
    for item in badges:
        layout.addWidget(item)
    layout.addStretch(1)
    return row


def selectable(label: QLabel) -> QLabel:
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return label


def open_path(path: Path | str | None) -> None:
    """Mở file hoặc thư mục bằng chương trình mặc định của Windows."""
    if path and os.path.exists(path):
        os.startfile(str(path))  # noqa: S606 - chỉ mở đường dẫn do tool tự tạo
