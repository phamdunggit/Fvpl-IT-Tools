"""Đọc tên các model máy in trong file .inf của driver, để IT chọn đúng model khi thêm máy in qua IP.

Chỉ đọc file, không cài gì. Cài thật làm trong script thêm máy in (pnputil /add-driver rồi Add-PrinterDriver).
Một file .inf liệt kê model theo kiến trúc: [Manufacturer] trỏ tới các mục như [HP.NTamd64]. Trên Windows 64-bit
chỉ mục có đuôi NTamd64 được dùng, mục không có đuôi là của bản 32-bit.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

PRINTER_CLASS_GUID = "{4d36e979-e325-11ce-bfc1-08002be10318}"
_ARCH = {"AMD64": "ntamd64", "ARM64": "ntarm64", "X86": "ntx86"}
_TOKEN = re.compile(r"%([^%]*)%")


class InfError(ValueError):
    pass


def machine_arch() -> str:
    """Đuôi mục model hợp với máy này: ntamd64, ntarm64 hoặc ntx86."""
    arch = os.environ.get("PROCESSOR_ARCHITEW6432") or os.environ.get("PROCESSOR_ARCHITECTURE", "AMD64")
    return _ARCH.get(arch.upper(), "ntamd64")


def decode(data: bytes) -> str:
    """File .inf của hãng hay là UTF-16 có BOM, cũng có file ANSI hoặc UTF-8."""
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16")
    if data.startswith(b"\xef\xbb\xbf"):
        return data[3:].decode("utf-8", errors="replace")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def _strip_comment(line: str) -> str:
    quoted = False
    for index, char in enumerate(line):
        if char == '"':
            quoted = not quoted
        elif char == ";" and not quoted:
            return line[:index]
    return line


def sections(text: str) -> dict[str, list[str]]:
    """{tên mục viết thường: các dòng}. Mục trùng tên thì gộp, dòng kết thúc bằng \\ nối với dòng sau."""
    result: dict[str, list[str]] = {}
    current: list[str] | None = None
    pending = ""
    for raw in text.splitlines():
        line = _strip_comment(raw).strip()
        if pending:
            line = pending + line
            pending = ""
        if line.endswith("\\"):
            pending = line[:-1]
            continue
        if not line:
            continue
        if line.startswith("[") and "]" in line:
            current = result.setdefault(line[1:line.index("]")].strip().lower(), [])
            continue
        if current is not None:
            current.append(line)
    return result


def _split(line: str) -> tuple[str, str]:
    key, _, value = line.partition("=")
    return key.strip(), value.strip()


def _unquote(text: str) -> str:
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] == '"':
        return text[1:-1].replace('""', '"')
    return text


def _strings(parsed: dict[str, list[str]]) -> dict[str, str]:
    # [Strings] gốc được ưu tiên, mục theo ngôn ngữ (Strings.0409...) chỉ bù chỗ thiếu.
    names = ["strings"] + sorted(name for name in parsed if name.startswith("strings."))
    found: dict[str, str] = {}
    for name in names:
        for line in parsed.get(name, []):
            key, value = _split(line)
            if key and "=" in line:
                found.setdefault(key.lower(), _unquote(value))
    return found


def _expand(text: str, strings: dict[str, str]) -> str:
    def repl(match: re.Match) -> str:
        token = match.group(1)
        return "%" if not token else strings.get(token.lower(), match.group(0))
    return _TOKEN.sub(repl, _unquote(text))


def models_from_text(text: str, arch: str | None = None) -> list[str]:
    arch = (arch or machine_arch()).lower()
    parsed = sections(text)
    strings = _strings(parsed)
    version = {key.lower(): _expand(value, strings) for key, value in map(_split, parsed.get("version", []))}
    klass, guid = version.get("class", ""), version.get("classguid", "").lower()
    if klass.lower() != "printer" and guid != PRINTER_CLASS_GUID:
        raise InfError(f"File này không phải driver máy in (Class = {klass or 'không ghi'}).")

    targets: list[str] = []
    for line in parsed.get("manufacturer", []):
        _, value = _split(line)
        parts = [part.strip() for part in _expand(value, strings).split(",") if part.strip()]
        if not parts:
            continue
        base, decorations = parts[0].lower(), [part.lower() for part in parts[1:]]
        if decorations:
            targets += [f"{base}.{item}" for item in decorations if item.split(".")[0] == arch]
        elif arch == "ntx86":
            targets.append(base)  # Mục không có đuôi chỉ dùng cho Windows 32-bit.

    models: list[str] = []
    for name in targets:
        for line in parsed.get(name, []):
            if "=" not in line:
                continue
            model = _expand(_split(line)[0], strings).strip()
            if model and model not in models:
                models.append(model)
    if not models:
        bits = {"ntamd64": "64-bit", "ntarm64": "ARM64", "ntx86": "32-bit"}.get(arch, arch)
        raise InfError(f"File này không có driver {bits} cho máy này. Tìm bản driver {bits} của hãng.")
    return models


def inf_models(path: str | Path, arch: str | None = None) -> list[str]:
    """Tên model máy in trong file .inf, đúng kiến trúc của máy này. Lỗi thì InfError (lời báo tiếng Việt)."""
    try:
        data = Path(path).read_bytes()
    except OSError as exc:
        raise InfError(f"Không đọc được file: {exc.strerror or exc}") from exc
    return models_from_text(decode(data), arch)
