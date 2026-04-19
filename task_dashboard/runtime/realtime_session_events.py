# -*- coding: utf-8 -*-

from __future__ import annotations

import hashlib
import time
from typing import Any


EVENT_VERSION = "v1"
STREAM_NAME = "active_session"


def _safe_text(value: Any, max_len: int) -> str:
    text = "" if value is None else str(value)
    if len(text) > max_len:
        return text[: max_len - 1] + "…"
    return text


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime())


def build_resume_token(session_id: str, seq: int) -> str:
    sid = _safe_text(session_id, 160).strip()
    safe_seq = max(0, int(seq or 0))
    return f"{sid}:{safe_seq}"


def parse_resume_token(token: str) -> tuple[str, int]:
    raw = _safe_text(token, 240).strip()
    if ":" not in raw:
        return "", 0
    sid, seq_raw = raw.rsplit(":", 1)
    try:
        seq = max(0, int(seq_raw or "0"))
    except Exception:
        seq = 0
    return sid.strip(), seq


def stable_projection_seq(parts: list[Any]) -> int:
    source = "|".join(_safe_text(item, 1000) for item in parts)
    digest = hashlib.sha1(source.encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def build_realtime_session_event(
    *,
    event: str,
    project_id: str,
    session_id: str,
    seq: int,
    payload: dict[str, Any] | None = None,
    delivery_mode: str = "websocket_push",
    occurred_at: str = "",
) -> dict[str, Any]:
    safe_seq = max(0, int(seq or 0))
    sid = _safe_text(session_id, 160).strip()
    return {
        "version": EVENT_VERSION,
        "stream": STREAM_NAME,
        "event": _safe_text(event, 80).strip() or "session.snapshot",
        "project_id": _safe_text(project_id, 160).strip(),
        "session_id": sid,
        "seq": safe_seq,
        "occurred_at": _safe_text(occurred_at, 80).strip() or now_iso(),
        "delivery_mode": _safe_text(delivery_mode, 80).strip() or "websocket_push",
        "resume_token": build_resume_token(sid, safe_seq),
        "payload": dict(payload or {}),
    }
