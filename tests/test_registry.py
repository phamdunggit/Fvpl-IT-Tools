from __future__ import annotations

import winreg

import pytest

from fvpl_ittools.core import registry
from fvpl_ittools.core.registry import RegPath, RegValue


def test_parse_key_aliases_and_slashes():
    assert registry.parse_key("HKEY_LOCAL_MACHINE\\Software\\X") == RegPath("HKLM", "Software\\X")
    assert registry.parse_key("hkcu/Software/X/") == RegPath("HKCU", "Software\\X")
    with pytest.raises(ValueError):
        registry.parse_key("HKXX\\Software")


def test_resolve_user_key_only_changes_hkcu():
    hkcu = registry.parse_key("HKCU\\Software\\X")
    assert str(registry.resolve_user_key(hkcu, "S-1-5-21-9")) == "HKU\\S-1-5-21-9\\Software\\X"
    assert registry.resolve_user_key(hkcu, None) == hkcu
    hklm = registry.parse_key("HKLM\\Software\\X")
    assert registry.resolve_user_key(hklm, "S-1-5-21-9") == hklm


@pytest.mark.parametrize("type_name, value", [
    ("DWORD", 0xFFFFFFFF),
    ("QWORD", 2**40),
    ("SZ", "Chữ có dấu"),
    ("EXPAND_SZ", "%SystemRoot%\\x"),
    ("MULTI_SZ", ["một", "hai"]),
    ("BINARY", b"\x00\x01\xff"),
])
def test_write_read_delete_roundtrip(test_key, type_name, value):
    path = registry.parse_key(test_key)
    registry.write_value(path, "V", registry.TYPES[type_name], value)
    read = registry.read_value(path, "V")
    assert read == RegValue(True, registry.TYPES[type_name], value)
    assert RegValue.from_json(read.to_json()) == read
    assert registry.delete_value(path, "V") is True
    assert registry.read_value(path, "V") == registry.MISSING
    assert registry.delete_value(path, "V") is False


def test_read_missing_key():
    assert registry.read_value(registry.parse_key("HKCU\\Software\\FVPL-khong-co"), "x") == registry.MISSING


@pytest.mark.parametrize("type_name, raw, expected", [
    ("DWORD", "0x1f", 31),
    ("DWORD", -1, 0xFFFFFFFF),
    ("SZ", 5, "5"),
    ("BINARY", "01 0a ff", b"\x01\x0a\xff"),
    ("BINARY", [1, 2], b"\x01\x02"),
])
def test_coerce(type_name, raw, expected):
    assert registry.coerce(type_name, raw) == expected


@pytest.mark.parametrize("type_name, raw", [
    ("DWORD", True), ("DWORD", 2**32), ("MULTI_SZ", "a"), ("BINARY", "zz"), ("NOPE", 1),
])
def test_coerce_rejects(type_name, raw):
    with pytest.raises(ValueError):
        registry.coerce(type_name, raw)


def test_reg_exe_command():
    path = registry.parse_key("HKCU\\Software\\X")
    assert registry.reg_exe_command(path, "A", "DWORD", 0, False) == 'reg add "HKCU\\Software\\X" /v "A" /t REG_DWORD /d "0" /f'
    assert registry.reg_exe_command(path, "", None, None, True) == 'reg delete "HKCU\\Software\\X" /ve /f'
    assert registry.reg_exe_command(path, "M", "MULTI_SZ", ["a", "b"], False).endswith('/d "a\\0b" /f')


def test_key_exists(test_key):
    path = registry.parse_key(test_key)
    assert not registry.key_exists(path)
    registry.write_value(path, "V", winreg.REG_SZ, "x")
    assert registry.key_exists(path)
