"""Xem nhanh lỗi trong Event Log (PLAN.md mục 5.7): Critical và Error của System, Application trong N giờ gần nhất.

Gộp theo (log, nguồn, mã sự kiện): một dòng một loại lỗi, kèm số lần và lần gần nhất, để thấy ngay lỗi lặp nhiều.
Chỉ đọc.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass

from . import shell

MAX_EVENTS = 3000
TIMEOUT = 120

_SCRIPT = """\
$since = (Get-Date).AddHours(-[int]$Hours)
$filter = @{ LogName = 'System', 'Application'; Level = 1, 2; StartTime = $since }
$events = @(Get-WinEvent -FilterHashtable $filter -MaxEvents ([int]$MaxEvents) -ErrorAction SilentlyContinue)
$groups = @(foreach ($group in @($events | Group-Object LogName, ProviderName, Id)) {
    $latest = $group.Group | Sort-Object TimeCreated -Descending | Select-Object -First 1
    $message = ''
    try { $message = [string]$latest.Message } catch { }
    if (-not $message) { $message = '(Windows không có mô tả cho sự kiện này)' }
    [pscustomobject]@{
        log = [string]$latest.LogName
        source = [string]$latest.ProviderName
        id = [int]$latest.Id
        level = [int]$latest.Level
        count = [int]$group.Count
        latest = $latest.TimeCreated.ToString('dd\\/MM\\/yyyy HH:mm')
        sort = $latest.TimeCreated.ToString('s')
        message = $(if ($message.Length -gt 1500) { $message.Substring(0, 1500) + '…' } else { $message })
    }
})
ConvertTo-Json -InputObject @($groups) -Compress
"""


class EventLogError(RuntimeError):
    pass


# Gợi ý cho các lỗi hay gặp: (nguồn, mã) → nghĩa và cách xử lý. Nguồn so không phân biệt hoa thường.
HINTS: dict[tuple[str, int], str] = {
    ("microsoft-windows-kernel-power", 41): "Máy tắt đột ngột (mất điện, giữ nút nguồn, treo). Lặp nhiều: kiểm tra nguồn, "
                                           "pin, nhiệt độ, RAM (Chẩn đoán RAM).",
    ("eventlog", 6008): "Lần tắt máy trước không đúng cách (mất điện / treo).",
    ("microsoft-windows-whea-logger", 1): "Lỗi phần cứng được sửa tạm (CPU, RAM, PCIe). Lặp nhiều: cập nhật BIOS, kiểm tra RAM.",
    ("microsoft-windows-whea-logger", 18): "Lỗi phần cứng nghiêm trọng (CPU / bo mạch): cập nhật BIOS, báo hãng bảo hành.",
    ("disk", 7): "Ổ đĩa có bad block: sao lưu dữ liệu ngay, kiểm tra sức khoẻ ổ (trang Tổng quan), thay ổ.",
    ("disk", 153): "Ổ đĩa phải thử đọc / ghi lại: ổ hoặc cáp sắp hỏng, sao lưu dữ liệu.",
    ("disk", 51): "Lỗi khi ghi trang bộ nhớ ra ổ: kiểm tra ổ cứng, cáp.",
    ("ntfs", 55): "Cấu trúc file trên ổ bị hỏng: chạy mục Hẹn sửa ổ đĩa khi khởi động.",
    ("ntfs", 98): "Ổ cần kiểm tra lỗi: chạy mục Hẹn sửa ổ đĩa khi khởi động.",
    ("netlogon", 5719): "Không tạo được kết nối bảo mật với DC: máy đang ngoài mạng công ty, DNS không trỏ về DC, hoặc "
                        "lỗi trust relationship (mục Kiểm tra kết nối với domain).",
    ("microsoft-windows-grouppolicy", 1129): "Không xử lý được Group Policy vì không kết nối được DC.",
    ("microsoft-windows-grouppolicy", 1054): "Không tìm được DC để áp Group Policy: máy ngoài mạng công ty hoặc DNS không "
                                             "trỏ về DC (mục Chẩn đoán mạng).",
    ("microsoft-windows-grouppolicy", 1053): "Không xác định được tài khoản để áp Group Policy: mất kết nối DC hoặc lỗi "
                                             "trust relationship.",
    ("microsoft-windows-time-service", 129): "Không đồng bộ được giờ với DC (mục Đồng bộ giờ).",
    ("microsoft-windows-dns-client", 1014): "Phân giải tên DNS hết thời gian chờ: kiểm tra DNS của card mạng.",
    ("service control manager", 7000): "Một dịch vụ không khởi động được (xem tên trong mô tả).",
    ("service control manager", 7001): "Dịch vụ không chạy vì dịch vụ nó phụ thuộc bị lỗi.",
    ("service control manager", 7009): "Dịch vụ khởi động quá lâu (quá 30 giây).",
    ("service control manager", 7023): "Dịch vụ dừng kèm lỗi.",
    ("service control manager", 7031): "Dịch vụ bị dừng đột ngột (crash) và đã được chạy lại.",
    ("service control manager", 7034): "Dịch vụ bị dừng đột ngột (crash).",
    ("application error", 1000): "Một chương trình bị crash (tên chương trình ở đầu mô tả).",
    ("application hang", 1002): "Một chương trình bị treo và bị đóng.",
    ("microsoft-windows-distributedcom", 10010): "Thường vô hại: một thành phần COM đăng ký chậm. Bỏ qua nếu máy chạy bình thường.",
    ("microsoft-windows-distributedcom", 10016): "Vô hại (Microsoft xác nhận): lỗi quyền DCOM của thành phần Windows. Bỏ qua.",
    ("microsoft-windows-windowsupdateclient", 20): "Cài bản cập nhật Windows bị lỗi: chạy gói Sửa Windows Update.",
    ("microsoft-windows-printservice", 372): "In lỗi (máy in / driver): xem trang Máy in.",
}


def hint_for(source: str, event_id: int) -> str:
    return HINTS.get((source.lower(), event_id), "")


@dataclass(frozen=True)
class EventGroup:
    log: str
    source: str
    event_id: int
    critical: bool
    count: int
    latest: str        # dd/MM/yyyy HH:mm
    sort_key: str      # thời điểm ISO để sắp xếp
    message: str

    @property
    def hint(self) -> str:
        return hint_for(self.source, self.event_id)

    @property
    def summary(self) -> str:
        """Dòng đầu của mô tả, để hiện trong bảng."""
        return self.message.strip().splitlines()[0] if self.message.strip() else ""


def script() -> str:
    return _SCRIPT


def parse(output: str) -> list[EventGroup]:
    data = json.loads(output) if output.strip() else []
    items = data if isinstance(data, list) else [data]
    groups = [EventGroup(str(item.get("log") or ""), str(item.get("source") or ""), int(item.get("id") or 0),
                         int(item.get("level") or 2) == 1, int(item.get("count") or 0), str(item.get("latest") or ""),
                         str(item.get("sort") or ""), str(item.get("message") or ""))
              for item in items if isinstance(item, dict)]
    # Critical trước, rồi lỗi lặp nhiều, cùng số lần thì lỗi gần đây trước (sắp hai lượt, sort giữ thứ tự cũ).
    groups.sort(key=lambda group: group.sort_key, reverse=True)
    groups.sort(key=lambda group: (not group.critical, -group.count))
    return groups


def read_errors(hours: int, cancel: threading.Event | None = None) -> list[EventGroup]:
    result = shell.run_powershell(_SCRIPT, variables={"Hours": str(int(hours)), "MaxEvents": str(MAX_EVENTS)},
                                  timeout=TIMEOUT, cancel=cancel)
    if result.cancelled:
        raise EventLogError("Đã huỷ")
    if result.timed_out:
        raise EventLogError(f"Đọc event log quá {TIMEOUT} giây")
    lines = [line for line in result.output.splitlines() if line.startswith("[") or line.startswith("{")]
    if result.code != 0 or not lines:
        raise EventLogError(result.output.strip().splitlines()[-1] if result.output.strip() else f"mã lỗi {result.code}")
    return parse(lines[-1])
