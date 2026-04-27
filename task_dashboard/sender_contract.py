# -*- coding: utf-8 -*-
"""Sender contract normalization and consistency validation helpers.

This module is intentionally lightweight and pure-function based so it can be
shared by runtime, frontend mapping tests, and offline inspectors.
"""

from __future__ import annotations

from typing import Any, Mapping

SENDER_TYPES = {"user", "agent", "system", "legacy"}


def _as_text(value: Any) -> str:
    return str(value or "").strip()


def _first_non_empty(data: Mapping[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        if key in data:
            text = _as_text(data.get(key))
            if text:
                return text
    return ""


def _mapping_from_keys(data: Mapping[str, Any], keys: tuple[str, ...]) -> Mapping[str, Any]:
    for key in keys:
        value = data.get(key)
        if isinstance(value, Mapping):
            return value
    return {}


def _nested_payload(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    nested = payload.get("run_extra_meta")
    if isinstance(nested, Mapping):
        return nested
    nested = payload.get("runExtraMeta")
    if isinstance(nested, Mapping):
        return nested
    return {}


def _infer_sender_fields(payload: Mapping[str, Any]) -> dict[str, str] | None:
    nested = _nested_payload(payload)
    sender_agent_ref = _mapping_from_keys(payload, ("sender_agent_ref", "senderAgentRef"))
    if not sender_agent_ref:
        sender_agent_ref = _mapping_from_keys(nested, ("sender_agent_ref", "senderAgentRef"))
    source_ref = _mapping_from_keys(payload, ("source_ref", "sourceRef"))
    if not source_ref:
        source_ref = _mapping_from_keys(nested, ("source_ref", "sourceRef"))
    target_ref = _mapping_from_keys(payload, ("target_ref", "targetRef"))
    if not target_ref:
        target_ref = _mapping_from_keys(nested, ("target_ref", "targetRef"))
    callback_to = _mapping_from_keys(payload, ("callback_to", "callbackTo"))
    if not callback_to:
        callback_to = _mapping_from_keys(nested, ("callback_to", "callbackTo"))

    trigger_type = (
        _first_non_empty(payload, ("trigger_type", "triggerType"))
        or _first_non_empty(nested, ("trigger_type", "triggerType"))
    ).lower()
    message_kind = (
        _first_non_empty(payload, ("message_kind", "messageKind"))
        or _first_non_empty(nested, ("message_kind", "messageKind"))
    ).lower()
    interaction_mode = (
        _first_non_empty(payload, ("interaction_mode", "interactionMode"))
        or _first_non_empty(nested, ("interaction_mode", "interactionMode"))
    ).lower()

    if message_kind in {"system_callback", "system_callback_summary", "restart_recovery_summary"} or trigger_type in {
        "callback_auto",
        "callback_auto_summary",
        "restart_recovery_summary",
    }:
        return {
            "sender_type": "system",
            "sender_id": "system",
            "sender_name": "系统",
        }

    if sender_agent_ref:
        sender_id = _first_non_empty(sender_agent_ref, ("session_id", "sessionId"))
        sender_name = _first_non_empty(sender_agent_ref, ("alias", "agent_name", "agentName"))
        if not sender_id:
            sender_id = (
                _first_non_empty(source_ref, ("session_id", "sessionId"))
                or _first_non_empty(source_ref, ("channel_name", "channelName"))
                or sender_name
            )
        if not sender_name:
            sender_name = (
                _first_non_empty(source_ref, ("channel_name", "channelName"))
                or _first_non_empty(target_ref, ("channel_name", "channelName"))
                or "Agent"
            )
        if sender_id or sender_name:
            return {
                "sender_type": "agent",
                "sender_id": sender_id,
                "sender_name": sender_name,
            }

    if message_kind == "collab_update" or interaction_mode == "task_with_receipt":
        sender_id = (
            _first_non_empty(source_ref, ("session_id", "sessionId"))
            or _first_non_empty(source_ref, ("channel_name", "channelName"))
            or _first_non_empty(target_ref, ("session_id", "sessionId"))
            or _first_non_empty(target_ref, ("channel_name", "channelName"))
        )
        sender_name = (
            _first_non_empty(payload, ("source_agent_alias", "sourceAgentAlias", "source_agent_name", "sourceAgentName"))
            or _first_non_empty(source_ref, ("channel_name", "channelName"))
            or _first_non_empty(target_ref, ("channel_name", "channelName"))
            or "Agent"
        )
        if sender_id or callback_to or target_ref:
            return {
                "sender_type": "agent",
                "sender_id": sender_id or "agent",
                "sender_name": sender_name,
            }
    return None


def normalize_sender_fields(data: Mapping[str, Any] | None) -> dict[str, str]:
    """Normalize sender fields to canonical snake_case keys.

    Compatibility input keys:
    - sender_type / senderType
    - sender_id / senderId
    - sender_name / senderName

    Normalization policy:
    - Missing or invalid `sender_type` falls back to `legacy`.
    - `user/system/legacy` auto-fill missing id/name with stable defaults.
    - `agent` keeps empty id/name (validator reports this as an issue).
    """
    payload = data or {}

    sender_type = _first_non_empty(payload, ("sender_type", "senderType")).lower()
    sender_id = _first_non_empty(payload, ("sender_id", "senderId"))
    sender_name = _first_non_empty(payload, ("sender_name", "senderName"))

    if not sender_type:
        inferred = _infer_sender_fields(payload)
        if inferred:
            sender_type = str(inferred.get("sender_type") or "").strip().lower()
            sender_id = sender_id or _as_text(inferred.get("sender_id"))
            sender_name = sender_name or _as_text(inferred.get("sender_name"))

    if sender_type not in SENDER_TYPES:
        sender_type = "legacy"

    if sender_type == "user":
        sender_id = sender_id or "user"
        sender_name = sender_name or "用户"
    elif sender_type == "system":
        sender_id = sender_id or "system"
        sender_name = sender_name or "系统"
    elif sender_type == "legacy":
        sender_id = sender_id or "legacy"
        sender_name = sender_name or "历史消息（来源未知）"

    return {
        "sender_type": sender_type,
        "sender_id": sender_id,
        "sender_name": sender_name,
    }


def validate_sender_consistency(data: Mapping[str, Any] | None) -> dict[str, Any]:
    """Validate sender fields and return a normalized result plus issues.

    Issue levels:
    - `error`: contract breaks that should be fixed.
    - `warn`: compatible but should be tracked (typically legacy fallback).
    """
    payload = data or {}
    normalized = normalize_sender_fields(payload)
    issues: list[dict[str, str]] = []

    raw_sender_type = _first_non_empty(payload, ("sender_type", "senderType")).lower()
    if raw_sender_type and raw_sender_type not in SENDER_TYPES:
        issues.append(
            {
                "code": "invalid_sender_type",
                "level": "error",
                "message": f"unsupported sender_type: {raw_sender_type}",
            }
        )

    sender_type = normalized["sender_type"]
    sender_id = normalized["sender_id"]
    sender_name = normalized["sender_name"]

    if sender_type == "agent" and not sender_id and not sender_name:
        issues.append(
            {
                "code": "agent_identity_missing",
                "level": "error",
                "message": "agent sender requires sender_id or sender_name",
            }
        )

    # Warn on legacy fallback when original sender type is missing/empty.
    if sender_type == "legacy":
        if not raw_sender_type:
            issues.append(
                {
                    "code": "sender_type_missing",
                    "level": "warn",
                    "message": "sender_type missing, fallback to legacy",
                }
            )

        # Explicitly record whether legacy came with empty identity.
        raw_sender_id = _first_non_empty(payload, ("sender_id", "senderId"))
        raw_sender_name = _first_non_empty(payload, ("sender_name", "senderName"))
        if not raw_sender_id and not raw_sender_name:
            issues.append(
                {
                    "code": "sender_identity_empty",
                    "level": "warn",
                    "message": "sender_id and sender_name both empty, using legacy defaults",
                }
            )

    return {
        "normalized": normalized,
        "issues": issues,
        "ok": not any(i["level"] == "error" for i in issues),
        "legacy": sender_type == "legacy",
    }
