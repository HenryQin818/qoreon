# -*- coding: utf-8 -*-

from __future__ import annotations

from typing import Any, Callable

from task_dashboard.runtime.agent_display_name import attach_agent_display_fields
from task_dashboard.runtime.session_display_state import build_session_display_fields
from task_dashboard.runtime.session_task_tracking import build_session_task_tracking


def _safe_heartbeat_task_id(item: dict[str, Any], index: int) -> str:
    task_id = str(
        item.get("heartbeat_task_id")
        or item.get("heartbeatTaskId")
        or ""
    ).strip()
    if task_id:
        return task_id
    return f"__heartbeat_task_{index}"


def _build_heartbeat_task_map(tasks: Any) -> dict[str, dict[str, Any]]:
    rows = tasks if isinstance(tasks, list) else []
    out: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(rows):
        if not isinstance(raw, dict):
            continue
        out[_safe_heartbeat_task_id(raw, index)] = dict(raw)
    return out


def _heartbeat_summary_from_task_map(task_map: dict[str, dict[str, Any]]) -> dict[str, Any]:
    total_count = len(task_map)
    enabled_count = 0
    ready_count = 0
    for item in task_map.values():
        enabled = bool(item.get("enabled"))
        ready = bool(item.get("ready"))
        if enabled:
            enabled_count += 1
        if enabled and ready:
            ready_count += 1
    return {
        "total_count": total_count,
        "enabled_count": enabled_count,
        "ready_count": ready_count,
        "has_enabled_tasks": enabled_count > 0,
    }


def _build_project_assigned_heartbeat_task_map_by_session(
    *,
    project_id: str,
    heartbeat_runtime: Any,
) -> dict[str, dict[str, dict[str, Any]]] | None:
    pid = str(project_id or "").strip()
    if heartbeat_runtime is None or not pid:
        return None
    try:
        payload = heartbeat_runtime.list_tasks(pid)
    except Exception:
        return None
    items = payload.get("items") if isinstance(payload, dict) else []
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for index, raw in enumerate(items if isinstance(items, list) else []):
        if not isinstance(raw, dict):
            continue
        session_id = str(
            raw.get("session_id")
            or raw.get("sessionId")
            or ""
        ).strip()
        if not session_id:
            continue
        bucket = out.setdefault(session_id, {})
        bucket[_safe_heartbeat_task_id(raw, index)] = dict(raw)
    return out


def _build_session_assigned_heartbeat_task_map_by_session(
    *,
    project_id: str,
    heartbeat_runtime: Any,
    load_session_heartbeat_config: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict[str, dict[str, dict[str, Any]]] | None:
    pid = str(project_id or "").strip()
    session_store = getattr(heartbeat_runtime, "session_store", None)
    list_sessions = getattr(session_store, "list_sessions", None)
    if heartbeat_runtime is None or not pid or not callable(list_sessions):
        return None
    try:
        sessions = list_sessions(pid)
    except Exception:
        return None
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for session in sessions if isinstance(sessions, list) else []:
        if not isinstance(session, dict):
            continue
        source_session_id = str(
            session.get("id")
            or session.get("session_id")
            or session.get("sessionId")
            or ""
        ).strip()
        heartbeat_cfg = load_session_heartbeat_config(session)
        tasks = heartbeat_cfg.get("tasks") if isinstance(heartbeat_cfg, dict) else []
        for index, raw in enumerate(tasks if isinstance(tasks, list) else []):
            if not isinstance(raw, dict):
                continue
            item = dict(raw)
            target_session_id = str(
                item.get("session_id")
                or item.get("sessionId")
                or source_session_id
            ).strip()
            if not target_session_id:
                continue
            item.setdefault("source_scope", "session")
            item.setdefault("source_session_id", source_session_id)
            bucket = out.setdefault(target_session_id, {})
            bucket[_safe_heartbeat_task_id(item, index)] = item
    return out


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


def apply_session_heartbeat_summary_rows(
    sessions: list[dict[str, Any]],
    *,
    project_id: str,
    heartbeat_runtime: Any,
    load_session_heartbeat_config: Callable[[dict[str, Any]], dict[str, Any]],
    heartbeat_summary_payload: Callable[[Any], Any],
) -> list[dict[str, Any]]:
    project_assigned_task_map_by_session = _build_project_assigned_heartbeat_task_map_by_session(
        project_id=project_id,
        heartbeat_runtime=heartbeat_runtime,
    )
    session_assigned_task_map_by_session = _build_session_assigned_heartbeat_task_map_by_session(
        project_id=project_id,
        heartbeat_runtime=heartbeat_runtime,
        load_session_heartbeat_config=load_session_heartbeat_config,
    )
    batch_summary_available = (
        project_assigned_task_map_by_session is not None
        and session_assigned_task_map_by_session is not None
    )
    rows: list[dict[str, Any]] = []
    for row in sessions:
        if not isinstance(row, dict):
            continue
        item = dict(row)
        session_id = str(
            item.get("id")
            or item.get("session_id")
            or item.get("sessionId")
            or ""
        ).strip()
        heartbeat_cfg = load_session_heartbeat_config(item)
        task_map = {}
        if batch_summary_available:
            task_map = dict(project_assigned_task_map_by_session.get(session_id) or {})
            task_map.update(session_assigned_task_map_by_session.get(session_id) or {})
            item["heartbeat_summary"] = _heartbeat_summary_from_task_map(task_map)
        else:
            item["heartbeat_summary"] = heartbeat_summary_payload(heartbeat_cfg)
        rows.append(item)
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
    enriched["task_tracking"] = build_session_task_tracking(
        session=enriched,
        store=store,
        project_id=project_id,
        session_id=session_id,
        runtime_state=runtime_state,
    )

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
    return attach_agent_display_fields(enriched)
