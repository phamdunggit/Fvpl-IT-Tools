# Tình huống "Không vào được mạng". CHỈ ĐỌC: card mạng, IP, gateway, DNS, Internet, proxy, DNS có trỏ về DC.
$adapters = @(Get-ActiveAdapters)
if (-not $adapters) {
    Add-Finding 'no_adapter' 'bad' 'Không có card mạng nào đang kết nối' 'Không card nào ở trạng thái Connected và có địa chỉ IPv4.'
}
else {
    foreach ($adapter in $adapters) {
        $kind = if ($adapter.Wireless) { 'Wi-Fi' } else { 'mạng dây' }
        $detail = 'IP {0} · gateway {1} · DNS {2} · {3}' -f ($adapter.IPv4 -join ', '), ($adapter.Gateway -join ', '),
            ($adapter.Dns -join ', '), $adapter.Description
        if ($adapter.IPv4 -like '169.254.*') {
            Add-Finding 'apipa' 'bad' "$($adapter.Name) ($kind) không xin được địa chỉ IP" $detail
        }
        else { Add-Finding 'adapter' 'ok' "$($adapter.Name) ($kind) có địa chỉ IP $($adapter.IPv4[0])" $detail }
    }

    $gateways = @($adapters | ForEach-Object { $_.Gateway } | Where-Object { $_ } | Select-Object -Unique)
    if (-not $gateways) { Add-Finding 'no_gateway' 'bad' 'Card mạng không có gateway nên không ra được ngoài mạng nội bộ' }
    foreach ($gateway in $gateways) {
        if (Test-Ping $gateway) { Add-Finding 'gateway' 'ok' "Kết nối được router / gateway $gateway" }
        else {
            Add-Finding 'gateway_unreachable' 'warn' "Không ping được router / gateway $gateway" `
                'Một số router chặn ping; xem tiếp dòng Internet bên dưới.'
        }
    }
}

$internetOk = $false
try {
    [void][System.Net.Dns]::GetHostAddresses('www.microsoft.com')
    Add-Finding 'dns' 'ok' 'Phân giải được tên trang web (DNS ra được Internet)'
    if (Test-Port 'www.microsoft.com' 443 3000) {
        $internetOk = $true
        Add-Finding 'internet' 'ok' 'Vào được Internet'
    }
    else {
        Add-Finding 'internet_fail' 'bad' 'Không vào được Internet' 'Không kết nối được www.microsoft.com cổng 443: mạng chặn, hoặc phải đi qua proxy.'
    }
}
catch {
    if ($adapters) { Add-Finding 'dns_fail' 'bad' 'Không phân giải được tên trang web (DNS lỗi)' 'Không tra được www.microsoft.com.' }
}

$settings = "Registry::HKEY_USERS\$TargetUserSid\Software\Microsoft\Windows\CurrentVersion\Internet Settings"
$proxy = Get-ItemProperty -LiteralPath $settings -ErrorAction SilentlyContinue
if ($proxy.ProxyEnable -eq 1 -and $proxy.ProxyServer) {
    $state = if ($internetOk) { 'info' } else { 'bad' }
    Add-Finding 'proxy' $state "Trình duyệt đang đặt proxy $($proxy.ProxyServer)" 'Proxy sai hoặc proxy cũ làm trình duyệt không vào được web.'
}
elseif ($proxy.AutoConfigURL) {
    $state = if ($internetOk) { 'info' } else { 'warn' }
    Add-Finding 'proxy' $state "Trình duyệt đang dùng file cấu hình proxy $($proxy.AutoConfigURL)"
}
$winhttp = (netsh winhttp show proxy) -join ' '
if ($winhttp -notmatch 'Direct access|Truy cập trực tiếp') {
    Add-Finding 'winhttp_proxy' 'warn' 'Windows đang đặt proxy hệ thống (WinHTTP): Windows Update, Office có thể không ra được Internet' $winhttp.Trim()
}

$cs = Get-CimInstance Win32_ComputerSystem
if ($cs.PartOfDomain -and $adapters) {
    $servers = @($adapters | ForEach-Object { $_.Dns } | Where-Object { $_ } | Select-Object -Unique)
    $found = @($servers | Where-Object { Test-DnsSrv $_ "_ldap._tcp.dc._msdcs.$($cs.Domain)" })
    if ($found) { Add-Finding 'dns_dc' 'ok' "DNS tìm được máy chủ domain $($cs.Domain)" ('DNS ' + ($found -join ', ')) }
    else {
        Add-Finding 'dns_no_dc' 'warn' "DNS không tìm được máy chủ domain $($cs.Domain): ổ chung, đăng nhập domain sẽ lỗi" `
            ('Đã hỏi DNS ' + ($servers -join ', ') + '. Máy đang ngoài mạng công ty, hoặc DNS của card mạng không trỏ về DC.')
    }
}
