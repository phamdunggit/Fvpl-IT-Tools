"""Danh mục phần mềm và profile phòng ban, đọc từ apps.yaml (PLAN.md mục 6.4).

Bản trên share (`<share_root>\\config\\apps.yaml`) được ưu tiên để IT sửa danh mục mà không phải build lại
tool. Không vào được share thì dùng bản đóng gói kèm theo (data/apps.yaml).
Khai báo sai thì mục / profile đó bị loại và báo lỗi tiếng Việt, phần còn lại vẫn dùng được.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from ..core import paths

BUNDLED_FILE = paths.DATA_DIR / "apps.yaml"
SHARE_RELATIVE = Path("config") / "apps.yaml"

SOURCES = ("winget", "share")
SHARE_TYPES = ("msi", "exe", "iso", "portable")
SCOPES = ("machine", "user")
PLACEHOLDERS = ("share", "programfiles", "programfiles_x86")

_ID = re.compile(r"^[a-z0-9][a-z0-9_\-]*$")
_WINGET_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.\-_+]*$")
_PLACEHOLDER = re.compile(r"\{([a-z_0-9]+)\}")
_APP_KEYS = {
    "id", "name", "group", "source", "winget_id", "type", "installer", "path", "setup", "args", "exe", "folder",
    "autostart", "detect", "scope", "description", "timeout", "conflicts",
}
_PROFILE_KEYS = {"name", "extends", "apps", "description"}


class CatalogError(ValueError):
    pass


@dataclass(frozen=True, kw_only=True)
class App:
    id: str
    name: str
    group: str
    source: str                        # winget | share
    winget_id: str = ""
    type: str = ""                     # share: msi | exe | iso | portable
    installer: str = ""                # share msi/exe/iso: file cài; portable: thư mục nguồn
    setup: str = ""                    # iso: file chạy bên trong ISO (mặc định setup.exe)
    args: str = ""                     # tham số thêm cho bộ cài
    exe: str = ""                      # portable: file chạy chính (để tạo shortcut và nhận biết đã cài)
    folder: str = ""                   # portable: tên thư mục trong Program Files (mặc định = id)
    autostart: bool = False            # portable: chạy cùng Windows cho mọi người dùng
    detect_names: tuple[str, ...] = ()  # mẫu tên trong Programs and Features, ví dụ "Microsoft 365*"
    detect_file: str = ""              # có file này nghĩa là đã cài
    conflict_names: tuple[str, ...] = ()  # máy có phần mềm khớp mẫu này (ví dụ "Microsoft 365*") thì không cài
    scope: str = "machine"             # user: bộ cài chỉ cài cho tài khoản đang chạy nó
    description: str = ""
    timeout: int = 1800

    @property
    def source_label(self) -> str:
        return "winget" if self.source == "winget" else f"share ({self.type})"

    @property
    def install_folder(self) -> str:
        return self.folder or self.id


@dataclass(frozen=True, kw_only=True)
class Profile:
    id: str
    name: str
    extends: tuple[str, ...] = ()
    apps: tuple[str, ...] = ()
    description: str = ""


@dataclass
class Catalog:
    apps: list[App] = field(default_factory=list)
    profiles: list[Profile] = field(default_factory=list)
    source: str = ""
    errors: list[str] = field(default_factory=list)

    def app(self, app_id: str) -> App | None:
        return next((app for app in self.apps if app.id == app_id), None)

    def profile_apps(self, profile_id: str) -> list[App]:
        """Các ứng dụng của profile, gồm cả profile được kế thừa (ứng dụng của profile cha đứng trước)."""
        by_id = {profile.id: profile for profile in self.profiles}
        ordered: list[str] = []

        def walk(current: str) -> None:  # kế thừa vòng tròn đã bị loại lúc nạp
            profile = by_id[current]
            for parent in profile.extends:
                walk(parent)
            for app_id in profile.apps:
                if app_id not in ordered:
                    ordered.append(app_id)

        walk(profile_id)
        return [app for app_id in ordered if (app := self.app(app_id)) is not None]


def expand(text: str, share_root: str) -> str:
    """Thay {share}, {programfiles}, {programfiles_x86} trong đường dẫn."""
    values = {
        "share": share_root.rstrip("\\"),
        "programfiles": os.environ.get("ProgramW6432") or os.environ.get("ProgramFiles", r"C:\Program Files"),
        "programfiles_x86": os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
    }
    return _PLACEHOLDER.sub(lambda match: values.get(match.group(1), match.group(0)), text)


def uses_share(app: App) -> bool:
    return any("{share}" in text for text in (app.installer, app.args, app.detect_file))


# ---------------------------------------------------------------- nạp


def share_catalog_path(share_root: str) -> Path | None:
    return Path(share_root) / SHARE_RELATIVE if share_root else None


def load_catalog(share_root: str = "") -> Catalog:
    """Bản trên share nếu có, ngược lại bản đóng gói. Có thể chậm nếu share không trả lời (gọi ở thread nền)."""
    share_file = share_catalog_path(share_root)
    if share_file is not None:
        try:
            if share_file.is_file():
                return load_catalog_file(share_file)
        except OSError:
            pass
    return load_catalog_file(BUNDLED_FILE)


def load_catalog_file(file: Path) -> Catalog:
    catalog = Catalog(source=str(file))
    try:
        data = yaml.safe_load(file.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        catalog.errors.append(f"{file.name}: không đọc được file ({exc})")
        return catalog
    if not isinstance(data, dict) or set(data) - {"apps", "profiles"}:
        catalog.errors.append(f"{file.name}: file cần đúng hai phần 'apps:' và 'profiles:'")
        return catalog

    raw_apps = data.get("apps") or []
    if not isinstance(raw_apps, list):
        catalog.errors.append(f"{file.name}: 'apps' phải là danh sách, mỗi ứng dụng bắt đầu bằng '- id: …'")
        raw_apps = []
    for index, raw in enumerate(raw_apps, start=1):
        label = f"{file.name} ứng dụng {index}"
        if isinstance(raw, dict) and isinstance(raw.get("id"), str):
            label += f" ({raw['id']})"
        try:
            app = parse_app(raw)
        except CatalogError as exc:
            catalog.errors.append(f"{label}: {exc}")
            continue
        if catalog.app(app.id) is not None:
            catalog.errors.append(f"{label}: trùng id")
            continue
        catalog.apps.append(app)

    raw_profiles = data.get("profiles") or {}
    if not isinstance(raw_profiles, dict):
        catalog.errors.append(f"{file.name}: 'profiles' phải là các khối 'tên-profile: …'")
        raw_profiles = {}
    parsed: list[Profile] = []
    failed: set[str] = set()
    for profile_id, raw in raw_profiles.items():
        try:
            parsed.append(parse_profile(str(profile_id), raw, {app.id for app in catalog.apps}))
        except CatalogError as exc:
            catalog.errors.append(f"{file.name} profile {profile_id}: {exc}")
            failed.add(str(profile_id))
    catalog.profiles = _check_inheritance(parsed, failed, catalog.errors, file.name)
    return catalog


def _text(raw: dict, key: str, required: bool = False) -> str:
    value = raw.get(key, "")
    if value is None:
        value = ""
    if not isinstance(value, (str, int, float)) or isinstance(value, bool):
        raise CatalogError(f"'{key}' phải là chữ")
    value = str(value).strip()
    if required and not value:
        raise CatalogError(f"thiếu '{key}'")
    return value


def _check_placeholders(text: str, key: str) -> None:
    for name in _PLACEHOLDER.findall(text):
        if name not in PLACEHOLDERS:
            raise CatalogError(f"'{key}' có {{{name}}} không hiểu (dùng {', '.join('{' + p + '}' for p in PLACEHOLDERS)})")


def parse_app(raw: Any) -> App:
    if not isinstance(raw, dict):
        raise CatalogError("mỗi ứng dụng phải là một khối 'khoá: giá trị'")
    unknown = sorted(set(raw) - _APP_KEYS)
    if unknown:
        raise CatalogError(f"không hiểu khoá {', '.join(unknown)}")
    app_id = _text(raw, "id", required=True)
    if not _ID.match(app_id):
        raise CatalogError("id chỉ gồm chữ thường không dấu, số, '-' và '_' (ví dụ chrome, 7zip, token-ca)")
    source = _text(raw, "source", required=True)
    if source not in SOURCES:
        raise CatalogError(f"'source' chỉ nhận {', '.join(SOURCES)}")
    scope = _text(raw, "scope") or "machine"
    if scope not in SCOPES:
        raise CatalogError(f"'scope' chỉ nhận {', '.join(SCOPES)}")
    autostart = raw.get("autostart", False)
    if not isinstance(autostart, bool):
        raise CatalogError("'autostart' phải là true hoặc false")
    timeout = raw.get("timeout", 1800)
    if not isinstance(timeout, int) or isinstance(timeout, bool) or timeout <= 0:
        raise CatalogError("'timeout' phải là số giây lớn hơn 0")

    detect_names: tuple[str, ...] = ()
    detect_file = ""
    detect = raw.get("detect")
    if detect is not None:
        if not isinstance(detect, dict) or not detect or set(detect) - {"uninstall_name", "file"}:
            raise CatalogError("'detect' nhận { uninstall_name: 'Tên*|Tên khác*' } hoặc { file: '{programfiles}\\...' }")
        names = _text(detect, "uninstall_name")
        detect_names = tuple(part.strip() for part in names.split("|") if part.strip())
        detect_file = _text(detect, "file")
        _check_placeholders(detect_file, "detect.file")

    conflicts = raw.get("conflicts")
    if conflicts is not None and not isinstance(conflicts, str):
        raise CatalogError("'conflicts' là mẫu tên trong Programs and Features, ví dụ 'Microsoft 365*|Microsoft Office Professional*'")
    conflict_names = tuple(part.strip() for part in (conflicts or "").split("|") if part.strip())

    args = _text(raw, "args")
    _check_placeholders(args, "args")
    values: dict[str, Any] = {
        "conflict_names": conflict_names,
        "id": app_id,
        "name": _text(raw, "name", required=True),
        "group": _text(raw, "group") or "Khác",
        "source": source,
        "args": args,
        "scope": scope,
        "description": _text(raw, "description"),
        "timeout": timeout,
        "detect_names": detect_names,
        "detect_file": detect_file,
    }
    if source == "winget":
        extra = sorted({"type", "installer", "path", "setup", "exe", "folder", "autostart"} & set(raw))
        if extra:
            raise CatalogError(f"ứng dụng winget không dùng khoá {', '.join(extra)}")
        winget_id = _text(raw, "winget_id", required=True)
        if not _WINGET_ID.match(winget_id):
            raise CatalogError("winget_id không hợp lệ (ví dụ Google.Chrome)")
        return App(winget_id=winget_id, **values)

    if "winget_id" in raw:
        raise CatalogError("ứng dụng share không dùng winget_id")
    kind = _text(raw, "type")
    installer = _text(raw, "installer") or _text(raw, "path")
    if not installer:
        raise CatalogError("ứng dụng share cần 'installer' (file cài) hoặc 'path' (thư mục, với type: portable)")
    _check_placeholders(installer, "installer")
    if not kind:
        suffix = installer.lower().rsplit(".", 1)[-1]
        kind = suffix if suffix in ("msi", "iso") else "exe"
    if kind not in SHARE_TYPES:
        raise CatalogError(f"'type' chỉ nhận {', '.join(SHARE_TYPES)}")
    setup = _text(raw, "setup")
    if kind == "iso":
        setup = setup or "setup.exe"
        if setup.startswith(("\\", "/")) or ":" in setup or ".." in setup.replace("/", "\\").split("\\"):
            raise CatalogError("'setup' là đường dẫn bên trong ISO, ví dụ setup.exe hoặc x64\\setup.exe")
    elif setup:
        raise CatalogError("'setup' chỉ dùng cho type: iso")
    exe = _text(raw, "exe")
    folder = _text(raw, "folder")
    if kind == "portable":
        if not exe:
            raise CatalogError("ứng dụng portable cần 'exe' (file chạy chính, ví dụ UniKeyNT.exe)")
        if any(char in exe + folder for char in '\\/:*?"<>|'):
            raise CatalogError("'exe' và 'folder' chỉ là tên, không chứa đường dẫn")
        if not detect_file and not detect_names:
            values["detect_file"] = f"{{programfiles}}\\{folder or app_id}\\{exe}"
    elif exe or folder or autostart:
        raise CatalogError("'exe', 'folder', 'autostart' chỉ dùng cho type: portable")
    return App(type=kind, installer=installer, setup=setup, exe=exe, folder=folder, autostart=autostart, **values)


def parse_profile(profile_id: str, raw: Any, known_apps: set[str]) -> Profile:
    if not _ID.match(profile_id):
        raise CatalogError("tên profile chỉ gồm chữ thường không dấu, số, '-' và '_' (ví dụ ke-toan)")
    if not isinstance(raw, dict):
        raise CatalogError("profile phải là một khối 'khoá: giá trị'")
    unknown = sorted(set(raw) - _PROFILE_KEYS)
    if unknown:
        raise CatalogError(f"không hiểu khoá {', '.join(unknown)}")
    extends = raw.get("extends") or []
    extends = [extends] if isinstance(extends, str) else extends
    apps = raw.get("apps") or []
    if not isinstance(extends, list) or not all(isinstance(item, str) for item in extends):
        raise CatalogError("'extends' phải là tên profile hoặc danh sách tên")
    if not isinstance(apps, list) or not all(isinstance(item, str) for item in apps):
        raise CatalogError("'apps' phải là danh sách id ứng dụng")
    missing = [item for item in apps if item not in known_apps]
    if missing:
        raise CatalogError(f"không có ứng dụng {', '.join(missing)} (sai id hoặc ứng dụng đó khai báo sai)")
    if not apps and not extends:
        raise CatalogError("profile cần 'apps' hoặc 'extends'")
    return Profile(
        id=profile_id,
        name=_text(raw, "name") or profile_id,
        extends=tuple(extends),
        apps=tuple(dict.fromkeys(apps)),
        description=_text(raw, "description"),
    )


def _check_inheritance(profiles: list[Profile], failed: set[str], errors: list[str], source: str) -> list[Profile]:
    """Bỏ profile mà chuỗi kế thừa (kể cả gián tiếp) có profile không có, khai báo sai, hoặc vòng tròn."""
    by_id = {profile.id: profile for profile in profiles}
    valid: list[Profile] = []
    for profile in profiles:
        problem = None
        stack = [(profile.id, (profile.id,))]
        while stack and problem is None:
            current, trail = stack.pop()
            for parent in by_id[current].extends:
                if parent in failed:
                    problem = f"kế thừa profile {parent} đang khai báo sai"
                elif parent not in by_id:
                    problem = f"kế thừa profile {parent} không có"
                elif parent in trail:
                    problem = "kế thừa vòng tròn: " + " → ".join(trail + (parent,))
                else:
                    stack.append((parent, trail + (parent,)))
                if problem:
                    break
        if problem:
            errors.append(f"{source} profile {profile.id}: {problem}")
        else:
            valid.append(profile)
    return valid
