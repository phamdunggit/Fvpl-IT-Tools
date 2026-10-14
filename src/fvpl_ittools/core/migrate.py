"""Chuyển dữ liệu người dùng từ máy cũ sang máy mới (PLAN.md mục 5.7).

Máy cũ: sao lưu ra ổ mang theo `<tool>\\ChuyenMay\\<máy>_<người dùng>_<thời gian>\\`:
    Desktop\\ Documents\\ Downloads\\ Pictures\\ (Videos\\ Music\\)   thư mục của người dùng (kể cả đã đổi chỗ)
    Browser\\Chrome\\Bookmarks, Browser\\Edge\\Bookmarks              bookmark trình duyệt
    Outlook\\Signatures\\                                           chữ ký Outlook
    manifest.json                                                  máy, người dùng, các mục, danh sách máy in và phần mềm
Máy mới: chép lại vào hồ sơ của người dùng đang đăng nhập (không ghi đè file mới hơn), bookmark cũ của máy mới
được đổi tên giữ lại. Danh sách phần mềm dùng để chọn sẵn ở trang Cài phần mềm.

Chép bằng robocopy (qua PowerShell, an toàn với tên thư mục có &, %), mỗi mục một lượt của executor để có
thanh tiến độ, log, ghi thời gian chạy.
"""

from __future__ import annotations

import fnmatch
import json
import ntpath
import os
import re
import threading
import winreg
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from ..actions.loader import parse_action
from ..actions.model import Action
from . import shell

FOLDER = "ChuyenMay"
MANIFEST = "manifest.json"
FORMAT = 1
_SHELL_FOLDERS = r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
ROBOCOPY_OK = tuple(range(8))  # robocopy: dưới 8 là chép được


@dataclass(frozen=True)
class ItemSpec:
    id: str
    label: str
    kind: str            # folder | bookmarks | signatures
    folder: str          # thư mục con trong bản sao lưu
    registry: str = ""   # tên giá trị trong User Shell Folders (thư mục người dùng)
    default_name: str = ""
    default: bool = True  # tick sẵn
    browser: str = ""     # bookmarks: tên tiến trình trình duyệt


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
    ItemSpec("signatures", "Chữ ký Outlook", "signatures", r"Outlook\Signatures",
             default_name=r"AppData\Roaming\Microsoft\Signatures"),
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
        return f"{self.computer} · {self.user} · {self.created}"


# ---------------------------------------------------------------- đường dẫn


def expand_profile(text: str, profile: str) -> str:
    """Thay %USERPROFILE% (và biến khác của tài khoản đó) bằng hồ sơ của người dùng cần chuyển."""
    values = {"USERPROFILE": profile, "APPDATA": ntpath.join(profile, "AppData", "Roaming"),
              "LOCALAPPDATA": ntpath.join(profile, "AppData", "Local"), "HOMEDRIVE": profile[:2],
              "HOMEPATH": profile[2:]}
    return re.sub(r"%([^%]+)%", lambda match: values.get(match.group(1).upper(), os.environ.get(match.group(1),
                                                                                              match.group(0))), text)


def shell_folders(sid: str) -> dict[str, str]:
    """Giá trị User Shell Folders của người dùng (chưa thay biến)."""
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
    return ntpath.join(profile, spec.default_name)


def measure(path: str, cancel: threading.Event | None = None) -> tuple[int, int]:
    """(số byte, số file) của thư mục, không đi theo junction / symlink, bỏ qua chỗ không đọc được."""
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
                            stack.append(entry.path)
                        elif entry.is_file(follow_symlinks=False):
                            total += entry.stat(follow_symlinks=False).st_size
                            files += 1
                    except OSError:
                        continue
        except OSError:
            continue
    return total, files


def scan_sources(sid: str, profile: str, cancel: threading.Event | None = None) -> list[Source]:
    """Các mục có thể sao lưu trên máy này (gọi ở thread nền: đếm dung lượng có thể lâu)."""
    folders = shell_folders(sid)
    sources = []
    for spec in ITEMS:
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
                source.bytes, source.files = measure(path, cancel)
        sources.append(source)
    return sources


def backups_root(portable_root: Path | None) -> Path | None:
    return portable_root / FOLDER if portable_root is not None else None


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
        "items": [{"id": source.spec.id, "label": source.spec.label, "source": source.path,
                   "folder": source.spec.folder, "bytes": source.bytes, "files": source.files} for source in sources],
        "printers": printers, "software": sorted(set(software), key=str.lower),
    }
    file = folder / MANIFEST
    file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return file


def read_backup(folder: Path) -> Backup:
    try:
        data = json.loads((folder / MANIFEST).read_text(encoding="utf-8"))
    except OSError as exc:
        raise MigrateError(f"Không đọc được {folder / MANIFEST}: {exc}") from exc
    except ValueError as exc:
        raise MigrateError(f"{folder / MANIFEST} sai định dạng: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        raise MigrateError(f"{folder / MANIFEST} không phải bản sao lưu của tool")
    items = [item for item in data["items"] if isinstance(item, dict) and item.get("id") in SPECS]
    return Backup(folder, str(data.get("computer") or ""), str(data.get("user") or ""), str(data.get("created") or ""),
                  items, [item for item in data.get("printers") or [] if isinstance(item, dict)],
                  [str(name) for name in data.get("software") or []])


def list_backups(root: Path | None) -> list[Backup]:
    """Các bản sao lưu trong thư mục ChuyenMay, mới nhất trước."""
    if root is None or not root.is_dir():
        return []
    result = []
    for folder in sorted((item for item in root.iterdir() if (item / MANIFEST).is_file()), reverse=True,
                         key=lambda item: item.stat().st_mtime):
        try:
            result.append(read_backup(folder))
        except MigrateError:
            continue
    return result


# ---------------------------------------------------------------- mục chạy


def _robocopy(source: str, target: str, extra: str = "") -> str:
    return (f"$source = {shell.ps_quote(source.rstrip(chr(92)))}\n"
            f"$target = {shell.ps_quote(target.rstrip(chr(92)))}\n"
            "if (-not (Test-Path -LiteralPath $source)) { Write-Output \"Không thấy $source\"; exit 16 }\n"
            f"& robocopy $source $target {extra}/E /R:1 /W:1 /XJ /MT:8 /NP /NFL /NDL /NJH\n"
            "exit $LASTEXITCODE")


def _copy_bookmarks(source_dir: str, target_dir: str, browser: str, label: str) -> str:
    return (f"if (Get-Process -Name {browser} -ErrorAction SilentlyContinue) {{ exit 4 }}\n"
            f"$source = Join-Path {shell.ps_quote(source_dir)} 'Bookmarks'\n"
            f"$folder = {shell.ps_quote(target_dir)}\n"
            "$target = Join-Path $folder 'Bookmarks'\n"
            "New-Item -ItemType Directory -Force -Path $folder | Out-Null\n"
            "if (Test-Path -LiteralPath $target) {\n"
            "    $old = $target + '.truoc-chuyen-' + (Get-Date -Format 'yyyyMMdd-HHmm')\n"
            "    Move-Item -LiteralPath $target -Destination $old -Force\n"
            f"    Write-Output \"Giữ {label} cũ của máy này ở $old\"\n"
            "}\n"
            "Copy-Item -LiteralPath $source -Destination $target -Force\n"
            f"Write-Output 'Đã chép {label}'\n"
            "exit 0")


def _action(action_id: str, name: str, script: str, ok_codes=ROBOCOPY_OK, messages: dict | None = None) -> Action:
    return parse_action({
        "id": action_id, "name": name, "category": "Chuyển máy", "page": "utilities", "admin": False,
        "description": "Chép dữ liệu người dùng giữa máy cũ và máy mới qua ổ mang theo.",
        "apply": [{"powershell": script, "timeout": 6 * 3600, "ok_codes": list(ok_codes),
                   "messages": messages or {8: "Có file không chép được (đang mở, không có quyền)",
                                            16: "Không chép được: không thấy thư mục hoặc ổ đích đầy"}}],
    })


def backup_actions(sources: list[Source], folder: Path) -> list[Action]:
    actions = []
    for source in sources:
        spec = source.spec
        target = str(folder / spec.folder)
        if spec.kind == "bookmarks":
            script = _robocopy(source.path, target, "Bookmarks ").replace("/E ", "")
        else:
            script = _robocopy(source.path, target)
        actions.append(_action(f"move.backup_{spec.id}", f"Sao lưu {spec.label}", script))
    return actions


def restore_actions(backup: Backup, item_ids: list[str], sid: str, profile: str) -> list[Action]:
    folders = shell_folders(sid)
    actions = []
    for item in backup.items:
        if item["id"] not in item_ids:
            continue
        spec = SPECS[item["id"]]
        source = str(backup.folder / spec.folder)
        target = item_path(spec, profile, folders)
        if spec.kind == "bookmarks":
            script = _copy_bookmarks(source, target, spec.browser, spec.label)
            actions.append(_action(f"move.restore_{spec.id}", f"Khôi phục {spec.label}", script, (0,),
                                   {4: f"Đang mở trình duyệt: đóng {spec.label.split()[-1]} rồi chạy lại"}))
        else:
            # /XO: không ghi đè file trên máy mới đã mới hơn bản sao lưu.
            actions.append(_action(f"move.restore_{spec.id}", f"Khôi phục {spec.label}", _robocopy(source, target, "/XO ")))
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
