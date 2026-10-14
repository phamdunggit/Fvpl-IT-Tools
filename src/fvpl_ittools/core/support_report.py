"""Báo cáo "Gửi cho IT" (KE-HOACH-GIAO-DIEN.md mục 5.9): máy, người dùng, tình huống, đã kiểm tra / đã làm gì,
kết quả, 50 dòng log cuối. Chép vào clipboard để dán vào Zalo / email, đồng thời lưu file HTML. Tool không tự gửi.

Log đã được che mật khẩu từ lúc ghi (core/log.py), báo cáo chỉ lấy lại phần đó.
"""

from __future__ import annotations

import html
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from . import paths

LOG_LINES = 50
MARKS = {"ok": "✔", "warn": "⚠", "bad": "✖", "info": "ⓘ"}


@dataclass
class SupportReport:
    computer: str
    domain: str
    os: str
    user: str
    tool_version: str
    topic: str = ""                                       # tình huống, ví dụ "Không in được"
    findings: list[tuple[str, str, str]] = field(default_factory=list)  # (trạng thái, câu, chi tiết)
    actions: list[tuple[str, str]] = field(default_factory=list)        # (mục đã chạy, kết quả)
    note: str = ""                                        # kết luận ngắn, ví dụ "Vẫn còn 1 vấn đề"
    log: list[str] = field(default_factory=list)
    now: datetime = field(default_factory=datetime.now)

    def to_text(self) -> str:
        lines = [
            f"[FVPL IT Toolkit {self.tool_version}] {self.now:%d/%m/%Y %H:%M}",
            f"Máy: {self.computer} ({self.domain}) · {self.os}",
            f"Người dùng: {self.user}",
        ]
        if self.topic:
            lines.append(f"Tình huống: {self.topic}")
        if self.note:
            lines.append(f"Kết quả: {self.note}")
        if self.findings:
            lines.append("")
            lines.append("Kiểm tra:")
            for state, text, detail in self.findings:
                lines.append(f"  {MARKS.get(state, '-')} {text}" + (f" ({detail})" if detail else ""))
        if self.actions:
            lines.append("")
            lines.append("Đã chạy:")
            lines += [f"  - {name}: {result}" for name, result in self.actions]
        if self.log:
            lines.append("")
            lines.append(f"Log ({len(self.log)} dòng cuối):")
            lines += [f"  {line}" for line in self.log[-LOG_LINES:]]
        return "\n".join(lines)

    def to_html(self) -> str:
        body = html.escape(self.to_text())
        return ("<!doctype html><html lang='vi'><head><meta charset='utf-8'>"
                f"<title>Báo cáo gửi IT - {html.escape(self.computer)}</title>"
                "<style>body{font-family:'Segoe UI',Arial,sans-serif;margin:24px;background:#f3f3f3;color:#1b1b1b}"
                "pre{background:#fff;border:1px solid #e5e5e5;border-radius:8px;padding:16px;white-space:pre-wrap;"
                "font-family:Consolas,'Cascadia Mono',monospace;font-size:13px;line-height:1.5}</style></head><body>"
                f"<h1 style='font-size:20px'>Báo cáo gửi IT · {html.escape(self.computer)}</h1><pre>{body}</pre>"
                "</body></html>")

    def save(self, folder: Path | None = None) -> Path:
        folder = folder or paths.reports_dir()
        folder.mkdir(parents=True, exist_ok=True)
        file = folder / f"GuiIT_{self.computer}_{self.now:%Y%m%d_%H%M%S}.html"
        file.write_text(self.to_html(), encoding="utf-8")
        return file
