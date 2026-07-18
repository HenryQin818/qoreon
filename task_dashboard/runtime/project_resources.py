# -*- coding: utf-8 -*-
"""Project-scoped user-maintained resources.

The runtime store is intentionally local and additive: it records only the
user's resource list and projects configured local service status at response time.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "project_resources.v1"
ALLOWED_RESOURCE_TYPES = {"doc_page", "service"}
ALLOWED_SOURCES = {"manual", "message_quick_add"}
MAX_ITEMS_PER_PROJECT = 500

_LOCKS_GUARD = threading.Lock()
_LOCKS: dict[str, threading.Lock] = {}


def _safe_text(value: Any, max_len: int = 4000) -> str:
    text = "" if value is None else str(value)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text).strip()
    if len(text) > max_len:
        return text[:max_len]
    return text


def _safe_storage_id(value: Any, *, fallback: str = "unknown_project") -> str:
    text = _safe_text(value, 240)
    text = re.sub(r"[^0-9A-Za-z_.-]+", "_", text)
    text = text.replace("..", "_").strip("._")
    return text or fallback


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _coerce_sort_order(value: Any, default: int = 0) -> int:
    try:
        number = int(value)
    except Exception:
        number = int(default)
    return max(-1_000_000, min(number, 1_000_000))


def _project_lock(path: Path) -> threading.Lock:
    key = str(path)
    with _LOCKS_GUARD:
        lock = _LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _LOCKS[key] = lock
        return lock


def project_resources_store_dir(worktree_root: Any, environment_name: str = "stable") -> Path:
    root = Path(worktree_root).expanduser().resolve()
    env = _safe_storage_id(environment_name or "stable", fallback="stable")
    return root / ".runtime" / env / ".resources"


def project_resources_store_path(worktree_root: Any, environment_name: str, project_id: str) -> Path:
    return project_resources_store_dir(worktree_root, environment_name) / f"{_safe_storage_id(project_id)}.json"


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp-{secrets.token_hex(6)}")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _empty_state(project_id: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "project_id": _safe_text(project_id, 120),
        "updated_at": "",
        "items": [],
    }


def _infer_resource_type(url: str) -> str:
    text = _safe_text(url, 2200).lower()
    if re.match(r"^https?://[^/?#]+:\d+(?:[/?#]|$)", text):
        return "service"
    if text.endswith((".html", ".htm", ".md", ".markdown", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".pdf")):
        return "doc_page"
    return "doc_page"


def _normalize_type(value: Any, *, url: str = "") -> str:
    text = _safe_text(value, 40).lower()
    if not text:
        return _infer_resource_type(url)
    if text not in ALLOWED_RESOURCE_TYPES:
        raise ValueError("invalid resource type")
    return text


def _normalize_source(value: Any) -> str:
    text = _safe_text(value, 80).lower()
    return text if text in ALLOWED_SOURCES else "manual"


def _normalize_item(raw: Any, *, project_id: str) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    resource_id = _safe_storage_id(raw.get("id"), fallback="")
    if not resource_id:
        return None
    title = _safe_text(raw.get("title"), 240)
    url = _safe_text(raw.get("url"), 2200)
    note = _safe_text(raw.get("note"), 2000)
    try:
        resource_type = _normalize_type(raw.get("type"), url=url)
    except ValueError:
        resource_type = "doc_page"
    created_at = _safe_text(raw.get("created_at") or raw.get("createdAt"), 80) or _utc_now_iso()
    updated_at = _safe_text(raw.get("updated_at") or raw.get("updatedAt"), 80) or created_at
    return {
        "id": resource_id,
        "project_id": _safe_text(raw.get("project_id") or raw.get("projectId") or project_id, 120) or project_id,
        "title": title or url or "未命名资源",
        "type": resource_type,
        "url": url,
        "note": note,
        "source": _normalize_source(raw.get("source")),
        "sort_order": _coerce_sort_order(raw.get("sort_order", raw.get("sortOrder", 0)), 0),
        "created_at": created_at,
        "updated_at": updated_at,
    }


def _load_registry(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _service_registry_paths() -> list[Path]:
    paths: list[Path] = []
    for env_key in ("QOREON_RESOURCE_REGISTRY", "TASK_DASHBOARD_RESOURCE_REGISTRY"):
        raw = _safe_text(os.environ.get(env_key), 4000)
        if raw:
            paths.append(Path(raw).expanduser())
    deduped: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(path)
    return deduped


def _url_match_key(url: str) -> tuple[str, str, str]:
    text = _safe_text(url, 2200).strip().rstrip("/")
    lower = text.lower()
    match = re.match(r"^(https?)://([^/?#:]+)(?::(\d+))?", lower)
    if not match:
        return (lower, "", "")
    scheme, host, port = match.groups()
    return (lower, f"{scheme}://{host}:{port or ''}", f"{host}:{port or ''}")


def _pid_alive(pid: Any) -> bool:
    try:
        number = int(pid)
    except Exception:
        return False
    if number <= 0:
        return False
    try:
        os.kill(number, 0)
        return True
    except Exception:
        return False


def _status_from_service(service_id: str, service: dict[str, Any]) -> dict[str, Any]:
    status_text = _safe_text(service.get("status") or service.get("state"), 80).lower()
    up_value = service.get("up")
    running_value = service.get("running")
    state = "unknown"
    if isinstance(up_value, bool):
        state = "up" if up_value else "stopped"
    elif isinstance(running_value, bool):
        state = "up" if running_value else "stopped"
    elif status_text in {"up", "running", "online", "started", "active"}:
        state = "up"
    elif status_text in {"down", "stopped", "offline", "inactive", "not_running"}:
        state = "stopped"
    elif "pid" in service:
        state = "up" if _pid_alive(service.get("pid")) else "stopped"

    return {
        "state": state,
        "label": {"up": "UP", "stopped": "未启"}.get(state, "未知"),
        "source": "configured_registry",
        "service_id": _safe_text(service.get("id") or service_id, 160),
        "service_name": _safe_text(service.get("name") or service_id, 240),
        "matched_url": _safe_text(service.get("url"), 2200),
        "updated_at": _safe_text(service.get("updated_at") or service.get("updatedAt"), 80),
    }


class ProjectResourceStore:
    """Runtime-local project resource list store."""

    def __init__(self, worktree_root: Any, *, environment_name: str = "stable") -> None:
        self.worktree_root = Path(worktree_root).expanduser().resolve()
        self.environment_name = _safe_storage_id(environment_name or "stable", fallback="stable")

    def path_for_project(self, project_id: str) -> Path:
        return project_resources_store_path(self.worktree_root, self.environment_name, project_id)

    def _load_state(self, project_id: str) -> dict[str, Any]:
        path = self.path_for_project(project_id)
        if not path.exists():
            return _empty_state(project_id)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return _empty_state(project_id)
        if not isinstance(data, dict):
            return _empty_state(project_id)
        state = _empty_state(project_id)
        state["updated_at"] = _safe_text(data.get("updated_at") or data.get("updatedAt"), 80)
        items: list[dict[str, Any]] = []
        for row in data.get("items") if isinstance(data.get("items"), list) else []:
            item = _normalize_item(row, project_id=project_id)
            if item:
                item["project_id"] = _safe_text(project_id, 120)
                items.append(item)
        state["items"] = sorted(items[:MAX_ITEMS_PER_PROJECT], key=lambda row: (int(row.get("sort_order") or 0), str(row.get("created_at") or "")))
        return state

    def _save_state(self, project_id: str, state: dict[str, Any]) -> None:
        path = self.path_for_project(project_id)
        payload = {
            "schema_version": SCHEMA_VERSION,
            "project_id": _safe_text(project_id, 120),
            "updated_at": _safe_text(state.get("updated_at"), 80),
            "items": state.get("items") if isinstance(state.get("items"), list) else [],
        }
        _atomic_write_json(path, payload)

    def _service_status_for_url(self, url: str) -> dict[str, Any]:
        wanted = _url_match_key(url)
        if not wanted[0]:
            return {
                "state": "unknown",
                "label": "未知",
                "source": "not_found",
                "service_id": "",
                "service_name": "",
                "matched_url": "",
                "updated_at": "",
            }
        for registry_path in _service_registry_paths():
            if not registry_path.exists():
                continue
            registry = _load_registry(registry_path)
            services = registry.get("services") if isinstance(registry.get("services"), dict) else {}
            for service_id, service in services.items():
                if not isinstance(service, dict):
                    continue
                service_url = _safe_text(service.get("url"), 2200)
                key = _url_match_key(service_url)
                if wanted[0] == key[0] or (wanted[1] and wanted[1] == key[1]) or (wanted[2] and wanted[2] == key[2]):
                    return _status_from_service(str(service_id), service)
        return {
            "state": "unknown",
            "label": "未知",
            "source": "not_found",
            "service_id": "",
            "service_name": "",
            "matched_url": "",
            "updated_at": "",
        }

    def _with_projection(self, item: dict[str, Any]) -> dict[str, Any]:
        out = dict(item)
        if out.get("type") == "service":
            out["service_status"] = self._service_status_for_url(str(out.get("url") or ""))
        return out

    def list(self, project_id: str) -> dict[str, Any]:
        with _project_lock(self.path_for_project(project_id)):
            state = self._load_state(project_id)
        items = [self._with_projection(item) for item in state.get("items") or []]
        service_status = {
            str(item.get("id") or ""): item.get("service_status")
            for item in items
            if item.get("type") == "service" and str(item.get("id") or "")
        }
        return {
            "project_id": _safe_text(project_id, 120),
            "safe_project_id": _safe_storage_id(project_id),
            "schema_version": SCHEMA_VERSION,
            "storage_mode": "runtime_local",
            "storage_path": str(self.path_for_project(project_id)),
            "updated_at": _safe_text(state.get("updated_at"), 80),
            "count": len(items),
            "items": items,
            "service_status": service_status,
        }

    def create(self, project_id: str, raw_item: Any) -> dict[str, Any]:
        if not isinstance(raw_item, dict):
            raise ValueError("invalid resource item")
        title = _safe_text(raw_item.get("title"), 240)
        url = _safe_text(raw_item.get("url"), 2200)
        if not title and not url:
            raise ValueError("missing title or url")
        now = _utc_now_iso()
        with _project_lock(self.path_for_project(project_id)):
            state = self._load_state(project_id)
            existing_items = list(state.get("items") or [])
            existing_ids = {str(item.get("id") or "") for item in existing_items}
            next_order = max([int(item.get("sort_order") or 0) for item in existing_items] or [0]) + 10
            resource_id = _safe_storage_id(raw_item.get("id"), fallback="")
            if not resource_id or resource_id in existing_ids:
                resource_id = "res_" + secrets.token_hex(8)
                while resource_id in existing_ids:
                    resource_id = "res_" + secrets.token_hex(8)
            item = {
                "id": resource_id,
                "project_id": _safe_text(project_id, 120),
                "title": title or url,
                "type": _normalize_type(raw_item.get("type"), url=url),
                "url": url,
                "note": _safe_text(raw_item.get("note"), 2000),
                "source": _normalize_source(raw_item.get("source")),
                "sort_order": _coerce_sort_order(raw_item.get("sort_order", raw_item.get("sortOrder", next_order)), next_order),
                "created_at": now,
                "updated_at": now,
            }
            existing_items.append(item)
            state["items"] = sorted(existing_items[:MAX_ITEMS_PER_PROJECT], key=lambda row: (int(row.get("sort_order") or 0), str(row.get("created_at") or "")))
            state["updated_at"] = now
            self._save_state(project_id, state)
        return self._with_projection(item)

    def update(self, project_id: str, resource_id: str, patch: Any) -> dict[str, Any] | None:
        if not isinstance(patch, dict):
            raise ValueError("invalid resource patch")
        rid = _safe_storage_id(resource_id, fallback="")
        if not rid:
            raise ValueError("missing resource id")
        now = _utc_now_iso()
        with _project_lock(self.path_for_project(project_id)):
            state = self._load_state(project_id)
            updated_item: dict[str, Any] | None = None
            next_items: list[dict[str, Any]] = []
            for item in list(state.get("items") or []):
                row = dict(item)
                if row.get("id") == rid:
                    if "title" in patch:
                        title = _safe_text(patch.get("title"), 240)
                        if not title:
                            raise ValueError("missing title")
                        row["title"] = title
                    if "url" in patch:
                        row["url"] = _safe_text(patch.get("url"), 2200)
                    if "type" in patch:
                        row["type"] = _normalize_type(patch.get("type"), url=str(row.get("url") or ""))
                    if "note" in patch:
                        row["note"] = _safe_text(patch.get("note"), 2000)
                    if "source" in patch:
                        row["source"] = _normalize_source(patch.get("source"))
                    if "sort_order" in patch or "sortOrder" in patch:
                        row["sort_order"] = _coerce_sort_order(patch.get("sort_order", patch.get("sortOrder")), int(row.get("sort_order") or 0))
                    row["project_id"] = _safe_text(project_id, 120)
                    row["updated_at"] = now
                    updated_item = row
                next_items.append(row)
            if updated_item is None:
                return None
            state["items"] = sorted(next_items, key=lambda row: (int(row.get("sort_order") or 0), str(row.get("created_at") or "")))
            state["updated_at"] = now
            self._save_state(project_id, state)
        return self._with_projection(updated_item)

    def delete(self, project_id: str, resource_id: str) -> tuple[bool, int]:
        rid = _safe_storage_id(resource_id, fallback="")
        if not rid:
            return False, self.list(project_id).get("count", 0)
        with _project_lock(self.path_for_project(project_id)):
            state = self._load_state(project_id)
            old_items = list(state.get("items") or [])
            next_items = [item for item in old_items if str(item.get("id") or "") != rid]
            deleted = len(next_items) != len(old_items)
            if deleted:
                state["items"] = next_items
                state["updated_at"] = _utc_now_iso()
                self._save_state(project_id, state)
            return deleted, len(next_items)
