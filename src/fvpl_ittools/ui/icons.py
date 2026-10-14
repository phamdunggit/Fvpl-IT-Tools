"""Icon nét mảnh kiểu Windows 11, vẽ bằng SVG ngay trong code (không cần file ảnh, đổi màu theo trạng thái).

Mỗi icon là các phần tử SVG trên lưới 24×24, nét 1.8px.
"""

from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

SHAPES: dict[str, str] = {
    "home": '<path d="M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8v.5"/>',
    "newpc": '<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/>',
    "apps": '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/>'
            '<rect x="3" y="14" width="7" height="7" rx="1.5"/><path d="M17.5 14v7M14 17.5h7"/>',
    "wrench": '<path d="M14.7 6.3a4 4 0 0 0-5.4 5.4L3 18l3 3 6.3-6.3a4 4 0 0 0 5.4-5.4l-2.5 2.5-2.4-.6-.6-2.4z"/>',
    "printer": '<path d="M6 9V3h12v6M6 18H4a1 1 0 0 1-1-1v-6a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v6a1 1 0 0 1-1 1h-2"/>'
               '<rect x="6" y="14" width="12" height="7"/>',
    "gauge": '<path d="M3.3 17a9 9 0 1 1 17.4 0"/><path d="m12 14 4-5"/>',
    "settings": '<circle cx="12" cy="12" r="3"/>'
                '<path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M4.9 19.1 7 17M17 7l2.1-2.1"/>',
    "toolbox": '<rect x="3" y="7" width="18" height="13" rx="2"/><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M3 13h18"/>',
    "history": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
    "wifi": '<path d="M2 9a15 15 0 0 1 20 0M5 12.5a10 10 0 0 1 14 0M8.5 16a5 5 0 0 1 7 0"/>'
            '<circle cx="12" cy="19.5" r="1"/>',
    "document": '<path d="M6 3h9l4 4v14H6z"/><path d="M14 3v5h5M9 13h6M9 17h6"/>',
    "refresh": '<path d="M20 11a8 8 0 1 0-2.3 5.7M20 4v7h-7"/>',
    "clipboard": '<rect x="5" y="4" width="14" height="17" rx="2"/><path d="M9 4V3h6v1M9 12l2 2 4-4"/>',
    "download": '<path d="M12 3v12m0 0-4-4m4 4 4-4M4 17v3h16v-3"/>',
    "ok": '<circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/>',
    "warn": '<path d="M12 3 2 20h20z"/><path d="M12 10v4M12 17v.5"/>',
    "bad": '<circle cx="12" cy="12" r="9"/><path d="m9 9 6 6M15 9l-6 6"/>',
    "shield": '<path d="M12 3 5 6v6c0 4.5 3 7.5 7 9 4-1.5 7-4.5 7-9V6z"/>',
    "disk": '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M7 15h.01M11 15h6"/>',
    "chevron": '<path d="m9 6 6 6-6 6"/>',
    "log": '<path d="M4 6h16M4 12h16M4 18h10"/>',
}


def svg(name: str, color: str, width: float = 1.8) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" '
            f'stroke-width="{width}" stroke-linecap="round" stroke-linejoin="round">{SHAPES[name]}</svg>')


@lru_cache(maxsize=256)
def pixmap(name: str, color: str, size: int = 20, scale: int = 2) -> QPixmap:
    """Ảnh của icon, vẽ ở độ phân giải gấp `scale` lần cho màn hình DPI cao."""
    image = QPixmap(size * scale, size * scale)
    image.fill(Qt.GlobalColor.transparent)
    renderer = QSvgRenderer(QByteArray(svg(name, color).encode("utf-8")))
    painter = QPainter(image)
    renderer.render(painter, QRectF(0, 0, size * scale, size * scale))
    painter.end()
    image.setDevicePixelRatio(scale)
    return image


def icon(name: str, color: str, selected: str | None = None, size: int = 20) -> QIcon:
    """Icon có màu thường và (tuỳ chọn) màu khi được chọn, ví dụ mục đang mở trên sidebar."""
    result = QIcon()
    result.addPixmap(pixmap(name, color, size), QIcon.Mode.Normal)
    if selected:
        result.addPixmap(pixmap(name, selected, size), QIcon.Mode.Selected)
    return result
