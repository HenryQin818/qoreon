# -*- coding: utf-8 -*-

from __future__ import annotations

from typing import Any


def build_callback_dispatch_payloads(
    *,
    source_meta: dict[str, Any],
    event_type: str,
    event_reason: str,
    target: dict[str, Any],
    route_resolution: dict[str, Any],
    profile: dict[str, Any],
    route_mismatch: bool,
    dispatch_state: str,
    build_terminal_callback_message: Any,
    build_terminal_receipt_summary: Any,
    build_callback_communication_view: Any,
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    event_name = "route_mismatch" if bool(route_mismatch) else "success"
    msg = build_terminal_callback_message(
        source_meta,
        event_type=str(event_type or "").strip(),
        event_reason=str(event_reason or "").strip(),
        target=target,
        route_resolution=route_resolution,
    )
    receipt_summary = build_terminal_receipt_summary(
        source_meta,
        event_type=str(event_type or "").strip(),
        event_reason=str(event_reason or "").strip(),
        target=target,
        route_resolution=route_resolution,
        profile=profile,
    )
    communication_view = build_callback_communication_view(
        source_meta,
        event_reason=event_name,
        dispatch_state=str(dispatch_state or "").strip(),
        dispatch_run_id="",
        route_mismatch=bool(route_mismatch),
        route_resolution=route_resolution,
    )
    return msg, receipt_summary, communication_view


def build_callback_run_extra_meta(
    *,
    event_type: str,
    event_reason: str,
    source_run_id: str,
    source_meta: dict[str, Any],
    profile: dict[str, Any],
    route_resolution: dict[str, Any],
    communication_view: dict[str, Any],
    receipt_summary: dict[str, Any],
    callback_anchor_key: str,
    anchor_created_at: str,
    callback_anchor_action: str,
) -> dict[str, Any]:
    rid = str(source_run_id or "").strip()
    return {
        "trigger_type": "callback_auto",
        "event_type": str(event_type or "").strip(),
        "event_reason": str(event_reason or "").strip(),
        "source_run_id": rid,
        "task_path": str(source_meta.get("task_path") or "").strip(),
        "execution_mode": str(source_meta.get("execution_mode") or "").strip().lower(),
        "execution_stage": str(profile.get("stage") or "").strip().lower(),
        "blocking_status": str(profile.get("blocking_status") or "").strip().lower(),
        "current_conclusion": str(profile.get("current_conclusion") or "").strip(),
        "need_confirmation": str(profile.get("need_confirmation") or "").strip(),
        "next_action": str(profile.get("next_step") or "").strip(),
        "feedback_file_path": str(source_meta.get("feedback_file_path") or "").strip(),
        "route_resolution": route_resolution,
        "communication_view": communication_view,
        "receipt_summary": receipt_summary,
        "callback_anchor_key": str(callback_anchor_key or "").strip(),
        "callback_aggregate_count": 1,
        "callback_last_merged_at": str(anchor_created_at or "").strip(),
        "callback_aggregate_source_run_ids": [rid],
        "callback_summary_of": [rid],
        "callback_merge_mode": "queue_anchor_v2",
        "callback_anchor_action": str(callback_anchor_action or "").strip(),
    }


def apply_callback_dispatch_views(
    *,
    callback_meta: dict[str, Any],
    source_meta: dict[str, Any],
    callback_run_id: str,
    event_reason: str,
    dispatch_state: str,
    route_mismatch: bool,
    route_resolution: dict[str, Any],
    build_callback_communication_view: Any,
) -> tuple[dict[str, Any], dict[str, Any]]:
    callback_id = str(callback_run_id or "").strip()
    out_callback_meta = dict(callback_meta if isinstance(callback_meta, dict) else {})
    out_source_meta = dict(source_meta if isinstance(source_meta, dict) else {})
    out_callback_meta["communication_view"] = dict(
        out_callback_meta.get("communication_view") or {},
        dispatch_run_id=callback_id,
    )
    out_source_meta["communication_view"] = build_callback_communication_view(
        out_source_meta,
        event_reason=str(event_reason or "").strip(),
        dispatch_state=str(dispatch_state or "").strip(),
        dispatch_run_id=callback_id,
        route_mismatch=bool(route_mismatch),
        route_resolution=route_resolution,
    )
    return out_callback_meta, out_source_meta
