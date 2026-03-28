# -*- coding: utf-8 -*-

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable


def list_project_heartbeat_tasks_response(*, project_id: str, find_project_cfg: Callable[[str], Any], heartbeat_runtime: Any) -> tuple[int, dict[str, Any]]:
    if not project_id:
        return 400, {"error": "missing project_id"}
    if not find_project_cfg(project_id):
        return 404, {"error": "project not found"}
    if heartbeat_runtime is None:
        return 503, {"error": "heartbeat task runtime unavailable"}
    return 200, heartbeat_runtime.list_tasks(project_id)


def get_project_heartbeat_task_response(
    *,
    project_id: str,
    heartbeat_task_id: str,
    find_project_cfg: Callable[[str], Any],
    heartbeat_runtime: Any,
) -> tuple[int, dict[str, Any]]:
    if not project_id:
        return 400, {"error": "missing project_id"}
    if not heartbeat_task_id:
        return 400, {"error": "missing heartbeat_task_id"}
    if not find_project_cfg(project_id):
        return 404, {"error": "project not found"}
    if heartbeat_runtime is None:
        return 503, {"error": "heartbeat task runtime unavailable"}
    item = heartbeat_runtime.get_task(project_id, heartbeat_task_id)
    if not item:
        return 404, {"error": "heartbeat task not found"}
    return 200, {"project_id": project_id, "item": item}


def list_project_heartbeat_task_history_response(
    *,
    project_id: str,
    heartbeat_task_id: str,
    limit: int,
    find_project_cfg: Callable[[str], Any],
    heartbeat_runtime: Any,
) -> tuple[int, dict[str, Any]]:
    if not project_id:
        return 400, {"error": "missing project_id"}
    if not heartbeat_task_id:
        return 400, {"error": "missing heartbeat_task_id"}
    if not find_project_cfg(project_id):
        return 404, {"error": "project not found"}
    if heartbeat_runtime is None:
        return 503, {"error": "heartbeat task runtime unavailable"}
    items = heartbeat_runtime.list_history(project_id, heartbeat_task_id, limit=limit)
    return 200, {
        "project_id": project_id,
        "heartbeat_task_id": heartbeat_task_id,
        "items": items,
        "count": len(items),
    }


def list_session_heartbeat_task_history_response(
    *,
    session_id: str,
    heartbeat_task_id: str,
    limit: int,
    session_store: Any,
    store: Any,
    heartbeat_runtime: Any,
    infer_project_id_for_session: Callable[[Any, str], str],
) -> tuple[int, dict[str, Any]]:
    if not session_id:
        return 400, {"error": "missing session_id"}
    if not heartbeat_task_id:
        return 400, {"error": "missing heartbeat_task_id"}
    if heartbeat_runtime is None:
        return 503, {"error": "heartbeat task runtime unavailable"}
    session = session_store.get_session(session_id)
    if not session:
        return 404, {"error": "session not found"}
    project_id = str(session.get("project_id") or "").strip() or infer_project_id_for_session(store, session_id)
    if not project_id:
        return 404, {"error": "project not found"}
    items = heartbeat_runtime.list_session_history(project_id, session_id, heartbeat_task_id, limit=limit)
    return 200, {
        "project_id": project_id,
        "session_id": session_id,
        "heartbeat_task_id": heartbeat_task_id,
        "items": items,
        "count": len(items),
    }


def create_or_update_project_heartbeat_task_response(
    *,
    project_id: str,
    body: dict[str, Any],
    find_project_cfg: Callable[[str], Any],
    heartbeat_runtime: Any,
    load_project_heartbeat_config: Callable[[str], dict[str, Any]],
    normalize_heartbeat_task: Callable[..., dict[str, Any] | None],
    heartbeat_tasks_for_write: Callable[[Any], list[dict[str, Any]]],
    build_heartbeat_patch_with_tasks: Callable[..., dict[str, Any]],
    coerce_bool: Callable[[Any, bool], bool],
    coerce_int: Callable[[Any, int], int],
    set_project_scheduler_contract_in_config: Callable[..., Path],
) -> tuple[int, dict[str, Any]]:
    if not project_id:
        return 400, {"error": "missing project_id"}
    if not find_project_cfg(project_id):
        return 404, {"error": "project not found"}
    if heartbeat_runtime is None:
        return 503, {"error": "heartbeat task runtime unavailable"}
    if not isinstance(body, dict):
        return 400, {"error": "bad json: object required"}
    task_payload = body.get("heartbeat_task") if isinstance(body.get("heartbeat_task"), dict) else body
    if not isinstance(task_payload, dict):
        return 400, {"error": "missing heartbeat_task"}
    cfg = load_project_heartbeat_config(project_id)
    new_task = normalize_heartbeat_task(task_payload, index=max(0, len(list(cfg.get("tasks") or []))), id_required=True)
    if not isinstance(new_task, dict):
        return 400, {"error": "invalid heartbeat_task"}
    task_id = str(new_task.get("heartbeat_task_id") or "").strip()
    current_tasks = heartbeat_tasks_for_write(cfg.get("tasks"))
    replaced = False
    merged_tasks: list[dict[str, Any]] = []
    for row in current_tasks:
        if str(row.get("heartbeat_task_id") or "").strip() == task_id:
            merged_tasks.append(new_task)
            replaced = True
        else:
            merged_tasks.append(row)
    if not replaced:
        merged_tasks.append(new_task)
    patch = build_heartbeat_patch_with_tasks(cfg=cfg, tasks=merged_tasks)
    if "enabled" in body:
        patch["enabled"] = coerce_bool(body.get("enabled"), bool(cfg.get("enabled")))
    if "scan_interval_seconds" in body:
        patch["scan_interval_seconds"] = max(20, int(coerce_int(body.get("scan_interval_seconds"), int(cfg.get("scan_interval_seconds") or 30))))
    try:
        config_path = set_project_scheduler_contract_in_config(project_id, heartbeat_patch=patch)
    except Exception as e:  # noqa: BLE001
        return 400, {"error": str(e)}
    payload = heartbeat_runtime.sync_project(project_id)
    created = heartbeat_runtime.get_task(project_id, task_id) or new_task
    return 200, {
        "ok": True,
        "project_id": project_id,
        "item": created,
        "count": int(payload.get("count") or 0),
        "enabled": bool(payload.get("enabled")),
        "scan_interval_seconds": int(payload.get("scan_interval_seconds") or 30),
        "config_path": str(config_path),
    }


def run_or_delete_session_heartbeat_task_response(
    *,
    session_id: str,
    heartbeat_task_id: str,
    action: str,
    session_store: Any,
    store: Any,
    heartbeat_runtime: Any,
    infer_project_id_for_session: Callable[[Any, str], str],
    load_session_heartbeat_config: Callable[[dict[str, Any]], dict[str, Any]],
    heartbeat_tasks_for_write: Callable[[Any], list[dict[str, Any]]],
    heartbeat_session_payload_for_write: Callable[..., dict[str, Any]],
) -> tuple[int, dict[str, Any]]:
    if not session_id:
        return 400, {"error": "missing session_id"}
    if not heartbeat_task_id:
        return 400, {"error": "missing heartbeat_task_id"}
    session = session_store.get_session(session_id)
    if not session:
        return 404, {"error": "session not found"}
    project_id = str(session.get("project_id") or "").strip() or infer_project_id_for_session(store, session_id)
    if not project_id:
        return 404, {"error": "project not found"}
    if heartbeat_runtime is None:
        return 503, {"error": "heartbeat task runtime unavailable"}
    if action == "run-now":
        try:
            record = heartbeat_runtime.run_session_task_now(project_id, session_id, heartbeat_task_id)
        except ValueError as e:
            return 422, {"error": str(e)}
        if not record:
            return 404, {"error": "heartbeat task not found"}
        item = heartbeat_runtime.get_session_task(project_id, session_id, heartbeat_task_id) or {}
        return 200, {
            "ok": True,
            "project_id": project_id,
            "session_id": session_id,
            "heartbeat_task_id": heartbeat_task_id,
            "record": record,
            "item": item,
        }
    existing_item = heartbeat_runtime.get_session_task(project_id, session_id, heartbeat_task_id) or {}
    if str(existing_item.get("source_scope") or "").strip() == "project":
        return 409, {"error": "project scoped heartbeat task must be managed from project config"}
    heartbeat_cfg = load_session_heartbeat_config(session)
    current_tasks = heartbeat_tasks_for_write(heartbeat_cfg.get("tasks"))
    merged_tasks = [row for row in current_tasks if str(row.get("heartbeat_task_id") or "").strip() != heartbeat_task_id]
    if len(merged_tasks) == len(current_tasks):
        return 404, {"error": "heartbeat task not found"}
    heartbeat_payload = heartbeat_session_payload_for_write(
        session,
        enabled=bool(heartbeat_cfg.get("enabled")),
        tasks=merged_tasks,
    )
    updated = session_store.update_session(session_id, heartbeat=heartbeat_payload)
    if not updated:
        return 404, {"error": "session not found"}
    payload = heartbeat_runtime.list_session_tasks(project_id, session_id)
    return 200, {
        "ok": True,
        "project_id": project_id,
        "session_id": session_id,
        "removed_heartbeat_task_id": heartbeat_task_id,
        "count": int(payload.get("count") or 0),
    }


def delete_project_heartbeat_task_response(
    *,
    project_id: str,
    heartbeat_task_id: str,
    find_project_cfg: Callable[[str], Any],
    heartbeat_runtime: Any,
    load_project_heartbeat_config: Callable[[str], dict[str, Any]],
    heartbeat_tasks_for_write: Callable[[Any], list[dict[str, Any]]],
    build_heartbeat_patch_with_tasks: Callable[..., dict[str, Any]],
    set_project_scheduler_contract_in_config: Callable[..., Path],
) -> tuple[int, dict[str, Any]]:
    if not project_id:
        return 400, {"error": "missing project_id"}
    if not heartbeat_task_id:
        return 400, {"error": "missing heartbeat_task_id"}
    if not find_project_cfg(project_id):
        return 404, {"error": "project not found"}
    if heartbeat_runtime is None:
        return 503, {"error": "heartbeat task runtime unavailable"}
    cfg = load_project_heartbeat_config(project_id)
    current_tasks = heartbeat_tasks_for_write(cfg.get("tasks"))
    merged_tasks = [row for row in current_tasks if str(row.get("heartbeat_task_id") or "").strip() != heartbeat_task_id]
    if len(merged_tasks) == len(current_tasks):
        return 404, {"error": "heartbeat task not found"}
    patch = build_heartbeat_patch_with_tasks(cfg=cfg, tasks=merged_tasks)
    try:
        config_path = set_project_scheduler_contract_in_config(project_id, heartbeat_patch=patch)
    except Exception as e:  # noqa: BLE001
        return 400, {"error": str(e)}
    payload = heartbeat_runtime.sync_project(project_id)
    return 200, {
        "ok": True,
        "project_id": project_id,
        "removed_heartbeat_task_id": heartbeat_task_id,
        "count": int(payload.get("count") or 0),
        "config_path": str(config_path),
    }


def run_project_heartbeat_task_now_response(
    *,
    project_id: str,
    heartbeat_task_id: str,
    find_project_cfg: Callable[[str], Any],
    heartbeat_runtime: Any,
) -> tuple[int, dict[str, Any]]:
    if not project_id:
        return 400, {"error": "missing project_id"}
    if not heartbeat_task_id:
        return 400, {"error": "missing heartbeat_task_id"}
    if not find_project_cfg(project_id):
        return 404, {"error": "project not found"}
    if heartbeat_runtime is None:
        return 503, {"error": "heartbeat task runtime unavailable"}
    try:
        record = heartbeat_runtime.run_now(project_id, heartbeat_task_id)
    except ValueError as e:
        return 422, {"error": str(e)}
    if not record:
        return 404, {"error": "heartbeat task not found"}
    item = heartbeat_runtime.get_task(project_id, heartbeat_task_id) or {}
    return 200, {
        "ok": True,
        "project_id": project_id,
        "heartbeat_task_id": heartbeat_task_id,
        "record": record,
        "item": item,
    }


def create_or_update_heartbeat_task_response(
    *,
    heartbeat_registry,  # HeartbeatTaskRuntimeRegistry 实例
    project_id: str,
    body: dict[str, Any],
    load_project_heartbeat_config: Callable[[str], dict[str, Any]],
    normalize_heartbeat_task: Callable[..., dict[str, Any] | None],
    heartbeat_tasks_for_write: Callable[[Any], list[dict[str, Any]]],
    build_heartbeat_patch_with_tasks: Callable[..., dict[str, Any]],
    set_project_scheduler_contract_in_config: Callable[..., Path],
    coerce_bool: Callable[[Any, bool], bool],
    coerce_int: Callable[[Any, int], int],
    find_project_cfg: Callable[[str], Any],
) -> tuple[int, dict[str, Any]]:
    """POST /api/projects/:id/heartbeat-tasks - 创建或更新项目心跳任务。"""
    if not project_id:
        return 400, {"error": "missing project_id"}
    if not find_project_cfg(project_id):
        return 404, {"error": "project not found"}
    if heartbeat_registry is None:
        return 503, {"error": "heartbeat task runtime unavailable"}
    if not isinstance(body, dict):
        return 400, {"error": "bad json: object required"}
    task_payload = body.get("heartbeat_task") if isinstance(body.get("heartbeat_task"), dict) else body
    if not isinstance(task_payload, dict):
        return 400, {"error": "missing heartbeat_task"}
    cfg = load_project_heartbeat_config(project_id)
    new_task = normalize_heartbeat_task(task_payload, index=max(0, len(list(cfg.get("tasks") or []))), id_required=True)
    if not isinstance(new_task, dict):
        return 400, {"error": "invalid heartbeat_task"}
    task_id = str(new_task.get("heartbeat_task_id") or "").strip()
    current_tasks = heartbeat_tasks_for_write(cfg.get("tasks"))
    replaced = False
    merged_tasks: list[dict[str, Any]] = []
    for row in current_tasks:
        if str(row.get("heartbeat_task_id") or "").strip() == task_id:
            merged_tasks.append(new_task)
            replaced = True
        else:
            merged_tasks.append(row)
    if not replaced:
        merged_tasks.append(new_task)
    patch = build_heartbeat_patch_with_tasks(cfg=cfg, tasks=merged_tasks)
    if "enabled" in body:
        patch["enabled"] = coerce_bool(body.get("enabled"), bool(cfg.get("enabled")))
    if "scan_interval_seconds" in body:
        patch["scan_interval_seconds"] = max(20, int(coerce_int(body.get("scan_interval_seconds"), int(cfg.get("scan_interval_seconds") or 30))))
    try:
        config_path = set_project_scheduler_contract_in_config(project_id, heartbeat_patch=patch)
    except Exception as e:  # noqa: BLE001
        return 400, {"error": str(e)}
    payload = heartbeat_registry.sync_project(project_id)
    created = heartbeat_registry.get_task(project_id, task_id) or new_task
    return 200, {
        "ok": True,
        "project_id": project_id,
        "item": created,
        "count": int(payload.get("count") or 0),
        "enabled": bool(payload.get("enabled")),
        "scan_interval_seconds": int(payload.get("scan_interval_seconds") or 30),
        "config_path": str(config_path),
    }


def delete_heartbeat_task_response(
    *,
    heartbeat_registry,  # HeartbeatTaskRuntimeRegistry 实例
    project_id: str,
    heartbeat_task_id: str,
    load_project_heartbeat_config: Callable[[str], dict[str, Any]],
    heartbeat_tasks_for_write: Callable[[Any], list[dict[str, Any]]],
    build_heartbeat_patch_with_tasks: Callable[..., dict[str, Any]],
    set_project_scheduler_contract_in_config: Callable[..., Path],
    find_project_cfg: Callable[[str], Any],
) -> tuple[int, dict[str, Any]]:
    """POST /api/projects/:id/heartbeat-tasks/:taskId/delete - 删除项目心跳任务。"""
    if not project_id:
        return 400, {"error": "missing project_id"}
    if not heartbeat_task_id:
        return 400, {"error": "missing heartbeat_task_id"}
    if not find_project_cfg(project_id):
        return 404, {"error": "project not found"}
    if heartbeat_registry is None:
        return 503, {"error": "heartbeat task runtime unavailable"}
    cfg = load_project_heartbeat_config(project_id)
    current_tasks = heartbeat_tasks_for_write(cfg.get("tasks"))
    merged_tasks = [row for row in current_tasks if str(row.get("heartbeat_task_id") or "").strip() != heartbeat_task_id]
    if len(merged_tasks) == len(current_tasks):
        return 404, {"error": "heartbeat task not found"}
    patch = build_heartbeat_patch_with_tasks(cfg=cfg, tasks=merged_tasks)
    try:
        config_path = set_project_scheduler_contract_in_config(project_id, heartbeat_patch=patch)
    except Exception as e:  # noqa: BLE001
        return 400, {"error": str(e)}
    payload = heartbeat_registry.sync_project(project_id)
    return 200, {
        "ok": True,
        "project_id": project_id,
        "removed_heartbeat_task_id": heartbeat_task_id,
        "count": int(payload.get("count") or 0),
        "config_path": str(config_path),
    }


def run_heartbeat_task_now_response(
    *,
    heartbeat_registry,  # HeartbeatTaskRuntimeRegistry 实例
    project_id: str,
    heartbeat_task_id: str,
    find_project_cfg: Callable[[str], Any],
) -> tuple[int, dict[str, Any]]:
    """POST /api/projects/:id/heartbeat-tasks/:taskId/run-now - 立即运行项目心跳任务。"""
    if not project_id:
        return 400, {"error": "missing project_id"}
    if not heartbeat_task_id:
        return 400, {"error": "missing heartbeat_task_id"}
    if not find_project_cfg(project_id):
        return 404, {"error": "project not found"}
    if heartbeat_registry is None:
        return 503, {"error": "heartbeat task runtime unavailable"}
    try:
        record = heartbeat_registry.run_now(project_id, heartbeat_task_id)
    except ValueError as e:
        return 422, {"error": str(e)}
    if not record:
        return 404, {"error": "heartbeat task not found"}
    item = heartbeat_registry.get_task(project_id, heartbeat_task_id) or {}
    return 200, {
        "ok": True,
        "project_id": project_id,
        "heartbeat_task_id": heartbeat_task_id,
        "record": record,
        "item": item,
    }


def run_session_heartbeat_task_now_response(
    *,
    heartbeat_registry,  # HeartbeatTaskRuntimeRegistry 实例
    session_id: str,
    heartbeat_task_id: str,
    session_store: Any,
    store: Any,
    infer_project_id_for_session: Callable[[Any, str], str],
) -> tuple[int, dict[str, Any]]:
    """POST /api/sessions/:sid/heartbeat-tasks/:taskId/run-now - 立即运行会话心跳任务。"""
    if not session_id:
        return 400, {"error": "missing session_id"}
    if not heartbeat_task_id:
        return 400, {"error": "missing heartbeat_task_id"}
    session = session_store.get_session(session_id)
    if not session:
        return 404, {"error": "session not found"}
    project_id = str(session.get("project_id") or "").strip() or infer_project_id_for_session(store, session_id)
    if not project_id:
        return 404, {"error": "project not found"}
    if heartbeat_registry is None:
        return 503, {"error": "heartbeat task runtime unavailable"}
    try:
        record = heartbeat_registry.run_session_task_now(project_id, session_id, heartbeat_task_id)
    except ValueError as e:
        return 422, {"error": str(e)}
    if not record:
        return 404, {"error": "heartbeat task not found"}
    item = heartbeat_registry.get_session_task(project_id, session_id, heartbeat_task_id) or {}
    return 200, {
        "ok": True,
        "project_id": project_id,
        "session_id": session_id,
        "heartbeat_task_id": heartbeat_task_id,
        "record": record,
        "item": item,
    }


def delete_session_heartbeat_task_response(
    *,
    heartbeat_registry,  # HeartbeatTaskRuntimeRegistry 实例
    session_id: str,
    heartbeat_task_id: str,
    session_store: Any,
    store: Any,
    infer_project_id_for_session: Callable[[Any, str], str],
    load_session_heartbeat_config: Callable[[dict[str, Any]], dict[str, Any]],
    heartbeat_tasks_for_write: Callable[[Any], list[dict[str, Any]]],
    heartbeat_session_payload_for_write: Callable[..., dict[str, Any]],
) -> tuple[int, dict[str, Any]]:
    """POST /api/sessions/:sid/heartbeat-tasks/:taskId/delete - 删除会话心跳任务。"""
    if not session_id:
        return 400, {"error": "missing session_id"}
    if not heartbeat_task_id:
        return 400, {"error": "missing heartbeat_task_id"}
    session = session_store.get_session(session_id)
    if not session:
        return 404, {"error": "session not found"}
    project_id = str(session.get("project_id") or "").strip() or infer_project_id_for_session(store, session_id)
    if not project_id:
        return 404, {"error": "project not found"}
    if heartbeat_registry is None:
        return 503, {"error": "heartbeat task runtime unavailable"}
    heartbeat_cfg = load_session_heartbeat_config(session)
    current_tasks = heartbeat_tasks_for_write(heartbeat_cfg.get("tasks"))
    merged_tasks = [row for row in current_tasks if str(row.get("heartbeat_task_id") or "").strip() != heartbeat_task_id]
    if len(merged_tasks) == len(current_tasks):
        return 404, {"error": "heartbeat task not found"}
    heartbeat_payload = heartbeat_session_payload_for_write(
        session,
        enabled=bool(heartbeat_cfg.get("enabled")),
        tasks=merged_tasks,
    )
    updated = session_store.update_session(session_id, heartbeat=heartbeat_payload)
    if not updated:
        return 404, {"error": "session not found"}
    payload = heartbeat_registry.list_session_tasks(project_id, session_id)
    return 200, {
        "ok": True,
        "project_id": project_id,
        "session_id": session_id,
        "removed_heartbeat_task_id": heartbeat_task_id,
        "count": int(payload.get("count") or 0),
    }
