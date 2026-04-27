# -*- coding: utf-8 -*-

from __future__ import annotations

import re
import threading
import time
from pathlib import Path
from typing import Any

from task_dashboard.domain import normalize_task_status
from task_dashboard.parser_md import extract_excerpt
from task_dashboard.task_identity import (
    resolve_task_reference,
    runtime_base_dir_for_repo,
    strip_markdown_front_matter,
)
from task_dashboard.task_harness import parse_task_harness
from task_dashboard.utils import safe_read_text


ACTIVE_RUN_STATUSES = {"queued", "running", "retry_waiting"}
_TASK_STATUS_RE = re.compile(r"^【([^】]+)】")
_TASK_SUMMARY_FIELD_NAMES = {"任务目标", "目标", "摘要", "说明"}
_TASK_FILE_CACHE_LOCK = threading.Lock()
_TASK_SUMMARY_FILE_CACHE: dict[tuple[str, int, int], str] = {}
_TASK_HARNESS_FILE_CACHE: dict[tuple[str, int, int], dict[str, Any]] = {}
_TASK_FILE_CACHE_MAX = 256


def _as_text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _normalize_task_path(value: Any) -> str:
    text = _as_text(value).replace("\\", "/")
    if not text or text == "未关联任务":
        return ""
    if text.startswith("task:"):
        text = text[5:]
    return text.strip()


def _session_repo_root(session: dict[str, Any]) -> Path | None:
    execution_context = session.get("project_execution_context") if isinstance(session.get("project_execution_context"), dict) else {}
    target_ctx = execution_context.get("target") if isinstance(execution_context.get("target"), dict) else {}
    source_ctx = execution_context.get("source") if isinstance(execution_context.get("source"), dict) else {}
    seen: set[str] = set()
    for raw in (
        session.get("workdir"),
        target_ctx.get("workdir"),
        source_ctx.get("workdir"),
        session.get("worktree_root"),
        target_ctx.get("worktree_root"),
        source_ctx.get("worktree_root"),
    ):
        root_text = _as_text(raw)
        if not root_text or root_text in seen:
            continue
        seen.add(root_text)
        try:
            return Path(root_text).expanduser().resolve()
        except Exception:
            continue
    return None


def _resolved_task_key(task_ref: dict[str, Any]) -> str:
    task_id = _as_text(task_ref.get("task_id"))
    if task_id:
        return f"task_id::{task_id}"
    return _normalize_task_path(task_ref.get("task_path"))


def _action_task_key(action: dict[str, Any]) -> str:
    task_id = _as_text(action.get("task_id"))
    if task_id:
        return f"task_id::{task_id}"
    return _normalize_task_path(action.get("task_path"))


def _resolve_task_reference_for_session(
    *,
    session: dict[str, Any],
    project_id: str,
    task_path: str = "",
    task_id: str = "",
    cache: dict[str, dict[str, str]],
) -> dict[str, str]:
    raw_path = _normalize_task_path(task_path)
    raw_task_id = _as_text(task_id)
    cache_key = f"{raw_task_id}||{raw_path}"
    cached = cache.get(cache_key)
    if isinstance(cached, dict):
        return dict(cached)

    repo_root = _session_repo_root(session)
    if repo_root is None:
        resolved = {
            "task_path": raw_path,
            "task_id": raw_task_id,
            "parent_task_id": "",
            "matched_by": "missing_repo_root",
        }
    else:
        resolved = resolve_task_reference(
            repo_root=repo_root,
            runtime_base_dir=runtime_base_dir_for_repo(repo_root),
            project_id=_as_text(project_id),
            task_path=raw_path,
            task_id=raw_task_id,
        )
    normalized = {
        "task_path": _normalize_task_path(resolved.get("task_path")),
        "task_id": _as_text(resolved.get("task_id")),
        "parent_task_id": _as_text(resolved.get("parent_task_id")),
        "matched_by": _as_text(resolved.get("matched_by")),
    }
    cache[cache_key] = dict(normalized)
    return dict(normalized)


def _task_title_from_path(path: str) -> str:
    raw = _normalize_task_path(path)
    if not raw:
        return ""
    name = raw.split("/")[-1]
    if name.endswith(".md"):
        name = name[:-3]
    return name


def _task_primary_status_from_path(path: str) -> str:
    name = _task_title_from_path(path)
    if not name:
        return ""
    match = _TASK_STATUS_RE.match(name)
    if not match:
        return ""
    normalized = normalize_task_status(match.group(1))
    return _as_text(normalized.get("primary_status"))


def _run_anchor_at(meta: dict[str, Any]) -> str:
    return (
        _as_text(meta.get("finishedAt"))
        or _as_text(meta.get("startedAt"))
        or _as_text(meta.get("createdAt"))
    )


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime())


def _strip_line_prefix(text: str) -> str:
    return re.sub(r"^[\-\*\u2022]\s+", "", text).strip()


def _extract_task_summary_text(md: str) -> str:
    body = strip_markdown_front_matter(md)
    in_summary_block = False
    fallback_lines: list[str] = []
    for raw in body.splitlines():
        line = raw.strip()
        if not line or line.startswith("```"):
            continue
        if line.startswith("更新时间:") or line.startswith("更新时间："):
            continue
        if line.startswith("#"):
            header = line.lstrip("#").strip()
            in_summary_block = header in _TASK_SUMMARY_FIELD_NAMES
            continue
        cleaned = _strip_line_prefix(line)
        if not cleaned:
            continue
        if in_summary_block:
            return cleaned[:200]
        fallback_lines.append(cleaned)
    if fallback_lines:
        return fallback_lines[0][:200]
    excerpt = extract_excerpt(body, max_lines=6, max_chars=200).strip()
    excerpt_lines = [
        _strip_line_prefix(line.strip())
        for line in excerpt.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    for line in excerpt_lines:
        if line and not line.startswith("更新时间:") and not line.startswith("更新时间："):
            return line[:200]
    return ""


def _task_file_signature(path: Path | None) -> tuple[str, int, int] | None:
    if path is None:
        return None
    try:
        stat = path.stat()
    except Exception:
        return None
    return (str(path), int(stat.st_mtime_ns), int(stat.st_size))


def _cache_get_summary(signature: tuple[str, int, int] | None) -> str | None:
    if signature is None:
        return None
    with _TASK_FILE_CACHE_LOCK:
        cached = _TASK_SUMMARY_FILE_CACHE.get(signature)
    return cached if isinstance(cached, str) else None


def _cache_put_summary(signature: tuple[str, int, int] | None, summary: str) -> None:
    if signature is None:
        return
    with _TASK_FILE_CACHE_LOCK:
        _TASK_SUMMARY_FILE_CACHE[signature] = summary
        if len(_TASK_SUMMARY_FILE_CACHE) > _TASK_FILE_CACHE_MAX:
            oldest_key = next(iter(_TASK_SUMMARY_FILE_CACHE))
            _TASK_SUMMARY_FILE_CACHE.pop(oldest_key, None)


def _cache_get_harness(signature: tuple[str, int, int] | None) -> dict[str, Any] | None:
    if signature is None:
        return None
    with _TASK_FILE_CACHE_LOCK:
        cached = _TASK_HARNESS_FILE_CACHE.get(signature)
    return dict(cached) if isinstance(cached, dict) else None


def _cache_put_harness(signature: tuple[str, int, int] | None, roles: dict[str, Any]) -> None:
    if signature is None:
        return
    with _TASK_FILE_CACHE_LOCK:
        _TASK_HARNESS_FILE_CACHE[signature] = {
            "main_owner": roles.get("main_owner"),
            "collaborators": list(roles.get("collaborators") or []),
            "validators": list(roles.get("validators") or []),
            "challengers": list(roles.get("challengers") or []),
            "backup_owners": list(roles.get("backup_owners") or []),
            "management_slot": list(roles.get("management_slot") or []),
            "custom_roles": list(roles.get("custom_roles") or []),
            "executors": list(roles.get("executors") or []),
            "acceptors": list(roles.get("acceptors") or []),
            "reviewers": list(roles.get("reviewers") or []),
            "visual_reviewers": list(roles.get("visual_reviewers") or []),
        }
        if len(_TASK_HARNESS_FILE_CACHE) > _TASK_FILE_CACHE_MAX:
            oldest_key = next(iter(_TASK_HARNESS_FILE_CACHE))
            _TASK_HARNESS_FILE_CACHE.pop(oldest_key, None)


def _clear_task_tracking_file_caches() -> None:
    with _TASK_FILE_CACHE_LOCK:
        _TASK_SUMMARY_FILE_CACHE.clear()
        _TASK_HARNESS_FILE_CACHE.clear()


def _resolve_task_file_path(
    *,
    session: dict[str, Any],
    project_id: str,
    task_path: str,
    task_id: str = "",
    resolve_cache: dict[str, dict[str, str]],
) -> tuple[Path | None, dict[str, str]]:
    resolved = _resolve_task_reference_for_session(
        session=session,
        project_id=project_id,
        task_path=task_path,
        task_id=task_id,
        cache=resolve_cache,
    )
    root = _session_repo_root(session)
    rel_text = _normalize_task_path(resolved.get("task_path"))
    if root is None or not rel_text:
        return None, resolved
    try:
        target = (root / rel_text).resolve()
        target.relative_to(root)
    except Exception:
        return None, resolved
    if not target.is_file():
        return None, resolved
    return target, resolved


def _load_task_summary_text(
    *,
    session: dict[str, Any],
    project_id: str,
    task_path: str,
    task_id: str = "",
    cache: dict[str, str],
    resolve_cache: dict[str, dict[str, str]],
) -> str:
    file_path, resolved = _resolve_task_file_path(
        session=session,
        project_id=project_id,
        task_path=task_path,
        task_id=task_id,
        resolve_cache=resolve_cache,
    )
    cache_key = _resolved_task_key(resolved)
    if not cache_key:
        return ""
    if cache_key in cache:
        return cache[cache_key]
    if file_path is None:
        cache[cache_key] = ""
        return ""
    signature = _task_file_signature(file_path)
    cached_summary = _cache_get_summary(signature)
    if cached_summary is not None:
        cache[cache_key] = cached_summary
        return cached_summary
    try:
        md = safe_read_text(file_path)
    except Exception:
        cache[cache_key] = ""
        return ""
    summary = _extract_task_summary_text(md)
    cache[cache_key] = summary
    _cache_put_summary(signature, summary)
    return summary


def _empty_task_harness_roles() -> dict[str, Any]:
    return {
        "main_owner": None,
        "collaborators": [],
        "validators": [],
        "challengers": [],
        "backup_owners": [],
        "management_slot": [],
        "custom_roles": [],
        "executors": [],
        "acceptors": [],
        "reviewers": [],
        "visual_reviewers": [],
    }


def _load_task_harness_roles(
    *,
    session: dict[str, Any],
    project_id: str,
    task_path: str,
    task_id: str = "",
    cache: dict[str, dict[str, Any]],
    resolve_cache: dict[str, dict[str, str]],
) -> dict[str, Any]:
    file_path, resolved = _resolve_task_file_path(
        session=session,
        project_id=project_id,
        task_path=task_path,
        task_id=task_id,
        resolve_cache=resolve_cache,
    )
    cache_key = _resolved_task_key(resolved)
    if not cache_key:
        return _empty_task_harness_roles()
    if cache_key in cache:
        return dict(cache[cache_key])
    if file_path is None:
        cache[cache_key] = _empty_task_harness_roles()
        return dict(cache[cache_key])
    signature = _task_file_signature(file_path)
    cached_roles = _cache_get_harness(signature)
    if cached_roles is not None:
        cache[cache_key] = dict(cached_roles)
        return dict(cached_roles)
    try:
        md = safe_read_text(file_path)
    except Exception:
        cache[cache_key] = _empty_task_harness_roles()
        return dict(cache[cache_key])
    try:
        root = _session_repo_root(session)
        roles = parse_task_harness(
            root=root or file_path.parent,
            task_root_rel="任务规划",
            project_id=_as_text(project_id),
            item_type="任务",
            markdown=strip_markdown_front_matter(md),
        )
    except Exception:
        roles = _empty_task_harness_roles()
    roles_payload = {
        "main_owner": roles.get("main_owner"),
        "collaborators": list(roles.get("collaborators") or []),
        "validators": list(roles.get("validators") or []),
        "challengers": list(roles.get("challengers") or []),
        "backup_owners": list(roles.get("backup_owners") or []),
        "management_slot": list(roles.get("management_slot") or []),
        "custom_roles": list(roles.get("custom_roles") or []),
        "executors": list(roles.get("executors") or []),
        "acceptors": list(roles.get("acceptors") or []),
        "reviewers": list(roles.get("reviewers") or []),
        "visual_reviewers": list(roles.get("visual_reviewers") or []),
    }
    cache[cache_key] = dict(roles_payload)
    _cache_put_harness(signature, roles_payload)
    return dict(cache[cache_key])


def _source_priority(source: str) -> int:
    order = {
        "task_path": 1,
        "callback_task": 2,
        "target_task_ref": 3,
        "session_primary_task": 4,
        "business_ref": 5,
        "system_merge": 6,
    }
    return order.get(_as_text(source), 99)


def _normalize_receipt_items(value: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in value if isinstance(value, list) else []:
        if not isinstance(row, dict):
            continue
        source_run_id = _as_text(row.get("source_run_id"))
        if not source_run_id:
            continue
        item = {
            "source_run_id": source_run_id,
            "callback_task": _normalize_task_path(row.get("callback_task")),
            "callback_task_id": _as_text(row.get("callback_task_id")),
            "source_agent_name": _as_text(row.get("source_agent_name")),
            "source_session_id": _as_text(row.get("source_session_id")),
            "callback_run_id": _as_text(row.get("callback_run_id")),
            "callback_at": _as_text(row.get("callback_at")),
            "need_confirm": _as_text(row.get("need_confirm")),
            "current_conclusion": _as_text(row.get("current_conclusion")),
            "need_peer": _as_text(row.get("need_peer")),
            "event_type": _as_text(row.get("event_type")).lower(),
        }
        out.append(item)
    out.sort(
        key=lambda item: (
            _as_text(item.get("callback_at")),
            _as_text(item.get("callback_run_id")),
            _as_text(item.get("source_run_id")),
        ),
        reverse=True,
    )
    return out


def _normalize_receipt_pending_actions(value: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in value if isinstance(value, list) else []:
        if not isinstance(row, dict):
            continue
        source_run_id = _as_text(row.get("source_run_id"))
        if not source_run_id:
            continue
        out.append(
            {
                "source_run_id": source_run_id,
                "title": _as_text(row.get("title")),
                "action_text": _as_text(row.get("action_text")),
                "action_kind": _as_text(row.get("action_kind")).lower() or "confirm",
                "callback_run_id": _as_text(row.get("callback_run_id")),
                "callback_at": _as_text(row.get("callback_at")),
            }
        )
    out.sort(
        key=lambda item: (
            _as_text(item.get("callback_at")),
            _as_text(item.get("callback_run_id")),
            _as_text(item.get("source_run_id")),
        ),
        reverse=True,
    )
    return out


def _extract_task_candidates(
    meta: dict[str, Any],
    *,
    include_business_refs: bool = True,
) -> list[dict[str, str]]:
    seen: set[tuple[str, str]] = set()
    out: list[dict[str, str]] = []

    def _append(path_value: Any, source: str, *, task_id: Any = "") -> None:
        path = _normalize_task_path(path_value)
        normalized_task_id = _as_text(task_id)
        if not path and not normalized_task_id:
            return
        dedupe_key = (normalized_task_id, path)
        if dedupe_key in seen:
            return
        seen.add(dedupe_key)
        out.append(
            {
                "task_path": path,
                "task_id": normalized_task_id,
                "source": source,
            }
        )

    _append(meta.get("task_path"), "task_path", task_id=meta.get("task_id"))
    _append(meta.get("callback_task"), "callback_task", task_id=meta.get("callback_task_id"))

    for item in _normalize_receipt_items(meta.get("receipt_items")):
        _append(item.get("callback_task"), "callback_task", task_id=item.get("callback_task_id"))

    if include_business_refs:
        for row in meta.get("business_refs") if isinstance(meta.get("business_refs"), list) else []:
            if not isinstance(row, dict):
                continue
            ref_type = _as_text(row.get("type"))
            if ref_type and ref_type != "任务":
                continue
            _append(row.get("path"), "business_ref", task_id=row.get("task_id"))

    return out


def _task_status_rank(status: str) -> int:
    order = {
        "进行中": 0,
        "待验收": 1,
        "待办": 2,
        "暂缓": 3,
        "已完成": 4,
    }
    return order.get(_as_text(status), 99)


def _discover_session_primary_task_path(session: dict[str, Any]) -> str:
    root = _session_repo_root(session)
    channel_name = _as_text(session.get("channel_name"))
    if root is None or not channel_name:
        return ""
    try:
        task_dir = (root / "任务规划" / channel_name / "任务").resolve()
        task_dir.relative_to(root)
    except Exception:
        return ""
    if not task_dir.is_dir():
        return ""

    candidates: list[dict[str, Any]] = []
    for task_file in task_dir.glob("*.md"):
        if not task_file.is_file():
            continue
        try:
            resolved = task_file.resolve()
            resolved.relative_to(root)
            stat = resolved.stat()
        except Exception:
            continue
        status = _task_primary_status_from_path(str(resolved))
        rank = _task_status_rank(status)
        if rank >= 99:
            continue
        candidates.append(
            {
                "task_path": _normalize_task_path(str(resolved.relative_to(root))),
                "rank": rank,
                "mtime": float(getattr(stat, "st_mtime", 0.0) or 0.0),
            }
        )
    if not candidates:
        return ""
    candidates.sort(key=lambda item: _as_text(item.get("task_path")), reverse=True)
    candidates.sort(key=lambda item: float(item.get("mtime") or 0.0), reverse=True)
    candidates.sort(
        key=lambda item: int(item["rank"]) if item.get("rank") is not None else 99
    )
    return _as_text(candidates[0].get("task_path"))


def _task_row_anchor(row: dict[str, Any] | None) -> str:
    if not isinstance(row, dict):
        return ""
    return (
        _as_text(row.get("latest_action_at"))
        or _as_text(row.get("last_seen_at"))
        or _as_text(row.get("first_seen_at"))
    )


def _is_terminal_task_row(row: dict[str, Any] | None) -> bool:
    if not isinstance(row, dict):
        return False
    primary_status = _as_text(row.get("task_primary_status"))
    if primary_status in {"已完成", "暂缓"}:
        return True
    if primary_status in {"进行中", "待办", "待验收"}:
        return False
    return _as_text(row.get("latest_action_kind")).lower() == "done"


def _pick_latest_open_task_key(
    task_rows: dict[str, dict[str, Any]],
    *,
    exclude_key: str = "",
) -> str:
    best_key = ""
    best_anchor = ""
    for task_key, row in task_rows.items():
        if not task_key or task_key == exclude_key:
            continue
        if _is_terminal_task_row(row):
            continue
        anchor = _task_row_anchor(row)
        if not anchor:
            continue
        if (not best_key) or anchor > best_anchor:
            best_key = task_key
            best_anchor = anchor
    return best_key


def _build_missing_owner() -> dict[str, Any]:
    return {
        "agent_name": "",
        "alias": "",
        "session_id": None,
        "state": "missing",
    }


def _build_current_session_owner(session: dict[str, Any], *, state: str = "confirmed") -> dict[str, Any]:
    alias = _as_text(session.get("alias")) or _as_text(session.get("display_name")) or _as_text(session.get("channel_name"))
    agent_name = alias or _as_text(session.get("channel_name")) or _as_text(session.get("id"))
    return {
        "agent_name": agent_name,
        "alias": alias or agent_name,
        "session_id": _as_text(session.get("id")) or None,
        "state": state if state in {"confirmed", "pending", "missing"} else "missing",
    }


def _build_pending_callback_owner(meta: dict[str, Any], *, current_session_id: str) -> dict[str, Any] | None:
    callback_to = meta.get("callback_to") if isinstance(meta.get("callback_to"), dict) else {}
    target_session_id = _as_text(callback_to.get("session_id"))
    if not target_session_id or target_session_id == current_session_id:
        return None

    sender_agent_ref = meta.get("sender_agent_ref") if isinstance(meta.get("sender_agent_ref"), dict) else {}
    communication_view = meta.get("communication_view") if isinstance(meta.get("communication_view"), dict) else {}
    alias = (
        _as_text(sender_agent_ref.get("alias"))
        or _as_text(sender_agent_ref.get("agent_name"))
        or _as_text(meta.get("sender_name"))
        or _as_text(communication_view.get("source_agent_name"))
    )
    agent_name = _as_text(sender_agent_ref.get("agent_name")) or alias
    if not target_session_id and not agent_name and not alias:
        return None
    return {
        "agent_name": agent_name,
        "alias": alias or agent_name,
        "session_id": target_session_id or None,
        "state": "pending",
    }


def _build_task_action_from_run(meta: dict[str, Any], task_ref: dict[str, str]) -> dict[str, Any]:
    task_path = _normalize_task_path(task_ref.get("task_path"))
    task_id = _as_text(task_ref.get("task_id"))
    parent_task_id = _as_text(task_ref.get("parent_task_id"))
    status = _as_text(meta.get("status")).lower()
    latest_text = _as_text(meta.get("lastPreview")) or _as_text(meta.get("partialPreview")) or _as_text(meta.get("messagePreview"))
    primary_status = _task_primary_status_from_path(task_path)
    action_kind = "update"
    action_status = "done" if status == "done" else "pending"
    if status in ACTIVE_RUN_STATUSES:
        action_kind = "start"
        action_status = "pending"
    elif status == "error":
        action_kind = "block"
        action_status = "error"
    elif status == "interrupted":
        action_kind = "pause"
        action_status = "interrupted"
    elif status == "done" and primary_status == "已完成":
        action_kind = "done"
        action_status = "done"
    text = latest_text
    if not text:
        if action_kind == "start":
            text = "任务已进入正式推进态"
        elif action_kind == "block":
            text = "任务执行出现错误，需要后续处理"
        elif action_kind == "pause":
            text = "任务执行被中断，待后续恢复"
        elif action_kind == "done":
            text = "任务执行完成"
        else:
            text = "任务有阶段性更新"
    return {
        "task_path": task_path,
        "task_id": task_id,
        "parent_task_id": parent_task_id,
        "task_title": _task_title_from_path(task_path),
        "action_kind": action_kind,
        "action_text": text,
        "status": action_status,
        "source_run_id": _as_text(meta.get("id")),
        "callback_run_id": "",
        "source_channel": _as_text(meta.get("channelName")),
        "source_agent_name": _as_text(meta.get("sender_name")),
        "at": _run_anchor_at(meta),
    }


def _build_task_actions_from_receipts(
    meta: dict[str, Any],
    *,
    session: dict[str, Any],
    project_id: str,
    resolve_cache: dict[str, dict[str, str]],
) -> list[dict[str, Any]]:
    items_by_source = {
        _as_text(item.get("source_run_id")): item
        for item in _normalize_receipt_items(meta.get("receipt_items"))
        if _as_text(item.get("source_run_id"))
    }
    out: list[dict[str, Any]] = []
    for action in _normalize_receipt_pending_actions(meta.get("receipt_pending_actions")):
        item = items_by_source.get(_as_text(action.get("source_run_id"))) or {}
        resolved = _resolve_task_reference_for_session(
            session=session,
            project_id=project_id,
            task_path=_as_text(item.get("callback_task")),
            task_id=_as_text(item.get("callback_task_id")),
            cache=resolve_cache,
        )
        task_path = _normalize_task_path(resolved.get("task_path"))
        if not task_path and not _as_text(resolved.get("task_id")):
            continue
        out.append(
            {
                "task_path": task_path,
                "task_id": _as_text(resolved.get("task_id")),
                "parent_task_id": _as_text(resolved.get("parent_task_id")),
                "task_title": _task_title_from_path(task_path),
                "action_kind": _as_text(action.get("action_kind")).lower() or "confirm",
                "action_text": _as_text(action.get("action_text")) or _as_text(action.get("title")) or "请查看回执详情。",
                "status": "pending",
                "source_run_id": _as_text(action.get("source_run_id")),
                "callback_run_id": _as_text(action.get("callback_run_id")),
                "source_channel": _as_text(meta.get("channelName")),
                "source_agent_name": _as_text(item.get("source_agent_name")) or _as_text(meta.get("sender_name")),
                "at": _as_text(action.get("callback_at")) or _run_anchor_at(meta),
            }
        )
    return out


def _action_preference(action: dict[str, Any]) -> tuple[int, str]:
    status = _as_text(action.get("status")).lower()
    kind = _as_text(action.get("action_kind")).lower()
    if status == "pending":
        return (4, kind)
    if status == "error":
        return (3, kind)
    if status == "interrupted":
        return (2, kind)
    if kind == "done":
        return (1, kind)
    return (0, kind)


def _pick_current_task_path(
    runs: list[dict[str, Any]],
    *,
    session: dict[str, Any],
    store: Any,
    active_run_id: str,
) -> tuple[dict[str, str], str]:
    if active_run_id:
        active_meta = store.load_meta(active_run_id) if hasattr(store, "load_meta") else None
        if isinstance(active_meta, dict):
            candidates = _extract_task_candidates(active_meta, include_business_refs=False)
            if candidates:
                first = candidates[0]
                return {
                    "task_path": _as_text(first.get("task_path")),
                    "task_id": _as_text(first.get("task_id")),
                }, _as_text(first.get("source"))
    for meta in runs:
        candidates = _extract_task_candidates(
            meta if isinstance(meta, dict) else {},
            include_business_refs=False,
        )
        if candidates:
            first = candidates[0]
            return {
                "task_path": _as_text(first.get("task_path")),
                "task_id": _as_text(first.get("task_id")),
            }, _as_text(first.get("source"))
    fallback_task_path = _discover_session_primary_task_path(session)
    if fallback_task_path:
        return {"task_path": fallback_task_path, "task_id": ""}, "session_primary_task"
    return {"task_path": "", "task_id": ""}, ""


def _build_task_row(
    *,
    session: dict[str, Any],
    project_id: str,
    task_ref: dict[str, str],
    source: str,
    at: str,
    task_summary_cache: dict[str, str],
    task_harness_cache: dict[str, dict[str, Any]],
    resolve_cache: dict[str, dict[str, str]],
) -> dict[str, Any]:
    task_path = _normalize_task_path(task_ref.get("task_path"))
    task_id = _as_text(task_ref.get("task_id"))
    parent_task_id = _as_text(task_ref.get("parent_task_id"))
    task_harness = _load_task_harness_roles(
        session=session,
        project_id=project_id,
        task_path=task_path,
        task_id=task_id,
        cache=task_harness_cache,
        resolve_cache=resolve_cache,
    )
    return {
        "task_path": task_path,
        "task_id": task_id,
        "parent_task_id": parent_task_id,
        "task_title": _task_title_from_path(task_path),
        "task_primary_status": _task_primary_status_from_path(task_path),
        "task_summary_text": _load_task_summary_text(
            session=session,
            project_id=project_id,
            task_path=task_path,
            task_id=task_id,
            cache=task_summary_cache,
            resolve_cache=resolve_cache,
        ),
        "relation": "tracking",
        "source": _as_text(source) or "system_merge",
        "first_seen_at": at,
        "last_seen_at": at,
        "latest_action_at": "",
        "latest_action_kind": "",
        "latest_action_text": "",
        "is_current": False,
        "main_owner": task_harness.get("main_owner"),
        "collaborators": task_harness.get("collaborators") or [],
        "validators": task_harness.get("validators") or [],
        "challengers": task_harness.get("challengers") or [],
        "backup_owners": task_harness.get("backup_owners") or [],
        "management_slot": task_harness.get("management_slot") or [],
        "custom_roles": task_harness.get("custom_roles") or [],
        "executors": task_harness.get("executors") or [],
        "acceptors": task_harness.get("acceptors") or [],
        "reviewers": task_harness.get("reviewers") or [],
        "visual_reviewers": task_harness.get("visual_reviewers") or [],
    }


def build_session_task_tracking(
    *,
    session: dict[str, Any],
    store: Any,
    project_id: str,
    session_id: str,
    runtime_state: dict[str, Any],
    run_limit: int = 80,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "version": "v1.1",
        "current_task_ref": None,
        "conversation_task_refs": [],
        "recent_task_actions": [],
        "updated_at": _as_text(runtime_state.get("updated_at")) or _now_iso(),
    }
    pid = _as_text(project_id)
    sid = _as_text(session_id)
    if not (pid and sid):
        return payload

    runs = store.list_runs(
        project_id=pid,
        session_id=sid,
        limit=max(1, min(int(run_limit or 80), 120)),
        payload_mode="light",
    )
    runs = [row for row in runs if isinstance(row, dict)]
    if not runs:
        return payload

    current_task_seed, current_source = _pick_current_task_path(
        runs,
        session=session,
        store=store,
        active_run_id=_as_text(runtime_state.get("active_run_id")),
    )
    task_summary_cache: dict[str, str] = {}
    task_harness_cache: dict[str, dict[str, Any]] = {}
    task_resolve_cache: dict[str, dict[str, str]] = {}
    task_rows: dict[str, dict[str, Any]] = {}
    task_latest_meta: dict[str, dict[str, Any]] = {}
    task_pending: dict[str, bool] = {}
    action_rows: list[dict[str, Any]] = []
    current_task_ref = _resolve_task_reference_for_session(
        session=session,
        project_id=pid,
        task_path=_as_text(current_task_seed.get("task_path")),
        task_id=_as_text(current_task_seed.get("task_id")),
        cache=task_resolve_cache,
    )
    current_task_key = _resolved_task_key(current_task_ref)

    for meta in reversed(runs):
        candidates = _extract_task_candidates(meta)
        if not candidates:
            continue
        at = _run_anchor_at(meta)
        for cand in candidates:
            resolved = _resolve_task_reference_for_session(
                session=session,
                project_id=pid,
                task_path=_as_text(cand.get("task_path")),
                task_id=_as_text(cand.get("task_id")),
                cache=task_resolve_cache,
            )
            task_key = _resolved_task_key(resolved)
            if not task_key:
                continue
            row = task_rows.get(task_key)
            if row is None:
                row = _build_task_row(
                    session=session,
                    project_id=pid,
                    task_ref=resolved,
                    source=_as_text(cand.get("source")) or "system_merge",
                    at=at,
                    task_summary_cache=task_summary_cache,
                    task_harness_cache=task_harness_cache,
                    resolve_cache=task_resolve_cache,
                )
                task_rows[task_key] = row
            else:
                row["last_seen_at"] = at or _as_text(row.get("last_seen_at"))
                current_source_priority = _source_priority(_as_text(row.get("source")))
                candidate_priority = _source_priority(_as_text(cand.get("source")))
                if candidate_priority < current_source_priority:
                    row["source"] = _as_text(cand.get("source")) or _as_text(row.get("source"))

    if current_task_key and current_task_key not in task_rows:
        task_rows[current_task_key] = _build_task_row(
            session=session,
            project_id=pid,
            task_ref=current_task_ref,
            source=current_source or "session_primary_task",
            at=_as_text(payload.get("updated_at")),
            task_summary_cache=task_summary_cache,
            task_harness_cache=task_harness_cache,
            resolve_cache=task_resolve_cache,
        )

    for meta in runs:
        for cand in _extract_task_candidates(meta):
            resolved = _resolve_task_reference_for_session(
                session=session,
                project_id=pid,
                task_path=_as_text(cand.get("task_path")),
                task_id=_as_text(cand.get("task_id")),
                cache=task_resolve_cache,
            )
            task_key = _resolved_task_key(resolved)
            if not task_key or task_key not in task_rows:
                continue
            action = _build_task_action_from_run(meta, resolved)
            action_rows.append(action)
            row = task_rows[task_key]
            latest_at = _as_text(row.get("latest_action_at"))
            action_at = _as_text(action.get("at"))
            if (not latest_at) or action_at >= latest_at:
                row["latest_action_at"] = action_at
                row["latest_action_kind"] = _as_text(action.get("action_kind"))
                row["latest_action_text"] = _as_text(action.get("action_text"))
                task_latest_meta[task_key] = meta

        receipt_actions = _build_task_actions_from_receipts(
            meta,
            session=session,
            project_id=pid,
            resolve_cache=task_resolve_cache,
        )
        if receipt_actions:
            action_rows.extend(receipt_actions)
            for action in receipt_actions:
                action_key = (
                    f"task_id::{_as_text(action.get('task_id'))}"
                    if _as_text(action.get("task_id"))
                    else _normalize_task_path(action.get("task_path"))
                )
                if not action_key or action_key not in task_rows:
                    continue
                task_pending[action_key] = True
                row = task_rows[action_key]
                current_pref = _action_preference(
                    {
                        "status": "pending" if _as_text(row.get("latest_action_kind")) in {"confirm", "fix", "recover"} else "",
                        "action_kind": _as_text(row.get("latest_action_kind")),
                    }
                )
                candidate_pref = _action_preference(action)
                latest_at = _as_text(row.get("latest_action_at"))
                action_at = _as_text(action.get("at"))
                if candidate_pref > current_pref or ((candidate_pref == current_pref) and ((not latest_at) or action_at >= latest_at)):
                    row["latest_action_at"] = action_at
                    row["latest_action_kind"] = _as_text(action.get("action_kind"))
                    row["latest_action_text"] = _as_text(action.get("action_text"))
                    task_latest_meta[action_key] = meta

    current_row = task_rows.get(current_task_key) if current_task_key else None
    if current_row is None or _is_terminal_task_row(current_row):
        latest_open_task_key = _pick_latest_open_task_key(task_rows, exclude_key=current_task_key)
        if latest_open_task_key:
            promoted_row = task_rows.get(latest_open_task_key) or {}
            current_task_key = latest_open_task_key
            current_task_ref = {
                "task_path": _normalize_task_path(promoted_row.get("task_path")),
                "task_id": _as_text(promoted_row.get("task_id")),
                "parent_task_id": _as_text(promoted_row.get("parent_task_id")),
            }
            current_source = _as_text(promoted_row.get("source")) or "system_merge"
        else:
            session_primary_task_path = _discover_session_primary_task_path(session)
            if session_primary_task_path:
                session_primary_ref = _resolve_task_reference_for_session(
                    session=session,
                    project_id=pid,
                    task_path=session_primary_task_path,
                    cache=task_resolve_cache,
                )
                session_primary_key = _resolved_task_key(session_primary_ref)
                if session_primary_key and session_primary_key not in task_rows:
                    task_rows[session_primary_key] = _build_task_row(
                        session=session,
                        project_id=pid,
                        task_ref=session_primary_ref,
                        source="session_primary_task",
                        at=_as_text(payload.get("updated_at")),
                        task_summary_cache=task_summary_cache,
                        task_harness_cache=task_harness_cache,
                        resolve_cache=task_resolve_cache,
                    )
                session_primary_row = task_rows.get(session_primary_key) if session_primary_key else None
                if session_primary_key and session_primary_row is not None and not _is_terminal_task_row(session_primary_row):
                    current_task_ref = session_primary_ref
                    current_task_key = session_primary_key
                    current_source = "session_primary_task"

    conversation_refs: list[dict[str, Any]] = []
    for task_key, row in task_rows.items():
        latest_meta = task_latest_meta.get(task_key) or {}
        if task_key == current_task_key:
            row["relation"] = "current"
            row["is_current"] = True
        elif _as_text(row.get("latest_action_kind")) == "create":
            row["relation"] = "created"
        else:
            row["relation"] = "tracking"

        next_owner = _build_missing_owner()
        latest_status = _as_text(latest_meta.get("status")).lower()
        if task_pending.get(task_key):
            next_owner = _build_current_session_owner(session, state="confirmed")
        elif latest_status in ACTIVE_RUN_STATUSES:
            next_owner = _build_current_session_owner(session, state="confirmed")
        else:
            pending_owner = _build_pending_callback_owner(latest_meta, current_session_id=sid)
            if pending_owner:
                next_owner = pending_owner
        row["next_owner"] = next_owner
        conversation_refs.append(row)

    conversation_refs.sort(
        key=lambda item: (
            _as_text(item.get("latest_action_at")),
            _as_text(item.get("last_seen_at")),
            _as_text(item.get("task_path")),
        ),
        reverse=True,
    )
    payload["conversation_task_refs"] = conversation_refs[:20]

    if current_task_key and current_task_key in task_rows:
        current = dict(task_rows[current_task_key])
        current.pop("first_seen_at", None)
        current.pop("last_seen_at", None)
        current.pop("is_current", None)
        current["relation"] = "current"
        current["source"] = current_source or _as_text(current.get("source")) or "task_path"
        payload["current_task_ref"] = current

    dedup_actions: list[dict[str, Any]] = []
    seen_action_keys: set[tuple[str, str, str, str]] = set()
    for action in sorted(
        action_rows,
        key=lambda item: (
            1 if current_task_key and _action_task_key(item) == current_task_key else 0,
            _action_preference(item),
            _as_text(item.get("at")),
            _as_text(item.get("callback_run_id")),
            _as_text(item.get("source_run_id")),
            _as_text(item.get("task_path")),
        ),
        reverse=True,
    ):
        key = (
            _as_text(action.get("task_id")) or _as_text(action.get("task_path")),
            _as_text(action.get("action_kind")),
            _as_text(action.get("at")),
            _as_text(action.get("source_run_id")),
        )
        if key in seen_action_keys:
            continue
        seen_action_keys.add(key)
        dedup_actions.append(action)
        if len(dedup_actions) >= 10:
            break
    payload["recent_task_actions"] = dedup_actions

    latest_updated = ""
    for row in conversation_refs:
        at = _as_text(row.get("latest_action_at")) or _as_text(row.get("last_seen_at"))
        if at and at > latest_updated:
            latest_updated = at
    if latest_updated:
        payload["updated_at"] = latest_updated
    return payload
