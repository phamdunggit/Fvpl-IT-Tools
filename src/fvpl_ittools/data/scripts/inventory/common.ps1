# Phần đầu chung của các script thu thập thông tin máy. core/inventory.py ghép:
#   common.ps1 + (hàm dựng sẵn nếu có dùng) + <phần>.ps1 + dòng xuất JSON của $data.
# Chỉ đọc, không đổi gì. Dùng Get-CimInstance thẳng thay cho cmdlet như Get-PhysicalDisk, Get-NetAdapter,
# Get-MpComputerStatus: các cmdlet đó phải nạp module trước, có máy mất 10–30 giây mỗi module.
#
# PowerShell 5.1: giá trị "không có output" đặt thẳng vào hashtable sẽ thành {} trong JSON. Vì vậy hàm
# luôn trả $null tường minh, và kết quả của Safe được gán vào biến trước khi đưa vào hashtable.

function Safe([scriptblock]$Block) { try { & $Block } catch { } }
function Iso($Value) { if ($Value) { ([datetime]$Value).ToString('s') } else { $null } }

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
$data = [ordered]@{}
