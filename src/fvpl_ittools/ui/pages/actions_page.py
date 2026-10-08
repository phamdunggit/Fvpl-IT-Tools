"""Trang danh sách mục (Sửa lỗi, Cấu hình, Tối ưu, Tiện ích): cây mục bên trái, chi tiết bên phải."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QFont, QGuiApplication
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QTreeWidgetItemIterator,
    QVBoxLayout,
    QWidget,
)

from ...actions.model import Action, Risk, Scope, UndoMode
from ...app import AppContext
from ...core import executor
from ...core.executor import Status
from ..controller import RunController
from ..text import fold
from ..theme import RISK_COLORS, STATE_COLORS
from ..widgets import badge, badge_row, page_header

ACTION_ID_ROLE = Qt.ItemDataRole.UserRole


def action_status(action: Action, app: AppContext, controller: RunController) -> tuple[str, str]:
    """(chữ, loại màu) cho cột Trạng thái."""
    env = app.env
    if not action.supports_build(env.build):
        return "Không áp dụng", "off"
    if executor.gpo_managed(action, env):
        return "GPO quản lý", "gpo"
    state = executor.check_state(action, env)
    if state is True:
        return "Đang bật", "on"
    last = controller.last_results.get(action.id)
    if last is not None:
        time_label = last.finished_at.strftime("%H:%M")
        if last.status is Status.OK:
            return f"✔ Xong {time_label}", "ok"
        if last.status is Status.FAILED:
            return f"✖ Lỗi {time_label}", "error"
    if state is False:
        return "Đang tắt", "off"
    if action.admin and not env.is_admin:
        return "Cần quyền admin", "blocked"
    return "", "off"


class ActionDetail(QFrame):
    """Khung chi tiết: mô tả, mức rủi ro, lệnh sẽ chạy, nút chạy / copy lệnh / hoàn tác."""

    def __init__(self, page: ActionsPage):
        super().__init__()
        self.page = page
        self.action: Action | None = None
        self.setObjectName("Card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        self.title = QLabel()
        self.title.setObjectName("DetailTitle")
        self.title.setWordWrap(True)
        self.badges_holder = QVBoxLayout()
        self.badges_holder.setContentsMargins(0, 0, 0, 0)
        self.description = QLabel()
        self.description.setWordWrap(True)
        self.description.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        commands_label = QLabel("Lệnh sẽ chạy")
        commands_label.setObjectName("SectionLabel")
        self.commands = QPlainTextEdit()
        self.commands.setObjectName("CodeView")
        self.commands.setReadOnly(True)
        self.commands.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.note = QLabel()
        self.note.setObjectName("Note")
        self.note.setWordWrap(True)

        buttons = QHBoxLayout()
        self.run_button = QPushButton("Chạy mục này")
        self.run_button.setObjectName("Primary")
        self.copy_button = QPushButton("Copy lệnh")
        self.undo_button = QPushButton("Hoàn tác")
        buttons.addWidget(self.run_button)
        buttons.addWidget(self.copy_button)
        buttons.addWidget(self.undo_button)
        buttons.addStretch(1)

        layout.addWidget(self.title)
        layout.addLayout(self.badges_holder)
        layout.addWidget(self.description)
        layout.addWidget(commands_label)
        layout.addWidget(self.commands, 1)
        layout.addWidget(self.note)
        layout.addLayout(buttons)

        self.run_button.clicked.connect(self._run)
        self.copy_button.clicked.connect(self._copy)
        self.undo_button.clicked.connect(self._undo)
        self.show_action(None)

    def show_action(self, action: Action | None) -> None:
        self.action = action
        while self.badges_holder.count():
            widget = self.badges_holder.takeAt(0).widget()
            if widget is not None:
                widget.deleteLater()
        if action is None:
            self.title.setText("Chọn một mục ở bên trái")
            self.description.setText("Tick vào ô vuông để chọn nhiều mục rồi bấm “Chạy mục đã chọn”.")
            self.commands.setPlainText("")
            self.note.setText("")
            for button in (self.run_button, self.copy_button, self.undo_button):
                button.setEnabled(False)
            return

        env = self.page.app.env
        badges = [badge(action.risk.label, action.risk.value)]
        if action.scope is Scope.USER:
            badges.append(badge(f"Áp cho {env.target_user.short_name}", "neutral"))
        else:
            badges.append(badge("Áp cho cả máy", "neutral"))
        if action.admin:
            badges.append(badge("Cần quyền admin", "neutral"))
        if action.reboot:
            badges.append(badge("Cần khởi động lại", "warn"))
        badges.append(badge("Hoàn tác được" if action.can_undo else "Không hoàn tác được", "neutral"))
        self.badges_holder.addWidget(badge_row(badges))

        self.title.setText(action.name)
        self.description.setText(action.description or "(Chưa có mô tả)")
        self.commands.setPlainText(executor.describe_action(action, env))
        self.note.setText(executor.blocked_reason(action, env) or "")
        self.refresh_buttons()

    def refresh_buttons(self) -> None:
        action = self.action
        busy = self.page.controller.busy
        if action is None:
            return
        blocked = executor.blocked_reason(action, self.page.app.env) is not None
        self.run_button.setEnabled(not busy and not blocked)
        self.copy_button.setEnabled(True)
        if action.undo_mode is UndoMode.AUTO:
            entry = self.page.app.journal.latest_for(action.id)
            self.undo_button.setEnabled(not busy and entry is not None)
            self.undo_button.setToolTip(f"Trả về như trước lần chạy lúc {entry.time_label}" if entry else "Chưa có lần chạy nào để hoàn tác")
        else:
            self.undo_button.setEnabled(not busy and action.undo_mode is UndoMode.STEPS)
            self.undo_button.setToolTip("" if action.can_undo else "Mục này không hoàn tác được")

    def _run(self) -> None:
        if self.action is not None:
            self.page.run_actions([self.action])

    def _copy(self) -> None:
        QGuiApplication.clipboard().setText(self.commands.toPlainText())
        self.page.controller.say(executor.Level.INFO, "Đã copy lệnh vào clipboard.")

    def _undo(self) -> None:
        action = self.action
        if action is None:
            return
        if action.undo_mode is UndoMode.STEPS:
            self.page.controller.run_undo_steps(action)
            return
        entry = self.page.app.journal.latest_for(action.id)
        if entry is not None:
            self.page.controller.undo([entry.id])


class ActionsPage(QWidget):
    def __init__(self, page_key: str, title: str, subtitle: str, empty_text: str,
                 app: AppContext, controller: RunController):
        super().__init__()
        self.app = app
        self.controller = controller
        self.actions = [action for action in app.actions if action.page == page_key]
        self._items: dict[str, QTreeWidgetItem] = {}
        self._by_id = {action.id: action for action in self.actions}

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 12)
        root.setSpacing(10)
        page_header(root, title, subtitle)

        if not self.actions:
            empty = QLabel(empty_text)
            empty.setObjectName("EmptyState")
            empty.setWordWrap(True)
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            root.addWidget(empty)
            root.addStretch(1)
            return

        toolbar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Tìm theo tên hoặc mô tả, gõ không dấu cũng được…")
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(240)
        self.restore_checkbox = QCheckBox("Tạo restore point")
        self.restore_checkbox.setToolTip("Tạo restore point trước khi chạy mục Cẩn thận hoặc Nâng cao")
        self.restore_checkbox.setChecked(controller.create_restore_point)
        self.preview_button = QPushButton("Xem trước")
        self.preview_button.setToolTip("Hiện các lệnh sẽ chạy của những mục đã tick, chưa chạy gì")
        self.run_button = QPushButton("Chạy mục đã chọn")
        self.run_button.setObjectName("Primary")
        toolbar.addWidget(self.search, 1)
        toolbar.addWidget(self.restore_checkbox)
        toolbar.addWidget(self.preview_button)
        toolbar.addWidget(self.run_button)
        root.addLayout(toolbar)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Mục", "Rủi ro", "Trạng thái"])
        self.tree.setUniformRowHeights(True)
        header = self.tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.detail = ActionDetail(self)
        splitter.addWidget(self.tree)
        splitter.addWidget(self.detail)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setChildrenCollapsible(False)
        root.addWidget(splitter, 1)

        self._populate()
        self.refresh_states()

        self.search.textChanged.connect(self._filter)
        self.tree.currentItemChanged.connect(self._current_changed)
        self.restore_checkbox.toggled.connect(controller.set_create_restore_point)
        controller.restore_point_changed.connect(self.restore_checkbox.setChecked)
        self.preview_button.clicked.connect(self._preview)
        self.run_button.clicked.connect(lambda: self.run_actions(self.checked_actions()))
        controller.busy_changed.connect(self._busy_changed)
        controller.journal_changed.connect(self.refresh_states)
        self._current_changed(self.tree.currentItem(), None)

    # ------------------------------------------------------------ dựng cây

    def _populate(self) -> None:
        categories: dict[str, QTreeWidgetItem] = {}
        bold = QFont()
        bold.setBold(True)
        for action in self.actions:
            parent = categories.get(action.category)
            if parent is None:
                parent = QTreeWidgetItem(self.tree, [action.category])
                parent.setFlags(parent.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsAutoTristate)
                parent.setCheckState(0, Qt.CheckState.Unchecked)
                parent.setFont(0, bold)
                categories[action.category] = parent
            item = QTreeWidgetItem(parent, [action.name, action.risk.label, ""])
            item.setData(0, ACTION_ID_ROLE, action.id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(0, Qt.CheckState.Unchecked)
            item.setForeground(1, QBrush(QColor(RISK_COLORS[action.risk])))
            item.setToolTip(0, action.description)
            self._items[action.id] = item
        self.tree.expandAll()
        first = self._items.get(self.actions[0].id)
        if first is not None:
            self.tree.setCurrentItem(first)

    def refresh_states(self) -> None:
        if not self.actions:
            return
        for action in self.actions:
            text, kind = action_status(action, self.app, self.controller)
            item = self._items[action.id]
            item.setText(2, text)
            item.setForeground(2, QBrush(QColor(STATE_COLORS.get(kind, "#64748b"))))
        self.detail.refresh_buttons()

    # ------------------------------------------------------------ thao tác

    def checked_actions(self) -> list[Action]:
        selected = []
        iterator = QTreeWidgetItemIterator(self.tree)
        while iterator.value() is not None:
            item = iterator.value()
            action_id = item.data(0, ACTION_ID_ROLE)
            if action_id and item.checkState(0) == Qt.CheckState.Checked and not item.isHidden():
                selected.append(self._by_id[action_id])
            iterator += 1
        return selected

    def run_actions(self, actions: list[Action]) -> None:
        if not actions:
            QMessageBox.information(self, "Chưa chọn mục", "Tick vào ô vuông trước các mục cần chạy.")
            return
        risky = [action for action in actions if action.risk is not Risk.SAFE]
        if risky:
            names = "\n".join(f"• {action.name} ({action.risk.label})" for action in risky)
            restore = "Tool sẽ tạo restore point trước khi chạy." if self.controller.create_restore_point else \
                "Đang tắt tạo restore point."
            answer = QMessageBox.question(
                self, "Xác nhận",
                f"Các mục sau có rủi ro:\n{names}\n\n{restore}\nTiếp tục?",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self.controller.run(actions)

    def _preview(self) -> None:
        actions = self.checked_actions()
        if not actions:
            QMessageBox.information(self, "Chưa chọn mục", "Tick vào ô vuông trước các mục cần xem.")
            return
        self.controller.preview(actions)

    def _current_changed(self, current: QTreeWidgetItem | None, _previous) -> None:
        action_id = current.data(0, ACTION_ID_ROLE) if current is not None else None
        self.detail.show_action(self._by_id.get(action_id) if action_id else None)

    def _filter(self, text: str) -> None:
        needle = fold(text.strip())
        for index in range(self.tree.topLevelItemCount()):
            category = self.tree.topLevelItem(index)
            category_match = needle in fold(category.text(0))
            visible = 0
            for child_index in range(category.childCount()):
                child = category.child(child_index)
                action = self._by_id[child.data(0, ACTION_ID_ROLE)]
                haystack = fold(f"{action.name} {action.description} {action.id}")
                show = not needle or category_match or needle in haystack
                child.setHidden(not show)
                visible += show
            category.setHidden(visible == 0)

    def _busy_changed(self, busy: bool) -> None:
        self.run_button.setEnabled(not busy)
        self.preview_button.setEnabled(not busy)
        self.detail.refresh_buttons()
        if not busy:
            self.refresh_states()
