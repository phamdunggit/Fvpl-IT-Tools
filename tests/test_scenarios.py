from __future__ import annotations

import re

import pytest

from fvpl_ittools.actions import loader
from fvpl_ittools.core import scenarios, shell
from fvpl_ittools.core.support_report import SupportReport

ACTIONS = {action.id: action for action in loader.load_builtin_actions()[0]}
SCENARIOS, ERRORS = scenarios.load()


def test_bundled_scenarios_load_and_point_to_real_actions():
    assert ERRORS == []
    assert {item.id for item in SCENARIOS} >= {"network", "printing", "domain", "slow", "office", "windows_update"}
    for item in SCENARIOS:
        assert scenarios.script_path(item).is_file(), item.check
        for finding_id, rule in item.rules.items():
            assert all(action_id in ACTIONS for action_id in rule.fix), (item.id, finding_id)
            assert rule.fix or rule.advice or rule.link, (item.id, finding_id)
            if rule.link:
                assert rule.link.split(":", 1)[0] in ("page", "tab", "action", "guide", "fixes"), rule.link
        assert item.more


@pytest.mark.parametrize("item", SCENARIOS, ids=[item.id for item in SCENARIOS])
def test_scripts_are_read_only_emit_known_findings_and_fit(item):
    body = scenarios.script_path(item).read_text(encoding="utf-8")
    emitted = set(re.findall(r"Add-Finding '([a-z0-9_]+)' '(?:warn|bad|info)'", body))
    every = set(re.findall(r"Add-Finding '([a-z0-9_]+)'", body))
    assert set(item.rules) <= every, "dấu hiệu khai báo trong YAML mà script không bao giờ báo"
    assert emitted - set(item.rules) <= {"trust_unknown"}, "dấu hiệu có vấn đề nhưng YAML không nói cách xử lý"
    lowered = body.lower()
    for verb in ("set-itemproperty", "remove-item", "stop-service", "restart-service", "new-item", "set-service",
                 "start-process", "remove-printjob", "ipconfig /", "netsh winhttp reset", "w32tm /resync"):
        assert verb not in lowered, f"script kiểm tra phải chỉ đọc: có {verb}"
    shell.encode_for_command_line(scenarios.script(item))  # không quá giới hạn dòng lệnh


def test_parse_findings_and_errors():
    output = 'chữ khác\n##FINDINGS [{"id":"a","state":"bad","text":"Lỗi A","detail":"x"},{"id":"b","state":"lạ","text":"B"}]'
    findings = scenarios.parse_findings(output)
    assert findings == [scenarios.Finding("a", "bad", "Lỗi A", "x"), scenarios.Finding("b", "info", "B", "")]
    assert scenarios.parse_findings('##FINDINGS {"id":"c","state":"ok","text":"C"}')[0].id == "c"
    with pytest.raises(scenarios.ScenarioError):
        scenarios.parse_findings("LỖI: không chạy được")


def test_plan_ticks_bad_findings_and_never_advanced():
    scenario = scenarios.parse_scenario({
        "id": "t", "title": "T", "tile": "t", "check": "printing", "more": [{"target": "page:home", "text": "x"}],
        "findings": {
            "stuck": {"fix": ["prn.clear_queue"]},
            "down": {"fix": ["prn.restart_spooler", "prn.clear_queue"]},
            "rpc": {"fix": ["prn.share_client_fix"]},
            "rpc_checked": {"fix": ["prn.share_host_privacy_off"], "checked": True},
            "tip": {"advice": "Tự làm"},
        },
    })
    findings = [scenarios.Finding("stuck", "bad", "Kẹt lệnh in"), scenarios.Finding("down", "warn", "Spooler tắt"),
                scenarios.Finding("rpc", "warn", "RPC"), scenarios.Finding("rpc_checked", "bad", "Mã hoá"),
                scenarios.Finding("tip", "bad", "Tip"), scenarios.Finding("ok", "ok", "Ổn")]
    planned = {item.action.id: item for item in scenarios.plan(scenario, findings, ACTIONS)}
    assert list(planned) == ["prn.clear_queue", "prn.restart_spooler", "prn.share_client_fix", "prn.share_host_privacy_off"]
    assert planned["prn.clear_queue"].checked and planned["prn.clear_queue"].reasons == ["Kẹt lệnh in", "Spooler tắt"]
    assert not planned["prn.restart_spooler"].checked and not planned["prn.share_client_fix"].checked
    assert not planned["prn.share_host_privacy_off"].checked  # mục Nâng cao không bao giờ tick sẵn
    assert [item.id for item in scenarios.remaining_problems(findings)] == ["stuck", "down", "rpc", "rpc_checked", "tip"]
    with pytest.raises(scenarios.ScenarioError, match="lạ"):
        scenarios.parse_scenario({"id": "x", "title": "X", "tile": "x", "check": "x", "lạ": 1})


def test_support_report_text_and_file(tmp_path):
    report = SupportReport("FVPL-KT05", "corp.example", "Windows 11", "CORP\\an", "0.2.0", topic="Không in được",
                           findings=[("bad", "Có 2 lệnh in bị kẹt", ""), ("ok", "Spooler chạy", "")],
                           actions=[("Xoá lệnh in bị kẹt", "Xong")], note="Đã sửa xong", log=["dòng 1", "dòng 2"])
    text = report.to_text()
    assert "Máy: FVPL-KT05 (corp.example)" in text and "Tình huống: Không in được" in text
    assert "✖ Có 2 lệnh in bị kẹt" in text and "- Xoá lệnh in bị kẹt: Xong" in text and "  dòng 2" in text
    file = report.save(tmp_path)
    assert file.name.startswith("GuiIT_FVPL-KT05_") and "Có 2 lệnh in bị kẹt" in file.read_text(encoding="utf-8")
