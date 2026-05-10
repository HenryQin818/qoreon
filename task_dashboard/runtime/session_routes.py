# -*- coding: utf-8 -*-

from __future__ import annotations

import copy
import os
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import parse_qs

import json

from task_dashboard.runtime.agent_display_name import apply_agent_display_fields, build_agent_identity_audit
from task_dashboard.runtime.session_views import apply_session_heartbeat_summary_rows

_SESSIONS_PAYLOAD_CACHE_LOCK = threading.Lock()
_SESSIONS_PAYLOAD_CACHE: dict[str, dict[str, Any]] = {}
_SESSIONS_PAYLOAD_CACHE_INFLIGHT: dict[str, dict[str, Any]] = {}
_SESSIONS_PAYLOAD_CACHE_INVALIDATED_AT: dict[str, float] = {}


def _sessions_payload_cache_ttl_s() -> float:
    raw = str(os.environ.get("CCB_SESSIONS_LIST_CACHE_TTL_MS") or "").strip()
    if raw:
        try:
            value = float(raw) / 1000.0
            return max(0.0, min(value, 15.0))
        except Exception:
            pass
    return 4.0


def _sessions_payload_cache_inflight_wait_s() -> float:
    raw = str(os.environ.get("CCB_SESSIONS_LIST_CACHE_INFLIGHT_WAIT_MS") or "").strip()
    if raw:
        try:
            value = float(raw) / 1000.0
            return max(0.2, min(value, 30.0))
        except Exception:
            pass
    return 8.0


def _sessions_payload_cache_key(
    *,
    scope: str,
    project_id: str,
    channel_name: str,
    include_deleted: bool,
    environment_name: str,
    worktree_root: Any,
    payload_mode: str = "full",
) -> str:
    return "|".join(
        [
            str(scope or "").strip(),
            str(project_id or "").strip(),
            str(channel_name or "").strip(),
            "1" if include_deleted else "0",
            str(payload_mode or "full").strip().lower(),
            str(environment_name or "").strip(),
            str(worktree_root or "").strip(),
        ]
    )


def _prune_sessions_payload_cache_locked(now_mono: float, ttl_s: float) -> None:
    expired_keys: list[str] = []
    for key, entry in list(_SESSIONS_PAYLOAD_CACHE.items()):
        checked = float((entry or {}).get("checked_at_mono") or 0.0)
        if ttl_s <= 0 or (now_mono - checked) > ttl_s:
            expired_keys.append(key)
    for key in expired_keys:
        _SESSIONS_PAYLOAD_CACHE.pop(key, None)
    inflight_expired: list[str] = []
    inflight_ttl_s = max(_sessions_payload_cache_inflight_wait_s() * 2.0, 5.0)
    for key, entry in list(_SESSIONS_PAYLOAD_CACHE_INFLIGHT.items()):
        started = float((entry or {}).get("started_at_mono") or 0.0)
        event = (entry or {}).get("event")
        if isinstance(event, threading.Event) and event.is_set():
            inflight_expired.append(key)
            continue
        if started > 0 and (now_mono - started) > inflight_ttl_s:
            inflight_expired.append(key)
    for key in inflight_expired:
        _SESSIONS_PAYLOAD_CACHE_INFLIGHT.pop(key, None)
    invalidated_expired: list[str] = []
    invalidated_ttl_s = max(ttl_s * 4.0, 30.0)
    for key, invalidated_at in list(_SESSIONS_PAYLOAD_CACHE_INVALIDATED_AT.items()):
        if invalidated_at <= 0:
            invalidated_expired.append(key)
            continue
        if (now_mono - float(invalidated_at)) > invalidated_ttl_s:
            invalidated_expired.append(key)
    for key in invalidated_expired:
        _SESSIONS_PAYLOAD_CACHE_INVALIDATED_AT.pop(key, None)
    if len(_SESSIONS_PAYLOAD_CACHE) <= 32:
        return
    ordered = sorted(
        _SESSIONS_PAYLOAD_CACHE.items(),
        key=lambda item: float((item[1] or {}).get("checked_at_mono") or 0.0),
        reverse=True,
    )
    for key, _entry in ordered[32:]:
        _SESSIONS_PAYLOAD_CACHE.pop(key, None)


def _load_sessions_payload_cache(
    cache_key: str,
    *,
    project_id: str,
    now_mono: Optional[float] = None,
    ttl_s: Optional[float] = None,
) -> Optional[dict[str, Any]]:
    effective_ttl = _sessions_payload_cache_ttl_s() if ttl_s is None else float(ttl_s)
    if effective_ttl <= 0:
        return None
    checked_now = time.monotonic() if now_mono is None else float(now_mono)
    invalidated_at = float(_SESSIONS_PAYLOAD_CACHE_INVALIDATED_AT.get(str(project_id or "").strip()) or 0.0)
    cached = _SESSIONS_PAYLOAD_CACHE.get(cache_key)
    if not isinstance(cached, dict):
        return None
    checked = float(cached.get("checked_at_mono") or 0.0)
    if (checked_now - checked) > effective_ttl:
        return None
    payload = cached.get("payload")
    if not isinstance(payload, dict):
        return None
    build_started_at = float(cached.get("build_started_at_mono") or checked)
    if build_started_at < invalidated_at:
        return None
    return copy.deepcopy(payload)


def _store_sessions_payload_cache(
    cache_key: str,
    payload: dict[str, Any],
    *,
    project_id: str,
    build_started_at_mono: float,
) -> None:
    ttl_s = _sessions_payload_cache_ttl_s()
    if ttl_s <= 0 or not isinstance(payload, dict):
        return
    now_mono = time.monotonic()
    with _SESSIONS_PAYLOAD_CACHE_LOCK:
        _prune_sessions_payload_cache_locked(now_mono, ttl_s)
        _SESSIONS_PAYLOAD_CACHE[cache_key] = {
            "checked_at_mono": now_mono,
            "build_started_at_mono": max(float(build_started_at_mono or 0.0), now_mono),
            "project_id": str(project_id or "").strip(),
            "payload": copy.deepcopy(payload),
        }


def _invalidate_sessions_payload_cache(project_id: str = "", *, channel_name: str = "") -> None:
    pid = str(project_id or "").strip()
    cname = str(channel_name or "").strip()
    now_mono = time.monotonic()
    with _SESSIONS_PAYLOAD_CACHE_LOCK:
        if not pid:
            _SESSIONS_PAYLOAD_CACHE.clear()
            _SESSIONS_PAYLOAD_CACHE_INFLIGHT.clear()
            _SESSIONS_PAYLOAD_CACHE_INVALIDATED_AT.clear()
            return
        _SESSIONS_PAYLOAD_CACHE_INVALIDATED_AT[pid] = now_mono
        for key, entry in list(_SESSIONS_PAYLOAD_CACHE.items()):
            entry_project_id = str((entry or {}).get("project_id") or "").strip()
            if entry_project_id != pid:
                continue
            if cname and f"|{cname}|" not in key:
                continue
            _SESSIONS_PAYLOAD_CACHE.pop(key, None)


def _build_or_load_sessions_payload(
    *,
    cache_key: str,
    project_id: str,
    builder: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    ttl_s = _sessions_payload_cache_ttl_s()
    if ttl_s <= 0:
        return builder()
    build_started_at_mono = time.monotonic()
    owns_build = False
    inflight_event: Optional[threading.Event] = None
    wait_s = _sessions_payload_cache_inflight_wait_s()
    while True:
        now_mono = time.monotonic()
        with _SESSIONS_PAYLOAD_CACHE_LOCK:
            _prune_sessions_payload_cache_locked(now_mono, ttl_s)
            cached_payload = _load_sessions_payload_cache(
                cache_key,
                project_id=project_id,
                now_mono=now_mono,
                ttl_s=ttl_s,
            )
            if cached_payload is not None:
                return cached_payload
            inflight = _SESSIONS_PAYLOAD_CACHE_INFLIGHT.get(cache_key)
            inflight_event = None
            if isinstance(inflight, dict):
                candidate = inflight.get("event")
                if isinstance(candidate, threading.Event):
                    inflight_event = candidate
            if inflight_event is None:
                inflight_event = threading.Event()
                _SESSIONS_PAYLOAD_CACHE_INFLIGHT[cache_key] = {
                    "event": inflight_event,
                    "started_at_mono": now_mono,
                    "project_id": str(project_id or "").strip(),
                }
                build_started_at_mono = now_mono
                owns_build = True
                break
        if inflight_event is not None:
            inflight_event.wait(wait_s)
    try:
        payload = builder()
        _store_sessions_payload_cache(
            cache_key,
            payload,
            project_id=project_id,
            build_started_at_mono=build_started_at_mono,
        )
        return payload
    finally:
        if owns_build and inflight_event is not None:
            with _SESSIONS_PAYLOAD_CACHE_LOCK:
                current = _SESSIONS_PAYLOAD_CACHE_INFLIGHT.get(cache_key)
                if isinstance(current, dict) and current.get("event") is inflight_event:
                    _SESSIONS_PAYLOAD_CACHE_INFLIGHT.pop(cache_key, None)
            inflight_event.set()


def build_sessions_list_payload(
    *,
    session_store: Any,
    store: Any,
    project_id: str,
    channel_name: str = "",
    include_deleted: bool = False,
    environment_name: str,
    worktree_root: Any,
    apply_effective_primary_flags: Callable[[Any, str, list[dict[str, Any]]], list[dict[str, Any]]],
    decorate_sessions_display_fields: Callable[[list[dict[str, Any]]], list[dict[str, Any]]],
    apply_session_context_rows: Callable[..., list[dict[str, Any]]],
    apply_session_work_context: Callable[..., dict[str, Any]],
    attach_runtime_state_to_sessions: Callable[[Any, list[dict[str, Any]]], list[dict[str, Any]]],
    heartbeat_runtime: Any,
    load_session_heartbeat_config: Callable[[dict[str, Any]], dict[str, Any]],
    heartbeat_summary_payload: Callable[[Any], Any],
) -> dict[str, Any]:
    sessions = session_store.list_sessions(
        project_id,
        channel_name if channel_name else None,
        include_deleted=include_deleted,
    )
    sessions = apply_effective_primary_flags(session_store, project_id, sessions)
    sessions = decorate_sessions_display_fields(sessions)
    sessions = apply_session_context_rows(
        sessions,
        project_id=project_id,
        environment_name=environment_name,
        worktree_root=worktree_root,
        apply_session_work_context=apply_session_work_context,
    )
    sessions = apply_session_heartbeat_summary_rows(
        sessions,
        project_id=project_id,
        heartbeat_runtime=heartbeat_runtime,
        load_session_heartbeat_config=load_session_heartbeat_config,
        heartbeat_summary_payload=heartbeat_summary_payload,
    )
    sessions = attach_runtime_state_to_sessions(store, sessions, project_id=project_id)
    sessions = apply_agent_display_fields(sessions)
    return {
        "sessions": sessions,
        "agent_identity_audit": build_agent_identity_audit(sessions, project_id=project_id),
    }


def build_channel_sessions_payload(
    *,
    session_store: Any,
    store: Any,
    project_id: str,
    channel_name: str,
    include_deleted: bool = False,
    environment_name: str,
    worktree_root: Any,
    apply_effective_primary_flags: Callable[[Any, str, list[dict[str, Any]]], list[dict[str, Any]]],
    decorate_sessions_display_fields: Callable[[list[dict[str, Any]]], list[dict[str, Any]]],
    apply_session_context_rows: Callable[..., list[dict[str, Any]]],
    apply_session_work_context: Callable[..., dict[str, Any]],
    resolve_channel_primary_session_id: Callable[[Any, str, str], str],
    heartbeat_runtime: Any,
    load_session_heartbeat_config: Callable[[dict[str, Any]], dict[str, Any]],
    heartbeat_summary_payload: Callable[[Any], Any],
) -> dict[str, Any]:
    sessions = session_store.list_sessions(
        project_id,
        channel_name,
        include_deleted=include_deleted,
    )
    sessions = apply_effective_primary_flags(session_store, project_id, sessions)
    sessions = decorate_sessions_display_fields(sessions)
    sessions = apply_session_context_rows(
        sessions,
        project_id=project_id,
        environment_name=environment_name,
        worktree_root=worktree_root,
        apply_session_work_context=apply_session_work_context,
    )
    sessions = apply_session_heartbeat_summary_rows(
        sessions,
        project_id=project_id,
        heartbeat_runtime=heartbeat_runtime,
        load_session_heartbeat_config=load_session_heartbeat_config,
        heartbeat_summary_payload=heartbeat_summary_payload,
    )
    sessions = apply_agent_display_fields(sessions)
    primary_session_id = resolve_channel_primary_session_id(session_store, project_id, channel_name)
    return {
        "project_id": project_id,
        "channel_name": channel_name,
        "primary_session_id": primary_session_id,
        "sessions": sessions,
        "count": len(sessions),
        "agent_identity_audit": build_agent_identity_audit(sessions, project_id=project_id),
    }


def build_session_detail_response(
    *,
    session_store: Any,
    store: Any,
    session_id: str,
    environment_name: str,
    worktree_root: Any,
    heartbeat_runtime: Any,
    infer_project_id_for_session: Callable[[Any, str], str],
    apply_effective_primary_flags: Callable[[Any, str, list[dict[str, Any]]], list[dict[str, Any]]],
    decorate_session_display_fields: Callable[[dict[str, Any]], dict[str, Any]],
    build_session_detail_payload: Callable[..., dict[str, Any]],
    apply_session_work_context: Callable[..., dict[str, Any]],
    build_project_session_runtime_index: Callable[[Any, str], dict[str, Any]],
    build_session_runtime_state_for_row: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]],
    load_session_heartbeat_config: Callable[[dict[str, Any]], dict[str, Any]],
    heartbeat_summary_payload: Callable[[Any], Any],
) -> Optional[dict[str, Any]]:
    session = session_store.get_session(session_id)
    if not session:
        return None
    project_id = str(session.get("project_id") or "").strip() or infer_project_id_for_session(store, session_id)
    session = apply_effective_primary_flags(session_store, project_id, [session])[0]
    session = decorate_session_display_fields(session)
    session = apply_agent_display_fields([session])[0]
    return build_session_detail_payload(
        session,
        session_id=session_id,
        project_id=project_id,
        environment_name=environment_name,
        worktree_root=worktree_root,
        store=store,
        heartbeat_runtime=heartbeat_runtime,
        apply_session_work_context=apply_session_work_context,
        build_project_session_runtime_index=build_project_session_runtime_index,
        build_session_runtime_state_for_row=build_session_runtime_state_for_row,
        load_session_heartbeat_config=load_session_heartbeat_config,
        heartbeat_summary_payload=heartbeat_summary_payload,
    )


def _coerce_bool(value: str, default: bool) -> bool:
    """Convert a string value to boolean."""
    if not value:
        return default
    return value.lower() in ("1", "true", "yes", "on")


_SESSION_SUMMARY_FIELDS = (
    "id",
    "sessionId",
    "session_id",
    "project_id",
    "projectId",
    "channel_name",
    "channelName",
    "cli_type",
    "cliType",
    "role",
    "alias",
    "display_name",
    "display_name_source",
    "agent_display_name",
    "agent_display_name_source",
    "agent_name_state",
    "agent_display_issue",
    "codex_title",
    "environment",
    "worktree_root",
    "workdir",
    "branch",
    "project_execution_context",
    "team_expansion_hint_state",
    "team_expansion_hint_summary",
    "team_expansion_hint_blocked_summary",
    "team_expansion_hint_prompt",
    "team_expansion_hint",
    "runtime_state",
    "session_health_state",
    "session_display_state",
    "session_display_reason",
    "latest_run_summary",
    "latest_effective_run_summary",
    "heartbeat_summary",
    "memo_summary",
    "conversation_list_metrics",
    "status",
    "created_at",
    "last_used_at",
    "is_primary",
    "is_deleted",
    "deleted_at",
    "deleted_reason",
    "source",
)


def _normalize_sessions_payload_mode(qs: dict[str, list[str]]) -> str:
    raw = str(
        (
            qs.get("payloadMode")
            or qs.get("payload_mode")
            or qs.get("queryMode")
            or qs.get("query_mode")
            or [""]
        )[0]
        or ""
    ).strip().lower()
    if raw in {"summary", "light", "full"}:
        return raw
    return "full"


def _session_summary_row(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in _SESSION_SUMMARY_FIELDS:
        if key in row:
            value = row.get(key)
            out[key] = copy.deepcopy(value) if isinstance(value, (dict, list)) else value
    return out


def _sessions_read_model_meta(*, payload_mode: str) -> dict[str, Any]:
    return {
        "version": "p0a.v1",
        "scope": "sessions",
        "payload_mode": payload_mode,
        "compat_mode": "additive_only",
        "cache_strategy": "ttl_single_flight",
        "cache_ttl_ms": int(_sessions_payload_cache_ttl_s() * 1000),
        "inflight_wait_ms": int(_sessions_payload_cache_inflight_wait_s() * 1000),
        "summary_fields": list(_SESSION_SUMMARY_FIELDS) if payload_mode in {"summary", "light"} else [],
    }


def build_sessions_summary_payload(
    *,
    session_store: Any,
    store: Any,
    project_id: str,
    channel_name: str = "",
    include_deleted: bool = False,
    environment_name: str,
    worktree_root: Any,
    apply_effective_primary_flags: Callable[[Any, str, list[dict[str, Any]]], list[dict[str, Any]]],
    decorate_sessions_display_fields: Callable[[list[dict[str, Any]]], list[dict[str, Any]]],
    apply_session_context_rows: Callable[..., list[dict[str, Any]]],
    apply_session_work_context: Callable[..., dict[str, Any]],
    attach_runtime_state_to_sessions: Callable[[Any, list[dict[str, Any]]], list[dict[str, Any]]],
) -> dict[str, Any]:
    sessions = session_store.list_sessions(
        project_id,
        channel_name if channel_name else None,
        include_deleted=include_deleted,
    )
    sessions = apply_effective_primary_flags(session_store, project_id, sessions)
    sessions = decorate_sessions_display_fields(sessions)
    sessions = apply_session_context_rows(
        sessions,
        project_id=project_id,
        environment_name=environment_name,
        worktree_root=worktree_root,
        apply_session_work_context=apply_session_work_context,
    )
    sessions = attach_runtime_state_to_sessions(store, sessions, project_id=project_id)
    sessions = apply_agent_display_fields(sessions)
    summary_rows = [_session_summary_row(row if isinstance(row, dict) else {}) for row in sessions]
    return {
        "project_id": project_id,
        "channel_name": channel_name,
        "count": len(summary_rows),
        "payloadMode": "summary",
        "sessions": summary_rows,
        "agent_identity_audit": build_agent_identity_audit(summary_rows, project_id=project_id),
        "sessions_read_model": _sessions_read_model_meta(payload_mode="summary"),
    }


def list_sessions_response(
    *,
    query_string: str,
    session_store: Any,
    store: Any,
    environment_name: str,
    worktree_root: Any,
    apply_effective_primary_flags: Callable[[Any, str, list[dict[str, Any]]], list[dict[str, Any]]],
    decorate_sessions_display_fields: Callable[[list[dict[str, Any]]], list[dict[str, Any]]],
    apply_session_context_rows: Callable[..., list[dict[str, Any]]],
    apply_session_work_context: Callable[..., dict[str, Any]],
    attach_runtime_state_to_sessions: Callable[[Any, list[dict[str, Any]]], list[dict[str, Any]]],
    heartbeat_runtime: Any,
    load_session_heartbeat_config: Callable[[dict[str, Any]], dict[str, Any]],
    heartbeat_summary_payload: Callable[[Any], Any],
) -> tuple[int, dict[str, Any]]:
    """Handle GET /api/sessions - list sessions with optional filters."""
    qs = parse_qs(query_string or "")
    project_id = (qs.get("project_id") or [""])[0]
    channel_name = (qs.get("channel_name") or [""])[0]
    include_deleted = _coerce_bool((qs.get("include_deleted") or qs.get("includeDeleted") or [""])[0], False)
    payload_mode = _normalize_sessions_payload_mode(qs)

    if not project_id:
        return 400, {"error": "missing project_id"}

    cache_key = _sessions_payload_cache_key(
        scope="sessions",
        project_id=project_id,
        channel_name=channel_name,
        include_deleted=include_deleted,
        environment_name=environment_name,
        worktree_root=worktree_root,
        payload_mode=payload_mode,
    )
    if payload_mode in {"summary", "light"}:
        payload = _build_or_load_sessions_payload(
            cache_key=cache_key,
            project_id=project_id,
            builder=lambda: build_sessions_summary_payload(
                session_store=session_store,
                store=store,
                project_id=project_id,
                channel_name=channel_name,
                include_deleted=include_deleted,
                environment_name=environment_name,
                worktree_root=worktree_root,
                apply_effective_primary_flags=apply_effective_primary_flags,
                decorate_sessions_display_fields=decorate_sessions_display_fields,
                apply_session_context_rows=apply_session_context_rows,
                apply_session_work_context=apply_session_work_context,
                attach_runtime_state_to_sessions=attach_runtime_state_to_sessions,
            ),
        )
        payload["payloadMode"] = payload_mode
        payload["sessions_read_model"] = _sessions_read_model_meta(payload_mode=payload_mode)
        return 200, payload

    payload = _build_or_load_sessions_payload(
        cache_key=cache_key,
        project_id=project_id,
        builder=lambda: build_sessions_list_payload(
            session_store=session_store,
            store=store,
            project_id=project_id,
            channel_name=channel_name,
            include_deleted=include_deleted,
            environment_name=environment_name,
            worktree_root=worktree_root,
            apply_effective_primary_flags=apply_effective_primary_flags,
            decorate_sessions_display_fields=decorate_sessions_display_fields,
            apply_session_context_rows=apply_session_context_rows,
            apply_session_work_context=apply_session_work_context,
            attach_runtime_state_to_sessions=attach_runtime_state_to_sessions,
            heartbeat_runtime=heartbeat_runtime,
            load_session_heartbeat_config=load_session_heartbeat_config,
            heartbeat_summary_payload=heartbeat_summary_payload,
        ),
    )
    payload["payloadMode"] = "full"
    payload["sessions_read_model"] = _sessions_read_model_meta(payload_mode="full")
    return 200, payload


def list_channel_sessions_response(
    *,
    query_string: str,
    session_store: Any,
    store: Any,
    environment_name: str,
    worktree_root: Any,
    apply_effective_primary_flags: Callable[[Any, str, list[dict[str, Any]]], list[dict[str, Any]]],
    decorate_sessions_display_fields: Callable[[list[dict[str, Any]]], list[dict[str, Any]]],
    apply_session_context_rows: Callable[..., list[dict[str, Any]]],
    apply_session_work_context: Callable[..., dict[str, Any]],
    resolve_channel_primary_session_id: Callable[[Any, str, str], str],
    heartbeat_runtime: Any,
    load_session_heartbeat_config: Callable[[dict[str, Any]], dict[str, Any]],
    heartbeat_summary_payload: Callable[[Any], Any],
) -> tuple[int, dict[str, Any]]:
    """Handle GET /api/channel-sessions - list sessions for a specific channel."""
    qs = parse_qs(query_string or "")
    project_id = (qs.get("project_id") or [""])[0]
    channel_name = (qs.get("channel_name") or [""])[0]
    include_deleted = _coerce_bool((qs.get("include_deleted") or qs.get("includeDeleted") or [""])[0], False)

    if not project_id:
        return 400, {"error": "missing project_id"}
    if not channel_name:
        return 400, {"error": "missing channel_name"}

    cache_key = _sessions_payload_cache_key(
        scope="channel_sessions",
        project_id=project_id,
        channel_name=channel_name,
        include_deleted=include_deleted,
        environment_name=environment_name,
        worktree_root=worktree_root,
    )
    payload = _build_or_load_sessions_payload(
        cache_key=cache_key,
        project_id=project_id,
        builder=lambda: build_channel_sessions_payload(
            session_store=session_store,
            store=store,
            project_id=project_id,
            channel_name=channel_name,
            include_deleted=include_deleted,
            environment_name=environment_name,
            worktree_root=worktree_root,
            apply_effective_primary_flags=apply_effective_primary_flags,
            decorate_sessions_display_fields=decorate_sessions_display_fields,
            apply_session_context_rows=apply_session_context_rows,
            apply_session_work_context=apply_session_work_context,
            resolve_channel_primary_session_id=resolve_channel_primary_session_id,
            heartbeat_runtime=heartbeat_runtime,
            load_session_heartbeat_config=load_session_heartbeat_config,
            heartbeat_summary_payload=heartbeat_summary_payload,
        ),
    )
    return 200, payload


def get_session_detail_response(
    *,
    session_id: str,
    session_store: Any,
    store: Any,
    environment_name: str,
    worktree_root: Any,
    heartbeat_runtime: Any,
    infer_project_id_for_session: Callable[[Any, str], str],
    apply_effective_primary_flags: Callable[[Any, str, list[dict[str, Any]]], list[dict[str, Any]]],
    decorate_session_display_fields: Callable[[dict[str, Any]], dict[str, Any]],
    build_session_detail_payload: Callable[..., dict[str, Any]],
    apply_session_work_context: Callable[..., dict[str, Any]],
    build_project_session_runtime_index: Callable[[Any, str], dict[str, Any]],
    build_session_runtime_state_for_row: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]],
    load_session_heartbeat_config: Callable[[dict[str, Any]], dict[str, Any]],
    heartbeat_summary_payload: Callable[[Any], Any],
) -> tuple[int, dict[str, Any]]:
    """Handle GET /api/sessions/{session_id} - get single session details."""
    session = session_store.get_session(session_id)
    if not session:
        return 404, {"error": "session not found"}
    project_id = str(session.get("project_id") or "").strip() or infer_project_id_for_session(store, session_id)
    cache_key = _sessions_payload_cache_key(
        scope="session_detail",
        project_id=project_id,
        channel_name=session_id,
        include_deleted=False,
        environment_name=environment_name,
        worktree_root=worktree_root,
    )
    def _build_payload() -> dict[str, Any]:
        return build_session_detail_response(
            session_store=session_store,
            store=store,
            session_id=session_id,
            environment_name=environment_name,
            worktree_root=worktree_root,
            heartbeat_runtime=heartbeat_runtime,
            infer_project_id_for_session=infer_project_id_for_session,
            apply_effective_primary_flags=apply_effective_primary_flags,
            decorate_session_display_fields=decorate_session_display_fields,
            build_session_detail_payload=build_session_detail_payload,
            apply_session_work_context=apply_session_work_context,
            build_project_session_runtime_index=build_project_session_runtime_index,
            build_session_runtime_state_for_row=build_session_runtime_state_for_row,
            load_session_heartbeat_config=load_session_heartbeat_config,
            heartbeat_summary_payload=heartbeat_summary_payload,
        ) or {"error": "session not found"}

    payload = _build_or_load_sessions_payload(
        cache_key=cache_key,
        project_id=project_id,
        builder=_build_payload,
    )
    if payload is None:
        return 404, {"error": "session not found"}
    if payload.get("error") == "session not found":
        return 404, payload
    return 200, payload


def dedup_session_channel_response(
    *,
    body: dict[str, Any],
    session_store: Any,
    safe_text: Callable[[Any, int], str],
    now_iso: Callable[[], str],
    coerce_bool: Callable[[Any, bool], bool],
) -> tuple[int, dict[str, Any]]:
    """Handle POST /api/sessions/dedup - deduplicate channel sessions."""
    project_id = safe_text(body.get("project_id") if "project_id" in body else body.get("projectId"), 120).strip()
    channel_name = safe_text(body.get("channel_name") if "channel_name" in body else body.get("channelName"), 240).strip()
    keep_session_id = safe_text(
        body.get("keep_session_id") if "keep_session_id" in body else body.get("keepSessionId"),
        120,
    ).strip()
    strategy = safe_text(body.get("strategy"), 24).strip().lower() or "latest"

    if not project_id or not channel_name:
        return 400, {"error": "missing project_id or channel_name"}
    if strategy not in {"latest", "first"}:
        return 400, {"error": "invalid strategy"}

    result = session_store.dedup_channel_sessions(
        project_id=project_id,
        channel_name=channel_name,
        keep_session_id=keep_session_id,
        strategy=strategy,
    )

    log_entry = {
        "at": now_iso(),
        "project_id": project_id,
        "channel_name": channel_name,
        "keep_session_id": keep_session_id,
        "strategy": strategy,
        "result": result,
    }
    log_path = _append_session_dedup_log(log_entry)
    return 200, {"ok": True, "result": result, "log_path": log_path}


def _append_session_dedup_log(entry: dict[str, Any]) -> str:
    """Append dedup action ledger for audit."""
    log_path = Path(__file__).resolve().parent.parent.parent / ".run" / "session-dedup-log.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(entry, ensure_ascii=False)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    return str(log_path)


def get_session_binding_response(
    *,
    session_id: str,
    session_binding_store: Any,
) -> tuple[int, dict[str, Any]]:
    """Handle GET /api/sessions/binding/:id - get single session binding."""
    binding = session_binding_store.get_binding(session_id)
    if binding:
        payload = dict(binding)
        payload["compatibility_entry"] = True
        payload["entry_role"] = "compatibility_management"
        payload["writable"] = True
        payload["primary_truth_hint"] = "/api/sessions + /api/agent-candidates"
        return 200, payload
    else:
        return 404, {"error": "not found"}


def list_session_heartbeat_task_history_route_response(
    *,
    session_id: str,
    heartbeat_task_id: str,
    limit: int,
    session_store: Any,
    store: Any,
    heartbeat_runtime: Any,
    infer_project_id_for_session: Callable[[Any, str], str],
    list_session_heartbeat_task_history_response: Callable[..., tuple[int, dict[str, Any]]],
) -> tuple[int, dict[str, Any]]:
    """Handle GET /api/sessions/:id/heartbeat-tasks/:taskId/history.

    This is a thin wrapper that delegates to the existing implementation in heartbeat_routes.
    """
    return list_session_heartbeat_task_history_response(
        session_id=session_id,
        heartbeat_task_id=heartbeat_task_id,
        limit=limit,
        session_store=session_store,
        store=store,
        heartbeat_runtime=heartbeat_runtime,
        infer_project_id_for_session=infer_project_id_for_session,
    )
