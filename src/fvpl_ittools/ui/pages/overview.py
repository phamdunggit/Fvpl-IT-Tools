"""Trang Tổng quan (bản GĐ0: thông tin cơ bản; phần cứng, bảo mật, xuất thông tin làm ở GĐ1)."""

from __future__ import annotations

from PySide6.QtWidgets import QFormLayout, QFrame, QLabel, QVBoxLayout, QWidget

from ... import __version__
from ...app import AppContext
from ...core import paths
from ..widgets import page_header, selectable


class OverviewPage(QWidget):
    def __init__(self, app: AppContext):
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 12)
        root.setSpacing(10)
        page_header(
            root, "Tổng quan",
            "Thông tin cơ bản của máy. Phần cứng, bảo mật và nút xuất thông tin sẽ có ở GĐ1.",
        )

        card = QFrame()
        card.setObjectName("Card")
        form = QFormLayout(card)
        form.setContentsMargins(18, 16, 18, 16)
        form.setHorizontalSpacing(24)
        form.setVerticalSpacing(10)

        machine, env, site = app.machine, app.env, app.site
        rows = [
            ("Tên máy", machine.computer_name),
            ("Domain / Workgroup", machine.domain_label),
            ("Windows", machine.os_label),
            ("Quyền admin", "Có" if env.is_admin else "Không (một số mục sẽ bị khoá)"),
            ("Người đang đăng nhập", env.target_user.name),
            ("Tool chạy bằng tài khoản", env.process_user.name + ("  (khác người đang đăng nhập)" if app.runs_as_other_user else "")),
            ("Cấu hình site", str(site.source) if site.loaded else "Chưa có site.yaml (xem site.example.yaml)"),
            ("Số mục đã nạp", f"{len(app.actions)}" + (f"  ({len(app.load_errors)} mục khai báo sai, xem log)" if app.load_errors else "")),
            ("Thư mục dữ liệu", str(paths.state_dir())),
            ("File log phiên này", str(app.log_file) if app.log_file else "(không ghi log)"),
            ("Phiên bản tool", __version__),
        ]
        for key, value in rows:
            key_label = QLabel(key)
            key_label.setObjectName("FormKey")
            value_label = selectable(QLabel(value))
            value_label.setWordWrap(True)
            form.addRow(key_label, value_label)
        root.addWidget(card)
        root.addStretch(1)
