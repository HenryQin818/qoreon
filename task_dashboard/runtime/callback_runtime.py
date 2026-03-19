# -*- coding: utf-8 -*-

from __future__ import annotations

import os
import threading
import time
from contextlib import nullcontext
from pathlib import Path
from typing import Any, Optional

from task_dashboard.helpers import (
    looks_like_uuid as _looks_like_uuid,
    now_iso as _now_iso,
    parse_iso_ts as _parse_iso_ts,
    safe_text as _safe_text,
)
from task_dashboard.runtime.callback_dispatch import (
    apply_callback_dispatch_views as runtime_apply_callback_dispatch_views,
    build_callback_dispatch_payloads as runtime_build_callback_dispatch_payloads,
    build_callback_run_extra_meta as runtime_build_callback_run_extra_meta,
)
from task_dashboard.session_store import SessionStore, session_binding_is_available

__all__ = [
    "_CALLBACK_ANCHOR_LOCK_GUARD",
    "_CALLBACK_ANCHOR_LOCKS",
    "_CALLBACK_WINDOW_LOCK",
    "_CALLBACK_WINDOWS",
    "_CALLBACK_DISPATCH_CLAIM_LOCK",
    "_CALLBACK_DISPATCH_INFLIGHT",
    "_append_source_callback_dispatch",
    "_build_callback_communication_view",
    "_build_callback_summary_message",
    "_build_callback_window_receipt_summary",
    "_build_terminal_callback_message",
    "_build_terminal_receipt_summary",
    "_callback_anchor_key",
    "_callback_anchor_mutex",
    "_callback_dispatch_key",
    "_callback_meta_bool",
    "_callback_meta_text",
    "_callback_progress_signature",
    "_callback_queue_aggregator_enabled",
    "_callback_summary_timer_key",
    "_callback_throttle_key",
    "_claim_callback_dispatch_key",
    "_classify_terminal_callback_event",
    "_default_callback_anchor_max_merges",
    "_default_callback_anchor_scan_limit",
    "_default_callback_conclusion",
    "_default_callback_next_step",
    "_default_callback_summary_window_s",
    "_dispatch_terminal_callback_for_run",
    "_extract_callback_progress_profile",
    "_flush_callback_summary_window",
    "_inspect_callback_task_activity",
    "_is_callback_auto_run",
    "_iter_callback_anchor_candidates",
    "_merge_callback_into_anchor",
    "_register_callback_window",
    "_release_callback_dispatch_key",
    "_render_receipt_summary_message",
    "_resolve_callback_target_cli_type",
    "_resolve_callback_target_for_run",
    "_resolve_master_control_target",
    "_resolve_primary_target_by_channel",
    "_resolve_source_channel_text",
    "_source_callback_dispatch_run_id",
    "_source_has_callback_dispatch",
    "_source_run_callback_eligible",
    "_try_merge_callback_into_queue_anchor",
]


def __getattr__(name: str):
    import server

    try:
        return getattr(server, name)
    except AttributeError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc


def _server_override(name: str, local_fn: Any = None) -> Any:
    import server

    override = getattr(server, name, None)
    if override is None:
        return local_fn
    if local_fn is not None and override is local_fn:
        return local_fn
    return override


def _call_server_override(name: str, local_fn: Any, *args, **kwargs):
    fn = _server_override(name, local_fn)
    return fn(*args, **kwargs)


_CALLBACK_ANCHOR_LOCK_GUARD = threading.Lock()
_CALLBACK_ANCHOR_LOCKS: dict[str, threading.Lock] = {}
_CALLBACK_WINDOW_LOCK = threading.Lock()
_CALLBACK_WINDOWS: dict[str, dict[str, Any]] = {}
_CALLBACK_DISPATCH_CLAIM_LOCK = threading.Lock()
_CALLBACK_DISPATCH_INFLIGHT: set[str] = set()


def _normalize_message_ref_local(value: Any, *, allow_run_id: bool = False) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    out: dict[str, str] = {}
    project_id = _safe_text(value.get("project_id") if "project_id" in value else value.get("projectId"), 80).strip()
    channel_name = _safe_text(value.get("channel_name") if "channel_name" in value else value.get("channelName"), 200).strip()
    session_id = _safe_text(value.get("session_id") if "session_id" in value else value.get("sessionId"), 80).strip()
    run_id = _safe_text(value.get("run_id") if "run_id" in value else value.get("runId"), 80).strip()
    if project_id:
        out["project_id"] = project_id
    if channel_name:
        out["channel_name"] = channel_name
    if session_id:
        out["session_id"] = session_id
    if allow_run_id and run_id:
        out["run_id"] = run_id
    return out


def _callback_queue_aggregator_enabled() -> bool:
    raw = str(os.environ.get("CCB_CALLBACK_QUEUE_AGGREGATOR") or "").strip().lower()
    if raw in {"0", "false", "off", "no"}:
        return False
    return True


def _default_callback_anchor_max_merges() -> int:
    raw = str(os.environ.get("CCB_CALLBACK_ANCHOR_MAX_MERGES") or "").strip()
    if raw:
        try:
            value = int(raw)
            return max(10, min(value, 500))
        except Exception:
            pass
    return 120


def _default_callback_anchor_scan_limit() -> int:
    raw = str(os.environ.get("CCB_CALLBACK_ANCHOR_SCAN_LIMIT") or "").strip()
    if raw:
        try:
            value = int(raw)
            return max(20, min(value, 2000))
        except Exception:
            pass
    return 600


def _default_callback_summary_window_s() -> int:
    raw = str(os.environ.get("CCB_CALLBACK_SUMMARY_WINDOW_S") or "").strip()
    if raw:
        try:
            value = int(raw)
            return max(10, min(value, 3600))
        except Exception:
            pass
    return 600


def _callback_meta_text(meta: dict[str, Any], *keys: str) -> str:
    for key in keys:
        if key in meta:
            value = _safe_text(meta.get(key), 300).strip()
            if value:
                return value
    return ""


def _callback_meta_bool(meta: dict[str, Any], *keys: str) -> Optional[bool]:
    for key in keys:
        if key not in meta:
            continue
        value = meta.get(key)
        if isinstance(value, bool):
            return value
        text = str(value or "").strip().lower()
        if text in {"1", "true", "yes", "y", "on", "blocked", "阻塞"}:
            return True
        if text in {"0", "false", "no", "n", "off", "unblocked", "未阻塞"}:
            return False
    return None


def _default_callback_conclusion(event_type: str) -> str:
    event = str(event_type or "").strip().lower()
    if event == "done":
        return "已完成，可进入验收/收口"
    if event == "interrupted":
        return "已中断待恢复"
    if event == "error":
        return "执行异常，需处理"
    return "状态待确认"


def _default_callback_next_step(event_type: str) -> str:
    event = str(event_type or "").strip().lower()
    if event == "done":
        return "请主负责确认是否转待验收或标记已完成。"
    if event == "interrupted":
        return "请判断是否补发“继续开展工作”并在恢复后回收结果。"
    if event == "error":
        return "请先查看日志并决定重试、回滚或转问题单。"
    return "请主负责确认下一步动作。"


def _resolve_source_channel_text(source_meta: dict[str, Any], receipt: Optional[dict[str, Any]] = None) -> str:
    rec = receipt if isinstance(receipt, dict) else {}
    for key in ("source_channel", "sourceChannel", "source_channel_name", "sourceChannelName"):
        text = _safe_text(rec.get(key), 200).strip()
        if text:
            return text

    for key in (
        "channelName",
        "channel_name",
        "source_channel",
        "sourceChannel",
        "source_channel_name",
        "sourceChannelName",
    ):
        text = _safe_text(source_meta.get(key), 200).strip()
        if text:
            return text

    communication_view = source_meta.get("communication_view")
    if isinstance(communication_view, dict):
        text = _safe_text(communication_view.get("source_channel"), 200).strip()
        if text:
            return text

    route_resolution = source_meta.get("route_resolution")
    if isinstance(route_resolution, dict):
        text = _safe_text(route_resolution.get("source_channel_name"), 200).strip()
        if text:
            return text
    return ""


def _resolve_source_agent_text(source_meta: dict[str, Any], receipt: Optional[dict[str, Any]] = None) -> str:
    rec = receipt if isinstance(receipt, dict) else {}
    for key in ("source_agent_name", "sourceAgentName", "agent_name", "agentName", "sender_name", "senderName"):
        text = _safe_text(rec.get(key), 200).strip()
        if text:
            return text

    owner_ref = source_meta.get("owner_ref")
    if isinstance(owner_ref, dict):
        text = _safe_text(owner_ref.get("agent_name") or owner_ref.get("alias"), 200).strip()
        if text:
            return text

    sender_agent_ref = source_meta.get("sender_agent_ref")
    if isinstance(sender_agent_ref, dict):
        text = _safe_text(sender_agent_ref.get("alias") or sender_agent_ref.get("agent_name"), 200).strip()
        if text:
            return text

    for key in ("sender_name", "senderName", "agent_name", "agentName"):
        text = _safe_text(source_meta.get(key), 200).strip()
        if text:
            return text
    return ""


def _extract_callback_progress_profile(source_meta: dict[str, Any], event_type: str) -> dict[str, str]:
    receipt_summary = source_meta.get("receipt_summary")
    receipt = receipt_summary if isinstance(receipt_summary, dict) else {}
    source_channel = _resolve_source_channel_text(source_meta, receipt) or "未知通道"
    source_agent_name = _resolve_source_agent_text(source_meta, receipt)
    task_path = (
        _safe_text(receipt.get("callback_task"), 1200).strip()
        or _callback_meta_text(source_meta, "task_path", "taskPath")
        or "未关联任务"
    )
    topic = _callback_meta_text(
        source_meta,
        "callback_topic",
        "callbackTopic",
        "receipt_topic",
        "receiptTopic",
    )
    if not topic:
        topic = event_type or "event"
    stage = _safe_text(receipt.get("execution_stage"), 40).strip() or _callback_meta_text(
        source_meta,
        "execution_stage",
        "executionStage",
        "progress_stage",
        "progressStage",
        "stage",
        "执行阶段",
    )
    if not stage:
        stage = event_type or "unknown"
    blocked = _callback_meta_bool(
        source_meta,
        "blocking_status",
        "blockingStatus",
        "blocked",
        "is_blocked",
        "isBlocked",
        "阻塞",
    )
    if blocked is None:
        blocked_text = _callback_meta_text(source_meta, "blocking_reason", "blockingReason", "阻塞原因")
        blocking_status = "blocked" if blocked_text else "unblocked"
    else:
        blocking_status = "blocked" if blocked else "unblocked"
    current_conclusion = _safe_text(receipt.get("conclusion"), 200).strip() or _callback_meta_text(
        source_meta,
        "current_conclusion",
        "currentConclusion",
        "conclusion",
        "当前结论",
    ) or _default_callback_conclusion(event_type)
    need_confirmation = _safe_text(receipt.get("need_confirm"), 200).strip() or _callback_meta_text(
        source_meta,
        "need_confirmation",
        "needConfirmation",
        "need_confirm",
        "needConfirm",
        "需确认",
        "需主负责确认",
        "需总控确认",
    ) or "无"
    next_step = _safe_text(receipt.get("need_peer"), 200).strip() or _callback_meta_text(
        source_meta,
        "next_action",
        "nextAction",
        "需要对方",
    ) or _default_callback_next_step(event_type)
    return {
        "source_channel": source_channel,
        "source_agent_name": _safe_text(source_agent_name, 200).strip(),
        "task_path": task_path,
        "topic": _safe_text(topic, 120).strip().lower() or "event",
        "stage": _safe_text(stage, 80).strip().lower() or "unknown",
        "blocking_status": _safe_text(blocking_status, 20).strip().lower() or "unblocked",
        "current_conclusion": _safe_text(current_conclusion, 200).strip(),
        "need_confirmation": _safe_text(need_confirmation, 200).strip(),
        "next_step": _safe_text(next_step, 200).strip(),
    }


def _callback_progress_signature(profile: dict[str, str]) -> tuple[str, str, str, str]:
    return (
        str(profile.get("stage") or "").strip().lower(),
        str(profile.get("blocking_status") or "").strip().lower(),
        str(profile.get("current_conclusion") or "").strip(),
        str(profile.get("need_confirmation") or "").strip(),
    )


def _callback_throttle_key(
    project_id: str,
    source_channel: str,
    task_path: str,
    topic: str,
    stage: str,
) -> str:
    return "||".join(
        [
            str(project_id or "").strip(),
            str(source_channel or "").strip(),
            str(task_path or "").strip(),
            str(topic or "").strip().lower(),
            str(stage or "").strip().lower(),
        ]
    )


def _callback_anchor_key(
    *,
    project_id: str,
    target_channel: str,
    target_session_id: str,
    event_type: str,
    profile: dict[str, str],
) -> str:
    return "||".join(
        [
            str(project_id or "").strip(),
            str(target_channel or "").strip(),
            str(target_session_id or "").strip(),
            "queue_anchor_v3",
        ]
    )


def _iter_callback_anchor_candidates(
    store,
    *,
    project_id: str,
    target_channel: str,
    target_session_id: str,
    event_type: str,
    anchor_key: str,
    profile: dict[str, str],
) -> list[tuple[float, str, dict[str, Any]]]:
    metas = store.list_runs(
        project_id=project_id,
        session_id=target_session_id,
        limit=_default_callback_anchor_scan_limit(),
        include_payload=False,
    )
    out: list[tuple[float, str, dict[str, Any]]] = []
    for meta in metas:
        if not isinstance(meta, dict):
            continue
        if bool(meta.get("hidden")):
            continue
        run_id = str(meta.get("id") or "").strip()
        if not run_id:
            continue
        status = str(meta.get("status") or "").strip().lower()
        if status not in {"queued", "retry_waiting"}:
            continue
        if str(meta.get("channelName") or "").strip() != str(target_channel or "").strip():
            continue
        trigger_type = str(meta.get("trigger_type") or "").strip().lower()
        if trigger_type != "callback_auto":
            continue
        created_ts = _parse_iso_ts(meta.get("createdAt")) or _parse_iso_ts(meta.get("startedAt")) or 0.0
        out.append((created_ts, run_id, meta))
    out.sort(key=lambda item: (item[0], item[1]))
    return out


def _merge_callback_into_anchor(
    store,
    *,
    anchor_run_id: str,
    source_meta: dict[str, Any],
    anchor_key: str,
    merged_message: str,
) -> tuple[bool, dict[str, Any], str]:
    run_id = str(anchor_run_id or "").strip()
    if not run_id:
        return False, {}, "anchor_missing"
    anchor_meta = store.load_meta(run_id) or {}
    if not isinstance(anchor_meta, dict):
        return False, {}, "anchor_not_found"
    status = str(anchor_meta.get("status") or "").strip().lower()
    if status not in {"queued", "retry_waiting"}:
        return False, {}, "anchor_not_queueable"
    now_iso = _now_iso()
    source_run_id = str(source_meta.get("id") or "").strip()
    if not source_run_id:
        return False, {}, "source_run_id_missing"

    base_ids: list[str] = []
    anchor_source = str(anchor_meta.get("source_run_id") or "").strip()
    if anchor_source:
        base_ids.append(anchor_source)
    for key in ("callback_aggregate_source_run_ids", "callback_summary_of"):
        rows = anchor_meta.get(key)
        for row in rows if isinstance(rows, list) else []:
            text = str(row or "").strip()
            if text and text not in base_ids:
                base_ids.append(text)
    added = False
    if source_run_id not in base_ids:
        base_ids.append(source_run_id)
        added = True

    prev_count = int(anchor_meta.get("callback_aggregate_count") or 0)
    if prev_count <= 0:
        prev_count = max(1, len(base_ids) - (1 if added else 0))
    new_count = prev_count + (1 if added else 0)

    anchor_meta["callback_anchor_key"] = str(anchor_key or "").strip()
    anchor_meta["callback_aggregate_count"] = int(max(1, new_count))
    anchor_meta["callback_last_merged_at"] = now_iso
    anchor_meta["callback_aggregate_source_run_ids"] = base_ids[:120]
    anchor_meta["callback_summary_of"] = base_ids[:50]
    anchor_meta["callback_merge_mode"] = "queue_anchor_v2"

    summary = anchor_meta.get("receipt_summary")
    summary_obj = dict(summary) if isinstance(summary, dict) else {}
    if summary_obj:
        technical = summary_obj.get("technical")
        technical_obj = dict(technical) if isinstance(technical, dict) else {}
        technical_obj["source_run_ids"] = base_ids[:120]
        technical_obj["anchor_run_id"] = run_id
        technical_obj["trigger_type"] = str(
            technical_obj.get("trigger_type") or anchor_meta.get("trigger_type") or "callback_auto"
        )
        summary_obj["technical"] = technical_obj
        anchor_meta["receipt_summary"] = summary_obj

    try:
        merged_text = str(merged_message or "").strip()
        if merged_text:
            append_block = (
                "\n\n---\n"
                f"[并入回执] source_run_id={source_run_id} merged_at={now_iso}\n\n"
                f"{merged_text}\n"
            )
            store.append_msg(run_id, append_block)
        store.save_meta(run_id, anchor_meta)
    except Exception as exc:
        return False, {}, f"anchor_save_failed:{type(exc).__name__}"
    return True, anchor_meta, ""


def _try_merge_callback_into_queue_anchor(
    store,
    *,
    source_meta: dict[str, Any],
    target: dict[str, str],
    event_type: str,
    profile: dict[str, str],
    merged_message: str,
) -> dict[str, Any]:
    project_id = str(source_meta.get("projectId") or "").strip()
    target_channel = str(target.get("channel_name") or "").strip()
    target_session_id = str(target.get("session_id") or "").strip()
    source_run_id = str(source_meta.get("id") or "").strip()
    if not (project_id and target_channel and target_session_id and source_run_id):
        return {"merged": False, "note": "no_anchor:invalid_context"}
    anchor_key = _callback_anchor_key(
        project_id=project_id,
        target_channel=target_channel,
        target_session_id=target_session_id,
        event_type=event_type,
        profile=profile,
    )
    candidates = _iter_callback_anchor_candidates(
        store,
        project_id=project_id,
        target_channel=target_channel,
        target_session_id=target_session_id,
        event_type=event_type,
        anchor_key=anchor_key,
        profile=profile,
    )
    if not candidates:
        return {"merged": False, "note": "no_anchor", "anchor_key": anchor_key}

    _, anchor_run_id, anchor_meta = candidates[0]
    max_merges = _default_callback_anchor_max_merges()
    current_count = int(anchor_meta.get("callback_aggregate_count") or 0)
    if current_count <= 0:
        rows = anchor_meta.get("callback_aggregate_source_run_ids")
        if isinstance(rows, list) and rows:
            current_count = len([str(item or "").strip() for item in rows if str(item or "").strip()])
        else:
            current_count = 1
    if current_count >= max_merges:
        return {
            "merged": False,
            "note": "anchor_overflow_new_anchor",
            "anchor_run_id": anchor_run_id,
            "anchor_key": anchor_key,
            "anchor_count": current_count,
        }

    ok, merged_meta, err = _call_server_override(
        "_merge_callback_into_anchor",
        _merge_callback_into_anchor,
        store,
        anchor_run_id=anchor_run_id,
        source_meta=source_meta,
        anchor_key=anchor_key,
        merged_message=merged_message,
    )
    if not ok:
        return {
            "merged": False,
            "note": f"merge_failed_new_anchor:{err or 'unknown'}",
            "anchor_run_id": anchor_run_id,
            "anchor_key": anchor_key,
        }
    return {
        "merged": True,
        "note": "merged_anchor",
        "anchor_run_id": anchor_run_id,
        "anchor_key": anchor_key,
        "aggregate_count": int(merged_meta.get("callback_aggregate_count") or 1),
        "last_merged_at": str(merged_meta.get("callback_last_merged_at") or ""),
    }


def _classify_terminal_callback_event(meta: dict[str, Any]) -> tuple[str, str]:
    status = str(meta.get("status") or "").strip().lower()
    if status == "done":
        return "done", ""
    if status != "error":
        return "", ""
    error = str(meta.get("error") or "").strip().lower()
    if not error:
        return "error", ""
    if "interrupted by user" in error:
        return "interrupted", "user_interrupt"
    if "run interrupted (server restarted or process exited)" in error:
        return "interrupted", "server_restart"
    if error.startswith("timeout>") or "timeout>" in error:
        return "interrupted", "timeout_interrupt"
    return "error", ""


def _is_callback_auto_run(meta: dict[str, Any]) -> bool:
    trigger_type = str(meta.get("trigger_type") or "").strip().lower()
    return trigger_type.startswith("callback_auto")


def _source_run_callback_eligible(meta: dict[str, Any]) -> bool:
    if not isinstance(meta, dict):
        return False
    if bool(meta.get("hidden")):
        return False
    if _is_callback_auto_run(meta):
        return False
    event_type, _ = _classify_terminal_callback_event(meta)
    if not event_type:
        return False
    if __getattr__("_normalize_callback_to")(meta.get("callback_to")):
        return True
    sender_type = str(meta.get("sender_type") or "").strip().lower()
    execution_mode = str(meta.get("execution_mode") or "").strip().lower()
    owner_channel = str(meta.get("owner_channel_name") or "").strip()
    task_path = str(meta.get("task_path") or "").strip()
    if sender_type == "agent":
        return True
    if execution_mode in {"managed", "supervised"}:
        return True
    if owner_channel:
        return True
    if sender_type == "system" and task_path:
        return True
    return False


def _resolve_primary_target_by_channel(project_id: str, channel_name: str) -> Optional[dict[str, str]]:
    channel = str(channel_name or "").strip()
    if not channel:
        return None
    try:
        session_store = SessionStore(__getattr__("_repo_root")())
        row = session_store.get_channel_default_session(project_id, channel)
    except Exception:
        row = None
    session_id = str((row or {}).get("id") or "").strip()
    if not session_id or not _looks_like_uuid(session_id):
        return None
    return {"channel_name": channel, "session_id": session_id}


def _resolve_master_control_target(project_id: str) -> Optional[dict[str, str]]:
    exact = _call_server_override(
        "_resolve_primary_target_by_channel",
        _resolve_primary_target_by_channel,
        project_id,
        "主体-总控（合并与验收）",
    )
    if exact:
        return exact
    try:
        session_store = SessionStore(__getattr__("_repo_root")())
        rows = session_store.list_sessions(project_id)
    except Exception:
        rows = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if not session_binding_is_available(row):
            continue
        channel_name = str(row.get("channel_name") or "").strip()
        session_id = str(row.get("id") or "").strip()
        if "主体-总控" in channel_name and session_id and _looks_like_uuid(session_id):
            return {"channel_name": channel_name, "session_id": session_id}
    return None


def _resolve_callback_target_for_run(meta: dict[str, Any]) -> tuple[Optional[dict[str, str]], dict[str, Any]]:
    project_id = str(meta.get("projectId") or "").strip()
    source_channel = str(meta.get("channelName") or "").strip()
    sender_type = str(meta.get("sender_type") or "").strip().lower()
    sender_id = str(meta.get("sender_id") or "").strip()
    original_cb = __getattr__("_normalize_callback_to")(meta.get("callback_to"))
    source_ref = _normalize_message_ref_local(meta.get("source_ref"), allow_run_id=True)
    owner_channel = str(meta.get("owner_channel_name") or "").strip()

    reasons: list[str] = []
    source = ""
    fallback_stage = "none"
    target: Optional[dict[str, str]] = None

    if original_cb:
        cb_sid = str(original_cb.get("session_id") or "").strip()
        cb_channel = str(original_cb.get("channel_name") or "").strip()
        if cb_sid and cb_channel:
            target = {"channel_name": cb_channel, "session_id": cb_sid}
            source = "callback_to"
        elif cb_channel:
            resolved = _call_server_override(
                "_resolve_primary_target_by_channel",
                _resolve_primary_target_by_channel,
                project_id,
                cb_channel,
            )
            if resolved:
                target = resolved
                source = "callback_to"
                fallback_stage = "callback_to_channel_primary"
                if not cb_sid:
                    reasons.append("callback_to_missing_session_id")
            else:
                reasons.append("callback_to_channel_unresolved")
        else:
            reasons.append("callback_to_invalid")

    if target is None and source_ref:
        source_ref_project_id = str(source_ref.get("project_id") or "").strip() or project_id
        source_ref_channel = str(source_ref.get("channel_name") or "").strip()
        source_ref_session_id = str(source_ref.get("session_id") or "").strip()
        if source_ref_project_id == project_id and source_ref_session_id and source_ref_channel:
            target = {
                "channel_name": source_ref_channel,
                "session_id": source_ref_session_id,
            }
            source = "source_ref"
            if original_cb:
                fallback_stage = "callback_to_to_source_ref"
        elif source_ref_project_id == project_id and source_ref_channel:
            resolved = _call_server_override(
                "_resolve_primary_target_by_channel",
                _resolve_primary_target_by_channel,
                project_id,
                source_ref_channel,
            )
            if resolved:
                target = resolved
                source = "source_ref"
                fallback_stage = "source_ref_channel_primary"
                if not source_ref_session_id:
                    reasons.append("source_ref_missing_session_id")
            else:
                reasons.append("source_ref_channel_unresolved")
        elif source_ref_project_id and source_ref_project_id != project_id:
            reasons.append("source_ref_cross_project_unresolved")
        else:
            reasons.append("source_ref_invalid")

    if target is None and sender_type == "agent" and sender_id and sender_id != source_channel:
        resolved = _call_server_override(
            "_resolve_primary_target_by_channel",
            _resolve_primary_target_by_channel,
            project_id,
            sender_id,
        )
        if resolved:
            target = resolved
            source = "sender_agent"
            if original_cb or source_ref:
                fallback_stage = "fallback_to_sender_agent"
        else:
            reasons.append("sender_agent_unresolved")

    if target is None and owner_channel and owner_channel != source_channel:
        resolved = _call_server_override(
            "_resolve_primary_target_by_channel",
            _resolve_primary_target_by_channel,
            project_id,
            owner_channel,
        )
        if resolved:
            target = resolved
            source = "owner_channel"
            if original_cb or sender_id:
                fallback_stage = "fallback_to_owner_channel"
        else:
            reasons.append("owner_channel_unresolved")

    if target is None:
        resolved = _call_server_override(
            "_resolve_master_control_target",
            _resolve_master_control_target,
            project_id,
        )
        if resolved:
            target = resolved
            source = "master_fallback"
            if original_cb or sender_id or owner_channel:
                fallback_stage = "fallback_to_master"
        else:
            reasons.append("master_control_unresolved")

    route_resolution: dict[str, Any] = {
        "source": source or "unresolved",
        "fallback_stage": fallback_stage,
    }
    if reasons:
        route_resolution["degrade_reason"] = str(reasons[0]).strip()
    if original_cb:
        route_resolution["original_callback_to"] = original_cb
    if source_ref:
        route_resolution["source_ref"] = {
            key: value
            for key, value in source_ref.items()
            if key in {"project_id", "channel_name", "session_id", "run_id"} and str(value or "").strip()
        }
    if target:
        route_resolution["resolved_target"] = dict(target)
        route_resolution["final_target"] = dict(target)
    if reasons:
        route_resolution["fallback_reasons"] = reasons[:8]
    return target, route_resolution


def _build_callback_communication_view(
    source_meta: dict[str, Any],
    *,
    event_reason: str,
    dispatch_state: str,
    dispatch_run_id: str,
    route_mismatch: bool,
    route_resolution: Any,
) -> dict[str, Any]:
    target_payload = {}
    if isinstance(route_resolution, dict):
        target_payload = route_resolution.get("final_target") or route_resolution.get("resolved_target") or {}
    source_target_ref = source_meta.get("target_ref")
    source_target_ref = source_target_ref if isinstance(source_target_ref, dict) else {}
    source_channel = _resolve_source_channel_text(source_meta)
    source_project_id = str(source_meta.get("projectId") or source_target_ref.get("project_id") or "").strip()
    source_session_id = str(source_meta.get("sessionId") or source_target_ref.get("session_id") or "").strip()
    target_project_id = source_project_id
    target_channel = str((target_payload or {}).get("channel_name") or "").strip()
    target_session_id = str((target_payload or {}).get("session_id") or "").strip()
    out: dict[str, Any] = {
        "version": "v1",
        "message_kind": "system_callback",
        "event_reason": str(event_reason or "unverified").strip().lower(),
        "dispatch_state": str(dispatch_state or "pending").strip().lower(),
        "dispatch_run_id": _safe_text(dispatch_run_id, 120).strip(),
        "route_mismatch": bool(route_mismatch),
    }
    if source_project_id:
        out["source_project_id"] = source_project_id
    if source_channel:
        out["source_channel"] = source_channel
    if source_session_id:
        out["source_session_id"] = source_session_id
    if target_project_id:
        out["target_project_id"] = target_project_id
    if target_channel:
        out["target_channel"] = target_channel
    if target_session_id:
        out["target_session_id"] = target_session_id
    if out["event_reason"] not in {"success", "unverified", "route_mismatch"}:
        out["event_reason"] = "unverified"
    if out["dispatch_state"] not in {"resolved", "fallback", "route_mismatch", "pending"}:
        out["dispatch_state"] = "pending"
    route_resolution_v1 = __getattr__("_compact_route_resolution_v1")(route_resolution)
    if route_resolution_v1:
        out["route_resolution"] = route_resolution_v1
    return out


def _callback_dispatch_key(project_id: str, source_run_id: str, event_type: str, target_session_id: str) -> str:
    return "||".join(
        [
            str(project_id or "").strip(),
            str(source_run_id or "").strip(),
            str(event_type or "").strip().lower(),
            str(target_session_id or "").strip(),
        ]
    )


def _callback_anchor_mutex(anchor_key: str) -> threading.Lock:
    key = str(anchor_key or "").strip() or "__default__"
    with _CALLBACK_ANCHOR_LOCK_GUARD:
        lock = _CALLBACK_ANCHOR_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _CALLBACK_ANCHOR_LOCKS[key] = lock
        return lock


def _append_source_callback_dispatch(
    store,
    source_meta: dict[str, Any],
    *,
    dispatch_key: str,
    event_type: str,
    target: dict[str, str],
    status: str,
    callback_run_id: str = "",
    note: str = "",
) -> dict[str, Any]:
    source = source_meta if isinstance(source_meta, dict) else dict(source_meta)
    rows = source.get("callback_dispatches")
    items = rows if isinstance(rows, list) else []
    for row in items:
        if isinstance(row, dict) and str(row.get("dispatch_key") or "").strip() == dispatch_key:
            return source
    item: dict[str, Any] = {
        "dispatch_key": dispatch_key,
        "event_type": str(event_type or "").strip().lower(),
        "target": {
            "channel_name": str(target.get("channel_name") or "").strip(),
            "session_id": str(target.get("session_id") or "").strip(),
        },
        "status": str(status or "").strip().lower(),
        "at": _now_iso(),
    }
    if callback_run_id:
        item["callback_run_id"] = callback_run_id
    if note:
        item["note"] = _safe_text(note, 300).strip()
    source["callback_dispatches"] = list(items) + [item]
    source["callback_dispatches"] = source["callback_dispatches"][-80:]
    if isinstance(source_meta, dict):
        source_meta["callback_dispatches"] = source["callback_dispatches"]
    store.save_meta(str(source.get("id") or "").strip(), source)
    return source


def _resolve_receipt_host_run(
    store,
    *,
    source_meta: dict[str, Any],
    route_resolution: Any,
) -> tuple[str, dict[str, Any], str]:
    source_run_id = str(source_meta.get("id") or "").strip()
    source_ref = _normalize_message_ref_local(source_meta.get("source_ref"), allow_run_id=True)
    rr = route_resolution if isinstance(route_resolution, dict) else {}
    rr_source_ref = _normalize_message_ref_local(rr.get("source_ref"), allow_run_id=True)
    merged_source_ref = dict(source_ref or {})
    for key, value in (rr_source_ref or {}).items():
        if value and key not in merged_source_ref:
            merged_source_ref[key] = value
    host_run_id = str(merged_source_ref.get("run_id") or "").strip()
    if host_run_id:
        host_meta = store.load_meta(host_run_id) or {}
        if isinstance(host_meta, dict) and str(host_meta.get("id") or "").strip() == host_run_id:
            return host_run_id, host_meta, "source_ref_run_id"
    if source_run_id:
        host_meta = store.load_meta(source_run_id) or dict(source_meta)
        if isinstance(host_meta, dict):
            if str(host_meta.get("id") or "").strip() != source_run_id:
                host_meta["id"] = source_run_id
            return source_run_id, host_meta, "source_run_id"
    return "", {}, "missing"


def _normalize_receipt_items(items: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in items if isinstance(items, list) else []:
        if not isinstance(row, dict):
            continue
        source_run_id = str(row.get("source_run_id") or "").strip()
        if not source_run_id:
            continue
        item: dict[str, Any] = {
            "source_run_id": source_run_id,
        }
        callback_run_id = str(row.get("callback_run_id") or "").strip()
        if callback_run_id:
            item["callback_run_id"] = callback_run_id
        for key in (
            "host_run_id",
            "host_reason",
            "trigger_type",
            "event_type",
            "event_reason",
            "dispatch_status",
            "source_channel",
            "source_agent_name",
            "source_project_id",
            "source_session_id",
            "target_project_id",
            "target_channel",
            "target_session_id",
            "callback_task",
            "execution_stage",
            "current_conclusion",
            "need_peer",
            "expected_result",
            "need_confirm",
            "feedback_file_path",
            "callback_merge_mode",
            "callback_anchor_action",
            "callback_at",
            "updated_at",
        ):
            text = _safe_text(row.get(key), 1200 if key.endswith("_path") else 300).strip()
            if text:
                item[key] = text
        route_resolution = __getattr__("_compact_route_resolution_v1")(row.get("route_resolution"))
        if route_resolution:
            item["route_resolution"] = route_resolution
        for bool_key in ("late_callback", "route_mismatch", "is_summary"):
            if isinstance(row.get(bool_key), bool):
                item[bool_key] = bool(row.get(bool_key))
        for int_key in ("aggregate_count", "summary_count"):
            raw = row.get(int_key)
            if raw is None:
                continue
            try:
                n = int(raw)
            except Exception:
                continue
            if n > 0:
                item[int_key] = min(n, 5000)
        out.append(item)
    out.sort(
        key=lambda row: (
            str(row.get("callback_at") or ""),
            str(row.get("callback_run_id") or ""),
            str(row.get("source_run_id") or ""),
        )
    )
    return out[-120:]


def _receipt_item_requires_action(item: dict[str, Any]) -> bool:
    event_type = str(item.get("event_type") or "").strip().lower()
    need_confirm = str(item.get("need_confirm") or "").strip()
    if event_type in {"error", "interrupted"}:
        return True
    if need_confirm and need_confirm != "无":
        return True
    return False


def _build_receipt_pending_actions(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in items:
        if not _receipt_item_requires_action(item):
            continue
        event_type = str(item.get("event_type") or "").strip().lower()
        need_confirm = str(item.get("need_confirm") or "").strip()
        current_conclusion = str(item.get("current_conclusion") or "").strip()
        need_peer = str(item.get("need_peer") or "").strip()
        title = need_confirm if need_confirm and need_confirm != "无" else (current_conclusion or "待处理回执")
        action_kind = "confirm"
        if event_type == "interrupted":
            action_kind = "recover"
        elif event_type == "error":
            action_kind = "fix"
        priority = "high" if event_type in {"error", "interrupted"} else "normal"
        row: dict[str, Any] = {
            "source_run_id": str(item.get("source_run_id") or "").strip(),
            "title": _safe_text(title, 200).strip() or "待处理回执",
            "action_text": _safe_text(need_peer or current_conclusion, 300).strip() or "请查看回执详情。",
            "action_kind": action_kind,
            "priority": priority,
            "source_channel": _safe_text(item.get("source_channel"), 200).strip(),
            "source_agent_name": _safe_text(item.get("source_agent_name"), 200).strip(),
            "event_type": event_type,
            "callback_at": _safe_text(item.get("callback_at"), 80).strip(),
        }
        callback_run_id = str(item.get("callback_run_id") or "").strip()
        if callback_run_id:
            row["callback_run_id"] = callback_run_id
        need_confirm_text = _safe_text(item.get("need_confirm"), 200).strip()
        if need_confirm_text:
            row["need_confirm"] = need_confirm_text
        out.append(row)
    out.sort(
        key=lambda row: (
            str(row.get("callback_at") or ""),
            str(row.get("callback_run_id") or ""),
            str(row.get("source_run_id") or ""),
        )
    )
    return out[-120:]


def _derive_receipt_rollup(items: list[dict[str, Any]], pending_actions: list[dict[str, Any]], *, host_run_id: str) -> dict[str, Any]:
    if not items:
        return {}
    counts = {"done": 0, "error": 0, "interrupted": 0}
    need_confirm_count = 0
    agents: list[str] = []
    latest = items[-1]
    event_types: set[str] = set()
    for item in items:
        event_type = str(item.get("event_type") or "").strip().lower()
        if event_type in counts:
            counts[event_type] += 1
            event_types.add(event_type)
        need_confirm = str(item.get("need_confirm") or "").strip()
        if need_confirm and need_confirm != "无":
            need_confirm_count += 1
        source_agent_name = str(item.get("source_agent_name") or "").strip()
        source_channel = str(item.get("source_channel") or "").strip()
        source_label = source_agent_name or source_channel
        if source_label and source_label not in agents:
            agents.append(source_label)
    latest_status = str(latest.get("event_type") or "").strip().lower() or "unknown"
    if len(event_types) > 1:
        latest_status = "mixed"
    rollup: dict[str, Any] = {
        "host_run_id": host_run_id,
        "total_callbacks": len(items),
        "callback_count": len(items),
        "done_count": counts["done"],
        "error_count": counts["error"],
        "interrupted_count": counts["interrupted"],
        "latest_status": latest_status,
        "latest_conclusion": str(latest.get("current_conclusion") or "").strip(),
        "pending_action_count": len(pending_actions),
        "need_confirm_count": need_confirm_count,
        "agents": agents[:20],
        "last_callback_at": str(latest.get("callback_at") or "").strip(),
    }
    callback_run_id = str(latest.get("callback_run_id") or "").strip()
    if callback_run_id:
        rollup["last_callback_run_id"] = callback_run_id
    return rollup


def _build_receipt_projection_item(
    *,
    host_run_id: str,
    host_reason: str,
    source_meta: dict[str, Any],
    callback_meta: Optional[dict[str, Any]],
    callback_run_id: str,
    event_type: str,
    event_reason: str,
    dispatch_status: str,
    route_resolution: Any,
) -> dict[str, Any]:
    cb_meta = callback_meta if isinstance(callback_meta, dict) else {}
    receipt_summary = cb_meta.get("receipt_summary")
    summary = receipt_summary if isinstance(receipt_summary, dict) else {}
    profile = _extract_callback_progress_profile(source_meta, event_type)
    technical = summary.get("technical") if isinstance(summary.get("technical"), dict) else {}
    prefer_source_profile = str(dispatch_status or "").strip().lower() in {"merged_anchor", "summary_window_member"}
    route_resolution_v1 = __getattr__("_compact_route_resolution_v1")(
        route_resolution if isinstance(route_resolution, dict) else (technical.get("route_resolution") or {})
    )
    source_run_id = str(source_meta.get("id") or "").strip()
    callback_at = str(cb_meta.get("createdAt") or cb_meta.get("startedAt") or _now_iso()).strip()
    out: dict[str, Any] = {
        "host_run_id": host_run_id,
        "host_reason": host_reason,
        "source_run_id": source_run_id,
        "callback_run_id": str(callback_run_id or "").strip(),
        "trigger_type": str(cb_meta.get("trigger_type") or "callback_auto").strip().lower(),
        "event_type": str(event_type or "").strip().lower(),
        "event_reason": str(event_reason or "").strip().lower(),
        "dispatch_status": str(dispatch_status or "").strip().lower(),
        "source_channel": str(
            (profile.get("source_channel") if prefer_source_profile else "")
            or summary.get("source_channel")
            or profile.get("source_channel")
            or ""
        ).strip(),
        "source_agent_name": str(
            (profile.get("source_agent_name") if prefer_source_profile else "")
            or summary.get("source_agent_name")
            or profile.get("source_agent_name")
            or ""
        ).strip(),
        "source_project_id": str(summary.get("source_project_id") or source_meta.get("projectId") or "").strip(),
        "source_session_id": str(summary.get("source_session_id") or source_meta.get("sessionId") or "").strip(),
        "target_project_id": str(summary.get("target_project_id") or source_meta.get("projectId") or "").strip(),
        "target_channel": str(summary.get("target_channel") or "").strip(),
        "target_session_id": str(summary.get("target_session_id") or "").strip(),
        "callback_task": str(
            (profile.get("task_path") if prefer_source_profile else "")
            or summary.get("callback_task")
            or profile.get("task_path")
            or ""
        ).strip(),
        "execution_stage": str(
            (profile.get("stage") if prefer_source_profile else "")
            or summary.get("execution_stage")
            or profile.get("stage")
            or ""
        ).strip(),
        "current_conclusion": str(
            (profile.get("current_conclusion") if prefer_source_profile else "")
            or summary.get("conclusion")
            or profile.get("current_conclusion")
            or ""
        ).strip(),
        "need_peer": str(
            (profile.get("next_step") if prefer_source_profile else "")
            or summary.get("need_peer")
            or profile.get("next_step")
            or ""
        ).strip(),
        "expected_result": str(summary.get("expected_result") or "").strip(),
        "need_confirm": str(
            (profile.get("need_confirmation") if prefer_source_profile else "")
            or summary.get("need_confirm")
            or profile.get("need_confirmation")
            or "无"
        ).strip() or "无",
        "feedback_file_path": str(source_meta.get("feedback_file_path") or cb_meta.get("feedback_file_path") or "").strip(),
        "callback_at": callback_at,
        "updated_at": _now_iso(),
    }
    if route_resolution_v1:
        out["route_resolution"] = route_resolution_v1
    late_callback = summary.get("late_callback")
    if isinstance(late_callback, bool):
        out["late_callback"] = late_callback
    route_mismatch = (cb_meta.get("communication_view") or {}).get("route_mismatch") if isinstance(cb_meta.get("communication_view"), dict) else None
    if isinstance(route_mismatch, bool):
        out["route_mismatch"] = route_mismatch
    trigger_type = str(out.get("trigger_type") or "").strip().lower()
    if trigger_type == "callback_auto_summary":
        out["is_summary"] = True
    aggregate_count = cb_meta.get("callback_aggregate_count")
    if aggregate_count is not None:
        try:
            n = int(aggregate_count)
            if n > 0:
                out["aggregate_count"] = min(n, 5000)
        except Exception:
            pass
    summary_of = cb_meta.get("callback_summary_of")
    if isinstance(summary_of, list):
        out["summary_count"] = len([str(x or "").strip() for x in summary_of if str(x or "").strip()])
    callback_merge_mode = str(cb_meta.get("callback_merge_mode") or "").strip().lower()
    if callback_merge_mode:
        out["callback_merge_mode"] = callback_merge_mode
    callback_anchor_action = str(cb_meta.get("callback_anchor_action") or "").strip().lower()
    if callback_anchor_action:
        out["callback_anchor_action"] = callback_anchor_action
    return out


def _project_receipt_to_host_run(
    store,
    *,
    source_meta: dict[str, Any],
    callback_meta: Optional[dict[str, Any]],
    callback_run_id: str,
    event_type: str,
    event_reason: str,
    dispatch_status: str,
    route_resolution: Any,
) -> str:
    host_run_id, host_meta, host_reason = _resolve_receipt_host_run(
        store,
        source_meta=source_meta,
        route_resolution=route_resolution,
    )
    if not host_run_id or not isinstance(host_meta, dict):
        return ""
    item = _build_receipt_projection_item(
        host_run_id=host_run_id,
        host_reason=host_reason,
        source_meta=source_meta,
        callback_meta=callback_meta,
        callback_run_id=callback_run_id,
        event_type=event_type,
        event_reason=event_reason,
        dispatch_status=dispatch_status,
        route_resolution=route_resolution,
    )
    items = _normalize_receipt_items(host_meta.get("receipt_items"))
    source_run_id = str(item.get("source_run_id") or "").strip()
    replaced = False
    if source_run_id:
        for idx, row in enumerate(items):
            if str(row.get("source_run_id") or "").strip() == source_run_id:
                items[idx] = item
                replaced = True
                break
    if not replaced:
        items.append(item)
    items = _normalize_receipt_items(items)
    pending_actions = _build_receipt_pending_actions(items)
    rollup = _derive_receipt_rollup(items, pending_actions, host_run_id=host_run_id)
    host_meta["receipt_items"] = items
    if pending_actions:
        host_meta["receipt_pending_actions"] = pending_actions
    else:
        host_meta.pop("receipt_pending_actions", None)
    if rollup:
        host_meta["receipt_rollup"] = rollup
    else:
        host_meta.pop("receipt_rollup", None)
    store.save_meta(host_run_id, host_meta)
    return host_run_id


def _source_has_callback_dispatch(meta: dict[str, Any], dispatch_key: str) -> bool:
    rows = meta.get("callback_dispatches")
    if not isinstance(rows, list):
        return False
    for row in rows:
        if isinstance(row, dict) and str(row.get("dispatch_key") or "").strip() == dispatch_key:
            return True
    return False


def _claim_callback_dispatch_key(store, run_id: str, dispatch_key: str) -> tuple[bool, dict[str, Any], str]:
    run = str(run_id or "").strip()
    key = str(dispatch_key or "").strip()
    latest = store.load_meta(run) or {}
    existing_run_id = _source_callback_dispatch_run_id(latest, key)
    if existing_run_id:
        return False, latest, existing_run_id
    with _CALLBACK_DISPATCH_CLAIM_LOCK:
        latest = store.load_meta(run) or latest
        existing_run_id = _source_callback_dispatch_run_id(latest, key)
        if existing_run_id:
            return False, latest, existing_run_id
        if key in _CALLBACK_DISPATCH_INFLIGHT:
            return False, latest, ""
        _CALLBACK_DISPATCH_INFLIGHT.add(key)
    return True, latest, ""


def _release_callback_dispatch_key(dispatch_key: str) -> None:
    key = str(dispatch_key or "").strip()
    if not key:
        return
    with _CALLBACK_DISPATCH_CLAIM_LOCK:
        _CALLBACK_DISPATCH_INFLIGHT.discard(key)


def _source_callback_dispatch_run_id(meta: dict[str, Any], dispatch_key: str) -> str:
    rows = meta.get("callback_dispatches")
    if not isinstance(rows, list):
        return ""
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("dispatch_key") or "").strip() != dispatch_key:
            continue
        run_id = str(row.get("callback_run_id") or "").strip()
        if run_id:
            return run_id
    return ""


def _resolve_callback_target_cli_type(
    store,
    *,
    source_meta: dict[str, Any],
    target: dict[str, str],
) -> str:
    session_id = str(target.get("session_id") or "").strip()
    if session_id:
        for base_dir in (store.runs_dir.parent, store.runs_dir):
            try:
                session_store = SessionStore(base_dir)
                row = session_store.get_session(session_id)
                if isinstance(row, dict):
                    cli_type = str(row.get("cli_type") or "").strip()
                    if cli_type:
                        return cli_type
            except Exception:
                continue
    return str(source_meta.get("cliType") or "codex").strip() or "codex"


def _callback_summary_timer_key(key: str) -> str:
    return str(key or "").strip()


def _inspect_callback_task_activity(task_path: str) -> dict[str, Any]:
    text = str(task_path or "").strip()
    out: dict[str, Any] = {
        "task_path": text,
        "state": "none",
        "is_archived": False,
        "reason": "none",
    }
    if not text:
        return out
    out["state"] = "unknown"
    norm = text.replace("\\", "/")
    filename = Path(norm).name
    path = Path(text)
    root = __getattr__("_repo_root")()
    candidate = path if path.is_absolute() else (root / path)

    def _mark_archived(reason: str) -> dict[str, Any]:
        out["state"] = "archived"
        out["is_archived"] = True
        out["reason"] = reason
        return out

    if candidate.exists():
        parts = set(candidate.parts)
        fname = str(candidate.name or "")
        if ("已完成" in parts) or ("暂缓" in parts):
            return _mark_archived("path_archived_dir")
        if "【已完成】" in fname or "【已验收通过】" in fname or "【暂缓】" in fname:
            return _mark_archived("filename_archived_tag")
        if "任务" in parts:
            out["state"] = "active"
            out["reason"] = "path_task_dir"
            return out
        out["state"] = "unknown"
        out["reason"] = "path_exists_unclassified"
        return out

    if "/已完成/" in norm or "/暂缓/" in norm:
        return _mark_archived("missing_archived_path")

    if "/任务/" in norm and filename:
        prefix = norm.split("/任务/")[0]
        for dirname in ("已完成", "暂缓"):
            probe = root / Path(prefix) / dirname / filename
            if probe.exists():
                return _mark_archived("moved_to_archived_dir")
        out["state"] = "active"
        out["reason"] = "task_path_missing"
        return out

    out["state"] = "unknown"
    out["reason"] = "path_missing_unclassified"
    return out


def _build_terminal_receipt_summary(
    source_meta: dict[str, Any],
    *,
    event_type: str,
    event_reason: str,
    target: dict[str, str],
    route_resolution: dict[str, Any],
    profile: dict[str, str],
) -> dict[str, Any]:
    source_target_ref = source_meta.get("target_ref")
    source_target_ref = source_target_ref if isinstance(source_target_ref, dict) else {}
    source_channel = str(profile.get("source_channel") or "").strip() or "未知通道"
    source_project_id = str(source_meta.get("projectId") or source_target_ref.get("project_id") or "").strip()
    source_session_id = str(source_meta.get("sessionId") or source_target_ref.get("session_id") or "").strip()
    target_project_id = source_project_id
    target_channel = str(target.get("channel_name") or "").strip() or "-"
    target_session_id = str(target.get("session_id") or "").strip()
    task_path = str(profile.get("task_path") or "").strip() or "未关联任务"
    source_run_id = str(source_meta.get("id") or "").strip()
    trigger_type = str(source_meta.get("trigger_type") or "").strip().lower() or "manual_dispatch"
    task_activity = _inspect_callback_task_activity(task_path)
    is_late = bool(task_activity.get("is_archived"))
    stage = str(profile.get("stage") or "").strip() or ("收口" if event_type == "done" else "推进")
    current_conclusion = str(profile.get("current_conclusion") or "").strip() or _default_callback_conclusion(event_type)
    if is_late:
        if event_type == "done":
            current_conclusion = "已完成（迟到回执）"
        elif event_type == "interrupted":
            current_conclusion = "已中断待恢复（迟到回执）"
        else:
            current_conclusion = "执行异常（迟到回执）"

    goal_map = {
        "done": "同步来源任务完成结果，推动验收收口。",
        "interrupted": "同步任务中断信息，推动恢复推进。",
        "error": "同步任务异常信息，推动排障处理。",
    }
    progress_map = {
        "done": "来源任务已完成执行，回执已送达目标通道。",
        "interrupted": "来源任务出现中断，已发送恢复提示。",
        "error": "来源任务执行异常，已发送排障提示。",
    }
    need_peer_map = {
        "done": "请主负责确认是否进入验收/收口。",
        "interrupted": "请判断是否补发“继续开展工作”并在恢复后回收结果。",
        "error": "请优先查看日志并决定重试、回滚或转问题单。",
    }
    expected_map = {
        "done": "任务进入验收或归档流程。",
        "interrupted": "中断任务恢复推进并形成新回执。",
        "error": "异常定位完成并形成处理结论。",
    }
    need_confirm_map = {
        "done": "是否进入验收/收口",
        "interrupted": "是否继续开展工作",
        "error": "无",
    }

    progress = progress_map.get(event_type, "系统回执已生成。")
    error = str(source_meta.get("error") or "").strip()
    last_preview = str(source_meta.get("lastPreview") or "").strip()
    if event_type == "error" and error:
        progress = f"{progress}（错误摘要：{_safe_text(error, 120)}）"
    if event_type == "done" and last_preview:
        progress = f"{progress}（结果摘要：{_safe_text(last_preview, 120)}）"

    need_peer = need_peer_map.get(event_type, "请主负责确认下一步动作。")
    expected_result = expected_map.get(event_type, "推进链路保持可追溯。")
    need_confirm = need_confirm_map.get(event_type, "无")
    if is_late:
        need_peer = "关联任务已归档，本条回执已降级为留痕提示；无需重复验收确认。"
        expected_result = "保持归档状态并补齐必要留痕。"
        need_confirm = "无"
        progress = f"{progress}（关联任务状态：已归档）"

    feedback_path = str(source_meta.get("feedback_file_path") or "").strip()
    actions = [
        f"已生成系统主动回执并投递至 `{str(target.get('channel_name') or '-')}`。",
        "已保留技术明细（run/路由/降级）供排障回放。",
    ]
    if feedback_path:
        actions.append(f"反馈文件：{feedback_path}")
    else:
        actions.append("反馈文件待补录（验收仍以反馈目录文件为准）")

    return {
        "version": "v1",
        "message_kind": "system_callback",
        "headline": f"{source_channel}：{current_conclusion}",
        "source_channel": source_channel,
        "source_agent_name": str(profile.get("source_agent_name") or "").strip(),
        "source_project_id": source_project_id,
        "source_session_id": source_session_id,
        "target_project_id": target_project_id,
        "target_channel": target_channel,
        "target_session_id": target_session_id,
        "callback_task": task_path,
        "execution_stage": stage,
        "goal": goal_map.get(event_type, "同步系统回执，保障任务推进沟通。"),
        "conclusion": current_conclusion,
        "progress": progress,
        "system_actions": actions[:3],
        "need_peer": need_peer,
        "expected_result": expected_result,
        "need_confirm": str(profile.get("need_confirmation") or "").strip() or need_confirm,
        "late_callback": is_late,
        "late_reason": str(task_activity.get("reason") or "none"),
        "technical": {
            "event_type": str(event_type or "").strip().lower(),
            "event_reason": str(event_reason or "").strip().lower(),
            "source_run_id": source_run_id,
            "trigger_type": trigger_type,
            "route_resolution": __getattr__("_compact_route_resolution_v1")(route_resolution),
        },
    }


def _build_callback_window_receipt_summary(state: dict[str, Any]) -> dict[str, Any]:
    event_type = str(state.get("event_type") or "").strip().lower()
    source_channel = str(state.get("source_channel") or "").strip() or "未知通道"
    task_path = str(state.get("task_path") or "").strip() or "未关联任务"
    stage = str(state.get("stage") or "").strip() or "推进"
    target_channel = str((state.get("target") or {}).get("channel_name") or "").strip() or "-"
    pending = state.get("pending")
    items = pending if isinstance(pending, list) else []
    run_ids = [str(item.get("source_run_id") or "").strip() for item in items if isinstance(item, dict)]
    run_ids = [run_id for run_id in run_ids if run_id]
    preview = ", ".join(run_ids[:8]) if run_ids else "-"
    if len(run_ids) > 8:
        preview += f" 等 {len(run_ids)} 条"
    conclusion = "已中断待恢复（汇总）" if event_type == "interrupted" else "执行异常（汇总）"
    return {
        "version": "v1",
        "message_kind": "system_callback_summary",
        "headline": f"{source_channel}：{conclusion}",
        "source_channel": source_channel,
        "callback_task": task_path,
        "execution_stage": stage,
        "goal": "短窗汇总回执，减少重复刷屏并保持推进主线清晰。",
        "conclusion": conclusion,
        "progress": f"窗口内汇总 {len(run_ids)} 条；来源run：{preview}",
        "system_actions": [
            f"已对目标通道 `{target_channel}` 发送汇总回执。",
            "逐条明细仍保留在来源 run 与反馈文件轨。",
        ],
        "need_peer": "请按优先级处理本批回执涉及任务。",
        "expected_result": "本批任务完成收口并形成后续推进结论。",
        "need_confirm": "无",
        "late_callback": False,
        "late_reason": "none",
        "technical": {
            "event_type": event_type,
            "trigger_type": "callback_auto_summary",
            "source_run_ids": run_ids[:120],
            "route_resolution": __getattr__("_compact_route_resolution_v1")(state.get("route_resolution")),
        },
    }


def _render_receipt_summary_message(summary: dict[str, Any]) -> str:
    source = summary if isinstance(summary, dict) else {}
    source_channel = str(source.get("source_channel") or "").strip() or "未知通道"
    callback_task = str(source.get("callback_task") or "").strip() or "未关联任务"
    stage = str(source.get("execution_stage") or "").strip() or "推进"
    goal = str(source.get("goal") or "").strip() or "同步系统回执，保障任务推进沟通。"
    conclusion = str(source.get("conclusion") or "").strip() or "需处理"
    progress = str(source.get("progress") or "").strip() or "系统回执已生成。"
    need_peer = str(source.get("need_peer") or "").strip() or "请主负责确认下一步动作。"
    expected_result = str(source.get("expected_result") or "").strip() or "推进链路保持可追溯。"
    need_confirm = str(source.get("need_confirm") or "").strip() or "无"
    actions = source.get("system_actions")
    if isinstance(actions, list):
        action_text = "；".join([str(item).strip() for item in actions if str(item).strip()][:3])
    else:
        action_text = ""
    if not action_text:
        action_text = "已生成系统回执并写入运行留痕。"
    lines = [
        f"[来源通道: {source_channel}]",
        f"回执任务: {callback_task}",
        f"执行阶段: {stage}",
        f"本次目标: {goal}",
        f"当前结论: {conclusion}",
        f"目标进展: {progress}",
        f"系统已处理: {action_text}",
        f"需要对方: {need_peer}",
        f"预期结果: {expected_result}",
        f"需确认: {need_confirm}",
    ]
    if bool(source.get("late_callback")):
        lines.append("说明: 该回执到达时关联任务已归档，已降级为留痕提示。")
    return "\n".join(lines)


def _build_terminal_callback_message(
    source_meta: dict[str, Any],
    *,
    event_type: str,
    event_reason: str,
    target: dict[str, str],
    route_resolution: dict[str, Any],
) -> str:
    profile = _extract_callback_progress_profile(source_meta, event_type)
    summary = _build_terminal_receipt_summary(
        source_meta,
        event_type=event_type,
        event_reason=event_reason,
        target=target,
        route_resolution=route_resolution,
        profile=profile,
    )
    technical = summary.get("technical") if isinstance(summary, dict) else {}
    tech = technical if isinstance(technical, dict) else {}
    source_run_id = str(tech.get("source_run_id") or "").strip() or str(source_meta.get("id") or "").strip()
    trigger_type = str(tech.get("trigger_type") or "").strip() or str(
        source_meta.get("trigger_type") or "manual_dispatch"
    ).strip().lower()
    error = str(source_meta.get("error") or "").strip()
    last_preview = str(source_meta.get("lastPreview") or "").strip()
    feedback_path = str(source_meta.get("feedback_file_path") or "").strip()
    event_label = {"done": "完成", "error": "异常", "interrupted": "中断"}.get(event_type, event_type or "事件")
    lines = [_render_receipt_summary_message(summary), "", "技术明细（折叠）："]
    lines.append(f"- 回执主题: {event_label}")
    lines.append(f"- 来源run: {source_run_id or '-'}")
    lines.append(f"- 事件类型: {event_type or '-'}")
    if event_reason:
        lines.append(f"- 事件原因: {event_reason}")
    lines.append(
        "- 路由结果: "
        + f"{str(route_resolution.get('source') or 'unknown')} -> "
        + f"{str(target.get('channel_name') or '')}"
    )
    lines.append(f"- 触发类型: {trigger_type}")
    if feedback_path:
        lines.append(f"- 反馈文件: {feedback_path}")
    else:
        lines.append("- 反馈文件: 待补录（验收仍以 `反馈/【待验收】【反馈】...` 为准）")
    if error and event_type != "done":
        lines.append(f"- 错误摘要: {_safe_text(error, 260)}")
    elif last_preview:
        lines.append(f"- 结果摘要: {_safe_text(last_preview, 260)}")
    else:
        lines.append("- 结果摘要: 无（请查看来源 run 日志/回收结果）")
    return "\n".join(lines)


def _build_callback_summary_message(state: dict[str, Any]) -> str:
    summary = _build_callback_window_receipt_summary(state)
    project_id = str(state.get("project_id") or "").strip()
    event_type = str(state.get("event_type") or "").strip().lower()
    target_channel = str((state.get("target") or {}).get("channel_name") or "").strip()
    pending = state.get("pending")
    items = pending if isinstance(pending, list) else []
    event_label = {"error": "异常", "interrupted": "中断"}.get(event_type, event_type or "事件")
    run_ids = [str(item.get("source_run_id") or "").strip() for item in items if isinstance(item, dict)]
    run_ids = [run_id for run_id in run_ids if run_id]
    preview = ", ".join(run_ids[:8])
    if len(run_ids) > 8:
        preview += f" 等 {len(run_ids)} 条"
    lines = [
        _render_receipt_summary_message(summary),
        "",
        "技术明细（折叠）：",
        f"- 回执主题: {event_label}汇总",
        f"- 目标通道: {target_channel or '-'}",
        f"- 项目: {project_id or '-'}",
        f"- 事件类型: {event_type}",
        f"- 窗口内汇总数量: {len(run_ids)}",
        f"- 来源run列表: {preview or '-'}",
        "- 说明: 该消息为短窗节流后的汇总回执；逐条明细仍可在来源 run 与反馈文件轨中查看。",
    ]
    return "\n".join(lines)


def _flush_callback_summary_window(
    store,
    scheduler: Optional["RunScheduler"],
    key: str,
) -> None:
    summary_key = _callback_summary_timer_key(key)
    with _CALLBACK_WINDOW_LOCK:
        state = _CALLBACK_WINDOWS.pop(summary_key, None)
    if not isinstance(state, dict):
        return
    pending = state.get("pending")
    items = pending if isinstance(pending, list) else []
    if not items:
        return
    target = state.get("target")
    if not isinstance(target, dict):
        return
    session_id = str(target.get("session_id") or "").strip()
    channel_name = str(target.get("channel_name") or "").strip()
    project_id = str(state.get("project_id") or "").strip()
    if not (project_id and channel_name and session_id and _looks_like_uuid(session_id)):
        return
    source_run_ids = [str(item.get("source_run_id") or "").strip() for item in items if isinstance(item, dict)]
    source_run_ids = [run_id for run_id in source_run_ids if run_id]
    if not source_run_ids:
        return
    event_type = str(state.get("event_type") or "").strip().lower()
    route_resolution = state.get("route_resolution")
    receipt_summary = _build_callback_window_receipt_summary(state)
    summary_run = store.create_run(
        project_id,
        channel_name,
        session_id,
        _build_callback_summary_message(state),
        profile_label="",
        cli_type=str(state.get("target_cli_type") or "codex").strip() or "codex",
        sender_type="system",
        sender_id="system",
        sender_name="系统",
        extra_meta={
            "trigger_type": "callback_auto_summary",
            "event_type": event_type,
            "source_run_id": source_run_ids[0],
            "task_path": str(state.get("task_path") or "").strip(),
            "execution_stage": str(state.get("stage") or "").strip().lower(),
            "current_conclusion": str(state.get("current_conclusion") or "").strip(),
            "need_confirmation": str(state.get("need_confirmation") or "").strip(),
            "next_action": str(state.get("next_step") or "").strip(),
            "route_resolution": route_resolution if isinstance(route_resolution, dict) else {},
            "callback_summary_of": source_run_ids,
            "receipt_summary": receipt_summary,
        },
    )
    summary_run_id = str(summary_run.get("id") or "").strip()
    if summary_run_id:
        callback_meta = store.load_meta(summary_run_id) or dict(summary_run)
        __getattr__("_enqueue_run_execution")(
            store,
            summary_run_id,
            session_id,
            str(summary_run.get("cliType") or "codex"),
            scheduler,
        )
        for source_run_id in source_run_ids:
            src = store.load_meta(source_run_id) or {}
            if not src:
                continue
            rows = src.get("callback_summary_runs")
            items = rows if isinstance(rows, list) else []
            if summary_run_id not in [str(item or "").strip() for item in items]:
                src["callback_summary_runs"] = list(items) + [summary_run_id]
                src["callback_summary_runs"] = src["callback_summary_runs"][-20:]
                store.save_meta(source_run_id, src)
            _project_receipt_to_host_run(
                store,
                source_meta=src,
                callback_meta=callback_meta,
                callback_run_id=summary_run_id,
                event_type=event_type,
                event_reason="summary_window",
                dispatch_status="summary_window_member",
                route_resolution=route_resolution,
            )


def _register_callback_window(
    store,
    source_meta: dict[str, Any],
    *,
    event_type: str,
    target: dict[str, str],
    route_resolution: dict[str, Any],
    scheduler: Optional["RunScheduler"],
) -> tuple[bool, str]:
    if event_type not in {"error", "interrupted"}:
        return True, ""
    project_id = str(source_meta.get("projectId") or "").strip()
    profile = _extract_callback_progress_profile(source_meta, event_type)
    source_channel = str(profile.get("source_channel") or "").strip()
    task_path = str(profile.get("task_path") or "").strip()
    topic = str(profile.get("topic") or "").strip()
    stage = str(profile.get("stage") or "").strip()
    if not (project_id and source_channel and task_path):
        return True, ""
    key = _callback_throttle_key(project_id, source_channel, task_path, topic, stage)
    window_seconds = _default_callback_summary_window_s()
    now_ts = time.time()
    signature = _callback_progress_signature(profile)
    with _CALLBACK_WINDOW_LOCK:
        state = _CALLBACK_WINDOWS.get(key)
        if not isinstance(state, dict) or float(state.get("window_end_ts") or 0.0) <= now_ts:
            end_ts = now_ts + float(window_seconds)
            timer_target = _server_override("_flush_callback_summary_window", _flush_callback_summary_window)
            timer = threading.Timer(end_ts - now_ts, timer_target, args=(store, scheduler, key))
            timer.daemon = True
            _CALLBACK_WINDOWS[key] = {
                "project_id": project_id,
                "source_channel": source_channel,
                "event_type": event_type,
                "target": dict(target),
                "target_cli_type": _resolve_callback_target_cli_type(
                    store,
                    source_meta=source_meta,
                    target=target,
                ),
                "window_start_ts": now_ts,
                "window_end_ts": end_ts,
                "pending": [],
                "route_resolution": dict(route_resolution or {}),
                "task_path": task_path,
                "topic": topic,
                "stage": stage,
                "blocking_status": str(profile.get("blocking_status") or "").strip(),
                "current_conclusion": str(profile.get("current_conclusion") or "").strip(),
                "need_confirmation": str(profile.get("need_confirmation") or "").strip(),
                "next_step": str(profile.get("next_step") or "").strip(),
                "must_send_signature": list(signature),
                "timer": timer,
            }
            timer.start()
            return True, ""

        prev_signature_raw = state.get("must_send_signature")
        prev_signature = tuple(prev_signature_raw) if isinstance(prev_signature_raw, list) else tuple(prev_signature_raw or ())
        if prev_signature and prev_signature != signature:
            changed: list[str] = []
            if len(prev_signature) >= 1 and prev_signature[0] != signature[0]:
                changed.append("stage")
            if len(prev_signature) >= 2 and prev_signature[1] != signature[1]:
                changed.append("blocking")
            if len(prev_signature) >= 3 and prev_signature[2] != signature[2]:
                changed.append("conclusion")
            if len(prev_signature) >= 4 and prev_signature[3] != signature[3]:
                changed.append("need_confirmation")
            state["must_send_signature"] = list(signature)
            state["stage"] = stage
            state["blocking_status"] = str(profile.get("blocking_status") or "").strip()
            state["current_conclusion"] = str(profile.get("current_conclusion") or "").strip()
            state["need_confirmation"] = str(profile.get("need_confirmation") or "").strip()
            state["next_step"] = str(profile.get("next_step") or "").strip()
            _CALLBACK_WINDOWS[key] = state
            reason = ",".join(changed) if changed else "state_changed"
            return True, f"summary_window_bypass:{reason}"

        pending = state.get("pending")
        items = pending if isinstance(pending, list) else []
        items.append(
            {
                "source_run_id": str(source_meta.get("id") or "").strip(),
                "status": str(source_meta.get("status") or "").strip().lower(),
                "error": _safe_text(source_meta.get("error"), 260).strip(),
                "finished_at": str(source_meta.get("finishedAt") or "").strip(),
            }
        )
        state["pending"] = items[-50:]
        _CALLBACK_WINDOWS[key] = state
        return False, f"summary_window_active:{window_seconds}s"


def _dispatch_terminal_callback_for_run(
    store,
    run_id: str,
    *,
    scheduler: Optional["RunScheduler"] = None,
    meta: Optional[dict[str, Any]] = None,
) -> str:
    source_run_id = str(run_id or "").strip()
    if not source_run_id:
        return ""
    source_meta = dict(meta or store.load_meta(source_run_id) or {})
    if not source_meta:
        return ""
    if str(source_meta.get("id") or "").strip() != source_run_id:
        source_meta["id"] = source_run_id
    if not _source_run_callback_eligible(source_meta):
        return ""

    event_type, event_reason = _classify_terminal_callback_event(source_meta)
    if not event_type:
        return ""
    source_session_id = str(source_meta.get("sessionId") or "").strip()
    source_channel_name = _resolve_source_channel_text(source_meta)

    def _persist_callback_view(
        *,
        dispatch_state: str,
        dispatch_run_id: str,
        route_mismatch_flag: bool,
        event: str,
        route_resolution_in: Any = None,
    ) -> None:
        source_meta["communication_view"] = _build_callback_communication_view(
            source_meta,
            event_reason=event,
            dispatch_state=dispatch_state,
            dispatch_run_id=dispatch_run_id,
            route_mismatch=route_mismatch_flag,
            route_resolution=route_resolution_in,
        )
        store.save_meta(source_run_id, source_meta)

    target, route_resolution = _resolve_callback_target_for_run(source_meta)
    route_resolution_v1 = __getattr__("_compact_route_resolution_v1")(route_resolution)
    if route_resolution_v1:
        source_meta["route_resolution"] = route_resolution_v1
        source_meta["callback_last_route_resolution"] = route_resolution_v1
    if not target:
        if not route_resolution_v1:
            source_meta["callback_last_route_resolution"] = route_resolution
        _persist_callback_view(
            dispatch_state="pending",
            dispatch_run_id="",
            route_mismatch_flag=False,
            event="unverified",
            route_resolution_in=route_resolution,
        )
        return ""

    target_session_id = str(target.get("session_id") or "").strip()
    target_channel_name = str(target.get("channel_name") or "").strip()
    if not (target_session_id and _looks_like_uuid(target_session_id) and target_channel_name):
        route_resolution = dict(route_resolution or {})
        route_resolution["fallback_reasons"] = list(route_resolution.get("fallback_reasons") or []) + [
            "resolved_target_invalid"
        ]
        route_resolution_v1 = __getattr__("_compact_route_resolution_v1")(route_resolution)
        if route_resolution_v1:
            source_meta["route_resolution"] = route_resolution_v1
            source_meta["callback_last_route_resolution"] = route_resolution_v1
        else:
            source_meta["callback_last_route_resolution"] = route_resolution
        _persist_callback_view(
            dispatch_state="pending",
            dispatch_run_id="",
            route_mismatch_flag=False,
            event="unverified",
            route_resolution_in=route_resolution,
        )
        return ""

    dispatch_key = _callback_dispatch_key(
        str(source_meta.get("projectId") or "").strip(),
        source_run_id,
        event_type,
        target_session_id,
    )
    dispatch_claimed = False
    try:
        dispatch_claimed, latest_source_meta, existing_callback_run_id = _claim_callback_dispatch_key(
            store,
            source_run_id,
            dispatch_key,
        )
        if existing_callback_run_id:
            return existing_callback_run_id
        if not dispatch_claimed:
            return ""
        if isinstance(latest_source_meta, dict) and latest_source_meta:
            source_meta = latest_source_meta
            if str(source_meta.get("id") or "").strip() != source_run_id:
                source_meta["id"] = source_run_id

        source_session_id = str(source_meta.get("sessionId") or "").strip()
        source_channel_name = _resolve_source_channel_text(source_meta)
        if (
            source_session_id
            and source_session_id == target_session_id
            and source_channel_name
            and source_channel_name == target_channel_name
        ):
            _append_source_callback_dispatch(
                store,
                source_meta,
                dispatch_key=dispatch_key,
                event_type=event_type,
                target=target,
                status="self_suppressed",
                note="self_target_same_channel_session",
            )
            _persist_callback_view(
                dispatch_state="pending",
                dispatch_run_id="",
                route_mismatch_flag=False,
                event="unverified",
                route_resolution_in=route_resolution,
            )
            return ""

        profile = _extract_callback_progress_profile(source_meta, event_type)
        route_mismatch = bool(source_session_id and target_session_id and source_session_id != target_session_id)
        dispatch_state = "route_mismatch" if route_mismatch else "resolved"
        merge_note = ""
        anchor_key = _callback_anchor_key(
            project_id=str(source_meta.get("projectId") or "").strip(),
            target_channel=target_channel_name,
            target_session_id=target_session_id,
            event_type=event_type,
            profile=profile,
        )
        use_queue_aggregator = _callback_queue_aggregator_enabled()
        msg = ""
        receipt_summary: dict[str, Any] = {}
        communication_view: dict[str, Any] = {}

        def _rebuild_callback_payloads() -> None:
            nonlocal communication_view, msg, receipt_summary
            msg, receipt_summary, communication_view = runtime_build_callback_dispatch_payloads(
                source_meta=source_meta,
                event_type=event_type,
                event_reason=event_reason,
                target=target,
                route_resolution=route_resolution,
                profile=profile,
                route_mismatch=route_mismatch,
                dispatch_state=dispatch_state,
                build_terminal_callback_message=_build_terminal_callback_message,
                build_terminal_receipt_summary=_build_terminal_receipt_summary,
                build_callback_communication_view=_build_callback_communication_view,
            )

        def _refresh_source_meta_for_dispatch() -> None:
            nonlocal source_meta
            latest = dict(store.load_meta(source_run_id) or {})
            if latest:
                source_meta = latest
                if str(source_meta.get("id") or "").strip() != source_run_id:
                    source_meta["id"] = source_run_id
                if route_resolution_v1:
                    source_meta["route_resolution"] = route_resolution_v1
                    source_meta["callback_last_route_resolution"] = route_resolution_v1

        lock_ctx = _callback_anchor_mutex(anchor_key) if use_queue_aggregator else nullcontext()
        with lock_ctx:
            if use_queue_aggregator:
                _refresh_source_meta_for_dispatch()
                existing_callback_run_id = _source_callback_dispatch_run_id(source_meta, dispatch_key)
                if existing_callback_run_id:
                    return existing_callback_run_id
                if _source_has_callback_dispatch(source_meta, dispatch_key):
                    return ""
                _rebuild_callback_payloads()
                merge_result = _try_merge_callback_into_queue_anchor(
                    store,
                    source_meta=source_meta,
                    event_type=event_type,
                    target=target,
                    profile=profile,
                    merged_message=msg,
                )
                if bool(merge_result.get("merged")):
                    anchor_run_id = str(merge_result.get("anchor_run_id") or "").strip()
                    if anchor_run_id:
                        _append_source_callback_dispatch(
                            store,
                            source_meta,
                            dispatch_key=dispatch_key,
                            event_type=event_type,
                            target=target,
                            status="merged_anchor",
                            callback_run_id=anchor_run_id,
                            note=str(merge_result.get("note") or "merged_anchor"),
                        )
                        _persist_callback_view(
                            dispatch_state=dispatch_state,
                            dispatch_run_id=anchor_run_id,
                            route_mismatch_flag=route_mismatch,
                            event="route_mismatch" if route_mismatch else "success",
                            route_resolution_in=route_resolution,
                        )
                        anchor_meta = store.load_meta(anchor_run_id) or {}
                        _project_receipt_to_host_run(
                            store,
                            source_meta=source_meta,
                            callback_meta=anchor_meta,
                            callback_run_id=anchor_run_id,
                            event_type=event_type,
                            event_reason=event_reason,
                            dispatch_status="merged_anchor",
                            route_resolution=route_resolution,
                        )
                        return anchor_run_id
                merge_note = str(merge_result.get("note") or "").strip()
                if merge_note == "no_anchor":
                    merge_note = "new_anchor_created:no_anchor"
                _refresh_source_meta_for_dispatch()
                existing_callback_run_id = _source_callback_dispatch_run_id(source_meta, dispatch_key)
                if existing_callback_run_id:
                    return existing_callback_run_id
                if _source_has_callback_dispatch(source_meta, dispatch_key):
                    return ""
            else:
                dispatch_now, suppress_note = _register_callback_window(
                    store,
                    source_meta,
                    event_type=event_type,
                    target=target,
                    route_resolution=route_resolution,
                    scheduler=scheduler,
                )
                if not dispatch_now:
                    _append_source_callback_dispatch(
                        store,
                        source_meta,
                        dispatch_key=dispatch_key,
                        event_type=event_type,
                        target=target,
                        status="suppressed_window",
                        note=suppress_note,
                    )
                    _persist_callback_view(
                        dispatch_state="fallback",
                        dispatch_run_id="",
                        route_mismatch_flag=False,
                        event="unverified",
                        route_resolution_in=route_resolution,
                    )
                    return ""
                merge_note = str(suppress_note or "").strip()

            _rebuild_callback_payloads()
            anchor_created_at = _now_iso()
            anchor_action = "created_new_anchor"
            if merge_note.startswith("merge_failed_new_anchor:"):
                anchor_action = "degraded_new_anchor"
            elif merge_note.startswith("anchor_overflow_new_anchor"):
                anchor_action = "overflow_new_anchor"
            callback_run = store.create_run(
                str(source_meta.get("projectId") or "").strip(),
                target_channel_name,
                target_session_id,
                msg,
                profile_label="",
                cli_type=_resolve_callback_target_cli_type(
                    store,
                    source_meta=source_meta,
                    target=target,
                ),
                sender_type="system",
                sender_id="system",
                sender_name="系统",
                extra_meta=runtime_build_callback_run_extra_meta(
                    event_type=event_type,
                    event_reason=event_reason,
                    source_run_id=source_run_id,
                    source_meta=source_meta,
                    profile=profile,
                    route_resolution=route_resolution,
                    communication_view=communication_view,
                    receipt_summary=receipt_summary,
                    callback_anchor_key=anchor_key,
                    anchor_created_at=anchor_created_at,
                    callback_anchor_action=anchor_action,
                ),
            )
            callback_run_id = str(callback_run.get("id") or "").strip()
            if not callback_run_id:
                store.save_meta(source_run_id, source_meta)
                return ""

            callback_meta = store.load_meta(callback_run_id) or {}
            callback_meta, source_meta = runtime_apply_callback_dispatch_views(
                callback_meta=callback_meta,
                source_meta=source_meta,
                callback_run_id=callback_run_id,
                event_reason="route_mismatch" if route_mismatch else "success",
                dispatch_state=dispatch_state,
                route_mismatch=route_mismatch,
                route_resolution=route_resolution,
                build_callback_communication_view=_build_callback_communication_view,
            )
            store.save_meta(callback_run_id, callback_meta)
            _append_source_callback_dispatch(
                store,
                source_meta,
                dispatch_key=dispatch_key,
                event_type=event_type,
                target=target,
                status="sent",
                callback_run_id=callback_run_id,
                note=merge_note,
            )
            __getattr__("_enqueue_run_execution")(
                store,
                callback_run_id,
                target_session_id,
                str(callback_run.get("cliType") or "codex"),
                scheduler,
            )
            _project_receipt_to_host_run(
                store,
                source_meta=source_meta,
                callback_meta=callback_meta,
                callback_run_id=callback_run_id,
                event_type=event_type,
                event_reason=event_reason,
                dispatch_status="sent",
                route_resolution=route_resolution,
            )
            return callback_run_id
    finally:
        if dispatch_claimed:
            _release_callback_dispatch_key(dispatch_key)
