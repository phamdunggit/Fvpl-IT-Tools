"""Trang Tổng quan: thông tin máy (hệ điều hành, phần cứng, mạng, bảo mật), copy và xuất HTML.

Phần đọc nhanh (tên máy, domain, bản Windows) hiện ngay; phần còn lại do 4 script PowerShell chạy
song song ở nền, phần nào xong thì hiện phần đó (core/inventory.py).
"""

from __future__ import annotations

import html
import logging
import threading
from datetime import datetime

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QTextBrowser, QVBoxLayout, QWidget

from ... import __version__
from ...app import AppContext
from ...core import inventory, paths
from ...core.executor import Level
from ..controller import RunController
from ..widgets import open_as_user, page_header

log = logging.getLogger(__name__)


class InventoryLoader(QObject):
    """Chạy các phần thu thập ở thread nền. Kết quả của lượt cũ (trước khi bấm Làm mới) bị bỏ qua."""

    part_done = Signal(int, str, object, bool)  # lượt, phần, dữ liệu hoặc thông báo lỗi, thành công

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self.generation = 0
        self._cancel = threading.Event()

    def start(self) -> int:
        self._cancel.set()
        self._cancel = threading.Event()
        self.generation += 1
        for part in inventory.PARTS:
            threading.Thread(
                target=self._work, args=(self.generation, part, self._cancel), name=f"inventory-{part}", daemon=True
            ).start()
        return self.generation

    def stop(self) -> None:
        self._cancel.set()

    def _work(self, generation: int, part: str, cancel: threading.Event) -> None:
        try:
            payload, ok = inventory.collect_part(part, cancel), True
        except inventory.InventoryError as exc:
            payload, ok = str(exc), False
        except Exception as exc:  # lỗi bất ngờ của một phần không được làm hỏng cả trang
            log.exception("Lỗi khi đọc thông tin máy (%s)", part)
            payload, ok = str(exc) or exc.__class__.__name__, False
        if not cancel.is_set():
            self.part_done.emit(generation, part, payload, ok)


_STATE_STYLE = {
    "ok": "color:#15803d", "warn": "color:#b45309", "bad": "color:#b91c1c; font-weight:600", "muted": "color:#7b8794",
}


def _card(title: str, rows) -> str:
    """Một thẻ thông tin bằng HTML của Qt (QTextBrowser chỉ hiểu một phần CSS, nên dùng bảng)."""
    lines = [
        "<table width='100%' cellspacing='0' cellpadding='12' bgcolor='#ffffff' style='border:1px solid #dde3ea'><tr><td>",
        f"<p style='font-size:11pt; font-weight:600; color:#102a43; margin:0 0 6px 0'>{html.escape(title)}</p>",
        "<table width='100%' cellspacing='0' cellpadding='3'>",
    ]
    for row in rows:
        style = _STATE_STYLE.get(row.state, "")
        lines.append(
            f"<tr><td width='34%' valign='top' style='color:#52606d'>{html.escape(row.label)}</td>"
            f"<td valign='top' style='{style}'>{html.escape(row.value)}</td></tr>"
        )
    lines.append("</table></td></tr></table>")
    return "".join(lines)


def render_html(sections: list[inventory.Section], tool_rows) -> str:
    """Hai cột: Hệ điều hành + Mạng bên trái, Phần cứng + Bảo mật bên phải, thẻ Công cụ ở dưới."""
    by_key = {section.key: section for section in sections}
    left = [by_key[key] for key in ("system", "network")]
    right = [by_key[key] for key in ("hardware", "security")]

    def column(items) -> str:
        return "<br>".join(_card(section.title, section.rows) for section in items)

    return (
        "<table width='100%' cellspacing='0' cellpadding='0'><tr>"
        f"<td width='50%' valign='top' style='padding-right:6px'>{column(left)}</td>"
        f"<td width='50%' valign='top' style='padding-left:6px'>{column(right)}</td>"
        "</tr></table><br>" + _card("Công cụ", tool_rows)
    )


class OverviewPage(QWidget):
    alerts_changed = Signal(list)

    def __init__(self, app: AppContext, controller: RunController):
        super().__init__()
        self.app = app
        self.controller = controller
        self.data: dict = {}
        self.failed: dict[str, str] = {}
        self.pending: set[str] = set()
        self.loaded_at: datetime | None = None
        self.loader = InventoryLoader(self)
        self.loader.part_done.connect(self._part_done)
        self._started = False

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 12)
        root.setSpacing(10)
        page_header(
            root, "Tổng quan",
            "Thông tin máy để kiểm tra nhanh và dán vào ticket. Phần chi tiết đọc nền trong vài giây.",
        )

        toolbar = QHBoxLayout()
        self.refresh_button = QPushButton("Làm mới")
        self.copy_button = QPushButton("Copy thông tin")
        self.copy_button.setToolTip("Copy dạng chữ để dán vào ticket, Zalo, email")
        self.export_button = QPushButton("Xuất HTML")
        self.export_button.setToolTip("Lưu thành file HTML trong thư mục reports rồi mở lên")
        self.status = QLabel()
        self.status.setObjectName("PageSubtitle")
        for button in (self.refresh_button, self.copy_button, self.export_button):
            toolbar.addWidget(button)
        toolbar.addSpacing(8)
        toolbar.addWidget(self.status, 1)
        root.addLayout(toolbar)

        self.view = QTextBrowser()
        self.view.setObjectName("InfoView")
        self.view.setOpenLinks(False)
        root.addWidget(self.view, 1)

        self.refresh_button.clicked.connect(self.refresh)
        self.copy_button.clicked.connect(self.copy_text)
        self.export_button.clicked.connect(self.export_html)
        self._render()

    # ------------------------------------------------------------ dữ liệu

    def basics(self) -> inventory.Basics:
        machine, env = self.app.machine, self.app.env
        return inventory.Basics(
            computer_name=machine.computer_name,
            domain_label=machine.domain_label,
            joined_domain=machine.joined_domain,
            os_label=machine.os_label,
            target_user=env.target_user.name,
            is_admin=env.is_admin,
        )

    def sections(self) -> list[inventory.Section]:
        return inventory.build_sections(self.data, self.basics(), self.failed)

    def _tool_rows(self) -> list[inventory.Row]:
        app, env, site = self.app, self.app.env, self.app.site
        account = env.process_user.name + ("  (khác người đang đăng nhập)" if app.runs_as_other_user else "")
        errors = f"  ({len(app.load_errors)} mục khai báo sai, xem log)" if app.load_errors else ""
        return [
            inventory.Row("Quyền admin", "Có" if env.is_admin else "Không (một số mục sẽ bị khoá)",
                          "" if env.is_admin else "warn"),
            inventory.Row("Tool chạy bằng tài khoản", account, "warn" if app.runs_as_other_user else ""),
            inventory.Row("Cấu hình site", str(site.source) if site.loaded else "Chưa có site.yaml (xem site.example.yaml)"),
            inventory.Row("Số mục đã nạp", f"{len(app.actions)} mục, {len(app.packs)} gói sửa nhanh{errors}"),
            inventory.Row("Thư mục dữ liệu", str(paths.state_dir())),
            inventory.Row("File log phiên này", str(app.log_file) if app.log_file else "(không ghi log)"),
            inventory.Row("Phiên bản tool", __version__),
        ]

    # ------------------------------------------------------------ nạp

    def showEvent(self, event) -> None:
        if not self._started:
            self._started = True
            self.refresh()
        super().showEvent(event)

    def refresh(self) -> None:
        self.failed = {}
        self.pending = set(inventory.PARTS)
        self.loader.start()
        self.refresh_button.setEnabled(False)
        self._render()

    def stop(self) -> None:
        self.loader.stop()

    @property
    def loading(self) -> bool:
        return bool(self.pending)

    def _part_done(self, generation: int, part: str, payload: object, ok: bool) -> None:
        if generation != self.loader.generation:
            return
        if ok:
            self.data.update(payload)
        else:
            self.failed[part] = str(payload)
        self.pending.discard(part)
        if not self.pending:
            self.loaded_at = datetime.now()
            self.refresh_button.setEnabled(True)
            for name, message in self.failed.items():
                self.controller.say(Level.WARN, f"Tổng quan: không đọc được phần {name}: {message}")
        self._render()
        self.alerts_changed.emit(inventory.alerts(self.data, self.basics()))

    def _render(self) -> None:
        # Giữ vị trí cuộn khi một phần đọc xong và trang được vẽ lại.
        scroll = self.view.verticalScrollBar().value()
        self.view.setHtml(render_html(self.sections(), self._tool_rows()))
        self.view.verticalScrollBar().setValue(scroll)
        if self.pending:
            self.status.setText(f"Đang đọc thông tin máy… ({len(inventory.PARTS) - len(self.pending)}/{len(inventory.PARTS)})")
        elif self.loaded_at is not None:
            note = f", {len(self.failed)} phần lỗi (xem khung log)" if self.failed else ""
            self.status.setText(f"Cập nhật lúc {self.loaded_at:%H:%M:%S}{note}")

    # ------------------------------------------------------------ copy / xuất

    def copy_text(self) -> None:
        QGuiApplication.clipboard().setText(inventory.to_text(self.sections(), self.basics()))
        note = " (một phần chưa đọc xong nên chưa có trong bản copy)" if self.pending else ""
        self.controller.say(Level.INFO, f"Đã copy thông tin máy vào clipboard{note}.")

    def export_html(self) -> None:
        basics = self.basics()
        file = paths.reports_dir() / f"ThongTinMay_{basics.computer_name}_{basics.now:%Y%m%d_%H%M%S}.html"
        file.write_text(inventory.to_html(self.sections(), basics, __version__), encoding="utf-8")
        self.controller.say(Level.OK, f"Đã xuất thông tin máy: {file}")
        open_as_user(file)
