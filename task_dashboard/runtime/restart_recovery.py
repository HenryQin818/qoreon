# -*- coding: utf-8 -*-

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Callable


def build_restart_resume_receipt_summary(
    *,
    base_message: str,
    source_run_ids: list[str],
    max_preview: int = 8,
) -> dict[str, Any]:
    ids = [str(x or "").strip() for x in source_run_ids if str(x or "").strip()]
    preview = ", ".join(ids[: max(1, int(max_preview or 1))]) if ids else "-"
    if len(ids) > max_preview:
        preview += f" 等{len(ids)}条"
    return {
        "version": "v1",
        "message_kind": "restart_recovery_summary",
        "headline": "服务重启恢复汇总",
        "source_channel": "系统",
        "callback_task": "未关联任务",
        "execution_stage": "恢复",
        "goal": str(base_message or "").strip() or "因服务重启而中断，请继续开展工作。",
        "conclusion": "已中断待恢复",
        "progress": f"本次重启恢复汇总: {len(ids)} 条；来源run: {preview}",
        "system_actions": [
            "已生成恢复汇总回执并排队到目标会话。",
            "已记录来源 run 与恢复批次关联。",
        ],
        "need_peer": "先处理本条恢复提示，再回收需要收口的历史结果。",
        "expected_result": "恢复批次完成并形成后续执行回执。",
        "need_confirm": "无",
        "late_callback": False,
        "late_reason": "none",
        "technical": {
            "event_type": "interrupted",
            "event_reason": "server_restart",
            "trigger_type": "restart_recovery_summary",
            "source_run_ids": ids[:120],
        },
    }


def build_restart_resume_summary_message(
    *,
    base_message: str,
    source_run_ids: list[str],
    render_receipt_summary_message: Callable[[dict[str, Any]], str],
    max_preview: int = 8,
) -> str:
    summary = build_restart_resume_receipt_summary(
        base_message=base_message,
        source_run_ids=source_run_ids,
        max_preview=max_preview,
    )
    lines = [render_receipt_summary_message(summary), "", "技术明细（折叠）："]
    technical = summary.get("technical") if isinstance(summary, dict) else {}
    tech = technical if isinstance(technical, dict) else {}
    run_ids = tech.get("source_run_ids") if isinstance(tech, dict) else []
    preview = ", ".join(run_ids[:8]) if isinstance(run_ids, list) and run_ids else "-"
    if isinstance(run_ids, list) and len(run_ids) > 8:
        preview += f" 等{len(run_ids)}条"
    lines.append(f"- 触发类型: {str(tech.get('trigger_type') or 'restart_recovery_summary')}")
    lines.append(f"- 来源run: {preview}")
    lines.append("- 说明: 本条为服务重启后的恢复汇总提示，明细以来源 run 为准。")
    return "\n".join(lines)


def is_restart_recovery_pending_meta(meta: dict[str, Any]) -> bool:
    if not isinstance(meta, dict):
        return False
    if bool(meta.get("hidden")):
        return False
    if str(meta.get("status") or "").strip().lower() != "error":
        return False
    err = str(meta.get("error") or "")
    if "run interrupted (server restarted or process exited)" not in err:
        return False
    if str(meta.get("restartRecoveryRunId") or "").strip():
        return False
    if str(meta.get("restartRecoveryQueuedAt") or "").strip():
        return False
    run_id = str(meta.get("id") or "").strip()
    project_id = str(meta.get("projectId") or "").strip()
    channel_name = str(meta.get("channelName") or "").strip()
    session_id = str(meta.get("sessionId") or "").strip()
    return bool(run_id and project_id and channel_name and session_id)


_RESTART_RECOVERY_LAZY_LOCK = threading.Lock()
_RESTART_RECOVERY_LAZY_LAST_TS: dict[str, float] = {}
_QUEUED_RECOVERY_LAZY_LOCK = threading.Lock()
_QUEUED_RECOVERY_LAZY_LAST_TS: dict[str, float] = {}


def restart_recovery_lazy_interval_s() -> float:
    raw = str(os.environ.get("CCB_RESTART_RECOVERY_LAZY_INTERVAL_S") or "").strip()
    if not raw:
        return 8.0
    try:
        val = float(raw)
    except Exception:
        return 8.0
    if val < 0:
        return 0.0
    return min(val, 120.0)


def queued_recovery_stale_after_s() -> float:
    raw = str(os.environ.get("CCB_QUEUED_RECOVERY_STALE_AFTER_S") or "").strip()
    if not raw:
        return 6.0
    try:
        val = float(raw)
    except Exception:
        return 6.0
    if val < 0:
        return 0.0
    return min(val, 300.0)


def queued_recovery_lazy_interval_s() -> float:
    raw = str(os.environ.get("CCB_QUEUED_RECOVERY_LAZY_INTERVAL_S") or "").strip()
    if not raw:
        return 6.0
    try:
        val = float(raw)
    except Exception:
        return 6.0
    if val < 0:
        return 0.0
    return min(val, 120.0)


def is_stale_queued_pending_meta(
    meta: dict[str, Any],
    *,
    parse_iso_ts: Callable[[Any], float],
    now_ts: float | None = None,
    stale_after_s: float | None = None,
) -> bool:
    if not isinstance(meta, dict):
        return False
    if bool(meta.get("hidden")):
        return False
    if str(meta.get("status") or "").strip().lower() != "queued":
        return False
    if str(meta.get("startedAt") or "").strip():
        return False
    if str(meta.get("finishedAt") or "").strip():
        return False
    if str(meta.get("queueReason") or "").strip().lower() == "session_busy_external":
        return False
    run_id = str(meta.get("id") or "").strip()
    project_id = str(meta.get("projectId") or "").strip()
    session_id = str(meta.get("sessionId") or "").strip()
    if not (run_id and project_id and session_id):
        return False
    current_ts = float(now_ts) if now_ts is not None else time.time()
    stale_s = queued_recovery_stale_after_s() if stale_after_s is None else max(0.0, float(stale_after_s))
    created_ts = parse_iso_ts(meta.get("createdAt")) or 0.0
    if created_ts <= 0:
        return False
    return (current_ts - created_ts) >= stale_s


def bootstrap_queued_runs(
    store: Any,
    scheduler: Any,
    *,
    parse_iso_ts: Callable[[Any], float],
    now_iso: Callable[[], str],
    limit: int = 400,
) -> int:
    n = 0
    metas: list[tuple[float, float, str, str, str, str, float]] = []
    for p in store._iter_live_meta_paths():
        try:
            meta = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(meta, dict):
            continue
        st = str(meta.get("status") or "").strip().lower()
        if st not in {"queued", "retry_waiting"}:
            continue
        if bool(meta.get("hidden")):
            continue
        run_id = str(meta.get("id") or "").strip()
        session_id = str(meta.get("sessionId") or "").strip()
        cli_type = str(meta.get("cliType") or "codex").strip() or "codex"
        if not run_id or not session_id:
            continue
        created_ts = parse_iso_ts(meta.get("createdAt")) or 0.0
        try:
            mtime = float(p.stat().st_mtime)
        except Exception:
            mtime = 0.0
        if created_ts <= 0:
            created_ts = mtime
        due_ts = parse_iso_ts(meta.get("retryScheduledAt"))
        metas.append((created_ts, mtime, run_id, session_id, cli_type, st, due_ts))

    metas.sort(key=lambda x: (x[0], x[1], x[2]))
    now_ts = time.time()
    for _, __, run_id, session_id, cli_type, st, due_ts in metas[: max(1, int(limit or 1))]:
        try:
            if st == "retry_waiting":
                if due_ts > now_ts and hasattr(scheduler, "schedule_retry_waiting"):
                    scheduler.schedule_retry_waiting(run_id, session_id, due_ts, cli_type=cli_type)
                else:
                    m = store.load_meta(run_id) or {}
                    if m and str(m.get("status") or "").strip().lower() == "retry_waiting":
                        m["status"] = "queued"
                        m["retryActivatedAt"] = now_iso()
                        store.save_meta(run_id, m)
                    scheduler.enqueue(run_id, session_id, cli_type=cli_type)
            else:
                scheduler.enqueue(run_id, session_id, cli_type=cli_type)
            n += 1
        except Exception:
            continue
    return n


def bootstrap_stale_queued_runs(
    store: Any,
    scheduler: Any,
    *,
    parse_iso_ts: Callable[[Any], float],
    limit: int = 120,
    now_ts: float | None = None,
    stale_after_s: float | None = None,
    metas: list[dict[str, Any]] | None = None,
) -> int:
    if scheduler is None:
        return 0
    current_ts = float(now_ts) if now_ts is not None else time.time()
    stale_s = queued_recovery_stale_after_s() if stale_after_s is None else max(0.0, float(stale_after_s))
    candidates: list[tuple[float, str, str, str]] = []
    rows = metas if isinstance(metas, list) else None
    if rows is None:
        rows = []
        for p in store._iter_live_meta_paths():
            try:
                meta = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            if isinstance(meta, dict):
                rows.append(meta)
    for meta in rows:
        if not is_stale_queued_pending_meta(
            meta,
            parse_iso_ts=parse_iso_ts,
            now_ts=current_ts,
            stale_after_s=stale_s,
        ):
            continue
        run_id = str(meta.get("id") or "").strip()
        session_id = str(meta.get("sessionId") or "").strip()
        cli_type = str(meta.get("cliType") or "codex").strip() or "codex"
        created_ts = parse_iso_ts(meta.get("createdAt")) or 0.0
        candidates.append((created_ts, run_id, session_id, cli_type))

    candidates.sort(key=lambda item: (item[0], item[1]))
    n = 0
    seen: set[str] = set()
    for _, run_id, session_id, cli_type in candidates[: max(1, int(limit or 1))]:
        if run_id in seen:
            continue
        seen.add(run_id)
        try:
            scheduler.enqueue(run_id, session_id, cli_type=cli_type)
            n += 1
        except Exception:
            continue
    return n


def bootstrap_restart_interrupted_runs(
    store: Any,
    *,
    scheduler: Any | None = None,
    parse_iso_ts: Callable[[Any], float],
    now_iso: Callable[[], str],
    default_restart_resume_window_s: Callable[[], int],
    default_restart_resume_message: Callable[[], str],
    run_process_alive: Callable[[str, str], bool],
    build_restart_resume_receipt_summary: Callable[..., dict[str, Any]],
    build_restart_resume_summary_message: Callable[..., str],
    run_cli_exec: Callable[..., None],
    limit: int = 80,
    now_ts: float | None = None,
    window_s: int | None = None,
) -> int:
    current_ts = float(now_ts) if now_ts is not None else time.time()
    win_s = int(window_s if window_s is not None else default_restart_resume_window_s())
    win_s = max(60, min(win_s, 7 * 24 * 3600))
    max_n = max(1, int(limit or 1))
    msg = default_restart_resume_message()
    reason = "run interrupted (server restarted or process exited)"
    running_grace_s = 45.0
    running_recent_progress_s = 30.0

    candidates: list[tuple[float, float, str, str, str, str, str, str]] = []
    existing_recovery_source_ids: set[str] = set()
    rows: list[tuple[Path, dict[str, Any]]] = []
    for p in store._iter_live_meta_paths():
        try:
            meta = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(meta, dict):
            continue
        if bool(meta.get("hidden")):
            continue
        trigger_type = str(meta.get("trigger_type") or "").strip().lower()
        if trigger_type == "restart_recovery_summary":
            source_run_id = str(meta.get("restartRecoveryOf") or "").strip()
            if source_run_id:
                existing_recovery_source_ids.add(source_run_id)
            source_run_ids = meta.get("restartRecoverySourceRunIds")
            if isinstance(source_run_ids, list):
                for item in source_run_ids:
                    rid = str(item or "").strip()
                    if rid:
                        existing_recovery_source_ids.add(rid)
        rows.append((p, meta))

    for p, meta in rows:
        st = str(meta.get("status") or "").strip().lower()
        interrupted = False
        if st == "error":
            interrupted = reason in str(meta.get("error") or "")
        elif st == "running":
            run_id_probe = str(meta.get("id") or "").strip()
            cli_type_probe = str(meta.get("cliType") or "codex").strip() or "codex"
            started_ts = parse_iso_ts(meta.get("startedAt"))
            created_ts = parse_iso_ts(meta.get("createdAt"))
            last_progress_ts = parse_iso_ts(meta.get("lastProgressAt"))
            anchor_ts = started_ts or created_ts
            if run_id_probe and anchor_ts > 0 and (current_ts - anchor_ts) >= running_grace_s:
                if last_progress_ts > 0 and (current_ts - last_progress_ts) < running_recent_progress_s:
                    continue
                try:
                    alive = run_process_alive(run_id_probe, cli_type_probe)
                except Exception:
                    alive = False
                if not alive:
                    meta["status"] = "error"
                    if not str(meta.get("finishedAt") or "").strip():
                        meta["finishedAt"] = now_iso()
                    if not str(meta.get("error") or "").strip():
                        meta["error"] = reason
                    try:
                        store.save_meta(run_id_probe, meta)
                    except Exception:
                        pass
                    interrupted = True
        if not interrupted:
            continue
        if str(meta.get("restartRecoveryRunId") or "").strip():
            continue
        if str(meta.get("restartRecoveryQueuedAt") or "").strip():
            continue

        run_id = str(meta.get("id") or "").strip()
        project_id = str(meta.get("projectId") or "").strip()
        channel_name = str(meta.get("channelName") or "").strip()
        session_id = str(meta.get("sessionId") or "").strip()
        profile_label = str(meta.get("profileLabel") or "").strip()
        cli_type = str(meta.get("cliType") or "codex").strip() or "codex"
        if not run_id or not project_id or not channel_name or not session_id:
            continue
        if run_id in existing_recovery_source_ids:
            continue

        event_ts = (
            parse_iso_ts(meta.get("finishedAt"))
            or parse_iso_ts(meta.get("startedAt"))
            or parse_iso_ts(meta.get("createdAt"))
        )
        try:
            mtime = float(p.stat().st_mtime)
        except Exception:
            mtime = 0.0
        if event_ts <= 0:
            event_ts = mtime
        if event_ts <= 0:
            continue
        if (current_ts - event_ts) > float(win_s):
            continue

        candidates.append((event_ts, mtime, run_id, project_id, channel_name, session_id, profile_label, cli_type))

    candidates.sort(key=lambda x: (x[0], x[1], x[2]))

    grouped: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    group_order: list[tuple[str, str, str, str]] = []
    for _, __, source_run_id, project_id, channel_name, session_id, profile_label, cli_type in candidates:
        key = (project_id, channel_name, session_id, cli_type)
        g = grouped.get(key)
        if not isinstance(g, dict):
            g = {
                "project_id": project_id,
                "channel_name": channel_name,
                "session_id": session_id,
                "cli_type": cli_type,
                "profile_label": profile_label,
                "source_run_ids": [],
            }
            grouped[key] = g
            group_order.append(key)
        if (not str(g.get("profile_label") or "").strip()) and profile_label:
            g["profile_label"] = profile_label
        arr = g.get("source_run_ids")
        rows = arr if isinstance(arr, list) else []
        rid = str(source_run_id or "").strip()
        if rid and rid not in rows:
            rows.append(rid)
        g["source_run_ids"] = rows

    n = 0
    for key in group_order[:max_n]:
        g = grouped.get(key) or {}
        project_id = str(g.get("project_id") or "").strip()
        channel_name = str(g.get("channel_name") or "").strip()
        session_id = str(g.get("session_id") or "").strip()
        profile_label = str(g.get("profile_label") or "").strip()
        cli_type = str(g.get("cli_type") or "codex").strip() or "codex"
        source_run_ids = [str(x or "").strip() for x in (g.get("source_run_ids") or []) if str(x or "").strip()]
        if not source_run_ids:
            continue
        try:
            receipt_summary = build_restart_resume_receipt_summary(
                base_message=msg,
                source_run_ids=source_run_ids,
            )
            follow_msg = build_restart_resume_summary_message(base_message=msg, source_run_ids=source_run_ids)
            follow = store.create_run(
                project_id,
                channel_name,
                session_id,
                follow_msg,
                profile_label=profile_label,
                cli_type=cli_type,
                sender_type="system",
                sender_id="system",
                sender_name="系统",
                extra_meta={
                    "trigger_type": "restart_recovery_summary",
                    "restartRecoveryOf": source_run_ids[0],
                    "restartRecoveryCount": len(source_run_ids),
                    "restartRecoverySourceRunIds": source_run_ids[:120],
                    "receipt_summary": receipt_summary,
                },
            )
            follow_id = str(follow.get("id") or "").strip()
            if not follow_id:
                continue

            follow_meta = store.load_meta(follow_id) or follow
            follow_meta["restartRecoveryOf"] = source_run_ids[0]
            follow_meta["restartRecoveryReason"] = "server_restart_interrupted"
            follow_meta["restartRecoveryQueuedAt"] = now_iso()
            follow_meta["restartRecoveryCount"] = len(source_run_ids)
            follow_meta["restartRecoverySourceRunIds"] = source_run_ids[:120]
            follow_meta["restartRecoveryBatchId"] = follow_id
            store.save_meta(follow_id, follow_meta)

            queued_at = now_iso()
            for source_run_id in source_run_ids:
                src = store.load_meta(source_run_id) or {}
                if not src:
                    continue
                src["restartRecoveryRunId"] = follow_id
                src["restartRecoveryQueuedAt"] = queued_at
                src["restartRecoverySender"] = "system"
                src["restartRecoveryBatchId"] = follow_id
                store.save_meta(source_run_id, src)

            if scheduler is not None and str(os.environ.get("CCB_SCHEDULER") or "").strip() != "0":
                try:
                    scheduler.enqueue(follow_id, session_id, cli_type=cli_type, priority="urgent")
                except TypeError:
                    scheduler.enqueue(follow_id, session_id, cli_type=cli_type)
            else:
                threading.Thread(
                    target=run_cli_exec,
                    args=(store, follow_id, None, cli_type),
                    daemon=True,
                ).start()
            n += 1
        except Exception:
            continue
    return n


def maybe_trigger_restart_recovery_lazy(
    store: Any,
    scheduler: Any | None,
    metas: list[dict[str, Any]],
    *,
    bootstrap_restart_interrupted_runs_fn: Callable[..., int],
    project_id_hint: str = "",
) -> int:
    rows = [m for m in metas if is_restart_recovery_pending_meta(m)]
    if not rows:
        return 0
    pid = str(project_id_hint or "").strip()
    if not pid:
        pid = str(rows[0].get("projectId") or "").strip()
    key = pid or "__global__"
    interval_s = restart_recovery_lazy_interval_s()
    now_ts = time.time()
    if interval_s > 0:
        with _RESTART_RECOVERY_LAZY_LOCK:
            last = float(_RESTART_RECOVERY_LAZY_LAST_TS.get(key) or 0.0)
            if last > 0 and (now_ts - last) < interval_s:
                return 0
            _RESTART_RECOVERY_LAZY_LAST_TS[key] = now_ts
    resumed = bootstrap_restart_interrupted_runs_fn(store, scheduler, limit=120, now_ts=now_ts)
    return int(resumed or 0)


def maybe_trigger_queued_recovery_lazy(
    store: Any,
    scheduler: Any,
    metas: list[dict[str, Any]],
    *,
    parse_iso_ts: Callable[[Any], float],
    bootstrap_stale_queued_runs_fn: Callable[..., int],
    project_id_hint: str = "",
) -> int:
    now_ts = time.time()
    stale_s = queued_recovery_stale_after_s()
    rows = [
        meta
        for meta in metas
        if is_stale_queued_pending_meta(
            meta,
            parse_iso_ts=parse_iso_ts,
            now_ts=now_ts,
            stale_after_s=stale_s,
        )
    ]
    if not rows:
        return 0
    project_id = str(project_id_hint or "").strip()
    if not project_id:
        project_id = str(rows[0].get("projectId") or "").strip()
    key = project_id or "__global__"
    interval_s = queued_recovery_lazy_interval_s()
    if interval_s > 0:
        with _QUEUED_RECOVERY_LAZY_LOCK:
            last = float(_QUEUED_RECOVERY_LAZY_LAST_TS.get(key) or 0.0)
            if last > 0 and (now_ts - last) < interval_s:
                return 0
            _QUEUED_RECOVERY_LAZY_LAST_TS[key] = now_ts
    resumed = bootstrap_stale_queued_runs_fn(
        store,
        scheduler,
        metas=rows,
        limit=120,
        now_ts=now_ts,
        stale_after_s=stale_s,
    )
    return int(resumed or 0)
