"""Tuỳ chọn của người dùng tool, theo tài khoản Windows: kho bộ cài đã chọn, sau này là chế độ giao diện.

Lưu ở %APPDATA%\\FVPL-ITTools\\prefs.json (không lên git). File hỏng hoặc không đọc được thì coi như chưa chọn gì.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from . import paths

log = logging.getLogger(__name__)

PREFS_FILE = "prefs.json"
SOFTWARE_ROOT = "software_root"  # kho bộ cài IT chọn bằng nút "Chọn kho…" ở trang Phần mềm


def prefs_path() -> Path:
    override = os.environ.get("FVPL_ITTOOLS_PREFS")
    if override:
        return Path(override)
    return Path(os.environ.get("APPDATA") or Path.home()) / paths.APP_DIR_NAME / PREFS_FILE


def load() -> dict[str, Any]:
    try:
        data = json.loads(prefs_path().read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        log.warning("Không đọc được %s, dùng mặc định: %s", prefs_path(), exc)
        return {}
    return data if isinstance(data, dict) else {}


def get(key: str, default: Any = None) -> Any:
    return load().get(key, default)


def put(key: str, value: Any) -> None:
    """Ghi một tuỳ chọn (None thì xoá). Lỗi ghi thì ném OSError."""
    data = load()
    if value is None:
        data.pop(key, None)
    else:
        data[key] = value
    file = prefs_path()
    file.parent.mkdir(parents=True, exist_ok=True)
    temp = file.with_suffix(".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, file)
