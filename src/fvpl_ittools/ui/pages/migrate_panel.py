"""Tab "Sao lưu dữ liệu" ở trang Tiện ích: sao lưu trước khi cài lại Windows / trên máy cũ, khôi phục sau khi cài
lại / trên máy mới (core/migrate.py)."""

from __future__ import annotations

import html
import logging
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
from ...core import migrate, paths, session
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
    tree.setColumnWidth(0, 250)  # đủ cho "File dữ liệu Outlook (.pst)" kèm ô tick
    return tree


def _collect(app: AppContext, user: session.UserIdentity, extras: list[str], cancel=None) -> dict:
    """Ở thread nền: người dùng trên máy, các mục và dung lượng, thư mục lạ ở gốc ổ C, máy in, phần mềm, các ổ."""
    from ...printers import manage
    from ...software.detect import installed_programs
    suggested = [path for path in migrate.root_folders() if path.lower() not in {extra.lower() for extra in extras}]
    sources = migrate.scan_sources(user.sid, user.profile_path or "", cancel, extras + suggested)
    try:
        printers = [{"name": printer.name, "label": printer.label, "where": printer.host or printer.port,
                     "driver": printer.driver, "default": printer.default}
                    for printer in manage.snapshot(app.env, cancel).printers]
    except Exception:  # danh sách máy in chỉ để tham khảo, lỗi thì bỏ qua
        log.exception("Không đọc được danh sách máy in để sao lưu")
        printers = []
    software = [entry.name for entry in installed_programs(user.sid) if not entry.hidden]
    return {"users": session.user_profiles(), "sources": sources, "suggested": suggested, "printers": printers,
            "software": software, "drives": migrate.list_drives()}


def _find(extra_roots: list[Path]) -> tuple[list[migrate.Drive], list[migrate.Backup]]:
    drives = migrate.list_drives()
    return drives, migrate.find_backups(drives, extra_roots)


class MigratePanel(QWidget):
    software_wanted = Signal(list)  # tên phần mềm máy cũ đã cài → chọn sẵn ở trang Cài phần mềm

    def __init__(self, app: AppContext, controller: RunController):
        super().__init__()
        self.app = app
        self.controller = controller
        self.user: session.UserIdentity = app.env.target_user
        self.users: list[session.UserIdentity] = []
        self.sources: list[migrate.Source] = []
        self.suggested: list[str] = []
        self.extras: list[str] = []  # thư mục IT thêm bằng tay
        self.printers: list[dict] = []
        self.software: list[str] = []
        self.drives: list[migrate.Drive] = []
        self.backups: list[migrate.Backup] = []
        self.chosen_target: Path | None = None   # IT bấm Đổi nơi lưu
        self.chosen_roots: list[Path] = []       # thư mục IT chọn thêm khi tìm bản sao lưu
        self.scanning = False
        self.finding = False
        self._started = False
        self._fresh = True       # lần quét tới tick theo mặc định (lần đầu, đổi người dùng)
        self._just_added = ""    # thư mục vừa thêm bằng tay: tick sẵn
        self.worker = Worker(self)
        self.worker.done.connect(self._done)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 12, 12, 8)
        layout.setSpacing(12)

        card, box = _card("1. Sao lưu: trước khi cài lại Windows, hoặc trên máy cũ")
        box.addWidget(_note("Chép dữ liệu ra ổ khác ổ C để cài lại Windows không bị mất. Tool tự chọn nơi lưu: USB / SSD "
                            "đang chạy tool, không thì ổ D. Chỉ đọc trên máy này, không xoá gì. Thư mục đồng bộ OneDrive "
                            "không tick sẵn (đã có trên mây). Thư mục lạ ở gốc ổ C (như C:\\KeToan) có trong danh sách, "
                            "tick nếu là dữ liệu."))
        row = QHBoxLayout()
        row.addWidget(QLabel("Dữ liệu của:"))
        self.user_combo = QComboBox()
        self.user_combo.setMinimumWidth(260)
        self.user_combo.currentIndexChanged.connect(self._user_changed)
        row.addWidget(self.user_combo)
        row.addStretch(1)
        self.add_folder_button = QPushButton("Thêm thư mục khác…")
        self.add_folder_button.clicked.connect(self.add_folder)
        row.addWidget(self.add_folder_button)
        box.addLayout(row)
        self.source_tree = _tree(["Mục", "Ở đâu", "Dung lượng"])
        self.source_tree.setMinimumHeight(340)
        self.source_tree.itemChanged.connect(lambda *_: self._update_source_status())
        box.addWidget(self.source_tree)
        row = QHBoxLayout()
        self.target_label = QLabel()
        self.target_label.setWordWrap(True)
        self.target_label.setTextFormat(Qt.TextFormat.RichText)
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

        card, box = _card(f"2. Khôi phục: sau khi cài lại Windows, hoặc trên máy mới (vào hồ sơ của "
                          f"{app.env.target_user.short_name})")
        box.addWidget(_note("Tool tìm bản sao lưu trên mọi ổ (USB, ổ D). File đã có trên máy này mà mới hơn thì giữ "
                            "nguyên; bookmark cũ của máy này được đổi tên giữ lại. Đóng trình duyệt, Outlook trước khi "
                            "khôi phục. Driver cần quyền admin."))
        row = QHBoxLayout()
        self.backup_combo = QComboBox()
        self.backup_combo.currentIndexChanged.connect(self._show_backup)
        self.find_button = QPushButton("Tìm lại")
        self.find_button.clicked.connect(self.refresh_backups)
        self.pick_backup_button = QPushButton("Chọn thư mục khác…")
        self.pick_backup_button.clicked.connect(self.choose_backup)
        self.open_backup_button = QPushButton("Mở thư mục")
        self.open_backup_button.clicked.connect(lambda: open_path(self.current_backup().folder)
                                                if self.current_backup() else None)
        row.addWidget(self.backup_combo, 1)
        row.addWidget(self.find_button)
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
        self._fill_backups()

    # ------------------------------------------------------------ sao lưu

    def showEvent(self, event) -> None:
        if not self._started:
            self._started = True
            self.scan()
            self.refresh_backups()
        super().showEvent(event)

    def scan(self) -> None:
        self.scanning = True
        self.source_status.setText("Đang đếm dung lượng…")
        self._update_buttons()
        user, extras = self.user, list(self.extras)
        self.worker.run("scan", lambda: _collect(self.app, user, extras))

    def _done(self, name: str, result: object) -> None:
        if name == "find":
            self.finding = False
            if isinstance(result, Exception):
                self.backup_info.setText(html.escape(f"Không tìm được bản sao lưu: {result}"))
            else:
                self.drives, self.backups = result
                self._fill_backups()
                self._show_target()
            self._update_buttons()
            return
        if name != "scan":
            return
        self.scanning = False
        if isinstance(result, Exception):
            self.source_status.setText(f"Không quét được: {result}")
        else:
            self.sources, self.suggested = result["sources"], result["suggested"]
            self.printers, self.software, self.drives = result["printers"], result["software"], result["drives"]
            self._fill_users(result["users"])
            self._fill_sources()
        self._update_buttons()

    def _fill_users(self, users: list[session.UserIdentity]) -> None:
        current = self.app.env.target_user
        if not any(user.sid == current.sid for user in users):
            users = [current, *users]
        self.users = users
        self.user_combo.blockSignals(True)
        self.user_combo.clear()
        for user in users:
            note = " (đang đăng nhập)" if user.sid == current.sid else ""
            self.user_combo.addItem(f"{user.name}{note}", user.sid)
        self.user_combo.setCurrentIndex(max(0, self.user_combo.findData(self.user.sid)))
        self.user_combo.blockSignals(False)

    def _user_changed(self) -> None:
        sid = self.user_combo.currentData()
        user = next((user for user in self.users if user.sid == sid), None)
        if user is not None and user.sid != self.user.sid:
            self.user = user
            self._fresh = True
            self.scan()

    def _fill_sources(self) -> None:
        # Quét lại thì giữ lựa chọn cũ của các mục đã có; mục mới (hoặc đổi người dùng) thì theo mặc định.
        previous: dict[str, bool] = {}
        if not self._fresh:
            for index in range(self.source_tree.topLevelItemCount()):
                item = self.source_tree.topLevelItem(index)
                if item.flags() & Qt.ItemFlag.ItemIsEnabled:
                    previous[item.data(0, ID_ROLE)] = item.checkState(0) == Qt.CheckState.Checked
        self._fresh = False
        self.source_tree.blockSignals(True)
        self.source_tree.clear()
        suggested = {path.lower() for path in self.suggested}
        for source in self.sources:
            spec = source.spec
            where = source.path + ("  (đồng bộ OneDrive)" if source.onedrive else "")
            label = spec.label if spec.kind != "extra" else f"Thư mục {spec.label}"
            item = QTreeWidgetItem([label, where if source.exists else "Không có trên máy này",
                                    source.size_label if source.usable else ""])
            item.setData(0, ID_ROLE, spec.id)
            flags = item.flags() | Qt.ItemFlag.ItemIsUserCheckable
            if not source.usable:
                flags &= ~Qt.ItemFlag.ItemIsEnabled
            item.setFlags(flags)
            wanted = previous.get(spec.id, self._default_checked(source, suggested))
            if spec.kind == "extra" and source.path.lower() == self._just_added.lower():
                wanted = True
            item.setCheckState(0, Qt.CheckState.Checked if wanted and source.usable else Qt.CheckState.Unchecked)
            if spec.kind == "wifi":
                item.setToolTip(0, "Có cả mật khẩu Wi-Fi: cất USB cẩn thận, xoá bản sao lưu sau khi khôi phục xong")
            elif spec.kind == "drivers":
                item.setToolTip(0, "Driver của hãng để cài lại sau khi cài Windows mà chưa có mạng (cần quyền admin)")
            self.source_tree.addTopLevelItem(item)
        self.source_tree.blockSignals(False)
        self._just_added = ""
        self._update_source_status()

    def _default_checked(self, source: migrate.Source, suggested: set[str]) -> bool:
        spec = source.spec
        if spec.kind == "extra":
            return source.path.lower() not in suggested  # thư mục IT tự thêm: tick; thư mục lạ tìm thấy: không
        if spec.kind == "drivers":
            return self.app.env.is_admin  # không có quyền admin thì mục này bị bỏ qua khi chạy
        return spec.default and not source.onedrive

    def add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Chọn thư mục cần sao lưu thêm")
        if not folder:
            return
        folder = str(Path(folder))
        if folder.lower() not in {extra.lower() for extra in self.extras}:
            self.extras.append(folder)
        self._just_added = folder
        self.scan()

    def selected_sources(self) -> list[migrate.Source]:
        checked = set()
        for index in range(self.source_tree.topLevelItemCount()):
            item = self.source_tree.topLevelItem(index)
            if item.checkState(0) == Qt.CheckState.Checked and item.flags() & Qt.ItemFlag.ItemIsEnabled:
                checked.add(item.data(0, ID_ROLE))
        return [source for source in self.sources if source.spec.id in checked]

    def needed(self) -> int:
        return sum(source.estimate for source in self.selected_sources())

    @property
    def target(self) -> Path | None:
        """Thư mục FVPL-SaoLuu sẽ lưu vào: nơi IT chọn, không thì tự chọn theo dung lượng cần."""
        if self.chosen_target is not None:
            return self.chosen_target
        return migrate.pick_target(self.drives, paths.portable_root(), self.needed())

    def _update_source_status(self) -> None:
        selected = self.selected_sources()
        total = sum(source.bytes for source in selected)
        text = f"Đã chọn {len(selected)} mục, {migrate.size_text(total)}"
        if any(source.spec.kind == "drivers" for source in selected):
            text += " + driver"
        free = migrate.free_space(self.target)
        if free is not None:
            text += f" · nơi lưu còn trống {migrate.size_text(free)}"
            if self.needed() > free:
                text += " · KHÔNG ĐỦ CHỖ"
        text += f" · {len(self.printers)} máy in, {len(self.software)} phần mềm sẽ được ghi danh sách"
        self.source_status.setText(text)
        self._show_target()
        self._update_buttons()

    def _show_target(self) -> None:
        target = self.target
        if target is None:
            self.target_label.setText(
                f"<b>Chưa có nơi lưu</b>: không có ổ nào ngoài ổ {migrate.system_drive()} đủ chỗ "
                f"({migrate.size_text(self.needed())}). Cắm USB / ổ cứng ngoài rồi bấm Quét lại, hoặc bấm Đổi nơi lưu "
                "(ổ mạng).")
            return
        text = f"Lưu vào: <b>{html.escape(str(target))}</b>"
        drive = next((drive for drive in self.drives if drive.letter == str(target)[:2].upper()), None)
        if migrate.on_system_drive(target):
            text += (f" <span style='color:#c42b1c'>(nằm trên ổ {migrate.system_drive()}: cài lại Windows sẽ mất, "
                     "chỉ dùng khi chuyển sang máy khác)</span>")
        elif drive is not None and drive.kind == "fixed":
            text += (f" · {html.escape(drive.title)}. Khi cài lại Windows chỉ xoá / format phân vùng ổ "
                     f"{migrate.system_drive()}, giữ nguyên ổ {drive.letter}.")
        elif drive is not None:
            text += f" · {html.escape(drive.title)}"
        self.target_label.setText(text)

    def choose_target(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Chọn nơi lưu bản sao lưu (ổ D, USB, ổ mạng)")
        if folder:
            self.chosen_target = Path(folder) / migrate.FOLDER
            self._update_source_status()

    def backup(self) -> None:
        selected = self.selected_sources()
        if not selected:
            QMessageBox.information(self, "Chưa chọn", "Tick ít nhất một mục cần sao lưu.")
            return
        target = self.target
        if target is None:
            self.choose_target()
            target = self.chosen_target
            if target is None:
                return
        free = migrate.free_space(target)
        if free is not None and self.needed() > free:
            QMessageBox.warning(self, "Không đủ chỗ", f"Cần {migrate.size_text(self.needed())}, nơi lưu chỉ còn "
                                                      f"{migrate.size_text(free)}. Bỏ bớt mục hoặc chọn ổ khác.")
            return
        if migrate.on_system_drive(target) and not self.confirm_system_drive(target):
            return
        machine, user = self.app.machine, self.user
        folder = migrate.new_backup_folder(target, machine.computer_name, user.name)
        try:
            migrate.write_manifest(folder, machine.computer_name, user.name, __version__, selected, self.printers,
                                   self.software)
        except OSError as exc:
            QMessageBox.warning(self, "Không ghi được", f"Không tạo được thư mục sao lưu {folder}: {exc}")
            return
        if target not in self.chosen_roots:
            self.chosen_roots.append(target)
        self.controller.say(Level.INFO, f"Sao lưu dữ liệu {user.name} vào {folder}")
        self.progress.watch("Sao lưu dữ liệu")
        self.progress.show()
        self.controller.run(migrate.backup_actions(selected, folder))

    def confirm_system_drive(self, target: Path) -> bool:
        answer = QMessageBox.question(
            self, "Lưu trên ổ Windows?",
            f"{target} nằm trên ổ {migrate.system_drive()}. Cài lại Windows sẽ xoá mất bản sao lưu này.\n\n"
            "Chỉ lưu ở đây khi chuyển dữ liệu sang máy khác qua mạng. Vẫn lưu?")
        return answer == QMessageBox.StandardButton.Yes

    # ------------------------------------------------------------ khôi phục

    def refresh_backups(self) -> None:
        if self.finding:
            return
        self.finding = True
        self._update_buttons()
        roots = list(self.chosen_roots)
        self.worker.run("find", lambda: _find(roots))

    def _fill_backups(self, select: Path | None = None) -> None:
        self.backup_combo.blockSignals(True)
        self.backup_combo.clear()
        for backup in self.backups:
            self.backup_combo.addItem(backup.label, str(backup.folder))
        if select is not None:
            self.backup_combo.setCurrentIndex(max(0, self.backup_combo.findData(str(select))))
        self.backup_combo.blockSignals(False)
        if not self.backups:
            self.backup_combo.addItem("Đang tìm bản sao lưu…" if self.finding or not self._started
                                      else "Không thấy bản sao lưu nào trên các ổ", "")
        self._show_backup()

    def current_backup(self) -> migrate.Backup | None:
        folder = self.backup_combo.currentData()
        return next((backup for backup in self.backups if str(backup.folder) == folder), None)

    def choose_backup(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Chọn thư mục bản sao lưu (có file manifest.json)")
        if not folder:
            return
        folder = Path(folder)
        try:
            backup = migrate.read_backup(folder)
        except migrate.MigrateError:
            found = migrate.list_backups(folder)  # chọn thư mục FVPL-SaoLuu chứa nhiều bản
            if not found:
                QMessageBox.warning(self, "Không đọc được", f"{folder} không có bản sao lưu của tool.")
                return
            backup = found[0]
            self.chosen_roots.append(folder)
        self.backups = [backup, *(item for item in self.backups if item.folder != backup.folder)]
        self._fill_backups(backup.folder)

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
            spec = backup.spec(entry)
            exists = (backup.folder / (entry.get("folder") or spec.folder)).exists()
            target = migrate.restore_target(spec, user.profile_path or "", folders)
            size = f"{entry.get('files') or 0} mạng" if spec.kind == "wifi" else (
                "" if spec.kind == "drivers" else migrate.size_text(int(entry.get("bytes") or 0)))
            label = spec.label if spec.kind != "extra" else f"Thư mục {spec.label}"
            item = QTreeWidgetItem([label, target if exists else "Thiếu trong bản sao lưu", size])
            item.setData(0, ID_ROLE, spec.id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            wanted = exists and (spec.kind != "drivers" or self.app.env.is_admin)
            item.setCheckState(0, Qt.CheckState.Checked if wanted else Qt.CheckState.Unchecked)
            self.restore_tree.addTopLevelItem(item)
        printers = ", ".join(f"{printer.get('name')}" + (f" ({printer.get('where')})" if printer.get("where") else "")
                             for printer in backup.printers[:8]) or "không có"
        computer, owner, created, printers, where = (html.escape(str(value)) for value in
                                                    (backup.computer, backup.user, backup.created, printers,
                                                     backup.folder))
        self.backup_info.setText(f"Từ máy <b>{computer}</b>, người dùng {owner}, lúc {created}, ở {where}.<br>"
                                 f"Máy in: {printers}. Thêm lại ở trang Máy in.<br>"
                                 f"Máy có {len(backup.software)} phần mềm.")
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
            self, "Khôi phục", f"Chép {len(ids)} mục từ bản sao lưu của {backup.computer} vào hồ sơ của {user.name}?\n\n"
                               "File đã có trên máy này mà mới hơn thì giữ nguyên. Không xoá gì.")
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.progress.watch("Khôi phục dữ liệu")
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
        self.add_folder_button.setEnabled(not self.scanning)
        self.user_combo.setEnabled(not self.scanning)
        self.find_button.setEnabled(not self.finding)
        backup = self.current_backup()
        self.restore_button.setEnabled(not busy and backup is not None)
        self.software_button.setEnabled(backup is not None and bool(backup.software))
        self.open_backup_button.setEnabled(backup is not None)
