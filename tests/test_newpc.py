from __future__ import annotations

from datetime import datetime

import pytest

from fvpl_ittools.actions.model import CmdStep, PowerShellStep
from fvpl_ittools.core import config, inventory, paths
from fvpl_ittools.newpc import naming, report, state, steps
from fvpl_ittools.software.detect import InstalledEntry

# ---------------------------------------------------------------- tên máy


@pytest.mark.parametrize("name, ok", [
    ("FVPL-KT05", True), ("PC1", True),
    ("", False), ("FVPL-KETOAN-0001", False), ("FVPL_KT05", False), ("-FVPL", False), ("FVPL-", False),
    ("12345", False), ("MÁY-01", False),
])
def test_name_problem(name, ok):
    assert (naming.name_problem(name) is None) is ok


def test_suggest_name_takes_next_number():
    existing = ["FVPL-KT01", "fvpl-kt07", "FVPL-KT03", "FVPL-KTX1", "FVPL-NS09", "FVPL-KT"]
    assert naming.suggest_name("FVPL-", "kt", existing) == "FVPL-KT08"
    assert naming.suggest_name("FVPL-", "IT", existing) == "FVPL-IT01"
    assert naming.suggest_name("FVPL-", "KT", ["FVPL-KT99"]) == "FVPL-KT100"
    assert naming.taken("fvpl-kt07", existing) and not naming.taken("FVPL-KT02", existing)


def test_existing_names_rejects_bad_input():
    with pytest.raises(naming.NamingError, match="domain"):
        naming.existing_names("", "FVPL-KT")
    with pytest.raises(naming.NamingError, match="Tiền tố"):
        naming.existing_names("corp.example", "FVPL)(cn=*")


# ---------------------------------------------------------------- trạng thái wizard


def test_state_round_trip_and_next_step(state_dir):
    assert state.load() is None and state.active() is None
    wizard = state.WizardState(department="KT", computer_name="FVPL-KT05", origin="E:\\FVPL-ITTools")
    wizard.mark("info", "ok", "Tên FVPL-KT05")
    wizard.mark("join", "ok")
    state.save(wizard)
    loaded = state.load()
    assert loaded.computer_name == "FVPL-KT05" and loaded.steps["info"].note == "Tên FVPL-KT05"
    assert loaded.next_step() == "after"
    loaded.mark("after", "skipped")
    assert loaded.next_step() == "software"
    loaded.finished = "2026-10-13T10:00:00"
    state.save(loaded)
    assert state.load() is not None and state.active() is None


def test_state_keeps_extra_apps(state_dir):
    wizard = state.WizardState(computer_name="FVPL-KT05", extra_apps=["office2016", "unikey"], template="Kế toán")
    state.save(wizard)
    loaded = state.load()
    assert loaded.extra_apps == ["office2016", "unikey"] and loaded.template == "Kế toán"
    state.state_path().write_text('{"computer_name": "X", "extra_apps": "sai kiểu"}', encoding="utf-8")
    assert state.load().extra_apps == []


# ---------------------------------------------------------------- mẫu


def test_templates_save_overwrite_delete(tmp_path):
    from fvpl_ittools.newpc import templates
    file = tmp_path / "wizard-templates.json"
    assert templates.load(file) == []
    templates.save(file, templates.Template("Kế toán – Laptop", "KT", "ke-toan", ["office2016"]))
    saved = templates.save(file, templates.Template("  Nhân sự  ", "NS", "van-phong"))
    assert [item.name for item in saved] == ["Kế toán – Laptop", "Nhân sự"]
    # Cùng tên (khác hoa thường) thì ghi đè.
    saved = templates.save(file, templates.Template("kế toán – laptop", "KT", "ke-toan", ["office2013"]))
    assert len(saved) == 2 and saved[0].apps == ["office2013"]
    assert [item.name for item in templates.delete(file, "Nhân sự")] == ["kế toán – laptop"]
    with pytest.raises(ValueError):
        templates.save(file, templates.Template("   "))
    with pytest.raises(ValueError):
        templates.save(file, templates.Template("x" * 61))


def test_templates_ignore_broken_entries(tmp_path):
    from fvpl_ittools.newpc import templates
    file = tmp_path / "wizard-templates.json"
    file.write_text('{"templates": [{"name": "A", "department": "kt", "apps": "sai"}, {"name": ""}, 5]}',
                    encoding="utf-8")
    assert templates.load(file) == [templates.Template("A", "KT", "", [])]
    file.write_text("{hỏng", encoding="utf-8")
    assert templates.load(file) == []


def test_templates_live_next_to_site_yaml(tmp_path, monkeypatch):
    from fvpl_ittools.newpc import templates
    site = config.load_site_config([tmp_path / "khong-co.yaml"])
    monkeypatch.setattr(paths, "app_root", lambda: tmp_path / "usb")
    assert templates.templates_path(site) == tmp_path / "usb" / "wizard-templates.json"
    file = tmp_path / "cfg" / "site.yaml"
    file.parent.mkdir()
    file.write_text("domain: corp.example\n", encoding="utf-8")
    assert templates.templates_path(config.load_site_config([file])) == tmp_path / "cfg" / "wizard-templates.json"


def test_state_ignores_broken_file(state_dir):
    state.state_path().write_text("{không phải json", encoding="utf-8")
    assert state.load() is None


def test_origin_soft(tmp_path):
    assert state.origin_soft(None) is None
    wizard = state.WizardState(origin=str(tmp_path))
    assert state.origin_soft(wizard) is None
    (tmp_path / "SOFT").mkdir()
    assert state.origin_soft(wizard) == tmp_path / "SOFT"
    # Tool chạy tiếp từ bản chép trong ProgramData: dùng SOFT trên ổ SSD nếu còn cắm, trước cả share.
    site = config.SiteConfig(share_root="\\\\srv\\IT$")
    source = config.software_source(site, app_root=tmp_path / "khac", extra_local=tmp_path / "SOFT")
    assert source.kind == "local" and source.root == str(tmp_path / "SOFT")


def test_resume_command_from_source():
    program, arguments = state.resume_command()
    assert program.lower().endswith("python.exe") and arguments == "-m fvpl_ittools --resume"


# ---------------------------------------------------------------- mã phòng trong site.yaml


def test_add_department_keeps_comments(tmp_path):
    file = tmp_path / "site.yaml"
    file.write_text("# chú thích của IT\ndomain: corp.example\n\ndepartments:\n  KT: \"Kế toán\"\n\n"
                    "# cuối file\ncomputer_prefix: FVPL-\n", encoding="utf-8")
    site = config.load_site_config([file])
    assert site.departments == (("KT", "Kế toán"),)
    updated = config.add_department(site, "ns", "  Nhân   sự ")
    assert updated.departments == (("KT", "Kế toán"), ("NS", "Nhân sự"))
    text = file.read_text(encoding="utf-8")
    assert text.startswith("# chú thích của IT") and "# cuối file" in text
    assert updated.domain == "corp.example" and updated.computer_prefix == "FVPL-"

    with pytest.raises(ValueError, match="đã có"):
        config.add_department(updated, "KT", "Kế toán 2")
    with pytest.raises(ValueError, match="chữ in hoa"):
        config.add_department(updated, "KẾ", "x")
    with pytest.raises(ValueError, match="tên phòng"):
        config.add_department(updated, "IT", "  ")


def test_add_department_creates_block_or_file(tmp_path, monkeypatch):
    file = tmp_path / "site.yaml"
    file.write_text("domain: corp.example\ndepartments: {}\n", encoding="utf-8")
    assert config.add_department(config.load_site_config([file]), "KHO", "Kho").departments == (("KHO", "Kho"),)

    file.write_text("domain: corp.example", encoding="utf-8")
    assert config.add_department(config.load_site_config([file]), "IT", "IT").departments == (("IT", "IT"),)

    file.write_text("departments: {KT: Kế toán}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="nhiều dòng"):
        config.add_department(config.load_site_config([file]), "IT", "IT")

    # Chưa có site.yaml: tạo cạnh tool.
    monkeypatch.setattr(paths, "app_root", lambda: tmp_path / "usb")
    (tmp_path / "usb").mkdir()
    created = config.add_department(config.SiteConfig(), "KT", "Kế toán")
    assert created.source == tmp_path / "usb" / "site.yaml" and created.departments == (("KT", "Kế toán"),)


def test_site_config_reports_bad_departments(tmp_path):
    file = tmp_path / "site.yaml"
    file.write_text("departments:\n  KT: Kế toán\n  ke-toan: Sai\ncomputer_ou: OU=May,DC=corp,DC=example\n",
                    encoding="utf-8")
    site = config.load_site_config([file])
    assert site.departments == (("KT", "Kế toán"),) and site.computer_ou == "OU=May,DC=corp,DC=example"
    assert any("KE-TOAN" in error for error in site.errors)


# ---------------------------------------------------------------- mục join và sau khởi động lại


def test_join_action():
    action = steps.join_action("fvpl-kt05", "corp.example", "OU=May tram,DC=corp,DC=example", copy_app=True)
    assert action.needs_credential == "domain" and action.reboot and action.risk.value == "advanced"
    copy, acl, join, task = action.apply
    assert isinstance(copy, CmdStep) and copy.command.startswith("robocopy ") and "/XD" in copy.command
    assert acl.command.startswith("icacls ") and "*S-1-5-32-545:(OI)(CI)RX" in acl.command  # Users chỉ đọc
    assert isinstance(join, PowerShellStep) and "$NewName = 'FVPL-KT05'" in join.script
    assert "$OUPath = 'OU=May tram,DC=corp,DC=example'" in join.script
    assert f"$TaskName = '{state.RESUME_TASK}'" in task.script and "-RunLevel Highest" in task.script
    assert len(steps.join_action("FVPL-KT05", "corp.example", "", copy_app=False).apply) == 2

    with pytest.raises(steps.StepError):
        steps.join_action("FVPL KT05", "corp.example", "")
    with pytest.raises(steps.StepError, match="domain"):
        steps.join_action("FVPL-KT05", "", "")
    with pytest.raises(steps.StepError, match="OU"):
        steps.join_action("FVPL-KT05", "corp.example", "May tram")


def test_after_restart_actions():
    existing = {"dom.time_sync": "TIME", "dom.gpupdate": "GP"}
    actions = steps.after_restart_actions("FVPL-KT05", "CORP\\IT Admins", existing)
    assert actions[0].id == "newpc.verify" and actions[1:3] == ["TIME", "GP"]
    assert actions[3].id == "newpc.it_admins" and "$Group = 'CORP\\IT Admins'" in actions[3].apply[0].script
    assert [getattr(item, "id", item) for item in steps.after_restart_actions("X", "", existing)] == [
        "newpc.verify", "TIME", "GP"]
    with pytest.raises(steps.StepError, match="DOMAIN"):
        steps.it_admins_action("IT Admins")


# ---------------------------------------------------------------- báo cáo


def test_report_html_and_save(state_dir, tmp_path):
    wizard = state.WizardState(department="KT", computer_name="FVPL-KT05", primary_user="Nguyễn <A>")
    wizard.mark("info", "ok", "Tên FVPL-KT05")
    wizard.mark("join", "failed", "Sai mật khẩu")
    basics = inventory.Basics(computer_name="FVPL-KT05", domain_label="corp.example", joined_domain=True,
                              os_label="Windows 11", target_user="CORP\\a", is_admin=True,
                              now=datetime(2026, 10, 13, 9, 30))
    sections = [inventory.Section("hardware", "Phần cứng", (inventory.Row("Serial", "ABC123"),))]
    data = report.ReportData(wizard, basics, sections, [InstalledEntry("7-Zip", "24.08", "Igor Pavlov")],
                             "corp.example", "CORP\\it", "0.3.0")
    page = report.to_html(data)
    assert "Nguyễn &lt;A&gt;" in page and "Sai mật khẩu" in page and "ABC123" in page and "7-Zip" in page
    assert "Chưa làm" in page  # bước chưa làm vẫn hiện

    origin = tmp_path / "usb"
    origin.mkdir()
    files = report.save(page, "FVPL-KT05", basics.now, str(origin))
    assert [file.name for file in files] == ["CaiMay_FVPL-KT05_20261013_0930.html"] * 2
    assert files[0].parent == paths.reports_dir() and files[1].parent == origin / "Reports"
    assert len(report.save(page, "FVPL-KT05", basics.now, str(tmp_path / "da-rut"))) == 1
