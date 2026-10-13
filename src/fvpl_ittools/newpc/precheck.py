"""Bước 0 của wizard Cài máy mới: kiểm tra máy trước khi đổi tên, join domain, cài phần mềm.

Chỉ đọc, không đổi gì. Thu thập "dữ kiện" (Facts) bằng Python và một script PowerShell (mạng, DNS, DC,
giờ), rồi `evaluate()` biến dữ kiện thành danh sách kết quả ✔ / ⚠ / ✖ kèm cách xử lý. Tách hai phần để
test được phần đánh giá mà không cần máy thật.
"""

from __future__ import annotations

import ctypes
import json
import os
import shutil
import threading
import winreg
from dataclasses import dataclass, field

from ..app import AppContext
from ..core import pslib, shell
from ..software.detect import winget_path

MIN_BUILD = 19045                 # Win10 22H2
DISK_OK_GB = 20
DISK_MIN_GB = 10
TIME_WARN_SECONDS = 60
TIME_MAX_SECONDS = 300            # Kerberos chỉ chịu lệch tối đa 5 phút

_NETWORK_SCRIPT = """\
$result = [ordered]@{}
$adapters = @(Get-ActiveAdapters)
$result.adapters = @($adapters | ForEach-Object {
    [ordered]@{ name = $_.Name; ipv4 = $_.IPv4; gateway = $_.Gateway; dns = $_.Dns; wireless = $_.Wireless }
})
$result.dns = @()
$result.dc = $null
$result.offset = $null
if ($Domain) {
    $servers = @($adapters | ForEach-Object { $_.Dns } | Where-Object { $_ } | Select-Object -Unique)
    $result.dns = @(foreach ($server in $servers) {
        [ordered]@{ server = $server; finds_dc = [bool](Test-DnsSrv $server "_ldap._tcp.dc._msdcs.$Domain") }
    })
    if (@($result.dns | Where-Object { $_.finds_dc }).Count) {
        $dc = Find-DomainController $Domain
        if ($dc) {
            $result.dc = $dc
            $result.offset = Get-NtpOffset $dc
        }
    }
}
$result.internet = [bool](Test-Port 'www.microsoft.com' 443 3000)
$result | ConvertTo-Json -Depth 4 -Compress
"""


@dataclass
class Facts:
    is_admin: bool
    build: int
    os_label: str
    joined_domain: bool
    domain: str                    # domain cần join / đang ở (rỗng nếu chưa khai báo)
    share_root: str
    share_ok: bool
    winget: bool
    disk_free_gb: float
    has_battery: bool
    on_ac: bool
    pending_reboot: list[str] = field(default_factory=list)
    network: dict | None = None    # kết quả script PowerShell, None nếu script lỗi
    network_error: str = ""


@dataclass(frozen=True)
class Check:
    key: str
    name: str
    state: str                     # ok | warn | bad | skip
    detail: str
    hint: str = ""                 # cách xử lý
    fix: str = ""                  # id mục sửa lỗi chạy được ngay, ví dụ dom.time_sync


# ---------------------------------------------------------------- thu thập


class _PowerStatus(ctypes.Structure):
    _fields_ = [
        ("ACLineStatus", ctypes.c_ubyte), ("BatteryFlag", ctypes.c_ubyte), ("BatteryLifePercent", ctypes.c_ubyte),
        ("SystemStatusFlag", ctypes.c_ubyte), ("BatteryLifeTime", ctypes.c_ulong), ("BatteryFullLifeTime", ctypes.c_ulong),
    ]


def power_status() -> tuple[bool, bool]:
    """(có pin, đang cắm sạc)."""
    status = _PowerStatus()
    if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(status)):
        return False, True
    has_battery = status.BatteryFlag not in (128, 255)  # 128: không có pin, 255: không rõ
    return has_battery, status.ACLineStatus == 1


_PENDING_REBOOT = (
    (r"SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending", None, "cài cập nhật Windows"),
    (r"SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired", None, "Windows Update"),
    (r"SYSTEM\CurrentControlSet\Control\Session Manager", "PendingFileRenameOperations", "thay file đang dùng"),
)


def pending_reboot() -> list[str]:
    """Lý do máy đang chờ khởi động lại (rỗng nếu không chờ)."""
    reasons = []
    for subkey, value, reason in _PENDING_REBOOT:
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, subkey, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
                if value is None or winreg.QueryValueEx(key, value)[0]:
                    reasons.append(reason)
        except OSError:
            continue
    return reasons


def target_domain(app: AppContext) -> str:
    if app.machine.joined_domain:
        return app.machine.dns_domain or app.machine.join_name
    return app.site.domain


def collect(app: AppContext, cancel: threading.Event | None = None) -> Facts:
    """Có thể mất vài giây (mạng) tới vài chục giây (share không trả lời); gọi ở thread nền."""
    domain = target_domain(app)
    system_drive = os.environ.get("SystemDrive", "C:") + "\\"
    has_battery, on_ac = power_status()
    share_root = app.site.share_root
    facts = Facts(
        is_admin=app.env.is_admin,
        build=app.env.build,
        os_label=app.machine.os_label,
        joined_domain=app.machine.joined_domain,
        domain=domain,
        share_root=share_root,
        share_ok=bool(share_root) and os.path.isdir(share_root),
        winget=winget_path() is not None,
        disk_free_gb=shutil.disk_usage(system_drive).free / 1024**3,
        has_battery=has_battery,
        on_ac=on_ac,
        pending_reboot=pending_reboot(),
    )
    result = shell.run_powershell(
        pslib.with_helpers(_NETWORK_SCRIPT), variables={"Domain": domain}, timeout=120, cancel=cancel
    )
    lines = [line for line in result.output.splitlines() if line.startswith("{")]
    if result.ok and lines:
        try:
            facts.network = json.loads(lines[-1])
        except ValueError as exc:
            facts.network_error = f"Kết quả không đọc được: {exc}"
    else:
        facts.network_error = result.output.strip().splitlines()[-1] if result.output.strip() else f"mã lỗi {result.code}"
    return facts


# ---------------------------------------------------------------- đánh giá


def _network_checks(facts: Facts) -> list[Check]:
    network = facts.network
    if network is None:
        return [Check("network", "Mạng", "bad", f"Không kiểm tra được mạng: {facts.network_error}")]
    checks: list[Check] = []
    adapters = network.get("adapters") or []
    with_gateway = [adapter for adapter in adapters if adapter.get("gateway")]
    if not adapters:
        checks.append(Check("network", "Mạng", "bad", "Không có card mạng nào đang kết nối",
                            "Cắm dây mạng hoặc kết nối Wi-Fi của công ty"))
    elif not with_gateway:
        checks.append(Check("network", "Mạng", "bad", "Card mạng không có gateway",
                            "Kiểm tra DHCP hoặc cấu hình IP của card mạng"))
    else:
        names = ", ".join(f"{adapter.get('name')} {', '.join(adapter.get('ipv4') or [])}" for adapter in with_gateway)
        wireless = any(adapter.get("wireless") for adapter in with_gateway)
        hint = "Nên cắm dây mạng khi join domain và cài phần mềm" if wireless else ""
        checks.append(Check("network", "Mạng", "warn" if wireless else "ok", names, hint))

    if network.get("internet"):
        checks.append(Check("internet", "Internet", "ok", "Kết nối được www.microsoft.com qua cổng 443"))
    else:
        checks.append(Check("internet", "Internet", "warn", "Không kết nối thẳng được Internet qua cổng 443",
                            "winget và Windows Update cần Internet; kiểm tra proxy hoặc tường lửa"))

    if not facts.domain:
        checks.append(Check("dns", "DNS trỏ về DC", "warn", "Chưa biết tên domain",
                            "Khai báo 'domain' trong site.yaml (xem site.example.yaml)"))
        return checks
    dns = network.get("dns") or []
    good = [item["server"] for item in dns if item.get("finds_dc")]
    bad = [item["server"] for item in dns if not item.get("finds_dc")]
    if not dns:
        checks.append(Check("dns", "DNS trỏ về DC", "bad", "Card mạng không có DNS server nào",
                            "Đặt DNS của card mạng về IP của DC"))
    elif not good:
        checks.append(Check("dns", "DNS trỏ về DC", "bad",
                            f"DNS {', '.join(bad)} không tìm được DC của {facts.domain}",
                            "Đặt DNS của card mạng về IP của DC (hoặc sửa DHCP), không dùng DNS công cộng"))
    elif bad:
        checks.append(Check("dns", "DNS trỏ về DC", "warn",
                            f"DNS {', '.join(good)} tìm được DC, nhưng DNS {', '.join(bad)} thì không",
                            "Bỏ DNS phụ không phải của DC, nếu không đăng nhập domain lúc được lúc không"))
    else:
        checks.append(Check("dns", "DNS trỏ về DC", "ok", f"DNS {', '.join(good)} tìm được DC của {facts.domain}"))

    if not good:
        checks.append(Check("dc", "Kết nối DC", "skip", "Bỏ qua vì DNS chưa tìm được DC"))
        checks.append(Check("time", "Giờ so với DC", "skip", "Bỏ qua vì DNS chưa tìm được DC"))
        return checks
    dc = network.get("dc")
    if not dc:
        checks.append(Check("dc", "Kết nối DC", "bad", "Không DC nào trả lời LDAP (cổng 389)",
                            "Kiểm tra tường lửa giữa máy và DC, hoặc DC đang tắt"))
        checks.append(Check("time", "Giờ so với DC", "skip", "Bỏ qua vì không kết nối được DC"))
        return checks
    checks.append(Check("dc", "Kết nối DC", "ok", f"DC {dc} trả lời LDAP"))
    offset = network.get("offset")
    if not isinstance(offset, (int, float)):
        checks.append(Check("time", "Giờ so với DC", "warn", f"Không hỏi được giờ của DC {dc} (cổng UDP 123)"))
    elif abs(offset) > TIME_MAX_SECONDS:
        checks.append(Check("time", "Giờ so với DC", "bad", f"Lệch {abs(offset):.0f} giây (quá 5 phút thì join domain lỗi)",
                            "Bấm Đồng bộ giờ, hoặc chỉnh giờ và múi giờ (UTC+7) bằng tay", fix="dom.time_sync"))
    elif abs(offset) > TIME_WARN_SECONDS:
        checks.append(Check("time", "Giờ so với DC", "warn", f"Lệch {abs(offset):.0f} giây", "Nên đồng bộ giờ",
                            fix="dom.time_sync"))
    else:
        checks.append(Check("time", "Giờ so với DC", "ok", f"Lệch {abs(offset):.1f} giây"))
    return checks


def evaluate(facts: Facts) -> list[Check]:
    checks = [
        Check("admin", "Quyền admin", "ok", "Tool đang chạy bằng quyền admin") if facts.is_admin else
        Check("admin", "Quyền admin", "bad", "Tool không có quyền admin", "Mở lại tool và bấm Yes ở hộp thoại UAC"),
    ]
    if facts.build >= MIN_BUILD:
        checks.append(Check("windows", "Bản Windows", "ok", facts.os_label))
    else:
        checks.append(Check("windows", "Bản Windows", "bad", f"{facts.os_label}: cũ hơn Win10 22H2",
                            "Cập nhật lên Win10 22H2 hoặc cài Win11"))
    if facts.pending_reboot:
        checks.append(Check("reboot", "Chờ khởi động lại", "warn", "Máy đang chờ khởi động lại: " + ", ".join(facts.pending_reboot),
                            "Khởi động lại trước khi join domain hoặc cài phần mềm, tránh bộ cài báo lỗi 1618 / 3010"))
    else:
        checks.append(Check("reboot", "Chờ khởi động lại", "ok", "Không có việc nào đang chờ khởi động lại"))
    checks += _network_checks(facts)
    if facts.joined_domain:
        checks.insert(0, Check("joined", "Domain", "ok", f"Máy đã vào domain {facts.domain}",
                               "Bỏ qua bước đổi tên + join; vẫn cài phần mềm và cấu hình được"))

    if not facts.share_root:
        checks.append(Check("share", "Thư mục share", "warn", "Chưa khai báo share_root trong site.yaml",
                            "Không cài được phần mềm từ share; danh mục dùng bản đóng gói kèm tool"))
    elif facts.share_ok:
        checks.append(Check("share", "Thư mục share", "ok", f"Vào được {facts.share_root}"))
    else:
        hint = "Máy chưa vào domain thì vào share cần tài khoản: join domain trước rồi cài phần mềm từ share sau" \
            if not facts.joined_domain else "Kiểm tra quyền của tài khoản trên share và đường dẫn trong site.yaml"
        checks.append(Check("share", "Thư mục share", "bad" if facts.joined_domain else "warn",
                            f"Không vào được {facts.share_root}", hint))

    if facts.winget:
        checks.append(Check("winget", "winget", "ok", "Có winget"))
    else:
        checks.append(Check("winget", "winget", "warn", "Không có winget cho tài khoản đang chạy tool",
                            "Cập nhật App Installer từ Microsoft Store, hoặc chờ nút cài lại winget từ share (GĐ2)"))

    free = facts.disk_free_gb
    disk_state = "ok" if free >= DISK_OK_GB else ("warn" if free >= DISK_MIN_GB else "bad")
    checks.append(Check("disk", "Dung lượng ổ hệ thống", disk_state, f"Còn trống {free:.0f} GB",
                        "" if disk_state == "ok" else f"Nên còn ít nhất {DISK_OK_GB} GB trước khi cài Office và cập nhật"))

    if not facts.has_battery:
        checks.append(Check("power", "Nguồn điện", "ok", "Máy không dùng pin"))
    elif facts.on_ac:
        checks.append(Check("power", "Nguồn điện", "ok", "Laptop đang cắm sạc"))
    else:
        checks.append(Check("power", "Nguồn điện", "warn", "Laptop đang chạy bằng pin",
                            "Cắm sạc: cài đặt và cập nhật lâu, hết pin giữa chừng dễ hỏng máy"))
    return checks


def summary(checks: list[Check]) -> tuple[str, str]:
    """(trạng thái chung, câu tóm tắt)."""
    bad = [check.name for check in checks if check.state == "bad"]
    warn = [check.name for check in checks if check.state == "warn"]
    if bad:
        return "bad", f"Cần xử lý trước khi cài: {', '.join(bad)}"
    if warn:
        return "warn", f"Cài được, nhưng nên xem: {', '.join(warn)}"
    return "ok", "Máy sẵn sàng để cài"


def to_text(checks: list[Check], computer_name: str) -> str:
    marks = {"ok": "✔", "warn": "⚠", "bad": "✖", "skip": "–"}
    lines = [f"Kiểm tra trước khi cài máy {computer_name}", summary(checks)[1], ""]
    for check in checks:
        line = f"{marks[check.state]} {check.name}: {check.detail}"
        if check.hint:
            line += f" → {check.hint}"
        lines.append(line)
    return "\n".join(lines)
