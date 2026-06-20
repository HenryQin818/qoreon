# -*- coding: utf-8 -*-

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from task_dashboard.claude_models import normalize_claude_model
from task_dashboard.claude_permissions import normalize_claude_permission_mode
from task_dashboard.codebuddy_permissions import normalize_codebuddy_permission_mode
from task_dashboard.runtime.execution_profiles import (
    normalize_execution_profile as _normalize_execution_profile,
    resolve_execution_profile_permissions,
)


def _path_identity(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    path = Path(text).expanduser()
    try:
        if path.exists():
            return str(path.resolve())
        return str(path)
    except Exception:
        return text


def _paths_equal(left: Any, right: Any) -> bool:
    left_id = _path_identity(left)
    right_id = _path_identity(right)
    return bool(left_id and right_id and left_id == right_id)


def _resolve_callable_path_text(fn: Callable[..., Any] | None, *args: Any) -> str:
    if not callable(fn):
        return ""
    try:
        candidate = fn(*args)
    except Exception:
        return ""
    text = str(candidate or "").strip()
    if not text:
        return ""
    path = Path(text).expanduser()
    return str(path) if path.exists() and path.is_dir() else text


def _session_has_explicit_workdir(session: dict[str, Any], *, project_workdir: str = "") -> bool:
    context = session.get("project_execution_context") if isinstance(session.get("project_execution_context"), dict) else {}
    override = context.get("override") if isinstance(context.get("override"), dict) else {}
    fields = override.get("fields") if isinstance(override.get("fields"), list) else []
    if "workdir" in {str(item or "").strip() for item in fields}:
        return True
    workdir = str(session.get("workdir") or "").strip()
    if not workdir:
        return False
    if project_workdir and _paths_equal(workdir, project_workdir):
        return False
    return True


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
    resolve_channel_workdir: Callable[[str, str], Any] | None = None,
) -> dict[str, Any]:
    row = dict(meta if isinstance(meta, dict) else {})
    row["status"] = "running"
    project_id = str(row.get("projectId") or "").strip()
    session_id = str(row.get("sessionId") or "").strip()
    profile_label = str(row.get("profileLabel") or "").strip()
    run_model = str(row.get("model") or "").strip()
    run_reasoning = normalize_reasoning_effort(row.get("reasoning_effort"))
    execution_profile = _normalize_execution_profile(row.get("execution_profile"), allow_empty=True)
    cli_key = str(cli_type or "").strip().lower()

    session_model = ""
    session_reasoning = ""
    session_context: dict[str, Any] = {}
    session_row: dict[str, Any] = {}
    project_context: dict[str, Any] = {}
    if session_id and (cli_key in {"claude", "codebuddy"} or not run_model):
        try:
            sstore = session_store_cls(base_dir=runs_parent)
            loaded_session = sstore.get_session(session_id) or {}
            session_row = loaded_session if isinstance(loaded_session, dict) else {}
            session_context = derive_session_work_context(
                session_row,
                project_id=project_id,
                worktree_root=worktree_root,
            )
            if not run_model:
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
            session_row = {}

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
    channel_name = str(row.get("channelName") or "").strip()
    if cli_key in {"claude", "codebuddy"} and project_id and channel_name and callable(resolve_channel_workdir):
        project_workdir = _resolve_callable_path_text(resolve_project_workdir, project_id)
        row_workdir = str(row.get("workdir") or "").strip()
        if not row_workdir and not _session_has_explicit_workdir(session_row, project_workdir=project_workdir):
            channel_workdir = _resolve_callable_path_text(resolve_channel_workdir, project_id, channel_name)
            if channel_workdir:
                effective_context["workdir"] = channel_workdir
    run_cwd = Path(str(effective_context.get("workdir") or resolve_project_workdir(project_id)))

    channel_model = project_channel_model(project_id, channel_name)
    channel_reasoning = project_channel_reasoning_effort(project_id, channel_name)
    resolved_model = run_model or session_model or channel_model
    if cli_key == "claude":
        resolved_model = normalize_claude_model(resolved_model)
    resolved_reasoning = run_reasoning or session_reasoning or channel_reasoning

    row.update(effective_context)
    row["execution_profile"] = execution_profile
    row["execution_permissions"] = execution_permissions
    if resolved_model:
        row["model"] = resolved_model
    if resolved_reasoning:
        row["reasoning_effort"] = resolved_reasoning
    if cli_key == "codebuddy":
        row["codebuddy_permission_mode"] = normalize_codebuddy_permission_mode(
            row.get("codebuddy_permission_mode") or session_row.get("codebuddy_permission_mode")
        )
    if cli_key == "claude":
        row["claude_permission_mode"] = normalize_claude_permission_mode(
            row.get("claude_permission_mode")
            or row.get("permission_mode")
            or session_row.get("claude_permission_mode")
        )

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
