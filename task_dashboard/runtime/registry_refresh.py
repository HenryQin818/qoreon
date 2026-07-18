# -*- coding: utf-8 -*-
"""Lightweight CCR/agent-directory refresh scheduling.

SessionStore remains the source of truth. This module only schedules derived
registry materialization and records degraded status when that secondary work
fails.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import secrets
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


CONTACT_FIELDS = {
    "alias",
    "agent_name",
    "channel_name",
    "is_primary",
    "is_deleted",
    "deleted_at",
    "deleted_reason",
    "session_role",
}

_GLOBAL_LOCK = threading.Lock()
_PROJECT_LOCKS: dict[str, threading.Lock] = {}
_PROJECT_TIMERS: dict[str, threading.Timer] = {}
_PROJECT_PENDING: dict[str, dict[str, Any]] = {}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _safe_project_id(project_id: str) -> str:
    text = str(project_id or "").strip()
    return text.replace("/", "_").replace("\\", "_").replace("..", "_") or "unknown"


def _repo_root_from_module() -> Path:
    return Path(__file__).resolve().parents[2]


def _runtime_base_dir(runtime_base_dir: Path | str | None = None) -> Path:
    if runtime_base_dir:
        return Path(runtime_base_dir).expanduser().resolve()
    return (_repo_root_from_module() / ".runtime" / "stable").resolve()


def _workspace_root(workspace_root: Path | str | None = None) -> Path:
    if workspace_root:
        return Path(workspace_root).expanduser().resolve()
    return _repo_root_from_module().resolve()


def _status_path(project_id: str, *, runtime_base_dir: Path | str | None = None) -> Path:
    return _runtime_base_dir(runtime_base_dir) / ".registry-refresh" / f"{_safe_project_id(project_id)}.json"


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp-{secrets.token_hex(6)}")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _write_status(
    project_id: str,
    payload: dict[str, Any],
    *,
    runtime_base_dir: Path | str | None = None,
) -> None:
    _atomic_write_json(_status_path(project_id, runtime_base_dir=runtime_base_dir), payload)


def _degraded_payload(
    *,
    project_id: str,
    reason: str,
    error: Any = "",
    session_id: str = "",
    channel_name: str = "",
    changed_fields: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "project_id": str(project_id or "").strip(),
        "state": "degraded",
        "degraded": True,
        "degraded_reason": str(reason or "registry_refresh_failed").strip() or "registry_refresh_failed",
        "error": str(error or "").strip()[:1000],
        "session_id": str(session_id or "").strip(),
        "channel_name": str(channel_name or "").strip(),
        "changed_fields": list(changed_fields or []),
        "repair_items": [
            {
                "code": "registry_refresh_retry",
                "message": "SessionStore 已保存，可通过后续同项目会话写入或显式刷新重试通讯录派生产物。",
            }
        ],
        "updated_at": _utc_now_iso(),
    }


def _load_bootstrap_module(workspace_root: Path) -> Any:
    script_path = workspace_root / "scripts" / "bootstrap_project_collab.py"
    if not script_path.exists():
        raise FileNotFoundError(f"scripts/bootstrap_project_collab.py not found under {workspace_root}")
    spec = importlib.util.spec_from_file_location("_task_dashboard_bootstrap_project_collab_runtime", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("failed to load bootstrap_project_collab.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_bootstrap_in_process(
    *,
    project_id: str,
    workspace_root: Path,
    session_json: Path | None = None,
) -> dict[str, Any]:
    module = _load_bootstrap_module(workspace_root)
    main_fn = getattr(module, "main", None)
    if not callable(main_fn):
        raise RuntimeError("bootstrap_project_collab.main is not callable")

    argv = [
        "--project-id",
        project_id,
        "--workspace-root",
        str(workspace_root),
        "--config",
        str(workspace_root / "config.toml"),
    ]
    if session_json is not None:
        argv.extend(["--session-json", str(session_json)])

    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        rc = main_fn(argv)
    if int(rc or 0) != 0:
        raise RuntimeError(stdout.getvalue().strip() or f"bootstrap_project_collab failed: {rc}")

    return {
        "ok": True,
        "stdout": stdout.getvalue()[-4000:],
    }


def _project_lock(project_id: str) -> threading.Lock:
    key = _safe_project_id(project_id)
    with _GLOBAL_LOCK:
        lock = _PROJECT_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _PROJECT_LOCKS[key] = lock
        return lock


def _merge_pending(current: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    merged = dict(current or {})
    merged["project_id"] = item.get("project_id") or merged.get("project_id") or ""
    merged["channel_name"] = item.get("channel_name") or merged.get("channel_name") or ""
    merged["session_id"] = item.get("session_id") or merged.get("session_id") or ""
    reasons = list(merged.get("reasons") or [])
    reason = str(item.get("reason") or "").strip()
    if reason and reason not in reasons:
        reasons.append(reason)
    changed = set(str(v or "").strip() for v in (merged.get("changed_fields") or []) if str(v or "").strip())
    changed.update(str(v or "").strip() for v in (item.get("changed_fields") or []) if str(v or "").strip())
    merged["reasons"] = reasons
    merged["changed_fields"] = sorted(changed)
    merged["updated_at"] = _utc_now_iso()
    return merged


def should_refresh_for_update(before: dict[str, Any] | None, update_fields: dict[str, Any] | None) -> tuple[bool, list[str]]:
    """Return whether a session update affects CCR/address-book fields."""
    row = before if isinstance(before, dict) else {}
    fields = update_fields if isinstance(update_fields, dict) else {}
    changed: list[str] = []
    for key in sorted(CONTACT_FIELDS.intersection(fields.keys())):
        next_value = fields.get(key)
        prev_value = row.get(key)
        if key in {"is_primary", "is_deleted"}:
            if bool(next_value) != bool(prev_value):
                changed.append(key)
            continue
        if str(next_value or "").strip() != str(prev_value or "").strip():
            changed.append(key)
    return bool(changed), changed


def schedule_registry_refresh(
    *,
    project_id: str,
    reason: str,
    session_id: str = "",
    channel_name: str = "",
    changed_fields: list[str] | tuple[str, ...] | None = None,
    workspace_root: Path | str | None = None,
    runtime_base_dir: Path | str | None = None,
    session_json: Path | str | None = None,
    debounce_s: float | None = None,
    synchronous: bool = False,
    runner: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Schedule a non-authoritative CCR refresh.

    The caller must never roll back the SessionStore write because of this
    result. A degraded payload is returned only when scheduling itself fails or
    when synchronous test mode runs the refresh immediately.
    """
    pid = str(project_id or "").strip()
    if not pid:
        return _degraded_payload(
            project_id=pid,
            reason="missing_project_id",
            session_id=session_id,
            channel_name=channel_name,
            changed_fields=list(changed_fields or []),
        )

    root = _workspace_root(workspace_root)
    runtime_root = _runtime_base_dir(runtime_base_dir)
    session_json_path = Path(session_json).expanduser().resolve() if session_json else None
    fields = sorted({str(v or "").strip() for v in (changed_fields or []) if str(v or "").strip()})
    pending_item = {
        "project_id": pid,
        "reason": str(reason or "session_store_changed").strip() or "session_store_changed",
        "session_id": str(session_id or "").strip(),
        "channel_name": str(channel_name or "").strip(),
        "changed_fields": fields,
        "updated_at": _utc_now_iso(),
    }

    scheduled_payload = {
        "project_id": pid,
        "state": "scheduled",
        "scheduled": True,
        "degraded": False,
        "reason": pending_item["reason"],
        "session_id": pending_item["session_id"],
        "channel_name": pending_item["channel_name"],
        "changed_fields": fields,
        "workspace_root": str(root),
        "runtime_base_dir": str(runtime_root),
        "updated_at": _utc_now_iso(),
    }

    try:
        _write_status(pid, scheduled_payload, runtime_base_dir=runtime_root)
    except Exception as exc:
        return _degraded_payload(
            project_id=pid,
            reason="registry_refresh_status_write_failed",
            error=exc,
            session_id=session_id,
            channel_name=channel_name,
            changed_fields=fields,
        )

    def _execute() -> None:
        key = _safe_project_id(pid)
        with _GLOBAL_LOCK:
            pending = _PROJECT_PENDING.pop(key, pending_item)
            _PROJECT_TIMERS.pop(key, None)
        lock = _project_lock(pid)
        with lock:
            started = {
                **scheduled_payload,
                "state": "running",
                "scheduled": False,
                "reasons": list(pending.get("reasons") or [pending_item["reason"]]),
                "changed_fields": list(pending.get("changed_fields") or fields),
                "updated_at": _utc_now_iso(),
            }
            try:
                _write_status(pid, started, runtime_base_dir=runtime_root)
                active_runner = runner or _run_bootstrap_in_process
                result = active_runner(project_id=pid, workspace_root=root, session_json=session_json_path)
                done = {
                    **started,
                    "state": "done",
                    "degraded": False,
                    "result": result if isinstance(result, dict) else {"ok": True},
                    "updated_at": _utc_now_iso(),
                }
                _write_status(pid, done, runtime_base_dir=runtime_root)
            except Exception as exc:
                degraded = _degraded_payload(
                    project_id=pid,
                    reason="registry_refresh_failed",
                    error=exc,
                    session_id=str(pending.get("session_id") or session_id),
                    channel_name=str(pending.get("channel_name") or channel_name),
                    changed_fields=list(pending.get("changed_fields") or fields),
                )
                try:
                    _write_status(pid, degraded, runtime_base_dir=runtime_root)
                except Exception:
                    pass

    if synchronous:
        _execute()
        try:
            data = json.loads(_status_path(pid, runtime_base_dir=runtime_root).read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else scheduled_payload
        except Exception:
            return scheduled_payload

    wait_s = debounce_s
    if wait_s is None:
        raw_ms = str(os.environ.get("CCB_REGISTRY_REFRESH_DEBOUNCE_MS") or "").strip()
        if raw_ms:
            try:
                wait_s = max(0.0, min(float(raw_ms) / 1000.0, 30.0))
            except Exception:
                wait_s = 1.5
        else:
            wait_s = 1.5

    key = _safe_project_id(pid)
    with _GLOBAL_LOCK:
        _PROJECT_PENDING[key] = _merge_pending(_PROJECT_PENDING.get(key) or {}, pending_item)
        old_timer = _PROJECT_TIMERS.get(key)
        if old_timer is not None:
            old_timer.cancel()
        timer = threading.Timer(float(wait_s), _execute)
        timer.daemon = True
        _PROJECT_TIMERS[key] = timer
        timer.start()

    return scheduled_payload


def read_registry_refresh_status(
    project_id: str,
    *,
    runtime_base_dir: Path | str | None = None,
) -> dict[str, Any]:
    try:
        data = json.loads(_status_path(project_id, runtime_base_dir=runtime_base_dir).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}
