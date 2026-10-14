"""Tab "Gỡ phần mềm" ở trang Tối ưu & dọn dẹp (software/uninstall.py)."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...app import AppContext
from ...core.search import fold
from ...software import uninstall
from ..components.banner import Banner
from ..components.progress_panel import ProgressPanel
from ..controller import RunController
from ..theme import BAD, OK, TEXT_MUTED, WARN
from ..widgets import Worker

KEY_ROLE = Qt.ItemDataRole.UserRole
COLUMNS = ["Phần mềm", "Phiên bản", "Nhà phát hành", "Ngày cài", "Dung lượng", "Cách gỡ", "Ghi chú"]
NOTE_COLUMN = len(COLUMNS) - 1


def _load(app: AppContext) -> tuple[list[uninstall.Program], uninstall.Rules]:
    return uninstall.read_programs(app.env.target_user.sid), uninstall.load_rules(app.software.root)


class UninstallPanel(QWidget):
    unwanted_found = Signal(list)  # tên phần mềm nên gỡ còn trên máy (khung Tình trạng máy ở Trang chủ)

    def __init__(self, app: AppContext, controller: RunController):
        super().__init__()
        self.app = app
        self.controller = controller
        self.programs: list[uninstall.Program] = []
        self.rules = uninstall.Rules()
        self.loading = False
        self.worker = Worker(self)
        self.worker.done.connect(self._loaded)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(10)
        self.banner = Banner()
        self.banner.clicked.connect(self.select_unwanted)
        self.banner.hide()
        layout.addWidget(self.banner)
        note = QLabel("Tick phần mềm cần gỡ rồi bấm Gỡ. Dòng \"Tự gỡ\" được gỡ im lặng; dòng \"Bấm theo trình gỡ\" mở "
                      "cửa sổ gỡ của hãng, bấm Next / Uninstall trong cửa sổ đó. Lưu bài và đóng phần mềm trước khi gỡ. "
                      "Có cả phần mềm cài riêng cho người đang đăng nhập (như WPS Office).")
        note.setObjectName("PageSubtitle")
        note.setWordWrap(True)
        layout.addWidget(note)

        row = QHBoxLayout()
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Tìm theo tên hoặc nhà phát hành…")
        self.filter.setClearButtonEnabled(True)
        self.filter.textChanged.connect(self._apply_filter)
        self.show_hidden = QCheckBox("Hiện cả thành phần, bản cập nhật")
        self.show_hidden.toggled.connect(lambda _on: self._populate())
        self.refresh_button = QPushButton("Làm mới")
        self.refresh_button.clicked.connect(self.refresh)
        row.addWidget(self.filter, 1)
        row.addWidget(self.show_hidden)
        row.addWidget(self.refresh_button)
        layout.addLayout(row)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(COLUMNS)
        self.tree.setRootIsDecorated(False)
        self.tree.setUniformRowHeights(True)
        header = self.tree.header()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(NOTE_COLUMN, QHeaderView.ResizeMode.Stretch)
        self.tree.setColumnWidth(0, 300)
        self.tree.itemChanged.connect(lambda *_: self._update_buttons())
        layout.addWidget(self.tree, 1)

        row = QHBoxLayout()
        self.status = QLabel()
        self.status.setObjectName("PageSubtitle")
        self.uninstall_button = QPushButton("Gỡ phần mềm đã chọn")
        self.uninstall_button.setObjectName("Primary")
        self.uninstall_button.clicked.connect(self.uninstall_selected)
        row.addWidget(self.status, 1)
        row.addWidget(self.uninstall_button)
        layout.addLayout(row)

        self.progress = ProgressPanel(controller)
        self.progress.setMinimumHeight(220)
        self.progress.hide()
        self.progress.dismissed.connect(self.progress.hide)
        self.progress.completed.connect(lambda _result: self.refresh())
        layout.addWidget(self.progress)

        controller.busy_changed.connect(lambda _busy: self._update_buttons())
        self._update_buttons()

    # ------------------------------------------------------------ đọc danh sách

    def refresh(self) -> None:
        if self.loading:
            return
        self.loading = True
        self.status.setText("Đang đọc danh sách phần mềm…")
        self._update_buttons()
        self.worker.run("programs", lambda: _load(self.app))

    def _loaded(self, _name: str, result: object) -> None:
        self.loading = False
        if isinstance(result, Exception):
            self.status.setText(f"Không đọc được danh sách phần mềm: {result}")
            self._update_buttons()
            return
        checked = set(self.checked_keys())
        self.programs, self.rules = result
        self._populate(checked)
        self._show_banner()

    def _show_banner(self) -> None:
        found = uninstall.unwanted(self.programs, self.rules)
        self.unwanted_found.emit([program.name for program, _reason in found])
        if not found:
            self.banner.hide()
            return
        names = ", ".join(program.name for program, _reason in found[:4]) + ("…" if len(found) > 4 else "")
        self.banner.show_state("warn", f"Máy có {len(found)} phần mềm nên gỡ: {names}",
                               found[0][1] if len(found) == 1 else "Rê chuột vào cột Ghi chú để xem lý do.",
                               "Chọn các phần mềm này", primary=True)
        self.banner.show()

    def _populate(self, checked: set[str] | None = None) -> None:
        checked = set(self.checked_keys()) if checked is None else checked
        profile = self.app.env.target_user.profile_path or ""
        self.tree.blockSignals(True)
        self.tree.clear()
        shown = [program for program in self.programs if self.show_hidden.isChecked() or not program.hidden]
        # Phần mềm nên gỡ lên đầu, còn lại theo tên.
        shown.sort(key=lambda program: (not self.rules.unwanted_reason(program), program.name.lower()))
        for program in shown:
            how = uninstall.plan(program, self.rules, profile)
            unwanted = self.rules.unwanted_reason(program)
            keep = self.rules.keep_reason(program)
            if unwanted:
                note, color = f"Nên gỡ: {unwanted}", BAD
            elif keep:
                note, color = f"Nên giữ: {keep}", OK
            elif program.per_user:
                note, color = f"Chỉ cài cho {self.app.env.target_user.short_name}", TEXT_MUTED
            else:
                note, color = "", TEXT_MUTED
            if how is None or program.no_remove:
                note, color = "Không gỡ được ở đây, gỡ trong Settings > Apps", TEXT_MUTED
            item = QTreeWidgetItem([program.name, program.version, program.publisher, program.date_text,
                                    uninstall.size_text(program.size_kb), how.how if how else "", note])
            item.setData(0, KEY_ROLE, program.key)
            flags = item.flags() | Qt.ItemFlag.ItemIsUserCheckable
            if how is None or program.no_remove:
                flags &= ~Qt.ItemFlag.ItemIsEnabled
            item.setFlags(flags)
            item.setCheckState(0, Qt.CheckState.Checked if program.key in checked else Qt.CheckState.Unchecked)
            item.setForeground(NOTE_COLUMN, QBrush(QColor(color)))
            if how is not None and not how.silent:
                item.setForeground(5, QBrush(QColor(WARN)))
            item.setToolTip(0, program.key)
            item.setToolTip(5, f"{how.file} {how.args}".strip() if how else "")
            item.setToolTip(NOTE_COLUMN, note)
            self.tree.addTopLevelItem(item)
        self.tree.blockSignals(False)
        self._apply_filter(self.filter.text())
        self._update_buttons()

    def _apply_filter(self, text: str) -> None:
        words = fold(text).split()
        for index in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(index)
            haystack = fold(f"{item.text(0)} {item.text(2)}")
            item.setHidden(bool(words) and not all(word in haystack for word in words))

    # ------------------------------------------------------------ chọn và gỡ

    def checked_keys(self) -> list[str]:
        return [self.tree.topLevelItem(index).data(0, KEY_ROLE) for index in range(self.tree.topLevelItemCount())
                if self.tree.topLevelItem(index).checkState(0) == Qt.CheckState.Checked]

    def checked_programs(self) -> list[uninstall.Program]:
        keys = set(self.checked_keys())
        return [program for program in self.programs if program.key in keys]

    def select_unwanted(self) -> None:
        keys = {program.key for program, _reason in uninstall.unwanted(self.programs, self.rules)}
        self.filter.clear()
        for index in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(index)
            if item.data(0, KEY_ROLE) in keys and item.flags() & Qt.ItemFlag.ItemIsEnabled:
                item.setCheckState(0, Qt.CheckState.Checked)
        self.tree.scrollToTop()

    def _actions(self, programs: list[uninstall.Program]) -> list:
        env = self.app.env
        profile = env.target_user.profile_path or ""
        as_user = env.user_hive_sid is not None  # tool chạy bằng tài khoản khác người đang đăng nhập
        actions = [uninstall.uninstall_action(program, self.rules, as_user and program.per_user, profile)
                   for program in programs]
        return [action for action in actions if action is not None]

    def uninstall_selected(self) -> None:
        programs = self.checked_programs()
        if not programs:
            return
        profile = self.app.env.target_user.profile_path or ""
        lines = [f"Gỡ {len(programs)} phần mềm khỏi máy này?", ""]
        lines += [f"• {program.name}" for program in programs[:12]]
        if len(programs) > 12:
            lines.append(f"• … và {len(programs) - 12} phần mềm khác")
        keep = [program.name for program in programs if self.rules.keep_reason(program)]
        if keep:
            lines += ["", "Cẩn thận: " + ", ".join(keep[:4]) + (" …" if len(keep) > 4 else "")
                      + " thường cần cho máy hoặc phần mềm khác chạy."]
        manual = [program.name for program in programs
                  if (how := uninstall.plan(program, self.rules, profile)) is not None and not how.silent]
        if manual:
            lines += ["", f"{len(manual)} phần mềm sẽ mở cửa sổ gỡ của hãng: bấm Next / Uninstall trong cửa sổ đó."]
        lines += ["", "Lưu bài và đóng các phần mềm này trước. Gỡ rồi thì phải cài lại, không hoàn tác được."]
        if not self.confirm("\n".join(lines), risky=bool(keep)):
            return
        self.progress.watch("Gỡ phần mềm")
        self.progress.show()
        self.controller.run(self._actions(programs))

    def confirm(self, text: str, risky: bool) -> bool:
        """Hỏi trước khi gỡ. `risky`: có phần mềm nên giữ, nút mặc định là Không."""
        icon = QMessageBox.Icon.Warning if risky else QMessageBox.Icon.Question
        box = QMessageBox(icon, "Gỡ phần mềm", text, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                          self)
        box.setDefaultButton(QMessageBox.StandardButton.No if risky else QMessageBox.StandardButton.Yes)
        return box.exec() == QMessageBox.StandardButton.Yes

    def _update_buttons(self) -> None:
        busy = self.controller.busy
        count = len(self.checked_keys())
        self.refresh_button.setEnabled(not busy and not self.loading)
        self.uninstall_button.setEnabled(not busy and not self.loading and count > 0)
        self.uninstall_button.setText(f"Gỡ {count} phần mềm đã chọn" if count else "Gỡ phần mềm đã chọn")
        if not self.loading and self.programs:
            visible = sum(1 for program in self.programs if not program.hidden)
            self.status.setText(f"{visible} phần mềm trên máy" + (f" · đã chọn {count}" if count else ""))
