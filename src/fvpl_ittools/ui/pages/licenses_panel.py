"""Tab "Key bản quyền" ở trang Tiện ích: lưu key Windows / Office vào một file, kích hoạt máy bằng key đã lưu
(core/licenses.py)."""

from __future__ import annotations

import html
import shutil
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QFont, QGuiApplication
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...app import AppContext
from ...core import licenses, paths, prefs
from ...core.executor import BatchResult, Level, Status
from ..components.progress_panel import ProgressPanel
from ..controller import RunController
from ..theme import BAD, OK, TEXT_MUTED
from ..widgets import Worker, open_path

ID_ROLE = Qt.ItemDataRole.UserRole


class KeyDialog(QDialog):
    """Thêm key (dán một hoặc nhiều key cho cùng một sản phẩm) hoặc sửa tên sản phẩm / loại / ghi chú."""

    def __init__(self, products: list[str], parent=None, key: licenses.LicenseKey | None = None):
        super().__init__(parent)
        self.editing = key
        self.setWindowTitle("Sửa key" if key else "Thêm key bản quyền")
        self.setMinimumWidth(520)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.product = QComboBox()
        self.product.setEditable(True)
        self.product.addItems(list(dict.fromkeys([*products, *licenses.PRODUCTS])))
        self.product.setCurrentText(key.product if key else "")
        self.product.lineEdit().setPlaceholderText("Ví dụ Office 2016 Standard, Windows 10/11 Pro")
        form.addRow("Sản phẩm:", self.product)
        if key is None:
            self.keys = QPlainTextEdit()
            self.keys.setPlaceholderText("Dán key vào đây, mỗi dòng một key (XXXXX-XXXXX-XXXXX-XXXXX-XXXXX).\n"
                                         "Dán cả đoạn chữ có lẫn key cũng được: tool tự lọc ra key.")
            self.keys.setFixedHeight(110)
            self.keys.textChanged.connect(self._count)
            form.addRow("Key:", self.keys)
            self.count = QLabel("Chưa có key nào")
            self.count.setObjectName("PageSubtitle")
            form.addRow("", self.count)
        else:
            form.addRow("Key:", QLabel(key.masked))
        self.type = QComboBox()
        self.type.addItems(list(licenses.TYPES))
        if key is not None:
            self.type.setCurrentText(key.type)
        form.addRow("Loại:", self.type)
        self.note = QLineEdit(key.note if key else "")
        self.note.setPlaceholderText("Ví dụ: hợp đồng 2024, 50 lượt, cho phòng Kế toán")
        form.addRow("Ghi chú:", self.note)
        layout.addLayout(form)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self._count()

    def found_keys(self) -> list[str]:
        return licenses.keys_in_text(self.keys.toPlainText()) if self.editing is None else []

    def _count(self) -> None:
        ok = bool(self.product.currentText().strip())
        if self.editing is None:
            count = len(self.found_keys())
            self.count.setText(f"Nhận được {count} key" if count else "Chưa có key nào đúng dạng")
            ok = ok and count > 0
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(ok)


class LicensesPanel(QWidget):
    def __init__(self, app: AppContext, controller: RunController):
        super().__init__()
        self.app = app
        self.controller = controller
        self.path = licenses.default_path(str(prefs.get(licenses.PREF) or ""), paths.portable_root(),
                                          paths.state_dir())
        self.keys: list[licenses.LicenseKey] = []
        self.loading = False
        self.error = ""
        self._started = False
        self._running: str = ""  # id key đang kích hoạt
        self.worker = Worker(self)
        self.worker.done.connect(self._loaded)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 12, 12, 8)
        layout.setSpacing(12)

        card = QFrame()
        card.setObjectName("Card")
        box = QVBoxLayout(card)
        box.setContentsMargins(16, 14, 16, 14)
        box.setSpacing(8)
        title = QLabel("File key")
        title.setObjectName("CardTitle")
        box.addWidget(title)
        note = QLabel("Mọi key nằm trong một file. Mang sang USB / máy khác: chép file này (hoặc bấm Lưu bản sao), rồi "
                      "bấm Mở file khác. File có key bản quyền của công ty: chỉ để trên USB / share của IT, không gửi qua "
                      "Zalo / email. Key không bao giờ được ghi ra log.")
        note.setObjectName("PageSubtitle")
        note.setWordWrap(True)
        box.addWidget(note)
        row = QHBoxLayout()
        self.file_label = QLabel()
        self.file_label.setWordWrap(True)
        self.file_label.setTextFormat(Qt.TextFormat.RichText)
        self.open_file_button = QPushButton("Mở file khác…")
        self.open_file_button.clicked.connect(self.choose_file)
        self.copy_file_button = QPushButton("Lưu bản sao…")
        self.copy_file_button.clicked.connect(self.save_copy)
        self.folder_button = QPushButton("Mở thư mục")
        self.folder_button.clicked.connect(lambda: open_path(self.path.parent))
        row.addWidget(self.file_label, 1)
        row.addWidget(self.open_file_button)
        row.addWidget(self.copy_file_button)
        row.addWidget(self.folder_button)
        box.addLayout(row)
        layout.addWidget(card)

        card = QFrame()
        card.setObjectName("Card")
        box = QVBoxLayout(card)
        box.setContentsMargins(16, 14, 16, 14)
        box.setSpacing(8)
        title = QLabel("Key theo sản phẩm")
        title.setObjectName("CardTitle")
        box.addWidget(title)
        row = QHBoxLayout()
        self.machine_label = QLabel(f"Máy này: <b>{html.escape(app.machine.os_label)}</b>")
        self.machine_label.setTextFormat(Qt.TextFormat.RichText)
        self.status_button = QPushButton("Xem trạng thái kích hoạt")
        self.status_button.clicked.connect(self.show_status)
        row.addWidget(self.machine_label, 1)
        row.addWidget(self.status_button)
        box.addLayout(row)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Sản phẩm / key", "Loại", "Đã dùng", "Ghi chú"])
        self.tree.setUniformRowHeights(True)
        self.tree.setMinimumHeight(260)
        header = self.tree.header()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.tree.setColumnWidth(0, 300)
        self.tree.itemSelectionChanged.connect(self._update_buttons)
        self.tree.itemDoubleClicked.connect(lambda item, _column: self.edit_key() if item.data(0, ID_ROLE) else None)
        box.addWidget(self.tree)
        row = QHBoxLayout()
        self.add_button = QPushButton("Thêm key…")
        self.add_button.clicked.connect(self.add_key)
        self.edit_button = QPushButton("Sửa…")
        self.edit_button.clicked.connect(self.edit_key)
        self.delete_button = QPushButton("Xoá")
        self.delete_button.clicked.connect(self.delete_key)
        self.show_keys = QCheckBox("Hiện key")
        self.show_keys.toggled.connect(lambda _on: self._populate())
        self.copy_button = QPushButton("Copy key")
        self.copy_button.clicked.connect(self.copy_key)
        self.activate_button = QPushButton("Kích hoạt máy này bằng key đã chọn")
        self.activate_button.setObjectName("Primary")
        self.activate_button.clicked.connect(self.activate)
        for widget in (self.add_button, self.edit_button, self.delete_button, self.show_keys, self.copy_button):
            row.addWidget(widget)
        row.addStretch(1)
        row.addWidget(self.activate_button)
        box.addLayout(row)
        self.hint = QLabel()
        self.hint.setObjectName("PageSubtitle")
        self.hint.setWordWrap(True)
        box.addWidget(self.hint)
        layout.addWidget(card)

        self.progress = ProgressPanel(controller)
        self.progress.setMinimumHeight(200)
        self.progress.hide()
        self.progress.dismissed.connect(self.progress.hide)
        self.progress.completed.connect(self._activated)
        layout.addWidget(self.progress)
        layout.addStretch(1)

        controller.busy_changed.connect(lambda _busy: self._update_buttons())
        self._show_file()
        self._update_buttons()

    # ------------------------------------------------------------ file

    def showEvent(self, event) -> None:
        if not self._started:
            self._started = True
            self.reload()
        super().showEvent(event)

    def reload(self) -> None:
        self.loading = True
        self._update_buttons()
        path = self.path
        self.worker.run("load", lambda: licenses.load(path))

    def _loaded(self, _name: str, result: object) -> None:
        self.loading = False
        if isinstance(result, Exception):
            self.error = str(result)
            self.keys = []
        else:
            self.error = ""
            self.keys = list(result)
        self._show_file()
        self._populate()

    def _show_file(self) -> None:
        where = html.escape(str(self.path))
        if self.loading:
            text = f"Đang đọc <b>{where}</b>…"
        elif self.error:
            text = f"<span style='color:{BAD}'>{html.escape(self.error)}</span>"
        elif not self.path.exists():
            text = f"Chưa có file: <b>{where}</b> (tạo khi thêm key đầu tiên)"
        else:
            text = f"<b>{where}</b> · {len(self.keys)} key"
        self.file_label.setText(text)

    def _write(self, keys: list[licenses.LicenseKey]) -> bool:
        try:
            licenses.save(self.path, keys)
        except licenses.LicenseError as exc:
            QMessageBox.warning(self, "Không ghi được", str(exc))
            return False
        self.keys = keys
        self.error = ""
        self._show_file()
        self._populate()
        return True

    def _fresh_keys(self) -> list[licenses.LicenseKey] | None:
        """Đọc lại file ngay trước khi sửa (file trên share có thể vừa được IT khác sửa)."""
        try:
            return licenses.load(self.path)
        except licenses.LicenseError as exc:
            QMessageBox.warning(self, "Không đọc được", f"{exc}\n\nSửa file hoặc bấm Mở file khác.")
            return None

    def choose_file(self) -> None:
        file, _ = QFileDialog.getOpenFileName(self, "Mở file key bản quyền", str(self.path.parent),
                                              "File key (*.json);;Tất cả (*.*)")
        if not file:
            return
        self.path = Path(file)
        try:
            prefs.put(licenses.PREF, str(self.path))
        except OSError:
            pass
        self.reload()

    def save_copy(self) -> None:
        file, _ = QFileDialog.getSaveFileName(self, "Lưu bản sao file key", licenses.FILE_NAME, "File key (*.json)")
        if not file:
            return
        try:
            shutil.copyfile(self.path, file)
        except OSError as exc:
            QMessageBox.warning(self, "Không chép được", str(exc))
            return
        self.controller.say(Level.INFO, f"Đã chép file key sang {file}")

    # ------------------------------------------------------------ danh sách

    def _populate(self) -> None:
        selected = self.selected_key()
        selected_id = selected.id if selected else ""
        suggested = {key.id for key in licenses.suggested(self.keys, self.app.machine.os_name)}
        self.tree.clear()
        groups: dict[str, QTreeWidgetItem] = {}
        bold = QFont()
        bold.setBold(True)
        for key in sorted(self.keys, key=lambda key: (key.kind, key.product.lower())):
            group = groups.get(key.product)
            if group is None:
                group = QTreeWidgetItem([key.product, "", "", ""])
                group.setFont(0, bold)
                group.setFlags(group.flags() & ~Qt.ItemFlag.ItemIsSelectable)
                self.tree.addTopLevelItem(group)
                groups[key.product] = group
            shown = key.key if self.show_keys.isChecked() else key.masked
            note = key.note + (" · hợp với máy này" if key.id in suggested else "")
            item = QTreeWidgetItem([shown, key.type, key.used_text, note.strip(" ·")])
            item.setData(0, ID_ROLE, key.id)
            if key.used and not key.used[-1].ok:
                item.setForeground(2, QBrush(QColor(BAD)))
            elif key.activations:
                item.setForeground(2, QBrush(QColor(OK)))
            else:
                item.setForeground(2, QBrush(QColor(TEXT_MUTED)))
            group.addChild(item)
            if key.id == selected_id:
                item.setSelected(True)
        for group in groups.values():
            group.setText(2, f"{group.childCount()} key")
        self.tree.expandAll()
        self._update_buttons()

    def selected_key(self) -> licenses.LicenseKey | None:
        items = self.tree.selectedItems()
        key_id = items[0].data(0, ID_ROLE) if items else None
        return next((key for key in self.keys if key.id == key_id), None)

    def select(self, key_id: str) -> None:
        for index in range(self.tree.topLevelItemCount()):
            group = self.tree.topLevelItem(index)
            for child in range(group.childCount()):
                item = group.child(child)
                item.setSelected(item.data(0, ID_ROLE) == key_id)

    def add_key(self) -> None:
        dialog = KeyDialog(sorted({key.product for key in self.keys}), self)
        if not self.ask(dialog):
            return
        keys = self._fresh_keys()
        if keys is None:
            return
        found = dialog.found_keys()
        keys, skipped = licenses.add_keys(keys, dialog.product.currentText(), found, dialog.type.currentText(),
                                          dialog.note.text())
        if self._write(keys):
            added = len(found) - len(skipped)
            self.controller.say(Level.OK, f"Đã thêm {added} key {dialog.product.currentText().strip()} vào {self.path}")
            if skipped:
                QMessageBox.information(self, "Key đã có", f"{len(skipped)} key đã có trong file nên bỏ qua.")

    def edit_key(self) -> None:
        key = self.selected_key()
        if key is None:
            return
        dialog = KeyDialog(sorted({item.product for item in self.keys}), self, key)
        if not self.ask(dialog):
            return
        keys = self._fresh_keys()
        if keys is None:
            return
        for item in keys:
            if item.id == key.id:
                item.product = dialog.product.currentText().strip()
                item.type = dialog.type.currentText()
                item.note = dialog.note.text().strip()
        self._write(keys)

    def delete_key(self) -> None:
        key = self.selected_key()
        if key is None:
            return
        answer = QMessageBox.question(self, "Xoá key", f"Xoá key {key.masked} ({key.product}) khỏi file?\n\n"
                                                       "Không xoá gì trên máy đã kích hoạt bằng key này.")
        if answer != QMessageBox.StandardButton.Yes:
            return
        keys = self._fresh_keys()
        if keys is not None:
            self._write([item for item in keys if item.id != key.id])

    def copy_key(self) -> None:
        key = self.selected_key()
        if key is not None:
            QGuiApplication.clipboard().setText(key.key)
            self.controller.say(Level.INFO, f"Đã copy key …{key.key[-5:]} ({key.product})")

    def ask(self, dialog: QDialog) -> bool:
        return dialog.exec() == QDialog.DialogCode.Accepted

    # ------------------------------------------------------------ kích hoạt

    def activate(self) -> None:
        key = self.selected_key()
        if key is None:
            return
        machine = self.app.machine
        text = (f"Nhập key {key.masked} ({key.product}) vào máy {machine.computer_name} và kích hoạt qua Internet?\n\n"
                f"Máy này: {machine.os_label}.")
        if key.kind == "windows" and key.id not in {item.id for item in licenses.suggested(self.keys, machine.os_name)}:
            text += "\n\nKey này có thể không hợp với bản Windows của máy (Pro / Enterprise / Education)."
        if key.activations:
            text += f"\n\nKey đã kích hoạt {key.activations} máy: key MAK có giới hạn số máy."
        if not self.confirm(text):
            return
        self._running = key.id
        self.progress.watch(f"Kích hoạt {key.product}")
        self.progress.show()
        self.controller.run([licenses.activation_action(key)])

    def confirm(self, text: str) -> bool:
        return QMessageBox.question(self, "Kích hoạt", text) == QMessageBox.StandardButton.Yes

    def _activated(self, result: BatchResult) -> None:
        key_id, self._running = self._running, ""
        item = next((item for item in result.results if item.action.id == f"lic.activate_{key_id}"), None)
        if not key_id or item is None or item.status is Status.SKIPPED or item.status is Status.CANCELLED:
            return
        keys = self._fresh_keys()
        if keys is None:
            return
        ok = item.status is Status.OK
        if licenses.record_usage(keys, key_id, self.app.machine.computer_name, ok, "" if ok else item.message):
            self._write(keys)
            self.select(key_id)

    def show_status(self) -> None:
        self.progress.watch("Trạng thái kích hoạt")
        self.progress.show()
        self.controller.run([licenses.status_action()])

    def _update_buttons(self) -> None:
        busy = self.controller.busy
        key = self.selected_key()
        ready = not self.loading and not self.error
        self.add_button.setEnabled(ready)
        self.edit_button.setEnabled(ready and key is not None)
        self.delete_button.setEnabled(ready and key is not None)
        self.copy_button.setEnabled(key is not None)
        self.copy_file_button.setEnabled(self.path.exists())
        self.activate_button.setEnabled(not busy and key is not None)
        self.status_button.setEnabled(not busy)
        if not self.keys and ready:
            self.hint.setText("Chưa có key nào. Bấm Thêm key, dán các key của từng sản phẩm (mỗi bản có thể nhiều key).")
        elif not self.app.env.is_admin:
            self.hint.setText("Kích hoạt cần mở tool bằng quyền admin.")
        else:
            self.hint.setText("Chọn một key rồi bấm Kích hoạt. Tool ghi lại máy nào đã dùng key nào để biết key MAK "
                              "còn lượt hay không.")
