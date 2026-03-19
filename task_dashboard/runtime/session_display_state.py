# -*- coding: utf-8 -*-

from __future__ import annotations

from typing import Any


WORKING_SESSION_DISPLAY_STATES = {"running", "queued", "retry_waiting", "external_busy"}
TERMINAL_RUN_STATES = {"done", "error"}
ALLOWED_SESSION_DISPLAY_STATES = WORKING_SESSION_DISPLAY_STATES | TERMINAL_RUN_STATES | {"idle"}


def normalize_session_display_state(raw: Any, fallback: str = "idle") -> str:
    state = str(raw or "").strip().lower()
    if state in ALLOWED_SESSION_DISPLAY_STATES:
        return state
    fb = str(fallback or "idle").strip().lower()
    return fb if fb in ALLOWED_SESSION_DISPLAY_STATES else "idle"


def build_latest_run_summary(agg: Any) -> dict[str, Any]:
    src = agg if isinstance(agg, dict) else {}
    return {
        "run_id": str(src.get("latest_run_id") or "").strip(),
        "status": normalize_session_display_state(src.get("latest_status"), "idle"),
        "updated_at": str(src.get("updated_at") or "").strip(),
        "preview": str(src.get("last_preview") or "").strip(),
        "speaker": str(src.get("last_speaker") or "assistant").strip() or "assistant",
        "sender_type": str(src.get("last_sender_type") or "").strip(),
        "sender_name": str(src.get("last_sender_name") or "").strip(),
        "sender_source": str(src.get("last_sender_source") or "").strip(),
        "latest_user_msg": str(src.get("latest_user_msg") or "").strip(),
        "latest_ai_msg": str(src.get("latest_ai_msg") or "").strip(),
        "error": str(src.get("last_error") or "").strip(),
        "run_count": int(src.get("run_count") or 0),
    }


def build_session_display_fields(runtime_state: Any, agg: Any) -> dict[str, Any]:
    runtime = runtime_state if isinstance(runtime_state, dict) else {}
    runtime_display = normalize_session_display_state(runtime.get("display_state"), "idle")
    latest_summary = build_latest_run_summary(agg)
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
    }
