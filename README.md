# FVPL IT Toolkit

Công cụ cho IT: cài máy mới, join domain, sửa lỗi thường gặp, tối ưu Windows.
Viết bằng Python 3.13 + PySide6, đóng gói thành exe chạy portable từ USB hoặc share.

- Trạng thái: **GĐ0 (nền móng) xong.** Khung app, bộ chạy lệnh, định nghĩa mục bằng YAML, log, hoàn tác, đóng gói exe, 3 mục mẫu.

| Tài liệu | Nội dung |
|---|---|
| [docs/HANDOFF.md](docs/HANDOFF.md) | **Đọc đầu tiên:** trạng thái, quy tắc, luồng chạy, việc chưa kiểm, việc tiếp theo |
| [PLAN.md](PLAN.md) | Kế hoạch tổng: chức năng, kiến trúc, lộ trình, câu hỏi còn mở |
| [docs/ACTIONS.md](docs/ACTIONS.md) | Tham chiếu khai báo mục sửa lỗi / tweak bằng YAML |
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

Các loại bước: `cmd`, `powershell`, `registry` (tự sao lưu để hoàn tác), `service` (start/stop/restart), `builtin` (thao tác viết bằng Python, ví dụ `restart_explorer`).

## Thông tin nội bộ

Repo để public, nên tên domain, server, đường dẫn share, OU nằm trong `site.yaml`. File này đã có trong `.gitignore`, không commit. Chép từ [site.example.yaml](site.example.yaml), đặt cạnh file exe hoặc trong `%ProgramData%\FVPL-ITTools\`.

## Cấu trúc

```
src/fvpl_ittools/
├── __main__.py        điểm vào, hỏi quyền admin, --selftest
├── app.py             gom thông tin máy, người dùng, danh sách mục
├── actions/           mô hình + bộ nạp/kiểm tra YAML
├── core/              chạy lệnh (shell), registry, executor, nhật ký hoàn tác, restore point, log
├── ui/                PySide6: cửa sổ chính, các trang, khung log
└── data/actions/      các mục sửa lỗi / tweak (YAML)
packaging/             spec PyInstaller + build.py
tests/                 pytest
```

Dữ liệu khi chạy: `%ProgramData%\FVPL-ITTools\logs\` (log từng phiên, giữ 90 ngày) và `undo\journal.json` (nhật ký hoàn tác).
