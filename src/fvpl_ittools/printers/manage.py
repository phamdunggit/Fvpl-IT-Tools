"""Máy in trên máy: đọc danh sách và dựng các mục thêm, gỡ, in trang thử cho trang Máy in.

Đọc bằng data/scripts/printers/list.ps1 (chỉ đọc). Thêm và gỡ là mục (Action) chạy qua executor như mọi mục
khác, nên có log, nút Huỷ và lệnh hiện trong khung log. Giá trị IT nhập được kiểm tra rồi mới đặt vào script,
luôn bằng shell.ps_quote, không ghép thẳng vào lệnh.

Máy in share (\\\\máy\\tên) có ba chỗ ở:
- của cả máy (printui /ga): HKLM\\SYSTEM\\CurrentControlSet\\Control\\Print\\Connections, hiện cho mọi người dùng;
- của tài khoản đang chạy tool;
- của người đang đăng nhập (HKU\\<SID>\\Printers\\Connections). Khi IT mở tool bằng tài khoản khác, máy in này không
  hiện trong Win32_Printer của tool: tool đọc từ hive của người dùng và gỡ bằng một tác vụ chạy dưới tên họ.
"""

from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass, field

from ..actions.loader import parse_action
from ..actions.model import Action
from ..core import paths, shell
from ..core.executor import Env

LIST_SCRIPT = paths.DATA_DIR / "scripts" / "printers" / "list.ps1"
LIST_TIMEOUT = 90

KIND_LOCAL = "local"            # máy in tạo trên máy này: IP, USB, WSD, máy in ảo
KIND_SHARE = "share"            # máy in share của tài khoản đang chạy tool
KIND_MACHINE = "machine_share"  # máy in share cho cả máy
KIND_USER = "user_share"        # máy in share của người đang đăng nhập (khác tài khoản chạy tool)

PRINTER_STATUS = {1: "Khác", 2: "Không rõ", 3: "Sẵn sàng", 4: "Đang in", 5: "Đang khởi động", 6: "Dừng in", 7: "Offline"}
ERROR_STATE = {
    3: "Sắp hết giấy", 4: "Hết giấy", 5: "Sắp hết mực", 6: "Hết mực", 7: "Đang mở nắp", 8: "Kẹt giấy",
    9: "Offline", 10: "Cần bảo trì", 11: "Khay ra giấy đầy",
}
PROBLEM_STATES = {4, 6, 7, 8, 9, 10, 11}

# Driver có sẵn trong Windows, cài được mà không cần file của hãng. IPP hợp với phần lớn máy in mạng đời mới.
INBOX_DRIVERS = ("Microsoft IPP Class Driver", "Microsoft PCL6 Class Driver", "Microsoft PS Class Driver",
                 "Generic / Text Only")


class PrinterError(RuntimeError):
    pass


@dataclass(frozen=True)
class Printer:
    name: str
    kind: str
    label: str                  # loại, để hiện
    port: str = ""
    host: str = ""              # IP / tên của máy in mạng (cổng TCP/IP)
    driver: str = ""
    status: str = ""
    problem: bool = False
    jobs: int = 0
    share_name: str = ""        # máy này đang share máy in này với tên đó
    default: bool = False       # máy in mặc định của người đang đăng nhập

    @property
    def is_connection(self) -> bool:
        return self.kind != KIND_LOCAL

    @property
    def server(self) -> str:
        return self.name.lstrip("\\").split("\\")[0] if self.is_connection else ""

    @property
    def where(self) -> str:
        """Địa chỉ để hiện: IP của máy in mạng, máy chia sẻ của máy in share, không thì tên cổng."""
        if self.is_connection:
            return self.server
        if not self.host and self.port.upper().startswith("WSD"):
            return "WSD (tự dò)"  # tên cổng WSD là một chuỗi GUID dài, xem ở tooltip
        return self.host or self.port


@dataclass
class Snapshot:
    printers: list[Printer] = field(default_factory=list)
    drivers: list[str] = field(default_factory=list)
    spooler: str = ""
    error: str = ""
    other_user: bool = False


# ---------------------------------------------------------------- đọc danh sách


def _items(value) -> list:
    if value is None or value == {}:
        return []
    return value if isinstance(value, list) else [value]


def _status(raw: dict) -> tuple[str, bool]:
    if raw.get("offline"):
        return "Đang để Use Printer Offline", True
    state = int(raw.get("error_state") or 0)
    if state in PROBLEM_STATES:
        return ERROR_STATE[state], True
    status = int(raw.get("status") or 0)
    return PRINTER_STATUS.get(status, ""), status in (6, 7)


def _local_label(port: str, host: str) -> str:
    upper = port.upper()
    if host:
        return "Mạng (IP)"
    if upper.startswith("WSD"):
        return "Mạng (WSD)"
    if upper.startswith("USB"):
        return "USB"
    if upper.startswith(("LPT", "COM")):
        return f"Cổng {port.rstrip(':')}"
    return "Khác / máy in ảo"


def parse_snapshot(data: dict) -> Snapshot:
    other = bool(data.get("other_user"))
    machine = {str(name).lower() for name in _items(data.get("machine_connections"))}
    default = str(data.get("default_printer") or "").lower()
    share_label = "Share (tài khoản chạy tool)" if other else "Share"
    printers: list[Printer] = []
    seen: set[str] = set()

    def add(printer: Printer) -> None:
        printers.append(printer)
        seen.add(printer.name.lower())

    for raw in _items(data.get("printers")):
        name = str(raw.get("name") or "")
        if not name or name.lower() in seen:
            continue
        status, problem = _status(raw)
        port, host = str(raw.get("port") or ""), str(raw.get("host") or "")
        if name.startswith("\\\\"):
            kind = KIND_MACHINE if name.lower() in machine else KIND_SHARE
            label = "Share (cả máy)" if kind == KIND_MACHINE else share_label
            share_name = ""  # Shared = True ở đây là của máy chia sẻ, không phải máy này
        else:
            kind, label = KIND_LOCAL, _local_label(port, host)
            share_name = str(raw.get("share_name") or "") if raw.get("shared") else ""
        add(Printer(name, kind, label, port=port, host=host, driver=str(raw.get("driver") or ""),
                    status=status, problem=problem, jobs=int(raw.get("jobs") or 0), share_name=share_name,
                    default=name.lower() == default))

    for name in _items(data.get("machine_connections")):
        if str(name).lower() not in seen:
            add(Printer(str(name), KIND_MACHINE, "Share (cả máy)", status="Chưa hiện: khởi động lại Spooler",
                        default=str(name).lower() == default))
    for name in _items(data.get("user_connections")):
        if str(name).lower() not in seen:
            kind, label = (KIND_USER, "Share (người đang đăng nhập)") if other else (KIND_SHARE, share_label)
            add(Printer(str(name), kind, label, status="" if other else "Không đọc được trạng thái",
                        default=str(name).lower() == default))

    order = {KIND_LOCAL: 0, KIND_MACHINE: 1, KIND_USER: 2, KIND_SHARE: 3}
    printers.sort(key=lambda item: (order[item.kind], item.name.lower()))
    return Snapshot(
        printers=printers,
        drivers=[str(name) for name in _items(data.get("drivers")) if name],
        spooler=str(data.get("spooler") or ""),
        error=str(data.get("error") or ""),
        other_user=other,
    )


def snapshot(env: Env, cancel: threading.Event | None = None) -> Snapshot:
    script = LIST_SCRIPT.read_text(encoding="utf-8")
    result = shell.run_powershell(script, variables={"TargetUserSid": env.target_user.sid},
                                  timeout=LIST_TIMEOUT, cancel=cancel)
    if result.cancelled:
        raise PrinterError("Đã huỷ")
    if result.timed_out:
        raise PrinterError(f"Quá {LIST_TIMEOUT} giây chưa đọc xong danh sách máy in")
    lines = [line for line in result.output.splitlines() if line.startswith("{")]
    if result.code != 0 or not lines:
        detail = result.output.strip().splitlines()[-1] if result.output.strip() else f"mã lỗi {result.code}"
        raise PrinterError(detail)
    try:
        return parse_snapshot(json.loads(lines[-1]))
    except (ValueError, TypeError) as exc:
        raise PrinterError(f"Kết quả không đọc được: {exc}") from exc


def driver_choices(installed: list[str]) -> list[tuple[str, bool]]:
    """(tên driver, đã cài chưa): driver đã cài trước, sau đó driver có sẵn trong Windows chưa cài."""
    have = {name.lower() for name in installed}
    return [(name, True) for name in installed] + [(name, False) for name in INBOX_DRIVERS if name.lower() not in have]


# ---------------------------------------------------------------- kiểm tra giá trị IT nhập

_ADDRESS = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.\-]{0,252}$")
_SERVER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.\-_]{0,252}$")
# Tên máy in Windows không được có \ , ! ; thêm " vì tên nằm trong ngoặc kép khi gọi printui.
_BAD_NAME_CHARS = set('\\,!"')


def valid_address(text: str) -> bool:
    """IPv4 hoặc tên máy in trong mạng (chữ không dấu, số, dấu chấm, gạch ngang)."""
    return bool(_ADDRESS.match(text))


def valid_printer_name(text: str) -> bool:
    return 0 < len(text) <= 200 and text == text.strip() and not (set(text) & _BAD_NAME_CHARS) \
        and all(ch.isprintable() for ch in text)


def normalize_share(text: str) -> str | None:
    """'\\\\máy\\tên máy in' chuẩn hoá (nhận cả / và thiếu \\\\ đầu), hoặc None nếu không hợp lệ."""
    path = text.strip().replace("/", "\\").lstrip("\\")
    server, _, name = path.partition("\\")
    if not _SERVER.match(server) or not valid_printer_name(name):
        return None
    return f"\\\\{server}\\{name}"


# ---------------------------------------------------------------- mục thêm / gỡ / in thử

_HINTS = """\
function Show-PrintHint([int]$Code) {
    switch ($Code) {
        0x011b { Write-Warn 'Máy chia sẻ đòi mã hoá RPC (0x0000011b). Cập nhật Windows cả hai máy; vẫn lỗi thì chạy mục "Máy chia sẻ máy in: bỏ yêu cầu mã hoá RPC" trên máy chia sẻ.' }
        { $_ -in 0x0709, 0x007c } { Write-Warn 'Hai máy gọi dịch vụ in khác kiểu (Win11 22H2 với Win10). Chạy mục "Máy chia sẻ máy in: cho máy khác kết nối vào" trên máy chia sẻ và "Máy kết nối máy in share: dùng Named Pipes" trên máy này (tab Sửa lỗi).' }
        0x0bcb { Write-Warn 'Không cài được driver từ máy chia sẻ (0x00000bcb). Cài driver trên máy này trước (tab Thêm máy in, máy in qua IP với file .inf, hoặc cài bộ driver của hãng) rồi kết nối lại.' }
        0x06ba { Write-Warn 'Không gọi được dịch vụ in bên máy chia sẻ (0x000006ba). Kiểm tra Print Spooler và firewall máy đó (mục "Máy chia sẻ máy in: cho máy khác kết nối vào").' }
        0x0005 { Write-Warn 'Không có quyền vào máy in này. Kiểm tra quyền share trên máy chia sẻ, hoặc lưu tài khoản của máy đó vào Credential Manager.' }
        default { Write-Warn 'Chạy mục "Kiểm tra share máy in" (tab Sửa lỗi) trên cả hai máy để xem thiếu gì.' }
    }
}
"""

_PRINTUI = """\
function Invoke-PrintUi([string]$Arguments) {
    # rundll32 không có mã thoát dùng được; kết quả kiểm lại bằng registry.
    $process = Start-Process -FilePath (Join-Path $env:SystemRoot 'System32\\rundll32.exe') -ArgumentList $Arguments -PassThru -WindowStyle Hidden
    $null = $process.Handle
    [void]$process.WaitForExit(60000)
}
function Test-ConnectionKey([string]$Key, [string]$Path) {
    $parts = $Path.Substring(2).Split([char]'\\')
    $name = ',,{0},{1}' -f $parts[0], $parts[1]
    return [bool](Get-ChildItem -LiteralPath $Key -ErrorAction SilentlyContinue | Where-Object { $_.PSChildName -eq $name })
}
"""

_ADD_IP = """\
if (Get-CimInstance Win32_Printer | Where-Object { $_.Name -eq $PrinterName }) {
    Write-Bad ('Máy đã có máy in tên "{0}". Đặt tên khác hoặc gỡ máy in đó trước.' -f $PrinterName)
    exit 3
}
if (Test-Port $Address 9100) { Write-Ok ('{0} trả lời ở cổng 9100 (in RAW).' -f $Address) }
elseif (Test-Ping $Address) { Write-Warn ('{0} trả lời ping nhưng không mở cổng 9100. Vẫn thêm; không in được thì xem lại cài đặt mạng của máy in.' -f $Address) }
else { Write-Warn ('Không thấy {0} trả lời: máy in tắt, sai IP hoặc khác mạng. Vẫn thêm máy in.' -f $Address) }

if ($InfPath) {
    Write-Line ('Nạp driver vào kho driver của Windows: {0}' -f $InfPath)
    $output = & pnputil.exe /add-driver $InfPath
    $code = $LASTEXITCODE
    foreach ($line in @($output)) { if ($line) { Write-Line $line } }
    if ($code -ne 0 -and $code -ne 259 -and $code -ne 3010) { Write-Bad ('pnputil báo lỗi {0}.' -f $code); exit 4 }
}
$installed = @(Get-CimInstance Win32_PrinterDriver | ForEach-Object { ([string]$_.Name -split ',')[0] })
if ($installed -notcontains $DriverName) {
    Write-Line ('Cài driver {0}…' -f $DriverName)
    try { Add-PrinterDriver -Name $DriverName }
    catch { Write-Bad ('Không cài được driver "{0}": {1}' -f $DriverName, $_.Exception.Message); exit 4 }
}
$port = 'IP_' + $Address
if (-not (Get-CimInstance Win32_TCPIPPrinterPort | Where-Object { $_.Name -eq $port })) {
    Add-PrinterPort -Name $port -PrinterHostAddress $Address
    Write-Line ('Đã tạo cổng {0}.' -f $port)
}
Add-Printer -Name $PrinterName -DriverName $DriverName -PortName $port
Write-Ok ('Đã thêm máy in "{0}" (cổng {1}, driver {2}).' -f $PrinterName, $port, $DriverName)
"""

_ADD_SHARE = """\
$parts = $SharePath.Substring(2).Split([char]'\\')
$server = $parts[0]
if (-not (Test-Port $server 445)) {
    Write-Bad ('Không vào được máy {0} qua mạng (cổng 445): máy đó tắt, sai tên, hoặc firewall bên đó chặn.' -f $server)
    exit 5
}
if (Get-CimInstance Win32_Printer | Where-Object { $_.Name -eq $SharePath }) {
    Write-Ok ('Tài khoản chạy tool đã kết nối {0} từ trước, driver đã có.' -f $SharePath)
}
else {
    # Kết nối bằng tài khoản chạy tool (quyền admin) để driver được cài vào máy, tránh lỗi 0x00000bcb
    # khi người dùng thường tự kết nối (từ 2021 chỉ admin được cài driver máy in).
    try {
        Add-Printer -ConnectionName $SharePath
        Write-Ok ('Đã kết nối {0} và cài driver bằng quyền admin.' -f $SharePath)
    }
    catch {
        $text = [string]$_.Exception.Message
        try {
            $native = $_.Exception.ErrorData.CimInstanceProperties['error_Code'].Value
            if ($native) { $text += ' (0x{0:X8})' -f [int]$native }
        } catch { }
        Write-Bad ('Không kết nối được {0}: {1}' -f $SharePath, $text)
        $code = 0
        if ($text -match '0x([0-9A-Fa-f]{8})') { $code = [Convert]::ToInt32($Matches[1], 16) -band 0xFFFF }
        Show-PrintHint $code
        exit 2
    }
}
if ($PerMachine) {
    $key = 'HKLM:\\SYSTEM\\CurrentControlSet\\Control\\Print\\Connections'
    Invoke-PrintUi ('printui.dll,PrintUIEntry /ga /n "{0}" /q' -f $SharePath)
    if (-not (Test-ConnectionKey $key $SharePath)) { Write-Bad 'Chưa thêm được máy in cho cả máy (printui /ga).'; exit 6 }
    Write-Line 'Khởi động lại Print Spooler để máy in hiện cho người đang đăng nhập…'
    Restart-Service -Name Spooler -Force
    Write-Ok ('Đã thêm {0} cho mọi người dùng trên máy này. Chưa thấy thì đăng xuất rồi đăng nhập lại.' -f $SharePath)
}
"""

_REMOVE = """\
$found = @(Get-CimInstance Win32_Printer | Where-Object { $_.Name -eq $PrinterName })
$driver = ''
$port = ''
if ($found) { $driver = [string]$found[0].DriverName; $port = [string]$found[0].PortName }

if ($Kind -eq 'machine_share') {
    Invoke-PrintUi ('printui.dll,PrintUIEntry /gd /n "{0}" /q' -f $PrinterName)
    if (Test-ConnectionKey 'HKLM:\\SYSTEM\\CurrentControlSet\\Control\\Print\\Connections' $PrinterName) {
        Write-Bad 'Chưa gỡ được máy in của cả máy (printui /gd).'
        exit 2
    }
    Write-Ok ('Đã gỡ {0} khỏi danh sách máy in của cả máy. Người dùng hết thấy sau khi đăng nhập lại.' -f $PrinterName)
}
elseif ($Kind -eq 'user_share') {
    # Máy in share là của người đang đăng nhập: gỡ bằng một tác vụ chạy dưới tên họ, chạy xong thì xoá tác vụ.
    $key = "Registry::HKEY_USERS\\$TargetUserSid\\Printers\\Connections"
    $taskName = 'FVPL-ITTools-RemovePrinter-' + [guid]::NewGuid().ToString('N').Substring(0, 8)
    $rundll = Join-Path $env:SystemRoot 'System32\\rundll32.exe'
    $taskAction = New-ScheduledTaskAction -Execute $rundll -Argument ('printui.dll,PrintUIEntry /dn /n "{0}" /q' -f $PrinterName)
    $principal = New-ScheduledTaskPrincipal -UserId $TargetUserName -LogonType Interactive -RunLevel Limited
    Register-ScheduledTask -TaskName $taskName -Action $taskAction -Principal $principal -Force | Out-Null
    $gone = $false
    try {
        Start-ScheduledTask -TaskName $taskName
        for ($i = 0; $i -lt 40 -and -not $gone; $i++) {
            Start-Sleep -Milliseconds 500
            $gone = -not (Test-ConnectionKey $key $PrinterName)
        }
    }
    finally {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
    }
    if (-not $gone) {
        Write-Bad ('Chưa gỡ được. {0} phải đang đăng nhập trên máy; hoặc nhờ người dùng tự gỡ trong Settings > Printers.' -f $TargetUserName)
        exit 2
    }
    Write-Ok ('Đã gỡ {0} của {1}.' -f $PrinterName, $TargetUserName)
}
elseif (-not $found) {
    Write-Warn ('Không còn máy in "{0}" trên máy.' -f $PrinterName)
}
else {
    Get-Printer | Where-Object { $_.Name -eq $PrinterName } | Remove-Printer
    Write-Ok ('Đã gỡ máy in "{0}".' -f $PrinterName)
}

if (-not $found) { exit 0 }
# Cổng của máy in share là cổng bên máy chia sẻ, không đụng tới.
$tcp = @()
if ($Kind -eq 'local') { $tcp = @(Get-CimInstance Win32_TCPIPPrinterPort | Where-Object { $_.Name -eq $port }) }
if (-not $RemoveDriver -and -not $tcp) { exit 0 }
# Spooler nhả driver và cổng của máy in vừa gỡ thì mới xoá được.
Restart-Service -Name Spooler -Force
$left = @(Get-CimInstance Win32_Printer)
if ($tcp -and -not ($left | Where-Object { $_.PortName -eq $port })) {
    try { Remove-PrinterPort -Name $port; Write-Line ('Đã xoá cổng {0}.' -f $port) }
    catch { Write-Line ('Giữ cổng {0}: {1}' -f $port, $_.Exception.Message) }
}
if ($RemoveDriver -and $driver) {
    $users = @($left | Where-Object { $_.DriverName -eq $driver } | ForEach-Object { $_.Name })
    if ($users) { Write-Line ('Giữ driver "{0}" vì máy in khác còn dùng: {1}' -f $driver, ($users -join ', ')) }
    else {
        $options = @{ Name = $driver }
        if ((Get-Command Remove-PrinterDriver).Parameters.ContainsKey('RemoveFromDriverStore')) { $options.RemoveFromDriverStore = $true }
        try { Remove-PrinterDriver @options; Write-Ok ('Đã gỡ driver "{0}".' -f $driver) }
        catch { Write-Warn ('Chưa gỡ được driver "{0}": {1} Khởi động lại máy rồi gỡ lại.' -f $driver, $_.Exception.Message) }
    }
}
"""

_TEST_PAGE = """\
$printer = @(Get-CimInstance Win32_Printer | Where-Object { $_.Name -eq $PrinterName })
if (-not $printer) { Write-Bad ('Không thấy máy in "{0}".' -f $PrinterName); exit 2 }
$result = Invoke-CimMethod -InputObject $printer[0] -MethodName PrintTestPage
if ($result.ReturnValue -ne 0) { Write-Bad ('Windows báo lỗi {0} khi in trang thử.' -f $result.ReturnValue); exit 2 }
Write-Ok ('Đã gửi trang in thử tới "{0}". Không ra giấy thì xem hàng đợi và trạng thái máy in.' -f $PrinterName)
"""


def _script(values: dict[str, str], body: str) -> str:
    return shell.ps_variable_lines(values) + body


def _action(action_id: str, name: str, script: str, messages: dict[int, str], description: str,
            timeout: int = 300) -> Action:
    return parse_action({
        "id": action_id, "name": name, "category": "Máy in", "page": "printers", "risk": "safe",
        "description": description,
        "apply": [{"powershell": script, "timeout": timeout, "messages": messages}],
    })


def add_ip_action(address: str, name: str, driver: str, inf_path: str = "") -> Action:
    if not valid_address(address):
        raise ValueError(f"Địa chỉ máy in không hợp lệ: {address!r}")
    if not valid_printer_name(name):
        raise ValueError(f"Tên máy in không hợp lệ: {name!r}")
    if not driver:
        raise ValueError("Chưa chọn driver")
    values = {"Address": address, "PrinterName": name, "DriverName": driver, "InfPath": inf_path}
    return _action(
        "prn.add_ip", f"Thêm máy in {name} ({address})", _script(values, _ADD_IP),
        {3: "Đã có máy in trùng tên", 4: "Không cài được driver"},
        "Tạo cổng TCP/IP tới máy in, cài driver (từ file .inf nếu có) rồi thêm máy in cho cả máy.",
    )


def add_share_action(path: str, per_machine: bool) -> Action:
    share = normalize_share(path)
    if share is None:
        raise ValueError(f"Đường dẫn máy in share không hợp lệ: {path!r}")
    values = {"SharePath": share, "PerMachine": "1" if per_machine else ""}
    return _action(
        "prn.add_share", f"Kết nối máy in {share}", _script(values, _HINTS + _PRINTUI + _ADD_SHARE),
        {2: "Không kết nối được máy in share, xem gợi ý ở trên", 5: "Không vào được máy chia sẻ qua mạng",
         6: "Chưa thêm được máy in cho cả máy"},
        "Kết nối máy in share bằng tài khoản chạy tool để driver được cài bằng quyền admin, "
        "rồi (nếu chọn) thêm cho mọi người dùng trên máy.",
    )


def remove_action(printer: Printer, remove_driver: bool) -> Action:
    values = {"PrinterName": printer.name, "Kind": printer.kind, "RemoveDriver": "1" if remove_driver else ""}
    return _action(
        "prn.remove", f"Gỡ máy in {printer.name}", _script(values, _PRINTUI + _REMOVE),
        {2: "Chưa gỡ được máy in"},
        "Gỡ máy in (kèm cổng TCP/IP không còn dùng), và driver nếu chọn và không máy in nào khác dùng.",
    )


def test_page_action(printer: Printer) -> Action:
    return _action(
        "prn.test_page", f"In trang thử: {printer.name}", _script({"PrinterName": printer.name}, _TEST_PAGE),
        {2: "Không in được trang thử"}, "Gửi trang in thử của Windows tới máy in.", timeout=120,
    )
