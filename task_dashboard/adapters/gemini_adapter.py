#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Gemini CLI Adapter.

Adapter for Google Gemini CLI tool.
Session directory: ~/.gemini/tmp/*/chats/session-*.json
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

from .base import CLIAdapter, CLIInfo, SessionInfo, resolve_cli_executable
from . import register_adapter


@register_adapter
class GeminiAdapter(CLIAdapter):
    """Adapter for Gemini CLI (gemini)."""

    @classmethod
    def info(cls) -> CLIInfo:
        return CLIInfo(
            id="gemini",
            name="Gemini CLI",
            description="Google Gemini CLI for code and task execution",
            enabled=True,
        )

    @classmethod
    def get_home_path(cls) -> Path:
        """
        Get Gemini data directory.

        Gemini CLI stores runtime data under:
        - ~/.gemini
        - or $GEMINI_CLI_HOME/.gemini when GEMINI_CLI_HOME is set
        """
        raw = str(os.environ.get("GEMINI_CLI_HOME") or "").strip()
        if raw:
            try:
                base = Path(raw).expanduser().resolve()
                if base.name == ".gemini":
                    return base
                return (base / ".gemini").resolve()
            except Exception:
                pass
        return (Path.home() / ".gemini").resolve()

    @classmethod
    def scan_sessions(cls, after_ts: float = 0.0) -> list[SessionInfo]:
        """
        Scan for Gemini session files.

        Sessions are stored in: ~/.gemini/tmp/<project_hash>/chats/session-*.json
        """
        sessions: list[SessionInfo] = []
        home = cls.get_home_path()
        tmp_root = home / "tmp"
        if not tmp_root.exists():
            return sessions

        try:
            for project_dir in tmp_root.iterdir():
                if not project_dir.is_dir():
                    continue
                chats_dir = project_dir / "chats"
                if not chats_dir.exists() or not chats_dir.is_dir():
                    continue
                for p in chats_dir.glob("session-*.json"):
                    try:
                        mtime = p.stat().st_mtime
                        if mtime < after_ts - 1.0:
                            continue
                        with p.open("r", encoding="utf-8", errors="ignore") as f:
                            data = json.load(f)
                        session_id = (
                            data.get("sessionId")
                            or data.get("session_id")
                            or cls.extract_session_id_from_name(p.name)
                        )
                        if not session_id:
                            continue
                        sid = str(session_id).strip()
                        if not sid:
                            continue
                        if cls.is_valid_session_id(sid):
                            sid = sid.lower()
                        elif len(sid) < 8:
                            continue

                        sessions.append(
                            SessionInfo(
                                session_id=sid,
                                path=p,
                                modified_ts=mtime,
                                cli_type="gemini",
                                metadata={
                                    "project_hash": project_dir.name,
                                    "start_time": str(data.get("startTime") or ""),
                                    "last_updated": str(data.get("lastUpdated") or ""),
                                },
                            )
                        )
                    except Exception:
                        continue
        except Exception:
            pass

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
        Build command to resume a Gemini session.

        Command: gemini --resume <session_id> --prompt "<message>" --output-format json
        """
        cmd = [
            resolve_cli_executable("gemini"),
            "--resume",
            session_id,
            "--prompt",
            message,
            "--output-format",
            "json",
        ]
        # Gemini CLI does not have codex-style profile labels. Keep the field for interface compatibility.
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
        Build command to create a new Gemini session.

        Command: gemini --prompt "<seed_prompt>" --output-format json
        """
        _ = sandbox_mode
        return [
            resolve_cli_executable("gemini"),
            "--prompt",
            str(seed_prompt or "Please reply with: OK"),
            "--output-format",
            "json",
        ]

    @classmethod
    def parse_output_line(cls, line: str) -> Optional[dict[str, Any]]:
        """
        Parse a line of Gemini output.

        Non-interactive mode with --output-format json returns a structured JSON object
        with fields like `session_id` and `response`.
        """
        stripped = str(line or "").strip()
        if not stripped:
            return None

        if stripped.startswith("{") or stripped.startswith("["):
            try:
                obj = json.loads(stripped)
            except json.JSONDecodeError:
                return {"type": "text", "text": stripped}

            if isinstance(obj, dict):
                if str(obj.get("type") or "") in {"item.completed", "text", "message"}:
                    return obj
                response = str(obj.get("response") or "").strip()
                if response:
                    return {"type": "message", "content": response}
                text = str(obj.get("text") or "").strip()
                if text:
                    return {"type": "text", "text": text}
                err = obj.get("error")
                if isinstance(err, dict):
                    err = err.get("message")
                err_txt = str(err or "").strip()
                if err_txt:
                    return {"type": "message", "content": err_txt}
                return obj

            if isinstance(obj, list):
                return {"items": obj}

        return {"type": "text", "text": stripped}

    @classmethod
    def get_process_signature(cls, session_id: str) -> str:
        """
        Get process signature for pgrep.

        Gemini processes can be found by looking for "gemini".
        """
        return "gemini"

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
