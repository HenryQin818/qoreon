from __future__ import annotations

import hashlib
import json
import re
import secrets
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

TERMINAL_STATUSES = ("done", "error", "interrupted")
PROTECTED_STATUSES = (
    "queued",
    "retry_waiting",
    "running",
    "active",
    "external_busy",
    "finalizing",
    "unknown",
    "missing",
    "hidden",
)
WARNING_HOT_RUN_COUNT = 200
CRITICAL_HOT_RUN_COUNT = 500
WARNING_OLDEST_TERMINAL_HOURS = 48
CRITICAL_OLDEST_TERMINAL_DAYS = 7
DRY_RUN_EXPIRES_SECONDS = 30 * 60
MAX_ARCHIVE_LIMIT = 2000


def _as_str(value: Any) -> str:
    return "" if value is None else str(value)


def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _coerce_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    text = _as_str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _normalize_protected_run_ids(values: Any) -> set[str]:
    if values is None:
        return set()
    if isinstance(values, (str, bytes)):
        values = [values]
    try:
        return {_as_str(item).strip() for item in values if _as_str(item).strip()}
    except Exception:
        return set()


def _now_ts() -> float:
    return time.time()


def _iso_from_ts(ts: float) -> str:
    if ts <= 0:
        return ""
    return datetime.fromtimestamp(ts).astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")


def _now_iso() -> str:
    return _iso_from_ts(_now_ts())


def _parse_time(raw: Any) -> float:
    value = _as_str(raw).strip()
    if not value:
        return 0.0
    normalized = value.replace("Z", "+00:00")
    if re.match(r".*[+-]\d{4}$", normalized):
        normalized = normalized[:-2] + ":" + normalized[-2:]
    try:
        return datetime.fromisoformat(normalized).timestamp()
    except Exception:
        return 0.0


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _safe_read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except Exception:
        return False


def _hot_paths(store: Any, run_id: str) -> dict[str, Path]:
    base = Path(store.hot_dir) / run_id
    return {
        "meta": base.with_suffix(".json"),
        "msg": base.with_suffix(".msg.txt"),
        "last": base.with_suffix(".last.txt"),
        "log": base.with_suffix(".log.txt"),
    }


def _archive_paths(store: Any, run_id: str, bucket: str) -> dict[str, Path]:
    base = Path(store.archive_dir) / bucket / run_id
    return {
        "meta": base.with_suffix(".json"),
        "msg": base.with_suffix(".msg.txt"),
        "last": base.with_suffix(".last.txt"),
        "log": base.with_suffix(".log.txt"),
    }


def _file_group_size(paths: dict[str, Path]) -> tuple[int, int, list[str]]:
    total = 0
    count = 0
    kinds: list[str] = []
    for kind, path in paths.items():
        try:
            if not path.exists() or not path.is_file():
                continue
            total += path.stat().st_size
            count += 1
            kinds.append(kind)
        except Exception:
            continue
    return total, count, kinds


def _state_group(status: str) -> str:
    if status in TERMINAL_STATUSES:
        return "terminal"
    if status in PROTECTED_STATUSES:
        return "protected"
    return "unknown"


def _project_matches(meta: dict[str, Any], project_id: str) -> bool:
    if not project_id:
        return True
    actual = _as_str(meta.get("projectId") or meta.get("project_id")).strip()
    return (not actual) or actual == project_id


def _anchor_ts(meta: dict[str, Any], meta_path: Path) -> float:
    for key in ("finishedAt", "updatedAt", "updated_at", "lastProgressAt", "createdAt", "startedAt"):
        ts = _parse_time(meta.get(key))
        if ts > 0:
            return ts
    try:
        return meta_path.stat().st_mtime
    except Exception:
        return 0.0


def _bucket_for_meta(meta: dict[str, Any], fallback_ts: float) -> str:
    for key in ("finishedAt", "createdAt", "startedAt"):
        value = _as_str(meta.get(key)).strip()
        if len(value) >= 7 and value[4:5] == "-" and value[7:8] in {"-", "T"}:
            return value[:7]
    if fallback_ts > 0:
        return datetime.fromtimestamp(fallback_ts).astimezone().strftime("%Y-%m")
    return time.strftime("%Y-%m", time.localtime())


def _path_guard_ok(store: Any, run_id: str, bucket: str) -> bool:
    hot_root = Path(store.hot_dir)
    archive_root = Path(store.archive_dir)
    for path in _hot_paths(store, run_id).values():
        if path.exists() and not _is_relative_to(path, hot_root):
            return False
    for path in _archive_paths(store, run_id, bucket).values():
        if not _is_relative_to(path, archive_root):
            return False
    return True


def _collect_hot_runs(
    store: Any,
    *,
    project_id: str = "",
    cutoff_ts: float = 0.0,
    include_hidden: bool = True,
    protected_run_ids: Any = None,
) -> list[dict[str, Any]]:
    hot_dir = Path(store.hot_dir)
    rows: list[dict[str, Any]] = []
    now_ts = _now_ts()
    protected_ids = _normalize_protected_run_ids(protected_run_ids)
    if not hot_dir.exists():
        return rows
    paths = sorted(hot_dir.glob("*.json"), key=lambda item: item.stat().st_mtime if item.exists() else 0, reverse=True)
    for meta_path in paths:
        meta = _safe_read_json(meta_path)
        if not meta:
            continue
        if not _project_matches(meta, project_id):
            continue
        hidden = _coerce_bool(meta.get("hidden"), False)
        if hidden and not include_hidden:
            continue
        run_id = _as_str(meta.get("id") or meta_path.stem).strip()
        if not run_id:
            continue
        status = _as_str(meta.get("status") or "unknown").strip().lower() or "unknown"
        group = _state_group(status)
        protected_by_runtime = run_id in protected_ids
        paths_for_run = _hot_paths(store, run_id)
        size, file_count, file_kinds = _file_group_size(paths_for_run)
        anchor_ts = _anchor_ts(meta, meta_path)
        bucket = _bucket_for_meta(meta, anchor_ts)
        path_ok = _path_guard_ok(store, run_id, bucket)
        excluded_reason = ""
        eligible = True
        if hidden:
            eligible = False
            excluded_reason = "hidden"
            group = "protected"
        elif protected_by_runtime:
            eligible = False
            excluded_reason = "protected"
            group = "protected"
        elif group == "unknown":
            eligible = False
            excluded_reason = "status_unknown"
        elif group != "terminal":
            eligible = False
            excluded_reason = "not_terminal"
        elif cutoff_ts > 0 and (anchor_ts <= 0 or anchor_ts > cutoff_ts):
            eligible = False
            excluded_reason = "too_new"
        elif not path_ok:
            eligible = False
            excluded_reason = "path_outside_runstore"
        rows.append(
            {
                "run_id": run_id,
                "status": status,
                "state_group": group,
                "project_id": _as_str(meta.get("projectId") or meta.get("project_id") or project_id).strip(),
                "session_id": _as_str(meta.get("sessionId") or meta.get("session_id")).strip(),
                "channel_name": _as_str(meta.get("channelName") or meta.get("channel_name")).strip(),
                "agent_display_name": _as_str(
                    meta.get("sender_name")
                    or meta.get("senderName")
                    or meta.get("source_agent_alias")
                    or meta.get("sourceAgentAlias")
                    or meta.get("channelName")
                ).strip(),
                "created_at": _as_str(meta.get("createdAt")).strip(),
                "started_at": _as_str(meta.get("startedAt")).strip(),
                "finished_at": _as_str(meta.get("finishedAt")).strip(),
                "anchor_at": _iso_from_ts(anchor_ts),
                "anchor_ts": anchor_ts,
                "age_hours": round(max(0.0, now_ts - anchor_ts) / 3600.0, 1) if anchor_ts > 0 else 0.0,
                "file_count": file_count,
                "bytes": size,
                "file_kinds": file_kinds,
                "has_attachments": bool(meta.get("attachments")),
                "archive_eligible": eligible,
                "archive_excluded_reason": excluded_reason,
                "protected_by_runtime": protected_by_runtime,
                "hidden": hidden,
                "bucket": bucket,
                "summary": _as_str(meta.get("lastPreview") or meta.get("messagePreview") or meta.get("partialPreview")).strip()[:220],
            }
        )
    return rows


def _archive_summary(store: Any, max_files: int = 50000) -> dict[str, Any]:
    archive_dir = Path(store.archive_dir)
    if not archive_dir.exists():
        return {"run_count": 0, "file_count": 0, "bytes": 0, "scan_mode": "exact"}
    run_count = 0
    file_count = 0
    total = 0
    scan_mode = "exact"
    try:
        for path in archive_dir.rglob("*"):
            if not path.is_file():
                continue
            file_count += 1
            if path.suffix == ".json" and path.parent.name != "manifests":
                run_count += 1
            try:
                total += path.stat().st_size
            except Exception:
                pass
            if file_count >= max_files:
                scan_mode = "estimated"
                break
    except Exception:
        scan_mode = "estimated"
    return {"run_count": run_count, "file_count": file_count, "bytes": total, "scan_mode": scan_mode}


def _build_session_summaries(rows: list[dict[str, Any]], limit: int = 60) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        sid = _as_str(row.get("session_id")).strip() or "(missing)"
        item = grouped.setdefault(
            sid,
            {
                "session_id": "" if sid == "(missing)" else sid,
                "channel_name": "",
                "agent_display_name": "",
                "hot_run_count": 0,
                "terminal_run_count": 0,
                "protected_run_count": 0,
                "unknown_run_count": 0,
                "bytes": 0,
                "oldest_run_at": "",
                "_oldest_run_ts": 0.0,
                "oldest_terminal_at": "",
                "_oldest_terminal_ts": 0.0,
                "newest_run_at": "",
                "_newest_run_ts": 0.0,
                "status_counts": {},
            },
        )
        if row.get("channel_name") and not item.get("channel_name"):
            item["channel_name"] = row.get("channel_name")
        if row.get("agent_display_name") and not item.get("agent_display_name"):
            item["agent_display_name"] = row.get("agent_display_name")
        item["hot_run_count"] += 1
        item["bytes"] += int(row.get("bytes") or 0)
        status = _as_str(row.get("status")).strip() or "unknown"
        item["status_counts"][status] = int(item["status_counts"].get(status) or 0) + 1
        group = _as_str(row.get("state_group")).strip()
        if group == "terminal":
            item["terminal_run_count"] += 1
        elif group == "protected":
            item["protected_run_count"] += 1
        else:
            item["unknown_run_count"] += 1
        ts = float(row.get("anchor_ts") or 0)
        if ts > 0 and (not item["_oldest_run_ts"] or ts < item["_oldest_run_ts"]):
            item["_oldest_run_ts"] = ts
            item["oldest_run_at"] = row.get("anchor_at") or ""
        if ts > 0 and (not item["_newest_run_ts"] or ts > item["_newest_run_ts"]):
            item["_newest_run_ts"] = ts
            item["newest_run_at"] = row.get("anchor_at") or ""
        if group == "terminal" and ts > 0 and (not item["_oldest_terminal_ts"] or ts < item["_oldest_terminal_ts"]):
            item["_oldest_terminal_ts"] = ts
            item["oldest_terminal_at"] = row.get("anchor_at") or ""
    out = []
    for item in grouped.values():
        item.pop("_oldest_run_ts", None)
        item.pop("_oldest_terminal_ts", None)
        item.pop("_newest_run_ts", None)
        out.append(item)
    return sorted(out, key=lambda x: (-int(x.get("hot_run_count") or 0), -int(x.get("terminal_run_count") or 0)))[:limit]


def build_runstore_health_response(
    store: Any,
    *,
    project_id: str = "",
    protected_run_ids: Any = None,
) -> tuple[int, dict[str, Any]]:
    rows = [
        row
        for row in _collect_hot_runs(
            store,
            project_id=project_id,
            include_hidden=True,
            protected_run_ids=protected_run_ids,
        )
    ]
    status_counts: dict[str, int] = {}
    state_group_counts = {"terminal": 0, "protected": 0, "unknown": 0}
    oldest_run_ts = 0.0
    newest_run_ts = 0.0
    oldest_terminal_ts = 0.0
    total_bytes = 0
    total_files = 0
    for row in rows:
        status = _as_str(row.get("status")).strip() or "unknown"
        status_counts[status] = int(status_counts.get(status) or 0) + 1
        group = _as_str(row.get("state_group")).strip() or "unknown"
        state_group_counts[group] = int(state_group_counts.get(group) or 0) + 1
        ts = float(row.get("anchor_ts") or 0)
        if ts > 0 and (not oldest_run_ts or ts < oldest_run_ts):
            oldest_run_ts = ts
        if ts > 0 and (not newest_run_ts or ts > newest_run_ts):
            newest_run_ts = ts
        if group == "terminal" and ts > 0 and (not oldest_terminal_ts or ts < oldest_terminal_ts):
            oldest_terminal_ts = ts
        total_bytes += int(row.get("bytes") or 0)
        total_files += int(row.get("file_count") or 0)
    now_ts = _now_ts()
    terminal_age_hours = (now_ts - oldest_terminal_ts) / 3600.0 if oldest_terminal_ts else 0.0
    reasons: list[str] = []
    level = "healthy"
    if len(rows) > CRITICAL_HOT_RUN_COUNT or terminal_age_hours >= CRITICAL_OLDEST_TERMINAL_DAYS * 24:
        level = "critical"
        if len(rows) > CRITICAL_HOT_RUN_COUNT:
            reasons.append("hot_run_count_over_critical")
        if terminal_age_hours >= CRITICAL_OLDEST_TERMINAL_DAYS * 24:
            reasons.append("oldest_terminal_over_7d")
    elif len(rows) > WARNING_HOT_RUN_COUNT or terminal_age_hours >= WARNING_OLDEST_TERMINAL_HOURS:
        level = "warning"
        if len(rows) > WARNING_HOT_RUN_COUNT:
            reasons.append("hot_run_count_over_warning")
        if terminal_age_hours >= WARNING_OLDEST_TERMINAL_HOURS:
            reasons.append("oldest_terminal_over_48h")
    recommendation = "当前 hot 规模可继续观察"
    recommendations: list[dict[str, Any]] = []
    if state_group_counts["terminal"] > 0 and level in {"warning", "critical"}:
        recommendation = "建议先 dry-run 归档 48 小时前终态 run"
        recommendations.append(
            {
                "action": "archive_terminal_hot_runs",
                "scope": "all",
                "session_id": "",
                "older_than_hours": 48,
                "reason": reasons[0] if reasons else "terminal_hot_runs_available",
            }
        )
    return 200, {
        "ok": True,
        "schema_version": "runstore_health.v1",
        "project_id": project_id,
        "generated_at": _now_iso(),
        "terminal_statuses": list(TERMINAL_STATUSES),
        "protected_statuses": list(PROTECTED_STATUSES),
        "hot_summary": {
            "run_count": len(rows),
            "file_count": total_files,
            "bytes": total_bytes,
            "terminal_run_count": state_group_counts["terminal"],
            "protected_run_count": state_group_counts["protected"],
            "unknown_run_count": state_group_counts["unknown"],
            "oldest_run_at": _iso_from_ts(oldest_run_ts),
            "oldest_terminal_at": _iso_from_ts(oldest_terminal_ts),
            "newest_run_at": _iso_from_ts(newest_run_ts),
        },
        "archive_summary": _archive_summary(store),
        "status_counts": status_counts,
        "state_group_counts": state_group_counts,
        "session_summaries": _build_session_summaries(rows),
        "thresholds": {
            "warning_hot_run_count": WARNING_HOT_RUN_COUNT,
            "critical_hot_run_count": CRITICAL_HOT_RUN_COUNT,
            "warning_oldest_terminal_hours": WARNING_OLDEST_TERMINAL_HOURS,
            "critical_oldest_terminal_days": CRITICAL_OLDEST_TERMINAL_DAYS,
        },
        "risk": {"level": level, "reasons": reasons, "recommendation": recommendation},
        "recommendations": recommendations,
    }


def _cutoff_from_params(params: dict[str, Any]) -> tuple[float, str, str]:
    hours = _coerce_int(params.get("older_than_hours") or params.get("olderThanHours"), 0)
    days = _coerce_int(params.get("older_than_days") or params.get("olderThanDays"), 0)
    if hours > 0:
        cutoff = datetime.now().astimezone() - timedelta(hours=hours)
        return cutoff.timestamp(), "older_than_hours", _iso_from_ts(cutoff.timestamp())
    if days > 0:
        cutoff = datetime.now().astimezone() - timedelta(days=days)
        return cutoff.timestamp(), "older_than_days", _iso_from_ts(cutoff.timestamp())
    return 0.0, "", ""


def list_runstore_hot_runs_response(
    store: Any,
    *,
    query: dict[str, list[str]],
    protected_run_ids: Any = None,
) -> tuple[int, dict[str, Any]]:
    def first(*names: str) -> str:
        for name in names:
            values = query.get(name) or []
            if values:
                return _as_str(values[0]).strip()
        return ""

    project_id = first("projectId", "project_id")
    session_id = first("session_id", "sessionId")
    status_filter = first("status").lower()
    state_group = first("state_group", "stateGroup").lower()
    cutoff_ts, cutoff_source, _ = _cutoff_from_params(
        {
            "older_than_hours": first("older_than_hours", "olderThanHours"),
            "older_than_days": first("older_than_days", "olderThanDays"),
        }
    )
    limit = max(1, min(_coerce_int(first("limit"), 50), 200))
    offset = max(0, _coerce_int(first("offset"), 0))
    rows = _collect_hot_runs(
        store,
        project_id=project_id,
        cutoff_ts=cutoff_ts,
        include_hidden=True,
        protected_run_ids=protected_run_ids,
    )
    if session_id:
        rows = [row for row in rows if _as_str(row.get("session_id")).strip() == session_id]
    if status_filter:
        rows = [row for row in rows if _as_str(row.get("status")).strip() == status_filter]
    if state_group:
        rows = [row for row in rows if _as_str(row.get("state_group")).strip() == state_group]
    rows.sort(key=lambda item: float(item.get("anchor_ts") or 0), reverse=True)
    total = len(rows)
    page = rows[offset : offset + limit]
    for row in page:
        row.pop("anchor_ts", None)
        row.pop("bucket", None)
        row.pop("hidden", None)
    return 200, {
        "ok": True,
        "schema_version": "runstore_hot_runs.v1",
        "project_id": project_id,
        "filters": {
            "session_id": session_id,
            "status": status_filter,
            "state_group": state_group,
            "older_than_hours": _coerce_int(first("older_than_hours", "olderThanHours"), 0),
            "older_than_days": _coerce_int(first("older_than_days", "olderThanDays"), 0),
            "cutoff_source": cutoff_source,
            "limit": limit,
            "offset": offset,
        },
        "pagination": {"limit": limit, "offset": offset, "returned": len(page), "total": total, "has_more": offset + len(page) < total},
        "terminal_statuses": list(TERMINAL_STATUSES),
        "protected_statuses": list(PROTECTED_STATUSES),
        "runs": page,
    }


def _normalize_statuses(raw: Any) -> tuple[list[str], str]:
    values = raw if isinstance(raw, list) else _as_str(raw).split(",")
    statuses = []
    for value in values:
        status = _as_str(value).strip().lower()
        if not status:
            continue
        if status not in TERMINAL_STATUSES:
            return [], status
        if status not in statuses:
            statuses.append(status)
    return statuses or list(TERMINAL_STATUSES), ""


def _dry_run_root(store: Any) -> Path:
    return Path(store.runs_dir).parent / ".run" / "runstore-health" / "dry-runs"


def _manifest_path(store: Any, job_id: str) -> Path:
    return Path(store.archive_dir) / "manifests" / f"{job_id}.json"


def _invalidate_runtime_caches(project_id: str, session_ids: list[str]) -> dict[str, bool]:
    result = {
        "runstore_live_index": True,
        "codex_runs_list_cache": False,
        "session_runtime_index_cache": False,
        "sessions_payload_cache": False,
    }
    try:
        from task_dashboard.runtime.run_routes import invalidate_runs_list_cache

        invalidate_runs_list_cache(project_id, session_id="")
        for sid in session_ids:
            invalidate_runs_list_cache(project_id, session_id=sid)
        result["codex_runs_list_cache"] = True
    except Exception:
        pass
    try:
        from task_dashboard.runtime.heartbeat_registry import _invalidate_project_session_runtime_index_cache

        _invalidate_project_session_runtime_index_cache(project_id, session_id="")
        for sid in session_ids:
            _invalidate_project_session_runtime_index_cache(project_id, session_id=sid)
        result["session_runtime_index_cache"] = True
    except Exception:
        pass
    try:
        from task_dashboard.runtime.session_routes import _invalidate_sessions_payload_cache

        _invalidate_sessions_payload_cache(project_id)
        result["sessions_payload_cache"] = True
    except Exception:
        pass
    return result


def create_runstore_archive_dry_run(
    store: Any,
    *,
    body: dict[str, Any],
    protected_run_ids: Any = None,
) -> tuple[int, dict[str, Any]]:
    scope = _as_str(body.get("scope") or "all").strip().lower()
    if scope not in {"all", "session"}:
        return 400, {"ok": False, "error": "invalid_scope"}
    session_id = _as_str(body.get("session_id") or body.get("sessionId")).strip()
    if scope == "session" and not session_id:
        return 400, {"ok": False, "error": "session_id_required"}
    cutoff_ts, cutoff_source, cutoff_at = _cutoff_from_params(body)
    if cutoff_ts <= 0:
        return 400, {"ok": False, "error": "cutoff_required"}
    statuses, invalid_status = _normalize_statuses(body.get("statuses"))
    if invalid_status:
        return 400, {"ok": False, "error": "status_not_terminal", "status": invalid_status}
    project_id = _as_str(body.get("project_id") or body.get("projectId")).strip()
    limit = max(1, min(_coerce_int(body.get("limit"), 500), MAX_ARCHIVE_LIMIT))
    rows = _collect_hot_runs(
        store,
        project_id=project_id,
        cutoff_ts=cutoff_ts,
        include_hidden=True,
        protected_run_ids=protected_run_ids,
    )
    if scope == "session":
        rows = [row for row in rows if _as_str(row.get("session_id")).strip() == session_id]
    eligible = [
        row
        for row in rows
        if bool(row.get("archive_eligible")) and _as_str(row.get("status")).strip() in statuses
    ]
    eligible.sort(key=lambda item: float(item.get("anchor_ts") or 0))
    limited = eligible[:limit]
    excluded = [row for row in rows if row not in limited]
    status_counts: dict[str, int] = {}
    session_counts: dict[str, int] = {}
    estimated_bytes = 0
    for row in limited:
        status = _as_str(row.get("status")).strip()
        status_counts[status] = int(status_counts.get(status) or 0) + 1
        sid = _as_str(row.get("session_id")).strip()
        if sid:
            session_counts[sid] = int(session_counts.get(sid) or 0) + 1
        estimated_bytes += int(row.get("bytes") or 0)
    job_id = f"runstore-archive-{time.strftime('%Y%m%d-%H%M%S', time.localtime())}-{secrets.token_hex(3)}"
    created_ts = _now_ts()
    expires_ts = created_ts + DRY_RUN_EXPIRES_SECONDS
    job = {
        "schema_version": "runstore_archive_plan.v1",
        "job_id": job_id,
        "created_at": _iso_from_ts(created_ts),
        "expires_at": _iso_from_ts(expires_ts),
        "expires_ts": expires_ts,
        "job_ttl_seconds": DRY_RUN_EXPIRES_SECONDS,
        "project_id": project_id,
        "scope": scope,
        "session_id": session_id,
        "cutoff_at": cutoff_at,
        "cutoff_ts": cutoff_ts,
        "cutoff_source": cutoff_source,
        "terminal_statuses": statuses,
        "eligible_count": len(limited),
        "estimated_bytes": estimated_bytes,
        "status_counts": status_counts,
        "session_counts": session_counts,
        "excluded_count": len(excluded),
        "excluded_active_count": sum(1 for row in excluded if _as_str(row.get("state_group")) == "protected"),
        "excluded_unknown_count": sum(1 for row in excluded if _as_str(row.get("state_group")) == "unknown"),
        "sample_run_ids": [_as_str(row.get("run_id")).strip() for row in limited[:10]],
        "candidate_run_ids": [_as_str(row.get("run_id")).strip() for row in limited],
        "warnings": ["plan_limited_by_request_limit"] if len(eligible) > len(limited) else [],
        "will_move_attachments": False,
        "will_delete_files": False,
        "reason": _as_str(body.get("reason")).strip(),
    }
    fingerprint_payload = {
        "project_id": project_id,
        "scope": scope,
        "session_id": session_id,
        "cutoff_at": cutoff_at,
        "terminal_statuses": statuses,
        "limit": limit,
        "candidate_run_ids": job["candidate_run_ids"],
    }
    digest = hashlib.sha256(
        json.dumps(fingerprint_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    job["plan_fingerprint"] = f"sha256:{digest}"
    _atomic_write_json(_dry_run_root(store) / f"{job_id}.json", job)
    return 200, {"ok": True, **{k: v for k, v in job.items() if k not in {"candidate_run_ids", "cutoff_ts", "expires_ts"}}}


def _load_dry_run_job(store: Any, job_id: str) -> dict[str, Any] | None:
    if not re.match(r"^runstore-archive-\d{8}-\d{6}-[a-f0-9]{6}$", job_id):
        return None
    path = _dry_run_root(store) / f"{job_id}.json"
    if not _is_relative_to(path, _dry_run_root(store)) or not path.exists():
        return None
    return _safe_read_json(path)


def execute_runstore_archive_plan(
    store: Any,
    *,
    body: dict[str, Any],
    protected_run_ids: Any = None,
) -> tuple[int, dict[str, Any]]:
    if not _coerce_bool(body.get("confirm"), False):
        return 400, {"ok": False, "error": "confirm_required"}
    job_id = _as_str(body.get("job_id") or body.get("jobId")).strip()
    job = _load_dry_run_job(store, job_id)
    if not job:
        return 404, {"ok": False, "error": "dry_run_job_not_found"}
    if _now_ts() > float(job.get("expires_ts") or 0):
        return 409, {"ok": False, "error": "dry_run_job_expired", "job_id": job_id}
    expected = body.get("expected_eligible_count")
    if expected is not None and _coerce_int(expected, -1) != int(job.get("eligible_count") or 0):
        return 409, {"ok": False, "error": "dry_run_plan_stale", "job_id": job_id}
    manifest_path = _manifest_path(store, job_id)
    if not _is_relative_to(manifest_path, Path(store.archive_dir)):
        return 409, {"ok": False, "error": "path_outside_runstore", "job_id": job_id}
    preflight = {"job_id": job_id, "state": "pending", "created_at": _now_iso()}
    try:
        _atomic_write_json(manifest_path, preflight)
    except Exception as exc:
        return 500, {"ok": False, "error": "archive_manifest_write_failed", "detail": str(exc)}

    project_id = _as_str(job.get("project_id")).strip()
    scope = _as_str(job.get("scope")).strip() or "all"
    session_id = _as_str(job.get("session_id")).strip()
    statuses = [_as_str(x).strip() for x in (job.get("terminal_statuses") or []) if _as_str(x).strip()]
    cutoff_ts = float(job.get("cutoff_ts") or 0)
    current_rows = {
        _as_str(row.get("run_id")).strip(): row
        for row in _collect_hot_runs(
            store,
            project_id=project_id,
            cutoff_ts=cutoff_ts,
            include_hidden=True,
            protected_run_ids=protected_run_ids,
        )
    }
    archived: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    failures: list[dict[str, str]] = []
    status_counts: dict[str, int] = {}
    archived_bytes = 0
    affected_session_ids: set[str] = set()

    for run_id in [x for x in (job.get("candidate_run_ids") or []) if _as_str(x).strip()]:
        run_id = _as_str(run_id).strip()
        row = current_rows.get(run_id)
        if not row:
            skipped.append({"run_id": run_id, "reason": "already_archived_or_missing"})
            continue
        if scope == "session" and _as_str(row.get("session_id")).strip() != session_id:
            skipped.append({"run_id": run_id, "reason": "session_changed"})
            continue
        status = _as_str(row.get("status")).strip()
        if status not in statuses:
            skipped.append({"run_id": run_id, "reason": "status_changed_to_" + (status or "unknown")})
            continue
        if not bool(row.get("archive_eligible")):
            skipped.append({"run_id": run_id, "reason": _as_str(row.get("archive_excluded_reason")).strip() or "not_eligible"})
            continue
        bucket = _as_str(row.get("bucket")).strip() or _bucket_for_meta({}, float(row.get("anchor_ts") or 0))
        src = _hot_paths(store, run_id)
        dst = _archive_paths(store, run_id, bucket)
        if not _path_guard_ok(store, run_id, bucket):
            skipped.append({"run_id": run_id, "reason": "path_outside_runstore"})
            continue
        existing_conflict = [kind for kind, path in dst.items() if src[kind].exists() and path.exists()]
        if existing_conflict:
            failures.append({"run_id": run_id, "reason": "archive_target_exists:" + ",".join(existing_conflict)})
            continue
        moved_files: list[dict[str, str]] = []
        try:
            dst["meta"].parent.mkdir(parents=True, exist_ok=True)
            for kind, src_path in src.items():
                if not src_path.exists():
                    continue
                dst_path = dst[kind]
                src_path.replace(dst_path)
                moved_files.append({"kind": kind, "src": str(src_path), "dst": str(dst_path)})
            if not moved_files:
                failures.append({"run_id": run_id, "reason": "no_hot_files_found"})
                continue
        except Exception as exc:
            for item in reversed(moved_files):
                try:
                    src_path = Path(str(item.get("src") or ""))
                    dst_path = Path(str(item.get("dst") or ""))
                    if dst_path.exists() and not src_path.exists():
                        dst_path.replace(src_path)
                except Exception:
                    pass
            failures.append({"run_id": run_id, "reason": str(exc)})
            continue
        remover = getattr(store, "_remove_live_run_index_entry", None)
        if callable(remover):
            try:
                remover(run_id)
            except Exception:
                pass
        archived.append({"run_id": run_id, "bucket": bucket, "status": status, "bytes": int(row.get("bytes") or 0), "files": moved_files})
        sid = _as_str(row.get("session_id")).strip()
        if sid:
            affected_session_ids.add(sid)
        archived_bytes += int(row.get("bytes") or 0)
        status_counts[status] = int(status_counts.get(status) or 0) + 1

    executed_at = _now_iso()
    execute_state = "completed"
    if failures or skipped:
        execute_state = "partial" if archived else "blocked"
    cache_invalidation = _invalidate_runtime_caches(project_id, sorted(affected_session_ids))
    manifest = {
        "schema_version": "runstore_archive_manifest.v1",
        "manifest_id": job_id,
        "job_id": job_id,
        "plan_fingerprint": _as_str(job.get("plan_fingerprint")).strip(),
        "operator": {
            "sender_type": _as_str(body.get("sender_type") or body.get("senderType") or "legacy").strip() or "legacy",
            "sender_id": _as_str(body.get("sender_id") or body.get("senderId")).strip(),
            "sender_name": _as_str(body.get("sender_name") or body.get("senderName")).strip(),
        },
        "job": job,
        "execute_state": execute_state,
        "executed_at": executed_at,
        "archived": archived,
        "skipped": skipped,
        "failures": failures,
        "will_move_attachments": False,
        "will_delete_files": False,
    }
    try:
        _atomic_write_json(manifest_path, manifest)
    except Exception as exc:
        return 500, {"ok": False, "error": "archive_manifest_write_failed", "detail": str(exc)}
    archived_count = len(archived)
    return 200, {
        "ok": True,
        "schema_version": "runstore_archive_execute.v1",
        "job_id": job_id,
        "execute_state": execute_state,
        "executed_at": executed_at,
        "scope": scope,
        "session_id": session_id,
        "cutoff_at": _as_str(job.get("cutoff_at")).strip(),
        "archived_count": archived_count,
        "archived_bytes": archived_bytes,
        "skipped_count": len(skipped),
        "failed_count": len(failures),
        "status_counts": status_counts,
        "manifest_path": str(manifest_path),
        "manifest_id": job_id,
        "cache_invalidation": cache_invalidation,
        "skipped": skipped[:50],
        "failures": failures[:50],
        "hot_summary_delta": {"run_count": -archived_count, "bytes": -archived_bytes},
        "archive_summary_delta": {"run_count": archived_count, "bytes": archived_bytes},
        "rollback_hint": {
            "supported": True,
            "mode": "manifest_guided_manual_restore",
            "summary": "可按 manifest 将本次归档文件移回 hot；P1 不提供自动回滚 API",
        },
        "will_move_attachments": False,
        "will_delete_files": False,
    }
