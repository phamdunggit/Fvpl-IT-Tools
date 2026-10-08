# Bàn giao: đọc file này trước khi làm tiếp

Cập nhật lần cuối: 08/10/2026, sau khi xong GĐ0.

## Trạng thái

| | |
|---|---|
| Giai đoạn | **GĐ0 (nền móng) xong.** Kế tiếp là GĐ1: Tổng quan + Sửa lỗi |
| Nhánh | Code mới làm trên `featured`. Chỉ merge về `main` khi được duyệt |
| Phiên bản | 0.1.0, xem [CHANGELOG.md](../CHANGELOG.md) |
| Test | 80 test pytest, tất cả đều qua |
| Bản exe | `python packaging\build.py`: thư mục 64MB, zip 25MB |

Đã có:
- Khung app (8 trang, 3 trang có nội dung thật: Sửa lỗi, Cấu hình, Nhật ký).
- Bộ chạy lệnh, executor, nhật ký hoàn tác, restore point, log.
- Bộ nạp YAML.
- 3 mục mẫu: `net.flush_dns`, `sys.restart_explorer`, `ui.show_file_ext`.

## Bắt đầu

```powershell
py -3.13 -m venv .venv
.venv\Scripts\python -m pip install -e .[dev]
.venv\Scripts\python -m pytest
.venv\Scripts\python -m fvpl_ittools --no-elevate
```

Chi tiết chạy, build, selftest: [README.md](../README.md). Cách khai báo mục: [ACTIONS.md](ACTIONS.md). Kế hoạch tổng: [PLAN.md](../PLAN.md).

## Quy tắc khi làm repo này

1. **Làm trên nhánh `featured`.** Không commit thẳng lên `main`, không tự merge.
2. **Repo để public.** Tên domain, server, đường dẫn share, OU, tên máy thật **không** được nằm trong code hay docs. Thông tin thật để trong `site.yaml` (gitignore). Trong docs viết `<domain>`, `<server>`. Trước khi commit, tìm tên nội bộ trong các file sắp commit.
3. **Máy dev là máy làm việc thật.** Không chạy thử các mục làm đổi hệ thống trên máy này. Test registry chỉ dùng khoá tạm `HKCU\Software\FVPL-ITTools-Test`. Explorer được giả lập trong test (fixture `fake_explorer`). Muốn chạy thật thì dùng máy ảo.
4. **Thêm mục mới bằng YAML** ([ACTIONS.md](ACTIONS.md)), chỉ viết Python khi YAML không làm được. Khi viết Python thì thêm vào `BUILTIN_NAMES` (model.py) và `BUILTINS` (executor.py); có test kiểm tra hai danh sách này khớp nhau.

## Một mục chạy như thế nào

```
ActionsPage (bấm Chạy)
  → RunController.run()               ui/controller.py, chạy ở thread nền
    → executor.run_batch()            core/executor.py
        blocked_reason()              sai bản Windows / thiếu quyền admin / GPO quản lý → bỏ qua
        restore point                 nếu có mục Cẩn thận/Nâng cao và đang có quyền admin
        run_action() từng mục
          cmd/powershell/service      → core/shell.py (giải mã output, timeout, huỷ)
          registry                    → core/registry.py, lưu trước/sau vào core/journal.py
          builtin                     → executor.BUILTINS
        việc làm sau (after)          chạy một lần cho cả lượt
  ← LogEvent qua Qt signal            → khung log; BatchResult → cột Trạng thái, hỏi restart
```

Hoàn tác: trang Nhật ký hoặc nút Hoàn tác ở khung chi tiết gọi `executor.undo_entry()`. Hàm này đọc `journal.json` rồi trả từng giá trị về như trước.

## Chưa kiểm chứng (làm khi bắt đầu GĐ1)

- [ ] **Chạy với quyền admin.** Phiên phát triển không có quyền admin, nên phần tạo restore point thật và các mục `admin: true` (như `net.flush_dns`) mới chỉ được test bằng giả lập. Cần mở exe bản phát hành (bấm Yes ở UAC), chạy "Xoá cache DNS", và thử một mục `risk: caution` để thấy restore point được tạo.
- [ ] **Máy ảo Win10 22H2 và Win11 sạch** (chưa cài Python): mở exe, chạy 3 mục mẫu, hoàn tác "Hiện đuôi file". Đây là tiêu chí "Xong khi" của GĐ0 trong PLAN.
- [ ] **Run as different user:** mở tool bằng tài khoản admin khác trong phiên của người dùng. Thanh trên cùng phải báo "Chạy bằng … · áp cho …", và "Hiện đuôi file" phải đổi registry của người dùng chứ không phải của tài khoản IT.

## Việc tiếp theo: GĐ1

Theo PLAN mục 5.1, 5.3 và 8:

1. Hộp thoại nhập tài khoản cho `needs_credential: domain`. Truyền qua `shell.run_powershell(credential=…)`, đăng ký mật khẩu với `log.register_secret()` để che trong log.
2. Các fix P1: mạng, domain (trust relationship, đồng bộ giờ, gpupdate…), máy in, Windows Update, hệ thống (SFC/DISM, chkdsk…), Office. Mỗi fix là một khối YAML.
3. Gói sửa nhanh (*Sửa mạng*, *Sửa máy in*, *Sửa Windows Update*, *Sửa domain*): chạy chuỗi bước và dừng khi có bước lỗi.
4. Trang Tổng quan đầy đủ: phần cứng, bảo mật, copy/xuất thông tin.
5. Mở nhanh các panel hệ thống.

Cần user trả lời trước (PLAN mục 11), nhất là **câu 11: 10 lỗi người dùng hay báo nhất**, để chọn fix nào làm trước.

## Bẫy đã gặp

- **YAML hiểu `on` là `true`.** Vì vậy khoá trạng thái tên là `on_value`.
- **Lệnh có sẵn của cmd (`echo`) ghi theo code page OEM 437**, nên `chcp 65001` không giúp được. Chữ có dấu thì in bằng PowerShell.
- **Windows để chế độ tối** làm ô tick vô hình. `theme.apply_theme()` ép bảng màu sáng.
- **Chụp ảnh giao diện không cần màn hình:** nền `offscreen` mặc định vẽ chữ thành ô vuông. Phải dùng `QT_QPA_PLATFORM=offscreen:fontengine=freetype` và `QT_QPA_FONTDIR=C:\Windows\Fonts`; `tests/conftest.py` đã đặt sẵn.
- **Build lỗi khi shell đang `cd` vào `dist\`:** PyInstaller không xoá được thư mục cũ. Ra khỏi `dist\` rồi build lại.
- **Kích thước exe:** plugin bàn phím ảo kéo theo Quick/Qml/Network/OpenGL. Danh sách loại bỏ nằm trong `packaging/fvpl_ittools.spec` (`UNUSED`). Thêm module Qt mới mà exe lỗi thì xem lại danh sách này.
