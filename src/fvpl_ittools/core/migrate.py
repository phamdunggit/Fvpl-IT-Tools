"""Sao lưu dữ liệu người dùng trước khi cài lại Windows, hoặc để chuyển sang máy mới (PLAN.md mục 5.7).

Sao lưu vào `<ổ>\\FVPL-SaoLuu\\<máy>_<người dùng>_<thời gian>\\`. Ổ được chọn tự động, không bao giờ là ổ Windows
(cài lại Windows sẽ xoá): ổ USB / SSD đang chạy tool nếu đủ chỗ, không thì ổ trong máy khác ổ C (ổ D) còn trống nhiều
nhất. Trong thư mục sao lưu:
    Desktop\\ Documents\\ Downloads\\ Pictures\\ (Videos\\ Music\\)   thư mục của người dùng (kể cả đã đổi chỗ)
    Browser\\Chrome|Edge|CocCoc\\Bookmarks                         bookmark trình duyệt
    Outlook\\Signatures\\, Outlook\\Data\\*.pst                      chữ ký và file dữ liệu Outlook
    WiFi\\*.xml                                                    mạng Wi-Fi đã lưu (có mật khẩu)
    Driver\\                                                       driver của hãng (pnputil, cần quyền admin)
    Khac\\C\\KeToan\\                                               thư mục khác IT chọn (ví dụ thư mục ở gốc ổ C)
    manifest.json                                                  máy, người dùng, các mục, danh sách máy in và phần mềm
Khôi phục: tìm bản sao lưu ở mọi ổ, chép vào hồ sơ của người đang đăng nhập (không ghi đè file mới hơn), thư mục khác
về đúng đường dẫn cũ; bookmark cũ của máy được đổi tên giữ lại. Danh sách phần mềm dùng để chọn sẵn ở trang Cài
phần mềm.

Chép bằng robocopy (qua PowerShell, an toàn với tên thư mục có &, %), mỗi mục một lượt của executor để có thanh
tiến độ, log, ghi thời gian chạy.
"""

from __future__ import annotations

import ctypes
import fnmatch
import hashlib
import json
import ntpath
import os
import re
import shutil
import string
import threading
import winreg
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path

from ..actions.loader import parse_action
from ..actions.model import Action
from . import drivers, shell

FOLDER = "FVPL-SaoLuu"
MANIFEST = "manifest.json"
FORMAT = 1
CATEGORY = "Sao lưu dữ liệu"
_SHELL_FOLDERS = r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
ROBOCOPY_OK = tuple(range(8))  # robocopy: dưới 8 là chép được
DRIVER_ESTIMATE = 2 * 1024**3   # chưa xuất thì chưa biết driver nặng bao nhiêu: tính dư 2 GB khi xem đủ chỗ không
FREE_MARGIN = 1024**3           # chừa lại trên ổ đích

# Thư mục ở gốc ổ Windows không phải dữ liệu người dùng (so không phân biệt hoa thường).
SYSTEM_ROOT_FOLDERS = {
    "$recycle.bin", "$windows.~bt", "$windows.~ws", "$winreagent", "$sysreset", "$getcurrent", "boot", "config.msi",
    "documents and settings", "drivers", "esd", "inetpub", "intel", "amd", "nvidia", "msocache", "onedrivetemp",
    "perflogs", "program files", "program files (x86)", "programdata", "recovery", "swsetup", "dell", "lenovo",
    "system volume information", "users", "windows", "windows.old", "xboxgames", "temp", "tmp", "$av_asw",
    "windowsapps", "fvpl-saoluu",
}


@dataclass(frozen=True)
class ItemSpec:
    id: str
    label: str
    kind: str            # folder | bookmarks | signatures | pst | wifi | drivers | extra
    folder: str          # thư mục con trong bản sao lưu
    registry: str = ""   # tên giá trị trong User Shell Folders (thư mục người dùng)
    default_name: str = ""
    default: bool = True  # tick sẵn
    browser: str = ""     # bookmarks: tên tiến trình trình duyệt
    browser_path: str = ""  # bookmarks: chữ có trong đường dẫn exe (tên tiến trình chung chung như "browser")
    source: str = ""      # extra: đường dẫn thật trên máy


ITEMS = (
    ItemSpec("desktop", "Desktop", "folder", "Desktop", "Desktop", "Desktop"),
    ItemSpec("documents", "Documents (Tài liệu)", "folder", "Documents", "Personal", "Documents"),
    ItemSpec("downloads", "Downloads (Tải về)", "folder", "Downloads", "{374DE290-123F-4565-9164-39C4925E467B}",
             "Downloads"),
    ItemSpec("pictures", "Pictures (Ảnh)", "folder", "Pictures", "My Pictures", "Pictures"),
    ItemSpec("videos", "Videos", "folder", "Videos", "My Video", "Videos", default=False),
    ItemSpec("music", "Music", "folder", "Music", "My Music", "Music", default=False),
    ItemSpec("chrome", "Bookmark Chrome", "bookmarks", r"Browser\Chrome", browser="chrome",
             default_name=r"AppData\Local\Google\Chrome\User Data\Default"),
    ItemSpec("edge", "Bookmark Edge", "bookmarks", r"Browser\Edge", browser="msedge",
             default_name=r"AppData\Local\Microsoft\Edge\User Data\Default"),
    ItemSpec("coccoc", "Bookmark Cốc Cốc", "bookmarks", r"Browser\CocCoc", browser="browser", browser_path="CocCoc",
             default_name=r"AppData\Local\CocCoc\Browser\User Data\Default"),
    ItemSpec("signatures", "Chữ ký Outlook", "signatures", r"Outlook\Signatures",
             default_name=r"AppData\Roaming\Microsoft\Signatures"),
    ItemSpec("outlook_data", "File dữ liệu Outlook (.pst)", "pst", r"Outlook\Data",
             default_name=r"AppData\Local\Microsoft\Outlook"),
    ItemSpec("wifi", "Mạng Wi-Fi đã lưu", "wifi", "WiFi"),
    ItemSpec("drivers", "Driver của máy", "drivers", "Driver"),
)
SPECS = {item.id: item for item in ITEMS}


class MigrateError(RuntimeError):
    pass


@dataclass
class Source:
    """Một mục trên máy này: đường dẫn thật, dung lượng, có đang đồng bộ OneDrive không."""
    spec: ItemSpec
    path: str
    exists: bool
    bytes: int = 0
    files: int = 0
    onedrive: bool = False

    @property
    def usable(self) -> bool:
        """Có gì để sao lưu không (thư mục rỗng thì không)."""
        if not self.exists:
            return False
        return self.files > 0 or self.spec.kind in ("bookmarks", "wifi", "drivers")

    @property
    def size_label(self) -> str:
        if self.spec.kind == "wifi":
            return f"{self.files} mạng"
        if self.spec.kind == "drivers":
            return "khoảng 0,5–2 GB"
        text = size_text(self.bytes)
        return text if self.spec.kind == "bookmarks" else f"{text} · {self.files} file"

    @property
    def estimate(self) -> int:
        return DRIVER_ESTIMATE if self.spec.kind == "drivers" else self.bytes


@dataclass
class Backup:
    folder: Path
    computer: str = ""
    user: str = ""
    created: str = ""
    items: list[dict] = field(default_factory=list)
    printers: list[dict] = field(default_factory=list)
    software: list[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        drive = self.folder.drive or str(self.folder)[:2]
        return f"{self.computer} · {self.user} · {self.created} ({drive})"

    def spec(self, item: dict) -> ItemSpec:
        if item.get("kind") == "extra":
            return extra_spec(str(item.get("source") or ""))
        return SPECS[item["id"]]


@dataclass(frozen=True)
class Drive:
    root: str       # "D:\\"
    kind: str       # removable | fixed | network | other
    free: int
    label: str = ""

    @property
    def letter(self) -> str:
        return self.root[:2].upper()

    @property
    def title(self) -> str:
        kinds = {"removable": "USB", "fixed": "ổ trong máy", "network": "ổ mạng"}
        name = f"{self.label} " if self.label else ""
        return f"{name}({self.letter}, {kinds.get(self.kind, 'ổ')})"


# ---------------------------------------------------------------- đường dẫn


def expand_profile(text: str, profile: str) -> str:
    """Thay %USERPROFILE% (và biến khác của tài khoản đó) bằng hồ sơ của người dùng cần chuyển."""
    values = {"USERPROFILE": profile, "APPDATA": ntpath.join(profile, "AppData", "Roaming"),
              "LOCALAPPDATA": ntpath.join(profile, "AppData", "Local"), "HOMEDRIVE": profile[:2],
              "HOMEPATH": profile[2:]}
    return re.sub(r"%([^%]+)%", lambda match: values.get(match.group(1).upper(), os.environ.get(match.group(1),
                                                                                              match.group(0))), text)


def shell_folders(sid: str) -> dict[str, str]:
    """Giá trị User Shell Folders của người dùng (chưa thay biến). Rỗng khi người đó không đăng nhập."""
    result: dict[str, str] = {}
    try:
        with winreg.OpenKey(winreg.HKEY_USERS, f"{sid}\\{_SHELL_FOLDERS}") as key:
            index = 0
            while True:
                try:
                    name, value, _kind = winreg.EnumValue(key, index)
                except OSError:
                    break
                result[name] = str(value)
                index += 1
    except OSError:
        pass
    return result


def item_path(spec: ItemSpec, profile: str, folders: dict[str, str]) -> str:
    if spec.kind == "folder":
        raw = folders.get(spec.registry) or ntpath.join("%USERPROFILE%", spec.default_name)
        return expand_profile(raw, profile)
    if spec.kind == "extra":
        return spec.source
    if spec.kind in ("wifi", "drivers"):
        return ""
    return ntpath.join(profile, spec.default_name)


def extra_spec(path: str) -> ItemSpec:
    """Mục cho một thư mục bất kỳ (ví dụ C:\\KeToan): chép vào Khac\\C-KeToan-<mã>, khôi phục về đúng chỗ cũ.

    Tên thư mục trong bản sao lưu ngắn (không lồng cả đường dẫn cũ) để không vượt 260 ký tự; mã phân biệt hai thư mục
    cùng tên ở hai chỗ khác nhau."""
    path = ntpath.normpath(path)
    drive, rest = ntpath.splitdrive(path)
    letter = drive.rstrip(":").strip("\\") or "UNC"
    name = ntpath.basename(rest.rstrip("\\/")) or "goc"
    digest = hashlib.sha1(path.lower().encode("utf-8")).hexdigest()[:8]
    return ItemSpec(f"extra_{digest}", path, "extra", ntpath.join("Khac", f"{letter}-{name}-{digest[:6]}"),
                    source=path)


def system_drive() -> str:
    return (os.environ.get("SystemDrive") or "C:").upper()


def on_system_drive(path: Path | str) -> bool:
    return str(path)[:2].upper() == system_drive()


def measure(path: str, cancel: threading.Event | None = None, pattern: str = "") -> tuple[int, int]:
    """(số byte, số file) của thư mục, không đi theo junction / symlink, bỏ qua chỗ không đọc được.
    `pattern`: chỉ đếm file khớp (ví dụ *.pst) ở ngay thư mục đó."""
    total = files = 0
    stack = [path]
    while stack:
        if cancel is not None and cancel.is_set():
            break
        current = stack.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    try:
                        if entry.is_symlink() or (hasattr(entry, "is_junction") and entry.is_junction()):
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            if not pattern:
                                stack.append(entry.path)
                        elif entry.is_file(follow_symlinks=False):
                            if pattern and not fnmatch.fnmatch(entry.name.lower(), pattern):
                                continue
                            total += entry.stat(follow_symlinks=False).st_size
                            files += 1
                    except OSError:
                        continue
        except OSError:
            continue
    return total, files


def root_folders(drive: str | None = None) -> list[str]:
    """Thư mục ở gốc ổ Windows có thể là dữ liệu (ví dụ C:\\KeToan): bỏ thư mục của Windows, ẩn, junction."""
    root = (drive or system_drive()) + "\\"
    result = []
    try:
        with os.scandir(root) as entries:
            for entry in entries:
                try:
                    if entry.name.lower() in SYSTEM_ROOT_FOLDERS or entry.name.startswith(("$", ".")):
                        continue
                    if entry.is_symlink() or (hasattr(entry, "is_junction") and entry.is_junction()):
                        continue
                    if not entry.is_dir(follow_symlinks=False):
                        continue
                    attributes = getattr(entry.stat(follow_symlinks=False), "st_file_attributes", 0)
                    if attributes & 0x6:  # FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_SYSTEM
                        continue
                    result.append(entry.path)
                except OSError:
                    continue
    except OSError:
        return []
    return sorted(result, key=str.lower)


def wifi_count() -> int:
    """Số mạng Wi-Fi đã lưu (0 khi máy không có Wi-Fi). Đọc bằng netsh như tab Công cụ khác."""
    from . import wifi
    try:
        return len(wifi.saved_profiles())
    except (wifi.WifiError, OSError):
        return 0


def scan_sources(sid: str, profile: str, cancel: threading.Event | None = None, extras: list[str] = (),
                 machine_items: bool = True) -> list[Source]:
    """Các mục có thể sao lưu (gọi ở thread nền: đếm dung lượng có thể lâu).

    `extras`: thư mục khác (IT thêm, hoặc thư mục ở gốc ổ C). `machine_items`: kèm Wi-Fi, driver.
    """
    folders = shell_folders(sid)
    sources = []
    for spec in ITEMS:
        if spec.kind in ("wifi", "drivers"):
            if not machine_items:
                continue
            if spec.kind == "wifi":
                count = wifi_count()
                sources.append(Source(spec, "Cấu hình Wi-Fi của Windows", count > 0, 0, count))
            else:
                sources.append(Source(spec, "Driver của hãng (oem*.inf), bằng pnputil", True))
            continue
        path = item_path(spec, profile, folders)
        source = Source(spec, path, False, onedrive="\\onedrive" in path.lower())
        if spec.kind == "bookmarks":
            file = ntpath.join(path, "Bookmarks")
            source.exists = os.path.isfile(file)
            if source.exists:
                source.bytes, source.files = os.path.getsize(file), 1
        else:
            source.exists = os.path.isdir(path)
            if source.exists:
                source.bytes, source.files = measure(path, cancel, "*.pst" if spec.kind == "pst" else "")
        sources.append(source)
    for path in extras:
        spec = extra_spec(path)
        source = Source(spec, spec.source, os.path.isdir(spec.source))
        if source.exists:
            source.bytes, source.files = measure(spec.source, cancel)
        sources.append(source)
    return sources


# ---------------------------------------------------------------- nơi lưu


_DRIVE_KINDS = {2: "removable", 3: "fixed", 4: "network"}


def list_drives() -> list[Drive]:
    """Các ổ đang có (USB, ổ trong máy, ổ mạng đã map), bỏ ổ CD và ổ không đọc được."""
    result = []
    try:
        mask = ctypes.windll.kernel32.GetLogicalDrives()
    except (AttributeError, OSError):
        return result
    for index, letter in enumerate(string.ascii_uppercase):
        if not mask & (1 << index):
            continue
        root = f"{letter}:\\"
        kind = _DRIVE_KINDS.get(ctypes.windll.kernel32.GetDriveTypeW(root), "other")
        if kind == "other":
            continue
        try:
            free = shutil.disk_usage(root).free
        except OSError:
            continue
        label = ctypes.create_unicode_buffer(261)
        if kind != "network":
            ctypes.windll.kernel32.GetVolumeInformationW(root, label, 261, None, None, None, None, 0)
        result.append(Drive(root, kind, free, label.value))
    return result


def pick_target(drives: list[Drive], tool_root: Path | None, needed: int) -> Path | None:
    """Nơi lưu tự chọn: không phải ổ Windows, đủ chỗ. Ưu tiên ổ đang chạy tool (USB / SSD IT mang theo), rồi tới ổ
    trong máy còn trống nhiều nhất (ổ D), rồi USB khác. None khi không có ổ nào đủ chỗ."""
    system = system_drive()
    room = [drive for drive in drives if drive.kind in ("removable", "fixed") and drive.letter != system
            and drive.free >= needed + FREE_MARGIN]
    tool = str(tool_root)[:2].upper() if tool_root is not None else ""
    for drive in room:
        if drive.letter == tool:
            return Path(drive.root) / FOLDER
    for kind in ("fixed", "removable"):
        choices = sorted((drive for drive in room if drive.kind == kind), key=lambda drive: -drive.free)
        if choices:
            return Path(choices[0].root) / FOLDER
    return None


def free_space(folder: Path | None) -> int | None:
    while folder is not None and not folder.exists():
        folder = folder.parent if folder.parent != folder else None
    try:
        return shutil.disk_usage(folder).free if folder is not None else None
    except OSError:
        return None


def new_backup_folder(root: Path, computer: str, user: str, now: datetime | None = None) -> Path:
    short = user.split("\\")[-1]
    safe = re.sub(r'[\\/:*?"<>|\s]+', "-", f"{computer}_{short}").strip("-")
    return root / f"{safe}_{(now or datetime.now()):%Y%m%d_%H%M}"


# ---------------------------------------------------------------- bản sao lưu


def write_manifest(folder: Path, computer: str, user: str, tool_version: str, sources: list[Source],
                   printers: list[dict], software: list[str], now: datetime | None = None) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    data = {
        "format": FORMAT, "computer": computer, "user": user, "tool": tool_version,
        "created": (now or datetime.now()).strftime("%d/%m/%Y %H:%M"),
        "items": [{"id": source.spec.id, "kind": source.spec.kind, "label": source.spec.label, "source": source.path,
                   "folder": source.spec.folder, "bytes": source.bytes, "files": source.files} for source in sources],
        "printers": printers, "software": sorted(set(software), key=str.lower),
    }
    file = folder / MANIFEST
    file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return file


def _known(item: object) -> bool:
    if not isinstance(item, dict):
        return False
    if item.get("kind") == "extra":
        return bool(re.match(r"^[A-Za-z]:\\", str(item.get("source") or "")))
    return item.get("id") in SPECS


def read_backup(folder: Path) -> Backup:
    try:
        data = json.loads((folder / MANIFEST).read_text(encoding="utf-8"))
    except OSError as exc:
        raise MigrateError(f"Không đọc được {folder / MANIFEST}: {exc}") from exc
    except ValueError as exc:
        raise MigrateError(f"{folder / MANIFEST} sai định dạng: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        raise MigrateError(f"{folder / MANIFEST} không phải bản sao lưu của tool")
    items = [item for item in data["items"] if _known(item)]
    return Backup(folder, str(data.get("computer") or ""), str(data.get("user") or ""), str(data.get("created") or ""),
                  items, [item for item in data.get("printers") or [] if isinstance(item, dict)],
                  [str(name) for name in data.get("software") or []])


def list_backups(root: Path | None) -> list[Backup]:
    """Các bản sao lưu trong một thư mục FVPL-SaoLuu, mới nhất trước."""
    try:
        if root is None or not root.is_dir():
            return []
        folders = sorted((item for item in root.iterdir() if (item / MANIFEST).is_file()), reverse=True,
                         key=lambda item: item.stat().st_mtime)
    except OSError:
        return []
    result = []
    for folder in folders:
        try:
            result.append(read_backup(folder))
        except MigrateError:
            continue
    return result


def find_backups(drives: list[Drive], extra_roots: list[Path] = ()) -> list[Backup]:
    """Bản sao lưu trên mọi ổ (USB, ổ D…, không đọc ổ mạng cho nhanh) và các thư mục chỉ định, mới nhất trước."""
    roots: list[Path] = [Path(drive.root) / FOLDER for drive in drives if drive.kind != "network"]
    roots += [root for root in extra_roots if root is not None]
    seen: set[str] = set()
    result: list[Backup] = []
    for root in roots:
        key = str(root).lower()
        if key in seen:
            continue
        seen.add(key)
        result += list_backups(root)
    return sorted(result, key=lambda backup: _created_key(backup.created), reverse=True)


def _created_key(text: str) -> datetime:
    try:
        return datetime.strptime(text, "%d/%m/%Y %H:%M")
    except ValueError:
        return datetime.min


# ---------------------------------------------------------------- mục chạy


def _robocopy(source: str, target: str, extra: str = "") -> str:
    return (f"$source = {shell.ps_quote(source.rstrip(chr(92)))}\n"
            f"$target = {shell.ps_quote(target.rstrip(chr(92)))}\n"
            "if (-not (Test-Path -LiteralPath $source)) { Write-Output \"Không thấy $source\"; exit 16 }\n"
            f"& robocopy $source $target {extra}/E /R:1 /W:1 /XJ /MT:8 /NP /NFL /NDL /NJH\n"
            "exit $LASTEXITCODE")


def _copy_bookmarks(source_dir: str, target_dir: str, spec: ItemSpec) -> str:
    running = f"Get-Process -Name {spec.browser} -ErrorAction SilentlyContinue"
    if spec.browser_path:
        running += f" | Where-Object {{ -not $_.Path -or $_.Path -like '*{spec.browser_path}*' }}"
    return (f"if ({running}) {{ exit 4 }}\n"
            f"$source = Join-Path {shell.ps_quote(source_dir)} 'Bookmarks'\n"
            "if (-not (Test-Path -LiteralPath $source)) { Write-Output \"Không thấy $source\"; exit 16 }\n"
            f"$folder = {shell.ps_quote(target_dir)}\n"
            "$target = Join-Path $folder 'Bookmarks'\n"
            "New-Item -ItemType Directory -Force -Path $folder | Out-Null\n"
            "if (Test-Path -LiteralPath $target) {\n"
            "    $old = $target + '.truoc-chuyen-' + (Get-Date -Format 'yyyyMMdd-HHmm')\n"
            "    Move-Item -LiteralPath $target -Destination $old -Force\n"
            f"    Write-Output \"Giữ {spec.label} cũ của máy này ở $old\"\n"
            "}\n"
            "Copy-Item -LiteralPath $source -Destination $target -Force\n"
            f"Write-Output 'Đã chép {spec.label}'\n"
            "exit 0")


# netsh cắt đường dẫn dài quá 260 ký tự (ghi nhầm file ra thư mục khác) và cần ngoặc kép khi có dấu cách: làm việc
# trong thư mục tạm đường dẫn ngắn, truyền cả dòng tham số qua Start-Process cho đúng nguyên văn, xoá thư mục tạm
# ngay sau đó (file có mật khẩu Wi-Fi).
_WIFI_BACKUP = """\
$work = Join-Path ([IO.Path]::GetTempPath()) ('fvpl-wifi-' + [guid]::NewGuid().ToString('N').Substring(0, 8))
New-Item -ItemType Directory -Force -Path $work | Out-Null
try {
    $process = Start-Process -FilePath netsh.exe -ArgumentList ('wlan export profile key=clear folder="{0}"' -f $work) -NoNewWindow -Wait -PassThru
    $files = @(Get-ChildItem -LiteralPath $work -Filter *.xml -ErrorAction SilentlyContinue)
    if (-not $files) { Write-Output ('netsh trả mã {0}, không xuất được mạng Wi-Fi nào.' -f $process.ExitCode); exit 5 }
    New-Item -ItemType Directory -Force -Path $Target | Out-Null
    $files | Copy-Item -Destination $Target -Force
    $protected = @($files | Where-Object { (Get-Content -LiteralPath $_.FullName -Raw) -match '<protected>true</protected>' })
    Write-Output ('Đã lưu {0} mạng Wi-Fi.' -f $files.Count)
    if ($protected) { Write-Output ('{0} mạng không lấy được mật khẩu (tool không chạy bằng quyền admin).' -f $protected.Count) }
} finally {
    Remove-Item -LiteralPath $work -Recurse -Force -ErrorAction SilentlyContinue
}
"""

_WIFI_RESTORE = """\
$files = @(Get-ChildItem -LiteralPath $Source -Filter *.xml -ErrorAction SilentlyContinue)
if (-not $files) { Write-Output 'Bản sao lưu không có mạng Wi-Fi nào.'; exit 16 }
$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
$scope = if ($admin) { 'all' } else { 'current' }
$work = Join-Path ([IO.Path]::GetTempPath()) ('fvpl-wifi-' + [guid]::NewGuid().ToString('N').Substring(0, 8))
New-Item -ItemType Directory -Force -Path $work | Out-Null
$added = 0
try {
    $index = 0
    foreach ($file in $files) {
        $index++
        $copy = Join-Path $work ('w{0}.xml' -f $index)
        Copy-Item -LiteralPath $file.FullName -Destination $copy -Force
        $process = Start-Process -FilePath netsh.exe -ArgumentList ('wlan add profile filename="{0}" user={1}' -f $copy, $scope) -NoNewWindow -Wait -PassThru
        if ($process.ExitCode -eq 0) { $added++ }
    }
} finally {
    Remove-Item -LiteralPath $work -Recurse -Force -ErrorAction SilentlyContinue
}
Write-Output ('Đã thêm {0}/{1} mạng Wi-Fi.' -f $added, $files.Count)
if (-not $added) { exit 5 }
"""

_MESSAGES = {8: "Có file không chép được (đang mở, không có quyền)",
             16: "Không chép được: không thấy thư mục hoặc ổ đích đầy"}


def _action(action_id: str, name: str, script: str, ok_codes=ROBOCOPY_OK, messages: dict | None = None,
            admin: bool = False) -> Action:
    return parse_action({
        "id": action_id, "name": name, "category": CATEGORY, "page": "utilities", "admin": admin,
        "description": "Sao lưu / khôi phục dữ liệu người dùng (trước khi cài lại Windows hoặc khi chuyển máy).",
        "apply": [{"powershell": script, "timeout": 6 * 3600, "ok_codes": list(ok_codes),
                   "messages": messages or _MESSAGES}],
    })


def backup_actions(sources: list[Source], folder: Path) -> list[Action]:
    actions = []
    for source in sources:
        spec = source.spec
        target = str(folder / spec.folder)
        action_id, name = f"move.backup_{spec.id}", f"Sao lưu {spec.label}"
        if spec.kind == "bookmarks":
            script = _robocopy(source.path, target, "Bookmarks ").replace("/E ", "")
        elif spec.kind == "pst":
            script = _robocopy(source.path, target, "*.pst ").replace("/E ", "")
        elif spec.kind == "wifi":
            actions.append(_action(action_id, name, shell.ps_variable_lines({"Target": target}) + _WIFI_BACKUP, (0,),
                                   {5: "Không xuất được mạng Wi-Fi nào"}))
            continue
        elif spec.kind == "drivers":
            actions.append(replace(drivers.backup_action(Path(target)), id=action_id, name=name, category=CATEGORY))
            continue
        else:
            script = _robocopy(source.path, target)
        actions.append(_action(action_id, name, script))
    return actions


def restore_target(spec: ItemSpec, profile: str, folders: dict[str, str]) -> str:
    """Nơi chép về khi khôi phục (chữ hiện trên giao diện cho Wi-Fi, driver)."""
    if spec.kind == "wifi":
        return "Thêm vào Windows"
    if spec.kind == "drivers":
        return "Cài vào máy (pnputil)"
    return item_path(spec, profile, folders)


def restore_actions(backup: Backup, item_ids: list[str], sid: str, profile: str) -> list[Action]:
    folders = shell_folders(sid)
    actions = []
    for item in backup.items:
        if item["id"] not in item_ids:
            continue
        spec = backup.spec(item)
        source = str(backup.folder / (item.get("folder") or spec.folder))
        target = item_path(spec, profile, folders)
        action_id, name = f"move.restore_{spec.id}", f"Khôi phục {spec.label}"
        if spec.kind == "bookmarks":
            actions.append(_action(action_id, name, _copy_bookmarks(source, target, spec), (0,),
                                   {4: f"Đang mở trình duyệt: đóng {spec.label.split(maxsplit=1)[-1]} rồi chạy lại",
                                    16: "Bản sao lưu không có bookmark này"}))
        elif spec.kind == "pst":
            actions.append(_action(action_id, name, _robocopy(source, target, "*.pst /XO ").replace("/E ", ""),
                                   messages={8: "Không chép được file .pst: đóng Outlook rồi chạy lại", 16: _MESSAGES[16]}))
        elif spec.kind == "wifi":
            actions.append(_action(action_id, name, shell.ps_variable_lines({"Source": source}) + _WIFI_RESTORE, (0,),
                                   {5: "Không thêm được mạng Wi-Fi nào", 16: "Bản sao lưu không có mạng Wi-Fi"}))
        elif spec.kind == "drivers":
            actions.append(replace(drivers.restore_action(Path(source)), id=action_id, name=name, category=CATEGORY))
        else:
            # /XO: không ghi đè file trên máy này đã mới hơn bản sao lưu.
            actions.append(_action(action_id, name, _robocopy(source, target, "/XO ")))
    return actions


def match_software(names: list[str], apps) -> list[str]:
    """Id ứng dụng trong danh mục khớp với phần mềm máy cũ đã cài: so tên theo mẫu `detect.uninstall_name`
    (mặc định "<tên>*"). Không xét `detect.file` vì file đó là trên máy đang chạy tool, không phải máy cũ."""
    lowered = [name.lower() for name in names]
    result = []
    for app in apps:
        patterns = [pattern.lower() for pattern in (app.detect_names or (f"{app.name}*",))]
        if any(fnmatch.fnmatchcase(name, pattern) for name in lowered for pattern in patterns):
            result.append(app.id)
    return result


def size_text(size: int) -> str:
    for unit, scale in (("GB", 1024**3), ("MB", 1024**2), ("KB", 1024)):
        if size >= scale:
            return f"{size / scale:.1f} {unit}".replace(".0 ", " ")
    return f"{size} B"
