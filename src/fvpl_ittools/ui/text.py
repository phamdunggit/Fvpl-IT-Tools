"""Tiện ích xử lý chữ cho giao diện."""

from __future__ import annotations

import unicodedata


def fold(text: str) -> str:
    """Bỏ dấu và viết thường, để gõ "may in" vẫn tìm ra "Máy in"."""
    decomposed = unicodedata.normalize("NFD", text.replace("đ", "d").replace("Đ", "D"))
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).lower()
