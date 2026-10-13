# Bàn giao: đọc file này trước khi làm tiếp

Cập nhật lần cuối: 13/10/2026, sau khi xong trang Phần mềm (phần đầu của GĐ2).

## Trạng thái

| | |
|---|---|
| Giai đoạn | **GĐ1 (Tổng quan + Sửa lỗi) xong phần code.** Còn chạy thử các mục đổi hệ thống bằng quyền admin (danh sách bên dưới) rồi mới coi là xong. **GĐ2 đang làm:** đã có trang Phần mềm; wizard Cài máy mới chưa làm |
| Nhánh | Code mới làm trên `featured`. Chỉ merge về `main` khi được duyệt |
| Phiên bản | 0.2.0, xem [CHANGELOG.md](../CHANGELOG.md) (trang Phần mềm nằm ở mục "Chưa phát hành") |
| Test | 212 test pytest, tất cả đều qua (khoảng 25 giây) |
| Bản exe | `python packaging\build.py`: thư mục 64MB, zip 27MB. `--test` chạy selftest trên exe, gồm cả đọc thông tin máy |

Đã có:
- Trang **Tổng quan**: hệ điều hành, kích hoạt, phần cứng, mạng (DNS có trỏ về DC không), bảo mật; copy chữ, xuất HTML.
- Trang **Sửa lỗi**: 24 mục (mạng, domain, máy in, Windows Update, hệ thống, Office) và 5 gói sửa nhanh.
- Trang **Cấu hình**: 1 mục mẫu (Hiện đuôi file). Trang **Tiện ích**: mở nhanh 29 công cụ quản trị, công cụ mạng.
- Trang **Phần mềm**: danh mục `apps.yaml` (share hoặc bản đóng gói), profile phòng ban, đánh dấu đã cài, cài lần lượt qua winget / MSI / EXE / portable. Cách khai báo: [SOFTWARE.md](SOFTWARE.md).
- Trang **Cài máy mới**: mới có bước 0 "Kiểm tra trước" (`newpc/precheck.py`); các bước 1–7 của wizard chưa làm.
- Trang **Tối ưu & dọn dẹp** (GĐ3): dọn rác có quét trước (`cleanup/junk.py`), chương trình khởi động cùng Windows (`cleanup/startup.py`), tối ưu / quyền riêng tư / nguồn điện / gỡ app cài sẵn (`75-optimize.yaml`).
- Trang **Nhật ký**: hoàn tác thay đổi registry.

## Bắt đầu

```powershell
py -3.13 -m venv .venv
.venv\Scripts\python -m pip install -e .[dev]
.venv\Scripts\python -m pytest
.venv\Scripts\python -m fvpl_ittools --no-elevate
```

Chi tiết chạy, build, selftest: [README.md](../README.md). Cách khai báo mục, gói, biến và hàm PowerShell dựng sẵn: [ACTIONS.md](ACTIONS.md). Kế hoạch tổng: [PLAN.md](../PLAN.md).

## Quy tắc khi làm repo này

1. **Làm trên nhánh `featured`.** Không commit thẳng lên `main`, không tự merge.
2. **Repo để public.** Tên domain, server, đường dẫn share, OU, tên máy thật **không** được nằm trong code hay docs. Thông tin thật để trong `site.yaml` (gitignore). Trong docs viết `<domain>`, `<server>`. Trước khi commit, tìm tên nội bộ trong các file sắp commit (`git diff --cached | grep -i <tên domain>`...). Ảnh chụp selftest có tên máy, domain, serial thật: không commit.
3. **Máy dev là máy làm việc thật.** Không chạy thử các mục làm đổi hệ thống trên máy này. Mục chỉ đọc (Chẩn đoán mạng, Liệt kê máy in, trang Tổng quan) chạy được. Test registry chỉ dùng khoá tạm `HKCU\Software\FVPL-ITTools-Test`. Explorer được giả lập trong test (fixture `fake_explorer`). Muốn chạy thật thì dùng máy ảo.
4. **Thêm mục mới bằng YAML** ([ACTIONS.md](ACTIONS.md)), chỉ viết Python khi YAML không làm được. Khi viết Python thì thêm vào `BUILTIN_NAMES` (model.py) và `BUILTINS` (executor.py); có test kiểm tra hai danh sách này khớp nhau.
5. **Script PowerShell dùng `Get-CimInstance` và .NET, không dùng cmdlet phải nạp module** (`Get-NetAdapter`, `Get-PhysicalDisk`...). Hàm dùng chung đặt trong `core/pslib.py`.

## Một mục chạy như thế nào

```
ActionsPage (bấm Chạy, hoặc nút gói sửa nhanh)
  → hỏi xác nhận nếu có mục Cẩn thận/Nâng cao; hỏi tài khoản nếu có mục needs_credential
  → RunController.run(actions, credential, stop_on_error)   ui/controller.py, chạy ở thread nền
    → executor.run_batch()                                   core/executor.py
        đăng ký mật khẩu để che trong log (quên ngay khi xong lượt)
        blocked_reason()   sai bản Windows / chưa vào domain / thiếu quyền admin / GPO quản lý → bỏ qua
        restore point      nếu có mục Cẩn thận/Nâng cao và đang có quyền admin
        run_action() từng mục; gói sửa nhanh: một mục lỗi thì bỏ các mục sau
          cmd                → core/shell.py run_cmd
          powershell/service → core/shell.py run_powershell: thêm biến ($TargetUser*, $ReportDir),
                               thêm hàm dựng sẵn nếu script có dùng (core/pslib.py),
                               chạy bằng -Command + đoạn mồi giải mã base64, tài khoản qua stdin
          registry           → core/registry.py, lưu trước/sau vào core/journal.py
          builtin            → executor.BUILTINS
        lỗi thì đổi mã thoát thành lời giải thích (khoá messages)
        việc làm sau (after) chạy một lần cho cả lượt
  ← LogEvent qua Qt signal → khung log (dòng ✔/✖/⚠ tô màu); BatchResult → cột Trạng thái, hỏi restart
```

Trang Tổng quan không đi qua executor: `ui/pages/overview.py` mở 4 thread, mỗi thread chạy một script trong `data/scripts/inventory/` (`core/inventory.py` ghép `common.ps1` + hàm dựng sẵn + phần đó), nhận JSON, dựng các mục rồi vẽ bằng HTML trong `QTextBrowser`.

## Chưa kiểm chứng: chạy trên máy ảo bằng quyền admin

Phiên phát triển không có quyền admin, và máy dev là máy thật nên các mục đổi hệ thống chỉ mới được soát cú pháp và test giả lập. Cần một VM Win11 (và một VM Win10 22H2) **đã join domain test**, có snapshot để quay lại. Mở bản `dist\FVPL-ITTools-v0.2.0.zip`, bấm Yes ở UAC.

Từ GĐ0, vẫn còn:
- [ ] Restore point thật được tạo khi chạy mục Cẩn thận; lần thứ hai trong 24 giờ báo đúng.
- [ ] Máy ảo sạch chưa cài Python mở được exe.
- [ ] Run as different user: thanh trên cùng báo "Chạy bằng … · áp cho …", "Hiện đuôi file" và "Xoá proxy của người dùng" đổi registry của người dùng chứ không phải tài khoản IT.

Các mục của GĐ1, chỗ cần để ý:
- [ ] **Tổng quan khi có quyền admin:** BitLocker đọc qua `Win32_EncryptableVolume` + `GetConversionStatus`, TPM qua `Win32_Tpm` (`IsEnabled_InitialValue`, `IsActivated_InitialValue`). Máy dev không có admin nên chưa thấy hai dòng này chạy thật.
- [ ] **Chẩn đoán mạng / Kiểm tra kết nối với domain** khi đang ở mạng công ty: DNS tìm được DC, cổng 53/88/389/445, độ lệch giờ NTP. Máy dev đang ở Wi-Fi ngoài nên mới thấy nhánh "DNS không trỏ về DC".
- [ ] **Sửa lỗi trust relationship:** làm hỏng trust trên VM (khôi phục snapshot cũ hơn 30 ngày, hoặc reset computer account trên DC), đăng nhập admin cục bộ, chạy mục, nhập tài khoản join.
- [ ] **Đồng bộ giờ:** mã thoát của `w32tm /resync /rediscover` khi DC không trả lời có đúng `0x800705B4` không.
- [ ] **Cập nhật Group Policy:** `echo n| gpupdate /force` không bị treo khi có policy đòi đăng xuất.
- [ ] **Báo cáo GPO:** `gpresult /user <người dùng>` khi chạy bằng tài khoản IT khác; file mở bằng trình duyệt của người dùng (qua `explorer.exe`).
- [ ] **Reset Winsock và TCP/IP:** `netsh int ip reset` hay trả mã 1 kèm vài dòng "Access is denied" dù phần lớn đã reset; đang coi mã 1 là thành công. Kiểm tra có trường hợp mã 1 là lỗi thật không.
- [ ] **Khởi động lại card mạng:** `Win32_NetworkAdapter.Disable/Enable` trả 0, card bật lại được.
- [ ] **Xoá proxy của người dùng:** sau khi xoá `DefaultConnectionSettings`, Settings → Proxy hiện "Automatically detect settings", trình duyệt vào web được.
- [ ] **Xoá lệnh in bị kẹt:** tạo lệnh in kẹt (máy in offline), chạy mục, hàng đợi trống, Spooler chạy lại.
- [ ] **Reset Windows Update:** đổi tên được `SoftwareDistribution` và `catroot2` khi Windows tự bật lại dịch vụ; sau đó quét cập nhật được.
- [ ] **DISM + SFC:** **chưa rõ mã thoát của `sfc /scannow`** khi tìm thấy và sửa được file hỏng (đang coi chỉ 0 là thành công). Nếu sfc trả mã khác 0 khi đã sửa xong thì thêm vào `ok_codes` kèm `messages`. DISM trên máy dùng WSUS hay lỗi `0x800F081F`.
- [ ] **Kiểm tra ổ đĩa / Hẹn sửa ổ đĩa:** mã thoát của `chkdsk /scan`; `fsutil dirty set` làm Windows chạy chkdsk lúc khởi động.
- [ ] **Xây lại cache icon:** Explorer tắt, file cache bị xoá, Explorer tự mở lại. Khi Windows không tự mở lại mà tool có quyền admin, tool tạo tác vụ chạy một lần để mở Explorer bằng tài khoản người dùng (`_START_EXPLORER_AS_USER` trong executor.py), đường này chưa chạy thật lần nào.
- [ ] **Sửa mất âm thanh:** `Restart-Service AudioEndpointBuilder -Force` rồi `Start-Service Audiosrv`.
- [ ] **Sửa Office:** cần máy có Office Click-to-Run. `OfficeClickToRun.exe` giao việc cho dịch vụ rồi thoát ngay; kiểm tra lấy đúng `Platform`, `ClientCulture` từ registry và Office được sửa thật.
- [ ] **5 gói sửa nhanh:** dừng đúng khi một bước lỗi; bước bị khoá thì bỏ qua và chạy tiếp.

Trang Phần mềm (GĐ2). Danh mục và phát hiện đã cài đã chạy thật trên máy dev (chỉ đọc); **chưa cài thật ứng dụng nào**:
- [ ] **winget:** cài 2–3 ứng dụng nhỏ (7-Zip, Notepad++) trên VM; ứng dụng đã có thì báo xong chứ không báo lỗi (`0x8A15002B`, `0x8A150061`). winget lần đầu trên máy mới có thể hỏi điều khoản nguồn dù đã có `--accept-source-agreements`.
- [ ] **MSI từ share:** log MSI xuất hiện trong thư mục logs; mã 3010 làm tool hỏi khởi động lại; thử 1618 bằng cách chạy một bộ cài MSI khác cùng lúc.
- [ ] **EXE từ share:** `ExitCode` đọc được sau `WaitForExit` (đã giữ `$process.Handle` để tránh lỗi PowerShell trả ExitCode rỗng).
- [ ] **Portable (UniKey):** chép vào Program Files, có shortcut Start Menu và Startup chung, đăng nhập tài khoản khác thấy UniKey tự chạy.
- [ ] **Office bằng ODT:** cần file `setup.exe` và `config.xml` thật trên share; xem có bị timeout 3600 giây không.
- [ ] **Run as different user:** ứng dụng `scope: user` (Zalo) bị khoá; phần mềm cài riêng cho người dùng (HKU\<SID>\…\Uninstall) vẫn được nhận là đã cài.
- [ ] **Sửa / cài lại winget:** tài khoản mới đăng nhập lần đầu chưa có winget → mục đăng ký lại được; xoá App Installer của tài khoản (`Get-AppxPackage Microsoft.DesktopAppInstaller | Remove-AppxPackage`) → mục cài lại từ `<share>\Installers\winget\`. Phần kiểm tra `winget --version` đã chạy thật trên máy dev.
- [ ] **Máy chưa vào domain:** trang báo "Không vào được share", danh mục quay về bản đóng gói; không bị treo lâu khi share không trả lời (quét chạy ở thread nền, nhưng `os.path.isdir` trên UNC có thể chờ 20–60 giây).

Trang Cài máy mới, bước Kiểm tra trước. Đã chạy thật trên máy dev (máy đã join, đang ở Wi-Fi ngoài nên DNS không trỏ về DC):
- [ ] VM **chưa join**, có `site.yaml` khai báo `domain`, cắm mạng công ty: DNS tìm được DC, DC trả lời LDAP, đo được giờ lệch.
- [ ] Chỉnh giờ VM lệch 10 phút: dòng giờ báo ✖, nút Đồng bộ giờ chạy rồi tự kiểm tra lại.
- [ ] Laptop rút sạc: dòng Nguồn điện báo ⚠ (đọc bằng `GetSystemPowerStatus`).
- [ ] Máy vừa cài cập nhật chưa khởi động lại: dòng "Chờ khởi động lại" báo ⚠.

Trang Cấu hình (mục mới). Trạng thái bật/tắt đã đọc đúng trên máy dev; **chưa đổi thật mục nào**:
- [ ] Gói "Cấu hình chuẩn máy mới" trên VM mới cài: múi giờ, Fast Startup (Control Panel → Power Options → "Turn on fast startup" bỏ tick), This PC, .NET 3.5, restore point mới trong `rstrui`.
- [ ] .NET 3.5 cả hai đường: có `Sources\sxs\<build>` trên share, và không có (tải từ Windows Update; máy WSUS báo `0x800F0954` kèm hướng dẫn).
- [ ] Restore point tạo được ngay cả khi vừa tạo một điểm trong 24 giờ (mục tạm đặt `SystemRestorePointCreationFrequency = 0` rồi trả lại).
- [ ] Menu chuột phải kiểu cũ: bật rồi Hoàn tác, menu Win11 quay lại (hoàn tác xoá cả khoá CLSID, không chỉ giá trị).
- [ ] End task, căn trái taskbar, hiện file ẩn: có hiệu lực sau khi Explorer khởi động lại; Run as different user thì đổi đúng người dùng.

Trang Tối ưu & dọn dẹp (GĐ3). Quét rác, danh sách khởi động, liệt kê app cài sẵn đã chạy thật trên máy dev (chỉ đọc); **chưa xoá / đổi thật gì**:
- [ ] **Dọn rác** bằng quyền admin trên VM có rác thật: Temp, SoftwareDistribution\Download (dịch vụ Windows Update dừng rồi chạy lại), dump. Dung lượng sau khi dọn khớp với số tool báo.
- [ ] **Windows.old** (VM vừa nâng cấp Windows) và **Delivery Optimization**: `cleanmgr /sagerun:4242` chạy xong, tool xoá lại thiết lập `StateFlags4242`. Xem cleanmgr có hiện cửa sổ chờ người bấm không.
- [ ] **Thùng rác**: chỉ xoá của người đang đăng nhập (`$Recycle.Bin\<SID>` trên mọi ổ cứng), Explorer hiện thùng rác trống.
- [ ] **Khởi động cùng Windows**: tắt một mục rồi đăng xuất / đăng nhập, mục không chạy; Task Manager cũng hiện Disabled; hoàn tác ở trang Nhật ký thì bật lại.
- [ ] **Tối ưu**: gói "Tắt quảng cáo và theo dõi" rồi xem Start, Settings, taskbar; Widgets tắt bằng policy `Dsh\AllowNewsAndInterests`; power plan High performance trên laptop Modern Standby (có thể Windows không cho).
- [ ] **Gỡ app cài sẵn**: chạy "Liệt kê" rồi "Gỡ" trên VM; tài khoản mới tạo sau đó không bị cài lại; các app trong danh sách giữ vẫn còn.

Hai bản USB / SSD:
- [ ] `deploy.py ssd` ra SSD thật, chạy tool từ SSD trên máy chưa vào domain: trang Phần mềm ghi "kho trên ổ mang theo", cài Office từ ISO trên SSD (mount ISO từ ổ USB/SSD).
- [ ] Bản USB: kho là share; máy chưa join thì báo không vào được kho, không treo.

## Việc tiếp theo

1. **Chạy danh sách trên** trên VM, sửa những gì sai. Khi đó GĐ1 mới xong.
2. **GĐ2: phần còn lại** (PLAN mục 5.2, 5.5): wizard Cài máy mới (kiểm tra trước, đổi tên + join domain, chạy tiếp sau restart, cấu hình chuẩn, báo cáo), sửa / cài lại winget từ share. Câu hỏi PLAN mục 11 đã được trả lời (13/10/2026): tên `FVPL-<mã phòng><2 chữ số>`, mã phòng ban thêm dần (wizard cho thêm mã mới và lưu lại), một OU chung cho máy trạm, đã có tài khoản join riêng, Office chọn theo từng người (MAK), Symantec managed qua SEPM, định dạng vùng vi-VN, kiểm kê chỉ lưu trên ổ mang theo. Thứ tự việc tiếp theo ở [TIEN-DO.md](TIEN-DO.md). Hộp thoại tài khoản domain, các hàm kiểm tra DC/DNS/giờ (`core/pslib.py`) và trang Phần mềm (`software/`) dùng lại được cho wizard. Lưu ý khi làm bước restart: tool có thể đang chạy từ USB, sau khi khởi động lại USB có thể đã rút; nên chép tool vào `%ProgramData%\FVPL-ITTools\app` trước khi hẹn tự mở lại.
3. Câu 11 (10 lỗi người dùng hay báo nhất) giúp chọn fix P2 nào làm trước (GĐ3).

## Bẫy đã gặp

GĐ0:
- **YAML hiểu `on` là `true`.** Vì vậy khoá trạng thái tên là `on_value`.
- **Lệnh có sẵn của cmd (`echo`) ghi theo code page OEM 437**, nên `chcp 65001` không giúp được. Chữ có dấu thì in bằng PowerShell.
- **Windows để chế độ tối** làm ô tick vô hình. `theme.apply_theme()` ép bảng màu sáng.
- **Chụp ảnh giao diện không cần màn hình:** nền `offscreen` mặc định vẽ chữ thành ô vuông. Phải dùng `QT_QPA_PLATFORM=offscreen:fontengine=freetype` và `QT_QPA_FONTDIR=C:\Windows\Fonts`; `tests/conftest.py` đã đặt sẵn.
- **Build lỗi khi shell đang `cd` vào `dist\`:** PyInstaller không xoá được thư mục cũ. Ra khỏi `dist\` rồi build lại.
- **Kích thước exe:** plugin bàn phím ảo kéo theo Quick/Qml/Network/OpenGL. Danh sách loại bỏ nằm trong `packaging/fvpl_ittools.spec` (`UNUSED`). Thêm module Qt mới mà exe lỗi thì xem lại danh sách này.

GĐ1:
- **Cmdlet phải nạp module rất chậm trên máy dev** (có phần mềm diệt virus): `Get-NetAdapter` 29 giây, `Get-PhysicalDisk` 16 giây, `Get-MpComputerStatus` 9 giây, `Get-NetIPConfiguration` 17 giây, `Get-NetFirewallProfile` 8 giây; gọi thẳng lớp CIM chỉ 0,1 giây. `Resolve-DnsName -QuickTimeout` vẫn chờ 15 giây mỗi DNS server không trả lời, nên tự hỏi DNS bằng UDP (`Test-DnsSrv`).
- **`-EncodedCommand` làm cảnh báo, `Write-Host`, verbose ra stderr dạng CLIXML.** `-OutputFormat Text` không giúp được; chuyển sang `-Command` với đoạn mồi giải mã base64.
- **`Write-Output` trong hàm PowerShell thành giá trị trả về;** `Write-Host` thì ra CLIXML (xem trên). Hàm vừa in vừa trả giá trị dùng `[Console]::Out.WriteLine` (`Write-Line` trong pslib).
- **PowerShell 5.1: giá trị "không có output" đặt thẳng vào hashtable thành `{}` trong JSON.** Gán vào biến trước, hoặc trả `$null` tường minh; Python đổi `{}` thành `None` cho chắc (`inventory._clean`).
- **`Get-Tpm` không có quyền admin không báo lỗi mà trả "không có TPM".** Chỉ đọc TPM/BitLocker khi có admin.
- **`[ordered]@{ 53 = ... }` rồi `$h[53]`** lấy phần tử thứ 53 chứ không phải khoá 53.
- **QLabel tự xuống dòng trong QScrollArea bị cắt chữ** (Qt tính sai chiều cao). Trang Tổng quan vẽ bằng HTML trong `QTextBrowser`.
- **`regedit.exe` nằm ở `C:\Windows`,** không phải System32.
- **Mã thoát âm** (HRESULT như `0x800705B4`) về Python thành số không dấu; khoá `messages` viết dạng hex là khớp.

GĐ2:
- **Bộ cài là chương trình giao diện:** gọi thẳng `& setup.exe` trong PowerShell thì không chờ. `Start-Process -Wait` lại chờ cả tiến trình con (nhiều bộ cài mở luôn ứng dụng sau khi cài), nên dùng `Start-Process -PassThru` rồi `WaitForExit()`; phải đọc `$process.Handle` ngay sau khi chạy, không thì `ExitCode` có lúc rỗng.
- **Programs and Features có thể có hai dòng trùng tên** (.NET Desktop Runtime: một dòng mang số phiên bản nội bộ MSI). Phát hiện đã cài ưu tiên dòng có phiên bản khớp với số trong tên.
