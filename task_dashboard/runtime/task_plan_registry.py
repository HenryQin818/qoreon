# -*- coding: utf-8 -*-
"""
TaskPlanRuntimeRegistry - task planning runtime.

Extracted from server.py to reduce file size.
Uses _get_server() lazy import for cross-references to remaining server.py functions.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional

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


__all__ = [
    "TaskPlanRuntimeRegistry",
    "list_task_plans_response",
    "upsert_task_plan_response",
    "activate_task_plan_response",
]


def __getattr__(name):
    """Lazy resolution of names still defined in server.py (avoids circular imports)."""
    import server
    try:
        return getattr(server, name)
    except AttributeError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _normalize_task_path_identity(task_path: str) -> str:
    return __getattr__("_normalize_task_path_identity")(task_path)


def _parse_rfc3339_ts(value: Any):
    return __getattr__("_parse_rfc3339_ts")(value)


def _resolve_task_project_channel(task_path: str, *, project_hint: str = ""):
    return __getattr__("_resolve_task_project_channel")(task_path, project_hint=project_hint)


def _resolve_primary_target_by_channel(project_id: str, channel_name: str):
    return __getattr__("_resolve_primary_target_by_channel")(project_id, channel_name)


def _build_task_auto_kickoff_message(task_path: str) -> str:
    return __getattr__("_build_task_auto_kickoff_message")(task_path)


from task_dashboard.runtime.scheduler_helpers import *  # noqa: F401,F403


class TaskPlanRuntimeRegistry:
    """
    Runtime for task plan table:
    - list/upsert/activate task plans
    - periodic executor for activation_mode != manual
    """

    _BATCH_STATUS = {"planned", "active", "paused", "done", "blocked"}
    _TASK_STATUS = {"planned", "queued", "running", "done", "error", "skipped", "blocked"}
    _ACTIVATION_MODE = {"manual", "at_time", "previous_batch_done"}
    _ACTIVATE_WHEN = {"manual", "at_time", "previous_batch_done"}
    _DISPATCH_MODE = {"immediate", "scheduled"}
    _DEPENDENCY_READY = {"done", "queued", "running", "skipped"}
    _DISPATCH_SUCCESS = {"dispatched", "retry_waiting", "retry_dispatched", "scheduled"}

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
        self._plans: dict[tuple[str, str], dict[str, Any]] = {}
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        interval_raw = _coerce_int(os.environ.get("CCB_TASK_PLAN_TICK_SECONDS"), 60)
        self._tick_seconds = max(20, min(300, int(interval_raw or 60)))

    def start(self) -> None:
        with self._lock:
            if isinstance(self._thread, threading.Thread) and self._thread.is_alive():
                return
            self._stop_event = threading.Event()
            t = threading.Thread(target=self._loop, daemon=True, name="task-plan-executor")
            self._thread = t
            t.start()

    def shutdown(self) -> None:
        self._stop_event.set()
        with self._lock:
            t = self._thread
            self._thread = None
        if isinstance(t, threading.Thread):
            try:
                t.join(timeout=0.2)
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

    def _plan_key(self, project_id: str, plan_id: str) -> tuple[str, str]:
        return (str(project_id or "").strip(), str(plan_id or "").strip())

    def _load_plan_from_disk(self, project_id: str, plan_id: str) -> Optional[dict[str, Any]]:
        pid = str(project_id or "").strip()
        rid = str(plan_id or "").strip()
        if not pid or not rid:
            return None
        raw = _read_json_file(_task_plan_item_path(self.store, pid, rid))
        if not raw:
            return None
        if str(raw.get("project_id") or "").strip() != pid:
            return None
        if str(raw.get("plan_id") or "").strip() != rid:
            return None
        return raw

    def _get_plan_locked(self, project_id: str, plan_id: str) -> Optional[dict[str, Any]]:
        key = self._plan_key(project_id, plan_id)
        cached = self._plans.get(key)
        if isinstance(cached, dict):
            return dict(cached)
        disk = self._load_plan_from_disk(project_id, plan_id)
        if not disk:
            return None
        self._plans[key] = dict(disk)
        return dict(disk)

    def _save_plan_locked(self, plan: dict[str, Any]) -> dict[str, Any]:
        pid = str(plan.get("project_id") or "").strip()
        rid = str(plan.get("plan_id") or "").strip()
        if not pid or not rid:
            return plan
        plan["updated_at"] = _now_iso()
        key = self._plan_key(pid, rid)
        self._plans[key] = dict(plan)
        _write_json_file(_task_plan_item_path(self.store, pid, rid), plan)
        return plan

    def _write_runtime_snapshot(self, project_id: str, patch: dict[str, Any]) -> None:
        pid = str(project_id or "").strip()
        if not pid:
            return
        path = _task_plan_runtime_path(self.store, pid)
        current = _read_json_file(path)
        out = current if isinstance(current, dict) else {}
        out.update({k: v for k, v in patch.items() if k})
        out["updated_at"] = _now_iso()
        _write_json_file(path, out)

    def _task_key(self, task_path: str) -> str:
        return _normalize_task_path_identity(task_path)

    def _normalize_plan(self, project_id: str, payload: dict[str, Any], existing: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        pid = str(project_id or "").strip()
        base = existing if isinstance(existing, dict) else {}
        plan_id = _safe_text(payload.get("plan_id") if "plan_id" in payload else payload.get("planId"), 120).strip()
        if not plan_id:
            plan_id = _safe_text(base.get("plan_id"), 120).strip()
        if not plan_id:
            raise ValueError("missing plan_id")

        name = _safe_text(payload.get("name") if "name" in payload else base.get("name"), 200).strip()
        enabled_src = payload.get("enabled") if "enabled" in payload else base.get("enabled")
        activation_mode_src = (
            payload.get("activation_mode")
            if "activation_mode" in payload
            else (payload.get("activationMode") if "activationMode" in payload else base.get("activation_mode"))
        )
        activation_mode = _safe_text(activation_mode_src, 40).strip().lower() or "manual"
        if activation_mode not in self._ACTIVATION_MODE:
            raise ValueError("invalid activation_mode")

        auto_dispatch_src = (
            payload.get("auto_dispatch_enabled")
            if "auto_dispatch_enabled" in payload
            else (payload.get("autoDispatchEnabled") if "autoDispatchEnabled" in payload else base.get("auto_dispatch_enabled"))
        )
        auto_inspection_src = (
            payload.get("auto_inspection_enabled")
            if "auto_inspection_enabled" in payload
            else (
                payload.get("autoInspectionEnabled")
                if "autoInspectionEnabled" in payload
                else base.get("auto_inspection_enabled")
            )
        )
        raw_batches = payload.get("batches")
        if raw_batches is None and isinstance(base.get("batches"), list):
            raw_batches = base.get("batches")
        if not isinstance(raw_batches, list) or not raw_batches:
            raise ValueError("batches must be non-empty")

        existing_task_state: dict[str, dict[str, Any]] = {}
        old_batches = base.get("batches")
        if isinstance(old_batches, list):
            for b in old_batches:
                if not isinstance(b, dict):
                    continue
                tasks = b.get("tasks")
                if not isinstance(tasks, list):
                    continue
                for t in tasks:
                    if not isinstance(t, dict):
                        continue
                    key = self._task_key(str(t.get("task_path") or ""))
                    if key:
                        existing_task_state[key] = t

        all_task_keys: set[str] = set()
        normalized_batches: list[dict[str, Any]] = []
        used_batch_ids: set[str] = set()
        used_order_index: set[int] = set()
        for row in raw_batches:
            if not isinstance(row, dict):
                raise ValueError("invalid batch item")
            batch_id = _safe_text(row.get("batch_id") if "batch_id" in row else row.get("batchId"), 120).strip()
            if not batch_id:
                raise ValueError("missing batch_id")
            if batch_id in used_batch_ids:
                raise ValueError("duplicate batch_id")
            used_batch_ids.add(batch_id)

            try:
                order_index = int(row.get("order_index") if "order_index" in row else row.get("orderIndex"))
            except Exception:
                raise ValueError("invalid order_index") from None
            if order_index <= 0:
                raise ValueError("invalid order_index")
            if order_index in used_order_index:
                raise ValueError("duplicate order_index")
            used_order_index.add(order_index)

            b_status = _safe_text(row.get("status"), 40).strip().lower() or "planned"
            if b_status not in self._BATCH_STATUS:
                raise ValueError("invalid batch.status")
            activate_when = _safe_text(row.get("activate_when") if "activate_when" in row else row.get("activateWhen"), 40).strip().lower() or "manual"
            if activate_when not in self._ACTIVATE_WHEN:
                raise ValueError("invalid activate_when")

            planned_start_at = _safe_text(
                row.get("planned_start_at") if "planned_start_at" in row else row.get("plannedStartAt"),
                80,
            ).strip()
            planned_end_at = _safe_text(
                row.get("planned_end_at") if "planned_end_at" in row else row.get("plannedEndAt"),
                80,
            ).strip()
            if planned_start_at and _parse_rfc3339_ts(planned_start_at) <= 0:
                raise ValueError("invalid planned_start_at")
            if planned_end_at and _parse_rfc3339_ts(planned_end_at) <= 0:
                raise ValueError("invalid planned_end_at")
            if planned_start_at and planned_end_at:
                if _parse_rfc3339_ts(planned_end_at) < _parse_rfc3339_ts(planned_start_at):
                    raise ValueError("planned_end_at must be >= planned_start_at")

            raw_tasks = row.get("tasks")
            if not isinstance(raw_tasks, list) or not raw_tasks:
                raise ValueError("batch.tasks must be non-empty")
            normalized_tasks: list[dict[str, Any]] = []
            for t in raw_tasks:
                if not isinstance(t, dict):
                    raise ValueError("invalid batch task item")
                task_path = _safe_text(t.get("task_path") if "task_path" in t else t.get("taskPath"), 1600).strip()
                task_key = self._task_key(task_path)
                if not task_key:
                    raise ValueError("missing task_path")
                all_task_keys.add(task_key)

                depends_on_raw = t.get("depends_on") if "depends_on" in t else t.get("dependsOn")
                depends_on: list[str] = []
                if isinstance(depends_on_raw, list):
                    for dep in depends_on_raw:
                        d = self._task_key(str(dep or ""))
                        if d and d not in depends_on:
                            depends_on.append(d)
                if task_key in depends_on:
                    raise ValueError("depends_on must not include self")

                dispatch_mode = _safe_text(
                    t.get("dispatch_mode") if "dispatch_mode" in t else t.get("dispatchMode"),
                    40,
                ).strip().lower() or "immediate"
                if dispatch_mode not in self._DISPATCH_MODE:
                    raise ValueError("invalid dispatch_mode")
                scheduled_at = _safe_text(
                    t.get("scheduled_at") if "scheduled_at" in t else t.get("scheduledAt"),
                    80,
                ).strip()
                if scheduled_at and _parse_rfc3339_ts(scheduled_at) <= 0:
                    raise ValueError("invalid scheduled_at")
                if dispatch_mode == "scheduled" and not scheduled_at:
                    scheduled_at = _now_iso()

                retry_max_attempts = _coerce_int(
                    t.get("retry_max_attempts") if "retry_max_attempts" in t else t.get("retryMaxAttempts"),
                    2,
                )
                retry_max_attempts = max(1, min(2, int(retry_max_attempts or 2)))
                retry_interval_seconds = _coerce_int(
                    t.get("retry_interval_seconds")
                    if "retry_interval_seconds" in t
                    else t.get("retryIntervalSeconds"),
                    60,
                )
                retry_interval_seconds = max(30, int(retry_interval_seconds or 60))

                t_status = _safe_text(t.get("status"), 40).strip().lower() or "planned"
                if t_status not in self._TASK_STATUS:
                    raise ValueError("invalid task.status")
                prev = existing_task_state.get(task_key) or {}
                callback_to = _safe_text(
                    t.get("callback_to") if "callback_to" in t else t.get("callbackTo"),
                    240,
                ).strip() or _safe_text(prev.get("callback_to"), 240).strip() or "主体-总控（合并与验收）"
                normalized_tasks.append(
                    {
                        "task_path": task_key,
                        "group_key": _safe_text(t.get("group_key"), 200).strip(),
                        "task_role": _safe_text(t.get("task_role"), 20).strip().lower() or "single",
                        "depends_on": depends_on,
                        "channel_name": _safe_text(
                            t.get("channel_name") if "channel_name" in t else t.get("channelName"),
                            240,
                        ).strip(),
                        "session_id": _safe_text(
                            t.get("session_id") if "session_id" in t else t.get("sessionId"),
                            120,
                        ).strip(),
                        "dispatch_mode": dispatch_mode,
                        "scheduled_at": scheduled_at,
                        "retry_max_attempts": retry_max_attempts,
                        "retry_interval_seconds": retry_interval_seconds,
                        "writeback_enabled": _coerce_bool(t.get("writeback_enabled"), True),
                        "callback_to": callback_to,
                        "status": t_status,
                        "dispatch_state": _safe_text(prev.get("dispatch_state"), 80).strip(),
                        "job_id": _safe_text(prev.get("job_id"), 120).strip(),
                        "run_id": _safe_text(prev.get("run_id"), 120).strip(),
                        "last_error": _safe_text(prev.get("last_error"), 800).strip(),
                        "updated_at": _safe_text(prev.get("updated_at"), 80).strip(),
                    }
                )

            normalized_batches.append(
                {
                    "batch_id": batch_id,
                    "order_index": order_index,
                    "name": _safe_text(row.get("name"), 200).strip(),
                    "status": b_status,
                    "planned_start_at": planned_start_at,
                    "planned_end_at": planned_end_at,
                    "activate_when": activate_when,
                    "tasks": normalized_tasks,
                }
            )

        for b in normalized_batches:
            tasks = b.get("tasks")
            if not isinstance(tasks, list):
                continue
            for t in tasks:
                deps = t.get("depends_on")
                if not isinstance(deps, list):
                    continue
                for dep in deps:
                    if dep not in all_task_keys:
                        raise ValueError("depends_on must reference tasks within the same plan")

        normalized_batches.sort(key=lambda x: (int(x.get("order_index") or 0), str(x.get("batch_id") or "")))
        created_at = _safe_text(base.get("created_at"), 80).strip() or _now_iso()
        return {
            "plan_id": plan_id,
            "project_id": pid,
            "name": name,
            "enabled": _coerce_bool(enabled_src, True),
            "activation_mode": activation_mode,
            "auto_dispatch_enabled": _coerce_bool(auto_dispatch_src, False),
            "auto_inspection_enabled": _coerce_bool(auto_inspection_src, True),
            "status": _safe_text(payload.get("status"), 40).strip().lower() or _safe_text(base.get("status"), 40).strip().lower() or "planned",
            "created_at": created_at,
            "updated_at": _now_iso(),
            "batches": normalized_batches,
        }

    def list(self, project_id: str, *, enabled: Optional[bool] = None, limit: int = 20) -> list[dict[str, Any]]:
        pid = str(project_id or "").strip()
        root = _task_plan_project_root(self.store, pid)
        if not root.exists():
            return []
        rows: list[tuple[float, dict[str, Any]]] = []
        for p in root.glob("*.json"):
            if p.name == "_runtime.json":
                continue
            raw = _read_json_file(p)
            if not raw:
                continue
            if str(raw.get("project_id") or "").strip() != pid:
                continue
            if enabled is not None and bool(raw.get("enabled")) != bool(enabled):
                continue
            ts = _parse_rfc3339_ts(raw.get("updated_at")) or p.stat().st_mtime
            rows.append((ts, raw))
        rows.sort(key=lambda x: x[0], reverse=True)
        out: list[dict[str, Any]] = []
        cap = max(1, min(100, int(limit or 20)))
        for _, row in rows[:cap]:
            out.append(dict(row))
        return out

    def get(self, project_id: str, plan_id: str) -> Optional[dict[str, Any]]:
        with self._lock:
            plan = self._get_plan_locked(project_id, plan_id)
        return dict(plan) if isinstance(plan, dict) else None

    def upsert(self, project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        pid = str(project_id or "").strip()
        rid = _safe_text(payload.get("plan_id") if "plan_id" in payload else payload.get("planId"), 120).strip()
        existing = self.get(pid, rid) if rid else None
        normalized = self._normalize_plan(pid, payload, existing=existing)
        with self._lock:
            saved = self._save_plan_locked(normalized)
        return dict(saved)

    def _dependency_ready(self, task_status: str) -> bool:
        return str(task_status or "").strip().lower() in self._DEPENDENCY_READY

    def _resolve_task_target(self, project_id: str, task: dict[str, Any]) -> dict[str, str]:
        pid = str(project_id or "").strip()
        channel_name = str(task.get("channel_name") or "").strip()
        session_id = str(task.get("session_id") or "").strip()
        if session_id and not channel_name:
            srow = self.session_store.get_session(session_id)
            if srow:
                channel_name = str(srow.get("channel_name") or "").strip()
        if channel_name and not session_id:
            target = _resolve_primary_target_by_channel(pid, channel_name)
            if target:
                session_id = str(target.get("session_id") or "").strip()
        if not channel_name:
            resolved_pid, resolved_channel, _ = _resolve_task_project_channel(str(task.get("task_path") or ""), project_hint=pid)
            if resolved_channel and (not resolved_pid or resolved_pid == pid):
                channel_name = resolved_channel
        if channel_name and not session_id:
            target = _resolve_auto_kickoff_target_session(self.session_store, pid, channel_name)
            if target:
                session_id = str(target.get("session_id") or "").strip()
        if channel_name and session_id and _looks_like_uuid(session_id):
            return {"channel_name": channel_name, "session_id": session_id}
        return {}

    def _dispatch_task_item(
        self,
        *,
        project_id: str,
        plan_id: str,
        batch_id: str,
        task: dict[str, Any],
        dry_run: bool,
        trigger: str,
        now_ts: float,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        task_path = str(task.get("task_path") or "").strip()
        out = {
            "task_path": task_path,
            "dispatch_state": "",
            "job_id": "",
            "run_id": "",
            "status": str(task.get("status") or "planned"),
            "last_error": "",
        }
        if dry_run:
            out["dispatch_state"] = "dry_run"
            return out, task

        target = self._resolve_task_target(project_id, task)
        if not target:
            out["dispatch_state"] = "target_unresolved"
            out["status"] = "blocked"
            out["last_error"] = "target_unresolved"
            task["status"] = "blocked"
            task["dispatch_state"] = "target_unresolved"
            task["last_error"] = "target_unresolved"
            task["updated_at"] = _now_iso()
            return out, task

        message = _build_task_auto_kickoff_message(task_path)
        run_extra_meta = {
            "trigger_type": "task_plan_activate",
            "execution_mode": "task_plan",
            "task_path": task_path,
            "plan_id": str(plan_id),
            "batch_id": str(batch_id),
            "activation_trigger": str(trigger or "manual"),
            "dispatch_mode": str(task.get("dispatch_mode") or "immediate"),
        }
        dispatch_mode = str(task.get("dispatch_mode") or "immediate").strip().lower()
        retry_max_attempts = max(1, min(2, int(task.get("retry_max_attempts") or 2)))
        retry_interval_seconds = max(30, int(task.get("retry_interval_seconds") or 60))
        scheduled_at = str(task.get("scheduled_at") or "").strip()
        item: dict[str, Any]
        if dispatch_mode == "scheduled":
            item = self.task_push_runtime.schedule_send(
                project_id=project_id,
                channel_name=target["channel_name"],
                session_id=target["session_id"],
                message=message,
                scheduled_at=scheduled_at or _now_iso(),
                retry_interval_seconds=retry_interval_seconds,
                max_attempts=retry_max_attempts,
                profile_label="ccb",
                run_extra_meta=run_extra_meta,
            )
        else:
            item = self.task_push_runtime.send_now(
                project_id=project_id,
                channel_name=target["channel_name"],
                session_id=target["session_id"],
                message=message,
                profile_label="ccb",
                run_extra_meta=run_extra_meta,
            )
            if str(item.get("status", {}).get("status") or "") == "skipped_active" and retry_max_attempts > 1:
                fallback_due = _iso_after_s(retry_interval_seconds)
                fallback = self.task_push_runtime.schedule_send(
                    project_id=project_id,
                    channel_name=target["channel_name"],
                    session_id=target["session_id"],
                    message=message,
                    scheduled_at=fallback_due,
                    retry_interval_seconds=retry_interval_seconds,
                    max_attempts=retry_max_attempts,
                    profile_label="ccb",
                    run_extra_meta={**run_extra_meta, "immediate_fallback": True},
                )
                item = fallback

        status_obj = item.get("status") if isinstance(item.get("status"), dict) else {}
        attempts = item.get("attempts") if isinstance(item.get("attempts"), list) else []
        run_id = str(status_obj.get("last_run_id") or "").strip()
        if not run_id:
            for a in reversed(attempts):
                if not isinstance(a, dict):
                    continue
                rid = str(a.get("run_id") or "").strip()
                if rid:
                    run_id = rid
                    break
        dispatch_state = str(status_obj.get("status") or "").strip() or "error"
        last_error = str(status_obj.get("last_error") or "").strip()
        if not last_error:
            for a in reversed(attempts):
                if not isinstance(a, dict):
                    continue
                err = str(a.get("error") or "").strip()
                if err:
                    last_error = err
                    break
        mapped_status = "queued" if dispatch_state in self._DISPATCH_SUCCESS else "error"
        if dispatch_state in {"skipped_active"}:
            mapped_status = "skipped"
        out.update(
            {
                "dispatch_state": dispatch_state,
                "job_id": str(status_obj.get("job_id") or ""),
                "run_id": run_id,
                "status": mapped_status,
                "last_error": last_error,
            }
        )
        task["status"] = mapped_status
        task["dispatch_state"] = dispatch_state
        task["job_id"] = out["job_id"]
        task["run_id"] = run_id
        task["last_error"] = last_error
        task["updated_at"] = _now_iso()
        return out, task

    def _pick_batch(self, plan: dict[str, Any], batch_id: str = "") -> Optional[dict[str, Any]]:
        batches = plan.get("batches")
        if not isinstance(batches, list) or not batches:
            return None
        if batch_id:
            for b in batches:
                if isinstance(b, dict) and str(b.get("batch_id") or "").strip() == str(batch_id or "").strip():
                    return b
            return None
        candidates = [b for b in batches if isinstance(b, dict) and str(b.get("status") or "planned").strip().lower() in {"planned", "paused", "blocked"}]
        if not candidates:
            return None
        candidates.sort(key=lambda x: (int(x.get("order_index") or 0), str(x.get("batch_id") or "")))
        return candidates[0]

    def _batch_window_state(self, batch: dict[str, Any], now_ts: float) -> tuple[bool, str]:
        start_at = str(batch.get("planned_start_at") or "").strip()
        end_at = str(batch.get("planned_end_at") or "").strip()
        if start_at:
            start_ts = _parse_rfc3339_ts(start_at)
            if start_ts > 0 and start_ts > now_ts:
                return False, "window_not_open"
        if end_at:
            end_ts = _parse_rfc3339_ts(end_at)
            if end_ts > 0 and now_ts > end_ts:
                return False, "window_expired"
        return True, ""

    def _rebuild_task_index(self, plan: dict[str, Any]) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        batches = plan.get("batches")
        if not isinstance(batches, list):
            return out
        for b in batches:
            if not isinstance(b, dict):
                continue
            tasks = b.get("tasks")
            if not isinstance(tasks, list):
                continue
            for t in tasks:
                if not isinstance(t, dict):
                    continue
                key = self._task_key(str(t.get("task_path") or ""))
                if key:
                    out[key] = t
        return out

    def activate(
        self,
        *,
        project_id: str,
        plan_id: str,
        batch_id: str = "",
        dry_run: bool = False,
        trigger: str = "manual",
    ) -> dict[str, Any]:
        pid = str(project_id or "").strip()
        rid = str(plan_id or "").strip()
        if not pid or not rid:
            raise ValueError("missing project_id/plan_id")
        with self._lock:
            plan = self._get_plan_locked(pid, rid)
            if not plan:
                raise FileNotFoundError("task plan not found")
            if not dry_run and not bool(plan.get("enabled")):
                raise PermissionError("task plan disabled")
            if not dry_run and not bool(plan.get("auto_dispatch_enabled", False)):
                raise PermissionError("task plan auto dispatch disabled")

            now_ts = time.time()
            batch = self._pick_batch(plan, batch_id=batch_id)
            if not isinstance(batch, dict):
                raise RuntimeError("batch not found or no activatable batch")
            ok_window, window_reason = self._batch_window_state(batch, now_ts)
            if not ok_window and not dry_run:
                raise RuntimeError(window_reason)

            task_index = self._rebuild_task_index(plan)
            tasks = batch.get("tasks")
            task_rows = tasks if isinstance(tasks, list) else []
            items: list[dict[str, Any]] = []
            activated_count = 0
            blocked_count = 0
            for task in task_rows:
                if not isinstance(task, dict):
                    continue
                task_path = self._task_key(str(task.get("task_path") or ""))
                depends_on = task.get("depends_on")
                dep_list = depends_on if isinstance(depends_on, list) else []
                unmet = []
                for dep in dep_list:
                    dep_key = self._task_key(str(dep or ""))
                    dep_row = task_index.get(dep_key) if dep_key else None
                    dep_status = str((dep_row or {}).get("status") or "").strip().lower()
                    if not dep_row or not self._dependency_ready(dep_status):
                        unmet.append(dep_key or str(dep or ""))
                if unmet:
                    state = "dependency_blocked"
                    task["status"] = "blocked"
                    task["dispatch_state"] = state
                    task["job_id"] = ""
                    task["run_id"] = ""
                    task["last_error"] = "depends_on_unmet:" + ",".join(unmet[:8])
                    task["updated_at"] = _now_iso()
                    items.append(
                        {
                            "task_path": task_path,
                            "dispatch_state": state,
                            "job_id": "",
                            "run_id": "",
                            "status": "blocked",
                            "last_error": str(task.get("last_error") or ""),
                        }
                    )
                    blocked_count += 1
                    continue

                dispatched, updated_task = self._dispatch_task_item(
                    project_id=pid,
                    plan_id=rid,
                    batch_id=str(batch.get("batch_id") or ""),
                    task=task,
                    dry_run=dry_run,
                    trigger=trigger,
                    now_ts=now_ts,
                )
                task.update(updated_task)
                items.append(dispatched)
                if str(dispatched.get("job_id") or "").strip():
                    activated_count += 1
                if str(dispatched.get("status") or "").strip().lower() == "blocked":
                    blocked_count += 1

            statuses = [
                str((t or {}).get("status") or "").strip().lower()
                for t in task_rows
                if isinstance(t, dict)
            ]
            if statuses and all(st == "done" for st in statuses):
                batch["status"] = "done"
            elif blocked_count and activated_count == 0:
                batch["status"] = "blocked"
            elif activated_count > 0:
                batch["status"] = "active"
            else:
                batch["status"] = "planned"
            plan["status"] = "active" if batch.get("status") in {"active", "done"} else str(batch.get("status") or "planned")
            plan["last_activated_at"] = _now_iso()
            plan["last_activated_batch_id"] = str(batch.get("batch_id") or "")
            self._save_plan_locked(plan)

        return {
            "ok": True,
            "project_id": pid,
            "plan_id": rid,
            "batch_id": str(batch.get("batch_id") or ""),
            "activated_count": int(activated_count),
            "items": items,
        }

    def _executor_pick_batch(self, plan: dict[str, Any], now_ts: float) -> Optional[str]:
        mode = str(plan.get("activation_mode") or "manual").strip().lower()
        if mode == "manual":
            return None
        batches = plan.get("batches")
        if not isinstance(batches, list) or not batches:
            return None
        ordered = [b for b in batches if isinstance(b, dict)]
        ordered.sort(key=lambda x: (int(x.get("order_index") or 0), str(x.get("batch_id") or "")))
        if mode == "at_time":
            for b in ordered:
                st = str(b.get("status") or "planned").strip().lower()
                if st not in {"planned", "paused", "blocked"}:
                    continue
                ok_window, reason = self._batch_window_state(b, now_ts)
                if ok_window:
                    return str(b.get("batch_id") or "")
                if reason == "window_expired":
                    b["status"] = "blocked"
                    continue
            return None

        # previous_batch_done
        ready_prev = True
        for b in ordered:
            st = str(b.get("status") or "planned").strip().lower()
            if st == "done":
                continue
            if st in {"active"}:
                ready_prev = False
                break
            if st in {"planned", "paused", "blocked"}:
                if not ready_prev:
                    break
                return str(b.get("batch_id") or "")
            ready_prev = False
            break
        return None

    def tick_once(self) -> None:
        root = _task_plan_state_root(self.store)
        if not root.exists():
            return
        for project_root in root.iterdir():
            if not project_root.is_dir():
                continue
            pid = str(project_root.name or "").strip()
            if not pid:
                continue
            self._write_runtime_snapshot(pid, {"state": "running", "last_tick_at": _now_iso(), "last_error": ""})
            plans = self.list(pid, enabled=True, limit=200)
            now_ts = time.time()
            for plan in plans:
                if not isinstance(plan, dict):
                    continue
                if not bool(plan.get("auto_dispatch_enabled", False)):
                    continue
                plan_id = str(plan.get("plan_id") or "").strip()
                if not plan_id:
                    continue
                batch_id = self._executor_pick_batch(plan, now_ts)
                if not batch_id:
                    continue
                try:
                    result = self.activate(
                        project_id=pid,
                        plan_id=plan_id,
                        batch_id=batch_id,
                        dry_run=False,
                        trigger="executor",
                    )
                    self._write_runtime_snapshot(
                        pid,
                        {
                            "state": "idle",
                            "last_tick_at": _now_iso(),
                            "last_plan_id": plan_id,
                            "last_batch_id": batch_id,
                            "last_activated_count": int(result.get("activated_count") or 0),
                            "last_error": "",
                        },
                    )
                except Exception as e:
                    self._write_runtime_snapshot(
                        pid,
                        {
                            "state": "error",
                            "last_tick_at": _now_iso(),
                            "last_plan_id": plan_id,
                            "last_batch_id": batch_id,
                            "last_error": f"{type(e).__name__}: {e}",
                        },
                    )


# =============================================================================
# Route handlers extracted from server.py
# =============================================================================


def list_task_plans_response(
    *,
    project_id: str,
    query_string: str,
    task_plan_runtime: "TaskPlanRuntimeRegistry",
    find_project_cfg: Callable[[str], dict[str, Any]],
) -> tuple[int, dict[str, Any]]:
    """Handle GET /api/projects/{project_id}/task-plans"""
    from urllib.parse import parse_qs

    project_id = str(project_id or "").strip()
    if not project_id:
        return 400, {"error": "missing project_id"}
    if not find_project_cfg(project_id):
        return 404, {"error": "project not found"}
    if task_plan_runtime is None:
        return 503, {"error": "task plan runtime unavailable"}

    qs = parse_qs(query_string or "")
    enabled_raw = _safe_text((qs.get("enabled") or [""])[0], 20).strip().lower()
    enabled_filter: Optional[bool] = None
    if enabled_raw:
        enabled_filter = _coerce_bool(enabled_raw, True)
    limit_s = _safe_text((qs.get("limit") or ["20"])[0], 20).strip()
    try:
        limit = max(1, min(100, int(limit_s)))
    except Exception:
        limit = 20
    items = task_plan_runtime.list(project_id, enabled=enabled_filter, limit=limit)
    return 200, {"items": items, "count": len(items)}


def upsert_task_plan_response(
    *,
    project_id: str,
    body: dict[str, Any],
    task_plan_runtime: "TaskPlanRuntimeRegistry",
    find_project_cfg: Callable[[str], dict[str, Any]],
) -> tuple[int, dict[str, Any]]:
    """Handle POST /api/projects/{project_id}/task-plans"""
    project_id = str(project_id or "").strip()
    if not project_id:
        return 400, {"error": "missing project_id"}
    if not find_project_cfg(project_id):
        return 404, {"error": "project not found"}
    if task_plan_runtime is None:
        return 503, {"error": "task plan runtime unavailable"}

    if not isinstance(body, dict):
        return 400, {"error": "bad json: object required"}
    try:
        item = task_plan_runtime.upsert(project_id, body)
    except ValueError as e:
        return 400, {"error": str(e)}
    except Exception as e:
        return 500, {"error": str(e), "step": "task_plan_upsert"}
    return 200, {
        "ok": True,
        "project_id": project_id,
        "item": {
            "plan_id": str(item.get("plan_id") or ""),
            "enabled": bool(item.get("enabled")),
            "updated_at": str(item.get("updated_at") or ""),
        },
    }


def activate_task_plan_response(
    *,
    project_id: str,
    plan_id: str,
    body: dict[str, Any],
    task_plan_runtime: "TaskPlanRuntimeRegistry",
    find_project_cfg: Callable[[str], dict[str, Any]],
) -> tuple[int, dict[str, Any]]:
    """Handle POST /api/projects/{project_id}/task-plans/{plan_id}/activate"""
    project_id = str(project_id or "").strip()
    plan_id = str(plan_id or "").strip()
    if not project_id or not plan_id:
        return 400, {"error": "missing project_id/plan_id"}
    if not find_project_cfg(project_id):
        return 404, {"error": "project not found"}
    if task_plan_runtime is None:
        return 503, {"error": "task plan runtime unavailable"}

    body_obj = body if isinstance(body, dict) else {}
    batch_id = _safe_text(body_obj.get("batch_id") if "batch_id" in body_obj else body_obj.get("batchId"), 120).strip()
    dry_run = _coerce_bool(body_obj.get("dry_run") if "dry_run" in body_obj else body_obj.get("dryRun"), False)
    try:
        result = task_plan_runtime.activate(
            project_id=project_id,
            plan_id=plan_id,
            batch_id=batch_id,
            dry_run=dry_run,
            trigger="manual",
        )
    except FileNotFoundError:
        return 404, {"error": "task plan not found"}
    except PermissionError as e:
        return 422, {"error": str(e)}
    except RuntimeError as e:
        return 409, {"error": str(e)}
    except ValueError as e:
        return 400, {"error": str(e)}
    except Exception as e:
        return 500, {"error": str(e), "step": "task_plan_activate"}
    return 200, result
