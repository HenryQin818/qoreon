from __future__ import annotations

from typing import Any

from task_dashboard.runtime.request_parsing import parse_announce_request
from task_dashboard.runtime.scheduler_helpers import (
    _apply_plan_first_to_message,
    _enqueue_run_for_dispatch,
    _validate_announce_session_binding,
)


def send_project_onboarding_announce(payload: dict[str, Any], ctx: Any) -> dict[str, Any]:
    """Create the onboarding announce run through the same runtime path as /api/codex/announce."""
    body = payload if isinstance(payload, dict) else {}
    session_id = ctx.safe_text(body.get("sessionId"), 80).strip()
    session_data = ctx.session_store.get_session(session_id) if session_id else None
    cli_type = str((session_data or {}).get("cli_type") or body.get("cliType") or body.get("cli_type") or "codex").strip() or "codex"
    if session_data:
        ctx.session_store.touch_session(session_id)

    parsed = parse_announce_request(
        body,
        extract_sender_fields=ctx.extract_sender_fields,
        extract_run_extra_fields=ctx.extract_run_extra_fields,
        derive_session_work_context=ctx.derive_session_work_context,
        coerce_bool=ctx.coerce_bool,
        build_local_server_origin=ctx.build_local_server_origin,
        load_project_execution_context=ctx.load_project_execution_context,
        session_data=session_data,
        environment_name=ctx.environment_name,
        worktree_root=ctx.worktree_root,
        local_server_host="127.0.0.1",
        local_server_port=ctx.server_port,
        project_id_from_session=str((session_data or {}).get("project_id") or ""),
        resolve_channel_workdir=ctx.resolve_channel_workdir,
        resolve_project_workdir=ctx.resolve_project_workdir,
    )
    project_id = str(parsed.get("project_id") or "")
    channel_name = str(parsed.get("channel_name") or "")
    message = str(parsed.get("message") or "")
    sender_fields = parsed.get("sender_fields") if isinstance(parsed.get("sender_fields"), dict) else {}
    run_extra_fields = parsed.get("run_extra_fields") if isinstance(parsed.get("run_extra_fields"), dict) else {}

    if not project_id or not channel_name:
        return {"ok": False, "error": "missing projectId/channelName"}
    if not session_id or not ctx.looks_like_uuid(session_id):
        return {"ok": False, "error": "missing/invalid sessionId"}
    binding_reason = _validate_announce_session_binding(
        session_data,
        project_id=project_id,
        channel_name=channel_name,
    )
    if binding_reason:
        return {"ok": False, "error": binding_reason}
    if not message:
        return {"ok": False, "error": "missing message"}

    message, run_extra_fields = _apply_plan_first_to_message(message, run_extra_fields)
    run = ctx.store.create_run(
        project_id,
        channel_name,
        session_id,
        message,
        profile_label=str(parsed.get("profile_label") or ""),
        model=str(parsed.get("model") or (session_data or {}).get("model") or ""),
        cli_type=cli_type,
        sender_type=str(sender_fields.get("sender_type") or "system"),
        sender_id=str(sender_fields.get("sender_id") or "project_bootstrap_onboarding"),
        sender_name=str(sender_fields.get("sender_name") or "项目启动上岗门禁"),
        extra_meta=run_extra_fields,
        reasoning_effort=str(parsed.get("reasoning_effort") or (session_data or {}).get("reasoning_effort") or ""),
    )
    _enqueue_run_for_dispatch(
        ctx.store,
        str(run.get("id") or ""),
        session_id,
        cli_type,
        ctx.scheduler,
    )
    return {
        "ok": True,
        "run": run,
        "announce_run_id": str(run.get("id") or ""),
        "target_session_id": session_id,
        "visible_in_channel_chat": bool(run_extra_fields.get("visible_in_channel_chat")),
    }
