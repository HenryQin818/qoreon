#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
CLI Adapter base classes and interfaces for multi-CLI support.

Each CLI tool (codex, claude, opencode, gemini, trae) implements CLIAdapter to provide
consistent interfaces for session management and command execution.
"""

from __future__ import annotations

import os
import re
import shutil
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from task_dashboard.local_cli_bins import get_local_cli_bin_override


@dataclass(frozen=True)
class CLIInfo:
    """Static information about a CLI tool."""

    id: str  # e.g., "codex", "claude", "opencode", "gemini", "trae"
    name: str  # Human-readable name, e.g., "Codex CLI"
    description: str = ""
    enabled: bool = True


@dataclass
class SessionInfo:
    """Information about a discovered CLI session."""

    session_id: str
    path: Path
    modified_ts: float = 0.0
    cli_type: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


def _normalize_explicit_cli_bin(value: str) -> str:
    txt = str(value or "").strip()
    if not txt:
        return ""
    if txt.startswith("~"):
        return str(Path(txt).expanduser())
    return txt


@lru_cache(maxsize=32)
def resolve_cli_executable_details(command: str) -> dict[str, Any]:
    """
    Resolve CLI executable path with minimal service environment fallbacks.

    Some service runners use a minimal PATH (/usr/bin:/bin:/usr/sbin:/sbin),
    so tools installed in /usr/local/bin or ~/.local/bin may be invisible.
    """
    cmd = str(command or "").strip()
    if not cmd:
        return {
            "command": "",
            "path": "",
            "source": "empty",
            "local_override": "",
            "env_override": "",
            "env_key": "",
            "exists": False,
            "executable": False,
        }

    local_override = _normalize_explicit_cli_bin(get_local_cli_bin_override(cmd))
    if local_override:
        local_path = Path(local_override).expanduser()
        return {
            "command": cmd,
            "path": local_override,
            "source": "local_config",
            "local_override": local_override,
            "env_override": "",
            "env_key": "",
            "exists": local_path.exists(),
            "executable": os.access(local_path, os.X_OK),
        }

    key_suffix = re.sub(r"[^A-Z0-9]+", "_", cmd.upper()).strip("_")
    env_key = f"TASK_DASHBOARD_{key_suffix}_BIN"
    override = _normalize_explicit_cli_bin(os.environ.get(env_key) or "")
    if override:
        override_path = Path(override).expanduser()
        if override_path.exists() or ("/" not in override and "\\" not in override and shutil.which(override)):
            return {
                "command": cmd,
                "path": override,
                "source": "env",
                "local_override": local_override,
                "env_override": override,
                "env_key": env_key,
                "exists": override_path.exists() if ("/" in override or "\\" in override or override.startswith("~")) else bool(shutil.which(override)),
                "executable": os.access(override_path, os.X_OK) if override_path.exists() else bool(shutil.which(override)),
            }

    found = shutil.which(cmd)
    if found:
        found_path = Path(found)
        return {
            "command": cmd,
            "path": found,
            "source": "PATH",
            "local_override": local_override,
            "env_override": override,
            "env_key": env_key,
            "exists": found_path.exists(),
            "executable": os.access(found_path, os.X_OK),
        }

    extras = [
        str(Path.home() / ".local" / "bin"),
        str(Path.home() / ".npm-global" / "bin"),
        str(Path.home() / ".bun" / "bin"),
        "/opt/homebrew/bin",
        "/usr/local/bin",
        "/usr/bin",
    ]
    for d in extras:
        p = Path(d) / cmd
        if p.exists() and os.access(p, os.X_OK):
            return {
                "command": cmd,
                "path": str(p),
                "source": "extras",
                "local_override": local_override,
                "env_override": override,
                "env_key": env_key,
                "exists": True,
                "executable": True,
            }
    return {
        "command": cmd,
        "path": cmd,
        "source": "default",
        "local_override": local_override,
        "env_override": override,
        "env_key": env_key,
        "exists": False,
        "executable": False,
    }


@lru_cache(maxsize=32)
def resolve_cli_executable(command: str) -> str:
    return str(resolve_cli_executable_details(command).get("path") or "").strip()


class CLIAdapter(ABC):
    """
    Abstract base class for CLI tool adapters.

    Each adapter implements this interface to provide CLI-specific
    behavior for session discovery, command construction, and output parsing.
    """

    @classmethod
    @abstractmethod
    def info(cls) -> CLIInfo:
        """
        Return static information about this CLI tool.

        Returns:
            CLIInfo with id, name, description, and enabled status.
        """
        ...

    @classmethod
    @abstractmethod
    def get_home_path(cls) -> Path:
        """
        Get the home directory for this CLI tool.

        Returns:
            Path to the CLI's home directory (e.g., ~/.codex, ~/.claude).
        """
        ...

    @classmethod
    @abstractmethod
    def scan_sessions(cls, after_ts: float = 0.0) -> list[SessionInfo]:
        """
        Scan for session files modified after the given timestamp.

        Args:
            after_ts: Unix timestamp; only return sessions modified after this time.

        Returns:
            List of SessionInfo objects for discovered sessions.
        """
        ...

    @classmethod
    @abstractmethod
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
        Build the command to resume a session with a new message.

        Args:
            session_id: The session UUID to resume.
            message: The message to send to the session.
            output_path: Path where the CLI should write output.
            profile_label: Optional profile/configuration label.
            model: Optional model identifier (e.g., codex-spark).
            reasoning_effort: Optional reasoning effort (e.g., low|medium|high|extra_high).

        Returns:
            Command as a list of strings suitable for subprocess.
        """
        ...

    @classmethod
    @abstractmethod
    def build_create_command(
        cls,
        seed_prompt: str,
        output_path: Path,
        model: str = "",
        reasoning_effort: str = "",
        sandbox_mode: str = "read-only",
    ) -> list[str]:
        """
        Build the command to create a new session with a seed prompt.

        Args:
            seed_prompt: Initial prompt for the new session.
            output_path: Path where the CLI should write output.
            model: Optional model identifier used when creating the session.
            reasoning_effort: Optional reasoning effort.
            sandbox_mode: Optional sandbox mode for CLIs that support it.

        Returns:
            Command as a list of strings suitable for subprocess.
        """
        ...

    @classmethod
    @abstractmethod
    def parse_output_line(cls, line: str) -> Optional[dict[str, Any]]:
        """
        Parse a single line of CLI output.

        Args:
            line: A line of output from the CLI process.

        Returns:
            Parsed dict if the line contains structured data, None otherwise.
        """
        ...

    @classmethod
    @abstractmethod
    def get_process_signature(cls, session_id: str) -> str:
        """
        Get a signature string for finding this session's running process.

        This is used with pgrep to detect if a session's process is still alive.

        Args:
            session_id: The session UUID.

        Returns:
            A string that can be used with pgrep to find the process.
        """
        ...

    @classmethod
    def supports_model(cls) -> bool:
        """Whether this CLI supports explicit model selection on command line."""
        return False

    @classmethod
    def extract_session_id_from_name(cls, name: str) -> str:
        """
        Extract a UUID session ID from a filename or path.

        Args:
            name: A filename or path potentially containing a UUID.

        Returns:
            The extracted UUID (lowercase) or empty string if not found.
        """
        import re

        m = re.search(
            r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})(?:\.jsonl|\.json)?$",
            str(name or "").strip(),
        )
        return (m.group(1) if m else "").lower()

    @classmethod
    def is_valid_session_id(cls, session_id: str) -> bool:
        """
        Check if a string looks like a valid UUID session ID.

        Args:
            session_id: The string to validate.

        Returns:
            True if the string matches UUID format.
        """
        import re

        return bool(
            re.match(
                r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$",
                str(session_id or "").strip(),
            )
        )
