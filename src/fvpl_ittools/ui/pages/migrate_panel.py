"""Tab "Chuyển máy" ở trang Tiện ích: sao lưu dữ liệu người dùng trên máy cũ, khôi phục trên máy mới (core/migrate.py)."""

from __future__ import annotations

import html
import logging
import shutil
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ... import __version__
from ...app import AppContext
from ...core import migrate, paths
from ...core.executor import BatchResult, Level
from ..components.progress_panel import ProgressPanel
from ..controller import RunController
from ..widgets import Worker, open_path

log = logging.getLogger(__name__)
ID_ROLE = Qt.ItemDataRole.UserRole


def _card(title: str) -> tuple[QFrame, QVBoxLayout]:
    card = QFrame()
    card.setObjectName("Card")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(16, 14, 16, 14)
    layout.setSpacing(8)
    label = QLabel(title)
    label.setObjectName("CardTitle")
    layout.addWidget(label)
    return card, layout


def _note(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("PageSubtitle")
    label.setWordWrap(True)
    return label


def _tree(headers: list[str]) -> QTreeWidget:
    tree = QTreeWidget()
    tree.setHeaderLabels(headers)
    tree.setRootIsDecorated(False)
    tree.setUniformRowHeights(True)
    tree.setMinimumHeight(170)
    tree.header().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
    tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
    tree.setColumnWidth(0, 230)  # đủ cho "Documents (Tài liệu)" kèm ô tick
    return tree


def _collect(app: AppContext, cancel=None) -> tuple[list[migrate.Source], list[dict], list[str]]:
    """Ở thread nền: dung lượng các mục, danh sách máy in và phần mềm của máy này."""
    from ...printers import manage
    from ...software.detect import installed_programs
    user = app.env.target_user
    sources = migrate.scan_sources(user.sid, user.profile_path or "", cancel)
    try:
        printers = [{"name": printer.name, "label": printer.label, "where": printer.host or printer.port,
                     "driver": printer.driver, "default": printer.default}
                    for printer in manage.snapshot(app.env, cancel).printers]
    except Exception:  # danh sách máy in chỉ để tham khảo, lỗi thì bỏ qua
        log.exception("Không đọc được danh sách máy in để chuyển máy")
        printers = []
    software = [entry.name for entry in installed_programs(user.sid) if not entry.hidden]
    return sources, printers, software


class MigratePanel(QWidget):
    software_wanted = Signal(list)  # tên phần mềm máy cũ đã cài → chọn sẵn ở trang Cài phần mềm

    def __init__(self, app: AppContext, controller: RunController):
        super().__init__()
        self.app = app
        self.controller = controller
        self.sources: list[migrate.Source] = []
        self.printers: list[dict] = []
        self.software: list[str] = []
        self.backups: list[migrate.Backup] = []
        self.root = migrate.backups_root(paths.portable_root())
        self.target: Path | None = self.root
        self.scanning = False
        self._started = False
        self.worker = Worker(self)
        self.worker.done.connect(self._done)
        user = app.env.target_user.short_name

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 12, 12, 8)
        layout.setSpacing(12)

        card, box = _card(f"1. Máy cũ: sao lưu dữ liệu của {user}")
        box.addWidget(_note("Chép thư mục cá nhân, bookmark trình duyệt, chữ ký Outlook ra ổ mang theo, kèm danh sách máy "
                            "in và phần mềm để cài lại. Chỉ đọc trên máy này, không xoá gì. Mục đồng bộ OneDrive thì "
                            "không cần chép: đăng nhập OneDrive trên máy mới là có."))
        self.source_tree = _tree(["Mục", "Ở đâu", "Dung lượng"])
        self.source_tree.itemChanged.connect(lambda *_: self._update_source_status())
        box.addWidget(self.source_tree)
        row = QHBoxLayout()
        self.target_label = QLabel()
        self.target_label.setWordWrap(True)
        self.target_button = QPushButton("Đổi nơi lưu…")
        self.target_button.clicked.connect(self.choose_target)
        row.addWidget(self.target_label, 1)
        row.addWidget(self.target_button)
        box.addLayout(row)
        row = QHBoxLayout()
        self.source_status = QLabel()
        self.source_status.setObjectName("PageSubtitle")
        self.source_status.setWordWrap(True)
        self.rescan_button = QPushButton("Quét lại")
        self.rescan_button.clicked.connect(self.scan)
        self.backup_button = QPushButton("Sao lưu")
        self.backup_button.setObjectName("Primary")
        self.backup_button.clicked.connect(self.backup)
        row.addWidget(self.source_status, 1)
        row.addWidget(self.rescan_button)
        row.addWidget(self.backup_button)
        box.addLayout(row)
        layout.addWidget(card)

        card, box = _card(f"2. Máy mới: khôi phục vào hồ sơ của {user}")
        box.addWidget(_note("Chọn bản sao lưu trên ổ mang theo. File đã có trên máy này mà mới hơn thì giữ nguyên; bookmark "
                            "cũ của máy này được đổi tên giữ lại. Đóng Chrome / Edge trước khi khôi phục bookmark."))
        row = QHBoxLayout()
        self.backup_combo = QComboBox()
        self.backup_combo.currentIndexChanged.connect(self._show_backup)
        self.pick_backup_button = QPushButton("Chọn thư mục khác…")
        self.pick_backup_button.clicked.connect(self.choose_backup)
        self.open_backup_button = QPushButton("Mở thư mục")
        self.open_backup_button.clicked.connect(lambda: open_path(self.current_backup().folder)
                                                if self.current_backup() else None)
        row.addWidget(self.backup_combo, 1)
        row.addWidget(self.pick_backup_button)
        row.addWidget(self.open_backup_button)
        box.addLayout(row)
        self.restore_tree = _tree(["Mục", "Chép vào", "Dung lượng"])
        box.addWidget(self.restore_tree)
        self.backup_info = _note("")
        self.backup_info.setTextFormat(Qt.TextFormat.RichText)
        box.addWidget(self.backup_info)
        row = QHBoxLayout()
        self.software_button = QPushButton("Chọn sẵn phần mềm ở trang Cài phần mềm")
        self.software_button.clicked.connect(self._want_software)
        self.restore_button = QPushButton("Khôi phục")
        self.restore_button.setObjectName("Primary")
        self.restore_button.clicked.connect(self.restore)
        row.addWidget(self.software_button)
        row.addStretch(1)
        row.addWidget(self.restore_button)
        box.addLayout(row)
        layout.addWidget(card)

        self.progress = ProgressPanel(controller)
        self.progress.setMinimumHeight(240)
        self.progress.hide()
        self.progress.dismissed.connect(self.progress.hide)
        self.progress.completed.connect(self._run_done)
        layout.addWidget(self.progress)
        layout.addStretch(1)

        controller.busy_changed.connect(lambda _busy: self._update_buttons())
        self._show_target()
        self.refresh_backups()

    # ------------------------------------------------------------ máy cũ

    def showEvent(self, event) -> None:
        if not self._started:
            self._started = True
            self.scan()
        super().showEvent(event)

    def scan(self) -> None:
        self.scanning = True
        self.source_status.setText("Đang đếm dung lượng…")
        self._update_buttons()
        self.worker.run("scan", lambda: _collect(self.app))

    def _done(self, name: str, result: object) -> None:
        if name != "scan":
            return
        self.scanning = False
        if isinstance(result, Exception):
            self.source_status.setText(f"Không quét được: {result}")
        else:
            self.sources, self.printers, self.software = result
            self._fill_sources()
        self._update_buttons()

    def _fill_sources(self) -> None:
        self.source_tree.clear()
        for source in self.sources:
            spec = source.spec
            where = source.path + ("  (đồng bộ OneDrive)" if source.onedrive else "")
            size = migrate.size_text(source.bytes) + (f" · {source.files} file" if spec.kind != "bookmarks" else "")
            item = QTreeWidgetItem([spec.label, where if source.exists else "Không có trên máy này",
                                    size if source.exists else ""])
            item.setData(0, ID_ROLE, spec.id)
            flags = item.flags() | Qt.ItemFlag.ItemIsUserCheckable
            if not source.exists or (source.files == 0 and spec.kind != "bookmarks"):
                flags &= ~Qt.ItemFlag.ItemIsEnabled
            item.setFlags(flags)
            wanted = source.exists and source.files > 0 and spec.default and not source.onedrive
            item.setCheckState(0, Qt.CheckState.Checked if wanted else Qt.CheckState.Unchecked)
            self.source_tree.addTopLevelItem(item)
        self._update_source_status()

    def selected_sources(self) -> list[migrate.Source]:
        checked = set()
        for index in range(self.source_tree.topLevelItemCount()):
            item = self.source_tree.topLevelItem(index)
            if item.checkState(0) == Qt.CheckState.Checked and item.flags() & Qt.ItemFlag.ItemIsEnabled:
                checked.add(item.data(0, ID_ROLE))
        return [source for source in self.sources if source.spec.id in checked]

    def _update_source_status(self) -> None:
        selected = self.selected_sources()
        total = sum(source.bytes for source in selected)
        text = f"Đã chọn {len(selected)} mục, {migrate.size_text(total)}"
        free = self._free_space()
        if free is not None:
            text += f" · nơi lưu còn trống {migrate.size_text(free)}"
            if total > free:
                text += " · KHÔNG ĐỦ CHỖ"
        text += f" · {len(self.printers)} máy in, {len(self.software)} phần mềm sẽ được ghi danh sách"
        self.source_status.setText(text)
        self._update_buttons()

    def _free_space(self) -> int | None:
        folder = self.target
        while folder is not None and not folder.exists():
            folder = folder.parent if folder.parent != folder else None
        try:
            return shutil.disk_usage(folder).free if folder is not None else None
        except OSError:
            return None

    def _show_target(self) -> None:
        self.target_label.setText(f"Lưu vào: <b>{html.escape(str(self.target))}</b>" if self.target is not None
                                  else "Tool đang chạy từ bản chép trong máy: bấm Đổi nơi lưu để chọn ổ mang theo.")

    def choose_target(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Chọn nơi lưu bản sao lưu (ổ USB / SSD)")
        if folder:
            self.target = Path(folder) / migrate.FOLDER
            self._show_target()
            self._update_source_status()

    def backup(self) -> None:
        selected = self.selected_sources()
        if not selected:
            QMessageBox.information(self, "Chưa chọn", "Tick ít nhất một mục cần sao lưu.")
            return
        if self.target is None:
            self.choose_target()
            if self.target is None:
                return
        total = sum(source.bytes for source in selected)
        free = self._free_space()
        if free is not None and total > free:
            QMessageBox.warning(self, "Không đủ chỗ", f"Cần {migrate.size_text(total)}, nơi lưu chỉ còn "
                                                      f"{migrate.size_text(free)}. Bỏ bớt mục hoặc chọn ổ khác.")
            return
        machine, user = self.app.machine, self.app.env.target_user
        folder = migrate.new_backup_folder(self.target, machine.computer_name, user.name)
        try:
            migrate.write_manifest(folder, machine.computer_name, user.name, __version__, selected, self.printers,
                                   self.software)
        except OSError as exc:
            QMessageBox.warning(self, "Không ghi được", f"Không tạo được thư mục sao lưu {folder}: {exc}")
            return
        self.controller.say(Level.INFO, f"Sao lưu dữ liệu {user.name} vào {folder}")
        self.progress.watch("Sao lưu dữ liệu người dùng")
        self.progress.show()
        self.controller.run(migrate.backup_actions(selected, folder))

    # ------------------------------------------------------------ máy mới

    def refresh_backups(self, select: Path | None = None) -> None:
        self.backups = migrate.list_backups(self.root)
        if select is not None and all(backup.folder != select for backup in self.backups):
            try:
                self.backups.insert(0, migrate.read_backup(select))
            except migrate.MigrateError as exc:
                QMessageBox.warning(self, "Không đọc được", str(exc))
        self.backup_combo.blockSignals(True)
        self.backup_combo.clear()
        for backup in self.backups:
            self.backup_combo.addItem(backup.label, str(backup.folder))
        if select is not None:
            self.backup_combo.setCurrentIndex(max(0, self.backup_combo.findData(str(select))))
        self.backup_combo.blockSignals(False)
        if not self.backups:
            self.backup_combo.addItem("Chưa có bản sao lưu nào trên ổ này", "")
        self._show_backup()

    def current_backup(self) -> migrate.Backup | None:
        folder = self.backup_combo.currentData()
        return next((backup for backup in self.backups if str(backup.folder) == folder), None)

    def choose_backup(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Chọn thư mục bản sao lưu (có file manifest.json)")
        if folder:
            self.refresh_backups(Path(folder))

    def _show_backup(self) -> None:
        self.restore_tree.clear()
        backup = self.current_backup()
        if backup is None:
            self.backup_info.setText("")
            self._update_buttons()
            return
        user = self.app.env.target_user
        folders = migrate.shell_folders(user.sid)
        for entry in backup.items:
            spec = migrate.SPECS[entry["id"]]
            exists = (backup.folder / spec.folder).exists()
            target = migrate.item_path(spec, user.profile_path or "", folders)
            item = QTreeWidgetItem([spec.label, target if exists else "Thiếu trong bản sao lưu",
                                    migrate.size_text(int(entry.get("bytes") or 0))])
            item.setData(0, ID_ROLE, spec.id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(0, Qt.CheckState.Checked if exists else Qt.CheckState.Unchecked)
            self.restore_tree.addTopLevelItem(item)
        printers = ", ".join(f"{printer.get('name')}" + (f" ({printer.get('where')})" if printer.get("where") else "")
                             for printer in backup.printers[:8]) or "không có"
        computer, user, created, printers = (html.escape(str(value)) for value in
                                             (backup.computer, backup.user, backup.created, printers))
        self.backup_info.setText(f"Từ máy <b>{computer}</b>, người dùng {user}, lúc {created}.<br>"
                                 f"Máy in máy cũ: {printers}. Thêm lại ở trang Máy in.<br>"
                                 f"Máy cũ có {len(backup.software)} phần mềm.")
        self._update_buttons()

    def selected_restore(self) -> list[str]:
        return [self.restore_tree.topLevelItem(index).data(0, ID_ROLE)
                for index in range(self.restore_tree.topLevelItemCount())
                if self.restore_tree.topLevelItem(index).checkState(0) == Qt.CheckState.Checked]

    def restore(self) -> None:
        backup, ids = self.current_backup(), self.selected_restore()
        if backup is None or not ids:
            QMessageBox.information(self, "Chưa chọn", "Chọn bản sao lưu và tick các mục cần khôi phục.")
            return
        user = self.app.env.target_user
        answer = QMessageBox.question(
            self, "Khôi phục", f"Chép {len(ids)} mục từ máy {backup.computer} vào hồ sơ của {user.name}?\n\n"
                               "File đã có trên máy này mà mới hơn thì giữ nguyên. Không xoá gì.")
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.progress.watch("Khôi phục dữ liệu người dùng")
        self.progress.show()
        self.controller.run(migrate.restore_actions(backup, ids, user.sid, user.profile_path or ""))

    def _want_software(self) -> None:
        backup = self.current_backup()
        if backup is not None:
            self.software_wanted.emit(list(backup.software))

    # ------------------------------------------------------------ chung

    def _run_done(self, _result: BatchResult) -> None:
        self.refresh_backups()

    def _update_buttons(self) -> None:
        busy = self.controller.busy
        self.backup_button.setEnabled(not busy and not self.scanning and bool(self.selected_sources()))
        self.rescan_button.setEnabled(not busy and not self.scanning)
        backup = self.current_backup()
        self.restore_button.setEnabled(not busy and backup is not None)
        self.software_button.setEnabled(backup is not None and bool(backup.software))
        self.open_backup_button.setEnabled(backup is not None)
