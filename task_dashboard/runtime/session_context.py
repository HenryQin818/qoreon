# -*- coding: utf-8 -*-

from __future__ import annotations

import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable

from task_dashboard.runtime.project_execution_context import (
    build_context_override_values,
    build_project_execution_context,
    diff_override_fields,
    infer_project_execution_context_source,
    merge_work_context_overrides,
)


_WORK_CONTEXT_CACHE_TTL_S = 2.0
_WORK_CONTEXT_CACHE_MAX = 64
_SERVER_DEFAULT_CONTEXT_CACHE: dict[tuple[str, str, str], dict[str, Any]] = {}
_PROJECT_SOURCE_CONTEXT_CACHE: dict[tuple[str, str, str], dict[str, Any]] = {}
_WORK_CONTEXT_CACHE_LOCK = threading.Lock()


def _cache_get(
    cache: dict[tuple[str, str, str], dict[str, Any]],
    key: tuple[str, str, str],
) -> dict[str, Any] | None:
    now_mono = time.monotonic()
    with _WORK_CONTEXT_CACHE_LOCK:
        cached = cache.get(key)
        if not isinstance(cached, dict):
            return None
        checked_at = float(cached.get("checked_at_mono") or 0.0)
        if (now_mono - checked_at) > _WORK_CONTEXT_CACHE_TTL_S:
            cache.pop(key, None)
            return None
        value = cached.get("value")
        if not isinstance(value, dict):
            return None
        return dict(value)


def _cache_set(
    cache: dict[tuple[str, str, str], dict[str, Any]],
    key: tuple[str, str, str],
    value: dict[str, Any],
) -> None:
    now_mono = time.monotonic()
    with _WORK_CONTEXT_CACHE_LOCK:
        cache[key] = {
            "checked_at_mono": now_mono,
            "value": dict(value),
        }
        if len(cache) > _WORK_CONTEXT_CACHE_MAX:
            stale_keys = sorted(
                cache.items(),
                key=lambda item: float((item[1] or {}).get("checked_at_mono") or 0.0),
            )[: max(1, len(cache) - _WORK_CONTEXT_CACHE_MAX)]
            for stale_key, _ in stale_keys:
                cache.pop(stale_key, None)


def _coerce_bool_local(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    txt = str(value).strip().lower()
    if txt in {"1", "true", "yes", "on"}:
        return True
    if txt in {"0", "false", "no", "off"}:
        return False
    return default


def detect_git_branch(root: Path | str) -> str:
    raw_target = str(root or "").strip()
    if not raw_target:
        return ""
    target = Path(raw_target).expanduser()
    try:
        proc = subprocess.run(
            ["git", "-C", str(target), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except Exception:
        return ""
    if proc.returncode != 0:
        return ""
    return str(proc.stdout or "").strip()


def _resolve_server_default_context(
    *,
    project_id: str = "",
    environment_name: str = "",
    worktree_root: Path | str | None = None,
    resolve_project_workdir: Callable[[str], Path] | None = None,
) -> dict[str, str]:
    resolved_environment = str(environment_name or "stable").strip() or "stable"
    resolved_worktree_root = ""
    if worktree_root is not None:
        resolved_worktree_root = str(Path(worktree_root).expanduser())
    cache_key = (
        str(project_id or "").strip(),
        resolved_environment,
        resolved_worktree_root,
    )
    cached = _cache_get(_SERVER_DEFAULT_CONTEXT_CACHE, cache_key)
    if cached is not None:
        return {
            "environment": str(cached.get("environment") or ""),
            "worktree_root": str(cached.get("worktree_root") or ""),
            "workdir": str(cached.get("workdir") or ""),
            "branch": str(cached.get("branch") or ""),
        }
    resolved_workdir = ""
    if project_id and callable(resolve_project_workdir):
        try:
            resolved_workdir = str(resolve_project_workdir(project_id))
        except Exception:
            resolved_workdir = ""
    resolved_branch = detect_git_branch(resolved_worktree_root) if resolved_worktree_root else ""
    result = {
        "environment": resolved_environment,
        "worktree_root": resolved_worktree_root,
        "workdir": resolved_workdir,
        "branch": resolved_branch,
    }
    _cache_set(_SERVER_DEFAULT_CONTEXT_CACHE, cache_key, result)
    return result


def _resolve_project_source_context(
    *,
    project_id: str = "",
    environment_name: str = "",
    worktree_root: Path | str | None = None,
    resolve_project_workdir: Callable[[str], Path] | None = None,
    load_project_execution_context: Callable[..., dict[str, Any]] | None = None,
) -> tuple[dict[str, str], str]:
    resolved_project_id = str(project_id or "").strip()
    resolved_environment = str(environment_name or "stable").strip() or "stable"
    resolved_worktree_root = str(Path(worktree_root).expanduser()) if worktree_root is not None else ""
    cache_key = (
        resolved_project_id,
        resolved_environment,
        resolved_worktree_root,
    )
    if resolved_project_id and callable(load_project_execution_context):
        cached = _cache_get(_PROJECT_SOURCE_CONTEXT_CACHE, cache_key)
        if cached is not None:
            return (
                {
                    "environment": str(cached.get("environment") or ""),
                    "worktree_root": str(cached.get("worktree_root") or ""),
                    "workdir": str(cached.get("workdir") or ""),
                    "branch": str(cached.get("branch") or ""),
                },
                str(cached.get("context_source") or "server_default"),
            )
    default_context = _resolve_server_default_context(
        project_id=resolved_project_id,
        environment_name=resolved_environment,
        worktree_root=resolved_worktree_root,
        resolve_project_workdir=resolve_project_workdir,
    )
    if not resolved_project_id or not callable(load_project_execution_context):
        return default_context, "server_default"
    try:
        loaded = load_project_execution_context(
            project_id=resolved_project_id,
            environment_name=resolved_environment,
            worktree_root=resolved_worktree_root,
        )
    except TypeError:
        loaded = load_project_execution_context(project_id)
    except Exception:
        loaded = {}
    effective, _fields, _override_source = merge_work_context_overrides(
        default_context,
        loaded if isinstance(loaded, dict) else {},
    )
    context_source = infer_project_execution_context_source(
        project_context=loaded if isinstance(loaded, dict) else {},
        stored_context_source=(loaded or {}).get("context_source") if isinstance(loaded, dict) else "",
    )
    _cache_set(
        _PROJECT_SOURCE_CONTEXT_CACHE,
        cache_key,
        {
            **effective,
            "context_source": context_source,
        },
    )
    return effective, context_source


def _resolve_session_work_context_bundle(
    session: dict[str, Any],
    *,
    project_id: str = "",
    environment_name: str = "",
    worktree_root: Path | str | None = None,
    resolve_project_workdir: Callable[[str], Path] | None = None,
    load_project_execution_context: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    row = dict(session if isinstance(session, dict) else {})
    resolved_project_id = str(project_id or row.get("project_id") or "").strip()
    stored_context = row.get("project_execution_context") if isinstance(row.get("project_execution_context"), dict) else {}
    if stored_context and not callable(load_project_execution_context):
        default_context = _resolve_server_default_context(
            project_id=resolved_project_id,
            environment_name=environment_name,
            worktree_root=worktree_root,
            resolve_project_workdir=resolve_project_workdir,
        )
        stored_source = stored_context.get("source") if isinstance(stored_context.get("source"), dict) else {}
        source_context, _source_fields, _source_override = merge_work_context_overrides(
            default_context,
            stored_source,
        )
        context_source = infer_project_execution_context_source(
            project_context=stored_source,
            stored_context_source=stored_context.get("context_source"),
        )
    else:
        source_context, context_source = _resolve_project_source_context(
            project_id=resolved_project_id,
            environment_name=environment_name,
            worktree_root=worktree_root,
            resolve_project_workdir=resolve_project_workdir,
            load_project_execution_context=load_project_execution_context,
        )
    if stored_context:
        session_override_values, override_fields = build_context_override_values(
            stored_context,
            fallback_target=row,
        )
        override_obj = stored_context.get("override") if isinstance(stored_context.get("override"), dict) else {}
        override_source = str(override_obj.get("source") or "").strip().lower() if override_fields else ""
        if override_fields and override_source not in {"session", "request", "run"}:
            override_source = "session"
    else:
        session_override_values = row
        override_fields = []
        override_source = "session"
    effective_context, override_fields, override_source = merge_work_context_overrides(
        source_context,
        session_override_values,
        override_source=override_source or "session",
    )
    return {
        "project_id": resolved_project_id,
        "source_context": source_context,
        "effective_context": effective_context,
        "context_source": context_source,
        "override_fields": override_fields or diff_override_fields(effective_context, source_context),
        "override_source": override_source,
    }


def derive_session_work_context(
    session: dict[str, Any],
    *,
    project_id: str = "",
    environment_name: str = "",
    worktree_root: Path | str | None = None,
    resolve_project_workdir: Callable[[str], Path] | None = None,
    load_project_execution_context: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, str]:
    bundle = _resolve_session_work_context_bundle(
        session,
        project_id=project_id,
        environment_name=environment_name,
        worktree_root=worktree_root,
        resolve_project_workdir=resolve_project_workdir,
        load_project_execution_context=load_project_execution_context,
    )
    return dict(bundle.get("effective_context") or {})


def apply_session_work_context(
    session: dict[str, Any],
    *,
    project_id: str = "",
    environment_name: str = "",
    worktree_root: Path | str | None = None,
    resolve_project_workdir: Callable[[str], Path] | None = None,
    load_project_execution_context: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    row = dict(session if isinstance(session, dict) else {})
    stored_context = row.get("project_execution_context") if isinstance(row.get("project_execution_context"), dict) else {}
    looks_persisted_session = bool(
        str(row.get("id") or "").strip()
        or str(row.get("created_at") or "").strip()
        or str(row.get("status") or "").strip()
    )
    effective_project_context_loader = load_project_execution_context
    if looks_persisted_session:
        effective_project_context_loader = None
    bundle = _resolve_session_work_context_bundle(
        row,
        project_id=project_id,
        environment_name=environment_name,
        worktree_root=worktree_root,
        resolve_project_workdir=resolve_project_workdir,
        load_project_execution_context=effective_project_context_loader,
    )
    effective_context = dict(bundle.get("effective_context") or {})
    source_context = dict(bundle.get("source_context") or {})
    resolved_project_id = str(bundle.get("project_id") or project_id or row.get("project_id") or "").strip()
    row.update(effective_context)
    row["project_execution_context"] = build_project_execution_context(
        target={
            "project_id": resolved_project_id,
            "channel_name": str(row.get("channel_name") or "").strip(),
            "session_id": str(row.get("id") or "").strip(),
            **effective_context,
        },
        source={
            "project_id": resolved_project_id,
            **source_context,
        },
        context_source=str(bundle.get("context_source") or ""),
        override_fields=list(bundle.get("override_fields") or []),
        override_source=str(bundle.get("override_source") or ""),
    )
    return row


def stable_write_ack_requested(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    return _coerce_bool_local(
        payload.get("allow_stable_write") if "allow_stable_write" in payload else payload.get("allowStableWrite"),
        False,
    )


def session_context_write_requires_guard(
    session: dict[str, Any],
    update_fields: dict[str, Any],
    *,
    server_environment: str = "",
) -> bool:
    if not isinstance(session, dict) or not isinstance(update_fields, dict):
        return False
    guarded_keys = {"environment", "worktree_root", "workdir", "branch", "channel_name"}
    if not any(key in update_fields for key in guarded_keys):
        return False
    current_env = str(session.get("environment") or server_environment or "stable").strip().lower() or "stable"
    target_env = str(update_fields.get("environment") or current_env).strip().lower() or current_env
    changed = False
    for key in guarded_keys:
        if key not in update_fields:
            continue
        current_value = str(session.get(key) or "").strip()
        target_value = str(update_fields.get(key) or "").strip()
        if key == "environment":
            current_value = current_env
            target_value = target_env
        if current_value != target_value:
            changed = True
            break
    if not changed:
        return False
    return current_env == "stable" or target_env == "stable"


def resolve_run_work_context(
    meta: dict[str, Any],
    *,
    project_id: str = "",
    session_context: dict[str, Any] | None = None,
    worktree_root: Path | str | None = None,
    resolve_project_workdir: Callable[[str], Path] | None = None,
    load_project_execution_context: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, str]:
    source_context, _context_source = _resolve_project_source_context(
        project_id=project_id,
        worktree_root=worktree_root,
        resolve_project_workdir=resolve_project_workdir,
        load_project_execution_context=load_project_execution_context,
    )
    effective_context, _session_override_fields, _session_override_source = merge_work_context_overrides(
        source_context,
        session_context or {},
        override_source="session",
    )
    effective_context, _run_override_fields, _run_override_source = merge_work_context_overrides(
        effective_context,
        meta,
        override_source="run",
    )
    run_cwd_text = str(effective_context.get("workdir") or "").strip()
    if run_cwd_text:
        candidate_cwd = Path(run_cwd_text).expanduser()
        if candidate_cwd.exists() and candidate_cwd.is_dir():
            effective_context["workdir"] = str(candidate_cwd)
            return effective_context
    if project_id and callable(resolve_project_workdir):
        try:
            effective_context["workdir"] = str(resolve_project_workdir(project_id))
        except Exception:
            pass
    return effective_context
