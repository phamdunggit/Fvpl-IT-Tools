# Tiến độ

Cập nhật: 13/10/2026. File này được cập nhật trước mỗi commit. Chi tiết: [PLAN](../PLAN.md), [HANDOFF](HANDOFF.md).

## Đang làm

- Không có việc dở. Việc tiếp theo: số 1 ở bảng "Còn lại" (wizard Cài máy mới).

## Đã xong (code xong, **chưa chạy thử bằng quyền admin trên máy ảo**)

| Giai đoạn | Đã có |
|---|---|
| GĐ0 Nền móng | Khung app, chạy lệnh nền, YAML, log, hoàn tác, restore point, đóng gói exe |
| GĐ1 Tổng quan + Sửa lỗi | Trang Tổng quan (copy, xuất HTML); các mục sửa lỗi P1; gói sửa nhanh; Tiện ích (mở nhanh 29 công cụ, ping/tracert/nslookup/cổng) |
| GĐ2 Cài máy mới (một phần) | Trang Phần mềm (winget, share MSI/EXE/ISO/portable, profile phòng ban); bước 0 Kiểm tra trước; cấu hình chuẩn máy mới; sửa / cài lại winget; danh mục công ty trong `SOFT` (Office 2010/2013/2016 từ ISO, Symantec, UniKey, UltraViewer) |
| Hai bản mang theo | **USB** (tool + cài qua share) và **SSD** (tool + kho `SOFT` cạnh exe, không cần mạng); `packaging/deploy.py usb/ssd` chép ra ổ |
| GĐ3 Tối ưu & dọn dẹp | Dọn rác có quét trước (8 loại, có cache trình duyệt); tìm file lớn; khởi động cùng Windows; tắt quảng cáo / theo dõi; power; gỡ app cài sẵn; các mục sửa lỗi P2 (hosts, firewall, Windows Update, WMI, MSI, Teams, RDP, BitLocker, Defender…) |
| Trang Máy in | Danh sách máy in (kể cả share của người đang đăng nhập), gỡ máy in / driver, in thử; thêm qua IP (driver từ file .inf) và qua share; **sửa share máy in Win11 ↔ Win10** (kiểm tra, máy chia sẻ, máy kết nối, lỗi 0x0000011b) |
| Câu hỏi PLAN mục 11 | Đã trả lời hết (13/10/2026) |

## Còn lại (theo thứ tự sẽ làm)

| # | Việc | Ghi chú |
|---|---|---|
| 1 | GĐ2 wizard: tên `FVPL-<mã phòng><2 số>` (thêm mã phòng mới khi gặp và lưu lại), join vào một OU chung bằng tài khoản join, tự chạy tiếp sau restart, cấu hình chuẩn, báo cáo | Không còn chờ gì |
| 2 | Cấu hình chuẩn: định dạng vùng **vi-VN** | |
| 3 | Cập nhật driver Dell (Dell Command \| Update) và Lenovo (System Update) | |
| 4 | Kiểm kê: lưu thông tin máy lên **ổ mang theo** (không gửi share), có file tổng hợp mở bằng Excel | GĐ4 |
| 5 | Hướng dẫn triển khai **BitLocker, Windows LAPS, GPO** cho công ty | Bồ muốn tìm hiểu |
| 6 | Startup: task chạy lúc đăng nhập; P3: hiệu ứng hình ảnh, service Manual, chặn app "đồng hành" driver | |
| 7 | GĐ4: sao lưu driver, xem event log, sửa HOSTS/PATH, file bị khoá, mật khẩu Wi-Fi, chuyển dữ liệu máy cũ, báo bản mới, ký số exe, hướng dẫn sử dụng, bản 1.0 | |

## Bồ cần làm

- Chạy thử trên máy ảo bằng quyền admin (danh sách từng mục trong [HANDOFF](HANDOFF.md)). Trang Máy in cần một máy Win11 share máy in và một máy Win10 kết nối tới.
- Điền `share_root` (share của IT), `domain` vào `site.yaml` (mẫu: `site.example.yaml`; file này không lên git).
- Điền key MAK vào `SOFT\config\office\*.xml`.
- Xuất `SyLink.xml` từ SEPM, chép đè vào `SOFT\Symantec\SEP-14.3-RU9-Win64\`.
- Chép thư mục UniKey vào `SOFT\UniKey\`, driver token Viettel-CA, VNPT-CA, FPT-CA vào `SOFT` (mình thêm vào danh mục khi có), driver máy in hay dùng (đã giải nén) vào `SOFT\Drivers\Printers\<hãng>\`.
- Build bản phát hành rồi chép ra ổ: `packaging\deploy.py usb E:\` / `ssd F:\`.
