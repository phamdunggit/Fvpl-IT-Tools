"""Trang Tối ưu & dọn dẹp: dọn rác (quét trước rồi mới xoá) và các mục tối ưu / quyền riêng tư."""

from __future__ import annotations

import logging
import threading

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...app import AppContext
from ...cleanup import junk
from ..controller import RunController
from ..widgets import page_header
from .actions_page import ActionsPage

log = logging.getLogger(__name__)
CATEGORY_ROLE = Qt.ItemDataRole.UserRole


class ScanLoader(QObject):
    done = Signal(int, object)  # lượt, list[junk.Scan] hoặc None

    def __init__(self, app: AppContext, parent: QObject | None = None):
        super().__init__(parent)
        self.app = app
        self.generation = 0
        self._cancel = threading.Event()

    def start(self) -> None:
        self._cancel.set()
        self._cancel = threading.Event()
        self.generation += 1
        threading.Thread(target=self._work, args=(self.generation, self._cancel), name="junk-scan", daemon=True).start()

    def stop(self) -> None:
        self._cancel.set()

    def _work(self, generation: int, cancel: threading.Event) -> None:
        try:
            result = junk.scan_all(self.app.env, cancel)
        except Exception:
            log.exception("Lỗi khi quét rác")
            result = None
        if not cancel.is_set():
            self.done.emit(generation, result)


class CleanupPanel(QWidget):
    def __init__(self, app: AppContext, controller: RunController):
        super().__init__()
        self.app = app
        self.controller = controller
        self.scans: list[junk.Scan] = []
        self.loading = False
        self._items: dict[str, QTreeWidgetItem] = {}
        self.loader = ScanLoader(app, self)
        self.loader.done.connect(self._scanned)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(10)
        note = QLabel("Quét trước để thấy dung lượng từng loại, tick loại cần dọn rồi bấm Dọn. File đang được dùng "
                      "sẽ được bỏ qua. Loại có nhãn Cẩn thận xoá rồi không lấy lại được.")
        note.setObjectName("PageSubtitle")
        note.setWordWrap(True)
        layout.addWidget(note)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Loại", "Dung lượng", "Số file", "Ghi chú"])
        self.tree.setRootIsDecorated(False)
        self.tree.setUniformRowHeights(True)
        header = self.tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        for category in junk.CATEGORIES:
            item = QTreeWidgetItem(self.tree, [category.name, "…", "", ""])
            item.setData(0, CATEGORY_ROLE, category.id)
            item.setToolTip(0, category.description)
            item.setTextAlignment(1, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            item.setTextAlignment(2, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._items[category.id] = item
        self.tree.itemChanged.connect(lambda *_: self._update_total())
        layout.addWidget(self.tree, 1)

        buttons = QHBoxLayout()
        self.rescan_button = QPushButton("Quét lại")
        self.total = QLabel()
        self.total.setObjectName("SectionLabel")
        self.clean_button = QPushButton("Dọn mục đã chọn")
        self.clean_button.setObjectName("Primary")
        buttons.addWidget(self.rescan_button)
        buttons.addSpacing(12)
        buttons.addWidget(self.total, 1)
        buttons.addWidget(self.clean_button)
        layout.addLayout(buttons)

        self.rescan_button.clicked.connect(self.rescan)
        self.clean_button.clicked.connect(self.clean)
        controller.busy_changed.connect(lambda _busy: self._update_buttons())
        controller.finished.connect(self._run_finished)
        self._update_buttons()

    # ------------------------------------------------------------ quét

    def rescan(self) -> None:
        self.loading = True
        for item in self._items.values():
            item.setText(1, "đang quét…")
            item.setText(2, "")
        self.total.setText("Đang quét…")
        self._update_buttons()
        self.loader.start()

    def stop(self) -> None:
        self.loader.stop()

    def _scanned(self, generation: int, scans: object) -> None:
        if generation != self.loader.generation:
            return
        self.loading = False
        if scans is None:
            self.total.setText("Quét lỗi, xem file log.")
            self._update_buttons()
            return
        first = not self.scans
        self.scans = scans
        is_admin = self.app.env.is_admin
        self.tree.blockSignals(True)
        for scan in scans:
            category = scan.category
            item = self._items[category.id]
            item.setText(1, junk.size_text(scan.size))
            item.setText(2, f"{scan.files:,}".replace(",", "."))
            notes = []
            if category.risk == "caution":
                notes.append("Cẩn thận: không lấy lại được")
            if category.admin and not is_admin:
                notes.append("Cần quyền admin")
            elif not scan.readable:
                notes.append("Có chỗ không đọc được, dung lượng có thể nhiều hơn")
            item.setText(3, " · ".join(notes))
            item.setForeground(3, QBrush(QColor("#b45309" if notes else "#52606d")))
            allowed = is_admin or not category.admin
            flags = item.flags() | Qt.ItemFlag.ItemIsUserCheckable
            if not allowed:
                flags &= ~Qt.ItemFlag.ItemIsUserCheckable
            item.setFlags(flags)
            if first or not allowed:
                checked = allowed and category.checked and scan.size > 0
                item.setCheckState(0, Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        self.tree.blockSignals(False)
        self._update_total()
        self._update_buttons()

    # ------------------------------------------------------------ dọn

    def selected(self) -> list[junk.Scan]:
        return [scan for scan in self.scans if self._items[scan.category.id].checkState(0) == Qt.CheckState.Checked]

    def _update_total(self) -> None:
        if not self.scans:
            return
        chosen = sum(scan.size for scan in self.selected())
        total = sum(scan.size for scan in self.scans)
        self.total.setText(f"Đã chọn {junk.size_text(chosen)} / quét thấy {junk.size_text(total)}")
        self._update_buttons()

    def clean(self) -> None:
        chosen = self.selected()
        if not chosen:
            QMessageBox.information(self, "Chưa chọn", "Tick vào các loại cần dọn.")
            return
        lines = "\n".join(f"• {scan.category.name}: {junk.size_text(scan.size)}" for scan in chosen)
        risky = [scan.category.name for scan in chosen if scan.category.risk == "caution"]
        warning = f"\n\nKhông lấy lại được: {', '.join(risky)}." if risky else ""
        answer = QMessageBox.question(self, "Dọn rác", f"Dọn các loại sau?\n{lines}{warning}")
        if answer != QMessageBox.StandardButton.Yes:
            return
        categories = [scan.category for scan in chosen]
        self.controller.run_job(lambda ctx: junk.clean(categories, ctx))

    def _run_finished(self, result: object) -> None:
        if isinstance(result, junk.CleanupResult):
            self.rescan()

    def _update_buttons(self) -> None:
        busy = self.controller.busy
        self.rescan_button.setEnabled(not self.loading and not busy)
        self.clean_button.setEnabled(not self.loading and not busy and bool(self.scans) and bool(self.selected()))


class OptimizePage(QWidget):
    def __init__(self, app: AppContext, controller: RunController):
        super().__init__()
        self._started = False
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 12)
        root.setSpacing(10)
        page_header(root, "Tối ưu & dọn dẹp",
                    "Dọn rác có quét trước, tối ưu và tắt quảng cáo / theo dõi. Mục đổi registry hoàn tác được.")
        self.tabs = QTabWidget()
        self.cleanup = CleanupPanel(app, controller)
        self.tweaks = ActionsPage(
            "optimize", "", "",
            "Chưa có mục tối ưu nào.", app, controller, packs=app.packs, show_header=False,
        )
        self.tabs.addTab(self.cleanup, "Dọn rác")
        self.tabs.addTab(self.tweaks, "Tối ưu && quyền riêng tư")  # "&&": Qt hiểu "&" là phím tắt
        root.addWidget(self.tabs, 1)

    @property
    def loading(self) -> bool:
        return self.cleanup.loading

    def showEvent(self, event) -> None:
        if not self._started:
            self._started = True
            self.cleanup.rescan()
        super().showEvent(event)

    def stop(self) -> None:
        self.cleanup.stop()
