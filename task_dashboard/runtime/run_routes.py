# -*- coding: utf-8 -*-

from __future__ import annotations

import copy
import os
import threading
import time
from typing import Any, Callable, Optional
from urllib.parse import parse_qs

from task_dashboard.adapters.codebuddy_output import sanitize_process_event_text
from task_dashboard.runtime.project_execution_context import (
    build_project_execution_context,
    infer_project_execution_context_source,
)
from task_dashboard.runtime.run_detail_fields import (
    extract_agent_messages,
    extract_agent_messages_from_file,
    extract_business_refs_from_texts,
    extract_process_events_from_file,
    extract_skills_used_from_texts,
    extract_terminal_message_from_file,
    extract_terminal_message_text,
    fallback_log_from_meta,
    normalize_business_refs_value,
    normalize_skills_used_value,
    safe_terminal_visible_text,
)

_RUNS_LIST_CACHE_LOCK = threading.Lock()
_RUNS_LIST_CACHE: dict[str, dict[str, Any]] = {}
_RUNS_LIST_CACHE_INFLIGHT: dict[str, dict[str, Any]] = {}
_RUNS_LIST_CACHE_INVALIDATED_AT: dict[str, float] = {}
_RUN_DETAIL_CACHE_LOCK = threading.Lock()
_RUN_DETAIL_CACHE: dict[str, dict[str, Any]] = {}


def _safe_text(value: Any, max_len: int) -> str:
    text = "" if value is None else str(value)
    if len(text) > max_len:
        return text[: max_len - 1] + "…"
    return text


def _runs_list_cache_ttl_s() -> float:
    raw = str(os.environ.get("CCB_RUNS_LIST_CACHE_TTL_MS") or "").strip()
    if raw:
        try:
            return max(0.0, min(float(raw) / 1000.0, 15.0))
        except Exception:
            pass
    return 2.0


def _runs_list_cache_stale_s() -> float:
    raw = str(os.environ.get("CCB_RUNS_LIST_CACHE_STALE_MS") or "").strip()
    if raw:
        try:
            return max(0.0, min(float(raw) / 1000.0, 30.0))
        except Exception:
            pass
    return 3.0


def _runs_list_cache_inflight_wait_s() -> float:
    raw = str(os.environ.get("CCB_RUNS_LIST_CACHE_INFLIGHT_WAIT_MS") or "").strip()
    if raw:
        try:
            return max(0.2, min(float(raw) / 1000.0, 30.0))
        except Exception:
            pass
    return 8.0


def _run_detail_cache_ttl_s() -> float:
    raw = str(os.environ.get("CCB_RUN_DETAIL_CACHE_TTL_MS") or "").strip()
    if raw:
        try:
            return max(0.0, min(float(raw) / 1000.0, 300.0))
        except Exception:
            pass
    return 60.0


def _is_terminal_run_meta(meta: dict[str, Any]) -> bool:
    status = str(meta.get("status") or meta.get("display_state") or "").strip().lower()
    outcome = str(meta.get("outcome_state") or meta.get("outcomeState") or "").strip().lower()
    if outcome in {"interrupted_infra", "interrupted_user", "failed_config", "failed_business", "success"}:
        return True
    return status in {"done", "error", "interrupted", "cancelled", "canceled"}


def _run_detail_cache_key(store: Any, run_id: str) -> str:
    root = str(getattr(store, "runs_dir", "") or "").strip()
    return f"{root}|{str(run_id or '').strip()}"


def _run_detail_file_token(store: Any, run_id: str) -> tuple[tuple[str, int, int], ...]:
    try:
        paths = store._paths(run_id)
    except Exception:
        paths = {}
    token: list[tuple[str, int, int]] = []
    for key in ("meta", "msg", "last", "log"):
        path = paths.get(key) if isinstance(paths, dict) else None
        try:
            st = path.stat()
            token.append((key, int(st.st_mtime_ns), int(st.st_size)))
        except Exception:
            token.append((key, 0, 0))
    return tuple(token)


def _prune_run_detail_cache_locked(now_mono: float, ttl_s: float) -> None:
    stale_after = max(ttl_s, 1.0)
    for key, entry in list(_RUN_DETAIL_CACHE.items()):
        stored_at = float(entry.get("stored_at") or 0.0)
        if stored_at <= 0.0 or (now_mono - stored_at) > stale_after:
            _RUN_DETAIL_CACHE.pop(key, None)
    if len(_RUN_DETAIL_CACHE) <= 128:
        return
    overflow = len(_RUN_DETAIL_CACHE) - 128
    ordered = sorted(_RUN_DETAIL_CACHE.items(), key=lambda item: float(item[1].get("stored_at") or 0.0))
    for key, _entry in ordered[:overflow]:
        _RUN_DETAIL_CACHE.pop(key, None)


def _load_run_detail_cache(cache_key: str, token: tuple[tuple[str, int, int], ...]) -> Optional[dict[str, Any]]:
    ttl_s = _run_detail_cache_ttl_s()
    if ttl_s <= 0.0:
        return None
    now_mono = time.monotonic()
    with _RUN_DETAIL_CACHE_LOCK:
        _prune_run_detail_cache_locked(now_mono, ttl_s)
        entry = _RUN_DETAIL_CACHE.get(cache_key)
        if not entry:
            return None
        if entry.get("token") != token:
            _RUN_DETAIL_CACHE.pop(cache_key, None)
            return None
        stored_at = float(entry.get("stored_at") or 0.0)
        if stored_at <= 0.0 or (now_mono - stored_at) > ttl_s:
            _RUN_DETAIL_CACHE.pop(cache_key, None)
            return None
        payload = entry.get("payload")
        if not isinstance(payload, dict):
            _RUN_DETAIL_CACHE.pop(cache_key, None)
            return None
        return copy.deepcopy(payload)


def _store_run_detail_cache(
    cache_key: str,
    token: tuple[tuple[str, int, int], ...],
    payload: dict[str, Any],
) -> None:
    ttl_s = _run_detail_cache_ttl_s()
    if ttl_s <= 0.0:
        return
    now_mono = time.monotonic()
    with _RUN_DETAIL_CACHE_LOCK:
        _prune_run_detail_cache_locked(now_mono, ttl_s)
        _RUN_DETAIL_CACHE[cache_key] = {
            "stored_at": now_mono,
            "token": token,
            "payload": copy.deepcopy(payload),
        }


def _runs_list_cache_key(
    *,
    store_root: str,
    channel_id: str,
    project_id: str,
    session_id: str,
    after_created_at: str,
    before_created_at: str,
    limit: int,
    payload_mode: str,
    environment_name: str,
    local_server_origin: str,
    worktree_root: str,
) -> str:
    return "|".join(
        [
            str(store_root or "").strip(),
            str(project_id or "").strip(),
            str(channel_id or "").strip(),
            str(session_id or "").strip(),
            str(after_created_at or "").strip(),
            str(before_created_at or "").strip(),
            str(int(limit or 0)),
            str(payload_mode or "").strip().lower(),
            str(environment_name or "").strip(),
            str(local_server_origin or "").strip(),
            str(worktree_root or "").strip(),
        ]
    )


def _prune_runs_list_cache_locked(now_mono: float, ttl_s: float, stale_s: float) -> None:
    max_age_s = max(ttl_s + stale_s, ttl_s)
    expired: list[str] = []
    for key, entry in list(_RUNS_LIST_CACHE.items()):
        checked = float((entry or {}).get("checked_at_mono") or 0.0)
        if max_age_s <= 0 or (now_mono - checked) > max_age_s:
            expired.append(key)
    for key in expired:
        _RUNS_LIST_CACHE.pop(key, None)

    inflight_expired: list[str] = []
    inflight_ttl_s = max(_runs_list_cache_inflight_wait_s() * 2.0, 5.0)
    for key, entry in list(_RUNS_LIST_CACHE_INFLIGHT.items()):
        started = float((entry or {}).get("started_at_mono") or 0.0)
        event = (entry or {}).get("event")
        if isinstance(event, threading.Event) and event.is_set():
            inflight_expired.append(key)
            continue
        if started > 0 and (now_mono - started) > inflight_ttl_s:
            inflight_expired.append(key)
    for key in inflight_expired:
        _RUNS_LIST_CACHE_INFLIGHT.pop(key, None)

    invalidated_expired: list[str] = []
    invalidated_ttl_s = max(max_age_s * 4.0, 30.0)
    for key, invalidated_at in list(_RUNS_LIST_CACHE_INVALIDATED_AT.items()):
        if invalidated_at <= 0 or (now_mono - float(invalidated_at)) > invalidated_ttl_s:
            invalidated_expired.append(key)
    for key in invalidated_expired:
        _RUNS_LIST_CACHE_INVALIDATED_AT.pop(key, None)

    if len(_RUNS_LIST_CACHE) <= 64:
        return
    ordered = sorted(
        _RUNS_LIST_CACHE.items(),
        key=lambda item: float((item[1] or {}).get("checked_at_mono") or 0.0),
        reverse=True,
    )
    for key, _entry in ordered[64:]:
        _RUNS_LIST_CACHE.pop(key, None)


def _load_runs_list_cache(
    cache_key: str,
    *,
    project_id: str,
    session_id: str,
    now_mono: float,
    ttl_s: float,
    stale_s: float,
    allow_stale: bool = False,
) -> tuple[Optional[dict[str, Any]], dict[str, Any]]:
    entry = _RUNS_LIST_CACHE.get(cache_key)
    if not isinstance(entry, dict):
        return None, {}
    payload = entry.get("payload")
    if not isinstance(payload, dict):
        return None, {}
    checked = float(entry.get("checked_at_mono") or 0.0)
    age_s = max(0.0, now_mono - checked)
    build_started = float(entry.get("build_started_at_mono") or checked)
    pid = str(project_id or "").strip()
    sid = str(session_id or "").strip()
    invalidated_at = max(
        float(_RUNS_LIST_CACHE_INVALIDATED_AT.get(pid) or 0.0) if pid else 0.0,
        float(_RUNS_LIST_CACHE_INVALIDATED_AT.get(f"session:{sid}") or 0.0) if sid else 0.0,
    )
    if build_started < invalidated_at:
        return None, {}
    if age_s <= ttl_s:
        return copy.deepcopy(payload), {
            "delivery_mode": "fresh_cache",
            "cache_age_ms": int(age_s * 1000),
            "served_from_stale_cache": False,
        }
    if allow_stale and stale_s > 0 and age_s <= ttl_s + stale_s:
        return copy.deepcopy(payload), {
            "delivery_mode": "stale_cache_budget",
            "cache_age_ms": int(age_s * 1000),
            "served_from_stale_cache": True,
        }
    return None, {}


def _store_runs_list_cache(
    cache_key: str,
    payload: dict[str, Any],
    *,
    project_id: str,
    session_id: str,
    build_started_at_mono: float,
) -> None:
    ttl_s = _runs_list_cache_ttl_s()
    if ttl_s <= 0 or not isinstance(payload, dict):
        return
    now_mono = time.monotonic()
    with _RUNS_LIST_CACHE_LOCK:
        _prune_runs_list_cache_locked(now_mono, ttl_s, _runs_list_cache_stale_s())
        _RUNS_LIST_CACHE[cache_key] = {
            "checked_at_mono": now_mono,
            "build_started_at_mono": max(float(build_started_at_mono or 0.0), now_mono),
            "project_id": str(project_id or "").strip(),
            "session_id": str(session_id or "").strip(),
            "payload": copy.deepcopy(payload),
        }


def invalidate_runs_list_cache(
    project_id: str = "",
    *,
    session_id: str = "",
    channel_id: str = "",
) -> None:
    pid = str(project_id or "").strip()
    sid = str(session_id or "").strip()
    cid = str(channel_id or "").strip()
    now_mono = time.monotonic()
    with _RUNS_LIST_CACHE_LOCK:
        if not pid and not sid and not cid:
            _RUNS_LIST_CACHE.clear()
            _RUNS_LIST_CACHE_INFLIGHT.clear()
            _RUNS_LIST_CACHE_INVALIDATED_AT.clear()
            return
        if pid:
            _RUNS_LIST_CACHE_INVALIDATED_AT[pid] = now_mono
        if sid:
            _RUNS_LIST_CACHE_INVALIDATED_AT[f"session:{sid}"] = now_mono
        for key, entry in list(_RUNS_LIST_CACHE.items()):
            if pid and str((entry or {}).get("project_id") or "").strip() != pid:
                continue
            if sid and str((entry or {}).get("session_id") or "").strip() != sid:
                continue
            if cid and f"|{cid}|" not in key:
                continue
            _RUNS_LIST_CACHE.pop(key, None)


def _with_runs_read_model_meta(
    payload: dict[str, Any],
    *,
    payload_mode: str,
    runtime_info: dict[str, Any],
) -> dict[str, Any]:
    out = copy.deepcopy(payload)
    out["payloadMode"] = payload_mode
    out["runs_read_model"] = {
        "version": "p0a.v1",
        "scope": "codex_runs",
        "payload_mode": payload_mode,
        "cache_strategy": "ttl_inflight_stale_fallback" if payload_mode in {"summary", "light", "none"} else "uncached_full_compat",
        "cache_ttl_ms": int(_runs_list_cache_ttl_s() * 1000),
        "inflight_wait_ms": int(_runs_list_cache_inflight_wait_s() * 1000),
        "stale_fallback_window_ms": int(_runs_list_cache_stale_s() * 1000),
        "delivery_mode": str(runtime_info.get("delivery_mode") or "fresh_build"),
        "cache_age_ms": int(runtime_info.get("cache_age_ms") or 0),
        "queue_wait_ms": int(runtime_info.get("queue_wait_ms") or 0),
        "served_from_stale_cache": bool(runtime_info.get("served_from_stale_cache")),
    }
    return out


def _build_or_load_runs_list_payload(
    *,
    cache_key: str,
    project_id: str,
    session_id: str,
    payload_mode: str,
    builder: Callable[[], dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    if payload_mode not in {"summary", "light", "none"}:
        return builder(), {"delivery_mode": "fresh_build"}
    ttl_s = _runs_list_cache_ttl_s()
    if ttl_s <= 0:
        return builder(), {"delivery_mode": "fresh_build"}

    wait_s = _runs_list_cache_inflight_wait_s()
    stale_s = _runs_list_cache_stale_s()
    build_started_at_mono = time.monotonic()
    owns_build = False
    inflight_event: Optional[threading.Event] = None
    first_wait_started = 0.0
    while True:
        now_mono = time.monotonic()
        with _RUNS_LIST_CACHE_LOCK:
            _prune_runs_list_cache_locked(now_mono, ttl_s, stale_s)
            cached, runtime_info = _load_runs_list_cache(
                cache_key,
                project_id=project_id,
                session_id=session_id,
                now_mono=now_mono,
                ttl_s=ttl_s,
                stale_s=stale_s,
            )
            if cached is not None:
                if first_wait_started > 0:
                    runtime_info["queue_wait_ms"] = int((now_mono - first_wait_started) * 1000)
                return cached, runtime_info
            inflight = _RUNS_LIST_CACHE_INFLIGHT.get(cache_key)
            inflight_event = None
            if isinstance(inflight, dict):
                candidate = inflight.get("event")
                if isinstance(candidate, threading.Event):
                    inflight_event = candidate
            if inflight_event is not None:
                stale_payload, stale_info = _load_runs_list_cache(
                    cache_key,
                    project_id=project_id,
                    session_id=session_id,
                    now_mono=now_mono,
                    ttl_s=ttl_s,
                    stale_s=stale_s,
                    allow_stale=True,
                )
                if stale_payload is not None:
                    return stale_payload, stale_info
            if inflight_event is None:
                inflight_event = threading.Event()
                _RUNS_LIST_CACHE_INFLIGHT[cache_key] = {
                    "event": inflight_event,
                    "started_at_mono": now_mono,
                    "project_id": str(project_id or "").strip(),
                    "session_id": str(session_id or "").strip(),
                }
                build_started_at_mono = now_mono
                owns_build = True
                break
        if inflight_event is not None:
            if first_wait_started <= 0:
                first_wait_started = time.monotonic()
            inflight_event.wait(wait_s)

    try:
        payload = builder()
        _store_runs_list_cache(
            cache_key,
            payload,
            project_id=project_id,
            session_id=session_id,
            build_started_at_mono=build_started_at_mono,
        )
        return payload, {"delivery_mode": "fresh_build"}
    finally:
        if owns_build and inflight_event is not None:
            with _RUNS_LIST_CACHE_LOCK:
                current = _RUNS_LIST_CACHE_INFLIGHT.get(cache_key)
                if isinstance(current, dict) and current.get("event") is inflight_event:
                    _RUNS_LIST_CACHE_INFLIGHT.pop(cache_key, None)
            inflight_event.set()


def _latest_process_row_preview(process_rows: Any, max_len: int) -> str:
    rows = process_rows if isinstance(process_rows, list) else []
    for row in reversed(rows):
        if isinstance(row, dict):
            text = _safe_text(str(row.get("text") or "").replace("\r\n", "\n").strip(), max_len)
            if text:
                return text
        else:
            text = _safe_text(str(row or "").replace("\r\n", "\n").strip(), max_len)
            if text:
                return text
    return ""


def _normalize_standard_process_rows(rows: Any) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    if not isinstance(rows, list):
        return out
    for row in rows:
        if not isinstance(row, dict):
            continue
        event_type = _safe_text(row.get("event_type"), 80).strip()
        item_type = _safe_text(row.get("item_type"), 120).strip()
        title = _safe_text(row.get("title"), 200).strip()
        text = _safe_text(
            sanitize_process_event_text(
                row.get("text"),
                title=title,
                item_type=item_type,
                event_type=event_type,
            ),
            3000,
        ).strip()
        if not text:
            continue
        item = {"text": text}
        for key, value in (
            ("event_type", event_type),
            ("item_type", item_type),
            ("title", title),
        ):
            if value:
                item[key] = value
        for key, max_len in (
            ("at", 80),
            ("path", 1000),
            ("source", 1000),
            ("raw_ref", 1000),
            ("call_id", 1000),
        ):
            value = _safe_text(row.get(key), max_len).strip()
            if value:
                item[key] = value
        out.append(item)
    return out


_TERMINAL_TEXT_CLIS = {"claude", "opencode", "gemini", "codebuddy"}
_TERMINAL_TEXT_PROCESS_CLEAR_CLIS = {"opencode", "gemini"}
_STANDARD_PROCESS_EVENT_CLIS = {"codebuddy", "claude"}


def _normalize_terminal_text_row_fields(store: Any, run_id: str, row: dict[str, Any]) -> bool:
    cli_type = str(row.get("cliType") or row.get("cli_type") or "").strip().lower()
    if cli_type not in _TERMINAL_TEXT_CLIS:
        return False
    changed = False
    preview = str(row.get("lastPreview") or "").strip()
    if not preview:
        preview = _safe_text(extract_terminal_message_from_file(store._paths(run_id)["log"], cli_type=cli_type), 300)
    if preview:
        preview = _safe_text(safe_terminal_visible_text(preview, cli_type=cli_type), 300)
        if preview:
            row["lastPreview"] = preview
            changed = True
    elif str(row.get("lastPreview") or "").strip():
        row["lastPreview"] = ""
        changed = True
    if int(row.get("agentMessagesCount") or 0) != 0:
        row["agentMessagesCount"] = 0
        changed = True
    if str(row.get("partialPreview") or "").strip():
        row["partialPreview"] = ""
        changed = True
    if cli_type in _TERMINAL_TEXT_PROCESS_CLEAR_CLIS:
        process_rows = row.get("processRows")
        if isinstance(process_rows, list) and process_rows:
            row["processRows"] = []
            changed = True
        process_rows_alt = row.get("process_rows")
        if isinstance(process_rows_alt, list) and process_rows_alt:
            row["process_rows"] = []
            changed = True
    elif cli_type in _STANDARD_PROCESS_EVENT_CLIS:
        standard_rows = row.get("processRows") or row.get("process_rows") or []
        standard_events = row.get("process_events") or row.get("processEvents") or []
        normalized_rows = _normalize_standard_process_rows(standard_rows)
        normalized_events = _normalize_standard_process_rows(standard_events)
        canonical = normalized_rows or normalized_events
        if canonical:
            if row.get("processRows") != canonical:
                row["processRows"] = [dict(item) for item in canonical]
                changed = True
            if row.get("process_events") != canonical:
                row["process_events"] = [dict(item) for item in canonical]
                changed = True
            if row.get("processEvents") != canonical:
                row["processEvents"] = [dict(item) for item in canonical]
                changed = True
    return changed


def _strip_runs_summary_fields(row: dict[str, Any]) -> None:
    """Keep summary mode lightweight even when older meta already has previews."""
    for key in (
        "messagePreview",
        "lastPreview",
        "partialPreview",
        "logPreview",
        "skills_used",
        "business_refs",
        "processRows",
        "process_rows",
        "process_events",
        "processEvents",
    ):
        row.pop(key, None)


def _align_run_runtime_identity(
    row: dict[str, Any],
    *,
    environment_name: str = "",
    local_server_origin: str = "",
    worktree_root: str = "",
) -> bool:
    changed = False
    target_environment = str(environment_name or "").strip()
    target_origin = str(local_server_origin or "").strip()
    target_worktree_root = str(worktree_root or "").strip()

    if target_environment and str(row.get("environment") or "").strip() != target_environment:
        row["environment"] = target_environment
        changed = True
    if target_origin and str(row.get("localServerOrigin") or "").strip() != target_origin:
        row["localServerOrigin"] = target_origin
        changed = True
    if target_worktree_root and str(row.get("worktree_root") or "").strip() != target_worktree_root:
        row["worktree_root"] = target_worktree_root
        changed = True
    return changed


def _attach_run_project_execution_context(
    row: dict[str, Any],
    *,
    project_id: str = "",
    channel_name: str = "",
    session_id: str = "",
) -> None:
    existing = row.get("project_execution_context")
    existing = existing if isinstance(existing, dict) else {}
    target = existing.get("target")
    if not isinstance(target, dict) or not target:
        target = {
            "project_id": str(project_id or row.get("projectId") or "").strip(),
            "channel_name": str(channel_name or row.get("channelName") or "").strip(),
            "session_id": str(session_id or row.get("sessionId") or "").strip(),
            "environment": str(row.get("environment") or "").strip(),
            "worktree_root": str(row.get("worktree_root") or "").strip(),
            "workdir": str(row.get("workdir") or "").strip(),
            "branch": str(row.get("branch") or "").strip(),
        }
    source = {
        "project_id": str(project_id or row.get("projectId") or "").strip(),
        "channel_name": str(channel_name or row.get("channelName") or "").strip(),
        "session_id": str(session_id or row.get("sessionId") or "").strip(),
        "environment": str(row.get("environment") or "").strip(),
        "worktree_root": str(row.get("worktree_root") or "").strip(),
        "workdir": str(row.get("workdir") or "").strip(),
        "branch": str(row.get("branch") or "").strip(),
    }
    row["project_execution_context"] = build_project_execution_context(
        target=target,
        source=source,
        context_source=infer_project_execution_context_source(
            stored_context_source=existing.get("context_source"),
        ),
    )


def list_runs_response(
    *,
    query_string: str,
    store: Any,
    scheduler: Any,
    maybe_trigger_restart_recovery_lazy: Callable[..., int],
    maybe_trigger_queued_recovery_lazy: Callable[..., int],
    build_run_observability_fields: Callable[..., dict[str, Any]],
    environment_name: str = "",
    local_server_origin: str = "",
    worktree_root: str = "",
) -> tuple[int, dict[str, Any]]:
    qs = parse_qs(query_string or "")
    channel_id = (qs.get("channelId") or [""])[0]
    project_id = (qs.get("projectId") or [""])[0]
    session_id = (qs.get("sessionId") or [""])[0]
    payload_mode = str((qs.get("payloadMode") or qs.get("payload_mode") or [""])[0] or "").strip().lower()
    include_payload_raw = str((qs.get("includePayload") or qs.get("include_payload") or [""])[0] or "").strip().lower()
    if payload_mode not in {"", "full", "summary", "light", "none"}:
        payload_mode = ""
    if not payload_mode and include_payload_raw:
        payload_mode = "full" if include_payload_raw in {"1", "true", "yes", "on"} else "none"
    if not payload_mode:
        payload_mode = "full"
    after_created_at = (qs.get("afterCreatedAt") or qs.get("after") or [""])[0]
    before_created_at = (qs.get("beforeCreatedAt") or qs.get("before") or [""])[0]
    limit_s = (qs.get("limit") or ["30"])[0]
    try:
        limit = max(1, min(200, int(limit_s)))
    except Exception:
        limit = 30

    def _build_payload() -> dict[str, Any]:
        runs = store.list_runs(
            channel_id=channel_id,
            project_id=project_id,
            session_id=session_id,
            limit=limit,
            after_created_at=after_created_at,
            before_created_at=before_created_at,
            payload_mode=payload_mode,
        )
        # Restart recovery remains handled by bootstrap/background paths.
        # Do not let read APIs mutate runtime state or enqueue recovery summaries,
        # otherwise an in-flight run can be misclassified during UI refresh.
        lazy_resumed = 0
        lazy_requeued = maybe_trigger_queued_recovery_lazy(
            store,
            scheduler,
            runs,
            project_id_hint=str(project_id or "").strip(),
        )
        if lazy_resumed > 0 or lazy_requeued > 0:
            runs = store.list_runs(
                channel_id=channel_id,
                project_id=project_id,
                session_id=session_id,
                limit=limit,
                after_created_at=after_created_at,
                before_created_at=before_created_at,
                payload_mode=payload_mode,
            )
        for row in runs:
            if not isinstance(row, dict):
                continue
            row.update(
                build_run_observability_fields(
                    store,
                    row,
                    infer_blocked=False,
                    include_session_semantics=(payload_mode == "full"),
                )
            )
            run_id = str(row.get("id") or "").strip()
            changed = False
            if run_id:
                changed = _normalize_terminal_text_row_fields(store, run_id, row) or changed
            changed = _align_run_runtime_identity(
                row,
                environment_name=environment_name,
                local_server_origin=local_server_origin,
                worktree_root=worktree_root,
            ) or changed
            _attach_run_project_execution_context(
                row,
                project_id=str(project_id or row.get("projectId") or "").strip(),
                channel_name=str(row.get("channelName") or "").strip(),
                session_id=str(row.get("sessionId") or "").strip(),
            )
            if changed and run_id:
                try:
                    store.save_meta(run_id, row)
                except Exception:
                    pass
            if payload_mode == "summary":
                _strip_runs_summary_fields(row)
        return {"runs": runs, "payloadMode": payload_mode}

    cache_key = _runs_list_cache_key(
        store_root=str(getattr(store, "runs_dir", "") or ""),
        channel_id=channel_id,
        project_id=project_id,
        session_id=session_id,
        after_created_at=after_created_at,
        before_created_at=before_created_at,
        limit=limit,
        payload_mode=payload_mode,
        environment_name=environment_name,
        local_server_origin=local_server_origin,
        worktree_root=worktree_root,
    )
    payload, runtime_info = _build_or_load_runs_list_payload(
        cache_key=cache_key,
        project_id=project_id,
        session_id=session_id,
        payload_mode=payload_mode,
        builder=_build_payload,
    )
    return 200, _with_runs_read_model_meta(
        payload,
        payload_mode=payload_mode,
        runtime_info=runtime_info,
    )


def get_run_detail_response(
    *,
    run_id: str,
    store: Any,
    scheduler: Any,
    maybe_trigger_restart_recovery_lazy: Callable[..., int],
    maybe_trigger_queued_recovery_lazy: Callable[..., int],
    build_run_observability_fields: Callable[..., dict[str, Any]],
    error_hint: Callable[[str], str],
) -> tuple[int, dict[str, Any]]:
    meta = store.load_meta(run_id)
    if not meta:
        return 404, {"error": "not found"}
    if hasattr(store, "reconcile_meta"):
        try:
            reconciled, changed = store.reconcile_meta(dict(meta))
            meta = reconciled
            if changed:
                store.save_meta(run_id, meta)
        except Exception:
            pass
    lazy_resumed = 0
    if lazy_resumed > 0:
        meta = store.load_meta(run_id) or meta
    lazy_requeued = maybe_trigger_queued_recovery_lazy(
        store,
        scheduler,
        [meta],
        project_id_hint=str(meta.get("projectId") or "").strip(),
    )
    if lazy_requeued > 0:
        meta = store.load_meta(run_id) or meta
    detail_cache_key = _run_detail_cache_key(store, run_id)
    if _is_terminal_run_meta(meta):
        cached_payload = _load_run_detail_cache(
            detail_cache_key,
            _run_detail_file_token(store, run_id),
        )
        if cached_payload is not None:
            return 200, cached_payload
    message = store.read_msg(run_id, limit_chars=300_000)
    last = store.read_last(run_id, limit_chars=500_000)
    log_tail = store.read_log(run_id, limit_chars=160_000)
    if not log_tail:
        log_tail = fallback_log_from_meta(meta)
    run_cli_type = str(meta.get("cliType") or "codex").strip() or "codex"
    run_cli_key = run_cli_type.lower()
    if not str(last or "").strip():
        last_file = extract_terminal_message_from_file(store._paths(run_id)["log"], cli_type=run_cli_key)
        last_tail = extract_terminal_message_text(log_tail, cli_type=run_cli_key)
        last = last_file if len(last_file) >= len(last_tail) else last_tail
    if run_cli_key == "codebuddy":
        last = safe_terminal_visible_text(last, cli_type=run_cli_key)
    agent_msgs_tail = extract_agent_messages(log_tail, max_items=200, cli_type=run_cli_key)
    agent_msgs_file = extract_agent_messages_from_file(store._paths(run_id)["log"], max_items=200, cli_type=run_cli_key)
    agent_msgs = agent_msgs_file if len(agent_msgs_file) >= len(agent_msgs_tail) else agent_msgs_tail
    partial = agent_msgs[-1] if agent_msgs else ""
    log_preview = _safe_text(log_tail.replace("\r\n", "\n").strip(), 420) if log_tail else ""
    meta_changed = False
    if log_preview and log_preview != str(meta.get("logPreview") or ""):
        meta["logPreview"] = log_preview
        meta_changed = True
    if run_cli_key in _TERMINAL_TEXT_CLIS:
        normalized_last = _safe_text(last, 300)
        if normalized_last and normalized_last != str(meta.get("lastPreview") or "").strip():
            meta["lastPreview"] = normalized_last
            meta_changed = True
        if int(meta.get("agentMessagesCount") or 0) != 0:
            meta["agentMessagesCount"] = 0
            meta_changed = True
        if str(meta.get("partialPreview") or "").strip():
            meta["partialPreview"] = ""
            meta_changed = True
        if run_cli_key in _TERMINAL_TEXT_PROCESS_CLEAR_CLIS:
            process_rows = meta.get("processRows")
            if isinstance(process_rows, list) and process_rows:
                meta["processRows"] = []
                meta_changed = True
            process_rows_alt = meta.get("process_rows")
            if isinstance(process_rows_alt, list) and process_rows_alt:
                meta["process_rows"] = []
                meta_changed = True
            process_events = meta.get("process_events")
            if isinstance(process_events, list) and process_events:
                meta["process_events"] = []
                meta_changed = True
            process_events_alt = meta.get("processEvents")
            if isinstance(process_events_alt, list) and process_events_alt:
                meta["processEvents"] = []
                meta_changed = True
        agent_msgs = []
        partial = ""
    if run_cli_key in _STANDARD_PROCESS_EVENT_CLIS:
        standard_rows = meta.get("processRows") or meta.get("process_rows") or []
        standard_events = meta.get("process_events") or meta.get("processEvents") or []
        has_rows = isinstance(standard_rows, list) and bool(standard_rows)
        has_events = isinstance(standard_events, list) and bool(standard_events)
        if not has_rows and not has_events:
            recovered_events = extract_process_events_from_file(
                store._paths(run_id)["log"],
                max_items=240,
                cli_type=run_cli_key,
            )
            if recovered_events:
                recovered_rows = [dict(row) for row in recovered_events]
                meta["processRows"] = recovered_rows
                meta["process_events"] = [dict(row) for row in recovered_events]
                meta["processEvents"] = [dict(row) for row in recovered_events]
                meta_changed = True
        elif has_rows and not has_events:
            normalized_rows = _normalize_standard_process_rows(standard_rows)
            if normalized_rows:
                meta["process_events"] = normalized_rows
                meta["processEvents"] = [dict(row) for row in normalized_rows]
                meta_changed = True
        elif has_events and not has_rows:
            normalized_events = _normalize_standard_process_rows(standard_events)
            if normalized_events:
                meta["processRows"] = normalized_events
                meta["process_events"] = [dict(row) for row in normalized_events]
                meta["processEvents"] = [dict(row) for row in normalized_events]
                meta_changed = True
        elif has_events and has_rows:
            normalized_events = _normalize_standard_process_rows(standard_events)
            if normalized_events:
                if meta.get("process_events") != normalized_events:
                    meta["process_events"] = [dict(row) for row in normalized_events]
                    meta_changed = True
                if meta.get("processEvents") != normalized_events:
                    meta["processEvents"] = [dict(row) for row in normalized_events]
                    meta_changed = True
            normalized_rows = _normalize_standard_process_rows(standard_rows)
            if normalized_rows and meta.get("processRows") != normalized_rows:
                meta["processRows"] = normalized_rows
                meta_changed = True
    if agent_msgs:
        prev_count = int(meta.get("agentMessagesCount") or 0)
        if len(agent_msgs) != prev_count:
            meta["agentMessagesCount"] = len(agent_msgs)
            meta_changed = True
        partial_preview = _safe_text(partial, 300)
        if partial_preview and partial_preview != str(meta.get("partialPreview") or ""):
            meta["partialPreview"] = partial_preview
            meta_changed = True
    existing_skills = normalize_skills_used_value(meta.get("skills_used"), max_items=20)
    if existing_skills:
        meta["skills_used"] = existing_skills
    elif not isinstance(meta.get("skills_used"), list):
        skill_texts: list[str] = []
        if last:
            skill_texts.append(last)
        if partial:
            skill_texts.append(partial)
        skill_texts.extend(agent_msgs[-20:])
        meta["skills_used"] = extract_skills_used_from_texts(skill_texts, max_items=20)
    else:
        meta["skills_used"] = []
    existing_business_refs = normalize_business_refs_value(meta.get("business_refs"), max_items=24)
    if existing_business_refs:
        meta["business_refs"] = existing_business_refs
    if (not existing_business_refs) or (not isinstance(meta.get("business_refs"), list)):
        business_texts: list[str] = []
        if last:
            business_texts.append(last)
        if partial:
            business_texts.append(partial)
        parsed_business_refs = extract_business_refs_from_texts(business_texts, max_items=24)
        if parsed_business_refs:
            meta["business_refs"] = parsed_business_refs
        elif not isinstance(meta.get("business_refs"), list):
            meta["business_refs"] = []
    if meta_changed or isinstance(meta.get("skills_used"), list) or isinstance(meta.get("business_refs"), list):
        try:
            store.save_meta(run_id, meta)
        except Exception:
            pass
    meta.update(build_run_observability_fields(store, meta, infer_blocked=True))
    _attach_run_project_execution_context(
        meta,
        project_id=str(meta.get("projectId") or "").strip(),
        channel_name=str(meta.get("channelName") or "").strip(),
        session_id=str(meta.get("sessionId") or "").strip(),
    )
    hint = error_hint(str(meta.get("error") or ""))
    process_rows = meta.get("processRows") or meta.get("process_rows") or []
    if not isinstance(process_rows, list):
        process_rows = []
    process_events = meta.get("process_events") or meta.get("processEvents") or []
    if not isinstance(process_events, list):
        process_events = []
    message_preview = _safe_text(message.replace("\r\n", "\n").strip(), 260) if message else ""
    if message_preview and message_preview != str(meta.get("messagePreview") or ""):
        meta["messagePreview"] = message_preview
        meta_changed = True
    latest_process_preview = _latest_process_row_preview(process_rows, 300)
    if partial:
        partial_preview = _safe_text(partial, 300)
        if partial_preview and partial_preview != str(meta.get("partialPreview") or ""):
            meta["partialPreview"] = partial_preview
            meta_changed = True
    elif latest_process_preview and latest_process_preview != str(meta.get("partialPreview") or ""):
        meta["partialPreview"] = latest_process_preview
        meta_changed = True
    effective_last_preview = _safe_text(
        safe_terminal_visible_text(last, cli_type=run_cli_key).replace("\r\n", "\n").strip(),
        300,
    ) if last else ""
    if not effective_last_preview:
        effective_last_preview = latest_process_preview
    if effective_last_preview and effective_last_preview != str(meta.get("lastPreview") or ""):
        meta["lastPreview"] = effective_last_preview
        meta_changed = True
    if meta_changed:
        try:
            store.save_meta(run_id, meta)
        except Exception:
            pass
    payload = {
        "run": meta,
        "message": message,
        "lastMessage": last,
        "logTail": log_tail,
        "logPreview": log_preview,
        "process": log_tail,
        "partialMessage": partial,
        "agentMessages": agent_msgs,
        "processRows": process_rows,
        "processEvents": process_events,
        "errorHint": hint,
    }
    if _is_terminal_run_meta(meta):
        _store_run_detail_cache(
            detail_cache_key,
            _run_detail_file_token(store, run_id),
            payload,
        )
    return 200, payload


def perform_run_action_response(
    *,
    run_id: str,
    body: dict[str, Any],
    store: Any,
    scheduler: Any,
    run_process_registry: Any,
    audit_action: Callable[..., None],
    now_iso: Callable[[], str],
    require_scheduler_enabled: Callable[[], bool],
    dispatch_terminal_callback_for_run: Callable[..., None],
) -> tuple[int, dict[str, Any]]:
    if not run_id:
        audit_action(
            run_id="",
            action="",
            requested_action="",
            http_status=400,
            outcome="rejected",
            error="missing run id",
        )
        return 400, {"error": "missing run id"}
    action = str(body.get("action") or "").strip().lower()
    requested_action = action
    meta = store.load_meta(run_id)
    if not meta:
        audit_action(
            run_id=run_id,
            action=action,
            requested_action=requested_action,
            http_status=404,
            outcome="rejected",
            error="run not found",
        )
        return 404, {"error": "run not found"}
    status = str(meta.get("status") or "").strip().lower()
    if action == "cancel_edit":
        if status != "queued":
            audit_action(
                run_id=run_id,
                action=action,
                requested_action=requested_action,
                http_status=409,
                outcome="rejected",
                error="run is not queued",
                meta=meta,
            )
            return 409, {"error": "run is not queued", "status": status}
        session_id = str(meta.get("sessionId") or "").strip()
        removed = False
        if scheduler is not None and require_scheduler_enabled():
            removed = scheduler.cancel_queued_run(run_id, session_id=session_id)
        if not removed:
            meta2 = store.load_meta(run_id) or meta
            status2 = str(meta2.get("status") or "").strip().lower()
            if status2 != "queued":
                audit_action(
                    run_id=run_id,
                    action=action,
                    requested_action=requested_action,
                    http_status=409,
                    outcome="rejected",
                    error="run is no longer queued",
                    meta=meta2,
                )
                return 409, {"error": "run is no longer queued", "status": status2 or status}
            meta = meta2
            meta["queueDesynced"] = True
            meta["queueDesyncedAt"] = now_iso()
        message = store.read_msg(run_id)
        attachments = []
        raw_attachments = meta.get("attachments")
        if isinstance(raw_attachments, list):
            for att in raw_attachments:
                if not isinstance(att, dict):
                    continue
                attachments.append(
                    {
                        "filename": str(att.get("filename") or ""),
                        "originalName": str(att.get("originalName") or att.get("filename") or ""),
                        "url": str(att.get("url") or ""),
                    }
                )
        cancelled_at = now_iso()
        meta["hidden"] = True
        meta["cancelAction"] = "cancel_edit"
        meta["cancelledAt"] = cancelled_at
        meta["status"] = "interrupted"
        meta["display_state"] = "interrupted"
        meta["outcome_state"] = "interrupted_user"
        meta["failure_class"] = "interrupted"
        meta["error_class"] = "user_cancelled"
        meta["recovery_required"] = False
        meta["recovery_mode"] = ""
        meta["finishedAt"] = str(meta.get("finishedAt") or "").strip() or cancelled_at
        meta["error"] = str(meta.get("error") or "").strip() or "cancelled by user before start"
        store.save_meta(run_id, meta)
        audit_action(
            run_id=run_id,
            action=action,
            requested_action=requested_action,
            http_status=200,
            outcome="accepted",
            meta=meta,
        )
        return 200, {
            "ok": True,
            "run": meta,
            "restored": {
                "message": message,
                "attachments": attachments,
            },
        }
    if action == "cancel_retry":
        if status not in {"retry_waiting", "queued"}:
            audit_action(
                run_id=run_id,
                action=action,
                requested_action=requested_action,
                http_status=409,
                outcome="rejected",
                error="run is not retry_waiting",
                meta=meta,
            )
            return 409, {"error": "run is not retry_waiting", "status": status}
        session_id = str(meta.get("sessionId") or "").strip()
        removed = False
        if scheduler is not None and require_scheduler_enabled():
            removed = scheduler.cancel_retry_waiting(run_id, session_id=session_id)
        if not removed:
            meta2 = store.load_meta(run_id) or meta
            status2 = str(meta2.get("status") or "").strip().lower()
            if status2 not in {"retry_waiting", "queued"}:
                audit_action(
                    run_id=run_id,
                    action=action,
                    requested_action=requested_action,
                    http_status=409,
                    outcome="rejected",
                    error="run is no longer retry_waiting",
                    meta=meta2,
                )
                return 409, {"error": "run is no longer retry_waiting", "status": status2 or status}
        meta["status"] = "done"
        meta["error"] = ""
        meta["retryCancelled"] = True
        meta["retryCancelledAt"] = now_iso()
        meta["cancelAction"] = "cancel_retry"
        meta["finishedAt"] = now_iso()
        store.save_meta(run_id, meta)
        try:
            dispatch_terminal_callback_for_run(store, run_id, scheduler=scheduler, meta=meta)
        except Exception:
            pass
        if scheduler is not None and session_id:
            try:
                scheduler.kick_session(session_id)
            except Exception:
                pass
        audit_action(
            run_id=run_id,
            action=action,
            requested_action=requested_action,
            http_status=200,
            outcome="accepted",
            meta=meta,
        )
        return 200, {"ok": True, "runId": run_id, "action": "cancel_retry", "run": meta}
    if action == "interrupt":
        if status != "running":
            audit_action(
                run_id=run_id,
                action=action,
                requested_action=requested_action,
                http_status=409,
                outcome="rejected",
                error="run is not running",
                meta=meta,
            )
            return 409, {"error": "run is not running", "status": status}
        tracked_before = run_process_registry.is_tracked(run_id)
        cli_type = str(meta.get("cliType") or "codex").strip() or "codex"
        ok = run_process_registry.request_interrupt(run_id, cli_type=cli_type)
        if not ok:
            audit_action(
                run_id=run_id,
                action=action,
                requested_action=requested_action,
                http_status=409,
                outcome="rejected",
                error="run is not interruptible",
                meta=meta,
            )
            return 409, {"error": "run is not interruptible", "status": status}
        meta2 = store.load_meta(run_id) or meta
        if str(meta2.get("status") or "").strip().lower() == "running":
            requested_at = now_iso()
            meta2["interruptRequestedAt"] = requested_at
            meta2["interruptRequestedBy"] = "user"
            meta2["interrupt_origin"] = "user"
            meta2["interrupt_requested_by"] = "user"
            meta2["interrupt_requested_at"] = requested_at
            try:
                store.save_meta(run_id, meta2)
            except Exception:
                pass
        if not tracked_before:
            meta2 = store.load_meta(run_id) or meta2
            if str(meta2.get("status") or "").strip().lower() == "running":
                meta2["status"] = "error"
                meta2["error"] = "interrupted by user"
                meta2["finishedAt"] = now_iso()
                meta2["interrupt_origin"] = "user"
                meta2["interrupt_requested_by"] = "user"
                if not str(meta2.get("interrupt_requested_at") or "").strip():
                    meta2["interrupt_requested_at"] = str(meta2.get("interruptRequestedAt") or "").strip() or now_iso()
                meta2["chain_state"] = "cancelled_by_user"
                store.save_meta(run_id, meta2)
                try:
                    dispatch_terminal_callback_for_run(store, run_id, scheduler=scheduler, meta=meta2)
                except Exception:
                    pass
                session_id = str(meta2.get("sessionId") or "").strip()
                if scheduler is not None and session_id:
                    try:
                        scheduler.kick_session(session_id)
                    except Exception:
                        pass
        audit_action(
            run_id=run_id,
            action=action,
            requested_action=requested_action,
            http_status=200,
            outcome="accepted",
            meta=meta,
        )
        return 200, {"ok": True, "runId": run_id, "action": "interrupt"}
    audit_action(
        run_id=run_id,
        action=action,
        requested_action=requested_action,
        http_status=400,
        outcome="rejected",
        error="unknown action",
        meta=meta,
    )
    return 400, {"error": "unknown action"}
