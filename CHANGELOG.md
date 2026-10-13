# Nhật ký thay đổi

## 0.2.0 (13/10/2026): GĐ1, Tổng quan + Sửa lỗi

Nhánh `featured`, chưa merge về `main`. Các mục đổi hệ thống **chưa chạy thật bằng quyền admin**, xem [docs/HANDOFF.md](docs/HANDOFF.md).

### Thêm

- Trang **Tổng quan** đầy đủ:
  - Hệ điều hành, kích hoạt Windows/Office (chỉ xem), phần cứng (model, serial, CPU, RAM theo khe, ổ đĩa SSD/HDD và sức khoẻ, phân vùng, GPU, màn hình).
  - Mạng: IP, DHCP/tĩnh, gateway, DNS, MAC, Wi-Fi/LAN; từng DNS server có tìm được DC không.
  - Bảo mật: Defender, phần mềm diệt virus khác, firewall, BitLocker, TPM, Secure Boot, lần cập nhật Windows gần nhất.
  - Dòng cần để ý được tô màu. Nút Làm mới, Copy thông tin (dán vào ticket/Zalo), Xuất HTML.
  - Đọc nền bằng 4 script PowerShell song song, khoảng 4 giây.
  - Thanh trên cùng báo "DNS không trỏ về DC".
- Trang Sửa lỗi có 24 mục (thêm 22 mục P1):
  - Mạng: chẩn đoán, xoá cache DNS, xin lại IP, xoá proxy người dùng, xoá proxy WinHTTP, khởi động lại card mạng, reset Winsock + TCP/IP.
  - Domain: kiểm tra kết nối, sửa trust relationship (hỏi tài khoản), đồng bộ giờ, gpupdate, báo cáo gpresult.
  - Máy in: liệt kê, xoá lệnh in kẹt, khởi động lại Spooler.
  - Windows Update: reset.
  - Hệ thống: DISM + SFC, chkdsk /scan, hẹn chkdsk khi khởi động, xây lại cache icon, sửa mất âm thanh.
  - Office: Quick Repair, Online Repair.
- 5 **gói sửa nhanh** trên đầu trang Sửa lỗi: Sửa mạng, Reset mạng toàn bộ, Sửa máy in, Sửa Windows Update, Sửa domain. Một bước lỗi thì dừng.
- Hộp thoại **tài khoản domain** cho mục `needs_credential`.
- Trang **Tiện ích**: mở nhanh 29 công cụ quản trị; công cụ mạng (ping, tracert, nslookup, kiểm tra cổng).
- Khai báo YAML: `requires_domain`, `messages` (giải thích mã thoát), biến `$TargetUser*`/`$ReportDir`, bộ hàm kiểm tra dựng sẵn (`core/pslib.py`), `data/packs.yaml`.
- Builtin `rebuild_icon_cache`. Khi Explorer không tự mở lại mà tool có quyền admin thì mở lại bằng tài khoản người dùng.
- Test: soát cú pháp mọi script PowerShell bằng parser của PowerShell; đọc thông tin máy thật (chỉ đọc). 130 test.
- `--selftest` chờ trang Tổng quan đọc xong, báo lỗi nếu phần nào hỏng.

### Sửa

- PowerShell chạy bằng `-Command` kèm đoạn mồi giải mã thay cho `-EncodedCommand`: trước đây cảnh báo, `Write-Host`, verbose ra log thành khối CLIXML.
- Script PowerShell quá dài thì tự bỏ chú thích và thụt lề cho vừa giới hạn dòng lệnh.
- Không dùng cmdlet phải nạp module chậm: bản đầu của trang Tổng quan mất 134 giây trên máy dev, giờ 4 giây.

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
