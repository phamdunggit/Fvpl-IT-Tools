"""Biến môi trường PATH (PLAN.md mục 5.7): xem từng thư mục, đánh dấu mục không tồn tại / trùng, sửa có hoàn tác.

Hai phạm vi: của cả máy (HKLM) và của người dùng (HKCU, tool tự đổi sang HKU\\<SID> khi chạy bằng tài khoản khác).
Sửa bằng một mục registry chạy qua executor (sao lưu giá trị cũ, hoàn tác ở trang Nhật ký), xong thì báo cho
Windows biết (chương trình mở sau đó thấy PATH mới; cửa sổ cmd đang mở thì phải mở lại).
"""

from __future__ import annotations

import ntpath
import os
import re
from dataclasses import dataclass

from ..actions.loader import parse_action
from ..actions.model import Action
from . import registry

MACHINE = "machine"
USER = "user"
KEYS = {
    MACHINE: r"HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
    USER: r"HKCU\Environment",
}
LABELS = {MACHINE: "PATH của cả máy", USER: "PATH của người dùng"}
LONG_PATH = 2047  # một số chương trình cũ chỉ đọc 2048 ký tự đầu
_VARIABLE = re.compile(r"%([^%]+)%")


@dataclass(frozen=True)
class PathEntry:
    raw: str          # như trong registry, ví dụ %SystemRoot%\system32
    expanded: str
    exists: bool
    duplicate: bool   # đã có ở trước (cùng phạm vi, hoặc PATH của máy với mục của người dùng)

    @property
    def state(self) -> str:
        if not self.raw.strip():
            return "empty"
        if self.duplicate:
            return "duplicate"
        return "ok" if self.exists else "missing"

    @property
    def problem(self) -> bool:
        return self.state != "ok"


STATE_LABELS = {"ok": "Có", "missing": "Không tồn tại", "duplicate": "Trùng", "empty": "Mục trống"}


def expand(text: str, overrides: dict[str, str] | None = None) -> str:
    """Thay %BIEN% bằng giá trị; biến không có thì giữ nguyên (thư mục sẽ báo không tồn tại)."""
    values = {key.upper(): value for key, value in os.environ.items()}
    values.update({key.upper(): value for key, value in (overrides or {}).items()})
    return _VARIABLE.sub(lambda match: values.get(match.group(1).upper(), match.group(0)), text)


def normalize(path: str) -> str:
    return ntpath.normcase(ntpath.normpath(path.strip().strip('"'))).rstrip("\\") if path.strip() else ""


def user_overrides(profile: str) -> dict[str, str]:
    """Biến theo người dùng khi tool chạy bằng tài khoản khác: %USERPROFILE% phải là hồ sơ của người dùng đó."""
    if not profile:
        return {}
    return {"USERPROFILE": profile, "APPDATA": ntpath.join(profile, "AppData", "Roaming"),
            "LOCALAPPDATA": ntpath.join(profile, "AppData", "Local")}


def split(value: str) -> list[str]:
    return [part for part in value.split(";")] if value else []


def analyze(parts: list[str], overrides: dict[str, str] | None = None, seen: set[str] | None = None) -> list[PathEntry]:
    seen = set(seen or ())
    entries = []
    for raw in parts:
        expanded = expand(raw.strip(), overrides)
        key = normalize(expanded)
        duplicate = bool(key) and key in seen
        exists = bool(key) and "%" not in expanded and os.path.isdir(expanded.strip().strip('"'))
        entries.append(PathEntry(raw, expanded, exists, duplicate))
        if key:
            seen.add(key)
    return entries


def keys_of(entries: list[PathEntry]) -> set[str]:
    return {normalize(entry.expanded) for entry in entries if entry.raw.strip()}


def cleaned(parts: list[str], overrides: dict[str, str] | None = None, seen: set[str] | None = None) -> list[str]:
    """Bỏ mục trống, trùng, không tồn tại; giữ nguyên thứ tự và cách viết (%SystemRoot%…)."""
    return [entry.raw.strip() for entry in analyze(parts, overrides, seen) if not entry.problem]


def join(parts: list[str]) -> str:
    return ";".join(part.strip() for part in parts if part.strip())


def read(scope: str, resolved_key: registry.RegPath) -> str:
    value = registry.read_value(resolved_key, "Path")
    return str(value.value or "") if value.exists else ""


def action(scope: str, value: str) -> Action:
    """Mục ghi PATH mới (REG_EXPAND_SZ), hoàn tác được, xong thì báo Windows."""
    machine = scope == MACHINE
    return parse_action({
        "id": f"env.path_{scope}", "name": f"Sửa {LABELS[scope]}", "category": "Biến môi trường",
        "page": "utilities", "risk": "caution", "scope": "machine" if machine else "user", "admin": machine,
        "undo": "auto", "after": ["notify_environment"],
        "description": f"Ghi lại {LABELS[scope]} (bỏ mục hỏng / trùng, thêm hoặc gỡ thư mục). Giá trị cũ được sao "
                       "lưu, hoàn tác ở trang Nhật ký. Chương trình mở sau đó thấy PATH mới.",
        "apply": [{"registry": {"key": KEYS[scope], "name": "Path", "type": "EXPAND_SZ", "value": value}}],
    })
