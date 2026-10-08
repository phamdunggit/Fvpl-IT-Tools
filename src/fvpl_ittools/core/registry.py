"""Đọc/ghi registry (luôn dùng view 64-bit) và chuyển giá trị sang JSON để lưu nhật ký hoàn tác."""

from __future__ import annotations

import winreg
from dataclasses import dataclass
from typing import Any

_HIVES = {
    "HKLM": winreg.HKEY_LOCAL_MACHINE,
    "HKCU": winreg.HKEY_CURRENT_USER,
    "HKU": winreg.HKEY_USERS,
    "HKCR": winreg.HKEY_CLASSES_ROOT,
}
_HIVE_ALIASES = {
    "HKEY_LOCAL_MACHINE": "HKLM",
    "HKEY_CURRENT_USER": "HKCU",
    "HKEY_USERS": "HKU",
    "HKEY_CLASSES_ROOT": "HKCR",
}

TYPES = {
    "DWORD": winreg.REG_DWORD,
    "QWORD": winreg.REG_QWORD,
    "SZ": winreg.REG_SZ,
    "EXPAND_SZ": winreg.REG_EXPAND_SZ,
    "MULTI_SZ": winreg.REG_MULTI_SZ,
    "BINARY": winreg.REG_BINARY,
}
TYPE_NAMES = {code: name for name, code in TYPES.items()}
_INT_LIMITS = {"DWORD": 0xFFFFFFFF, "QWORD": 0xFFFFFFFFFFFFFFFF}
_VIEW = winreg.KEY_WOW64_64KEY


@dataclass(frozen=True)
class RegPath:
    hive: str
    subkey: str

    def __str__(self) -> str:
        return f"{self.hive}\\{self.subkey}" if self.subkey else self.hive

    @property
    def root(self):
        return _HIVES[self.hive]


def parse_key(text: str) -> RegPath:
    """'HKCU\\Software\\X' hoặc 'HKEY_CURRENT_USER\\Software\\X' → RegPath."""
    cleaned = text.strip().replace("/", "\\").strip("\\")
    head, _, rest = cleaned.partition("\\")
    hive = _HIVE_ALIASES.get(head.upper(), head.upper())
    if hive not in _HIVES:
        raise ValueError(f"hive registry không hợp lệ: {head!r} (dùng HKLM, HKCU, HKU hoặc HKCR)")
    return RegPath(hive, rest)


def resolve_user_key(path: RegPath, user_sid: str | None) -> RegPath:
    """Đổi HKCU thành HKU\\<SID> khi cần ghi cho người dùng khác tài khoản đang chạy tool."""
    if path.hive == "HKCU" and user_sid:
        return RegPath("HKU", f"{user_sid}\\{path.subkey}" if path.subkey else user_sid)
    return path


@dataclass(frozen=True)
class RegValue:
    exists: bool
    type: int | None = None
    value: Any = None

    def to_json(self) -> dict:
        if not self.exists:
            return {"exists": False}
        data: dict[str, Any] = {"exists": True, "type": TYPE_NAMES.get(self.type, self.type)}
        if isinstance(self.value, (bytes, bytearray)):
            data["hex"] = bytes(self.value).hex()
        else:
            data["value"] = self.value
        return data

    @classmethod
    def from_json(cls, data: dict) -> RegValue:
        if not data.get("exists"):
            return MISSING
        type_code = data["type"]
        type_code = TYPES[type_code] if isinstance(type_code, str) else int(type_code)
        value = bytes.fromhex(data["hex"]) if "hex" in data else data.get("value")
        return cls(True, type_code, value)

    def display(self) -> str:
        if not self.exists:
            return "(chưa có)"
        if isinstance(self.value, (bytes, bytearray)):
            return bytes(self.value).hex(" ")
        if isinstance(self.value, list):
            return " | ".join(self.value)
        return str(self.value)


MISSING = RegValue(False)


def coerce(type_name: str, value: Any) -> Any:
    """Kiểm tra và đổi giá trị trong file YAML sang đúng kiểu winreg cần."""
    type_name = type_name.upper()
    if type_name not in TYPES:
        raise ValueError(f"kiểu registry không hợp lệ: {type_name} (dùng {', '.join(TYPES)})")
    if type_name in _INT_LIMITS:
        if isinstance(value, bool):
            raise ValueError(f"{type_name} cần số, không phải true/false")
        if isinstance(value, str):
            try:
                value = int(value, 0)
            except ValueError as exc:
                raise ValueError(f"{type_name} cần số, gặp {value!r}") from exc
        if not isinstance(value, int):
            raise ValueError(f"{type_name} cần số, gặp {value!r}")
        if value < 0:
            value &= _INT_LIMITS[type_name]
        if value > _INT_LIMITS[type_name]:
            raise ValueError(f"{value} vượt giới hạn của {type_name}")
        return value
    if type_name in ("SZ", "EXPAND_SZ"):
        if isinstance(value, (dict, list)) or value is None:
            raise ValueError(f"{type_name} cần chuỗi, gặp {value!r}")
        return str(value)
    if type_name == "MULTI_SZ":
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise ValueError("MULTI_SZ cần danh sách chuỗi")
        return list(value)
    # BINARY: chuỗi hex ("01 0a ff") hoặc danh sách số 0–255
    if isinstance(value, str):
        try:
            return bytes.fromhex(value.replace(" ", ""))
        except ValueError as exc:
            raise ValueError(f"BINARY cần chuỗi hex, gặp {value!r}") from exc
    if isinstance(value, list):
        try:
            return bytes(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("BINARY cần danh sách số 0–255") from exc
    raise ValueError(f"BINARY cần chuỗi hex hoặc danh sách số, gặp {value!r}")


def read_value(path: RegPath, name: str) -> RegValue:
    try:
        with winreg.OpenKey(path.root, path.subkey, 0, winreg.KEY_READ | _VIEW) as key:
            value, type_code = winreg.QueryValueEx(key, name)
    except FileNotFoundError:
        return MISSING
    return RegValue(True, type_code, value)


def write_value(path: RegPath, name: str, type_code: int, value: Any) -> None:
    with winreg.CreateKeyEx(path.root, path.subkey, 0, winreg.KEY_SET_VALUE | _VIEW) as key:
        winreg.SetValueEx(key, name, 0, type_code, value)


def delete_value(path: RegPath, name: str) -> bool:
    """Xoá một giá trị. Trả về False nếu giá trị (hoặc khoá) vốn không có."""
    try:
        with winreg.OpenKey(path.root, path.subkey, 0, winreg.KEY_SET_VALUE | _VIEW) as key:
            winreg.DeleteValue(key, name)
    except FileNotFoundError:
        return False
    return True


def key_exists(path: RegPath) -> bool:
    try:
        winreg.CloseKey(winreg.OpenKey(path.root, path.subkey, 0, winreg.KEY_READ | _VIEW))
        return True
    except OSError:
        return False


def reg_exe_command(path: RegPath, name: str, type_name: str | None, value: Any, delete: bool) -> str:
    """Lệnh reg.exe tương đương, để IT copy chạy tay hoặc đối chiếu."""
    target = "/ve" if name == "" else f'/v "{name}"'
    if delete:
        return f'reg delete "{path}" {target} /f'
    type_name = (type_name or "SZ").upper()
    if isinstance(value, (bytes, bytearray)):
        data = bytes(value).hex()
    elif isinstance(value, list):
        data = "\\0".join(value)
    else:
        data = str(value).replace('"', '\\"')
    return f'reg add "{path}" {target} /t REG_{type_name} /d "{data}" /f'
