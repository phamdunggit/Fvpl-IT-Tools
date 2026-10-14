# Tiến độ

Cập nhật: 14/10/2026. File này được cập nhật trước mỗi commit. Chi tiết: [PLAN](../PLAN.md), [HANDOFF](HANDOFF.md).

## Đang làm

- **Ba việc bồ yêu cầu ngày 14/10/2026**: (1) gỡ phần mềm, phần mềm rác như WPS (**xong**), (2) sao lưu dữ liệu ổ C trước khi cài lại Windows, tự lưu về một chỗ rồi lấy lại, (3) chỗ nhập key Windows / Office (mỗi bản nhiều key), lưu vào một file mang đi dùng được, kích hoạt từ tool.
- **Làm mới giao diện** theo [kế hoạch](KE-HOACH-GIAO-DIEN.md) (bồ đã duyệt 14/10/2026). **Xong cả 4 đợt (P0 → P3).** Còn lại là thử với người thật (2–3 người không làm IT tự làm "Không in được", "Cài phần mềm") và thử trên máy ảo có lỗi thật.

## Đã xong (code xong, **chưa chạy thử bằng quyền admin trên máy ảo**)

| Giai đoạn | Đã có |
|---|---|
| Cài phần mềm công ty | **Office 2010 / 2013 / 2016** bản volume cài im lặng từ ISO (key MAK trong file XML), chặn khi máy có Microsoft 365 cài sẵn + mục gỡ nó, mục **kích hoạt Office** và xem trạng thái; **Symantec Endpoint Protection** (MSI im lặng, managed qua SEPM bằng SyLink.xml); UniKey, UltraViewer, ứng dụng winget; profile phòng ban. Cách dùng: [HUONG-DAN-SU-DUNG.md](HUONG-DAN-SU-DUNG.md) mục 4–6 |
| Hướng dẫn sử dụng | [HUONG-DAN-SU-DUNG.md](HUONG-DAN-SU-DUNG.md): chuẩn bị kho bộ cài, wizard, cài Office / Symantec, các trang, khi có lỗi |
| LAPS, BitLocker | [Hướng dẫn GPO, Windows LAPS, BitLocker](BITLOCKER-LAPS-GPO.md) (từng bước, lộ trình 4 tuần). Trong tool: tab **LAPS & BitLocker** ở trang Tiện ích (tra mật khẩu LAPS, bắt đổi, tra khoá BitLocker của máy khác; không ghi vào log); mục Kiểm tra Windows LAPS, Bật BitLocker (chỉ khi đủ điều kiện an toàn), Tạm dừng BitLocker |
| Kiểm kê | Nút "Lưu kiểm kê" (trang Thông tin máy, wizard bước 7): `Inventory\` cạnh tool trên USB / SSD, file tổng hợp `KiemKe.xlsx` một dòng một máy (đã thử mở bằng Excel) |
| GĐ0 Nền móng | Khung app, chạy lệnh nền, YAML, log, hoàn tác, restore point, đóng gói exe |
| GĐ1 Tổng quan + Sửa lỗi | Trang Tổng quan (copy, xuất HTML); các mục sửa lỗi P1; gói sửa nhanh; Tiện ích (mở nhanh 29 công cụ, ping/tracert/nslookup/cổng) |
| GĐ2 Cài máy mới | **Wizard 8 bước:** kiểm tra trước; tên `FVPL-<mã phòng><2 số>` (thêm mã phòng mới, lưu vào site.yaml; gợi ý số kế tiếp từ AD); đổi tên + join OU chung; tự mở lại sau khi khởi động lại; gpupdate, nhóm IT vào Administrators; phần mềm theo profile; cấu hình chuẩn (có vi-VN); driver / BIOS của hãng (Dell Command \| Update, Lenovo System Update) + Windows Update; báo cáo HTML trên máy và ổ mang theo. **Mẫu** (ví dụ "Kế toán – Laptop": phòng, profile, phần mềm thêm như bản Office) chọn lại một lần là xong. Trang Cài phần mềm (winget, share MSI/EXE/ISO/portable); danh mục công ty trong `SOFT` |
| Hai bản mang theo | **USB** (tool + cài qua share) và **SSD** (tool + kho `SOFT` cạnh exe, không cần mạng); `packaging/deploy.py usb/ssd` chép ra ổ |
| GĐ3 Tối ưu & dọn dẹp | Dọn rác có quét trước (8 loại, có cache trình duyệt); tìm file lớn; **gỡ phần mềm** (tab Gỡ phần mềm: cả phần mềm cài riêng cho người dùng như WPS, gỡ im lặng khi được, phần mềm rác đánh dấu Nên gỡ và báo ở Trang chủ, danh sách sửa được ở `SOFT\config\uninstall.yaml`); khởi động cùng Windows (khoá Run, thư mục Startup, **task chạy lúc đăng nhập / bật máy**); hiệu ứng hình ảnh cho máy yếu; dịch vụ cập nhật Edge / Chrome / Adobe sang Manual; chặn app "đồng hành" driver; tắt quảng cáo / theo dõi; power; gỡ app cài sẵn; các mục sửa lỗi P2 (hosts, firewall, Windows Update, WMI, MSI, Teams, RDP, BitLocker, Defender…) |
| Giao diện mới, đợt P3 | Mọi trang theo khung mới (màu trang Thông tin máy, Nhật ký có dòng báo trống); **thanh tiến độ trên taskbar** Windows (đỏ khi có lỗi); **"còn khoảng N phút"** theo thời gian chạy thật các lần trước (`durations.json`); **hướng dẫn nhanh 3 bước** lần đầu mở tool (F1 xem lại); phím tắt **Ctrl+1…0**; ô Trang chủ tự giãn khi cỡ chữ 150%; **ảnh giao diện mới** trong hướng dẫn sử dụng |
| Giao diện mới, đợt P2 (phần sau) | Trang **Cài phần mềm dạng thẻ** (mỗi phần mềm một thẻ: tên, một câu giải thích, nguồn / trạng thái, bấm để chọn); wizard **thanh bước nằm ngang**, **thẻ chọn bản Office** ở bước 1, mỗi bước cuộn được khi cửa sổ thấp; **tên dễ hiểu** (`basic_name`) cho 17 mục có tên kỹ thuật ở chế độ Cơ bản; **thông báo khay hệ thống** khi chạy xong mà cửa sổ đang thu nhỏ |
| Giao diện mới, đợt P2 (phần đầu) | **Sửa lỗi theo tình huống** từng bước (Kiểm tra → Sửa → Kết quả) cho 6 tình huống: mạng, máy in, domain / ổ chung, máy chậm, Office, Windows Update (`scenarios.yaml`, script kiểm tra chỉ đọc trong `data/scripts/scenarios/`, đã chạy thật trên máy dev); mở từ ô Trang chủ, Ctrl+K, thanh "Hướng dẫn từng bước" trên trang Sửa lỗi. **Gửi kết quả cho IT**: báo cáo vào clipboard + file HTML |
| Giao diện mới, đợt P1 | **Khung kiểu Windows 11** (màu, chữ Segoe UI Variable, icon nét mảnh tự vẽ, thanh trên trắng, sidebar có icon, thanh trạng thái dưới cùng, khung log thành ngăn kéo "Chi tiết kỹ thuật"); **Trang chủ**: 8 ô theo việc cần làm, khung **Tình trạng máy này** có nút sửa, banner cài dở; **chế độ Cơ bản / Chuyên gia** (Cơ bản ẩn mục Nâng cao, tab Event log / LAPS, gập log; nhớ lựa chọn); **tìm Ctrl+K** (bỏ dấu, mã lỗi, từ khoá cho 51 mục sửa lỗi / máy in; mở đúng trang, tab, mục) |
| Giao diện mới, đợt P0 | **Thanh tiến độ** cho mọi lượt chạy nhiều mục (mục n/N, % tải về của winget, từng mục ✔ / ✖ kèm lý do, dừng sau mục đang chạy, thẻ kết quả + Thử lại mục lỗi) ở trang Cài phần mềm, wizard bước 3 / 5 / 6 và khung log; **thẻ chọn bản Office** (Không cài / 2016 / 2013 / 2010 / 365), có cả khi chạy bản zip không kèm kho; máy có Microsoft 365 cài sẵn thì tick **Gỡ trước khi cài**; **banner kho bộ cài + Chọn kho…** (nhớ cho lần sau) |
| GĐ4 Tiện ích | **Chuyển dữ liệu máy cũ** (Tiện ích → Chuyển máy: sao lưu Desktop / Documents / Downloads / Pictures, bookmark, chữ ký Outlook ra ổ mang theo kèm danh sách máy in, phần mềm; khôi phục không ghi đè file mới hơn, chọn sẵn phần mềm ở trang Cài phần mềm). **Báo bản mới** (version.json trên share, `deploy.py share`), **ký số exe** khi build (cần chứng chỉ, [KY-SO.md](KY-SO.md)). **Sửa biến PATH** (bỏ mục hỏng / trùng, hoàn tác được). Trang Tiện ích thêm tab **Event log** (lỗi Critical / Error 24 giờ / 7 / 30 ngày, gộp theo loại, gợi ý tiếng Việt) và **Công cụ khác**: sao lưu / cài lại driver (`DriverBackup\` cạnh tool), sao lưu rồi sửa HOSTS, tìm chương trình đang khoá file, mật khẩu Wi-Fi đã lưu; Chẩn đoán RAM ở Mở nhanh |
| Trang Máy in | Danh sách máy in (kể cả share của người đang đăng nhập), gỡ máy in / driver, in thử; thêm qua IP (driver từ file .inf) và qua share; **sửa share máy in Win11 ↔ Win10** |
| Câu hỏi PLAN mục 11 | Đã trả lời hết (13/10/2026) |

## Còn lại (theo thứ tự sẽ làm)

| # | Việc | Ghi chú |
|---|---|---|
| 1 | Thử giao diện mới với 2–3 người không làm IT, sửa theo góp ý | [Kế hoạch](KE-HOACH-GIAO-DIEN.md) mục 7, cột "Xong khi" của P2 |
| 2 | Sao lưu dữ liệu trước khi cài lại Windows | Tự chọn chỗ lưu không nằm trên ổ C, gồm cả thư mục lạ trên ổ C, Wi-Fi, driver; cài lại xong tự tìm bản sao lưu |
| 3 | Quản lý key Windows / Office, kích hoạt | File key nằm ngoài repo, không ghi key vào log |
| 4 | Bản 1.0 | Mọi chức năng GĐ4 đã có code. Chờ chạy thử trên VM bằng quyền admin (HANDOFF) rồi bồ duyệt mới đặt 1.0 và merge vào main |

## Bồ cần làm

- Chạy thử bản build mới: Trang chủ, ô tìm Ctrl+K, nút Cơ bản / Chuyên gia; trang Cài phần mềm (chọn bản Office, Chọn
  kho…, thanh tiến độ khi cài). Kho `SOFT` trên SSD cần
  thêm dòng `choice: office` cho các bản Office trong `config\apps.yaml` (bản trên máy dev đã thêm; chép lại kho ra SSD
  bằng `deploy.py ssd` hoặc sửa tay).
- Đọc [hướng dẫn GPO, LAPS, BitLocker](BITLOCKER-LAPS-GPO.md), làm theo lộ trình ở mục 5 (bắt đầu bằng nhóm máy thử).
- Chạy thử trên máy ảo bằng quyền admin (danh sách từng mục trong [HANDOFF](HANDOFF.md)). Wizard cần một VM chưa join và domain test (hoặc domain thật với tài khoản join); trang Máy in cần một máy Win11 share máy in và một máy Win10.
- Điền vào `site.yaml` (mẫu: `site.example.yaml`; file này không lên git): `share_root`, `domain`, `netbios_domain`, **`computer_ou`** (OU chung của máy trạm), **`it_admins_group`** (nhóm IT thêm vào Administrators, bỏ trống nếu không cần). Mã phòng ban thì thêm dần ngay trong wizard.
- Điền key MAK vào `SOFT\config\office\*.xml`.
- Xuất `SyLink.xml` từ SEPM, chép đè vào `SOFT\Symantec\SEP-14.3-RU9-Win64\`.
- Chép thư mục UniKey vào `SOFT\UniKey\`, driver token Viettel-CA, VNPT-CA, FPT-CA vào `SOFT` (mình thêm vào danh mục khi có), driver máy in hay dùng (đã giải nén) vào `SOFT\Drivers\Printers\<hãng>\`.
- Build bản phát hành rồi chép ra ổ: `packaging\deploy.py usb E:\` / `ssd F:\`.
