# -*- coding: utf-8 -*-

from __future__ import annotations

import re
from typing import Any


_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_OPENCODE_SESSION_RE = re.compile(r"^ses_[A-Za-z0-9_-]{6,}$")
_SESSION_LABEL_RE = re.compile(r"^(?:会话|Session)\s*[0-9a-fA-F-]{4,}$", re.IGNORECASE)
_PSEUDO_NAME_RE = re.compile(r"^(?:agent|user|session|tmp|temp|random)[_-]?[0-9a-fA-F]{4,}$", re.IGNORECASE)
_MISSING_NAME_VALUES = {"", "-", "unknown", "unnamed", "none", "null", "n/a", "na", "未命名", "未命名会话"}
_DISPLAY_SESSION_FALLBACK_SOURCES = {
    "session_id",
    "legacy",
    "explicit_sid_fallback",
    "display_name_session_fallback",
    "unknown",
}


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _first_text(*values: Any) -> str:
    for value in values:
        text = _safe_text(value)
        if text:
            return text
    return ""


def _compact_id(value: str) -> str:
    return re.sub(r"[^0-9a-fA-F]", "", str(value or "")).lower()


def _session_short_id_issue(value: str, session_id: str) -> str:
    text = _safe_text(value)
    if not text:
        return ""
    sid = _safe_text(session_id)
    if not sid:
        return ""
    compact_sid = _compact_id(sid)
    compact_text = _compact_id(text)
    if len(compact_sid) < 8 or len(compact_text) < 4:
        return ""
    if compact_text == compact_sid:
        return "polluted_session_id"
    if compact_text in compact_sid:
        return "polluted_short_id"
    return ""


def detect_agent_display_name_issue(value: Any, *, session_id: str = "") -> str:
    text = _safe_text(value)
    lowered = text.lower()
    if lowered in _MISSING_NAME_VALUES:
        return "polluted_random_name" if text else ""
    if _UUID_RE.match(text) or _OPENCODE_SESSION_RE.match(text):
        return "polluted_session_id"
    if _SESSION_LABEL_RE.match(text):
        return "polluted_short_id"
    short_issue = _session_short_id_issue(text, session_id)
    if short_issue:
        return short_issue
    if _PSEUDO_NAME_RE.match(text):
        return "polluted_random_name"
    return ""


def _identity_source_candidates(row: dict[str, Any]) -> list[tuple[str, str]]:
    agent_registry = row.get("agent_registry") if isinstance(row.get("agent_registry"), dict) else {}
    owner_ref = row.get("owner_ref") if isinstance(row.get("owner_ref"), dict) else {}
    sender_ref = row.get("sender_agent_ref") if isinstance(row.get("sender_agent_ref"), dict) else {}
    return [
        ("alias", _first_text(row.get("alias"))),
        ("agent_name", _first_text(row.get("agent_name"), row.get("agentName"))),
        (
            "agent_registry",
            _first_text(
                agent_registry.get("alias"),
                agent_registry.get("agent_name"),
                agent_registry.get("agentName"),
                agent_registry.get("name"),
            ),
        ),
        ("owner_ref", _first_text(owner_ref.get("alias"), owner_ref.get("agent_name"), owner_ref.get("agentName"))),
        (
            "sender_agent_ref",
            _first_text(sender_ref.get("alias"), sender_ref.get("agent_name"), sender_ref.get("agentName")),
        ),
    ]


def build_agent_display_fields(row: dict[str, Any]) -> dict[str, str]:
    item = row if isinstance(row, dict) else {}
    session_id = _first_text(item.get("id"), item.get("session_id"), item.get("sessionId"))
    first_pollution = ""
    identity_seen = False
    for source, value in _identity_source_candidates(item):
        if not value:
            continue
        identity_seen = True
        issue = detect_agent_display_name_issue(value, session_id=session_id)
        if issue:
            first_pollution = first_pollution or issue
            continue
        return {
            "agent_display_name": value,
            "agent_display_name_source": source,
            "agent_name_state": "resolved",
            "agent_display_issue": "none",
        }

    display_name = _first_text(item.get("display_name"), item.get("displayName"))
    display_source = _first_text(item.get("display_name_source"), item.get("displayNameSource")).lower()
    display_issue = detect_agent_display_name_issue(display_name, session_id=session_id)
    if display_issue:
        first_pollution = first_pollution or display_issue
    elif display_source in _DISPLAY_SESSION_FALLBACK_SOURCES and display_name:
        first_pollution = first_pollution or "legacy_session_display_fallback"

    if first_pollution:
        return {
            "agent_display_name": "",
            "agent_display_name_source": "",
            "agent_name_state": "polluted",
            "agent_display_issue": first_pollution,
        }
    if identity_seen:
        return {
            "agent_display_name": "",
            "agent_display_name_source": "",
            "agent_name_state": "name_missing",
            "agent_display_issue": "missing_name",
        }
    return {
        "agent_display_name": "",
        "agent_display_name_source": "",
        "agent_name_state": "identity_unresolved",
        "agent_display_issue": "missing_identity_source",
    }


def attach_agent_display_fields(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row if isinstance(row, dict) else {})
    item.update(build_agent_display_fields(item))
    return item


def apply_agent_display_fields(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [attach_agent_display_fields(row) for row in rows if isinstance(row, dict)]


def build_agent_identity_audit(rows: list[dict[str, Any]], *, project_id: str = "") -> dict[str, Any]:
    manual_backfill_required: list[dict[str, Any]] = []
    for raw in rows:
        row = raw if isinstance(raw, dict) else {}
        cli_type = _safe_text(row.get("cli_type") or row.get("cliType")).lower()
        if cli_type in {"", "codex"}:
            continue
        display_fields = build_agent_display_fields(row)
        state = display_fields.get("agent_name_state") or ""
        issue = display_fields.get("agent_display_issue") or ""
        if state not in {"identity_unresolved", "name_missing"}:
            continue
        if issue not in {"missing_identity_source", "missing_name"}:
            continue
        manual_backfill_required.append(
            {
                "project_id": _first_text(row.get("project_id"), project_id),
                "session_id": _first_text(row.get("id"), row.get("session_id"), row.get("sessionId")),
                "cli_type": cli_type,
                "channel_name": _first_text(row.get("channel_name"), row.get("channelName")),
                "current_alias": _first_text(row.get("alias")),
                "current_agent_name": _first_text(row.get("agent_name"), row.get("agentName")),
                "proposed_alias": "",
                "proposed_agent_name": "",
                "backfill_source": "",
                "source_evidence_path": "",
                "action": "needs_owner_confirmation",
                "audit_status": "pending",
            }
        )
    return {
        "version": "v1",
        "manual_backfill_required_count": len(manual_backfill_required),
        "manual_backfill_required": manual_backfill_required,
    }
