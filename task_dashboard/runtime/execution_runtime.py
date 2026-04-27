# -*- coding: utf-8 -*-

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Optional

from task_dashboard.adapters import CodexAdapter
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
    extract_terminal_message_from_file,
    reconcile_generated_media_for_run,
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
    "_schedule_retry_waiting_fallback",
    "bootstrap_stale_queued_runs",
    "bootstrap_queued_runs",
    "bootstrap_restart_interrupted_runs",
    "run_cli_exec",
    "run_codex_exec",
]


_TERMINAL_TEXT_CLIS = {"claude", "opencode"}


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

    attachment_block = __getattr__("_build_attachment_prompt_block")(meta, store.runs_dir)
    if attachment_block:
        message = message + attachment_block
    message = _build_callback_context_message(meta, message)

    meta["status"] = "running"
    meta["startedAt"] = _now_iso()
    meta["cliType"] = cli_type
    meta["lastProgressAt"] = _now_iso()
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
            registry = __getattr__("RUN_PROCESS_REGISTRY")
            registry.register(run_id, proc)
            try:
                lock = threading.Lock()
                err_buf: list[str] = []
                live_auth_error: dict[str, str] = {"text": ""}
                is_terminal_text_cli = str(cli_type or "").strip().lower() in _TERMINAL_TEXT_CLIS
                existing_rows_raw = meta.get("processRows") or meta.get("process_rows") or []
                existing_rows: list[dict[str, str]] = []
                if isinstance(existing_rows_raw, list) and not is_terminal_text_cli:
                    for item in existing_rows_raw[-240:]:
                        if not isinstance(item, dict):
                            continue
                        text = _safe_text(item.get("text"), 3000).strip()
                        if not text:
                            continue
                        existing_rows.append(
                            {
                                "text": text,
                                "at": str(item.get("at") or item.get("timestamp") or item.get("time") or "").strip(),
                            }
                        )
                if is_terminal_text_cli:
                    meta["agentMessagesCount"] = 0
                    meta["partialPreview"] = ""
                    meta["processRows"] = []
                    meta["process_rows"] = []
                process_state: dict[str, Any] = {
                    "count": 0 if is_terminal_text_cli else int(meta.get("agentMessagesCount") or 0),
                    "latest": "" if is_terminal_text_cli else str(meta.get("partialPreview") or ""),
                    "last_text": str((existing_rows[-1] or {}).get("text") or "") if existing_rows else "",
                    "rows": existing_rows,
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
                last_partial_preview = str(meta.get("partialPreview") or "")
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
                    if cur_count > 0:
                        prev_count = int(meta.get("agentMessagesCount") or 0)
                        meta["agentMessagesCount"] = max(prev_count, cur_count)
                    if cur_count > last_agent_count:
                        progress_made = True
                        last_agent_count = cur_count
                    if cur_latest and not str(meta.get("lastPreview") or "").strip():
                        meta["partialPreview"] = _safe_text(cur_latest, 300)
                    if cur_latest and cur_latest != last_partial_preview:
                        progress_made = True
                        last_partial_preview = cur_latest
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
                        terminal_error = __getattr__("_detect_terminal_text_cli_incomplete_error")(
                            cli_type,
                            log_path=log_path,
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
    try:
        last = last_path.read_text(encoding="utf-8", errors="replace")
        meta["lastPreview"] = _safe_text(last.replace("\r\n", "\n").strip(), 300)
    except Exception:
        last = ""
    if not str(last or "").strip():
        last = extract_terminal_message_from_file(log_path, cli_type=cli_type)
        if last:
            meta["lastPreview"] = _safe_text(last.replace("\r\n", "\n").strip(), 300)
    if str(cli_type or "").strip().lower() in _TERMINAL_TEXT_CLIS:
        meta["agentMessagesCount"] = 0
        meta["partialPreview"] = ""
        meta["processRows"] = []
        meta["process_rows"] = []
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
    current_count = int(meta.get("agentMessagesCount") or 0)
    if current_count > 0:
        meta["agentMessagesCount"] = current_count
    store.save_meta(run_id, meta)
    try:
        __getattr__("_dispatch_terminal_callback_for_run")(store, run_id, scheduler=scheduler, meta=meta)
    except Exception:
        pass
