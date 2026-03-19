# -*- coding: utf-8 -*-

from __future__ import annotations

from pathlib import Path
from typing import Any

from task_dashboard.config import load_dashboard_config

DEFAULT_EXECUTION_PROFILE = "sandboxed"
_BUILTIN_PROFILE_ORDER = ("sandboxed", "privileged", "project_privileged_full")


def _dashboard_repo_root(dashboard_repo_root: Path | str | None = None) -> Path:
    if dashboard_repo_root is None:
        return Path(__file__).resolve().parents[2]
    path = Path(dashboard_repo_root).expanduser()
    try:
        return path.resolve()
    except Exception:
        return path


def _workspace_root(dashboard_repo_root: Path) -> Path:
    parents = dashboard_repo_root.parents
    if len(parents) >= 3:
        return parents[2]
    if parents:
        return parents[-1]
    return dashboard_repo_root


def _coerce_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _normalize_root_value(value: Any, *, dashboard_repo_root: Path) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    path = Path(text).expanduser()
    if not path.is_absolute():
        path = dashboard_repo_root / path
    try:
        return str(path.resolve())
    except Exception:
        return str(path)


def _normalize_root_list(value: Any, *, dashboard_repo_root: Path) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        normalized = _normalize_root_value(item, dashboard_repo_root=dashboard_repo_root)
        if normalized and normalized not in out:
            out.append(normalized)
    return out


def _normalize_command_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text and text not in out:
            out.append(text)
    return out


def _option_label_for_profile(profile: str) -> str:
    mapping = {
        "sandboxed": "sandboxed · 受限执行（默认更安全）",
        "privileged": "privileged · 真实仓执行（可发布/重启）",
        "project_privileged_full": "project_privileged_full · 完全放开（当前用户态）",
    }
    return mapping.get(str(profile or "").strip().lower(), str(profile or "").strip())


def _builtin_execution_profiles(
    *,
    dashboard_repo_root: Path | str | None = None,
    home_dir: Path | str | None = None,
) -> dict[str, dict[str, Any]]:
    repo_root = _dashboard_repo_root(dashboard_repo_root)
    workspace_root = _workspace_root(repo_root)
    home_root = Path(home_dir or Path.home()).expanduser()
    refactor_root = repo_root.parent / "task-dashboard-refactor"
    static_sites_root = workspace_root / "static_sites"
    codex_home_root = home_root / ".codex"
    codex_sessions_root = codex_home_root / "sessions"
    return {
        "sandboxed": {
            "profile": "sandboxed",
            "label": "受限执行",
            "description": "只允许临时 runner 和只读排查",
            "option_label": _option_label_for_profile("sandboxed"),
            "writable_roots": [],
            "allow_launchctl": False,
            "allow_service_hub_write": False,
            "allow_localhost_admin": False,
            "allowed_commands": [],
        },
        "privileged": {
            "profile": "privileged",
            "label": "项目执行",
            "description": "允许真实项目仓执行，但不含全局注册目录",
            "option_label": _option_label_for_profile("privileged"),
            "writable_roots": [
                str(repo_root),
                str((repo_root / ".runtime").resolve()),
            ],
            "allow_launchctl": False,
            "allow_service_hub_write": False,
            "allow_localhost_admin": False,
            "allowed_commands": [],
        },
        "project_privileged_full": {
            "profile": "project_privileged_full",
            "label": "完全放开",
            "description": "按当前用户态直接放开，覆盖项目目录、CLI 会话目录与本机管理动作",
            "option_label": _option_label_for_profile("project_privileged_full"),
            "writable_roots": [
                str(home_root),
            ],
            "allow_launchctl": True,
            "allow_service_hub_write": True,
            "allow_localhost_admin": True,
            "allowed_commands": ["launchctl", "lsof", "kill", "curl", "python3", "bash", "sh", "mkdir", "mv", "cp", "rm", "ln"],
        },
    }


def _load_execution_profile_config(
    *,
    dashboard_repo_root: Path | str | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if isinstance(config, dict):
        return config
    repo_root = _dashboard_repo_root(dashboard_repo_root)
    try:
        return load_dashboard_config(repo_root, with_local=False)
    except Exception:
        return {}


def get_execution_profile_catalog(
    *,
    dashboard_repo_root: Path | str | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    repo_root = _dashboard_repo_root(dashboard_repo_root)
    catalog = _builtin_execution_profiles(dashboard_repo_root=repo_root)
    loaded = _load_execution_profile_config(dashboard_repo_root=repo_root, config=config)
    raw_profiles = loaded.get("execution_profiles") if isinstance(loaded, dict) else {}
    if not isinstance(raw_profiles, dict):
        return catalog

    for profile_id, raw in raw_profiles.items():
        key = str(profile_id or "").strip().lower()
        if not key or not isinstance(raw, dict):
            continue
        base = dict(
            catalog.get(key)
            or {
                "profile": key,
                "label": key,
                "description": "",
                "option_label": _option_label_for_profile(key),
                "writable_roots": [],
                "allow_launchctl": False,
                "allow_service_hub_write": False,
                "allow_localhost_admin": False,
                "allowed_commands": [],
            }
        )
        if "label" in raw:
            base["label"] = str(raw.get("label") or "").strip() or base.get("label") or key
        if "description" in raw:
            base["description"] = str(raw.get("description") or "").strip()
        base["option_label"] = str(raw.get("option_label") or "").strip() or _option_label_for_profile(key)
        if "writable_roots" in raw:
            base["writable_roots"] = _normalize_root_list(raw.get("writable_roots"), dashboard_repo_root=repo_root)
        else:
            base["writable_roots"] = _normalize_root_list(base.get("writable_roots"), dashboard_repo_root=repo_root)
        if "allow_launchctl" in raw:
            base["allow_launchctl"] = _coerce_bool(raw.get("allow_launchctl"), False)
        if "allow_service_hub_write" in raw:
            base["allow_service_hub_write"] = _coerce_bool(raw.get("allow_service_hub_write"), False)
        if "allow_localhost_admin" in raw:
            base["allow_localhost_admin"] = _coerce_bool(raw.get("allow_localhost_admin"), False)
        if "allowed_commands" in raw:
            base["allowed_commands"] = _normalize_command_list(raw.get("allowed_commands"))
        else:
            base["allowed_commands"] = _normalize_command_list(base.get("allowed_commands"))
        catalog[key] = base
    return catalog


def list_execution_profiles(
    *,
    dashboard_repo_root: Path | str | None = None,
    config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    catalog = get_execution_profile_catalog(dashboard_repo_root=dashboard_repo_root, config=config)
    ordered: list[str] = [item for item in _BUILTIN_PROFILE_ORDER if item in catalog]
    ordered.extend(key for key in catalog.keys() if key not in ordered)
    return [dict(catalog.get(key) or {}) for key in ordered]


def normalize_execution_profile(
    value: Any,
    *,
    default: str = DEFAULT_EXECUTION_PROFILE,
    allow_empty: bool = False,
    dashboard_repo_root: Path | str | None = None,
    config: dict[str, Any] | None = None,
) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return "" if allow_empty else default
    catalog = get_execution_profile_catalog(dashboard_repo_root=dashboard_repo_root, config=config)
    if text in catalog:
        return text
    return ""


def resolve_execution_profile_permissions(
    profile: Any,
    *,
    dashboard_repo_root: Path | str | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    catalog = get_execution_profile_catalog(dashboard_repo_root=dashboard_repo_root, config=config)
    normalized = normalize_execution_profile(
        profile,
        default=DEFAULT_EXECUTION_PROFILE,
        dashboard_repo_root=dashboard_repo_root,
        config=config,
    )
    resolved = dict(catalog.get(normalized) or catalog.get(DEFAULT_EXECUTION_PROFILE) or {})
    resolved["profile"] = normalized
    resolved["option_label"] = str(resolved.get("option_label") or _option_label_for_profile(normalized))
    resolved["writable_roots"] = _normalize_root_list(
        resolved.get("writable_roots"),
        dashboard_repo_root=_dashboard_repo_root(dashboard_repo_root),
    )
    resolved["allow_launchctl"] = _coerce_bool(resolved.get("allow_launchctl"), False)
    resolved["allow_service_hub_write"] = _coerce_bool(resolved.get("allow_service_hub_write"), False)
    resolved["allow_localhost_admin"] = _coerce_bool(resolved.get("allow_localhost_admin"), False)
    resolved["allowed_commands"] = _normalize_command_list(resolved.get("allowed_commands"))
    return resolved


def uses_direct_worktree_execution(profile: Any) -> bool:
    normalized = normalize_execution_profile(profile, allow_empty=True)
    return bool(normalized) and normalized != DEFAULT_EXECUTION_PROFILE
