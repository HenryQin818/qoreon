# -*- coding: utf-8 -*-
"""Busy-aware announce delivery controls.

This module keeps the P0/P1 delivery state runtime-local and additive:
busy confirmations are persisted outside run artifacts, while notify-only
merges keep a normal visible run as the delivery evidence container.
"""

from __future__ import annotations

import json
import secrets
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from task_dashboard.helpers import atomic_write_text, now_iso, parse_iso_ts, safe_text
from task_dashboard.runtime.session_display_state import WORKING_SESSION_DISPLAY_STATES


BUSY_CONFIRM_TTL_SECONDS = 600
NOTIFICATION_MERGE_MAX_ITEMS = 20
NOTIFICATION_MERGE_WINDOW_SECONDS = 30 * 60
NOTIFICATION_MERGE_KEEP_RECENT = 10

_LOCKS_GUARD = threading.Lock()
_LOCKS: dict[str, threading.Lock] = {}


def _lock_for(path: Path) -> threading.Lock:
    key = str(path)
    with _LOCKS_GUARD:
        lock = _LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _LOCKS[key] = lock
        return lock


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp-{secrets.token_hex(4)}")
    atomic_write_text(tmp, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    tmp.replace(path)


def _runtime_root_from_store(store: Any) -> Path:
    runs_dir = Path(getattr(store, "runs_dir", ".")).expanduser().resolve()
    return runs_dir.parent / ".run" / "message_delivery"


def _utc_iso(ts: float | None = None) -> str:
    value = time.time() if ts is None else float(ts)
    return datetime.fromtimestamp(value, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _as_text(value: Any, limit: int = 4000) -> str:
    return safe_text(value, limit).strip()


def _is_uuid_session(value: Any, looks_like_uuid: Callable[[str], bool] | None = None) -> bool:
    text = _as_text(value, 120)
    if not text:
        return False
    if callable(looks_like_uuid):
        try:
            return bool(looks_like_uuid(text))
        except Exception:
            return False
    return len(text) >= 8 and all(ch.isalnum() or ch == "-" for ch in text)


def _source_session_from_meta(
    run_extra_fields: dict[str, Any],
    *,
    looks_like_uuid: Callable[[str], bool] | None = None,
) -> str:
    source_ref = run_extra_fields.get("source_ref") if isinstance(run_extra_fields.get("source_ref"), dict) else {}
    sid = _as_text((source_ref or {}).get("session_id"), 120)
    return sid if _is_uuid_session(sid, looks_like_uuid) else ""


def _is_internal_immediate_path(run_extra_fields: dict[str, Any]) -> bool:
    message_kind = _as_text(run_extra_fields.get("message_kind"), 80).lower()
    trigger_type = _as_text(run_extra_fields.get("trigger_type"), 80).lower()
    if message_kind in {"system_callback", "system_callback_summary", "restart_recovery_summary"}:
        return True
    return trigger_type in {
        "callback_auto",
        "callback_auto_summary",
        "provider_auto_retry",
        "network_auto_resume",
        "restart_recovery",
        "restart_recovery_summary",
    }


def _call_runtime_state_builder(
    build_session_runtime_state_for_row: Callable[..., dict[str, Any]],
    row: dict[str, Any],
    agg: dict[str, Any],
    store: Any,
) -> dict[str, Any]:
    try:
        return build_session_runtime_state_for_row(row, agg, store=store)
    except TypeError:
        return build_session_runtime_state_for_row(row, agg)
    except Exception:
        return {}


def _elapsed_seconds(meta: dict[str, Any], snapshot_ts: float) -> int:
    raw = _as_text(meta.get("startedAt") or meta.get("createdAt"), 80)
    started = parse_iso_ts(raw) if raw else 0.0
    if started <= 0:
        return 0
    return max(0, int(snapshot_ts - started))


def build_target_busy_snapshot(
    *,
    store: Any,
    project_id: str,
    session_id: str,
    session_data: dict[str, Any] | None,
    build_project_session_runtime_index: Callable[[Any, str], dict[str, Any]],
    build_session_runtime_state_for_row: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    """Build a lightweight target busy snapshot from existing runtime views."""
    snapshot_ts = time.time()
    snapshot_at = _utc_iso(snapshot_ts)
    try:
        runtime_index = build_project_session_runtime_index(store, project_id)
    except Exception:
        runtime_index = {}
    agg = runtime_index.get(session_id) if isinstance(runtime_index, dict) else {}
    if not isinstance(agg, dict):
        agg = {}
    row = dict(session_data or {})
    row.setdefault("id", session_id)
    state = _call_runtime_state_builder(build_session_runtime_state_for_row, row, agg, store)
    if not isinstance(state, dict):
        state = {}
    display_state = _as_text(state.get("display_state"), 80).lower() or "idle"
    active_run_id = _as_text(state.get("active_run_id"), 120)
    active_meta = store.load_meta(active_run_id) if active_run_id and hasattr(store, "load_meta") else None
    active_meta = active_meta if isinstance(active_meta, dict) else {}
    preview = _as_text(active_meta.get("messagePreview") or active_meta.get("lastPreview"), 260)
    if not preview and active_run_id and hasattr(store, "read_msg"):
        try:
            preview = _as_text(store.read_msg(active_run_id, limit_chars=800), 260)
        except Exception:
            preview = ""
    snapshot: dict[str, Any] = {
        "target_session_id": session_id,
        "display_state": display_state,
        "active_run_id": active_run_id,
        "queued_run_id": _as_text(state.get("queued_run_id"), 120),
        "queue_depth": max(0, int(state.get("queue_depth") or 0)),
        "snapshot_at": snapshot_at,
        "updated_at": _as_text(state.get("updated_at"), 80),
    }
    if active_meta:
        source_ref = active_meta.get("source_ref") if isinstance(active_meta.get("source_ref"), dict) else {}
        snapshot.update(
            {
                "active_sender_name": _as_text(active_meta.get("sender_name"), 160),
                "active_sender_type": _as_text(active_meta.get("sender_type"), 80),
                "active_source_channel": _as_text((source_ref or {}).get("channel_name"), 240),
                "active_source_session_id": _as_text((source_ref or {}).get("session_id"), 120),
                "active_elapsed_seconds": _elapsed_seconds(active_meta, snapshot_ts),
                "active_message_preview": preview,
            }
        )
    if display_state == "external_busy":
        snapshot["external_busy_reason"] = _as_text(state.get("external_busy_reason"), 160)
    return snapshot


class MessageDeliveryRuntime:
    """Runtime-local registry for busy confirmations and notify merge containers."""

    def __init__(self, runtime_root: Path | str) -> None:
        self.runtime_root = Path(runtime_root).expanduser().resolve()
        self.confirm_path = self.runtime_root / "busy_confirmations.json"

    @classmethod
    def for_store(cls, store: Any) -> "MessageDeliveryRuntime":
        return cls(_runtime_root_from_store(store))

    def _confirmation_key(self, sender_session: str, target_session: str) -> str:
        return f"{sender_session}::{target_session}"

    def evaluate_busy_gate(
        self,
        *,
        store: Any,
        project_id: str,
        target_session_id: str,
        session_data: dict[str, Any] | None,
        run_extra_fields: dict[str, Any],
        build_project_session_runtime_index: Callable[[Any, str], dict[str, Any]],
        build_session_runtime_state_for_row: Callable[..., dict[str, Any]],
        looks_like_uuid: Callable[[str], bool] | None = None,
        ttl_seconds: int = BUSY_CONFIRM_TTL_SECONDS,
    ) -> dict[str, Any]:
        mode = _as_text(run_extra_fields.get("interaction_mode"), 80).lower()
        if mode not in {"task_with_receipt", "dialog_now"}:
            return {"action": "pass", "reason": "interaction_mode_not_gated"}
        if _is_internal_immediate_path(run_extra_fields):
            return {"action": "pass", "reason": "internal_immediate_path"}

        snapshot = build_target_busy_snapshot(
            store=store,
            project_id=project_id,
            session_id=target_session_id,
            session_data=session_data,
            build_project_session_runtime_index=build_project_session_runtime_index,
            build_session_runtime_state_for_row=build_session_runtime_state_for_row,
        )
        if _as_text(snapshot.get("display_state"), 80).lower() not in WORKING_SESSION_DISPLAY_STATES:
            return {"action": "pass", "reason": "target_idle", "target_busy": snapshot}

        sender_session = _source_session_from_meta(run_extra_fields, looks_like_uuid=looks_like_uuid)
        now_ts = time.time()
        ttl = max(1, int(ttl_seconds or BUSY_CONFIRM_TTL_SECONDS))
        if not sender_session:
            return {
                "action": "blocked",
                "target_busy": snapshot,
                "pending_confirm_available": False,
                "blocking_error": {
                    "code": "target_busy",
                    "message": "目标 Agent 正忙；本次未携带真实 source_ref.session_id，无法建立确认窗。",
                    "next_action": "请补齐真实 source_ref.session_id 后重发；缺失时再次发送仍只会回弹，不会入队。",
                },
            }

        key = self._confirmation_key(sender_session, target_session_id)
        with _lock_for(self.confirm_path):
            state = _read_json(self.confirm_path)
            pending = state.get("pending") if isinstance(state.get("pending"), dict) else {}
            cleaned: dict[str, Any] = {}
            for existing_key, row in pending.items():
                if not isinstance(row, dict):
                    continue
                if float(row.get("expires_at_ts") or 0.0) > now_ts:
                    cleaned[str(existing_key)] = row
            existing = cleaned.get(key)
            if isinstance(existing, dict) and float(existing.get("expires_at_ts") or 0.0) > now_ts:
                cleaned.pop(key, None)
                _write_json(
                    self.confirm_path,
                    {
                        "schema_version": "message_delivery_busy_confirm.v1",
                        "updated_at": _utc_iso(now_ts),
                        "pending": cleaned,
                    },
                )
                return {
                    "action": "confirmed",
                    "busy_confirm": {
                        "confirmed": True,
                        "key": {"sender_session": sender_session, "target_session": target_session_id},
                        "confirmed_at": _utc_iso(now_ts),
                    },
                    "target_busy": snapshot,
                }
            expires_ts = now_ts + ttl
            cleaned[key] = {
                "sender_session": sender_session,
                "target_session": target_session_id,
                "project_id": project_id,
                "created_at": _utc_iso(now_ts),
                "created_at_ts": now_ts,
                "expires_at": _utc_iso(expires_ts),
                "expires_at_ts": expires_ts,
                "target_busy": snapshot,
            }
            _write_json(
                self.confirm_path,
                {
                    "schema_version": "message_delivery_busy_confirm.v1",
                    "updated_at": _utc_iso(now_ts),
                    "pending": cleaned,
                },
            )
        return {
            "action": "blocked",
            "target_busy": snapshot,
            "pending_confirm_available": True,
            "busy_confirm": {
                "key": {"sender_session": sender_session, "target_session": target_session_id},
                "ttl_seconds": ttl,
                "expires_at": _utc_iso(expires_ts),
            },
            "blocking_error": {
                "code": "target_busy",
                "message": "目标 Agent 正忙；确需协助请在 TTL 内再发一次。",
                "next_action": f"确需协助，请在 {ttl} 秒内由同一 source_ref.session_id 向同一目标 session 再发一次，系统将确认入队。",
            },
        }

    def _target_lock_path(self, target_session_id: str) -> Path:
        safe = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in target_session_id) or "unknown"
        return self.runtime_root / "notification_merge" / f"{safe}.lock"

    def _notification_item(
        self,
        *,
        message: str,
        sender_fields: dict[str, Any],
        run_extra_fields: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "item_id": "ntf_" + secrets.token_hex(6),
            "sent_at": now_iso(),
            "sender_type": _as_text(sender_fields.get("sender_type"), 80),
            "sender_id": _as_text(sender_fields.get("sender_id"), 160),
            "sender_name": _as_text(sender_fields.get("sender_name"), 200),
            "source_ref": run_extra_fields.get("source_ref") if isinstance(run_extra_fields.get("source_ref"), dict) else {},
            "client_message_id": _as_text(run_extra_fields.get("client_message_id"), 160),
            "message": _as_text(message, 20_000),
        }

    def _compose_notification_message(self, items: list[dict[str, Any]], folded_count: int) -> str:
        lines = [
            "[通知合并容器]",
            f"合并通知数: {len(items)}",
        ]
        if folded_count:
            lines.append(f"已折叠较早通知: {folded_count} 条")
        lines.append("")
        for index, item in enumerate(items, 1):
            source_ref = item.get("source_ref") if isinstance(item.get("source_ref"), dict) else {}
            source_channel = _as_text((source_ref or {}).get("channel_name"), 240)
            sender = _as_text(item.get("sender_name"), 200) or _as_text(item.get("sender_id"), 160) or "未知发送方"
            lines.extend(
                [
                    f"## 通知 {index}",
                    f"- 发送方: {sender}",
                    f"- 来源通道: {source_channel or '未提供'}",
                    f"- 发送时间: {_as_text(item.get('sent_at'), 80)}",
                    "",
                    _as_text(item.get("message"), 20_000),
                    "",
                ]
            )
        return "\n".join(lines).strip() + "\n"

    def _find_open_notification_container(self, store: Any, project_id: str, target_session_id: str) -> dict[str, Any] | None:
        try:
            runs = store.list_runs(project_id=project_id, session_id=target_session_id, limit=80, include_payload=False)
        except Exception:
            runs = []
        for meta in runs:
            if not isinstance(meta, dict):
                continue
            merge = meta.get("notification_merge") if isinstance(meta.get("notification_merge"), dict) else {}
            if not bool((merge or {}).get("container")):
                continue
            if _as_text(meta.get("status"), 80).lower() not in {"queued", "retry_waiting"}:
                continue
            if bool(meta.get("hidden")):
                continue
            return meta
        return None

    def _fold_items_if_needed(self, meta: dict[str, Any], items: list[dict[str, Any]], folded_count: int) -> tuple[list[dict[str, Any]], int]:
        created_ts = parse_iso_ts(meta.get("createdAt"))
        age_s = max(0.0, time.time() - created_ts) if created_ts > 0 else 0.0
        if len(items) <= NOTIFICATION_MERGE_MAX_ITEMS and age_s <= NOTIFICATION_MERGE_WINDOW_SECONDS:
            return items, folded_count
        if len(items) <= NOTIFICATION_MERGE_KEEP_RECENT:
            return items, folded_count
        drop_count = len(items) - NOTIFICATION_MERGE_KEEP_RECENT
        return items[-NOTIFICATION_MERGE_KEEP_RECENT:], folded_count + drop_count

    def merge_notify_only(
        self,
        *,
        store: Any,
        project_id: str,
        channel_name: str,
        target_session_id: str,
        message: str,
        profile_label: str,
        model: str,
        cli_type: str,
        attachments: list[dict[str, Any]] | None,
        sender_fields: dict[str, Any],
        run_extra_fields: dict[str, Any],
        reasoning_effort: str,
        create_run: Callable[[str, dict[str, Any]], dict[str, Any]],
        enqueue_run: Callable[[dict[str, Any]], None],
    ) -> dict[str, Any]:
        item = self._notification_item(message=message, sender_fields=sender_fields, run_extra_fields=run_extra_fields)
        client_message_id = _as_text(item.get("client_message_id"), 160)
        lock_path = self._target_lock_path(target_session_id)
        with _lock_for(lock_path):
            existing = self._find_open_notification_container(store, project_id, target_session_id)
            if existing:
                run_id = _as_text(existing.get("id"), 120)
                meta = dict(store.load_meta(run_id) or existing)
                merge = meta.get("notification_merge") if isinstance(meta.get("notification_merge"), dict) else {}
                items = list(merge.get("items") or [])
                client_ids = [str(x or "") for x in (merge.get("client_message_ids") or []) if str(x or "")]
                if client_message_id and client_message_id in set(client_ids):
                    return {
                        "run": meta,
                        "notification_merge": {
                            "merged": True,
                            "action": "idempotent_replay",
                            "container_run_id": run_id,
                            "item_count": len(items),
                            "folded_count": int(merge.get("folded_count") or 0),
                        },
                    }
                items.append(item)
                folded_count = int(merge.get("folded_count") or 0)
                items, folded_count = self._fold_items_if_needed(meta, items, folded_count)
                if client_message_id:
                    client_ids.append(client_message_id)
                merge.update(
                    {
                        "container": True,
                        "action": "appended",
                        "item_count": len(items),
                        "folded_count": folded_count,
                        "items": items,
                        "client_message_ids": client_ids[-200:],
                        "updated_at": now_iso(),
                    }
                )
                meta["notification_merge"] = merge
                store.write_msg(run_id, self._compose_notification_message(items, folded_count))
                store.save_meta(run_id, meta)
                return {
                    "run": meta,
                    "notification_merge": {
                        "merged": True,
                        "action": "appended",
                        "container_run_id": run_id,
                        "item_count": len(items),
                        "folded_count": folded_count,
                    },
                }

            merge_meta = {
                "container": True,
                "action": "created",
                "item_count": 1,
                "folded_count": 0,
                "items": [item],
                "client_message_ids": [client_message_id] if client_message_id else [],
                "created_at": now_iso(),
                "updated_at": now_iso(),
                "target_session_id": target_session_id,
            }
            container_message = self._compose_notification_message([item], 0)
            run = create_run(container_message, run_extra_fields)
            run_id = _as_text(run.get("id"), 120)
            meta = dict(store.load_meta(run_id) or run)
            meta["notification_merge"] = merge_meta
            store.write_msg(run_id, container_message)
            store.save_meta(run_id, meta)
            enqueue_run(meta)
            return {
                "run": meta,
                "notification_merge": {
                    "merged": True,
                    "action": "created",
                    "container_run_id": run_id,
                    "item_count": 1,
                    "folded_count": 0,
                },
            }
