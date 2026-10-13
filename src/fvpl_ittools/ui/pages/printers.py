"""Trang Máy in: danh sách máy in trên máy (gỡ, in thử, mở hàng đợi), thêm máy in qua IP / share, sửa lỗi."""

from __future__ import annotations

import logging
import os
import subprocess
import threading

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...app import AppContext
from ...core import shell
from ...core.executor import BatchResult
from ...printers import inf, manage
from ..controller import RunController
from ..widgets import page_header
from .actions_page import ActionsPage

log = logging.getLogger(__name__)
PRINTER_ROLE = Qt.ItemDataRole.UserRole
INF_ROLE = Qt.ItemDataRole.UserRole          # file .inf của driver chọn từ file, "" với driver có sẵn
NAME_ROLE = Qt.ItemDataRole.UserRole + 1     # tên driver thật (chữ hiện có thể kèm ghi chú)


class SnapshotLoader(QObject):
    done = Signal(int, object)  # lượt, manage.Snapshot hoặc chuỗi lỗi

    def __init__(self, app: AppContext, parent: QObject | None = None):
        super().__init__(parent)
        self.app = app
        self.generation = 0
        self._cancel = threading.Event()

    def start(self) -> None:
        self._cancel.set()
        self._cancel = threading.Event()
        self.generation += 1
        threading.Thread(target=self._work, args=(self.generation, self._cancel), name="printers", daemon=True).start()

    def stop(self) -> None:
        self._cancel.set()

    def _work(self, generation: int, cancel: threading.Event) -> None:
        try:
            result: object = manage.snapshot(self.app.env, cancel)
        except manage.PrinterError as exc:
            result = str(exc)
        except Exception:
            log.exception("Lỗi khi đọc danh sách máy in")
            result = "Lỗi không mong muốn, xem file log"
        if not cancel.is_set():
            self.done.emit(generation, result)


class PrinterListPanel(QWidget):
    def __init__(self, app: AppContext, controller: RunController, loader: SnapshotLoader):
        super().__init__()
        self.app = app
        self.controller = controller
        self.loader = loader
        self.printers: list[manage.Printer] = []
        self.loading = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(10)
        note = QLabel("Máy in trên máy này, kể cả máy in share của người đang đăng nhập. Máy in lỗi thì gỡ đi "
                      "rồi thêm lại ở tab Thêm máy in. Dòng in đậm là máy in mặc định của người dùng.")
        note.setObjectName("PageSubtitle")
        note.setWordWrap(True)
        layout.addWidget(note)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Máy in", "Loại", "Địa chỉ / cổng", "Driver", "Trạng thái", "Lệnh chờ"])
        self.tree.setRootIsDecorated(False)
        self.tree.setUniformRowHeights(True)
        header = self.tree.header()
        header.setStretchLastSection(False)  # chỗ trống dành cho tên máy in, không cho cột Lệnh chờ
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in range(1, 6):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.tree, 1)

        self.status = QLabel()
        self.status.setObjectName("SectionLabel")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        buttons = QHBoxLayout()
        self.refresh_button = QPushButton("Làm mới")
        self.test_button = QPushButton("In trang thử")
        self.queue_button = QPushButton("Mở hàng đợi")
        self.driver_checkbox = QCheckBox("Gỡ cả driver")
        self.driver_checkbox.setToolTip("Chỉ gỡ khi không máy in nào khác dùng driver đó. Dùng khi driver hỏng, "
                                        "định cài lại driver mới.")
        self.remove_button = QPushButton("Gỡ máy in")
        buttons.addWidget(self.refresh_button)
        buttons.addStretch(1)
        buttons.addWidget(self.test_button)
        buttons.addWidget(self.queue_button)
        buttons.addSpacing(12)
        buttons.addWidget(self.driver_checkbox)
        buttons.addWidget(self.remove_button)
        layout.addLayout(buttons)

        self.refresh_button.clicked.connect(self.refresh)
        self.test_button.clicked.connect(self.test_page)
        self.queue_button.clicked.connect(self.open_queue)
        self.remove_button.clicked.connect(self.remove)
        self.tree.itemSelectionChanged.connect(self._update_buttons)
        controller.busy_changed.connect(lambda _busy: self._update_buttons())
        self._update_buttons()

    def refresh(self) -> None:
        self.loading = True
        self.status.setText("Đang đọc danh sách máy in…")
        self._update_buttons()
        self.loader.start()

    def show_snapshot(self, result: object) -> None:
        self.loading = False
        self.tree.clear()
        if isinstance(result, str):
            self.printers = []
            self.status.setText(f"Không đọc được danh sách máy in: {result}")
            self._update_buttons()
            return
        self.printers = list(result.printers)
        bold = QFont()
        bold.setBold(True)
        for index, printer in enumerate(self.printers):
            name = printer.name + (f"   (đang share: {printer.share_name})" if printer.share_name else "")
            item = QTreeWidgetItem(self.tree, [name, printer.label, printer.where, printer.driver, printer.status,
                                               str(printer.jobs) if printer.jobs else ""])
            item.setData(0, PRINTER_ROLE, index)
            item.setToolTip(0, printer.name)
            item.setToolTip(2, printer.port)
            if printer.default:
                for column in range(6):
                    item.setFont(column, bold)
            if printer.problem or printer.jobs:
                item.setForeground(4, QBrush(QColor("#b45309")))
        parts = [f"{len(self.printers)} máy in"]
        if result.spooler and result.spooler != "Running":
            parts.append(f"Print Spooler đang {result.spooler}: chạy mục Khởi động lại Print Spooler ở tab Sửa lỗi")
        if result.error:
            parts.append(f"đọc thiếu: {result.error}")
        self.status.setText(" · ".join(parts))
        self._update_buttons()

    def selected(self) -> manage.Printer | None:
        items = self.tree.selectedItems()
        return self.printers[items[0].data(0, PRINTER_ROLE)] if items else None

    def test_page(self) -> None:
        printer = self.selected()
        if printer is not None:
            self.controller.run([manage.test_page_action(printer)])

    def open_queue(self) -> None:
        printer = self.selected()
        if printer is None:
            return
        rundll = os.path.join(shell.system_dir(), "rundll32.exe")
        subprocess.Popen([rundll, "printui.dll,PrintUIEntry", "/o", "/n", printer.name])

    def remove(self) -> None:
        printer = self.selected()
        if printer is None:
            return
        remove_driver = self.driver_checkbox.isChecked() and printer.kind != manage.KIND_USER and bool(printer.driver)
        lines = [f"Gỡ máy in “{printer.name}” ({printer.label})?"]
        if printer.kind == manage.KIND_MACHINE:
            lines.append("Máy in share của cả máy: mọi người dùng trên máy đều mất máy in này.")
        if printer.kind == manage.KIND_USER:
            lines.append(f"Máy in của {self.app.env.target_user.short_name}: tool gỡ bằng một tác vụ chạy dưới tên "
                         "người đó, người đó phải đang đăng nhập.")
        if remove_driver:
            lines.append(f"Gỡ cả driver “{printer.driver}” nếu không máy in nào khác dùng.")
        if printer.share_name:
            lines.append(f"Máy này đang share máy in này ({printer.share_name}): máy khác in qua nó sẽ hết in được.")
        answer = QMessageBox.question(self, "Gỡ máy in", "\n\n".join(lines))
        if answer == QMessageBox.StandardButton.Yes:
            self.controller.run([manage.remove_action(printer, remove_driver)])

    def _update_buttons(self) -> None:
        printer = self.selected()
        busy = self.controller.busy
        visible = printer is not None and printer.kind != manage.KIND_USER  # máy in tài khoản tool nhìn thấy
        self.refresh_button.setEnabled(not self.loading)
        self.test_button.setEnabled(not busy and visible)
        self.queue_button.setEnabled(visible)
        self.remove_button.setEnabled(not busy and printer is not None and self.app.env.is_admin)
        self.remove_button.setToolTip("" if self.app.env.is_admin else "Cần mở tool bằng quyền admin")
        self.driver_checkbox.setEnabled(printer is not None and printer.kind != manage.KIND_USER)


class AddPrinterPanel(QWidget):
    def __init__(self, app: AppContext, controller: RunController):
        super().__init__()
        self.app = app
        self.controller = controller
        self.installed: list[str] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(12)
        note = QLabel("Máy in thêm ở đây dùng được cho mọi người dùng trên máy. Tool cài driver bằng quyền admin, "
                      "nên người dùng thường không bị chặn vì không được cài driver (lỗi 0x00000bcb). "
                      "Kết quả hiện ở khung log bên dưới.")
        note.setObjectName("PageSubtitle")
        note.setWordWrap(True)
        layout.addWidget(note)

        # ---- máy in mạng qua IP
        ip_card, ip_form = self._card("Máy in mạng (IP)")
        self.address = QLineEdit()
        self.address.setPlaceholderText("Ví dụ 192.168.1.50")
        self.printer_name = QLineEdit()
        self.printer_name.setPlaceholderText("Để trống thì đặt là “Máy in <IP>”")
        self.driver = QComboBox()
        self.driver.setMinimumWidth(320)
        self.inf_button = QPushButton("Driver từ file .inf…")
        self.inf_button.setToolTip("Chọn file .inf trong bộ driver của hãng (đã giải nén), ví dụ trong "
                                   "kho bộ cài: Drivers\\Printers\\<hãng>")
        self.add_ip_button = QPushButton("Thêm máy in")
        self.add_ip_button.setObjectName("Primary")
        driver_row = QHBoxLayout()
        driver_row.addWidget(self.driver, 1)
        driver_row.addWidget(self.inf_button)
        ip_form.addWidget(QLabel("Địa chỉ IP"), 1, 0)
        ip_form.addWidget(self.address, 1, 1)
        ip_form.addWidget(QLabel("Tên máy in"), 2, 0)
        ip_form.addWidget(self.printer_name, 2, 1)
        ip_form.addWidget(QLabel("Driver"), 3, 0)
        ip_form.addLayout(driver_row, 3, 1)
        ip_form.addWidget(self.add_ip_button, 4, 1, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(ip_card)

        # ---- máy in share
        share_card, share_form = self._card("Máy in share từ máy khác")
        self.share_path = QLineEdit()
        self.share_path.setPlaceholderText("\\\\TEN-MAY\\Ten may in")
        self.per_machine = QCheckBox("Cho mọi người dùng trên máy này")
        self.per_machine.setChecked(app.runs_as_other_user)
        self.per_machine.setToolTip(
            "Thêm máy in cho cả máy (printui /ga): ai đăng nhập cũng thấy, người dùng không tự xoá được. "
            "Nên bật khi mở tool bằng tài khoản IT, vì kết nối thường chỉ là của tài khoản chạy tool.")
        self.add_share_button = QPushButton("Kết nối")
        self.add_share_button.setObjectName("Primary")
        share_form.addWidget(QLabel("Đường dẫn"), 1, 0)
        share_form.addWidget(self.share_path, 1, 1)
        share_form.addWidget(self.per_machine, 2, 1)
        share_form.addWidget(self.add_share_button, 3, 1, alignment=Qt.AlignmentFlag.AlignLeft)
        hint = QLabel("Lỗi 0x0000011b, 0x00000709, 0x0000007c khi kết nối giữa Win11 và Win10: xem tab Sửa lỗi, "
                      "nhóm “Share máy in Win11 ↔ Win10”.")
        hint.setObjectName("PageSubtitle")
        hint.setWordWrap(True)
        share_form.addWidget(hint, 4, 1)
        layout.addWidget(share_card)

        self.error = QLabel()
        self.error.setObjectName("Note")
        self.error.setWordWrap(True)
        layout.addWidget(self.error)
        layout.addStretch(1)

        self.inf_button.clicked.connect(self.pick_inf)
        self.add_ip_button.clicked.connect(self.add_ip)
        self.add_share_button.clicked.connect(self.add_share)
        self.share_path.returnPressed.connect(self.add_share)
        controller.busy_changed.connect(lambda _busy: self._update_buttons())
        self.set_drivers([])

    @staticmethod
    def _card(title: str) -> tuple[QFrame, QGridLayout]:
        card = QFrame()
        card.setObjectName("Card")
        form = QGridLayout(card)
        form.setContentsMargins(16, 14, 16, 14)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(10)
        label = QLabel(title)
        label.setObjectName("CardTitle")
        form.addWidget(label, 0, 0, 1, 2)
        form.setColumnStretch(1, 1)
        return card, form

    def set_drivers(self, installed: list[str]) -> None:
        """Danh sách driver: đã cài trên máy, rồi driver có sẵn trong Windows, giữ lại driver chọn từ file .inf."""
        self.installed = list(installed)
        current = self.driver.currentText()
        extra = [(self.driver.itemText(index), self.driver.itemData(index, INF_ROLE),
                  self.driver.itemData(index, NAME_ROLE))
                 for index in range(self.driver.count()) if self.driver.itemData(index, INF_ROLE)]
        self.driver.clear()
        self.driver.addItem("— Chọn driver —")
        for text, path, name in extra:
            self._add_driver(text, name, path)
        for name, have in manage.driver_choices(self.installed):
            self._add_driver(name if have else f"{name}  (có sẵn trong Windows)", name, "")
        found = self.driver.findText(current)
        self.driver.setCurrentIndex(max(found, 0))
        self._update_buttons()

    def _add_driver(self, text: str, name: str, inf_path: str, index: int | None = None) -> None:
        index = self.driver.count() if index is None else index
        self.driver.insertItem(index, text)
        self.driver.setItemData(index, inf_path, INF_ROLE)
        self.driver.setItemData(index, name, NAME_ROLE)

    def selected_driver(self) -> tuple[str, str] | None:
        """(tên driver, file .inf hoặc "") đang chọn."""
        index = self.driver.currentIndex()
        if index <= 0:
            return None
        return str(self.driver.itemData(index, NAME_ROLE)), str(self.driver.itemData(index, INF_ROLE) or "")

    def _inf_start_dir(self) -> str:
        root = self.app.software.root
        for candidate in (os.path.join(root, "Drivers", "Printers"), os.path.join(root, "Drivers"), root):
            if root and os.path.isdir(candidate):
                return candidate
        return ""

    def pick_inf(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Chọn file .inf của driver máy in", self._inf_start_dir(),
                                              "Driver máy in (*.inf)")
        if path:
            self.use_inf(os.path.normpath(path))

    def use_inf(self, path: str) -> None:
        try:
            models = inf.inf_models(path)
        except inf.InfError as exc:
            QMessageBox.warning(self, "Không dùng được file này", str(exc))
            return
        model = models[0]
        if len(models) > 1:
            model, ok = QInputDialog.getItem(self, "Chọn model", "File .inf có nhiều model, chọn đúng model máy in:",
                                             models, 0, False)
            if not ok:
                return
        text = f"{model}  (từ {os.path.basename(path)})"
        index = self.driver.findText(text)
        if index < 0:
            index = 1
            self._add_driver(text, model, path, index)
        self.driver.setCurrentIndex(index)

    def add_ip(self) -> None:
        address = self.address.text().strip()
        name = self.printer_name.text().strip() or f"Máy in {address}"
        driver = self.selected_driver()
        if not manage.valid_address(address):
            self.error.setText("Nhập IP hoặc tên của máy in (chữ không dấu, số, dấu chấm, gạch ngang).")
            return
        if not manage.valid_printer_name(name):
            self.error.setText("Tên máy in không được có các ký tự \\ , ! \" và không quá 200 ký tự.")
            return
        if driver is None:
            self.error.setText("Chọn driver, hoặc bấm “Driver từ file .inf…” để lấy driver của hãng.")
            return
        self.error.setText("")
        self.controller.run([manage.add_ip_action(address, name, driver[0], driver[1])])

    def add_share(self) -> None:
        path = manage.normalize_share(self.share_path.text())
        if path is None:
            self.error.setText("Nhập đường dẫn dạng \\\\TEN-MAY\\Ten may in (tên máy không dấu).")
            return
        self.error.setText("")
        self.share_path.setText(path)
        self.controller.run([manage.add_share_action(path, self.per_machine.isChecked())])

    def _update_buttons(self) -> None:
        busy = self.controller.busy
        allowed = self.app.env.is_admin
        for button in (self.add_ip_button, self.add_share_button):
            button.setEnabled(not busy and allowed)
            button.setToolTip("" if allowed else "Cần mở tool bằng quyền admin")


class PrintersPage(QWidget):
    def __init__(self, app: AppContext, controller: RunController):
        super().__init__()
        self._started = False
        self.loader = SnapshotLoader(app, self)
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 12)
        root.setSpacing(10)
        page_header(root, "Máy in", "Xem, thêm, gỡ máy in và sửa lỗi in, lỗi share máy in giữa Win11 và Win10.")
        self.tabs = QTabWidget()
        self.list = PrinterListPanel(app, controller, self.loader)
        self.add = AddPrinterPanel(app, controller)
        self.fixes = ActionsPage("printers", "", "", "Chưa có mục sửa lỗi máy in nào.", app, controller,
                                 packs=app.packs, show_header=False)
        self.tabs.addTab(self.list, "Máy in trên máy")
        self.tabs.addTab(self.add, "Thêm máy in")
        self.tabs.addTab(self.fixes, "Sửa lỗi")
        root.addWidget(self.tabs, 1)
        self.loader.done.connect(self._loaded)
        controller.finished.connect(self._run_finished)

    @property
    def loading(self) -> bool:
        return self.list.loading

    def _loaded(self, generation: int, result: object) -> None:
        if generation != self.loader.generation:
            return
        self.list.show_snapshot(result)
        if isinstance(result, manage.Snapshot):
            self.add.set_drivers(result.drivers)

    def _run_finished(self, result: object) -> None:
        # Thêm / gỡ máy in, xoá lệnh in, đổi Spooler: đọc lại danh sách.
        if self._started and isinstance(result, BatchResult) and any(
                item.action.id.startswith("prn.") for item in result.results):
            self.list.refresh()

    def showEvent(self, event) -> None:
        if not self._started:
            self._started = True
            self.list.refresh()
        super().showEvent(event)

    def stop(self) -> None:
        self.loader.stop()
