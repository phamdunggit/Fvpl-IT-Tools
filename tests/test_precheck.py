from __future__ import annotations

from dataclasses import replace

from fvpl_ittools.app import build_context
from fvpl_ittools.newpc import precheck


def facts(**overrides):
    values = dict(
        is_admin=True, build=26100, os_label="Windows 11 Pro 24H2", joined_domain=False, domain="corp.example",
        share_root=r"\\files.corp.example\IT$", share_ok=True, winget=True, disk_free_gb=120.0,
        has_battery=True, on_ac=True, pending_reboot=[],
        network={
            "adapters": [{"name": "Ethernet", "ipv4": ["10.0.0.25"], "gateway": ["10.0.0.1"], "dns": ["10.0.0.10"],
                          "wireless": False}],
            "dns": [{"server": "10.0.0.10", "finds_dc": True}],
            "dc": "10.0.0.10", "offset": 2.5, "internet": True,
        },
    )
    values.update(overrides)
    return precheck.Facts(**values)


def by_key(checks):
    return {check.key: check for check in checks}


def network(**overrides):
    data = dict(facts().network)
    data.update(overrides)
    return data


def test_ready_machine():
    checks = precheck.evaluate(facts())
    assert all(check.state == "ok" for check in checks), [c for c in checks if c.state != "ok"]
    assert precheck.summary(checks) == ("ok", "Máy sẵn sàng để cài")


def test_dns_not_pointing_to_dc_skips_dc_and_time():
    checks = by_key(precheck.evaluate(facts(network=network(dns=[{"server": "8.8.8.8", "finds_dc": False}], dc=None))))
    assert checks["dns"].state == "bad" and "8.8.8.8" in checks["dns"].detail
    assert checks["dc"].state == checks["time"].state == "skip"
    state, text = precheck.summary(list(checks.values()))
    assert state == "bad" and "DNS trỏ về DC" in text


def test_secondary_public_dns_is_a_warning():
    dns = [{"server": "10.0.0.10", "finds_dc": True}, {"server": "8.8.8.8", "finds_dc": False}]
    check = by_key(precheck.evaluate(facts(network=network(dns=dns))))["dns"]
    assert check.state == "warn" and "8.8.8.8" in check.detail


def test_time_offset_levels_offer_time_sync():
    assert by_key(precheck.evaluate(facts(network=network(offset=-90))))["time"].state == "warn"
    bad = by_key(precheck.evaluate(facts(network=network(offset=400))))["time"]
    assert bad.state == "bad" and bad.fix == "dom.time_sync" and "400 giây" in bad.detail
    assert by_key(precheck.evaluate(facts(network=network(offset=None))))["time"].state == "warn"


def test_dc_not_answering():
    checks = by_key(precheck.evaluate(facts(network=network(dc=None))))
    assert checks["dc"].state == "bad" and checks["time"].state == "skip"


def test_other_checks():
    checks = by_key(precheck.evaluate(facts(
        is_admin=False, build=19044, pending_reboot=["Windows Update"], winget=False, disk_free_gb=8,
        on_ac=False, share_ok=False, domain="",
        network=network(adapters=[{"name": "Wi-Fi", "ipv4": ["192.0.2.5"], "gateway": ["192.0.2.1"], "dns": [],
                                   "wireless": True}], internet=False),
    )))
    assert checks["admin"].state == "bad"
    assert checks["windows"].state == "bad"
    assert checks["reboot"].state == "warn" and "Windows Update" in checks["reboot"].detail
    assert checks["network"].state == "warn"  # Wi-Fi
    assert checks["internet"].state == "warn"
    assert checks["dns"].state == "warn" and "site.yaml" in checks["dns"].hint  # chưa biết domain
    assert checks["share"].state == "warn"  # chưa vào domain nên chưa vào được share là bình thường
    assert checks["winget"].state == "warn"
    assert checks["disk"].state == "bad"
    assert checks["power"].state == "warn"


def test_joined_machine_and_share_errors():
    checks = by_key(precheck.evaluate(facts(joined_domain=True, share_ok=False)))
    assert checks["joined"].state == "ok"
    assert checks["share"].state == "bad"
    no_share = by_key(precheck.evaluate(facts(share_root="")))["share"]
    assert no_share.state == "warn" and "share_root" in no_share.detail and "SOFT" in no_share.detail


def test_network_script_failure():
    checks = by_key(precheck.evaluate(facts(network=None, network_error="PowerShell lỗi")))
    assert checks["network"].state == "bad" and "PowerShell lỗi" in checks["network"].detail


def test_to_text():
    text = precheck.to_text(precheck.evaluate(facts(on_ac=False)), "PC-01")
    assert text.splitlines()[0] == "Kiểm tra trước khi cài máy PC-01"
    assert "⚠ Nguồn điện: Laptop đang chạy bằng pin → Cắm sạc" in text


def test_collect_on_this_machine_reads_only():
    app = build_context()
    collected = precheck.collect(replace(app, software=replace(app.software, root="")))
    assert collected.network is not None, collected.network_error
    assert collected.disk_free_gb > 0
    checks = precheck.evaluate(collected)
    assert {"admin", "windows", "network", "internet", "disk", "power"} <= set(by_key(checks))
