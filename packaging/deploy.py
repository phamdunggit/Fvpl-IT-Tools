"""Chép tool ra ổ mang theo: bản USB (cài qua share mạng) hoặc bản SSD (kèm kho bộ cài SOFT); hoặc phát hành lên share.

    python packaging/deploy.py usb E:\\                # tool + site.yaml  →  E:\\FVPL-ITTools
    python packaging/deploy.py ssd F:\\                # thêm kho bộ cài   →  F:\\FVPL-ITTools\\SOFT
    python packaging/deploy.py ssd F:\\ --soft D:\\Kho  # lấy kho từ thư mục khác (mặc định: SOFT trong repo)
    python packaging/deploy.py share \\\\srv\\IT$\\SOFT\\ITTools --note "Sửa lỗi theo tình huống"
        # phát hành: thư mục FVPL-ITTools-v<bản>, file zip và version.json (tool đọc để báo có bản mới)

Chạy packaging/build.py (bản phát hành) trước. Dùng robocopy: lần sau chỉ chép phần thay đổi, ISO đã có
không chép lại. Tool tự nhận kho bộ cài: có thư mục SOFT cạnh file exe thì dùng (bản SSD), không thì dùng
share_root trong site.yaml (bản USB).
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist" / "FVPL-ITTools"
NAME = "FVPL-ITTools"
EXE = f"{NAME}.exe"
ROBOCOPY_OPTIONS = ["/R:1", "/W:1", "/NJH", "/NDL"]
VERSION_FILE = "version.json"


def read_version() -> str:
    text = (ROOT / "src" / "fvpl_ittools" / "__init__.py").read_text(encoding="utf-8")
    return re.search(r'__version__ = "([^"]+)"', text).group(1)


def release_manifest(version: str, notes: list[str], today: datetime.date | None = None, exe_sha256: str = "") -> dict:
    """Nội dung version.json (cùng định dạng core/updates.py đọc). `exe_sha256`: để IT thêm exception trong SEPM."""
    manifest = {"version": version, "date": (today or datetime.date.today()).isoformat(),
                "folder": f"{NAME}-v{version}", "zip": f"{NAME}-v{version}.zip",
                "notes": notes or ["Xem CHANGELOG.md trong repo"]}
    if exe_sha256:
        manifest["exe_sha256"] = exe_sha256
    return manifest


def exe_sha256() -> str:
    digest = hashlib.sha256()
    with (DIST / EXE).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def folder_size(folder: Path) -> int:
    return sum(item.stat().st_size for item in folder.rglob("*") if item.is_file())


def commands(mode: str, target_root: Path, soft: Path, site_file: Path | None, version: str = "") -> list[list[str]]:
    """Các lệnh robocopy cần chạy (tách riêng để test được mà không chép gì)."""
    if mode == "share":
        # Mỗi bản một thư mục riêng (bản cũ giữ lại để quay về được), kèm file zip để chép ra USB.
        target = target_root / f"{NAME}-v{version}"
        steps = [["robocopy", str(DIST), str(target), "/MIR", *ROBOCOPY_OPTIONS],
                 ["robocopy", str(DIST.parent), str(target_root), f"{NAME}-v{version}.zip", *ROBOCOPY_OPTIONS]]
        if site_file is not None:
            steps.append(["robocopy", str(site_file.parent), str(target), site_file.name, *ROBOCOPY_OPTIONS])
        return steps
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
    parser = argparse.ArgumentParser(description="Chép FVPL IT Toolkit ra USB / SSD, hoặc phát hành lên share")
    parser.add_argument("mode", choices=("usb", "ssd", "share"),
                        help="usb: chỉ tool; ssd: tool + kho bộ cài SOFT; share: phát hành kèm version.json")
    parser.add_argument("drive", help="ổ hoặc thư mục đích, ví dụ E:\\ hoặc \\\\srv\\IT$\\SOFT\\ITTools")
    parser.add_argument("--soft", default=str(ROOT / "SOFT"), help="thư mục kho bộ cài (bản ssd)")
    parser.add_argument("--note", action="append", default=[], help="dòng ghi chú bản mới (share), lặp lại được")
    args = parser.parse_args(argv)

    if not (DIST / EXE).is_file():
        print(f"Chưa có {DIST / EXE}. Chạy trước: python packaging\\build.py")
        return 1
    target_root = Path(args.drive)
    version = read_version()
    if args.mode == "share":
        target_root.mkdir(parents=True, exist_ok=True)
        if not (DIST.parent / f"{NAME}-v{version}.zip").is_file():
            print(f"Chưa có {NAME}-v{version}.zip trong dist. Chạy trước: python packaging\\build.py")
            return 1
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

    for command in commands(args.mode, target_root, soft, site_file, version):
        print(">", " ".join(command))
        code = subprocess.run(command).returncode
        if code >= 8:  # robocopy: dưới 8 là chép được
            print(f"robocopy lỗi (mã {code})")
            return code
    if args.mode == "share":
        # Ghi version.json sau cùng: máy khác chỉ thấy bản mới khi thư mục đã chép xong.
        (target_root / VERSION_FILE).write_text(
            json.dumps(release_manifest(version, args.note, exe_sha256=exe_sha256()), ensure_ascii=False, indent=2),
            encoding="utf-8")
        print(f"Xong: {target_root / f'{NAME}-v{version}'} và {target_root / VERSION_FILE} (bản {version})")
        return 0
    print(f"Xong: {target_root / NAME}" + (" (có kho bộ cài SOFT)" if args.mode == "ssd" else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
