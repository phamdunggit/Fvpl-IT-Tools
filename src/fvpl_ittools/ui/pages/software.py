"""Trang Phần mềm: kho bộ cài, chọn bản Office, danh mục từ apps.yaml, chọn theo profile, cài lần lượt có tiến độ.

Ứng dụng cùng khoá `choice` (ví dụ các bản Office) hiện thành nhóm thẻ chọn một; các ứng dụng khác nằm trong cây.
"""

from __future__ import annotations

import logging
import os
import re
import threading
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...app import AppContext
from ...core import paths, prefs
from ...core.executor import BatchResult, Level, Status
from ...software import catalog as catalog_module
from ...software import scan as scan_module
from ...software.catalog import App
from ...software.install import REMOVE_C2R, blocked_reason, install_action
from ..components.banner import Banner
from ..components.choice import ChoiceGroup, ChoiceOption
from ..components.progress_panel import ProgressPanel
from ..controller import RunController
from ..text import fold
from ..theme import STATE_COLORS
from ..widgets import page_header

log = logging.getLogger(__name__)
APP_ID_ROLE = Qt.ItemDataRole.UserRole
SELECT_VIEW, PROGRESS_VIEW = 0, 1
STORE_TITLES = {"local": "Kho bộ cài trên ổ mang theo", "chosen": "Kho bộ cài đã chọn", "share": "Kho bộ cài trên mạng"}


def short_name(name: str) -> tuple[str, str]:
    """("Office 2016", "64-bit") từ "Microsoft Office Standard 2016 (64-bit)": tên gọn cho thẻ chọn."""
    match = re.match(r"^(.*?)\s*\(([^)]*)\)\s*$", name)
    base, extra = (match.group(1), match.group(2)) if match else (name, "")
    base = re.sub(r"^Microsoft (?=Office)", "", base)
    base = re.sub(r"\b(Standard|Professional Plus|Professional) (?=\d)", "", base)
    return base.strip(), extra.strip()


class ScanLoader(QObject):
    done = Signal(int, object, str)  # lượt, SoftwareState hoặc None, thông báo lỗi

    def __init__(self, app: AppContext, parent: QObject | None = None):
        super().__init__(parent)
        self.app = app
        self.generation = 0

    def start(self) -> None:
        self.generation += 1
        threading.Thread(target=self._work, args=(self.generation,), name="software-scan", daemon=True).start()

    def _work(self, generation: int) -> None:
        try:
            self.done.emit(generation, scan_module.scan(self.app), "")
        except Exception as exc:  # lỗi bất ngờ không được làm treo trang
            log.exception("Lỗi khi quét phần mềm")
            self.done.emit(generation, None, str(exc) or exc.__class__.__name__)


class SoftwarePage(QWidget):
    store_changed = Signal()  # vừa quét xong hoặc đổi kho: thanh bên cập nhật dòng "Kho bộ cài"

    def __init__(self, app: AppContext, controller: RunController):
        super().__init__()
        self.app = app
        self.controller = controller
        self.state: scan_module.SoftwareState | None = None
        self.loading = False
        self._items: dict[str, QTreeWidgetItem] = {}
        self.choice_groups: dict[str, ChoiceGroup] = {}
        self._started = False
        self._wanted_profile: tuple[str, tuple[str, ...]] | None = None  # (profile, ứng dụng thêm) chờ quét xong
        self._wanted_focus: str | None = None  # ứng dụng chọn từ tìm kiếm, chờ quét xong
        self.loader = ScanLoader(app, self)
        self.loader.done.connect(self._scanned)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 12)
        root.setSpacing(10)
        page_header(
            root, "Cài phần mềm",
            "Chọn bản Office và các phần mềm cần cài rồi bấm Cài. Tool cài lần lượt, không cần bấm Next; "
            "một mục lỗi thì vẫn cài tiếp mục sau.",
        )
        self.views = QStackedWidget()
        root.addWidget(self.views, 1)

        select = QWidget()
        select_layout = QVBoxLayout(select)
        select_layout.setContentsMargins(0, 0, 0, 0)
        select_layout.setSpacing(10)
        self.store = Banner()
        self.store.show_state("info", "Đang kiểm tra kho bộ cài…")
        self.store.clicked.connect(self.choose_store)
        select_layout.addWidget(self.store)
        self.choice_area = QVBoxLayout()
        self.choice_area.setSpacing(10)
        select_layout.addLayout(self.choice_area)

        profile_row = QHBoxLayout()
        apps_label = QLabel("Phần mềm khác")
        apps_label.setObjectName("CardTitle")
        profile_row.addWidget(apps_label)
        profile_row.addSpacing(12)
        profile_row.addWidget(QLabel("Chọn nhanh theo phòng ban"))
        self.profile = QComboBox()
        self.profile.setMinimumWidth(180)
        self.pick_button = QPushButton("Chọn theo profile")
        self.pick_button.setToolTip("Tick các ứng dụng của profile (kể cả profile được kế thừa) mà máy chưa có")
        self.search = QLineEdit()
        self.search.setPlaceholderText("Tìm ứng dụng, gõ không dấu cũng được…")
        self.search.setClearButtonEnabled(True)
        profile_row.addWidget(self.profile)
        profile_row.addWidget(self.pick_button)
        profile_row.addSpacing(12)
        profile_row.addWidget(self.search, 1)
        select_layout.addLayout(profile_row)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Ứng dụng", "Nguồn", "Trạng thái"])
        self.tree.setUniformRowHeights(True)
        self.tree.setMinimumHeight(140)
        header = self.tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        select_layout.addWidget(self.tree, 1)
        self.info = QLabel("Đang đọc danh mục…")
        self.info.setObjectName("PageSubtitle")
        self.info.setWordWrap(True)
        select_layout.addWidget(self.info)
        # Cửa sổ thấp (màn hình laptop, khung log kéo cao) thì cuộn thay vì đè chữ lên nhau.
        select_scroll = QScrollArea()
        select_scroll.setObjectName("PageScroll")
        select_scroll.setWidgetResizable(True)
        select_scroll.setFrameShape(QFrame.Shape.NoFrame)
        select_scroll.setWidget(select)
        self.views.addWidget(select_scroll)

        self.progress = ProgressPanel(controller)
        self.progress.can_retry = True
        self.progress.hint_for = self._result_hint
        self.progress.retry_requested.connect(lambda: self.install(self.failed_apps()))
        self.progress.dismissed.connect(lambda: self.views.setCurrentIndex(SELECT_VIEW))
        self.views.addWidget(self.progress)

        self.bottom = QWidget()
        buttons = QHBoxLayout(self.bottom)
        buttons.setContentsMargins(0, 0, 0, 0)
        self.summary = QLabel()
        self.summary.setObjectName("BottomSummary")
        self.rescan_button = QPushButton("Kiểm tra lại")
        self.preview_button = QPushButton("Xem trước")
        self.preview_button.setToolTip("Hiện lệnh cài của các mục đã chọn, chưa chạy gì")
        self.retry_button = QPushButton("Thử lại mục lỗi")
        self.install_button = QPushButton("Cài")
        self.install_button.setObjectName("Primary")
        self.install_button.setMinimumWidth(120)
        buttons.addWidget(self.summary, 1)
        buttons.addWidget(self.rescan_button)
        buttons.addWidget(self.preview_button)
        buttons.addWidget(self.retry_button)
        buttons.addWidget(self.install_button)
        root.addWidget(self.bottom)

        self.rescan_button.clicked.connect(self.rescan)
        self.pick_button.clicked.connect(self.pick_profile)
        self.search.textChanged.connect(self._filter)
        self.preview_button.clicked.connect(self.preview)
        self.install_button.clicked.connect(lambda: self.install(self.selected_apps()))
        self.retry_button.clicked.connect(lambda: self.install(self.failed_apps()))
        self.tree.itemChanged.connect(lambda *_: self._update_summary())
        self.views.currentChanged.connect(lambda index: self.bottom.setVisible(index == SELECT_VIEW))
        controller.busy_changed.connect(lambda _busy: self._update_buttons())
        controller.finished.connect(self._run_finished)
        self._update_buttons()

    # ------------------------------------------------------------ quét

    def showEvent(self, event) -> None:
        if not self._started:
            self._started = True
            self.rescan()
        super().showEvent(event)

    def rescan(self) -> None:
        self.loading = True
        self.info.setText("Đang đọc danh mục và kiểm tra phần mềm đã cài…")
        self._update_buttons()
        self.loader.start()

    def _scanned(self, generation: int, state: object, error: str) -> None:
        if generation != self.loader.generation:
            return
        self.loading = False
        if state is None:
            self.info.setText(f"Không đọc được danh mục phần mềm: {error}")
            self.controller.say(Level.ERROR, f"Phần mềm: {error}")
            self._update_buttons()
            return
        first = self.state is None
        self.state = state
        if first:
            for error_text in state.catalog.errors:
                self.controller.say(Level.ERROR, f"Danh mục phần mềm khai báo sai, đã bỏ qua: {error_text}")
        self._populate()
        self.info.setText(self._info_text())
        self._update_store()
        self._update_buttons()
        if self._wanted_profile is not None:
            self.preselect_profile(*self._wanted_profile)
        if self._wanted_focus is not None:
            self.focus_app(self._wanted_focus)
        self.store_changed.emit()

    def focus_app(self, app_id: str) -> None:
        """Ứng dụng chọn từ tìm kiếm (Ctrl+K): chọn sẵn để cài và cuộn tới. Chưa quét xong thì làm sau."""
        self.views.setCurrentIndex(SELECT_VIEW)
        if self.state is None or self.loading:
            self._wanted_focus = app_id
            if not self.loading:
                self._started = True
                self.rescan()
            return
        self._wanted_focus = None
        app = self.state.catalog.app(app_id)
        if app is None:
            return
        if app.choice:
            if not self.choice_groups[app.choice].select(app.id):
                self.controller.say(Level.INFO, f"{app.name}: {self._choice_note(app)[2] or 'không chọn được'}")
            return
        item = self._items[app.id]
        if not self.state.detections[app.id].installed and blocked_reason(app, self.state.senv) is None:
            item.setCheckState(0, Qt.CheckState.Checked)
        self.search.clear()
        self.tree.setCurrentItem(item)
        self.tree.scrollToItem(item)

    def preselect_profile(self, profile_id: str, extra_apps: list[str] | tuple[str, ...] = ()) -> None:
        """Chọn profile, tick sẵn ứng dụng của nó và các ứng dụng thêm (wizard Cài máy mới gọi).

        Chưa quét xong thì làm sau khi quét."""
        if self.state is None or self.loading:
            self._wanted_profile = (profile_id, tuple(extra_apps))
            return
        self._wanted_profile = None
        if profile_id:
            index = self.profile.findData(profile_id)
            if index < 0:
                self.controller.say(Level.WARN, f"Danh mục phần mềm không có profile {profile_id!r}, chọn tay nhé.")
            else:
                self.profile.setCurrentIndex(index)
                self.pick_profile()
        picked, skipped = [], []
        for app_id in extra_apps:
            app = self.state.catalog.app(app_id)
            if app is None:
                skipped.append(app_id)
            elif app.choice:
                if self.choice_groups[app.choice].select(app.id):
                    picked.append(app.name)
                else:
                    skipped.append(app.name)
            elif self.state.detections[app_id].installed or blocked_reason(app, self.state.senv) is not None:
                skipped.append(app.name)
            else:
                self._items[app_id].setCheckState(0, Qt.CheckState.Checked)
                picked.append(app.name)
        if picked:
            self.controller.say(Level.INFO, f"Chọn thêm: {', '.join(picked)}.")
        if skipped:
            self.controller.say(Level.INFO, f"Không chọn thêm (đã cài, không cài được hoặc không có trong danh mục): "
                                            f"{', '.join(skipped)}.")

    def _info_text(self) -> str:
        state = self.state
        senv = state.senv
        installed = sum(1 for detection in state.detections.values() if detection.installed)
        self.info.setToolTip(f"Danh mục: {state.catalog.source}")
        parts = [
            f"{len(state.catalog.apps)} ứng dụng trong danh mục, máy đã có {installed}",
            f"winget: {'có' if senv.winget else 'không có'}",
        ]
        if state.catalog.errors:
            parts.append(f"{len(state.catalog.errors)} mục khai báo sai (xem khung log)")
        if not senv.is_admin:
            parts.append("cần mở tool bằng quyền admin để cài")
        return " · ".join(parts)

    # ------------------------------------------------------------ kho bộ cài

    def _update_store(self) -> None:
        source, state = self.app.software, self.state
        if state is None:
            return
        root = state.senv.share_root  # kho của lượt quét vừa xong
        if not root:
            self.store.show_state(
                "warn", "Chưa có kho bộ cài",
                "Office, Symantec và bộ cài riêng của công ty cần kho bộ cài: thư mục SOFT trên ổ SSD, hoặc thư mục "
                "chung trên mạng. Phần mềm tải từ Internet vẫn cài được.", "Chọn kho…", primary=True)
            return
        if not state.senv.share_ok:
            self.store.show_state("bad", f"Không vào được kho bộ cài {root}",
                                  "Kiểm tra ổ SSD còn cắm, hoặc mạng tới thư mục chung.", "Chọn kho khác…", primary=True)
            return
        catalog = state.catalog
        share_apps = [app for app in catalog.apps if app.source == "share"]
        have = len(share_apps) - len(state.senv.missing)
        own = Path(catalog.source) != catalog_module.BUNDLED_FILE
        text = f"{have}/{len(share_apps)} bộ cài trong danh mục có sẵn · " + (
            "dùng danh mục của kho (config\\apps.yaml)" if own
            else "kho chưa có config\\apps.yaml, đang dùng danh mục mặc định của tool")
        title = f"{STORE_TITLES.get(source.kind, 'Kho bộ cài')}: {root}"
        self.store.show_state("ok" if have == len(share_apps) else "warn", title, text, "Đổi kho…")

    def choose_store(self) -> None:
        start = self.app.software.root or str(paths.app_root())
        folder = QFileDialog.getExistingDirectory(self, "Chọn thư mục kho bộ cài (thư mục SOFT)", start)
        if not folder:
            return
        folder = os.path.normpath(folder)
        has_catalog, installers = catalog_module.inspect_store(folder)
        if not has_catalog and installers == 0:
            answer = QMessageBox.question(
                self, "Kho bộ cài",
                f"{folder}\n\nThư mục này không có config\\apps.yaml và không có file cài (.iso, .msi, .exe). "
                "Kho bộ cài thường là thư mục SOFT trên ổ SSD. Vẫn dùng thư mục này?")
            if answer != QMessageBox.StandardButton.Yes:
                return
        try:
            prefs.put(prefs.SOFTWARE_ROOT, folder)
        except OSError as exc:
            self.controller.say(Level.WARN, f"Không lưu được kho đã chọn cho lần sau: {exc}")
        self.app.use_software_root(folder)
        self.controller.say(Level.INFO, f"Đổi kho bộ cài: {folder}"
                                        + ("" if has_catalog else " (chưa có config\\apps.yaml, dùng danh mục mặc định)"))
        self.store.show_state("info", f"Đang kiểm tra kho bộ cài {folder}…")
        self.rescan()

    # ------------------------------------------------------------ nhóm chọn một (Office)

    def _choice_note(self, app: App) -> tuple[str, bool, str]:
        """(ghi chú trên thẻ, chọn được không, chú thích đầy đủ)."""
        state = self.state
        senv = state.senv
        _, extra = short_name(app.name)
        detection = state.detections[app.id]
        if detection.installed:
            version = f" {detection.version}" if detection.version else ""
            return f"Đã cài{version}", False, detection.matched
        reason = blocked_reason(app, senv, remove_conflicts=True)
        if reason:
            conflict = dict(senv.conflicts).get(app.id)
            if not senv.is_admin:
                short = "Cần quyền admin"
            elif conflict and app.id not in senv.removable:
                short = f"Máy đang có {conflict}"
            elif app.source == "share" and not senv.share_root:
                short = "Cần kho bộ cài"
            elif app.source == "share" and not senv.share_ok:
                short = "Không vào được kho bộ cài"
            elif app.id in senv.missing:
                short = "Không thấy bộ cài trong kho"
            elif app.source == "winget" and not senv.winget:
                short = "Chưa có winget"
            else:
                short = "Không cài được"
            return short, False, reason
        where = "Cài từ kho bộ cài" if app.source == "share" else "Tải từ Internet"
        return " · ".join(part for part in (extra, where) if part), True, app.description

    def _build_choices(self) -> None:
        previous = {choice: group.selected() for choice, group in self.choice_groups.items()}
        while self.choice_area.count():
            widget = self.choice_area.takeAt(0).widget()
            if widget is not None:
                widget.deleteLater()
        self.choice_groups = {}
        catalog = self.state.catalog
        for choice, apps in catalog.choices().items():
            installed = [app for app in apps if self.state.detections[app.id].installed]
            group = ChoiceGroup(catalog.choice_title(choice), "Chọn một bản. Bản trong kho cài im lặng và tự kích hoạt.")
            options = [ChoiceOption("", "Không cài", f"Giữ {short_name(installed[0].name)[0]}" if installed
                                    else "Không cài bản nào")]
            for app in apps:
                note, enabled, tooltip = self._choice_note(app)
                options.append(ChoiceOption(app.id, short_name(app.name)[0], note, enabled,
                                            f"{app.name}\n{tooltip}".strip()))
            group.set_options(options, previous.get(choice, ""))
            group.changed.connect(lambda _key, name=choice: self._choice_changed(name))
            group.warning_check.toggled.connect(lambda _checked: self._update_summary())
            self.choice_groups[choice] = group
            self.choice_area.addWidget(group)
            self._choice_changed(choice)

    def _choice_changed(self, choice: str) -> None:
        group = self.choice_groups[choice]
        key = group.selected()
        senv = self.state.senv
        conflict = dict(senv.conflicts).get(key)
        if key and conflict and key in senv.removable and any(action.id == REMOVE_C2R for action in self.app.actions):
            name = short_name(self.state.catalog.app(key).name)[0]
            group.show_warning(
                f"Máy đang có <b>{conflict}</b> (Office cài sẵn kiểu Click-to-Run), {name} không cài chung được. "
                f"Tool sẽ gỡ bản cài sẵn trước, cài các phần mềm khác, rồi cài {name} sau cùng.",
                "Gỡ trước khi cài")
        else:
            group.hide_warning()
        self._update_summary()

    def _remove_first(self, app: App) -> bool:
        """Lượt cài có gỡ Office Click-to-Run trước cho ứng dụng này không (IT để tick "Gỡ trước khi cài")."""
        group = self.choice_groups.get(app.choice) if app.choice else None
        if group is None or group.warning.isHidden() or group.warning_check.isHidden():
            return False
        return group.selected() == app.id and group.warning_check.isChecked()

    def chosen_apps(self) -> list[App]:
        """Ứng dụng đang chọn trong các nhóm chọn một (ví dụ bản Office)."""
        if self.state is None:
            return []
        return [app for group in self.choice_groups.values()
                if (key := group.selected()) and (app := self.state.catalog.app(key)) is not None]

    # ------------------------------------------------------------ cây

    def _populate(self) -> None:
        state = self.state
        checked = {app.id for app in self.checked_apps()}
        current_profile = self.profile.currentData()
        self.tree.blockSignals(True)
        self.tree.clear()
        self._items.clear()
        groups: dict[str, QTreeWidgetItem] = {}
        bold = QFont()
        bold.setBold(True)
        for app in state.catalog.apps:
            if app.choice:
                continue
            parent = groups.get(app.group)
            if parent is None:
                parent = QTreeWidgetItem(self.tree, [app.group])
                parent.setFlags(parent.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsAutoTristate)
                parent.setCheckState(0, Qt.CheckState.Unchecked)
                parent.setFont(0, bold)
                groups[app.group] = parent
            item = QTreeWidgetItem(parent, [app.name, app.source_label, ""])
            item.setData(0, APP_ID_ROLE, app.id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(0, Qt.CheckState.Checked if app.id in checked else Qt.CheckState.Unchecked)
            item.setToolTip(0, app.description or app.name)
            self._items[app.id] = item
        self.tree.expandAll()
        self.tree.blockSignals(False)

        self.profile.clear()
        for profile in state.catalog.profiles:
            self.profile.addItem(profile.name, profile.id)
        if current_profile is not None:
            index = self.profile.findData(current_profile)
            if index >= 0:
                self.profile.setCurrentIndex(index)
        self._build_choices()
        self.refresh_states()
        self._filter(self.search.text())
        self._update_summary()

    def app_status(self, app: App) -> tuple[str, str, str]:
        """(chữ, loại màu, chú thích) cho cột Trạng thái."""
        state = self.state
        last = self.controller.last_results.get(f"app.{app.id}")
        if last is not None and last.status is Status.FAILED:
            return f"✖ Lỗi {last.finished_at:%H:%M}", "error", last.message
        detection = state.detections.get(app.id)
        if detection is not None and detection.installed:
            version = f" {detection.version}" if detection.version else ""
            return f"Đã cài{version}", "on", detection.matched
        reason = blocked_reason(app, state.senv)
        if reason:
            return "Không cài được", "blocked", reason
        if last is not None and last.status is Status.OK:
            return f"✔ Cài xong {last.finished_at:%H:%M}", "ok", "Chưa thấy trong Programs and Features, bấm Kiểm tra lại"
        return "Chưa cài", "off", ""

    def refresh_states(self) -> None:
        if self.state is None:
            return
        self.tree.blockSignals(True)
        for app_id, item in self._items.items():
            text, kind, note = self.app_status(self.state.catalog.app(app_id))
            item.setText(2, text)
            item.setToolTip(2, note)
            item.setForeground(2, QBrush(QColor(STATE_COLORS.get(kind, "#64748b"))))
        self.tree.blockSignals(False)

    def _filter(self, text: str) -> None:
        needle = fold(text.strip())
        for index in range(self.tree.topLevelItemCount()):
            group = self.tree.topLevelItem(index)
            group_match = needle in fold(group.text(0))
            visible = 0
            for child_index in range(group.childCount()):
                child = group.child(child_index)
                app = self.state.catalog.app(child.data(0, APP_ID_ROLE))
                show = not needle or group_match or needle in fold(f"{app.name} {app.id} {app.description}")
                child.setHidden(not show)
                visible += show
            group.setHidden(visible == 0)

    # ------------------------------------------------------------ chọn

    def checked_apps(self) -> list[App]:
        """Ứng dụng đang tick trong cây (không gồm nhóm chọn một)."""
        if self.state is None:
            return []
        return [app for app in self.state.catalog.apps
                if (item := self._items.get(app.id)) is not None and item.checkState(0) == Qt.CheckState.Checked]

    def selected_apps(self) -> list[App]:
        return self.chosen_apps() + self.checked_apps()

    def failed_apps(self) -> list[App]:
        if self.state is None:
            return []
        return [app for app in self.state.catalog.apps
                if (last := self.controller.last_results.get(f"app.{app.id}")) is not None
                and last.status is Status.FAILED]

    def pick_profile(self) -> None:
        if self.state is None or self.profile.currentData() is None:
            return
        profile_apps = self.state.catalog.profile_apps(self.profile.currentData())
        wanted = {app.id for app in profile_apps}
        picked = 0
        self.tree.blockSignals(True)
        for app_id, item in self._items.items():
            app = self.state.catalog.app(app_id)
            installed = self.state.detections[app_id].installed
            check = app_id in wanted and not installed and blocked_reason(app, self.state.senv) is None
            item.setCheckState(0, Qt.CheckState.Checked if check else Qt.CheckState.Unchecked)
            picked += check
        self.tree.blockSignals(False)
        for choice, group in self.choice_groups.items():
            options = [app.id for app in profile_apps if app.choice == choice]
            if not any(group.select(app_id) for app_id in options):
                group.select("")
            picked += bool(group.selected())
        skipped = len(wanted) - picked
        note = f", bỏ qua {skipped} ứng dụng đã cài hoặc không cài được" if skipped > 0 else ""
        self.controller.say(Level.INFO, f"Profile {self.profile.currentText()}: chọn {picked} ứng dụng{note}.")
        self._update_summary()

    def _update_summary(self) -> None:
        chosen, checked = self.chosen_apps(), self.checked_apps()
        total = len(chosen) + len(checked)
        if total == 0:
            self.summary.setText("Chưa chọn gì")
        else:
            office = f" (có {', '.join(short_name(app.name)[0] for app in chosen)})" if chosen else ""
            self.summary.setText(f"Đã chọn {total} mục{office}")
        self.install_button.setText(f"Cài {total} mục" if total else "Cài")

    # ------------------------------------------------------------ cài

    def _split(self, apps: list[App]) -> tuple[list[App], list[tuple[App, str]]]:
        runnable, blocked = [], []
        for app in apps:
            reason = blocked_reason(app, self.state.senv, remove_conflicts=self._remove_first(app))
            if reason:
                blocked.append((app, reason))
            else:
                runnable.append(app)
        return runnable, blocked

    def plan(self, apps: list[App]) -> tuple[list, list[App], list[tuple[App, str]]]:
        """(các mục sẽ chạy, ứng dụng sẽ cài, ứng dụng bị bỏ qua kèm lý do).

        Có gỡ Office cài sẵn thì gỡ trước, cài các ứng dụng khác, ứng dụng cần gỡ trước cài sau cùng."""
        runnable, blocked = self._split(apps)
        share_root = self.state.senv.share_root
        late = [app for app in runnable if self._remove_first(app)]
        early = [app for app in runnable if app not in late]
        actions = []
        if late:
            actions.append(next(action for action in self.app.actions if action.id == REMOVE_C2R))
        actions += [install_action(app, share_root) for app in early + late]
        return actions, early + late, blocked

    def preview(self) -> None:
        apps = self.selected_apps()
        if not apps:
            QMessageBox.information(self, "Chưa chọn", "Chọn bản Office hoặc tick các ứng dụng cần xem trước.")
            return
        self.controller.preview(self.plan(apps)[0])

    def install(self, apps: list[App]) -> None:
        if self.state is None:
            return
        if not apps:
            QMessageBox.information(self, "Chưa chọn", "Chọn bản Office hoặc tick các ứng dụng cần cài.")
            return
        if self.controller.busy:
            QMessageBox.information(self, "Đang chạy", "Đang có việc chạy, chờ xong rồi bấm Cài.")
            return
        actions, runnable, blocked = self.plan(apps)
        for app, reason in blocked:
            self.controller.say(Level.WARN, f"Bỏ qua {app.name}: {reason}")
        if not runnable:
            QMessageBox.information(self, "Không cài được", "Không ứng dụng nào trong số đã chọn cài được trên máy này.")
            return
        names = "\n".join(f"• {app.name} ({app.source_label})" for app in runnable)
        notes = []
        if any(action.id == REMOVE_C2R for action in actions):
            notes.append("Trước khi cài: gỡ Office / Microsoft 365 cài sẵn trên máy (đóng Word, Excel, Outlook trước).")
        if blocked:
            notes.append(f"Bỏ qua {len(blocked)} mục không cài được (xem khung log).")
        if any(app.source == "winget" for app in runnable):
            notes.append("Ứng dụng tải từ Internet cần mạng.")
        note = ("\n\n" + "\n".join(notes)) if notes else ""
        answer = QMessageBox.question(
            self, "Cài phần mềm",
            f"Cài lần lượt {len(runnable)} ứng dụng:\n{names}{note}\n\nCó thể mất nhiều phút. Tiếp tục?",
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.progress.watch("Cài phần mềm")
            self.views.setCurrentIndex(PROGRESS_VIEW)
            self.controller.run(actions)

    def _result_hint(self, result: BatchResult) -> str:
        removed = any(item.action.id == REMOVE_C2R and item.status is Status.OK for item in result.results)
        failed = any(item.action.id.startswith("app.") and item.status is Status.FAILED for item in result.results)
        if removed and failed:
            return "Vừa gỡ Office cài sẵn: khởi động lại máy rồi vào lại trang này bấm Thử lại mục lỗi."
        return ""

    def _run_finished(self, result: object) -> None:
        if not isinstance(result, BatchResult):
            return
        if any(item.action.id.startswith("app.") or item.action.id == REMOVE_C2R for item in result.results):
            self.rescan()
        else:
            self.refresh_states()

    def _update_buttons(self) -> None:
        ready = self.state is not None and not self.loading and not self.controller.busy
        for button in (self.install_button, self.preview_button, self.pick_button):
            button.setEnabled(ready)
        self.retry_button.setEnabled(ready and bool(self.failed_apps()))
        self.rescan_button.setEnabled(not self.loading and not self.controller.busy)
        self.store.button.setEnabled(not self.controller.busy)
