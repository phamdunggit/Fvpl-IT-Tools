"""Hướng dẫn nhanh 3 bước, hiện lần đầu mở tool (KE-HOACH-GIAO-DIEN.md mục 7, đợt P3). Xem lại bằng phím F1."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from ... import APP_NAME
from .. import icons, theme

STEPS = (
    ("home", "Trang chủ: chọn việc cần làm",
     "Mỗi ô là một việc hay gặp (không in được, mất mạng, cài phần mềm…). Tool kiểm tra máy, đề xuất cách sửa an "
     "toàn, sửa xong tự kiểm tra lại."),
    ("search", "Ctrl+K: tìm mọi chức năng",
     "Gõ việc cần làm, gõ không dấu hay gõ cả mã lỗi (0x0000011b) cũng được. Enter mở đúng chỗ, không tự chạy gì."),
    ("settings", "Cơ bản hay Chuyên gia",
     "Cơ bản (góc trên bên phải) cho người hỗ trợ: tên dễ hiểu, ẩn mục rủi ro. Chuyên gia cho IT: đủ mọi mục, "
     "mở sẵn chi tiết kỹ thuật (log)."),
)


class WelcomeDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Chào mừng đến {APP_NAME}")
        self.setMinimumWidth(820)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 18)
        layout.setSpacing(14)
        title = QLabel(f"Chào mừng đến {APP_NAME}")
        title.setObjectName("PageTitle")
        subtitle = QLabel("3 điều cần biết để bắt đầu. Xem lại bất cứ lúc nào bằng phím F1.")
        subtitle.setObjectName("PageSubtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)
        row = QHBoxLayout()
        row.setSpacing(12)
        for number, (icon_name, heading, text) in enumerate(STEPS, start=1):
            card = QFrame()
            card.setObjectName("Card")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(16, 16, 16, 16)
            card_layout.setSpacing(8)
            mark = QLabel()
            mark.setObjectName("TileIcon")
            mark.setFixedSize(40, 40)
            mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
            mark.setPixmap(icons.pixmap(icon_name, theme.ACCENT, 22))
            head = QLabel(f"{number}. {heading}")
            head.setObjectName("CardTitle")
            head.setWordWrap(True)
            body = QLabel(text)
            body.setObjectName("PageSubtitle")
            body.setWordWrap(True)
            card_layout.addWidget(mark)
            card_layout.addWidget(head)
            card_layout.addWidget(body)
            card_layout.addStretch(1)
            row.addWidget(card, 1)
        layout.addLayout(row)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.start_button = QPushButton("Bắt đầu")
        self.start_button.setObjectName("Primary")
        self.start_button.setMinimumWidth(120)
        self.start_button.clicked.connect(self.accept)
        buttons.addWidget(self.start_button)
        layout.addLayout(buttons)
