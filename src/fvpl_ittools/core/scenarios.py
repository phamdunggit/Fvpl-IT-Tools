"""Sửa lỗi theo tình huống (KE-HOACH-GIAO-DIEN.md mục 5.8): Kiểm tra → Đề xuất → Sửa → Kiểm tra lại → Kết quả.

- data/scenarios.yaml: mỗi tình huống có script kiểm tra và bảng "dấu hiệu → cách sửa".
- data/scripts/scenarios/<check>.ps1: script CHỈ ĐỌC, gọi `Add-Finding 'id' 'trạng thái' 'câu dễ hiểu' 'chi tiết'`
  cho từng điều kiểm tra. Trạng thái: ok, warn, bad, info. Cuối script tool tự in dòng `##FINDINGS [...]`.
- Dấu hiệu warn / bad có `fix` thì các mục đó vào danh sách "Tool sẽ làm"; bad tick sẵn, warn / info chỉ tick sẵn
  khi bảng khai báo `checked: true`.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from ..actions.model import Action, Risk
from . import paths, pslib, shell

SCENARIOS_FILE = paths.DATA_DIR / "scenarios.yaml"
SCRIPTS_DIR = paths.DATA_DIR / "scripts" / "scenarios"
MARK = "##FINDINGS"
STATES = ("ok", "warn", "bad", "info")
TIMEOUT = 150

PREAMBLE = """\
$Findings = New-Object System.Collections.Generic.List[object]
function Add-Finding([string]$Id, [string]$State, [string]$Text, [string]$Detail = '') {
    $Findings.Add([pscustomobject]@{ id = $Id; state = $State; text = $Text; detail = $Detail })
}
"""
# ConvertTo-Json của PowerShell 5.1 lỗi "Argument types do not match" với @(List[object]): đổi sang mảng trước.
EPILOGUE = """
Write-Output ('##FINDINGS ' + (ConvertTo-Json -InputObject ([object[]]$Findings.ToArray()) -Compress -Depth 3))
"""
_SCENARIO_KEYS = {"id", "title", "short", "tile", "icon", "check", "keywords", "findings", "more", "description"}
_RULE_KEYS = {"fix", "advice", "link", "link_text", "checked"}


class ScenarioError(RuntimeError):
    pass


@dataclass(frozen=True)
class Rule:
    fix: tuple[str, ...] = ()
    advice: str = ""          # việc IT / người dùng tự làm, khi tool không sửa được
    link: str = ""            # đích điều hướng (giống tìm kiếm), ví dụ "tab:printers:Thêm máy in"
    link_text: str = ""
    checked: bool = False     # tick sẵn mục sửa kể cả khi dấu hiệu chỉ là warn / info


@dataclass(frozen=True)
class Scenario:
    id: str
    title: str
    tile: str
    icon: str
    check: str
    keywords: tuple[str, ...] = ()
    rules: dict[str, Rule] = field(default_factory=dict)
    more: tuple[tuple[str, str], ...] = ()  # (đích, chữ) khi sửa xong mà vẫn chưa được
    description: str = ""
    short: str = ""  # tên ngắn cho nút trên trang Sửa lỗi

    @property
    def target(self) -> str:
        return f"guide:{self.id}"


@dataclass(frozen=True)
class Finding:
    id: str
    state: str
    text: str
    detail: str = ""

    @property
    def problem(self) -> bool:
        return self.state in ("warn", "bad")


@dataclass
class PlannedFix:
    action: Action
    reasons: list[str]        # câu của các dấu hiệu dẫn tới mục này
    checked: bool


# ---------------------------------------------------------------- nạp


def _texts(value: Any, key: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ScenarioError(f"'{key}' phải là danh sách chữ")
    return tuple(item.strip() for item in value if item.strip())


def parse_scenario(raw: Any) -> Scenario:
    if not isinstance(raw, dict):
        raise ScenarioError("mỗi tình huống là một khối 'khoá: giá trị'")
    unknown = sorted(set(raw) - _SCENARIO_KEYS)
    if unknown:
        raise ScenarioError(f"không hiểu khoá {', '.join(unknown)}")
    for key in ("id", "title", "tile", "check"):
        if not isinstance(raw.get(key), str) or not raw[key].strip():
            raise ScenarioError(f"thiếu '{key}'")
    rules: dict[str, Rule] = {}
    for finding_id, rule in (raw.get("findings") or {}).items():
        rule = rule or {}
        if not isinstance(rule, dict) or set(rule) - _RULE_KEYS:
            raise ScenarioError(f"dấu hiệu {finding_id}: chỉ nhận {', '.join(sorted(_RULE_KEYS))}")
        rules[str(finding_id)] = Rule(
            fix=_texts(rule.get("fix"), "fix"), advice=str(rule.get("advice") or "").strip(),
            link=str(rule.get("link") or ""), link_text=str(rule.get("link_text") or ""),
            checked=bool(rule.get("checked", False)),
        )
    more = []
    for item in raw.get("more") or []:
        if not isinstance(item, dict) or not item.get("target") or not item.get("text"):
            raise ScenarioError("'more' là danh sách { target: ..., text: ... }")
        more.append((str(item["target"]), str(item["text"])))
    return Scenario(
        id=raw["id"].strip(), title=raw["title"].strip(), tile=raw["tile"].strip(),
        icon=str(raw.get("icon") or "wrench"), check=raw["check"].strip(), keywords=_texts(raw.get("keywords"), "keywords"),
        rules=rules, more=tuple(more), description=str(raw.get("description") or "").strip(),
        short=str(raw.get("short") or raw["title"]).strip(),
    )


def load(file: Path = SCENARIOS_FILE) -> tuple[list[Scenario], list[str]]:
    scenarios, errors = [], []
    try:
        data = yaml.safe_load(file.read_text(encoding="utf-8")) or []
    except (OSError, yaml.YAMLError) as exc:
        return [], [f"{file.name}: không đọc được ({exc})"]
    for index, raw in enumerate(data if isinstance(data, list) else [], start=1):
        try:
            scenarios.append(parse_scenario(raw))
        except ScenarioError as exc:
            errors.append(f"{file.name} tình huống {index}: {exc}")
    return scenarios, errors


# ---------------------------------------------------------------- kiểm tra


def script_path(scenario: Scenario) -> Path:
    return SCRIPTS_DIR / f"{scenario.check}.ps1"


def script(scenario: Scenario) -> str:
    body = script_path(scenario).read_text(encoding="utf-8")
    return PREAMBLE + pslib.with_helpers(body) + EPILOGUE


def parse_findings(output: str) -> list[Finding]:
    lines = [line for line in output.splitlines() if line.startswith(MARK)]
    if not lines:
        raise ScenarioError("script kiểm tra không trả kết quả")
    try:
        data = json.loads(lines[-1][len(MARK):].strip() or "[]")
    except ValueError as exc:
        raise ScenarioError(f"kết quả kiểm tra không đọc được: {exc}") from exc
    items = data if isinstance(data, list) else [data]
    return [Finding(str(item.get("id") or ""), str(item.get("state") or "info") if item.get("state") in STATES else "info",
                    str(item.get("text") or ""), str(item.get("detail") or ""))
            for item in items if isinstance(item, dict)]


def run_check(scenario: Scenario, variables: dict[str, str], cancel: threading.Event | None = None) -> list[Finding]:
    """Chạy script kiểm tra (chỉ đọc) ở thread gọi hàm này. `variables`: biến dựng sẵn như của mục YAML."""
    text = script(scenario)
    used = {name: value for name, value in variables.items() if f"${name.lower()}" in text.lower()}
    result = shell.run_powershell(text, variables=used, timeout=TIMEOUT, cancel=cancel)
    if result.cancelled:
        raise ScenarioError("Đã huỷ")
    if result.timed_out:
        raise ScenarioError(f"Kiểm tra quá {TIMEOUT} giây chưa xong")
    return parse_findings(result.output)


# ---------------------------------------------------------------- đề xuất


def plan(scenario: Scenario, findings: list[Finding], actions: dict[str, Action]) -> list[PlannedFix]:
    """Các mục sửa theo thứ tự dấu hiệu, không trùng. Mục Nâng cao không bao giờ tick sẵn."""
    planned: dict[str, PlannedFix] = {}
    for finding in findings:
        rule = scenario.rules.get(finding.id)
        if rule is None or not rule.fix or finding.state == "ok":
            continue
        checked = finding.state == "bad" or rule.checked
        for action_id in rule.fix:
            action = actions.get(action_id)
            if action is None:
                continue
            item = planned.setdefault(action_id, PlannedFix(action, [], False))
            item.reasons.append(finding.text)
            item.checked = (item.checked or checked) and action.risk is not Risk.ADVANCED
    return list(planned.values())


def remaining_problems(findings: list[Finding]) -> list[Finding]:
    return [finding for finding in findings if finding.problem]
