"""Báo khi có bản tool mới (PLAN.md mục 6.8): đọc version.json trong thư mục phát hành trên share.

Thư mục phát hành: `release_dir` trong site.yaml, bỏ trống thì `<kho bộ cài>\\ITTools`. Lệnh
`python packaging\\deploy.py share <thư mục>` chép bản build lên đó và ghi version.json:

    {"version": "1.0.0", "date": "2026-10-20", "folder": "FVPL-ITTools-v1.0.0",
     "zip": "FVPL-ITTools-v1.0.0.zip", "notes": ["Sửa lỗi theo tình huống", "..."]}

Tool không tự cập nhật (bản trên USB / SSD đang chạy thì không ghi đè được): chỉ báo và mở thư mục để IT chép.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

VERSION_FILE = "version.json"
RELEASE_SUBDIR = "ITTools"


class UpdateError(RuntimeError):
    pass


@dataclass(frozen=True)
class Release:
    version: str
    folder: Path            # thư mục bản phát hành, ví dụ ...\ITTools\FVPL-ITTools-v1.0.0
    zip: Path | None
    date: str = ""
    notes: tuple[str, ...] = ()


def version_key(text: str) -> tuple[int, ...]:
    """"1.2.3" → (1, 2, 3, 0); chữ thêm phía sau (rc1, -beta) bị bỏ qua."""
    numbers = [int(part) for part in re.findall(r"\d+", str(text).split("-")[0].split("+")[0])[:4]]
    return tuple(numbers + [0] * (4 - len(numbers)))


def is_newer(candidate: str, current: str) -> bool:
    return version_key(candidate) > version_key(current)


def release_dir(configured: str, software_root: str) -> Path | None:
    if configured:
        return Path(configured)
    if software_root:
        return Path(software_root) / RELEASE_SUBDIR
    return None


def manifest(version: str, date: str, folder: str, zip_name: str, notes: list[str]) -> dict:
    return {"version": version, "date": date, "folder": folder, "zip": zip_name, "notes": list(notes)}


def read_release(directory: Path) -> Release | None:
    """Bản phát hành mới nhất khai báo trong version.json; None nếu thư mục không có file đó."""
    file = directory / VERSION_FILE
    try:
        if not file.is_file():
            return None
        data = json.loads(file.read_text(encoding="utf-8"))
    except OSError as exc:
        raise UpdateError(f"Không đọc được {file}: {exc}") from exc
    except ValueError as exc:
        raise UpdateError(f"{file} sai định dạng: {exc}") from exc
    if not isinstance(data, dict) or not data.get("version"):
        raise UpdateError(f"{file} thiếu 'version'")
    notes = data.get("notes") or []
    return Release(
        version=str(data["version"]),
        folder=directory / str(data.get("folder") or directory),
        zip=directory / str(data["zip"]) if data.get("zip") else None,
        date=str(data.get("date") or ""),
        notes=tuple(str(note) for note in (notes if isinstance(notes, list) else [notes])),
    )


def check(directory: Path | None, current: str) -> Release | None:
    """Bản mới hơn bản đang chạy, None nếu không có. Gọi ở thread nền (share có thể chậm)."""
    if directory is None:
        return None
    release = read_release(directory)
    return release if release is not None and is_newer(release.version, current) else None
