# Hướng dẫn triển khai GPO, Windows LAPS và BitLocker

Viết cho môi trường: một domain Active Directory, chưa dùng GPO, máy trạm nằm chung một OU, Windows 10 và 11 lẫn lộn,
máy chủ yếu Dell và Lenovo. Tên trong tài liệu là ví dụ: domain `corp.example` (NetBIOS `CORP`), OU máy trạm
`OU=Workstations,DC=corp,DC=example`, nhóm IT `CORP\IT Admins`. Thay bằng tên thật (đã có trong `site.yaml`).

Thứ tự nên làm: **GPO nền móng → LAPS → BitLocker**. LAPS gần như không có rủi ro mà lợi ích lớn ngay. BitLocker cần
chuẩn bị kỹ hơn vì làm sai thì người dùng có thể bị khoá máy.

| Phần | Giải quyết việc gì | Rủi ro khi làm sai |
|---|---|---|
| GPO | Cấu hình hàng loạt máy từ một chỗ, máy mới vào OU là tự nhận | Áp nhầm cho cả công ty; sửa bằng cách bỏ liên kết GPO |
| Windows LAPS | Mỗi máy một mật khẩu admin cục bộ riêng, tự đổi định kỳ, IT tra trong AD | Thấp: chỉ đổi mật khẩu tài khoản admin cục bộ |
| BitLocker | Mã hoá ổ cứng: mất laptop không lộ dữ liệu; khoá khôi phục lưu trong AD | Cao hơn: chưa lưu được khoá mà máy hỏi khoá thì mất dữ liệu |

---

## 1. GPO: nền móng

### 1.1 Khái niệm cần nhớ

- **GPO** (Group Policy Object) là một bộ thiết lập. GPO **liên kết (link)** vào một OU thì áp cho máy / người dùng
  nằm trong OU đó (và OU con).
- Có hai nửa: **Computer Configuration** (áp cho máy, khi khởi động và mỗi 90 ± 30 phút) và **User Configuration**
  (áp cho người dùng khi đăng nhập). LAPS, BitLocker, Windows Update đều là Computer Configuration.
- Thứ tự áp: Local → Site → Domain → OU (OU con áp sau, thắng OU cha). Hai GPO cùng chỉnh một thiết lập thì GPO áp sau thắng.
- **Security filtering**: mặc định GPO áp cho `Authenticated Users` (mọi máy, mọi người). Muốn thử trên vài máy thì
  đổi thành một nhóm, ví dụ `GPO-Thu`, rồi cho máy cần thử vào nhóm đó (nhớ giữ quyền Read cho `Domain Computers`,
  xem mục 1.4).
- Thiết lập trong **Administrative Templates** tự gỡ khi GPO thôi áp. Thiết lập **Security Settings** và
  **Preferences (GPP)** thì thường ở lại trên máy ("tattoo"), phải tạo GPO khác để đặt lại.

### 1.2 Công cụ

Trên máy IT (Windows 11, tài khoản domain có quyền):

```powershell
# Group Policy Management Console (GPMC), Active Directory Users and Computers, BitLocker Recovery viewer
Add-WindowsCapability -Online -Name Rsat.GroupPolicy.Management.Tools~~~~0.0.1.0
Add-WindowsCapability -Online -Name Rsat.ActiveDirectory.DS-LDS.Tools~~~~0.0.1.0
Add-WindowsCapability -Online -Name Rsat.BitLocker.Recovery.Tools~~~~0.0.1.0
```

Trên máy trạm, FVPL IT Toolkit có sẵn: **Cập nhật Group Policy** (`gpupdate /force`) và **Báo cáo GPO đang áp**
(`gpresult /h`, mở bằng trình duyệt) ở trang Sửa lỗi, nhóm Domain. Dùng hai mục này sau mỗi lần sửa GPO.

### 1.3 Kiểm tra domain trước khi bắt đầu

Chạy trên máy IT (đã cài RSAT ở trên):

```powershell
Get-ADDomain | Select-Object DNSRoot, DomainMode          # cần Windows2016Domain trở lên để mã hoá mật khẩu LAPS
Get-ADForest | Select-Object ForestMode
Get-ADDomainController -Filter * | Select-Object Name, OperatingSystem
Get-ADComputer -SearchBase 'OU=Workstations,DC=corp,DC=example' -Filter * | Measure-Object   # số máy trong OU
```

Ghi lại `DomainMode`: mục 2 cần biết.

### 1.4 Central Store cho file mẫu chính sách

File mẫu (ADMX) quyết định GPMC hiện những thiết lập nào. Nên dùng **Central Store** trên SYSVOL để mọi máy IT thấy
cùng một bộ mẫu, và để có mẫu của Windows 11 mới nhất (LAPS, máy in RPC...).

1. Trên một máy **Windows 11 bản mới nhất, đã cập nhật đủ**, chép cả thư mục `C:\Windows\PolicyDefinitions`.
2. Dán vào `\\corp.example\SYSVOL\corp.example\Policies\PolicyDefinitions` (tạo mới nếu chưa có). Giữ thư mục ngôn
   ngữ `en-US` bên trong.
3. Mở lại GPMC, sửa một GPO bất kỳ: dòng trên cùng hiện "Policy definitions (ADMX files) retrieved from the central
   store" là được.

Lưu ý: khi đã có Central Store, GPMC **chỉ** đọc mẫu ở đó. Mỗi lần công ty lên bản Windows mới thì chép lại thư mục
này từ máy mới nhất.

### 1.5 Quy ước đặt GPO

- **Không sửa Default Domain Policy**, trừ chính sách mật khẩu và khoá tài khoản. Mỗi việc một GPO riêng, dễ bật tắt.
- Đặt tên theo đối tượng và việc: `WS - LAPS`, `WS - BitLocker`, `WS - Cau hinh chung`, `WS - May in` (WS = máy trạm).
- GPO chỉ có thiết lập máy thì tắt nửa người dùng: chuột phải GPO → **GPO Status** → **User Configuration Settings
  Disabled** (máy xử lý nhanh hơn).
- Sao lưu trước khi sửa lớn:

  ```powershell
  Backup-GPO -All -Path '\\fileserver\IT$\Backup-GPO'
  ```

### 1.6 Cách thử một GPO an toàn

1. Tạo nhóm `GPO-Thu` (Global, Security), cho 2–3 máy vào (máy IT, một máy Win10, một máy Win11).
2. Tạo GPO, link vào OU máy trạm. Ở tab **Scope** → **Security Filtering**: bỏ `Authenticated Users`, thêm `GPO-Thu`.
   Sang tab **Delegation** → **Advanced**, thêm `Domain Computers` với quyền **Read** (không tick Apply), nếu không
   GPO sẽ không đọc được (thay đổi bảo mật của Microsoft từ 2016).
3. Máy trong nhóm phải **khởi động lại một lần** để nhận nhóm mới, rồi chạy **Cập nhật Group Policy** và **Báo cáo
   GPO đang áp** bằng tool: GPO phải nằm ở mục "Applied GPOs".
4. Ổn vài ngày thì đổi Security Filtering về `Authenticated Users` để áp cho cả OU.

Gỡ: bỏ liên kết (Link Enabled = No) hoặc xoá link. Không xoá GPO ngay để còn đường quay lại.

---

## 2. Windows LAPS: mật khẩu admin cục bộ riêng cho từng máy

### 2.1 Vì sao nên làm trước

Hiện nay mật khẩu tài khoản admin cục bộ thường giống nhau trên mọi máy: lộ một máy là vào được cả công ty. Windows LAPS
đặt cho **mỗi máy một mật khẩu ngẫu nhiên**, tự đổi định kỳ, lưu vào computer object trong AD; IT tra khi cần.
Rất có ích khi máy **mất quan hệ tin cậy với domain** (lỗi trust relationship): đăng nhập `.\Administrator` bằng
mật khẩu LAPS rồi chạy mục Sửa lỗi trust relationship của tool.

Windows LAPS có sẵn trong Windows (không cài thêm), từ bản cập nhật **11/04/2023** cho Windows 10 / 11 và Windows
Server 2019 trở lên. Bản Microsoft LAPS cũ (file MSI) đã bị khai tử: **đừng cài**. Lưu ý: Windows 10 hết hỗ trợ từ
14/10/2025, máy Win10 không có bản cập nhật bảo mật mở rộng (ESU) thì nên lên Windows 11.

### 2.2 Chuẩn bị AD (làm một lần)

Chạy PowerShell **bằng quyền admin** trên máy IT Windows 11 đã cập nhật (có sẵn module `LAPS`) hoặc trên DC
Windows Server 2019+, bằng tài khoản thuộc **Schema Admins** và **Domain Admins**:

```powershell
# 1. Thêm các thuộc tính LAPS vào schema (một lần cho cả forest)
Update-LapsADSchema -Verbose

# 2. Cho máy trong OU tự ghi mật khẩu của nó lên AD
Set-LapsADComputerSelfPermission -Identity 'OU=Workstations,DC=corp,DC=example'

# 3. (Tuỳ chọn) cho nhóm IT đọc và bắt đổi mật khẩu. Domain Admins có sẵn hai quyền này.
Set-LapsADReadPasswordPermission  -Identity 'OU=Workstations,DC=corp,DC=example' -AllowedPrincipals 'CORP\IT Admins'
Set-LapsADResetPasswordPermission -Identity 'OU=Workstations,DC=corp,DC=example' -AllowedPrincipals 'CORP\IT Admins'

# 4. Xem ai đang có quyền "All extended rights" trên OU (người đó đọc được mật khẩu): chỉ nên là SYSTEM, Domain Admins
Find-LapsADExtendedRights -Identity 'OU=Workstations,DC=corp,DC=example'
```

### 2.3 GPO `WS - LAPS`

**Computer Configuration → Policies → Administrative Templates → System → LAPS**:

| Thiết lập | Đặt | Ghi chú |
|---|---|---|
| Configure password backup directory | Enabled → **Active Directory** | Bắt buộc, không đặt thì LAPS không làm gì |
| Password Settings | Enabled: complexity **Large letters + small letters + numbers + special characters**, length **16**, age **30** ngày | Dài hơn chính sách mật khẩu cục bộ là được |
| Enable password encryption | **Enabled** nếu `DomainMode` ≥ Windows2016Domain, **Disabled** nếu thấp hơn | Mặc định là bật: domain cũ mà không tắt thì máy không lưu được mật khẩu |
| Configure authorized password decryptors | `CORP\IT Admins` | Chỉ có tác dụng khi bật mã hoá; không đặt thì chỉ Domain Admins giải mã được |
| Configure size of encrypted password history | 6 | Giữ mật khẩu cũ để mở bản sao lưu hệ thống cũ |
| Post-authentication actions | Reset password and log off, 8 giờ | Mật khẩu bị đổi 8 giờ sau khi IT dùng xong |
| Name of administrator account to manage | **Không đặt** | Để LAPS quản lý tài khoản Administrator gốc (nhận theo RID, không phụ thuộc ngôn ngữ) |

Tài khoản Administrator gốc mặc định bị **tắt** trên Windows 10/11. LAPS vẫn đổi mật khẩu cho nó, nhưng muốn đăng nhập
được thì bật lên trong cùng GPO: **Computer Configuration → Policies → Windows Settings → Security Settings → Local
Policies → Security Options → Accounts: Administrator account status = Enabled**. Mật khẩu do LAPS quản lý nên bật lên
không còn nguy hiểm như trước.

Máy Windows 11 24H2 trở lên có thêm tuỳ chọn tự tạo tài khoản quản lý riêng và mật khẩu dạng cụm từ (passphrase).
Công ty còn máy Win10 nên chưa dùng: máy cũ không hiểu thì quay về mặc định.

### 2.4 Kiểm tra và dùng

Trên máy thử: chạy **Cập nhật Group Policy** trong tool, rồi trong PowerShell admin:

```powershell
Invoke-LapsPolicyProcessing     # xử lý ngay, không chờ chu kỳ 1 giờ
```

Event Viewer → Applications and Services Logs → Microsoft → Windows → **LAPS** → Operational: sự kiện **10018** là đã
lưu mật khẩu lên AD. Lỗi 10027 thường do độ dài / độ phức tạp không hợp với chính sách mật khẩu cục bộ.

Tra mật khẩu trên máy IT:

```powershell
Get-LapsADPassword -Identity FVPL-KT05 -AsPlainText
# Bắt đổi mật khẩu sớm (lần xử lý chính sách tiếp theo của máy đó)
Set-LapsADPasswordExpirationTime -Identity FVPL-KT05
```

Hoặc trong Active Directory Users and Computers (RSAT bản mới): mở computer object → tab **LAPS**.

---

## 3. BitLocker: mã hoá ổ cứng, khoá khôi phục lưu trong AD

### 3.1 Điều kiện

- Windows **Pro** trở lên (bản Home không có BitLocker đầy đủ).
- **TPM 2.0**, khởi động **UEFI** và **Secure Boot** bật. Máy Dell, Lenovo dòng văn phòng đời 2017 trở lại đây gần
  như đều có. Xem nhanh cả công ty: file kiểm kê `KiemKe.xlsx` (nút Lưu kiểm kê của tool) có cột **TPM** và
  **BitLocker**; trang Tổng quan của tool hiện TPM, Secure Boot, BitLocker từng máy.
- Ưu tiên **laptop** (dễ mất, dễ bị lấy cắp) trước máy bàn.

### 3.2 GPO `WS - BitLocker`

**Computer Configuration → Policies → Administrative Templates → Windows Components → BitLocker Drive Encryption**:

| Thiết lập | Đặt |
|---|---|
| Choose drive encryption method and cipher strength (Windows 10 [Version 1511] and later) | Enabled: ổ hệ thống **XTS-AES 128-bit**, ổ dữ liệu **XTS-AES 128-bit**, ổ rời (USB) **AES-CBC 128-bit** (để cắm được máy khác) |
| Operating System Drives → **Choose how BitLocker-protected operating system drives can be recovered** | Enabled. Allow 48-digit recovery password; tick **Omit recovery options from the BitLocker setup wizard**; tick **Save BitLocker recovery information to AD DS for operating system drives** → **Store recovery passwords and key packages**; tick **Do not enable BitLocker until recovery information is stored to AD DS for operating system drives** |
| Fixed Data Drives → Choose how BitLocker-protected fixed drives can be recovered | Như trên, cho ổ D nếu có |
| Operating System Drives → Require additional authentication at startup | Để Not configured (chỉ dùng TPM, người dùng không phải gõ PIN khi bật máy) |

Ý chính: **"Do not enable BitLocker until recovery information is stored to AD DS"**: máy không sao lưu được khoá lên
AD thì không cho bật BitLocker. Đây là chốt an toàn quan trọng nhất.

GPO **không tự mã hoá máy** (domain không có Intune). Sau khi GPO đã áp (kiểm tra bằng Báo cáo GPO đang áp), bật trên
từng máy.

### 3.3 Bật BitLocker trên một máy

PowerShell **admin** trên máy cần mã hoá:

```powershell
manage-bde -status C:                                   # xem đã mã hoá chưa
Get-Tpm                                                 # TpmPresent, TpmReady phải là True

# Thêm khoá khôi phục 48 số (GPO sẽ tự đẩy lên AD), rồi bật BitLocker dùng TPM, chỉ mã hoá phần đã dùng (nhanh)
Add-BitLockerKeyProtector -MountPoint C: -RecoveryPasswordProtector
Enable-BitLocker -MountPoint C: -TpmProtector -EncryptionMethod XtsAes128 -UsedSpaceOnly

manage-bde -protectors -get C:                          # phải thấy TPM và Numerical Password
```

Máy chạy bình thường trong lúc mã hoá. Khởi động lại một lần để kiểm tra không bị hỏi khoá.

Máy **đã mã hoá sẵn** từ trước (một số máy Windows 11 cài mới tự bật "Device encryption"), hoặc bật BitLocker trước
khi có GPO: khoá chưa chắc có trong AD. Chạy mục **Sao lưu khoá BitLocker lên AD** của tool (trang Sửa lỗi, nhóm Bảo
mật) sau khi GPO đã áp.

### 3.4 Tra khoá khôi phục khi máy hỏi

- Active Directory Users and Computers → computer object → tab **BitLocker Recovery** (cài
  `Rsat.BitLocker.Recovery.Tools` ở mục 1.2). Màn hình xanh trên máy có **Recovery key ID** (8 ký tự đầu): khớp với
  dòng trong tab.
- Hoặc PowerShell:

  ```powershell
  $computer = Get-ADComputer FVPL-KT05
  Get-ADObject -SearchBase $computer.DistinguishedName -Filter "objectClass -eq 'msFVE-RecoveryInformation'" `
      -Properties msFVE-RecoveryPassword | Select-Object Name, msFVE-RecoveryPassword
  ```

### 3.5 Những lúc hay bị hỏi khoá

- **Cập nhật BIOS / firmware**: phải tạm dừng BitLocker trước (`Suspend-BitLocker -MountPoint C: -RebootCount 1`).
  Mục "Cập nhật driver, BIOS của hãng" của tool với máy Dell đã tự tạm dừng (`-autoSuspendBitLocker`); cập nhật BIOS
  bằng tay thì nhớ tạm dừng.
- Đổi thiết lập trong BIOS (Secure Boot, TPM, thứ tự boot), thay mainboard, chuyển ổ sang máy khác.
- Trước khi cài lại Windows hoặc đem máy đi sửa ngoài: tạm dừng hoặc giải mã (`Disable-BitLocker -MountPoint C:`).

Không có khoá trong AD mà máy hỏi khoá thì **mất dữ liệu**. Vì vậy chỉ bật sau khi GPO ở mục 3.2 đã áp, và thử tra
khoá (mục 3.4) cho mấy máy đầu tiên trước khi làm hàng loạt.

---

## 4. Các GPO nên có thêm (làm dần)

| GPO | Thiết lập | Vì sao |
|---|---|---|
| `WS - Cau hinh chung` | **Computer → Preferences → Control Panel Settings → Local Users and Groups**: nhóm `Administrators (built-in)`, Action **Update**, thêm `CORP\IT Admins` | Mọi máy có nhóm IT trong Administrators (wizard của tool đang làm từng máy) |
| | **Security Options → Interactive logon: Machine inactivity limit** = 900 | Tự khoá màn hình sau 15 phút không dùng |
| | **Computer → Preferences → Windows Settings → Registry**: `HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Power`, `HiberbootEnabled` = 0 | Tắt Fast Startup để GPO, bản cập nhật áp đúng khi bật máy |
| `WS - Windows Update` | **Windows Components → Windows Update → Manage updates offered from Windows Update**: Select when Quality Updates are received = 3–7 ngày; Select the target Feature Update version = Windows 11, bản đã thử (ví dụ 24H2) | Công ty cập nhật thẳng từ Microsoft: lùi vài ngày để tránh bản lỗi, không tự lên bản Windows mới khi chưa thử |
| `WS - May in` | **Administrative Templates → Printers**: Configure RPC connection settings = RpcOverNamedPipes; Configure RPC listener settings = RpcOverNamedPipesAndTcp | Thay cho việc chạy từng máy các mục "Share máy in Win11 ↔ Win10" của tool. Win10 bỏ qua hai thiết lập này |
| | **Printers → Point and Print Restrictions**: chỉ cho phép máy chủ in / máy share được duyệt | Người dùng thường không tự cài driver từ máy lạ (an toàn sau lỗi PrintNightmare) |
| Default Domain Policy | **Account Lockout Policy**: khoá sau 10 lần sai, 15 phút | Chặn dò mật khẩu |

Ánh xạ ổ mạng, máy in theo phòng ban dùng **User Configuration → Preferences → Drive Maps / Printers** với
**Item-level targeting** theo nhóm phòng ban.

---

## 5. Lộ trình gợi ý

| Tuần | Việc | Xong khi |
|---|---|---|
| 1 | Cài RSAT trên máy IT; kiểm tra domain (1.3); Central Store (1.4); sao lưu GPO; tạo nhóm `GPO-Thu` | GPMC đọc mẫu từ Central Store |
| 2 | LAPS: chuẩn bị AD (2.2), GPO `WS - LAPS` cho `GPO-Thu` (2.3), kiểm tra (2.4) | Tra được mật khẩu của 3 máy thử, đăng nhập `.\Administrator` được |
| 3 | LAPS cho cả OU; GPO `WS - BitLocker` cho `GPO-Thu`; bật BitLocker 2–3 laptop thử (3.3) | Tra được khoá khôi phục trong AD (3.4); khởi động lại không bị hỏi khoá |
| 4 | Lưu kiểm kê các máy để biết máy nào có TPM 2.0; BitLocker cho laptop, rồi máy bàn | Cột BitLocker trong `KiemKe.xlsx` là "Đã mã hoá" |
| Sau đó | `WS - Cau hinh chung`, `WS - Windows Update`, `WS - May in` | Máy mới join vào OU tự nhận đủ cấu hình |

---

## Nguồn

- Microsoft Learn: [Windows LAPS overview](https://learn.microsoft.com/en-us/windows-server/identity/laps/laps-overview),
  [Get started with Windows LAPS and Windows Server Active Directory](https://learn.microsoft.com/en-us/windows-server/identity/laps/laps-scenarios-windows-server-active-directory),
  [Configure policy settings for Windows LAPS](https://learn.microsoft.com/en-us/windows-server/identity/laps/laps-management-policy-settings).
- Microsoft Learn: [Configure BitLocker](https://learn.microsoft.com/en-us/windows/security/operating-system-security/data-protection/bitlocker/configure).
- Microsoft Learn: [Create and manage the Central Store](https://learn.microsoft.com/en-us/troubleshoot/windows-client/group-policy/create-and-manage-central-store).
- Microsoft Learn: [Windows 11 RPC connection updates for print](https://learn.microsoft.com/en-us/troubleshoot/windows-client/printing/windows-11-rpc-connection-updates-for-print).
