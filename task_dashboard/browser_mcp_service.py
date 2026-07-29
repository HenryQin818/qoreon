#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""CCB browser capability policy and local configuration checks."""

from __future__ import annotations

import hashlib
import os
import shutil
import tomllib
from pathlib import Path
from typing import Any, Mapping


PLAYWRIGHT_MCP_PACKAGE = "@playwright/mcp@0.0.78"
BROWSER_MODES = ("auto", "off", "ephemeral", "collab", "plugin")
DEFAULT_BROWSER_MODE = "collab"
PLAYWRIGHT_ENABLED_ENV = "TASK_DASHBOARD_CODEX_PLAYWRIGHT_MCP"
BROWSER_PLUGIN_ENABLED_ENV = "TASK_DASHBOARD_CODEX_BROWSER_PLUGIN"
PLAYWRIGHT_PROFILE_ROOT_ENV = "TASK_DASHBOARD_CODEX_PLAYWRIGHT_PROFILE_ROOT"


class BrowserConfigurationError(ValueError):
    """Raised when an explicitly requested browser capability is unavailable."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = str(code or "browser_configuration_error")


def _env_bool(env: Mapping[str, str], name: str, default: bool) -> bool:
    raw = str(env.get(name) or "").strip().lower()
    if not raw:
        return default
    if raw in {"1", "true", "yes", "y", "on"}:
        return True
    if raw in {"0", "false", "no", "n", "off"}:
        return False
    return default


def normalize_browser_mode(value: Any, *, default: str = DEFAULT_BROWSER_MODE) -> str:
    text = str(value or "").strip().lower().replace("-", "_")
    aliases = {
        "": default,
        "agent_choice": "auto",
        "automatic": "auto",
        "none": "off",
        "disabled": "off",
        "temporary": "ephemeral",
        "isolated": "ephemeral",
        "background": "ephemeral",
        "persistent": "collab",
        "headed": "collab",
        "visible": "collab",
        "project_profile": "collab",
        "browser_plugin": "plugin",
        "chrome_plugin": "plugin",
        "desktop_plugin": "plugin",
    }
    normalized = aliases.get(text, text)
    if normalized not in BROWSER_MODES:
        raise BrowserConfigurationError(
            "invalid_browser_mode",
            "browser_mode 仅允许 auto、off、ephemeral、collab 或 plugin",
        )
    return normalized


def effective_browser_mode(value: Any, *, default: str = DEFAULT_BROWSER_MODE) -> str:
    """Map the retired dual-backend auto mode to one safe Playwright backend."""

    mode = normalize_browser_mode(value, default=default)
    return "collab" if mode == "auto" else mode


def resolve_playwright_profile_dir(
    project_id: Any,
    env: Mapping[str, str] | None = None,
) -> Path:
    """Return an opaque, project-scoped persistent profile directory.

    The caller never supplies a directory fragment. This prevents project ids
    from becoming paths and keeps the real profile location out of run meta.
    """

    source = env if env is not None else os.environ
    normalized_project = str(project_id or "").strip().lower()
    if not normalized_project:
        raise BrowserConfigurationError(
            "browser_project_required",
            "可见协作浏览器需要明确的 project_id 才能隔离登录状态",
        )
    configured_root = str(source.get(PLAYWRIGHT_PROFILE_ROOT_ENV) or "").strip()
    root = (
        Path(configured_root).expanduser()
        if configured_root
        else Path.home() / "Library" / "Application Support" / "Qoreon" / "browser-profiles"
    )
    if not root.is_absolute():
        raise BrowserConfigurationError(
            "browser_profile_root_invalid",
            f"{PLAYWRIGHT_PROFILE_ROOT_ENV} 必须是绝对路径",
        )
    profile_key = hashlib.sha256(normalized_project.encode("utf-8")).hexdigest()[:24]
    return root.resolve(strict=False) / profile_key


def prepare_playwright_profile_dir(
    project_id: Any,
    env: Mapping[str, str] | None = None,
) -> Path:
    """Create the opaque profile directory with user-only permissions."""

    profile_dir = resolve_playwright_profile_dir(project_id, env)
    try:
        profile_dir.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if profile_dir.exists() and (profile_dir.is_symlink() or not profile_dir.is_dir()):
            raise OSError("profile target is not a regular directory")
        profile_dir.mkdir(mode=0o700, exist_ok=True)
        os.chmod(profile_dir.parent, 0o700)
        os.chmod(profile_dir, 0o700)
    except OSError as exc:
        raise BrowserConfigurationError(
            "browser_profile_unavailable",
            "项目浏览器 Profile 无法安全创建或访问",
        ) from exc
    return profile_dir


def _codex_config_path(env: Mapping[str, str]) -> Path:
    codex_home = str(env.get("CODEX_HOME") or "").strip()
    root = Path(codex_home).expanduser() if codex_home else Path.home() / ".codex"
    return root / "config.toml"


def resolve_browser_plugin_command(env: Mapping[str, str] | None = None) -> str:
    source = env if env is not None else os.environ
    if not _env_bool(source, BROWSER_PLUGIN_ENABLED_ENV, True):
        raise BrowserConfigurationError("browser_plugin_disabled", "CCB 浏览器插件备用能力已被关闭")
    config_path = _codex_config_path(source)
    try:
        config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise BrowserConfigurationError(
            "browser_plugin_unavailable",
            "浏览器插件备用能力不可用：Codex 配置无法读取",
        ) from exc
    servers = config.get("mcp_servers") if isinstance(config, dict) else None
    node_repl = servers.get("node_repl") if isinstance(servers, dict) else None
    command = str(node_repl.get("command") or "").strip() if isinstance(node_repl, dict) else ""
    if not command:
        raise BrowserConfigurationError(
            "browser_plugin_unavailable",
            "浏览器插件备用能力不可用：缺少 mcp_servers.node_repl.command",
        )
    resolved = Path(command).expanduser() if Path(command).is_absolute() else None
    if (
        resolved is not None
        and (not resolved.is_file() or not os.access(resolved, os.X_OK))
    ) or (resolved is None and not shutil.which(command)):
        raise BrowserConfigurationError(
            "browser_plugin_unavailable",
            "浏览器插件备用能力不可用：node_repl 命令不存在或不可执行",
        )
    return str(resolved.resolve()) if resolved is not None else command


def browser_plugin_status(env: Mapping[str, str] | None = None) -> tuple[bool, str]:
    try:
        resolve_browser_plugin_command(env)
        return True, ""
    except BrowserConfigurationError as exc:
        return False, str(exc)


def build_browser_run_meta(
    *,
    project_id: Any,
    cli_type: Any,
    requested_mode: Any,
    env: Mapping[str, str] | None = None,
    scheduler_available: bool = True,
) -> dict[str, Any]:
    del scheduler_available
    source = env if env is not None else os.environ
    normalized_cli = str(cli_type or "codex").strip().lower()
    mode = normalize_browser_mode(
        requested_mode,
        default=(DEFAULT_BROWSER_MODE if normalized_cli == "codex" else "off"),
    )
    if normalized_cli != "codex" and mode != "off":
        raise BrowserConfigurationError("browser_mode_cli_unsupported", "浏览器能力目前仅支持 Codex CLI")

    effective_mode = effective_browser_mode(mode)
    playwright_available = _env_bool(source, PLAYWRIGHT_ENABLED_ENV, True)
    plugin_available, plugin_error = browser_plugin_status(source)
    if effective_mode == "plugin":
        # Preserve the precise disabled/unavailable error for explicit requests.
        resolve_browser_plugin_command(source)
    if effective_mode in {"ephemeral", "collab"} and not playwright_available:
        raise BrowserConfigurationError(
            "playwright_mcp_disabled",
            "Playwright MCP 已被关闭，无法使用当前浏览器模式",
        )
    if effective_mode == "collab":
        # Validate project scoping without persisting or exposing the path.
        resolve_playwright_profile_dir(project_id, source)

    enabled_backends: list[str] = []
    if effective_mode in {"ephemeral", "collab"} and playwright_available:
        enabled_backends.append("playwright")
    if effective_mode == "plugin" and plugin_available:
        enabled_backends.append("browser_plugin")
    if not enabled_backends:
        effective_mode = "off"
    return {
        "browser_mode": mode,
        "browser_effective_mode": effective_mode,
        "browser_transport": "stdio" if enabled_backends else "disabled",
        "browser_backend": "+".join(enabled_backends) if enabled_backends else "disabled",
        "browser_available_backends": enabled_backends,
        "browser_profile_scope": (
            "project"
            if effective_mode == "collab"
            else "temporary"
            if effective_mode == "ephemeral"
            else "none"
        ),
        "browser_persistent": effective_mode == "collab",
        "browser_headed": effective_mode == "collab",
    }


def browser_capabilities(
    *,
    env: Mapping[str, str] | None = None,
    scheduler_available: bool = True,
) -> dict[str, Any]:
    del scheduler_available
    source = env if env is not None else os.environ
    playwright_available = _env_bool(source, PLAYWRIGHT_ENABLED_ENV, True)
    plugin_available, plugin_error = browser_plugin_status(source)
    available_modes = ["off"]
    if playwright_available:
        available_modes.extend(["auto", "ephemeral", "collab"])
    if plugin_available:
        available_modes.append("plugin")
    available_backends = (["playwright"] if playwright_available else []) + (
        ["browser_plugin"] if plugin_available else []
    )
    return {
        "default_mode": DEFAULT_BROWSER_MODE if playwright_available else "off",
        "agent_choice": False,
        "auto_compatibility_mode": "collab",
        "available_modes": available_modes,
        "available_backends": available_backends,
        "playwright_enabled": playwright_available,
        "plugin_available": plugin_available,
        "plugin_unavailable_reason": plugin_error,
    }
