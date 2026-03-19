# -*- coding: utf-8 -*-

from __future__ import annotations

from typing import Any, Callable


def apply_profile_fallback_retry_result(
    meta: dict[str, Any],
    retry: Any,
    *,
    safe_text: Callable[[Any, int], str],
    is_auth_error: Callable[[str], bool],
    is_transient_network_error: Callable[[str], bool],
) -> dict[str, Any]:
    detected_auth_error = False
    network_failed_persist = False
    returncode = getattr(retry, "returncode", 1)
    if returncode is not None and int(returncode) == 0:
        meta["status"] = "done"
        meta["error"] = ""
        return {
            "detected_auth_error": False,
            "network_failed_persist": False,
        }
    meta["status"] = "error"
    meta["error"] = safe_text((getattr(retry, "stderr", "") or "").strip() or f"exit={retry.returncode}", 1200)
    detected_auth_error = is_auth_error(str(meta.get("error") or ""))
    if detected_auth_error:
        meta["errorType"] = "auth_error"
    network_failed_persist = is_transient_network_error(str(meta.get("error") or "")) and (not detected_auth_error)
    return {
        "detected_auth_error": bool(detected_auth_error),
        "network_failed_persist": bool(network_failed_persist),
    }


def apply_network_retry_failure(
    meta: dict[str, Any],
    *,
    recovered: bool,
    final_err: str,
    err_text: str,
    detected_text: str,
    detected_auth_error: bool,
    network_retry_max: int,
    safe_text: Callable[[Any, int], str],
    is_auth_error: Callable[[str], bool],
    is_transient_network_error: Callable[[str], bool],
) -> bool:
    if recovered:
        return False
    meta["status"] = "error"
    meta["retryCount"] = network_retry_max
    meta["error"] = safe_text(final_err or err_text or "exit=1", 1200)
    if detected_auth_error or is_auth_error(str(final_err or "")):
        meta["errorType"] = "auth_error"
        return False
    meta["errorType"] = "network_error"
    return bool(is_transient_network_error(str(final_err or detected_text or "")))
