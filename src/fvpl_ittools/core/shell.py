"""Chạy lệnh cmd / PowerShell ở nền: đọc output từng dòng, giải mã đúng, huỷ được, có giới hạn thời gian."""

from __future__ import annotations

import base64
import codecs
import logging
import os
import re
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from typing import Callable

from . import winapi

log = logging.getLogger(__name__)

CREATE_NO_WINDOW = 0x08000000
MAX_COMMAND_LINE = 32000

LineCallback = Callable[[str, bool], None]
"""Nhận (dòng, là_dòng_tiến_độ). Dòng tiến độ kết thúc bằng '\\r' đơn lẻ như thanh % của DISM."""


@dataclass
class ShellResult:
    code: int | None
    output: str
    timed_out: bool = False
    cancelled: bool = False

    @property
    def ok(self) -> bool:
        return self.code == 0 and not self.timed_out and not self.cancelled


def system_dir() -> str:
    """System32 thật, kể cả khi Python 32-bit chạy trên Windows 64-bit (dùng Sysnative)."""
    windows = os.environ.get("SystemRoot", r"C:\Windows")
    if sys.maxsize <= 2**32 and os.environ.get("PROCESSOR_ARCHITEW6432"):
        return os.path.join(windows, "Sysnative")
    return os.path.join(windows, "System32")


def oem_encoding() -> str:
    try:
        name = f"cp{winapi.oem_codepage()}"
        codecs.lookup(name)
        return name
    except (LookupError, OSError):
        return "mbcs"


def _looks_utf16le(data: bytes) -> bool:
    if data.startswith(codecs.BOM_UTF16_LE):
        return True
    sample = data[:400]
    odd, even = sample[1::2], sample[0::2]
    if len(odd) < 2:
        return False
    return odd.count(0) >= len(odd) * 0.4 and even.count(0) <= len(even) * 0.1


class StreamDecoder:
    """Giải mã output của lệnh Windows.

    Tự nhận UTF-16LE (sfc ghi kiểu này), còn lại thử UTF-8. Gặp byte không phải UTF-8
    thì chuyển sang code page OEM của máy cho phần còn lại.
    """

    def __init__(self, encoding: str = "auto"):
        self._pending = b""
        self._decoder = None
        if encoding != "auto":
            self._decoder = codecs.getincrementaldecoder(encoding)(errors="replace")

    def decode(self, data: bytes, final: bool = False) -> str:
        if self._decoder is None:
            self._pending += data
            if len(self._pending) < 4 and not final:
                return ""
            data, self._pending = self._pending, b""
            if _looks_utf16le(data):
                if data.startswith(codecs.BOM_UTF16_LE):
                    data = data[2:]
                self._decoder = codecs.getincrementaldecoder("utf-16-le")(errors="replace")
            else:
                self._decoder = codecs.getincrementaldecoder("utf-8-sig")(errors="strict")
        try:
            return self._decoder.decode(data, final)
        except UnicodeDecodeError:
            self._decoder = codecs.getincrementaldecoder(oem_encoding())(errors="replace")
            return self._decoder.decode(data, final)


_BREAK = re.compile(r"[\r\n]")


class LineSplitter:
    """Tách text thành dòng. '\\r\\n' (kể cả '\\r\\r\\n') là xuống dòng thường, '\\r' đơn lẻ là dòng tiến độ."""

    def __init__(self) -> None:
        self._buffer = ""

    def feed(self, text: str) -> list[tuple[str, bool]]:
        self._buffer += text
        lines: list[tuple[str, bool]] = []
        while True:
            match = _BREAK.search(self._buffer)
            if match is None:
                break
            start = match.start()
            if self._buffer[start] == "\n":
                lines.append((self._buffer[:start], False))
                self._buffer = self._buffer[start + 1:]
                continue
            end = start
            while end < len(self._buffer) and self._buffer[end] == "\r":
                end += 1
            if end >= len(self._buffer):
                break  # chưa biết sau '\r' có '\n' không, chờ dữ liệu tiếp
            if self._buffer[end] == "\n":
                lines.append((self._buffer[:start], False))
                self._buffer = self._buffer[end + 1:]
            else:
                lines.append((self._buffer[:start], True))
                self._buffer = self._buffer[end:]
        return lines

    def flush(self) -> list[tuple[str, bool]]:
        rest = self._buffer.rstrip("\r")
        self._buffer = ""
        return [(rest, False)] if rest else []


def _kill_tree(proc: subprocess.Popen) -> None:
    try:
        subprocess.run(
            ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=CREATE_NO_WINDOW, timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass
    if proc.poll() is None:
        try:
            proc.kill()
        except OSError:
            pass


def run_process(
    command: str | list[str],
    *,
    stdin_data: bytes | None = None,
    timeout: float | None = None,
    cancel: threading.Event | None = None,
    on_line: LineCallback | None = None,
    encoding: str = "auto",
) -> ShellResult:
    proc = subprocess.Popen(
        command,
        stdin=subprocess.PIPE if stdin_data is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        creationflags=CREATE_NO_WINDOW,
    )
    lines: list[str] = []

    def push(pairs: list[tuple[str, bool]]) -> None:
        for text, progress in pairs:
            if not progress:
                lines.append(text)
            if on_line is not None:
                try:
                    on_line(text, progress)
                except Exception:  # lỗi ở phía hiển thị không được làm mất output
                    log.exception("Lỗi khi đẩy dòng output ra giao diện")

    def reader() -> None:
        decoder = StreamDecoder(encoding)
        splitter = LineSplitter()
        while True:
            chunk = proc.stdout.read1(65536)
            if not chunk:
                break
            push(splitter.feed(decoder.decode(chunk)))
        push(splitter.feed(decoder.decode(b"", final=True)))
        push(splitter.flush())

    reader_thread = threading.Thread(target=reader, name="shell-reader", daemon=True)
    reader_thread.start()

    if stdin_data is not None:
        try:
            proc.stdin.write(stdin_data)
            proc.stdin.close()
        except OSError:
            pass  # tiến trình đã thoát trước khi đọc stdin

    deadline = time.monotonic() + timeout if timeout else None
    timed_out = cancelled = False
    while proc.poll() is None:
        if cancel is not None and cancel.is_set():
            cancelled = True
            _kill_tree(proc)
            break
        if deadline is not None and time.monotonic() > deadline:
            timed_out = True
            _kill_tree(proc)
            break
        if cancel is not None:
            cancel.wait(0.05)
        else:
            time.sleep(0.05)
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
    reader_thread.join(timeout=5)
    return ShellResult(proc.returncode, "\n".join(lines), timed_out, cancelled)


def run_cmd(command: str, **kwargs) -> ShellResult:
    """Chạy một dòng lệnh cmd. Đặt code page UTF-8 trước để chữ có dấu không bị lỗi."""
    comspec = os.path.join(system_dir(), "cmd.exe")
    # /s /c "...": cmd bỏ cặp ngoặc kép ngoài cùng, giữ nguyên ngoặc kép bên trong lệnh.
    command_line = f'"{comspec}" /d /s /c "chcp 65001 >nul 2>&1 & {command}"'
    return run_process(command_line, **kwargs)


_PS_PRELUDE = """\
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
try { [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false } catch { }
$OutputEncoding = New-Object System.Text.UTF8Encoding $false
"""

_PS_CREDENTIAL = """\
try { [Console]::InputEncoding = New-Object System.Text.UTF8Encoding $false } catch { }
$__user = [Console]::In.ReadLine()
$__pass = [Console]::In.ReadLine()
$Credential = New-Object System.Management.Automation.PSCredential($__user, (ConvertTo-SecureString $__pass -AsPlainText -Force))
Remove-Variable __user, __pass
"""


def powershell_exe() -> str:
    return os.path.join(system_dir(), "WindowsPowerShell", "v1.0", "powershell.exe")


_PS_VARIABLE_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def ps_variable_lines(variables: dict[str, str]) -> str:
    """Các dòng `$Ten = 'giá trị'` để đặt sẵn biến cho script."""
    lines = []
    for name, value in variables.items():
        if not _PS_VARIABLE_NAME.match(name):
            raise ValueError(f"Tên biến PowerShell không hợp lệ: {name!r}")
        lines.append(f"${name} = {ps_quote(value)}\n")
    return "".join(lines)


def build_powershell_script(
    script: str, with_credential: bool = False, variables: dict[str, str] | None = None
) -> str:
    """Bọc script: dừng ngay khi gặp lỗi, output UTF-8, trả mã thoát của lệnh native cuối cùng."""
    return (
        _PS_PRELUDE
        + (_PS_CREDENTIAL if with_credential else "")
        + ps_variable_lines(variables or {})
        + "try {\n& {\n"
        + script
        + "\n}\nif ($LASTEXITCODE) { exit $LASTEXITCODE }\nexit 0\n}\ncatch {\n"
        + "[Console]::Error.WriteLine('LỖI: ' + $_.Exception.Message)\nexit 1\n}\n"
    )


def _encode(script: str) -> str:
    return base64.b64encode(script.encode("utf-16-le")).decode("ascii")


def compact_powershell(script: str) -> str:
    """Bỏ dòng trống, dòng chú thích '#' và thụt đầu dòng, để script dài vừa giới hạn dòng lệnh.

    Không dùng được cho script có here-string (@' '@) vì nội dung bên trong sẽ bị đổi.
    """
    if "@'" in script or '@"' in script:
        return script
    lines = (line.strip() for line in script.splitlines())
    return "\n".join(line for line in lines if line and not line.startswith("#"))


def encode_for_command_line(
    script: str, with_credential: bool = False, variables: dict[str, str] | None = None
) -> str:
    """Script đã bọc, mã hoá base64 để đặt trên dòng lệnh; quá dài thì bỏ chú thích và thụt lề rồi thử lại.

    Vẫn quá giới hạn thì ValueError. Test gọi hàm này cho mọi script để biết trước, không phải đợi chạy thật.
    """
    encoded = _encode(build_powershell_script(script, with_credential=with_credential, variables=variables))
    if len(encoded) > MAX_COMMAND_LINE:
        compact = compact_powershell(script)
        encoded = _encode(build_powershell_script(compact, with_credential=with_credential, variables=variables))
    if len(encoded) > MAX_COMMAND_LINE:
        raise ValueError("Script PowerShell quá dài để truyền qua dòng lệnh, hãy tách nhỏ.")
    return encoded


def run_powershell(
    script: str,
    *,
    credential: tuple[str, str] | None = None,
    variables: dict[str, str] | None = None,
    **kwargs,
) -> ShellResult:
    """Chạy script bằng Windows PowerShell 5.1 có sẵn trên mọi máy Win10/11.

    Script được mã hoá base64 và truyền qua -Command kèm đoạn mồi tự giải mã, nên không bị Execution
    Policy (kể cả do GPO đặt) chặn. Không dùng -EncodedCommand: với cờ đó PowerShell ghi cảnh báo,
    Write-Host, verbose ra stderr dạng CLIXML thay vì chữ thường.
    Tài khoản (nếu có) đi qua stdin, không nằm trên dòng lệnh, nên không lộ trong danh sách tiến trình.
    Trong script dùng biến $Credential. `variables` đặt sẵn các biến chuỗi khác cho script.
    """
    encoded = encode_for_command_line(script, with_credential=credential is not None, variables=variables)
    bootstrap = f"& ([ScriptBlock]::Create([Text.Encoding]::Unicode.GetString([Convert]::FromBase64String('{encoded}'))))"
    argv = [
        powershell_exe(), "-NoLogo", "-NoProfile", "-NonInteractive",
        "-ExecutionPolicy", "Bypass", "-Command", bootstrap,
    ]
    stdin_data = None
    if credential is not None:
        user, password = credential
        stdin_data = f"{user}\n{password}\n".encode("utf-8")
    return run_process(argv, stdin_data=stdin_data, **kwargs)


def ps_quote(text: str) -> str:
    """Đặt chuỗi vào ngoặc đơn PowerShell. PowerShell coi cả ‘ ’ ‚ ‛ là ngoặc đơn nên cũng phải nhân đôi."""
    escaped = "".join(ch * 2 if ch in "'\u2018\u2019\u201a\u201b" else ch for ch in text)
    return f"'{escaped}'"
