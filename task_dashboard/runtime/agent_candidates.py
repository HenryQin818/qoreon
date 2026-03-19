# -*- coding: utf-8 -*-

from __future__ import annotations

from typing import Any, Callable
from urllib.parse import parse_qs


_ACTIVE_STATE_PRIORITY = {
    "running": 5,
    "queued": 4,
    "retry_waiting": 3,
    "external_busy": 2,
    "done": 1,
    "idle": 0,
    "error": 0,
}


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _state_priority(row: dict[str, Any]) -> int:
    state = _safe_text(row.get("session_display_state") or "").lower()
    return int(_ACTIVE_STATE_PRIORITY.get(state, 0))


def _pick_recommended_session(rows: list[dict[str, Any]]) -> tuple[dict[str, Any], str]:
    ordered = sorted(
        (dict(row) for row in rows if isinstance(row, dict)),
        key=lambda row: (
            1 if bool(row.get("is_primary")) else 0,
            _state_priority(row),
            _safe_text(row.get("last_used_at") or row.get("lastActiveAt")),
            _safe_text(row.get("created_at")),
            _safe_text(row.get("id") or row.get("sessionId") or row.get("session_id")),
        ),
        reverse=True,
    )
    if not ordered:
        return {}, ""
    selected = ordered[0]
    if bool(selected.get("is_primary")):
        return selected, "effective_primary"
    state = _safe_text(selected.get("session_display_state") or "").lower()
    if state in {"running", "queued", "retry_waiting", "external_busy"}:
        return selected, f"runtime_state:{state}"
    if _safe_text(selected.get("last_used_at") or selected.get("lastActiveAt")):
        return selected, "latest_last_used_at"
    return selected, "latest_created_at"


def build_agent_candidates_payload(
    *,
    session_store: Any,
    store: Any,
    project_id: str,
    environment_name: str,
    worktree_root: Any,
    apply_effective_primary_flags: Callable[[Any, str, list[dict[str, Any]]], list[dict[str, Any]]],
    decorate_sessions_display_fields: Callable[[list[dict[str, Any]]], list[dict[str, Any]]],
    apply_session_context_rows: Callable[..., list[dict[str, Any]]],
    apply_session_work_context: Callable[..., dict[str, Any]],
    attach_runtime_state_to_sessions: Callable[[Any, list[dict[str, Any]]], list[dict[str, Any]]],
) -> dict[str, Any]:
    sessions = session_store.list_sessions(project_id, include_deleted=False)
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

    by_channel: dict[str, list[dict[str, Any]]] = {}
    for raw in sessions:
        row = dict(raw if isinstance(raw, dict) else {})
        channel_name = _safe_text(row.get("channel_name") or row.get("channelName"))
        session_id = _safe_text(row.get("id") or row.get("sessionId") or row.get("session_id"))
        if not channel_name or not session_id:
            continue
        by_channel.setdefault(channel_name, []).append(row)

    agent_targets: list[dict[str, Any]] = []
    for channel_name in sorted(by_channel.keys()):
        bucket = by_channel.get(channel_name) or []
        selected, reason = _pick_recommended_session(bucket)
        if not selected:
            continue
        item = dict(selected)
        item["agent_candidate_source"] = "session_store_recommended"
        item["selection_reason"] = reason
        item["candidate_count_for_channel"] = len(bucket)
        agent_targets.append(item)

    return {
        "project_id": project_id,
        "source": "session_store_recommended",
        "selection_policy": "per_channel_recommended_session",
        "raw_session_count": len(sessions),
        "agent_targets": agent_targets,
        "count": len(agent_targets),
    }


def list_agent_candidates_response(
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
    qs = parse_qs(query_string or "")
    project_id = _safe_text((qs.get("project_id") or qs.get("projectId") or [""])[0])
    if not project_id:
        return 400, {"error": "missing project_id"}

    payload = build_agent_candidates_payload(
        session_store=session_store,
        store=store,
        project_id=project_id,
        environment_name=environment_name,
        worktree_root=worktree_root,
        apply_effective_primary_flags=apply_effective_primary_flags,
        decorate_sessions_display_fields=decorate_sessions_display_fields,
        apply_session_context_rows=apply_session_context_rows,
        apply_session_work_context=apply_session_work_context,
        attach_runtime_state_to_sessions=attach_runtime_state_to_sessions,
    )
    return 200, payload
