# -*- coding: utf-8 -*-

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

from task_dashboard.helpers import atomic_write_text, coerce_bool, coerce_int, looks_like_session_id, now_iso, read_json_file
from task_dashboard.task_identity import runtime_base_dir_for_repo


_STATE_VERSION = 1
_SCHEDULE_TYPES = {"interval", "daily"}
_DEFAULT_CONTEXT_SCOPE = {
    "recent_tasks_limit": 8,
    "recent_runs_limit": 8,
    "include_task_counts": True,
    "include_recent_tasks": True,
    "include_recent_runs": True,
}
_TASK_ASSISTANT_MODES: dict[str, dict[str, str]] = {
    "stale_progress": {
        "label": "长时间未推进提醒",
        "prompt_template": (
            "请仅围绕 task_id={task_id} 做长时间未推进观察。"
            "先核对当前任务链路、最近动作和是否存在卡点；"
            "若需要推动，只输出建议、催办对象与最小下一步。"
            "不要直接改任务状态，不要跨通道派单。"
        ),
    },
    "pending_receipt": {
        "label": "待回执催办建议",
        "prompt_template": (
            "请仅围绕 task_id={task_id} 检查是否存在待回执或待确认动作。"
            "若需要催办，只输出催办建议、目标对象与证据缺口；"
            "不要直接改任务状态，不要跨通道派单。"
        ),
    },
    "pending_acceptance": {
        "label": "待验收提醒",
        "prompt_template": (
            "请仅围绕 task_id={task_id} 检查是否已进入待验收但仍缺反馈、缺证据或缺回执。"
            "只输出补口建议与最小下一步，不要直接改任务状态。"
        ),
    },
    "pending_release": {
        "label": "待放行提醒",
        "prompt_template": (
            "请仅围绕 task_id={task_id} 检查当前是否卡在待放行或待拍板阶段。"
            "若仍阻塞，只输出阻塞点、建议联系对象与收口动作；"
            "不要直接改任务状态。"
        ),
    },
    "owner_inactive": {
        "label": "主负责人长时间无动作提醒",
        "prompt_template": (
            "请仅围绕 task_id={task_id} 检查主负责人是否长期无动作。"
            "若确有停滞，只输出提醒建议、建议回执对象与证据摘要；"
            "不要直接改任务状态，不要跨通道派单。"
        ),
    },
}
_MODE_ALIASES = {
    "stale": "stale_progress",
    "stale_progress_reminder": "stale_progress",
    "pending_receipt_followup": "pending_receipt",
    "acceptance_followup": "pending_acceptance",
    "pending_acceptance_reminder": "pending_acceptance",
    "pending_release_reminder": "pending_release",
    "owner_idle": "owner_inactive",
    "owner_inactive_reminder": "owner_inactive",
}
_DAILY_TIME_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


def _heartbeat_helpers_module():
    from task_dashboard.runtime import scheduler_helpers as helpers

    return helpers


def runtime_base_dir_for_session(session: Any, fallback_root: Any = None) -> Path:
    row = session if isinstance(session, dict) else {}
    candidates: list[str] = []
    execution_context = row.get("project_execution_context") if isinstance(row.get("project_execution_context"), dict) else {}
    target_ctx = execution_context.get("target") if isinstance(execution_context.get("target"), dict) else {}
    source_ctx = execution_context.get("source") if isinstance(execution_context.get("source"), dict) else {}
    for raw in (
        row.get("worktree_root"),
        row.get("workdir"),
        target_ctx.get("worktree_root"),
        target_ctx.get("workdir"),
        source_ctx.get("worktree_root"),
        source_ctx.get("workdir"),
        fallback_root,
    ):
        text = str(raw or "").strip()
        if text:
            candidates.append(text)
    for text in candidates:
        try:
            root = Path(text).expanduser().resolve()
        except Exception:
            continue
        return runtime_base_dir_for_repo(root)
    return runtime_base_dir_for_repo(Path(__file__).resolve().parents[2])


def task_assistant_state_path(*, runtime_base_dir: Path, project_id: str) -> Path:
    pid = str(project_id or "").strip() or "__global__"
    safe_pid = pid.replace("/", "_").replace("\\", "_").replace("..", "_")
    return Path(runtime_base_dir) / ".run" / "task_assistant" / f"{safe_pid}.json"


def load_task_assistant_state(*, runtime_base_dir: Path, project_id: str) -> dict[str, Any]:
    raw = read_json_file(task_assistant_state_path(runtime_base_dir=runtime_base_dir, project_id=project_id))
    state = raw if isinstance(raw, dict) else {}
    items = state.get("items")
    state["version"] = int(state.get("version") or _STATE_VERSION)
    state["project_id"] = str(state.get("project_id") or project_id or "").strip() or str(project_id or "").strip()
    state["updated_at"] = str(state.get("updated_at") or "").strip()
    state["items"] = items if isinstance(items, dict) else {}
    return state


def save_task_assistant_state(*, runtime_base_dir: Path, project_id: str, state: dict[str, Any]) -> Path:
    path = task_assistant_state_path(runtime_base_dir=runtime_base_dir, project_id=project_id)
    payload = dict(state if isinstance(state, dict) else {})
    payload["version"] = _STATE_VERSION
    payload["project_id"] = str(project_id or "").strip()
    payload["updated_at"] = now_iso()
    payload["items"] = dict(payload.get("items") or {})
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2))
    return path


def normalize_task_assistant_mode(value: Any, *, default: str = "stale_progress") -> str:
    raw = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    raw = _MODE_ALIASES.get(raw, raw)
    if raw in _TASK_ASSISTANT_MODES:
        return raw
    fallback = str(default or "stale_progress").strip().lower().replace("-", "_")
    fallback = _MODE_ALIASES.get(fallback, fallback)
    if fallback in _TASK_ASSISTANT_MODES:
        return fallback
    return "stale_progress"


def compiled_task_assistant_heartbeat_task_id(task_id: str) -> str:
    normalized_task_id = str(task_id or "").strip()
    helpers = _heartbeat_helpers_module()
    return helpers._normalize_heartbeat_task_id(
        f"task-assistant-{normalized_task_id}",
        default="task-assistant",
    )


def _normalize_schedule(raw: Any) -> dict[str, Any]:
    obj = raw if isinstance(raw, dict) else {}
    schedule_type = str(
        obj.get("type")
        if "type" in obj
        else (obj.get("schedule_type") if "schedule_type" in obj else obj.get("scheduleType"))
    ).strip().lower() or "interval"
    if schedule_type not in _SCHEDULE_TYPES:
        raise ValueError("invalid task assistant schedule.type")
    if schedule_type == "interval":
        interval_raw = (
            obj.get("interval_minutes")
            if "interval_minutes" in obj
            else obj.get("intervalMinutes")
        )
        interval_minutes = max(0, coerce_int(interval_raw, 60))
        if interval_minutes < 5:
            raise ValueError("task assistant schedule.interval_minutes must be >= 5")
        return {
            "type": "interval",
            "interval_minutes": int(interval_minutes),
            "daily_time": "",
            "weekdays": [],
        }
    daily_time = str(
        obj.get("daily_time")
        if "daily_time" in obj
        else obj.get("dailyTime")
        or "09:00"
    ).strip() or "09:00"
    if not _DAILY_TIME_RE.fullmatch(daily_time):
        raise ValueError("invalid task assistant schedule.daily_time")
    weekdays = _heartbeat_helpers_module()._normalize_heartbeat_weekdays(obj.get("weekdays"))
    return {
        "type": "daily",
        "interval_minutes": None,
        "daily_time": daily_time,
        "weekdays": weekdays,
    }


def _normalize_busy_policy(value: Any, *, default: str = "run_on_next_idle") -> str:
    helpers = _heartbeat_helpers_module()
    raw = str(value or "").strip().lower() or str(default or "run_on_next_idle").strip().lower()
    if raw in helpers._HEARTBEAT_TASK_BUSY_POLICIES:
        return raw
    return "run_on_next_idle"


def _normalize_max_execute_count(value: Any, *, default: int = 0) -> int:
    return max(0, coerce_int(value, default))


def normalize_task_assistant_config(
    raw: Any,
    *,
    task_id: str,
    existing: Optional[dict[str, Any]] = None,
    session_store: Any = None,
    project_id: str = "",
) -> dict[str, Any]:
    task_identifier = str(task_id or "").strip()
    if not task_identifier:
        raise ValueError("missing task_id")
    obj = raw if isinstance(raw, dict) else {}
    prev = existing if isinstance(existing, dict) else {}
    enabled = coerce_bool(obj.get("enabled"), coerce_bool(prev.get("enabled"), False))
    mode = normalize_task_assistant_mode(obj.get("mode"), default=str(prev.get("mode") or "stale_progress"))
    target_session_id = str(
        obj.get("target_session_id")
        if "target_session_id" in obj
        else obj.get("targetSessionId")
        or prev.get("target_session_id")
        or ""
    ).strip()
    if not target_session_id:
        raise ValueError("missing target_session_id")
    if not looks_like_session_id(target_session_id):
        raise ValueError("invalid target_session_id")
    if session_store is not None:
        target_session = session_store.get_session(target_session_id) or {}
        if not isinstance(target_session, dict) or not target_session:
            raise ValueError("target session not found")
        if bool(target_session.get("is_deleted")):
            raise ValueError("target session unavailable")
        target_project_id = str(target_session.get("project_id") or "").strip()
        if project_id and target_project_id and target_project_id != str(project_id or "").strip():
            raise ValueError("target session not in project whitelist")
    schedule_source = obj.get("schedule") if isinstance(obj.get("schedule"), dict) else None
    schedule = _normalize_schedule(schedule_source if schedule_source is not None else prev.get("schedule"))
    busy_policy = _normalize_busy_policy(
        obj.get("busy_policy") if "busy_policy" in obj else obj.get("busyPolicy"),
        default=str(prev.get("busy_policy") or "run_on_next_idle"),
    )
    max_execute_count = _normalize_max_execute_count(
        obj.get("max_execute_count") if "max_execute_count" in obj else obj.get("maxExecuteCount"),
        default=int(prev.get("max_execute_count") or 0),
    )
    return {
        "task_id": task_identifier,
        "enabled": bool(enabled),
        "mode": mode,
        "target_session_id": target_session_id,
        "schedule": schedule,
        "busy_policy": busy_policy,
        "max_execute_count": max_execute_count,
        "updated_at": now_iso(),
    }


def _mode_spec(mode: str) -> dict[str, str]:
    return _TASK_ASSISTANT_MODES.get(normalize_task_assistant_mode(mode), _TASK_ASSISTANT_MODES["stale_progress"])


def build_allowed_target_sessions(*, project_id: str, session_store: Any) -> list[dict[str, str]]:
    if session_store is None:
        return []
    try:
        sessions = session_store.list_sessions(str(project_id or "").strip())
    except Exception:
        return []
    out: list[dict[str, str]] = []
    for row in sessions if isinstance(sessions, list) else []:
        if not isinstance(row, dict) or bool(row.get("is_deleted")):
            continue
        session_id = str(row.get("id") or "").strip()
        if not session_id:
            continue
        alias = str(row.get("alias") or "").strip()
        channel_name = str(row.get("channel_name") or "").strip()
        out.append(
            {
                "session_id": session_id,
                "channel_name": channel_name,
                "alias": alias,
                "display_name": alias or channel_name or session_id,
            }
        )
    return out


def compile_task_assistant_to_heartbeat(
    *,
    project_id: str,
    task_id: str,
    config: dict[str, Any],
    session_store: Any,
) -> tuple[dict[str, Any], dict[str, Any]]:
    target_session_id = str(config.get("target_session_id") or "").strip()
    target_session = session_store.get_session(target_session_id) if session_store is not None else {}
    if not isinstance(target_session, dict) or not target_session:
        raise ValueError("target session not found")
    if bool(target_session.get("is_deleted")):
        raise ValueError("target session unavailable")
    target_project_id = str(target_session.get("project_id") or "").strip()
    if project_id and target_project_id and target_project_id != str(project_id or "").strip():
        raise ValueError("target session not in project whitelist")
    schedule = config.get("schedule") if isinstance(config.get("schedule"), dict) else {}
    mode = normalize_task_assistant_mode(config.get("mode"))
    mode_spec = _mode_spec(mode)
    compiled = _heartbeat_helpers_module()._normalize_heartbeat_task(
        {
            "heartbeat_task_id": compiled_task_assistant_heartbeat_task_id(task_id),
            "title": f"Task Assistant·{mode_spec.get('label') or mode}·{task_id}",
            "enabled": bool(config.get("enabled")),
            "channel_name": str(target_session.get("channel_name") or "").strip(),
            "session_id": target_session_id,
            "prompt_template": str(mode_spec.get("prompt_template") or "").format(task_id=str(task_id or "").strip()),
            "schedule_type": str(schedule.get("type") or "interval"),
            "interval_minutes": schedule.get("interval_minutes"),
            "daily_time": str(schedule.get("daily_time") or ""),
            "weekdays": list(schedule.get("weekdays") or []),
            "busy_policy": _normalize_busy_policy(config.get("busy_policy")),
            "max_execute_count": _normalize_max_execute_count(config.get("max_execute_count")),
            "context_scope": dict(_DEFAULT_CONTEXT_SCOPE),
        },
        index=0,
        id_required=True,
    )
    if not isinstance(compiled, dict):
        raise ValueError("failed to compile task assistant heartbeat task")
    return compiled, target_session


def _session_heartbeat_task_by_id(session: dict[str, Any], heartbeat_task_id: str) -> Optional[dict[str, Any]]:
    heartbeat_cfg = _heartbeat_helpers_module()._load_session_heartbeat_config(session)
    for row in heartbeat_cfg.get("tasks") or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("heartbeat_task_id") or "").strip() == str(heartbeat_task_id or "").strip():
            return dict(row)
    return None


def _remove_task_from_session(*, session_store: Any, session: dict[str, Any], heartbeat_task_id: str) -> bool:
    helpers = _heartbeat_helpers_module()
    heartbeat_cfg = helpers._load_session_heartbeat_config(session)
    current_tasks = helpers._heartbeat_tasks_for_write(heartbeat_cfg.get("tasks"))
    merged_tasks = [row for row in current_tasks if str(row.get("heartbeat_task_id") or "").strip() != str(heartbeat_task_id or "").strip()]
    if len(merged_tasks) == len(current_tasks):
        return False
    heartbeat_payload = helpers._heartbeat_session_payload_for_write(
        session,
        enabled=any(bool(row.get("enabled")) for row in merged_tasks),
        tasks=merged_tasks,
    )
    return bool(session_store.update_session(str(session.get("id") or "").strip(), heartbeat=heartbeat_payload))


def _upsert_task_into_session(*, session_store: Any, session: dict[str, Any], heartbeat_task: dict[str, Any]) -> bool:
    helpers = _heartbeat_helpers_module()
    heartbeat_cfg = helpers._load_session_heartbeat_config(session)
    current_tasks = helpers._heartbeat_tasks_for_write(heartbeat_cfg.get("tasks"))
    task_id = str(heartbeat_task.get("heartbeat_task_id") or "").strip()
    merged_tasks: list[dict[str, Any]] = []
    replaced = False
    for row in current_tasks:
        if str(row.get("heartbeat_task_id") or "").strip() == task_id:
            merged_tasks.append(dict(heartbeat_task))
            replaced = True
        else:
            merged_tasks.append(row)
    if not replaced:
        merged_tasks.append(dict(heartbeat_task))
    heartbeat_payload = helpers._heartbeat_session_payload_for_write(
        session,
        enabled=any(bool(row.get("enabled")) for row in merged_tasks),
        tasks=merged_tasks,
    )
    return bool(session_store.update_session(str(session.get("id") or "").strip(), heartbeat=heartbeat_payload))


def sync_task_assistant_config(
    *,
    runtime_base_dir: Path,
    project_id: str,
    task_id: str,
    raw_config: Any,
    session_store: Any,
) -> tuple[dict[str, Any], Path]:
    state = load_task_assistant_state(runtime_base_dir=runtime_base_dir, project_id=project_id)
    items = dict(state.get("items") or {})
    existing = items.get(str(task_id or "").strip()) if isinstance(items.get(str(task_id or "").strip()), dict) else {}
    config = normalize_task_assistant_config(
        raw_config,
        task_id=task_id,
        existing=existing,
        session_store=session_store,
        project_id=project_id,
    )
    compiled_task, target_session = compile_task_assistant_to_heartbeat(
        project_id=project_id,
        task_id=task_id,
        config=config,
        session_store=session_store,
    )
    heartbeat_task_id = str(compiled_task.get("heartbeat_task_id") or "").strip()
    old_target_session_id = str(existing.get("target_session_id") or "").strip()
    if old_target_session_id and old_target_session_id != str(config.get("target_session_id") or "").strip():
        old_session = session_store.get_session(old_target_session_id) or {}
        if isinstance(old_session, dict) and old_session:
            _remove_task_from_session(session_store=session_store, session=old_session, heartbeat_task_id=heartbeat_task_id)
    _upsert_task_into_session(session_store=session_store, session=target_session, heartbeat_task=compiled_task)
    config["compiled_heartbeat_task_id"] = heartbeat_task_id
    items[str(task_id or "").strip()] = config
    state["items"] = items
    path = save_task_assistant_state(runtime_base_dir=runtime_base_dir, project_id=project_id, state=state)
    return config, path


def delete_task_assistant_config(
    *,
    runtime_base_dir: Path,
    project_id: str,
    task_id: str,
    session_store: Any,
) -> tuple[bool, Path]:
    state = load_task_assistant_state(runtime_base_dir=runtime_base_dir, project_id=project_id)
    items = dict(state.get("items") or {})
    existing = items.pop(str(task_id or "").strip(), None)
    heartbeat_task_id = compiled_task_assistant_heartbeat_task_id(task_id)
    if isinstance(existing, dict):
        target_session_id = str(existing.get("target_session_id") or "").strip()
        if target_session_id:
            session = session_store.get_session(target_session_id) or {}
            if isinstance(session, dict) and session:
                _remove_task_from_session(session_store=session_store, session=session, heartbeat_task_id=heartbeat_task_id)
    state["items"] = items
    path = save_task_assistant_state(runtime_base_dir=runtime_base_dir, project_id=project_id, state=state)
    return bool(isinstance(existing, dict)), path


def build_task_assistant_summary(
    *,
    runtime_base_dir: Path,
    project_id: str,
    task_id: str,
    session_store: Any = None,
    heartbeat_runtime: Any = None,
) -> dict[str, Any]:
    task_identifier = str(task_id or "").strip()
    heartbeat_task_id = compiled_task_assistant_heartbeat_task_id(task_identifier) if task_identifier else ""
    summary: dict[str, Any] = {
        "task_id": task_identifier,
        "available": bool(task_identifier),
        "configured": False,
        "enabled": False,
        "state": "disabled",
        "mode": "",
        "mode_label": "",
        "target_session_id": "",
        "target_channel_name": "",
        "schedule": {
            "type": "interval",
            "interval_minutes": 60,
            "daily_time": "",
            "weekdays": [],
        },
        "busy_policy": "run_on_next_idle",
        "max_execute_count": 0,
        "updated_at": "",
        "errors": [],
        "compiled": {
            "heartbeat_task_id": heartbeat_task_id,
            "exists": False,
            "ready": False,
            "enabled": False,
            "next_due_at": "",
            "last_status": "",
            "last_result": "",
            "last_error": "",
            "last_run_id": "",
            "executed_count": 0,
            "remaining_execute_count": 0,
            "history_count": 0,
            "session_id": "",
            "channel_name": "",
            "errors": [],
        },
    }
    if not task_identifier:
        return summary
    state = load_task_assistant_state(runtime_base_dir=runtime_base_dir, project_id=project_id)
    item = state.get("items", {}).get(task_identifier) if isinstance(state.get("items"), dict) else None
    if not isinstance(item, dict):
        return summary

    summary["configured"] = True
    summary["enabled"] = bool(item.get("enabled"))
    summary["mode"] = normalize_task_assistant_mode(item.get("mode"))
    summary["mode_label"] = str(_mode_spec(summary["mode"]).get("label") or "")
    summary["target_session_id"] = str(item.get("target_session_id") or "").strip()
    summary["schedule"] = _normalize_schedule(item.get("schedule"))
    summary["busy_policy"] = _normalize_busy_policy(item.get("busy_policy"))
    summary["max_execute_count"] = _normalize_max_execute_count(item.get("max_execute_count"))
    summary["updated_at"] = str(item.get("updated_at") or "").strip()
    summary["compiled"]["session_id"] = summary["target_session_id"]

    target_session = session_store.get_session(summary["target_session_id"]) if session_store is not None else {}
    if not isinstance(target_session, dict) or not target_session or bool(target_session.get("is_deleted")):
        summary["state"] = "blocked" if summary["enabled"] else "paused"
        summary["errors"] = ["task_assistant.target_session_unavailable"]
        summary["compiled"]["errors"] = ["task_assistant.target_session_unavailable"]
        return summary
    if project_id and str(target_session.get("project_id") or "").strip() not in {"", str(project_id or "").strip()}:
        summary["state"] = "blocked" if summary["enabled"] else "paused"
        summary["errors"] = ["task_assistant.target_session_outside_project"]
        summary["compiled"]["errors"] = ["task_assistant.target_session_outside_project"]
        return summary
    summary["target_channel_name"] = str(target_session.get("channel_name") or "").strip()
    summary["compiled"]["channel_name"] = summary["target_channel_name"]

    compiled_item: dict[str, Any] = {}
    if heartbeat_runtime is not None:
        try:
            compiled_item = heartbeat_runtime.get_session_task(project_id, summary["target_session_id"], heartbeat_task_id) or {}
        except Exception:
            compiled_item = {}
    if not compiled_item:
        compiled_item = _session_heartbeat_task_by_id(target_session, heartbeat_task_id) or {}

    if compiled_item:
        summary["compiled"].update(
            {
                "exists": True,
                "ready": bool(compiled_item.get("ready")),
                "enabled": bool(compiled_item.get("enabled")),
                "next_due_at": str(compiled_item.get("next_due_at") or ""),
                "last_status": str(compiled_item.get("last_status") or ""),
                "last_result": str(compiled_item.get("last_result") or ""),
                "last_error": str(compiled_item.get("last_error") or ""),
                "last_run_id": str(compiled_item.get("last_run_id") or ""),
                "executed_count": int(compiled_item.get("executed_count") or 0),
                "remaining_execute_count": int(compiled_item.get("remaining_execute_count") or 0),
                "history_count": int(compiled_item.get("history_count") or 0),
                "errors": list(compiled_item.get("errors") or []),
            }
        )
    else:
        summary["compiled"]["errors"] = ["task_assistant.compiled_heartbeat_missing"]

    if not summary["enabled"]:
        summary["state"] = "paused"
    elif summary["compiled"]["exists"] and summary["compiled"]["ready"] and not summary["compiled"]["errors"]:
        summary["state"] = "enabled"
    else:
        summary["state"] = "blocked"
        errors = list(summary.get("errors") or [])
        errors.extend(str(x) for x in (summary["compiled"].get("errors") or []) if str(x).strip())
        summary["errors"] = list(dict.fromkeys(errors))
    return summary


def get_task_assistant_response(
    *,
    runtime_base_dir: Path,
    project_id: str,
    task_id: str,
    session_store: Any,
    heartbeat_runtime: Any,
) -> tuple[int, dict[str, Any]]:
    pid = str(project_id or "").strip()
    tid = str(task_id or "").strip()
    if not pid:
        return 400, {"error": "missing project_id"}
    if not tid:
        return 400, {"error": "missing task_id"}
    return 200, {
        "ok": True,
        "project_id": pid,
        "task_id": tid,
        "task_assistant": build_task_assistant_summary(
            runtime_base_dir=runtime_base_dir,
            project_id=pid,
            task_id=tid,
            session_store=session_store,
            heartbeat_runtime=heartbeat_runtime,
        ),
        "allowed_target_sessions": build_allowed_target_sessions(project_id=pid, session_store=session_store),
        "config_path": str(task_assistant_state_path(runtime_base_dir=runtime_base_dir, project_id=pid)),
    }


def put_task_assistant_response(
    *,
    runtime_base_dir: Path,
    project_id: str,
    task_id: str,
    body: dict[str, Any],
    session_store: Any,
    heartbeat_runtime: Any,
) -> tuple[int, dict[str, Any]]:
    pid = str(project_id or "").strip()
    tid = str(task_id or "").strip()
    if not pid:
        return 400, {"error": "missing project_id"}
    if not tid:
        return 400, {"error": "missing task_id"}
    if not isinstance(body, dict):
        return 400, {"error": "bad json: object required"}
    config_payload = body.get("task_assistant") if isinstance(body.get("task_assistant"), dict) else body
    try:
        _config, config_path = sync_task_assistant_config(
            runtime_base_dir=runtime_base_dir,
            project_id=pid,
            task_id=tid,
            raw_config=config_payload,
            session_store=session_store,
        )
    except ValueError as e:
        return 422, {"error": str(e)}
    summary = build_task_assistant_summary(
        runtime_base_dir=runtime_base_dir,
        project_id=pid,
        task_id=tid,
        session_store=session_store,
        heartbeat_runtime=heartbeat_runtime,
    )
    return 200, {
        "ok": True,
        "project_id": pid,
        "task_id": tid,
        "task_assistant": summary,
        "config_path": str(config_path),
    }


def delete_task_assistant_response(
    *,
    runtime_base_dir: Path,
    project_id: str,
    task_id: str,
    session_store: Any,
    heartbeat_runtime: Any,
) -> tuple[int, dict[str, Any]]:
    pid = str(project_id or "").strip()
    tid = str(task_id or "").strip()
    if not pid:
        return 400, {"error": "missing project_id"}
    if not tid:
        return 400, {"error": "missing task_id"}
    removed, config_path = delete_task_assistant_config(
        runtime_base_dir=runtime_base_dir,
        project_id=pid,
        task_id=tid,
        session_store=session_store,
    )
    if not removed:
        return 404, {"error": "task assistant config not found"}
    return 200, {
        "ok": True,
        "project_id": pid,
        "task_id": tid,
        "removed": True,
        "task_assistant": build_task_assistant_summary(
            runtime_base_dir=runtime_base_dir,
            project_id=pid,
            task_id=tid,
            session_store=session_store,
            heartbeat_runtime=heartbeat_runtime,
        ),
        "config_path": str(config_path),
    }


def run_task_assistant_now_response(
    *,
    runtime_base_dir: Path,
    project_id: str,
    task_id: str,
    session_store: Any,
    heartbeat_runtime: Any,
) -> tuple[int, dict[str, Any]]:
    pid = str(project_id or "").strip()
    tid = str(task_id or "").strip()
    if not pid:
        return 400, {"error": "missing project_id"}
    if not tid:
        return 400, {"error": "missing task_id"}
    if heartbeat_runtime is None:
        return 503, {"error": "heartbeat task runtime unavailable"}
    summary = build_task_assistant_summary(
        runtime_base_dir=runtime_base_dir,
        project_id=pid,
        task_id=tid,
        session_store=session_store,
        heartbeat_runtime=heartbeat_runtime,
    )
    if not bool(summary.get("configured")):
        return 404, {"error": "task assistant config not found"}
    if str(summary.get("state") or "") in {"paused", "disabled"}:
        return 422, {"error": "task assistant not enabled"}
    if str(summary.get("state") or "") == "blocked":
        return 422, {"error": "task assistant blocked"}
    target_session_id = str(summary.get("target_session_id") or "").strip()
    heartbeat_task_id = str(((summary.get("compiled") or {}).get("heartbeat_task_id")) or "").strip()
    try:
        record = heartbeat_runtime.run_session_task_now(pid, target_session_id, heartbeat_task_id)
    except ValueError as e:
        return 422, {"error": str(e)}
    if not isinstance(record, dict):
        return 404, {"error": "compiled heartbeat task not found"}
    item = heartbeat_runtime.get_session_task(pid, target_session_id, heartbeat_task_id) or {}
    return 200, {
        "ok": True,
        "project_id": pid,
        "task_id": tid,
        "record": record,
        "item": item,
        "task_assistant": build_task_assistant_summary(
            runtime_base_dir=runtime_base_dir,
            project_id=pid,
            task_id=tid,
            session_store=session_store,
            heartbeat_runtime=heartbeat_runtime,
        ),
    }
