"""Sao lưu và cài lại driver (PLAN.md mục 5.7): `pnputil /export-driver` và `pnputil /add-driver /subdirs /install`.

Chỉ xuất driver không có sẵn trong Windows (driver của hãng, oem*.inf). Hữu ích trước khi cài lại Windows, hoặc để
lấy driver của một máy cho máy cùng model. Bản sao lưu đặt trên ổ mang theo (`DriverBackup\\<máy>_<ngày>` cạnh
tool) nếu tool đang chạy từ USB / SSD, không thì trong thư mục dữ liệu của tool.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from ..actions.loader import parse_action
from ..actions.model import Action
from . import paths, shell

FOLDER = "DriverBackup"

_BACKUP = """\
New-Item -ItemType Directory -Force -Path $Destination | Out-Null
Write-Output ('Xuất driver vào {0}' -f $Destination)
& pnputil.exe /export-driver * $Destination
$code = $LASTEXITCODE
$folders = @(Get-ChildItem -LiteralPath $Destination -Directory -ErrorAction SilentlyContinue)
$size = (Get-ChildItem -LiteralPath $Destination -Recurse -File -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum
Write-Output ('Đã xuất {0} gói driver, {1:N0} MB.' -f $folders.Count, ($size / 1MB))
exit $code
"""

_RESTORE = """\
if (-not (Get-ChildItem -LiteralPath $Source -Recurse -Filter *.inf -ErrorAction SilentlyContinue | Select-Object -First 1)) {
    Write-Output ('Không thấy file .inf nào trong {0}' -f $Source)
    exit 2
}
& pnputil.exe /add-driver (Join-Path $Source '*.inf') /subdirs /install
exit $LASTEXITCODE
"""


def _writable(folder: Path) -> bool:
    try:
        folder.mkdir(parents=True, exist_ok=True)
        probe = folder / ".write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def backup_root() -> Path:
    root = paths.portable_root()
    if root is not None and _writable(root / FOLDER):
        return root / FOLDER
    folder = paths.state_dir() / "driver-backup"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def backup_dir(computer: str, now: datetime | None = None) -> Path:
    safe = "".join(char if char.isalnum() or char == "-" else "_" for char in computer) or "may"
    return backup_root() / f"{safe}_{(now or datetime.now()):%Y%m%d_%H%M}"


def backup_action(destination: Path) -> Action:
    return parse_action({
        "id": "drv.backup", "name": f"Sao lưu driver vào {destination}", "category": "Driver", "page": "utilities",
        "description": "Xuất driver của hãng (không gồm driver có sẵn trong Windows) bằng pnputil /export-driver.",
        "apply": [{"powershell": shell.ps_variable_lines({"Destination": str(destination)}) + _BACKUP,
                   "timeout": 1800}],
    })


def restore_action(source: Path) -> Action:
    return parse_action({
        "id": "drv.restore", "name": f"Cài lại driver từ {source}", "category": "Driver", "page": "utilities",
        "description": "Nạp mọi file .inf trong thư mục (cả thư mục con) vào kho driver và cài cho thiết bị khớp.",
        "apply": [{"powershell": shell.ps_variable_lines({"Source": str(source)}) + _RESTORE, "timeout": 3600,
                   "ok_codes": [0, 259], "reboot_codes": [3010],
                   "messages": {2: "Thư mục không có driver (.inf)",
                                259: "Không có thiết bị nào cần driver trong thư mục này"}}],
    })


def scripts() -> list[tuple[str, str]]:
    return [("driver sao lưu", _BACKUP), ("driver cài lại", _RESTORE)]
