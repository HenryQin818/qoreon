# -*- coding: utf-8 -*-

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import parse_qs

import json


def build_sessions_list_payload(
    *,
    session_store: Any,
    store: Any,
    project_id: str,
    channel_name: str = "",
    include_deleted: bool = False,
    environment_name: str,
    worktree_root: Any,
    apply_effective_primary_flags: Callable[[Any, str, list[dict[str, Any]]], list[dict[str, Any]]],
    decorate_sessions_display_fields: Callable[[list[dict[str, Any]]], list[dict[str, Any]]],
    apply_session_context_rows: Callable[..., list[dict[str, Any]]],
    apply_session_work_context: Callable[..., dict[str, Any]],
    attach_runtime_state_to_sessions: Callable[[Any, list[dict[str, Any]]], list[dict[str, Any]]],
) -> dict[str, Any]:
    sessions = session_store.list_sessions(
        project_id,
        channel_name if channel_name else None,
        include_deleted=include_deleted,
    )
    sessions = apply_effective_primary_flags(session_store, project_id, sessions)
    sessions = decorate_sessions_display_fields(sessions)
    sessions = apply_session_context_rows(
        sessions,
        project_id=project_id,
        environment_name=environment_name,
        worktree_root=worktree_root,
        apply_session_work_context=apply_session_work_context,
    )
    sessions = attach_runtime_state_to_sessions(store, sessions, project_id=project_id)
    return {"sessions": sessions}


def build_channel_sessions_payload(
    *,
    session_store: Any,
    store: Any,
    project_id: str,
    channel_name: str,
    include_deleted: bool = False,
    environment_name: str,
    worktree_root: Any,
    apply_effective_primary_flags: Callable[[Any, str, list[dict[str, Any]]], list[dict[str, Any]]],
    decorate_sessions_display_fields: Callable[[list[dict[str, Any]]], list[dict[str, Any]]],
    apply_session_context_rows: Callable[..., list[dict[str, Any]]],
    apply_session_work_context: Callable[..., dict[str, Any]],
    resolve_channel_primary_session_id: Callable[[Any, str, str], str],
) -> dict[str, Any]:
    sessions = session_store.list_sessions(
        project_id,
        channel_name,
        include_deleted=include_deleted,
    )
    sessions = apply_effective_primary_flags(session_store, project_id, sessions)
    sessions = decorate_sessions_display_fields(sessions)
    sessions = apply_session_context_rows(
        sessions,
        project_id=project_id,
        environment_name=environment_name,
        worktree_root=worktree_root,
        apply_session_work_context=apply_session_work_context,
    )
    primary_session_id = resolve_channel_primary_session_id(session_store, project_id, channel_name)
    return {
        "project_id": project_id,
        "channel_name": channel_name,
        "primary_session_id": primary_session_id,
        "sessions": sessions,
        "count": len(sessions),
    }


def build_session_detail_response(
    *,
    session_store: Any,
    store: Any,
    session_id: str,
    environment_name: str,
    worktree_root: Any,
    heartbeat_runtime: Any,
    infer_project_id_for_session: Callable[[Any, str], str],
    apply_effective_primary_flags: Callable[[Any, str, list[dict[str, Any]]], list[dict[str, Any]]],
    decorate_session_display_fields: Callable[[dict[str, Any]], dict[str, Any]],
    build_session_detail_payload: Callable[..., dict[str, Any]],
    apply_session_work_context: Callable[..., dict[str, Any]],
    build_project_session_runtime_index: Callable[[Any, str], dict[str, Any]],
    build_session_runtime_state_for_row: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]],
    load_session_heartbeat_config: Callable[[dict[str, Any]], dict[str, Any]],
    heartbeat_summary_payload: Callable[[Any], Any],
) -> Optional[dict[str, Any]]:
    session = session_store.get_session(session_id)
    if not session:
        return None
    project_id = str(session.get("project_id") or "").strip() or infer_project_id_for_session(store, session_id)
    session = apply_effective_primary_flags(session_store, project_id, [session])[0]
    session = decorate_session_display_fields(session)
    return build_session_detail_payload(
        session,
        session_id=session_id,
        project_id=project_id,
        environment_name=environment_name,
        worktree_root=worktree_root,
        store=store,
        heartbeat_runtime=heartbeat_runtime,
        apply_session_work_context=apply_session_work_context,
        build_project_session_runtime_index=build_project_session_runtime_index,
        build_session_runtime_state_for_row=build_session_runtime_state_for_row,
        load_session_heartbeat_config=load_session_heartbeat_config,
        heartbeat_summary_payload=heartbeat_summary_payload,
    )


def _coerce_bool(value: str, default: bool) -> bool:
    """Convert a string value to boolean."""
    if not value:
        return default
    return value.lower() in ("1", "true", "yes", "on")


def list_sessions_response(
    *,
    query_string: str,
    session_store: Any,
    store: Any,
    environment_name: str,
    worktree_root: Any,
    apply_effective_primary_flags: Callable[[Any, str, list[dict[str, Any]]], list[dict[str, Any]]],
    decorate_sessions_display_fields: Callable[[list[dict[str, Any]]], list[dict[str, Any]]],
    apply_session_context_rows: Callable[..., list[dict[str, Any]]],
    apply_session_work_context: Callable[..., dict[str, Any]],
    attach_runtime_state_to_sessions: Callable[[Any, list[dict[str, Any]]], list[dict[str, Any]]],
) -> tuple[int, dict[str, Any]]:
    """Handle GET /api/sessions - list sessions with optional filters."""
    qs = parse_qs(query_string or "")
    project_id = (qs.get("project_id") or [""])[0]
    channel_name = (qs.get("channel_name") or [""])[0]
    include_deleted = _coerce_bool((qs.get("include_deleted") or qs.get("includeDeleted") or [""])[0], False)

    if not project_id:
        return 400, {"error": "missing project_id"}

    payload = build_sessions_list_payload(
        session_store=session_store,
        store=store,
        project_id=project_id,
        channel_name=channel_name,
        include_deleted=include_deleted,
        environment_name=environment_name,
        worktree_root=worktree_root,
        apply_effective_primary_flags=apply_effective_primary_flags,
        decorate_sessions_display_fields=decorate_sessions_display_fields,
        apply_session_context_rows=apply_session_context_rows,
        apply_session_work_context=apply_session_work_context,
        attach_runtime_state_to_sessions=attach_runtime_state_to_sessions,
    )
    return 200, payload


def list_channel_sessions_response(
    *,
    query_string: str,
    session_store: Any,
    store: Any,
    environment_name: str,
    worktree_root: Any,
    apply_effective_primary_flags: Callable[[Any, str, list[dict[str, Any]]], list[dict[str, Any]]],
    decorate_sessions_display_fields: Callable[[list[dict[str, Any]]], list[dict[str, Any]]],
    apply_session_context_rows: Callable[..., list[dict[str, Any]]],
    apply_session_work_context: Callable[..., dict[str, Any]],
    resolve_channel_primary_session_id: Callable[[Any, str, str], str],
) -> tuple[int, dict[str, Any]]:
    """Handle GET /api/channel-sessions - list sessions for a specific channel."""
    qs = parse_qs(query_string or "")
    project_id = (qs.get("project_id") or [""])[0]
    channel_name = (qs.get("channel_name") or [""])[0]
    include_deleted = _coerce_bool((qs.get("include_deleted") or qs.get("includeDeleted") or [""])[0], False)

    if not project_id:
        return 400, {"error": "missing project_id"}
    if not channel_name:
        return 400, {"error": "missing channel_name"}

    payload = build_channel_sessions_payload(
        session_store=session_store,
        store=store,
        project_id=project_id,
        channel_name=channel_name,
        include_deleted=include_deleted,
        environment_name=environment_name,
        worktree_root=worktree_root,
        apply_effective_primary_flags=apply_effective_primary_flags,
        decorate_sessions_display_fields=decorate_sessions_display_fields,
        apply_session_context_rows=apply_session_context_rows,
        apply_session_work_context=apply_session_work_context,
        resolve_channel_primary_session_id=resolve_channel_primary_session_id,
    )
    return 200, payload


def get_session_detail_response(
    *,
    session_id: str,
    session_store: Any,
    store: Any,
    environment_name: str,
    worktree_root: Any,
    heartbeat_runtime: Any,
    infer_project_id_for_session: Callable[[Any, str], str],
    apply_effective_primary_flags: Callable[[Any, str, list[dict[str, Any]]], list[dict[str, Any]]],
    decorate_session_display_fields: Callable[[dict[str, Any]], dict[str, Any]],
    build_session_detail_payload: Callable[..., dict[str, Any]],
    apply_session_work_context: Callable[..., dict[str, Any]],
    build_project_session_runtime_index: Callable[[Any, str], dict[str, Any]],
    build_session_runtime_state_for_row: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]],
    load_session_heartbeat_config: Callable[[dict[str, Any]], dict[str, Any]],
    heartbeat_summary_payload: Callable[[Any], Any],
) -> tuple[int, dict[str, Any]]:
    """Handle GET /api/sessions/{session_id} - get single session details."""
    payload = build_session_detail_response(
        session_store=session_store,
        store=store,
        session_id=session_id,
        environment_name=environment_name,
        worktree_root=worktree_root,
        heartbeat_runtime=heartbeat_runtime,
        infer_project_id_for_session=infer_project_id_for_session,
        apply_effective_primary_flags=apply_effective_primary_flags,
        decorate_session_display_fields=decorate_session_display_fields,
        build_session_detail_payload=build_session_detail_payload,
        apply_session_work_context=apply_session_work_context,
        build_project_session_runtime_index=build_project_session_runtime_index,
        build_session_runtime_state_for_row=build_session_runtime_state_for_row,
        load_session_heartbeat_config=load_session_heartbeat_config,
        heartbeat_summary_payload=heartbeat_summary_payload,
    )
    if payload is None:
        return 404, {"error": "session not found"}
    return 200, payload


def dedup_session_channel_response(
    *,
    body: dict[str, Any],
    session_store: Any,
    safe_text: Callable[[Any, int], str],
    now_iso: Callable[[], str],
    coerce_bool: Callable[[Any, bool], bool],
) -> tuple[int, dict[str, Any]]:
    """Handle POST /api/sessions/dedup - deduplicate channel sessions."""
    project_id = safe_text(body.get("project_id") if "project_id" in body else body.get("projectId"), 120).strip()
    channel_name = safe_text(body.get("channel_name") if "channel_name" in body else body.get("channelName"), 240).strip()
    keep_session_id = safe_text(
        body.get("keep_session_id") if "keep_session_id" in body else body.get("keepSessionId"),
        120,
    ).strip()
    strategy = safe_text(body.get("strategy"), 24).strip().lower() or "latest"

    if not project_id or not channel_name:
        return 400, {"error": "missing project_id or channel_name"}
    if strategy not in {"latest", "first"}:
        return 400, {"error": "invalid strategy"}

    result = session_store.dedup_channel_sessions(
        project_id=project_id,
        channel_name=channel_name,
        keep_session_id=keep_session_id,
        strategy=strategy,
    )

    log_entry = {
        "at": now_iso(),
        "project_id": project_id,
        "channel_name": channel_name,
        "keep_session_id": keep_session_id,
        "strategy": strategy,
        "result": result,
    }
    log_path = _append_session_dedup_log(log_entry)
    return 200, {"ok": True, "result": result, "log_path": log_path}


def _append_session_dedup_log(entry: dict[str, Any]) -> str:
    """Append dedup action ledger for audit."""
    log_path = Path(__file__).resolve().parent.parent.parent / ".run" / "session-dedup-log.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(entry, ensure_ascii=False)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    return str(log_path)


def get_session_binding_response(
    *,
    session_id: str,
    session_binding_store: Any,
) -> tuple[int, dict[str, Any]]:
    """Handle GET /api/sessions/binding/:id - get single session binding."""
    binding = session_binding_store.get_binding(session_id)
    if binding:
        return 200, binding
    else:
        return 404, {"error": "not found"}


def list_session_heartbeat_task_history_route_response(
    *,
    session_id: str,
    heartbeat_task_id: str,
    limit: int,
    session_store: Any,
    store: Any,
    heartbeat_runtime: Any,
    infer_project_id_for_session: Callable[[Any, str], str],
    list_session_heartbeat_task_history_response: Callable[..., tuple[int, dict[str, Any]]],
) -> tuple[int, dict[str, Any]]:
    """Handle GET /api/sessions/:id/heartbeat-tasks/:taskId/history.

    This is a thin wrapper that delegates to the existing implementation in heartbeat_routes.
    """
    return list_session_heartbeat_task_history_response(
        session_id=session_id,
        heartbeat_task_id=heartbeat_task_id,
        limit=limit,
        session_store=session_store,
        store=store,
        heartbeat_runtime=heartbeat_runtime,
        infer_project_id_for_session=infer_project_id_for_session,
    )
