# -*- coding: utf-8 -*-

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from task_dashboard.runtime.execution_profiles import normalize_execution_profile
from task_dashboard.session_store import session_binding_is_available, session_binding_sort_key
from task_dashboard.helpers import looks_like_session_id


def _derive_context_binding_state(context_meta: Any, *, fallback_target: Any = None) -> str:
    ctx = context_meta if isinstance(context_meta, dict) else {}
    target = ctx.get("target") if isinstance(ctx.get("target"), dict) else {}
    if not isinstance(target, dict) or not target:
        target = fallback_target if isinstance(fallback_target, dict) else {}
    override = ctx.get("override") if isinstance(ctx.get("override"), dict) else {}
    has_binding = bool(str(target.get("worktree_root") or "").strip() and str(target.get("branch") or "").strip())
    if not has_binding:
        return "unbound"
    if bool(override.get("applied")):
        return "override"
    return "bound"


def _normalize_reuse_strategy(value: Any) -> str:
    text = str(value or "").strip().lower().replace("-", "_")
    if text in {"reuse", "reuse_existing", "reuse_active"}:
        return "reuse_active"
    if text in {"rotate", "replace"}:
        return "rotate"
    if text in {"copy", "clone", "duplicate"}:
        return "copy"
    if text in {"", "new", "create", "create_new"}:
        return "create_new"
    return "create_new"


def _resolve_context_dir(raw: Any, *, fallback_root: Path | str | None = None) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    path = Path(text).expanduser()
    if not path.is_absolute() and fallback_root:
        path = Path(fallback_root) / path
    try:
        path = path.resolve()
    except Exception:
        path = path.absolute()
    if path.exists() and path.is_dir():
        return str(path)
    return ""


def _looks_like_uuid_local(value: Any) -> bool:
    return looks_like_session_id(str(value or ""))


def _session_process_busy_best_effort(session_id: str, cli_type: str = "codex") -> bool:
    try:
        from task_dashboard.runtime.heartbeat_registry import _session_process_busy

        return bool(_session_process_busy(str(session_id or "").strip(), cli_type=str(cli_type or "codex")))
    except Exception:
        return False


def _pick_reusable_session(
    sessions: list[dict[str, Any]],
    *,
    environment: str,
    worktree_root: str,
    workdir: str = "",
    branch: str = "",
    cli_type: str,
) -> dict[str, Any] | None:
    available = [
        row for row in sessions
        if isinstance(row, dict)
        and session_binding_is_available(row)
    ]
    if not available:
        return None
    exact = [
        row for row in available
        if str(row.get("environment") or "").strip() == environment
        and str(row.get("worktree_root") or "").strip() == worktree_root
        and str(row.get("cli_type") or "codex").strip() == cli_type
    ]
    requested_workdir = str(workdir or "").strip()
    if requested_workdir:
        exact_workdir = [
            row for row in exact
            if str(row.get("workdir") or "").strip() == requested_workdir
        ]
        if exact_workdir:
            exact = exact_workdir
        elif exact:
            return None
    requested_branch = str(branch or "").strip()
    if requested_branch:
        exact_branch = [
            row for row in exact
            if str(row.get("branch") or "").strip() == requested_branch
        ]
        if exact_branch:
            exact = exact_branch
        elif exact:
            return None
    candidates = exact or available
    candidates.sort(key=session_binding_sort_key, reverse=True)
    return candidates[0] if candidates else None


def create_session_response(
    *,
    payload: dict[str, Any],
    session_store: Any,
    environment_name: str,
    worktree_root: str,
    create_cli_session: Callable[..., dict[str, Any]],
    resolve_project_workdir: Callable[[str], Any],
    detect_git_branch: Callable[[str], str],
    build_session_seed_prompt: Callable[..., str],
    decorate_session_display_fields: Callable[[dict[str, Any]], dict[str, Any]],
    apply_session_work_context: Callable[..., dict[str, Any]],
    load_project_execution_context: Callable[..., dict[str, Any]] | None = None,
    project_exists: Callable[[str], bool],
    channel_exists: Callable[[str, str], bool],
) -> dict[str, Any]:
    project_id = str(payload.get("project_id") or "")
    channel_name = str(payload.get("channel_name") or "")
    mode = str(payload.get("mode") or "create_new").strip() or "create_new"
    requested_session_id = str(payload.get("session_id") or "").strip()
    cli_type = str(payload.get("cli_type") or "codex")
    model = str(payload.get("model") or "")
    reasoning_effort = str(payload.get("reasoning_effort") or "")
    alias = str(payload.get("alias") or "")
    environment = str(payload.get("environment") or environment_name or "stable").strip() or "stable"
    requested_worktree_root = str(payload.get("worktree_root") or worktree_root or "").strip()
    requested_workdir = str(payload.get("workdir") or "").strip()
    requested_branch = str(payload.get("branch") or "").strip()
    session_role = str(payload.get("session_role") or "").strip()
    purpose = str(payload.get("purpose") or "").strip()
    reuse_strategy = _normalize_reuse_strategy(payload.get("reuse_strategy"))
    reuse_strategy_explicit = bool(payload.get("reuse_strategy_explicit"))
    set_as_primary = payload.get("set_as_primary")
    first_message = str(payload.get("first_message") or "")
    if not project_id or not channel_name:
        raise ValueError("missing project_id or channel_name")
    if not project_exists(project_id):
        raise LookupError("project not found")
    if not channel_exists(project_id, channel_name):
        raise LookupError("channel not found")

    requested_context_seed = {
        "project_id": project_id,
        "channel_name": channel_name,
        "environment": environment,
        "worktree_root": requested_worktree_root,
        "workdir": requested_workdir,
        "branch": requested_branch,
    }
    resolved_context_seed = apply_session_work_context(
        requested_context_seed,
        project_id=project_id,
        environment_name=environment_name,
        worktree_root=worktree_root,
    )
    effective_environment = str(resolved_context_seed.get("environment") or environment or environment_name or "stable").strip() or "stable"
    effective_worktree_root = str(resolved_context_seed.get("worktree_root") or "").strip() or str(worktree_root or "")
    resolved_workdir_text = (
        _resolve_context_dir(requested_workdir, fallback_root=effective_worktree_root)
        if requested_workdir
        else str(resolved_context_seed.get("workdir") or "").strip()
    )
    if not resolved_workdir_text:
        resolved_workdir_text = str(resolve_project_workdir(project_id))
    project_workdir = Path(resolved_workdir_text)
    branch = str(resolved_context_seed.get("branch") or requested_branch or detect_git_branch(effective_worktree_root)).strip()
    context_meta = resolved_context_seed.get("project_execution_context")
    context_meta = context_meta if isinstance(context_meta, dict) else {}
    project_context: dict[str, Any] = {}
    if callable(load_project_execution_context):
        try:
            project_context = load_project_execution_context(
                project_id=project_id,
                environment_name=effective_environment,
                worktree_root=effective_worktree_root,
            ) or {}
        except TypeError:
            try:
                project_context = load_project_execution_context(project_id) or {}
            except Exception:
                project_context = {}
        except Exception:
            project_context = {}
    execution_profile = normalize_execution_profile(
        (project_context if isinstance(project_context, dict) else {}).get("profile"),
        allow_empty=True,
    )
    effective_primary = set_as_primary if isinstance(set_as_primary, bool) else (session_role == "primary")
    effective_binding_state = _derive_context_binding_state(
        context_meta,
        fallback_target={
            "environment": effective_environment,
            "worktree_root": effective_worktree_root,
            "workdir": str(project_workdir),
            "branch": branch,
        },
    )

    if mode == "attach_existing" or requested_session_id:
        if not _looks_like_uuid_local(requested_session_id):
            raise ValueError("invalid session_id")
        if _session_process_busy_best_effort(requested_session_id, cli_type=cli_type):
            raise ValueError("session is currently busy")
        attached_session, imported = session_store.attach_existing_session(
            project_id=project_id,
            channel_name=channel_name,
            session_id=requested_session_id,
            cli_type=cli_type,
            alias=alias,
            model=model,
            reasoning_effort=reasoning_effort,
            environment=effective_environment,
            worktree_root=effective_worktree_root,
            workdir=str(project_workdir),
            branch=branch,
            session_role=session_role,
            purpose=purpose,
            reuse_strategy=reuse_strategy or "attach_existing",
            schema_version="session.attach_existing.v1",
            created_via="api.attach_existing_session_v1",
            context_binding_state=effective_binding_state,
            project_execution_context=context_meta,
            is_primary=effective_primary if isinstance(effective_primary, bool) else None,
        )
        attached_session = decorate_session_display_fields(attached_session)
        attached_session = apply_session_work_context(
            attached_session,
            project_id=project_id,
            environment_name=effective_environment,
            worktree_root=effective_worktree_root,
        )
        return {
            "session": attached_session,
            "sessionPath": "",
            "workdir": str(project_workdir),
            "created": False,
            "reused": False,
            "attached": True,
            "imported": bool(imported),
        }

    if (
        reuse_strategy == "reuse_active"
        and not reuse_strategy_explicit
        and set_as_primary is True
        and session_role == "primary"
    ):
        reuse_strategy = "create_new"

    if reuse_strategy == "reuse_active":
        reusable = _pick_reusable_session(
            session_store.list_sessions(project_id, channel_name, include_deleted=True),
            environment=effective_environment,
            worktree_root=effective_worktree_root,
            workdir=str(project_workdir),
            branch=branch,
            cli_type=cli_type,
        )
        if reusable:
            update_fields: dict[str, Any] = {
                "last_used_at": reusable.get("last_used_at") or "",
                "reuse_strategy": reuse_strategy,
                "schema_version": "session.create.v2",
                "created_via": "api.create_session_v2.reuse",
                "context_binding_state": effective_binding_state,
            }
            if alias:
                update_fields["alias"] = alias
            if model:
                update_fields["model"] = model
            if reasoning_effort:
                update_fields["reasoning_effort"] = reasoning_effort
            if purpose:
                update_fields["purpose"] = purpose
            if session_role:
                update_fields["session_role"] = session_role
            if effective_environment:
                update_fields["environment"] = effective_environment
            if effective_worktree_root:
                update_fields["worktree_root"] = effective_worktree_root
            if str(project_workdir or "").strip():
                update_fields["workdir"] = str(project_workdir)
            if branch:
                update_fields["branch"] = branch
            if context_meta:
                update_fields["project_execution_context"] = context_meta
            if effective_primary:
                update_fields["is_primary"] = True
            session = session_store.update_session(str(reusable.get("id") or "").strip(), **update_fields)
            if not session:
                raise LookupError("session not found")
            session = decorate_session_display_fields(session)
            session = apply_session_work_context(
                session,
                project_id=project_id,
                environment_name=effective_environment,
                worktree_root=effective_worktree_root,
            )
            return {
                "session": session,
                "sessionPath": "",
                "workdir": str(project_workdir),
                "created": False,
                "reused": True,
            }

    seed = build_session_seed_prompt(
        project_id=project_id,
        channel_name=channel_name,
        first_message=first_message,
    )
    create_result = create_cli_session(
        seed_prompt=seed,
        timeout_s=90,
        cli_type=cli_type,
        workdir=project_workdir,
        model=model,
        reasoning_effort=reasoning_effort,
        execution_profile=execution_profile,
    )
    timeout_recovered = False
    create_warning: dict[str, Any] = {}
    create_error = str(create_result.get("error") or "").strip().lower()
    recovered_session_id = str(create_result.get("sessionId") or "").strip()
    if not create_result.get("ok"):
        if "timeout" in create_error and _looks_like_uuid_local(recovered_session_id):
            timeout_recovered = True
            create_warning = {
                "error": str(create_result.get("error") or "timeout"),
                "cliType": create_result.get("cliType", cli_type),
                "sessionId": recovered_session_id,
                "sessionPath": create_result.get("sessionPath", ""),
            }
        else:
            err = RuntimeError("create session failed")
            setattr(err, "detail", create_result)
            raise err
    session = session_store.create_session(
        project_id=project_id,
        channel_name=channel_name,
        cli_type=cli_type,
        alias=alias,
        session_id=recovered_session_id,
        model=model,
        reasoning_effort=reasoning_effort,
        environment=effective_environment,
        worktree_root=effective_worktree_root,
        workdir=str(create_result.get("workdir", str(project_workdir)) or str(project_workdir)),
        branch=branch,
        session_role=session_role,
        purpose=purpose,
        reuse_strategy=reuse_strategy,
        schema_version="session.create.v2",
        created_via="api.create_session_v2.timeout_recovered" if timeout_recovered else "api.create_session_v2",
        context_binding_state=effective_binding_state,
        project_execution_context=context_meta,
        is_primary=effective_primary if isinstance(effective_primary, bool) else None,
    )
    session = decorate_session_display_fields(session)
    session = apply_session_work_context(
        session,
        project_id=project_id,
        environment_name=effective_environment,
        worktree_root=effective_worktree_root,
    )
    return {
        "session": session,
        "sessionPath": create_result.get("sessionPath", ""),
        "workdir": create_result.get("workdir", str(project_workdir)),
        "created": True,
        "reused": False,
        "timeout_recovered": timeout_recovered,
        "timeoutRecovered": timeout_recovered,
        "create_warning": create_warning,
    }


def save_binding_response(
    *,
    session_binding_store: Any,
    session_id: str,
    project_id: str,
    channel_name: str,
    cli_type: str,
) -> dict[str, Any]:
    compat_meta = {
        "compatibility_entry": True,
        "entry_role": "compatibility_management",
        "writable": True,
        "primary_truth_hint": "/api/sessions + /api/agent-candidates",
    }
    return {
        "binding": session_binding_store.save_binding(session_id, project_id, channel_name, cli_type),
        **compat_meta,
    }


def delete_binding_response(
    *,
    session_binding_store: Any,
    session_id: str,
) -> dict[str, Any]:
    return {
        "deleted": session_binding_store.delete_binding(session_id),
        "compatibility_entry": True,
        "entry_role": "compatibility_management",
        "writable": True,
        "primary_truth_hint": "/api/sessions + /api/agent-candidates",
    }


def manage_channel_sessions_response(
    *,
    session_store: Any,
    project_id: str,
    channel_name: str,
    primary_session_id: str,
    updates: list[dict[str, Any]],
    decorate_sessions_display_fields: Callable[[list[dict[str, Any]]], list[dict[str, Any]]],
) -> dict[str, Any]:
    result = session_store.manage_channel_sessions(
        project_id,
        channel_name,
        primary_session_id=primary_session_id,
        updates=updates,
    )
    sessions = decorate_sessions_display_fields(result.get("sessions") or [])
    return {
        "ok": True,
        "project_id": project_id,
        "channel_name": channel_name,
        "primary_session_id": result.get("primary_session_id") or "",
        "sessions": sessions,
        "count": len(sessions),
    }


def update_session_response(
    *,
    session_store: Any,
    session_id: str,
    update_fields: dict[str, Any],
    body: dict[str, Any],
    store: Any,
    environment_name: str,
    worktree_root: Any,
    infer_project_id_for_session: Callable[[Any, str], str],
    apply_session_work_context: Callable[..., dict[str, Any]],
    session_context_write_requires_guard: Callable[[dict[str, Any], dict[str, Any]], bool],
    stable_write_ack_requested: Callable[[dict[str, Any]], bool],
    coerce_bool: Callable[[Any, bool], bool],
    heartbeat_session_payload_for_write: Callable[..., dict[str, Any]],
    build_session_detail_response: Callable[..., dict[str, Any] | None],
    heartbeat_runtime: Any,
    apply_effective_primary_flags: Callable[[Any, str, list[dict[str, Any]]], list[dict[str, Any]]],
    decorate_session_display_fields: Callable[[dict[str, Any]], dict[str, Any]],
    build_session_detail_payload: Callable[..., dict[str, Any]],
    build_project_session_runtime_index: Callable[[Any, str], dict[str, Any]],
    build_session_runtime_state_for_row: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]],
    load_session_heartbeat_config: Callable[[dict[str, Any]], dict[str, Any]],
    heartbeat_summary_payload: Callable[[Any], Any],
) -> dict[str, Any]:
    session = session_store.get_session(session_id)
    if not session:
        raise LookupError("session not found")
    project_id = str(session.get("project_id") or "").strip() or infer_project_id_for_session(store, session_id)
    guard_session = apply_session_work_context(
        session,
        project_id=project_id,
        environment_name=environment_name,
        worktree_root=worktree_root,
    )
    if session_context_write_requires_guard(
        guard_session,
        update_fields,
        server_environment=environment_name,
    ) and not stable_write_ack_requested(body):
        raise PermissionError(str(session.get("environment") or environment_name or "stable"))

    if "heartbeat" in body:
        heartbeat_obj = body.get("heartbeat")
        if not isinstance(heartbeat_obj, dict):
            raise ValueError("invalid heartbeat")
        enabled = coerce_bool(
            heartbeat_obj.get("enabled"),
            coerce_bool(((session.get("heartbeat") or {}) if isinstance(session.get("heartbeat"), dict) else {}).get("enabled"), False),
        )
        raw_tasks = heartbeat_obj.get("tasks") if "tasks" in heartbeat_obj else heartbeat_obj.get("heartbeat_tasks")
        if raw_tasks in (None, ""):
            raw_tasks = []
        if raw_tasks is not None and not isinstance(raw_tasks, list):
            raise ValueError("invalid heartbeat.tasks")
        update_fields["heartbeat"] = heartbeat_session_payload_for_write(
            session,
            enabled=enabled,
            tasks=raw_tasks,
        )

    preview_session = dict(session)
    preview_session.update(update_fields)
    preview_payload = apply_session_work_context(
        preview_session,
        project_id=project_id,
        environment_name=environment_name,
        worktree_root=worktree_root,
    )
    preview_context = preview_payload.get("project_execution_context")
    if isinstance(preview_context, dict):
        update_fields["project_execution_context"] = preview_context
        update_fields["context_binding_state"] = _derive_context_binding_state(preview_context)

    if not update_fields:
        raise ValueError("no fields to update")

    updated = session_store.update_session(session_id, **update_fields)
    if not updated:
        raise LookupError("session not found")
    payload = build_session_detail_response(
        session_store=session_store,
        store=store,
        session_id=session_id,
        environment_name=environment_name,
        worktree_root=worktree_root,
        heartbeat_runtime=heartbeat_runtime,
        infer_project_id_for_session=infer_project_id_for_session,
        apply_effective_primary_flags=apply_effective_primary_flags,
        decorate_session_display_fields=decorate_session_display_fields,
        build_session_detail_payload=build_session_detail_payload,
        apply_session_work_context=apply_session_work_context,
        build_project_session_runtime_index=build_project_session_runtime_index,
        build_session_runtime_state_for_row=build_session_runtime_state_for_row,
        load_session_heartbeat_config=load_session_heartbeat_config,
        heartbeat_summary_payload=heartbeat_summary_payload,
    )
    if payload is None:
        raise LookupError("session not found")
    return {"session": payload}


def delete_session_response(
    *,
    session_store: Any,
    session_id: str,
    session_binding_store: Any | None = None,
) -> dict[str, Any]:
    deleted = session_store.delete_session(session_id)
    if not deleted:
        raise LookupError("session not found")
    binding_deleted = False
    if session_binding_store is not None:
        try:
            binding_deleted = bool(session_binding_store.delete_binding(session_id))
        except Exception:
            binding_deleted = False
    return {
        "deleted": True,
        "soft_deleted": True,
        "binding_deleted": binding_deleted,
    }
