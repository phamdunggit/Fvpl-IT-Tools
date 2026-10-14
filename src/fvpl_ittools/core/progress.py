"""Tiến độ của một lượt chạy: mục thứ mấy / tổng mấy, phần trăm mục đang chạy (KE-HOACH-GIAO-DIEN.md mục 5.6).

Executor phát `BatchStarted` khi bắt đầu lượt và `ItemUpdate` khi một mục bắt đầu, đổi phần trăm hay xong.
Phần trăm đọc từ output đang chạy:
- winget: "45.2 MB / 112 MB", thanh "██▒▒ 45%";
- DISM, SFC: "[=====  23.4%  ]"; robocopy: " 45%";
- script của tool: dòng `##PROGRESS 45 Đang tải về` (`##PROGRESS - chữ` khi chỉ đổi giai đoạn).
Chỉ nhận dòng chỉ có thanh / số phần trăm, để số % trong câu thường (ví dụ "ổ C còn 5%") không làm nhảy thanh.
Bộ cài không in phần trăm (MSI, EXE im lặng) thì giao diện hiện thanh chạy qua lại.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

MARK = "##PROGRESS"

RUNNING = "running"
OK = "ok"
FAILED = "failed"
SKIPPED = "skipped"
CANCELLED = "cancelled"
DONE_STATES = (OK, FAILED, SKIPPED, CANCELLED)

BATCH = -1  # ItemUpdate.index cho giai đoạn của cả lượt (ví dụ tạo điểm khôi phục)


@dataclass(frozen=True)
class PlanItem:
    action_id: str
    name: str
    skipped: str = ""  # lý do bỏ qua ngay từ đầu (thiếu quyền admin, chưa nhập tài khoản…)


@dataclass(frozen=True)
class BatchStarted:
    batch_id: int
    items: tuple[PlanItem, ...]


@dataclass(frozen=True)
class ItemUpdate:
    batch_id: int
    index: int                    # vị trí trong BatchStarted.items, BATCH cho giai đoạn của cả lượt
    state: str = RUNNING          # running | ok | failed | skipped | cancelled
    percent: float | None = None  # None: không biết (thanh chạy qua lại)
    phase: str = ""               # "Đang tải về", "Đang cài đặt"…
    message: str = ""             # lý do lỗi / bỏ qua
    reboot: bool = False


@dataclass(frozen=True)
class Hint:
    percent: float | None
    phase: str = ""
    hide: bool = False  # dòng đánh dấu của tool, không in ra log


_BAR = r"[\s\[\]=\-#|/\\█▓▒░■□━─>.]*"
_NUMBER = r"(\d+(?:[.,]\d+)?)"
_PERCENT_LINE = re.compile(rf"^{_BAR}{_NUMBER}\s?%{_BAR}$")
_SIZE_LINE = re.compile(rf"^{_BAR}{_NUMBER}\s*(B|KB|MB|GB)\s*/\s*{_NUMBER}\s*(B|KB|MB|GB){_BAR}$", re.IGNORECASE)
_MARK_LINE = re.compile(rf"^\s*{MARK}\s+(-|{_NUMBER})\s*(.*)$")
_UNITS = {"b": 1, "kb": 1024, "mb": 1024 ** 2, "gb": 1024 ** 3}

DOWNLOADING = "Đang tải về"
INSTALLING = "Đang cài đặt"
# Dòng output của winget (tiếng Anh / tiếng Việt) bắt đầu bằng chữ này → (giai đoạn, phần trăm mới hoặc None).
# Script của tool tự in dòng ##PROGRESS nên không cần đoán.
_PHASES: tuple[tuple[str, str, float | None], ...] = (
    ("downloading ", DOWNLOADING, 0.0),
    ("đang tải xuống", DOWNLOADING, 0.0),
    ("starting package install", INSTALLING, None),
    ("bắt đầu cài đặt gói", INSTALLING, None),
    ("successfully installed", "Cài xong", 100.0),
    ("đã cài đặt thành công", "Cài xong", 100.0),
)


WAITING = "waiting"
STATE_LABELS = {WAITING: "Chờ", RUNNING: "Đang chạy…", OK: "Xong", FAILED: "Lỗi", SKIPPED: "Bỏ qua",
                CANCELLED: "Đã dừng"}


@dataclass
class ItemState:
    item: PlanItem
    state: str = WAITING
    percent: float | None = None
    phase: str = ""
    message: str = ""
    reboot: bool = False


class Tracker:
    """Gom các sự kiện của một lượt để vẽ thanh tiến độ: mục nào xong, mục nào đang chạy, được bao nhiêu phần."""

    def __init__(self, started: BatchStarted):
        self.batch_id = started.batch_id
        self.items = [ItemState(item, SKIPPED, message=item.skipped) if item.skipped else ItemState(item)
                      for item in started.items]
        self.phase = ""  # giai đoạn của cả lượt, ví dụ tạo điểm khôi phục

    def apply(self, update: ItemUpdate) -> bool:
        """Cập nhật theo sự kiện; False nếu sự kiện không thuộc lượt này."""
        if update.batch_id != self.batch_id:
            return False
        if update.index == BATCH:
            self.phase = update.phase
            return True
        if not 0 <= update.index < len(self.items):
            return False
        self.phase = ""
        current = self.items[update.index]
        if update.state != current.state:
            current.percent, current.phase = None, ""
        current.state = update.state
        if update.state == RUNNING:
            if update.percent is not None or update.phase:
                current.percent = update.percent
            if update.phase:
                current.phase = update.phase
        else:
            current.message, current.reboot = update.message, update.reboot
        return True

    @property
    def total(self) -> int:
        return len(self.items)

    def count(self, state: str) -> int:
        return sum(1 for item in self.items if item.state == state)

    @property
    def finished(self) -> int:
        return sum(1 for item in self.items if item.state in DONE_STATES)

    @property
    def current(self) -> tuple[int, ItemState] | None:
        return next(((index, item) for index, item in enumerate(self.items) if item.state == RUNNING), None)

    @property
    def fraction(self) -> float:
        """Phần đã làm của cả lượt (0–1): mục đã xong + phần trăm của mục đang chạy."""
        if not self.items:
            return 1.0
        running = self.current
        part = (running[1].percent or 0) / 100 if running else 0
        return min(1.0, (self.finished + part) / self.total)

    def headline(self) -> str:
        """Ví dụ "Mục 4/8: Cài Google Chrome · Đang tải về 45%"."""
        running = self.current
        if running is None:
            return self.phase or ("Đang chuẩn bị…" if self.finished < self.total else "Xong")
        index, item = running
        detail = item.phase
        if item.percent is not None:
            detail = f"{detail} {item.percent:.0f}%".strip()
        return f"Mục {index + 1}/{self.total}: {item.item.name}" + (f" · {detail}" if detail else "")


def marker(phase: str, percent: float | None = None) -> str:
    """Dòng PowerShell in dấu tiến độ, ví dụ marker("Đang cài đặt") → Write-Output '##PROGRESS - Đang cài đặt'."""
    value = "-" if percent is None else f"{percent:g}"
    return "Write-Output '{0} {1} {2}'".format(MARK, value, phase.replace("'", "''"))


def _number(text: str) -> float:
    return float(text.replace(",", "."))


def parse(line: str) -> Hint | None:
    """Đọc phần trăm / giai đoạn từ một dòng output, None nếu dòng không nói gì về tiến độ."""
    text = line.strip()
    if not text:
        return None
    mark = _MARK_LINE.match(text)
    if mark:
        percent = None if mark.group(1) == "-" else max(0.0, min(100.0, _number(mark.group(2))))
        return Hint(percent, mark.group(3).strip(), hide=True)
    size = _SIZE_LINE.match(text)
    if size:
        done = _number(size.group(1)) * _UNITS[size.group(2).lower()]
        total = _number(size.group(3)) * _UNITS[size.group(4).lower()]
        if total > 0 and done <= total:
            return Hint(done / total * 100, DOWNLOADING)
        return None
    percent = _PERCENT_LINE.match(text)
    if percent:
        value = _number(percent.group(1))
        return Hint(value) if 0 <= value <= 100 else None
    lower = text.lower()
    for needle, phase, value in _PHASES:
        if lower.startswith(needle):
            return Hint(value, phase)
    return None
