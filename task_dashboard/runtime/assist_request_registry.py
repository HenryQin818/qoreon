"""Assist-request runtime registry (extracted from server.py)."""
from __future__ import annotations

import json
import os
import secrets
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional

from task_dashboard.helpers import (


    safe_text as _safe_text,
    now_iso as _now_iso,
    looks_like_uuid as _looks_like_uuid,
    read_json_file as _read_json_file,
    write_json_file as _write_json_file,
    coerce_bool as _coerce_bool,
    coerce_int as _coerce_int,
    parse_iso_ts as _parse_iso_ts,
    atomic_write_text as _atomic_write_text,
    read_json_file_safe as _read_json_file_safe,
)


# ---------------------------------------------------------------------------
# Lazy accessor for server-level functions that remain in server.py.
# Using late import avoids circular-import issues.
# ---------------------------------------------------------------------------


__all__ = [
    "AssistRequestRuntimeRegistry",
    "_assist_request_close_message_text",
    "_assist_request_item_path",
    "_assist_request_message_text",
    "_assist_request_new_id",
    "_assist_request_normalize_context_refs",
    "_assist_request_normalize_missing_dimensions",
    "_assist_request_normalize_status",
    "_assist_request_project_root",
    "_assist_request_state_root",
    "_assist_request_support_level_from_score",
    "_assist_request_threshold_triggered",
    # Route handlers
    "list_assist_requests_response",
    "get_assist_request_response",
    "create_assist_request_response",
    "auto_trigger_assist_request_response",
    "close_assist_request_response",
    "reply_assist_request_response",
]


def __getattr__(name):
    """Lazy resolution of names still defined in server.py (avoids circular imports)."""
    import server
    try:
        return getattr(server, name)
    except AttributeError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _parse_rfc3339_ts(value: Any):
    return __getattr__("_parse_rfc3339_ts")(value)


def _resolve_task_project_channel(task_path: str, *, project_hint: str = ""):
    return __getattr__("_resolve_task_project_channel")(task_path, project_hint=project_hint)


def _resolve_primary_target_by_channel(project_id: str, channel_name: str):
    return __getattr__("_resolve_primary_target_by_channel")(project_id, channel_name)


def _resolve_master_control_target(project_id: str):
    return __getattr__("_resolve_master_control_target")(project_id)


def _resolve_cli_type_for_session(session_store, project_id: str, session_id: str, fallback: str = "codex") -> str:
    return __getattr__("_resolve_cli_type_for_session")(session_store, project_id, session_id, fallback)


def _enqueue_run_for_dispatch(
    store,
    run_id: str,
    session_id: str,
    cli_type: str,
    scheduler,
) -> None:
    __getattr__("_enqueue_run_for_dispatch")(store, run_id, session_id, cli_type, scheduler)


# ---------------------------------------------------------------------------
# Helper functions (standalone – only depend on task_dashboard.helpers)
# ---------------------------------------------------------------------------

def _assist_request_state_root(store: "RunStore") -> Path:
    return store.runs_dir.parent / ".run" / "assist_requests"


def _assist_request_project_root(store: "RunStore", project_id: str) -> Path:
    pid = str(project_id or "").strip()
    return _assist_request_state_root(store) / pid


def _assist_request_item_path(store: "RunStore", project_id: str, request_id: str) -> Path:
    rid = str(request_id or "").strip()
    return _assist_request_project_root(store, project_id) / f"{rid}.json"


def _assist_request_new_id() -> str:
    return "asr_" + time.strftime("%Y%m%d_%H%M%S", time.localtime()) + "_" + secrets.token_hex(3)


def _assist_request_normalize_status(value: Any, default: str = "open") -> str:
    allowed = {
        "open",
        "pending_reply",
        "acknowledged",
        "in_progress",
        "replied",
        "resolved",
        "expired",
        "closed",
        "canceled",
        "error",
    }
    txt = _safe_text(value, 40).strip().lower()
    if txt in allowed:
        return txt
    return default


def _assist_request_normalize_context_refs(value: Any) -> list[str]:
    out: list[str] = []
    if not isinstance(value, list):
        return out
    for item in value:
        txt = _safe_text(item, 1200).strip()
        if txt:
            out.append(txt)
    return out[:40]


def _assist_request_normalize_missing_dimensions(value: Any) -> list[str]:
    allowed = {"facts", "evidence", "impact", "owner", "deadline"}
    out: list[str] = []
    if not isinstance(value, list):
        return out
    for item in value:
        txt = _safe_text(item, 40).strip().lower()
        if txt in allowed and txt not in out:
            out.append(txt)
    return out[:10]


def _assist_request_support_level_from_score(score: int) -> str:
    n = max(0, min(int(score), 100))
    if n >= 80:
        return "sufficient"
    if n >= 60:
        return "watch"
    return "insufficient"


def _assist_request_threshold_triggered(
    *,
    support_score: int,
    missing_dimensions: list[str],
    evidence_count: int,
    required_evidence_count: int,
) -> bool:
    if int(support_score) < 60:
        return True
    if "facts" in missing_dimensions or "evidence" in missing_dimensions:
        return True
    if int(evidence_count) < max(0, int(required_evidence_count)):
        return True
    if len(missing_dimensions) >= 2:
        return True
    return False


def _assist_request_close_message_text(
    item: dict[str, Any],
    *,
    close_action: str,
    close_by: str,
    resolution_summary: str,
) -> str:
    request_id = str(item.get("assist_request_id") or "").strip()
    source_channel = str(item.get("source_channel") or "").strip()
    target_channel = str(item.get("target_channel") or "").strip()
    task_path = str(item.get("task_path") or "").strip()
    lines = [
        "[证据补全协助单收口]",
        f"- request_id: {request_id or 'unknown'}",
        f"- close_action: {close_action}",
        f"- close_by: {close_by}",
        f"- source_channel: {source_channel or 'unknown'}",
        f"- target_channel: {target_channel or 'unknown'}",
    ]
    if task_path:
        lines.append(f"- task_path: {task_path}")
    lines.append("")
    lines.append("收口结论：")
    lines.append(resolution_summary)
    return "\n".join(lines)


def _assist_request_message_text(item: dict[str, Any], reply: str, reply_by: str) -> str:
    request_id = str(item.get("assist_request_id") or "").strip()
    source_channel = str(item.get("source_channel") or "").strip()
    target_channel = str(item.get("target_channel") or "").strip()
    task_path = str(item.get("task_path") or "").strip()
    question = str(item.get("question") or "").strip()
    lines = [
        "[请求协助回复]",
        f"- request_id: {request_id or 'unknown'}",
        f"- source_channel: {source_channel or 'unknown'}",
        f"- target_channel: {target_channel or 'unknown'}",
        f"- reply_by: {reply_by}",
    ]
    if task_path:
        lines.append(f"- task_path: {task_path}")
    if question:
        lines.append(f"- question: {question}")
    lines.append("")
    lines.append("回复内容：")
    lines.append(reply)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# AssistRequestRuntimeRegistry
# ---------------------------------------------------------------------------

class AssistRequestRuntimeRegistry:
    """
    Runtime for assist request object V1:
    - create
    - list/query
    - reply (default writeback to master channel primary session)
    """

    def __init__(self, *, store: "RunStore", session_store: "SessionStore") -> None:
        self.store = store
        self.session_store = session_store
        self._scheduler: Optional["RunScheduler"] = None
        self._lock = threading.Lock()

    def set_scheduler(self, scheduler: Optional["RunScheduler"]) -> None:
        self._scheduler = scheduler

    def _resolve_source_channel_with_fallback(
        self,
        *,
        project_id: str,
        task_path: str,
        source_channel: str,
    ) -> str:
        explicit = _safe_text(source_channel, 200).strip()
        if explicit:
            return explicit
        _, inferred_channel, _ = _resolve_task_project_channel(task_path, project_hint=project_id)
        return _safe_text(inferred_channel, 200).strip()

    def _normalize_item_locked(self, item: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        out = dict(item)
        changed = False

        def _ensure(key: str, value: Any) -> None:
            nonlocal changed
            if key not in out:
                out[key] = value
                changed = True

        _ensure("trigger_reason", "")
        _ensure("decision_required", False)
        _ensure("missing_dimensions", [])
        _ensure("support_score", 0)
        _ensure("support_level", _assist_request_support_level_from_score(int(out.get("support_score") or 0)))
        _ensure("threshold_triggered", False)
        _ensure("evidence_count", 0)
        _ensure("required_evidence_count", 2)
        _ensure("help_kind", "")
        _ensure("close_action", "")
        _ensure("close_by", "")
        _ensure("resolution_summary", "")
        _ensure("resolved_at", "")
        _ensure("close_writeback_run_id", "")
        _ensure("close_note", "")
        _ensure("writeback_target", {})
        _ensure("close_writeback_target", {})
        _ensure("writeback_run_id", "")
        _ensure("context_refs", [])
        _ensure("error", "")
        inferred_source = self._resolve_source_channel_with_fallback(
            project_id=str(out.get("project_id") or "").strip(),
            task_path=str(out.get("task_path") or "").strip(),
            source_channel=str(out.get("source_channel") or "").strip(),
        )
        if inferred_source and inferred_source != str(out.get("source_channel") or "").strip():
            out["source_channel"] = inferred_source
            changed = True
        return out, changed

    def _is_open_status(self, status: str) -> bool:
        st = _assist_request_normalize_status(status, "open")
        return st in {"open", "pending_reply", "acknowledged", "in_progress", "replied"}

    def _load_item_locked(self, project_id: str, request_id: str) -> Optional[dict[str, Any]]:
        path = _assist_request_item_path(self.store, project_id, request_id)
        raw = _read_json_file(path)
        if not raw:
            return None
        if str(raw.get("project_id") or "").strip() != str(project_id or "").strip():
            return None
        if str(raw.get("assist_request_id") or "").strip() != str(request_id or "").strip():
            return None
        row, changed = self._normalize_item_locked(raw)
        if changed:
            self._save_item_locked(row)
        return row

    def _save_item_locked(self, item: dict[str, Any]) -> dict[str, Any]:
        item["updated_at"] = _now_iso()
        pid = str(item.get("project_id") or "").strip()
        rid = str(item.get("assist_request_id") or "").strip()
        if pid and rid:
            _write_json_file(_assist_request_item_path(self.store, pid, rid), item)
        return item

    def create(
        self,
        *,
        project_id: str,
        task_path: str = "",
        source_channel: str = "",
        target_channel: str = "",
        question: str = "",
        created_by: str = "system",
        status: str = "open",
        context_refs: Optional[list[str]] = None,
        trigger_reason: str = "",
        decision_required: bool = False,
        missing_dimensions: Optional[list[str]] = None,
        support_score: Optional[int] = None,
        support_level: str = "",
        threshold_triggered: Optional[bool] = None,
        evidence_count: Optional[int] = None,
        required_evidence_count: Optional[int] = None,
        help_kind: str = "",
        close_action: str = "",
        close_by: str = "",
        resolution_summary: str = "",
        resolved_at: str = "",
        close_writeback_run_id: str = "",
    ) -> dict[str, Any]:
        pid = str(project_id or "").strip()
        question_txt = _safe_text(question, 8000).strip()
        if not question_txt:
            raise ValueError("missing question")
        request_id = _assist_request_new_id()
        now = _now_iso()
        actor = _safe_text(created_by, 20).strip().lower()
        if actor not in {"user", "agent", "system"}:
            actor = "system"
        score = int(support_score if support_score is not None else 0)
        score = max(0, min(score, 100))
        dims = _assist_request_normalize_missing_dimensions(missing_dimensions or [])
        evidence_n = max(0, int(evidence_count if evidence_count is not None else 0))
        required_n = max(1, int(required_evidence_count if required_evidence_count is not None else 2))
        level = _safe_text(support_level, 20).strip().lower()
        if level not in {"sufficient", "watch", "insufficient"}:
            level = _assist_request_support_level_from_score(score)
        source_channel_txt = self._resolve_source_channel_with_fallback(
            project_id=pid,
            task_path=_safe_text(task_path, 1200).strip(),
            source_channel=source_channel,
        )
        triggered = (
            bool(threshold_triggered)
            if threshold_triggered is not None
            else _assist_request_threshold_triggered(
                support_score=score,
                missing_dimensions=dims,
                evidence_count=evidence_n,
                required_evidence_count=required_n,
            )
        )
        item = {
            "assist_request_id": request_id,
            "project_id": pid,
            "task_path": _safe_text(task_path, 1200).strip(),
            "source_channel": source_channel_txt,
            "target_channel": _safe_text(target_channel, 200).strip(),
            "question": question_txt,
            "status": _assist_request_normalize_status(status, "open"),
            "context_refs": list(context_refs or [])[:40],
            "trigger_reason": _safe_text(trigger_reason, 120).strip().lower(),
            "decision_required": bool(decision_required),
            "missing_dimensions": dims,
            "support_score": score,
            "support_level": level,
            "threshold_triggered": bool(triggered),
            "evidence_count": evidence_n,
            "required_evidence_count": required_n,
            "help_kind": _safe_text(help_kind, 80).strip().lower(),
            "created_by": actor,
            "created_at": now,
            "updated_at": now,
            "last_reply": "",
            "last_reply_by": "",
            "last_reply_at": "",
            "writeback_run_id": "",
            "close_action": _safe_text(close_action, 40).strip().lower(),
            "close_by": _safe_text(close_by, 20).strip().lower(),
            "resolution_summary": _safe_text(resolution_summary, 2000).strip(),
            "resolved_at": _safe_text(resolved_at, 80).strip(),
            "close_writeback_run_id": _safe_text(close_writeback_run_id, 80).strip(),
            "error": "",
        }
        with self._lock:
            self._save_item_locked(item)
        return dict(item)

    def get(self, project_id: str, request_id: str) -> Optional[dict[str, Any]]:
        with self._lock:
            item = self._load_item_locked(project_id, request_id)
        if not item:
            return None
        return dict(item)

    def list(
        self,
        project_id: str,
        status: str = "",
        limit: int = 20,
        task_path: str = "",
        help_kind: str = "",
    ) -> list[dict[str, Any]]:
        pid = str(project_id or "").strip()
        root = _assist_request_project_root(self.store, pid)
        if not root.exists():
            return []
        target_status = _safe_text(status, 40).strip().lower()
        target_task_path = _safe_text(task_path, 1200).strip()
        target_help_kind = _safe_text(help_kind, 80).strip().lower()
        rows: list[tuple[float, dict[str, Any]]] = []
        for p in root.glob("*.json"):
            raw = _read_json_file(p)
            if not raw:
                continue
            raw, _ = self._normalize_item_locked(raw)
            if str(raw.get("project_id") or "").strip() != pid:
                continue
            st = str(raw.get("status") or "").strip().lower()
            if target_status and st != target_status:
                continue
            if target_task_path and str(raw.get("task_path") or "").strip() != target_task_path:
                continue
            if target_help_kind and str(raw.get("help_kind") or "").strip().lower() != target_help_kind:
                continue
            ts = _parse_rfc3339_ts(raw.get("updated_at")) or p.stat().st_mtime
            rows.append((ts, raw))
        rows.sort(key=lambda x: x[0], reverse=True)
        out: list[dict[str, Any]] = []
        for _, item in rows[: max(1, min(int(limit or 20), 200))]:
            out.append(dict(item))
        return out

    def _find_open_match_locked(
        self,
        *,
        project_id: str,
        task_path: str,
        help_kind: str,
    ) -> Optional[dict[str, Any]]:
        pid = str(project_id or "").strip()
        root = _assist_request_project_root(self.store, pid)
        if not root.exists():
            return None
        target_task = str(task_path or "").strip()
        target_kind = str(help_kind or "").strip().lower()
        latest: Optional[dict[str, Any]] = None
        latest_ts = 0.0
        for p in root.glob("*.json"):
            raw = _read_json_file(p)
            if not raw:
                continue
            raw, _ = self._normalize_item_locked(raw)
            if str(raw.get("project_id") or "").strip() != pid:
                continue
            if not self._is_open_status(str(raw.get("status") or "")):
                continue
            if target_task and str(raw.get("task_path") or "").strip() != target_task:
                continue
            if target_kind and str(raw.get("help_kind") or "").strip().lower() != target_kind:
                continue
            ts = _parse_rfc3339_ts(raw.get("updated_at")) or p.stat().st_mtime
            if ts >= latest_ts:
                latest_ts = ts
                latest = raw
        return dict(latest) if isinstance(latest, dict) else None

    def auto_trigger(
        self,
        *,
        project_id: str,
        task_path: str,
        source_channel: str = "",
        target_channel: str = "",
        question: str = "",
        context_refs: Optional[list[str]] = None,
        trigger_reason: str = "",
        decision_required: bool = False,
        support_score: Optional[int] = None,
        support_level: str = "",
        missing_dimensions: Optional[list[str]] = None,
        evidence_count: Optional[int] = None,
        required_evidence_count: Optional[int] = None,
        help_kind: str = "",
        created_by: str = "system",
    ) -> tuple[bool, bool, dict[str, Any]]:
        pid = str(project_id or "").strip()
        task_path_txt = _safe_text(task_path, 1200).strip()
        if not task_path_txt:
            raise ValueError("missing task_path")
        kind = _safe_text(help_kind, 80).strip().lower() or "insufficient_evidence"
        score = int(support_score if support_score is not None else 0)
        score = max(0, min(score, 100))
        dims = _assist_request_normalize_missing_dimensions(missing_dimensions or [])
        evidence_n = max(0, int(evidence_count if evidence_count is not None else 0))
        required_n = max(1, int(required_evidence_count if required_evidence_count is not None else 2))
        level = _safe_text(support_level, 20).strip().lower()
        if level not in {"sufficient", "watch", "insufficient"}:
            level = _assist_request_support_level_from_score(score)
        source_channel_txt = self._resolve_source_channel_with_fallback(
            project_id=pid,
            task_path=task_path_txt,
            source_channel=source_channel,
        )
        triggered = _assist_request_threshold_triggered(
            support_score=score,
            missing_dimensions=dims,
            evidence_count=evidence_n,
            required_evidence_count=required_n,
        )
        if not triggered:
            shadow = {
                "project_id": pid,
                "task_path": task_path_txt,
                "help_kind": kind,
                "trigger_reason": _safe_text(trigger_reason, 120).strip().lower(),
                "decision_required": bool(decision_required),
                "support_score": score,
                "support_level": level,
                "threshold_triggered": False,
                "missing_dimensions": dims,
                "evidence_count": evidence_n,
                "required_evidence_count": required_n,
                "status": "skipped",
            }
            return False, False, shadow

        with self._lock:
            existing = self._find_open_match_locked(project_id=pid, task_path=task_path_txt, help_kind=kind)
            if existing:
                existing["trigger_reason"] = _safe_text(trigger_reason, 120).strip().lower()
                existing["decision_required"] = bool(decision_required)
                existing["support_score"] = score
                existing["support_level"] = level
                existing["threshold_triggered"] = True
                existing["missing_dimensions"] = dims
                existing["evidence_count"] = evidence_n
                existing["required_evidence_count"] = required_n
                existing["context_refs"] = list(context_refs or [])[:40]
                if source_channel_txt:
                    existing["source_channel"] = source_channel_txt
                if target_channel:
                    existing["target_channel"] = _safe_text(target_channel, 200).strip()
                if question:
                    existing["question"] = _safe_text(question, 8000).strip()
                existing["status"] = _assist_request_normalize_status(existing.get("status"), "open")
                existing["help_kind"] = kind
                existing["error"] = ""
                self._save_item_locked(existing)
                return True, True, dict(existing)

            seed_question = _safe_text(question, 8000).strip() or "请补齐关键证据并给出收口结论。"
            actor = _safe_text(created_by, 20).strip().lower()
            if actor not in {"user", "agent", "system"}:
                actor = "system"
            now = _now_iso()
            created = {
                "assist_request_id": _assist_request_new_id(),
                "project_id": pid,
                "task_path": task_path_txt,
                "source_channel": source_channel_txt,
                "target_channel": _safe_text(target_channel, 200).strip(),
                "question": seed_question,
                "status": "open",
                "context_refs": list(context_refs or [])[:40],
                "trigger_reason": _safe_text(trigger_reason, 120).strip().lower(),
                "decision_required": bool(decision_required),
                "missing_dimensions": dims,
                "support_score": score,
                "support_level": level,
                "threshold_triggered": True,
                "evidence_count": evidence_n,
                "required_evidence_count": required_n,
                "help_kind": kind,
                "created_by": actor,
                "created_at": now,
                "updated_at": now,
                "last_reply": "",
                "last_reply_by": "",
                "last_reply_at": "",
                "writeback_run_id": "",
                "close_action": "",
                "close_by": "",
                "resolution_summary": "",
                "resolved_at": "",
                "close_writeback_run_id": "",
                "close_note": "",
                "error": "",
            }
            self._save_item_locked(created)
            return True, False, dict(created)

    def _resolve_writeback_target(
        self,
        *,
        project_id: str,
        item: dict[str, Any],
        writeback: Optional[dict[str, Any]] = None,
    ) -> Optional[dict[str, str]]:
        wb = writeback if isinstance(writeback, dict) else {}
        wb_channel = _safe_text(
            wb.get("channel_name") if "channel_name" in wb else wb.get("channelName"),
            200,
        ).strip()
        wb_session = _safe_text(
            wb.get("session_id") if "session_id" in wb else wb.get("sessionId"),
            80,
        ).strip()
        if wb_session and not _looks_like_uuid(wb_session):
            wb_session = ""
        if wb_channel and wb_session:
            return {"channel_name": wb_channel, "session_id": wb_session}
        if wb_channel:
            resolved = _resolve_primary_target_by_channel(project_id, wb_channel)
            if resolved:
                return resolved
        # V1 default strategy: write back to master control channel.
        target = _resolve_master_control_target(project_id)
        if target:
            return target
        # Backward-compatible fallback: source channel primary session.
        source_channel = str(item.get("source_channel") or "").strip()
        if source_channel:
            return _resolve_primary_target_by_channel(project_id, source_channel)
        return None

    def reply(
        self,
        *,
        project_id: str,
        request_id: str,
        reply: str,
        reply_by: str = "user",
        writeback: Optional[dict[str, Any]] = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        pid = str(project_id or "").strip()
        rid = str(request_id or "").strip()
        reply_text = _safe_text(reply, 8000).strip()
        if not reply_text:
            raise ValueError("missing reply")
        actor = _safe_text(reply_by, 20).strip().lower()
        if actor not in {"user", "agent", "system"}:
            actor = "user"

        with self._lock:
            item = self._load_item_locked(pid, rid)
            if not item:
                raise FileNotFoundError("assist request not found")
            current_status = str(item.get("status") or "").strip().lower()
            if current_status in {"resolved", "canceled"}:
                raise RuntimeError("assist request is closed")

            target = self._resolve_writeback_target(project_id=pid, item=item, writeback=writeback)
            if not target:
                raise LookupError("writeback target unavailable")
            target_channel = str(target.get("channel_name") or "").strip()
            target_session_id = str(target.get("session_id") or "").strip()
            if not target_channel or not target_session_id:
                raise LookupError("writeback target unavailable")

            cli_type = _resolve_cli_type_for_session(self.session_store, pid, target_session_id, "codex")
            message = _assist_request_message_text(item, reply_text, actor)
            extra_meta = {
                "trigger_type": "assist_request_reply",
                "task_path": str(item.get("task_path") or "").strip(),
                "owner_channel_name": str(item.get("source_channel") or "").strip(),
                "assist_request_id": rid,
                "assist_request_status_before": current_status or "open",
                "assist_request_reply_by": actor,
            }
            refs = item.get("context_refs")
            if isinstance(refs, list) and refs:
                extra_meta["assist_context_refs"] = refs[:20]
            run = self.store.create_run(
                pid,
                target_channel,
                target_session_id,
                message,
                profile_label="assist_request_reply",
                cli_type=cli_type,
                sender_type=actor,
                sender_id=f"assist_request:{rid}",
                sender_name="Assist Request Reply",
                extra_meta=extra_meta,
            )
            _enqueue_run_for_dispatch(
                self.store,
                str(run.get("id") or "").strip(),
                target_session_id,
                cli_type,
                self._scheduler,
            )

            now = _now_iso()
            item["status"] = "replied"
            item["last_reply"] = reply_text
            item["last_reply_by"] = actor
            item["last_reply_at"] = now
            item["writeback_run_id"] = str(run.get("id") or "").strip()
            item["writeback_target"] = {
                "channel_name": target_channel,
                "session_id": target_session_id,
            }
            item["error"] = ""
            self._save_item_locked(item)
            return dict(item), dict(run)

    def close(
        self,
        *,
        project_id: str,
        request_id: str,
        close_action: str = "resolved",
        close_by: str = "system",
        resolution_summary: str = "",
        resolved_at: str = "",
        writeback: Optional[dict[str, Any]] = None,
    ) -> tuple[dict[str, Any], Optional[dict[str, Any]]]:
        pid = str(project_id or "").strip()
        rid = str(request_id or "").strip()
        action = _safe_text(close_action, 40).strip().lower() or "resolved"
        if action not in {"resolved", "escalate", "dismissed", "duplicate", "expired"}:
            raise ValueError("invalid close_action")
        actor = _safe_text(close_by, 20).strip().lower()
        if actor not in {"user", "agent", "system"}:
            actor = "system"
        summary = _safe_text(resolution_summary, 2000).strip()
        if not summary:
            raise ValueError("missing resolution_summary")
        resolved_at_text = _safe_text(resolved_at, 80).strip() or _now_iso()

        with self._lock:
            item = self._load_item_locked(pid, rid)
            if not item:
                raise FileNotFoundError("assist request not found")
            current_status = str(item.get("status") or "").strip().lower()
            if current_status in {"closed", "canceled", "resolved"}:
                raise RuntimeError("assist request already closed")

            target = self._resolve_writeback_target(project_id=pid, item=item, writeback=writeback)
            run: Optional[dict[str, Any]] = None
            if target:
                target_channel = str(target.get("channel_name") or "").strip()
                target_session_id = str(target.get("session_id") or "").strip()
                if target_channel and target_session_id:
                    cli_type = _resolve_cli_type_for_session(self.session_store, pid, target_session_id, "codex")
                    message = _assist_request_close_message_text(
                        item,
                        close_action=action,
                        close_by=actor,
                        resolution_summary=summary,
                    )
                    extra_meta = {
                        "trigger_type": "assist_request_close",
                        "task_path": str(item.get("task_path") or "").strip(),
                        "owner_channel_name": str(item.get("source_channel") or "").strip(),
                        "assist_request_id": rid,
                        "assist_request_status_before": current_status or "open",
                        "assist_request_close_action": action,
                        "assist_request_close_by": actor,
                    }
                    run = self.store.create_run(
                        pid,
                        target_channel,
                        target_session_id,
                        message,
                        profile_label="assist_request_close",
                        cli_type=cli_type,
                        sender_type=actor,
                        sender_id=f"assist_request:{rid}",
                        sender_name="Assist Request Close",
                        extra_meta=extra_meta,
                    )
                    _enqueue_run_for_dispatch(
                        self.store,
                        str(run.get("id") or "").strip(),
                        target_session_id,
                        cli_type,
                        self._scheduler,
                    )
                    item["close_writeback_run_id"] = str(run.get("id") or "").strip()
                    item["close_writeback_target"] = {
                        "channel_name": target_channel,
                        "session_id": target_session_id,
                    }

            item["close_action"] = action
            item["close_by"] = actor
            item["resolution_summary"] = summary
            item["resolved_at"] = resolved_at_text
            item["close_note"] = "escalated_to_next_owner" if action == "escalate" else ""
            item["status"] = "resolved" if action == "resolved" else "closed"
            item["error"] = ""
            self._save_item_locked(item)
            return dict(item), (dict(run) if isinstance(run, dict) else None)


# =============================================================================
# Route handlers extracted from server.py
# =============================================================================


def list_assist_requests_response(
    *,
    project_id: str,
    query_string: str,
    assist_runtime: "AssistRequestRuntimeRegistry",
    find_project_cfg: Callable[[str], dict[str, Any]],
) -> tuple[int, dict[str, Any]]:
    """Handle GET /api/projects/{project_id}/assist-requests"""
    from urllib.parse import parse_qs

    project_id = str(project_id or "").strip()
    if not project_id:
        return 400, {"error": "missing project_id"}
    if not find_project_cfg(project_id):
        return 404, {"error": "project not found"}
    if assist_runtime is None:
        return 503, {"error": "assist request runtime unavailable"}

    qs = parse_qs(query_string or "")
    status = _safe_text((qs.get("status") or [""])[0], 40).strip().lower()
    task_path = _safe_text((qs.get("task_path") or qs.get("taskPath") or [""])[0], 1200).strip()
    help_kind = _safe_text((qs.get("help_kind") or qs.get("helpKind") or [""])[0], 80).strip().lower()
    limit_s = _safe_text((qs.get("limit") or ["20"])[0], 20).strip()
    try:
        limit = max(1, min(200, int(limit_s)))
    except Exception:
        limit = 20
    items = assist_runtime.list(
        project_id,
        status=status,
        limit=limit,
        task_path=task_path,
        help_kind=help_kind,
    )
    return 200, {"items": items, "count": len(items)}


def get_assist_request_response(
    *,
    project_id: str,
    request_id: str,
    assist_runtime: "AssistRequestRuntimeRegistry",
    find_project_cfg: Callable[[str], dict[str, Any]],
) -> tuple[int, dict[str, Any]]:
    """Handle GET /api/projects/{project_id}/assist-requests/{request_id}"""
    project_id = str(project_id or "").strip()
    request_id = str(request_id or "").strip()
    if not project_id:
        return 400, {"error": "missing project_id"}
    if not request_id:
        return 400, {"error": "missing assist_request_id"}
    if not find_project_cfg(project_id):
        return 404, {"error": "project not found"}
    if assist_runtime is None:
        return 503, {"error": "assist request runtime unavailable"}
    item = assist_runtime.get(project_id, request_id)
    if not item:
        return 404, {"error": "assist request not found"}
    return 200, {"item": item}


def create_assist_request_response(
    *,
    project_id: str,
    body: dict[str, Any],
    assist_runtime: "AssistRequestRuntimeRegistry",
    find_project_cfg: Callable[[str], dict[str, Any]],
) -> tuple[int, dict[str, Any]]:
    """Handle POST /api/projects/{project_id}/assist-requests"""
    project_id = str(project_id or "").strip()
    if not project_id:
        return 400, {"error": "missing project_id"}
    if not find_project_cfg(project_id):
        return 404, {"error": "project not found"}
    if assist_runtime is None:
        return 503, {"error": "assist request runtime unavailable"}

    if not isinstance(body, dict):
        return 400, {"error": "bad json: object required"}

    task_path = _safe_text(body.get("task_path") if "task_path" in body else body.get("taskPath"), 1200).strip()
    source_channel = _safe_text(
        body.get("source_channel") if "source_channel" in body else body.get("sourceChannel"),
        200,
    ).strip()
    target_channel = _safe_text(
        body.get("target_channel") if "target_channel" in body else body.get("targetChannel"),
        200,
    ).strip()
    question = _safe_text(body.get("question"), 8000).strip()
    created_by = _safe_text(body.get("created_by") if "created_by" in body else body.get("createdBy"), 20).strip()
    status = _safe_text(body.get("status"), 40).strip()
    raw_refs = body.get("context_refs") if "context_refs" in body else body.get("contextRefs")
    context_refs = _assist_request_normalize_context_refs(raw_refs)
    trigger_reason = _safe_text(
        body.get("trigger_reason") if "trigger_reason" in body else body.get("triggerReason"),
        120,
    ).strip()
    decision_required = _coerce_bool(
        body.get("decision_required") if "decision_required" in body else body.get("decisionRequired"),
        False,
    )
    raw_dims = body.get("missing_dimensions") if "missing_dimensions" in body else body.get("missingDimensions")
    missing_dimensions = _assist_request_normalize_missing_dimensions(raw_dims)
    support_score_raw = body.get("support_score") if "support_score" in body else body.get("supportScore")
    support_level = _safe_text(
        body.get("support_level") if "support_level" in body else body.get("supportLevel"),
        20,
    ).strip()
    threshold_triggered_raw = (
        body.get("threshold_triggered") if "threshold_triggered" in body else body.get("thresholdTriggered")
    )
    evidence_count_raw = body.get("evidence_count") if "evidence_count" in body else body.get("evidenceCount")
    required_evidence_count_raw = (
        body.get("required_evidence_count")
        if "required_evidence_count" in body
        else body.get("requiredEvidenceCount")
    )
    help_kind = _safe_text(body.get("help_kind") if "help_kind" in body else body.get("helpKind"), 80).strip()
    close_action = _safe_text(body.get("close_action") if "close_action" in body else body.get("closeAction"), 40).strip()
    close_by = _safe_text(body.get("close_by") if "close_by" in body else body.get("closeBy"), 20).strip()
    resolution_summary = _safe_text(
        body.get("resolution_summary") if "resolution_summary" in body else body.get("resolutionSummary"),
        2000,
    ).strip()
    resolved_at = _safe_text(body.get("resolved_at") if "resolved_at" in body else body.get("resolvedAt"), 80).strip()
    close_writeback_run_id = _safe_text(
        body.get("close_writeback_run_id")
        if "close_writeback_run_id" in body
        else body.get("closeWritebackRunId"),
        80,
    ).strip()
    if not question:
        return 400, {"error": "missing question"}

    support_score: Optional[int] = None
    if support_score_raw is not None:
        try:
            support_score = int(support_score_raw)
        except Exception:
            return 400, {"error": "invalid support_score"}
    threshold_triggered: Optional[bool] = None
    if threshold_triggered_raw is not None:
        threshold_triggered = _coerce_bool(threshold_triggered_raw, False)
    evidence_count: Optional[int] = None
    if evidence_count_raw is not None:
        try:
            evidence_count = int(evidence_count_raw)
        except Exception:
            return 400, {"error": "invalid evidence_count"}
    required_evidence_count: Optional[int] = None
    if required_evidence_count_raw is not None:
        try:
            required_evidence_count = int(required_evidence_count_raw)
        except Exception:
            return 400, {"error": "invalid required_evidence_count"}

    item = assist_runtime.create(
        project_id=project_id,
        task_path=task_path,
        source_channel=source_channel,
        target_channel=target_channel,
        question=question,
        created_by=created_by or "system",
        status=status or "open",
        context_refs=context_refs,
        trigger_reason=trigger_reason,
        decision_required=decision_required,
        missing_dimensions=missing_dimensions,
        support_score=support_score,
        support_level=support_level,
        threshold_triggered=threshold_triggered,
        evidence_count=evidence_count,
        required_evidence_count=required_evidence_count,
        help_kind=help_kind,
        close_action=close_action,
        close_by=close_by,
        resolution_summary=resolution_summary,
        resolved_at=resolved_at,
        close_writeback_run_id=close_writeback_run_id,
    )
    return 200, {"ok": True, "item": item}


def auto_trigger_assist_request_response(
    *,
    project_id: str,
    body: dict[str, Any],
    assist_runtime: "AssistRequestRuntimeRegistry",
    find_project_cfg: Callable[[str], dict[str, Any]],
) -> tuple[int, dict[str, Any]]:
    """Handle POST /api/projects/{project_id}/assist-requests/auto-trigger"""
    project_id = str(project_id or "").strip()
    if not project_id:
        return 400, {"error": "missing project_id"}
    if not find_project_cfg(project_id):
        return 404, {"error": "project not found"}
    if assist_runtime is None:
        return 503, {"error": "assist request runtime unavailable"}

    if not isinstance(body, dict):
        return 400, {"error": "bad json: object required"}

    task_path = _safe_text(body.get("task_path") if "task_path" in body else body.get("taskPath"), 1200).strip()
    source_channel = _safe_text(
        body.get("source_channel") if "source_channel" in body else body.get("sourceChannel"),
        200,
    ).strip()
    target_channel = _safe_text(
        body.get("target_channel") if "target_channel" in body else body.get("targetChannel"),
        200,
    ).strip()
    question = _safe_text(body.get("question"), 8000).strip()
    raw_refs = body.get("context_refs") if "context_refs" in body else body.get("contextRefs")
    context_refs = _assist_request_normalize_context_refs(raw_refs)
    trigger_reason = _safe_text(
        body.get("trigger_reason") if "trigger_reason" in body else body.get("triggerReason"),
        120,
    ).strip()
    decision_required = _coerce_bool(
        body.get("decision_required") if "decision_required" in body else body.get("decisionRequired"),
        False,
    )
    support_level = _safe_text(
        body.get("support_level") if "support_level" in body else body.get("supportLevel"),
        20,
    ).strip()
    raw_dims = body.get("missing_dimensions") if "missing_dimensions" in body else body.get("missingDimensions")
    missing_dimensions = _assist_request_normalize_missing_dimensions(raw_dims)
    help_kind = _safe_text(body.get("help_kind") if "help_kind" in body else body.get("helpKind"), 80).strip()
    created_by = _safe_text(body.get("created_by") if "created_by" in body else body.get("createdBy"), 20).strip()
    support_score_raw = body.get("support_score") if "support_score" in body else body.get("supportScore")
    evidence_count_raw = body.get("evidence_count") if "evidence_count" in body else body.get("evidenceCount")
    required_evidence_count_raw = (
        body.get("required_evidence_count")
        if "required_evidence_count" in body
        else body.get("requiredEvidenceCount")
    )

    support_score: Optional[int] = None
    if support_score_raw is not None:
        try:
            support_score = int(support_score_raw)
        except Exception:
            return 400, {"error": "invalid support_score"}
    evidence_count: Optional[int] = None
    if evidence_count_raw is not None:
        try:
            evidence_count = int(evidence_count_raw)
        except Exception:
            return 400, {"error": "invalid evidence_count"}
    required_evidence_count: Optional[int] = None
    if required_evidence_count_raw is not None:
        try:
            required_evidence_count = int(required_evidence_count_raw)
        except Exception:
            return 400, {"error": "invalid required_evidence_count"}

    try:
        triggered, updated, item = assist_runtime.auto_trigger(
            project_id=project_id,
            task_path=task_path,
            source_channel=source_channel,
            target_channel=target_channel,
            question=question,
            context_refs=context_refs,
            trigger_reason=trigger_reason,
            decision_required=decision_required,
            support_score=support_score,
            support_level=support_level,
            missing_dimensions=missing_dimensions,
            evidence_count=evidence_count,
            required_evidence_count=required_evidence_count,
            help_kind=help_kind,
            created_by=created_by or "system",
        )
    except ValueError as e:
        return 400, {"error": str(e), "step": "assist_request_auto_trigger"}
    except Exception as e:
        return 500, {"error": str(e), "step": "assist_request_auto_trigger"}
    return 200, {"ok": True, "triggered": triggered, "updated": updated, "item": item}


def close_assist_request_response(
    *,
    project_id: str,
    request_id: str,
    body: dict[str, Any],
    assist_runtime: "AssistRequestRuntimeRegistry",
    find_project_cfg: Callable[[str], dict[str, Any]],
) -> tuple[int, dict[str, Any]]:
    """Handle POST /api/projects/{project_id}/assist-requests/{request_id}/close"""
    project_id = str(project_id or "").strip()
    request_id = str(request_id or "").strip()
    if not project_id:
        return 400, {"error": "missing project_id"}
    if not request_id:
        return 400, {"error": "missing assist_request_id"}
    if not find_project_cfg(project_id):
        return 404, {"error": "project not found"}
    if assist_runtime is None:
        return 503, {"error": "assist request runtime unavailable"}

    body_obj = body if isinstance(body, dict) else {}
    close_action = _safe_text(
        body_obj.get("close_action") if "close_action" in body_obj else body_obj.get("closeAction"),
        40,
    ).strip()
    close_by = _safe_text(
        body_obj.get("close_by") if "close_by" in body_obj else body_obj.get("closeBy"),
        20,
    ).strip()
    resolution_summary = _safe_text(
        body_obj.get("resolution_summary") if "resolution_summary" in body_obj else body_obj.get("resolutionSummary"),
        2000,
    ).strip()
    resolved_at = _safe_text(
        body_obj.get("resolved_at") if "resolved_at" in body_obj else body_obj.get("resolvedAt"),
        80,
    ).strip()
    writeback = body_obj.get("writeback") if isinstance(body_obj.get("writeback"), dict) else None

    try:
        item, run = assist_runtime.close(
            project_id=project_id,
            request_id=request_id,
            close_action=close_action or "resolved",
            close_by=close_by or "system",
            resolution_summary=resolution_summary,
            resolved_at=resolved_at,
            writeback=writeback,
        )
    except FileNotFoundError:
        return 404, {"error": "assist request not found"}
    except ValueError as e:
        return 400, {"error": str(e), "step": "assist_request_close"}
    except RuntimeError as e:
        return 409, {"error": str(e), "step": "assist_request_close"}
    except Exception as e:
        return 500, {"error": str(e), "step": "assist_request_close"}
    payload: dict[str, Any] = {"ok": True, "item": item}
    if run:
        payload["run"] = {
            "id": str(run.get("id") or ""),
            "status": str(run.get("status") or ""),
        }
    return 200, payload


def reply_assist_request_response(
    *,
    project_id: str,
    request_id: str,
    body: dict[str, Any],
    assist_runtime: "AssistRequestRuntimeRegistry",
    find_project_cfg: Callable[[str], dict[str, Any]],
) -> tuple[int, dict[str, Any]]:
    """Handle POST /api/projects/{project_id}/assist-requests/{request_id}/reply"""
    project_id = str(project_id or "").strip()
    request_id = str(request_id or "").strip()
    if not project_id:
        return 400, {"error": "missing project_id"}
    if not request_id:
        return 400, {"error": "missing assist_request_id"}
    if not find_project_cfg(project_id):
        return 404, {"error": "project not found"}
    if assist_runtime is None:
        return 503, {"error": "assist request runtime unavailable"}

    body_obj = body if isinstance(body, dict) else {}
    reply = _safe_text(body_obj.get("reply"), 8000).strip()
    reply_by = _safe_text(body_obj.get("reply_by") if "reply_by" in body_obj else body_obj.get("replyBy"), 20).strip()
    writeback = body_obj.get("writeback") if isinstance(body_obj.get("writeback"), dict) else None

    try:
        item, run = assist_runtime.reply(
            project_id=project_id,
            request_id=request_id,
            reply=reply,
            reply_by=reply_by or "user",
            writeback=writeback,
        )
    except FileNotFoundError:
        return 404, {"error": "assist request not found"}
    except ValueError as e:
        return 400, {"error": str(e), "step": "assist_request_reply"}
    except RuntimeError as e:
        return 422, {"error": str(e), "step": "assist_request_reply"}
    except LookupError as e:
        return 422, {"error": str(e), "step": "assist_request_writeback_target"}
    except Exception as e:
        return 500, {"error": str(e), "step": "assist_request_reply"}
    return 200, {
        "ok": True,
        "item": item,
        "run": {
            "id": str(run.get("id") or ""),
            "status": str(run.get("status") or ""),
        },
    }
