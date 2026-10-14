"""Thời gian chạy thật của từng mục (ví dụ cài Office mất bao lâu), để ước tính "còn khoảng N phút".

Lưu 5 lần chạy gần nhất của mỗi mục trong <thư mục dữ liệu>\\durations.json. Chỉ tính lần chạy xong không lỗi.
Mục chưa chạy lần nào thì không biết, khi đó không hiện ước tính (thà không nói còn hơn nói sai).
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Iterable
from pathlib import Path

from . import paths

log = logging.getLogger(__name__)

FILE = "durations.json"
KEEP = 5
MIN_SECONDS = 1.0  # mục chạy nhanh hơn thế này không đáng ghi


def _file() -> Path:
    return paths.state_dir() / FILE


def load() -> dict[str, list[float]]:
    try:
        data = json.loads(_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(key): [float(item) for item in value if isinstance(item, (int, float))]
            for key, value in data.items() if isinstance(value, list)}


def record(samples: Iterable[tuple[str, float]]) -> None:
    """Ghi (id mục, số giây) của các mục vừa chạy xong không lỗi."""
    samples = [(action_id, seconds) for action_id, seconds in samples if seconds >= MIN_SECONDS]
    if not samples:
        return
    data = load()
    for action_id, seconds in samples:
        data[action_id] = (data.get(action_id, []) + [round(seconds, 1)])[-KEEP:]
    try:
        file = _file()
        temp = file.with_suffix(".tmp")
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(temp, file)
    except OSError as exc:
        log.warning("Không lưu được thời gian chạy: %s", exc)


def estimate(action_id: str, data: dict[str, list[float]] | None = None) -> float | None:
    values = (load() if data is None else data).get(action_id)
    return sum(values) / len(values) if values else None


def total(action_ids: Iterable[str]) -> float | None:
    """Tổng thời gian ước tính, None nếu có mục chưa biết."""
    data = load()
    result = 0.0
    for action_id in action_ids:
        value = estimate(action_id, data)
        if value is None:
            return None
        result += value
    return result


def minutes_text(seconds: float) -> str:
    minutes = max(1, round(seconds / 60))
    return f"khoảng {minutes} phút"
