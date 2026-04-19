# -*- coding: utf-8 -*-

from __future__ import annotations

import base64
import hashlib
import json
import struct
from typing import Any
from urllib.parse import quote

from task_dashboard.runtime.realtime_session_events import (
    build_realtime_session_event,
    build_resume_token,
    now_iso,
)


_WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def _safe_text(value: Any, max_len: int) -> str:
    text = "" if value is None else str(value)
    if len(text) > max_len:
        return text[: max_len - 1] + "…"
    return text


def build_realtime_session_hint(
    *,
    project_id: str,
    session_id: str,
    last_seq: int,
    enabled: bool = True,
) -> dict[str, Any]:
    pid = _safe_text(project_id, 160).strip()
    sid = _safe_text(session_id, 160).strip()
    seq = max(0, int(last_seq or 0))
    ws_url = f"/api/ws/sessions?project_id={quote(pid)}&session_id={quote(sid)}&after_seq={seq}"
    return {
        "version": "v1",
        "enabled": bool(enabled),
        "transport": "websocket",
        "mode": "active_session_ws" if enabled else "off",
        "focused_session_only": True,
        "ws_url": ws_url,
        "resume_token": build_resume_token(sid, seq),
        "after_seq": seq,
        "fallback_http": f"/api/sessions/{quote(sid)}?project_id={quote(pid)}",
        "bootstrap_url": f"/api/sessions/{quote(sid)}/active-bootstrap?project_id={quote(pid)}",
        "history_lite_url": f"/api/sessions/{quote(sid)}/history-lite?project_id={quote(pid)}",
        "reconnect_budget_ms": 1200,
        "gateway_scope": "focused_session_only",
        "fanout_scope": "session",
        "stream_lifecycle": "snapshot_then_incremental",
        "compat_mode": "additive_only",
    }


def is_websocket_upgrade(headers: Any) -> bool:
    upgrade = _safe_text(getattr(headers, "get", lambda _k, _d=None: "")("Upgrade", ""), 80).lower()
    connection = _safe_text(getattr(headers, "get", lambda _k, _d=None: "")("Connection", ""), 160).lower()
    return upgrade == "websocket" and "upgrade" in connection


def _websocket_accept_key(key: str) -> str:
    raw = (key.strip() + _WS_GUID).encode("ascii")
    return base64.b64encode(hashlib.sha1(raw).digest()).decode("ascii")


def _websocket_text_frame(payload: str) -> bytes:
    data = payload.encode("utf-8")
    length = len(data)
    if length < 126:
        return bytes([0x81, length]) + data
    if length <= 0xFFFF:
        return bytes([0x81, 126]) + struct.pack("!H", length) + data
    return bytes([0x81, 127]) + struct.pack("!Q", length) + data


def _websocket_close_frame() -> bytes:
    return b"\x88\x00"


def write_snapshot_websocket_response(
    handler: Any,
    *,
    project_id: str,
    session_id: str,
    projection: dict[str, Any],
    after_seq: int = 0,
) -> tuple[bool, int, dict[str, Any]]:
    if not is_websocket_upgrade(handler.headers):
        return False, 200, {
            "ok": True,
            "realtime": build_realtime_session_hint(
                project_id=project_id,
                session_id=session_id,
                last_seq=int((projection or {}).get("last_seq") or after_seq or 0),
                enabled=True,
            ),
        }
    key = _safe_text(handler.headers.get("Sec-WebSocket-Key"), 160).strip()
    version = _safe_text(handler.headers.get("Sec-WebSocket-Version"), 20).strip()
    if not key or version != "13":
        return False, 400, {"error": "invalid_websocket_upgrade"}

    seq = int((projection or {}).get("last_seq") or after_seq or 0)
    event = build_realtime_session_event(
        event="session.snapshot",
        project_id=project_id,
        session_id=session_id,
        seq=seq,
        delivery_mode="websocket_push",
        occurred_at=now_iso(),
        payload={
            "projection": projection,
            "after_seq": max(0, int(after_seq or 0)),
            "gateway_scope": "focused_session_only",
        },
    )
    keepalive = build_realtime_session_event(
        event="stream.keepalive",
        project_id=project_id,
        session_id=session_id,
        seq=seq,
        delivery_mode="websocket_push",
        occurred_at=now_iso(),
        payload={"state": "snapshot_delivered"},
    )
    handler.send_response(101, "Switching Protocols")
    handler.send_header("Upgrade", "websocket")
    handler.send_header("Connection", "Upgrade")
    handler.send_header("Sec-WebSocket-Accept", _websocket_accept_key(key))
    handler.end_headers()
    handler.wfile.write(_websocket_text_frame(json.dumps(event, ensure_ascii=False, separators=(",", ":"))))
    handler.wfile.write(_websocket_text_frame(json.dumps(keepalive, ensure_ascii=False, separators=(",", ":"))))
    handler.wfile.write(_websocket_close_frame())
    handler.wfile.flush()
    return True, 101, {"ok": True, "event": "session.snapshot"}
