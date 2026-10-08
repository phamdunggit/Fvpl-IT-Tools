"""Ghi log ra file theo từng phiên chạy và che mật khẩu trước khi ghi."""

from __future__ import annotations

import logging
import time
from datetime import datetime
from pathlib import Path

from . import paths

LOG_RETENTION_DAYS = 90
MASK = "******"

_secrets: set[str] = set()
_current_log: Path | None = None


def register_secret(value: str | None) -> None:
    """Đăng ký một chuỗi bí mật (mật khẩu...) để không bao giờ xuất hiện trong log hay khung log."""
    if value:
        _secrets.add(value)


def forget_secret(value: str | None) -> None:
    if value:
        _secrets.discard(value)


def mask(text: str) -> str:
    for secret in _secrets:
        text = text.replace(secret, MASK)
    return text


class _MaskFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if _secrets:
            record.msg = mask(record.getMessage())
            record.args = None
        return True


def setup_logging() -> Path:
    """Tạo file log cho phiên này trong thư mục logs, xoá log cũ hơn LOG_RETENTION_DAYS ngày."""
    global _current_log
    folder = paths.logs_dir()
    _remove_old_logs(folder)
    _current_log = folder / f"{datetime.now():%Y-%m-%d_%H%M%S}.log"
    handler = logging.FileHandler(_current_log, encoding="utf-8")
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S")
    )
    handler.addFilter(_MaskFilter())
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    return _current_log


def current_log_file() -> Path | None:
    return _current_log


def _remove_old_logs(folder: Path) -> None:
    cutoff = time.time() - LOG_RETENTION_DAYS * 86400
    for file in folder.glob("*.log"):
        try:
            if file.stat().st_mtime < cutoff:
                file.unlink()
        except OSError:
            pass
