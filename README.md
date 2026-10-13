# FVPL IT Toolkit

Công cụ cho IT: cài máy mới, join domain, sửa lỗi thường gặp, tối ưu Windows.
Viết bằng Python 3.13 + PySide6, đóng gói thành exe chạy portable từ USB hoặc share.

- Trạng thái: **GĐ1 (Tổng quan + Sửa lỗi) xong phần code, phiên bản 0.2.0.** Trang Tổng quan, 24 mục sửa lỗi, 5 gói sửa nhanh, trang Tiện ích. **GĐ2 đang làm:** đã có trang Phần mềm (danh mục, profile, cài qua winget và share), bước Kiểm tra trước và cấu hình chuẩn; wizard join domain chờ thông tin công ty. **GĐ3:** đã có dọn rác có quét trước, quản lý khởi động, tối ưu và quyền riêng tư. Các mục đổi hệ thống chưa chạy thật bằng quyền admin, xem [docs/HANDOFF.md](docs/HANDOFF.md).

| Tài liệu | Nội dung |
|---|---|
| [docs/TIEN-DO.md](docs/TIEN-DO.md) | **Xem nhanh:** đã làm tới đâu, còn lại gì |
| [docs/HANDOFF.md](docs/HANDOFF.md) | **Đọc đầu tiên:** trạng thái, quy tắc, luồng chạy, việc chưa kiểm, việc tiếp theo |
| [PLAN.md](PLAN.md) | Kế hoạch tổng: chức năng, kiến trúc, lộ trình, câu hỏi còn mở |
| [docs/ACTIONS.md](docs/ACTIONS.md) | Tham chiếu khai báo mục sửa lỗi / tweak bằng YAML |
| [docs/SOFTWARE.md](docs/SOFTWARE.md) | Khai báo danh mục phần mềm và profile phòng ban (apps.yaml) |
| [CHANGELOG.md](CHANGELOG.md) | Thay đổi theo phiên bản |

## Quy ước nhánh

Code mới và chức năng mới làm trên nhánh **`featured`**. Chỉ đưa về `main` sau khi được duyệt.

## Chạy từ mã nguồn

```powershell
py -3.13 -m venv .venv
.venv\Scripts\python -m pip install -e .[dev]
.venv\Scripts\python -m fvpl_ittools              # hỏi mở lại bằng quyền admin
.venv\Scripts\python -m fvpl_ittools --no-elevate # chạy luôn không admin (các mục cần admin bị khoá)
```

## Kiểm thử

```powershell
.venv\Scripts\python -m pytest
```

Test chỉ chạy lệnh vô hại. Phần registry chỉ ghi vào khoá tạm `HKCU\Software\FVPL-ITTools-Test` và xoá sau khi test xong. Log và nhật ký hoàn tác ghi vào thư mục tạm, không đụng `%ProgramData%`.

Tự kiểm tra giao diện (chụp ảnh từng trang + `selftest.json`):

```powershell
.venv\Scripts\python -m fvpl_ittools --selftest C:\Temp\selftest
```

## Đóng gói exe

```powershell
.venv\Scripts\python packaging\build.py          # bản phát hành: exe tự xin quyền admin (UAC)
.venv\Scripts\python packaging\build.py --test   # bản thử: không xin UAC, tự chạy selftest sau khi build
```

Kết quả: `dist\FVPL-ITTools\` (khoảng 65MB) và `dist\FVPL-ITTools-v<phiên bản>.zip`.

## Hai bản mang theo: USB và SSD

Cùng một chương trình, khác nhau ở **kho bộ cài** (nơi lấy Office, Symantec, nguồn .NET 3.5…):

| Bản | Trên ổ có gì | Kho bộ cài |
|---|---|---|
| **USB** | `FVPL-ITTools\` + `site.yaml` | Share mạng (`share_root` trong site.yaml): sửa lỗi, cài phần mềm qua mạng |
| **SSD** | như USB + `FVPL-ITTools\SOFT\` (ISO, bộ cài, `config\apps.yaml`) | Thư mục `SOFT` cạnh file exe: cài máy mới không cần tải, không cần vào share |

Tool tự nhận: có thư mục `SOFT` cạnh file exe thì dùng nó, không thì dùng share. Trang Phần mềm và bước Kiểm tra trước ghi rõ đang dùng kho nào. Chép ra ổ (sau khi build bản phát hành):

```powershell
.venv\Scripts\python packaging\deploy.py usb E:\    # bản USB
.venv\Scripts\python packaging\deploy.py ssd F:\    # bản SSD, chép thêm thư mục SOFT của repo (không bao giờ commit)
```

Chép lại lần sau chỉ chép phần thay đổi. Cấu trúc thư mục `SOFT` giống thư mục share, xem [site.example.yaml](site.example.yaml) và [docs/SOFTWARE.md](docs/SOFTWARE.md).

## Thêm một mục sửa lỗi / tweak mới

Thêm một khối YAML vào file trong `src/fvpl_ittools/data/actions/`, không cần sửa code. Đủ các khoá và các bẫy hay gặp xem [docs/ACTIONS.md](docs/ACTIONS.md). Xong thì chạy `pytest`: test sẽ báo lỗi khai báo bằng tiếng Việt kèm tên file và số thứ tự mục.

```yaml
- id: net.flush_dns            # nhom.ten, chữ thường không dấu
  name: Xoá cache DNS
  category: Mạng & Internet
  page: fixes                  # fixes | optimize | config | utilities
  risk: safe                   # safe | caution | advanced (caution/advanced bắt buộc khai báo undo)
  description: >
    Mô tả cho IT đọc trong khung chi tiết.
  apply:
    - cmd: ipconfig /flushdns
```

Các loại bước: `cmd`, `powershell`, `registry` (tự sao lưu để hoàn tác), `service` (start/stop/restart), `builtin` (thao tác viết bằng Python, ví dụ `restart_explorer`). Script PowerShell có sẵn biến người dùng và bộ hàm kiểm tra (ping, cổng, DNS, DC); gói sửa nhanh khai báo trong `data/packs.yaml`. Chi tiết ở [docs/ACTIONS.md](docs/ACTIONS.md).

## Thông tin nội bộ

Repo để public, nên tên domain, server, đường dẫn share, OU nằm trong `site.yaml`. File này đã có trong `.gitignore`, không commit. Chép từ [site.example.yaml](site.example.yaml), đặt cạnh file exe hoặc trong `%ProgramData%\FVPL-ITTools\`.

## Cấu trúc

```
src/fvpl_ittools/
├── __main__.py        điểm vào, hỏi quyền admin, --selftest
├── app.py             gom thông tin máy, người dùng, danh sách mục
├── actions/           mô hình + bộ nạp/kiểm tra YAML
├── core/              chạy lệnh (shell, pslib), registry, executor, thông tin máy (inventory),
│                      nhật ký hoàn tác, restore point, log
├── software/          danh mục phần mềm, phát hiện đã cài, lệnh cài (winget, share)
├── newpc/             Cài máy mới: kiểm tra trước
├── cleanup/           dọn rác, chương trình khởi động cùng Windows
├── ui/                PySide6: cửa sổ chính, các trang, khung log, hộp thoại tài khoản
└── data/
    ├── actions/       các mục sửa lỗi / tweak (YAML)
    ├── apps.yaml      danh mục phần mềm mặc định
    ├── packs.yaml     gói sửa nhanh
    └── scripts/       script PowerShell đọc thông tin máy cho trang Tổng quan
packaging/             spec PyInstaller + build.py
tests/                 pytest
```

Dữ liệu khi chạy: `%ProgramData%\FVPL-ITTools\logs\` (log từng phiên, giữ 90 ngày), `undo\journal.json` (nhật ký hoàn tác) và `reports\` (thông tin máy xuất HTML, báo cáo gpresult).
