"""Màn hình sửa lỗi theo tình huống (mockup 3): Kiểm tra → Sửa → Kết quả.

1. Kiểm tra: chạy script chỉ đọc của tình huống ở thread nền, hiện từng dấu hiệu bằng lời thường.
2. Đề xuất: "Tool sẽ làm" (mục sửa tick sẵn theo core/scenarios.plan) và "Bạn cần tự làm" (lời khuyên, nút mở chỗ khác).
3. Sửa: chạy các mục đã tick qua RunController, khung tiến độ như trang Phần mềm.
4. Kiểm tra lại tự động, báo đã sửa được gì, còn gì; "Vẫn chưa được?" gợi ý chỗ khác và nút Gửi cho IT.
"""

from __future__ import annotations

import logging
from typing import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ... import __version__
from ...actions.model import Risk
from ...app import AppContext
from ...core import executor, scenarios
from ...core.executor import BatchResult, Level, Status
from ...core.support_report import SupportReport
from .. import icons, theme
from ..components.banner import Banner
from ..components.progress_panel import ProgressPanel
from ..controller import RunController
from ..credential_dialog import ask_credential
from ..widgets import Worker, badge

log = logging.getLogger(__name__)
STEPS = ("Kiểm tra", "Sửa", "Kết quả")
STAGE_STEP = {"checking": 0, "review": 0, "fixing": 1, "verifying": 2, "result": 2}
FINDING_ICONS = {"ok": "ok", "warn": "warn", "bad": "bad", "info": "info"}


def _clear(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        if item.widget() is not None:
            item.widget().deleteLater()
        elif item.layout() is not None:
            _clear(item.layout())


def _card(title: str) -> tuple[QFrame, QVBoxLayout]:
    card = QFrame()
    card.setObjectName("Card")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(18, 14, 18, 14)
    layout.setSpacing(8)
    label = QLabel(title)
    label.setObjectName("CardTitle")
    layout.addWidget(label)
    return card, layout


class FixRow(QFrame):
    """Một mục tool sẽ làm: ô tick + tên, nhãn rủi ro, lý do."""

    def __init__(self, item: scenarios.PlannedFix):
        super().__init__()
        self.item = item
        self.setObjectName("FixRow")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)
        top = QHBoxLayout()
        self.check = QCheckBox(item.action.title(basic=True))
        self.check.setToolTip(item.action.name)
        self.check.setChecked(item.checked)
        self.check.setStyleSheet("font-weight: 600;")
        top.addWidget(self.check, 1)
        kind = item.action.risk.value
        label = {"safe": "An toàn", "caution": "Có hoàn tác" if item.action.can_undo else "Cẩn thận",
                 "advanced": "Nâng cao"}[kind]
        top.addWidget(badge(label, kind))
        layout.addLayout(top)
        reason = QLabel("Vì: " + "; ".join(dict.fromkeys(item.reasons)))
        reason.setObjectName("PageSubtitle")
        reason.setWordWrap(True)
        reason.setContentsMargins(26, 0, 0, 0)
        layout.addWidget(reason)


class ScenarioPage(QWidget):
    navigate = Signal(str)

    def __init__(self, app: AppContext, controller: RunController, items: list[scenarios.Scenario],
                 log_text: Callable[[], str] = lambda: ""):
        super().__init__()
        self.app = app
        self.controller = controller
        self.scenarios = {item.id: item for item in items}
        self.log_text = log_text
        self.actions = {action.id: action for action in app.actions}
        self.scenario: scenarios.Scenario | None = None
        self.findings: list[scenarios.Finding] = []
        self.before: list[scenarios.Finding] = []  # dấu hiệu lúc trước khi sửa
        self.planned: list[scenarios.PlannedFix] = []
        self.fix_rows: list[FixRow] = []
        self.ran: BatchResult | None = None
        self.stage = "idle"
        self.error = ""
        self._generation = 0
        self.worker = Worker(self)
        self.worker.done.connect(self._checked)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setObjectName("PageScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll)
        body = QWidget()
        scroll.setWidget(body)
        root = QVBoxLayout(body)
        root.setContentsMargins(28, 18, 28, 20)
        root.setSpacing(14)

        back = QPushButton("‹ Trang chủ")
        back.setObjectName("LinkButton")
        back.setCursor(Qt.CursorShape.PointingHandCursor)
        back.clicked.connect(lambda: self.navigate.emit("page:home"))
        root.addWidget(back, 0, Qt.AlignmentFlag.AlignLeft)
        self.title = QLabel()
        self.title.setObjectName("PageTitle")
        self.subtitle = QLabel("Tool kiểm tra máy này, đề xuất cách sửa an toàn, sửa xong thì kiểm tra lại.")
        self.subtitle.setObjectName("PageSubtitle")
        self.subtitle.setWordWrap(True)
        root.addWidget(self.title)
        root.addWidget(self.subtitle)

        steps = QHBoxLayout()
        steps.setSpacing(8)
        self.step_labels: list[QLabel] = []
        for index, name in enumerate(STEPS):
            label = QLabel(f"{index + 1}  {name}")
            label.setObjectName("StepLabel")
            steps.addWidget(label)
            self.step_labels.append(label)
            if index < len(STEPS) - 1:
                line = QFrame()
                line.setObjectName("StepLine")
                line.setFixedSize(40, 2)
                steps.addWidget(line)
        steps.addStretch(1)
        root.addLayout(steps)

        self.banner = Banner()
        self.banner.clicked.connect(self._banner_clicked)
        root.addWidget(self.banner)

        self.findings_card, findings_layout = _card("Tool đã kiểm tra")
        self.findings_box = QVBoxLayout()
        self.findings_box.setSpacing(0)
        findings_layout.addLayout(self.findings_box)
        root.addWidget(self.findings_card)

        self.plan_card, plan_layout = _card("Tool sẽ làm")
        self.plan_box = QVBoxLayout()
        self.plan_box.setSpacing(8)
        plan_layout.addLayout(self.plan_box)
        buttons = QHBoxLayout()
        self.fix_button = QPushButton("Sửa giúp tôi")
        self.fix_button.setObjectName("Primary")
        self.fix_button.setMinimumHeight(36)
        self.fix_button.clicked.connect(self.fix)
        self.expert_button = QPushButton("Tôi muốn tự chọn (trang Sửa lỗi)")
        self.expert_button.clicked.connect(lambda: self.navigate.emit("page:fixes"))
        buttons.addWidget(self.fix_button)
        buttons.addWidget(self.expert_button)
        buttons.addStretch(1)
        plan_layout.addLayout(buttons)
        root.addWidget(self.plan_card)

        self.manual_card, manual_layout = _card("Bạn cần tự làm")
        self.manual_box = QVBoxLayout()
        self.manual_box.setSpacing(6)
        manual_layout.addLayout(self.manual_box)
        root.addWidget(self.manual_card)

        self.progress = ProgressPanel(controller)
        self.progress.setMinimumHeight(260)
        self.progress.hide()
        self.progress.dismissed.connect(self.progress.hide)
        root.addWidget(self.progress)

        self.more_card, more_layout = _card("Vẫn chưa được?")
        self.more_box = QVBoxLayout()
        self.more_box.setSpacing(4)
        more_layout.addLayout(self.more_box)
        more_buttons = QHBoxLayout()
        self.recheck_button = QPushButton("Kiểm tra lại")
        self.recheck_button.clicked.connect(self.recheck)
        self.report_button = QPushButton("Gửi kết quả cho IT")
        self.report_button.setToolTip("Chép báo cáo (máy, đã kiểm tra / đã làm gì, log) vào clipboard để dán vào Zalo, email")
        self.report_button.clicked.connect(self.copy_report)
        more_buttons.addWidget(self.recheck_button)
        more_buttons.addWidget(self.report_button)
        more_buttons.addStretch(1)
        more_layout.addLayout(more_buttons)
        root.addWidget(self.more_card)

        self.details_button = QPushButton("Chi tiết kỹ thuật ▸")
        self.details_button.setObjectName("LinkButton")
        self.details_button.setCheckable(True)
        self.details_button.toggled.connect(self._toggle_details)
        self.details = QPlainTextEdit()
        self.details.setObjectName("CodeView")
        self.details.setReadOnly(True)
        self.details.setMinimumHeight(140)
        self.details.hide()
        root.addWidget(self.details_button, 0, Qt.AlignmentFlag.AlignLeft)
        root.addWidget(self.details)
        root.addStretch(1)

        controller.finished.connect(self._run_finished)
        controller.busy_changed.connect(lambda _busy: self._update_buttons())
        self._render()

    # ------------------------------------------------------------ luồng

    def start(self, scenario_id: str) -> bool:
        scenario = self.scenarios.get(scenario_id)
        if scenario is None:
            return False
        if self.stage in ("fixing", "verifying") and self.scenario is not scenario:
            self.controller.say(Level.WARN, "Đang sửa theo tình huống khác, chờ xong rồi mở tình huống mới.")
            return False
        if self.scenario is scenario and self.stage in ("checking", "fixing", "verifying"):
            return True  # đang làm dở tình huống này: chỉ hiện lại
        self.scenario = scenario
        self.findings, self.before, self.planned, self.ran = [], [], [], None
        self.progress.hide()
        self.title.setText(scenario.title)
        self.subtitle.setText(scenario.description or
                              f"{scenario.tile}. Tool kiểm tra máy này, đề xuất cách sửa an toàn, sửa xong thì kiểm tra lại.")
        self._check("checking")
        return True

    def recheck(self) -> None:
        if self.scenario is not None and not self.controller.busy:
            self.progress.hide()
            self.before, self.ran = [], None
            self._check("checking")

    def _check(self, stage: str) -> None:
        self.stage = stage
        self.error = ""
        self._generation += 1
        scenario, variables = self.scenario, executor.ps_variables(self.app.env)
        self.worker.run(f"scenario:{self._generation}", lambda: scenarios.run_check(scenario, variables))
        self._render()

    def _checked(self, name: str, result: object) -> None:
        if name != f"scenario:{self._generation}":
            return  # lượt kiểm tra cũ
        if isinstance(result, Exception):
            self.error = str(result) or result.__class__.__name__
            self.findings = []
            self.stage = "result" if self.stage == "verifying" else "review"
            self.controller.say(Level.ERROR, f"{self.scenario.title}: không kiểm tra được: {self.error}")
        else:
            self.findings = list(result)
            self.stage = "result" if self.stage == "verifying" else "review"
            problems = scenarios.remaining_problems(self.findings)
            self.controller.say(Level.INFO, f"{self.scenario.title}: kiểm tra xong, {len(problems)} vấn đề.")
        self.planned = scenarios.plan(self.scenario, self.findings, self.actions)
        self._render()

    def selected_actions(self) -> list:
        return [row.item.action for row in self.fix_rows if row.check.isChecked()]

    def fix(self) -> None:
        actions = self.selected_actions()
        if not actions:
            QMessageBox.information(self, "Chưa chọn", "Tick ít nhất một việc trong khung \"Tool sẽ làm\".")
            return
        if self.controller.busy:
            QMessageBox.information(self, "Đang chạy", "Đang có việc chạy, chờ xong rồi bấm lại.")
            return
        env = self.app.env
        risky = [action for action in actions if action.risk is not Risk.SAFE]
        if risky:
            names = "\n".join(f"• {action.name} ({action.risk.label})" for action in risky)
            restore = ("Tool sẽ tạo điểm khôi phục trước khi chạy." if self.controller.create_restore_point
                       else "Đang tắt tạo điểm khôi phục.")
            if QMessageBox.question(self, "Xác nhận", f"Các việc sau đổi cài đặt của máy:\n{names}\n\n{restore}\nTiếp tục?") \
                    != QMessageBox.StandardButton.Yes:
                return
        credential = None
        need = [action.name for action in actions if action.needs_credential and not executor.blocked_reason(action, env)]
        if need:
            domain = self.app.machine.join_name if self.app.machine.joined_domain else self.app.site.netbios_domain
            credential = ask_credential(need, domain, self)
            if credential is None:
                self.controller.say(Level.WARN, "Đã huỷ vì chưa nhập tài khoản domain.")
                return
        self.before = list(self.findings)
        self.stage = "fixing"
        self.progress.watch(f"Đang sửa: {self.scenario.title}")
        self.progress.show()
        self.controller.run(actions, credential=credential)
        self._render()

    def _run_finished(self, result: object) -> None:
        if self.stage != "fixing" or not isinstance(result, BatchResult):
            return
        self.ran = result
        self._check("verifying")

    # ------------------------------------------------------------ Gửi cho IT

    def report(self) -> SupportReport:
        machine, env = self.app.machine, self.app.env
        lines = [line for line in self.log_text().splitlines() if line.strip()]
        report = SupportReport(
            computer=machine.computer_name, domain=machine.domain_label, os=machine.os_label,
            user=env.target_user.name, tool_version=__version__,
            topic=self.scenario.title if self.scenario else "", note=self.banner.title.text(),
            findings=[(finding.state, finding.text, finding.detail) for finding in self.findings],
            log=lines[-50:],
        )
        if self.ran is not None:
            report.actions = [(item.action.name, item.status.label + (f": {item.message}" if item.message else ""))
                              for item in self.ran.results]
        return report

    def copy_report(self) -> None:
        report = self.report()
        QGuiApplication.clipboard().setText(report.to_text())
        try:
            file = report.save()
            where = f" Đã lưu thêm file {file}."
        except OSError as exc:
            where = f" (Không lưu được file: {exc})"
        self.controller.say(Level.OK, "Đã chép báo cáo vào clipboard: dán (Ctrl+V) vào Zalo / email gửi IT." + where)
        QMessageBox.information(self, "Gửi cho IT",
                                "Đã chép báo cáo vào clipboard.\nMở Zalo hoặc email, bấm Ctrl+V để dán rồi gửi cho IT.")

    # ------------------------------------------------------------ vẽ

    def _banner_clicked(self) -> None:
        if self.stage in ("review", "result"):
            self.recheck()

    def _toggle_details(self, shown: bool) -> None:
        self.details.setVisible(shown)
        self.details_button.setText("Chi tiết kỹ thuật ▾" if shown else "Chi tiết kỹ thuật ▸")

    def _update_buttons(self) -> None:
        busy = self.controller.busy
        self.fix_button.setEnabled(not busy and self.stage in ("review", "result"))
        self.recheck_button.setEnabled(not busy and self.stage in ("review", "result"))

    def _render(self) -> None:
        current = STAGE_STEP.get(self.stage, 0)
        done_all = self.stage == "result"
        for index, label in enumerate(self.step_labels):
            state = "done" if index < current or (done_all and index == current) else ("active" if index == current else "")
            label.setProperty("state", state)
            label.setText(("✓  " if state == "done" else f"{index + 1}  ") + STEPS[index])
            label.style().unpolish(label)
            label.style().polish(label)

        scenario = self.scenario
        if scenario is None:
            self.banner.show_state("info", "Chọn một tình huống ở Trang chủ")
            for card in (self.findings_card, self.plan_card, self.manual_card, self.more_card):
                card.hide()
            return

        problems = scenarios.remaining_problems(self.findings)
        if self.stage == "checking":
            self.banner.show_state("info", "Đang kiểm tra máy…", "Chỉ xem, chưa đổi gì. Khoảng 5–30 giây.")
        elif self.stage == "fixing":
            self.banner.show_state("info", "Đang sửa…", "Không cần làm gì, cứ để tool chạy. Xong tool tự kiểm tra lại.")
        elif self.stage == "verifying":
            self.banner.show_state("info", "Đã sửa xong, đang kiểm tra lại…")
        elif self.error:
            self.banner.show_state("bad", "Không kiểm tra được", self.error, "Thử lại", primary=True)
        elif self.stage == "result":
            before_ids = {finding.id for finding in scenarios.remaining_problems(self.before)}
            fixed = len(before_ids - {finding.id for finding in problems})
            failed = self.ran is not None and self.ran.count(Status.FAILED)
            if not problems:
                self.banner.show_state("ok", "Đã sửa xong. Thử lại việc vừa bị lỗi.",
                                       "Tool đã kiểm tra lại, không còn thấy vấn đề nào.", "Kiểm tra lại")
            else:
                note = f"Đã sửa được {fixed} vấn đề, còn {len(problems)} vấn đề." if fixed else f"Còn {len(problems)} vấn đề."
                if failed:
                    note += f" {failed} việc chạy bị lỗi (xem khung tiến độ)."
                self.banner.show_state("warn", "Chưa sửa hết", note + " Xem phần Bạn cần tự làm bên dưới.", "Kiểm tra lại")
        elif problems:
            self.banner.show_state("warn", f"Tìm thấy {len(problems)} vấn đề",
                                   "Xem các dòng ⚠ / ✖ bên dưới. Tool đề xuất cách sửa ở khung Tool sẽ làm.")
        else:
            self.banner.show_state("ok", "Không thấy lỗi nào trong các điều tool kiểm tra được",
                                   "Vẫn còn lỗi thì xem gợi ý ở khung Vẫn chưa được.", "Kiểm tra lại")

        self._render_findings()
        self._render_plan()
        self._render_manual(problems)
        self._render_more()
        show_more = self.stage in ("review", "result") and (self.stage == "result" or not problems or bool(self.error))
        self.more_card.setVisible(show_more)
        self.details.setPlainText("\n".join(
            f"[{finding.state}] {finding.id}: {finding.text}" + (f"\n    {finding.detail}" if finding.detail else "")
            for finding in self.findings))
        self._update_buttons()

    def _render_findings(self) -> None:
        _clear(self.findings_box)
        self.findings_card.setVisible(bool(self.findings) and self.stage not in ("checking",))
        order = {"bad": 0, "warn": 1, "info": 2, "ok": 3}
        for finding in sorted(self.findings, key=lambda item: order.get(item.state, 4)):
            row = QFrame()
            row.setObjectName("HealthRow")
            layout = QHBoxLayout(row)
            layout.setContentsMargins(0, 8, 0, 8)
            layout.setSpacing(12)
            mark = QLabel()
            mark.setPixmap(icons.pixmap(FINDING_ICONS.get(finding.state, "info"),
                                        theme.STATUS_COLORS.get(finding.state, theme.ACCENT), 20))
            text = QLabel(finding.text)
            text.setWordWrap(True)
            layout.addWidget(mark, 0, Qt.AlignmentFlag.AlignTop)
            layout.addWidget(text, 1)
            self.findings_box.addWidget(row)

    def _render_plan(self) -> None:
        _clear(self.plan_box)
        self.fix_rows = []
        visible = self.stage in ("review", "result") and bool(self.planned) and not self.error
        self.plan_card.setVisible(visible)
        for item in self.planned:
            row = FixRow(item)
            self.plan_box.addWidget(row)
            self.fix_rows.append(row)
        self.fix_button.setText("Sửa lại" if self.stage == "result" else "Sửa giúp tôi")

    def _render_manual(self, problems: list[scenarios.Finding]) -> None:
        _clear(self.manual_box)
        rows = 0
        if self.stage in ("review", "result") and self.scenario is not None:
            for finding in problems + [item for item in self.findings if item.state == "info"]:
                rule = self.scenario.rules.get(finding.id)
                if rule is None or not (rule.advice or rule.link):
                    continue
                if finding.state == "info" and not rule.link:
                    continue
                line = QHBoxLayout()
                text = QLabel(f"<b>{finding.text}</b><br>{rule.advice}" if rule.advice else f"<b>{finding.text}</b>")
                text.setWordWrap(True)
                line.addWidget(text, 1)
                if rule.link:
                    button = QPushButton(rule.link_text or "Mở")
                    button.clicked.connect(lambda _checked=False, target=rule.link: self.navigate.emit(target))
                    line.addWidget(button, 0, Qt.AlignmentFlag.AlignTop)
                self.manual_box.addLayout(line)
                rows += 1
        self.manual_card.setVisible(rows > 0)

    def _render_more(self) -> None:
        _clear(self.more_box)
        if self.scenario is None:
            return
        for target, text in self.scenario.more:
            button = QPushButton(text)
            button.setObjectName("LinkButton")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, value=target: self.navigate.emit(value))
            self.more_box.addWidget(button, 0, Qt.AlignmentFlag.AlignLeft)
