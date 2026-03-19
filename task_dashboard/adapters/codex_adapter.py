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
import time
from pathlib import Path
from typing import Any, Optional

from .base import CLIAdapter, CLIInfo, SessionInfo, resolve_cli_executable
from . import register_adapter


@register_adapter
class CodexAdapter(CLIAdapter):
    """Adapter for Codex CLI (codex exec)."""

    @staticmethod
    def _normalize_cli_reasoning_effort(reasoning_effort: str) -> str:
        effort = str(reasoning_effort or "").strip().lower().replace("-", "_").replace(" ", "_")
        if effort == "extra_high":
            return "xhigh"
        return effort

    @classmethod
    def _build_codex_invocation_prefix(cls) -> list[str]:
        preferred_bin = Path.home() / ".local" / "bin"
        preferred_codex = preferred_bin / "codex"
        if preferred_codex.exists():
            return [str(preferred_codex)]
        return [resolve_cli_executable("codex")]

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
    ) -> list[str]:
        """
        Build command to resume a Codex session.

        Command: codex exec --skip-git-repo-check --json -o <output_path> resume <session_id> "<message>"
        With profile: codex exec -p <profile> --skip-git-repo-check --json -o <output_path> resume <session_id> "<message>"
        """
        cmd = cls._build_codex_invocation_prefix() + ["exec"]
        if profile_label:
            cmd.extend(["-p", profile_label])
        if model:
            cmd.extend(["-m", model])
        effort = cls._normalize_cli_reasoning_effort(reasoning_effort)
        if effort:
            cmd.extend(["-c", f'model_reasoning_effort="{effort}"'])
        cmd.extend(
            [
                "--skip-git-repo-check",
                "--json",
                "-o",
                str(output_path),
                "resume",
                session_id,
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
    ) -> list[str]:
        """
        Build command to create a new Codex session.

        Command: codex exec --skip-git-repo-check [--sandbox <mode>] -o <output_path> "<seed_prompt>"
        """
        cmd = cls._build_codex_invocation_prefix() + ["exec"]
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
