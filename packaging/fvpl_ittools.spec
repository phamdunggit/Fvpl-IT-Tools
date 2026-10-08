# -*- mode: python ; coding: utf-8 -*-
# Spec PyInstaller. Không chạy trực tiếp, dùng: python packaging/build.py
import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

ROOT = Path(SPECPATH).parent
NAME = "FVPL-ITTools"
# build.py đặt FVPL_NO_UAC=1 cho bản thử (chạy được không cần UAC để tự kiểm tra sau khi build).
UAC_ADMIN = os.environ.get("FVPL_NO_UAC") != "1"
VERSION_FILE = ROOT / "packaging" / "version_info.txt"

a = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT / "src")],
    datas=collect_data_files("fvpl_ittools"),
    excludes=["tkinter", "unittest", "pydoc", "PySide6.QtNetwork", "PySide6.QtQml", "PySide6.QtQuick"],
    noarchive=False,
)

# Bỏ phần Qt app không dùng (~60MB): bàn phím ảo kéo theo Quick/Qml/Network/OpenGL, plugin PDF,
# OpenGL phần mềm, platform Direct2D và các định dạng ảnh hiếm.
UNUSED = (
    "opengl32sw.dll", "Qt6Quick", "Qt6Qml", "Qt6Network", "Qt6OpenGL", "Qt6Pdf", "Qt6VirtualKeyboard",
    "qtvirtualkeyboardplugin", "qpdf.dll", "qdirect2d.dll", "qicns.dll", "qtga.dll", "qtiff.dll",
    "qwbmp.dll", "qwebp.dll", "qtuiotouchplugin.dll",
)


def _used(entry) -> bool:
    file_name = entry[0].replace("\\", "/").rsplit("/", 1)[-1]
    return not file_name.startswith(UNUSED)


a.binaries = [entry for entry in a.binaries if _used(entry)]
a.datas = [entry for entry in a.datas if _used(entry)]
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=NAME,
    console=False,
    uac_admin=UAC_ADMIN,
    upx=False,  # UPX làm diệt virus báo nhầm nhiều hơn
    version=str(VERSION_FILE) if VERSION_FILE.exists() else None,
)
coll = COLLECT(exe, a.binaries, a.datas, name=NAME, upx=False)
