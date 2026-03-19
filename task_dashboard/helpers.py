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
from pathlib import Path
from typing import Any


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


def looks_like_uuid(s: str) -> bool:
    return bool(
        re.match(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", s.strip())
    )


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

    Uses TASK_DASHBOARD_REPO_ROOT when present, otherwise discovers the nearest
    repository/package root by walking upward from this module.
    """

    # Allow explicit root override to keep path presentation stable across symlinked
    # workspaces (e.g. Desktop alias vs workspace physical path).
    raw = str(os.environ.get("TASK_DASHBOARD_REPO_ROOT") or "").strip()
    if raw:
        p = Path(raw).expanduser()
        if not p.is_absolute():
            p = (Path(__file__).absolute().parent / p)
        if p.exists() and p.is_dir():
            return p
    here = Path(__file__).absolute()
    for parent in [here.parent] + list(here.parents):
        if (parent / ".git").exists():
            return parent
    for parent in [here.parent] + list(here.parents):
        if (parent / "task_dashboard").exists() and (parent / "web").exists():
            return parent
    return here.parents[1]


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
    "looks_like_uuid",
    "atomic_write_text",
    "coerce_bool",
    "coerce_int",
    "_repo_root",
    "_find_project_cfg",
]
