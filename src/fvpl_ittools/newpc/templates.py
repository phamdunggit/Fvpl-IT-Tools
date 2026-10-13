"""Mẫu cho wizard Cài máy mới (PLAN.md mục 5.2): bộ lựa chọn hay dùng, ví dụ "Kế toán – Laptop".

Một mẫu gồm mã phòng ban, profile phần mềm và phần mềm thêm ngoài profile (ví dụ bản Office của người dùng đó).
Lưu ở `wizard-templates.json` cạnh site.yaml (theo tool ra USB / SSD, không lên git vì là thông tin công ty).
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ..core import config

log = logging.getLogger(__name__)

TEMPLATES_FILE = "wizard-templates.json"
NAME_MAX = 60


@dataclass
class Template:
    name: str
    department: str = ""
    profile: str = ""
    apps: list[str] = field(default_factory=list)   # id ứng dụng thêm ngoài profile


def templates_path(site: config.SiteConfig) -> Path:
    return config.site_file_for_write(site).parent / TEMPLATES_FILE


def check_name(name: str) -> str:
    name = " ".join(name.split())
    if not name:
        raise ValueError("Chưa nhập tên mẫu.")
    if len(name) > NAME_MAX:
        raise ValueError(f"Tên mẫu tối đa {NAME_MAX} ký tự.")
    return name


def load(file: Path) -> list[Template]:
    """Mẫu đọc được; file hỏng thì bỏ qua (ghi log) và coi như chưa có mẫu."""
    if not file.is_file():
        return []
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        log.exception("Không đọc được %s", file)
        return []
    templates = []
    for item in data.get("templates", []) if isinstance(data, dict) else []:
        if not isinstance(item, dict) or not str(item.get("name", "")).strip():
            continue
        apps = item.get("apps") if isinstance(item.get("apps"), list) else []
        templates.append(Template(
            name=" ".join(str(item["name"]).split()),
            department=str(item.get("department") or "").strip().upper(),
            profile=str(item.get("profile") or "").strip(),
            apps=[str(app) for app in apps if str(app).strip()],
        ))
    return templates


def _write(file: Path, templates: list[Template]) -> None:
    file.parent.mkdir(parents=True, exist_ok=True)
    payload = {"templates": [asdict(item) for item in sorted(templates, key=lambda item: item.name.lower())]}
    temp = file.with_suffix(".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(file)


def save(file: Path, template: Template) -> list[Template]:
    """Thêm mẫu, hoặc ghi đè mẫu cùng tên (không phân biệt hoa thường). Trả danh sách mới."""
    template.name = check_name(template.name)
    templates = [item for item in load(file) if item.name.lower() != template.name.lower()]
    templates.append(template)
    _write(file, templates)
    return load(file)


def delete(file: Path, name: str) -> list[Template]:
    templates = [item for item in load(file) if item.name.lower() != name.strip().lower()]
    _write(file, templates)
    return load(file)
