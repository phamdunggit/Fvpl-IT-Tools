"""Trang chủ (KE-HOACH-GIAO-DIEN.md mục 5.3): ô lớn theo tình huống, tình trạng máy này, banner cài máy dở.

Bấm một ô hoặc nút sửa thì phát `navigate` với đích giống kết quả tìm kiếm ("page:software", "fixes:<nhóm>",
"action:<id>"…); cửa sổ chính mở đúng chỗ.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ...app import AppContext
from ... import __version__
from ...core import health, updates
from ...newpc import state as wizard_state
from .. import icons, theme
from ..components.banner import Banner
from ..widgets import open_path

COLUMNS = 4
HEALTH_ICONS = {"ok": "ok", "warn": "warn", "bad": "bad"}


@dataclass(frozen=True)
class TileSpec:
    title: str
    text: str
    icon: str
    target: str
    accent: bool = False


TILES = (
    TileSpec("Cài máy mới", "Đặt tên, vào domain, cài phần mềm, cấu hình chuẩn", "newpc", "page:newpc", accent=True),
    TileSpec("Cài phần mềm", "Office, Symantec, UniKey, Chrome… chọn là cài", "download", "page:software"),
    TileSpec("Không vào được mạng", "Mất mạng, mạng chậm, không vào được trang web", "wifi", "guide:network"),
    TileSpec("Không in được", "Kẹt lệnh in, máy in báo lỗi, máy in share Win11 ↔ Win10", "printer", "guide:printing"),
    TileSpec("Máy chậm, đầy ổ", "Dọn rác, tắt bớt chương trình chạy cùng Windows", "gauge", "guide:slow"),
    TileSpec("Lỗi Office, Outlook", "Sửa Office, kích hoạt Office, Teams lỗi", "document", "guide:office"),
    TileSpec("Windows Update lỗi", "Cập nhật không chạy, báo lỗi, kẹt phần trăm", "refresh", "guide:windows_update"),
    TileSpec("Kiểm tra máy", "Thông tin máy, serial, lưu kiểm kê", "clipboard", "page:overview"),
)


class Tile(QFrame):
    """Ô lớn ở Trang chủ. Là khung (không phải nút) để chữ xuống dòng thì ô tự cao lên, không bị cắt
    (cỡ chữ 150%, cửa sổ hẹp). Bấm chuột, Enter hoặc phím cách đều mở."""
    clicked = Signal()

    def __init__(self, spec: TileSpec):
        super().__init__()
        self.spec = spec
        self.setObjectName("Tile")
        self.setProperty("accent", spec.accent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setMinimumHeight(128)
        self.setAccessibleName(spec.title)
        self.setToolTip(spec.text)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 14)
        layout.setSpacing(8)
        mark = QLabel()
        mark.setObjectName("TileIcon")
        mark.setFixedSize(40, 40)
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark.setPixmap(icons.pixmap(spec.icon, "#ffffff" if spec.accent else theme.ACCENT, 22))
        title = QLabel(spec.title)
        title.setObjectName("TileTitle")
        title.setWordWrap(True)
        text = QLabel(spec.text)
        text.setObjectName("TileText")
        text.setWordWrap(True)
        text.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        for label in (mark, title, text):
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(mark)
        layout.addWidget(title)
        layout.addWidget(text)
        layout.addStretch(1)

    def click(self) -> None:
        self.clicked.emit()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.clicked.emit()
            return
        super().keyPressEvent(event)


class HomePage(QWidget):
    navigate = Signal(str)
    need_data = Signal()  # trang chủ hiện lần đầu: nhờ trang Thông tin máy đọc thông tin

    def __init__(self, app: AppContext):
        super().__init__()
        self.app = app
        self._started = False
        self.health_items: list[health.HealthItem] = []
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setObjectName("PageScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll)
        body = QWidget()
        scroll.setWidget(body)
        root = QVBoxLayout(body)
        root.setContentsMargins(28, 22, 28, 20)
        root.setSpacing(16)

        self.resume = Banner()
        self.resume.clicked.connect(lambda: self.navigate.emit("page:newpc"))
        root.addWidget(self.resume)
        self.release: updates.Release | None = None
        self.update_banner = Banner()
        self.update_banner.clicked.connect(self.open_release)
        self.update_banner.hide()
        root.addWidget(self.update_banner)

        title = QLabel("Bạn cần làm gì?")
        title.setObjectName("PageTitle")
        subtitle = QLabel("Chọn việc cần làm. Tool hướng dẫn từng bước, chạy xong nói rõ kết quả. "
                          "Không thấy việc mình cần thì bấm ô tìm ở trên (Ctrl+K).")
        subtitle.setObjectName("PageSubtitle")
        subtitle.setWordWrap(True)
        root.addWidget(title)
        root.addWidget(subtitle)

        grid = QGridLayout()
        grid.setSpacing(12)
        self.tiles: list[Tile] = []
        for index, spec in enumerate(TILES):
            tile = Tile(spec)
            tile.clicked.connect(lambda target=spec.target: self.navigate.emit(target))
            grid.addWidget(tile, index // COLUMNS, index % COLUMNS)
            self.tiles.append(tile)
        for column in range(COLUMNS):
            grid.setColumnStretch(column, 1)
        root.addLayout(grid)

        card = QFrame()
        card.setObjectName("Card")
        self.health_layout = QVBoxLayout(card)
        self.health_layout.setContentsMargins(18, 14, 18, 12)
        self.health_layout.setSpacing(0)
        head = QHBoxLayout()
        health_title = QLabel("Tình trạng máy này")
        health_title.setObjectName("CardTitle")
        self.details_button = QPushButton("Xem toàn bộ thông tin máy")
        self.details_button.setObjectName("LinkButton")
        self.details_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.details_button.clicked.connect(lambda: self.navigate.emit("page:overview"))
        head.addWidget(health_title)
        head.addStretch(1)
        head.addWidget(self.details_button)
        self.health_layout.addLayout(head)
        self.health_layout.addSpacing(6)
        self.rows_box = QVBoxLayout()
        self.rows_box.setSpacing(0)
        self.health_layout.addLayout(self.rows_box)
        root.addWidget(card)
        root.addStretch(1)
        self.set_health([], loading=True)
        self.refresh_resume()

    def showEvent(self, event) -> None:
        if not self._started:
            self._started = True
            self.need_data.emit()
        self.refresh_resume()
        super().showEvent(event)

    def refresh_resume(self) -> None:
        wizard = wizard_state.active()
        if wizard is None:
            self.resume.hide()
            return
        done = sum(1 for key, _ in wizard_state.STEPS if wizard.status(key) in ("ok", "skipped"))
        name = wizard.computer_name or "(chưa đặt tên)"
        self.resume.show_state("info", f"Đang cài dở máy {name}",
                               f"Đã xong {done}/{len(wizard_state.STEPS)} bước. Bấm Làm tiếp để mở trang Cài máy mới.",
                               "Làm tiếp", primary=True)
        self.resume.show()

    def show_update(self, release: updates.Release) -> None:
        """Có bản tool mới trên share."""
        self.release = release
        notes = "; ".join(release.notes[:3])
        when = f" ({release.date})" if release.date else ""
        self.update_banner.show_state(
            "info", f"Có bản tool mới {release.version}{when}, bản đang chạy là {__version__}",
            (notes + ". " if notes else "") + "Chép thư mục bản mới ra USB / SSD (hoặc chạy deploy.py) rồi mở lại tool.",
            "Mở thư mục bản mới")
        self.update_banner.show()

    def open_release(self) -> None:
        if self.release is not None:
            folder = self.release.folder
            open_path(folder if folder.exists() else folder.parent)

    def set_health(self, items: list[health.HealthItem], loading: bool = False) -> None:
        self.health_items = items
        while self.rows_box.count():
            widget = self.rows_box.takeAt(0).widget()
            if widget is not None:
                widget.deleteLater()
        if loading and not items:
            waiting = QLabel("Đang kiểm tra máy…")
            waiting.setObjectName("PageSubtitle")
            self.rows_box.addWidget(waiting)
            return
        for item in items:
            self.rows_box.addWidget(self._row(item))
        if loading:
            more = QLabel("Đang đọc thêm…")
            more.setObjectName("PageSubtitle")
            self.rows_box.addWidget(more)

    def _row(self, item: health.HealthItem) -> QWidget:
        row = QFrame()
        row.setObjectName("HealthRow")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(12)
        mark = QLabel()
        mark.setPixmap(icons.pixmap(HEALTH_ICONS.get(item.state, "ok"), theme.STATUS_COLORS.get(item.state, theme.OK), 20))
        text = QLabel(item.text)
        text.setWordWrap(True)
        layout.addWidget(mark)
        layout.addWidget(text, 1)
        if item.button and item.target:
            button = QPushButton(item.button)
            button.clicked.connect(lambda _checked=False, target=item.target: self.navigate.emit(target))
            layout.addWidget(button)
        return row
