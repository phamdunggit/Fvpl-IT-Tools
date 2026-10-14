from __future__ import annotations

import winreg

from fvpl_ittools.core import shell
from fvpl_ittools.software import uninstall
from fvpl_ittools.software.uninstall import Program

from .conftest import TEST_ROOT

PROFILE = r"C:\Users\an"
SID = "S-1-5-21-1-2-3-1001"


def program(name: str, uninstall_string: str = "", **values) -> Program:
    return Program(name=name, key=rf"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{name}",
                   uninstall=uninstall_string, **values)


def test_split_command_handles_quotes_and_spaces():
    assert uninstall.split_command('"C:\\Program Files\\A\\uninst.exe" /S') == (r"C:\Program Files\A\uninst.exe", "/S")
    assert uninstall.split_command(r"C:\Program Files (x86)\B\uninstall.exe /x y") == (
        r"C:\Program Files (x86)\B\uninstall.exe", "/x y")
    assert uninstall.split_command("MsiExec.exe /X{1}") == ("MsiExec.exe", "/X{1}")
    assert uninstall.split_command("winget uninstall --id A") == ("winget", "uninstall --id A")


def test_plan_picks_silent_command():
    rules = uninstall.load_rules()
    code = "{12345678-1234-1234-1234-123456789ABC}"
    msi = uninstall.plan(program("App", f"MsiExec.exe /I{code}", msi_code=code), rules)
    assert msi.msi and msi.args == f"/x {code} /qn /norestart"
    quiet = uninstall.plan(program("Q", '"C:\\q\\u.exe"', quiet='"C:\\q\\u.exe" /quiet'), rules)
    assert (quiet.file, quiet.args, quiet.silent) == (r"C:\q\u.exe", "/quiet", True)
    wps = Program(name="WPS Office (12.2)", key="HKEY_USERS\\x", user_sid=SID,
                  uninstall=r'"%LOCALAPPDATA%\Kingsoft\WPS Office\12.2\utility\uninst.exe"')
    plan = uninstall.plan(wps, rules, PROFILE)
    assert plan.file == r"C:\Users\an\AppData\Local\Kingsoft\WPS Office\12.2\utility\uninst.exe"
    assert plan.args == "/S" and plan.silent
    inno = uninstall.plan(program("I", r'"C:\I\unins000.exe"', inno=True), rules)
    assert inno.args == uninstall.INNO_ARGS
    chrome = uninstall.plan(program("Cốc Cốc", r'"C:\C\setup.exe" --uninstall --system-level'), rules)
    assert chrome.args.endswith("--force-uninstall") and chrome.silent
    winget = uninstall.plan(program("Bun", "winget uninstall --product-code Bun"), rules)
    assert winget.args.endswith("--silent --disable-interactivity")
    manual = uninstall.plan(program("TeamViewer", r'"C:\T\uninstall.exe"'), rules)
    assert not manual.silent and manual.how == "Bấm theo trình gỡ"
    assert uninstall.plan(program("Không lệnh"), rules) is None


def test_rules_from_store_come_first(tmp_path):
    config = tmp_path / "config"
    config.mkdir()
    (config / "uninstall.yaml").write_text(
        "unwanted:\n  - match: 'Cốc Cốc*'\n    reason: Công ty dùng Chrome\n"
        "keep:\n  - match: 'WPS Office*'\n    reason: Phòng X cần\n"
        "silent:\n  - match: 'TeamViewer*'\n    args: /S\n", encoding="utf-8")
    rules = uninstall.load_rules(str(tmp_path))
    assert rules.errors == []
    assert rules.unwanted_reason(program("Cốc Cốc")) == "Công ty dùng Chrome"
    assert rules.unwanted_reason(program("WPS Office")).startswith("Bộ văn phòng")  # mục đóng gói vẫn còn
    assert rules.keep_reason(program("WPS Office")) == ""  # nên gỡ thì không "nên giữ"
    assert rules.keep_reason(program("Microsoft Visual C++ 2015-2022 Redistributable (x64)"))
    assert uninstall.plan(program("TeamViewer", r'"C:\T\uninstall.exe"'), rules).args == "/S"
    (config / "uninstall.yaml").write_text("remove:\n  - x\n", encoding="utf-8")
    assert uninstall.load_rules(str(tmp_path)).errors


def test_unwanted_skips_hidden_entries():
    rules = uninstall.load_rules()
    programs = [program("WPS Office"), program("McAfee Security Scan", hidden=True), program("Zalo")]
    assert [item.name for item, _reason in uninstall.unwanted(programs, rules)] == ["WPS Office"]


def test_uninstall_actions():
    rules = uninstall.load_rules()
    code = "{12345678-1234-1234-1234-123456789ABC}"
    msi = uninstall.uninstall_action(program("App", msi_code=code), rules)
    assert msi.admin and msi.apply[0].ok_codes == (0, 1605) and "/x " + code in msi.apply[0].script
    wps = Program(name="WPS Office", key=rf"HKEY_USERS\{SID}\Software\Microsoft\Windows\CurrentVersion\Uninstall\Kingsoft",
                  user_sid=SID, uninstall=r'"C:\Users\an\AppData\Local\Kingsoft\uninst.exe"')
    own = uninstall.uninstall_action(wps, rules, profile=PROFILE)
    script = own.apply[0].script
    assert not own.admin and "$asUser = $false" in script and shell.ps_quote(f"Registry::{wps.key}") in script
    assert "$arguments = '/S'" in script and "##PROGRESS" in script
    other = uninstall.uninstall_action(wps, rules, as_user=True, profile=PROFILE)
    assert other.admin and "$asUser = $true" in other.apply[0].script
    assert own.id == other.id == uninstall.action_id(wps) and own.id.startswith("soft.uninstall_")
    assert uninstall.uninstall_action(program("Không lệnh"), rules) is None
    assert uninstall.size_text(0) == "" and uninstall.size_text(2048) == "2 MB"


def test_read_registry_entries():
    subkey = rf"{TEST_ROOT}\Uninstall"
    code = "{12345678-1234-1234-1234-123456789ABC}"
    values = {
        "WPS Office": {"DisplayName": "WPS Office", "UninstallString": r'"C:\W\uninst.exe"', "EstimatedSize": 2048,
                       "InstallDate": "20261001"},
        code: {"DisplayName": "Ứng dụng MSI", "UninstallString": f"MsiExec.exe /I{code}", "WindowsInstaller": 1},
        "Inno_is1": {"DisplayName": "Inno", "UninstallString": r'"C:\I\unins000.exe"'},
        "Part": {"DisplayName": "Thành phần", "UninstallString": "x.exe", "SystemComponent": 1},
        "NoName": {"UninstallString": "x.exe"},
    }
    try:
        for name, entries in values.items():
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"{subkey}\{name}") as key:
                for value_name, value in entries.items():
                    kind = winreg.REG_DWORD if isinstance(value, int) else winreg.REG_SZ
                    winreg.SetValueEx(key, value_name, 0, kind, value)
        found = {item.name: item for item in uninstall._read(winreg.HKEY_CURRENT_USER, rf"HKEY_CURRENT_USER\{subkey}",
                                                             subkey, 0, SID)}
    finally:
        for name in values:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, rf"{subkey}\{name}")
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, subkey)
    assert set(found) == {"WPS Office", "Ứng dụng MSI", "Inno", "Thành phần"}
    wps = found["WPS Office"]
    assert wps.size_kb == 2048 and wps.date_text == "01/10/2026" and wps.per_user and not wps.hidden
    assert wps.key == rf"HKEY_CURRENT_USER\{subkey}\WPS Office"
    assert found["Ứng dụng MSI"].msi_code == code and found["Inno"].inno and found["Thành phần"].hidden
