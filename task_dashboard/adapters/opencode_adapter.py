#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
OpenCode CLI Adapter.

Adapter for OpenCode CLI tool.
Session directory: ~/.local/share/opencode/sessions/*.json
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Optional

from .base import CLIAdapter, CLIInfo, SessionInfo, resolve_cli_executable
from . import register_adapter


@register_adapter
class OpenCodeAdapter(CLIAdapter):
    """Adapter for OpenCode CLI (opencode)."""

    @classmethod
    def info(cls) -> CLIInfo:
        return CLIInfo(
            id="opencode",
            name="OpenCode",
            description="OpenCode CLI for open-source code assistance",
            enabled=True,
        )

    @classmethod
    def get_home_path(cls) -> Path:
        """Get the OpenCode data directory (~/.local/share/opencode or OPENCODE_HOME env)."""
        raw = str(os.environ.get("OPENCODE_HOME") or "").strip()
        if raw:
            try:
                return Path(raw).expanduser().resolve()
            except Exception:
                pass
        return (Path.home() / ".local" / "share" / "opencode").resolve()

    @classmethod
    def scan_sessions(cls, after_ts: float = 0.0) -> list[SessionInfo]:
        """
        Scan for OpenCode session files.

        Sessions are stored as JSON files in: ~/.local/share/opencode/sessions/*.json
        Each JSON file contains session metadata.
        """
        sessions: list[SessionInfo] = []
        home = cls.get_home_path()
        sessions_root = home / "sessions"
        seen_ids: set[str] = set()

        def _append_session(
            session_id: Any,
            *,
            path: Path,
            modified_ts: float,
            metadata: dict[str, Any] | None = None,
        ) -> None:
            sid = str(session_id or "").strip()
            if not sid:
                return
            if not cls.is_valid_session_id(sid) and len(sid) < 8:
                return
            if sid in seen_ids:
                return
            seen_ids.add(sid)
            sessions.append(
                SessionInfo(
                    session_id=sid,
                    path=path,
                    modified_ts=modified_ts,
                    cli_type="opencode",
                    metadata=metadata if isinstance(metadata, dict) else {},
                )
            )

        if sessions_root.exists():
            try:
                for p in sessions_root.glob("*.json"):
                    try:
                        mtime = p.stat().st_mtime
                        if mtime < after_ts - 1.0:
                            continue
                        with p.open("r", encoding="utf-8", errors="ignore") as f:
                            data = json.load(f)
                        session_id = (
                            data.get("id")
                            or data.get("sessionId")
                            or data.get("session_id")
                            or cls.extract_session_id_from_name(p.name)
                        )
                        _append_session(
                            session_id,
                            path=p,
                            modified_ts=mtime,
                            metadata=data if isinstance(data, dict) else {},
                        )
                    except Exception:
                        continue
            except Exception:
                pass

        db_path = home / "opencode.db"
        if db_path.exists():
            try:
                conn = sqlite3.connect(str(db_path))
                try:
                    rows = conn.execute(
                        """
                        SELECT id, project_id, slug, directory, title, version, time_created, time_updated
                        FROM session
                        ORDER BY time_updated DESC
                        """
                    ).fetchall()
                finally:
                    conn.close()
                for row in rows:
                    try:
                        raw_updated = row[7]
                        updated_ts = float(raw_updated or 0)
                        if updated_ts > 10_000_000_000:
                            updated_ts = updated_ts / 1000.0
                        if updated_ts < after_ts - 1.0:
                            continue
                        _append_session(
                            row[0],
                            path=db_path,
                            modified_ts=updated_ts,
                            metadata={
                                "project_id": row[1],
                                "slug": row[2],
                                "directory": row[3],
                                "title": row[4],
                                "version": row[5],
                                "time_created": row[6],
                                "time_updated": row[7],
                            },
                        )
                    except Exception:
                        continue
            except Exception:
                pass

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
        Build command to resume an OpenCode session.

        Command: opencode run --session <session_id> "<message>"
        """
        cmd = [
            resolve_cli_executable("opencode"),
            "run",
            "--session",
            session_id,
            message,
        ]
        # Note: OpenCode may have different profile/config handling.
        # The profile_label parameter is kept for interface consistency.
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
        Build command to create a new OpenCode session.

        Command: opencode run "<seed_prompt>"
        Without --session, this creates a new session.
        """
        _ = sandbox_mode
        return [
            resolve_cli_executable("opencode"),
            "run",
            str(seed_prompt or "Please reply with: OK"),
        ]

    @classmethod
    def parse_output_line(cls, line: str) -> Optional[dict[str, Any]]:
        """
        Parse a line of OpenCode output.

        OpenCode may output JSON or text depending on mode.
        """
        stripped = str(line or "").strip()
        if not stripped:
            return None

        # Try to parse as JSON
        if stripped.startswith("{") or stripped.startswith("["):
            try:
                obj = json.loads(stripped)
                return obj if isinstance(obj, dict) else {"items": obj}
            except json.JSONDecodeError:
                pass

        # Return plain text as structured message
        return {"type": "text", "text": stripped}

    @classmethod
    def get_process_signature(cls, session_id: str) -> str:
        """
        Get process signature for pgrep.

        OpenCode processes can be found by looking for "opencode" with the session_id.
        """
        return "opencode"

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
