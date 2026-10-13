# Danh mục phần mềm (apps.yaml)

Trang **Phần mềm** đọc danh mục từ `apps.yaml`:

1. `<share_root>\config\apps.yaml` nếu `site.yaml` có `share_root` và vào được share. IT sửa file này là xong, không phải build lại tool.
2. Không có thì dùng bản đóng gói kèm tool: `src/fvpl_ittools/data/apps.yaml` (danh sách gợi ý, chưa chốt).

Khai báo sai thì ứng dụng / profile đó bị loại, khung log báo lỗi tiếng Việt kèm tên file và số thứ tự; phần còn lại vẫn dùng được. Sửa bản đóng gói thì chạy `pytest` (test `test_bundled_catalog_loads_without_errors`). Sửa bản trên share thì mở tool, vào trang Phần mềm, xem khung log.

## Ứng dụng

```yaml
apps:
  - id: chrome                 # chữ thường không dấu, số, - và _
    name: Google Chrome
    group: Trình duyệt         # nhóm trong cây
    source: winget
    winget_id: Google.Chrome   # tra bằng: winget search chrome

  - id: office
    name: Microsoft Office
    group: Văn phòng
    source: share
    installer: '{share}\Installers\Office\setup.exe'
    args: '/configure "{share}\Installers\Office\config-van-phong.xml"'
    detect: { uninstall_name: 'Microsoft 365*|Microsoft Office*' }
    timeout: 3600

  - id: unikey
    name: UniKey
    group: Gõ tiếng Việt
    source: share
    type: portable
    path: '{share}\Installers\UniKey'
    exe: UniKeyNT.exe
    autostart: true
```

| Khoá | Dùng cho | Ý nghĩa |
|---|---|---|
| `id`, `name` | mọi ứng dụng | Bắt buộc. `id` dùng trong profile. |
| `group` | mọi ứng dụng | Nhóm trong cây, mặc định "Khác". |
| `source` | mọi ứng dụng | `winget` hoặc `share`. |
| `winget_id` | winget | ID gói, đúng chữ hoa/thường như `winget search` hiện. Tool chỉ lấy từ nguồn `winget` (không dùng Microsoft Store). |
| `installer` | share | File cài (`.msi` hoặc `.exe`). Với `type: portable` thì là thư mục, viết `path:` cũng được. |
| `type` | share | `msi` / `exe` / `portable`. Bỏ trống thì tự đoán theo đuôi file. |
| `args` | share | Tham số thêm. MSI: thêm sau `/qn /norestart` (ví dụ `ALLUSERS=1 TRANSFORMS=x.mst`). EXE: **toàn bộ** tham số cài im lặng, phải tự tìm cho từng bộ cài (ví dụ `/S`, `/VERYSILENT /NORESTART`). Thiếu tham số im lặng thì bộ cài hiện cửa sổ và đứng chờ tới hết `timeout`. |
| `exe`, `folder`, `autostart` | portable | `exe`: file chạy chính. `folder`: tên thư mục trong Program Files (mặc định = `id`). `autostart: true`: tạo shortcut trong Startup chung để chạy cùng Windows với mọi người dùng. |
| `detect` | mọi ứng dụng | Cách nhận biết đã cài. `uninstall_name`: mẫu tên trong Programs and Features, `*` thay cho chữ bất kỳ, nhiều mẫu cách nhau bằng `\|`. `file`: có file này là đã cài. Mặc định: tên ứng dụng + `*` (portable: `{programfiles}\<folder>\<exe>`). |
| `scope` | mọi ứng dụng | `user` nếu bộ cài chỉ cài cho tài khoản đang chạy nó (ví dụ Zalo). Khi IT mở tool bằng tài khoản khác, ứng dụng này bị khoá để không cài nhầm vào tài khoản IT. |
| `timeout` | mọi ứng dụng | Số giây tối đa, mặc định 1800. |
| `description` | mọi ứng dụng | Hiện khi rê chuột lên tên ứng dụng. |

Chỗ giữ chỗ trong đường dẫn và tham số: `{share}` (= `share_root` trong site.yaml), `{programfiles}`, `{programfiles_x86}`.

## Profile phòng ban

```yaml
profiles:
  van-phong:
    name: Văn phòng
    apps: [chrome, office, unikey]
  ke-toan:
    name: Kế toán
    extends: van-phong          # một tên hoặc danh sách tên
    apps: [htkk, itaxviewer]
```

Profile kế thừa được nhiều tầng; ứng dụng của profile cha đứng trước, trùng thì chỉ tính một lần. Kế thừa vòng tròn, kế thừa profile không có hoặc đang khai báo sai thì profile đó bị loại.

Bấm **Chọn theo profile** trên trang Phần mềm sẽ tick các ứng dụng của profile mà máy chưa có và cài được.

## Cài như thế nào

| Nguồn | Lệnh | Thành công khi |
|---|---|---|
| winget | `winget install --id <id> --exact --source winget --silent --accept-package-agreements --accept-source-agreements --disable-interactivity` | Mã 0, hoặc báo đã cài sẵn / không có bản mới. Mã lỗi thường gặp được giải thích bằng tiếng Việt. |
| MSI | `msiexec /i "<file>" /qn /norestart /l*v "<log>" <args>` | Mã 0; 3010/1641 là xong nhưng cần khởi động lại. Mã 1618 (đang có bộ cài khác) thì chờ 30 giây, thử lại tối đa 3 lần. Log MSI nằm trong thư mục logs của tool. |
| EXE | `"<file>" <args>`, thư mục làm việc là thư mục chứa bộ cài | Như MSI. |
| portable | chép thư mục vào `Program Files\<folder>` (robocopy), tạo shortcut Start Menu (và Startup nếu `autostart`) | Chép được và có file `exe`. |

Các ứng dụng cài **lần lượt**; một ứng dụng lỗi thì vẫn cài tiếp ứng dụng sau. Xong lượt, tool kiểm tra lại phần mềm đã cài và hỏi khởi động lại nếu có bộ cài cần. Nút **Thử lại mục lỗi** cài lại các ứng dụng vừa lỗi.

Ứng dụng bị khoá (hiện "Không cài được", rê chuột lên để xem lý do) khi: tool không có quyền admin; máy chưa có winget; chưa khai báo `share_root`, không vào được share hoặc không thấy bộ cài; ứng dụng `scope: user` mà tool chạy bằng tài khoản khác.

## Lưu ý

- **Máy chưa vào domain thì thường không vào được share.** Bước join domain của wizard Cài máy mới (GĐ2) sẽ lo việc này; hiện tại cần map share bằng tài khoản domain trước (`net use`), hoặc cài phần mềm sau khi join.
- **winget thuộc từng tài khoản.** Tool dùng winget của tài khoản đang chạy tool; tài khoản chưa đăng nhập lần nào thì có thể chưa có winget. Việc cài lại winget từ share làm ở GĐ2.
- **Tìm tham số cài im lặng** cho EXE: thử `setup.exe /?`, xem trang của hãng, hoặc tra "<tên phần mềm> silent install". Thử trên máy ảo trước khi đưa vào danh mục.
