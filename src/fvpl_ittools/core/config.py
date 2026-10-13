"""Đọc site.yaml: thông tin nội bộ của công ty (domain, share...), không nằm trong repo."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

from . import paths

SITE_FILE = "site.yaml"
_FIELDS = ("domain", "netbios_domain", "share_root", "computer_prefix")


@dataclass(frozen=True)
class SiteConfig:
    source: Path | None = None
    domain: str = ""
    netbios_domain: str = ""
    share_root: str = ""
    computer_prefix: str = ""
    errors: tuple[str, ...] = ()

    @property
    def loaded(self) -> bool:
        return self.source is not None


LOCAL_REPO = "SOFT"


@dataclass(frozen=True)
class SoftwareSource:
    """Kho bộ cài mà {share} / $ShareRoot trỏ tới.

    Bản SSD: thư mục SOFT nằm cạnh file exe (ISO, bộ cài, config\\apps.yaml), dùng được không cần mạng.
    Bản USB: không có SOFT, lấy share_root trong site.yaml (cài qua mạng).
    """
    root: str = ""
    kind: str = ""  # local | share | "" (chưa có)

    @property
    def label(self) -> str:
        if self.kind == "local":
            return f"kho trên ổ mang theo {self.root}"
        if self.kind == "share":
            return f"share {self.root}"
        return "chưa có (không có thư mục SOFT cạnh tool, chưa khai báo share_root trong site.yaml)"


def software_source(site: SiteConfig, app_root: Path | None = None) -> SoftwareSource:
    local = (app_root if app_root is not None else paths.app_root()) / LOCAL_REPO
    if local.is_dir():
        return SoftwareSource(str(local), "local")
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
    errors = [f"{file.name}: không hiểu khoá {key!r}" for key in data if key not in _FIELDS]
    values = {key: str(data[key]).strip() for key in _FIELDS if data.get(key) is not None}
    return SiteConfig(source=file, errors=tuple(errors), **values)
