#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""CodeBuddy Code CLI Adapter.

Adapter for Tencent CodeBuddy Code (`codebuddy`).
Session directory: ~/.codebuddy/projects/*/*.jsonl
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

from . import register_adapter
from .base import CLIAdapter, CLIInfo, SessionInfo
from .codebuddy_output import extract_final_text, normalize_process_event
from .codebuddy_runner import normalize_permission_mode


@register_adapter
class CodeBuddyAdapter(CLIAdapter):
    """Adapter for CodeBuddy Code CLI (codebuddy)."""

    @classmethod
    def info(cls) -> CLIInfo:
        return CLIInfo(
            id="codebuddy",
            name="CodeBuddy Code",
            description="Tencent CodeBuddy Code CLI",
            enabled=True,
        )

    @classmethod
    def get_home_path(cls) -> Path:
        raw = str(os.environ.get("CODEBUDDY_HOME") or "").strip()
        if raw:
            try:
                return Path(raw).expanduser().resolve()
            except Exception:
                pass
        return (Path.home() / ".codebuddy").resolve()

    @classmethod
    def scan_sessions(cls, after_ts: float = 0.0) -> list[SessionInfo]:
        sessions: list[SessionInfo] = []
        projects_root = cls.get_home_path() / "projects"
        if not projects_root.exists():
            return sessions
        try:
            for p in projects_root.glob("*/*.jsonl"):
                try:
                    mtime = p.stat().st_mtime
                    if mtime < after_ts - 1.0:
                        continue
                    session_id = str(p.stem or "").strip()
                    if not session_id or len(session_id) < 6:
                        continue
                    sessions.append(
                        SessionInfo(
                            session_id=session_id,
                            path=p,
                            modified_ts=mtime,
                            cli_type="codebuddy",
                            metadata={"project_key": p.parent.name},
                        )
                    )
                except Exception:
                    continue
        except Exception:
            pass
        sessions.sort(key=lambda s: s.modified_ts, reverse=True)
        return sessions

    @classmethod
    def _runner_base(
        cls,
        output_path: Path,
        message: str,
        model: str = "",
        permission_mode: str = "",
    ) -> list[str]:
        cmd = [
            sys.executable or "python3",
            "-m",
            "task_dashboard.adapters.codebuddy_runner",
            "--message",
            str(message or "Please reply with: OK"),
            "--output-path",
            str(output_path),
        ]
        model_name = str(model or "").strip()
        if model_name:
            cmd.extend(["--model", model_name])

        permission_mode_text = str(permission_mode or "").strip()
        if permission_mode_text:
            resolved_permission_mode = normalize_permission_mode(permission_mode_text)
        else:
            resolved_permission_mode = normalize_permission_mode(
                os.environ.get("TASK_DASHBOARD_CODEBUDDY_PERMISSION_MODE")
            )
        if resolved_permission_mode:
            cmd.extend(["--permission-mode", resolved_permission_mode])

        max_turns = str(os.environ.get("TASK_DASHBOARD_CODEBUDDY_MAX_TURNS") or "").strip()
        if max_turns:
            cmd.extend(["--max-turns", max_turns])

        tools = str(os.environ.get("TASK_DASHBOARD_CODEBUDDY_TOOLS") or "").strip()
        if tools:
            cmd.extend(["--tools", tools])
        return cmd

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
        _ = profile_label, reasoning_effort
        cmd = cls._runner_base(
            output_path=output_path,
            message=message,
            model=model,
            permission_mode=permission_mode,
        )
        cmd.extend(["resume", "--session-id", str(session_id or "").strip()])
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
        _ = reasoning_effort, sandbox_mode
        cmd = cls._runner_base(
            output_path=output_path,
            message=seed_prompt or "请回复 OK。",
            model=model,
            permission_mode=permission_mode,
        )
        cmd.append("create")
        return cmd

    @classmethod
    def parse_output_line(cls, line: str) -> Optional[dict[str, Any]]:
        stripped = str(line or "").strip()
        if not stripped:
            return None
        if stripped.startswith("{") or stripped.startswith("["):
            try:
                obj = json.loads(stripped)
            except json.JSONDecodeError:
                return None
            if isinstance(obj, dict):
                event = normalize_process_event(obj)
                if event:
                    return event
            text = extract_final_text(obj)
            if text:
                return {"type": "message", "content": text}
            return None
        return None

    @classmethod
    def get_process_signature(cls, session_id: str) -> str:
        _ = session_id
        return "task_dashboard.adapters.codebuddy_runner"

    @classmethod
    def supports_model(cls) -> bool:
        return True

    @classmethod
    def find_new_session_id(cls, start_ts: float) -> tuple[str, str]:
        sessions = cls.scan_sessions(after_ts=start_ts)
        if not sessions:
            return "", ""
        newest = sessions[0]
        return newest.session_id, str(newest.path)
