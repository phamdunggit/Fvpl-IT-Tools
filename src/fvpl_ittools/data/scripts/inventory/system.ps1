# Hệ điều hành, kích hoạt, phần cứng, phân vùng.

$os = Get-CimInstance Win32_OperatingSystem
$cs = Get-CimInstance Win32_ComputerSystem
$bios = Safe { Get-CimInstance Win32_BIOS }
$product = Safe { Get-CimInstance Win32_ComputerSystemProduct }
$cv = Get-ItemProperty -LiteralPath 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion'

$data.os = [ordered]@{
    caption         = $os.Caption
    display_version = $cv.DisplayVersion
    build           = $os.BuildNumber
    ubr             = $cv.UBR
    architecture    = $os.OSArchitecture
    install_date    = Iso $os.InstallDate
    last_boot       = Iso $os.LastBootUpTime
    logged_on_user  = $cs.UserName
}

# Kích hoạt: chỉ đọc trạng thái. 55c92734… là Windows, 0ff1ce15… là Office bản dùng key.
$data.licenses = @(Safe {
    Get-CimInstance SoftwareLicensingProduct -Filter ("PartialProductKey IS NOT NULL AND " +
        "(ApplicationID='55c92734-d682-4d71-983e-d6ec3f16059f' OR ApplicationID='0ff1ce15-a989-479d-af46-f275c6370663')") |
        ForEach-Object {
            $kind = 'office'
            if ($_.ApplicationID -like '55c92734*') { $kind = 'windows' }
            [ordered]@{ product = $kind; name = $_.Name; status = [int]$_.LicenseStatus; channel = $_.ProductKeyChannel }
        }
})
$c2r = Safe { Get-ItemProperty -LiteralPath 'HKLM:\SOFTWARE\Microsoft\Office\ClickToRun\Configuration' -ErrorAction Stop }
$data.office = $null
if ($c2r) { $data.office = [ordered]@{ products = $c2r.ProductReleaseIds; version = $c2r.VersionToReport; platform = $c2r.Platform } }

$ramSlots = Safe { [int](Get-CimInstance Win32_PhysicalMemoryArray | Measure-Object MemoryDevices -Sum).Sum }
$hasBattery = [bool](Safe { Get-CimInstance Win32_Battery })
$data.hardware = [ordered]@{
    manufacturer  = $cs.Manufacturer
    model         = $cs.Model
    model_version = $product.Version
    serial        = $bios.SerialNumber
    bios_version  = $bios.SMBIOSBIOSVersion
    bios_date     = Iso $bios.ReleaseDate
    pc_type       = [int]$cs.PCSystemType
    has_battery   = $hasBattery
    cpu           = @(Get-CimInstance Win32_Processor | ForEach-Object {
        [ordered]@{ name = "$($_.Name)".Trim(); cores = $_.NumberOfCores; threads = $_.NumberOfLogicalProcessors }
    })
    ram_total     = [int64]$cs.TotalPhysicalMemory
    ram_slots     = $ramSlots
    ram_modules   = @(Safe {
        Get-CimInstance Win32_PhysicalMemory | ForEach-Object {
            [ordered]@{ slot = $_.DeviceLocator; size = [int64]$_.Capacity; speed = $_.ConfiguredClockSpeed }
        }
    })
    gpu           = @(Safe { Get-CimInstance Win32_VideoController | ForEach-Object { $_.Name } })
    monitors      = @(Safe {
        Get-CimInstance -Namespace 'root/wmi' -ClassName WmiMonitorID -ErrorAction Stop | ForEach-Object {
            $name = -join ($_.UserFriendlyName | Where-Object { $_ } | ForEach-Object { [char]$_ })
            $maker = -join ($_.ManufacturerName | Where-Object { $_ } | ForEach-Object { [char]$_ })
            "$maker $name".Trim()
        }
    })
}

$data.volumes = @(Safe {
    Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3' | ForEach-Object {
        [ordered]@{ drive = $_.DeviceID; label = $_.VolumeName; size = [int64]$_.Size; free = [int64]$_.FreeSpace }
    }
})
$data.system_drive = $env:SystemDrive
