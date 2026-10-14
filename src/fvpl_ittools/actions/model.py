"""Mô hình dữ liệu của một mục (action) và các bước bên trong. Xem ví dụ ở PLAN.md mục 6.3."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class Risk(str, Enum):
    SAFE = "safe"
    CAUTION = "caution"
    ADVANCED = "advanced"

    @property
    def label(self) -> str:
        return RISK_LABELS[self]


RISK_LABELS = {Risk.SAFE: "An toàn", Risk.CAUTION: "Cẩn thận", Risk.ADVANCED: "Nâng cao"}


class Scope(str, Enum):
    MACHINE = "machine"
    USER = "user"


class UndoMode(str, Enum):
    AUTO = "auto"    # trả registry về giá trị đã sao lưu
    NONE = "none"    # không hoàn tác được
    STEPS = "steps"  # chạy các bước hoàn tác khai báo riêng


PAGES = ("fixes", "printers", "optimize", "config", "utilities")

# Các thao tác viết bằng Python, gọi bằng `builtin: <tên>` hoặc `after: [<tên>]`.
BUILTIN_NAMES = {
    "restart_explorer": "Khởi động lại Explorer",
    "rebuild_icon_cache": "Tắt Explorer, xoá cache icon và thumbnail, mở lại Explorer",
    "restart_spooler": "Khởi động lại Print Spooler",
    "notify_environment": "Báo cho Windows biết biến môi trường đã đổi",
}

SERVICE_ACTIONS = ("start", "stop", "restart")
DEFAULT_OK_CODES = (0,)
DEFAULT_REBOOT_CODES = (3010, 1641)


@dataclass(frozen=True, kw_only=True)
class StepBase:
    timeout: float | None = None
    ok_codes: tuple[int, ...] = DEFAULT_OK_CODES
    reboot_codes: tuple[int, ...] = DEFAULT_REBOOT_CODES
    messages: tuple[tuple[int, str], ...] = ()  # (mã thoát, giải thích) hiện thay cho "mã lỗi N"

    def message_for(self, code: int) -> str | None:
        return dict(self.messages).get(code)


@dataclass(frozen=True, kw_only=True)
class CmdStep(StepBase):
    command: str
    encoding: str = "auto"


@dataclass(frozen=True, kw_only=True)
class PowerShellStep(StepBase):
    script: str
    encoding: str = "auto"


@dataclass(frozen=True, kw_only=True)
class RegistryStep(StepBase):
    key: str
    name: str
    type: str | None = None
    value: Any = None
    delete: bool = False


@dataclass(frozen=True, kw_only=True)
class ServiceStep(StepBase):
    service: str
    action: str


@dataclass(frozen=True, kw_only=True)
class BuiltinStep(StepBase):
    name: str


Step = CmdStep | PowerShellStep | RegistryStep | ServiceStep | BuiltinStep


@dataclass(frozen=True)
class RegistryCheck:
    """Đọc trạng thái hiện tại: giá trị bằng `on_value` nghĩa là mục đã được áp dụng ("✔ Đã áp dụng")."""
    key: str
    name: str
    on_value: Any


@dataclass(frozen=True)
class GpoRef:
    """Giá trị policy mà nếu có mặt thì coi như GPO đang quản lý mục này."""
    key: str
    name: str


@dataclass(frozen=True, kw_only=True)
class Action:
    id: str
    name: str
    category: str
    apply: tuple[Step, ...]
    page: str = "fixes"
    risk: Risk = Risk.SAFE
    scope: Scope = Scope.MACHINE
    admin: bool = True
    reboot: bool = False
    min_build: int | None = None
    max_build: int | None = None
    description: str = ""
    undo_mode: UndoMode = UndoMode.NONE
    undo_steps: tuple[Step, ...] = ()
    check: RegistryCheck | None = None
    after: tuple[str, ...] = ()
    gpo: tuple[GpoRef, ...] = ()
    needs_credential: str | None = None
    requires_domain: bool = False
    keywords: tuple[str, ...] = ()  # từ người dùng hay gõ khi tìm (Ctrl+K): từ đồng nghĩa, mã lỗi
    basic_name: str = ""  # tên dễ hiểu hiện ở chế độ Cơ bản, rỗng thì dùng name

    def title(self, basic: bool = False) -> str:
        return self.basic_name if basic and self.basic_name else self.name
    source: str = ""

    def supports_build(self, build: int) -> bool:
        if self.min_build is not None and build < self.min_build:
            return False
        if self.max_build is not None and build > self.max_build:
            return False
        return True

    @property
    def can_undo(self) -> bool:
        return self.undo_mode is not UndoMode.NONE


@dataclass(frozen=True, kw_only=True)
class Pack:
    """Gói: chạy lần lượt nhiều mục. Gói sửa nhanh dừng khi một mục lỗi; gói cấu hình thì làm tiếp."""
    id: str
    name: str
    description: str
    actions: tuple[str, ...]
    page: str = "fixes"
    stop_on_error: bool = True
    source: str = ""
