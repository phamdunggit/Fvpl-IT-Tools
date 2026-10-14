"""Điểm vào: python -m fvpl_ittools (hoặc file exe đóng gói)."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import traceback
from pathlib import Path

from . import APP_NAME, __version__

log = logging.getLogger("fvpl_ittools")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="fvpl-ittools", description=APP_NAME)
    parser.add_argument("--no-elevate", action="store_true",
                        help="không hỏi mở lại bằng quyền admin (dùng khi phát triển)")
    parser.add_argument("--selftest", metavar="THƯ_MỤC",
                        help="dựng cửa sổ, chụp ảnh từng trang và ghi selftest.json vào thư mục rồi thoát")
    parser.add_argument("--resume", action="store_true",
                        help="mở thẳng trang Cài máy mới để làm tiếp sau khi khởi động lại (tác vụ hẹn của wizard)")
    return parser.parse_args(argv)


def _install_excepthook() -> None:
    def handle(exc_type, exc, tb) -> None:
        log.critical("Lỗi không bắt được:\n%s", "".join(traceback.format_exception(exc_type, exc, tb)))
        try:
            from PySide6.QtWidgets import QApplication, QMessageBox
            if QApplication.instance() is not None:
                QMessageBox.critical(None, APP_NAME, f"Lỗi không mong muốn:\n{exc}\n\nChi tiết đã ghi vào file log.")
        except Exception:
            pass
    sys.excepthook = handle


def _ask_elevate(args: list[str]) -> bool:
    """Hỏi mở lại bằng quyền admin. True nếu đã mở tiến trình admin mới (tiến trình này nên thoát)."""
    from PySide6.QtWidgets import QMessageBox
    from .app import relaunch_as_admin

    box = QMessageBox()
    box.setWindowTitle(APP_NAME)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setText("Tool cần quyền admin cho phần lớn chức năng.")
    box.setInformativeText("Mở lại bằng quyền admin? Nếu chạy tiếp không có quyền admin, các mục cần admin sẽ bị khoá.")
    elevate = box.addButton("Mở lại bằng admin", QMessageBox.ButtonRole.AcceptRole)
    box.addButton("Chạy không có admin", QMessageBox.ButtonRole.RejectRole)
    box.exec()
    if box.clickedButton() is elevate:
        if relaunch_as_admin(args):
            return True
        QMessageBox.warning(None, APP_NAME, "Không mở được bằng quyền admin (có thể đã bấm No ở hộp thoại UAC).")
    return False


def _selftest(window, app_ctx, out_dir: Path) -> int:
    from PySide6.QtWidgets import QApplication

    def wait_loaded(page) -> None:
        # Trang đọc nền (Tổng quan, Phần mềm): chờ đọc xong, kiểm tra luôn script và dữ liệu đã được đóng gói đủ.
        deadline = time.monotonic() + 120
        while getattr(page, "loading", False) and time.monotonic() < deadline:
            QApplication.processEvents()
            time.sleep(0.05)
        for _ in range(5):  # widget vừa tạo khi đọc xong (ví dụ thẻ chọn Office) cần vài lượt để dàn trang
            QApplication.processEvents()

    out_dir.mkdir(parents=True, exist_ok=True)
    window.show()
    shots = []
    for row in range(window.sidebar.count()):
        window.sidebar.setCurrentRow(row)
        QApplication.processEvents()
        wait_loaded(window.stack.currentWidget())
        file = out_dir / f"page-{row}.png"
        window.grab().save(str(file))
        shots.append(file.name)
    software = window.software.state
    software_errors = software.catalog.errors if software is not None else ["chưa quét xong"]
    report = {
        "version": __version__,
        "frozen": bool(getattr(sys, "frozen", False)),
        "actions": [action.id for action in app_ctx.actions],
        "packs": [pack.id for pack in app_ctx.packs],
        "load_errors": app_ctx.load_errors,
        "computer": app_ctx.machine.computer_name,
        "is_admin": app_ctx.env.is_admin,
        "overview_loaded": not window.overview.loading,
        "overview_errors": window.overview.failed,
        "software_catalog": software.catalog.source if software is not None else None,
        "software_errors": software_errors,
        "screenshots": shots,
    }
    (out_dir / "selftest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    window.overview.stop()
    ok = (app_ctx.actions and not app_ctx.load_errors and not window.overview.loading
          and not window.overview.failed and not software_errors)
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    raw_args = list(sys.argv[1:] if argv is None else argv)
    args = _parse_args(raw_args)
    if args.selftest and "QT_QPA_PLATFORM" not in os.environ:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"

    from PySide6.QtWidgets import QApplication

    from .app import build_context
    from .core import winapi
    from .core.log import setup_logging
    from .ui.main_window import MainWindow
    from .ui.theme import apply_theme

    log_file = setup_logging()
    _install_excepthook()
    log.info("Khởi động %s %s", APP_NAME, __version__)

    qt_app = QApplication(sys.argv[:1])
    qt_app.setApplicationName(APP_NAME)
    qt_app.setApplicationVersion(__version__)
    apply_theme(qt_app)

    if not args.selftest and not args.no_elevate and not winapi.is_admin():
        if _ask_elevate(raw_args):
            return 0

    app_ctx = build_context(log_file)
    window = MainWindow(app_ctx, resume=args.resume)
    if args.selftest:
        return _selftest(window, app_ctx, Path(args.selftest))
    window.show()
    window.maybe_show_welcome()
    return qt_app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
