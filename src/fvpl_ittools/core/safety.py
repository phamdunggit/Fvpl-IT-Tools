"""Tạo restore point trước khi chạy mục có rủi ro."""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass

from . import shell

RESTORE_POINT_TIMEOUT = 600

_RESTORE_POINT_SCRIPT = """\
$desc = __DESC__
function Get-LastRestorePoint {
    Get-ComputerRestorePoint -ErrorAction SilentlyContinue | Sort-Object SequenceNumber | Select-Object -Last 1
}
$before = Get-LastRestorePoint
try { Enable-ComputerRestore -Drive "$env:SystemDrive\\" -ErrorAction Stop }
catch { Write-Output ('Không bật được System Protection: ' + $_.Exception.Message) }
Checkpoint-Computer -Description $desc -RestorePointType MODIFY_SETTINGS -WarningAction SilentlyContinue
$after = Get-LastRestorePoint
$created = [bool]($after -and (-not $before -or $after.SequenceNumber -ne $before.SequenceNumber))
$last = $null
if ($after) { $last = $after.ConvertToDateTime($after.CreationTime).ToString('dd\\/MM\\/yyyy HH:mm') }
[pscustomobject]@{ created = $created; last_time = $last } | ConvertTo-Json -Compress
"""


@dataclass(frozen=True)
class RestorePointResult:
    created: bool
    message: str


def last_json_line(output: str) -> dict | None:
    for line in reversed(output.splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except ValueError:
                return None
    return None


def create_restore_point(description: str, cancel: threading.Event | None = None) -> RestorePointResult:
    """Bật System Protection cho ổ hệ thống nếu đang tắt, rồi tạo restore point.

    Windows chỉ cho tạo một restore point mỗi 24 giờ. Khi bị từ chối vì lý do này thì báo rõ
    thời điểm của điểm gần nhất, để IT biết vẫn còn đường quay lại.
    """
    script = _RESTORE_POINT_SCRIPT.replace("__DESC__", shell.ps_quote(description))
    result = shell.run_powershell(script, timeout=RESTORE_POINT_TIMEOUT, cancel=cancel)
    data = last_json_line(result.output)
    if result.cancelled:
        return RestorePointResult(False, "Đã huỷ tạo restore point.")
    if not result.ok or data is None:
        detail = result.output.strip().splitlines()[-1] if result.output.strip() else f"mã lỗi {result.code}"
        return RestorePointResult(False, f"Không tạo được restore point: {detail}")
    if data.get("created"):
        return RestorePointResult(True, f"Đã tạo restore point “{description}”.")
    if data.get("last_time"):
        return RestorePointResult(
            False,
            "Windows chỉ cho tạo 1 restore point mỗi 24 giờ. "
            f"Điểm gần nhất tạo lúc {data['last_time']}, có thể dùng điểm đó để quay lại.",
        )
    return RestorePointResult(False, "Không tạo được restore point (System Protection có thể đang bị chặn bởi GPO).")
