# -*- coding: utf-8 -*-

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from task_dashboard.runtime.execution_profiles import (
    normalize_execution_profile as _normalize_execution_profile,
    resolve_execution_profile_permissions,
)


def prepare_run_execution_context(
    meta: dict[str, Any],
    *,
    cli_type: str,
    runs_parent: Path,
    worktree_root: Path,
    normalize_reasoning_effort: Callable[[Any], str],
    session_store_cls: Any,
    derive_session_work_context: Callable[..., dict[str, str]],
    resolve_model_for_session: Callable[..., str],
    resolve_reasoning_effort_for_session: Callable[..., str],
    resolve_run_work_context: Callable[..., dict[str, str]],
    load_project_execution_context: Callable[..., dict[str, Any]] | None,
    resolve_project_workdir: Callable[[str], Path],
    project_channel_model: Callable[[str, str], str],
    project_channel_reasoning_effort: Callable[[str, str], str],
) -> dict[str, Any]:
    row = dict(meta if isinstance(meta, dict) else {})
    row["status"] = "running"
    project_id = str(row.get("projectId") or "").strip()
    session_id = str(row.get("sessionId") or "").strip()
    profile_label = str(row.get("profileLabel") or "").strip()
    run_model = str(row.get("model") or "").strip()
    run_reasoning = normalize_reasoning_effort(row.get("reasoning_effort"))
    execution_profile = _normalize_execution_profile(row.get("execution_profile"), allow_empty=True)

    session_model = ""
    session_reasoning = ""
    session_context: dict[str, Any] = {}
    project_context: dict[str, Any] = {}
    if not run_model and session_id:
        try:
            sstore = session_store_cls(base_dir=runs_parent)
            session_row = sstore.get_session(session_id) or {}
            session_context = derive_session_work_context(
                session_row,
                project_id=project_id,
                worktree_root=worktree_root,
            )
            session_model = resolve_model_for_session(
                sstore,
                project_id=project_id,
                session_id=session_id,
            )
            if not run_reasoning:
                session_reasoning = resolve_reasoning_effort_for_session(
                    sstore,
                    project_id=project_id,
                    session_id=session_id,
                )
        except Exception:
            session_model = ""
            session_reasoning = ""
            session_context = {}

    effective_context = resolve_run_work_context(
        row,
        project_id=project_id,
        session_context=session_context,
        worktree_root=worktree_root,
    )
    if project_id and callable(load_project_execution_context):
        try:
            project_context = load_project_execution_context(
                project_id,
                environment_name=effective_context.get("environment") or row.get("environment") or "",
                worktree_root=effective_context.get("worktree_root") or worktree_root,
            ) or {}
        except Exception:
            project_context = {}
    if not execution_profile:
        execution_profile = _normalize_execution_profile(
            (project_context or {}).get("profile"),
            allow_empty=True,
        )
    execution_profile = execution_profile or "sandboxed"
    execution_permissions = resolve_execution_profile_permissions(
        execution_profile,
        config=None,
    )
    if isinstance((project_context or {}).get("permissions"), dict):
        execution_permissions.update(
            {
                key: value
                for key, value in dict(project_context.get("permissions") or {}).items()
                if value not in (None, "")
            }
        )
    run_cwd = Path(str(effective_context.get("workdir") or resolve_project_workdir(project_id)))

    channel_name = str(row.get("channelName") or "").strip()
    channel_model = project_channel_model(project_id, channel_name)
    channel_reasoning = project_channel_reasoning_effort(project_id, channel_name)
    resolved_model = run_model or session_model or channel_model
    resolved_reasoning = run_reasoning or session_reasoning or channel_reasoning

    row.update(effective_context)
    row["execution_profile"] = execution_profile
    row["execution_permissions"] = execution_permissions
    if resolved_model:
        row["model"] = resolved_model
    if resolved_reasoning:
        row["reasoning_effort"] = resolved_reasoning

    return {
        "meta": row,
        "project_id": project_id,
        "session_id": session_id,
        "profile_label": profile_label,
        "run_cwd": run_cwd,
        "resolved_model": resolved_model,
        "resolved_reasoning": resolved_reasoning,
        "execution_profile": execution_profile,
        "execution_permissions": execution_permissions,
        "session_context": session_context,
        "effective_context": effective_context,
    }
