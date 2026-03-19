from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

EVENT_TYPES = {"done", "error", "interrupted"}
INTERRUPT_REASONS = {
    "user_interrupt",
    "server_restart",
    "process_exit",
    "timeout_interrupt",
    "unknown",
}
SUMMARY_EVENT_TYPES = {"error", "interrupted"}
DEFAULT_SUMMARY_WINDOW_S = 300


def _as_text(value: Any) -> str:
    return str(value or "").strip()


def _first_non_empty(data: Mapping[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        if key in data:
            val = _as_text(data.get(key))
            if val:
                return val
    return ""


def _first_present(data: Mapping[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in data:
            return data.get(key)
    return None


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _parse_ts(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    s = _as_text(value)
    if not s:
        return 0.0
    try:
        return datetime.fromisoformat(s).timestamp()
    except ValueError:
        return 0.0


def normalize_callback_target(data: Mapping[str, Any] | None) -> dict[str, str]:
    payload = data or {}
    return {
        "channel_name": _first_non_empty(payload, ("channel_name", "channelName")),
        "session_id": _first_non_empty(payload, ("session_id", "sessionId")),
    }


def normalize_route_resolution(data: Mapping[str, Any] | None) -> dict[str, Any]:
    payload = data or {}
    out = {
        "source": _first_non_empty(payload, ("source",)) or "unknown",
        "fallback_stage": _first_non_empty(payload, ("fallback_stage", "fallbackStage")) or "unknown",
        "degrade_reason": _first_non_empty(payload, ("degrade_reason", "degradeReason")) or "none",
        "final_target": normalize_callback_target(
            _first_present(payload, ("final_target", "finalTarget")) or {}
        ),
    }
    return out


def normalize_message_ref(data: Mapping[str, Any] | None) -> dict[str, str]:
    payload = data or {}
    return {
        "project_id": _first_non_empty(payload, ("project_id", "projectId")),
        "channel_name": _first_non_empty(payload, ("channel_name", "channelName")),
        "session_id": _first_non_empty(payload, ("session_id", "sessionId")),
        "run_id": _first_non_empty(payload, ("run_id", "runId")),
    }


def _normalize_evidence_paths(data: Mapping[str, Any]) -> list[str]:
    raw = _first_present(data, ("evidence_paths", "evidencePaths"))
    if isinstance(raw, (list, tuple)):
        out: list[str] = []
        for item in raw:
            s = _as_text(item)
            if s:
                out.append(s)
        return out
    if isinstance(raw, str):
        s = _as_text(raw)
        return [s] if s else []
    return []


def callback_summary_window_key(
    project_id: str,
    source_channel_name: str,
    target_session_id: str,
    event_type: str,
) -> str:
    return "|".join(
        [
            _as_text(project_id),
            _as_text(source_channel_name),
            _as_text(target_session_id),
            _as_text(event_type),
        ]
    )


def build_callback_event_idempotency_key(data: Mapping[str, Any] | None) -> str:
    payload = data or {}
    project_id = _first_non_empty(payload, ("project_id", "projectId"))
    source_run_id = _first_non_empty(payload, ("source_run_id", "sourceRunId"))
    event_type = _first_non_empty(payload, ("event_type", "eventType")).lower()

    # Prefer explicit target_session_id if already normalized.
    target_session_id = _first_non_empty(payload, ("target_session_id", "targetSessionId"))
    if not target_session_id:
        rr = normalize_route_resolution(
            _first_present(payload, ("route_resolution", "routeResolution")) or {}
        )
        target_session_id = _as_text((rr.get("final_target") or {}).get("session_id"))
    if not target_session_id:
        cb = normalize_callback_target(_first_present(payload, ("callback_to", "callbackTo")) or {})
        target_session_id = cb["session_id"]
    return "|".join([project_id, source_run_id, event_type, target_session_id])


def normalize_callback_event_payload(data: Mapping[str, Any] | None) -> dict[str, Any]:
    payload = data or {}
    route_resolution = normalize_route_resolution(
        _first_present(payload, ("route_resolution", "routeResolution")) or {}
    )
    callback_to = normalize_callback_target(
        _first_present(payload, ("callback_to", "callbackTo")) or {}
    )
    final_target = route_resolution.get("final_target") or {}
    target_session_id = _as_text(final_target.get("session_id") or callback_to.get("session_id"))
    target_channel_name = _as_text(final_target.get("channel_name") or callback_to.get("channel_name"))

    event_type = _first_non_empty(payload, ("event_type", "eventType")).lower()
    event_reason = _first_non_empty(payload, ("event_reason", "eventReason")).lower()

    feedback_file_path = _as_text(
        _first_present(payload, ("feedback_file_path", "feedbackFilePath"))
    )
    source_channel_name = _first_non_empty(
        payload,
        ("source_channel_name", "sourceChannelName", "channel_name", "channelName"),
    )
    source_ref = normalize_message_ref(_first_present(payload, ("source_ref", "sourceRef")) or {})
    target_ref = normalize_message_ref(_first_present(payload, ("target_ref", "targetRef")) or {})
    source_project_id = _first_non_empty(payload, ("source_project_id", "sourceProjectId")) or _first_non_empty(payload, ("project_id", "projectId")) or source_ref.get("project_id", "")
    source_session_id = _first_non_empty(payload, ("source_session_id", "sourceSessionId")) or source_ref.get("session_id", "")
    target_project_id = _first_non_empty(payload, ("target_project_id", "targetProjectId")) or target_ref.get("project_id", "") or _first_non_empty(payload, ("project_id", "projectId"))

    out = {
        "event_type": event_type,
        "event_reason": event_reason,
        "source_run_id": _first_non_empty(payload, ("source_run_id", "sourceRunId")),
        "project_id": _first_non_empty(payload, ("project_id", "projectId")),
        "source_project_id": source_project_id,
        "source_session_id": source_session_id,
        "task_path": _first_non_empty(payload, ("task_path", "taskPath")),
        "callback_to": callback_to,
        "route_resolution": route_resolution,
        "evidence_paths": _normalize_evidence_paths(payload),
        "feedback_file_path": feedback_file_path,
        "feedback_file_pending": not bool(feedback_file_path),
        "source_channel_name": source_channel_name,
        "target_project_id": target_project_id,
        "target_session_id": target_session_id,
        "target_channel_name": target_channel_name,
    }
    if any(source_ref.values()):
        out["source_ref"] = source_ref
    if any(target_ref.values()):
        out["target_ref"] = target_ref
    out["idempotency_key"] = build_callback_event_idempotency_key({**payload, **out})
    return out


def validate_callback_event_payload(data: Mapping[str, Any] | None) -> dict[str, Any]:
    normalized = normalize_callback_event_payload(data)
    issues: list[dict[str, str]] = []

    if normalized["event_type"] not in EVENT_TYPES:
        issues.append(
            {
                "level": "error",
                "code": "invalid_event_type",
                "message": f"unsupported event_type: {normalized['event_type'] or '(empty)'}",
            }
        )

    if not normalized["project_id"]:
        issues.append({"level": "error", "code": "project_id_missing", "message": "project_id missing"})
    if not normalized["source_run_id"]:
        issues.append(
            {"level": "error", "code": "source_run_id_missing", "message": "source_run_id missing"}
        )

    rr = normalized["route_resolution"] or {}
    for key in ("source", "fallback_stage", "degrade_reason", "final_target"):
        if key not in rr:
            issues.append(
                {"level": "error", "code": "route_resolution_missing", "message": f"route_resolution.{key} missing"}
            )
    ft = rr.get("final_target") or {}
    if not _as_text(ft.get("channel_name")) and not _as_text(ft.get("session_id")):
        issues.append(
            {
                "level": "warn",
                "code": "final_target_empty",
                "message": "route_resolution.final_target channel/session both empty",
            }
        )

    if normalized["event_type"] == "interrupted":
        if normalized["event_reason"] not in INTERRUPT_REASONS:
            issues.append(
                {
                    "level": "error",
                    "code": "event_reason_invalid",
                    "message": "interrupted event requires valid event_reason",
                }
            )
    elif normalized["event_reason"]:
        issues.append(
            {
                "level": "warn",
                "code": "event_reason_unused",
                "message": "event_reason provided for non-interrupted event",
            }
        )

    if not normalized["evidence_paths"]:
        issues.append(
            {
                "level": "warn",
                "code": "evidence_paths_empty",
                "message": "evidence_paths empty; recommend at least source .json",
            }
        )

    if normalized["feedback_file_pending"]:
        issues.append(
            {
                "level": "warn",
                "code": "feedback_file_pending",
                "message": "反馈文件待补录（验收仍以反馈目录文件为准）",
            }
        )

    return {
        "normalized": normalized,
        "issues": issues,
        "ok": not any(i["level"] == "error" for i in issues),
    }


class CallbackSummaryWindowBook:
    """In-memory summary window state for 12-7C V1.

    Policy:
    - `done`: no summary window, always immediate
    - `error/interrupted`: first event immediate, window-active events suppressed+aggregated
    """

    def __init__(self, window_s: int = DEFAULT_SUMMARY_WINDOW_S) -> None:
        self.window_s = max(1, int(window_s))
        self._windows: dict[str, dict[str, Any]] = {}

    def register(self, data: Mapping[str, Any], now_ts: float | None = None) -> dict[str, Any]:
        validation = validate_callback_event_payload(data)
        normalized = validation["normalized"]
        ts = float(now_ts if now_ts is not None else _parse_ts(_first_present(data or {}, ("finished_at", "finishedAt"))) or datetime.now(timezone.utc).timestamp())

        event_type = normalized["event_type"]
        if event_type not in SUMMARY_EVENT_TYPES:
            return {
                "status": "immediate",
                "dispatch_now": True,
                "summary_key": "",
                "validation": validation,
            }

        key = callback_summary_window_key(
            normalized["project_id"],
            normalized["source_channel_name"],
            normalized["target_session_id"],
            event_type,
        )
        state = self._windows.get(key)
        if not isinstance(state, dict) or float(state.get("window_end_ts") or 0.0) <= ts:
            self._windows[key] = {
                "summary_key": key,
                "project_id": normalized["project_id"],
                "event_type": event_type,
                "source_channel_name": normalized["source_channel_name"],
                "target_session_id": normalized["target_session_id"],
                "target_channel_name": normalized["target_channel_name"],
                "window_start_ts": ts,
                "window_end_ts": ts + float(self.window_s),
                "first_source_run_id": normalized["source_run_id"],
                "route_resolution": normalized["route_resolution"],
                "callback_to": normalized["callback_to"],
                "pending": [],
                "source_run_ids": [normalized["source_run_id"]],
                "count_total": 1,
                "count_suppressed": 0,
            }
            return {
                "status": "immediate_window_opened",
                "dispatch_now": True,
                "summary_key": key,
                "window_end_ts": self._windows[key]["window_end_ts"],
                "validation": validation,
            }

        pending_item = {
            "source_run_id": normalized["source_run_id"],
            "event_reason": normalized["event_reason"],
            "feedback_file_path": normalized["feedback_file_path"],
            "evidence_paths": list(normalized["evidence_paths"]),
        }
        state.setdefault("pending", []).append(pending_item)
        state.setdefault("source_run_ids", []).append(normalized["source_run_id"])
        state["count_total"] = int(state.get("count_total") or 0) + 1
        state["count_suppressed"] = int(state.get("count_suppressed") or 0) + 1
        return {
            "status": "suppressed_window",
            "dispatch_now": False,
            "summary_key": key,
            "window_end_ts": state.get("window_end_ts"),
            "validation": validation,
        }

    def flush_due(self, now_ts: float | None = None) -> list[dict[str, Any]]:
        ts = float(now_ts if now_ts is not None else datetime.now(timezone.utc).timestamp())
        due_keys: list[str] = []
        for key, state in list(self._windows.items()):
            if float(state.get("window_end_ts") or 0.0) <= ts:
                due_keys.append(key)
        out: list[dict[str, Any]] = []
        for key in due_keys:
            summary = self.flush_key(key)
            if summary:
                out.append(summary)
        return out

    def flush_key(self, key: str) -> dict[str, Any]:
        state = self._windows.pop(key, None)
        if not isinstance(state, dict):
            return {}
        return {
            "summary_key": key,
            "event_type": state.get("event_type") or "",
            "project_id": state.get("project_id") or "",
            "source_channel_name": state.get("source_channel_name") or "",
            "target_session_id": state.get("target_session_id") or "",
            "target_channel_name": state.get("target_channel_name") or "",
            "window_start_ts": float(state.get("window_start_ts") or 0.0),
            "window_end_ts": float(state.get("window_end_ts") or 0.0),
            "count_total": int(state.get("count_total") or 0),
            "count_suppressed": int(state.get("count_suppressed") or 0),
            "source_run_ids": list(state.get("source_run_ids") or []),
            "route_resolution": dict(state.get("route_resolution") or {}),
            "callback_to": dict(state.get("callback_to") or {}),
            "pending": list(state.get("pending") or []),
        }

    def snapshot(self) -> dict[str, Any]:
        windows: list[dict[str, Any]] = []
        for key in sorted(self._windows.keys()):
            state = self._windows[key]
            windows.append(
                {
                    "summary_key": key,
                    "event_type": state.get("event_type"),
                    "project_id": state.get("project_id"),
                    "source_channel_name": state.get("source_channel_name"),
                    "target_session_id": state.get("target_session_id"),
                    "target_channel_name": state.get("target_channel_name"),
                    "window_start_ts": state.get("window_start_ts"),
                    "window_end_ts": state.get("window_end_ts"),
                    "count_total": state.get("count_total"),
                    "count_suppressed": state.get("count_suppressed"),
                }
            )
        return {"window_s": self.window_s, "active_count": len(windows), "windows": windows}


class CallbackDispatchLedger:
    """JSONL-first ledger for callback dispatch orchestration and dedupe."""

    def __init__(self, ledger_path: Path, summary_json_path: Path | None = None) -> None:
        self.ledger_path = Path(ledger_path)
        self.summary_json_path = Path(summary_json_path) if summary_json_path else None
        self._idempotency_keys: set[str] = set()
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        if self.ledger_path.exists():
            self._load_existing_keys()

    def _load_existing_keys(self) -> None:
        try:
            with self.ledger_path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    key = _as_text(row.get("idempotency_key"))
                    if key:
                        self._idempotency_keys.add(key)
        except FileNotFoundError:
            return

    def seen(self, idempotency_key: str) -> bool:
        return idempotency_key in self._idempotency_keys

    def append_event_record(
        self,
        data: Mapping[str, Any],
        *,
        stage: str,
        status: str,
        note: str = "",
        extra: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        validation = validate_callback_event_payload(data)
        normalized = validation["normalized"]
        key = normalized["idempotency_key"]
        duplicate = bool(key) and key in self._idempotency_keys
        if key and status in {"sent", "suppressed_window", "duplicate"}:
            self._idempotency_keys.add(key)

        row: dict[str, Any] = {
            "recorded_at": _now_iso(),
            "record_type": "callback_event",
            "stage": stage,
            "status": status,
            "note": note,
            "idempotency_key": key,
            "duplicate": duplicate,
            "project_id": normalized["project_id"],
            "source_project_id": normalized["source_project_id"],
            "source_run_id": normalized["source_run_id"],
            "source_session_id": normalized["source_session_id"],
            "event_type": normalized["event_type"],
            "event_reason": normalized["event_reason"],
            "source_channel_name": normalized["source_channel_name"],
            "target_project_id": normalized["target_project_id"],
            "target_channel_name": normalized["target_channel_name"],
            "target_session_id": normalized["target_session_id"],
            "feedback_file_path": normalized["feedback_file_path"],
            "feedback_file_pending": normalized["feedback_file_pending"],
            "evidence_paths": list(normalized["evidence_paths"]),
            "route_resolution": normalized["route_resolution"],
            "callback_to": normalized["callback_to"],
            "source_ref": normalized.get("source_ref") or {},
            "target_ref": normalized.get("target_ref") or {},
            "ok": validation["ok"],
            "issues": validation["issues"],
        }
        if extra:
            row.update(dict(extra))
        self._append_jsonl(row)
        return row

    def append_summary_record(
        self,
        summary: Mapping[str, Any],
        *,
        status: str = "flushed",
        note: str = "",
    ) -> dict[str, Any]:
        row = {
            "recorded_at": _now_iso(),
            "record_type": "callback_summary_window",
            "status": status,
            "note": note,
            **dict(summary),
        }
        self._append_jsonl(row)
        return row

    def write_summary_snapshot(
        self,
        *,
        windows: Mapping[str, Any] | None = None,
        counters: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        snapshot = {
            "updated_at": _now_iso(),
            "windows": dict(windows or {}),
            "counters": dict(counters or {}),
        }
        if self.summary_json_path:
            self.summary_json_path.parent.mkdir(parents=True, exist_ok=True)
            self.summary_json_path.write_text(
                json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        return snapshot

    def _append_jsonl(self, row: Mapping[str, Any]) -> None:
        with self.ledger_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(dict(row), ensure_ascii=False) + "\n")


__all__ = [
    "CallbackDispatchLedger",
    "CallbackSummaryWindowBook",
    "DEFAULT_SUMMARY_WINDOW_S",
    "EVENT_TYPES",
    "INTERRUPT_REASONS",
    "SUMMARY_EVENT_TYPES",
    "build_callback_event_idempotency_key",
    "callback_summary_window_key",
    "normalize_message_ref",
    "normalize_callback_event_payload",
    "normalize_callback_target",
    "normalize_route_resolution",
    "validate_callback_event_payload",
]
