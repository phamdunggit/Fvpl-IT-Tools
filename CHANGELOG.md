# Nhật ký thay đổi

## Chưa phát hành: GĐ2 (Cài máy mới), GĐ3 (Tối ưu & dọn dẹp), trang Máy in

### Thêm

- **Chuyển dữ liệu máy cũ sang máy mới** (Tiện ích → tab **Chuyển máy**, `core/migrate.py`): máy cũ quét dung lượng Desktop, Documents, Downloads, Pictures (Videos, Music tuỳ chọn; đọc đúng thư mục đã đổi chỗ trong User Shell Folders, mục đồng bộ OneDrive không tick sẵn), bookmark Chrome / Edge, chữ ký Outlook; sao lưu ra `<tool>\ChuyenMay\<máy>_<người dùng>_<thời gian>\` bằng robocopy (mỗi mục một bước, có thanh tiến độ), kèm `manifest.json` ghi danh sách máy in và phần mềm. Máy mới chọn bản sao lưu, khôi phục vào hồ sơ người dùng đang đăng nhập (robocopy /XO: không ghi đè file mới hơn; bookmark cũ đổi tên giữ lại, trình duyệt đang mở thì báo đóng trước), nút **Chọn sẵn phần mềm ở trang Cài phần mềm** khớp tên phần mềm máy cũ với danh mục.
- **Báo bản mới**: lúc mở, tool đọc `version.json` trong thư mục phát hành (`release_dir` trong site.yaml, mặc định `<kho bộ cài>\ITTools`) ở thread nền; có bản mới hơn thì Trang chủ hiện dòng báo + nút mở thư mục bản mới (`core/updates.py`). Lệnh mới `packaging/deploy.py share <thư mục> --note "…"`: chép thư mục `FVPL-ITTools-v<bản>`, file zip, ghi `version.json` sau cùng.
- **Ký số exe** khi build: đặt `FVPL_SIGN_THUMBPRINT` (chứng chỉ Code Signing của AD CS hoặc mua) thì `build.py` ký SHA-256 kèm dấu thời gian và kiểm tra lại trước khi nén zip; không đặt thì bỏ qua. Hướng dẫn lấy chứng chỉ: [docs/KY-SO.md](docs/KY-SO.md).
- **Sửa biến PATH** (Tiện ích → Công cụ khác): PATH của cả máy và của người dùng, mỗi thư mục ghi Có / Không tồn tại / Trùng (mục của người dùng trùng với PATH của máy cũng tính là trùng), thêm / gỡ / đổi thứ tự, nút "Bỏ mục hỏng và trùng"; báo khi PATH của máy dài quá 2048 ký tự. Lưu bằng mục registry (REG_EXPAND_SZ, giữ cách viết %SystemRoot%…) có hoàn tác ở trang Nhật ký, xong thì báo Windows (builtin `notify_environment`).
- **Giao diện mới, đợt P3**: nút của tool ở **taskbar Windows** có thanh tiến độ (chạy qua lại khi chưa biết %, đỏ khi có mục lỗi; `core/taskbar.py`, gọi ITaskbarList3 bằng ctypes). Tool ghi thời gian chạy thật của từng mục (`durations.json`, 5 lần gần nhất) để khung tiến độ hiện **"còn khoảng N phút"** và trang Cài phần mềm hiện thời gian dự kiến. **Hướng dẫn nhanh 3 bước** lần đầu mở tool, **F1** xem lại. Phím **Ctrl+1 … Ctrl+0** mở trang trên sidebar. Ô Trang chủ tự giãn khi chữ xuống dòng (cỡ chữ 150%, cửa sổ hẹp), Tab / Enter mở được ô. Thanh trên chỉ ghi tên máy · domain (bản Windows ở tooltip). Trang Nhật ký có dòng báo khi chưa có thay đổi; màu trang Thông tin máy theo bảng màu mới. Hướng dẫn sử dụng có ảnh giao diện mới (`docs/images/`).
- **Sửa lỗi theo tình huống** (giao diện mới, đợt P2): 6 tình huống (Không vào được mạng, Không in được, Lỗi domain / ổ chung, Máy chậm / đầy ổ, Lỗi Office / Outlook, Windows Update lỗi). Màn hình 3 bước: **Kiểm tra** bằng script chỉ đọc (dấu hiệu viết bằng lời thường), **Tool sẽ làm** (mục sửa tick sẵn theo dấu hiệu, nhãn rủi ro) + **Bạn cần tự làm** (lời khuyên, nút mở đúng chỗ), **Sửa** có thanh tiến độ, tự **kiểm tra lại** và báo đã sửa được gì, còn gì; **Vẫn chưa được?** gợi ý chỗ khác. Khai báo trong `data/scenarios.yaml` (xem docs/ACTIONS.md). Ô ở Trang chủ, tìm Ctrl+K và thanh "Hướng dẫn từng bước" trên trang Sửa lỗi mở tình huống.
- Trang **Cài phần mềm dạng thẻ** (mockup 4): mỗi phần mềm một thẻ (chữ viết tắt, tên, một câu giải thích, "Tải từ Internet" / "Từ kho bộ cài" / "Đã cài"), bấm vào thẻ để chọn, thẻ đã cài hoặc không cài được bị khoá; tìm thì thẻ còn lại xếp liền nhau.
- Wizard **Cài máy mới**: thanh bước nằm ngang ở trên, **thẻ chọn bản Office** ở bước 1 (đồng bộ với "Phần mềm thêm" và mẫu), mỗi bước cuộn được khi cửa sổ thấp.
- Khoá mới `basic_name` cho mục YAML: tên dễ hiểu hiện ở chế độ Cơ bản và màn hình tình huống (đã đặt cho 17 mục, ví dụ "Reset Winsock và TCP/IP" → "Sửa lỗi mạng nặng (đặt lại Winsock, TCP/IP)"); khung chi tiết vẫn ghi tên kỹ thuật.
- Chạy xong mà cửa sổ tool đang thu nhỏ / ở sau: **thông báo ở khay hệ thống**, bấm vào để mở lại tool.
- **Gửi kết quả cho IT**: báo cáo (máy, người dùng, tình huống, đã kiểm tra / đã chạy gì, 50 dòng log cuối) chép vào clipboard để dán vào Zalo / email, lưu thêm file HTML (`core/support_report.py`).
- **Giao diện mới, đợt P1** ([kế hoạch](docs/KE-HOACH-GIAO-DIEN.md)):
  - **Khung kiểu Windows 11 sáng**: bảng màu mới (nền #F3F3F3, thẻ trắng, màu nhấn #005FB8), chữ Segoe UI Variable, icon nét mảnh vẽ bằng SVG trong code (`ui/icons.py`); thanh trên màu trắng có ô tìm, thông tin máy, nút **Cơ bản / Chuyên gia**; sidebar có icon và ô **Kho bộ cài · Đổi kho…**; **thanh trạng thái** dưới cùng (đang chạy mục n/N, %, Huỷ, kết quả lượt vừa chạy); khung log thành ngăn kéo **Chi tiết kỹ thuật (log)**.
  - **Trang chủ** (trang mở đầu): 8 ô theo việc cần làm (Cài máy mới, Cài phần mềm, Không vào được mạng, Không in được, Máy chậm / đầy ổ, Lỗi Office, Windows Update lỗi, Kiểm tra máy), khung **Tình trạng máy này** (`core/health.py`: domain / DNS, ổ C, Office, diệt virus, số ngày chưa cập nhật, số ngày chưa khởi động lại) kèm nút sửa, banner **Đang cài dở máy … · Làm tiếp**.
  - **Chế độ Cơ bản / Chuyên gia** (lưu trong `prefs.json`): Cơ bản ẩn mục Nâng cao (ghi rõ số mục đang ẩn), ẩn tab Event log / LAPS & BitLocker / Mục khác, gập khung log.
  - **Tìm chức năng Ctrl+K** (`core/search.py`, `ui/components/command_palette.py`): tìm trong trang, mục sửa lỗi, gói, công cụ, phần mềm, công cụ Windows; bỏ dấu, bỏ từ thừa, khớp mã lỗi; Enter mở đúng trang / tab và chọn sẵn mục, không tự chạy. Khoá mới `keywords` cho mục YAML (đã thêm cho 51 mục sửa lỗi / máy in).
  - Đổi tên trang: Tổng quan → **Thông tin máy**, Phần mềm → **Cài phần mềm**. Ô tìm của trang Sửa lỗi tìm cả từ khoá; gõ đúng tên nhóm thì chỉ hiện nhóm đó.
- **Giao diện mới, đợt P0** ([kế hoạch](docs/KE-HOACH-GIAO-DIEN.md)):
  - **Thanh tiến độ**: executor báo từng mục bắt đầu / xong / lỗi kèm số thứ tự (`core/progress.py`), đọc phần trăm từ output (winget "12 MB / 80 MB", DISM, robocopy, dòng `##PROGRESS` của script). Trang Phần mềm và wizard bước 3 / 5 / 6 hiện khung tiến độ: "Mục 4/8: Cài Google Chrome · Đang tải về 45%", thanh tổng, đếm Xong / Đang chạy / Chờ / Lỗi, từng mục có trạng thái và lý do lỗi, thời gian đã chạy; nút **Dừng sau mục đang chạy** (không cắt ngang bộ cài) và **Huỷ ngay**. Chạy xong có thẻ kết quả (mục lỗi và lý do, cần khởi động lại) + **Thử lại mục lỗi**. Khung log có thanh tiến độ nhỏ cho mọi lượt chạy.
  - **Chọn bản Office** bằng thẻ chọn một ở đầu trang Phần mềm (khoá mới `choice` trong `apps.yaml`). Danh mục đóng gói kèm tool có sẵn Office 2016 / 2013 / 2010 (ISO trong kho) và Microsoft 365 (winget), nên chạy bản zip không kèm kho vẫn thấy các bản, kèm lý do chưa cài được ("Cần kho bộ cài"…). Profile / mẫu wizard có bản Office thì thẻ chọn sẵn.
  - Máy có Microsoft 365 / Office **Click-to-Run** cài sẵn: chọn Office bản volume thì hiện cảnh báo và ô **Gỡ trước khi cài** (tick sẵn); lượt cài gỡ bản cài sẵn trước, Office cài sau cùng. Xung đột với Office MSI khác vẫn phải gỡ tay.
  - **Banner kho bộ cài** đầu trang Phần mềm (kho nào, bao nhiêu bộ cài có sẵn, có `config\apps.yaml` không) và nút **Chọn kho…**: chọn thư mục SOFT trên SSD / USB / mạng, nhớ cho lần sau trong `%APPDATA%\FVPL-ITTools\prefs.json`.
- Trang **Tiện ích** (GĐ4):
  - Tab **Event log**: lỗi Critical và Error của System, Application trong 24 giờ / 7 / 30 ngày, gộp theo nguồn + mã sự kiện (số lần, lần gần nhất), Critical và lỗi lặp nhiều lên đầu; gợi ý tiếng Việt cho các lỗi hay gặp (Kernel-Power 41, ổ đĩa, NTFS, NETLOGON 5719, Group Policy, dịch vụ, crash ứng dụng, DCOM vô hại…). Chỉ đọc, chạy nền.
  - Tab **Công cụ khác**: **sao lưu driver** (`pnputil /export-driver` vào `DriverBackup\<máy>-<ngày>` cạnh tool) và **cài lại driver** từ thư mục sao lưu; **sửa HOSTS** (sao lưu rồi mở bằng Notepad quyền admin); **tìm chương trình đang khoá file / thư mục** (Windows Restart Manager, không cần handle.exe), kết thúc tiến trình có hỏi lại; **mật khẩu Wi-Fi đã lưu** (xuất ra thư mục tạm, đọc rồi xoá ngay; không ghi log).
  - Mở nhanh thêm **Chẩn đoán RAM** (mdsched).
- [docs/KE-HOACH-GIAO-DIEN.md](docs/KE-HOACH-GIAO-DIEN.md): kế hoạch làm mới giao diện (trang chủ theo tình huống, chế độ Cơ bản / Chuyên gia, tìm Ctrl+K, thanh tiến độ, chọn bản Office, sửa lỗi có hướng dẫn), chờ duyệt.
- **Wizard Cài máy mới** (trang Cài máy mới, 8 bước, tiến độ lưu lại để làm tiếp sau khi khởi động lại):
  - Bước 1: chọn phòng ban, **thêm mã phòng mới** (ghi vào `departments` trong site.yaml, giữ chú thích), **gợi ý tên** `<tiền tố><mã><2 số>` theo số lớn nhất đang có trong AD (máy chưa join thì hỏi AD bằng tài khoản join), báo tên đã có (KB5020276); người dùng chính, profile phần mềm.
  - Bước 2: chép tool vào `%ProgramData%\FVPL-ITTools\app` (chỉ admin ghi được), đổi tên + join domain vào OU chung trong một lần khởi động lại, hẹn tool tự mở lại (`--resume`) khi admin đăng nhập; lỗi join kèm gợi ý theo nguyên nhân.
  - Bước 3: kiểm tra đã vào domain / đúng tên / secure channel, đồng bộ giờ, gpupdate, thêm nhóm IT (`it_admins_group`) vào Administrators.
  - Bước 4–6: mở trang Phần mềm với profile tick sẵn, gói Cấu hình chuẩn, driver của hãng + Windows Update; kết quả tự ghi vào bước.
  - Bước 7: báo cáo HTML (các bước, hệ điều hành, phần cứng + serial, phần mềm như Programs and Features), lưu trên máy và `Reports\` cạnh tool trên ổ mang theo; Kết thúc thì bỏ hẹn mở lại.
  - Sau khởi động lại, trang Phần mềm vẫn dùng được kho SOFT trên SSD nếu ổ còn cắm đúng chỗ.
  - **Mẫu**: lưu phòng ban, profile và phần mềm thêm ngoài profile (ví dụ Office 2016) thành mẫu như "Kế toán – Laptop" (`wizard-templates.json` cạnh site.yaml); chọn mẫu là điền sẵn bước 1, bước 4 tick sẵn cả phần mềm thêm. Báo cáo ghi mẫu và phần mềm thêm đã dùng.
- Tab **Khởi động cùng Windows** có thêm task trong Task Scheduler chạy lúc đăng nhập / bật máy (đọc nền qua COM, khoảng 1 giây; bỏ task của Windows trong thư mục `\Microsoft`), bật / tắt được như mục khác.
- Mục tối ưu: **Hiệu ứng hình ảnh ưu tiên hiệu năng** (máy yếu, theo người dùng), **Chuyển dịch vụ cập nhật của Edge, Chrome, Adobe, bản đồ sang Manual** (Nâng cao, hoàn tác về mặc định), **Chặn app "đồng hành" do driver tự cài** (policy PreventDeviceMetadataFromNetwork).
- **Office bản volume:** khoá `conflicts` trong `apps.yaml` (máy có Microsoft 365 / Office khác thì không cài, báo lý do và cách gỡ); mục **Gỡ Microsoft 365 / Office cài sẵn (Click-to-Run)** (gỡ im lặng, chờ tới khi xong); mục **Kích hoạt Office bản volume (MAK) và xem trạng thái** (ospp.vbs /act, trạng thái cả Office 2010). Trang Tổng quan đọc thêm kích hoạt của Office 2010.
- Tài liệu [docs/HUONG-DAN-SU-DUNG.md](docs/HUONG-DAN-SU-DUNG.md): chuẩn bị kho bộ cài (key MAK, SyLink.xml), wizard, **cài Office và Symantec từng bước**, các trang, khi có lỗi. README có danh sách chức năng chính.
- Trang Tiện ích, tab **LAPS & BitLocker**: gõ tên máy để xem mật khẩu Windows LAPS (giải mã được mật khẩu đã mã hoá), bắt đổi mật khẩu, xem khoá khôi phục BitLocker trong AD (đọc LDAP, không cần RSAT). Có thể dùng tài khoản khác. Kết quả không vào khung log / file log, tự xoá sau 2 phút, clipboard tự xoá sau 60 giây; log chỉ ghi ai tra máy nào.
- Mục **Kiểm tra Windows LAPS** (chính sách, chạy xử lý ngay, đọc nhật ký LAPS), **Bật BitLocker ổ hệ thống** (chỉ khi TPM sẵn sàng và đã có GPO lưu khoá lên AD; sao lưu khoá trước khi bật; hoàn tác là giải mã), **Tạm dừng BitLocker cho một lần khởi động lại**.
- Tài liệu [docs/BITLOCKER-LAPS-GPO.md](docs/BITLOCKER-LAPS-GPO.md): triển khai GPO (Central Store, thử trên nhóm máy), Windows LAPS (schema, quyền, GPO, tra mật khẩu), BitLocker (GPO lưu khoá lên AD, bật từng máy, tra khoá), các GPO nên có và lộ trình.
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
