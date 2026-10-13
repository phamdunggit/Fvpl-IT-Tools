# Khai báo mục sửa lỗi / tweak bằng YAML

Mỗi mục là một khối trong file `src/fvpl_ittools/data/actions/NN-ten.yaml`. Số `NN` đầu tên file quyết định thứ tự nhóm trong cây (10 mạng, 20 domain, 30 máy in, 40 Windows Update, 50 hệ thống, 60 Office, 90 tuỳ chọn). Thêm mục không cần sửa code.
Khai báo sai thì mục đó bị loại, tool báo lỗi bằng tiếng Việt kèm tên file và số thứ tự. Các mục khác vẫn chạy bình thường.

**Sau khi thêm hoặc sửa thì chạy `.venv\Scripts\python -m pytest`.** Hai test hay bắt lỗi nhất:
- `test_bundled_actions_load_without_errors`: khai báo sai khoá, sai kiểu.
- `test_every_powershell_script_parses`: soát cú pháp mọi script PowerShell bằng parser của PowerShell (không chạy script), ví dụ thiếu ngoặc, `"$bien:"` trong chuỗi.

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

Mục chẩn đoán dùng hàm dựng sẵn và giải thích mã thoát:

```yaml
- id: dom.check_dc
  name: Kiểm tra kết nối với domain
  category: Domain & đăng nhập
  requires_domain: true
  description: >
    Chỉ kiểm tra, không đổi gì...
  apply:
    - powershell: |
        $domain = (Get-CimInstance Win32_ComputerSystem).Domain
        $servers = @(Get-ActiveAdapters | ForEach-Object { $_.Dns } | Select-Object -Unique)
        if (Test-DomainDns $domain $servers) { ... }
        Exit-Checks
      timeout: 180
      messages:
        2: Có mục kiểm tra không đạt, xem các dòng ✖ ở trên
```

## Các khoá của một mục

| Khoá | Bắt buộc | Mặc định | Ý nghĩa |
|---|---|---|---|
| `id` | có | | Dạng `nhom.ten`: chữ thường không dấu, số, `_`. Không được trùng giữa các file. Nhóm đang dùng: `net`, `dom`, `prn`, `wu`, `sys`, `off`, `ui`. |
| `name` | có | | Tên hiện trong danh sách. |
| `category` | có | | Nhóm trong cây (ví dụ `Mạng & Internet`). |
| `page` | | `fixes` | Trang hiện mục: `fixes` (Sửa lỗi), `optimize` (Tối ưu & dọn dẹp), `config` (Cấu hình), `utilities` (Tiện ích, tab "Mục khác"). |
| `risk` | | `safe` | `safe` / `caution` / `advanced` (An toàn / Cẩn thận / Nâng cao). Mục Cẩn thận/Nâng cao sẽ hỏi xác nhận và tạo restore point trước khi chạy. |
| `scope` | | `machine` | `machine`: áp cho cả máy, **không được** ghi HKCU. `user`: áp cho người đang đăng nhập, **chỉ được** ghi HKCU; tool tự đổi sang `HKU\<SID>` khi IT chạy tool bằng tài khoản khác. Script PowerShell của mục `user` dùng `$TargetUserProfile`, `$TargetUserSid` thay cho `$env:USERPROFILE`, `HKCU:`. |
| `admin` | | `true` | Cần quyền admin. Tool không có quyền admin thì mục bị khoá. |
| `requires_domain` | | `false` | Chỉ chạy được khi máy đã vào domain; chưa vào thì mục bị khoá và hiện "Chưa vào domain". |
| `reboot` | | `false` | Cần khởi động lại sau khi chạy (chỉ tính khi mục có thay đổi). |
| `os` | | | `{ min_build: 22000, max_build: 26100 }`. Ví dụ 19045 = Win10 22H2, 22000 = Win11 đầu tiên. |
| `description` | | | Mô tả hiện trong khung chi tiết. Viết cho IT đọc: làm gì, dùng khi nào, ảnh hưởng gì. Test yêu cầu tối thiểu 40 ký tự. |
| `check` | | | `{ registry: { key, name, on_value } }`. Đọc trạng thái hiện tại: giá trị bằng `on_value` thì hiện "Đang bật", ngược lại "Đang tắt". |
| `apply` | có | | Danh sách bước, chạy lần lượt. Một bước lỗi thì dừng mục đó. |
| `undo` | có nếu `risk` khác `safe` | `auto` khi có bước registry, ngược lại `none` | `auto`: trả registry về giá trị đã sao lưu. `none`: không hoàn tác được. Hoặc một danh sách bước hoàn tác. |
| `after` | | | Thao tác làm sau, ví dụ `[restart_explorer]`. Chỉ chạy nếu mục có thay đổi, và chạy **một lần** cho cả lượt dù nhiều mục cùng khai báo. |
| `gpo` | | | `[{ key, name }]`. Nếu một giá trị trong đây có mặt, mục hiện "GPO quản lý" và không chạy. |
| `needs_credential` | | | `domain`. Trước khi chạy, tool hỏi tài khoản domain (tự thêm `DOMAIN\` nếu IT chỉ gõ tên). Script PowerShell dùng biến `$Credential`. Mật khẩu đi qua stdin, bị che trong log và chỉ sống trong lượt chạy đó. Mục loại này phải là Cẩn thận hoặc Nâng cao. |

## Các loại bước

Mỗi bước có đúng **một** trong các khoá sau:

| Loại | Cách viết | Ghi chú |
|---|---|---|
| `cmd` | `- cmd: ipconfig /flushdns` | Chạy bằng `cmd.exe /d /s /c` sau khi `chcp 65001`. Lệnh có sẵn của cmd như `echo` không in được chữ có dấu, chỗ đó dùng PowerShell. Lệnh hỏi Y/N thì trả lời trước bằng `echo n\|`, ví dụ `echo n\| gpupdate /force`. |
| `powershell` | `- powershell: \|` rồi các dòng script | Windows PowerShell 5.1, gặp lỗi là dừng (`$ErrorActionPreference = 'Stop'`), output UTF-8. Mã thoát là mã của lệnh native cuối cùng, gặp lỗi thì là 1; tự đặt được bằng `exit N`. Script dài tối đa khoảng 11.000 ký tự (quá thì tool tự bỏ chú thích và thụt lề). Có sẵn biến và hàm, xem phần dưới. |
| `registry` | `- registry: { key, name, type, value }` | `type`: `DWORD`, `QWORD`, `SZ`, `EXPAND_SZ`, `MULTI_SZ` (danh sách chuỗi), `BINARY` (chuỗi hex `"01 0a ff"` hoặc danh sách số). `name: ""` là giá trị mặc định của khoá. Xoá giá trị thì viết `{ key, name, delete: true }`. Giá trị đã đúng sẵn thì bỏ qua và không ghi nhật ký. Không được ghi thẳng `HKU`. |
| `service` | `- service: { name: Spooler, action: restart }` | `action`: `start` / `stop` / `restart`. Đổi kiểu khởi động làm ở GĐ3. |
| `builtin` | `- builtin: restart_explorer` | Thao tác viết bằng Python. Hiện có: `restart_explorer`, `rebuild_icon_cache` (tắt Explorer, xoá cache icon/thumbnail của người dùng, mở lại). |

Khoá dùng chung cho mọi bước:

| Khoá | Mặc định | Ý nghĩa |
|---|---|---|
| `timeout` | 600 | Số giây tối đa, quá thì dừng lệnh (kill cả cây tiến trình). |
| `ok_codes` | `[0]` | Các mã thoát coi là thành công. |
| `reboot_codes` | `[3010, 1641]` | Các mã thoát nghĩa là thành công nhưng cần khởi động lại. |
| `messages` | | `{ mã: "giải thích" }`. Khi bước lỗi với mã đó, khung log và cột trạng thái hiện lời giải thích thay cho "mã lỗi N". Mã kiểu HRESULT viết dạng hex, ví dụ `0x800F081F: DISM không tìm được nguồn file sạch`. |
| `encoding` | `auto` | Chỉ cho `cmd`/`powershell`. `auto` tự nhận UTF-8 / UTF-16 (như `sfc`) / code page OEM. |

## Biến và hàm dựng sẵn cho PowerShell

Biến, có sẵn trong mọi script:

| Biến | Giá trị |
|---|---|
| `$TargetUserName` | Người đang đăng nhập, dạng `DOMAIN\user` (khác tài khoản chạy tool khi IT dùng "Run as different user"). |
| `$TargetUserSid` | SID của người đó. Registry của họ: `Registry::HKEY_USERS\$TargetUserSid\...` |
| `$TargetUserProfile` | Thư mục profile của họ, ví dụ `C:\Users\nva`. |
| `$ReportDir` | Thư mục `reports` của tool, nơi lưu file báo cáo (gpresult, thông tin máy). |
| `$LogDir` | Thư mục `logs` của tool (ví dụ log MSI). |
| `$ShareRoot` | `share_root` trong site.yaml, rỗng nếu chưa khai báo. Ví dụ nguồn .NET 3.5 offline: `$ShareRoot\Sources\sxs\<build>`. |
| `$Credential` | Chỉ có ở mục `needs_credential`. |

Hàm, khai báo trong `src/fvpl_ittools/core/pslib.py`. Tool chỉ thêm chúng vào script nào có gọi tới; nút "Copy lệnh" copy kèm luôn để chạy tay vẫn đúng.

| Hàm | Làm gì |
|---|---|
| `Write-Ok`, `Write-Bad`, `Write-Warn`, `Write-Line` | In dòng `✔` / `✖` / `⚠` / thường (khung log tô màu xanh / đỏ / vàng). `Write-Bad` đếm số lỗi. Ghi thẳng ra stdout nên dùng được trong hàm mà không lẫn vào giá trị trả về. |
| `Exit-Checks` | Thoát với mã 2 nếu đã có `Write-Bad`. Đặt `messages: { 2: ... }` cho bước. |
| `Test-Ping $ip [timeout]`, `Test-Port $ip $port [timeout]` | Trả True/False, có timeout ngắn (1,5–2 giây). |
| `Get-NtpOffset $server` | Số giây giờ máy lệch so với server NTP (DC), hoặc `$null`. |
| `Test-DnsSrv $dnsServer $name` | Hỏi thẳng một DNS server xem có bản ghi SRV không, timeout thật 1,5 giây. |
| `Get-ActiveAdapters` | Card mạng đang kết nối (bỏ card ảo nội bộ): `Name, Description, Mac, Wireless, Speed, Physical, IPv4, Gateway, Dns, Dhcp`. |
| `Test-DomainDns $domain $servers` | In ✔/✖ cho từng DNS server: có tìm được DC không. Trả True nếu ít nhất một server tìm được. |
| `Find-DomainController $domain` | IP của một DC đang trả lời LDAP, hoặc `$null` (đã in ✖ lý do). |
| `Test-DomainController $ip` | In ✔/✖ cho các cổng 53/88/389/445 và độ lệch giờ so với DC. |

## Gói sửa nhanh

Khai báo trong `src/fvpl_ittools/data/packs.yaml`, hiện thành nút trên đầu trang Sửa lỗi. Bấm thì tool liệt kê các bước (kèm bước nào sẽ bị bỏ qua và vì sao), hỏi xác nhận rồi chạy lần lượt; **một mục lỗi thì dừng**, mục bị khoá (chưa vào domain, thiếu quyền admin) thì bỏ qua và chạy tiếp.

```yaml
- id: pack.network
  name: Sửa mạng
  description: >
    Các bước nhẹ, không cần khởi động lại...
  actions: [net.flush_dns, net.reset_proxy, net.reset_winhttp_proxy, net.renew_ip, net.diagnose]
```

`actions` cần ít nhất 2 mục, không lặp, và mọi id phải có thật (mục khai báo sai bị loại thì gói nhắc tới nó cũng bị loại). Test `test_bundled_packs_load_without_errors` kiểm tra file này.

Hai khoá tuỳ chọn:

| Khoá | Mặc định | Ý nghĩa |
|---|---|---|
| `page` | `fixes` | Trang hiện nút gói: `fixes` (Sửa lỗi) hoặc `config` (Cấu hình, nhãn "Làm cả gói"). |
| `stop_on_error` | `true` | `false`: một mục lỗi thì vẫn làm tiếp mục sau. Dùng cho gói cấu hình, ví dụ `pack.standard_config` (lỗi cài .NET 3.5 không nên chặn việc tạo restore point). |

## Bẫy hay gặp

- **Đừng đặt tên khoá là `on`, `off`, `yes`, `no`.** YAML hiểu chúng là true/false. Đây là lý do khoá trạng thái tên là `on_value`.
- **Đường dẫn có `\`** thì để không ngoặc hoặc trong ngoặc đơn `'...'`. Ngoặc kép `"..."` làm YAML hiểu `\S`, `\n`... là ký tự đặc biệt. Trong khối `powershell: |` thì `\` giữ nguyên, không cần lo.
- **`messages` có dấu `:` trong lời giải thích** thì viết dạng nhiều dòng (`messages:` xuống dòng rồi `2: ...`), đừng viết `{ 2: a: b }`.
- **Mục `scope: machine` mà ghi HKCU** thì bị loại. Nếu thiết lập là của người dùng, khai báo `scope: user`.
- **Không dò chữ trong output** để quyết định thành công hay lỗi, vì Windows tiếng Việt và tiếng Anh in khác nhau. Dùng mã thoát (`ok_codes`), hoặc cho script PowerShell `exit` với mã phù hợp. Dấu ✔/✖ đầu dòng chỉ để tô màu.
- **Dùng SID hoặc ID nhóm thay cho tên hiển thị** (ví dụ nhóm Administrators là `S-1-5-32-544`), vì tên bị dịch theo ngôn ngữ Windows.
- **Không dùng cmdlet phải nạp module chậm** như `Get-NetAdapter`, `Get-NetIPConfiguration`, `Get-NetIPInterface`, `Get-PhysicalDisk`, `Get-MpComputerStatus`, `Resolve-DnsName`: có máy mất 10–30 giây chỉ để nạp module. Dùng `Get-CimInstance` thẳng (`Win32_NetworkAdapter`, `MSFT_PhysicalDisk` trong `root/Microsoft/Windows/Storage`...) hoặc hàm dựng sẵn ở trên.
- **PowerShell: `"$bien:"` trong chuỗi ngoặc kép là lỗi cú pháp** (PowerShell hiểu là `$scope:tên`). Viết `"$($bien):"` hoặc `"${bien}:"`.
- **PowerShell: `Write-Output` trong hàm thành giá trị trả về.** Hàm vừa in vừa trả True/False thì in bằng `Write-Line` / `Write-Ok`...
- **PowerShell: hashtable `[ordered]` lấy số làm vị trí**, `$h[53]` là phần tử thứ 53 chứ không phải khoá 53. Khoá là số thì dùng `@{ }` thường.
- **Lệnh dừng dịch vụ rồi làm gì đó** thì chạy lại dịch vụ trong `finally`, để lỗi giữa chừng không bỏ dịch vụ ở trạng thái dừng (xem `prn.clear_queue`, `wu.reset`).
