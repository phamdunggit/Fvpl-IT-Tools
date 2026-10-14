# Bàn giao: đọc file này trước khi làm tiếp

Cập nhật lần cuối: 14/10/2026, sau khi xong giao diện mới (P0 → P3) và các tiện ích GĐ4, thêm gỡ phần mềm, sao lưu trước khi cài lại Windows, key bản quyền.

## Trạng thái

| | |
|---|---|
| Giai đoạn | **GĐ1, GĐ2 (wizard Cài máy mới), phần lớn GĐ3 xong phần code.** Còn chạy thử các mục đổi hệ thống bằng quyền admin trên VM (danh sách bên dưới) rồi mới coi là xong |
| Nhánh | Code mới làm trên `featured`. Chỉ merge về `main` khi được duyệt |
| Phiên bản | 0.2.0, xem [CHANGELOG.md](../CHANGELOG.md) (trang Phần mềm nằm ở mục "Chưa phát hành") |
| Test | 395 test pytest, tất cả đều qua (khoảng 1,5 phút) |
| Bản exe | `python packaging\build.py`: thư mục 64MB, zip 27MB. `--test` chạy selftest trên exe, gồm cả đọc thông tin máy |

Đã có:
- **Khung giao diện** (`ui/main_window.py`): thanh trên (ô tìm, thông tin máy, nút Cơ bản / Chuyên gia), sidebar có icon (`ui/icons.py`) + ô kho bộ cài, thanh trạng thái, ngăn kéo log. Mọi chỗ mở trang đi qua `MainWindow.navigate(đích)` (`page:`, `fixes:<nhóm>`, `action:`, `pack:`, `app:`, `tab:<trang>:<tab>`, `shortcut:`, `store`). Chế độ lưu ở `prefs.json` (`ui_mode`); trang nào có `set_mode` thì được gọi khi đổi chế độ.
- **Trang chủ** (`ui/pages/home.py`): ô tình huống (`TILES`), khung Tình trạng máy (`core/health.py`, lấy dữ liệu trang Thông tin máy).
- **Báo bản mới**: `core/updates.py` đọc `version.json` (thư mục `release_dir` trong site.yaml, mặc định `<kho>/ITTools`) ở thread nền lúc mở cửa sổ; `deploy.py share` ghi file đó. **Ký số**: `build.py` ký khi có biến `FVPL_SIGN_THUMBPRINT` (docs/KY-SO.md). **Sửa PATH**: `core/envpath.py` + `ui/pages/path_dialog.py`, ghi bằng mục registry có hoàn tác, builtin `notify_environment`. **Sao lưu dữ liệu** (cài lại Windows / chuyển máy): `core/migrate.py` (quét thư mục theo User Shell Folders của người dùng được chọn, `root_folders()` gợi ý thư mục ở gốc ổ C, `extra_spec()` cho thư mục bất kỳ (`Khac\C-<tên>-<mã>` cho ngắn), Wi-Fi qua netsh trong thư mục tạm ngắn, driver qua `core/drivers.py`; `pick_target()` chọn nơi lưu ngoài ổ Windows, `find_backups()` tìm `<ổ>:\FVPL-SaoLuu` trên mọi ổ; mỗi mục một action `move.*`, `manifest.json` ghi máy in + phần mềm, `match_software` khớp tên với `apps.yaml`) + `ui/pages/migrate_panel.py` (tab Sao lưu dữ liệu trong Tiện ích, signal `software_wanted` → trang Cài phần mềm). Danh sách người dùng: `session.user_profiles()`.
- **Sửa lỗi theo tình huống**: `data/scenarios.yaml` + script chỉ đọc `data/scripts/scenarios/*.ps1` (gọi `Add-Finding`), `core/scenarios.py` (nạp, chạy kiểm tra, `plan()` chọn mục sửa), màn hình `ui/pages/scenario.py` (đích `guide:<id>`, không có trên sidebar). Gửi cho IT: `core/support_report.py`.
- **Tìm Ctrl+K**: `core/search.py` (bỏ dấu, chấm điểm), `MainWindow.build_index()` gom trang, mục YAML (khoá `keywords`), gói, công cụ (`TOOLS`), Mở nhanh, phần mềm; bảng tìm `ui/components/command_palette.py`.
- Trang **Thông tin máy** (trước là Tổng quan): hệ điều hành, kích hoạt, phần cứng, mạng (DNS có trỏ về DC không), bảo mật; copy chữ, xuất HTML; **Lưu kiểm kê** (`core/assets.py`): `Inventory\<máy>.json` cạnh tool trên USB / SSD và file tổng hợp `KiemKe.xlsx` (tool tự ghi file .xlsx, không cần thư viện).
- Trang **Sửa lỗi**: các mục mạng, domain, Windows Update, hệ thống, Office và 4 gói sửa nhanh.
- Trang **Máy in**: danh sách máy in (kể cả share của người đang đăng nhập), gỡ máy in / driver, in thử; thêm máy in qua IP (driver từ file .inf) và máy in share; tab Sửa lỗi có các mục share máy in Win11 ↔ Win10 (`printers/`, `30-printers.yaml`).
- Trang **Cấu hình**: 1 mục mẫu (Hiện đuôi file). Trang **Tiện ích**: mở nhanh 30 công cụ quản trị, công cụ mạng, Event log (`core/eventlog.py`), Công cụ khác (`ui/pages/system_tools.py`: sao lưu / cài lại driver `core/drivers.py`, HOSTS, file bị khoá `core/lockedfiles.py`, Wi-Fi `core/wifi.py`), LAPS & BitLocker.
- Trang **Phần mềm**: banner kho bộ cài + **Chọn kho…** (`core/prefs.py`, `AppContext.use_software_root`), thẻ chọn bản Office (`choice` trong `apps.yaml`, `ui/components/choice.py`; gỡ Office Click-to-Run trước khi cài nếu IT tick), danh mục `apps.yaml` (kho hoặc bản đóng gói), profile phòng ban, đánh dấu đã cài, cài lần lượt qua winget / MSI / EXE / portable, khung tiến độ khi cài. Cách khai báo: [SOFTWARE.md](SOFTWARE.md).
- **Tiến độ:** `executor._run_batch` phát `progress.BatchStarted` / `ItemUpdate` qua `RunContext.report` (→ signal `RunController.progress`); `RunContext.output` đọc phần trăm từ output. Giao diện: `ui/components/progress_panel.py` (gọi `watch(title)` ngay trước `controller.run`), thanh nhỏ trong khung log. Dừng mềm: `RunController.stop_after_current()`.
- Trang **Cài máy mới**: wizard 8 bước (`ui/pages/newpc.py`, `newpc/`): kiểm tra trước, thông tin máy (mã phòng lưu vào site.yaml, gợi ý tên bằng AD), đổi tên + join, sau khởi động lại, phần mềm, cấu hình chuẩn, Windows Update, báo cáo. Tiến độ lưu ở `newpc-wizard.json` trong thư mục dữ liệu; bước 2 chép tool vào `%ProgramData%\FVPL-ITTools\app` và hẹn tác vụ `FVPL-ITTools-TiepTucCaiMay` mở lại tool (`--resume`) khi admin đăng nhập.
- Trang **Tối ưu & dọn dẹp** (GĐ3): dọn rác có quét trước (`cleanup/junk.py`), chương trình khởi động cùng Windows (`cleanup/startup.py`), tối ưu / quyền riêng tư / nguồn điện / gỡ app cài sẵn (`75-optimize.yaml`).
- **Gỡ phần mềm** (tab ở trang Tối ưu): `software/uninstall.py` đọc khoá Uninstall (HKLM 64 / WOW6432Node, HKU của người đang đăng nhập), `plan()` chọn lệnh gỡ, `uninstall_action()` sinh mục `soft.uninstall_<hash>`: chạy trình gỡ rồi chờ khoá biến mất (không tin mã thoát), phần mềm cài riêng cho người dùng mà tool chạy bằng tài khoản khác thì chạy trình gỡ qua tác vụ Interactive của người dùng. Danh sách nên gỡ / giữ / tham số im lặng: `data/uninstall.yaml` + `<kho>\config\uninstall.yaml`. Giao diện `ui/pages/uninstall_panel.py`; Trang chủ có dòng "Có phần mềm nên gỡ" (`MainWindow.check_unwanted`).
- **Key bản quyền** (tab ở Tiện ích): `core/licenses.py` (file `license-keys.json`: `load` / `save` ghi file tạm rồi thay, đăng ký mọi key với `log.register_secret`; `activation_action` dòng đầu script là chú thích vì log chỉ in dòng đầu, key ở biến `$ProductKey`, output slmgr / ospp được thay key trước khi in; `record_usage` ghi máy đã dùng) + `ui/pages/licenses_panel.py` (đọc lại file ngay trước mỗi lần sửa để không ghi đè thay đổi của IT khác trên share). Đường dẫn file IT chọn lưu ở `prefs.json` (`license_file`). File key trong `.gitignore`: chạy từ mã nguồn thì file nằm ở gốc repo.
- Trang **Nhật ký**: hoàn tác thay đổi registry.

## Bắt đầu

```powershell
py -3.13 -m venv .venv
.venv\Scripts\python -m pip install -e .[dev]
.venv\Scripts\python -m pytest
.venv\Scripts\python -m fvpl_ittools --no-elevate
```

Chi tiết chạy, build, selftest: [README.md](../README.md). Cách khai báo mục, gói, biến và hàm PowerShell dựng sẵn: [ACTIONS.md](ACTIONS.md). Kế hoạch tổng: [PLAN.md](../PLAN.md). Hướng dẫn triển khai GPO / LAPS / BitLocker cho công ty (không phải code): [BITLOCKER-LAPS-GPO.md](BITLOCKER-LAPS-GPO.md).

## Quy tắc khi làm repo này

1. **Làm trên nhánh `featured`.** Không commit thẳng lên `main`, không tự merge.
2. **Repo để public.** Tên domain, server, đường dẫn share, OU, tên máy thật **không** được nằm trong code hay docs. Thông tin thật để trong `site.yaml` (gitignore). Trong docs viết `<domain>`, `<server>`. Trước khi commit, tìm tên nội bộ trong các file sắp commit (`git diff --cached | grep -i <tên domain>`...). Ảnh chụp selftest có tên máy, domain, serial thật: không commit.
3. **Máy dev là máy làm việc thật.** Không chạy thử các mục làm đổi hệ thống trên máy này. Mục chỉ đọc (Chẩn đoán mạng, Liệt kê máy in, trang Tổng quan) chạy được. Test registry chỉ dùng khoá tạm `HKCU\Software\FVPL-ITTools-Test`. Explorer được giả lập trong test (fixture `fake_explorer`). Muốn chạy thật thì dùng máy ảo.
4. **Thêm mục mới bằng YAML** ([ACTIONS.md](ACTIONS.md)), chỉ viết Python khi YAML không làm được. Khi viết Python thì thêm vào `BUILTIN_NAMES` (model.py) và `BUILTINS` (executor.py); có test kiểm tra hai danh sách này khớp nhau.
5. **Script PowerShell dùng `Get-CimInstance` và .NET, không dùng cmdlet phải nạp module** (`Get-NetAdapter`, `Get-PhysicalDisk`...). Hàm dùng chung đặt trong `core/pslib.py`.

## Một mục chạy như thế nào

```
ActionsPage (bấm Chạy, hoặc nút gói sửa nhanh)
  → hỏi xác nhận nếu có mục Cẩn thận/Nâng cao; hỏi tài khoản nếu có mục needs_credential
  → RunController.run(actions, credential, stop_on_error)   ui/controller.py, chạy ở thread nền
    → executor.run_batch()                                   core/executor.py
        đăng ký mật khẩu để che trong log (quên ngay khi xong lượt)
        blocked_reason()   sai bản Windows / chưa vào domain / thiếu quyền admin / GPO quản lý → bỏ qua
        restore point      nếu có mục Cẩn thận/Nâng cao và đang có quyền admin
        run_action() từng mục; gói sửa nhanh: một mục lỗi thì bỏ các mục sau
          cmd                → core/shell.py run_cmd
          powershell/service → core/shell.py run_powershell: thêm biến ($TargetUser*, $ReportDir),
                               thêm hàm dựng sẵn nếu script có dùng (core/pslib.py),
                               chạy bằng -Command + đoạn mồi giải mã base64, tài khoản qua stdin
          registry           → core/registry.py, lưu trước/sau vào core/journal.py
          builtin            → executor.BUILTINS
        lỗi thì đổi mã thoát thành lời giải thích (khoá messages)
        việc làm sau (after) chạy một lần cho cả lượt
  ← LogEvent qua Qt signal → khung log (dòng ✔/✖/⚠ tô màu); BatchResult → cột Trạng thái, hỏi restart
```

Trang Tổng quan không đi qua executor: `ui/pages/overview.py` mở 4 thread, mỗi thread chạy một script trong `data/scripts/inventory/` (`core/inventory.py` ghép `common.ps1` + hàm dựng sẵn + phần đó), nhận JSON, dựng các mục rồi vẽ bằng HTML trong `QTextBrowser`.

## Chưa kiểm chứng: chạy trên máy ảo bằng quyền admin

Phiên phát triển không có quyền admin, và máy dev là máy thật nên các mục đổi hệ thống chỉ mới được soát cú pháp và test giả lập. Cần một VM Win11 (và một VM Win10 22H2) **đã join domain test**, có snapshot để quay lại. Mở bản `dist\FVPL-ITTools-v0.2.0.zip`, bấm Yes ở UAC.

Từ GĐ0, vẫn còn:
- [ ] Restore point thật được tạo khi chạy mục Cẩn thận; lần thứ hai trong 24 giờ báo đúng.
- [ ] Máy ảo sạch chưa cài Python mở được exe.
- [ ] Run as different user: thanh trên cùng báo "Chạy bằng … · áp cho …", "Hiện đuôi file" và "Xoá proxy của người dùng" đổi registry của người dùng chứ không phải tài khoản IT.

Các mục của GĐ1, chỗ cần để ý:
- [ ] **Tổng quan khi có quyền admin:** BitLocker đọc qua `Win32_EncryptableVolume` + `GetConversionStatus`, TPM qua `Win32_Tpm` (`IsEnabled_InitialValue`, `IsActivated_InitialValue`). Máy dev không có admin nên chưa thấy hai dòng này chạy thật.
- [ ] **Chẩn đoán mạng / Kiểm tra kết nối với domain** khi đang ở mạng công ty: DNS tìm được DC, cổng 53/88/389/445, độ lệch giờ NTP. Máy dev đang ở Wi-Fi ngoài nên mới thấy nhánh "DNS không trỏ về DC".
- [ ] **Sửa lỗi trust relationship:** làm hỏng trust trên VM (khôi phục snapshot cũ hơn 30 ngày, hoặc reset computer account trên DC), đăng nhập admin cục bộ, chạy mục, nhập tài khoản join.
- [ ] **Đồng bộ giờ:** mã thoát của `w32tm /resync /rediscover` khi DC không trả lời có đúng `0x800705B4` không.
- [ ] **Cập nhật Group Policy:** `echo n| gpupdate /force` không bị treo khi có policy đòi đăng xuất.
- [ ] **Báo cáo GPO:** `gpresult /user <người dùng>` khi chạy bằng tài khoản IT khác; file mở bằng trình duyệt của người dùng (qua `explorer.exe`).
- [ ] **Reset Winsock và TCP/IP:** `netsh int ip reset` hay trả mã 1 kèm vài dòng "Access is denied" dù phần lớn đã reset; đang coi mã 1 là thành công. Kiểm tra có trường hợp mã 1 là lỗi thật không.
- [ ] **Khởi động lại card mạng:** `Win32_NetworkAdapter.Disable/Enable` trả 0, card bật lại được.
- [ ] **Xoá proxy của người dùng:** sau khi xoá `DefaultConnectionSettings`, Settings → Proxy hiện "Automatically detect settings", trình duyệt vào web được.
- [ ] **Xoá lệnh in bị kẹt:** tạo lệnh in kẹt (máy in offline), chạy mục, hàng đợi trống, Spooler chạy lại.
- [ ] **Reset Windows Update:** đổi tên được `SoftwareDistribution` và `catroot2` khi Windows tự bật lại dịch vụ; sau đó quét cập nhật được.
- [ ] **DISM + SFC:** **chưa rõ mã thoát của `sfc /scannow`** khi tìm thấy và sửa được file hỏng (đang coi chỉ 0 là thành công). Nếu sfc trả mã khác 0 khi đã sửa xong thì thêm vào `ok_codes` kèm `messages`. DISM trên máy dùng WSUS hay lỗi `0x800F081F`.
- [ ] **Kiểm tra ổ đĩa / Hẹn sửa ổ đĩa:** mã thoát của `chkdsk /scan`; `fsutil dirty set` làm Windows chạy chkdsk lúc khởi động.
- [ ] **Xây lại cache icon:** Explorer tắt, file cache bị xoá, Explorer tự mở lại. Khi Windows không tự mở lại mà tool có quyền admin, tool tạo tác vụ chạy một lần để mở Explorer bằng tài khoản người dùng (`_START_EXPLORER_AS_USER` trong executor.py), đường này chưa chạy thật lần nào.
- [ ] **Sửa mất âm thanh:** `Restart-Service AudioEndpointBuilder -Force` rồi `Start-Service Audiosrv`.
- [ ] **Sửa Office:** cần máy có Office Click-to-Run. `OfficeClickToRun.exe` giao việc cho dịch vụ rồi thoát ngay; kiểm tra lấy đúng `Platform`, `ClientCulture` từ registry và Office được sửa thật.
- [ ] **5 gói sửa nhanh:** dừng đúng khi một bước lỗi; bước bị khoá thì bỏ qua và chạy tiếp.

Trang Phần mềm (GĐ2). Danh mục và phát hiện đã cài đã chạy thật trên máy dev (chỉ đọc); **chưa cài thật ứng dụng nào**:
- [ ] **winget:** cài 2–3 ứng dụng nhỏ (7-Zip, Notepad++) trên VM; ứng dụng đã có thì báo xong chứ không báo lỗi (`0x8A15002B`, `0x8A150061`). winget lần đầu trên máy mới có thể hỏi điều khoản nguồn dù đã có `--accept-source-agreements`.
- [ ] **MSI từ share:** log MSI xuất hiện trong thư mục logs; mã 3010 làm tool hỏi khởi động lại; thử 1618 bằng cách chạy một bộ cài MSI khác cùng lúc.
- [ ] **EXE từ share:** `ExitCode` đọc được sau `WaitForExit` (đã giữ `$process.Handle` để tránh lỗi PowerShell trả ExitCode rỗng).
- [ ] **Portable (UniKey):** chép vào Program Files, có shortcut Start Menu và Startup chung, đăng nhập tài khoản khác thấy UniKey tự chạy.
- [ ] **Office bằng ODT:** cần file `setup.exe` và `config.xml` thật trên share; xem có bị timeout 3600 giây không.
- [ ] **Office 2016 từ ISO trên máy Dell / Lenovo mới có Microsoft 365 cài sẵn:** trang Phần mềm báo "Không cài được: máy đang có Microsoft 365…"; mục **Gỡ Microsoft 365 / Office cài sẵn** gỡ im lặng thật không (`DisplayLevel=False` thêm vào lệnh gỡ trong Programs and Features), chờ đúng tới khi mục biến mất; khởi động lại rồi cài Office 2016 được. Đã chạy thật trên máy dev (chỉ đọc): máy có Office 2013 nên Office 2016 / 2010 bị khoá đúng.
- [ ] **Kích hoạt Office (MAK):** cài khi chưa có Internet rồi chạy mục Kích hoạt Office; Office 2010 đọc trạng thái qua `OfficeSoftwareProtectionProduct`. Phần đọc trạng thái đã chạy thật trên máy dev (Office 2013 MAK, đã kích hoạt).
- [ ] **Run as different user:** ứng dụng `scope: user` (Zalo) bị khoá; phần mềm cài riêng cho người dùng (HKU\<SID>\…\Uninstall) vẫn được nhận là đã cài.
- [ ] **Sửa / cài lại winget:** tài khoản mới đăng nhập lần đầu chưa có winget → mục đăng ký lại được; xoá App Installer của tài khoản (`Get-AppxPackage Microsoft.DesktopAppInstaller | Remove-AppxPackage`) → mục cài lại từ `<share>\Installers\winget\`. Phần kiểm tra `winget --version` đã chạy thật trên máy dev.
- [ ] **Máy chưa vào domain:** trang báo "Không vào được share", danh mục quay về bản đóng gói; không bị treo lâu khi share không trả lời (quét chạy ở thread nền, nhưng `os.path.isdir` trên UNC có thể chờ 20–60 giây).

Wizard Cài máy mới. "Gợi ý tên" (hỏi AD, máy đã join) và tạo báo cáo đã chạy thật trên máy dev (chỉ đọc); **chưa join / đổi tên / hẹn tác vụ thật**. Cần VM chưa join, bản exe trên USB, có `site.yaml` (`domain`, `netbios_domain`, `computer_ou`, `it_admins_group`):
- [ ] **Gợi ý tên khi máy chưa join:** LDAP bằng tài khoản join (`DirectoryEntry` với user/mật khẩu) qua DNS đang trỏ về DC; sai mật khẩu thì báo rõ và hỏi lại.
- [ ] **Join + đổi tên một lần khởi động lại**, vào đúng OU; thử cả tên đã có trong AD bằng tài khoản join thường (phải ra gợi ý KB5020276) và OU sai. Xem lời báo của `Add-Computer` có mã lỗi không (đang dò theo chữ tiếng Anh).
- [ ] **Chạy tiếp sau khởi động lại:** rút USB, khởi động lại, đăng nhập bằng Domain Admin: tác vụ mở bản chép trong ProgramData, không hỏi UAC, vào thẳng bước 3. Đăng nhập bằng tài khoản không phải admin thì tác vụ không chạy (đúng ý), mở tool bằng tay vẫn thấy wizard dở. `icacls` đã khoá thư mục (Users chỉ đọc).
- [ ] **Bước 3:** secure channel, gpupdate, thêm `it_admins_group` vào Administrators bằng ADSI (đã có sẵn thì báo đã có).
- [ ] **Bản SSD:** bắt đầu từ SSD, sau khởi động lại SSD vẫn cắm cùng ký tự ổ → trang Phần mềm dùng kho SOFT trên SSD (`origin` trong newpc-wizard.json). Cắm khác ký tự ổ thì quay về share.
- [ ] **Định dạng vùng vi-VN:** `rundll32 shell32.dll,Control_RunDLL intl.cpl,,/f:"x.xml"` có chờ xong mới thoát không; tài khoản mới tạo sau đó nhận vi-VN; màn hình đăng nhập (`HKU\.DEFAULT`) đổi theo.
- [ ] **Báo cáo:** mở được bằng trình duyệt của người dùng; có bản trong `Reports\` trên USB. Kết thúc wizard thì tác vụ mở lại bị xoá.
- [ ] **Mẫu:** lưu mẫu từ bản exe trên USB (file `wizard-templates.json` nằm cạnh site.yaml trên USB, được chép theo vào ProgramData ở bước 2); máy sau chọn mẫu → bước 4 tick sẵn profile và bản Office.

Cập nhật driver, BIOS của hãng (`drv.vendor_update`). Máy dev là Dell nhưng chưa có Dell Command | Update và không có quyền admin nên **chưa chạy lần nào**:
- [ ] **Dell chưa có DCU:** winget cài `Dell.CommandUpdate.Universal`, rồi `dcu-cli /applyUpdates` chạy, có dòng tiến độ trong khung log, log ở thư mục logs. Mã 1 → tool hỏi khởi động lại; 500 → báo đã mới nhất. Máy có BitLocker: BIOS cập nhật được nhờ `-autoSuspendBitLocker=enable`.
- [ ] **Lenovo ThinkPad / ThinkCentre:** winget cài `Lenovo.SystemUpdate`; `tvsu.exe /CM -search R -action INSTALL -includerebootpackages 3 -nolicense -noreboot -noicon` có hiện cửa sổ / hỏi gì không; tool có chờ đúng tới khi `tvsukernel.exe` xong; mã thoát khi không có gì để cài.
- [ ] Máy hãng khác: bước 6 của wizard chỉ chạy Windows Update.

Trang Cài máy mới, bước Kiểm tra trước. Đã chạy thật trên máy dev (máy đã join, đang ở Wi-Fi ngoài nên DNS không trỏ về DC):
- [ ] VM **chưa join**, có `site.yaml` khai báo `domain`, cắm mạng công ty: DNS tìm được DC, DC trả lời LDAP, đo được giờ lệch.
- [ ] Chỉnh giờ VM lệch 10 phút: dòng giờ báo ✖, nút Đồng bộ giờ chạy rồi tự kiểm tra lại.
- [ ] Laptop rút sạc: dòng Nguồn điện báo ⚠ (đọc bằng `GetSystemPowerStatus`).
- [ ] Máy vừa cài cập nhật chưa khởi động lại: dòng "Chờ khởi động lại" báo ⚠.

Trang Cấu hình (mục mới). Trạng thái bật/tắt đã đọc đúng trên máy dev; **chưa đổi thật mục nào**:
- [ ] Gói "Cấu hình chuẩn máy mới" trên VM mới cài: múi giờ, Fast Startup (Control Panel → Power Options → "Turn on fast startup" bỏ tick), This PC, .NET 3.5, restore point mới trong `rstrui`.
- [ ] .NET 3.5 cả hai đường: có `Sources\sxs\<build>` trên share, và không có (tải từ Windows Update; máy WSUS báo `0x800F0954` kèm hướng dẫn).
- [ ] Restore point tạo được ngay cả khi vừa tạo một điểm trong 24 giờ (mục tạm đặt `SystemRestorePointCreationFrequency = 0` rồi trả lại).
- [ ] Menu chuột phải kiểu cũ: bật rồi Hoàn tác, menu Win11 quay lại (hoàn tác xoá cả khoá CLSID, không chỉ giá trị).
- [ ] End task, căn trái taskbar, hiện file ẩn: có hiệu lực sau khi Explorer khởi động lại; Run as different user thì đổi đúng người dùng.

Trang Tối ưu & dọn dẹp (GĐ3). Quét rác, danh sách khởi động, liệt kê app cài sẵn đã chạy thật trên máy dev (chỉ đọc); **chưa xoá / đổi thật gì**:
- [ ] **Dọn rác** bằng quyền admin trên VM có rác thật: Temp, SoftwareDistribution\Download (dịch vụ Windows Update dừng rồi chạy lại), dump. Dung lượng sau khi dọn khớp với số tool báo.
- [ ] **Windows.old** (VM vừa nâng cấp Windows) và **Delivery Optimization**: `cleanmgr /sagerun:4242` chạy xong, tool xoá lại thiết lập `StateFlags4242`. Xem cleanmgr có hiện cửa sổ chờ người bấm không.
- [ ] **Thùng rác**: chỉ xoá của người đang đăng nhập (`$Recycle.Bin\<SID>` trên mọi ổ cứng), Explorer hiện thùng rác trống.
- [ ] **Khởi động cùng Windows**: tắt một mục rồi đăng xuất / đăng nhập, mục không chạy; Task Manager cũng hiện Disabled; hoàn tác ở trang Nhật ký thì bật lại.
- [ ] **Task khởi động** (đọc đã chạy thật trên máy dev, không quyền admin thấy 4 task): bằng quyền admin thấy thêm task của Edge / Google Update; tắt một task (COM `Enabled = false`) rồi Task Scheduler hiện Disabled; bật lại được.
- [ ] **Mục tối ưu mới:** hiệu ứng hình ảnh có hiệu lực sau khi đăng xuất / đăng nhập, hoàn tác về như cũ; dịch vụ edgeupdate / gupdate sang Manual mà Edge, Chrome vẫn tự cập nhật (qua task); cắm thiết bị mới (chuột, tai nghe) không tự cài app của hãng sau khi bật mục chặn app đồng hành.
- [ ] **Tối ưu**: gói "Tắt quảng cáo và theo dõi" rồi xem Start, Settings, taskbar; Widgets tắt bằng policy `Dsh\AllowNewsAndInterests`; power plan High performance trên laptop Modern Standby (có thể Windows không cho).
- [ ] **Gỡ app cài sẵn**: chạy "Liệt kê" rồi "Gỡ" trên VM; tài khoản mới tạo sau đó không bị cài lại; các app trong danh sách giữ vẫn còn.

Trang Máy in. Danh sách máy in và mục "Kiểm tra share máy in" đã chạy thật trên máy dev (chỉ đọc); **chưa thêm / gỡ / đổi thật gì**. Cần một VM Win11 24H2+ share máy in (máy in ảo cũng được, ví dụ "Generic / Text Only" cổng FILE:) và một VM Win10 22H2 kết nối tới:
- [ ] **Win10 → máy in share trên Win11:** trước khi sửa lỗi gì thì ghi lại mã lỗi; "Máy chia sẻ máy in: cho máy khác kết nối vào" trên Win11 (`RpcProtocols = 7`, firewall) rồi Win10 kết nối được. Xem các luật firewall nào được bật (luật gộp Private + Public).
- [ ] **Win11 → máy in share trên Win10:** "Máy kết nối máy in share: dùng Named Pipes" trên Win11 rồi kết nối được; kiểm tra sau đó Win11 này vẫn kết nối được máy in share trên một Win11 khác đã chạy mục máy chia sẻ.
- [ ] **0x0000011b:** chỉ thử nếu gặp; xem `RpcAuthnLevelPrivacyEnabled = 0` bây giờ còn tác dụng không (Microsoft vẫn ghi trong tài liệu 02/2026).
- [ ] **Thêm máy in share** khi tool chạy bằng tài khoản IT (Run as different user): driver được cài, `printui /ga` tạo khoá `HKLM\...\Print\Connections\,,máy,tên`, người dùng thấy máy in sau khi khởi động lại Spooler hay phải đăng nhập lại. Khi kết nối lỗi, mã lỗi lấy được từ `error_Code` hay chỉ có trong chữ của lỗi.
- [ ] **Thêm máy in qua IP:** driver có sẵn (Microsoft IPP Class Driver), và driver từ file .inf của hãng (`pnputil /add-driver` rồi `Add-PrinterDriver -Name` đúng tên model); mã thoát của pnputil khi driver đã có sẵn.
- [ ] **Gỡ máy in:** máy in IP (cổng TCP/IP bị xoá khi không còn dùng), gỡ cả driver (`-RemoveFromDriverStore` trên Win10 có không); máy in share của cả máy (`printui /gd`); máy in share của người dùng khi tool chạy bằng tài khoản IT (tác vụ chạy dưới tên họ, người đó phải đang đăng nhập).
- [ ] **In trang thử** và **Mở hàng đợi** với máy in thật.

Kiểm kê. Đã dựng `KiemKe.xlsx` từ dữ liệu thật của máy dev và mở bằng Excel (ẩn, chỉ đọc): đủ 25 cột, số là số, có lọc, cố định dòng tiêu đề, ô chữ bắt đầu bằng `=` không thành công thức. Còn:
- [ ] Lưu từ bản exe chạy trên USB: thư mục `Inventory\` nằm trên USB; chạy từ bản chép trong ProgramData (sau khi wizard khởi động lại) thì lưu sang ổ lúc bắt đầu nếu còn cắm, không thì vào thư mục dữ liệu trên máy.
- [ ] Đang mở `KiemKe.xlsx` trong Excel rồi bấm Lưu kiểm kê: JSON vẫn lưu, tool báo đóng file rồi lưu lại.

LAPS và BitLocker (cần làm GPO theo [BITLOCKER-LAPS-GPO.md](BITLOCKER-LAPS-GPO.md) trên domain test trước). Tra cứu đã chạy thật trên máy dev (chỉ đọc): máy chưa có LAPS → báo chưa có mật khẩu; chưa có khoá BitLocker → danh sách trống:
- [ ] **Tab LAPS & BitLocker:** tra mật khẩu LAPS bằng Domain Admins và bằng tài khoản thuộc nhóm giải mã (mật khẩu mã hoá); tài khoản không quyền → báo không được giải mã; "Dùng tài khoản khác" khi máy IT chưa vào domain. Bắt đổi mật khẩu rồi chạy Kiểm tra Windows LAPS trên máy đó → mật khẩu mới. Khoá BitLocker: tài khoản thường thấy Key ID nhưng không thấy khoá.
- [ ] **Kiểm tra Windows LAPS:** máy chưa nhận GPO (✖), máy đã nhận (thấy sự kiện 10018), độ dài mật khẩu thấp hơn chính sách cục bộ (10027).
- [ ] **Bật BitLocker:** máy chưa có GPO lưu khoá → từ chối, không đổi gì; có GPO → khoá lên AD (tra được ở tab), khởi động lại không bị hỏi khoá, ổ mã hoá ở nền; Hoàn tác giải mã được. Máy không có TPM / TPM tắt trong BIOS → báo rõ.
- [ ] **Tạm dừng BitLocker** rồi đổi thiết lập BIOS: không bị hỏi khoá lần khởi động đó.

Hai bản USB / SSD:
- [ ] `deploy.py ssd` ra SSD thật, chạy tool từ SSD trên máy chưa vào domain: trang Phần mềm ghi "kho trên ổ mang theo", cài Office từ ISO trên SSD (mount ISO từ ổ USB/SSD).
- [ ] Bản USB: kho là share; máy chưa join thì báo không vào được kho, không treo.

Tiện ích GĐ4. Đã chạy thật trên máy dev (chỉ đọc): Event log (thấy Kernel-Power 41, NETLOGON 5719 kèm gợi ý), tìm chương trình khoá file, xuất mật khẩu Wi-Fi (thư mục tạm bị xoá sau khi đọc). Còn:
- [ ] **Sao lưu driver** bằng quyền admin: thư mục `DriverBackup\<máy>-<ngày>` trên USB có đủ .inf; **cài lại driver** từ thư mục đó trên máy vừa cài lại Windows (mã 3010 → báo cần khởi động lại).
- [ ] **Sửa HOSTS:** bản sao lưu nằm cạnh file gốc, Notepad mở được bằng quyền admin và lưu được.
- [ ] **Kết thúc tiến trình** đang khoá file: chương trình của người dùng khác (cần admin), tiến trình hệ thống bị từ chối và báo rõ.
- [ ] **Sửa PATH** bằng quyền admin: bỏ mục hỏng ở PATH hệ thống, mở cmd mới thấy PATH mới (không cần đăng xuất); Hoàn tác ở trang Nhật ký trả lại giá trị cũ.

Gỡ phần mềm. Đã chạy thật trên máy dev với mục giả trong `HKCU\Software\FVPL-ITTools-Test`: gỡ được, trình gỡ đóng mà mục còn (báo mã 5 sau 15 giây), thiếu file trình gỡ (mã 3), đã gỡ trước đó. Đọc danh sách thật: 142 phần mềm, 100 gỡ im lặng được. Còn:
- [ ] **WPS Office thật** (cài riêng cho người dùng): `uninst.exe /S` gỡ im lặng hết không, có mở trang khảo sát không; tool chạy bằng tài khoản admin khác người đang đăng nhập (đi qua tác vụ Interactive). Sau khi gỡ, file .docx mở bằng Word.
- [ ] **Bấm theo trình gỡ** (ví dụ TeamViewer): cửa sổ gỡ hiện lên, bấm Huỷ → báo "vẫn còn"; gỡ xong → ✔.
- [ ] Gỡ MSI cần khởi động lại (mã 3010) → tool hỏi khởi động lại.

Key bản quyền. Đã chạy thật trên máy dev: Xem trạng thái kích hoạt (không cần admin, đọc đúng Windows Pro MAK và Office 2013 MAK), hàm giải thích mã lỗi. Chưa nhập key thật vào máy nào. Còn:
- [ ] **Kích hoạt Windows bằng key MAK** trên VM (quyền admin): ✔ và cột Đã dùng thêm máy; key sai phiên bản (Pro cho máy Enterprise) → báo 0xC004F050 bằng tiếng Việt; không có mạng → báo không vào được Internet. Log và khung log không có key (chỉ ******).
- [ ] **Kích hoạt Office 2016 / 2013** bằng key trong file (máy đã cài Office bản volume): đúng OSPP.VBS của phiên bản.
- [ ] File key trên share: hai IT cùng thêm key gần như cùng lúc, không mất key của nhau.

Sao lưu dữ liệu. Đã chạy thật trên máy dev (không quyền admin): sao lưu Music, bookmark Chrome / Edge, một thư mục thêm bằng tay vào thư mục tạm; tìm lại bản sao lưu; khôi phục sang hồ sơ giả (Chrome đang mở → báo đóng trình duyệt; file mới hơn ở thư mục gốc được giữ). Xuất Wi-Fi vào đường dẫn dài: đủ 13 mạng, không để lại file tạm (lần đầu netsh cắt đường dẫn > 260 ký tự và ghi nhầm chỗ, đã sửa bằng thư mục tạm ngắn). Còn:
- [ ] **Cài lại Windows thật trên VM**: sao lưu ra ổ D (tự chọn), cài lại chỉ format phân vùng C, đăng nhập lại, tab tự thấy bản sao lưu trên ổ D, khôi phục đủ: Desktop / Documents, thư mục `C:\KeToan`, Wi-Fi (bằng quyền admin, kết nối được không cần gõ mật khẩu), driver (máy chưa có driver mạng).
- [ ] **Sao lưu người dùng khác** (tool chạy bằng admin, chọn người không đăng nhập): đọc được thư mục, đường dẫn mặc định đúng.
- [ ] **Máy cũ chạy bằng quyền admin** (tool mở bằng "Run as administrator", người dùng khác đang đăng nhập): quét đúng thư mục của người đang đăng nhập, không phải của admin; Documents chuyển sang OneDrive thì không tick sẵn.
- [ ] **Sao lưu vài GB ra USB** (FAT32 / exFAT / NTFS): thanh tiến độ, "Dừng sau mục đang chạy"; file > 4 GB trên FAT32 báo lỗi rõ ở mục đó.
- [ ] **Khôi phục trên máy mới** (Win11, người dùng domain mới đăng nhập lần đầu): file vào đúng Desktop / Documents, file mới hơn trên máy mới không bị ghi đè; bookmark Chrome / Edge hiện sau khi mở trình duyệt; chữ ký Outlook hiện trong Outlook. **Chọn sẵn phần mềm** tick đúng các ứng dụng có trong danh mục.

Giao diện mới đợt P0. Đã chạy thử offscreen với dữ liệu giả (chụp ảnh trang Phần mềm, khung tiến độ, thẻ kết quả) và test tự động; chưa cài thật. Còn:
- [ ] **winget có in phần trăm không** khi tool chạy nó (output bị chuyển hướng): cài Chrome / 7-Zip, xem thanh "Đang tải về N%" có chạy không. Không có thì thanh chạy qua lại, tiến độ tổng vẫn đúng theo số mục.
- [ ] **Gỡ trước khi cài** trên máy Dell / Lenovo có Microsoft 365 cài sẵn: gỡ xong cài Office 2016 ngay trong lượt có được không, hay phải khởi động lại rồi Thử lại mục lỗi (khi đó ghi vào hướng dẫn).
- [ ] **Dừng sau mục đang chạy** trong lúc cài Office: Office cài xong mới dừng, các mục sau "Đã dừng".
- [ ] **Chọn kho…** trỏ tới thư mục SOFT trên USB / mạng (UNC): mở lại tool vẫn nhớ; rút USB thì banner báo không vào được kho.

## Việc tiếp theo

1. **Thử giao diện mới với người thật**: 2–3 người không làm IT tự làm "Không in được" và "Cài phần mềm" không cần hỏi (cột "Xong khi" của P2 trong KE-HOACH-GIAO-DIEN.md). Ghi lại chỗ họ bị vướng rồi sửa câu chữ / thứ tự.
   Ảnh trong `docs/images/` chụp bằng dữ liệu mẫu (tên máy FVPL-KT05, domain corp.example): khi chụp lại, không dùng máy thật (repo công khai).
2. **Thử tình huống trên VM có lỗi thật**: rút cáp mạng, tắt Spooler, kẹt lệnh in, lệch giờ, tắt dịch vụ Windows Update: mỗi tình huống phải chỉ đúng vấn đề, sửa xong kiểm tra lại thấy hết.
3. **Chạy danh sách trên** trên VM, sửa những gì sai. Khi đó GĐ1, GĐ2 mới xong. Wizard cần VM chưa join + domain test.
4. **Bản 1.0** ([TIEN-DO.md](TIEN-DO.md)): mọi chức năng GĐ4 đã có code; sau khi chạy thử xong danh sách trên và được duyệt thì đặt 1.0 trong `src/fvpl_ittools/__init__.py` / CHANGELOG, merge `featured` vào `main`.

## Bẫy đã gặp

GĐ0:
- **YAML hiểu `on` là `true`.** Vì vậy khoá trạng thái tên là `on_value`.
- **Lệnh có sẵn của cmd (`echo`) ghi theo code page OEM 437**, nên `chcp 65001` không giúp được. Chữ có dấu thì in bằng PowerShell.
- **Windows để chế độ tối** làm ô tick vô hình. `theme.apply_theme()` ép bảng màu sáng.
- **Chụp ảnh giao diện không cần màn hình:** nền `offscreen` mặc định vẽ chữ thành ô vuông. Phải dùng `QT_QPA_PLATFORM=offscreen:fontengine=freetype` và `QT_QPA_FONTDIR=C:\Windows\Fonts`; `tests/conftest.py` đã đặt sẵn.
- **Build lỗi khi shell đang `cd` vào `dist\`:** PyInstaller không xoá được thư mục cũ. Ra khỏi `dist\` rồi build lại.
- **Kích thước exe:** plugin bàn phím ảo kéo theo Quick/Qml/Network/OpenGL. Danh sách loại bỏ nằm trong `packaging/fvpl_ittools.spec` (`UNUSED`). Thêm module Qt mới mà exe lỗi thì xem lại danh sách này.

GĐ1:
- **Cmdlet phải nạp module rất chậm trên máy dev** (có phần mềm diệt virus): `Get-NetAdapter` 29 giây, `Get-PhysicalDisk` 16 giây, `Get-MpComputerStatus` 9 giây, `Get-NetIPConfiguration` 17 giây, `Get-NetFirewallProfile` 8 giây; gọi thẳng lớp CIM chỉ 0,1 giây. `Resolve-DnsName -QuickTimeout` vẫn chờ 15 giây mỗi DNS server không trả lời, nên tự hỏi DNS bằng UDP (`Test-DnsSrv`).
- **`-EncodedCommand` làm cảnh báo, `Write-Host`, verbose ra stderr dạng CLIXML.** `-OutputFormat Text` không giúp được; chuyển sang `-Command` với đoạn mồi giải mã base64.
- **`Write-Output` trong hàm PowerShell thành giá trị trả về;** `Write-Host` thì ra CLIXML (xem trên). Hàm vừa in vừa trả giá trị dùng `[Console]::Out.WriteLine` (`Write-Line` trong pslib).
- **PowerShell 5.1: giá trị "không có output" đặt thẳng vào hashtable thành `{}` trong JSON.** Gán vào biến trước, hoặc trả `$null` tường minh; Python đổi `{}` thành `None` cho chắc (`inventory._clean`).
- **`Get-Tpm` không có quyền admin không báo lỗi mà trả "không có TPM".** Chỉ đọc TPM/BitLocker khi có admin.
- **`[ordered]@{ 53 = ... }` rồi `$h[53]`** lấy phần tử thứ 53 chứ không phải khoá 53.
- **QLabel tự xuống dòng trong QScrollArea bị cắt chữ** (Qt tính sai chiều cao). Trang Tổng quan vẽ bằng HTML trong `QTextBrowser`.
- **`regedit.exe` nằm ở `C:\Windows`,** không phải System32.
- **Mã thoát âm** (HRESULT như `0x800705B4`) về Python thành số không dấu; khoá `messages` viết dạng hex là khớp.

GĐ2:
- **Script quá dài so với dòng lệnh** chỉ lộ ra khi chạy thật (mục "Kiểm tra share máy in" dài 32.400 ký tự sau khi mã hoá, giới hạn 32.000). Giờ hàm dựng sẵn chỉ được thêm khi script gọi tới, và `test_every_powershell_script_fits_command_line` soát mọi script.
- **`Win32_Printer.Shared` của máy in share (`\\máy\tên`) là True:** đó là trạng thái bên máy chia sẻ. Muốn biết máy này có share máy in nào thì bỏ các máy in có tên bắt đầu bằng `\\`.
- **Tác vụ chạy bằng quyền admin phải trỏ vào thư mục người dùng thường không ghi được.** Thư mục con của ProgramData mặc định cho Users tạo file (thả DLL cạnh exe là chạy bằng quyền admin), nên bước join `icacls` lại `%ProgramData%\FVPL-ITTools`. Kho SOFT trên ổ mang theo (`origin`) vẫn là chỗ tin tưởng ổ cắm vào: trang Phần mềm luôn ghi rõ đang dùng kho nào.
- **Programs and Features ẩn các mục `SystemComponent = 1` và có `ParentKeyName`** (bản cập nhật). Máy dev có 321 mục trong registry nhưng chỉ 142 mục hiện; báo cáo bỏ mục ẩn, còn phát hiện "đã cài" vẫn đọc tất cả.
- **Mật khẩu / khoá không được đi qua executor:** mọi dòng output của mục chạy qua executor vào khung log và file log. Tra mật khẩu LAPS, khoá BitLocker (`core/adsecrets.py`) chạy PowerShell riêng ở thread nền, trả kết quả thẳng cho giao diện. `Add-BitLockerKeyProtector` in khoá khôi phục trong cảnh báo: luôn `-WarningAction SilentlyContinue | Out-Null`.
- **Heredoc của Bash nuốt bớt dấu `\`** (`\\` thành `\`), cả khi dùng `<<'EOF'` để chạy Python sửa file. Nội dung có `\` thì sửa bằng công cụ Edit/Write, rồi grep lại.
- **Bộ cài là chương trình giao diện:** gọi thẳng `& setup.exe` trong PowerShell thì không chờ. `Start-Process -Wait` lại chờ cả tiến trình con (nhiều bộ cài mở luôn ứng dụng sau khi cài), nên dùng `Start-Process -PassThru` rồi `WaitForExit()`; phải đọc `$process.Handle` ngay sau khi chạy, không thì `ExitCode` có lúc rỗng.
- **Programs and Features có thể có hai dòng trùng tên** (.NET Desktop Runtime: một dòng mang số phiên bản nội bộ MSI). Phát hiện đã cài ưu tiên dòng có phiên bản khớp với số trong tên.
