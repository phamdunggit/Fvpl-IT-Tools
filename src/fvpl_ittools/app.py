"""Gom thông tin dùng chung cho cả app: máy, người dùng, danh sách mục, nhật ký hoàn tác, site.yaml."""

from __future__ import annotations

import ctypes
import logging
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .actions import loader
from .actions.model import Action, Pack
from .core import config, paths, session, sysinfo, winapi
from .core.executor import Env
from .core.journal import UndoJournal

log = logging.getLogger(__name__)


@dataclass
class AppContext:
    machine: sysinfo.MachineInfo
    env: Env
    actions: list[Action]
    packs: list[Pack]
    load_errors: list[str]
    journal: UndoJournal
    site: config.SiteConfig
    log_file: Path | None

    @property
    def runs_as_other_user(self) -> bool:
        """True khi IT mở tool bằng tài khoản khác người đang đăng nhập."""
        return self.env.user_hive_sid is not None


def build_context(log_file: Path | None = None) -> AppContext:
    machine = sysinfo.quick_machine_info()
    process_user = session.process_user()
    session_user = session.session_user()
    if session_user is None:
        log.warning("Không xác định được người đang đăng nhập, thiết lập người dùng sẽ áp cho %s", process_user.name)
        session_user = process_user
    env = Env(
        is_admin=winapi.is_admin(),
        build=machine.build,
        process_user=process_user,
        target_user=session_user,
        joined_domain=machine.joined_domain,
    )
    actions, errors = loader.load_builtin_actions()
    packs, pack_errors = loader.load_builtin_packs(actions)
    errors += pack_errors
    for error in errors:
        log.warning("Bỏ qua mục khai báo sai: %s", error)
    site = config.load_site_config()
    for error in site.errors:
        log.warning("%s", error)
    log.info(
        "Máy %s | %s | %s | admin=%s | chạy bằng %s | áp cho %s | %d mục",
        machine.computer_name, machine.domain_label, machine.os_label, env.is_admin,
        process_user.name, session_user.name, len(actions),
    )
    return AppContext(
        machine=machine,
        env=env,
        actions=actions,
        packs=packs,
        load_errors=errors,
        journal=UndoJournal(paths.undo_journal_path()),
        site=site,
        log_file=log_file,
    )


def relaunch_as_admin(args: list[str]) -> bool:
    """Mở lại tool qua hộp thoại UAC. True nếu tiến trình mới đã được mở."""
    if paths.is_frozen():
        executable, params = sys.executable, args
    else:
        executable, params = sys.executable, ["-m", "fvpl_ittools", *args]
    result = ctypes.windll.shell32.ShellExecuteW(
        None, "runas", executable, subprocess.list2cmdline(params), os.getcwd(), 1
    )
    return result > 32
