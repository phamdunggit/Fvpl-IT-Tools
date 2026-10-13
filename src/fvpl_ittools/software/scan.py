"""Một lượt quét cho trang Phần mềm: nạp danh mục, xem share và winget có không, phần mềm nào đã cài.

Có thể chậm vài chục giây nếu share không trả lời, nên trang Phần mềm gọi ở thread nền.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from ..app import AppContext
from . import catalog as catalog_module
from .catalog import Catalog, expand
from .detect import Detection, InstalledEntry, detect, installed_programs, winget_path
from .install import SoftwareEnv


@dataclass
class SoftwareState:
    catalog: Catalog
    senv: SoftwareEnv
    entries: list[InstalledEntry] = field(default_factory=list)
    detections: dict[str, Detection] = field(default_factory=dict)


def scan(app: AppContext) -> SoftwareState:
    share_root = app.site.share_root
    share_ok = bool(share_root) and os.path.isdir(share_root)
    catalog = catalog_module.load_catalog(share_root if share_ok else "")
    missing = frozenset(
        item.id for item in catalog.apps
        if item.source == "share" and share_ok and not os.path.exists(expand(item.installer, share_root))
    )
    senv = SoftwareEnv(
        is_admin=app.env.is_admin,
        runs_as_other_user=app.runs_as_other_user,
        winget=winget_path(),
        share_root=share_root,
        share_ok=share_ok,
        missing=missing,
    )
    entries = installed_programs(app.env.target_user.sid)
    detections = {item.id: detect(item, entries, share_root) for item in catalog.apps}
    return SoftwareState(catalog=catalog, senv=senv, entries=entries, detections=detections)
