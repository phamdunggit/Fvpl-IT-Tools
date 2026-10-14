# Tình huống "Không in được". CHỈ ĐỌC: dịch vụ in, máy in, lệnh in kẹt, máy in IP / share có trả lời không.
$virtual = 'Microsoft Print to PDF|Microsoft XPS Document Writer|OneNote|^Fax$|Adobe PDF|Foxit PDF'

$spooler = Get-Service -Name Spooler -ErrorAction SilentlyContinue
if (-not $spooler) { Add-Finding 'spooler_down' 'bad' 'Không thấy dịch vụ in của Windows (Print Spooler)' }
elseif ($spooler.Status -ne 'Running') {
    Add-Finding 'spooler_down' 'bad' 'Dịch vụ in của Windows đang tắt' "Spooler: $($spooler.Status), khởi động: $($spooler.StartType)"
}
else { Add-Finding 'spooler' 'ok' 'Dịch vụ in của Windows đang chạy' }

$printers = @(Get-CimInstance Win32_Printer -ErrorAction SilentlyContinue | Where-Object { $_.Name -notmatch $virtual })
if (-not $printers) {
    Add-Finding 'no_printer' 'bad' 'Máy chưa có máy in nào (chỉ có máy in ảo như PDF)'
}
else {
    $default = @($printers | Where-Object { $_.Default }) | Select-Object -First 1
    if ($default) { Add-Finding 'default' 'ok' "Máy in mặc định: $($default.Name)" }
    else { Add-Finding 'no_default' 'warn' 'Chưa chọn máy in mặc định nên lệnh in có thể đi nhầm máy in' }

    $ports = @{}
    Get-CimInstance Win32_TCPIPPrinterPort -ErrorAction SilentlyContinue | ForEach-Object { $ports[$_.Name] = $_.HostAddress }
    $checkedHosts = @{}
    foreach ($printer in $printers) {
        $offline = $printer.WorkOffline -or $printer.PrinterStatus -eq 7
        $address = $null
        if ($printer.Network -and -not $printer.Local -and $printer.ServerName) {
            # Máy in share: máy chia sẻ phải trả lời cổng 445.
            $server = ([string]$printer.ServerName).TrimStart('\')
            if (-not $checkedHosts.ContainsKey($server)) { $checkedHosts[$server] = Test-Port $server 445 2000 }
            if (-not $checkedHosts[$server]) {
                Add-Finding 'share_unreachable' 'bad' "Không kết nối được máy chia sẻ máy in $server ($($printer.Name))" `
                    'Cổng 445 của máy chia sẻ không trả lời: máy đó đang tắt, khác mạng, hoặc firewall chặn File and Printer Sharing.'
                continue
            }
        }
        elseif ($ports.ContainsKey([string]$printer.PortName)) {
            $address = $ports[[string]$printer.PortName]
            if (-not $checkedHosts.ContainsKey($address)) { $checkedHosts[$address] = (Test-Port $address 9100 1500) -or (Test-Ping $address) }
            if (-not $checkedHosts[$address]) {
                Add-Finding 'printer_unreachable' 'bad' "Máy in $($printer.Name) ($address) không trả lời" `
                    "Không ping được $address và cổng 9100 không mở."
                continue
            }
        }
        if ($offline) { Add-Finding 'printer_offline' 'warn' "Windows đang báo máy in $($printer.Name) ngoại tuyến (offline)" }
    }

    # Máy in share trên Win11 22H2 trở lên: Windows mặc định gọi RPC qua TCP, máy chia sẻ Win10 cũ hay không nhận.
    $shared = @($printers | Where-Object { $_.Network -and -not $_.Local })
    $build = [int](Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion').CurrentBuildNumber
    if ($shared -and $build -ge 22621) {
        $rpc = (Get-ItemProperty -LiteralPath 'HKLM:\SOFTWARE\Policies\Microsoft\Windows NT\Printers\RPC' -ErrorAction SilentlyContinue).RpcUseNamedPipeProtocol
        if ($rpc -ne 1) {
            Add-Finding 'share_rpc' 'warn' 'Máy này là Windows 11 mới, dùng máy in share: có thể bị chặn cách kết nối kiểu cũ (lỗi 0x00000709, 0x0000007c)' `
                "Build $build, RpcUseNamedPipeProtocol chưa đặt."
        }
    }
}

# Lệnh in kẹt: lệnh báo lỗi / tạm dừng, hoặc chờ quá 10 phút.
$jobs = @(Get-CimInstance Win32_PrintJob -ErrorAction SilentlyContinue)
$stuck = @($jobs | Where-Object {
    ([string]$_.JobStatus -match 'Error|Paused|Offline|Blocked|Deleting') -or
    ($_.TimeSubmitted -and ((Get-Date) - $_.TimeSubmitted).TotalMinutes -gt 10)
})
if ($stuck) {
    $names = ($stuck | ForEach-Object { ([string]$_.Name -split ',')[0] } | Select-Object -Unique) -join ', '
    Add-Finding 'queue_stuck' 'bad' "Có $($stuck.Count) lệnh in bị kẹt ($names)" `
        (($stuck | ForEach-Object { '{0}: {1} ({2})' -f $_.Name, $_.Document, $_.JobStatus }) -join '; ')
}
elseif ($jobs) { Add-Finding 'queue' 'ok' "Có $($jobs.Count) lệnh in đang chờ, chưa thấy kẹt" }
else { Add-Finding 'queue' 'ok' 'Không có lệnh in nào bị kẹt' }
