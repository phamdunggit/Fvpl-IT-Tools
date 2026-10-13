"""Chép tool ra ổ mang theo: bản USB (cài qua share mạng) hoặc bản SSD (kèm kho bộ cài SOFT).

    python packaging/deploy.py usb E:\\                # tool + site.yaml  →  E:\\FVPL-ITTools
    python packaging/deploy.py ssd F:\\                # thêm kho bộ cài   →  F:\\FVPL-ITTools\\SOFT
    python packaging/deploy.py ssd F:\\ --soft D:\\Kho  # lấy kho từ thư mục khác (mặc định: SOFT trong repo)

Chạy packaging/build.py (bản phát hành) trước. Dùng robocopy: lần sau chỉ chép phần thay đổi, ISO đã có
không chép lại. Tool tự nhận kho bộ cài: có thư mục SOFT cạnh file exe thì dùng (bản SSD), không thì dùng
share_root trong site.yaml (bản USB).
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist" / "FVPL-ITTools"
NAME = "FVPL-ITTools"
EXE = f"{NAME}.exe"
ROBOCOPY_OPTIONS = ["/R:1", "/W:1", "/NJH", "/NDL"]


def folder_size(folder: Path) -> int:
    return sum(item.stat().st_size for item in folder.rglob("*") if item.is_file())


def commands(mode: str, target_root: Path, soft: Path, site_file: Path | None) -> list[list[str]]:
    """Các lệnh robocopy cần chạy (tách riêng để test được mà không chép gì)."""
    target = target_root / NAME
    steps = [
        # _internal: đồng bộ hẳn (/MIR) để không còn file của bản cũ. Không /MIR cả thư mục tool vì sẽ xoá SOFT, site.yaml.
        ["robocopy", str(DIST / "_internal"), str(target / "_internal"), "/MIR", *ROBOCOPY_OPTIONS],
        ["robocopy", str(DIST), str(target), EXE, *ROBOCOPY_OPTIONS],
    ]
    if site_file is not None:
        steps.append(["robocopy", str(site_file.parent), str(target), site_file.name, *ROBOCOPY_OPTIONS])
    if mode == "ssd":
        # /E: thêm và cập nhật, không xoá gì ở đích (an toàn nếu trên SSD có bộ cài khác).
        steps.append(["robocopy", str(soft), str(target / "SOFT"), "/E", *ROBOCOPY_OPTIONS])
    return steps


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # như build.py: chữ có dấu không làm lỗi khi in
    parser = argparse.ArgumentParser(description="Chép FVPL IT Toolkit ra USB / SSD")
    parser.add_argument("mode", choices=("usb", "ssd"), help="usb: chỉ tool; ssd: tool + kho bộ cài SOFT")
    parser.add_argument("drive", help="ổ hoặc thư mục đích, ví dụ E:\\")
    parser.add_argument("--soft", default=str(ROOT / "SOFT"), help="thư mục kho bộ cài (bản ssd)")
    args = parser.parse_args(argv)

    if not (DIST / EXE).is_file():
        print(f"Chưa có {DIST / EXE}. Chạy trước: python packaging\\build.py")
        return 1
    target_root = Path(args.drive)
    if not target_root.exists():
        print(f"Không thấy {target_root}")
        return 1
    soft = Path(args.soft)
    if args.mode == "ssd":
        if not (soft / "config" / "apps.yaml").is_file():
            print(f"{soft} không giống kho bộ cài (thiếu config\\apps.yaml)")
            return 1
        need = folder_size(soft) + folder_size(DIST)
        free = shutil.disk_usage(target_root).free
        if need > free:
            print(f"Ổ đích không đủ chỗ: cần tới {need / 1024**3:.1f} GB, còn trống {free / 1024**3:.1f} GB")
            return 1
    site_file = ROOT / "site.yaml"
    if not site_file.is_file():
        print("Lưu ý: chưa có site.yaml ở thư mục repo, ổ đích sẽ không có thông tin domain/share.")
        site_file = None

    for command in commands(args.mode, target_root, soft, site_file):
        print(">", " ".join(command))
        code = subprocess.run(command).returncode
        if code >= 8:  # robocopy: dưới 8 là chép được
            print(f"robocopy lỗi (mã {code})")
            return code
    print(f"Xong: {target_root / NAME}" + (" (có kho bộ cài SOFT)" if args.mode == "ssd" else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
