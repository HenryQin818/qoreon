from __future__ import annotations

import os
from pathlib import Path
from typing import Any

try:
    import tomllib  # py311+
except Exception:  # pragma: no cover
    tomllib = None  # type: ignore[assignment]


def resolve_dashboard_config_path(script_dir: Path) -> Path:
    explicit = str(os.environ.get("TASK_DASHBOARD_CONFIG") or "").strip()
    if explicit:
        return Path(explicit).expanduser()
    env_name = str(os.environ.get("TASK_DASHBOARD_ENV_NAME") or "").strip().lower()
    if env_name and env_name != "stable":
        candidate = script_dir / f"config.{env_name}.toml"
        if candidate.exists():
            return candidate
    return script_dir / "config.toml"


def resolve_dashboard_local_config_path(script_dir: Path) -> Path:
    explicit = str(os.environ.get("TASK_DASHBOARD_CONFIG_LOCAL") or "").strip()
    if explicit:
        return Path(explicit).expanduser()
    base = resolve_dashboard_config_path(script_dir)
    if base.name != "config.toml":
        env_local = base.with_name(f"{base.stem}.local{base.suffix}")
        if env_local.exists():
            return env_local
    return script_dir / "config.local.toml"


def load_dashboard_config(script_dir: Path, *, with_local: bool = False) -> dict[str, Any]:
    """
    Load config from config.toml (required for shared config).

    Local-only overrides can be stored in config.local.toml, but are only loaded when
    `with_local=True` (explicit opt-in) to avoid accidentally mixing work materials into
    git-synced outputs.
    """
    if tomllib is None:
        raise RuntimeError("tomllib not available (need Python 3.11+)")

    def _load_toml(path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        raw = path.read_bytes()
        obj = tomllib.loads(raw.decode("utf-8"))
        return obj if isinstance(obj, dict) else {}

    def _pid(p: Any) -> str:
        if not isinstance(p, dict):
            return ""
        return str(p.get("id") or "").strip()

    def _merge_projects(base_list: list[Any], override_list: list[Any]) -> list[Any]:
        # Merge by project id:
        # - same id: deep-merge project object so base-only keys (e.g. scheduler/reminder)
        #   are kept unless explicitly overridden in local config.
        # - new id: append.
        base_by_id: dict[str, Any] = {}
        out: list[Any] = []
        for p in base_list:
            pid = _pid(p)
            if pid:
                base_by_id[pid] = p

        override_by_id: dict[str, Any] = {}
        override_new: list[Any] = []
        for p in override_list:
            pid = _pid(p)
            if pid:
                override_by_id[pid] = p
            else:
                override_new.append(p)

        for p in base_list:
            pid = _pid(p)
            if pid and pid in override_by_id:
                ov = override_by_id[pid]
                if isinstance(p, dict) and isinstance(ov, dict):
                    out.append(_merge_dict(p, ov))
                else:
                    out.append(ov)
            else:
                out.append(p)

        for pid, p in override_by_id.items():
            if pid not in base_by_id:
                out.append(p)
        out.extend(override_new)
        return out

    def _merge_dict(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
        if not override:
            return dict(base)
        out: dict[str, Any] = dict(base)
        for k, v in override.items():
            if k == "projects" and isinstance(out.get("projects"), list) and isinstance(v, list):
                out["projects"] = _merge_projects(out.get("projects") or [], v)
                continue
            bv = out.get(k)
            if isinstance(bv, dict) and isinstance(v, dict):
                out[k] = _merge_dict(bv, v)
            else:
                out[k] = v
        return out

    base = _load_toml(resolve_dashboard_config_path(script_dir))
    if not base:
        base = {}

    if not with_local:
        return base

    local = _load_toml(resolve_dashboard_local_config_path(script_dir))
    if not local:
        return base
    return _merge_dict(base, local)
