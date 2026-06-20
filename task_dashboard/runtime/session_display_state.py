# -*- coding: utf-8 -*-

from __future__ import annotations

from typing import Any

from task_dashboard.runtime.run_detail_fields import safe_terminal_visible_text


WORKING_SESSION_DISPLAY_STATES = {"running", "queued", "retry_waiting", "external_busy"}
TERMINAL_RUN_STATES = {"done", "error"}
ALLOWED_SESSION_DISPLAY_STATES = WORKING_SESSION_DISPLAY_STATES | TERMINAL_RUN_STATES | {"idle"}
SYSTEM_MESSAGE_KINDS = {"system_callback", "system_callback_summary", "restart_recovery_summary"}
SYSTEM_TRIGGER_TYPES = {"callback_auto", "callback_auto_summary", "restart_recovery_summary"}


def _normalize_provider_error(raw: Any) -> dict[str, Any]:
    src = raw if isinstance(raw, dict) else {}
    matched = src.get("matched_patterns")
    return {
        "kind": str(src.get("kind") or "").strip(),
        "retryable": bool(src.get("retryable")),
        "matched_patterns": list(matched) if isinstance(matched, list) else [],
    }


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _pick_text(src: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        text = str(src.get(key) or "").strip()
        if text:
            return text
    return ""


def _coerce_int(value: Any) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def _lower_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _has_structured_ref(value: Any) -> bool:
    return isinstance(value, dict) and any(str(item or "").strip() for item in value.values())


def _active_run_signal(src: dict[str, Any], runtime: dict[str, Any]) -> dict[str, Any]:
    communication_view = src.get("communication_view") if isinstance(src.get("communication_view"), dict) else {}
    message_kind = _lower_text(
        src.get("message_kind") or src.get("messageKind") or communication_view.get("message_kind") or communication_view.get("messageKind")
    )
    interaction_mode = _lower_text(src.get("interaction_mode") or src.get("interactionMode"))
    sender_type = _lower_text(src.get("sender_type") or src.get("senderType") or src.get("last_sender_type"))
    trigger_type = _lower_text(src.get("trigger_type") or src.get("triggerType"))
    visible = _coerce_bool(src.get("visible_in_channel_chat") or src.get("visibleInChannelChat"))
    source_ref = src.get("source_ref") if isinstance(src.get("source_ref"), dict) else {}
    callback_to = src.get("callback_to") if isinstance(src.get("callback_to"), dict) else {}
    source_run_id = _pick_text(src, ("source_run_id", "sourceRunId"))
    run_id = _pick_text(src, ("latest_run_id", "run_id", "id"))
    active_run_id = str(runtime.get("active_run_id") or "").strip()
    if active_run_id and run_id and active_run_id != run_id:
        run_id = active_run_id
    if not source_run_id:
        source_run_id = run_id
    status = _lower_text(src.get("latest_status") or src.get("status") or runtime.get("display_state"))
    failure_class = _lower_text(src.get("failure_class"))
    provider_error = src.get("provider_error") if isinstance(src.get("provider_error"), dict) else {}
    provider_error_kind = _lower_text(provider_error.get("kind")) if provider_error else ""
    is_provider_transient = bool(failure_class == "provider_transient" or provider_error_kind)
    is_system = bool(
        sender_type == "system"
        or message_kind in SYSTEM_MESSAGE_KINDS
        or trigger_type in SYSTEM_TRIGGER_TYPES
    )
    has_source_ref = _has_structured_ref(source_ref)
    has_callback_to = _has_structured_ref(callback_to)
    is_legacy = bool(sender_type == "legacy")
    missing_projection_refs = bool(
        (not message_kind)
        or (message_kind == "collab_update" and not has_source_ref)
        or (interaction_mode == "task_with_receipt" and not has_callback_to)
    )

    visibility = "missing"
    reason = "unknown"
    has_projectable = False
    display_state = _lower_text(runtime.get("display_state"))
    if (not active_run_id) and (display_state in {"queued", "retry_waiting"} or str(runtime.get("queued_run_id") or "").strip()):
        reason = "queued_no_active_run"
    elif (not active_run_id) and display_state == "external_busy":
        reason = "external_busy_no_run"
    elif not (run_id or active_run_id):
        reason = "no_active_run"
    elif is_provider_transient and status == "error":
        visibility = "projectable" if visible and not (is_system or is_legacy or missing_projection_refs) else "hidden"
        has_projectable = visibility == "projectable"
        reason = "provider_transient_failure"
    elif not visible:
        visibility = "hidden"
        reason = "hidden_message"
    elif is_system:
        visibility = "system_only"
        reason = "system_callback"
    elif is_legacy:
        visibility = "legacy_unknown"
        reason = "legacy_missing_refs"
    elif missing_projection_refs:
        visibility = "visible_unprojectable"
        if not message_kind:
            reason = "missing_message_kind"
        elif message_kind == "collab_update" and not has_source_ref:
            reason = "missing_source_ref"
        elif interaction_mode == "task_with_receipt" and not has_callback_to:
            reason = "missing_callback_to"
        else:
            reason = "no_projectable_message"
    else:
        visibility = "projectable"
        reason = "ok"
        has_projectable = True

    return {
        "message_kind": message_kind,
        "interaction_mode": interaction_mode,
        "sender_type": sender_type,
        "trigger_type": trigger_type,
        "visible_in_channel_chat": visible,
        "source_run_id": source_run_id,
        "active_run_id": active_run_id,
        "visibility": visibility,
        "projection_reason": reason,
        "has_projectable_message": has_projectable,
        "provider_transient": is_provider_transient,
        "system": is_system,
        "legacy": is_legacy,
        "missing_projection_refs": missing_projection_refs,
    }


def build_runtime_state_explainers(agg: Any, runtime_state: Any = None) -> dict[str, Any]:
    src = agg if isinstance(agg, dict) else {}
    runtime = runtime_state if isinstance(runtime_state, dict) else {}
    signal = _active_run_signal(src, runtime)
    internal_state = _lower_text(runtime.get("internal_state"))
    display_state = _lower_text(runtime.get("display_state"))
    external_busy = bool(runtime.get("external_busy"))
    active_run_id = str(runtime.get("active_run_id") or "").strip()
    queued_run_id = str(runtime.get("queued_run_id") or "").strip()
    health_state = _lower_text(src.get("session_health_state"))
    degraded = bool(runtime.get("degraded"))

    if degraded:
        busy_source = "degraded_unknown"
    elif external_busy and (active_run_id or internal_state in {"running", "queued", "retry_waiting"}):
        busy_source = "mixed"
    elif active_run_id and signal.get("system"):
        busy_source = "system_callback"
    elif active_run_id and signal.get("legacy"):
        busy_source = "legacy_run"
    elif active_run_id or internal_state in {"running", "queued", "retry_waiting"} or queued_run_id:
        busy_source = "internal_run"
    elif external_busy or display_state == "external_busy":
        busy_source = "external_cli"
    elif health_state == "busy":
        busy_source = "health_busy"
    else:
        busy_source = "none"

    if degraded:
        secondary_state = "degraded_unknown"
    elif signal.get("provider_transient"):
        secondary_state = "provider_transient"
    elif busy_source in {"external_cli", "mixed", "health_busy"}:
        secondary_state = "external_busy"
    elif busy_source == "system_callback":
        secondary_state = "system_callback"
    elif busy_source == "legacy_run":
        secondary_state = "legacy_run"
    elif signal.get("projection_reason") not in {"ok", "no_active_run", "queued_no_active_run", "external_busy_no_run"}:
        secondary_state = "missing_projection"
    else:
        secondary_state = "none"

    external_busy_reason = str(runtime.get("external_busy_reason") or src.get("external_busy_reason") or "").strip()
    if not external_busy_reason and busy_source == "mixed":
        external_busy_reason = "mixed_internal_external"
    elif not external_busy_reason and busy_source == "external_cli":
        external_busy_reason = "process_probe"
    elif not external_busy_reason and busy_source == "health_busy":
        external_busy_reason = "health_busy"

    has_active_run = bool(active_run_id)
    return {
        "busy_source": busy_source,
        "display_secondary_state": secondary_state,
        "external_busy_reason": external_busy_reason,
        "active_run_message_kind": str(signal.get("message_kind") or "") if has_active_run else "",
        "active_run_sender_type": str(signal.get("sender_type") or "") if has_active_run else "",
        "active_run_trigger_type": str(signal.get("trigger_type") or "") if has_active_run else "",
        "active_run_visibility": str(signal.get("visibility") or "unknown") if has_active_run else "missing",
        "active_run_projection_reason": str(signal.get("projection_reason") or "unknown") if has_active_run else "no_active_run",
    }


def build_projection_summary(
    agg: Any,
    runtime_state: Any = None,
    *,
    degraded: bool = False,
    degraded_reason: str = "",
) -> dict[str, Any]:
    src = agg if isinstance(agg, dict) else {}
    runtime = runtime_state if isinstance(runtime_state, dict) else {}
    signal = _active_run_signal(src, runtime)
    effective_degraded = bool(degraded or runtime.get("degraded"))
    reason = str(signal.get("projection_reason") or "unknown")
    if effective_degraded and reason in {"unknown", "no_active_run"}:
        reason = "degraded_unknown"
    return {
        "has_projectable_message": bool(signal.get("has_projectable_message")),
        "reason": reason,
        "active_run_id": str(signal.get("active_run_id") or ""),
        "source_run_id": str(signal.get("source_run_id") or ""),
        "message_kind": str(signal.get("message_kind") or ""),
        "interaction_mode": str(signal.get("interaction_mode") or ""),
        "sender_type": str(signal.get("sender_type") or ""),
        "trigger_type": str(signal.get("trigger_type") or ""),
        "visible_in_channel_chat": bool(signal.get("visible_in_channel_chat")),
        "updated_at": _pick_text(
            src,
            (
                "updated_at",
                "lastProgressAt",
                "updatedAt",
                "finishedAt",
                "startedAt",
                "createdAt",
            ),
        ) or str(runtime.get("updated_at") or "").strip(),
        "degraded": bool(effective_degraded),
        "degraded_reason": str(degraded_reason or runtime.get("degraded_reason") or "").strip(),
    }


def normalize_session_display_state(raw: Any, fallback: str = "idle") -> str:
    state = str(raw or "").strip().lower()
    if state in ALLOWED_SESSION_DISPLAY_STATES:
        return state
    fb = str(fallback or "idle").strip().lower()
    return fb if fb in ALLOWED_SESSION_DISPLAY_STATES else "idle"


def build_latest_run_summary(agg: Any) -> dict[str, Any]:
    src = agg if isinstance(agg, dict) else {}
    provider_error = src.get("provider_error")
    cli_type = str(src.get("latest_cli_type") or src.get("cliType") or src.get("cli_type") or "codex").strip() or "codex"
    summary = {
        "run_id": str(src.get("latest_run_id") or "").strip(),
        "status": normalize_session_display_state(src.get("latest_status"), "idle"),
        "updated_at": str(src.get("updated_at") or "").strip(),
        "preview": safe_terminal_visible_text(src.get("last_preview"), cli_type=cli_type),
        "speaker": str(src.get("last_speaker") or "assistant").strip() or "assistant",
        "sender_type": str(src.get("last_sender_type") or "").strip(),
        "sender_name": str(src.get("last_sender_name") or "").strip(),
        "sender_source": str(src.get("last_sender_source") or "").strip(),
        "latest_user_msg": str(src.get("latest_user_msg") or "").strip(),
        "latest_ai_msg": safe_terminal_visible_text(src.get("latest_ai_msg"), cli_type=cli_type),
        "error": str(src.get("last_error") or "").strip(),
        "run_count": int(src.get("run_count") or 0),
    }
    failure_class = str(src.get("failure_class") or "").strip().lower()
    if failure_class:
        summary["failure_class"] = failure_class
    error_class = str(src.get("error_class") or "").strip().lower()
    if error_class:
        summary["error_class"] = error_class
    if isinstance(provider_error, dict) and provider_error:
        summary["provider_error"] = _normalize_provider_error(provider_error)
    side_effect_risk = str(src.get("side_effect_risk") or "").strip().lower()
    if side_effect_risk:
        summary["side_effect_risk"] = side_effect_risk
    recovery_mode = str(src.get("recovery_mode") or "").strip().lower()
    if recovery_mode:
        summary["recovery_mode"] = recovery_mode
    if "recovery_required" in src:
        summary["recovery_required"] = bool(src.get("recovery_required"))
    if "retry_exhausted" in src or "providerRetryExhausted" in src:
        summary["retry_exhausted"] = bool(src.get("retry_exhausted") or src.get("providerRetryExhausted"))
    return summary


def build_latest_effective_run_summary(agg: Any) -> dict[str, Any]:
    src = agg if isinstance(agg, dict) else {}
    summary = src.get("latest_effective_run_summary")
    if isinstance(summary, dict) and summary:
        out = {
            "run_id": str(summary.get("run_id") or "").strip(),
            "outcome_state": str(summary.get("outcome_state") or "").strip(),
            "preview": str(summary.get("preview") or "").strip(),
            "created_at": str(summary.get("created_at") or "").strip(),
        }
        failure_class = str(summary.get("failure_class") or "").strip().lower()
        if failure_class:
            out["failure_class"] = failure_class
        error_class = str(summary.get("error_class") or "").strip().lower()
        if error_class:
            out["error_class"] = error_class
        provider_error = summary.get("provider_error")
        if isinstance(provider_error, dict) and provider_error:
            out["provider_error"] = _normalize_provider_error(provider_error)
        side_effect_risk = str(summary.get("side_effect_risk") or "").strip().lower()
        if side_effect_risk:
            out["side_effect_risk"] = side_effect_risk
        recovery_mode = str(summary.get("recovery_mode") or "").strip().lower()
        if recovery_mode:
            out["recovery_mode"] = recovery_mode
        if "recovery_required" in summary:
            out["recovery_required"] = bool(summary.get("recovery_required"))
        if "retry_exhausted" in summary or "providerRetryExhausted" in summary:
            out["retry_exhausted"] = bool(summary.get("retry_exhausted") or summary.get("providerRetryExhausted"))
        return out
    run_id = str(src.get("latest_effective_run_id") or "").strip()
    outcome_state = str(src.get("latest_effective_outcome_state") or "").strip()
    created_at = str(src.get("latest_effective_created_at") or "").strip()
    if not (run_id and outcome_state and created_at):
        return {}
    out = {
        "run_id": run_id,
        "outcome_state": outcome_state,
        "preview": str(src.get("latest_effective_preview") or "").strip(),
        "created_at": created_at,
    }
    failure_class = str(src.get("latest_effective_failure_class") or "").strip().lower()
    if failure_class:
        out["failure_class"] = failure_class
    error_class = str(src.get("latest_effective_error_class") or "").strip().lower()
    if error_class:
        out["error_class"] = error_class
    provider_error = src.get("latest_effective_provider_error")
    if isinstance(provider_error, dict) and provider_error:
        out["provider_error"] = _normalize_provider_error(provider_error)
    side_effect_risk = str(src.get("latest_effective_side_effect_risk") or "").strip().lower()
    if side_effect_risk:
        out["side_effect_risk"] = side_effect_risk
    recovery_mode = str(src.get("latest_effective_recovery_mode") or "").strip().lower()
    if recovery_mode:
        out["recovery_mode"] = recovery_mode
    if "latest_effective_recovery_required" in src:
        out["recovery_required"] = bool(src.get("latest_effective_recovery_required"))
    if "latest_effective_retry_exhausted" in src:
        out["retry_exhausted"] = bool(src.get("latest_effective_retry_exhausted"))
    return out


def build_communication_status_summary(
    agg: Any,
    runtime_state: Any = None,
    *,
    degraded: bool = False,
    degraded_reason: str = "",
) -> dict[str, Any]:
    src = agg if isinstance(agg, dict) else {}
    runtime = runtime_state if isinstance(runtime_state, dict) else {}
    communication_view = src.get("communication_view") if isinstance(src.get("communication_view"), dict) else {}
    receipt_rollup = src.get("receipt_rollup") if isinstance(src.get("receipt_rollup"), dict) else {}
    receipt_items = src.get("receipt_items") if isinstance(src.get("receipt_items"), list) else []
    receipt_pending = src.get("receipt_pending_actions") if isinstance(src.get("receipt_pending_actions"), list) else []
    run_id = _pick_text(src, ("source_run_id", "latest_run_id", "run_id", "id"))
    updated_at = _pick_text(
        src,
        (
            "updated_at",
            "lastProgressAt",
            "updatedAt",
            "finishedAt",
            "startedAt",
            "createdAt",
        ),
    )
    status = str(src.get("latest_status") or src.get("status") or runtime.get("display_state") or "").strip().lower()
    dispatch_state = str(
        communication_view.get("dispatch_state") or communication_view.get("dispatchState") or ""
    ).strip().lower()
    dispatch_run_id = str(
        communication_view.get("dispatch_run_id") or communication_view.get("dispatchRunId") or ""
    ).strip()
    event_reason = str(
        communication_view.get("event_reason") or communication_view.get("eventReason") or ""
    ).strip().lower()
    route_mismatch = bool(
        communication_view.get("route_mismatch") or communication_view.get("routeMismatch")
    )
    visible = _coerce_bool(src.get("visible_in_channel_chat") or src.get("visibleInChannelChat"))

    if route_mismatch or dispatch_state == "route_mismatch":
        delivery_state = "route_mismatch"
    elif visible or event_reason == "success" or (dispatch_state in {"resolved", "fallback"} and dispatch_run_id):
        delivery_state = "delivered"
    elif dispatch_state == "pending" or status in WORKING_SESSION_DISPLAY_STATES:
        delivery_state = "pending"
    elif status == "error":
        delivery_state = "failed"
    else:
        delivery_state = "unknown"

    interaction_mode = str(src.get("interaction_mode") or src.get("interactionMode") or "").strip().lower()
    receipt_required = bool(
        _coerce_bool(src.get("receipt_required") or src.get("receiptRequired"))
        or interaction_mode == "task_with_receipt"
    )
    if not receipt_required:
        receipt_state = "not_required"
    elif receipt_pending:
        receipt_state = "action_required"
    elif receipt_items or _coerce_int(receipt_rollup.get("total_count") or receipt_rollup.get("count")):
        receipt_state = "received"
    elif delivery_state == "delivered":
        receipt_state = "pending"
    elif delivery_state in {"failed", "route_mismatch"}:
        receipt_state = "blocked"
    else:
        receipt_state = "unknown"

    source_missing = not run_id
    effective_degraded = bool(degraded or source_missing)
    reason = str(degraded_reason or "").strip()
    if effective_degraded and not reason:
        reason = "source_unavailable" if source_missing else "communication_source_unavailable"

    return {
        "delivery_state": delivery_state,
        "receipt_state": receipt_state,
        "receipt_required": bool(receipt_required),
        "source_run_id": run_id,
        "updated_at": updated_at,
        "degraded": bool(effective_degraded),
        "degraded_reason": reason,
        "projection_summary": build_projection_summary(
            src,
            runtime,
            degraded=effective_degraded,
            degraded_reason=reason,
        ),
    }


def build_session_display_fields(runtime_state: Any, agg: Any) -> dict[str, Any]:
    runtime = runtime_state if isinstance(runtime_state, dict) else {}
    src = agg if isinstance(agg, dict) else {}
    runtime_display = normalize_session_display_state(runtime.get("display_state"), "idle")
    latest_summary = build_latest_run_summary(agg)
    latest_effective_run_summary = build_latest_effective_run_summary(agg)
    communication_status_summary = build_communication_status_summary(agg, runtime)
    latest_status = normalize_session_display_state(latest_summary.get("status"), "idle")

    if runtime_display in WORKING_SESSION_DISPLAY_STATES:
        display_state = runtime_display
        reason = f"runtime_state:{runtime_display}"
    elif runtime_display == "error":
        display_state = "error"
        reason = "runtime_state:error"
    elif latest_status == "error":
        display_state = "error"
        reason = "latest_run_summary:error"
    elif latest_status == "done":
        display_state = "done"
        reason = "latest_run_summary:done"
    else:
        display_state = "idle"
        reason = "runtime_state:idle"

    return {
        "session_display_state": display_state,
        "session_display_reason": reason,
        "latest_run_summary": latest_summary,
        "session_health_state": str(src.get("session_health_state") or "").strip(),
        "latest_effective_run_summary": latest_effective_run_summary,
        "communication_status_summary": communication_status_summary,
    }
