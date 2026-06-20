# -*- coding: utf-8 -*-

from __future__ import annotations

import json
import hashlib
import mimetypes
import os
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Optional

from task_dashboard.claude_permissions import (
    apply_claude_permission_mode_to_runner_command,
    normalize_claude_permission_mode,
)
from task_dashboard.adapters import CodexAdapter
from task_dashboard.codebuddy_permissions import (
    apply_codebuddy_permission_mode_to_runner_command,
    normalize_codebuddy_permission_mode,
)
from task_dashboard.runtime.execution_command import (
    build_execution_command as runtime_build_execution_command,
    prepare_process_spawn as runtime_prepare_process_spawn,
    write_execution_log_header as runtime_write_execution_log_header,
)
from task_dashboard.runtime.execution_context import (
    prepare_run_execution_context as runtime_prepare_run_execution_context,
)
from task_dashboard.runtime.execution_retry import (
    apply_network_retry_failure as runtime_apply_network_retry_failure,
    apply_profile_fallback_retry_result as runtime_apply_profile_fallback_retry_result,
)
from task_dashboard.runtime.execution_streams import (
    append_process_event as runtime_append_process_event,
    capture_agent_text as runtime_capture_agent_text,
    capture_auth_error as runtime_capture_auth_error,
    pump_process_stream as runtime_pump_process_stream,
    write_retry_process_output as runtime_write_retry_process_output,
)
from task_dashboard.runtime.execution_timeout import (
    detect_execution_timeout as runtime_detect_execution_timeout,
    terminate_process_for_timeout as runtime_terminate_process_for_timeout,
)
from task_dashboard.runtime.network_recovery import (
    apply_network_resume_schedule as runtime_apply_network_resume_schedule,
    build_network_resume_retry_meta as runtime_build_network_resume_retry_meta,
)
from task_dashboard.runtime.provider_failure import (
    apply_run_failure_classification as runtime_apply_run_failure_classification,
)
from task_dashboard.runtime.restart_recovery import (
    bootstrap_stale_queued_runs as runtime_bootstrap_stale_queued_runs,
    bootstrap_queued_runs as runtime_bootstrap_queued_runs,
    bootstrap_restart_interrupted_runs as runtime_bootstrap_restart_interrupted_runs,
    build_restart_resume_receipt_summary as runtime_build_restart_resume_receipt_summary,
    build_restart_resume_summary_message as runtime_build_restart_resume_summary_message,
    is_restart_recovery_pending_meta as runtime_is_restart_recovery_pending_meta,
    is_stale_queued_pending_meta as runtime_is_stale_queued_pending_meta,
    maybe_trigger_queued_recovery_lazy as runtime_maybe_trigger_queued_recovery_lazy,
    queued_recovery_lazy_interval_s as runtime_queued_recovery_lazy_interval_s,
    restart_recovery_lazy_interval_s as runtime_restart_recovery_lazy_interval_s,
)
from task_dashboard.runtime.run_detail_fields import (
    candidate_local_imagegen_files,
    extract_process_events_from_file,
    extract_terminal_message_from_file,
    latest_local_imagegen_mtime,
    reconcile_generated_media_for_run,
    refresh_generated_media_status,
    safe_terminal_visible_text,
)
from task_dashboard.session_store import SessionStore

__all__ = [
    "_RESTART_RECOVERY_LAZY_LAST_TS",
    "_RESTART_RECOVERY_LAZY_LOCK",
    "_QUEUED_RECOVERY_LAZY_LAST_TS",
    "_QUEUED_RECOVERY_LAZY_LOCK",
    "_build_restart_resume_receipt_summary",
    "_build_restart_resume_summary_message",
    "_is_restart_recovery_pending_meta",
    "_is_stale_queued_pending_meta",
    "_maybe_trigger_queued_recovery_lazy",
    "_maybe_trigger_restart_recovery_lazy",
    "_queued_recovery_lazy_interval_s",
    "_restart_recovery_lazy_interval_s",
    "_schedule_network_resume_run",
    "_schedule_provider_auto_retry_run",
    "_schedule_retry_waiting_fallback",
    "bootstrap_stale_queued_runs",
    "bootstrap_queued_runs",
    "bootstrap_restart_interrupted_runs",
    "run_cli_exec",
    "run_codex_exec",
]


_TERMINAL_TEXT_CLIS = {"claude", "opencode", "gemini", "codebuddy"}
_TERMINAL_TEXT_PROCESS_CLEAR_CLIS = {"opencode", "gemini"}


def _harvest_terminal_final_text(last_path: Path, log_path: Path, *, cli_type: str) -> str:
    cli = str(cli_type or "").strip().lower()
    try:
        last = last_path.read_text(encoding="utf-8", errors="replace")
        last = safe_terminal_visible_text(last, cli_type=cli)
    except Exception:
        last = ""
    if str(last or "").strip():
        return last.replace("\r\n", "\n").strip()
    try:
        last = extract_terminal_message_from_file(log_path, cli_type=cli)
        last = safe_terminal_visible_text(last, cli_type=cli)
    except Exception:
        last = ""
    return last.replace("\r\n", "\n").strip() if str(last or "").strip() else ""


def __getattr__(name: str):
    import server

    try:
        return getattr(server, name)
    except AttributeError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc


def _server_override(name: str, local_fn: Any = None) -> Any:
    import server

    override = getattr(server, name, None)
    if override is None:
        return local_fn
    if local_fn is not None and override is local_fn:
        return local_fn
    return override


def _safe_text(value: Any, max_len: int = 200) -> str:
    return __getattr__("_safe_text")(value, max_len)


def _now_iso() -> str:
    return __getattr__("_now_iso")()


def _parse_iso_ts(value: Any) -> float:
    return __getattr__("_parse_iso_ts")(value)


def _iso_after_s(seconds: int) -> str:
    return __getattr__("_iso_after_s")(seconds)


def _build_callback_context_message(meta: dict[str, Any], original_message: str) -> str:
    row = meta if isinstance(meta, dict) else {}
    trigger_type = str(row.get("trigger_type") or "").strip().lower()
    if trigger_type not in {"callback_auto", "callback_auto_summary"}:
        return str(original_message or "")
    summary = row.get("receipt_summary")
    if not isinstance(summary, dict) or not summary:
        return str(original_message or "")

    source_channel = str(summary.get("source_channel") or "").strip() or "未知通道"
    callback_task = str(summary.get("callback_task") or "").strip() or "未关联任务"
    stage = str(summary.get("execution_stage") or "").strip() or "推进"
    conclusion = str(summary.get("conclusion") or "").strip() or "需处理"
    progress = str(summary.get("progress") or "").strip() or "系统回执已生成。"
    need_peer = str(summary.get("need_peer") or "").strip() or "请主负责确认下一步动作。"
    need_confirm = str(summary.get("need_confirm") or "").strip() or "无"

    lines = [
        f"[来源通道: {source_channel}]",
        f"回执任务: {callback_task}",
        f"执行阶段: {stage}",
        f"当前结论: {conclusion}",
        f"目标进展: {progress}",
        f"需要对方: {need_peer}",
        f"需确认: {need_confirm}",
        "",
        "说明: 这是系统回执的上下文摘要。完整技术明细仍保留在当前 run 详情、结构化字段和日志中；除非存在明确待办，不要把这条回执当成新的协作任务逐条回复。",
    ]
    if bool(summary.get("late_callback")):
        lines.append("补充说明: 该回执已按迟到留痕口径处理。")
    return "\n".join(lines)


_D24_CODEX_IMAGE_CONTENT_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}
_D24_CODEX_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


def _runtime_attachment_values(raw: Any) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                values.append(item)
    return values


def _nested_runtime_attachments(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, dict):
        return []
    out: list[dict[str, Any]] = []
    out.extend(_runtime_attachment_values(raw.get("attachments")))
    runtime_input = raw.get("runtime_input") if isinstance(raw.get("runtime_input"), dict) else raw.get("runtimeInput")
    if isinstance(runtime_input, dict):
        out.extend(_runtime_attachment_values(runtime_input.get("attachments")))
    adapter_input = raw.get("adapter_input") if isinstance(raw.get("adapter_input"), dict) else raw.get("adapterInput")
    if isinstance(adapter_input, dict):
        out.extend(_nested_runtime_attachments(adapter_input))
    queue_job = raw.get("queue_job") if isinstance(raw.get("queue_job"), dict) else raw.get("queueJob")
    if isinstance(queue_job, dict):
        out.extend(_nested_runtime_attachments(queue_job))
    task_envelope = raw.get("task_envelope") if isinstance(raw.get("task_envelope"), dict) else raw.get("taskEnvelope")
    if isinstance(task_envelope, dict):
        out.extend(_nested_runtime_attachments(task_envelope))
    return out


def _attachment_identity_keys(attachment: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    for key in (
        "attachment_id",
        "attachmentId",
        "id",
        "localId",
        "local_id",
        "message_part_id",
        "messagePartId",
        "url",
        "path",
        "localPath",
        "local_path",
        "resolved_local_path",
        "file_path",
        "filename",
        "originalName",
    ):
        value = str(attachment.get(key) or "").strip()
        if value:
            keys.add(f"{key}:{value}")
            if key in {"url", "path", "localPath", "local_path", "resolved_local_path", "file_path"}:
                keys.add(value)
    return keys


def _controlled_attachment_roots(runs_root: Path) -> list[Path]:
    roots: list[Path] = []
    for raw in (
        runs_root,
        runs_root.parent,
        Path(tempfile.gettempdir()) / "task-dashboard-codex-runner",
    ):
        try:
            roots.append(Path(raw).resolve())
        except Exception:
            continue
    return roots


def _path_is_under_any(path: Path, roots: list[Path]) -> bool:
    try:
        resolved = path.resolve()
    except Exception:
        return False
    for root in roots:
        try:
            resolved.relative_to(root)
            return True
        except Exception:
            continue
    return False


def _resolve_runtime_attachment_path(runs_root: Path, attachment: dict[str, Any]) -> Path | None:
    roots = _controlled_attachment_roots(runs_root)
    for key in ("resolved_local_path", "local_path", "localPath", "path", "file_path"):
        raw = str(attachment.get(key) or "").strip()
        if not raw:
            continue
        try:
            candidate = Path(raw).expanduser().resolve()
        except Exception:
            continue
        if candidate.exists() and candidate.is_file() and os.access(candidate, os.R_OK) and _path_is_under_any(candidate, roots):
            return candidate
    try:
        resolver = __getattr__("_resolve_attachment_local_path")
        resolved = resolver(runs_root, attachment)
        if resolved is not None:
            candidate = Path(resolved).resolve()
            if candidate.exists() and candidate.is_file() and os.access(candidate, os.R_OK):
                return candidate
    except Exception:
        pass
    return None


def _runtime_attachment_content_type(attachment: dict[str, Any], path: Path) -> str:
    content_type = str(
        attachment.get("content_type")
        or attachment.get("contentType")
        or attachment.get("mimeType")
        or attachment.get("mime_type")
        or ""
    ).strip().lower()
    if content_type == "image/jpg":
        return "image/jpeg"
    if content_type:
        return content_type
    guessed, _ = mimetypes.guess_type(str(path))
    return str(guessed or "").strip().lower()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _resolve_runtime_image_attachments(meta: dict[str, Any], runs_root: Path) -> list[dict[str, Any]]:
    raw_items = _nested_runtime_attachments(meta)
    out: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    max_bytes_raw = str(os.environ.get("TASK_DASHBOARD_CODEX_IMAGE_MAX_BYTES") or "").strip()
    try:
        max_bytes = int(max_bytes_raw) if max_bytes_raw else 25 * 1024 * 1024
    except Exception:
        max_bytes = 25 * 1024 * 1024
    for item in raw_items:
        path = _resolve_runtime_attachment_path(runs_root, item)
        if path is None:
            continue
        path_key = str(path)
        if path_key in seen_paths:
            continue
        content_type = _runtime_attachment_content_type(item, path)
        kind = str(item.get("kind") or item.get("attachment_kind") or "").strip().lower()
        if kind and kind != "image":
            continue
        if content_type not in _D24_CODEX_IMAGE_CONTENT_TYPES:
            continue
        if path.suffix.lower() not in _D24_CODEX_IMAGE_EXTENSIONS:
            continue
        try:
            size_bytes = int(path.stat().st_size)
        except Exception:
            size_bytes = int(item.get("size_bytes") or item.get("size") or 0)
        if size_bytes <= 0 or size_bytes > max_bytes:
            continue
        sha256 = str(item.get("sha256") or item.get("hash") or "").strip()
        if not sha256:
            try:
                sha256 = _sha256_file(path)
            except Exception:
                sha256 = ""
        seen_paths.add(path_key)
        out.append(
            {
                "attachment_id": str(
                    item.get("attachment_id") or item.get("attachmentId") or item.get("id") or item.get("localId") or ""
                ).strip(),
                "message_part_id": str(item.get("message_part_id") or item.get("messagePartId") or "").strip(),
                "filename": str(item.get("filename") or item.get("originalName") or path.name).strip() or path.name,
                "kind": "image",
                "content_type": content_type,
                "size_bytes": size_bytes,
                "sha256": sha256,
                "source": str(item.get("source") or "message_attachment").strip() or "message_attachment",
                "runtime_passthrough": True,
                "adapter_arg_kind": "codex_image_flag",
                "resolved_local_path": path_key,
                "_source_keys": sorted(_attachment_identity_keys(item)),
            }
        )
    return out


def _metadata_without_runtime_passthrough_attachments(
    meta: dict[str, Any],
    runtime_attachments: list[dict[str, Any]],
) -> dict[str, Any]:
    if not runtime_attachments:
        return meta
    exclude_keys: set[str] = set()
    for item in runtime_attachments:
        raw_keys = item.get("_source_keys")
        if isinstance(raw_keys, list):
            exclude_keys.update(str(key) for key in raw_keys if str(key or "").strip())
    if not exclude_keys:
        return meta
    attachments = meta.get("attachments") if isinstance(meta.get("attachments"), list) else []
    filtered: list[Any] = []
    changed = False
    for item in attachments:
        if isinstance(item, dict) and _attachment_identity_keys(item) & exclude_keys:
            changed = True
            continue
        filtered.append(item)
    if not changed:
        return meta
    updated = dict(meta)
    updated["attachments"] = filtered
    return updated


def _count_codex_image_args(cmd: list[str]) -> int:
    count = 0
    for token in list(cmd or []):
        text = str(token or "")
        if text in {"-i", "--image"} or text.startswith("--image="):
            count += 1
    return count


def _safe_prompt_line(value: Any) -> str:
    return str(value or "").replace("\r", " ").replace("\n", " ").strip()


def _build_claude_image_path_fallback_prompt(runtime_attachments: list[dict[str, Any]]) -> str:
    image_lines: list[str] = []
    for index, item in enumerate(runtime_attachments if isinstance(runtime_attachments, list) else [], start=1):
        if not isinstance(item, dict):
            continue
        path = _safe_prompt_line(item.get("resolved_local_path"))
        if not path:
            continue
        filename = _safe_prompt_line(item.get("filename")) or Path(path).name
        content_type = _safe_prompt_line(item.get("content_type")) or "image"
        image_lines.append(f"{index}. {filename} ({content_type}): {path}")
    if not image_lines:
        return ""
    return "\n\n".join(
        [
            "",
            "[CCB 图片附件读取提示]",
            "本次消息包含图片附件。Claude Code 未使用原生图片参数，CCB 已提供本机绝对路径兜底。",
            "请优先使用 Read/读取工具打开以下图片文件，基于图片内容作答；不要只根据文件名或路径猜测。",
            "\n".join(image_lines),
            "[/CCB 图片附件读取提示]",
        ]
    )


def _build_claude_image_path_fallback_summary(runtime_attachments: list[dict[str, Any]]) -> dict[str, Any]:
    count = 0
    public_attachments: list[dict[str, Any]] = []
    for item in runtime_attachments if isinstance(runtime_attachments, list) else []:
        if not isinstance(item, dict):
            continue
        if not str(item.get("resolved_local_path") or "").strip():
            continue
        count += 1
        public_attachments.append(
            {
                "attachment_id": str(item.get("attachment_id") or "").strip(),
                "message_part_id": str(item.get("message_part_id") or "").strip(),
                "filename": str(item.get("filename") or "").strip(),
                "content_type": str(item.get("content_type") or "").strip(),
                "size_bytes": int(item.get("size_bytes") or 0),
                "sha256": str(item.get("sha256") or "").strip(),
                "runtime_passthrough": True,
                "path_redacted": True,
            }
        )
    return {
        "enabled": bool(count),
        "image_count": count,
        "adapter_arg_kind": "claude_prompt_path_fallback" if count else "",
        "prompt_contains_absolute_paths": bool(count),
        "requires_read_tool": bool(count),
        "attachments": public_attachments,
        "path_redacted": True,
    }


def _build_runtime_attachment_summary(
    runtime_attachments: list[dict[str, Any]],
    *,
    adapter_image_arg_count: int,
    actual_cli_invoked: bool,
) -> dict[str, Any]:
    public_attachments: list[dict[str, Any]] = []
    for item in runtime_attachments:
        public_attachments.append(
            {
                "attachment_id": str(item.get("attachment_id") or "").strip(),
                "message_part_id": str(item.get("message_part_id") or "").strip(),
                "filename": str(item.get("filename") or "").strip(),
                "content_type": str(item.get("content_type") or "").strip(),
                "size_bytes": int(item.get("size_bytes") or 0),
                "sha256": str(item.get("sha256") or "").strip(),
                "runtime_passthrough": True,
                "path_redacted": True,
            }
        )
    image_count = len(public_attachments)
    arg_count = int(adapter_image_arg_count or 0)
    return {
        "image_passed": bool(actual_cli_invoked and image_count > 0 and arg_count >= image_count),
        "image_count": image_count,
        "adapter_image_arg_count": arg_count,
        "adapter_arg_kind": "codex_image_flag" if image_count else "",
        "attachments": public_attachments,
        "path_redacted": True,
    }


def _restart_recovery_run_cli_exec(*args, **kwargs):
    fn = _server_override("run_cli_exec", run_cli_exec)
    return fn(*args, **kwargs)


def bootstrap_queued_runs(store, scheduler, *, limit: int = 400) -> int:
    return runtime_bootstrap_queued_runs(
        store,
        scheduler,
        parse_iso_ts=_parse_iso_ts,
        now_iso=_now_iso,
        limit=limit,
    )


def _build_restart_resume_summary_message(
    *,
    base_message: str,
    source_run_ids: list[str],
    max_preview: int = 8,
) -> str:
    return runtime_build_restart_resume_summary_message(
        base_message=base_message,
        source_run_ids=source_run_ids,
        render_receipt_summary_message=__getattr__("_render_receipt_summary_message"),
        max_preview=max_preview,
    )


def _build_restart_resume_receipt_summary(
    *,
    base_message: str,
    source_run_ids: list[str],
    max_preview: int = 8,
) -> dict[str, Any]:
    return runtime_build_restart_resume_receipt_summary(
        base_message=base_message,
        source_run_ids=source_run_ids,
        max_preview=max_preview,
    )


def bootstrap_restart_interrupted_runs(
    store,
    scheduler=None,
    *,
    limit: int = 80,
    now_ts: Optional[float] = None,
    window_s: Optional[int] = None,
) -> int:
    return runtime_bootstrap_restart_interrupted_runs(
        store,
        scheduler=scheduler,
        parse_iso_ts=_parse_iso_ts,
        now_iso=_now_iso,
        default_restart_resume_window_s=__getattr__("_default_restart_resume_window_s"),
        default_restart_resume_message=__getattr__("_default_restart_resume_message"),
        run_process_alive=__getattr__("_run_process_alive"),
        build_restart_resume_receipt_summary=_build_restart_resume_receipt_summary,
        build_restart_resume_summary_message=_build_restart_resume_summary_message,
        run_cli_exec=_restart_recovery_run_cli_exec,
        limit=limit,
        now_ts=now_ts,
        window_s=window_s,
    )


_RESTART_RECOVERY_LAZY_LOCK = threading.Lock()
_RESTART_RECOVERY_LAZY_LAST_TS: dict[str, float] = {}
_QUEUED_RECOVERY_LAZY_LOCK = threading.Lock()
_QUEUED_RECOVERY_LAZY_LAST_TS: dict[str, float] = {}


def _restart_recovery_lazy_interval_s() -> float:
    return runtime_restart_recovery_lazy_interval_s()


def _is_restart_recovery_pending_meta(meta: dict[str, Any]) -> bool:
    return runtime_is_restart_recovery_pending_meta(meta)


def _queued_recovery_lazy_interval_s() -> float:
    return runtime_queued_recovery_lazy_interval_s()


def _is_stale_queued_pending_meta(meta: dict[str, Any]) -> bool:
    return runtime_is_stale_queued_pending_meta(meta, parse_iso_ts=_parse_iso_ts)


def _maybe_trigger_restart_recovery_lazy(
    store,
    scheduler,
    metas: list[dict[str, Any]],
    *,
    project_id_hint: str = "",
) -> int:
    rows = [meta for meta in metas if _is_restart_recovery_pending_meta(meta)]
    if not rows:
        return 0
    project_id = str(project_id_hint or "").strip()
    if not project_id:
        project_id = str(rows[0].get("projectId") or "").strip()
    key = project_id or "__global__"
    interval_s = _restart_recovery_lazy_interval_s()
    now_ts = time.time()
    if interval_s > 0:
        with _RESTART_RECOVERY_LAZY_LOCK:
            last = float(_RESTART_RECOVERY_LAZY_LAST_TS.get(key) or 0.0)
            if last > 0 and (now_ts - last) < interval_s:
                return 0
            _RESTART_RECOVERY_LAZY_LAST_TS[key] = now_ts
    resumed = bootstrap_restart_interrupted_runs(store, scheduler, limit=120, now_ts=now_ts)
    return int(resumed or 0)


def bootstrap_stale_queued_runs(
    store,
    scheduler,
    *,
    limit: int = 120,
    now_ts: Optional[float] = None,
    stale_after_s: Optional[float] = None,
    metas: list[dict[str, Any]] | None = None,
) -> int:
    return runtime_bootstrap_stale_queued_runs(
        store,
        scheduler,
        parse_iso_ts=_parse_iso_ts,
        limit=limit,
        now_ts=now_ts,
        stale_after_s=stale_after_s,
        metas=metas,
    )


def _maybe_trigger_queued_recovery_lazy(
    store,
    scheduler,
    metas: list[dict[str, Any]],
    *,
    project_id_hint: str = "",
) -> int:
    return runtime_maybe_trigger_queued_recovery_lazy(
        store,
        scheduler,
        metas,
        parse_iso_ts=_parse_iso_ts,
        bootstrap_stale_queued_runs_fn=bootstrap_stale_queued_runs,
        project_id_hint=project_id_hint,
    )


def _schedule_retry_waiting_fallback(
    store,
    run_id: str,
    session_id: str,
    cli_type: str,
    due_ts: float,
) -> None:
    rid = str(run_id or "").strip()
    sid = str(session_id or "").strip()
    cli_t = str(cli_type or "codex").strip() or "codex"
    if not rid or not sid:
        return

    def _worker() -> None:
        wait_s = max(0.0, float(due_ts or 0.0) - time.time())
        if wait_s > 0:
            time.sleep(wait_s)
        meta = store.load_meta(rid) or {}
        if not meta:
            return
        if bool(meta.get("hidden")):
            return
        status = str(meta.get("status") or "").strip().lower()
        if status != "retry_waiting":
            return
        meta["status"] = "queued"
        meta["retryActivatedAt"] = _now_iso()
        store.save_meta(rid, meta)
        _restart_recovery_run_cli_exec(store, rid, cli_type=cli_t, scheduler=None)

    threading.Thread(target=_worker, daemon=True).start()


def _schedule_network_resume_run(
    store,
    source_meta: dict[str, Any],
    *,
    scheduler,
    cli_type: str,
) -> str:
    if not isinstance(source_meta, dict):
        return ""
    if bool(source_meta.get("autoResumePrompt")):
        return ""
    source_id = str(source_meta.get("id") or "").strip()
    project_id = str(source_meta.get("projectId") or "").strip()
    channel_name = str(source_meta.get("channelName") or "").strip()
    session_id = str(source_meta.get("sessionId") or "").strip()
    if not source_id or not project_id or not channel_name or not session_id:
        return ""

    delay_s = __getattr__("_default_network_resume_delay_s")()
    message = __getattr__("_default_network_resume_message")()
    due_ts = time.time() + float(delay_s)
    retry_run = store.create_run(
        project_id,
        channel_name,
        session_id,
        message,
        profile_label=str(source_meta.get("profileLabel") or ""),
        model=str(source_meta.get("model") or "").strip(),
        cli_type=cli_type,
        attachments=None,
        sender_type="system",
        sender_id="ccb",
        sender_name="CCB Runtime",
        extra_meta={"trigger_type": "network_auto_resume"},
    )
    retry_id = str(retry_run.get("id") or "").strip()
    if not retry_id:
        return ""

    retry_meta = runtime_build_network_resume_retry_meta(
        store.load_meta(retry_id) or retry_run,
        source_id=source_id,
        delay_s=delay_s,
        message=message,
        iso_after_s=_iso_after_s,
    )
    store.save_meta(retry_id, retry_meta)

    if scheduler is not None and str(os.environ.get("CCB_SCHEDULER") or "").strip() != "0":
        scheduler.schedule_retry_waiting(retry_id, session_id, due_ts, cli_type=cli_type)
    else:
        _schedule_retry_waiting_fallback(store, retry_id, session_id, cli_type, due_ts)
    return retry_id


def _default_provider_auto_retry_delay_s() -> int:
    raw = str(os.environ.get("CCB_PROVIDER_RETRY_DELAY_S") or "").strip()
    if raw:
        try:
            value = int(float(raw))
            if value >= 0:
                return min(value, 3600)
        except Exception:
            pass
    return 60


def _default_provider_auto_retry_max_attempts() -> int:
    raw = str(os.environ.get("CCB_PROVIDER_RETRY_MAX") or "").strip()
    if raw:
        try:
            value = int(float(raw))
            if value >= 0:
                return min(value, 2)
        except Exception:
            pass
    return 2


def _meta_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() not in {"", "0", "false", "none", "null", "no", "off"}


def _provider_retry_root_id(meta: dict[str, Any]) -> str:
    return str(meta.get("retry_of") or meta.get("retryOf") or meta.get("id") or "").strip()


def _provider_retry_current_attempt(meta: dict[str, Any]) -> int:
    try:
        return max(0, int(meta.get("retry_attempt") or meta.get("retryAttempt") or 0))
    except Exception:
        return 0


def _provider_retry_reason(meta: dict[str, Any]) -> str:
    provider_error = meta.get("provider_error") if isinstance(meta.get("provider_error"), dict) else {}
    kind = str(provider_error.get("kind") or "").strip().lower()
    return f"provider_{kind}" if kind else "provider_transient"


def _provider_auto_retry_eligible(meta: dict[str, Any], *, max_attempts: int) -> tuple[bool, str]:
    if not isinstance(meta, dict):
        return False, "invalid_meta"
    if str(meta.get("status") or "").strip().lower() != "error":
        return False, "not_error"
    if str(meta.get("failure_class") or "").strip().lower() != "provider_transient":
        return False, "not_provider_transient"
    provider_error = meta.get("provider_error") if isinstance(meta.get("provider_error"), dict) else {}
    if not bool(provider_error.get("retryable")):
        return False, "provider_error_not_retryable"
    if str(meta.get("side_effect_risk") or "").strip().lower() != "none":
        return False, f"side_effect_risk_{str(meta.get('side_effect_risk') or 'unknown').strip().lower()}"
    if str(meta.get("recovery_mode") or "").strip().lower() != "auto_retry":
        return False, "recovery_mode_not_auto_retry"
    if not _meta_bool(meta.get("auto_retry_eligible")):
        return False, "auto_retry_eligible_false"
    if _meta_bool(meta.get("recovery_required")):
        return False, "recovery_required"
    if _meta_bool(meta.get("hidden")):
        return False, "hidden_run"
    if _meta_bool(meta.get("autoResumePrompt")):
        return False, "network_resume_prompt"
    if str(meta.get("networkResumeRunId") or meta.get("network_resume_run_id") or "").strip():
        return False, "network_resume_already_scheduled"
    if _meta_bool(meta.get("visible_in_channel_chat")) or _meta_bool(meta.get("visibleInChannelChat")):
        return False, "visible_in_channel_chat"
    if str(meta.get("providerRetryRunId") or meta.get("provider_auto_retry_run_id") or "").strip():
        return False, "provider_retry_already_scheduled"
    if _meta_bool(meta.get("retry_exhausted")) or _meta_bool(meta.get("retryExhausted")):
        return False, "retry_exhausted"
    if max_attempts <= 0:
        return False, "provider_retry_disabled"
    if _provider_retry_current_attempt(meta) >= max_attempts:
        return False, "retry_exhausted"
    return True, "provider_transient_low_risk"


def _provider_retry_read_message(store, meta: dict[str, Any], *, fallback_meta: Optional[dict[str, Any]] = None) -> str:
    rows = [meta]
    if isinstance(fallback_meta, dict) and fallback_meta is not meta:
        rows.append(fallback_meta)
    for row in rows:
        paths = row.get("paths") if isinstance(row.get("paths"), dict) else {}
        msg_path = str(paths.get("msg") or "").strip()
        if msg_path:
            try:
                text = Path(msg_path).read_text(encoding="utf-8", errors="replace")
                if text.strip():
                    return text
            except Exception:
                pass
        rid = str(row.get("id") or "").strip()
        if rid and hasattr(store, "_paths"):
            try:
                text = store._paths(rid)["msg"].read_text(encoding="utf-8", errors="replace")
                if text.strip():
                    return text
            except Exception:
                pass
    return str(meta.get("messagePreview") or fallback_meta.get("messagePreview") if isinstance(fallback_meta, dict) else "").strip()


_PROVIDER_RETRY_EXTRA_META_KEYS = (
    "source_ref",
    "target_ref",
    "callback_to",
    "owner_ref",
    "sender_agent_ref",
    "mention_targets",
    "reply_to_run_id",
    "replyToRunId",
    "reply_to",
    "replyTo",
    "task_path",
    "execution_mode",
    "topic",
    "task_id",
    "owner_channel_name",
    "execution_stage",
    "current_conclusion",
    "need_confirmation",
    "next_action",
    "blocking_status",
    "message_kind",
    "interaction_mode",
    "plan_first",
    "plan_phase",
    "plan_prompt_version",
    "task_with_receipt_guard_version",
    "localServerOrigin",
    "environment",
    "worktree_root",
    "workdir",
    "branch",
    "project_execution_context",
    "codebuddy_permission_mode",
    "claude_permission_mode",
)


def _provider_retry_extra_meta(source_meta: dict[str, Any]) -> dict[str, Any]:
    extra: dict[str, Any] = {}
    for key in _PROVIDER_RETRY_EXTRA_META_KEYS:
        if key in source_meta:
            extra[key] = source_meta.get(key)
    # Provider retry is an internal retry run. Keep source/callback context but
    # do not mark the retry artifact as a newly announced channel message.
    extra["visible_in_channel_chat"] = False
    extra["trigger_type"] = "provider_auto_retry"
    return extra


def _mark_provider_retry_exhausted(meta: dict[str, Any], *, max_attempts: int, reason: str = "retry_exhausted") -> None:
    meta["providerRetryExhausted"] = True
    meta["retry_exhausted"] = True
    meta["retryExhaustedAt"] = _now_iso()
    meta["providerRetryMaxAttempts"] = int(max_attempts)
    meta["auto_retry_eligible"] = False
    meta["retry_eligibility_reason"] = reason
    meta["recovery_mode"] = "manual_recovery"
    meta["recovery_required"] = True


def _schedule_provider_auto_retry_run(
    store,
    source_meta: dict[str, Any],
    *,
    scheduler,
    cli_type: str,
) -> str:
    if not isinstance(source_meta, dict):
        return ""
    source_id = str(source_meta.get("id") or "").strip()
    project_id = str(source_meta.get("projectId") or "").strip()
    channel_name = str(source_meta.get("channelName") or "").strip()
    session_id = str(source_meta.get("sessionId") or "").strip()
    if not source_id or not project_id or not channel_name or not session_id:
        return ""

    max_attempts = _default_provider_auto_retry_max_attempts()
    eligible, reason = _provider_auto_retry_eligible(source_meta, max_attempts=max_attempts)
    if not eligible:
        if reason == "retry_exhausted":
            _mark_provider_retry_exhausted(source_meta, max_attempts=max_attempts)
        return ""

    root_id = _provider_retry_root_id(source_meta) or source_id
    root_meta = store.load_meta(root_id) if root_id != source_id and hasattr(store, "load_meta") else None
    if not isinstance(root_meta, dict) or not root_meta:
        root_meta = source_meta
    next_attempt = _provider_retry_current_attempt(source_meta) + 1
    if next_attempt > max_attempts:
        _mark_provider_retry_exhausted(source_meta, max_attempts=max_attempts)
        return ""

    message = _provider_retry_read_message(store, root_meta, fallback_meta=source_meta)
    if not str(message or "").strip():
        source_meta["auto_retry_eligible"] = False
        source_meta["retry_eligibility_reason"] = "missing_original_message"
        source_meta["recovery_mode"] = "manual_recovery"
        source_meta["recovery_required"] = True
        return ""

    delay_s = _default_provider_auto_retry_delay_s()
    due_ts = time.time() + float(delay_s)
    reason_text = _provider_retry_reason(source_meta)
    base_meta = root_meta if isinstance(root_meta, dict) and root_meta else source_meta
    retry_run = store.create_run(
        project_id,
        channel_name,
        session_id,
        message,
        profile_label=str(base_meta.get("profileLabel") or ""),
        model=str(base_meta.get("model") or "").strip(),
        cli_type=cli_type,
        attachments=list(base_meta.get("attachments") or []) if isinstance(base_meta.get("attachments"), list) else None,
        sender_type=str(base_meta.get("sender_type") or "system").strip() or "system",
        sender_id=str(base_meta.get("sender_id") or "ccb").strip() or "ccb",
        sender_name=str(base_meta.get("sender_name") or "CCB Runtime").strip() or "CCB Runtime",
        extra_meta=_provider_retry_extra_meta(base_meta),
        reasoning_effort=str(base_meta.get("reasoning_effort") or "").strip(),
    )
    retry_id = str(retry_run.get("id") or "").strip()
    if not retry_id:
        return ""

    retry_meta = dict(store.load_meta(retry_id) or retry_run)
    retry_meta.update(
        {
            "status": "retry_waiting",
            "retry_of": root_id,
            "retryOf": root_id,
            "retry_parent_run_id": source_id,
            "retry_attempt": next_attempt,
            "retryAttempt": next_attempt,
            "retry_reason": reason_text,
            "retryReason": reason_text,
            "retryKind": "provider_transient_auto_retry",
            "retry_kind": "provider_transient_auto_retry",
            "retryDelaySeconds": int(delay_s),
            "retryScheduledAt": _iso_after_s(int(delay_s)),
            "retryCancelable": True,
            "provider_auto_retry": True,
            "providerRetryMaxAttempts": int(max_attempts),
            "side_effect_risk": "none",
            "recovery_mode": "auto_retry",
            "auto_retry_eligible": True,
            "retry_eligibility_reason": "provider_transient_no_side_effect_evidence",
            "provider_error": dict(source_meta.get("provider_error") or {})
            if isinstance(source_meta.get("provider_error"), dict)
            else {},
        }
    )
    store.save_meta(retry_id, retry_meta)

    source_meta["providerRetryRunId"] = retry_id
    source_meta["providerRetryScheduledAt"] = _iso_after_s(int(delay_s))
    source_meta["providerRetryAttempt"] = next_attempt
    source_meta["providerRetryMaxAttempts"] = int(max_attempts)
    source_meta["providerRetryReason"] = reason_text
    source_meta["superseded_by"] = retry_id
    source_meta["superseded_by_run_id"] = retry_id
    source_meta["retry_status"] = "retry_waiting"

    if scheduler is not None and str(os.environ.get("CCB_SCHEDULER") or "").strip() != "0":
        scheduler.schedule_retry_waiting(retry_id, session_id, due_ts, cli_type=cli_type)
    else:
        _schedule_retry_waiting_fallback(store, retry_id, session_id, cli_type, due_ts)
    return retry_id


def run_codex_exec(store, run_id: str, timeout_s: Optional[int] = None) -> None:
    run_cli_exec(store, run_id, timeout_s=timeout_s, cli_type="codex")


def run_cli_exec(
    store,
    run_id: str,
    timeout_s: Optional[int] = None,
    cli_type: str = "codex",
    scheduler=None,
) -> None:
    if timeout_s is None:
        timeout_s = __getattr__("_default_run_timeout_s")()
    timeout_enabled = bool(timeout_s and timeout_s > 0)
    timeout_value = int(timeout_s) if timeout_enabled else 0
    no_progress_timeout_s = __getattr__("_default_run_no_progress_timeout_s")(cli_type=cli_type)
    if no_progress_timeout_s and timeout_enabled:
        no_progress_timeout_s = min(int(no_progress_timeout_s), timeout_value)
    no_progress_enabled = bool(no_progress_timeout_s and no_progress_timeout_s > 0)
    no_progress_value = int(no_progress_timeout_s) if no_progress_enabled else 0

    adapter_cls = __getattr__("get_adapter")(cli_type) or CodexAdapter
    network_retry_max = __getattr__("_default_network_retry_max")()
    network_retry_base_s = __getattr__("_default_network_retry_base_s")()

    meta = store.load_meta(run_id) or {}
    if not meta:
        return
    if bool(meta.get("hidden")):
        return
    paths = meta.get("paths") or {}
    msg_path = Path(str(paths.get("msg") or ""))
    last_path = Path(str(paths.get("last") or ""))
    log_path = Path(str(paths.get("log") or ""))

    message = ""
    try:
        message = msg_path.read_text(encoding="utf-8")
    except Exception:
        pass

    runtime_image_attachments = _resolve_runtime_image_attachments(meta, store.runs_dir)
    prompt_meta = _metadata_without_runtime_passthrough_attachments(meta, runtime_image_attachments)
    attachment_block = __getattr__("_build_attachment_prompt_block")(prompt_meta, store.runs_dir)
    if attachment_block:
        message = message + attachment_block
    message = _build_callback_context_message(meta, message)
    claude_image_path_fallback = ""
    if str(cli_type or "").strip().lower() == "claude" and runtime_image_attachments:
        claude_image_path_fallback = _build_claude_image_path_fallback_prompt(runtime_image_attachments)
        if claude_image_path_fallback:
            message = message + claude_image_path_fallback

    meta["status"] = "running"
    meta["startedAt"] = _now_iso()
    meta["cliType"] = cli_type
    meta["lastProgressAt"] = _now_iso()
    try:
        refresh_generated_media_status(meta, extra_texts=[message])
    except Exception:
        pass
    prepared = runtime_prepare_run_execution_context(
        meta,
        cli_type=cli_type,
        runs_parent=store.runs_dir.parent,
        worktree_root=Path(__file__).resolve().parent.parent.parent,
        normalize_reasoning_effort=__getattr__("_normalize_reasoning_effort"),
        session_store_cls=SessionStore,
        derive_session_work_context=__getattr__("_derive_session_work_context"),
        resolve_model_for_session=__getattr__("_resolve_model_for_session"),
        resolve_reasoning_effort_for_session=__getattr__("_resolve_reasoning_effort_for_session"),
        resolve_run_work_context=__getattr__("_resolve_run_work_context"),
        load_project_execution_context=__getattr__("_load_project_execution_context"),
        resolve_project_workdir=__getattr__("_resolve_project_workdir"),
        resolve_channel_workdir=__getattr__("_resolve_channel_workdir"),
        project_channel_model=__getattr__("_project_channel_model"),
        project_channel_reasoning_effort=__getattr__("_project_channel_reasoning_effort"),
    )
    meta = dict(prepared.get("meta") or meta)
    project_id = str(prepared.get("project_id") or "")
    session_id = str(prepared.get("session_id") or "")
    profile_label = str(prepared.get("profile_label") or "")
    execution_profile = (
        str(prepared.get("execution_profile") or meta.get("execution_profile") or "sandboxed").strip().lower()
        or "sandboxed"
    )
    run_cwd = Path(prepared.get("run_cwd") or __getattr__("_resolve_project_workdir")(project_id))
    resolved_model = str(prepared.get("resolved_model") or "")
    resolved_reasoning = str(prepared.get("resolved_reasoning") or "")
    try:
        refresh_generated_media_status(meta, extra_texts=[message])
    except Exception:
        pass
    store.save_meta(run_id, meta)

    supports_model = bool(adapter_cls.supports_model())
    command_bundle = runtime_build_execution_command(
        adapter_cls=adapter_cls,
        session_id=session_id,
        message=message,
        output_path=last_path,
        profile_label=profile_label,
        resolved_model=resolved_model,
        resolved_reasoning=resolved_reasoning,
        cli_type=cli_type,
        supports_model=supports_model,
        profile_not_found_recent=__getattr__("_profile_not_found_recent"),
        permission_mode=(
            str(meta.get("codebuddy_permission_mode") or "")
            if str(cli_type or "").strip().lower() == "codebuddy"
            else str(meta.get("claude_permission_mode") or "")
            if str(cli_type or "").strip().lower() == "claude"
            else ""
        ),
        attachments=runtime_image_attachments,
    )
    base_cmd = list(command_bundle.get("base_cmd") or [])
    cmd = list(command_bundle.get("cmd") or [])
    profile_suppressed = bool(command_bundle.get("profile_suppressed"))
    profile_suppress_left_s = float(command_bundle.get("profile_suppress_left_s") or 0.0)
    spawn_bundle = runtime_prepare_process_spawn(
        cli_type=cli_type,
        requested_cwd=run_cwd,
        cmd=cmd,
        execution_profile=execution_profile,
    )
    spawn_cmd = list(spawn_bundle.get("cmd") or cmd)
    spawn_cwd = Path(spawn_bundle.get("spawn_cwd") or run_cwd)
    spawn_env = dict(spawn_bundle.get("spawn_env") or os.environ)
    spawn_mode = str(spawn_bundle.get("mode") or "direct")
    mirrored_from = str(spawn_bundle.get("mirrored_from") or "")
    execution_profile = str(spawn_bundle.get("execution_profile") or execution_profile or "sandboxed")
    runtime_image_arg_count = (
        _count_codex_image_args(spawn_cmd)
        if str(cli_type or "").strip().lower() == "codex" and runtime_image_attachments
        else 0
    )
    if runtime_image_attachments:
        meta["runtime_attachment_summary"] = _build_runtime_attachment_summary(
            runtime_image_attachments,
            adapter_image_arg_count=runtime_image_arg_count,
            actual_cli_invoked=False,
        )
        if claude_image_path_fallback:
            meta["claude_image_path_fallback"] = _build_claude_image_path_fallback_summary(runtime_image_attachments)
        meta["image_passed"] = False
        meta["adapter_image_arg_count"] = runtime_image_arg_count
        try:
            store.save_meta(run_id, meta)
        except Exception:
            pass
    if str(cli_type or "").strip().lower() == "codebuddy":
        codebuddy_permission_mode = normalize_codebuddy_permission_mode(meta.get("codebuddy_permission_mode"))
        meta["codebuddy_permission_mode"] = codebuddy_permission_mode
        spawn_env["TASK_DASHBOARD_CODEBUDDY_PERMISSION_MODE"] = codebuddy_permission_mode
        spawn_cmd = apply_codebuddy_permission_mode_to_runner_command(spawn_cmd, codebuddy_permission_mode)
        try:
            store.save_meta(run_id, meta)
        except Exception:
            pass
    if str(cli_type or "").strip().lower() == "claude":
        claude_permission_mode = normalize_claude_permission_mode(meta.get("claude_permission_mode"))
        meta["claude_permission_mode"] = claude_permission_mode
        spawn_env["TASK_DASHBOARD_CLAUDE_PERMISSION_MODE"] = claude_permission_mode
        spawn_cmd = apply_claude_permission_mode_to_runner_command(spawn_cmd, claude_permission_mode)
        try:
            store.save_meta(run_id, meta)
        except Exception:
            pass

    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("w", encoding="utf-8") as logf:
            runtime_write_execution_log_header(
                logf,
                meta=meta,
                run_cwd=run_cwd,
                spawn_cwd=spawn_cwd,
                cmd=spawn_cmd,
                profile_label=profile_label,
                profile_suppressed=profile_suppressed,
                profile_suppress_left_s=profile_suppress_left_s,
                spawn_mode=spawn_mode,
                mirrored_from=mirrored_from,
                execution_profile=execution_profile,
            )

            proc = subprocess.Popen(
                spawn_cmd,
                cwd=str(spawn_cwd),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                env=spawn_env,
            )
            if str(cli_type or "").strip().lower() == "codex":
                meta["actual_cli_invoked"] = True
                meta["deterministic_fallback_used"] = False
                if runtime_image_attachments:
                    meta["runtime_attachment_summary"] = _build_runtime_attachment_summary(
                        runtime_image_attachments,
                        adapter_image_arg_count=runtime_image_arg_count,
                        actual_cli_invoked=True,
                    )
                    meta["image_passed"] = bool(
                        meta["runtime_attachment_summary"].get("image_passed")
                    )
                    meta["adapter_image_arg_count"] = runtime_image_arg_count
                try:
                    store.save_meta(run_id, meta)
                except Exception:
                    pass
            registry = __getattr__("RUN_PROCESS_REGISTRY")
            registry.register(run_id, proc)
            try:
                lock = threading.Lock()
                err_buf: list[str] = []
                live_auth_error: dict[str, str] = {"text": ""}
                cli_type_normalized = str(cli_type or "").strip().lower()
                is_terminal_text_cli = cli_type_normalized in _TERMINAL_TEXT_CLIS
                should_clear_process_fields = cli_type_normalized in _TERMINAL_TEXT_PROCESS_CLEAR_CLIS
                existing_rows_raw = meta.get("processRows") or meta.get("process_rows") or []
                existing_rows: list[dict[str, str]] = []
                if isinstance(existing_rows_raw, list) and not should_clear_process_fields:
                    for item in existing_rows_raw[-240:]:
                        if not isinstance(item, dict):
                            continue
                        text = _safe_text(item.get("text"), 3000).strip()
                        if not text:
                            continue
                        row = {
                            "text": text,
                            "at": str(item.get("at") or item.get("timestamp") or item.get("time") or "").strip(),
                        }
                        for optional_key in ("event_type", "item_type", "title", "path", "source"):
                            optional_value = _safe_text(item.get(optional_key), 1000).strip()
                            if optional_value:
                                row[optional_key] = optional_value
                        existing_rows.append(row)
                existing_events_raw = meta.get("process_events") or meta.get("processEvents") or []
                existing_events: list[dict[str, str]] = []
                if isinstance(existing_events_raw, list) and not should_clear_process_fields:
                    for item in existing_events_raw[-240:]:
                        if not isinstance(item, dict):
                            continue
                        text = _safe_text(item.get("text"), 3000).strip()
                        if not text:
                            continue
                        existing_events.append(
                            {
                                "event_type": str(item.get("event_type") or "").strip(),
                                "item_type": str(item.get("item_type") or "").strip(),
                                "title": str(item.get("title") or "").strip(),
                                "text": text,
                                "at": str(item.get("at") or item.get("timestamp") or item.get("time") or "").strip(),
                                "path": str(item.get("path") or "").strip(),
                                "source": str(item.get("source") or "").strip(),
                            }
                        )
                if is_terminal_text_cli:
                    meta["agentMessagesCount"] = 0
                    meta["partialPreview"] = ""
                    if should_clear_process_fields:
                        meta["processRows"] = []
                        meta["process_rows"] = []
                        meta["process_events"] = []
                        meta["processEvents"] = []
                process_state: dict[str, Any] = {
                    "count": 0 if is_terminal_text_cli else int(meta.get("agentMessagesCount") or 0),
                    "latest": "" if is_terminal_text_cli else str(meta.get("partialPreview") or ""),
                    "last_text": str((existing_rows[-1] or {}).get("text") or "") if existing_rows else "",
                    "rows": existing_rows,
                    "events": existing_events,
                    "event_count": len(existing_events),
                    "event_latest": str((existing_events[-1] or {}).get("text") or "") if existing_events else "",
                }

                def _capture_auth_error(raw: str) -> None:
                    runtime_capture_auth_error(
                        raw,
                        live_auth_error=live_auth_error,
                        is_auth_error=__getattr__("_is_auth_error"),
                        safe_text=_safe_text,
                    )

                def _capture_agent_text(raw_line: str) -> None:
                    runtime_capture_agent_text(
                        raw_line,
                        adapter_cls=adapter_cls,
                        process_state=process_state,
                        meta=meta,
                        parse_adapter_output_line=__getattr__("_parse_adapter_output_line"),
                        extract_agent_message_text_from_parsed=__getattr__("_extract_agent_message_text_from_parsed"),
                        safe_text=_safe_text,
                        now_iso=_now_iso,
                    )

                def _pump(stream: Any, label: str) -> None:
                    runtime_pump_process_stream(
                        stream,
                        label=label,
                        lock=lock,
                        logf=logf,
                        err_buf=err_buf,
                        capture_auth_error_cb=_capture_auth_error,
                        capture_agent_text_cb=_capture_agent_text,
                    )

                t_out = threading.Thread(target=_pump, args=(proc.stdout, "stdout"), daemon=True)  # type: ignore[arg-type]
                t_err = threading.Thread(target=_pump, args=(proc.stderr, "stderr"), daemon=True)  # type: ignore[arg-type]
                t_out.start()
                t_err.start()

                start_ts = time.time()
                timed_out = False
                timeout_error = ""
                last_progress_ts = start_ts
                last_last_mtime = 0.0
                last_log_mtime = 0.0
                last_agent_count = int(meta.get("agentMessagesCount") or 0)
                last_event_count = int(process_state.get("event_count") or 0)
                last_partial_preview = str(meta.get("partialPreview") or "")
                seen_local_imagegen_paths: set[str] = set()
                last_local_imagegen_mtime = 0.0
                try:
                    if last_path.exists():
                        last_last_mtime = float(last_path.stat().st_mtime)
                except Exception:
                    last_last_mtime = 0.0
                try:
                    if log_path.exists():
                        last_log_mtime = float(log_path.stat().st_mtime)
                except Exception:
                    last_log_mtime = 0.0
                try:
                    for path in candidate_local_imagegen_files(meta, now_ts=start_ts, max_items=32):
                        seen_local_imagegen_paths.add(str(path))
                    last_local_imagegen_mtime = latest_local_imagegen_mtime(meta, now_ts=start_ts)
                except Exception:
                    seen_local_imagegen_paths = set()
                    last_local_imagegen_mtime = 0.0
                while True:
                    rc = proc.poll()
                    now_ts = time.time()
                    progress_made = False
                    last = __getattr__("_tail_text")(last_path, max_chars=2600)
                    if last:
                        new_preview = _safe_text(last.replace("\r\n", "\n").strip(), 300)
                        if new_preview and new_preview != str(meta.get("lastPreview") or ""):
                            progress_made = True
                        meta["lastPreview"] = new_preview
                    with lock:
                        cur_count = int(process_state.get("count") or 0)
                        cur_latest = str(process_state.get("latest") or "").strip()
                        cur_event_count = int(process_state.get("event_count") or 0)
                        cur_event_latest = str(process_state.get("event_latest") or "").strip()
                    if cur_count > 0:
                        prev_count = int(meta.get("agentMessagesCount") or 0)
                        meta["agentMessagesCount"] = max(prev_count, cur_count)
                    if cur_count > last_agent_count:
                        progress_made = True
                        last_agent_count = cur_count
                    if cur_event_count > last_event_count:
                        progress_made = True
                        last_event_count = cur_event_count
                    if cur_latest and not str(meta.get("lastPreview") or "").strip():
                        meta["partialPreview"] = _safe_text(cur_latest, 300)
                    if cur_latest and cur_latest != last_partial_preview:
                        progress_made = True
                        last_partial_preview = cur_latest
                    if (
                        cur_event_latest
                        and not cur_latest
                        and not str(meta.get("lastPreview") or "").strip()
                        and cur_event_latest != last_partial_preview
                    ):
                        progress_made = True
                        meta["partialPreview"] = _safe_text(cur_event_latest, 300)
                        last_partial_preview = cur_event_latest
                    try:
                        if last_path.exists():
                            cur_last_mtime = float(last_path.stat().st_mtime)
                            if cur_last_mtime > last_last_mtime:
                                progress_made = True
                                last_last_mtime = cur_last_mtime
                    except Exception:
                        pass
                    try:
                        if log_path.exists():
                            cur_log_mtime = float(log_path.stat().st_mtime)
                            if cur_log_mtime > last_log_mtime:
                                progress_made = True
                                last_log_mtime = cur_log_mtime
                    except Exception:
                        pass
                    try:
                        for media_path in candidate_local_imagegen_files(meta, now_ts=now_ts, max_items=32):
                            path_key = str(media_path)
                            try:
                                media_mtime = float(media_path.stat().st_mtime)
                            except Exception:
                                media_mtime = 0.0
                            is_new_path = path_key not in seen_local_imagegen_paths
                            if media_mtime > last_local_imagegen_mtime:
                                progress_made = True
                                last_local_imagegen_mtime = media_mtime
                            if is_new_path:
                                seen_local_imagegen_paths.add(path_key)
                                try:
                                    display_path = str(media_path.relative_to(run_cwd))
                                except Exception:
                                    display_path = media_path.name
                                with lock:
                                    runtime_append_process_event(
                                        process_state,
                                        meta,
                                        {
                                            "event_type": "generated_media_file",
                                            "item_type": "local_imagegen_fallback",
                                            "title": display_path,
                                            "text": f"生成媒体文件: {display_path}",
                                            "path": str(media_path),
                                            "source": "local_imagegen_fallback",
                                        },
                                        safe_text=_safe_text,
                                        now_iso=_now_iso,
                                    )
                                progress_made = True
                    except Exception:
                        pass
                    try:
                        if refresh_generated_media_status(meta, extra_texts=[message, last, cur_latest, cur_event_latest]):
                            progress_made = True
                    except Exception:
                        pass
                    if progress_made:
                        last_progress_ts = now_ts
                        meta["lastProgressAt"] = _now_iso()
                    store.save_meta(run_id, meta)
                    if rc is not None:
                        break
                    timeout_error = runtime_detect_execution_timeout(
                        timeout_enabled=timeout_enabled,
                        timeout_value=timeout_value,
                        start_ts=start_ts,
                        now_ts=now_ts,
                        no_progress_enabled=no_progress_enabled,
                        no_progress_value=no_progress_value,
                        last_progress_ts=last_progress_ts,
                    )
                    if timeout_error:
                        timed_out = True
                        runtime_terminate_process_for_timeout(proc, timeout_error)
                        break
                    time.sleep(0.7)

                t_out.join(timeout=1.5)
                t_err.join(timeout=1.5)
                if cli_type_normalized in {"codebuddy", "claude"}:
                    with lock:
                        has_process_fields = bool(
                            meta.get("processRows") or meta.get("process_events") or meta.get("processEvents")
                        )
                    if not has_process_fields:
                        recovered_events = extract_process_events_from_file(
                            log_path,
                            max_items=240,
                            cli_type=cli_type_normalized,
                        )
                        if recovered_events:
                            with lock:
                                for event in recovered_events:
                                    runtime_append_process_event(
                                        process_state,
                                        meta,
                                        event,
                                        safe_text=_safe_text,
                                        now_iso=_now_iso,
                                    )
                latest_meta = store.load_meta(run_id) or {}
                interrupt_requested_at = str(latest_meta.get("interruptRequestedAt") or "").strip()
                interrupted_by_user = registry.consume_interrupted(run_id)
                if not interrupted_by_user and interrupt_requested_at:
                    try:
                        last_text = last_path.read_text(encoding="utf-8", errors="replace").strip()
                    except Exception:
                        last_text = ""
                    try:
                        agent_msgs = __getattr__("_extract_agent_messages_from_file")(
                            log_path,
                            max_items=4,
                            cli_type=cli_type,
                        )
                    except Exception:
                        agent_msgs = []
                    try:
                        log_has_turn_completed = __getattr__("_log_has_terminal_signal")(
                            log_path,
                            signal="turn.completed",
                        )
                    except Exception:
                        log_has_turn_completed = False
                    interrupted_by_user = bool(not (last_text or log_has_turn_completed or agent_msgs))

                if timed_out:
                    meta["status"] = "error"
                    meta["error"] = timeout_error or f"timeout>{timeout_value}s"
                    with lock:
                        if "no_progress" in str(meta.get("error") or ""):
                            logf.write("\nERROR: timeout (no progress)\n")
                        else:
                            logf.write("\nERROR: timeout\n")
                        logf.flush()
                elif interrupted_by_user:
                    meta["status"] = "error"
                    meta["error"] = "interrupted by user"
                    meta["interrupt_origin"] = "user"
                    meta["interrupt_requested_by"] = "user"
                    if interrupt_requested_at:
                        meta["interrupt_requested_at"] = interrupt_requested_at
                    meta["chain_state"] = "cancelled_by_user"
                    meta.pop("errorType", None)
                    with lock:
                        logf.write("\n[system] interrupted by user\n")
                        logf.flush()
                else:
                    rc = proc.returncode if proc.returncode is not None else -1
                    if rc != 0:
                        network_failed_persist = False
                        err_text = "".join(err_buf).strip()
                        meta.pop("errorType", None)
                        detected_auth_error = __getattr__("_is_auth_error")(
                            "\n".join([err_text, str(live_auth_error.get("text") or "")]).strip()
                        )
                        if cli_type == "codex" and profile_label and __getattr__("_is_profile_not_found")(err_text):
                            __getattr__("_record_profile_not_found")(cli_type, profile_label)
                            retry_base_cmd = list(base_cmd)
                            if spawn_mode != "direct":
                                retry_spawn_bundle = runtime_prepare_process_spawn(
                                    cli_type=cli_type,
                                    requested_cwd=run_cwd,
                                    cmd=retry_base_cmd,
                                    execution_profile=execution_profile,
                                )
                                retry_base_cmd = list(retry_spawn_bundle.get("cmd") or retry_base_cmd)
                                retry_spawn_env = dict(retry_spawn_bundle.get("spawn_env") or spawn_env)
                            else:
                                retry_spawn_env = spawn_env
                            with lock:
                                logf.write("\n[system] profile not found, retrying without -p ...\n")
                                logf.write(f"$ {' '.join(retry_base_cmd)}\n\n")
                                logf.flush()
                            try:
                                retry = subprocess.run(
                                    retry_base_cmd,
                                    cwd=str(spawn_cwd),
                                    capture_output=True,
                                    text=True,
                                    timeout=(timeout_value if timeout_enabled else None),
                                    env=retry_spawn_env,
                                )
                                runtime_write_retry_process_output(
                                    retry,
                                    lock=lock,
                                    logf=logf,
                                    capture_agent_text_cb=_capture_agent_text,
                                )
                                retry_result = runtime_apply_profile_fallback_retry_result(
                                    meta,
                                    retry,
                                    safe_text=_safe_text,
                                    is_auth_error=__getattr__("_is_auth_error"),
                                    is_transient_network_error=__getattr__("_is_transient_network_error"),
                                )
                                detected_auth_error = bool(retry_result.get("detected_auth_error"))
                                network_failed_persist = bool(retry_result.get("network_failed_persist"))
                            except subprocess.TimeoutExpired:
                                meta["status"] = "error"
                                meta["error"] = f"timeout>{timeout_value}s"
                                with lock:
                                    logf.write("\nERROR: retry timeout\n")
                                    logf.flush()
                        elif network_retry_max > 0:
                            tail = __getattr__("_tail_text")(log_path, max_chars=5000)
                            detected_text = (err_text + "\n" + tail).strip()
                            detected_auth_error = __getattr__("_is_auth_error")(detected_text)
                            if detected_auth_error:
                                meta["status"] = "error"
                                meta["error"] = _safe_text(err_text or f"exit={rc}", 1200)
                                meta["errorType"] = "auth_error"
                                with lock:
                                    logf.write("\n[system] auth-related error detected, skip auto-resume/retry\n")
                                    logf.flush()
                                network_failed_persist = False
                            elif __getattr__("_is_transient_network_error")(detected_text):
                                recovered = False
                                final_err = err_text
                                for attempt in range(1, network_retry_max + 1):
                                    delay_s = max(0.0, network_retry_base_s * (2 ** (attempt - 1)))
                                    with lock:
                                        logf.write(
                                            f"\n[system] transient network error detected, retrying {attempt}/{network_retry_max} "
                                            f"after {delay_s:.1f}s ...\n"
                                        )
                                        logf.flush()
                                    if delay_s > 0:
                                        time.sleep(delay_s)
                                    try:
                                        retry = subprocess.run(
                                            spawn_cmd,
                                            cwd=str(spawn_cwd),
                                            capture_output=True,
                                            text=True,
                                            timeout=(timeout_value if timeout_enabled else None),
                                            env=spawn_env,
                                        )
                                        runtime_write_retry_process_output(
                                            retry,
                                            lock=lock,
                                            logf=logf,
                                            capture_agent_text_cb=_capture_agent_text,
                                        )
                                        if retry.returncode == 0:
                                            recovered = True
                                            meta["status"] = "done"
                                            meta["error"] = ""
                                            meta["retryCount"] = attempt
                                            meta.pop("errorType", None)
                                            break
                                        final_err = (retry.stderr or "").strip() or f"exit={retry.returncode}"
                                        if __getattr__("_is_auth_error")(final_err):
                                            detected_auth_error = True
                                            break
                                        if not __getattr__("_is_transient_network_error")(final_err):
                                            break
                                    except subprocess.TimeoutExpired:
                                        final_err = f"timeout>{timeout_value}s"
                                        break
                                if not recovered:
                                    network_failed_persist = runtime_apply_network_retry_failure(
                                        meta,
                                        recovered=recovered,
                                        final_err=final_err,
                                        err_text=err_text,
                                        detected_text=detected_text,
                                        detected_auth_error=detected_auth_error,
                                        network_retry_max=network_retry_max,
                                        safe_text=_safe_text,
                                        is_auth_error=__getattr__("_is_auth_error"),
                                        is_transient_network_error=__getattr__("_is_transient_network_error"),
                                    )
                            else:
                                meta["status"] = "error"
                                meta["error"] = _safe_text(err_text or f"exit={rc}", 1200)
                                if detected_auth_error:
                                    meta["errorType"] = "auth_error"
                                network_failed_persist = __getattr__("_is_transient_network_error")(err_text) and (
                                    not detected_auth_error
                                )
                        else:
                            meta["status"] = "error"
                            meta["error"] = _safe_text(err_text or f"exit={rc}", 1200)
                            if detected_auth_error:
                                meta["errorType"] = "auth_error"
                            network_failed_persist = __getattr__("_is_transient_network_error")(err_text) and (
                                not detected_auth_error
                            )
                        if (
                            meta.get("status") == "error"
                            and network_failed_persist
                            and not bool(meta.get("autoResumePrompt"))
                        ):
                            retry_run_id = _schedule_network_resume_run(
                                store,
                                meta,
                                scheduler=scheduler,
                                cli_type=cli_type,
                            )
                            if retry_run_id:
                                log_line = runtime_apply_network_resume_schedule(
                                    meta,
                                    retry_run_id=retry_run_id,
                                    delay_s=__getattr__("_default_network_resume_delay_s")(),
                                    iso_after_s=_iso_after_s,
                                )
                                with lock:
                                    logf.write(log_line)
                                    logf.flush()
                    else:
                        harvested_final = ""
                        if cli_type_normalized == "claude":
                            harvested_final = _harvest_terminal_final_text(
                                last_path,
                                log_path,
                                cli_type=cli_type_normalized,
                            )
                        terminal_error = (
                            ""
                            if harvested_final
                            else __getattr__("_detect_terminal_text_cli_incomplete_error")(
                                cli_type,
                                log_path=log_path,
                            )
                        )
                        if terminal_error:
                            meta["status"] = "error"
                            meta["error"] = _safe_text(terminal_error, 1200)
                            meta["errorType"] = "permission_denied"
                            with lock:
                                logf.write(
                                    "\n[system] terminal-text CLI exited without final answer after permission denial\n"
                                )
                                logf.flush()
                        else:
                            meta["status"] = "done"
                            meta["error"] = ""
                            meta.pop("errorType", None)
            finally:
                registry.unregister(run_id)
    except Exception as exc:
        meta["status"] = "error"
        meta["error"] = _safe_text(str(exc), 1200)
        try:
            log_path.write_text(f"$ {' '.join(spawn_cmd)}\n\nERROR: {exc}\n", encoding="utf-8")
        except Exception:
            pass

    meta.pop("interruptRequestedAt", None)
    meta.pop("interruptRequestedBy", None)
    meta["finishedAt"] = _now_iso()
    cli_type_normalized = str(cli_type or "").strip().lower()
    last = _harvest_terminal_final_text(last_path, log_path, cli_type=cli_type_normalized)
    if last:
        meta["lastPreview"] = _safe_text(last, 300)
    if cli_type_normalized in _TERMINAL_TEXT_CLIS:
        meta["agentMessagesCount"] = 0
        meta["partialPreview"] = ""
        if cli_type_normalized in _TERMINAL_TEXT_PROCESS_CLEAR_CLIS:
            meta["processRows"] = []
            meta["process_rows"] = []
            meta["process_events"] = []
            meta["processEvents"] = []
    try:
        skill_texts: list[str] = []
        if last:
            skill_texts.append(last)
        partial = str(meta.get("partialPreview") or "").strip()
        if partial:
            skill_texts.append(partial)
        agent_msgs = __getattr__("_extract_agent_messages_from_file")(log_path, max_items=240, cli_type=cli_type)
        if agent_msgs:
            skill_texts.extend(agent_msgs)
        meta["skills_used"] = __getattr__("_extract_skills_used_from_texts")(skill_texts, max_items=20)
    except Exception:
        meta["skills_used"] = __getattr__("_normalize_skills_used_value")(meta.get("skills_used"), max_items=20)
    try:
        business_texts: list[str] = []
        if last:
            business_texts.append(last)
        partial_business = str(meta.get("partialPreview") or "").strip()
        if partial_business:
            business_texts.append(partial_business)
        meta["business_refs"] = __getattr__("_extract_business_refs_from_texts")(business_texts, max_items=24)
    except Exception:
        meta["business_refs"] = __getattr__("_normalize_business_refs_value")(meta.get("business_refs"), max_items=24)
    try:
        reconcile_generated_media_for_run(store, run_id, meta, log_path=log_path)
    except Exception:
        pass
    try:
        log_tail = __getattr__("_tail_text")(log_path, max_chars=24_000)
    except Exception:
        log_tail = ""
    try:
        runtime_apply_run_failure_classification(meta, log_text=log_tail, last_text=last)
    except Exception:
        pass
    try:
        retry_run_id = _schedule_provider_auto_retry_run(
            store,
            meta,
            scheduler=scheduler,
            cli_type=cli_type,
        )
        if retry_run_id:
            try:
                with log_path.open("a", encoding="utf-8") as logf:
                    logf.write(
                        "\n[system] provider transient failure eligible, scheduled "
                        f"auto retry run={retry_run_id} attempt={meta.get('providerRetryAttempt')} "
                        f"in {meta.get('providerRetryScheduledAt')}\n"
                    )
            except Exception:
                pass
    except Exception:
        pass
    current_count = int(meta.get("agentMessagesCount") or 0)
    if current_count > 0:
        meta["agentMessagesCount"] = current_count
    store.save_meta(run_id, meta)
    try:
        __getattr__("_dispatch_terminal_callback_for_run")(store, run_id, scheduler=scheduler, meta=meta)
    except Exception:
        pass
