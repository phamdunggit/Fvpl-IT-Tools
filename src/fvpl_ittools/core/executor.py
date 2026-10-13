"""Chạy các mục (action): từng bước, ghi log, lưu nhật ký hoàn tác, gom việc làm sau, báo cần restart.

Không phụ thuộc giao diện: giao diện truyền vào hàm `emit` để nhận từng dòng log,
và `cancel` để huỷ giữa chừng.
"""

from __future__ import annotations

import logging
import subprocess
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Callable

from ..actions.model import (
    BUILTIN_NAMES,
    Action,
    BuiltinStep,
    CmdStep,
    PowerShellStep,
    RegistryStep,
    Risk,
    ServiceStep,
    Step,
)
from . import paths, pslib, registry, safety, shell
from .journal import JournalEntry, RegChange, UndoJournal
from .log import forget_secret, mask, register_secret
from .session import UserIdentity

log = logging.getLogger("fvpl_ittools.run")

DEFAULT_STEP_TIMEOUT = 600.0


class Level(str, Enum):
    HEADER = "header"
    INFO = "info"
    OK = "ok"
    WARN = "warn"
    ERROR = "error"
    CMD = "cmd"
    OUTPUT = "output"


_LOG_LEVELS = {Level.WARN: logging.WARNING, Level.ERROR: logging.ERROR}


@dataclass(frozen=True)
class LogEvent:
    level: Level
    text: str
    progress: bool = False
    time: datetime = field(default_factory=datetime.now)


class Status(str, Enum):
    OK = "ok"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"

    @property
    def label(self) -> str:
        return STATUS_LABELS[self]


STATUS_LABELS = {Status.OK: "Xong", Status.FAILED: "Lỗi", Status.SKIPPED: "Bỏ qua", Status.CANCELLED: "Đã huỷ"}


@dataclass(frozen=True)
class Env:
    """Môi trường chạy: quyền admin, bản Windows, ai chạy tool và thiết lập người dùng áp cho ai."""

    is_admin: bool
    build: int
    process_user: UserIdentity
    target_user: UserIdentity
    joined_domain: bool = False
    share_root: str = ""  # từ site.yaml, rỗng nếu chưa khai báo

    @property
    def user_hive_sid(self) -> str | None:
        """SID cần dùng thay cho HKCU, hoặc None nếu HKCU đã đúng là người dùng cần áp."""
        return None if self.target_user.sid == self.process_user.sid else self.target_user.sid

    def resolve(self, key: str) -> registry.RegPath:
        return registry.resolve_user_key(registry.parse_key(key), self.user_hive_sid)


@dataclass
class RunContext:
    env: Env
    journal: UndoJournal
    emit: Callable[[LogEvent], None] = lambda event: None
    cancel: threading.Event = field(default_factory=threading.Event)
    create_restore_point: bool = True
    restore_point: Callable[..., safety.RestorePointResult] = safety.create_restore_point
    credential: tuple[str, str] | None = None  # (tài khoản, mật khẩu) cho mục needs_credential, chỉ giữ trong RAM

    def say(self, level: Level, text: str, progress: bool = False) -> None:
        text = mask(text)
        if not progress:
            log.log(_LOG_LEVELS.get(level, logging.INFO), "%s", text)
        self.emit(LogEvent(level, text, progress))


@dataclass
class StepOutcome:
    status: Status = Status.OK
    message: str = ""
    changed: bool = False
    reboot: bool = False


@dataclass
class ActionResult:
    action: Action
    status: Status
    message: str = ""
    changed: bool = False
    reboot_required: bool = False
    journal_id: str | None = None
    seconds: float = 0.0
    finished_at: datetime = field(default_factory=datetime.now)


@dataclass
class BatchResult:
    results: list[ActionResult] = field(default_factory=list)
    cancelled: bool = False

    @property
    def reboot_required(self) -> bool:
        return any(result.reboot_required for result in self.results)

    def count(self, status: Status) -> int:
        return sum(1 for result in self.results if result.status is status)


# ---------------------------------------------------------------- trạng thái


def gpo_managed(action: Action, env: Env) -> bool:
    for ref in action.gpo:
        try:
            if registry.read_value(env.resolve(ref.key), ref.name).exists:
                return True
        except OSError:
            continue
    return False


def blocked_reason(action: Action, env: Env) -> str | None:
    """Lý do mục này không chạy được trên máy này, hoặc None nếu chạy được."""
    if not action.supports_build(env.build):
        return f"Không dùng cho bản Windows này (build {env.build})"
    if action.requires_domain and not env.joined_domain:
        return "Máy chưa vào domain"
    if action.admin and not env.is_admin:
        return "Cần mở tool bằng quyền admin"
    if gpo_managed(action, env):
        return "Thiết lập này đang do GPO quản lý, tool không ghi đè"
    return None


def check_state(action: Action, env: Env) -> bool | None:
    """True = đang bật, False = đang tắt, None = mục không có phần kiểm tra hoặc không đọc được."""
    if action.check is None:
        return None
    try:
        value = registry.read_value(env.resolve(action.check.key), action.check.name)
    except OSError:
        return None
    return value.exists and value.value == action.check.on_value


# ---------------------------------------------------------------- mô tả lệnh


def _service_script(step: ServiceStep) -> str:
    name = shell.ps_quote(step.service)
    if step.action == "start":
        return f"Start-Service -Name {name}"
    if step.action == "stop":
        return f"Stop-Service -Name {name} -Force"
    return f"Restart-Service -Name {name} -Force"


def ps_variables(env: Env) -> dict[str, str]:
    """Biến dựng sẵn cho mọi script PowerShell của mục (xem docs/ACTIONS.md)."""
    return {
        "TargetUserName": env.target_user.name,
        "TargetUserSid": env.target_user.sid,
        "TargetUserProfile": env.target_user.profile_path or "",
        "ReportDir": str(paths.reports_dir()),
        "LogDir": str(paths.logs_dir()),
        "ShareRoot": env.share_root,
    }


def _used_variables(script: str, env: Env) -> dict[str, str]:
    lowered = script.lower()
    return {name: value for name, value in ps_variables(env).items() if f"${name.lower()}" in lowered}


def ps_script_for(step: PowerShellStep) -> str:
    """Script thật sẽ chạy: thêm hàm dựng sẵn nếu script có dùng."""
    return pslib.with_helpers(step.script)


def describe_step(step: Step, env: Env, full: bool = False) -> str:
    """Lệnh của một bước để IT đọc. `full`: kèm cả hàm kiểm tra dựng sẵn, để copy ra chạy tay vẫn đúng."""
    if isinstance(step, CmdStep):
        return step.command
    if isinstance(step, PowerShellStep):
        script = shell.ps_variable_lines(_used_variables(step.script, env))
        if full:
            script += ps_script_for(step)
        else:
            script += step.script
            if ps_script_for(step) != step.script:
                script += "\n# (dùng hàm kiểm tra dựng sẵn Write-Ok, Test-Port...: nút Copy lệnh copy kèm cả các hàm này)"
        body = "\n".join(f"    {line}" for line in script.splitlines())
        return f"PowerShell:\n{body}"
    if isinstance(step, RegistryStep):
        return registry.reg_exe_command(env.resolve(step.key), step.name, step.type, step.value, step.delete)
    if isinstance(step, ServiceStep):
        return f"PowerShell: {_service_script(step)}"
    return f"[{BUILTIN_NAMES[step.name]}]"


def describe_action(action: Action, env: Env, full: bool = False) -> str:
    lines = [describe_step(step, env, full) for step in action.apply]
    lines += [f"Sau khi xong: {BUILTIN_NAMES[hook]}" for hook in action.after]
    return "\n".join(lines)


def preview(actions: list[Action], env: Env) -> list[str]:
    """Danh sách lệnh sẽ chạy, không thực thi gì (nút "Xem trước")."""
    lines = [f"Xem trước {len(actions)} mục (chưa chạy gì):"]
    for action in actions:
        reason = blocked_reason(action, env)
        lines.append(f"▶ {action.name}" + (f"   (sẽ bỏ qua: {reason})" if reason else ""))
        lines += [f"    {line}" for line in describe_action(action, env).splitlines()]
    return lines


# ---------------------------------------------------------------- chạy


def _echo(ctx: RunContext) -> shell.LineCallback:
    def on_line(text: str, progress: bool) -> None:
        if text.strip():
            ctx.say(Level.OUTPUT, text.rstrip(), progress)
    return on_line


def _shell_outcome(result: shell.ShellResult, step: Step, timeout: float) -> StepOutcome:
    if result.cancelled:
        return StepOutcome(Status.CANCELLED, "Đã huỷ")
    if result.timed_out:
        return StepOutcome(Status.FAILED, f"Quá thời gian chờ ({int(timeout)} giây)")
    if result.code in step.reboot_codes:
        return StepOutcome(Status.OK, changed=True, reboot=True)
    if result.code in step.ok_codes:
        return StepOutcome(Status.OK, changed=True)
    code = result.code if result.code is not None else -1
    explained = step.message_for(code)
    if explained:
        return StepOutcome(Status.FAILED, f"{explained} (mã {code})")
    return StepOutcome(Status.FAILED, f"Lệnh trả mã lỗi {code} (0x{code & 0xFFFFFFFF:08X})")


def _run_registry(step: RegistryStep, ctx: RunContext, changes: list[RegChange]) -> StepOutcome:
    path = ctx.env.resolve(step.key)
    target = f"{path}\\{step.name or '(Default)'}"
    before = registry.read_value(path, step.name)
    if step.delete:
        if not before.exists:
            ctx.say(Level.INFO, f"{target} vốn không có, bỏ qua.")
            return StepOutcome()
        ctx.say(Level.CMD, f"> Xoá {target}")
        registry.delete_value(path, step.name)
        after = registry.MISSING
    else:
        type_code = registry.TYPES[step.type]
        after = registry.RegValue(True, type_code, step.value)
        if before == after:
            ctx.say(Level.INFO, f"{target} đã đúng sẵn ({after.display()}), không cần đổi.")
            return StepOutcome()
        ctx.say(Level.CMD, f"> Đặt {target} = {after.display()} ({step.type}), trước đó: {before.display()}")
        registry.write_value(path, step.name, type_code, step.value)
    changes.append(RegChange(key=str(path), name=step.name, before=before, after=after))
    return StepOutcome(changed=True)


def _run_step(step: Step, ctx: RunContext, changes: list[RegChange], action: Action) -> StepOutcome:
    if isinstance(step, RegistryStep):
        return _run_registry(step, ctx, changes)
    if isinstance(step, BuiltinStep):
        return run_builtin(step.name, ctx)
    timeout = step.timeout or DEFAULT_STEP_TIMEOUT
    options = {"timeout": timeout, "cancel": ctx.cancel, "on_line": _echo(ctx)}
    if isinstance(step, CmdStep):
        ctx.say(Level.CMD, f"> {step.command}")
        result = shell.run_cmd(step.command, encoding=step.encoding, **options)
    elif isinstance(step, PowerShellStep):
        first_line = step.script.strip().splitlines()[0]
        more = " …" if len(step.script.strip().splitlines()) > 1 else ""
        ctx.say(Level.CMD, f"> PowerShell: {first_line}{more}")
        credential = ctx.credential if action.needs_credential else None
        result = shell.run_powershell(
            ps_script_for(step), encoding=step.encoding, credential=credential, variables=ps_variables(ctx.env),
            **options,
        )
    else:
        script = _service_script(step)
        ctx.say(Level.CMD, f"> {script}")
        result = shell.run_powershell(script, **options)
    return _shell_outcome(result, step, timeout)


def _friendly_error(exc: Exception) -> str:
    if isinstance(exc, PermissionError):
        return "Không đủ quyền (cần mở tool bằng quyền admin)"
    return str(exc) or exc.__class__.__name__


def run_action(action: Action, ctx: RunContext) -> ActionResult:
    started = time.monotonic()
    ctx.say(Level.HEADER, f"▶ {action.name}")
    result = ActionResult(action, Status.OK)
    changes: list[RegChange] = []
    try:
        for step in action.apply:
            if ctx.cancel.is_set():
                result.status, result.message = Status.CANCELLED, "Đã huỷ"
                break
            outcome = _run_step(step, ctx, changes, action)
            result.changed |= outcome.changed
            result.reboot_required |= outcome.reboot
            if outcome.status is not Status.OK:
                result.status, result.message = outcome.status, outcome.message
                break
    except Exception as exc:  # lỗi bất ngờ của một mục không được làm hỏng cả lượt chạy
        log.exception("Lỗi khi chạy %s", action.id)
        result.status, result.message = Status.FAILED, _friendly_error(exc)

    # Kể cả khi lỗi giữa chừng, những gì đã đổi vẫn được ghi để hoàn tác được.
    if changes:
        entry = JournalEntry.new(
            action.id, action.name, ctx.env.process_user.name, ctx.env.target_user.name, changes, list(action.after)
        )
        ctx.journal.add(entry)
        result.journal_id = entry.id
    if action.reboot and result.status is Status.OK and result.changed:
        result.reboot_required = True
    result.seconds = time.monotonic() - started
    result.finished_at = datetime.now()

    if result.status is Status.OK:
        note = "" if result.changed else " (không có gì phải đổi)"
        ctx.say(Level.OK, f"✔ {action.name}: xong sau {result.seconds:.1f}s{note}")
    elif result.status is Status.CANCELLED:
        ctx.say(Level.WARN, f"■ {action.name}: đã huỷ")
    else:
        ctx.say(Level.ERROR, f"✖ {action.name}: {result.message}")
    return result


def _make_restore_point(ctx: RunContext) -> None:
    if not ctx.env.is_admin:
        ctx.say(Level.WARN, "Không tạo được restore point vì tool không chạy bằng quyền admin.")
        return
    ctx.say(Level.INFO, "Đang tạo restore point (có thể mất 1–2 phút)…")
    try:
        point = ctx.restore_point(f"FVPL IT Toolkit {datetime.now():%d/%m/%Y %H:%M}", cancel=ctx.cancel)
    except Exception as exc:
        log.exception("Lỗi khi tạo restore point")
        ctx.say(Level.WARN, f"Không tạo được restore point: {exc}")
        return
    ctx.say(Level.OK if point.created else Level.WARN, point.message)


def run_batch(actions: list[Action], ctx: RunContext, stop_on_error: bool = False) -> BatchResult:
    """Chạy lần lượt các mục. `stop_on_error` (dùng cho gói sửa nhanh): một mục lỗi thì bỏ các mục sau."""
    password = ctx.credential[1] if ctx.credential else None
    register_secret(password)
    try:
        return _run_batch(actions, ctx, stop_on_error)
    finally:
        forget_secret(password)


def _run_batch(actions: list[Action], ctx: RunContext, stop_on_error: bool) -> BatchResult:
    batch = BatchResult()
    runnable: list[Action] = []
    for action in actions:
        reason = blocked_reason(action, ctx.env)
        if reason is None and action.needs_credential and ctx.credential is None:
            reason = "Chưa nhập tài khoản domain"
        if reason:
            batch.results.append(ActionResult(action, Status.SKIPPED, reason))
            ctx.say(Level.WARN, f"Bỏ qua “{action.name}”: {reason}")
        else:
            runnable.append(action)

    if runnable and ctx.create_restore_point and any(action.risk is not Risk.SAFE for action in runnable):
        _make_restore_point(ctx)

    hooks: list[str] = []
    for index, action in enumerate(runnable):
        if ctx.cancel.is_set():
            batch.cancelled = True
            batch.results += [ActionResult(rest, Status.CANCELLED, "Đã huỷ trước khi chạy") for rest in runnable[index:]]
            break
        result = run_action(action, ctx)
        batch.results.append(result)
        if result.status is Status.CANCELLED:
            batch.cancelled = True
        if result.changed:
            hooks += [hook for hook in action.after if hook not in hooks]
        if stop_on_error and result.status is Status.FAILED and index + 1 < len(runnable):
            reason = f"Dừng vì “{action.name}” lỗi"
            ctx.say(Level.WARN, f"{reason}, bỏ qua {len(runnable) - index - 1} mục còn lại.")
            batch.results += [ActionResult(rest, Status.SKIPPED, reason) for rest in runnable[index + 1:]]
            break

    # Việc làm sau (ví dụ khởi động lại Explorer) chỉ chạy một lần cho cả lượt.
    for hook in hooks:
        outcome = run_builtin(hook, ctx)
        if outcome.status is Status.FAILED:
            ctx.say(Level.WARN, outcome.message)

    _summary(batch, ctx)
    return batch


def _summary(batch: BatchResult, ctx: RunContext) -> None:
    parts = [f"{batch.count(Status.OK)} xong"]
    for status in (Status.FAILED, Status.SKIPPED, Status.CANCELLED):
        if batch.count(status):
            parts.append(f"{batch.count(status)} {status.label.lower()}")
    level = Level.OK if not batch.count(Status.FAILED) and not batch.cancelled else Level.WARN
    ctx.say(level, "Kết thúc: " + ", ".join(parts) + ".")
    if batch.reboot_required:
        ctx.say(Level.WARN, "Cần khởi động lại máy để hoàn tất.")


# ---------------------------------------------------------------- hoàn tác


def undo_entry(entry_id: str, ctx: RunContext) -> bool:
    """Trả các giá trị registry của một lần chạy về như trước khi tool đổi."""
    entry = ctx.journal.get(entry_id)
    if entry is None:
        ctx.say(Level.ERROR, "Không tìm thấy lần chạy này trong nhật ký hoàn tác.")
        return False
    if entry.undone:
        ctx.say(Level.WARN, f"“{entry.action_name}” đã được hoàn tác lúc {entry.undone_label}.")
        return False
    ctx.say(Level.HEADER, f"↶ Hoàn tác: {entry.action_name} (chạy lúc {entry.time_label})")
    try:
        for change in reversed(entry.changes):
            path = registry.parse_key(change.key)
            target = f"{path}\\{change.name or '(Default)'}"
            if registry.read_value(path, change.name) != change.after:
                ctx.say(Level.WARN, f"{target} đã bị đổi sau lần chạy đó, vẫn trả về giá trị cũ.")
            if change.before.exists:
                registry.write_value(path, change.name, change.before.type, change.before.value)
                ctx.say(Level.CMD, f"> Trả {target} về {change.before.display()}")
            else:
                registry.delete_value(path, change.name)
                ctx.say(Level.CMD, f"> Xoá {target} (trước đó chưa có)")
    except Exception as exc:
        log.exception("Lỗi khi hoàn tác %s", entry.id)
        ctx.say(Level.ERROR, f"✖ Hoàn tác lỗi: {_friendly_error(exc)}")
        return False
    ctx.journal.mark_undone(entry.id)
    for hook in entry.after:
        if hook in BUILTINS:
            run_builtin(hook, ctx)
    ctx.say(Level.OK, f"✔ Đã hoàn tác “{entry.action_name}”.")
    return True


def run_undo_steps(action: Action, ctx: RunContext) -> ActionResult:
    """Chạy các bước hoàn tác khai báo riêng (undo: [ ... ]) của một mục."""
    undo_action = Action(
        id=action.id, name=f"Hoàn tác: {action.name}", category=action.category,
        apply=action.undo_steps, scope=action.scope, admin=action.admin, after=action.after,
    )
    return run_action(undo_action, ctx)


# ---------------------------------------------------------------- thao tác viết bằng Python

# Khung chung: tắt Explorer trong phiên của tool, làm việc cần làm khi Explorer đang tắt, chờ Windows tự mở lại.
_EXPLORER_TEMPLATE = """\
__BEFORE__
$session = (Get-Process -Id $PID).SessionId
Get-Process explorer -ErrorAction SilentlyContinue | Where-Object SessionId -eq $session | Stop-Process -Force
__WHILE_STOPPED__
for ($i = 0; $i -lt 16; $i++) {
    Start-Sleep -Milliseconds 500
    if (Get-Process explorer -ErrorAction SilentlyContinue | Where-Object SessionId -eq $session) {
        Write-Output 'Explorer đã tự mở lại.'
        exit 0
    }
}
exit 2
"""

# Mở Explorer bằng tài khoản người dùng (không phải quyền admin của tool) qua một tác vụ chạy một lần.
_START_EXPLORER_AS_USER = """\
$session = (Get-Process -Id $PID).SessionId
$name = 'FVPL-ITTools-StartExplorer-' + [guid]::NewGuid().ToString('N').Substring(0, 8)
$taskAction = New-ScheduledTaskAction -Execute (Join-Path $env:SystemRoot 'explorer.exe')
$principal = New-ScheduledTaskPrincipal -UserId $TargetUserName -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $name -Action $taskAction -Principal $principal -Force | Out-Null
$started = $false
try {
    Start-ScheduledTask -TaskName $name
    for ($i = 0; $i -lt 20 -and -not $started; $i++) {
        Start-Sleep -Milliseconds 500
        $started = [bool](Get-Process explorer -ErrorAction SilentlyContinue | Where-Object SessionId -eq $session)
    }
}
finally {
    Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction SilentlyContinue
}
if (-not $started) { exit 2 }
Write-Output 'Đã mở lại Explorer bằng tài khoản người dùng.'
"""

_ICON_CACHE_BEFORE = """\
if (-not $TargetUserProfile -or -not (Test-Path -LiteralPath $TargetUserProfile)) {
    Write-Output 'Không tìm thấy thư mục profile của người dùng.'
    exit 3
}
$local = Join-Path $TargetUserProfile 'AppData\\Local'
$cache = @(Join-Path $local 'IconCache.db')
$explorerDir = Join-Path $local 'Microsoft\\Windows\\Explorer'
if (Test-Path -LiteralPath $explorerDir) {
    $cache += @(Get-ChildItem -LiteralPath $explorerDir -Force -File |
        Where-Object { $_.Name -like 'iconcache*.db' -or $_.Name -like 'thumbcache*.db' } |
        ForEach-Object { $_.FullName })
}
"""

# Xoá ngay sau khi tắt Explorer, trước khi Windows kịp mở lại và khoá file. Thử lại tối đa 5 giây.
_ICON_CACHE_WHILE_STOPPED = """\
$deadline = (Get-Date).AddSeconds(5)
$deleted = 0
$locked = 0
foreach ($file in $cache) {
    if (-not (Test-Path -LiteralPath $file)) { continue }
    $done = $false
    while (-not $done) {
        try { Remove-Item -LiteralPath $file -Force -ErrorAction Stop; $done = $true }
        catch { if ((Get-Date) -gt $deadline) { break }; Start-Sleep -Milliseconds 100 }
    }
    if ($done) { $deleted++ } else { $locked++ }
}
Write-Output "Đã xoá $deleted file cache."
if ($locked) { Write-Output "$locked file đang bị chương trình khác giữ, sẽ được làm mới sau khi khởi động lại máy." }
"""


def explorer_script(before: str = "", while_stopped: str = "") -> str:
    return _EXPLORER_TEMPLATE.replace("__BEFORE__", before).replace("__WHILE_STOPPED__", while_stopped)


def _cycle_explorer(ctx: RunContext, name: str, script: str) -> StepOutcome:
    ctx.say(Level.CMD, f"> {BUILTIN_NAMES[name]}")
    options = {"cancel": ctx.cancel, "on_line": _echo(ctx), "variables": ps_variables(ctx.env)}
    result = shell.run_powershell(script, timeout=60, **options)
    if result.code == 3:
        return StepOutcome(Status.FAILED, "Không tìm thấy thư mục profile của người dùng")
    if result.code != 2:
        return _shell_outcome(result, BuiltinStep(name=name), 60)

    # Windows không tự mở lại Explorer. Không mở thẳng từ tool khi tool có quyền admin hoặc chạy bằng
    # tài khoản khác: Explorer sẽ chạy bằng quyền đó, mọi thứ mở từ desktop cũng thành admin.
    if not ctx.env.is_admin and ctx.env.user_hive_sid is None:
        subprocess.Popen(["explorer.exe"], creationflags=shell.CREATE_NO_WINDOW)
        ctx.say(Level.INFO, "Đã mở lại Explorer.")
        return StepOutcome(changed=True)
    if ctx.env.is_admin:
        result = shell.run_powershell(_START_EXPLORER_AS_USER, timeout=60, **options)
        if result.ok:
            return StepOutcome(changed=True)
    return StepOutcome(
        Status.FAILED,
        "Explorer chưa tự mở lại. Nhấn Ctrl+Shift+Esc → Run new task → gõ explorer → OK.",
    )


def _restart_explorer(ctx: RunContext) -> StepOutcome:
    return _cycle_explorer(ctx, "restart_explorer", explorer_script())


def _rebuild_icon_cache(ctx: RunContext) -> StepOutcome:
    return _cycle_explorer(ctx, "rebuild_icon_cache", explorer_script(_ICON_CACHE_BEFORE, _ICON_CACHE_WHILE_STOPPED))


BUILTINS: dict[str, Callable[[RunContext], StepOutcome]] = {
    "restart_explorer": _restart_explorer,
    "rebuild_icon_cache": _rebuild_icon_cache,
}


def run_builtin(name: str, ctx: RunContext) -> StepOutcome:
    return BUILTINS[name](ctx)
