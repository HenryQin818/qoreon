# -*- coding: utf-8 -*-

"""
Common utility functions shared across the task-dashboard codebase.

Extracted from server.py to reduce its size and allow direct imports
from runtime modules and other packages.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import time
import tomllib
from pathlib import Path
from typing import Any


UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
OPENCODE_SESSION_RE = re.compile(r"^ses_[A-Za-z0-9]{8,128}$")


def safe_text(s: Any, max_len: int) -> str:
    s2 = "" if s is None else str(s)
    if len(s2) > max_len:
        return s2[: max_len - 1] + "\u2026"
    return s2


def now_iso() -> str:
    # local time
    return time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime())


def channel_id(project_id: str, channel_name: str) -> str:
    # Keep it stable for filtering; filenames use run_id.
    return f"{project_id}::{channel_name}"


def tail_text(path: Path, max_chars: int = 12_000) -> str:
    if not path.exists():
        return ""
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""
    if len(raw) <= max_chars:
        return raw
    return "\u2026\n" + raw[-max_chars:]


def tail_str(text: Any, max_chars: int = 4000) -> str:
    raw = str(text or "")
    if len(raw) <= max_chars:
        return raw
    return "\u2026\n" + raw[-max_chars:]


def extract_last_json_object_text(text: Any) -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""
    positions = [i for i, ch in enumerate(raw) if ch == "{"]
    # Try from the end first (script may print [INFO] logs before final JSON)
    for pos in reversed(positions[-400:]):
        candidate = raw[pos:].strip()
        try:
            obj = json.loads(candidate)
        except Exception:
            continue
        if isinstance(obj, dict):
            return candidate
    return ""


def read_json_file_safe(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def parse_iso_ts(s: Any) -> float:
    txt = str(s or "").strip()
    if not txt:
        return 0.0
    try:
        return time.mktime(time.strptime(txt, "%Y-%m-%dT%H:%M:%S%z"))
    except Exception:
        return 0.0


def parse_rfc3339_ts(s: Any) -> float:
    """
    Parse RFC3339-like timestamps.
    Accepts local format used in this project (`+0800`) and common `+08:00`/`Z`.
    """
    txt = str(s or "").strip()
    if not txt:
        return 0.0
    norm = txt
    if norm.endswith("Z"):
        norm = norm[:-1] + "+0000"
    # Convert timezone offset from +08:00 to +0800 when needed.
    if len(norm) >= 6 and (norm[-6] in {"+", "-"}) and norm[-3] == ":":
        norm = norm[:-3] + norm[-2:]
    return parse_iso_ts(norm)


def iso_after_s(delay_s: float) -> str:
    ts = max(0.0, float(delay_s or 0.0))
    return time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(time.time() + ts))


def looks_like_session_id(s: str) -> bool:
    text = str(s or "").strip()
    if not text:
        return False
    return bool(UUID_RE.match(text) or OPENCODE_SESSION_RE.match(text))


def looks_like_uuid(s: str) -> bool:
    # Backward-compatible name: session IDs are no longer UUID-only after OpenCode
    # adopted native `ses_...` identifiers.
    return looks_like_session_id(s)


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp-{secrets.token_hex(6)}")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)


def read_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return raw if isinstance(raw, dict) else {}


def write_json_file(path: Path, payload: dict[str, Any]) -> None:
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2))


def coerce_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    txt = str(value).strip().lower()
    if txt in {"1", "true", "yes", "on"}:
        return True
    if txt in {"0", "false", "no", "off"}:
        return False
    return default


def coerce_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _repo_root() -> Path:
    """
    Resolve the repository root path.

    Uses the TASK_DASHBOARD_REPO_ROOT environment variable if set and valid.
    Otherwise, choose between the current repo root and the legacy workspace root
    by checking which one actually matches config.toml's relative project paths.

    Prefers Desktop/xiaomishu as canonical root when it resolves to the same
    physical directory, to keep path presentation stable across symlinked workspaces.
    """

    def _prefer_desktop_alias(p: Path) -> Path:
        # Prefer Desktop/xiaomishu as canonical root text when it points to the same
        # physical directory as the computed root.
        try:
            desk = Path.home() / "Desktop" / "xiaomishu"
            if desk.exists() and desk.is_dir():
                if desk.resolve() == p.resolve():
                    return desk
        except Exception:
            pass
        return p

    def _project_relative_hints(project: Any) -> list[str]:
        if not isinstance(project, dict):
            return []
        hints: list[str] = []
        for key in ("project_root_rel", "task_root_rel", "runtime_root_rel", "session_json_rel", "session_list_rel"):
            text = str(project.get(key) or "").strip()
            if text:
                hints.append(text)
        return hints

    def _config_relative_hints(config_path: Path) -> list[str]:
        try:
            payload = tomllib.loads(config_path.read_text(encoding="utf-8"))
        except Exception:
            return []
        projects = payload.get("projects") if isinstance(payload, dict) else None
        if not isinstance(projects, list):
            return []
        hints: list[str] = []
        for project in projects:
            hints.extend(_project_relative_hints(project))
        return hints

    def _first_project_hints(config_path: Path) -> list[str]:
        try:
            payload = tomllib.loads(config_path.read_text(encoding="utf-8"))
        except Exception:
            return []
        projects = payload.get("projects") if isinstance(payload, dict) else None
        if not isinstance(projects, list):
            return []
        for project in projects:
            hints = _project_relative_hints(project)
            if hints:
                return hints
        return []

    def _candidate_score(root: Path, hints: list[str]) -> int:
        score = 0
        for rel in hints:
            try:
                target = (root / rel).resolve()
            except Exception:
                target = root / rel
            if target.exists():
                score += 1
        return score

    repo_root = Path(__file__).absolute().parents[1]
    workspace_root = repo_root.parents[2] if len(repo_root.parents) >= 3 else repo_root
    config_path = repo_root / "config.toml"
    first_hints = _first_project_hints(config_path)

    # Allow explicit root override to keep path presentation stable across symlinked
    # workspaces (e.g. Desktop alias vs workspace physical path). When the current repo
    # already contains a self-contained public config layout, ignore unrelated env roots.
    raw = str(os.environ.get("TASK_DASHBOARD_REPO_ROOT") or "").strip()
    if raw:
        p = Path(raw).expanduser()
        if not p.is_absolute():
            p = (Path(__file__).absolute().parent / p)
        if p.exists() and p.is_dir():
            if first_hints and _candidate_score(repo_root, first_hints) > 0 and _candidate_score(p, first_hints) == 0:
                return _prefer_desktop_alias(repo_root)
            return _prefer_desktop_alias(p)

    if first_hints:
        if _candidate_score(repo_root, first_hints) > 0:
            return _prefer_desktop_alias(repo_root)
        if _candidate_score(workspace_root, first_hints) > 0:
            return _prefer_desktop_alias(workspace_root)

    hints = _config_relative_hints(config_path)
    if hints:
        repo_score = _candidate_score(repo_root, hints)
        workspace_score = _candidate_score(workspace_root, hints)
        if repo_score > workspace_score:
            return _prefer_desktop_alias(repo_root)
        if workspace_score > 0:
            return _prefer_desktop_alias(workspace_root)

    return _prefer_desktop_alias(repo_root)


def _find_project_cfg(project_id: str) -> dict[str, Any]:
    """Find project configuration by project ID from the loaded dashboard config."""
    # Deferred import to avoid circular dependency with server.py
    from server import _load_dashboard_cfg_current

    pid = str(project_id or "").strip()
    if not pid:
        return {}
    cfg = _load_dashboard_cfg_current()
    projects = cfg.get("projects")
    if not isinstance(projects, list):
        return {}
    for p in projects:
        if not isinstance(p, dict):
            continue
        if str(p.get("id") or "").strip() == pid:
            return p
    return {}


__all__ = [
    "safe_text",
    "now_iso",
    "channel_id",
    "tail_text",
    "tail_str",
    "extract_last_json_object_text",
    "read_json_file_safe",
    "read_json_file",
    "write_json_file",
    "parse_iso_ts",
    "parse_rfc3339_ts",
    "iso_after_s",
    "looks_like_session_id",
    "looks_like_uuid",
    "atomic_write_text",
    "coerce_bool",
    "coerce_int",
    "_repo_root",
    "_find_project_cfg",
]
