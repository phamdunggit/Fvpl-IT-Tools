# Ổ đĩa vật lý: loại (SSD/HDD), chuẩn giao tiếp, dung lượng, sức khoẻ. Python đổi mã số ra chữ.

$data.disks = @(Safe {
    Get-CimInstance -Namespace 'root/Microsoft/Windows/Storage' -ClassName MSFT_PhysicalDisk -ErrorAction Stop |
        Sort-Object { [int]$_.DeviceId } | ForEach-Object {
            [ordered]@{
                name   = "$($_.FriendlyName)".Trim()
                media  = [int]$_.MediaType
                bus    = [int]$_.BusType
                size   = [int64]$_.Size
                health = [int]$_.HealthStatus
            }
        }
})
