# Nhật ký thay đổi

## Chưa phát hành: GĐ2 (Cài máy mới), GĐ3 (Tối ưu & dọn dẹp), trang Máy in

### Thêm

- **Wizard Cài máy mới** (trang Cài máy mới, 8 bước, tiến độ lưu lại để làm tiếp sau khi khởi động lại):
  - Bước 1: chọn phòng ban, **thêm mã phòng mới** (ghi vào `departments` trong site.yaml, giữ chú thích), **gợi ý tên** `<tiền tố><mã><2 số>` theo số lớn nhất đang có trong AD (máy chưa join thì hỏi AD bằng tài khoản join), báo tên đã có (KB5020276); người dùng chính, profile phần mềm.
  - Bước 2: chép tool vào `%ProgramData%\FVPL-ITTools\app` (chỉ admin ghi được), đổi tên + join domain vào OU chung trong một lần khởi động lại, hẹn tool tự mở lại (`--resume`) khi admin đăng nhập; lỗi join kèm gợi ý theo nguyên nhân.
  - Bước 3: kiểm tra đã vào domain / đúng tên / secure channel, đồng bộ giờ, gpupdate, thêm nhóm IT (`it_admins_group`) vào Administrators.
  - Bước 4–6: mở trang Phần mềm với profile tick sẵn, gói Cấu hình chuẩn, driver của hãng + Windows Update; kết quả tự ghi vào bước.
  - Bước 7: báo cáo HTML (các bước, hệ điều hành, phần cứng + serial, phần mềm như Programs and Features), lưu trên máy và `Reports\` cạnh tool trên ổ mang theo; Kết thúc thì bỏ hẹn mở lại.
  - Sau khởi động lại, trang Phần mềm vẫn dùng được kho SOFT trên SSD nếu ổ còn cắm đúng chỗ.
- **Kiểm kê ra ổ mang theo**: nút "Lưu kiểm kê" ở trang Tổng quan (và bước 7 của wizard) lưu thông tin máy vào `Inventory\<tên máy>.json` cạnh tool trên USB / SSD, rồi dựng lại `KiemKe.xlsx` (một dòng một máy, 25 cột: hãng, model, serial, CPU, RAM, ổ đĩa, Windows, kích hoạt, Office, IP, MAC, diệt virus, BitLocker, TPM, cập nhật gần nhất…; có lọc, cố định dòng tiêu đề). Máy đổi tên mà cùng serial thì thay bản cũ. Ghi .xlsx trực tiếp, không cần Excel; chữ không bao giờ bị hiểu là công thức.
- Mục **Cập nhật driver, BIOS của hãng** (trang Sửa lỗi, nhóm Driver & BIOS; bước 6 của wizard): tự nhận Dell / Lenovo, chạy Dell Command | Update (tạm dừng BitLocker khi cập nhật BIOS) hoặc Lenovo System Update, chưa có công cụ thì cài bằng winget; giải thích mã lỗi của Dell bằng tiếng Việt. Danh mục phần mềm thêm nhóm "Công cụ hãng máy".
- Mục **Định dạng vùng Việt Nam (vi-VN)** (trang Cấu hình, có trong gói Cấu hình chuẩn): tài khoản đang chạy tool, màn hình đăng nhập và tài khoản mới.
- site.yaml thêm `computer_ou`, `it_admins_group`, `departments`.
- Trang **Máy in** (mục sửa máy in chuyển từ trang Sửa lỗi sang), ba tab:
  - **Máy in trên máy**: máy in IP / USB / WSD / ảo, máy in share của cả máy và của người đang đăng nhập (đọc từ hive của họ khi IT chạy tool bằng tài khoản khác), driver, trạng thái, lệnh chờ, máy in mặc định. In trang thử, mở hàng đợi, gỡ máy in (kèm cổng TCP/IP không còn dùng, và driver nếu chọn).
  - **Thêm máy in**: qua IP (driver đã cài, driver có sẵn trong Windows như Microsoft IPP Class Driver, hoặc file .inf của hãng: tool đọc tên model trong file để chọn); máy in share `\\máy\tên` (cài driver bằng quyền admin để tránh 0x00000bcb, tuỳ chọn thêm cho mọi người dùng bằng `printui /ga`). Lỗi kết nối kèm gợi ý theo mã lỗi.
  - **Sửa lỗi**: gói "Sửa máy in", nhóm "Share máy in Win11 ↔ Win10": mục kiểm tra (cách gọi RPC, Spooler, firewall, mạng Public, máy chia sẻ có trả lời không, bảng mã lỗi), máy chia sẻ nhận cả Named Pipes và mở firewall File and Printer Sharing, máy Win11 22H2+ kết nối bằng Named Pipes (0x00000709, 0x0000007c), bỏ yêu cầu mã hoá RPC (0x0000011b, Nâng cao). Đều hoàn tác được.
- Builtin `restart_spooler` (dùng trong `after`).
- Trang **Tối ưu & dọn dẹp** (GĐ3), ba tab:
  - **Dọn rác**: quét trước 7 loại (Temp người dùng, Temp Windows, bản cập nhật đã tải, cache Delivery Optimization, dump và báo cáo lỗi, thùng rác, Windows.old), hiện dung lượng và số file, tick rồi mới xoá. File Temp sửa trong 24 giờ được giữ; không đi theo junction/symlink; file đang khoá thì bỏ qua. Windows.old và Delivery Optimization dọn bằng Disk Cleanup.
  - **Khởi động cùng Windows**: danh sách từ khoá Run và thư mục Startup, bật/tắt kiểu Task Manager (StartupApproved), có nhật ký và hoàn tác.
  - **Tối ưu & quyền riêng tư**: tắt quảng cáo và gợi ý, Bing trong Start, Widgets, Copilot, ID quảng cáo, giảm telemetry; power plan High performance, tắt ngủ đông, tắt USB selective suspend; gỡ app cài sẵn theo danh sách chọn lọc (kèm mục liệt kê để xem trước); gói "Tắt quảng cáo và theo dõi".
- **Hai bản mang theo**: tool tự chọn kho bộ cài: thư mục `SOFT` cạnh file exe (bản SSD, không cần mạng), không thì `share_root` (bản USB). `packaging/deploy.py usb|ssd <ổ>` chép tool (và kho SOFT) ra ổ bằng robocopy, kiểm tra chỗ trống.
- Danh mục phần mềm cài thẳng từ ISO (kiểu `iso`); dọn cache trình duyệt; tab Tìm file lớn.
- Cột trạng thái của mục có phần kiểm tra hiện "✔ Đã áp dụng" / "Chưa áp dụng" thay cho "Đang bật" / "Đang tắt".

- Trang **Phần mềm**:
  - Danh mục `apps.yaml` (winget, share MSI/EXE/portable) và profile phòng ban kế thừa nhau. Bản trên `<share_root>\config\apps.yaml` được ưu tiên; bản đóng gói kèm tool là danh sách gợi ý, chưa chốt. Cách khai báo: [docs/SOFTWARE.md](docs/SOFTWARE.md).
  - Đánh dấu phần mềm đã cài kèm phiên bản (đọc Programs and Features, không cần winget).
  - Chọn theo profile, tìm không dấu, xem trước lệnh, cài lần lượt, thử lại mục lỗi. Ứng dụng không cài được thì ghi rõ lý do.
  - MSI ghi log riêng và tự thử lại khi gặp mã 1618; mã lỗi winget được giải thích bằng tiếng Việt.
- Trang **Cài máy mới**, bước 0 "Kiểm tra trước" (chỉ đọc):
  - Quyền admin, bản Windows, máy đang chờ khởi động lại, mạng (cảnh báo khi dùng Wi-Fi), Internet.
  - Từng DNS server có tìm được DC không, DC trả lời LDAP, giờ lệch so với DC (nút Đồng bộ giờ khi lệch).
  - Share, winget, dung lượng ổ hệ thống, laptop có cắm sạc.
  - Mỗi dòng kèm cách xử lý; dòng tóm tắt "sẵn sàng / nên xem / cần xử lý"; Copy kết quả.
  - Domain lấy từ máy (nếu đã join) hoặc `domain` trong site.yaml.
- Trang **Cấu hình**:
  - Nhóm "Cấu hình chuẩn" (bước 5 của wizard sẽ dùng lại): múi giờ UTC+7, tắt Fast Startup, hiện This PC trên desktop, cài .NET 3.5 (nguồn offline `<share>\Sources\sxs\<build>` nếu có, không thì Windows Update), bật System Protection và tạo restore point "sau khi cài máy".
  - Nhóm "Tuỳ chọn hay dùng" thêm: hiện file ẩn, menu chuột phải kiểu cũ (Win11), End task trên taskbar (Win11 23H2+), căn trái taskbar (Win11), Long Paths. Mỗi mục hiện trạng thái đang bật/tắt và hoàn tác được.
  - Gói "Cấu hình chuẩn máy mới": làm lần lượt, một mục lỗi vẫn làm tiếp.
- Mục **Sửa / cài lại winget** (trang Sửa lỗi, nhóm Phần mềm): đăng ký lại App Installer cho tài khoản đang chạy tool; không được thì cài từ `<share>\Installers\winget\` (có file license thì cài sẵn cho cả máy). Trang Phần mềm và bước Kiểm tra trước trỏ tới mục này khi thiếu winget.
- Gói có thêm khoá `page` (hiện ở trang nào) và `stop_on_error`. Script PowerShell có thêm biến `$ShareRoot`, `$LogDir`.
- `--selftest` chờ trang Phần mềm quét xong và báo lỗi danh mục.

### Sửa

- Hàm PowerShell dựng sẵn chỉ được thêm khi script gọi tới (trước đây thêm cả bộ khoảng 7.000 ký tự), để script dài không vượt giới hạn dòng lệnh. Có test soát độ dài mọi script.

### Bỏ

- Trang giới thiệu tạm (PlaceholderPage): không còn trang nào dùng.

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
