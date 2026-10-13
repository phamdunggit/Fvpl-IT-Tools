"""Trạng thái wizard Cài máy mới, lưu ra file để chạy tiếp sau khi khởi động lại (PLAN.md mục 5.2, bước 2–3).

File nằm trong thư mục dữ liệu của tool (%ProgramData%\\FVPL-ITTools\\newpc-wizard.json). Không chứa mật khẩu.

Tool có thể đang chạy từ USB / SSD mà sau khi khởi động lại ổ đó đã rút ra. Vì vậy trước khi join, tool chép
chính nó vào %ProgramData%\\FVPL-ITTools\\app và hẹn một tác vụ mở bản chép đó (kèm --resume) khi một admin
đăng nhập. `origin` ghi thư mục tool lúc đầu để tìm lại kho SOFT nếu ổ SSD vẫn cắm đúng chỗ.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from ..core import paths

log = logging.getLogger(__name__)

STATE_FILE = "newpc-wizard.json"
RESUME_TASK = "FVPL-ITTools-TiepTucCaiMay"
EXE_NAME = "FVPL-ITTools.exe"

# (khoá, tên hiện ở danh sách bước)
STEPS = (
    ("check", "0. Kiểm tra trước"),
    ("info", "1. Thông tin máy"),
    ("join", "2. Đổi tên + join domain"),
    ("after", "3. Sau khởi động lại"),
    ("software", "4. Cài phần mềm"),
    ("config", "5. Cấu hình chuẩn"),
    ("update", "6. Driver + Windows Update"),
    ("report", "7. Báo cáo"),
)
STEP_NAMES = dict(STEPS)
STATUS_LABELS = {"ok": "Xong", "failed": "Lỗi", "skipped": "Bỏ qua"}


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


@dataclass
class StepRecord:
    status: str          # ok | failed | skipped
    time: str
    note: str = ""

    @property
    def time_label(self) -> str:
        try:
            return datetime.fromisoformat(self.time).strftime("%d/%m/%Y %H:%M")
        except ValueError:
            return self.time


@dataclass
class WizardState:
    department: str = ""
    computer_name: str = ""
    primary_user: str = ""       # người dùng chính của máy, đưa vào báo cáo
    profile: str = ""            # profile phần mềm
    extra_apps: list[str] = field(default_factory=list)  # phần mềm thêm ngoài profile (ví dụ bản Office)
    template: str = ""           # mẫu đã dùng, nếu có
    origin: str = ""             # thư mục tool lúc bắt đầu (USB / SSD)
    started: str = field(default_factory=_now)
    finished: str = ""
    steps: dict[str, StepRecord] = field(default_factory=dict)

    def mark(self, key: str, status: str, note: str = "") -> None:
        self.steps[key] = StepRecord(status, _now(), note)

    def status(self, key: str) -> str:
        record = self.steps.get(key)
        return record.status if record else ""

    def next_step(self) -> str:
        """Bước nên mở: bước đầu tiên chưa xong hoặc chưa bỏ qua (không tính bước 0)."""
        for key, _name in STEPS[1:]:
            if self.status(key) not in ("ok", "skipped"):
                return key
        return "report"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> WizardState:
        known = {name for name in cls.__dataclass_fields__}
        values = {key: value for key, value in data.items() if key in known and key not in ("steps", "extra_apps")}
        state = cls(**{key: str(value) for key, value in values.items()})
        apps = data.get("extra_apps")
        state.extra_apps = [str(app) for app in apps] if isinstance(apps, list) else []
        for key, record in (data.get("steps") or {}).items():
            if isinstance(record, dict) and record.get("status"):
                state.steps[str(key)] = StepRecord(str(record["status"]), str(record.get("time", "")),
                                                   str(record.get("note", "")))
        return state


def state_path() -> Path:
    return paths.state_dir() / STATE_FILE


def load() -> WizardState | None:
    file = state_path()
    if not file.is_file():
        return None
    try:
        return WizardState.from_dict(json.loads(file.read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError):
        log.exception("Không đọc được %s, coi như chưa có wizard đang dở", file)
        return None


def save(state: WizardState) -> None:
    file = state_path()
    temp = file.with_suffix(".tmp")
    temp.write_text(json.dumps(state.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, file)


def clear() -> None:
    try:
        state_path().unlink()
    except FileNotFoundError:
        pass


def active() -> WizardState | None:
    """Wizard đang làm dở (có file, chưa kết thúc)."""
    state = load()
    return state if state is not None and not state.finished else None


# ---------------------------------------------------------------- chạy tiếp sau khởi động lại


def app_copy_dir() -> Path:
    return paths.app_copy_dir()


def resume_command() -> tuple[str, str]:
    """(chương trình, tham số) của tác vụ mở lại tool sau khi khởi động lại."""
    if paths.is_frozen():
        return str(app_copy_dir() / EXE_NAME), "--resume"
    # Chạy từ mã nguồn (máy dev / VM thử): mở lại bằng chính Python đang chạy.
    return sys.executable, "-m fvpl_ittools --resume"


def origin_soft(state: WizardState | None) -> Path | None:
    """Thư mục SOFT cạnh tool lúc bắt đầu wizard (bản SSD), nếu ổ đó vẫn cắm."""
    if state is None or not state.origin:
        return None
    folder = Path(state.origin) / "SOFT"
    return folder if folder.is_dir() else None
