# -*- coding: utf-8 -*-
"""
Shared scheduling/inspection/queue infrastructure helpers.

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
from urllib.parse import urlparse

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
from task_dashboard.runtime.request_parsing import (
    _normalize_reasoning_effort_local as _normalize_reasoning_effort,
)
from task_dashboard.runtime.project_execution_context import build_project_execution_context


__all__ = [
    "_AUTO_INSPECTION_EXECUTION_HINTS",
    "_AUTO_INSPECTION_GATE_L1_THRESHOLD",
    "_AUTO_INSPECTION_GATE_L2_THRESHOLD",
    "_AUTO_INSPECTION_OBJECT_TYPE_ORDER",
    "_AUTO_INSPECTION_OBJECT_TYPE_SET",
    "_AUTO_INSPECTION_RECORD_LIMIT",
    "_AUTO_INSPECTION_RECORD_STATUS",
    "_DEFAULT_HEARTBEAT_TASK_ID",
    "_DEFAULT_INSPECTION_TARGETS",
    "_DEFAULT_INSPECTION_TASK_ID",
    "_GUARD_EVENT_LEVEL_ORDER",
    "_HEARTBEAT_TASK_BUSY_POLICIES",
    "_HEARTBEAT_TASK_HISTORY_LIMIT",
    "_HEARTBEAT_TASK_SCHEDULE_TYPES",
    "_INSPECTION_TARGET_LABELS",
    "_INSPECTION_TARGET_ORDER",
    "_INSPECTION_TARGET_SET",
    "_RUNTIME_BUBBLE_ACTIVE_STATUSES",
    "_RUNTIME_BUBBLE_STATUS_LABELS",
    "_RUNTIME_BUBBLE_STATUS_TONES",
    "_RUNTIME_BUBBLE_TERMINAL_STATUSES",
    "_RUNTIME_BUBBLE_TTL_SECONDS",
    "_RUNTIME_RELATION_TTL_SECONDS",
    "_apply_effective_primary_flags",
    "_attach_auto_inspection_candidate_preview",
    "_auto_inspection_has_execution_evidence",
    "_auto_inspection_object_key_for_target",
    "_auto_inspection_targets_from_objects",
    "_auto_inspection_tasks_for_write",
    "_build_auto_inspection_patch_with_tasks",
    "_build_auto_inspection_prompt",
    "_build_auto_inspections_from_targets",
    "_build_default_auto_inspection_task",
    "_build_heartbeat_patch_with_tasks",
    "_build_inspection_record_id",
    "_build_project_scheduler_status",
    "_build_project_task_item_from_path",
    "_build_runtime_bubbles_payload",
    "_build_session_binding_required_payload",
    "_classify_auto_inspection_execution_result",
    "_collect_auto_inspection_candidates",
    "_enqueue_run_for_dispatch",
    "_ensure_auto_scheduler_status_shape",
    "_extract_auto_inspection_structured_payload",
    "_extract_status_from_task_filename",
    "_heartbeat_session_payload_for_write",
    "_heartbeat_summary_payload",
    "_heartbeat_task_project_root",
    "_heartbeat_task_runtime_key",
    "_heartbeat_task_runtime_path",
    "_heartbeat_task_state_root",
    "_heartbeat_tasks_for_write",
    "_inspection_record_from_reminder_record",
    "_inspection_records_from_reminder_records",
    "_inspection_target_tokens",
    "_iso_from_ts",
    "_list_project_task_items",
    "_load_project_auto_dispatch_config",
    "_load_project_auto_inspection_config",
    "_load_project_heartbeat_config",
    "_load_project_scheduler_contract_config",
    "_load_project_scheduler_runtime_snapshot",
    "_load_session_heartbeat_config",
    "_matches_inspection_target",
    "_normalize_auto_inspection_match_values",
    "_normalize_auto_inspection_object",
    "_normalize_auto_inspection_reminder_record",
    "_normalize_auto_inspection_reminder_records",
    "_normalize_auto_inspection_selected_tasks",
    "_normalize_auto_inspection_task",
    "_normalize_auto_inspection_tasks",
    "_normalize_auto_inspections",
    "_normalize_guard_runtime_event",
    "_normalize_guard_runtime_events",
    "_normalize_guard_runtime_stats",
    "_normalize_heartbeat_context_scope",
    "_normalize_heartbeat_task",
    "_normalize_heartbeat_task_id",
    "_normalize_heartbeat_tasks",
    "_normalize_heartbeat_weekdays",
    "_normalize_inspection_record",
    "_normalize_inspection_records",
    "_normalize_inspection_targets",
    "_normalize_inspection_task_id",
    "_project_scheduler_state_path",
    "_project_scheduler_state_root",
    "_promote_auto_inspection_task_to_in_progress",
    "_reminder_record_from_inspection_record",
    "_reminder_records_from_inspection_records",
    "_resolve_auto_kickoff_target_session",
    "_resolve_channel_primary_session_id",
    "_resolve_cli_type_for_session",
    "_resolve_model_for_session",
    "_resolve_project_task_abs_path",
    "_resolve_reasoning_effort_for_session",
    "_resolve_scheduler_engine_enabled",
    "_run_project_scheduler_once_bridge",
    "_runtime_bubble_status_label",
    "_runtime_bubble_status_tone",
    "_runtime_expire_at_from_base",
    "_runtime_related_objects_from_meta",
    "_runtime_relations_from_meta",
    "_save_project_scheduler_runtime_snapshot",
    "_scan_project_task_items",
    "_select_active_auto_inspection_task",
    "_set_project_scheduler_contract_in_config",
    "_set_project_scheduler_contract_in_config_text",
    "_set_project_scheduler_enabled_in_config",
    "_set_project_scheduler_enabled_in_config_text",
    "_set_project_table_values_in_config_text",
    "_task_lane_from_bucket",
    "_task_plan_item_path",
    "_task_plan_project_root",
    "_task_plan_runtime_path",
    "_task_plan_state_root",
    "_task_push_active_state",
    "_task_push_dedupe_key",
    "_task_push_job_path",
    "_task_push_new_job_id",
    "_task_push_should_auto_retry",
    "_task_push_state_root",
    "_task_push_trigger_type",
    "_validate_announce_session_binding",
    # Metadata normalization functions (extracted from server.py)
    "_PLAN_FIRST_MARKER",
    "_PLAN_FIRST_PROMPT_VERSION",
    "_apply_plan_first_to_message",
    "_build_plan_first_prefix",
    "_compact_route_resolution_v1",
    "_extract_run_extra_fields",
    "_normalize_callback_to",
    "_normalize_mention_targets",
    "_normalize_reply_to_fields",
    "_sanitize_local_server_origin",
    "_sanitize_receipt_summary",
    "_sanitize_run_extra_meta",
]

_TASK_WITH_RECEIPT_GUARD_MARKER = "[运行时回执约束]"
_TASK_WITH_RECEIPT_GUARD_VERSION = "v1"


def __getattr__(name):
    """Lazy resolution of names still defined in server.py (avoids circular imports)."""
    import server
    try:
        return getattr(server, name)
    except AttributeError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _call_server_override(name: str, local_fn: Callable[..., Any], *args, **kwargs):
    remote = __getattr__(name)
    if remote is not local_fn:
        return remote(*args, **kwargs)
    return local_fn(*args, **kwargs)


def _find_project_cfg(project_id: str):
    return __getattr__("_find_project_cfg")(project_id)


def _resolve_project_task_root(project_id: str):
    return __getattr__("_resolve_project_task_root")(project_id)


def _normalize_task_path_identity(task_path: str) -> str:
    return __getattr__("_normalize_task_path_identity")(task_path)


def _repo_root() -> Path:
    return __getattr__("_repo_root")()


def _parse_rfc3339_ts(value: Any):
    return __getattr__("_parse_rfc3339_ts")(value)


def _resolve_task_project_channel(task_path: str, *, project_hint: str = ""):
    return __getattr__("_resolve_task_project_channel")(task_path, project_hint=project_hint)


def _resolve_primary_target_by_channel(project_id: str, channel_name: str):
    return __getattr__("_resolve_primary_target_by_channel")(project_id, channel_name)


def _clear_auto_inspection_preview_cache(project_id: str) -> None:
    __getattr__("_clear_auto_inspection_preview_cache")(project_id)


def _project_channel_cli_type(project_id: str, channel_name: str) -> str:
    return __getattr__("_project_channel_cli_type")(project_id, channel_name)


def _change_task_status(task_path: str, next_status: str):
    return __getattr__("_change_task_status")(task_path, next_status)


def _auto_inspection_preview_cache_ttl_s() -> float:
    return float(__getattr__("_auto_inspection_preview_cache_ttl_s")())


def _auto_inspection_preview_cache_lock():
    return __getattr__("_AUTO_INSPECTION_PREVIEW_CACHE_LOCK")


def _auto_inspection_preview_cache() -> dict[str, Any]:
    return __getattr__("_AUTO_INSPECTION_PREVIEW_CACHE")


def _store_runtime_base_dir(store: "RunStore") -> Path:
    runs_dir = getattr(store, "runs_dir", None)
    if isinstance(runs_dir, Path):
        return runs_dir.parent
    if runs_dir:
        try:
            return Path(runs_dir).parent
        except Exception:
            pass
    return _repo_root()


def bucket_key_for_status(status: str):
    return __getattr__("bucket_key_for_status")(status)


def _extract_task_title(task_path: str) -> str:
    return __getattr__("_extract_task_title")(task_path)


def _inspect_callback_task_activity(task_path: str):
    return __getattr__("_inspect_callback_task_activity")(task_path)


def _task_items_cache_enabled() -> bool:
    return bool(__getattr__("_task_items_cache_enabled")())


def _task_items_cache_ttl_s() -> float:
    return float(__getattr__("_task_items_cache_ttl_s")())


def _project_task_items_cache_lock():
    return __getattr__("_PROJECT_TASK_ITEMS_CACHE_LOCK")


def _project_task_items_cache():
    return __getattr__("_PROJECT_TASK_ITEMS_CACHE")


def _project_scheduler_state_root(store: "RunStore") -> Path:
    return _store_runtime_base_dir(store) / ".run" / "project_scheduler"


def _project_scheduler_state_path(store: "RunStore", project_id: str) -> Path:
    pid = str(project_id or "").strip()
    return _project_scheduler_state_root(store) / pid / "status.json"


def _task_push_state_root(store: "RunStore") -> Path:
    return _store_runtime_base_dir(store) / ".run" / "task_push"


def _task_push_job_path(store: "RunStore", project_id: str, job_id: str) -> Path:
    pid = str(project_id or "").strip()
    jid = str(job_id or "").strip()
    return _task_push_state_root(store) / pid / f"{jid}.json"


def _task_push_new_job_id() -> str:
    return time.strftime("%Y%m%d-%H%M%S", time.localtime()) + "-" + secrets.token_hex(4)


def _task_push_trigger_type(run_extra_meta: Any) -> str:
    meta = run_extra_meta if isinstance(run_extra_meta, dict) else {}
    return _safe_text(meta.get("trigger_type"), 80).strip().lower()


def _task_push_should_auto_retry(run_extra_meta: Any) -> bool:
    return _task_push_trigger_type(run_extra_meta).startswith("auto_inspection")


def _task_push_dedupe_key(run_extra_meta: Any, message: str) -> str:
    meta = run_extra_meta if isinstance(run_extra_meta, dict) else {}
    for key in ("topic", "task_id", "task_path"):
        v = _safe_text(meta.get(key), 300).strip()
        if v:
            return f"meta:{v}"
    msg = str(message or "").strip()
    return f"msg:{msg}" if msg else ""


def _task_plan_state_root(store: "RunStore") -> Path:
    return _store_runtime_base_dir(store) / ".run" / "task_plans"


def _task_plan_project_root(store: "RunStore", project_id: str) -> Path:
    pid = str(project_id or "").strip()
    return _task_plan_state_root(store) / pid


def _task_plan_item_path(store: "RunStore", project_id: str, plan_id: str) -> Path:
    rid = str(plan_id or "").strip()
    return _task_plan_project_root(store, project_id) / f"{rid}.json"


def _task_plan_runtime_path(store: "RunStore", project_id: str) -> Path:
    return _task_plan_project_root(store, project_id) / "_runtime.json"


def _heartbeat_task_state_root(store: "RunStore") -> Path:
    return _store_runtime_base_dir(store) / ".run" / "heartbeat_tasks"


def _heartbeat_task_project_root(store: "RunStore", project_id: str) -> Path:
    pid = str(project_id or "").strip()
    return _heartbeat_task_state_root(store) / pid


def _heartbeat_task_runtime_path(store: "RunStore", project_id: str, heartbeat_task_id: str) -> Path:
    hid = str(heartbeat_task_id or "").strip()
    return _heartbeat_task_project_root(store, project_id) / f"{hid}.json"


def _heartbeat_task_runtime_key(heartbeat_task_id: str, session_id: str = "") -> str:
    task_id = _normalize_heartbeat_task_id(heartbeat_task_id, default="")
    sid = str(session_id or "").strip().lower()
    if sid:
        safe_sid = re.sub(r"[^0-9a-zA-Z_-]+", "-", sid).strip("-_")[:120]
        if safe_sid:
            return f"session-{safe_sid}-{task_id}"[:220]
    return task_id


_INSPECTION_TARGET_ORDER = [
    "todo",
    "in_progress",
    "pending",
    "pending_acceptance",
]
_INSPECTION_TARGET_SET = set(_INSPECTION_TARGET_ORDER)
_AUTO_INSPECTION_OBJECT_TYPE_ORDER = _INSPECTION_TARGET_ORDER + ["custom"]
_AUTO_INSPECTION_OBJECT_TYPE_SET = set(_AUTO_INSPECTION_OBJECT_TYPE_ORDER)
_DEFAULT_INSPECTION_TARGETS = ["todo", "in_progress"]
_INSPECTION_TARGET_LABELS = {
    "todo": "待开始",
    "in_progress": "进行中",
    "pending": "待处理",
    "pending_acceptance": "待验收",
}
_AUTO_INSPECTION_RECORD_LIMIT = 50
_AUTO_INSPECTION_RECORD_STATUS = {"dispatched", "effective", "skipped_active", "advice_only", "skipped", "error"}
_AUTO_INSPECTION_GATE_L1_THRESHOLD = 2
_AUTO_INSPECTION_GATE_L2_THRESHOLD = 3
_DEFAULT_INSPECTION_TASK_ID = "default"
_HEARTBEAT_TASK_HISTORY_LIMIT = 50
_HEARTBEAT_TASK_SCHEDULE_TYPES = {"interval", "daily"}
_HEARTBEAT_TASK_BUSY_POLICIES = {"run_on_next_idle", "skip_if_busy", "queue_if_busy"}
_HEARTBEAT_TASK_PRESETS: dict[str, dict[str, str]] = {
    "issue_review": {
        "title": "问题审查",
        "prompt": "审查最近一轮工作中出现的问题、重复故障与未收口风险，输出结论、风险、建议动作与需人工确认项。",
    },
    "work_push": {
        "title": "任务推进",
        "prompt": "检查你当前负责任务的进度、阻塞与未补齐项；优先推进可直接落地的工作，并给出最小下一步。",
    },
    "team_watch": {
        "title": "团队巡查",
        "prompt": "检查团队内活跃任务与会话，识别超过阈值无进展、阻塞或协同缺口的项，并给出疏通动作。",
    },
    "ops_inspection": {
        "title": "运维巡查",
        "prompt": "巡查运行态、异常会话、残留运行产物与可直接恢复的问题，先给结论，再给处理动作。",
    },
    "acceptance_followup": {
        "title": "待验收催收",
        "prompt": "检查待验收项是否缺反馈、缺证据或缺联调结果，优先补齐可直接收口的内容。",
    },
    "daily_summary": {
        "title": "每日总结",
        "prompt": "总结当日推进结果、剩余风险、次日重点与需协同事项，保持摘要清晰可执行。",
    },
}
_DEFAULT_HEARTBEAT_TASK_ID = "default"
_AUTO_INSPECTION_EXECUTION_HINTS = (
    "已执行",
    "执行完成",
    "已完成",
    "已落地",
    "已提交",
    "已触发",
    "测试通过",
    "run_id",
    "job_id",
    "api/",
    "curl ",
    "python3 ",
)


def _normalize_inspection_task_id(raw: Any, *, default: str = "") -> str:
    txt = _safe_text(raw, 120).strip().lower()
    if txt:
        txt = re.sub(r"[^0-9a-zA-Z_-]+", "-", txt)
        txt = txt.strip("-_")
    if not txt:
        txt = _safe_text(default, 120).strip().lower()
        txt = re.sub(r"[^0-9a-zA-Z_-]+", "-", txt).strip("-_")
    return txt[:80]


def _normalize_heartbeat_task_id(raw: Any, *, default: str = "") -> str:
    txt = _safe_text(raw, 120).strip().lower()
    if txt:
        txt = re.sub(r"[^0-9a-zA-Z_-]+", "-", txt)
        txt = txt.strip("-_")
    if not txt:
        txt = _safe_text(default, 120).strip().lower()
        txt = re.sub(r"[^0-9a-zA-Z_-]+", "-", txt).strip("-_")
    return txt[:80]


def _normalize_heartbeat_weekdays(raw: Any) -> list[int]:
    rows = raw if isinstance(raw, list) else []
    out: list[int] = []
    for item in rows:
        try:
            value = int(item)
        except Exception:
            continue
        if value < 1 or value > 7 or value in out:
            continue
        out.append(value)
    return out or [1, 2, 3, 4, 5, 6, 7]


def _normalize_heartbeat_context_scope(raw: Any) -> dict[str, Any]:
    obj = raw if isinstance(raw, dict) else {}
    recent_tasks_limit = max(
        0,
        min(
            20,
            _coerce_int(
                obj.get("recent_tasks_limit") if "recent_tasks_limit" in obj else obj.get("recentTasksLimit"),
                5,
            ),
        ),
    )
    recent_runs_limit = max(
        0,
        min(
            20,
            _coerce_int(
                obj.get("recent_runs_limit") if "recent_runs_limit" in obj else obj.get("recentRunsLimit"),
                5,
            ),
        ),
    )
    return {
        "recent_tasks_limit": recent_tasks_limit,
        "recent_runs_limit": recent_runs_limit,
        "include_task_counts": _coerce_bool(
            obj.get("include_task_counts") if "include_task_counts" in obj else obj.get("includeTaskCounts"),
            True,
        ),
        "include_recent_tasks": _coerce_bool(
            obj.get("include_recent_tasks") if "include_recent_tasks" in obj else obj.get("includeRecentTasks"),
            True,
        ),
        "include_recent_runs": _coerce_bool(
            obj.get("include_recent_runs") if "include_recent_runs" in obj else obj.get("includeRecentRuns"),
            True,
        ),
    }


def _normalize_heartbeat_task(
    item: Any,
    *,
    index: int = 0,
    defaults: Optional[dict[str, Any]] = None,
    id_required: bool = False,
) -> Optional[dict[str, Any]]:
    if not isinstance(item, dict):
        return None
    d = defaults if isinstance(defaults, dict) else {}
    fallback_id = f"heartbeat-{index + 1}"
    raw_task_id = (
        item.get("heartbeat_task_id")
        if "heartbeat_task_id" in item
        else (
            item.get("heartbeatTaskId")
            if "heartbeatTaskId" in item
            else item.get("task_id")
        )
    )
    heartbeat_task_id = _normalize_heartbeat_task_id(raw_task_id, default=fallback_id)
    if id_required and not str(raw_task_id or "").strip():
        return None
    if not heartbeat_task_id:
        return None

    title = _safe_text(
        item.get("title")
        if "title" in item
        else (item.get("name") if "name" in item else d.get("title")),
        200,
    ).strip()
    if not title:
        title = f"心跳任务-{heartbeat_task_id}"
    enabled = _coerce_bool(item.get("enabled"), _coerce_bool(d.get("enabled"), False))
    channel_name = _safe_text(
        item.get("channel_name")
        if "channel_name" in item
        else (item.get("channelName") if "channelName" in item else d.get("channel_name")),
        240,
    ).strip()
    session_id = _safe_text(
        item.get("session_id")
        if "session_id" in item
        else (item.get("sessionId") if "sessionId" in item else d.get("session_id")),
        120,
    ).strip()
    preset_key = _safe_text(
        item.get("preset_key")
        if "preset_key" in item
        else (item.get("presetKey") if "presetKey" in item else d.get("preset_key")),
        80,
    ).strip().lower()
    if preset_key and preset_key not in _HEARTBEAT_TASK_PRESETS:
        preset_key = ""
    prompt_template = _safe_text(
        item.get("prompt_template")
        if "prompt_template" in item
        else (
            item.get("promptTemplate")
            if "promptTemplate" in item
            else (
                item.get("custom_prompt")
                if "custom_prompt" in item
                else (item.get("customPrompt") if "customPrompt" in item else d.get("prompt_template"))
            )
        ),
        20_000,
    ).strip()
    schedule_type = _safe_text(
        item.get("schedule_type")
        if "schedule_type" in item
        else (item.get("scheduleType") if "scheduleType" in item else d.get("schedule_type")),
        40,
    ).strip().lower() or "interval"
    if schedule_type not in _HEARTBEAT_TASK_SCHEDULE_TYPES:
        schedule_type = "interval"
    interval_raw = (
        item.get("interval_minutes")
        if "interval_minutes" in item
        else (item.get("intervalMinutes") if "intervalMinutes" in item else d.get("interval_minutes"))
    )
    max_execute_count_raw = (
        item.get("max_execute_count")
        if "max_execute_count" in item
        else (item.get("maxExecuteCount") if "maxExecuteCount" in item else d.get("max_execute_count"))
    )
    max_execute_count = 0
    if max_execute_count_raw not in (None, "", False):
        max_execute_count = max(0, _coerce_int(max_execute_count_raw, 0))
    interval_minutes: Optional[int] = None
    daily_time = _safe_text(
        item.get("daily_time")
        if "daily_time" in item
        else (item.get("dailyTime") if "dailyTime" in item else d.get("daily_time")),
        20,
    ).strip()
    weekdays = _normalize_heartbeat_weekdays(
        item.get("weekdays") if "weekdays" in item else d.get("weekdays")
    )
    busy_policy = _safe_text(
        item.get("busy_policy")
        if "busy_policy" in item
        else (item.get("busyPolicy") if "busyPolicy" in item else d.get("busy_policy")),
        40,
    ).strip().lower() or "run_on_next_idle"
    if busy_policy not in _HEARTBEAT_TASK_BUSY_POLICIES:
        busy_policy = "run_on_next_idle"
    context_scope = _normalize_heartbeat_context_scope(
        item.get("context_scope") if "context_scope" in item else item.get("contextScope")
    )
    if not isinstance(item.get("context_scope"), dict) and not isinstance(item.get("contextScope"), dict):
        context_scope = _normalize_heartbeat_context_scope(d.get("context_scope"))

    errors: list[str] = []
    if session_id and not _looks_like_uuid(session_id):
        errors.append("heartbeat_task.session_id_invalid")
        session_id = ""
    if enabled and not channel_name:
        errors.append("heartbeat_task.channel_name_missing")
    if enabled and not session_id:
        errors.append("heartbeat_task.session_id_missing")
    if schedule_type == "interval":
        if interval_raw not in (None, "", 0, "0", False):
            interval_minutes = _coerce_int(interval_raw, 60)
        elif enabled:
            interval_minutes = 60
        if interval_minutes is not None and interval_minutes < 5:
            errors.append("heartbeat_task.interval_minutes_lt_5")
            interval_minutes = 60
    else:
        interval_minutes = None
        if not daily_time:
            daily_time = "09:00"
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", daily_time):
            errors.append("heartbeat_task.daily_time_invalid")
            daily_time = "09:00"
    effective_prompt = prompt_template
    if enabled and not prompt_template:
        errors.append("heartbeat_task.prompt_template_missing")
    return {
        "heartbeat_task_id": heartbeat_task_id,
        "title": title,
        "enabled": bool(enabled),
        "channel_name": channel_name,
        "session_id": session_id,
        "preset_key": preset_key,
        "prompt_template": prompt_template,
        "effective_prompt_template": effective_prompt,
        "schedule_type": schedule_type,
        "interval_minutes": int(interval_minutes) if interval_minutes is not None else None,
        "daily_time": daily_time if schedule_type == "daily" else "",
        "weekdays": weekdays,
        "busy_policy": busy_policy,
        "max_execute_count": int(max_execute_count or 0),
        "context_scope": context_scope,
        "ready": bool(enabled and channel_name and session_id and prompt_template and not errors),
        "errors": errors,
        "source": "heartbeat_tasks",
    }


def _normalize_heartbeat_tasks(
    raw: Any,
    *,
    defaults: Optional[dict[str, Any]] = None,
) -> list[dict[str, Any]]:
    rows = raw if isinstance(raw, list) else []
    out: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for idx, item in enumerate(rows):
        row = _normalize_heartbeat_task(item, index=idx, defaults=defaults)
        if not row:
            continue
        tid = str(row.get("heartbeat_task_id") or "").strip()
        if not tid or tid in seen_ids:
            continue
        seen_ids.add(tid)
        out.append(row)
        if len(out) >= 50:
            break
    return out


def _build_default_auto_inspection_task(
    *,
    enabled: bool,
    channel_name: str,
    session_id: str,
    interval_minutes: Optional[int],
    prompt_template: str,
    inspection_targets: list[str],
    auto_inspections: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "inspection_task_id": _DEFAULT_INSPECTION_TASK_ID,
        "title": "默认巡查任务",
        "enabled": bool(enabled),
        "channel_name": str(channel_name or "").strip(),
        "session_id": str(session_id or "").strip(),
        "interval_minutes": int(interval_minutes) if interval_minutes is not None else None,
        "prompt_template": str(prompt_template or "").strip(),
        "inspection_targets": _normalize_inspection_targets(inspection_targets, default=[]),
        "auto_inspections": _normalize_auto_inspections(auto_inspections, fallback_targets=inspection_targets),
        "ready": False,
        "errors": [],
        "source": "legacy_auto_inspection",
    }


def _normalize_auto_inspection_task(
    item: Any,
    *,
    index: int = 0,
    defaults: Optional[dict[str, Any]] = None,
    id_required: bool = False,
) -> Optional[dict[str, Any]]:
    if not isinstance(item, dict):
        return None
    d = defaults if isinstance(defaults, dict) else {}
    fallback_id = f"task-{index + 1}"
    raw_task_id = (
        item.get("inspection_task_id")
        if "inspection_task_id" in item
        else item.get("inspectionTaskId")
    )
    inspection_task_id = _normalize_inspection_task_id(raw_task_id, default=fallback_id)
    if id_required and not str(raw_task_id or "").strip():
        return None
    if not inspection_task_id:
        return None
    title = _safe_text(
        item.get("title")
        if "title" in item
        else (
            item.get("name")
            if "name" in item
            else item.get("display_name")
        ),
        200,
    ).strip()
    if not title:
        title = _safe_text(d.get("title"), 200).strip() or f"巡查任务-{inspection_task_id}"
    enabled_default = _coerce_bool(d.get("enabled"), False)
    enabled = _coerce_bool(item.get("enabled"), enabled_default)
    channel_name = _safe_text(
        item.get("channel_name")
        if "channel_name" in item
        else (
            item.get("channelName")
            if "channelName" in item
            else d.get("channel_name")
        ),
        200,
    ).strip()
    session_id = _safe_text(
        item.get("session_id")
        if "session_id" in item
        else (
            item.get("sessionId")
            if "sessionId" in item
            else d.get("session_id")
        ),
        120,
    ).strip()
    prompt_template = _safe_text(
        item.get("prompt_template")
        if "prompt_template" in item
        else (
            item.get("promptTemplate")
            if "promptTemplate" in item
            else d.get("prompt_template")
        ),
        20_000,
    ).strip()
    interval_raw = (
        item.get("interval_minutes")
        if "interval_minutes" in item
        else (
            item.get("intervalMinutes")
            if "intervalMinutes" in item
            else d.get("interval_minutes")
        )
    )
    interval_minutes: Optional[int] = None
    errors: list[str] = []
    if interval_raw not in (None, "", 0, "0", False):
        interval_minutes = _coerce_int(interval_raw, 30)
        if interval_minutes < 5:
            errors.append("inspection_task.interval_minutes_lt_5")
            interval_minutes = 30
    elif enabled:
        interval_minutes = 30

    inspection_targets_raw = (
        item.get("inspection_targets")
        if "inspection_targets" in item
        else (
            item.get("inspectionTargets")
            if "inspectionTargets" in item
            else d.get("inspection_targets")
        )
    )
    auto_inspections_raw = (
        item.get("auto_inspections")
        if "auto_inspections" in item
        else (
            item.get("autoInspections")
            if "autoInspections" in item
            else d.get("auto_inspections")
        )
    )
    inspection_targets = _normalize_inspection_targets(inspection_targets_raw, default=[])
    auto_inspections = _normalize_auto_inspections(
        auto_inspections_raw,
        fallback_targets=inspection_targets,
    )
    targets_from_objects = _auto_inspection_targets_from_objects(auto_inspections)
    if targets_from_objects:
        inspection_targets = targets_from_objects
    if session_id and not _looks_like_uuid(session_id):
        errors.append("inspection_task.session_id_invalid")
        session_id = ""
    if enabled and not channel_name:
        errors.append("inspection_task.channel_name_missing")
    if enabled and not session_id:
        errors.append("inspection_task.session_id_missing")
    if enabled and not prompt_template:
        errors.append("inspection_task.prompt_template_missing")
    if enabled and not inspection_targets and not auto_inspections:
        inspection_targets = list(_DEFAULT_INSPECTION_TARGETS)
    return {
        "inspection_task_id": inspection_task_id,
        "title": title,
        "enabled": bool(enabled),
        "channel_name": channel_name,
        "session_id": session_id,
        "interval_minutes": int(interval_minutes) if interval_minutes is not None else None,
        "prompt_template": prompt_template,
        "inspection_targets": inspection_targets,
        "auto_inspections": auto_inspections,
        "ready": bool(enabled and channel_name and session_id and prompt_template and (inspection_targets or auto_inspections) and not errors),
        "errors": errors,
        "source": "inspection_tasks",
    }


def _normalize_auto_inspection_tasks(
    raw: Any,
    *,
    defaults: Optional[dict[str, Any]] = None,
    fallback_single_task: Optional[dict[str, Any]] = None,
    has_explicit_field: bool = False,
) -> list[dict[str, Any]]:
    rows = raw if isinstance(raw, list) else []
    out: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for idx, item in enumerate(rows):
        row = _normalize_auto_inspection_task(item, index=idx, defaults=defaults)
        if not row:
            continue
        tid = str(row.get("inspection_task_id") or "").strip()
        if not tid or tid in seen_ids:
            continue
        seen_ids.add(tid)
        out.append(row)
        if len(out) >= 50:
            break
    if out:
        return out
    if has_explicit_field:
        return []
    if isinstance(fallback_single_task, dict):
        single = _normalize_auto_inspection_task(
            fallback_single_task,
            index=0,
            defaults=defaults,
        )
        if single:
            return [single]
    return []


def _select_active_auto_inspection_task(
    tasks: list[dict[str, Any]],
    *,
    active_task_id_hint: str = "",
) -> Optional[dict[str, Any]]:
    if not tasks:
        return None
    hint = _normalize_inspection_task_id(active_task_id_hint)
    if hint:
        for row in tasks:
            if str(row.get("inspection_task_id") or "").strip() == hint:
                return row
    for row in tasks:
        if bool(row.get("enabled")):
            return row
    return tasks[0]


def _inspection_target_tokens(raw: Any) -> list[str]:
    tokens: list[str] = []
    if raw is None:
        return tokens
    values = raw if isinstance(raw, (list, tuple, set)) else [raw]
    for item in values:
        if item is None:
            continue
        txt = str(item).strip().lower().replace("-", "_")
        if not txt:
            continue
        for part in re.split(r"[\s,|]+", txt):
            t = str(part or "").strip()
            if t:
                tokens.append(t)
    return tokens


def _normalize_inspection_targets(raw: Any, default: Optional[list[str]] = None) -> list[str]:
    defaults = list(default) if isinstance(default, list) else []
    out: list[str] = []
    for token in _inspection_target_tokens(raw):
        if token not in _INSPECTION_TARGET_SET:
            continue
        if token in out:
            continue
        out.append(token)
    if out:
        return out
    return [x for x in defaults if x in _INSPECTION_TARGET_SET]


def _auto_inspection_object_key_for_target(target: str) -> str:
    token = str(target or "").strip().lower().replace("-", "_")
    if token not in _INSPECTION_TARGET_SET:
        return ""
    return f"ins-{token}"


def _normalize_auto_inspection_match_values(raw: Any) -> list[str]:
    values = raw if isinstance(raw, list) else []
    out: list[str] = []
    for item in values:
        val = _safe_text(item, 120).strip()
        if not val or val in out:
            continue
        out.append(val)
        if len(out) >= 30:
            break
    return out


def _build_auto_inspections_from_targets(targets: Any, *, source: str = "inspection_targets") -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for token in _normalize_inspection_targets(targets, default=[]):
        object_key = _auto_inspection_object_key_for_target(token)
        if not object_key:
            continue
        out.append(
            {
                "object_key": object_key,
                "object_type": token,
                "display_name": _INSPECTION_TARGET_LABELS.get(token, token),
                "enabled": True,
                "source": source,
                "match_values": [],
            }
        )
    return out


def _normalize_auto_inspection_object(item: Any, *, source_default: str = "auto_inspections") -> Optional[dict[str, Any]]:
    if not isinstance(item, dict):
        return None
    object_key = _safe_text(item.get("object_key") if "object_key" in item else item.get("objectKey"), 120).strip()
    object_type = _safe_text(item.get("object_type") if "object_type" in item else item.get("objectType"), 80).strip().lower()
    object_type = object_type.replace("-", "_")
    if not object_key or object_type not in _AUTO_INSPECTION_OBJECT_TYPE_SET:
        return None
    if "enabled" not in item:
        return None
    enabled = _coerce_bool(item.get("enabled"), False)
    display_name = _safe_text(
        item.get("display_name") if "display_name" in item else item.get("displayName"),
        200,
    ).strip()
    source = _safe_text(item.get("source"), 60).strip().lower() or source_default
    match_values = _normalize_auto_inspection_match_values(
        item.get("match_values") if "match_values" in item else item.get("matchValues")
    )
    if object_type != "custom":
        match_values = []
    return {
        "object_key": object_key,
        "object_type": object_type,
        "display_name": display_name,
        "enabled": bool(enabled),
        "source": source,
        "match_values": match_values,
    }


def _normalize_auto_inspections(raw: Any, *, fallback_targets: Any = None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    rows = raw if isinstance(raw, list) else []
    for item in rows:
        row = _normalize_auto_inspection_object(item)
        if not row:
            continue
        key = str(row.get("object_key") or "").strip()
        if not key or key in seen_keys:
            continue
        seen_keys.add(key)
        out.append(row)
        if len(out) >= 50:
            break
    if out:
        return out
    return _build_auto_inspections_from_targets(fallback_targets, source="inspection_targets")


def _auto_inspection_targets_from_objects(objects: Any) -> list[str]:
    vals = objects if isinstance(objects, list) else []
    out: list[str] = []
    for item in vals:
        if not isinstance(item, dict):
            continue
        if not _coerce_bool(item.get("enabled"), False):
            continue
        object_type = str(item.get("object_type") or "").strip().lower().replace("-", "_")
        if object_type not in _INSPECTION_TARGET_SET:
            continue
        if object_type in out:
            continue
        out.append(object_type)
    return out


def _build_inspection_record_id(
    created_at: str,
    run_id: str,
    target_task_path: str,
    index: int,
) -> str:
    created_token = re.sub(r"[^0-9]", "", str(created_at or ""))[:14] or "0"
    run_token = re.sub(r"[^0-9a-zA-Z]", "", str(run_id or ""))[-8:] or "norun"
    task_token = re.sub(r"[^0-9a-zA-Z]", "", Path(str(target_task_path or "")).stem)[-8:] or "notask"
    idx = max(0, int(index or 0))
    return f"ins-rec-{created_token}-{run_token}-{task_token}-{idx:02d}"


def _normalize_inspection_record(item: Any, *, index: int = 0) -> Optional[dict[str, Any]]:
    if not isinstance(item, dict):
        return None
    created_at = _safe_text(item.get("created_at"), 80).strip() or _now_iso()
    status = str(item.get("status") or "").strip().lower()
    if status not in _AUTO_INSPECTION_RECORD_STATUS:
        status = "error" if status == "failed" else "skipped" if status.startswith("skip") else "dispatched"
        if status not in _AUTO_INSPECTION_RECORD_STATUS:
            status = "error"
    summary = _safe_text(item.get("summary") if "summary" in item else item.get("message_summary"), 500).strip()
    target_task_path = _normalize_task_path_identity(str(item.get("target_task_path") or ""))
    target_channel = _safe_text(item.get("target_channel"), 200).strip()
    run_id = _safe_text(item.get("run_id"), 120).strip()
    skip_reason = _safe_text(item.get("skip_reason"), 120).strip()
    object_key = _safe_text(item.get("object_key") if "object_key" in item else item.get("objectKey"), 120).strip()
    inspection_task_id = _normalize_inspection_task_id(
        item.get("inspection_task_id") if "inspection_task_id" in item else item.get("inspectionTaskId"),
        default=_DEFAULT_INSPECTION_TASK_ID,
    )
    evidence_refs_raw = item.get("evidence_refs") if "evidence_refs" in item else item.get("evidenceRefs")
    evidence_refs = _normalize_auto_inspection_match_values(evidence_refs_raw)
    record_id = _safe_text(item.get("record_id") if "record_id" in item else item.get("recordId"), 160).strip()
    if not record_id:
        record_id = _build_inspection_record_id(created_at, run_id, target_task_path, index)
    return {
        "record_id": record_id,
        "created_at": created_at,
        "status": status,
        "summary": summary,
        "target_task_path": target_task_path,
        "target_channel": target_channel,
        "run_id": run_id,
        "skip_reason": skip_reason,
        "object_key": object_key,
        "inspection_task_id": inspection_task_id or _DEFAULT_INSPECTION_TASK_ID,
        "evidence_refs": evidence_refs,
    }


def _normalize_inspection_records(raw: Any, *, limit: int = _AUTO_INSPECTION_RECORD_LIMIT) -> list[dict[str, Any]]:
    rows = raw if isinstance(raw, list) else []
    out: list[dict[str, Any]] = []
    for idx, item in enumerate(rows):
        row = _normalize_inspection_record(item, index=idx)
        if not row:
            continue
        out.append(row)
        if len(out) >= max(1, min(int(limit or _AUTO_INSPECTION_RECORD_LIMIT), _AUTO_INSPECTION_RECORD_LIMIT)):
            break
    return out


_GUARD_EVENT_LEVEL_ORDER = {"P0": 0, "P1": 1, "P2": 2}


def _normalize_guard_runtime_event(item: Any) -> Optional[dict[str, Any]]:
    if not isinstance(item, dict):
        return None
    level = str(item.get("level") or "").strip().upper()
    if level not in {"P0", "P1", "P2"}:
        level = "P2"
    status = str(item.get("status") or "").strip().lower()
    if status not in {"open", "processing", "resolved", "escalated"}:
        status = "open"
    action_state = str(item.get("action_state") or "").strip().lower()
    if action_state not in {"dispatched", "reminded", "escalated", "closed"}:
        action_state = "dispatched" if status != "resolved" else "closed"
    try:
        sla_minutes = max(1, int(item.get("sla_minutes") or 0))
    except Exception:
        sla_minutes = 60
    hit_count_15m = 0
    try:
        hit_count_15m = max(0, int(item.get("hit_count_15m") or 0))
    except Exception:
        hit_count_15m = 0
    upgrade_reasons = item.get("upgrade_reasons")
    reasons: list[str] = []
    if isinstance(upgrade_reasons, list):
        for x in upgrade_reasons:
            s = str(x or "").strip()
            if s:
                reasons.append(s)
            if len(reasons) >= 8:
                break
    evidence_refs = item.get("evidence_refs")
    refs: list[str] = []
    if isinstance(evidence_refs, list):
        for x in evidence_refs:
            s = str(x or "").strip()
            if s:
                refs.append(s)
            if len(refs) >= 20:
                break
    return {
        "time": _safe_text(item.get("time"), 80).strip(),
        "level": level,
        "status": status,
        "summary": _safe_text(item.get("summary"), 500).strip(),
        "owner_channel": _safe_text(item.get("owner_channel"), 200).strip(),
        "related_run_id": _safe_text(item.get("related_run_id"), 80).strip(),
        "rule_key": _safe_text(item.get("rule_key"), 160).strip(),
        "action_state": action_state,
        "updated_at": _safe_text(item.get("updated_at"), 80).strip(),
        "fatal_hit": bool(item.get("fatal_hit")),
        "fatal_condition": _safe_text(item.get("fatal_condition"), 200).strip(),
        "sla_minutes": sla_minutes,
        "response_due_at": _safe_text(item.get("response_due_at"), 80).strip(),
        "hit_count_15m": hit_count_15m,
        "upgrade_triggered": bool(item.get("upgrade_triggered")),
        "upgrade_reasons": reasons,
        "issue_path": _normalize_task_path_identity(str(item.get("issue_path") or "")),
        "evidence_refs": refs,
    }


def _normalize_guard_runtime_events(raw: Any, *, limit: int = 20) -> list[dict[str, Any]]:
    rows = raw if isinstance(raw, list) else []
    out: list[dict[str, Any]] = []
    max_items = max(1, min(int(limit or 20), 50))
    for item in rows:
        row = _normalize_guard_runtime_event(item)
        if not row:
            continue
        out.append(row)
        if len(out) >= max_items:
            break
    out.sort(key=lambda x: (_GUARD_EVENT_LEVEL_ORDER.get(str(x.get("level") or "P2"), 9), str(x.get("updated_at") or "")), reverse=False)
    return out


def _normalize_guard_runtime_stats(raw: Any) -> dict[str, Any]:
    obj = raw if isinstance(raw, dict) else {}
    recovered_raw = obj.get("recovered_rules")
    recovered: list[str] = []
    if isinstance(recovered_raw, list):
        for item in recovered_raw:
            s = str(item or "").strip()
            if s:
                recovered.append(s)
            if len(recovered) >= 20:
                break
    try:
        open_count = max(0, int(obj.get("open_count") or 0))
    except Exception:
        open_count = 0
    try:
        escalated_count = max(0, int(obj.get("escalated_count") or 0))
    except Exception:
        escalated_count = 0
    return {
        "open_count": open_count,
        "escalated_count": escalated_count,
        "recovered_rules": recovered,
        "updated_at": _safe_text(obj.get("updated_at"), 80).strip(),
    }


def _inspection_record_from_reminder_record(
    row: dict[str, Any],
    *,
    index: int = 0,
    default_object_key: str = "",
    default_inspection_task_id: str = _DEFAULT_INSPECTION_TASK_ID,
) -> dict[str, Any]:
    created_at = _safe_text(row.get("created_at"), 80).strip() or _now_iso()
    run_id = _safe_text(row.get("run_id"), 120).strip()
    target_task_path = _normalize_task_path_identity(str(row.get("target_task_path") or ""))
    data = {
        "record_id": _build_inspection_record_id(created_at, run_id, target_task_path, index),
        "created_at": created_at,
        "status": _safe_text(row.get("status"), 40).strip().lower() or "error",
        "summary": _safe_text(row.get("message_summary"), 500).strip(),
        "target_task_path": target_task_path,
        "target_channel": _safe_text(row.get("target_channel"), 200).strip(),
        "run_id": run_id,
        "skip_reason": _safe_text(row.get("skip_reason"), 120).strip(),
        "object_key": _safe_text(row.get("object_key"), 120).strip() or default_object_key,
        "inspection_task_id": _normalize_inspection_task_id(
            row.get("inspection_task_id"),
            default=default_inspection_task_id or _DEFAULT_INSPECTION_TASK_ID,
        ),
        "evidence_refs": _normalize_auto_inspection_match_values(row.get("evidence_refs")),
    }
    normalized = _normalize_inspection_record(data, index=index)
    return normalized or {
        "record_id": _build_inspection_record_id(created_at, run_id, target_task_path, index),
        "created_at": created_at,
        "status": "error",
        "summary": "",
        "target_task_path": target_task_path,
        "target_channel": "",
        "run_id": run_id,
        "skip_reason": "",
        "object_key": default_object_key,
        "inspection_task_id": _normalize_inspection_task_id(
            row.get("inspection_task_id"),
            default=default_inspection_task_id or _DEFAULT_INSPECTION_TASK_ID,
        ),
        "evidence_refs": [],
    }


def _inspection_records_from_reminder_records(
    reminder_records: Any,
    *,
    auto_inspections: Any = None,
    default_inspection_task_id: str = _DEFAULT_INSPECTION_TASK_ID,
) -> list[dict[str, Any]]:
    reminders = _normalize_auto_inspection_reminder_records(reminder_records)
    objects = _normalize_auto_inspections(auto_inspections, fallback_targets=[])
    enabled_keys = [str(x.get("object_key") or "").strip() for x in objects if bool(x.get("enabled"))]
    default_object_key = enabled_keys[0] if len(enabled_keys) == 1 else ""
    out: list[dict[str, Any]] = []
    for idx, row in enumerate(reminders):
        out.append(
            _inspection_record_from_reminder_record(
                row,
                index=idx,
                default_object_key=default_object_key,
                default_inspection_task_id=default_inspection_task_id,
            )
        )
    return out[:_AUTO_INSPECTION_RECORD_LIMIT]


def _reminder_record_from_inspection_record(item: Any) -> Optional[dict[str, str]]:
    row = _normalize_inspection_record(item)
    if not row:
        return None
    return _normalize_auto_inspection_reminder_record(
        {
            "created_at": row.get("created_at"),
            "status": row.get("status"),
            "message_summary": row.get("summary"),
            "target_task_path": row.get("target_task_path"),
            "target_channel": row.get("target_channel"),
            "run_id": row.get("run_id"),
            "skip_reason": row.get("skip_reason"),
            "object_key": row.get("object_key"),
            "inspection_task_id": row.get("inspection_task_id"),
            "evidence_refs": row.get("evidence_refs"),
        }
    )


def _reminder_records_from_inspection_records(records: Any) -> list[dict[str, str]]:
    rows = records if isinstance(records, list) else []
    out: list[dict[str, str]] = []
    for item in rows:
        row = _reminder_record_from_inspection_record(item)
        if not row:
            continue
        out.append(row)
        if len(out) >= _AUTO_INSPECTION_RECORD_LIMIT:
            break
    return out


_RUNTIME_BUBBLE_ACTIVE_STATUSES = {"queued", "retry_waiting", "running", "dispatching", "collecting", "scanning"}
_RUNTIME_BUBBLE_TERMINAL_STATUSES = {"done", "error"}
_RUNTIME_BUBBLE_STATUS_LABELS = {
    "queued": "排队中",
    "retry_waiting": "等待重试",
    "running": "执行中",
    "dispatching": "派发中",
    "collecting": "收集中",
    "scanning": "扫描中",
    "done": "已完成",
    "error": "异常",
}
_RUNTIME_BUBBLE_STATUS_TONES = {
    "queued": "warn",
    "retry_waiting": "warn",
    "running": "warn",
    "dispatching": "warn",
    "collecting": "warn",
    "scanning": "warn",
    "done": "good",
    "error": "bad",
}
_RUNTIME_BUBBLE_TTL_SECONDS = 60
_RUNTIME_RELATION_TTL_SECONDS = 90


def _runtime_bubble_status_label(status: Any) -> str:
    key = str(status or "").strip().lower()
    return _RUNTIME_BUBBLE_STATUS_LABELS.get(key, key or "未知")


def _runtime_bubble_status_tone(status: Any) -> str:
    key = str(status or "").strip().lower()
    return _RUNTIME_BUBBLE_STATUS_TONES.get(key, "muted")


def _iso_from_ts(ts: float) -> str:
    try:
        if float(ts) <= 0:
            return ""
    except Exception:
        return ""
    return time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(float(ts)))


def _runtime_related_objects_from_meta(meta: dict[str, Any]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    seen: set[str] = set()

    def _push(obj_type: str, key: Any, label: Any) -> None:
        k = str(key or "").strip()
        if not k:
            return
        uniq = f"{obj_type}:{k}"
        if uniq in seen:
            return
        seen.add(uniq)
        out.append({"type": obj_type, "key": k, "label": str(label or k).strip() or k})

    channel_name = str(meta.get("channelName") or "").strip()
    session_id = str(meta.get("sessionId") or "").strip()
    sender_name = str(meta.get("sender_name") or meta.get("senderName") or "").strip()
    sender_id = str(meta.get("sender_id") or "").strip()
    sender_type = str(meta.get("sender_type") or "").strip()

    if channel_name:
        _push("channel", channel_name, channel_name)
    if session_id:
        short_sid = session_id
        if len(session_id) >= 12:
            short_sid = session_id[:8] + "..." + session_id[-4:]
        _push("session", session_id, short_sid)
    if sender_name or sender_id:
        sender_key = sender_id or sender_name
        sender_label = sender_name or sender_id
        if sender_type:
            sender_label = f"{sender_type}:{sender_label}"
        _push("sender", sender_key, sender_label)
    return out


def _runtime_expire_at_from_base(base_ts: float, ttl_seconds: int) -> str:
    try:
        if float(base_ts) <= 0:
            return ""
    except Exception:
        return ""
    ttl = max(1, int(ttl_seconds or 0))
    return _iso_from_ts(float(base_ts) + float(ttl))


def _runtime_relations_from_meta(
    *,
    meta: dict[str, Any],
    project_id: str,
    run_id: str,
    status: str,
    created_at: str,
    started_at: str,
    finished_at: str,
    updated_at: str,
) -> list[dict[str, Any]]:
    source_agent_id = str(meta.get("sessionId") or "").strip()
    if not source_agent_id:
        return []
    source_channel_name = str(meta.get("channelName") or "").strip()
    callback_to = _normalize_callback_to(meta.get("callback_to"))

    targets: list[dict[str, str]] = []
    if isinstance(callback_to, dict):
        cb_sid = str(callback_to.get("session_id") or "").strip()
        cb_channel = str(callback_to.get("channel_name") or "").strip()
        if cb_sid:
            targets.append(
                {
                    "target_agent_id": cb_sid,
                    "target_channel_name": cb_channel,
                    "reason": "callback_to",
                }
            )
        elif cb_channel:
            targets.append(
                {
                    "target_agent_id": "",
                    "target_channel_name": cb_channel,
                    "reason": "callback_to_channel",
                }
            )

    sender_id = str(meta.get("sender_id") or "").strip()
    sender_type = str(meta.get("sender_type") or "").strip().lower()
    if sender_id and sender_id != source_agent_id and sender_type in {"agent", "system", "user"}:
        targets.append(
            {
                "target_agent_id": sender_id,
                "target_channel_name": "",
                "reason": f"sender_{sender_type}",
            }
        )

    if not targets:
        return []

    started_ts = _parse_rfc3339_ts(started_at) if started_at else 0.0
    created_ts = _parse_rfc3339_ts(created_at) if created_at else 0.0
    finished_ts = _parse_rfc3339_ts(finished_at) if finished_at else 0.0
    updated_ts = _parse_rfc3339_ts(updated_at) if updated_at else 0.0
    started_iso = started_at or created_at
    ttl_seconds = _RUNTIME_RELATION_TTL_SECONDS
    base_ts = finished_ts if status in _RUNTIME_BUBBLE_TERMINAL_STATUSES else (updated_ts or started_ts or created_ts)
    expires_at = _runtime_expire_at_from_base(base_ts, ttl_seconds)

    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for target in targets:
        target_agent_id = str(target.get("target_agent_id") or "").strip()
        target_channel_name = str(target.get("target_channel_name") or "").strip()
        reason = str(target.get("reason") or "").strip() or "runtime_link"
        target_key = target_agent_id or f"channel:{target_channel_name}"
        if not target_key:
            continue
        uniq = f"{source_agent_id}|{target_key}|{reason}"
        if uniq in seen:
            continue
        seen.add(uniq)
        out.append(
            {
                "runtime_id": f"runtime:{run_id}:{uniq}",
                "project_id": project_id,
                "source_agent_id": source_agent_id,
                "target_agent_id": target_agent_id,
                "source_channel_name": source_channel_name,
                "target_channel_name": target_channel_name,
                "reason": reason,
                "started_at": started_iso,
                "ttl_seconds": ttl_seconds,
                "expires_at": expires_at,
                "related_run_id": run_id,
                "active": status in _RUNTIME_BUBBLE_ACTIVE_STATUSES,
            }
        )
    return out


def _build_runtime_bubbles_payload(
    store: "RunStore",
    project_id: str,
    *,
    session_store: Optional[SessionStore] = None,
    channel_name: str = "",
    session_id: str = "",
    limit: int = 80,
    bubble_limit: int = 40,
    max_related_objects: int = 2,
) -> dict[str, Any]:
    pid = str(project_id or "").strip()
    cname = str(channel_name or "").strip()
    sid = str(session_id or "").strip()
    run_limit = max(1, min(300, int(limit or 80)))
    bubble_limit = max(1, min(200, int(bubble_limit or 40)))
    max_related = max(1, min(5, int(max_related_objects or 2)))

    runs = store.list_runs(project_id=pid, session_id=sid, limit=run_limit, include_payload=False)
    if cname:
        runs = [m for m in runs if str(m.get("channelName") or "").strip() == cname]
    project_agent_ids: set[str] = set()
    for meta in runs:
        sid_meta = str((meta or {}).get("sessionId") or "").strip()
        if sid_meta:
            project_agent_ids.add(sid_meta)
    if session_store is not None:
        try:
            sess_rows = session_store.list_sessions(pid)
        except Exception:
            sess_rows = []
        if isinstance(sess_rows, list):
            for row in sess_rows:
                if not isinstance(row, dict):
                    continue
                sid_row = str(row.get("id") or "").strip()
                if sid_row:
                    project_agent_ids.add(sid_row)
    now_ts = time.time()

    events: list[dict[str, Any]] = []
    runtime_relations: list[dict[str, Any]] = []
    relation_seen: set[str] = set()
    for meta in runs:
        rid = str(meta.get("id") or "").strip()
        status = str(meta.get("status") or "").strip().lower()
        created_at = str(meta.get("createdAt") or "").strip()
        started_at = str(meta.get("startedAt") or "").strip()
        finished_at = str(meta.get("finishedAt") or "").strip()
        updated_at = str(meta.get("lastProgressAt") or finished_at or started_at or created_at).strip()
        created_ts = _parse_rfc3339_ts(created_at) if created_at else 0.0
        started_ts = _parse_rfc3339_ts(started_at) if started_at else 0.0
        finished_ts = _parse_rfc3339_ts(finished_at) if finished_at else 0.0
        updated_ts = _parse_rfc3339_ts(updated_at) if updated_at else 0.0
        active = status in _RUNTIME_BUBBLE_ACTIVE_STATUSES
        terminal = status in _RUNTIME_BUBBLE_TERMINAL_STATUSES

        elapsed_ms = 0
        duration_ms = 0
        if started_ts > 0:
            end_ts = finished_ts if finished_ts > 0 else now_ts
            elapsed_ms = max(0, int((end_ts - started_ts) * 1000))
            if finished_ts > 0:
                duration_ms = elapsed_ms
        elif status in {"queued", "retry_waiting"} and created_ts > 0:
            elapsed_ms = max(0, int((now_ts - created_ts) * 1000))

        related = _runtime_related_objects_from_meta(meta)
        primary_related = related[:max_related]
        extra_related_count = max(0, len(related) - len(primary_related))
        ttl_seconds = _RUNTIME_BUBBLE_TTL_SECONDS
        event_expires_at = ""
        if terminal:
            base_ts = finished_ts if finished_ts > 0 else (updated_ts if updated_ts > 0 else 0.0)
            event_expires_at = _runtime_expire_at_from_base(base_ts, ttl_seconds)

        events.append(
            {
                "event_id": f"run:{rid}:{status or 'unknown'}",
                "event_type": "run_status",
                "source_run_id": rid,
                "project_id": pid,
                "channel_name": str(meta.get("channelName") or "").strip(),
                "session_id": str(meta.get("sessionId") or "").strip(),
                "status": status or "unknown",
                "status_label": _runtime_bubble_status_label(status),
                "tone": _runtime_bubble_status_tone(status),
                "active": active,
                "terminal": terminal,
                "created_at": created_at,
                "started_at": started_at,
                "finished_at": finished_at,
                "updated_at": updated_at,
                "updated_ts": updated_ts,
                "elapsed_ms": elapsed_ms,
                "duration_ms": duration_ms,
                "related_objects": primary_related,
                "related_object_count": len(related),
                "related_object_extra_count": extra_related_count,
                "ttl_seconds": ttl_seconds,
                "expires_at": event_expires_at,
            }
        )
        for rel in _runtime_relations_from_meta(
            meta=meta,
            project_id=pid,
            run_id=rid,
            status=status,
            created_at=created_at,
            started_at=started_at,
            finished_at=finished_at,
            updated_at=updated_at,
        ):
            src_sid = str(rel.get("source_agent_id") or "").strip()
            dst_sid = str(rel.get("target_agent_id") or "").strip()
            if not src_sid or not dst_sid:
                continue
            if project_agent_ids and (src_sid not in project_agent_ids or dst_sid not in project_agent_ids):
                continue
            rel_key = str(rel.get("runtime_id") or "").strip()
            if not rel_key or rel_key in relation_seen:
                continue
            relation_seen.add(rel_key)
            runtime_relations.append(rel)

    events.sort(key=lambda x: float(x.get("updated_ts") or 0), reverse=True)

    bubbles: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for ev in events:
        bubble_key = "|".join(
            [
                str(ev.get("channel_name") or ""),
                str(ev.get("session_id") or ""),
                str(ev.get("status") or ""),
            ]
        )
        if bubble_key in seen_keys:
            continue
        seen_keys.add(bubble_key)
        expires_at = ""
        ttl_seconds = _RUNTIME_BUBBLE_TTL_SECONDS
        if bool(ev.get("terminal")):
            end_ts = _parse_rfc3339_ts(ev.get("finished_at")) if str(ev.get("finished_at") or "").strip() else 0.0
            if end_ts <= 0:
                end_ts = _parse_rfc3339_ts(ev.get("updated_at")) if str(ev.get("updated_at") or "").strip() else 0.0
            if end_ts > 0:
                expires_at = _runtime_expire_at_from_base(end_ts, ttl_seconds)
        bubbles.append(
            {
                "bubble_key": bubble_key,
                "source_run_id": str(ev.get("source_run_id") or ""),
                "status": str(ev.get("status") or ""),
                "status_label": str(ev.get("status_label") or ""),
                "tone": str(ev.get("tone") or "muted"),
                "active": bool(ev.get("active")),
                "created_at": str(ev.get("created_at") or ""),
                "updated_at": str(ev.get("updated_at") or ""),
                "started_at": str(ev.get("started_at") or ""),
                "finished_at": str(ev.get("finished_at") or ""),
                "elapsed_ms": int(ev.get("elapsed_ms") or 0),
                "duration_ms": int(ev.get("duration_ms") or 0),
                "expire_at": expires_at,
                "expires_at": expires_at,
                "ttl_seconds": ttl_seconds,
                "related_objects": list(ev.get("related_objects") or []),
                "related_object_count": int(ev.get("related_object_count") or 0),
                "related_object_extra_count": int(ev.get("related_object_extra_count") or 0),
            }
        )
        if len(bubbles) >= bubble_limit:
            break

    return {
        "project_id": pid,
        "channel_name": cname,
        "session_id": sid,
        "runtime_events": events,
        "runtime_bubbles": bubbles,
        "runtime_relations": runtime_relations,
        "counts": {
            "events": len(events),
            "bubbles": len(bubbles),
            "relations": len(runtime_relations),
        },
    }


def _extract_status_from_task_filename(task_path: str) -> str:
    name = Path(str(task_path or "")).name
    hits = re.findall(r"【([^】]+)】", name)
    if not hits:
        return ""
    return str(hits[0] or "").strip()


def _task_lane_from_bucket(bucket: str) -> str:
    b = str(bucket or "").strip()
    if b in {"督办", "进行中"}:
        return "进行中"
    if b in {"待处理", "待消费", "待验收"}:
        return "待处理"
    if b == "待开始":
        return "待开始"
    if b == "已完成":
        return "已完成"
    return "已归档"


def _scan_project_task_items(project_id: str, root: Path) -> list[dict[str, Any]]:
    pid = str(project_id or "").strip()
    repo_root = _repo_root().resolve()
    rows: list[dict[str, Any]] = []
    for p in root.rglob("*.md"):
        try:
            if not p.is_file():
                continue
            rel_parts = p.relative_to(root).parts
        except Exception:
            continue
        if "任务" not in rel_parts:
            continue
        task_idx = rel_parts.index("任务")
        if task_idx <= 0:
            continue
        task_path = _normalize_task_path_identity(str(p))
        if not task_path:
            continue
        resolved_pid, channel_name, bucket = _resolve_task_project_channel(task_path, project_hint=pid)
        if resolved_pid and resolved_pid != pid:
            continue
        if bucket and bucket != "任务":
            continue
        status = _extract_status_from_task_filename(task_path)
        status_bucket = bucket_key_for_status(status)
        try:
            st = p.stat()
            updated_ts = float(st.st_mtime)
        except Exception:
            updated_ts = 0.0
        updated_at = (
            time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(updated_ts))
            if updated_ts > 0
            else ""
        )
        rows.append(
            {
                "task_path": task_path,
                "title": _extract_task_title(task_path),
                "status": status,
                "status_bucket": status_bucket,
                "lane": _task_lane_from_bucket(status_bucket),
                "channel_name": str(channel_name or rel_parts[task_idx - 1] or "").strip(),
                "updated_at": updated_at,
                "updated_ts": updated_ts,
                "exists": True,
            }
        )
    rows.sort(key=lambda x: float(x.get("updated_ts") or 0), reverse=True)
    return rows


def _list_project_task_items(project_id: str, *, use_cache: bool = True) -> list[dict[str, Any]]:
    try:
        import server

        override = getattr(server, "_list_project_task_items", None)
        if callable(override) and override is not _list_project_task_items:
            return list(override(project_id, use_cache=use_cache) or [])
    except Exception:
        pass
    pid = str(project_id or "").strip()
    root = _resolve_project_task_root(pid)
    if root is None or (not root.exists()) or (not root.is_dir()):
        return []
    try:
        root_key = str(root.resolve())
    except Exception:
        root_key = str(root)
    cache_key = f"{pid}|{root_key}"
    if (not use_cache) or (not _task_items_cache_enabled()):
        return _scan_project_task_items(pid, root)

    ttl_s = _task_items_cache_ttl_s()
    now_mono = time.monotonic()
    with _project_task_items_cache_lock():
        cached = _project_task_items_cache().get(cache_key)
        if isinstance(cached, dict):
            rows = cached.get("rows")
            fetched_at = float(cached.get("fetched_at_mono") or 0.0)
            if isinstance(rows, list) and (now_mono - fetched_at) <= ttl_s:
                return [dict(x) for x in rows if isinstance(x, dict)]

    rows = _scan_project_task_items(pid, root)
    with _project_task_items_cache_lock():
        cache = _project_task_items_cache()
        cache[cache_key] = {
            "rows": rows,
            "fetched_at_mono": now_mono,
        }
        if len(cache) > 128:
            # 清理过旧项，避免长期运行时缓存失控。
            stale_keys = sorted(
                cache.keys(),
                key=lambda k: float((cache.get(k) or {}).get("fetched_at_mono") or 0.0),
            )[:-64]
            for key in stale_keys:
                cache.pop(key, None)
    return [dict(x) for x in rows if isinstance(x, dict)]


def _resolve_project_task_abs_path(project_id: str, task_path: str) -> Optional[Path]:
    pid = str(project_id or "").strip()
    norm = _normalize_task_path_identity(task_path)
    if not norm:
        return None
    repo_root = _repo_root().resolve()
    direct = repo_root / norm
    try:
        if direct.exists() and direct.is_file():
            return direct
    except Exception:
        pass

    task_root = _resolve_project_task_root(pid)
    if task_root is None:
        return None
    try:
        task_root_resolved = task_root.resolve()
    except Exception:
        task_root_resolved = task_root

    candidates: list[Path] = []
    task_root_rel = ""
    try:
        task_root_rel = _normalize_task_path_identity(str(task_root_resolved.relative_to(repo_root)))
    except Exception:
        task_root_rel = _normalize_task_path_identity(str(task_root_resolved))
    if task_root_rel and norm.startswith(task_root_rel + "/"):
        tail = norm[len(task_root_rel) + 1 :]
        if tail:
            candidates.append(task_root_resolved / tail)
    if norm.startswith("任务规划/"):
        tail = norm[len("任务规划/") :]
        if tail:
            candidates.append(task_root_resolved / tail)
    marker = "任务规划/"
    idx = norm.find(marker)
    if idx >= 0:
        tail = norm[idx + len(marker) :]
        if tail:
            candidates.append(task_root_resolved / tail)
    candidates.append(task_root_resolved / norm)

    seen: set[str] = set()
    for cand in candidates:
        key = str(cand)
        if key in seen:
            continue
        seen.add(key)
        try:
            if cand.exists() and cand.is_file():
                return cand
        except Exception:
            continue
    return None


def _build_project_task_item_from_path(project_id: str, task_path: str) -> Optional[dict[str, Any]]:
    pid = str(project_id or "").strip()
    path_txt = _normalize_task_path_identity(task_path)
    if not path_txt:
        return None
    resolved_pid, channel_name, bucket = _resolve_task_project_channel(path_txt, project_hint=pid)
    if resolved_pid and resolved_pid != pid:
        return None
    if bucket and bucket != "任务":
        return None
    abs_path = _resolve_project_task_abs_path(pid, path_txt)
    if abs_path is None:
        return None
    try:
        st = abs_path.stat()
        updated_ts = float(st.st_mtime)
    except Exception:
        updated_ts = 0.0
    updated_at = (
        time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(updated_ts))
        if updated_ts > 0
        else ""
    )
    status = _extract_status_from_task_filename(path_txt)
    status_bucket = bucket_key_for_status(status)
    return {
        "task_path": path_txt,
        "title": _extract_task_title(path_txt),
        "status": status,
        "status_bucket": status_bucket,
        "lane": _task_lane_from_bucket(status_bucket),
        "channel_name": str(channel_name or "").strip(),
        "updated_at": updated_at,
        "updated_ts": updated_ts,
        "exists": True,
    }


def _promote_auto_inspection_task_to_in_progress(
    store: "RunStore",
    project_id: str,
    task_path: str,
) -> dict[str, Any]:
    """
    Promote task status from pending to in-progress when auto inspection dispatch succeeds.

    Pending statuses:
    - 待处理
    - 待开始
    """
    pid = str(project_id or "").strip()
    out: dict[str, Any] = {
        "changed": False,
        "old_task_path": "",
        "new_task_path": "",
        "old_status": "",
        "new_status": "",
        "queue_updated": False,
        "reason": "",
    }
    if not pid:
        out["reason"] = "missing_project_id"
        return out
    norm = _normalize_task_path_identity(task_path)
    if not norm:
        out["reason"] = "missing_task_path"
        return out
    old_path = norm
    out["old_task_path"] = old_path
    row = _build_project_task_item_from_path(pid, old_path)
    if not row:
        out["reason"] = "task_not_found"
        out["new_task_path"] = old_path
        return out

    old_status = str(row.get("status") or "").strip()
    old_bucket = str(row.get("status_bucket") or "").strip()
    out["old_status"] = old_status
    if old_bucket not in {"待处理", "待开始"}:
        out["reason"] = "status_not_pending"
        out["new_task_path"] = old_path
        return out

    try:
        changed = _change_task_status(old_path, "进行中")
    except Exception as e:
        out["reason"] = f"change_status_error:{type(e).__name__}"
        out["new_task_path"] = old_path
        return out

    new_path = _normalize_task_path_identity(str(changed.get("new_path") or "")) or old_path
    out.update(
        {
            "changed": True,
            "new_task_path": new_path,
            "new_status": "进行中",
            "reason": "promoted",
        }
    )
    if new_path == old_path:
        return out
    return out


def _matches_inspection_target(target: str, status_bucket: str) -> bool:
    t = str(target or "").strip().lower()
    b = str(status_bucket or "").strip()
    if t == "in_progress":
        return b in {"督办", "进行中"}
    if t == "pending":
        return b in {"待处理", "待消费"}
    if t == "todo":
        return b == "待开始"
    if t == "pending_acceptance":
        return b == "待验收"
    return False


def _collect_auto_inspection_candidates(
    store: "RunStore",
    project_id: str,
    inspection_targets: list[str],
    *,
    limit: int = 20,
) -> dict[str, Any]:
    pid = str(project_id or "").strip()
    targets = _normalize_inspection_targets(inspection_targets, default=_DEFAULT_INSPECTION_TARGETS)
    all_items: list[dict[str, Any]] = []
    by_path: dict[str, dict[str, Any]] = {}
    by_tail: dict[str, dict[str, Any]] = {}
    indexes_loaded = False
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    skipped_done = 0
    skipped_dedupe = 0
    skipped_missing = 0
    alias_hit = 0

    def _ensure_indexes() -> None:
        nonlocal indexes_loaded, all_items
        if indexes_loaded:
            return
        indexes_loaded = True
        all_items = _list_project_task_items(pid, use_cache=True)
        by_path.clear()
        by_tail.clear()
        for row in all_items:
            if not isinstance(row, dict):
                continue
            rp = _normalize_task_path_identity(str(row.get("task_path") or ""))
            if not rp:
                continue
            by_path[rp] = row
            marker = "任务规划/"
            idx = rp.find(marker)
            if idx < 0:
                continue
            tail = rp[idx:]
            # 只在唯一 tail 时启用兜底，避免跨项目/跨目录误命中。
            if tail in by_tail and by_tail[tail] is not row:
                by_tail[tail] = {}
            else:
                by_tail[tail] = row

    def _resolve_row(path_txt: str) -> Optional[dict[str, Any]]:
        nonlocal alias_hit
        norm = _normalize_task_path_identity(path_txt)
        if not norm:
            return None
        precise = _build_project_task_item_from_path(pid, norm)
        if precise:
            return precise
        _ensure_indexes()
        row = by_path.get(norm)
        if isinstance(row, dict) and row:
            return row
        marker = "任务规划/"
        idx = norm.find(marker)
        if idx >= 0:
            tail = norm[idx:]
            row3 = by_tail.get(tail)
            if isinstance(row3, dict) and row3:
                alias_hit += 1
                return row3
        return None

    def _append_candidate(path_txt: str, source: str) -> None:
        nonlocal skipped_done, skipped_dedupe, skipped_missing
        norm = _normalize_task_path_identity(path_txt)
        if not norm:
            return
        if norm in seen:
            skipped_dedupe += 1
            return
        row = _resolve_row(norm)
        if not row:
            skipped_missing += 1
            return
        row_path = _normalize_task_path_identity(str(row.get("task_path") or norm))
        if row_path in seen:
            skipped_dedupe += 1
            return
        bucket = str(row.get("status_bucket") or "")
        if bucket in {"已完成", "已暂停"}:
            skipped_done += 1
            return
        seen.add(norm)
        seen.add(row_path)
        selected.append(
            {
                "task_path": row_path or norm,
                "title": str(row.get("title") or ""),
                "status": str(row.get("status") or ""),
                "status_bucket": bucket,
                "channel_name": str(row.get("channel_name") or ""),
                "owner_primary_session_id": str(
                    ((_resolve_primary_target_by_channel(pid, str(row.get("channel_name") or "")) or {}).get("session_id") or "")
                ),
                "target_source": source,
                "updated_at": str(row.get("updated_at") or ""),
                "updated_ts": float(row.get("updated_ts") or 0),
            }
        )

    if len(selected) < limit:
        _ensure_indexes()
        for target in targets:
            for row in all_items:
                bucket = str(row.get("status_bucket") or "")
                if not _matches_inspection_target(target, bucket):
                    continue
                _append_candidate(str(row.get("task_path") or ""), target)
                if len(selected) >= limit:
                    break
            if len(selected) >= limit:
                break

    summary = {
        "targets": targets,
        "selected_count": len(selected),
        "skipped_done": skipped_done,
        "skipped_dedupe": skipped_dedupe,
        "skipped_missing": skipped_missing,
        "alias_hit": alias_hit,
    }
    return {"candidates": selected[: max(1, min(100, int(limit or 20)))], "summary": summary}


def _build_auto_inspection_prompt(
    base_prompt: str,
    *,
    candidates: list[dict[str, Any]],
    summary: dict[str, Any],
) -> str:
    prompt_raw = str(base_prompt or "").strip()
    prompt_scan = prompt_raw.replace("\\r\\n", "\n").replace("\\n", "\n")
    # 下线历史冗余段，避免把“固定文案+格式要求”重复塞进自动巡查提示。
    skip_section_markers = (
        "【对话方式】发送消息时使用 agent 主体标签",
        "【输出格式】单个JSON对象",
        "固定督办句（仅此一处）",
        "【发送动作】task_push.send_now",
        "执行口径：",
        "【筛选摘要】",
        "【执行提示】",
    )
    drop_line_markers = (
        "请在本轮给出当前状态、阻塞点、下一步计划。",
        "【自动巡查】任务已逾期未推进，请立即开始处理：{task_id}",
    )
    cleaned_lines: list[str] = []
    skipping_legacy_section = False
    for raw_line in prompt_scan.splitlines():
        line = str(raw_line or "")
        text = line.strip()
        is_header = bool(text.startswith("【") and "】" in text)
        if skipping_legacy_section:
            if not is_header:
                continue
            skipping_legacy_section = False
        if any(marker in text for marker in skip_section_markers):
            skipping_legacy_section = True
            continue
        if any(marker in text for marker in drop_line_markers):
            continue
        cleaned_lines.append(line)
    prompt = "\n".join(cleaned_lines).strip()
    if prompt:
        return prompt
    # 避免全部清洗后为空，保留最小可执行提示，但不再拼接候选任务尾段。
    return "请执行自动巡查并推进首个候选任务。"


def _extract_auto_inspection_structured_payload(text: str) -> dict[str, Any]:
    raw = str(text or "")
    if not raw:
        return {}

    fenced_json_pattern = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)
    for match in fenced_json_pattern.finditer(raw):
        try:
            payload = json.loads(match.group(1).strip())
        except Exception:
            continue
        if isinstance(payload, dict):
            return payload

    start = raw.find("{")
    if start < 0:
        return {}
    depth = 0
    in_str = False
    escaped = False
    for idx in range(start, len(raw)):
        ch = raw[idx]
        if in_str:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                candidate = raw[start : idx + 1]
                try:
                    payload = json.loads(candidate)
                except Exception:
                    continue
                if isinstance(payload, dict):
                    return payload
    return {}


def _auto_inspection_has_execution_evidence(text: str) -> bool:
    body = str(text or "").strip()
    if not body:
        return False
    payload = _extract_auto_inspection_structured_payload(body)
    if payload:
        evidences = payload.get("evidence_paths")
        if isinstance(evidences, list):
            for item in evidences:
                if _safe_text(item, 400).strip():
                    return True
        if _safe_text(payload.get("run_id"), 120).strip():
            return True
    body_l = body.lower()
    if re.search(r"\b20\d{6}-\d{6}-[0-9a-f]{8}\b", body_l):
        return True
    if re.search(r"\b(run_id|job_id|dispatch_state)\b", body_l):
        return True
    if "任务规划/" in body and ".md" in body:
        return True
    return any(token in body_l for token in _AUTO_INSPECTION_EXECUTION_HINTS)


def _classify_auto_inspection_execution_result(store: "RunStore", run_id: str) -> dict[str, str]:
    rid = str(run_id or "").strip()
    if not rid:
        return {"state": "", "reason": "missing_run_id"}
    meta = store.load_meta(rid) or {}
    st = str(meta.get("status") or "").strip().lower()
    if st in {"queued", "running", "retry_waiting"}:
        return {"state": "pending", "reason": st or "pending"}
    if st == "error":
        return {"state": "error", "reason": str(meta.get("error") or "run_error")[:200]}
    evidence_texts = [
        str(store.read_last(rid, limit_chars=12000) or "").strip(),
        str(store.read_log(rid, limit_chars=12000) or "").strip(),
        str(meta.get("lastPreview") or "").strip(),
        str(meta.get("partialPreview") or "").strip(),
    ]
    if any(_auto_inspection_has_execution_evidence(txt) for txt in evidence_texts if txt):
        return {"state": "effective", "reason": "evidence_detected"}
    return {"state": "advice_only", "reason": "missing_execution_evidence"}


def _resolve_cli_type_for_session(
    session_store: SessionStore,
    project_id: str,
    session_id: str,
    fallback_cli_type: str = "codex",
) -> str:
    sid = str(session_id or "").strip()
    if not sid:
        return str(fallback_cli_type or "codex").strip() or "codex"

    row = session_store.get_session(sid)
    if row:
        ctype = str(row.get("cli_type") or "").strip()
        if ctype:
            return ctype

    return str(fallback_cli_type or "codex").strip() or "codex"


def _resolve_model_for_session(
    session_store: SessionStore,
    project_id: str,
    session_id: str,
) -> str:
    sid = str(session_id or "").strip()
    if not sid:
        return ""

    row = session_store.get_session(sid)
    if row:
        model = str(row.get("model") or "").strip()
        if model:
            return model
        channel_name = str(row.get("channel_name") or row.get("channelName") or "").strip()
        if channel_name:
            cfg_model = __getattr__("_project_channel_model")(project_id, channel_name)
            if cfg_model:
                return cfg_model

    return ""


def _resolve_reasoning_effort_for_session(
    session_store: SessionStore,
    project_id: str,
    session_id: str,
) -> str:
    sid = str(session_id or "").strip()
    if not sid:
        return ""

    row = session_store.get_session(sid)
    if row:
        effort = _normalize_reasoning_effort(row.get("reasoning_effort"))
        if effort:
            return effort
        channel_name = str(row.get("channel_name") or row.get("channelName") or "").strip()
        if channel_name:
            cfg_effort = __getattr__("_project_channel_reasoning_effort")(project_id, channel_name)
            if cfg_effort:
                return cfg_effort

    return ""


def _enqueue_run_for_dispatch(
    store: "RunStore",
    run_id: str,
    session_id: str,
    cli_type: str,
    scheduler: Optional["RunScheduler"],
) -> None:
    if scheduler is None or str(os.environ.get("CCB_SCHEDULER") or "").strip() == "0":
        from task_dashboard.runtime.execution_runtime import run_cli_exec as runtime_run_cli_exec

        t = threading.Thread(target=runtime_run_cli_exec, args=(store, run_id, None, cli_type), daemon=True)
        t.start()
    else:
        scheduler.enqueue(run_id, session_id, cli_type=cli_type)


def _task_push_active_state(
    store: "RunStore",
    project_id: str,
    session_id: str,
) -> dict[str, Any]:
    sid = str(session_id or "").strip()
    if not sid:
        return {"active": False, "status": "", "run_id": "", "checked_at": _now_iso()}
    runs = store.list_runs(project_id=str(project_id or "").strip(), session_id=sid, limit=1, include_payload=False)
    if not runs:
        return {"active": False, "status": "", "run_id": "", "checked_at": _now_iso()}
    latest = runs[0] if isinstance(runs[0], dict) else {}
    st = str(latest.get("status") or "").strip().lower()
    rid = str(latest.get("id") or "").strip()
    active = st in {"running", "queued", "retry_waiting"}
    return {"active": active, "status": st, "run_id": rid, "checked_at": _now_iso()}


def _resolve_auto_kickoff_target_session(
    session_store: Optional["SessionStore"],
    project_id: str,
    channel_name: str,
) -> dict[str, str]:
    pid = str(project_id or "").strip()
    cname = str(channel_name or "").strip()
    if session_store is None or not pid or not cname:
        return {}

    row = session_store.get_channel_default_session(pid, cname)
    if not isinstance(row, dict):
        return {}

    sid = str(row.get("id") or "").strip()
    if not sid or not _looks_like_uuid(sid):
        return {}

    cli_type = str(row.get("cli_type") or "").strip() or _project_channel_cli_type(pid, cname)
    return {
        "channel_name": cname,
        "session_id": sid,
        "source": "session_store",
        "cli_type": cli_type,
    }


def _resolve_channel_primary_session_id(
    session_store: Optional["SessionStore"],
    project_id: str,
    channel_name: str,
) -> str:
    pid = str(project_id or "").strip()
    cname = str(channel_name or "").strip()
    if not pid or not cname:
        return ""
    if session_store is not None:
        target = _resolve_auto_kickoff_target_session(session_store, pid, cname)
        sid = str((target or {}).get("session_id") or "").strip()
        if sid and _looks_like_uuid(sid):
            return sid
    fallback = _resolve_primary_target_by_channel(pid, cname)
    sid = str((fallback or {}).get("session_id") or "").strip()
    if sid and _looks_like_uuid(sid):
        return sid
    return ""


def _apply_effective_primary_flags(
    session_store: Optional["SessionStore"],
    project_id: str,
    sessions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Keep per-session `is_primary` aligned with the effective channel primary.

    Historical project data may keep stale `is_primary=false` on every row while
    channel-level primary routing already points to one concrete session id.
    The UI renders 主/子标签 from row-level `is_primary`, so read APIs must
    reconcile rows with the current effective primary_session_id.
    """
    pid = str(project_id or "").strip()
    rows = [dict(row) for row in (sessions or []) if isinstance(row, dict)]
    if not pid or not rows:
        return rows

    primary_by_channel: dict[str, str] = {}
    for row in rows:
        channel_name = str(row.get("channel_name") or row.get("channelName") or "").strip()
        if not channel_name or channel_name in primary_by_channel:
            continue
        primary_by_channel[channel_name] = _resolve_channel_primary_session_id(session_store, pid, channel_name)

    out: list[dict[str, Any]] = []
    for row in rows:
        channel_name = str(row.get("channel_name") or row.get("channelName") or "").strip()
        sid = str(row.get("id") or row.get("session_id") or row.get("sessionId") or "").strip()
        effective_primary = primary_by_channel.get(channel_name, "")
        next_row = dict(row)
        if channel_name and sid and effective_primary:
            next_row["is_primary"] = bool(
                sid == effective_primary and not _coerce_bool(next_row.get("is_deleted"), False)
            )
        out.append(next_row)
    return out


def _build_session_binding_required_payload(
    project_id: str,
    channel_name: str,
    session_id: str,
    *,
    session_data: Optional[dict[str, Any]] = None,
    binding_reason: str = "",
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "error": "session binding required",
        "error_code": "session_binding_required",
        "project_id": str(project_id or "").strip(),
        "channel_name": str(channel_name or "").strip(),
        "session_id": str(session_id or "").strip(),
        "manual_takeover_required": True,
    }
    reason = str(binding_reason or "").strip()
    if reason:
        payload["binding_reason"] = reason
    if not isinstance(session_data, dict):
        return payload
    bound_project_id = str(session_data.get("project_id") or "").strip()
    bound_channel_name = str(session_data.get("channel_name") or "").strip()
    if bound_project_id:
        payload["bound_project_id"] = bound_project_id
    if bound_channel_name:
        payload["bound_channel_name"] = bound_channel_name
    if bool(session_data.get("is_deleted")):
        payload["session_deleted"] = True
        deleted_reason = str(session_data.get("deleted_reason") or "").strip()
        if deleted_reason:
            payload["deleted_reason"] = deleted_reason
    return payload


def _is_compatible_project_binding(requested_project_id: str, bound_project_id: str) -> bool:
    requested = str(requested_project_id or "").strip()
    bound = str(bound_project_id or "").strip()
    if not requested or not bound:
        return False
    requested_key = requested.casefold()
    bound_key = bound.casefold()
    if requested_key == bound_key:
        return True
    compat_group = {"task_dashboard", "task_dashboard_prod", "task_dashboard_prod_mirror"}
    return requested_key in compat_group and bound_key in compat_group


def _validate_announce_session_binding(
    session_data: Optional[dict[str, Any]],
    *,
    project_id: str,
    channel_name: str,
) -> str:
    if not isinstance(session_data, dict):
        return "session_not_found"
    if bool(session_data.get("is_deleted")):
        return "session_deleted"
    bound_project_id = str(session_data.get("project_id") or "").strip()
    bound_channel_name = str(session_data.get("channel_name") or "").strip()
    if not bound_project_id:
        return "session_project_missing"
    if not bound_channel_name:
        return "session_channel_missing"
    if not _is_compatible_project_binding(str(project_id or "").strip(), bound_project_id):
        return "project_mismatch"
    if bound_channel_name != str(channel_name or "").strip():
        return "channel_mismatch"
    return ""


def _load_project_auto_dispatch_config(project_id: str) -> dict[str, Any]:
    pid = str(project_id or "").strip()
    p = _find_project_cfg(pid)
    if not p:
        return {"project_exists": False, "project_id": pid}
    raw = p.get("auto_dispatch")
    obj = raw if isinstance(raw, dict) else {}
    enabled = False
    if "enabled" in obj:
        enabled = _coerce_bool(obj.get("enabled"), False)
    return {
        "project_exists": True,
        "project_id": pid,
        "enabled": bool(enabled),
        "configured": bool(isinstance(raw, dict) and "enabled" in obj),
    }


def _heartbeat_tasks_for_write(raw_tasks: Any) -> list[dict[str, Any]]:
    tasks = _normalize_heartbeat_tasks(raw_tasks)
    out: list[dict[str, Any]] = []
    for row in tasks:
        out.append(
            {
                "heartbeat_task_id": str(row.get("heartbeat_task_id") or ""),
                "title": str(row.get("title") or ""),
                "enabled": bool(row.get("enabled")),
                "channel_name": str(row.get("channel_name") or ""),
                "session_id": str(row.get("session_id") or ""),
                "preset_key": str(row.get("preset_key") or ""),
                "prompt_template": str(row.get("prompt_template") or ""),
                "schedule_type": str(row.get("schedule_type") or "interval"),
                "interval_minutes": row.get("interval_minutes"),
                "daily_time": str(row.get("daily_time") or ""),
                "weekdays": list(row.get("weekdays") or []),
                "busy_policy": str(row.get("busy_policy") or "run_on_next_idle"),
                "max_execute_count": max(0, int(row.get("max_execute_count") or 0)),
                "context_scope": _normalize_heartbeat_context_scope(row.get("context_scope")),
            }
        )
    return out


def _build_heartbeat_patch_with_tasks(
    *,
    cfg: dict[str, Any],
    tasks: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "enabled": bool(cfg.get("enabled")),
        "scan_interval_seconds": int(cfg.get("scan_interval_seconds") or 30),
        "tasks": _heartbeat_tasks_for_write(tasks),
    }


def _load_project_heartbeat_config(project_id: str) -> dict[str, Any]:
    try:
        import server

        override = getattr(server, "_load_project_heartbeat_config", None)
        if callable(override) and override is not _load_project_heartbeat_config:
            return override(project_id)
    except Exception:
        pass

    pid = str(project_id or "").strip()
    p = _find_project_cfg(pid)
    if not p:
        return {"project_exists": False, "project_id": pid}
    raw = p.get("heartbeat")
    obj = raw if isinstance(raw, dict) else {}
    enabled = _coerce_bool(obj.get("enabled"), False)
    scan_interval_seconds = _coerce_int(obj.get("scan_interval_seconds"), 30)
    errors: list[str] = []
    if scan_interval_seconds < 20:
        errors.append("heartbeat.scan_interval_seconds_lt_20")
        scan_interval_seconds = 30
    tasks_raw = obj.get("tasks") if "tasks" in obj else obj.get("heartbeat_tasks")
    tasks = _normalize_heartbeat_tasks(tasks_raw)
    if enabled and not tasks:
        errors.append("heartbeat.tasks_missing")
    return {
        "project_exists": True,
        "project_id": pid,
        "enabled": bool(enabled),
        "scan_interval_seconds": int(scan_interval_seconds),
        "tasks": tasks,
        "configured": isinstance(raw, dict),
        "ready": bool(enabled and any(bool(row.get("ready")) for row in tasks)),
        "errors": errors,
    }


def _load_session_heartbeat_config(session: dict[str, Any]) -> dict[str, Any]:
    row = session if isinstance(session, dict) else {}
    project_id = str(row.get("project_id") or "").strip()
    channel_name = str(row.get("channel_name") or "").strip()
    session_id = str(row.get("id") or row.get("session_id") or "").strip()
    raw = row.get("heartbeat")
    obj = raw if isinstance(raw, dict) else {}
    raw_enabled = _coerce_bool(obj.get("enabled"), False)
    tasks_raw = obj.get("tasks") if "tasks" in obj else obj.get("heartbeat_tasks")
    defaults = {
        "channel_name": channel_name,
        "session_id": session_id,
        "enabled": raw_enabled,
    }
    tasks = _normalize_heartbeat_tasks(tasks_raw, defaults=defaults)
    enabled_count = sum(1 for item in tasks if bool((item or {}).get("enabled")))
    ready_count = sum(1 for item in tasks if bool((item or {}).get("enabled")) and bool((item or {}).get("ready")))
    effective_enabled = bool(enabled_count > 0)
    errors: list[str] = []
    if raw_enabled and not tasks:
        errors.append("heartbeat.tasks_missing")
    return {
        "project_id": project_id,
        "channel_name": channel_name,
        "session_id": session_id,
        "enabled": bool(effective_enabled),
        "raw_enabled": bool(raw_enabled),
        "tasks": tasks,
        "configured": isinstance(raw, dict),
        "ready": bool(ready_count > 0),
        "count": len(tasks),
        "enabled_count": int(enabled_count),
        "summary": {
            "total_count": len(tasks),
            "enabled_count": int(enabled_count),
            "ready_count": int(ready_count),
            "has_enabled_tasks": bool(enabled_count > 0),
        },
        "errors": errors,
    }


def _heartbeat_session_payload_for_write(
    session: dict[str, Any],
    *,
    enabled: bool,
    tasks: Any,
) -> dict[str, Any]:
    cfg = _load_session_heartbeat_config(
        {
            "project_id": str(session.get("project_id") or "").strip(),
            "channel_name": str(session.get("channel_name") or "").strip(),
            "id": str(session.get("id") or session.get("session_id") or "").strip(),
            "heartbeat": {
                "enabled": bool(enabled),
                "tasks": tasks,
            },
        }
    )
    return {
        "enabled": bool(cfg.get("enabled")),
        "tasks": _heartbeat_tasks_for_write(cfg.get("tasks")),
    }


def _heartbeat_summary_payload(raw: Any) -> dict[str, Any]:
    obj = raw if isinstance(raw, dict) else {}
    summary = obj.get("summary") if isinstance(obj.get("summary"), dict) else {}
    total_count = int(summary.get("total_count") or obj.get("count") or 0)
    enabled_count = int(summary.get("enabled_count") or obj.get("enabled_count") or 0)
    ready_count = int(summary.get("ready_count") or 0)
    return {
        "total_count": max(0, total_count),
        "enabled_count": max(0, enabled_count),
        "ready_count": max(0, ready_count),
        "has_enabled_tasks": bool(summary.get("has_enabled_tasks")) if "has_enabled_tasks" in summary else bool(enabled_count > 0),
    }


def _load_project_auto_inspection_config(project_id: str) -> dict[str, Any]:
    pid = str(project_id or "").strip()
    p = _find_project_cfg(pid)
    if not p:
        return {"project_exists": False, "project_id": pid}
    raw = p.get("auto_inspection")
    obj = raw if isinstance(raw, dict) else {}
    enabled = _coerce_bool(obj.get("enabled"), False)
    channel_name = _safe_text(obj.get("channel_name") if "channel_name" in obj else obj.get("channelName"), 200).strip()
    session_id = _safe_text(obj.get("session_id") if "session_id" in obj else obj.get("sessionId"), 120).strip()
    prompt_template = _safe_text(
        obj.get("prompt_template") if "prompt_template" in obj else obj.get("promptTemplate"),
        20_000,
    ).strip()
    inspection_targets_raw = (
        obj.get("inspection_targets")
        if "inspection_targets" in obj
        else obj.get("inspectionTargets")
    )
    auto_inspections_raw = (
        obj.get("auto_inspections")
        if "auto_inspections" in obj
        else obj.get("autoInspections")
    )
    inspection_targets = _normalize_inspection_targets(inspection_targets_raw, default=[])
    auto_inspections = _normalize_auto_inspections(
        auto_inspections_raw,
        fallback_targets=inspection_targets,
    )
    targets_from_objects = _auto_inspection_targets_from_objects(auto_inspections)
    if targets_from_objects:
        inspection_targets = targets_from_objects
    elif not inspection_targets:
        inspection_targets = _normalize_inspection_targets(
            inspection_targets_raw,
            default=_DEFAULT_INSPECTION_TARGETS if enabled else [],
        )
    interval_raw = obj.get("interval_minutes")
    interval_minutes: Optional[int] = None
    errors: list[str] = []
    if interval_raw not in (None, "", 0, "0", False):
        interval_minutes = _coerce_int(interval_raw, 30)
        if interval_minutes < 5:
            errors.append("auto_inspection.interval_minutes_lt_5")
            interval_minutes = 30
    elif enabled:
        interval_minutes = 30

    if session_id and not _looks_like_uuid(session_id):
        errors.append("auto_inspection.session_id_invalid")
        session_id = ""
    if enabled and not channel_name:
        errors.append("auto_inspection.channel_name_missing")
    if enabled and not session_id:
        errors.append("auto_inspection.session_id_missing")
    if enabled and not prompt_template:
        errors.append("auto_inspection.prompt_template_missing")
    if enabled and not inspection_targets and not auto_inspections:
        inspection_targets = list(_DEFAULT_INSPECTION_TARGETS)

    fallback_task = _build_default_auto_inspection_task(
        enabled=enabled,
        channel_name=channel_name,
        session_id=session_id,
        interval_minutes=interval_minutes,
        prompt_template=prompt_template,
        inspection_targets=inspection_targets,
        auto_inspections=auto_inspections,
    )
    active_task_id_hint = _normalize_inspection_task_id(
        obj.get("active_inspection_task_id")
        if "active_inspection_task_id" in obj
        else obj.get("activeInspectionTaskId")
    )
    has_tasks_field = "inspection_tasks" in obj or "inspectionTasks" in obj
    tasks_raw = obj.get("inspection_tasks") if "inspection_tasks" in obj else obj.get("inspectionTasks")
    tasks = _normalize_auto_inspection_tasks(
        tasks_raw,
        defaults=fallback_task,
        fallback_single_task=(fallback_task if isinstance(raw, dict) else None),
        has_explicit_field=has_tasks_field,
    )
    if enabled and not tasks:
        errors.append("auto_inspection.inspection_tasks_missing")
    active_task = _select_active_auto_inspection_task(tasks, active_task_id_hint=active_task_id_hint)
    if active_task is None and tasks:
        active_task = tasks[0]
    if active_task is not None:
        active_task_id_hint = str(active_task.get("inspection_task_id") or "")
        channel_name = str(active_task.get("channel_name") or "")
        session_id = str(active_task.get("session_id") or "")
        prompt_template = str(active_task.get("prompt_template") or "")
        interval_minutes = (
            int(active_task.get("interval_minutes"))
            if active_task.get("interval_minutes") not in (None, "")
            else None
        )
        inspection_targets = _normalize_inspection_targets(active_task.get("inspection_targets"), default=[])
        auto_inspections = _normalize_auto_inspections(
            active_task.get("auto_inspections"),
            fallback_targets=inspection_targets,
        )
        errors.extend([str(x) for x in (active_task.get("errors") or []) if str(x).strip()])
    return {
        "project_exists": True,
        "project_id": pid,
        "enabled": bool(enabled),
        "channel_name": channel_name,
        "session_id": session_id,
        "interval_minutes": int(interval_minutes) if interval_minutes is not None else None,
        "prompt_template": prompt_template,
        "inspection_targets": inspection_targets,
        "auto_inspections": auto_inspections,
        "inspection_tasks": tasks,
        "active_inspection_task_id": active_task_id_hint or "",
        "configured": isinstance(raw, dict),
        "ready": bool(
            enabled
            and active_task is not None
            and bool(active_task.get("ready"))
            and not errors
        ),
        "errors": errors,
    }


def _auto_inspection_tasks_for_write(cfg: dict[str, Any], raw_tasks: Any) -> list[dict[str, Any]]:
    base_defaults = _build_default_auto_inspection_task(
        enabled=bool(cfg.get("enabled")),
        channel_name=str(cfg.get("channel_name") or ""),
        session_id=str(cfg.get("session_id") or ""),
        interval_minutes=(int(cfg.get("interval_minutes")) if cfg.get("interval_minutes") is not None else None),
        prompt_template=str(cfg.get("prompt_template") or ""),
        inspection_targets=_normalize_inspection_targets(cfg.get("inspection_targets"), default=[]),
        auto_inspections=_normalize_auto_inspections(cfg.get("auto_inspections"), fallback_targets=cfg.get("inspection_targets")),
    )
    tasks = _normalize_auto_inspection_tasks(
        raw_tasks,
        defaults=base_defaults,
        fallback_single_task=base_defaults,
        has_explicit_field=True,
    )
    out: list[dict[str, Any]] = []
    for row in tasks:
        out.append(
            {
                "inspection_task_id": str(row.get("inspection_task_id") or ""),
                "title": str(row.get("title") or ""),
                "enabled": bool(row.get("enabled")),
                "channel_name": str(row.get("channel_name") or ""),
                "session_id": str(row.get("session_id") or ""),
                "interval_minutes": row.get("interval_minutes"),
                "prompt_template": str(row.get("prompt_template") or ""),
                "inspection_targets": _normalize_inspection_targets(row.get("inspection_targets"), default=[]),
                "auto_inspections": _normalize_auto_inspections(
                    row.get("auto_inspections"),
                    fallback_targets=_normalize_inspection_targets(row.get("inspection_targets"), default=[]),
                ),
            }
        )
    return out


def _build_auto_inspection_patch_with_tasks(
    *,
    cfg: dict[str, Any],
    tasks: list[dict[str, Any]],
    active_task_id: str = "",
) -> dict[str, Any]:
    normalized_tasks = _auto_inspection_tasks_for_write(cfg, tasks)
    selected = _select_active_auto_inspection_task(
        normalized_tasks,
        active_task_id_hint=active_task_id or str(cfg.get("active_inspection_task_id") or ""),
    )
    selected_id = str(selected.get("inspection_task_id") or "").strip() if isinstance(selected, dict) else ""
    patch: dict[str, Any] = {
        "inspection_tasks": normalized_tasks,
        "active_inspection_task_id": selected_id or None,
        "inspection_targets": [],
        "auto_inspections": [],
        "channel_name": None,
        "session_id": None,
        "interval_minutes": None,
        "prompt_template": None,
    }
    if isinstance(selected, dict):
        patch["inspection_targets"] = _normalize_inspection_targets(selected.get("inspection_targets"), default=[])
        patch["auto_inspections"] = _normalize_auto_inspections(
            selected.get("auto_inspections"),
            fallback_targets=patch["inspection_targets"],
        )
        patch["channel_name"] = str(selected.get("channel_name") or "") or None
        patch["session_id"] = str(selected.get("session_id") or "") or None
        patch["interval_minutes"] = selected.get("interval_minutes")
        patch["prompt_template"] = str(selected.get("prompt_template") or "") or None
    return patch


def _load_project_scheduler_contract_config(project_id: str) -> dict[str, Any]:
    """
    Normalize project scheduler/reminder config using 12-4 frozen contract defaults.
    Returns effective config + validation notes; invalid values degrade to disabled.
    """
    try:
        import server

        override = getattr(server, "_load_project_scheduler_contract_config", None)
        if callable(override) and override is not _load_project_scheduler_contract_config:
            return override(project_id)
    except Exception:
        pass

    pid = str(project_id or "").strip()
    p = _find_project_cfg(pid)
    if not p:
        return {"project_exists": False, "project_id": pid}

    scheduler_raw = p.get("scheduler")
    scheduler_obj = scheduler_raw if isinstance(scheduler_raw, dict) else {}
    reminder_raw = p.get("reminder")
    reminder_obj = reminder_raw if isinstance(reminder_raw, dict) else {}

    scheduler_enabled = _coerce_bool(scheduler_obj.get("enabled"), False)
    scan_interval_seconds = _coerce_int(scheduler_obj.get("scan_interval_seconds"), 300)
    max_concurrency_override = scheduler_obj.get("max_concurrency_override")
    retry_on_boot = _coerce_bool(scheduler_obj.get("retry_on_boot"), True)
    scheduler_errors: list[str] = []

    if scan_interval_seconds < 60:
        scheduler_errors.append("scheduler.scan_interval_seconds_lt_60")
        scheduler_enabled = False
        scan_interval_seconds = 300

    reminder_enabled = _coerce_bool(reminder_obj.get("enabled"), False)
    reminder_interval_minutes = reminder_obj.get("interval_minutes")
    reminder_cron = str(reminder_obj.get("cron") or "").strip()
    reminder_stale_after = _coerce_int(reminder_obj.get("in_progress_stale_after_minutes"), 120)
    reminder_escalate_after = _coerce_int(reminder_obj.get("escalate_after_minutes"), 480)
    reminder_summary_window = _coerce_int(reminder_obj.get("summary_window_minutes"), 5)
    reminder_errors: list[str] = []

    if reminder_enabled:
        if reminder_interval_minutes is None and not reminder_cron:
            reminder_interval_minutes = 30
        if reminder_interval_minutes is not None:
            reminder_interval_minutes = _coerce_int(reminder_interval_minutes, 30)
            if reminder_interval_minutes < 5:
                reminder_errors.append("reminder.interval_minutes_lt_5")
                reminder_enabled = False
        if reminder_stale_after <= 0:
            reminder_errors.append("reminder.in_progress_stale_after_minutes_lte_0")
            reminder_enabled = False
        if reminder_summary_window < 1:
            reminder_summary_window = 5

    return {
        "project_exists": True,
        "project_id": pid,
        "scheduler": {
            "enabled": bool(scheduler_enabled),
            "scan_interval_seconds": int(scan_interval_seconds),
            "max_concurrency_override": max_concurrency_override if isinstance(max_concurrency_override, int) else None,
            "retry_on_boot": bool(retry_on_boot),
            "errors": scheduler_errors,
        },
        "reminder": {
            "enabled": bool(reminder_enabled),
            "interval_minutes": int(reminder_interval_minutes) if reminder_interval_minutes is not None else None,
            "cron": reminder_cron or "",
            "in_progress_stale_after_minutes": int(reminder_stale_after),
            "escalate_after_minutes": int(reminder_escalate_after),
            "summary_window_minutes": int(reminder_summary_window),
            "errors": reminder_errors,
        },
    }


def _load_project_scheduler_runtime_snapshot(store: "RunStore", project_id: str) -> dict[str, Any]:
    path = _project_scheduler_state_path(store, project_id)
    raw = _read_json_file(path)
    return raw if isinstance(raw, dict) else {}


def _save_project_scheduler_runtime_snapshot(store: "RunStore", project_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    path = _project_scheduler_state_path(store, project_id)
    base = _load_project_scheduler_runtime_snapshot(store, project_id)
    out = dict(base)
    for k, v in (patch or {}).items():
        out[k] = v
    out["project_id"] = str(project_id or "").strip()
    out["updated_at"] = _now_iso()
    _write_json_file(path, out)
    return out


def _normalize_auto_inspection_reminder_record(item: Any) -> Optional[dict[str, str]]:
    if not isinstance(item, dict):
        return None
    status = str(item.get("status") or "").strip().lower()
    if status not in _AUTO_INSPECTION_RECORD_STATUS:
        status = "error" if status == "failed" else "skipped" if status.startswith("skip") else "dispatched"
        if status not in _AUTO_INSPECTION_RECORD_STATUS:
            status = "error"
    created_at = _safe_text(item.get("created_at"), 80).strip() or _now_iso()
    message_summary = _safe_text(item.get("message_summary"), 500).strip()
    target_task_path = _normalize_task_path_identity(str(item.get("target_task_path") or ""))
    target_channel = _safe_text(item.get("target_channel"), 200).strip()
    run_id = _safe_text(item.get("run_id"), 120).strip()
    skip_reason = _safe_text(item.get("skip_reason"), 120).strip()
    inspection_task_id = _normalize_inspection_task_id(
        item.get("inspection_task_id") if "inspection_task_id" in item else item.get("inspectionTaskId"),
        default=_DEFAULT_INSPECTION_TASK_ID,
    )
    return {
        "created_at": created_at,
        "status": status,
        "message_summary": message_summary,
        "target_task_path": target_task_path,
        "target_channel": target_channel,
        "run_id": run_id,
        "skip_reason": skip_reason,
        "inspection_task_id": inspection_task_id or _DEFAULT_INSPECTION_TASK_ID,
    }


def _normalize_auto_inspection_reminder_records(raw: Any, *, limit: int = _AUTO_INSPECTION_RECORD_LIMIT) -> list[dict[str, str]]:
    rows = raw if isinstance(raw, list) else []
    out: list[dict[str, str]] = []
    for item in rows:
        row = _normalize_auto_inspection_reminder_record(item)
        if not row:
            continue
        out.append(row)
        if len(out) >= max(1, min(int(limit or _AUTO_INSPECTION_RECORD_LIMIT), _AUTO_INSPECTION_RECORD_LIMIT)):
            break
    return out


def _normalize_auto_inspection_selected_tasks(raw: Any) -> list[str]:
    vals = raw if isinstance(raw, list) else []
    out: list[str] = []
    for item in vals:
        path = _normalize_task_path_identity(str(item or ""))
        if not path:
            continue
        if path in out:
            continue
        out.append(path)
        if len(out) >= 1:
            break
    return out


def _ensure_auto_scheduler_status_shape(status: Any) -> dict[str, Any]:
    row = dict(status) if isinstance(status, dict) else {}
    targets = _normalize_inspection_targets(row.get("auto_inspection_targets"), default=[])
    auto_inspections = _normalize_auto_inspections(
        row.get("auto_inspections") if "auto_inspections" in row else row.get("autoInspections"),
        fallback_targets=targets,
    )
    targets_from_objects = _auto_inspection_targets_from_objects(auto_inspections)
    row["auto_inspection_targets"] = targets_from_objects or targets
    row["auto_inspections"] = _normalize_auto_inspections(auto_inspections, fallback_targets=row["auto_inspection_targets"])
    fallback_task = _build_default_auto_inspection_task(
        enabled=bool(row.get("auto_inspection_enabled")),
        channel_name=str(row.get("auto_inspection_channel_name") or ""),
        session_id=str(row.get("auto_inspection_session_id") or ""),
        interval_minutes=(
            _coerce_int(row.get("auto_inspection_interval_minutes"), 30)
            if row.get("auto_inspection_interval_minutes") not in (None, "", False)
            else None
        ),
        prompt_template=str(row.get("auto_inspection_prompt_template") or ""),
        inspection_targets=row["auto_inspection_targets"],
        auto_inspections=row["auto_inspections"],
    )
    has_tasks_field = "inspection_tasks" in row or "inspectionTasks" in row
    raw_tasks = row.get("inspection_tasks") if "inspection_tasks" in row else row.get("inspectionTasks")
    tasks = _normalize_auto_inspection_tasks(
        raw_tasks,
        defaults=fallback_task,
        fallback_single_task=(
            fallback_task
            if (has_tasks_field or bool(row.get("auto_inspection_configured")) or bool(row.get("auto_inspection_enabled")))
            else None
        ),
        has_explicit_field=has_tasks_field,
    )
    active_task_id_hint = _normalize_inspection_task_id(
        row.get("active_inspection_task_id")
        if "active_inspection_task_id" in row
        else row.get("activeInspectionTaskId"),
        default=_DEFAULT_INSPECTION_TASK_ID,
    )
    active_task = _select_active_auto_inspection_task(tasks, active_task_id_hint=active_task_id_hint)
    default_task_id = (
        str(active_task.get("inspection_task_id") or "").strip()
        if isinstance(active_task, dict)
        else (str(tasks[0].get("inspection_task_id") or "").strip() if tasks else _DEFAULT_INSPECTION_TASK_ID)
    ) or _DEFAULT_INSPECTION_TASK_ID
    row["inspection_tasks"] = tasks
    row["active_inspection_task_id"] = default_task_id if tasks else ""

    reminder_records = _normalize_auto_inspection_reminder_records(row.get("reminder_records"))
    inspection_records_raw = row.get("inspection_records") if "inspection_records" in row else row.get("inspectionRecords")
    inspection_records = _normalize_inspection_records(inspection_records_raw)
    if inspection_records:
        if not reminder_records:
            reminder_records = _reminder_records_from_inspection_records(inspection_records)
    else:
        inspection_records = _inspection_records_from_reminder_records(
            reminder_records,
            auto_inspections=row["auto_inspections"],
            default_inspection_task_id=default_task_id,
        )
    if default_task_id:
        for rec in reminder_records:
            if not isinstance(rec, dict):
                continue
            rid = _normalize_inspection_task_id(rec.get("inspection_task_id"), default="")
            if not rid or rid == _DEFAULT_INSPECTION_TASK_ID:
                rec["inspection_task_id"] = default_task_id
        for rec in inspection_records:
            if not isinstance(rec, dict):
                continue
            rid = _normalize_inspection_task_id(rec.get("inspection_task_id"), default="")
            if not rid or rid == _DEFAULT_INSPECTION_TASK_ID:
                rec["inspection_task_id"] = default_task_id
    row["inspection_records"] = inspection_records
    row["reminder_records"] = reminder_records
    row["auto_inspection_last_selected_tasks"] = _normalize_auto_inspection_selected_tasks(
        row.get("auto_inspection_last_selected_tasks")
    )
    state = str(row.get("auto_inspection_execution_state") or "").strip().lower()
    if state not in {"effective", "skipped_active", "advice_only", "error", "pending"}:
        row["auto_inspection_execution_state"] = "pending"
    else:
        row["auto_inspection_execution_state"] = state
    try:
        row["auto_inspection_advice_only_streak"] = max(0, int(row.get("auto_inspection_advice_only_streak") or 0))
    except Exception:
        row["auto_inspection_advice_only_streak"] = 0
    try:
        row["auto_inspection_escalation_level"] = max(0, int(row.get("auto_inspection_escalation_level") or 0))
    except Exception:
        row["auto_inspection_escalation_level"] = 0
    return row


def _attach_auto_inspection_candidate_preview(
    store: "RunStore",
    status: dict[str, Any],
) -> dict[str, Any]:
    row = _ensure_auto_scheduler_status_shape(status)
    if not bool(row.get("auto_inspection_enabled")):
        return row
    pid = str(row.get("project_id") or "").strip()
    if not pid:
        return row
    targets = _normalize_inspection_targets(
        row.get("auto_inspection_targets"),
        default=_DEFAULT_INSPECTION_TARGETS,
    )
    preview_key = f"{pid}|{','.join(targets)}"
    ttl_s = _auto_inspection_preview_cache_ttl_s()
    now_mono = time.monotonic()
    preview_cache = _auto_inspection_preview_cache()
    with _auto_inspection_preview_cache_lock():
        cached = preview_cache.get(preview_key)
        if isinstance(cached, dict):
            cached_at = float(cached.get("fetched_at_mono") or 0.0)
            if (now_mono - cached_at) <= ttl_s:
                try:
                    row["auto_inspection_candidate_count_preview"] = int(cached.get("count") or 0)
                    return row
                except Exception:
                    pass
    try:
        preview = _call_server_override(
            "_collect_auto_inspection_candidates",
            _collect_auto_inspection_candidates,
            store,
            pid,
            targets,
            limit=20,
        )
        rows = preview.get("candidates") if isinstance(preview, dict) else []
        count = len(rows) if isinstance(rows, list) else 0
        row["auto_inspection_candidate_count_preview"] = count
        with _auto_inspection_preview_cache_lock():
            preview_cache[preview_key] = {
                "count": int(count),
                "fetched_at_mono": now_mono,
            }
            if len(preview_cache) > 256:
                stale_keys = sorted(
                    preview_cache.keys(),
                    key=lambda k: float((preview_cache.get(k) or {}).get("fetched_at_mono") or 0.0),
                )[:-128]
                for key in stale_keys:
                    preview_cache.pop(key, None)
    except Exception:
        row["auto_inspection_candidate_count_preview"] = 0
    return row


def _build_project_scheduler_status(
    store: "RunStore",
    project_id: str,
    *,
    runtime_flags: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    cfg = _call_server_override(
        "_load_project_scheduler_contract_config",
        _load_project_scheduler_contract_config,
        project_id,
    )
    pid = str(project_id or "").strip()
    runtime_disk = _load_project_scheduler_runtime_snapshot(store, pid)
    runtime = runtime_flags if isinstance(runtime_flags, dict) else {}
    if not cfg.get("project_exists"):
        if not runtime and not runtime_disk:
            return {}
        cfg = {
            "project_exists": True,
            "scheduler": {"enabled": False, "errors": []},
            "reminder": {"enabled": False, "errors": []},
        }
    scheduler_cfg = cfg.get("scheduler") if isinstance(cfg.get("scheduler"), dict) else {}
    reminder_cfg = cfg.get("reminder") if isinstance(cfg.get("reminder"), dict) else {}
    auto_dispatch_cfg = _call_server_override(
        "_load_project_auto_dispatch_config",
        _load_project_auto_dispatch_config,
        pid,
    )
    auto_inspection_cfg = _call_server_override(
        "_load_project_auto_inspection_config",
        _load_project_auto_inspection_config,
        pid,
    )

    scheduler_enabled = bool(scheduler_cfg.get("enabled"))
    reminder_enabled = bool(reminder_cfg.get("enabled"))
    auto_dispatch_enabled = bool(auto_dispatch_cfg.get("enabled", False))
    auto_inspection_enabled = bool(auto_inspection_cfg.get("enabled"))

    scheduler_state = "disabled"
    if scheduler_enabled:
        scheduler_state = str(runtime.get("scheduler_state") or runtime_disk.get("scheduler_state") or "idle")
        if scheduler_state not in {"idle", "scanning", "error"}:
            scheduler_state = "idle"

    reminder_state = "disabled"
    if reminder_enabled:
        reminder_state = str(runtime.get("reminder_state") or runtime_disk.get("reminder_state") or "idle")
        if reminder_state not in {"idle", "collecting", "dispatching", "error"}:
            reminder_state = "idle"

    status: dict[str, Any] = {
        "project_id": pid,
        "scheduler_enabled": scheduler_enabled,
        "scheduler_state": scheduler_state,
        "reminder_enabled": reminder_enabled,
        "reminder_state": reminder_state,
        # Additive aliases/config status for task auto-dispatch and inspection bridge.
        "auto_dispatch_enabled": auto_dispatch_enabled,
        "auto_inspection_enabled": auto_inspection_enabled,
    }
    auto_inspection_ready_raw = auto_inspection_cfg.get("ready")
    auto_inspection_ready = (
        bool(auto_inspection_ready_raw)
        if isinstance(auto_inspection_ready_raw, bool)
        else bool(
            auto_inspection_enabled
            and str(auto_inspection_cfg.get("channel_name") or "").strip()
            and str(auto_inspection_cfg.get("session_id") or "").strip()
        )
    )
    auto_inspection_state = "disabled"
    if auto_inspection_enabled:
        auto_inspection_state = "idle" if auto_inspection_ready else "invalid_config"
    runtime_auto_inspection_state = str(
        runtime.get("auto_inspection_state") or runtime_disk.get("auto_inspection_state") or ""
    ).strip()
    if runtime_auto_inspection_state in {"idle", "running", "error", "invalid_config", "disabled"}:
        if auto_inspection_enabled:
            auto_inspection_state = runtime_auto_inspection_state if runtime_auto_inspection_state != "disabled" else auto_inspection_state
        else:
            auto_inspection_state = "disabled"
    status["auto_inspection_state"] = auto_inspection_state
    if auto_dispatch_cfg.get("configured"):
        status["auto_dispatch_configured"] = True
    if auto_inspection_cfg.get("configured"):
        status["auto_inspection_configured"] = True
    if auto_inspection_cfg.get("channel_name"):
        status["auto_inspection_channel_name"] = str(auto_inspection_cfg.get("channel_name") or "")
    if auto_inspection_cfg.get("session_id"):
        status["auto_inspection_session_id"] = str(auto_inspection_cfg.get("session_id") or "")
    status["auto_inspection_targets"] = _normalize_inspection_targets(
        auto_inspection_cfg.get("inspection_targets"),
        default=_DEFAULT_INSPECTION_TARGETS if auto_inspection_enabled else [],
    )
    status["auto_inspections"] = _normalize_auto_inspections(
        auto_inspection_cfg.get("auto_inspections"),
        fallback_targets=status["auto_inspection_targets"],
    )
    status["inspection_tasks"] = _normalize_auto_inspection_tasks(
        auto_inspection_cfg.get("inspection_tasks"),
        fallback_single_task=_build_default_auto_inspection_task(
            enabled=bool(auto_inspection_cfg.get("enabled")),
            channel_name=str(auto_inspection_cfg.get("channel_name") or ""),
            session_id=str(auto_inspection_cfg.get("session_id") or ""),
            interval_minutes=(
                int(auto_inspection_cfg.get("interval_minutes"))
                if auto_inspection_cfg.get("interval_minutes") is not None
                else None
            ),
            prompt_template=str(auto_inspection_cfg.get("prompt_template") or ""),
            inspection_targets=status["auto_inspection_targets"],
            auto_inspections=status["auto_inspections"],
        ),
        has_explicit_field=True,
    )
    status["active_inspection_task_id"] = str(auto_inspection_cfg.get("active_inspection_task_id") or "")
    mapped_targets = _auto_inspection_targets_from_objects(status["auto_inspections"])
    if mapped_targets:
        status["auto_inspection_targets"] = mapped_targets
    if auto_inspection_cfg.get("interval_minutes") is not None:
        status["auto_inspection_interval_minutes"] = int(auto_inspection_cfg.get("interval_minutes") or 0)
    if auto_inspection_cfg.get("prompt_template"):
        status["auto_inspection_prompt_template"] = str(auto_inspection_cfg.get("prompt_template") or "")
    status["auto_inspection_ready"] = auto_inspection_ready
    for k in (
        "auto_inspection_last_tick_at",
        "auto_inspection_last_run_id",
        "auto_inspection_last_job_id",
        "auto_inspection_next_due_at",
        "auto_inspection_last_error",
        "auto_inspection_last_candidate_count",
        "auto_inspection_last_target_sources",
        "auto_inspection_last_selected_tasks",
        "auto_inspection_last_task_id",
    ):
        v = runtime.get(k) if k in runtime else runtime_disk.get(k)
        if v is None:
            continue
        if isinstance(v, list):
            status[k] = _normalize_auto_inspection_selected_tasks(v) if k == "auto_inspection_last_selected_tasks" else list(v)
        else:
            status[k] = str(v)
    for k in (
        "auto_inspection_execution_state",
        "auto_inspection_gate_last_reason",
        "auto_inspection_gate_last_run_id",
        "auto_inspection_gate_last_checked_at",
        "auto_inspection_gate_action",
        "auto_inspection_gate_action_run_id",
    ):
        v = runtime.get(k) if k in runtime else runtime_disk.get(k)
        if v:
            status[k] = str(v)
    for k in ("auto_inspection_advice_only_streak", "auto_inspection_escalation_level"):
        v = runtime.get(k) if k in runtime else runtime_disk.get(k)
        try:
            status[k] = max(0, int(v or 0))
        except Exception:
            status[k] = 0
    guard_events_raw = runtime.get("guard_events") if "guard_events" in runtime else runtime_disk.get("guard_events")
    if guard_events_raw is not None:
        status["guard_events"] = _normalize_guard_runtime_events(guard_events_raw)
    guard_stats_raw = runtime.get("guard_stats") if "guard_stats" in runtime else runtime_disk.get("guard_stats")
    if guard_stats_raw is not None:
        status["guard_stats"] = _normalize_guard_runtime_stats(guard_stats_raw)
    guard_policy_raw = runtime.get("guard_policy") if "guard_policy" in runtime else runtime_disk.get("guard_policy")
    if isinstance(guard_policy_raw, dict) and guard_policy_raw:
        status["guard_policy"] = dict(guard_policy_raw)
    guard_last_tick_raw = (
        runtime.get("guard_last_tick_at")
        if "guard_last_tick_at" in runtime
        else runtime_disk.get("guard_last_tick_at")
    )
    if guard_last_tick_raw:
        status["guard_last_tick_at"] = str(guard_last_tick_raw)
    # scheduler runtime fields
    for k in ("scheduler_last_tick_at", "scheduler_last_error"):
        v = runtime.get(k) if k in runtime else runtime_disk.get(k)
        if v:
            status[k] = str(v)
    # reminder config/runtime fields
    if reminder_cfg.get("interval_minutes") is not None:
        status["reminder_interval_minutes"] = int(reminder_cfg.get("interval_minutes") or 0)
    if reminder_cfg.get("cron"):
        status["reminder_cron"] = str(reminder_cfg.get("cron") or "")
    status["reminder_stale_after_minutes"] = int(reminder_cfg.get("in_progress_stale_after_minutes") or 120)
    status["reminder_escalate_after_minutes"] = int(reminder_cfg.get("escalate_after_minutes") or 480)
    status["reminder_summary_window_minutes"] = int(reminder_cfg.get("summary_window_minutes") or 5)
    for k in ("reminder_last_tick_at", "reminder_last_sent_at", "reminder_next_due_at", "reminder_last_error"):
        v = runtime.get(k) if k in runtime else runtime_disk.get(k)
        if v:
            status[k] = str(v)
    reminder_records_raw = runtime.get("reminder_records") if "reminder_records" in runtime else runtime_disk.get("reminder_records")
    status["reminder_records"] = _normalize_auto_inspection_reminder_records(reminder_records_raw)
    inspection_records_raw = (
        runtime.get("inspection_records")
        if "inspection_records" in runtime
        else runtime_disk.get("inspection_records")
    )
    if inspection_records_raw is not None:
        status["inspection_records"] = _normalize_inspection_records(inspection_records_raw)
    else:
        default_task_id = _normalize_inspection_task_id(
            status.get("active_inspection_task_id"),
            default=_DEFAULT_INSPECTION_TASK_ID,
        )
        status["inspection_records"] = _inspection_records_from_reminder_records(
            status["reminder_records"],
            auto_inspections=status.get("auto_inspections"),
            default_inspection_task_id=default_task_id,
        )
    active_task_row = _select_active_auto_inspection_task(
        _normalize_auto_inspection_tasks(status.get("inspection_tasks"), has_explicit_field=True),
        active_task_id_hint=str(status.get("active_inspection_task_id") or ""),
    )
    active_task_id = (
        _normalize_inspection_task_id(active_task_row.get("inspection_task_id"), default="")
        if isinstance(active_task_row, dict)
        else ""
    )
    tasks_out: list[dict[str, Any]] = []
    for raw_task in list(status.get("inspection_tasks") or []):
        if not isinstance(raw_task, dict):
            continue
        task = dict(raw_task)
        tid = _normalize_inspection_task_id(task.get("inspection_task_id"), default="")
        if not tid:
            continue
        task["inspection_task_id"] = tid
        if not bool(task.get("enabled")):
            task["state"] = "disabled"
        elif tid == active_task_id:
            task["state"] = str(status.get("auto_inspection_state") or "idle")
            task["next_due_at"] = str(status.get("auto_inspection_next_due_at") or "")
            task["last_tick_at"] = str(status.get("auto_inspection_last_tick_at") or "")
            task["last_run_id"] = str(status.get("auto_inspection_last_run_id") or "")
            task["last_error"] = str(status.get("auto_inspection_last_error") or "")
            task["last_candidate_count"] = int(status.get("auto_inspection_last_candidate_count") or 0)
        else:
            task["state"] = "idle"
            task["next_due_at"] = ""
            task["last_tick_at"] = ""
            task["last_run_id"] = ""
            task["last_error"] = ""
            task["last_candidate_count"] = 0
        tasks_out.append(task)
    status["inspection_tasks"] = tasks_out
    # expose validation issues as optional diagnostics (V1 additive)
    errs = []
    errs.extend([str(x) for x in (scheduler_cfg.get("errors") or []) if str(x).strip()])
    errs.extend([str(x) for x in (reminder_cfg.get("errors") or []) if str(x).strip()])
    errs.extend([str(x) for x in (auto_inspection_cfg.get("errors") or []) if str(x).strip()])
    if errs:
        status["config_errors"] = errs
    if "worker_running" in runtime:
        status["worker_running"] = bool(runtime.get("worker_running"))
    return _ensure_auto_scheduler_status_shape(status)


def _resolve_scheduler_engine_enabled() -> tuple[bool, str]:
    raw = str(os.environ.get("CCB_SCHEDULER") or "").strip()
    if not raw:
        return True, "default"
    return raw != "0", "env"


def _toml_scalar_literal(value: Any) -> str:
    if isinstance(value, dict):
        pairs: list[str] = []
        for raw_key, raw_value in value.items():
            key = str(raw_key or "").strip()
            if not key or raw_value is None:
                continue
            pairs.append(f"{key} = {_toml_scalar_literal(raw_value)}")
        return "{ " + ", ".join(pairs) + " }"
    if isinstance(value, (list, tuple)):
        rows: list[str] = []
        for item in value:
            if item is None:
                continue
            if isinstance(item, dict):
                rows.append(_toml_scalar_literal(item))
                continue
            if isinstance(item, bool):
                rows.append("true" if item else "false")
            elif isinstance(item, int) and not isinstance(item, bool):
                rows.append(str(item))
            else:
                rows.append(json.dumps(str(item), ensure_ascii=False))
        return "[" + ", ".join(rows) + "]"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return json.dumps(str(value), ensure_ascii=False)


def _find_project_block_range(config_content: str, project_id: str) -> tuple[int, int, str]:
    content = str(config_content or "")
    pid = str(project_id or "").strip()
    if not pid:
        raise ValueError("missing project_id")
    matches = list(re.finditer(r"(?m)^\[\[projects\]\]\s*$", content))
    if not matches:
        raise ValueError("no [[projects]] blocks found")
    for idx, m in enumerate(matches):
        start = m.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(content)
        block = content[start:end]
        if re.search(rf"(?m)^\s*id\s*=\s*['\"]{re.escape(pid)}['\"]\s*$", block):
            return start, end, block
    raise ValueError(f"project '{pid}' not found in config.toml")


def _set_project_table_values_in_config_text(
    config_content: str,
    project_id: str,
    table_name: str,
    updates: dict[str, Any],
) -> str:
    content = str(config_content or "")
    start, end, block = _find_project_block_range(content, project_id)
    clean_updates = {str(k).strip(): v for k, v in (updates or {}).items() if str(k).strip()}
    if not clean_updates:
        return content

    hdr = re.search(rf"(?m)^\[projects\.{re.escape(table_name)}\]\s*$", block)

    def _apply_to_subtable(sub: str) -> str:
        out = sub
        for key, value in clean_updates.items():
            multi_dq_pat = re.compile(
                rf'(?ms)^[ \t]*{re.escape(key)}[ \t]*=[ \t]*""".*?"""[ \t]*(?:\n|$)'
            )
            multi_sq_pat = re.compile(
                rf"(?ms)^[ \t]*{re.escape(key)}[ \t]*=[ \t]*'''.*?'''[ \t]*(?:\n|$)"
            )
            line_pat = re.compile(rf"(?m)^\s*{re.escape(key)}\s*=.*$")

            # Drop existing key entry first. This avoids leaving stale lines behind
            # when previous value used TOML multiline strings.
            out = re.sub(multi_dq_pat, "", out)
            out = re.sub(multi_sq_pat, "", out)
            out = re.sub(line_pat, "", out)

            if value is None:
                continue
            repl = f"{key} = {_toml_scalar_literal(value)}"
            if not out.endswith("\n"):
                out += "\n"
            out += repl + "\n"
        out = re.sub(r"\n{3,}", "\n\n", out)
        return out

    if hdr:
        sub_start = hdr.start()
        next_hdr = re.search(r"(?m)^\[", block[hdr.end() :])
        sub_end = hdr.end() + (next_hdr.start() if next_hdr else len(block) - hdr.end())
        sub = block[sub_start:sub_end]
        sub2 = _apply_to_subtable(sub)
        new_block = block[:sub_start] + sub2 + block[sub_end:]
    else:
        lines: list[str] = []
        for key, value in clean_updates.items():
            if value is None:
                continue
            lines.append(f"{key} = {_toml_scalar_literal(value)}")
        if not lines:
            return content
        suffix = "" if block.endswith("\n") else "\n"
        append = suffix + f"\n[projects.{table_name}]\n" + "\n".join(lines) + "\n"
        new_block = block + append

    return content[:start] + new_block + content[end:]


def _set_project_scheduler_contract_in_config_text(
    config_content: str,
    project_id: str,
    *,
    scheduler_patch: Optional[dict[str, Any]] = None,
    reminder_patch: Optional[dict[str, Any]] = None,
    auto_dispatch_patch: Optional[dict[str, Any]] = None,
    auto_inspection_patch: Optional[dict[str, Any]] = None,
    heartbeat_patch: Optional[dict[str, Any]] = None,
    execution_context_patch: Optional[dict[str, Any]] = None,
    session_health_patch: Optional[dict[str, Any]] = None,
) -> str:
    out = str(config_content or "")
    if isinstance(scheduler_patch, dict) and scheduler_patch:
        out = _set_project_table_values_in_config_text(out, project_id, "scheduler", scheduler_patch)
    if isinstance(reminder_patch, dict) and reminder_patch:
        out = _set_project_table_values_in_config_text(out, project_id, "reminder", reminder_patch)
    if isinstance(auto_dispatch_patch, dict) and auto_dispatch_patch:
        out = _set_project_table_values_in_config_text(out, project_id, "auto_dispatch", auto_dispatch_patch)
    if isinstance(auto_inspection_patch, dict) and auto_inspection_patch:
        out = _set_project_table_values_in_config_text(out, project_id, "auto_inspection", auto_inspection_patch)
    if isinstance(heartbeat_patch, dict) and heartbeat_patch:
        out = _set_project_table_values_in_config_text(out, project_id, "heartbeat", heartbeat_patch)
    if isinstance(execution_context_patch, dict) and execution_context_patch:
        out = _set_project_table_values_in_config_text(out, project_id, "execution_context", execution_context_patch)
    if isinstance(session_health_patch, dict) and session_health_patch:
        out = _set_project_table_values_in_config_text(out, project_id, "session_health", session_health_patch)
    return out


def _set_project_scheduler_contract_in_config(
    project_id: str,
    *,
    scheduler_patch: Optional[dict[str, Any]] = None,
    reminder_patch: Optional[dict[str, Any]] = None,
    auto_dispatch_patch: Optional[dict[str, Any]] = None,
    auto_inspection_patch: Optional[dict[str, Any]] = None,
    heartbeat_patch: Optional[dict[str, Any]] = None,
    execution_context_patch: Optional[dict[str, Any]] = None,
    session_health_patch: Optional[dict[str, Any]] = None,
) -> Path:
    _config_toml_path = __getattr__("_config_toml_path")
    _clear_dashboard_cfg_cache = __getattr__("_clear_dashboard_cfg_cache")
    config_path = _config_toml_path()
    if not config_path.exists():
        raise ValueError("config.toml not found")
    raw = config_path.read_text(encoding="utf-8")
    updated = _set_project_scheduler_contract_in_config_text(
        raw,
        project_id,
        scheduler_patch=scheduler_patch,
        reminder_patch=reminder_patch,
        auto_dispatch_patch=auto_dispatch_patch,
        auto_inspection_patch=auto_inspection_patch,
        heartbeat_patch=heartbeat_patch,
        execution_context_patch=execution_context_patch,
        session_health_patch=session_health_patch,
    )
    _atomic_write_text(config_path, updated)
    _clear_dashboard_cfg_cache()
    return config_path


def _set_project_scheduler_enabled_in_config_text(config_content: str, project_id: str, enabled: bool) -> str:
    return _set_project_scheduler_contract_in_config_text(
        config_content,
        project_id,
        scheduler_patch={"enabled": bool(enabled)},
    )


def _set_project_scheduler_enabled_in_config(project_id: str, enabled: bool) -> Path:
    return _set_project_scheduler_contract_in_config(
        project_id,
        scheduler_patch={"enabled": bool(enabled)},
    )


def _run_project_scheduler_once_bridge(store: "RunStore", project_id: str) -> dict[str, Any]:
    """
    V1 bridge to existing inspection scheduler.
    Note: current inspection executor works on shared `.runs`; this bridge isolates project task_root and state paths.
    """
    task_root = _resolve_project_task_root(project_id)
    if task_root is None or not task_root.exists():
        raise ValueError(f"task_root unavailable for project: {project_id}")
    from task_dashboard.inspection_scheduler import run_once as inspection_run_once


    base = _project_scheduler_state_root(store) / str(project_id or "").strip()
    return inspection_run_once(
        task_root=task_root,
        runs_dir=store.runs_dir,
        watermark_path=base / "watermark.json",
        ledger_path=base / "ledger.jsonl",
        alignment_state_path=base / "alignment_state.json",
        health_path=base / "inspection_health.json",
    )


# =============================================================================
# Metadata normalization functions (extracted from server.py)
# =============================================================================


def _normalize_callback_to(value: Any) -> Optional[dict[str, str]]:
    if not isinstance(value, dict):
        return None
    channel_name = _safe_text(value.get("channel_name") or value.get("channelName"), 200).strip()
    session_id = _safe_text(value.get("session_id") or value.get("sessionId"), 80).strip()
    if session_id and not _looks_like_uuid(session_id):
        session_id = ""
    if not channel_name and not session_id:
        return None
    out: dict[str, str] = {}
    if channel_name:
        out["channel_name"] = channel_name
    if session_id:
        out["session_id"] = session_id
    return out or None


def _normalize_agent_ref(value: Any, *, include_channel: bool) -> Optional[dict[str, str]]:
    if not isinstance(value, dict):
        return None
    out: dict[str, str] = {}
    if include_channel:
        channel_name = _safe_text(value.get("channel_name") or value.get("channelName"), 200).strip()
        if channel_name:
            out["channel_name"] = channel_name
    agent_name = _safe_text(value.get("agent_name") or value.get("agentName"), 200).strip()
    if agent_name:
        out["agent_name"] = agent_name
    session_id = _safe_text(value.get("session_id") or value.get("sessionId"), 80).strip()
    if session_id and _looks_like_uuid(session_id):
        out["session_id"] = session_id
    alias = _safe_text(value.get("alias"), 200).strip()
    if alias:
        out["alias"] = alias
    return out or None


def _pick_payload_value(primary: dict[str, Any], fallback: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in primary:
            return primary.get(key)
    for key in keys:
        if key in fallback:
            return fallback.get(key)
    return None


def _normalize_mention_targets(value: Any) -> list[dict[str, str]]:
    """Normalize mention target objects from snake/camel payloads.

    V1 contract keeps this as optional, passthrough-only metadata.
    Invalid rows are ignored to preserve legacy announce behavior.
    """
    if not isinstance(value, list):
        return []
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, dict):
            continue
        channel_name = _safe_text(item.get("channel_name") or item.get("channelName"), 200).strip()
        session_id = _safe_text(item.get("session_id") or item.get("sessionId"), 80).strip()
        if not (channel_name and session_id and _looks_like_uuid(session_id)):
            continue
        row: dict[str, str] = {
            "channel_name": channel_name,
            "session_id": session_id,
        }
        cli_type = _safe_text(item.get("cli_type") or item.get("cliType"), 40).strip().lower()
        if cli_type:
            row["cli_type"] = cli_type
        display_name = _safe_text(item.get("display_name") or item.get("displayName"), 200).strip()
        if display_name:
            row["display_name"] = display_name
        project_id = _safe_text(item.get("project_id") or item.get("projectId"), 120).strip()
        if project_id:
            row["project_id"] = project_id
        dedupe_key = f"{channel_name}|{session_id}"
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        rows.append(row)
        if len(rows) >= 20:
            break
    return rows


def _normalize_reply_to_fields(value: Any) -> Optional[dict[str, str]]:
    if not isinstance(value, dict):
        return None
    out: dict[str, str] = {}
    reply_to_run_id = _safe_text(
        value.get("reply_to_run_id") if "reply_to_run_id" in value else value.get("replyToRunId"),
        80,
    ).strip()
    reply_to_sender_name = _safe_text(
        value.get("reply_to_sender_name") if "reply_to_sender_name" in value else value.get("replyToSenderName"),
        200,
    ).strip()
    reply_to_created_at = _safe_text(
        value.get("reply_to_created_at") if "reply_to_created_at" in value else value.get("replyToCreatedAt"),
        80,
    ).strip()
    reply_to_preview = _safe_text(
        value.get("reply_to_preview") if "reply_to_preview" in value else value.get("replyToPreview"),
        1000,
    ).strip()
    if reply_to_run_id:
        out["reply_to_run_id"] = reply_to_run_id
    if reply_to_sender_name:
        out["reply_to_sender_name"] = reply_to_sender_name
    if reply_to_created_at:
        out["reply_to_created_at"] = reply_to_created_at
    if reply_to_preview:
        out["reply_to_preview"] = reply_to_preview
    return out or None


def _normalize_message_ref(value: Any, *, allow_run_id: bool = False) -> Optional[dict[str, str]]:
    if not isinstance(value, dict):
        return None
    out: dict[str, str] = {}
    project_id = _safe_text(
        value.get("project_id") if "project_id" in value else value.get("projectId"),
        80,
    ).strip()
    channel_name = _safe_text(
        value.get("channel_name") if "channel_name" in value else value.get("channelName"),
        200,
    ).strip()
    session_id = _safe_text(
        value.get("session_id") if "session_id" in value else value.get("sessionId"),
        80,
    ).strip()
    run_id = _safe_text(value.get("run_id") if "run_id" in value else value.get("runId"), 80).strip()
    if project_id:
        out["project_id"] = project_id
    if channel_name:
        out["channel_name"] = channel_name
    if session_id:
        out["session_id"] = session_id
    if allow_run_id and run_id:
        out["run_id"] = run_id
    return out or None


def _compact_route_resolution_v1(route_resolution: Any) -> dict[str, Any]:
    """Keep V1 source-run route log to the minimal frozen fields."""
    src = route_resolution if isinstance(route_resolution, dict) else {}
    out: dict[str, Any] = {}
    source = _safe_text(src.get("source"), 80).strip().lower()
    if source:
        out["source"] = source
    fallback_stage = _safe_text(src.get("fallback_stage"), 80).strip().lower()
    if fallback_stage:
        out["fallback_stage"] = fallback_stage
    degrade_reason = _safe_text(src.get("degrade_reason"), 120).strip().lower()
    if degrade_reason:
        out["degrade_reason"] = degrade_reason
    source_ref = _normalize_message_ref(src.get("source_ref"), allow_run_id=True)
    if source_ref:
        out["source_ref"] = source_ref
    final_target = _normalize_callback_to(src.get("final_target"))
    if final_target:
        out["final_target"] = final_target
    return out


def _sanitize_communication_view(value: Any) -> Optional[dict[str, Any]]:
    if not isinstance(value, dict):
        return None
    communication_view = value
    cv: dict[str, Any] = {}
    message_kind = _safe_text(
        communication_view.get("message_kind") if "message_kind" in communication_view else communication_view.get("messageKind"),
        80,
    ).strip().lower()
    if message_kind:
        cv["message_kind"] = message_kind
    cv_event_reason = _safe_text(
        communication_view.get("event_reason") if "event_reason" in communication_view else communication_view.get("eventReason"),
        80,
    ).strip().lower()
    if cv_event_reason:
        cv["event_reason"] = (
            cv_event_reason
            if cv_event_reason in {"success", "unverified", "route_mismatch"}
            else "unverified"
        )
    cv_dispatch_state = _safe_text(
        communication_view.get("dispatch_state") if "dispatch_state" in communication_view else communication_view.get("dispatchState"),
        80,
    ).strip().lower()
    if cv_dispatch_state:
        cv["dispatch_state"] = (
            cv_dispatch_state
            if cv_dispatch_state in {"resolved", "fallback", "route_mismatch", "pending"}
            else "pending"
        )
    cv_dispatch_run_id = _safe_text(
        communication_view.get("dispatch_run_id") if "dispatch_run_id" in communication_view else communication_view.get("dispatchRunId"),
        120,
    ).strip()
    if cv_dispatch_run_id:
        cv["dispatch_run_id"] = cv_dispatch_run_id
    cv_route_mismatch = (
        communication_view.get("route_mismatch")
        if "route_mismatch" in communication_view
        else communication_view.get("routeMismatch")
    )
    if isinstance(cv_route_mismatch, bool):
        cv["route_mismatch"] = cv_route_mismatch
    cv_source_project_id = _safe_text(
        communication_view.get("source_project_id") if "source_project_id" in communication_view else communication_view.get("sourceProjectId"),
        80,
    ).strip()
    if cv_source_project_id:
        cv["source_project_id"] = cv_source_project_id
    cv_source_channel = _safe_text(
        communication_view.get("source_channel") if "source_channel" in communication_view else communication_view.get("sourceChannel"),
        200,
    ).strip()
    if cv_source_channel:
        cv["source_channel"] = cv_source_channel
    cv_source_session_id = _safe_text(
        communication_view.get("source_session_id") if "source_session_id" in communication_view else communication_view.get("sourceSessionId"),
        80,
    ).strip()
    if cv_source_session_id:
        cv["source_session_id"] = cv_source_session_id
    cv_target_project_id = _safe_text(
        communication_view.get("target_project_id") if "target_project_id" in communication_view else communication_view.get("targetProjectId"),
        80,
    ).strip()
    if cv_target_project_id:
        cv["target_project_id"] = cv_target_project_id
    cv_target_channel = _safe_text(
        communication_view.get("target_channel") if "target_channel" in communication_view else communication_view.get("targetChannel"),
        200,
    ).strip()
    if cv_target_channel:
        cv["target_channel"] = cv_target_channel
    cv_target_session_id = _safe_text(
        communication_view.get("target_session_id") if "target_session_id" in communication_view else communication_view.get("targetSessionId"),
        80,
    ).strip()
    if cv_target_session_id:
        cv["target_session_id"] = cv_target_session_id
    cv_route_resolution = _compact_route_resolution_v1(communication_view.get("route_resolution") if "route_resolution" in communication_view else communication_view.get("routeResolution"))
    if cv_route_resolution:
        cv["route_resolution"] = cv_route_resolution
    cv_version = _safe_text(communication_view.get("version"), 20).strip()
    if cv_version:
        cv["version"] = cv_version
    return cv or None


def _sanitize_receipt_summary(value: Any) -> Optional[dict[str, Any]]:
    if not isinstance(value, dict):
        return None
    src = value
    out: dict[str, Any] = {"version": "v1"}

    def _pick_text(keys: list[str], max_len: int = 500) -> str:
        for k in keys:
            if k not in src:
                continue
            txt = _safe_text(src.get(k), max_len).strip()
            if txt:
                return txt
        return ""

    source_channel = _pick_text(["source_channel", "sourceChannel"], 200)
    source_project_id = _pick_text(["source_project_id", "sourceProjectId"], 80)
    source_session_id = _pick_text(["source_session_id", "sourceSessionId"], 80)
    target_project_id = _pick_text(["target_project_id", "targetProjectId"], 80)
    target_channel = _pick_text(["target_channel", "targetChannel"], 200)
    target_session_id = _pick_text(["target_session_id", "targetSessionId"], 80)
    callback_task = _pick_text(["callback_task", "callbackTask"], 1200)
    execution_stage = _pick_text(["execution_stage", "executionStage"], 40)
    goal = _pick_text(["goal"], 300)
    conclusion = _pick_text(["conclusion"], 120)
    progress = _pick_text(["progress"], 300)
    need_peer = _pick_text(["need_peer", "needPeer"], 260)
    expected_result = _pick_text(["expected_result", "expectedResult"], 260)
    need_confirm = _pick_text(["need_confirm", "needConfirm"], 200)
    headline = _pick_text(["headline"], 200)
    message_kind = _pick_text(["message_kind", "messageKind"], 60)

    if source_channel:
        out["source_channel"] = source_channel
    if source_project_id:
        out["source_project_id"] = source_project_id
    if source_session_id:
        out["source_session_id"] = source_session_id
    if target_project_id:
        out["target_project_id"] = target_project_id
    if target_channel:
        out["target_channel"] = target_channel
    if target_session_id:
        out["target_session_id"] = target_session_id
    if callback_task:
        out["callback_task"] = callback_task
    if execution_stage:
        out["execution_stage"] = execution_stage
    if goal:
        out["goal"] = goal
    if conclusion:
        out["conclusion"] = conclusion
    if progress:
        out["progress"] = progress
    if need_peer:
        out["need_peer"] = need_peer
    if expected_result:
        out["expected_result"] = expected_result
    if need_confirm:
        out["need_confirm"] = need_confirm
    if headline:
        out["headline"] = headline
    if message_kind:
        out["message_kind"] = message_kind

    actions = src.get("system_actions")
    if isinstance(actions, list):
        rows: list[str] = []
        for x in actions:
            txt = _safe_text(x, 260).strip()
            if txt:
                rows.append(txt)
        if rows:
            out["system_actions"] = rows[:6]

    late_callback = src.get("late_callback")
    if isinstance(late_callback, bool):
        out["late_callback"] = late_callback
    late_reason = _pick_text(["late_reason", "lateReason"], 80).lower()
    if late_reason:
        out["late_reason"] = late_reason

    technical = src.get("technical")
    if isinstance(technical, dict):
        t: dict[str, Any] = {}
        event_type = _safe_text(technical.get("event_type"), 40).strip().lower()
        if event_type:
            t["event_type"] = event_type
        event_reason = _safe_text(technical.get("event_reason"), 80).strip().lower()
        if event_reason:
            t["event_reason"] = event_reason
        source_run_id = _safe_text(technical.get("source_run_id"), 80).strip()
        if source_run_id:
            t["source_run_id"] = source_run_id
        trigger_type = _safe_text(technical.get("trigger_type"), 80).strip().lower()
        if trigger_type:
            t["trigger_type"] = trigger_type
        invalid_terminal_preview_reason = _safe_text(technical.get("invalid_terminal_preview_reason"), 80).strip().lower()
        if invalid_terminal_preview_reason:
            t["invalid_terminal_preview_reason"] = invalid_terminal_preview_reason
        source_run_ids = technical.get("source_run_ids")
        if isinstance(source_run_ids, list):
            vals: list[str] = []
            for x in source_run_ids:
                s = _safe_text(x, 80).strip()
                if s:
                    vals.append(s)
            if vals:
                t["source_run_ids"] = vals[:120]
        route_resolution = technical.get("route_resolution")
        if isinstance(route_resolution, dict):
            rr = _compact_route_resolution_v1(route_resolution)
            if rr:
                t["route_resolution"] = rr
        if t:
            out["technical"] = t

    return out if len(out) > 1 else None


def _extract_run_extra_fields(payload: dict[str, Any]) -> dict[str, Any]:
    obj = payload if isinstance(payload, dict) else {}
    extra_obj = obj.get("run_extra_meta") if "run_extra_meta" in obj else obj.get("runExtraMeta")
    extra_obj = extra_obj if isinstance(extra_obj, dict) else {}
    out: dict[str, Any] = {}

    source_ref = _normalize_message_ref(
        _pick_payload_value(obj, extra_obj, "source_ref", "sourceRef"),
        allow_run_id=True,
    )
    if source_ref:
        out["source_ref"] = source_ref

    target_ref = _normalize_message_ref(
        _pick_payload_value(obj, extra_obj, "target_ref", "targetRef")
    )
    if target_ref:
        out["target_ref"] = target_ref

    cb = _normalize_callback_to(_pick_payload_value(obj, extra_obj, "callback_to", "callbackTo"))
    if cb is None:
        raw_cb = _pick_payload_value(obj, extra_obj, "callback_to", "callbackTo")
        if isinstance(raw_cb, dict):
            raw_sid = _safe_text(raw_cb.get("session_id") or raw_cb.get("sessionId"), 80).strip().lower()
            if raw_sid in {"none", "null"} and isinstance(source_ref, dict):
                source_channel = _safe_text(source_ref.get("channel_name"), 200).strip()
                if source_channel:
                    cb = {"channel_name": source_channel}
    if cb:
        out["callback_to"] = cb

    owner_ref = _normalize_agent_ref(_pick_payload_value(obj, extra_obj, "owner_ref", "ownerRef"), include_channel=True)
    if owner_ref:
        out["owner_ref"] = owner_ref

    sender_agent_ref = _normalize_agent_ref(
        _pick_payload_value(obj, extra_obj, "sender_agent_ref", "senderAgentRef"),
        include_channel=False,
    )
    if sender_agent_ref:
        out["sender_agent_ref"] = sender_agent_ref

    mention_targets = _normalize_mention_targets(
        _pick_payload_value(obj, extra_obj, "mention_targets", "mentionTargets")
    )
    if mention_targets:
        out["mention_targets"] = mention_targets

    reply_to = _normalize_reply_to_fields(obj)
    if reply_to:
        out.update(reply_to)

    task_path = _safe_text(obj.get("task_path") if "task_path" in obj else obj.get("taskPath"), 1200).strip()
    if task_path:
        out["task_path"] = task_path

    execution_mode = _safe_text(
        obj.get("execution_mode") if "execution_mode" in obj else obj.get("executionMode"),
        40,
    ).strip().lower()
    if execution_mode:
        out["execution_mode"] = execution_mode

    trigger_type = _safe_text(
        obj.get("trigger_type") if "trigger_type" in obj else obj.get("triggerType"),
        80,
    ).strip().lower()
    if trigger_type:
        out["trigger_type"] = trigger_type

    owner_channel = _safe_text(
        obj.get("owner_channel_name") if "owner_channel_name" in obj else obj.get("ownerChannelName"),
        200,
    ).strip()
    if owner_channel:
        out["owner_channel_name"] = owner_channel

    execution_stage = _safe_text(
        obj.get("execution_stage") if "execution_stage" in obj else obj.get("executionStage"),
        40,
    ).strip().lower()
    if execution_stage:
        out["execution_stage"] = execution_stage

    current_conclusion = _safe_text(
        obj.get("current_conclusion") if "current_conclusion" in obj else obj.get("currentConclusion"),
        200,
    ).strip()
    if current_conclusion:
        out["current_conclusion"] = current_conclusion

    need_confirmation = _safe_text(
        obj.get("need_confirmation")
        if "need_confirmation" in obj
        else (obj.get("needConfirmation") if "needConfirmation" in obj else obj.get("need_confirm")),
        200,
    ).strip()
    if need_confirmation:
        out["need_confirmation"] = need_confirmation

    next_action = _safe_text(
        obj.get("next_action") if "next_action" in obj else obj.get("nextAction"),
        200,
    ).strip()
    if next_action:
        out["next_action"] = next_action

    blocking_status = _safe_text(
        obj.get("blocking_status")
        if "blocking_status" in obj
        else (obj.get("blockingStatus") if "blockingStatus" in obj else obj.get("blocked")),
        40,
    ).strip().lower()
    if blocking_status:
        if blocking_status in {"1", "true", "yes", "y", "on", "阻塞"}:
            out["blocking_status"] = "blocked"
        elif blocking_status in {"0", "false", "no", "n", "off", "未阻塞"}:
            out["blocking_status"] = "unblocked"
        else:
            out["blocking_status"] = blocking_status

    model = _safe_text(obj.get("model"), 120).strip()
    if model:
        out["model"] = model

    message_kind = _safe_text(
        _pick_payload_value(obj, extra_obj, "message_kind", "messageKind"),
        80,
    ).strip().lower()
    if message_kind:
        out["message_kind"] = message_kind

    interaction_mode = _safe_text(
        _pick_payload_value(obj, extra_obj, "interaction_mode", "interactionMode"),
        80,
    ).strip().lower()
    if interaction_mode in {"dialog_now", "task_with_receipt", "notify_only"}:
        out["interaction_mode"] = interaction_mode

    receipt_summary = _sanitize_receipt_summary(
        _pick_payload_value(obj, extra_obj, "receipt_summary", "receiptSummary")
    )
    if receipt_summary:
        out["receipt_summary"] = receipt_summary

    project_execution_context = _pick_payload_value(
        obj,
        extra_obj,
        "project_execution_context",
        "projectExecutionContext",
    )
    if isinstance(project_execution_context, dict):
        out["project_execution_context"] = project_execution_context

    return out


def _sanitize_local_server_origin(raw: Any) -> str:
    text = _safe_text(raw, 300).strip().rstrip("/")
    if not text:
        return ""
    try:
        parsed = urlparse(text)
    except Exception:
        return ""
    scheme = str(parsed.scheme or "").strip().lower()
    host = str(parsed.hostname or "").strip().lower()
    if scheme not in {"http", "https"}:
        return ""
    if host not in {"127.0.0.1", "localhost", "::1"}:
        return ""
    if not parsed.netloc:
        return ""
    return f"{scheme}://{parsed.netloc}"


def _sanitize_run_extra_meta(extra_meta: Any) -> dict[str, Any]:
    src = extra_meta if isinstance(extra_meta, dict) else {}
    out: dict[str, Any] = {}

    source_ref = _normalize_message_ref(
        src.get("source_ref") if "source_ref" in src else src.get("sourceRef"),
        allow_run_id=True,
    )
    if source_ref:
        out["source_ref"] = source_ref

    target_ref = _normalize_message_ref(src.get("target_ref") if "target_ref" in src else src.get("targetRef"))
    if target_ref:
        out["target_ref"] = target_ref

    cb = _normalize_callback_to(src.get("callback_to") if "callback_to" in src else src.get("callbackTo"))
    if cb:
        out["callback_to"] = cb

    owner_ref = _normalize_agent_ref(
        src.get("owner_ref") if "owner_ref" in src else src.get("ownerRef"),
        include_channel=True,
    )
    if owner_ref:
        out["owner_ref"] = owner_ref

    sender_agent_ref = _normalize_agent_ref(
        src.get("sender_agent_ref") if "sender_agent_ref" in src else src.get("senderAgentRef"),
        include_channel=False,
    )
    if sender_agent_ref:
        out["sender_agent_ref"] = sender_agent_ref

    mention_targets = _normalize_mention_targets(
        src.get("mention_targets") if "mention_targets" in src else src.get("mentionTargets")
    )
    if mention_targets:
        out["mention_targets"] = mention_targets

    reply_to = _normalize_reply_to_fields(src)
    if reply_to:
        out.update(reply_to)

    task_path = _safe_text(src.get("task_path"), 1200).strip()
    if task_path:
        out["task_path"] = task_path

    execution_mode = _safe_text(src.get("execution_mode"), 40).strip().lower()
    if execution_mode:
        out["execution_mode"] = execution_mode

    trigger_type = _safe_text(src.get("trigger_type"), 80).strip().lower()
    if trigger_type:
        out["trigger_type"] = trigger_type

    topic = _safe_text(src.get("topic"), 300).strip()
    if topic:
        out["topic"] = topic

    task_id = _safe_text(src.get("task_id"), 300).strip()
    if task_id:
        out["task_id"] = task_id

    owner_channel = _safe_text(src.get("owner_channel_name"), 200).strip()
    if owner_channel:
        out["owner_channel_name"] = owner_channel

    execution_stage = _safe_text(src.get("execution_stage"), 40).strip().lower()
    if execution_stage:
        out["execution_stage"] = execution_stage

    current_conclusion = _safe_text(src.get("current_conclusion"), 200).strip()
    if current_conclusion:
        out["current_conclusion"] = current_conclusion

    need_confirmation = _safe_text(src.get("need_confirmation"), 200).strip()
    if need_confirmation:
        out["need_confirmation"] = need_confirmation

    next_action = _safe_text(src.get("next_action"), 200).strip()
    if next_action:
        out["next_action"] = next_action

    blocking_status = _safe_text(src.get("blocking_status"), 40).strip().lower()
    if blocking_status:
        out["blocking_status"] = blocking_status

    model = _safe_text(src.get("model"), 120).strip()
    if model:
        out["model"] = model

    message_kind = _safe_text(
        src.get("message_kind") if "message_kind" in src else src.get("messageKind"),
        80,
    ).strip().lower()
    if message_kind:
        out["message_kind"] = message_kind

    interaction_mode = _safe_text(
        src.get("interaction_mode") if "interaction_mode" in src else src.get("interactionMode"),
        80,
    ).strip().lower()
    if interaction_mode in {"dialog_now", "task_with_receipt", "notify_only"}:
        out["interaction_mode"] = interaction_mode

    visible_in_channel_chat = (
        src.get("visible_in_channel_chat")
        if "visible_in_channel_chat" in src
        else src.get("visibleInChannelChat")
    )
    if isinstance(visible_in_channel_chat, bool):
        out["visible_in_channel_chat"] = visible_in_channel_chat
    elif visible_in_channel_chat is not None:
        out["visible_in_channel_chat"] = _coerce_bool(visible_in_channel_chat, False)

    plan_first = src.get("plan_first") if "plan_first" in src else src.get("planFirst")
    if isinstance(plan_first, bool):
        if plan_first:
            out["plan_first"] = True
    elif plan_first is not None and _coerce_bool(plan_first, False):
        out["plan_first"] = True

    plan_phase = _safe_text(
        src.get("plan_phase") if "plan_phase" in src else src.get("planPhase"),
        40,
    ).strip().lower()
    if plan_phase in {"planning", "execution"}:
        out["plan_phase"] = plan_phase

    plan_prompt_version = _safe_text(src.get("plan_prompt_version"), 40).strip().lower()
    if plan_prompt_version:
        out["plan_prompt_version"] = plan_prompt_version

    task_with_receipt_guard_version = _safe_text(src.get("task_with_receipt_guard_version"), 40).strip().lower()
    if task_with_receipt_guard_version:
        out["task_with_receipt_guard_version"] = task_with_receipt_guard_version

    event_type = _safe_text(src.get("event_type"), 40).strip().lower()
    if event_type:
        out["event_type"] = event_type

    event_reason = _safe_text(src.get("event_reason"), 80).strip().lower()
    if event_reason:
        out["event_reason"] = event_reason

    source_run_id = _safe_text(src.get("source_run_id"), 80).strip()
    if source_run_id:
        out["source_run_id"] = source_run_id

    feedback_file_path = _safe_text(src.get("feedback_file_path"), 1200).strip()
    if feedback_file_path:
        out["feedback_file_path"] = feedback_file_path

    task_push_job_id = _safe_text(src.get("task_push_job_id"), 80).strip()
    if task_push_job_id:
        out["task_push_job_id"] = task_push_job_id

    task_push_attempt = src.get("task_push_attempt")
    if task_push_attempt is not None:
        try:
            n = int(task_push_attempt)
            if n > 0:
                out["task_push_attempt"] = n
        except Exception:
            pass

    assist_request_id = _safe_text(src.get("assist_request_id"), 80).strip()
    if assist_request_id:
        out["assist_request_id"] = assist_request_id

    assist_request_status_before = _safe_text(src.get("assist_request_status_before"), 40).strip().lower()
    if assist_request_status_before:
        out["assist_request_status_before"] = assist_request_status_before

    assist_request_reply_by = _safe_text(src.get("assist_request_reply_by"), 20).strip().lower()
    if assist_request_reply_by in {"user", "agent", "system"}:
        out["assist_request_reply_by"] = assist_request_reply_by

    assist_request_close_action = _safe_text(src.get("assist_request_close_action"), 40).strip().lower()
    if assist_request_close_action:
        out["assist_request_close_action"] = assist_request_close_action

    assist_request_close_by = _safe_text(src.get("assist_request_close_by"), 20).strip().lower()
    if assist_request_close_by in {"user", "agent", "system"}:
        out["assist_request_close_by"] = assist_request_close_by

    assist_context_refs = src.get("assist_context_refs")
    if isinstance(assist_context_refs, list):
        refs: list[str] = []
        for x in assist_context_refs:
            s = _safe_text(x, 1200).strip()
            if s:
                refs.append(s)
        if refs:
            out["assist_context_refs"] = refs[:20]

    route_resolution = src.get("route_resolution")
    if isinstance(route_resolution, dict):
        rr: dict[str, Any] = {}
        source = _safe_text(route_resolution.get("source"), 80).strip().lower()
        if source:
            rr["source"] = source
        fallback_stage = _safe_text(route_resolution.get("fallback_stage"), 80).strip().lower()
        if fallback_stage:
            rr["fallback_stage"] = fallback_stage
        degrade_reason = _safe_text(route_resolution.get("degrade_reason"), 120).strip().lower()
        if degrade_reason:
            rr["degrade_reason"] = degrade_reason
        source_ref = _normalize_message_ref(route_resolution.get("source_ref"), allow_run_id=True)
        if source_ref:
            rr["source_ref"] = source_ref
        resolved_target = _normalize_callback_to(route_resolution.get("resolved_target"))
        if resolved_target:
            rr["resolved_target"] = resolved_target
        original_callback_to = _normalize_callback_to(route_resolution.get("original_callback_to"))
        if original_callback_to:
            rr["original_callback_to"] = original_callback_to
        reasons = route_resolution.get("fallback_reasons")
        if isinstance(reasons, list):
            vals = []
            for x in reasons:
                s = _safe_text(x, 120).strip()
                if s:
                    vals.append(s)
            if vals:
                rr["fallback_reasons"] = vals[:8]
        final_target = _normalize_callback_to(route_resolution.get("final_target"))
        if final_target:
            rr["final_target"] = final_target
        if rr:
            out["route_resolution"] = rr

    callback_summary_of = src.get("callback_summary_of")
    if isinstance(callback_summary_of, list):
        vals = []
        for x in callback_summary_of:
            s = _safe_text(x, 80).strip()
            if s:
                vals.append(s)
        if vals:
            out["callback_summary_of"] = vals[:50]

    callback_anchor_key = _safe_text(src.get("callback_anchor_key"), 500).strip()
    if callback_anchor_key:
        out["callback_anchor_key"] = callback_anchor_key

    callback_aggregate_count = src.get("callback_aggregate_count")
    if callback_aggregate_count is not None:
        try:
            n = int(callback_aggregate_count)
            if n > 0:
                out["callback_aggregate_count"] = min(n, 5000)
        except Exception:
            pass

    callback_last_merged_at = _safe_text(src.get("callback_last_merged_at"), 80).strip()
    if callback_last_merged_at:
        out["callback_last_merged_at"] = callback_last_merged_at

    callback_aggregate_source_run_ids = src.get("callback_aggregate_source_run_ids")
    if isinstance(callback_aggregate_source_run_ids, list):
        vals = []
        for x in callback_aggregate_source_run_ids:
            s = _safe_text(x, 80).strip()
            if s:
                vals.append(s)
        if vals:
            out["callback_aggregate_source_run_ids"] = vals[:120]

    callback_merge_mode = _safe_text(src.get("callback_merge_mode"), 80).strip().lower()
    if callback_merge_mode:
        out["callback_merge_mode"] = callback_merge_mode

    local_server_origin = _sanitize_local_server_origin(src.get("localServerOrigin"))
    if local_server_origin:
        out["localServerOrigin"] = local_server_origin

    environment = _safe_text(src.get("environment") if "environment" in src else src.get("environmentName"), 80).strip()
    if environment:
        out["environment"] = environment

    worktree_root = _safe_text(src.get("worktree_root") if "worktree_root" in src else src.get("worktreeRoot"), 4000).strip()
    if worktree_root:
        out["worktree_root"] = worktree_root

    workdir = _safe_text(src.get("workdir"), 4000).strip()
    if workdir:
        out["workdir"] = workdir

    branch = _safe_text(src.get("branch"), 240).strip()
    if branch:
        out["branch"] = branch

    project_execution_context = src.get("project_execution_context")
    if isinstance(project_execution_context, dict):
        override = project_execution_context.get("override")
        out["project_execution_context"] = build_project_execution_context(
            target=project_execution_context.get("target"),
            source=project_execution_context.get("source"),
            context_source=project_execution_context.get("context_source"),
            override_fields=list((override or {}).get("fields") or []),
            override_source=(override or {}).get("source"),
        )

    callback_anchor_action = _safe_text(src.get("callback_anchor_action"), 80).strip().lower()
    if callback_anchor_action:
        out["callback_anchor_action"] = callback_anchor_action

    display_host_run_id = _safe_text(src.get("display_host_run_id"), 80).strip()
    if display_host_run_id:
        out["display_host_run_id"] = display_host_run_id

    communication_view = _sanitize_communication_view(src.get("communication_view"))
    if communication_view:
        out["communication_view"] = communication_view

    receipt_summary = _sanitize_receipt_summary(src.get("receipt_summary"))
    if receipt_summary:
        out["receipt_summary"] = receipt_summary

    return out


_PLAN_FIRST_PROMPT_VERSION = "v1"
_PLAN_FIRST_MARKER = "[计划优先约束]"


def _build_plan_first_prefix() -> str:
    return "\n".join(
        [
            _PLAN_FIRST_MARKER,
            "1. 先输出 3-5 步计划，包含风险点与回滚口径。",
            "2. 若任务目标与边界已明确，可在计划后继续执行；若存在关键不确定项，先停在计划与待确认项。",
            "3. 未经确认，不要直接执行高风险操作或大范围改动。",
            "4. 执行完成后回传证据：改动文件、接口落点、测试结果。",
        ]
    )


def _apply_plan_first_to_message(message: Any, run_extra_meta: Any) -> tuple[str, dict[str, Any]]:
    raw_message = _safe_text(message, 20_000).strip()
    clean_meta = _sanitize_run_extra_meta(run_extra_meta)
    interaction_mode = str(clean_meta.get("interaction_mode") or "").strip().lower()

    if bool(clean_meta.get("plan_first")):
        if not str(clean_meta.get("plan_phase") or "").strip():
            clean_meta["plan_phase"] = "planning"
        if not str(clean_meta.get("plan_prompt_version") or "").strip():
            clean_meta["plan_prompt_version"] = _PLAN_FIRST_PROMPT_VERSION
        if raw_message and _PLAN_FIRST_MARKER not in raw_message:
            raw_message = f"{_build_plan_first_prefix()}\n\n{raw_message}"

    if raw_message and interaction_mode == "task_with_receipt":
        if _TASK_WITH_RECEIPT_GUARD_MARKER not in raw_message:
            raw_message = (
                f"{raw_message}\n\n"
                f"{_TASK_WITH_RECEIPT_GUARD_MARKER}\n"
                "- 本轮结论只允许基于当前回执任务与当前消息主线；历史错线 run 只能排除，不能当成本主线结果。\n"
                "- 禁止轮询当前执行 run 自己的 runtime log files 来判断“是否已完成”。\n"
                "- 若当前 run 仍在执行，禁止把“本 run 仍在 running / 等待本 run 完成 / 等待当前 run 落盘”写成最终回执。\n"
                "- 若证据不足，请直接回单一阻塞，不要用自引用中间态补位。"
            )
        if not str(clean_meta.get("task_with_receipt_guard_version") or "").strip():
            clean_meta["task_with_receipt_guard_version"] = _TASK_WITH_RECEIPT_GUARD_VERSION

    return raw_message, clean_meta
