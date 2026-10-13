from __future__ import annotations

import threading
import time

from fvpl_ittools.core import shell


def test_decoder_utf8_split_across_chunks():
    decoder = shell.StreamDecoder()
    data = "Đã xong".encode("utf-8")
    assert decoder.decode(data[:3]) + decoder.decode(data[3:], final=True) == "Đã xong"


def test_decoder_detects_utf16le_like_sfc():
    decoder = shell.StreamDecoder()
    data = "\r\nĐang quét 12%".encode("utf-16-le")
    assert decoder.decode(data, final=True) == "\r\nĐang quét 12%"


def test_decoder_falls_back_to_oem_codepage(monkeypatch):
    monkeypatch.setattr(shell, "oem_encoding", lambda: "cp437")
    decoder = shell.StreamDecoder()
    assert decoder.decode(b"ch\x85o", final=True) == "chào"


def test_line_splitter_handles_crlf_progress_and_chunk_boundaries():
    splitter = shell.LineSplitter()
    lines = splitter.feed("a\r")
    lines += splitter.feed("\nb\r\r\n10%\r20%\rc")
    lines += splitter.flush()
    assert lines == [("a", False), ("b", False), ("10%", True), ("20%", True), ("c", False)]


def test_run_cmd_returns_exit_code_and_output():
    result = shell.run_cmd('echo xin chao & echo "co ngoac kep" & exit /b 3')
    assert result.code == 3
    assert result.output.splitlines() == ["xin chao ", '"co ngoac kep" ']


def test_run_cmd_streams_lines():
    received = []
    shell.run_cmd("echo mot & echo hai", on_line=lambda text, progress: received.append(text))
    assert [line.strip() for line in received] == ["mot", "hai"]


def test_run_cmd_timeout_kills_process():
    started = time.monotonic()
    result = shell.run_cmd("ping -n 30 127.0.0.1 >nul", timeout=1)
    assert result.timed_out
    assert time.monotonic() - started < 10


def test_run_powershell_utf8_and_native_exit_code():
    result = shell.run_powershell("Write-Output 'Tiếng Việt: đã xong'; cmd /c exit 5")
    assert result.code == 5
    assert result.output == "Tiếng Việt: đã xong"


def test_run_powershell_other_streams_are_plain_text():
    result = shell.run_powershell("Write-Warning 'cảnh báo'; Write-Host 'dòng host'; Write-Output 'xong'")
    assert "CLIXML" not in result.output
    assert result.output.splitlines() == ["WARNING: cảnh báo", "dòng host", "xong"]


def test_long_script_is_compacted_to_fit_command_line():
    body = "\n".join(f"    # chú thích dài {'x' * 80}\n    $a{i} = {i}" for i in range(300))
    result = shell.run_powershell(body + "\nWrite-Output $a299")
    assert result.output == "299"


def test_run_powershell_error_becomes_exit_code_1():
    result = shell.run_powershell(r"Get-Item 'C:\khong-co-file-nay-dau'")
    assert result.code == 1
    assert result.output.startswith("LỖI:")


def test_run_powershell_credential_via_stdin():
    script = "Write-Output ($Credential.UserName + '|' + $Credential.GetNetworkCredential().Password)"
    result = shell.run_powershell(script, credential=("CORP\\test", "mật khẩu 'có' ngoặc"))
    assert result.ok
    assert result.output == "CORP\\test|mật khẩu 'có' ngoặc"


def test_run_powershell_cancel():
    cancel = threading.Event()
    threading.Timer(0.5, cancel.set).start()
    started = time.monotonic()
    result = shell.run_powershell("Start-Sleep -Seconds 20", cancel=cancel)
    assert result.cancelled
    assert time.monotonic() - started < 10


def test_ps_quote_escapes_all_single_quote_kinds():
    assert shell.ps_quote("it's ‘x’") == "'it''s ‘‘x’’'"
    result = shell.run_powershell(f"Write-Output {shell.ps_quote('it’s ok')}")
    assert result.output == "it’s ok"
