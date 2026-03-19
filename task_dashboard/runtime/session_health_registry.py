# -*- coding: utf-8 -*-

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any, Callable

from task_dashboard.config import load_dashboard_config
from task_dashboard.helpers import now_iso as _now_iso, parse_rfc3339_ts as _parse_rfc3339_ts, read_json_file, write_json_file
from task_dashboard.session_health import load_project_session_health_config


class SessionHealthRuntimeRegistry:
    def __init__(
        self,
        *,
        store: Any,
        build_payload: Callable[[str], dict[str, Any]],
        environment_name: str = "stable",
        config_loader: Callable[[], dict[str, Any]] | None = None,
    ) -> None:
        self.store = store
        self.build_payload = build_payload
        self.environment_name = str(environment_name or "stable").strip() or "stable"
        self._config_loader = config_loader
        self._lock = threading.Lock()
        self._project_locks: dict[str, threading.Lock] = {}
        self._states: dict[str, dict[str, Any]] = {}
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop_event.clear()
            thread = threading.Thread(
                target=self._loop,
                name="session-health-registry",
                daemon=True,
            )
            self._thread = thread
            thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    def get_payload(self, project_id: str, *, refresh: bool = False) -> dict[str, Any]:
        pid = str(project_id or "").strip()
        if not pid:
            return {"error": "missing project_id"}
        if refresh:
            return self.refresh_project(pid, reason="manual")
        payload = read_json_file(self._snapshot_path(pid))
        if not payload:
            return self.refresh_project(pid, reason="bootstrap")
        return self._decorate_payload(pid, payload)

    def refresh_project(self, project_id: str, *, reason: str = "manual") -> dict[str, Any]:
        pid = str(project_id or "").strip()
        if not pid:
            return {"error": "missing project_id"}
        lock = self._project_lock(pid)
        with lock:
            started_at = _now_iso()
            self._set_state(
                pid,
                state="running",
                running=True,
                last_started_at=started_at,
                last_refresh_reason=str(reason or "manual"),
                last_error="",
            )
            t0 = time.time()
            try:
                payload = dict(self.build_payload(pid) or {})
                finished_at = _now_iso()
                duration_ms = int(max(0.0, time.time() - t0) * 1000)
                payload = self._decorate_payload(
                    pid,
                    payload,
                    runtime_patch={
                        "state": "idle",
                        "running": False,
                        "last_started_at": started_at,
                        "last_completed_at": finished_at,
                        "last_refresh_reason": str(reason or "manual"),
                        "last_duration_ms": duration_ms,
                        "last_error": "",
                    },
                )
                write_json_file(self._snapshot_path(pid), payload)
                self._set_state(
                    pid,
                    state="idle",
                    running=False,
                    last_started_at=started_at,
                    last_completed_at=finished_at,
                    last_refresh_reason=str(reason or "manual"),
                    last_duration_ms=duration_ms,
                    last_error="",
                )
                return payload
            except Exception as exc:
                finished_at = _now_iso()
                self._set_state(
                    pid,
                    state="error",
                    running=False,
                    last_started_at=started_at,
                    last_completed_at=finished_at,
                    last_refresh_reason=str(reason or "manual"),
                    last_error=str(exc),
                )
                payload = read_json_file(self._snapshot_path(pid))
                if payload:
                    return self._decorate_payload(
                        pid,
                        payload,
                        runtime_patch={
                            "state": "error",
                            "running": False,
                            "last_started_at": started_at,
                            "last_completed_at": finished_at,
                            "last_refresh_reason": str(reason or "manual"),
                            "last_error": str(exc),
                        },
                    )
                raise

    def update_project_config(
        self,
        project_id: str,
        *,
        enabled: bool | None = None,
        interval_minutes: int | None = None,
    ) -> dict[str, Any]:
        pid = str(project_id or "").strip()
        if not pid:
            return {"error": "missing project_id"}
        now = time.time()
        patch: dict[str, Any] = {}
        if enabled is not None:
            patch["enabled"] = bool(enabled)
        if interval_minutes is not None:
            patch["interval_minutes"] = int(interval_minutes)
        self._set_state(pid, config_updated_at=_now_iso(), config_patch=patch, due_at_ts=now)
        payload = read_json_file(self._snapshot_path(pid))
        if payload:
            return self._decorate_payload(pid, payload)
        return self.get_payload(pid, refresh=False)

    def automation_summary(self) -> dict[str, Any]:
        project_ids = self._list_project_ids()
        enabled_count = 0
        rows = []
        for pid in project_ids:
            cfg = load_project_session_health_config(pid)
            if cfg.get("enabled"):
                enabled_count += 1
            rows.append(
                {
                    "project_id": pid,
                    "project_name": cfg.get("project_name") or pid,
                    "enabled": bool(cfg.get("enabled")),
                    "interval_minutes": int(cfg.get("interval_minutes") or 0),
                }
            )
        return {
            "project_count": len(project_ids),
            "enabled_count": enabled_count,
            "items": rows,
        }

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                for pid in self._list_project_ids():
                    cfg = load_project_session_health_config(pid)
                    runtime = self._current_runtime(pid, cfg)
                    if not bool(cfg.get("enabled")):
                        self._set_state(
                            pid,
                            state="disabled",
                            running=False,
                            next_due_at="",
                        )
                        continue
                    due_ts = float(runtime.get("due_at_ts") or 0.0)
                    now_ts = time.time()
                    if due_ts and now_ts < due_ts:
                        continue
                    self.refresh_project(pid, reason="auto")
            except Exception:
                pass
            self._stop_event.wait(15.0)

    def _load_cfg(self) -> dict[str, Any]:
        if callable(self._config_loader):
            cfg = self._config_loader()
            return cfg if isinstance(cfg, dict) else {}
        script_dir = Path(__file__).resolve().parents[2]
        try:
            cfg = load_dashboard_config(script_dir)
        except Exception:
            return {}
        return cfg if isinstance(cfg, dict) else {}

    def _list_project_ids(self) -> list[str]:
        cfg = self._load_cfg()
        items = cfg.get("projects")
        if not isinstance(items, list):
            return []
        out: list[str] = []
        for row in items:
            if not isinstance(row, dict):
                continue
            pid = str(row.get("id") or "").strip()
            if pid:
                out.append(pid)
        return out

    def _project_lock(self, project_id: str) -> threading.Lock:
        pid = str(project_id or "").strip()
        with self._lock:
            lock = self._project_locks.get(pid)
            if lock is None:
                lock = threading.Lock()
                self._project_locks[pid] = lock
            return lock

    def _state_root(self) -> Path:
        return Path(self.store.runs_dir).parent / ".run" / "session_health"

    def _snapshot_path(self, project_id: str) -> Path:
        return self._state_root() / f"{str(project_id or '').strip()}.json"

    def _set_state(self, target_project_id: str, **patch: Any) -> dict[str, Any]:
        pid = str(target_project_id or "").strip()
        with self._lock:
            base = dict(self._states.get(pid) or {})
            base.update(patch)
            self._states[pid] = base
            return dict(base)

    def _current_runtime(self, project_id: str, cfg: dict[str, Any], payload: dict[str, Any] | None = None) -> dict[str, Any]:
        pid = str(project_id or "").strip()
        with self._lock:
            base = dict(self._states.get(pid) or {})
        snapshot = payload if isinstance(payload, dict) and payload else read_json_file(self._snapshot_path(pid))
        generated_at = str((snapshot or {}).get("generated_at") or base.get("last_completed_at") or "").strip()
        enabled = bool(cfg.get("enabled"))
        interval_minutes = int(cfg.get("interval_minutes") or 0)
        generated_ts = _parse_rfc3339_ts(generated_at) if generated_at else 0.0
        due_at_ts = float(base.get("due_at_ts") or 0.0)
        if enabled:
            if generated_ts > 0:
                due_at_ts = max(due_at_ts, generated_ts + (interval_minutes * 60))
            else:
                due_at_ts = due_at_ts or 0.0
        else:
            due_at_ts = 0.0
        next_due_at = _now_iso() if enabled and due_at_ts <= 0 else time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(due_at_ts)) if enabled else ""
        state = str(base.get("state") or ("disabled" if not enabled else "idle")).strip() or "idle"
        if not enabled:
            state = "disabled"
        runtime = {
            "project_id": pid,
            "enabled": enabled,
            "interval_minutes": interval_minutes,
            "state": state,
            "running": bool(base.get("running")),
            "last_started_at": str(base.get("last_started_at") or "").strip(),
            "last_completed_at": str(base.get("last_completed_at") or generated_at).strip(),
            "last_refresh_reason": str(base.get("last_refresh_reason") or "").strip(),
            "last_duration_ms": int(base.get("last_duration_ms") or 0),
            "last_error": str(base.get("last_error") or "").strip(),
            "next_due_at": next_due_at,
            "due_at_ts": due_at_ts,
            "config_updated_at": str(base.get("config_updated_at") or "").strip(),
        }
        self._set_state(pid, **runtime)
        return runtime

    def _decorate_payload(
        self,
        project_id: str,
        payload: dict[str, Any],
        *,
        runtime_patch: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        pid = str(project_id or "").strip()
        out = dict(payload or {})
        cfg = load_project_session_health_config(pid)
        runtime = self._current_runtime(pid, cfg, out)
        if isinstance(runtime_patch, dict) and runtime_patch:
            runtime = {**runtime, **runtime_patch}
            self._set_state(pid, **runtime)
        runtime["project_name"] = cfg.get("project_name") or str(out.get("project_name") or pid)
        runtime["latest_generated_at"] = str(out.get("generated_at") or runtime.get("last_completed_at") or "").strip()
        out["project_id"] = str(out.get("project_id") or pid)
        out["project_name"] = str(out.get("project_name") or cfg.get("project_name") or pid)
        out["session_health"] = {
            "project_id": pid,
            "project_name": runtime["project_name"],
            "enabled": bool(cfg.get("enabled")),
            "interval_minutes": int(cfg.get("interval_minutes") or 0),
            "configured": bool(cfg.get("configured")),
            "state": str(runtime.get("state") or "idle"),
            "running": bool(runtime.get("running")),
            "last_started_at": str(runtime.get("last_started_at") or ""),
            "last_completed_at": str(runtime.get("last_completed_at") or ""),
            "latest_generated_at": str(runtime.get("latest_generated_at") or ""),
            "last_refresh_reason": str(runtime.get("last_refresh_reason") or ""),
            "last_duration_ms": int(runtime.get("last_duration_ms") or 0),
            "last_error": str(runtime.get("last_error") or ""),
            "next_due_at": str(runtime.get("next_due_at") or ""),
        }
        out["global_automation"] = self.automation_summary()
        return out
