# -*- coding: utf-8 -*-

"""ClaudeCode model normalization for CCB runtime paths."""

from __future__ import annotations

from typing import Any

DEFAULT_CLAUDE_MODEL = "claude-opus-4-8"

SUPPORTED_CLAUDE_MODELS = {
    "claude-fable-5",
    "claude-opus-4-8",
    "claude-sonnet-4-6",
    "claude-haiku-4-5",
}

_CLAUDE_MODEL_ALIASES = {
    "default": DEFAULT_CLAUDE_MODEL,
    "best": DEFAULT_CLAUDE_MODEL,
    "fable": "claude-fable-5",
    "fable5": "claude-fable-5",
    "fable-5": "claude-fable-5",
    "fable_5": "claude-fable-5",
    "claude-fable": "claude-fable-5",
    "claude-fable5": "claude-fable-5",
    "opus": DEFAULT_CLAUDE_MODEL,
    "opusplan": DEFAULT_CLAUDE_MODEL,
    "opus-plan": DEFAULT_CLAUDE_MODEL,
    "opus_plan": DEFAULT_CLAUDE_MODEL,
    "claude-opus": DEFAULT_CLAUDE_MODEL,
    "claude-opus-4-20250514": DEFAULT_CLAUDE_MODEL,
    "sonnet": "claude-sonnet-4-6",
    "claude-sonnet": "claude-sonnet-4-6",
    "claude-sonnet-4-20250514": "claude-sonnet-4-6",
    "haiku": "claude-haiku-4-5",
    "claude-haiku": "claude-haiku-4-5",
}


def normalize_claude_model(value: Any) -> str:
    """Return a safe current ClaudeCode model id.

    The runtime intentionally projects aliases and deprecated model ids to the
    current full model ids so accidental project/channel names never reach
    `claude --model`.
    """
    text = str(value or "").strip()
    if not text:
        return DEFAULT_CLAUDE_MODEL
    normalized = text.lower().replace(" ", "-")
    if normalized in SUPPORTED_CLAUDE_MODELS:
        return normalized
    return _CLAUDE_MODEL_ALIASES.get(normalized, DEFAULT_CLAUDE_MODEL)
