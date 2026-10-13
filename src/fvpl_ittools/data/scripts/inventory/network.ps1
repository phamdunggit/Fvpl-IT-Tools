# Card mạng đang kết nối, và DNS của máy có tìm được DC không (hỏi bản ghi SRV của DC qua từng DNS server).

$cs = Get-CimInstance Win32_ComputerSystem
$data.network = @(Get-ActiveAdapters | ForEach-Object {
    [ordered]@{
        name        = $_.Name
        description = $_.Description
        mac         = $_.Mac
        wireless    = $_.Wireless
        speed       = $_.Speed
        ipv4        = $_.IPv4
        gateway     = $_.Gateway
        dns         = $_.Dns
        dhcp        = $_.Dhcp
    }
})

$data.dns_checks = @()
if ($cs.PartOfDomain) {
    $servers = @($data.network | ForEach-Object { $_.dns } | Where-Object { $_ } | Select-Object -Unique)
    $data.dns_checks = @(foreach ($server in $servers) {
        [ordered]@{ server = $server; finds_dc = (Test-DnsSrv $server "_ldap._tcp.dc._msdcs.$($cs.Domain)") }
    })
}
