# -*- coding: utf-8 -*-
"""
Heartbeat helper functions.

Re-exports heartbeat-related functions from scheduler_helpers for cleaner imports.
These functions are also available in server.py for backward compatibility.
"""
from __future__ import annotations

from typing import Any, Optional

# Constants are safe to import directly (no function calls during import)
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
_HEARTBEAT_TASK_HISTORY_LIMIT = 50
_DEFAULT_HEARTBEAT_TASK_ID = "default"


def _get_scheduler_helpers():
    """Lazy import to avoid circular imports."""
    from task_dashboard.runtime import scheduler_helpers
    return scheduler_helpers


def _load_project_heartbeat_config(project_id: str) -> dict[str, Any]:
    """Load heartbeat configuration for a project."""
    return _get_scheduler_helpers()._load_project_heartbeat_config(project_id)


def _normalize_heartbeat_task(
    item: Any,
    *,
    index: int = 0,
    defaults: Optional[dict[str, Any]] = None,
    id_required: bool = False,
) -> Optional[dict[str, Any]]:
    """Normalize a single heartbeat task configuration."""
    return _get_scheduler_helpers()._normalize_heartbeat_task(
        item,
        index=index,
        defaults=defaults,
        id_required=id_required,
    )


def _heartbeat_tasks_for_write(raw_tasks: Any) -> list[dict[str, Any]]:
    """Prepare heartbeat tasks for write operations."""
    return _get_scheduler_helpers()._heartbeat_tasks_for_write(raw_tasks)


def _build_heartbeat_patch_with_tasks(
    *,
    cfg: dict[str, Any],
    tasks: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build a heartbeat patch payload with tasks."""
    return _get_scheduler_helpers()._build_heartbeat_patch_with_tasks(cfg=cfg, tasks=tasks)


def _normalize_heartbeat_tasks(
    raw: Any,
    *,
    defaults: Optional[dict[str, Any]] = None,
) -> list[dict[str, Any]]:
    """Normalize a list of heartbeat task configurations."""
    return _get_scheduler_helpers()._normalize_heartbeat_tasks(raw, defaults=defaults)


def _normalize_heartbeat_task_id(raw: Any, *, default: str = "") -> str:
    """Normalize a heartbeat task ID."""
    return _get_scheduler_helpers()._normalize_heartbeat_task_id(raw, default=default)


def _normalize_heartbeat_weekdays(raw: Any) -> list[int]:
    """Normalize heartbeat weekdays configuration."""
    return _get_scheduler_helpers()._normalize_heartbeat_weekdays(raw)


def _normalize_heartbeat_context_scope(raw: Any) -> dict[str, Any]:
    """Normalize heartbeat context scope configuration."""
    return _get_scheduler_helpers()._normalize_heartbeat_context_scope(raw)


__all__ = [
    # Primary functions
    "_load_project_heartbeat_config",
    "_normalize_heartbeat_task",
    "_heartbeat_tasks_for_write",
    "_build_heartbeat_patch_with_tasks",
    # Additional helper functions
    "_normalize_heartbeat_tasks",
    "_normalize_heartbeat_task_id",
    "_normalize_heartbeat_weekdays",
    "_normalize_heartbeat_context_scope",
    # Constants
    "_HEARTBEAT_TASK_SCHEDULE_TYPES",
    "_HEARTBEAT_TASK_BUSY_POLICIES",
    "_HEARTBEAT_TASK_PRESETS",
    "_HEARTBEAT_TASK_HISTORY_LIMIT",
    "_DEFAULT_HEARTBEAT_TASK_ID",
]
