# -*- coding: utf-8 -*-

from __future__ import annotations

from typing import Any, Callable, Optional
from urllib.parse import parse_qs

from task_dashboard.runtime.execution_profiles import (
    list_execution_profiles,
    normalize_execution_profile,
    resolve_execution_profile_permissions,
)


def _normalize_execution_profile(value: Any) -> str:
    return normalize_execution_profile(value, allow_empty=True)


def _build_execution_context_config(raw: Any) -> dict[str, Any]:
    cfg = raw if isinstance(raw, dict) else {}
    profile = _normalize_execution_profile(cfg.get("profile")) or "sandboxed"
    permissions = resolve_execution_profile_permissions(profile)
    return {
        "profile": profile,
        "environment": str(cfg.get("environment") or ""),
        "worktree_root": str(cfg.get("worktree_root") or ""),
        "workdir": str(cfg.get("workdir") or ""),
        "branch": str(cfg.get("branch") or ""),
        "runtime_root": str(cfg.get("runtime_root") or ""),
        "sessions_root": str(cfg.get("sessions_root") or ""),
        "runs_root": str(cfg.get("runs_root") or ""),
        "server_port": str(cfg.get("server_port") or ""),
        "health_source": str(cfg.get("health_source") or ""),
        "permissions": permissions,
        "available_profiles": list_execution_profiles(),
        "configured": bool(cfg),
        "context_source": "project" if bool(cfg) else "server_default",
    }


def build_project_contract_update_response(
    *,
    project_id: str,
    config_path: Any,
    status: dict[str, Any],
    cfg_project: dict[str, Any],
    auto_dispatch_cfg: dict[str, Any],
    auto_inspection_cfg: dict[str, Any],
    heartbeat_cfg: dict[str, Any],
    execution_context_cfg: dict[str, Any],
    heartbeat_runtime: Any,
    normalize_inspection_targets: Callable[..., list[dict[str, Any]] | list[str]],
    normalize_auto_inspections: Callable[..., list[dict[str, Any]]],
    normalize_auto_inspection_tasks: Callable[..., list[dict[str, Any]]],
    normalize_heartbeat_tasks: Callable[[Any], list[dict[str, Any]]],
    default_inspection_targets: list[str],
) -> dict[str, Any]:
    heartbeat_status = (
        heartbeat_runtime.sync_project(project_id)
        if heartbeat_runtime is not None
        else {
            "project_id": project_id,
            "enabled": bool(heartbeat_cfg.get("enabled")),
            "scan_interval_seconds": int(heartbeat_cfg.get("scan_interval_seconds") or 30),
            "items": normalize_heartbeat_tasks(heartbeat_cfg.get("tasks")),
            "count": len(normalize_heartbeat_tasks(heartbeat_cfg.get("tasks"))),
            "errors": list(heartbeat_cfg.get("errors") or []),
            "ready": bool(heartbeat_cfg.get("ready")),
        }
    )
    inspection_targets = normalize_inspection_targets(
        auto_inspection_cfg.get("inspection_targets"),
        default=default_inspection_targets if bool(auto_inspection_cfg.get("enabled")) else [],
    )
    return {
        "ok": True,
        "project_id": project_id,
        "config_path": str(config_path),
        "project": {
            "scheduler": cfg_project.get("scheduler") if isinstance(cfg_project, dict) else {},
            "reminder": cfg_project.get("reminder") if isinstance(cfg_project, dict) else {},
            "auto_dispatch": {
                "enabled": bool(auto_dispatch_cfg.get("enabled", False)),
            },
            "auto_inspection": {
                "enabled": bool(auto_inspection_cfg.get("enabled")),
                "channel_name": str(auto_inspection_cfg.get("channel_name") or ""),
                "session_id": str(auto_inspection_cfg.get("session_id") or ""),
                "interval_minutes": auto_inspection_cfg.get("interval_minutes"),
                "prompt_template": str(auto_inspection_cfg.get("prompt_template") or ""),
                "inspection_targets": inspection_targets,
                "auto_inspections": normalize_auto_inspections(
                    auto_inspection_cfg.get("auto_inspections"),
                    fallback_targets=inspection_targets,
                ),
                "inspection_tasks": normalize_auto_inspection_tasks(
                    auto_inspection_cfg.get("inspection_tasks"),
                    has_explicit_field=True,
                ),
                "active_inspection_task_id": str(auto_inspection_cfg.get("active_inspection_task_id") or ""),
                "ready": bool(auto_inspection_cfg.get("ready")),
                "errors": list(auto_inspection_cfg.get("errors") or []),
            },
            "heartbeat": heartbeat_status,
            "execution_context": {
                "profile": str(execution_context_cfg.get("profile") or "sandboxed"),
                "environment": str(execution_context_cfg.get("environment") or ""),
                "worktree_root": str(execution_context_cfg.get("worktree_root") or ""),
                "workdir": str(execution_context_cfg.get("workdir") or ""),
                "branch": str(execution_context_cfg.get("branch") or ""),
                "runtime_root": str(execution_context_cfg.get("runtime_root") or ""),
                "sessions_root": str(execution_context_cfg.get("sessions_root") or ""),
                "runs_root": str(execution_context_cfg.get("runs_root") or ""),
                "server_port": str(execution_context_cfg.get("server_port") or ""),
                "health_source": str(execution_context_cfg.get("health_source") or ""),
                "permissions": dict(execution_context_cfg.get("permissions") or {}),
                "available_profiles": list(execution_context_cfg.get("available_profiles") or []),
                "configured": bool(execution_context_cfg.get("configured")),
                "context_source": str(execution_context_cfg.get("context_source") or ""),
            },
            "status": status or {},
        },
    }


def get_project_config_response(
    *,
    project_id: str,
    store: Any,
    find_project_cfg: Callable[[str], Any],
    load_project_scheduler_contract_config: Callable[[str], dict[str, Any]],
    load_project_auto_dispatch_config: Callable[[str], dict[str, Any]],
    load_project_auto_inspection_config: Callable[[str], dict[str, Any]],
    load_project_heartbeat_config: Callable[[str], dict[str, Any]],
    build_project_scheduler_status: Callable[[Any, str], dict[str, Any]],
    ensure_auto_scheduler_status_shape: Callable[[Any], dict[str, Any]],
    project_scheduler_runtime: Any,
    heartbeat_runtime: Any,
    normalize_inspection_targets: Callable[..., list[dict[str, Any]] | list[str]],
    normalize_auto_inspections: Callable[..., list[dict[str, Any]]],
    normalize_auto_inspection_tasks: Callable[..., list[dict[str, Any]]],
    normalize_heartbeat_tasks: Callable[[Any], list[dict[str, Any]]],
    default_inspection_targets: list[str],
    config_path_getter: Callable[[], Any],
) -> tuple[int, dict[str, Any]]:
    pid = str(project_id or "").strip()
    if not pid:
        return 400, {"error": "missing project_id"}
    project_cfg = find_project_cfg(pid) or {}
    if not project_cfg:
        return 404, {"error": "project not found"}
    status = (
        project_scheduler_runtime.get_status(pid)
        if project_scheduler_runtime is not None
        else build_project_scheduler_status(store, pid)
    )
    status = ensure_auto_scheduler_status_shape(status)
    cfg_project = load_project_scheduler_contract_config(pid)
    auto_dispatch_cfg = load_project_auto_dispatch_config(pid)
    auto_inspection_cfg = load_project_auto_inspection_config(pid)
    heartbeat_cfg = load_project_heartbeat_config(pid)
    execution_context_cfg = _build_execution_context_config(project_cfg.get("execution_context"))
    payload = build_project_contract_update_response(
        project_id=pid,
        config_path=config_path_getter(),
        status=status,
        cfg_project=cfg_project,
        auto_dispatch_cfg=auto_dispatch_cfg,
        auto_inspection_cfg=auto_inspection_cfg,
        heartbeat_cfg=heartbeat_cfg,
        execution_context_cfg=execution_context_cfg,
        heartbeat_runtime=heartbeat_runtime,
        normalize_inspection_targets=normalize_inspection_targets,
        normalize_auto_inspections=normalize_auto_inspections,
        normalize_auto_inspection_tasks=normalize_auto_inspection_tasks,
        normalize_heartbeat_tasks=normalize_heartbeat_tasks,
        default_inspection_targets=default_inspection_targets,
    )
    return 200, payload


def get_project_auto_scheduler_status_response(
    *,
    project_id: str,
    store: Any,
    find_project_cfg: Callable[[str], Any],
    project_scheduler_runtime: Any,
    build_project_scheduler_status: Callable[[Any, str], dict[str, Any]],
    ensure_auto_scheduler_status_shape: Callable[[Any], dict[str, Any]],
    attach_auto_inspection_candidate_preview: Callable[[Any, dict[str, Any]], dict[str, Any]],
) -> tuple[int, dict[str, Any]]:
    pid = str(project_id or "").strip()
    if not pid:
        return 400, {"error": "missing project_id"}
    if not find_project_cfg(pid):
        return 404, {"error": "project not found"}
    status = (
        project_scheduler_runtime.get_status(pid)
        if project_scheduler_runtime is not None
        else build_project_scheduler_status(store, pid)
    )
    status = attach_auto_inspection_candidate_preview(
        store,
        ensure_auto_scheduler_status_shape(status),
    )
    if not status:
        return 404, {"error": "project not found"}
    return 200, {"status": status}


def list_project_auto_inspection_tasks_response(
    *,
    project_id: str,
    find_project_cfg: Callable[[str], Any],
    load_project_auto_inspection_config: Callable[[str], dict[str, Any]],
    normalize_auto_inspection_tasks: Callable[..., list[dict[str, Any]]],
) -> tuple[int, dict[str, Any]]:
    pid = str(project_id or "").strip()
    if not pid:
        return 400, {"error": "missing project_id"}
    if not find_project_cfg(pid):
        return 404, {"error": "project not found"}
    cfg = load_project_auto_inspection_config(pid)
    items = normalize_auto_inspection_tasks(
        cfg.get("inspection_tasks"),
        has_explicit_field=True,
    )
    return 200, {
        "project_id": pid,
        "items": items,
        "count": len(items),
        "active_inspection_task_id": str(cfg.get("active_inspection_task_id") or ""),
        "enabled": bool(cfg.get("enabled")),
    }


def list_project_inspection_records_response(
    *,
    project_id: str,
    query_string: str,
    store: Any,
    find_project_cfg: Callable[[str], Any],
    normalize_inspection_task_id: Callable[..., str],
    safe_text: Callable[[Any, int], str],
    auto_inspection_record_limit: int,
    project_scheduler_runtime: Any,
    build_project_scheduler_status: Callable[[Any, str], dict[str, Any]],
    ensure_auto_scheduler_status_shape: Callable[[Any], dict[str, Any]],
    normalize_inspection_records: Callable[..., list[dict[str, Any]]],
) -> tuple[int, dict[str, Any]]:
    pid = str(project_id or "").strip()
    if not pid:
        return 400, {"error": "missing project_id"}
    if not find_project_cfg(pid):
        return 404, {"error": "project not found"}
    qs = parse_qs(query_string or "")
    inspection_task_id = normalize_inspection_task_id(
        (qs.get("inspection_task_id") or qs.get("inspectionTaskId") or [""])[0],
    )
    limit_s = safe_text((qs.get("limit") or ["50"])[0], 20).strip()
    try:
        limit = max(1, min(auto_inspection_record_limit, int(limit_s)))
    except Exception:
        limit = auto_inspection_record_limit
    status = (
        project_scheduler_runtime.get_status(pid)
        if project_scheduler_runtime is not None
        else build_project_scheduler_status(store, pid)
    )
    status = ensure_auto_scheduler_status_shape(status)
    records = normalize_inspection_records(status.get("inspection_records"))
    if inspection_task_id:
        records = [
            row
            for row in records
            if normalize_inspection_task_id(row.get("inspection_task_id")) == inspection_task_id
        ]
    items = records[:limit]
    return 200, {
        "project_id": pid,
        "inspection_task_id": inspection_task_id or "",
        "items": items,
        "count": len(items),
    }


def create_or_update_project_auto_inspection_task_response(
    *,
    project_id: str,
    body: dict[str, Any],
    find_project_cfg: Callable[[str], Any],
    load_project_auto_inspection_config: Callable[[str], dict[str, Any]],
    build_default_auto_inspection_task: Callable[..., dict[str, Any]],
    normalize_inspection_targets: Callable[..., list[dict[str, Any]] | list[str]],
    normalize_auto_inspections: Callable[..., list[dict[str, Any]]],
    normalize_auto_inspection_task: Callable[..., Optional[dict[str, Any]]],
    auto_inspection_tasks_for_write: Callable[[dict[str, Any], Any], list[dict[str, Any]]],
    normalize_inspection_task_id: Callable[..., str],
    build_auto_inspection_patch_with_tasks: Callable[..., dict[str, Any]],
    coerce_bool: Callable[[Any, bool], bool],
    set_project_scheduler_contract_in_config: Callable[..., Any],
    project_scheduler_runtime: Any,
    store: Any,
    build_project_scheduler_status: Callable[[Any, str], dict[str, Any]],
    ensure_auto_scheduler_status_shape: Callable[[Any], dict[str, Any]],
) -> tuple[int, dict[str, Any]]:
    pid = str(project_id or "").strip()
    if not pid:
        return 400, {"error": "missing project_id"}
    if not find_project_cfg(pid):
        return 404, {"error": "project not found"}
    task_payload = body.get("inspection_task") if isinstance(body.get("inspection_task"), dict) else body
    if not isinstance(task_payload, dict):
        return 400, {"error": "missing inspection_task"}
    cfg = load_project_auto_inspection_config(pid)
    inspection_targets = normalize_inspection_targets(cfg.get("inspection_targets"), default=[])
    defaults = build_default_auto_inspection_task(
        enabled=bool(cfg.get("enabled")),
        channel_name=str(cfg.get("channel_name") or ""),
        session_id=str(cfg.get("session_id") or ""),
        interval_minutes=(int(cfg.get("interval_minutes")) if cfg.get("interval_minutes") is not None else None),
        prompt_template=str(cfg.get("prompt_template") or ""),
        inspection_targets=inspection_targets,
        auto_inspections=normalize_auto_inspections(
            cfg.get("auto_inspections"),
            fallback_targets=inspection_targets,
        ),
    )
    new_task = normalize_auto_inspection_task(
        task_payload,
        index=max(0, len(list(cfg.get("inspection_tasks") or []))),
        defaults=defaults,
        id_required=True,
    )
    if not isinstance(new_task, dict):
        return 400, {"error": "invalid inspection_task"}
    task_id = str(new_task.get("inspection_task_id") or "").strip()
    if not task_id:
        return 400, {"error": "invalid inspection_task.inspection_task_id"}
    current_tasks = auto_inspection_tasks_for_write(cfg, list(cfg.get("inspection_tasks") or []))
    replaced = False
    merged_tasks: list[dict[str, Any]] = []
    for row in current_tasks:
        if str(row.get("inspection_task_id") or "").strip() == task_id:
            merged_tasks.append(new_task)
            replaced = True
        else:
            merged_tasks.append(row)
    if not replaced:
        merged_tasks.append(new_task)
    active_task_id = normalize_inspection_task_id(
        body.get("active_inspection_task_id")
        if "active_inspection_task_id" in body
        else body.get("activeInspectionTaskId"),
    )
    if coerce_bool(body.get("set_active"), False):
        active_task_id = task_id
    patch = build_auto_inspection_patch_with_tasks(
        cfg=cfg,
        tasks=merged_tasks,
        active_task_id=active_task_id,
    )
    if "enabled" in body:
        patch["enabled"] = coerce_bool(body.get("enabled"), bool(cfg.get("enabled")))
    try:
        config_path = set_project_scheduler_contract_in_config(
            pid,
            auto_inspection_patch=patch,
        )
    except Exception as e:
        return 400, {"error": str(e)}
    status = (
        project_scheduler_runtime.sync_project(pid)
        if project_scheduler_runtime is not None
        else build_project_scheduler_status(store, pid)
    )
    status = ensure_auto_scheduler_status_shape(status)
    return 200, {
        "ok": True,
        "project_id": pid,
        "item": next(
            (
                row
                for row in list(status.get("inspection_tasks") or [])
                if str(row.get("inspection_task_id") or "").strip() == task_id
            ),
            new_task,
        ),
        "count": len(list(status.get("inspection_tasks") or [])),
        "active_inspection_task_id": str(status.get("active_inspection_task_id") or ""),
        "config_path": str(config_path),
        "status": status,
    }


def delete_project_auto_inspection_task_response(
    *,
    project_id: str,
    task_id: str,
    body: Any,
    find_project_cfg: Callable[[str], Any],
    load_project_auto_inspection_config: Callable[[str], dict[str, Any]],
    auto_inspection_tasks_for_write: Callable[[dict[str, Any], Any], list[dict[str, Any]]],
    normalize_inspection_task_id: Callable[..., str],
    build_auto_inspection_patch_with_tasks: Callable[..., dict[str, Any]],
    set_project_scheduler_contract_in_config: Callable[..., Any],
    project_scheduler_runtime: Any,
    store: Any,
    build_project_scheduler_status: Callable[[Any, str], dict[str, Any]],
    ensure_auto_scheduler_status_shape: Callable[[Any], dict[str, Any]],
) -> tuple[int, dict[str, Any]]:
    pid = str(project_id or "").strip()
    normalized_task_id = normalize_inspection_task_id(task_id, default="")
    if not pid:
        return 400, {"error": "missing project_id"}
    if not normalized_task_id:
        return 400, {"error": "missing inspection_task_id"}
    if not find_project_cfg(pid):
        return 404, {"error": "project not found"}
    cfg = load_project_auto_inspection_config(pid)
    current_tasks = auto_inspection_tasks_for_write(cfg, list(cfg.get("inspection_tasks") or []))
    merged_tasks = [
        row for row in current_tasks if str(row.get("inspection_task_id") or "").strip() != normalized_task_id
    ]
    if len(merged_tasks) == len(current_tasks):
        return 404, {"error": "inspection_task not found"}
    active_task_id = normalize_inspection_task_id(
        body.get("active_inspection_task_id")
        if isinstance(body, dict) and "active_inspection_task_id" in body
        else (body.get("activeInspectionTaskId") if isinstance(body, dict) else ""),
    )
    patch = build_auto_inspection_patch_with_tasks(
        cfg=cfg,
        tasks=merged_tasks,
        active_task_id=active_task_id,
    )
    try:
        config_path = set_project_scheduler_contract_in_config(
            pid,
            auto_inspection_patch=patch,
        )
    except Exception as e:
        return 400, {"error": str(e)}
    status = (
        project_scheduler_runtime.sync_project(pid)
        if project_scheduler_runtime is not None
        else build_project_scheduler_status(store, pid)
    )
    status = ensure_auto_scheduler_status_shape(status)
    return 200, {
        "ok": True,
        "project_id": pid,
        "removed_inspection_task_id": normalized_task_id,
        "count": len(list(status.get("inspection_tasks") or [])),
        "active_inspection_task_id": str(status.get("active_inspection_task_id") or ""),
        "config_path": str(config_path),
        "status": status,
    }


def set_project_auto_scheduler_enabled_response(
    *,
    project_id: str,
    body: dict[str, Any],
    store: Any,
    find_project_cfg: Callable[[str], Any],
    coerce_bool: Callable[[Any, bool], bool],
    set_project_scheduler_enabled_in_config: Callable[[str, bool], Any],
    project_scheduler_runtime: Any,
    build_project_scheduler_status: Callable[[Any, str], dict[str, Any]],
    ensure_auto_scheduler_status_shape: Callable[[Any], dict[str, Any]],
    attach_auto_inspection_candidate_preview: Callable[[Any, dict[str, Any]], dict[str, Any]],
) -> tuple[int, dict[str, Any]]:
    pid = str(project_id or "").strip()
    if not pid:
        return 400, {"error": "missing project_id"}
    if not find_project_cfg(pid):
        return 404, {"error": "project not found"}
    if "enabled" not in body and "scheduler_enabled" not in body:
        return 400, {"error": "missing enabled"}
    enabled = coerce_bool(
        body.get("enabled") if "enabled" in body else body.get("scheduler_enabled"),
        False,
    )
    try:
        config_path = set_project_scheduler_enabled_in_config(pid, enabled)
    except Exception as e:
        return 400, {"error": str(e)}
    status = (
        project_scheduler_runtime.sync_project(pid)
        if project_scheduler_runtime is not None
        else build_project_scheduler_status(store, pid)
    )
    status = attach_auto_inspection_candidate_preview(
        store,
        ensure_auto_scheduler_status_shape(status),
    )
    return 200, {
        "ok": True,
        "project_id": pid,
        "status": status,
        "config_path": str(config_path),
    }


def update_project_config_response(
    *,
    project_id: str,
    body: dict[str, Any],
    find_project_cfg: Callable[[str], Any],
    safe_text: Callable[[Any, int], str],
    coerce_bool: Callable[[Any, bool], bool],
    looks_like_uuid: Callable[[str], bool],
    load_project_scheduler_contract_config: Callable[[str], dict[str, Any]],
    load_project_auto_dispatch_config: Callable[[str], dict[str, Any]],
    load_project_auto_inspection_config: Callable[[str], dict[str, Any]],
    load_project_heartbeat_config: Callable[[str], dict[str, Any]],
    build_default_auto_inspection_task: Callable[..., dict[str, Any]],
    normalize_inspection_targets: Callable[..., list[dict[str, Any]] | list[str]],
    normalize_auto_inspections: Callable[..., list[dict[str, Any]]],
    normalize_auto_inspection_task: Callable[..., Optional[dict[str, Any]]],
    normalize_auto_inspection_tasks: Callable[..., list[dict[str, Any]]],
    normalize_auto_inspection_object: Callable[..., Optional[dict[str, Any]]],
    auto_inspection_targets_from_objects: Callable[[list[dict[str, Any]]], list[str]],
    inspection_target_tokens: Callable[[Any], list[str]],
    inspection_target_set: set[str],
    build_auto_inspection_patch_with_tasks: Callable[..., dict[str, Any]],
    normalize_inspection_task_id: Callable[..., str],
    heartbeat_tasks_for_write: Callable[[Any], list[dict[str, Any]]],
    normalize_heartbeat_task: Callable[..., Optional[dict[str, Any]]],
    normalize_heartbeat_tasks: Callable[[Any], list[dict[str, Any]]],
    set_project_scheduler_contract_in_config: Callable[..., Any],
    build_project_scheduler_status: Callable[[Any, str], dict[str, Any]],
    ensure_auto_scheduler_status_shape: Callable[[Any], dict[str, Any]],
    project_scheduler_runtime: Any,
    heartbeat_runtime: Any,
    store: Any,
    default_inspection_targets: list[str],
) -> tuple[int, dict[str, Any]]:
    pid = str(project_id or "").strip()
    if not pid:
        return 400, {"error": "missing project_id"}
    if not find_project_cfg(pid):
        return 404, {"error": "project not found"}

    scheduler_obj = body.get("scheduler") if isinstance(body.get("scheduler"), dict) else {}
    reminder_obj = body.get("reminder") if isinstance(body.get("reminder"), dict) else {}
    auto_dispatch_obj = body.get("auto_dispatch") if isinstance(body.get("auto_dispatch"), dict) else {}
    auto_inspection_obj = body.get("auto_inspection") if isinstance(body.get("auto_inspection"), dict) else {}
    heartbeat_obj = body.get("heartbeat") if isinstance(body.get("heartbeat"), dict) else {}
    execution_context_obj = body.get("execution_context") if isinstance(body.get("execution_context"), dict) else {}
    task_auto_trigger_obj = body.get("task_auto_trigger") if isinstance(body.get("task_auto_trigger"), dict) else {}
    if not scheduler_obj:
        scheduler_obj = body if any(
            key in body
            for key in ("enabled", "scheduler_enabled", "scan_interval_seconds", "max_concurrency_override", "retry_on_boot")
        ) else {}
    if not reminder_obj:
        reminder_obj = body if any(
            key in body
            for key in (
                "reminder_enabled",
                "interval_minutes",
                "cron",
                "in_progress_stale_after_minutes",
                "escalate_after_minutes",
                "summary_window_minutes",
            )
        ) else {}
    if not auto_dispatch_obj:
        auto_dispatch_obj = body if "auto_dispatch_enabled" in body else {}
    if not auto_dispatch_obj and task_auto_trigger_obj:
        auto_dispatch_obj = task_auto_trigger_obj
    if not auto_inspection_obj:
        auto_inspection_obj = body if any(
            key in body
            for key in (
                "auto_inspection_enabled",
                "auto_inspection_channel_name",
                "auto_inspection_session_id",
                "auto_inspection_interval_minutes",
                "auto_inspection_prompt_template",
                "auto_inspection_targets",
                "auto_inspections",
            )
        ) else {}

    scheduler_patch: dict[str, Any] = {}
    reminder_patch: dict[str, Any] = {}
    auto_dispatch_patch: dict[str, Any] = {}
    auto_inspection_patch: dict[str, Any] = {}
    heartbeat_patch: dict[str, Any] = {}
    execution_context_patch: dict[str, Any] = {}

    if isinstance(scheduler_obj, dict):
        if "enabled" in scheduler_obj or "scheduler_enabled" in scheduler_obj:
            scheduler_patch["enabled"] = coerce_bool(
                scheduler_obj.get("enabled") if "enabled" in scheduler_obj else scheduler_obj.get("scheduler_enabled"),
                False,
            )
        if "scan_interval_seconds" in scheduler_obj:
            try:
                interval_s = int(scheduler_obj.get("scan_interval_seconds"))
            except Exception:
                return 400, {"error": "invalid scheduler.scan_interval_seconds"}
            if interval_s < 60:
                return 400, {"error": "scheduler.scan_interval_seconds must be >= 60"}
            scheduler_patch["scan_interval_seconds"] = interval_s
        if "max_concurrency_override" in scheduler_obj:
            raw_override = scheduler_obj.get("max_concurrency_override")
            if raw_override in (None, "", 0, "0", False):
                scheduler_patch["max_concurrency_override"] = None
            else:
                try:
                    value = int(raw_override)
                except Exception:
                    return 400, {"error": "invalid scheduler.max_concurrency_override"}
                if value < 1 or value > 32:
                    return 400, {"error": "scheduler.max_concurrency_override out of range: 1..32"}
                scheduler_patch["max_concurrency_override"] = value
        if "retry_on_boot" in scheduler_obj:
            scheduler_patch["retry_on_boot"] = coerce_bool(scheduler_obj.get("retry_on_boot"), True)

    if isinstance(reminder_obj, dict):
        if "enabled" in reminder_obj or "reminder_enabled" in reminder_obj:
            reminder_patch["enabled"] = coerce_bool(
                reminder_obj.get("enabled") if "enabled" in reminder_obj else reminder_obj.get("reminder_enabled"),
                False,
            )
        if "interval_minutes" in reminder_obj:
            raw_interval = reminder_obj.get("interval_minutes")
            if raw_interval in (None, "", 0, "0", False):
                reminder_patch["interval_minutes"] = None
            else:
                try:
                    interval_m = int(raw_interval)
                except Exception:
                    return 400, {"error": "invalid reminder.interval_minutes"}
                if interval_m < 5:
                    return 400, {"error": "reminder.interval_minutes must be >= 5"}
                reminder_patch["interval_minutes"] = interval_m
        if "cron" in reminder_obj:
            cron = safe_text(reminder_obj.get("cron"), 200).strip()
            reminder_patch["cron"] = cron or None
        if "in_progress_stale_after_minutes" in reminder_obj:
            try:
                stale_m = int(reminder_obj.get("in_progress_stale_after_minutes"))
            except Exception:
                return 400, {"error": "invalid reminder.in_progress_stale_after_minutes"}
            if stale_m <= 0:
                return 400, {"error": "reminder.in_progress_stale_after_minutes must be > 0"}
            reminder_patch["in_progress_stale_after_minutes"] = stale_m
        if "escalate_after_minutes" in reminder_obj:
            try:
                escalate_m = int(reminder_obj.get("escalate_after_minutes"))
            except Exception:
                return 400, {"error": "invalid reminder.escalate_after_minutes"}
            if escalate_m <= 0:
                return 400, {"error": "reminder.escalate_after_minutes must be > 0"}
            reminder_patch["escalate_after_minutes"] = escalate_m
        if "summary_window_minutes" in reminder_obj:
            try:
                summary_window_m = int(reminder_obj.get("summary_window_minutes"))
            except Exception:
                return 400, {"error": "invalid reminder.summary_window_minutes"}
            if summary_window_m < 1:
                return 400, {"error": "reminder.summary_window_minutes must be >= 1"}
            reminder_patch["summary_window_minutes"] = summary_window_m

    if isinstance(auto_dispatch_obj, dict):
        if "enabled" in auto_dispatch_obj or "auto_dispatch_enabled" in auto_dispatch_obj:
            auto_dispatch_patch["enabled"] = coerce_bool(
                auto_dispatch_obj.get("enabled")
                if "enabled" in auto_dispatch_obj
                else auto_dispatch_obj.get("auto_dispatch_enabled"),
                True,
            )

    if isinstance(auto_inspection_obj, dict):
        if "enabled" in auto_inspection_obj or "auto_inspection_enabled" in auto_inspection_obj:
            auto_inspection_patch["enabled"] = coerce_bool(
                auto_inspection_obj.get("enabled")
                if "enabled" in auto_inspection_obj
                else auto_inspection_obj.get("auto_inspection_enabled"),
                False,
            )
        if any(key in auto_inspection_obj for key in ("channel_name", "channelName", "auto_inspection_channel_name")):
            channel_name = safe_text(
                auto_inspection_obj.get("channel_name")
                if "channel_name" in auto_inspection_obj
                else (
                    auto_inspection_obj.get("channelName")
                    if "channelName" in auto_inspection_obj
                    else auto_inspection_obj.get("auto_inspection_channel_name")
                ),
                200,
            ).strip()
            auto_inspection_patch["channel_name"] = channel_name or None
        if any(key in auto_inspection_obj for key in ("session_id", "sessionId", "auto_inspection_session_id")):
            inspection_session_id = safe_text(
                auto_inspection_obj.get("session_id")
                if "session_id" in auto_inspection_obj
                else (
                    auto_inspection_obj.get("sessionId")
                    if "sessionId" in auto_inspection_obj
                    else auto_inspection_obj.get("auto_inspection_session_id")
                ),
                120,
            ).strip()
            if inspection_session_id and not looks_like_uuid(inspection_session_id):
                return 400, {"error": "invalid auto_inspection.session_id"}
            auto_inspection_patch["session_id"] = inspection_session_id or None
        if "interval_minutes" in auto_inspection_obj or "auto_inspection_interval_minutes" in auto_inspection_obj:
            raw_interval = (
                auto_inspection_obj.get("interval_minutes")
                if "interval_minutes" in auto_inspection_obj
                else auto_inspection_obj.get("auto_inspection_interval_minutes")
            )
            if raw_interval in (None, "", 0, "0", False):
                auto_inspection_patch["interval_minutes"] = None
            else:
                try:
                    interval_m = int(raw_interval)
                except Exception:
                    return 400, {"error": "invalid auto_inspection.interval_minutes"}
                if interval_m < 5:
                    return 400, {"error": "auto_inspection.interval_minutes must be >= 5"}
                auto_inspection_patch["interval_minutes"] = interval_m
        if any(key in auto_inspection_obj for key in ("prompt_template", "promptTemplate", "auto_inspection_prompt_template")):
            prompt_template = safe_text(
                auto_inspection_obj.get("prompt_template")
                if "prompt_template" in auto_inspection_obj
                else (
                    auto_inspection_obj.get("promptTemplate")
                    if "promptTemplate" in auto_inspection_obj
                    else auto_inspection_obj.get("auto_inspection_prompt_template")
                ),
                20_000,
            ).strip()
            auto_inspection_patch["prompt_template"] = prompt_template or None
        if any(key in auto_inspection_obj for key in ("inspection_tasks", "inspectionTasks")):
            raw_tasks = (
                auto_inspection_obj.get("inspection_tasks")
                if "inspection_tasks" in auto_inspection_obj
                else auto_inspection_obj.get("inspectionTasks")
            )
            if raw_tasks in (None, ""):
                auto_inspection_patch["inspection_tasks"] = []
                auto_inspection_patch["active_inspection_task_id"] = None
                auto_inspection_patch["inspection_targets"] = []
                auto_inspection_patch["auto_inspections"] = []
            elif not isinstance(raw_tasks, list):
                return 400, {"error": "invalid auto_inspection.inspection_tasks"}
            else:
                existing_cfg = load_project_auto_inspection_config(pid)
                inspection_targets = normalize_inspection_targets(existing_cfg.get("inspection_targets"), default=[])
                defaults = build_default_auto_inspection_task(
                    enabled=bool(existing_cfg.get("enabled")),
                    channel_name=str(existing_cfg.get("channel_name") or ""),
                    session_id=str(existing_cfg.get("session_id") or ""),
                    interval_minutes=(
                        int(existing_cfg.get("interval_minutes")) if existing_cfg.get("interval_minutes") is not None else None
                    ),
                    prompt_template=str(existing_cfg.get("prompt_template") or ""),
                    inspection_targets=inspection_targets,
                    auto_inspections=normalize_auto_inspections(
                        existing_cfg.get("auto_inspections"),
                        fallback_targets=inspection_targets,
                    ),
                )
                normalized_tasks: list[dict[str, Any]] = []
                invalid_items: list[dict[str, Any]] = []
                seen_ids: set[str] = set()
                for idx, item in enumerate(raw_tasks):
                    row = normalize_auto_inspection_task(
                        item,
                        index=idx,
                        defaults=defaults,
                        id_required=True,
                    )
                    if not row:
                        invalid_items.append({"index": idx, "reason": "invalid_item_or_missing_task_id"})
                        continue
                    task_id = str(row.get("inspection_task_id") or "").strip()
                    if task_id in seen_ids:
                        invalid_items.append({"index": idx, "reason": "duplicate_inspection_task_id"})
                        continue
                    seen_ids.add(task_id)
                    normalized_tasks.append(row)
                if invalid_items:
                    return 400, {"error": "invalid auto_inspection.inspection_tasks", "invalid": invalid_items}
                active_task_id = normalize_inspection_task_id(
                    auto_inspection_obj.get("active_inspection_task_id")
                    if "active_inspection_task_id" in auto_inspection_obj
                    else auto_inspection_obj.get("activeInspectionTaskId")
                )
                auto_inspection_patch.update(
                    build_auto_inspection_patch_with_tasks(
                        cfg=existing_cfg,
                        tasks=normalized_tasks,
                        active_task_id=active_task_id,
                    )
                )
        elif any(key in auto_inspection_obj for key in ("active_inspection_task_id", "activeInspectionTaskId")):
            active_task_id = normalize_inspection_task_id(
                auto_inspection_obj.get("active_inspection_task_id")
                if "active_inspection_task_id" in auto_inspection_obj
                else auto_inspection_obj.get("activeInspectionTaskId")
            )
            existing_cfg = load_project_auto_inspection_config(pid)
            auto_inspection_patch.update(
                build_auto_inspection_patch_with_tasks(
                    cfg=existing_cfg,
                    tasks=list(existing_cfg.get("inspection_tasks") or []),
                    active_task_id=active_task_id,
                )
            )
        if any(key in auto_inspection_obj for key in ("auto_inspections", "autoInspections")):
            raw_objects = (
                auto_inspection_obj.get("auto_inspections")
                if "auto_inspections" in auto_inspection_obj
                else auto_inspection_obj.get("autoInspections")
            )
            if raw_objects in (None, "") and "inspection_tasks" not in auto_inspection_patch:
                auto_inspection_patch["auto_inspections"] = []
                auto_inspection_patch["inspection_targets"] = []
            elif not isinstance(raw_objects, list):
                return 400, {"error": "invalid auto_inspection.auto_inspections"}
            elif "inspection_tasks" not in auto_inspection_patch:
                normalized_objects: list[dict[str, Any]] = []
                invalid_items: list[dict[str, Any]] = []
                seen_object_keys: set[str] = set()
                for idx, item in enumerate(raw_objects):
                    row = normalize_auto_inspection_object(item, source_default="auto_inspections")
                    if not row:
                        invalid_items.append({"index": idx, "reason": "invalid_item"})
                        continue
                    object_key = str(row.get("object_key") or "").strip()
                    if object_key in seen_object_keys:
                        invalid_items.append({"index": idx, "reason": "duplicate_object_key"})
                        continue
                    seen_object_keys.add(object_key)
                    normalized_objects.append(row)
                if invalid_items:
                    return 400, {"error": "invalid auto_inspection.auto_inspections", "invalid": invalid_items}
                auto_inspection_patch["auto_inspections"] = normalized_objects
                auto_inspection_patch["inspection_targets"] = auto_inspection_targets_from_objects(normalized_objects)
        if (
            any(key in auto_inspection_obj for key in ("inspection_targets", "inspectionTargets", "auto_inspection_targets"))
            and "auto_inspections" not in auto_inspection_patch
            and "inspection_tasks" not in auto_inspection_patch
        ):
            raw_targets = (
                auto_inspection_obj.get("inspection_targets")
                if "inspection_targets" in auto_inspection_obj
                else (
                    auto_inspection_obj.get("inspectionTargets")
                    if "inspectionTargets" in auto_inspection_obj
                    else auto_inspection_obj.get("auto_inspection_targets")
                )
            )
            target_tokens = inspection_target_tokens(raw_targets)
            invalid_targets = [item for item in target_tokens if item not in inspection_target_set]
            if invalid_targets:
                return 400, {"error": "invalid auto_inspection.inspection_targets", "invalid": invalid_targets}
            auto_inspection_patch["inspection_targets"] = normalize_inspection_targets(target_tokens, default=[])

    if isinstance(heartbeat_obj, dict):
        if "enabled" in heartbeat_obj:
            heartbeat_patch["enabled"] = coerce_bool(heartbeat_obj.get("enabled"), False)
        if "scan_interval_seconds" in heartbeat_obj:
            try:
                scan_interval_seconds = int(heartbeat_obj.get("scan_interval_seconds"))
            except Exception:
                return 400, {"error": "invalid heartbeat.scan_interval_seconds"}
            if scan_interval_seconds < 20:
                return 400, {"error": "heartbeat.scan_interval_seconds must be >= 20"}
            heartbeat_patch["scan_interval_seconds"] = scan_interval_seconds
        if any(key in heartbeat_obj for key in ("tasks", "heartbeat_tasks")):
            raw_tasks = heartbeat_obj.get("tasks") if "tasks" in heartbeat_obj else heartbeat_obj.get("heartbeat_tasks")
            if raw_tasks in (None, ""):
                heartbeat_patch["tasks"] = []
            elif not isinstance(raw_tasks, list):
                return 400, {"error": "invalid heartbeat.tasks"}
            else:
                normalized_tasks: list[dict[str, Any]] = []
                invalid_items: list[dict[str, Any]] = []
                seen_ids: set[str] = set()
                for idx, item in enumerate(raw_tasks):
                    row = normalize_heartbeat_task(item, index=idx, id_required=True)
                    if not row:
                        invalid_items.append({"index": idx, "reason": "invalid_item_or_missing_task_id"})
                        continue
                    task_id = str(row.get("heartbeat_task_id") or "").strip()
                    if task_id in seen_ids:
                        invalid_items.append({"index": idx, "reason": "duplicate_heartbeat_task_id"})
                        continue
                    seen_ids.add(task_id)
                    normalized_tasks.append(row)
                if invalid_items:
                    return 400, {"error": "invalid heartbeat.tasks", "invalid": invalid_items}
                heartbeat_patch["tasks"] = heartbeat_tasks_for_write(normalized_tasks)

    if isinstance(execution_context_obj, dict):
        if "profile" in execution_context_obj:
            raw_profile = safe_text(execution_context_obj.get("profile"), 40).strip().lower()
            if not raw_profile:
                execution_context_patch["profile"] = None
            else:
                normalized_profile = _normalize_execution_profile(raw_profile)
                if not normalized_profile:
                    return 400, {"error": "invalid execution_context.profile"}
                execution_context_patch["profile"] = normalized_profile
        if "environment" in execution_context_obj or "environmentName" in execution_context_obj:
            environment_value = safe_text(
                execution_context_obj.get("environment")
                if "environment" in execution_context_obj
                else execution_context_obj.get("environmentName"),
                80,
            ).strip()
            execution_context_patch["environment"] = environment_value or None
        if "worktree_root" in execution_context_obj or "worktreeRoot" in execution_context_obj:
            worktree_value = safe_text(
                execution_context_obj.get("worktree_root")
                if "worktree_root" in execution_context_obj
                else execution_context_obj.get("worktreeRoot"),
                4000,
            ).strip()
            execution_context_patch["worktree_root"] = worktree_value or None
        if "workdir" in execution_context_obj:
            workdir_value = safe_text(execution_context_obj.get("workdir"), 4000).strip()
            execution_context_patch["workdir"] = workdir_value or None
        if "branch" in execution_context_obj:
            branch_value = safe_text(execution_context_obj.get("branch"), 240).strip()
            execution_context_patch["branch"] = branch_value or None
        if "runtime_root" in execution_context_obj or "runtimeRoot" in execution_context_obj:
            runtime_root_value = safe_text(
                execution_context_obj.get("runtime_root")
                if "runtime_root" in execution_context_obj
                else execution_context_obj.get("runtimeRoot"),
                4000,
            ).strip()
            execution_context_patch["runtime_root"] = runtime_root_value or None
        if "sessions_root" in execution_context_obj or "sessionsRoot" in execution_context_obj:
            sessions_root_value = safe_text(
                execution_context_obj.get("sessions_root")
                if "sessions_root" in execution_context_obj
                else execution_context_obj.get("sessionsRoot"),
                4000,
            ).strip()
            execution_context_patch["sessions_root"] = sessions_root_value or None
        if "runs_root" in execution_context_obj or "runsRoot" in execution_context_obj:
            runs_root_value = safe_text(
                execution_context_obj.get("runs_root")
                if "runs_root" in execution_context_obj
                else execution_context_obj.get("runsRoot"),
                4000,
            ).strip()
            execution_context_patch["runs_root"] = runs_root_value or None
        if "server_port" in execution_context_obj or "serverPort" in execution_context_obj:
            server_port_value = safe_text(
                execution_context_obj.get("server_port")
                if "server_port" in execution_context_obj
                else execution_context_obj.get("serverPort"),
                80,
            ).strip()
            execution_context_patch["server_port"] = server_port_value or None
        if "health_source" in execution_context_obj or "healthSource" in execution_context_obj:
            health_source_value = safe_text(
                execution_context_obj.get("health_source")
                if "health_source" in execution_context_obj
                else execution_context_obj.get("healthSource"),
                4000,
            ).strip()
            execution_context_patch["health_source"] = health_source_value or None

    if isinstance(reminder_obj, dict):
        if "channel_name" in reminder_obj and "channel_name" not in auto_inspection_patch:
            alias_channel_name = safe_text(reminder_obj.get("channel_name"), 200).strip()
            auto_inspection_patch["channel_name"] = alias_channel_name or None
        elif "channelName" in reminder_obj and "channel_name" not in auto_inspection_patch:
            alias_channel_name = safe_text(reminder_obj.get("channelName"), 200).strip()
            auto_inspection_patch["channel_name"] = alias_channel_name or None

        if "session_id" in reminder_obj and "session_id" not in auto_inspection_patch:
            alias_session_id = safe_text(reminder_obj.get("session_id"), 120).strip()
            if alias_session_id and not looks_like_uuid(alias_session_id):
                return 400, {"error": "invalid reminder.session_id"}
            auto_inspection_patch["session_id"] = alias_session_id or None
        elif "sessionId" in reminder_obj and "session_id" not in auto_inspection_patch:
            alias_session_id = safe_text(reminder_obj.get("sessionId"), 120).strip()
            if alias_session_id and not looks_like_uuid(alias_session_id):
                return 400, {"error": "invalid reminder.sessionId"}
            auto_inspection_patch["session_id"] = alias_session_id or None

        if "prompt_template" in reminder_obj and "prompt_template" not in auto_inspection_patch:
            alias_prompt = safe_text(reminder_obj.get("prompt_template"), 20_000).strip()
            auto_inspection_patch["prompt_template"] = alias_prompt or None
        elif "prompt" in reminder_obj and "prompt_template" not in auto_inspection_patch:
            alias_prompt = safe_text(reminder_obj.get("prompt"), 20_000).strip()
            auto_inspection_patch["prompt_template"] = alias_prompt or None

    if (
        not scheduler_patch
        and not reminder_patch
        and not auto_dispatch_patch
        and not auto_inspection_patch
        and not heartbeat_patch
        and not execution_context_patch
    ):
        return 400, {"error": "no config fields to update"}

    try:
        config_path = set_project_scheduler_contract_in_config(
            pid,
            scheduler_patch=scheduler_patch,
            reminder_patch=reminder_patch,
            auto_dispatch_patch=auto_dispatch_patch,
            auto_inspection_patch=auto_inspection_patch,
            heartbeat_patch=heartbeat_patch,
            execution_context_patch=execution_context_patch,
        )
    except Exception as e:
        return 400, {"error": str(e)}

    status = (
        project_scheduler_runtime.sync_project(pid)
        if project_scheduler_runtime is not None
        else build_project_scheduler_status(store, pid)
    )
    status = ensure_auto_scheduler_status_shape(status)

    cfg_project = load_project_scheduler_contract_config(pid)
    auto_dispatch_cfg = load_project_auto_dispatch_config(pid)
    auto_inspection_cfg = load_project_auto_inspection_config(pid)
    heartbeat_cfg = load_project_heartbeat_config(pid)
    project_cfg = find_project_cfg(pid) or {}
    execution_context_cfg = _build_execution_context_config(
        project_cfg.get("execution_context") if isinstance(project_cfg, dict) else {}
    )
    payload = build_project_contract_update_response(
        project_id=pid,
        config_path=config_path,
        status=status,
        cfg_project=cfg_project,
        auto_dispatch_cfg=auto_dispatch_cfg,
        auto_inspection_cfg=auto_inspection_cfg,
        heartbeat_cfg=heartbeat_cfg,
        execution_context_cfg=execution_context_cfg,
        heartbeat_runtime=heartbeat_runtime,
        normalize_inspection_targets=normalize_inspection_targets,
        normalize_auto_inspections=normalize_auto_inspections,
        normalize_auto_inspection_tasks=normalize_auto_inspection_tasks,
        normalize_heartbeat_tasks=normalize_heartbeat_tasks,
        default_inspection_targets=default_inspection_targets,
    )
    return 200, payload
