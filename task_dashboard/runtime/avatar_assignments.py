# -*- coding: utf-8 -*-

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import threading
import time
from typing import Any

from task_dashboard.helpers import atomic_write_text, now_iso, safe_text


AVATAR_ASSIGNMENTS_VERSION = 2
AVATAR_ASSIGNMENTS_FILENAME = "avatar-assignments.v2.json"
_AVATAR_ASSIGNMENTS_CACHE_LOCK = threading.Lock()
_AVATAR_ASSIGNMENTS_CACHE: dict[str, dict[str, Any]] = {}
VALID_AVATAR_IDS = {
    "chief",
    "pmo",
    "planner",
    "prototype",
    "ui",
    "ux",
    "frontend",
    "backend",
    "api",
    "data",
    "runtime",
    "scheduler",
    "ai-engine",
    "adapter",
    "qa",
    "regression",
    "release",
    "ops",
    "sre",
    "alarm",
    "security",
    "compliance",
    "doc",
    "knowledge",
    "collab",
    "announce",
    "meeting",
    "archive",
    "board",
    "org",
    "timeline",
    "message",
    "memo",
    "avatar",
    "inspector",
    "heartbeat",
    "queue",
    "callback",
    "escalate",
    "product",
    "engineer",
    "tester",
    "analyst",
    "designer",
    "mentor",
    "finance",
    "crm",
    "contract",
    "delivery",
    "risk",
    "decision",
    "customer",
    "growth",
    "notion",
    "github",
    "chat",
    "cloud",
    "local",
    "script",
}


def _avatar_assignments_cache_ttl_s() -> float:
    raw = str(os.environ.get("CCB_AVATAR_ASSIGNMENTS_CACHE_TTL_MS") or "").strip()
    if raw:
        try:
            return max(0.0, min(float(int(raw)) / 1000.0, 10.0))
        except Exception:
            pass
    return 3.0


def _avatar_assignments_cache_key(path: Path, project_id: str) -> str:
    return f"{str(path.resolve())}|{str(project_id or '').strip()}"


def _avatar_assignments_runtime_payload(
    *,
    delivery_mode: str,
    cache_age_s: float = 0.0,
) -> dict[str, Any]:
    return {
        "scope": "avatar_assignments",
        "delivery_mode": str(delivery_mode or "fresh_disk"),
        "cache_ttl_ms": int(_avatar_assignments_cache_ttl_s() * 1000),
        "cache_age_ms": int(max(0.0, float(cache_age_s or 0.0)) * 1000),
    }


def _with_avatar_assignments_runtime(
    payload: dict[str, Any],
    *,
    delivery_mode: str,
    cache_age_s: float = 0.0,
) -> dict[str, Any]:
    out = copy.deepcopy(payload if isinstance(payload, dict) else {})
    out["avatar_assignments_runtime"] = _avatar_assignments_runtime_payload(
        delivery_mode=delivery_mode,
        cache_age_s=cache_age_s,
    )
    return out


def invalidate_avatar_assignments_cache(path: Path | None = None) -> None:
    with _AVATAR_ASSIGNMENTS_CACHE_LOCK:
        if path is None:
            _AVATAR_ASSIGNMENTS_CACHE.clear()
            return
        resolved = str(path.resolve())
        for key in list(_AVATAR_ASSIGNMENTS_CACHE.keys()):
            if key.startswith(resolved + "|"):
                _AVATAR_ASSIGNMENTS_CACHE.pop(key, None)


def _normalize_project_path(raw: Any, repo_root: Path) -> Path:
    text = str(raw or "").strip().replace("\\", "/")
    if not text:
        return repo_root.resolve()
    path = Path(text).expanduser()
    if path.is_absolute():
        return path.resolve()

    candidates = [(repo_root / path).resolve()]
    for parent in repo_root.parents:
        candidates.append((parent / path).resolve())
    existing = [item for item in candidates if item.exists()]
    if existing:
        existing.sort(key=lambda item: len(item.parts))
        return existing[0]

    norm = text.strip("/")
    for anchor in (repo_root,) + tuple(repo_root.parents):
        marker = anchor.name.strip()
        if marker and (norm == marker or norm.startswith(marker + "/")):
            return (anchor.parent / norm).resolve()
    return candidates[0]


def avatar_assignments_path(project_cfg: dict[str, Any], repo_root: Path) -> Path:
    project_root = _normalize_project_path(project_cfg.get("project_root_rel"), repo_root)
    return (project_root / "registry" / AVATAR_ASSIGNMENTS_FILENAME).resolve()


def empty_avatar_assignments(project_id: str, path: Path | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": True,
        "version": AVATAR_ASSIGNMENTS_VERSION,
        "project_id": str(project_id or "").strip(),
        "updated_at": "",
        "bySessionId": {},
        "clearedSessionIds": {},
    }
    if path is not None:
        payload["config_path"] = str(path)
    return payload


def normalize_avatar_assignments_payload(
    raw: Any,
    *,
    project_id: str,
    path: Path | None = None,
) -> dict[str, Any]:
    source = raw if isinstance(raw, dict) else {}
    by_session_id: dict[str, str] = {}
    cleared_session_ids: dict[str, bool] = {}

    raw_by_session_id = source.get("bySessionId")
    if isinstance(raw_by_session_id, dict):
        for raw_sid, raw_avatar_id in raw_by_session_id.items():
            sid = safe_text(raw_sid, 160).strip()
            avatar_id = safe_text(raw_avatar_id, 80).strip()
            if sid and avatar_id in VALID_AVATAR_IDS:
                by_session_id[sid] = avatar_id

    raw_cleared = source.get("clearedSessionIds")
    if isinstance(raw_cleared, dict):
        for raw_sid, flag in raw_cleared.items():
            sid = safe_text(raw_sid, 160).strip()
            if sid and bool(flag):
                cleared_session_ids[sid] = True

    payload = empty_avatar_assignments(project_id, path)
    payload["updated_at"] = safe_text(source.get("updated_at") or source.get("updatedAt"), 80).strip()
    payload["bySessionId"] = by_session_id
    payload["clearedSessionIds"] = cleared_session_ids
    return payload


def load_avatar_assignments(
    *,
    project_id: str,
    project_cfg: dict[str, Any],
    repo_root: Path,
) -> dict[str, Any]:
    path = avatar_assignments_path(project_cfg, repo_root)
    cache_ttl_s = _avatar_assignments_cache_ttl_s()
    cache_key = _avatar_assignments_cache_key(path, project_id)
    now_mono = time.monotonic()
    stat = None
    if path.exists():
        try:
            stat = path.stat()
        except Exception:
            stat = None
    if cache_ttl_s > 0:
        with _AVATAR_ASSIGNMENTS_CACHE_LOCK:
            cached = _AVATAR_ASSIGNMENTS_CACHE.get(cache_key)
            if isinstance(cached, dict):
                checked_at = float(cached.get("checked_at_mono") or 0.0)
                age_s = max(0.0, now_mono - checked_at)
                same_file = (
                    int(cached.get("mtime_ns") or -1) == int(getattr(stat, "st_mtime_ns", -2))
                    and int(cached.get("size") or -1) == int(getattr(stat, "st_size", -2))
                )
                payload = cached.get("payload")
                if same_file and age_s <= cache_ttl_s and isinstance(payload, dict):
                    return _with_avatar_assignments_runtime(payload, delivery_mode="memory_cache", cache_age_s=age_s)
    if not path.exists():
        payload = empty_avatar_assignments(project_id, path)
        return _with_avatar_assignments_runtime(payload, delivery_mode="missing_file")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        raw = {}
    payload = normalize_avatar_assignments_payload(raw, project_id=project_id, path=path)
    if cache_ttl_s > 0 and stat is not None:
        with _AVATAR_ASSIGNMENTS_CACHE_LOCK:
            _AVATAR_ASSIGNMENTS_CACHE[cache_key] = {
                "checked_at_mono": now_mono,
                "mtime_ns": int(getattr(stat, "st_mtime_ns", 0)),
                "size": int(getattr(stat, "st_size", 0)),
                "payload": copy.deepcopy(payload),
            }
    return _with_avatar_assignments_runtime(payload, delivery_mode="fresh_disk")


def save_avatar_assignments(
    *,
    payload: dict[str, Any],
    path: Path,
) -> None:
    content = {
        "version": AVATAR_ASSIGNMENTS_VERSION,
        "updated_at": payload.get("updated_at") or now_iso(),
        "bySessionId": dict(payload.get("bySessionId") or {}),
        "clearedSessionIds": dict(payload.get("clearedSessionIds") or {}),
    }
    atomic_write_text(path, json.dumps(content, ensure_ascii=False, indent=2) + "\n")
    invalidate_avatar_assignments_cache(path)


def get_avatar_assignments_response(
    *,
    project_id: str,
    project_cfg: dict[str, Any],
    repo_root: Path,
) -> tuple[int, dict[str, Any]]:
    project_id = safe_text(project_id, 120).strip()
    if not project_id:
        return 400, {"error": "missing project_id"}
    return 200, load_avatar_assignments(
        project_id=project_id,
        project_cfg=project_cfg,
        repo_root=repo_root,
    )


def update_avatar_assignment_response(
    *,
    project_id: str,
    session_id: str,
    avatar_id: str,
    project_cfg: dict[str, Any],
    repo_root: Path,
    session_exists: bool,
) -> tuple[int, dict[str, Any]]:
    project_id = safe_text(project_id, 120).strip()
    session_id = safe_text(session_id, 160).strip()
    avatar_id = safe_text(avatar_id, 80).strip()
    if not project_id:
        return 400, {"error": "missing project_id"}
    if not session_id:
        return 400, {"error": "missing session_id"}
    if not session_exists:
        return 404, {"error": "session not found"}
    if avatar_id and avatar_id not in VALID_AVATAR_IDS:
        return 400, {"error": "invalid avatar_id"}

    path = avatar_assignments_path(project_cfg, repo_root)
    payload = load_avatar_assignments(
        project_id=project_id,
        project_cfg=project_cfg,
        repo_root=repo_root,
    )
    by_session_id = dict(payload.get("bySessionId") or {})
    cleared_session_ids = dict(payload.get("clearedSessionIds") or {})
    if avatar_id:
        by_session_id[session_id] = avatar_id
        cleared_session_ids.pop(session_id, None)
    else:
        by_session_id.pop(session_id, None)
        cleared_session_ids[session_id] = True

    payload["updated_at"] = now_iso()
    payload["bySessionId"] = by_session_id
    payload["clearedSessionIds"] = cleared_session_ids
    save_avatar_assignments(payload=payload, path=path)
    payload["config_path"] = str(path)
    return 200, payload
