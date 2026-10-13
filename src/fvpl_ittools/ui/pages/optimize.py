"""Trang Tối ưu & dọn dẹp: dọn rác (quét trước rồi mới xoá) và các mục tối ưu / quyền riêng tư."""

from __future__ import annotations

import logging
import os
import subprocess
import threading
import time

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...app import AppContext
from ...cleanup import bigfiles, junk, startup
from ...core import shell
from ...core.executor import BatchResult, Level
from ..controller import RunController
from ..widgets import page_header
from .actions_page import ActionsPage

log = logging.getLogger(__name__)
CATEGORY_ROLE = Qt.ItemDataRole.UserRole
ENTRY_ROLE = Qt.ItemDataRole.UserRole


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


class StartupPanel(QWidget):
    """Chương trình chạy cùng Windows: bật/tắt kiểu Task Manager, có nhật ký và hoàn tác."""

    def __init__(self, app: AppContext, controller: RunController):
        super().__init__()
        self.app = app
        self.controller = controller
        self.entries: list[startup.StartupEntry] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(10)
        note = QLabel("Tắt bớt chương trình chạy cùng Windows để máy khởi động nhanh hơn. Tắt giống tab Startup của "
                      "Task Manager: không xoá gì, bật lại hoặc hoàn tác ở trang Nhật ký được. Có hiệu lực từ lần "
                      "đăng nhập sau. Chọn nhiều dòng bằng Ctrl hoặc Shift.")
        note.setObjectName("PageSubtitle")
        note.setWordWrap(True)
        layout.addWidget(note)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Chương trình", "Trạng thái", "Nguồn", "Lệnh"])
        self.tree.setRootIsDecorated(False)
        self.tree.setUniformRowHeights(True)
        self.tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        header = self.tree.header()
        for column in range(3):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.tree, 1)

        buttons = QHBoxLayout()
        self.refresh_button = QPushButton("Làm mới")
        self.disable_button = QPushButton("Tắt mục đã chọn")
        self.enable_button = QPushButton("Bật mục đã chọn")
        buttons.addWidget(self.refresh_button)
        buttons.addStretch(1)
        buttons.addWidget(self.enable_button)
        buttons.addWidget(self.disable_button)
        layout.addLayout(buttons)

        self.refresh_button.clicked.connect(self.refresh)
        self.disable_button.clicked.connect(lambda: self.toggle(False))
        self.enable_button.clicked.connect(lambda: self.toggle(True))
        self.tree.itemSelectionChanged.connect(self._update_buttons)
        controller.busy_changed.connect(lambda _busy: self._update_buttons())
        controller.finished.connect(self._run_finished)

    def refresh(self) -> None:
        try:
            self.entries = startup.entries(self.app.env)
        except OSError as exc:
            log.exception("Không đọc được danh sách khởi động")
            self.controller.say(Level.ERROR, f"Không đọc được danh sách chương trình khởi động: {exc}")
            self.entries = []
        self.tree.clear()
        for index, entry in enumerate(self.entries):
            item = QTreeWidgetItem(self.tree, [entry.name, "Bật" if entry.enabled else "Tắt", entry.source, entry.command])
            item.setData(0, ENTRY_ROLE, index)
            item.setForeground(1, QBrush(QColor("#15803d" if entry.enabled else "#64748b")))
            item.setToolTip(3, entry.command)
        self._update_buttons()

    def selected(self) -> list[startup.StartupEntry]:
        return [self.entries[item.data(0, ENTRY_ROLE)] for item in self.tree.selectedItems()]

    def toggle(self, enable: bool) -> None:
        targets = [entry for entry in self.selected() if entry.enabled != enable]
        if not targets:
            return
        self.controller.run([startup.toggle_action(entry, enable) for entry in targets])

    def _run_finished(self, result: object) -> None:
        if isinstance(result, BatchResult) and any(item.action.id == "startup.toggle" for item in result.results):
            self.refresh()

    def _update_buttons(self) -> None:
        chosen = self.selected()
        busy = self.controller.busy
        self.refresh_button.setEnabled(not busy)
        self.disable_button.setEnabled(not busy and any(entry.enabled for entry in chosen))
        self.enable_button.setEnabled(not busy and any(not entry.enabled for entry in chosen))


class BigFilesPanel(QWidget):
    """Tìm file lớn và thư mục chiếm nhiều chỗ (chỉ đọc)."""

    progress = Signal(int, int)       # lượt, số file đã xem
    done = Signal(int, object)        # lượt, bigfiles.SearchResult

    def __init__(self, controller: RunController):
        super().__init__()
        self.controller = controller
        self.result: bigfiles.SearchResult | None = None
        self.searching = False
        self.generation = 0
        self._cancel = threading.Event()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(10)
        note = QLabel("Tìm xem file và thư mục nào đang chiếm chỗ. Chỉ xem, tool không xoá file của người dùng: "
                      "chọn một file rồi bấm Mở thư mục chứa để xử lý tay. Quét cả ổ C có thể mất 1–2 phút.")
        note.setObjectName("PageSubtitle")
        note.setWordWrap(True)
        layout.addWidget(note)

        row = QHBoxLayout()
        row.addWidget(QLabel("Tìm trong"))
        self.root = QLineEdit(os.environ.get("SystemDrive", "C:") + "\\")
        row.addWidget(self.root, 1)
        row.addWidget(QLabel("File từ"))
        self.min_mb = QSpinBox()
        self.min_mb.setRange(10, 100000)
        self.min_mb.setValue(500)
        self.min_mb.setSuffix(" MB")
        row.addWidget(self.min_mb)
        self.search_button = QPushButton("Tìm")
        self.search_button.setObjectName("Primary")
        self.stop_button = QPushButton("Dừng")
        row.addWidget(self.search_button)
        row.addWidget(self.stop_button)
        layout.addLayout(row)

        self.status = QLabel()
        self.status.setObjectName("SectionLabel")
        layout.addWidget(self.status)

        self.files = QTreeWidget()
        self.files.setHeaderLabels(["Dung lượng", "Sửa lần cuối", "File"])
        self.folders = QTreeWidget()
        self.folders.setHeaderLabels(["Dung lượng", "Thư mục cấp đầu"])
        for tree in (self.files, self.folders):
            tree.setRootIsDecorated(False)
            tree.setUniformRowHeights(True)
            header = tree.header()
            for column in range(tree.columnCount() - 1):
                header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(tree.columnCount() - 1, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.files, 3)
        layout.addWidget(self.folders, 2)

        buttons = QHBoxLayout()
        self.open_button = QPushButton("Mở thư mục chứa")
        buttons.addStretch(1)
        buttons.addWidget(self.open_button)
        layout.addLayout(buttons)

        self.search_button.clicked.connect(self.search)
        self.stop_button.clicked.connect(self.stop)
        self.open_button.clicked.connect(self.open_selected)
        self.progress.connect(self._progress)
        self.done.connect(self._done)
        self._selected: str | None = None
        self.files.itemSelectionChanged.connect(lambda: self._picked(self.files))
        self.folders.itemSelectionChanged.connect(lambda: self._picked(self.folders))
        self._update_buttons()

    def search(self) -> None:
        root = self.root.text().strip()
        if not os.path.isdir(root):
            self.status.setText(f"Không thấy thư mục {root}")
            return
        self._cancel.set()
        self._cancel = threading.Event()
        self.generation += 1
        generation, cancel, min_size = self.generation, self._cancel, self.min_mb.value() * 1024**2
        self.searching = True
        self.status.setText(f"Đang tìm trong {root}…")
        self._update_buttons()

        def work() -> None:
            try:
                result = bigfiles.find(root, min_size, cancel, lambda count: self.progress.emit(generation, count))
            except Exception:
                log.exception("Lỗi khi tìm file lớn")
                result = bigfiles.SearchResult(root=root, cancelled=True)
            self.done.emit(generation, result)

        threading.Thread(target=work, name="big-files", daemon=True).start()

    def stop(self) -> None:
        self._cancel.set()

    def _progress(self, generation: int, count: int) -> None:
        if generation == self.generation and self.searching:
            self.status.setText(f"Đang tìm… đã xem {count:,} file".replace(",", "."))

    def _done(self, generation: int, result: object) -> None:
        if generation != self.generation:
            return
        self.searching = False
        self.result = result
        self.files.clear()
        self.folders.clear()
        self._selected = None
        for item in result.files:
            when = time.strftime("%d/%m/%Y", time.localtime(item.modified)) if item.modified else ""
            row = QTreeWidgetItem(self.files, [junk.size_text(item.size), when, item.path])
            row.setData(0, ENTRY_ROLE, item.path)
            row.setTextAlignment(0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        for size, path in result.folders:
            row = QTreeWidgetItem(self.folders, [junk.size_text(size), path])
            row.setData(0, ENTRY_ROLE, path)
            row.setTextAlignment(0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        state = "Đã dừng" if result.cancelled else "Xong"
        unreadable = f", {result.unreadable:,} chỗ không đọc được (thiếu quyền)".replace(",", ".") if result.unreadable else ""
        self.status.setText(f"{state}: đã xem {result.scanned:,} file".replace(",", ".")
                            + f", {len(result.files)} file từ {self.min_mb.value()} MB trở lên{unreadable}.")
        self._update_buttons()

    def _picked(self, tree: QTreeWidget) -> None:
        items = tree.selectedItems()
        self._selected = items[0].data(0, ENTRY_ROLE) if items else None
        self._update_buttons()

    def selected_path(self) -> str | None:
        """Dòng chọn gần nhất, ở bảng file hoặc bảng thư mục."""
        return self._selected

    def open_selected(self) -> None:
        path = self.selected_path()
        if path:
            # explorer /select mở thư mục chứa và chọn sẵn file.
            subprocess.Popen(f'explorer.exe /select,"{path}"', creationflags=shell.CREATE_NO_WINDOW)

    def _update_buttons(self) -> None:
        self.search_button.setEnabled(not self.searching)
        self.stop_button.setEnabled(self.searching)
        self.open_button.setEnabled(self.selected_path() is not None)


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
        self.startup = StartupPanel(app, controller)
        self.bigfiles = BigFilesPanel(controller)
        self.tabs.addTab(self.cleanup, "Dọn rác")
        self.tabs.addTab(self.bigfiles, "File lớn")
        self.tabs.addTab(self.startup, "Khởi động cùng Windows")
        self.tabs.addTab(self.tweaks, "Tối ưu && quyền riêng tư")  # "&&": Qt hiểu "&" là phím tắt
        root.addWidget(self.tabs, 1)

    @property
    def loading(self) -> bool:
        return self.cleanup.loading

    def showEvent(self, event) -> None:
        if not self._started:
            self._started = True
            self.cleanup.rescan()
            self.startup.refresh()
        super().showEvent(event)

    def stop(self) -> None:
        self.cleanup.stop()
        self.bigfiles.stop()
