# Tình huống "Windows Update lỗi". CHỈ ĐỌC: dịch vụ, chờ khởi động lại, lịch sử cài, ổ đĩa.
$service = Get-Service -Name wuauserv -ErrorAction SilentlyContinue
if ($service -and $service.StartType -eq 'Disabled') {
    Add-Finding 'service_disabled' 'bad' 'Dịch vụ Windows Update đang bị tắt hẳn (Disabled)' 'Có thể do phần mềm "chặn update" hoặc GPO.'
}

$pending = (Test-Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired') -or
    (Test-Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending')
if ($pending) { Add-Finding 'reboot_pending' 'warn' 'Có bản cập nhật đang chờ khởi động lại máy để cài xong' }

try {
    $searcher = (New-Object -ComObject Microsoft.Update.Session).CreateUpdateSearcher()
    $total = $searcher.GetTotalHistoryCount()
    $history = @(if ($total) { $searcher.QueryHistory(0, [math]::Min($total, 80)) })
    $installs = @($history | Where-Object { $_.Operation -eq 1 -and $_.Title -notmatch 'Defender|Security Intelligence|Security platform|Malicious Software' })
    $lastOk = $installs | Where-Object { $_.ResultCode -eq 2 } | Sort-Object Date -Descending | Select-Object -First 1
    $since = (Get-Date).AddDays(-30)
    $failed = @($installs | Where-Object { $_.ResultCode -in 4, 5 -and $_.Date -gt $since })
    if ($failed) {
        $codes = ($failed | ForEach-Object { '0x{0:X8}' -f ($_.HResult -band 0xFFFFFFFF) } | Select-Object -Unique) -join ', '
        Add-Finding 'recent_failures' 'bad' "$($failed.Count) lần cài bản cập nhật bị lỗi trong 30 ngày qua" `
            ("Mã lỗi: $codes. " + (($failed | Select-Object -First 3 | ForEach-Object { $_.Title }) -join '; '))
    }
    if ($lastOk) {
        $days = [int]((Get-Date) - $lastOk.Date.ToLocalTime()).TotalDays
        if ($days -gt 45) { Add-Finding 'outdated' 'bad' "Đã $days ngày Windows không cài được bản cập nhật nào" $lastOk.Title }
        else { Add-Finding 'updated' 'ok' "Windows cài bản cập nhật gần nhất cách đây $days ngày" $lastOk.Title }
    }
    elseif ($total) { Add-Finding 'outdated' 'bad' 'Chưa thấy lần cài bản cập nhật Windows nào thành công' }
    else { Add-Finding 'no_history' 'warn' 'Máy chưa có lịch sử cập nhật (máy mới cài hoặc lịch sử đã bị xoá)' }
}
catch { Add-Finding 'history_error' 'warn' 'Không đọc được lịch sử cập nhật: thành phần Windows Update có thể đang lỗi' "$_" }

$drive = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID = '$($env:SystemDrive)'"
if ($drive -and $drive.FreeSpace -lt 10GB) {
    Add-Finding 'disk_low' 'warn' ('Ổ hệ thống chỉ còn {0:N1} GB: bản cập nhật lớn cần 10 GB trống' -f ($drive.FreeSpace / 1GB))
}
