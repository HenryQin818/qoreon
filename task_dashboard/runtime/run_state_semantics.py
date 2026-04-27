# -*- coding: utf-8 -*-

from __future__ import annotations

from typing import Any

from task_dashboard.helpers import parse_iso_ts, safe_text


_SYSTEM_MESSAGE_KINDS = {
    "system_callback",
    "system_callback_summary",
    "restart_recovery_summary",
}
_SYSTEM_TRIGGER_TYPES = {
    "callback_auto",
    "callback_auto_summary",
    "restart_recovery_summary",
}
_PREVIEW_OUTCOME_STATES = {"success", "failed_business"}
_HEALTH_OUTCOME_STATES = {
    "success",
    "interrupted_infra",
    "interrupted_user",
    "failed_config",
    "failed_business",
    "recovered_notice",
}


def _normalize_text(value: Any, max_len: int = 300) -> str:
    return safe_text(str(value or "").replace("\r\n", "\n").strip(), max_len).strip()


def _latest_process_row_preview(process_rows: Any, max_len: int = 300) -> str:
    rows = process_rows if isinstance(process_rows, list) else []
    for row in reversed(rows):
        if isinstance(row, dict):
            text = _normalize_text(row.get("text"), max_len=max_len)
        else:
            text = _normalize_text(row, max_len=max_len)
        if text:
            return text
    return ""


def _run_preview_parts(meta: dict[str, Any]) -> dict[str, str]:
    process_rows = meta.get("processRows") or meta.get("process_rows") or []
    ai_preview = _normalize_text(
        meta.get("generated_media_summary") or meta.get("lastPreview") or meta.get("partialPreview"),
        max_len=300,
    )
    if not ai_preview:
        ai_preview = _latest_process_row_preview(process_rows, max_len=300)
    user_preview = _normalize_text(meta.get("messagePreview"), max_len=260)
    preview = ai_preview or user_preview
    return {
        "ai_preview": ai_preview,
        "user_preview": user_preview,
        "preview": preview,
    }


def _run_created_at(meta: dict[str, Any]) -> str:
    return str(
        meta.get("createdAt")
        or meta.get("startedAt")
        or meta.get("finishedAt")
        or ""
    ).strip()


def _run_created_ts(meta: dict[str, Any]) -> float:
    return (
        parse_iso_ts(meta.get("createdAt"))
        or parse_iso_ts(meta.get("startedAt"))
        or parse_iso_ts(meta.get("finishedAt"))
        or 0.0
    )


def _is_system_run(meta: dict[str, Any]) -> bool:
    sender_type = str(meta.get("sender_type") or meta.get("senderType") or "").strip().lower()
    message_kind = str(meta.get("message_kind") or meta.get("messageKind") or "").strip().lower()
    trigger_type = str(meta.get("trigger_type") or meta.get("triggerType") or "").strip().lower()
    return (
        sender_type == "system"
        or message_kind in _SYSTEM_MESSAGE_KINDS
        or trigger_type in _SYSTEM_TRIGGER_TYPES
    )


def _recovery_of_run_id(meta: dict[str, Any]) -> str:
    direct = str(meta.get("restartRecoveryOf") or meta.get("recovery_of_run_id") or "").strip()
    if direct:
        return direct
    source_run_ids = meta.get("restartRecoverySourceRunIds")
    if isinstance(source_run_ids, list):
        for item in source_run_ids:
            run_id = str(item or "").strip()
            if run_id:
                return run_id
    return ""


def _restart_recovery_run_id(meta: dict[str, Any]) -> str:
    return str(meta.get("restartRecoveryRunId") or meta.get("superseded_by_run_id") or "").strip()


def classify_run_semantics(meta: dict[str, Any]) -> dict[str, Any]:
    row = meta if isinstance(meta, dict) else {}
    status = str(row.get("status") or "").strip().lower()
    trigger_type = str(row.get("trigger_type") or row.get("triggerType") or "").strip().lower()
    message_kind = str(row.get("message_kind") or row.get("messageKind") or "").strip().lower()
    previews = _run_preview_parts(row)
    preview = previews["preview"]
    error_text = " ".join(
        [
            str(row.get("error") or ""),
            preview,
            str(row.get("lastPreview") or ""),
            str(row.get("partialPreview") or ""),
            str(row.get("messagePreview") or ""),
        ]
    ).lower()
    is_system_run = _is_system_run(row)

    outcome_state = ""
    error_class = ""
    if trigger_type == "restart_recovery_summary" or message_kind == "restart_recovery_summary":
        outcome_state = "recovered_notice"
        error_class = "infra_restart_recovered"
    elif status == "done":
        outcome_state = "success"
    elif status == "error":
        if "run interrupted (server restarted or process exited)" in error_text:
            outcome_state = "interrupted_infra"
            error_class = "infra_restart"
        elif "queued orphan recovered" in error_text:
            outcome_state = "recovered_notice"
            error_class = "infra_restart_recovered"
        elif "no conversation found with session id" in error_text:
            outcome_state = "failed_config"
            error_class = "session_binding"
        elif (
            "permission denied" in error_text
            or "external_directory" in error_text
            or "rejected permission to use this specific tool call" in error_text
        ):
            outcome_state = "failed_config"
            error_class = "workspace_permission"
        elif "interrupted by user" in error_text or "cancelled by user" in error_text or "canceled by user" in error_text:
            outcome_state = "interrupted_user"
        elif "syntaxerror" in error_text:
            outcome_state = "failed_config"
            error_class = "cli_path"
        else:
            outcome_state = "failed_business"

    effective_for_session_health = bool(outcome_state) and (
        outcome_state == "recovered_notice"
        or (outcome_state in _HEALTH_OUTCOME_STATES and not is_system_run)
    )
    effective_for_session_preview = outcome_state in _PREVIEW_OUTCOME_STATES and not is_system_run

    return {
        "outcome_state": outcome_state,
        "error_class": error_class,
        "effective_for_session_health": bool(effective_for_session_health),
        "effective_for_session_preview": bool(effective_for_session_preview),
        "superseded_by_run_id": "",
        "recovery_of_run_id": _recovery_of_run_id(row),
        "restart_recovery_run_id": _restart_recovery_run_id(row),
        "is_system_run": bool(is_system_run),
        "preview": preview,
        "created_at": _run_created_at(row),
        "created_ts": _run_created_ts(row),
    }


def _session_health_state_from_fields(fields: dict[str, Any]) -> str:
    outcome = str(fields.get("outcome_state") or "").strip().lower()
    recovery_status = str(fields.get("restart_recovery_status") or "").strip().lower()
    if outcome in {"success", "recovered_notice"}:
        return "healthy"
    if outcome == "failed_config":
        return "blocked"
    if outcome == "interrupted_infra" and recovery_status in {"queued", "running", "retry_waiting"}:
        return "recovering"
    if outcome in {"interrupted_infra", "interrupted_user", "failed_business"}:
        return "attention"
    return "healthy"


def _summary_object(run_id: str, fields: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": str(run_id or "").strip(),
        "outcome_state": str(fields.get("outcome_state") or "").strip(),
        "preview": str(fields.get("preview") or "").strip(),
        "created_at": str(fields.get("created_at") or "").strip(),
    }


def build_session_semantics(runs: list[dict[str, Any]]) -> dict[str, Any]:
    meta_by_id: dict[str, dict[str, Any]] = {}
    ordered: list[tuple[float, str, dict[str, Any]]] = []
    for meta in runs:
        if not isinstance(meta, dict):
            continue
        run_id = str(meta.get("id") or "").strip()
        if not run_id:
            continue
        meta_by_id[run_id] = meta
        fields = classify_run_semantics(meta)
        ordered.append((float(fields.get("created_ts") or 0.0), run_id, dict(fields)))
    ordered.sort(key=lambda item: (item[0], item[1]))

    per_run_fields: dict[str, dict[str, Any]] = {}
    unresolved_interrupt_ids: list[str] = []
    latest_effective_business_summary: dict[str, Any] = {}
    latest_system_summary: dict[str, Any] = {}
    latest_health_fields: dict[str, Any] = {}

    for _created_ts, run_id, fields in ordered:
        restart_recovery_run_id = str(fields.get("restart_recovery_run_id") or "").strip()
        restart_recovery_status = str((meta_by_id.get(restart_recovery_run_id) or {}).get("status") or "").strip().lower()
        per_run_fields[run_id] = {
            "outcome_state": str(fields.get("outcome_state") or "").strip(),
            "error_class": str(fields.get("error_class") or "").strip(),
            "effective_for_session_health": bool(fields.get("effective_for_session_health")),
            "effective_for_session_preview": bool(fields.get("effective_for_session_preview")),
            "superseded_by_run_id": "",
            "recovery_of_run_id": str(fields.get("recovery_of_run_id") or "").strip(),
        }
        outcome_state = str(fields.get("outcome_state") or "").strip()
        if outcome_state == "interrupted_infra":
            unresolved_interrupt_ids.append(run_id)
        elif outcome_state == "recovered_notice":
            source_run_id = str(fields.get("recovery_of_run_id") or "").strip()
            if (not source_run_id) and unresolved_interrupt_ids:
                source_run_id = unresolved_interrupt_ids.pop()
            if source_run_id:
                per_run_fields[run_id]["recovery_of_run_id"] = source_run_id
                source_fields = per_run_fields.get(source_run_id)
                if isinstance(source_fields, dict):
                    source_fields["superseded_by_run_id"] = run_id
                    source_fields["effective_for_session_health"] = False
                unresolved_interrupt_ids = [item for item in unresolved_interrupt_ids if item != source_run_id]
        elif outcome_state == "success" and unresolved_interrupt_ids:
            while unresolved_interrupt_ids:
                source_run_id = unresolved_interrupt_ids.pop()
                source_fields = per_run_fields.get(source_run_id)
                if isinstance(source_fields, dict):
                    source_fields["superseded_by_run_id"] = run_id
                    source_fields["effective_for_session_health"] = False

        if fields.get("effective_for_session_health"):
            latest_health_fields = {
                **fields,
                "restart_recovery_status": restart_recovery_status,
            }
        if fields.get("effective_for_session_preview"):
            latest_effective_business_summary = _summary_object(run_id, fields)
        elif outcome_state == "recovered_notice" and str(fields.get("preview") or "").strip():
            latest_system_summary = _summary_object(run_id, fields)

    return {
        "run_fields": per_run_fields,
        "session_health_state": _session_health_state_from_fields(latest_health_fields),
        "latest_effective_run_summary": latest_effective_business_summary,
        "latest_system_summary": latest_system_summary,
    }
