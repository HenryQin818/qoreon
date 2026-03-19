from __future__ import annotations

import json
import re
import secrets
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

from .session_store import SessionStore
from .utils import iter_channel_dirs

IN_PROGRESS_TASK_PATTERN = "【进行中】【任务】*.md"
UPDATED_AT_RE = re.compile(r"^\s*更新时间[：:]\s*(.+?)\s*$", re.MULTILINE)
_ALLOWED_CLI_TYPES = {"codex", "claude", "opencode", "gemini"}


def _now_local_iso() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _normalize_cli_type(raw: Any, *, default: str = "codex") -> str:
    s = str(raw or "").strip().lower()
    if s in _ALLOWED_CLI_TYPES:
        return s
    return str(default or "codex").strip().lower() or "codex"


def _parse_datetime(raw: str) -> datetime | None:
    s = str(raw or "").strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S %z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _to_iso(dt: datetime) -> str:
    return dt.astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")


def _minute_bucket_end(triggered_at: datetime, window_minutes: int) -> datetime:
    win = max(1, int(window_minutes or 1))
    minute = (triggered_at.minute // win) * win
    start = triggered_at.replace(minute=minute, second=0, microsecond=0)
    end = start + timedelta(minutes=win)
    return end


def _minute_bucket_start(triggered_at: datetime, window_minutes: int) -> datetime:
    end = _minute_bucket_end(triggered_at, window_minutes)
    return end - timedelta(minutes=max(1, int(window_minutes or 1)))


def _format_bucket_for_dedupe(dt: datetime) -> str:
    # Keep contract-style minute precision, no seconds.
    return dt.astimezone().strftime("%Y-%m-%dT%H:%M")


def _extract_updated_at(path: Path) -> datetime:
    text = _read_text(path)
    m = UPDATED_AT_RE.search(text)
    if m:
        dt = _parse_datetime(str(m.group(1) or ""))
        if dt is not None:
            return dt.astimezone()
    return datetime.fromtimestamp(path.stat().st_mtime).astimezone()


def scan_in_progress_tasks(
    *,
    task_root: Path,
    now_iso: str | None = None,
    stale_after_minutes: int = 120,
    escalate_after_minutes: int = 480,
    include_channels: Iterable[str] | None = None,
) -> dict[str, Any]:
    now_dt = _parse_datetime(now_iso or "") or datetime.now().astimezone()
    include_set = {str(x).strip() for x in (include_channels or []) if str(x).strip()}
    rows: list[dict[str, Any]] = []

    for channel_dir in iter_channel_dirs(task_root):
        channel_name = channel_dir.name
        if include_set and channel_name not in include_set:
            continue
        task_dir = channel_dir / "任务"
        if not task_dir.is_dir():
            continue
        for path in sorted(task_dir.glob(IN_PROGRESS_TASK_PATTERN)):
            updated_dt = _extract_updated_at(path)
            age_minutes = max(0, int((now_dt - updated_dt).total_seconds() // 60))
            stale = age_minutes >= max(0, int(stale_after_minutes or 0))
            escalated_candidate = age_minutes >= max(0, int(escalate_after_minutes or 0))
            rows.append(
                {
                    "task_path": str(path),
                    "channel_name": channel_name,
                    "updated_at": updated_dt.strftime("%Y-%m-%d %H:%M:%S %z"),
                    "age_minutes": age_minutes,
                    "stale": stale,
                    "escalated_candidate": escalated_candidate,
                }
            )

    stale_rows = [x for x in rows if bool(x.get("stale"))]
    escalated_rows = [x for x in stale_rows if bool(x.get("escalated_candidate"))]
    return {
        "scanned_at": _to_iso(now_dt),
        "checked_count": len(rows),
        "matched_count": len(stale_rows),
        "escalated_candidate_count": len(escalated_rows),
        "task_refs": rows,
        "stale_task_refs": stale_rows,
    }


def load_primary_session_targets(*, project_root: Path, project_id: str) -> dict[str, dict[str, str]]:
    mapping: dict[str, dict[str, str]] = {}
    store = SessionStore(project_root)
    for row in store.list_sessions(project_id):
        channel_name = str(row.get("channel_name") or row.get("channelName") or "").strip()
        session_id = str(row.get("id") or row.get("session_id") or row.get("sessionId") or "").strip()
        if not channel_name or not session_id or channel_name in mapping:
            continue
        cli_type = _normalize_cli_type(row.get("cli_type") or row.get("cliType"), default="codex")
        mapping[channel_name] = {
            "channel_name": channel_name,
            "session_id": session_id,
            "cli_type": cli_type,
        }
    return mapping


class ReminderEscalationState:
    """Persistent state machine for stale-task reminder/escalation tracking."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._state = self._load()

    def _load(self) -> dict[str, Any]:
        default = {"version": 1, "tasks": {}}
        if not self.path.exists():
            return default
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return default
        if not isinstance(raw, dict):
            return default
        tasks = raw.get("tasks")
        if not isinstance(tasks, dict):
            raw["tasks"] = {}
        raw["version"] = int(raw.get("version") or 1)
        return raw

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(self._state, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def evaluate_and_mark(
        self,
        *,
        task_refs: list[dict[str, Any]],
        now_iso: str,
        escalate_after_minutes: int,
    ) -> list[dict[str, Any]]:
        now_dt = _parse_datetime(now_iso) or datetime.now().astimezone()
        tasks_state = self._state.setdefault("tasks", {})
        active_keys: set[str] = set()
        out: list[dict[str, Any]] = []

        for ref in task_refs:
            row = dict(ref)
            task_path = str(row.get("task_path") or "").strip()
            if not task_path:
                out.append(row)
                continue
            key = task_path
            active_keys.add(key)
            entry = tasks_state.get(key)
            if not isinstance(entry, dict):
                entry = {
                    "first_stale_at": now_iso,
                    "last_seen_at": now_iso,
                    "last_reminded_at": "",
                    "last_escalated_at": "",
                    "escalated": False,
                }
            else:
                entry["last_seen_at"] = now_iso
                entry.setdefault("first_stale_at", now_iso)
                entry.setdefault("last_reminded_at", "")
                entry.setdefault("last_escalated_at", "")
                entry.setdefault("escalated", False)

            first_stale_dt = _parse_datetime(str(entry.get("first_stale_at") or "")) or now_dt
            stale_minutes = max(0, int((now_dt - first_stale_dt).total_seconds() // 60))
            should_escalate = stale_minutes >= max(0, int(escalate_after_minutes or 0))
            if should_escalate and not bool(entry.get("escalated")):
                entry["last_escalated_at"] = now_iso
            entry["escalated"] = bool(should_escalate)
            tasks_state[key] = entry

            row["stale_since_at"] = str(entry.get("first_stale_at") or "")
            row["stale_duration_minutes"] = stale_minutes
            row["escalated"] = bool(entry.get("escalated"))
            row["last_escalated_at"] = str(entry.get("last_escalated_at") or "")
            out.append(row)

        # Best-effort GC: drop entries no longer stale for > 7d is overkill; for V1 drop absent keys immediately.
        for key in list(tasks_state.keys()):
            if key not in active_keys:
                tasks_state.pop(key, None)
        self.save()
        return out

    def mark_reminded(self, *, task_paths: Iterable[str], reminded_at_iso: str) -> None:
        tasks_state = self._state.setdefault("tasks", {})
        for task_path in task_paths:
            key = str(task_path or "").strip()
            if not key:
                continue
            entry = tasks_state.get(key)
            if not isinstance(entry, dict):
                continue
            entry["last_reminded_at"] = reminded_at_iso
            entry["last_seen_at"] = reminded_at_iso
        self.save()


class ReminderDedupeLedger:
    """JSONL-first reminder record ledger for dedupe and replay."""

    def __init__(self, jsonl_path: Path) -> None:
        self.jsonl_path = Path(jsonl_path)
        self.jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        self._seen_keys: set[str] = set()
        if self.jsonl_path.exists():
            self._load_seen()

    def _load_seen(self) -> None:
        try:
            with self.jsonl_path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    key = str(row.get("dedupe_key") or "").strip()
                    status = str(row.get("status") or "").strip()
                    if key and status in {"queued", "sent", "partial", "skipped"}:
                        self._seen_keys.add(key)
        except Exception:
            return

    def seen(self, dedupe_key: str) -> bool:
        return str(dedupe_key or "").strip() in self._seen_keys

    def append_record(self, record: Mapping[str, Any]) -> None:
        row = dict(record)
        self.jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        with self.jsonl_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        key = str(row.get("dedupe_key") or "").strip()
        status = str(row.get("status") or "").strip()
        if key and status in {"queued", "sent", "partial", "skipped"}:
            self._seen_keys.add(key)


def build_in_progress_reminder_events(
    *,
    project_id: str,
    stale_task_refs: list[dict[str, Any]],
    triggered_at_iso: str,
    target_map: Mapping[str, Mapping[str, Any]],
    summary_window_minutes: int = 5,
    trigger_reason: str = "stale_in_progress",
    escalate_to_channel: str = "主体-总控（合并与验收）",
) -> list[dict[str, Any]]:
    triggered_at = _parse_datetime(triggered_at_iso) or datetime.now().astimezone()
    bucket_start = _minute_bucket_start(triggered_at, summary_window_minutes)
    bucket_end = _minute_bucket_end(triggered_at, summary_window_minutes)

    groups: dict[str, list[dict[str, Any]]] = {}
    for ref in stale_task_refs:
        channel_name = str(ref.get("channel_name") or "").strip()
        if not channel_name:
            continue
        groups.setdefault(channel_name, []).append(dict(ref))

    events: list[dict[str, Any]] = []
    for idx, (channel_name, refs) in enumerate(sorted(groups.items()), start=1):
        target = dict(target_map.get(channel_name) or {})
        session_id = str(target.get("session_id") or "").strip()
        cli_type = str(target.get("cli_type") or "").strip().lower()
        if cli_type and cli_type not in _ALLOWED_CLI_TYPES:
            cli_type = ""
        if not cli_type and session_id:
            cli_type = "codex"
        target_obj = {
            "channel_name": channel_name,
            "session_id": session_id,
            # Additive V1-compatible field for multi-CLI reminder dispatch routing.
            "cli_type": cli_type,
        }
        task_refs = [
            {
                "task_path": str(r.get("task_path") or ""),
                "channel_name": channel_name,
                "updated_at": str(r.get("updated_at") or ""),
                "age_minutes": int(r.get("age_minutes") or 0),
                "stale_duration_minutes": int(r.get("stale_duration_minutes") or r.get("age_minutes") or 0),
                "escalated": bool(r.get("escalated")),
            }
            for r in sorted(refs, key=lambda x: str(x.get("task_path") or ""))
        ]
        escalated_count = sum(1 for r in task_refs if bool(r.get("escalated")))
        matched_count = len(task_refs)
        missing_session = 0 if target_obj["session_id"] else 1
        # 12-4 contract example uses trigger minute as dedupe slot (not window_end).
        dedupe_key = (
            f"{project_id}|in_progress_reminder|{channel_name}|"
            f"{_format_bucket_for_dedupe(triggered_at)}"
        )
        event_id = (
            f"rem-evt-{triggered_at.astimezone().strftime('%Y%m%d-%H%M%S')}-"
            f"{idx:02d}-{secrets.token_hex(2)}"
        )
        events.append(
            {
                "event_id": event_id,
                "event_type": "in_progress_reminder",
                "project_id": project_id,
                "triggered_at": _to_iso(triggered_at),
                "trigger_reason": trigger_reason,
                "dedupe_key": dedupe_key,
                "window_start_at": _to_iso(bucket_start),
                "window_end_at": _to_iso(bucket_end),
                "targets": [target_obj],
                "task_refs": task_refs,
                "stats": {
                    "matched_count": matched_count,
                    "escalated_count": escalated_count,
                    "missing_session_target_count": missing_session,
                },
                "escalation": {
                    "escalated": escalated_count > 0,
                    "escalate_to_channel": escalate_to_channel if escalated_count > 0 else "",
                    "escalate_reason": "stale_over_threshold" if escalated_count > 0 else "",
                },
            }
        )
    return events


def build_reminder_message_summary(event: Mapping[str, Any]) -> str:
    stats = event.get("stats") if isinstance(event, Mapping) else {}
    stats = stats if isinstance(stats, Mapping) else {}
    matched = int(stats.get("matched_count") or 0)
    escalated = int(stats.get("escalated_count") or 0)
    if escalated > 0:
        return f"项目级例行提醒：发现 {matched} 项进行中任务，其中 {escalated} 项超过升级阈值"
    return f"项目级例行提醒：发现 {matched} 项进行中任务超过阈值"


def build_reminder_record(
    *,
    event: Mapping[str, Any],
    status: str = "queued",
    created_at_iso: str | None = None,
    delivery_results: list[dict[str, Any]] | None = None,
    error: str = "",
    feedback_file_path: str = "",
) -> dict[str, Any]:
    created_at = created_at_iso or _now_local_iso()
    event_id = str(event.get("event_id") or "").strip()
    record_id = f"rem-rec-{datetime.now().astimezone().strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(2)}"
    targets = event.get("targets")
    task_refs = event.get("task_refs")
    stats = event.get("stats")
    target_rows = []
    if isinstance(targets, list):
        for t in targets:
            if not isinstance(t, Mapping):
                continue
            target_rows.append(
                {
                    "channel_name": str(t.get("channel_name") or ""),
                    "session_id": str(t.get("session_id") or ""),
                    "cli_type": _normalize_cli_type(t.get("cli_type"), default="codex")
                    if str(t.get("session_id") or "").strip()
                    else str(t.get("cli_type") or ""),
                    "result": str(t.get("result") or ""),
                }
            )
    return {
        "record_id": record_id,
        "event_id": event_id,
        "project_id": str(event.get("project_id") or ""),
        "status": str(status or "queued"),
        "created_at": created_at,
        "updated_at": created_at,
        "dedupe_key": str(event.get("dedupe_key") or ""),
        "delivery_targets": target_rows,
        "delivery_results": list(delivery_results or []),
        "message_summary": build_reminder_message_summary(event),
        "task_refs": list(task_refs or []),
        "stats": dict(stats or {}) if isinstance(stats, Mapping) else {},
        "feedback_file_path": str(feedback_file_path or ""),
        "error": str(error or ""),
    }


def _normalize_api_base(api_base: str) -> str:
    return str(api_base or "").strip().rstrip("/")


def _http_json(
    *,
    method: str,
    url: str,
    payload: Mapping[str, Any] | None = None,
    token: str = "",
    timeout_s: float = 5.0,
) -> dict[str, Any]:
    body: bytes | None = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(dict(payload), ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    if token:
        headers["X-TaskDashboard-Token"] = token
    req = urllib_request.Request(url=url, data=body, method=method.upper(), headers=headers)
    with urllib_request.urlopen(req, timeout=timeout_s) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    if not raw.strip():
        return {}
    data = json.loads(raw)
    return data if isinstance(data, dict) else {"data": data}


def fetch_project_auto_scheduler_status(
    *,
    api_base: str,
    project_id: str,
    token: str = "",
    timeout_s: float = 5.0,
) -> dict[str, Any]:
    base = _normalize_api_base(api_base)
    pid = urllib_parse.quote(str(project_id or "").strip(), safe="")
    data = _http_json(
        method="GET",
        url=f"{base}/api/projects/{pid}/auto-scheduler",
        token=token,
        timeout_s=timeout_s,
    )
    status = data.get("status")
    return dict(status) if isinstance(status, Mapping) else {}


def fetch_primary_session_target_via_api(
    *,
    api_base: str,
    project_id: str,
    channel_name: str,
    token: str = "",
    timeout_s: float = 5.0,
) -> dict[str, str]:
    base = _normalize_api_base(api_base)
    qs = urllib_parse.urlencode({"project_id": project_id, "channel_name": channel_name})
    data = _http_json(method="GET", url=f"{base}/api/sessions?{qs}", token=token, timeout_s=timeout_s)
    sessions = data.get("sessions")
    rows = sessions if isinstance(sessions, list) else []
    chosen: Mapping[str, Any] | None = None
    for row in rows:
        if isinstance(row, Mapping) and bool(row.get("is_primary") or row.get("isPrimary")):
            chosen = row
            break
    if chosen is None:
        for row in rows:
            if isinstance(row, Mapping):
                chosen = row
                break
    chosen = chosen or {}
    return {
        "channel_name": str(chosen.get("channel_name") or chosen.get("channelName") or channel_name or "").strip(),
        "session_id": str(chosen.get("session_id") or chosen.get("sessionId") or "").strip(),
        "cli_type": str(chosen.get("cli_type") or chosen.get("cliType") or "codex").strip() or "codex",
    }


def build_in_progress_reminder_message(event: Mapping[str, Any]) -> str:
    lines = [build_reminder_message_summary(event)]
    task_refs = event.get("task_refs")
    if isinstance(task_refs, list):
        preview = []
        for row in task_refs[:3]:
            if not isinstance(row, Mapping):
                continue
            p = str(row.get("task_path") or "")
            age = int(row.get("age_minutes") or 0)
            mark = " [升级]" if bool(row.get("escalated")) else ""
            preview.append(f"- {p}（{age}分钟）{mark}".rstrip())
        if preview:
            lines.append("")
            lines.extend(preview)
        remain = max(0, len(task_refs) - len(preview))
        if remain > 0:
            lines.append(f"- 其余 {remain} 项见台账记录")
    escalation = event.get("escalation")
    if isinstance(escalation, Mapping) and bool(escalation.get("escalated")):
        esc_to = str(escalation.get("escalate_to_channel") or "").strip()
        if esc_to:
            lines.append("")
            lines.append(f"升级提示：存在超阈值任务，请同步关注（升级通道：{esc_to}）")
    return "\n".join(lines).strip()


def dispatch_reminder_event_via_ccb(
    *,
    api_base: str,
    event: Mapping[str, Any],
    token: str = "",
    timeout_s: float = 10.0,
    sender_type: str = "system",
    sender_id: str = "system",
    sender_name: str = "系统",
) -> dict[str, Any]:
    base = _normalize_api_base(api_base)
    targets = event.get("targets")
    target_rows = targets if isinstance(targets, list) else []
    message = build_in_progress_reminder_message(event)
    now_iso = _now_local_iso()
    results: list[dict[str, Any]] = []
    errors: list[str] = []
    success_count = 0
    skipped_count = 0
    error_count = 0

    for row in target_rows:
        t = row if isinstance(row, Mapping) else {}
        channel_name = str(t.get("channel_name") or t.get("channelName") or "").strip()
        session_id = str(t.get("session_id") or t.get("sessionId") or "").strip()
        target_cli_type_raw = str(t.get("cli_type") or t.get("cliType") or "").strip().lower()
        target_cli_type = target_cli_type_raw if target_cli_type_raw in _ALLOWED_CLI_TYPES else ""
        if not session_id:
            skipped_count += 1
            results.append(
                {
                    "channel_name": channel_name,
                    "session_id": "",
                    "status": "skipped",
                    "error": "no_primary_session",
                    "run_id": "",
                    "cli_type": target_cli_type,
                }
            )
            continue
        payload = {
            "projectId": str(event.get("project_id") or ""),
            "channelName": channel_name,
            "sessionId": session_id,
            "message": message,
            "sender_type": sender_type,
            "sender_id": sender_id,
            "sender_name": sender_name,
        }
        # V1 reminder multi-CLI compatibility: explicitly pass cliType when target provides it.
        # Server-side announce still keeps session binding as higher priority.
        if target_cli_type:
            payload["cliType"] = target_cli_type
        try:
            data = _http_json(
                method="POST",
                url=f"{base}/api/codex/announce",
                payload=payload,
                token=token,
                timeout_s=timeout_s,
            )
            run = data.get("run")
            run_obj = run if isinstance(run, Mapping) else {}
            run_id = str(run_obj.get("id") or data.get("runId") or "").strip()
            cli_type = str(run_obj.get("cliType") or payload.get("cliType") or "").strip()
            if run_id:
                success_count += 1
            else:
                # treat missing run id as send-side error; response is not useful for tracking.
                error_count += 1
                errors.append(f"{channel_name}:missing_run_id")
            results.append(
                {
                    "channel_name": channel_name,
                    "session_id": session_id,
                    "status": "queued" if run_id else "error",
                    "error": "" if run_id else "missing_run_id",
                    "run_id": run_id,
                    "cli_type": cli_type or target_cli_type,
                }
            )
        except urllib_error.HTTPError as e:
            error_count += 1
            msg = f"http_{e.code}"
            errors.append(f"{channel_name}:{msg}")
            results.append(
                {
                    "channel_name": channel_name,
                    "session_id": session_id,
                    "status": "error",
                    "error": msg,
                    "run_id": "",
                    "cli_type": target_cli_type,
                }
            )
        except Exception as e:
            error_count += 1
            msg = _safe_error_code(e)
            errors.append(f"{channel_name}:{msg}")
            results.append(
                {
                    "channel_name": channel_name,
                    "session_id": session_id,
                    "status": "error",
                    "error": msg,
                    "run_id": "",
                    "cli_type": target_cli_type,
                }
            )

    if success_count > 0 and error_count == 0 and skipped_count == 0:
        status = "queued"
    elif success_count == 0 and error_count == 0 and skipped_count > 0:
        status = "skipped"
    elif success_count == 0 and error_count > 0 and skipped_count == 0:
        status = "error"
    else:
        status = "partial"

    record = build_reminder_record(
        event=event,
        status=status,
        created_at_iso=now_iso,
        delivery_results=results,
        error=";".join(errors),
        feedback_file_path="",
    )
    record["updated_at"] = _now_local_iso()
    if isinstance(record.get("stats"), dict):
        record["stats"]["delivery_success_count"] = success_count
        record["stats"]["delivery_error_count"] = error_count
        record["stats"]["delivery_skipped_count"] = skipped_count
    return record


def _safe_error_code(exc: Exception) -> str:
    name = exc.__class__.__name__.lower()
    if "timeout" in name:
        return "timeout"
    if "url" in name or "http" in name:
        return "network_error"
    return "send_error"


__all__ = [
    "IN_PROGRESS_TASK_PATTERN",
    "ReminderDedupeLedger",
    "ReminderEscalationState",
    "build_in_progress_reminder_message",
    "build_in_progress_reminder_events",
    "build_reminder_message_summary",
    "build_reminder_record",
    "dispatch_reminder_event_via_ccb",
    "fetch_primary_session_target_via_api",
    "fetch_project_auto_scheduler_status",
    "load_primary_session_targets",
    "scan_in_progress_tasks",
]
