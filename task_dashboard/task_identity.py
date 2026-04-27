from __future__ import annotations

import json
import re
import secrets
import time
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from .helpers import atomic_write_text, now_iso, read_json_file
from .utils import safe_read_text


_FRONT_MATTER_BOUNDARY = "---"
_DEFAULT_TASK_ROOT_REL = "任务规划"
_STATE_VERSION = 1
_TASK_ID_PREFIX = "task_"
_FRONT_MATTER_PRIMARY_KEYS = ("task_id", "parent_task_id", "created_at")
_TASK_STATUS_PREFIX_RE = re.compile(r"^(?:【[^】]+】)+")


def generate_task_id(prefix: str = _TASK_ID_PREFIX) -> str:
    base = str(prefix or _TASK_ID_PREFIX).strip() or _TASK_ID_PREFIX
    if not base.endswith("_"):
        base += "_"
    return f"{base}{time.strftime('%Y%m%d', time.localtime())}_{secrets.token_hex(4)}"


def normalize_task_id(value: Any) -> str:
    text = str(value or "").strip()
    if text in {"", "-", "—", '""', "''", "未关联任务"}:
        return ""
    if text.lower() in {"none", "null", "undefined"}:
        return ""
    return text


def normalize_task_path(value: Any, *, repo_root: Path | None = None) -> str:
    text = str(value or "").strip()
    if not text or text == "未关联任务":
        return ""
    text = unquote(text).replace("\\", "/").strip()
    if text.startswith("task:"):
        text = text[5:].strip()
    if repo_root is not None:
        root = Path(repo_root).expanduser().resolve()
        root_text = str(root).replace("\\", "/").strip("/")
        text_without_leading_slash = text.strip("/")
        if root_text and text_without_leading_slash.startswith(root_text + "/"):
            text = text_without_leading_slash[len(root_text) + 1 :]
        try:
            path = Path(text)
            if path.is_absolute():
                text = str(path.resolve().relative_to(root))
        except Exception:
            pass
    while text.startswith("./"):
        text = text[2:]
    return text.lstrip("/")


def split_markdown_front_matter(markdown: str) -> tuple[dict[str, str], str]:
    text = str(markdown or "")
    if not text.startswith(f"{_FRONT_MATTER_BOUNDARY}\n") and text.strip() != _FRONT_MATTER_BOUNDARY:
        return {}, text
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != _FRONT_MATTER_BOUNDARY:
        return {}, text
    end_index = -1
    for idx in range(1, len(lines)):
        if lines[idx].strip() == _FRONT_MATTER_BOUNDARY:
            end_index = idx
            break
    if end_index < 0:
        return {}, text
    payload: dict[str, str] = {}
    for raw in lines[1:end_index]:
        line = raw.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key_text = str(key or "").strip()
        if not key_text:
            continue
        payload[key_text] = str(value or "").strip()
    body = "".join(lines[end_index + 1 :])
    return payload, body


def strip_markdown_front_matter(markdown: str) -> str:
    _, body = split_markdown_front_matter(markdown)
    return body


def extract_task_identity_from_markdown(markdown: str) -> dict[str, str]:
    front_matter, _ = split_markdown_front_matter(markdown)
    return {
        "task_id": normalize_task_id(front_matter.get("task_id")),
        "parent_task_id": normalize_task_id(front_matter.get("parent_task_id")),
        "created_at": str(front_matter.get("created_at") or "").strip(),
    }


def extract_task_identity_from_file(path: Path) -> dict[str, str]:
    file_path = Path(path)
    if not file_path.is_file():
        return {"task_id": "", "parent_task_id": "", "created_at": ""}
    return extract_task_identity_from_markdown(safe_read_text(file_path))


def render_task_front_matter(
    *,
    task_id: str,
    parent_task_id: str = "",
    created_at: str = "",
    extra_fields: dict[str, Any] | None = None,
) -> str:
    payload: dict[str, str] = {
        "task_id": normalize_task_id(task_id),
        "parent_task_id": normalize_task_id(parent_task_id),
        "created_at": str(created_at or now_iso()).strip(),
    }
    extra = extra_fields if isinstance(extra_fields, dict) else {}
    for key, value in extra.items():
        key_text = str(key or "").strip()
        if not key_text:
            continue
        payload[key_text] = str(value or "").strip()
    ordered_keys = list(_FRONT_MATTER_PRIMARY_KEYS)
    for key in payload.keys():
        if key not in ordered_keys:
            ordered_keys.append(key)
    lines = [_FRONT_MATTER_BOUNDARY]
    for key in ordered_keys:
        lines.append(f"{key}: {payload.get(key, '')}")
    lines.append(_FRONT_MATTER_BOUNDARY)
    return "\n".join(lines) + "\n\n"


def ensure_task_front_matter(
    markdown: str,
    *,
    task_id: str,
    parent_task_id: str = "",
    created_at: str = "",
) -> str:
    front_matter, body = split_markdown_front_matter(markdown)
    front_matter = dict(front_matter)
    front_matter["task_id"] = normalize_task_id(task_id)
    front_matter["parent_task_id"] = normalize_task_id(parent_task_id)
    if created_at:
        front_matter["created_at"] = str(created_at).strip()
    elif not str(front_matter.get("created_at") or "").strip():
        front_matter["created_at"] = now_iso()
    prefix = render_task_front_matter(
        task_id=front_matter.get("task_id") or "",
        parent_task_id=front_matter.get("parent_task_id") or "",
        created_at=front_matter.get("created_at") or "",
        extra_fields={
            key: value
            for key, value in front_matter.items()
            if key not in _FRONT_MATTER_PRIMARY_KEYS
        },
    )
    return prefix + body.lstrip("\n")


def ensure_task_created_at(markdown: str, *, created_at: str) -> str:
    created_text = str(created_at or "").strip()
    if not created_text:
        return str(markdown or "")
    front_matter, body = split_markdown_front_matter(markdown)
    next_front_matter = dict(front_matter)
    if str(next_front_matter.get("created_at") or "").strip() == created_text:
        return str(markdown or "")
    next_front_matter["created_at"] = created_text
    ordered_keys: list[str] = []
    for key in ("task_id", "parent_task_id"):
        if str(next_front_matter.get(key) or "").strip():
            ordered_keys.append(key)
    ordered_keys.append("created_at")
    for key in next_front_matter.keys():
        if key not in ordered_keys:
            ordered_keys.append(key)
    lines = [_FRONT_MATTER_BOUNDARY]
    for key in ordered_keys:
        value = str(next_front_matter.get(key) or "").strip()
        if not value:
            continue
        lines.append(f"{key}: {value}")
    lines.append(_FRONT_MATTER_BOUNDARY)
    return "\n".join(lines) + "\n\n" + str(body or "").lstrip("\n")


def runtime_base_dir_for_repo(repo_root: Path) -> Path:
    root = Path(repo_root).expanduser().resolve()
    preferred = root / ".runtime" / "stable"
    runtime_root = root / ".runtime"
    if preferred.exists() or runtime_root.exists():
        return preferred
    return root


def task_identity_state_path(
    *,
    runtime_base_dir: Path,
    project_id: str = "",
) -> Path:
    pid = str(project_id or "").strip() or "__global__"
    return Path(runtime_base_dir) / ".run" / "task_identity" / f"{pid}.json"


def load_task_identity_state(
    *,
    runtime_base_dir: Path,
    project_id: str = "",
) -> dict[str, Any]:
    path = task_identity_state_path(runtime_base_dir=runtime_base_dir, project_id=project_id)
    raw = read_json_file(path)
    state = raw if isinstance(raw, dict) else {}
    task_ids = state.get("task_ids")
    aliases = state.get("path_aliases")
    state["version"] = int(state.get("version") or _STATE_VERSION)
    state["updated_at"] = str(state.get("updated_at") or "").strip()
    state["task_ids"] = task_ids if isinstance(task_ids, dict) else {}
    state["path_aliases"] = aliases if isinstance(aliases, dict) else {}
    return state


def save_task_identity_state(
    *,
    runtime_base_dir: Path,
    project_id: str,
    state: dict[str, Any],
) -> None:
    path = task_identity_state_path(runtime_base_dir=runtime_base_dir, project_id=project_id)
    payload = dict(state if isinstance(state, dict) else {})
    payload["version"] = _STATE_VERSION
    payload["updated_at"] = now_iso()
    payload["task_ids"] = dict(payload.get("task_ids") or {})
    payload["path_aliases"] = dict(payload.get("path_aliases") or {})
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2))


def _resolve_task_file(repo_root: Path, task_path: str) -> Path | None:
    normalized = normalize_task_path(task_path, repo_root=repo_root)
    if not normalized:
        return None
    root = Path(repo_root).expanduser().resolve()
    try:
        target = (root / normalized).resolve()
        target.relative_to(root)
    except Exception:
        return None
    if not target.is_file():
        return None
    return target


def _task_root(repo_root: Path) -> Path:
    return Path(repo_root).expanduser().resolve() / _DEFAULT_TASK_ROOT_REL


def _scan_task_path_by_id(repo_root: Path, task_id: str) -> str:
    normalized_id = normalize_task_id(task_id)
    if not normalized_id:
        return ""
    task_root = _task_root(repo_root)
    if not task_root.is_dir():
        return ""
    for path in task_root.rglob("*.md"):
        try:
            if not path.is_file():
                continue
        except Exception:
            continue
        identity = extract_task_identity_from_file(path)
        if identity.get("task_id") == normalized_id:
            return normalize_task_path(str(path), repo_root=repo_root)
    return ""


def _task_title_signature(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    name = Path(raw.replace("\\", "/")).name.strip()
    if name.endswith(".md"):
        name = name[:-3]
    return _TASK_STATUS_PREFIX_RE.sub("", name).strip()


def _scan_task_path_by_title(repo_root: Path, task_path: str) -> str:
    normalized_path = normalize_task_path(task_path, repo_root=repo_root)
    signature = _task_title_signature(normalized_path or task_path)
    if not signature:
        return ""
    task_root = _task_root(repo_root)
    if not task_root.is_dir():
        return ""

    scope_parts = normalized_path.split("/")[:2] if normalized_path else []
    scoped_matches: list[str] = []
    matches: list[str] = []
    for path in task_root.rglob("*.md"):
        try:
            if not path.is_file():
                continue
        except Exception:
            continue
        if _task_title_signature(path.name) != signature:
            continue
        rel_path = normalize_task_path(str(path), repo_root=repo_root)
        if not rel_path:
            continue
        matches.append(rel_path)
        if scope_parts and rel_path.split("/")[: len(scope_parts)] == scope_parts:
            scoped_matches.append(rel_path)

    if len(scoped_matches) == 1:
        return scoped_matches[0]
    if len(matches) == 1:
        return matches[0]
    return ""


def _follow_path_aliases(path_aliases: dict[str, Any], task_path: str) -> str:
    current = normalize_task_path(task_path)
    if not current:
        return ""
    seen: set[str] = set()
    while current and current not in seen:
        seen.add(current)
        row = path_aliases.get(current)
        if not isinstance(row, dict):
            break
        nxt = normalize_task_path(row.get("current_path"))
        if not nxt or nxt == current:
            break
        current = nxt
    return current


def _ensure_task_identity_for_file(
    *,
    repo_root: Path,
    runtime_base_dir: Path,
    project_id: str,
    file_path: Path,
) -> dict[str, str]:
    target = Path(file_path).expanduser().resolve()
    identity = extract_task_identity_from_file(target)
    task_id = normalize_task_id(identity.get("task_id"))
    parent_task_id = normalize_task_id(identity.get("parent_task_id"))
    created_at = str(identity.get("created_at") or "").strip()

    if not task_id:
        markdown = safe_read_text(target)
        task_id = generate_task_id()
        updated = ensure_task_front_matter(
            markdown,
            task_id=task_id,
            parent_task_id=parent_task_id,
            created_at=created_at,
        )
        if updated != markdown:
            atomic_write_text(target, updated)
        identity = extract_task_identity_from_markdown(updated)
        task_id = normalize_task_id(identity.get("task_id"))
        parent_task_id = normalize_task_id(identity.get("parent_task_id"))

    resolved_task_path = normalize_task_path(str(target), repo_root=repo_root)
    if resolved_task_path or task_id:
        record_task_identity(
            repo_root=repo_root,
            runtime_base_dir=runtime_base_dir,
            project_id=project_id,
            task_path=resolved_task_path,
            task_id=task_id,
            parent_task_id=parent_task_id,
        )
    return {
        "task_path": resolved_task_path,
        "task_id": task_id,
        "parent_task_id": parent_task_id,
        "created_at": created_at,
    }


def build_task_identity_key(
    *,
    repo_root: Path,
    runtime_base_dir: Path | None = None,
    project_id: str = "",
    task_path: str = "",
    task_id: str = "",
) -> str:
    resolved = resolve_task_reference(
        repo_root=repo_root,
        runtime_base_dir=runtime_base_dir,
        project_id=project_id,
        task_path=task_path,
        task_id=task_id,
    )
    resolved_task_id = normalize_task_id(resolved.get("task_id"))
    if resolved_task_id:
        return f"task_id::{resolved_task_id}"
    resolved_path = normalize_task_path(resolved.get("task_path"), repo_root=repo_root)
    if resolved_path:
        return resolved_path
    return normalize_task_path(task_path, repo_root=repo_root)


def record_task_identity(
    *,
    repo_root: Path,
    runtime_base_dir: Path | None = None,
    project_id: str = "",
    task_path: str,
    task_id: str = "",
    parent_task_id: str = "",
) -> dict[str, str]:
    root = Path(repo_root).expanduser().resolve()
    base_dir = Path(runtime_base_dir or runtime_base_dir_for_repo(root)).expanduser().resolve()
    normalized_path = normalize_task_path(task_path, repo_root=root)
    normalized_task_id = normalize_task_id(task_id)
    normalized_parent_task_id = normalize_task_id(parent_task_id)
    if not normalized_path and not normalized_task_id:
        return {"task_path": "", "task_id": "", "parent_task_id": ""}
    state = load_task_identity_state(runtime_base_dir=base_dir, project_id=project_id)
    if normalized_task_id:
        task_ids = state.setdefault("task_ids", {})
        row = task_ids.get(normalized_task_id) if isinstance(task_ids, dict) else None
        row = dict(row) if isinstance(row, dict) else {}
        if normalized_path:
            row["current_path"] = normalized_path
        if normalized_parent_task_id:
            row["parent_task_id"] = normalized_parent_task_id
        row["updated_at"] = now_iso()
        task_ids[normalized_task_id] = row
    if normalized_path:
        aliases = state.setdefault("path_aliases", {})
        existing = aliases.get(normalized_path) if isinstance(aliases, dict) else None
        existing = dict(existing) if isinstance(existing, dict) else {}
        existing["current_path"] = normalized_path
        if normalized_task_id:
            existing["task_id"] = normalized_task_id
        existing["updated_at"] = now_iso()
        aliases[normalized_path] = existing
    save_task_identity_state(runtime_base_dir=base_dir, project_id=project_id, state=state)
    return {
        "task_path": normalized_path,
        "task_id": normalized_task_id,
        "parent_task_id": normalized_parent_task_id,
    }


def record_task_move(
    *,
    repo_root: Path,
    runtime_base_dir: Path | None = None,
    project_id: str = "",
    old_path: str,
    new_path: str,
    task_id: str = "",
    parent_task_id: str = "",
) -> dict[str, str]:
    root = Path(repo_root).expanduser().resolve()
    base_dir = Path(runtime_base_dir or runtime_base_dir_for_repo(root)).expanduser().resolve()
    old_norm = normalize_task_path(old_path, repo_root=root)
    new_norm = normalize_task_path(new_path, repo_root=root)
    normalized_task_id = normalize_task_id(task_id)
    normalized_parent_task_id = normalize_task_id(parent_task_id)
    if not old_norm and not new_norm and not normalized_task_id:
        return {"old_path": "", "new_path": "", "task_id": "", "parent_task_id": ""}
    state = load_task_identity_state(runtime_base_dir=base_dir, project_id=project_id)
    aliases = state.setdefault("path_aliases", {})
    if isinstance(aliases, dict):
        for key in filter(None, {old_norm, new_norm}):
            row = aliases.get(key) if isinstance(aliases.get(key), dict) else {}
            row = dict(row)
            row["current_path"] = new_norm or old_norm
            if normalized_task_id:
                row["task_id"] = normalized_task_id
            row["updated_at"] = now_iso()
            aliases[key] = row
        if old_norm and new_norm:
            row = dict(aliases.get(old_norm) or {})
            row["current_path"] = new_norm
            if normalized_task_id:
                row["task_id"] = normalized_task_id
            row["updated_at"] = now_iso()
            aliases[old_norm] = row
    if normalized_task_id:
        task_ids = state.setdefault("task_ids", {})
        if isinstance(task_ids, dict):
            row = task_ids.get(normalized_task_id) if isinstance(task_ids.get(normalized_task_id), dict) else {}
            row = dict(row)
            row["current_path"] = new_norm or old_norm
            if normalized_parent_task_id:
                row["parent_task_id"] = normalized_parent_task_id
            row["updated_at"] = now_iso()
            task_ids[normalized_task_id] = row
    save_task_identity_state(runtime_base_dir=base_dir, project_id=project_id, state=state)
    return {
        "old_path": old_norm,
        "new_path": new_norm,
        "task_id": normalized_task_id,
        "parent_task_id": normalized_parent_task_id,
    }


def resolve_task_reference(
    *,
    repo_root: Path,
    runtime_base_dir: Path | None = None,
    project_id: str = "",
    task_path: str = "",
    task_id: str = "",
) -> dict[str, str]:
    root = Path(repo_root).expanduser().resolve()
    base_dir = Path(runtime_base_dir or runtime_base_dir_for_repo(root)).expanduser().resolve()
    normalized_path = normalize_task_path(task_path, repo_root=root)
    normalized_task_id = normalize_task_id(task_id)
    state = load_task_identity_state(runtime_base_dir=base_dir, project_id=project_id)
    task_ids = state.get("task_ids") if isinstance(state.get("task_ids"), dict) else {}
    path_aliases = state.get("path_aliases") if isinstance(state.get("path_aliases"), dict) else {}

    def _finalize(found_path: str, *, matched_by: str) -> dict[str, str]:
        found_norm = normalize_task_path(found_path, repo_root=root)
        resolved_file = _resolve_task_file(root, found_norm)
        identity = (
            _ensure_task_identity_for_file(
                repo_root=root,
                runtime_base_dir=base_dir,
                project_id=project_id,
                file_path=resolved_file,
            )
            if resolved_file is not None
            else {}
        )
        resolved_task_id = normalize_task_id(identity.get("task_id") or normalized_task_id)
        resolved_parent_task_id = normalize_task_id(identity.get("parent_task_id"))
        resolved_created_at = str(identity.get("created_at") or "").strip()
        if resolved_task_id or found_norm:
            if normalized_path and found_norm and normalized_path != found_norm:
                record_task_move(
                    repo_root=root,
                    runtime_base_dir=base_dir,
                    project_id=project_id,
                    old_path=normalized_path,
                    new_path=found_norm,
                    task_id=resolved_task_id,
                    parent_task_id=resolved_parent_task_id,
                )
            else:
                record_task_identity(
                    repo_root=root,
                    runtime_base_dir=base_dir,
                    project_id=project_id,
                    task_path=found_norm,
                    task_id=resolved_task_id,
                    parent_task_id=resolved_parent_task_id,
                )
        return {
            "task_path": found_norm or normalized_path,
            "task_id": resolved_task_id,
            "parent_task_id": resolved_parent_task_id,
            "created_at": resolved_created_at,
            "matched_by": matched_by,
        }

    if normalized_path and _resolve_task_file(root, normalized_path) is not None:
        return _finalize(normalized_path, matched_by="task_path")

    if normalized_task_id:
        row = task_ids.get(normalized_task_id) if isinstance(task_ids, dict) else None
        candidate = normalize_task_path((row or {}).get("current_path"), repo_root=root) if isinstance(row, dict) else ""
        if candidate and _resolve_task_file(root, candidate) is not None:
            return _finalize(candidate, matched_by="task_id_state")

    if normalized_path:
        candidate = _follow_path_aliases(path_aliases if isinstance(path_aliases, dict) else {}, normalized_path)
        if candidate and _resolve_task_file(root, candidate) is not None:
            return _finalize(candidate, matched_by="path_alias")

    if normalized_task_id:
        scanned = _scan_task_path_by_id(root, normalized_task_id)
        if scanned:
            return _finalize(scanned, matched_by="task_id_scan")

    if normalized_path:
        scanned = _scan_task_path_by_title(root, normalized_path)
        if scanned:
            return _finalize(scanned, matched_by="task_title_scan")

    if normalized_path:
        return {
            "task_path": normalized_path,
            "task_id": normalized_task_id,
            "parent_task_id": "",
            "created_at": "",
            "matched_by": "unresolved_path",
        }
    return {
        "task_path": "",
        "task_id": normalized_task_id,
        "parent_task_id": "",
        "created_at": "",
        "matched_by": "missing",
    }
