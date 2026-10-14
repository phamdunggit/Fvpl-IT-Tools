from __future__ import annotations

from datetime import datetime

import pytest

from fvpl_ittools.actions import loader
from fvpl_ittools.core import health, inventory, search

from .test_inventory import SAMPLE


def test_fold_and_tokens():
    assert search.fold("Máy in Đã kẹt") == "may in da ket"
    assert search.query_tokens("máy in không in được") == ["in"]  # bỏ từ không mang nghĩa, bỏ trùng
    assert search.query_tokens("không được") == ["khong", "duoc"]  # chỉ có từ phổ biến thì vẫn dùng
    assert search.query_tokens("Lỗi 0x0000011B") == ["0x0000011b"]


def _index():
    return search.Index([
        search.Entry("action", "Xoá lệnh in bị kẹt", "action:prn.clear_queue", "Dừng Print Spooler, xoá lệnh in",
                     "Máy in", "máy in kẹt lệnh in spooler"),
        search.Entry("action", "Reset Windows Update", "action:wu.reset", "Windows Update lỗi", "Sửa lỗi › Windows Update",
                     "cập nhật lỗi", advanced=True),
        search.Entry("action", "Kiểm tra share máy in", "action:prn.share_check", "Chỉ xem", "Máy in",
                     "0x0000011b rpc win11"),
        search.Entry("tool", "Xem mật khẩu Wi-Fi đã lưu", "tab:utilities:Công cụ khác", "", "", "wifi mật khẩu"),
        search.Entry("page", "Máy in", "page:printers", "Thêm, gỡ, sửa máy in"),
    ])


def test_search_ranks_title_matches_and_short_words_match_whole_words():
    results, hidden = _index().search("máy in không in được")
    targets = [entry.target for entry in results]
    # Mọi mục có chữ "in" trong tên, cùng điểm thì giữ thứ tự trong chỉ mục; "in" không khớp "Windows".
    assert targets == ["action:prn.clear_queue", "action:prn.share_check", "page:printers"]
    assert hidden == 0


def test_search_error_codes_accents_and_advanced():
    index = _index()
    assert [entry.target for entry in index.search("0x0000011b")[0]] == ["action:prn.share_check"]
    assert index.search("mat khau wifi")[0][0].target == "tab:utilities:Công cụ khác"
    results, hidden = index.search("windows update", include_advanced=False)
    assert results == [] and hidden == 1
    assert index.search("windows update")[0][0].target == "action:wu.reset"
    assert index.search("")[0] == [] and index.search("zzz")[0] == []


def test_search_prefers_entries_matching_every_word():
    index = _index()
    results, _ = index.search("kẹt spooler")
    assert [entry.target for entry in results] == ["action:prn.clear_queue"]


def test_fix_and_printer_actions_have_keywords():
    actions, errors = loader.load_builtin_actions()
    assert not errors
    missing = [action.id for action in actions if action.page in ("fixes", "printers") and not action.keywords]
    assert missing == []
    with pytest.raises(loader.ActionError, match="keywords"):
        loader.parse_action({"id": "test.kw", "name": "X", "category": "Y", "keywords": [1, 2],
                             "apply": [{"cmd": "exit /b 0"}]})


def test_health_items_from_inventory():
    basics = inventory.Basics("FVPL-KT05", "corp.example", True, "Windows 11", "CORP\\an", True,
                              now=datetime(2026, 10, 14, 9, 0))
    items = health.items(SAMPLE, basics)
    texts = [item.text for item in items]
    assert items[0].state in ("bad", "warn")  # có vấn đề lên trước
    drive = next(item for item in items if item.text.startswith("Ổ C"))
    assert drive.button == "Dọn rác" and drive.target == "page:optimize"
    update = next(item for item in items if "chưa cập nhật" in item.text)
    assert update.target == "action:wu.scan_install"
    assert any(text.startswith("Máy chạy liên tục") for text in texts)
    assert "Đã vào domain corp.example" in texts
    workgroup = inventory.Basics("PC", "Workgroup WORKGROUP", False, "Windows 11", "PC\\an", True)
    assert health.items({}, workgroup)[0].target == "page:newpc"
