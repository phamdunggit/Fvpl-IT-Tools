"""Bước 7 của wizard: báo cáo cài máy (HTML).

Gồm thông tin wizard (tên máy, phòng, người dùng chính), kết quả từng bước, hệ điều hành và phần cứng (serial)
đọc bằng script của trang Tổng quan, danh sách phần mềm đã cài kèm phiên bản. Chỉ lưu trên máy và trên ổ mang
theo (thư mục Reports cạnh tool), không gửi đi đâu (PLAN.md mục 11, câu 12).
"""

from __future__ import annotations

import html
import logging
import re
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from ..core import inventory, paths
from ..software.detect import InstalledEntry, installed_programs
from .state import STATUS_LABELS, STEPS, StepRecord, WizardState

log = logging.getLogger(__name__)
REPORT_DIR_ON_DRIVE = "Reports"
_STATUS_COLORS = {"ok": "#15803d", "failed": "#b91c1c", "skipped": "#7b8794"}


@dataclass
class ReportData:
    state: WizardState
    basics: inventory.Basics
    sections: list[inventory.Section]
    programs: list[InstalledEntry]
    domain: str
    it_account: str
    tool_version: str
    raw: dict | None = None     # dữ liệu thô của 4 phần, để lưu kiểm kê


def collect(state: WizardState, basics: inventory.Basics, domain: str, it_account: str, tool_version: str,
            user_sid: str | None, cancel: threading.Event | None = None) -> ReportData:
    """Đọc thông tin máy (cả 4 phần của trang Tổng quan, để lưu kiểm kê luôn) và phần mềm đã cài.

    Báo cáo chỉ in phần hệ điều hành và phần cứng."""
    data: dict = {}
    failed: dict[str, str] = {}
    for part in inventory.PARTS:
        try:
            data.update(inventory.collect_part(part, cancel))
        except inventory.InventoryError as exc:
            failed[part] = str(exc)
    sections = [section for section in inventory.build_sections(data, basics, failed)
                if section.key in ("system", "hardware")]
    # Giống Programs and Features: bỏ thành phần hệ thống và bản cập nhật của phần mềm khác.
    visible = [entry for entry in installed_programs(user_sid) if not entry.hidden]
    programs = sorted({(entry.name, entry.version): entry for entry in visible}.values(),
                      key=lambda entry: entry.name.lower())
    return ReportData(state, basics, sections, programs, domain, it_account, tool_version, data)


def to_html(report: ReportData) -> str:
    def esc(text: object) -> str:
        return html.escape(str(text))

    state, basics = report.state, report.basics
    parts = [
        "<!doctype html><html lang='vi'><head><meta charset='utf-8'>",
        f"<title>Báo cáo cài máy {esc(basics.computer_name)}</title>",
        "<style>body{font-family:'Segoe UI',Arial,sans-serif;margin:24px;color:#1f2933;background:#f4f6f8}"
        "h1{font-size:20px;margin:0 0 4px}p.meta{color:#52606d;margin:0 0 16px}"
        "section{background:#fff;border:1px solid #dde3ea;border-radius:8px;padding:12px 16px;margin-bottom:14px}"
        "h2{font-size:15px;margin:0 0 8px;color:#102a43}table{border-collapse:collapse;width:100%}"
        "td,th{padding:4px 8px;vertical-align:top;border-top:1px solid #eef1f4;text-align:left}"
        "th{color:#52606d;font-weight:600}td.k{color:#52606d;width:220px;white-space:nowrap}</style></head><body>",
        f"<h1>Báo cáo cài máy {esc(basics.computer_name)}</h1>",
        f"<p class='meta'>Lập lúc {basics.now:%d/%m/%Y %H:%M} bằng FVPL IT Toolkit {esc(report.tool_version)}, "
        f"tài khoản {esc(report.it_account)}</p>",
        "<section><h2>Thông tin máy</h2><table>",
    ]
    started = StepRecord("", state.started).time_label
    for label, value in (("Tên máy", basics.computer_name), ("Domain", report.domain or basics.domain_label),
                         ("Phòng ban", state.department), ("Người dùng chính", state.primary_user),
                         ("Profile phần mềm", state.profile), ("Bắt đầu cài", started)):
        parts.append(f"<tr><td class='k'>{esc(label)}</td><td>{esc(value or '—')}</td></tr>")
    parts.append("</table></section><section><h2>Các bước</h2><table>"
                 "<tr><th>Bước</th><th>Kết quả</th><th>Lúc</th><th>Ghi chú</th></tr>")
    for key, name in STEPS[1:]:
        record = state.steps.get(key)
        if record is None:
            parts.append(f"<tr><td>{esc(name)}</td><td style='color:#b45309'>Chưa làm</td><td></td><td></td></tr>")
            continue
        color = _STATUS_COLORS.get(record.status, "")
        parts.append(f"<tr><td>{esc(name)}</td><td style='color:{color}'>"
                     f"{esc(STATUS_LABELS.get(record.status, record.status))}</td>"
                     f"<td>{esc(record.time_label)}</td><td>{esc(record.note)}</td></tr>")
    parts.append("</table></section>")
    for section in report.sections:
        parts.append(f"<section><h2>{esc(section.title)}</h2><table>")
        for row in section.rows:
            if not row.loading:
                parts.append(f"<tr><td class='k'>{esc(row.label)}</td><td>{esc(row.value)}</td></tr>")
        parts.append("</table></section>")
    parts.append(f"<section><h2>Phần mềm đã cài ({len(report.programs)})</h2><table>"
                 "<tr><th>Tên</th><th>Phiên bản</th><th>Hãng</th></tr>")
    for entry in report.programs:
        parts.append(f"<tr><td>{esc(entry.name)}</td><td>{esc(entry.version)}</td><td>{esc(entry.publisher)}</td></tr>")
    parts.append("</table></section></body></html>")
    return "\n".join(parts)


def file_name(computer_name: str, now: datetime) -> str:
    safe = re.sub(r"[^A-Za-z0-9-]", "_", computer_name) or "may"
    return f"CaiMay_{safe}_{now:%Y%m%d_%H%M}.html"


def save(report_html: str, computer_name: str, now: datetime, origin: str = "") -> list[Path]:
    """Ghi vào thư mục reports của tool và, nếu tool chạy từ ổ mang theo, vào <ổ>\\Reports. Trả các file đã ghi."""
    name = file_name(computer_name, now)
    targets = [paths.reports_dir() / name]
    if origin and Path(origin).is_dir():
        targets.append(Path(origin) / REPORT_DIR_ON_DRIVE / name)
    written = []
    for target in targets:
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(report_html, encoding="utf-8")
            written.append(target)
        except OSError:
            log.exception("Không ghi được báo cáo vào %s", target)
    return written
