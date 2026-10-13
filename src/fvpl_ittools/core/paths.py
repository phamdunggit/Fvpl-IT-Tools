"""Đường dẫn dùng chung: dữ liệu đóng gói kèm app và thư mục ghi log / nhật ký hoàn tác."""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_DIR_NAME = "FVPL-ITTools"
PACKAGE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PACKAGE_DIR / "data"

_state_dir: Path | None = None


def is_frozen() -> bool:
    """True khi chạy từ bản exe đóng gói bằng PyInstaller."""
    return bool(getattr(sys, "frozen", False))


def app_root() -> Path:
    """Thư mục chứa file exe (bản đóng gói) hoặc thư mục gốc repo (khi chạy từ mã nguồn)."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return PACKAGE_DIR.parent.parent


def _writable(folder: Path) -> bool:
    try:
        folder.mkdir(parents=True, exist_ok=True)
        probe = folder / ".write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def state_dir() -> Path:
    """Nơi ghi log và nhật ký hoàn tác.

    Ưu tiên %ProgramData%\\FVPL-ITTools để mọi tài khoản admin trên máy dùng chung một nhật ký.
    Không ghi được (chạy không có quyền admin) thì dùng %LOCALAPPDATA%.
    """
    global _state_dir
    if _state_dir is None:
        candidates: list[Path] = []
        override = os.environ.get("FVPL_ITTOOLS_STATE_DIR")
        if override:
            candidates.append(Path(override))
        candidates.append(Path(os.environ.get("ProgramData", r"C:\ProgramData")) / APP_DIR_NAME)
        candidates.append(Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / APP_DIR_NAME)
        for candidate in candidates:
            if _writable(candidate):
                _state_dir = candidate
                break
        else:
            raise RuntimeError("Không tìm được thư mục nào ghi được để lưu log của tool.")
    return _state_dir


def logs_dir() -> Path:
    folder = state_dir() / "logs"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def reports_dir() -> Path:
    """Báo cáo tool tạo ra (gpresult, thông tin máy xuất HTML...)."""
    folder = state_dir() / "reports"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def undo_journal_path() -> Path:
    folder = state_dir() / "undo"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "journal.json"
