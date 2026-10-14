# Kế hoạch làm mới giao diện

Lập: 14/10/2026. Trạng thái: **chờ duyệt**. Đã có mockup 6 màn hình (canvas trên claude.ai, gửi riêng cho bồ, chưa share). Chưa sửa code giao diện.

## 1. Vì sao làm

Phản hồi sau khi chạy thử bản phát hành:

| Vấn đề | Nguyên nhân trong code hiện tại |
|---|---|
| Giao diện chưa hiện đại, khó dùng | Trang nào cũng là danh sách mục kỹ thuật + khung log đen ở dưới. Sidebar chỉ có chữ. Không có màn hình "bắt đầu từ đâu". |
| Không thấy chỗ chọn bản Office | Bản phát hành không kèm kho `SOFT`, nên tool dùng danh mục có sẵn: chỉ có một mục "Microsoft Office" chung. Tool không báo là đang thiếu kho bộ cài. Office 2016 / 2013 / 2010 chỉ hiện khi có `SOFT\config\apps.yaml`. |
| Khó tìm chức năng | Hơn 100 mục nằm ở 9 trang, nhiều trang có tab. Ô tìm chỉ lọc trong trang đang mở. |
| Không biết đang chạy tới đâu | Executor chỉ đẩy dòng log. Cài 8 phần mềm thì chỉ thấy chữ chạy, không biết đang ở mục mấy, còn bao lâu. |
| Người không chuyên khó dùng | Tên mục là tên kỹ thuật (Winsock, Spooler, RPC). Kết quả nằm trong log. Không có hướng dẫn "làm gì tiếp". |

## 2. Đã chốt

- **Người dùng chính:** IT mới và người hỗ trợ (biết dùng máy, chưa rành lệnh). Có hai chế độ: **Cơ bản** (mặc định) và **Chuyên gia** (giống giao diện hiện tại, đủ mọi mục).
- **Phong cách:** trang chủ là các ô lớn theo tình huống ("Không in được", "Cài phần mềm"…). Các trang bên trong theo kiểu Windows 11 Settings: thẻ (card) trắng trên nền xám nhạt, icon nét mảnh, màu nhấn xanh Windows.
- **Chỉ giao diện sáng.** Giao diện tối vẫn để sau.
- **Xem mockup trước rồi mới code.**

## 3. Nguyên tắc

1. **Nói việc, không nói lệnh.** "Xoá lệnh in bị kẹt", không phải "Clear spooler queue". Tên lệnh, mã lỗi để trong phần "Chi tiết kỹ thuật".
2. **Một màn hình, một nút chính** (màu xanh). Các nút khác là nút phụ.
3. **Luôn thấy đang ở đâu và còn bao lâu:** bước mấy / tổng mấy, mục mấy / tổng mấy, phần trăm, thời gian đã chạy.
4. **An toàn là mặc định.** Chế độ Cơ bản chỉ tự chọn mục "An toàn" và "Có hoàn tác". Mục "Nâng cao" chỉ hiện ở chế độ Chuyên gia.
5. **Chạy xong phải nói rõ kết quả và bước tiếp theo:** đã sửa / chưa sửa được, thử gì tiếp, hoàn tác ở đâu, gửi kết quả cho IT.
6. **Chi tiết kỹ thuật lúc nào cũng có, nhưng gập lại.** Chế độ Chuyên gia thì mở sẵn.

## 4. Mockup (6 màn hình)

| # | Màn hình | Thể hiện |
|---|---|---|
| 1 | Trang chủ | Banner "đang cài dở máy… Làm tiếp"; 8 ô tình huống; khung "Tình trạng máy này" có nút sửa ngay (đầy ổ, lâu chưa cập nhật). Header có ô tìm, trạng thái máy, nút Cơ bản / Chuyên gia; góc dưới sidebar cho biết đang dùng kho bộ cài nào. |
| 2 | Tìm chức năng (Ctrl+K) | Gõ "máy in không in được" (gõ không dấu, gõ mã lỗi 0x0000011b cũng được), ra tình huống + mục sửa + công cụ, mỗi dòng có câu giải thích và nút Chạy / Mở. |
| 3 | Sửa lỗi có hướng dẫn | Tình huống "Không in được": Kiểm tra → Sửa → Kết quả. Kết quả kiểm tra viết bằng lời thường; danh sách việc tool sẽ làm kèm nhãn An toàn / Có hoàn tác; nút "Sửa giúp tôi"; thanh tiến độ; màn hình kết quả có "In trang thử", "Vẫn chưa in được", "Gửi kết quả cho IT". |
| 4 | Cài phần mềm | Banner kho bộ cài (có / chưa có + "Chọn kho…"); **thẻ chọn bản Office** (Không cài / 2016 / 2013 / 2010 / Microsoft 365), báo máy đang có Microsoft 365 và tick "Gỡ trước khi cài"; chọn nhanh theo phòng ban; lưới thẻ phần mềm (đã cài, cần kho, tải từ Internet); thanh dưới "Đã chọn 7 mục · khoảng 25 phút · Cài 7 mục". |
| 5 | Đang cài | Thanh tổng (mục 4/8, %, đã chạy, còn khoảng); đếm Xong / Đang cài / Chờ / Lỗi; từng mục có trạng thái, mục đang cài có thanh % riêng ("Đang tải về…", "Đang cài đặt…"); mục lỗi có lý do dễ hiểu + "Thử lại"; log gập lại; thanh trạng thái dưới cùng có thanh tiến độ nhỏ. |
| 6 | Cài máy mới | Thanh 7 bước; chọn mẫu (Kế toán, Hành chính, Máy yếu…); form "Máy này của ai?" (phòng ban, tên máy kiểm tra trùng ngay, người dùng); "Cài những gì?" (bản Office, phần mềm theo phòng, làm thêm); ước tính thời gian và số lần khởi động lại. |

## 5. Thiết kế chi tiết

### 5.1 Hệ thống giao diện

| Thành phần | Giá trị |
|---|---|
| Màu nền / thẻ / viền | `#F3F3F3` / `#FFFFFF` / `#E5E5E5` |
| Chữ chính / chữ phụ | `#1B1B1B` / `#5C5C5C` |
| Màu nhấn (nút chính, mục đang chọn) | `#005FB8`, nền nhạt `#E8F1FB` |
| Trạng thái | Ổn `#0E700E` (nền `#DFF6DD`), Cảnh báo `#8A5300` (nền `#FFF4CE`), Lỗi `#C42B1C` (nền `#FDE7E9`) |
| Chữ | Segoe UI Variable, dự phòng Segoe UI. Tiêu đề trang 20pt, tiêu đề thẻ 12pt, chữ thường 10pt |
| Khoảng cách, bo góc | Bội số của 4 px (4 / 8 / 12 / 16 / 24 / 32); thẻ bo 8 px, nút bo 6 px; nút cao tối thiểu 32 px |
| Icon | [Fluent UI System Icons](https://github.com/microsoft/fluentui-system-icons) (MIT, cùng bộ với Windows 11), file SVG chép vào `data/icons/`, đổi màu khi vẽ |

Không dùng thư viện PySide6-Fluent-Widgets: bản miễn phí là GPLv3, khá nặng và khó ghép với stylesheet hiện có. Mình tự viết stylesheet và một bộ thành phần nhỏ trong `ui/components/`:

`NavBar` (sidebar có icon) · `PageHeader` (đường dẫn, tiêu đề, mô tả) · `Card` · `Tile` (ô lớn trang chủ) · `StatusRow` (icon trạng thái + chữ + nút) · `Badge` (An toàn / Có hoàn tác / Nâng cao) · `Banner` (thông tin / cảnh báo / lỗi + nút) · `Stepper` · `SegmentedButton` · `ChoiceCard` (thẻ chọn một, dùng cho Office) · `AppCard` · `ProgressPanel` · `ResultCard` · `TechDetails` (phần gập "Chi tiết kỹ thuật") · `CommandPalette`.

Truy cập bằng bàn phím: Tab đi qua mọi nút, có viền focus rõ, `setAccessibleName` cho nút chỉ có icon, chạy đúng khi Windows đặt cỡ chữ 125–150%.

### 5.2 Bố cục chung

- **Header:** logo + tên app; ô tìm (bấm vào hoặc Ctrl+K mở bảng tìm); thông tin máy dạng nhãn tròn (tên máy · domain · Windows), "Quyền admin ✓" hoặc cảnh báo đỏ; nút Cơ bản / Chuyên gia.
- **Sidebar có icon:** Trang chủ, Cài máy mới, Cài phần mềm, Sửa lỗi, Máy in, Tối ưu & dọn dẹp, Cấu hình, Tiện ích, Nhật ký. Nội dung trang Tổng quan hiện tại chuyển thành khung "Tình trạng máy" ở Trang chủ, bản đầy đủ là trang "Thông tin máy" (mở từ ô "Kiểm tra máy"). Góc dưới sidebar: kho bộ cài đang dùng + "Đổi kho…".
- **Thanh trạng thái** thay cho khung log luôn mở: "Sẵn sàng" / "Đang cài 4/8 · Google Chrome 64%" + thanh nhỏ + "Chi tiết kỹ thuật (log)". Khung log hiện tại thành ngăn kéo mở từ thanh này. Chế độ Chuyên gia mở sẵn ngăn kéo.

### 5.3 Trang chủ

- Banner "đang cài dở máy X · bước n/7 · Làm tiếp" khi có `newpc-wizard.json` chưa xong.
- Ô tình huống: Cài máy mới (ô màu nhấn), Cài phần mềm, Không vào được mạng, Không in được, Máy chậm / đầy ổ, Lỗi Office / Outlook, Windows Update lỗi, Kiểm tra máy. Danh sách ô lấy từ `scenarios.yaml` (mục 5.8), thêm ô không cần sửa code.
- "Tình trạng máy này": domain, ổ C còn trống, số ngày chưa cập nhật Windows, diệt virus, Office đã kích hoạt chưa, có cần khởi động lại không. Dòng nào có vấn đề thì kèm một nút sửa. Dữ liệu lấy từ các hàm trang Tổng quan đang dùng, chạy nền.

### 5.4 Tìm chức năng (Ctrl+K)

- **Chỉ mục** dựng một lần khi mở app, từ: action YAML (tên, mô tả, `keywords`), gói sửa nhanh, tình huống, phần mềm trong danh mục, các trang và tab (khai báo trong code).
- **So khớp:** bỏ dấu tiếng Việt (`unicodedata` NFD, `đ` → `d`), chữ thường, bỏ từ vô nghĩa ("không", "được", "bị", "lỗi"…). Điểm = số từ khớp, ưu tiên khớp tên, ưu tiên tình huống. Mã lỗi (0x…) khớp nguyên văn.
- **Kết quả** gom theo nhóm: Tình huống · Sửa lỗi · Phần mềm · Công cụ · Trang. Mỗi dòng có tên, câu giải thích, nằm ở trang nào, nút Chạy / Mở / Bắt đầu. Enter chạy dòng đầu; Chạy vẫn hỏi xác nhận như bấm từ trang.
- Chế độ Cơ bản ẩn các mục "Nâng cao" khỏi kết quả, cuối danh sách ghi "Có thêm N mục nâng cao (chế độ Chuyên gia)".
- YAML thêm trường `keywords:` (từ đồng nghĩa, cách người dùng hay gọi, mã lỗi). Có test bắt buộc mọi mục P1 phải có `keywords`.

### 5.5 Chế độ Cơ bản và Chuyên gia

| | Cơ bản (mặc định) | Chuyên gia |
|---|---|---|
| Trang mở đầu | Trang chủ (ô tình huống) | Trang chủ, nhớ trang mở lần trước |
| Sửa lỗi | Đi theo tình huống; danh sách mục chỉ có An toàn và Có hoàn tác | Đủ mọi mục, chọn nhiều, gói sửa nhanh, xem trước lệnh |
| Tên mục | Tên dễ hiểu (`basic_name` nếu có) | Tên hiện tại |
| Log | Gập, chỉ hiện thanh trạng thái | Mở sẵn |
| Tiện ích | Mở nhanh, Wi-Fi, kiểm kê | Đủ tab (Event log, file bị khoá, LAPS & BitLocker…) |
| Xác nhận | Hộp xác nhận viết bằng lời thường, ghi rõ hoàn tác được không | Như hiện tại |

Chế độ lưu trong `%APPDATA%\FVPL-ITTools\prefs.json` (theo người dùng Windows, không lên git). Đổi chế độ không cần mở lại app.

### 5.6 Thanh tiến độ

**Dữ liệu.** Thêm sự kiện `ProgressEvent(batch_id, index, total, action_id, title, state, percent, phase)` bên cạnh `LogEvent`. `state` là start / progress / done / failed / skipped / cancelled; `percent` là `None` khi không biết.

- `executor._run_batch` phát `start` / `done` / `failed` quanh mỗi mục, kèm số thứ tự và tổng. Việc này cho ngay "mục 4/8" cho mọi lượt chạy: phần mềm, gói sửa nhanh, wizard, cấu hình chuẩn.
- **Phần trăm từng mục** (`core/progress.py`) lấy từ output đang đọc từng dòng:
  - winget: "45.2 MB / 112 MB" → 40%; dòng có "NN%".
  - DISM / SFC: "[====  23.4% ===]".
  - robocopy: dòng "NN%".
  - Script của mình: in dòng `##PROGRESS 45 Đang tải về` qua helper `Report-Progress` trong `pslib` (dùng cho Windows Update, sao lưu driver, dọn rác).
  - Không đọc được phần trăm (MSI, EXE cài im lặng): thanh chạy qua lại kèm "Đang cài… có thể mất vài phút" và thời gian đã chạy.
- **Ước tính thời gian còn lại:** lưu thời gian cài thật của mỗi phần mềm vào `%ProgramData%\FVPL-ITTools\durations.json`; lần sau lấy trung bình. Chưa có số liệu thì dùng `minutes:` trong `apps.yaml`, không có nữa thì không hiện "còn khoảng".

**Giao diện.** `ProgressPanel` dùng chung cho trang Phần mềm, Sửa lỗi, Cấu hình và wizard bước 4–6:

- Thanh tổng = (số mục xong + % mục đang chạy) / tổng; dòng "Mục 4/8: Google Chrome · 52% · đã chạy 6:52 · còn khoảng 7 phút".
- Đếm Xong / Đang cài / Chờ / Lỗi.
- Danh sách từng mục: icon trạng thái; mục đang chạy có thanh riêng; mục lỗi có lý do dễ hiểu (dùng bảng mã lỗi winget / MSI sẵn có, viết lại cho dễ hiểu) + "Thử lại".
- Nút "Dừng sau mục đang cài" (không giết bộ cài đang chạy dở) và "Huỷ ngay" (chỉ ở chế độ Chuyên gia).
- Thanh trạng thái dưới cùng luôn thấy tiến độ, kể cả khi chuyển sang trang khác.
- Chạy xong: `ResultCard` (mục 5.9), thông báo ở khay hệ thống nếu cửa sổ đang thu nhỏ.

### 5.7 Cài phần mềm, chọn bản Office, kho bộ cài

- **Kho bộ cài thấy được:** banner đầu trang "Kho bộ cài: Ổ SSD F:\…\SOFT · 24 bộ cài" hoặc "Chưa tìm thấy kho bộ cài" + nút **Chọn kho…** (chọn thư mục; tool kiểm tra có `config\apps.yaml` và các bộ cài; nhớ lựa chọn trong `prefs.json`). Mục nào cần kho mà chưa có kho thì vẫn hiện nhưng mờ, ghi "Cần kho bộ cài", không bị ẩn mất.
- **Thẻ chọn bản Office:** danh mục thêm khoá `choice: office`. Mọi app có cùng `choice` được vẽ thành một nhóm chọn một (thẻ radio) thay vì checkbox. Danh mục có sẵn trong tool khai báo sẵn Office 2016 / 2013 / 2010 (cài từ ISO trong kho, đường dẫn tương đối, không có key) và Microsoft 365 (Office Deployment Tool hoặc winget). Key MAK vẫn chỉ nằm trong kho.
- **Xung đột:** chọn Office MSI mà máy có Microsoft 365 cài sẵn thì hiện cảnh báo, tick sẵn "Gỡ trước khi cài". Tool tự thêm mục `off.remove_c2r` vào đầu lượt cài và `off.activate_volume` sau khi cài.
- **Thẻ phần mềm** thay cho bảng: tên, một câu giải thích, nguồn (kho / Internet), trạng thái (đã cài, cần kho, bị chặn và lý do).
- Chọn nhanh theo phòng ban (profile) dạng nút tròn; sửa tay thì nút chuyển sang "Tự chọn".
- Thanh dưới cố định: "Đã chọn N mục (có Office 2016) · khoảng X phút · Cài N mục".

### 5.8 Sửa lỗi theo tình huống

File mới `data/scenarios.yaml`, mỗi tình huống gồm:

```yaml
- id: printing
  title: Không in được
  tile: Kẹt lệnh in, máy in báo lỗi, máy in share Win11 ↔ Win10
  icon: print
  keywords: [máy in, in, printer, spooler, 0x0000011b, 0x00000709]
  check: [prn.list, prn.share_check]     # mục chỉ đọc
  findings:                              # dấu hiệu trong kết quả kiểm tra → câu dễ hiểu + mục sửa
    queue_stuck: { text: "Có {n} lệnh in bị kẹt", fix: [prn.clear_queue] }
    spooler_down: { text: "Dịch vụ in của Windows đang tắt", fix: [prn.restart_spooler] }
    share_rpc: { text: "Windows 11 chặn cách kết nối máy in share kiểu cũ", fix: [prn.share_client_fix] }
  verify: [prn.share_check]
  not_fixed: [page:printers, send_to_it]
```

- Script kiểm tra in thêm một dòng JSON `##FINDINGS [...]` để tool biết dấu hiệu nào xuất hiện. Phần còn lại vẫn là log như cũ.
- Luồng: **Kiểm tra** (chỉ đọc) → **Đề xuất** (danh sách việc sẽ làm có nhãn, bỏ tick được) → **Sửa** (`ProgressPanel`) → **Kiểm tra lại** → **Kết quả**.
- Tình huống đợt đầu (dùng lại mục sẵn có): Không in được, Không vào được mạng, Không vào được ổ chung, Mất kết nối domain (trust), Máy chậm / đầy ổ, Lỗi Office / Outlook, Windows Update lỗi.
- Test: mọi `check` / `fix` / `verify` trong `scenarios.yaml` phải là id có thật; mục chạy trong chế độ Cơ bản không được là "Nâng cao".

### 5.9 Màn hình kết quả và "Gửi cho IT"

- `ResultCard` sau mọi lượt chạy: icon to (ổn / còn lỗi), một câu tóm tắt, danh sách mục lỗi kèm việc nên làm, cần khởi động lại hay không, nút Hoàn tác (nếu có), "Thử lại mục lỗi".
- **Gửi cho IT:** tạo báo cáo ngắn (máy, người dùng, tình huống, đã thử gì, kết quả, 50 dòng log cuối đã che mật khẩu). Chép vào clipboard để dán vào Zalo / email và lưu file HTML vào `Reports\`. Tool không tự gửi đi đâu.

### 5.10 Cài máy mới

Giữ nguyên logic wizard hiện tại, chỉ làm lại phần hiển thị như mockup 6: thanh bước ở trên, chọn mẫu bằng thẻ, form chia hai thẻ "Máy này của ai?" và "Cài những gì?" (có thẻ chọn Office), kiểm tra tên máy ngay khi gõ, ước tính thời gian + số lần khởi động lại. Bước 4–6 dùng `ProgressPanel`. Bước 7 dùng `ResultCard` + nút mở báo cáo.

### 5.11 Viết cho người không chuyên

- Tên mục bắt đầu bằng động từ, nói kết quả: "Xoá lệnh in bị kẹt", "Cho phép máy này dùng máy in share của Windows 10".
- Mô tả trả lời hai câu: **dùng khi nào** và **sau khi chạy có gì thay đổi**.
- Báo lỗi theo mẫu: chuyện gì xảy ra + làm gì tiếp. Ví dụ: "Không tải được bộ cài. Mạng chập chờn hoặc trang tải đang lỗi. Bấm Thử lại khi mạng ổn." Mã lỗi để trong chi tiết kỹ thuật.
- YAML thêm `basic_name` (tên dễ hiểu, không bắt buộc) và `keywords`. Rà lại toàn bộ mô tả các mục P1 theo quy tắc này.

## 6. Thay đổi trong code

| Phần | File |
|---|---|
| Màu, chữ, stylesheet | `ui/theme.py` (viết lại theo bảng 5.1) |
| Icon | `data/icons/*.svg`, `ui/icons.py` (nạp SVG, đổi màu, cache) |
| Thành phần giao diện | `ui/components/` (mục 5.1); `ui/widgets.py` giữ `Worker` |
| Khung cửa sổ | `ui/main_window.py`: header mới, `NavBar`, thanh trạng thái, ngăn kéo log |
| Trang chủ | `ui/pages/home.py` (mới), `ui/pages/overview.py` thành trang Thông tin máy |
| Tìm kiếm | `core/search.py` (chỉ mục, bỏ dấu, chấm điểm; không phụ thuộc Qt), `ui/components/command_palette.py` |
| Chế độ | `core/prefs.py` (`prefs.json`: chế độ, kho bộ cài đã chọn), lọc trong `actions_page.py`, `utilities.py` |
| Tiến độ | `core/progress.py` (đọc %), `executor.py` (`ProgressEvent`), `ui/controller.py` (signal `progress`), `pslib` (`Report-Progress`), `ui/components/progress_panel.py` |
| Office, kho | `software/catalog.py` (`choice`, `minutes`), `data/apps.yaml` (Office 2016 / 2013 / 2010 / 365), `ui/pages/software.py` |
| Tình huống | `data/scenarios.yaml`, `scenarios/model.py`, `ui/pages/scenario.py` |
| Kết quả, gửi IT | `ui/components/result_card.py`, `core/support_report.py` |
| Tài liệu | `docs/HUONG-DAN-SU-DUNG.md` (ảnh chụp mới), `docs/ACTIONS.md` (`keywords`, `basic_name`), `docs/SOFTWARE.md` (`choice`, `minutes`) |

## 7. Lộ trình

| Đợt | Nội dung | Xong khi |
|---|---|---|
| **P0** · giải quyết ngay phần bồ thấy thiếu | `ProgressEvent` + `ProgressPanel` cho trang Phần mềm và wizard; thẻ chọn bản Office + `choice` trong danh mục; banner kho bộ cài + "Chọn kho…"; `ResultCard` sau khi cài | Cài 8 phần mềm thấy "mục n/8", % từng mục (winget), mục lỗi có lý do; chạy bản phát hành không có `SOFT` vẫn thấy Office 2016 / 2013 / 2010 (mờ, "Cần kho bộ cài"), chọn kho xong thì cài được |
| **P1** · bộ khung mới | Theme + icon + thành phần; header, `NavBar`, thanh trạng thái, ngăn kéo log; Trang chủ (ô + tình trạng máy); chế độ Cơ bản / Chuyên gia; tìm Ctrl+K + `keywords` cho mọi mục P1 | Giao diện giống mockup 1, 2; tìm "may in" ra đủ mục máy in; chế độ Cơ bản không hiện mục Nâng cao |
| **P2** · dễ dùng cho người không chuyên | `scenarios.yaml` + 7 tình huống; làm lại trang Phần mềm (thẻ) và wizard theo mockup; `basic_name`, viết lại mô tả; "Gửi cho IT"; thông báo khay hệ thống | Một người không làm IT tự làm được "Không in được" và "Cài phần mềm" không cần hỏi (thử với 2–3 người) |
| **P3** · hoàn thiện | Làm lại các trang còn lại (Máy in, Tối ưu, Cấu hình, Tiện ích, Nhật ký); tiến độ trên taskbar Windows (`ITaskbarList3`); ước tính thời gian từ số liệu thật; lần đầu mở app có hướng dẫn nhanh 3 bước; rà bàn phím, cỡ chữ 150% | Mọi trang theo bộ khung mới; ảnh chụp trong hướng dẫn sử dụng là giao diện mới |

Mỗi đợt là một hoặc vài commit trên nhánh `featured`, test chạy xanh trước khi commit, kèm bản build để bồ thử.

## 8. Kiểm thử

- `core/search.py`: bỏ dấu, từ vô nghĩa, mã lỗi, thứ tự kết quả (test thuần Python).
- `core/progress.py`: output thật của winget, DISM, robocopy, `##PROGRESS` (lưu mẫu trong `tests/data/`).
- Executor phát đúng chuỗi `ProgressEvent` cho lượt chạy có mục lỗi, bỏ qua, huỷ.
- `scenarios.yaml`, `apps.yaml` (`choice`), `keywords`: test kiểm tra dữ liệu như các test YAML hiện có.
- Giao diện: pytest-qt cho `ProgressPanel`, `CommandPalette`, `ChoiceCard`, chuyển chế độ; test cửa sổ chính hiện có vẫn phải chạy.
- Thử tay trên máy ảo Win10 / Win11 với cỡ chữ 100% và 150%.

## 9. Rủi ro

| Rủi ro | Cách xử lý |
|---|---|
| winget đổi định dạng thanh tiến độ | Không đọc được thì chuyển sang thanh chạy qua lại, tiến độ tổng vẫn đúng theo số mục |
| Làm lại giao diện làm hỏng chức năng đang chạy tốt | Giữ nguyên tầng `core`, `actions`, `software`, `newpc`; chỉ thay tầng `ui`. Mỗi trang làm lại xong mới bỏ trang cũ. Test giao diện hiện có giữ nguyên |
| Chế độ Cơ bản giấu mất mục IT cần | Tìm kiếm luôn báo "có thêm N mục nâng cao"; chuyển chế độ một cú bấm |
| Exe nặng hơn vì icon, QtSvg | Chỉ chép icon dùng tới (khoảng 60 file SVG, dưới 200 KB); QtSvg đã có trong PySide6 |

## 10. Không làm

| Không làm | Lý do |
|---|---|
| Giao diện tối | Đã chốt chỉ giao diện sáng; để sau |
| Đổi sang web UI (Electron, Tauri) | Phải viết lại toàn bộ, exe nặng hơn nhiều; PySide6 làm được giao diện như mockup |
| Hiệu ứng Mica / acrylic của Windows 11 | Không chạy trên Win10, ít lợi ích |
| Tự gửi báo cáo qua email / Zalo | Cần lưu tài khoản gửi; chép vào clipboard là đủ |
