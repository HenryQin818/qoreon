from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .helpers import _find_project_cfg
from .session_store import session_binding_is_available

UUID_RE = re.compile(
    r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
    re.IGNORECASE,
)
ONE_DAY = timedelta(days=1)
DEFAULT_SESSION_HEALTH_INTERVAL_MINUTES = 120
MIN_SESSION_HEALTH_INTERVAL_MINUTES = 15
MAX_SESSION_HEALTH_INTERVAL_MINUTES = 1440


def _parse_iso(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _iso_local(value: datetime | None) -> str:
    if value is None:
        return ""
    return value.astimezone().isoformat(timespec="seconds")


def _hours_between(start: datetime | None, end: datetime | None) -> float | None:
    if start is None or end is None:
        return None
    return max(0.0, (end - start).total_seconds() / 3600.0)


def _days_between(start: datetime | None, end: datetime | None) -> float:
    if start is None or end is None:
        return 0.0
    return max(0.0, (end - start).total_seconds() / 86400.0)


def _round_mb(size_bytes: int) -> float:
    if size_bytes <= 0:
        return 0.0
    return round(size_bytes / (1024 * 1024), 2)


def _avg(values: list[float]) -> float | None:
    items = [float(v) for v in values if v is not None]
    if not items:
        return None
    return sum(items) / len(items)


def _token_usage_pct(info: Any) -> float | None:
    if not isinstance(info, dict):
        return None
    last_usage = info.get("last_token_usage")
    if not isinstance(last_usage, dict):
        return None
    try:
        total_tokens = float(last_usage.get("total_tokens") or 0.0)
        context_window = float(info.get("model_context_window") or 0.0)
    except (TypeError, ValueError):
        return None
    if total_tokens <= 0 or context_window <= 0:
        return None
    return round(total_tokens / context_window * 100.0, 1)


def _build_compaction_observations(
    timeline_events: list[dict[str, Any]],
    *,
    recent_limit: int = 5,
) -> tuple[list[dict[str, Any]], list[float]]:
    compact_events = [item for item in timeline_events if item.get("kind") == "compact"]
    token_events = [item for item in timeline_events if item.get("kind") == "token" and item.get("usage_pct") is not None]
    if not compact_events or not token_events:
        return [], []

    observations: list[dict[str, Any]] = []
    post_compact_values: list[float] = []
    seen_compact_keys: set[str] = set()
    for compact in compact_events:
        compact_ts = compact.get("timestamp")
        if compact_ts is None:
            continue
        compact_key = _iso_local(compact_ts)
        if compact_key in seen_compact_keys:
            continue
        seen_compact_keys.add(compact_key)
        before = None
        after = None
        for token in reversed(token_events):
            token_ts = token.get("timestamp")
            if token_ts is not None and token_ts <= compact_ts:
                before = token
                break
        for token in token_events:
            token_ts = token.get("timestamp")
            if token_ts is not None and token_ts >= compact_ts:
                after = token
                break
        before_pct = before.get("usage_pct") if isinstance(before, dict) else None
        after_pct = after.get("usage_pct") if isinstance(after, dict) else None
        if after_pct is not None:
            post_compact_values.append(float(after_pct))
        observations.append(
            {
                "compacted_at": _iso_local(compact_ts),
                "before_pct": before_pct,
                "after_pct": after_pct,
                "before_observed_at": _iso_local(before.get("timestamp")) if isinstance(before, dict) else "",
                "after_observed_at": _iso_local(after.get("timestamp")) if isinstance(after, dict) else "",
            }
        )
    observations = observations[-recent_limit:]
    return observations, post_compact_values


def _estimate_baseline_floor_pct(
    compacted_count: int,
    recent_compactions_24h: int,
    recent_compactions_7d: int,
    avg_turns_between_compactions: float | None,
    avg_hours_between_compactions: float | None,
    turns_since_last_compaction: int | None,
) -> tuple[int, list[str], bool]:
    if compacted_count <= 0:
        return 0, ["暂无 compact 记录"], False

    score = 22
    reasons: list[str] = []

    if recent_compactions_24h >= 6:
        score += 24
        reasons.append(f"24h压缩={recent_compactions_24h}")
    elif recent_compactions_24h >= 3:
        score += 18
        reasons.append(f"24h压缩={recent_compactions_24h}")
    elif recent_compactions_24h >= 1:
        score += 8
        reasons.append(f"24h压缩={recent_compactions_24h}")

    if avg_turns_between_compactions is not None:
        if avg_turns_between_compactions <= 8:
            score += 26
        elif avg_turns_between_compactions <= 20:
            score += 18
        elif avg_turns_between_compactions <= 40:
            score += 12
        elif avg_turns_between_compactions <= 80:
            score += 6
        reasons.append(f"压缩间推进={avg_turns_between_compactions:.0f}轮")

    if avg_hours_between_compactions is not None:
        if avg_hours_between_compactions <= 1:
            score += 18
        elif avg_hours_between_compactions <= 6:
            score += 14
        elif avg_hours_between_compactions <= 24:
            score += 8
        elif avg_hours_between_compactions <= 72:
            score += 4
        reasons.append(f"压缩间隔={avg_hours_between_compactions:.1f}h")

    if turns_since_last_compaction is not None:
        if turns_since_last_compaction <= 5:
            score += 12
        elif turns_since_last_compaction <= 15:
            score += 8
        elif turns_since_last_compaction <= 30:
            score += 4
        reasons.append(f"最近压缩后推进={turns_since_last_compaction}轮")

    if recent_compactions_7d >= 12:
        score += 8
    elif recent_compactions_7d >= 6:
        score += 5
    elif recent_compactions_7d >= 3:
        score += 2
    if recent_compactions_7d >= 3:
        reasons.append(f"7d压缩={recent_compactions_7d}")

    floor_pct = min(100, score)
    sustained_high_floor = (
        floor_pct >= 60
        and compacted_count >= 2
        and (
            recent_compactions_24h >= 2
            or (avg_turns_between_compactions is not None and avg_turns_between_compactions <= 20)
            or (turns_since_last_compaction is not None and turns_since_last_compaction <= 15)
        )
    )
    if sustained_high_floor:
        reasons.append("连续压缩后仍处高位")

    return floor_pct, reasons, sustained_high_floor


def _observed_baseline_floor(
    compaction_observations: list[dict[str, Any]],
) -> tuple[int | None, list[str], bool]:
    after_values = [
        float(item.get("after_pct"))
        for item in compaction_observations
        if item.get("after_pct") is not None
    ]
    if not after_values:
        return None, [], False
    baseline_floor_pct = int(round(min(after_values)))
    series_text = " / ".join(f"{int(round(value))}%" for value in after_values[-5:])
    reasons = [f"最近压缩后={series_text}"]
    latest = compaction_observations[-1]
    if latest.get("before_pct") is not None and latest.get("after_pct") is not None:
        reasons.append(
            f"最近一次={int(round(float(latest['before_pct'])))}%→{int(round(float(latest['after_pct'])))}%"
        )
    sustained_high_floor = len(after_values) >= 2 and min(after_values[-3:]) >= 60.0
    if sustained_high_floor:
        reasons.append("连续多次压缩后仍>=60%")
    return baseline_floor_pct, reasons, sustained_high_floor


def _baseline_band(
    baseline_floor_pct: int,
    sustained_high_floor: bool,
) -> tuple[str, str]:
    if sustained_high_floor and baseline_floor_pct >= 60:
        return "high", "高优先级轮换"
    if baseline_floor_pct >= 70:
        return "high", "建议轮换"
    if baseline_floor_pct >= 55:
        return "medium", "偏危险"
    if baseline_floor_pct > 35:
        return "medium", "可观察"
    return "low", "健康"


def _health_action(
    baseline_floor_pct: int,
    sustained_high_floor: bool,
) -> str:
    if sustained_high_floor and baseline_floor_pct >= 60:
        return "高优先级轮换"
    if baseline_floor_pct >= 70:
        return "建议立即重置"
    if baseline_floor_pct >= 55:
        return "建议准备轮换"
    return "继续观察"


def _coerce_interval_minutes(value: Any, default: int = DEFAULT_SESSION_HEALTH_INTERVAL_MINUTES) -> int:
    try:
        interval = int(value)
    except Exception:
        interval = int(default)
    interval = max(MIN_SESSION_HEALTH_INTERVAL_MINUTES, interval)
    interval = min(MAX_SESSION_HEALTH_INTERVAL_MINUTES, interval)
    return interval


def _pick_primary_project_id(project_ids: list[str]) -> str:
    cleaned = [str(item or "").strip() for item in project_ids if str(item or "").strip()]
    if not cleaned:
        return ""
    if "task_dashboard" in cleaned:
        return "task_dashboard"
    return cleaned[0]


def normalize_project_session_health_config(
    project_id: str,
    *,
    project_name: str = "",
    raw: Any = None,
) -> dict[str, Any]:
    obj = raw if isinstance(raw, dict) else {}
    configured = bool(obj)
    if "enabled" in obj:
        enabled = bool(obj.get("enabled"))
    else:
        enabled = True
    interval_minutes = _coerce_interval_minutes(obj.get("interval_minutes"))
    return {
        "project_id": str(project_id or "").strip(),
        "project_name": str(project_name or project_id).strip() or str(project_id or "").strip(),
        "enabled": bool(enabled),
        "interval_minutes": interval_minutes,
        "configured": configured,
    }


def load_project_session_health_config(project_id: str) -> dict[str, Any]:
    project = _find_project_cfg(project_id)
    pid = str(project.get("id") or project_id).strip()
    pname = str(project.get("name") or pid).strip() or pid
    raw = project.get("session_health") if isinstance(project, dict) else {}
    return normalize_project_session_health_config(
        pid,
        project_name=pname,
        raw=raw,
    )


def _find_codex_log_paths(session_id: str, log_index: dict[str, list[Path]]) -> list[Path]:
    paths = log_index.get(session_id, [])
    uniq: dict[str, Path] = {}
    for path in paths:
        uniq[str(path)] = path
    return sorted(uniq.values(), key=lambda item: str(item))


def index_codex_log_files(log_roots: list[Path]) -> dict[str, list[Path]]:
    out: dict[str, list[Path]] = {}
    for root in log_roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            name = path.name
            if ".jsonl" not in name:
                continue
            if ".jsonl.bak" in name:
                continue
            match = UUID_RE.search(name)
            if not match:
                continue
            out.setdefault(match.group(1), []).append(path)
    return out


def analyze_codex_session_logs(session_id: str, log_index: dict[str, list[Path]]) -> dict[str, Any]:
    paths = _find_codex_log_paths(session_id, log_index)
    metrics: dict[str, Any] = {
        "has_log": bool(paths),
        "log_paths": [str(path) for path in paths],
        "log_paths_count": len(paths),
        "log_size_bytes": 0,
        "log_size_mb": 0.0,
        "turn_context_count": 0,
        "compacted_count": 0,
        "first_event_at": "",
        "last_event_at": "",
        "last_compacted_at": "",
        "compaction_timestamps": [],
        "compaction_observations": [],
        "recent_after_usage_pcts": [],
        "last_after_usage_pct": None,
        "avg_turns_between_compactions": None,
        "avg_hours_between_compactions": None,
        "turns_since_last_compaction": None,
    }
    if not paths:
        return metrics

    first_event: datetime | None = None
    last_event: datetime | None = None
    last_compacted: datetime | None = None
    turn_context_count = 0
    compacted_count = 0
    size_bytes = 0
    compaction_timestamps: list[datetime] = []
    turns_between_compactions: list[int] = []
    hours_between_compactions: list[float] = []
    turns_since_last_compaction = 0
    seen_first_compaction = False
    timeline_events: list[dict[str, Any]] = []

    for path in paths:
        try:
            size_bytes += path.stat().st_size
        except OSError:
            continue
        try:
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    text = line.strip()
                    if not text:
                        continue
                    try:
                        event = json.loads(text)
                    except json.JSONDecodeError:
                        continue
                    ts = _parse_iso(event.get("timestamp"))
                    if ts is not None:
                        if first_event is None or ts < first_event:
                            first_event = ts
                        if last_event is None or ts > last_event:
                            last_event = ts
                    event_type = str(event.get("type") or "").strip()
                    if event_type == "turn_context":
                        turn_context_count += 1
                        if seen_first_compaction:
                            turns_since_last_compaction += 1
                    elif event_type == "compacted":
                        compacted_count += 1
                        if seen_first_compaction:
                            turns_between_compactions.append(turns_since_last_compaction)
                        turns_since_last_compaction = 0
                        seen_first_compaction = True
                        if ts is not None and (last_compacted is None or ts > last_compacted):
                            last_compacted = ts
                        if ts is not None:
                            if compaction_timestamps:
                                gap_hours = _hours_between(compaction_timestamps[-1], ts)
                                if gap_hours is not None:
                                    hours_between_compactions.append(gap_hours)
                            compaction_timestamps.append(ts)
                            timeline_events.append({"kind": "compact", "timestamp": ts})
                    elif event_type == "event_msg":
                        payload = event.get("payload")
                        if not isinstance(payload, dict):
                            continue
                        payload_type = str(payload.get("type") or "").strip()
                        if payload_type == "token_count":
                            usage_pct = _token_usage_pct(payload.get("info"))
                            if ts is not None and usage_pct is not None:
                                timeline_events.append({"kind": "token", "timestamp": ts, "usage_pct": usage_pct})
                        elif payload_type == "context_compacted":
                            compacted_count += 1
                            if seen_first_compaction:
                                turns_between_compactions.append(turns_since_last_compaction)
                            turns_since_last_compaction = 0
                            seen_first_compaction = True
                            if ts is not None and (last_compacted is None or ts > last_compacted):
                                last_compacted = ts
                            if ts is not None:
                                if compaction_timestamps:
                                    gap_hours = _hours_between(compaction_timestamps[-1], ts)
                                    if gap_hours is not None:
                                        hours_between_compactions.append(gap_hours)
                                compaction_timestamps.append(ts)
                                timeline_events.append({"kind": "compact", "timestamp": ts})
        except OSError:
            continue

    timeline_events.sort(key=lambda item: item.get("timestamp") or datetime.min.replace(tzinfo=timezone.utc))
    compaction_observations, post_compact_values = _build_compaction_observations(timeline_events)
    metrics["log_size_bytes"] = size_bytes
    metrics["log_size_mb"] = _round_mb(size_bytes)
    metrics["turn_context_count"] = turn_context_count
    metrics["compacted_count"] = compacted_count
    metrics["first_event_at"] = _iso_local(first_event)
    metrics["last_event_at"] = _iso_local(last_event)
    metrics["last_compacted_at"] = _iso_local(last_compacted)
    metrics["compaction_timestamps"] = [_iso_local(item) for item in compaction_timestamps]
    metrics["compaction_observations"] = compaction_observations
    metrics["recent_after_usage_pcts"] = [round(float(value), 1) for value in post_compact_values[-5:]]
    metrics["last_after_usage_pct"] = round(float(post_compact_values[-1]), 1) if post_compact_values else None
    metrics["avg_turns_between_compactions"] = round(_avg([float(v) for v in turns_between_compactions]) or 0.0, 1) if turns_between_compactions else None
    metrics["avg_hours_between_compactions"] = round(_avg(hours_between_compactions) or 0.0, 1) if hours_between_compactions else None
    metrics["turns_since_last_compaction"] = turns_since_last_compaction if seen_first_compaction else None
    return metrics


def build_session_health_page(
    projects_meta: list[dict[str, Any]],
    *,
    generated_at: str,
    task_page_link: str,
    overview_page_link: str,
    communication_page_link: str,
    agent_curtain_page_link: str,
    session_health_page_link: str,
    agent_directory_page_link: str = "",
    log_index: dict[str, list[Path]] | None = None,
) -> dict[str, Any]:
    generated_dt = _parse_iso(generated_at) or datetime.now().astimezone()
    log_index = dict(log_index or {})
    if not log_index:
        log_roots = [
            Path.home() / ".codex" / "sessions",
            Path.home() / ".codex" / "archived_sessions",
        ]
        log_index = index_codex_log_files(log_roots)

    sessions: list[dict[str, Any]] = []
    channel_groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    project_summaries: list[dict[str, Any]] = []
    deleted_skipped_count = 0
    project_ids: list[str] = []

    for project in projects_meta:
        project_id = str(project.get("id") or "").strip()
        if project_id:
            project_ids.append(project_id)
        project_name = str(project.get("name") or project_id).strip() or project_id
        session_health_cfg = normalize_project_session_health_config(
            project_id,
            project_name=project_name,
            raw=project.get("session_health_config") if isinstance(project.get("session_health_config"), dict) else project.get("session_health"),
        )
        channel_sessions = project.get("all_sessions")
        if not isinstance(channel_sessions, list) or not channel_sessions:
            channel_sessions = project.get("channel_sessions")
        if not isinstance(channel_sessions, list):
            continue
        project_rows: list[dict[str, Any]] = []
        for session in channel_sessions:
            if not isinstance(session, dict):
                continue
            if bool(session.get("is_deleted")):
                deleted_skipped_count += 1
                continue
            session_id = str(session.get("session_id") or "").strip()
            if not session_id:
                continue
            cli_type = str(session.get("cli_type") or "codex").strip() or "codex"
            base_row = {
                "project_id": project_id,
                "project_name": project_name,
                "channel_name": str(session.get("name") or "").strip(),
                "alias": str(session.get("alias") or "").strip(),
                "display_name": str(session.get("display_name") or session.get("displayName") or "").strip(),
                "display_name_source": str(session.get("display_name_source") or session.get("displayNameSource") or "").strip(),
                "codex_title": str(session.get("codex_title") or session.get("codexTitle") or "").strip(),
                "session_id": session_id,
                "cli_type": cli_type,
                "model": str(session.get("model") or "").strip(),
                "reasoning_effort": str(session.get("reasoning_effort") or "").strip(),
                "source": str(session.get("source") or "").strip(),
                "environment": str(session.get("environment") or "").strip(),
                "branch": str(session.get("branch") or "").strip(),
                "worktree_root": str(session.get("worktree_root") or "").strip(),
                "workdir": str(session.get("workdir") or "").strip(),
                "is_primary": bool(session.get("is_primary")),
                "session_role": str(session.get("session_role") or "").strip() or ("primary" if bool(session.get("is_primary")) else "child"),
                "status": str(session.get("status") or "").strip() or "active",
                "is_deleted": bool(session.get("is_deleted")),
                "created_at": str(session.get("created_at") or "").strip(),
                "last_used_at": str(session.get("last_used_at") or "").strip(),
            }

            if cli_type != "codex":
                base_row.update(
                    {
                        "supported": False,
                        "has_log": False,
                        "log_paths": [],
                        "log_paths_count": 0,
                        "log_size_bytes": 0,
                        "log_size_mb": 0.0,
                        "turn_context_count": 0,
                        "compacted_count": 0,
                        "first_event_at": "",
                        "last_event_at": "",
                        "last_compacted_at": "",
                        "age_days": 0.0,
                        "hours_since_last_compacted": None,
                        "risk_score": 0,
                        "risk_level": "unsupported",
                        "risk_reasons": ["仅支持 Codex 日志"],
                        "recent_compactions_24h": 0,
                        "recent_compactions_7d": 0,
                        "compaction_observations": [],
                        "recent_after_usage_pcts": [],
                        "last_after_usage_pct": None,
                        "baseline_floor_pct": 0,
                        "baseline_floor_reasons": ["仅支持 Codex 日志"],
                        "baseline_floor_status": "未支持",
                        "baseline_floor_estimated": False,
                        "baseline_floor_source": "unsupported",
                        "sustained_high_floor": False,
                        "health_action": "仅展示绑定",
                        "recent_compaction": False,
                    }
                )
                sessions.append(base_row)
                project_rows.append(base_row)
                channel_groups.setdefault((project_id, base_row["channel_name"]), []).append(base_row)
                continue

            metrics = analyze_codex_session_logs(session_id, log_index)
            compaction_timestamps = [_parse_iso(item) for item in metrics.get("compaction_timestamps") or []]
            created_at_dt = _parse_iso(base_row["created_at"]) or _parse_iso(metrics.get("first_event_at"))
            last_event_dt = _parse_iso(metrics.get("last_event_at")) or _parse_iso(base_row["last_used_at"])
            last_compacted_dt = _parse_iso(metrics.get("last_compacted_at"))
            age_days = _days_between(created_at_dt, generated_dt)
            recent_compaction = False
            if last_compacted_dt is not None:
                recent_compaction = generated_dt.astimezone() - last_compacted_dt.astimezone() <= ONE_DAY
            recent_compactions_24h = sum(
                1
                for ts in compaction_timestamps
                if ts is not None and generated_dt.astimezone() - ts.astimezone() <= ONE_DAY
            )
            recent_compactions_7d = sum(
                1
                for ts in compaction_timestamps
                if ts is not None and generated_dt.astimezone() - ts.astimezone() <= timedelta(days=7)
            )
            observed_floor_pct, observed_reasons, observed_sustained_high_floor = _observed_baseline_floor(
                metrics.get("compaction_observations") or []
            )
            if observed_floor_pct is not None:
                baseline_floor_pct = observed_floor_pct
                baseline_floor_reasons = observed_reasons
                sustained_high_floor = observed_sustained_high_floor
                baseline_floor_estimated = False
                baseline_floor_source = "observed"
            else:
                baseline_floor_pct, baseline_floor_reasons, sustained_high_floor = _estimate_baseline_floor_pct(
                    int(metrics.get("compacted_count") or 0),
                    recent_compactions_24h,
                    recent_compactions_7d,
                    float(metrics.get("avg_turns_between_compactions")) if metrics.get("avg_turns_between_compactions") is not None else None,
                    float(metrics.get("avg_hours_between_compactions")) if metrics.get("avg_hours_between_compactions") is not None else None,
                    int(metrics.get("turns_since_last_compaction")) if metrics.get("turns_since_last_compaction") is not None else None,
                )
                baseline_floor_estimated = True
                baseline_floor_source = "estimated"
            risk_level, baseline_floor_status = _baseline_band(
                baseline_floor_pct,
                sustained_high_floor,
            )
            base_row.update(metrics)
            base_row.update(
                {
                    "supported": True,
                    "age_days": round(age_days, 1),
                    "hours_since_last_compacted": _hours_between(last_compacted_dt, generated_dt),
                    "recent_compaction": recent_compaction,
                    "recent_compactions_24h": recent_compactions_24h,
                    "recent_compactions_7d": recent_compactions_7d,
                    "risk_score": baseline_floor_pct,
                    "risk_level": risk_level,
                    "risk_reasons": baseline_floor_reasons,
                    "baseline_floor_pct": baseline_floor_pct,
                    "baseline_floor_reasons": baseline_floor_reasons,
                    "baseline_floor_status": baseline_floor_status,
                    "baseline_floor_estimated": baseline_floor_estimated,
                    "baseline_floor_source": baseline_floor_source,
                    "sustained_high_floor": sustained_high_floor,
                    "health_action": _health_action(
                        baseline_floor_pct,
                        sustained_high_floor,
                    ),
                    "created_at_effective": _iso_local(created_at_dt),
                    "last_event_at_effective": _iso_local(last_event_dt),
                }
            )
            sessions.append(base_row)
            project_rows.append(base_row)
            channel_groups.setdefault((project_id, base_row["channel_name"]), []).append(base_row)

        supported_rows = [row for row in project_rows if row.get("supported")]
        project_summaries.append(
            {
                "project_id": project_id,
                "project_name": project_name,
                "session_count": len(project_rows),
                "high_risk_count": sum(1 for row in supported_rows if row.get("risk_level") == "high"),
                "medium_risk_count": sum(1 for row in supported_rows if row.get("risk_level") == "medium"),
                "recent_compaction_count": sum(1 for row in supported_rows if row.get("recent_compaction")),
                "session_health": session_health_cfg,
            }
        )

    supported_sessions = [row for row in sessions if row.get("supported")]
    risk_counts = {
        "high": sum(1 for row in supported_sessions if row.get("risk_level") == "high"),
        "medium": sum(1 for row in supported_sessions if row.get("risk_level") == "medium"),
        "low": sum(1 for row in supported_sessions if row.get("risk_level") == "low"),
    }
    compacted_sessions = [row for row in supported_sessions if int(row.get("compacted_count") or 0) > 0]
    recent_compaction_sessions = sorted(
        [row for row in supported_sessions if row.get("recent_compaction")],
        key=lambda row: (
            row.get("last_compacted_at") or "",
            int(row.get("baseline_floor_pct") or 0),
            int(row.get("compacted_count") or 0),
        ),
        reverse=True,
    )
    top_high_risk = sorted(
        [row for row in supported_sessions if row.get("risk_level") == "high"],
        key=lambda row: (
            int(row.get("baseline_floor_pct") or 0),
            int(row.get("compacted_count") or 0),
            int(row.get("recent_compactions_24h") or 0),
        ),
        reverse=True,
    )
    sessions_sorted = sorted(
        sessions,
        key=lambda row: (
            {"high": 3, "medium": 2, "low": 1, "unsupported": 0}.get(str(row.get("risk_level") or ""), 0),
            int(row.get("baseline_floor_pct") or 0),
            int(row.get("recent_compactions_24h") or 0),
            int(row.get("compacted_count") or 0),
            row.get("channel_name") or "",
        ),
        reverse=True,
    )

    multi_active_channels: list[dict[str, Any]] = []
    for (project_id, channel_name), rows in channel_groups.items():
        available_rows = [row for row in rows if session_binding_is_available(row)]
        if len(available_rows) <= 1:
            continue
        multi_active_channels.append(
            {
                "project_id": project_id,
                "project_name": available_rows[0].get("project_name") or project_id,
                "channel_name": channel_name,
                "active_session_count": len(available_rows),
                "high_risk_count": sum(1 for row in available_rows if row.get("risk_level") == "high"),
                "sessions": [
                    {
                        "alias": row.get("alias") or row.get("channel_name") or row.get("session_id"),
                        "session_id": row.get("session_id"),
                        "risk_level": row.get("risk_level"),
                        "baseline_floor_pct": row.get("baseline_floor_pct"),
                        "compacted_count": row.get("compacted_count"),
                        "is_primary": bool(row.get("is_primary")),
                    }
                    for row in sorted(
                        available_rows,
                        key=lambda item: (
                            int(item.get("baseline_floor_pct") or 0),
                            int(item.get("compacted_count") or 0),
                            int(item.get("recent_compactions_24h") or 0),
                        ),
                        reverse=True,
                    )
                ],
            }
        )
    multi_active_channels.sort(
        key=lambda row: (
            int(row.get("active_session_count") or 0),
            int(row.get("high_risk_count") or 0),
        ),
        reverse=True,
    )

    channel_load_rows = []
    for item in multi_active_channels[:8]:
        high_count = int(item.get("high_risk_count") or 0)
        active_count = int(item.get("active_session_count") or 0)
        channel_load_rows.append(
            {
                "label": str(item.get("channel_name") or "-"),
                "value": str(active_count),
                "percent": (high_count / active_count * 100.0) if active_count else 0.0,
                "note": f"高风险 {high_count} / 活动 {active_count}",
            }
        )

    total_supported = len(supported_sessions)
    sessions_with_logs = sum(1 for row in supported_sessions if row.get("has_log"))
    compacted_rate_pct = (len(compacted_sessions) / total_supported * 100.0) if total_supported else 0.0
    primary_project_id = _pick_primary_project_id(project_ids)
    primary_project_name = next(
        (
            str(item.get("project_name") or primary_project_id).strip() or primary_project_id
            for item in project_summaries
            if str(item.get("project_id") or "").strip() == primary_project_id
        ),
        primary_project_id,
    )
    primary_session_health_cfg = next(
        (
            dict(item.get("session_health") or {})
            for item in project_summaries
            if str(item.get("project_id") or "").strip() == primary_project_id
        ),
        normalize_project_session_health_config(primary_project_id, project_name=primary_project_name),
    )
    global_automation = {
        "project_count": len(project_summaries),
        "enabled_count": sum(
            1
            for item in project_summaries
            if bool((item.get("session_health") or {}).get("enabled"))
        ),
        "items": [
            {
                "project_id": str(item.get("project_id") or "").strip(),
                "project_name": str(item.get("project_name") or item.get("project_id") or "").strip(),
                "enabled": bool((item.get("session_health") or {}).get("enabled")),
                "interval_minutes": int((item.get("session_health") or {}).get("interval_minutes") or 0),
            }
            for item in project_summaries
        ],
    }

    return {
        "generated_at": generated_at,
        "project_id": primary_project_id,
        "project_name": primary_project_name,
        "title": "会话上下文健康看板",
        "subtitle": "主指标改成压缩后占用基线，优先看 compact 后还能不能明显降下来。",
        "live_sessions_endpoint": f"/api/sessions?project_id={primary_project_id}" if primary_project_id else "",
        "live_health_endpoint": f"/api/session-health?project_id={primary_project_id}" if primary_project_id else "",
        "session_health": primary_session_health_cfg,
        "global_automation": global_automation,
        "summary": {
            "project_count": len(project_summaries),
            "session_count": len(sessions),
            "codex_supported_count": total_supported,
            "sessions_with_logs": sessions_with_logs,
            "compacted_session_count": len(compacted_sessions),
            "compacted_rate_pct": round(compacted_rate_pct, 1),
            "recent_compaction_count": len(recent_compaction_sessions),
            "multi_active_channel_count": len(multi_active_channels),
            "deleted_skipped_count": deleted_skipped_count,
            "rotation_due_count": sum(
                1
                for row in supported_sessions
                if str(row.get("health_action") or "") in {"高优先级轮换", "建议立即重置", "建议准备轮换"}
            ),
            "risk_counts": risk_counts,
        },
        "thresholds": {
            "healthy": "<=35%",
            "observe": "35%-55%",
            "warning": "55%-70%",
            "rotate": ">=70%",
            "priority_rotate": "连续多次 compact 后仍 >=60%",
            "note": "优先展示日志实测的 compact 前后占用比例；缺少 token_count 时才退回节奏估算。",
        },
        "projects": project_summaries,
        "top_high_risk": top_high_risk[:8],
        "recent_compaction": recent_compaction_sessions[:12],
        "multi_active_channels": multi_active_channels,
        "channel_load_rows": channel_load_rows,
        "sessions": sessions_sorted,
        "links": {
            "task_page": task_page_link,
            "overview_page": overview_page_link,
            "communication_page": communication_page_link,
            "agent_curtain_page": agent_curtain_page_link,
            "session_health_page": session_health_page_link,
            "agent_directory_page": agent_directory_page_link,
        },
    }
