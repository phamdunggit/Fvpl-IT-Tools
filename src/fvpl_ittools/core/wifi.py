"""Mật khẩu Wi-Fi đã lưu trên máy (PLAN.md mục 5.7, chỉ dành cho IT).

Xuất các profile ra thư mục tạm bằng `netsh wlan export profile key=clear` rồi đọc file XML (không phụ thuộc ngôn ngữ
Windows như khi đọc chữ của `netsh wlan show profile`), xoá thư mục tạm ngay sau đó. Cần quyền admin để thấy mật khẩu.
Kết quả chỉ trả về giao diện, không ghi log.
"""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree

from . import shell

NS = {"w": "http://www.microsoft.com/networking/WLAN/profile/v1"}


class WifiError(RuntimeError):
    pass


@dataclass(frozen=True)
class WifiProfile:
    name: str
    ssid: str
    security: str      # WPA2PSK, WPA3SAE, open, WPA2 (doanh nghiệp)...
    password: str      # rỗng: mạng mở, mạng doanh nghiệp (đăng nhập bằng tài khoản) hoặc không đọc được


def parse_profile(text: str) -> WifiProfile | None:
    try:
        root = ElementTree.fromstring(text)
    except ElementTree.ParseError:
        return None
    name = root.findtext("w:name", default="", namespaces=NS)
    ssid = root.findtext("w:SSIDConfig/w:SSID/w:name", default=name, namespaces=NS)
    security = root.findtext("w:MSM/w:security/w:authEncryption/w:authentication", default="", namespaces=NS)
    password = root.findtext("w:MSM/w:security/w:sharedKey/w:keyMaterial", default="", namespaces=NS)
    protected = root.findtext("w:MSM/w:security/w:sharedKey/w:protected", default="false", namespaces=NS)
    if protected.lower() == "true":
        password = ""  # còn mã hoá: tool không có quyền admin
    return WifiProfile(name, ssid, security, password)


def saved_profiles() -> list[WifiProfile]:
    folder = Path(tempfile.mkdtemp(prefix="fvpl-wifi-"))
    try:
        result = shell.run_cmd(f'netsh wlan export profile key=clear folder="{folder}"', timeout=60)
        files = sorted(folder.glob("*.xml"))
        if not files:
            detail = result.output.strip().splitlines()[-1] if result.output.strip() else f"mã lỗi {result.code}"
            raise WifiError(f"Không đọc được profile Wi-Fi nào ({detail}). Máy không có card Wi-Fi hoặc dịch vụ "
                            "WLAN AutoConfig không chạy.")
        profiles = [profile for file in files
                    if (profile := parse_profile(file.read_text(encoding="utf-8", errors="replace"))) is not None]
        return sorted(profiles, key=lambda profile: profile.name.lower())
    finally:
        shutil.rmtree(folder, ignore_errors=True)
