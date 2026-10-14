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

## 3. Chưa ký được

Phần mềm diệt virus báo nhầm file exe thì gửi file cho hãng xét lại. Với Microsoft Defender:
<https://www.microsoft.com/wdsi/filesubmission> (chọn *Software developer*, ghi rõ là công cụ nội bộ). Tool đã đóng gói
kiểu `onedir` (không nén thành một file exe) để giảm báo nhầm.
