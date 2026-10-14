# Tình huống "Lỗi Office, Outlook". CHỈ ĐỌC: bản Office, kích hoạt, ứng dụng đang mở, Teams.
$c2r = Get-ItemProperty -LiteralPath 'HKLM:\SOFTWARE\Microsoft\Office\ClickToRun\Configuration' -ErrorAction SilentlyContinue
$msi = @()
foreach ($root in @($env:ProgramFiles, ${env:ProgramFiles(x86)})) {
    if (-not $root) { continue }
    foreach ($version in 'Office16', 'Office15', 'Office14') {
        if (Test-Path -LiteralPath (Join-Path $root "Microsoft Office\$version\OSPP.VBS")) { $msi += $version }
    }
}

if (-not $c2r -and -not $msi) {
    Add-Finding 'no_office' 'bad' 'Máy chưa cài Office'
}
if ($c2r) {
    Add-Finding 'c2r' 'info' ("Office {0} bản {1} (Click-to-Run): sửa nhanh thường hết lỗi treo, mất nút, báo lỗi khi mở" -f `
        (($c2r.ProductReleaseIds -split ',') -join ', '), $c2r.VersionToReport)
}
if ($msi) {
    $products = @()
    try {
        $products = @(Get-CimInstance SoftwareLicensingProduct -ErrorAction Stop `
            -Filter "ApplicationID='0ff1ce15-a989-479d-af46-f275c6370663' AND PartialProductKey IS NOT NULL")
    }
    catch { }
    try {
        $products += @(Get-CimInstance OfficeSoftwareProtectionProduct -ErrorAction Stop `
            -Filter "ApplicationID='59a52881-a989-479d-af46-f275c6370663' AND PartialProductKey IS NOT NULL")
    }
    catch { }
    $active = @($products | Where-Object { $_.LicenseStatus -eq 1 })
    if ($active) { Add-Finding 'activated' 'ok' "Office bản volume đã kích hoạt ($($active[0].Name))" }
    elseif ($products) {
        Add-Finding 'not_activated' 'bad' 'Office bản volume chưa kích hoạt: sau thời gian dùng thử Office sẽ khoá chức năng sửa file' `
            (($products | ForEach-Object { '{0}: trạng thái {1}' -f $_.Name, $_.LicenseStatus }) -join '; ')
    }
    else { Add-Finding 'not_activated' 'bad' 'Office bản volume chưa có key: chưa kích hoạt được' ($msi -join ', ') }
    Add-Finding 'msi_repair' 'info' 'Office bản volume: sửa bằng Settings > Apps > Microsoft Office > Modify > Repair'
}

$open = @(Get-Process -Name WINWORD, EXCEL, POWERPNT, OUTLOOK, MSACCESS, ONENOTE -ErrorAction SilentlyContinue |
    ForEach-Object ProcessName | Select-Object -Unique)
if ($open) { Add-Finding 'apps_open' 'warn' "Đang mở $($open -join ', '): lưu bài và đóng trước khi sửa Office" }

$teams = @(
    (Join-Path $TargetUserProfile 'AppData\Local\Packages\MSTeams_8wekyb3d8bbwe'),
    (Join-Path $TargetUserProfile 'AppData\Roaming\Microsoft\Teams')
) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }
if ($teams) { Add-Finding 'teams' 'info' 'Teams trắng màn hình, không đăng nhập được: xoá cache Teams (không mất tin nhắn)' }
