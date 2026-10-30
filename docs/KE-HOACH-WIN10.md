# Kế hoạch: chạy ổn trên Windows 10

Người dùng báo: mở tool trên Win10 thì "lỗi tùm lum". Kế hoạch này gom việc cần làm để Win10 22H2 chạy ngang Win11.

## 1. Hiện trạng (rà code ngày 30/10/2026)

- Tool mới chạy thật trên **Win11 25H2** (máy dev). Win10 có trong phạm vi hỗ trợ (PLAN.md: "Win10 22H2 + Win11")
  nhưng **chưa chạy thử lần nào**, kể cả bản exe (HANDOFF.md, mục "Chưa kiểm chứng").
- Phần đã tính tới Win10, không cần làm lại:
  - Giao diện: font `Segoe UI Variable` (chỉ có trên Win11) đã có dự phòng `Segoe UI`; style Fusion + bảng màu sáng cố định,
    không theo chế độ tối của Windows; icon vẽ bằng SVG, không dùng font icon `Segoe Fluent Icons` của Win11.
  - Tên Windows: Win11 vẫn ghi "Windows 10" trong registry, `core/sysinfo.py` sửa theo build.
  - Các mục chỉ dành cho Win11 đã khai báo `os: { min_build: ... }` (menu chuột phải kiểu cũ, căn trái taskbar,
    End task, Named Pipes máy in).
  - PowerShell gọi Windows PowerShell 5.1, giống nhau trên Win10 và Win11.
- **Rủi ro lớn nhất tìm thấy:** Qt 6.12 (PySide6 6.12.0, bản đang cài) là **bản cuối cùng hỗ trợ Win10**
  (doc.qt.io/qt-6/windows.html). `pyproject.toml` chỉ ghi `PySide6>=6.7`, nên lần cài / build sau mà ra bản 6.13 thì
  exe sẽ không chạy được trên Win10. Qt 6.12 cũng chỉ nhận Win10 **1809 trở lên**.

## 2. Nghi vấn cần kiểm (chưa có thông báo lỗi cụ thể)

| # | Nghi vấn | Vì sao Win10 khác Win11 |
|---|---|---|
| A | winget không có hoặc quá cũ | Win10 cài mới, LTSC 2019/2021 không có Store, App Installer thường cũ hoặc chưa đăng ký. Trang Phần mềm, Cài máy mới, mục cập nhật app phụ thuộc winget |
| B | Cmdlet không có trên một số bản Win10 | `Get-LapsADPassword` / `Invoke-LapsPolicyProcessing` cần bản cập nhật 04/2023; `Get-BitLockerVolume` không có trên bản Home; `Get-AppxProvisionedPackage` cần quyền admin |
| C | Bản Win10 cũ hơn 22H2 | Khoá `DisplayVersion` chỉ có từ 20H2; build < 17763 thì Qt không chạy |
| D | Symantec (SEP) chặn PowerShell / exe chưa ký | Máy Win10 trong công ty thường là máy cũ, chính sách SEP cũ hơn (xem docs/KY-SO.md) |
| E | Trang Tổng quan / Kiểm kê đọc thiếu thông tin | Một số lớp WMI / thuộc tính khác nhau giữa các bản build (TPM, ổ đĩa, Secure Boot) |
| F | Giao diện hiển thị lệch | Win10 hay đặt scale 125% / 150%, font render khác, không bo góc cửa sổ |
| G | Mục Win11 lọt sang Win10 | Mục nói tới Win11 mà quên khai báo `os:`; gói sửa nhanh (`packs.yaml`) chứa mục không hợp Win10 |

## 3. Các bước

### Bước 0: Gom lỗi thật (làm trước, ước 0,5 ngày)
- Trên máy Win10 bị lỗi, lấy:
  - Log phiên: `%ProgramData%\FVPL-ITTools\logs\` (file mới nhất).
  - Chạy `FVPL-ITTools.exe --selftest C:\Temp\selftest` rồi gửi `selftest.json` + ảnh các trang
    (ảnh có tên máy thật: không commit).
  - Chụp màn hình lỗi, ghi bản Windows: `winver` (ví dụ 22H2 build 19045.xxxx), bản Home / Pro / LTSC.
- Ghi từng lỗi vào bảng ở mục 5, gắn với nghi vấn A–G hoặc thêm nghi vấn mới.

### Bước 1: Khoá phiên bản Qt (ước 0,5 giờ)
- `pyproject.toml`: `PySide6>=6.7,<6.13`. Ghi lý do ngay cạnh dòng đó.
- Thêm test: phiên bản PySide6 đang cài < 6.13 (để bản build không lặng lẽ bỏ Win10).
- `__main__.py`: build < 17763 thì báo bằng hộp thoại Windows (ctypes `MessageBoxW`, không cần Qt) rồi thoát,
  thay vì crash không rõ lý do.

### Bước 2: Máy ảo Win10 để thử (ước 0,5 ngày)
- VM Hyper-V Win10 22H2 sạch (bản Pro), có snapshot; thêm một VM LTSC 2021 nếu công ty còn dùng.
- Chạy bản exe phát hành và bản `--test`, lần lượt từng trang. Ghi lỗi vào mục 5.

### Bước 3: Sửa theo nhóm lỗi (ước 2–3 ngày, tuỳ Bước 0 và 2)
- **winget (A):** khi không có winget, các trang hiện thông báo rõ kèm nút "Cài lại winget" (`sw.repair_winget`,
  nguồn từ `Installers\winget\` trên share / SOFT), không báo lỗi thô. Cài phần mềm từ share / SOFT vẫn chạy được
  khi không có winget.
- **Cmdlet thiếu (B):** script kiểm `Get-Command` trước khi gọi; thiếu thì ghi lý do bằng tiếng Việt
  ("Bản Windows này chưa có Windows LAPS: cập nhật Windows…") thay vì lỗi đỏ. Mục cần BitLocker thì khoá trên bản Home.
- **Bản cũ (C):** đọc `ReleaseId` khi không có `DisplayVersion`; Trang chủ cảnh báo máy cũ hơn 22H2.
- **Symantec (D):** đối chiếu với cách xử lý trong docs/KY-SO.md; nếu cần thì ký số bản phát hành.
- **Tổng quan / Kiểm kê (E):** mỗi thông tin đọc lỗi thì hiện "Không đọc được" thay vì làm hỏng cả trang.
- **Giao diện (F):** thử ở 100 / 125 / 150%; sửa chỗ chữ bị cắt, nút lệch.
- **Mục Win11 (G):** rà lại toàn bộ `data/actions/*.yaml`, `packs.yaml`, `scenarios.yaml`; thêm `os:` cho mục còn thiếu.
  Thêm test: mục nào trong tên / mô tả có "Win11" mà không có `os.min_build` thì báo lỗi (trừ mục nói về cả hai).

### Bước 4: Kiểm và chốt (ước 0,5 ngày)
- Chạy lại toàn bộ trên VM Win10 và Win11, đánh dấu từng dòng ở mục 5.
- `pytest` đủ test, build bản mới, cập nhật CHANGELOG, HANDOFF (mục "Chưa kiểm chứng") và TIEN-DO.

## 4. Không làm trong đợt này
- Hỗ trợ Win10 cũ hơn 1809 (Qt không chạy được).
- Giữ hỗ trợ Win10 khi lên Qt 6.13+: nếu sau này cần Qt mới, phải tách hai bản build. Quyết định lúc đó.

## 5. Bảng theo dõi lỗi trên Win10

| # | Trang / mục | Lỗi thấy | Bản Win10 | Nghi vấn | Đã sửa |
|---|---|---|---|---|---|
| 1 | | | | | |
