# -*- coding: utf-8 -*-

from __future__ import annotations

from typing import Any

from task_dashboard.runtime.realtime_session_events import build_resume_token, stable_projection_seq


def _safe_text(value: Any, max_len: int) -> str:
    text = "" if value is None else str(value)
    if len(text) > max_len:
        return text[: max_len - 1] + "…"
    return text


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _summary_item(session_detail: dict[str, Any], *, project_id: str, session_id: str) -> dict[str, Any]:
    latest = _dict(session_detail.get("latest_run_summary"))
    effective = _dict(session_detail.get("latest_effective_run_summary"))
    task_tracking = _dict(session_detail.get("task_tracking"))
    current_task = _dict(task_tracking.get("current_task_ref"))
    preview = _safe_text(
        effective.get("preview") or latest.get("preview") or session_detail.get("display_name"),
        500,
    ).strip()
    return {
        "item_id": f"session:{session_id}:summary",
        "entity_type": "session_summary",
        "source": "session_detail",
        "project_id": project_id,
        "session_id": session_id,
        "status": _safe_text(session_detail.get("session_display_state"), 40).strip(),
        "preview": preview,
        "run_id": _safe_text(latest.get("run_id") or effective.get("run_id"), 160).strip(),
        "current_task_ref": current_task,
    }


def build_active_session_projection(
    *,
    project_id: str,
    session_id: str,
    session_detail: dict[str, Any],
    history_lite_payload: dict[str, Any] | None = None,
    memo_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    pid = _safe_text(project_id, 160).strip()
    sid = _safe_text(session_id, 160).strip()
    history_items = [
        dict(item)
        for item in _list((history_lite_payload or {}).get("items"))
        if isinstance(item, dict)
    ]
    memo_summary = _dict((memo_payload or {}).get("memo_summary"))
    if not memo_summary:
        memo_summary = _dict(memo_payload)
    memo_items = []
    for memo in _list((memo_payload or {}).get("items")):
        if not isinstance(memo, dict):
            continue
        memo_id = _safe_text(memo.get("id"), 120).strip()
        memo_items.append(
            {
                "item_id": f"memo:{memo_id}" if memo_id else "",
                "entity_type": "memo",
                "source": "conversation_memos",
                "project_id": pid,
                "session_id": sid,
                "memo_id": memo_id,
                "preview": _safe_text(memo.get("text"), 500).strip(),
                "attachments": _list(memo.get("attachments")),
                "created_at": _safe_text(memo.get("createdAt"), 80).strip(),
                "updated_at": _safe_text(memo.get("updatedAt"), 80).strip(),
            }
        )
    items = [_summary_item(session_detail, project_id=pid, session_id=sid)] + history_items + memo_items
    seq_parts: list[Any] = [pid, sid, len(items)]
    for item in items:
        if isinstance(item, dict):
            seq_parts.extend(
                [
                    item.get("item_id"),
                    item.get("run_id"),
                    item.get("status"),
                    item.get("updated_at"),
                    item.get("preview"),
                ]
            )
    last_seq = stable_projection_seq(seq_parts)
    latest = _dict(session_detail.get("latest_run_summary"))
    effective = _dict(session_detail.get("latest_effective_run_summary"))
    runtime_state = _dict(session_detail.get("runtime_state"))
    try:
        memo_count = int(memo_summary.get("memo_count") if "memo_count" in memo_summary else (memo_payload or {}).get("count") or len(memo_items))
    except Exception:
        memo_count = len(memo_items)
    return {
        "version": "v1",
        "project_id": pid,
        "session_id": sid,
        "focused_session_only": True,
        "source": "runtime_active_projection",
        "order": "newest_first",
        "last_seq": last_seq,
        "resume_token": build_resume_token(sid, last_seq),
        "runtime_state": runtime_state,
        "latest_run_summary": latest,
        "latest_effective_run_summary": effective,
        "summary": {
            "display_state": _safe_text(session_detail.get("session_display_state"), 40).strip(),
            "display_reason": _safe_text(session_detail.get("session_display_reason"), 160).strip(),
            "latest_run_id": _safe_text(latest.get("run_id") or effective.get("run_id"), 160).strip(),
            "latest_status": _safe_text(latest.get("status") or effective.get("outcome_state"), 80).strip(),
            "latest_preview": _safe_text(effective.get("preview") or latest.get("preview"), 500).strip(),
            "history_lite_count": len(history_items),
            "memo_count": max(0, memo_count),
            "memo_updated_at": _safe_text(memo_summary.get("memo_updated_at") or memo_summary.get("updatedAt"), 80).strip(),
            "memo_has_items": bool(memo_summary.get("memo_has_items") or memo_count > 0),
            "memo_summary_source": _safe_text(memo_summary.get("memo_summary_source"), 80).strip(),
        },
        "items": items,
    }
