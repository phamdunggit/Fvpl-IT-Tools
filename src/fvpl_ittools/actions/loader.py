"""Nạp các file YAML định nghĩa fix/tweak và kiểm tra lỗi khai báo.

Mục khai báo sai sẽ bị loại và báo lỗi bằng tiếng Việt kèm tên file + số thứ tự,
các mục còn lại vẫn dùng được bình thường.
"""

from __future__ import annotations

import codecs
import re
from pathlib import Path
from typing import Any, Iterable

import yaml

from ..core import paths, registry
from .model import (
    BUILTIN_NAMES,
    DEFAULT_OK_CODES,
    DEFAULT_REBOOT_CODES,
    PAGES,
    SERVICE_ACTIONS,
    Action,
    BuiltinStep,
    CmdStep,
    GpoRef,
    Pack,
    PowerShellStep,
    RegistryCheck,
    RegistryStep,
    Risk,
    Scope,
    ServiceStep,
    Step,
    UndoMode,
)

ACTIONS_DIR = paths.DATA_DIR / "actions"
PACKS_FILE = paths.DATA_DIR / "packs.yaml"

_ID_PATTERN = re.compile(r"^[a-z0-9_]+(\.[a-z0-9_]+)+$")
_ACTION_KEYS = {
    "id", "name", "category", "page", "risk", "scope", "admin", "reboot", "os",
    "description", "check", "apply", "undo", "after", "gpo", "needs_credential", "requires_domain",
}
_STEP_KINDS = ("cmd", "powershell", "registry", "service", "builtin")
_STEP_COMMON = {"timeout", "ok_codes", "reboot_codes", "messages"}
_SHELL_KEYS = {"encoding"}
_CREDENTIAL_KINDS = ("domain",)


class ActionError(ValueError):
    pass


def load_builtin_actions() -> tuple[list[Action], list[str]]:
    return load_action_files(sorted(ACTIONS_DIR.glob("*.yaml")))


def load_action_files(files: Iterable[Path]) -> tuple[list[Action], list[str]]:
    actions: list[Action] = []
    errors: list[str] = []
    seen: dict[str, str] = {}
    for file in files:
        try:
            data = yaml.safe_load(file.read_text(encoding="utf-8")) or []
        except (OSError, yaml.YAMLError) as exc:
            errors.append(f"{file.name}: không đọc được file ({exc})")
            continue
        if not isinstance(data, list):
            errors.append(f"{file.name}: file phải là danh sách các mục, mỗi mục bắt đầu bằng '- id: …'")
            continue
        for index, raw in enumerate(data, start=1):
            label = f"{file.name} mục {index}"
            if isinstance(raw, dict) and isinstance(raw.get("id"), str):
                label += f" ({raw['id']})"
            try:
                action = parse_action(raw, source=file.name)
            except ActionError as exc:
                errors.append(f"{label}: {exc}")
                continue
            if action.id in seen:
                errors.append(f"{label}: trùng id với {seen[action.id]}")
                continue
            seen[action.id] = label
            actions.append(action)
    return actions, errors


def parse_action(raw: Any, source: str = "") -> Action:
    if not isinstance(raw, dict):
        raise ActionError("mỗi mục phải là một khối 'khoá: giá trị'")
    unknown = sorted(set(raw) - _ACTION_KEYS)
    if unknown:
        raise ActionError(f"không hiểu khoá {', '.join(unknown)}")

    action_id = _required_text(raw, "id")
    if not _ID_PATTERN.match(action_id):
        raise ActionError("id phải có dạng nhom.ten, chỉ gồm chữ thường không dấu, số và '_' (ví dụ net.flush_dns)")
    name = _required_text(raw, "name")
    category = _required_text(raw, "category")
    page = _choice(raw, "page", PAGES, "fixes")
    risk = Risk(_choice(raw, "risk", [item.value for item in Risk], Risk.SAFE.value))
    scope = Scope(_choice(raw, "scope", [item.value for item in Scope], Scope.MACHINE.value))
    admin = _flag(raw, "admin", True)
    reboot = _flag(raw, "reboot", False)
    requires_domain = _flag(raw, "requires_domain", False)
    min_build, max_build = _parse_os(raw.get("os"))
    description = _optional_text(raw, "description")

    apply_raw = raw.get("apply")
    if not isinstance(apply_raw, list) or not apply_raw:
        raise ActionError("thiếu 'apply' (danh sách các bước sẽ chạy)")
    steps = tuple(_parse_step(item, f"apply bước {i}") for i, item in enumerate(apply_raw, start=1))
    has_registry = any(isinstance(step, RegistryStep) for step in steps)

    if "undo" in raw:
        undo_mode, undo_steps = _parse_undo(raw["undo"], has_registry)
    elif risk is not Risk.SAFE:
        raise ActionError("mục Cẩn thận/Nâng cao phải khai báo 'undo': auto, none (không hoàn tác được) hoặc các bước hoàn tác")
    else:
        undo_mode, undo_steps = (UndoMode.AUTO if has_registry else UndoMode.NONE), ()

    check = _parse_check(raw.get("check"))
    after = _parse_after(raw.get("after"))
    gpo = _parse_gpo(raw.get("gpo"))
    needs_credential = raw.get("needs_credential")
    if needs_credential is not None and needs_credential not in _CREDENTIAL_KINDS:
        raise ActionError(f"needs_credential chỉ nhận {', '.join(_CREDENTIAL_KINDS)}")

    registry_keys = [step.key for step in steps + undo_steps if isinstance(step, RegistryStep)]
    if check is not None:
        registry_keys.append(check.key)
    _check_scope(scope, registry_keys)

    return Action(
        id=action_id,
        name=name,
        category=category,
        apply=steps,
        page=page,
        risk=risk,
        scope=scope,
        admin=admin,
        reboot=reboot,
        min_build=min_build,
        max_build=max_build,
        description=description,
        undo_mode=undo_mode,
        undo_steps=undo_steps,
        check=check,
        after=after,
        gpo=gpo,
        needs_credential=needs_credential,
        requires_domain=requires_domain,
        source=source,
    )


def _required_text(raw: dict, key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ActionError(f"thiếu '{key}' hoặc '{key}' không phải chữ")
    return value.strip()


def _optional_text(raw: dict, key: str) -> str:
    value = raw.get(key, "")
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ActionError(f"'{key}' phải là chữ")
    return value.strip()


def _choice(raw: dict, key: str, choices, default: str) -> str:
    value = raw.get(key, default)
    if value not in choices:
        raise ActionError(f"'{key}' chỉ nhận {', '.join(choices)} (gặp {value!r})")
    return value


def _flag(raw: dict, key: str, default: bool) -> bool:
    value = raw.get(key, default)
    if not isinstance(value, bool):
        raise ActionError(f"'{key}' phải là true hoặc false")
    return value


def _parse_os(raw: Any) -> tuple[int | None, int | None]:
    if raw is None:
        return None, None
    if not isinstance(raw, dict) or set(raw) - {"min_build", "max_build"}:
        raise ActionError("'os' chỉ nhận min_build và max_build, ví dụ os: { min_build: 19045 }")
    builds = []
    for key in ("min_build", "max_build"):
        value = raw.get(key)
        if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value <= 0):
            raise ActionError(f"os.{key} phải là số build Windows, ví dụ 19045 (Win10 22H2) hoặc 22000 (Win11)")
        builds.append(value)
    return builds[0], builds[1]


def _codes(raw: Any, default: tuple[int, ...], where: str, key: str) -> tuple[int, ...]:
    if raw is None:
        return default
    if not isinstance(raw, list) or not all(isinstance(code, int) and not isinstance(code, bool) for code in raw):
        raise ActionError(f"{where}: '{key}' phải là danh sách mã số, ví dụ [0, 3010]")
    return tuple(raw)


def _messages(raw: Any, where: str) -> tuple[tuple[int, str], ...]:
    if raw is None:
        return ()
    if not isinstance(raw, dict) or not all(
        isinstance(code, int) and not isinstance(code, bool) and isinstance(text, str) and text.strip()
        for code, text in raw.items()
    ):
        raise ActionError(f"{where}: 'messages' phải có dạng {{ mã: \"giải thích\" }}, ví dụ {{ 3: \"Ổ đĩa có lỗi\" }}")
    return tuple((code, text.strip()) for code, text in raw.items())


def _parse_step(raw: Any, where: str) -> Step:
    if not isinstance(raw, dict):
        raise ActionError(f"{where}: mỗi bước phải là một khối 'khoá: giá trị'")
    kinds = [key for key in _STEP_KINDS if key in raw]
    if len(kinds) != 1:
        raise ActionError(f"{where}: cần đúng một trong các loại bước {', '.join(_STEP_KINDS)}")
    kind = kinds[0]
    allowed = {kind} | _STEP_COMMON | (_SHELL_KEYS if kind in ("cmd", "powershell") else set())
    extra = sorted(set(raw) - allowed)
    if extra:
        raise ActionError(f"{where}: không hiểu khoá {', '.join(extra)}")

    timeout = raw.get("timeout")
    if timeout is not None and (not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or timeout <= 0):
        raise ActionError(f"{where}: 'timeout' phải là số giây lớn hơn 0")
    common = {
        "timeout": float(timeout) if timeout is not None else None,
        "ok_codes": _codes(raw.get("ok_codes"), DEFAULT_OK_CODES, where, "ok_codes"),
        "reboot_codes": _codes(raw.get("reboot_codes"), DEFAULT_REBOOT_CODES, where, "reboot_codes"),
        "messages": _messages(raw.get("messages"), where),
    }
    body = raw[kind]

    if kind in ("cmd", "powershell"):
        if not isinstance(body, str) or not body.strip():
            raise ActionError(f"{where}: '{kind}' cần nội dung lệnh")
        encoding = raw.get("encoding", "auto")
        if encoding != "auto":
            try:
                codecs.lookup(encoding)
            except (LookupError, TypeError) as exc:
                raise ActionError(f"{where}: encoding {encoding!r} không hợp lệ") from exc
        if kind == "cmd":
            return CmdStep(command=body.strip(), encoding=encoding, **common)
        return PowerShellStep(script=body.strip("\n"), encoding=encoding, **common)

    if kind == "registry":
        return _parse_registry_step(body, where, common)

    if kind == "service":
        if not isinstance(body, dict):
            raise ActionError(f"{where}: 'service' cần name và action, ví dụ {{name: Spooler, action: restart}}")
        if "startup" in body:
            raise ActionError(f"{where}: chưa hỗ trợ đổi kiểu khởi động service (làm ở GĐ3)")
        extra = sorted(set(body) - {"name", "action"})
        if extra:
            raise ActionError(f"{where}: service không hiểu khoá {', '.join(extra)}")
        service_name = body.get("name")
        if not isinstance(service_name, str) or not re.fullmatch(r"[A-Za-z0-9_.\-]+", service_name):
            raise ActionError(f"{where}: tên service không hợp lệ")
        action = body.get("action")
        if action not in SERVICE_ACTIONS:
            raise ActionError(f"{where}: service.action chỉ nhận {', '.join(SERVICE_ACTIONS)}")
        return ServiceStep(service=service_name, action=action, **common)

    if body not in BUILTIN_NAMES:
        raise ActionError(f"{where}: builtin {body!r} không có (đang có: {', '.join(BUILTIN_NAMES)})")
    return BuiltinStep(name=body, **common)


def _parse_registry_step(body: Any, where: str, common: dict) -> RegistryStep:
    if not isinstance(body, dict):
        raise ActionError(f"{where}: 'registry' cần key, name, type, value (hoặc delete: true)")
    extra = sorted(set(body) - {"key", "name", "type", "value", "delete"})
    if extra:
        raise ActionError(f"{where}: registry không hiểu khoá {', '.join(extra)}")
    key = _registry_key(body.get("key"), where)
    name = body.get("name")
    if not isinstance(name, str):
        raise ActionError(f"{where}: registry cần 'name' (dùng \"\" cho giá trị mặc định)")
    delete = body.get("delete", False)
    if not isinstance(delete, bool):
        raise ActionError(f"{where}: 'delete' phải là true hoặc false")
    if delete:
        if "type" in body or "value" in body:
            raise ActionError(f"{where}: bước xoá (delete: true) không cần type/value")
        return RegistryStep(key=key, name=name, delete=True, **common)
    type_name = body.get("type")
    if not isinstance(type_name, str) or type_name.upper() not in registry.TYPES:
        raise ActionError(f"{where}: registry.type chỉ nhận {', '.join(registry.TYPES)}")
    if "value" not in body:
        raise ActionError(f"{where}: registry thiếu 'value'")
    try:
        value = registry.coerce(type_name, body["value"])
    except ValueError as exc:
        raise ActionError(f"{where}: {exc}") from exc
    return RegistryStep(key=key, name=name, type=type_name.upper(), value=value, **common)


def _registry_key(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ActionError(f"{where}: thiếu 'key' của registry")
    try:
        path = registry.parse_key(value)
    except ValueError as exc:
        raise ActionError(f"{where}: {exc}") from exc
    if path.hive == "HKU":
        raise ActionError(f"{where}: không ghi thẳng HKU, dùng HKCU kèm scope: user để tool tự chọn đúng người dùng")
    if not path.subkey:
        raise ActionError(f"{where}: key registry thiếu đường dẫn sau hive")
    return str(path)


def _parse_undo(raw: Any, has_registry: bool) -> tuple[UndoMode, tuple[Step, ...]]:
    if raw == UndoMode.AUTO.value:
        if not has_registry:
            raise ActionError("undo: auto chỉ dùng được khi có bước registry; lệnh cmd/PowerShell cần khai báo bước hoàn tác hoặc undo: none")
        return UndoMode.AUTO, ()
    if raw == UndoMode.NONE.value:
        return UndoMode.NONE, ()
    if isinstance(raw, list) and raw:
        return UndoMode.STEPS, tuple(_parse_step(item, f"undo bước {i}") for i, item in enumerate(raw, start=1))
    raise ActionError("'undo' chỉ nhận auto, none hoặc danh sách các bước hoàn tác")


def _parse_check(raw: Any) -> RegistryCheck | None:
    if raw is None:
        return None
    if not isinstance(raw, dict) or set(raw) != {"registry"} or not isinstance(raw["registry"], dict):
        raise ActionError("'check' hiện chỉ hỗ trợ dạng check: { registry: { key, name, on_value } }")
    body = raw["registry"]
    # Không dùng tên khoá "on": YAML hiểu on/off/yes/no là true/false.
    if set(body) != {"key", "name", "on_value"} or not isinstance(body["name"], str):
        raise ActionError("check.registry cần đủ key, name, on_value")
    return RegistryCheck(key=_registry_key(body["key"], "check"), name=body["name"], on_value=body["on_value"])


def _parse_after(raw: Any) -> tuple[str, ...]:
    if raw is None:
        return ()
    items = [raw] if isinstance(raw, str) else raw
    if not isinstance(items, list):
        raise ActionError("'after' phải là tên thao tác hoặc danh sách tên")
    for item in items:
        if item not in BUILTIN_NAMES:
            raise ActionError(f"after: {item!r} không có (đang có: {', '.join(BUILTIN_NAMES)})")
    return tuple(dict.fromkeys(items))


def _parse_gpo(raw: Any) -> tuple[GpoRef, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ActionError("'gpo' phải là danh sách { key, name }")
    refs = []
    for item in raw:
        if not isinstance(item, dict) or set(item) != {"key", "name"} or not isinstance(item["name"], str):
            raise ActionError("mỗi mục 'gpo' cần đúng key và name")
        refs.append(GpoRef(key=_registry_key(item["key"], "gpo"), name=item["name"]))
    return tuple(refs)


def _check_scope(scope: Scope, keys: list[str]) -> None:
    for key in keys:
        hive = registry.parse_key(key).hive
        if scope is Scope.USER and hive != "HKCU":
            raise ActionError(f"mục áp cho người dùng (scope: user) chỉ được ghi HKCU, gặp {key}")
        if scope is Scope.MACHINE and hive == "HKCU":
            raise ActionError(f"khoá {key} thuộc HKCU nên mục này phải khai báo scope: user")


# ---------------------------------------------------------------- gói sửa nhanh

_PACK_KEYS = {"id", "name", "description", "actions"}


def load_builtin_packs(actions: Iterable[Action]) -> tuple[list[Pack], list[str]]:
    return load_pack_file(PACKS_FILE, actions)


def load_pack_file(file: Path, actions: Iterable[Action]) -> tuple[list[Pack], list[str]]:
    """Nạp gói sửa nhanh. Gói nhắc tới mục không có (hoặc mục bị loại vì khai báo sai) thì bị bỏ."""
    known = {action.id for action in actions}
    if not file.exists():
        return [], []
    try:
        data = yaml.safe_load(file.read_text(encoding="utf-8")) or []
    except (OSError, yaml.YAMLError) as exc:
        return [], [f"{file.name}: không đọc được file ({exc})"]
    if not isinstance(data, list):
        return [], [f"{file.name}: file phải là danh sách các gói, mỗi gói bắt đầu bằng '- id: …'"]
    packs: list[Pack] = []
    errors: list[str] = []
    seen: set[str] = set()
    for index, raw in enumerate(data, start=1):
        label = f"{file.name} gói {index}"
        if isinstance(raw, dict) and isinstance(raw.get("id"), str):
            label += f" ({raw['id']})"
        try:
            pack = parse_pack(raw, known, source=file.name)
        except ActionError as exc:
            errors.append(f"{label}: {exc}")
            continue
        if pack.id in seen:
            errors.append(f"{label}: trùng id")
            continue
        seen.add(pack.id)
        packs.append(pack)
    return packs, errors


def parse_pack(raw: Any, known: set[str], source: str = "") -> Pack:
    if not isinstance(raw, dict):
        raise ActionError("mỗi gói phải là một khối 'khoá: giá trị'")
    unknown = sorted(set(raw) - _PACK_KEYS)
    if unknown:
        raise ActionError(f"không hiểu khoá {', '.join(unknown)}")
    pack_id = _required_text(raw, "id")
    if not _ID_PATTERN.match(pack_id):
        raise ActionError("id phải có dạng nhom.ten, ví dụ pack.network")
    items = raw.get("actions")
    if not isinstance(items, list) or len(items) < 2 or not all(isinstance(item, str) for item in items):
        raise ActionError("'actions' phải là danh sách id của ít nhất 2 mục")
    if len(set(items)) != len(items):
        raise ActionError("'actions' có mục bị lặp")
    missing = [item for item in items if item not in known]
    if missing:
        raise ActionError(f"không có mục {', '.join(missing)} (sai id hoặc mục đó khai báo sai)")
    return Pack(
        id=pack_id,
        name=_required_text(raw, "name"),
        description=_optional_text(raw, "description"),
        actions=tuple(items),
        source=source,
    )
