# -*- coding: utf-8 -*-

from __future__ import annotations

import json
import os
import re
import secrets
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote, urlencode

from task_dashboard.helpers import looks_like_uuid as _looks_like_uuid
from task_dashboard.runtime.agent_display_name import apply_agent_display_fields


SHARE_SPACE_SCHEMA_VERSION = "share_space.v1"
SHARE_MODE_SCHEMA_VERSION = "share_mode.v4"
DEFAULT_PERMISSION = "read_send"
DEFAULT_NETWORK_SCOPE = "lan_only"
ALLOWED_PERMISSIONS = {"read", "read_send"}
ALLOWED_NETWORK_SCOPES = {"lan_only"}
SHARE_SPACE_ACTIONS = {"upsert", "patch", "enable", "disable", "revoke", "delete", "hard_delete"}
SHARE_MODE_PAGE_PATH = "/share/project-task-dashboard.html"
LEGACY_PROJECT_CHAT_PAGE_PATH = "/share/project-chat.html"
LEGACY_SHARE_SPACE_PAGE_PATH = "/share/project-share-space.html"


def _safe_text(value: Any, max_len: int = 4000) -> str:
    text = "" if value is None else str(value)
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if len(text) > max_len:
        text = text[:max_len]
    return text


def _safe_storage_id(value: Any) -> str:
    text = _safe_text(value, 240)
    text = re.sub(r"[^0-9A-Za-z_.-]+", "_", text)
    text = text.replace("..", "_").strip("._")
    return text or "default"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _coerce_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _normalize_string_list(value: Any, *, max_items: int = 80, max_len: int = 160) -> list[str]:
    raw_items: list[Any]
    if isinstance(value, list):
        raw_items = value
    elif isinstance(value, str):
        raw_items = [part.strip() for part in value.split(",")]
    elif value in (None, ""):
        raw_items = []
    else:
        raw_items = [value]

    out: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        text = _safe_text(item, max_len)
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
        if len(out) >= max_items:
            break
    return out


def _normalize_mention_targets(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, dict):
            continue
        channel_name = _safe_text(item.get("channel_name") or item.get("channelName"), 200).strip()
        session_id = _safe_text(item.get("session_id") or item.get("sessionId"), 80).strip()
        if not (channel_name and session_id and _looks_like_uuid(session_id)):
            continue
        row: dict[str, str] = {
            "channel_name": channel_name,
            "session_id": session_id,
        }
        cli_type = _safe_text(item.get("cli_type") or item.get("cliType"), 40).strip().lower()
        if cli_type:
            row["cli_type"] = cli_type
        display_name = _safe_text(item.get("display_name") or item.get("displayName"), 200).strip()
        if display_name:
            row["display_name"] = display_name
        project_id = _safe_text(item.get("project_id") or item.get("projectId"), 120).strip()
        if project_id:
            row["project_id"] = project_id
        dedupe_key = f"{channel_name}|{session_id}"
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        rows.append(row)
        if len(rows) >= 20:
            break
    return rows


def _parse_iso_datetime(value: Any) -> datetime | None:
    text = _safe_text(value, 80)
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def _first_non_empty(*values: Any, max_len: int = 4000) -> str:
    for value in values:
        text = _safe_text(value, max_len)
        if text:
            return text
    return ""


def share_space_store_dir(worktree_root: Any, environment_name: str) -> Path:
    root = Path(worktree_root).expanduser().resolve()
    env = _safe_storage_id(environment_name or "stable")
    return root / ".runtime" / env / "share_spaces"


def share_space_store_path(worktree_root: Any, environment_name: str, project_id: str) -> Path:
    return share_space_store_dir(worktree_root, environment_name) / f"{_safe_storage_id(project_id)}.json"


def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp-{secrets.token_hex(6)}")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _empty_share_space_config(project_id: str) -> dict[str, Any]:
    return {
        "schema_version": SHARE_SPACE_SCHEMA_VERSION,
        "project_id": _safe_text(project_id, 120),
        "enabled": False,
        "storage_mode": "runtime_local",
        "spaces": [],
        "count": 0,
        "updated_at": "",
    }


def _existing_spaces_by_id(existing: Any) -> dict[str, dict[str, Any]]:
    cfg = existing if isinstance(existing, dict) else {}
    out: dict[str, dict[str, Any]] = {}
    for item in cfg.get("spaces") or []:
        if not isinstance(item, dict):
            continue
        share_id = _safe_text(item.get("share_id") or item.get("shareId") or item.get("id"), 120)
        if share_id:
            out[share_id] = dict(item)
    return out


def _normalize_share_space_item(
    item: Any,
    *,
    project_id: str,
    existing_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise ValueError("invalid share_space item")

    raw_share_id = item.get("share_id") if "share_id" in item else item.get("shareId", item.get("id"))
    share_id = _safe_text(raw_share_id, 120)
    if not share_id:
        share_id = "share_" + secrets.token_urlsafe(8).replace("-", "_")
    share_id = _safe_storage_id(share_id)
    existing = existing_by_id.get(share_id) or {}

    permission = _safe_text(item.get("permission", existing.get("permission") or DEFAULT_PERMISSION), 40)
    if permission not in ALLOWED_PERMISSIONS:
        raise ValueError("invalid share_space.permission")

    network_scope = _safe_text(item.get("network_scope", item.get("networkScope", existing.get("network_scope") or DEFAULT_NETWORK_SCOPE)), 40)
    if network_scope not in ALLOWED_NETWORK_SCOPES:
        raise ValueError("invalid share_space.network_scope")

    if "allowed_session_ids" in item or "allowedSessionIds" in item or "session_ids" in item:
        allowed_session_ids = _normalize_string_list(
            item.get("allowed_session_ids")
            if "allowed_session_ids" in item
            else item.get("allowedSessionIds", item.get("session_ids")),
            max_items=120,
            max_len=140,
        )
    else:
        allowed_session_ids = _normalize_string_list(existing.get("allowed_session_ids"), max_items=120, max_len=140)

    access_token = _safe_text(
        item.get("access_token")
        if "access_token" in item
        else item.get("accessToken", existing.get("access_token") or secrets.token_urlsafe(24)),
        240,
    )
    if not access_token:
        access_token = secrets.token_urlsafe(24)

    if "passcode" in item:
        passcode = _safe_text(item.get("passcode"), 120)
    else:
        passcode = _safe_text(existing.get("passcode"), 120)

    name = _first_non_empty(
        item.get("name"),
        item.get("display_name"),
        item.get("displayName"),
        existing.get("name"),
        item.get("title"),
        existing.get("title"),
        share_id,
        max_len=200,
    )
    title = _first_non_empty(
        item.get("title"),
        existing.get("title"),
        name,
        share_id,
        max_len=200,
    )

    disabled_at = _safe_text(
        item.get("disabled_at", item.get("disabledAt", existing.get("disabled_at") or "")),
        80,
    )
    existing_deleted_at = _safe_text(existing.get("deleted_at", existing.get("deletedAt") or ""), 80)
    deleted_at = _safe_text(
        item.get("deleted_at", item.get("deletedAt", existing_deleted_at)),
        80,
    )
    if existing_deleted_at:
        deleted_at = existing_deleted_at
    revoked_at = _safe_text(item.get("revoked_at", item.get("revokedAt", existing.get("revoked_at") or "")), 80)
    raw_enabled = item.get("enabled") if "enabled" in item else item.get("is_enabled", item.get("isEnabled"))
    if raw_enabled is None:
        if "enabled" in existing:
            enabled = _coerce_bool(existing.get("enabled"), True)
        else:
            enabled = not bool(disabled_at or deleted_at or revoked_at)
    else:
        enabled = _coerce_bool(raw_enabled, True)
    if disabled_at or deleted_at or revoked_at:
        enabled = False

    now = _utc_now_iso()
    return {
        "share_id": share_id,
        "project_id": _safe_text(project_id, 120),
        "name": name,
        "title": title,
        "allowed_session_ids": allowed_session_ids,
        "access_token": access_token,
        "passcode": passcode,
        "expires_at": _safe_text(item.get("expires_at", item.get("expiresAt", existing.get("expires_at") or "")), 80),
        "revoked_at": revoked_at,
        "disabled_at": disabled_at,
        "deleted_at": deleted_at,
        "enabled": bool(enabled),
        "network_scope": network_scope,
        "permission": permission,
        "created_at": _safe_text(item.get("created_at", item.get("createdAt", existing.get("created_at") or now)), 80),
        "updated_at": now,
    }


def normalize_share_space_config(
    raw: Any,
    *,
    project_id: str,
    existing: Any = None,
) -> dict[str, Any]:
    cfg = raw if isinstance(raw, dict) else {}
    existing_cfg = existing if isinstance(existing, dict) else {}
    existing_by_id = _existing_spaces_by_id(existing_cfg)

    raw_spaces = cfg.get("spaces") if "spaces" in cfg else cfg.get("items")
    known_item_keys = {"share_id", "shareId", "allowed_session_ids", "allowedSessionIds", "session_ids", "access_token", "accessToken"}
    if raw_spaces is None and any(key in cfg for key in known_item_keys):
        raw_spaces = [cfg]
    if raw_spaces is None:
        raw_spaces = existing_cfg.get("spaces") if isinstance(existing_cfg.get("spaces"), list) else []
    if raw_spaces in (None, ""):
        raw_spaces = []
    if not isinstance(raw_spaces, list):
        raise ValueError("invalid share_space.spaces")

    spaces: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw_spaces:
        normalized = _normalize_share_space_item(item, project_id=project_id, existing_by_id=existing_by_id)
        share_id = str(normalized.get("share_id") or "")
        if share_id in seen:
            raise ValueError("duplicate share_space.share_id")
        seen.add(share_id)
        spaces.append(normalized)

    if "enabled" in cfg:
        enabled = _coerce_bool(cfg.get("enabled"), False)
    elif "enabled" in existing_cfg:
        enabled = _coerce_bool(existing_cfg.get("enabled"), False)
    else:
        enabled = bool(spaces)

    return {
        "schema_version": SHARE_SPACE_SCHEMA_VERSION,
        "project_id": _safe_text(project_id, 120),
        "enabled": bool(enabled),
        "storage_mode": "runtime_local",
        "spaces": spaces,
        "count": len(spaces),
        "active_count": len([item for item in spaces if _share_space_status(item) in {"active", "read_only"}]),
        "deleted_count": len([item for item in spaces if _share_space_status(item) == "deleted"]),
        "updated_at": _utc_now_iso(),
    }


def _share_space_status(space: dict[str, Any], *, now: datetime | None = None) -> str:
    if str(space.get("deleted_at") or "").strip():
        return "deleted"
    if str(space.get("revoked_at") or "").strip():
        return "revoked"
    if str(space.get("disabled_at") or "").strip() or not _coerce_bool(space.get("enabled"), True):
        return "disabled"
    expires_at = _parse_iso_datetime(space.get("expires_at"))
    if expires_at is not None:
        current = now or datetime.now(timezone.utc)
        if current.astimezone(timezone.utc) >= expires_at:
            return "expired"
    if str(space.get("permission") or DEFAULT_PERMISSION) == "read":
        return "read_only"
    return "active"


def _space_summary(space: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    status = _share_space_status(space, now=now)
    allowed_ids = _normalize_string_list(space.get("allowed_session_ids"), max_items=120, max_len=140)
    return {
        "share_id": str(space.get("share_id") or ""),
        "project_id": str(space.get("project_id") or ""),
        "name": str(space.get("name") or space.get("title") or space.get("share_id") or ""),
        "title": str(space.get("title") or space.get("name") or space.get("share_id") or ""),
        "status": status,
        "enabled": status in {"active", "read_only"},
        "allowed_session_count": len(allowed_ids),
        "permission": str(space.get("permission") or DEFAULT_PERMISSION),
        "network_scope": str(space.get("network_scope") or DEFAULT_NETWORK_SCOPE),
        "created_at": str(space.get("created_at") or ""),
        "updated_at": str(space.get("updated_at") or ""),
        "expires_at": str(space.get("expires_at") or ""),
        "disabled_at": str(space.get("disabled_at") or ""),
        "revoked_at": str(space.get("revoked_at") or ""),
        "deleted_at": str(space.get("deleted_at") or ""),
    }


def _finalize_config(cfg: dict[str, Any]) -> dict[str, Any]:
    spaces = [item for item in cfg.get("spaces") or [] if isinstance(item, dict)]
    cfg["spaces"] = spaces
    cfg["count"] = len(spaces)
    cfg["active_count"] = len([item for item in spaces if _share_space_status(item) in {"active", "read_only"}])
    cfg["deleted_count"] = len([item for item in spaces if _share_space_status(item) == "deleted"])
    cfg["summaries"] = [_space_summary(item) for item in spaces]
    return cfg


def _space_payload_from_action(raw_share_space: Any) -> dict[str, Any]:
    raw = raw_share_space if isinstance(raw_share_space, dict) else {}
    space = raw.get("space") if isinstance(raw.get("space"), dict) else {}
    item = dict(space)
    for key in (
        "share_id",
        "shareId",
        "name",
        "title",
        "allowed_session_ids",
        "allowedSessionIds",
        "session_ids",
        "permission",
        "access_token",
        "accessToken",
        "passcode",
        "expires_at",
        "expiresAt",
        "revoked_at",
        "revokedAt",
        "disabled_at",
        "disabledAt",
        "deleted_at",
        "deletedAt",
        "enabled",
        "network_scope",
        "networkScope",
    ):
        if key in raw and key not in item:
            item[key] = raw[key]
    return item


def _apply_share_space_action(raw_share_space: Any, *, project_id: str, existing: dict[str, Any]) -> dict[str, Any]:
    raw = raw_share_space if isinstance(raw_share_space, dict) else {}
    action = _safe_text(raw.get("action"), 40).strip().lower()
    if not action:
        return _finalize_config(normalize_share_space_config(raw_share_space, project_id=project_id, existing=existing))
    if action not in SHARE_SPACE_ACTIONS:
        raise ValueError("invalid share_space.action")

    current = normalize_share_space_config(existing, project_id=project_id)
    spaces = [dict(item) for item in current.get("spaces") or [] if isinstance(item, dict)]
    by_id = _existing_spaces_by_id({"spaces": spaces})
    item = _space_payload_from_action(raw)
    share_id = _safe_text(item.get("share_id") or item.get("shareId") or raw.get("share_id") or raw.get("shareId"), 120)
    if not share_id and action in {"enable", "disable", "revoke", "delete", "hard_delete", "patch"}:
        raise ValueError("missing share_space.share_id")
    share_id = _safe_storage_id(share_id) if share_id else ""

    now = _utc_now_iso()
    if action in {"hard_delete"}:
        spaces = [space for space in spaces if _safe_storage_id(space.get("share_id")) != share_id]
    elif action in {"enable", "disable", "revoke", "delete"}:
        if share_id not in by_id:
            raise ValueError("share_space not found")
        target = dict(by_id[share_id])
        if action == "enable":
            if str(target.get("deleted_at") or "").strip():
                raise ValueError("share_space deleted")
            target["enabled"] = True
            target["disabled_at"] = ""
            target["revoked_at"] = ""
        elif action == "disable":
            target["enabled"] = False
            target["disabled_at"] = now
        elif action == "revoke":
            target["enabled"] = False
            target["revoked_at"] = now
        elif action == "delete":
            target["enabled"] = False
            target["deleted_at"] = now
        target["updated_at"] = now
        spaces = [target if _safe_storage_id(space.get("share_id")) == share_id else space for space in spaces]
    else:
        normalized = _normalize_share_space_item(item, project_id=project_id, existing_by_id=by_id)
        target_id = str(normalized.get("share_id") or "")
        replaced = False
        next_spaces: list[dict[str, Any]] = []
        for space in spaces:
            if _safe_storage_id(space.get("share_id")) == target_id:
                next_spaces.append(normalized)
                replaced = True
            else:
                next_spaces.append(space)
        if not replaced:
            next_spaces.append(normalized)
        spaces = next_spaces

    return _finalize_config(
        {
            "schema_version": SHARE_SPACE_SCHEMA_VERSION,
            "project_id": _safe_text(project_id, 120),
            "enabled": _coerce_bool(raw.get("enabled"), _coerce_bool(current.get("enabled"), bool(spaces))),
            "storage_mode": "runtime_local",
            "spaces": spaces,
            "updated_at": now,
        }
    )


def load_project_share_space_config(
    *,
    worktree_root: Any,
    environment_name: str,
    project_id: str,
) -> dict[str, Any]:
    pid = _safe_text(project_id, 120)
    path = share_space_store_path(worktree_root, environment_name, pid)
    if not path.exists():
        cfg = _empty_share_space_config(pid)
        cfg["storage_path"] = str(path)
        return cfg
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        raw = {}
    try:
        cfg = normalize_share_space_config(raw, project_id=pid)
    except Exception:
        cfg = _empty_share_space_config(pid)
    cfg = _finalize_config(cfg)
    cfg["storage_path"] = str(path)
    return cfg


def save_project_share_space_config(
    *,
    worktree_root: Any,
    environment_name: str,
    project_id: str,
    config: dict[str, Any],
) -> Path:
    path = share_space_store_path(worktree_root, environment_name, project_id)
    _atomic_write_json(path, config)
    return path


def update_project_share_space_config_response(
    *,
    worktree_root: Any,
    environment_name: str,
    project_id: str,
    raw_share_space: Any,
) -> tuple[int, dict[str, Any]]:
    pid = _safe_text(project_id, 120)
    if not pid:
        return 400, {"error": "missing project_id"}
    existing = load_project_share_space_config(
        worktree_root=worktree_root,
        environment_name=environment_name,
        project_id=pid,
    )
    try:
        cfg = _apply_share_space_action(raw_share_space, project_id=pid, existing=existing)
        path = save_project_share_space_config(
            worktree_root=worktree_root,
            environment_name=environment_name,
            project_id=pid,
            config=cfg,
        )
    except Exception as exc:
        return 400, {"error": str(exc)}
    cfg["storage_path"] = str(path)
    return 200, {"ok": True, "project_id": pid, "share_space": cfg, "share_space_path": str(path)}


def _public_share_space(space: dict[str, Any]) -> dict[str, Any]:
    summary = _space_summary(space)
    return {
        **summary,
        "allowed_session_ids": list(space.get("allowed_session_ids") or []),
        "can_send": str(space.get("permission") or DEFAULT_PERMISSION) == "read_send",
        "read_only": str(space.get("permission") or DEFAULT_PERMISSION) == "read",
        "passcode_required": bool(str(space.get("passcode") or "").strip()),
    }


def _share_mode_api_base_path(share_id: str) -> str:
    return f"/api/share-spaces/{quote(str(share_id or '').strip(), safe='')}"


def _share_mode_api_paths(share_id: str, *, session_id: str = "") -> dict[str, str]:
    sid = str(session_id or "").strip()
    session_ref = sid or ":session_id"
    return {
        "bootstrap_path": f"{_share_mode_api_base_path(share_id)}/bootstrap",
        "session_path": f"{_share_mode_api_base_path(share_id)}/sessions/{quote(session_ref, safe=':_-')}",
        "announce_path": f"{_share_mode_api_base_path(share_id)}/announce",
    }


def _share_mode_entry_path(
    *,
    project_id: str,
    share_id: str,
    page_path: str,
) -> str:
    params = [
        ("project_id", str(project_id or "").strip()),
        ("share_id", str(share_id or "").strip()),
    ]
    query = urlencode([(key, value) for key, value in params if value])
    return page_path + (("?" + query) if query else "")


def _share_mode_contract(
    *,
    project_id: str,
    share_id: str,
    space: dict[str, Any],
    default_session_id: str = "",
    selected_session_id: str = "",
) -> dict[str, Any]:
    api_paths = _share_mode_api_paths(share_id, session_id=selected_session_id or default_session_id)
    template_paths = _share_mode_api_paths(share_id)
    return {
        "schema_version": SHARE_MODE_SCHEMA_VERSION,
        "entry": {
            "canonical_path": SHARE_MODE_PAGE_PATH,
            "canonical_url": _share_mode_entry_path(
                project_id=project_id,
                share_id=share_id,
                page_path=SHARE_MODE_PAGE_PATH,
            ),
            "legacy_path": LEGACY_PROJECT_CHAT_PAGE_PATH,
            "legacy_url": _share_mode_entry_path(
                project_id=project_id,
                share_id=share_id,
                page_path=LEGACY_PROJECT_CHAT_PAGE_PATH,
            ),
            "legacy_strategy": {
                "mode": "redirect_task_shell_preserve_credentials",
                "fallback": "keep_legacy_redirect_only",
                "preserve_query": True,
            },
        },
        "ui_contract": {
            "shell": "current_task_page",
            "hide_top_tabs": True,
            "hide_project_controls": True,
            "hide_non_share_panels": True,
            "agent_scope": "authorized_only",
            "data_scope": "share_scoped_only",
        },
        "endpoints": {
            **api_paths,
            "session_path_template": template_paths["session_path"],
            "allowlist": [
                template_paths["bootstrap_path"],
                template_paths["session_path"],
                template_paths["announce_path"],
            ],
        },
        "default_session_id": str(default_session_id or ""),
        "selected_session_id": str(selected_session_id or ""),
    }


def _find_share_space(config: dict[str, Any], share_id: str) -> dict[str, Any] | None:
    target = _safe_storage_id(share_id)
    for item in config.get("spaces") or []:
        if not isinstance(item, dict):
            continue
        if _safe_storage_id(item.get("share_id")) == target:
            return item
    return None


def validate_share_space_access(
    config: dict[str, Any],
    *,
    share_id: str,
    access_token: str = "",
    passcode: str = "",
    require_send: bool = False,
    now: datetime | None = None,
) -> tuple[dict[str, Any] | None, int, dict[str, Any]]:
    if not bool(config.get("enabled")):
        return None, 403, {"error": "share_space disabled"}
    space = _find_share_space(config, share_id)
    if not space:
        return None, 404, {"error": "share_space not found"}
    status = _share_space_status(space, now=now)
    if status == "deleted":
        return None, 404, {"error": "share_space deleted", "status": status}
    if status == "disabled":
        return None, 403, {"error": "share_space disabled", "status": status}
    if str(space.get("revoked_at") or "").strip():
        return None, 403, {"error": "share_space revoked", "status": status}

    expires_at = _parse_iso_datetime(space.get("expires_at"))
    if expires_at is not None:
        current = now or datetime.now(timezone.utc)
        if current.astimezone(timezone.utc) >= expires_at:
            return None, 403, {"error": "share_space expired", "status": "expired"}

    expected_token = _safe_text(space.get("access_token"), 240)
    if expected_token and _safe_text(access_token, 240) != expected_token:
        return None, 401, {"error": "invalid share token"}

    expected_passcode = _safe_text(space.get("passcode"), 120)
    if expected_passcode and _safe_text(passcode, 120) != expected_passcode:
        return None, 401, {"error": "invalid share passcode", "passcode_required": True}

    permission = str(space.get("permission") or DEFAULT_PERMISSION)
    if require_send and permission != "read_send":
        return None, 403, {"error": "share_space send not allowed"}
    return space, 200, {}


def _minimal_session_row(
    session: dict[str, Any],
    *,
    decorate_session_display_fields: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    row = deepcopy(session)
    if callable(decorate_session_display_fields):
        row = decorate_session_display_fields(row)
    row = apply_agent_display_fields([row])[0]
    session_id = str(row.get("id") or row.get("session_id") or row.get("sessionId") or "").strip()
    return {
        "id": session_id,
        "session_id": session_id,
        "sessionId": session_id,
        "project_id": str(row.get("project_id") or ""),
        "channel_name": str(row.get("channel_name") or ""),
        "group_key": str(row.get("channel_name") or ""),
        "group_title": str(row.get("channel_name") or ""),
        "alias": str(row.get("alias") or ""),
        "cli_type": str(row.get("cli_type") or "codex"),
        "session_role": str(row.get("session_role") or ""),
        "is_primary": bool(row.get("is_primary")),
        "agent_display_name": str(row.get("agent_display_name") or row.get("display_name") or row.get("alias") or row.get("channel_name") or session_id),
        "agent_display_name_source": str(row.get("agent_display_name_source") or ""),
        "agent_name_state": str(row.get("agent_name_state") or ""),
        "agent_display_issue": str(row.get("agent_display_issue") or ""),
        "conversation_title": str(row.get("agent_display_name") or row.get("display_name") or row.get("alias") or row.get("channel_name") or session_id),
    }


def _allowed_session_ids(space: dict[str, Any]) -> set[str]:
    return set(_normalize_string_list(space.get("allowed_session_ids"), max_items=120, max_len=140))


def _validate_share_mention_targets(
    value: Any,
    *,
    space: dict[str, Any],
    project_id: str,
    session_store: Any,
) -> tuple[int, list[dict[str, str]] | None, dict[str, Any] | None]:
    rows = _normalize_mention_targets(value)
    if not rows:
        return 200, [], None

    allowed_session_ids = _allowed_session_ids(space)
    validated: list[dict[str, str]] = []
    seen_session_ids: set[str] = set()
    for item in rows:
        mention_session_id = str(item.get("session_id") or "").strip()
        if not mention_session_id or mention_session_id in seen_session_ids:
            continue
        if mention_session_id not in allowed_session_ids:
            return 403, None, {"error": "mention target not allowed by share_space"}
        target_session = session_store.get_session(mention_session_id)
        if not isinstance(target_session, dict) or not target_session:
            return 404, None, {"error": "mention target session not found"}
        if bool(target_session.get("is_deleted")):
            return 404, None, {"error": "mention target session not found"}
        target_project_id = str(target_session.get("project_id") or "")
        if target_project_id != str(project_id):
            return 403, None, {"error": "mention target session project mismatch"}
        canonical_row = dict(item)
        canonical_channel_name = str(target_session.get("channel_name") or item.get("channel_name") or "").strip()
        if canonical_channel_name:
            canonical_row["channel_name"] = canonical_channel_name
        canonical_cli_type = _safe_text(target_session.get("cli_type") or item.get("cli_type"), 40).strip().lower()
        if canonical_cli_type:
            canonical_row["cli_type"] = canonical_cli_type
        canonical_row["project_id"] = target_project_id or str(project_id)
        validated.append(canonical_row)
        seen_session_ids.add(mention_session_id)
    return 200, validated, None


def _default_share_agent(agents: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not agents:
        return None
    for agent in agents:
        if bool(agent.get("is_primary")):
            return agent
    return agents[0]


def build_share_bootstrap_response(
    *,
    worktree_root: Any,
    environment_name: str,
    project_id: str,
    share_id: str,
    access_token: str,
    passcode: str,
    session_store: Any,
    decorate_session_display_fields: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> tuple[int, dict[str, Any]]:
    config = load_project_share_space_config(
        worktree_root=worktree_root,
        environment_name=environment_name,
        project_id=project_id,
    )
    space, code, error_payload = validate_share_space_access(
        config,
        share_id=share_id,
        access_token=access_token,
        passcode=passcode,
    )
    if not space:
        return code, error_payload

    agents: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    for session_id in space.get("allowed_session_ids") or []:
        sid = _safe_text(session_id, 140)
        if not sid:
            continue
        session = session_store.get_session(sid)
        if not isinstance(session, dict) or not session:
            skipped.append({"session_id": sid, "reason": "missing"})
            continue
        if bool(session.get("is_deleted")):
            skipped.append({"session_id": sid, "reason": "deleted"})
            continue
        if str(session.get("project_id") or "") != str(project_id):
            skipped.append({"session_id": sid, "reason": "project_mismatch"})
            continue
        agents.append(_minimal_session_row(session, decorate_session_display_fields=decorate_session_display_fields))

    groups_by_channel: dict[str, dict[str, Any]] = {}
    for agent in agents:
        channel = str(agent.get("channel_name") or "")
        group = groups_by_channel.setdefault(channel, {"channel_name": channel, "title": channel, "agents": []})
        group["agents"].append(agent)
    agent_groups = []
    for group in groups_by_channel.values():
        group["count"] = len(group["agents"])
        agent_groups.append(group)
    default_agent = _default_share_agent(agents)
    share_space_id = str(space.get("share_id") or share_id)
    default_session_id = str((default_agent or {}).get("session_id") or "")

    return 200, {
        "ok": True,
        "project_id": project_id,
        "share_id": share_space_id,
        "share_space": _public_share_space(space),
        "share_status": _space_summary(space),
        "share_mode": _share_mode_contract(
            project_id=project_id,
            share_id=share_space_id,
            space=space,
            default_session_id=default_session_id,
        ),
        "agents": agents,
        "agent_groups": agent_groups,
        "default_session_id": default_session_id,
        "default_session": default_agent or {},
        "default_group_key": str((default_agent or {}).get("group_key") or ""),
        "default_group_title": str((default_agent or {}).get("group_title") or ""),
        "count": len(agents),
        "skipped": skipped,
    }


def _minimal_run_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row.get("id") or ""),
        "projectId": str(row.get("projectId") or ""),
        "channelName": str(row.get("channelName") or ""),
        "sessionId": str(row.get("sessionId") or ""),
        "cliType": str(row.get("cliType") or "codex"),
        "status": str(row.get("status") or ""),
        "createdAt": str(row.get("createdAt") or ""),
        "startedAt": str(row.get("startedAt") or ""),
        "finishedAt": str(row.get("finishedAt") or ""),
        "error": str(row.get("error") or ""),
        "messagePreview": str(row.get("messagePreview") or ""),
        "lastPreview": str(row.get("lastPreview") or ""),
        "partialPreview": str(row.get("partialPreview") or ""),
        "sender_type": str(row.get("sender_type") or ""),
        "sender_id": str(row.get("sender_id") or ""),
        "sender_name": str(row.get("sender_name") or ""),
        "message_kind": str(row.get("message_kind") or ""),
        "interaction_mode": str(row.get("interaction_mode") or ""),
        "visible_in_channel_chat": bool(row.get("visible_in_channel_chat")),
        "attachments": list(row.get("attachments") or []) if isinstance(row.get("attachments"), list) else [],
        "mention_targets": list(row.get("mention_targets") or []) if isinstance(row.get("mention_targets"), list) else [],
        "reply_to_run_id": str(row.get("reply_to_run_id") or ""),
        "reply_to_sender_name": str(row.get("reply_to_sender_name") or ""),
        "reply_to_created_at": str(row.get("reply_to_created_at") or ""),
        "reply_to_preview": str(row.get("reply_to_preview") or ""),
        "communication_view": dict(row.get("communication_view") or {}) if isinstance(row.get("communication_view"), dict) else {},
        "trigger_type": str(row.get("trigger_type") or ""),
    }


def _chat_messages_from_runs(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    for row in runs:
        if not isinstance(row, dict):
            continue
        run_id = str(row.get("id") or "")
        message_preview = str(row.get("messagePreview") or "")
        if message_preview:
            messages.append(
                {
                    "id": f"{run_id}:request",
                    "run_id": run_id,
                    "role": "user",
                    "text": message_preview,
                    "createdAt": str(row.get("createdAt") or ""),
                    "sender_name": str(row.get("sender_name") or ""),
                    "status": str(row.get("status") or ""),
                }
            )
        last_preview = str(row.get("lastPreview") or "")
        if last_preview:
            messages.append(
                {
                    "id": f"{run_id}:response",
                    "run_id": run_id,
                    "role": "assistant",
                    "text": last_preview,
                    "createdAt": str(row.get("finishedAt") or row.get("startedAt") or row.get("createdAt") or ""),
                    "sender_name": "assistant",
                    "status": str(row.get("status") or ""),
                }
            )
    return messages


def build_share_session_response(
    *,
    worktree_root: Any,
    environment_name: str,
    project_id: str,
    share_id: str,
    session_id: str,
    access_token: str,
    passcode: str,
    session_store: Any,
    store: Any,
    decorate_session_display_fields: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    limit: int = 30,
) -> tuple[int, dict[str, Any]]:
    config = load_project_share_space_config(
        worktree_root=worktree_root,
        environment_name=environment_name,
        project_id=project_id,
    )
    space, code, error_payload = validate_share_space_access(
        config,
        share_id=share_id,
        access_token=access_token,
        passcode=passcode,
    )
    if not space:
        return code, error_payload

    sid = _safe_text(session_id, 140)
    if sid not in _allowed_session_ids(space):
        return 403, {"error": "session not allowed by share_space"}
    session = session_store.get_session(sid)
    if not isinstance(session, dict) or not session:
        return 404, {"error": "session not found"}
    if bool(session.get("is_deleted")):
        return 404, {"error": "session not found"}
    if str(session.get("project_id") or "") != str(project_id):
        return 403, {"error": "session project mismatch"}

    try:
        run_limit = max(1, min(100, int(limit)))
    except Exception:
        run_limit = 30
    runs = store.list_runs(
        project_id=project_id,
        session_id=sid,
        limit=run_limit,
        payload_mode="light",
    )

    run_rows = [_minimal_run_row(row) for row in runs if isinstance(row, dict)]
    messages = _chat_messages_from_runs(run_rows)
    can_send = str(space.get("permission") or DEFAULT_PERMISSION) == "read_send"
    share_space_id = str(space.get("share_id") or share_id)
    session_row = _minimal_session_row(session, decorate_session_display_fields=decorate_session_display_fields)
    return 200, {
        "ok": True,
        "project_id": project_id,
        "share_id": share_space_id,
        "share_space": _public_share_space(space),
        "share_status": _space_summary(space),
        "share_mode": _share_mode_contract(
            project_id=project_id,
            share_id=share_space_id,
            space=space,
            default_session_id=sid,
            selected_session_id=sid,
        ),
        "session": session_row,
        "runs": run_rows,
        "run_summaries": run_rows,
        "messages": messages,
        "chat": {
            "share_id": share_space_id,
            "session_id": sid,
            "permission": str(space.get("permission") or DEFAULT_PERMISSION),
            "can_send": can_send,
            "read_only": not can_send,
            "messages": messages,
        },
        "conversation": {
            "share_id": share_space_id,
            "session_id": sid,
            "title": str(session_row.get("conversation_title") or session_row.get("agent_display_name") or sid),
            "channel_name": str(session_row.get("channel_name") or ""),
            "message_count": len(messages),
            "run_count": len(run_rows),
        },
        "composer": {
            "enabled": can_send,
            "disabled_reason": "" if can_send else "read_only",
        },
        "count": len(runs),
    }


def build_share_announce_request(
    *,
    worktree_root: Any,
    environment_name: str,
    project_id: str,
    share_id: str,
    access_token: str,
    passcode: str,
    body: dict[str, Any],
    session_store: Any,
    decorate_session_display_fields: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> tuple[int, dict[str, Any]]:
    config = load_project_share_space_config(
        worktree_root=worktree_root,
        environment_name=environment_name,
        project_id=project_id,
    )
    space, code, error_payload = validate_share_space_access(
        config,
        share_id=share_id,
        access_token=access_token,
        passcode=passcode,
        require_send=True,
    )
    if not space:
        return code, error_payload

    session_id = _safe_text(body.get("session_id") if "session_id" in body else body.get("sessionId"), 140)
    if not session_id:
        return 400, {"error": "missing session_id"}
    if session_id not in _allowed_session_ids(space):
        return 403, {"error": "session not allowed by share_space"}

    message = _safe_text(body.get("message"), 20_000)
    if not message:
        return 400, {"error": "missing message"}

    session = session_store.get_session(session_id)
    if not isinstance(session, dict) or not session:
        return 404, {"error": "session not found"}
    if bool(session.get("is_deleted")):
        return 404, {"error": "session not found"}
    if str(session.get("project_id") or "") != str(project_id):
        return 403, {"error": "session project mismatch"}

    mention_targets_value = body.get("mention_targets") if "mention_targets" in body else body.get("mentionTargets")
    mention_code, mention_targets, mention_error = _validate_share_mention_targets(
        mention_targets_value,
        space=space,
        project_id=project_id,
        session_store=session_store,
    )
    if mention_error:
        return mention_code, mention_error

    sender_name = _safe_text(
        body.get("sender_name") if "sender_name" in body else body.get("senderName"),
        120,
    ) or "外部协作者"
    reply_to_run_id = _safe_text(
        body.get("reply_to_run_id") if "reply_to_run_id" in body else body.get("replyToRunId"),
        120,
    )
    sender_id = f"share:{space.get('share_id') or share_id}"
    extra_meta = {
        "interaction_mode": "task_with_receipt",
        "delivery_mode": "wait_reply",
        "communication_view": {"message_kind": "manual_update"},
        "share_mode": {
            "schema_version": SHARE_MODE_SCHEMA_VERSION,
            "share_id": str(space.get("share_id") or share_id),
            "selected_session_id": session_id,
        },
        "share_space": {
            "share_id": str(space.get("share_id") or share_id),
            "project_id": project_id,
            "permission": str(space.get("permission") or DEFAULT_PERMISSION),
            "network_scope": str(space.get("network_scope") or DEFAULT_NETWORK_SCOPE),
            "authorized_session_id": session_id,
        },
        "source_ref": {
            "project_id": project_id,
            "channel_name": "share_space",
            "session_id": "",
            "run_id": "",
        },
        "target_ref": {
            "project_id": project_id,
            "channel_name": str(session.get("channel_name") or ""),
            "session_id": session_id,
        },
    }
    if mention_targets:
        extra_meta["mention_targets"] = mention_targets
    if reply_to_run_id:
        extra_meta["reply_to_run_id"] = reply_to_run_id

    return 200, {
        "ok": True,
        "project_id": project_id,
        "share_id": str(space.get("share_id") or share_id),
        "session": _minimal_session_row(session, decorate_session_display_fields=decorate_session_display_fields),
        "channel_name": str(session.get("channel_name") or ""),
        "session_id": session_id,
        "cli_type": str(session.get("cli_type") or "codex").strip() or "codex",
        "model": str(session.get("model") or "").strip(),
        "reasoning_effort": str(session.get("reasoning_effort") or "").strip(),
        "message": message,
        "sender_type": "user",
        "sender_id": sender_id,
        "sender_name": sender_name,
        "extra_meta": extra_meta,
    }
