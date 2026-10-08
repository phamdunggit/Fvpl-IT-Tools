"""Nhật ký hoàn tác: lưu giá trị registry trước và sau mỗi lần tool đổi, để trả lại được."""

from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .registry import RegValue

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class RegChange:
    key: str
    name: str
    before: RegValue
    after: RegValue

    def to_json(self) -> dict:
        return {"key": self.key, "name": self.name, "before": self.before.to_json(), "after": self.after.to_json()}

    @classmethod
    def from_json(cls, data: dict) -> RegChange:
        return cls(
            key=data["key"],
            name=data["name"],
            before=RegValue.from_json(data["before"]),
            after=RegValue.from_json(data["after"]),
        )


@dataclass
class JournalEntry:
    id: str
    action_id: str
    action_name: str
    time: str
    run_by: str
    target_user: str
    changes: list[RegChange]
    after: list[str] = field(default_factory=list)
    undone_at: str | None = None

    @classmethod
    def new(cls, action_id: str, action_name: str, run_by: str, target_user: str,
            changes: list[RegChange], after: list[str]) -> JournalEntry:
        return cls(
            id=uuid.uuid4().hex[:12],
            action_id=action_id,
            action_name=action_name,
            time=datetime.now().isoformat(timespec="seconds"),
            run_by=run_by,
            target_user=target_user,
            changes=changes,
            after=after,
        )

    @property
    def undone(self) -> bool:
        return self.undone_at is not None

    @property
    def time_label(self) -> str:
        return _format_time(self.time)

    @property
    def undone_label(self) -> str:
        return _format_time(self.undone_at) if self.undone_at else ""

    def to_json(self) -> dict:
        return {
            "id": self.id,
            "action_id": self.action_id,
            "action_name": self.action_name,
            "time": self.time,
            "run_by": self.run_by,
            "target_user": self.target_user,
            "changes": [change.to_json() for change in self.changes],
            "after": self.after,
            "undone_at": self.undone_at,
        }

    @classmethod
    def from_json(cls, data: dict) -> JournalEntry:
        return cls(
            id=data["id"],
            action_id=data["action_id"],
            action_name=data["action_name"],
            time=data["time"],
            run_by=data.get("run_by", ""),
            target_user=data.get("target_user", ""),
            changes=[RegChange.from_json(item) for item in data.get("changes", [])],
            after=list(data.get("after", [])),
            undone_at=data.get("undone_at"),
        )


def _format_time(value: str) -> str:
    try:
        return datetime.fromisoformat(value).strftime("%d/%m/%Y %H:%M:%S")
    except ValueError:
        return value


class UndoJournal:
    """Lưu trong một file JSON. Ghi theo kiểu file tạm rồi đổi tên để không hỏng file khi mất điện."""

    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()

    def entries(self) -> list[JournalEntry]:
        """Mới nhất đứng trước."""
        with self._lock:
            return list(reversed(self._load()))

    def get(self, entry_id: str) -> JournalEntry | None:
        return next((entry for entry in self.entries() if entry.id == entry_id), None)

    def latest_for(self, action_id: str) -> JournalEntry | None:
        """Lần chạy gần nhất của một mục mà chưa hoàn tác."""
        return next(
            (entry for entry in self.entries() if entry.action_id == action_id and not entry.undone), None
        )

    def add(self, entry: JournalEntry) -> None:
        with self._lock:
            items = self._load()
            items.append(entry)
            self._save(items)

    def mark_undone(self, entry_id: str) -> None:
        with self._lock:
            items = self._load()
            for entry in items:
                if entry.id == entry_id:
                    entry.undone_at = datetime.now().isoformat(timespec="seconds")
            self._save(items)

    def _load(self) -> list[JournalEntry]:
        if not self.path.exists():
            return []
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            return [JournalEntry.from_json(item) for item in raw.get("entries", [])]
        except (OSError, ValueError, KeyError, TypeError):
            # File hỏng thì cất riêng để còn xem lại, rồi bắt đầu nhật ký mới.
            backup = self.path.with_name(f"{self.path.stem}.corrupt-{datetime.now():%Y%m%d%H%M%S}.json")
            log.exception("Nhật ký hoàn tác bị hỏng, đã đổi tên thành %s", backup.name)
            try:
                self.path.replace(backup)
            except OSError:
                pass
            return []

    def _save(self, items: list[JournalEntry]) -> None:
        data = {"version": 1, "entries": [entry.to_json() for entry in items]}
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp, self.path)
