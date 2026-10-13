# Hướng dẫn sử dụng FVPL IT Toolkit

Viết cho IT dùng tool hằng ngày. Cách sửa / thêm chức năng cho tool xem [README](../README.md) và [ACTIONS.md](ACTIONS.md).
Tên domain, share trong tài liệu là ví dụ; thông tin thật nằm trong `site.yaml` cạnh tool.

Mục lục: [1. Chuẩn bị](#1-chuẩn-bị-làm-một-lần) · [2. Mở tool](#2-mở-tool) · [3. Cài máy mới](#3-cài-máy-mới-wizard) ·
[4. Cài Office](#4-cài-office-2010--2013--2016-bản-volume) · [5. Cài Symantec](#5-cài-symantec-endpoint-protection) ·
[6. Phần mềm khác](#6-phần-mềm-khác) · [7. Các trang còn lại](#7-các-trang-còn-lại) · [8. Khi có lỗi](#8-khi-có-lỗi)

---

## 1. Chuẩn bị (làm một lần)

### 1.1 Hai bản mang theo

| Bản | Dùng khi | Trên ổ có |
|---|---|---|
| **USB** | Sửa lỗi hằng ngày, cài phần mềm qua mạng | `FVPL-ITTools\` (tool) + `site.yaml` |
| **SSD** | Cài máy mới, không cần mạng / share | Như USB + `FVPL-ITTools\SOFT\` (ISO Office, Symantec, UniKey…) |

Chép ra ổ sau khi build (trên máy có mã nguồn):

```powershell
.venv\Scripts\python packaging\build.py
.venv\Scripts\python packaging\deploy.py usb E:\
.venv\Scripts\python packaging\deploy.py ssd F:\
```

Tool tự chọn **kho bộ cài**: có thư mục `SOFT` cạnh file exe thì dùng nó, không thì dùng share `share_root` trong
`site.yaml`. Trang Phần mềm luôn ghi đang dùng kho nào.

### 1.2 `site.yaml`

Chép từ `site.example.yaml`, đặt cạnh file exe. Các khoá: `domain`, `netbios_domain`, `share_root`, `computer_prefix`,
`computer_ou` (OU chung của máy trạm), `it_admins_group` (nhóm IT thêm vào Administrators), `departments` (mã phòng,
tool tự thêm khi bồ bấm "Thêm mã phòng" trong wizard).

### 1.3 Kho bộ cài (`SOFT` trên SSD hoặc thư mục share)

```
SOFT\
├── config\apps.yaml                     danh mục phần mềm công ty, profile phòng ban
├── config\office\office2016-standard.xml   cấu hình cài im lặng Office (điền key MAK ở đây)
├── config\office\office2013-standard.xml
├── config\office\office2010-standard.xml
├── SW_DVD5_Office_2016_64Bit_English_MLF_X20-42479.ISO
├── SW_DVD5_Office_2013w_SP1_64Bit_English_MLF_X19-34904.ISO
├── Microsoft Office 2010 Standard Edition X86 SP1.iso
├── Symantec\SEP-14.3-RU9-Win64\          gói client đã giải nén (Sep64.msi) + SyLink.xml của SEPM
├── UniKey\                               thư mục UniKey (có UniKeyNT.exe)
└── Drivers\Printers\<hãng>\              driver máy in đã giải nén (có file .inf)
```

**Điền key MAK cho Office:** mở từng file `config\office\officeXXXX-standard.xml`, bỏ dấu chú thích dòng `PIDKEY` và
điền key:

```xml
<PIDKEY Value="XXXXX-XXXXX-XXXXX-XXXXX-XXXXX" />
<Setting Id="AUTO_ACTIVATE" Value="1" />
```

`AUTO_ACTIVATE` có sẵn: cài xong Office tự kích hoạt nếu máy có Internet. File có key **không** được đưa lên git hay
gửi ra ngoài.

**SyLink.xml cho Symantec:** gói "All Clients" tải từ Broadcom là bản *unmanaged* (không báo về SEPM). Muốn client tự
vào SEPM của công ty: trong SEPM console → **Clients** → chuột phải nhóm máy trạm → **Export Communication Settings**
→ chọn chế độ *Computer* → lưu `SyLink.xml`, rồi chép đè vào `SOFT\Symantec\SEP-14.3-RU9-Win64\` (cùng thư mục với
`Sep64.msi`). Bộ cài MSI tự đọc file này.

---

## 2. Mở tool

Chạy `FVPL-ITTools.exe`, bấm **Yes** ở UAC. Thanh trên cùng cho biết tên máy, domain, bản Windows, có quyền admin không,
và cảnh báo nếu tool chạy bằng tài khoản khác người đang đăng nhập (thiết lập theo người dùng vẫn áp đúng người đang
đăng nhập). Khung **Nhật ký chạy** dưới cùng hiện từng lệnh và kết quả; nút **Mở thư mục log** để gửi log khi cần.

---

## 3. Cài máy mới (wizard)

Trang **Cài máy mới**, làm lần lượt từ trên xuống. Danh sách bước bên trái có dấu ✔ / ✖; tool nhớ tiến độ.

| Bước | Làm gì |
|---|---|
| 0. Kiểm tra trước | Xem dòng ✖: DNS chưa trỏ về DC, giờ lệch (bấm **Đồng bộ giờ**), thiếu mạng… |
| 1. Thông tin máy | Chọn **Mẫu** nếu có (ví dụ "Kế toán – Laptop"), hoặc chọn phòng ban, bấm **Gợi ý tên** (hỏi AD lấy số kế tiếp), ghi người dùng, chọn profile và **phần mềm thêm** (bản Office). **Lưu thành mẫu…** để lần sau chọn lại |
| 2. Đổi tên + join | Nhập tài khoản join. Tool chép mình vào máy, đổi tên và join OU trong một lần khởi động lại, hẹn tự mở lại |
| 3. Sau khởi động lại | Đăng nhập bằng tài khoản domain có quyền admin: tool tự mở, bấm **Chạy các bước sau khởi động lại** |
| 4. Cài phần mềm | Sang trang Phần mềm, các ứng dụng đã tick sẵn theo profile + phần mềm thêm, bấm **Cài mục đã chọn** (xem mục 4–6) |
| 5. Cấu hình chuẩn | Múi giờ, định dạng vi-VN, tắt Fast Startup, .NET 3.5, restore point… |
| 6. Driver + Windows Update | Dell Command \| Update / Lenovo System Update rồi Windows Update |
| 7. Báo cáo | HTML trên máy và trong `Reports\` cạnh tool; đồng thời lưu kiểm kê. Bấm **Kết thúc wizard** khi xong |

---

## 4. Cài Office 2010 / 2013 / 2016 (bản volume)

Office **không** nằm trong profile vì mỗi người dùng một bản: chọn ở **phần mềm thêm** của wizard (hoặc tick tay ở trang
Phần mềm). Chỉ cài **một** bản Office trên một máy.

1. **Máy có Microsoft 365 / Office cài sẵn?** Máy Dell, Lenovo mới thường có. Trang Phần mềm sẽ hiện ở cột Trạng thái
   "Không cài được: máy đang có Microsoft 365…". Khi đó vào trang **Sửa lỗi → nhóm Office → Gỡ Microsoft 365 / Office
   cài sẵn (Click-to-Run)**, chạy (5–15 phút), khởi động lại máy, quay lại trang Phần mềm bấm **Kiểm tra lại**.
2. **Cài:** trang **Phần mềm**, nhóm Văn phòng, tick bản cần cài (Office 2016 64-bit, 2013 64-bit hoặc 2010 32-bit),
   bấm **Cài mục đã chọn**. Tool tự mount ISO, chạy `setup.exe /config <file xml>` im lặng (không có cửa sổ, không có
   thanh tiến độ), tháo ISO khi xong; mất 10–20 phút. Log của bộ cài Office nằm trong thư mục `%TEMP%` của tài khoản
   chạy tool (tên `Office 2016 Standard Setup(…).txt`, theo dòng `Logging` trong file XML). Lỗi thì xem mục 8.
3. **Kích hoạt:** nếu lúc cài máy chưa có Internet hoặc chưa điền key, chạy **Sửa lỗi → Office → Kích hoạt Office bản
   volume (MAK) và xem trạng thái**. Dòng ✔ "đã kích hoạt" là xong; ✖ thì xem lời báo (thiếu Internet, key MAK hết
   lượt…).
4. **Kiểm tra:** trang **Tổng quan**, dòng **Kích hoạt Office**. Mở thử Word, Excel bằng tài khoản người dùng.

Lưu ý:

- Office 2010 đã hết hỗ trợ từ 2020, chỉ cài cho máy chạy phần mềm cũ bắt buộc cần bản này.
- File `SW_DVD5_Office_2019.ISO` trong kho là **Office Online Server** (bản cho máy chủ SharePoint), không cài lên máy
  nhân viên.
- Sửa Office bản volume: Settings → Apps → Microsoft Office Standard → Modify → Repair. Hai mục "Sửa Office nhanh /
  trực tuyến" của tool chỉ dùng cho Office Click-to-Run.

---

## 5. Cài Symantec Endpoint Protection

1. Đã chép `SyLink.xml` của SEPM vào thư mục gói client (mục 1.3). Không có file này máy vẫn cài được nhưng là bản
   *unmanaged*, không báo về SEPM.
2. Trang **Phần mềm**, nhóm **Diệt virus**, tick **Symantec Endpoint Protection 14.3 RU9**, bấm **Cài mục đã chọn**.
   Tool chạy `Sep64.msi` im lặng (`SYMREBOOT=ReallySuppress`: không tự khởi động lại), log MSI nằm trong thư mục logs.
3. **Khởi động lại máy** (tool hỏi nếu bộ cài báo cần khởi động lại; không hỏi thì vẫn nên khởi động lại một lần).
4. **Kiểm tra:**
   - Biểu tượng Symantec dưới khay hệ thống không còn báo lỗi. Mở client → **Help → Troubleshooting → Management**:
     thấy tên máy chủ SEPM và nhóm (managed). Hoặc trên SEPM console thấy máy trong nhóm.
   - Trang **Tổng quan**, phần Bảo mật: dòng **Diệt virus: Symantec Endpoint Protection: đang bật, đã cập nhật**;
     Microsoft Defender tự chuyển sang không chạy vì máy có phần mềm diệt virus khác.
5. Máy đã có Symantec thì trang Phần mềm hiện "Đã cài" kèm phiên bản. Cài lại / nâng cấp: gỡ bản cũ trước (Settings →
   Apps), hoặc đẩy bản mới từ SEPM.

---

## 6. Phần mềm khác

- **UniKey:** nhóm Gõ tiếng Việt. Tool chép thư mục `SOFT\UniKey` vào Program Files, tạo shortcut Start Menu và cho
  chạy cùng Windows cho mọi người dùng.
- **Ứng dụng winget** (Chrome, Foxit, Zalo, 7-Zip, UltraViewer, VLC…): cần Internet. Thiếu winget thì chạy **Sửa lỗi →
  Phần mềm → Sửa / cài lại winget**.
- **Profile phòng ban:** chọn profile ở ô trên cùng rồi **Chọn theo profile** để tick sẵn các ứng dụng máy chưa có.
- **Công cụ hãng máy:** Dell Command | Update, Lenovo System Update (mục Cập nhật driver, BIOS của hãng tự cài khi cần).
- Thêm / bớt phần mềm trong danh mục: sửa `SOFT\config\apps.yaml` theo [SOFTWARE.md](SOFTWARE.md).

---

## 7. Các trang còn lại

| Trang | Dùng khi |
|---|---|
| **Tổng quan** | Xem nhanh máy: Windows, kích hoạt, phần cứng, serial, mạng, bảo mật. **Copy thông tin** dán vào ticket / Zalo; **Xuất HTML**; **Lưu kiểm kê** (ghi vào `Inventory\` cạnh tool và cập nhật `KiemKe.xlsx`) |
| **Sửa lỗi** | Mạng, domain, Windows Update, hệ thống, Office, bảo mật. Không chắc lỗi ở đâu thì bấm một **gói sửa nhanh** trên cùng. Mỗi mục ghi rõ lệnh sẽ chạy, mức rủi ro, hoàn tác được không |
| **Máy in** | Danh sách máy in, gỡ máy in / driver lỗi, in thử; thêm máy in qua IP (driver từ file .inf) hoặc share; tab Sửa lỗi có các mục **share máy in Win11 ↔ Win10** (bắt đầu bằng mục Kiểm tra share máy in) |
| **Tối ưu & dọn dẹp** | Dọn rác (quét trước rồi mới xoá), tìm file lớn, tắt chương trình khởi động cùng Windows, tắt quảng cáo / theo dõi |
| **Phần mềm** | Mục 4–6 ở trên |
| **Cấu hình** | Gói Cấu hình chuẩn máy mới và các tuỳ chọn hay dùng (hiện đuôi file, menu chuột phải kiểu cũ…) |
| **Tiện ích** | Mở nhanh công cụ quản trị; ping / tracert / kiểm tra cổng; tab **LAPS & BitLocker**: tra mật khẩu admin cục bộ và khoá khôi phục BitLocker của một máy (xem [BITLOCKER-LAPS-GPO.md](BITLOCKER-LAPS-GPO.md)) |
| **Nhật ký** | Các thay đổi registry tool đã làm, **hoàn tác** theo từng lần chạy |

---

## 8. Khi có lỗi

- Khung log ghi lời giải thích bằng tiếng Việt cho các mã lỗi hay gặp (ví dụ MSI 1603, 1618; winget; Dell Command |
  Update). Cột Trạng thái của mục hiện "✖ Lỗi" kèm giờ.
- **Mở thư mục log** (khung log) để lấy file log của phiên; log cài MSI (Symantec…) cũng nằm trong thư mục đó. Log cài
  Office bản volume nằm trong `%TEMP%` (mục 4 bước 2).
- Cài Office lỗi thường do: còn Office khác trên máy (mục 4 bước 1), ISO hỏng / không mount được (chép ISO về máy rồi
  thử lại), đang có bộ cài khác chạy (mã 1618, tool tự thử lại 3 lần).
- Mục nào chạy được bằng tay: bấm **Copy lệnh** ở khung chi tiết, dán vào PowerShell (admin) để chạy và xem lỗi trực tiếp.
