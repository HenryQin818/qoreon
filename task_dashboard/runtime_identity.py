from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable


RUNTIME_IDENTITY_COMPARE_KEYS = (
    "project_id",
    "runtime_role",
    "environment",
    "port",
    "bind",
    "localOrigin",
    "publicOrigin",
    "runsDir",
    "staticRoot",
    "worktreeRoot",
    "configPath",
)


def _norm_text(value: Any) -> str:
    return str(value or "").strip()


def _norm_path(value: Any) -> str:
    raw = _norm_text(value)
    if not raw:
        return ""
    try:
        return str(Path(raw).expanduser().resolve())
    except Exception:
        return raw


def build_health_runtime_identity(
    *,
    project_id: str,
    runtime_role: str,
    environment: str,
    port: int,
    bind_host: str = "",
    local_origin: str = "",
    public_origin: str = "",
    runs_dir: Path | str,
    sessions_file: Path | str,
    static_root: Path | str,
    worktree_root: Path | str,
    config_path: Path | str,
) -> dict[str, Any]:
    return {
        "project_id": _norm_text(project_id),
        "runtime_role": _norm_text(runtime_role),
        "environment": _norm_text(environment),
        "port": int(port or 0),
        "bind": _norm_text(bind_host),
        "localOrigin": _norm_text(local_origin),
        "publicOrigin": _norm_text(public_origin),
        "runsDir": _norm_path(runs_dir),
        "sessionsFile": _norm_path(sessions_file),
        "staticRoot": _norm_path(static_root),
        "worktreeRoot": _norm_path(worktree_root),
        "configPath": _norm_path(config_path),
    }


def compare_runtime_identity(
    expected: dict[str, Any],
    actual: dict[str, Any],
    *,
    keys: Iterable[str] | None = None,
) -> list[str]:
    mismatch_keys = tuple(keys or RUNTIME_IDENTITY_COMPARE_KEYS)
    mismatches: list[str] = []
    for key in mismatch_keys:
        if key in {"runsDir", "sessionsFile", "staticRoot", "worktreeRoot", "configPath"}:
            left = _norm_path(expected.get(key))
            right = _norm_path(actual.get(key))
        else:
            left = _norm_text(expected.get(key))
            right = _norm_text(actual.get(key))
        if left != right:
            mismatches.append(f"{key}: expected={left or '-'} actual={right or '-'}")
    return mismatches
