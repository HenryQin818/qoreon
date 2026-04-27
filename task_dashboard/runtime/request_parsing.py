# -*- coding: utf-8 -*-

from __future__ import annotations

from typing import Any, Callable

from task_dashboard.runtime.execution_profiles import normalize_execution_profile
from task_dashboard.runtime.project_execution_context import (
    build_project_execution_context,
    diff_override_fields,
    infer_project_execution_context_source,
    merge_work_context_overrides,
)


def _safe_text_local(value: Any, max_len: int) -> str:
    text = "" if value is None else str(value)
    if len(text) > max_len:
        return text[: max_len - 1] + "…"
    return text


def _normalize_reasoning_effort_local(value: Any) -> str:
    txt = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if not txt:
        return ""
    alias = {
        "med": "medium",
        "normal": "medium",
        "default": "medium",
        "extra_high": "xhigh",
        "very_high": "xhigh",
        "ultra": "xhigh",
        "extra": "xhigh",
    }
    txt = alias.get(txt, txt)
    if txt in {"low", "medium", "high", "xhigh"}:
        return txt
    return ""


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


def _coerce_optional_bool_local(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    txt = str(value).strip().lower()
    if txt in {"1", "true", "yes", "on"}:
        return True
    if txt in {"0", "false", "no", "off"}:
        return False
    return None


def _coerce_int_local(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _normalize_execution_profile_local(value: Any) -> str:
    return normalize_execution_profile(_safe_text_local(value, 40), allow_empty=True)


def _normalize_session_role_local(value: Any) -> str:
    txt = _safe_text_local(value, 40).strip().lower().replace("-", "_").replace(" ", "_")
    if not txt:
        return ""
    alias = {
        "main": "primary",
        "master": "primary",
        "root": "primary",
        "sub": "child",
        "sub_session": "child",
        "secondary": "child",
        "child_session": "child",
    }
    txt = alias.get(txt, txt)
    if txt in {"primary", "child"}:
        return txt
    return ""


def _normalize_session_create_mode_local(value: Any) -> str:
    txt = _safe_text_local(value, 80).strip().lower().replace("-", "_").replace(" ", "_")
    if txt in {"attach", "attach_existing", "existing", "import_existing"}:
        return "attach_existing"
    return "create_new"


def parse_session_create_request(body: dict[str, Any]) -> dict[str, Any]:
    row = body if isinstance(body, dict) else {}
    set_as_primary = _coerce_optional_bool_local(
        row.get("set_as_primary") if "set_as_primary" in row else row.get("setAsPrimary")
    )
    reuse_strategy = _safe_text_local(
        row.get("reuse_strategy") if "reuse_strategy" in row else row.get("reuseStrategy"),
        80,
    ).strip()
    create_timeout_s = _coerce_int_local(
        row.get("create_timeout_s") if "create_timeout_s" in row else row.get("createTimeoutS"),
        0,
    )
    return {
        "mode": _normalize_session_create_mode_local(
            row.get("mode") if "mode" in row else row.get("createMode")
        ),
        "project_id": _safe_text_local(row.get("project_id"), 80).strip(),
        "channel_name": _safe_text_local(row.get("channel_name"), 200).strip(),
        "session_id": _safe_text_local(
            row.get("session_id")
            if "session_id" in row
            else (row.get("sessionId") if "sessionId" in row else row.get("existingSessionId")),
            80,
        ).strip(),
        "cli_type": _safe_text_local(row.get("cli_type"), 40).strip() or "codex",
        "model": _safe_text_local(row.get("model"), 120).strip(),
        "reasoning_effort": _normalize_reasoning_effort_local(
            row.get("reasoning_effort") if "reasoning_effort" in row else row.get("reasoningEffort")
        ),
        "alias": _safe_text_local(row.get("alias"), 200).strip(),
        "environment": _safe_text_local(
            row.get("environment") if "environment" in row else row.get("environmentName"),
            80,
        ).strip(),
        "worktree_root": _safe_text_local(
            row.get("worktree_root") if "worktree_root" in row else row.get("worktreeRoot"),
            4000,
        ).strip(),
        "workdir": _safe_text_local(row.get("workdir"), 4000).strip(),
        "branch": _safe_text_local(row.get("branch"), 240).strip(),
        "session_role": _normalize_session_role_local(
            row.get("session_role") if "session_role" in row else row.get("sessionRole")
        ),
        "purpose": _safe_text_local(row.get("purpose"), 200).strip(),
        "reuse_strategy": reuse_strategy or "reuse_active",
        "reuse_strategy_explicit": bool(reuse_strategy),
        "create_timeout_s": max(0, create_timeout_s),
        "set_as_primary": set_as_primary,
        "first_message": _safe_text_local(
            row.get("first_message") if "first_message" in row else row.get("firstMessage"),
            20_000,
        ).strip(),
    }


def parse_session_update_fields(body: dict[str, Any]) -> dict[str, Any]:
    row = body if isinstance(body, dict) else {}
    update_fields: dict[str, Any] = {}
    if "alias" in row:
        update_fields["alias"] = _safe_text_local(row.get("alias"), 200).strip()
    if "status" in row:
        update_fields["status"] = _safe_text_local(row.get("status"), 40).strip()
    if "channel_name" in row:
        update_fields["channel_name"] = _safe_text_local(row.get("channel_name"), 200).strip()
    if "cli_type" in row:
        update_fields["cli_type"] = _safe_text_local(row.get("cli_type"), 40).strip()
    if "model" in row:
        update_fields["model"] = _safe_text_local(row.get("model"), 120).strip()
    if "reasoning_effort" in row or "reasoningEffort" in row:
        update_fields["reasoning_effort"] = _normalize_reasoning_effort_local(
            row.get("reasoning_effort") if "reasoning_effort" in row else row.get("reasoningEffort")
        )
    if "environment" in row or "environmentName" in row:
        update_fields["environment"] = _safe_text_local(
            row.get("environment") if "environment" in row else row.get("environmentName"),
            80,
        ).strip()
    if "worktree_root" in row or "worktreeRoot" in row:
        update_fields["worktree_root"] = _safe_text_local(
            row.get("worktree_root") if "worktree_root" in row else row.get("worktreeRoot"),
            4000,
        ).strip()
    if "workdir" in row:
        update_fields["workdir"] = _safe_text_local(row.get("workdir"), 4000).strip()
    if "branch" in row:
        update_fields["branch"] = _safe_text_local(row.get("branch"), 240).strip()
    if "session_role" in row or "sessionRole" in row:
        update_fields["session_role"] = _normalize_session_role_local(
            row.get("session_role") if "session_role" in row else row.get("sessionRole")
        )
    if "purpose" in row:
        update_fields["purpose"] = _safe_text_local(row.get("purpose"), 200).strip()
    if "reuse_strategy" in row or "reuseStrategy" in row:
        update_fields["reuse_strategy"] = _safe_text_local(
            row.get("reuse_strategy") if "reuse_strategy" in row else row.get("reuseStrategy"),
            80,
        ).strip()
    if "set_as_primary" in row or "setAsPrimary" in row:
        update_fields["is_primary"] = _coerce_bool_local(
            row.get("set_as_primary") if "set_as_primary" in row else row.get("setAsPrimary"),
            False,
        )
    return update_fields


def parse_announce_request(
    body: dict[str, Any],
    *,
    extract_sender_fields: Callable[[dict[str, Any]], dict[str, str]],
    extract_run_extra_fields: Callable[[dict[str, Any]], dict[str, Any]],
    derive_session_work_context: Callable[..., dict[str, str]],
    coerce_bool: Callable[[Any, bool], bool],
    build_local_server_origin: Callable[[str, int], str],
    load_project_execution_context: Callable[..., dict[str, Any]] | None = None,
    session_data: dict[str, Any] | None,
    environment_name: str,
    worktree_root: Any,
    local_server_host: str,
    local_server_port: int,
    project_id_from_session: str = "",
) -> dict[str, Any]:
    row = body if isinstance(body, dict) else {}
    project_id = _safe_text_local(row.get("projectId"), 80).strip()
    if not project_id:
        project_id = str(project_id_from_session or "").strip()
    channel_name = _safe_text_local(row.get("channelName"), 200).strip()
    session_id = _safe_text_local(row.get("sessionId"), 80).strip()
    profile_label = _safe_text_local(row.get("profileLabel"), 80).strip()
    model = _safe_text_local(row.get("model"), 120).strip()
    reasoning_effort = _normalize_reasoning_effort_local(
        row.get("reasoning_effort") if "reasoning_effort" in row else row.get("reasoningEffort")
    )
    message = _safe_text_local(row.get("message"), 20_000).strip()
    sender_fields = extract_sender_fields(row)
    run_extra_fields = extract_run_extra_fields(row)
    target_ref = run_extra_fields.get("target_ref")
    if not isinstance(target_ref, dict):
        target_ref = {}
    if project_id and "project_id" not in target_ref:
        target_ref["project_id"] = project_id
    if channel_name and "channel_name" not in target_ref:
        target_ref["channel_name"] = channel_name
    if session_id and "session_id" not in target_ref:
        target_ref["session_id"] = session_id
    if target_ref:
        run_extra_fields["target_ref"] = target_ref
    requested_work_context = {
        "environment": _safe_text_local(
            row.get("environment") if "environment" in row else row.get("environmentName"),
            80,
        ).strip(),
        "worktree_root": _safe_text_local(
            row.get("worktree_root") if "worktree_root" in row else row.get("worktreeRoot"),
            4000,
        ).strip(),
        "workdir": _safe_text_local(row.get("workdir"), 4000).strip(),
        "branch": _safe_text_local(row.get("branch"), 240).strip(),
    }
    if "plan_first" in row or "planFirst" in row:
        run_extra_fields["plan_first"] = coerce_bool(
            row.get("plan_first") if "plan_first" in row else row.get("planFirst"),
            False,
        )
    if "plan_phase" in row or "planPhase" in row:
        run_extra_fields["plan_phase"] = _safe_text_local(
            row.get("plan_phase") if "plan_phase" in row else row.get("planPhase"),
            40,
        ).strip().lower()

    source_work_context: dict[str, Any] = {}
    if callable(load_project_execution_context) and project_id:
        try:
            source_work_context = load_project_execution_context(
                project_id=project_id,
                environment_name=environment_name,
                worktree_root=worktree_root,
            )
        except TypeError:
            source_work_context = load_project_execution_context(project_id) or {}
        except Exception:
            source_work_context = {}
    if not isinstance(source_work_context, dict):
        source_work_context = {}
    execution_profile = _normalize_execution_profile_local(source_work_context.get("profile")) or "sandboxed"
    effective_work_context = derive_session_work_context(
        session_data or {},
        project_id=project_id,
        environment_name=environment_name,
        worktree_root=worktree_root,
    )
    effective_work_context, request_override_fields, request_override_source = merge_work_context_overrides(
        effective_work_context,
        requested_work_context,
        override_source="request",
    )
    run_extra_fields.update(effective_work_context)
    run_extra_fields["execution_profile"] = execution_profile

    local_server_origin = build_local_server_origin(local_server_host, local_server_port)
    if local_server_origin and "localServerOrigin" not in run_extra_fields:
        run_extra_fields["localServerOrigin"] = local_server_origin

    context_target = {
        "project_id": project_id,
        "channel_name": channel_name,
        "session_id": session_id,
        **effective_work_context,
    }
    context_source = {
        "project_id": project_id,
        "channel_name": channel_name,
        **source_work_context,
    }
    override_source = request_override_source
    if not override_source and diff_override_fields(effective_work_context, context_source):
        override_source = "session"
    run_extra_fields["project_execution_context"] = build_project_execution_context(
        target=context_target,
        source=context_source,
        context_source=infer_project_execution_context_source(
            project_context=source_work_context,
        ),
        override_source=override_source,
    )
    # `/api/codex/announce` 是正式写入会话聊天区的入口，运行时直接写回可见性真源。
    run_extra_fields["visible_in_channel_chat"] = True

    return {
        "project_id": project_id,
        "channel_name": channel_name,
        "session_id": session_id,
        "profile_label": profile_label,
        "model": model,
        "reasoning_effort": reasoning_effort,
        "message": message,
        "sender_fields": sender_fields,
        "run_extra_fields": run_extra_fields,
    }
