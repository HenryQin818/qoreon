# -*- coding: utf-8 -*-

from __future__ import annotations

import os
from typing import Any

from task_dashboard.runtime.conversation_memo_summary import (
    build_memo_summary_payload,
    load_memo_summaries,
    normalize_memo_summary,
)
from task_dashboard.runtime.session_task_tracking import (
    build_prefetched_session_run_map,
    build_session_task_tracking,
)


def _as_text(value: Any) -> str:
    return str(value or "").strip()


def _session_id_for_row(row: dict[str, Any]) -> str:
    return _as_text(row.get("id") or row.get("session_id") or row.get("sessionId"))


def _list_metrics_run_limit() -> int:
    raw = _as_text(os.environ.get("CCB_SESSION_LIST_METRICS_RUN_LIMIT"))
    if raw:
        try:
            return max(4, min(int(raw), 40))
        except Exception:
            pass
    return 12


def _task_key(row: dict[str, Any]) -> str:
    task_id = _as_text(row.get("task_id"))
    if task_id:
        return f"task_id::{task_id}"
    task_path = _as_text(row.get("task_path"))
    if task_path:
        return f"task_path::{task_path}"
    return ""


def _task_status_bucket(row: dict[str, Any]) -> str:
    status = _as_text(
        row.get("task_primary_status")
        or row.get("status")
        or row.get("latest_action_kind")
    ).lower()
    if not status:
        return "other"
    if any(token in status for token in ("阻塞", "blocked", "block", "error", "failed")):
        return "blocked"
    if any(token in status for token in ("暂停", "暂缓", "paused", "pause")):
        return "paused"
    if any(token in status for token in ("已完成", "完成", "归档", "done", "closed", "success")):
        return "done"
    if any(token in status for token in ("进行中", "处理中", "running", "in_progress", "active", "start", "update")):
        return "in_progress"
    if any(token in status for token in ("待开始", "待处理", "待办", "待验收", "pending", "todo", "review", "acceptance", "queued", "confirm")):
        return "pending"
    return "other"


def _task_summary(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(row, dict):
        return None
    task_id = _as_text(row.get("task_id"))
    task_path = _as_text(row.get("task_path"))
    if not (task_id or task_path):
        return None
    return {
        "task_id": task_id,
        "parent_task_id": _as_text(row.get("parent_task_id")),
        "task_path": task_path,
        "task_title": _as_text(row.get("task_title")),
        "task_primary_status": _as_text(row.get("task_primary_status")),
        "status_bucket": _task_status_bucket(row),
        "task_summary_text": _as_text(row.get("task_summary_text")),
        "relation": _as_text(row.get("relation")),
        "source": _as_text(row.get("source")),
        "created_at": _as_text(row.get("created_at")),
        "due": _as_text(row.get("due")),
        "latest_action_at": _as_text(row.get("latest_action_at")),
        "latest_action_kind": _as_text(row.get("latest_action_kind")),
        "latest_action_text": _as_text(row.get("latest_action_text")),
        "next_owner_state": _as_text((row.get("next_owner") or {}).get("state")) if isinstance(row.get("next_owner"), dict) else "",
    }


def _tracking_rows(task_tracking: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    current = task_tracking.get("current_task_ref")
    if isinstance(current, dict):
        key = _task_key(current)
        if key:
            seen.add(key)
        rows.append(dict(current))
    for raw in task_tracking.get("conversation_task_refs") or []:
        if not isinstance(raw, dict):
            continue
        key = _task_key(raw)
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        rows.append(dict(raw))
    return rows


def _task_counts(rows: list[dict[str, Any]], current_summary: dict[str, Any] | None) -> dict[str, int]:
    counts = {
        "total": 0,
        "current": 1 if current_summary else 0,
        "in_progress": 0,
        "pending": 0,
        "done": 0,
        "blocked": 0,
        "paused": 0,
        "other": 0,
    }
    for row in rows:
        bucket = _task_status_bucket(row)
        counts["total"] += 1
        if bucket not in counts:
            bucket = "other"
        counts[bucket] += 1
    return counts


def _badge(kind: str, state: str, label: str, *, count: int | None = None, severity: str = "neutral") -> dict[str, Any]:
    item: dict[str, Any] = {
        "kind": kind,
        "state": state,
        "label": label,
        "severity": severity,
    }
    if count is not None:
        item["count"] = int(count)
    return item


def _session_state_badge(session: dict[str, Any]) -> dict[str, Any] | None:
    runtime_state = session.get("runtime_state") if isinstance(session.get("runtime_state"), dict) else {}
    state = _as_text(session.get("session_display_state") or runtime_state.get("display_state"))
    if not state:
        return None
    labels = {
        "running": "运行中",
        "queued": "排队",
        "retry_waiting": "等待重试",
        "external_busy": "外部占用",
        "error": "异常",
        "done": "完成",
        "idle": "空闲",
    }
    severities = {
        "running": "info",
        "queued": "warning",
        "retry_waiting": "warning",
        "external_busy": "warning",
        "error": "danger",
        "done": "success",
        "idle": "neutral",
    }
    return _badge("session_state", state, labels.get(state, state), severity=severities.get(state, "neutral"))


def _status_badges(
    session: dict[str, Any],
    counts: dict[str, int],
    current_summary: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    badges: list[dict[str, Any]] = []
    session_badge = _session_state_badge(session)
    if session_badge:
        badges.append(session_badge)
    if current_summary:
        status = _as_text(current_summary.get("task_primary_status")) or _as_text(current_summary.get("status_bucket"))
        if status:
            badges.append(_badge("current_task", _as_text(current_summary.get("status_bucket")), status, severity="info"))
    if counts.get("in_progress", 0) > 0:
        badges.append(_badge("task_count", "in_progress", f"中{counts['in_progress']}", count=counts["in_progress"], severity="info"))
    if counts.get("pending", 0) > 0:
        badges.append(_badge("task_count", "pending", f"待{counts['pending']}", count=counts["pending"], severity="warning"))
    if counts.get("blocked", 0) > 0:
        badges.append(_badge("task_count", "blocked", f"阻{counts['blocked']}", count=counts["blocked"], severity="danger"))
    return badges


def build_conversation_list_metrics(
    session: dict[str, Any],
    task_tracking: dict[str, Any] | None,
    *,
    source: str = "",
    memo_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    tracking = task_tracking if isinstance(task_tracking, dict) else {}
    current_summary = _task_summary(tracking.get("current_task_ref") if isinstance(tracking, dict) else None)
    rows = _tracking_rows(tracking)
    counts = _task_counts(rows, current_summary)
    has_tracking_source = bool(tracking)
    session_id = _session_id_for_row(session)
    memo = normalize_memo_summary(
        memo_summary,
        project_id=_as_text(session.get("project_id")),
        session_id=session_id,
    )
    return {
        "version": "v1",
        "source": _as_text(source) or ("task_tracking" if has_tracking_source else "none"),
        "updated_at": _as_text(tracking.get("updated_at")) if isinstance(tracking, dict) else "",
        "task_counts": counts,
        "current_task_summary": current_summary,
        "status_badges": _status_badges(session, counts, current_summary),
        "memo_count": int(memo.get("memo_count") or 0),
        "memo_updated_at": _as_text(memo.get("memo_updated_at")),
        "memo_has_items": bool(memo.get("memo_has_items")),
        "memo_summary_source": _as_text(memo.get("memo_summary_source")),
        "memo_summary": memo,
        "detail_hydration": {
            "can_skip_detail_for_list": bool(has_tracking_source),
            "requires_detail_for_counts": not bool(has_tracking_source),
            "covered_fields": [
                "task_counts",
                "current_task_summary",
                "status_badges",
                "memo_summary",
            ],
            "detail_required_for": [
                "full_task_tracking",
                "recent_task_actions",
                "task_assistant",
                "conversation_history",
            ],
        },
    }


def apply_session_conversation_list_metrics_rows(
    sessions: list[dict[str, Any]],
    *,
    project_id: str = "",
    store: Any = None,
    session_store: Any = None,
    heartbeat_runtime: Any = None,
    conversation_memo_store: Any = None,
    build_tracking_if_missing: bool = False,
) -> list[dict[str, Any]]:
    pid = _as_text(project_id)
    can_build_tracking = (
        bool(build_tracking_if_missing)
        and bool(pid)
        and callable(getattr(store, "list_runs", None))
    )
    run_limit = _list_metrics_run_limit()
    prefetched_runs_by_session: dict[str, list[dict[str, Any]]] = {}
    if can_build_tracking:
        session_ids = [
            _session_id_for_row(row)
            for row in sessions
            if isinstance(row, dict) and _session_id_for_row(row)
        ]
        try:
            prefetched_runs_by_session = build_prefetched_session_run_map(
                store=store,
                project_id=pid,
                session_ids=session_ids,
                per_session_limit=run_limit,
            )
        except Exception:
            prefetched_runs_by_session = {}
            can_build_tracking = False

    memo_summaries: dict[str, dict[str, Any]] = {}
    session_ids_for_memos = [
        _session_id_for_row(row)
        for row in sessions
        if isinstance(row, dict) and _session_id_for_row(row)
    ]
    if pid and session_ids_for_memos:
        memo_summaries = load_memo_summaries(
            conversation_memo_store,
            project_id=pid,
            session_ids=session_ids_for_memos,
        )

    rows: list[dict[str, Any]] = []
    for row in sessions:
        if not isinstance(row, dict):
            continue
        item = dict(row)
        session_id = _session_id_for_row(item)
        memo_summary = memo_summaries.get(session_id) or build_memo_summary_payload(
            project_id=pid,
            session_id=session_id,
            memo_summary_source="unavailable",
            delivery_mode="unavailable",
        )
        item["memo_summary"] = memo_summary
        tracking = item.get("task_tracking") if isinstance(item.get("task_tracking"), dict) else None
        source = "task_tracking" if tracking else "none"
        if tracking is None and can_build_tracking:
            session_id = _session_id_for_row(item)
            runtime_state = dict(item.get("runtime_state") or {}) if isinstance(item.get("runtime_state"), dict) else {}
            try:
                tracking = build_session_task_tracking(
                    session=item,
                    store=store,
                    project_id=pid,
                    session_id=session_id,
                    runtime_state=runtime_state,
                    session_store=session_store,
                    heartbeat_runtime=heartbeat_runtime,
                    run_limit=run_limit,
                    runs=prefetched_runs_by_session.get(session_id),
                )
                source = "task_tracking_light"
            except Exception:
                tracking = None
                source = "none"
        item["conversation_list_metrics"] = build_conversation_list_metrics(
            item,
            tracking,
            source=source,
            memo_summary=memo_summary,
        )
        rows.append(item)
    return rows
