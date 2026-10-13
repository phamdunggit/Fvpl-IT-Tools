from __future__ import annotations

import os

import pytest

from fvpl_ittools.actions.model import CmdStep, PowerShellStep
from fvpl_ittools.software import catalog, detect, install
from fvpl_ittools.software.catalog import CatalogError
from fvpl_ittools.software.detect import InstalledEntry

SHARE = r"\\files.corp.example\IT$\ITTools"


def winget_app(**overrides):
    raw = {"id": "chrome", "name": "Google Chrome", "group": "Trình duyệt", "source": "winget",
           "winget_id": "Google.Chrome"}
    raw.update(overrides)
    return catalog.parse_app(raw)


def share_app(**overrides):
    raw = {"id": "office", "name": "Microsoft Office", "source": "share",
           "installer": r"{share}\Installers\Office\setup.exe", "args": r'/configure "{share}\Installers\Office\c.xml"'}
    raw.update(overrides)
    return catalog.parse_app(raw)


def senv(**overrides):
    values = {"is_admin": True, "runs_as_other_user": False, "winget": r"C:\winget.exe", "share_root": SHARE,
              "share_ok": True}
    values.update(overrides)
    return install.SoftwareEnv(**values)


# ---------------------------------------------------------------- danh mục


def test_bundled_catalog_loads_without_errors():
    loaded = catalog.load_catalog_file(catalog.BUNDLED_FILE)
    assert loaded.errors == []
    assert {"chrome", "office", "unikey", "zalo"} <= {app.id for app in loaded.apps}
    assert {"van-phong", "ke-toan", "it"} <= {profile.id for profile in loaded.profiles}


def test_profile_inheritance_keeps_parent_apps_first_without_duplicates(tmp_path):
    file = tmp_path / "apps.yaml"
    file.write_text(
        "apps:\n"
        "  - {id: a, name: A, source: winget, winget_id: X.A}\n"
        "  - {id: b, name: B, source: winget, winget_id: X.B}\n"
        "  - {id: c, name: C, source: winget, winget_id: X.C}\n"
        "profiles:\n"
        "  base: {apps: [a, b]}\n"
        "  child: {extends: base, apps: [c, a]}\n"
        "  grandchild: {extends: [child], apps: [b]}\n",
        encoding="utf-8",
    )
    loaded = catalog.load_catalog_file(file)
    assert loaded.errors == []
    assert [app.id for app in loaded.profile_apps("grandchild")] == ["a", "b", "c"]
    assert loaded.profiles[0].name == "base"


def test_profile_errors_are_reported_and_dropped(tmp_path):
    file = tmp_path / "apps.yaml"
    file.write_text(
        "apps:\n"
        "  - {id: a, name: A, source: winget, winget_id: X.A}\n"
        "  - {id: a, name: Trùng, source: winget, winget_id: X.B}\n"
        "  - {id: bad, name: Sai, source: ftp}\n"
        "profiles:\n"
        "  ok: {apps: [a]}\n"
        "  missing-app: {apps: [a, zzz]}\n"
        "  loop-1: {extends: loop-2, apps: [a]}\n"
        "  loop-2: {extends: loop-1, apps: [a]}\n"
        "  orphan: {extends: nobody, apps: [a]}\n"
        "  child-of-bad: {extends: orphan, apps: [a]}\n"
        "  child-of-broken: {extends: missing-app, apps: [a]}\n",
        encoding="utf-8",
    )
    loaded = catalog.load_catalog_file(file)
    assert [app.id for app in loaded.apps] == ["a"]
    assert [profile.id for profile in loaded.profiles] == ["ok"]
    text = "\n".join(loaded.errors)
    assert "trùng id" in text and "'source' chỉ nhận" in text
    assert "không có ứng dụng zzz" in text
    assert "kế thừa vòng tròn" in text
    assert "kế thừa profile nobody không có" in text
    assert "child-of-bad: kế thừa profile nobody không có" in text  # truy tới gốc của lỗi
    assert "child-of-broken: kế thừa profile missing-app đang khai báo sai" in text


@pytest.mark.parametrize("overrides, message", [
    ({"id": "Chrome"}, "id chỉ gồm"),
    ({"winget_id": ""}, "thiếu 'winget_id'"),
    ({"winget_id": "a b"}, "winget_id không hợp lệ"),
    ({"exe": "x.exe"}, "không dùng khoá exe"),
    ({"scope": "everyone"}, "'scope' chỉ nhận"),
    ({"detect": {"name": "x"}}, "'detect' nhận"),
    ({"colour": "red"}, "không hiểu khoá colour"),
])
def test_invalid_winget_apps(overrides, message):
    with pytest.raises(CatalogError, match=message):
        winget_app(**overrides)


@pytest.mark.parametrize("overrides, message", [
    ({"installer": ""}, "cần 'installer'"),
    ({"installer": r"{server}\x.exe"}, "có {server} không hiểu"),
    ({"type": "portable"}, "cần 'exe'"),
    ({"type": "portable", "exe": r"bin\x.exe"}, "chỉ là tên"),
    ({"autostart": True}, "chỉ dùng cho type: portable"),
    ({"winget_id": "X.Y"}, "không dùng winget_id"),
])
def test_invalid_share_apps(overrides, message):
    with pytest.raises(CatalogError, match=message):
        share_app(**overrides)


def test_share_type_inferred_and_portable_detect_default():
    assert share_app().type == "exe"
    assert share_app(installer=r"{share}\x\Tool.MSI").type == "msi"
    portable = share_app(id="unikey", type="portable", installer=r"{share}\UniKey", exe="UniKeyNT.exe")
    assert portable.detect_file == r"{programfiles}\unikey\UniKeyNT.exe"
    assert catalog.uses_share(share_app()) and not catalog.uses_share(winget_app())


def test_iso_type():
    app = share_app(installer=r"{share}\Office\SW_DVD5_Office_2016.ISO", args=r'/config "{share}\Office\o16.xml"')
    assert app.type == "iso" and app.setup == "setup.exe"
    assert share_app(installer=r"{share}\x.iso", setup=r"x64\setup.exe").setup == r"x64\setup.exe"
    for bad in (r"..\setup.exe", r"C:\setup.exe", r"\setup.exe"):
        with pytest.raises(CatalogError, match="bên trong ISO"):
            share_app(installer=r"{share}\x.iso", setup=bad)
    with pytest.raises(CatalogError, match="chỉ dùng cho type: iso"):
        share_app(setup="setup.exe")
    script = install.install_action(app, SHARE).apply[0].script
    assert f"$image = '{SHARE}\\Office\\SW_DVD5_Office_2016.ISO'" in script
    assert "Mount-DiskImage" in script and "Dismount-DiskImage" in script
    assert "$program = Join-Path $folder 'setup.exe'" in script
    assert f"$arguments = '/config \"{SHARE}\\Office\\o16.xml\"'" in script
    assert script.index("finally") < script.index("exit $code")


def test_expand_placeholders(monkeypatch):
    monkeypatch.setenv("ProgramW6432", r"C:\Program Files")
    assert catalog.expand(r"{share}\a.msi", SHARE + "\\") == SHARE + r"\a.msi"
    assert catalog.expand(r"{programfiles}\X", "") == r"C:\Program Files\X"


def test_load_catalog_prefers_share_copy(tmp_path):
    share_file = tmp_path / "config" / "apps.yaml"
    share_file.parent.mkdir()
    share_file.write_text("apps:\n  - {id: only, name: Only, source: winget, winget_id: X.Y}\n", encoding="utf-8")
    assert [app.id for app in catalog.load_catalog(str(tmp_path)).apps] == ["only"]
    assert catalog.load_catalog(str(tmp_path / "khong-co")).source == str(catalog.BUNDLED_FILE)


# ---------------------------------------------------------------- phát hiện


ENTRIES = [
    InstalledEntry("Google Chrome", "130.0.1"),
    InstalledEntry("Microsoft 365 Apps for business - en-us", "16.0.1"),
    InstalledEntry("Microsoft Windows Desktop Runtime - 8.0.12 (x64)", "64.48.26178"),
    InstalledEntry("Microsoft Windows Desktop Runtime - 8.0.12 (x64)", "8.0.12.34500"),
    InstalledEntry("Notepad++ (64-bit x64)", "8.7"),
]


def test_detect_by_name_pattern_and_default_name():
    assert detect.detect(winget_app(), ENTRIES) == detect.Detection(True, "130.0.1", "Google Chrome")
    office = share_app(detect={"uninstall_name": "Microsoft 365*|Microsoft Office*"})
    assert detect.detect(office, ENTRIES).installed
    assert not detect.detect(winget_app(id="vlc", name="VLC media player", winget_id="VideoLAN.VLC"), ENTRIES).installed
    npp = winget_app(id="npp", name="Notepad++", winget_id="Notepad++.Notepad++")
    assert detect.detect(npp, ENTRIES).version == "8.7"


def test_detect_prefers_version_matching_name():
    dotnet = winget_app(id="dotnet", name=".NET", winget_id="Microsoft.DotNet.DesktopRuntime.8",
                        detect={"uninstall_name": "Microsoft Windows Desktop Runtime - 8.*"})
    assert detect.detect(dotnet, ENTRIES).version == "8.0.12.34500"


def test_detect_by_file(tmp_path):
    (tmp_path / "Tool.exe").write_text("x")
    app = share_app(id="tool", type="portable", installer=r"{share}\Tool", exe="Tool.exe",
                    detect={"file": str(tmp_path / "Tool.exe")})
    assert detect.detect(app, []).installed
    assert not detect.detect(share_app(detect={"file": str(tmp_path / "khong.exe")}), []).installed


def test_conflicts_block_install():
    from fvpl_ittools.software.detect import InstalledEntry
    app = share_app(id="office2016", installer=r"{share}\Office2016.iso", args="",
                    detect={"uninstall_name": "Microsoft Office Standard 2016*"},
                    conflicts="Microsoft 365*|Microsoft Office Standard 2013*")
    assert app.conflict_names == ("Microsoft 365*", "Microsoft Office Standard 2013*")
    entries = [InstalledEntry("Microsoft 365 - en-us", "16.0"), InstalledEntry("7-Zip 24.08"),
               InstalledEntry("Microsoft 365 Hidden Part", hidden=True)]
    assert detect.conflicts(app, entries) == ["Microsoft 365 - en-us"]  # mục ẩn không tính
    assert detect.conflicts(share_app(), entries) == []
    reason = install.blocked_reason(app, senv(conflicts=(("office2016", "Microsoft 365 - en-us"),)))
    assert "Microsoft 365 - en-us" in reason and "Gỡ Microsoft 365" in reason
    assert install.blocked_reason(app, senv()) is None
    with pytest.raises(catalog.CatalogError, match="conflicts"):
        share_app(conflicts=["Microsoft 365*"])


def test_installed_programs_reads_this_machine():
    entries = detect.installed_programs()
    assert entries and all(entry.name for entry in entries)


def test_hidden_uninstall_entries(test_key):
    """Thành phần hệ thống và bản cập nhật vẫn đọc (để phát hiện đã cài) nhưng đánh dấu ẩn cho báo cáo."""
    import winreg
    subkey = test_key.split("\\", 1)[1]
    for name, extra in (("App", {}), ("Lib", {"SystemComponent": 1}), ("KB1", {"ParentKeyName": "App"})):
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, f"{subkey}\\{name}") as key:
            winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, name)
            for value_name, value in extra.items():
                kind = winreg.REG_DWORD if isinstance(value, int) else winreg.REG_SZ
                winreg.SetValueEx(key, value_name, 0, kind, value)
    entries = {entry.name: entry.hidden for entry in detect._read_entries(winreg.HKEY_CURRENT_USER, subkey)}
    assert entries == {"App": False, "Lib": True, "KB1": True}


# ---------------------------------------------------------------- cài


def test_blocked_reasons():
    assert install.blocked_reason(winget_app(), senv()) is None
    assert "quyền admin" in install.blocked_reason(winget_app(), senv(is_admin=False))
    assert "winget" in install.blocked_reason(winget_app(), senv(winget=None))
    assert "share_root" in install.blocked_reason(share_app(), senv(share_root=""))
    assert "Không vào được kho bộ cài" in install.blocked_reason(share_app(), senv(share_ok=False))
    assert "Không thấy bộ cài" in install.blocked_reason(share_app(), senv(missing=frozenset({"office"})))
    user_app = winget_app(scope="user")
    assert "tài khoản khác" in install.blocked_reason(user_app, senv(runs_as_other_user=True))
    assert install.blocked_reason(user_app, senv()) is None


def test_winget_action():
    action = install.install_action(winget_app(), SHARE)
    step = action.apply[0]
    assert isinstance(step, CmdStep)
    assert step.command == (
        "winget install --id Google.Chrome --exact --source winget --silent "
        "--accept-package-agreements --accept-source-agreements --disable-interactivity"
    )
    assert 0x8A150061 in step.ok_codes and 0x8A150109 in step.reboot_codes
    assert "không tìm thấy gói" in step.message_for(0x8A150014)
    assert action.id == "app.chrome" and action.name == "Cài Google Chrome"


def test_share_actions_expand_paths_and_quote():
    exe = install.install_action(share_app(), SHARE).apply[0]
    assert isinstance(exe, PowerShellStep)
    assert f"$program = '{SHARE}\\Installers\\Office\\setup.exe'" in exe.script
    assert f"$arguments = '/configure \"{SHARE}\\Installers\\Office\\c.xml\"'" in exe.script
    assert "Start-Process" in exe.script and "-Wait" not in exe.script
    msi = install.install_action(share_app(id="agent", installer=r"{share}\Agent's.msi", args="ALLUSERS=1"), SHARE)
    script = msi.apply[0].script
    assert "Agent''s.msi" in script  # ngoặc đơn trong đường dẫn được nhân đôi
    assert "msi_agent_" in script and "/qn /norestart" in script and "$extra = 'ALLUSERS=1'" in script
    assert msi.apply[0].reboot_codes == (3010, 1641)


def test_portable_action():
    app = share_app(id="unikey", name="UniKey", type="portable", installer=r"{share}\UniKey", exe="UniKeyNT.exe",
                    autostart=True, args="")
    script = install.install_action(app, SHARE).apply[0].script
    assert "robocopy $source $target" in script and "if ($LASTEXITCODE -ge 8)" in script
    assert "'UniKey.lnk'" in script and "'StartUp\\UniKey.lnk'" in script
    assert script.rstrip().endswith("exit 0")


def test_generated_scripts_parse(env, tmp_path):
    """Script cài đặt dựng từ danh mục đóng gói phải đúng cú pháp PowerShell."""
    import json

    from fvpl_ittools.core import executor, shell

    from .test_scripts import _PARSE
    loaded = catalog.load_catalog_file(catalog.BUNDLED_FILE)
    extra = [share_app(id="m", installer=r"{share}\a b\x.msi"),
             share_app(id="p", type="portable", installer=r"{share}\P", exe="p.exe", autostart=True, args=""),
             share_app(id="i", installer=r"{share}\Office 2016.ISO", setup=r"x64\setup.exe")]
    scripts = []
    for app in loaded.apps + extra:
        step = install.install_action(app, SHARE).apply[0]
        if isinstance(step, PowerShellStep):
            scripts.append({"name": app.id, "script": shell.build_powershell_script(
                executor.ps_script_for(step), variables=executor.ps_variables(env))})
    assert len(scripts) >= 3
    file = tmp_path / "scripts.json"
    file.write_text(json.dumps(scripts, ensure_ascii=False), encoding="utf-8")
    result = shell.run_powershell(_PARSE, variables={"ScriptsFile": str(file)}, timeout=120)
    assert json.loads(result.output.strip().splitlines()[-1]) == []
    assert os.path.exists(catalog.BUNDLED_FILE)
