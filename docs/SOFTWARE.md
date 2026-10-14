# Danh mục phần mềm (apps.yaml)

Trang **Cài phần mềm** đọc danh mục từ `apps.yaml`:

1. `<kho bộ cài>\config\apps.yaml`. Kho bộ cài là thư mục `SOFT` cạnh file exe (bản SSD) nếu có, không thì `share_root` trong `site.yaml` (bản USB, cần vào được share). IT sửa file này là xong, không phải build lại tool. `{share}` trong danh mục trỏ tới kho đang dùng.
2. Không có thì dùng bản đóng gói kèm tool: `src/fvpl_ittools/data/apps.yaml` (danh sách gợi ý, chưa chốt).

Khai báo sai thì ứng dụng / profile đó bị loại, khung log báo lỗi tiếng Việt kèm tên file và số thứ tự; phần còn lại vẫn dùng được. Sửa bản đóng gói thì chạy `pytest` (test `test_bundled_catalog_loads_without_errors`). Sửa bản trên share thì mở tool, vào trang Cài phần mềm, xem khung log.

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
| `installer` | share | File cài (`.msi`, `.exe` hoặc file `.iso`). Với `type: portable` thì là thư mục, viết `path:` cũng được. |
| `type` | share | `msi` / `exe` / `iso` / `portable`. Bỏ trống thì tự đoán theo đuôi file. |
| `setup` | iso | File chạy bên trong ISO, mặc định `setup.exe` (ví dụ `x64\setup.exe`). |
| `args` | share | Tham số thêm. MSI: thêm sau `/qn /norestart` (ví dụ `ALLUSERS=1 TRANSFORMS=x.mst`). EXE: **toàn bộ** tham số cài im lặng, phải tự tìm cho từng bộ cài (ví dụ `/S`, `/VERYSILENT /NORESTART`). Thiếu tham số im lặng thì bộ cài hiện cửa sổ và đứng chờ tới hết `timeout`. |
| `exe`, `folder`, `autostart` | portable | `exe`: file chạy chính. `folder`: tên thư mục trong Program Files (mặc định = `id`). `autostart: true`: tạo shortcut trong Startup chung để chạy cùng Windows với mọi người dùng. |
| `detect` | mọi ứng dụng | Cách nhận biết đã cài. `uninstall_name`: mẫu tên trong Programs and Features, `*` thay cho chữ bất kỳ, nhiều mẫu cách nhau bằng `\|`. `file`: có file này là đã cài. Mặc định: tên ứng dụng + `*` (portable: `{programfiles}\<folder>\<exe>`). |
| `scope` | mọi ứng dụng | `user` nếu bộ cài chỉ cài cho tài khoản đang chạy nó (ví dụ Zalo). Khi IT mở tool bằng tài khoản khác, ứng dụng này bị khoá để không cài nhầm vào tài khoản IT. |
| `timeout` | mọi ứng dụng | Số giây tối đa, mặc định 1800. |
| `conflicts` | mọi ứng dụng | Mẫu tên (giống `detect.uninstall_name`) của phần mềm không cài chung được. Máy đang có phần mềm khớp mẫu (chỉ tính mục hiện trong Programs and Features) thì ứng dụng bị khoá kèm lý do. Ví dụ Office bản volume: `'Microsoft 365*\|Microsoft Office Professional*'`. |
| `choice` | mọi ứng dụng | Tên nhóm chọn một, ví dụ `office`. Các ứng dụng cùng `choice` không nằm trong cây mà hiện thành **thẻ chọn một** ở đầu trang Cài phần mềm (thêm thẻ "Không cài"); chọn được một bản. Profile có một ứng dụng của nhóm thì bấm Chọn theo profile sẽ chọn sẵn bản đó. |
| `description` | mọi ứng dụng | Hiện khi rê chuột lên tên ứng dụng (thẻ chọn: rê lên thẻ). |

Chỗ giữ chỗ trong đường dẫn và tham số: `{share}` (= `share_root` trong site.yaml), `{programfiles}`, `{programfiles_x86}`.

## Profile phòng ban

```yaml
profiles:
  van-phong:
    name: Văn phòng
    apps: [chrome, office2016, unikey]
  ke-toan:
    name: Kế toán
    extends: van-phong          # một tên hoặc danh sách tên
    apps: [htkk, itaxviewer]
```

Profile kế thừa được nhiều tầng; ứng dụng của profile cha đứng trước, trùng thì chỉ tính một lần. Kế thừa vòng tròn, kế thừa profile không có hoặc đang khai báo sai thì profile đó bị loại.

Bấm **Chọn theo profile** trên trang Cài phần mềm sẽ tick các ứng dụng của profile mà máy chưa có và cài được.

## Cài như thế nào

| Nguồn | Lệnh | Thành công khi |
|---|---|---|
| winget | `winget install --id <id> --exact --source winget --silent --accept-package-agreements --accept-source-agreements --disable-interactivity` | Mã 0, hoặc báo đã cài sẵn / không có bản mới. Mã lỗi thường gặp được giải thích bằng tiếng Việt. |
| MSI | `msiexec /i "<file>" /qn /norestart /l*v "<log>" <args>` | Mã 0; 3010/1641 là xong nhưng cần khởi động lại. Mã 1618 (đang có bộ cài khác) thì chờ 30 giây, thử lại tối đa 3 lần. Log MSI nằm trong thư mục logs của tool. |
| EXE | `"<file>" <args>`, thư mục làm việc là thư mục chứa bộ cài | Như MSI. |
| ISO | Mount ISO, chạy `<setup> <args>` bên trong, tháo ISO ra kể cả khi lỗi. ISO đang được mount sẵn thì dùng luôn và để nguyên | Như MSI. |
| portable | chép thư mục vào `Program Files\<folder>` (robocopy), tạo shortcut Start Menu (và Startup nếu `autostart`) | Chép được và có file `exe`. |

Các ứng dụng cài **lần lượt**; một ứng dụng lỗi thì vẫn cài tiếp ứng dụng sau. Xong lượt, tool kiểm tra lại phần mềm đã cài và hỏi khởi động lại nếu có bộ cài cần. Nút **Thử lại mục lỗi** cài lại các ứng dụng vừa lỗi.

Kho bộ cài: thư mục `SOFT` cạnh tool (bản SSD), nếu không có thì kho IT đã chọn bằng nút **Chọn kho…** ở đầu trang Cài phần mềm (nhớ cho lần sau, trong `%APPDATA%\FVPL-ITTools\prefs.json`), cuối cùng là `share_root` trong site.yaml. Kho không có `config\apps.yaml` thì tool dùng danh mục mặc định đóng gói kèm (đã có Office 2016 / 2013 / 2010 với tên ISO như ở mục dưới, và Microsoft 365 qua winget).

Ứng dụng bị khoá (hiện "Không cài được", rê chuột lên để xem lý do) khi: tool không có quyền admin; máy đang có phần mềm khớp `conflicts`; máy chưa có winget; chưa khai báo `share_root`, không vào được share hoặc không thấy bộ cài; ứng dụng `scope: user` mà tool chạy bằng tài khoản khác.

## Office bản volume (MSI) và phần mềm diệt virus

Office 2010 / 2013 / 2016 bản volume (ISO `SW_DVD5_Office_..._MLF`) cài bằng `setup.exe /config <file xml>`. Khai báo kiểu `iso`, tool tự mount ISO:

```yaml
  - id: office2016
    name: Microsoft Office Standard 2016 (64-bit)
    group: Văn phòng
    source: share
    installer: '{share}\Installers\Office\SW_DVD5_Office_2016_64Bit_English_MLF_X20-42479.ISO'
    args: '/config "{share}\config\office\office2016-standard.xml"'
    detect: { uninstall_name: 'Microsoft Office Standard 2016*' }
    # Máy mới hay có Microsoft 365 cài sẵn: không cài chung được, trang Cài phần mềm báo và chỉ cách gỡ.
    conflicts: 'Microsoft 365*|Microsoft Office 365*|Microsoft Office Home*|Microsoft Office Professional*|Microsoft Office Standard 2013*|Microsoft Office Standard 2010*'
    timeout: 3600
```

Cài xong mà chưa kích hoạt (máy chưa có Internet lúc cài): mục **Kích hoạt Office bản volume (MAK)** ở trang Sửa lỗi.
Khai báo thêm `choice: office` cho các bản Office để trang Cài phần mềm hiện thẻ chọn một bản. Máy có Microsoft 365 / Office cài sẵn kiểu Click-to-Run thì khi chọn Office bản volume, trang Cài phần mềm hiện cảnh báo và tick sẵn **Gỡ trước khi cài**: lượt cài chạy mục gỡ trước, cài các phần mềm khác, cài Office sau cùng (Office lỗi vì chưa khởi động lại thì khởi động lại rồi bấm Thử lại mục lỗi). Office bản MSI khác đang cài thì vẫn phải gỡ bằng tay.
Gỡ Microsoft 365 cài sẵn: mục **Gỡ Microsoft 365 / Office cài sẵn (Click-to-Run)**. Cách dùng từng bước:
[HUONG-DAN-SU-DUNG.md](HUONG-DAN-SU-DUNG.md) mục 4–5.

File xml cài im lặng (đặt trên share, **không** đưa lên git nếu có key):

```xml
<Configuration Product="Standard">  <!-- Product: tên thư mục *.WW trong ISO, ví dụ Standard, ProPlus -->
  <Display Level="none" CompletionNotice="no" SuppressModal="yes" AcceptEula="yes" />
  <Logging Type="standard" Path="%temp%" Template="Office Setup(*).txt" />
  <!-- <PIDKEY Value="XXXXX-XXXXX-XXXXX-XXXXX-XXXXX" /> -->   <!-- key MAK nếu công ty dùng MAK -->
  <Setting Id="AUTO_ACTIVATE" Value="1" />
  <Setting Id="SETUP_REBOOT" Value="Never" />
</Configuration>
```

Office 2019 trở đi không có bộ cài MSI: cài bằng Office Deployment Tool (`setup.exe /configure config.xml`). ISO có thư mục `WacServer.WW` là **Office Online Server** (bản chạy trên máy chủ cho SharePoint), không cài lên máy nhân viên.

Symantec Endpoint Protection: gói client là file tự giải nén. Giải nén ra thư mục (7-Zip) rồi khai báo `Sep64.msi` với `args: 'SYMREBOOT=ReallySuppress'`. Gói "All Clients" tải về là bản unmanaged; muốn client báo về SEPM thì chép đè `SyLink.xml` xuất từ SEPM vào thư mục đó, hoặc xuất gói cài managed từ SEPM. Nhận biết đã cài dùng đúng tên `Symantec Endpoint Protection` (không có `*`), để không nhầm với máy chủ "Symantec Endpoint Protection Manager".

## Lưu ý

- **Máy chưa vào domain thì thường không vào được share.** Bước join domain của wizard Cài máy mới (GĐ2) sẽ lo việc này; hiện tại cần map share bằng tài khoản domain trước (`net use`), hoặc cài phần mềm sau khi join.
- **winget thuộc từng tài khoản.** Tool dùng winget của tài khoản đang chạy tool; tài khoản mới đăng nhập lần đầu thường chưa có. Mục **Sửa / cài lại winget** (trang Sửa lỗi, nhóm Phần mềm) đăng ký lại App Installer cho tài khoản đó; không được thì cài từ `<share_root>\Installers\winget\`. Chuẩn bị thư mục này từ trang phát hành của winget-cli trên GitHub (bản mới nhất):
  - `Microsoft.DesktopAppInstaller_8wekyb3d8bbwe.msixbundle`
  - file license `*_License1.xml` (có thì tool cài sẵn cho cả máy, tài khoản đăng nhập sau này cũng có winget)
  - các gói phụ thuộc `.appx` bản x64: `Microsoft.VCLibs.140.00.UWPDesktop_*_x64.appx`, `Microsoft.UI.Xaml.2.8_*_x64.appx` (lấy trong file `DesktopAppInstaller_Dependencies.zip` cùng trang phát hành)
- **Tìm tham số cài im lặng** cho EXE: thử `setup.exe /?`, xem trang của hãng, hoặc tra "<tên phần mềm> silent install". Thử trên máy ảo trước khi đưa vào danh mục.
