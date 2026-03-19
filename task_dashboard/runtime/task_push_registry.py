# -*- coding: utf-8 -*-
"""
TaskPushRuntimeRegistry - task push execution tracking.

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
    "TaskPushRuntimeRegistry",
    "list_task_push_status_response",
    "handle_task_push_action_response",
]


def __getattr__(name):
    """Lazy resolution of names still defined in server.py (avoids circular imports)."""
    import server
    try:
        return getattr(server, name)
    except AttributeError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _parse_rfc3339_ts(value: Any):
    return __getattr__("_parse_rfc3339_ts")(value)


from task_dashboard.runtime.scheduler_helpers import *  # noqa: F401,F403


class TaskPushRuntimeRegistry:
    """
    Runtime for task-level push dispatch:
    - send-now
    - schedule (max retry rounds default 2)
    - cancel
    - status/query
    """

    def __init__(self, *, store: "RunStore", session_store: SessionStore) -> None:
        self.store = store
        self.session_store = session_store
        self._scheduler: Optional["RunScheduler"] = None
        self._lock = threading.Lock()
        self._jobs: dict[tuple[str, str], dict[str, Any]] = {}
        self._timers: dict[tuple[str, str], threading.Timer] = {}

    def set_scheduler(self, scheduler: Optional["RunScheduler"]) -> None:
        self._scheduler = scheduler

    def shutdown(self) -> None:
        with self._lock:
            timers = list(self._timers.values())
            self._timers.clear()
        for t in timers:
            try:
                t.cancel()
            except Exception:
                pass

    def _job_key(self, project_id: str, job_id: str) -> tuple[str, str]:
        return (str(project_id or "").strip(), str(job_id or "").strip())

    def _job_from_disk(self, project_id: str, job_id: str) -> Optional[dict[str, Any]]:
        path = _task_push_job_path(self.store, project_id, job_id)
        raw = _read_json_file(path)
        if not raw:
            return None
        if str(raw.get("project_id") or "").strip() != str(project_id or "").strip():
            return None
        if str(raw.get("id") or "").strip() != str(job_id or "").strip():
            return None
        return raw

    def _save_job_locked(self, job: dict[str, Any]) -> dict[str, Any]:
        job["updated_at"] = _now_iso()
        pid = str(job.get("project_id") or "").strip()
        jid = str(job.get("id") or "").strip()
        if pid and jid:
            self._jobs[(pid, jid)] = dict(job)
            _write_json_file(_task_push_job_path(self.store, pid, jid), job)
        return job

    def _get_job_locked(self, project_id: str, job_id: str) -> Optional[dict[str, Any]]:
        key = self._job_key(project_id, job_id)
        job = self._jobs.get(key)
        if isinstance(job, dict):
            return dict(job)
        disk = self._job_from_disk(project_id, job_id)
        if not disk:
            return None
        self._jobs[key] = dict(disk)
        return dict(disk)

    def _find_pending_auto_job_locked(
        self,
        project_id: str,
        channel_name: str,
        session_id: str,
        dedupe_key: str,
        *,
        within_seconds: int = 900,
    ) -> Optional[dict[str, Any]]:
        pid = str(project_id or "").strip()
        cname = str(channel_name or "").strip()
        sid = str(session_id or "").strip()
        key = str(dedupe_key or "").strip()
        if not pid or not sid:
            return None
        root = _task_push_state_root(self.store) / pid
        if not root.exists():
            return None
        floor = time.time() - max(60, int(within_seconds or 900))
        rows: list[tuple[float, dict[str, Any]]] = []
        for path in root.glob("*.json"):
            raw = _read_json_file(path)
            if not raw:
                continue
            if str(raw.get("project_id") or "").strip() != pid:
                continue
            if str(raw.get("session_id") or "").strip() != sid:
                continue
            if cname and str(raw.get("channel_name") or "").strip() != cname:
                continue
            status = str(raw.get("status") or "").strip().lower()
            if status not in {"created", "scheduled", "retry_waiting"}:
                continue
            meta = raw.get("run_extra_meta")
            if not _task_push_should_auto_retry(meta):
                continue
            raw_key = _task_push_dedupe_key(meta, str(raw.get("message") or ""))
            if key and raw_key and raw_key != key:
                continue
            ts = (
                _parse_rfc3339_ts(raw.get("updated_at"))
                or _parse_rfc3339_ts(raw.get("created_at"))
                or path.stat().st_mtime
            )
            if ts < floor:
                continue
            rows.append((ts, raw))
        if not rows:
            return None
        rows.sort(key=lambda x: x[0], reverse=True)
        return dict(rows[0][1])

    def _cancel_timer_locked(self, project_id: str, job_id: str) -> None:
        key = self._job_key(project_id, job_id)
        timer = self._timers.pop(key, None)
        if timer is not None:
            try:
                timer.cancel()
            except Exception:
                pass

    def _schedule_timer_locked(self, project_id: str, job_id: str, due_ts: float) -> None:
        key = self._job_key(project_id, job_id)
        self._cancel_timer_locked(project_id, job_id)
        delay = max(0.0, float(due_ts or 0.0) - time.time())
        timer = threading.Timer(delay, self._run_job_due, args=(str(project_id), str(job_id), "scheduled"))
        timer.daemon = True
        self._timers[key] = timer
        timer.start()

    def _summary(self, job: dict[str, Any]) -> dict[str, Any]:
        attempts = job.get("attempts")
        arr = attempts if isinstance(attempts, list) else []
        last = arr[-1] if arr else {}
        status = {
            "job_id": str(job.get("id") or ""),
            "project_id": str(job.get("project_id") or ""),
            "mode": str(job.get("mode") or ""),
            "status": str(job.get("status") or ""),
            "created_at": str(job.get("created_at") or ""),
            "updated_at": str(job.get("updated_at") or ""),
            "scheduled_at": str(job.get("scheduled_at") or ""),
            "next_due_at": str(job.get("next_due_at") or ""),
            "finished_at": str(job.get("finished_at") or ""),
            "canceled_at": str(job.get("canceled_at") or ""),
            "max_attempts": int(job.get("max_attempts") or 0),
            "attempt_count": len(arr),
            "last_result": str(last.get("result") or ""),
            "last_run_id": str(last.get("run_id") or ""),
            "last_error": str(last.get("error") or ""),
            "retryable": str(job.get("status") or "") in {"retry_waiting", "scheduled"},
            "target": {
                "channel_name": str(job.get("channel_name") or ""),
                "session_id": str(job.get("session_id") or ""),
            },
        }
        return {"status": status, "attempts": arr}

    def get_status(self, project_id: str, job_id: str) -> Optional[dict[str, Any]]:
        with self._lock:
            job = self._get_job_locked(project_id, job_id)
        if not job:
            return None
        return self._summary(job)

    def list_status(self, project_id: str, limit: int = 20) -> list[dict[str, Any]]:
        pid = str(project_id or "").strip()
        root = _task_push_state_root(self.store) / pid
        if not root.exists():
            return []
        rows: list[tuple[float, dict[str, Any]]] = []
        for p in root.glob("*.json"):
            raw = _read_json_file(p)
            if not raw:
                continue
            if str(raw.get("project_id") or "").strip() != pid:
                continue
            ts = _parse_rfc3339_ts(raw.get("updated_at")) or p.stat().st_mtime
            rows.append((ts, raw))
        rows.sort(key=lambda x: x[0], reverse=True)
        out: list[dict[str, Any]] = []
        for _, job in rows[: max(1, min(int(limit or 20), 100))]:
            out.append(self._summary(job))
        return out

    def send_now(
        self,
        *,
        project_id: str,
        channel_name: str,
        session_id: str,
        message: str,
        profile_label: str = "",
        run_extra_meta: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        pid = str(project_id or "").strip()
        jid = _task_push_new_job_id()
        now = _now_iso()
        clean_meta = _sanitize_run_extra_meta(run_extra_meta)
        auto_retry = _task_push_should_auto_retry(clean_meta)
        dedupe_key = _task_push_dedupe_key(clean_meta, message)
        if auto_retry:
            with self._lock:
                pending = self._find_pending_auto_job_locked(
                    pid,
                    str(channel_name or "").strip(),
                    str(session_id or "").strip(),
                    dedupe_key,
                )
            if isinstance(pending, dict):
                out = self._summary(pending)
                status_obj = out.get("status")
                if isinstance(status_obj, dict):
                    status_obj["dedupe_hit"] = True
                    status_obj["dedupe_reason"] = "pending_auto_inspection_job_exists"
                return out
        job = {
            "id": jid,
            "project_id": pid,
            "mode": "immediate",
            "status": "created",
            "channel_name": str(channel_name or "").strip(),
            "session_id": str(session_id or "").strip(),
            "message": str(message or ""),
            "profile_label": str(profile_label or "").strip(),
            "max_attempts": 2 if auto_retry else 1,
            "retry_interval_seconds": 90 if auto_retry else 60,
            "scheduled_at": now,
            "next_due_at": now,
            "created_at": now,
            "updated_at": now,
            "finished_at": "",
            "canceled_at": "",
            "attempts": [],
            "run_extra_meta": clean_meta,
        }
        with self._lock:
            self._save_job_locked(job)
        self._run_job_due(pid, jid, "immediate")
        status = self.get_status(pid, jid)
        return status or {"status": {"job_id": jid, "project_id": pid, "status": "error"}, "attempts": []}

    def schedule_send(
        self,
        *,
        project_id: str,
        channel_name: str,
        session_id: str,
        message: str,
        scheduled_at: str = "",
        retry_interval_seconds: int = 60,
        max_attempts: int = 2,
        profile_label: str = "",
        run_extra_meta: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        pid = str(project_id or "").strip()
        sid = str(session_id or "").strip()
        jid = _task_push_new_job_id()
        now_ts = time.time()
        due_ts = _parse_rfc3339_ts(scheduled_at) if scheduled_at else 0.0
        if due_ts <= 0:
            due_ts = now_ts
        max_try = max(1, min(int(max_attempts or 2), 2))
        interval_s = max(10, int(retry_interval_seconds or 60))
        job = {
            "id": jid,
            "project_id": pid,
            "mode": "scheduled",
            "status": "scheduled",
            "channel_name": str(channel_name or "").strip(),
            "session_id": sid,
            "message": str(message or ""),
            "profile_label": str(profile_label or "").strip(),
            "max_attempts": max_try,
            "retry_interval_seconds": interval_s,
            "scheduled_at": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(due_ts)),
            "next_due_at": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(due_ts)),
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
            "finished_at": "",
            "canceled_at": "",
            "attempts": [],
            "run_extra_meta": _sanitize_run_extra_meta(run_extra_meta),
        }
        with self._lock:
            self._save_job_locked(job)
            self._schedule_timer_locked(pid, jid, due_ts)
        return self.get_status(pid, jid) or {"status": {"job_id": jid, "project_id": pid, "status": "error"}, "attempts": []}

    def cancel(self, project_id: str, job_id: str, reason: str = "user_cancel") -> Optional[dict[str, Any]]:
        pid = str(project_id or "").strip()
        jid = str(job_id or "").strip()
        with self._lock:
            job = self._get_job_locked(pid, jid)
            if not job:
                return None
            st = str(job.get("status") or "")
            if st in {"dispatched", "error", "exhausted", "canceled", "skipped_active"}:
                return self._summary(job)
            self._cancel_timer_locked(pid, jid)
            now = _now_iso()
            job["status"] = "canceled"
            job["canceled_at"] = now
            job["finished_at"] = now
            job["next_due_at"] = ""
            if reason:
                job["cancel_reason"] = str(reason)
            self._save_job_locked(job)
            return self._summary(job)

    def _run_job_due(self, project_id: str, job_id: str, trigger: str) -> None:
        pid = str(project_id or "").strip()
        jid = str(job_id or "").strip()
        with self._lock:
            job = self._get_job_locked(pid, jid)
            if not job:
                return
            st = str(job.get("status") or "").strip().lower()
            if st in {"dispatched", "canceled", "error", "exhausted", "skipped_active"}:
                self._cancel_timer_locked(pid, jid)
                return
            self._cancel_timer_locked(pid, jid)

            attempts = job.get("attempts")
            arr = attempts if isinstance(attempts, list) else []
            attempt_no = len(arr) + 1
            due_at = str(job.get("next_due_at") or job.get("scheduled_at") or _now_iso())
            active = _task_push_active_state(self.store, pid, str(job.get("session_id") or ""))
            item: dict[str, Any] = {
                "attempt": attempt_no,
                "trigger": str(trigger or "scheduled"),
                "due_at": due_at,
                "attempted_at": _now_iso(),
                "active": bool(active.get("active")),
                "active_status": str(active.get("status") or ""),
                "active_run_id": str(active.get("run_id") or ""),
                "result": "",
                "run_id": "",
                "error": "",
            }

            max_attempts = max(1, min(int(job.get("max_attempts") or 2), 2))
            retry_interval_s = max(10, int(job.get("retry_interval_seconds") or 60))
            mode = str(job.get("mode") or "scheduled")

            if item["active"]:
                item["result"] = "skipped_active"
                arr.append(item)
                job["attempts"] = arr
                if mode == "scheduled" and attempt_no < max_attempts:
                    next_due = _iso_after_s(retry_interval_s)
                    job["status"] = "retry_waiting"
                    job["next_due_at"] = next_due
                    self._save_job_locked(job)
                    due_ts = _parse_rfc3339_ts(next_due)
                    self._schedule_timer_locked(pid, jid, due_ts if due_ts > 0 else time.time() + retry_interval_s)
                    return
                run_extra_meta = job.get("run_extra_meta")
                if mode == "immediate" and _task_push_should_auto_retry(run_extra_meta) and attempt_no < max_attempts:
                    next_due = _iso_after_s(retry_interval_s)
                    job["status"] = "retry_waiting"
                    job["next_due_at"] = next_due
                    self._save_job_locked(job)
                    due_ts = _parse_rfc3339_ts(next_due)
                    self._schedule_timer_locked(pid, jid, due_ts if due_ts > 0 else time.time() + retry_interval_s)
                    return
                if mode == "immediate":
                    # Immediate mode does not create a retry plan. Expose a terminal status to
                    # avoid misleading "retry_waiting + empty next_due_at" combinations.
                    job["status"] = "skipped_active"
                    job["finished_at"] = _now_iso()
                    job["next_due_at"] = ""
                else:
                    job["status"] = "exhausted"
                    job["finished_at"] = _now_iso()
                    job["next_due_at"] = ""
                self._save_job_locked(job)
                return

            try:
                sid = str(job.get("session_id") or "").strip()
                ctype = _resolve_cli_type_for_session(self.session_store, pid, sid, "codex")
                extra = _sanitize_run_extra_meta(job.get("run_extra_meta"))
                message = str(job.get("message") or "")
                message, extra = _apply_plan_first_to_message(message, extra)
                extra["trigger_type"] = "task_push_now" if mode == "immediate" else "task_push_schedule"
                extra["task_push_job_id"] = jid
                extra["task_push_attempt"] = attempt_no
                run = self.store.create_run(
                    pid,
                    str(job.get("channel_name") or "").strip(),
                    sid,
                    message,
                    profile_label=str(job.get("profile_label") or "").strip(),
                    cli_type=ctype,
                    sender_type="system",
                    sender_id="ccb",
                    sender_name="CCB Runtime",
                    extra_meta=extra,
                )
                _enqueue_run_for_dispatch(
                    self.store,
                    str(run.get("id") or "").strip(),
                    sid,
                    ctype,
                    self._scheduler,
                )
                item["result"] = "dispatched"
                item["run_id"] = str(run.get("id") or "")
                arr.append(item)
                job["attempts"] = arr
                job["status"] = "dispatched"
                job["finished_at"] = _now_iso()
                job["next_due_at"] = ""
                self._save_job_locked(job)
            except Exception as e:
                err = f"{type(e).__name__}: {e}"
                item["result"] = "dispatch_error"
                item["error"] = err
                arr.append(item)
                job["attempts"] = arr
                if mode == "scheduled" and attempt_no < max_attempts:
                    next_due = _iso_after_s(retry_interval_s)
                    job["status"] = "retry_waiting"
                    job["next_due_at"] = next_due
                    job["last_error"] = err
                    self._save_job_locked(job)
                    due_ts = _parse_rfc3339_ts(next_due)
                    self._schedule_timer_locked(pid, jid, due_ts if due_ts > 0 else time.time() + retry_interval_s)
                    return
                job["status"] = "error"
                job["last_error"] = err
                job["finished_at"] = _now_iso()
                job["next_due_at"] = ""
                self._save_job_locked(job)


# =============================================================================
# Route handlers (extracted from server.py)
# =============================================================================

from urllib.parse import parse_qs


def list_task_push_status_response(
    *,
    project_id: str,
    query_string: str,
    task_push_runtime: "TaskPushRuntimeRegistry",
    safe_text: Callable[[Any, int], str],
) -> tuple[int, dict[str, Any]]:
    """Handle GET /api/projects/{project_id}/task-push.

    Query params:
    - job_id / jobId: Get single job status
    - limit: List jobs with limit (default 20, max 100)

    Returns (status_code, response_dict).
    """
    pid = str(project_id or "").strip()
    if not pid:
        return 400, {"error": "missing project_id"}

    qs = parse_qs(query_string or "")
    job_id = safe_text((qs.get("job_id") or qs.get("jobId") or [""])[0], 120).strip()
    limit_s = safe_text((qs.get("limit") or ["20"])[0], 20).strip()
    try:
        limit = max(1, min(100, int(limit_s)))
    except Exception:
        limit = 20

    if job_id:
        item = task_push_runtime.get_status(pid, job_id)
        if not item:
            return 404, {"error": "job not found"}
        return 200, {"item": item}

    items = task_push_runtime.list_status(pid, limit=limit)
    return 200, {"items": items, "count": len(items)}


def handle_task_push_action_response(
    *,
    project_id: str,
    action: str,
    body: dict[str, Any],
    task_push_runtime: "TaskPushRuntimeRegistry",
    session_store: Any,
    safe_text: Callable[[Any, int], str],
    coerce_bool: Callable[[Any, bool], bool],
    coerce_int: Callable[[Any, int], int],
    looks_like_uuid: Callable[[str], bool],
    resolve_primary_target_by_channel: Callable[[str, str], Optional[dict[str, Any]]],
) -> tuple[int, dict[str, Any]]:
    """Handle POST /api/projects/{project_id}/task-push/{action}.

    Actions:
    - cancel: Cancel a scheduled job
    - send-now: Send message immediately
    - schedule: Schedule message for later

    Returns (status_code, response_dict).
    """
    pid = str(project_id or "").strip()
    if not pid:
        return 400, {"error": "missing project_id"}

    action = str(action or "").strip().lower()

    if action == "cancel":
        job_id = safe_text(body.get("job_id") if "job_id" in body else body.get("jobId"), 120).strip()
        if not job_id:
            return 400, {"error": "missing job_id"}
        reason = safe_text(body.get("reason"), 200).strip() or "user_cancel"
        item = task_push_runtime.cancel(pid, job_id, reason=reason)
        if not item:
            return 404, {"error": "job not found"}
        return 200, {"ok": True, "project_id": pid, "item": item}

    channel_name = safe_text(
        body.get("channel_name") if "channel_name" in body else body.get("channelName"),
        200,
    ).strip()
    session_id = safe_text(
        body.get("session_id") if "session_id" in body else body.get("sessionId"),
        80,
    ).strip()
    message = safe_text(body.get("message"), 20_000).strip()
    profile_label = safe_text(
        body.get("profile_label") if "profile_label" in body else body.get("profileLabel"),
        80,
    ).strip()
    prefer_primary_session = coerce_bool(
        body.get("prefer_primary_session")
        if "prefer_primary_session" in body
        else body.get("preferPrimarySession"),
        False,
    )
    raw_extra = body.get("run_extra_meta")
    if raw_extra is None:
        raw_extra = body.get("runExtraMeta")
    run_extra_meta = raw_extra if isinstance(raw_extra, dict) else {}
    structured_extra = _extract_run_extra_fields(body)
    if structured_extra:
        run_extra_meta = {**run_extra_meta, **structured_extra}
    if "plan_first" in body or "planFirst" in body:
        run_extra_meta["plan_first"] = coerce_bool(
            body.get("plan_first") if "plan_first" in body else body.get("planFirst"),
            False,
        )
    if "plan_phase" in body or "planPhase" in body:
        run_extra_meta["plan_phase"] = safe_text(
            body.get("plan_phase") if "plan_phase" in body else body.get("planPhase"),
            40,
        ).strip().lower()

    if session_id and not looks_like_uuid(session_id):
        return 400, {"error": "invalid session_id"}
    if session_id and not channel_name:
        srow = session_store.get_session(session_id)
        if srow:
            channel_name = str(srow.get("channel_name") or "").strip()
    if channel_name and not session_id:
        target = resolve_primary_target_by_channel(pid, channel_name)
        if target:
            session_id = str(target.get("session_id") or "").strip()
    if channel_name and prefer_primary_session:
        target = resolve_primary_target_by_channel(pid, channel_name)
        if target:
            channel_name = str(target.get("channel_name") or channel_name).strip() or channel_name
            session_id = str(target.get("session_id") or session_id).strip() or session_id
    if not channel_name or not session_id:
        return 400, {"error": "missing target channel/session"}
    if not message:
        return 400, {"error": "missing message"}

    if action == "send-now":
        item = task_push_runtime.send_now(
            project_id=pid,
            channel_name=channel_name,
            session_id=session_id,
            message=message,
            profile_label=profile_label,
            run_extra_meta=run_extra_meta,
        )
        return 200, {"ok": True, "project_id": pid, "item": item}

    if action == "schedule":
        scheduled_at = safe_text(
            body.get("scheduled_at")
            if "scheduled_at" in body
            else body.get("scheduledAt") or body.get("due_at") or body.get("dueAt"),
            80,
        ).strip()
        retry_interval_seconds = coerce_int(
            body.get("retry_interval_seconds")
            if "retry_interval_seconds" in body
            else body.get("retryIntervalSeconds"),
            60,
        )
        max_attempts = coerce_int(
            body.get("max_attempts") if "max_attempts" in body else body.get("maxAttempts"),
            2,
        )
        item = task_push_runtime.schedule_send(
            project_id=pid,
            channel_name=channel_name,
            session_id=session_id,
            message=message,
            scheduled_at=scheduled_at,
            retry_interval_seconds=retry_interval_seconds,
            max_attempts=max_attempts,
            profile_label=profile_label,
            run_extra_meta=run_extra_meta,
        )
        return 200, {"ok": True, "project_id": pid, "item": item}

    return 400, {"error": "unsupported action"}
