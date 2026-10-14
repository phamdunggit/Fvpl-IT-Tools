"""Tìm chức năng (Ctrl+K, KE-HOACH-GIAO-DIEN.md mục 5.4). Không phụ thuộc giao diện.

- Bỏ dấu tiếng Việt, chữ thường, bỏ các từ không mang nghĩa ("không", "được", "bị"…).
- Mỗi từ của câu tìm phải khớp đầu một từ trong mục (từ 1–2 ký tự phải khớp nguyên từ, để "in" không khớp "Windows").
- Điểm: khớp ở tên 3, từ khoá 2, nhóm / trang 1.5, mô tả 1; thêm điểm khi cả câu nằm trong tên.
- Ưu tiên mục khớp mọi từ; không có thì lấy mục khớp được nhiều từ nhất.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

STOPWORDS = frozenset({
    "khong", "duoc", "bi", "cua", "va", "la", "cho", "thi", "toi", "tui", "minh", "em", "anh", "chi", "can", "muon",
    "lam", "sao", "the", "nao", "o", "a", "nhe", "voi", "gi", "may", "loi", "hay", "cai", "nay", "do", "di", "roi",
    "nhu", "khi", "de", "mot", "nhung", "cac", "bo",
})
# "máy", "lỗi", "cái"… quá phổ biến: vẫn dùng khi câu tìm chỉ có các từ đó.

KIND_LABELS = {"guide": "Tình huống", "action": "Chức năng", "pack": "Gói sửa nhanh", "app": "Phần mềm",
               "tool": "Công cụ", "page": "Trang"}
_WEIGHTS = (("title", 3.0), ("keywords", 2.0), ("where", 1.5), ("description", 1.0))


def fold(text: str) -> str:
    """Bỏ dấu, chữ thường: "Máy in Đã" → "may in da"."""
    text = unicodedata.normalize("NFD", str(text).lower())
    return "".join(char for char in text if unicodedata.category(char) != "Mn").replace("đ", "d")


def words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", fold(text))


def query_tokens(query: str) -> list[str]:
    tokens = list(dict.fromkeys(words(query)))
    meaningful = [token for token in tokens if token not in STOPWORDS]
    return meaningful or tokens


@dataclass(frozen=True)
class Entry:
    kind: str             # action | pack | app | tool | page | guide
    title: str
    target: str           # ví dụ "action:net.flush_dns", "page:software", "tab:utilities:Event log"
    description: str = ""
    where: str = ""       # "Sửa lỗi › Mạng & Internet"
    keywords: str = ""
    advanced: bool = False  # chỉ hiện ở chế độ Chuyên gia
    icon: str = ""          # tên icon trong ui/icons.py

    @property
    def kind_label(self) -> str:
        return KIND_LABELS.get(self.kind, self.kind)


class Index:
    def __init__(self, entries: list[Entry]):
        self.entries = entries
        self._words = [{field: words(getattr(entry, field)) for field, _ in _WEIGHTS} for entry in entries]
        self._titles = [" ".join(words(entry.title)) for entry in entries]

    @staticmethod
    def _matches(token: str, field_words: list[str]) -> bool:
        if len(token) <= 2:
            return token in field_words
        return any(word.startswith(token) for word in field_words)

    def search(self, query: str, include_advanced: bool = True, limit: int = 40) -> tuple[list[Entry], int]:
        """(kết quả theo thứ tự, số mục nâng cao bị ẩn vì không ở chế độ Chuyên gia)."""
        tokens = query_tokens(query)
        if not tokens:
            return [], 0
        phrase = " ".join(tokens)
        scored = []
        for index, entry in enumerate(self.entries):
            fields = self._words[index]
            score, matched = 0.0, 0
            for token in tokens:
                best = max((weight for field, weight in _WEIGHTS if self._matches(token, fields[field])), default=0.0)
                if best:
                    score += best
                    matched += 1
            if not matched:
                continue
            if len(tokens) > 1 and phrase in self._titles[index]:
                score += 3
            if entry.kind == "guide":
                score += 0.5
            scored.append((matched, score, index))
        if not scored:
            return [], 0
        best_matched = max(item[0] for item in scored)
        wanted = len(tokens) if best_matched == len(tokens) else best_matched
        ranked = sorted((item for item in scored if item[0] >= wanted), key=lambda item: (-item[1], item[2]))
        results = [self.entries[index] for _, _, index in ranked]
        hidden = 0
        if not include_advanced:
            hidden = sum(1 for entry in results if entry.advanced)
            results = [entry for entry in results if not entry.advanced]
        return results[:limit], hidden
