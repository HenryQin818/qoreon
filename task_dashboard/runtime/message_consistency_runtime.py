from __future__ import annotations

from typing import Any
from urllib.parse import quote


_ANNOUNCE_CONSISTENCY_VERSION = "v1"


def _safe_text(value: Any, max_len: int) -> str:
    text = "" if value is None else str(value)
    if len(text) > max_len:
        return text[: max_len - 1] + "…"
    return text


def _first_non_empty(values: list[Any], max_len: int = 500) -> str:
    for value in values:
        text = _safe_text(value, max_len).strip()
        if text:
            return text
    return ""


def _normalize_message_kind(value: Any) -> str:
    text = _safe_text(value, 80).strip().lower()
    if not text:
        return ""
    return text.replace("-", "_").replace(" ", "_")


def _stream_hint(
    *,
    project_id: str = "",
    session_id: str = "",
    after_seq: int = 0,
) -> dict[str, Any]:
    pid = _safe_text(project_id, 160).strip()
    sid = _safe_text(session_id, 160).strip()
    safe_seq = max(0, int(after_seq or 0))
    return {
        "version": _ANNOUNCE_CONSISTENCY_VERSION,
        "transport": "websocket",
        "focused_session_only": True,
        "session_id": sid,
        "after_seq": safe_seq,
        "bootstrap_url": f"/api/sessions/{quote(sid)}/active-bootstrap?project_id={quote(pid)}" if sid else "",
        "history_lite_url": f"/api/sessions/{quote(sid)}/history-lite?project_id={quote(pid)}" if sid else "",
        "fallback_http": f"/api/sessions/{quote(sid)}?project_id={quote(pid)}" if sid else "",
        "compat_mode": "additive_only",
    }


def _normalize_ref(value: Any) -> dict[str, str]:
    src = value if isinstance(value, dict) else {}
    project_id = _first_non_empty(
        [
            src.get("project_id"),
            src.get("projectId"),
        ],
        80,
    )
    channel_name = _first_non_empty(
        [
            src.get("channel_name"),
            src.get("channelName"),
        ],
        200,
    )
    session_id = _first_non_empty(
        [
            src.get("session_id"),
            src.get("sessionId"),
        ],
        80,
    )
    run_id = _first_non_empty(
        [
            src.get("run_id"),
            src.get("runId"),
        ],
        120,
    )
    out: dict[str, str] = {}
    if project_id:
        out["project_id"] = project_id
    if channel_name:
        out["channel_name"] = channel_name
    if session_id:
        out["session_id"] = session_id
    if run_id:
        out["run_id"] = run_id
    return out


def _parse_structured_message_fields(message: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw_line in str(message or "").splitlines():
        line = str(raw_line or "").strip()
        if not line:
            continue
        text = line
        if text.startswith("[") and text.endswith("]"):
            text = text[1:-1].strip()
        if "：" in text:
            key, value = text.split("：", 1)
        elif ":" in text:
            key, value = text.split(":", 1)
        else:
            continue
        clean_key = str(key or "").strip()
        clean_value = str(value or "").strip()
        if clean_key and clean_value and clean_key not in out:
            out[clean_key] = clean_value
    return out


def _looks_like_collab_announce(
    *,
    message_kind: str,
    sender_type: str,
    source_ref: dict[str, str],
    target_ref: dict[str, str],
    callback_to: dict[str, str],
    interaction_mode: str,
    message_fields: dict[str, str],
) -> bool:
    if message_kind in {"collab_update", "manual_update", "system_callback"}:
        return True
    if interaction_mode == "task_with_receipt":
        return True
    if sender_type in {"agent", "system"} and (source_ref or target_ref or callback_to):
        return True
    return any(
        key in message_fields
        for key in (
            "回执任务",
            "执行阶段",
            "本次目标",
            "当前结论",
            "需要对方",
            "预期结果",
        )
    )


def build_announce_run_consistency_meta(
    *,
    project_id: str,
    channel_name: str,
    session_id: str,
    message: str,
    message_kind: str,
    sender_type: str,
    run_extra_fields: dict[str, Any] | None,
) -> dict[str, Any]:
    extra = dict(run_extra_fields or {})
    source_ref = _normalize_ref(extra.get("source_ref"))
    target_ref = _normalize_ref(extra.get("target_ref"))
    callback_to = _normalize_ref(extra.get("callback_to"))
    route_resolution = extra.get("route_resolution") if isinstance(extra.get("route_resolution"), dict) else None
    interaction_mode = _normalize_message_kind(extra.get("interaction_mode"))
    message_fields = _parse_structured_message_fields(message)
    normalized_kind = _normalize_message_kind(message_kind)
    normalized_sender_type = _normalize_message_kind(sender_type) or "legacy"

    if not target_ref:
        target_ref = {
            "project_id": str(project_id or "").strip(),
            "channel_name": str(channel_name or "").strip(),
            "session_id": str(session_id or "").strip(),
        }

    if not _looks_like_collab_announce(
        message_kind=normalized_kind,
        sender_type=normalized_sender_type,
        source_ref=source_ref,
        target_ref=target_ref,
        callback_to=callback_to,
        interaction_mode=interaction_mode,
        message_fields=message_fields,
    ):
        return {}

    communication_view: dict[str, Any] = {
        "version": _ANNOUNCE_CONSISTENCY_VERSION,
        "event_reason": "unverified",
        "dispatch_state": "pending",
    }
    if normalized_kind:
        communication_view["message_kind"] = normalized_kind
    if source_ref.get("project_id"):
        communication_view["source_project_id"] = source_ref["project_id"]
    if source_ref.get("channel_name"):
        communication_view["source_channel"] = source_ref["channel_name"]
    if source_ref.get("session_id"):
        communication_view["source_session_id"] = source_ref["session_id"]
    if target_ref.get("project_id"):
        communication_view["target_project_id"] = target_ref["project_id"]
    if target_ref.get("channel_name"):
        communication_view["target_channel"] = target_ref["channel_name"]
    if target_ref.get("session_id"):
        communication_view["target_session_id"] = target_ref["session_id"]
    if route_resolution:
        communication_view["route_resolution"] = route_resolution

    summary: dict[str, Any] = {
        "version": _ANNOUNCE_CONSISTENCY_VERSION,
    }
    if normalized_kind:
        summary["message_kind"] = normalized_kind
    if source_ref.get("project_id"):
        summary["source_project_id"] = source_ref["project_id"]
    if source_ref.get("session_id"):
        summary["source_session_id"] = source_ref["session_id"]
    if target_ref.get("project_id"):
        summary["target_project_id"] = target_ref["project_id"]
    if target_ref.get("channel_name"):
        summary["target_channel"] = target_ref["channel_name"]
    if target_ref.get("session_id"):
        summary["target_session_id"] = target_ref["session_id"]

    source_channel = _first_non_empty(
        [
            message_fields.get("来源通道"),
            source_ref.get("channel_name"),
        ],
        200,
    )
    if source_channel:
        summary["source_channel"] = source_channel

    callback_task = _first_non_empty(
        [
            message_fields.get("回执任务"),
            extra.get("task_path"),
            extra.get("task_id"),
            extra.get("topic"),
        ],
        1200,
    )
    if callback_task:
        summary["callback_task"] = callback_task

    execution_stage = _first_non_empty(
        [
            message_fields.get("执行阶段"),
            extra.get("execution_stage"),
        ],
        40,
    )
    if execution_stage:
        summary["execution_stage"] = execution_stage

    goal = _first_non_empty(
        [
            message_fields.get("本次目标"),
            message_fields.get("通知事项"),
        ],
        300,
    )
    if goal:
        summary["goal"] = goal

    conclusion = _first_non_empty(
        [
            message_fields.get("当前结论"),
            extra.get("current_conclusion"),
        ],
        120,
    )
    if conclusion:
        summary["conclusion"] = conclusion

    progress = _first_non_empty(
        [
            message_fields.get("目标进展"),
        ],
        300,
    )
    if progress:
        summary["progress"] = progress

    need_peer = _first_non_empty(
        [
            message_fields.get("需要对方"),
        ],
        260,
    )
    if need_peer:
        summary["need_peer"] = need_peer

    expected_result = _first_non_empty(
        [
            message_fields.get("预期结果"),
        ],
        260,
    )
    if expected_result:
        summary["expected_result"] = expected_result

    need_confirm = _first_non_empty(
        [
            message_fields.get("需确认"),
            extra.get("need_confirmation"),
        ],
        200,
    )
    if need_confirm:
        summary["need_confirm"] = need_confirm

    headline = _first_non_empty(
        [
            callback_task,
            conclusion,
            goal,
        ],
        200,
    )
    if headline:
        summary["headline"] = headline

    if route_resolution:
        summary["technical"] = {
            "route_resolution": route_resolution,
        }

    out: dict[str, Any] = {}
    if communication_view:
        out["communication_view"] = communication_view
    if len(summary) > 1:
        out["receipt_summary"] = summary
    return out


def build_announce_active_path_runtime(
    *,
    run: dict[str, Any],
    ack_budget_ms: int,
    readback_budget_ms: int,
    processing_state: str,
    feedback_strategy: str,
    accepted_at: str,
) -> dict[str, Any]:
    summary = run.get("receipt_summary") if isinstance(run.get("receipt_summary"), dict) else {}
    communication_view = run.get("communication_view") if isinstance(run.get("communication_view"), dict) else {}
    session_id = _safe_text(run.get("sessionId") or run.get("session_id"), 160).strip()
    project_id = _safe_text(run.get("projectId") or run.get("project_id"), 160).strip()
    run_id = _safe_text(run.get("id"), 160).strip()
    return {
        "scope": "announce_send",
        "delivery_mode": "accepted_queued",
        "ack_budget_ms": int(ack_budget_ms or 250),
        "readback_budget_ms": int(readback_budget_ms or 1200),
        "processing_state": str(processing_state or run.get("status") or "queued"),
        "feedback_strategy": str(feedback_strategy or "optimistic_then_readback"),
        "accepted_at": str(accepted_at or ""),
        "confirmation_state": "accepted",
        "message_consistency_version": _ANNOUNCE_CONSISTENCY_VERSION,
        "completion_hint_mode": "receipt_summary_readback" if summary else "run_status_readback",
        "communication_view_ready": bool(communication_view),
        "receipt_summary_ready": bool(summary),
        "client_message_id": _safe_text(run.get("client_message_id") or run.get("clientMessageId"), 160).strip(),
        "completion_target": "receipt_summary" if summary else "run_terminal",
        "stream_identity": {
            "project_id": project_id,
            "session_id": session_id,
            "run_id": run_id,
            "entity_type": "run_receipt",
        },
        "stream_hint": _stream_hint(project_id=project_id, session_id=session_id),
    }


def build_message_consistency_hints(
    *,
    send_ack_budget_ms: int,
    send_readback_budget_ms: int,
    session_detail_budget_ms: int,
    conversation_memos_budget_ms: int,
    attachment_ack_budget_ms: int,
    attachment_placeholder_mode: str,
) -> dict[str, Any]:
    return {
        "version": _ANNOUNCE_CONSISTENCY_VERSION,
        "send_confirmation_budget_ms": int(send_ack_budget_ms or 0),
        "completion_convergence_budget_ms": int(send_readback_budget_ms or 0),
        "active_session_detail_budget_ms": int(session_detail_budget_ms or 0),
        "conversation_memos_budget_ms": int(conversation_memos_budget_ms or 0),
        "attachment_ack_budget_ms": int(attachment_ack_budget_ms or 0),
        "attachment_placeholder_mode": str(attachment_placeholder_mode or "client_preview_immediate"),
        "stream_bridge": {
            "transport": "websocket",
            "focused_session_only": True,
            "active_bootstrap_endpoint": "/api/sessions/{session_id}/active-bootstrap",
            "history_lite_endpoint": "/api/sessions/{session_id}/history-lite",
            "gateway_endpoint": "/api/ws/sessions",
            "fallback": "http_light_read",
            "compat_mode": "additive_only",
        },
    }


def build_attachment_confirmation_payload(
    *,
    url: str,
    mime_type: str,
    ack_budget_ms: int,
) -> dict[str, Any]:
    normalized_mime = str(mime_type or "").strip() or "application/octet-stream"
    return {
        "version": _ANNOUNCE_CONSISTENCY_VERSION,
        "state": "uploaded",
        "confirm_via": "uploaded_url",
        "attachment_url": str(url or "").strip(),
        "mime_type": normalized_mime,
        "preview_mode": "client_preview_immediate" if normalized_mime.startswith("image/") else "attachment_chip_immediate",
        "ack_budget_ms": int(ack_budget_ms or 300),
        "local_attachment_id": "",
        "stream_hint": _stream_hint(),
        "preview_url": str(url or "").strip(),
    }


def build_conversation_memo_write_runtime(*, count: int) -> dict[str, Any]:
    return {
        "scope": "conversation_memo_write",
        "delivery_mode": "memory_write_through",
        "confirmation_state": "accepted",
        "message_consistency_version": _ANNOUNCE_CONSISTENCY_VERSION,
        "count_after_write": int(max(0, int(count or 0))),
        "readback_budget_ms": 800,
    }


def build_conversation_memo_read_runtime(
    *,
    delivery_mode: str,
    cache_ttl_ms: int,
    completion_budget_ms: int,
    cache_age_ms: int,
) -> dict[str, Any]:
    return {
        "scope": "conversation_memos",
        "delivery_mode": str(delivery_mode or "fresh_disk"),
        "delivery_strategy": "memory_ttl",
        "cache_ttl_ms": int(cache_ttl_ms or 0),
        "completion_budget_ms": int(completion_budget_ms or 0),
        "cache_age_ms": int(cache_age_ms or 0),
        "read_scope": "active_session_light",
        "message_consistency_version": _ANNOUNCE_CONSISTENCY_VERSION,
    }
