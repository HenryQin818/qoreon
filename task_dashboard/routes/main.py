# -*- coding: utf-8 -*-
"""
Route dispatcher for task dashboard server.

This module extracts the route dispatching logic from server.py into a separate module.
The routing pattern follows the existing HTTP method-based dispatch (do_GET, do_POST, etc.)
with URL path matching via if-elif chains.

Usage:
    from task_dashboard.routes import dispatch_get_request, dispatch_post_request

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if not dispatch_get_request(self, context):
                self._serve_static(static_root, urlparse(self.path).path)
"""

from __future__ import annotations

import json
import mimetypes
import os
import secrets
import subprocess
import threading
import time
from dataclasses import dataclass, field
from http import HTTPStatus
from pathlib import Path
from typing import Any, Callable, Optional, TYPE_CHECKING
from urllib.parse import parse_qs, urlencode, urlparse

from task_dashboard.runtime.request_parsing import (
    _normalize_reasoning_effort_local as _normalize_reasoning_effort,
    parse_announce_request as runtime_parse_announce_request,
    parse_session_create_request as runtime_parse_session_create_request,
    parse_session_update_fields as runtime_parse_session_update_fields,
)
from task_dashboard.helpers import atomic_write_text as runtime_atomic_write_text
from task_dashboard.runtime.channel_workflow import (
    build_channel_assist_message_payload as runtime_build_channel_assist_message_payload,
    build_channel_edit_request_message_payload as runtime_build_channel_edit_request_message_payload,
    normalize_channel_request_edit_request as runtime_normalize_channel_request_edit_request,
    normalize_channel_bootstrap_v3_request as runtime_normalize_channel_bootstrap_v3_request,
)
from task_dashboard.runtime.agent_candidates import (
    list_agent_candidates_response as runtime_list_agent_candidates_response,
)
from task_dashboard.runtime.channel_admin import (
    delete_channel as runtime_delete_channel,
    resolve_task_root_path as runtime_resolve_task_root_path,
)
from task_dashboard.runtime_identity import build_health_runtime_identity
from task_dashboard.runtime.project_execution_context import build_project_execution_context
from task_dashboard.runtime.project_admin import (
    bootstrap_project_response as runtime_bootstrap_project_response,
)
from task_dashboard.performance_diagnostics import build_runtime_perf_snapshot
from task_dashboard.runtime.execution_profiles import (
    normalize_execution_profile as runtime_normalize_execution_profile,
)
from task_dashboard.runtime.assist_request_registry import (
    auto_trigger_assist_request_response,
    close_assist_request_response,
    create_assist_request_response,
    reply_assist_request_response,
)
from task_dashboard.runtime.heartbeat_helpers import (
    _build_heartbeat_patch_with_tasks as runtime_build_heartbeat_patch_with_tasks,
)
from task_dashboard.runtime.heartbeat_registry import (
    _clear_dashboard_cfg_cache as runtime_clear_dashboard_cfg_cache,
    _change_task_status as runtime_change_task_status,
    _dispatch_task_status_auto_start as runtime_dispatch_task_status_auto_start,
    _evaluate_task_status_gate as runtime_evaluate_task_status_gate,
)
from task_dashboard.runtime.heartbeat_routes import (
    create_or_update_project_heartbeat_task_response,
    delete_project_heartbeat_task_response,
    run_or_delete_session_heartbeat_task_response,
    run_project_heartbeat_task_now_response,
)
from task_dashboard.runtime.scheduler_helpers import (
    _apply_plan_first_to_message as runtime_apply_plan_first_to_message,
    _build_session_binding_required_payload as runtime_build_session_binding_required_payload,
    _enqueue_run_for_dispatch as runtime_enqueue_run_for_dispatch,
    _validate_announce_session_binding as runtime_validate_announce_session_binding,
)
from task_dashboard.runtime.session_admin import (
    create_session_response as runtime_create_session_response,
    delete_binding_response as runtime_delete_binding_response,
    delete_session_response as runtime_delete_session_response,
    manage_channel_sessions_response as runtime_manage_channel_sessions_response,
    save_binding_response as runtime_save_binding_response,
    update_session_response as runtime_update_session_response,
)
from task_dashboard.runtime.session_routes import (
    dedup_session_channel_response as runtime_dedup_session_channel_response,
)
from task_dashboard.runtime.share_space import (
    build_share_announce_request as runtime_build_share_announce_request,
    build_share_bootstrap_response as runtime_build_share_bootstrap_response,
    build_share_session_response as runtime_build_share_session_response,
    load_project_share_space_config as runtime_load_project_share_space_config,
    update_project_share_space_config_response as runtime_update_project_share_space_config_response,
)
from task_dashboard.runtime.platform_lan_access import (
    build_state as runtime_build_platform_lan_access_state,
    update_response as runtime_update_platform_lan_access_response,
)
from task_dashboard.runtime.project_id_aliases import (
    canonicalize_runtime_project_id,
    rewrite_payload_project_id_fields,
)
from task_dashboard.runtime.task_assistant_runtime import (
    build_task_assistant_summary,
    delete_task_assistant_response,
    get_task_assistant_response,
    put_task_assistant_response,
    run_task_assistant_now_response,
)
from task_dashboard.runtime.session_task_tracking import build_session_task_tracking
from task_dashboard.runtime.task_plan_registry import (
    activate_task_plan_response,
    upsert_task_plan_response,
)
from task_dashboard.runtime.task_push_registry import (
    handle_task_push_action_response,
)
from task_dashboard.task_identity import runtime_base_dir_for_repo
from task_dashboard.task_cli import (
    create_task_from_payload as task_workflow_create_from_payload,
    validate_task_from_payload as task_workflow_validate_from_payload,
)

if TYPE_CHECKING:
    from http.server import BaseHTTPRequestHandler

    from task_dashboard.session_store import SessionStore
    from task_dashboard.run_store import RunStore
    from task_dashboard.runtime.heartbeat_registry import HeartbeatTaskRuntimeRegistry
    from task_dashboard.runtime.project_scheduler_registry import ProjectSchedulerRuntimeRegistry
    from task_dashboard.runtime.task_push_registry import TaskPushRuntimeRegistry
    from task_dashboard.runtime.task_plan_registry import TaskPlanRuntimeRegistry
    from task_dashboard.runtime.assist_request_registry import AssistRequestRuntimeRegistry


@dataclass
class RouteContext:
    """Context object passed to route handlers containing server state and helpers."""

    store: Any  # RunStore
    session_store: Any  # SessionStore
    session_binding_store: Any
    static_root: Path
    runs_dir: Path
    worktree_root: Path
    environment_name: str
    server_port: int
    scheduler: Optional[Any]
    project_scheduler_runtime: Optional[Any]
    heartbeat_runtime: Optional[Any]
    task_push_runtime: Optional[Any]
    task_plan_runtime: Optional[Any]
    assist_request_runtime: Optional[Any]
    conversation_memo_store: Optional[Any]
    allow_root: Path

    # Helper functions injected from server.py
    json_response: Callable[..., None] = field(repr=False)
    read_body_json: Callable[..., dict[str, Any]] = field(repr=False)
    require_token: Callable[[], bool] = field(repr=False)
    safe_text: Callable[[Any, int], str] = field(repr=False)
    coerce_bool: Callable[[Any, bool], bool] = field(repr=False)
    coerce_int: Callable[[Any, int], int] = field(repr=False)
    now_iso: Callable[[], str] = field(repr=False)
    looks_like_uuid: Callable[[str], bool] = field(repr=False)
    find_project_cfg: Callable[[str], Optional[dict]] = field(repr=False)

    # Additional helper functions
    server_token: Callable[[], str] = field(repr=False)
    repo_root: Callable[[], Path] = field(repr=False)

    # Runtime helpers for GET routes
    list_enabled_cli_types: Callable[[], list] = field(repr=False)
    runtime_list_sessions_response: Callable[..., tuple[int, dict[str, Any]]] = field(repr=False)
    runtime_list_runs_response: Callable[..., tuple[int, dict]] = field(repr=False)
    runtime_get_run_detail_response: Callable[..., tuple[int, dict]] = field(repr=False)
    runtime_list_channel_sessions_response: Callable[..., tuple[int, dict[str, Any]]] = field(repr=False)
    runtime_get_session_binding_response: Callable[..., tuple[int, dict[str, Any]]] = field(repr=False)
    runtime_list_session_heartbeat_task_history_route_response: Callable[..., tuple[int, dict[str, Any]]] = field(repr=False)
    maybe_trigger_restart_recovery_lazy: Callable[..., None] = field(repr=False)
    maybe_trigger_queued_recovery_lazy: Callable[..., None] = field(repr=False)
    build_run_observability_fields: Callable[..., dict] = field(repr=False)
    error_hint: Callable[..., str] = field(repr=False)
    perform_run_action_response: Callable[..., tuple[int, dict]] = field(repr=False)
    list_task_push_status_response: Callable[..., tuple[int, dict[str, Any]]] = field(repr=False)
    run_process_registry: Any = field(repr=False)
    append_run_action_audit: Callable[..., None] = field(repr=False)
    dispatch_terminal_callback_for_run: Callable[..., None] = field(repr=False)

    # Session/channel management helpers for POST routes
    create_cli_session: Callable[..., dict[str, Any]] = field(repr=False)
    resolve_project_workdir: Callable[[str], Path] = field(repr=False)
    detect_git_branch: Callable[[str], str] = field(repr=False)
    build_session_seed_prompt: Callable[..., str] = field(repr=False)
    decorate_session_display_fields: Callable[[dict[str, Any]], dict[str, Any]] = field(repr=False)
    decorate_sessions_display_fields: Callable[[list[dict[str, Any]]], list[dict[str, Any]]] = field(repr=False)
    apply_session_context_rows: Callable[..., list[dict[str, Any]]] = field(repr=False)
    derive_session_work_context: Callable[..., dict[str, str]] = field(repr=False)
    apply_session_work_context: Callable[..., dict[str, Any]] = field(repr=False)
    load_project_execution_context: Callable[..., dict[str, Any]] = field(repr=False)
    project_channel_exists: Callable[[str, str], bool] = field(repr=False)
    create_channel: Callable[[str, str, str, str], dict[str, Any]] = field(repr=False)
    run_codex_channel_bootstrap: Callable[..., tuple[int, dict[str, Any]]] = field(repr=False)
    infer_project_id_for_session: Callable[[Any, str], str] = field(repr=False)
    resolve_primary_target_by_channel: Callable[[str, str], Optional[dict[str, Any]]] = field(repr=False)
    resolve_channel_primary_session_id: Callable[[Any, str, str], str] = field(repr=False)
    session_context_write_requires_guard: Callable[[dict[str, Any], dict[str, Any]], bool] = field(repr=False)
    stable_write_ack_requested: Callable[[dict[str, Any]], bool] = field(repr=False)
    heartbeat_session_payload_for_write: Callable[..., dict[str, Any]] = field(repr=False)
    build_session_detail_response: Callable[..., dict[str, Any] | None] = field(repr=False)
    apply_effective_primary_flags: Callable[[Any, str, list[dict[str, Any]]], list[dict[str, Any]]] = field(repr=False)
    build_session_detail_payload: Callable[..., dict[str, Any]] = field(repr=False)
    build_project_session_runtime_index: Callable[[Any, str], dict[str, Any]] = field(repr=False)
    build_session_runtime_state_for_row: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]] = field(repr=False)
    attach_runtime_state_to_sessions: Callable[[Any, list[dict[str, Any]]], list[dict[str, Any]]] = field(repr=False)
    load_session_heartbeat_config: Callable[[dict[str, Any]], dict[str, Any]] = field(repr=False)
    heartbeat_summary_payload: Callable[[Any], Any] = field(repr=False)
    reveal_allowed_roots: Callable[[], list[Path]] = field(repr=False)
    upload_max_bytes: Callable[[], int] = field(repr=False)
    sanitize_upload_filename: Callable[[str], str] = field(repr=False)
    parse_multipart_single_file: Callable[[bytes, str], tuple[str, bytes, str]] = field(repr=False)
    rebuild_dashboard_static: Callable[[int], dict[str, Any]] = field(repr=False)
    read_task_dashboard_generated_at: Callable[[], str] = field(repr=False)
    set_runtime_max_concurrency_in_config: Callable[[int], Path] = field(repr=False)
    set_runtime_cli_bins_in_local_config: Callable[[dict[str, Any]], Path] = field(repr=False)
    communication_audit_scope_catalog: Callable[[Any], dict[str, dict[str, Any]]] = field(repr=False)
    parse_communication_audit_scopes: Callable[..., list[str]] = field(repr=False)
    get_communication_audit_summary: Callable[..., dict[str, Any]] = field(repr=False)
    communication_audit_cache_ttl_s: Callable[[], float] = field(repr=False)
    load_dashboard_cfg_current: Callable[[], dict[str, Any]] = field(repr=False)
    default_project_id_from_cfg: Callable[[dict[str, Any]], str] = field(repr=False)
    resolve_effective_max_concurrency: Callable[..., tuple[int, str]] = field(repr=False)
    resolve_scheduler_engine_enabled: Callable[[], tuple[bool, str]] = field(repr=False)
    collect_cli_tools_snapshot: Callable[..., dict[str, Any]] = field(repr=False)
    runtime_cfg_max_concurrency_from_cfg: Callable[[dict[str, Any]], int | None] = field(repr=False)
    with_local_config_enabled: Callable[[], bool] = field(repr=False)
    resolve_allowed_fs_path: Callable[[str], Path] = field(repr=False)
    relative_path_to_repo_root: Callable[[Path], str] = field(repr=False)
    fs_preview_dir_limit: int = field(repr=False)
    is_text_preview_path: Callable[[Path, str], bool] = field(repr=False)
    read_text_preview: Callable[..., tuple[str, bool]] = field(repr=False)
    preview_mode_for_path: Callable[[Path], str] = field(repr=False)
    build_global_resource_graph_payload: Callable[..., dict[str, Any]] = field(repr=False)
    list_project_heartbeat_tasks_response: Callable[..., tuple[int, dict[str, Any]]] = field(repr=False)
    get_project_heartbeat_task_response: Callable[..., tuple[int, dict[str, Any]]] = field(repr=False)
    list_project_heartbeat_task_history_response: Callable[..., tuple[int, dict[str, Any]]] = field(repr=False)
    list_session_heartbeat_task_history_response: Callable[..., tuple[int, dict[str, Any]]] = field(repr=False)
    normalize_heartbeat_task_id: Callable[..., str] = field(repr=False)
    heartbeat_task_history_limit: int = field(repr=False)
    build_runtime_bubbles_payload: Callable[..., dict[str, Any]] = field(repr=False)
    list_task_plans_response: Callable[..., tuple[int, dict[str, Any]]] = field(repr=False)
    list_assist_requests_response: Callable[..., tuple[int, dict[str, Any]]] = field(repr=False)
    get_assist_request_response: Callable[..., tuple[int, dict[str, Any]]] = field(repr=False)
    get_project_auto_scheduler_status_response: Callable[..., tuple[int, dict[str, Any]]] = field(repr=False)
    list_project_auto_inspection_tasks_response: Callable[..., tuple[int, dict[str, Any]]] = field(repr=False)
    list_project_inspection_records_response: Callable[..., tuple[int, dict[str, Any]]] = field(repr=False)
    build_project_scheduler_status: Callable[..., dict[str, Any]] = field(repr=False)
    ensure_auto_scheduler_status_shape: Callable[[dict[str, Any]], dict[str, Any]] = field(repr=False)
    get_project_config_response: Callable[..., tuple[int, dict[str, Any]]] = field(repr=False)
    attach_auto_inspection_candidate_preview: Callable[..., dict[str, Any]] = field(repr=False)
    config_toml_path: Callable[[], Path] = field(repr=False)
    config_local_toml_path: Callable[[], Path] = field(repr=False)
    load_project_auto_inspection_config: Callable[[str], dict[str, Any]] = field(repr=False)
    normalize_auto_inspection_tasks: Callable[..., list[dict[str, Any]]] = field(repr=False)
    normalize_inspection_task_id: Callable[..., str] = field(repr=False)
    normalize_inspection_records: Callable[..., list[dict[str, Any]]] = field(repr=False)
    auto_inspection_record_limit: int = field(repr=False)
    create_or_update_project_auto_inspection_task_response: Callable[..., tuple[int, dict[str, Any]]] = field(repr=False)
    delete_project_auto_inspection_task_response: Callable[..., tuple[int, dict[str, Any]]] = field(repr=False)
    set_project_auto_scheduler_enabled_response: Callable[..., tuple[int, dict[str, Any]]] = field(repr=False)
    build_default_auto_inspection_task: Callable[..., dict[str, Any]] = field(repr=False)
    normalize_inspection_targets: Callable[..., list[dict[str, Any]] | list[str]] = field(repr=False)
    normalize_auto_inspections: Callable[..., list[dict[str, Any]]] = field(repr=False)
    normalize_auto_inspection_task: Callable[..., dict[str, Any] | None] = field(repr=False)
    auto_inspection_tasks_for_write: Callable[[dict[str, Any], Any], list[dict[str, Any]]] = field(repr=False)
    build_auto_inspection_patch_with_tasks: Callable[..., dict[str, Any]] = field(repr=False)
    set_project_scheduler_contract_in_config: Callable[..., Any] = field(repr=False)
    set_project_scheduler_enabled_in_config: Callable[[str, bool], Any] = field(repr=False)
    update_project_config_response: Callable[..., tuple[int, dict[str, Any]]] = field(repr=False)
    clear_dashboard_cfg_cache: Callable[[], None] = field(repr=False)
    invalidate_sessions_payload_cache: Callable[..., None] = field(repr=False)
    load_project_scheduler_contract_config: Callable[[str], dict[str, Any]] = field(repr=False)
    load_project_auto_dispatch_config: Callable[[str], dict[str, Any]] = field(repr=False)
    load_project_heartbeat_config: Callable[[str], dict[str, Any]] = field(repr=False)
    normalize_auto_inspection_object: Callable[..., dict[str, Any] | None] = field(repr=False)
    auto_inspection_targets_from_objects: Callable[[list[dict[str, Any]]], list[str]] = field(repr=False)
    inspection_target_tokens: Callable[[Any], list[str]] = field(repr=False)
    inspection_target_set: set[str] = field(repr=False)
    normalize_heartbeat_task: Callable[..., dict[str, Any] | None] = field(repr=False)
    heartbeat_tasks_for_write: Callable[[Any], list[dict[str, Any]]] = field(repr=False)
    normalize_heartbeat_tasks: Callable[[Any], list[dict[str, Any]]] = field(repr=False)
    default_inspection_targets: list[str] = field(repr=False)
    extract_sender_fields: Callable[[dict[str, Any]], dict[str, str]] = field(repr=False)
    extract_run_extra_fields: Callable[[dict[str, Any]], dict[str, Any]] = field(repr=False)
    build_local_server_origin: Callable[[str, int], str] = field(repr=False)
    build_public_server_origin: Callable[[str, int], str] = field(repr=False)
    local_client_addresses: Callable[..., set[str]] = field(repr=False)
    resolve_attachment_local_path: Callable[[Path, Any], Optional[Path]] = field(repr=False)


def _truncate_reply_preview(text: Any, max_len: int = 1000) -> str:
    src = "" if text is None else str(text).strip()
    if len(src) <= max_len:
        return src
    return src[: max_len - 1] + "…"


def _hydrate_reply_to_fields_from_store(store: Any, run_extra_fields: dict[str, Any]) -> None:
    if not isinstance(run_extra_fields, dict):
        return
    reply_to_run_id = str(run_extra_fields.get("reply_to_run_id") or "").strip()
    if not reply_to_run_id:
        return
    need_preview = not str(run_extra_fields.get("reply_to_preview") or "").strip()
    need_sender = not str(run_extra_fields.get("reply_to_sender_name") or "").strip()
    need_created = not str(run_extra_fields.get("reply_to_created_at") or "").strip()
    if not (need_preview or need_sender or need_created):
        return
    load_meta = getattr(store, "load_meta", None)
    if not callable(load_meta):
        return
    try:
        source_meta = load_meta(reply_to_run_id)
    except Exception:
        source_meta = None
    if not isinstance(source_meta, dict):
        return

    assistant_preview = str(source_meta.get("lastPreview") or source_meta.get("partialPreview") or "").strip()
    user_preview = str(source_meta.get("messagePreview") or "").strip()
    preview_role = ""
    if need_preview:
        preview_text = ""
        if assistant_preview:
            preview_text = assistant_preview
            preview_role = "assistant"
        elif user_preview:
            preview_text = user_preview
            preview_role = "user"
        if preview_text:
            run_extra_fields["reply_to_preview"] = _truncate_reply_preview(preview_text)

    if need_sender:
        sender_name = ""
        if preview_role == "assistant":
            sender_name = str(
                source_meta.get("sender_name")
                or source_meta.get("senderName")
                or source_meta.get("source_agent_alias")
                or source_meta.get("sourceAgentAlias")
                or source_meta.get("channelName")
                or ""
            ).strip()
        else:
            sender_name = str(
                source_meta.get("sender_name")
                or source_meta.get("senderName")
                or source_meta.get("source_agent_alias")
                or source_meta.get("sourceAgentAlias")
                or source_meta.get("channelName")
                or ""
            ).strip()
        if sender_name:
            run_extra_fields["reply_to_sender_name"] = sender_name

    if need_created:
        created_at = str(source_meta.get("createdAt") or "").strip()
        if created_at:
            run_extra_fields["reply_to_created_at"] = created_at


class RouteDispatcher:
    """
    Route dispatcher that handles HTTP method routing for the task dashboard server.

    This class encapsulates the route matching and dispatching logic that was
    previously embedded in the Handler class's do_GET/do_POST/etc methods.
    """

    def __init__(self, context: RouteContext):
        self.ctx = context

    def _task_runtime_base_dir(self) -> Path:
        return runtime_base_dir_for_repo(self.ctx.worktree_root)

    def _alias_project_query_string(
        self,
        query_string: str,
        *,
        param_names: tuple[str, ...] = ("project_id", "projectId"),
    ) -> tuple[str, str]:
        qs = parse_qs(query_string or "", keep_blank_values=True)
        requested_project_id = ""
        for name in param_names:
            values = qs.get(name) or []
            if values:
                requested_project_id = str(values[0] or "").strip()
                if requested_project_id:
                    break
        canonical_project_id = canonicalize_runtime_project_id(requested_project_id)
        if requested_project_id and canonical_project_id and canonical_project_id != requested_project_id:
            for name in param_names:
                if name in qs:
                    qs[name] = [canonical_project_id]
            return urlencode(qs, doseq=True), requested_project_id
        return query_string, requested_project_id

    def _qs_first(
        self,
        qs: dict[str, list[str]],
        names: tuple[str, ...],
        *,
        max_len: int = 4000,
    ) -> str:
        for name in names:
            values = qs.get(name) or []
            if not values:
                continue
            value = self.ctx.safe_text(values[0], max_len).strip()
            if value:
                return value
        return ""

    def _share_project_id(self, qs: dict[str, list[str]], body: dict[str, Any] | None = None) -> str:
        if isinstance(body, dict):
            value = self.ctx.safe_text(
                body.get("project_id") if "project_id" in body else body.get("projectId"),
                160,
            ).strip()
            if value:
                return value
        return self._qs_first(qs, ("project_id", "projectId"), max_len=160)

    def _extract_share_credentials(
        self,
        handler: "BaseHTTPRequestHandler",
        qs: dict[str, list[str]],
        body: dict[str, Any] | None = None,
    ) -> tuple[str, str]:
        token = self._qs_first(qs, ("token", "access_token", "accessToken"), max_len=240)
        passcode = self._qs_first(qs, ("passcode",), max_len=120)
        if isinstance(body, dict):
            if not token:
                token = self.ctx.safe_text(
                    body.get("token") if "token" in body else body.get("access_token", body.get("accessToken")),
                    240,
                ).strip()
            if not passcode:
                passcode = self.ctx.safe_text(body.get("passcode"), 120).strip()
        if not token:
            token = self.ctx.safe_text(handler.headers.get("X-Share-Token"), 240).strip()
        if not token:
            auth = self.ctx.safe_text(handler.headers.get("Authorization"), 400).strip()
            if auth.lower().startswith("bearer "):
                token = auth[7:].strip()
        if not passcode:
            passcode = self.ctx.safe_text(handler.headers.get("X-Share-Passcode"), 120).strip()
        return token, passcode

    def _rewrite_alias_payload(
        self,
        payload: dict[str, Any],
        *,
        requested_project_id: str,
        row_keys: tuple[str, ...] = (),
        nested_row_keys: tuple[str, ...] = (),
    ) -> dict[str, Any]:
        requested = str(requested_project_id or "").strip()
        if not requested or not isinstance(payload, dict):
            return payload
        return rewrite_payload_project_id_fields(
            payload,
            project_id=requested,
            row_keys=row_keys,
            nested_row_keys=nested_row_keys,
        )

    def _attach_task_assistant_to_session_rows(
        self,
        payload: dict[str, Any],
        *,
        fallback_project_id: str = "",
    ) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return payload
        rows = payload.get("sessions")
        if not isinstance(rows, list) or not rows:
            return payload
        runtime_base_dir = self._task_runtime_base_dir()
        next_rows: list[dict[str, Any]] = []
        for raw in rows:
            row = dict(raw) if isinstance(raw, dict) else {}
            tracking = row.get("task_tracking") if isinstance(row.get("task_tracking"), dict) else None
            if tracking is None:
                project_id_for_tracking = canonicalize_runtime_project_id(
                    str(
                        row.get("project_id")
                        or row.get("projectId")
                        or payload.get("project_id")
                        or payload.get("projectId")
                        or fallback_project_id
                        or ""
                    ).strip()
                )
                session_id = str(row.get("id") or row.get("session_id") or "").strip()
                try:
                    tracking = build_session_task_tracking(
                        session=row,
                        store=self.ctx.store,
                        project_id=project_id_for_tracking,
                        session_id=session_id,
                        runtime_state=row.get("runtime_state") if isinstance(row.get("runtime_state"), dict) else {},
                    )
                except Exception:
                    tracking = None
            current_task_ref = (tracking.get("current_task_ref") or {}) if isinstance(tracking, dict) else {}
            if not isinstance(current_task_ref, dict):
                next_rows.append(row)
                continue
            task_id = str(current_task_ref.get("task_id") or "").strip()
            if not task_id:
                next_rows.append(row)
                continue
            project_id = canonicalize_runtime_project_id(
                str(
                    row.get("project_id")
                    or row.get("projectId")
                    or payload.get("project_id")
                    or payload.get("projectId")
                    or fallback_project_id
                    or ""
                ).strip()
            )
            if not project_id:
                next_rows.append(row)
                continue
            summary = build_task_assistant_summary(
                runtime_base_dir=runtime_base_dir,
                project_id=project_id,
                task_id=task_id,
                session_store=self.ctx.session_store,
                heartbeat_runtime=self.ctx.heartbeat_runtime,
            )
            next_tracking = dict(tracking or {})
            next_current = dict(current_task_ref)
            next_current["task_assistant"] = summary
            next_tracking["current_task_ref"] = next_current
            row["task_tracking"] = next_tracking
            next_rows.append(row)
        next_payload = dict(payload)
        next_payload["sessions"] = next_rows
        return next_payload

    def dispatch_head(self, handler: "BaseHTTPRequestHandler") -> bool:
        """
        Dispatch HEAD requests. Returns True if handled, False to fall through.
        """
        u = urlparse(handler.path)
        path = u.path

        # /__health - simple health check
        if path == "/__health":
            self.ctx.json_response(
                handler,
                200,
                {
                    "ok": True,
                    "environment": self.ctx.environment_name,
                    "port": self.ctx.server_port,
                },
                send_body=False,
            )
            return True

        # All other routes fall back to server.py
        return False

    def dispatch_get(self, handler: "BaseHTTPRequestHandler") -> bool:
        """
        Dispatch GET requests. Returns True if handled, False to fall through.
        """
        u = urlparse(handler.path)
        path = u.path
        qs = parse_qs(u.query or "")
        parts = [seg for seg in path.split("/") if seg]

        # /__health - health check with full details
        if path == "/__health":
            self._handle_health_get(handler)
            return True

        # /api/cli/types - list available CLI types
        if path == "/api/cli/types":
            self._handle_cli_types_get(handler)
            return True

        if path == "/api/runtime/lan-access":
            self._handle_platform_lan_access_get(handler)
            return True

        if path == "/api/runtime/perf-snapshot":
            self._handle_runtime_perf_snapshot_get(handler)
            return True

        if path == "/api/conversation-memos":
            self._handle_conversation_memos_get(handler, qs)
            return True

        if path == "/api/channel-sessions":
            self._handle_channel_sessions_get(handler, u.query or "")
            return True

        if path == "/api/agent-candidates":
            self._handle_agent_candidates_get(handler, u.query or "")
            return True

        if len(parts) == 4 and parts[:2] == ["api", "share-spaces"] and parts[3] == "bootstrap":
            self._handle_share_space_bootstrap_get(handler, parts[2], qs)
            return True

        if len(parts) == 5 and parts[:2] == ["api", "share-spaces"] and parts[3] == "sessions":
            self._handle_share_space_session_get(handler, parts[2], parts[4], qs)
            return True

        if path == "/api/sessions/bindings":
            self._handle_session_bindings_get(handler, qs)
            return True

        if path.startswith("/api/sessions/binding/") and path.count("/") == 4:
            self._handle_session_binding_get(handler, path)
            return True

        if (
            path.startswith("/api/sessions/")
            and "/heartbeat-tasks/" in path
            and path.endswith("/history")
        ):
            self._handle_session_heartbeat_history_get(handler, path, qs)
            return True

        if path == "/api/communication/audit":
            self._handle_communication_audit_get(handler, qs)
            return True

        if path == "/api/config/effective":
            self._handle_config_effective_get(handler, qs)
            return True

        if path == "/api/fs/read":
            self._handle_fs_read_get(handler, qs)
            return True

        if path == "/api/fs/open":
            self._handle_fs_open_get(handler, qs)
            return True

        if path == "/api/board/global-resource-graph":
            self._handle_global_resource_graph_get(handler, qs)
            return True

        if path == "/api/sessions":
            self._handle_sessions_list_get(handler, u.query or "")
            return True

        if len(parts) == 4 and parts[:2] == ["api", "tasks"] and parts[3] == "assistant-config":
            self._handle_task_assistant_get(handler, parts[2], qs)
            return True

        if path == "/api/codex/runs":
            self._handle_runs_list_get(handler, u.query or "")
            return True

        if path.startswith("/api/codex/run/"):
            self._handle_run_detail_get(handler, path)
            return True

        if self._dispatch_project_routes_get(handler, path, parts, qs):
            return True

        # All other routes fall back to server.py
        return False

    def dispatch_post(self, handler: "BaseHTTPRequestHandler") -> bool:
        """
        Dispatch POST requests. Returns True if handled, False to fall through.

        NOTE: Currently returns False for all routes to allow server.py fallback.
        This will be enabled incrementally as routes are migrated.
        """
        u = urlparse(handler.path)
        path = u.path
        qs = parse_qs(u.query or "")
        parts = [seg for seg in path.split("/") if seg]

        if path == "/api/sessions":
            self._handle_session_create_post(handler)
            return True

        if path == "/api/projects/bootstrap":
            self._handle_project_bootstrap_post(handler)
            return True

        if path == "/api/dashboard/rebuild":
            self._handle_dashboard_rebuild_post(handler)
            return True

        if path == "/api/dashboard/visibility-check":
            self._handle_visibility_check_post(handler)
            return True

        if path == "/api/config/global":
            self._handle_config_global_post(handler)
            return True

        if path == "/api/runtime/lan-access":
            self._handle_platform_lan_access_post(handler)
            return True

        if path == "/api/tasks/status":
            self._handle_task_status_post(handler)
            return True

        if path == "/api/codex/announce":
            self._handle_codex_announce_post(handler)
            return True

        if len(parts) == 4 and parts[:2] == ["api", "share-spaces"] and parts[3] == "announce":
            self._handle_share_space_announce_post(handler, parts[2], qs)
            return True

        if len(parts) == 5 and parts[:2] == ["api", "tasks"] and parts[3] == "assistant-config" and parts[4] == "run-now":
            self._handle_task_assistant_run_now_post(handler, parts[2])
            return True

        if (
            len(parts) == 6
            and parts[:2] == ["api", "sessions"]
            and parts[3] == "heartbeat-tasks"
            and parts[5] in {"run-now", "delete"}
        ):
            self._handle_session_heartbeat_task_action_post(handler, parts[2], parts[4], parts[5])
            return True

        if self._dispatch_project_routes_post(handler, path, parts):
            return True

        if path == "/api/sessions/dedup":
            self._handle_session_dedup_post(handler)
            return True

        if path == "/api/sessions/bindings/save":
            self._handle_binding_save_post(handler)
            return True

        if path == "/api/sessions/bindings/delete":
            self._handle_binding_delete_post(handler)
            return True

        if path == "/api/channel-sessions/manage":
            self._handle_channel_sessions_manage_post(handler)
            return True

        if path == "/api/codex/session/new":
            self._handle_session_new_post(handler)
            return True

        if path == "/api/channels/bootstrap-codex":
            self._handle_channel_bootstrap_post(handler)
            return True

        if path == "/api/channels/bootstrap-v3":
            self._handle_channel_bootstrap_v3_post(handler)
            return True

        if path == "/api/channels/request-edit":
            self._handle_channel_request_edit_post(handler)
            return True

        if path == "/api/channels/delete":
            self._handle_channel_delete_post(handler)
            return True

        if path == "/api/channels":
            self._handle_channel_create_post(handler)
            return True

        if path == "/api/fs/reveal":
            self._handle_fs_reveal_post(handler)
            return True

        if path == "/api/codex/upload":
            self._handle_upload_post(handler)
            return True

        if len(parts) == 5 and parts[:3] == ["api", "codex", "run"] and parts[4] == "action":
            self._handle_run_action_post(handler, parts)
            return True

        if path == "/api/conversation-memos":
            self._handle_conversation_memo_create_post(handler)
            return True

        if path == "/api/conversation-memos/delete":
            self._handle_conversation_memo_delete_post(handler)
            return True

        if path == "/api/conversation-memos/clear":
            self._handle_conversation_memo_clear_post(handler)
            return True

        # All other routes fall back to server.py for now
        return False

    def dispatch_put(self, handler: "BaseHTTPRequestHandler") -> bool:
        """
        Dispatch PUT requests. Returns True if handled, False to fall through.

        NOTE: Currently returns False for all routes to allow server.py fallback.
        This will be enabled incrementally as routes are migrated.
        """
        path = urlparse(handler.path).path
        parts = [seg for seg in path.split("/") if seg]
        if path.startswith("/api/sessions/") and path.count("/") == 3:
            self._handle_session_update_put(handler, path)
            return True

        if len(parts) == 4 and parts[:2] == ["api", "tasks"] and parts[3] == "assistant-config":
            self._handle_task_assistant_put(handler, parts[2])
            return True

        return False

    def dispatch_delete(self, handler: "BaseHTTPRequestHandler") -> bool:
        """
        Dispatch DELETE requests. Returns True if handled, False to fall through.

        NOTE: Currently returns False for all routes to allow server.py fallback.
        This will be enabled incrementally as routes are migrated.
        """
        path = urlparse(handler.path).path
        parts = [seg for seg in path.split("/") if seg]
        if path.startswith("/api/sessions/") and path.count("/") == 3:
            self._handle_session_delete(handler, path)
            return True

        if len(parts) == 4 and parts[:2] == ["api", "tasks"] and parts[3] == "assistant-config":
            self._handle_task_assistant_delete(handler, parts[2], parse_qs(urlparse(handler.path).query or ""))
            return True

        return False

    # -----------------------------------------------------------------------
    # HEAD request handlers
    # -----------------------------------------------------------------------

    def _handle_runs_head(self, handler: "BaseHTTPRequestHandler", path: str) -> bool:
        """Handle HEAD requests for .runs files."""
        # This is a simplified version - full implementation needs _resolve_runs_static_target
        return False  # Let server.py handle it

    def _handle_api_head(self, handler: "BaseHTTPRequestHandler", path: str) -> bool:
        """Handle HEAD requests for API endpoints."""
        known_paths = [
            "/api/codex/runs",
            "/api/communication/audit",
            "/api/cli/types",
            "/api/runtime/lan-access",
            "/api/runtime/perf-snapshot",
            "/api/board/global-resource-graph",
            "/api/conversation-memos",
        ]
        known_patterns = [
            lambda p: p.startswith("/api/codex/run/"),
            lambda p: p.startswith("/api/projects/") and p.endswith("/runtime-bubbles"),
            lambda p: p.startswith("/api/projects/") and "/auto-scheduler" in p,
        ]

        if path in known_paths or any(pattern(path) for pattern in known_patterns):
            handler.send_response(HTTPStatus.OK)
            handler.send_header("Content-Length", "0")
            handler.end_headers()
            return True

        return False

    # -----------------------------------------------------------------------
    # GET request handlers
    # -----------------------------------------------------------------------

    def _handle_health_get(self, handler: "BaseHTTPRequestHandler") -> None:
        """Handle GET /__health."""
        project_id = str(getattr(handler.server, "project_id", "") or "").strip()
        runtime_role = str(getattr(handler.server, "runtime_role", "") or "").strip()
        sessions_file = str(getattr(handler.server, "sessions_file", "") or "").strip()
        bind_host = ""
        try:
            bind_host = str(handler.server.server_address[0] or "").strip()
        except Exception:
            bind_host = ""
        runtime_identity = build_health_runtime_identity(
            project_id=project_id,
            runtime_role=runtime_role,
            environment=self.ctx.environment_name,
            port=self.ctx.server_port,
            bind_host=bind_host,
            local_origin=self.ctx.build_local_server_origin(bind_host, self.ctx.server_port),
            public_origin=self.ctx.build_public_server_origin(bind_host, self.ctx.server_port),
            runs_dir=self.ctx.runs_dir,
            sessions_file=sessions_file,
            static_root=self.ctx.static_root,
            worktree_root=self.ctx.worktree_root,
            config_path=self.ctx.config_toml_path(),
        )
        server_context = {
            "project_id": project_id,
            "environment": self.ctx.environment_name,
            "worktree_root": str(self.ctx.worktree_root),
        }
        self.ctx.json_response(
            handler,
            200,
            {
                "ok": True,
                **runtime_identity,
                "compat_shell": runtime_role == "compat_shell",
                "project_execution_context": build_project_execution_context(
                    target=server_context,
                    source=server_context,
                    context_source="server_runtime",
                ),
            },
        )

    def _current_bind_host(self, handler: "BaseHTTPRequestHandler") -> str:
        try:
            return str(handler.server.server_address[0] or "").strip()
        except Exception:
            return ""

    def _platform_lan_access_state(self, handler: "BaseHTTPRequestHandler") -> dict[str, Any]:
        bind_host = self._current_bind_host(handler)
        return runtime_build_platform_lan_access_state(
            runtime_base_dir=self.ctx.runs_dir.parent,
            current_bind=bind_host,
            port=self.ctx.server_port,
            local_origin=self.ctx.build_local_server_origin(bind_host, self.ctx.server_port),
            public_origin=self.ctx.build_public_server_origin(bind_host, self.ctx.server_port),
            local_addresses=self.ctx.local_client_addresses(),
        )

    def _handle_platform_lan_access_get(self, handler: "BaseHTTPRequestHandler") -> None:
        """Handle GET /api/runtime/lan-access."""
        self.ctx.json_response(handler, 200, self._platform_lan_access_state(handler))

    def _handle_platform_lan_access_post(self, handler: "BaseHTTPRequestHandler") -> None:
        """Handle POST /api/runtime/lan-access."""
        if not self.ctx.require_token():
            return
        try:
            body = self.ctx.read_body_json(handler, max_bytes=10_000)
        except Exception as e:
            self.ctx.json_response(handler, 400, {"ok": False, "error": f"bad json: {e}"})
            return
        bind_host = self._current_bind_host(handler)
        code, payload = runtime_update_platform_lan_access_response(
            runtime_base_dir=self.ctx.runs_dir.parent,
            payload=body,
            current_bind=bind_host,
            port=self.ctx.server_port,
            local_origin=self.ctx.build_local_server_origin(bind_host, self.ctx.server_port),
            public_origin=self.ctx.build_public_server_origin(bind_host, self.ctx.server_port),
            local_addresses=self.ctx.local_client_addresses(),
            updated_by="api:/api/runtime/lan-access",
        )
        self.ctx.json_response(handler, code, payload)

    def _handle_communication_audit_get(
        self, handler: "BaseHTTPRequestHandler", qs: dict[str, list[str]]
    ) -> None:
        """Handle GET /api/communication/audit."""
        catalog = self.ctx.communication_audit_scope_catalog(handler.server)
        scopes = self.ctx.parse_communication_audit_scopes(
            (qs.get("scopes") or [""])[0],
            allowed=set(catalog.keys()),
        )
        response_window_raw = self.ctx.safe_text(
            (qs.get("response_window_hours") or qs.get("responseWindowHours") or ["2"])[0],
            20,
        ).strip()
        top_limit_raw = self.ctx.safe_text(
            (qs.get("top_limit") or qs.get("topLimit") or ["8"])[0],
            20,
        ).strip()
        include_hidden = self.ctx.coerce_bool(
            (qs.get("include_hidden") or qs.get("includeHidden") or [""])[0],
            False,
        )
        try:
            response_window_hours = max(0.25, min(float(response_window_raw or "2"), 24.0))
        except Exception:
            response_window_hours = 2.0
        try:
            top_limit = max(3, min(int(top_limit_raw or "8"), 20))
        except Exception:
            top_limit = 8

        reports: dict[str, Any] = {}
        for scope in scopes:
            meta = catalog.get(scope) or {}
            reports[scope] = self.ctx.get_communication_audit_summary(
                scope=scope,
                label=str(meta.get("label") or scope),
                description=str(meta.get("description") or ""),
                runs_dirs=list(meta.get("runs_dirs") or []),
                response_window_hours=response_window_hours,
                top_limit=top_limit,
                include_hidden=include_hidden,
            )

        self.ctx.json_response(
            handler,
            200,
            {
                "ok": True,
                "generated_at": self.ctx.now_iso(),
                "environment": str(getattr(handler.server, "environment_name", "stable") or "stable"),
                "cache_ttl_seconds": self.ctx.communication_audit_cache_ttl_s(),
                "default_scopes": ["hot", "repo_flat"],
                "available_scopes": [
                    {
                        "id": key,
                        "label": str(val.get("label") or key),
                        "description": str(val.get("description") or ""),
                    }
                    for key, val in catalog.items()
                ],
                "reports": reports,
            },
        )

    def _handle_conversation_memos_get(
        self, handler: "BaseHTTPRequestHandler", qs: dict[str, list[str]]
    ) -> None:
        """Handle GET /api/conversation-memos."""
        project_id = self.ctx.safe_text(
            (qs.get("projectId") or qs.get("project_id") or [""])[0], 120
        ).strip()
        session_id = self.ctx.safe_text(
            (qs.get("sessionId") or qs.get("session_id") or [""])[0], 120
        ).strip()

        if not project_id:
            self.ctx.json_response(handler, 400, {"error": "missing projectId"})
            return
        if not session_id or not self.ctx.looks_like_uuid(session_id):
            self.ctx.json_response(handler, 400, {"error": "missing/invalid sessionId"})
            return

        # Use conversation memo store from context
        memo_store = self.ctx.conversation_memo_store
        if memo_store is None:
            self.ctx.json_response(handler, 500, {"error": "memo store not available"})
            return
        payload = memo_store.list(project_id, session_id)
        self.ctx.json_response(handler, 200, payload)

    def _handle_runs_get(self, handler: "BaseHTTPRequestHandler", path: str) -> bool:
        """Handle GET requests for .runs files."""
        # This needs full implementation with _resolve_runs_static_target
        return False  # Let server.py handle it

    def _handle_cli_types_get(self, handler: "BaseHTTPRequestHandler") -> None:
        """Handle GET /api/cli/types."""
        # Import at runtime to avoid circular imports
        from task_dashboard.adapters import list_enabled_cli_types

        types = list_enabled_cli_types()
        self.ctx.json_response(
            handler,
            200,
            {"types": [{"id": t.id, "name": t.name, "enabled": t.enabled} for t in types]},
        )

    def _handle_runtime_perf_snapshot_get(self, handler: "BaseHTTPRequestHandler") -> None:
        """Handle GET /api/runtime/perf-snapshot."""
        project_id = str(getattr(handler.server, "project_id", "") or "").strip()
        if not project_id:
            cfg = self.ctx.load_dashboard_cfg_current()
            project_id = self.ctx.default_project_id_from_cfg(cfg)

        http_log_value = getattr(handler.server, "http_log", None)
        http_log_path: Path | None = None
        if http_log_value:
            try:
                http_log_path = Path(str(http_log_value)).expanduser()
            except Exception:
                http_log_path = None

        payload = build_runtime_perf_snapshot(
            repo_root=self.ctx.worktree_root,
            environment_name=self.ctx.environment_name,
            port=self.ctx.server_port,
            project_id=project_id,
            http_log_path=http_log_path,
        )
        self.ctx.json_response(handler, 200, payload)

    def _handle_config_effective_get(
        self, handler: "BaseHTTPRequestHandler", qs: dict[str, list[str]]
    ) -> None:
        """Handle GET /api/config/effective."""
        cfg = self.ctx.load_dashboard_cfg_current()
        project_id = self.ctx.safe_text(
            (qs.get("project_id") or qs.get("projectId") or [""])[0],
            120,
        ).strip()
        if not project_id:
            project_id = self.ctx.default_project_id_from_cfg(cfg)
        if not project_id or not self.ctx.find_project_cfg(project_id):
            self.ctx.json_response(handler, 404, {"error": "project not found"})
            return

        status = (
            self.ctx.project_scheduler_runtime.get_status(project_id)
            if self.ctx.project_scheduler_runtime is not None
            else self.ctx.build_project_scheduler_status(self.ctx.store, project_id)
        )
        status = self.ctx.ensure_auto_scheduler_status_shape(status)
        cfg_project = self.ctx.load_project_scheduler_contract_config(project_id)
        auto_dispatch_cfg = self.ctx.load_project_auto_dispatch_config(project_id)
        auto_inspection_cfg = self.ctx.load_project_auto_inspection_config(project_id)
        heartbeat_cfg = self.ctx.load_project_heartbeat_config(project_id)
        max_cc, max_cc_source = self.ctx.resolve_effective_max_concurrency(cfg=cfg)
        scheduler_engine_enabled, scheduler_engine_source = self.ctx.resolve_scheduler_engine_enabled()
        cli_tools = self.ctx.collect_cli_tools_snapshot(cfg, session_store=self.ctx.session_store)
        bind_host = ""
        try:
            bind_host = str(handler.server.server_address[0] or "")
        except Exception:
            bind_host = ""

        self.ctx.json_response(
            handler,
            200,
            {
                "global": {
                        "max_concurrency": int(max_cc),
                        "max_concurrency_source": max_cc_source,
                        "configured_max_concurrency": self.ctx.runtime_cfg_max_concurrency_from_cfg(cfg),
                        "scheduler_engine_enabled": bool(scheduler_engine_enabled),
                        "scheduler_engine_source": scheduler_engine_source,
                        "token_required": bool(self.ctx.server_token()),
                        "with_local_config": self.ctx.with_local_config_enabled(),
                        "bind": bind_host,
                        "cli_bins_config_path": str(self.ctx.config_local_toml_path()),
                        "cli_tools": cli_tools,
                    "limits": {"max_concurrency": {"min": 1, "max": 32}},
                },
                "project": {
                    "project_id": project_id,
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
                        "inspection_targets": self.ctx.normalize_inspection_targets(
                            auto_inspection_cfg.get("inspection_targets"),
                            default=self.ctx.default_inspection_targets if bool(auto_inspection_cfg.get("enabled")) else [],
                        ),
                        "auto_inspections": self.ctx.normalize_auto_inspections(
                            auto_inspection_cfg.get("auto_inspections"),
                            fallback_targets=self.ctx.normalize_inspection_targets(
                                auto_inspection_cfg.get("inspection_targets"),
                                default=self.ctx.default_inspection_targets if bool(auto_inspection_cfg.get("enabled")) else [],
                            ),
                        ),
                        "inspection_tasks": self.ctx.normalize_auto_inspection_tasks(
                            auto_inspection_cfg.get("inspection_tasks"),
                            has_explicit_field=True,
                        ),
                        "active_inspection_task_id": str(auto_inspection_cfg.get("active_inspection_task_id") or ""),
                        "ready": bool(auto_inspection_cfg.get("ready")),
                        "errors": list(auto_inspection_cfg.get("errors") or []),
                    },
                    "heartbeat": {
                        "enabled": bool(heartbeat_cfg.get("enabled")),
                        "scan_interval_seconds": int(heartbeat_cfg.get("scan_interval_seconds") or 30),
                        "tasks": self.ctx.normalize_heartbeat_tasks(heartbeat_cfg.get("tasks")),
                        "ready": bool(heartbeat_cfg.get("ready")),
                        "errors": list(heartbeat_cfg.get("errors") or []),
                    },
                    "status": status or {},
                },
            },
        )

    def _handle_fs_read_get(
        self, handler: "BaseHTTPRequestHandler", qs: dict[str, list[str]]
    ) -> None:
        """Handle GET /api/fs/read."""
        path_raw = self.ctx.safe_text((qs.get("path") or [""])[0], 4000).strip()
        if not path_raw:
            self.ctx.json_response(handler, 400, {"error": "missing path"})
            return
        try:
            pr = self.ctx.resolve_allowed_fs_path(path_raw)
        except FileNotFoundError:
            self.ctx.json_response(handler, 404, {"error": "path not found"})
            return
        except PermissionError:
            self.ctx.json_response(handler, 403, {"error": "path not allowed"})
            return
        except ValueError as exc:
            self.ctx.json_response(handler, 400, {"error": str(exc)})
            return
        except Exception as exc:
            self.ctx.json_response(handler, 500, {"error": f"resolve path failed: {exc}"})
            return

        try:
            repo_rel = self.ctx.relative_path_to_repo_root(pr)
            if pr.is_dir():
                entries_all = sorted(
                    pr.iterdir(),
                    key=lambda item: (not item.is_dir(), item.name.lower()),
                )
                entries = []
                for child in entries_all[: self.ctx.fs_preview_dir_limit]:
                    child_is_dir = child.is_dir()
                    child_rel = self.ctx.relative_path_to_repo_root(child)
                    child_mime_type = "inode/directory"
                    if not child_is_dir:
                        child_mime_type = str(mimetypes.guess_type(child.name)[0] or "application/octet-stream")
                    entries.append(
                        {
                            "name": child.name,
                            "kind": "dir" if child_is_dir else "file",
                            "path": str(child),
                            "relative_path": child_rel,
                            "extension": "" if child_is_dir else str(child.suffix or "").lower(),
                            "mime_type": child_mime_type,
                            "is_image": bool((not child_is_dir) and child_mime_type.startswith("image/")),
                        }
                    )
                self.ctx.json_response(
                    handler,
                    200,
                    {
                        "ok": True,
                        "item": {
                            "kind": "dir",
                            "path": str(pr),
                            "relative_path": repo_rel,
                            "name": pr.name or str(pr),
                            "entries": entries,
                            "entry_count": len(entries_all),
                            "truncated": len(entries_all) > self.ctx.fs_preview_dir_limit,
                        },
                    },
                )
                return

            mime_type = str(mimetypes.guess_type(pr.name)[0] or "application/octet-stream")
            is_text = self.ctx.is_text_preview_path(pr, mime_type)
            is_image = mime_type.startswith("image/")
            content = ""
            truncated = False
            if is_text:
                content, truncated = self.ctx.read_text_preview(pr)
            stat = pr.stat()
            self.ctx.json_response(
                handler,
                200,
                {
                    "ok": True,
                    "item": {
                        "kind": "file",
                        "path": str(pr),
                        "relative_path": repo_rel,
                        "name": pr.name,
                        "extension": str(pr.suffix or "").lower(),
                        "mime_type": mime_type,
                        "size": int(stat.st_size),
                        "is_text": bool(is_text),
                        "is_image": bool(is_image),
                        "preview_mode": self.ctx.preview_mode_for_path(pr),
                        "content": content,
                        "truncated": bool(truncated),
                    },
                },
            )
        except Exception as exc:
            self.ctx.json_response(handler, 500, {"error": f"read path failed: {exc}"})

    def _handle_fs_open_get(
        self, handler: "BaseHTTPRequestHandler", qs: dict[str, list[str]]
    ) -> None:
        """Handle GET /api/fs/open."""
        path_raw = self.ctx.safe_text((qs.get("path") or [""])[0], 4000).strip()
        if not path_raw:
            self.ctx.json_response(handler, 400, {"error": "missing path"})
            return
        try:
            pr = self.ctx.resolve_allowed_fs_path(path_raw)
        except FileNotFoundError:
            self.ctx.json_response(handler, 404, {"error": "path not found"})
            return
        except PermissionError:
            self.ctx.json_response(handler, 403, {"error": "path not allowed"})
            return
        except ValueError as exc:
            self.ctx.json_response(handler, 400, {"error": str(exc)})
            return
        except Exception as exc:
            self.ctx.json_response(handler, 500, {"error": f"resolve path failed: {exc}"})
            return

        if pr.is_dir():
            self.ctx.json_response(handler, 400, {"error": "directory open not supported"})
            return

        mime_type = str(mimetypes.guess_type(pr.name)[0] or "application/octet-stream")
        if mime_type.startswith("text/") and "charset=" not in mime_type.lower():
            mime_type = f"{mime_type}; charset=utf-8"
        try:
            stat = pr.stat()
            handler.send_response(HTTPStatus.OK)
            handler.send_header("Content-Type", mime_type)
            handler.send_header("Content-Length", str(int(stat.st_size)))
            handler.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
            handler.send_header("Pragma", "no-cache")
            handler.send_header("Expires", "0")
            handler.end_headers()
            with pr.open("rb") as fh:
                while True:
                    chunk = fh.read(64 * 1024)
                    if not chunk:
                        break
                    handler.wfile.write(chunk)
        except BrokenPipeError:
            return
        except Exception as exc:
            self.ctx.json_response(handler, 500, {"error": f"open path failed: {exc}"})

    def _handle_global_resource_graph_get(
        self, handler: "BaseHTTPRequestHandler", qs: dict[str, list[str]]
    ) -> None:
        """Handle GET /api/board/global-resource-graph."""
        project_id = self.ctx.safe_text(
            (qs.get("project_id") or qs.get("projectId") or [""])[0],
            120,
        ).strip()
        channel_name = self.ctx.safe_text(
            (qs.get("channel_name") or qs.get("channelName") or [""])[0],
            240,
        ).strip()
        run_limit_s = self.ctx.safe_text(
            (qs.get("run_limit") or qs.get("runLimit") or ["600"])[0],
            20,
        ).strip()
        try:
            run_limit = max(50, min(5000, int(run_limit_s)))
        except Exception:
            run_limit = 600
        if project_id and not self.ctx.find_project_cfg(project_id):
            self.ctx.json_response(handler, 404, {"error": "project not found"})
            return
        try:
            payload = self.ctx.build_global_resource_graph_payload(
                store=self.ctx.store,
                session_store=self.ctx.session_store,
                project_id=project_id,
                channel_name=channel_name,
                run_limit=run_limit,
            )
        except Exception as exc:
            self.ctx.json_response(
                handler,
                500,
                {"error": "global resource graph build failed", "message": str(exc)},
            )
            return
        self.ctx.json_response(handler, 200, payload)

    def _dispatch_project_routes_get(
        self,
        handler: "BaseHTTPRequestHandler",
        path: str,
        parts: list[str],
        qs: dict[str, list[str]],
    ) -> bool:
        """Dispatch project-related GET routes."""
        if len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "heartbeat-tasks":
            self._handle_project_heartbeat_tasks_get(handler, parts[2])
            return True

        if len(parts) == 5 and parts[:2] == ["api", "projects"] and parts[3] == "heartbeat-tasks":
            self._handle_project_heartbeat_task_get(handler, parts[2], parts[4])
            return True

        if (
            len(parts) == 6
            and parts[:2] == ["api", "projects"]
            and parts[3] == "heartbeat-tasks"
            and parts[5] == "history"
        ):
            self._handle_project_heartbeat_task_history_get(handler, parts[2], parts[4], qs)
            return True

        if len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "runtime-bubbles":
            self._handle_project_runtime_bubbles_get(handler, parts[2], qs)
            return True

        if len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "task-push":
            self._handle_project_task_push_get(handler, parts[2], handler.path)
            return True

        if len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "task-plans":
            self._handle_project_task_plans_get(handler, parts[2], handler.path)
            return True

        if len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "assist-requests":
            self._handle_project_assist_requests_get(handler, parts[2], handler.path)
            return True

        if len(parts) == 5 and parts[:2] == ["api", "projects"] and parts[3] == "assist-requests":
            self._handle_project_assist_request_get(handler, parts[2], parts[4])
            return True

        if len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "auto-scheduler":
            self._handle_project_auto_scheduler_get(handler, parts[2])
            return True

        if len(parts) == 5 and parts[:2] == ["api", "projects"] and parts[3] == "auto-scheduler" and parts[4] == "inspection-tasks":
            self._handle_project_inspection_tasks_get(handler, parts[2])
            return True

        if len(parts) == 5 and parts[:2] == ["api", "projects"] and parts[3] == "auto-scheduler" and parts[4] == "inspection-records":
            self._handle_project_inspection_records_get(handler, parts[2], handler.path)
            return True
        if len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "config":
            self._handle_project_config_get(handler, parts[2])
            return True

        return False

    def _handle_project_heartbeat_tasks_get(
        self,
        handler: "BaseHTTPRequestHandler",
        project_id: str,
    ) -> None:
        """Handle GET /api/projects/{project_id}/heartbeat-tasks."""
        code, payload = self.ctx.list_project_heartbeat_tasks_response(
            project_id=project_id,
            find_project_cfg=self.ctx.find_project_cfg,
            heartbeat_runtime=self.ctx.heartbeat_runtime,
        )
        self.ctx.json_response(handler, code, payload)

    def _handle_project_heartbeat_task_get(
        self,
        handler: "BaseHTTPRequestHandler",
        project_id: str,
        task_id: str,
    ) -> None:
        """Handle GET /api/projects/{project_id}/heartbeat-tasks/{task_id}."""
        code, payload = self.ctx.get_project_heartbeat_task_response(
            project_id=project_id,
            heartbeat_task_id=self.ctx.normalize_heartbeat_task_id(task_id, default=""),
            find_project_cfg=self.ctx.find_project_cfg,
            heartbeat_runtime=self.ctx.heartbeat_runtime,
        )
        self.ctx.json_response(handler, code, payload)

    def _handle_project_heartbeat_task_history_get(
        self,
        handler: "BaseHTTPRequestHandler",
        project_id: str,
        task_id: str,
        qs: dict[str, list[str]],
    ) -> None:
        """Handle GET /api/projects/{project_id}/heartbeat-tasks/{task_id}/history."""
        limit_s = self.ctx.safe_text((qs.get("limit") or ["20"])[0], 20).strip()
        try:
            limit = max(1, min(self.ctx.heartbeat_task_history_limit, int(limit_s)))
        except Exception:
            limit = 20
        code, payload = self.ctx.list_project_heartbeat_task_history_response(
            project_id=project_id,
            heartbeat_task_id=self.ctx.normalize_heartbeat_task_id(task_id, default=""),
            limit=limit,
            find_project_cfg=self.ctx.find_project_cfg,
            heartbeat_runtime=self.ctx.heartbeat_runtime,
        )
        self.ctx.json_response(handler, code, payload)

    def _handle_project_runtime_bubbles_get(
        self,
        handler: "BaseHTTPRequestHandler",
        project_id: str,
        qs: dict[str, list[str]],
    ) -> None:
        """Handle GET /api/projects/{project_id}/runtime-bubbles."""
        pid = str(project_id or "").strip()
        if not pid:
            self.ctx.json_response(handler, 400, {"error": "missing project_id"})
            return
        if not self.ctx.find_project_cfg(pid):
            self.ctx.json_response(handler, 404, {"error": "project not found"})
            return
        channel_name = self.ctx.safe_text((qs.get("channel_name") or qs.get("channelName") or [""])[0], 240).strip()
        session_id = self.ctx.safe_text((qs.get("session_id") or qs.get("sessionId") or [""])[0], 120).strip()
        limit_s = self.ctx.safe_text((qs.get("limit") or ["80"])[0], 20).strip()
        bubble_limit_s = self.ctx.safe_text((qs.get("bubble_limit") or qs.get("bubbleLimit") or ["40"])[0], 20).strip()
        object_limit_s = self.ctx.safe_text((qs.get("object_limit") or qs.get("objectLimit") or ["2"])[0], 20).strip()
        try:
            limit = int(limit_s)
        except Exception:
            limit = 80
        try:
            bubble_limit = int(bubble_limit_s)
        except Exception:
            bubble_limit = 40
        try:
            object_limit = int(object_limit_s)
        except Exception:
            object_limit = 2
        payload = self.ctx.build_runtime_bubbles_payload(
            self.ctx.store,
            pid,
            session_store=self.ctx.session_store,
            channel_name=channel_name,
            session_id=session_id,
            limit=limit,
            bubble_limit=bubble_limit,
            max_related_objects=object_limit,
        )
        self.ctx.json_response(handler, 200, payload)

    def _handle_project_task_plans_get(
        self,
        handler: "BaseHTTPRequestHandler",
        project_id: str,
        raw_path: str,
    ) -> None:
        """Handle GET /api/projects/{project_id}/task-plans."""
        code, payload = self.ctx.list_task_plans_response(
            project_id=str(project_id or "").strip(),
            query_string=urlparse(raw_path).query or "",
            task_plan_runtime=self.ctx.task_plan_runtime,
            find_project_cfg=self.ctx.find_project_cfg,
        )
        self.ctx.json_response(handler, code, payload)

    def _handle_project_task_push_get(
        self,
        handler: "BaseHTTPRequestHandler",
        project_id: str,
        raw_path: str,
    ) -> None:
        """Handle GET /api/projects/{project_id}/task-push."""
        pid = str(project_id or "").strip()
        if not pid:
            self.ctx.json_response(handler, 400, {"error": "missing project_id"})
            return
        if not self.ctx.find_project_cfg(pid):
            self.ctx.json_response(handler, 404, {"error": "project not found"})
            return
        if self.ctx.task_push_runtime is None:
            self.ctx.json_response(handler, 503, {"error": "task push runtime unavailable"})
            return
        code, payload = self.ctx.list_task_push_status_response(
            project_id=pid,
            query_string=urlparse(raw_path).query or "",
            task_push_runtime=self.ctx.task_push_runtime,
            safe_text=self.ctx.safe_text,
        )
        self.ctx.json_response(handler, code, payload)

    def _handle_project_assist_requests_get(
        self,
        handler: "BaseHTTPRequestHandler",
        project_id: str,
        raw_path: str,
    ) -> None:
        """Handle GET /api/projects/{project_id}/assist-requests."""
        code, payload = self.ctx.list_assist_requests_response(
            project_id=str(project_id or "").strip(),
            query_string=urlparse(raw_path).query or "",
            assist_runtime=self.ctx.assist_request_runtime,
            find_project_cfg=self.ctx.find_project_cfg,
        )
        self.ctx.json_response(handler, code, payload)

    def _handle_project_assist_request_get(
        self,
        handler: "BaseHTTPRequestHandler",
        project_id: str,
        request_id: str,
    ) -> None:
        """Handle GET /api/projects/{project_id}/assist-requests/{request_id}."""
        code, payload = self.ctx.get_assist_request_response(
            project_id=str(project_id or "").strip(),
            request_id=str(request_id or "").strip(),
            assist_runtime=self.ctx.assist_request_runtime,
            find_project_cfg=self.ctx.find_project_cfg,
        )
        self.ctx.json_response(handler, code, payload)

    def _handle_project_auto_scheduler_get(
        self,
        handler: "BaseHTTPRequestHandler",
        project_id: str,
    ) -> None:
        """Handle GET /api/projects/{project_id}/auto-scheduler."""
        code, payload = self.ctx.get_project_auto_scheduler_status_response(
            project_id=project_id,
            store=self.ctx.store,
            find_project_cfg=self.ctx.find_project_cfg,
            project_scheduler_runtime=self.ctx.project_scheduler_runtime,
            build_project_scheduler_status=self.ctx.build_project_scheduler_status,
            ensure_auto_scheduler_status_shape=self.ctx.ensure_auto_scheduler_status_shape,
            attach_auto_inspection_candidate_preview=self.ctx.attach_auto_inspection_candidate_preview,
        )
        self.ctx.json_response(handler, code, payload)

    def _project_config_response_with_share_space(
        self,
        project_id: str,
    ) -> tuple[int, dict[str, Any]]:
        code, payload = self.ctx.get_project_config_response(
            project_id=project_id,
            store=self.ctx.store,
            find_project_cfg=self.ctx.find_project_cfg,
            load_project_scheduler_contract_config=self.ctx.load_project_scheduler_contract_config,
            load_project_auto_dispatch_config=self.ctx.load_project_auto_dispatch_config,
            load_project_auto_inspection_config=self.ctx.load_project_auto_inspection_config,
            load_project_heartbeat_config=self.ctx.load_project_heartbeat_config,
            build_project_scheduler_status=self.ctx.build_project_scheduler_status,
            ensure_auto_scheduler_status_shape=self.ctx.ensure_auto_scheduler_status_shape,
            project_scheduler_runtime=self.ctx.project_scheduler_runtime,
            heartbeat_runtime=self.ctx.heartbeat_runtime,
            normalize_inspection_targets=self.ctx.normalize_inspection_targets,
            normalize_auto_inspections=self.ctx.normalize_auto_inspections,
            normalize_auto_inspection_tasks=self.ctx.normalize_auto_inspection_tasks,
            normalize_heartbeat_tasks=self.ctx.normalize_heartbeat_tasks,
            default_inspection_targets=self.ctx.default_inspection_targets,
            config_path_getter=self.ctx.config_toml_path,
        )
        if code == 200 and isinstance(payload, dict):
            response_project_id = str(payload.get("project_id") or project_id)
            project = payload.get("project")
            if not isinstance(project, dict):
                project = {}
                payload["project"] = project
            project["share_space"] = runtime_load_project_share_space_config(
                worktree_root=self.ctx.worktree_root,
                environment_name=self.ctx.environment_name,
                project_id=response_project_id,
            )
        return code, payload

    def _update_project_config_response_without_share_space(
        self,
        project_id: str,
        body: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        return self.ctx.update_project_config_response(
            project_id=project_id,
            body=body,
            find_project_cfg=self.ctx.find_project_cfg,
            safe_text=self.ctx.safe_text,
            coerce_bool=self.ctx.coerce_bool,
            looks_like_uuid=self.ctx.looks_like_uuid,
            load_project_scheduler_contract_config=self.ctx.load_project_scheduler_contract_config,
            load_project_auto_dispatch_config=self.ctx.load_project_auto_dispatch_config,
            load_project_auto_inspection_config=self.ctx.load_project_auto_inspection_config,
            load_project_heartbeat_config=self.ctx.load_project_heartbeat_config,
            build_default_auto_inspection_task=self.ctx.build_default_auto_inspection_task,
            normalize_inspection_targets=self.ctx.normalize_inspection_targets,
            normalize_auto_inspections=self.ctx.normalize_auto_inspections,
            normalize_auto_inspection_task=self.ctx.normalize_auto_inspection_task,
            normalize_auto_inspection_tasks=self.ctx.normalize_auto_inspection_tasks,
            normalize_auto_inspection_object=self.ctx.normalize_auto_inspection_object,
            auto_inspection_targets_from_objects=self.ctx.auto_inspection_targets_from_objects,
            inspection_target_tokens=self.ctx.inspection_target_tokens,
            inspection_target_set=self.ctx.inspection_target_set,
            build_auto_inspection_patch_with_tasks=self.ctx.build_auto_inspection_patch_with_tasks,
            normalize_inspection_task_id=self.ctx.normalize_inspection_task_id,
            heartbeat_tasks_for_write=self.ctx.heartbeat_tasks_for_write,
            normalize_heartbeat_task=self.ctx.normalize_heartbeat_task,
            normalize_heartbeat_tasks=self.ctx.normalize_heartbeat_tasks,
            set_project_scheduler_contract_in_config=self.ctx.set_project_scheduler_contract_in_config,
            build_project_scheduler_status=self.ctx.build_project_scheduler_status,
            ensure_auto_scheduler_status_shape=self.ctx.ensure_auto_scheduler_status_shape,
            project_scheduler_runtime=self.ctx.project_scheduler_runtime,
            heartbeat_runtime=self.ctx.heartbeat_runtime,
            store=self.ctx.store,
            default_inspection_targets=self.ctx.default_inspection_targets,
            clear_dashboard_cfg_cache=self.ctx.clear_dashboard_cfg_cache,
            invalidate_sessions_payload_cache=self.ctx.invalidate_sessions_payload_cache,
        )

    def _handle_project_config_get(
        self,
        handler: "BaseHTTPRequestHandler",
        project_id: str,
    ) -> None:
        """Handle GET /api/projects/{project_id}/config."""
        code, payload = self._project_config_response_with_share_space(project_id)
        self.ctx.json_response(handler, code, payload)

    def _handle_project_inspection_tasks_get(
        self,
        handler: "BaseHTTPRequestHandler",
        project_id: str,
    ) -> None:
        """Handle GET /api/projects/{project_id}/auto-scheduler/inspection-tasks."""
        code, payload = self.ctx.list_project_auto_inspection_tasks_response(
            project_id=project_id,
            find_project_cfg=self.ctx.find_project_cfg,
            load_project_auto_inspection_config=self.ctx.load_project_auto_inspection_config,
            normalize_auto_inspection_tasks=self.ctx.normalize_auto_inspection_tasks,
        )
        self.ctx.json_response(handler, code, payload)

    def _handle_project_inspection_records_get(
        self,
        handler: "BaseHTTPRequestHandler",
        project_id: str,
        raw_path: str,
    ) -> None:
        """Handle GET /api/projects/{project_id}/auto-scheduler/inspection-records."""
        query_string = urlparse(raw_path).query or ""
        code, payload = self.ctx.list_project_inspection_records_response(
            project_id=project_id,
            query_string=query_string,
            store=self.ctx.store,
            find_project_cfg=self.ctx.find_project_cfg,
            normalize_inspection_task_id=self.ctx.normalize_inspection_task_id,
            safe_text=self.ctx.safe_text,
            auto_inspection_record_limit=self.ctx.auto_inspection_record_limit,
            project_scheduler_runtime=self.ctx.project_scheduler_runtime,
            build_project_scheduler_status=self.ctx.build_project_scheduler_status,
            ensure_auto_scheduler_status_shape=self.ctx.ensure_auto_scheduler_status_shape,
            normalize_inspection_records=self.ctx.normalize_inspection_records,
        )
        self.ctx.json_response(handler, code, payload)

    def _handle_sessions_list_get(
        self, handler: "BaseHTTPRequestHandler", query_string: str
    ) -> None:
        """Handle GET /api/sessions."""
        project_id = str(getattr(handler.server, "project_id", "") or "").strip()
        runtime_role = str(getattr(handler.server, "runtime_role", "") or "").strip()
        query_string, requested_project_id = self._alias_project_query_string(query_string)
        code, payload = self.ctx.runtime_list_sessions_response(
            query_string=query_string,
            session_store=self.ctx.session_store,
            store=self.ctx.store,
            environment_name=self.ctx.environment_name,
            worktree_root=self.ctx.worktree_root,
            apply_effective_primary_flags=self.ctx.apply_effective_primary_flags,
            decorate_sessions_display_fields=self.ctx.decorate_sessions_display_fields,
            apply_session_context_rows=self.ctx.apply_session_context_rows,
            apply_session_work_context=self.ctx.apply_session_work_context,
            attach_runtime_state_to_sessions=self.ctx.attach_runtime_state_to_sessions,
            heartbeat_runtime=self.ctx.heartbeat_runtime,
            load_session_heartbeat_config=self.ctx.load_session_heartbeat_config,
            heartbeat_summary_payload=self.ctx.heartbeat_summary_payload,
        )
        if isinstance(payload, dict):
            payload.setdefault("project_id", project_id)
            payload.setdefault("runtime_role", runtime_role)
            payload.setdefault(
                "compat_shell",
                runtime_role == "compat_shell" or project_id == "task_dashboard",
            )
            payload = self._attach_task_assistant_to_session_rows(
                payload,
                fallback_project_id=requested_project_id,
            )
            payload = self._rewrite_alias_payload(payload, requested_project_id=requested_project_id, row_keys=("sessions",))
        self.ctx.json_response(handler, code, payload)

    def _handle_channel_sessions_get(
        self, handler: "BaseHTTPRequestHandler", query_string: str
    ) -> None:
        """Handle GET /api/channel-sessions."""
        code, payload = self.ctx.runtime_list_channel_sessions_response(
            query_string=query_string,
            session_store=self.ctx.session_store,
            store=self.ctx.store,
            environment_name=self.ctx.environment_name,
            worktree_root=self.ctx.worktree_root,
            apply_effective_primary_flags=self.ctx.apply_effective_primary_flags,
            decorate_sessions_display_fields=self.ctx.decorate_sessions_display_fields,
            apply_session_context_rows=self.ctx.apply_session_context_rows,
            apply_session_work_context=self.ctx.apply_session_work_context,
            resolve_channel_primary_session_id=self.ctx.resolve_channel_primary_session_id,
            heartbeat_runtime=self.ctx.heartbeat_runtime,
            load_session_heartbeat_config=self.ctx.load_session_heartbeat_config,
            heartbeat_summary_payload=self.ctx.heartbeat_summary_payload,
        )
        self.ctx.json_response(handler, code, payload)

    def _handle_agent_candidates_get(
        self, handler: "BaseHTTPRequestHandler", query_string: str
    ) -> None:
        """Handle GET /api/agent-candidates."""
        query_string, requested_project_id = self._alias_project_query_string(query_string)
        code, payload = runtime_list_agent_candidates_response(
            query_string=query_string,
            session_store=self.ctx.session_store,
            store=self.ctx.store,
            environment_name=self.ctx.environment_name,
            worktree_root=self.ctx.worktree_root,
            apply_effective_primary_flags=self.ctx.apply_effective_primary_flags,
            decorate_sessions_display_fields=self.ctx.decorate_sessions_display_fields,
            apply_session_context_rows=self.ctx.apply_session_context_rows,
            apply_session_work_context=self.ctx.apply_session_work_context,
            attach_runtime_state_to_sessions=self.ctx.attach_runtime_state_to_sessions,
            heartbeat_runtime=self.ctx.heartbeat_runtime,
            load_session_heartbeat_config=self.ctx.load_session_heartbeat_config,
            heartbeat_summary_payload=self.ctx.heartbeat_summary_payload,
        )
        if isinstance(payload, dict):
            payload = self._rewrite_alias_payload(payload, requested_project_id=requested_project_id, row_keys=("agent_targets",))
        self.ctx.json_response(handler, code, payload)

    def _handle_session_bindings_get(
        self, handler: "BaseHTTPRequestHandler", qs: dict[str, list[str]]
    ) -> None:
        """Handle GET /api/sessions/bindings."""
        requested_project_id = str((qs.get("projectId") or [""])[0] or "").strip()
        project_id = canonicalize_runtime_project_id(requested_project_id)
        compat_meta = {
            "compatibility_entry": True,
            "entry_role": "compatibility_management",
            "writable": True,
            "primary_truth_hint": "/api/sessions + /api/agent-candidates",
        }
        bindings = self.ctx.session_binding_store.list_bindings(
            project_id if project_id else None
        )
        out_bindings: list[dict[str, Any]] = []
        for row in bindings:
            item = dict(row if isinstance(row, dict) else {})
            item.update(compat_meta)
            session_id = str(item.get("sessionId") or "").strip()
            session = self.ctx.session_store.get_session(session_id) if session_id else None
            if isinstance(session, dict):
                enriched = self.ctx.apply_session_work_context(
                    session,
                    project_id=str(session.get("project_id") or item.get("projectId") or "").strip(),
                    environment_name=self.ctx.environment_name,
                    worktree_root=self.ctx.worktree_root,
                )
                item["project_execution_context"] = (
                    (enriched.get("project_execution_context") or {}) if isinstance(enriched, dict) else {}
                )
            out_bindings.append(item)
        payload = {"bindings": out_bindings, **compat_meta}
        payload = self._rewrite_alias_payload(payload, requested_project_id=requested_project_id, row_keys=("bindings",))
        self.ctx.json_response(handler, 200, payload)

    def _handle_session_binding_get(
        self, handler: "BaseHTTPRequestHandler", path: str
    ) -> None:
        """Handle GET /api/sessions/binding/{session_id}."""
        code, payload = self.ctx.runtime_get_session_binding_response(
            session_id=path.split("/")[-1],
            session_binding_store=self.ctx.session_binding_store,
        )
        if code == 200 and isinstance(payload, dict):
            session_id = str(payload.get("sessionId") or "").strip()
            session = self.ctx.session_store.get_session(session_id) if session_id else None
            if isinstance(session, dict):
                enriched = self.ctx.apply_session_work_context(
                    session,
                    project_id=str(session.get("project_id") or payload.get("projectId") or "").strip(),
                    environment_name=self.ctx.environment_name,
                    worktree_root=self.ctx.worktree_root,
                )
                payload = dict(payload)
                payload["project_execution_context"] = (
                    (enriched.get("project_execution_context") or {}) if isinstance(enriched, dict) else {}
                )
        self.ctx.json_response(handler, code, payload)

    def _handle_session_heartbeat_history_get(
        self, handler: "BaseHTTPRequestHandler", path: str, qs: dict[str, list[str]]
    ) -> None:
        """Handle GET /api/sessions/{session_id}/heartbeat-tasks/{task_id}/history."""
        parts = [seg for seg in path.split("/") if seg]
        if not (
            len(parts) == 6
            and parts[:2] == ["api", "sessions"]
            and parts[3] == "heartbeat-tasks"
            and parts[5] == "history"
        ):
            self.ctx.json_response(handler, 404, {"error": "not found"})
            return
        limit_s = self.ctx.safe_text((qs.get("limit") or ["20"])[0], 20).strip()
        try:
            limit = max(1, min(self.ctx.heartbeat_task_history_limit, int(limit_s)))
        except Exception:
            limit = 20
        code, payload = self.ctx.runtime_list_session_heartbeat_task_history_route_response(
            session_id=str(parts[2] or "").strip(),
            heartbeat_task_id=self.ctx.normalize_heartbeat_task_id(parts[4], default=""),
            limit=limit,
            session_store=self.ctx.session_store,
            store=self.ctx.store,
            heartbeat_runtime=self.ctx.heartbeat_runtime,
            infer_project_id_for_session=self.ctx.infer_project_id_for_session,
            list_session_heartbeat_task_history_response=self.ctx.list_session_heartbeat_task_history_response,
        )
        self.ctx.json_response(handler, code, payload)

    def _handle_session_detail_get(
        self, handler: "BaseHTTPRequestHandler", path: str
    ) -> None:
        """Handle GET /api/sessions/{session_id}."""
        # Placeholder - full implementation uses runtime session routes
        self.ctx.json_response(handler, 404, {"error": "not found"})

    def _handle_runs_list_get(
        self, handler: "BaseHTTPRequestHandler", query_string: str
    ) -> None:
        """Handle GET /api/codex/runs."""
        project_id = str(getattr(handler.server, "project_id", "") or "").strip()
        runtime_role = str(getattr(handler.server, "runtime_role", "") or "").strip()
        bind_host = ""
        try:
            bind_host = str(handler.server.server_address[0] or "").strip()
        except Exception:
            bind_host = ""
        query_string, requested_project_id = self._alias_project_query_string(query_string, param_names=("projectId", "project_id"))
        code, payload = self.ctx.runtime_list_runs_response(
            query_string=query_string,
            store=self.ctx.store,
            scheduler=self.ctx.scheduler,
            maybe_trigger_restart_recovery_lazy=self.ctx.maybe_trigger_restart_recovery_lazy,
            maybe_trigger_queued_recovery_lazy=self.ctx.maybe_trigger_queued_recovery_lazy,
            build_run_observability_fields=self.ctx.build_run_observability_fields,
            environment_name=self.ctx.environment_name,
            local_server_origin=self.ctx.build_local_server_origin(bind_host, self.ctx.server_port),
            worktree_root=str(self.ctx.worktree_root),
        )
        if isinstance(payload, dict):
            payload.setdefault("project_id", project_id)
            payload.setdefault("runtime_role", runtime_role)
            payload.setdefault(
                "compat_shell",
                runtime_role == "compat_shell" or project_id == "task_dashboard",
            )
            payload = self._rewrite_alias_payload(payload, requested_project_id=requested_project_id, row_keys=("runs",))
        self.ctx.json_response(handler, code, payload)

    def _handle_run_detail_get(
        self, handler: "BaseHTTPRequestHandler", path: str
    ) -> None:
        """Handle GET /api/codex/run/{run_id}."""
        run_id = path.rsplit("/", 1)[-1]
        code, payload = self.ctx.runtime_get_run_detail_response(
            run_id=run_id,
            store=self.ctx.store,
            scheduler=self.ctx.scheduler,
            maybe_trigger_restart_recovery_lazy=self.ctx.maybe_trigger_restart_recovery_lazy,
            maybe_trigger_queued_recovery_lazy=self.ctx.maybe_trigger_queued_recovery_lazy,
            build_run_observability_fields=self.ctx.build_run_observability_fields,
            error_hint=self.ctx.error_hint,
        )
        self.ctx.json_response(handler, code, payload)

    def _handle_task_assistant_get(
        self,
        handler: "BaseHTTPRequestHandler",
        task_id: str,
        qs: dict[str, list[str]],
    ) -> None:
        """Handle GET /api/tasks/{task_id}/assistant-config."""
        project_id = str((qs.get("project_id") or qs.get("projectId") or [""])[0] or "").strip()
        code, payload = get_task_assistant_response(
            runtime_base_dir=self._task_runtime_base_dir(),
            project_id=project_id,
            task_id=task_id,
            session_store=self.ctx.session_store,
            heartbeat_runtime=self.ctx.heartbeat_runtime,
        )
        self.ctx.json_response(handler, code, payload)

    def _handle_task_assistant_put(
        self,
        handler: "BaseHTTPRequestHandler",
        task_id: str,
    ) -> None:
        """Handle PUT /api/tasks/{task_id}/assistant-config."""
        if not self.ctx.require_token():
            return
        try:
            body = self.ctx.read_body_json(handler, max_bytes=32_000)
        except Exception as e:
            self.ctx.json_response(handler, 400, {"error": f"bad json: {e}"})
            return
        project_id = str((body.get("project_id") or body.get("projectId") or "")).strip()
        code, payload = put_task_assistant_response(
            runtime_base_dir=self._task_runtime_base_dir(),
            project_id=project_id,
            task_id=task_id,
            body=body,
            session_store=self.ctx.session_store,
            heartbeat_runtime=self.ctx.heartbeat_runtime,
        )
        self.ctx.json_response(handler, code, payload)

    def _handle_task_assistant_delete(
        self,
        handler: "BaseHTTPRequestHandler",
        task_id: str,
        qs: dict[str, list[str]],
    ) -> None:
        """Handle DELETE /api/tasks/{task_id}/assistant-config."""
        if not self.ctx.require_token():
            return
        project_id = str((qs.get("project_id") or qs.get("projectId") or [""])[0] or "").strip()
        code, payload = delete_task_assistant_response(
            runtime_base_dir=self._task_runtime_base_dir(),
            project_id=project_id,
            task_id=task_id,
            session_store=self.ctx.session_store,
            heartbeat_runtime=self.ctx.heartbeat_runtime,
        )
        self.ctx.json_response(handler, code, payload)

    def _handle_task_assistant_run_now_post(
        self,
        handler: "BaseHTTPRequestHandler",
        task_id: str,
    ) -> None:
        """Handle POST /api/tasks/{task_id}/assistant-config/run-now."""
        if not self.ctx.require_token():
            return
        try:
            body = self.ctx.read_body_json(handler, max_bytes=16_000)
        except Exception:
            body = {}
        project_id = str(((body or {}).get("project_id") or (body or {}).get("projectId") or "")).strip()
        code, payload = run_task_assistant_now_response(
            runtime_base_dir=self._task_runtime_base_dir(),
            project_id=project_id,
            task_id=task_id,
            session_store=self.ctx.session_store,
            heartbeat_runtime=self.ctx.heartbeat_runtime,
        )
        self.ctx.json_response(handler, code, payload)

    # -----------------------------------------------------------------------
    # POST request handlers
    # -----------------------------------------------------------------------

    def _handle_dashboard_rebuild_post(self, handler: "BaseHTTPRequestHandler") -> None:
        """Handle POST /api/dashboard/rebuild."""
        if not self.ctx.require_token():
            return
        try:
            self.ctx.read_body_json(handler, max_bytes=4_000)
        except Exception:
            pass
        try:
            result = self.ctx.rebuild_dashboard_static(timeout_s=150)
            self.ctx.json_response(handler, 200, result)
        except subprocess.TimeoutExpired:
            self.ctx.json_response(handler, 504, {"error": "dashboard rebuild timeout"})
        except Exception as e:
            self.ctx.json_response(handler, 500, {"error": str(e)})

    def _handle_visibility_check_post(self, handler: "BaseHTTPRequestHandler") -> None:
        """Handle POST /api/dashboard/visibility-check."""
        if not self.ctx.require_token():
            return
        try:
            body = self.ctx.read_body_json(handler, max_bytes=12_000)
        except Exception as e:
            self.ctx.json_response(handler, 400, {"error": f"bad json: {e}"})
            return
        project_id = self.ctx.safe_text(
            body.get("project_id") if "project_id" in body else body.get("projectId"),
            120,
        ).strip()
        channel_name = self.ctx.safe_text(
            body.get("channel_name") if "channel_name" in body else body.get("channelName"),
            240,
        ).strip()
        session_id = self.ctx.safe_text(
            body.get("session_id") if "session_id" in body else body.get("sessionId"),
            120,
        ).strip()
        expected_generated_at = self.ctx.safe_text(
            body.get("expected_generated_at")
            if "expected_generated_at" in body
            else body.get("expectedGeneratedAt"),
            120,
        ).strip()
        auto_rebuild = self.ctx.coerce_bool(
            body.get("auto_rebuild") if "auto_rebuild" in body else body.get("autoRebuild"),
            True,
        )
        if not project_id or not channel_name:
            self.ctx.json_response(handler, 400, {"error": "missing project_id or channel_name"})
            return

        sessions = self.ctx.session_store.list_sessions(project_id, channel_name if channel_name else None)
        merged = self.ctx.decorate_sessions_display_fields(sessions)
        target_bound = False
        if session_id:
            for row in merged:
                row_session_id = str(row.get("id") or row.get("sessionId") or "").strip()
                if row_session_id and row_session_id == session_id:
                    target_bound = True
                    break
        else:
            target_bound = bool(merged)

        generated_before = self.ctx.read_task_dashboard_generated_at()
        rebuild_triggered = False
        rebuild_ok = False
        rebuild_error = ""
        rebuild_summary: dict[str, Any] = {}
        reason = ""

        if not target_bound:
            reason = "session_not_bound"
        elif not expected_generated_at:
            reason = "missing_expected_generated_at"
        elif generated_before and generated_before != expected_generated_at:
            reason = "already_fresh"
        elif auto_rebuild:
            rebuild_triggered = True
            reason = "generated_at_stale"
            try:
                rebuild_summary = self.ctx.rebuild_dashboard_static(timeout_s=150)
                rebuild_ok = True
            except Exception as e:
                rebuild_error = str(e)

        generated_after = self.ctx.read_task_dashboard_generated_at()
        generated_fresh = bool(expected_generated_at and generated_after and generated_after != expected_generated_at)
        hard_refresh_required = bool(target_bound and expected_generated_at and not generated_fresh)
        self.ctx.json_response(
            handler,
            200,
            {
                "ok": True,
                "project_id": project_id,
                "channel_name": channel_name,
                "session_id": session_id,
                "checks": {
                    "session_bound": bool(target_bound),
                    "session_count": len(merged),
                    "expected_generated_at": expected_generated_at,
                    "generated_at_before": generated_before,
                    "generated_at_after": generated_after,
                    "generated_at_fresh": generated_fresh,
                },
                "action": {
                    "reason": reason,
                    "auto_rebuild": bool(auto_rebuild),
                    "rebuild_triggered": bool(rebuild_triggered),
                    "rebuild_ok": bool(rebuild_ok),
                    "rebuild_error": rebuild_error,
                    "hard_refresh_required": hard_refresh_required,
                },
                "rebuild": rebuild_summary,
            },
        )

    def _handle_config_global_post(self, handler: "BaseHTTPRequestHandler") -> None:
        """Handle POST /api/config/global."""
        if not self.ctx.require_token():
            return
        try:
            body = self.ctx.read_body_json(handler, max_bytes=10_000)
        except Exception as e:
            self.ctx.json_response(handler, 400, {"error": f"bad json: {e}"})
            return
        raw = body.get("max_concurrency") if "max_concurrency" in body else body.get("maxConcurrency")
        cli_bins_raw = body.get("cli_bins") if "cli_bins" in body else body.get("cliBins")
        if raw is None and cli_bins_raw is None:
            self.ctx.json_response(handler, 400, {"error": "missing max_concurrency/cli_bins"})
            return

        max_concurrency: int | None = None
        if raw is not None:
            try:
                max_concurrency = int(raw)
            except Exception:
                self.ctx.json_response(handler, 400, {"error": "invalid max_concurrency"})
                return
            if max_concurrency < 1 or max_concurrency > 32:
                self.ctx.json_response(handler, 400, {"error": "max_concurrency out of range: 1..32"})
                return

        cli_bins_patch: dict[str, Any] = {}
        if cli_bins_raw is not None:
            if not isinstance(cli_bins_raw, dict):
                self.ctx.json_response(handler, 400, {"error": "invalid cli_bins"})
                return
            cli_bins_patch = {str(k or ""): ("" if v is None else str(v)) for k, v in cli_bins_raw.items()}

        config_path: Path | None = None
        local_config_path: Path | None = None
        try:
            if max_concurrency is not None:
                config_path = self.ctx.set_runtime_max_concurrency_in_config(max_concurrency)
            if cli_bins_raw is not None:
                local_config_path = self.ctx.set_runtime_cli_bins_in_local_config(cli_bins_patch)
        except Exception as e:
            self.ctx.json_response(handler, 400, {"error": str(e)})
            return
        cfg = self.ctx.load_dashboard_cfg_current()
        max_cc, max_cc_source = self.ctx.resolve_effective_max_concurrency(cfg=cfg)
        self.ctx.json_response(
            handler,
            200,
            {
                "ok": True,
                "global": {
                    "max_concurrency": int(max_cc),
                    "max_concurrency_source": max_cc_source,
                    "requires_restart": bool(max_concurrency is not None),
                    "cli_tools": self.ctx.collect_cli_tools_snapshot(cfg, session_store=self.ctx.session_store),
                },
                "config_path": str(config_path) if config_path else "",
                "local_config_path": str(local_config_path) if local_config_path else "",
            },
        )

    def _dispatch_project_routes_post(
        self,
        handler: "BaseHTTPRequestHandler",
        path: str,
        parts: list[str],
    ) -> bool:
        """Dispatch project-related POST routes."""
        if len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "auto-scheduler":
            self._handle_project_auto_scheduler_post(handler, parts[2])
            return True

        if len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "heartbeat-tasks":
            self._handle_project_heartbeat_tasks_post(handler, parts[2])
            return True

        if len(parts) == 5 and parts[:2] == ["api", "projects"] and parts[3] == "task-push":
            self._handle_project_task_push_action_post(handler, parts[2], parts[4])
            return True

        if len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "task-plans":
            self._handle_project_task_plans_post(handler, parts[2])
            return True

        if len(parts) == 5 and parts[:2] == ["api", "projects"] and parts[3] == "tasks" and parts[4] in {"create", "validate"}:
            self._handle_project_task_workflow_post(handler, parts[2], parts[4])
            return True

        if len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "assist-requests":
            self._handle_project_assist_request_create_post(handler, parts[2])
            return True

        if len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "config":
            self._handle_project_config_post(handler, parts[2])
            return True

        if len(parts) == 6 and parts[:2] == ["api", "projects"] and parts[3] == "task-plans" and parts[5] == "activate":
            self._handle_project_task_plan_activate_post(handler, parts[2], parts[4])
            return True

        if len(parts) == 6 and parts[:2] == ["api", "projects"] and parts[3] == "heartbeat-tasks" and parts[5] == "run-now":
            self._handle_project_heartbeat_task_run_now_post(handler, parts[2], parts[4])
            return True

        if len(parts) == 5 and parts[:2] == ["api", "projects"] and parts[3] == "assist-requests" and parts[4] == "auto-trigger":
            self._handle_project_assist_request_auto_trigger_post(handler, parts[2])
            return True

        if len(parts) == 6 and parts[:2] == ["api", "projects"] and parts[3] == "heartbeat-tasks" and parts[5] == "delete":
            self._handle_project_heartbeat_task_delete_post(handler, parts[2], parts[4])
            return True

        if len(parts) == 5 and parts[:2] == ["api", "projects"] and parts[3] == "auto-scheduler" and parts[4] == "inspection-tasks":
            self._handle_project_inspection_task_upsert_post(handler, parts[2])
            return True

        if len(parts) == 6 and parts[:2] == ["api", "projects"] and parts[3] == "assist-requests" and parts[5] == "close":
            self._handle_project_assist_request_close_post(handler, parts[2], parts[4])
            return True

        if len(parts) == 6 and parts[:2] == ["api", "projects"] and parts[3] == "assist-requests" and parts[5] == "reply":
            self._handle_project_assist_request_reply_post(handler, parts[2], parts[4])
            return True

        if (
            len(parts) == 7
            and parts[:2] == ["api", "projects"]
            and parts[3] == "auto-scheduler"
            and parts[4] == "inspection-tasks"
            and parts[6] == "delete"
        ):
            self._handle_project_inspection_task_delete_post(handler, parts[2], parts[5])
            return True

        return False

    def _handle_session_heartbeat_task_action_post(
        self,
        handler: "BaseHTTPRequestHandler",
        session_id: str,
        task_id: str,
        action: str,
    ) -> None:
        """Handle POST /api/sessions/{session_id}/heartbeat-tasks/{task_id}/(run-now|delete)."""
        if not self.ctx.require_token():
            return
        code, payload = run_or_delete_session_heartbeat_task_response(
            session_id=str(session_id or "").strip(),
            heartbeat_task_id=self.ctx.normalize_heartbeat_task_id(task_id, default=""),
            action=str(action or "").strip(),
            session_store=self.ctx.session_store,
            store=self.ctx.store,
            heartbeat_runtime=self.ctx.heartbeat_runtime,
            infer_project_id_for_session=self.ctx.infer_project_id_for_session,
            load_session_heartbeat_config=self.ctx.load_session_heartbeat_config,
            heartbeat_tasks_for_write=self.ctx.heartbeat_tasks_for_write,
            heartbeat_session_payload_for_write=self.ctx.heartbeat_session_payload_for_write,
        )
        self.ctx.json_response(handler, code, payload)

    def _handle_project_task_push_action_post(
        self,
        handler: "BaseHTTPRequestHandler",
        project_id: str,
        action: str,
    ) -> None:
        """Handle POST /api/projects/{project_id}/task-push/{action}."""
        if not self.ctx.require_token():
            return
        pid = str(project_id or "").strip()
        act = str(action or "").strip().lower()
        if not pid:
            self.ctx.json_response(handler, 400, {"error": "missing project_id"})
            return
        if not self.ctx.find_project_cfg(pid):
            self.ctx.json_response(handler, 404, {"error": "project not found"})
            return
        if self.ctx.task_push_runtime is None:
            self.ctx.json_response(handler, 503, {"error": "task push runtime unavailable"})
            return
        try:
            body = self.ctx.read_body_json(handler, max_bytes=40_000)
        except Exception as e:
            self.ctx.json_response(handler, 400, {"error": f"bad json: {e}"})
            return
        status_code, payload = handle_task_push_action_response(
            project_id=pid,
            action=act,
            body=body,
            task_push_runtime=self.ctx.task_push_runtime,
            session_store=self.ctx.session_store,
            safe_text=self.ctx.safe_text,
            coerce_bool=self.ctx.coerce_bool,
            coerce_int=self.ctx.coerce_int,
            looks_like_uuid=self.ctx.looks_like_uuid,
            resolve_primary_target_by_channel=self.ctx.resolve_primary_target_by_channel,
        )
        self.ctx.json_response(handler, status_code, payload)

    def _handle_project_task_plans_post(
        self,
        handler: "BaseHTTPRequestHandler",
        project_id: str,
    ) -> None:
        """Handle POST /api/projects/{project_id}/task-plans."""
        if not self.ctx.require_token():
            return
        try:
            body = self.ctx.read_body_json(handler, max_bytes=200_000)
        except Exception as e:
            self.ctx.json_response(handler, 400, {"error": f"bad json: {e}"})
            return
        code, payload = upsert_task_plan_response(
            project_id=str(project_id or "").strip(),
            body=body,
            task_plan_runtime=self.ctx.task_plan_runtime,
            find_project_cfg=self.ctx.find_project_cfg,
        )
        self.ctx.json_response(handler, code, payload)

    def _handle_project_task_workflow_post(
        self,
        handler: "BaseHTTPRequestHandler",
        project_id: str,
        action: str,
    ) -> None:
        """Handle POST /api/projects/{project_id}/tasks/(create|validate)."""
        if not self.ctx.require_token():
            return
        pid = str(project_id or "").strip()
        if not pid:
            self.ctx.json_response(handler, 400, {"ok": False, "error": "missing_project_id", "step": "request_validate"})
            return
        if not self.ctx.find_project_cfg(pid):
            self.ctx.json_response(handler, 404, {"ok": False, "error": "project_not_found", "step": "request_validate"})
            return
        try:
            body = self.ctx.read_body_json(handler, max_bytes=120_000)
        except Exception as e:
            self.ctx.json_response(handler, 400, {"ok": False, "error": "bad_json", "message": str(e), "step": "request_parse"})
            return
        if action == "create":
            code, payload = task_workflow_create_from_payload(
                root=self.ctx.repo_root(),
                project_id=pid,
                payload=body,
            )
        else:
            code, payload = task_workflow_validate_from_payload(
                root=self.ctx.repo_root(),
                project_id=pid,
                payload=body,
            )
        self.ctx.json_response(handler, code, payload)

    def _handle_project_heartbeat_tasks_post(
        self,
        handler: "BaseHTTPRequestHandler",
        project_id: str,
    ) -> None:
        """Handle POST /api/projects/{project_id}/heartbeat-tasks."""
        if not self.ctx.require_token():
            return
        try:
            body = self.ctx.read_body_json(handler, max_bytes=80_000)
        except Exception as e:
            self.ctx.json_response(handler, 400, {"error": f"bad json: {e}"})
            return
        code, payload = create_or_update_project_heartbeat_task_response(
            project_id=str(project_id or "").strip(),
            body=body,
            find_project_cfg=self.ctx.find_project_cfg,
            heartbeat_runtime=self.ctx.heartbeat_runtime,
            load_project_heartbeat_config=self.ctx.load_project_heartbeat_config,
            normalize_heartbeat_task=self.ctx.normalize_heartbeat_task,
            heartbeat_tasks_for_write=self.ctx.heartbeat_tasks_for_write,
            build_heartbeat_patch_with_tasks=runtime_build_heartbeat_patch_with_tasks,
            coerce_bool=self.ctx.coerce_bool,
            coerce_int=self.ctx.coerce_int,
            set_project_scheduler_contract_in_config=self.ctx.set_project_scheduler_contract_in_config,
        )
        self.ctx.json_response(handler, code, payload)

    def _handle_project_task_plan_activate_post(
        self,
        handler: "BaseHTTPRequestHandler",
        project_id: str,
        plan_id: str,
    ) -> None:
        """Handle POST /api/projects/{project_id}/task-plans/{plan_id}/activate."""
        if not self.ctx.require_token():
            return
        try:
            body = self.ctx.read_body_json(handler, max_bytes=20_000)
        except Exception:
            body = {}
        code, payload = activate_task_plan_response(
            project_id=str(project_id or "").strip(),
            plan_id=str(plan_id or "").strip(),
            body=body,
            task_plan_runtime=self.ctx.task_plan_runtime,
            find_project_cfg=self.ctx.find_project_cfg,
        )
        self.ctx.json_response(handler, code, payload)

    def _handle_project_heartbeat_task_run_now_post(
        self,
        handler: "BaseHTTPRequestHandler",
        project_id: str,
        task_id: str,
    ) -> None:
        """Handle POST /api/projects/{project_id}/heartbeat-tasks/{task_id}/run-now."""
        if not self.ctx.require_token():
            return
        code, payload = run_project_heartbeat_task_now_response(
            project_id=str(project_id or "").strip(),
            heartbeat_task_id=self.ctx.normalize_heartbeat_task_id(task_id, default=""),
            find_project_cfg=self.ctx.find_project_cfg,
            heartbeat_runtime=self.ctx.heartbeat_runtime,
        )
        self.ctx.json_response(handler, code, payload)

    def _handle_project_assist_request_create_post(
        self,
        handler: "BaseHTTPRequestHandler",
        project_id: str,
    ) -> None:
        """Handle POST /api/projects/{project_id}/assist-requests."""
        if not self.ctx.require_token():
            return
        try:
            body = self.ctx.read_body_json(handler, max_bytes=40_000)
        except Exception as e:
            self.ctx.json_response(handler, 400, {"error": f"bad json: {e}"})
            return
        code, payload = create_assist_request_response(
            project_id=str(project_id or "").strip(),
            body=body,
            assist_runtime=self.ctx.assist_request_runtime,
            find_project_cfg=self.ctx.find_project_cfg,
        )
        self.ctx.json_response(handler, code, payload)

    def _handle_project_assist_request_auto_trigger_post(
        self,
        handler: "BaseHTTPRequestHandler",
        project_id: str,
    ) -> None:
        """Handle POST /api/projects/{project_id}/assist-requests/auto-trigger."""
        if not self.ctx.require_token():
            return
        try:
            body = self.ctx.read_body_json(handler, max_bytes=40_000)
        except Exception as e:
            self.ctx.json_response(handler, 400, {"error": f"bad json: {e}"})
            return
        code, payload = auto_trigger_assist_request_response(
            project_id=str(project_id or "").strip(),
            body=body,
            assist_runtime=self.ctx.assist_request_runtime,
            find_project_cfg=self.ctx.find_project_cfg,
        )
        self.ctx.json_response(handler, code, payload)

    def _handle_project_heartbeat_task_delete_post(
        self,
        handler: "BaseHTTPRequestHandler",
        project_id: str,
        task_id: str,
    ) -> None:
        """Handle POST /api/projects/{project_id}/heartbeat-tasks/{task_id}/delete."""
        if not self.ctx.require_token():
            return
        code, payload = delete_project_heartbeat_task_response(
            project_id=str(project_id or "").strip(),
            heartbeat_task_id=self.ctx.normalize_heartbeat_task_id(task_id, default=""),
            find_project_cfg=self.ctx.find_project_cfg,
            heartbeat_runtime=self.ctx.heartbeat_runtime,
            load_project_heartbeat_config=self.ctx.load_project_heartbeat_config,
            heartbeat_tasks_for_write=self.ctx.heartbeat_tasks_for_write,
            build_heartbeat_patch_with_tasks=runtime_build_heartbeat_patch_with_tasks,
            set_project_scheduler_contract_in_config=self.ctx.set_project_scheduler_contract_in_config,
        )
        self.ctx.json_response(handler, code, payload)

    def _handle_project_assist_request_close_post(
        self,
        handler: "BaseHTTPRequestHandler",
        project_id: str,
        request_id: str,
    ) -> None:
        """Handle POST /api/projects/{project_id}/assist-requests/{request_id}/close."""
        if not self.ctx.require_token():
            return
        try:
            body = self.ctx.read_body_json(handler, max_bytes=40_000)
        except Exception as e:
            self.ctx.json_response(handler, 400, {"error": f"bad json: {e}"})
            return
        code, payload = close_assist_request_response(
            project_id=str(project_id or "").strip(),
            request_id=str(request_id or "").strip(),
            body=body,
            assist_runtime=self.ctx.assist_request_runtime,
            find_project_cfg=self.ctx.find_project_cfg,
        )
        self.ctx.json_response(handler, code, payload)

    def _handle_project_assist_request_reply_post(
        self,
        handler: "BaseHTTPRequestHandler",
        project_id: str,
        request_id: str,
    ) -> None:
        """Handle POST /api/projects/{project_id}/assist-requests/{request_id}/reply."""
        if not self.ctx.require_token():
            return
        try:
            body = self.ctx.read_body_json(handler, max_bytes=40_000)
        except Exception as e:
            self.ctx.json_response(handler, 400, {"error": f"bad json: {e}"})
            return
        code, payload = reply_assist_request_response(
            project_id=str(project_id or "").strip(),
            request_id=str(request_id or "").strip(),
            body=body,
            assist_runtime=self.ctx.assist_request_runtime,
            find_project_cfg=self.ctx.find_project_cfg,
        )
        self.ctx.json_response(handler, code, payload)

    def _handle_project_auto_scheduler_post(
        self,
        handler: "BaseHTTPRequestHandler",
        project_id: str,
    ) -> None:
        """Handle POST /api/projects/{project_id}/auto-scheduler."""
        if not self.ctx.require_token():
            return
        try:
            body = self.ctx.read_body_json(handler, max_bytes=10_000)
        except Exception as e:
            self.ctx.json_response(handler, 400, {"error": f"bad json: {e}"})
            return
        code, payload = self.ctx.set_project_auto_scheduler_enabled_response(
            project_id=project_id,
            body=body if isinstance(body, dict) else {},
            store=self.ctx.store,
            find_project_cfg=self.ctx.find_project_cfg,
            coerce_bool=self.ctx.coerce_bool,
            set_project_scheduler_enabled_in_config=self.ctx.set_project_scheduler_enabled_in_config,
            project_scheduler_runtime=self.ctx.project_scheduler_runtime,
            build_project_scheduler_status=self.ctx.build_project_scheduler_status,
            ensure_auto_scheduler_status_shape=self.ctx.ensure_auto_scheduler_status_shape,
            attach_auto_inspection_candidate_preview=self.ctx.attach_auto_inspection_candidate_preview,
        )
        self.ctx.json_response(handler, code, payload)

    def _handle_project_config_post(
        self,
        handler: "BaseHTTPRequestHandler",
        project_id: str,
    ) -> None:
        """Handle POST /api/projects/{project_id}/config."""
        if not self.ctx.require_token():
            return
        try:
            body = self.ctx.read_body_json(handler, max_bytes=80_000)
        except Exception as e:
            self.ctx.json_response(handler, 400, {"error": f"bad json: {e}"})
            return

        body_dict = body if isinstance(body, dict) else {}
        has_share_space = "share_space" in body_dict or "shareSpace" in body_dict
        raw_share_space = body_dict.get("share_space") if "share_space" in body_dict else body_dict.get("shareSpace")
        config_body = {k: v for k, v in body_dict.items() if k not in {"share_space", "shareSpace"}}

        if config_body:
            code, payload = self._update_project_config_response_without_share_space(project_id, config_body)
            if code >= 400:
                self.ctx.json_response(handler, code, payload)
                return
        else:
            code, payload = self._project_config_response_with_share_space(project_id)
            if code >= 400:
                self.ctx.json_response(handler, code, payload)
                return

        if has_share_space:
            share_code, share_payload = runtime_update_project_share_space_config_response(
                worktree_root=self.ctx.worktree_root,
                environment_name=self.ctx.environment_name,
                project_id=str(payload.get("project_id") or project_id),
                raw_share_space=raw_share_space,
            )
            if share_code >= 400:
                self.ctx.json_response(handler, share_code, share_payload)
                return
            project = payload.get("project")
            if not isinstance(project, dict):
                project = {}
                payload["project"] = project
            project["share_space"] = share_payload.get("share_space") or {}
            payload["share_space_path"] = share_payload.get("share_space_path") or ""

        self.ctx.json_response(handler, code, payload)

    def _handle_project_bootstrap_post(self, handler: "BaseHTTPRequestHandler") -> None:
        """Handle POST /api/projects/bootstrap."""
        if not self.ctx.require_token():
            return
        try:
            body = self.ctx.read_body_json(handler, max_bytes=120_000)
        except Exception as e:
            self.ctx.json_response(handler, 400, {"error": f"bad json: {e}"})
            return
        code, payload = runtime_bootstrap_project_response(
            body=body if isinstance(body, dict) else {},
            config_path=self.ctx.config_toml_path(),
            repo_root=self.ctx.repo_root(),
            session_store=self.ctx.session_store,
            create_cli_session=self.ctx.create_cli_session,
            detect_git_branch=self.ctx.detect_git_branch,
            build_session_seed_prompt=self.ctx.build_session_seed_prompt,
            decorate_session_display_fields=self.ctx.decorate_session_display_fields,
            apply_session_work_context=self.ctx.apply_session_work_context,
            read_task_dashboard_generated_at=self.ctx.read_task_dashboard_generated_at,
            rebuild_dashboard_static=self.ctx.rebuild_dashboard_static,
            clear_dashboard_cfg_cache=runtime_clear_dashboard_cfg_cache,
        )
        self.ctx.json_response(handler, code, payload)

    def _handle_project_inspection_task_upsert_post(
        self,
        handler: "BaseHTTPRequestHandler",
        project_id: str,
    ) -> None:
        """Handle POST /api/projects/{project_id}/auto-scheduler/inspection-tasks."""
        if not self.ctx.require_token():
            return
        try:
            body = self.ctx.read_body_json(handler, max_bytes=40_000)
        except Exception as e:
            self.ctx.json_response(handler, 400, {"error": f"bad json: {e}"})
            return
        code, payload = self.ctx.create_or_update_project_auto_inspection_task_response(
            project_id=project_id,
            body=body if isinstance(body, dict) else {},
            find_project_cfg=self.ctx.find_project_cfg,
            load_project_auto_inspection_config=self.ctx.load_project_auto_inspection_config,
            build_default_auto_inspection_task=self.ctx.build_default_auto_inspection_task,
            normalize_inspection_targets=self.ctx.normalize_inspection_targets,
            normalize_auto_inspections=self.ctx.normalize_auto_inspections,
            normalize_auto_inspection_task=self.ctx.normalize_auto_inspection_task,
            auto_inspection_tasks_for_write=self.ctx.auto_inspection_tasks_for_write,
            normalize_inspection_task_id=self.ctx.normalize_inspection_task_id,
            build_auto_inspection_patch_with_tasks=self.ctx.build_auto_inspection_patch_with_tasks,
            coerce_bool=self.ctx.coerce_bool,
            set_project_scheduler_contract_in_config=self.ctx.set_project_scheduler_contract_in_config,
            project_scheduler_runtime=self.ctx.project_scheduler_runtime,
            store=self.ctx.store,
            build_project_scheduler_status=self.ctx.build_project_scheduler_status,
            ensure_auto_scheduler_status_shape=self.ctx.ensure_auto_scheduler_status_shape,
        )
        self.ctx.json_response(handler, code, payload)

    def _handle_project_inspection_task_delete_post(
        self,
        handler: "BaseHTTPRequestHandler",
        project_id: str,
        task_id: str,
    ) -> None:
        """Handle POST /api/projects/{project_id}/auto-scheduler/inspection-tasks/{task_id}/delete."""
        if not self.ctx.require_token():
            return
        try:
            body = self.ctx.read_body_json(handler, max_bytes=10_000)
        except Exception:
            body = {}
        code, payload = self.ctx.delete_project_auto_inspection_task_response(
            project_id=project_id,
            task_id=task_id,
            body=body,
            find_project_cfg=self.ctx.find_project_cfg,
            load_project_auto_inspection_config=self.ctx.load_project_auto_inspection_config,
            auto_inspection_tasks_for_write=self.ctx.auto_inspection_tasks_for_write,
            normalize_inspection_task_id=self.ctx.normalize_inspection_task_id,
            build_auto_inspection_patch_with_tasks=self.ctx.build_auto_inspection_patch_with_tasks,
            set_project_scheduler_contract_in_config=self.ctx.set_project_scheduler_contract_in_config,
            project_scheduler_runtime=self.ctx.project_scheduler_runtime,
            store=self.ctx.store,
            build_project_scheduler_status=self.ctx.build_project_scheduler_status,
            ensure_auto_scheduler_status_shape=self.ctx.ensure_auto_scheduler_status_shape,
        )
        self.ctx.json_response(handler, code, payload)

    def _handle_session_create_post(self, handler: "BaseHTTPRequestHandler") -> None:
        """Handle POST /api/sessions."""
        if not self.ctx.require_token():
            return
        try:
            body = self.ctx.read_body_json(handler, max_bytes=10_000)
        except Exception as e:
            self.ctx.json_response(handler, 400, {"error": f"bad json: {e}"})
            return
        payload = runtime_parse_session_create_request(body)
        project_id = str(payload.get("project_id") or "")
        channel_name = str(payload.get("channel_name") or "")
        if not project_id or not channel_name:
            self.ctx.json_response(handler, 400, {"error": "missing project_id or channel_name"})
            return
        try:
            payload_out = runtime_create_session_response(
                payload=payload,
                session_store=self.ctx.session_store,
                environment_name=self.ctx.environment_name,
                worktree_root=str(self.ctx.worktree_root or ""),
                create_cli_session=self.ctx.create_cli_session,
                resolve_project_workdir=self.ctx.resolve_project_workdir,
                detect_git_branch=self.ctx.detect_git_branch,
                build_session_seed_prompt=self.ctx.build_session_seed_prompt,
                decorate_session_display_fields=self.ctx.decorate_session_display_fields,
                apply_session_work_context=self.ctx.apply_session_work_context,
                load_project_execution_context=self.ctx.load_project_execution_context,
                project_exists=lambda pid: bool(self.ctx.find_project_cfg(pid))
                or bool(self.ctx.session_store.list_sessions(pid, include_deleted=True)),
                channel_exists=lambda pid, cname: self.ctx.project_channel_exists(pid, cname)
                or bool(self.ctx.session_store.list_sessions(pid, cname, include_deleted=True)),
            )
        except ValueError as e:
            self.ctx.json_response(handler, 400, {"error": str(e)})
            return
        except LookupError as e:
            self.ctx.json_response(handler, 404, {"error": str(e)})
            return
        except RuntimeError as e:
            self.ctx.json_response(
                handler,
                500,
                {"error": "create session failed", "detail": getattr(e, "detail", str(e))},
            )
            return
        self.ctx.json_response(handler, 200, payload_out)

    def _handle_session_dedup_post(self, handler: "BaseHTTPRequestHandler") -> None:
        """Handle POST /api/sessions/dedup."""
        if not self.ctx.require_token():
            return
        try:
            body = self.ctx.read_body_json(handler, max_bytes=10_000)
        except Exception as e:
            self.ctx.json_response(handler, 400, {"error": f"bad json: {e}"})
            return
        code, payload = runtime_dedup_session_channel_response(
            body=body,
            session_store=self.ctx.session_store,
            safe_text=self.ctx.safe_text,
            now_iso=self.ctx.now_iso,
            coerce_bool=self.ctx.coerce_bool,
        )
        self.ctx.json_response(handler, code, payload)

    def _handle_task_status_post(self, handler: "BaseHTTPRequestHandler") -> None:
        """Handle POST /api/tasks/status."""
        if not self.ctx.require_token():
            return
        try:
            body = self.ctx.read_body_json(handler, max_bytes=10_000)
        except Exception as e:
            self.ctx.json_response(handler, 400, {"error": f"bad json: {e}"})
            return

        task_path = self.ctx.safe_text(body.get("path"), 500).strip()
        new_status = self.ctx.safe_text(body.get("status"), 40).strip()
        project_id_hint = self.ctx.safe_text(
            body.get("project_id") if "project_id" in body else body.get("projectId"),
            80,
        ).strip()
        auto_start_raw = body.get("auto_start_ccb") if "auto_start_ccb" in body else body.get("autoStartCcb")
        auto_start_ccb = self.ctx.coerce_bool(auto_start_raw, True)
        auto_start_message = self.ctx.safe_text(
            body.get("auto_start_message") if "auto_start_message" in body else body.get("autoStartMessage"),
            20_000,
        ).strip()
        force_raw = body.get("force") if "force" in body else body.get("forceTransition")
        force_transition = self.ctx.coerce_bool(force_raw, False)

        if not task_path or not new_status:
            self.ctx.json_response(handler, 400, {"error": "missing path or status"})
            return

        try:
            gate = runtime_evaluate_task_status_gate(
                task_path,
                new_status,
                project_id_hint=project_id_hint,
            )
            gate["force_requested"] = bool(force_transition)
            if bool(gate.get("applies")) and not bool(gate.get("passed")):
                if force_transition:
                    gate["forced"] = True
                    gate["bypassed"] = True
                else:
                    self.ctx.json_response(
                        handler,
                        409,
                        {
                            "error": str(gate.get("summary") or "任务状态软门禁未通过"),
                            "gate": gate,
                        },
                    )
                    return
            result = runtime_change_task_status(task_path, new_status)
            auto_start = runtime_dispatch_task_status_auto_start(
                store=self.ctx.store,
                session_store=self.ctx.session_store,
                task_push_runtime=self.ctx.task_push_runtime,
                task_path=str(result.get("new_path") or task_path),
                old_status=str(result.get("old_status") or ""),
                new_status=str(result.get("new_status") or new_status),
                auto_start_ccb=auto_start_ccb,
                auto_start_message=auto_start_message,
                project_id_hint=project_id_hint,
            )
            result["auto_start"] = auto_start
            result["gate"] = gate
            self.ctx.json_response(handler, 200, result)
        except Exception as e:
            self.ctx.json_response(handler, 400, {"error": str(e)})

    def _handle_share_space_bootstrap_get(
        self,
        handler: "BaseHTTPRequestHandler",
        share_id: str,
        qs: dict[str, list[str]],
    ) -> None:
        project_id = self._share_project_id(qs)
        if not project_id:
            self.ctx.json_response(handler, 400, {"error": "missing project_id"})
            return
        access_token, passcode = self._extract_share_credentials(handler, qs)
        code, payload = runtime_build_share_bootstrap_response(
            worktree_root=self.ctx.worktree_root,
            environment_name=self.ctx.environment_name,
            project_id=project_id,
            share_id=share_id,
            access_token=access_token,
            passcode=passcode,
            session_store=self.ctx.session_store,
            decorate_session_display_fields=self.ctx.decorate_session_display_fields,
        )
        self.ctx.json_response(handler, code, payload)

    def _handle_share_space_session_get(
        self,
        handler: "BaseHTTPRequestHandler",
        share_id: str,
        session_id: str,
        qs: dict[str, list[str]],
    ) -> None:
        project_id = self._share_project_id(qs)
        if not project_id:
            self.ctx.json_response(handler, 400, {"error": "missing project_id"})
            return
        access_token, passcode = self._extract_share_credentials(handler, qs)
        limit_s = self._qs_first(qs, ("limit",), max_len=20)
        try:
            limit = max(1, min(100, int(limit_s or "30")))
        except Exception:
            limit = 30
        code, payload = runtime_build_share_session_response(
            worktree_root=self.ctx.worktree_root,
            environment_name=self.ctx.environment_name,
            project_id=project_id,
            share_id=share_id,
            session_id=session_id,
            access_token=access_token,
            passcode=passcode,
            session_store=self.ctx.session_store,
            store=self.ctx.store,
            decorate_session_display_fields=self.ctx.decorate_session_display_fields,
            limit=limit,
        )
        self.ctx.json_response(handler, code, payload)

    def _handle_share_space_announce_post(
        self,
        handler: "BaseHTTPRequestHandler",
        share_id: str,
        qs: dict[str, list[str]],
    ) -> None:
        try:
            body = self.ctx.read_body_json(handler, max_bytes=40_000)
        except Exception as e:
            self.ctx.json_response(handler, 400, {"error": f"bad json: {e}"})
            return
        body_dict = body if isinstance(body, dict) else {}
        project_id = self._share_project_id(qs, body_dict)
        if not project_id:
            self.ctx.json_response(handler, 400, {"error": "missing project_id"})
            return

        access_token, passcode = self._extract_share_credentials(handler, qs, body_dict)
        code, payload = runtime_build_share_announce_request(
            worktree_root=self.ctx.worktree_root,
            environment_name=self.ctx.environment_name,
            project_id=project_id,
            share_id=share_id,
            access_token=access_token,
            passcode=passcode,
            body=body_dict,
            session_store=self.ctx.session_store,
            decorate_session_display_fields=self.ctx.decorate_session_display_fields,
        )
        if code >= 400:
            self.ctx.json_response(handler, code, payload)
            return

        session_id = str(payload.get("session_id") or "")
        session_data = self.ctx.session_store.get_session(session_id)
        channel_name = str(payload.get("channel_name") or "")
        binding_reason = runtime_validate_announce_session_binding(
            session_data,
            project_id=project_id,
            channel_name=channel_name,
        )
        if binding_reason:
            self.ctx.json_response(
                handler,
                409,
                runtime_build_session_binding_required_payload(
                    project_id,
                    channel_name,
                    session_id,
                    session_data=session_data,
                    binding_reason=binding_reason,
                ),
            )
            return

        message = str(payload.get("message") or "")
        run_extra_fields = payload.get("extra_meta") if isinstance(payload.get("extra_meta"), dict) else {}
        message, run_extra_fields = runtime_apply_plan_first_to_message(message, run_extra_fields)
        _hydrate_reply_to_fields_from_store(self.ctx.store, run_extra_fields)
        attachments: list[dict[str, Any]] = []
        raw_attachments = body_dict.get("attachments")
        if isinstance(raw_attachments, list):
            for att in raw_attachments:
                if not isinstance(att, dict):
                    continue
                item = {
                    "filename": str(att.get("filename", "")),
                    "originalName": str(att.get("originalName", "")),
                    "url": str(att.get("url", "")),
                }
                target = self.ctx.resolve_attachment_local_path(self.ctx.store.runs_dir, item)
                if target is not None:
                    item["path"] = str(target)
                attachments.append(item)
        self.ctx.session_store.touch_session(session_id)
        run = self.ctx.store.create_run(
            project_id,
            channel_name,
            session_id,
            message,
            model=str(payload.get("model") or ""),
            cli_type=str(payload.get("cli_type") or "codex"),
            attachments=attachments if attachments else None,
            sender_type=str(payload.get("sender_type") or "user"),
            sender_id=str(payload.get("sender_id") or ""),
            sender_name=str(payload.get("sender_name") or ""),
            extra_meta=run_extra_fields,
            reasoning_effort=str(payload.get("reasoning_effort") or ""),
        )
        runtime_enqueue_run_for_dispatch(
            self.ctx.store,
            str(run.get("id") or ""),
            session_id,
            str(payload.get("cli_type") or "codex"),
            self.ctx.scheduler,
        )
        self.ctx.json_response(
            handler,
            200,
            {
                "ok": True,
                "project_id": project_id,
                "share_id": str(payload.get("share_id") or share_id),
                "run": run,
            },
        )

    def _handle_codex_announce_post(self, handler: "BaseHTTPRequestHandler") -> None:
        """Handle POST /api/codex/announce."""
        if not self.ctx.require_token():
            return

        try:
            body = self.ctx.read_body_json(handler)
        except Exception as e:
            self.ctx.json_response(handler, 400, {"error": f"bad json: {e}"})
            return

        cli_type = ""
        session_data: dict[str, Any] | None = None
        raw_session_id = self.ctx.safe_text(body.get("sessionId"), 80).strip()
        session_id = raw_session_id
        if session_id:
            session_data = self.ctx.session_store.get_session(session_id)
            if session_data:
                cli_type = str(session_data.get("cli_type") or "").strip()
                self.ctx.session_store.touch_session(session_id)

        local_host = str(getattr(handler.server, "server_address", ("127.0.0.1", 0))[0] or "")
        parsed_announce = runtime_parse_announce_request(
            body,
            extract_sender_fields=self.ctx.extract_sender_fields,
            extract_run_extra_fields=self.ctx.extract_run_extra_fields,
            derive_session_work_context=self.ctx.derive_session_work_context,
            coerce_bool=self.ctx.coerce_bool,
            build_local_server_origin=self.ctx.build_local_server_origin,
            load_project_execution_context=self.ctx.load_project_execution_context,
            session_data=session_data,
            environment_name=self.ctx.environment_name,
            worktree_root=self.ctx.worktree_root,
            local_server_host=local_host,
            local_server_port=self.ctx.server_port,
            project_id_from_session=str((session_data or {}).get("project_id") or ""),
        )
        project_id = str(parsed_announce.get("project_id") or "")
        channel_name = str(parsed_announce.get("channel_name") or "")
        profile_label = str(parsed_announce.get("profile_label") or "")
        model = str(parsed_announce.get("model") or "")
        reasoning_effort = str(parsed_announce.get("reasoning_effort") or "")
        message = str(parsed_announce.get("message") or "")
        sender_fields = parsed_announce.get("sender_fields") or {}
        run_extra_fields = parsed_announce.get("run_extra_fields") or {}

        if session_data:
            if not model:
                model = str(session_data.get("model") or "").strip()
            if not reasoning_effort:
                reasoning_effort = _normalize_reasoning_effort(session_data.get("reasoning_effort"))
        if not cli_type:
            cli_type = self.ctx.safe_text(body.get("cliType"), 40).strip() or "codex"

        attachments: list[dict[str, Any]] = []
        raw_attachments = body.get("attachments")
        if isinstance(raw_attachments, list):
            for att in raw_attachments:
                if not isinstance(att, dict):
                    continue
                item = {
                    "filename": str(att.get("filename", "")),
                    "originalName": str(att.get("originalName", "")),
                    "url": str(att.get("url", "")),
                }
                target = self.ctx.resolve_attachment_local_path(self.ctx.store.runs_dir, item)
                if target is not None:
                    item["path"] = str(target)
                attachments.append(item)

        if not project_id or not channel_name:
            self.ctx.json_response(handler, 400, {"error": "missing projectId/channelName"})
            return
        if not session_id or not self.ctx.looks_like_uuid(session_id):
            self.ctx.json_response(handler, 400, {"error": "missing/invalid sessionId"})
            return

        binding_reason = runtime_validate_announce_session_binding(
            session_data,
            project_id=project_id,
            channel_name=channel_name,
        )
        if binding_reason:
            self.ctx.json_response(
                handler,
                409,
                runtime_build_session_binding_required_payload(
                    project_id,
                    channel_name,
                    session_id,
                    session_data=session_data,
                    binding_reason=binding_reason,
                ),
            )
            return

        self.ctx.session_store.touch_session(session_id)
        if not message:
            self.ctx.json_response(handler, 400, {"error": "missing message"})
            return

        message, run_extra_fields = runtime_apply_plan_first_to_message(message, run_extra_fields)
        _hydrate_reply_to_fields_from_store(self.ctx.store, run_extra_fields)
        run = self.ctx.store.create_run(
            project_id,
            channel_name,
            session_id,
            message,
            profile_label=profile_label,
            model=model,
            cli_type=cli_type,
            attachments=attachments if attachments else None,
            sender_type=sender_fields["sender_type"],
            sender_id=sender_fields["sender_id"],
            sender_name=sender_fields["sender_name"],
            extra_meta=run_extra_fields,
            reasoning_effort=reasoning_effort,
        )

        runtime_enqueue_run_for_dispatch(
            self.ctx.store,
            str(run.get("id") or ""),
            session_id,
            cli_type,
            self.ctx.scheduler,
        )
        self.ctx.json_response(handler, 200, {"run": run})

    def _handle_session_new_post(self, handler: "BaseHTTPRequestHandler") -> None:
        """Handle POST /api/codex/session/new."""
        if not self.ctx.require_token():
            return
        try:
            body = self.ctx.read_body_json(handler, max_bytes=40_000)
        except Exception:
            body = {}
        project_id = self.ctx.safe_text(body.get("projectId"), 80).strip()
        channel_name = self.ctx.safe_text(body.get("channelName"), 200).strip()
        note = self.ctx.safe_text(body.get("note"), 220).strip()
        cli_type = self.ctx.safe_text(body.get("cliType"), 40).strip() or "codex"
        model = self.ctx.safe_text(body.get("model"), 120).strip()
        reasoning_effort = _normalize_reasoning_effort(
            body.get("reasoning_effort") if "reasoning_effort" in body else body.get("reasoningEffort")
        )
        first_message = self.ctx.safe_text(
            body.get("firstMessage") if "firstMessage" in body else body.get("first_message"),
            20_000,
        ).strip()
        seed = self.ctx.build_session_seed_prompt(
            project_id=project_id,
            channel_name=channel_name,
            note=note,
            first_message=first_message,
        )
        project_workdir = self.ctx.resolve_project_workdir(project_id)
        project_execution_context = (
            self.ctx.load_project_execution_context(
                project_id=project_id,
                environment_name=self.ctx.environment_name,
                worktree_root=str(self.ctx.worktree_root or ""),
            )
            if project_id
            else {}
        )
        result = self.ctx.create_cli_session(
            seed_prompt=seed,
            timeout_s=90,
            cli_type=cli_type,
            workdir=project_workdir,
            model=model,
            reasoning_effort=reasoning_effort,
            execution_profile=runtime_normalize_execution_profile(
                (project_execution_context if isinstance(project_execution_context, dict) else {}).get("profile"),
                allow_empty=True,
            ),
        )
        if not result.get("ok"):
            self.ctx.json_response(handler, 500, {"error": "create session failed", "detail": result})
            return
        self.ctx.json_response(
            handler,
            200,
            {
                "sessionId": result.get("sessionId"),
                "sessionPath": result.get("sessionPath", ""),
                "cliType": result.get("cliType", cli_type),
                "model": model,
                "reasoning_effort": reasoning_effort,
                "workdir": result.get("workdir", str(project_workdir)),
            },
        )

    def _handle_fs_reveal_post(self, handler: "BaseHTTPRequestHandler") -> None:
        """Handle POST /api/fs/reveal."""
        if not self.ctx.require_token():
            return
        try:
            body = self.ctx.read_body_json(handler)
        except Exception as e:
            self.ctx.json_response(handler, 400, {"error": f"bad json: {e}"})
            return

        path_raw = self.ctx.safe_text(body.get("path"), 4000).strip()
        if not path_raw:
            self.ctx.json_response(handler, 400, {"error": "missing path"})
            return

        try:
            resolved = self.ctx.resolve_allowed_fs_path(path_raw)

            cmd = ["open", str(resolved)] if resolved.is_dir() else ["open", "-R", str(resolved)]
            subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        except FileNotFoundError:
            self.ctx.json_response(handler, 404, {"error": "path not found"})
            return
        except ValueError as exc:
            self.ctx.json_response(handler, 400, {"error": str(exc)})
            return
        except Exception as e:
            self.ctx.json_response(handler, 500, {"error": f"reveal failed: {e}"})
            return

        self.ctx.json_response(handler, 200, {"ok": True})

    def _handle_upload_post(self, handler: "BaseHTTPRequestHandler") -> None:
        """Handle POST /api/codex/upload."""
        if not self.ctx.require_token():
            return
        try:
            content_type = handler.headers.get("Content-Type", "")
            if "multipart/form-data" not in content_type:
                self.ctx.json_response(
                    handler,
                    400,
                    {"error": "invalid_upload", "message": "expected multipart/form-data"},
                )
                return

            boundary = ""
            for part in content_type.split(";"):
                if "boundary=" in part:
                    boundary = part.split("boundary=")[1].strip().strip('"')
                    break
            if not boundary:
                self.ctx.json_response(handler, 400, {"error": "invalid_upload", "message": "missing boundary"})
                return

            try:
                content_length = int(handler.headers.get("Content-Length", 0))
            except Exception:
                content_length = 0
            max_bytes = self.ctx.upload_max_bytes()
            if content_length <= 0:
                self.ctx.json_response(handler, 400, {"error": "invalid_upload", "message": "missing content"})
                return
            if content_length > max_bytes:
                self.ctx.json_response(
                    handler,
                    400,
                    {
                        "error": "file_too_large",
                        "message": f"file too large (max {max_bytes // (1024 * 1024)}MB)",
                    },
                )
                return

            body = handler.rfile.read(content_length)
            try:
                filename, file_content, mime_type = self.ctx.parse_multipart_single_file(body, boundary)
            except ValueError as e:
                self.ctx.json_response(handler, 400, {"error": "invalid_upload", "message": str(e)})
                return

            safe_name = self.ctx.sanitize_upload_filename(filename)
            unique_name = f"{int(time.time() * 1000)}-{secrets.token_hex(4)}-{safe_name}"
            if not file_content:
                self.ctx.json_response(handler, 400, {"error": "invalid_upload", "message": "empty file"})
                return

            attach_dir = (self.ctx.store.runs_dir / "attachments").resolve()
            attach_dir.mkdir(parents=True, exist_ok=True)
            file_path = (attach_dir / unique_name).resolve()
            if file_path.parent != attach_dir:
                self.ctx.json_response(handler, 400, {"error": "invalid_upload", "message": "invalid filename"})
                return
            file_path.write_bytes(file_content)

            self.ctx.json_response(
                handler,
                200,
                {
                    "ok": True,
                    "filename": unique_name,
                    "originalName": filename,
                    "url": f"/.runs/attachments/{unique_name}",
                    "mimeType": mime_type or "application/octet-stream",
                    "size": len(file_content),
                },
            )
        except Exception as e:
            self.ctx.json_response(handler, 500, {"error": "upload_failed", "message": f"upload failed: {e}"})

    def _handle_binding_save_post(self, handler: "BaseHTTPRequestHandler") -> None:
        """Handle POST /api/sessions/bindings/save."""
        if not self.ctx.require_token():
            return
        try:
            body = self.ctx.read_body_json(handler, max_bytes=10_000)
        except Exception as e:
            self.ctx.json_response(handler, 400, {"error": f"bad json: {e}"})
            return
        session_id = self.ctx.safe_text(body.get("sessionId"), 80).strip()
        project_id = self.ctx.safe_text(body.get("projectId"), 80).strip()
        channel_name = self.ctx.safe_text(body.get("channelName"), 200).strip()
        cli_type = self.ctx.safe_text(body.get("cliType"), 40).strip() or "codex"
        if not session_id or not project_id or not channel_name:
            self.ctx.json_response(handler, 400, {"error": "missing required fields"})
            return
        self.ctx.json_response(
            handler,
            200,
            runtime_save_binding_response(
                session_binding_store=self.ctx.session_binding_store,
                session_id=session_id,
                project_id=project_id,
                channel_name=channel_name,
                cli_type=cli_type,
            ),
        )

    def _handle_binding_delete_post(self, handler: "BaseHTTPRequestHandler") -> None:
        """Handle POST /api/sessions/bindings/delete."""
        if not self.ctx.require_token():
            return
        try:
            body = self.ctx.read_body_json(handler, max_bytes=10_000)
        except Exception as e:
            self.ctx.json_response(handler, 400, {"error": f"bad json: {e}"})
            return
        session_id = self.ctx.safe_text(body.get("sessionId"), 80).strip()
        if not session_id:
            self.ctx.json_response(handler, 400, {"error": "missing sessionId"})
            return
        self.ctx.json_response(
            handler,
            200,
            runtime_delete_binding_response(
                session_binding_store=self.ctx.session_binding_store,
                session_id=session_id,
            ),
        )

    def _handle_channel_bootstrap_post(self, handler: "BaseHTTPRequestHandler") -> None:
        """Handle POST /api/channels/bootstrap-codex."""
        if not self.ctx.require_token():
            return
        try:
            body = self.ctx.read_body_json(handler, max_bytes=64_000)
        except Exception as e:
            self.ctx.json_response(handler, 400, {"error": "bad json", "message": str(e), "step": "request_parse"})
            return
        project_id = self.ctx.safe_text(body.get("projectId"), 80).strip()
        channel_kind_mode = self.ctx.safe_text(body.get("channelKindMode"), 20).strip().lower()
        channel_kind_raw = self.ctx.safe_text(body.get("channelKind"), 20).strip()
        channel_kind_custom = self.ctx.safe_text(body.get("channelKindCustom"), 20).strip()
        if channel_kind_raw == "__custom__":
            channel_kind_mode = "custom"
        channel_kind = channel_kind_custom if channel_kind_mode == "custom" else channel_kind_raw
        channel_kind = self.ctx.safe_text(channel_kind, 20).strip()
        channel_index = self.ctx.safe_text(body.get("channelIndex"), 40).strip()
        channel_name = self.ctx.safe_text(body.get("channelName"), 200).strip()
        task_title = self.ctx.safe_text(body.get("taskTitle"), 300).strip()
        goal = self.ctx.safe_text(body.get("goal"), 4000).strip()
        channel_scope = self.ctx.safe_text(body.get("channelScope"), 300).strip()
        desc = self.ctx.safe_text(body.get("desc"), 500).strip()
        session_alias = self.ctx.safe_text(body.get("sessionAlias"), 120).strip()
        missing: list[str] = []
        if not project_id:
            missing.append("projectId")
        if not channel_kind:
            missing.append("channelKind")
        if not channel_index:
            missing.append("channelIndex")
        if not channel_name:
            missing.append("channelName")
        if not task_title:
            missing.append("taskTitle")
        if missing:
            self.ctx.json_response(
                handler,
                400,
                {
                    "error": "missing required fields",
                    "message": "missing: " + ", ".join(missing),
                    "step": "request_validate",
                },
            )
            return
        if any(ch in '/\\:*?"<>|' for ch in channel_kind):
            self.ctx.json_response(
                handler,
                400,
                {
                    "error": "invalid channelKind",
                    "message": "channelKind contains invalid characters",
                    "step": "request_validate",
                },
            )
            return
        code, payload = self.ctx.run_codex_channel_bootstrap(
            project_id=project_id,
            channel_kind=channel_kind,
            channel_index=channel_index,
            channel_name=channel_name,
            task_title=task_title,
            goal=goal,
            channel_scope=channel_scope,
            desc=desc,
            session_alias=session_alias,
            port=self.ctx.server_port,
        )
        self.ctx.json_response(handler, code, payload)

    def _channel_root_path(self, project_id: str, channel_name: str) -> str:
        project_cfg = self.ctx.find_project_cfg(project_id) or {}
        task_root_rel = str((project_cfg.get("task_root_rel") or "")).strip()
        if not task_root_rel:
            return ""
        try:
            task_root = runtime_resolve_task_root_path(repo_root=self.ctx.repo_root(), task_root_rel=task_root_rel)
            return str((task_root / channel_name).resolve())
        except Exception:
            return str(runtime_resolve_task_root_path(repo_root=self.ctx.repo_root(), task_root_rel=task_root_rel) / channel_name)

    def _build_channel_bootstrap_v3_response(
        self,
        *,
        project_id: str,
        channel_name: str,
        channel_theme: str,
        channel_desc: str,
        create_result: dict[str, Any],
        mode: str,
        dispatch: dict[str, Any] | None = None,
        target_session: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        framework_path = self._channel_root_path(project_id, channel_name)
        readme_path = f"{framework_path}/README.md" if framework_path else ""
        inbox_path = ""
        if framework_path:
            candidate = Path(framework_path) / "沟通-收件箱.md"
            if candidate.exists():
                inbox_path = str(candidate)
        payload: dict[str, Any] = {
            "ok": True,
            "status": "done",
            "mode": mode,
            "projectId": project_id,
            "channelName": channel_name,
            "channelTheme": channel_theme,
            "channelDesc": channel_desc or channel_name,
            "framework": {
                "created": bool(create_result.get("ok")),
                "cliType": create_result.get("cli_type", "codex"),
                "configPath": str(self.ctx.config_toml_path()),
                "channelRootPath": framework_path,
                "readmePath": readme_path,
                "inboxPath": inbox_path,
            },
            "resultPath": str(self.ctx.config_toml_path()),
        }
        if target_session:
            payload["targetSession"] = {
                "sessionId": str(target_session.get("sessionId") or target_session.get("session_id") or target_session.get("id") or ""),
                "channelName": str(
                    target_session.get("channel_name")
                    or target_session.get("primaryChannel")
                    or target_session.get("channelName")
                    or ""
                ).strip(),
                "alias": str(target_session.get("alias") or "").strip(),
                "cliType": str(target_session.get("cli_type") or target_session.get("cliType") or "codex").strip(),
                "model": str(target_session.get("model") or "").strip(),
                "reasoningEffort": _normalize_reasoning_effort(
                    target_session.get("reasoning_effort") if "reasoning_effort" in target_session else target_session.get("reasoningEffort")
                ),
            }
        if dispatch:
            payload["dispatch"] = dispatch
        return payload

    def _build_channel_dispatch_response(
        self,
        *,
        project_id: str,
        channel_name: str,
        target_session: dict[str, Any] | None,
        dispatch: dict[str, Any],
        action: str,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "ok": True,
            "status": "done",
            "action": action,
            "projectId": project_id,
            "channelName": channel_name,
            "dispatch": dispatch,
        }
        if target_session:
            payload["targetSession"] = {
                "sessionId": str(target_session.get("sessionId") or target_session.get("session_id") or target_session.get("id") or ""),
                "channelName": str(
                    target_session.get("channel_name")
                    or target_session.get("primaryChannel")
                    or target_session.get("channelName")
                    or ""
                ).strip(),
                "alias": str(target_session.get("alias") or "").strip(),
                "cliType": str(target_session.get("cli_type") or target_session.get("cliType") or "codex").strip(),
                "model": str(target_session.get("model") or "").strip(),
                "reasoningEffort": _normalize_reasoning_effort(
                    target_session.get("reasoning_effort") if "reasoning_effort" in target_session else target_session.get("reasoningEffort")
                ),
            }
        return payload

    def _handle_channel_bootstrap_v3_post(self, handler: "BaseHTTPRequestHandler") -> None:
        """Handle POST /api/channels/bootstrap-v3."""
        if not self.ctx.require_token():
            return
        try:
            body = self.ctx.read_body_json(handler, max_bytes=64_000)
        except Exception as e:
            self.ctx.json_response(handler, 400, {"error": "bad json", "message": str(e), "step": "request_parse"})
            return

        req = runtime_normalize_channel_bootstrap_v3_request(body)
        project_id = str(req.get("project_id") or "").strip()
        mode = str(req.get("mode") or "direct").strip().lower()
        channel_kind = str(req.get("channel_kind") or "").strip()
        channel_index = str(req.get("channel_index") or "").strip()
        channel_name = str(req.get("channel_name") or "").strip()
        channel_theme = str(req.get("channel_theme") or "").strip()
        channel_desc = str(req.get("channel_desc") or "").strip()
        target_session_id = str(req.get("target_session_id") or "").strip()
        business_requirement = str(req.get("business_requirement") or "").strip()
        prompt_preset = str(req.get("prompt_preset") or "channel_create_assist_v1").strip()
        source_session_id = str(req.get("source_session_id") or "").strip()
        source_channel_name = str(req.get("source_channel_name") or "").strip()
        source_agent_name = str(req.get("source_agent_name") or "任务看板").strip()
        source_agent_alias = str(req.get("source_agent_alias") or "").strip()
        source_agent_id = str(req.get("source_agent_id") or "task_dashboard").strip() or "task_dashboard"

        missing: list[str] = []
        if not project_id:
            missing.append("projectId")
        if not channel_kind:
            missing.append("channelKind")
        if not channel_index:
            missing.append("channelIndex")
        if not channel_name:
            missing.append("channelName")
        if mode not in {"direct", "agent_assist"}:
            self.ctx.json_response(
                handler,
                400,
                {
                    "error": "invalid mode",
                    "message": "mode must be one of: direct, agent_assist",
                    "step": "request_validate",
                },
            )
            return
        if mode == "agent_assist":
            if not target_session_id:
                missing.append("targetSessionId")
            if not business_requirement:
                missing.append("businessRequirement")
        if missing:
            self.ctx.json_response(
                handler,
                400,
                {
                    "error": "missing required fields",
                    "message": "missing: " + ", ".join(missing),
                    "step": "request_validate",
                },
            )
            return
        if any(ch in '/\\:*?"<>|' for ch in channel_kind):
            self.ctx.json_response(
                handler,
                400,
                {
                    "error": "invalid channelKind",
                    "message": "channelKind contains invalid characters",
                    "step": "request_validate",
                },
            )
            return

        target_session: dict[str, Any] | None = None
        if mode == "agent_assist":
            resolved_target = self.ctx.session_store.get_session(target_session_id)
            if not isinstance(resolved_target, dict):
                self.ctx.json_response(
                    handler,
                    404,
                    {
                        "error": "target session not found",
                        "message": f"session not found: {target_session_id}",
                        "step": "resolve_target_session",
                    },
                )
                return
            target_project_id = str(resolved_target.get("project_id") or "").strip()
            if target_project_id and target_project_id != project_id:
                self.ctx.json_response(
                    handler,
                    409,
                    {
                        "error": "target session project mismatch",
                        "message": f"target session belongs to {target_project_id}, expected {project_id}",
                        "step": "resolve_target_session",
                    },
                )
                return
            target_session = resolved_target

        try:
            create_result = self.ctx.create_channel(project_id, channel_name, channel_desc or channel_name, "codex")
            runtime_clear_dashboard_cfg_cache()
        except ValueError as e:
            message = str(e)
            if "already exists" in message.lower():
                runtime_clear_dashboard_cfg_cache()
                self.ctx.json_response(
                    handler,
                    409,
                    {
                        "error": "channel already exists",
                        "message": message,
                        "step": "create_channel",
                        "projectId": project_id,
                        "channelName": channel_name,
                        "channelExistsInProject": bool(self.ctx.project_channel_exists(project_id, channel_name)),
                    },
                )
                return
            self.ctx.json_response(
                handler,
                400,
                {"error": "invalid channel request", "message": message, "step": "create_channel"},
            )
            return
        except Exception as e:
            self.ctx.json_response(
                handler,
                500,
                {"error": "create channel failed", "message": str(e), "step": "create_channel"},
            )
            return

        if mode == "direct":
            self.ctx.json_response(
                handler,
                200,
                self._build_channel_bootstrap_v3_response(
                    project_id=project_id,
                    channel_name=channel_name,
                    channel_theme=channel_theme or channel_name,
                    channel_desc=channel_desc or channel_name,
                    create_result=create_result,
                    mode=mode,
                ),
            )
            return

        target_payload = runtime_build_channel_assist_message_payload(
            project_id=project_id,
            created_channel_name=channel_name,
            created_channel_theme=channel_theme or channel_name,
            created_channel_desc=channel_desc or channel_name,
            target_session=target_session,
            business_requirement=business_requirement,
            prompt_preset=prompt_preset,
            source_session_id=source_session_id,
            source_channel_name=source_channel_name or channel_name,
            source_agent_name=source_agent_name,
            source_agent_alias=source_agent_alias,
            source_agent_id=source_agent_id,
        )
        message = str(target_payload.get("message") or "").strip()
        sender_fields = target_payload.get("sender_fields") or {}
        run_extra_fields = target_payload.get("run_extra_fields") or {}
        target_session_id = str(target_payload.get("target_session_id") or "").strip()
        target_channel_name = str(target_payload.get("target_session_channel_name") or "").strip()
        target_alias = str(target_payload.get("target_session_alias") or "").strip()
        target_cli_type = str(target_payload.get("target_cli_type") or "codex").strip() or "codex"
        target_model = str(target_payload.get("target_model") or "").strip()
        target_reasoning_effort = str(target_payload.get("target_reasoning_effort") or "").strip()

        if not message:
            self.ctx.json_response(
                handler,
                500,
                {"error": "build dispatch message failed", "step": "build_dispatch_message"},
            )
            return

        run = self.ctx.store.create_run(
            project_id,
            target_channel_name or channel_name,
            target_session_id,
            message,
            model=target_model,
            cli_type=target_cli_type,
            sender_type=str(sender_fields.get("sender_type") or "agent"),
            sender_id=str(sender_fields.get("sender_id") or source_agent_id or "task_dashboard"),
            sender_name=str(sender_fields.get("sender_name") or source_agent_alias or source_agent_name or "任务看板"),
            extra_meta=run_extra_fields,
            reasoning_effort=target_reasoning_effort,
        )
        runtime_enqueue_run_for_dispatch(
            self.ctx.store,
            str(run.get("id") or ""),
            target_session_id,
            target_cli_type,
            self.ctx.scheduler,
        )

        dispatch_payload = {
            "runId": str(run.get("id") or ""),
            "runStatus": str(run.get("status") or "queued"),
            "projectId": project_id,
            "channelName": target_channel_name or channel_name,
            "sessionId": target_session_id,
            "alias": target_alias,
            "cliType": target_cli_type,
            "senderType": str(sender_fields.get("sender_type") or "agent"),
            "senderId": str(sender_fields.get("sender_id") or source_agent_id or "task_dashboard"),
            "senderName": str(sender_fields.get("sender_name") or source_agent_alias or source_agent_name or "任务看板"),
            "messageKind": str((run_extra_fields or {}).get("message_kind") or "collab_update"),
            "interactionMode": str((run_extra_fields or {}).get("interaction_mode") or "task_with_receipt"),
            "sourceRef": (run_extra_fields or {}).get("source_ref") or {},
            "targetRef": (run_extra_fields or {}).get("target_ref") or {},
            "callbackTo": (run_extra_fields or {}).get("callback_to") or {},
            "senderAgentRef": (run_extra_fields or {}).get("sender_agent_ref") or {},
            "targetAgentRef": (run_extra_fields or {}).get("target_agent_ref") or {},
        }

        self.ctx.json_response(
            handler,
            200,
            self._build_channel_bootstrap_v3_response(
                project_id=project_id,
                channel_name=channel_name,
                channel_theme=channel_theme or channel_name,
                channel_desc=channel_desc or channel_name,
                create_result=create_result,
                mode=mode,
                dispatch=dispatch_payload,
                target_session=target_session,
            ),
        )

    def _handle_channel_request_edit_post(self, handler: "BaseHTTPRequestHandler") -> None:
        """Handle POST /api/channels/request-edit."""
        if not self.ctx.require_token():
            return
        try:
            body = self.ctx.read_body_json(handler, max_bytes=64_000)
        except Exception as e:
            self.ctx.json_response(handler, 400, {"error": "bad json", "message": str(e), "step": "request_parse"})
            return

        req = runtime_normalize_channel_request_edit_request(body)
        project_id = str(req.get("project_id") or "").strip()
        channel_name = str(req.get("channel_name") or "").strip()
        channel_desc = str(req.get("channel_desc") or "").strip()
        target_session_id = str(req.get("target_session_id") or "").strip()
        business_requirement = str(req.get("business_requirement") or "").strip()
        source_session_id = str(req.get("source_session_id") or "").strip()
        source_channel_name = str(req.get("source_channel_name") or "").strip()
        source_agent_name = str(req.get("source_agent_name") or "任务看板").strip()
        source_agent_alias = str(req.get("source_agent_alias") or "").strip()
        source_agent_id = str(req.get("source_agent_id") or "task_dashboard").strip() or "task_dashboard"

        missing: list[str] = []
        if not project_id:
            missing.append("projectId")
        if not channel_name:
            missing.append("channelName")
        if not target_session_id:
            missing.append("targetSessionId")
        if not business_requirement:
            missing.append("businessRequirement")
        if missing:
            self.ctx.json_response(
                handler,
                400,
                {
                    "error": "missing required fields",
                    "message": "missing: " + ", ".join(missing),
                    "step": "request_validate",
                },
            )
            return

        resolved_target = self.ctx.session_store.get_session(target_session_id)
        if not isinstance(resolved_target, dict):
            self.ctx.json_response(
                handler,
                404,
                {
                    "error": "target session not found",
                    "message": f"session not found: {target_session_id}",
                    "step": "resolve_target_session",
                },
            )
            return
        target_project_id = str(resolved_target.get("project_id") or "").strip()
        if target_project_id and target_project_id != project_id:
            self.ctx.json_response(
                handler,
                409,
                {
                    "error": "target session project mismatch",
                    "message": f"target session belongs to {target_project_id}, expected {project_id}",
                    "step": "resolve_target_session",
                },
            )
            return

        target_payload = runtime_build_channel_edit_request_message_payload(
            project_id=project_id,
            channel_name=channel_name,
            channel_desc=channel_desc or channel_name,
            target_session=resolved_target,
            business_requirement=business_requirement,
            source_session_id=source_session_id,
            source_channel_name=source_channel_name or channel_name,
            source_agent_name=source_agent_name,
            source_agent_alias=source_agent_alias,
            source_agent_id=source_agent_id,
        )
        message = str(target_payload.get("message") or "").strip()
        sender_fields = target_payload.get("sender_fields") or {}
        run_extra_fields = target_payload.get("run_extra_fields") or {}
        target_session_id = str(target_payload.get("target_session_id") or "").strip()
        target_channel_name = str(target_payload.get("target_session_channel_name") or "").strip()
        target_alias = str(target_payload.get("target_session_alias") or "").strip()
        target_cli_type = str(target_payload.get("target_cli_type") or "codex").strip() or "codex"
        target_model = str(target_payload.get("target_model") or "").strip()
        target_reasoning_effort = str(target_payload.get("target_reasoning_effort") or "").strip()

        if not message:
            self.ctx.json_response(
                handler,
                500,
                {"error": "build dispatch message failed", "step": "build_dispatch_message"},
            )
            return

        run = self.ctx.store.create_run(
            project_id,
            target_channel_name or channel_name,
            target_session_id,
            message,
            model=target_model,
            cli_type=target_cli_type,
            sender_type=str(sender_fields.get("sender_type") or "agent"),
            sender_id=str(sender_fields.get("sender_id") or source_agent_id or "task_dashboard"),
            sender_name=str(sender_fields.get("sender_name") or source_agent_alias or source_agent_name or "任务看板"),
            extra_meta=run_extra_fields,
            reasoning_effort=target_reasoning_effort,
        )
        runtime_enqueue_run_for_dispatch(
            self.ctx.store,
            str(run.get("id") or ""),
            target_session_id,
            target_cli_type,
            self.ctx.scheduler,
        )

        dispatch_payload = {
            "runId": str(run.get("id") or ""),
            "runStatus": str(run.get("status") or "queued"),
            "projectId": project_id,
            "channelName": target_channel_name or channel_name,
            "sessionId": target_session_id,
            "alias": target_alias,
            "cliType": target_cli_type,
            "senderType": str(sender_fields.get("sender_type") or "agent"),
            "senderId": str(sender_fields.get("sender_id") or source_agent_id or "task_dashboard"),
            "senderName": str(sender_fields.get("sender_name") or source_agent_alias or source_agent_name or "任务看板"),
            "messageKind": str((run_extra_fields or {}).get("message_kind") or "collab_update"),
            "interactionMode": str((run_extra_fields or {}).get("interaction_mode") or "task_with_receipt"),
            "sourceRef": (run_extra_fields or {}).get("source_ref") or {},
            "targetRef": (run_extra_fields or {}).get("target_ref") or {},
            "callbackTo": (run_extra_fields or {}).get("callback_to") or {},
            "senderAgentRef": (run_extra_fields or {}).get("sender_agent_ref") or {},
            "targetAgentRef": (run_extra_fields or {}).get("target_agent_ref") or {},
        }
        self.ctx.json_response(
            handler,
            200,
            self._build_channel_dispatch_response(
                project_id=project_id,
                channel_name=channel_name,
                target_session=resolved_target,
                dispatch=dispatch_payload,
                action="request_edit",
            ),
        )

    def _handle_channel_delete_post(self, handler: "BaseHTTPRequestHandler") -> None:
        """Handle POST /api/channels/delete."""
        if not self.ctx.require_token():
            return
        try:
            body = self.ctx.read_body_json(handler, max_bytes=32_000)
        except Exception as e:
            self.ctx.json_response(handler, 400, {"error": "bad json", "message": str(e), "step": "request_parse"})
            return

        project_id = self.ctx.safe_text(
            body.get("projectId") if "projectId" in body else body.get("project_id"),
            120,
        ).strip()
        channel_name = self.ctx.safe_text(
            body.get("channelName") if "channelName" in body else body.get("channel_name"),
            200,
        ).strip()
        confirm_name = self.ctx.safe_text(
            body.get("confirmChannelName") if "confirmChannelName" in body else body.get("confirm_channel_name"),
            200,
        ).strip()
        reason = self.ctx.safe_text(body.get("reason"), 500).strip()
        if not project_id:
            self.ctx.json_response(handler, 400, {"error": "missing projectId", "step": "request_validate"})
            return
        if not channel_name:
            self.ctx.json_response(handler, 400, {"error": "missing channelName", "step": "request_validate"})
            return
        if confirm_name != channel_name:
            self.ctx.json_response(
                handler,
                400,
                {
                    "error": "confirmChannelName mismatch",
                    "message": "confirmChannelName must match channelName exactly",
                    "step": "request_validate",
                },
            )
            return

        project_cfg = self.ctx.find_project_cfg(project_id)
        if not isinstance(project_cfg, dict):
            self.ctx.json_response(handler, 404, {"error": "project not found", "step": "resolve_project"})
            return
        task_root_rel = str(project_cfg.get("task_root_rel") or "").strip()
        if not task_root_rel:
            self.ctx.json_response(
                handler,
                409,
                {"error": "task_root_rel missing", "step": "resolve_project"},
            )
            return

        channel_root_path = self._channel_root_path(project_id, channel_name)
        channel_root_exists = bool(channel_root_path) and Path(channel_root_path).exists()
        existing_sessions = self.ctx.session_store.list_sessions(project_id, channel_name, include_deleted=True)
        existing_bindings = [
            row for row in self.ctx.session_binding_store.list_bindings(project_id)
            if str((row or {}).get("channelName") or "").strip() == channel_name
        ]
        channel_exists = bool(self.ctx.project_channel_exists(project_id, channel_name)) or channel_root_exists or bool(existing_sessions) or bool(existing_bindings)
        if not channel_exists:
            self.ctx.json_response(
                handler,
                404,
                {
                    "error": "channel not found",
                    "message": f"channel not found: {channel_name}",
                    "step": "resolve_channel",
                },
            )
            return

        updates = []
        for row in existing_sessions:
            session_id = str((row or {}).get("id") or "").strip()
            if not session_id:
                continue
            updates.append(
                {
                    "session_id": session_id,
                    "is_deleted": True,
                    "deleted_reason": reason or "channel_deleted",
                }
            )

        try:
            managed = runtime_manage_channel_sessions_response(
                session_store=self.ctx.session_store,
                project_id=project_id,
                channel_name=channel_name,
                primary_session_id="",
                updates=updates,
                decorate_sessions_display_fields=self.ctx.decorate_sessions_display_fields,
            )
            deleted_binding_session_ids: list[str] = []
            for binding in existing_bindings:
                session_id = str((binding or {}).get("sessionId") or "").strip()
                if not session_id:
                    continue
                if self.ctx.session_binding_store.delete_binding(session_id):
                    deleted_binding_session_ids.append(session_id)
            delete_result = runtime_delete_channel(
                project_id=project_id,
                channel_name=channel_name,
                config_path=self.ctx.config_toml_path(),
                repo_root=self.ctx.repo_root(),
                task_root_rel=task_root_rel,
                atomic_write_text=runtime_atomic_write_text,
            )
            runtime_clear_dashboard_cfg_cache()
        except Exception as e:
            self.ctx.json_response(
                handler,
                500,
                {"error": "delete channel failed", "message": str(e), "step": "delete_channel"},
            )
            return

        self.ctx.json_response(
            handler,
            200,
            {
                "ok": True,
                "status": "done",
                "action": "delete_channel",
                "projectId": project_id,
                "channelName": channel_name,
                "deleted": {
                    "configEntry": bool(delete_result.get("removed_from_config")),
                    "channelRootPath": str(delete_result.get("channel_root_path") or ""),
                    "channelRootDeleted": bool(delete_result.get("channel_root_deleted")),
                    "keptRuntimeRuns": True,
                },
                "sessions": {
                    "count": int(managed.get("count") or 0),
                    "softDeletedSessionIds": [
                        str((row or {}).get("id") or "")
                        for row in (managed.get("sessions") or [])
                        if bool((row or {}).get("is_deleted"))
                    ],
                },
                "bindings": {
                    "deletedSessionIds": deleted_binding_session_ids,
                    "count": len(deleted_binding_session_ids),
                },
                "rebuildRequired": True,
            },
        )

    def _handle_channel_create_post(self, handler: "BaseHTTPRequestHandler") -> None:
        """Handle POST /api/channels."""
        if not self.ctx.require_token():
            return
        try:
            body = self.ctx.read_body_json(handler, max_bytes=10_000)
        except Exception as e:
            self.ctx.json_response(handler, 400, {"error": f"bad json: {e}"})
            return
        project_id = self.ctx.safe_text(body.get("projectId"), 80).strip()
        channel_name = self.ctx.safe_text(body.get("name"), 200).strip()
        channel_desc = self.ctx.safe_text(body.get("desc"), 500).strip()
        if not project_id or not channel_name:
            self.ctx.json_response(handler, 400, {"error": "missing projectId or name"})
            return
        try:
            result = self.ctx.create_channel(project_id, channel_name, channel_desc, "codex")
            runtime_clear_dashboard_cfg_cache()
        except Exception as e:
            self.ctx.json_response(handler, 500, {"error": str(e)})
            return
        self.ctx.json_response(handler, 200, result)

    def _handle_run_action_post(
        self, handler: "BaseHTTPRequestHandler", parts: list[str]
    ) -> None:
        """Handle POST /api/codex/run/{run_id}/action."""
        if not self.ctx.require_token():
            return
        req_client_ip = str(handler.client_address[0] if handler.client_address else "").strip()
        req_user_agent = str(handler.headers.get("User-Agent") or "").strip()
        req_referer = str(handler.headers.get("Referer") or "").strip()
        req_origin = str(handler.headers.get("Origin") or "").strip()
        request_path = str(handler.path or "").strip()

        def _audit_action(
            *,
            run_id: str,
            action: str,
            requested_action: str,
            http_status: int,
            outcome: str,
            error: str = "",
            meta: Optional[dict[str, Any]] = None,
        ) -> None:
            self.ctx.append_run_action_audit(
                self.ctx.store,
                run_id=run_id,
                action=action,
                requested_action=requested_action,
                http_status=http_status,
                outcome=outcome,
                error=error,
                meta=meta,
                client_ip=req_client_ip,
                user_agent=req_user_agent,
                referer=req_referer,
                origin=req_origin,
                request_path=request_path,
            )

        run_id = str(parts[3] or "").strip()
        try:
            body = self.ctx.read_body_json(handler, max_bytes=40_000)
        except Exception as e:
            _audit_action(
                run_id=run_id,
                action="",
                requested_action="",
                http_status=400,
                outcome="rejected",
                error=f"bad json: {e}",
            )
            self.ctx.json_response(handler, 400, {"error": f"bad json: {e}"})
            return
        code, payload = self.ctx.perform_run_action_response(
            run_id=run_id,
            body=body,
            store=self.ctx.store,
            scheduler=self.ctx.scheduler,
            run_process_registry=self.ctx.run_process_registry,
            audit_action=_audit_action,
            now_iso=self.ctx.now_iso,
            require_scheduler_enabled=lambda: str(os.environ.get("CCB_SCHEDULER") or "").strip() != "0",
            dispatch_terminal_callback_for_run=self.ctx.dispatch_terminal_callback_for_run,
        )
        self.ctx.json_response(handler, code, payload)

    def _handle_conversation_memo_create_post(
        self, handler: "BaseHTTPRequestHandler"
    ) -> None:
        """Handle POST /api/conversation-memos."""
        if not self.ctx.require_token():
            return
        try:
            body = self.ctx.read_body_json(handler, max_bytes=160_000)
        except Exception as e:
            self.ctx.json_response(handler, 400, {"error": f"bad json: {e}"})
            return
        project_id = self.ctx.safe_text(
            body.get("projectId") if "projectId" in body else body.get("project_id"),
            120,
        ).strip()
        session_id = self.ctx.safe_text(
            body.get("sessionId") if "sessionId" in body else body.get("session_id"),
            120,
        ).strip()
        text = body.get("text") if "text" in body else body.get("message")
        attachments = body.get("attachments")
        if not project_id:
            self.ctx.json_response(handler, 400, {"error": "missing projectId"})
            return
        if not session_id or not self.ctx.looks_like_uuid(session_id):
            self.ctx.json_response(handler, 400, {"error": "missing/invalid sessionId"})
            return
        memo_store = self.ctx.conversation_memo_store
        if memo_store is None:
            self.ctx.json_response(handler, 500, {"error": "memo store not available"})
            return
        try:
            item, count = memo_store.create(
                project_id=project_id,
                session_id=session_id,
                text=text,
                attachments=attachments,
            )
        except ValueError:
            self.ctx.json_response(handler, 400, {"error": "empty memo"})
            return
        except Exception as e:
            self.ctx.json_response(handler, 500, {"error": f"save memo failed: {e}"})
            return
        self.ctx.json_response(handler, 200, {"ok": True, "item": item, "count": int(count)})

    def _handle_conversation_memo_delete_post(
        self, handler: "BaseHTTPRequestHandler"
    ) -> None:
        """Handle POST /api/conversation-memos/delete."""
        if not self.ctx.require_token():
            return
        try:
            body = self.ctx.read_body_json(handler, max_bytes=80_000)
        except Exception as e:
            self.ctx.json_response(handler, 400, {"error": f"bad json: {e}"})
            return
        project_id = self.ctx.safe_text(
            body.get("projectId") if "projectId" in body else body.get("project_id"),
            120,
        ).strip()
        session_id = self.ctx.safe_text(
            body.get("sessionId") if "sessionId" in body else body.get("session_id"),
            120,
        ).strip()
        raw_ids = body.get("ids")
        if not isinstance(raw_ids, list):
            single_id = self.ctx.safe_text(body.get("id"), 80).strip()
            raw_ids = [single_id] if single_id else []
        ids = [self.ctx.safe_text(x, 80).strip() for x in raw_ids if self.ctx.safe_text(x, 80).strip()]
        if not project_id:
            self.ctx.json_response(handler, 400, {"error": "missing projectId"})
            return
        if not session_id or not self.ctx.looks_like_uuid(session_id):
            self.ctx.json_response(handler, 400, {"error": "missing/invalid sessionId"})
            return
        memo_store = self.ctx.conversation_memo_store
        if memo_store is None:
            self.ctx.json_response(handler, 500, {"error": "memo store not available"})
            return
        try:
            deleted, count = memo_store.delete(project_id, session_id, ids)
        except Exception as e:
            self.ctx.json_response(handler, 500, {"error": f"delete memo failed: {e}"})
            return
        self.ctx.json_response(handler, 200, {"ok": True, "deleted": int(deleted), "count": int(count)})

    def _handle_conversation_memo_clear_post(
        self, handler: "BaseHTTPRequestHandler"
    ) -> None:
        """Handle POST /api/conversation-memos/clear."""
        if not self.ctx.require_token():
            return
        try:
            body = self.ctx.read_body_json(handler, max_bytes=20_000)
        except Exception as e:
            self.ctx.json_response(handler, 400, {"error": f"bad json: {e}"})
            return
        project_id = self.ctx.safe_text(
            body.get("projectId") if "projectId" in body else body.get("project_id"),
            120,
        ).strip()
        session_id = self.ctx.safe_text(
            body.get("sessionId") if "sessionId" in body else body.get("session_id"),
            120,
        ).strip()
        if not project_id:
            self.ctx.json_response(handler, 400, {"error": "missing projectId"})
            return
        if not session_id or not self.ctx.looks_like_uuid(session_id):
            self.ctx.json_response(handler, 400, {"error": "missing/invalid sessionId"})
            return
        memo_store = self.ctx.conversation_memo_store
        if memo_store is None:
            self.ctx.json_response(handler, 500, {"error": "memo store not available"})
            return
        try:
            cleared = memo_store.clear(project_id, session_id)
        except Exception as e:
            self.ctx.json_response(handler, 500, {"error": f"clear memo failed: {e}"})
            return
        self.ctx.json_response(handler, 200, {"ok": True, "cleared": int(cleared), "count": 0})

    def _handle_channel_sessions_manage_post(
        self, handler: "BaseHTTPRequestHandler"
    ) -> None:
        """Handle POST /api/channel-sessions/manage."""
        if not self.ctx.require_token():
            return
        try:
            body = self.ctx.read_body_json(handler, max_bytes=40_000)
        except Exception as e:
            self.ctx.json_response(handler, 400, {"error": f"bad json: {e}"})
            return
        project_id = self.ctx.safe_text(
            body.get("project_id") if "project_id" in body else body.get("projectId"),
            120,
        ).strip()
        channel_name = self.ctx.safe_text(
            body.get("channel_name") if "channel_name" in body else body.get("channelName"),
            200,
        ).strip()
        primary_session_id = self.ctx.safe_text(
            body.get("primary_session_id") if "primary_session_id" in body else body.get("primarySessionId"),
            120,
        ).strip()
        raw_updates = body.get("updates")
        if not project_id:
            self.ctx.json_response(handler, 400, {"error": "missing project_id"})
            return
        if not channel_name:
            self.ctx.json_response(handler, 400, {"error": "missing channel_name"})
            return
        if raw_updates is not None and not isinstance(raw_updates, list):
            self.ctx.json_response(handler, 400, {"error": "invalid updates"})
            return
        updates: list[dict[str, Any]] = []
        for item in raw_updates or []:
            if not isinstance(item, dict):
                continue
            session_id = self.ctx.safe_text(
                item.get("session_id") if "session_id" in item else item.get("sessionId"),
                120,
            ).strip()
            if not session_id:
                continue
            updates.append(
                {
                    "session_id": session_id,
                    "is_deleted": self.ctx.coerce_bool(
                        item.get("is_deleted") if "is_deleted" in item else item.get("isDeleted"),
                        False,
                    ),
                    "deleted_reason": self.ctx.safe_text(
                        item.get("deleted_reason") if "deleted_reason" in item else item.get("deletedReason"),
                        200,
                    ).strip(),
                }
            )
        self.ctx.json_response(
            handler,
            200,
            runtime_manage_channel_sessions_response(
                session_store=self.ctx.session_store,
                project_id=project_id,
                channel_name=channel_name,
                primary_session_id=primary_session_id,
                updates=updates,
                decorate_sessions_display_fields=self.ctx.decorate_sessions_display_fields,
            ),
        )

    # -----------------------------------------------------------------------
    # PUT request handlers
    # -----------------------------------------------------------------------

    def _handle_session_update_put(
        self, handler: "BaseHTTPRequestHandler", path: str
    ) -> None:
        """Handle PUT /api/sessions/{session_id}."""
        if not self.ctx.require_token():
            return
        session_id = path.split("/")[-1]
        try:
            body = self.ctx.read_body_json(handler, max_bytes=10_000)
        except Exception as e:
            self.ctx.json_response(handler, 400, {"error": f"bad json: {e}"})
            return
        try:
            payload = runtime_update_session_response(
                session_store=self.ctx.session_store,
                session_id=session_id,
                update_fields=runtime_parse_session_update_fields(body),
                body=body,
                store=self.ctx.store,
                environment_name=self.ctx.environment_name,
                worktree_root=self.ctx.worktree_root,
                infer_project_id_for_session=self.ctx.infer_project_id_for_session,
                apply_session_work_context=self.ctx.apply_session_work_context,
                session_context_write_requires_guard=self.ctx.session_context_write_requires_guard,
                stable_write_ack_requested=self.ctx.stable_write_ack_requested,
                coerce_bool=self.ctx.coerce_bool,
                heartbeat_session_payload_for_write=self.ctx.heartbeat_session_payload_for_write,
                build_session_detail_response=self.ctx.build_session_detail_response,
                heartbeat_runtime=self.ctx.heartbeat_runtime,
                apply_effective_primary_flags=self.ctx.apply_effective_primary_flags,
                decorate_session_display_fields=self.ctx.decorate_session_display_fields,
                build_session_detail_payload=self.ctx.build_session_detail_payload,
                build_project_session_runtime_index=self.ctx.build_project_session_runtime_index,
                build_session_runtime_state_for_row=self.ctx.build_session_runtime_state_for_row,
                load_session_heartbeat_config=self.ctx.load_session_heartbeat_config,
                heartbeat_summary_payload=self.ctx.heartbeat_summary_payload,
            )
        except ValueError as e:
            self.ctx.json_response(handler, 400, {"error": str(e)})
            return
        except PermissionError as e:
            self.ctx.json_response(
                handler,
                409,
                {
                    "error": "stable environment write requires confirmation",
                    "error_code": "stable_write_confirmation_required",
                    "environment": str(e) or "stable",
                },
            )
            return
        except LookupError:
            self.ctx.json_response(handler, 404, {"error": "session not found"})
            return
        self.ctx.json_response(handler, 200, payload)

    # -----------------------------------------------------------------------
    # DELETE request handlers
    # -----------------------------------------------------------------------

    def _handle_session_delete(
        self, handler: "BaseHTTPRequestHandler", path: str
    ) -> None:
        """Handle DELETE /api/sessions/{session_id}."""
        if not self.ctx.require_token():
            return
        session_id = path.split("/")[-1]
        try:
            payload = runtime_delete_session_response(
                session_store=self.ctx.session_store,
                session_id=session_id,
                session_binding_store=self.ctx.session_binding_store,
            )
        except LookupError:
            self.ctx.json_response(handler, 404, {"error": "session not found"})
            return
        self.ctx.json_response(handler, 200, payload)


# ---------------------------------------------------------------------------
# Convenience functions for direct dispatch
# ---------------------------------------------------------------------------


def dispatch_head_request(
    handler: "BaseHTTPRequestHandler", context: RouteContext
) -> bool:
    """Dispatch HEAD request using the given context. Returns True if handled."""
    return RouteDispatcher(context).dispatch_head(handler)


def dispatch_get_request(
    handler: "BaseHTTPRequestHandler", context: RouteContext
) -> bool:
    """Dispatch GET request using the given context. Returns True if handled."""
    return RouteDispatcher(context).dispatch_get(handler)


def dispatch_post_request(
    handler: "BaseHTTPRequestHandler", context: RouteContext
) -> bool:
    """Dispatch POST request using the given context. Returns True if handled."""
    return RouteDispatcher(context).dispatch_post(handler)


def dispatch_put_request(
    handler: "BaseHTTPRequestHandler", context: RouteContext
) -> bool:
    """Dispatch PUT request using the given context. Returns True if handled."""
    return RouteDispatcher(context).dispatch_put(handler)


def dispatch_delete_request(
    handler: "BaseHTTPRequestHandler", context: RouteContext
) -> bool:
    """Dispatch DELETE request using the given context. Returns True if handled."""
    return RouteDispatcher(context).dispatch_delete(handler)
