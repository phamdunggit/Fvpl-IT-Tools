"""Hộp thoại sửa biến PATH: hai danh sách (cả máy, người dùng), mục hỏng / trùng tô màu, thêm / gỡ / đổi thứ tự.

Bấm Lưu thì chạy mục registry qua RunController (có nhật ký, hoàn tác ở trang Nhật ký).
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
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

from ...app import AppContext
from ...core import envpath, registry
from .. import theme
from ..controller import RunController

STATE_COLORS = {"ok": theme.OK, "missing": theme.BAD, "duplicate": theme.WARN, "empty": theme.TEXT_MUTED}


class PathList(QWidget):
    changed = Signal()

    def __init__(self, title: str, editable: bool, note: str = ""):
        super().__init__()
        self.parts: list[str] = []
        self.overrides: dict[str, str] = {}
        self.seen: set[str] = set()
        self.entries: list[envpath.PathEntry] = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        head = QLabel(title)
        head.setObjectName("CardTitle")
        layout.addWidget(head)
        if note:
            label = QLabel(note)
            label.setObjectName("Note")
            label.setWordWrap(True)
            layout.addWidget(label)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Thư mục", "Trạng thái"])
        self.tree.setRootIsDecorated(False)
        self.tree.setUniformRowHeights(True)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.tree, 1)
        row = QHBoxLayout()
        self.add_button = QPushButton("Thêm thư mục…")
        self.remove_button = QPushButton("Gỡ mục đã chọn")
        self.up_button = QPushButton("Lên")
        self.down_button = QPushButton("Xuống")
        self.clean_button = QPushButton("Bỏ mục hỏng và trùng")
        for button in (self.add_button, self.remove_button, self.up_button, self.down_button):
            row.addWidget(button)
        row.addStretch(1)
        row.addWidget(self.clean_button)
        layout.addLayout(row)
        for button in (self.add_button, self.remove_button, self.up_button, self.down_button, self.clean_button):
            button.setEnabled(editable)
        self.add_button.clicked.connect(self.add)
        self.remove_button.clicked.connect(self.remove)
        self.up_button.clicked.connect(lambda: self.move(-1))
        self.down_button.clicked.connect(lambda: self.move(1))
        self.clean_button.clicked.connect(self.clean)

    def set_parts(self, parts: list[str], overrides: dict[str, str] | None = None, seen: set[str] | None = None) -> None:
        self.parts = list(parts)
        if overrides is not None:
            self.overrides = overrides
        if seen is not None:
            self.seen = seen
        self.render()

    def render(self, select: int | None = None) -> None:
        self.entries = envpath.analyze(self.parts, self.overrides, self.seen)
        self.tree.clear()
        for entry in self.entries:
            item = QTreeWidgetItem([entry.raw.strip() or "(trống)", envpath.STATE_LABELS[entry.state]])
            item.setToolTip(0, entry.expanded)
            item.setForeground(1, QBrush(QColor(STATE_COLORS[entry.state])))
            self.tree.addTopLevelItem(item)
        if select is not None and 0 <= select < self.tree.topLevelItemCount():
            self.tree.setCurrentItem(self.tree.topLevelItem(select))
        self.changed.emit()

    @property
    def problems(self) -> int:
        return sum(1 for entry in self.entries if entry.problem)

    def _row(self) -> int:
        item = self.tree.currentItem()
        return self.tree.indexOfTopLevelItem(item) if item is not None else -1

    def add(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Chọn thư mục thêm vào PATH")
        if folder:
            self.parts.append(folder.replace("/", "\\"))
            self.render(len(self.parts) - 1)

    def remove(self) -> None:
        row = self._row()
        if row >= 0:
            del self.parts[row]
            self.render(min(row, len(self.parts) - 1))

    def move(self, step: int) -> None:
        row = self._row()
        target = row + step
        if row >= 0 and 0 <= target < len(self.parts):
            self.parts[row], self.parts[target] = self.parts[target], self.parts[row]
            self.render(target)

    def clean(self) -> None:
        self.parts = envpath.cleaned(self.parts, self.overrides, self.seen)
        self.render()


class PathDialog(QDialog):
    def __init__(self, app: AppContext, controller: RunController, parent: QWidget | None = None):
        super().__init__(parent)
        self.app = app
        self.controller = controller
        self.setWindowTitle("Sửa biến PATH")
        self.resize(860, 640)
        env = app.env
        self.keys = {envpath.MACHINE: registry.parse_key(envpath.KEYS[envpath.MACHINE]),
                     envpath.USER: env.resolve(envpath.KEYS[envpath.USER])}
        self.original = {scope: envpath.read(scope, key) for scope, key in self.keys.items()}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(12)
        intro = QLabel("PATH là danh sách thư mục Windows tìm chương trình khi gõ lệnh. Mục <b>Không tồn tại</b> (thư mục "
                       "đã bị xoá, phần mềm đã gỡ) và mục <b>Trùng</b> bỏ đi được an toàn. Lưu xong, chương trình mở sau đó "
                       "thấy PATH mới; cửa sổ cmd / PowerShell đang mở thì phải mở lại.")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        machine_note = "" if env.is_admin else "Cần mở tool bằng quyền admin để sửa PATH của cả máy."
        self.machine = PathList(envpath.LABELS[envpath.MACHINE] + " (mọi người dùng)", env.is_admin, machine_note)
        self.user = PathList(f"{envpath.LABELS[envpath.USER]} {env.target_user.short_name}", True)
        self.machine.set_parts(envpath.split(self.original[envpath.MACHINE]))
        self.user.set_parts(envpath.split(self.original[envpath.USER]),
                            envpath.user_overrides(env.target_user.profile_path or ""),
                            envpath.keys_of(self.machine.entries))
        self.machine.changed.connect(self._machine_changed)
        self.user.changed.connect(self._update_status)
        layout.addWidget(self.machine, 3)
        layout.addWidget(self.user, 2)
        bottom = QHBoxLayout()
        self.status = QLabel()
        self.status.setObjectName("PageSubtitle")
        self.status.setWordWrap(True)
        self.save_button = QPushButton("Lưu thay đổi")
        self.save_button.setObjectName("Primary")
        close = QPushButton("Đóng")
        bottom.addWidget(self.status, 1)
        bottom.addWidget(close)
        bottom.addWidget(self.save_button)
        layout.addLayout(bottom)
        close.clicked.connect(self.reject)
        self.save_button.clicked.connect(self.save)
        self._update_status()

    def _machine_changed(self) -> None:
        # Mục của người dùng trùng với PATH của máy thì cũng tính là trùng.
        self.user.seen = envpath.keys_of(self.machine.entries)
        self.user.render()

    def changes(self) -> dict[str, str]:
        """Phạm vi có thay đổi → giá trị PATH mới."""
        result = {}
        for scope, widget in ((envpath.MACHINE, self.machine), (envpath.USER, self.user)):
            value = envpath.join(widget.parts)
            if value != envpath.join(envpath.split(self.original[scope])):
                result[scope] = value
        return result

    def _update_status(self) -> None:
        problems = self.machine.problems + self.user.problems
        parts = [f"{problems} mục hỏng / trùng" if problems else "Không có mục hỏng hay trùng"]
        length = len(envpath.join(self.machine.parts))
        if length > envpath.LONG_PATH:
            parts.append(f"PATH của máy dài {length} ký tự (quá {envpath.LONG_PATH + 1}, chương trình cũ có thể đọc thiếu)")
        changed = self.changes()
        parts.append(f"{len(changed)} phạm vi đã đổi, chưa lưu" if changed else "chưa đổi gì")
        self.status.setText(" · ".join(parts))
        self.save_button.setEnabled(bool(changed) and not self.controller.busy)

    def save(self) -> None:
        changed = self.changes()
        if not changed:
            return
        lines = []
        for scope, value in changed.items():
            before, after = envpath.split(self.original[scope]), envpath.split(value)
            removed = [part for part in before if part.strip() and part not in after]
            added = [part for part in after if part not in before]
            lines.append(f"{envpath.LABELS[scope]}: bỏ {len(removed)} mục, thêm {len(added)} mục"
                         + (f"\n  bỏ: {', '.join(removed[:5])}" + ("…" if len(removed) > 5 else "") if removed else ""))
        answer = QMessageBox.question(self, "Lưu PATH", "\n".join(lines) + "\n\nGiá trị cũ được sao lưu, hoàn tác ở trang "
                                                                         "Nhật ký. Lưu?")
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.controller.run([envpath.action(scope, value) for scope, value in changed.items()])
        self.accept()
