"""Tìm file lớn và thư mục chiếm nhiều chỗ trên một ổ / thư mục. Chỉ đọc, không xoá gì.

IT xem kết quả rồi tự quyết định (mở thư mục chứa, hỏi người dùng); tool không xoá file của người dùng.
Không đi theo junction / symlink để không đếm trùng hay đi vòng.
"""

from __future__ import annotations

import heapq
import os
import threading
from dataclasses import dataclass, field
from typing import Callable

PROGRESS_EVERY = 5000


@dataclass(frozen=True, order=True)
class BigFile:
    size: int
    path: str
    modified: float = 0.0


@dataclass
class SearchResult:
    root: str
    files: list[BigFile] = field(default_factory=list)       # lớn nhất trước
    folders: list[tuple[int, str]] = field(default_factory=list)  # (dung lượng, thư mục cấp đầu), lớn nhất trước
    scanned: int = 0
    unreadable: int = 0
    cancelled: bool = False


def find(root: str, min_size: int, cancel: threading.Event, progress: Callable[[int], None] | None = None,
         limit: int = 200) -> SearchResult:
    result = SearchResult(root=root)
    heap: list[BigFile] = []
    folder_sizes: dict[str, int] = {}
    # (thư mục cần xem, thư mục cấp đầu mà nó thuộc về; None với chính thư mục gốc)
    stack: list[tuple[str, str | None]] = [(root, None)]
    next_report = PROGRESS_EVERY
    while stack:
        if cancel.is_set():
            result.cancelled = True
            break
        current, top = stack.pop()
        try:
            entries = os.scandir(current)
        except OSError:
            result.unreadable += 1
            continue
        with entries:
            for entry in entries:
                try:
                    if entry.is_symlink() or entry.is_junction():
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        stack.append((entry.path, top or entry.path))
                        continue
                    info = entry.stat(follow_symlinks=False)
                except OSError:
                    result.unreadable += 1
                    continue
                result.scanned += 1
                if top is not None:
                    folder_sizes[top] = folder_sizes.get(top, 0) + info.st_size
                if info.st_size >= min_size:
                    item = BigFile(info.st_size, entry.path, info.st_mtime)
                    if len(heap) < limit:
                        heapq.heappush(heap, item)
                    elif item > heap[0]:
                        heapq.heapreplace(heap, item)
        if progress is not None and result.scanned >= next_report:
            progress(result.scanned)
            next_report = result.scanned + PROGRESS_EVERY
    result.files = sorted(heap, reverse=True)
    result.folders = sorted(((size, path) for path, size in folder_sizes.items()), reverse=True)[:30]
    return result
