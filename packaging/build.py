"""Đóng gói app thành thư mục exe + file zip.

    python packaging/build.py            # bản phát hành: exe tự xin quyền admin (UAC)
    python packaging/build.py --test     # bản thử: không xin UAC, tự chạy selftest sau khi build

Kết quả nằm trong dist/: thư mục FVPL-ITTools/, FVPL-ITTools-v<phiên bản>.zip và FVPL-ITTools-v<phiên bản>.sha256.txt
(mã SHA-256 của exe, để thêm exception theo hash trong SEPM khi Symantec chặn nhầm).

Ký số (bản phát hành): đặt biến môi trường FVPL_SIGN_THUMBPRINT = thumbprint của chứng chỉ Code Signing đã cài trong
Certificates của tài khoản đang build (xem docs/KY-SO.md). Không đặt thì bỏ qua, exe chưa ký.

Files the IT team keeps next to the exe in dist/FVPL-ITTools (SOFT, site.yaml, ... see KEEP_BESIDE_EXE) survive a
rebuild: PyInstaller wipes that folder, so they are moved aside first and moved back afterwards. They never go into
the zip.
"""

from __future__ import annotations

import argparse
import hashlib
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
SIGN_THUMBPRINT = "FVPL_SIGN_THUMBPRINT"
SIGN_TIMESTAMP = "FVPL_SIGN_TIMESTAMP"
SIGNTOOL = "FVPL_SIGNTOOL"
DEFAULT_TIMESTAMP = "http://timestamp.digicert.com"
# Kept next to the exe across rebuilds, left out of the zip (installers, company info, real machine data).
KEEP_BESIDE_EXE = ("SOFT", "site.yaml", "wizard-templates.json", "license-keys*.json",
                   "Reports", "Inventory", "DriverBackup")
STASH = DIST / f".{NAME}-keep"

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


def find_signtool() -> Path | None:
    """signtool.exe: biến FVPL_SIGNTOOL, không thì bản mới nhất trong Windows SDK."""
    override = os.environ.get(SIGNTOOL)
    if override:
        return Path(override) if Path(override).is_file() else None
    kits = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Windows Kits" / "10" / "bin"
    found = sorted(kits.glob("10.*/x64/signtool.exe"), key=lambda item: [int(part) for part in item.parent.parent.name.split(".")])
    return found[-1] if found else None


def sign_commands(signtool: Path, exe: Path, thumbprint: str, timestamp: str) -> list[list[str]]:
    """Ký SHA-256 kèm dấu thời gian (chữ ký còn hiệu lực sau khi chứng chỉ hết hạn), rồi kiểm tra lại."""
    return [
        [str(signtool), "sign", "/sha1", thumbprint.replace(" ", ""), "/fd", "SHA256",
         "/tr", timestamp, "/td", "SHA256", "/d", "FVPL IT Toolkit", str(exe)],
        [str(signtool), "verify", "/pa", str(exe)],
    ]


def sign(exe: Path) -> bool:
    thumbprint = os.environ.get(SIGN_THUMBPRINT, "").strip()
    if not thumbprint:
        print(f"Chưa ký số exe (đặt {SIGN_THUMBPRINT}, xem docs/KY-SO.md).")
        return False
    signtool = find_signtool()
    if signtool is None:
        raise SystemExit("Không thấy signtool.exe: cài Windows SDK (chỉ cần phần Signing Tools) hoặc đặt FVPL_SIGNTOOL")
    for command in sign_commands(signtool, exe, thumbprint, os.environ.get(SIGN_TIMESTAMP) or DEFAULT_TIMESTAMP):
        subprocess.run(command, check=True)
    print(f"Đã ký số {exe.name}")
    return True


def sha256(file: Path) -> str:
    digest = hashlib.sha256()
    with file.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def stash_kept(folder: Path, stash: Path) -> list[str]:
    """Move KEEP_BESIDE_EXE items out of `folder` into `stash` (a rename, so large ISOs are not copied)."""
    restore_kept(folder, stash)  # a previous build was interrupted: put its items back first
    moved = []
    for pattern in KEEP_BESIDE_EXE:
        for item in sorted(folder.glob(pattern)) if folder.is_dir() else []:
            stash.mkdir(parents=True, exist_ok=True)
            item.rename(stash / item.name)
            moved.append(item.name)
    return moved


def restore_kept(folder: Path, stash: Path) -> None:
    if not stash.is_dir():
        return
    folder.mkdir(parents=True, exist_ok=True)
    for item in sorted(stash.iterdir()):
        target = folder / item.name
        if target.exists():
            raise SystemExit(f"Không chép lại được {item} vì {target} đã có: tự gộp hai thư mục này rồi build lại")
        item.rename(target)
    stash.rmdir()


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
    folder = DIST / NAME
    kept = stash_kept(folder, STASH)
    try:
        subprocess.run(
            [sys.executable, "-m", "PyInstaller", str(PACKAGING / "fvpl_ittools.spec"),
             "--noconfirm", "--clean", "--distpath", str(DIST), "--workpath", str(ROOT / "build")],
            check=True, cwd=ROOT, env=env,
        )
        exe = folder / f"{NAME}.exe"
        if args.test:
            selftest(exe)
            return
        signed = sign(exe)  # ký trước khi nén để file zip có bản đã ký
        digest = sha256(exe)
        (DIST / f"{NAME}-v{version}.sha256.txt").write_text(
            f"{digest}  {NAME}.exe  v{version}{'  (đã ký số)' if signed else ''}\n", encoding="utf-8")
        archive = shutil.make_archive(str(DIST / f"{NAME}-v{version}"), "zip", DIST, NAME)  # before restoring kept items
        size = sum(file.stat().st_size for file in folder.rglob("*") if file.is_file()) / 1024 / 1024
        print(f"SHA-256 của {NAME}.exe: {digest} (exception theo hash trong SEPM, xem docs/KY-SO.md)")
        print(f"Xong: {folder} ({size:.0f} MB), {archive}")
    finally:
        restore_kept(folder, STASH)
        if kept:
            print(f"Giữ lại cạnh exe (không có trong file zip): {', '.join(kept)}")


if __name__ == "__main__":
    main()
