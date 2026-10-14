# Tiến độ

Cập nhật: 14/10/2026. File này được cập nhật trước mỗi commit. Chi tiết: [PLAN](../PLAN.md), [HANDOFF](HANDOFF.md).

## Đang làm

- **Làm mới giao diện:** đã có [kế hoạch](KE-HOACH-GIAO-DIEN.md) và mockup 6 màn hình (trang chủ theo tình huống, tìm Ctrl+K, sửa lỗi có hướng dẫn, chọn bản Office, thanh tiến độ khi cài, wizard). **Chờ bồ duyệt** rồi làm đợt P0 (thanh tiến độ, chọn bản Office, chọn kho bộ cài).

## Đã xong (code xong, **chưa chạy thử bằng quyền admin trên máy ảo**)

| Giai đoạn | Đã có |
|---|---|
| Cài phần mềm công ty | **Office 2010 / 2013 / 2016** bản volume cài im lặng từ ISO (key MAK trong file XML), chặn khi máy có Microsoft 365 cài sẵn + mục gỡ nó, mục **kích hoạt Office** và xem trạng thái; **Symantec Endpoint Protection** (MSI im lặng, managed qua SEPM bằng SyLink.xml); UniKey, UltraViewer, ứng dụng winget; profile phòng ban. Cách dùng: [HUONG-DAN-SU-DUNG.md](HUONG-DAN-SU-DUNG.md) mục 4–6 |
| Hướng dẫn sử dụng | [HUONG-DAN-SU-DUNG.md](HUONG-DAN-SU-DUNG.md): chuẩn bị kho bộ cài, wizard, cài Office / Symantec, các trang, khi có lỗi |
| LAPS, BitLocker | [Hướng dẫn GPO, Windows LAPS, BitLocker](BITLOCKER-LAPS-GPO.md) (từng bước, lộ trình 4 tuần). Trong tool: tab **LAPS & BitLocker** ở trang Tiện ích (tra mật khẩu LAPS, bắt đổi, tra khoá BitLocker của máy khác; không ghi vào log); mục Kiểm tra Windows LAPS, Bật BitLocker (chỉ khi đủ điều kiện an toàn), Tạm dừng BitLocker |
| Kiểm kê | Nút "Lưu kiểm kê" (trang Tổng quan, wizard bước 7): `Inventory\` cạnh tool trên USB / SSD, file tổng hợp `KiemKe.xlsx` một dòng một máy (đã thử mở bằng Excel) |
| GĐ0 Nền móng | Khung app, chạy lệnh nền, YAML, log, hoàn tác, restore point, đóng gói exe |
| GĐ1 Tổng quan + Sửa lỗi | Trang Tổng quan (copy, xuất HTML); các mục sửa lỗi P1; gói sửa nhanh; Tiện ích (mở nhanh 29 công cụ, ping/tracert/nslookup/cổng) |
| GĐ2 Cài máy mới | **Wizard 8 bước:** kiểm tra trước; tên `FVPL-<mã phòng><2 số>` (thêm mã phòng mới, lưu vào site.yaml; gợi ý số kế tiếp từ AD); đổi tên + join OU chung; tự mở lại sau khi khởi động lại; gpupdate, nhóm IT vào Administrators; phần mềm theo profile; cấu hình chuẩn (có vi-VN); driver / BIOS của hãng (Dell Command \| Update, Lenovo System Update) + Windows Update; báo cáo HTML trên máy và ổ mang theo. **Mẫu** (ví dụ "Kế toán – Laptop": phòng, profile, phần mềm thêm như bản Office) chọn lại một lần là xong. Trang Phần mềm (winget, share MSI/EXE/ISO/portable); danh mục công ty trong `SOFT` |
| Hai bản mang theo | **USB** (tool + cài qua share) và **SSD** (tool + kho `SOFT` cạnh exe, không cần mạng); `packaging/deploy.py usb/ssd` chép ra ổ |
| GĐ3 Tối ưu & dọn dẹp | Dọn rác có quét trước (8 loại, có cache trình duyệt); tìm file lớn; khởi động cùng Windows (khoá Run, thư mục Startup, **task chạy lúc đăng nhập / bật máy**); hiệu ứng hình ảnh cho máy yếu; dịch vụ cập nhật Edge / Chrome / Adobe sang Manual; chặn app "đồng hành" driver; tắt quảng cáo / theo dõi; power; gỡ app cài sẵn; các mục sửa lỗi P2 (hosts, firewall, Windows Update, WMI, MSI, Teams, RDP, BitLocker, Defender…) |
| GĐ4 Tiện ích (một phần) | Trang Tiện ích thêm tab **Event log** (lỗi Critical / Error 24 giờ / 7 / 30 ngày, gộp theo loại, gợi ý tiếng Việt) và **Công cụ khác**: sao lưu / cài lại driver (`DriverBackup\` cạnh tool), sao lưu rồi sửa HOSTS, tìm chương trình đang khoá file, mật khẩu Wi-Fi đã lưu; Chẩn đoán RAM ở Mở nhanh |
| Trang Máy in | Danh sách máy in (kể cả share của người đang đăng nhập), gỡ máy in / driver, in thử; thêm qua IP (driver từ file .inf) và qua share; **sửa share máy in Win11 ↔ Win10** |
| Câu hỏi PLAN mục 11 | Đã trả lời hết (13/10/2026) |

## Còn lại (theo thứ tự sẽ làm)

| # | Việc | Ghi chú |
|---|---|---|
| 1 | Làm mới giao diện, đợt P0 → P3 | Sau khi bồ duyệt [kế hoạch](KE-HOACH-GIAO-DIEN.md) mục 7 |
| 2 | GĐ4 còn lại: chuyển dữ liệu máy cũ, sửa PATH, báo bản mới, ký số exe, bản 1.0 | |

## Bồ cần làm

- Xem mockup (link mình gửi trong chat) và [kế hoạch giao diện](KE-HOACH-GIAO-DIEN.md): duyệt, hoặc ghi chỗ cần sửa.
- Đọc [hướng dẫn GPO, LAPS, BitLocker](BITLOCKER-LAPS-GPO.md), làm theo lộ trình ở mục 5 (bắt đầu bằng nhóm máy thử).
- Chạy thử trên máy ảo bằng quyền admin (danh sách từng mục trong [HANDOFF](HANDOFF.md)). Wizard cần một VM chưa join và domain test (hoặc domain thật với tài khoản join); trang Máy in cần một máy Win11 share máy in và một máy Win10.
- Điền vào `site.yaml` (mẫu: `site.example.yaml`; file này không lên git): `share_root`, `domain`, `netbios_domain`, **`computer_ou`** (OU chung của máy trạm), **`it_admins_group`** (nhóm IT thêm vào Administrators, bỏ trống nếu không cần). Mã phòng ban thì thêm dần ngay trong wizard.
- Điền key MAK vào `SOFT\config\office\*.xml`.
- Xuất `SyLink.xml` từ SEPM, chép đè vào `SOFT\Symantec\SEP-14.3-RU9-Win64\`.
- Chép thư mục UniKey vào `SOFT\UniKey\`, driver token Viettel-CA, VNPT-CA, FPT-CA vào `SOFT` (mình thêm vào danh mục khi có), driver máy in hay dùng (đã giải nén) vào `SOFT\Drivers\Printers\<hãng>\`.
- Build bản phát hành rồi chép ra ổ: `packaging\deploy.py usb E:\` / `ssd F:\`.
