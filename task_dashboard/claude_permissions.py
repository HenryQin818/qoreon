# -*- coding: utf-8 -*-

from __future__ import annotations

from typing import Any


CLAUDE_PERMISSION_MODE_DEFAULT = "bypassPermissions"
CLAUDE_PERMISSION_MODES = {
    "bypassPermissions",
    "default",
    "acceptEdits",
    "plan",
}

_CLAUDE_PERMISSION_MODE_ALIASES = {
    "accept_edits": "acceptEdits",
    "acceptedits": "acceptEdits",
    "accept-edits": "acceptEdits",
    "bypass_permissions": "bypassPermissions",
    "bypasspermissions": "bypassPermissions",
    "bypass-permissions": "bypassPermissions",
    "dangerouslyskippermissions": "bypassPermissions",
    "dangerously_skip_permissions": "bypassPermissions",
    "dangerously-skip-permissions": "bypassPermissions",
    "--dangerously-skip-permissions": "bypassPermissions",
    "full": "bypassPermissions",
    "default": "default",
    "plan": "plan",
}


def normalize_claude_permission_mode(value: Any) -> str:
    """Normalize Claude permission mode to a fixed safe whitelist.

    Empty or invalid values keep the existing ClaudeCode maximum-authorization
    default by resolving to `bypassPermissions`.
    """
    raw = str(value or "").strip()
    if raw in CLAUDE_PERMISSION_MODES:
        return raw
    key = raw.lower().replace("-", "_").replace(" ", "_").strip("_")
    return _CLAUDE_PERMISSION_MODE_ALIASES.get(key, CLAUDE_PERMISSION_MODE_DEFAULT)


def claude_permission_mode_cli_arg(value: Any) -> str:
    return normalize_claude_permission_mode(value)


def apply_claude_permission_mode_to_runner_command(cmd: list[str], value: Any) -> list[str]:
    """Replace any existing runner permission flag with the normalized value."""
    mode = claude_permission_mode_cli_arg(value)
    out: list[str] = []
    skip_next = False
    for item in list(cmd or []):
        if skip_next:
            skip_next = False
            continue
        if str(item or "") == "--permission-mode":
            skip_next = True
            continue
        out.append(item)
    insert_at = len(out)
    for idx, item in enumerate(out):
        if str(item or "") in {"create", "resume"}:
            insert_at = idx
            break
    return out[:insert_at] + ["--permission-mode", mode] + out[insert_at:]
