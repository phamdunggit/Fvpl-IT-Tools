# Tình huống "Lỗi đăng nhập domain, không vào được ổ chung". CHỈ ĐỌC: DNS → DC, cổng DC, giờ, secure channel, GPO.
$cs = Get-CimInstance Win32_ComputerSystem
if (-not $cs.PartOfDomain) {
    Add-Finding 'not_joined' 'warn' 'Máy chưa vào domain' "Workgroup $($cs.Workgroup)"
}
else {
    $domain = $cs.Domain
    $servers = @(Get-ActiveAdapters | ForEach-Object { $_.Dns } | Where-Object { $_ } | Select-Object -Unique)
    $found = @($servers | Where-Object { Test-DnsSrv $_ "_ldap._tcp.dc._msdcs.$domain" })
    if ($found) { Add-Finding 'dns_dc' 'ok' "DNS tìm được máy chủ domain $domain" ('DNS ' + ($found -join ', ')) }
    else {
        Add-Finding 'dns_no_dc' 'bad' "DNS không tìm được máy chủ domain $domain" `
            ('Đã hỏi DNS ' + ($servers -join ', ') + '. Máy đang ngoài mạng công ty (cần VPN), hoặc DNS của card mạng không trỏ về DC.')
    }

    $dc = $null
    try {
        $addresses = @([System.Net.Dns]::GetHostAddresses($domain) | Where-Object { $_.AddressFamily -eq 'InterNetwork' } |
            ForEach-Object { $_.IPAddressToString })
        $dc = @($addresses | Select-Object -First 5 | Where-Object { Test-Port $_ 389 1500 }) | Select-Object -First 1
    }
    catch { }
    if (-not $dc) {
        Add-Finding 'dc_unreachable' 'bad' 'Không liên lạc được máy chủ domain' "Không DC nào của $domain trả lời cổng 389."
    }
    else {
        $closed = @(foreach ($port in 88, 445) { if (-not (Test-Port $dc $port)) { $port } })
        if ($closed) {
            Add-Finding 'dc_ports' 'bad' "Máy chủ domain $dc không mở cổng $($closed -join ', ')" 'Cổng 88: Kerberos (đăng nhập). Cổng 445: ổ chung, GPO.'
        }
        else { Add-Finding 'dc' 'ok' "Liên lạc được máy chủ domain $dc" }

        $offset = Get-NtpOffset $dc
        if ($null -ne $offset) {
            if ([math]::Abs($offset) -gt 300) {
                Add-Finding 'time_skew' 'bad' ('Giờ máy lệch {0:N0} phút so với máy chủ domain: đăng nhập, ổ chung sẽ lỗi' -f ($offset / 60)) ('{0:N0} giây' -f $offset)
            }
            elseif ([math]::Abs($offset) -gt 60) {
                Add-Finding 'time_skew' 'warn' ('Giờ máy lệch {0:N0} giây so với máy chủ domain' -f $offset)
            }
            else { Add-Finding 'time' 'ok' 'Giờ máy khớp máy chủ domain' }
        }
    }

    if ($dc) {
        try {
            if (Test-ComputerSecureChannel -ErrorAction Stop) { Add-Finding 'trust' 'ok' 'Máy vẫn được domain tin cậy (secure channel tốt)' }
            else {
                Add-Finding 'trust_broken' 'bad' 'Máy bị domain từ chối (lỗi trust relationship)' `
                    'Test-ComputerSecureChannel trả về False: mật khẩu máy với domain bị lệch, thường do khôi phục ảnh máy cũ.'
            }
        }
        catch { Add-Finding 'trust_unknown' 'info' 'Chưa kiểm tra được quan hệ tin cậy với domain (cần mở tool bằng quyền admin)' "$_" }
    }

    # Lần áp Group Policy gần nhất của máy.
    $state = Get-ItemProperty -LiteralPath 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Group Policy\State\Machine\Extension-List\{00000000-0000-0000-0000-000000000000}' -ErrorAction SilentlyContinue
    if ($state -and $state.EndTimeHi) {
        $last = [DateTime]::FromFileTime(([int64][uint32]$state.EndTimeHi -shl 32) -bor [int64][uint32]$state.EndTimeLo)
        $days = [int]((Get-Date) - $last).TotalDays
        if ($days -gt 7) { Add-Finding 'gpo_old' 'warn' "Đã $days ngày máy chưa nhận Group Policy" ('Lần cuối ' + $last.ToString('dd/MM/yyyy HH:mm')) }
        else { Add-Finding 'gpo' 'ok' ('Máy nhận Group Policy lúc ' + $last.ToString('dd/MM/yyyy HH:mm')) }
    }
    Add-Finding 'share_tip' 'info' 'Vừa đổi mật khẩu hoặc vừa được cấp quyền ổ chung mà vẫn bị từ chối: xoá vé đăng nhập cũ (Kerberos)'
}
