from __future__ import annotations

import json

import pytest

from fvpl_ittools.core import adsecrets


@pytest.mark.parametrize("name, ok", [("fvpl-kt05", True), ("PC1", True), ("", False), ("FVPL-KETOAN-00001", False),
                                      ("pc)(cn=*", False), ("máy-01", False)])
def test_check_computer(name, ok):
    if ok:
        assert adsecrets.check_computer(name) == name.upper()
    else:
        with pytest.raises(adsecrets.SecretLookupError):
            adsecrets.check_computer(name)


def fake_run(output: str):
    calls = []

    def run(script, computer, domain, credential, cancel):
        calls.append((computer, domain, credential))
        return output
    return run, calls


def test_laps_password(monkeypatch):
    run, calls = fake_run(json.dumps({"account": "Administrator", "password": "Pa$$w0rd!xyz", "updated": "01/10/2026 08:00",
                                      "expires": "31/10/2026 08:00", "source": "EncryptedPassword",
                                      "decryption": "Success"}))
    monkeypatch.setattr(adsecrets, "_run", run)
    item = adsecrets.laps_password("fvpl-kt05", "corp.example", ("CORP\\it", "pw"))
    assert (item.computer, item.account, item.password, item.encrypted) == ("FVPL-KT05", "Administrator", "Pa$$w0rd!xyz", True)
    assert calls == [("FVPL-KT05", "corp.example", ("CORP\\it", "pw"))]


def test_laps_password_without_permission(monkeypatch):
    run, _ = fake_run(json.dumps({"account": "Administrator", "password": "", "source": "EncryptedPassword",
                                  "decryption": "Unauthorized"}))
    monkeypatch.setattr(adsecrets, "_run", run)
    with pytest.raises(adsecrets.SecretLookupError, match="giải mã"):
        adsecrets.laps_password("FVPL-KT05", "corp.example")
    run, _ = fake_run(json.dumps({"account": "Administrator", "password": "", "source": "CleartextPassword",
                                  "decryption": ""}))
    monkeypatch.setattr(adsecrets, "_run", run)
    with pytest.raises(adsecrets.SecretLookupError, match="quyền đọc"):
        adsecrets.laps_password("FVPL-KT05", "corp.example")


def test_bitlocker_keys_newest_first(monkeypatch):
    run, _ = fake_run(json.dumps([
        {"id": "AAAA1111-0000-0000-0000-000000000000", "password": "111111-222222", "created": "05/01/2026 09:00"},
        {"id": "BBBB2222-0000-0000-0000-000000000000", "password": "", "created": "20/12/2025 10:00"},
        {"id": "CCCC3333-0000-0000-0000-000000000000", "password": "333333-444444", "created": "05/01/2026 10:30"},
    ]))
    monkeypatch.setattr(adsecrets, "_run", run)
    keys = adsecrets.bitlocker_keys("FVPL-KT05", "corp.example")
    assert [key.key_id[:4] for key in keys] == ["CCCC", "AAAA", "BBBB"]
    # Một khoá thì PowerShell xuất ra một object chứ không phải mảng.
    run, _ = fake_run(json.dumps({"id": "AAAA1111", "password": "1", "created": "05/01/2026 09:00"}))
    monkeypatch.setattr(adsecrets, "_run", run)
    assert len(adsecrets.bitlocker_keys("FVPL-KT05", "corp.example")) == 1
    with pytest.raises(adsecrets.SecretLookupError, match="domain"):
        adsecrets.bitlocker_keys("FVPL-KT05", "")


def test_run_rejects_bad_domain():
    with pytest.raises(adsecrets.SecretLookupError, match="domain"):
        adsecrets.laps_password("FVPL-KT05", "corp.example; calc")
