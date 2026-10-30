# Hướng dẫn dựng kho bộ cài SOFT và quản lý key bản quyền

Kho `SOFT` chứa những thứ không tải được từ Internet: ISO Office bản volume, gói Symantec, UniKey, driver máy in…
Tool tự nhận kho khi thư mục `SOFT` nằm **cạnh file exe**. Mang tool đi chỉ cần chép **một thư mục** `FVPL-ITTools`.

```
dist\FVPL-ITTools\              ← chép nguyên thư mục này ra SSD / USB / máy khác
├── FVPL-ITTools.exe
├── _internal\                  thư viện của tool (build sinh ra)
├── SOFT\                       kho bộ cài (mục 1)
├── license-keys.json           key bản quyền Windows / Office (mục 3, tool tự tạo khi thêm key đầu tiên)
└── site.yaml                   domain, share, OU của công ty (không bắt buộc, xem site.example.yaml)
```

Build lại tool (`python packaging\build.py`) **không xoá** `SOFT`, `license-keys.json`, `site.yaml`, `Reports`,
`Inventory`, `DriverBackup`: build tạm dời chúng ra chỗ khác rồi trả lại. File zip phát hành không chứa những thứ này.

> **Không bao giờ** đưa `SOFT` hay `license-keys.json` lên git, Zalo, email: có bộ cài bản quyền và key.

---

## 1. Cấu trúc kho

Đã dựng sẵn trong `dist\FVPL-ITTools\SOFT`. Ô **Trạng thái** cho biết còn thiếu gì.

| Đường dẫn trong `SOFT\` | Dùng cho | Trạng thái |
|---|---|---|
| `config\apps.yaml` | Danh mục phần mềm, profile phòng ban (sửa được, không cần build lại) | Có sẵn |
| `config\office\office2016-standard.xml` (2013, 2010) | Cấu hình cài im lặng Office | Có sẵn, chưa có key |
| `SW_DVD5_Office_2016_64Bit_English_MLF_X20-42479.ISO` | Office 2016 Standard 64-bit | **Cần chép vào** |
| `SW_DVD5_Office_2013w_SP1_64Bit_English_MLF_X19-34904.ISO` | Office 2013 Standard SP1 64-bit | **Cần chép vào** |
| `Microsoft Office 2010 Standard Edition X86 SP1.iso` | Office 2010 Standard 32-bit | **Cần chép vào** (nếu dùng) |
| `Installers\UniKey\` | UniKey (`UniKeyNT.exe`, `UKHook40.dll`, `keymap.txt`) | Có sẵn |
| `Symantec\SEP-14.3-RU9-Win64\` | Gói client SEP đã giải nén (`Sep64.msi`) + `SyLink.xml` | **Cần chép vào** |
| `Installers\winget\` | Bộ cài winget offline (`.msixbundle`, `.appx`, license `.xml`) | Không bắt buộc |
| `Sources\sxs\<build>\` | Nguồn .NET 3.5 offline, ví dụ `Sources\sxs\19045` cho Win10 22H2 | Không bắt buộc |
| `Drivers\Printers\<hãng>\` | Driver máy in đã giải nén (có file `.inf`) | Không bắt buộc |

---

## 2. Các bước làm kho

### Bước 1: Chép ISO Office

1. Chép file ISO vào thẳng `SOFT\`, **giữ đúng tên** như bảng trên.
2. ISO tên khác? Có hai cách:
   - Đổi tên file cho khớp bảng trên (đơn giản nhất), hoặc
   - Mở `SOFT\config\apps.yaml`, tìm mục `office2016` (hoặc `office2013`, `office2010`), sửa dòng `installer:` thành
     tên file của bồ, ví dụ `installer: '{share}\Office2016_x64.iso'`. `{share}` là thư mục `SOFT`.
3. **Kiểm tra bản Standard hay Professional Plus:** mở ISO (nhấp đúp), xem thư mục tên `*.WW`:
   - `Standard.WW` → giữ nguyên file XML (`Product="Standard"`).
   - `ProPlus.WW` → mở `config\office\officeXXXX-standard.xml`, sửa thành `Product="ProPlus"`, rồi trong
     `apps.yaml` sửa `name:` và `detect: { uninstall_name: 'Microsoft Office Professional Plus 2016*' }` cho đúng.

### Bước 2: Chép gói Symantec (nếu cài SEP bằng tool)

1. Giải nén gói client SEP 64-bit (bằng 7-Zip) vào `SOFT\Symantec\SEP-14.3-RU9-Win64\`. Trong thư mục phải có `Sep64.msi`.
2. Muốn máy tự vào SEPM của công ty: trong SEPM console → **Clients** → chuột phải nhóm máy trạm →
   **Export Communication Settings** → chế độ *Computer* → lưu `SyLink.xml`, chép đè vào cùng thư mục với `Sep64.msi`.
3. Bản khác 14.3 RU9: đổi tên thư mục, rồi sửa dòng `installer:` và `name:` của mục `sep` trong `apps.yaml`.

### Bước 3: Thêm phần mềm riêng của công ty (nếu cần)

Thêm một mục vào `SOFT\config\apps.yaml`. Ví dụ bộ cài `.msi` hoặc `.exe` đặt trong `SOFT\Installers\`:

```yaml
  - id: phan-mem-ke-toan          # chữ thường không dấu, số, - và _
    name: Phần mềm kế toán
    group: Văn phòng
    source: share
    installer: '{share}\Installers\KeToan\setup.msi'
    # .exe thì phải có tham số cài im lặng, ví dụ: args: '/S'  hoặc  args: '/VERYSILENT /NORESTART'
```

Đủ các khoá, cách khai báo profile phòng ban: [SOFTWARE.md](SOFTWARE.md).

### Bước 4: Kiểm tra kho

1. Mở `FVPL-ITTools.exe` (bấm Yes ở UAC), vào **Cài phần mềm**.
2. Khung vàng "Chưa có kho bộ cài" **không còn**; thanh bên trái ghi **Kho bộ cài** là thư mục `SOFT`.
3. Từng mục có dòng trạng thái nhỏ:
   - **Chưa cài** / **Cài từ kho bộ cài**: kho đủ, tick được.
   - **Không thấy bộ cài trong kho** (thẻ Office) hoặc **Không cài được** kèm chú thích "Không thấy bộ cài trên
     share" (rê chuột lên): sai tên file / sai thư mục. So đường dẫn với dòng `installer:` của mục đó trong `apps.yaml`.
   - **Máy đang có Microsoft 365 / Office…**: máy đã có Office khác, xem
     [HUONG-DAN-SU-DUNG.md](HUONG-DAN-SU-DUNG.md) mục 4.
4. Sửa `apps.yaml` sai cú pháp: khung log báo lỗi tiếng Việt kèm số thứ tự mục; sửa xong bấm **Kiểm tra lại**.

---

## 3. Key bản quyền Windows / Office

Có hai cách. **Nên dùng cách A** vì một phiên bản giữ được nhiều key và biết key nào còn lượt.

### Cách A (khuyên dùng): tab Key bản quyền, nhiều key cho mỗi bản

1. Mở tool → **Tiện ích** → tab **Key bản quyền** (hoặc gõ "key" ở ô tìm, Ctrl+K).
2. Bấm **Thêm key…**:
   - **Sản phẩm:** chọn hoặc gõ, ví dụ `Office 2016 Standard`, `Windows 10/11 Pro`.
   - **Key:** dán **một hoặc nhiều key**, mỗi dòng một key. Dán cả đoạn chữ có lẫn key cũng được, tool tự lọc.
   - **Loại:** MAK, Retail, OEM hoặc KMS.
   - **Ghi chú:** số hợp đồng, số lượt kích hoạt…
   Lặp lại cho từng sản phẩm. Mỗi sản phẩm có bao nhiêu key cũng được.
3. Key lưu vào `license-keys.json` **cạnh file exe**, đi theo thư mục `FVPL-ITTools` khi chép. Cả nhóm IT dùng chung:
   để file trên share, bấm **Mở file khác…** chọn file đó (tool nhớ cho lần sau).
4. **Cài Office trước, kích hoạt sau:** để file XML Office **không có** dòng `PIDKEY` (như hiện tại). Cài Office ở trang
   **Cài phần mềm**, xong vào tab **Key bản quyền** → chọn một key của đúng bản Office → **Kích hoạt máy này bằng key
   đã chọn** (cần Internet). Windows cũng làm vậy; key hợp với bản Windows của máy có ghi "hợp với máy này".
5. Cột **Đã dùng** cho biết mỗi key đã kích hoạt mấy máy, lần cuối máy nào. Key MAK hết lượt thì kích hoạt báo lỗi:
   chọn key khác của cùng bản rồi bấm lại.
6. Xem máy đã kích hoạt chưa: nút **Xem trạng thái kích hoạt** (không cần admin) hoặc trang **Thông tin máy**.

### Cách B: ghi một key cố định vào file XML Office

Chỉ hợp khi mỗi bản Office chỉ có **một** key MAK. Cài xong Office tự kích hoạt, không cần bước kích hoạt riêng.

1. Mở `SOFT\config\office\office2016-standard.xml` bằng Notepad.
2. Sửa dòng
   ```xml
   <!-- <PIDKEY Value="XXXXX-XXXXX-XXXXX-XXXXX-XXXXX" /> -->
   ```
   thành (bỏ `<!--` và `-->`, điền key thật):
   ```xml
   <PIDKEY Value="ABCDE-FGHIJ-KLMNO-PQRST-UVWXY" />
   ```
3. Làm tương tự cho file 2013, 2010 nếu dùng.

Khi key này hết lượt phải sửa lại file; tool không theo dõi được key trong file XML. Có nhiều key thì dùng cách A.

---

## 4. Mang tool đi

- **Chép tay:** chép nguyên thư mục `dist\FVPL-ITTools` ra SSD / USB. Mở `FVPL-ITTools.exe` ở đó là dùng được.
- **Chép bằng script** (chỉ chép phần thay đổi, kho lớn vẫn nhanh):
  ```powershell
  .venv\Scripts\python packaging\deploy.py ssd F:\    # tool + SOFT (lấy SOFT trong dist\FVPL-ITTools)
  .venv\Scripts\python packaging\deploy.py usb E:\    # chỉ tool, không kèm kho
  ```
  `deploy.py` không chép `license-keys.json`: chép tay file này nếu cần mang key theo.
- **Bản phát hành lên share** (`deploy.py share …`) không bao giờ kèm `SOFT`, `site.yaml`, `license-keys.json`.
