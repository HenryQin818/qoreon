#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
CLI Adapter registry for multi-CLI support.

This module provides a registry for CLI adapters and utilities to
lookup adapters by CLI type.
"""

from __future__ import annotations

from typing import Optional, Type

from .base import CLIAdapter, CLIInfo, SessionInfo

# Registry of all available adapters, keyed by CLI type ID.
_ADAPTERS: dict[str, Type[CLIAdapter]] = {}


def register_adapter(adapter_cls: Type[CLIAdapter]) -> Type[CLIAdapter]:
    """
    Decorator to register a CLI adapter class.

    Usage:
        @register_adapter
        class CodexAdapter(CLIAdapter):
            ...

    Args:
        adapter_cls: The adapter class to register.

    Returns:
        The same adapter class (for decorator chaining).
    """
    info = adapter_cls.info()
    _ADAPTERS[info.id] = adapter_cls
    return adapter_cls


def get_adapter(cli_type: str) -> Optional[Type[CLIAdapter]]:
    """
    Get an adapter class by CLI type.

    Args:
        cli_type: The CLI type ID (e.g., "codex", "claude", "opencode", "gemini").

    Returns:
        The adapter class, or None if not found.
    """
    return _ADAPTERS.get(cli_type)


def get_adapter_or_error(cli_type: str) -> Type[CLIAdapter]:
    """
    Get an adapter class by CLI type, raising an error if not found.

    Args:
        cli_type: The CLI type ID.

    Returns:
        The adapter class.

    Raises:
        ValueError: If no adapter is registered for the given type.
    """
    adapter = get_adapter(cli_type)
    if adapter is None:
        available = ", ".join(sorted(_ADAPTERS.keys())) or "none"
        raise ValueError(f"Unknown CLI type: {cli_type!r}. Available: {available}")
    return adapter


def list_cli_types() -> list[CLIInfo]:
    """
    List all registered CLI types.

    Returns:
        List of CLIInfo objects for all registered adapters.
    """
    return [cls.info() for cls in _ADAPTERS.values()]


def list_enabled_cli_types() -> list[CLIInfo]:
    """
    List all enabled CLI types.

    Returns:
        List of CLIInfo objects for enabled adapters only.
    """
    return [cls.info() for cls in _ADAPTERS.values() if cls.info().enabled]


# Import adapters to trigger registration.
# These imports must come after register_adapter is defined.
from .codex_adapter import CodexAdapter
from .claude_adapter import ClaudeAdapter
from .opencode_adapter import OpenCodeAdapter
from .gemini_adapter import GeminiAdapter
from .trae_adapter import TraeAdapter

# Re-export for convenience.
__all__ = [
    "CLIAdapter",
    "CLIInfo",
    "SessionInfo",
    "register_adapter",
    "get_adapter",
    "get_adapter_or_error",
    "list_cli_types",
    "list_enabled_cli_types",
    "CodexAdapter",
    "ClaudeAdapter",
    "OpenCodeAdapter",
    "GeminiAdapter",
    "TraeAdapter",
]
