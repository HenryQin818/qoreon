# -*- coding: utf-8 -*-
"""
HeartbeatTaskRuntimeRegistry - heartbeat task monitoring and auto-start.

Extracted from server.py to reduce file size.
Uses _get_server() lazy import for cross-references to remaining server.py functions.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional

from task_dashboard.domain import normalize_task_status
from task_dashboard.helpers import (
    safe_text as _safe_text,
    now_iso as _now_iso,
    channel_id as _channel_id,
    tail_text as _tail_text,
    tail_str as _tail_str,
    extract_last_json_object_text as _extract_last_json_object_text,
    read_json_file_safe as _read_json_file_safe,
    parse_iso_ts as _parse_iso_ts,
    iso_after_s as _iso_after_s,
    looks_like_uuid as _looks_like_uuid,
    atomic_write_text as _atomic_write_text,
    read_json_file as _read_json_file,
    write_json_file as _write_json_file,
    coerce_bool as _coerce_bool,
    coerce_int as _coerce_int,
)
from task_dashboard.parser_md import extract_field, parse_leading_tags
from task_dashboard.task_identity import (
    extract_task_identity_from_file as _extract_task_identity_from_file,
    normalize_task_path as _identity_normalize_task_path,
    record_task_move as _record_task_move,
)
from task_dashboard.runtime.channel_admin import (
    create_channel as runtime_create_channel,
    resolve_task_root_path as runtime_resolve_task_root_path,
)
from task_dashboard.runtime.agent_display_name import attach_agent_display_fields
from task_dashboard.runtime.run_state_semantics import build_session_semantics, classify_run_semantics
from task_dashboard.runtime.session_display_state import (
    build_latest_run_summary as _session_display_build_latest_run_summary,
    build_session_display_fields as _session_display_build_fields,
)
from task_dashboard.utils import safe_read_text


__all__ = [
    "HeartbeatTaskRuntimeRegistry",
    "_CODEX_HISTORY_TITLE_CACHE",
    "_CODEX_HISTORY_TITLE_CACHE_LOCK",
    "_attach_runtime_state_to_sessions",
    "_auto_kickoff_global_enabled",
    "_auto_kickoff_project_enabled",
    "_build_project_session_runtime_index",
    "_build_run_observability_fields",
    "_build_session_runtime_state_for_row",
    "_build_task_auto_kickoff_message",
    "_change_task_status",
    "_channel_auto_kickoff_enabled",
    "_create_channel",
    "_decorate_session_display_fields",
    "_decorate_sessions_display_fields",
    "_dispatch_task_status_auto_start",
    "_evaluate_task_status_gate",
    "_extract_bootstrap_result_path_from_stdout",
    "_extract_task_title",
    "_infer_blocked_by_run_id",
    "_infer_project_id_for_session",
    "_load_archived_session_summary",
    "_load_codex_history_title_index",
    "_normalize_bootstrap_v1_success_payload",
    "_normalize_history_title_text",
    "_normalize_task_path_identity",
    "_probe_external_session_busy_batch_cached",
    "_probe_external_session_busy_cached",
    "_resolve_auto_kickoff_target_session",
    "_resolve_task_project_channel",
    "_run_codex_channel_bootstrap_v1",
    "_run_created_ts",
    "_run_status_display_state",
    "_scan_task_auto_kickoff_history",
    "_invalidate_project_session_runtime_index_cache",
    "_session_archive_summary_cache_ttl_s",
    "_session_external_busy_probe_ttl_s",
    "_session_runtime_index_cache_ttl_s",
    "_session_runtime_internal_state",
    "_session_runtime_scan_limit",
]


def __getattr__(name):
    """Lazy resolution of names still defined in server.py (avoids circular imports)."""
    import server
    try:
        return getattr(server, name)
    except AttributeError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


from task_dashboard.runtime.scheduler_helpers import *  # noqa: F401,F403


def _normalize_cli_type_id(value: Any) -> str:
    return __getattr__("_normalize_cli_type_id")(value)


def _normalize_reasoning_effort(value: Any) -> str:
    return __getattr__("_normalize_reasoning_effort")(value)


def _codex_home() -> Path:
    return __getattr__("_codex_home")()


def _scan_process_table_rows() -> list[tuple[int, str]]:
    return __getattr__("_scan_process_table_rows")()


def _scan_session_busy_rows(*args, **kwargs):
    return __getattr__("_scan_session_busy_rows")(*args, **kwargs)


def _scan_session_busy_rows_effective(*args, **kwargs):
    try:
        impl = __getattr__("_scan_session_busy_rows_effective")
    except AttributeError:
        impl = None
    if callable(impl):
        return impl(*args, **kwargs)

    # 回滚到旧版 server.py 时，可能不存在 *_effective 变体。
    # 这里退回基础 busy scan，优先保证 /api/sessions 可用，
    # 不让 heartbeat_registry 因兼容缺口直接打崩目录接口。
    if args:
        _store = args[0]
        sid = args[1] if len(args) > 1 else ""
        cli_type = args[2] if len(args) > 2 else kwargs.get("cli_type", "codex")
        rows = args[3] if len(args) > 3 else kwargs.get("rows")
    else:
        sid = kwargs.get("session_id", "")
        cli_type = kwargs.get("cli_type", "codex")
        rows = kwargs.get("rows")
    return _scan_session_busy_rows(sid, cli_type=cli_type, rows=rows)


def _session_process_busy(session_id: str, cli_type: str = "codex") -> bool:
    return bool(__getattr__("_session_process_busy")(session_id, cli_type=cli_type))


def _project_channel_cli_type(project_id: str, channel_name: str) -> str:
    return __getattr__("_project_channel_cli_type")(project_id, channel_name)


def _find_project_cfg(project_id: str):
    return __getattr__("_find_project_cfg")(project_id)


def _clear_dashboard_cfg_cache() -> None:
    return __getattr__("_clear_dashboard_cfg_cache")()


def _load_dashboard_cfg_current(*args, **kwargs):
    return __getattr__("_load_dashboard_cfg_current")(*args, **kwargs)


def _repo_root() -> Path:
    return __getattr__("_repo_root")()


def _config_toml_path() -> Path:
    return __getattr__("_config_toml_path")()


def _parse_rfc3339_ts(value: Any):
    return __getattr__("_parse_rfc3339_ts")(value)


def _session_runtime_index_cache_lock():
    return __getattr__("_SESSION_RUNTIME_INDEX_CACHE_LOCK")


def _session_runtime_index_cache():
    return __getattr__("_SESSION_RUNTIME_INDEX_CACHE")


def _session_runtime_index_inflight():
    return __getattr__("_SESSION_RUNTIME_INDEX_INFLIGHT")


def _session_runtime_index_invalidated_at():
    return __getattr__("_SESSION_RUNTIME_INDEX_INVALIDATED_AT")


def _session_external_busy_cache_lock():
    return __getattr__("_SESSION_EXTERNAL_BUSY_CACHE_LOCK")


def _session_external_busy_cache():
    return __getattr__("_SESSION_EXTERNAL_BUSY_CACHE")


def _session_archive_summary_cache_lock():
    return __getattr__("_SESSION_ARCHIVE_SESSION_SUMMARY_CACHE_LOCK")


def _session_archive_summary_cache():
    return __getattr__("_SESSION_ARCHIVE_SESSION_SUMMARY_CACHE")


def _task_push_active_state(store: "RunStore", project_id: str, session_id: str) -> dict[str, Any]:
    return __getattr__("_task_push_active_state")(store, project_id, session_id)


def _load_codex_history_title_index_for_display() -> dict[str, str]:
    try:
        import server

        patched = getattr(server, "_load_codex_history_title_index")
    except Exception:
        patched = None
    if callable(patched) and patched is not _load_codex_history_title_index:
        try:
            result = patched()
            if isinstance(result, dict):
                return result
        except Exception:
            pass
    return _load_codex_history_title_index()


class HeartbeatTaskRuntimeRegistry:
    """
    Configurable periodic agent jobs ("heartbeat tasks"):
    - project-level task config from [projects.heartbeat]
    - interval / daily schedule
    - run-now / history / runtime status
    """

    def __init__(
        self,
        *,
        store: "RunStore",
        session_store: SessionStore,
        task_push_runtime: TaskPushRuntimeRegistry,
    ) -> None:
        self.store = store
        self.session_store = session_store
        self.task_push_runtime = task_push_runtime
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        tick_raw = _coerce_int(os.environ.get("CCB_HEARTBEAT_TICK_SECONDS"), 30)
        self._tick_seconds = max(20, min(300, int(tick_raw or 30)))

    def _runtime_key(self, task: dict[str, Any], *, heartbeat_task_id: str = "", session_id: str = "") -> str:
        tid = str(heartbeat_task_id or task.get("heartbeat_task_id") or "").strip()
        sid = str(session_id or task.get("session_id") or "").strip()
        return _heartbeat_task_runtime_key(tid, sid if str(task.get("source_scope") or "") == "session" or sid else "")

    def _iter_session_tasks(self, project_id: str) -> list[dict[str, Any]]:
        pid = str(project_id or "").strip()
        out: list[dict[str, Any]] = []
        for session in self.session_store.list_sessions(pid):
            if not isinstance(session, dict):
                continue
            heartbeat_cfg = _load_session_heartbeat_config(session)
            for row in heartbeat_cfg.get("tasks") or []:
                if not isinstance(row, dict):
                    continue
                item = dict(row)
                item["source_scope"] = "session"
                item["source_session_id"] = str(session.get("id") or "")
                item["source_channel_name"] = str(session.get("channel_name") or "")
                out.append(item)
        return out

    def _iter_project_tasks(self, project_id: str) -> list[dict[str, Any]]:
        pid = str(project_id or "").strip()
        out: list[dict[str, Any]] = []
        cfg = _load_project_heartbeat_config(pid)
        for row in _normalize_heartbeat_tasks(cfg.get("tasks")):
            if not isinstance(row, dict):
                continue
            item = dict(row)
            item["source_scope"] = "project"
            out.append(item)
        return out

    def _iter_session_assigned_tasks(self, project_id: str, session_id: str) -> list[dict[str, Any]]:
        pid = str(project_id or "").strip()
        sid = str(session_id or "").strip()
        ordered_ids: list[str] = []
        merged: dict[str, dict[str, Any]] = {}
        for row in self._iter_project_tasks(pid):
            if str(row.get("session_id") or "").strip() != sid:
                continue
            tid = str(row.get("heartbeat_task_id") or "").strip()
            if not tid:
                continue
            if tid not in merged:
                ordered_ids.append(tid)
            merged[tid] = dict(row)
        for row in self._iter_session_tasks(pid):
            if str(row.get("session_id") or "").strip() != sid:
                continue
            tid = str(row.get("heartbeat_task_id") or "").strip()
            if not tid:
                continue
            if tid not in merged:
                ordered_ids.append(tid)
            merged[tid] = dict(row)
        return [merged[tid] for tid in ordered_ids if tid in merged]

    def start(self) -> None:
        with self._lock:
            if isinstance(self._thread, threading.Thread) and self._thread.is_alive():
                return
            self._stop_event = threading.Event()
            thread = threading.Thread(target=self._loop, daemon=True, name="heartbeat-task-executor")
            self._thread = thread
            thread.start()

    def shutdown(self) -> None:
        self._stop_event.set()
        with self._lock:
            thread = self._thread
            self._thread = None
        if isinstance(thread, threading.Thread):
            try:
                thread.join(timeout=0.2)
            except Exception:
                pass

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.tick_once()
            except Exception:
                pass
            if self._stop_event.wait(self._tick_seconds):
                break

    def _task_runtime_locked(self, project_id: str, heartbeat_task_id: str, session_id: str = "") -> dict[str, Any]:
        raw = _read_json_file(
            _heartbeat_task_runtime_path(
                self.store,
                project_id,
                _heartbeat_task_runtime_key(heartbeat_task_id, session_id),
            )
        )
        return raw if isinstance(raw, dict) else {}

    def _save_task_runtime_locked(
        self,
        project_id: str,
        heartbeat_task_id: str,
        payload: dict[str, Any],
        session_id: str = "",
    ) -> dict[str, Any]:
        pid = str(project_id or "").strip()
        tid = str(heartbeat_task_id or "").strip()
        sid = str(session_id or "").strip()
        current = self._task_runtime_locked(pid, tid, sid)
        current.update({k: v for k, v in (payload or {}).items() if k})
        current["project_id"] = pid
        current["heartbeat_task_id"] = tid
        if sid:
            current["session_id"] = sid
        current["updated_at"] = _now_iso()
        _write_json_file(
            _heartbeat_task_runtime_path(
                self.store,
                pid,
                _heartbeat_task_runtime_key(tid, sid),
            ),
            current,
        )
        return current

    def _append_history_locked(
        self,
        project_id: str,
        heartbeat_task_id: str,
        record: dict[str, Any],
        session_id: str = "",
    ) -> list[dict[str, Any]]:
        current = self._task_runtime_locked(project_id, heartbeat_task_id, session_id)
        history = current.get("history")
        rows = [dict(x) for x in history if isinstance(x, dict)] if isinstance(history, list) else []
        rows.insert(0, dict(record))
        rows = rows[:_HEARTBEAT_TASK_HISTORY_LIMIT]
        current["history"] = rows
        self._save_task_runtime_locked(project_id, heartbeat_task_id, current, session_id)
        return rows

    def _build_context_summary(self, project_id: str, task: dict[str, Any]) -> dict[str, Any]:
        scope = _normalize_heartbeat_context_scope(task.get("context_scope"))
        task_items = _list_project_task_items(project_id, use_cache=True)
        task_counts: dict[str, int] = {}
        for row in task_items:
            if not isinstance(row, dict):
                continue
            bucket = str(row.get("status_bucket") or "").strip()
            if not bucket:
                continue
            task_counts[bucket] = int(task_counts.get(bucket) or 0) + 1
        recent_tasks: list[dict[str, Any]] = []
        if bool(scope.get("include_recent_tasks")) and int(scope.get("recent_tasks_limit") or 0) > 0:
            for row in task_items[: int(scope.get("recent_tasks_limit") or 0)]:
                if not isinstance(row, dict):
                    continue
                recent_tasks.append(
                    {
                        "task_path": str(row.get("task_path") or ""),
                        "title": str(row.get("title") or ""),
                        "status": str(row.get("status") or ""),
                        "channel_name": str(row.get("channel_name") or ""),
                    }
                )
        recent_runs: list[dict[str, Any]] = []
        if bool(scope.get("include_recent_runs")) and int(scope.get("recent_runs_limit") or 0) > 0:
            for row in self.store.list_runs(project_id=project_id, limit=int(scope.get("recent_runs_limit") or 0), include_payload=False):
                if not isinstance(row, dict):
                    continue
                recent_runs.append(
                    {
                        "run_id": str(row.get("id") or ""),
                        "channel_name": str(row.get("channelId") or row.get("channel_name") or ""),
                        "status": str(row.get("status") or ""),
                        "created_at": str(row.get("createdAt") or ""),
                    }
                )
        return {
            "task_counts": task_counts if bool(scope.get("include_task_counts")) else {},
            "recent_tasks": recent_tasks,
            "recent_runs": recent_runs,
        }

    def _build_dispatch_message(self, project_id: str, task: dict[str, Any], *, trigger: str) -> str:
        effective_prompt = str(task.get("effective_prompt_template") or task.get("prompt_template") or "").strip()
        return effective_prompt

    def _next_due_at(self, task: dict[str, Any], *, now_ts: Optional[float] = None) -> str:
        base_ts = float(now_ts if now_ts is not None else time.time())
        schedule_type = str(task.get("schedule_type") or "interval").strip().lower()
        if schedule_type == "daily":
            daily_time = str(task.get("daily_time") or "09:00").strip() or "09:00"
            hour = 9
            minute = 0
            try:
                hour, minute = [int(x) for x in daily_time.split(":", 1)]
            except Exception:
                hour, minute = 9, 0
            weekdays = _normalize_heartbeat_weekdays(task.get("weekdays"))
            for offset in range(0, 8):
                probe_ts = base_ts + (offset * 86400)
                local = time.localtime(probe_ts)
                weekday = int(local.tm_wday) + 1
                if weekday not in weekdays:
                    continue
                candidate_ts = time.mktime(
                    (
                        local.tm_year,
                        local.tm_mon,
                        local.tm_mday,
                        hour,
                        minute,
                        0,
                        local.tm_wday,
                        local.tm_yday,
                        local.tm_isdst,
                    )
                )
                if candidate_ts > base_ts + 1:
                    return time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(candidate_ts))
            return _iso_after_s(24 * 3600)
        interval_minutes = max(5, int(task.get("interval_minutes") or 60))
        return _iso_after_s(interval_minutes * 60)

    def _task_runtime_session_id(self, task: dict[str, Any]) -> str:
        source_scope = str(task.get("source_scope") or "project").strip().lower()
        return str(task.get("session_id") or "").strip() if source_scope == "session" else ""

    def _history_record_for_job(self, runtime: dict[str, Any], job_id: str) -> dict[str, Any]:
        jid = str(job_id or "").strip()
        if not jid:
            return {}
        rows = runtime.get("history")
        if not isinstance(rows, list):
            return {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            if str(row.get("job_id") or "").strip() == jid:
                return dict(row)
        return {}

    def _disable_task_after_limit(self, project_id: str, task: dict[str, Any]) -> bool:
        pid = str(project_id or "").strip()
        tid = str(task.get("heartbeat_task_id") or "").strip()
        if not (pid and tid):
            return False
        source_scope = str(task.get("source_scope") or "project").strip().lower()
        if source_scope == "session":
            sid = str(task.get("session_id") or "").strip()
            if not sid:
                return False
            session = self.session_store.get_session(sid) or {}
            if not isinstance(session, dict) or not session:
                return False
            heartbeat_cfg = _load_session_heartbeat_config(session)
            current_tasks = _heartbeat_tasks_for_write(heartbeat_cfg.get("tasks"))
            changed = False
            for row in current_tasks:
                if str(row.get("heartbeat_task_id") or "").strip() != tid:
                    continue
                if not bool(row.get("enabled")):
                    return False
                row["enabled"] = False
                changed = True
                break
            if not changed:
                return False
            enabled_any = any(bool(row.get("enabled")) for row in current_tasks)
            heartbeat_payload = _heartbeat_session_payload_for_write(
                session,
                enabled=enabled_any,
                tasks=current_tasks,
            )
            return bool(self.session_store.update_session(sid, heartbeat=heartbeat_payload))

        cfg = _load_project_heartbeat_config(pid)
        current_tasks = _heartbeat_tasks_for_write(cfg.get("tasks"))
        changed = False
        for row in current_tasks:
            if str(row.get("heartbeat_task_id") or "").strip() != tid:
                continue
            if not bool(row.get("enabled")):
                return False
            row["enabled"] = False
            changed = True
            break
        if not changed:
            return False
        _set_project_scheduler_contract_in_config(
            pid,
            heartbeat_patch=_build_heartbeat_patch_with_tasks(cfg=cfg, tasks=current_tasks),
        )
        return True

    def _refresh_runtime_execution_fields(
        self,
        project_id: str,
        task: dict[str, Any],
        runtime: dict[str, Any],
    ) -> dict[str, Any]:
        pid = str(project_id or "").strip()
        tid = str(task.get("heartbeat_task_id") or "").strip()
        sid = self._task_runtime_session_id(task)
        current = dict(runtime if isinstance(runtime, dict) else {})
        if not tid:
            return current

        patch: dict[str, Any] = {}
        job_id = str(current.get("last_job_id") or "").strip()
        if job_id:
            job = self.task_push_runtime.get_status(pid, job_id)
            if isinstance(job, dict):
                status_obj = job.get("status") if isinstance(job.get("status"), dict) else {}
                attempts = job.get("attempts") if isinstance(job.get("attempts"), list) else []
                last_attempt = attempts[-1] if attempts and isinstance(attempts[-1], dict) else {}
                latest_status = str(status_obj.get("status") or current.get("last_job_status") or "").strip()
                latest_run_id = str(status_obj.get("last_run_id") or current.get("last_run_id") or "").strip()
                latest_error = str(status_obj.get("last_error") or current.get("last_error") or "").strip()
                latest_result = str(status_obj.get("last_result") or current.get("last_result") or "").strip()
                latest_busy = str(last_attempt.get("active_status") or current.get("last_busy_status") or "").strip()
                pending_job = latest_status in {"created", "scheduled", "retry_waiting"}
                if latest_status != str(current.get("last_job_status") or ""):
                    patch["last_job_status"] = latest_status
                if latest_run_id != str(current.get("last_run_id") or ""):
                    patch["last_run_id"] = latest_run_id
                if latest_error != str(current.get("last_error") or ""):
                    patch["last_error"] = latest_error
                if latest_result != str(current.get("last_result") or ""):
                    patch["last_result"] = latest_result
                if latest_busy != str(current.get("last_busy_status") or ""):
                    patch["last_busy_status"] = latest_busy
                if pending_job != bool(current.get("pending_job")):
                    patch["pending_job"] = pending_job

        effective = dict(current)
        effective.update(patch)
        max_execute_count = max(0, int(task.get("max_execute_count") or 0))
        executed_count = max(0, int(effective.get("executed_count") or 0))
        last_counted_job_id = str(effective.get("last_counted_job_id") or "").strip()
        last_trigger = str(effective.get("last_trigger") or "").strip().lower()
        job_status = str(effective.get("last_job_status") or "").strip().lower()
        if job_id and job_id != last_counted_job_id and last_trigger != "manual" and job_status == "dispatched":
            record = self._history_record_for_job(effective, job_id)
            record_trigger = str(record.get("trigger") or last_trigger).strip().lower()
            record_result = str(record.get("result") or effective.get("last_result") or "").strip().lower()
            if record_trigger != "manual" and record_result == "dispatched":
                executed_count += 1
                patch["executed_count"] = executed_count
                patch["last_counted_job_id"] = job_id
                effective["executed_count"] = executed_count
                effective["last_counted_job_id"] = job_id

        if max_execute_count > 0:
            remaining = max(0, max_execute_count - executed_count)
            if remaining != int(effective.get("remaining_execute_count") or 0):
                patch["remaining_execute_count"] = remaining
            if remaining <= 0:
                if str(effective.get("auto_disabled_reason") or "").strip() != "max_execute_count_reached":
                    patch["auto_disabled_reason"] = "max_execute_count_reached"
                    patch["auto_disabled_at"] = _now_iso()
                    effective["auto_disabled_reason"] = "max_execute_count_reached"
                    effective["auto_disabled_at"] = str(patch["auto_disabled_at"])
                if bool(task.get("enabled")) and self._disable_task_after_limit(pid, task):
                    patch["next_due_at"] = ""
                    patch["pending_job"] = False
            else:
                if str(effective.get("auto_disabled_reason") or "").strip():
                    patch["auto_disabled_reason"] = ""
                if str(effective.get("auto_disabled_at") or "").strip():
                    patch["auto_disabled_at"] = ""
        else:
            if effective.get("remaining_execute_count") is not None:
                patch["remaining_execute_count"] = None
            if str(effective.get("auto_disabled_reason") or "").strip():
                patch["auto_disabled_reason"] = ""
            if str(effective.get("auto_disabled_at") or "").strip():
                patch["auto_disabled_at"] = ""

        if patch:
            current = self._save_task_runtime_locked(pid, tid, patch, sid)
        return current

    def _merge_task(self, project_id: str, task: dict[str, Any]) -> dict[str, Any]:
        tid = str(task.get("heartbeat_task_id") or "").strip()
        source_scope = str(task.get("source_scope") or "project").strip().lower()
        sid = str(task.get("session_id") or "").strip() if source_scope == "session" else ""
        runtime = self._task_runtime_locked(project_id, tid, sid) if tid else {}
        out = dict(task)
        if tid:
            runtime = self._refresh_runtime_execution_fields(project_id, task, runtime)
        out.update(
            {
                "enabled": False
                if str(runtime.get("auto_disabled_reason") or "").strip() == "max_execute_count_reached"
                else bool(task.get("enabled")),
                "max_execute_count": max(0, int(task.get("max_execute_count") or 0)),
                "executed_count": max(0, int(runtime.get("executed_count") or 0)),
                "remaining_execute_count": runtime.get("remaining_execute_count"),
                "last_counted_job_id": str(runtime.get("last_counted_job_id") or ""),
                "auto_disabled_reason": str(runtime.get("auto_disabled_reason") or ""),
                "auto_disabled_at": str(runtime.get("auto_disabled_at") or ""),
                "next_due_at": str(runtime.get("next_due_at") or ""),
                "last_triggered_at": str(runtime.get("last_triggered_at") or ""),
                "last_trigger": str(runtime.get("last_trigger") or ""),
                "last_status": str(runtime.get("last_status") or ""),
                "last_result": str(runtime.get("last_result") or ""),
                "last_error": str(runtime.get("last_error") or ""),
                "last_job_id": str(runtime.get("last_job_id") or ""),
                "last_job_status": str(runtime.get("last_job_status") or ""),
                "last_run_id": str(runtime.get("last_run_id") or ""),
                "last_busy_status": str(runtime.get("last_busy_status") or ""),
                "pending_job": bool(runtime.get("pending_job")),
                "history_count": len(runtime.get("history") or []) if isinstance(runtime.get("history"), list) else 0,
                "updated_at": str(runtime.get("updated_at") or ""),
            }
        )
        out["source_scope"] = "session" if source_scope == "session" and sid else "project"
        return out

    def list_tasks(self, project_id: str) -> dict[str, Any]:
        cfg = _load_project_heartbeat_config(project_id)
        items = [
            self._merge_task(project_id, row)
            for row in _normalize_heartbeat_tasks(cfg.get("tasks"))
        ]
        return {
            "project_id": str(project_id or "").strip(),
            "enabled": bool(cfg.get("enabled")),
            "scan_interval_seconds": int(cfg.get("scan_interval_seconds") or 30),
            "items": items,
            "count": len(items),
            "errors": list(cfg.get("errors") or []),
            "ready": bool(cfg.get("ready")),
        }

    def list_session_tasks(self, project_id: str, session_id: str) -> dict[str, Any]:
        pid = str(project_id or "").strip()
        sid = str(session_id or "").strip()
        items = [self._merge_task(pid, row) for row in self._iter_session_assigned_tasks(pid, sid)]
        session = self.session_store.get_session(sid) or {}
        cfg = _load_session_heartbeat_config(session if isinstance(session, dict) else {})
        enabled_count = sum(1 for row in items if bool(row.get("enabled")))
        ready_count = sum(1 for row in items if bool(row.get("enabled")) and bool(row.get("ready")))
        session_count = sum(1 for row in items if str(row.get("source_scope") or "") == "session")
        project_assigned_count = sum(1 for row in items if str(row.get("source_scope") or "") == "project")
        return {
            "project_id": pid,
            "session_id": sid,
            "enabled": enabled_count > 0,
            "items": items,
            "count": len(items),
            "enabled_count": enabled_count,
            "summary": {
                "total_count": len(items),
                "enabled_count": enabled_count,
                "ready_count": ready_count,
                "has_enabled_tasks": enabled_count > 0,
                "session_count": session_count,
                "project_assigned_count": project_assigned_count,
            },
            "errors": list(cfg.get("errors") or []),
            "ready": ready_count > 0 if items else bool(cfg.get("ready")),
            "session_count": session_count,
            "project_assigned_count": project_assigned_count,
        }

    def get_task(self, project_id: str, heartbeat_task_id: str) -> Optional[dict[str, Any]]:
        tid = _normalize_heartbeat_task_id(heartbeat_task_id)
        if not tid:
            return None
        cfg = _load_project_heartbeat_config(project_id)
        for row in _normalize_heartbeat_tasks(cfg.get("tasks")):
            if str(row.get("heartbeat_task_id") or "").strip() == tid:
                return self._merge_task(project_id, row)
        return None

    def list_history(self, project_id: str, heartbeat_task_id: str, limit: int = 20) -> list[dict[str, Any]]:
        runtime = self._task_runtime_locked(project_id, heartbeat_task_id)
        rows = runtime.get("history")
        items = [dict(x) for x in rows if isinstance(x, dict)] if isinstance(rows, list) else []
        return items[: max(1, min(int(limit or 20), _HEARTBEAT_TASK_HISTORY_LIMIT))]

    def list_session_history(self, project_id: str, session_id: str, heartbeat_task_id: str, limit: int = 20) -> list[dict[str, Any]]:
        task = self.get_session_task(project_id, session_id, heartbeat_task_id) or {}
        runtime_session_id = session_id if str(task.get("source_scope") or "") == "session" else ""
        runtime = self._task_runtime_locked(project_id, heartbeat_task_id, runtime_session_id)
        rows = runtime.get("history")
        items = [dict(x) for x in rows if isinstance(x, dict)] if isinstance(rows, list) else []
        return items[: max(1, min(int(limit or 20), _HEARTBEAT_TASK_HISTORY_LIMIT))]

    def get_session_task(self, project_id: str, session_id: str, heartbeat_task_id: str) -> Optional[dict[str, Any]]:
        pid = str(project_id or "").strip()
        sid = str(session_id or "").strip()
        tid = _normalize_heartbeat_task_id(heartbeat_task_id)
        if not (pid and sid and tid):
            return None
        for row in self._iter_session_assigned_tasks(pid, sid):
            if str(row.get("heartbeat_task_id") or "").strip() == tid:
                return self._merge_task(pid, row)
        return None

    def sync_project(self, project_id: str) -> dict[str, Any]:
        pid = str(project_id or "").strip()
        cfg = _load_project_heartbeat_config(pid)
        tasks = _normalize_heartbeat_tasks(cfg.get("tasks"))
        for row in tasks:
            tid = str(row.get("heartbeat_task_id") or "").strip()
            if not tid:
                continue
            runtime = self._task_runtime_locked(pid, tid)
            if not bool(cfg.get("enabled")) or not bool(row.get("enabled")):
                self._save_task_runtime_locked(
                    pid,
                    tid,
                    {
                        "next_due_at": "",
                        "last_status": "disabled",
                        "pending_job": False,
                    },
                )
                continue
            if not str(runtime.get("next_due_at") or "").strip():
                self._save_task_runtime_locked(
                    pid,
                    tid,
                    {
                        "next_due_at": self._next_due_at(row),
                        "last_status": "idle" if bool(row.get("ready")) else "invalid_config",
                        "pending_job": False,
                    },
                )
        for row in self._iter_session_tasks(pid):
            tid = str(row.get("heartbeat_task_id") or "").strip()
            sid = str(row.get("session_id") or "").strip()
            if not (tid and sid):
                continue
            runtime = self._task_runtime_locked(pid, tid, sid)
            if not bool(row.get("enabled")):
                self._save_task_runtime_locked(
                    pid,
                    tid,
                    {"next_due_at": "", "last_status": "disabled", "pending_job": False},
                    sid,
                )
                continue
            if not str(runtime.get("next_due_at") or "").strip():
                self._save_task_runtime_locked(
                    pid,
                    tid,
                    {
                        "next_due_at": self._next_due_at(row),
                        "last_status": "idle" if bool(row.get("ready")) else "invalid_config",
                        "pending_job": False,
                    },
                    sid,
                )
        return self.list_tasks(pid)

    def _dispatch_task(
        self,
        project_id: str,
        task: dict[str, Any],
        *,
        trigger: str,
        respect_busy_policy: bool,
    ) -> dict[str, Any]:
        pid = str(project_id or "").strip()
        tid = str(task.get("heartbeat_task_id") or "").strip()
        now = _now_iso()
        message = self._build_dispatch_message(pid, task, trigger=trigger)
        busy_policy = str(task.get("busy_policy") or "run_on_next_idle")
        target_session_id = str(task.get("session_id") or "").strip()
        runtime_session_id = target_session_id if str(task.get("source_scope") or "") == "session" else ""
        active = _task_push_active_state(self.store, pid, target_session_id)

        if respect_busy_policy and bool(active.get("active")) and busy_policy == "skip_if_busy":
            record = {
                "record_id": f"{int(time.time() * 1000)}-{secrets.token_hex(3)}",
                "triggered_at": now,
                "trigger": trigger,
                "status": "skipped_active",
                "job_id": "",
                "run_id": "",
                "error": "",
                "active_status": str(active.get("status") or ""),
                "active_run_id": str(active.get("run_id") or ""),
            }
            self._append_history_locked(pid, tid, record, runtime_session_id)
            self._save_task_runtime_locked(
                pid,
                tid,
                {
                    "last_triggered_at": now,
                    "last_trigger": trigger,
                    "last_status": "skipped_active",
                    "last_result": "skipped_active",
                    "last_busy_status": str(active.get("status") or ""),
                    "last_error": "",
                    "pending_job": False,
                    "next_due_at": self._next_due_at(task),
                },
                runtime_session_id,
            )
            return record

        if respect_busy_policy and bool(active.get("active")) and busy_policy == "run_on_next_idle":
            record = {
                "record_id": f"{int(time.time() * 1000)}-{secrets.token_hex(3)}",
                "triggered_at": now,
                "trigger": trigger,
                "status": "waiting_idle",
                "job_id": "",
                "run_id": "",
                "error": "",
                "active_status": str(active.get("status") or ""),
                "active_run_id": str(active.get("run_id") or ""),
            }
            self._append_history_locked(pid, tid, record, runtime_session_id)
            self._save_task_runtime_locked(
                pid,
                tid,
                {
                    "last_triggered_at": now,
                    "last_trigger": trigger,
                    "last_status": "waiting_idle",
                    "last_result": "waiting_idle",
                    "last_busy_status": str(active.get("status") or ""),
                    "last_error": "",
                    "pending_job": False,
                    "next_due_at": _iso_after_s(self._tick_seconds),
                },
                runtime_session_id,
            )
            return record

        extra_meta = {
            "trigger_type": "heartbeat_task",
            "heartbeat_task_id": tid,
            "heartbeat_trigger": trigger,
            "heartbeat_preset_key": str(task.get("preset_key") or ""),
            "topic": tid,
        }
        if respect_busy_policy and bool(active.get("active")) and busy_policy == "queue_if_busy":
            item = self.task_push_runtime.schedule_send(
                project_id=pid,
                channel_name=str(task.get("channel_name") or ""),
                session_id=target_session_id,
                message=message,
                scheduled_at=now,
                retry_interval_seconds=60,
                max_attempts=2,
                profile_label="heartbeat_task",
                run_extra_meta=extra_meta,
            )
        else:
            item = self.task_push_runtime.send_now(
                project_id=pid,
                channel_name=str(task.get("channel_name") or ""),
                session_id=target_session_id,
                message=message,
                profile_label="heartbeat_task",
                run_extra_meta=extra_meta,
            )
        status_obj = item.get("status") if isinstance(item.get("status"), dict) else {}
        attempts = item.get("attempts") if isinstance(item.get("attempts"), list) else []
        last_attempt = attempts[-1] if attempts and isinstance(attempts[-1], dict) else {}
        record = {
            "record_id": f"{int(time.time() * 1000)}-{secrets.token_hex(3)}",
            "triggered_at": now,
            "trigger": trigger,
            "status": str(status_obj.get("status") or ""),
            "result": str(status_obj.get("last_result") or ""),
            "job_id": str(status_obj.get("job_id") or ""),
            "run_id": str(status_obj.get("last_run_id") or ""),
            "error": str(status_obj.get("last_error") or ""),
            "active_status": str(last_attempt.get("active_status") or ""),
            "active_run_id": str(last_attempt.get("active_run_id") or ""),
        }
        self._append_history_locked(pid, tid, record, runtime_session_id)
        self._save_task_runtime_locked(
            pid,
            tid,
            {
                "last_triggered_at": now,
                "last_trigger": trigger,
                "last_status": str(status_obj.get("status") or ""),
                "last_result": str(status_obj.get("last_result") or ""),
                "last_error": str(status_obj.get("last_error") or ""),
                "last_job_id": str(status_obj.get("job_id") or ""),
                "last_job_status": str(status_obj.get("status") or ""),
                "last_run_id": str(status_obj.get("last_run_id") or ""),
                "last_busy_status": str(last_attempt.get("active_status") or ""),
                "pending_job": str(status_obj.get("status") or "") in {"created", "scheduled", "retry_waiting"},
                "next_due_at": self._next_due_at(task),
            },
            runtime_session_id,
        )
        return record

    def run_now(self, project_id: str, heartbeat_task_id: str) -> Optional[dict[str, Any]]:
        task = self.get_task(project_id, heartbeat_task_id)
        if not isinstance(task, dict):
            return None
        if not bool(task.get("ready")):
            raise ValueError("heartbeat task not ready")
        return self._dispatch_task(project_id, task, trigger="manual", respect_busy_policy=False)

    def run_session_task_now(self, project_id: str, session_id: str, heartbeat_task_id: str) -> Optional[dict[str, Any]]:
        task = self.get_session_task(project_id, session_id, heartbeat_task_id)
        if not isinstance(task, dict):
            return None
        if not bool(task.get("ready")):
            raise ValueError("heartbeat task not ready")
        return self._dispatch_task(project_id, task, trigger="manual", respect_busy_policy=False)

    def tick_once(self, project_id: str = "") -> None:
        cfg = _load_dashboard_cfg_current()
        projects = cfg.get("projects") if isinstance(cfg, dict) else []
        project_ids: list[str] = []
        if project_id:
            project_ids = [str(project_id).strip()]
        elif isinstance(projects, list):
            for row in projects:
                if not isinstance(row, dict):
                    continue
                pid = str(row.get("id") or "").strip()
                if pid:
                    project_ids.append(pid)
        for pid in project_ids:
            hcfg = _load_project_heartbeat_config(pid)
            tasks = _normalize_heartbeat_tasks(hcfg.get("tasks"))
            if not bool(hcfg.get("enabled")):
                for row in tasks:
                    tid = str(row.get("heartbeat_task_id") or "").strip()
                    if tid:
                        self._save_task_runtime_locked(
                            pid,
                            tid,
                            {"next_due_at": "", "last_status": "disabled", "pending_job": False},
                        )
            else:
                for row in tasks:
                    row = self._merge_task(pid, row)
                    tid = str(row.get("heartbeat_task_id") or "").strip()
                    if not tid:
                        continue
                    runtime = self._task_runtime_locked(pid, tid)
                    if not bool(row.get("enabled")):
                        self._save_task_runtime_locked(
                            pid,
                            tid,
                            {"next_due_at": "", "last_status": "disabled", "pending_job": False},
                        )
                        continue
                    if not bool(row.get("ready")):
                        self._save_task_runtime_locked(
                            pid,
                            tid,
                            {"next_due_at": "", "last_status": "invalid_config", "pending_job": False},
                        )
                        continue
                    if bool(runtime.get("pending_job")):
                        job_id = str(runtime.get("last_job_id") or "").strip()
                        job = self.task_push_runtime.get_status(pid, job_id) if job_id else None
                        if isinstance(job, dict):
                            status_obj = job.get("status") if isinstance(job.get("status"), dict) else {}
                            job_status = str(status_obj.get("status") or "").strip()
                            if job_status in {"created", "scheduled", "retry_waiting"}:
                                continue
                            self._save_task_runtime_locked(
                                pid,
                                tid,
                                {
                                    "pending_job": False,
                                    "last_job_status": job_status,
                                    "last_run_id": str(status_obj.get("last_run_id") or runtime.get("last_run_id") or ""),
                                    "last_error": str(status_obj.get("last_error") or runtime.get("last_error") or ""),
                                },
                            )
                    next_due_at = str(runtime.get("next_due_at") or "").strip()
                    if not next_due_at:
                        self._save_task_runtime_locked(
                            pid,
                            tid,
                            {
                                "next_due_at": self._next_due_at(row),
                                "last_status": str(runtime.get("last_status") or "idle"),
                            },
                        )
                        continue
                    due_ts = _parse_rfc3339_ts(next_due_at)
                    if due_ts > time.time():
                        continue
                    self._dispatch_task(pid, row, trigger="schedule", respect_busy_policy=True)
            for row in self._iter_session_tasks(pid):
                row = self._merge_task(pid, row)
                tid = str(row.get("heartbeat_task_id") or "").strip()
                sid = str(row.get("session_id") or "").strip()
                if not (tid and sid):
                    continue
                runtime = self._task_runtime_locked(pid, tid, sid)
                if not bool(row.get("enabled")):
                    self._save_task_runtime_locked(
                        pid,
                        tid,
                        {"next_due_at": "", "last_status": "disabled", "pending_job": False},
                        sid,
                    )
                    continue
                if not bool(row.get("ready")):
                    self._save_task_runtime_locked(
                        pid,
                        tid,
                        {"next_due_at": "", "last_status": "invalid_config", "pending_job": False},
                        sid,
                    )
                    continue
                if bool(runtime.get("pending_job")):
                    job_id = str(runtime.get("last_job_id") or "").strip()
                    job = self.task_push_runtime.get_status(pid, job_id) if job_id else None
                    if isinstance(job, dict):
                        status_obj = job.get("status") if isinstance(job.get("status"), dict) else {}
                        job_status = str(status_obj.get("status") or "").strip()
                        if job_status in {"created", "scheduled", "retry_waiting"}:
                            continue
                        self._save_task_runtime_locked(
                            pid,
                            tid,
                            {
                                "pending_job": False,
                                "last_job_status": job_status,
                                "last_run_id": str(status_obj.get("last_run_id") or runtime.get("last_run_id") or ""),
                                "last_error": str(status_obj.get("last_error") or runtime.get("last_error") or ""),
                            },
                            sid,
                        )
                        runtime = self._task_runtime_locked(pid, tid, sid)
                next_due_at = str(runtime.get("next_due_at") or "").strip()
                if not next_due_at:
                    self._save_task_runtime_locked(
                        pid,
                        tid,
                        {
                            "next_due_at": self._next_due_at(row),
                            "last_status": "idle",
                            "pending_job": False,
                        },
                        sid,
                    )
                    continue
                due_ts = _parse_rfc3339_ts(next_due_at)
                if due_ts <= 0:
                    self._save_task_runtime_locked(
                        pid,
                        tid,
                        {
                            "next_due_at": self._next_due_at(row),
                            "last_status": "idle",
                            "pending_job": False,
                        },
                        sid,
                    )
                    continue
                if due_ts <= time.time() + 1:
                    self._dispatch_task(pid, row, trigger="schedule", respect_busy_policy=True)

_CODEX_HISTORY_TITLE_CACHE_LOCK = threading.Lock()
_RUN_SESSION_SEMANTICS_REENTRY = threading.local()
_CODEX_HISTORY_TITLE_CACHE: dict[str, Any] = {
    "path": "",
    "mtime_ns": -1,
    "size": -1,
    "titles": {},
}


def _normalize_history_title_text(value: Any, max_len: int = 200) -> str:
    raw = str(value or "")
    if not raw:
        return ""
    first = ""
    for line in raw.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        txt = line.strip()
        if txt:
            first = txt
            break
    if not first:
        return ""
    first = re.sub(r"\s+", " ", first)
    return _safe_text(first, max_len).strip()


def _load_codex_history_title_index() -> dict[str, str]:
    """
    Load session title index from ~/.codex/history.jsonl.

    Keep the earliest title-like text per session_id, which aligns with Codex App
    session naming behavior based on the first meaningful prompt.
    """
    history_path = _codex_home() / "history.jsonl"
    if not history_path.exists() or not history_path.is_file():
        return {}
    try:
        st = history_path.stat()
        mtime_ns = int(getattr(st, "st_mtime_ns", int(st.st_mtime * 1_000_000_000)))
        size = int(st.st_size)
    except Exception:
        return {}

    cache_path = str(history_path)
    with _CODEX_HISTORY_TITLE_CACHE_LOCK:
        cache = _CODEX_HISTORY_TITLE_CACHE
        if (
            str(cache.get("path") or "") == cache_path
            and int(cache.get("mtime_ns") or -1) == mtime_ns
            and int(cache.get("size") or -1) == size
        ):
            titles = cache.get("titles")
            if isinstance(titles, dict):
                return dict(titles)

    titles: dict[str, str] = {}
    try:
        with history_path.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                raw = str(line or "").strip()
                if not raw or not raw.startswith("{"):
                    continue
                try:
                    obj = json.loads(raw)
                except Exception:
                    continue
                if not isinstance(obj, dict):
                    continue
                sid = str(
                    obj.get("session_id")
                    if "session_id" in obj
                    else obj.get("sessionId") if "sessionId" in obj else obj.get("id")
                ).strip().lower()
                if not sid or sid in titles or not _looks_like_uuid(sid):
                    continue
                title = _normalize_history_title_text(
                    obj.get("text") if "text" in obj else obj.get("title") if "title" in obj else obj.get("message")
                )
                if not title:
                    continue
                titles[sid] = title
    except Exception:
        return {}

    with _CODEX_HISTORY_TITLE_CACHE_LOCK:
        _CODEX_HISTORY_TITLE_CACHE["path"] = cache_path
        _CODEX_HISTORY_TITLE_CACHE["mtime_ns"] = mtime_ns
        _CODEX_HISTORY_TITLE_CACHE["size"] = size
        _CODEX_HISTORY_TITLE_CACHE["titles"] = dict(titles)
    return dict(titles)


def _session_runtime_scan_limit() -> int:
    raw = str(os.environ.get("CCB_SESSION_RUNTIME_SCAN_LIMIT") or "").strip()
    if raw:
        try:
            v = int(raw)
            return max(100, min(v, 5000))
        except Exception:
            pass
    return 1200


def _session_runtime_index_cache_ttl_s() -> float:
    raw = str(os.environ.get("CCB_SESSION_RUNTIME_CACHE_TTL_MS") or "").strip()
    if raw:
        try:
            v = float(raw) / 1000.0
            return max(0.5, min(v, 15.0))
        except Exception:
            pass
    return 4.0


def _session_runtime_index_inflight_wait_s() -> float:
    raw = str(os.environ.get("CCB_SESSION_RUNTIME_CACHE_INFLIGHT_WAIT_MS") or "").strip()
    if raw:
        try:
            v = float(raw) / 1000.0
            return max(0.2, min(v, 30.0))
        except Exception:
            pass
    return 8.0


def _session_archive_summary_cache_ttl_s() -> float:
    raw = str(os.environ.get("CCB_SESSION_ARCHIVE_SUMMARY_CACHE_TTL_MS") or "").strip()
    if raw:
        try:
            v = float(raw) / 1000.0
            return max(1.0, min(v, 60.0))
        except Exception:
            pass
    return 8.0


def _session_external_busy_probe_ttl_s() -> float:
    raw = str(os.environ.get("CCB_SESSION_EXTERNAL_BUSY_PROBE_TTL_MS") or "").strip()
    if raw:
        try:
            v = float(raw) / 1000.0
            return max(0.5, min(v, 30.0))
        except Exception:
            pass
    return 2.0


def _run_created_ts(meta: dict[str, Any]) -> float:
    return (
        _parse_iso_ts(meta.get("createdAt"))
        or _parse_iso_ts(meta.get("startedAt"))
        or _parse_iso_ts(meta.get("finishedAt"))
        or 0.0
    )


def _run_activity_ts(meta: dict[str, Any]) -> float:
    return (
        _parse_iso_ts(meta.get("lastProgressAt"))
        or _parse_iso_ts(meta.get("updatedAt"))
        or _parse_iso_ts(meta.get("finishedAt"))
        or _parse_iso_ts(meta.get("startedAt"))
        or _parse_iso_ts(meta.get("createdAt"))
        or 0.0
    )


def _latest_process_row_preview(process_rows: Any, max_len: int = 300) -> str:
    rows = process_rows if isinstance(process_rows, list) else []
    for row in reversed(rows):
        if isinstance(row, dict):
            text = _safe_text(str(row.get("text") or "").replace("\r\n", "\n").strip(), max_len).strip()
            if text:
                return text
        else:
            text = _safe_text(str(row or "").replace("\r\n", "\n").strip(), max_len).strip()
            if text:
                return text
    return ""


def _build_session_summary_from_meta(meta: dict[str, Any]) -> dict[str, Any]:
    process_rows = meta.get("processRows") or meta.get("process_rows") or []
    ai_preview = str(meta.get("lastPreview") or meta.get("partialPreview") or "").strip()
    if not ai_preview:
        ai_preview = _latest_process_row_preview(process_rows, 300)
    user_preview = str(meta.get("messagePreview") or "").strip()
    status = str(meta.get("status") or "").strip().lower()
    return {
        "latest_run_id": str(meta.get("id") or "").strip(),
        "latest_status": status,
        "updated_at": str(
            meta.get("lastProgressAt")
            or meta.get("updatedAt")
            or meta.get("finishedAt")
            or meta.get("startedAt")
            or meta.get("createdAt")
            or ""
        ).strip(),
        "latest_ai_msg": ai_preview,
        "latest_user_msg": user_preview,
        "last_preview": ai_preview or user_preview,
        "last_speaker": "assistant" if ai_preview else ("user" if user_preview else "assistant"),
        "last_sender_type": str(meta.get("sender_type") or ("user" if user_preview and not ai_preview else "")).strip(),
        "last_sender_name": str(meta.get("sender_name") or "").strip(),
        "last_sender_source": str(meta.get("sender_source") or ("manual" if user_preview and not ai_preview else "")).strip(),
        "last_error": str(meta.get("error") or "").strip() if status == "error" else "",
    }


def _run_status_display_state(status: Any) -> str:
    st = str(status or "").strip().lower()
    if st in {"running", "queued", "retry_waiting", "done", "error"}:
        return st
    if st in {"dispatching", "collecting", "scanning"}:
        return "running"
    if st == "planned":
        return "idle"
    return st or "idle"


def _session_runtime_internal_state(agg: dict[str, Any]) -> str:
    running_ids = agg.get("running_ids") if isinstance(agg, dict) else []
    queued_ids = agg.get("queued_ids") if isinstance(agg, dict) else []
    retry_ids = agg.get("retry_waiting_ids") if isinstance(agg, dict) else []
    latest_status = str((agg or {}).get("latest_status") or "").strip().lower()
    if isinstance(running_ids, list) and running_ids:
        return "running"
    if isinstance(queued_ids, list) and queued_ids:
        return "queued"
    if isinstance(retry_ids, list) and retry_ids:
        return "retry_waiting"
    if latest_status == "error":
        return "error"
    return "idle"


def _probe_external_session_busy_cached(
    session_id: str,
    cli_type: str = "codex",
    *,
    store: "RunStore" | None = None,
) -> tuple[bool, str]:
    sid = str(session_id or "").strip()
    if not sid:
        return False, ""
    cli_t = str(cli_type or "codex").strip() or "codex"
    key = f"{sid}|{cli_t}"
    ttl_s = _session_external_busy_probe_ttl_s()
    now = time.monotonic()
    cache = _session_external_busy_cache()
    with _session_external_busy_cache_lock():
        cached = cache.get(key)
        if isinstance(cached, dict):
            checked = float(cached.get("checked_at_mono") or 0.0)
            if (now - checked) <= ttl_s:
                return bool(cached.get("external_busy")), str(cached.get("updated_at") or "")
    busy = False
    try:
        busy = bool(_scan_session_busy_rows_effective(store, sid, cli_type=cli_t))
    except Exception:
        busy = False
    updated_at = _now_iso()
    with _session_external_busy_cache_lock():
        cache[key] = {
            "external_busy": bool(busy),
            "updated_at": updated_at,
            "checked_at_mono": now,
        }
    return bool(busy), updated_at


def _probe_external_session_busy_batch_cached(
    session_rows: list[tuple[str, str]],
    *,
    store: "RunStore" | None = None,
) -> dict[str, tuple[bool, str]]:
    """
    Batch probe external busy for multiple sessions with one process-table scan.
    Returns mapping key "{session_id}|{cli_type}" -> (external_busy, updated_at).
    """
    if not isinstance(session_rows, list) or not session_rows:
        return {}
    ttl_s = _session_external_busy_probe_ttl_s()
    now = time.monotonic()
    out: dict[str, tuple[bool, str]] = {}
    pending: list[tuple[str, str, str]] = []
    seen: set[str] = set()

    cache = _session_external_busy_cache()
    with _session_external_busy_cache_lock():
        for sid_raw, cli_raw in session_rows:
            sid = str(sid_raw or "").strip()
            cli_t = str(cli_raw or "codex").strip() or "codex"
            if not sid:
                continue
            key = f"{sid}|{cli_t}"
            if key in seen:
                continue
            seen.add(key)
            cached = cache.get(key)
            if isinstance(cached, dict):
                checked = float(cached.get("checked_at_mono") or 0.0)
                if (now - checked) <= ttl_s:
                    out[key] = (bool(cached.get("external_busy")), str(cached.get("updated_at") or ""))
                    continue
            pending.append((key, sid, cli_t))

    if not pending:
        return out

    rows = _scan_process_table_rows()
    updated_at = _now_iso()
    cache_patch: dict[str, dict[str, Any]] = {}
    for key, sid, cli_t in pending:
        busy = bool(_scan_session_busy_rows_effective(store, sid, cli_type=cli_t, rows=rows))
        out[key] = (busy, updated_at)
        cache_patch[key] = {
            "external_busy": bool(busy),
            "updated_at": updated_at,
            "checked_at_mono": now,
        }
    if cache_patch:
        with _session_external_busy_cache_lock():
            cache.update(cache_patch)
    return out


def _load_archived_session_summary(store: "RunStore", project_id: str, session_id: str) -> dict[str, Any]:
    pid = str(project_id or "").strip()
    sid = str(session_id or "").strip()
    if not (pid and sid):
        return {}
    runs_root = ""
    try:
        runs_root = str(Path(getattr(store, "runs_dir", "")).resolve())
    except Exception:
        runs_root = str(getattr(store, "runs_dir", "") or "")
    cache_key = f"{runs_root}|{pid}|{sid}"
    now_mono = time.monotonic()
    ttl_s = _session_archive_summary_cache_ttl_s()
    cache = _session_archive_summary_cache()
    with _session_archive_summary_cache_lock():
        cached = cache.get(cache_key)
        if isinstance(cached, dict):
            checked = float(cached.get("checked_at_mono") or 0.0)
            summary = cached.get("summary")
            if isinstance(summary, dict) and (now_mono - checked) <= ttl_s:
                return dict(summary)

    archive_root = getattr(store, "archive_dir", None)
    if not isinstance(archive_root, Path) or not archive_root.exists():
        return {}

    best_meta: dict[str, Any] | None = None
    best_ts = 0.0
    best_meta_path: Path | None = None
    try:
        meta_paths = sorted(archive_root.rglob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    except Exception:
        meta_paths = []
    for meta_path in meta_paths:
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(meta, dict):
            continue
        if str(meta.get("projectId") or "").strip() != pid:
            continue
        if str(meta.get("sessionId") or "").strip() != sid:
            continue
        ts = _run_created_ts(meta)
        if ts <= 0:
            try:
                ts = float(meta_path.stat().st_mtime)
            except Exception:
                ts = 0.0
        if ts < best_ts:
            continue
        best_ts = ts
        best_meta = meta
        best_meta_path = meta_path
        if str(meta.get("lastPreview") or meta.get("partialPreview") or meta.get("messagePreview") or "").strip():
            break

    summary: dict[str, Any] = {}
    if isinstance(best_meta, dict):
        ai_preview = str(best_meta.get("lastPreview") or best_meta.get("partialPreview") or "").strip()
        user_preview = str(best_meta.get("messagePreview") or "").strip()
        if best_meta_path is not None:
            try:
                if not ai_preview:
                    lp = best_meta_path.with_suffix('.last.txt')
                    if lp.exists():
                        ai_preview = _safe_text(lp.read_text(encoding='utf-8', errors='replace').replace("\r\n", "\n").strip(), 300)
            except Exception:
                pass
            try:
                if not user_preview:
                    mp = best_meta_path.with_suffix('.msg.txt')
                    if mp.exists():
                        user_preview = _safe_text(mp.read_text(encoding='utf-8', errors='replace').replace("\r\n", "\n").strip(), 260)
            except Exception:
                pass
        summary = {
            "last_preview": ai_preview or user_preview,
            "last_speaker": "assistant" if ai_preview else ("user" if user_preview else "assistant"),
            "last_sender_type": str(best_meta.get("sender_type") or ("user" if user_preview and not ai_preview else "")).strip(),
            "last_sender_name": str(best_meta.get("sender_name") or "").strip(),
            "last_sender_source": str(best_meta.get("sender_source") or ("manual" if user_preview and not ai_preview else "")).strip(),
            "latest_user_msg": user_preview,
            "latest_ai_msg": ai_preview,
            "last_error": str(best_meta.get("error") or "").strip() if str(best_meta.get("status") or "").strip().lower() == "error" else "",
            "updated_at": str(best_meta.get("finishedAt") or best_meta.get("startedAt") or best_meta.get("createdAt") or "").strip(),
            "latest_status": str(best_meta.get("status") or "").strip().lower(),
            "run_count": 0,
        }

    with _session_archive_summary_cache_lock():
        cache[cache_key] = {
            "checked_at_mono": now_mono,
            "summary": dict(summary),
        }
    return summary


def _build_session_run_semantics_cached(
    store: "RunStore",
    *,
    project_id: str,
    session_id: str,
) -> dict[str, Any]:
    pid = str(project_id or "").strip()
    sid = str(session_id or "").strip()
    if not (pid and sid):
        return {
            "run_fields": {},
            "session_health_state": "healthy",
            "latest_effective_run_summary": {},
            "latest_system_summary": {},
        }
    previous = bool(getattr(_RUN_SESSION_SEMANTICS_REENTRY, "active", False))
    _RUN_SESSION_SEMANTICS_REENTRY.active = True
    try:
        runs = store.list_runs(
            project_id=pid,
            session_id=sid,
            limit=_session_runtime_scan_limit(),
            include_payload=False,
        )
    finally:
        _RUN_SESSION_SEMANTICS_REENTRY.active = previous
    return build_session_semantics(runs)


def _invalidate_project_session_runtime_index_cache(project_id: str = "", *, session_id: str = "") -> None:
    pid = str(project_id or "").strip()
    sid = str(session_id or "").strip()
    now_mono = time.monotonic()
    with _session_runtime_index_cache_lock():
        cache = _session_runtime_index_cache()
        inflight = _session_runtime_index_inflight()
        invalidated = _session_runtime_index_invalidated_at()
        if pid:
            cache.pop(pid, None)
            invalidated[pid] = now_mono
        else:
            cache.clear()
            inflight.clear()
            invalidated.clear()
    if sid:
        with _session_external_busy_cache_lock():
            cache = _session_external_busy_cache()
            for key in list(cache.keys()):
                if str(key).startswith(f"{sid}|"):
                    cache.pop(key, None)
        with _session_archive_summary_cache_lock():
            cache = _session_archive_summary_cache()
            for key in list(cache.keys()):
                key_text = str(key)
                if not key_text.endswith(f"|{sid}"):
                    continue
                if pid and f"|{pid}|{sid}" not in key_text:
                    continue
                cache.pop(key, None)


def _session_runtime_index_cache_entry(
    project_id: str,
    *,
    now_mono: float,
    ttl_s: float,
) -> dict[str, dict[str, Any]] | None:
    pid = str(project_id or "").strip()
    if not pid:
        return None
    cached = _session_runtime_index_cache().get(pid)
    if not isinstance(cached, dict):
        return None
    index = cached.get("index")
    if not isinstance(index, dict):
        return None
    checked = float(cached.get("checked_at_mono") or 0.0)
    if (now_mono - checked) > ttl_s:
        return None
    build_started = float(cached.get("build_started_at_mono") or checked)
    invalidated_at = float(_session_runtime_index_invalidated_at().get(pid) or 0.0)
    if build_started < invalidated_at:
        return None
    return dict(index)


def _build_project_session_runtime_index(store: "RunStore", project_id: str) -> dict[str, dict[str, Any]]:
    pid = str(project_id or "").strip()
    if not pid:
        return {}
    ttl_s = _session_runtime_index_cache_ttl_s()
    build_started_mono = time.monotonic()
    builder = False
    inflight_event: threading.Event | None = None
    wait_s = _session_runtime_index_inflight_wait_s()
    while True:
        now_mono = time.monotonic()
        with _session_runtime_index_cache_lock():
            cached_index = _session_runtime_index_cache_entry(pid, now_mono=now_mono, ttl_s=ttl_s)
            if isinstance(cached_index, dict):
                return cached_index
            inflight = _session_runtime_index_inflight().get(pid)
            inflight_event = None
            if isinstance(inflight, dict):
                event = inflight.get("event")
                if isinstance(event, threading.Event):
                    inflight_event = event
            if inflight_event is None:
                inflight_event = threading.Event()
                _session_runtime_index_inflight()[pid] = {
                    "event": inflight_event,
                    "build_started_at_mono": now_mono,
                }
                builder = True
                build_started_mono = now_mono
                break
        if inflight_event is not None:
            inflight_event.wait(wait_s)

    try:
        runs = store.list_runs(project_id=pid, limit=_session_runtime_scan_limit(), include_payload=False)
        idx: dict[str, dict[str, Any]] = {}
        runs_by_session: dict[str, list[dict[str, Any]]] = {}
        for meta in runs:
            if not isinstance(meta, dict):
                continue
            sid = str(meta.get("sessionId") or "").strip()
            if not sid:
                continue
            rid = str(meta.get("id") or "").strip()
            if not rid:
                continue
            runs_by_session.setdefault(sid, []).append(meta)
            st = str(meta.get("status") or "").strip().lower()
            ts = _run_created_ts(meta)
            row = idx.setdefault(
                sid,
                {
                    "running_ids": [],
                    "queued_ids": [],
                    "retry_waiting_ids": [],
                    "external_busy": False,
                    "latest_run_id": "",
                    "latest_status": "",
                    "latest_ts": 0.0,
                    "updated_at": "",
                    "last_preview": "",
                    "last_speaker": "assistant",
                    "last_sender_type": "",
                    "last_sender_name": "",
                    "last_sender_source": "",
                    "latest_user_msg": "",
                    "latest_ai_msg": "",
                    "last_error": "",
                    "run_count": 0,
                    "active_activity_ts": 0.0,
                    "session_health_state": "healthy",
                    "latest_effective_run_summary": {},
                },
            )
            row["run_count"] = int(row.get("run_count") or 0) + 1
            if st == "running":
                row["running_ids"].append((ts, rid))
                activity_ts = _run_activity_ts(meta)
                if activity_ts >= float(row.get("active_activity_ts") or 0.0):
                    row["active_activity_ts"] = activity_ts
                    row.update(_build_session_summary_from_meta(meta))
            elif st == "queued":
                row["queued_ids"].append((ts, rid))
            elif st == "retry_waiting":
                row["retry_waiting_ids"].append((ts, rid))
            if st in {"queued", "retry_waiting"}:
                qreason = str(meta.get("queueReason") or "").strip().lower()
                if qreason == "session_busy_external":
                    row["external_busy"] = True
            if ts >= float(row.get("latest_ts") or 0.0):
                row["latest_ts"] = ts
                row["latest_run_id"] = rid
                row["latest_status"] = st
                row["updated_at"] = str(meta.get("finishedAt") or meta.get("startedAt") or meta.get("createdAt") or "").strip()
                ai_preview = str(meta.get("lastPreview") or meta.get("partialPreview") or "").strip()
                user_preview = str(meta.get("messagePreview") or "").strip()
                row["latest_ai_msg"] = ai_preview
                row["latest_user_msg"] = user_preview
                row["last_preview"] = ai_preview or user_preview
                row["last_speaker"] = "assistant" if ai_preview else ("user" if user_preview else "assistant")
                if user_preview and not ai_preview:
                    row["last_sender_type"] = str(meta.get("sender_type") or "user").strip() or "user"
                    row["last_sender_name"] = str(meta.get("sender_name") or "").strip()
                    row["last_sender_source"] = str(meta.get("sender_source") or "manual").strip() or "manual"
                else:
                    row["last_sender_type"] = ""
                    row["last_sender_name"] = ""
                    row["last_sender_source"] = ""
                row["last_error"] = str(meta.get("error") or "").strip() if st == "error" else ""

        for row in idx.values():
            for key in ("running_ids", "queued_ids", "retry_waiting_ids"):
                arr = row.get(key)
                if not isinstance(arr, list):
                    row[key] = []
                    continue
                arr_sorted = sorted(
                    [(float(x[0] or 0.0), str(x[1] or "").strip()) for x in arr if str(x[1] or "").strip()],
                    key=lambda t: (t[0], t[1]),
                )
                row[key] = arr_sorted
            row.pop("active_activity_ts", None)
        for sid, row in idx.items():
            semantics = build_session_semantics(runs_by_session.get(sid) or [])
            row["session_health_state"] = str(semantics.get("session_health_state") or "healthy")
            latest_effective = semantics.get("latest_effective_run_summary")
            row["latest_effective_run_summary"] = dict(latest_effective) if isinstance(latest_effective, dict) else {}

        with _session_runtime_index_cache_lock():
            cache_written_at_mono = time.monotonic()
            _session_runtime_index_cache()[pid] = {
                "checked_at_mono": cache_written_at_mono,
                "build_started_at_mono": max(float(build_started_mono or 0.0), cache_written_at_mono),
                "index": idx,
            }
        return idx
    finally:
        if builder and inflight_event is not None:
            with _session_runtime_index_cache_lock():
                current = _session_runtime_index_inflight().get(pid)
                if isinstance(current, dict) and current.get("event") is inflight_event:
                    _session_runtime_index_inflight().pop(pid, None)
            inflight_event.set()


def _build_session_runtime_state_for_row(
    row: dict[str, Any],
    agg: dict[str, Any],
    *,
    store: "RunStore" | None = None,
    probe_external_when_idle: bool = True,
) -> dict[str, Any]:
    sid = str(row.get("id") or "").strip()
    cli_type = _normalize_cli_type_id(row.get("cli_type") if "cli_type" in row else row.get("cliType"))
    running_ids = list(agg.get("running_ids") or [])
    queued_ids = list(agg.get("queued_ids") or [])
    retry_ids = list(agg.get("retry_waiting_ids") or [])
    internal_state = _session_runtime_internal_state(agg)
    external_busy = bool(agg.get("external_busy"))
    probe_updated_at = ""
    if (not external_busy) and probe_external_when_idle and sid and internal_state not in {"running", "queued", "retry_waiting"}:
        external_busy, probe_updated_at = _probe_external_session_busy_cached(sid, cli_type=cli_type, store=store)

    if internal_state in {"running", "queued", "retry_waiting"}:
        display_state = internal_state
    elif external_busy:
        display_state = "external_busy"
    elif internal_state == "error":
        display_state = "error"
    else:
        display_state = "idle"

    active_run_id = str(running_ids[0][1] if running_ids else "").strip()
    queued_run_id = str(queued_ids[0][1] if queued_ids else (retry_ids[0][1] if retry_ids else "")).strip()
    queue_depth = int(len(queued_ids) + len(retry_ids))
    updated_at = str(agg.get("updated_at") or "").strip() or probe_updated_at or _now_iso()
    return {
        "internal_state": internal_state,
        "external_busy": bool(external_busy),
        "display_state": display_state,
        "active_run_id": active_run_id,
        "queued_run_id": queued_run_id,
        "queue_depth": queue_depth,
        "updated_at": updated_at,
    }


def _build_session_display_state_fields(
    state: dict[str, Any],
    agg: dict[str, Any],
) -> dict[str, str]:
    fields = _session_display_build_fields(state, agg)
    return {
        "session_display_state": str(fields.get("session_display_state") or "idle"),
        "session_display_reason": str(fields.get("session_display_reason") or ""),
    }


def _build_session_latest_run_summary(summary: dict[str, Any], agg: dict[str, Any]) -> dict[str, Any]:
    merged = dict(agg or {})
    merged.update(
        {
            "last_preview": summary.get("last_preview") or merged.get("last_preview") or "",
            "last_speaker": summary.get("last_speaker") or merged.get("last_speaker") or "assistant",
            "last_sender_type": summary.get("last_sender_type") or merged.get("last_sender_type") or "",
            "last_sender_name": summary.get("last_sender_name") or merged.get("last_sender_name") or "",
            "last_sender_source": summary.get("last_sender_source") or merged.get("last_sender_source") or "",
            "latest_user_msg": summary.get("latest_user_msg") or merged.get("latest_user_msg") or "",
            "latest_ai_msg": summary.get("latest_ai_msg") or merged.get("latest_ai_msg") or "",
            "last_error": summary.get("last_error") or merged.get("last_error") or "",
            "updated_at": summary.get("updated_at") or merged.get("updated_at") or "",
            "latest_status": summary.get("latest_status") or merged.get("latest_status") or "",
        }
    )
    latest = _session_display_build_latest_run_summary(merged)
    if not any(latest.values()):
        return {}
    latest["run_count"] = int(summary.get("run_count") or agg.get("run_count") or 0)
    return latest


def _attach_runtime_state_to_sessions(
    store: "RunStore",
    sessions: list[dict[str, Any]],
    *,
    project_id: str,
) -> list[dict[str, Any]]:
    pid = str(project_id or "").strip()
    if not pid:
        return sessions
    idx = _build_project_session_runtime_index(store, pid)
    # Batch external-busy probe for idle sessions to avoid per-session ps scans on /api/sessions.
    probe_targets: list[tuple[str, str]] = []
    for row in sessions:
        if not isinstance(row, dict):
            continue
        sid = str(row.get("id") or "").strip()
        if not sid:
            continue
        agg = idx.get(sid) if sid else {}
        if bool((agg or {}).get("external_busy")):
            continue
        internal_state = _session_runtime_internal_state(agg or {})
        if internal_state in {"running", "queued", "retry_waiting"}:
            continue
        cli_type = _normalize_cli_type_id(row.get("cli_type") if "cli_type" in row else row.get("cliType"))
        probe_targets.append((sid, cli_type))
    busy_map = _probe_external_session_busy_batch_cached(probe_targets, store=store)

    out: list[dict[str, Any]] = []
    for row in sessions:
        if not isinstance(row, dict):
            continue
        item = dict(row)
        sid = str(item.get("id") or "").strip()
        agg = idx.get(sid) if sid else None
        # runtime_state 构造时关闭逐项 probe，统一走批量 probe 结果覆写。
        state = _build_session_runtime_state_for_row(item, agg or {}, store=store, probe_external_when_idle=False)
        cli_type = _normalize_cli_type_id(item.get("cli_type") if "cli_type" in item else item.get("cliType"))
        busy_key = f"{sid}|{cli_type}" if sid else ""
        busy_entry = busy_map.get(busy_key) if busy_key else None
        if isinstance(busy_entry, tuple) and len(busy_entry) >= 2:
            external_busy = bool(busy_entry[0]) or bool(state.get("external_busy"))
            state["external_busy"] = external_busy
            internal_state = str(state.get("internal_state") or "").strip().lower()
            if internal_state in {"running", "queued", "retry_waiting"}:
                state["display_state"] = internal_state
            elif external_busy:
                state["display_state"] = "external_busy"
            elif internal_state == "error":
                state["display_state"] = "error"
            else:
                state["display_state"] = "idle"
            updated_at = str(busy_entry[1] or "").strip()
            if updated_at:
                state["updated_at"] = updated_at
        item["runtime_state"] = state
        summary = agg if isinstance(agg, dict) else {}
        if (not str(summary.get("last_preview") or "").strip()) and sid:
            archived_summary = _load_archived_session_summary(store, pid, sid)
            if archived_summary:
                merged = dict(archived_summary)
                merged.update({k: v for k, v in summary.items() if v not in (None, "", [], {})})
                summary = merged
        display_fields = _build_session_display_state_fields(state, summary)
        item["session_display_state"] = str(
            display_fields.get("session_display_state") or item.get("session_display_state") or "idle"
        )
        item["session_display_reason"] = str(
            display_fields.get("session_display_reason") or item.get("session_display_reason") or ""
        )
        item["lastStatus"] = str(item.get("session_display_state") or item.get("lastStatus") or "idle")
        latest_run_summary = _build_session_latest_run_summary(summary, agg or {})
        if latest_run_summary:
            item["latest_run_summary"] = latest_run_summary
        latest_effective_run_summary = summary.get("latest_effective_run_summary")
        if isinstance(latest_effective_run_summary, dict) and latest_effective_run_summary:
            item["latest_effective_run_summary"] = dict(latest_effective_run_summary)
        session_health_state = str(summary.get("session_health_state") or "healthy").strip() or "healthy"
        if str(state.get("display_state") or "").strip().lower() in {"running", "queued", "retry_waiting", "external_busy"}:
            session_health_state = "busy"
        item["session_health_state"] = session_health_state
        if summary:
            item["lastPreview"] = str(summary.get("last_preview") or item.get("lastPreview") or "")
            item["lastSpeaker"] = str(summary.get("last_speaker") or item.get("lastSpeaker") or "assistant")
            item["lastSenderType"] = str(summary.get("last_sender_type") or item.get("lastSenderType") or "")
            item["lastSenderName"] = str(summary.get("last_sender_name") or item.get("lastSenderName") or "")
            item["lastSenderSource"] = str(summary.get("last_sender_source") or item.get("lastSenderSource") or "")
            item["latestUserMsg"] = str(summary.get("latest_user_msg") or item.get("latestUserMsg") or "")
            item["latestAiMsg"] = str(summary.get("latest_ai_msg") or item.get("latestAiMsg") or "")
            item["lastError"] = str(summary.get("last_error") or item.get("lastError") or "")
            item["runCount"] = int(summary.get("run_count") or item.get("runCount") or 0)
            item["lastActiveAt"] = str(summary.get("updated_at") or item.get("lastActiveAt") or item.get("last_used_at") or "")
        out.append(item)
    return out


def _infer_project_id_for_session(store: "RunStore", session_id: str) -> str:
    sid = str(session_id or "").strip()
    if not sid:
        return ""
    runs = store.list_runs(session_id=sid, limit=1, include_payload=False)
    if not runs:
        return ""
    row = runs[0] if isinstance(runs[0], dict) else {}
    return str(row.get("projectId") or "").strip()


def _infer_blocked_by_run_id(store: "RunStore", meta: dict[str, Any]) -> str:
    rid = str(meta.get("id") or "").strip()
    sid = str(meta.get("sessionId") or "").strip()
    pid = str(meta.get("projectId") or "").strip()
    if not (rid and sid and pid):
        return ""
    st = str(meta.get("status") or "").strip().lower()
    if st not in {"queued", "retry_waiting"}:
        return ""
    cur_ts = _run_created_ts(meta)
    runs = store.list_runs(project_id=pid, session_id=sid, limit=200, include_payload=False)
    running: list[tuple[float, str]] = []
    queued_like: list[tuple[float, str]] = []
    for row in runs:
        if not isinstance(row, dict):
            continue
        other_id = str(row.get("id") or "").strip()
        if not other_id or other_id == rid:
            continue
        other_st = str(row.get("status") or "").strip().lower()
        ts = _run_created_ts(row)
        if cur_ts > 0 and ts > 0 and ts > cur_ts:
            continue
        if other_st == "running":
            running.append((ts, other_id))
        elif other_st in {"queued", "retry_waiting"}:
            queued_like.append((ts, other_id))
    if running:
        running.sort(key=lambda t: (t[0], t[1]))
        return running[0][1]
    if queued_like:
        queued_like.sort(key=lambda t: (t[0], t[1]))
        return queued_like[0][1]
    return ""


def _build_run_observability_fields(
    store: "RunStore",
    meta: dict[str, Any],
    *,
    infer_blocked: bool = True,
    include_session_semantics: bool = True,
) -> dict[str, Any]:
    st = str(meta.get("status") or "").strip().lower()
    display_state = _run_status_display_state(st)
    run_semantics = classify_run_semantics(meta)
    queue_reason = str(meta.get("queueReason") or meta.get("queue_reason") or "").strip().lower()
    blocked_by_run_id = str(meta.get("blockedByRunId") or meta.get("blocked_by_run_id") or "").strip()
    if infer_blocked and (not blocked_by_run_id) and st in {"queued", "retry_waiting"} and queue_reason != "session_busy_external":
        blocked_by_run_id = _infer_blocked_by_run_id(store, meta)
    if not queue_reason:
        if st == "queued":
            queue_reason = "session_serial" if blocked_by_run_id else ""
        elif st == "retry_waiting":
            queue_reason = "retry_waiting"
    project_id = str(meta.get("projectId") or "").strip()
    session_id = str(meta.get("sessionId") or "").strip()
    run_id = str(meta.get("id") or "").strip()
    if (
        include_session_semantics
        and project_id
        and session_id
        and run_id
        and not bool(getattr(_RUN_SESSION_SEMANTICS_REENTRY, "active", False))
    ):
        session_semantics = _build_session_run_semantics_cached(
            store,
            project_id=project_id,
            session_id=session_id,
        )
        run_fields = (session_semantics.get("run_fields") or {}).get(run_id)
        if isinstance(run_fields, dict):
            run_semantics.update(run_fields)
    return {
        "display_state": display_state,
        "queue_reason": queue_reason,
        "blocked_by_run_id": blocked_by_run_id,
        "outcome_state": str(run_semantics.get("outcome_state") or "").strip(),
        "error_class": str(run_semantics.get("error_class") or "").strip(),
        "effective_for_session_health": bool(run_semantics.get("effective_for_session_health")),
        "effective_for_session_preview": bool(run_semantics.get("effective_for_session_preview")),
        "superseded_by_run_id": str(run_semantics.get("superseded_by_run_id") or "").strip(),
        "recovery_of_run_id": str(run_semantics.get("recovery_of_run_id") or "").strip(),
    }


def _decorate_session_display_fields(
    session: dict[str, Any],
    *,
    title_index: Optional[dict[str, str]] = None,
) -> dict[str, Any]:
    row = dict(session if isinstance(session, dict) else {})
    sid = str(row.get("id") or "").strip()
    sid_key = sid.lower()
    raw_cli = row.get("cli_type") if "cli_type" in row else row.get("cliType")
    cli_type = _normalize_cli_type_id(raw_cli)
    alias = str(row.get("alias") or "").strip()
    channel_name = str(
        row.get("channel_name") if "channel_name" in row else row.get("channelName")
    ).strip()
    row["model"] = str(row.get("model") or "").strip()
    row["reasoning_effort"] = _normalize_reasoning_effort(
        row.get("reasoning_effort") if "reasoning_effort" in row else row.get("reasoningEffort")
    )
    row["environment"] = str(row.get("environment") or "").strip()
    row["worktree_root"] = str(row.get("worktree_root") or "").strip()
    row["workdir"] = str(row.get("workdir") or "").strip()
    row["branch"] = str(row.get("branch") or "").strip()

    index = title_index if isinstance(title_index, dict) else _load_codex_history_title_index_for_display()
    codex_title = str(index.get(sid_key) or "").strip() if (cli_type == "codex" and sid_key) else ""

    used_codex_fallback = False
    if codex_title:
        row["codex_title"] = codex_title
    if not alias and codex_title:
        alias = codex_title
        row["alias"] = codex_title
        used_codex_fallback = True

    if alias:
        display_name = alias
        display_source = "codex_history" if used_codex_fallback else "alias"
    elif channel_name:
        display_name = channel_name
        display_source = "channel_name"
    elif sid:
        display_name = sid
        display_source = "session_id"
    else:
        display_name = ""
        display_source = "unknown"

    row["display_name"] = display_name
    row["display_name_source"] = display_source
    heartbeat_cfg = _load_session_heartbeat_config(row)
    row["heartbeat_summary"] = _heartbeat_summary_payload(heartbeat_cfg)
    return attach_agent_display_fields(row)


def _decorate_sessions_display_fields(sessions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    index = _load_codex_history_title_index_for_display()
    out: list[dict[str, Any]] = []
    for row in sessions:
        if not isinstance(row, dict):
            continue
        out.append(_decorate_session_display_fields(row, title_index=index))
    return out

def _normalize_bootstrap_v1_success_payload(result: dict[str, Any]) -> dict[str, Any]:
    warnings: list[str] = []
    raw_warnings = result.get("warnings")
    if isinstance(raw_warnings, list):
        for w in raw_warnings:
            txt = _safe_text(w, 500).strip()
            if txt:
                warnings.append(txt)
    ok = bool(result.get("ok"))
    payload = {
        "ok": ok,
        "channelName": _safe_text(result.get("channel_name"), 200).strip(),
        "sessionId": _safe_text(result.get("session_id"), 120).strip(),
        "initRunId": _safe_text(result.get("init_run_id"), 80).strip(),
        "initRunStatus": _safe_text(result.get("init_run_status"), 40).strip(),
        "okRunId": _safe_text(result.get("ok_run_id"), 80).strip(),
        "okRunStatus": _safe_text(result.get("ok_run_status"), 40).strip(),
        "taskFile": _safe_text(result.get("task_file"), 2000).strip(),
        "warnings": warnings,
        "resultPath": _safe_text(result.get("bootstrap_result_path"), 4000).strip(),
        "status": "done" if ok else "error",
    }
    return payload


def _extract_bootstrap_result_path_from_stdout(stdout: str) -> str:
    txt = str(stdout or "")
    import re

    m = re.search(r'"bootstrap_result_path"\s*:\s*"([^"]+)"', txt)
    if not m:
        return ""
    return str(m.group(1) or "").strip()


def _run_codex_channel_bootstrap_v1(
    *,
    project_id: str,
    channel_kind: str,
    channel_index: str,
    channel_name: str,
    task_title: str,
    goal: str = "",
    channel_scope: str = "",
    desc: str = "",
    session_alias: str = "",
    port: int = 0,
    timeout_s: int = 900,
) -> tuple[int, dict[str, Any]]:
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "create_codex_channel_bootstrap.py"
    if not script_path.exists():
        return 500, {
            "error": "bootstrap script not found",
            "message": "scripts/create_codex_channel_bootstrap.py not found",
            "step": "bootstrap_codex",
        }

    py = str(sys.executable or "python3").strip() or "python3"
    p = int(port or 0)
    if p <= 0:
        p = 18765
    cmd = [
        py,
        str(script_path),
        "--project-id",
        str(project_id),
        "--port",
        str(p),
        "--channel-kind",
        str(channel_kind),
        "--channel-index",
        str(channel_index),
        "--channel-name",
        str(channel_name),
        "--task-title",
        str(task_title),
    ]
    if str(goal).strip():
        cmd.extend(["--goal", str(goal)])
    if str(channel_scope).strip():
        cmd.extend(["--channel-scope", str(channel_scope)])
    if str(desc).strip():
        cmd.extend(["--desc", str(desc)])
    if str(session_alias).strip():
        cmd.extend(["--session-alias", str(session_alias)])
    token = str(os.environ.get("TASK_DASHBOARD_TOKEN") or "").strip()
    if token:
        cmd.extend(["--token", token])

    try:
        proc = subprocess.run(
            cmd,
            cwd=str(repo_root),
            text=True,
            capture_output=True,
            timeout=max(30, int(timeout_s)),
        )
    except subprocess.TimeoutExpired as e:
        return 500, {
            "error": "bootstrap script timeout",
            "message": f"bootstrap script timed out after {max(30, int(timeout_s))}s",
            "step": "bootstrap_codex",
            "stdoutTail": _tail_str(getattr(e, "stdout", "") or "", 4000),
            "stderrTail": _tail_str(getattr(e, "stderr", "") or "", 4000),
        }
    except Exception as e:
        return 500, {
            "error": "bootstrap script exec failed",
            "message": str(e),
            "step": "bootstrap_codex",
        }

    stdout = str(proc.stdout or "")
    stderr = str(proc.stderr or "")
    if proc.returncode != 0:
        return 500, {
            "error": "bootstrap script failed",
            "message": f"bootstrap script exited with code {proc.returncode}",
            "step": "bootstrap_codex",
            "exitCode": int(proc.returncode),
            "stdoutTail": _tail_str(stdout, 6000),
            "stderrTail": _tail_str(stderr, 6000),
        }

    result_obj: dict[str, Any] = {}
    json_tail = _extract_last_json_object_text(stdout)
    if json_tail:
        try:
            parsed = json.loads(json_tail)
            if isinstance(parsed, dict):
                result_obj = parsed
        except Exception:
            result_obj = {}

    # Prefer stable file content when available (script writes bootstrap-result.json).
    result_path = _safe_text(result_obj.get("bootstrap_result_path"), 4000).strip()
    if not result_path:
        result_path = _extract_bootstrap_result_path_from_stdout(stdout)
    if result_path:
        file_obj = _read_json_file_safe(Path(result_path))
        if file_obj:
            result_obj = file_obj

    if not result_obj:
        return 500, {
            "error": "bootstrap result parse failed",
            "message": "script succeeded but result JSON could not be parsed",
            "step": "bootstrap_codex_parse",
            "stdoutTail": _tail_str(stdout, 6000),
            "stderrTail": _tail_str(stderr, 6000),
        }

    payload = _normalize_bootstrap_v1_success_payload(result_obj)
    if not payload.get("channelName"):
        payload["channelName"] = str(channel_name)
    if not payload.get("status"):
        payload["status"] = "done" if payload.get("ok") else "error"
    return 200, payload


def _create_channel(project_id: str, channel_name: str, channel_desc: str, cli_type: str) -> dict[str, Any]:
    result = runtime_create_channel(
        project_id=project_id,
        channel_name=channel_name,
        channel_desc=channel_desc,
        cli_type=cli_type,
        config_path=_config_toml_path(),
        repo_root=_repo_root(),
        atomic_write_text=_atomic_write_text,
    )
    _clear_dashboard_cfg_cache()
    return result


# Status to directory mapping
STATUS_DIR_MAP = {
    "待开始": "任务",
    "待处理": "任务",
    "待验收": "任务",
    "进行中": "任务",
    "已完成": "已完成",
    "已验收通过": "已完成",
    "暂缓": "暂缓",
    "答复": "答复",
    "反馈": "反馈",
}
_TASK_STATUS_GATE_TASK_SUBDIRS = {"任务", "已完成", "暂缓"}
_TASK_STATUS_GATE_CHANNEL_SUBDIRS = _TASK_STATUS_GATE_TASK_SUBDIRS | {"答复", "反馈", "讨论空间", "问题", "产出物"}


def _task_status_gate_wip_limit() -> int:
    raw = str(os.environ.get("TASK_DASHBOARD_TASK_WIP_LIMIT", "3") or "").strip()
    try:
        value = int(raw or "3")
    except Exception:
        value = 3
    return max(0, min(value, 32))


def _task_status_gate_require_owner() -> bool:
    raw = os.environ.get("TASK_DASHBOARD_TASK_GATE_REQUIRE_OWNER")
    return bool(_coerce_bool(raw, True))


def _task_channel_root_for_file(file_path: Path) -> Path:
    current_dir = file_path.parent
    if current_dir.name in _TASK_STATUS_GATE_CHANNEL_SUBDIRS:
        return current_dir.parent
    return current_dir


def _scan_channel_wip_snapshot(channel_root: Path, *, repo_root: Path, exclude_path: Path | None = None) -> dict[str, Any]:
    count = 0
    sample_paths: list[str] = []
    excluded = ""
    try:
        excluded = str(exclude_path.resolve()) if isinstance(exclude_path, Path) else ""
    except Exception:
        excluded = str(exclude_path or "")

    for path in sorted(channel_root.rglob("*.md")):
        try:
            if not path.is_file():
                continue
        except Exception:
            continue
        if path.name.startswith("README") or path.name == "沟通-收件箱.md":
            continue
        rel = ""
        top_dir = ""
        try:
            rel_obj = path.relative_to(channel_root)
            rel = str(rel_obj)
            top_dir = rel_obj.parts[0] if len(rel_obj.parts) >= 2 else ""
        except Exception:
            rel = path.name
            top_dir = ""
        if top_dir and top_dir not in _TASK_STATUS_GATE_TASK_SUBDIRS:
            continue

        tags, _ = parse_leading_tags(path.stem)
        if len(tags) >= 2 and str(tags[1] or "").strip() not in {"", "任务"}:
            continue
        if not top_dir and (len(tags) < 2 or str(tags[1] or "").strip() != "任务"):
            continue

        try:
            current_resolved = str(path.resolve())
        except Exception:
            current_resolved = str(path)
        if excluded and current_resolved == excluded:
            continue

        status = str(tags[0] or "").strip() if tags else ""
        normalized = normalize_task_status(status)
        if not bool(normalized.get("counts_as_wip")):
            continue
        count += 1
        if len(sample_paths) < 3:
            sample_paths.append(rel if rel else str(path.relative_to(repo_root)))

    return {
        "count": count,
        "sample_paths": sample_paths,
    }


def _evaluate_task_status_gate(task_path: str, new_status: str, *, project_id_hint: str = "") -> dict[str, Any]:
    repo_root = _repo_root()
    rel_task_path = str(task_path or "").strip()
    target_status = str(new_status or "").strip()
    file_path = repo_root / rel_task_path
    if not file_path.exists():
        raise ValueError(f"Task file not found: {task_path}")

    tags, _ = parse_leading_tags(file_path.stem)
    current_status = str(tags[0] or "").strip() if tags else ""
    current_norm = normalize_task_status(current_status)
    target_norm = normalize_task_status(target_status)
    pid, channel_name, bucket = _resolve_task_project_channel(rel_task_path, project_hint=project_id_hint)

    gate: dict[str, Any] = {
        "checked": True,
        "applies": False,
        "passed": True,
        "forced": False,
        "bypassed": False,
        "force_allowed": True,
        "reason": "status_not_entering_in_progress",
        "summary": "",
        "current_status": current_status,
        "target_status": target_status,
        "scope": {
            "project_id": pid,
            "channel_name": channel_name,
            "bucket": bucket,
            "task_path": rel_task_path,
        },
        "config": {
            "require_owner": _task_status_gate_require_owner(),
            "channel_wip_limit": _task_status_gate_wip_limit(),
        },
        "rules": [],
    }

    if str(target_norm.get("primary_status") or "").strip() != "进行中":
        return gate
    if str(current_norm.get("primary_status") or "").strip() == "进行中":
        gate["reason"] = "already_in_progress"
        return gate
    if bucket != "任务":
        gate["reason"] = "invalid_task_scope"
        return gate

    gate["applies"] = True
    gate["reason"] = "entering_in_progress"
    md = safe_read_text(file_path)

    if bool(gate["config"]["require_owner"]):
        owner = extract_field(md, "负责人")
        owner_passed = bool(str(owner or "").strip())
        gate["rules"].append(
            {
                "key": "owner_required",
                "label": "负责人必填",
                "passed": owner_passed,
                "detail": "已填写负责人" if owner_passed else "缺少 `## 负责人` 或 `负责人:` 字段",
                "value": str(owner or "").strip(),
            }
        )

    wip_limit = int(gate["config"]["channel_wip_limit"] or 0)
    if wip_limit > 0:
        channel_root = _task_channel_root_for_file(file_path)
        snapshot = _scan_channel_wip_snapshot(channel_root, repo_root=repo_root, exclude_path=file_path)
        current_wip = int(snapshot.get("count") or 0)
        wip_passed = current_wip < wip_limit
        gate["rules"].append(
            {
                "key": "channel_wip_limit",
                "label": "通道进行中上限",
                "passed": wip_passed,
                "detail": (
                    f"当前进行中 {current_wip} / 上限 {wip_limit}"
                    if wip_passed
                    else f"当前进行中 {current_wip}，达到上限 {wip_limit}"
                ),
                "current": current_wip,
                "limit": wip_limit,
                "next": current_wip + 1,
                "sample_paths": snapshot.get("sample_paths") or [],
            }
        )

    failed_rules = [rule for rule in gate["rules"] if isinstance(rule, dict) and not bool(rule.get("passed"))]
    gate["passed"] = not failed_rules
    if failed_rules:
        gate["summary"] = "软门禁未通过：" + "；".join(str(rule.get("detail") or rule.get("label") or "").strip() for rule in failed_rules)
    else:
        gate["summary"] = "软门禁通过"
    return gate


def _change_task_status(task_path: str, new_status: str) -> dict[str, Any]:
    """
    Change task status by:
    1. Modifying the status tag in filename
    2. Moving file to corresponding directory based on status
    """
    import re

    repo_root = _repo_root()
    file_path = repo_root / task_path

    if not file_path.exists():
        raise ValueError(f"Task file not found: {task_path}")

    if new_status not in STATUS_DIR_MAP:
        raise ValueError(f"Invalid status: {new_status}")

    # Get current filename
    old_filename = file_path.name
    stem = old_filename.rsplit(".md", 1)[0] if old_filename.endswith(".md") else old_filename

    # Parse existing tags
    tag_pattern = r"^(【[^】]+】)+"
    tag_match = re.match(tag_pattern, stem)

    if tag_match:
        # Extract all tags
        tags = re.findall(r"【([^】]+)】", tag_match.group(0))
        rest = stem[tag_match.end():]
        old_status = tags[0] if tags else ""
        if tags:
            # Replace first tag (status) with new status
            tags[0] = new_status
        else:
            tags = [new_status]
    else:
        # No existing tags, add status tag
        old_status = ""
        tags = [new_status, "任务"]
        rest = stem

    # Build new filename
    new_tags_str = "".join(f"【{t}】" for t in tags)
    new_filename = f"{new_tags_str}{rest}.md"

    # Determine target directory based on new status
    target_subdir = STATUS_DIR_MAP[new_status]

    # Get the channel directory (parent of current status dir)
    current_dir = file_path.parent
    channel_dir = current_dir.parent  # e.g., 通道名/

    # Check if we need to move the file
    current_subdir = current_dir.name
    if current_subdir in ["任务", "已完成", "暂缓", "答复", "反馈", "讨论空间", "问题", "产出物"]:
        # Current file is in a status subdirectory
        target_dir = channel_dir / target_subdir
    else:
        # Current file is at channel root level, stay there
        target_dir = current_dir

    # Create target directory if needed
    target_dir.mkdir(parents=True, exist_ok=True)

    # Compute new path
    new_file_path = target_dir / new_filename

    # Move/rename file
    file_path.rename(new_file_path)

    # Compute new relative path
    new_rel_path = str(new_file_path.relative_to(repo_root))
    identity = _extract_task_identity_from_file(new_file_path)
    project_id, _, _ = _resolve_task_project_channel(new_rel_path)
    _record_task_move(
        repo_root=repo_root,
        project_id=project_id,
        old_path=task_path,
        new_path=new_rel_path,
        task_id=identity.get("task_id") or "",
        parent_task_id=identity.get("parent_task_id") or "",
    )

    return {
        "ok": True,
        "old_path": task_path,
        "new_path": new_rel_path,
        "task_id": str(identity.get("task_id") or "").strip(),
        "parent_task_id": str(identity.get("parent_task_id") or "").strip(),
        "old_filename": old_filename,
        "new_filename": new_filename,
        "old_status": old_status,
        "new_status": new_status,
    }


def _auto_kickoff_global_enabled() -> bool:
    raw = str(os.environ.get("AUTO_KICKOFF_ENABLED") or "").strip()
    if not raw:
        return True
    return _coerce_bool(raw, True)


def _auto_kickoff_project_enabled(project_id: str) -> bool:
    # 兼容历史测试与旧调用：若 server 侧被 monkeypatch，优先复用其覆盖值。
    try:
        import server as _server  # noqa: PLC0415

        override = getattr(_server, "_auto_kickoff_project_enabled", None)
        if callable(override) and override is not _auto_kickoff_project_enabled:
            return bool(override(project_id))
    except Exception:
        pass

    pid = str(project_id or "").strip()
    if not pid:
        return True
    cfg = _load_project_auto_dispatch_config(pid)
    return bool(cfg.get("enabled", False))


def _normalize_task_path_identity(task_path: str) -> str:
    return _identity_normalize_task_path(task_path, repo_root=_repo_root())


def _extract_task_title(task_path: str) -> str:
    import re


    name = Path(str(task_path or "")).name
    stem = name.rsplit(".md", 1)[0] if name.endswith(".md") else name
    stripped = re.sub(r"^(【[^】]+】)+", "", stem).strip()
    return stripped or stem


def _resolve_task_project_channel(task_path: str, project_hint: str = "") -> tuple[str, str, str]:
    norm = _normalize_task_path_identity(task_path)
    if not norm:
        return "", "", ""
    cfg = _load_dashboard_cfg_current()
    projects = cfg.get("projects")
    if not isinstance(projects, list):
        return "", "", ""

    hint = str(project_hint or "").strip()
    ordered: list[dict[str, Any]] = []
    for p in projects:
        if not isinstance(p, dict):
            continue
        pid = str(p.get("id") or "").strip()
        if not pid:
            continue
        if hint and pid == hint:
            ordered.insert(0, p)
        else:
            ordered.append(p)

    for p in ordered:
        pid = str(p.get("id") or "").strip()
        task_root_rel = _normalize_task_path_identity(str(p.get("task_root_rel") or ""))
        prefixes: list[str] = []
        if task_root_rel:
            prefixes.append(task_root_rel)
        # task_dashboard 常见短路径：任务规划/<channel>/...
        if pid == "task_dashboard":
            prefixes.append("任务规划")
        for prefix in prefixes:
            pre = str(prefix or "").strip().strip("/")
            if not pre:
                continue
            needle = pre + "/"
            if not norm.startswith(needle):
                continue
            rest = norm[len(needle) :]
            parts = rest.split("/")
            if len(parts) < 2:
                continue
            channel_name = str(parts[0] or "").strip()
            bucket = str(parts[1] or "").strip()
            if channel_name:
                return pid, channel_name, bucket

    # 最后兜底：路径本身是任务规划相对路径
    if norm.startswith("任务规划/"):
        parts = norm.split("/")
        if len(parts) >= 3:
            return "task_dashboard", str(parts[1] or "").strip(), str(parts[2] or "").strip()

    # 兼容历史前缀路径：".../task-dashboard/任务规划/<channel>/<bucket>/..."
    marker = "任务规划/"
    idx = norm.find(marker)
    if idx >= 0:
        parts = norm[idx:].split("/")
        if len(parts) >= 3:
            channel_name = str(parts[1] or "").strip()
            bucket = str(parts[2] or "").strip()
            if channel_name:
                for p in ordered:
                    pid = str(p.get("id") or "").strip()
                    channels = p.get("channels")
                    if not isinstance(channels, list):
                        continue
                    for row in channels:
                        if not isinstance(row, dict):
                            continue
                        if str(row.get("name") or "").strip() == channel_name:
                            return pid, channel_name, bucket
                if hint:
                    return hint, channel_name, bucket
                return "task_dashboard", channel_name, bucket

    return "", "", ""


def _channel_auto_kickoff_enabled(project_id: str, channel_name: str) -> bool:
    p = _find_project_cfg(project_id)
    channels = p.get("channels")
    if not isinstance(channels, list):
        return True
    cname = str(channel_name or "").strip()
    for row in channels:
        if not isinstance(row, dict):
            continue
        if str(row.get("name") or "").strip() != cname:
            continue
        if "auto_kickoff_enabled" in row:
            return _coerce_bool(row.get("auto_kickoff_enabled"), True)
        return True
    return True


def _resolve_auto_kickoff_target_session(
    session_store: SessionStore,
    project_id: str,
    channel_name: str,
) -> dict[str, str]:
    pid = str(project_id or "").strip()
    cname = str(channel_name or "").strip()
    if not pid or not cname:
        return {}

    row = session_store.get_channel_default_session(pid, cname)
    if isinstance(row, dict):
        sid = str(row.get("id") or "").strip()
        if sid and _looks_like_uuid(sid):
            cli_type = str(row.get("cli_type") or "").strip() or _project_channel_cli_type(pid, cname)
            return {
                "channel_name": cname,
                "session_id": sid,
                "source": "session_store",
                "cli_type": cli_type,
            }
    return {}


def _scan_task_auto_kickoff_history(
    store: "RunStore",
    project_id: str,
    task_path: str,
    *,
    dedupe_window_seconds: int = 600,
    hourly_window_seconds: int = 3600,
) -> dict[str, Any]:
    pid = str(project_id or "").strip()
    norm_task = _normalize_task_path_identity(task_path)
    out: dict[str, Any] = {
        "dedupe_hit": False,
        "hourly_count": 0,
        "last_job_id": "",
        "last_run_id": "",
    }
    if not pid or not norm_task:
        return out
    root = _task_push_state_root(store) / pid
    if not root.exists():
        return out

    now = time.time()
    dedupe_floor = now - max(60, int(dedupe_window_seconds or 600))
    hourly_floor = now - max(600, int(hourly_window_seconds or 3600))
    latest_ts = 0.0
    latest_job_id = ""
    latest_run_id = ""

    for path in root.glob("*.json"):
        raw = _read_json_file(path)
        if not raw:
            continue
        if str(raw.get("project_id") or "").strip() != pid:
            continue
        meta = raw.get("run_extra_meta")
        if not isinstance(meta, dict):
            continue
        trigger_type = str(meta.get("trigger_type") or "").strip().lower()
        if trigger_type not in {"task_status_auto_start", "task_status_auto_start_retry"}:
            continue
        hist_task = _normalize_task_path_identity(str(meta.get("task_path") or ""))
        if not hist_task or hist_task != norm_task:
            continue

        ts = (
            _parse_rfc3339_ts(raw.get("updated_at"))
            or _parse_rfc3339_ts(raw.get("created_at"))
            or _parse_rfc3339_ts(raw.get("scheduled_at"))
            or path.stat().st_mtime
        )
        if ts >= hourly_floor:
            out["hourly_count"] = int(out.get("hourly_count") or 0) + 1
        if ts >= dedupe_floor:
            out["dedupe_hit"] = True
        if ts > latest_ts:
            latest_ts = ts
            latest_job_id = str(raw.get("id") or "").strip()
            latest_run_id = str(raw.get("last_run_id") or "").strip()
            if not latest_run_id:
                attempts = raw.get("attempts")
                if isinstance(attempts, list):
                    for item in reversed(attempts):
                        if not isinstance(item, dict):
                            continue
                        rid = str(item.get("run_id") or "").strip()
                        if rid:
                            latest_run_id = rid
                            break

    out["last_job_id"] = latest_job_id
    out["last_run_id"] = latest_run_id
    return out


def _build_task_auto_kickoff_message(task_path: str) -> str:
    title = _extract_task_title(task_path)
    return "\n".join(
        [
            f"回执任务：{title}",
            "执行阶段：启动",
            "本次目标：任务已进入进行中，按自动首发规则启动执行。",
            "需要对方：完成后回传关键结果与待确认项（无则写无）。",
        ]
    )


def _dispatch_task_status_auto_start(
    *,
    store: "RunStore",
    session_store: SessionStore,
    task_push_runtime: Optional["TaskPushRuntimeRegistry"],
    task_path: str,
    old_status: str,
    new_status: str,
    auto_start_ccb: bool = True,
    auto_start_message: str = "",
    project_id_hint: str = "",
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "enabled": bool(auto_start_ccb),
        "triggered": False,
        "status": "skipped",
        "dispatch_state": "skipped",
        "job_id": "",
        "run_id": "",
        "reason": "",
        "note": "",
        "manual_takeover_required": False,
    }

    if not auto_start_ccb:
        result["status"] = "disabled"
        result["dispatch_state"] = "disabled"
        result["reason"] = "request_disabled"
        return result
    if not _auto_kickoff_global_enabled():
        result["enabled"] = False
        result["status"] = "disabled"
        result["dispatch_state"] = "disabled"
        result["reason"] = "global_disabled"
        return result
    if str(new_status or "").strip() != "进行中" or str(old_status or "").strip() == "进行中":
        result["reason"] = "status_not_entering_in_progress"
        result["dispatch_state"] = "not_entering_in_progress"
        return result
    if task_push_runtime is None:
        result["status"] = "error"
        result["dispatch_state"] = "runtime_unavailable"
        result["reason"] = "runtime_unavailable"
        result["manual_takeover_required"] = True
        return result

    pid, channel_name, bucket = _resolve_task_project_channel(task_path, project_hint=project_id_hint)
    if not pid or not channel_name:
        result["dispatch_state"] = "path_unresolved"
        result["reason"] = "path_unresolved"
        result["manual_takeover_required"] = True
        return result
    if bucket != "任务":
        result["dispatch_state"] = "invalid_task_scope"
        result["reason"] = "invalid_task_scope"
        result["note"] = f"bucket={bucket or '-'}"
        return result
    if not _auto_kickoff_project_enabled(pid):
        result["enabled"] = False
        result["status"] = "disabled"
        result["dispatch_state"] = "project_disabled"
        result["reason"] = "project_disabled"
        result["target"] = {"project_id": pid, "channel_name": channel_name}
        return result
    if not _channel_auto_kickoff_enabled(pid, channel_name):
        result["status"] = "disabled"
        result["dispatch_state"] = "channel_disabled"
        result["reason"] = "channel_disabled"
        result["target"] = {"project_id": pid, "channel_name": channel_name}
        return result

    target = _resolve_auto_kickoff_target_session(session_store, pid, channel_name)
    if not target:
        result["dispatch_state"] = "target_unresolved"
        result["reason"] = "target_unresolved"
        result["target"] = {"project_id": pid, "channel_name": channel_name}
        result["manual_takeover_required"] = True
        return result

    stats = _scan_task_auto_kickoff_history(store, pid, task_path)
    result["target"] = {
        "project_id": pid,
        "channel_name": channel_name,
        "session_id": str(target.get("session_id") or ""),
        "source": str(target.get("source") or ""),
    }
    result["stats"] = {
        "hourly_count": int(stats.get("hourly_count") or 0),
        "dedupe_window_hit": bool(stats.get("dedupe_hit")),
    }
    if stats.get("last_job_id"):
        result["stats"]["last_job_id"] = str(stats.get("last_job_id") or "")
    if stats.get("last_run_id"):
        result["stats"]["last_run_id"] = str(stats.get("last_run_id") or "")

    if bool(stats.get("dedupe_hit")):
        result["dispatch_state"] = "dedupe_window_hit"
        result["reason"] = "dedupe_window_hit"
        result["job_id"] = str(stats.get("last_job_id") or "")
        result["run_id"] = str(stats.get("last_run_id") or "")
        return result
    if int(stats.get("hourly_count") or 0) >= 2:
        result["dispatch_state"] = "hourly_limited"
        result["reason"] = "hourly_limited"
        result["job_id"] = str(stats.get("last_job_id") or "")
        result["run_id"] = str(stats.get("last_run_id") or "")
        result["manual_takeover_required"] = True
        return result

    msg = str(auto_start_message or "").strip() or _build_task_auto_kickoff_message(task_path)
    extra_meta = {
        "trigger_type": "task_status_auto_start",
        "task_path": _normalize_task_path_identity(task_path),
        "execution_mode": "auto_start",
        "owner_channel_name": channel_name,
    }
    try:
        sent = task_push_runtime.send_now(
            project_id=pid,
            channel_name=channel_name,
            session_id=str(target.get("session_id") or ""),
            message=msg,
            profile_label="ccb",
            run_extra_meta=extra_meta,
        )
    except Exception as e:
        result["status"] = "error"
        result["dispatch_state"] = "dispatch_error"
        result["reason"] = "dispatch_error"
        result["note"] = f"{type(e).__name__}: {e}"
        result["manual_takeover_required"] = True
        return result

    sent_status = sent.get("status") if isinstance(sent.get("status"), dict) else {}
    status_name = str(sent_status.get("status") or "").strip().lower()
    run_id = str(sent_status.get("last_run_id") or "").strip()
    if not run_id:
        attempts = sent.get("attempts")
        if isinstance(attempts, list):
            for item in reversed(attempts):
                if not isinstance(item, dict):
                    continue
                rid = str(item.get("run_id") or "").strip()
                if rid:
                    run_id = rid
                    break
    result["job_id"] = str(sent_status.get("job_id") or "")
    result["run_id"] = run_id
    result["triggered"] = bool(result["job_id"] or result["run_id"])

    if status_name == "dispatched":
        result["status"] = "dispatched"
        result["dispatch_state"] = "dispatched"
        return result

    if status_name == "skipped_active":
        retry_meta = dict(extra_meta)
        retry_meta["trigger_type"] = "task_status_auto_start_retry"
        retry = task_push_runtime.schedule_send(
            project_id=pid,
            channel_name=channel_name,
            session_id=str(target.get("session_id") or ""),
            message=msg,
            scheduled_at=_iso_after_s(60),
            retry_interval_seconds=300,
            max_attempts=2,
            profile_label="ccb",
            run_extra_meta=retry_meta,
        )
        retry_status = retry.get("status") if isinstance(retry.get("status"), dict) else {}
        retry_name = str(retry_status.get("status") or "").strip().lower()
        result["job_id"] = str(retry_status.get("job_id") or "") or result["job_id"]
        result["run_id"] = str(retry_status.get("last_run_id") or "").strip() or result["run_id"]
        if retry_name in {"scheduled", "retry_waiting"}:
            result["status"] = "retry_scheduled"
            result["dispatch_state"] = "retry_scheduled"
            result["reason"] = "active_conflict_retry"
            result["note"] = "send_now_active_conflict"
            return result
        if retry_name == "dispatched":
            result["status"] = "dispatched"
            result["dispatch_state"] = "retry_dispatched"
            result["reason"] = "active_conflict_retry"
            return result
        result["status"] = "error"
        result["dispatch_state"] = "retry_failed"
        result["reason"] = "retry_failed"
        result["manual_takeover_required"] = True
        return result

    result["status"] = status_name or "error"
    result["dispatch_state"] = status_name or "error"
    if status_name in {"error", "exhausted"}:
        result["manual_takeover_required"] = True
    return result
