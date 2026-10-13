"""Màu sắc và stylesheet của app."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

from ..actions.model import Risk
from ..core.executor import Level

ACCENT = "#2563eb"
RISK_COLORS = {Risk.SAFE: "#15803d", Risk.CAUTION: "#b45309", Risk.ADVANCED: "#b91c1c"}
STATE_COLORS = {"on": "#15803d", "off": "#64748b", "gpo": "#7c3aed", "blocked": "#b45309", "ok": "#15803d", "error": "#b91c1c"}
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

STYLESHEET = """
QWidget { color: #1f2933; }
#Central, #PageArea { background: #f4f6f8; }

#Header { background: #1e3a5f; }
#Header QLabel { color: #e6edf5; }
#AppTitle { font-size: 13pt; font-weight: 600; color: #ffffff; }
#AppVersion { color: #9fb3c8; }
QLabel[chip="normal"] { background: rgba(255,255,255,0.12); border-radius: 10px; padding: 3px 10px; }
QLabel[chip="ok"] { background: #15803d; color: #ffffff; border-radius: 10px; padding: 3px 10px; }
QLabel[chip="bad"] { background: #b91c1c; color: #ffffff; border-radius: 10px; padding: 3px 10px; }
QLabel[chip="warn"] { background: #b45309; color: #ffffff; border-radius: 10px; padding: 3px 10px; }

#Sidebar { background: #ffffff; border: none; border-right: 1px solid #dde3ea; padding-top: 10px; outline: 0; }
#Sidebar::item { padding-left: 14px; margin: 1px 8px; border-radius: 6px; }
#Sidebar::item:selected { background: #e0ecfa; color: #1e3a5f; font-weight: 600; }
#Sidebar::item:hover:!selected { background: #f0f3f7; }

#PageTitle { font-size: 16pt; font-weight: 600; color: #102a43; }
#PageSubtitle { color: #52606d; }
#EmptyState { color: #52606d; background: #ffffff; border: 1px dashed #c5cfda; border-radius: 8px; padding: 28px; }
#Card { background: #ffffff; border: 1px solid #dde3ea; border-radius: 8px; }
#PackBar { background: #eef4fc; border: 1px solid #c9dbf3; border-radius: 8px; }
QPushButton#PackButton { background: #ffffff; border-color: #9dbbe6; color: #1e3a5f; font-weight: 600; }
QPushButton#PackButton:hover { background: #dbe9fb; }
#DetailTitle { font-size: 13pt; font-weight: 600; color: #102a43; }
#SectionLabel { color: #52606d; font-weight: 600; }
#Note { color: #b45309; }
#FormKey { color: #52606d; }
#CardTitle { font-size: 11pt; font-weight: 600; color: #102a43; }
QLabel[state="ok"] { color: #15803d; }
QLabel[state="warn"] { color: #b45309; }
QLabel[state="bad"] { color: #b91c1c; font-weight: 600; }
QLabel[state="muted"] { color: #7b8794; }
#InfoView { background: #f4f6f8; border: none; }
#ShortcutsPanel { background: #ffffff; }
#SummaryLine { font-weight: 600; padding: 8px 12px; border-radius: 6px; background: #eef1f4; color: #52606d; }
#SummaryLine[state="ok"] { background: #dcfce7; color: #166534; }
#SummaryLine[state="warn"] { background: #fef3c7; color: #92400e; }
#SummaryLine[state="bad"] { background: #fee2e2; color: #991b1b; }
#ShortcutsPanel QPushButton { min-height: 22px; }

QPushButton { padding: 6px 14px; border: 1px solid #c5cfda; border-radius: 6px; background: #ffffff; }
QPushButton:hover { background: #f0f5fb; }
QPushButton:pressed { background: #e2ebf6; }
QPushButton:disabled { color: #9aa5b1; background: #f4f6f8; border-color: #dde3ea; }
QPushButton#Primary { background: #2563eb; color: #ffffff; border-color: #2563eb; font-weight: 600; }
QPushButton#Primary:hover { background: #1d4ed8; }
QPushButton#Primary:disabled { background: #a7c0f5; border-color: #a7c0f5; color: #eef3fd; }
QPushButton#Danger { color: #b91c1c; }

QLineEdit { padding: 5px 8px; border: 1px solid #c5cfda; border-radius: 6px; background: #ffffff; }
QLineEdit:focus { border-color: #2563eb; }
QTreeWidget, QTableWidget { background: #ffffff; border: 1px solid #dde3ea; border-radius: 6px; }
QTreeWidget::item, QTableWidget::item { padding: 4px 2px; }
QHeaderView::section { background: #f8fafc; border: none; border-bottom: 1px solid #dde3ea; padding: 6px; font-weight: 600; color: #52606d; }
#CodeView { background: #f8fafc; border: 1px solid #dde3ea; border-radius: 6px; font-family: Consolas, "Cascadia Mono", monospace; }

QLabel[badge] { border-radius: 9px; padding: 2px 9px; }
QLabel[badge="safe"] { background: #dcfce7; color: #166534; }
QLabel[badge="caution"] { background: #fef3c7; color: #92400e; }
QLabel[badge="advanced"] { background: #fee2e2; color: #991b1b; }
QLabel[badge="neutral"] { background: #e2e8f0; color: #334155; }
QLabel[badge="warn"] { background: #ffedd5; color: #9a3412; }

#LogPanel { background: #0f172a; }
#LogPanel QLabel { color: #cbd5e1; font-weight: 600; }
#LogPanel QPushButton { background: #1e293b; color: #e2e8f0; border-color: #334155; padding: 3px 10px; }
#LogPanel QPushButton:hover { background: #273449; }
#LogPanel QPushButton:disabled { color: #64748b; background: #111827; }
#LogView { background: #0f172a; color: #e2e8f0; border: none; font-family: Consolas, "Cascadia Mono", monospace; font-size: 9pt; }

QSplitter::handle { background: #dde3ea; }
"""


def _light_palette() -> QPalette:
    palette = QPalette()
    colors = {
        QPalette.ColorRole.Window: "#f4f6f8",
        QPalette.ColorRole.WindowText: "#1f2933",
        QPalette.ColorRole.Base: "#ffffff",
        QPalette.ColorRole.AlternateBase: "#f8fafc",
        QPalette.ColorRole.Text: "#1f2933",
        QPalette.ColorRole.Button: "#ffffff",
        QPalette.ColorRole.ButtonText: "#1f2933",
        QPalette.ColorRole.Highlight: "#dbeafe",
        QPalette.ColorRole.HighlightedText: "#102a43",
        QPalette.ColorRole.ToolTipBase: "#ffffff",
        QPalette.ColorRole.ToolTipText: "#1f2933",
        QPalette.ColorRole.PlaceholderText: "#7b8794",
        QPalette.ColorRole.Link: ACCENT,
    }
    for role, color in colors.items():
        palette.setColor(role, QColor(color))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText, QPalette.ColorRole.WindowText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor("#9aa5b1"))
    return palette


def apply_theme(app: QApplication) -> None:
    # Luôn dùng giao diện sáng: nếu theo chế độ tối của Windows thì ô tick và dòng chọn bị lệch màu với stylesheet.
    app.styleHints().setColorScheme(Qt.ColorScheme.Light)
    app.setStyle("Fusion")
    app.setPalette(_light_palette())
    app.setFont(QFont("Segoe UI", 10))
    app.setStyleSheet(STYLESHEET)
