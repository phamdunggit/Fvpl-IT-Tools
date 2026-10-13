from __future__ import annotations

from fvpl_ittools.core import config, registry, session
from fvpl_ittools.core.journal import JournalEntry, RegChange, UndoJournal


def make_entry(action_id="a.b"):
    change = RegChange("HKCU\\Software\\X", "V", registry.MISSING, registry.RegValue(True, registry.TYPES["SZ"], "mới"))
    return JournalEntry.new(action_id, "Tên mục", "TEST\\it", "TEST\\user", [change], ["restart_explorer"])


def test_journal_persists_and_marks_undone(tmp_path):
    path = tmp_path / "journal.json"
    first, second = make_entry(), make_entry()
    journal = UndoJournal(path)
    journal.add(first)
    journal.add(second)

    reopened = UndoJournal(path)
    assert [entry.id for entry in reopened.entries()] == [second.id, first.id]
    assert reopened.latest_for("a.b").id == second.id
    reopened.mark_undone(second.id)
    assert UndoJournal(path).latest_for("a.b").id == first.id
    loaded = UndoJournal(path).get(first.id)
    assert loaded.changes[0].after.value == "mới"
    assert loaded.after == ["restart_explorer"]


def test_corrupt_journal_is_set_aside(tmp_path):
    path = tmp_path / "journal.json"
    path.write_text("{ không phải json", encoding="utf-8")
    journal = UndoJournal(path)
    assert journal.entries() == []
    assert list(tmp_path.glob("journal.corrupt-*.json"))
    journal.add(make_entry())
    assert len(journal.entries()) == 1


def test_site_config(tmp_path):
    assert not config.load_site_config([tmp_path / "khong-co.yaml"]).loaded
    file = tmp_path / "site.yaml"
    file.write_text("domain: corp.example\nshare_root: '\\\\srv\\IT$'\ntypo: 1\n", encoding="utf-8")
    site = config.load_site_config([file])
    assert site.loaded and site.domain == "corp.example" and site.share_root == "\\\\srv\\IT$"
    assert site.errors == ("site.yaml: không hiểu khoá 'typo'",)


def test_software_source_prefers_soft_next_to_tool(tmp_path):
    site = config.SiteConfig(share_root=r"\\files.corp.example\IT$")
    usb = config.software_source(site, app_root=tmp_path)
    assert (usb.root, usb.kind) == (r"\\files.corp.example\IT$", "share")
    (tmp_path / "SOFT").mkdir()
    ssd = config.software_source(site, app_root=tmp_path)
    assert (ssd.root, ssd.kind) == (str(tmp_path / "SOFT"), "local")
    assert "ổ mang theo" in ssd.label
    nothing = config.software_source(config.SiteConfig(), app_root=tmp_path / "khac")
    assert nothing.kind == "" and "SOFT" in nothing.label


def test_process_and_session_user():
    me = session.process_user()
    assert me.sid.startswith("S-1-5-")
    assert "\\" in me.name or me.name
    logged_on = session.session_user()
    assert logged_on is not None
    assert logged_on.sid == me.sid
    assert session.hive_loaded(me.sid)
