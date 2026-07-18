# -*- coding: utf-8 -*-

from __future__ import annotations

import json
import os
import secrets
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable

from task_dashboard.runtime.project_execution_context import (
    build_project_execution_context,
    merge_work_context_overrides,
)


_CONTEXT_FIELDS = ("environment", "worktree_root", "workdir", "branch")
_LOCKS_GUARD = threading.Lock()
_MIGRATION_LOCKS: dict[tuple[int, str], threading.RLock] = {}


class SessionMigrationError(RuntimeError):
    """Structured failure for a compensated cross-channel migration."""

    def __init__(
        self,
        message: str,
        *,
        rollback_complete: bool,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(message)
        self.error_code = (
            "session_migration_failed"
            if rollback_complete
            else "session_migration_rollback_failed"
        )
        self.payload = {
            "error": message,
            "error_code": self.error_code,
            "rollback_complete": bool(rollback_complete),
        }
        if cause is not None:
            self.payload["cause"] = str(cause)[:1000]


def project_migration_lock(session_store: Any, project_id: str) -> threading.RLock:
    key = (id(session_store), str(project_id or "").strip())
    with _LOCKS_GUARD:
        lock = _MIGRATION_LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _MIGRATION_LOCKS[key] = lock
        return lock


def rebuild_session_work_context_for_update(
    session: dict[str, Any],
    update_fields: dict[str, Any],
    *,
    project_id: str,
    environment_name: str,
    worktree_root: Any,
    apply_session_work_context: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    """Replace explicitly updated context values without reviving old overrides."""

    preview = dict(session)
    preview.update(update_fields)
    explicit_fields = [key for key in _CONTEXT_FIELDS if key in update_fields]
    if not explicit_fields:
        return apply_session_work_context(
            preview,
            project_id=project_id,
            environment_name=environment_name,
            worktree_root=worktree_root,
        )

    current = apply_session_work_context(
        session,
        project_id=project_id,
        environment_name=environment_name,
        worktree_root=worktree_root,
    )
    current_context = (
        current.get("project_execution_context")
        if isinstance(current.get("project_execution_context"), dict)
        else {}
    )
    source = (
        current_context.get("source")
        if isinstance(current_context.get("source"), dict)
        else {}
    )
    old_override = (
        current_context.get("override")
        if isinstance(current_context.get("override"), dict)
        else {}
    )
    old_override_fields = {
        str(item or "").strip()
        for item in (old_override.get("fields") if isinstance(old_override.get("fields"), list) else [])
        if str(item or "").strip() in _CONTEXT_FIELDS
    }

    override_values: dict[str, str] = {}
    for key in _CONTEXT_FIELDS:
        if key in update_fields:
            value = str(update_fields.get(key) or "").strip()
        elif key in old_override_fields:
            value = str(current.get(key) or "").strip()
        else:
            continue
        if value:
            override_values[key] = value

    effective, override_fields, _override_source = merge_work_context_overrides(
        source,
        override_values,
        override_source="request",
    )
    context_source = str(current_context.get("context_source") or "").strip()
    preview["project_execution_context"] = build_project_execution_context(
        target={
            "project_id": project_id,
            "channel_name": str(preview.get("channel_name") or "").strip(),
            "session_id": str(preview.get("id") or "").strip(),
            **effective,
        },
        source=source,
        context_source=context_source,
        override_fields=override_fields,
        override_source="request" if override_fields else "",
    )
    return apply_session_work_context(
        preview,
        project_id=project_id,
        environment_name=environment_name,
        worktree_root=worktree_root,
    )


def snapshot_affected_bindings(
    session_binding_store: Any,
    *,
    project_id: str,
    session_id: str,
    channel_names: set[str],
) -> list[dict[str, Any]]:
    rows = session_binding_store.list_bindings(project_id)
    return [
        deepcopy(row)
        for row in rows
        if isinstance(row, dict)
        and (
            str(row.get("sessionId") or "").strip() == session_id
            or str(row.get("channelName") or "").strip() in channel_names
        )
    ]


def sync_cross_channel_bindings(
    session_binding_store: Any,
    session_store: Any,
    *,
    updated_session: dict[str, Any],
    old_channel_name: str,
) -> None:
    session_binding_store.save_binding(
        str(updated_session.get("id") or "").strip(),
        str(updated_session.get("project_id") or "").strip(),
        str(updated_session.get("channel_name") or "").strip(),
        str(updated_session.get("cli_type") or "codex").strip() or "codex",
    )

    old_primary = session_store.get_channel_default_session(
        str(updated_session.get("project_id") or "").strip(),
        old_channel_name,
    )
    if not isinstance(old_primary, dict) or not bool(old_primary.get("is_primary")):
        return
    old_primary_id = str(old_primary.get("id") or "").strip()
    if not old_primary_id or old_primary_id == str(updated_session.get("id") or "").strip():
        return
    session_binding_store.save_binding(
        old_primary_id,
        str(updated_session.get("project_id") or "").strip(),
        old_channel_name,
        str(old_primary.get("cli_type") or "codex").strip() or "codex",
    )


def restore_affected_bindings(
    session_binding_store: Any,
    snapshots: list[dict[str, Any]],
    *,
    project_id: str,
    session_id: str,
    channel_names: set[str],
) -> None:
    current = session_binding_store.list_bindings(project_id)
    affected_ids = {session_id}
    affected_ids.update(
        str(row.get("sessionId") or "").strip()
        for row in snapshots
        if isinstance(row, dict)
    )
    for row in current:
        if not isinstance(row, dict):
            continue
        sid = str(row.get("sessionId") or "").strip()
        channel = str(row.get("channelName") or "").strip()
        if sid in affected_ids or channel in channel_names:
            session_binding_store.delete_binding(sid)

    for row in snapshots:
        sid = str(row.get("sessionId") or "").strip()
        if not sid:
            continue
        path_resolver = getattr(session_binding_store, "_session_path", None)
        if not callable(path_resolver):
            raise RuntimeError("session binding store does not support exact rollback")
        path = Path(path_resolver(sid))
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + f".tmp-{secrets.token_hex(6)}")
        tmp.write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)
