"""Trang Cài máy mới: wizard 8 bước (PLAN.md mục 5.2). Danh sách bước bên trái, nội dung từng bước bên phải.

Trạng thái wizard lưu ra file (newpc/state.py) để chạy tiếp sau khi khởi động lại. Các bước chạy lệnh đi qua
RunController như mọi mục khác; trang ghi kết quả bước khi lượt chạy do chính bước đó bấm kết thúc.
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, QSize, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QGuiApplication
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ... import __version__
from ...app import AppContext
from ...core import config, inventory, paths, sysinfo
from ...core.executor import BatchResult, Level, RunContext, Status
from ...newpc import naming, precheck, report, state as wizard_state, steps
from ...software import catalog as catalog_module
from ..controller import RunController
from ..credential_dialog import ask_credential
from ..widgets import open_as_user, open_path, page_header

log = logging.getLogger(__name__)

STATE_MARKS = {"ok": "✔", "warn": "⚠", "bad": "✖", "skip": "–"}
STATE_TEXT_COLORS = {"ok": "#15803d", "warn": "#b45309", "bad": "#b91c1c", "skip": "#7b8794"}
STEP_MARKS = {"ok": "✔", "failed": "✖", "skipped": "–", "": "○"}
STEP_COLORS = {"ok": "#15803d", "failed": "#b91c1c", "skipped": "#7b8794"}
STEP_KEYS = [key for key, _name in wizard_state.STEPS]
UPDATE_ACTIONS = ("drv.vendor_update", "wu.scan_install")  # bước 6, chạy lần lượt


# ---------------------------------------------------------------- bước 0: kiểm tra trước


class PrecheckLoader(QObject):
    done = Signal(int, object, str)  # lượt, Facts hoặc None, thông báo lỗi

    def __init__(self, app: AppContext, parent: QObject | None = None):
        super().__init__(parent)
        self.app = app
        self.generation = 0
        self._cancel = threading.Event()

    def start(self) -> None:
        self._cancel.set()
        self._cancel = threading.Event()
        self.generation += 1
        threading.Thread(target=self._work, args=(self.generation, self._cancel), name="precheck", daemon=True).start()

    def stop(self) -> None:
        self._cancel.set()

    def _work(self, generation: int, cancel: threading.Event) -> None:
        try:
            facts, error = precheck.collect(self.app, cancel), ""
        except Exception as exc:
            log.exception("Lỗi khi kiểm tra trước")
            facts, error = None, str(exc) or exc.__class__.__name__
        if not cancel.is_set():
            self.done.emit(generation, facts, error)


def _restyle(widget: QWidget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def _note(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("PageSubtitle")
    label.setWordWrap(True)
    label.setTextFormat(Qt.TextFormat.RichText)
    return label


class PrecheckPanel(QWidget):
    def __init__(self, app: AppContext, controller: RunController):
        super().__init__()
        self.app = app
        self.controller = controller
        self.checks: list[precheck.Check] = []
        self.loading = False
        self.loader = PrecheckLoader(app, self)
        self.loader.done.connect(self._checked)
        self._actions = {action.id: action for action in app.actions}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(_note("Kiểm tra máy trước khi đổi tên, join domain và cài phần mềm. Chỉ đọc, không đổi gì."))
        self.summary = QLabel("Đang kiểm tra…")
        self.summary.setObjectName("SummaryLine")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Kiểm tra", "Kết quả", "Cách xử lý"])
        self.tree.setRootIsDecorated(False)
        self.tree.setWordWrap(True)
        header = self.tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.tree, 1)

        buttons = QHBoxLayout()
        self.recheck_button = QPushButton("Kiểm tra lại")
        self.time_button = QPushButton("Đồng bộ giờ")
        self.time_button.setToolTip("Chạy mục Đồng bộ giờ ở trang Sửa lỗi rồi kiểm tra lại")
        self.copy_button = QPushButton("Copy kết quả")
        for button in (self.recheck_button, self.time_button, self.copy_button):
            buttons.addWidget(button)
        buttons.addStretch(1)
        layout.addLayout(buttons)

        self.recheck_button.clicked.connect(self.recheck)
        self.time_button.clicked.connect(self.sync_time)
        self.copy_button.clicked.connect(self.copy_text)
        controller.busy_changed.connect(lambda _busy: self._update_buttons())
        controller.finished.connect(self._run_finished)
        self._update_buttons()

    def recheck(self) -> None:
        self.loading = True
        self.summary.setText("Đang kiểm tra (mạng, DNS, DC, giờ, share…)")
        self.summary.setProperty("state", "muted")
        _restyle(self.summary)
        self._update_buttons()
        self.loader.start()

    def stop(self) -> None:
        self.loader.stop()

    def _checked(self, generation: int, facts: object, error: str) -> None:
        if generation != self.loader.generation:
            return
        self.loading = False
        if facts is None:
            self.checks = []
            self.summary.setText(f"Không kiểm tra được: {error}")
            self.summary.setProperty("state", "bad")
        else:
            self.checks = precheck.evaluate(facts)
            state, text = precheck.summary(self.checks)
            self.summary.setText(text)
            self.summary.setProperty("state", state)
        _restyle(self.summary)
        self.tree.clear()
        for check in self.checks:
            item = QTreeWidgetItem(self.tree, [f"{STATE_MARKS[check.state]}  {check.name}", check.detail, check.hint])
            color = QBrush(QColor(STATE_TEXT_COLORS[check.state]))
            item.setForeground(0, color)
            item.setForeground(1, color)
            for column in range(3):
                item.setToolTip(column, item.text(column))
        self._update_buttons()

    def sync_time(self) -> None:
        action = self._actions.get("dom.time_sync")
        if action is not None:
            self.controller.run([action])

    def _run_finished(self, result: object) -> None:
        if isinstance(result, BatchResult) and any(item.action.id == "dom.time_sync" for item in result.results) \
                and self.isVisible():
            self.recheck()

    def copy_text(self) -> None:
        QGuiApplication.clipboard().setText(precheck.to_text(self.checks, self.app.machine.computer_name))
        self.controller.say(Level.INFO, "Đã copy kết quả kiểm tra vào clipboard.")

    def _update_buttons(self) -> None:
        busy = self.controller.busy
        self.recheck_button.setEnabled(not self.loading and not busy)
        self.copy_button.setEnabled(bool(self.checks))
        needs_time = any(check.fix == "dom.time_sync" for check in self.checks)
        self.time_button.setEnabled(needs_time and not busy and "dom.time_sync" in self._actions)


# ---------------------------------------------------------------- bước 1: thông tin máy


class DepartmentDialog(QDialog):
    """Thêm mã phòng ban mới, lưu vào site.yaml."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Thêm mã phòng ban")
        self.setMinimumWidth(380)
        layout = QVBoxLayout(self)
        layout.addWidget(_note("Mã dùng trong tên máy, ví dụ KT trong FVPL-KT05. Chữ in hoa không dấu và số, "
                               "tối đa 6 ký tự. Lưu vào site.yaml để lần sau chọn lại được."))
        form = QFormLayout()
        self.code = QLineEdit()
        self.code.setMaxLength(6)
        self.code.setPlaceholderText("KT")
        self.name = QLineEdit()
        self.name.setPlaceholderText("Kế toán")
        form.addRow("Mã", self.code)
        form.addRow("Tên phòng", self.name)
        layout.addLayout(form)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Lưu")
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Huỷ")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.code.textChanged.connect(lambda text: self.code.setText(text.upper()) if text != text.upper() else None)
        self.code.textChanged.connect(self._update)
        self.name.textChanged.connect(self._update)
        self._update()

    def _update(self) -> None:
        ok = bool(config.DEPARTMENT_CODE.match(self.code.text().strip())) and bool(self.name.text().strip())
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(ok)


class Worker(QObject):
    """Chạy một hàm ở thread nền, trả kết quả (hoặc lỗi dạng chuỗi) qua signal."""
    done = Signal(str, object)  # tên việc, kết quả hoặc Exception

    def run(self, name: str, fn) -> None:
        def work() -> None:
            try:
                result = fn()
            except Exception as exc:
                if not isinstance(exc, (naming.NamingError, OSError)):
                    log.exception("Lỗi khi chạy %s", name)
                result = exc
            self.done.emit(name, result)
        threading.Thread(target=work, name=f"newpc-{name}", daemon=True).start()


@dataclass
class ReportResult:
    files: list[Path]


# ---------------------------------------------------------------- trang


class NewPcPage(QWidget):
    open_software = Signal(str)  # profile cần chọn sẵn ở trang Phần mềm

    def __init__(self, app: AppContext, controller: RunController):
        super().__init__()
        self.app = app
        self.controller = controller
        self._started = False
        self._pending: str | None = None              # bước đang chạy lệnh, ghi kết quả khi chạy xong
        self._credential: tuple[str, str] | None = None  # tài khoản join, chỉ giữ trong RAM tới khi join xong
        self._existing: list[str] | None = None       # tên máy trong AD vừa đọc
        self._actions = {action.id: action for action in app.actions}
        self._packs = {pack.id: pack for pack in app.packs}
        self.state = wizard_state.active()
        self.profiles: list[tuple[str, str]] = []
        self.worker = Worker(self)
        self.worker.done.connect(self._worker_done)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 12)
        root.setSpacing(10)
        page_header(root, "Cài máy mới",
                    "Làm lần lượt từ trên xuống: kiểm tra, đặt tên, join domain, cài phần mềm, cấu hình chuẩn, "
                    "báo cáo. Tool nhớ đang làm tới đâu, khởi động lại máy xong thì tự mở lại để làm tiếp.")
        banner = QHBoxLayout()
        self.banner = QLabel()
        self.banner.setObjectName("SummaryLine")
        self.banner.setWordWrap(True)
        self.reset_button = QPushButton("Huỷ / cài máy khác")
        self.reset_button.setToolTip("Xoá tiến độ wizard đang lưu (không hoàn tác những gì đã làm trên máy)")
        banner.addWidget(self.banner, 1)
        banner.addWidget(self.reset_button)
        root.addLayout(banner)

        body = QHBoxLayout()
        body.setSpacing(12)
        self.step_list = QListWidget()
        self.step_list.setFixedWidth(230)
        for key, name in wizard_state.STEPS:
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, key)
            item.setSizeHint(QSize(0, 32))
            self.step_list.addItem(item)
        self.stack = QStackedWidget()
        self.check = PrecheckPanel(app, controller)
        self.stack.addWidget(self._framed(self.check))
        self.stack.addWidget(self._framed(self._info_panel()))
        self.stack.addWidget(self._framed(self._join_panel()))
        self.stack.addWidget(self._framed(self._after_panel()))
        self.stack.addWidget(self._framed(self._software_panel()))
        self.stack.addWidget(self._framed(self._config_panel()))
        self.stack.addWidget(self._framed(self._update_panel()))
        self.stack.addWidget(self._framed(self._report_panel()))
        body.addWidget(self.step_list)
        body.addWidget(self.stack, 1)
        root.addLayout(body, 1)

        self.step_list.currentRowChanged.connect(self._step_changed)
        self.reset_button.clicked.connect(self.reset)
        controller.busy_changed.connect(lambda _busy: self._update_buttons())
        controller.finished.connect(self._run_finished)
        self._load_state_into_fields()
        self._refresh()
        self.step_list.setCurrentRow(STEP_KEYS.index(self.start_step()))

    # ------------------------------------------------------------ dựng các bước

    @staticmethod
    def _framed(panel: QWidget) -> QWidget:
        frame = QFrame()
        frame.setObjectName("Card")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.addWidget(panel)
        return frame

    @staticmethod
    def _panel(title: str) -> tuple[QWidget, QVBoxLayout]:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        label = QLabel(title)
        label.setObjectName("CardTitle")
        layout.addWidget(label)
        return panel, layout

    @staticmethod
    def _buttons(layout: QVBoxLayout, *buttons: QPushButton) -> None:
        row = QHBoxLayout()
        for button in buttons:
            row.addWidget(button)
        row.addStretch(1)
        layout.addLayout(row)

    def _skip_button(self, key: str) -> QPushButton:
        button = QPushButton("Bỏ qua bước này")
        button.clicked.connect(lambda: self.record(key, "skipped", "IT bỏ qua", advance=True))
        return button

    def _info_panel(self) -> QWidget:
        panel, layout = self._panel("1. Thông tin máy")
        layout.addWidget(_note("Tên máy theo quy ước <b>&lt;tiền tố&gt;&lt;mã phòng&gt;&lt;2 số&gt;</b>, ví dụ "
                               "FVPL-KT05. Bấm <b>Gợi ý tên</b> để tool hỏi AD các tên đã dùng và lấy số kế tiếp "
                               "(máy chưa vào domain thì hỏi tài khoản join)."))
        form = QGridLayout()
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(10)
        self.department = QComboBox()
        self.department.setMinimumWidth(220)
        self.add_department_button = QPushButton("Thêm mã phòng…")
        self.computer_name = QLineEdit()
        self.computer_name.setMaxLength(naming.NAME_MAX)
        self.suggest_button = QPushButton("Gợi ý tên")
        self.name_status = QLabel()
        self.name_status.setWordWrap(True)
        self.primary_user = QLineEdit()
        self.primary_user.setPlaceholderText("Người dùng chính của máy (ghi vào báo cáo), ví dụ Nguyễn Văn A")
        self.profile = QComboBox()
        self.profile.setMinimumWidth(220)
        form.addWidget(QLabel("Phòng ban"), 0, 0)
        form.addWidget(self.department, 0, 1)
        form.addWidget(self.add_department_button, 0, 2)
        form.addWidget(QLabel("Tên máy"), 1, 0)
        form.addWidget(self.computer_name, 1, 1)
        form.addWidget(self.suggest_button, 1, 2)
        form.addWidget(self.name_status, 2, 1, 1, 2)
        form.addWidget(QLabel("Người dùng"), 3, 0)
        form.addWidget(self.primary_user, 3, 1, 1, 2)
        form.addWidget(QLabel("Profile phần mềm"), 4, 0)
        form.addWidget(self.profile, 4, 1)
        form.setColumnStretch(1, 1)
        layout.addLayout(form)
        self.save_info_button = QPushButton("Lưu và sang bước tiếp")
        self.save_info_button.setObjectName("Primary")
        self._buttons(layout, self.save_info_button)
        layout.addStretch(1)
        self._fill_departments()
        self.add_department_button.clicked.connect(self.add_department)
        self.suggest_button.clicked.connect(self.suggest_name)
        self.save_info_button.clicked.connect(self.save_info)
        self.computer_name.textChanged.connect(self._name_changed)
        self.department.currentIndexChanged.connect(lambda _index: self._name_changed())
        return panel

    def _join_panel(self) -> QWidget:
        panel, layout = self._panel("2. Đổi tên + join domain")
        self.join_info = _note("")
        layout.addWidget(self.join_info)
        self.join_button = QPushButton("Đổi tên và join domain")
        self.join_button.setObjectName("Primary")
        self.join_done_button = QPushButton("Đánh dấu đã xong")
        self.join_done_button.setToolTip("Máy đã đúng tên và đã ở domain")
        self._buttons(layout, self.join_button, self.join_done_button)
        layout.addStretch(1)
        self.join_button.clicked.connect(self.join)
        self.join_done_button.clicked.connect(lambda: self.record("join", "ok", "Máy đã đúng tên và ở domain",
                                                                  advance=True))
        return panel

    def _after_panel(self) -> QWidget:
        panel, layout = self._panel("3. Sau khởi động lại")
        self.after_info = _note("")
        layout.addWidget(self.after_info)
        self.after_button = QPushButton("Chạy các bước sau khởi động lại")
        self.after_button.setObjectName("Primary")
        self._buttons(layout, self.after_button, self._skip_button("after"))
        layout.addStretch(1)
        self.after_button.clicked.connect(self.run_after_restart)
        return panel

    def _software_panel(self) -> QWidget:
        panel, layout = self._panel("4. Cài phần mềm")
        self.software_info = _note("")
        layout.addWidget(self.software_info)
        self.software_button = QPushButton("Mở trang Phần mềm, chọn sẵn profile")
        self.software_button.setObjectName("Primary")
        self.software_done_button = QPushButton("Đánh dấu đã xong")
        self._buttons(layout, self.software_button, self.software_done_button, self._skip_button("software"))
        layout.addStretch(1)
        self.software_button.clicked.connect(self.go_software)
        self.software_done_button.clicked.connect(lambda: self.record("software", "ok", "IT đánh dấu xong",
                                                                      advance=True))
        return panel

    def _config_panel(self) -> QWidget:
        panel, layout = self._panel("5. Cấu hình chuẩn")
        pack = self._packs.get("pack.standard_config")
        names = "".join(f"<li>{self._actions[action_id].name}</li>" for action_id in pack.actions) if pack else ""
        layout.addWidget(_note("Chạy gói <b>Cấu hình chuẩn máy mới</b> của trang Cấu hình, mục nào lỗi thì vẫn làm "
                               f"tiếp:<ul>{names}</ul>Muốn bỏ bớt mục thì làm ở trang Cấu hình rồi đánh dấu xong."))
        self.config_button = QPushButton("Chạy cấu hình chuẩn")
        self.config_button.setObjectName("Primary")
        self.config_button.setEnabled(pack is not None)
        self.config_done_button = QPushButton("Đánh dấu đã xong")
        self._buttons(layout, self.config_button, self.config_done_button, self._skip_button("config"))
        layout.addStretch(1)
        self.config_button.clicked.connect(self.run_config)
        self.config_done_button.clicked.connect(lambda: self.record("config", "ok", "IT đánh dấu xong", advance=True))
        return panel

    def _update_panel(self) -> QWidget:
        panel, layout = self._panel("6. Driver + Windows Update")
        layout.addWidget(_note(
            "Chạy lần lượt, mục lỗi thì vẫn làm tiếp:<ul>"
            "<li><b>Cập nhật driver, BIOS của hãng</b>: máy Dell dùng Dell Command | Update, máy Lenovo dòng Think "
            "dùng Lenovo System Update (chưa có thì tự cài bằng winget). Hãng khác thì bỏ qua mục này.</li>"
            "<li><b>Quét và cài bản cập nhật</b> của Windows.</li></ul>"
            "Cần Internet, có thể mất 30 phút trở lên; xong thì tool hỏi khởi động lại."))
        self.update_button = QPushButton("Cập nhật driver và Windows")
        self.update_button.setObjectName("Primary")
        self.update_done_button = QPushButton("Đánh dấu đã xong")
        self._buttons(layout, self.update_button, self.update_done_button, self._skip_button("update"))
        layout.addStretch(1)
        self.update_button.clicked.connect(self.run_update)
        self.update_done_button.clicked.connect(lambda: self.record("update", "ok", "IT đánh dấu xong", advance=True))
        return panel

    def _report_panel(self) -> QWidget:
        panel, layout = self._panel("7. Báo cáo")
        layout.addWidget(_note("Báo cáo HTML gồm kết quả từng bước, hệ điều hành, phần cứng (serial) và phần mềm đã "
                               "cài. Lưu trong thư mục reports của tool và trong thư mục Reports cạnh tool trên ổ "
                               "mang theo (nếu còn cắm). Không gửi lên đâu."))
        self.report_status = QLabel()
        self.report_status.setWordWrap(True)
        layout.addWidget(self.report_status)
        self.report_button = QPushButton("Tạo báo cáo")
        self.report_button.setObjectName("Primary")
        self.open_reports_button = QPushButton("Mở thư mục báo cáo")
        self.finish_button = QPushButton("Kết thúc wizard")
        self.finish_button.setToolTip("Bỏ hẹn tự mở lại tool và đánh dấu máy này đã cài xong")
        self._buttons(layout, self.report_button, self.open_reports_button, self.finish_button)
        layout.addStretch(1)
        self.report_button.clicked.connect(self.make_report)
        self.open_reports_button.clicked.connect(lambda: open_path(paths.reports_dir()))
        self.finish_button.clicked.connect(self.finish)
        return panel

    # ------------------------------------------------------------ trạng thái

    def start_step(self) -> str:
        """Bước mở khi vào trang: wizard đang dở thì mở bước cần làm tiếp, không thì bước 0."""
        if self.state is None:
            return "check"
        if self.state.status("join") == "ok" and not self._machine_matches():
            return "join"  # đã join nhưng chưa khởi động lại
        return self.state.next_step()

    def _machine_matches(self) -> bool:
        machine = self.app.machine
        name_ok = not self.state or machine.computer_name.upper() == self.state.computer_name.upper()
        return machine.joined_domain and name_ok

    def domain(self) -> str:
        return precheck.target_domain(self.app)

    def _netbios(self) -> str:
        return self.app.site.netbios_domain or self.domain().split(".")[0].upper()

    def record(self, key: str, status: str, note: str = "", advance: bool = False) -> None:
        if self.state is None:
            self.state = wizard_state.WizardState(origin=str(paths.app_root()))
        self.state.mark(key, status, note)
        try:
            wizard_state.save(self.state)
        except OSError as exc:
            self.controller.say(Level.ERROR, f"Không lưu được tiến độ wizard: {exc}")
        self._refresh()
        if advance and status in ("ok", "skipped"):
            index = STEP_KEYS.index(key)
            if index + 1 < len(STEP_KEYS):
                self.step_list.setCurrentRow(index + 1)

    def _refresh(self) -> None:
        state = self.state
        for row, key in enumerate(STEP_KEYS):
            item = self.step_list.item(row)
            status = state.status(key) if state else ""
            item.setText(f"{STEP_MARKS.get(status, '○')}  {wizard_state.STEP_NAMES[key]}")
            item.setForeground(QBrush(QColor(STEP_COLORS.get(status, "#1f2933"))))
            record = state.steps.get(key) if state else None
            item.setToolTip(f"{wizard_state.STATUS_LABELS.get(record.status, '')} lúc {record.time_label}"
                            f"{': ' + record.note if record.note else ''}" if record else "Chưa làm")
        if state is None:
            self.banner.setText("Chưa bắt đầu cài máy nào. Xem bước 0 rồi điền thông tin máy ở bước 1.")
            self.banner.setProperty("state", "")
        else:
            name = state.computer_name or "(chưa đặt tên)"
            started = wizard_state.StepRecord("", state.started).time_label
            self.banner.setText(f"Đang cài máy {name}, bắt đầu {started}. Bước tiếp theo: "
                                f"{wizard_state.STEP_NAMES[self.start_step()]}.")
            self.banner.setProperty("state", "warn")
        _restyle(self.banner)
        self._refresh_join()
        self._refresh_after()
        self._refresh_software()
        self._update_buttons()

    def _load_state_into_fields(self) -> None:
        state = self.state
        self.computer_name.setText(state.computer_name if state else "")
        self.primary_user.setText(state.primary_user if state else "")
        if state and state.department:
            index = self.department.findData(state.department)
            if index >= 0:
                self.department.setCurrentIndex(index)

    # ------------------------------------------------------------ bước 1

    def _fill_departments(self, select: str = "") -> None:
        self.department.blockSignals(True)
        self.department.clear()
        self.department.addItem("— Chọn phòng —", "")
        for code, name in self.app.site.departments:
            self.department.addItem(f"{code}: {name}", code)
        if select:
            self.department.setCurrentIndex(max(self.department.findData(select), 0))
        self.department.blockSignals(False)

    def add_department(self) -> None:
        dialog = DepartmentDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        code, name = dialog.code.text().strip().upper(), dialog.name.text().strip()
        try:
            self.app.site = config.add_department(self.app.site, code, name)
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, "Chưa lưu được mã phòng", str(exc))
            return
        self.controller.say(Level.OK, f"Đã thêm mã phòng {code} ({name}) vào {self.app.site.source}.")
        self._fill_departments(select=code)
        self._name_changed()

    def selected_department(self) -> str:
        return self.department.currentData() or ""

    def suggest_name(self) -> None:
        department = self.selected_department()
        if not department:
            self.name_status.setText("Chọn phòng ban trước.")
            return
        domain = self.domain()
        if not domain:
            self.name_status.setText("Chưa biết domain: khai báo domain trong site.yaml, hoặc gõ tên máy tay.")
            return
        credential = None
        if not self.app.machine.joined_domain:
            credential = self._credential or ask_credential(
                ["Hỏi AD danh sách tên máy đã dùng (chỉ đọc)", "Đổi tên và join domain (bước 2)"], self._netbios(), self)
            if credential is None:
                return
            self._credential = credential
        prefix = naming.base_name(self.app.site.prefix, department)
        self.name_status.setText(f"Đang hỏi AD các máy tên {prefix}…")
        self.suggest_button.setEnabled(False)
        self.worker.run("names", lambda: (prefix, naming.existing_names(domain, prefix, credential)))

    def _worker_done(self, name: str, result: object) -> None:
        if name == "names":
            self.suggest_button.setEnabled(True)
            if isinstance(result, Exception):
                self.name_status.setText(f"Không hỏi được AD: {result}. Gõ tên máy tay.")
                self.name_status.setProperty("state", "warn")
                if "password" in str(result).lower() or "mật khẩu" in str(result).lower():
                    self._credential = None
            else:
                prefix, existing = result
                self._existing = existing
                suggestion = naming.suggest_name(self.app.site.prefix, self.selected_department(), existing)
                self.computer_name.setText(suggestion)
                self.name_status.setText(f"AD có {len(existing)} máy tên {prefix}…, gợi ý {suggestion}.")
                self.name_status.setProperty("state", "ok")
            _restyle(self.name_status)
        elif name == "profiles":
            self.profiles = [] if isinstance(result, Exception) else result
            current = self.state.profile if self.state else self.profile.currentData()
            self.profile.clear()
            self.profile.addItem("— Không cài theo profile —", "")
            for profile_id, profile_name in self.profiles:
                self.profile.addItem(profile_name, profile_id)
            if current:
                self.profile.setCurrentIndex(max(self.profile.findData(current), 0))

    def _name_changed(self) -> None:
        name = self.computer_name.text().strip().upper()
        problem = naming.name_problem(name) if name else None
        if problem:
            self.name_status.setText(problem)
            self.name_status.setProperty("state", "bad")
        elif name and self._existing is not None and naming.taken(name, self._existing):
            self.name_status.setText(f"{name} đã có trong AD. Join tên này có thể bị chặn (KB5020276) nếu tài khoản "
                                     "join không phải người tạo máy đó: chọn tên khác hoặc xoá máy cũ trong AD.")
            self.name_status.setProperty("state", "warn")
        elif name and self.selected_department() and not name.startswith(
                naming.base_name(self.app.site.prefix, self.selected_department())):
            self.name_status.setText(f"Tên không theo quy ước {naming.base_name(self.app.site.prefix, self.selected_department())}NN.")
            self.name_status.setProperty("state", "warn")
        elif self.name_status.property("state") in ("bad", "warn"):
            self.name_status.setText("")
            self.name_status.setProperty("state", "")
        _restyle(self.name_status)

    def save_info(self) -> None:
        name = self.computer_name.text().strip().upper()
        problem = naming.name_problem(name)
        if problem:
            QMessageBox.information(self, "Tên máy", problem)
            return
        if self.state is None:
            self.state = wizard_state.WizardState(origin=str(paths.app_root()))
        self.state.department = self.selected_department()
        self.state.computer_name = name
        self.state.primary_user = " ".join(self.primary_user.text().split())
        self.state.profile = self.profile.currentData() or ""
        self.computer_name.setText(name)
        self.record("info", "ok", f"Tên {name}", advance=True)

    # ------------------------------------------------------------ bước 2, 3

    def _refresh_join(self) -> None:
        state, machine, site = self.state, self.app.machine, self.app.site
        target = state.computer_name if state else ""
        domain = self.domain()
        ou = site.computer_ou or "container Computers mặc định (chưa khai báo computer_ou trong site.yaml)"
        now = f"{machine.computer_name}, {machine.domain_label}"
        if not target:
            text = "Lưu thông tin máy ở bước 1 trước."
        elif machine.joined_domain and machine.computer_name.upper() == target.upper():
            text = f"Máy đã tên <b>{target}</b> và đã ở domain {machine.domain_label}. Bấm Đánh dấu đã xong."
        elif state.status("join") == "ok":
            text = (f"Đã đổi tên thành <b>{target}</b> và join <b>{domain}</b>. <b>Khởi động lại máy</b> để có hiệu "
                    "lực; tool sẽ tự mở lại khi tài khoản admin đăng nhập.")
        else:
            text = (f"Hiện tại: {now}.<br>Sẽ đổi tên thành <b>{target}</b> và join domain <b>{domain or '?'}</b>, "
                    f"OU: {ou}.<br><br>Tool hỏi tài khoản join, chép chính nó vào %ProgramData%\\FVPL-ITTools\\app "
                    "và hẹn tự mở lại khi tài khoản admin đăng nhập (để làm tiếp kể cả khi đã rút USB). Xong thì "
                    "khởi động lại máy. Sau khởi động lại, đăng nhập bằng tài khoản domain có quyền admin "
                    "(Domain Admin) hoặc admin cục bộ.")
        self.join_info.setText(text)

    def join(self) -> None:
        state = self.state
        if state is None or not state.computer_name:
            QMessageBox.information(self, "Thiếu thông tin", "Lưu thông tin máy ở bước 1 trước.")
            return
        try:
            action = steps.join_action(state.computer_name, self.domain(), self.app.site.computer_ou)
        except steps.StepError as exc:
            QMessageBox.warning(self, "Chưa join được", str(exc))
            return
        bad = [check.name for check in self.check.checks if check.state == "bad"]
        warning = f"\n\nBước 0 còn mục chưa đạt: {', '.join(bad)}." if bad else ""
        answer = QMessageBox.question(
            self, "Đổi tên và join domain",
            f"Đổi tên máy thành {state.computer_name} và join domain {self.domain()}?{warning}\n\n"
            "Không hoàn tác được bằng tool (muốn bỏ thì cho máy ra workgroup bằng tay). Xong thì cần khởi động lại.")
        if answer != QMessageBox.StandardButton.Yes:
            return
        credential = self._credential or ask_credential([action.name], self._netbios(), self)
        if credential is None:
            self.controller.say(Level.WARN, "Đã huỷ vì chưa nhập tài khoản join.")
            return
        self._pending = "join"
        self.controller.run([action], credential=credential)
        self._credential = None  # mật khẩu không giữ lại sau lượt join

    def _refresh_after(self) -> None:
        machine, site = self.app.machine, self.app.site
        lines = [f"Máy hiện tại: <b>{machine.computer_name}</b>, {machine.domain_label}."]
        if not machine.joined_domain:
            lines.append("Máy chưa vào domain: làm bước 2 rồi khởi động lại.")
        lines.append("Các việc: kiểm tra máy đã vào domain và đúng tên, secure channel; đồng bộ giờ với DC; "
                     "cập nhật Group Policy (gpupdate /force)"
                     + (f"; thêm nhóm <b>{site.it_admins_group}</b> vào Administrators của máy." if site.it_admins_group
                        else ". Chưa khai báo it_admins_group trong site.yaml nên không thêm nhóm IT vào Administrators."))
        self.after_info.setText("<br>".join(lines))

    def run_after_restart(self) -> None:
        site = self.app.site
        try:
            actions = steps.after_restart_actions(self.state.computer_name if self.state else "",
                                                  site.it_admins_group, self._actions)
        except steps.StepError as exc:
            QMessageBox.warning(self, "Sai cấu hình", str(exc))
            return
        self._pending = "after"
        self.controller.run(actions, stop_on_error=False)

    # ------------------------------------------------------------ bước 4, 5, 6

    def _refresh_software(self) -> None:
        profile = self.state.profile if self.state else ""
        name = dict(self.profiles).get(profile, profile)
        source = self.app.software.label
        text = (f"Profile đã chọn: <b>{name}</b>. " if profile else "Chưa chọn profile ở bước 1. ")
        text += (f"Kho bộ cài: {source}.<br>Bấm nút dưới để sang trang Phần mềm với các ứng dụng của profile đã được "
                 "tick sẵn, chọn thêm bản Office theo người dùng nếu cần, rồi bấm Cài. Cài xong tool tự ghi kết quả "
                 "vào bước này.")
        self.software_info.setText(text)

    def go_software(self) -> None:
        self._pending = "software"
        self.open_software.emit(self.state.profile if self.state else "")

    def run_config(self) -> None:
        pack = self._packs.get("pack.standard_config")
        if pack is None:
            return
        self._pending = "config"
        self.controller.run([self._actions[action_id] for action_id in pack.actions], stop_on_error=False)

    def update_actions(self) -> list:
        """Bước 6: bỏ mục driver của hãng nếu máy không phải Dell / Lenovo (mục đó chỉ báo không hỗ trợ)."""
        vendor = sysinfo.manufacturer().lower()
        wanted = [action_id for action_id in UPDATE_ACTIONS
                  if action_id != "drv.vendor_update" or not vendor or "dell" in vendor or "lenovo" in vendor]
        return [self._actions[action_id] for action_id in wanted if action_id in self._actions]

    def run_update(self) -> None:
        actions = self.update_actions()
        if actions:
            self._pending = "update"
            self.controller.run(actions, stop_on_error=False)

    def _run_finished(self, result: object) -> None:
        key = self._pending
        if key is None:
            return
        if isinstance(result, ReportResult):
            self._pending = None
            self._report_done(result)
            return
        if not isinstance(result, BatchResult):
            if key != "software":
                self._pending = None
            return
        ids = [item.action.id for item in result.results]
        if key == "software" and not any(action_id.startswith("app.") for action_id in ids):
            return  # chạy việc khác trong lúc chờ cài phần mềm
        self._pending = None
        failed = [item.action.name for item in result.results if item.status is Status.FAILED]
        done = result.count(Status.OK)
        note = f"{done} mục xong" + (f", lỗi: {', '.join(failed)}" if failed else "")
        if result.cancelled:
            note += ", bị huỷ giữa chừng"
        status = "failed" if failed or result.cancelled or not done else "ok"
        if key == "join" and status == "ok":
            note = "Chờ khởi động lại"
        self.record(key, status, note, advance=status == "ok" and key != "join")

    # ------------------------------------------------------------ bước 7

    def make_report(self) -> None:
        if self.state is None:
            QMessageBox.information(self, "Chưa có gì để báo cáo", "Chưa bắt đầu wizard cho máy này.")
            return
        state, machine, env = self.state, self.app.machine, self.app.env
        basics = inventory.Basics(
            computer_name=machine.computer_name, domain_label=machine.domain_label,
            joined_domain=machine.joined_domain, os_label=machine.os_label,
            target_user=env.target_user.name, is_admin=env.is_admin,
        )
        domain, account = self.domain(), env.process_user.name

        def job(ctx: RunContext) -> ReportResult:
            ctx.say(Level.HEADER, "▶ Tạo báo cáo cài máy")
            ctx.say(Level.INFO, "Đọc hệ điều hành, phần cứng và phần mềm đã cài…")
            data = report.collect(state, basics, domain, account, __version__, env.target_user.sid, ctx.cancel)
            files = report.save(report.to_html(data), basics.computer_name, basics.now, state.origin)
            for file in files:
                ctx.say(Level.OK, f"✔ Đã lưu báo cáo: {file}")
            if not files:
                ctx.say(Level.ERROR, "✖ Không lưu được báo cáo, xem file log.")
            return ReportResult(files)

        self._pending = "report"
        self.controller.run_job(job)

    def _report_done(self, result: ReportResult) -> None:
        if not result.files:
            self.record("report", "failed", "Không lưu được báo cáo")
            return
        self.report_status.setText("Đã lưu: " + "; ".join(str(file) for file in result.files))
        self.record("report", "ok", str(result.files[0].name))
        open_as_user(result.files[0])

    def finish(self) -> None:
        if self.state is None:
            return
        missing = [wizard_state.STEP_NAMES[key] for key in STEP_KEYS[1:]
                   if self.state.status(key) not in ("ok", "skipped")]
        text = "Kết thúc wizard cho máy này? Tool bỏ hẹn tự mở lại sau khi khởi động."
        if missing:
            text += "\n\nCác bước chưa xong: " + ", ".join(missing) + "."
        if QMessageBox.question(self, "Kết thúc wizard", text) != QMessageBox.StandardButton.Yes:
            return
        self._close_wizard("Đã kết thúc wizard cài máy.")

    def reset(self) -> None:
        if self.state is None:
            return
        answer = QMessageBox.question(
            self, "Huỷ wizard",
            f"Xoá tiến độ cài máy {self.state.computer_name or ''} đang lưu và bắt đầu lại từ đầu?\n\n"
            "Những gì đã làm trên máy (đổi tên, join, cài phần mềm) vẫn giữ nguyên.")
        if answer == QMessageBox.StandardButton.Yes:
            self._close_wizard("Đã xoá tiến độ wizard.")

    def _close_wizard(self, message: str) -> None:
        if self.state is not None and self.state.status("join") == "ok":
            self.controller.run([steps.finish_action()])  # bỏ tác vụ mở lại tool mà bước 2 đã tạo
        if self.state is not None:
            self.state.finished = wizard_state._now()
            try:
                wizard_state.save(self.state)
            except OSError:
                log.exception("Không lưu được trạng thái wizard")
        self.state = None
        self._existing = None
        self._load_state_into_fields()
        self.report_status.setText("")
        self._refresh()
        self.step_list.setCurrentRow(0)
        self.controller.say(Level.INFO, message)

    # ------------------------------------------------------------ chung

    def _step_changed(self, row: int) -> None:
        if row >= 0:
            self.stack.setCurrentIndex(row)

    def _update_buttons(self) -> None:
        busy = self.controller.busy
        admin = self.app.env.is_admin
        state = self.state
        has_info = bool(state and state.computer_name)
        machine = self.app.machine
        matches = has_info and machine.joined_domain and machine.computer_name.upper() == state.computer_name.upper()
        self.save_info_button.setEnabled(not busy)
        self.join_button.setEnabled(not busy and admin and has_info and not matches and state.status("join") != "ok")
        self.join_done_button.setEnabled(not busy and bool(matches))
        self.after_button.setEnabled(not busy and admin and machine.joined_domain)
        for button in (self.software_button, self.config_button, self.update_button):
            button.setEnabled(not busy and admin)
        self.report_button.setEnabled(not busy and state is not None)
        self.finish_button.setEnabled(not busy and state is not None)
        self.reset_button.setVisible(state is not None)
        if not admin:
            for button in (self.join_button, self.after_button, self.software_button, self.config_button,
                           self.update_button):
                button.setToolTip("Cần mở tool bằng quyền admin")

    def showEvent(self, event) -> None:
        if not self._started:
            self._started = True
            self.check.recheck()
            root = self.app.software.root
            self.worker.run("profiles", lambda: [
                (profile.id, profile.name)
                for profile in catalog_module.load_catalog(root if root and os.path.isdir(root) else "").profiles])
        super().showEvent(event)

    @property
    def loading(self) -> bool:
        return self.check.loading

    def stop(self) -> None:
        self.check.stop()
