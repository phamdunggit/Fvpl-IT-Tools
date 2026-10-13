# Defender, phần mềm diệt virus, firewall, BitLocker, TPM, Secure Boot, lần cập nhật Windows gần nhất.

$defender = Safe {
    $mp = Get-CimInstance -Namespace 'root/Microsoft/Windows/Defender' -ClassName MSFT_MpComputerStatus -ErrorAction Stop
    [ordered]@{
        enabled        = [bool]$mp.AntivirusEnabled
        realtime       = [bool]$mp.RealTimeProtectionEnabled
        mode           = "$($mp.AMRunningMode)"
        signature_date = Iso $mp.AntivirusSignatureLastUpdated
    }
}

# BitLocker và TPM chỉ đọc được khi có quyền admin.
$bitlocker = $null
$tpm = $null
if ($isAdmin) {
    $bitlocker = Safe {
        $volume = Get-CimInstance -Namespace 'root/cimv2/security/microsoftvolumeencryption' -ClassName Win32_EncryptableVolume `
            -Filter "DriveLetter = '$env:SystemDrive'" -ErrorAction Stop
        $conversion = Invoke-CimMethod -InputObject $volume -MethodName GetConversionStatus
        [ordered]@{
            protection = [int]$volume.ProtectionStatus
            conversion = [int]$conversion.ConversionStatus
            percent    = [int]$conversion.EncryptionPercentage
        }
    }
    $tpm = Safe {
        $chip = Get-CimInstance -Namespace 'root/cimv2/security/microsofttpm' -ClassName Win32_Tpm -ErrorAction Stop
        if ($chip) {
            [ordered]@{
                present = $true
                ready   = [bool]($chip.IsEnabled_InitialValue -and $chip.IsActivated_InitialValue)
                version = "$($chip.SpecVersion)".Split(',')[0].Trim()
            }
        }
        else { [ordered]@{ present = $false; ready = $false; version = '' } }
    }
}
if (-not $bitlocker) {
    # Đọc qua Explorer, không cần admin: 1 bật, 2 tắt, 3 đang mã hoá, 4 đang giải mã, 5 tạm dừng, 6 bật và đang khoá.
    $shellValue = Safe { (New-Object -ComObject Shell.Application).NameSpace("$env:SystemDrive\").Self.ExtendedProperty('System.Volume.BitLockerProtection') }
    if ($null -ne $shellValue) { $bitlocker = [ordered]@{ shell_value = [int]$shellValue } }
}

# Firewall đang có hiệu lực (kể cả do GPO đặt). 1 Domain, 2 Private, 4 Public.
$policy = Safe { New-Object -ComObject HNetCfg.FwPolicy2 }
$firewall = @()
if ($policy) {
    $firewall = @(foreach ($item in @(('Domain', 1), ('Private', 2), ('Public', 4))) {
        [ordered]@{ profile = $item[0]; enabled = [bool]$policy.FirewallEnabled($item[1]) }
    })
}

$secureBoot = Safe {
    [int](Get-ItemProperty -LiteralPath 'HKLM:\SYSTEM\CurrentControlSet\Control\SecureBoot\State' -ErrorAction Stop).UEFISecureBootEnabled
}
$lastUpdate = Safe {
    $searcher = (New-Object -ComObject Microsoft.Update.Session).CreateUpdateSearcher()
    $count = $searcher.GetTotalHistoryCount()
    if ($count -gt 0) {
        $entry = $searcher.QueryHistory(0, [Math]::Min($count, 30)) | Where-Object { $_.ResultCode -eq 2 } | Select-Object -First 1
        if ($entry) { [ordered]@{ date = Iso $entry.Date.ToLocalTime(); title = $entry.Title } }
    }
}

$data.security = [ordered]@{
    is_admin    = [bool]$isAdmin
    defender    = $defender
    antivirus   = @(Safe {
        Get-CimInstance -Namespace 'root/SecurityCenter2' -ClassName AntiVirusProduct -ErrorAction Stop | ForEach-Object {
            [ordered]@{ name = $_.displayName; state = [int64]$_.productState }
        }
    })
    firewall    = $firewall
    bitlocker   = $bitlocker
    tpm         = $tpm
    firmware    = $env:firmware_type
    secure_boot = $secureBoot
    last_update = $lastUpdate
}
