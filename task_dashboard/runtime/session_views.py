# -*- coding: utf-8 -*-

from __future__ import annotations

from typing import Any, Callable

from task_dashboard.runtime.session_display_state import build_session_display_fields


def apply_session_context_rows(
    sessions: list[dict[str, Any]],
    *,
    project_id: str,
    environment_name: str,
    worktree_root: Any,
    apply_session_work_context: Callable[..., dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in sessions:
        rows.append(
            apply_session_work_context(
                row,
                project_id=project_id,
                environment_name=environment_name,
                worktree_root=worktree_root,
            )
        )
    return rows


def build_session_detail_payload(
    session: dict[str, Any],
    *,
    session_id: str,
    project_id: str,
    environment_name: str,
    worktree_root: Any,
    store: Any,
    heartbeat_runtime: Any,
    apply_session_work_context: Callable[..., dict[str, Any]],
    build_project_session_runtime_index: Callable[[Any, str], dict[str, Any]],
    build_session_runtime_state_for_row: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]],
    load_session_heartbeat_config: Callable[[dict[str, Any]], dict[str, Any]],
    heartbeat_summary_payload: Callable[[Any], Any],
) -> dict[str, Any]:
    enriched = apply_session_work_context(
        session,
        project_id=project_id,
        environment_name=environment_name,
        worktree_root=worktree_root,
    )
    agg: dict[str, Any] = {}
    if project_id:
        idx = build_project_session_runtime_index(store, project_id)
        agg = idx.get(session_id) if isinstance(idx, dict) else {}
    runtime_state = build_session_runtime_state_for_row(enriched, agg or {})
    enriched["runtime_state"] = runtime_state
    enriched.update(build_session_display_fields(runtime_state, agg or {}))

    heartbeat_cfg = load_session_heartbeat_config(enriched)
    heartbeat_payload = {
        "enabled": bool(heartbeat_cfg.get("enabled")),
        "tasks": heartbeat_cfg.get("tasks") or [],
        "count": int(heartbeat_cfg.get("count") or 0),
        "enabled_count": int(heartbeat_cfg.get("enabled_count") or 0),
        "summary": heartbeat_summary_payload(heartbeat_cfg),
        "ready": bool(heartbeat_cfg.get("ready")),
        "errors": list(heartbeat_cfg.get("errors") or []),
    }
    if heartbeat_runtime is not None and project_id:
        heartbeat_payload = heartbeat_runtime.list_session_tasks(project_id, session_id)
    enriched["heartbeat"] = heartbeat_payload
    enriched["heartbeat_summary"] = heartbeat_summary_payload(heartbeat_payload)
    return enriched
