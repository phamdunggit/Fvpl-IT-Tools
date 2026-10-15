# Ký số file exe

File exe đóng gói bằng PyInstaller chưa ký số thì:

- Hộp UAC ghi **Nhà phát hành: Không xác định** (Unknown publisher).
- Phần mềm diệt virus dễ báo nhầm hơn.
- Tải từ Internet về (file zip có "Mark of the Web") thì SmartScreen chặn với thông báo "Windows protected your PC".

Ký số bằng chứng chỉ **Code Signing** giúp UAC ghi tên nhà phát hành, và diệt virus tin file hơn. Tool tự ký khi build nếu có
chứng chỉ; chưa có thì vẫn build bình thường, chỉ in nhắc "Chưa ký số exe".

## 1. Lấy chứng chỉ

**Cách A: CA nội bộ của công ty (AD CS).** Hợp với tool chỉ dùng trong công ty, không tốn tiền.

1. Trên CA: **Certificate Templates** → nhân bản mẫu **Code Signing**, đặt tên ví dụ "FVPL Code Signing", tab Security
   cho nhóm IT quyền **Enroll**. Publish mẫu đó (**Certificate Templates → New → Certificate Template to Issue**).
2. Trên máy build, bằng tài khoản IT: `certmgr.msc` → **Personal → Certificates** → chuột phải **All Tasks → Request New
   Certificate** → chọn mẫu vừa tạo.
3. Lấy thumbprint:

   ```powershell
   Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert | Format-List Subject, Thumbprint, NotAfter
   ```

4. Máy trong domain đã tin CA gốc của công ty, nên chữ ký hợp lệ. Muốn UAC và AppLocker coi đây là nhà phát hành tin cậy
   thì thêm chứng chỉ (phần công khai, file .cer) vào **Trusted Publishers** bằng GPO: *Computer Configuration → Policies
   → Windows Settings → Security Settings → Public Key Policies → Trusted Publishers*.

**Cách B: mua chứng chỉ của CA công cộng** (Sectigo, DigiCert, GlobalSign…), loại OV hoặc EV. Máy ngoài domain cũng tin.
Chứng chỉ EV có ngay "danh tiếng" với SmartScreen. Từ 2023, khoá riêng phải nằm trên token USB hoặc HSM. Cắm token
vào máy build; signtool vẫn chọn chứng chỉ theo thumbprint như cách A.

**Cách C: chứng chỉ tự tạo, phát cho máy trong domain bằng GPO.** Dùng khi công ty chưa có AD CS: không tốn tiền, không
phải dựng máy chủ CA, khoảng 15 phút. Máy trong domain tin chữ ký sau khi nhận GPO. Máy chưa vào domain (lúc chạy wizard
Cài máy mới) vẫn thấy chữ ký nhưng ghi "không tin cậy"; tool vẫn chạy bình thường.

1. Trên máy build, PowerShell (không cần admin) tạo chứng chỉ 5 năm:

   ```powershell
   $cert = New-SelfSignedCertificate -Type CodeSigningCert -Subject "CN=FVPL IT Toolkit" `
       -KeyAlgorithm RSA -KeyLength 3072 -HashAlgorithm SHA256 -NotAfter (Get-Date).AddYears(5) `
       -CertStoreLocation Cert:\CurrentUser\My
   $cert.Thumbprint
   Export-Certificate -Cert $cert -FilePath "$env:USERPROFILE\Desktop\FVPL-CodeSigning.cer"
   ```

2. Sao lưu khoá riêng (máy build hỏng thì vẫn ký tiếp được bằng đúng chứng chỉ này). Tự đặt mật khẩu, cất file .pfx
   và mật khẩu ở chỗ an toàn, **không** để trong repo hay trên USB phát cho người khác:

   ```powershell
   Export-PfxCertificate -Cert $cert -FilePath "$env:USERPROFILE\Desktop\FVPL-CodeSigning.pfx" `
       -Password (Read-Host -AsSecureString "Mật khẩu cho file pfx")
   ```

3. Phát file **.cer** (phần công khai, không có khoá riêng) cho mọi máy trong domain: Group Policy Management → GPO gắn
   vào OU máy trạm (hoặc cả domain) → *Computer Configuration → Policies → Windows Settings → Security Settings → Public
   Key Policies*, import file .cer vào **cả hai** mục:
   - **Trusted Root Certification Authorities** (để chữ ký hợp lệ)
   - **Trusted Publishers** (để UAC / AppLocker coi là nhà phát hành tin cậy)

   Rồi `gpupdate /force` trên máy build và máy thử. Build kiểm tra chữ ký bằng `signtool verify /pa`, nên máy build phải
   nhận GPO này (hoặc import .cer vào Trusted Root của máy build) trước khi build.
4. Build có ký như mục 2 bên dưới, với thumbprint ở bước 1.

## 2. Build có ký số

Cần `signtool.exe` (Windows SDK, chỉ chọn phần **Signing Tools for Desktop Apps**). Build sẽ tự tìm bản mới nhất trong
`C:\Program Files (x86)\Windows Kits\10\bin`.

```powershell
$env:FVPL_SIGN_THUMBPRINT = "<thumbprint ở bước 1>"
.venv\Scripts\python packaging\build.py
```

Build ký `FVPL-ITTools.exe` (SHA-256, kèm dấu thời gian: chữ ký vẫn hợp lệ khi chứng chỉ hết hạn), kiểm tra lại bằng
`signtool verify /pa`, rồi mới nén file zip.

| Biến môi trường | Dùng khi |
|---|---|
| `FVPL_SIGN_THUMBPRINT` | Bắt buộc để ký. Không đặt thì bỏ qua bước ký |
| `FVPL_SIGN_TIMESTAMP` | Đổi máy chủ dấu thời gian (mặc định `http://timestamp.digicert.com`; máy build không ra Internet thì dùng máy chủ nội bộ nếu có) |
| `FVPL_SIGNTOOL` | Đường dẫn `signtool.exe` khi không cài ở chỗ mặc định |

Kiểm tra: chuột phải file exe → **Properties → Digital Signatures**, hoặc mở tool và xem hộp UAC.

## 3. Symantec Endpoint Protection cách ly tool

SEP có thể cách ly `FVPL-ITTools.exe` với tên kiểu `SONAR.SuspOpen!gen…`. Đây là đánh giá theo hành vi và độ phổ biến của
file (file mới build, chỉ có trên vài máy, chạy nhiều lệnh PowerShell), không phải mẫu virus. Ký số giúp, nhưng chứng chỉ
tự tạo (cách C) không có "danh tiếng" với Symantec, nên vẫn cần thêm exception trong SEPM (**Policies → Exceptions**,
nhớ chọn cả loại quét SONAR):

| Loại exception | Ưu | Nhược |
|---|---|---|
| Theo **chứng chỉ** (nếu bản SEPM có loại này trong *Add → Windows Exceptions*) | Một lần cho mọi bản build sau | Phải ký số trước |
| Theo **file / hash SHA-256** của exe (build in ra và ghi vào `dist/FVPL-ITTools-v<bản>.sha256.txt`; bản phát hành lên share có trong `version.json`, khoá `exe_sha256`) | Chắc chắn đúng file | Mỗi bản build mới phải thêm lại |
| Theo **thư mục** | Bản chép trong máy `C:\ProgramData\FVPL-ITTools\app\`, share cố định | USB / SSD đổi ký tự ổ thì không khớp |

File đã bị cách ly: khôi phục trong SEP client (**View Quarantine → Restore**) hoặc từ SEPM sau khi đã thêm exception.

## 4. Chưa ký được

Phần mềm diệt virus báo nhầm file exe thì gửi file cho hãng xét lại. Với Microsoft Defender:
<https://www.microsoft.com/wdsi/filesubmission> (chọn *Software developer*, ghi rõ là công cụ nội bộ). Tool đã đóng gói
kiểu `onedir` (không nén thành một file exe) để giảm báo nhầm.
