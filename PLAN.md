# FVPL IT Toolkit: kế hoạch

> Tên tạm. Lập ngày 08/10/2026. **Trạng thái: đã duyệt 08/10/2026. GĐ0 xong; GĐ1 xong phần code (13/10/2026), còn chạy thử bằng quyền admin. Nhánh `featured`.**
> Câu trả lời cho các điểm chưa rõ nằm ở [mục 11](#11-câu-hỏi-đã-trả-lời-13102026).

---

## 1. Mục tiêu và nguyên tắc

Làm một app Python có giao diện. IT mang theo bằng USB hoặc chạy từ thư mục share, chạy với quyền admin trên từng máy để:

1. **Cài máy mới** nhanh và đồng bộ: đổi tên máy, join domain, cài phần mềm theo phòng ban, áp cấu hình chuẩn, rồi xuất báo cáo.
2. **Sửa các lỗi hay gặp** (mạng, máy in, domain, Windows Update, Office...) bằng một cú bấm, có giải thích lệnh nào sẽ chạy.
3. **Tối ưu và dọn dẹp** máy, hoàn tác được.
4. **Xem nhanh thông tin máy** và xuất ra để kiểm kê tài sản.

Nguyên tắc chung cho mọi tính năng:

- **Mọi thao tác đều ghi log.** Trước khi đổi hệ thống thì tạo restore point và sao lưu giá trị registry cũ. Mục nào hoàn tác được thì có nút Hoàn tác.
- **Mỗi mục có mức rủi ro:** `An toàn` / `Cẩn thận` / `Nâng cao`. Mỗi mục cũng có nút ⓘ giải thích nó đổi gì, chạy lệnh gì, có cần khởi động lại không, và nút copy lệnh (học theo FixWin).
- **Không giẫm chân GPO.** Thiết lập nào GPO đang quản lý thì gắn nhãn "GPO quản lý" và không ghi đè.
- **Không làm những thứ hạ bảo mật hoặc vi phạm bản quyền.** Chi tiết ở [mục 9](#9-không-làm-và-lý-do).

## 2. Những gì đã chốt

| Hạng mục | Lựa chọn |
|---|---|
| Người dùng | Chỉ IT, chạy trực tiếp trên từng máy |
| Phân phối | Thư mục app portable (exe) chạy từ USB hoặc share, tự xin quyền admin |
| Windows | Win10 22H2 + Win11 (23H2, 24H2, 25H2) |
| Domain | AD on-prem, không dùng Entra ID. Tên domain, server, OU nằm trong file cấu hình riêng `site.yaml` (xem 6.9) |
| Repo | GitHub **public** `phamdunggit/Fvpl-IT-Tools`, nên không commit thông tin nội bộ |
| Nguồn phần mềm | winget cho phần mềm phổ thông, thư mục share nội bộ cho phần mềm riêng của công ty |
| Ngôn ngữ / giao diện | Python 3.13 + PySide6 (Qt 6), giao diện tiếng Việt |

## 3. Tham khảo các tool hiện có

| Tool | Là gì | Đáng học | Lấy vào tool mình |
|---|---|---|---|
| **Chris Titus WinUtil** | Tool PowerShell có GUI, gồm các tab Install / Tweaks / Config / Updates | Cài app qua winget; nút "Get Installed" đánh dấu app đã có; tweak chia Essential và Advanced; tạo restore point trước khi tweak; hoàn tác từng tweak; nhóm Fixes (System Corruption Scan, Network Reset, Windows Update Reset, WinGet Reinstall, NTP); mở nhanh các panel đời cũ | Gần như toàn bộ cấu trúc tab. Tweak định nghĩa bằng file dữ liệu thay vì viết cứng trong code. Cơ chế restore point + hoàn tác |
| **Win11Debloat** (Raphire) | Script PowerShell gỡ app rác, tắt quảng cáo, bảo vệ quyền riêng tư | Áp dụng cho cả user khác và Default User; chế độ chạy thử (dry-run); cảnh báo khi GPO ghi đè; tắt scheduled task telemetry; chặn app "đồng hành" của driver tự cài | Nhóm debloat và quyền riêng tư; chạy thử; cảnh báo GPO; áp dụng cho Default User |
| **Optimizer** (hellzerg) | App tối ưu và quyền riêng tư, nay đã chuyển sang OptimizerNXT | Quản lý startup, sửa HOSTS, sửa PATH, tìm file bị khoá, xem phần cứng, ping, xoá cache DNS, chạy im lặng theo file template | Nhóm Tiện ích; lưu lựa chọn thành "mẫu" để tự động hoá |
| **FixWin 11** | App sửa lỗi, chia 6 nhóm | Mỗi fix có nút giải thích đổi gì và khoá registry nào; nhấp đúp để copy lệnh; khuyên chạy SFC trước và sửa từng lỗi một | Nút ⓘ và copy lệnh cho mọi mục; chia lỗi theo chủ đề |
| **Tweaking.com Windows Repair** | Bộ sửa lỗi all-in-one | Sửa quyền registry và file; đăng ký lại DLL; sửa WMI, MSI, Winsock/DNS/proxy/hosts, Firewall, Windows Update; trả service về mặc định; khôi phục cổng máy in | Các fix hệ thống nâng cao (WMI, MSI, máy in); chạy theo "gói" |
| **Microsoft PC Manager** | App dọn dẹp của Microsoft | Quét trước rồi hiện dung lượng từng loại rác; quản lý startup; tìm file lớn trên ổ C | Trang Dọn dẹp theo luồng *quét → xem dung lượng → chọn → xoá* |
| **O&O ShutUp10++** | Chỉnh quyền riêng tư | Mỗi mục có mức khuyên dùng xanh / vàng / đỏ | 3 mức rủi ro An toàn / Cẩn thận / Nâng cao |
| **Sophia Script** | Module PowerShell có hơn 150 hàm tweak | Mỗi tweak có cặp bật/tắt rõ ràng | Mọi tweak phải đọc được trạng thái hiện tại và có chiều ngược lại |
| **Ninite / Patch My PC** | Cài và cập nhật app hàng loạt | Cài im lặng theo gói; cập nhật app cũ | Gói phần mềm theo phòng ban; nút "Cập nhật tất cả" |
| **PDQ Inventory / BGInfo** | Kiểm kê và hiển thị thông tin máy | Thu thập cấu hình máy về một chỗ | Xuất thông tin máy lên share để kiểm kê |

## 4. Giao diện

```
┌────────────────────────────────────────────────────────────────────────┐
│ FVPL IT Toolkit    FVPL-KT05 · <domain> · Win11 25H2 · Admin ✔         │
├────────────────┬───────────────────────────────────────────────────────┤
│ Tổng quan       │                                                       │
│ Cài máy mới     │   Nội dung trang đang chọn                            │
│ Sửa lỗi         │   (danh sách mục: ☐ tên · nhãn rủi ro · ⟳ restart ·   │
│ Tối ưu & dọn    │    ⓘ giải thích · [Chạy])                             │
│ Phần mềm        │                                                       │
│ Cấu hình        │   [Xem trước]  [Chạy mục đã chọn]  [Hoàn tác]         │
│ Tiện ích        │                                                       │
│ Nhật ký         │                                                       │
├────────────────┴───────────────────────────────────────────────────────┤
│ 10:21:03 ✔ Xoá cache DNS (0,2s) · 10:21:05 ▶ Reset Winsock...   [Huỷ]  │
└────────────────────────────────────────────────────────────────────────┘
```

- **Thanh trên:** tên máy, domain, phiên bản Windows, trạng thái admin, và nhãn cảnh báo khi DNS không trỏ về DC hoặc chưa vào domain.
- **Khung log dưới cùng:** hiện output trực tiếp, có nút Huỷ. Giao diện không bao giờ treo vì mọi lệnh chạy nền.
- **Ô tìm kiếm** trên mỗi trang. Gõ "máy in" là lọc ra mọi mục liên quan.

## 5. Chức năng chi tiết

Ưu tiên: **P1** làm trong bản đầu (GĐ1–2), **P2** làm tiếp (GĐ3), **P3** làm khi rảnh (GĐ4). Xem [Lộ trình](#8-lộ-trình).

### 5.1 Tổng quan máy

| Chức năng | Chi tiết | Ưu tiên |
|---|---|---|
| Hệ điều hành | Tên máy, domain/workgroup, người đang đăng nhập, phiên bản (edition, version, build), ngày cài Windows, uptime | P1 |
| Kích hoạt | Trạng thái kích hoạt Windows và Office (**chỉ xem**) | P1 |
| Phần cứng | Hãng, model, serial (BIOS), CPU, RAM (dung lượng, số khe), ổ đĩa (SSD/HDD, dung lượng, còn trống, sức khoẻ), GPU, màn hình | P1 |
| Mạng | IP, MAC, gateway, DNS (cảnh báo nếu không trỏ về DC), LAN hay Wi-Fi | P1 |
| Bảo mật | Defender (có bật không, ngày cập nhật chữ ký), Firewall, BitLocker, TPM, Secure Boot, lần cập nhật Windows gần nhất | P1 |
| Sức khoẻ | Báo cáo pin laptop (`powercfg /batteryreport`), màn hình xanh gần đây (Event 1001, thư mục Minidump), tắt máy đột ngột (Kernel-Power 41, Event 6008) | P2 |
| Lên Win11 được không | Dành cho máy Win10: kiểm tra TPM 2.0, Secure Boot, CPU, RAM, ổ đĩa | P2 |
| Xuất thông tin | Copy để dán vào ticket hoặc Zalo; xuất HTML. **Lưu kiểm kê ✔**: mỗi máy một file JSON trong `Inventory\` cạnh tool trên USB / SSD (máy đổi tên cùng serial thì thay bản cũ), tự dựng `KiemKe.xlsx` một dòng một máy; không gửi lên share (mục 11, câu 12). Wizard bước 7 cũng lưu | P1 / P2 |

### 5.2 Cài máy mới (wizard)

Wizard đi theo từng bước. Mọi lựa chọn có thể lưu thành **mẫu** (ví dụ "Kế toán – Laptop"), lần sau chỉ cần chọn mẫu (mẫu: chưa làm).

**Đã làm (13/10/2026), chưa chạy thật trên VM:** trang Cài máy mới thành wizard 8 bước, danh sách bước bên trái, tiến độ lưu ở `%ProgramData%\FVPL-ITTools\newpc-wizard.json` (`newpc/state.py`).
- Bước 1: chọn mã phòng (thêm mã mới thì ghi tiếp vào `departments` trong site.yaml, giữ chú thích của IT). **Gợi ý tên** hỏi AD bằng LDAP (máy chưa join thì dùng tài khoản join, chỉ đọc), lấy số lớn nhất + 1, báo nếu tên đã có (KB5020276). Ghi người dùng chính, profile phần mềm.
- Bước 2: chép tool vào `%ProgramData%\FVPL-ITTools\app` (khoá quyền: Users chỉ đọc), `Add-Computer -NewName -OUPath` (đã ở đúng domain thì `Rename-Computer`), hẹn tác vụ mở lại tool (`--resume`, khi một admin đăng nhập, quyền cao nhất). Lỗi join kèm gợi ý theo mã.
- Bước 3: kiểm tra đã vào domain, đúng tên, secure channel; đồng bộ giờ; gpupdate; thêm `it_admins_group` vào Administrators.
- Bước 4: mở trang Phần mềm với profile tick sẵn; tool ghi kết quả khi lượt cài kết thúc. Bước 5: gói Cấu hình chuẩn (đã thêm định dạng vùng vi-VN). Bước 6: Windows Update (bỏ qua được).
- Bước 7: báo cáo HTML (các bước, hệ điều hành, phần cứng + serial, phần mềm như Programs and Features), lưu trên máy và `Reports\` cạnh tool trên ổ mang theo. Kết thúc thì xoá tác vụ mở lại.

| Bước | Nội dung |
|---|---|
| **0. Kiểm tra trước** | Kiểm tra: quyền admin; phiên bản Windows; có mạng; DNS phân giải được `_ldap._tcp.dc._msdcs.<domain>` (tức DNS đang trỏ về DC); giờ lệch so với DC (lệch quá 5 phút thì Kerberos lỗi, tool sẽ đồng bộ giờ); vào được share; winget chạy được (hỏng thì cài lại từ share); ổ C còn đủ dung lượng; laptop đang cắm sạc. |
| **1. Thông tin máy** | Chọn phòng ban, tool gợi ý tên kế tiếp theo quy ước (ví dụ `FVPL-KT05`) và kiểm tra tên đã có trong AD chưa. Chọn OU, chọn profile phần mềm, ghi tên người dùng chính (để đưa vào báo cáo kiểm kê). |
| **2. Đổi tên + join domain** | Nhập tài khoản join qua hộp thoại mật khẩu. Tool chạy `Add-Computer -DomainName <domain> -NewName <tên> -OUPath <OU> -Credential …`, đổi tên và join chỉ tốn một lần khởi động lại. Tiếp theo: thêm nhóm IT vào Administrators cục bộ (theo SID `S-1-5-32-544`), lưu trạng thái, hẹn tự mở lại tool sau khi khởi động, rồi restart. |
| **3. Sau khởi động lại** | IT đăng nhập bằng tài khoản domain có quyền admin, tool tự chạy tiếp: `gpupdate /force`, kiểm tra secure channel với DC. |
| **4. Cài phần mềm** | Cài theo profile: app winget trước, app từ share sau. Hiện tiến độ từng app; lỗi thì ghi lại và chạy tiếp app sau. |
| **5. Cấu hình chuẩn** | Mỗi mục tick được: múi giờ SE Asia (UTC+7) và đồng bộ giờ; định dạng vùng; power plan và **tắt Fast Startup** (máy domain nên tắt để GPO và bản cập nhật áp đúng); hiện đuôi file; This PC trên desktop; .NET 3.5 (nguồn offline trên share); tắt quảng cáo và consumer features; gỡ app rác; bật System Protection cho ổ C rồi tạo restore point "Sau khi cài máy"; sao lưu khoá BitLocker lên AD (nếu công ty dùng). |
| **6. Windows Update** | Tuỳ chọn: quét và cài cập nhật, có thể để chạy nền. |
| **7. Báo cáo** | Liệt kê bước nào ✔ / ✖, phần mềm đã cài kèm phiên bản, phần cứng và serial. Lưu HTML trên máy và trên ổ mang theo (`Reports\` cạnh tool); không gửi lên share (mục 11, câu 12). |

Lưu ý về thứ tự và các trường hợp đặc biệt:

- **Join domain trước, cài phần mềm từ share sau.** Máy chưa vào domain thì phải nhập tài khoản mới mở được share. Nếu cần cài trước khi join, tool hỏi tài khoản và chạy `net use` tạm thời, không lưu lại.
- **Máy cài lại nhưng giữ tên cũ:** computer object đã có sẵn trong AD. Từ bản vá KB5020276 (10/2022), join lại có thể bị chặn nếu tài khoản join không phải người tạo object đó hoặc không phải Domain Admin. Tool nhận ra lỗi này và hướng dẫn cách xử lý: reset hoặc xoá object trong AD, hoặc bật GPO cho phép dùng lại computer account.

### 5.3 Sửa lỗi

Mỗi nhóm có một **gói sửa nhanh** (*Sửa mạng*, *Sửa máy in*, *Sửa Windows Update*, *Sửa domain*). Gói chạy chuỗi bước theo thứ tự và dừng nếu một bước lỗi.

**Mạng và Internet**

| Mục | Cách làm | Rủi ro | Ưu tiên |
|---|---|---|---|
| Chẩn đoán mạng | Ping gateway, DC và Internet; `nslookup` tên domain; `Test-NetConnection` các cổng 53/88/389/445/443. Kết quả hiện xanh/đỏ | An toàn | P1 |
| Xoá cache DNS | `ipconfig /flushdns` | An toàn | P1 |
| Xin lại IP | `ipconfig /release` + `/renew` | An toàn | P1 |
| Reset proxy | `netsh winhttp reset proxy` + xoá proxy của người dùng | An toàn | P1 |
| Reset Winsock + TCP/IP | `netsh winsock reset`, `netsh int ip reset` (cần restart) | Cẩn thận | P1 |
| Reset mạng toàn bộ | Gộp các bước trên + reset card mạng | Cẩn thận | P1 |
| Khôi phục file hosts | Sao lưu file hiện tại rồi trả về mặc định | Cẩn thận | P2 |
| Reset Firewall | `netsh advfirewall reset` (GPO sẽ áp lại luật của domain) | Cẩn thận | P2 |

**Domain và đăng nhập**

| Mục | Cách làm | Rủi ro | Ưu tiên |
|---|---|---|---|
| Kiểm tra kết nối DC | `nltest /dsgetdc:<domain>`, `nltest /sc_verify`, DNS có trỏ về DC không | An toàn | P1 |
| Sửa lỗi "The trust relationship … failed" | `Test-ComputerSecureChannel -Repair -Credential`, không cần join lại | Cẩn thận | P1 |
| Đồng bộ giờ với DC | `w32tm /resync /force` | An toàn | P1 |
| Cập nhật Group Policy | `gpupdate /force` | An toàn | P1 |
| Báo cáo GPO đang áp | `gpresult /h` rồi mở file HTML | An toàn | P1 |
| Xoá vé Kerberos | `klist purge` | An toàn | P2 |
| Xoá thông tin đăng nhập đã lưu | Credential Manager, chọn từng mục để xoá | Cẩn thận | P2 |

**Máy in** (trang riêng "Máy in": danh sách, thêm, sửa lỗi). Dấu ✔: đã làm.

| Mục | Cách làm | Rủi ro | Ưu tiên |
|---|---|---|---|
| Xoá lệnh in bị kẹt ✔ | Dừng Spooler, xoá `spool\PRINTERS\*`, chạy lại Spooler | An toàn | P1 |
| Khởi động lại Print Spooler ✔ | | An toàn | P1 |
| Danh sách máy in ✔ | Máy in trên máy, share của cả máy và của người đang đăng nhập (đọc từ hive của họ khi IT chạy tool bằng tài khoản khác), trạng thái, lệnh chờ; in trang thử, mở hàng đợi | An toàn | P2 |
| Thêm máy in qua IP ✔ | Tạo cổng TCP/IP, driver đã cài / có sẵn trong Windows / từ file .inf (đọc tên model trong file), đặt tên | An toàn | P2 |
| Thêm máy in share ✔ | `Add-Printer -ConnectionName` bằng quyền admin để driver được cài (tránh 0x00000bcb), rồi `printui /ga` cho cả máy | An toàn | P2 |
| Gỡ máy in và driver lỗi ✔ | `Remove-Printer`, cổng TCP/IP không còn dùng, `Remove-PrinterDriver` nếu chọn; share của cả máy bằng `printui /gd`; share của người dùng bằng tác vụ chạy dưới tên họ | Cẩn thận | P2 |
| Share máy in Win11 ↔ Win10 ✔ | Mục kiểm tra (RPC, Spooler, firewall, mạng Public, máy chia sẻ trả lời không); máy chia sẻ nhận cả Named Pipes (`RpcProtocols = 7`) và mở firewall File and Printer Sharing; máy Win11 22H2+ kết nối bằng Named Pipes (`RpcUseNamedPipeProtocol = 1`, lỗi 0x00000709 / 0x0000007c) | Cẩn thận | P1 |
| Lỗi 0x0000011b ✔ | `RpcAuthnLevelPrivacyEnabled = 0` trên máy chia sẻ. **Hạ bảo mật**, chỉ dùng khi đã cập nhật Windows mà vẫn lỗi; nên chuyển sang in qua IP | Nâng cao | P2 |

**Windows Update**

| Mục | Cách làm | Rủi ro | Ưu tiên |
|---|---|---|---|
| Reset Windows Update | Dừng wuauserv/bits/cryptsvc/msiserver, đổi tên `SoftwareDistribution` và `catroot2`, chạy lại các service | Cẩn thận | P1 |
| Lịch sử và mã lỗi cập nhật | Đọc qua Windows Update API (COM) và tra nghĩa mã lỗi | An toàn | P2 |
| Quét và cài cập nhật | Windows Update API (`Microsoft.Update.Session`) | An toàn | P2 |
| Dọn component store | `DISM /Online /Cleanup-Image /StartComponentCleanup` | An toàn | P2 |

**Hệ thống**

| Mục | Cách làm | Rủi ro | Ưu tiên |
|---|---|---|---|
| Quét file hệ thống | `DISM /RestoreHealth` rồi `sfc /scannow` (tuỳ chọn lấy nguồn `install.wim` trên share) | An toàn | P1 |
| Kiểm tra ổ đĩa | `chkdsk C: /scan`; muốn `/f` thì hẹn chạy lúc khởi động | An toàn / Cẩn thận | P1 |
| Khởi động lại Explorer | | An toàn | P1 |
| Xây lại cache icon và thumbnail | Xoá `iconcache*.db`, `thumbcache*.db` rồi khởi động lại Explorer | An toàn | P1 |
| Sửa âm thanh | Khởi động lại Audiosrv và AudioEndpointBuilder | An toàn | P1 |
| Thiết bị lỗi | Liệt kê thiết bị lỗi (`Get-PnpDevice`), quét lại phần cứng (`pnputil /scan-devices`) | An toàn | P2 |
| Sửa WMI | `winmgmt /verifyrepository`, rồi `/salvagerepository` | Cẩn thận | P2 |
| Sửa Windows Installer | `msiexec /unregister` + `/regserver` | Cẩn thận | P2 |
| Reset Microsoft Store | `wsreset.exe` | An toàn | P2 |
| Start / Search / Settings không mở | Đăng ký lại các app hệ thống (Appx) | Nâng cao | P2 |
| Xây lại chỉ mục Windows Search | | Cẩn thận | P3 |
| Đăng nhập vào profile tạm (TEMP) | Sửa `ProfileList` (khoá `.bak`) | Nâng cao | P3 |

**Office và ứng dụng**

| Mục | Cách làm | Rủi ro | Ưu tiên |
|---|---|---|---|
| Sửa Office | Quick Repair / Online Repair qua `OfficeClickToRun.exe scenario=Repair` | An toàn | P1 |
| Cập nhật Office | `OfficeC2RClient.exe /update user` | An toàn | P2 |
| Outlook | Mở chế độ an toàn, `/resetnavpane`, mở ScanPST, xem dung lượng PST/OST | An toàn | P2 |
| Xoá cache Teams (bản mới) | Tắt Teams, xoá `LocalCache` | An toàn | P2 |
| Xoá cache Chrome/Edge | Không đụng mật khẩu và bookmark | An toàn | P2 |

**Bảo mật và truy cập**

| Mục | Cách làm | Rủi ro | Ưu tiên |
|---|---|---|---|
| Bật/tắt Remote Desktop | Registry + nhóm luật firewall, chọn theo ID nhóm vì Windows tiếng Việt dịch tên nhóm khác | Cẩn thận | P2 |
| Sao lưu khoá BitLocker lên AD | `manage-bde -protectors -adbackup` | An toàn | P2 |
| Cập nhật và quét Defender | `Update-MpSignature`, `Start-MpScan -ScanType QuickScan` | An toàn | P2 |

### 5.4 Tối ưu và dọn dẹp

**Dọn rác.** Quét trước, hiện dung lượng từng loại, người dùng tick chọn rồi mới xoá (học PC Manager). Dấu ✔: đã làm ở GĐ3 (trang Tối ưu & dọn dẹp).

| Mục | Rủi ro | Ưu tiên |
|---|---|---|
| Temp của người dùng + Windows Temp ✔ | An toàn | P1 |
| Cache Windows Update (`SoftwareDistribution\Download`) ✔ | An toàn | P1 |
| Cache Delivery Optimization ✔ | An toàn | P1 |
| Crash dump, Windows Error Reporting ✔ | An toàn | P1 |
| Thumbnail cache ✔ (mục "Xây lại cache icon và thumbnail" ở trang Sửa lỗi) | An toàn | P2 |
| Thùng rác (hiện dung lượng, hỏi lại trước khi xoá) ✔ | Cẩn thận | P2 |
| `Windows.old` / bản cài cũ (xoá thì mất đường quay về bản Windows trước) ✔ dọn bằng Disk Cleanup | Cẩn thận | P2 |
| Tìm file và thư mục lớn trên ổ C | An toàn | P2 |

**Khởi động và hiệu năng**

| Mục | Ghi chú | Rủi ro | Ưu tiên |
|---|---|---|---|
| Tắt Fast Startup ✔ | Ở trang Cấu hình, nhóm Cấu hình chuẩn | An toàn | P1 |
| Quản lý startup ✔ | Đọc Run keys (HKLM/HKCU), thư mục Startup (task chạy lúc đăng nhập: chưa làm). Bật/tắt kiểu Task Manager (`StartupApproved`) nên hoàn tác được | An toàn | P2 |
| Power plan ✔ | Balanced / High performance; máy bàn thì tắt USB selective suspend | An toàn | P2 |
| Tắt hibernation trên máy bàn ✔ | Giải phóng `hiberfil.sys` | Cẩn thận | P2 |
| Hiệu ứng hình ảnh tối ưu hiệu năng | Dành cho máy yếu | An toàn | P3 |
| Chuyển một số service sang Manual | Chỉ những service trong danh sách đã chọn lọc | Nâng cao | P3 |

**Gọn gàng và quyền riêng tư (debloat)**

| Mục | Ghi chú | Rủi ro | Ưu tiên |
|---|---|---|---|
| Gỡ app cài sẵn ✔ | Xbox, Clipchamp, Solitaire, News... Gỡ cho mọi user và gỡ cả bản *provisioned* để user mới không bị cài lại. Có danh sách giữ lại: Calculator, Photos, Snipping Tool, Store... | Cẩn thận | P2 |
| Tắt quảng cáo và gợi ý ✔ | Gợi ý trong Start, tips, quảng cáo màn hình khoá, consumer features (tự cài game) | An toàn | P2 |
| Tắt Bing trong Start, Widgets, Copilot ✔ | Tắt bằng policy | An toàn | P2 |
| Telemetry về mức thấp nhất mà bản Pro cho phép ✔ | | An toàn | P2 |
| Chặn app "đồng hành" của driver tự cài | | An toàn | P3 |

> Phần lớn các mục ở trên nên đặt bằng **GPO cho cả domain** nếu được. Tool chỉ là phương án cho từng máy, và sẽ không ghi đè những gì GPO đang quản lý.

### 5.5 Phần mềm

| Chức năng | Chi tiết | Ưu tiên |
|---|---|---|
| Danh mục phần mềm | Đọc từ file trên share, chia nhóm, có ô tìm kiếm và tick chọn. *Đã làm (GĐ2), cách khai báo ở [docs/SOFTWARE.md](docs/SOFTWARE.md)* | P1 |
| Phát hiện đã cài | Khoá registry Uninstall (máy + người đang đăng nhập), so theo mẫu tên hoặc file; hiện phiên bản. Không dùng `winget list` vì chậm và phải đọc bảng chữ. *Đã làm* | P1 |
| Cài theo profile phòng ban | Profile có thể kế thừa nhau, ví dụ Kế toán = Văn phòng + phần mềm thuế. *Đã làm* | P1 |
| Cài từ winget | `winget install --id … --exact --source winget --silent --accept-package-agreements --accept-source-agreements --disable-interactivity`. *Đã làm* | P1 |
| Cài từ share | MSI (`/qn /norestart`), EXE kèm tham số cài im lặng, app portable (copy + tạo shortcut). Xử lý mã thoát 0 / 3010 / 1641 / 1618. *Đã làm* | P1 |
| Hàng đợi cài | Chạy tuần tự, ghi log từng app, có nút thử lại khi lỗi. *Đã làm* | P1 |
| Sửa / cài lại winget | Đăng ký lại App Installer cho tài khoản; không được thì cài App Installer và các gói phụ thuộc từ share (giống "WinGet Reinstall" của WinUtil). *Đã làm: mục `sw.repair_winget` ở trang Sửa lỗi* | P1 |
| Office | Cài bằng Office Deployment Tool với file `config.xml` trên share, dùng license của công ty | P1 |
| Cập nhật app | `winget upgrade`, có danh sách loại trừ | P2 |
| Gỡ cài đặt | | P2 |
| Driver theo hãng ✔ (Dell, Lenovo) | Mục "Cập nhật driver, BIOS của hãng" (`55-drivers.yaml`): tự nhận hãng; Dell Command \| Update (`dcu-cli /applyUpdates`, tự tạm dừng BitLocker) hoặc Lenovo System Update (`tvsu /CM`), chưa có thì cài bằng winget; bước 6 của wizard dùng. HP chưa làm (máy HP ít) | P2 |

Danh sách mặc định gợi ý (**cần bồ chốt**; đã đưa phần có winget vào `data/apps.yaml` đóng gói kèm tool):

- **Văn phòng:** Chrome, 7-Zip, Foxit hoặc Adobe Reader, UniKey/EVKey, Zalo PC, VLC, Notepad++, VC++ Redistributable, .NET Desktop Runtime, font tiếng Việt (VNI, TCVN3) để đọc tài liệu cũ, phần mềm hỗ trợ từ xa theo chính sách công ty (UltraViewer/TeamViewer/AnyDesk).
- **Kế toán:** thêm HTKK, iTaxViewer, driver token chữ ký số, phần mềm hoá đơn điện tử và kế toán đang dùng.
- **IT:** thêm RSAT, PuTTY/WinSCP, Wireshark...

### 5.6 Cấu hình và lối tắt

| Chức năng | Chi tiết | Ưu tiên |
|---|---|---|
| Mở nhanh panel hệ thống | Control Panel, Network Connections, Devices and Printers, Device Manager, Computer Management, Services, Event Viewer, System Properties, Programs and Features, Credential Manager, Firewall, Disk Management, Registry Editor, Task Scheduler, gpedit. *Đã làm ở GĐ1, nằm ở trang Tiện ích, tab "Mở nhanh".* | P1 |
| Windows Features | .NET 3.5 (nguồn offline), RSAT (máy IT), Telnet Client, OpenSSH. SMB1 chỉ bật khi máy scan đời cũ bắt buộc phải có (Nâng cao) | P2 |
| Tuỳ chọn hay dùng | Có công tắc bật/tắt hiện trạng thái hiện tại: hiện đuôi file, hiện file ẩn, menu chuột phải kiểu cũ (Win11), Num Lock khi khởi động, End Task trên taskbar (Win11), Long Paths, căn trái taskbar (Win11) | P2 |
| Vùng / giờ / bàn phím | Múi giờ, định dạng ngày và số, bàn phím | P2 |

### 5.7 Tiện ích

| Chức năng | Chi tiết | Ưu tiên |
|---|---|---|
| Ping / tracert / nslookup / kiểm tra cổng | Nằm chung trang Chẩn đoán mạng | P1 |
| Sao lưu và cài lại driver | `pnputil /export-driver * <thư mục>`. Hữu ích trước khi cài lại Windows | P2 |
| Xem nhanh Event Log | Lỗi Critical và Error trong 24 giờ / 7 ngày gần nhất | P2 |
| Sửa file HOSTS | Có sao lưu trước | P2 |
| Sửa biến PATH | | P3 |
| Tìm process đang khoá file | Dùng Windows Restart Manager API, không cần thêm `handle.exe` | P3 |
| Xem mật khẩu Wi-Fi đã lưu | Chỉ dành cho IT | P3 |
| Chạy chẩn đoán RAM | `mdsched` | P3 |
| Chuyển dữ liệu từ máy cũ sang máy mới | Desktop, Documents, Downloads, bookmark Chrome/Edge, chữ ký Outlook, danh sách máy in, danh sách phần mềm | P3 |

### 5.8 Phần dùng chung (log, sao lưu, hoàn tác)

- **Log:** mỗi phiên ghi một file `%ProgramData%\FVPL-ITTools\logs\yyyy-MM-dd_HHmmss.log` gồm lệnh, output, mã thoát, thời gian. Mật khẩu luôn bị che. Tuỳ chọn copy log lên share.
- **Restore point** trước khi chạy mục Cẩn thận hoặc Nâng cao. System Protection đang tắt thì tool tự bật. Windows chỉ cho tạo 1 restore point mỗi 24 giờ, nên nếu vừa có một điểm gần đây thì tool báo lại cho rõ.
- **Nhật ký hoàn tác:** trước khi ghi khoá registry nào, tool lưu giá trị cũ vào một file JSON. Nút Hoàn tác trả từng mục về giá trị cũ.
- **Xem trước (dry-run):** liệt kê các lệnh sẽ chạy mà không thực thi.
- **Kiểm tra GPO:** thiết lập nằm dưới `…\Policies\…` do GPO đặt thì gắn nhãn "GPO quản lý" và bỏ qua.
- **Khởi động lại:** gom các mục cần restart và hỏi một lần vào cuối phiên.
- **Huỷ và timeout:** tác vụ nào cũng huỷ được, mỗi bước có giới hạn thời gian.

## 6. Kiến trúc kỹ thuật

### 6.1 Công nghệ

| Thành phần | Chọn | Ghi chú |
|---|---|---|
| Ngôn ngữ | Python 3.13 | Máy chạy tool không cần cài Python vì đã đóng gói sẵn |
| Giao diện | PySide6 (Qt 6) | Bản chính thức của Qt, giấy phép LGPL, chạy trên Win10 1809 trở lên |
| Định nghĩa fix/tweak và danh mục phần mềm | YAML (PyYAML) | Dễ đọc, có comment, thêm fix mới không phải sửa code |
| Thông tin hệ thống | `winreg` + `ctypes` cho phần đọc nhanh; PowerShell `Get-CimInstance` xuất JSON cho trang Tổng quan (GĐ1, không cần psutil) | |
| Windows API | `winreg`, `ctypes` (không cần pywin32). Windows Update API gọi qua COM trong PowerShell | |
| Đóng gói | PyInstaller onedir qua `packaging/build.py` (exe đòi quyền admin) | Nuitka là phương án B nếu diệt virus báo nhầm |
| Kiểm thử | pytest + `--selftest` (chụp ảnh từng trang) + máy ảo Hyper-V | |

### 6.2 Cấu trúc thư mục

Cấu trúc hiện tại (sau GĐ1). Mục ghi *(sẽ có)* là phần các giai đoạn sau thêm vào.

```
IT Tools/
├── PLAN.md, README.md, CHANGELOG.md
├── docs/
│   ├── HANDOFF.md             # trạng thái + cách làm tiếp, đọc đầu tiên
│   ├── ACTIONS.md             # tham chiếu khai báo mục bằng YAML
│   └── SOFTWARE.md            # tham chiếu khai báo danh mục phần mềm (apps.yaml)
├── pyproject.toml
├── site.example.yaml          # mẫu thông tin nội bộ (site.yaml thật không commit)
├── src/fvpl_ittools/
│   ├── __main__.py            # điểm vào: hỏi quyền admin, --selftest, mở cửa sổ
│   ├── app.py                 # AppContext: thông tin máy, người dùng, danh sách mục, nhật ký
│   ├── actions/
│   │   ├── model.py           # Action, các loại bước, mức rủi ro
│   │   └── loader.py          # nạp + kiểm tra YAML, báo lỗi tiếng Việt
│   ├── core/
│   │   ├── shell.py           # gọi cmd/PowerShell, giải mã output, timeout, huỷ
│   │   ├── pslib.py           # hàm PowerShell dựng sẵn cho script chẩn đoán (✔/✖, ping, cổng, DNS, DC, giờ)
│   │   ├── executor.py        # chạy mục theo lượt, gói sửa nhanh, restore point, việc làm sau, hoàn tác
│   │   ├── inventory.py       # thông tin máy cho trang Tổng quan, xuất chữ/HTML
│   │   ├── registry.py        # đọc/ghi view 64-bit, đổi HKCU → HKU\<SID>
│   │   ├── journal.py         # nhật ký hoàn tác (JSON)
│   │   ├── safety.py          # restore point
│   │   ├── session.py         # tài khoản chạy tool và người đang đăng nhập (SID, profile)
│   │   ├── sysinfo.py         # tên máy, domain, bản Windows
│   │   ├── winapi.py          # hàm Windows API qua ctypes
│   │   ├── config.py          # đọc site.yaml, thêm mã phòng ban
│   │   └── paths.py, log.py
│   ├── software/              # danh mục + profile (catalog), phát hiện đã cài (detect), lệnh cài (install), quét (scan)
│   ├── newpc/                 # Cài máy mới: precheck (bước 0), naming (tên máy, hỏi AD), state (tiến độ, chạy tiếp
│   │                          # sau restart), steps (join, sau khởi động lại, kết thúc), report (báo cáo HTML)
│   ├── cleanup/               # dọn rác (junk) và chương trình khởi động (startup)
│   ├── printers/              # danh sách máy in, thêm / gỡ máy in (manage), đọc model trong file .inf (inf)
│   ├── ui/
│   │   ├── main_window.py     # thanh trên cùng + sidebar + vùng trang + khung log
│   │   ├── controller.py      # chạy executor ở thread nền, đẩy log về giao diện
│   │   ├── credential_dialog.py  # hỏi tài khoản domain cho mục needs_credential
│   │   ├── log_panel.py, theme.py, widgets.py, text.py
│   │   └── pages/             # overview, actions_page (Sửa lỗi/Cấu hình), printers, optimize, software, newpc, utilities, history
│   └── data/
│       ├── actions/NN-*.yaml  # các fix/tweak; số đầu tên file quyết định thứ tự nhóm trong cây
│       ├── packs.yaml         # gói sửa nhanh
│       ├── scripts/inventory/ # script PowerShell đọc thông tin máy (4 phần chạy song song)
│       ├── scripts/printers/  # script đọc danh sách máy in và driver (chỉ đọc)
│       └── apps.yaml          # danh mục phần mềm mặc định, bản trên share được ưu tiên
├── tests/                     # pytest
└── packaging/                 # spec PyInstaller + build.py (không dùng build/ vì PyInstaller ghi file tạm vào đó)
```

### 6.3 Định nghĩa fix/tweak bằng YAML

Mỗi mục là một khối dữ liệu, không viết cứng trong code (cùng cách WinUtil dùng file JSON). Thêm fix mới chỉ cần thêm vài dòng.

```yaml
# data/actions/10-network.yaml (ví dụ rút gọn; bản thật xem trong repo)
- id: net.flush_dns
  name: Xoá cache DNS
  category: Mạng & Internet
  risk: safe              # safe | caution | advanced
  scope: machine          # machine | user  (xem 6.6)
  reboot: false
  os: { min_build: 19045 }   # 19045 = Win10 22H2
  description: >
    Xoá bộ nhớ đệm phân giải tên miền. Dùng khi vào web hoặc ổ mạng
    bị trỏ sai địa chỉ sau khi đổi server/IP.
  apply:
    - cmd: ipconfig /flushdns

- id: ui.show_file_ext
  name: Hiện đuôi file
  category: Tuỳ chọn hay dùng
  risk: safe
  scope: user
  check:                  # đọc trạng thái hiện tại để hiện công tắc bật/tắt
    registry: { key: 'HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced', name: HideFileExt, on_value: 0 }
  apply:
    - registry: { key: 'HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced', name: HideFileExt, type: DWORD, value: 0 }
  undo: auto              # trả về giá trị đã sao lưu trước khi đổi
  after: restart_explorer

- id: dom.repair_trust
  name: Sửa lỗi "trust relationship" với domain
  category: Domain & đăng nhập
  risk: caution
  needs_credential: domain   # tool hiện hộp thoại nhập tài khoản
  apply:
    - powershell: Test-ComputerSecureChannel -Repair -Credential $Credential
```

Các loại bước gồm `cmd`, `powershell`, `registry`, `service` (start/stop/restart; đổi kiểu khởi động làm ở GĐ3) và `builtin` (thao tác viết bằng Python, hiện có `restart_explorer`). Tham chiếu đầy đủ các khoá ở [docs/ACTIONS.md](docs/ACTIONS.md).

Khoá trạng thái tên là `on_value` chứ không phải `on`, vì YAML hiểu `on`/`off`/`yes`/`no` là true/false.

### 6.4 Danh mục phần mềm và profile

File để trên share. IT sửa file là xong, không cần build lại tool.

```yaml
# \\<server>\IT$\ITTools\config\apps.yaml
apps:
  - id: chrome
    name: Google Chrome
    group: Trình duyệt
    source: winget
    winget_id: Google.Chrome
  - id: 7zip
    name: 7-Zip
    group: Tiện ích
    source: winget
    winget_id: 7zip.7zip
  - id: unikey
    name: UniKey
    group: Gõ tiếng Việt
    source: share
    type: portable              # copy vào Program Files + shortcut + chạy cùng Windows
    path: '{share}\Installers\UniKey'
  - id: office
    name: Microsoft Office
    group: Văn phòng
    source: share
    installer: '{share}\Installers\Office\setup.exe'
    args: '/configure "{share}\Installers\Office\config-van-phong.xml"'
    detect: { uninstall_name: 'Microsoft 365*|Microsoft Office*' }

profiles:
  van-phong:
    apps: [chrome, 7zip, unikey, office]
  ke-toan:
    extends: van-phong
    apps: [htkk, itaxviewer, token-ca, font-vn]
```

### 6.5 Chạy lệnh hệ thống

- Mọi lệnh chạy trong một thread nền (mỗi lần chỉ một lượt). Output được đẩy từng dòng về khung log qua Qt signal. Dòng tiến độ kết thúc bằng `\r` (kiểu thanh % của DISM) ghi đè lên dòng trước.
- **PowerShell:** dùng Windows PowerShell 5.1 có sẵn trên mọi máy, không cần PS7. Script được mã hoá base64 rồi truyền qua `-Command` kèm một đoạn mồi tự giải mã. Lý do: nếu GPO đã đặt Execution Policy thì tham số `-ExecutionPolicy Bypass` không có tác dụng với `-File`, còn lệnh truyền thẳng thì không bị policy chặn. Không dùng `-EncodedCommand` vì với cờ đó cảnh báo, `Write-Host`, verbose bị ghi ra dạng CLIXML. Stdin để dành cho tài khoản (xem 6.7). Script dài tối đa khoảng 11.000 ký tự vì giới hạn độ dài dòng lệnh; quá thì tool tự bỏ chú thích và thụt lề.
- **Không dùng cmdlet phải nạp module chậm** (`Get-NetAdapter`, `Get-NetIPConfiguration`, `Get-PhysicalDisk`, `Get-MpComputerStatus`, `Resolve-DnsName`...): có máy mất 10–30 giây mỗi module. Dùng `Get-CimInstance` thẳng và hàm .NET; các hàm dùng chung nằm trong `core/pslib.py`.
- **cmd:** chạy `cmd.exe /d /s /c` và đặt `chcp 65001` trước. Lệnh có sẵn của cmd (như `echo`) vẫn ghi theo code page OEM, chữ nào không có trong code page đó sẽ thành `?`. Vì vậy muốn in chữ có dấu thì dùng PowerShell.
- Dữ liệu trả về dạng JSON (`ConvertTo-Json`), không đọc kết quả bằng cách dò chữ, vì Windows tiếng Việt và tiếng Anh in thông báo khác nhau.
- **Encoding:** ép đầu ra UTF-8. Riêng `sfc` xuất UTF-16 nên có bộ giải mã riêng.
- **Không dùng tên hiển thị dễ bị dịch** (nhóm Administrators, nhóm firewall "Remote Desktop"). Dùng SID hoặc ID nhóm.
- Mã thoát quy về 3 loại: thành công / thành công nhưng cần restart / lỗi.

### 6.6 Áp cho máy hay cho người dùng

Tool chạy với quyền admin. Nếu IT mở tool bằng tài khoản admin khác (Run as different user) thì `HKCU` và `%AppData%` là của tài khoản IT. Khi đó các thiết lập theo người dùng (taskbar, đuôi file, máy in share, cache Teams/Office...) sẽ bị áp nhầm vào tài khoản IT. Cách xử lý:

- Mỗi mục khai báo `scope: machine | user`.
- Mục `user` ghi vào `HKEY_USERS\<SID>` và profile của **người đang đăng nhập thật**. Tool xác định người này qua phiên Windows đang chứa tool (`WTSQuerySessionInformation`): "Run as different user" vẫn nằm trong phiên của người dùng. Không tra được SID (ví dụ mất kết nối DC) thì dò `ProfileList`. *(Đã làm ở GĐ0.)*
- Tuỳ chọn **"Áp cho Default User"** *(GĐ2)*: nạp `C:\Users\Default\NTUSER.DAT` để tài khoản đăng nhập lần đầu sau này nhận luôn thiết lập. Dùng khi cài máy mới, trước khi người dùng đăng nhập.
- Việc bắt buộc phải chạy trong phiên của người dùng (ví dụ thêm máy in share) thì tool tạo một tác vụ chạy một lần khi họ đăng nhập.

### 6.7 Mật khẩu và tài khoản

- Tài khoản join domain được nhập qua hộp thoại khi cần và chỉ giữ trong RAM. Mật khẩu được đưa vào PowerShell qua stdin, không qua tham số dòng lệnh, để không lộ trong danh sách process hay trong log. Dùng xong thì xoá.
- **Không lưu mật khẩu** vào file, config, log hay trạng thái resume. Không làm tính năng AutoLogon.
- Khuyến nghị: tạo một **tài khoản AD riêng chỉ có quyền join máy vào OU máy trạm** (uỷ quyền), không dùng Domain Admin.
- Mật khẩu admin cục bộ nên quản lý bằng **Windows LAPS** (có sẵn trong Windows từ bản cập nhật 04/2023) qua GPO. Tool chỉ kiểm tra LAPS đã được áp chưa.

### 6.8 Đóng gói và phát hành

- PyInstaller kiểu `onedir`: khởi động nhanh hơn và ít bị diệt virus báo nhầm hơn `onefile`. Nhúng manifest đòi quyền admin, thông tin phiên bản và icon.
- Bản GĐ0 nặng khoảng 65MB sau khi bỏ các phần Qt không dùng (bàn phím ảo, Quick/Qml, PDF, OpenGL phần mềm). Chưa bỏ thì là 108MB.
- Phát hành thư mục `FVPL-ITTools-vX.Y.Z` lên share, kèm bản nén zip để chép vào USB. File `version.json` trên share để tool báo khi có bản mới.
- **Ký số file exe** (nếu công ty có AD CS hoặc mua chứng chỉ code signing) để SmartScreen và Defender không chặn. Chưa ký được thì gửi file cho Microsoft xét báo nhầm.
- Config lấy từ share trước (bản mới nhất). Không vào được share thì dùng bản đóng gói kèm theo.

### 6.9 Thông tin nội bộ không nằm trong repo

Repo để public nên **tên domain, tên server, đường dẫn share, OU, tiền tố tên máy** không được ghi trong code hay trong repo:

- Tất cả nằm trong file `site.yaml`, đặt trên share hoặc cạnh file exe. File này có trong `.gitignore`.
- Repo chỉ có `site.example.yaml` chứa giá trị mẫu (ví dụ `corp.example`) để biết cần điền những gì.
- Trong plan này các giá trị nội bộ được viết là `<domain>`, `<server>`.
- Không vào được share và không có `site.yaml` thì tool vẫn chạy được phần Sửa lỗi / Tổng quan. Các phần cần domain sẽ hỏi IT nhập tay.

## 7. Kiểm thử

- **Tự động (pytest, hiện có 130 test):** test chỉ chạy lệnh vô hại (kể cả đọc thông tin máy thật, không đổi gì). Mọi script PowerShell được soát cú pháp bằng parser của PowerShell mà không chạy. Registry chỉ ghi vào khoá tạm `HKCU\Software\FVPL-ITTools-Test` rồi xoá. Explorer được giả lập trong test.
  - Mọi file YAML đúng schema và không trùng `id`.
  - Mọi mục Cẩn thận hoặc Nâng cao đều có `undo`, hoặc ghi rõ "không hoàn tác được".
  - Giải mã đúng output của `sfc` (UTF-16) và `winget`.
  - Dựng lệnh đúng và giải đúng profile kế thừa.
- **`--selftest <thư mục>`:** dựng cửa sổ, chụp ảnh từng trang, ghi `selftest.json`. `build.py --test` chạy selftest trên chính file exe vừa build để chắc đã đóng gói đủ dữ liệu.
- **Máy ảo Hyper-V** (Win11 Pro có sẵn Hyper-V): snapshot Win10 22H2 sạch, Win11 24H2 và 25H2 sạch. Mỗi mục được chạy thử trên VM rồi revert về snapshot.
- **Join domain thử:** dùng OU riêng (ví dụ `OU=Test`) và tên máy `FVPL-TEST..`. Test xong thì xoá computer object.
- **Mỗi bản phát hành:** chạy checklist tay gồm mở exe trên VM sạch chưa cài Python, chạy trọn wizard, chạy 4 gói sửa nhanh, thử hoàn tác.

## 8. Lộ trình

| Giai đoạn | Nội dung | Xong khi |
|---|---|---|
| **0. Nền móng** ✔ 08/10/2026 | Khung PySide6 (sidebar, khung log, thanh trạng thái); kiểm tra quyền admin; runner chạy nền có nút huỷ; nạp và kiểm tra YAML; log ra file; restore point và nhật ký hoàn tác; build exe | Exe chạy được trên VM Win10 và Win11 sạch (không có Python), chạy được 3 mục mẫu, có log, hoàn tác được 1 tweak registry |
| **1. Tổng quan + Sửa lỗi** ◐ code xong 13/10/2026 | Trang Tổng quan (copy và xuất thông tin); toàn bộ fix P1 (mạng, domain, máy in, Windows Update, hệ thống, Office); gói sửa nhanh (làm 5 gói: thêm "Reset mạng toàn bộ"); mở nhanh panel; công cụ mạng | IT dùng hằng ngày thay cho gõ lệnh tay; mục nào cũng có ⓘ và copy lệnh |
| **2. Cài máy mới** ◐ code xong 13/10/2026 (còn mẫu wizard) | Wizard 7 bước; đổi tên + join + chạy tiếp sau restart; danh mục phần mềm (winget + share) và profile; sửa winget; Office từ ISO; cấu hình chuẩn; báo cáo | Từ một VM Windows sạch: vào được domain, cài đủ phần mềm theo profile, có báo cáo trên máy và trên ổ mang theo. IT chỉ phải chọn phòng ban và nhập mật khẩu join |
| **3. Tối ưu & dọn dẹp** ◑ đã có dọn rác, startup, debloat, power | Dọn rác có quét trước; quản lý startup; debloat và quyền riêng tư; power; các fix P2 | Thấy được dung lượng trước khi xoá; mọi tweak hoàn tác được |
| **4. Tiện ích & hoàn thiện** | Các tiện ích; kiểm kê ra ổ mang theo (đã làm); báo bản mới; ký số; hướng dẫn sử dụng; các mục P3 | Bản 1.0 có trên share |
| **Để sau** | Điều khiển nhiều máy từ xa, bản rút gọn cho nhân viên tự sửa lỗi, giao diện tối | |

GĐ0 và GĐ1 đã chạy được trên máy dev (Win11 25H2, không có quyền admin): các mục chỉ đọc (Chẩn đoán mạng, Liệt kê máy in, trang Tổng quan) đã chạy thật. Các mục đổi hệ thống của GĐ1 mới được soát cú pháp và test giả lập, **chưa chạy thật bằng quyền admin**. Việc đó cùng với chạy trên máy ảo Win10/Win11 sạch là việc đầu tiên trước khi coi GĐ1 xong, danh sách cụ thể ở [docs/HANDOFF.md](docs/HANDOFF.md).

Làm Sửa lỗi (GĐ1) trước Cài máy mới (GĐ2) vì hai lý do. Thứ nhất, fix ít rủi ro nên dùng để kiểm chứng bộ máy chạy action. Thứ hai, IT dùng được ngay hằng ngày. Wizard cần môi trường test domain nên làm sau. Nếu cần cài máy mới gấp thì đổi thứ tự được.

## 9. Không làm và lý do

| Không làm | Lý do |
|---|---|
| Kích hoạt Windows/Office lậu (MAS, KMS crack...) | Vi phạm bản quyền. Tool chỉ hiện trạng thái kích hoạt, còn Office cài bằng ODT với license của công ty |
| Tắt Defender, tắt UAC, tắt hẳn Windows Update, gỡ Edge, tắt Firewall | Hạ bảo mật máy công ty. WinUtil và Optimizer có những mục này nhưng không phù hợp ở đây. Cập nhật nên quản lý bằng GPO/WSUS |
| Tắt BitLocker (nằm trong "Essential Tweaks" của WinUtil) | Ngược với yêu cầu bảo vệ dữ liệu |
| Đổi DNS sang DNS công cộng (DNS changer của Optimizer) | Máy domain phải dùng DNS của DC. Tool chỉ kiểm tra và cảnh báo khi DNS sai |
| "Registry cleaner", "RAM booster" | Không có tác dụng thật, lại dễ gây lỗi |
| Bỏ qua kiểm tra TPM / Secure Boot, tạo ISO tuỳ biến | Không cần cho máy công ty |
| Lưu mật khẩu, AutoLogon | Lý do bảo mật (xem 6.7) |
| Điều khiển nhiều máy từ xa, Win7/8.1 | Ngoài phạm vi bản đầu |

## 10. Rủi ro và lưu ý kỹ thuật

- **Diệt virus báo nhầm** file exe đóng gói bằng PyInstaller. Giảm rủi ro bằng `onedir`, ký số, và gửi file cho Microsoft xét.
- **GPO ghi đè tweak.** Tool kiểm tra và gắn nhãn GPO. Thiết lập dùng chung cho cả công ty nên làm bằng GPO.
- **Win10 hết hỗ trợ từ 14/10/2025.** Tool vẫn hỗ trợ Win10, kèm mục kiểm tra lên Win11 được không. winget trên Win10 mới cài thường cũ hoặc chưa được đăng ký, nên cần cài lại từ share.
- **.NET 3.5 qua WSUS hay lỗi 0x800f0954.** Dùng nguồn `sxs` offline khớp đúng build Windows.
- **Join domain:** giờ lệch quá 5 phút làm Kerberos lỗi; DNS không trỏ về DC thì báo không tìm thấy domain; join lại tên máy cũ có thể bị chặn (KB5020276). Cả ba đã nằm trong bước kiểm tra trước và hướng dẫn xử lý của wizard.
- **Restore point:** mỗi 24 giờ chỉ tạo được một điểm, và System Protection có thể đang tắt. Tool tự bật lại và báo rõ khi không tạo được.
- **Thông báo lỗi khác nhau theo ngôn ngữ Windows.** Chỉ dựa vào mã thoát và JSON, không dò chữ trong output.
- **Windows để chế độ tối** làm Qt lấy bảng màu tối, ô tick và dòng chọn lệch màu với stylesheet. App luôn ép giao diện sáng.
- **YAML 1.1** hiểu `on`/`off`/`yes`/`no` là true/false, kể cả khi dùng làm tên khoá. Đường dẫn registry có `\` thì để trong ngoặc đơn hoặc không ngoặc, đừng dùng ngoặc kép.

## 11. Câu hỏi đã trả lời (13/10/2026)

| # | Câu hỏi | Trả lời | Ảnh hưởng |
|---|---|---|---|
| 1 | Tên chính thức | Giữ **FVPL IT Toolkit** | |
| 2 | Quy ước tên máy | `FVPL-<mã phòng><2 chữ số>`, ví dụ `FVPL-KT05` | Wizard gợi ý số kế tiếp |
| 2 | Mã phòng ban | Chưa chốt danh sách: wizard cho IT **thêm mã mới khi gặp và lưu lại** | Lưu trong `site.yaml` cạnh tool |
| 3 | OU máy trạm | **Chung một OU** cho mọi máy trạm | Khai báo một OU trong `site.yaml` |
| 3 | Tài khoản join | **Đã có tài khoản riêng chỉ để join** | Hộp thoại tài khoản của GĐ1 dùng lại |
| 4 | Share | Có share riêng cho IT (đường dẫn chỉ ghi trong `site.yaml`) | Bản USB lấy bộ cài từ đây |
| 5 | Office | Bản 2010 / 2013 / 2016 Standard từ ISO, **IT chọn bản theo từng người** (không gắn vào profile); kích hoạt **MAK** | Key điền trong file xml trên share / SSD |
| 5 | Diệt virus | **Symantec Endpoint Protection, managed qua SEPM** | Cần `SyLink.xml` xuất từ SEPM |
| 5 | Phần mềm khác | Gõ tiếng Việt **UniKey**; hỗ trợ từ xa chỉ **UltraViewer**; chữ ký số **Viettel-CA, VNPT-CA, FPT-CA**; phần mềm kế toán: chưa cần | Bộ cài UniKey, driver token đặt vào kho bộ cài |
| 6 | WSUS | Không, cập nhật **thẳng từ Microsoft** | .NET 3.5, DISM tải trực tiếp được |
| 6–7 | GPO, BitLocker, LAPS | **Chưa dùng**; muốn tìm hiểu | Viết hướng dẫn triển khai (GĐ4) |
| 8 | Máy in | **Lẫn nhiều kiểu**: IP, print server, share từ PC | Ưu tiên sửa lỗi share máy in Win11 → Win10 |
| 9 | Hãng máy | Chủ yếu **Dell và Lenovo**, đôi khi hãng khác | Dell Command \| Update, Lenovo System Update |
| 10 | Định dạng vùng | **vi-VN** | Thêm vào Cấu hình chuẩn |
| 11 | Lỗi hay gặp | **Share máy in từ Win11 sang Win10**, máy in, mạng / ổ mạng / domain, Office / Outlook, máy chậm / đầy ổ | Thứ tự làm tiếp |
| 12 | Kiểm kê | **Chỉ lưu trên máy / ổ mang theo**, không gửi lên share | Đổi việc "gửi kiểm kê lên share" của GĐ4 |

## 12. Nguồn tham khảo

- [Chris Titus Tech – WinUtil User Guide](https://winutil.christitus.com/guides/) · [winutil in 2026](https://christitus.com/winutil-in-2026/) · [GitHub releases](https://github.com/ChrisTitusTech/winutil/releases)
- [Raphire/Win11Debloat](https://github.com/raphire/win11debloat) · [Release 2026.07.11](https://newreleases.io/project/github/Raphire/Win11Debloat/release/2026.07.11)
- [hellzerg/optimizer README](https://github.com/hellzerg/optimizer/blob/master/README.md)
- [FixWin 11 – The Windows Club](https://thewindowsclub.com/fixwin-windows-pc-repair-software) · [MajorGeeks](https://www.majorgeeks.com/files/details/fixwin_11.html)
- [Tweaking.com – Windows Repair](https://www.tweaking.com/content/page/windows_repair_all_in_one.html)
- [Microsoft PC Manager (tổng hợp)](https://jacar.es/en/efficient-pc-management-with-microsoft-pc-manager/)
