"""Các widget nhỏ dùng chung giữa các trang."""

from __future__ import annotations

import logging
import os
import subprocess
import threading
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLayout, QSizePolicy, QWidget

from ..core import shell

log = logging.getLogger(__name__)


class Worker(QObject):
    """Chạy một hàm ở thread nền, trả kết quả (hoặc Exception) qua signal `done`.

    Lỗi RuntimeError / OSError là lỗi dự kiến (có lời báo tiếng Việt), không ghi traceback vào log.
    """
    done = Signal(str, object)  # tên việc, kết quả hoặc Exception

    def run(self, name: str, fn) -> None:
        def work() -> None:
            try:
                result = fn()
            except Exception as exc:
                if not isinstance(exc, (RuntimeError, OSError)):
                    log.exception("Lỗi khi chạy %s", name)
                result = exc
            self.done.emit(name, result)
        threading.Thread(target=work, name=f"worker-{name}", daemon=True).start()


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
    label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)  # không bị ép đè lên nhãn bên cạnh
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


def open_as_user(path: Path | str) -> None:
    """Mở file qua explorer.exe: chương trình mở file (trình duyệt...) chạy bằng quyền của người đang
    đăng nhập, không thừa hưởng quyền admin của tool."""
    explorer = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "explorer.exe")
    subprocess.Popen([explorer, str(path)], creationflags=shell.CREATE_NO_WINDOW)
