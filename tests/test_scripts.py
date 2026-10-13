"""Soát cú pháp mọi script PowerShell mà tool có thể chạy, bằng chính trình phân tích của PowerShell.

Không chạy script nào, chỉ parse. Bắt được lỗi kiểu "$bien:" trong chuỗi, thiếu ngoặc, sai cú pháp
mà test chạy thật không phủ được (các mục sửa lỗi không được chạy trên máy dev).
"""

from __future__ import annotations

import json

from fvpl_ittools.actions import loader
from fvpl_ittools.actions.model import PowerShellStep
from fvpl_ittools.core import executor, inventory, pslib, safety, shell

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


def _bundled_scripts(env) -> list[dict]:
    actions, errors = loader.load_builtin_actions()
    assert errors == []
    scripts = []
    for action in actions:
        for index, step in enumerate(action.apply + action.undo_steps, start=1):
            if isinstance(step, PowerShellStep):
                wrapped = shell.build_powershell_script(
                    executor.ps_script_for(step),
                    with_credential=action.needs_credential is not None,
                    variables=executor.ps_variables(env),
                )
                scripts.append({"name": f"{action.id} bước {index}", "script": wrapped})
    return scripts


def _internal_scripts() -> list[dict]:
    return [
        {"name": "restart_explorer", "script": executor.explorer_script()},
        {"name": "rebuild_icon_cache", "script": executor.explorer_script(
            executor._ICON_CACHE_BEFORE, executor._ICON_CACHE_WHILE_STOPPED)},
        {"name": "start_explorer_as_user", "script": executor._START_EXPLORER_AS_USER},
        {"name": "restore_point", "script": safety._RESTORE_POINT_SCRIPT.replace("__DESC__", "'x'")},
        {"name": "check_helpers", "script": pslib.CHECK_HELPERS},
    ] + [{"name": f"inventory {part}", "script": inventory.part_script(part)} for part in inventory.PARTS]


def test_every_powershell_script_parses(env, tmp_path):
    scripts = _bundled_scripts(env) + _internal_scripts()
    assert len(scripts) > 10
    file = tmp_path / "scripts.json"
    file.write_text(json.dumps(scripts, ensure_ascii=False), encoding="utf-8")
    result = shell.run_powershell(_PARSE, variables={"ScriptsFile": str(file)}, timeout=120)
    assert result.ok, result.output
    problems = json.loads(result.output.strip().splitlines()[-1])
    assert problems == [], "\n".join(f"{p['name']} dòng {p['line']}: {p['message']}" for p in problems)


def test_bundled_actions_have_descriptions_and_explain_risky_steps():
    actions, _ = loader.load_builtin_actions()
    for action in actions:
        assert len(action.description) >= 40, f"{action.id}: mô tả quá ngắn"
        if action.needs_credential:
            assert action.risk.value != "safe", f"{action.id}: mục cần tài khoản phải là Cẩn thận/Nâng cao"
