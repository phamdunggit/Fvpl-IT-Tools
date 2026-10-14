"""Đọc site.yaml: thông tin nội bộ của công ty (domain, share...), không nằm trong repo."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from . import paths

SITE_FILE = "site.yaml"
_FIELDS = ("domain", "netbios_domain", "share_root", "computer_prefix", "computer_ou", "it_admins_group")
_DEPARTMENTS = "departments"
DEPARTMENT_CODE = re.compile(r"^[A-Z0-9]{1,6}$")


@dataclass(frozen=True)
class SiteConfig:
    source: Path | None = None
    domain: str = ""
    netbios_domain: str = ""
    share_root: str = ""
    computer_prefix: str = ""
    computer_ou: str = ""              # OU chung của máy trạm (distinguished name), rỗng = container Computers
    it_admins_group: str = ""          # nhóm domain của IT, thêm vào Administrators của máy sau khi join
    departments: tuple[tuple[str, str], ...] = ()  # (mã phòng, tên phòng), thêm dần từ wizard
    errors: tuple[str, ...] = ()

    @property
    def loaded(self) -> bool:
        return self.source is not None

    @property
    def prefix(self) -> str:
        return self.computer_prefix or "FVPL-"


LOCAL_REPO = "SOFT"


@dataclass(frozen=True)
class SoftwareSource:
    """Kho bộ cài mà {share} / $ShareRoot trỏ tới.

    Bản SSD: thư mục SOFT nằm cạnh file exe (ISO, bộ cài, config\\apps.yaml), dùng được không cần mạng.
    Bản USB: không có SOFT, lấy share_root trong site.yaml (cài qua mạng).
    """
    root: str = ""
    kind: str = ""  # local | chosen | share | "" (chưa có)

    @property
    def label(self) -> str:
        if self.kind == "local":
            return f"kho trên ổ mang theo {self.root}"
        if self.kind == "chosen":
            return f"kho đã chọn {self.root}"
        if self.kind == "share":
            return f"share {self.root}"
        return "chưa có (không có thư mục SOFT cạnh tool, chưa khai báo share_root trong site.yaml)"


def software_source(site: SiteConfig, app_root: Path | None = None, extra_local: Path | None = None,
                    chosen: str = "") -> SoftwareSource:
    """Thứ tự: SOFT cạnh tool → `extra_local` → `chosen` → share_root trong site.yaml.

    `extra_local`: thư mục SOFT trên ổ SSD lúc bắt đầu wizard Cài máy mới, khi tool đã chạy tiếp từ bản chép
    trong ProgramData sau khi khởi động lại. `chosen`: kho IT chọn bằng nút "Chọn kho…" (lưu trong prefs.json),
    chỉ dùng khi còn tồn tại."""
    local = (app_root if app_root is not None else paths.app_root()) / LOCAL_REPO
    if local.is_dir():
        return SoftwareSource(str(local), "local")
    if extra_local is not None and extra_local.is_dir():
        return SoftwareSource(str(extra_local), "local")
    if chosen and os.path.isdir(chosen):
        return SoftwareSource(chosen, "chosen")
    if site.share_root:
        return SoftwareSource(site.share_root, "share")
    return SoftwareSource()


def site_config_candidates() -> list[Path]:
    """Thứ tự tìm: biến môi trường FVPL_ITTOOLS_SITE → cạnh file exe/gốc repo → %ProgramData%\\FVPL-ITTools."""
    candidates: list[Path] = []
    override = os.environ.get("FVPL_ITTOOLS_SITE")
    if override:
        candidates.append(Path(override))
    candidates.append(paths.app_root() / SITE_FILE)
    candidates.append(Path(os.environ.get("ProgramData", r"C:\ProgramData")) / paths.APP_DIR_NAME / SITE_FILE)
    return candidates


def load_site_config(candidates: list[Path] | None = None) -> SiteConfig:
    for candidate in candidates if candidates is not None else site_config_candidates():
        if candidate.is_file():
            return _parse(candidate)
    return SiteConfig()


def _parse(file: Path) -> SiteConfig:
    try:
        data = yaml.safe_load(file.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        return SiteConfig(source=file, errors=(f"Không đọc được {file}: {exc}",))
    if not isinstance(data, dict):
        return SiteConfig(source=file, errors=(f"{file} phải là các dòng key: value",))
    errors = [f"{file.name}: không hiểu khoá {key!r}" for key in data if key not in (*_FIELDS, _DEPARTMENTS)]
    values = {key: str(data[key]).strip() for key in _FIELDS if data.get(key) is not None}
    departments: list[tuple[str, str]] = []
    raw = data.get(_DEPARTMENTS)
    if isinstance(raw, dict):
        for code, name in raw.items():
            code = str(code).strip().upper()
            if DEPARTMENT_CODE.match(code):
                departments.append((code, str(name or code).strip()))
            else:
                errors.append(f"{file.name}: mã phòng {code!r} chỉ gồm chữ in hoa không dấu và số, tối đa 6 ký tự")
    elif raw is not None:
        errors.append(f"{file.name}: '{_DEPARTMENTS}' phải là các dòng MÃ: Tên phòng")
    return SiteConfig(source=file, errors=tuple(errors), departments=tuple(departments), **values)


def site_file_for_write(site: SiteConfig) -> Path:
    """File site.yaml sẽ ghi: file đang dùng, chưa có thì tạo cạnh file exe."""
    return site.source if site.source is not None else paths.app_root() / SITE_FILE


def add_department(site: SiteConfig, code: str, name: str) -> SiteConfig:
    """Thêm mã phòng vào site.yaml rồi đọc lại. Sửa thẳng chữ trong file để giữ nguyên chú thích của IT.

    Lỗi (mã sai, trùng, không ghi được) thì ValueError / OSError kèm lời báo tiếng Việt.
    """
    code, name = code.strip().upper(), " ".join(name.split())
    if not DEPARTMENT_CODE.match(code):
        raise ValueError("Mã phòng chỉ gồm chữ in hoa không dấu và số, tối đa 6 ký tự (ví dụ KT, NS, KHO).")
    if not name:
        raise ValueError("Chưa nhập tên phòng.")
    if code in dict(site.departments):
        raise ValueError(f"Mã {code} đã có ({dict(site.departments)[code]}).")
    file = site_file_for_write(site)
    text = file.read_text(encoding="utf-8") if file.is_file() else (
        "# Cấu hình riêng của công ty, tạo bởi FVPL IT Toolkit. Mẫu đầy đủ: site.example.yaml.\n")
    entry = f"  {code}: {json.dumps(name, ensure_ascii=False)}"
    lines = text.splitlines()
    start = next((index for index, line in enumerate(lines)
                  if re.match(rf"^{_DEPARTMENTS}\s*:\s*(\{{\s*\}}\s*)?(#.*)?$", line)), None)
    if start is None:
        if any(line.startswith(f"{_DEPARTMENTS}:") for line in lines):
            raise ValueError(f"Trong {file.name}, viết '{_DEPARTMENTS}:' dạng nhiều dòng (mỗi dòng 'MÃ: Tên') "
                             "thì tool mới thêm mã mới vào được.")
        lines += ["", f"{_DEPARTMENTS}:", entry]
    else:
        lines[start] = f"{_DEPARTMENTS}:"
        end = start + 1
        while end < len(lines) and (not lines[end].strip() or lines[end].startswith((" ", "\t"))):
            end += 1
        while end > start + 1 and not lines[end - 1].strip():
            end -= 1
        lines.insert(end, entry)
    file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    updated = _parse(file)
    if code not in dict(updated.departments):
        raise ValueError(f"Đã ghi {file} nhưng đọc lại không thấy mã {code}, kiểm tra lại file.")
    return updated
