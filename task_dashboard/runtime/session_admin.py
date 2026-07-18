# -*- coding: utf-8 -*-

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from task_dashboard.claude_permissions import normalize_claude_permission_mode
from task_dashboard.codebuddy_permissions import normalize_codebuddy_permission_mode
from task_dashboard.runtime.execution_profiles import normalize_execution_profile
from task_dashboard.runtime.registry_refresh import schedule_registry_refresh, should_refresh_for_update
from task_dashboard.runtime.session_atomic_migration import (
    SessionMigrationError,
    project_migration_lock,
    rebuild_session_work_context_for_update,
    restore_affected_bindings,
    snapshot_affected_bindings,
    sync_cross_channel_bindings,
)
from task_dashboard.session_store import session_binding_is_available, session_binding_sort_key, session_context_is_exhausted
from task_dashboard.helpers import looks_like_session_id


class SessionIdentityError(ValueError):
    """Structured API error for manual Agent identity gates."""

    def __init__(self, error_code: str, message: str, *, payload: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.error_code = str(error_code or "session_identity_error")
        base = {"error": message, "error_code": self.error_code}
        if isinstance(payload, dict):
            base.update(payload)
        self.payload = base


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


def _cli_session_exists_for_attach(session_id: str, cli_type: str) -> bool:
    cli = str(cli_type or "codex").strip().lower() or "codex"
    sid = str(session_id or "").strip().lower()
    if not sid:
        return False
    if cli != "claude":
        return True
    try:
        from task_dashboard.adapters import get_adapter

        adapter_cls = get_adapter(cli)
        if adapter_cls is None:
            return False
        for row in adapter_cls.scan_sessions(after_ts=0.0):
            found = str(getattr(row, "session_id", "") or "").strip().lower()
            if found == sid:
                return True
    except Exception:
        return False
    return False


def _payload_has_codebuddy_permission_mode(payload: dict[str, Any]) -> bool:
    row = payload if isinstance(payload, dict) else {}
    if str(row.get("cli_type") or row.get("cliType") or "").strip().lower() == "claude":
        return False
    if "_codebuddy_permission_mode_explicit" in row:
        return bool(row.get("_codebuddy_permission_mode_explicit"))
    return "codebuddy_permission_mode" in row or "codebuddyPermissionMode" in row


def _payload_codebuddy_permission_mode(payload: dict[str, Any]) -> str:
    row = payload if isinstance(payload, dict) else {}
    raw = row.get("codebuddy_permission_mode") if "codebuddy_permission_mode" in row else row.get("codebuddyPermissionMode")
    return normalize_codebuddy_permission_mode(raw)


def _payload_has_claude_permission_mode(payload: dict[str, Any]) -> bool:
    row = payload if isinstance(payload, dict) else {}
    if "_claude_permission_mode_explicit" in row:
        return bool(row.get("_claude_permission_mode_explicit"))
    return (
        "claude_permission_mode" in row
        or "claudePermissionMode" in row
        or (
            str(row.get("cli_type") or row.get("cliType") or "").strip().lower() == "claude"
            and ("permission_mode" in row or "permissionMode" in row)
        )
    )


def _payload_claude_permission_mode(payload: dict[str, Any]) -> str:
    row = payload if isinstance(payload, dict) else {}
    raw = (
        row.get("claude_permission_mode")
        if "claude_permission_mode" in row
        else (
            row.get("claudePermissionMode")
            if "claudePermissionMode" in row
            else (row.get("permission_mode") if "permission_mode" in row else row.get("permissionMode"))
        )
    )
    return normalize_claude_permission_mode(raw)


def _payload_agent_name(payload: dict[str, Any]) -> str:
    row = payload if isinstance(payload, dict) else {}
    return str(row.get("agent_name") if "agent_name" in row else row.get("agentName") or "").strip()


def _canonical_alias(alias: Any, agent_name: Any = "") -> str:
    return str(alias or "").strip() or str(agent_name or "").strip()


def _session_store_base_dir(session_store: Any) -> Path:
    base = getattr(session_store, "base_dir", None)
    if base:
        return Path(base).expanduser().resolve()
    sessions_dir = getattr(session_store, "sessions_dir", None)
    if sessions_dir:
        return Path(sessions_dir).expanduser().resolve().parent
    return Path(".").resolve()


def _session_store_project_json(session_store: Any, project_id: str) -> Path:
    sessions_dir = getattr(session_store, "sessions_dir", None)
    base = Path(sessions_dir).expanduser().resolve() if sessions_dir else (_session_store_base_dir(session_store) / ".sessions")
    safe_id = str(project_id or "").strip().replace("/", "_").replace("\\", "_").replace("..", "_")
    return base / f"{safe_id}.json"


def _schedule_registry_refresh_best_effort(
    *,
    session_store: Any,
    project_id: str,
    reason: str,
    workspace_root: Any,
    session_id: str = "",
    channel_name: str = "",
    changed_fields: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    try:
        return schedule_registry_refresh(
            project_id=project_id,
            reason=reason,
            session_id=session_id,
            channel_name=channel_name,
            changed_fields=changed_fields,
            workspace_root=workspace_root,
            runtime_base_dir=_session_store_base_dir(session_store),
            session_json=_session_store_project_json(session_store, project_id),
        )
    except Exception as exc:
        return {
            "project_id": str(project_id or "").strip(),
            "state": "degraded",
            "scheduled": False,
            "degraded": True,
            "degraded_reason": "registry_refresh_schedule_failed",
            "error": str(exc)[:1000],
            "repair_items": [
                {
                    "code": "registry_refresh_retry",
                    "message": "SessionStore 已保存，通讯录刷新调度失败；后续同项目写入或显式刷新可补偿。",
                }
            ],
        }


def _session_identity_is_counted(session: Any) -> bool:
    row = session if isinstance(session, dict) else {}
    if not str(row.get("id") or "").strip() or bool(row.get("is_deleted")):
        return False
    status = str(row.get("status") or "active").strip().lower() or "active"
    if status != "active":
        return False
    if bool(row.get("context_exhausted") or row.get("contextExhausted")):
        return False
    binding_state = str(row.get("context_binding_state") or "").strip().lower()
    if binding_state in {"context_exhausted", "exhausted"}:
        return False
    return True


def _session_identity_conflict_payload(session: dict[str, Any]) -> dict[str, Any]:
    row = session if isinstance(session, dict) else {}
    return {
        "session_id": str(row.get("id") or "").strip(),
        "channel_name": str(row.get("channel_name") or "").strip(),
        "alias": str(row.get("alias") or "").strip(),
        "agent_name": str(row.get("agent_name") or row.get("agentName") or "").strip(),
        "status": str(row.get("status") or "").strip(),
        "is_primary": bool(row.get("is_primary")),
    }


def validate_session_identity_gate(
    session_store: Any,
    project_id: str,
    alias: Any,
    *,
    exclude_session_id: str = "",
    exclude_session_ids: list[str] | tuple[str, ...] | set[str] | None = None,
) -> str:
    """Require a non-empty project-unique alias for manual Agent creation paths."""

    effective_alias = str(alias or "").strip()
    if not effective_alias:
        raise SessionIdentityError(
            "alias_required",
            "alias is required for manual Agent creation or attach",
            payload={"project_id": str(project_id or "").strip()},
        )

    excluded = {str(exclude_session_id or "").strip()}
    excluded.update(str(item or "").strip() for item in (exclude_session_ids or []) if str(item or "").strip())
    excluded.discard("")
    try:
        sessions = session_store.list_sessions(str(project_id or "").strip(), include_deleted=True)
    except TypeError:
        sessions = session_store.list_sessions(str(project_id or "").strip())
    for session in sessions:
        row = session if isinstance(session, dict) else {}
        if str(row.get("id") or "").strip() in excluded:
            continue
        if not _session_identity_is_counted(row):
            continue
        if str(row.get("alias") or "").strip() != effective_alias:
            continue
        raise SessionIdentityError(
            "alias_conflict",
            "alias already exists in active sessions",
            payload={
                "project_id": str(project_id or "").strip(),
                "alias": effective_alias,
                "conflict": _session_identity_conflict_payload(row),
            },
        )
    return effective_alias


def _same_channel_rotation_sources(
    session_store: Any,
    project_id: str,
    channel_name: str,
    alias: Any,
) -> list[dict[str, Any]]:
    effective_alias = str(alias or "").strip()
    if not effective_alias:
        return []
    try:
        sessions = session_store.list_sessions(str(project_id or "").strip(), str(channel_name or "").strip(), include_deleted=True)
    except TypeError:
        sessions = session_store.list_sessions(str(project_id or "").strip(), str(channel_name or "").strip())
    sources: list[dict[str, Any]] = []
    for session in sessions:
        row = session if isinstance(session, dict) else {}
        if bool(row.get("is_deleted")):
            continue
        if str(row.get("alias") or row.get("agent_name") or row.get("agentName") or "").strip() != effective_alias:
            continue
        sources.append(row)
    sources.sort(key=session_binding_sort_key, reverse=True)
    return sources


def _context_exhausted_rotation_source(
    session_store: Any,
    project_id: str,
    channel_name: str,
) -> dict[str, Any] | None:
    try:
        sessions = session_store.list_sessions(str(project_id or "").strip(), str(channel_name or "").strip(), include_deleted=True)
    except TypeError:
        sessions = session_store.list_sessions(str(project_id or "").strip(), str(channel_name or "").strip())
    candidates: list[dict[str, Any]] = []
    for session in sessions:
        row = session if isinstance(session, dict) else {}
        if bool(row.get("is_deleted")):
            continue
        if not session_context_is_exhausted(row):
            continue
        if not str(row.get("alias") or row.get("agent_name") or row.get("agentName") or "").strip():
            continue
        candidates.append(row)
    candidates.sort(key=session_binding_sort_key, reverse=True)
    return candidates[0] if candidates else None


def _pick_reusable_session(
    sessions: list[dict[str, Any]],
    *,
    environment: str,
    worktree_root: str,
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
    resolve_channel_workdir: Callable[[str, str], Any] | None = None,
    ensure_static_instruction_files: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    project_id = str(payload.get("project_id") or "")
    channel_name = str(payload.get("channel_name") or "")
    mode = str(payload.get("mode") or "create_new").strip() or "create_new"
    requested_session_id = str(payload.get("session_id") or "").strip()
    cli_type = str(payload.get("cli_type") or "codex")
    model = str(payload.get("model") or "")
    reasoning_effort = str(payload.get("reasoning_effort") or "")
    codebuddy_permission_mode_explicit = _payload_has_codebuddy_permission_mode(payload)
    codebuddy_permission_mode = _payload_codebuddy_permission_mode(payload) if codebuddy_permission_mode_explicit else ""
    claude_permission_mode_explicit = _payload_has_claude_permission_mode(payload)
    claude_permission_mode = _payload_claude_permission_mode(payload) if claude_permission_mode_explicit else ""
    agent_name = str(payload.get("agent_name") or payload.get("agentName") or "").strip()
    alias = str(payload.get("alias") or "").strip() or agent_name
    requested_environment = str(payload.get("environment") or "").strip()
    environment = requested_environment or str(environment_name or "stable").strip() or "stable"
    requested_worktree_root = str(payload.get("worktree_root") or "").strip()
    requested_workdir = str(payload.get("workdir") or "").strip()
    requested_branch = str(payload.get("branch") or "").strip()
    session_role = str(payload.get("session_role") or "").strip()
    purpose = str(payload.get("purpose") or "").strip()
    reuse_strategy = _normalize_reuse_strategy(payload.get("reuse_strategy"))
    set_as_primary = payload.get("set_as_primary")
    first_message = str(payload.get("first_message") or "")
    if not project_id or not channel_name:
        raise ValueError("missing project_id or channel_name")
    if not project_exists(project_id):
        raise LookupError("project not found")
    if not channel_exists(project_id, channel_name):
        raise LookupError("channel not found")
    static_instruction_files: dict[str, Any] = {}
    if str(cli_type or "").strip().lower() == "codebuddy" and callable(ensure_static_instruction_files):
        static_instruction_files = ensure_static_instruction_files(
            project_id=project_id,
            channel_name=channel_name,
            cli_type=cli_type,
        ) or {}

    requested_context_seed = {
        "project_id": project_id,
        "channel_name": channel_name,
        "environment": requested_environment,
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
    resolved_workdir_text = ""
    if requested_workdir:
        resolved_workdir_text = _resolve_context_dir(requested_workdir, fallback_root=effective_worktree_root)
    elif callable(resolve_channel_workdir):
        try:
            resolved_workdir_text = _resolve_context_dir(
                resolve_channel_workdir(project_id, channel_name),
                fallback_root=effective_worktree_root,
            )
        except Exception:
            resolved_workdir_text = ""
    if not resolved_workdir_text:
        resolved_workdir_text = str(resolved_context_seed.get("workdir") or "").strip()
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
    rotation_source: dict[str, Any] | None = None
    if reuse_strategy == "rotate":
        rotation_source = _context_exhausted_rotation_source(session_store, project_id, channel_name)
        if rotation_source:
            alias = alias or str(rotation_source.get("alias") or rotation_source.get("agent_name") or "").strip()
            agent_name = agent_name or str(rotation_source.get("agent_name") or rotation_source.get("alias") or "").strip()
            purpose = purpose or str(rotation_source.get("purpose") or "").strip()
            if not session_role and bool(rotation_source.get("is_primary")):
                session_role = "primary"
    effective_primary = set_as_primary if isinstance(set_as_primary, bool) else (True if reuse_strategy == "rotate" else session_role == "primary")
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
        if not _cli_session_exists_for_attach(requested_session_id, cli_type):
            raise ValueError("claude session_id not found; create a new ClaudeCode Agent or attach a real Claude conversation id")
        existing_session = session_store.get_session(requested_session_id)
        existing_alias = str((existing_session or {}).get("alias") or "").strip()
        effective_alias = validate_session_identity_gate(
            session_store,
            project_id,
            alias or existing_alias,
            exclude_session_id=requested_session_id,
        )
        attached_session, imported = session_store.attach_existing_session(
            project_id=project_id,
            channel_name=channel_name,
            session_id=requested_session_id,
            cli_type=cli_type,
            alias=alias or ("" if existing_alias else effective_alias),
            agent_name=agent_name or (effective_alias if not existing_alias else ""),
            model=model,
            reasoning_effort=reasoning_effort,
            codebuddy_permission_mode=codebuddy_permission_mode if codebuddy_permission_mode_explicit else "",
            claude_permission_mode=claude_permission_mode if claude_permission_mode_explicit else "",
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
        registry_refresh = _schedule_registry_refresh_best_effort(
            session_store=session_store,
            project_id=project_id,
            reason="session_attach_existing" if imported else "session_attach_existing_update",
            workspace_root=worktree_root,
            session_id=requested_session_id,
            channel_name=channel_name,
            changed_fields=["alias", "agent_name", "channel_name", "is_primary"],
        )
        return {
            "session": attached_session,
            "sessionPath": "",
            "workdir": str(project_workdir),
            "created": False,
            "reused": False,
            "attached": True,
            "imported": bool(imported),
            "registry_refresh": registry_refresh,
            **({"static_instruction_files": static_instruction_files} if static_instruction_files else {}),
        }

    if reuse_strategy == "reuse_active":
        reusable = _pick_reusable_session(
            session_store.list_sessions(project_id, channel_name, include_deleted=True),
            environment=effective_environment,
            worktree_root=effective_worktree_root,
            cli_type=cli_type,
        )
        if reusable:
            effective_alias = validate_session_identity_gate(
                session_store,
                project_id,
                alias or reusable.get("alias") or "",
                exclude_session_id=str(reusable.get("id") or "").strip(),
            )
            update_fields: dict[str, Any] = {
                "last_used_at": reusable.get("last_used_at") or "",
                "reuse_strategy": reuse_strategy,
                "schema_version": "session.create.v2",
                "created_via": "api.create_session_v2.reuse",
                "context_binding_state": effective_binding_state,
            }
            if alias:
                update_fields["alias"] = effective_alias
            if agent_name:
                update_fields["agent_name"] = agent_name
            if model:
                update_fields["model"] = model
            if reasoning_effort:
                update_fields["reasoning_effort"] = reasoning_effort
            if codebuddy_permission_mode_explicit:
                update_fields["codebuddy_permission_mode"] = codebuddy_permission_mode
            if claude_permission_mode_explicit:
                update_fields["claude_permission_mode"] = claude_permission_mode
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
            registry_refresh = _schedule_registry_refresh_best_effort(
                session_store=session_store,
                project_id=project_id,
                reason="session_reuse_active",
                workspace_root=worktree_root,
                session_id=str(session.get("id") or reusable.get("id") or "").strip(),
                channel_name=channel_name,
                changed_fields=sorted(
                    set(update_fields.keys()).intersection(
                        {"alias", "agent_name", "channel_name", "is_primary", "is_deleted", "session_role"}
                    )
                ),
            )
            return {
                "session": session,
                "sessionPath": "",
                "workdir": str(project_workdir),
                "created": False,
                "reused": True,
                "registry_refresh": registry_refresh,
                **({"static_instruction_files": static_instruction_files} if static_instruction_files else {}),
            }

    rotation_sources: list[dict[str, Any]] = []
    rotation_replace_ids: list[str] = []
    if reuse_strategy == "rotate":
        rotation_sources = _same_channel_rotation_sources(session_store, project_id, channel_name, alias)
        rotation_source_name = (
            str((rotation_source or {}).get("alias") or (rotation_source or {}).get("agent_name") or "").strip()
            if rotation_source
            else ""
        )
        if rotation_source and rotation_source_name == str(alias or "").strip() and str(rotation_source.get("id") or "").strip() not in {
            str(item.get("id") or "").strip() for item in rotation_sources
        }:
            rotation_sources.append(rotation_source)
        rotation_replace_ids = [
            str(item.get("id") or "").strip()
            for item in rotation_sources
            if str(item.get("id") or "").strip()
        ]
    effective_alias = validate_session_identity_gate(
        session_store,
        project_id,
        alias,
        exclude_session_ids=rotation_replace_ids,
    )
    seed = build_session_seed_prompt(
        project_id=project_id,
        channel_name=channel_name,
        first_message=first_message,
        cli_type=cli_type,
    )
    create_result = create_cli_session(
        seed_prompt=seed,
        timeout_s=90,
        cli_type=cli_type,
        workdir=project_workdir,
        model=model,
        reasoning_effort=reasoning_effort,
        execution_profile=execution_profile,
        permission_mode=claude_permission_mode if str(cli_type or "").strip().lower() == "claude" else "",
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
    session_writer = session_store.rotate_session if reuse_strategy == "rotate" else session_store.create_session
    writer_kwargs: dict[str, Any] = {
        "project_id": project_id,
        "channel_name": channel_name,
        "cli_type": cli_type,
        "alias": effective_alias,
        "agent_name": agent_name or effective_alias,
        "session_id": recovered_session_id,
        "model": model,
        "reasoning_effort": reasoning_effort,
        "codebuddy_permission_mode": codebuddy_permission_mode if codebuddy_permission_mode_explicit else "default",
        "claude_permission_mode": claude_permission_mode if claude_permission_mode_explicit else "",
        "environment": effective_environment,
        "worktree_root": effective_worktree_root,
        "workdir": str(create_result.get("workdir", str(project_workdir)) or str(project_workdir)),
        "branch": branch,
        "session_role": session_role,
        "purpose": purpose,
        "reuse_strategy": reuse_strategy,
        "schema_version": "session.create.v2",
        "created_via": "api.create_session_v2",
        "context_binding_state": effective_binding_state,
        "project_execution_context": context_meta,
        "is_primary": effective_primary if isinstance(effective_primary, bool) else None,
    }
    if reuse_strategy == "rotate":
        writer_kwargs["replace_session_ids"] = rotation_replace_ids
        writer_kwargs["retire_reason"] = "session_rotate_alias_takeover"
    session = session_writer(**writer_kwargs)
    session = decorate_session_display_fields(session)
    session = apply_session_work_context(
        session,
        project_id=project_id,
        environment_name=effective_environment,
        worktree_root=effective_worktree_root,
    )
    registry_refresh = _schedule_registry_refresh_best_effort(
        session_store=session_store,
        project_id=project_id,
        reason="session_rotate_alias_takeover" if reuse_strategy == "rotate" else "session_create",
        workspace_root=worktree_root,
        session_id=str(session.get("id") or recovered_session_id or "").strip(),
        channel_name=channel_name,
        changed_fields=["alias", "agent_name", "channel_name", "is_primary", "is_deleted", "session_role"]
        if reuse_strategy == "rotate"
        else ["alias", "agent_name", "channel_name", "is_primary"],
    )
    return {
        "session": session,
        "sessionPath": create_result.get("sessionPath", ""),
        "workdir": create_result.get("workdir", str(project_workdir)),
        "created": True,
        "reused": False,
        **(
            {
                "rotated": True,
                "replaced_sessions": [_session_identity_conflict_payload(item) for item in rotation_sources],
                "replaced_session_ids": rotation_replace_ids,
                "rotation_summary": {
                    "state_transition": "old_sessions_soft_deleted_then_new_session_primary",
                    "retire_reason": "session_rotate_alias_takeover",
                    "rollback": "if CLI creation fails no SessionStore write is performed; if the atomic SessionStore write fails the old binding remains unchanged and the new CLI conversation is not registered",
                },
            }
            if reuse_strategy == "rotate"
            else {}
        ),
        "timeout_recovered": timeout_recovered,
        "create_warning": create_warning,
        "registry_refresh": registry_refresh,
        **({"static_instruction_files": static_instruction_files} if static_instruction_files else {}),
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
    workspace_root: Any = "",
) -> dict[str, Any]:
    result = session_store.manage_channel_sessions(
        project_id,
        channel_name,
        primary_session_id=primary_session_id,
        updates=updates,
    )
    sessions = decorate_sessions_display_fields(result.get("sessions") or [])
    registry_refresh = None
    if primary_session_id or updates:
        registry_refresh = _schedule_registry_refresh_best_effort(
            session_store=session_store,
            project_id=project_id,
            reason="channel_session_manage",
            workspace_root=workspace_root or Path(".").resolve(),
            session_id=str(primary_session_id or "").strip(),
            channel_name=channel_name,
            changed_fields=["is_primary", "is_deleted"],
        )
    return {
        "ok": True,
        "project_id": project_id,
        "channel_name": channel_name,
        "primary_session_id": result.get("primary_session_id") or "",
        "sessions": sessions,
        "count": len(sessions),
        **({"registry_refresh": registry_refresh} if registry_refresh else {}),
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
    session_binding_store: Any | None = None,
) -> dict[str, Any]:
    session = session_store.get_session(session_id)
    if not session:
        raise LookupError("session not found")
    project_id = str(session.get("project_id") or "").strip() or infer_project_id_for_session(store, session_id)
    if "agent_name" in update_fields and "alias" not in update_fields:
        agent_name_alias = str(update_fields.get("agent_name") or "").strip()
        if agent_name_alias:
            update_fields["alias"] = agent_name_alias
    if "alias" in update_fields:
        validate_session_identity_gate(
            session_store,
            project_id,
            update_fields.get("alias"),
            exclude_session_id=session_id,
        )
    if "is_primary" not in update_fields and "session_role" in update_fields:
        update_fields["is_primary"] = str(update_fields.get("session_role") or "").strip().lower() == "primary"
    if "is_primary" in update_fields:
        update_fields["session_role"] = "primary" if bool(update_fields.get("is_primary")) else "child"
    refresh_needed, refresh_changed_fields = should_refresh_for_update(session, update_fields)
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

    preview_payload = rebuild_session_work_context_for_update(
        session,
        update_fields,
        project_id=project_id,
        environment_name=environment_name,
        worktree_root=worktree_root,
        apply_session_work_context=apply_session_work_context,
    )
    preview_context = preview_payload.get("project_execution_context")
    if isinstance(preview_context, dict):
        update_fields["project_execution_context"] = preview_context
        update_fields["context_binding_state"] = _derive_context_binding_state(preview_context)

    if not update_fields:
        raise ValueError("no fields to update")

    old_channel_name = str(session.get("channel_name") or "").strip()
    new_channel_name = str(update_fields.get("channel_name") or old_channel_name).strip()
    cross_channel_migration = "channel_name" in update_fields and new_channel_name != old_channel_name
    if cross_channel_migration and not new_channel_name:
        raise ValueError("channel_name cannot be empty for session migration")
    if cross_channel_migration and session_binding_store is None:
        raise SessionMigrationError(
            "cross-channel migration requires session binding store",
            rollback_complete=True,
        )

    def _build_updated_payload() -> tuple[dict[str, Any], dict[str, Any]]:
        updated_row = session_store.update_session(session_id, **update_fields)
        if not updated_row:
            raise LookupError("session not found")
        detail = build_session_detail_response(
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
        if detail is None:
            raise LookupError("session not found")
        return updated_row, detail

    if cross_channel_migration:
        affected_channels = {old_channel_name, new_channel_name}
        with project_migration_lock(session_store, project_id):
            try:
                session_snapshots = session_store.snapshot_session_records(
                    project_id,
                    session_ids={session_id},
                    channel_names=affected_channels,
                )
                binding_snapshots = snapshot_affected_bindings(
                    session_binding_store,
                    project_id=project_id,
                    session_id=session_id,
                    channel_names=affected_channels,
                )
            except Exception as exc:
                raise SessionMigrationError(
                    "session migration preflight failed; no changes were written",
                    rollback_complete=True,
                    cause=exc,
                ) from exc
            try:
                updated = session_store.update_session(session_id, **update_fields)
                if not updated:
                    raise LookupError("session not found")
                sync_cross_channel_bindings(
                    session_binding_store,
                    session_store,
                    updated_session=updated,
                    old_channel_name=old_channel_name,
                )
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
            except Exception as exc:
                rollback_errors: list[str] = []
                try:
                    session_store.restore_session_records(project_id, session_snapshots)
                except Exception as rollback_exc:
                    rollback_errors.append(f"session_store: {rollback_exc}")
                try:
                    restore_affected_bindings(
                        session_binding_store,
                        binding_snapshots,
                        project_id=project_id,
                        session_id=session_id,
                        channel_names=affected_channels,
                    )
                except Exception as rollback_exc:
                    rollback_errors.append(f"session_binding: {rollback_exc}")
                rollback_complete = not rollback_errors
                message = "session migration failed and was rolled back"
                if rollback_errors:
                    message = "session migration failed and rollback was incomplete: " + "; ".join(rollback_errors)
                raise SessionMigrationError(
                    message,
                    rollback_complete=rollback_complete,
                    cause=exc,
                ) from exc
    else:
        updated, payload = _build_updated_payload()

    out = {"session": payload}
    if refresh_needed:
        out["registry_refresh"] = _schedule_registry_refresh_best_effort(
            session_store=session_store,
            project_id=project_id,
            reason="session_update_identity",
            workspace_root=worktree_root,
            session_id=session_id,
            channel_name=str(updated.get("channel_name") or session.get("channel_name") or "").strip(),
            changed_fields=refresh_changed_fields,
        )
    return out


def delete_session_response(
    *,
    session_store: Any,
    session_id: str,
    session_binding_store: Any | None = None,
    workspace_root: Any = "",
) -> dict[str, Any]:
    session = session_store.get_session(session_id)
    deleted = session_store.delete_session(session_id)
    if not deleted:
        raise LookupError("session not found")
    binding_deleted = False
    if session_binding_store is not None:
        try:
            binding_deleted = bool(session_binding_store.delete_binding(session_id))
        except Exception:
            binding_deleted = False
    project_id = str((session or {}).get("project_id") or "").strip()
    channel_name = str((session or {}).get("channel_name") or "").strip()
    registry_refresh = None
    if project_id:
        registry_refresh = _schedule_registry_refresh_best_effort(
            session_store=session_store,
            project_id=project_id,
            reason="session_delete",
            workspace_root=workspace_root or Path(".").resolve(),
            session_id=session_id,
            channel_name=channel_name,
            changed_fields=["is_deleted"],
        )
    return {
        "deleted": True,
        "soft_deleted": True,
        "binding_deleted": binding_deleted,
        **({"registry_refresh": registry_refresh} if registry_refresh else {}),
    }
