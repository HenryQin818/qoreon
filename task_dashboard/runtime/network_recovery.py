# -*- coding: utf-8 -*-

from __future__ import annotations

from typing import Any, Callable


def build_network_resume_retry_meta(
    retry_meta: dict[str, Any],
    *,
    source_id: str,
    delay_s: int,
    message: str,
    iso_after_s: Callable[[int], str],
) -> dict[str, Any]:
    meta = dict(retry_meta if isinstance(retry_meta, dict) else {})
    meta["status"] = "retry_waiting"
    meta["retryOf"] = str(source_id or "").strip()
    meta["retryKind"] = "network_resume"
    meta["retryDelaySeconds"] = int(delay_s or 0)
    meta["retryScheduledAt"] = iso_after_s(int(delay_s or 0))
    meta["autoResumePrompt"] = True
    meta["retryMessage"] = str(message or "").strip()
    meta["retryCancelable"] = True
    return meta


def apply_network_resume_schedule(
    meta: dict[str, Any],
    *,
    retry_run_id: str,
    delay_s: int,
    iso_after_s: Callable[[int], str],
) -> str:
    if not isinstance(meta, dict):
        raise TypeError("meta must be dict")
    rid = str(retry_run_id or "").strip()
    delay = int(delay_s or 0)
    meta["networkResumeRunId"] = rid
    meta["networkResumeScheduledAt"] = iso_after_s(delay)
    return f"\n[system] transient network failure persisted, scheduled auto resume run={rid} in {delay}s\n"
