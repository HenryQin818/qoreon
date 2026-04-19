# -*- coding: utf-8 -*-

from __future__ import annotations

import copy
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Optional

from task_dashboard.runtime.agent_display_name import apply_agent_display_fields, build_agent_identity_audit


_SNAPSHOT_LOCK = threading.Lock()
_SNAPSHOT_CACHE: dict[str, dict[str, Any]] = {}
_SNAPSHOT_INVALIDATED_AT: dict[str, float] = {}
_SNAPSHOT_REFRESH_INFLIGHT: dict[str, threading.Event] = {}
_SNAPSHOT_DIAGNOSTICS: dict[str, dict[str, Any]] = {}
_SNAPSHOT_REFRESH_BUILDERS: dict[str, dict[str, Any]] = {}
_SNAPSHOT_RECENT_EVENTS_LIMIT = 20
_WINDOWED_EVENT_KINDS = {"invalidate", "invalidate_merged"}


@dataclass(frozen=True)
class SessionDirectorySnapshotConfig:
    enabled: bool
    ttl_ms: int
    prewarm_enabled: bool
    stale_ttl_ms: int = 30000
    foreground_interval_ms: int = 5000
    background_interval_ms: int = 10000
    invalidation_window_ms: int = 10000


def _coerce_env_bool(name: str, default: bool) -> bool:
    raw = str(os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _coerce_env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = str(os.environ.get(name) or "").strip()
    if not raw:
        return int(default)
    try:
        value = int(raw)
    except Exception:
        return int(default)
    return max(int(minimum), min(int(value), int(maximum)))


def session_directory_snapshot_config(project_id: str = "") -> SessionDirectorySnapshotConfig:
    pid = str(project_id or "").strip()
    runtime_role = str(os.environ.get("TASK_DASHBOARD_RUNTIME_ROLE") or "").strip().lower()
    default_enabled = bool(pid) and runtime_role == "prod"
    enabled = _coerce_env_bool("CCB_SESSIONS_DIRECTORY_SNAPSHOT_ENABLED", default_enabled)
    ttl_ms = _coerce_env_int("CCB_SESSIONS_DIRECTORY_SNAPSHOT_TTL_MS", 5000, minimum=0, maximum=60000)
    prewarm_enabled = _coerce_env_bool("CCB_SESSIONS_DIRECTORY_SNAPSHOT_PREWARM", True)
    stale_ttl_ms = _coerce_env_int(
        "CCB_SESSIONS_DIRECTORY_SNAPSHOT_STALE_TTL_MS",
        30000,
        minimum=0,
        maximum=120000,
    )
    foreground_interval_ms = _coerce_env_int(
        "CCB_SESSIONS_DIRECTORY_SNAPSHOT_FOREGROUND_INTERVAL_MS",
        max(ttl_ms, 5000),
        minimum=1000,
        maximum=60000,
    )
    background_interval_ms = _coerce_env_int(
        "CCB_SESSIONS_DIRECTORY_SNAPSHOT_BACKGROUND_INTERVAL_MS",
        max(foreground_interval_ms, 10000),
        minimum=1000,
        maximum=120000,
    )
    invalidation_window_ms = _coerce_env_int(
        "CCB_SESSIONS_DIRECTORY_SNAPSHOT_INVALIDATION_WINDOW_MS",
        max(background_interval_ms, 10000),
        minimum=1000,
        maximum=120000,
    )
    return SessionDirectorySnapshotConfig(
        enabled=bool(enabled),
        ttl_ms=int(ttl_ms),
        prewarm_enabled=bool(prewarm_enabled),
        stale_ttl_ms=int(stale_ttl_ms),
        foreground_interval_ms=int(foreground_interval_ms),
        background_interval_ms=int(background_interval_ms),
        invalidation_window_ms=int(invalidation_window_ms),
    )


def _snapshot_cache_key(*, project_id: str, environment_name: str, worktree_root: Any) -> str:
    return "|".join(
        [
            str(project_id or "").strip(),
            str(environment_name or "").strip(),
            str(worktree_root or "").strip(),
        ]
    )


def _snapshot_metadata(
    config: SessionDirectorySnapshotConfig,
    *,
    hit: bool,
    age_ms: int = 0,
    build_source: str,
    build_elapsed_ms: int = 0,
    fallback_reason: str = "",
    prewarm_state: str = "",
) -> dict[str, Any]:
    return {
        "enabled": bool(config.enabled and config.ttl_ms > 0),
        "hit": bool(hit),
        "age_ms": max(0, int(age_ms)),
        "ttl_ms": max(0, int(config.ttl_ms)),
        "stale_ttl_ms": max(0, int(getattr(config, "stale_ttl_ms", 0) or 0)),
        "build_source": str(build_source or "snapshot"),
        "build_elapsed_ms": max(0, int(build_elapsed_ms)),
        "fallback_reason": str(fallback_reason or ""),
        "prewarm_state": str(prewarm_state or ("ready" if config.prewarm_enabled else "disabled")),
    }


def _snapshot_now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _snapshot_monotonic(default: float = 0.0) -> float:
    try:
        return float(time.monotonic())
    except Exception:
        return float(default)


def _snapshot_elapsed_s(started_at: float) -> float:
    started = float(started_at or 0.0)
    return max(0.0, _snapshot_monotonic(started) - started)


def _snapshot_diag_base(
    *,
    project_id: str,
    environment_name: str,
    worktree_root: Any,
    config: SessionDirectorySnapshotConfig,
) -> dict[str, Any]:
    enabled = bool(config.enabled and config.ttl_ms > 0)
    refresh_state = "idle" if config.prewarm_enabled else "disabled"
    return {
        "_project_id": str(project_id or "").strip(),
        "_environment_name": str(environment_name or "").strip(),
        "_worktree_root": str(worktree_root or "").strip(),
        "_last_refresh_started_mono": 0.0,
        "_functional_log_mode": "structured_registry_only",
        "enabled": enabled,
        "default_query_mode": "plain_project_list_only",
        "foreground_interval_ms": max(0, int(getattr(config, "foreground_interval_ms", 0) or 0)),
        "background_interval_ms": max(0, int(getattr(config, "background_interval_ms", 0) or 0)),
        "invalidation_window_ms": max(0, int(getattr(config, "invalidation_window_ms", 0) or 0)),
        "last_build_source": "",
        "last_hit": False,
        "last_age_ms": 0,
        "ttl_ms": max(0, int(config.ttl_ms)),
        "stale_ttl_ms": max(0, int(getattr(config, "stale_ttl_ms", 0) or 0)),
        "last_build_elapsed_ms": 0,
        "last_fallback_reason": "",
        "last_delivery_mode": "",
        "last_refresh_trigger": "",
        "refresh_state": refresh_state,
        "last_invalidated_at": "",
        "last_refresh_started_at": "",
        "last_refresh_finished_at": "",
        "background_summary": {},
        "recent_events": [],
    }


def _ensure_snapshot_diag_locked(
    key: str,
    *,
    project_id: str,
    environment_name: str,
    worktree_root: Any,
    config: SessionDirectorySnapshotConfig,
) -> dict[str, Any]:
    diag = _SNAPSHOT_DIAGNOSTICS.get(key)
    if not isinstance(diag, dict):
        diag = _snapshot_diag_base(
            project_id=project_id,
            environment_name=environment_name,
            worktree_root=worktree_root,
            config=config,
        )
        _SNAPSHOT_DIAGNOSTICS[key] = diag
    diag["enabled"] = bool(config.enabled and config.ttl_ms > 0)
    diag["ttl_ms"] = max(0, int(config.ttl_ms))
    diag["stale_ttl_ms"] = max(0, int(getattr(config, "stale_ttl_ms", 0) or 0))
    diag["foreground_interval_ms"] = max(0, int(getattr(config, "foreground_interval_ms", 0) or 0))
    diag["background_interval_ms"] = max(0, int(getattr(config, "background_interval_ms", 0) or 0))
    diag["invalidation_window_ms"] = max(0, int(getattr(config, "invalidation_window_ms", 0) or 0))
    if not str(diag.get("default_query_mode") or "").strip():
        diag["default_query_mode"] = "plain_project_list_only"
    if not str(diag.get("refresh_state") or "").strip():
        diag["refresh_state"] = "idle" if config.prewarm_enabled else "disabled"
    if not str(diag.get("_functional_log_mode") or "").strip():
        diag["_functional_log_mode"] = "structured_registry_only"
    return diag


def _append_snapshot_event_locked(
    diag: dict[str, Any],
    *,
    event_kind: str,
    build_source: str = "",
    hit: Optional[bool] = None,
    age_ms: Optional[int] = None,
    build_elapsed_ms: Optional[int] = None,
    fallback_reason: str = "",
    refresh_state: str = "",
) -> None:
    event_kind_text = str(event_kind or "").strip() or "observe"
    window_ms = max(0, int(diag.get("invalidation_window_ms") or 0))
    recent = list(diag.get("recent_events") or [])
    fallback_mono = 0.0
    if recent:
        try:
            fallback_mono = float((recent[-1] or {}).get("_at_mono") or 0.0)
        except Exception:
            fallback_mono = 0.0
    if fallback_mono <= 0:
        try:
            fallback_mono = float(diag.get("_last_refresh_started_mono") or 0.0)
        except Exception:
            fallback_mono = 0.0
    now_mono = _snapshot_monotonic(fallback_mono)
    now_iso = _snapshot_now_iso()
    event = {
        "at": now_iso,
        "kind": event_kind_text,
        "build_source": str(build_source or "").strip(),
        "hit": bool(hit) if hit is not None else None,
        "age_ms": max(0, int(age_ms or 0)),
        "build_elapsed_ms": max(0, int(build_elapsed_ms or 0)),
        "fallback_reason": str(fallback_reason or "").strip(),
        "refresh_state": str(refresh_state or "").strip(),
        "_at_mono": now_mono,
    }
    if event_kind_text in _WINDOWED_EVENT_KINDS:
        event["count"] = 1
        event["window_ms"] = window_ms
        event["first_at"] = now_iso
        event["last_at"] = now_iso
    if event_kind_text in _WINDOWED_EVENT_KINDS and recent:
        for last in reversed(recent):
            last_kind = str(last.get("kind") or "").strip()
            last_mono = float(last.get("_at_mono") or 0.0)
            if last_kind not in _WINDOWED_EVENT_KINDS:
                continue
            if not (window_ms > 0 and last_mono > 0 and (now_mono - last_mono) * 1000 <= window_ms):
                break
            first_at = str(last.get("first_at") or last.get("at") or now_iso)
            last["count"] = max(1, int(last.get("count") or 1)) + 1
            last["window_ms"] = window_ms
            last["last_at"] = now_iso
            last["at"] = now_iso
            last["_at_mono"] = now_mono
            last["first_at"] = first_at
            last["build_source"] = event["build_source"]
            last["hit"] = event["hit"]
            last["age_ms"] = event["age_ms"]
            last["build_elapsed_ms"] = event["build_elapsed_ms"]
            last["fallback_reason"] = event["fallback_reason"]
            last["refresh_state"] = event["refresh_state"]
            diag["recent_events"] = recent[-_SNAPSHOT_RECENT_EVENTS_LIMIT:]
            return
    recent.append(event)
    diag["recent_events"] = recent[-_SNAPSHOT_RECENT_EVENTS_LIMIT:]


def _build_snapshot_payload_summary(payload: Any) -> dict[str, Any]:
    sessions = list((payload or {}).get("sessions") or [])
    return {
        "sessions_count": len(sessions),
        "runtime_state_count": sum(1 for row in sessions if isinstance((row or {}).get("runtime_state"), dict)),
        "conversation_list_metrics_count": sum(
            1 for row in sessions if isinstance((row or {}).get("conversation_list_metrics"), dict)
        ),
        "heartbeat_summary_count": sum(1 for row in sessions if isinstance((row or {}).get("heartbeat_summary"), dict)),
        "generated_at": _snapshot_now_iso(),
    }


def _update_snapshot_diag(
    key: str,
    *,
    project_id: str,
    environment_name: str,
    worktree_root: Any,
    config: SessionDirectorySnapshotConfig,
    build_source: str = "",
    hit: Optional[bool] = None,
    age_ms: Optional[int] = None,
    build_elapsed_ms: Optional[int] = None,
    fallback_reason: Optional[str] = None,
    refresh_state: Optional[str] = None,
    event_kind: str = "",
    invalidated_at: str = "",
    refresh_started_at: str = "",
    refresh_finished_at: str = "",
    delivery_mode: Optional[str] = None,
    refresh_trigger: Optional[str] = None,
    payload_summary: Optional[dict[str, Any]] = None,
) -> None:
    with _SNAPSHOT_LOCK:
        diag = _ensure_snapshot_diag_locked(
            key,
            project_id=project_id,
            environment_name=environment_name,
            worktree_root=worktree_root,
            config=config,
        )
        if build_source:
            diag["last_build_source"] = str(build_source)
        if hit is not None:
            diag["last_hit"] = bool(hit)
        if age_ms is not None:
            diag["last_age_ms"] = max(0, int(age_ms))
        if build_elapsed_ms is not None:
            diag["last_build_elapsed_ms"] = max(0, int(build_elapsed_ms))
        if fallback_reason is not None:
            diag["last_fallback_reason"] = str(fallback_reason or "")
        if delivery_mode is not None:
            diag["last_delivery_mode"] = str(delivery_mode or "")
        if refresh_trigger is not None:
            diag["last_refresh_trigger"] = str(refresh_trigger or "")
        if refresh_state is not None:
            diag["refresh_state"] = str(refresh_state or "")
        if invalidated_at:
            diag["last_invalidated_at"] = str(invalidated_at)
        if refresh_started_at:
            diag["last_refresh_started_at"] = str(refresh_started_at)
        if refresh_finished_at:
            diag["last_refresh_finished_at"] = str(refresh_finished_at)
        if payload_summary is not None:
            diag["background_summary"] = copy.deepcopy(payload_summary if isinstance(payload_summary, dict) else {})
        if event_kind:
            _append_snapshot_event_locked(
                diag,
                event_kind=event_kind,
                build_source=build_source or str(diag.get("last_build_source") or ""),
                hit=hit if hit is not None else bool(diag.get("last_hit")),
                age_ms=age_ms if age_ms is not None else int(diag.get("last_age_ms") or 0),
                build_elapsed_ms=(
                    build_elapsed_ms if build_elapsed_ms is not None else int(diag.get("last_build_elapsed_ms") or 0)
                ),
                fallback_reason=(
                    fallback_reason if fallback_reason is not None else str(diag.get("last_fallback_reason") or "")
                ),
                refresh_state=refresh_state if refresh_state is not None else str(diag.get("refresh_state") or ""),
            )


def session_directory_snapshot_diagnostics(
    *,
    project_id: str,
    environment_name: str,
    worktree_root: Any,
) -> dict[str, Any]:
    pid = str(project_id or "").strip()
    cfg = session_directory_snapshot_config(pid)
    key = _snapshot_cache_key(project_id=pid, environment_name=environment_name, worktree_root=worktree_root)
    with _SNAPSHOT_LOCK:
        diag = _SNAPSHOT_DIAGNOSTICS.get(key)
        if not isinstance(diag, dict):
            candidates = [
                item
                for item in _SNAPSHOT_DIAGNOSTICS.values()
                if isinstance(item, dict)
                and str(item.get("_project_id") or "").strip() == pid
                and str(item.get("_environment_name") or "").strip() == str(environment_name or "").strip()
            ]
            if candidates:
                candidates.sort(key=lambda item: str(item.get("last_refresh_finished_at") or item.get("last_invalidated_at") or ""))
                diag = candidates[-1]
        if not isinstance(diag, dict):
            diag = _snapshot_diag_base(
                project_id=pid,
                environment_name=environment_name,
                worktree_root=worktree_root,
                config=cfg,
            )
            invalidated_mono = float(_SNAPSHOT_INVALIDATED_AT.get(pid) or 0.0)
            if invalidated_mono > 0:
                diag["last_invalidated_at"] = _snapshot_now_iso()
        else:
            diag = copy.deepcopy(diag)
            diag["enabled"] = bool(cfg.enabled and cfg.ttl_ms > 0)
            diag["ttl_ms"] = max(0, int(cfg.ttl_ms))
            diag["stale_ttl_ms"] = max(0, int(getattr(cfg, "stale_ttl_ms", 0) or 0))
            diag["foreground_interval_ms"] = max(0, int(getattr(cfg, "foreground_interval_ms", 0) or 0))
            diag["background_interval_ms"] = max(0, int(getattr(cfg, "background_interval_ms", 0) or 0))
            diag["invalidation_window_ms"] = max(0, int(getattr(cfg, "invalidation_window_ms", 0) or 0))
        diag.pop("_project_id", None)
        diag.pop("_environment_name", None)
        diag.pop("_worktree_root", None)
        diag.pop("_last_refresh_started_mono", None)
        diag["functional_log_mode"] = str(diag.pop("_functional_log_mode", "structured_registry_only") or "structured_registry_only")
        recent_events = []
        for item in list(diag.get("recent_events") or [])[-_SNAPSHOT_RECENT_EVENTS_LIMIT:]:
            if not isinstance(item, dict):
                continue
            clean = {k: v for k, v in item.items() if not str(k).startswith("_")}
            recent_events.append(clean)
        diag["recent_events"] = recent_events
        return diag


def _with_snapshot_metadata(payload: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(payload if isinstance(payload, dict) else {})
    out["directory_snapshot"] = copy.deepcopy(metadata)
    return out


def invalidate_session_directory_snapshot(project_id: str = "") -> None:
    pid = str(project_id or "").strip()
    invalidated_at = _snapshot_now_iso()
    refresh_candidates: list[dict[str, Any]] = []
    with _SNAPSHOT_LOCK:
        if not pid:
            _SNAPSHOT_CACHE.clear()
            _SNAPSHOT_INVALIDATED_AT.clear()
            _SNAPSHOT_REFRESH_INFLIGHT.clear()
            _SNAPSHOT_DIAGNOSTICS.clear()
            _SNAPSHOT_REFRESH_BUILDERS.clear()
            return
        merged = any(
            str(key or "").startswith(f"{pid}|") and isinstance(event, threading.Event) and not event.is_set()
            for key, event in _SNAPSHOT_REFRESH_INFLIGHT.items()
        )
        _SNAPSHOT_INVALIDATED_AT[pid] = _snapshot_monotonic(float(_SNAPSHOT_INVALIDATED_AT.get(pid) or 0.0))
        for key, diag in list(_SNAPSHOT_DIAGNOSTICS.items()):
            if not isinstance(diag, dict):
                continue
            if str(diag.get("_project_id") or "").strip() != pid:
                continue
            diag["last_invalidated_at"] = invalidated_at
            _append_snapshot_event_locked(
                diag,
                event_kind="invalidate_merged" if merged else "invalidate",
                build_source=str(diag.get("last_build_source") or ""),
                hit=bool(diag.get("last_hit")),
                age_ms=int(diag.get("last_age_ms") or 0),
                build_elapsed_ms=int(diag.get("last_build_elapsed_ms") or 0),
                fallback_reason=str(diag.get("last_fallback_reason") or ""),
                refresh_state=str(diag.get("refresh_state") or ""),
            )
        for key, builder_entry in list(_SNAPSHOT_REFRESH_BUILDERS.items()):
            if not isinstance(builder_entry, dict):
                continue
            if str(builder_entry.get("project_id") or "").strip() != pid:
                continue
            if key not in _SNAPSHOT_CACHE:
                continue
            cfg = builder_entry.get("config")
            if not isinstance(cfg, SessionDirectorySnapshotConfig) or not cfg.prewarm_enabled:
                continue
            refresh_candidates.append(
                {
                    "key": key,
                    "project_id": pid,
                    "environment_name": str(builder_entry.get("environment_name") or ""),
                    "worktree_root": builder_entry.get("worktree_root"),
                    "config": cfg,
                    "light_builder": builder_entry.get("light_builder"),
                }
            )
    for item in refresh_candidates:
        light_builder = item.get("light_builder")
        if not callable(light_builder):
            continue
        _start_snapshot_refresh(
            str(item.get("key") or ""),
            project_id=str(item.get("project_id") or ""),
            environment_name=str(item.get("environment_name") or ""),
            worktree_root=item.get("worktree_root"),
            config=item.get("config"),
            light_builder=light_builder,
            trigger="invalidate",
        )


def _store_snapshot_cache(
    key: str,
    *,
    project_id: str,
    payload: dict[str, Any],
    build_started_at: float,
    build_elapsed_s: float,
    prewarm_state: str,
) -> None:
    checked_at = _snapshot_monotonic(float(build_started_at or 0.0))
    with _SNAPSHOT_LOCK:
        _SNAPSHOT_CACHE[key] = {
            "project_id": str(project_id or "").strip(),
            "checked_at_mono": checked_at,
            "built_at_mono": float(build_started_at or checked_at),
            "build_elapsed_s": max(0.0, float(build_elapsed_s or 0.0)),
            "prewarm_state": str(prewarm_state or "ready"),
            "payload": copy.deepcopy(payload),
        }


def _register_snapshot_refresh_builder(
    key: str,
    *,
    project_id: str,
    environment_name: str,
    worktree_root: Any,
    config: SessionDirectorySnapshotConfig,
    light_builder: Callable[[], dict[str, Any]],
) -> None:
    with _SNAPSHOT_LOCK:
        _SNAPSHOT_REFRESH_BUILDERS[key] = {
            "project_id": str(project_id or "").strip(),
            "environment_name": str(environment_name or "").strip(),
            "worktree_root": worktree_root,
            "config": config,
            "light_builder": light_builder,
        }
        _ensure_snapshot_diag_locked(
            key,
            project_id=project_id,
            environment_name=environment_name,
            worktree_root=worktree_root,
            config=config,
        )


def _start_snapshot_refresh(
    key: str,
    *,
    project_id: str,
    environment_name: str,
    worktree_root: Any,
    config: SessionDirectorySnapshotConfig,
    light_builder: Callable[[], dict[str, Any]],
    trigger: str = "stale_first",
) -> str:
    with _SNAPSHOT_LOCK:
        diag = _ensure_snapshot_diag_locked(
            key,
            project_id=project_id,
            environment_name=environment_name,
            worktree_root=worktree_root,
            config=config,
        )
        event = _SNAPSHOT_REFRESH_INFLIGHT.get(key)
        if isinstance(event, threading.Event) and not event.is_set():
            diag["refresh_state"] = "already_running"
            diag["last_refresh_trigger"] = str(trigger or "")
            _append_snapshot_event_locked(
                diag,
                event_kind="refresh_already_running",
                build_source=str(diag.get("last_build_source") or ""),
                hit=bool(diag.get("last_hit")),
                age_ms=int(diag.get("last_age_ms") or 0),
                build_elapsed_ms=int(diag.get("last_build_elapsed_ms") or 0),
                fallback_reason=str(diag.get("last_fallback_reason") or ""),
                refresh_state="already_running",
            )
            return "already_running"
        now_mono = _snapshot_monotonic(float(diag.get("_last_refresh_started_mono") or 0.0))
        last_started_mono = float(diag.get("_last_refresh_started_mono") or 0.0)
        min_interval_s = max(0.0, float(getattr(config, "background_interval_ms", 0) or 0) / 1000.0)
        if last_started_mono > 0 and min_interval_s > 0 and (now_mono - last_started_mono) < min_interval_s:
            diag["refresh_state"] = "throttled"
            diag["last_refresh_trigger"] = str(trigger or "")
            _append_snapshot_event_locked(
                diag,
                event_kind="refresh_throttled",
                build_source=str(diag.get("last_build_source") or ""),
                hit=bool(diag.get("last_hit")),
                age_ms=int(diag.get("last_age_ms") or 0),
                build_elapsed_ms=int(diag.get("last_build_elapsed_ms") or 0),
                fallback_reason=str(diag.get("last_fallback_reason") or ""),
                refresh_state="throttled",
            )
            return "throttled"
        event = threading.Event()
        _SNAPSHOT_REFRESH_INFLIGHT[key] = event
        refresh_started_at = _snapshot_now_iso()
        diag["refresh_state"] = "started"
        diag["_last_refresh_started_mono"] = now_mono
        diag["last_refresh_trigger"] = str(trigger or "")
        diag["last_refresh_started_at"] = refresh_started_at
        _append_snapshot_event_locked(
            diag,
            event_kind="refresh_started",
            build_source=str(diag.get("last_build_source") or ""),
            hit=bool(diag.get("last_hit")),
            age_ms=int(diag.get("last_age_ms") or 0),
            build_elapsed_ms=int(diag.get("last_build_elapsed_ms") or 0),
            fallback_reason=str(diag.get("last_fallback_reason") or ""),
            refresh_state="started",
        )

    def _refresh() -> None:
        build_started_at = _snapshot_monotonic()
        refresh_finished_at = ""
        refresh_state = "idle"
        try:
            payload = light_builder()
            build_elapsed_s = _snapshot_elapsed_s(build_started_at)
            if isinstance(payload, dict):
                payload_summary = _build_snapshot_payload_summary(payload)
                _store_snapshot_cache(
                    key,
                    project_id=project_id,
                    payload=payload,
                    build_started_at=build_started_at,
                    build_elapsed_s=build_elapsed_s,
                    prewarm_state="ready",
                )
                refresh_finished_at = _snapshot_now_iso()
                _update_snapshot_diag(
                    key,
                    project_id=project_id,
                    environment_name=environment_name,
                    worktree_root=worktree_root,
                    config=config,
                    build_elapsed_ms=int(build_elapsed_s * 1000),
                    refresh_state="idle",
                    refresh_finished_at=refresh_finished_at,
                    refresh_trigger=trigger,
                    payload_summary=payload_summary,
                    event_kind="refresh_finished",
                )
        except Exception:
            refresh_state = "failed"
            refresh_finished_at = _snapshot_now_iso()
            _update_snapshot_diag(
                key,
                project_id=project_id,
                environment_name=environment_name,
                worktree_root=worktree_root,
                config=config,
                refresh_state=refresh_state,
                refresh_finished_at=refresh_finished_at,
                refresh_trigger=trigger,
                fallback_reason="refresh_error",
                event_kind="refresh_failed",
            )
        finally:
            with _SNAPSHOT_LOCK:
                current = _SNAPSHOT_REFRESH_INFLIGHT.get(key)
                if current is event:
                    _SNAPSHOT_REFRESH_INFLIGHT.pop(key, None)
                if refresh_state != "failed" and refresh_finished_at:
                    diag = _ensure_snapshot_diag_locked(
                        key,
                        project_id=project_id,
                        environment_name=environment_name,
                        worktree_root=worktree_root,
                        config=config,
                    )
                    diag["refresh_state"] = "idle"
                    diag["last_refresh_finished_at"] = refresh_finished_at
            event.set()

    thread = threading.Thread(target=_refresh, name="session-directory-snapshot-refresh", daemon=True)
    thread.start()
    return "started"


def _fallback_payload(
    *,
    config: SessionDirectorySnapshotConfig,
    fallback_builder: Callable[[], dict[str, Any]],
    reason: str,
    started_at_mono: Optional[float] = None,
) -> dict[str, Any]:
    started = _snapshot_monotonic() if started_at_mono is None else float(started_at_mono)
    payload = fallback_builder()
    elapsed_ms = int(_snapshot_elapsed_s(started) * 1000)
    return _with_snapshot_metadata(
        payload,
        _snapshot_metadata(
            config,
            hit=False,
            build_source="fallback",
            build_elapsed_ms=elapsed_ms,
            fallback_reason=reason,
            prewarm_state="fallback",
        ),
    )


def build_session_directory_light_payload(
    *,
    session_store: Any,
    store: Any,
    project_id: str,
    environment_name: str,
    worktree_root: Any,
    apply_effective_primary_flags: Callable[[Any, str, list[dict[str, Any]]], list[dict[str, Any]]],
    decorate_sessions_display_fields: Callable[[list[dict[str, Any]]], list[dict[str, Any]]],
    apply_session_context_rows: Callable[..., list[dict[str, Any]]],
    apply_session_work_context: Callable[..., dict[str, Any]],
    heartbeat_runtime: Any,
    load_session_heartbeat_config: Callable[[dict[str, Any]], dict[str, Any]],
    heartbeat_summary_payload: Callable[[Any], Any],
    apply_session_heartbeat_summary_rows: Callable[..., list[dict[str, Any]]],
    apply_session_conversation_list_metrics_rows: Callable[..., list[dict[str, Any]]],
    perf_payload_builder: Callable[[str], dict[str, Any]],
    attach_runtime_state_to_sessions: Optional[Callable[[Any, list[dict[str, Any]]], list[dict[str, Any]]]] = None,
    conversation_memo_store: Any = None,
) -> dict[str, Any]:
    sessions = session_store.list_sessions(project_id, None, include_deleted=False)
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
    if callable(attach_runtime_state_to_sessions):
        sessions = attach_runtime_state_to_sessions(
            store,
            sessions,
            project_id=project_id,
            runtime_index_wait_for_inflight=False,
            runtime_index_allow_stale=True,
        )
    sessions = apply_session_conversation_list_metrics_rows(
        sessions,
        project_id=project_id,
        store=store,
        session_store=session_store,
        heartbeat_runtime=heartbeat_runtime,
        build_tracking_if_missing=True,
        conversation_memo_store=conversation_memo_store,
    )
    sessions = apply_agent_display_fields(sessions)
    payload = {"sessions": sessions}
    payload["agent_identity_audit"] = build_agent_identity_audit(sessions, project_id=project_id)
    payload.update(perf_payload_builder(project_id))
    return payload


def build_session_directory_snapshot_payload(
    *,
    project_id: str,
    channel_name: str = "",
    include_deleted: bool = False,
    environment_name: str,
    worktree_root: Any,
    light_builder: Callable[[], dict[str, Any]],
    fallback_builder: Callable[[], dict[str, Any]],
    config: Optional[SessionDirectorySnapshotConfig] = None,
    now_mono: Optional[float] = None,
) -> dict[str, Any]:
    cfg = config if isinstance(config, SessionDirectorySnapshotConfig) else session_directory_snapshot_config(project_id)
    started_at = _snapshot_monotonic() if now_mono is None else float(now_mono)
    key = _snapshot_cache_key(project_id=project_id, environment_name=environment_name, worktree_root=worktree_root)
    _register_snapshot_refresh_builder(
        key,
        project_id=project_id,
        environment_name=environment_name,
        worktree_root=worktree_root,
        config=cfg,
        light_builder=light_builder,
    )
    if not cfg.enabled:
        payload = _fallback_payload(config=cfg, fallback_builder=fallback_builder, reason="disabled", started_at_mono=started_at)
        _update_snapshot_diag(
            key,
            project_id=project_id,
            environment_name=environment_name,
            worktree_root=worktree_root,
            config=cfg,
            build_source="fallback",
            hit=False,
            age_ms=0,
            build_elapsed_ms=int(_snapshot_elapsed_s(started_at) * 1000),
            fallback_reason="disabled",
            delivery_mode="fallback_disabled",
            refresh_state="disabled",
            event_kind="fallback_disabled",
        )
        return payload
    if int(cfg.ttl_ms) <= 0:
        payload = _fallback_payload(config=cfg, fallback_builder=fallback_builder, reason="ttl_zero", started_at_mono=started_at)
        _update_snapshot_diag(
            key,
            project_id=project_id,
            environment_name=environment_name,
            worktree_root=worktree_root,
            config=cfg,
            build_source="fallback",
            hit=False,
            age_ms=0,
            build_elapsed_ms=int(_snapshot_elapsed_s(started_at) * 1000),
            fallback_reason="ttl_zero",
            delivery_mode="fallback_ttl_zero",
            refresh_state="disabled",
            event_kind="fallback_ttl_zero",
        )
        return payload
    if str(channel_name or "").strip():
        payload = _fallback_payload(
            config=cfg,
            fallback_builder=fallback_builder,
            reason="filtered_query",
            started_at_mono=started_at,
        )
        _update_snapshot_diag(
            key,
            project_id=project_id,
            environment_name=environment_name,
            worktree_root=worktree_root,
            config=cfg,
            build_source="fallback",
            hit=False,
            age_ms=0,
            build_elapsed_ms=int(_snapshot_elapsed_s(started_at) * 1000),
            fallback_reason="filtered_query",
            delivery_mode="fallback_filtered_query",
            refresh_state="idle" if cfg.prewarm_enabled else "disabled",
            event_kind="fallback_filtered_query",
        )
        return payload
    if include_deleted:
        payload = _fallback_payload(
            config=cfg,
            fallback_builder=fallback_builder,
            reason="include_deleted",
            started_at_mono=started_at,
        )
        _update_snapshot_diag(
            key,
            project_id=project_id,
            environment_name=environment_name,
            worktree_root=worktree_root,
            config=cfg,
            build_source="fallback",
            hit=False,
            age_ms=0,
            build_elapsed_ms=int(_snapshot_elapsed_s(started_at) * 1000),
            fallback_reason="include_deleted",
            delivery_mode="fallback_include_deleted",
            refresh_state="idle" if cfg.prewarm_enabled else "disabled",
            event_kind="fallback_include_deleted",
        )
        return payload

    now = _snapshot_monotonic(float(started_at)) if now_mono is None else float(now_mono)
    ttl_s = max(0.0, float(cfg.ttl_ms) / 1000.0)
    stale_ttl_s = max(ttl_s, float(getattr(cfg, "stale_ttl_ms", 0) or 0) / 1000.0)
    stale_reason = "miss"
    snapshot_hit_payload: Optional[dict[str, Any]] = None
    snapshot_hit_age_s = 0.0
    snapshot_hit_build_elapsed_s = 0.0
    snapshot_hit_prewarm_state = "ready" if cfg.prewarm_enabled else "disabled"
    stale_payload: Optional[dict[str, Any]] = None
    stale_age_s = 0.0
    stale_build_elapsed_s = 0.0
    with _SNAPSHOT_LOCK:
        cached = _SNAPSHOT_CACHE.get(key)
        invalidated_at = float(_SNAPSHOT_INVALIDATED_AT.get(str(project_id or "").strip()) or 0.0)
        if isinstance(cached, dict):
            checked_at = float(cached.get("checked_at_mono") or 0.0)
            built_at = float(cached.get("built_at_mono") or checked_at)
            age_s = max(0.0, now - checked_at)
            payload = cached.get("payload")
            if built_at < invalidated_at:
                stale_reason = "invalidated"
            elif age_s <= ttl_s:
                if isinstance(payload, dict):
                    snapshot_hit_payload = payload
                    snapshot_hit_age_s = age_s
                    snapshot_hit_build_elapsed_s = max(0.0, float(cached.get("build_elapsed_s") or 0.0))
                    snapshot_hit_prewarm_state = str(cached.get("prewarm_state") or snapshot_hit_prewarm_state)
            else:
                stale_reason = "expired"
            if isinstance(payload, dict) and stale_ttl_s > ttl_s and age_s <= stale_ttl_s:
                stale_payload = copy.deepcopy(payload)
                stale_age_s = age_s
                stale_build_elapsed_s = max(0.0, float(cached.get("build_elapsed_s") or 0.0))

    if snapshot_hit_payload is not None:
        _update_snapshot_diag(
            key,
            project_id=project_id,
            environment_name=environment_name,
            worktree_root=worktree_root,
            config=cfg,
            build_source="snapshot",
            hit=True,
            age_ms=int(snapshot_hit_age_s * 1000),
            build_elapsed_ms=int(snapshot_hit_build_elapsed_s * 1000),
            fallback_reason="",
            delivery_mode="snapshot_hit",
            payload_summary=_build_snapshot_payload_summary(snapshot_hit_payload),
            refresh_state="idle" if cfg.prewarm_enabled else "disabled",
            event_kind="serve_snapshot_hit",
        )
        return _with_snapshot_metadata(
            snapshot_hit_payload,
            _snapshot_metadata(
                cfg,
                hit=True,
                age_ms=int(snapshot_hit_age_s * 1000),
                build_source="snapshot",
                build_elapsed_ms=int(snapshot_hit_build_elapsed_s * 1000),
                prewarm_state=snapshot_hit_prewarm_state,
            ),
        )

    if stale_payload is not None and cfg.prewarm_enabled:
        prewarm_state = _start_snapshot_refresh(
            key,
            project_id=project_id,
            environment_name=environment_name,
            worktree_root=worktree_root,
            config=cfg,
            light_builder=light_builder,
            trigger="stale_first",
        )
        _update_snapshot_diag(
            key,
            project_id=project_id,
            environment_name=environment_name,
            worktree_root=worktree_root,
            config=cfg,
            build_source="stale_snapshot",
            hit=True,
            age_ms=int(stale_age_s * 1000),
            build_elapsed_ms=int(stale_build_elapsed_s * 1000),
            fallback_reason=stale_reason,
            delivery_mode="stale_snapshot",
            refresh_trigger="stale_first",
            payload_summary=_build_snapshot_payload_summary(stale_payload),
            refresh_state=prewarm_state,
            event_kind="serve_stale_snapshot",
        )
        return _with_snapshot_metadata(
            stale_payload,
            _snapshot_metadata(
                cfg,
                hit=True,
                age_ms=int(stale_age_s * 1000),
                build_source="stale_snapshot",
                build_elapsed_ms=int(stale_build_elapsed_s * 1000),
                fallback_reason=stale_reason,
                prewarm_state=prewarm_state,
            ),
        )

    build_started_at = _snapshot_monotonic(float(now))
    try:
        payload = light_builder()
    except Exception:
        payload = _fallback_payload(
            config=cfg,
            fallback_builder=fallback_builder,
            reason="build_error",
            started_at_mono=build_started_at,
        )
        _update_snapshot_diag(
            key,
            project_id=project_id,
            environment_name=environment_name,
            worktree_root=worktree_root,
            config=cfg,
            build_source="fallback",
            hit=False,
            age_ms=0,
            build_elapsed_ms=int(_snapshot_elapsed_s(build_started_at) * 1000),
            fallback_reason="build_error",
            delivery_mode="fallback_build_error",
            refresh_state="idle" if cfg.prewarm_enabled else "disabled",
            event_kind="fallback_build_error",
        )
        return payload
    build_elapsed_s = _snapshot_elapsed_s(build_started_at)
    if not isinstance(payload, dict):
        payload = _fallback_payload(
            config=cfg,
            fallback_builder=fallback_builder,
            reason="build_error",
            started_at_mono=build_started_at,
        )
        _update_snapshot_diag(
            key,
            project_id=project_id,
            environment_name=environment_name,
            worktree_root=worktree_root,
            config=cfg,
            build_source="fallback",
            hit=False,
            age_ms=0,
            build_elapsed_ms=int(build_elapsed_s * 1000),
            fallback_reason="build_error",
            delivery_mode="fallback_build_error",
            refresh_state="idle" if cfg.prewarm_enabled else "disabled",
            event_kind="fallback_build_error",
        )
        return payload
    payload_summary = _build_snapshot_payload_summary(payload)
    _store_snapshot_cache(
        key,
        project_id=project_id,
        payload=payload,
        build_started_at=build_started_at,
        build_elapsed_s=build_elapsed_s,
        prewarm_state="ready" if cfg.prewarm_enabled else "disabled",
    )
    _update_snapshot_diag(
        key,
        project_id=project_id,
        environment_name=environment_name,
        worktree_root=worktree_root,
        config=cfg,
        build_source="snapshot",
        hit=False,
        age_ms=0,
        build_elapsed_ms=int(build_elapsed_s * 1000),
        fallback_reason=stale_reason,
        delivery_mode="snapshot_rebuild",
        payload_summary=payload_summary,
        refresh_state="idle" if cfg.prewarm_enabled else "disabled",
        event_kind="build_snapshot",
    )
    return _with_snapshot_metadata(
        payload,
        _snapshot_metadata(
            cfg,
            hit=False,
            age_ms=0,
            build_source="snapshot",
            build_elapsed_ms=int(build_elapsed_s * 1000),
            fallback_reason=stale_reason,
            prewarm_state="ready" if cfg.prewarm_enabled else "disabled",
        ),
    )
