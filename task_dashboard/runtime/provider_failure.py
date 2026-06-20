# -*- coding: utf-8 -*-

from __future__ import annotations

import re
from typing import Any


_PROVIDER_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "high_demand",
        (
            "high demand",
            "temporary errors",
        ),
    ),
    (
        "model_capacity",
        (
            "model_capacity_exhausted",
            "model capacity exhausted",
            "no capacity available for model",
            "resource_exhausted",
        ),
    ),
    (
        "rate_limit",
        (
            "rate limit",
            "rate_limit",
            "too many requests",
            "http 429",
            "status 429",
        ),
    ),
    (
        "server_error",
        (
            "5xx",
            "http 500",
            "http 502",
            "http 503",
            "http 504",
            "500 internal server error",
            "502 bad gateway",
            "503 service unavailable",
            "504 gateway timeout",
        ),
    ),
    (
        "network_timeout",
        (
            "operation timed out",
            "timed out (os error 60)",
            "connection timed out",
            "request timed out",
            "upstream timeout",
            "websocket timeout",
        ),
    ),
    (
        "network_reset",
        (
            "connection reset by peer",
            "stream disconnected before completion",
            "transport channel closed",
            "error sending request for url",
            "connection closed via error",
        ),
    ),
    (
        "upstream_unavailable",
        (
            "upstream unavailable",
            "temporarily unavailable",
            "failed to connect to websocket",
            "failed to refresh available models",
            "service unavailable",
        ),
    ),
)

_HTTP_429_RE = re.compile(r"\b(?:http\s*)?429\b|status(?:\s+code)?[:=]?\s*429", re.IGNORECASE)
_HTTP_5XX_RE = re.compile(
    r"\b(?:http\s*)?(?:500|502|503|504)\b|status(?:\s+code)?[:=]?\s*(?:500|502|503|504)",
    re.IGNORECASE,
)
_PROVIDER_CONTEXT_RE = re.compile(
    r"\b(openai|gemini|googleapis|cloudcode|provider|upstream|model|responses?_api|responses_websocket|websocket|request|network|transport|codex_api)\b",
    re.IGNORECASE,
)


def _as_text(value: Any) -> str:
    return "" if value is None else str(value)


def _normalize_text(value: Any) -> str:
    return _as_text(value).replace("\r\n", "\n").replace("\r", "\n").strip()


def _iter_text_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, dict):
        rows: list[str] = []
        for key in ("text", "message", "summary", "preview", "output", "path", "error", "reason"):
            rows.extend(_iter_text_values(value.get(key)))
        return rows
    if isinstance(value, list):
        rows: list[str] = []
        for item in value:
            rows.extend(_iter_text_values(item))
        return rows
    return []


def classify_provider_error_text(text: Any) -> dict[str, Any]:
    normalized = _normalize_text(text)
    lower = normalized.lower()
    matched: list[str] = []
    kind = ""

    if not lower:
        return {"kind": "", "retryable": False, "matched_patterns": []}

    for candidate_kind, patterns in _PROVIDER_PATTERNS:
        local_matches = [pattern for pattern in patterns if pattern in lower]
        if not local_matches:
            continue
        if not kind:
            kind = candidate_kind
        matched.extend(local_matches)

    if _HTTP_429_RE.search(normalized):
        if not kind:
            kind = "rate_limit"
        matched.append("429")
    if _HTTP_5XX_RE.search(normalized):
        if not kind:
            kind = "server_error"
        matched.append("5xx")

    # Generic timeout alone is often a local task timeout. Require provider/network context.
    if not kind and re.search(r"\b(?:timed out|timeout|time-out)\b", lower) and _PROVIDER_CONTEXT_RE.search(normalized):
        kind = "network_timeout"
        matched.append("timeout_with_provider_context")

    if not kind:
        return {"kind": "", "retryable": False, "matched_patterns": []}

    out: list[str] = []
    seen: set[str] = set()
    for item in matched:
        text_item = str(item or "").strip()
        if not text_item or text_item in seen:
            continue
        seen.add(text_item)
        out.append(text_item)
    return {"kind": kind, "retryable": True, "matched_patterns": out[:12]}


def _generated_attachment_present(meta: dict[str, Any]) -> bool:
    attachments = meta.get("attachments")
    if not isinstance(attachments, list):
        return False
    for item in attachments:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source") or "").strip().lower()
        role = str(item.get("attachment_role") or item.get("attachmentRole") or "").strip().lower()
        generated_by = str(item.get("generatedBy") or item.get("generated_by") or "").strip().lower()
        if source == "generated" or role == "assistant" or generated_by:
            return True
    return False


_CONFIRMED_SIDE_EFFECT_MARKERS: tuple[str, ...] = (
    "announce_run_id=",
    "visible_in_channel_chat=true",
    "manifest_path",
    "manifest_id",
    "generated_media_file",
    "生成媒体文件",
)

_POSSIBLE_SIDE_EFFECT_MARKERS: tuple[str, ...] = (
    "apply_patch",
    "patch applied",
    "wrote ",
    "wrote file",
    "write ",
    "write file",
    "created ",
    "updated ",
    "saved ",
    "deployed ",
    "published ",
    "deleted ",
    "removed ",
    "archived ",
    "moved ",
    "renamed ",
    "已写",
    "已创建",
    "已更新",
    "已保存",
    "已发送",
    "已部署",
    "已发布",
    "已删除",
    "已移动",
    "已归档",
)


def _append_marker_evidence(evidence: list[str], haystack: str, markers: tuple[str, ...], prefix: str) -> None:
    seen = set(evidence)
    for marker in markers:
        if marker in haystack:
            item = f"{prefix}:{marker}"
            if item not in seen:
                evidence.append(item)
                seen.add(item)


def _preview_is_provider_error_only(value: Any) -> bool:
    text = _normalize_text(value)
    if not text:
        return True
    provider_error = classify_provider_error_text(text)
    if bool(provider_error.get("retryable")):
        return True
    lower = text.lower()
    return "turn.failed" in lower and ("temporary error" in lower or "provider" in lower)


def assess_side_effect_risk(meta: dict[str, Any], *, log_text: Any = "", last_text: Any = "") -> dict[str, Any]:
    row = meta if isinstance(meta, dict) else {}
    text_sources: list[str] = []
    text_sources.extend(_iter_text_values(row.get("processRows") or row.get("process_rows")))
    text_sources.extend(_iter_text_values(row.get("process_events")))
    text_sources.extend(_iter_text_values(row.get("lastPreview")))
    text_sources.extend(_iter_text_values(row.get("partialPreview")))
    text_sources.extend(_iter_text_values(last_text))
    text_sources.extend(_iter_text_values(log_text))
    haystack = "\n".join(text_sources).lower()

    confirmed_evidence: list[str] = []
    _append_marker_evidence(
        confirmed_evidence,
        haystack,
        _CONFIRMED_SIDE_EFFECT_MARKERS,
        "confirmed_marker",
    )
    for key in (
        "visible_in_channel_chat",
        "visibleInChannelChat",
        "callback_run_id",
        "callbackRunId",
        "dispatch_run_id",
        "dispatchRunId",
    ):
        value = row.get(key)
        if bool(value) and str(value).strip().lower() not in {"0", "false", "none", ""}:
            confirmed_evidence.append(f"meta:{key}")
    communication_view = row.get("communication_view")
    if isinstance(communication_view, dict):
        dispatch_run_id = str(communication_view.get("dispatch_run_id") or "").strip()
        if dispatch_run_id:
            confirmed_evidence.append("communication_view.dispatch_run_id")
    if _generated_attachment_present(row):
        confirmed_evidence.append("generated_attachment_present")
    try:
        if int(row.get("generated_media_count") or 0) > 0:
            confirmed_evidence.append("generated_media_count")
    except Exception:
        pass
    if str(row.get("generated_media_summary") or "").strip():
        confirmed_evidence.append("generated_media_summary")
    if confirmed_evidence:
        return {"risk": "confirmed", "evidence": confirmed_evidence[:12]}

    possible_evidence: list[str] = []
    _append_marker_evidence(
        possible_evidence,
        haystack,
        _POSSIBLE_SIDE_EFFECT_MARKERS,
        "possible_marker",
    )
    if str(row.get("lastPreview") or "").strip() and not _preview_is_provider_error_only(row.get("lastPreview")):
        possible_evidence.append("last_preview_non_provider_text")
    if str(row.get("partialPreview") or "").strip() and not _preview_is_provider_error_only(row.get("partialPreview")):
        possible_evidence.append("partial_preview_non_provider_text")
    try:
        if int(row.get("agentMessagesCount") or 0) > 0:
            possible_evidence.append("agent_messages_present")
    except Exception:
        pass
    if row.get("processRows") or row.get("process_rows") or row.get("process_events"):
        possible_evidence.append("process_events_present")
    if possible_evidence:
        return {"risk": "possible", "evidence": possible_evidence[:12]}
    return {"risk": "none", "evidence": ["no_side_effect_evidence_detected"]}


def infer_side_effect_risk(meta: dict[str, Any], *, log_text: Any = "", last_text: Any = "") -> str:
    assessment = assess_side_effect_risk(meta, log_text=log_text, last_text=last_text)
    return str(assessment.get("risk") or "possible")


def classify_run_failure(
    meta: dict[str, Any],
    *,
    log_text: Any = "",
    last_text: Any = "",
    error_text: Any = "",
) -> dict[str, Any]:
    row = meta if isinstance(meta, dict) else {}
    status = str(row.get("status") or "").strip().lower()
    combined = "\n".join(
        part
        for part in (
            _normalize_text(error_text),
            _normalize_text(row.get("error")),
            _normalize_text(row.get("errorHint")),
            _normalize_text(row.get("lastPreview")),
            _normalize_text(row.get("partialPreview")),
            _normalize_text(row.get("logPreview")),
            _normalize_text(last_text),
            _normalize_text(log_text),
        )
        if part
    )
    lower = combined.lower()
    provider_error = classify_provider_error_text(combined)
    existing_failure_class = str(row.get("failure_class") or row.get("failureClass") or "").strip().lower()
    existing_error_class = str(row.get("error_class") or row.get("errorClass") or "").strip().lower()
    existing_outcome_state = str(row.get("outcome_state") or row.get("outcomeState") or "").strip().lower()
    existing_provider_error = row.get("provider_error") if isinstance(row.get("provider_error"), dict) else {}
    existing_provider_like = (
        existing_failure_class == "provider_transient"
        or existing_error_class == "provider_transient"
        or existing_outcome_state == "provider_transient_failed"
    )
    if not provider_error.get("retryable") and existing_provider_like:
        provider_error = {
            "kind": str(existing_provider_error.get("kind") or "unknown").strip().lower() or "unknown",
            "retryable": True,
            "matched_patterns": list(existing_provider_error.get("matched_patterns") or []),
        }

    if (
        status in {"interrupted", "cancelled", "canceled"}
        or "interrupted by user" in lower
        or "run interrupted (server restarted or process exited)" in lower
        or "server restarted or process exited" in lower
    ):
        failure_class = "interrupted"
    elif provider_error.get("retryable") or existing_provider_like:
        failure_class = "provider_transient"
    elif status == "error":
        failure_class = "business" if combined else "unknown"
    else:
        failure_class = ""

    if not failure_class:
        return {}

    side_effect_assessment = assess_side_effect_risk(row, log_text=log_text, last_text=last_text)
    side_effect_risk = str(side_effect_assessment.get("risk") or "possible")
    side_effect_evidence = list(side_effect_assessment.get("evidence") or [])
    recovery_mode = "none"
    recovery_required = False
    auto_retry_eligible = False
    retry_eligibility_reason = "not_provider_transient"
    retry_exhausted = bool(row.get("retry_exhausted") or row.get("retryExhausted"))
    if failure_class == "provider_transient":
        if retry_exhausted:
            recovery_mode = "manual_recovery"
            recovery_required = True
            auto_retry_eligible = False
            retry_eligibility_reason = "retry_exhausted"
        elif side_effect_risk == "none":
            recovery_mode = "auto_retry"
            recovery_required = False
            auto_retry_eligible = True
            retry_eligibility_reason = "provider_transient_no_side_effect_evidence"
        else:
            recovery_mode = "manual_recovery"
            recovery_required = True
            retry_eligibility_reason = f"side_effect_risk_{side_effect_risk}"
    elif failure_class == "interrupted":
        retry_eligibility_reason = "interrupted"
    elif failure_class == "business":
        retry_eligibility_reason = "business_failure"
    elif failure_class == "unknown":
        retry_eligibility_reason = "unknown_failure"

    return {
        "failure_class": failure_class,
        "provider_error": {
            "kind": str(provider_error.get("kind") or ""),
            "retryable": bool(provider_error.get("retryable")),
            "matched_patterns": list(provider_error.get("matched_patterns") or []),
        },
        "side_effect_risk": side_effect_risk,
        "side_effect_evidence": side_effect_evidence[:12],
        "recovery_mode": recovery_mode,
        "recovery_required": bool(recovery_required),
        "auto_retry_eligible": bool(auto_retry_eligible),
        "retry_eligibility_reason": retry_eligibility_reason,
        "retry_exhausted": bool(retry_exhausted),
    }


def apply_run_failure_classification(
    meta: dict[str, Any],
    *,
    log_text: Any = "",
    last_text: Any = "",
    error_text: Any = "",
) -> bool:
    if not isinstance(meta, dict):
        return False
    fields = classify_run_failure(meta, log_text=log_text, last_text=last_text, error_text=error_text)
    if not fields:
        return False
    changed = False
    for key, value in fields.items():
        if meta.get(key) != value:
            meta[key] = value
            changed = True
    return changed
