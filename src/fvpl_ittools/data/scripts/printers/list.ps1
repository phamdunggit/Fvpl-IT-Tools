# Danh sách máy in và driver cho trang Máy in. Chỉ đọc, không đổi gì trên máy.
# Biến $TargetUserSid do tool truyền vào: người đang đăng nhập (có thể khác tài khoản chạy tool).

function ConvertTo-Connection([string]$KeyName) {
    # Khoá máy in share có dạng ",,máy,tên máy in" (tên máy in không có dấu phẩy) thành \\máy\tên máy in.
    $parts = $KeyName.Split(',')
    if ($parts.Count -ge 4 -and $parts[2] -and $parts[3]) { return '\\' + $parts[2] + '\' + $parts[3] }
}

function Get-Connections([string]$Key) {
    if (-not (Test-Path -LiteralPath $Key)) { return }
    Get-ChildItem -LiteralPath $Key | ForEach-Object { ConvertTo-Connection $_.PSChildName } | Where-Object { $_ }
}

$me = [Security.Principal.WindowsIdentity]::GetCurrent()
$otherUser = [bool]($TargetUserSid -and $TargetUserSid -ne $me.User.Value)

$tcpPorts = @{}
$jobs = @{}
$printers = @()
$drivers = @()
$listError = ''
try {
    foreach ($port in @(Get-CimInstance Win32_TCPIPPrinterPort)) {
        if ($port.Name) { $tcpPorts[[string]$port.Name] = [string]$port.HostAddress }
    }
    foreach ($job in @(Get-CimInstance Win32_PrintJob)) {
        # Tên lệnh in dạng "tên máy in, số lệnh".
        $printerName = ([string]$job.Name -split ',')[0]
        $jobs[$printerName] = 1 + [int]$jobs[$printerName]
    }
    $printers = @(foreach ($p in @(Get-CimInstance Win32_Printer)) {
        $portHost = ''
        if ($p.PortName -and $tcpPorts.ContainsKey([string]$p.PortName)) { $portHost = $tcpPorts[[string]$p.PortName] }
        [pscustomobject]@{
            name = [string]$p.Name
            port = [string]$p.PortName
            host = $portHost
            driver = [string]$p.DriverName
            shared = [bool]$p.Shared
            share_name = [string]$p.ShareName
            status = [int]$p.PrinterStatus
            error_state = [int]$p.DetectedErrorState
            offline = [bool]$p.WorkOffline
            jobs = [int]$jobs[[string]$p.Name]
        }
    })
    $platform = 'Windows x64'
    if ($env:PROCESSOR_ARCHITECTURE -eq 'ARM64') { $platform = 'Windows ARM64' }
    elseif (-not [Environment]::Is64BitOperatingSystem) { $platform = 'Windows NT x86' }
    $drivers = @(Get-CimInstance Win32_PrinterDriver | Where-Object { $_.SupportedPlatform -eq $platform } |
        ForEach-Object { ([string]$_.Name -split ',')[0] } | Sort-Object -Unique)
}
catch {
    $listError = $_.Exception.Message
}

$userConnections = @()
$defaultPrinter = ''
if ($TargetUserSid) {
    $hive = "Registry::HKEY_USERS\$TargetUserSid"
    $userConnections = @(Get-Connections "$hive\Printers\Connections")
    $windows = Get-ItemProperty -LiteralPath "$hive\Software\Microsoft\Windows NT\CurrentVersion\Windows" -ErrorAction SilentlyContinue
    if ($windows -and $windows.Device) { $defaultPrinter = ([string]$windows.Device -split ',')[0] }
}

[pscustomobject]@{
    tool_user = $me.Name
    other_user = $otherUser
    spooler = [string](Get-Service -Name Spooler).Status
    error = $listError
    printers = $printers
    machine_connections = @(Get-Connections 'HKLM:\SYSTEM\CurrentControlSet\Control\Print\Connections')
    user_connections = $userConnections
    default_printer = $defaultPrinter
    drivers = $drivers
} | ConvertTo-Json -Depth 4 -Compress
