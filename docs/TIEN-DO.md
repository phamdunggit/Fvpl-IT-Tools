# Tiến độ

Cập nhật: 13/10/2026. File này được cập nhật trước mỗi commit. Chi tiết: [PLAN](../PLAN.md), [HANDOFF](HANDOFF.md).

## Đang làm

- Không có việc dở. Việc tiếp theo: số 1 ở bảng "Còn lại" (driver Dell / Lenovo).

## Đã xong (code xong, **chưa chạy thử bằng quyền admin trên máy ảo**)

| Giai đoạn | Đã có |
|---|---|
| GĐ0 Nền móng | Khung app, chạy lệnh nền, YAML, log, hoàn tác, restore point, đóng gói exe |
| GĐ1 Tổng quan + Sửa lỗi | Trang Tổng quan (copy, xuất HTML); các mục sửa lỗi P1; gói sửa nhanh; Tiện ích (mở nhanh 29 công cụ, ping/tracert/nslookup/cổng) |
| GĐ2 Cài máy mới | **Wizard 8 bước:** kiểm tra trước; tên `FVPL-<mã phòng><2 số>` (thêm mã phòng mới, lưu vào site.yaml; gợi ý số kế tiếp từ AD); đổi tên + join OU chung; tự mở lại sau khi khởi động lại; gpupdate, nhóm IT vào Administrators; phần mềm theo profile; cấu hình chuẩn (có vi-VN); Windows Update; báo cáo HTML trên máy và ổ mang theo. Trang Phần mềm (winget, share MSI/EXE/ISO/portable); danh mục công ty trong `SOFT` |
| Hai bản mang theo | **USB** (tool + cài qua share) và **SSD** (tool + kho `SOFT` cạnh exe, không cần mạng); `packaging/deploy.py usb/ssd` chép ra ổ |
| GĐ3 Tối ưu & dọn dẹp | Dọn rác có quét trước (8 loại, có cache trình duyệt); tìm file lớn; khởi động cùng Windows; tắt quảng cáo / theo dõi; power; gỡ app cài sẵn; các mục sửa lỗi P2 (hosts, firewall, Windows Update, WMI, MSI, Teams, RDP, BitLocker, Defender…) |
| Trang Máy in | Danh sách máy in (kể cả share của người đang đăng nhập), gỡ máy in / driver, in thử; thêm qua IP (driver từ file .inf) và qua share; **sửa share máy in Win11 ↔ Win10** |
| Câu hỏi PLAN mục 11 | Đã trả lời hết (13/10/2026) |

## Còn lại (theo thứ tự sẽ làm)

| # | Việc | Ghi chú |
|---|---|---|
| 1 | Cập nhật driver Dell (Dell Command \| Update) và Lenovo (System Update) | |
| 2 | Kiểm kê: lưu thông tin máy lên **ổ mang theo** (không gửi share), có file tổng hợp mở bằng Excel | GĐ4 |
| 3 | Hướng dẫn triển khai **BitLocker, Windows LAPS, GPO** cho công ty | Bồ muốn tìm hiểu |
| 4 | Wizard: lưu **mẫu** (ví dụ "Kế toán – Laptop") để lần sau chọn lại | |
| 5 | Startup: task chạy lúc đăng nhập; P3: hiệu ứng hình ảnh, service Manual, chặn app "đồng hành" driver | |
| 6 | GĐ4: sao lưu driver, xem event log, sửa HOSTS/PATH, file bị khoá, mật khẩu Wi-Fi, chuyển dữ liệu máy cũ, báo bản mới, ký số exe, hướng dẫn sử dụng, bản 1.0 | |

## Bồ cần làm

- Chạy thử trên máy ảo bằng quyền admin (danh sách từng mục trong [HANDOFF](HANDOFF.md)). Wizard cần một VM chưa join và domain test (hoặc domain thật với tài khoản join); trang Máy in cần một máy Win11 share máy in và một máy Win10.
- Điền vào `site.yaml` (mẫu: `site.example.yaml`; file này không lên git): `share_root`, `domain`, `netbios_domain`, **`computer_ou`** (OU chung của máy trạm), **`it_admins_group`** (nhóm IT thêm vào Administrators, bỏ trống nếu không cần). Mã phòng ban thì thêm dần ngay trong wizard.
- Điền key MAK vào `SOFT\config\office\*.xml`.
- Xuất `SyLink.xml` từ SEPM, chép đè vào `SOFT\Symantec\SEP-14.3-RU9-Win64\`.
- Chép thư mục UniKey vào `SOFT\UniKey\`, driver token Viettel-CA, VNPT-CA, FPT-CA vào `SOFT` (mình thêm vào danh mục khi có), driver máy in hay dùng (đã giải nén) vào `SOFT\Drivers\Printers\<hãng>\`.
- Build bản phát hành rồi chép ra ổ: `packaging\deploy.py usb E:\` / `ssd F:\`.
