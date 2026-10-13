"""Hàm PowerShell dựng sẵn cho script chẩn đoán và script thu thập thông tin máy.

Chỉ được thêm vào script nào có gọi tới (xem docs/ACTIONS.md). Các hàm dùng WMI/CIM và .NET trực tiếp:
cmdlet như Get-NetAdapter, Get-NetIPConfiguration, Get-PhysicalDisk, Resolve-DnsName phải nạp module
trước khi chạy, có máy mất 10–30 giây cho mỗi module.
"""

from __future__ import annotations

import re

CHECK_HELPERS = r"""$Checks = @{ Failed = 0 }
# Ghi thẳng ra stdout: dòng in ra không bị lẫn vào giá trị trả về của hàm gọi chúng (như Write-Output),
# và không thành khối CLIXML khi stderr bị chuyển hướng (như Write-Host).
function Write-Line([string]$Text) { [Console]::Out.WriteLine($Text) }
function Write-Ok([string]$Text) { Write-Line "✔ $Text" }
function Write-Bad([string]$Text) { Write-Line "✖ $Text"; $Checks.Failed++ }
function Write-Warn([string]$Text) { Write-Line "⚠ $Text" }
function Exit-Checks { if ($Checks.Failed) { exit 2 } }
function Test-Ping([string]$Target, [int]$Timeout = 1500) {
    try { return (New-Object System.Net.NetworkInformation.Ping).Send($Target, $Timeout).Status -eq 'Success' }
    catch { return $false }
}
function Test-Port([string]$Target, [int]$Port, [int]$Timeout = 2000) {
    $client = New-Object System.Net.Sockets.TcpClient
    try { return $client.ConnectAsync($Target, $Port).Wait($Timeout) -and $client.Connected }
    catch { return $false }
    finally { $client.Close() }
}
function Get-NtpOffset([string]$Server, [int]$Timeout = 2000) {
    # Số giây giờ máy này lệch so với $Server (dương = máy này chậm hơn), hoặc $null nếu không hỏi được.
    $udp = New-Object System.Net.Sockets.UdpClient
    try {
        $udp.Client.ReceiveTimeout = $Timeout
        $udp.Connect($Server, 123)
        $request = New-Object byte[] 48
        $request[0] = 0x1B
        $sent = [DateTime]::UtcNow
        [void]$udp.Send($request, 48)
        $remote = New-Object System.Net.IPEndPoint([System.Net.IPAddress]::Any, 0)
        $reply = $udp.Receive([ref]$remote)
        $received = [DateTime]::UtcNow
        $seconds = [BitConverter]::ToUInt32([byte[]]($reply[43], $reply[42], $reply[41], $reply[40]), 0)
        $fraction = [BitConverter]::ToUInt32([byte[]]($reply[47], $reply[46], $reply[45], $reply[44]), 0)
        $serverTime = (New-Object DateTime(1900, 1, 1, 0, 0, 0, [DateTimeKind]::Utc)).AddSeconds($seconds + $fraction / 4294967296.0)
        $localTime = $sent.AddTicks(($received - $sent).Ticks / 2)
        return ($serverTime - $localTime).TotalSeconds
    }
    catch { return $null }
    finally { $udp.Close() }
}
function Test-DnsSrv([string]$Server, [string]$Name, [int]$Timeout = 1500) {
    # True nếu DNS server $Server trả lời có bản ghi SRV $Name. Hỏi thẳng bằng UDP để có timeout thật.
    $udp = New-Object System.Net.Sockets.UdpClient
    try {
        $udp.Client.ReceiveTimeout = $Timeout
        $udp.Connect($Server, 53)
        $packet = New-Object System.Collections.Generic.List[byte]
        # Header: ID, cờ hỏi đệ quy, 1 câu hỏi, 1 bản ghi thêm (EDNS, để nhận được gói lớn khi có nhiều DC).
        $packet.AddRange([byte[]](0x46, 0x56, 0x01, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01))
        foreach ($label in $Name.TrimEnd('.').Split('.')) {
            $bytes = [Text.Encoding]::ASCII.GetBytes($label)
            $packet.Add([byte]$bytes.Length)
            $packet.AddRange($bytes)
        }
        # Hết tên, kiểu SRV (33), lớp IN, rồi bản ghi OPT cho gói UDP tới 4096 byte.
        $packet.AddRange([byte[]](0x00, 0x00, 0x21, 0x00, 0x01, 0x00, 0x00, 0x29, 0x10, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00))
        [void]$udp.Send($packet.ToArray(), $packet.Count)
        $remote = New-Object System.Net.IPEndPoint([System.Net.IPAddress]::Any, 0)
        $reply = $udp.Receive([ref]$remote)
        $truncated = ($reply[2] -band 0x02) -ne 0
        $answers = $reply[6] * 256 + $reply[7]
        return ($reply[3] -band 0x0F) -eq 0 -and ($answers -gt 0 -or $truncated)
    }
    catch { return $false }
    finally { $udp.Close() }
}
function Test-DomainDns([string]$Domain, [string[]]$Servers) {
    # In ✔/✖ cho từng DNS server: có tìm được DC của $Domain không. Trả True nếu ít nhất một server tìm được.
    if (-not $Servers) { Write-Bad 'Card mạng không có DNS server nào.'; return $false }
    $found = $false
    foreach ($server in $Servers) {
        if (Test-DnsSrv $server "_ldap._tcp.dc._msdcs.$Domain") { Write-Ok "DNS $server tìm được DC của domain $Domain"; $found = $true }
        else { Write-Bad "DNS $server không tìm được DC của domain $Domain (DNS này không trỏ về DC)" }
    }
    return $found
}
function Find-DomainController([string]$Domain) {
    # IP của một DC đang trả lời LDAP (cổng 389). Tên domain phân giải ra IP các DC, thử tối đa 5 IP.
    $addresses = @()
    try {
        $addresses = @([System.Net.Dns]::GetHostAddresses($Domain) | Where-Object { $_.AddressFamily -eq 'InterNetwork' } |
            ForEach-Object { $_.IPAddressToString })
    }
    catch { }
    foreach ($address in @($addresses | Select-Object -First 5)) {
        if (Test-Port $address 389 1500) { return $address }
    }
    if ($addresses) { Write-Bad ('Không DC nào trả lời LDAP (đã thử {0})' -f ($addresses -join ', ')) }
    else { Write-Bad "Không phân giải được tên domain $Domain ra IP của DC" }
    return $null
}
function Test-DomainController([string]$Address) {
    # In ✔/✖ cho các cổng DC cần mở và độ lệch giờ so với DC.
    $ports = @{ 53 = 'DNS'; 88 = 'Kerberos'; 389 = 'LDAP'; 445 = 'SMB, ổ mạng và GPO' }
    foreach ($port in 53, 88, 389, 445) {
        if (Test-Port $Address $port) { Write-Ok "DC $Address mở cổng $port ($($ports[$port]))" }
        else { Write-Bad "Không kết nối được cổng $port ($($ports[$port])) của DC $Address" }
    }
    $offset = Get-NtpOffset $Address
    if ($null -eq $offset) { Write-Warn "Không hỏi được giờ của DC $Address (cổng UDP 123)" }
    elseif ([math]::Abs($offset) -gt 300) {
        Write-Bad ('Giờ máy lệch {0:N0} giây so với DC. Lệch quá 5 phút thì đăng nhập domain lỗi, chạy mục Đồng bộ giờ.' -f $offset)
    }
    elseif ([math]::Abs($offset) -gt 60) { Write-Warn ('Giờ máy lệch {0:N0} giây so với DC' -f $offset) }
    else { Write-Ok ('Giờ máy khớp DC (lệch {0:N1} giây)' -f $offset) }
}
function Get-ActiveAdapters {
    # Card đang kết nối có IPv4: card thật, hoặc card ảo có gateway (VPN). Bỏ card ảo nội bộ như vEthernet.
    $configs = @{}
    Get-CimInstance Win32_NetworkAdapterConfiguration -Filter 'IPEnabled = True' | ForEach-Object { $configs[[int]$_.Index] = $_ }
    foreach ($nic in @(Get-CimInstance Win32_NetworkAdapter -Filter 'NetConnectionStatus = 2')) {
        $config = $configs[[int]$nic.Index]
        if (-not $config) { continue }
        $ipv4 = @($config.IPAddress | Where-Object { $_ -match '^\d+\.' })
        $gateway = @($config.DefaultIPGateway | Where-Object { $_ -match '^\d+\.' })
        $physical = $nic.PNPDeviceID -notmatch '^(ROOT|SWD)\\'
        if (-not $ipv4 -or (-not $physical -and -not $gateway)) { continue }
        $key = "HKLM:\SYSTEM\CurrentControlSet\Control\Network\{4D36E972-E325-11CE-BFC1-08002BE10318}\$($nic.GUID)\Connection"
        $subType = (Get-ItemProperty -LiteralPath $key -ErrorAction SilentlyContinue).MediaSubType
        [pscustomobject]@{
            Name        = $nic.NetConnectionID
            Description = $nic.Name
            Mac         = $nic.MACAddress
            Wireless    = ($subType -eq 2)
            Speed       = [int64]$nic.Speed
            Physical    = $physical
            IPv4        = $ipv4
            Gateway     = $gateway
            Dns         = @($config.DNSServerSearchOrder | Where-Object { $_ })
            Dhcp        = [bool]$config.DHCPEnabled
        }
    }
}
"""

_HELPER_NAMES = re.compile(
    r"\b(Write-Line|Write-Ok|Write-Bad|Write-Warn|Exit-Checks|Test-Ping|Test-Port|Get-NtpOffset|Test-DnsSrv|Get-ActiveAdapters"
    r"|Test-DomainDns|Find-DomainController|Test-DomainController)\b",
    re.IGNORECASE,
)


def uses_helpers(script: str) -> bool:
    return _HELPER_NAMES.search(script) is not None


def _split_helpers() -> tuple[str, dict[str, str]]:
    """(phần đầu: biến $Checks, {tên hàm: thân hàm}) theo đúng thứ tự trong CHECK_HELPERS."""
    preamble, *blocks = re.split(r"(?m)^(?=function )", CHECK_HELPERS)
    return preamble, {re.match(r"function ([\w-]+)", block).group(1).lower(): block for block in blocks}


_PREAMBLE, _BLOCKS = _split_helpers()


def _called(text: str) -> set[str]:
    return {match.lower() for match in _HELPER_NAMES.findall(text)}


def with_helpers(script: str) -> str:
    """Thêm vào đầu script các hàm dựng sẵn mà script gọi tới, kèm hàm mà chúng gọi.

    Chỉ thêm hàm cần dùng: cả bộ khoảng 7.000 ký tự, thêm nguyên bộ thì script dài dễ vượt giới hạn dòng lệnh.
    """
    needed = _called(script)
    if not needed:
        return script
    pending = list(needed)
    while pending:
        for name in _called(_BLOCKS[pending.pop()]) - needed:
            needed.add(name)
            pending.append(name)
    return _PREAMBLE + "".join(block for name, block in _BLOCKS.items() if name in needed) + script
