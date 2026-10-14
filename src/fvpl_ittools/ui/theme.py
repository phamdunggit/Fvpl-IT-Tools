"""Màu sắc và stylesheet của app: kiểu Windows 11 sáng (docs/KE-HOACH-GIAO-DIEN.md mục 5.1)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

from ..actions.model import Risk
from ..core.executor import Level

# Bảng màu
BACKGROUND = "#f3f3f3"
CARD = "#ffffff"
BORDER = "#e5e5e5"
BORDER_STRONG = "#d1d1d1"
TEXT = "#1b1b1b"
TEXT_SECONDARY = "#5c5c5c"
TEXT_MUTED = "#8a8a8a"
ACCENT = "#005fb8"
ACCENT_HOVER = "#0a6ac4"
ACCENT_PRESSED = "#004a91"
ACCENT_TINT = "#e8f1fb"
SELECTED = "#e5eef8"
OK, OK_BG = "#0e700e", "#dff6dd"
WARN, WARN_BG = "#8a5300", "#fff4ce"
BAD, BAD_BG = "#c42b1c", "#fde7e9"

RISK_COLORS = {Risk.SAFE: OK, Risk.CAUTION: WARN, Risk.ADVANCED: BAD}
STATE_COLORS = {"on": OK, "off": TEXT_SECONDARY, "gpo": "#6b46c1", "blocked": WARN, "ok": OK, "error": BAD}
STATUS_COLORS = {"ok": OK, "warn": WARN, "bad": BAD, "muted": TEXT_MUTED, "info": ACCENT}
LOG_COLORS = {
    Level.HEADER: "#ffffff",
    Level.INFO: "#cbd5e1",
    Level.OK: "#4ade80",
    Level.WARN: "#fbbf24",
    Level.ERROR: "#f87171",
    Level.CMD: "#7dd3fc",
    Level.OUTPUT: "#e2e8f0",
}
OUTPUT_MARK_COLORS = {"✔": LOG_COLORS[Level.OK], "✖": LOG_COLORS[Level.ERROR], "⚠": LOG_COLORS[Level.WARN]}

STYLESHEET = f"""
QWidget {{ color: {TEXT}; }}
#Central, #PageArea {{ background: {BACKGROUND}; }}
QToolTip {{ background: {CARD}; color: {TEXT}; border: 1px solid {BORDER_STRONG}; padding: 4px 6px; }}

/* Thanh trên cùng */
#Header {{ background: {CARD}; border-bottom: 1px solid {BORDER}; }}
#AppLogo {{ background: {ACCENT}; color: #ffffff; border-radius: 7px; font-weight: 700; font-size: 10pt; }}
#AppTitle {{ font-size: 11.5pt; font-weight: 600; color: {TEXT}; }}
#AppVersion {{ color: {TEXT_MUTED}; }}
QPushButton#SearchBox {{ text-align: left; padding: 7px 12px; color: {TEXT_SECONDARY}; background: #fafafa;
    border: 1px solid {BORDER_STRONG}; border-radius: 6px; }}
QPushButton#SearchBox:hover {{ background: #f5f5f5; border-color: #b8b8b8; }}
QLabel[chip] {{ border-radius: 11px; padding: 3px 10px; }}
QLabel[chip="normal"] {{ background: #f0f0f0; color: {TEXT}; }}
QLabel[chip="ok"] {{ background: {OK_BG}; color: {OK}; }}
QLabel[chip="bad"] {{ background: {BAD_BG}; color: {BAD}; font-weight: 600; }}
QLabel[chip="warn"] {{ background: {WARN_BG}; color: {WARN}; }}
QPushButton[segment] {{ border-radius: 0; padding: 5px 12px; border: 1px solid {BORDER_STRONG}; background: {CARD}; }}
QPushButton[segment="first"] {{ border-top-left-radius: 6px; border-bottom-left-radius: 6px; border-right: none; }}
QPushButton[segment="last"] {{ border-top-right-radius: 6px; border-bottom-right-radius: 6px; }}
QPushButton[segment]:checked {{ background: {ACCENT}; border-color: {ACCENT}; color: #ffffff; }}

/* Sidebar */
#Sidebar {{ background: {BACKGROUND}; border: none; padding-top: 8px; outline: 0; }}
#Sidebar::item {{ padding: 2px 8px; margin: 1px 8px; border-radius: 6px; color: {TEXT}; }}
#Sidebar::item:selected {{ background: {SELECTED}; color: {TEXT}; font-weight: 600; }}
#Sidebar::item:hover:!selected {{ background: #eaeaea; }}
#StoreBox {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 8px; }}
#StoreBox QLabel {{ color: {TEXT_SECONDARY}; font-size: 9pt; }}
#StoreBox #StoreName {{ color: {TEXT}; font-weight: 600; }}
QPushButton#LinkButton {{ border: none; background: transparent; color: {ACCENT}; padding: 0; text-align: left; }}
QPushButton#LinkButton:hover {{ text-decoration: underline; }}

/* Thanh trạng thái dưới cùng */
#StatusBar {{ background: {CARD}; border-top: 1px solid {BORDER}; }}
#StatusBar QLabel {{ color: {TEXT_SECONDARY}; }}
#StatusDot {{ border-radius: 4px; background: {OK}; }}
#StatusDot[kind="busy"] {{ background: {ACCENT}; }}
#StatusDot[kind="warn"] {{ background: {WARN}; }}
QPushButton#StatusLink {{ border: none; background: transparent; color: {ACCENT}; padding: 2px 6px; }}
QPushButton#StatusLink:checked {{ text-decoration: underline; }}

/* Trang */
#PageTitle {{ font-size: 18pt; font-weight: 600; color: {TEXT}; }}
#PageSubtitle {{ color: {TEXT_SECONDARY}; }}
#EmptyState {{ color: {TEXT_SECONDARY}; background: {CARD}; border: 1px dashed {BORDER_STRONG}; border-radius: 8px; padding: 28px; }}
#Card {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 8px; }}
#PackBar {{ background: {ACCENT_TINT}; border: 1px solid #c7dcf2; border-radius: 8px; }}
QPushButton#PackButton {{ background: {CARD}; border-color: #9cc0e6; color: {ACCENT_PRESSED}; font-weight: 600; }}
QPushButton#PackButton:hover {{ background: #dbe9f8; }}
#DetailTitle {{ font-size: 13pt; font-weight: 600; color: {TEXT}; }}
#SectionLabel {{ color: {TEXT_SECONDARY}; font-weight: 600; }}
#Note {{ color: {WARN}; }}
#FormKey {{ color: {TEXT_SECONDARY}; }}
#CardTitle {{ font-size: 11pt; font-weight: 600; color: {TEXT}; }}
QLabel[state="ok"] {{ color: {OK}; }}
QLabel[state="warn"] {{ color: {WARN}; }}
QLabel[state="bad"] {{ color: {BAD}; font-weight: 600; }}
QLabel[state="muted"] {{ color: {TEXT_MUTED}; }}
#InfoView {{ background: {BACKGROUND}; border: none; }}
#ShortcutsPanel {{ background: {CARD}; }}
#SummaryLine {{ font-weight: 600; padding: 8px 12px; border-radius: 6px; background: #eeeeee; color: {TEXT_SECONDARY}; }}
#SummaryLine[state="ok"] {{ background: {OK_BG}; color: {OK}; }}
#SummaryLine[state="warn"] {{ background: {WARN_BG}; color: {WARN}; }}
#SummaryLine[state="bad"] {{ background: {BAD_BG}; color: {BAD}; }}
#ShortcutsPanel QPushButton {{ min-height: 22px; }}

/* Nút, ô nhập, bảng */
QPushButton {{ padding: 6px 14px; border: 1px solid {BORDER_STRONG}; border-radius: 6px; background: {CARD}; }}
QPushButton:hover {{ background: #f6f6f6; }}
QPushButton:pressed {{ background: #ededed; }}
QPushButton:focus {{ border-color: {ACCENT}; }}
QPushButton:disabled {{ color: #a0a0a0; background: #f5f5f5; border-color: {BORDER}; }}
QPushButton#Primary {{ background: {ACCENT}; color: #ffffff; border-color: {ACCENT}; font-weight: 600; }}
QPushButton#Primary:hover {{ background: {ACCENT_HOVER}; }}
QPushButton#Primary:pressed {{ background: {ACCENT_PRESSED}; }}
QPushButton#Primary:disabled {{ background: #9ec3e6; border-color: #9ec3e6; color: #f2f7fc; }}
QPushButton#Danger {{ color: {BAD}; }}
QLineEdit, QComboBox {{ padding: 5px 8px; border: 1px solid {BORDER_STRONG}; border-radius: 6px; background: {CARD}; }}
QLineEdit:focus, QComboBox:focus {{ border: 1px solid {ACCENT}; border-bottom: 2px solid {ACCENT}; }}
QTreeWidget, QTableWidget, QListWidget {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 8px; }}
QTreeWidget::item, QTableWidget::item {{ padding: 4px 2px; }}
QTreeWidget::item:selected, QTableWidget::item:selected {{ background: {SELECTED}; color: {TEXT}; }}
QHeaderView::section {{ background: #fafafa; border: none; border-bottom: 1px solid {BORDER}; padding: 6px; font-weight: 600; color: {TEXT_SECONDARY}; }}
#CodeView {{ background: #f7f7f7; border: 1px solid {BORDER}; border-radius: 6px; font-family: Consolas, "Cascadia Mono", monospace; }}
QTabWidget::pane {{ border: none; }}
QTabBar::tab {{ background: transparent; border: none; padding: 7px 14px; margin-right: 2px; color: {TEXT_SECONDARY}; }}
QTabBar::tab:selected {{ color: {TEXT}; font-weight: 600; border-bottom: 3px solid {ACCENT}; }}
QTabBar::tab:hover:!selected {{ color: {TEXT}; background: #eaeaea; border-radius: 6px; }}
QCheckBox::indicator, QTreeWidget::indicator {{ width: 16px; height: 16px; }}

QLabel[badge] {{ border-radius: 9px; padding: 2px 9px; }}
QLabel[badge="safe"] {{ background: {OK_BG}; color: {OK}; }}
QLabel[badge="caution"] {{ background: {WARN_BG}; color: {WARN}; }}
QLabel[badge="advanced"] {{ background: {BAD_BG}; color: {BAD}; }}
QLabel[badge="neutral"] {{ background: #eeeeee; color: #3a3a3a; }}
QLabel[badge="warn"] {{ background: {WARN_BG}; color: {WARN}; }}

/* Khung log (ngăn kéo "Chi tiết kỹ thuật") */
#LogPanel {{ background: #1e1e1e; }}
#LogPanel QLabel {{ color: #d4d4d4; font-weight: 600; }}
#LogPanel QPushButton {{ background: #2d2d2d; color: #e5e5e5; border-color: #3c3c3c; padding: 3px 10px; }}
#LogPanel QPushButton:hover {{ background: #383838; }}
#LogPanel QPushButton:disabled {{ color: #7a7a7a; background: #252525; }}
#LogView {{ background: #1e1e1e; color: #e2e8f0; border: none; font-family: Consolas, "Cascadia Mono", monospace; font-size: 9pt; }}
QSplitter::handle {{ background: {BORDER}; }}

/* Banner, thẻ chọn, tiến độ (đợt P0) */
#Banner {{ border-radius: 8px; border: 1px solid {BORDER}; background: {CARD}; }}
#Banner[kind="ok"] {{ border-color: #b7e1b4; }}
#Banner[kind="warn"] {{ background: {WARN_BG}; border-color: #f2d58a; }}
#Banner[kind="bad"] {{ background: {BAD_BG}; border-color: #f4c2c6; }}
#Banner[kind="info"] {{ background: {ACCENT_TINT}; border-color: #c7dcf2; }}
#BannerMark {{ font-size: 15pt; min-width: 22px; }}
#Banner[kind="ok"] #BannerMark {{ color: {OK}; }}
#Banner[kind="warn"] #BannerMark {{ color: {WARN}; }}
#Banner[kind="bad"] #BannerMark {{ color: {BAD}; }}
#Banner[kind="info"] #BannerMark {{ color: {ACCENT}; }}
#BannerTitle {{ font-weight: 600; color: {TEXT}; }}
#BannerText {{ color: {TEXT_SECONDARY}; }}

#ChoiceCard {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 8px; }}
#ChoiceCard:hover {{ border-color: #9cc0e6; }}
#ChoiceCard[checked="true"] {{ background: {ACCENT_TINT}; border: 2px solid {ACCENT}; }}
#ChoiceCard[disabled="true"] {{ background: #fafafa; }}
#ChoiceTitle {{ font-weight: 600; }}
#ChoiceNote {{ color: {TEXT_SECONDARY}; font-size: 9pt; }}

QProgressBar {{ background: {BORDER}; border: none; border-radius: 4px; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 4px; }}
#OverallBar {{ border-radius: 5px; }}
#OverallBar::chunk {{ border-radius: 5px; }}
#OverallBar[kind="ok"]::chunk {{ background: {OK}; }}
#OverallBar[kind="warn"]::chunk {{ background: {WARN}; }}
#ItemBar, #ItemBar::chunk {{ border-radius: 3px; }}
#ProgressHeadline {{ font-size: 12pt; font-weight: 600; color: {TEXT}; }}
#ProgressList {{ background: transparent; }}
#ProgressList > QWidget > QWidget {{ background: transparent; }}
#ProgressRow {{ border-top: 1px solid #efefef; }}
#ProgressMark {{ font-weight: 700; color: {TEXT_MUTED}; }}
#ProgressRow[state="running"] #ProgressMark, #ProgressRow[state="running"] #ProgressState {{ color: {ACCENT}; }}
#ProgressRow[state="running"] #ProgressName {{ font-weight: 600; }}
#ProgressRow[state="ok"] #ProgressMark, #ProgressRow[state="ok"] #ProgressState {{ color: {OK}; }}
#ProgressRow[state="failed"] #ProgressMark, #ProgressRow[state="failed"] #ProgressState {{ color: {BAD}; }}
#ProgressRow[state="cancelled"] #ProgressMark, #ProgressRow[state="cancelled"] #ProgressState {{ color: {WARN}; }}
#ProgressRow[state="waiting"] #ProgressName, #ProgressRow[state="skipped"] #ProgressName {{ color: {TEXT_MUTED}; }}
#ProgressState {{ color: {TEXT_SECONDARY}; }}
#ProgressReason {{ color: {TEXT_SECONDARY}; font-size: 9pt; }}
#ResultBox {{ border-radius: 6px; padding: 10px 12px; background: {OK_BG}; color: {OK}; }}
#ResultBox[kind="warn"] {{ background: {WARN_BG}; color: {WARN}; }}
#PageScroll {{ background: transparent; }}
#PageScroll > QWidget > QWidget {{ background: transparent; }}
#BottomSummary {{ font-weight: 600; color: {TEXT}; }}

/* Trang chủ */
QPushButton#Tile {{ text-align: left; background: {CARD}; border: 1px solid {BORDER}; border-radius: 8px; padding: 0; }}
QPushButton#Tile:hover {{ border-color: #9cc0e6; background: #fbfdff; }}
QPushButton#Tile[accent="true"] {{ background: {ACCENT}; border-color: {ACCENT}; }}
QPushButton#Tile[accent="true"]:hover {{ background: {ACCENT_HOVER}; }}
#TileTitle {{ font-size: 11.5pt; font-weight: 600; color: {TEXT}; background: transparent; }}
#TileText {{ color: {TEXT_SECONDARY}; background: transparent; }}
QPushButton#Tile[accent="true"] #TileTitle {{ color: #ffffff; }}
QPushButton#Tile[accent="true"] #TileText {{ color: #e8f1fb; }}
#TileIcon {{ background: {ACCENT_TINT}; border-radius: 8px; }}
QPushButton#Tile[accent="true"] #TileIcon {{ background: rgba(255, 255, 255, 40); }}
#HealthRow {{ border-top: 1px solid #efefef; }}

/* Bảng tìm chức năng (Ctrl+K) */
#Palette {{ background: {CARD}; border: 1px solid {BORDER_STRONG}; border-radius: 10px; }}
#Palette QLineEdit {{ border: none; border-bottom: 1px solid {BORDER}; border-radius: 0; padding: 12px 14px; font-size: 12.5pt; }}
#Palette QListWidget {{ border: none; border-radius: 0; background: {CARD}; outline: 0; }}
#Palette QListWidget::item {{ border-radius: 6px; margin: 1px 6px; }}
#Palette QListWidget::item:selected {{ background: {ACCENT_TINT}; }}
#PaletteTitle {{ font-weight: 600; background: transparent; }}
#PaletteText, #PaletteWhere {{ color: {TEXT_SECONDARY}; background: transparent; }}
#PaletteWhere {{ font-size: 8.5pt; }}
#PaletteKind {{ background: {ACCENT_TINT}; color: {ACCENT}; border-radius: 6px; font-weight: 700; font-size: 8.5pt; }}
#PaletteFoot {{ color: {TEXT_SECONDARY}; font-size: 8.5pt; padding: 8px 14px; border-top: 1px solid {BORDER}; }}
#PaletteCount {{ color: {TEXT_SECONDARY}; font-size: 8.5pt; padding: 6px 14px; background: #fafafa; }}
"""


def _light_palette() -> QPalette:
    palette = QPalette()
    colors = {
        QPalette.ColorRole.Window: BACKGROUND,
        QPalette.ColorRole.WindowText: TEXT,
        QPalette.ColorRole.Base: CARD,
        QPalette.ColorRole.AlternateBase: "#fafafa",
        QPalette.ColorRole.Text: TEXT,
        QPalette.ColorRole.Button: CARD,
        QPalette.ColorRole.ButtonText: TEXT,
        QPalette.ColorRole.Highlight: ACCENT,
        QPalette.ColorRole.HighlightedText: "#ffffff",
        QPalette.ColorRole.ToolTipBase: CARD,
        QPalette.ColorRole.ToolTipText: TEXT,
        QPalette.ColorRole.PlaceholderText: TEXT_MUTED,
        QPalette.ColorRole.Link: ACCENT,
    }
    for role, color in colors.items():
        palette.setColor(role, QColor(color))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText, QPalette.ColorRole.WindowText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor("#a0a0a0"))
    return palette


def app_font() -> QFont:
    """Segoe UI Variable (Windows 11), không có thì Segoe UI."""
    font = QFont()
    font.setFamilies(["Segoe UI Variable Text", "Segoe UI"])
    font.setPointSize(10)
    return font


def apply_theme(app: QApplication) -> None:
    # Luôn dùng giao diện sáng: nếu theo chế độ tối của Windows thì ô tick và dòng chọn bị lệch màu với stylesheet.
    app.styleHints().setColorScheme(Qt.ColorScheme.Light)
    app.setStyle("Fusion")
    app.setPalette(_light_palette())
    app.setFont(app_font())
    app.setStyleSheet(STYLESHEET)
