# Nhật ký thay đổi

## 0.1.0 (08/10/2026): GĐ0, nền móng

Nhánh `featured`, chưa merge về `main`.

### Thêm

- Cửa sổ chính PySide6:
  - Thanh trên cùng hiện tên máy, domain, bản Windows, trạng thái admin; cảnh báo khi tool chạy bằng tài khoản khác người đang đăng nhập.
  - Sidebar 8 trang, khung log có nút Huỷ.
- Trang Sửa lỗi / Cấu hình:
  - Cây mục có ô tick, tìm kiếm không dấu.
  - Khung chi tiết hiện mức rủi ro, áp cho ai, lệnh sẽ chạy (kèm lệnh `reg.exe` tương đương).
  - Nút Chạy, Copy lệnh, Hoàn tác, Xem trước.
- Trang Nhật ký: danh sách thay đổi registry, hoàn tác theo từng lần chạy, mở file log.
- Trang Tổng quan (bản cơ bản) và trang giới thiệu các phần sẽ làm (Cài máy mới, Phần mềm).
- Bộ chạy lệnh:
  - cmd/PowerShell ở nền, output đẩy từng dòng.
  - Tự nhận UTF-8 / UTF-16 / code page OEM.
  - Có timeout và huỷ.
  - PowerShell không bị Execution Policy chặn; tài khoản truyền qua stdin.
- Định nghĩa mục bằng YAML với 5 loại bước (`cmd`, `powershell`, `registry`, `service`, `builtin`), kiểm tra khai báo và báo lỗi bằng tiếng Việt.
- An toàn:
  - Restore point trước mục Cẩn thận/Nâng cao.
  - Nhật ký hoàn tác cho registry.
  - Kiểm tra GPO, bản Windows, quyền admin.
  - Che mật khẩu trong log.
- Thiết lập người dùng (HKCU) áp đúng người đang đăng nhập, kể cả khi IT dùng "Run as different user".
- 3 mục mẫu: Xoá cache DNS, Khởi động lại Explorer, Hiện đuôi file.
- `site.yaml` cho thông tin nội bộ (không commit), mẫu ở `site.example.yaml`.
- Đóng gói:
  - `packaging/build.py`: exe đòi quyền admin, có version info.
  - Bỏ phần Qt không dùng: 108MB → 64MB.
  - `--test` chạy selftest trên chính exe vừa build.
- `--selftest`: chụp ảnh từng trang và ghi `selftest.json`.
- 80 test pytest.

### Chưa kiểm chứng

- Chạy với quyền admin thật (restore point, mục `admin: true`).
- Chạy trên máy ảo Win10/Win11 sạch.

Chi tiết ở [docs/HANDOFF.md](docs/HANDOFF.md).
