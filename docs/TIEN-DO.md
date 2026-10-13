# Tiến độ

Cập nhật: 13/10/2026. File này được cập nhật trước mỗi commit. Chi tiết: [PLAN](../PLAN.md), [HANDOFF](HANDOFF.md).

## Đang làm

- Hai bản mang theo: **USB** (tool + cài qua share mạng) và **SSD** (tool + kho bộ cài/ISO `SOFT` cạnh tool, không cần mạng).

## Đã xong (code xong, **chưa chạy thử bằng quyền admin trên máy ảo**)

| Giai đoạn | Đã có |
|---|---|
| GĐ0 Nền móng | Khung app, chạy lệnh nền, YAML, log, hoàn tác, restore point, đóng gói exe |
| GĐ1 Tổng quan + Sửa lỗi | Trang Tổng quan (copy, xuất HTML); 24 mục sửa lỗi P1; 5 gói sửa nhanh; Tiện ích (mở nhanh 29 công cụ, ping/tracert/nslookup/cổng) |
| GĐ2 Cài máy mới (một phần) | Trang Phần mềm (winget, share MSI/EXE/ISO/portable, profile phòng ban); bước 0 Kiểm tra trước; cấu hình chuẩn máy mới; sửa / cài lại winget; danh mục công ty trong `SOFT` (Office 2010/2013/2016 từ ISO, Symantec) |
| GĐ3 Tối ưu & dọn dẹp | Dọn rác có quét trước (8 loại, có cache trình duyệt); tìm file lớn; khởi động cùng Windows; tắt quảng cáo / theo dõi; power; gỡ app cài sẵn; các mục sửa lỗi P2 (hosts, firewall, Windows Update, WMI, MSI, Teams, RDP, BitLocker, Defender…) |

## Còn lại

| Giai đoạn | Việc | Chờ gì |
|---|---|---|
| GĐ2 | Wizard bước 1–7: gợi ý tên máy, đổi tên + join domain, tự chạy tiếp sau restart, báo cáo lên share | Bồ trả lời PLAN mục 11, câu 2–5 |
| GĐ2 | Bản Symantec managed (báo về SEPM) | `SyLink.xml` xuất từ SEPM |
| GĐ3 | Startup: task chạy lúc đăng nhập; P3: hiệu ứng hình ảnh, service Manual, chặn app "đồng hành" driver | |
| GĐ3 | Máy in: thêm qua IP / share, gỡ máy in lỗi, lỗi 0x11b / 0x709; xoá mật khẩu đã lưu; công cụ Outlook | Hãng, model máy in (câu 8) |
| GĐ4 | Tiện ích: sao lưu driver, xem event log, sửa HOSTS/PATH, file bị khoá, mật khẩu Wi-Fi, chuyển dữ liệu máy cũ | |
| GĐ4 | Gửi kiểm kê lên share, báo bản mới, ký số exe, hướng dẫn sử dụng, bản 1.0 | |

## Bồ cần làm

- Chạy thử trên máy ảo bằng quyền admin (danh sách từng mục trong [HANDOFF](HANDOFF.md)).
- Trả lời PLAN mục 11, nhất là câu 2–5.
- Điền key MAK vào `SOFT\config\office\*.xml` (nếu công ty dùng MAK).
