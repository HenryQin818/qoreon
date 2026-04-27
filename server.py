#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Task dashboard local server with CCB (CLI Control Bridge) endpoints.

Serves static files from a given directory (default: <repo>/static_sites)
and exposes a small API surface on the same origin:

- GET  /__health
- POST /api/codex/announce
- GET  /api/codex/runs?limit=&channelId=&projectId=&sessionId=&afterCreatedAt=&beforeCreatedAt=
- GET  /api/codex/run/<id>
- GET  /api/cli/types

All run artifacts are stored under: task-dashboard/.runs/

Supports multiple CLI tools: codex, claude, opencode, gemini, trae.
"""

from __future__ import annotations

import argparse
from collections import deque
from concurrent.futures import ThreadPoolExecutor
import ipaddress
import inspect
import json
import mimetypes
import os
import re
import secrets
import signal
import socket
import subprocess
import sys
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qs, unquote, urlparse

# Import CLI adapters
from task_dashboard.adapters import (
    CLIAdapter,
    get_adapter,
    get_adapter_or_error,
    list_cli_types,
    list_enabled_cli_types,
    CodexAdapter,
)
from task_dashboard.adapters.base import resolve_cli_executable, resolve_cli_executable_details
from task_dashboard.config import (
    load_dashboard_config,
    resolve_dashboard_config_path,
    resolve_dashboard_local_config_path,
)
from task_dashboard.communication_audit import audit_communication_patterns
from task_dashboard.conversation_memo_store import ConversationMemoStore
from task_dashboard.domain import bucket_key_for_status
from task_dashboard.global_resource_graph import build_global_resource_graph
from task_dashboard.local_cli_bins import (
    cli_bin_command_name,
    load_local_cli_bin_overrides,
    save_local_cli_bin_overrides,
)
from task_dashboard.session_health import (
    DEFAULT_SESSION_HEALTH_INTERVAL_MINUTES,
    MAX_SESSION_HEALTH_INTERVAL_MINUTES,
    MIN_SESSION_HEALTH_INTERVAL_MINUTES,
    build_session_health_page,
    load_project_session_health_config,
)
from task_dashboard.runtime.session_context import (
    apply_session_work_context as runtime_apply_session_work_context,
    clear_work_context_cache as runtime_clear_work_context_cache,
    detect_git_branch as runtime_detect_git_branch,
    derive_session_work_context as runtime_derive_session_work_context,
    resolve_run_work_context as runtime_resolve_run_work_context,
    session_context_write_requires_guard as runtime_session_context_write_requires_guard,
    stable_write_ack_requested as runtime_stable_write_ack_requested,
)
from task_dashboard.runtime.execution_runtime import (
    _QUEUED_RECOVERY_LAZY_LAST_TS,
    _QUEUED_RECOVERY_LAZY_LOCK,
    _RESTART_RECOVERY_LAZY_LAST_TS,
    _RESTART_RECOVERY_LAZY_LOCK,
    _build_restart_resume_receipt_summary,
    _build_restart_resume_summary_message,
    _is_restart_recovery_pending_meta,
    _is_stale_queued_pending_meta,
    _maybe_trigger_queued_recovery_lazy,
    _maybe_trigger_restart_recovery_lazy,
    _queued_recovery_lazy_interval_s,
    _restart_recovery_lazy_interval_s,
    _schedule_network_resume_run,
    _schedule_retry_waiting_fallback,
    bootstrap_stale_queued_runs,
    bootstrap_queued_runs,
    bootstrap_restart_interrupted_runs,
    run_cli_exec,
    run_codex_exec,
)
from task_dashboard.runtime.execution_command import (
    prepare_process_spawn as runtime_prepare_process_spawn,
)
from task_dashboard.runtime.execution_profiles import (
    normalize_execution_profile as runtime_normalize_execution_profile,
    resolve_execution_profile_permissions as runtime_resolve_execution_profile_permissions,
)
from task_dashboard.runtime.session_views import (
    apply_session_context_rows as runtime_apply_session_context_rows,
    build_session_detail_payload as runtime_build_session_detail_payload,
)
from task_dashboard.runtime.session_routes import (
    build_channel_sessions_payload as runtime_build_channel_sessions_payload,
    build_session_detail_response as runtime_build_session_detail_response,
    build_sessions_list_payload as runtime_build_sessions_list_payload,
    get_session_detail_response as runtime_get_session_detail_response,
    list_channel_sessions_response as runtime_list_channel_sessions_response,
    list_sessions_response as runtime_list_sessions_response,
    get_session_binding_response as runtime_get_session_binding_response,
    list_session_heartbeat_task_history_route_response as runtime_list_session_heartbeat_task_history_route_response,
    _invalidate_sessions_payload_cache as runtime_invalidate_sessions_payload_cache,
)
from task_dashboard.runtime.run_routes import (
    get_run_detail_response as runtime_get_run_detail_response,
    list_runs_response as runtime_list_runs_response,
    perform_run_action_response as runtime_perform_run_action_response,
)
from task_dashboard.runtime.run_detail_fields import (
    extract_terminal_message_from_file as runtime_extract_terminal_message_from_file,
)
from task_dashboard.sender_contract import normalize_sender_fields

# Import assist-request registry (extracted from server.py)
from task_dashboard.runtime.assist_request_registry import (  # noqa: F401 – re-export
    AssistRequestRuntimeRegistry,
    _assist_request_state_root,
    _assist_request_project_root,
    _assist_request_item_path,
    _assist_request_new_id,
    _assist_request_normalize_status,
    _assist_request_normalize_context_refs,
    _assist_request_normalize_missing_dimensions,
    _assist_request_support_level_from_score,
    _assist_request_threshold_triggered,
    _assist_request_close_message_text,
    _assist_request_message_text,
    # Route handlers
    list_assist_requests_response,
    get_assist_request_response,
    create_assist_request_response,
    auto_trigger_assist_request_response,
    close_assist_request_response,
    reply_assist_request_response,
)

# Import extracted registries and their helpers (re-export for backward compat)
from task_dashboard.runtime.scheduler_helpers import *  # noqa: F401,F403
from task_dashboard.runtime.project_scheduler_registry import *  # noqa: F401,F403
from task_dashboard.runtime.task_push_registry import *  # noqa: F401,F403
from task_dashboard.runtime.task_plan_registry import *  # noqa: F401,F403
from task_dashboard.runtime.heartbeat_registry import *  # noqa: F401,F403
from task_dashboard.runtime.heartbeat_helpers import (  # noqa: F401
    _load_project_heartbeat_config,
    _normalize_heartbeat_task,
    _heartbeat_tasks_for_write,
    _build_heartbeat_patch_with_tasks,
)
from task_dashboard.runtime.heartbeat_routes import (  # noqa: F401
    list_project_heartbeat_tasks_response,
    get_project_heartbeat_task_response,
    list_project_heartbeat_task_history_response,
    list_session_heartbeat_task_history_response,
    create_or_update_project_heartbeat_task_response,
    run_or_delete_session_heartbeat_task_response,
    delete_project_heartbeat_task_response,
    run_project_heartbeat_task_now_response,
)
from task_dashboard.runtime.project_scheduler_routes import (  # noqa: F401
    build_project_contract_update_response,
    get_project_config_response,
    get_project_auto_scheduler_status_response,
    list_project_auto_inspection_tasks_response,
    list_project_inspection_records_response,
    create_or_update_project_auto_inspection_task_response,
    delete_project_auto_inspection_task_response,
    set_project_auto_scheduler_enabled_response,
    update_project_config_response,
)
from task_dashboard.runtime.callback_runtime import *  # noqa: F401,F403
from task_dashboard.runtime.session_health_registry import SessionHealthRuntimeRegistry
from task_dashboard.runtime.share_space import (
    LEGACY_PROJECT_CHAT_PAGE_PATH as RUNTIME_LEGACY_PROJECT_CHAT_PAGE_PATH,
    LEGACY_SHARE_SPACE_PAGE_PATH as RUNTIME_LEGACY_SHARE_SPACE_PAGE_PATH,
    SHARE_MODE_PAGE_PATH as RUNTIME_SHARE_MODE_PAGE_PATH,
)

# Import route dispatcher (extracted from server.py)
from task_dashboard.routes import (
    RouteDispatcher,
    RouteContext,
    dispatch_get_request,
    dispatch_post_request,
    dispatch_put_request,
    dispatch_delete_request,
    dispatch_head_request,
)

# Import common helpers (extracted from server.py)
from task_dashboard.helpers import (
    safe_text as _safe_text,
    now_iso as _now_iso,
    channel_id as _channel_id,
    tail_text as _tail_text,
    tail_str as _tail_str,
    extract_last_json_object_text as _extract_last_json_object_text,
    read_json_file_safe as _read_json_file_safe,
    parse_iso_ts as _parse_iso_ts,
    iso_after_s as _iso_after_s,
    looks_like_uuid as _looks_like_uuid,
    atomic_write_text as _atomic_write_text,
    read_json_file as _read_json_file,
    write_json_file as _write_json_file,
    coerce_bool as _coerce_bool,
    coerce_int as _coerce_int,
    parse_rfc3339_ts as _parse_rfc3339_ts,
    _repo_root,
    _find_project_cfg,
)

# Import session store
from task_dashboard.session_store import SessionStore
from task_dashboard.session_store_sync import sync_project_session_store

_DASHBOARD_CFG_CACHE_LOCK = threading.Lock()
_DASHBOARD_CFG_CACHE: dict[str, Any] = {
    "cfg": {},
    "signature": (),
    "with_local": False,
    "checked_at_mono": 0.0,
}
_PROJECT_TASK_ITEMS_CACHE_LOCK = threading.Lock()
_PROJECT_TASK_ITEMS_CACHE: dict[str, dict[str, Any]] = {}
_AUTO_INSPECTION_PREVIEW_CACHE_LOCK = threading.Lock()
_AUTO_INSPECTION_PREVIEW_CACHE: dict[str, dict[str, Any]] = {}
_SESSION_RUNTIME_INDEX_CACHE_LOCK = threading.Lock()
_SESSION_RUNTIME_INDEX_CACHE: dict[str, dict[str, Any]] = {}
_SESSION_RUNTIME_INDEX_INFLIGHT: dict[str, dict[str, Any]] = {}
_SESSION_RUNTIME_INDEX_INVALIDATED_AT: dict[str, float] = {}
_SESSION_EXTERNAL_BUSY_CACHE_LOCK = threading.Lock()
_SESSION_EXTERNAL_BUSY_CACHE: dict[str, dict[str, Any]] = {}
_SESSION_ARCHIVE_SESSION_SUMMARY_CACHE: dict[str, dict[str, Any]] = {}
_SESSION_ARCHIVE_SESSION_SUMMARY_CACHE_LOCK = threading.Lock()
_COMMUNICATION_AUDIT_CACHE_LOCK = threading.Lock()
_COMMUNICATION_AUDIT_CACHE: dict[str, dict[str, Any]] = {}
_SERVER_HOLDER: dict[str, Any] = {"server": None}


def _json_response(
    handler: BaseHTTPRequestHandler,
    code: int,
    payload: dict[str, Any],
    *,
    send_body: bool = True,
) -> None:
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(raw)))
    handler.end_headers()
    if send_body:
        handler.wfile.write(raw)


def _read_body_json(handler: BaseHTTPRequestHandler, max_bytes: int = 256_000) -> dict[str, Any]:
    n = int(handler.headers.get("Content-Length") or "0")
    if n <= 0:
        return {}
    if n > max_bytes:
        raise ValueError("body too large")
    raw = handler.rfile.read(n)
    return json.loads(raw.decode("utf-8"))


def _upload_max_bytes() -> int:
    raw_bytes = str(os.environ.get("CCB_UPLOAD_MAX_BYTES") or "").strip()
    if raw_bytes:
        try:
            n = int(raw_bytes)
            return max(1 * 1024, min(n, 200 * 1024 * 1024))
        except Exception:
            pass
    raw_mb = str(os.environ.get("CCB_UPLOAD_MAX_MB") or "").strip()
    if raw_mb:
        try:
            n_mb = float(raw_mb)
            n = int(n_mb * 1024 * 1024)
            return max(1 * 1024, min(n, 200 * 1024 * 1024))
        except Exception:
            pass
    return 20 * 1024 * 1024


def _communication_audit_cache_ttl_s() -> float:
    raw = str(os.environ.get("CCB_COMMUNICATION_AUDIT_CACHE_TTL_S") or "").strip()
    try:
        value = float(raw) if raw else 20.0
    except Exception:
        value = 20.0
    return max(5.0, min(value, 300.0))


def _communication_audit_scope_catalog(server: Any) -> dict[str, dict[str, Any]]:
    runs_dir = Path(getattr(server, "runs_dir", "") or "")
    worktree_root = Path(getattr(server, "worktree_root", _repo_root()) or _repo_root())
    hot_dir = runs_dir / "hot"
    if not hot_dir.exists():
        hot_dir = runs_dir
    repo_flat_dir = worktree_root / ".runs"
    return {
        "hot": {
            "label": "当前协作面",
            "description": "默认只读分析当前运行热区，读取成本最低。",
            "runs_dirs": [hot_dir],
        },
        "repo_flat": {
            "label": "仓库根样本",
            "description": "对照仓库根 .runs 样本，观察历史习惯与当前差异。",
            "runs_dirs": [repo_flat_dir],
        },
        "runtime_all": {
            "label": "运行态全量",
            "description": "深扫当前运行根全部 run，开销最高，仅按需使用。",
            "runs_dirs": [runs_dir],
        },
    }


def _parse_communication_audit_scopes(raw: Any, *, allowed: set[str]) -> list[str]:
    txt = str(raw or "").strip().lower()
    if not txt:
        return ["hot", "repo_flat"]
    out: list[str] = []
    seen: set[str] = set()
    for item in txt.split(","):
        scope = str(item or "").strip().lower()
        if not scope or scope not in allowed or scope in seen:
            continue
        seen.add(scope)
        out.append(scope)
    return out or ["hot", "repo_flat"]


def _get_communication_audit_summary(
    *,
    scope: str,
    label: str,
    description: str,
    runs_dirs: list[Path],
    response_window_hours: float,
    top_limit: int,
    include_hidden: bool,
) -> dict[str, Any]:
    dirs_norm = [str(Path(p).expanduser().resolve()) for p in runs_dirs if str(p or "").strip()]
    cache_key = json.dumps(
        {
            "scope": scope,
            "dirs": dirs_norm,
            "response_window_hours": round(float(response_window_hours or 0.0), 3),
            "top_limit": int(top_limit or 0),
            "include_hidden": bool(include_hidden),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    now_mono = time.monotonic()
    ttl_s = _communication_audit_cache_ttl_s()
    with _COMMUNICATION_AUDIT_CACHE_LOCK:
        cached = _COMMUNICATION_AUDIT_CACHE.get(cache_key)
        if cached and (now_mono - float(cached.get("cached_at_mono") or 0.0)) <= ttl_s:
            return dict(cached.get("payload") or {})

    summary = audit_communication_patterns(
        runs_dirs=[Path(x) for x in dirs_norm],
        response_window_hours=float(response_window_hours or 0.0),
        top_limit=max(1, int(top_limit or 1)),
        include_hidden=bool(include_hidden),
    )
    payload = {
        "scope": scope,
        "label": label,
        "description": description,
        "summary": summary,
    }
    with _COMMUNICATION_AUDIT_CACHE_LOCK:
        _COMMUNICATION_AUDIT_CACHE[cache_key] = {
            "cached_at_mono": now_mono,
            "payload": payload,
        }
    return payload


def _sanitize_upload_filename(filename: str) -> str:
    raw = str(filename or "").replace("\x00", "").strip()
    base = Path(raw).name.strip()
    safe = re.sub(r"[^0-9A-Za-z._-]+", "_", base)
    safe = re.sub(r"_+", "_", safe).strip("._")
    if not safe:
        safe = "file"
    if len(safe) > 120:
        ext = Path(safe).suffix[:16]
        stem_limit = max(1, 120 - len(ext))
        stem = Path(safe).stem[:stem_limit]
        safe = f"{stem}{ext}"
    return safe


def _build_session_health_payload(
    *,
    project_id: str,
    session_store: Any,
    store: Any,
    environment_name: str,
    worktree_root: Any,
    heartbeat_runtime: Any,
    load_session_heartbeat_config: Callable[[dict[str, Any]], dict[str, Any]],
    heartbeat_summary_payload: Callable[[Any], Any],
) -> dict[str, Any]:
    sessions_payload = runtime_build_sessions_list_payload(
        session_store=session_store,
        store=store,
        project_id=project_id,
        environment_name=environment_name,
        worktree_root=worktree_root,
        apply_effective_primary_flags=_apply_effective_primary_flags,
        decorate_sessions_display_fields=_decorate_sessions_display_fields,
        apply_session_context_rows=runtime_apply_session_context_rows,
        apply_session_work_context=_apply_session_work_context,
        attach_runtime_state_to_sessions=_attach_runtime_state_to_sessions,
        heartbeat_runtime=heartbeat_runtime,
        load_session_heartbeat_config=load_session_heartbeat_config,
        heartbeat_summary_payload=heartbeat_summary_payload,
    )
    project_cfg = _find_project_cfg(project_id) or {}
    session_health_cfg = load_project_session_health_config(project_id)
    session_rows = []
    for row in sessions_payload.get("sessions") or []:
        if not isinstance(row, dict):
            continue
        session_rows.append(
            {
                "session_id": str(row.get("id") or row.get("session_id") or "").strip(),
                "name": str(row.get("channel_name") or "").strip(),
                "alias": str(row.get("alias") or "").strip(),
                "display_name": str(row.get("display_name") or row.get("displayName") or "").strip(),
                "display_name_source": str(
                    row.get("display_name_source") or row.get("displayNameSource") or ""
                ).strip(),
                "codex_title": str(row.get("codex_title") or row.get("codexTitle") or "").strip(),
                "cli_type": str(row.get("cli_type") or "codex").strip() or "codex",
                "model": str(row.get("model") or "").strip(),
                "reasoning_effort": str(row.get("reasoning_effort") or "").strip(),
                "source": str(row.get("source") or "").strip(),
                "environment": str(row.get("environment") or "").strip(),
                "branch": str(row.get("branch") or "").strip(),
                "worktree_root": str(row.get("worktree_root") or "").strip(),
                "workdir": str(row.get("workdir") or "").strip(),
                "project_execution_context": dict(row.get("project_execution_context") or {})
                if isinstance(row.get("project_execution_context"), dict)
                else {},
                "is_primary": bool(row.get("is_primary")),
                "session_role": str(row.get("session_role") or "").strip(),
                "status": str(row.get("status") or "").strip(),
                "is_deleted": bool(row.get("is_deleted")),
                "created_at": str(row.get("created_at") or "").strip(),
                "last_used_at": str(row.get("last_used_at") or "").strip(),
            }
        )
    return build_session_health_page(
        [
            {
                "id": project_id,
                "name": str(project_cfg.get("name") or project_id).strip() or project_id,
                "all_sessions": session_rows,
                "session_health_config": session_health_cfg,
            }
        ],
        generated_at=_now_iso(),
        task_page_link="project-task-dashboard.html",
        overview_page_link="project-overview-dashboard.html",
        communication_page_link="project-communication-audit.html",
        agent_curtain_page_link="project-agent-curtain.html",
        session_health_page_link="project-session-health-dashboard.html",
        agent_directory_page_link="project-agent-directory.html",
    )


def _normalize_session_health_interval_minutes(value: Any) -> int:
    try:
        interval = int(value)
    except Exception:
        interval = int(DEFAULT_SESSION_HEALTH_INTERVAL_MINUTES)
    interval = max(MIN_SESSION_HEALTH_INTERVAL_MINUTES, interval)
    interval = min(MAX_SESSION_HEALTH_INTERVAL_MINUTES, interval)
    return interval


def _session_health_runtime_status(httpd: Any, project_id: str) -> dict[str, Any]:
    runtime = getattr(httpd, "session_health_runtime", None)
    if runtime is None:
        return {}
    try:
        payload = runtime.get_payload(project_id, refresh=False)
    except Exception:
        return {}
    return dict(payload.get("session_health") or {})


def _update_project_session_health_config(project_id: str, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    pid = _safe_text(project_id, 120).strip()
    if not pid:
        return 400, {"error": "missing project_id"}
    if not _find_project_cfg(pid):
        return 404, {"error": "project not found"}
    payload = body if isinstance(body, dict) else {}
    enabled_value = None
    if "enabled" in payload:
        enabled_value = _coerce_bool(payload.get("enabled"), True)
    elif "auto_enabled" in payload:
        enabled_value = _coerce_bool(payload.get("auto_enabled"), True)
    interval_value = None
    if "interval_minutes" in payload:
        interval_value = _normalize_session_health_interval_minutes(payload.get("interval_minutes"))
    elif "auto_interval_minutes" in payload:
        interval_value = _normalize_session_health_interval_minutes(payload.get("auto_interval_minutes"))
    if enabled_value is None and interval_value is None:
        return 400, {"error": "missing enabled or interval_minutes"}
    patch: dict[str, Any] = {}
    if enabled_value is not None:
        patch["enabled"] = bool(enabled_value)
    if interval_value is not None:
        patch["interval_minutes"] = int(interval_value)
    try:
        config_path = _set_project_scheduler_contract_in_config(
            pid,
            session_health_patch=patch,
        )
    except Exception as exc:
        return 400, {"error": str(exc)}
    _clear_dashboard_cfg_cache()
    runtime = getattr(_SERVER_HOLDER.get("server"), "session_health_runtime", None)
    if runtime is not None:
        try:
            runtime.update_project_config(
                pid,
                enabled=patch.get("enabled") if "enabled" in patch else None,
                interval_minutes=patch.get("interval_minutes") if "interval_minutes" in patch else None,
            )
        except Exception:
            pass
    session_health = load_project_session_health_config(pid)
    server_obj = _SERVER_HOLDER.get("server")
    runtime_status = _session_health_runtime_status(server_obj, pid) if server_obj is not None else {}
    return 200, {
        "ok": True,
        "project_id": pid,
        "config_path": str(config_path),
        "session_health": {
            **session_health,
            **runtime_status,
        },
    }


def _parse_multipart_single_file(body: bytes, boundary: str) -> tuple[str, bytes, str]:
    bnd = str(boundary or "").strip()
    if not bnd:
        raise ValueError("missing boundary")
    delimiter = b"--" + bnd.encode("utf-8", errors="ignore")
    parts = body.split(delimiter)
    for raw_part in parts:
        part = raw_part.strip(b"\r\n")
        if not part or part == b"--":
            continue
        if part.endswith(b"--"):
            part = part[:-2].rstrip(b"\r\n")
        header_end = part.find(b"\r\n\r\n")
        if header_end <= 0:
            continue
        header_txt = part[:header_end].decode("utf-8", errors="replace")
        data = part[header_end + 4 :]
        if data.endswith(b"\r\n"):
            data = data[:-2]

        headers: dict[str, str] = {}
        for line in header_txt.split("\r\n"):
            if ":" not in line:
                continue
            k, v = line.split(":", 1)
            headers[k.strip().lower()] = v.strip()
        disp = str(headers.get("content-disposition") or "")
        if "form-data" not in disp.lower():
            continue

        filename = ""
        fn_star = re.search(r"filename\*=([^;]+)", disp, flags=re.IGNORECASE)
        if fn_star:
            val = fn_star.group(1).strip().strip('"')
            if "''" in val:
                _, enc = val.split("''", 1)
                filename = unquote(enc)
            else:
                filename = val
        if not filename:
            fn_plain = re.search(r'filename="([^"]*)"', disp, flags=re.IGNORECASE)
            if fn_plain:
                filename = fn_plain.group(1)
        filename = str(filename or "").strip()
        if not filename:
            continue

        mime = str(headers.get("content-type") or "application/octet-stream").strip()
        return filename, data, mime
    raise ValueError("no file provided")


def _extract_sender_fields(payload: dict[str, Any]) -> dict[str, str]:
    """Normalize and sanitize sender fields from request payload."""
    normalized = normalize_sender_fields(payload)
    sender_type = _safe_text(normalized.get("sender_type"), 20).strip().lower() or "legacy"
    sender_id = _safe_text(normalized.get("sender_id"), 120).strip()
    sender_name = _safe_text(normalized.get("sender_name"), 200).strip()
    return {
        "sender_type": sender_type,
        "sender_id": sender_id,
        "sender_name": sender_name,
    }


def _run_process_alive(run_id: str, cli_type: str = "codex") -> bool:
    rid = str(run_id or "").strip()
    if not rid:
        return False

    # Get adapter for the CLI type to find process signature
    adapter_cls = get_adapter(cli_type) or CodexAdapter
    process_sig = adapter_cls.get_process_signature(rid)

    rows = _scan_process_table_rows()
    cli_t = str(cli_type or "codex").strip().lower() or "codex"
    for _, cmd in rows:
        cmd_txt = str(cmd or "")
        if process_sig and process_sig not in cmd_txt:
            continue
        if _run_busy_cmd_matches(cmd_txt, rid, cli_t):
            return True
        if _run_busy_cmd_fallback_matches(cmd_txt, rid, cli_t):
            return True
        if cli_t not in {"codex", "trae"} and rid in cmd_txt:
            return True
    return False


def _session_process_busy(session_id: str, cli_type: str = "codex") -> bool:
    """Best-effort detect whether a session is currently occupied by an external CLI process."""
    sid = str(session_id or "").strip()
    if not sid:
        return False
    rows = _scan_session_busy_rows(sid, cli_type=cli_type)
    return bool(rows)


def _interrupt_run_process_by_scan(run_id: str, cli_type: str = "codex") -> bool:
    """Best-effort interrupt for untracked run processes by scanning system process table."""
    rid = str(run_id or "").strip()
    if not rid:
        return False
    adapter_cls = get_adapter(cli_type) or CodexAdapter
    process_sig = adapter_cls.get_process_signature(rid)
    rows = _scan_process_rows(rid, process_sig)
    pids = [pid for pid, _ in rows]
    if not pids:
        return False
    signaled = False
    alive: list[int] = []
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
            signaled = True
            alive.append(pid)
        except Exception:
            continue
    if not signaled:
        return False
    time.sleep(0.25)
    for pid in alive:
        try:
            os.kill(pid, 0)
        except Exception:
            continue
        try:
            os.kill(pid, signal.SIGKILL)
        except Exception:
            continue
    return True


def _scan_process_table_rows() -> list[tuple[int, str]]:
    """Return full process table rows as (pid, command), excluding current process."""
    try:
        env = dict(os.environ)
        env["LC_ALL"] = "C"
        # Use `-ww` to avoid truncating long CLI resume commands; otherwise
        # terminal-bound orphan rows may lose their `-o <run>.last.txt` segment
        # and get misclassified as real external busy processes.
        proc = subprocess.run(
            ["ps", "-axww", "-o", "pid=,command="],
            capture_output=True,
            text=True,
            timeout=2.0,
            env=env,
        )
    except Exception:
        return []
    if proc.returncode != 0:
        return []
    out: list[tuple[int, str]] = []
    self_pid = int(os.getpid() or 0)
    for line in (proc.stdout or "").splitlines():
        raw = str(line or "").strip()
        if not raw:
            continue
        parts = raw.split(None, 1)
        if len(parts) < 2:
            continue
        try:
            pid = int(parts[0])
        except Exception:
            continue
        cmd = str(parts[1] or "").strip()
        if not cmd:
            continue
        if pid <= 0 or pid == self_pid:
            continue
        out.append((pid, cmd))
    return out


def _scan_process_rows(token: str, signature: str = "", rows: Optional[list[tuple[int, str]]] = None) -> list[tuple[int, str]]:
    """Return process rows whose command contains token (and optional signature)."""
    needle = str(token or "").strip()
    sig = str(signature or "").strip()
    if not needle:
        return []
    all_rows = rows if isinstance(rows, list) else _scan_process_table_rows()
    out: list[tuple[int, str]] = []
    for pid, cmd in all_rows:
        if needle not in cmd:
            continue
        if sig and sig not in cmd:
            continue
        out.append((int(pid), str(cmd)))
    return out


def _run_busy_cmd_matches(cmd: str, run_id: str, cli_type: str) -> bool:
    """Match run id only when it appears in the CLI's run-artifact argument slot."""
    text = str(cmd or "").replace("\\012", " ")
    rid = str(run_id or "").strip()
    if not rid:
        return False
    escaped_rid = re.escape(rid)
    cli_t = str(cli_type or "codex").strip().lower()
    patterns: list[str] = []
    if cli_t == "codex":
        patterns = [rf"(?:^|\s)-o\s+[^\s\"']*{escaped_rid}\.last\.txt(?:\s|$)"]
    elif cli_t == "trae":
        patterns = [rf"(?:^|\s)--trajectory-file\s+[^\s\"']*{escaped_rid}\.last\.txt(?:\s|$)"]
    if not patterns:
        return False
    return any(re.search(p, text) is not None for p in patterns)


def _run_busy_cmd_fallback_matches(cmd: str, run_id: str, cli_type: str) -> bool:
    """Fallback match for active run process rows whose output-path arg is quoted or oddly escaped."""
    text = str(cmd or "").replace("\\012", " ")
    rid = str(run_id or "").strip()
    if not rid:
        return False
    cli_t = str(cli_type or "codex").strip().lower()
    if cli_t == "codex":
        return (re.search(r"(?:^|\s)-o(?:\s|=)", text) is not None) and (f"{rid}.last.txt" in text)
    if cli_t == "trae":
        return (re.search(r"(?:^|\s)--trajectory-file(?:\s|=)", text) is not None) and (f"{rid}.last.txt" in text)
    return False


_RUN_OUTPUT_FILE_TOKEN_RE = re.compile(r"([A-Za-z0-9][A-Za-z0-9._-]{5,120})\.last\.txt")


def _extract_run_id_from_busy_cmd(cmd: str, cli_type: str) -> str:
    """Best-effort extract run id from a CLI process row bound to a run output file."""
    text = str(cmd or "").replace("\\012", " ")
    cli_t = str(cli_type or "codex").strip().lower()
    if cli_t == "codex":
        if re.search(r"(?:^|\s)-o(?:\s|=)", text) is None:
            return ""
    elif cli_t == "trae":
        if re.search(r"(?:^|\s)--trajectory-file(?:\s|=)", text) is None:
            return ""
    else:
        return ""
    matches = list(_RUN_OUTPUT_FILE_TOKEN_RE.finditer(text))
    if not matches:
        return ""
    return str(matches[-1].group(1) or "").strip()


def _terminal_run_bound_session_process(
    store: Any,
    session_id: str,
    cmd: str,
    *,
    cli_type: str = "codex",
) -> bool:
    """Return True when a matched session process is bound to a run already in terminal state."""
    if store is None or not hasattr(store, "load_meta"):
        return False
    sid = str(session_id or "").strip()
    if not sid:
        return False
    run_id = _extract_run_id_from_busy_cmd(cmd, cli_type=cli_type)
    if not run_id:
        return False
    try:
        meta = store.load_meta(run_id)
    except Exception:
        meta = None
    if not isinstance(meta, dict):
        return False
    if str(meta.get("sessionId") or "").strip() != sid:
        return False
    return str(meta.get("status") or "").strip().lower() in {"done", "error"}


def _session_busy_cmd_matches(cmd: str, session_id: str, cli_type: str) -> bool:
    """Match session id only when it appears in the real CLI session argument slot."""
    text = str(cmd or "").replace("\\012", " ")
    sid = str(session_id or "").strip()
    if not sid:
        return False
    escaped_sid = re.escape(sid)
    cli_t = str(cli_type or "codex").strip().lower()
    patterns: list[str]
    if cli_t == "codex":
        patterns = [rf"(?:^|\s)resume\s+{escaped_sid}(?:\s|$)"]
    elif cli_t in {"claude", "gemini"}:
        patterns = [rf"(?:^|\s)--resume\s+{escaped_sid}(?:\s|$)"]
    elif cli_t == "opencode":
        patterns = [rf"(?:^|\s)--session\s+{escaped_sid}(?:\s|$)"]
    elif cli_t == "trae":
        # Trae adapter V1 does not pass external session-id in process args.
        return False
    else:
        patterns = [rf"(?:^|\s){escaped_sid}(?:\s|$)"]
    return any(re.search(p, text) is not None for p in patterns)


def _scan_session_busy_rows(
    session_id: str,
    cli_type: str = "codex",
    rows: Optional[list[tuple[int, str]]] = None,
) -> list[tuple[int, str]]:
    sid = str(session_id or "").strip()
    if not sid:
        return []
    cli_t = str(cli_type or "codex").strip() or "codex"
    adapter_cls = get_adapter(cli_t) or CodexAdapter
    sig = str(adapter_cls.get_process_signature(sid) or "").strip()
    all_rows = rows if isinstance(rows, list) else _scan_process_table_rows()
    out: list[tuple[int, str]] = []
    for pid, cmd in all_rows:
        cmd_txt = str(cmd or "")
        if sig and sig not in cmd_txt:
            continue
        if not _session_busy_cmd_matches(cmd_txt, sid, cli_t):
            continue
        out.append((int(pid), cmd_txt))
    return out


def _scan_session_busy_rows_effective(
    store: Any,
    session_id: str,
    cli_type: str = "codex",
    rows: Optional[list[tuple[int, str]]] = None,
) -> list[tuple[int, str]]:
    """Filter matched session processes, ignoring rows bound to terminal runs."""
    sid = str(session_id or "").strip()
    cli_t = str(cli_type or "codex").strip() or "codex"
    matched = _scan_session_busy_rows(sid, cli_type=cli_t, rows=rows)
    if not matched or store is None or not hasattr(store, "load_meta"):
        return matched
    out: list[tuple[int, str]] = []
    for pid, cmd in matched:
        if _terminal_run_bound_session_process(store, sid, cmd, cli_type=cli_t):
            continue
        out.append((int(pid), str(cmd)))
    return out


def _session_process_busy_effective(
    store: Any,
    session_id: str,
    cli_type: str = "codex",
    rows: Optional[list[tuple[int, str]]] = None,
) -> bool:
    return bool(_scan_session_busy_rows_effective(store, session_id, cli_type=cli_type, rows=rows))


def _fallback_log_from_meta(meta: dict[str, Any]) -> str:
    err = str(meta.get("error") or "").strip()
    if not err:
        return ""
    parts = [
        "[system] no captured process log for this run",
        f"[system] status={meta.get('status')}",
        f"[system] error={err}",
        f"[system] started_at={meta.get('startedAt')}",
        f"[system] finished_at={meta.get('finishedAt')}",
    ]
    return "\n".join(parts)


def _resolve_runs_static_target(runs_root: Path, request_path: str) -> Optional[Path]:
    """Resolve '/.runs/*' request path to a safe file path under runs_root."""
    if not str(request_path or "").startswith("/.runs/"):
        return None
    rel_raw = str(request_path or "")[len("/.runs/") :]
    rel = unquote(rel_raw).lstrip("/")
    if not rel:
        return None
    target = (runs_root / rel).resolve()
    try:
        target.relative_to(runs_root.resolve())
    except ValueError:
        return None
    return target


def _is_runs_attachment_request(request_path: str) -> bool:
    p = str(request_path or "")
    return p.startswith("/.runs/") and ("/attachments/" in p)


def _normalize_client_host(host: Any) -> str:
    raw = str(host or "").strip()
    if raw.startswith("[") and raw.endswith("]"):
        raw = raw[1:-1]
    if "%" in raw:
        raw = raw.split("%", 1)[0]
    if raw.lower().startswith("::ffff:"):
        raw = raw.split(":", 3)[-1]
    return raw


_LOCAL_CLIENT_ADDRESSES_CACHE_LOCK = threading.Lock()
_LOCAL_CLIENT_ADDRESSES_CACHE: dict[str, Any] = {
    "checked_at": 0.0,
    "addresses": {"127.0.0.1", "::1", "localhost"},
}


def _is_loopback_client_address(client_address: Any) -> bool:
    host = ""
    if isinstance(client_address, (tuple, list)) and client_address:
        host = _normalize_client_host(client_address[0])
    else:
        host = _normalize_client_host(client_address)
    if not host:
        return False
    if host == "localhost":
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        ip = mapped
    return bool(ip.is_loopback)


def _local_client_address_candidates() -> set[str]:
    candidates = {"localhost", "127.0.0.1", "::1"}
    for raw in {socket.gethostname(), socket.getfqdn()}:
        host = _normalize_client_host(raw)
        if host:
            candidates.add(host)
    for host in tuple(candidates):
        try:
            infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
        except Exception:
            continue
        for info in infos:
            sockaddr = info[4] if len(info) > 4 else ()
            if not sockaddr:
                continue
            resolved = _normalize_client_host(sockaddr[0])
            if resolved:
                candidates.add(resolved)
    for dest in (("8.8.8.8", 80), ("1.1.1.1", 80), ("192.168.0.1", 80)):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                sock.connect(dest)
                resolved = _normalize_client_host(sock.getsockname()[0])
            finally:
                sock.close()
        except Exception:
            continue
        if resolved:
            candidates.add(resolved)
    normalized: set[str] = set()
    for raw in candidates:
        host = _normalize_client_host(raw)
        if not host:
            continue
        normalized.add(host)
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            continue
        mapped = getattr(ip, "ipv4_mapped", None)
        if mapped is not None:
            ip = mapped
        normalized.add(str(ip))
    return normalized


def _local_client_addresses(refresh: bool = False) -> set[str]:
    ttl_s = 15.0
    now_mono = time.monotonic()
    with _LOCAL_CLIENT_ADDRESSES_CACHE_LOCK:
        checked_at = float(_LOCAL_CLIENT_ADDRESSES_CACHE.get("checked_at") or 0.0)
        cached = set(_LOCAL_CLIENT_ADDRESSES_CACHE.get("addresses") or set())
        if cached and not refresh and (now_mono - checked_at) < ttl_s:
            return cached
    resolved = _local_client_address_candidates()
    with _LOCAL_CLIENT_ADDRESSES_CACHE_LOCK:
        _LOCAL_CLIENT_ADDRESSES_CACHE["checked_at"] = now_mono
        _LOCAL_CLIENT_ADDRESSES_CACHE["addresses"] = set(resolved)
    return set(resolved)


def _is_local_client_address(client_address: Any, local_addresses: Optional[set[str]] = None) -> bool:
    host = ""
    if isinstance(client_address, (tuple, list)) and client_address:
        host = _normalize_client_host(client_address[0])
    else:
        host = _normalize_client_host(client_address)
    if not host:
        return False
    if _is_loopback_client_address(host):
        return True
    normalized = local_addresses if local_addresses is not None else _local_client_addresses()
    if host in normalized:
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        ip = mapped
    return str(ip) in normalized


def _is_remote_share_only_allowed_request(method: str, request_path: str) -> bool:
    path = urlparse(str(request_path or "")).path
    method_upper = str(method or "").upper()
    parts = [seg for seg in path.split("/") if seg]

    if method_upper in {"GET", "HEAD"} and path in {
        RUNTIME_SHARE_MODE_PAGE_PATH,
        RUNTIME_LEGACY_PROJECT_CHAT_PAGE_PATH,
        RUNTIME_LEGACY_SHARE_SPACE_PAGE_PATH,
    }:
        return True

    if method_upper in {"GET", "HEAD"} and _is_runs_attachment_request(path):
        return True

    if len(parts) == 4 and parts[:2] == ["api", "share-spaces"] and parts[3] == "bootstrap":
        return method_upper in {"GET", "HEAD"}

    if len(parts) == 5 and parts[:2] == ["api", "share-spaces"] and parts[3] == "sessions":
        return method_upper in {"GET", "HEAD"}

    if len(parts) == 4 and parts[:2] == ["api", "share-spaces"] and parts[3] == "announce":
        return method_upper == "POST"

    return False


def _is_remote_share_only_request_blocked(
    client_address: Any,
    method: str,
    request_path: str,
    *,
    local_addresses: Optional[set[str]] = None,
) -> bool:
    if _is_local_client_address(client_address, local_addresses=local_addresses):
        return False
    return not _is_remote_share_only_allowed_request(method, request_path)


def _format_origin_host(host: str) -> str:
    normalized = _normalize_client_host(host)
    if not normalized:
        return ""
    if ":" in normalized and not normalized.startswith("["):
        return f"[{normalized}]"
    return normalized


def _preferred_local_server_host(bind_host: str, *, refresh: bool = False) -> str:
    host = _normalize_client_host(bind_host)
    if host and host not in {"0.0.0.0", "::", "[::]"}:
        return _format_origin_host(host)

    for dest in (("8.8.8.8", 80), ("1.1.1.1", 80), ("192.168.0.1", 80)):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                sock.connect(dest)
                resolved = _normalize_client_host(sock.getsockname()[0])
            finally:
                sock.close()
        except Exception:
            continue
        if resolved and not _is_loopback_client_address(resolved):
            return _format_origin_host(resolved)

    local_addresses = _local_client_addresses(refresh=refresh)
    ipv4_candidates: list[str] = []
    ipv6_candidates: list[str] = []
    for candidate in sorted(local_addresses):
        host = _normalize_client_host(candidate)
        if not host or host == "localhost" or _is_loopback_client_address(host):
            continue
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            continue
        mapped = getattr(ip, "ipv4_mapped", None)
        if mapped is not None:
            ip = mapped
        if ip.is_link_local:
            continue
        if ip.version == 4:
            ipv4_candidates.append(str(ip))
        else:
            ipv6_candidates.append(str(ip))
    if ipv4_candidates:
        return _format_origin_host(ipv4_candidates[0])
    if ipv6_candidates:
        return _format_origin_host(ipv6_candidates[0])
    return "127.0.0.1"


def _should_refresh_local_public_origin(host: str) -> bool:
    normalized = _normalize_client_host(host)
    if not normalized:
        return False
    if normalized == "localhost" or _is_loopback_client_address(normalized):
        return False
    try:
        ip = ipaddress.ip_address(normalized)
    except ValueError:
        return False
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        ip = mapped
    return bool(ip.is_private or ip.is_link_local)


def _build_local_server_origin(bind_host: str, port: int) -> str:
    resolved_port = int(port or 0)
    if resolved_port <= 0:
        return ""
    return f"http://127.0.0.1:{resolved_port}"


def _build_public_server_origin(bind_host: str, port: int) -> str:
    public_origin = str(os.environ.get("TASK_DASHBOARD_PUBLIC_ORIGIN") or "").strip().rstrip("/")
    if public_origin:
        if not re.match(r"^https?://", public_origin, re.I):
            public_origin = "http://" + public_origin.lstrip("/")
        parsed = urlparse(public_origin)
        configured_host = _normalize_client_host(parsed.hostname or "")
        if configured_host and _should_refresh_local_public_origin(configured_host):
            local_addresses = _local_client_addresses(refresh=True)
            if configured_host not in local_addresses:
                current_host = _preferred_local_server_host(bind_host, refresh=False)
                current_port = int(parsed.port or port or 0)
                if current_host:
                    if current_port > 0:
                        return f"{parsed.scheme or 'http'}://{current_host}:{current_port}"
                    return f"{parsed.scheme or 'http'}://{current_host}"
        return public_origin
    host = str(bind_host or "").strip()
    if not host or host in {"0.0.0.0", "::", "[::]"}:
        host = _preferred_local_server_host(host, refresh=True)
    elif host == "::1":
            host = "[::1]"
    else:
        host = _format_origin_host(host)
    return f"http://{host}:{int(port or 0)}" if int(port or 0) > 0 else ""


def _resolve_attachment_local_path(runs_root: Path, attachment: Any) -> Optional[Path]:
    if not isinstance(attachment, dict):
        return None
    raw_path = str(attachment.get("path") or attachment.get("localPath") or "").strip()
    if raw_path:
        try:
            target = Path(raw_path).resolve()
            target.relative_to(runs_root.resolve())
            if target.exists():
                return target
        except Exception:
            pass
    raw_url = str(attachment.get("url") or "").strip()
    if not raw_url:
        return None
    target = _resolve_runs_static_target(runs_root, raw_url)
    if target is not None and target.exists():
        return target
    return None


def _build_attachment_prompt_block(meta: dict[str, Any], runs_root: Path) -> str:
    attachments = meta.get("attachments") or []
    if not isinstance(attachments, list) or not attachments:
        return ""
    local_server_origin = _sanitize_local_server_origin(meta.get("localServerOrigin"))
    lines = ["", "", "[附件]", "以下是用户随消息附带的附件；优先使用“本机路径”读取。"]
    for att in attachments:
        if not isinstance(att, dict):
            continue
        display_name = str(att.get("originalName") or att.get("filename") or "unknown").strip() or "unknown"
        parts: list[str] = []
        local_path = _resolve_attachment_local_path(runs_root, att)
        if local_path is not None:
            parts.append(f"本机路径: {local_path}")
        raw_url = str(att.get("url") or "").strip()
        if raw_url and local_server_origin and raw_url.startswith("/"):
            parts.append(f"本机URL: {local_server_origin}{raw_url}")
        elif raw_url:
            parts.append(f"附件地址: {raw_url}")
        if parts:
            lines.append(f"- {display_name}；" + "；".join(parts))
        else:
            lines.append(f"- {display_name}")
    return "\n".join(lines) if len(lines) > 4 else ""


def _extract_agent_messages(log_text: str, max_items: int = 12, cli_type: str = "codex") -> list[str]:
    out: list[str] = []
    if not log_text:
        return out

    # Get adapter for parsing
    adapter_cls = get_adapter(cli_type) or CodexAdapter

    for raw in log_text.splitlines():
        line = raw.strip()
        payload = ""
        if line.startswith("[stdout] "):
            payload = line[len("[stdout] ") :].strip()
        elif line.startswith("{") and '"type"' in line:
            # 兼容旧日志：整段 stdout 被一次性写入时，后续行可能丢失 [stdout] 前缀。
            payload = line
        if not payload:
            continue

        parsed = _parse_adapter_output_line(adapter_cls, payload)
        if not parsed:
            continue

        txt = _extract_agent_message_text_from_parsed(parsed)
        if txt:
            out.append(txt)

    if len(out) > max_items:
        return out[-max_items:]
    return out


def _extract_agent_messages_from_file(path: Path, max_items: int = 12, cli_type: str = "codex") -> list[str]:
    out: deque[str] = deque(maxlen=max(1, int(max_items or 1)))
    if not path.exists():
        return []

    # Get adapter for parsing
    adapter_cls = get_adapter(cli_type) or CodexAdapter

    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            for raw in f:
                line = raw.strip()
                payload = ""
                if line.startswith("[stdout] "):
                    payload = line[len("[stdout] ") :].strip()
                elif line.startswith("{") and '"type"' in line:
                    # 兼容旧日志：整段 stdout 被一次性写入时，后续行可能丢失 [stdout] 前缀。
                    payload = line
                if not payload:
                    continue

                parsed = _parse_adapter_output_line(adapter_cls, payload)
                if not parsed:
                    continue

                txt = _extract_agent_message_text_from_parsed(parsed)
                if txt:
                    out.append(txt)
    except Exception:
        return []
    return list(out)


def _log_has_terminal_signal(path: Path, *, signal: str) -> bool:
    if not path.exists():
        return False
    needle = str(signal or "").strip()
    if not needle:
        return False
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            for raw in f:
                if needle in raw:
                    return True
    except Exception:
        return False
    return False


def _extract_agent_message_text_from_parsed(parsed: dict[str, Any]) -> str:
    """Extract agent-message text from normalized adapter parsed output."""
    if not isinstance(parsed, dict):
        return ""
    msg_type = str(parsed.get("type") or "")
    if msg_type == "item.completed":
        item = parsed.get("item") or {}
        if str(item.get("type") or "") == "agent_message":
            return str(item.get("text") or "").strip()
        return ""
    if msg_type == "text":
        return str(parsed.get("text") or "").strip()
    if msg_type == "message":
        return str(parsed.get("content") or parsed.get("text") or "").strip()
    if msg_type == "agent_message":
        return str(parsed.get("text") or parsed.get("content") or "").strip()
    return ""


_SKILL_TOKEN_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,80}$")
_UUID_TOKEN_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)
_SKILL_INLINE_RE = re.compile(r"`([A-Za-z0-9][A-Za-z0-9._-]{2,80})`")
_SKILL_DOLLAR_RE = re.compile(r"\$([A-Za-z0-9][A-Za-z0-9._-]{1,80})")
_SKILL_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+?SKILL\.md[^)]*)\)", re.IGNORECASE)
_SKILL_PATH_RE = re.compile(r"/([^/]+)/SKILL\.md", re.IGNORECASE)
_BUSINESS_PATH_RE = re.compile(r"(/[^\s\"'`<>]+?\.(?:md|markdown|html?|pdf|png|jpe?g|webp|gif|svg|docx?|xlsx?|pptx?|txt|json|csv|toml|ya?ml))", re.IGNORECASE)
_BUSINESS_MARKER_RE = re.compile(r"(?:\[|【)\s*(任务|问题|讨论|反馈|沉淀|材料)\s*(?:\]|】)\s*[:：]?\s*([^\n\[\]【】]{1,120})")
_SKILL_BLOCKED = {
    "task.js",
    "task.css",
    "task.html.tpl",
    "server.py",
    "task-dashboard",
    "codex",
}
_KNOWN_SKILL_NAMES: Optional[set[str]] = None
_KNOWN_SKILL_LOCK = threading.Lock()


def _get_known_skill_names() -> set[str]:
    global _KNOWN_SKILL_NAMES
    cached = _KNOWN_SKILL_NAMES
    if cached is not None:
        return cached
    with _KNOWN_SKILL_LOCK:
        cached2 = _KNOWN_SKILL_NAMES
        if cached2 is not None:
            return cached2
        names: set[str] = set()
        roots = [
            Path(__file__).resolve().parent / ".codex" / "skills",
            Path.home() / ".codex" / "skills",
        ]
        for root in roots:
            if not root.exists():
                continue
            try:
                for skill_file in root.rglob("SKILL.md"):
                    nm = skill_file.parent.name.strip().lower()
                    if nm and _SKILL_TOKEN_RE.match(nm):
                        names.add(nm)
            except Exception:
                continue
        _KNOWN_SKILL_NAMES = names
        return names


def _normalize_skill_token(raw: Any) -> str:
    t = str(raw or "").strip().strip("`").strip()
    if not t:
        return ""
    if t.startswith("$"):
        t = t[1:].strip()
    if "/" in t:
        t = t.rstrip("/").rsplit("/", 1)[-1].strip()
    if t.lower().endswith(".md"):
        t = t[:-3].strip()
    t = t.lower()
    if not t or not _SKILL_TOKEN_RE.match(t):
        return ""
    if _UUID_TOKEN_RE.match(t):
        return ""
    if t in _SKILL_BLOCKED:
        return ""
    return t


def _is_skill_candidate(token: str, known: set[str]) -> bool:
    if not token:
        return False
    if token in known:
        return True
    if "skill" in token:
        return True
    if token.count("-") >= 2:
        return True
    return False


def _extract_skills_used_from_texts(texts: list[str], max_items: int = 20) -> list[str]:
    if not texts:
        return []
    known = _get_known_skill_names()
    out: list[str] = []
    seen: set[str] = set()

    def _push(raw: Any) -> None:
        tok = _normalize_skill_token(raw)
        if not tok or tok in seen:
            return
        if not _is_skill_candidate(tok, known):
            return
        seen.add(tok)
        out.append(tok)

    for txt0 in texts:
        txt = str(txt0 or "")
        if not txt:
            continue
        for label, path in _SKILL_LINK_RE.findall(txt):
            _push(label)
            if path:
                m = _SKILL_PATH_RE.search(path)
                if m:
                    _push(m.group(1))
        for tok in _SKILL_DOLLAR_RE.findall(txt):
            _push(tok)
        for tok in _SKILL_INLINE_RE.findall(txt):
            _push(tok)
        if len(out) >= max_items:
            return out[:max_items]
    return out[:max_items]


def _normalize_skills_used_value(raw: Any, max_items: int = 20) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        tok = _normalize_skill_token(item)
        if not tok or tok in seen:
            continue
        seen.add(tok)
        out.append(tok)
        if len(out) >= max_items:
            break
    return out


_BUSINESS_ALLOWED_TYPES = {"任务", "问题", "讨论", "反馈", "沉淀", "材料", "其他"}
_BUSINESS_PATH_SEGMENTS = [
    "/任务规划/",
    "/协同空间/",
    "/产出物/",
    "/任务/",
    "/问题/",
    "/讨论空间/",
    "/反馈/",
    "/沉淀/",
    "/材料/",
]


def _clean_business_path(raw: Any) -> str:
    p = str(raw or "").strip().strip("`").strip()
    if not p:
        return ""
    while p and p[-1] in ").,;:，。；：】]>}":
        p = p[:-1]
    if not p.startswith("/"):
        return ""
    low = p.lower()
    m = re.search(r"\.(md|markdown|html?|pdf|png|jpe?g|webp|gif|svg|docx?|xlsx?|pptx?|txt|json|csv|toml|ya?ml)", low)
    if not m:
        return ""
    p = p[: m.end()]
    low = p.lower()
    if low.endswith("/skill.md") or "/.codex/" in low:
        return ""
    if not any(seg in p for seg in _BUSINESS_PATH_SEGMENTS):
        return ""
    return p


def _strip_business_title_ext(name: str) -> str:
    t = str(name or "").strip()
    if not t:
        return ""
    return re.sub(r"\.(md|markdown|html?|pdf|png|jpe?g|webp|gif|svg|docx?|xlsx?|pptx?|txt|json|csv|toml|ya?ml)$", "", t, flags=re.IGNORECASE)


def _business_type_from_path(path: str, title: str = "") -> str:
    p = str(path or "")
    if "/任务/" in p:
        return "任务"
    if "/问题/" in p:
        return "问题"
    if "/讨论空间/" in p:
        return "讨论"
    if "/反馈/" in p:
        return "反馈"
    if "/产出物/沉淀/" in p or "/沉淀/" in p:
        return "沉淀"
    if "/产出物/材料/" in p or "/材料/" in p:
        return "材料"
    t = str(title or "")
    if "【任务】" in t:
        return "任务"
    if "【问题】" in t:
        return "问题"
    if "讨论" in t:
        return "讨论"
    if "【反馈】" in t or "反馈" in t:
        return "反馈"
    if "沉淀" in t:
        return "沉淀"
    if "材料" in t:
        return "材料"
    return "其他"


def _normalize_business_ref_item(raw: Any) -> Optional[dict[str, str]]:
    if not isinstance(raw, dict):
        return None
    path = _clean_business_path(raw.get("path"))
    title = _safe_text(raw.get("title"), 200).strip()
    if not title and path:
        title = path.rsplit("/", 1)[-1]
        title = _strip_business_title_ext(title)
    if not title:
        return None
    typ = _safe_text(raw.get("type"), 20).strip()
    if typ not in _BUSINESS_ALLOWED_TYPES:
        typ = _business_type_from_path(path, title)
    return {
        "type": typ if typ in _BUSINESS_ALLOWED_TYPES else "其他",
        "title": title,
        "path": path,
    }


def _normalize_business_refs_value(raw: Any, max_items: int = 24) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        return []
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in raw:
        norm = _normalize_business_ref_item(item)
        if not norm:
            continue
        key = f"{norm.get('type','')}|{norm.get('path','')}|{norm.get('title','')}"
        if key in seen:
            continue
        seen.add(key)
        out.append(norm)
        if len(out) >= max_items:
            break
    return out


def _extract_business_refs_from_texts(texts: list[str], max_items: int = 24) -> list[dict[str, str]]:
    if not texts:
        return []
    out: list[dict[str, str]] = []
    seen: set[str] = set()

    def _push(ref_type: str, title_raw: Any, path_raw: Any = "") -> None:
        path = _clean_business_path(path_raw)
        title = _safe_text(title_raw, 200).strip()
        if not title and path:
            title = path.rsplit("/", 1)[-1]
            title = _strip_business_title_ext(title)
        if not title:
            return
        typ = str(ref_type or "").strip()
        if typ not in _BUSINESS_ALLOWED_TYPES:
            typ = _business_type_from_path(path, title)
        if typ not in _BUSINESS_ALLOWED_TYPES:
            typ = "其他"
        key = f"{typ}|{path}|{title}"
        if key in seen:
            return
        seen.add(key)
        out.append({"type": typ, "title": title, "path": path})

    for txt0 in texts:
        txt = str(txt0 or "")
        if not txt:
            continue
        for raw_path in _BUSINESS_PATH_RE.findall(txt):
            path = _clean_business_path(raw_path)
            if not path:
                continue
            title = path.rsplit("/", 1)[-1]
            title = _strip_business_title_ext(title)
            _push(_business_type_from_path(path, title), title, path)
            if len(out) >= max_items:
                return out[:max_items]
        txt_for_markers = _BUSINESS_PATH_RE.sub(" ", txt)
        for typ, title_raw in _BUSINESS_MARKER_RE.findall(txt_for_markers):
            title = str(title_raw or "").strip()
            if not title:
                continue
            for sep in ["。", "；", ";", "，", ",", "\n"]:
                if sep in title:
                    title = title.split(sep, 1)[0].strip()
            if len(title) > 80:
                title = title[:80].strip()
            _push(typ, title, "")
            if len(out) >= max_items:
                return out[:max_items]
    return out[:max_items]


def _parse_adapter_output_line(adapter_cls: Any, payload: str) -> Optional[dict[str, Any]]:
    txt = str(payload or "").strip()
    if not txt:
        return None
    parse_fn = getattr(adapter_cls, "parse_output_line", None)
    if callable(parse_fn):
        try:
            parsed = parse_fn(txt)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
    # 兜底：兼容测试桩或部分 CLI 的 JSON 行。
    if txt.startswith("{"):
        try:
            obj = json.loads(txt)
            if isinstance(obj, dict):
                return obj
        except Exception:
            return None
    return None


def _error_hint(err: str) -> str:
    raw = _normalize_cli_runtime_text(err)
    e = raw.lower()
    if not e:
        return ""
    perm_kind, perm_target = _extract_permission_denied_context(raw)
    if perm_kind or "permission denied" in e:
        target_desc = f"“{perm_target}”" if perm_target else "目标目录或工具调用"
        if perm_kind == "external_directory":
            return (
                f"CLI 访问工作区外目录被拒绝：{target_desc}。"
                "当前任务引用了外部项目路径，但运行时未放行该目录；"
                "请把目标目录纳入当前工作区/镜像目录，或在对应 CLI 侧放开该目录访问后重试。"
            )
        return (
            f"CLI 工具权限被拒绝：{target_desc}。"
            "请检查该 CLI 的目录/工具调用授权设置，必要时调整任务范围后重试。"
        )
    if "no such file or directory" in e:
        missing_path = ""
        m = re.search(r"No such file or directory:\s*['\"]([^'\"]+)['\"]", raw, re.IGNORECASE)
        if m:
            missing_path = str(m.group(1) or "").strip()
        command = ""
        if missing_path:
            try:
                command = Path(missing_path).name.strip()
            except Exception:
                command = ""
        label = cli_bin_command_name(command or "cli") if command else "CLI"
        path_desc = f"“{missing_path}”" if missing_path else "当前配置路径"
        return (
            f"{label} 启动路径无效：未找到 {path_desc}。"
            f"请在右上角“系统设置”→“CLI 联通”里修正 {label} 的本机覆盖路径；"
            "若本机已加入 PATH，可直接清空该项改为自动发现。保存后重启本机服务再重试。"
        )
    if "timeout>" in e:
        return "执行超时：任务可能已部分完成，但最终总结未写回。可用“回收结果”快速收口。"
    if "interrupted" in e:
        return "进程中断：常见于服务重启或运行进程退出。可重试或回收结果。"
    if _is_transient_network_error(e):
        return "网络波动：系统已做自动重试但仍失败。建议稍后重试，或先用“回收结果”收口已完成内容。"
    return ""


_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def _normalize_cli_runtime_text(text: Any) -> str:
    raw = "" if text is None else str(text)
    if not raw:
        return ""
    stripped = _ANSI_ESCAPE_RE.sub("", raw)
    return stripped.replace("\r\n", "\n").replace("\r", "\n").strip()


def _extract_permission_denied_context(text: Any) -> tuple[str, str]:
    raw = _normalize_cli_runtime_text(text)
    if not raw:
        return "", ""
    lowered = raw.lower()
    denied_match = re.search(r"([a-z0-9_]+)\s+permission denied(?::\s*(.+))?$", raw, re.IGNORECASE)
    if denied_match:
        kind = str(denied_match.group(1) or "").strip().lower()
        target = str(denied_match.group(2) or "").strip()
        return kind, target
    explicit_reject = (
        "the user rejected permission to use this specific tool call" in lowered
        or "permission denied" in lowered
        or "auto-rejecting" in lowered
    )
    match = re.search(r"permission requested:\s*([a-z0-9_]+)\s*\(([^)]+)\)", raw, re.IGNORECASE)
    if not match:
        return ("permission", "") if explicit_reject else ("", "")
    if not explicit_reject:
        return "", ""
    kind = str(match.group(1) or "").strip().lower()
    target = str(match.group(2) or "").strip()
    return kind, target


def _extract_permission_denied_error(text: Any) -> str:
    kind, target = _extract_permission_denied_context(text)
    if not kind:
        return ""
    if kind == "permission" and not target:
        return "permission denied"
    if target:
        return f"{kind} permission denied: {target}"
    return f"{kind} permission denied"


def _detect_terminal_text_cli_incomplete_error(
    cli_type: str,
    *,
    log_path: Path | str | None = None,
    log_text: str = "",
) -> str:
    cli = str(cli_type or "").strip().lower()
    if cli not in {"claude", "opencode"}:
        return ""
    text = _normalize_cli_runtime_text(log_text)
    if not text and log_path:
        try:
            text = _normalize_cli_runtime_text(_tail_text(Path(log_path), max_chars=24_000))
        except Exception:
            text = ""
    if not text:
        return ""

    pending_error = ""
    saw_stdout_after_error = False
    for raw_line in text.splitlines():
        line = _normalize_cli_runtime_text(raw_line)
        if not line:
            continue
        if line.startswith("[stdout] "):
            payload = str(line[len("[stdout] ") :]).strip()
            if payload and pending_error:
                saw_stdout_after_error = True
            continue
        err = _extract_permission_denied_error(line)
        if err:
            if not pending_error or pending_error == "permission denied":
                pending_error = err
            saw_stdout_after_error = False
    if pending_error and not saw_stdout_after_error:
        return pending_error
    return ""


def _default_run_timeout_s() -> Optional[int]:
    raw = str(os.environ.get("CCB_TIMEOUT_S") or "").strip()
    if raw:
        try:
            v = int(raw)
            if v > 0:
                return v
        except Exception:
            pass
    # 默认不限制执行时长；仅在显式配置 CCB_TIMEOUT_S>0 时启用超时。
    return None


def _default_run_no_progress_timeout_s(cli_type: str = "codex") -> Optional[int]:
    raw = str(os.environ.get("CCB_NO_PROGRESS_TIMEOUT_S") or "").strip()
    if raw:
        try:
            v = int(raw)
            if v <= 0:
                return None
            return min(v, 24 * 3600)
        except Exception:
            pass
    if str(cli_type or "codex").strip().lower() == "claude":
        return None
    # 默认 30 分钟：运行中若长期无任何日志/输出进展，按卡住处理并回收状态。
    return 30 * 60


def _default_network_retry_max() -> int:
    raw = str(os.environ.get("CCB_NETWORK_RETRY_MAX") or "").strip()
    if raw:
        try:
            v = int(raw)
            if v < 0:
                return 0
            return min(v, 5)
        except Exception:
            pass
    # 默认重试 1 次：覆盖短时抖动，避免无边界重试。
    return 1


def _default_network_retry_base_s() -> float:
    raw = str(os.environ.get("CCB_NETWORK_RETRY_BASE_S") or "").strip()
    if raw:
        try:
            v = float(raw)
            if v <= 0:
                return 0.8
            return min(v, 30.0)
        except Exception:
            pass
    return 1.2


def _default_network_resume_delay_s() -> int:
    raw = str(os.environ.get("CCB_NETWORK_RESUME_DELAY_S") or "").strip()
    if raw:
        try:
            v = int(raw)
            if v < 5:
                return 5
            return min(v, 3600)
        except Exception:
            pass
    return 60


def _default_network_resume_message() -> str:
    raw = str(os.environ.get("CCB_NETWORK_RESUME_MESSAGE") or "").strip()
    if raw:
        return _safe_text(raw, 400)
    return "网络中断了，请继续"


def _default_profile_not_found_suppress_s() -> int:
    raw = str(os.environ.get("CCB_PROFILE_NOT_FOUND_SUPPRESS_S") or "").strip()
    if raw:
        try:
            v = int(raw)
            if v < 0:
                return 0
            return min(v, 24 * 3600)
        except Exception:
            pass
    # 默认 30 分钟内抑制同 profile 的重复无效尝试，降低日志噪声与额外等待。
    return 30 * 60


def _default_session_busy_timeout_s() -> int:
    raw = str(os.environ.get("CCB_SESSION_BUSY_TIMEOUT_S") or "").strip()
    if raw:
        try:
            v = int(raw)
            if v < 0:
                return 0
            return min(v, 24 * 3600)
        except Exception:
            pass
    # 默认 8 分钟：避免外部占用导致 run 长期排队不收敛。
    return 8 * 60


def _default_restart_resume_window_s() -> int:
    raw = str(os.environ.get("CCB_RESTART_RESUME_WINDOW_S") or "").strip()
    if raw:
        try:
            v = int(raw)
            if v < 60:
                return 60
            return min(v, 7 * 24 * 3600)
        except Exception:
            pass
    # 默认只处理最近 3 小时内的“重启中断” run，避免一次性补发历史积压。
    return 3 * 3600


def _default_restart_resume_message() -> str:
    raw = str(os.environ.get("CCB_RESTART_RESUME_MESSAGE") or "").strip()
    if raw:
        return _safe_text(raw, 400)
    return "因服务重启而中断，请继续开展工作。"


def _is_transient_network_error(text: str) -> bool:
    e = str(text or "").strip().lower()
    if not e:
        return False
    patterns = [
        "transport channel closed",
        "stream disconnected before completion",
        "error sending request for url",
        "connection closed via error",
        "connection reset by peer",
        "failed to connect to websocket",
        "responses_websocket",
        "operation timed out",
        "timed out (os error 60)",
        "connection timed out",
        "failed to refresh available models",
        "temporarily unavailable",
        "tls handshake",
        "reconnecting...",
    ]
    return any(p in e for p in patterns)


def _is_auth_error(text: str) -> bool:
    e = str(text or "").strip().lower()
    if not e:
        return False
    patterns = [
        "authrequired",
        "invalid access token",
        "unauthorized",
        "www_authenticate_header",
        "forbidden",
    ]
    if any(p in e for p in patterns):
        return True
    return re.search(r"\b401\b", e) is not None


def _server_token() -> str:
    return str(os.environ.get("TASK_DASHBOARD_TOKEN") or "").strip()


def _dashboard_build_paths() -> dict[str, Path]:
    """Resolve static dashboard build script and output paths."""
    repo_root = _repo_root()
    script = repo_root / "build_project_task_dashboard.py"
    out_task = repo_root / "dist" / "project-task-dashboard.html"
    out_overview = repo_root / "dist" / "project-overview-dashboard.html"
    out_communication = repo_root / "dist" / "project-communication-audit.html"
    out_message_risk_dashboard = repo_root / "dist" / "project-message-risk-dashboard.html"
    out_status_report = repo_root / "dist" / "project-status-report.html"
    return {
        "repo_root": repo_root,
        "script": script,
        "out_task": out_task,
        "out_overview": out_overview,
        "out_communication": out_communication,
        "out_message_risk_dashboard": out_message_risk_dashboard,
        "out_status_report": out_status_report,
    }


def _rebuild_dashboard_static(timeout_s: int = 120) -> dict[str, Any]:
    """Rebuild dashboard static html files and return a compact summary."""
    paths = _dashboard_build_paths()
    script = paths["script"]
    if not script.exists():
        raise RuntimeError(f"build script not found: {script}")

    repo_root = paths["repo_root"]
    cmd = [
        str(sys.executable or "python3"),
        str(script),
        "--root",
        str(repo_root),
        "--out-task",
        "dist/project-task-dashboard.html",
        "--out-overview",
        "dist/project-overview-dashboard.html",
        "--out-communication",
        "dist/project-communication-audit.html",
        "--out-message-risk-dashboard",
        "dist/project-message-risk-dashboard.html",
        "--out-status-report",
        "dist/project-status-report.html",
    ]
    started = time.time()
    proc = subprocess.run(
        cmd,
        cwd=str(script.parent),
        capture_output=True,
        text=True,
        timeout=max(30, int(timeout_s)),
        env=dict(os.environ),
    )
    duration_ms = int((time.time() - started) * 1000)
    stdout = str(proc.stdout or "")
    stderr = str(proc.stderr or "")
    if proc.returncode != 0:
        detail = _safe_text((stderr or stdout or f"exit={proc.returncode}").strip(), 2000)
        raise RuntimeError(f"dashboard rebuild failed: {detail}")

    out_task = paths["out_task"]
    out_overview = paths["out_overview"]
    out_communication = paths["out_communication"]
    out_status_report = paths["out_status_report"]
    task_mtime = out_task.stat().st_mtime if out_task.exists() else 0
    overview_mtime = out_overview.stat().st_mtime if out_overview.exists() else 0
    communication_mtime = out_communication.stat().st_mtime if out_communication.exists() else 0
    status_report_mtime = out_status_report.stat().st_mtime if out_status_report.exists() else 0
    latest_mtime = max(task_mtime, overview_mtime, communication_mtime, status_report_mtime, time.time())
    rebuilt_at = time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(latest_mtime))
    return {
        "ok": True,
        "duration_ms": duration_ms,
        "rebuilt_at": rebuilt_at,
        "script": str(script),
        "task_page": str(out_task),
        "overview_page": str(out_overview),
        "communication_page": str(out_communication),
        "status_report_page": str(out_status_report),
        "stdout_tail": _safe_text(stdout.strip(), 1200),
    }


def _read_task_dashboard_generated_at() -> str:
    """Read generated_at from built task dashboard html."""
    out_task = _dashboard_build_paths().get("out_task")
    if not isinstance(out_task, Path) or not out_task.exists():
        return ""
    try:
        text = out_task.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""
    m = re.search(r'"generated_at"\s*:\s*"([^"]+)"', text)
    if m:
        return str(m.group(1) or "").strip()
    m2 = re.search(r"generated_at\s*=\s*([^\s<]+)", text)
    if m2:
        return str(m2.group(1) or "").strip()
    return ""


def _append_session_dedup_log(entry: dict[str, Any]) -> str:
    """Append dedup action ledger for audit."""
    log_path = Path(__file__).resolve().parent / ".run" / "session-dedup-log.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(entry, ensure_ascii=False)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    return str(log_path)


def _with_local_config_enabled() -> bool:
    raw = str(os.environ.get("TASK_DASHBOARD_WITH_LOCAL_CONFIG") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _config_toml_path() -> Path:
    return resolve_dashboard_config_path(Path(__file__).resolve().parent)


def _config_local_toml_path() -> Path:
    return resolve_dashboard_local_config_path(Path(__file__).resolve().parent)


def _cfg_file_mtime_ns(path: Path) -> int:
    try:
        return int(path.stat().st_mtime_ns)
    except Exception:
        return -1


def _path_size(path: Path) -> int:
    try:
        return int(path.stat().st_size)
    except Exception:
        return -1


def _dashboard_cfg_cache_enabled() -> bool:
    raw = str(os.environ.get("CCB_CFG_CACHE") or "").strip().lower()
    if raw in {"0", "false", "off", "no"}:
        return False
    return True


def _dashboard_cfg_cache_stat_ttl_s() -> float:
    raw = str(os.environ.get("CCB_CFG_CACHE_STAT_TTL_MS") or "").strip()
    if not raw:
        return 0.5
    try:
        ms = float(raw)
    except Exception:
        return 0.5
    if ms < 0:
        return 0.0
    return min(ms / 1000.0, 5.0)


def _dashboard_cfg_cache_signature(*, with_local: bool) -> tuple[Any, ...]:
    config_path = _config_toml_path()
    local_path = _config_local_toml_path()
    return (
        str(config_path),
        _cfg_file_mtime_ns(config_path),
        bool(with_local),
        _cfg_file_mtime_ns(local_path) if with_local else -2,
    )


def _clear_dashboard_cfg_cache() -> None:
    with _DASHBOARD_CFG_CACHE_LOCK:
        _DASHBOARD_CFG_CACHE["cfg"] = {}
        _DASHBOARD_CFG_CACHE["signature"] = ()
        _DASHBOARD_CFG_CACHE["with_local"] = False
        _DASHBOARD_CFG_CACHE["checked_at_mono"] = 0.0
    runtime_clear_work_context_cache()

def _task_items_cache_enabled() -> bool:
    raw = str(os.environ.get("CCB_TASK_ITEMS_CACHE") or "").strip().lower()
    if raw in {"0", "false", "off", "no"}:
        return False
    return True


def _task_items_cache_ttl_s() -> float:
    raw = str(os.environ.get("CCB_TASK_ITEMS_CACHE_TTL_MS") or "").strip()
    if not raw:
        return 3.0
    try:
        ms = float(raw)
    except Exception:
        return 3.0
    if ms <= 0:
        return 0.0
    return min(ms / 1000.0, 30.0)


def _auto_inspection_preview_cache_ttl_s() -> float:
    raw = str(os.environ.get("CCB_AUTO_INSPECTION_PREVIEW_CACHE_TTL_MS") or "").strip()
    if not raw:
        return 2.0
    try:
        ms = float(raw)
    except Exception:
        return 2.0
    if ms <= 0:
        return 0.0
    return min(ms / 1000.0, 20.0)


def _clear_project_task_items_cache(project_id: str = "") -> None:
    pid = str(project_id or "").strip()
    with _PROJECT_TASK_ITEMS_CACHE_LOCK:
        if not pid:
            _PROJECT_TASK_ITEMS_CACHE.clear()
            return
        drop = [k for k in _PROJECT_TASK_ITEMS_CACHE.keys() if k.startswith(pid + "|")]
        for key in drop:
            _PROJECT_TASK_ITEMS_CACHE.pop(key, None)


def _clear_auto_inspection_preview_cache(project_id: str = "") -> None:
    pid = str(project_id or "").strip()
    with _AUTO_INSPECTION_PREVIEW_CACHE_LOCK:
        if not pid:
            _AUTO_INSPECTION_PREVIEW_CACHE.clear()
            return
        drop = [k for k in _AUTO_INSPECTION_PREVIEW_CACHE.keys() if k.startswith(pid + "|")]
        for key in drop:
            _AUTO_INSPECTION_PREVIEW_CACHE.pop(key, None)


def _load_dashboard_cfg_current() -> dict[str, Any]:
    script_dir = Path(__file__).resolve().parent
    with_local = _with_local_config_enabled()
    if not _dashboard_cfg_cache_enabled():
        try:
            cfg = load_dashboard_config(script_dir, with_local=with_local)
        except Exception:
            return {}
        return cfg if isinstance(cfg, dict) else {}

    ttl_s = _dashboard_cfg_cache_stat_ttl_s()
    now_mono = time.monotonic()
    with _DASHBOARD_CFG_CACHE_LOCK:
        cached_cfg = _DASHBOARD_CFG_CACHE.get("cfg")
        cached_with_local = bool(_DASHBOARD_CFG_CACHE.get("with_local"))
        checked_at = float(_DASHBOARD_CFG_CACHE.get("checked_at_mono") or 0.0)
        if (
            isinstance(cached_cfg, dict)
            and cached_cfg
            and cached_with_local == bool(with_local)
            and (now_mono - checked_at) <= ttl_s
        ):
            return cached_cfg

    signature = _dashboard_cfg_cache_signature(with_local=with_local)
    with _DASHBOARD_CFG_CACHE_LOCK:
        cached_cfg = _DASHBOARD_CFG_CACHE.get("cfg")
        cached_signature = _DASHBOARD_CFG_CACHE.get("signature")
        cached_with_local = bool(_DASHBOARD_CFG_CACHE.get("with_local"))
        if (
            isinstance(cached_cfg, dict)
            and cached_cfg
            and cached_signature == signature
            and cached_with_local == bool(with_local)
        ):
            _DASHBOARD_CFG_CACHE["checked_at_mono"] = now_mono
            return cached_cfg

    try:
        cfg = load_dashboard_config(script_dir, with_local=with_local)
    except Exception:
        return {}
    out = cfg if isinstance(cfg, dict) else {}
    with _DASHBOARD_CFG_CACHE_LOCK:
        _DASHBOARD_CFG_CACHE["cfg"] = out
        _DASHBOARD_CFG_CACHE["signature"] = signature
        _DASHBOARD_CFG_CACHE["with_local"] = bool(with_local)
        _DASHBOARD_CFG_CACHE["checked_at_mono"] = now_mono
    return out


def _list_project_ids_from_cfg(cfg: dict[str, Any]) -> list[str]:
    out: list[str] = []
    projects = cfg.get("projects")
    if not isinstance(projects, list):
        return out
    for p in projects:
        if not isinstance(p, dict):
            continue
        pid = str(p.get("id") or "").strip()
        if pid:
            out.append(pid)
    return out


def _default_project_id_from_cfg(cfg: dict[str, Any]) -> str:
    ids = _list_project_ids_from_cfg(cfg)
    if not ids:
        return ""
    preferred = str(os.environ.get("TASK_DASHBOARD_PROJECT_ID") or "").strip()
    if preferred and preferred in ids:
        return preferred
    if "task_dashboard" in ids:
        return "task_dashboard"
    return ids[0]


def _current_project_id_from_cfg(cfg: dict[str, Any]) -> str:
    return _default_project_id_from_cfg(cfg)


def _resolve_runtime_project_id(
    cfg: dict[str, Any],
    *,
    environment_name: str = "",
    port: int = 0,
) -> str:
    ids = _list_project_ids_from_cfg(cfg)
    if not ids:
        return ""
    preferred = str(os.environ.get("TASK_DASHBOARD_PROJECT_ID") or "").strip()
    if preferred and preferred in ids:
        return preferred
    port_candidates = {
        18765: ("task_dashboard", "task_dashboard_prod"),
        18766: ("task_dashboard_dev",),
        18767: ("task_dashboard_prod_mirror",),
        18768: ("task_dashboard_dev_control", "task_dashboard_dev"),
        18769: ("task_dashboard_prod_debug",),
    }
    for candidate in port_candidates.get(int(port or 0), ()):
        if candidate in ids:
            return candidate
    env_slug = str(environment_name or "").strip().lower()
    if env_slug == "dev":
        for candidate in ("task_dashboard_dev_control", "task_dashboard_dev"):
            if candidate in ids:
                return candidate
    if env_slug == "stable":
        for candidate in ("task_dashboard", "task_dashboard_prod"):
            if candidate in ids:
                return candidate
    if env_slug == "refactor" and "task_dashboard_prod_debug" in ids:
        return "task_dashboard_prod_debug"
    return _default_project_id_from_cfg(cfg)


def _project_runtime_role(project_id: str) -> str:
    pid = str(project_id or "").strip()
    if not pid:
        return ""
    project_cfg = _find_project_cfg(pid) or {}
    runtime_role = str(project_cfg.get("runtime_role") or "").strip().lower()
    if runtime_role:
        return runtime_role
    project_mode = str(project_cfg.get("project_mode") or "").strip().lower()
    if project_mode:
        return project_mode
    if pid == "task_dashboard_prod":
        return "prod"
    if pid == "task_dashboard_dev":
        return "dev"
    if pid == "task_dashboard_prod_mirror":
        return "prod_mirror"
    if pid == "task_dashboard":
        return "prod"
    return ""


def _build_global_resource_graph_payload(
    *,
    store: "RunStore",
    session_store: SessionStore,
    project_id: str = "",
    channel_name: str = "",
    run_limit: int = 600,
) -> dict[str, Any]:
    cfg = _load_dashboard_cfg_current()
    return build_global_resource_graph(
        cfg=cfg,
        root=_repo_root(),
        session_store=session_store,
        run_store=store,
        project_id=str(project_id or "").strip(),
        channel_name=str(channel_name or "").strip(),
        run_limit=int(run_limit or 600),
    )


def _runtime_cfg_max_concurrency_from_cfg(cfg: dict[str, Any]) -> Optional[int]:
    runtime_cfg = cfg.get("runtime")
    if not isinstance(runtime_cfg, dict):
        return None
    raw = runtime_cfg.get("max_concurrency")
    try:
        n = int(raw)
    except Exception:
        return None
    if 1 <= n <= 32:
        return n
    return None


def _resolve_effective_max_concurrency(*, cfg: Optional[dict[str, Any]] = None) -> tuple[int, str]:
    raw_env = str(os.environ.get("CCB_MAX_CONCURRENCY") or "").strip()
    if raw_env:
        try:
            return max(1, min(32, int(raw_env))), "env"
        except Exception:
            pass
    c = cfg if isinstance(cfg, dict) else _load_dashboard_cfg_current()
    n = _runtime_cfg_max_concurrency_from_cfg(c)
    if n is not None:
        return n, "config"
    return 8, "default"


def _normalize_cli_type_id(value: Any) -> str:
    txt = str(value or "").strip().lower()
    return txt or "codex"


def _cli_command_for_type(value: Any) -> str:
    txt = _normalize_cli_type_id(value)
    if txt == "trae":
        return "trae-cli"
    return txt


def _load_local_cli_bin_overrides() -> dict[str, str]:
    return load_local_cli_bin_overrides(Path(__file__).resolve().parent)


def _collect_cli_tools_snapshot(
    cfg: dict[str, Any],
    *,
    session_store: Optional[SessionStore] = None,
) -> dict[str, Any]:
    available: list[dict[str, Any]] = []
    known_ids: set[str] = set()
    try:
        infos = list_cli_types()
    except Exception:
        infos = []
    for info in infos:
        cid = _normalize_cli_type_id(getattr(info, "id", ""))
        if not cid:
            continue
        known_ids.add(cid)
        available.append(
            {
                "id": cid,
                "name": str(getattr(info, "name", cid)),
                "description": str(getattr(info, "description", "")),
                "enabled": bool(getattr(info, "enabled", True)),
            }
        )

    stats: dict[str, dict[str, Any]] = {}

    def _ensure(cid: str) -> dict[str, Any]:
        key = _normalize_cli_type_id(cid)
        row = stats.get(key)
        if isinstance(row, dict):
            return row
        row = {
            "id": key,
            "effective_channel_count": 0,
            "explicit_channel_count": 0,
            "session_binding_count": 0,
            "projects": set(),
        }
        stats[key] = row
        return row

    projects = cfg.get("projects")
    if isinstance(projects, list):
        for p in projects:
            if not isinstance(p, dict):
                continue
            pid = str(p.get("id") or "").strip()
            if not pid:
                continue
            channels = p.get("channels")
            if isinstance(channels, list):
                for ch in channels:
                    if not isinstance(ch, dict):
                        continue
                    explicit_cli = str(ch.get("cli_type") or "").strip().lower()
                    effective_cli = _normalize_cli_type_id(explicit_cli or "codex")
                    row = _ensure(effective_cli)
                    row["effective_channel_count"] = int(row.get("effective_channel_count") or 0) + 1
                    row["projects"].add(pid)
                    if explicit_cli:
                        row["explicit_channel_count"] = int(row.get("explicit_channel_count") or 0) + 1
            if session_store is not None:
                try:
                    sessions = session_store.list_sessions(pid)
                except Exception:
                    sessions = []
                if isinstance(sessions, list):
                    for sess in sessions:
                        if not isinstance(sess, dict):
                            continue
                        cli = _normalize_cli_type_id(sess.get("cli_type"))
                        row = _ensure(cli)
                        row["session_binding_count"] = int(row.get("session_binding_count") or 0) + 1
                        row["projects"].add(pid)

    by_cli: list[dict[str, Any]] = []
    seen = set(known_ids)
    for cid in sorted(seen.union(set(stats.keys()))):
        base = next((x for x in available if x.get("id") == cid), None)
        row = stats.get(cid) or {}
        projects_set = row.get("projects") if isinstance(row.get("projects"), set) else set()
        command = _cli_command_for_type(cid)
        resolved = resolve_cli_executable_details(command)
        effective_bin = str(resolved.get("path") or "").strip()
        local_bins = _load_local_cli_bin_overrides()
        local_bin = str(local_bins.get(str(command).replace("-", "_")) or "").strip()
        item = {
            "id": cid,
            "name": str((base or {}).get("name") or cid),
            "enabled": bool((base or {}).get("enabled", True)),
            "effective_channel_count": int(row.get("effective_channel_count") or 0),
            "explicit_channel_count": int(row.get("explicit_channel_count") or 0),
            "session_binding_count": int(row.get("session_binding_count") or 0),
            "projects": sorted(str(x) for x in projects_set if str(x).strip()),
            "command": command,
            "command_label": cli_bin_command_name(command),
            "effective_bin": effective_bin,
            "bin_source": str(resolved.get("source") or ""),
            "bin_exists": bool(resolved.get("exists")),
            "bin_executable": bool(resolved.get("executable")),
            "local_bin": local_bin,
            "env_key": str(resolved.get("env_key") or ""),
        }
        item["configured"] = bool(
            item["effective_channel_count"] > 0 or item["session_binding_count"] > 0
        )
        by_cli.append(item)
    by_cli.sort(key=lambda x: (0 if x.get("configured") else 1, str(x.get("id") or "")))

    configured_ids = [str(x.get("id") or "") for x in by_cli if x.get("configured")]
    return {
        "available": available,
        "configured": {
            "by_cli": by_cli,
            "configured_ids": configured_ids,
        },
    }


def _set_runtime_max_concurrency_in_config_text(config_content: str, max_concurrency: int) -> str:
    import re

    content = str(config_content or "")
    n = int(max_concurrency)
    if n < 1 or n > 32:
        raise ValueError("max_concurrency out of range: 1..32")
    line = f"max_concurrency = {n}"

    m = re.search(r"(?m)^\[runtime\]\s*$", content)
    if m:
        next_hdr = re.search(r"(?m)^\[", content[m.end() :])
        sub_end = m.end() + (next_hdr.start() if next_hdr else len(content) - m.end())
        sub = content[m.start() : sub_end]
        if re.search(r"(?m)^\s*max_concurrency\s*=", sub):
            sub2 = re.sub(r"(?m)^\s*max_concurrency\s*=.*$", line, sub, count=1)
        else:
            sub2 = sub if sub.endswith("\n") else sub + "\n"
            sub2 += line + "\n"
        return content[: m.start()] + sub2 + content[sub_end:]

    suffix = "" if content.endswith("\n") else "\n"
    return content + suffix + "\n[runtime]\n" + line + "\n"


def _set_runtime_max_concurrency_in_config(max_concurrency: int) -> Path:
    config_path = _config_toml_path()
    if not config_path.exists():
        raise ValueError("config.toml not found")
    raw = config_path.read_text(encoding="utf-8")
    updated = _set_runtime_max_concurrency_in_config_text(raw, int(max_concurrency))
    _atomic_write_text(config_path, updated)
    _clear_dashboard_cfg_cache()
    return config_path


def _set_runtime_cli_bins_in_local_config(patch: dict[str, Any]) -> Path:
    path = save_local_cli_bin_overrides(patch, Path(__file__).resolve().parent)
    try:
        resolve_cli_executable.cache_clear()
    except Exception:
        pass
    try:
        resolve_cli_executable_details.cache_clear()
    except Exception:
        pass
    _clear_dashboard_cfg_cache()
    return path


def _resolve_dir(raw: str, repo_root: Path) -> Optional[Path]:
    txt = str(raw or "").strip()
    if not txt:
        return None
    p = Path(txt).expanduser()
    if not p.is_absolute():
        p = (repo_root / txt)
    # Prefer logical path (for consistent displayed workdir), fallback to resolved.
    if p.exists() and p.is_dir():
        return p
    try:
        rp = p.resolve()
        if rp.exists() and rp.is_dir():
            return rp
    except Exception:
        pass
    return None



def _resolve_project_workdir(project_id: str) -> Path:
    """
    Resolve runtime working directory by project.

    Priority:
    1) projects[].project_root_rel
    2) infer from projects[].task_root_rel (if ends with '任务规划', use parent)
    3) repo root
    """
    repo_root = _repo_root()
    p = _find_project_cfg(project_id)
    if p:
        project_root_rel = str(p.get("project_root_rel") or "").strip()
        resolved = _resolve_dir(project_root_rel, repo_root)
        if resolved:
            return resolved

        task_root_rel = str(p.get("task_root_rel") or "").strip()
        task_root = _resolve_dir(task_root_rel, repo_root)
        if task_root:
            if task_root.name == "任务规划":
                parent = task_root.parent
                if parent.exists() and parent.is_dir():
                    return parent
            return task_root

    return repo_root


def _normalize_execution_profile(value: Any, *, default: str = "sandboxed", allow_empty: bool = False) -> str:
    return runtime_normalize_execution_profile(value, default=default, allow_empty=allow_empty)


def _load_project_execution_context(
    project_id: str,
    *,
    environment_name: str = "",
    worktree_root: Path | str | None = None,
) -> dict[str, Any]:
    pid = str(project_id or "").strip()
    project_cfg = _find_project_cfg(pid) or {}
    raw_context = project_cfg.get("execution_context")
    configured_context = raw_context if isinstance(raw_context, dict) else {}
    configured = bool(configured_context)
    repo_root = _repo_root()

    resolved_environment = str(
        configured_context.get("environment")
        if "environment" in configured_context
        else configured_context.get("environmentName", "")
    ).strip() or str(environment_name or "stable").strip() or "stable"
    resolved_worktree_root = _resolve_dir(
        str(
            configured_context.get("worktree_root")
            if "worktree_root" in configured_context
            else configured_context.get("worktreeRoot", "")
        ).strip(),
        repo_root,
    )
    if resolved_worktree_root is None and worktree_root is not None:
        candidate_root = Path(worktree_root).expanduser()
        resolved_worktree_root = candidate_root if candidate_root.exists() and candidate_root.is_dir() else candidate_root
    source_root_text = str(resolved_worktree_root or "").strip()

    raw_workdir = str(configured_context.get("workdir") or "").strip()
    resolved_workdir: Optional[Path] = None
    if raw_workdir:
        candidate_base = resolved_worktree_root if isinstance(resolved_worktree_root, Path) else repo_root
        resolved_workdir = _resolve_dir(raw_workdir, candidate_base or repo_root)
    if resolved_workdir is None and pid:
        resolved_workdir = _resolve_project_workdir(pid)

    resolved_branch = str(configured_context.get("branch") or "").strip()
    if not resolved_branch:
        resolved_branch = runtime_detect_git_branch(source_root_text)

    resolved_runtime_root = str(
        configured_context.get("runtime_root")
        if "runtime_root" in configured_context
        else configured_context.get("runtimeRoot", "")
    ).strip()
    resolved_sessions_root = str(
        configured_context.get("sessions_root")
        if "sessions_root" in configured_context
        else configured_context.get("sessionsRoot", "")
    ).strip()
    resolved_runs_root = str(
        configured_context.get("runs_root")
        if "runs_root" in configured_context
        else configured_context.get("runsRoot", "")
    ).strip()
    if not resolved_runs_root and resolved_runtime_root:
        resolved_runs_root = str(Path(resolved_runtime_root) / ".runs")

    server_port: int | None = None
    raw_server_port = (
        configured_context.get("server_port")
        if "server_port" in configured_context
        else configured_context.get("serverPort")
    )
    if raw_server_port not in (None, "", False):
        try:
            server_port = int(raw_server_port)
        except Exception:
            server_port = None

    return {
        "project_id": pid,
        "profile": _normalize_execution_profile(configured_context.get("profile"), default="sandboxed"),
        "environment": resolved_environment,
        "worktree_root": source_root_text,
        "workdir": str(resolved_workdir or "").strip(),
        "branch": resolved_branch,
        "runtime_root": resolved_runtime_root,
        "sessions_root": resolved_sessions_root,
        "runs_root": resolved_runs_root,
        "server_port": server_port,
        "health_source": str(
            configured_context.get("health_source")
            if "health_source" in configured_context
            else configured_context.get("healthSource", "")
        ).strip(),
        "permissions": runtime_resolve_execution_profile_permissions(
            _normalize_execution_profile(configured_context.get("profile"), default="sandboxed"),
            dashboard_repo_root=Path(__file__).resolve().parent,
            config=_load_dashboard_cfg_current(),
        ),
        "configured": configured,
        "context_source": "project" if configured else "server_default",
    }


def _derive_session_work_context(
    session: dict[str, Any],
    *,
    project_id: str = "",
    environment_name: str = "",
    worktree_root: Path | str | None = None,
) -> dict[str, str]:
    return runtime_derive_session_work_context(
        session,
        project_id=project_id,
        environment_name=environment_name,
        worktree_root=worktree_root,
        resolve_project_workdir=_resolve_project_workdir,
        load_project_execution_context=_load_project_execution_context,
    )


def _apply_session_work_context(
    session: dict[str, Any],
    *,
    project_id: str = "",
    environment_name: str = "",
    worktree_root: Path | str | None = None,
) -> dict[str, Any]:
    return runtime_apply_session_work_context(
        session,
        project_id=project_id,
        environment_name=environment_name,
        worktree_root=worktree_root,
        resolve_project_workdir=_resolve_project_workdir,
        load_project_execution_context=_load_project_execution_context,
    )


def _stable_write_ack_requested(payload: Any) -> bool:
    return runtime_stable_write_ack_requested(payload)


def _session_context_write_requires_guard(
    session: dict[str, Any],
    update_fields: dict[str, Any],
    *,
    server_environment: str = "",
) -> bool:
    return runtime_session_context_write_requires_guard(
        session,
        update_fields,
        server_environment=server_environment,
    )


def _resolve_run_work_context(
    meta: dict[str, Any],
    *,
    project_id: str = "",
    session_context: dict[str, Any] | None = None,
    worktree_root: Path | str | None = None,
) -> dict[str, str]:
    return runtime_resolve_run_work_context(
        meta,
        project_id=project_id,
        session_context=session_context,
        worktree_root=worktree_root,
        resolve_project_workdir=_resolve_project_workdir,
        load_project_execution_context=_load_project_execution_context,
    )

def _project_channel_cli_type(project_id: str, channel_name: str) -> str:
    p = _find_project_cfg(project_id)
    channels = p.get("channels")
    if not isinstance(channels, list):
        return "codex"
    target = str(channel_name or "").strip()
    for ch in channels:
        if not isinstance(ch, dict):
            continue
        if str(ch.get("name") or "").strip() != target:
            continue
        cli_type = str(ch.get("cli_type") or "").strip()
        if cli_type:
            return cli_type
        break
    return "codex"


def _project_channel_model(project_id: str, channel_name: str) -> str:
    p = _find_project_cfg(project_id)
    channels = p.get("channels")
    if not isinstance(channels, list):
        return ""
    target = str(channel_name or "").strip()
    for ch in channels:
        if not isinstance(ch, dict):
            continue
        if str(ch.get("name") or "").strip() != target:
            continue
        model = str(ch.get("model") or "").strip()
        if model:
            return model
        break
    return ""


def _normalize_reasoning_effort(value: Any) -> str:
    txt = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if not txt:
        return ""
    alias = {
        "med": "medium",
        "normal": "medium",
        "default": "medium",
        "xhigh": "extra_high",
        "very_high": "extra_high",
        "ultra": "extra_high",
        "extra": "extra_high",
    }
    txt = alias.get(txt, txt)
    if txt in {"low", "medium", "high", "extra_high"}:
        return txt
    return ""


def _project_channel_reasoning_effort(project_id: str, channel_name: str) -> str:
    p = _find_project_cfg(project_id)
    channels = p.get("channels")
    if not isinstance(channels, list):
        return ""
    target = str(channel_name or "").strip()
    for ch in channels:
        if not isinstance(ch, dict):
            continue
        if str(ch.get("name") or "").strip() != target:
            continue
        effort = _normalize_reasoning_effort(ch.get("reasoning_effort"))
        if effort:
            return effort
        break
    return ""


def _project_channel_exists(project_id: str, channel_name: str) -> bool:
    p = _find_project_cfg(project_id)
    channels = p.get("channels")
    if not isinstance(channels, list):
        return False
    target = str(channel_name or "").strip()
    if not target:
        return False
    for ch in channels:
        if not isinstance(ch, dict):
            continue
        if str(ch.get("name") or "").strip() == target:
            return True
    return False


def _resolve_project_task_root(project_id: str) -> Optional[Path]:
    p = _find_project_cfg(project_id)
    if not p:
        return None
    repo_root = _repo_root()
    task_root_rel = str(p.get("task_root_rel") or "").strip()
    resolved = _resolve_dir(task_root_rel, repo_root)
    if resolved:
        return resolved

    # Compatibility fallback:
    # if repo_root drifted (Desktop/workspace alias, launch context difference),
    # task_dashboard should still be able to locate its local 任务规划目录.
    script_dir = Path(__file__).resolve().parent
    norm_rel = _normalize_task_path_identity(task_root_rel)
    marker = "task-dashboard/"
    if norm_rel:
        idx = norm_rel.find(marker)
        if idx >= 0:
            tail = norm_rel[idx + len(marker):]
            candidate = _resolve_dir(tail, script_dir)
            if candidate:
                return candidate

    if str(project_id or "").strip() == "task_dashboard":
        candidate = script_dir / "任务规划"
        if candidate.exists() and candidate.is_dir():
            return candidate
    return None


def _reveal_allowed_roots() -> list[Path]:
    """Allowed roots for Finder reveal (workspace + configured project roots)."""
    repo_root = _repo_root()
    roots: list[Path] = []
    seen: set[str] = set()

    def _add_root(p: Optional[Path]) -> None:
        if not p:
            return
        try:
            rp = p.resolve()
        except Exception:
            return
        key = str(rp)
        if key in seen:
            return
        seen.add(key)
        roots.append(rp)

    _add_root(repo_root)
    cfg = _load_dashboard_cfg_current()
    projects = cfg.get("projects")
    if isinstance(projects, list):
        for p in projects:
            if not isinstance(p, dict):
                continue
            project_root_rel = str(p.get("project_root_rel") or "").strip()
            task_root_rel = str(p.get("task_root_rel") or "").strip()
            _add_root(_resolve_dir(project_root_rel, repo_root))
            _add_root(_resolve_dir(task_root_rel, repo_root))
    for extra_root in _extra_allowed_fs_roots():
        _add_root(extra_root)
    return roots


_TEXT_PREVIEW_EXTS = {
    ".md", ".markdown", ".txt", ".log", ".json", ".jsonl", ".js", ".ts", ".tsx",
    ".jsx", ".css", ".scss", ".less", ".py", ".sh", ".zsh", ".toml", ".yaml", ".yml",
    ".ini", ".cfg", ".conf", ".html", ".htm", ".xml", ".csv", ".tsv", ".sql",
    ".java", ".go", ".rs", ".c", ".cc", ".cpp", ".h", ".hpp", ".rb", ".php",
}
_FS_PREVIEW_MAX_BYTES = 120_000
_FS_PREVIEW_DIR_LIMIT = 80


def _truthy_flag(raw: Any) -> bool:
    if isinstance(raw, bool):
        return raw
    return str(raw or "").strip().lower() in {"1", "true", "yes", "on"}


def _fs_access_cfg() -> dict[str, Any]:
    cfg = _load_dashboard_cfg_current()
    raw = cfg.get("fs_access")
    return raw if isinstance(raw, dict) else {}


def _extra_allowed_fs_roots() -> list[Path]:
    repo_root = _repo_root()
    roots: list[Path] = []
    seen: set[str] = set()

    def _add_spec(raw: Any) -> None:
        spec = _safe_text(raw, 4000).strip()
        if not spec:
            return
        try:
            candidate = Path(spec).expanduser()
            resolved = candidate.resolve() if candidate.is_absolute() else (repo_root / candidate).resolve()
        except Exception:
            return
        if not resolved.exists():
            return
        key = str(resolved)
        if key in seen:
            return
        seen.add(key)
        roots.append(resolved)

    env_raw = str(os.environ.get("TASK_DASHBOARD_EXTRA_FS_ROOTS") or "").strip()
    if env_raw:
        for part in env_raw.split(os.pathsep):
            _add_spec(part)

    cfg_roots = _fs_access_cfg().get("extra_allowed_roots")
    if isinstance(cfg_roots, (list, tuple)):
        for item in cfg_roots:
            _add_spec(item)
    elif isinstance(cfg_roots, str):
        for item in cfg_roots.splitlines():
            _add_spec(item)

    return roots


def _repair_project_prefixed_path(path: Path) -> Path:
    try:
        parts = path.parts
    except Exception:
        return path
    if not parts:
        return path
    for idx in range(1, len(parts)):
        parent_name = parts[idx - 1]
        name = parts[idx]
        managed_workspace_name = "项目管理" + "-小秘书"
        if parent_name != managed_workspace_name:
            continue
        if not name or name.startswith("【项目】"):
            continue
        try:
            candidate = Path(*parts[:idx]) / f"【项目】{name}"
            for tail in parts[idx + 1:]:
                candidate /= tail
            if candidate.exists():
                return candidate.resolve()
        except Exception:
            continue
    return path


def _resolve_allowed_fs_path(path_raw: str) -> Path:
    p_raw = _safe_text(path_raw, 4000).strip()
    if not p_raw:
        raise ValueError("missing path")
    ws_root = _repo_root().resolve()
    p = Path(p_raw).expanduser()
    if p.is_absolute():
        pr = p.resolve()
    else:
        dashboard_root = Path(__file__).resolve().parent
        candidate_dashboard = (dashboard_root / p).resolve()
        candidate_workspace = (ws_root / p).resolve()
        pr = candidate_dashboard if candidate_dashboard.exists() else candidate_workspace
    if not pr.exists():
        repaired = _repair_project_prefixed_path(pr)
        if repaired.exists():
            pr = repaired
        else:
            raise FileNotFoundError("path not found")
    return pr


def _relative_path_to_repo_root(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(_repo_root().resolve()))
    except Exception:
        return ""


def _is_text_preview_path(path: Path, mime_type: str) -> bool:
    suffix = str(path.suffix or "").lower()
    if suffix in _TEXT_PREVIEW_EXTS:
        return True
    mime = str(mime_type or "").lower()
    return mime.startswith("text/") or mime in {
        "application/json",
        "application/xml",
        "application/javascript",
        "image/svg+xml",
    }


def _preview_mode_for_path(path: Path) -> str:
    suffix = str(path.suffix or "").lower()
    if suffix in {".md", ".markdown"}:
        return "markdown"
    if suffix in {".json", ".jsonl"}:
        return "json"
    if suffix in {".html", ".htm"}:
        return "html"
    if suffix in {".js", ".ts", ".tsx", ".jsx", ".css", ".scss", ".less", ".py", ".sh", ".zsh", ".toml", ".yaml", ".yml", ".sql", ".java", ".go", ".rs", ".c", ".cc", ".cpp", ".h", ".hpp"}:
        return "code"
    return "text"


def _read_text_preview(path: Path, max_bytes: int = _FS_PREVIEW_MAX_BYTES) -> tuple[str, bool]:
    with path.open("rb") as fh:
        raw = fh.read(max_bytes + 1)
    truncated = len(raw) > max_bytes
    if truncated:
        raw = raw[:max_bytes]
    text = raw.decode("utf-8", errors="replace")
    return text, truncated


class RunScheduler:
    """
    Enforce:
    - per session: strictly serial
    - global: bounded by executor max_workers
    """

    def __init__(
        self,
        store: "RunStore",
        max_concurrency: int = 8,
        busy_probe_delay_s: float = 1.2,
        busy_timeout_s: Optional[float] = None,
    ) -> None:
        self.store = store
        self.max_concurrency = max(1, int(max_concurrency or 1))
        self._executor = ThreadPoolExecutor(max_workers=self.max_concurrency)
        self._lock = threading.Lock()
        self._q: dict[str, deque[tuple[str, str]]] = {}
        self._running: dict[str, str] = {}
        self._retry_waiting: dict[str, tuple[str, float, str]] = {}
        self._retry_timers: dict[str, threading.Timer] = {}
        self._busy_probe_delay_s = max(0.2, float(busy_probe_delay_s or 0.2))
        busy_default = _default_session_busy_timeout_s() if busy_timeout_s is None else busy_timeout_s
        self._busy_timeout_s = max(0.0, float(busy_default or 0.0))
        self._busy_probe_timers: dict[str, threading.Timer] = {}

    def _schedule_busy_probe_locked(self, session_id: str) -> None:
        sid = str(session_id or "").strip()
        if not sid:
            return
        prev = self._busy_probe_timers.get(sid)
        if prev and prev.is_alive():
            return

        def _kick() -> None:
            with self._lock:
                self._busy_probe_timers.pop(sid, None)
                self._heal_stale_running_locked(sid)
                self._try_dispatch_locked(sid)

        timer = threading.Timer(self._busy_probe_delay_s, _kick)
        timer.daemon = True
        self._busy_probe_timers[sid] = timer
        timer.start()

    def enqueue(
        self,
        run_id: str,
        session_id: str,
        cli_type: str = "codex",
        *,
        priority: str = "normal",
    ) -> None:
        sid = str(session_id or "").strip()
        rid = str(run_id or "").strip()
        cli_t = str(cli_type or "codex").strip() or "codex"
        pr = str(priority or "normal").strip().lower()
        if not sid or not rid:
            return
        with self._lock:
            self._heal_stale_running_locked(sid)
            q = self._q.get(sid)
            if q is None:
                q = deque()
                self._q[sid] = q
            if pr in {"urgent", "high", "priority"}:
                q.appendleft((rid, cli_t))
            else:
                q.append((rid, cli_t))
            self._try_dispatch_locked(sid)

    def _schedule_retry_waiting_locked(self, run_id: str, session_id: str, due_ts: float, cli_type: str) -> threading.Timer:
        sid = str(session_id or "").strip()
        rid = str(run_id or "").strip()
        cli_t = str(cli_type or "codex").strip() or "codex"
        delay = max(0.0, float(due_ts or 0.0) - time.time())
        timer = threading.Timer(delay, self._activate_retry_waiting, args=(sid, rid, cli_t))
        timer.daemon = True
        prev = self._retry_timers.pop(rid, None)
        if prev:
            try:
                prev.cancel()
            except Exception:
                pass
        self._retry_waiting[sid] = (rid, float(due_ts or 0.0), cli_t)
        self._retry_timers[rid] = timer
        return timer

    def _enqueue_pending_retry_locked(self, session_id: str, run_id: str, cli_type: str) -> None:
        sid = str(session_id or "").strip()
        rid = str(run_id or "").strip()
        cli_t = str(cli_type or "codex").strip() or "codex"
        if not sid or not rid:
            return
        q = self._q.get(sid)
        if q is None:
            q = deque()
            self._q[sid] = q
        existing = [item for item in q]
        for item in existing:
            irid = str(item[0] if isinstance(item, tuple) else item).strip()
            if irid == rid:
                return
        insert_at = 0
        for idx, item in enumerate(existing):
            qrid = str(item[0] if isinstance(item, tuple) else item).strip()
            if not qrid:
                break
            try:
                qmeta = self.store.load_meta(qrid) if hasattr(self.store, "load_meta") else None
            except Exception:
                qmeta = None
            qstatus = str((qmeta or {}).get("status") or "").strip().lower()
            if qstatus == "retry_waiting":
                insert_at = idx + 1
                continue
            break
        existing.insert(insert_at, (rid, cli_t))
        self._q[sid] = deque(existing)

    def schedule_retry_waiting(self, run_id: str, session_id: str, due_ts: float, cli_type: str = "codex") -> bool:
        sid = str(session_id or "").strip()
        rid = str(run_id or "").strip()
        cli_t = str(cli_type or "codex").strip() or "codex"
        if not sid or not rid:
            return False
        timer: Optional[threading.Timer] = None
        with self._lock:
            cur = self._retry_waiting.get(sid)
            if (cur and str(cur[0] or "").strip() != rid) or sid in self._running or bool(self._q.get(sid)):
                self._enqueue_pending_retry_locked(sid, rid, cli_t)
                self._try_dispatch_locked(sid)
            else:
                timer = self._schedule_retry_waiting_locked(rid, sid, due_ts, cli_t)
        if timer:
            timer.start()
        return True

    def cancel_retry_waiting(self, run_id: str, session_id: str = "") -> bool:
        rid = str(run_id or "").strip()
        sid_hint = str(session_id or "").strip()
        if not rid:
            return False
        removed = False
        with self._lock:
            targets = [sid_hint] if sid_hint else list(self._retry_waiting.keys())
            for sid in targets:
                item = self._retry_waiting.get(sid)
                if not item:
                    continue
                wrid = str(item[0] or "").strip()
                if wrid != rid:
                    continue
                self._retry_waiting.pop(sid, None)
                t = self._retry_timers.pop(rid, None)
                if t:
                    try:
                        t.cancel()
                    except Exception:
                        pass
                removed = True
                self._try_dispatch_locked(sid)
                break

            for sid in ([sid_hint] if sid_hint else list(self._q.keys())):
                q = self._q.get(sid)
                if not q:
                    continue
                new_q: deque[tuple[str, str]] = deque()
                removed_here = False
                for item in q:
                    irid = str(item[0] if isinstance(item, tuple) else item).strip()
                    if irid == rid:
                        removed_here = True
                        continue
                    if isinstance(item, tuple):
                        new_q.append((str(item[0]), str(item[1] or "codex")))
                    else:
                        new_q.append((str(item), "codex"))
                if removed_here:
                    removed = True
                    if new_q:
                        self._q[sid] = new_q
                    else:
                        self._q.pop(sid, None)
                    self._try_dispatch_locked(sid)
                    break
        return removed

    def kick_session(self, session_id: str) -> None:
        sid = str(session_id or "").strip()
        if not sid:
            return
        with self._lock:
            self._heal_stale_running_locked(sid)
            self._try_dispatch_locked(sid)

    def cancel_queued_run(self, run_id: str, session_id: str = "") -> bool:
        """Best-effort remove a queued run before dispatch."""
        rid = str(run_id or "").strip()
        sid = str(session_id or "").strip()
        if not rid:
            return False
        with self._lock:
            targets = [sid] if sid else list(self._q.keys())
            for s in targets:
                q = self._q.get(s)
                if not q:
                    continue
                new_q: deque[tuple[str, str]] = deque()
                removed = False
                for item in q:
                    irid = str(item[0] if isinstance(item, tuple) else item).strip()
                    if irid == rid:
                        removed = True
                        continue
                    if isinstance(item, tuple):
                        new_q.append((str(item[0]), str(item[1] or "codex")))
                    else:
                        new_q.append((str(item), "codex"))
                if removed:
                    if new_q:
                        self._q[s] = new_q
                    else:
                        self._q.pop(s, None)
                    return True
        return False

    def _activate_retry_waiting(self, session_id: str, run_id: str, cli_type: str) -> None:
        sid = str(session_id or "").strip()
        rid = str(run_id or "").strip()
        cli_t = str(cli_type or "codex").strip() or "codex"
        if not sid or not rid:
            return
        with self._lock:
            cur = self._retry_waiting.get(sid)
            if not cur or str(cur[0] or "").strip() != rid:
                self._retry_timers.pop(rid, None)
                return
            self._retry_waiting.pop(sid, None)
            self._retry_timers.pop(rid, None)

            try:
                meta = self.store.load_meta(rid) if hasattr(self.store, "load_meta") else None
            except Exception:
                meta = None
            if not meta:
                self._try_dispatch_locked(sid)
                return
            if bool(meta.get("hidden")):
                self._try_dispatch_locked(sid)
                return
            st = str(meta.get("status") or "").strip().lower()
            if st != "retry_waiting":
                self._try_dispatch_locked(sid)
                return

            meta["status"] = "queued"
            meta["retryActivatedAt"] = _now_iso()
            try:
                self.store.save_meta(rid, meta)
            except Exception:
                pass

            q = self._q.get(sid)
            if q is None:
                q = deque()
                self._q[sid] = q
            # 置于队首，确保“自动续连消息”先于后续同会话消息执行。
            q.appendleft((rid, cli_t))
            self._try_dispatch_locked(sid)

    def _heal_stale_running_locked(self, session_id: str) -> None:
        sid = str(session_id or "").strip()
        if not sid:
            return
        if not hasattr(self.store, "load_meta"):
            return
        rid = str(self._running.get(sid) or "").strip()
        if not rid:
            return
        try:
            meta = self.store.load_meta(rid)
        except Exception:
            meta = None
        if not meta:
            # Missing/corrupted meta for a claimed running slot is stale.
            # Release it so later runs in the same session can continue.
            self._running.pop(sid, None)
            return
        st = str(meta.get("status") or "").strip().lower()
        if st == "running":
            return
        self._running.pop(sid, None)

    def _try_dispatch_locked(self, session_id: str) -> None:
        self._heal_stale_running_locked(session_id)
        if session_id in self._running:
            return
        if session_id in self._retry_waiting:
            return
        q = self._q.get(session_id)
        if not q:
            return
        run_id = ""
        cli_type = "codex"
        while q:
            item = q.popleft()
            if isinstance(item, tuple):
                run_id, cli_type = item
            else:
                run_id, cli_type = item, "codex"
            run_id = str(run_id or "").strip()
            cli_type = str(cli_type or "codex").strip() or "codex"
            if not run_id:
                continue
            try:
                meta = self.store.load_meta(run_id) if hasattr(self.store, "load_meta") else None
            except Exception:
                meta = None
            if meta is None:
                break
            if bool(meta.get("hidden")):
                continue
            st = str(meta.get("status") or "").strip().lower()
            if st == "queued":
                break
            if st == "retry_waiting":
                due_ts = _parse_iso_ts(meta.get("retryScheduledAt")) or time.time() + max(1, _default_network_resume_delay_s())
                timer = self._schedule_retry_waiting_locked(run_id, session_id, due_ts, cli_type)
                timer.start()
                if not q:
                    self._q.pop(session_id, None)
                return
            # stale queue item, skip
            run_id = ""
            continue
        if not run_id:
            if not q:
                self._q.pop(session_id, None)
            return
        if _session_process_busy_effective(self.store, session_id, cli_type=cli_type):
            busy_timed_out = False
            if meta is not None and hasattr(self.store, "save_meta"):
                changed = False
                if str(meta.get("status") or "").strip().lower() != "queued":
                    meta["status"] = "queued"
                    changed = True
                queue_reason = str(meta.get("queueReason") or "").strip().lower()
                if queue_reason != "session_busy_external":
                    meta["queueReason"] = "session_busy_external"
                    meta["queueReasonAt"] = _now_iso()
                    changed = True
                else:
                    queue_at = _parse_iso_ts(meta.get("queueReasonAt"))
                    if queue_at <= 0:
                        meta["queueReasonAt"] = _now_iso()
                        changed = True
                        queue_at = _parse_iso_ts(meta.get("queueReasonAt"))
                    if self._busy_timeout_s > 0 and queue_at > 0 and (time.time() - queue_at) >= self._busy_timeout_s:
                        busy_timed_out = True
                        meta["status"] = "error"
                        meta["errorType"] = "session_busy_timeout"
                        meta["error"] = f"timeout>session_busy_external>{int(self._busy_timeout_s)}s"
                        meta["queueReason"] = "session_busy_timeout"
                        meta["queueTimeoutAt"] = _now_iso()
                        changed = True
                if changed:
                    try:
                        self.store.save_meta(run_id, meta)
                    except Exception:
                        pass
            if busy_timed_out:
                if not q:
                    self._q.pop(session_id, None)
                self._try_dispatch_locked(session_id)
                return
            q.appendleft((run_id, cli_type))
            self._schedule_busy_probe_locked(session_id)
            return
        if meta is not None and hasattr(self.store, "save_meta"):
            changed = False
            if "queueReason" in meta:
                meta.pop("queueReason", None)
                changed = True
            if "queueReasonAt" in meta:
                meta.pop("queueReasonAt", None)
                changed = True
            if changed:
                try:
                    self.store.save_meta(run_id, meta)
                except Exception:
                    pass
        if not q:
            self._q.pop(session_id, None)
        self._running[session_id] = run_id

        def _runner() -> None:
            try:
                run_cli_exec(self.store, run_id, cli_type=cli_type, scheduler=self)
            finally:
                with self._lock:
                    cur = str(self._running.get(session_id) or "").strip()
                    if cur == run_id:
                        self._running.pop(session_id, None)
                    self._try_dispatch_locked(session_id)

        self._executor.submit(_runner)


class RunProcessRegistry:
    """Track active run processes for interrupt support."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._procs: dict[str, subprocess.Popen[Any]] = {}
        self._interrupted: set[str] = set()

    def register(self, run_id: str, proc: subprocess.Popen[Any]) -> None:
        rid = str(run_id or "").strip()
        if not rid:
            return
        with self._lock:
            self._procs[rid] = proc

    def unregister(self, run_id: str) -> None:
        rid = str(run_id or "").strip()
        if not rid:
            return
        with self._lock:
            self._procs.pop(rid, None)

    def is_tracked(self, run_id: str) -> bool:
        rid = str(run_id or "").strip()
        if not rid:
            return False
        with self._lock:
            return rid in self._procs

    def request_interrupt(self, run_id: str, cli_type: str = "codex") -> bool:
        rid = str(run_id or "").strip()
        if not rid:
            return False
        with self._lock:
            proc = self._procs.get(rid)
            if proc is None or proc.poll() is not None:
                fallback_ok = _interrupt_run_process_by_scan(rid, cli_type=cli_type)
                if fallback_ok:
                    self._interrupted.add(rid)
                return fallback_ok
            self._interrupted.add(rid)
        try:
            proc.terminate()
            time.sleep(0.25)
            if proc.poll() is None:
                proc.kill()
            return True
        except Exception:
            with self._lock:
                self._interrupted.discard(rid)
            return False

    def consume_interrupted(self, run_id: str) -> bool:
        rid = str(run_id or "").strip()
        if not rid:
            return False
        with self._lock:
            if rid in self._interrupted:
                self._interrupted.discard(rid)
                return True
        return False


RUN_PROCESS_REGISTRY = RunProcessRegistry()


def _codex_home() -> Path:
    """Legacy function for backward compatibility. Use CodexAdapter.get_home_path() instead."""
    return CodexAdapter.get_home_path()


def _extract_uuid_from_name(name: str) -> str:
    """Legacy function for backward compatibility. Use CLIAdapter.extract_session_id_from_name() instead."""
    return CodexAdapter.extract_session_id_from_name(name)


def _find_new_session_id(
    start_ts: float,
    cli_type: str = "codex",
    exclude_session_ids: Optional[set[str]] = None,
) -> tuple[str, str]:
    """
    Find the most recently created session after start_ts for the given CLI type.

    Args:
        start_ts: Unix timestamp to search after.
        cli_type: The CLI type to search for (default: "codex").
        exclude_session_ids: Optional set of known-existing session ids.
            When provided, only sessions not in this set are eligible.

    Returns:
        Tuple of (session_id, session_path) or ("", "") if not found.
    """
    adapter_cls = get_adapter(cli_type) or CodexAdapter
    sessions = adapter_cls.scan_sessions(after_ts=start_ts)
    if not sessions:
        return "", ""
    blocked = {
        str(sid or "").strip().lower()
        for sid in (exclude_session_ids or set())
        if str(sid or "").strip()
    }
    for info in sessions:
        sid = str(getattr(info, "session_id", "") or "").strip()
        if not sid:
            continue
        if blocked and sid.lower() in blocked:
            continue
        return sid, str(getattr(info, "path", "") or "")
    return "", ""


def create_codex_session(seed_prompt: str, timeout_s: int = 90) -> dict[str, Any]:
    """
    Create a new Codex session by running a minimal `codex exec` turn (read-only sandbox)
    and then discovering the new session id from CODEX_HOME session files.

    This is kept for backward compatibility. Use create_cli_session() for new code.
    """
    return create_cli_session(seed_prompt=seed_prompt, timeout_s=timeout_s, cli_type="codex")


def create_cli_session(
    seed_prompt: str,
    timeout_s: int = 90,
    cli_type: str = "codex",
    workdir: Optional[Path] = None,
    model: str = "",
    reasoning_effort: str = "",
    execution_profile: str = "",
) -> dict[str, Any]:
    """
    Create a new CLI session by running a minimal command
    and then discovering the new session id from the CLI's session files.

    Args:
        seed_prompt: Initial prompt for the session.
        timeout_s: Timeout in seconds.
        cli_type: The CLI type to use (codex, claude, opencode, gemini, trae).
        model: Optional model identifier, used when CLI adapter supports it.
        reasoning_effort: Optional reasoning effort for supported CLI.
        execution_profile: Optional dashboard execution profile used for spawn behavior.

    Returns:
        Dict with ok, sessionId, sessionPath, and optional error info.
    """
    adapter_cls = get_adapter_or_error(cli_type)
    normalized_execution_profile = runtime_normalize_execution_profile(execution_profile, allow_empty=True)
    codex_sandbox_mode = "read-only" if normalized_execution_profile in {"", "sandboxed"} else ""

    start_ts = time.time()
    existing_session_ids: set[str] = set()
    try:
        for row in adapter_cls.scan_sessions(after_ts=0.0):
            sid = str(getattr(row, "session_id", "") or "").strip().lower()
            if sid:
                existing_session_ids.add(sid)
    except Exception:
        existing_session_ids = set()
    # Create temp directory for output
    cli_home = adapter_cls.get_home_path()
    tmp_dir = cli_home / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    last_path = tmp_dir / f"task-dashboard-new-session-{int(start_ts)}.last.txt"

    cmd = adapter_cls.build_create_command(
        seed_prompt=seed_prompt or "请回复 OK。",
        output_path=last_path,
        model=(str(model or "").strip() if adapter_cls.supports_model() else ""),
        reasoning_effort=(_normalize_reasoning_effort(reasoning_effort) if cli_type == "codex" else ""),
        sandbox_mode=(codex_sandbox_mode if cli_type == "codex" else ""),
    )

    run_cwd = workdir if (workdir and workdir.exists() and workdir.is_dir()) else Path(__file__).resolve().parent
    spawn_bundle = runtime_prepare_process_spawn(
        cli_type=cli_type,
        requested_cwd=run_cwd,
        cmd=cmd,
        execution_profile=normalized_execution_profile or "sandboxed",
    )
    spawn_cmd = list(spawn_bundle.get("cmd") or cmd)
    spawn_cwd = Path(spawn_bundle.get("spawn_cwd") or run_cwd)
    spawn_env = dict(spawn_bundle.get("spawn_env") or os.environ)

    try:
        proc = subprocess.run(
            spawn_cmd,
            capture_output=True,
            text=True,
            timeout=max(10, int(timeout_s)),
            cwd=str(spawn_cwd),
            env=spawn_env,
        )
    except subprocess.TimeoutExpired as e:
        sid, spath = _find_new_session_id(
            start_ts,
            cli_type,
            exclude_session_ids=existing_session_ids,
        )
        combined_output = "\n".join(
            str(part or "")
            for part in [getattr(e, "stdout", "") or "", getattr(e, "stderr", "") or ""]
            if part
        )
        if not sid:
            try:
                extractor = getattr(adapter_cls, "extract_session_id_from_output", None)
                if callable(extractor):
                    extracted_sid = str(extractor(combined_output) or "").strip()
                    if extracted_sid and extracted_sid.lower() not in existing_session_ids:
                        sid = extracted_sid
            except Exception:
                sid = ""
        if sid and not spath:
            try:
                for info in adapter_cls.scan_sessions(after_ts=start_ts):
                    candidate_sid = str(getattr(info, "session_id", "") or "").strip()
                    if candidate_sid and candidate_sid.lower() == sid.lower():
                        spath = str(getattr(info, "path", "") or "")
                        break
            except Exception:
                spath = ""
        return {
            "ok": False,
            "error": "timeout",
            "sessionId": sid,
            "sessionPath": spath,
            "cliType": cli_type,
            "stderr": _safe_text(getattr(e, "stderr", "") or "", 6000),
            "workdir": str(run_cwd),
            "spawn_cwd": str(spawn_cwd),
            "execution_profile": normalized_execution_profile or "sandboxed",
        }
    except Exception as e:
        return {
            "ok": False,
            "error": f"spawn failed: {e}",
            "cliType": cli_type,
            "workdir": str(run_cwd),
            "spawn_cwd": str(spawn_cwd),
            "execution_profile": normalized_execution_profile or "sandboxed",
        }

    sid, spath = _find_new_session_id(
        start_ts,
        cli_type,
        exclude_session_ids=existing_session_ids,
    )
    if not sid and proc.returncode == 0:
        combined_output = "\n".join(part for part in [proc.stdout, proc.stderr] if part)
        try:
            extractor = getattr(adapter_cls, "extract_session_id_from_output", None)
            if callable(extractor):
                sid = str(extractor(combined_output) or "").strip().lower()
                if sid in existing_session_ids:
                    sid = ""
        except Exception:
            sid = ""
    if proc.returncode != 0:
        err = (proc.stderr or "").strip() or (proc.stdout or "").strip()
        return {
            "ok": False,
            "error": f"{cli_type} exec failed",
            "code": proc.returncode,
            "sessionId": sid,
            "sessionPath": spath,
            "cliType": cli_type,
            "stderr": _safe_text(err, 6000),
            "workdir": str(run_cwd),
            "spawn_cwd": str(spawn_cwd),
            "execution_profile": normalized_execution_profile or "sandboxed",
        }
    if not sid:
        # No file observed; still return last output for debugging.
        return {
            "ok": False,
            "error": "sessionId not detected",
            "sessionId": "",
            "sessionPath": spath,
            "cliType": cli_type,
            "stdout": _safe_text((proc.stdout or "").strip(), 4000),
            "stderr": _safe_text((proc.stderr or "").strip(), 4000),
            "workdir": str(run_cwd),
            "spawn_cwd": str(spawn_cwd),
            "execution_profile": normalized_execution_profile or "sandboxed",
        }
    return {
        "ok": True,
        "sessionId": sid,
        "sessionPath": spath,
        "cliType": cli_type,
        "workdir": str(run_cwd),
        "spawn_cwd": str(spawn_cwd),
        "execution_profile": normalized_execution_profile or "sandboxed",
    }


def _build_session_seed_prompt(
    project_id: str = "",
    channel_name: str = "",
    note: str = "",
    first_message: str = "",
) -> str:
    """
    Build the first prompt for new session creation.

    If `first_message` is provided, use it directly so callers can control
    the Codex Desktop thread title. Otherwise use the default seed with
    dynamic connectivity acceptance text (channel + dialog type).
    """
    custom = str(first_message or "").strip()
    if custom:
        return custom

    seed = "[task-dashboard] new session"
    pid = str(project_id or "").strip()
    cname = str(channel_name or "").strip()
    memo = str(note or "").strip()
    if pid or cname:
        seed += f" · {pid} · {cname}"
    if memo:
        seed += f" · {memo}"
    channel_for_accept = cname or "未命名通道"
    is_master_dialog = "主体-总控" in channel_for_accept
    dialog_type = "主对话" if is_master_dialog else "子级对话"
    dialog_short = "主" if is_master_dialog else "子级"
    accept_line = (
        f"【连通性验收】通道：{channel_for_accept}；对话类型：{dialog_type}。"
        f"请仅回复：OK（{channel_for_accept}-{dialog_short}）"
    )
    return seed + "\n\n" + accept_line


def _is_profile_not_found(err: str) -> bool:
    txt = str(err or "").lower()
    return "config profile" in txt and "not found" in txt


_PROFILE_NOT_FOUND_CACHE: dict[str, float] = {}
_PROFILE_NOT_FOUND_CACHE_LOCK = threading.Lock()


def _profile_not_found_cache_key(cli_type: str, profile_label: str) -> str:
    return (str(cli_type or "codex").strip().lower() + "::" + str(profile_label or "").strip().lower())


def _profile_not_found_recent(cli_type: str, profile_label: str) -> tuple[bool, float]:
    label = str(profile_label or "").strip()
    ttl = _default_profile_not_found_suppress_s()
    if not label or ttl <= 0:
        return False, 0.0
    key = _profile_not_found_cache_key(cli_type, label)
    now = time.time()
    with _PROFILE_NOT_FOUND_CACHE_LOCK:
        ts = float(_PROFILE_NOT_FOUND_CACHE.get(key) or 0.0)
        if ts <= 0:
            return False, 0.0
        elapsed = now - ts
        if elapsed < ttl:
            return True, max(0.0, (ts + ttl) - now)
        _PROFILE_NOT_FOUND_CACHE.pop(key, None)
    return False, 0.0


def _record_profile_not_found(cli_type: str, profile_label: str) -> None:
    label = str(profile_label or "").strip()
    if not label:
        return
    key = _profile_not_found_cache_key(cli_type, label)
    with _PROFILE_NOT_FOUND_CACHE_LOCK:
        _PROFILE_NOT_FOUND_CACHE[key] = time.time()


class RunStore:
    def __init__(self, runs_dir: Path) -> None:
        self.runs_dir = runs_dir
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.hot_dir = self.runs_dir / "hot"
        self.archive_dir = self.runs_dir / "archive"
        self.hot_dir.mkdir(parents=True, exist_ok=True)
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        self._live_run_index_lock = threading.Lock()
        self._live_run_index_ready = False
        self._live_run_index_by_id: dict[str, dict[str, Any]] = {}
        self._live_run_index_order: list[str] = []

    def _legacy_paths(self, run_id: str) -> dict[str, Path]:
        base = self.runs_dir / run_id
        return {
            "meta": base.with_suffix(".json"),
            "msg": base.with_suffix(".msg.txt"),
            "last": base.with_suffix(".last.txt"),
            "log": base.with_suffix(".log.txt"),
        }

    def _hot_paths(self, run_id: str) -> dict[str, Path]:
        base = self.hot_dir / run_id
        return {
            "meta": base.with_suffix(".json"),
            "msg": base.with_suffix(".msg.txt"),
            "last": base.with_suffix(".last.txt"),
            "log": base.with_suffix(".log.txt"),
        }

    def _should_mirror_legacy_meta(self, run_id: str, meta: dict[str, Any]) -> bool:
        trigger_type = str(meta.get("trigger_type") or "").strip().lower()
        if trigger_type.startswith("callback_auto"):
            return True
        return self._legacy_paths(run_id)["meta"].exists()

    def _mirror_legacy_meta(self, run_id: str, meta_text: str, meta: dict[str, Any]) -> None:
        if not self._should_mirror_legacy_meta(run_id, meta):
            return
        legacy_meta = self._legacy_paths(run_id)["meta"]
        _atomic_write_text(legacy_meta, meta_text)

    def _archive_paths(self, run_id: str, bucket: str) -> dict[str, Path]:
        base = self.archive_dir / bucket / run_id
        return {
            "meta": base.with_suffix(".json"),
            "msg": base.with_suffix(".msg.txt"),
            "last": base.with_suffix(".last.txt"),
            "log": base.with_suffix(".log.txt"),
        }

    def _archive_bucket_for_meta(self, meta: dict[str, Any]) -> str:
        for key in ("finishedAt", "createdAt", "startedAt"):
            raw = str(meta.get(key) or "").strip()
            if len(raw) >= 7 and raw[4] == "-" and raw[7] in {"-", "T"}:
                return raw[:7]
        return time.strftime("%Y-%m", time.localtime())

    def _iter_live_meta_paths(self) -> list[Path]:
        paths: list[Path] = []
        seen: set[str] = set()
        for root in (self.hot_dir, self.runs_dir):
            for path in root.glob("*.json"):
                name = path.name
                if name in seen:
                    continue
                seen.add(name)
                paths.append(path)
        return paths

    def _build_live_run_index(self) -> tuple[dict[str, dict[str, Any]], list[str]]:
        by_id: dict[str, dict[str, Any]] = {}
        ordered_ids: list[str] = []
        for path in sorted(self._iter_live_meta_paths(), key=lambda x: x.stat().st_mtime, reverse=True):
            try:
                meta = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(meta, dict):
                continue
            run_id = str(meta.get("id") or "").strip()
            if not run_id or run_id in by_id:
                continue
            by_id[run_id] = dict(meta)
            ordered_ids.append(run_id)
        return by_id, ordered_ids

    def _ensure_live_run_index_ready(self) -> None:
        with self._live_run_index_lock:
            if self._live_run_index_ready:
                return
        by_id, ordered_ids = self._build_live_run_index()
        with self._live_run_index_lock:
            if self._live_run_index_ready:
                return
            self._live_run_index_by_id = by_id
            self._live_run_index_order = ordered_ids
            self._live_run_index_ready = True

    def _snapshot_live_run_index(self) -> list[dict[str, Any]]:
        self._ensure_live_run_index_ready()
        with self._live_run_index_lock:
            return [
                dict(meta)
                for run_id in self._live_run_index_order
                for meta in [self._live_run_index_by_id.get(run_id) or {}]
                if meta
            ]

    def _update_live_run_index_entry(self, run_id: str, meta: dict[str, Any]) -> None:
        if not run_id:
            return
        with self._live_run_index_lock:
            if not self._live_run_index_ready:
                return
            self._live_run_index_by_id[run_id] = dict(meta)
            try:
                self._live_run_index_order.remove(run_id)
            except ValueError:
                pass
            self._live_run_index_order.insert(0, run_id)

    def _remove_live_run_index_entry(self, run_id: str) -> None:
        if not run_id:
            return
        with self._live_run_index_lock:
            if not self._live_run_index_ready:
                return
            self._live_run_index_by_id.pop(run_id, None)
            try:
                self._live_run_index_order.remove(run_id)
            except ValueError:
                pass

    def _find_meta_path(self, run_id: str) -> Optional[Path]:
        hot = self._hot_paths(run_id)["meta"]
        if hot.exists():
            return hot
        legacy = self._legacy_paths(run_id)["meta"]
        if legacy.exists():
            return legacy
        pattern = f"*/{run_id}.json"
        matches = sorted(self.archive_dir.glob(pattern), reverse=True)
        if matches:
            return matches[0]
        return None

    def _paths(self, run_id: str) -> dict[str, Path]:
        meta_path = self._find_meta_path(run_id)
        if meta_path is not None:
            base = meta_path.with_suffix("")
            return {
                "meta": meta_path,
                "msg": base.with_suffix(".msg.txt"),
                "last": base.with_suffix(".last.txt"),
                "log": base.with_suffix(".log.txt"),
            }
        return self._hot_paths(run_id)

    def repair_legacy_hot_meta_consistency(self, *, limit: int = 200) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        sync_keys = (
            "status",
            "display_state",
            "queue_reason",
            "blocked_by_run_id",
            "queueReason",
            "blockedByRunId",
            "finishedAt",
            "error",
            "lastPreview",
        )
        for hot_meta_path in sorted(self.hot_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            run_id = hot_meta_path.stem
            legacy_meta_path = self._legacy_paths(run_id)["meta"]
            if not legacy_meta_path.exists():
                continue
            hot_meta = _read_json_file_safe(hot_meta_path)
            if not hot_meta:
                continue
            legacy_meta = _read_json_file_safe(legacy_meta_path)
            if all(hot_meta.get(key) == legacy_meta.get(key) for key in sync_keys):
                continue
            _atomic_write_text(
                legacy_meta_path,
                json.dumps(hot_meta, ensure_ascii=False, indent=2),
            )
            results.append({
                "run_id": run_id,
                "status": str(hot_meta.get("status") or "").strip(),
                "display_state": str(hot_meta.get("display_state") or "").strip(),
                "legacy_meta": str(legacy_meta_path),
            })
            if len(results) >= max(1, int(limit or 1)):
                break
        return results

    def create_run(
        self,
        project_id: str,
        channel_name: str,
        session_id: str,
        message: str,
        profile_label: str = "",
        model: str = "",
        cli_type: str = "codex",
        attachments: list[dict[str, Any]] | None = None,
        sender_type: str = "legacy",
        sender_id: str = "legacy",
        sender_name: str = "历史消息（来源未知）",
        extra_meta: dict[str, Any] | None = None,
        reasoning_effort: str = "",
    ) -> dict[str, Any]:
        run_id = time.strftime("%Y%m%d-%H%M%S", time.localtime()) + "-" + secrets.token_hex(4)
        p = self._paths(run_id)
        cid = _channel_id(project_id, channel_name)

        # Handle attachments - copy to run-specific directory
        saved_attachments: list[dict[str, Any]] = []
        if attachments:
            import shutil
            attach_dir = self.runs_dir / run_id / "attachments"
            attach_dir.mkdir(parents=True, exist_ok=True)
            for att in attachments:
                # Check if we have a path to copy from, or just use the URL directly
                src_path = att.get("path", "")
                url = att.get("url", "")
                filename = att.get("filename", "unknown")
                original_name = att.get("originalName", filename)

                if src_path and Path(src_path).exists():
                    # Copy from provided path
                    dst_path = attach_dir / filename
                    try:
                        shutil.copy2(src_path, dst_path)
                        saved_attachments.append({
                            "filename": filename,
                            "originalName": original_name,
                            "url": f"/.runs/{run_id}/attachments/{filename}",
                            "path": str(dst_path),
                        })
                    except Exception:
                        pass  # Skip failed attachments
                elif url:
                    # Use the URL directly (image already uploaded to attachments folder)
                    # Just keep the attachment info with the original URL
                    saved_item = {
                        "filename": filename,
                        "originalName": original_name,
                        "url": url,
                    }
                    target = _resolve_runs_static_target(self.runs_dir, url)
                    if target is not None and target.exists():
                        saved_item["path"] = str(target)
                    saved_attachments.append(saved_item)

        resolved_model = str(model or "").strip() or _project_channel_model(project_id, channel_name)
        resolved_reasoning = _normalize_reasoning_effort(reasoning_effort) or _project_channel_reasoning_effort(project_id, channel_name)
        meta: dict[str, Any] = {
            "id": run_id,
            "channelId": cid,
            "projectId": project_id,
            "channelName": channel_name,
            "profileLabel": profile_label,
            "model": resolved_model,
            "reasoning_effort": resolved_reasoning,
            "sessionId": session_id,
            "cliType": cli_type or "codex",
            "status": "queued",  # queued|retry_waiting|running|done|error
            "createdAt": _now_iso(),
            "startedAt": "",
            "finishedAt": "",
            "error": "",
            "lastPreview": "",
            "sender_type": str(sender_type or "legacy").strip() or "legacy",
            "sender_id": str(sender_id or "legacy").strip() or "legacy",
            "sender_name": str(sender_name or "历史消息（来源未知）").strip() or "历史消息（来源未知）",
            "attachments": saved_attachments,
            "paths": {k: str(v) for k, v in p.items()},
        }
        meta.update(_sanitize_run_extra_meta(extra_meta))

        meta_text = json.dumps(meta, ensure_ascii=False, indent=2)
        _atomic_write_text(p["msg"], message)
        _atomic_write_text(p["meta"], meta_text)
        self._mirror_legacy_meta(run_id, meta_text, meta)
        self._update_live_run_index_entry(run_id, meta)
        try:
            _invalidate_project_session_runtime_index_cache(
                str(meta.get("projectId") or "").strip(),
                session_id=str(meta.get("sessionId") or "").strip(),
            )
        except Exception:
            pass
        try:
            runtime_invalidate_sessions_payload_cache(str(meta.get("projectId") or "").strip())
        except Exception:
            pass
        return meta

    def load_meta(self, run_id: str) -> Optional[dict[str, Any]]:
        p = self._paths(run_id)["meta"]
        if not p.exists():
            return None
        try:
            meta = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None
        try:
            meta2, changed = self.reconcile_meta(meta)
        except Exception:
            return meta
        if changed:
            try:
                self.save_meta(run_id, meta2)
            except Exception:
                pass
        return meta2

    def save_meta(self, run_id: str, meta: dict[str, Any]) -> None:
        p = self._paths(run_id)["meta"]
        try:
            existing = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        except Exception:
            existing = {}
        if isinstance(existing, dict):
            for key in (
                "restartRecoveryRunId",
                "restartRecoveryQueuedAt",
                "restartRecoverySender",
                "restartRecoveryBatchId",
            ):
                if not str(meta.get(key) or "").strip() and str(existing.get(key) or "").strip():
                    meta[key] = existing[key]
        meta_text = json.dumps(meta, ensure_ascii=False, indent=2)
        _atomic_write_text(p, meta_text)
        self._mirror_legacy_meta(run_id, meta_text, meta)
        self._update_live_run_index_entry(run_id, meta)
        try:
            _invalidate_project_session_runtime_index_cache(
                str(meta.get("projectId") or "").strip(),
                session_id=str(meta.get("sessionId") or "").strip(),
            )
        except Exception:
            pass
        try:
            runtime_invalidate_sessions_payload_cache(str(meta.get("projectId") or "").strip())
        except Exception:
            pass

    def read_msg(self, run_id: str, limit_chars: int = 50_000) -> str:
        p = self._paths(run_id)["msg"]
        if not p.exists():
            return ""
        return _safe_text(p.read_text(encoding="utf-8", errors="replace"), limit_chars)

    def write_msg(self, run_id: str, message: str) -> None:
        p = self._paths(run_id)["msg"]
        _atomic_write_text(p, str(message or ""))

    def append_msg(self, run_id: str, chunk: str) -> None:
        add = str(chunk or "")
        if not add:
            return
        p = self._paths(run_id)["msg"]
        prev = ""
        if p.exists():
            prev = p.read_text(encoding="utf-8", errors="replace")
        merged = f"{prev}{add}" if prev else add
        _atomic_write_text(p, merged)

    def read_last(self, run_id: str, limit_chars: int = 80_000) -> str:
        p = self._paths(run_id)["last"]
        if not p.exists():
            return ""
        return _safe_text(p.read_text(encoding="utf-8", errors="replace"), limit_chars)

    def read_log(self, run_id: str, limit_chars: int = 40_000) -> str:
        p = self._paths(run_id)["log"]
        return _safe_text(_tail_text(p, max_chars=limit_chars), limit_chars)

    def reconcile_meta(self, meta: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        def _sync_observability_fields() -> bool:
            changed_local = False
            try:
                # Reconcile runs on read/startup paths with lightweight observability only.
                # Cross-run session semantics are derived in response/runtime views and are
                # too expensive to recompute for every meta reconciliation.
                obs = _build_run_observability_fields(
                    self,
                    meta,
                    infer_blocked=False,
                    include_session_semantics=False,
                )
            except Exception:
                return False
            if str(meta.get("status") or "").strip() in {"done", "error"}:
                obs["queue_reason"] = ""
                obs["blocked_by_run_id"] = ""
            if bool(meta.get("hidden")):
                obs["display_state"] = "hidden"
            for key, value in obs.items():
                if meta.get(key) != value:
                    meta[key] = value
                    changed_local = True
            return changed_local

        st = str(meta.get("status") or "")
        run_id = str(meta.get("id") or "").strip()
        if st in {"done", "error"}:
            changed = False
            cli_type = str(meta.get("cliType") or "codex").strip() or "codex"
            if run_id and st == "done":
                terminal_error = _detect_terminal_text_cli_incomplete_error(
                    cli_type,
                    log_path=self._paths(run_id)["log"],
                )
                if terminal_error:
                    meta["status"] = "error"
                    if str(meta.get("error") or "").strip() != terminal_error:
                        meta["error"] = terminal_error
                    meta.pop("errorType", None)
                    st = "error"
                    changed = True
            if run_id and st == "error" and not str(meta.get("error") or "").strip():
                terminal_error = _detect_terminal_text_cli_incomplete_error(
                    cli_type,
                    log_path=self._paths(run_id)["log"],
                )
                if terminal_error:
                    meta["error"] = terminal_error
                    changed = True
            elif run_id and st == "error":
                terminal_error = _detect_terminal_text_cli_incomplete_error(
                    cli_type,
                    log_path=self._paths(run_id)["log"],
                )
                current_error = str(meta.get("error") or "").strip()
                if terminal_error and current_error in {"", "permission denied", "permission permission denied"}:
                    if current_error != terminal_error:
                        meta["error"] = terminal_error
                        changed = True
            changed = _sync_observability_fields() or changed
            return meta, changed
        # queue-related states can legitimately wait.
        # But when a queued run's own process is already alive (e.g. restarted scheduler lost in-memory slot),
        # auto-heal status to running to avoid long-lived false "queued" display.
        if st in {"queued", "retry_waiting"}:
            if st == "queued":
                run_id = str(meta.get("id") or "").strip()
                if run_id:
                    cli_type = str(meta.get("cliType") or "codex").strip() or "codex"
                    alive = _run_process_alive(run_id, cli_type=cli_type)
                    if alive:
                        changed = False
                        if str(meta.get("status") or "") != "running":
                            meta["status"] = "running"
                            changed = True
                        if not str(meta.get("startedAt") or "").strip():
                            meta["startedAt"] = str(meta.get("createdAt") or "").strip() or _now_iso()
                            changed = True
                        if str(meta.get("finishedAt") or "").strip():
                            meta["finishedAt"] = ""
                            changed = True
                        if str(meta.get("error") or "").strip():
                            meta["error"] = ""
                            changed = True
                        if "errorType" in meta:
                            meta.pop("errorType", None)
                            changed = True
                        if "queueReason" in meta:
                            meta.pop("queueReason", None)
                            changed = True
                        if "queueReasonAt" in meta:
                            meta.pop("queueReasonAt", None)
                            changed = True
                        if "queueTimeoutAt" in meta:
                            meta.pop("queueTimeoutAt", None)
                            changed = True
                        return meta, changed
            return meta, False
        if st != "running":
            return meta, False

        if not run_id:
            return meta, False

        # If this run is still tracked by the in-process executor, keep status=running.
        # This avoids UI flicker caused by transient probe misses during long/retrying runs.
        if RUN_PROCESS_REGISTRY.is_tracked(run_id):
            if "probeMisses" in meta:
                try:
                    meta.pop("probeMisses", None)
                except Exception:
                    pass
                return meta, True
            return meta, False

        # Get CLI type from meta, default to codex for backward compatibility
        cli_type = str(meta.get("cliType") or "codex").strip() or "codex"

        created_ts = _parse_iso_ts(meta.get("createdAt"))
        started_ts = _parse_iso_ts(meta.get("startedAt"))
        anchor_ts = started_ts or created_ts
        if anchor_ts > 0 and (time.time() - anchor_ts) < 45:
            return meta, False

        alive = _run_process_alive(run_id, cli_type=cli_type)
        if alive:
            if "probeMisses" in meta:
                try:
                    meta.pop("probeMisses", None)
                except Exception:
                    pass
                return meta, True
            return meta, False

        # Avoid false "interrupted" flaps:
        # only mark as interrupted after several consecutive misses.
        miss = int(meta.get("probeMisses") or 0) + 1
        meta["probeMisses"] = miss
        if miss < 3:
            return meta, True

        changed = False
        log_path = self._paths(run_id)["log"]
        last = self.read_last(run_id, limit_chars=8000).strip()
        terminal_last = runtime_extract_terminal_message_from_file(log_path, cli_type=cli_type).strip()
        existing_last_preview = str(meta.get("lastPreview") or "").strip()
        agent_msgs = _extract_agent_messages_from_file(log_path, max_items=4, cli_type=cli_type)
        log_has_turn_completed = _log_has_terminal_signal(log_path, signal="turn.completed")
        log_has_turn_failed = _log_has_terminal_signal(log_path, signal="turn.failed")
        if (
            last
            or terminal_last
            or existing_last_preview
            or log_has_turn_completed
            or (agent_msgs and not log_has_turn_failed)
        ):
            if "probeMisses" in meta:
                try:
                    meta.pop("probeMisses", None)
                except Exception:
                    pass
                changed = True
            if st != "done":
                meta["status"] = "done"
                changed = True
            if str(meta.get("error") or "").strip():
                meta["error"] = ""
                changed = True
            if not str(meta.get("finishedAt") or "").strip():
                meta["finishedAt"] = _now_iso()
                changed = True
            preview_src = last or terminal_last or existing_last_preview or (agent_msgs[-1] if agent_msgs else "")
            preview = _safe_text(preview_src.replace("\r\n", "\n"), 300)
            if preview != str(meta.get("lastPreview") or ""):
                meta["lastPreview"] = preview
                changed = True
            if _sync_observability_fields():
                changed = True
            return meta, changed

        # Consecutive probe misses reached threshold; clear counter and mark interrupted.
        if "probeMisses" in meta:
            try:
                meta.pop("probeMisses", None)
            except Exception:
                pass
            changed = True

        if st != "error":
            meta["status"] = "error"
            changed = True
        if not str(meta.get("finishedAt") or "").strip():
            meta["finishedAt"] = _now_iso()
            changed = True
        if not str(meta.get("error") or "").strip():
            meta["error"] = "run interrupted (server restarted or process exited)"
            changed = True
        if _sync_observability_fields():
            changed = True
        # Backfill a minimal log for old/interrupted runs so UI can show actionable context.
        try:
            if not log_path.exists():
                log_path.write_text(
                    "[system] run interrupted: process no longer alive\n"
                    f"[system] run_id={run_id}\n"
                    f"[system] cli_type={cli_type}\n"
                    f"[system] created_at={meta.get('createdAt')}\n"
                    f"[system] started_at={meta.get('startedAt')}\n"
                    f"[system] finished_at={meta.get('finishedAt')}\n",
                    encoding="utf-8",
                )
        except Exception:
            pass
        return meta, changed

    def list_runs(
        self,
        channel_id: str = "",
        limit: int = 30,
        project_id: str = "",
        session_id: str = "",
        cli_type: str = "",
        after_created_at: str = "",
        before_created_at: str = "",
        include_payload: bool = True,
        payload_mode: str = "",
    ) -> list[dict[str, Any]]:
        metas = []
        resolved_payload_mode = str(payload_mode or "").strip().lower()
        if resolved_payload_mode not in {"", "full", "light", "none"}:
            resolved_payload_mode = ""
        if not resolved_payload_mode:
            resolved_payload_mode = "full" if include_payload else "none"
        include_payload = resolved_payload_mode != "none"
        hydrate_light = resolved_payload_mode in {"full", "light"}
        hydrate_full = resolved_payload_mode == "full"
        after_txt = str(after_created_at or "").strip()
        before_txt = str(before_created_at or "").strip()
        after_ts = _parse_rfc3339_ts(after_txt) if after_txt else 0.0
        before_ts = _parse_rfc3339_ts(before_txt) if before_txt else 0.0
        for meta in self._snapshot_live_run_index():
            if bool(meta.get("hidden")):
                continue
            run_id = str(meta.get("id") or "").strip()
            if run_id:
                meta, changed = self.reconcile_meta(meta)
                if changed:
                    self.save_meta(run_id, meta)
            if channel_id and str(meta.get("channelId") or "") != channel_id:
                continue
            if project_id and str(meta.get("projectId") or "") != project_id:
                continue
            if session_id and str(meta.get("sessionId") or "") != session_id:
                continue
            if cli_type and str(meta.get("cliType") or "codex") != cli_type:
                continue
            if after_ts > 0 or before_ts > 0:
                created_ts = _parse_rfc3339_ts(meta.get("createdAt"))
                if after_ts > 0 and not (created_ts > after_ts):
                    continue
                if before_ts > 0 and not (created_ts < before_ts):
                    continue

            if include_payload:
                # Get CLI type for this run
                run_cli_type = str(meta.get("cliType") or "codex").strip() or "codex"

                msg = ""
                if hydrate_light and (hydrate_full or not str(meta.get("messagePreview") or "").strip()):
                    msg = self.read_msg(run_id, limit_chars=4000)
                    if msg:
                        meta["messagePreview"] = _safe_text(msg.replace("\r\n", "\n").strip(), 260)
                last = ""
                if hydrate_light and (hydrate_full or not str(meta.get("lastPreview") or "").strip()):
                    last = self.read_last(run_id, limit_chars=2000)
                    if last:
                        meta["lastPreview"] = _safe_text(last.replace("\r\n", "\n").strip(), 300)
                log = ""
                am: list[str] = []
                if hydrate_full:
                    log = self.read_log(run_id, limit_chars=2400)
                    if not log:
                        log = _fallback_log_from_meta(meta)
                    if log:
                        meta["logPreview"] = _safe_text(log.replace("\r\n", "\n").strip(), 420)
                        am_preview = _extract_agent_messages(log, max_items=4, cli_type=run_cli_type)
                        am_file = _extract_agent_messages_from_file(
                            self._paths(run_id)["log"],
                            max_items=4,
                            cli_type=run_cli_type,
                        )
                        am = am_file if len(am_file) >= len(am_preview) else am_preview
                        if am:
                            prev_count = int(meta.get("agentMessagesCount") or 0)
                            meta["agentMessagesCount"] = max(prev_count, len(am))
                        if am and not str(meta.get("lastPreview") or "").strip():
                            meta["partialPreview"] = _safe_text(am[-1], 300)
                eh = _error_hint(str(meta.get("error") or ""))
                if eh:
                    meta["errorHint"] = eh
                existing_skills = _normalize_skills_used_value(meta.get("skills_used"), max_items=20)
                if existing_skills:
                    meta["skills_used"] = existing_skills
                elif hydrate_full and not isinstance(meta.get("skills_used"), list):
                    skill_texts: list[str] = []
                    last_preview = str(meta.get("lastPreview") or "").strip()
                    partial_preview = str(meta.get("partialPreview") or "").strip()
                    msg_preview = str(meta.get("messagePreview") or "").strip()
                    if last_preview:
                        skill_texts.append(last_preview)
                    if partial_preview:
                        skill_texts.append(partial_preview)
                    if msg_preview:
                        skill_texts.append(msg_preview)
                    if am:
                        skill_texts.extend(am)
                    meta["skills_used"] = _extract_skills_used_from_texts(skill_texts, max_items=20)
                existing_business_refs = _normalize_business_refs_value(meta.get("business_refs"), max_items=24)
                if existing_business_refs:
                    meta["business_refs"] = existing_business_refs
                elif hydrate_full and (not isinstance(meta.get("business_refs"), list)):
                    business_texts: list[str] = []
                    last_preview = str(meta.get("lastPreview") or "").strip()
                    partial_preview = str(meta.get("partialPreview") or "").strip()
                    msg_preview = str(meta.get("messagePreview") or "").strip()
                    if last_preview:
                        business_texts.append(last_preview)
                    if partial_preview:
                        business_texts.append(partial_preview)
                    if msg_preview:
                        business_texts.append(msg_preview)
                    parsed_business_refs = _extract_business_refs_from_texts(business_texts, max_items=24)
                    if parsed_business_refs:
                        meta["business_refs"] = parsed_business_refs
            metas.append(meta)
            if len(metas) >= limit:
                break
        return metas

    def archive_terminal_runs(
        self,
        *,
        older_than_s: float,
        limit: int = 500,
        dry_run: bool = False,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        terminal_statuses = {"done", "error", "interrupted"}
        now_ts = time.time()
        if older_than_s <= 0:
            older_than_s = 86400.0
        candidates: list[tuple[float, Path, dict[str, Any]]] = []
        for meta_path in self._iter_live_meta_paths():
            if meta_path.parent == self.hot_dir:
                continue
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(meta, dict):
                continue
            if bool(meta.get("hidden")):
                continue
            status = str(meta.get("status") or "").strip().lower()
            if status not in terminal_statuses:
                continue
            anchor_ts = (
                _parse_iso_ts(meta.get("finishedAt"))
                or _parse_iso_ts(meta.get("createdAt"))
                or _parse_iso_ts(meta.get("startedAt"))
            )
            if anchor_ts <= 0 or (now_ts - anchor_ts) < older_than_s:
                continue
            candidates.append((anchor_ts, meta_path, meta))

        candidates.sort(key=lambda item: item[0])
        for _, meta_path, meta in candidates[: max(1, int(limit or 1))]:
            run_id = str(meta.get("id") or "").strip()
            if not run_id:
                continue
            bucket = self._archive_bucket_for_meta(meta)
            src = self._paths(run_id)
            dst = self._archive_paths(run_id, bucket)
            results.append({
                "run_id": run_id,
                "bucket": bucket,
                "status": str(meta.get("status") or "").strip(),
                "src_meta": str(src["meta"]),
                "dst_meta": str(dst["meta"]),
            })
            if dry_run:
                continue
            dst["meta"].parent.mkdir(parents=True, exist_ok=True)
            for key in ("meta", "msg", "last", "log"):
                if not src[key].exists():
                    continue
                src[key].replace(dst[key])
            self._remove_live_run_index_entry(run_id)
        return results

_RUN_ACTION_AUDIT_LOCK = threading.Lock()


def _run_action_audit_path(store: "RunStore") -> Path:
    return store.runs_dir.parent / ".run" / "run-action-audit.jsonl"


def _append_run_action_audit(
    store: "RunStore",
    *,
    run_id: str,
    action: str,
    requested_action: str = "",
    http_status: int,
    outcome: str,
    error: str = "",
    meta: Optional[dict[str, Any]] = None,
    client_ip: str = "",
    user_agent: str = "",
    referer: str = "",
    origin: str = "",
    request_path: str = "",
) -> None:
    payload: dict[str, Any] = {
        "at": _now_iso(),
        "run_id": _safe_text(run_id, 80).strip(),
        "action": _safe_text(action, 80).strip().lower(),
        "requested_action": _safe_text(requested_action, 80).strip().lower(),
        "http_status": int(http_status),
        "outcome": _safe_text(outcome, 40).strip().lower(),
        "error": _safe_text(error, 500).strip(),
        "request": {
            "path": _safe_text(request_path, 500).strip(),
            "client_ip": _safe_text(client_ip, 80).strip(),
            "user_agent": _safe_text(user_agent, 500).strip(),
            "referer": _safe_text(referer, 500).strip(),
            "origin": _safe_text(origin, 500).strip(),
        },
    }
    if isinstance(meta, dict):
        payload["target_run"] = {
            "status": _safe_text(meta.get("status"), 60).strip().lower(),
            "project_id": _safe_text(meta.get("projectId"), 80).strip(),
            "channel_name": _safe_text(meta.get("channelName"), 200).strip(),
            "session_id": _safe_text(meta.get("sessionId"), 80).strip(),
            "trigger_type": _safe_text(meta.get("trigger_type"), 80).strip(),
            "task_push_job_id": _safe_text(meta.get("task_push_job_id"), 80).strip(),
        }
    try:
        line = json.dumps(payload, ensure_ascii=False)
    except Exception:
        return
    path = _run_action_audit_path(store)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with _RUN_ACTION_AUDIT_LOCK:
            with path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
    except Exception:
        return


def _enqueue_run_execution(
    store: RunStore,
    run_id: str,
    session_id: str,
    cli_type: str,
    scheduler: Optional["RunScheduler"],
    *,
    priority: str = "normal",
) -> None:
    if scheduler is not None and str(os.environ.get("CCB_SCHEDULER") or "").strip() != "0":
        try:
            scheduler.enqueue(run_id, session_id, cli_type=cli_type, priority=priority)
        except TypeError:
            # Backward compatibility for tests/stubs that only accept legacy signature.
            scheduler.enqueue(run_id, session_id, cli_type=cli_type)
    else:
        threading.Thread(target=run_cli_exec, args=(store, run_id, None, cli_type, None), daemon=True).start()

class SessionBindingStore:
    """Persistent session binding store (like .runs/ but for session bindings).

    This is the legacy session binding store. For new session management,
    use SessionStore from task_dashboard.session_store instead.
    """

    def __init__(self, runs_dir: Path) -> None:
        self.sessions_dir = runs_dir.parent / ".sessions"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

    def _session_path(self, session_id: str) -> Path:
        # Use safe filename: replace problematic chars
        safe_id = session_id.replace("/", "_").replace(":", "_")
        return self.sessions_dir / f"{safe_id}.json"

    def save_binding(
        self,
        session_id: str,
        project_id: str,
        channel_name: str,
        cli_type: str = "codex",
    ) -> dict[str, Any]:
        """Save a session binding to persistent storage."""
        sid = str(session_id or "").strip()
        pid = str(project_id or "").strip()
        cname = str(channel_name or "").strip()
        ctype = str(cli_type or "codex").strip() or "codex"
        path = self._session_path(sid)
        meta = {
            "sessionId": sid,
            "projectId": pid,
            "channelName": cname,
            "cliType": ctype,
            "boundAt": time.strftime("%Y-%m-%dT%H:%M:%S+0800", time.localtime()),
        }
        _atomic_write_text(path, json.dumps(meta, ensure_ascii=False, indent=2))
        # Legacy store keeps one effective binding per channel.
        # Remove stale files for the same project/channel to avoid old rows overriding new binding.
        for p in self.sessions_dir.glob("*.json"):
            if p == path:
                continue
            try:
                raw = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(raw, dict):
                continue
            if str(raw.get("projectId") or "").strip() != pid:
                continue
            if str(raw.get("channelName") or "").strip() != cname:
                continue
            if str(raw.get("sessionId") or "").strip() == sid:
                continue
            try:
                p.unlink()
            except Exception:
                continue
        return meta

    def get_binding(self, session_id: str) -> dict[str, Any] | None:
        """Get a session binding by session_id."""
        path = self._session_path(session_id)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def delete_binding(self, session_id: str) -> bool:
        """Delete a session binding."""
        path = self._session_path(session_id)
        if path.exists():
            path.unlink()
            return True
        return False

    def list_bindings(self, project_id: str | None = None) -> list[dict[str, Any]]:
        """List all session bindings, optionally filtered by project_id."""
        results = []
        for p in self.sessions_dir.glob("*.json"):
            try:
                meta = json.loads(p.read_text(encoding="utf-8"))
                if project_id and str(meta.get("projectId") or "") != project_id:
                    continue
                results.append(meta)
            except Exception:
                continue
        # Sort by boundAt descending
        results.sort(key=lambda x: x.get("boundAt", ""), reverse=True)
        return results


class Handler(BaseHTTPRequestHandler):
    server_version = "task-dashboard-ccb/1.0"

    def _deny_remote_share_only_request(self, method: str) -> bool:
        if not _is_remote_share_only_request_blocked(
            getattr(self, "client_address", None),
            method,
            getattr(self, "path", ""),
        ):
            return False
        path = urlparse(str(getattr(self, "path", "") or "")).path
        if path == "/__health" or path.startswith("/api/"):
            _json_response(self, 404, {"error": "not found"}, send_body=(self.command != "HEAD"))
            return True
        self.send_error(HTTPStatus.NOT_FOUND, "not found")
        return True

    def _require_token(self) -> bool:
        tok = _server_token()
        if not tok:
            return True
        hv = str(self.headers.get("X-TaskDashboard-Token") or "").strip()
        if hv and secrets.compare_digest(hv, tok):
            return True
        auth = str(self.headers.get("Authorization") or "").strip()
        if auth.lower().startswith("bearer "):
            av = auth[7:].strip()
            if av and secrets.compare_digest(av, tok):
                return True
        _json_response(self, 403, {"error": "forbidden"}, send_body=(self.command != "HEAD"))
        return False

    def _serve_static(self, static_root: Path, url_path: str, *, send_body: bool = True) -> None:
        # Map URL to file; default to /index.html if directory.
        rel = url_path.lstrip("/")
        rel = rel.split("?", 1)[0].split("#", 1)[0]
        if not rel:
            rel = "index.html"
        # Prevent traversal via .. while still allowing symlinks under static_root.
        rel_path = Path(rel)
        if rel_path.is_absolute() or any(p == ".." for p in rel_path.parts):
            self.send_error(HTTPStatus.FORBIDDEN, "forbidden")
            return

        target_raw = (static_root / rel_path)
        target = target_raw.resolve()
        static_root_res = static_root.resolve()
        allow_root_res: Path = self.server.allow_root  # type: ignore[attr-defined]
        # Allow:
        # - normal files under static_root
        # - symlink targets that resolve under allow_root (repo root), so /share/*.html symlinks work
        allowed = False
        try:
            target.relative_to(static_root_res)
            allowed = True
        except Exception:
            pass
        if not allowed:
            try:
                target.relative_to(allow_root_res)
                allowed = True
            except Exception:
                allowed = False
        if not allowed:
            self.send_error(HTTPStatus.FORBIDDEN, "forbidden")
            return

        if target.is_dir():
            target = (target / "index.html").resolve()
        if not target.exists() or not target.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "not found")
            return

        ctype, _ = mimetypes.guess_type(str(target))
        ctype = ctype or "application/octet-stream"
        size = 0
        data = b""
        try:
            size = int(target.stat().st_size)
        except Exception:
            size = 0
        if send_body:
            data = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data) if send_body else size))
        # Dashboard files are frequently regenerated; disable browser caching
        # to avoid stale views after channel/status changes.
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.end_headers()
        if send_body:
            self.wfile.write(data)

    def _conversation_memo_store(self, run_store: RunStore) -> ConversationMemoStore:
        store = getattr(self.server, "conversation_memo_store", None)  # type: ignore[attr-defined]
        if isinstance(store, ConversationMemoStore):
            return store
        base_dir = run_store.runs_dir.parent / ".run" / "conversation-memos"
        store = ConversationMemoStore(base_dir=base_dir)
        try:
            self.server.conversation_memo_store = store  # type: ignore[attr-defined]
        except Exception:
            pass
        return store

    def _share_mode_static_target(self, static_root: Path) -> Path:
        rel = RUNTIME_SHARE_MODE_PAGE_PATH.lstrip("/")
        return static_root / rel

    def _maybe_redirect_legacy_share_page(
        self,
        static_root: Path,
        request_path: str,
        *,
        query: str = "",
    ) -> bool:
        if str(request_path or "") not in {
            RUNTIME_LEGACY_PROJECT_CHAT_PAGE_PATH,
            RUNTIME_LEGACY_SHARE_SPACE_PAGE_PATH,
        }:
            return False
        target = self._share_mode_static_target(static_root)
        if not target.exists() or not target.is_file():
            return False

        location = RUNTIME_SHARE_MODE_PAGE_PATH + (("?" + query) if query else "")
        self.send_response(HTTPStatus.FOUND)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.end_headers()
        return True

    def _build_route_context(
        self,
        store: RunStore,
        session_store: SessionStore,
        static_root: Path,
        scheduler: Any,
    ) -> RouteContext:
        """Build RouteContext for route dispatcher."""
        ctx_kwargs = dict(
            store=store,
            session_store=session_store,
            session_binding_store=self.server.session_binding_store,  # type: ignore[attr-defined]
            static_root=static_root,
            runs_dir=store.runs_dir,
            worktree_root=getattr(self.server, "worktree_root", _repo_root()),  # type: ignore[attr-defined]
            environment_name=str(getattr(self.server, "environment_name", "stable") or "stable"),
            server_port=int(getattr(self.server, "server_port", 0) or 0),
            scheduler=scheduler,
            project_scheduler_runtime=getattr(self.server, "project_scheduler_runtime", None),  # type: ignore[attr-defined]
            heartbeat_runtime=getattr(self.server, "heartbeat_task_runtime", None),  # type: ignore[attr-defined]
            task_push_runtime=getattr(self.server, "task_push_runtime", None),  # type: ignore[attr-defined]
            task_plan_runtime=getattr(self.server, "task_plan_runtime", None),  # type: ignore[attr-defined]
            assist_request_runtime=getattr(self.server, "assist_request_runtime", None),  # type: ignore[attr-defined]
            conversation_memo_store=self._conversation_memo_store(store),
            allow_root=self.server.allow_root,  # type: ignore[attr-defined]
            # Helper functions
            json_response=_json_response,
            read_body_json=_read_body_json,
            require_token=self._require_token,
            safe_text=_safe_text,
            coerce_bool=_coerce_bool,
            coerce_int=_coerce_int,
            now_iso=_now_iso,
            looks_like_uuid=_looks_like_uuid,
            find_project_cfg=_find_project_cfg,
            server_token=_server_token,
            repo_root=_repo_root,
            # Runtime helpers for GET routes
            list_enabled_cli_types=list_enabled_cli_types,
            runtime_list_sessions_response=runtime_list_sessions_response,
            runtime_list_runs_response=runtime_list_runs_response,
            runtime_get_run_detail_response=runtime_get_run_detail_response,
            runtime_list_channel_sessions_response=runtime_list_channel_sessions_response,
            runtime_get_session_binding_response=runtime_get_session_binding_response,
            runtime_list_session_heartbeat_task_history_route_response=runtime_list_session_heartbeat_task_history_route_response,
            maybe_trigger_restart_recovery_lazy=_maybe_trigger_restart_recovery_lazy,
            maybe_trigger_queued_recovery_lazy=_maybe_trigger_queued_recovery_lazy,
            build_run_observability_fields=_build_run_observability_fields,
            error_hint=_error_hint,
            perform_run_action_response=runtime_perform_run_action_response,
            list_task_push_status_response=list_task_push_status_response,
            run_process_registry=RUN_PROCESS_REGISTRY,
            append_run_action_audit=_append_run_action_audit,
            dispatch_terminal_callback_for_run=_dispatch_terminal_callback_for_run,
            create_cli_session=create_cli_session,
            resolve_project_workdir=_resolve_project_workdir,
            detect_git_branch=runtime_detect_git_branch,
            build_session_seed_prompt=_build_session_seed_prompt,
            decorate_session_display_fields=_decorate_session_display_fields,
            decorate_sessions_display_fields=_decorate_sessions_display_fields,
            apply_session_context_rows=runtime_apply_session_context_rows,
            derive_session_work_context=_derive_session_work_context,
            apply_session_work_context=_apply_session_work_context,
            load_project_execution_context=_load_project_execution_context,
            project_channel_exists=_project_channel_exists,
            create_channel=_create_channel,
            run_codex_channel_bootstrap=_run_codex_channel_bootstrap_v1,
            infer_project_id_for_session=_infer_project_id_for_session,
            resolve_primary_target_by_channel=_resolve_primary_target_by_channel,
            resolve_channel_primary_session_id=_resolve_channel_primary_session_id,
            session_context_write_requires_guard=_session_context_write_requires_guard,
            stable_write_ack_requested=_stable_write_ack_requested,
            heartbeat_session_payload_for_write=_heartbeat_session_payload_for_write,
            build_session_detail_response=runtime_build_session_detail_response,
            apply_effective_primary_flags=_apply_effective_primary_flags,
            build_session_detail_payload=runtime_build_session_detail_payload,
            build_project_session_runtime_index=_build_project_session_runtime_index,
            build_session_runtime_state_for_row=_build_session_runtime_state_for_row,
            attach_runtime_state_to_sessions=_attach_runtime_state_to_sessions,
            load_session_heartbeat_config=_load_session_heartbeat_config,
            heartbeat_summary_payload=_heartbeat_summary_payload,
            reveal_allowed_roots=_reveal_allowed_roots,
            upload_max_bytes=_upload_max_bytes,
            sanitize_upload_filename=_sanitize_upload_filename,
            parse_multipart_single_file=_parse_multipart_single_file,
            rebuild_dashboard_static=_rebuild_dashboard_static,
            read_task_dashboard_generated_at=_read_task_dashboard_generated_at,
            set_runtime_max_concurrency_in_config=_set_runtime_max_concurrency_in_config,
            set_runtime_cli_bins_in_local_config=_set_runtime_cli_bins_in_local_config,
            communication_audit_scope_catalog=_communication_audit_scope_catalog,
            parse_communication_audit_scopes=_parse_communication_audit_scopes,
            get_communication_audit_summary=_get_communication_audit_summary,
            communication_audit_cache_ttl_s=_communication_audit_cache_ttl_s,
            load_dashboard_cfg_current=_load_dashboard_cfg_current,
            default_project_id_from_cfg=_default_project_id_from_cfg,
            resolve_effective_max_concurrency=_resolve_effective_max_concurrency,
            resolve_scheduler_engine_enabled=_resolve_scheduler_engine_enabled,
            collect_cli_tools_snapshot=_collect_cli_tools_snapshot,
            runtime_cfg_max_concurrency_from_cfg=_runtime_cfg_max_concurrency_from_cfg,
            with_local_config_enabled=_with_local_config_enabled,
            resolve_allowed_fs_path=_resolve_allowed_fs_path,
            relative_path_to_repo_root=_relative_path_to_repo_root,
            fs_preview_dir_limit=_FS_PREVIEW_DIR_LIMIT,
            is_text_preview_path=_is_text_preview_path,
            read_text_preview=_read_text_preview,
            preview_mode_for_path=_preview_mode_for_path,
            build_global_resource_graph_payload=_build_global_resource_graph_payload,
            list_project_heartbeat_tasks_response=list_project_heartbeat_tasks_response,
            get_project_heartbeat_task_response=get_project_heartbeat_task_response,
            list_project_heartbeat_task_history_response=list_project_heartbeat_task_history_response,
            list_session_heartbeat_task_history_response=list_session_heartbeat_task_history_response,
            normalize_heartbeat_task_id=_normalize_heartbeat_task_id,
            heartbeat_task_history_limit=_HEARTBEAT_TASK_HISTORY_LIMIT,
            build_runtime_bubbles_payload=_build_runtime_bubbles_payload,
            list_task_plans_response=list_task_plans_response,
            list_assist_requests_response=list_assist_requests_response,
            get_assist_request_response=get_assist_request_response,
            get_project_auto_scheduler_status_response=get_project_auto_scheduler_status_response,
            list_project_auto_inspection_tasks_response=list_project_auto_inspection_tasks_response,
            list_project_inspection_records_response=list_project_inspection_records_response,
            build_project_scheduler_status=_build_project_scheduler_status,
            ensure_auto_scheduler_status_shape=_ensure_auto_scheduler_status_shape,
            get_project_config_response=get_project_config_response,
            attach_auto_inspection_candidate_preview=_attach_auto_inspection_candidate_preview,
            config_toml_path=_config_toml_path,
            config_local_toml_path=_config_local_toml_path,
            load_project_auto_inspection_config=_load_project_auto_inspection_config,
            normalize_auto_inspection_tasks=_normalize_auto_inspection_tasks,
            normalize_inspection_task_id=_normalize_inspection_task_id,
            normalize_inspection_records=_normalize_inspection_records,
            auto_inspection_record_limit=_AUTO_INSPECTION_RECORD_LIMIT,
            create_or_update_project_auto_inspection_task_response=create_or_update_project_auto_inspection_task_response,
            delete_project_auto_inspection_task_response=delete_project_auto_inspection_task_response,
            set_project_auto_scheduler_enabled_response=set_project_auto_scheduler_enabled_response,
            build_default_auto_inspection_task=_build_default_auto_inspection_task,
            normalize_inspection_targets=_normalize_inspection_targets,
            normalize_auto_inspections=_normalize_auto_inspections,
            normalize_auto_inspection_task=_normalize_auto_inspection_task,
            auto_inspection_tasks_for_write=_auto_inspection_tasks_for_write,
            build_auto_inspection_patch_with_tasks=_build_auto_inspection_patch_with_tasks,
            set_project_scheduler_contract_in_config=_set_project_scheduler_contract_in_config,
            set_project_scheduler_enabled_in_config=_set_project_scheduler_enabled_in_config,
            update_project_config_response=update_project_config_response,
            clear_dashboard_cfg_cache=_clear_dashboard_cfg_cache,
            invalidate_sessions_payload_cache=runtime_invalidate_sessions_payload_cache,
            load_project_scheduler_contract_config=_load_project_scheduler_contract_config,
            load_project_auto_dispatch_config=_load_project_auto_dispatch_config,
            load_project_heartbeat_config=_load_project_heartbeat_config,
            normalize_auto_inspection_object=_normalize_auto_inspection_object,
            auto_inspection_targets_from_objects=_auto_inspection_targets_from_objects,
            inspection_target_tokens=_inspection_target_tokens,
            inspection_target_set=_INSPECTION_TARGET_SET,
            normalize_heartbeat_task=_normalize_heartbeat_task,
            heartbeat_tasks_for_write=_heartbeat_tasks_for_write,
            normalize_heartbeat_tasks=_normalize_heartbeat_tasks,
            default_inspection_targets=_DEFAULT_INSPECTION_TARGETS,
            extract_sender_fields=_extract_sender_fields,
            extract_run_extra_fields=_extract_run_extra_fields,
            build_local_server_origin=_build_local_server_origin,
            build_public_server_origin=_build_public_server_origin,
            resolve_attachment_local_path=_resolve_attachment_local_path,
        )
        try:
            allowed_keys = set(inspect.signature(RouteContext).parameters.keys())
        except Exception:
            allowed_keys = set(ctx_kwargs.keys())
        return RouteContext(**{key: value for key, value in ctx_kwargs.items() if key in allowed_keys})

    def do_HEAD(self) -> None:  # noqa: N802
        if self._deny_remote_share_only_request("HEAD"):
            return
        static_root: Path = self.server.static_root  # type: ignore[attr-defined]
        store: RunStore = self.server.store  # type: ignore[attr-defined]
        session_store: SessionStore = self.server.session_store  # type: ignore[attr-defined]
        scheduler = getattr(self.server, "scheduler", None)  # type: ignore[attr-defined]

        # Try route dispatcher first
        ctx = self._build_route_context(store, session_store, static_root, scheduler)
        if dispatch_head_request(self, ctx):
            return

        u = urlparse(self.path)
        if u.path.startswith("/.runs/"):
            runs_root = store.runs_dir
            target = _resolve_runs_static_target(runs_root, u.path)
            if not target:
                self.send_error(HTTPStatus.FORBIDDEN, "forbidden")
                return
            if not target.exists() or not target.is_file():
                self.send_error(HTTPStatus.NOT_FOUND, "not found")
                return
            ctype, _ = mimetypes.guess_type(str(target))
            ctype = ctype or "application/octet-stream"
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(target.stat().st_size))
            if _is_runs_attachment_request(u.path):
                self.send_header("Cache-Control", "public, max-age=86400, immutable")
            else:
                self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
                self.send_header("Pragma", "no-cache")
                self.send_header("Expires", "0")
            self.end_headers()
            return

        # For API endpoints, keep behavior simple: mirror GET status but no body.
        if u.path.startswith("/api/"):
            if (
                u.path == "/api/codex/runs"
                or u.path.startswith("/api/codex/run/")
                or u.path == "/api/communication/audit"
                or (u.path.startswith("/api/projects/") and u.path.endswith("/runtime-bubbles"))
                or (u.path.startswith("/api/projects/") and "/auto-scheduler" in u.path)
                or u.path == "/api/cli/types"
                or u.path == "/api/board/global-resource-graph"
                or u.path == "/api/conversation-memos"
            ):
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            self.send_error(HTTPStatus.NOT_FOUND, "not found")
            return

        if self._maybe_redirect_legacy_share_page(static_root, u.path, query=u.query or ""):
            return

        self._serve_static(static_root, u.path, send_body=False)

    def do_GET(self) -> None:  # noqa: N802
        if self._deny_remote_share_only_request("GET"):
            return
        static_root: Path = self.server.static_root  # type: ignore[attr-defined]
        store: RunStore = self.server.store  # type: ignore[attr-defined]
        session_store: SessionStore = self.server.session_store  # type: ignore[attr-defined]
        scheduler = getattr(self.server, "scheduler", None)  # type: ignore[attr-defined]
        u = urlparse(self.path)

        # Try route dispatcher first
        ctx = self._build_route_context(store, session_store, static_root, scheduler)
        if dispatch_get_request(self, ctx):
            return  # Route handled by dispatcher

        if self._maybe_redirect_legacy_share_page(static_root, u.path, query=u.query or ""):
            return

        if u.path == "/api/conversation-memos":
            qs = parse_qs(u.query or "")
            project_id = _safe_text((qs.get("projectId") or qs.get("project_id") or [""])[0], 120).strip()
            session_id = _safe_text((qs.get("sessionId") or qs.get("session_id") or [""])[0], 120).strip()
            if not project_id:
                _json_response(self, 400, {"error": "missing projectId"})
                return
            if not session_id or not _looks_like_uuid(session_id):
                _json_response(self, 400, {"error": "missing/invalid sessionId"})
                return
            memo_store = self._conversation_memo_store(store)
            payload = memo_store.list(project_id, session_id)
            _json_response(self, 200, payload)
            return

        # Serve files from .runs directory (attachments)
        if u.path.startswith("/.runs/"):
            runs_root = store.runs_dir
            # e.g., /.runs/attachments/xxx.png -> <runs_root>/attachments/xxx.png
            target = _resolve_runs_static_target(runs_root, u.path)
            if not target:
                self.send_error(HTTPStatus.FORBIDDEN, "forbidden")
                return
            if not target.exists() or not target.is_file():
                self.send_error(HTTPStatus.NOT_FOUND, "not found")
                return
            ctype, _ = mimetypes.guess_type(str(target))
            ctype = ctype or "application/octet-stream"
            data = target.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            if _is_runs_attachment_request(u.path):
                self.send_header("Cache-Control", "public, max-age=86400, immutable")
            else:
                self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
                self.send_header("Pragma", "no-cache")
                self.send_header("Expires", "0")
            self.end_headers()
            self.wfile.write(data)
            return
        parts = [seg for seg in u.path.split("/") if seg]
        # New endpoint: GET /api/sessions - list sessions
        if u.path == "/api/sessions":
            code, payload = runtime_list_sessions_response(
                query_string=u.query or "",
                session_store=session_store,
                store=store,
                environment_name=str(getattr(self.server, "environment_name", "stable") or "stable"),
                worktree_root=getattr(self.server, "worktree_root", _repo_root()),
                apply_effective_primary_flags=_apply_effective_primary_flags,
                decorate_sessions_display_fields=_decorate_sessions_display_fields,
                apply_session_context_rows=runtime_apply_session_context_rows,
                apply_session_work_context=_apply_session_work_context,
                attach_runtime_state_to_sessions=_attach_runtime_state_to_sessions,
                heartbeat_runtime=getattr(self.server, "heartbeat_task_runtime", None),
                load_session_heartbeat_config=_load_session_heartbeat_config,
                heartbeat_summary_payload=_heartbeat_summary_payload,
            )
            _json_response(self, code, payload)
            return

        if u.path == "/api/session-health":
            qs = parse_qs(u.query or "")
            project_id = _safe_text((qs.get("project_id") or qs.get("projectId") or [""])[0], 120).strip()
            if not project_id:
                _json_response(self, 400, {"error": "missing project_id"})
                return
            refresh = _coerce_bool((qs.get("refresh") or ["0"])[0], False)
            runtime = getattr(self.server, "session_health_runtime", None)
            if runtime is not None:
                payload = runtime.get_payload(project_id, refresh=refresh)
            else:
                payload = _build_session_health_payload(
                    project_id=project_id,
                    session_store=session_store,
                    store=store,
                    environment_name=str(getattr(self.server, "environment_name", "stable") or "stable"),
                    worktree_root=getattr(self.server, "worktree_root", _repo_root()),
                    heartbeat_runtime=getattr(self.server, "heartbeat_task_runtime", None),
                    load_session_heartbeat_config=_load_session_heartbeat_config,
                    heartbeat_summary_payload=_heartbeat_summary_payload,
                )
            _json_response(self, 200, payload)
            return

        # New endpoint: GET /api/sessions/{session_id} - get single session
        if u.path.startswith("/api/sessions/") and u.path.count("/") == 3:
            session_id = u.path.split("/")[-1]
            heartbeat_runtime: Optional[HeartbeatTaskRuntimeRegistry] = getattr(
                self.server, "heartbeat_task_runtime", None
            )  # type: ignore[attr-defined]
            code, payload = runtime_get_session_detail_response(
                session_id=session_id,
                session_store=session_store,
                store=store,
                environment_name=str(getattr(self.server, "environment_name", "stable") or "stable"),
                worktree_root=getattr(self.server, "worktree_root", _repo_root()),
                heartbeat_runtime=heartbeat_runtime,
                infer_project_id_for_session=_infer_project_id_for_session,
                apply_effective_primary_flags=_apply_effective_primary_flags,
                decorate_session_display_fields=_decorate_session_display_fields,
                build_session_detail_payload=runtime_build_session_detail_payload,
                apply_session_work_context=_apply_session_work_context,
                build_project_session_runtime_index=_build_project_session_runtime_index,
                build_session_runtime_state_for_row=_build_session_runtime_state_for_row,
                load_session_heartbeat_config=_load_session_heartbeat_config,
                heartbeat_summary_payload=_heartbeat_summary_payload,
            )
            _json_response(self, code, payload)
            return

        if u.path == "/api/codex/runs":
            bind_host = ""
            try:
                bind_host = str(self.server.server_address[0] or "").strip()
            except Exception:
                bind_host = ""
            code, payload = runtime_list_runs_response(
                query_string=u.query or "",
                store=store,
                scheduler=scheduler,
                maybe_trigger_restart_recovery_lazy=_maybe_trigger_restart_recovery_lazy,
                maybe_trigger_queued_recovery_lazy=_maybe_trigger_queued_recovery_lazy,
                build_run_observability_fields=_build_run_observability_fields,
                environment_name=str(getattr(self.server, "environment_name", "stable") or "stable"),
                local_server_origin=_build_local_server_origin(
                    bind_host,
                    int(getattr(self.server, "server_port", 0) or 0),
                ),
                worktree_root=str(getattr(self.server, "worktree_root", _repo_root())),
            )
            _json_response(self, code, payload)
            return

        if u.path.startswith("/api/codex/run/"):
            run_id = u.path.rsplit("/", 1)[-1]
            code, payload = runtime_get_run_detail_response(
                run_id=run_id,
                store=store,
                scheduler=scheduler,
                maybe_trigger_restart_recovery_lazy=_maybe_trigger_restart_recovery_lazy,
                maybe_trigger_queued_recovery_lazy=_maybe_trigger_queued_recovery_lazy,
                build_run_observability_fields=_build_run_observability_fields,
                error_hint=_error_hint,
            )
            _json_response(self, code, payload)
            return

        self._serve_static(static_root, u.path)

    def do_POST(self) -> None:  # noqa: N802
        if self._deny_remote_share_only_request("POST"):
            return
        store: RunStore = self.server.store  # type: ignore[attr-defined]
        session_store: SessionStore = self.server.session_store  # type: ignore[attr-defined]
        session_binding_store: SessionBindingStore = self.server.session_binding_store  # type: ignore[attr-defined]
        static_root: Path = self.server.static_root  # type: ignore[attr-defined]
        scheduler = getattr(self.server, "scheduler", None)  # type: ignore[attr-defined]

        # Try route dispatcher first
        ctx = self._build_route_context(store, session_store, static_root, scheduler)
        if dispatch_post_request(self, ctx):
            return

        u = urlparse(self.path)
        if u.path == "/api/session-health":
            if not self._require_token():
                return
            try:
                body = _read_body_json(self)
            except Exception as exc:
                _json_response(self, 400, {"error": str(exc)})
                return
            qs = parse_qs(u.query or "")
            project_id = _safe_text(
                body.get("project_id")
                if isinstance(body, dict) and "project_id" in body
                else (qs.get("project_id") or qs.get("projectId") or [""])[0],
                120,
            ).strip()
            code, payload = _update_project_session_health_config(
                project_id,
                body if isinstance(body, dict) else {},
            )
            _json_response(self, code, payload)
            return
        _json_response(self, 404, {"error": "not found"})

    def do_PUT(self) -> None:  # noqa: N802
        """Handle PUT requests for updating resources."""
        if self._deny_remote_share_only_request("PUT"):
            return
        store: RunStore = self.server.store  # type: ignore[attr-defined]
        session_store: SessionStore = self.server.session_store  # type: ignore[attr-defined]
        static_root: Path = self.server.static_root  # type: ignore[attr-defined]
        scheduler = getattr(self.server, "scheduler", None)  # type: ignore[attr-defined]

        # Try route dispatcher first
        ctx = self._build_route_context(store, session_store, static_root, scheduler)
        if dispatch_put_request(self, ctx):
            return

        u = urlparse(self.path)

        _json_response(self, 404, {"error": "not found"})

    def do_DELETE(self) -> None:  # noqa: N802
        """Handle DELETE requests for deleting resources."""
        if self._deny_remote_share_only_request("DELETE"):
            return
        store: RunStore = self.server.store  # type: ignore[attr-defined]
        session_store: SessionStore = self.server.session_store  # type: ignore[attr-defined]
        static_root: Path = self.server.static_root  # type: ignore[attr-defined]
        scheduler = getattr(self.server, "scheduler", None)  # type: ignore[attr-defined]

        # Try route dispatcher first
        ctx = self._build_route_context(store, session_store, static_root, scheduler)
        if dispatch_delete_request(self, ctx):
            return

        u = urlparse(self.path)

        _json_response(self, 404, {"error": "not found"})

    def log_message(self, fmt: str, *args: Any) -> None:
        # Keep stdout clean; write to server log file if needed.
        try:
            log_path: Path = self.server.http_log  # type: ignore[attr-defined]
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("a", encoding="utf-8") as f:
                f.write("%s - - [%s] %s\n" % (self.client_address[0], _now_iso(), fmt % args))
        except Exception:
            pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bind", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=18765)
    ap.add_argument("--static-root", type=str, required=True, help="directory to serve (static_sites)")
    ap.add_argument("--runs-dir", type=str, default=str(Path(__file__).resolve().parent / ".runs"))
    ap.add_argument("--http-log", type=str, default=str(Path(__file__).resolve().parent / ".run" / "task-dashboard-server.http.log"))
    ap.add_argument(
        "--environment-name",
        type=str,
        default=str(os.environ.get("TASK_DASHBOARD_ENV_NAME") or "stable"),
        help="runtime environment label",
    )
    args = ap.parse_args()

    static_root = Path(args.static_root).resolve()
    # Allow serving symlink targets within the declared repo root so env-specific
    # share aliases can point back to this worktree's dist files.
    allow_root = _repo_root().resolve()
    runs_dir = Path(args.runs_dir).resolve()
    store = RunStore(runs_dir=runs_dir)
    repaired_legacy_rows = store.repair_legacy_hot_meta_consistency(limit=200)
    if repaired_legacy_rows:
        print(f"[runstore] repaired legacy/hot meta drift: {len(repaired_legacy_rows)}")
    conversation_memo_store = ConversationMemoStore(base_dir=runs_dir.parent / ".run" / "conversation-memos")
    repo_root = Path(__file__).resolve().parent
    environment_name = str(args.environment_name or "stable").strip() or "stable"
    cfg = _load_dashboard_cfg_current()
    current_project_id = _resolve_runtime_project_id(
        cfg,
        environment_name=environment_name,
        port=int(args.port or 0),
    )
    current_runtime_role = str(os.environ.get("TASK_DASHBOARD_RUNTIME_ROLE") or "").strip().lower()
    if not current_runtime_role:
        current_runtime_role = _project_runtime_role(current_project_id)
    if environment_name == "stable" and runs_dir.parent != repo_root:
        try:
            sync_report = sync_project_session_store(repo_root, runs_dir.parent)
            copied = len(sync_report.get("copied_projects") or [])
            merged = len(sync_report.get("merged_projects") or [])
            if copied or merged:
                print(f"[session-sync] copied_projects={copied} merged_projects={merged}")
        except Exception as exc:
            print(f"[session-sync] skipped: {exc}")
    # New session store (for session CRUD)
    session_store = SessionStore(base_dir=runs_dir.parent)
    # Legacy session binding store (kept for backward compatibility)
    session_binding_store = SessionBindingStore(runs_dir=runs_dir)

    httpd = ThreadingHTTPServer((args.bind, args.port), Handler)
    _SERVER_HOLDER["server"] = httpd
    httpd.environment_name = environment_name  # type: ignore[attr-defined]
    httpd.project_id = current_project_id  # type: ignore[attr-defined]
    httpd.runtime_role = current_runtime_role  # type: ignore[attr-defined]
    httpd.static_root = static_root  # type: ignore[attr-defined]
    httpd.allow_root = allow_root  # type: ignore[attr-defined]
    httpd.runs_dir = runs_dir  # type: ignore[attr-defined]
    httpd.worktree_root = Path(__file__).resolve().parent  # type: ignore[attr-defined]
    httpd.store = store  # type: ignore[attr-defined]
    httpd.conversation_memo_store = conversation_memo_store  # type: ignore[attr-defined]
    httpd.session_store = session_store  # type: ignore[attr-defined]
    httpd.sessions_file = session_store.sessions_dir / f"{current_project_id or 'task_dashboard'}.json"  # type: ignore[attr-defined]
    httpd.session_binding_store = session_binding_store  # type: ignore[attr-defined]
    httpd.http_log = Path(args.http_log).resolve()  # type: ignore[attr-defined]
    httpd.project_scheduler_runtime = ProjectSchedulerRuntimeRegistry(store=store, session_store=session_store)  # type: ignore[attr-defined]
    httpd.task_push_runtime = TaskPushRuntimeRegistry(store=store, session_store=session_store)  # type: ignore[attr-defined]
    httpd.task_plan_runtime = TaskPlanRuntimeRegistry(  # type: ignore[attr-defined]
        store=store,
        session_store=session_store,
        task_push_runtime=httpd.task_push_runtime,
    )
    httpd.heartbeat_task_runtime = HeartbeatTaskRuntimeRegistry(  # type: ignore[attr-defined]
        store=store,
        session_store=session_store,
        task_push_runtime=httpd.task_push_runtime,
    )
    httpd.assist_request_runtime = AssistRequestRuntimeRegistry(store=store, session_store=session_store)  # type: ignore[attr-defined]
    httpd.session_health_runtime = SessionHealthRuntimeRegistry(  # type: ignore[attr-defined]
        store=store,
        environment_name=environment_name,
        build_payload=lambda project_id: _build_session_health_payload(
            project_id=project_id,
            session_store=session_store,
            store=store,
            environment_name=environment_name,
            worktree_root=Path(__file__).resolve().parent,
            heartbeat_runtime=httpd.heartbeat_task_runtime,
            load_session_heartbeat_config=_load_session_heartbeat_config,
            heartbeat_summary_payload=_heartbeat_summary_payload,
        ),
        config_loader=_load_dashboard_cfg_current,
    )
    # Scheduler enabled by default; can be disabled by: CCB_SCHEDULER=0
    max_cc, max_cc_source = _resolve_effective_max_concurrency()
    if max_cc_source == "config":
        print(f"[scheduler] using runtime.max_concurrency from config.toml: {max_cc}")
    elif max_cc_source == "env":
        print(f"[scheduler] using CCB_MAX_CONCURRENCY from env: {max_cc}")
    if str(os.environ.get("CCB_SCHEDULER") or "").strip() != "0":
        httpd.scheduler = RunScheduler(store=store, max_concurrency=max_cc)  # type: ignore[attr-defined]
        try:
            booted = bootstrap_queued_runs(store, httpd.scheduler, limit=600)  # type: ignore[arg-type]
            if booted:
                print(f"[scheduler] bootstrapped queued runs: {booted}")
        except Exception:
            pass
        try:
            resumed = bootstrap_restart_interrupted_runs(store, httpd.scheduler, limit=120)  # type: ignore[arg-type]
            if resumed:
                print(f"[scheduler] auto-resumed interrupted runs: {resumed}")
        except Exception:
            pass
    else:
        httpd.scheduler = None  # type: ignore[attr-defined]
        try:
            resumed = bootstrap_restart_interrupted_runs(store, None, limit=120)
            if resumed:
                print(f"[scheduler] auto-resumed interrupted runs (fallback): {resumed}")
        except Exception:
            pass
    try:
        httpd.task_push_runtime.set_scheduler(httpd.scheduler)  # type: ignore[attr-defined]
    except Exception:
        pass
    try:
        httpd.project_scheduler_runtime.set_scheduler(httpd.scheduler)  # type: ignore[attr-defined]
    except Exception:
        pass
    try:
        httpd.assist_request_runtime.set_scheduler(httpd.scheduler)  # type: ignore[attr-defined]
    except Exception:
        pass
    try:
        httpd.task_plan_runtime.start()  # type: ignore[attr-defined]
    except Exception as e:
        print(f"[task-plan] executor start failed: {e}")
    try:
        httpd.heartbeat_task_runtime.start()  # type: ignore[attr-defined]
    except Exception as e:
        print(f"[heartbeat-task] executor start failed: {e}")
    try:
        httpd.session_health_runtime.start()  # type: ignore[attr-defined]
    except Exception as e:
        print(f"[session-health] runtime start failed: {e}")

    try:
        httpd.project_scheduler_runtime.sync_enabled_projects_from_config()  # type: ignore[attr-defined]
    except Exception as e:
        print(f"[project-scheduler] bootstrap sync failed: {e}")
    try:
        httpd.heartbeat_task_runtime.tick_once()  # type: ignore[attr-defined]
    except Exception as e:
        print(f"[heartbeat-task] bootstrap sync failed: {e}")

    print(f"Serving static_root={static_root} on http://{args.bind}:{args.port}")
    httpd.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
