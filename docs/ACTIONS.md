# Khai báo mục sửa lỗi / tweak bằng YAML

Mỗi mục là một khối trong file `src/fvpl_ittools/data/actions/*.yaml`. Thêm mục không cần sửa code.
Khai báo sai thì mục đó bị loại, tool báo lỗi bằng tiếng Việt kèm tên file và số thứ tự. Các mục khác vẫn chạy bình thường.

**Sau khi thêm hoặc sửa thì chạy `.venv\Scripts\python -m pytest`.** Test `test_bundled_actions_load_without_errors` sẽ fail nếu có mục khai báo sai.

## Ví dụ đủ các phần

```yaml
- id: ui.show_file_ext
  name: Hiện đuôi file
  category: Tuỳ chọn hay dùng
  page: config
  risk: safe
  scope: user
  admin: false
  description: >
    Hiện phần đuôi (.docx, .pdf, .exe...) của tên file trong File Explorer.
  check:
    registry:
      key: HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced
      name: HideFileExt
      on_value: 0
  apply:
    - registry:
        key: HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced
        name: HideFileExt
        type: DWORD
        value: 0
  undo: auto
  after: [restart_explorer]
```

## Các khoá của một mục

| Khoá | Bắt buộc | Mặc định | Ý nghĩa |
|---|---|---|---|
| `id` | có | | Dạng `nhom.ten`: chữ thường không dấu, số, `_`. Không được trùng giữa các file. |
| `name` | có | | Tên hiện trong danh sách. |
| `category` | có | | Nhóm trong cây (ví dụ `Mạng & Internet`). |
| `page` | | `fixes` | Trang hiện mục: `fixes` (Sửa lỗi), `optimize` (Tối ưu & dọn dẹp), `config` (Cấu hình), `utilities` (Tiện ích). |
| `risk` | | `safe` | `safe` / `caution` / `advanced` (An toàn / Cẩn thận / Nâng cao). Mục Cẩn thận/Nâng cao sẽ hỏi xác nhận và tạo restore point trước khi chạy. |
| `scope` | | `machine` | `machine`: áp cho cả máy, **không được** ghi HKCU. `user`: áp cho người đang đăng nhập, **chỉ được** ghi HKCU; tool tự đổi sang `HKU\<SID>` khi IT chạy tool bằng tài khoản khác. |
| `admin` | | `true` | Cần quyền admin. Tool không có quyền admin thì mục bị khoá. |
| `reboot` | | `false` | Cần khởi động lại sau khi chạy (chỉ tính khi mục có thay đổi). |
| `os` | | | `{ min_build: 22000, max_build: 26100 }`. Ví dụ 19045 = Win10 22H2, 22000 = Win11 đầu tiên. |
| `description` | | | Mô tả hiện trong khung chi tiết. Viết cho IT đọc: làm gì, dùng khi nào, ảnh hưởng gì. |
| `check` | | | `{ registry: { key, name, on_value } }`. Đọc trạng thái hiện tại: giá trị bằng `on_value` thì hiện "Đang bật", ngược lại "Đang tắt". |
| `apply` | có | | Danh sách bước, chạy lần lượt. Một bước lỗi thì dừng mục đó. |
| `undo` | có nếu `risk` khác `safe` | `auto` khi có bước registry, ngược lại `none` | `auto`: trả registry về giá trị đã sao lưu. `none`: không hoàn tác được. Hoặc một danh sách bước hoàn tác. |
| `after` | | | Thao tác làm sau, ví dụ `[restart_explorer]`. Chỉ chạy nếu mục có thay đổi, và chạy **một lần** cho cả lượt dù nhiều mục cùng khai báo. |
| `gpo` | | | `[{ key, name }]`. Nếu một giá trị trong đây có mặt, mục hiện "GPO quản lý" và không chạy. |
| `needs_credential` | | | `domain`. Hộp thoại nhập tài khoản **chưa có (làm ở GĐ1)**. Script PowerShell dùng biến `$Credential`. |

## Các loại bước

Mỗi bước có đúng **một** trong các khoá sau:

| Loại | Cách viết | Ghi chú |
|---|---|---|
| `cmd` | `- cmd: ipconfig /flushdns` | Chạy bằng `cmd.exe /d /s /c` sau khi `chcp 65001`. Lệnh có sẵn của cmd như `echo` không in được chữ có dấu, chỗ đó dùng PowerShell. |
| `powershell` | `- powershell: \|` rồi các dòng script | Windows PowerShell 5.1, gặp lỗi là dừng (`$ErrorActionPreference = 'Stop'`), output UTF-8. Mã thoát là mã của lệnh native cuối cùng, gặp lỗi thì là 1; tự đặt được bằng `exit N`. Script dài tối đa khoảng 11.000 ký tự. |
| `registry` | `- registry: { key, name, type, value }` | `type`: `DWORD`, `QWORD`, `SZ`, `EXPAND_SZ`, `MULTI_SZ` (danh sách chuỗi), `BINARY` (chuỗi hex `"01 0a ff"` hoặc danh sách số). `name: ""` là giá trị mặc định của khoá. Xoá giá trị thì viết `{ key, name, delete: true }`. Giá trị đã đúng sẵn thì bỏ qua và không ghi nhật ký. Không được ghi thẳng `HKU`. |
| `service` | `- service: { name: Spooler, action: restart }` | `action`: `start` / `stop` / `restart`. Đổi kiểu khởi động làm ở GĐ3. |
| `builtin` | `- builtin: restart_explorer` | Thao tác viết bằng Python. Hiện có: `restart_explorer`. |

Khoá dùng chung cho mọi bước:

| Khoá | Mặc định | Ý nghĩa |
|---|---|---|
| `timeout` | 600 | Số giây tối đa, quá thì dừng lệnh (kill cả cây tiến trình). |
| `ok_codes` | `[0]` | Các mã thoát coi là thành công. |
| `reboot_codes` | `[3010, 1641]` | Các mã thoát nghĩa là thành công nhưng cần khởi động lại. |
| `encoding` | `auto` | Chỉ cho `cmd`/`powershell`. `auto` tự nhận UTF-8 / UTF-16 (như `sfc`) / code page OEM. |

## Bẫy hay gặp

- **Đừng đặt tên khoá là `on`, `off`, `yes`, `no`.** YAML hiểu chúng là true/false. Đây là lý do khoá trạng thái tên là `on_value`.
- **Đường dẫn có `\`** thì để không ngoặc hoặc trong ngoặc đơn `'...'`. Ngoặc kép `"..."` làm YAML hiểu `\S`, `\n`... là ký tự đặc biệt.
- **Mục `scope: machine` mà ghi HKCU** thì bị loại. Nếu thiết lập là của người dùng, khai báo `scope: user`.
- **Không dò chữ trong output** để quyết định thành công hay lỗi, vì Windows tiếng Việt và tiếng Anh in khác nhau. Dùng mã thoát (`ok_codes`), hoặc cho script PowerShell `exit` với mã phù hợp.
- **Dùng SID hoặc ID nhóm thay cho tên hiển thị** (ví dụ nhóm Administrators là `S-1-5-32-544`), vì tên bị dịch theo ngôn ngữ Windows.
