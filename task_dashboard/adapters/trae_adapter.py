#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Trae Agent CLI Adapter.

Adapter for trae-agent CLI (`trae-cli`).

Notes:
- Trae CLI currently exposes task-based `run` execution rather than a native
  external session-resume id API. For task-dashboard compatibility, we keep a
  synthetic session id discovered from task-dashboard bootstrap trajectory files.
- Runtime execution remains fully functional because each run writes trajectory
  output to a run-scoped file.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Optional

from . import register_adapter
from .base import CLIAdapter, CLIInfo, SessionInfo, resolve_cli_executable


@register_adapter
class TraeAdapter(CLIAdapter):
    """Adapter for Trae Agent CLI (trae)."""

    @classmethod
    def info(cls) -> CLIInfo:
        return CLIInfo(
            id="trae",
            name="Trae Agent CLI",
            description="Bytedance Trae Agent CLI task execution",
            enabled=True,
        )

    @classmethod
    def get_home_path(cls) -> Path:
        """
        Get Trae Agent runtime home directory.

        Priority:
        1) $TRAE_AGENT_HOME
        2) ~/.trae-agent
        """
        raw = str(os.environ.get("TRAE_AGENT_HOME") or "").strip()
        if raw:
            try:
                return Path(raw).expanduser().resolve()
            except Exception:
                pass
        return (Path.home() / ".trae-agent").resolve()

    @classmethod
    def _resolve_config_file(cls, profile_label: str = "") -> str:
        """
        Resolve Trae config path.

        Priority:
        1) TASK_DASHBOARD_TRAE_CONFIG_FILE
        2) TRAE_CONFIG_FILE
        3) profile_label when it looks like a config path
        """
        env_cfg = str(os.environ.get("TASK_DASHBOARD_TRAE_CONFIG_FILE") or "").strip()
        if env_cfg:
            return env_cfg
        env_cfg2 = str(os.environ.get("TRAE_CONFIG_FILE") or "").strip()
        if env_cfg2:
            return env_cfg2
        p = str(profile_label or "").strip()
        if p and ("/" in p or p.endswith(".yaml") or p.endswith(".yml") or p.endswith(".json")):
            return p
        return ""

    @classmethod
    def _default_max_steps(cls) -> int:
        raw = str(os.environ.get("TASK_DASHBOARD_TRAE_MAX_STEPS") or "").strip()
        if raw.isdigit():
            try:
                val = int(raw)
                if val > 0:
                    return val
            except Exception:
                pass
        return 20

    @classmethod
    def _build_run_command(
        cls,
        task_text: str,
        output_path: Path,
        profile_label: str = "",
        model: str = "",
        reasoning_effort: str = "",
    ) -> list[str]:
        cmd = [
            resolve_cli_executable("trae-cli"),
            "run",
            str(task_text or "Please reply with: OK"),
            "--trajectory-file",
            str(output_path),
            "--max-steps",
            str(cls._default_max_steps()),
        ]
        config_file = cls._resolve_config_file(profile_label=profile_label)
        if config_file:
            cmd.extend(["--config-file", config_file])
        if str(model or "").strip():
            cmd.extend(["--model", str(model).strip()])
        return cmd

    @classmethod
    def scan_sessions(cls, after_ts: float = 0.0) -> list[SessionInfo]:
        """
        Scan synthetic bootstrap session artifacts.

        create_cli_session() passes output_path:
        ~/.trae-agent/tmp/task-dashboard-new-session-<ts>.last.txt
        We map each file to a synthetic UUID-like session id.
        """
        sessions: list[SessionInfo] = []
        home = cls.get_home_path()
        tmp_root = home / "tmp"
        if not tmp_root.exists():
            return sessions
        try:
            for p in tmp_root.glob("task-dashboard-new-session-*"):
                try:
                    st = p.stat()
                    mtime = st.st_mtime
                    if mtime < after_ts - 1.0:
                        continue
                    digest = hashlib.md5(str(p.resolve()).encode("utf-8")).hexdigest()
                    sid = f"{digest[0:8]}-{digest[8:12]}-{digest[12:16]}-{digest[16:20]}-{digest[20:32]}"
                    sessions.append(
                        SessionInfo(
                            session_id=sid,
                            path=p,
                            modified_ts=mtime,
                            cli_type="trae",
                            metadata={"synthetic": True},
                        )
                    )
                except Exception:
                    continue
        except Exception:
            return sessions
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
        Build command to execute a task turn via Trae CLI.

        Trae CLI does not currently expose external session-resume ids.
        We accept session_id for interface compatibility but do not pass it.
        """
        _ = session_id
        return cls._build_run_command(
            task_text=message,
            output_path=output_path,
            profile_label=profile_label,
            model=model,
            reasoning_effort=reasoning_effort,
        )

    @classmethod
    def build_create_command(
        cls,
        seed_prompt: str,
        output_path: Path,
        model: str = "",
        reasoning_effort: str = "",
        sandbox_mode: str = "read-only",
    ) -> list[str]:
        """Build command to create a logical Trae conversation session."""
        _ = sandbox_mode
        return cls._build_run_command(
            task_text=seed_prompt or "请回复 OK。",
            output_path=output_path,
            profile_label="",
            model=model,
            reasoning_effort=reasoning_effort,
        )

    @classmethod
    def parse_output_line(cls, line: str) -> Optional[dict[str, Any]]:
        stripped = str(line or "").strip()
        if not stripped:
            return None
        if stripped.startswith("{") or stripped.startswith("["):
            try:
                obj = json.loads(stripped)
                if isinstance(obj, dict):
                    return obj
                return {"items": obj}
            except Exception:
                return {"type": "text", "text": stripped}
        return {"type": "text", "text": stripped}

    @classmethod
    def get_process_signature(cls, session_id: str) -> str:
        _ = session_id
        return "trae-cli"

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
