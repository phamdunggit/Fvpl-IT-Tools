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
from . import registry, safety, shell
from .journal import JournalEntry, RegChange, UndoJournal
from .log import mask
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


def describe_step(step: Step, env: Env) -> str:
    if isinstance(step, CmdStep):
        return step.command
    if isinstance(step, PowerShellStep):
        body = "\n".join(f"    {line}" for line in step.script.splitlines())
        return f"PowerShell:\n{body}"
    if isinstance(step, RegistryStep):
        return registry.reg_exe_command(env.resolve(step.key), step.name, step.type, step.value, step.delete)
    if isinstance(step, ServiceStep):
        return f"PowerShell: {_service_script(step)}"
    return f"[{BUILTIN_NAMES[step.name]}]"


def describe_action(action: Action, env: Env) -> str:
    lines = [describe_step(step, env) for step in action.apply]
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


def _run_step(step: Step, ctx: RunContext, changes: list[RegChange]) -> StepOutcome:
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
        result = shell.run_powershell(step.script, encoding=step.encoding, **options)
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
            outcome = _run_step(step, ctx, changes)
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


def run_batch(actions: list[Action], ctx: RunContext) -> BatchResult:
    batch = BatchResult()
    runnable: list[Action] = []
    for action in actions:
        reason = blocked_reason(action, ctx.env)
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

_RESTART_EXPLORER = """\
$session = (Get-Process -Id $PID).SessionId
Get-Process explorer -ErrorAction SilentlyContinue | Where-Object SessionId -eq $session | Stop-Process -Force
for ($i = 0; $i -lt 16; $i++) {
    Start-Sleep -Milliseconds 500
    if (Get-Process explorer -ErrorAction SilentlyContinue | Where-Object SessionId -eq $session) {
        Write-Output 'Explorer đã tự mở lại.'
        exit 0
    }
}
exit 2
"""


def _restart_explorer(ctx: RunContext) -> StepOutcome:
    ctx.say(Level.CMD, "> Khởi động lại Explorer")
    result = shell.run_powershell(_RESTART_EXPLORER, timeout=60, cancel=ctx.cancel, on_line=_echo(ctx))
    if result.code == 2:
        # Windows không tự mở lại. Chỉ tự mở khi tool không chạy bằng quyền admin, vì Explorer mở
        # từ tiến trình admin sẽ chạy luôn bằng quyền admin, mọi thứ mở từ desktop cũng thành admin.
        if not ctx.env.is_admin and ctx.env.user_hive_sid is None:
            subprocess.Popen(["explorer.exe"], creationflags=shell.CREATE_NO_WINDOW)
            ctx.say(Level.INFO, "Đã mở lại Explorer.")
            return StepOutcome(changed=True)
        return StepOutcome(
            Status.FAILED,
            "Explorer chưa tự mở lại. Nhấn Ctrl+Shift+Esc → Run new task → gõ explorer → OK.",
        )
    return _shell_outcome(result, BuiltinStep(name="restart_explorer"), 60)


BUILTINS: dict[str, Callable[[RunContext], StepOutcome]] = {
    "restart_explorer": _restart_explorer,
}


def run_builtin(name: str, ctx: RunContext) -> StepOutcome:
    return BUILTINS[name](ctx)
