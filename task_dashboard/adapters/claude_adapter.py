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
import sys
import time
from pathlib import Path
from typing import Any, Optional

from .base import CLIAdapter, CLIInfo, SessionInfo
from . import register_adapter
from .claude_runner import normalize_permission_mode
from task_dashboard.claude_models import normalize_claude_model


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
    def resolve_session_cwd(cls, session_id: str) -> str:
        """
        Return the cwd where a Claude session was created.

        Claude stores sessions under ~/.claude/projects/<cwd-scope>/<id>.jsonl
        and resolves `claude --resume` within the current cwd scope. CCB can
        resume from a different project cwd, so we locate the session file
        globally and read the cwd recorded in its JSONL metadata.
        """
        sid = str(session_id or "").strip()
        if not sid:
            return ""
        projects_root = cls.get_home_path() / "projects"
        if not projects_root.exists():
            return ""
        try:
            matches = sorted(
                projects_root.glob(f"*/{sid}.jsonl"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
        except Exception:
            return ""
        for path in matches:
            try:
                with path.open("r", encoding="utf-8", errors="ignore") as f:
                    for _ in range(20):
                        line = f.readline()
                        if not line:
                            break
                        if '"cwd"' not in line:
                            continue
                        obj = json.loads(line.strip())
                        cwd = str(obj.get("cwd") or "").strip()
                        if not cwd:
                            continue
                        candidate = Path(cwd).expanduser()
                        if candidate.exists() and candidate.is_dir():
                            return str(candidate)
            except Exception:
                continue
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
        permission_mode: str = "",
    ) -> list[str]:
        """
        Build command to resume a Claude session.

        CCB executes a thin runner so Claude stream-json can be normalized into
        process events while the public final result is written to output_path.
        """
        _ = profile_label, reasoning_effort
        cmd = [
            sys.executable or "python3",
            "-m",
            "task_dashboard.adapters.claude_runner",
            "--message",
            str(message or "Please reply with: OK"),
            "--output-path",
            str(output_path),
        ]
        cmd.extend(["--model", normalize_claude_model(model)])
        permission_mode_text = str(permission_mode or "").strip()
        if permission_mode_text:
            cmd.extend(["--permission-mode", normalize_permission_mode(permission_mode_text)])
        cmd.extend(
            [
                "resume",
                # Keep --resume in the wrapper command so execution_command can
                # still relocate the subprocess cwd to the original Claude
                # session directory before the runner starts.
                "--resume",
                str(session_id or "").strip(),
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
        permission_mode: str = "",
    ) -> list[str]:
        """
        Build command to create a new Claude session through the CCB runner.
        """
        _ = reasoning_effort, sandbox_mode
        cmd = [
            sys.executable or "python3",
            "-m",
            "task_dashboard.adapters.claude_runner",
            "--message",
            str(seed_prompt or "Please reply with: OK"),
            "--output-path",
            str(output_path),
        ]
        cmd.extend(["--model", normalize_claude_model(model)])
        permission_mode_text = str(permission_mode or "").strip()
        if permission_mode_text:
            cmd.extend(["--permission-mode", normalize_permission_mode(permission_mode_text)])
        cmd.append("create")
        return cmd

    @classmethod
    def parse_output_line(cls, line: str) -> Optional[dict[str, Any]]:
        """
        Parse a line of Claude runner output.

        Runner stdout emits only CCB process event JSONL plus the final public
        text line. Raw Claude stream-json/system/user records are ignored here.
        """
        stripped = str(line or "").strip()
        if not stripped or not stripped.startswith("{"):
            return None
        try:
            obj = json.loads(stripped)
        except json.JSONDecodeError:
            return None
        if not isinstance(obj, dict):
            return None
        event_type = str(obj.get("type") or "").strip()
        if event_type in {"tool_call.started", "tool_call.completed", "runtime_event.completed"}:
            return obj
        if event_type == "result":
            text = str(obj.get("result") or "").strip()
            if text:
                return {"type": "message", "content": text}
        return None

    @classmethod
    def get_process_signature(cls, session_id: str) -> str:
        """
        Get process signature for pgrep.

        CCB now launches Claude through the adapter runner.
        """
        _ = session_id
        return "task_dashboard.adapters.claude_runner"

    @classmethod
    def supports_model(cls) -> bool:
        return True

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
