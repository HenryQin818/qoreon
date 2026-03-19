# -*- coding: utf-8 -*-

from __future__ import annotations

from typing import Any, Callable, Optional
from urllib.parse import parse_qs

from task_dashboard.runtime.project_execution_context import (
    build_project_execution_context,
    infer_project_execution_context_source,
)
from task_dashboard.runtime.run_detail_fields import (
    extract_agent_messages,
    extract_agent_messages_from_file,
    extract_business_refs_from_texts,
    extract_skills_used_from_texts,
    extract_terminal_message_from_file,
    extract_terminal_message_text,
    fallback_log_from_meta,
    normalize_business_refs_value,
    normalize_skills_used_value,
)


def _safe_text(value: Any, max_len: int) -> str:
    text = "" if value is None else str(value)
    if len(text) > max_len:
        return text[: max_len - 1] + "…"
    return text


def _normalize_claude_row_fields(store: Any, run_id: str, row: dict[str, Any]) -> bool:
    if str(row.get("cliType") or row.get("cli_type") or "").strip().lower() != "claude":
        return False
    changed = False
    preview = str(row.get("lastPreview") or "").strip()
    if not preview:
        preview = _safe_text(extract_terminal_message_from_file(store._paths(run_id)["log"], cli_type="claude"), 300)
        if preview:
            row["lastPreview"] = preview
            changed = True
    if int(row.get("agentMessagesCount") or 0) != 0:
        row["agentMessagesCount"] = 0
        changed = True
    if str(row.get("partialPreview") or "").strip():
        row["partialPreview"] = ""
        changed = True
    process_rows = row.get("processRows")
    if isinstance(process_rows, list) and process_rows:
        row["processRows"] = []
        changed = True
    process_rows_alt = row.get("process_rows")
    if isinstance(process_rows_alt, list) and process_rows_alt:
        row["process_rows"] = []
        changed = True
    return changed


def _align_run_runtime_identity(
    row: dict[str, Any],
    *,
    environment_name: str = "",
    local_server_origin: str = "",
    worktree_root: str = "",
) -> bool:
    changed = False
    target_environment = str(environment_name or "").strip()
    target_origin = str(local_server_origin or "").strip()
    target_worktree_root = str(worktree_root or "").strip()

    if target_environment and str(row.get("environment") or "").strip() != target_environment:
        row["environment"] = target_environment
        changed = True
    if target_origin and str(row.get("localServerOrigin") or "").strip() != target_origin:
        row["localServerOrigin"] = target_origin
        changed = True
    if target_worktree_root and str(row.get("worktree_root") or "").strip() != target_worktree_root:
        row["worktree_root"] = target_worktree_root
        changed = True
    return changed


def _attach_run_project_execution_context(
    row: dict[str, Any],
    *,
    project_id: str = "",
    channel_name: str = "",
    session_id: str = "",
) -> None:
    existing = row.get("project_execution_context")
    existing = existing if isinstance(existing, dict) else {}
    target = existing.get("target")
    if not isinstance(target, dict) or not target:
        target = {
            "project_id": str(project_id or row.get("projectId") or "").strip(),
            "channel_name": str(channel_name or row.get("channelName") or "").strip(),
            "session_id": str(session_id or row.get("sessionId") or "").strip(),
            "environment": str(row.get("environment") or "").strip(),
            "worktree_root": str(row.get("worktree_root") or "").strip(),
            "workdir": str(row.get("workdir") or "").strip(),
            "branch": str(row.get("branch") or "").strip(),
        }
    source = {
        "project_id": str(project_id or row.get("projectId") or "").strip(),
        "channel_name": str(channel_name or row.get("channelName") or "").strip(),
        "session_id": str(session_id or row.get("sessionId") or "").strip(),
        "environment": str(row.get("environment") or "").strip(),
        "worktree_root": str(row.get("worktree_root") or "").strip(),
        "workdir": str(row.get("workdir") or "").strip(),
        "branch": str(row.get("branch") or "").strip(),
    }
    row["project_execution_context"] = build_project_execution_context(
        target=target,
        source=source,
        context_source=infer_project_execution_context_source(
            stored_context_source=existing.get("context_source"),
        ),
    )


def list_runs_response(
    *,
    query_string: str,
    store: Any,
    scheduler: Any,
    maybe_trigger_restart_recovery_lazy: Callable[..., int],
    maybe_trigger_queued_recovery_lazy: Callable[..., int],
    build_run_observability_fields: Callable[..., dict[str, Any]],
    environment_name: str = "",
    local_server_origin: str = "",
    worktree_root: str = "",
) -> tuple[int, dict[str, Any]]:
    qs = parse_qs(query_string or "")
    channel_id = (qs.get("channelId") or [""])[0]
    project_id = (qs.get("projectId") or [""])[0]
    session_id = (qs.get("sessionId") or [""])[0]
    payload_mode = str((qs.get("payloadMode") or qs.get("payload_mode") or [""])[0] or "").strip().lower()
    include_payload_raw = str((qs.get("includePayload") or qs.get("include_payload") or [""])[0] or "").strip().lower()
    if payload_mode not in {"", "full", "light", "none"}:
        payload_mode = ""
    if not payload_mode and include_payload_raw:
        payload_mode = "full" if include_payload_raw in {"1", "true", "yes", "on"} else "none"
    if not payload_mode:
        payload_mode = "full"
    after_created_at = (qs.get("afterCreatedAt") or qs.get("after") or [""])[0]
    before_created_at = (qs.get("beforeCreatedAt") or qs.get("before") or [""])[0]
    limit_s = (qs.get("limit") or ["30"])[0]
    try:
        limit = max(1, min(200, int(limit_s)))
    except Exception:
        limit = 30
    runs = store.list_runs(
        channel_id=channel_id,
        project_id=project_id,
        session_id=session_id,
        limit=limit,
        after_created_at=after_created_at,
        before_created_at=before_created_at,
        payload_mode=payload_mode,
    )
    # Restart recovery remains handled by bootstrap/background paths.
    # Do not let read APIs mutate runtime state or enqueue recovery summaries,
    # otherwise an in-flight run can be misclassified during UI refresh.
    lazy_resumed = 0
    lazy_requeued = maybe_trigger_queued_recovery_lazy(
        store,
        scheduler,
        runs,
        project_id_hint=str(project_id or "").strip(),
    )
    if lazy_resumed > 0 or lazy_requeued > 0:
        runs = store.list_runs(
            channel_id=channel_id,
            project_id=project_id,
            session_id=session_id,
            limit=limit,
            after_created_at=after_created_at,
            before_created_at=before_created_at,
            payload_mode=payload_mode,
        )
    for row in runs:
        if not isinstance(row, dict):
            continue
        row.update(build_run_observability_fields(store, row, infer_blocked=False))
        run_id = str(row.get("id") or "").strip()
        changed = False
        if run_id:
            changed = _normalize_claude_row_fields(store, run_id, row) or changed
        changed = _align_run_runtime_identity(
            row,
            environment_name=environment_name,
            local_server_origin=local_server_origin,
            worktree_root=worktree_root,
        ) or changed
        _attach_run_project_execution_context(
            row,
            project_id=str(project_id or row.get("projectId") or "").strip(),
            channel_name=str(row.get("channelName") or "").strip(),
            session_id=str(row.get("sessionId") or "").strip(),
        )
        if changed and run_id:
            try:
                store.save_meta(run_id, row)
            except Exception:
                pass
    return 200, {"runs": runs, "payloadMode": payload_mode}


def get_run_detail_response(
    *,
    run_id: str,
    store: Any,
    scheduler: Any,
    maybe_trigger_restart_recovery_lazy: Callable[..., int],
    maybe_trigger_queued_recovery_lazy: Callable[..., int],
    build_run_observability_fields: Callable[..., dict[str, Any]],
    error_hint: Callable[[str], str],
) -> tuple[int, dict[str, Any]]:
    meta = store.load_meta(run_id)
    if not meta:
        return 404, {"error": "not found"}
    lazy_resumed = 0
    if lazy_resumed > 0:
        meta = store.load_meta(run_id) or meta
    lazy_requeued = maybe_trigger_queued_recovery_lazy(
        store,
        scheduler,
        [meta],
        project_id_hint=str(meta.get("projectId") or "").strip(),
    )
    if lazy_requeued > 0:
        meta = store.load_meta(run_id) or meta
    message = store.read_msg(run_id, limit_chars=300_000)
    last = store.read_last(run_id, limit_chars=500_000)
    log_tail = store.read_log(run_id, limit_chars=160_000)
    if not log_tail:
        log_tail = fallback_log_from_meta(meta)
    run_cli_type = str(meta.get("cliType") or "codex").strip() or "codex"
    if not str(last or "").strip():
        last_file = extract_terminal_message_from_file(store._paths(run_id)["log"], cli_type=run_cli_type)
        last_tail = extract_terminal_message_text(log_tail, cli_type=run_cli_type)
        last = last_file if len(last_file) >= len(last_tail) else last_tail
    agent_msgs_tail = extract_agent_messages(log_tail, max_items=200, cli_type=run_cli_type)
    agent_msgs_file = extract_agent_messages_from_file(store._paths(run_id)["log"], max_items=200, cli_type=run_cli_type)
    agent_msgs = agent_msgs_file if len(agent_msgs_file) >= len(agent_msgs_tail) else agent_msgs_tail
    partial = agent_msgs[-1] if agent_msgs else ""
    log_preview = _safe_text(log_tail.replace("\r\n", "\n").strip(), 420) if log_tail else ""
    meta_changed = False
    if log_preview and log_preview != str(meta.get("logPreview") or ""):
        meta["logPreview"] = log_preview
        meta_changed = True
    if run_cli_type == "claude":
        normalized_last = _safe_text(last, 300)
        if normalized_last and normalized_last != str(meta.get("lastPreview") or "").strip():
            meta["lastPreview"] = normalized_last
            meta_changed = True
        if int(meta.get("agentMessagesCount") or 0) != 0:
            meta["agentMessagesCount"] = 0
            meta_changed = True
        if str(meta.get("partialPreview") or "").strip():
            meta["partialPreview"] = ""
            meta_changed = True
        process_rows = meta.get("processRows")
        if isinstance(process_rows, list) and process_rows:
            meta["processRows"] = []
            meta_changed = True
        process_rows_alt = meta.get("process_rows")
        if isinstance(process_rows_alt, list) and process_rows_alt:
            meta["process_rows"] = []
            meta_changed = True
        agent_msgs = []
        partial = ""
    if agent_msgs:
        prev_count = int(meta.get("agentMessagesCount") or 0)
        if len(agent_msgs) != prev_count:
            meta["agentMessagesCount"] = len(agent_msgs)
            meta_changed = True
        partial_preview = _safe_text(partial, 300)
        if partial_preview and partial_preview != str(meta.get("partialPreview") or ""):
            meta["partialPreview"] = partial_preview
            meta_changed = True
    existing_skills = normalize_skills_used_value(meta.get("skills_used"), max_items=20)
    if existing_skills:
        meta["skills_used"] = existing_skills
    elif not isinstance(meta.get("skills_used"), list):
        skill_texts: list[str] = []
        if last:
            skill_texts.append(last)
        if partial:
            skill_texts.append(partial)
        skill_texts.extend(agent_msgs[-20:])
        meta["skills_used"] = extract_skills_used_from_texts(skill_texts, max_items=20)
    else:
        meta["skills_used"] = []
    existing_business_refs = normalize_business_refs_value(meta.get("business_refs"), max_items=24)
    if existing_business_refs:
        meta["business_refs"] = existing_business_refs
    if (not existing_business_refs) or (not isinstance(meta.get("business_refs"), list)):
        business_texts: list[str] = []
        if last:
            business_texts.append(last)
        if partial:
            business_texts.append(partial)
        parsed_business_refs = extract_business_refs_from_texts(business_texts, max_items=24)
        if parsed_business_refs:
            meta["business_refs"] = parsed_business_refs
        elif not isinstance(meta.get("business_refs"), list):
            meta["business_refs"] = []
    if meta_changed or isinstance(meta.get("skills_used"), list) or isinstance(meta.get("business_refs"), list):
        try:
            store.save_meta(run_id, meta)
        except Exception:
            pass
    meta.update(build_run_observability_fields(store, meta, infer_blocked=True))
    _attach_run_project_execution_context(
        meta,
        project_id=str(meta.get("projectId") or "").strip(),
        channel_name=str(meta.get("channelName") or "").strip(),
        session_id=str(meta.get("sessionId") or "").strip(),
    )
    hint = error_hint(str(meta.get("error") or ""))
    process_rows = meta.get("processRows") or meta.get("process_rows") or []
    if not isinstance(process_rows, list):
        process_rows = []
    return 200, {
        "run": meta,
        "message": message,
        "lastMessage": last,
        "logTail": log_tail,
        "logPreview": log_preview,
        "process": log_tail,
        "partialMessage": partial,
        "agentMessages": agent_msgs,
        "processRows": process_rows,
        "errorHint": hint,
    }


def perform_run_action_response(
    *,
    run_id: str,
    body: dict[str, Any],
    store: Any,
    scheduler: Any,
    run_process_registry: Any,
    audit_action: Callable[..., None],
    now_iso: Callable[[], str],
    require_scheduler_enabled: Callable[[], bool],
    dispatch_terminal_callback_for_run: Callable[..., None],
) -> tuple[int, dict[str, Any]]:
    if not run_id:
        audit_action(
            run_id="",
            action="",
            requested_action="",
            http_status=400,
            outcome="rejected",
            error="missing run id",
        )
        return 400, {"error": "missing run id"}
    action = str(body.get("action") or "").strip().lower()
    requested_action = action
    meta = store.load_meta(run_id)
    if not meta:
        audit_action(
            run_id=run_id,
            action=action,
            requested_action=requested_action,
            http_status=404,
            outcome="rejected",
            error="run not found",
        )
        return 404, {"error": "run not found"}
    status = str(meta.get("status") or "").strip().lower()
    if action == "cancel_edit":
        if status != "queued":
            audit_action(
                run_id=run_id,
                action=action,
                requested_action=requested_action,
                http_status=409,
                outcome="rejected",
                error="run is not queued",
                meta=meta,
            )
            return 409, {"error": "run is not queued", "status": status}
        session_id = str(meta.get("sessionId") or "").strip()
        removed = False
        if scheduler is not None and require_scheduler_enabled():
            removed = scheduler.cancel_queued_run(run_id, session_id=session_id)
        if not removed:
            meta2 = store.load_meta(run_id) or meta
            status2 = str(meta2.get("status") or "").strip().lower()
            if status2 != "queued":
                audit_action(
                    run_id=run_id,
                    action=action,
                    requested_action=requested_action,
                    http_status=409,
                    outcome="rejected",
                    error="run is no longer queued",
                    meta=meta2,
                )
                return 409, {"error": "run is no longer queued", "status": status2 or status}
            meta = meta2
            meta["queueDesynced"] = True
            meta["queueDesyncedAt"] = now_iso()
        message = store.read_msg(run_id)
        attachments = []
        raw_attachments = meta.get("attachments")
        if isinstance(raw_attachments, list):
            for att in raw_attachments:
                if not isinstance(att, dict):
                    continue
                attachments.append(
                    {
                        "filename": str(att.get("filename") or ""),
                        "originalName": str(att.get("originalName") or att.get("filename") or ""),
                        "url": str(att.get("url") or ""),
                    }
                )
        meta["hidden"] = True
        meta["cancelAction"] = "cancel_edit"
        meta["cancelledAt"] = now_iso()
        store.save_meta(run_id, meta)
        audit_action(
            run_id=run_id,
            action=action,
            requested_action=requested_action,
            http_status=200,
            outcome="accepted",
            meta=meta,
        )
        return 200, {
            "ok": True,
            "run": meta,
            "restored": {
                "message": message,
                "attachments": attachments,
            },
        }
    if action == "cancel_retry":
        if status not in {"retry_waiting", "queued"}:
            audit_action(
                run_id=run_id,
                action=action,
                requested_action=requested_action,
                http_status=409,
                outcome="rejected",
                error="run is not retry_waiting",
                meta=meta,
            )
            return 409, {"error": "run is not retry_waiting", "status": status}
        session_id = str(meta.get("sessionId") or "").strip()
        removed = False
        if scheduler is not None and require_scheduler_enabled():
            removed = scheduler.cancel_retry_waiting(run_id, session_id=session_id)
        if not removed:
            meta2 = store.load_meta(run_id) or meta
            status2 = str(meta2.get("status") or "").strip().lower()
            if status2 not in {"retry_waiting", "queued"}:
                audit_action(
                    run_id=run_id,
                    action=action,
                    requested_action=requested_action,
                    http_status=409,
                    outcome="rejected",
                    error="run is no longer retry_waiting",
                    meta=meta2,
                )
                return 409, {"error": "run is no longer retry_waiting", "status": status2 or status}
        meta["status"] = "done"
        meta["error"] = ""
        meta["retryCancelled"] = True
        meta["retryCancelledAt"] = now_iso()
        meta["cancelAction"] = "cancel_retry"
        meta["finishedAt"] = now_iso()
        store.save_meta(run_id, meta)
        try:
            dispatch_terminal_callback_for_run(store, run_id, scheduler=scheduler, meta=meta)
        except Exception:
            pass
        if scheduler is not None and session_id:
            try:
                scheduler.kick_session(session_id)
            except Exception:
                pass
        audit_action(
            run_id=run_id,
            action=action,
            requested_action=requested_action,
            http_status=200,
            outcome="accepted",
            meta=meta,
        )
        return 200, {"ok": True, "runId": run_id, "action": "cancel_retry", "run": meta}
    if action == "interrupt":
        if status != "running":
            audit_action(
                run_id=run_id,
                action=action,
                requested_action=requested_action,
                http_status=409,
                outcome="rejected",
                error="run is not running",
                meta=meta,
            )
            return 409, {"error": "run is not running", "status": status}
        tracked_before = run_process_registry.is_tracked(run_id)
        cli_type = str(meta.get("cliType") or "codex").strip() or "codex"
        ok = run_process_registry.request_interrupt(run_id, cli_type=cli_type)
        if not ok:
            audit_action(
                run_id=run_id,
                action=action,
                requested_action=requested_action,
                http_status=409,
                outcome="rejected",
                error="run is not interruptible",
                meta=meta,
            )
            return 409, {"error": "run is not interruptible", "status": status}
        meta2 = store.load_meta(run_id) or meta
        if str(meta2.get("status") or "").strip().lower() == "running":
            meta2["interruptRequestedAt"] = now_iso()
            meta2["interruptRequestedBy"] = "user"
            try:
                store.save_meta(run_id, meta2)
            except Exception:
                pass
        if not tracked_before:
            meta2 = store.load_meta(run_id) or meta2
            if str(meta2.get("status") or "").strip().lower() == "running":
                meta2["status"] = "error"
                meta2["error"] = "interrupted by user"
                meta2["finishedAt"] = now_iso()
                store.save_meta(run_id, meta2)
                try:
                    dispatch_terminal_callback_for_run(store, run_id, scheduler=scheduler, meta=meta2)
                except Exception:
                    pass
                session_id = str(meta2.get("sessionId") or "").strip()
                if scheduler is not None and session_id:
                    try:
                        scheduler.kick_session(session_id)
                    except Exception:
                        pass
        audit_action(
            run_id=run_id,
            action=action,
            requested_action=requested_action,
            http_status=200,
            outcome="accepted",
            meta=meta,
        )
        return 200, {"ok": True, "runId": run_id, "action": "interrupt"}
    audit_action(
        run_id=run_id,
        action=action,
        requested_action=requested_action,
        http_status=400,
        outcome="rejected",
        error="unknown action",
        meta=meta,
    )
    return 400, {"error": "unknown action"}
