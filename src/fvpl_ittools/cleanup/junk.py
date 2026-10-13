"""Các loại rác, quét dung lượng và xoá.

Nguyên tắc an toàn:
- Không bao giờ đi theo junction hoặc symlink (profile có junction như "Application Data" trỏ vòng, Windows.old
  có junction trỏ ra ngoài). Gặp là bỏ qua, không xoá cả bản thân nó.
- Chỉ xoá nội dung bên trong thư mục của từng loại, không xoá thư mục gốc.
- Thư mục Temp: giữ file sửa trong 24 giờ gần đây (bộ cài đang chạy có thể còn dùng).
- File đang bị khoá thì bỏ qua và đếm lại để báo.
- Windows.old và cache Delivery Optimization dọn bằng Disk Cleanup (cleanmgr /sagerun): không phụ thuộc ngôn
  ngữ Windows, tự xử lý quyền của Windows.old.
"""

from __future__ import annotations

import ctypes
import logging
import os
import stat
import threading
import time
import winreg
from dataclasses import dataclass, field
from pathlib import Path

from ..core import shell
from ..core.executor import Env, Level, RunContext

log = logging.getLogger(__name__)

DAY = 24 * 3600
SAGERUN = 4242  # số hiệu bộ thiết lập Disk Cleanup riêng của tool
_VOLUME_CACHES = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\VolumeCaches"


@dataclass(frozen=True)
class Category:
    id: str
    name: str
    description: str
    risk: str = "safe"                    # safe | caution
    admin: bool = True                    # cần quyền admin để đọc / xoá
    checked: bool = True                  # tick sẵn sau khi quét
    min_age: int = 0                      # giây; file mới hơn thì giữ lại
    services: tuple[str, ...] = ()        # dừng trước khi xoá, chạy lại sau
    cleanmgr: tuple[str, ...] = ()        # dọn bằng trình dọn có sẵn của Disk Cleanup thay vì tự xoá
    keep: tuple[str, ...] = ()            # tên file luôn giữ (ví dụ desktop.ini trong thùng rác)


CATEGORIES: tuple[Category, ...] = (
    Category(
        "user_temp", "Temp của người dùng",
        "Thư mục Temp của người đang đăng nhập. Giữ lại file sửa trong 24 giờ gần đây.", min_age=DAY,
        admin=False,
    ),
    Category(
        "windows_temp", "Temp của Windows",
        "C:\\Windows\\Temp. Giữ lại file sửa trong 24 giờ gần đây.", min_age=DAY,
    ),
    Category(
        "wu_download", "Bản cập nhật Windows đã tải",
        "SoftwareDistribution\\Download: bản cập nhật đã cài xong hoặc tải dở. Dịch vụ Windows Update được dừng "
        "trong lúc xoá; bản nào còn cần sẽ được tải lại.",
        services=("wuauserv", "bits"),
    ),
    Category(
        "delivery_optimization", "Cache Delivery Optimization",
        "Bản cập nhật Windows và Store giữ lại để chia sẻ cho máy khác trong mạng. Dọn bằng Disk Cleanup.",
        cleanmgr=("Delivery Optimization Files",),
    ),
    Category(
        "crash_dumps", "File dump khi lỗi và báo cáo lỗi",
        "Minidump và MEMORY.DMP sau màn hình xanh, LiveKernelReports, báo cáo Windows Error Reporting, CrashDumps "
        "của người dùng. Nếu đang điều tra màn hình xanh thì lấy file trong C:\\Windows\\Minidump ra trước.",
    ),
    Category(
        "browser_cache", "Cache trình duyệt (Chrome, Edge)",
        "Cache của Chrome và Edge của người đang đăng nhập (ảnh, script tạm của trang web). Không đụng mật khẩu, "
        "bookmark, lịch sử, cookie. Nên đóng trình duyệt trước; file đang dùng sẽ được bỏ qua.",
        admin=False, checked=False,
    ),
    Category(
        "recycle_bin", "Thùng rác của người dùng",
        "Thùng rác của người đang đăng nhập trên mọi ổ cứng. Xoá rồi không lấy lại được, hỏi người dùng trước.",
        risk="caution", admin=False, checked=False, keep=("desktop.ini",),
    ),
    Category(
        "windows_old", "Bản Windows cũ (Windows.old)",
        "Windows.old và file cài đặt tạm sau khi nâng cấp Windows. Xoá rồi không quay về bản Windows trước được "
        "(Settings → Recovery → Go back). Dọn bằng Disk Cleanup, có thể mất vài phút.",
        risk="caution", checked=False, cleanmgr=("Previous Installations", "Temporary Setup Files"),
    ),
)
CATEGORY_BY_ID = {category.id: category for category in CATEGORIES}


def fixed_drives() -> list[Path]:
    kernel32 = ctypes.windll.kernel32
    kernel32.GetDriveTypeW.argtypes = [ctypes.c_wchar_p]
    mask = kernel32.GetLogicalDrives()
    drives = []
    for index in range(26):
        if mask & (1 << index):
            root = f"{chr(65 + index)}:\\"
            if kernel32.GetDriveTypeW(root) == 3:  # DRIVE_FIXED
                drives.append(Path(root))
    return drives


def browser_cache_paths(local: Path) -> list[Path]:
    """Thư mục cache của từng profile Chrome / Edge. Chỉ cache: không có Login Data, Bookmarks, History, Cookies."""
    paths: list[Path] = []
    for user_data in (local / "Google" / "Chrome" / "User Data", local / "Microsoft" / "Edge" / "User Data"):
        try:
            profiles = [item for item in user_data.iterdir()
                        if item.is_dir() and (item.name == "Default" or item.name.startswith("Profile "))]
        except OSError:
            continue
        paths += [user_data / "ShaderCache", user_data / "GrShaderCache"]
        for profile in sorted(profiles):
            paths += [profile / "Cache", profile / "Code Cache", profile / "GPUCache",
                      profile / "Service Worker" / "CacheStorage"]
    return paths


def locations(category: Category, env: Env) -> list[Path]:
    """Thư mục (xoá nội dung bên trong) hoặc file (xoá chính nó) của một loại rác."""
    windows = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    programdata = Path(os.environ.get("ProgramData", r"C:\ProgramData"))
    system_drive = Path(os.environ.get("SystemDrive", "C:") + "\\")
    profile = env.target_user.profile_path
    local = Path(profile) / "AppData" / "Local" if profile else None
    wer = programdata / "Microsoft" / "Windows" / "WER"
    if category.id == "user_temp":
        return [local / "Temp"] if local else []
    if category.id == "windows_temp":
        return [windows / "Temp"]
    if category.id == "wu_download":
        return [windows / "SoftwareDistribution" / "Download"]
    if category.id == "delivery_optimization":
        return [windows / "ServiceProfiles" / "NetworkService" / "AppData" / "Local" / "Microsoft" / "Windows"
                / "DeliveryOptimization" / "Cache"]
    if category.id == "crash_dumps":
        paths = [windows / "Minidump", windows / "MEMORY.DMP", windows / "LiveKernelReports",
                 wer / "ReportArchive", wer / "ReportQueue", wer / "Temp"]
        if local:
            paths += [local / "CrashDumps", local / "Microsoft" / "Windows" / "WER" / "ReportArchive",
                      local / "Microsoft" / "Windows" / "WER" / "ReportQueue"]
        return paths
    if category.id == "browser_cache":
        return browser_cache_paths(local) if local else []
    if category.id == "recycle_bin":
        return [drive / "$Recycle.Bin" / env.target_user.sid for drive in fixed_drives()]
    if category.id == "windows_old":
        return [system_drive / "Windows.old", system_drive / "$Windows.~BT", system_drive / "$Windows.~WS"]
    raise KeyError(category.id)


# ---------------------------------------------------------------- quét


@dataclass
class Scan:
    category: Category
    size: int = 0
    files: int = 0
    readable: bool = True  # False nếu không đọc được một phần (thường do thiếu quyền admin)


def _is_link(entry: os.DirEntry) -> bool:
    return entry.is_symlink() or entry.is_junction()


def _is_reparse(info: os.stat_result) -> bool:
    """Junction hoặc symlink (kết quả của os.lstat)."""
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_reparse_tag", 0))


def _measure(path: Path, min_age: int, keep: tuple[str, ...], now: float) -> tuple[int, int, bool]:
    size = files = 0
    readable = True
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return 0, 0, True
    except OSError:
        return 0, 0, False
    if _is_reparse(info):
        return 0, 0, True
    if not stat.S_ISDIR(info.st_mode):
        too_new = min_age and now - info.st_mtime < min_age
        return (0, 0, True) if too_new or path.name.lower() in keep else (info.st_size, 1, True)
    stack = [str(path)]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    try:
                        if _is_link(entry):
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(entry.path)
                            continue
                        if entry.name.lower() in keep:
                            continue
                        entry_info = entry.stat(follow_symlinks=False)
                        if min_age and now - entry_info.st_mtime < min_age:
                            continue
                        size += entry_info.st_size
                        files += 1
                    except OSError:
                        readable = False
        except FileNotFoundError:
            continue
        except OSError:
            readable = False
    return size, files, readable


def scan(category: Category, env: Env, cancel: threading.Event | None = None) -> Scan:
    result = Scan(category)
    now = time.time()
    keep = tuple(name.lower() for name in category.keep)
    for path in locations(category, env):
        if cancel is not None and cancel.is_set():
            break
        size, files, readable = _measure(path, category.min_age, keep, now)
        result.size += size
        result.files += files
        result.readable &= readable
    return result


def scan_all(env: Env, cancel: threading.Event | None = None) -> list[Scan]:
    return [scan(category, env, cancel) for category in CATEGORIES]


# ---------------------------------------------------------------- xoá


@dataclass
class Cleaned:
    category: Category
    freed: int = 0
    deleted: int = 0
    failed: int = 0
    message: str = ""


@dataclass
class CleanupResult:
    results: list[Cleaned] = field(default_factory=list)
    cancelled: bool = False

    @property
    def freed(self) -> int:
        return sum(item.freed for item in self.results)


def _remove_file(path: str, size: int, stats: Cleaned) -> None:
    try:
        os.remove(path)
    except PermissionError:
        # File chỉ đọc: bỏ thuộc tính rồi thử lại. Đang bị khoá thì vẫn lỗi, đếm vào failed.
        try:
            os.chmod(path, stat.S_IWRITE)
            os.remove(path)
        except OSError:
            stats.failed += 1
            return
    except FileNotFoundError:
        return
    except OSError:
        stats.failed += 1
        return
    stats.freed += size
    stats.deleted += 1


def _clean_dir(folder: str, min_age: int, keep: tuple[str, ...], now: float, stats: Cleaned,
               cancel: threading.Event, is_root: bool) -> None:
    try:
        entries = list(os.scandir(folder))
    except FileNotFoundError:
        return
    except OSError:
        stats.failed += 1
        return
    for entry in entries:
        if cancel.is_set():
            return
        try:
            if _is_link(entry):
                continue  # không đi theo, không xoá
            if entry.is_dir(follow_symlinks=False):
                _clean_dir(entry.path, min_age, keep, now, stats, cancel, is_root=False)
                continue
            if entry.name.lower() in keep:
                continue
            info = entry.stat(follow_symlinks=False)
            if min_age and now - info.st_mtime < min_age:
                continue
            _remove_file(entry.path, info.st_size, stats)
        except OSError:
            stats.failed += 1
    if not is_root:
        try:
            os.rmdir(folder)  # chỉ xoá được khi đã rỗng
        except OSError:
            pass


def clean_locations(category: Category, paths: list[Path], cancel: threading.Event) -> Cleaned:
    stats = Cleaned(category)
    now = time.time()
    keep = tuple(name.lower() for name in category.keep)
    for path in paths:
        if cancel.is_set():
            break
        try:
            info = os.lstat(path)
        except OSError:
            continue
        if _is_reparse(info):
            continue  # gốc là junction / symlink: không đụng
        if stat.S_ISDIR(info.st_mode):
            _clean_dir(str(path), category.min_age, keep, now, stats, cancel, is_root=True)
        elif not (category.min_age and now - info.st_mtime < category.min_age):
            _remove_file(str(path), info.st_size, stats)
    return stats


def _set_services(names: tuple[str, ...], start: bool, ctx: RunContext) -> None:
    quoted = ", ".join(shell.ps_quote(name) for name in names)
    verb = "Start-Service" if start else "Stop-Service -Force"
    ctx.say(Level.CMD, f"> {'Chạy lại' if start else 'Dừng'} dịch vụ {', '.join(names)}")
    shell.run_powershell(f"foreach ($name in @({quoted})) {{ {verb} -Name $name -ErrorAction SilentlyContinue }}",
                         timeout=120)


def _run_cleanmgr(category: Category, ctx: RunContext) -> str:
    """Bật các trình dọn của Disk Cleanup cho bộ thiết lập SAGERUN, chạy, rồi xoá thiết lập."""
    flag = f"StateFlags{SAGERUN:04d}"
    opened = []
    try:
        for handler in category.cleanmgr:
            try:
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, f"{_VOLUME_CACHES}\\{handler}", 0,
                                     winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY)
            except OSError:
                continue  # máy không có trình dọn này
            with key:
                winreg.SetValueEx(key, flag, 0, winreg.REG_DWORD, 2)
            opened.append(handler)
        if not opened:
            return "Máy không có trình dọn tương ứng của Disk Cleanup"
        command = [os.path.join(shell.system_dir(), "cleanmgr.exe"), f"/sagerun:{SAGERUN}"]
        ctx.say(Level.CMD, f"> cleanmgr /sagerun:{SAGERUN} ({', '.join(opened)})")
        result = shell.run_process(command, timeout=3600, cancel=ctx.cancel)
        if result.cancelled:
            return "Đã huỷ"
        if result.timed_out:
            return "Disk Cleanup chạy quá 1 giờ, đã dừng"
        return ""
    finally:
        for handler in opened:
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, f"{_VOLUME_CACHES}\\{handler}", 0,
                                    winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY) as key:
                    winreg.DeleteValue(key, flag)
            except OSError:
                pass


def clean_category(category: Category, ctx: RunContext) -> Cleaned:
    paths = locations(category, ctx.env)
    if category.cleanmgr:
        before = scan(category, ctx.env)
        message = _run_cleanmgr(category, ctx)
        after = scan(category, ctx.env)
        stats = Cleaned(category, freed=max(before.size - after.size, 0),
                        deleted=max(before.files - after.files, 0), message=message)
        return stats
    if category.services:
        _set_services(category.services, start=False, ctx=ctx)
    try:
        return clean_locations(category, paths, ctx.cancel)
    finally:
        if category.services:
            _set_services(category.services, start=True, ctx=ctx)


def clean(categories: list[Category], ctx: RunContext) -> CleanupResult:
    batch = CleanupResult()
    for category in categories:
        if ctx.cancel.is_set():
            batch.cancelled = True
            break
        ctx.say(Level.HEADER, f"▶ Dọn {category.name}")
        try:
            stats = clean_category(category, ctx)
        except Exception as exc:  # lỗi một loại không được làm dừng các loại khác
            log.exception("Lỗi khi dọn %s", category.id)
            stats = Cleaned(category, message=str(exc) or exc.__class__.__name__)
        batch.results.append(stats)
        note = f", {stats.failed} file đang bị khoá hoặc không xoá được" if stats.failed else ""
        if stats.message:
            ctx.say(Level.WARN, f"⚠ {category.name}: {stats.message}")
        ctx.say(Level.OK, f"✔ {category.name}: giải phóng {size_text(stats.freed)} ({stats.deleted} file){note}")
    if ctx.cancel.is_set():
        batch.cancelled = True
    ctx.say(Level.OK if not batch.cancelled else Level.WARN,
            f"Kết thúc dọn rác: giải phóng {size_text(batch.freed)}" + (" (đã huỷ giữa chừng)" if batch.cancelled else "."))
    return batch


def size_text(size: int) -> str:
    units = ("B", "KB", "MB", "GB", "TB")
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit in ("B", "KB"):
                return f"{value:.0f} {unit}"
            return f"{value:.1f} {unit}".replace(".", ",")
        value /= 1024
    return f"{size} B"
