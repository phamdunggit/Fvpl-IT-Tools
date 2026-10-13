"""Trang Tiện ích: mở nhanh panel hệ thống, công cụ mạng (ping, tracert, nslookup, kiểm tra cổng)."""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass

from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ...actions.loader import parse_action
from ...actions.model import Action
from ...app import AppContext
from ...core import shell
from ...core.executor import Level
from ..controller import RunController
from ..widgets import page_header
from .actions_page import ActionsPage


@dataclass(frozen=True)
class Shortcut:
    name: str
    target: tuple[str, ...]  # chương trình + tham số; chương trình không có đường dẫn thì lấy trong System32
    note: str = ""

    @property
    def is_uri(self) -> bool:
        return _is_uri(self.target[0])


def _is_uri(text: str) -> bool:
    """ms-settings:..., windowsdefender: là URI, mở bằng chương trình Windows gán sẵn."""
    return ":" in text and not os.path.isabs(text)


SHORTCUTS: dict[str, list[Shortcut]] = {
    "Hệ thống": [
        Shortcut("Control Panel", ("control.exe",)),
        Shortcut("System Properties", ("SystemPropertiesAdvanced.exe",), "Tên máy, domain, biến môi trường, hiệu năng"),
        Shortcut("Computer Management", ("mmc.exe", "compmgmt.msc")),
        Shortcut("Device Manager", ("mmc.exe", "devmgmt.msc")),
        Shortcut("Services", ("mmc.exe", "services.msc")),
        Shortcut("Event Viewer", ("mmc.exe", "eventvwr.msc")),
        Shortcut("Task Scheduler", ("mmc.exe", "taskschd.msc")),
        Shortcut("Task Manager", ("taskmgr.exe",)),
        Shortcut("Resource Monitor", ("resmon.exe",)),
        Shortcut("System Information", ("msinfo32.exe",)),
        Shortcut("Registry Editor", ("regedit.exe",)),
        Shortcut("Power Options", ("control.exe", "powercfg.cpl")),
        Shortcut("Windows Update", ("ms-settings:windowsupdate",)),
    ],
    "Mạng": [
        Shortcut("Network Connections", ("control.exe", "ncpa.cpl")),
        Shortcut("Network and Sharing Center", ("control.exe", "/name", "Microsoft.NetworkAndSharingCenter")),
        Shortcut("Internet Options", ("control.exe", "inetcpl.cpl"), "Proxy của tài khoản đang chạy tool"),
        Shortcut("Firewall nâng cao", ("mmc.exe", "wf.msc")),
    ],
    "Ổ đĩa, máy in, phần mềm": [
        Shortcut("Disk Management", ("mmc.exe", "diskmgmt.msc")),
        Shortcut("Devices and Printers", ("control.exe", "printers")),
        Shortcut("Print Management", ("mmc.exe", "printmanagement.msc"), "Không có trên bản Home"),
        Shortcut("Programs and Features", ("control.exe", "appwiz.cpl")),
        Shortcut("Windows Features", ("optionalfeatures.exe",)),
        Shortcut("Sound", ("control.exe", "mmsys.cpl")),
    ],
    "Người dùng và bảo mật": [
        Shortcut("Local Users and Groups", ("mmc.exe", "lusrmgr.msc"), "Không có trên bản Home"),
        Shortcut("User Accounts (netplwiz)", ("netplwiz.exe",)),
        Shortcut("Credential Manager", ("control.exe", "/name", "Microsoft.CredentialManager"),
                 "Mật khẩu đã lưu của tài khoản đang chạy tool"),
        Shortcut("Group Policy (gpedit)", ("mmc.exe", "gpedit.msc"), "Không có trên bản Home"),
        Shortcut("Certificates của máy", ("mmc.exe", "certlm.msc")),
        Shortcut("Windows Security", ("windowsdefender:",)),
    ],
}


def resolve(shortcut: Shortcut) -> list[str] | None:
    """Dòng lệnh đầy đủ, hoặc None nếu máy này không có công cụ đó (ví dụ gpedit trên bản Home)."""
    if shortcut.is_uri:
        return list(shortcut.target)
    system = shell.system_dir()
    # Phần lớn nằm trong System32, riêng regedit.exe nằm ở thư mục Windows.
    folders = (system, os.path.dirname(system))
    program = next((os.path.join(folder, shortcut.target[0]) for folder in folders
                    if os.path.exists(os.path.join(folder, shortcut.target[0]))), None)
    args = list(shortcut.target[1:])
    if program is None:
        return None
    if args and args[0].endswith(".msc"):
        console = os.path.join(system, args[0])
        if not os.path.exists(console):
            return None
        args[0] = console
    return [program, *args]


def launch(command: list[str]) -> None:
    if len(command) == 1 and _is_uri(command[0]):
        os.startfile(command[0])  # noqa: S606 - URI cố định trong SHORTCUTS
        return
    subprocess.Popen(command, cwd=shell.system_dir())


# ---------------------------------------------------------------- công cụ mạng

_HOST = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.\-_:]{0,252}$")


def valid_host(text: str) -> bool:
    """Tên máy, tên miền, IPv4 hoặc IPv6. Chặn mọi ký tự khác để không chèn được lệnh vào cmd."""
    return bool(_HOST.match(text))


def network_action(tool: str, host: str, port: int = 0) -> Action:
    """Mục chạy một lần cho công cụ mạng. `host` phải qua valid_host trước."""
    if not valid_host(host):
        raise ValueError(f"Địa chỉ không hợp lệ: {host!r}")
    steps = {
        "ping": ("Ping", [{"cmd": f"ping -n 4 {host}", "messages": {1: "Không ping được"}}]),
        "tracert": ("Tracert", [{"cmd": f"tracert -d -h 20 -w 1000 {host}", "timeout": 300}]),
        "nslookup": ("Nslookup", [{"cmd": f"nslookup {host}", "messages": {1: "Không phân giải được tên này"}}]),
        "port": (f"Kiểm tra cổng {port}", [{
            "powershell": (
                f"$target = {shell.ps_quote(host)}\n"
                f"if (Test-Port $target {int(port)} 3000) {{ Write-Ok \"$target mở cổng {int(port)}\" }}\n"
                f"else {{ Write-Bad \"Không kết nối được cổng {int(port)} của $target\" }}\n"
                "Exit-Checks"
            ),
            "messages": {2: "Cổng không mở hoặc bị chặn"},
        }]),
    }
    title, apply = steps[tool]
    return parse_action({
        "id": f"util.{tool}", "name": f"{title} {host}", "category": "Công cụ mạng", "page": "utilities",
        "admin": False, "description": "Chạy từ trang Tiện ích.", "apply": apply,
    })


class ShortcutsPanel(QWidget):
    def __init__(self, controller: RunController):
        super().__init__()
        self.controller = controller
        self.buttons: dict[str, QPushButton] = {}
        self.setObjectName("ShortcutsPanel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 12, 12, 8)
        layout.setSpacing(10)
        note = QLabel("Mở bằng quyền của tool (thường là quyền admin). Mục theo người dùng như Credential Manager, "
                      "Internet Options sẽ là của tài khoản đang chạy tool.")
        note.setObjectName("PageSubtitle")
        note.setWordWrap(True)
        layout.addWidget(note)
        for group, items in SHORTCUTS.items():
            title = QLabel(group)
            title.setObjectName("SectionLabel")
            layout.addWidget(title)
            grid = QGridLayout()
            grid.setHorizontalSpacing(8)
            grid.setVerticalSpacing(8)
            for index, shortcut in enumerate(items):
                button = QPushButton(shortcut.name)
                command = resolve(shortcut)
                button.setEnabled(command is not None)
                button.setToolTip(shortcut.note if command else "Máy này không có công cụ này")
                button.clicked.connect(lambda _checked=False, item=shortcut: self.open(item))
                grid.addWidget(button, index // 4, index % 4)
                self.buttons[shortcut.name] = button
            for column in range(4):
                grid.setColumnStretch(column, 1)
            layout.addLayout(grid)
        layout.addStretch(1)

    def open(self, shortcut: Shortcut) -> None:
        command = resolve(shortcut)
        if command is None:
            return
        try:
            launch(command)
        except OSError as exc:
            self.controller.say(Level.ERROR, f"Không mở được {shortcut.name}: {exc}")
            return
        self.controller.say(Level.INFO, f"Đã mở {shortcut.name}.")


class NetworkToolsPanel(QWidget):
    def __init__(self, controller: RunController):
        super().__init__()
        self.controller = controller
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(10)
        note = QLabel("Kết quả hiện ở khung log bên dưới. Muốn chẩn đoán toàn bộ (gateway, DNS, DC, Internet) "
                      "thì dùng mục Chẩn đoán mạng ở trang Sửa lỗi.")
        note.setObjectName("PageSubtitle")
        note.setWordWrap(True)
        layout.addWidget(note)

        card = QFrame()
        card.setObjectName("Card")
        form = QGridLayout(card)
        form.setContentsMargins(16, 14, 16, 14)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(10)
        self.host = QLineEdit()
        self.host.setPlaceholderText("Tên máy, tên miền hoặc IP, ví dụ 8.8.8.8 hoặc www.microsoft.com")
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(443)
        self.error = QLabel()
        self.error.setObjectName("Note")
        form.addWidget(QLabel("Địa chỉ"), 0, 0)
        form.addWidget(self.host, 0, 1, 1, 4)
        buttons = QHBoxLayout()
        self.tool_buttons: dict[str, QPushButton] = {}
        for tool, label in (("ping", "Ping"), ("tracert", "Tracert"), ("nslookup", "Nslookup")):
            button = QPushButton(label)
            button.clicked.connect(lambda _checked=False, name=tool: self.run(name))
            buttons.addWidget(button)
            self.tool_buttons[tool] = button
        buttons.addSpacing(16)
        buttons.addWidget(QLabel("Cổng"))
        buttons.addWidget(self.port)
        port_button = QPushButton("Kiểm tra cổng")
        port_button.clicked.connect(lambda: self.run("port"))
        buttons.addWidget(port_button)
        self.tool_buttons["port"] = port_button
        buttons.addStretch(1)
        form.addLayout(buttons, 1, 1, 1, 4)
        form.addWidget(self.error, 2, 1, 1, 4)
        form.setColumnStretch(1, 1)
        layout.addWidget(card)
        layout.addStretch(1)

        self.host.returnPressed.connect(lambda: self.run("ping"))
        controller.busy_changed.connect(self._busy_changed)

    def run(self, tool: str) -> None:
        host = self.host.text().strip()
        if not valid_host(host):
            self.error.setText("Nhập tên máy, tên miền hoặc IP (chỉ gồm chữ không dấu, số, dấu chấm, gạch ngang, dấu hai chấm).")
            return
        self.error.setText("")
        self.controller.run([network_action(tool, host, self.port.value())])

    def _busy_changed(self, busy: bool) -> None:
        for button in self.tool_buttons.values():
            button.setEnabled(not busy)


class UtilitiesPage(QWidget):
    def __init__(self, app: AppContext, controller: RunController):
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 12)
        root.setSpacing(10)
        page_header(root, "Tiện ích", "Mở nhanh các công cụ quản trị của Windows và công cụ mạng cho IT.")
        self.tabs = QTabWidget()
        self.shortcuts = ShortcutsPanel(controller)
        self.network = NetworkToolsPanel(controller)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(self.shortcuts)
        self.tabs.addTab(scroll, "Mở nhanh")
        self.tabs.addTab(self.network, "Công cụ mạng")
        if any(action.page == "utilities" for action in app.actions):
            self.tabs.addTab(ActionsPage("utilities", "", "", "", app, controller, show_header=False), "Mục khác")
        root.addWidget(self.tabs, 1)
