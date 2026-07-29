#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Codex CLI Adapter.

Adapter for OpenAI Codex CLI tool (codex exec).
Session directory: ~/.codex/sessions/YYYY/MM/DD/*.jsonl
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Optional

from .base import CLIAdapter, CLIInfo, SessionInfo, resolve_cli_executable
from . import register_adapter
from task_dashboard.browser_mcp_service import (
    PLAYWRIGHT_MCP_PACKAGE,
    browser_plugin_status,
    effective_browser_mode,
    normalize_browser_mode,
    prepare_playwright_profile_dir,
    resolve_browser_plugin_command,
)


@register_adapter
class CodexAdapter(CLIAdapter):
    """Adapter for Codex CLI (codex exec)."""

    _DEFAULT_HTTP_PROVIDER_ID = "openai_ccb_http"
    _DEFAULT_HTTP_BASE_URL = "https://chatgpt.com/backend-api/codex"
    _PLAYWRIGHT_MCP_PACKAGE = PLAYWRIGHT_MCP_PACKAGE
    _PLAYWRIGHT_MCP_ARGS = (
        "--offline",
        "--yes",
        _PLAYWRIGHT_MCP_PACKAGE,
        "--browser=chrome",
        "--timeout-action=10000",
        "--timeout-navigation=60000",
        "--output-mode=stdout",
    )

    @staticmethod
    def _env_bool(name: str, default: bool) -> bool:
        raw = str(os.environ.get(name) or "").strip().lower()
        if not raw:
            return default
        if raw in {"1", "true", "yes", "y", "on"}:
            return True
        if raw in {"0", "false", "no", "n", "off"}:
            return False
        return default

    @staticmethod
    def _env_int(name: str, default: int, min_value: int, max_value: int) -> int:
        raw = str(os.environ.get(name) or "").strip()
        if raw:
            try:
                value = int(raw)
                return max(min_value, min(max_value, value))
            except Exception:
                pass
        return default

    @staticmethod
    def _toml_string(value: str) -> str:
        return json.dumps(str(value or ""), ensure_ascii=False)

    @staticmethod
    def _normalize_cli_reasoning_effort(reasoning_effort: str) -> str:
        effort = str(reasoning_effort or "").strip().lower().replace("-", "_").replace(" ", "_")
        if effort == "extra_high":
            return "xhigh"
        return effort

    @classmethod
    def _build_codex_invocation_prefix(cls) -> list[str]:
        return [resolve_cli_executable("codex")]

    @classmethod
    def _ccb_runtime_config_args(
        cls,
        browser_mode: str = "off",
        project_id: str = "",
    ) -> list[str]:
        """
        Keep CCB's background Codex turns lean and predictable.

        Interactive Codex config can enable apps/connectors and WebSocket
        streaming. CCB does not need app preloading, and run-level recovery is
        already visible in the dashboard, so the child process defaults to an
        HTTP-only provider to avoid hidden startup retry loops.
        """
        args: list[str] = []

        if cls._env_bool("TASK_DASHBOARD_CODEX_DISABLE_APPS", True):
            args.extend(["-c", "features.apps=false"])

        # A run gets exactly one browser controller. Persistent Playwright uses
        # an opaque project profile; the plugin remains an explicit fallback.
        playwright_enabled = cls._env_bool(
            "TASK_DASHBOARD_CODEX_PLAYWRIGHT_MCP",
            True,
        )
        mode = normalize_browser_mode(browser_mode)
        effective_mode = effective_browser_mode(mode)
        playwright_mcp_args = list(cls._PLAYWRIGHT_MCP_ARGS)
        if effective_mode == "ephemeral":
            playwright_mcp_args.extend(["--headless", "--isolated"])
        elif effective_mode == "collab":
            profile_dir = prepare_playwright_profile_dir(project_id)
            playwright_mcp_args.extend(["--user-data-dir", str(profile_dir)])
        playwright_args = json.dumps(
            playwright_mcp_args,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        playwright_active = playwright_enabled and effective_mode in {"ephemeral", "collab"}
        playwright_config = (
            "mcp_servers.playwright="
            f'{{command="npx",args={playwright_args},enabled={str(playwright_active).lower()}}}'
        )
        plugin_available, _plugin_error = browser_plugin_status()
        plugin_active = plugin_available and effective_mode == "plugin"
        if effective_mode == "plugin" and not plugin_available:
            resolve_browser_plugin_command()
        node_repl_config = (
            "mcp_servers.node_repl.enabled=true"
            if plugin_active
            else 'mcp_servers.node_repl={command="",enabled=false}'
        )
        args.extend(
            [
                "-c",
                playwright_config,
                "-c",
                'mcp_servers.chrome-devtools={command="",enabled=false}',
                "-c",
                'mcp_servers.agent-browser={command="",enabled=false}',
                "-c",
                'mcp_servers.agent-browser-headed={command="",enabled=false}',
                "-c",
                node_repl_config,
                "-c",
                'mcp_servers.computer-use={command="",enabled=false}',
            ]
        )

        if not cls._env_bool("TASK_DASHBOARD_CODEX_FORCE_HTTP", True):
            return args

        provider_id = str(
            os.environ.get("TASK_DASHBOARD_CODEX_HTTP_PROVIDER_ID")
            or cls._DEFAULT_HTTP_PROVIDER_ID
        ).strip()
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", provider_id):
            provider_id = cls._DEFAULT_HTTP_PROVIDER_ID

        base_url = str(
            os.environ.get("TASK_DASHBOARD_CODEX_HTTP_BASE_URL")
            or cls._DEFAULT_HTTP_BASE_URL
        ).strip().rstrip("/")
        if not base_url:
            base_url = cls._DEFAULT_HTTP_BASE_URL

        stream_max_retries = cls._env_int(
            "TASK_DASHBOARD_CODEX_STREAM_MAX_RETRIES",
            default=0,
            min_value=0,
            max_value=5,
        )
        request_max_retries = cls._env_int(
            "TASK_DASHBOARD_CODEX_REQUEST_MAX_RETRIES",
            default=1,
            min_value=0,
            max_value=5,
        )

        args.extend(
            [
                "-c",
                f"model_provider={cls._toml_string(provider_id)}",
                "-c",
                f"model_providers.{provider_id}.name={cls._toml_string('OpenAI CCB HTTP')}",
                "-c",
                f"model_providers.{provider_id}.base_url={cls._toml_string(base_url)}",
                "-c",
                f"model_providers.{provider_id}.wire_api={cls._toml_string('responses')}",
                "-c",
                f"model_providers.{provider_id}.requires_openai_auth=true",
                "-c",
                f"model_providers.{provider_id}.supports_websockets=false",
                "-c",
                f"model_providers.{provider_id}.stream_max_retries={stream_max_retries}",
                "-c",
                f"model_providers.{provider_id}.request_max_retries={request_max_retries}",
                "-c",
                "features.responses_websockets=false",
                "-c",
                "features.responses_websockets_v2=false",
            ]
        )
        return args

    @classmethod
    def info(cls) -> CLIInfo:
        return CLIInfo(
            id="codex",
            name="Codex CLI",
            description="OpenAI Codex CLI tool for code execution",
            enabled=True,
        )

    @classmethod
    def supports_model(cls) -> bool:
        return True

    @classmethod
    def get_home_path(cls) -> Path:
        """Get the Codex home directory (~/.codex or CODEX_HOME env)."""
        raw = str(os.environ.get("CODEX_HOME") or "").strip()
        if raw:
            try:
                return Path(raw).expanduser().resolve()
            except Exception:
                pass
        return (Path.home() / ".codex").resolve()

    @classmethod
    def scan_sessions(cls, after_ts: float = 0.0) -> list[SessionInfo]:
        """
        Scan for Codex session files.

        Sessions are stored in: ~/.codex/sessions/YYYY/MM/DD/*.jsonl
        """
        sessions: list[SessionInfo] = []
        home = cls.get_home_path()
        sessions_root = home / "sessions"

        if not sessions_root.exists():
            return sessions

        # Scan today's directory and recent days
        now = time.localtime()
        for day_offset in range(7):  # Check last 7 days
            ts = time.time() - (day_offset * 86400)
            lt = time.localtime(ts)
            day_dir = sessions_root / f"{lt.tm_year:04d}" / f"{lt.tm_mon:02d}" / f"{lt.tm_mday:02d}"

            if not day_dir.exists():
                continue

            for p in day_dir.glob("*.jsonl"):
                try:
                    mtime = p.stat().st_mtime
                    if mtime < after_ts - 1.0:
                        continue
                    session_id = cls.extract_session_id_from_name(p.name)
                    if not session_id:
                        continue
                    sessions.append(
                        SessionInfo(
                            session_id=session_id,
                            path=p,
                            modified_ts=mtime,
                            cli_type="codex",
                        )
                    )
                except Exception:
                    continue

        # Sort by modification time, newest first
        sessions.sort(key=lambda s: s.modified_ts, reverse=True)
        return sessions

    @classmethod
    def build_resume_command(
        cls,
        session_id: str,
        message: str,
        output_path: Path,
        profile_label: str = "",
        model: str = "",
        reasoning_effort: str = "",
        attachments: list[dict[str, Any]] | None = None,
        browser_mode: str = "off",
        project_id: str = "",
    ) -> list[str]:
        """
        Build command to resume a Codex session.

        Command: codex exec --skip-git-repo-check --json -o <output_path> resume <session_id> "<message>"
        With profile: codex exec -p <profile> --skip-git-repo-check --json -o <output_path> resume <session_id> "<message>"
        """
        cmd = cls._build_codex_invocation_prefix() + ["exec"]
        if profile_label:
            cmd.extend(["-p", profile_label])
        cmd.extend(cls._ccb_runtime_config_args(browser_mode, project_id))
        if model:
            cmd.extend(["-m", model])
        effort = cls._normalize_cli_reasoning_effort(reasoning_effort)
        if effort:
            cmd.extend(["-c", f'model_reasoning_effort="{effort}"'])
        resume_image_args: list[str] = []
        for attachment in attachments if isinstance(attachments, list) else []:
            if not isinstance(attachment, dict):
                continue
            kind = str(attachment.get("kind") or attachment.get("attachment_kind") or "").strip().lower()
            content_type = str(
                attachment.get("content_type")
                or attachment.get("contentType")
                or attachment.get("mimeType")
                or attachment.get("mime_type")
                or ""
            ).strip().lower()
            if kind and kind != "image":
                continue
            if content_type and not content_type.startswith("image/"):
                continue
            image_path = str(
                attachment.get("resolved_local_path")
                or attachment.get("local_path")
                or attachment.get("path")
                or attachment.get("file_path")
                or ""
            ).strip()
            if not image_path:
                continue
            resume_image_args.extend(["-i", image_path])
        cmd.extend(
            [
                "--skip-git-repo-check",
                "--json",
                "-o",
                str(output_path),
                "resume",
                *resume_image_args,
                session_id,
                "--",
                message,
            ]
        )
        return cmd

    @classmethod
    def build_create_command(
        cls,
        seed_prompt: str,
        output_path: Path,
        model: str = "",
        reasoning_effort: str = "",
        sandbox_mode: str = "read-only",
        browser_mode: str = "off",
        project_id: str = "",
    ) -> list[str]:
        """
        Build command to create a new Codex session.

        Command: codex exec --skip-git-repo-check [--sandbox <mode>] -o <output_path> "<seed_prompt>"
        """
        cmd = cls._build_codex_invocation_prefix() + ["exec"]
        cmd.extend(cls._ccb_runtime_config_args(browser_mode, project_id))
        if model:
            cmd.extend(["-m", model])
        effort = cls._normalize_cli_reasoning_effort(reasoning_effort)
        if effort:
            cmd.extend(["-c", f'model_reasoning_effort="{effort}"'])
        cmd.extend(["--skip-git-repo-check"])
        sandbox = str(sandbox_mode or "").strip()
        if sandbox:
            cmd.extend(["--sandbox", sandbox])
        cmd.extend(["-o", str(output_path), str(seed_prompt or "请回复 OK。")])
        return cmd

    @classmethod
    def parse_output_line(cls, line: str) -> Optional[dict[str, Any]]:
        """
        Parse a line of Codex JSON output.

        Codex outputs JSON lines with structure like:
        {"type": "item.completed", "item": {"type": "agent_message", "text": "..."}}
        """
        stripped = str(line or "").strip()
        if not stripped.startswith("{"):
            return None
        try:
            obj = json.loads(stripped)
        except json.JSONDecodeError:
            return None
        return obj if isinstance(obj, dict) else None

    @classmethod
    def get_process_signature(cls, session_id: str) -> str:
        """
        Get process signature for pgrep.

        Codex processes can be found by looking for "codex exec" with the session_id.
        """
        return f"codex exec"

    @classmethod
    def find_new_session_id(cls, start_ts: float) -> tuple[str, str]:
        """
        Find the most recently created session after start_ts.

        This is a helper for session creation - scans for the newest session
        file created after the given timestamp.

        Returns:
            Tuple of (session_id, session_path) or ("", "") if not found.
        """
        sessions = cls.scan_sessions(after_ts=start_ts)
        if not sessions:
            return "", ""
        newest = sessions[0]
        return newest.session_id, str(newest.path)

    @classmethod
    def extract_session_id_from_output(cls, text: str) -> str:
        import re

        raw = str(text or "")
        patterns = [
            r"session id:\s*([0-9a-fA-F-]{36})",
            r"thread_id\"\s*:\s*\"([0-9a-fA-F-]{36})\"",
        ]
        for pattern in patterns:
            match = re.search(pattern, raw, flags=re.IGNORECASE)
            if not match:
                continue
            session_id = str(match.group(1) or "").strip().lower()
            if cls.is_valid_session_id(session_id):
                return session_id
        return ""
