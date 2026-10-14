# Tình huống "Máy chậm, đầy ổ". CHỈ ĐỌC: ổ hệ thống, RAM, bộ nhớ đang dùng, thời gian chưa khởi động lại, startup, HDD.
$os = Get-CimInstance Win32_OperatingSystem
$cs = Get-CimInstance Win32_ComputerSystem

$drive = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID = '$($env:SystemDrive)'"
if ($drive -and $drive.Size) {
    $freeGb = [math]::Round($drive.FreeSpace / 1GB, 1)
    $percent = [math]::Round($drive.FreeSpace * 100 / $drive.Size)
    $text = "Ổ $($env:SystemDrive.TrimEnd(':')) còn trống $freeGb GB ($percent%)"
    if ($percent -lt 5 -or $freeGb -lt 5) { Add-Finding 'disk_low' 'bad' "${text}: gần đầy, máy sẽ rất chậm" }
    elseif ($percent -lt 10 -or $freeGb -lt 15) { Add-Finding 'disk_low' 'warn' "${text}: sắp đầy" }
    else { Add-Finding 'disk' 'ok' $text }
}

$ramGb = [math]::Round($cs.TotalPhysicalMemory / 1GB)
if ($ramGb -lt 8) {
    Add-Finding 'ram_low' 'warn' "Máy chỉ có $ramGb GB RAM: chạy Windows 11 và trình duyệt sẽ chậm" 'Nên nâng lên 8 GB trở lên. Tạm thời giảm hiệu ứng hình ảnh.'
}
else { Add-Finding 'ram' 'ok' "Máy có $ramGb GB RAM" }

$freePercent = [math]::Round($os.FreePhysicalMemory * 100 / $os.TotalVisibleMemorySize)
if ($freePercent -lt 15) {
    $top = Get-Process | Sort-Object WorkingSet64 -Descending | Select-Object -First 5 |
        ForEach-Object { '{0} {1:N0} MB' -f $_.ProcessName, ($_.WorkingSet64 / 1MB) }
    Add-Finding 'memory_busy' 'warn' "RAM đang gần hết (còn $freePercent%): đóng bớt chương trình không dùng" ('Dùng nhiều nhất: ' + ($top -join ', '))
}

$uptime = (Get-Date) - $os.LastBootUpTime
if ($uptime.TotalDays -gt 7) {
    Add-Finding 'uptime' 'warn' ('Máy chạy liên tục {0:N0} ngày chưa khởi động lại' -f $uptime.TotalDays) 'Khởi động lại máy giải phóng bộ nhớ và hoàn tất bản cập nhật đang chờ.'
}

$count = 0
foreach ($key in 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run', 'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Run',
                 "Registry::HKEY_USERS\$TargetUserSid\Software\Microsoft\Windows\CurrentVersion\Run") {
    $item = Get-Item -LiteralPath $key -ErrorAction SilentlyContinue
    if ($item) { $count += @($item.GetValueNames() | Where-Object { $_ }).Count }
}
foreach ($folder in "$env:ProgramData\Microsoft\Windows\Start Menu\Programs\StartUp",
                    (Join-Path $TargetUserProfile 'AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup')) {
    if ($folder -and (Test-Path -LiteralPath $folder)) { $count += @(Get-ChildItem -LiteralPath $folder -File -ErrorAction SilentlyContinue).Count }
}
if ($count -gt 12) { Add-Finding 'startup_many' 'warn' "Có $count chương trình chạy cùng Windows: máy khởi động chậm" }
else { Add-Finding 'startup' 'ok' "Có $count chương trình chạy cùng Windows" }

try {
    $disks = @(Get-CimInstance -Namespace root/Microsoft/Windows/Storage -ClassName MSFT_PhysicalDisk -ErrorAction Stop)
    if ($disks -and -not ($disks | Where-Object { $_.MediaType -eq 4 }) -and ($disks | Where-Object { $_.MediaType -eq 3 })) {
        Add-Finding 'hdd' 'info' 'Máy dùng ổ cứng HDD: thay bằng SSD là cách làm máy nhanh lên rõ nhất'
    }
}
catch { }
