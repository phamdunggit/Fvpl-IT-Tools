"""Đóng gói app thành thư mục exe + file zip.

    python packaging/build.py            # bản phát hành: exe tự xin quyền admin (UAC)
    python packaging/build.py --test     # bản thử: không xin UAC, tự chạy selftest sau khi build

Kết quả nằm trong dist/: thư mục FVPL-ITTools/ và FVPL-ITTools-v<phiên bản>.zip
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGING = ROOT / "packaging"
DIST = ROOT / "dist"
NAME = "FVPL-ITTools"

VERSION_TEMPLATE = """\
VSVersionInfo(
  ffi=FixedFileInfo(filevers={tuple}, prodvers={tuple}),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'FVPL IT'),
      StringStruct('FileDescription', 'FVPL IT Toolkit'),
      StringStruct('FileVersion', '{text}'),
      StringStruct('InternalName', '{name}'),
      StringStruct('OriginalFilename', '{name}.exe'),
      StringStruct('ProductName', 'FVPL IT Toolkit'),
      StringStruct('ProductVersion', '{text}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""


def read_version() -> str:
    text = (ROOT / "src" / "fvpl_ittools" / "__init__.py").read_text(encoding="utf-8")
    return re.search(r'__version__ = "([^"]+)"', text).group(1)


def write_version_file(version: str) -> None:
    numbers = [int(part) for part in re.findall(r"\d+", version)[:4]]
    numbers += [0] * (4 - len(numbers))
    (PACKAGING / "version_info.txt").write_text(
        VERSION_TEMPLATE.format(tuple=tuple(numbers), text=version, name=NAME), encoding="utf-8"
    )


def selftest(exe: Path) -> None:
    out = Path(tempfile.mkdtemp(prefix="fvpl-selftest-"))
    env = dict(os.environ, FVPL_ITTOOLS_STATE_DIR=str(out / "state"))
    code = subprocess.run([str(exe), "--selftest", str(out)], env=env, timeout=120).returncode
    report = json.loads((out / "selftest.json").read_text(encoding="utf-8"))
    print(f"Selftest: mã thoát {code}, {len(report['actions'])} mục, lỗi nạp: {report['load_errors']}")
    print(f"Ảnh chụp các trang: {out}")
    if code != 0 or not report["frozen"]:
        raise SystemExit("Selftest bản exe KHÔNG đạt")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true", help="bản thử không UAC, tự chạy selftest")
    args = parser.parse_args()

    version = read_version()
    write_version_file(version)
    env = dict(os.environ)
    if args.test:
        env["FVPL_NO_UAC"] = "1"
    subprocess.run(
        [sys.executable, "-m", "PyInstaller", str(PACKAGING / "fvpl_ittools.spec"),
         "--noconfirm", "--clean", "--distpath", str(DIST), "--workpath", str(ROOT / "build")],
        check=True, cwd=ROOT, env=env,
    )
    folder = DIST / NAME
    if args.test:
        selftest(folder / f"{NAME}.exe")
        return
    archive = shutil.make_archive(str(DIST / f"{NAME}-v{version}"), "zip", DIST, NAME)
    size = sum(file.stat().st_size for file in folder.rglob("*") if file.is_file()) / 1024 / 1024
    print(f"Xong: {folder} ({size:.0f} MB), {archive}")


if __name__ == "__main__":
    main()
