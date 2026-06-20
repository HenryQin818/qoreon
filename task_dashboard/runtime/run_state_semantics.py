# -*- coding: utf-8 -*-

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from task_dashboard.helpers import parse_iso_ts, safe_text
from task_dashboard.runtime.provider_failure import classify_run_failure


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
    "provider_transient_failed",
    "recovered_notice",
}
_MEDIA_FILE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".avif", ".html", ".htm"}
_MEDIA_SIGNAL_NEEDLES = (
    "image gen",
    "imagegen",
    "image_gen",
    "generated_images",
    "output/imagegen",
    "codex_imagegen",
)
_OUTPUT_IMAGEGEN_ARTIFACT_RE = re.compile(
    r"output/imagegen/[^\s)>\]]+\.(?:png|jpg|jpeg|webp|gif|avif|html)\b",
    re.IGNORECASE,
)
_WORKING_STATUSES = {"queued", "running", "retry_waiting", "dispatching", "collecting"}
_INTERRUPTED_STATUSES = {"interrupted", "cancelled", "canceled"}
_PROVIDER_TRANSIENT_PATTERNS = (
    (
        "high_demand",
        "high demand",
        re.compile(r"\bhigh demand\b|temporary errors?", re.IGNORECASE),
    ),
    (
        "model_capacity",
        "model capacity",
        re.compile(
            r"model[_\s-]?capacity[_\s-]?exhausted|resource[_\s-]?exhausted"
            r"|no capacity available for model",
            re.IGNORECASE,
        ),
    ),
    (
        "rate_limit",
        "rate limit",
        re.compile(r"\b429\b|rate limit(?:ed|ing)?|too many requests", re.IGNORECASE),
    ),
    (
        "server_error",
        "5xx/server unavailable",
        re.compile(
            r"\b(?:500|502|503|504)\b.*(?:openai|provider|upstream|model|temporary|unavailable|server)"
            r"|(?:openai|provider|upstream|model|server).*?\b(?:500|502|503|504)\b"
            r"|internal server error|bad gateway|service unavailable|gateway timeout",
            re.IGNORECASE,
        ),
    ),
    (
        "network_timeout",
        "network/upstream timeout",
        re.compile(
            r"etimedout|econnreset|network reset|connection reset|socket hang up"
            r"|upstream unavailable|upstream timeout|request timed out"
            r"|timed out.*(?:openai|provider|upstream|model)"
            r"|(?:openai|provider|upstream|model).*timed out",
            re.IGNORECASE,
        ),
    ),
)
_SIDE_EFFECT_SIGNAL_RE = re.compile(
    r"announce_run_id|visible_in_channel_chat\s*=\s*true|file_change|apply_patch|write file|wrote file"
    r"|已写|已修改|已发送|部署|发布|删除|归档|moved?|archived?",
    re.IGNORECASE,
)


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


def _iter_text_values(value: Any) -> list[str]:
    rows: list[str] = []
    if value is None:
        return rows
    if isinstance(value, str):
        text = value.strip()
        if text:
            rows.append(text)
        return rows
    if isinstance(value, dict):
        for key in ("text", "message", "summary", "preview", "output", "path"):
            text = str(value.get(key) or "").strip()
            if text:
                rows.append(text)
        return rows
    if isinstance(value, list):
        for item in value:
            rows.extend(_iter_text_values(item))
    return rows


def _attachment_ext(att: dict[str, Any]) -> str:
    name = str(att.get("filename") or att.get("originalName") or "").strip()
    if not name:
        name = str(att.get("url") or att.get("path") or "").split("?", 1)[0].rsplit("/", 1)[-1]
    return str(Path(name).suffix or "").strip().lower()


def _is_generated_media_attachment(att: Any) -> bool:
    if not isinstance(att, dict):
        return False
    if _attachment_ext(att) not in _MEDIA_FILE_EXTS:
        return False
    generated_by = str(att.get("generatedBy") or att.get("generated_by") or "").strip().lower()
    source = str(att.get("source") or "").strip().lower()
    role = str(att.get("attachment_role") or att.get("attachmentRole") or "").strip().lower()
    return generated_by == "codex_imagegen" or source == "generated" or role == "assistant"


def _generated_media_attachment_count(meta: dict[str, Any]) -> int:
    attachments = meta.get("attachments") if isinstance(meta.get("attachments"), list) else []
    return sum(1 for att in attachments if _is_generated_media_attachment(att))


def _generated_media_count(meta: dict[str, Any]) -> int:
    try:
        return max(0, int(meta.get("generated_media_count") or 0))
    except Exception:
        return 0


def _media_signal_evidence(meta: dict[str, Any]) -> list[str]:
    evidence: list[str] = []
    if _generated_media_count(meta) > 0 or str(meta.get("generated_media_summary") or "").strip():
        evidence.append("generated_media_metadata")
    if _generated_media_attachment_count(meta) > 0:
        evidence.append("generated_attachment")

    skills = meta.get("skills_used")
    if isinstance(skills, list):
        normalized_skills = {str(item or "").strip().lower() for item in skills}
        if normalized_skills.intersection({"imagegen", "image_gen"}):
            evidence.append("imagegen_skill")

    text_sources: list[str] = []
    for key in (
        "lastPreview",
        "partialPreview",
        "messagePreview",
        "logPreview",
        "error",
    ):
        text_sources.extend(_iter_text_values(meta.get(key)))
    text_sources.extend(_iter_text_values(meta.get("processRows") or meta.get("process_rows")))
    haystack = "\n".join(text_sources).lower()
    output_fallback_matched = bool(_OUTPUT_IMAGEGEN_ARTIFACT_RE.search(haystack))
    for needle in _MEDIA_SIGNAL_NEEDLES:
        if needle in haystack:
            evidence.append(
                "output_imagegen_fallback"
                if needle == "output/imagegen"
                else ("generated_images_log" if needle == "generated_images" else "imagegen_text")
            )
    if "output_imagegen_fallback" in evidence and not output_fallback_matched:
        evidence = [item for item in evidence if item != "output_imagegen_fallback"]
    out: list[str] = []
    seen: set[str] = set()
    for item in evidence:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out[:8]


def classify_media_run_monitoring(meta: dict[str, Any]) -> dict[str, Any]:
    row = meta if isinstance(meta, dict) else {}
    status = str(row.get("status") or row.get("display_state") or "").strip().lower()
    evidence = _media_signal_evidence(row)
    status_text_only_allowed = status in _WORKING_STATUSES or status in _INTERRUPTED_STATUSES or status == "error"
    strong_evidence = [item for item in evidence if item != "imagegen_text"]
    candidate = bool(strong_evidence or (status_text_only_allowed and evidence))
    if not candidate:
        evidence = []
    generated_attachment_count = _generated_media_attachment_count(row)
    generated_count = _generated_media_count(row)
    has_summary = bool(str(row.get("generated_media_summary") or "").strip())
    has_result_attachment = generated_attachment_count > 0
    has_result_metadata = generated_count > 0 or has_summary
    has_result = has_result_attachment or has_result_metadata

    monitor_status = ""
    monitor_reason = ""
    pending = False
    exempt_reason = ""
    if candidate:
        if has_result_attachment:
            monitor_status = "generated_media_ready"
            monitor_reason = "generated_attachment_present"
            exempt_reason = "generated_media_result_present"
        elif has_result_metadata:
            monitor_status = "generated_media_metadata_pending_attachment"
            monitor_reason = "generated_media_metadata_without_attachment"
            pending = True
            exempt_reason = "generated_media_metadata_present"
        elif status in _WORKING_STATUSES:
            monitor_status = "media_result_pending"
            monitor_reason = "working_media_generation"
            pending = True
            exempt_reason = "media_generation_in_progress"
        elif status in _INTERRUPTED_STATUSES:
            monitor_status = "media_generation_interrupted"
            monitor_reason = "terminal_interrupted_without_media_result"
        elif status == "error":
            monitor_status = "media_generation_failed"
            monitor_reason = "terminal_error_without_media_result"
        elif status == "done":
            monitor_status = "media_result_missing"
            monitor_reason = "done_without_media_result"
            pending = True
        else:
            monitor_status = "media_result_pending"
            monitor_reason = "media_signal_without_terminal_result"
            pending = True
            exempt_reason = "media_generation_signal_present"

    return {
        "media_run_candidate": bool(candidate),
        "media_result_pending": bool(pending),
        "media_monitor_status": monitor_status,
        "media_monitor_reason": monitor_reason,
        "media_monitor_evidence": evidence,
        "media_generated_attachment_count": int(generated_attachment_count),
        "media_false_stop_exempt": bool(exempt_reason),
        "media_false_stop_exempt_reason": exempt_reason,
        "media_terminal_result_present": bool(has_result),
    }


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


def _provider_failure_evidence_text(meta: dict[str, Any], extra_text: Any = "") -> str:
    row = meta if isinstance(meta, dict) else {}
    text_sources: list[str] = []
    for key in (
        "error",
        "errorHint",
        "errorType",
        "lastPreview",
        "partialPreview",
        "messagePreview",
        "logPreview",
    ):
        text_sources.extend(_iter_text_values(row.get(key)))
    text_sources.extend(_iter_text_values(row.get("processRows") or row.get("process_rows")))
    text_sources.extend(_iter_text_values(row.get("process_events")))
    text_sources.extend(_iter_text_values(extra_text))
    return "\n".join(text_sources)


def _provider_side_effect_risk(meta: dict[str, Any], evidence_text: str) -> tuple[str, list[str]]:
    row = meta if isinstance(meta, dict) else {}
    evidence: list[str] = []
    communication_view = row.get("communication_view") or row.get("communicationView")
    if isinstance(communication_view, dict):
        if str(communication_view.get("dispatch_run_id") or "").strip():
            evidence.append("dispatch_run_id")
        if bool(communication_view.get("visible_in_channel_chat")):
            evidence.append("visible_in_channel_chat")
    for key in (
        "announce_run_id",
        "dispatch_run_id",
        "callback_run_id",
        "callbackRunId",
        "visible_in_channel_chat",
    ):
        value = row.get(key)
        if bool(value) and str(value).strip().lower() not in {"0", "false", "none", ""}:
            evidence.append(str(key))
    if _SIDE_EFFECT_SIGNAL_RE.search(str(evidence_text or "")):
        evidence.append("side_effect_text_signal")
    out: list[str] = []
    seen: set[str] = set()
    for item in evidence:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    # P0 is intentionally conservative: provider failures are not auto-retried from UI.
    return ("confirmed" if out else "possible"), out[:8]


def classify_provider_transient_failure(meta: dict[str, Any], extra_text: Any = "") -> dict[str, Any]:
    row = meta if isinstance(meta, dict) else {}
    status = str(row.get("status") or row.get("display_state") or "").strip().lower()
    existing_failure_class = str(row.get("failure_class") or row.get("failureClass") or "").strip().lower()
    existing_error_class = str(row.get("error_class") or row.get("errorClass") or "").strip().lower()
    existing_outcome_state = str(row.get("outcome_state") or row.get("outcomeState") or "").strip().lower()
    existing_provider_error = row.get("provider_error") if isinstance(row.get("provider_error"), dict) else {}
    existing_provider_like = (
        existing_failure_class == "provider_transient"
        or existing_error_class == "provider_transient"
        or existing_outcome_state == "provider_transient_failed"
    )
    if status != "error" and not existing_provider_like:
        return {}

    evidence_text = _provider_failure_evidence_text(row, extra_text=extra_text)
    matched: list[tuple[str, str]] = []
    for kind, label, pattern in _PROVIDER_TRANSIENT_PATTERNS:
        if pattern.search(evidence_text):
            matched.append((kind, label))
    if not matched and existing_provider_like:
        kind = str(existing_provider_error.get("kind") or "unknown").strip().lower() or "unknown"
        matched.append((kind, kind))
    if not matched:
        return {}

    primary_kind = matched[0][0]
    matched_patterns: list[str] = []
    seen_patterns: set[str] = set()
    for _kind, label in matched:
        if label in seen_patterns:
            continue
        seen_patterns.add(label)
        matched_patterns.append(label)
    side_effect_risk, side_effect_evidence = _provider_side_effect_risk(row, evidence_text)
    return {
        "failure_class": "provider_transient",
        "provider_error": {
            "kind": primary_kind,
            "retryable": True,
            "matched_patterns": matched_patterns[:8],
        },
        "side_effect_risk": side_effect_risk,
        "side_effect_evidence": side_effect_evidence,
        "recovery_mode": "manual_recovery",
        "recovery_required": True,
    }


def apply_provider_transient_failure_fields(meta: dict[str, Any], extra_text: Any = "") -> bool:
    if not isinstance(meta, dict):
        return False
    status = str(meta.get("status") or "").strip().lower()
    if status != "error":
        changed = False
        if str(meta.get("failure_class") or "").strip().lower() == "provider_transient":
            for key in (
                "failure_class",
                "provider_error",
                "side_effect_risk",
                "side_effect_evidence",
                "recovery_mode",
                "recovery_required",
            ):
                if key in meta:
                    meta.pop(key, None)
                    changed = True
        return changed

    fields = classify_provider_transient_failure(meta, extra_text=extra_text)
    if not fields:
        return False
    changed = False
    for key, value in fields.items():
        if meta.get(key) != value:
            meta[key] = value
            changed = True
    return changed


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


def _superseded_by_run_id(meta: dict[str, Any]) -> str:
    """Return the run that supersedes this run without changing existing restart semantics."""
    for key in (
        "providerRetryRunId",
        "provider_auto_retry_run_id",
        "superseded_by",
        "supersededBy",
        "superseded_by_run_id",
        "restartRecoveryRunId",
    ):
        run_id = str(meta.get(key) or "").strip()
        if run_id:
            return run_id
    return ""


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
    provider_failure = classify_provider_transient_failure(row)
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
        elif provider_failure:
            outcome_state = "provider_transient_failed"
            error_class = "provider_transient"
        else:
            outcome_state = "failed_business"

    failure_fields = classify_run_failure(row, error_text=error_text)

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
        "superseded_by_run_id": _superseded_by_run_id(row),
        "recovery_of_run_id": _recovery_of_run_id(row),
        "restart_recovery_run_id": _restart_recovery_run_id(row),
        "is_system_run": bool(is_system_run),
        "preview": preview,
        "created_at": _run_created_at(row),
        "created_ts": _run_created_ts(row),
        "failure_class": str(failure_fields.get("failure_class") or "").strip().lower(),
        "provider_error": dict(failure_fields.get("provider_error") or {}) if isinstance(failure_fields.get("provider_error"), dict) else {},
        "side_effect_risk": str(failure_fields.get("side_effect_risk") or "").strip().lower(),
        "side_effect_evidence": list(failure_fields.get("side_effect_evidence") or []),
        "recovery_mode": str(failure_fields.get("recovery_mode") or "").strip().lower(),
        "recovery_required": bool(failure_fields.get("recovery_required")),
        "auto_retry_eligible": bool(failure_fields.get("auto_retry_eligible")),
        "retry_eligibility_reason": str(failure_fields.get("retry_eligibility_reason") or "").strip(),
        "retry_exhausted": bool(failure_fields.get("retry_exhausted")),
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
    if outcome in {"interrupted_infra", "interrupted_user", "failed_business", "provider_transient_failed"}:
        return "attention"
    return "healthy"


def _summary_object(run_id: str, fields: dict[str, Any]) -> dict[str, Any]:
    summary = {
        "run_id": str(run_id or "").strip(),
        "outcome_state": str(fields.get("outcome_state") or "").strip(),
        "preview": str(fields.get("preview") or "").strip(),
        "created_at": str(fields.get("created_at") or "").strip(),
    }
    error_class = str(fields.get("error_class") or "").strip().lower()
    if error_class:
        summary["error_class"] = error_class
    for key in (
        "failure_class",
        "provider_error",
        "side_effect_risk",
        "side_effect_evidence",
        "recovery_mode",
        "recovery_required",
        "auto_retry_eligible",
        "retry_eligibility_reason",
        "retry_exhausted",
    ):
        value = fields.get(key)
        if key == "provider_error":
            if isinstance(value, dict) and value:
                summary[key] = dict(value)
            continue
        if value not in (None, "", [], {}):
            summary[key] = value
    return summary


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
            "superseded_by_run_id": str(fields.get("superseded_by_run_id") or "").strip(),
            "recovery_of_run_id": str(fields.get("recovery_of_run_id") or "").strip(),
            "failure_class": str(fields.get("failure_class") or "").strip().lower(),
            "provider_error": dict(fields.get("provider_error") or {}) if isinstance(fields.get("provider_error"), dict) else {},
            "side_effect_risk": str(fields.get("side_effect_risk") or "").strip().lower(),
            "side_effect_evidence": list(fields.get("side_effect_evidence") or []),
            "recovery_mode": str(fields.get("recovery_mode") or "").strip().lower(),
            "recovery_required": bool(fields.get("recovery_required")),
            "auto_retry_eligible": bool(fields.get("auto_retry_eligible")),
            "retry_eligibility_reason": str(fields.get("retry_eligibility_reason") or "").strip(),
            "retry_exhausted": bool(fields.get("retry_exhausted")),
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
        if outcome_state == "recovered_notice" and str(fields.get("preview") or "").strip():
            latest_system_summary = _summary_object(run_id, fields)

    latest_effective_business_summary = {}
    for _created_ts, run_id, fields in ordered:
        stored_fields = per_run_fields.get(run_id) if isinstance(per_run_fields.get(run_id), dict) else {}
        merged_fields = {**fields, **stored_fields}
        outcome_state = str(merged_fields.get("outcome_state") or "").strip()
        if outcome_state == "recovered_notice" or bool(merged_fields.get("is_system_run")):
            continue
        if not bool(merged_fields.get("effective_for_session_health")):
            continue
        if str(merged_fields.get("superseded_by_run_id") or "").strip():
            continue
        latest_effective_business_summary = _summary_object(run_id, merged_fields)

    return {
        "run_fields": per_run_fields,
        "session_health_state": _session_health_state_from_fields(latest_health_fields),
        "latest_effective_run_summary": latest_effective_business_summary,
        "latest_system_summary": latest_system_summary,
    }
