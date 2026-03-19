#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Claude Code CLI Adapter.

Adapter for Anthropic Claude Code CLI tool.
Session directory: ~/.claude/projects/*/*.jsonl
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Optional

from .base import CLIAdapter, CLIInfo, SessionInfo, resolve_cli_executable
from . import register_adapter


@register_adapter
class ClaudeAdapter(CLIAdapter):
    """Adapter for Claude Code CLI (claude)."""

    @classmethod
    def info(cls) -> CLIInfo:
        return CLIInfo(
            id="claude",
            name="Claude Code",
            description="Anthropic Claude Code CLI for AI-assisted development",
            enabled=True,
        )

    @classmethod
    def get_home_path(cls) -> Path:
        """Get the Claude home directory (~/.claude or CLAUDE_HOME env)."""
        raw = str(os.environ.get("CLAUDE_HOME") or "").strip()
        if raw:
            try:
                return Path(raw).expanduser().resolve()
            except Exception:
                pass
        return (Path.home() / ".claude").resolve()

    @classmethod
    def scan_sessions(cls, after_ts: float = 0.0) -> list[SessionInfo]:
        """
        Scan for Claude Code session files.

        Sessions are stored in: ~/.claude/projects/*/*.jsonl
        Each project directory contains JSONL session files.
        """
        sessions: list[SessionInfo] = []
        home = cls.get_home_path()
        projects_root = home / "projects"

        if not projects_root.exists():
            return sessions

        # Scan all project directories
        try:
            for project_dir in projects_root.iterdir():
                if not project_dir.is_dir():
                    continue

                for p in project_dir.glob("*.jsonl"):
                    try:
                        mtime = p.stat().st_mtime
                        if mtime < after_ts - 1.0:
                            continue
                        session_id = cls.extract_session_id_from_name(p.name)
                        if not session_id:
                            # Try to extract from path or file content
                            session_id = cls._extract_session_from_path(p, project_dir.name)
                        if not session_id:
                            continue
                        sessions.append(
                            SessionInfo(
                                session_id=session_id,
                                path=p,
                                modified_ts=mtime,
                                cli_type="claude",
                                metadata={"project": project_dir.name},
                            )
                        )
                    except Exception:
                        continue
        except Exception:
            pass

        # Sort by modification time, newest first
        sessions.sort(key=lambda s: s.modified_ts, reverse=True)
        return sessions

    @classmethod
    def _extract_session_from_path(cls, path: Path, project_name: str) -> str:
        """
        Try to extract session ID from path or first line of file.

        Some Claude sessions may have the ID in the first line of the JSONL.
        """
        # Try to read first line for session ID
        try:
            with path.open("r", encoding="utf-8", errors="ignore") as f:
                first_line = f.readline().strip()
                if first_line.startswith("{"):
                    obj = json.loads(first_line)
                    # Look for sessionId in various places
                    sid = (
                        obj.get("sessionId")
                        or obj.get("session_id")
                        or (obj.get("meta", {}) or {}).get("sessionId")
                    )
                    if sid and cls.is_valid_session_id(str(sid)):
                        return str(sid).lower()
        except Exception:
            pass

        return ""

    @classmethod
    def build_resume_command(
        cls,
        session_id: str,
        message: str,
        output_path: Path,
        profile_label: str = "",
        model: str = "",
        reasoning_effort: str = "",
    ) -> list[str]:
        """
        Build command to resume a Claude session.

        Command: claude --resume <session_id> --print "<message>"
        The --print flag outputs to stdout which we can capture.
        """
        cmd = [
            resolve_cli_executable("claude"),
            "--dangerously-skip-permissions",
            "--resume",
            session_id,
            "--print",
            message,
        ]
        # Note: Claude Code may not support profile labels the same way.
        # The profile_label parameter is ignored for now but kept for interface consistency.
        return cmd

    @classmethod
    def build_create_command(
        cls,
        seed_prompt: str,
        output_path: Path,
        model: str = "",
        reasoning_effort: str = "",
        sandbox_mode: str = "read-only",
    ) -> list[str]:
        """
        Build command to create a new Claude session.

        Command: claude --print "<seed_prompt>"
        This creates a new session and outputs the response.
        """
        _ = sandbox_mode
        return [
            resolve_cli_executable("claude"),
            "--dangerously-skip-permissions",
            "--print",
            str(seed_prompt or "Please reply with: OK"),
        ]

    @classmethod
    def parse_output_line(cls, line: str) -> Optional[dict[str, Any]]:
        """
        Parse a line of Claude output.

        Claude Code default stdout is user-facing正文，不应逐行落入过程轨。
        这里只保留结构化输出；普通文本由最终 last message 展示。
        """
        stripped = str(line or "").strip()
        if not stripped:
            return None

        # Try to parse as JSON for structured output
        if stripped.startswith("{"):
            try:
                obj = json.loads(stripped)
                return obj if isinstance(obj, dict) else None
            except json.JSONDecodeError:
                pass

        return None

    @classmethod
    def get_process_signature(cls, session_id: str) -> str:
        """
        Get process signature for pgrep.

        Claude processes can be found by looking for "claude" with the session_id.
        """
        return "claude"

    @classmethod
    def find_new_session_id(cls, start_ts: float) -> tuple[str, str]:
        """
        Find the most recently created session after start_ts.

        Returns:
            Tuple of (session_id, session_path) or ("", "") if not found.
        """
        sessions = cls.scan_sessions(after_ts=start_ts)
        if not sessions:
            return "", ""
        newest = sessions[0]
        return newest.session_id, str(newest.path)
