# -*- coding: utf-8 -*-

from __future__ import annotations

from typing import Any


CODEBUDDY_PERMISSION_MODE_DEFAULT = "default"
CODEBUDDY_PERMISSION_MODES = {
    "default",
    "bypassPermissions",
    "acceptEdits",
    "plan",
}

_CODEBUDDY_PERMISSION_MODE_ALIASES = {
    "default": "default",
    "accept_edits": "acceptEdits",
    "acceptedits": "acceptEdits",
    "accept-edits": "acceptEdits",
    "bypass_permissions": "bypassPermissions",
    "bypasspermissions": "bypassPermissions",
    "bypass-permissions": "bypassPermissions",
    "plan": "plan",
}


def normalize_codebuddy_permission_mode(value: Any) -> str:
    """Normalize CodeBuddy permission mode to a safe fixed whitelist."""
    raw = str(value or "").strip()
    if raw in CODEBUDDY_PERMISSION_MODES:
        return raw
    key = raw.lower().replace(" ", "_")
    return _CODEBUDDY_PERMISSION_MODE_ALIASES.get(key, CODEBUDDY_PERMISSION_MODE_DEFAULT)


def codebuddy_permission_mode_cli_arg(value: Any) -> str:
    mode = normalize_codebuddy_permission_mode(value)
    return "" if mode == CODEBUDDY_PERMISSION_MODE_DEFAULT else mode


def apply_codebuddy_permission_mode_to_runner_command(cmd: list[str], value: Any) -> list[str]:
    """Replace any existing runner permission flag with the normalized session value."""
    mode = codebuddy_permission_mode_cli_arg(value)
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
    if not mode:
        return out
    insert_at = len(out)
    for idx, item in enumerate(out):
        if str(item or "") in {"create", "resume"}:
            insert_at = idx
            break
    return out[:insert_at] + ["--permission-mode", mode] + out[insert_at:]
