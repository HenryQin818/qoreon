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
        model_name = str(model or "").strip()
        if model_name:
            cmd.extend(["--model", model_name])
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
        cmd = [
            resolve_cli_executable("gemini"),
            "--prompt",
            str(seed_prompt or "Please reply with: OK"),
            "--output-format",
            "json",
        ]
        model_name = str(model or "").strip()
        if model_name:
            cmd.extend(["--model", model_name])
        return cmd

    @classmethod
    def supports_model(cls) -> bool:
        """Gemini CLI supports explicit model selection via --model."""
        return True

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
                if cls._looks_like_json_fragment(stripped):
                    return None
                return {"type": "text", "text": stripped}

            text = cls._extract_text_from_json(obj)
            if text:
                return {"type": "message", "content": text}
            return None

        if cls._looks_like_json_fragment(stripped):
            return None

        return {"type": "text", "text": stripped}

    @classmethod
    def _looks_like_json_fragment(cls, text: str) -> bool:
        txt = str(text or "").strip()
        if not txt:
            return False
        if txt in {"{", "}", "[", "]", "},", "],"}:
            return True
        if txt.startswith('"') and (txt.endswith(",") or ":" in txt):
            return True
        if txt.startswith(("}", "]")):
            return True
        return False

    @classmethod
    def _extract_text_from_json(cls, value: Any) -> str:
        if isinstance(value, dict):
            msg_type = str(value.get("type") or "")
            if msg_type == "item.completed":
                item = value.get("item") or {}
                if isinstance(item, dict) and str(item.get("type") or "") == "agent_message":
                    return str(item.get("text") or "").strip()
            if msg_type in {"text", "message", "agent_message"}:
                direct = str(value.get("content") or value.get("text") or "").strip()
                if direct:
                    return direct

            for key in ("response", "text", "content", "message"):
                direct = value.get(key)
                if isinstance(direct, str) and direct.strip():
                    return direct.strip()
                nested = cls._extract_text_from_json(direct)
                if nested:
                    return nested

            err = value.get("error")
            if isinstance(err, dict):
                err_txt = str(err.get("message") or err.get("text") or "").strip()
                if err_txt:
                    return err_txt
            elif isinstance(err, str) and err.strip():
                return err.strip()

            candidates = value.get("candidates")
            if isinstance(candidates, list):
                text = cls._extract_text_from_json(candidates)
                if text:
                    return text

            parts = value.get("parts")
            if isinstance(parts, list):
                text = cls._extract_text_from_json(parts)
                if text:
                    return text

            item = value.get("item")
            if isinstance(item, dict):
                text = cls._extract_text_from_json(item)
                if text:
                    return text

        if isinstance(value, list):
            parts: list[str] = []
            for item in value:
                text = cls._extract_text_from_json(item)
                if text:
                    parts.append(text)
            return "\n".join(parts).strip()

        return ""

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
