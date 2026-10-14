"""Soát cú pháp mọi script PowerShell mà tool có thể chạy, bằng chính trình phân tích của PowerShell.

Không chạy script nào, chỉ parse. Bắt được lỗi kiểu "$bien:" trong chuỗi, thiếu ngoặc, sai cú pháp
mà test chạy thật không phủ được (các mục sửa lỗi không được chạy trên máy dev).
"""

from __future__ import annotations

import json

from fvpl_ittools.actions import loader
from fvpl_ittools.cleanup import startup
from fvpl_ittools.actions.model import PowerShellStep
from fvpl_ittools.core import adsecrets, drivers, eventlog, executor, inventory, pslib, safety, shell
from fvpl_ittools.newpc import naming, precheck, steps

from . import test_printers as printers_test

_PARSE = """\
$items = Get-Content -LiteralPath $ScriptsFile -Raw -Encoding UTF8 | ConvertFrom-Json
$problems = @()
foreach ($item in $items) {
    $tokens = $null
    $errors = $null
    [void][System.Management.Automation.Language.Parser]::ParseInput($item.script, [ref]$tokens, [ref]$errors)
    foreach ($e in $errors) {
        $problems += [pscustomobject]@{ name = $item.name; line = $e.Extent.StartLineNumber; message = $e.Message }
    }
}
ConvertTo-Json -InputObject @($problems) -Compress
"""


def _bundled_steps() -> list[tuple[str, str, bool]]:
    """(tên, script thật sẽ chạy kèm hàm dựng sẵn, có hỏi tài khoản không) của mọi bước PowerShell."""
    actions, errors = loader.load_builtin_actions()
    assert errors == []
    steps = []
    for action in actions:
        for index, step in enumerate(action.apply + action.undo_steps, start=1):
            if isinstance(step, PowerShellStep):
                steps.append((f"{action.id} bước {index}", executor.ps_script_for(step),
                              action.needs_credential is not None))
    return steps


def _bundled_scripts(env) -> list[dict]:
    return [
        {"name": name, "script": shell.build_powershell_script(
            script, with_credential=credential, variables=executor.ps_variables(env))}
        for name, script, credential in _bundled_steps()
    ]


def _internal_scripts() -> list[dict]:
    return [
        {"name": "restart_explorer", "script": executor.explorer_script()},
        {"name": "rebuild_icon_cache", "script": executor.explorer_script(
            executor._ICON_CACHE_BEFORE, executor._ICON_CACHE_WHILE_STOPPED)},
        {"name": "start_explorer_as_user", "script": executor._START_EXPLORER_AS_USER},
        {"name": "restore_point", "script": safety._RESTORE_POINT_SCRIPT.replace("__DESC__", "'x'")},
        {"name": "check_helpers", "script": pslib.CHECK_HELPERS},
        {"name": "precheck", "script": pslib.with_helpers(precheck._NETWORK_SCRIPT)},
    ] + [{"name": f"inventory {part}", "script": inventory.part_script(part)} for part in inventory.PARTS] + [
        {"name": name, "script": pslib.with_helpers(script)}
        for name, script in printers_test.generated_scripts() + steps.generated_scripts()
    ] + [{"name": "newpc tên máy trong AD", "script": naming.ad_script()},
         {"name": "startup task", "script": startup.TASK_SCRIPT},
         {"name": "startup bật tắt task", "script": startup._TOGGLE_TASK},
         {"name": "event log", "script": eventlog.script()}] + [
        {"name": name, "script": script} for name, script in drivers.scripts()] + [
        {"name": name, "script": script} for name, script in adsecrets.scripts()]


def test_every_powershell_script_parses(env, tmp_path):
    scripts = _bundled_scripts(env) + _internal_scripts()
    assert len(scripts) > 10
    file = tmp_path / "scripts.json"
    file.write_text(json.dumps(scripts, ensure_ascii=False), encoding="utf-8")
    result = shell.run_powershell(_PARSE, variables={"ScriptsFile": str(file)}, timeout=120)
    assert result.ok, result.output
    problems = json.loads(result.output.strip().splitlines()[-1])
    assert problems == [], "\n".join(f"{p['name']} dòng {p['line']}: {p['message']}" for p in problems)


def test_every_powershell_script_fits_command_line(env):
    """Script truyền qua dòng lệnh, Windows giới hạn độ dài. Quá thì mục chỉ báo lỗi khi chạy thật, nên soát trước.

    Biến dựng sẵn đặt dài 250 ký tự (đường dẫn profile, share dài) cho chắc.
    """
    variables = {name: "x" * 250 for name in executor.ps_variables(env)}
    scripts = [(name, script, credential) for name, script, credential in _bundled_steps()]
    scripts += [(item["name"], item["script"], False) for item in _internal_scripts()]
    too_long = []
    for name, script, credential in scripts:
        try:
            shell.encode_for_command_line(script, with_credential=credential, variables=variables)
        except ValueError:
            too_long.append(name)
    assert too_long == [], f"Script quá dài, cần tách nhỏ: {too_long}"


def test_helpers_are_added_only_when_called():
    script = "if (Test-Port $ip 445) { Write-Ok 'mở' }"
    full = pslib.with_helpers(script)
    assert full.endswith(script) and "$Checks" in full
    assert "function Test-Port" in full and "function Write-Ok" in full
    assert "function Write-Line" in full  # Write-Ok gọi Write-Line
    assert "function Test-DnsSrv" not in full and "function Get-ActiveAdapters" not in full
    domain = pslib.with_helpers("Test-DomainDns $d $s")
    assert "function Test-DnsSrv" in domain and "function Write-Bad" in domain
    assert pslib.with_helpers("Get-Date") == "Get-Date"


def test_bloat_app_lists_match():
    """Mục liệt kê và mục gỡ app cài sẵn phải dùng đúng một danh sách."""
    actions = {action.id: action for action in loader.load_builtin_actions()[0]}

    def names(action_id):
        script = actions[action_id].apply[0].script
        return script[script.index("$names = @("):script.index(")\n")]

    assert names("opt.list_bloat_apps") == names("opt.remove_bloat_apps")


def test_bundled_actions_have_descriptions_and_explain_risky_steps():
    actions, _ = loader.load_builtin_actions()
    for action in actions:
        assert len(action.description) >= 40, f"{action.id}: mô tả quá ngắn"
        if action.needs_credential:
            assert action.risk.value != "safe", f"{action.id}: mục cần tài khoản phải là Cẩn thận/Nâng cao"
