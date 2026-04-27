# -*- coding: utf-8 -*-
"""
ProjectSchedulerRuntimeRegistry - project-level scheduling.

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

from task_dashboard.config import load_dashboard_config
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
    "ProjectSchedulerRuntimeRegistry",
]


def __getattr__(name):
    """Lazy resolution of names still defined in server.py (avoids circular imports)."""
    import server
    try:
        return getattr(server, name)
    except AttributeError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


from task_dashboard.runtime.scheduler_helpers import *  # noqa: F401,F403


def _build_project_scheduler_status(*args, **kwargs):
    return __getattr__("_build_project_scheduler_status")(*args, **kwargs)


def _ensure_auto_scheduler_status_shape(*args, **kwargs):
    return __getattr__("_ensure_auto_scheduler_status_shape")(*args, **kwargs)


def _load_project_scheduler_contract_config(*args, **kwargs):
    return __getattr__("_load_project_scheduler_contract_config")(*args, **kwargs)


def _load_project_scheduler_runtime_snapshot(*args, **kwargs):
    return __getattr__("_load_project_scheduler_runtime_snapshot")(*args, **kwargs)


def _save_project_scheduler_runtime_snapshot(*args, **kwargs):
    return __getattr__("_save_project_scheduler_runtime_snapshot")(*args, **kwargs)


def _load_project_auto_inspection_config(*args, **kwargs):
    return __getattr__("_load_project_auto_inspection_config")(*args, **kwargs)


def _collect_auto_inspection_candidates(*args, **kwargs):
    return __getattr__("_collect_auto_inspection_candidates")(*args, **kwargs)


def _with_local_config_enabled(*args, **kwargs):
    return __getattr__("_with_local_config_enabled")(*args, **kwargs)


def _resolve_channel_primary_session_id(*args, **kwargs):
    return __getattr__("_resolve_channel_primary_session_id")(*args, **kwargs)


def _task_push_active_state(*args, **kwargs):
    return __getattr__("_task_push_active_state")(*args, **kwargs)


def _resolve_cli_type_for_session(*args, **kwargs):
    return __getattr__("_resolve_cli_type_for_session")(*args, **kwargs)


def _project_channel_cli_type(*args, **kwargs):
    return __getattr__("_project_channel_cli_type")(*args, **kwargs)


def _enqueue_run_execution(*args, **kwargs):
    return __getattr__("_enqueue_run_execution")(*args, **kwargs)


def _resolve_master_control_target(*args, **kwargs):
    return __getattr__("_resolve_master_control_target")(*args, **kwargs)


def _parse_rfc3339_ts(*args, **kwargs):
    return __getattr__("_parse_rfc3339_ts")(*args, **kwargs)


def _normalize_task_path_identity(*args, **kwargs):
    return __getattr__("_normalize_task_path_identity")(*args, **kwargs)


def _promote_auto_inspection_task_to_in_progress(*args, **kwargs):
    return __getattr__("_promote_auto_inspection_task_to_in_progress")(*args, **kwargs)


def _run_project_scheduler_once_bridge(*args, **kwargs):
    return __getattr__("_run_project_scheduler_once_bridge")(*args, **kwargs)


class ProjectSchedulerRuntimeRegistry:
    def __init__(self, *, store: "RunStore", session_store: Optional[SessionStore] = None) -> None:
        self.store = store
        self.session_store = session_store
        self._scheduler: Optional["RunScheduler"] = None
        self._lock = threading.Lock()
        self._workers: dict[str, dict[str, Any]] = {}

    def set_scheduler(self, scheduler: Optional["RunScheduler"]) -> None:
        self._scheduler = scheduler

    def _worker_runtime_flags(self, project_id: str) -> dict[str, Any]:
        pid = str(project_id or "").strip()
        with self._lock:
            w = dict(self._workers.get(pid) or {})
        if not w:
            return {"worker_running": False}
        return {
            "worker_running": bool(w.get("running")),
            "scheduler_state": str(w.get("scheduler_state") or ""),
            "scheduler_last_tick_at": str(w.get("scheduler_last_tick_at") or ""),
            "scheduler_last_error": str(w.get("scheduler_last_error") or ""),
            "reminder_state": str(w.get("reminder_state") or ""),
            "reminder_last_tick_at": str(w.get("reminder_last_tick_at") or ""),
            "reminder_next_due_at": str(w.get("reminder_next_due_at") or ""),
            "reminder_last_error": str(w.get("reminder_last_error") or ""),
            "reminder_records": _normalize_auto_inspection_reminder_records(w.get("reminder_records")),
            "inspection_records": _normalize_inspection_records(w.get("inspection_records")),
            "auto_inspection_state": str(w.get("auto_inspection_state") or ""),
            "auto_inspection_last_tick_at": str(w.get("auto_inspection_last_tick_at") or ""),
            "auto_inspection_last_run_id": str(w.get("auto_inspection_last_run_id") or ""),
            "auto_inspection_last_job_id": str(w.get("auto_inspection_last_job_id") or ""),
            "auto_inspection_next_due_at": str(w.get("auto_inspection_next_due_at") or ""),
            "auto_inspection_last_error": str(w.get("auto_inspection_last_error") or ""),
            "auto_inspection_last_candidate_count": int(w.get("auto_inspection_last_candidate_count") or 0),
            "auto_inspection_last_target_sources": str(w.get("auto_inspection_last_target_sources") or ""),
            "auto_inspection_last_selected_tasks": _normalize_auto_inspection_selected_tasks(
                w.get("auto_inspection_last_selected_tasks")
            ),
            "auto_inspection_last_task_id": str(w.get("auto_inspection_last_task_id") or ""),
            "auto_inspection_execution_state": str(w.get("auto_inspection_execution_state") or ""),
            "auto_inspection_gate_last_reason": str(w.get("auto_inspection_gate_last_reason") or ""),
            "auto_inspection_gate_last_run_id": str(w.get("auto_inspection_gate_last_run_id") or ""),
            "auto_inspection_gate_last_checked_at": str(w.get("auto_inspection_gate_last_checked_at") or ""),
            "auto_inspection_advice_only_streak": int(w.get("auto_inspection_advice_only_streak") or 0),
            "auto_inspection_escalation_level": int(w.get("auto_inspection_escalation_level") or 0),
            "auto_inspection_gate_action": str(w.get("auto_inspection_gate_action") or ""),
            "auto_inspection_gate_action_run_id": str(w.get("auto_inspection_gate_action_run_id") or ""),
            "guard_policy": dict(w.get("guard_policy") or {}),
            "guard_events": _normalize_guard_runtime_events(w.get("guard_events")),
            "guard_stats": _normalize_guard_runtime_stats(w.get("guard_stats")),
            "guard_last_tick_at": str(w.get("guard_last_tick_at") or ""),
        }

    def get_status(self, project_id: str) -> dict[str, Any]:
        return _ensure_auto_scheduler_status_shape(
            _build_project_scheduler_status(
            self.store,
            project_id,
            runtime_flags=self._worker_runtime_flags(project_id),
            )
        )

    def _set_worker_fields(self, project_id: str, **kwargs: Any) -> None:
        pid = str(project_id or "").strip()
        if not pid:
            return
        with self._lock:
            w = self._workers.get(pid)
            if not isinstance(w, dict):
                return
            for k, v in kwargs.items():
                w[k] = v
            self._workers[pid] = w

    def _append_auto_inspection_reminder_record(self, project_id: str, record: dict[str, Any]) -> None:
        pid = str(project_id or "").strip()
        if not pid:
            return
        item = _normalize_auto_inspection_reminder_record(record)
        if not item:
            return
        disk = _load_project_scheduler_runtime_snapshot(self.store, pid)
        cfg = _load_project_auto_inspection_config(pid)
        default_task_id = _normalize_inspection_task_id(
            record.get("inspection_task_id")
            if isinstance(record, dict)
            else "",
            default=str(cfg.get("active_inspection_task_id") or _DEFAULT_INSPECTION_TASK_ID),
        ) or _DEFAULT_INSPECTION_TASK_ID
        item["inspection_task_id"] = default_task_id
        default_object_key = _safe_text(record.get("object_key"), 120).strip()
        if not default_object_key:
            first_source = _safe_text(record.get("target_source"), 80).strip().lower().replace("-", "_")
            default_object_key = _auto_inspection_object_key_for_target(first_source)
        item_record = _inspection_record_from_reminder_record(
            item,
            index=0,
            default_object_key=default_object_key,
            default_inspection_task_id=default_task_id,
        )
        with self._lock:
            worker = self._workers.get(pid)
            current_raw: list[Any] = []
            current_inspection_raw: list[Any] = []
            if isinstance(worker, dict):
                current_raw = list(worker.get("reminder_records") or [])
                current_inspection_raw = list(worker.get("inspection_records") or [])
            if not current_raw:
                current_raw = list(disk.get("reminder_records") or [])
            if not current_inspection_raw:
                current_inspection_raw = list(disk.get("inspection_records") or [])
            merged_reminders = [item] + _normalize_auto_inspection_reminder_records(current_raw)
            merged_reminders = merged_reminders[:_AUTO_INSPECTION_RECORD_LIMIT]
            fallback_records = (
                _inspection_records_from_reminder_records(
                    current_raw,
                    default_inspection_task_id=default_task_id,
                )
                if not current_inspection_raw
                else _normalize_inspection_records(current_inspection_raw)
            )
            merged_inspections = [item_record] + fallback_records
            merged_inspections = _normalize_inspection_records(merged_inspections)[:_AUTO_INSPECTION_RECORD_LIMIT]
            if isinstance(worker, dict):
                worker["reminder_records"] = merged_reminders
                worker["inspection_records"] = merged_inspections
                self._workers[pid] = worker
        _save_project_scheduler_runtime_snapshot(
            self.store,
            pid,
            {
                "reminder_records": merged_reminders,
                "inspection_records": merged_inspections,
            },
        )

    def _dispatch_auto_inspection_gate_followup(
        self,
        *,
        project_id: str,
        target_channel: str,
        target_session_id: str,
        message: str,
        source_run_id: str,
        action: str,
    ) -> str:
        pid = str(project_id or "").strip()
        channel_name = str(target_channel or "").strip()
        session_id = str(target_session_id or "").strip()
        if not (pid and channel_name and session_id and str(message or "").strip()):
            return ""
        try:
            fallback_cli = _project_channel_cli_type(pid, channel_name)
            if self.session_store is None:
                cli_type = fallback_cli or "codex"
            else:
                cli_type = _resolve_cli_type_for_session(self.session_store, pid, session_id, fallback_cli or "codex")
            run = self.store.create_run(
                pid,
                channel_name,
                session_id,
                str(message or "").strip(),
                profile_label="ccb",
                cli_type=cli_type,
                sender_type="system",
                sender_id="auto_inspection_gate",
                sender_name="系统自动巡查门禁",
                extra_meta={
                    "trigger_type": "project_auto_inspection_gate",
                    "execution_mode": "auto_inspection_gate",
                    "auto_inspection_gate_action": action,
                    "source_run_id": str(source_run_id or "").strip(),
                },
            )
            run_id = str(run.get("id") or "").strip()
            if run_id:
                _enqueue_run_execution(self.store, run_id, session_id, cli_type, self._scheduler)
            return run_id
        except Exception:
            return ""

    def _evaluate_previous_auto_inspection_gate(self, project_id: str, cfg: dict[str, Any]) -> None:
        pid = str(project_id or "").strip()
        if not pid:
            return
        runtime_disk = _load_project_scheduler_runtime_snapshot(self.store, pid)
        with self._lock:
            worker = dict(self._workers.get(pid) or {})
        prev_run_id = str(worker.get("auto_inspection_last_run_id") or runtime_disk.get("auto_inspection_last_run_id") or "").strip()
        if not prev_run_id:
            return
        checked_run_id = str(
            worker.get("auto_inspection_gate_last_run_id") or runtime_disk.get("auto_inspection_gate_last_run_id") or ""
        ).strip()
        if checked_run_id == prev_run_id:
            return
        verdict = _classify_auto_inspection_execution_result(self.store, prev_run_id)
        state = str(verdict.get("state") or "").strip()
        reason = str(verdict.get("reason") or "").strip()
        if state == "pending":
            return
        streak_base = int(worker.get("auto_inspection_advice_only_streak") or runtime_disk.get("auto_inspection_advice_only_streak") or 0)
        level_base = int(worker.get("auto_inspection_escalation_level") or runtime_disk.get("auto_inspection_escalation_level") or 0)
        streak_now = streak_base + 1 if state == "advice_only" else 0
        level_now = level_base if state == "advice_only" else 0
        checked_at = _now_iso()
        patch: dict[str, Any] = {
            "auto_inspection_execution_state": state or "error",
            "auto_inspection_gate_last_reason": reason,
            "auto_inspection_gate_last_run_id": prev_run_id,
            "auto_inspection_gate_last_checked_at": checked_at,
            "auto_inspection_advice_only_streak": streak_now,
            "auto_inspection_escalation_level": level_now,
        }

        # 记录上一轮实际执行判定结果
        if state in {"effective", "advice_only", "error"}:
            self._append_auto_inspection_reminder_record(
                pid,
                {
                    "created_at": checked_at,
                    "status": state,
                    "message_summary": f"自动巡查门禁判定：{state}",
                    "target_task_path": "",
                    "target_channel": str(cfg.get('channel_name') or ""),
                    "run_id": prev_run_id,
                    "skip_reason": reason if state != "effective" else "",
                },
            )

        if state == "advice_only":
            cfg_channel = str(cfg.get("channel_name") or "").strip()
            cfg_session = str(cfg.get("session_id") or "").strip()
            action = ""
            target_channel = cfg_channel
            target_session = cfg_session
            message = ""
            if streak_now >= _AUTO_INSPECTION_GATE_L2_THRESHOLD and level_base < 2:
                master_target = _resolve_master_control_target(pid) or {}
                mt_channel = str(master_target.get("channel_name") or "").strip()
                mt_session = str(master_target.get("session_id") or "").strip()
                if mt_channel and mt_session:
                    target_channel = mt_channel
                    target_session = mt_session
                action = "escalate_master"
                level_now = 2
                message = (
                    "【自动巡查升级总控】检测到连续3轮 advice_only（仅建议未执行）。\n"
                    f"- project_id: {pid}\n"
                    f"- source_run_id: {prev_run_id}\n"
                    f"- reason: {reason or 'missing_execution_evidence'}\n"
                    "请总控介入并要求本轮先执行再回执。"
                )
            elif streak_now >= _AUTO_INSPECTION_GATE_L1_THRESHOLD and level_base < 1:
                action = "remedy_execute"
                level_now = 1
                message = (
                    "【自动巡查补执行催办】检测到连续2轮 advice_only（仅建议未执行）。\n"
                    f"- project_id: {pid}\n"
                    f"- source_run_id: {prev_run_id}\n"
                    f"- reason: {reason or 'missing_execution_evidence'}\n"
                    "请立即执行本轮动作并回执执行证据（run_id/命令/改动文件/接口结果）。"
                )
            if action and target_channel and target_session:
                action_run_id = self._dispatch_auto_inspection_gate_followup(
                    project_id=pid,
                    target_channel=target_channel,
                    target_session_id=target_session,
                    message=message,
                    source_run_id=prev_run_id,
                    action=action,
                )
                if action_run_id:
                    patch["auto_inspection_gate_action"] = action
                    patch["auto_inspection_gate_action_run_id"] = action_run_id
                    patch["auto_inspection_escalation_level"] = level_now
                    self._append_auto_inspection_reminder_record(
                        pid,
                        {
                            "created_at": checked_at,
                            "status": "dispatched",
                            "message_summary": f"自动巡查门禁补救触发：{action}",
                            "target_task_path": "",
                            "target_channel": target_channel,
                            "run_id": action_run_id,
                            "skip_reason": "",
                        },
                    )
                else:
                    patch["auto_inspection_gate_action"] = f"{action}_failed"
                    patch["auto_inspection_escalation_level"] = level_now
                    self._append_auto_inspection_reminder_record(
                        pid,
                        {
                            "created_at": checked_at,
                            "status": "error",
                            "message_summary": f"自动巡查门禁补救触发失败：{action}",
                            "target_task_path": "",
                            "target_channel": target_channel,
                            "run_id": "",
                            "skip_reason": f"{action}_dispatch_failed",
                        },
                    )
        self._set_worker_fields(pid, **patch)
        _save_project_scheduler_runtime_snapshot(self.store, pid, patch)

    def _auto_inspection_worker_interval_s(self, cfg: dict[str, Any]) -> Optional[int]:
        acfg = _load_project_auto_inspection_config(str(cfg.get("project_id") or ""))
        if not bool(acfg.get("enabled")):
            return None
        interval_m = acfg.get("interval_minutes")
        if interval_m is None:
            return 30 * 60
        try:
            return max(60, int(interval_m) * 60)
        except Exception:
            return 30 * 60

    def _effective_worker_interval_s(self, project_id: str) -> int:
        pid = str(project_id or "").strip()
        cfg = _load_project_scheduler_contract_config(pid)
        scfg = cfg.get("scheduler") if isinstance(cfg.get("scheduler"), dict) else {}
        scheduler_interval_s: Optional[int] = None
        if bool(scfg.get("enabled")):
            scheduler_interval_s = max(60, int(scfg.get("scan_interval_seconds") or 300))
        auto_inspection_interval_s = self._auto_inspection_worker_interval_s({"project_id": pid})
        candidates = [x for x in (scheduler_interval_s, auto_inspection_interval_s) if isinstance(x, int) and x > 0]
        if not candidates:
            return 300
        return min(candidates)

    def _sync_auto_inspection_runtime_hints(
        self,
        project_id: str,
        *,
        auto_inspection_cfg: Optional[dict[str, Any]] = None,
    ) -> None:
        pid = str(project_id or "").strip()
        cfg = auto_inspection_cfg if isinstance(auto_inspection_cfg, dict) else _load_project_auto_inspection_config(pid)
        enabled = bool(cfg.get("enabled"))
        ready = bool(cfg.get("ready"))
        interval_s = max(60, int(cfg.get("interval_minutes") or 30) * 60) if enabled else 0

        with self._lock:
            w = self._workers.get(pid)
            if not isinstance(w, dict):
                return
            current_next = str(w.get("auto_inspection_next_due_at") or "").strip()
            if not enabled:
                w["auto_inspection_state"] = "disabled"
                w["auto_inspection_next_due_at"] = ""
            elif not ready:
                w["auto_inspection_state"] = "invalid_config"
                w["auto_inspection_next_due_at"] = ""
            else:
                if str(w.get("auto_inspection_state") or "") not in {"running", "error"}:
                    w["auto_inspection_state"] = "idle"
                due_ts = _parse_rfc3339_ts(current_next) if current_next else 0.0
                if due_ts <= 0:
                    w["auto_inspection_next_due_at"] = _iso_after_s(interval_s)
            self._workers[pid] = w
            patch = {
                "auto_inspection_state": str(w.get("auto_inspection_state") or ""),
                "auto_inspection_next_due_at": str(w.get("auto_inspection_next_due_at") or ""),
            }
        _save_project_scheduler_runtime_snapshot(self.store, pid, patch)

    def _tick_auto_inspection_once(self, project_id: str) -> None:
        pid = str(project_id or "").strip()
        if not pid:
            return
        cfg = _load_project_auto_inspection_config(pid)
        enabled = bool(cfg.get("enabled"))
        ready_raw = cfg.get("ready")
        ready = bool(ready_raw) if isinstance(ready_raw, bool) else bool(
            enabled
            and str(cfg.get("channel_name") or "").strip()
            and str(cfg.get("session_id") or "").strip()
        )
        if not enabled:
            self._set_worker_fields(pid, auto_inspection_state="disabled", auto_inspection_next_due_at="")
            _save_project_scheduler_runtime_snapshot(
                self.store,
                pid,
                {"auto_inspection_state": "disabled", "auto_inspection_next_due_at": ""},
            )
            return
        if not ready:
            self._set_worker_fields(
                pid,
                auto_inspection_state="invalid_config",
                auto_inspection_next_due_at="",
            )
            _save_project_scheduler_runtime_snapshot(
                self.store,
                pid,
                {
                    "auto_inspection_state": "invalid_config",
                    "auto_inspection_next_due_at": "",
                    "auto_inspection_last_error": "",
                },
            )
            return

        fallback_task = _build_default_auto_inspection_task(
            enabled=bool(cfg.get("enabled")),
            channel_name=str(cfg.get("channel_name") or ""),
            session_id=str(cfg.get("session_id") or ""),
            interval_minutes=(int(cfg.get("interval_minutes")) if cfg.get("interval_minutes") is not None else None),
            prompt_template=str(cfg.get("prompt_template") or ""),
            inspection_targets=_normalize_inspection_targets(cfg.get("inspection_targets"), default=[]),
            auto_inspections=_normalize_auto_inspections(
                cfg.get("auto_inspections"),
                fallback_targets=_normalize_inspection_targets(cfg.get("inspection_targets"), default=[]),
            ),
        )
        inspection_tasks = _normalize_auto_inspection_tasks(
            cfg.get("inspection_tasks"),
            defaults=fallback_task,
            fallback_single_task=fallback_task,
            has_explicit_field=("inspection_tasks" in cfg or "inspectionTasks" in cfg),
        )
        active_task = _select_active_auto_inspection_task(
            inspection_tasks,
            active_task_id_hint=str(cfg.get("active_inspection_task_id") or ""),
        )
        if not isinstance(active_task, dict):
            self._set_worker_fields(
                pid,
                auto_inspection_state="invalid_config",
                auto_inspection_next_due_at="",
            )
            _save_project_scheduler_runtime_snapshot(
                self.store,
                pid,
                {
                    "auto_inspection_state": "invalid_config",
                    "auto_inspection_next_due_at": "",
                    "auto_inspection_last_error": "ValueError: no_active_inspection_task",
                },
            )
            return
        inspection_task_id = _normalize_inspection_task_id(
            active_task.get("inspection_task_id"),
            default=_DEFAULT_INSPECTION_TASK_ID,
        ) or _DEFAULT_INSPECTION_TASK_ID
        channel_name = str(active_task.get("channel_name") or cfg.get("channel_name") or "").strip()
        session_id = str(active_task.get("session_id") or cfg.get("session_id") or "").strip()
        prompt_template = str(active_task.get("prompt_template") or cfg.get("prompt_template") or "").strip()
        inspection_targets = _normalize_inspection_targets(
            active_task.get("inspection_targets"),
            default=_DEFAULT_INSPECTION_TARGETS,
        )
        interval_s = max(
            60,
            int(active_task.get("interval_minutes") or cfg.get("interval_minutes") or 30) * 60,
        )
        now_ts = time.time()
        next_due = ""
        with self._lock:
            w = self._workers.get(pid) or {}
            next_due = str(w.get("auto_inspection_next_due_at") or "").strip()
        if not next_due:
            next_due = _iso_after_s(interval_s)
            self._set_worker_fields(pid, auto_inspection_state="idle", auto_inspection_next_due_at=next_due)
            _save_project_scheduler_runtime_snapshot(
                self.store,
                pid,
                {"auto_inspection_state": "idle", "auto_inspection_next_due_at": next_due},
            )
            return
        due_ts = _parse_rfc3339_ts(next_due)
        if due_ts > 0 and due_ts > now_ts:
            if due_ts - now_ts > (interval_s * 4):
                corrected_due = _iso_after_s(interval_s)
                self._set_worker_fields(pid, auto_inspection_next_due_at=corrected_due)
                _save_project_scheduler_runtime_snapshot(
                    self.store,
                    pid,
                    {"auto_inspection_next_due_at": corrected_due},
                )
            return

        # Gate the previous round result before starting current round.
        self._evaluate_previous_auto_inspection_gate(pid, cfg)

        candidate_pack = _collect_auto_inspection_candidates(
            self.store,
            pid,
            inspection_targets,
            limit=20,
        )
        candidates_all = candidate_pack.get("candidates") if isinstance(candidate_pack, dict) else []
        summary = candidate_pack.get("summary") if isinstance(candidate_pack, dict) else {}
        first_candidate = candidates_all[0] if isinstance(candidates_all, list) and candidates_all else {}
        selected_candidates = [first_candidate] if isinstance(first_candidate, dict) and first_candidate else []
        selected_task_paths = [
            str(x.get("task_path") or "").strip()
            for x in selected_candidates
            if isinstance(x, dict) and str(x.get("task_path") or "").strip()
        ]
        selected_channel_name = (
            str(first_candidate.get("channel_name") or "").strip() if isinstance(first_candidate, dict) else ""
        )
        selected_task_title = str(first_candidate.get("title") or "").strip() if isinstance(first_candidate, dict) else ""
        selected_task_path = (
            _normalize_task_path_identity(str(first_candidate.get("task_path") or "")) if isinstance(first_candidate, dict) else ""
        )
        candidate_count = len(candidates_all) if isinstance(candidates_all, list) else 0
        summary_payload = dict(summary) if isinstance(summary, dict) else {}
        summary_payload["candidate_total"] = candidate_count
        summary_payload["selection_policy"] = "first_task_only_v1"
        summary_payload["selected_count"] = len(selected_candidates)
        prompt_to_send = _build_auto_inspection_prompt(
            prompt_template,
            candidates=selected_candidates,
            summary=summary_payload,
        )
        selected_target_source = ""
        target_sources_txt = ",".join(inspection_targets)
        if isinstance(first_candidate, dict):
            first_source = str(first_candidate.get("target_source") or "").strip()
            if first_source:
                target_sources_txt = first_source
                selected_target_source = first_source
        started_at = _now_iso()
        next_due_at = _iso_after_s(interval_s)

        if not selected_candidates:
            self._set_worker_fields(
                pid,
                auto_inspection_state="idle",
                auto_inspection_last_tick_at=started_at,
                auto_inspection_last_run_id="",
                auto_inspection_last_job_id="",
                auto_inspection_next_due_at=next_due_at,
                auto_inspection_last_error="",
                auto_inspection_last_candidate_count=candidate_count,
                auto_inspection_last_target_sources=target_sources_txt,
                auto_inspection_last_selected_tasks=[],
                auto_inspection_last_task_id=inspection_task_id,
            )
            _save_project_scheduler_runtime_snapshot(
                self.store,
                pid,
                {
                    "auto_inspection_state": "idle",
                    "auto_inspection_last_tick_at": started_at,
                    "auto_inspection_last_run_id": "",
                    "auto_inspection_last_job_id": "",
                    "auto_inspection_next_due_at": next_due_at,
                    "auto_inspection_last_error": "",
                    "auto_inspection_last_candidate_count": candidate_count,
                    "auto_inspection_last_target_sources": target_sources_txt,
                    "auto_inspection_last_selected_tasks": [],
                    "auto_inspection_last_task_id": inspection_task_id,
                },
            )
            self._append_auto_inspection_reminder_record(
                pid,
                {
                    "created_at": started_at,
                    "status": "skipped",
                    "message_summary": "自动巡查未命中可督办任务，已跳过本轮提醒。",
                    "target_task_path": "",
                    "target_channel": "",
                    "run_id": "",
                    "skip_reason": "no_candidate",
                    "inspection_task_id": inspection_task_id,
                },
            )
            return

        owner_primary_session = _resolve_channel_primary_session_id(self.session_store, pid, selected_channel_name)
        if owner_primary_session:
            active_state = _task_push_active_state(self.store, pid, owner_primary_session)
            if bool(active_state.get("active")):
                self._set_worker_fields(
                    pid,
                    auto_inspection_state="idle",
                    auto_inspection_last_tick_at=started_at,
                    auto_inspection_last_run_id="",
                    auto_inspection_last_job_id="",
                    auto_inspection_next_due_at=next_due_at,
                    auto_inspection_last_error="",
                    auto_inspection_last_candidate_count=candidate_count,
                    auto_inspection_last_target_sources=target_sources_txt,
                    auto_inspection_last_selected_tasks=selected_task_paths[:20],
                    auto_inspection_last_task_id=inspection_task_id,
                )
                _save_project_scheduler_runtime_snapshot(
                    self.store,
                    pid,
                    {
                        "auto_inspection_state": "idle",
                        "auto_inspection_last_tick_at": started_at,
                        "auto_inspection_last_run_id": "",
                        "auto_inspection_last_job_id": "",
                        "auto_inspection_next_due_at": next_due_at,
                        "auto_inspection_last_error": "",
                        "auto_inspection_last_candidate_count": candidate_count,
                        "auto_inspection_last_target_sources": target_sources_txt,
                        "auto_inspection_last_selected_tasks": selected_task_paths[:20],
                        "auto_inspection_last_task_id": inspection_task_id,
                    },
                )
                self._append_auto_inspection_reminder_record(
                    pid,
                    {
                        "created_at": started_at,
                        "status": "skipped_active",
                        "message_summary": f"主办通道活跃，自动巡查跳过：{selected_task_title or selected_task_path}",
                        "target_task_path": selected_task_path,
                        "target_channel": selected_channel_name,
                        "run_id": "",
                        "skip_reason": "owner_channel_active",
                        "target_source": selected_target_source,
                        "inspection_task_id": inspection_task_id,
                    },
                )
                return

        self._set_worker_fields(pid, auto_inspection_state="running")
        _save_project_scheduler_runtime_snapshot(
            self.store,
            pid,
            {"auto_inspection_state": "running"},
        )
        try:
            fallback_cli = _project_channel_cli_type(pid, channel_name)
            if self.session_store is None:
                cli_type = fallback_cli or "codex"
            else:
                cli_type = _resolve_cli_type_for_session(self.session_store, pid, session_id, fallback_cli or "codex")
            if self._scheduler is None or str(os.environ.get("CCB_SCHEDULER") or "").strip() == "0":
                raise RuntimeError("scheduler_unavailable_for_auto_inspection")
            run = self.store.create_run(
                pid,
                channel_name,
                session_id,
                prompt_to_send,
                profile_label="ccb",
                cli_type=cli_type,
                sender_type="system",
                sender_id="auto_inspection",
                sender_name="系统自动巡查",
                extra_meta={
                    "trigger_type": "project_auto_inspection",
                    "execution_mode": "auto_inspection",
                    "auto_inspection": True,
                    "inspection_task_id": inspection_task_id,
                    "inspection_targets": inspection_targets,
                    "inspection_candidate_count": candidate_count,
                    "inspection_selected_tasks": selected_task_paths[:20],
                },
            )
            run_id = str(run.get("id") or "").strip()
            _enqueue_run_execution(
                self.store,
                run_id,
                session_id,
                cli_type,
                self._scheduler,
            )
            promote_result = _promote_auto_inspection_task_to_in_progress(
                self.store,
                pid,
                selected_task_path,
            )
            promoted_task_path = _normalize_task_path_identity(str(promote_result.get("new_task_path") or ""))
            if bool(promote_result.get("changed")) and promoted_task_path:
                selected_task_path = promoted_task_path
                selected_task_paths = [promoted_task_path]
            self._set_worker_fields(
                pid,
                auto_inspection_state="idle",
                auto_inspection_last_tick_at=started_at,
                auto_inspection_last_run_id=run_id,
                auto_inspection_last_job_id="",
                auto_inspection_next_due_at=next_due_at,
                auto_inspection_last_error="",
                auto_inspection_last_candidate_count=candidate_count,
                auto_inspection_last_target_sources=target_sources_txt,
                auto_inspection_last_selected_tasks=selected_task_paths[:20],
                auto_inspection_last_task_id=inspection_task_id,
            )
            _save_project_scheduler_runtime_snapshot(
                self.store,
                pid,
                {
                    "auto_inspection_state": "idle",
                    "auto_inspection_last_tick_at": started_at,
                    "auto_inspection_last_run_id": run_id,
                    "auto_inspection_last_job_id": "",
                    "auto_inspection_next_due_at": next_due_at,
                    "auto_inspection_last_error": "",
                    "auto_inspection_last_candidate_count": candidate_count,
                    "auto_inspection_last_target_sources": target_sources_txt,
                    "auto_inspection_last_selected_tasks": selected_task_paths[:20],
                    "auto_inspection_last_task_id": inspection_task_id,
                },
            )
            self._append_auto_inspection_reminder_record(
                pid,
                {
                    "created_at": started_at,
                    "status": "dispatched",
                    "message_summary": f"自动巡查已触发督办：{selected_task_title or selected_task_path}",
                    "target_task_path": selected_task_path,
                    "target_channel": selected_channel_name,
                    "run_id": run_id,
                    "skip_reason": "",
                    "target_source": selected_target_source,
                    "inspection_task_id": inspection_task_id,
                },
            )
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
            failed_at = _now_iso()
            self._set_worker_fields(
                pid,
                auto_inspection_state="error",
                auto_inspection_last_tick_at=failed_at,
                auto_inspection_next_due_at=next_due_at,
                auto_inspection_last_error=err,
                auto_inspection_last_candidate_count=candidate_count,
                auto_inspection_last_target_sources=target_sources_txt,
                auto_inspection_last_selected_tasks=selected_task_paths[:20],
                auto_inspection_last_task_id=inspection_task_id,
            )
            _save_project_scheduler_runtime_snapshot(
                self.store,
                pid,
                {
                    "auto_inspection_state": "error",
                    "auto_inspection_last_tick_at": failed_at,
                    "auto_inspection_next_due_at": next_due_at,
                    "auto_inspection_last_error": err,
                    "auto_inspection_last_candidate_count": candidate_count,
                    "auto_inspection_last_target_sources": target_sources_txt,
                    "auto_inspection_last_selected_tasks": selected_task_paths[:20],
                    "auto_inspection_last_task_id": inspection_task_id,
                },
            )
            self._append_auto_inspection_reminder_record(
                pid,
                {
                    "created_at": failed_at,
                    "status": "error",
                    "message_summary": _safe_text(err, 500),
                    "target_task_path": selected_task_path,
                    "target_channel": selected_channel_name,
                    "run_id": "",
                    "skip_reason": "dispatch_error",
                    "target_source": selected_target_source,
                    "inspection_task_id": inspection_task_id,
                },
            )

    def _tick_once(self, project_id: str) -> None:
        pid = str(project_id or "").strip()
        if not pid:
            return
        started_at = _now_iso()
        self._set_worker_fields(
            pid,
            scheduler_state="scanning",
            reminder_state="collecting",
        )
        _save_project_scheduler_runtime_snapshot(
            self.store,
            pid,
            {
                "scheduler_state": "scanning",
                "reminder_state": "collecting",
            },
        )
        try:
            bridge_summary = _run_project_scheduler_once_bridge(self.store, pid)
            guard_runtime = bridge_summary.get("guard_runtime") if isinstance(bridge_summary, dict) else {}
            guard_events = _normalize_guard_runtime_events(
                guard_runtime.get("events") if isinstance(guard_runtime, dict) else []
            )
            guard_stats = _normalize_guard_runtime_stats(
                guard_runtime.get("stats") if isinstance(guard_runtime, dict) else {}
            )
            guard_policy = dict(guard_runtime.get("policy") or {}) if isinstance(guard_runtime, dict) else {}
            finished_at = _now_iso()
            self._set_worker_fields(
                pid,
                scheduler_state="idle",
                scheduler_last_tick_at=finished_at,
                scheduler_last_error="",
                reminder_state="idle",
                reminder_last_tick_at=finished_at,
                reminder_last_error="",
                guard_policy=guard_policy,
                guard_events=guard_events,
                guard_stats=guard_stats,
                guard_last_tick_at=finished_at,
            )
            _save_project_scheduler_runtime_snapshot(
                self.store,
                pid,
                {
                    "scheduler_state": "idle",
                    "scheduler_last_tick_at": finished_at,
                    "scheduler_last_error": "",
                    "reminder_state": "idle",
                    "reminder_last_tick_at": finished_at,
                    "reminder_last_error": "",
                    "guard_policy": guard_policy,
                    "guard_events": guard_events,
                    "guard_stats": guard_stats,
                    "guard_last_tick_at": finished_at,
                },
            )
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
            failed_at = _now_iso()
            self._set_worker_fields(
                pid,
                scheduler_state="error",
                scheduler_last_tick_at=failed_at,
                scheduler_last_error=err,
                reminder_state="error",
                reminder_last_tick_at=failed_at,
                reminder_last_error=err,
            )
            _save_project_scheduler_runtime_snapshot(
                self.store,
                pid,
                {
                    "scheduler_state": "error",
                    "scheduler_last_tick_at": failed_at,
                    "scheduler_last_error": err,
                    "reminder_state": "error",
                    "reminder_last_tick_at": failed_at,
                    "reminder_last_error": err,
                },
            )

    def _loop(self, project_id: str, stop_event: threading.Event) -> None:
        pid = str(project_id or "").strip()
        while not stop_event.is_set():
            cfg = _load_project_scheduler_contract_config(pid)
            scfg = cfg.get("scheduler") if isinstance(cfg.get("scheduler"), dict) else {}
            rcfg = cfg.get("reminder") if isinstance(cfg.get("reminder"), dict) else {}
            acfg = _load_project_auto_inspection_config(pid)
            scheduler_enabled = bool(cfg.get("project_exists")) and bool(scfg.get("enabled"))
            auto_inspection_enabled = bool(acfg.get("enabled"))
            if not cfg.get("project_exists") or (not scheduler_enabled and not auto_inspection_enabled):
                break
            interval_s = self._effective_worker_interval_s(pid)
            scheduler_scan_interval_s = int(scfg.get("scan_interval_seconds") or 300)
            self._set_worker_fields(
                pid,
                running=True,
                interval_s=interval_s,
                reminder_state="idle" if (scheduler_enabled and bool(rcfg.get("enabled"))) else "disabled",
                reminder_next_due_at=(
                    _iso_after_s(scheduler_scan_interval_s)
                    if (scheduler_enabled and bool(rcfg.get("enabled")))
                    else ""
                ),
            )
            self._sync_auto_inspection_runtime_hints(pid, auto_inspection_cfg=acfg)
            if stop_event.wait(max(1, interval_s)):
                break
            if scheduler_enabled:
                self._tick_once(pid)
            else:
                self._set_worker_fields(
                    pid,
                    scheduler_state="disabled",
                    reminder_state="disabled",
                    reminder_next_due_at="",
                )
                _save_project_scheduler_runtime_snapshot(
                    self.store,
                    pid,
                    {
                        "scheduler_state": "disabled",
                        "reminder_state": "disabled",
                        "reminder_next_due_at": "",
                    },
                )
            self._tick_auto_inspection_once(pid)
            if not stop_event.is_set():
                if scheduler_enabled:
                    next_due = _iso_after_s(scheduler_scan_interval_s)
                    self._set_worker_fields(
                        pid,
                        reminder_next_due_at=next_due if bool(rcfg.get("enabled")) else "",
                    )
                    _save_project_scheduler_runtime_snapshot(
                        self.store,
                        pid,
                        {
                            "reminder_next_due_at": next_due if bool(rcfg.get("enabled")) else "",
                        },
                    )
                else:
                    self._set_worker_fields(pid, reminder_next_due_at="")
                    _save_project_scheduler_runtime_snapshot(
                        self.store,
                        pid,
                        {
                            "reminder_next_due_at": "",
                        },
                    )

        # mark stopped (state comes from config via query; runtime only notes worker flag)
        self._set_worker_fields(pid, running=False)

    def _start_worker_locked(
        self,
        project_id: str,
        interval_s: int,
        reminder_enabled: bool,
        *,
        reminder_interval_s: int = 300,
        auto_inspection_cfg: Optional[dict[str, Any]] = None,
    ) -> None:
        pid = str(project_id or "").strip()
        if not pid:
            return
        acfg = auto_inspection_cfg if isinstance(auto_inspection_cfg, dict) else _load_project_auto_inspection_config(pid)
        auto_enabled = bool(acfg.get("enabled"))
        auto_ready = bool(acfg.get("ready"))
        auto_state = "disabled"
        auto_next_due_at = ""
        existing_snapshot = _load_project_scheduler_runtime_snapshot(self.store, pid)
        existing_records = _normalize_auto_inspection_reminder_records(existing_snapshot.get("reminder_records"))
        existing_inspection_records = _normalize_inspection_records(existing_snapshot.get("inspection_records"))
        if not existing_inspection_records and existing_records:
            existing_inspection_records = _inspection_records_from_reminder_records(
                existing_records,
                auto_inspections=acfg.get("auto_inspections"),
                default_inspection_task_id=_normalize_inspection_task_id(
                    acfg.get("active_inspection_task_id"),
                    default=_DEFAULT_INSPECTION_TASK_ID,
                ),
            )
        existing_execution_state = str(existing_snapshot.get("auto_inspection_execution_state") or "")
        existing_gate_reason = str(existing_snapshot.get("auto_inspection_gate_last_reason") or "")
        existing_gate_run_id = str(existing_snapshot.get("auto_inspection_gate_last_run_id") or "")
        existing_gate_checked_at = str(existing_snapshot.get("auto_inspection_gate_last_checked_at") or "")
        existing_gate_action = str(existing_snapshot.get("auto_inspection_gate_action") or "")
        existing_gate_action_run_id = str(existing_snapshot.get("auto_inspection_gate_action_run_id") or "")
        existing_last_task_id = _normalize_inspection_task_id(
            existing_snapshot.get("auto_inspection_last_task_id"),
            default=_DEFAULT_INSPECTION_TASK_ID,
        )
        try:
            existing_advice_streak = max(0, int(existing_snapshot.get("auto_inspection_advice_only_streak") or 0))
        except Exception:
            existing_advice_streak = 0
        try:
            existing_escalation_level = max(0, int(existing_snapshot.get("auto_inspection_escalation_level") or 0))
        except Exception:
            existing_escalation_level = 0
        if auto_enabled:
            auto_state = "idle" if auto_ready else "invalid_config"
            if auto_ready:
                auto_next_due_at = _iso_after_s(max(60, int(acfg.get("interval_minutes") or 30) * 60))
        stop_event = threading.Event()
        thread = threading.Thread(target=self._loop, args=(pid, stop_event), daemon=True)
        self._workers[pid] = {
            "thread": thread,
            "stop_event": stop_event,
            "running": True,
            "interval_s": interval_s,
            "scheduler_state": "idle",
            "scheduler_last_error": "",
            "reminder_state": "idle" if reminder_enabled else "disabled",
            "reminder_next_due_at": _iso_after_s(reminder_interval_s) if reminder_enabled else "",
            "reminder_records": existing_records,
            "inspection_records": existing_inspection_records,
            "auto_inspection_state": auto_state,
            "auto_inspection_next_due_at": auto_next_due_at,
            "auto_inspection_last_error": "",
            "auto_inspection_last_task_id": existing_last_task_id,
            "auto_inspection_execution_state": existing_execution_state,
            "auto_inspection_gate_last_reason": existing_gate_reason,
            "auto_inspection_gate_last_run_id": existing_gate_run_id,
            "auto_inspection_gate_last_checked_at": existing_gate_checked_at,
            "auto_inspection_advice_only_streak": existing_advice_streak,
            "auto_inspection_escalation_level": existing_escalation_level,
            "auto_inspection_gate_action": existing_gate_action,
            "auto_inspection_gate_action_run_id": existing_gate_action_run_id,
        }
        _save_project_scheduler_runtime_snapshot(
            self.store,
            pid,
            {
                "scheduler_state": "idle",
                "scheduler_last_error": "",
                "reminder_state": "idle" if reminder_enabled else "disabled",
                "reminder_next_due_at": _iso_after_s(reminder_interval_s) if reminder_enabled else "",
                "reminder_records": existing_records,
                "inspection_records": existing_inspection_records,
                "auto_inspection_state": auto_state,
                "auto_inspection_next_due_at": auto_next_due_at,
                "auto_inspection_last_error": "",
                "auto_inspection_last_task_id": existing_last_task_id,
                "auto_inspection_execution_state": existing_execution_state,
                "auto_inspection_gate_last_reason": existing_gate_reason,
                "auto_inspection_gate_last_run_id": existing_gate_run_id,
                "auto_inspection_gate_last_checked_at": existing_gate_checked_at,
                "auto_inspection_advice_only_streak": existing_advice_streak,
                "auto_inspection_escalation_level": existing_escalation_level,
                "auto_inspection_gate_action": existing_gate_action,
                "auto_inspection_gate_action_run_id": existing_gate_action_run_id,
            },
        )
        thread.start()

    def stop_project(self, project_id: str) -> dict[str, Any]:
        pid = str(project_id or "").strip()
        with self._lock:
            w = self._workers.pop(pid, None)
        if isinstance(w, dict):
            ev = w.get("stop_event")
            if isinstance(ev, threading.Event):
                ev.set()
        _save_project_scheduler_runtime_snapshot(
            self.store,
            pid,
            {
                "scheduler_state": "disabled",
                "scheduler_last_error": "",
                "reminder_state": "disabled",
                "reminder_next_due_at": "",
                "auto_inspection_state": "disabled",
                "auto_inspection_next_due_at": "",
            },
        )
        return self.get_status(pid)

    def sync_project(self, project_id: str) -> dict[str, Any]:
        pid = str(project_id or "").strip()
        cfg = _load_project_scheduler_contract_config(pid)
        if not cfg.get("project_exists"):
            return {}
        scfg = cfg.get("scheduler") if isinstance(cfg.get("scheduler"), dict) else {}
        rcfg = cfg.get("reminder") if isinstance(cfg.get("reminder"), dict) else {}
        acfg = _load_project_auto_inspection_config(pid)
        scheduler_enabled = bool(scfg.get("enabled"))
        auto_inspection_enabled = bool(acfg.get("enabled"))
        enabled = scheduler_enabled or auto_inspection_enabled
        interval_s = self._effective_worker_interval_s(pid)
        scheduler_scan_interval_s = int(scfg.get("scan_interval_seconds") or 300)
        reminder_enabled = bool(rcfg.get("enabled")) and scheduler_enabled

        if not enabled:
            return self.stop_project(pid)

        restart_needed = False
        fast_status = False
        with self._lock:
            existing = self._workers.get(pid)
            if isinstance(existing, dict):
                old_interval = int(existing.get("interval_s") or interval_s)
                if old_interval != interval_s:
                    ev = existing.get("stop_event")
                    if isinstance(ev, threading.Event):
                        ev.set()
                    self._workers.pop(pid, None)
                    restart_needed = True
                else:
                    # keep worker, refresh reminder state hints
                    existing["reminder_state"] = "idle" if reminder_enabled else "disabled"
                    existing["reminder_next_due_at"] = _iso_after_s(scheduler_scan_interval_s) if reminder_enabled else ""
                    self._workers[pid] = existing
                    fast_status = True
            if not fast_status:
                self._start_worker_locked(
                    pid,
                    interval_s,
                    reminder_enabled,
                    reminder_interval_s=scheduler_scan_interval_s,
                    auto_inspection_cfg=acfg,
                )
        if fast_status:
            self._sync_auto_inspection_runtime_hints(pid, auto_inspection_cfg=acfg)
            # Important: query status outside the registry lock. get_status() reads runtime flags
            # and would deadlock if called while holding the same non-reentrant lock.
            return self.get_status(pid)

        if restart_needed:
            # Worker replaced; status query will read new worker state.
            pass
        return self.get_status(pid)

    def sync_enabled_projects_from_config(self) -> None:
        script_dir = Path(__file__).resolve().parent
        cfg = load_dashboard_config(script_dir, with_local=_with_local_config_enabled())
        projects = cfg.get("projects")
        if not isinstance(projects, list):
            return
        desired: set[str] = set()
        for p in projects:
            if not isinstance(p, dict):
                continue
            pid = str(p.get("id") or "").strip()
            if not pid:
                continue
            scfg = p.get("scheduler") if isinstance(p.get("scheduler"), dict) else {}
            acfg = p.get("auto_inspection") if isinstance(p.get("auto_inspection"), dict) else {}
            if _coerce_bool(scfg.get("enabled"), False) or _coerce_bool(acfg.get("enabled"), False):
                desired.add(pid)
        for pid in sorted(desired):
            try:
                self.sync_project(pid)
            except Exception:
                continue
        with self._lock:
            current = list(self._workers.keys())
        for pid in current:
            if pid not in desired:
                self.stop_project(pid)

    def shutdown(self) -> None:
        with self._lock:
            ids = list(self._workers.keys())
        for pid in ids:
            self.stop_project(pid)
