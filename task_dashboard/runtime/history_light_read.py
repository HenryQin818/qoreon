# -*- coding: utf-8 -*-

from __future__ import annotations

from typing import Any, Callable
from urllib.parse import parse_qs, quote

from task_dashboard.runtime.conversation_memo_summary import load_memo_summary


def _safe_text(value: Any, max_len: int) -> str:
    text = "" if value is None else str(value)
    if len(text) > max_len:
        return text[: max_len - 1] + "…"
    return text


def _first_text(values: list[Any], max_len: int = 500) -> str:
    for value in values:
        text = _safe_text(value, max_len).strip()
        if text:
            return text
    return ""


def _coerce_limit(value: Any, default: int = 20) -> int:
    try:
        return max(1, min(int(value or default), 50))
    except Exception:
        return default


def build_history_light_item(row: dict[str, Any], *, project_id: str, session_id: str) -> dict[str, Any]:
    run_id = _safe_text(row.get("id"), 160).strip()
    status = _safe_text(row.get("status"), 40).strip()
    message_preview = _first_text([row.get("messagePreview"), row.get("latestUserMsg")], 500)
    response_preview = _first_text(
        [
            row.get("lastPreview"),
            row.get("partialPreview"),
            row.get("latestAiMsg"),
            row.get("error"),
        ],
        500,
    )
    preview = _first_text([response_preview, message_preview, row.get("error")], 500)
    created_at = _safe_text(row.get("createdAt"), 80).strip()
    updated_at = _first_text([row.get("finishedAt"), row.get("startedAt"), row.get("createdAt")], 80)
    return {
        "item_id": f"run:{run_id}" if run_id else "",
        "entity_type": "run_message",
        "source": "run_store",
        "project_id": _safe_text(project_id, 160).strip(),
        "session_id": _safe_text(session_id, 160).strip(),
        "run_id": run_id,
        "status": status,
        "message_preview": message_preview,
        "response_preview": response_preview,
        "preview": preview,
        "created_at": created_at,
        "updated_at": updated_at,
        "detail_url": f"/api/codex/run/{quote(run_id)}" if run_id else "",
        "session_detail_url": (
            f"/api/sessions/{quote(_safe_text(session_id, 160).strip())}"
            f"?project_id={quote(_safe_text(project_id, 160).strip())}"
        ),
        "has_more_detail": bool(run_id),
        "delivery_mode": "history_lite",
    }


def history_light_read_response(
    *,
    query_string: str,
    session_id: str,
    session_store: Any,
    store: Any,
    infer_project_id_for_session: Callable[[Any, str], str],
    conversation_memo_store: Any = None,
) -> tuple[int, dict[str, Any]]:
    qs = parse_qs(query_string or "")
    sid = _safe_text(session_id, 160).strip()
    project_id = _first_text([qs.get("project_id", [""])[0], qs.get("projectId", [""])[0]], 160)
    session = session_store.get_session(sid, project_id=project_id) if project_id else session_store.get_session(sid)
    if not session:
        return 404, {"error": "session not found"}
    project_id = project_id or _safe_text(session.get("project_id"), 160).strip() or infer_project_id_for_session(store, sid)
    limit = _coerce_limit(_first_text([qs.get("limit", [""])[0]], 20), default=20)
    cursor = _first_text([qs.get("cursor", [""])[0]], 200)
    try:
        rows = store.list_runs(
            project_id=project_id,
            session_id=sid,
            limit=limit,
            payload_mode="light",
        )
    except Exception:
        rows = []
    items = [
        build_history_light_item(row, project_id=project_id, session_id=sid)
        for row in rows
        if isinstance(row, dict)
    ]
    memo_summary = load_memo_summary(
        conversation_memo_store,
        project_id=project_id,
        session_id=sid,
    )
    return 200, {
        "ok": True,
        "version": "v1",
        "project_id": project_id,
        "session_id": sid,
        "cursor": cursor,
        "next_cursor": "",
        "count": len(items),
        "items": items,
        "memo_summary": memo_summary,
        "active_path_runtime": {
            "scope": "history_lite",
            "delivery_mode": "direct_http_light_read",
            "completion_budget_ms": 1200,
            "detail_fallback": "run_detail",
            "focused_session_only": True,
            "message_consistency_version": "v1",
        },
    }
