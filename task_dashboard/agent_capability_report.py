from __future__ import annotations

import json
import re
import subprocess
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .communication_audit import audit_communication_patterns
from .sender_identity_audit import audit_run_sender_integrity


HOT_RUNS_REL = Path(".runtime/stable/.runs/hot")
PERFORMANCE_DOC_REL = Path("docs/public/performance-diagnostics.md")
UTF8_HEADER_ERROR_PATTERN = "failed to convert header to a str for header name 'x-codex-turn-metadata'"
PRIMARY_PROJECT_ID = "task_dashboard"


def _as_str(value: Any) -> str:
    return "" if value is None else str(value)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _pct(part: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round((float(part) / float(total)) * 100.0, 1)


def _fmt_int(value: Any) -> str:
    try:
        return f"{int(value):,}"
    except Exception:
        return "0"


def _fmt_pct(value: Any) -> str:
    try:
        return f"{float(value):.1f}%"
    except Exception:
        return "0.0%"


def _fmt_score(value: int) -> str:
    return f"{max(0, min(100, int(value))):d}/100"


def _parse_created_at(value: Any) -> datetime | None:
    text = _as_str(value).strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%dT%H:%M:%S%z")
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        pass
    match = re.match(r"^(\d{4})(\d{2})(\d{2})-", text)
    if not match:
        return None
    return datetime(
        int(match.group(1)),
        int(match.group(2)),
        int(match.group(3)),
    ).astimezone()


def _read_json_dict(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_log_head(path: Path, max_bytes: int = 32_768) -> str:
    try:
        with path.open("rb") as handle:
            data = handle.read(max_bytes)
    except Exception:
        return ""
    return data.decode("utf-8", errors="replace")


def _git_stdout(repo_root: Path, *args: str) -> str:
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), *args],
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:
        return ""
    if proc.returncode != 0:
        return ""
    return _as_str(proc.stdout).strip()


def _load_hot_rows(runs_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(runs_dir.glob("*.json")):
        row = _read_json_dict(path)
        if not row or bool(row.get("hidden")):
            continue
        rows.append(row)
    fallback_dt = datetime(1970, 1, 1).astimezone()
    rows.sort(
        key=lambda row: (
            _parse_created_at(row.get("createdAt")) or fallback_dt,
            _as_str(row.get("id")),
        )
    )
    return rows


def _count_utf8_header_errors(rows: list[dict[str, Any]]) -> int:
    count = 0
    for row in rows:
        paths = _as_dict(row.get("paths"))
        log_path_text = _as_str(paths.get("log")).strip()
        if not log_path_text:
            continue
        log_path = Path(log_path_text)
        if not log_path.exists():
            continue
        if UTF8_HEADER_ERROR_PATTERN in _read_log_head(log_path):
            count += 1
    return count


def _scan_route_mismatch(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = 0
    target_matches_callback = 0
    cross_session_callback_match = 0
    for row in rows:
        communication_view = _as_dict(row.get("communication_view"))
        callback_to = _as_dict(row.get("callback_to"))
        if not communication_view or not bool(communication_view.get("route_mismatch")):
            continue
        total += 1
        source_session_id = _as_str(communication_view.get("source_session_id")).strip()
        target_session_id = _as_str(communication_view.get("target_session_id")).strip()
        callback_session_id = _as_str(callback_to.get("session_id")).strip()
        if callback_session_id and target_session_id == callback_session_id:
            target_matches_callback += 1
            if source_session_id and source_session_id != callback_session_id:
                cross_session_callback_match += 1
    return {
        "route_mismatch_runs": total,
        "target_matches_callback_to": target_matches_callback,
        "target_matches_callback_to_rate_pct": _pct(target_matches_callback, total),
        "cross_session_callback_match_runs": cross_session_callback_match,
        "cross_session_callback_match_rate_pct": _pct(cross_session_callback_match, total),
    }


def _current_project_channel_stats(projects_meta: list[dict[str, Any]]) -> dict[str, Any]:
    current = next(
        (
            project
            for project in projects_meta
            if _as_str(project.get("id")).strip() == PRIMARY_PROJECT_ID
        ),
        {},
    )
    channel_sessions = [
        row for row in _as_list(current.get("channel_sessions")) if isinstance(row, dict)
    ]
    total_channels = len(
        {
            _as_str(row.get("name") or row.get("channel_name")).strip()
            for row in channel_sessions
            if _as_str(row.get("name") or row.get("channel_name")).strip()
        }
    )
    active_channels = len(
        {
            _as_str(row.get("name") or row.get("channel_name")).strip()
            for row in channel_sessions
            if _as_str(row.get("status")).strip() == "active"
            and _as_str(row.get("name") or row.get("channel_name")).strip()
        }
    )
    primary_active_channels = len(
        {
            _as_str(row.get("name") or row.get("channel_name")).strip()
            for row in channel_sessions
            if _as_str(row.get("status")).strip() == "active"
            and bool(row.get("is_primary"))
            and _as_str(row.get("name") or row.get("channel_name")).strip()
        }
    )
    return {
        "project_name": _as_str(current.get("name")).strip() or "Qoreon·生产主项目",
        "total_channels": total_channels,
        "active_channels": active_channels,
        "primary_active_channels": primary_active_channels,
        "active_channel_rate_pct": _pct(active_channels, total_channels),
        "primary_active_channel_rate_pct": _pct(primary_active_channels, total_channels),
    }


def _project_session_summary(session_health_page_data: dict[str, Any]) -> dict[str, Any]:
    for row in _as_list(session_health_page_data.get("projects")):
        if not isinstance(row, dict):
            continue
        if _as_str(row.get("project_id")).strip() == PRIMARY_PROJECT_ID:
            return row
    return {}


def _performance_snapshot(script_dir: Path) -> dict[str, Any]:
    doc_path = (script_dir / PERFORMANCE_DOC_REL).resolve()
    text = doc_path.read_text(encoding="utf-8") if doc_path.exists() else ""

    def grab(pattern: str) -> float:
        match = re.search(pattern, text)
        if not match:
            return 0.0
        try:
            return float(match.group(1))
        except Exception:
            return 0.0

    return {
        "doc_path": str(doc_path),
        "session_detail_avg_s": grab(r"`session_detail`\s+平均\s+`([\d.]+)s`"),
        "sessions_list_avg_s": grab(r"`sessions_list`\s+平均\s+`([\d.]+)s`"),
        "sessions_list_max_s": grab(r"`sessions_list`\s+平均\s+`[\d.]+s`，最大\s+`([\d.]+)s`"),
        "runs_avg_s": grab(r"`runs`\s+平均\s+`([\d.]+)s`"),
    }


def _window_stats(rows: list[dict[str, Any]], *, days: int = 7) -> dict[str, Any]:
    now = datetime.now().astimezone()
    start = now - timedelta(days=max(1, int(days)))
    subset: list[dict[str, Any]] = []
    for row in rows:
        created_at = _parse_created_at(row.get("createdAt"))
        if created_at and created_at >= start:
            subset.append(row)

    sender_counts = Counter(_as_str(row.get("sender_type")).strip() or "(empty)" for row in subset)
    status_counts = Counter(_as_str(row.get("status")).strip() or "(empty)" for row in subset)
    sessions = {
        _as_str(row.get("sessionId")).strip()
        for row in subset
        if _as_str(row.get("sessionId")).strip()
    }
    channels = {
        _as_str(row.get("channelName")).strip()
        for row in subset
        if _as_str(row.get("channelName")).strip()
    }
    project_counts = Counter(
        _as_str(row.get("projectId") or row.get("project_id")).strip() or "(empty)"
        for row in subset
    )
    day_counter: Counter[str] = Counter()
    day_error_counter: Counter[str] = Counter()
    for row in subset:
        created_at = _parse_created_at(row.get("createdAt"))
        if not created_at:
            continue
        day_key = created_at.astimezone().strftime("%m-%d")
        day_counter[day_key] += 1
        if _as_str(row.get("status")).strip() == "error":
            day_error_counter[day_key] += 1

    ordered_days: list[dict[str, Any]] = []
    max_count = max(day_counter.values()) if day_counter else 1
    for offset in range(max(1, int(days))):
        current = (start + timedelta(days=offset + 1)).astimezone()
        key = current.strftime("%m-%d")
        count = int(day_counter.get(key) or 0)
        ordered_days.append(
            {
                "label": key,
                "count": count,
                "value": _fmt_int(count),
                "percent": round((count / max_count) * 100.0, 1) if max_count else 0.0,
                "note": f"error {int(day_error_counter.get(key) or 0)}",
            }
        )

    total = len(subset)
    return {
        "days": days,
        "runs": total,
        "done_count": int(status_counts.get("done") or 0),
        "error_count": int(status_counts.get("error") or 0),
        "running_count": int(status_counts.get("running") or 0),
        "active_sessions": len(sessions),
        "active_channels": len(channels),
        "sender_counts": sender_counts,
        "status_counts": status_counts,
        "project_counts": project_counts,
        "daily_rows": ordered_days,
        "done_rate_pct": _pct(int(status_counts.get("done") or 0), total),
        "error_rate_pct": _pct(int(status_counts.get("error") or 0), total),
    }


def _top_counter_rows(counter: Counter[str], *, total: int, limit: int = 6) -> list[dict[str, Any]]:
    rows = counter.most_common(max(1, int(limit)))
    out: list[dict[str, Any]] = []
    for name, count in rows:
        out.append(
            {
                "label": _as_str(name).strip() or "-",
                "value": _fmt_int(count),
                "percent": _pct(int(count), total),
                "note": "",
            }
        )
    return out


def _speed_score(value: float, *, healthy_s: float, bad_s: float) -> float:
    if value <= 0:
        return 1.0
    if value <= healthy_s:
        return 1.0
    if value >= bad_s:
        return 0.0
    span = max(0.1, bad_s - healthy_s)
    return max(0.0, min(1.0, 1.0 - ((value - healthy_s) / span)))


def _grade(score: int) -> tuple[str, str]:
    if score >= 85:
        return "健康", "good"
    if score >= 70:
        return "可用", "accent"
    if score >= 55:
        return "需关注", "warn"
    return "需优化", "danger"


def _build_metric(label: str, value: str, note: str = "") -> dict[str, str]:
    return {"label": label, "value": value, "note": note}


def build_agent_capability_report_page_data(
    script_dir: Path,
    *,
    generated_at: str,
    dashboard: dict[str, Any],
    links: dict[str, Any],
    projects_meta: list[dict[str, Any]],
    session_health_page_data: dict[str, Any],
    agent_capability_page_link: str,
    performance_page_link: str,
) -> dict[str, Any]:
    repo_root = script_dir
    runs_dir = (repo_root / HOT_RUNS_REL).resolve()
    rows = _load_hot_rows(runs_dir)
    audit = audit_communication_patterns(runs_dirs=[runs_dir], response_window_hours=2.0, top_limit=8, include_hidden=False)
    sender_audit = audit_run_sender_integrity(runs_dir=runs_dir, max_detail_items=8, include_hidden=False)
    recent = _window_stats(rows, days=7)
    primary_channel_stats = _current_project_channel_stats(projects_meta)
    primary_session_summary = _project_session_summary(session_health_page_data)
    perf = _performance_snapshot(script_dir)
    route_scan = _scan_route_mismatch(rows)
    utf8_error_count = _count_utf8_header_errors(rows)

    session_summary = _as_dict(session_health_page_data.get("summary"))
    total_supported_sessions = int(session_summary.get("codex_supported_count") or 0)
    sender_checked = int(sender_audit.get("checked_runs") or 0)
    sender_pass = int(sender_audit.get("pass_count") or 0)
    sender_integrity_rate = (float(sender_pass) / float(sender_checked)) if sender_checked else 0.0
    communication_view_rate = float(_as_dict(audit.get("rates")).get("communication_view_rate_pct") or 0.0) / 100.0
    route_mismatch_rate = float(_as_dict(audit.get("rates")).get("route_mismatch_rate_pct") or 0.0) / 100.0
    automation_enabled = int(_as_dict(session_health_page_data.get("global_automation")).get("enabled_count") or 0)
    automation_projects = int(_as_dict(session_health_page_data.get("global_automation")).get("project_count") or 0)
    automation_rate = (float(automation_enabled) / float(automation_projects)) if automation_projects else 0.0
    active_session_rate = (float(recent.get("active_sessions") or 0) / float(total_supported_sessions)) if total_supported_sessions else 0.0
    active_channel_rate = float(primary_channel_stats.get("active_channel_rate_pct") or 0.0) / 100.0
    primary_channel_rate = float(primary_channel_stats.get("primary_active_channel_rate_pct") or 0.0) / 100.0
    done_rate_7d = float(recent.get("done_rate_pct") or 0.0) / 100.0
    error_rate_7d = float(recent.get("error_rate_pct") or 0.0) / 100.0
    stability_rate = max(0.0, min(1.0, 1.0 - error_rate_7d))
    speed_score = (
        _speed_score(float(perf.get("session_detail_avg_s") or 0.0), healthy_s=3.0, bad_s=18.0)
        + _speed_score(float(perf.get("sessions_list_avg_s") or 0.0), healthy_s=1.5, bad_s=15.0)
        + _speed_score(float(perf.get("runs_avg_s") or 0.0), healthy_s=1.0, bad_s=10.0)
    ) / 3.0
    adjusted_route_health = max(0.0, min(1.0, 1.0 - (route_mismatch_rate * 0.5)))
    degrade_rows = _as_list(audit.get("top_degrade_reasons"))
    callback_invalid = next((int(row.get("count") or 0) for row in degrade_rows if _as_str(row.get("name")).strip() == "callback_to_invalid"), 0)
    sender_unresolved = next((int(row.get("count") or 0) for row in degrade_rows if _as_str(row.get("name")).strip() == "sender_agent_unresolved"), 0)
    degrade_pool = int(_as_dict(audit.get("totals")).get("communication_view_runs") or 0) or 1
    degrade_health = max(0.0, min(1.0, 1.0 - ((callback_invalid + sender_unresolved) / float(degrade_pool))))

    business_score = round((0.35 * active_session_rate + 0.35 * done_rate_7d + 0.30 * active_channel_rate) * 100.0)
    function_score = round((0.35 * sender_integrity_rate + 0.15 * automation_rate + 0.25 * communication_view_rate + 0.25 * primary_channel_rate) * 100.0)
    experience_score = round((0.35 * stability_rate + 0.65 * speed_score) * 100.0)
    governance_score = round((0.40 * sender_integrity_rate + 0.30 * adjusted_route_health + 0.30 * degrade_health) * 100.0)
    overall_score = round((0.30 * business_score) + (0.25 * function_score) + (0.20 * experience_score) + (0.25 * governance_score))

    overall_label, overall_tone = _grade(overall_score)
    business_label, business_tone = _grade(business_score)
    function_label, function_tone = _grade(function_score)
    experience_label, experience_tone = _grade(experience_score)
    governance_label, governance_tone = _grade(governance_score)

    needs_optimization = overall_score < 85 or experience_score < 70 or governance_score < 75
    optimization_tone = "warn" if needs_optimization else "good"
    optimization_value = "需要，优先级 P0" if needs_optimization else "可继续观察"

    sender_mix_rows = _top_counter_rows(
        recent.get("sender_counts") or Counter(),
        total=max(1, int(recent.get("runs") or 0)),
        limit=6,
    )
    status_mix_rows = _top_counter_rows(
        recent.get("status_counts") or Counter(),
        total=max(1, int(recent.get("runs") or 0)),
        limit=6,
    )
    top_projects_rows = _top_counter_rows(
        recent.get("project_counts") or Counter(),
        total=max(1, int(recent.get("runs") or 0)),
        limit=6,
    )
    top_error_channels = [
        {
            "label": _as_str(row.get("name")).strip() or "-",
            "value": _fmt_int(row.get("count")),
            "percent": float(row.get("percent") or 0.0),
            "note": "",
        }
        for row in _as_list(audit.get("top_error_channels"))[:6]
    ]
    degrade_reason_rows = [
        {
            "label": _as_str(row.get("name")).strip() or "(empty)",
            "value": _fmt_int(row.get("count")),
            "percent": float(row.get("percent") or 0.0),
            "note": "",
        }
        for row in degrade_rows[:6]
    ]

    health_panels = [
        {
            "title": "业务健康度",
            "score": _fmt_score(business_score),
            "label": business_label,
            "tone": business_tone,
            "summary": "最近一周系统活跃度和交付完成率都不低，对话 Agent 已经是业务推进主通道之一。",
            "metrics": [
                _build_metric("7天运行量", _fmt_int(recent.get("runs")), f"{_fmt_int(recent.get('active_channels'))} 个活跃通道 / {_fmt_int(recent.get('active_sessions'))} 个活跃会话"),
                _build_metric("7天完成率", _fmt_pct(recent.get("done_rate_pct")), f"error {_fmt_pct(recent.get('error_rate_pct'))}"),
                _build_metric("主项目通道活跃", _fmt_pct(primary_channel_stats.get("active_channel_rate_pct")), f"{_fmt_int(primary_channel_stats.get('active_channels'))} / {_fmt_int(primary_channel_stats.get('total_channels'))}"),
            ],
        },
        {
            "title": "功能健康度",
            "score": _fmt_score(function_score),
            "label": function_label,
            "tone": function_tone,
            "summary": "会话、消息、自动巡检链条已经形成基础闭环，但主位覆盖和结构化元数据覆盖还不够厚。",
            "metrics": [
                _build_metric("Sender 完整率", _fmt_pct(sender_integrity_rate * 100.0), f"legacy {_fmt_int(sender_audit.get('legacy_count'))} / missing {_fmt_int(sender_audit.get('missing_count'))}"),
                _build_metric("健康巡检覆盖", _fmt_pct(automation_rate * 100.0), f"{_fmt_int(automation_enabled)} / {_fmt_int(automation_projects)} 项目已开启"),
                _build_metric("主位通道覆盖", _fmt_pct(primary_channel_stats.get("primary_active_channel_rate_pct")), f"{_fmt_int(primary_channel_stats.get('primary_active_channels'))} / {_fmt_int(primary_channel_stats.get('total_channels'))}"),
            ],
        },
        {
            "title": "体验健康度",
            "score": _fmt_score(experience_score),
            "label": experience_label,
            "tone": experience_tone,
            "summary": "对话 Agent 功能最大短板在体验层，特别是 Agent 详情和会话列表的请求放大问题。",
            "metrics": [
                _build_metric("详情平均耗时", f"{float(perf.get('session_detail_avg_s') or 0.0):.1f}s", "最新性能诊断快照"),
                _build_metric("会话列表平均耗时", f"{float(perf.get('sessions_list_avg_s') or 0.0):.1f}s", f"最大 {float(perf.get('sessions_list_max_s') or 0.0):.1f}s"),
                _build_metric("runs 平均耗时", f"{float(perf.get('runs_avg_s') or 0.0):.1f}s", "热区同时并发时会继续放大"),
            ],
        },
        {
            "title": "治理健康度",
            "score": _fmt_score(governance_score),
            "label": governance_label,
            "tone": governance_tone,
            "summary": "消息链路能用，但审计口径噪音和 callback 元数据问题还在拖累判断成本。",
            "metrics": [
                _build_metric("route_mismatch", _fmt_pct(route_mismatch_rate * 100.0), f"{_fmt_int(route_scan.get('cross_session_callback_match_runs'))} 条更像正常跨 session 回执"),
                _build_metric("callback_to_invalid", _fmt_int(callback_invalid), "当前最主要的降级原因之一"),
                _build_metric("sender_agent_unresolved", _fmt_int(sender_unresolved), "会影响协作链证据完整性"),
            ],
        },
    ]

    findings = [
        {
            "severity": "P0",
            "title": "体验层已经成为当前对话 Agent 能力的主短板",
            "summary": "业务运行和会话基础健康度都还可以，但 Agent 详情与会话列表过慢，会直接拖累日常使用体感。",
            "impact": "不是功能不可用，而是用户每次打开 Agent 详情都在承受额外等待，随着并发增长会进一步放大。",
            "recommendation": "优先做请求链减载、runtime/live-meta 缓存增厚、全项目预热按需化；不要靠裁剪可见内容来换速度。",
            "evidence": [
                f"session_detail 平均 {float(perf.get('session_detail_avg_s') or 0.0):.1f}s",
                f"sessions_list 平均 {float(perf.get('sessions_list_avg_s') or 0.0):.1f}s",
                f"runs 平均 {float(perf.get('runs_avg_s') or 0.0):.1f}s",
            ],
            "refs": [
                "task_dashboard/runtime/session_views.py",
                "task_dashboard/runtime/heartbeat_registry.py",
                "web/task_parts/74-session-bootstrap-and-sessions.js",
            ],
        },
        {
            "severity": "P1",
            "title": "消息治理噪音偏高，审计结论还不够干净",
            "summary": "消息链路本身大多能走通，但 callback_to 与 sender_agent 解析缺口会让很多记录看起来像故障。",
            "impact": "维护成本上升，问题排查容易被误报拖住，也会影响跨 Agent 协作的证据闭环判断。",
            "recommendation": "先把 route_mismatch 里的正常跨 session 回执拆出来，再治理 callback_to_invalid 与 sender_agent_unresolved。",
            "evidence": [
                f"route_mismatch {int(_as_dict(audit.get('totals')).get('route_mismatch_runs') or 0)} 条",
                f"callback_to_invalid {callback_invalid} 条",
                f"sender_agent_unresolved {sender_unresolved} 条",
            ],
            "refs": [
                "task_dashboard/message_risk_report.py",
                "task_dashboard/communication_audit.py",
                "task_dashboard/runtime/callback_runtime.py",
            ],
        },
        {
            "severity": "P1",
            "title": "主位通道覆盖不足，部分能力依赖子会话或休眠主位承接",
            "summary": "当前生产主项目有 21 个通道，但主位 active 只有 12 个，说明真正稳定在线的主负责位还不够满。",
            "impact": "短期不一定出错，但会影响响应一致性和责任位清晰度，尤其在跨通道推进时更明显。",
            "recommendation": "补齐高频通道主位活跃覆盖，先处理经常参与协作但当前不在 primary active 状态的通道。",
            "evidence": [
                f"active channel {int(primary_channel_stats.get('active_channels') or 0)} / {int(primary_channel_stats.get('total_channels') or 0)}",
                f"primary active {int(primary_channel_stats.get('primary_active_channels') or 0)} / {int(primary_channel_stats.get('total_channels') or 0)}",
                f"主项目高风险会话 {int(primary_session_summary.get('high_risk_count') or 0)}，说明瓶颈主要不在 compact，而在编排与覆盖",
            ],
            "refs": [
                ".sessions/task_dashboard.json",
                "dist/project-session-health-dashboard.html",
            ],
        },
        {
            "severity": "P2",
            "title": "会话上下文健康和自动巡检基线总体稳，是继续优化的好底座",
            "summary": "15 个项目都已开启会话健康巡检，生产主项目当前没有高风险 compact 会话，说明底层可持续性没有先出大洞。",
            "impact": "优化可以集中打性能与治理，不必先做会话级救火。",
            "recommendation": "继续保持 session health 自动巡检全开，把高风险治理聚焦在体验和协作链路。",
            "evidence": [
                f"global automation {automation_enabled}/{automation_projects}",
                f"task_dashboard session high risk {int(primary_session_summary.get('high_risk_count') or 0)}",
                f"global rotation due {int(session_summary.get('rotation_due_count') or 0)}",
            ],
            "refs": [
                "task_dashboard/session_health.py",
                "dist/project-session-health-dashboard.html",
            ],
        },
    ]

    actions = [
        {
            "priority": "P0",
            "title": "先做请求链减载，不动可见内容裁剪",
            "detail": "把全项目会话预热改按需加载，把 runtime/live-meta 缓存增厚并做 in-flight 去重，先解决详情慢和列表慢。",
        },
        {
            "priority": "P1",
            "title": "把 Agent 详情中的 task_tracking 做成兜底二段式",
            "detail": "只在主方案后评估启用；首屏主体信息必须稳定可见，task_tracking 只允许局部占位，不允许整页空白。",
        },
        {
            "priority": "P1",
            "title": "校正协作消息审计口径",
            "detail": "拆掉正常 callback_to 跨 session 回执的误报，补齐 callback_to / sender_agent 解析，降低排障噪音。",
        },
        {
            "priority": "P2",
            "title": "补齐主位通道覆盖",
            "detail": "优先把高频协作通道恢复到 primary active 状态，避免长期依赖子会话临时承接。",
        },
    ]

    references = [
        {
            "label": "对话 Agent 最新性能诊断",
            "path": str((script_dir / PERFORMANCE_DOC_REL).resolve()),
            "note": "性能层真源，用来判断当前体验健康度和优化优先级。",
        },
        {
            "label": "会话健康看板产物",
            "path": str((script_dir / "dist" / "project-session-health-dashboard.html").resolve()),
            "note": "读取会话 compact 风险、自动巡检覆盖与项目级健康度快照。",
        },
        {
            "label": "消息风险看板产物",
            "path": str((script_dir / "dist" / "project-message-risk-dashboard.html").resolve()),
            "note": "读取 callback、sender、communication view 和降级原因。",
        },
        {
            "label": "当前热区 run 样本",
            "path": str(runs_dir),
            "note": "最近运行事实样本，支持业务活跃度和状态分布判断。",
        },
        {
            "label": "生产主项目会话主数据",
            "path": str((script_dir / ".sessions" / "task_dashboard.json").resolve()),
            "note": "用于评估通道覆盖、主位状态和会话活跃度。",
        },
    ]

    return {
        "generated_at": generated_at,
        "dashboard": dashboard,
        "links": {
            **links,
            "message_risk_page": links.get("message_risk_page") or "project-message-risk-dashboard.html",
            "status_report_page": links.get("status_report_page") or "project-status-report.html",
            "session_health_page": links.get("session_health_page") or "project-session-health-dashboard.html",
            "performance_page": performance_page_link,
            "agent_capability_page": agent_capability_page_link,
        },
        "agent_capability_report": {
            "hero": {
                "kicker": "Agent Capability Check",
                "headline": "对话Agent功能体检看板",
                "summary": "当前系统的对话 Agent 能力已经具备持续业务运行基础，但体验层和协作治理层存在明确优化项，且优化方式必须坚持“内容稳定可见、不要靠隐藏换速度”。",
            },
            "snapshot": {
                "overall_score": overall_score,
                "overall_label": overall_label,
                "overall_tone": overall_tone,
                "current_branch": _git_stdout(repo_root, "branch", "--show-current"),
                "runs_dir": str(runs_dir),
                "project_count": int(session_summary.get("project_count") or 0),
                "session_count": int(session_summary.get("session_count") or 0),
                "needs_optimization": bool(needs_optimization),
                "primary_project_name": _as_str(primary_channel_stats.get("project_name")).strip(),
                "utf8_header_error_count": utf8_error_count,
            },
            "summary_cards": [
                {
                    "label": "总体判断",
                    "value": f"{overall_label} · {_fmt_score(overall_score)}",
                    "note": "整体可用，但优化优先级已经明确，重点在体验层与协作治理层。",
                    "tone": overall_tone,
                },
                {
                    "label": "业务健康度",
                    "value": _fmt_score(business_score),
                    "note": f"7天 {_fmt_int(recent.get('runs'))} 次运行，done {_fmt_pct(recent.get('done_rate_pct'))}",
                    "tone": business_tone,
                },
                {
                    "label": "功能健康度",
                    "value": _fmt_score(function_score),
                    "note": f"sender 完整 {_fmt_pct(sender_integrity_rate * 100.0)}，主位覆盖 {_fmt_pct(primary_channel_stats.get('primary_active_channel_rate_pct'))}",
                    "tone": function_tone,
                },
                {
                    "label": "体验健康度",
                    "value": _fmt_score(experience_score),
                    "note": f"详情 {float(perf.get('session_detail_avg_s') or 0.0):.1f}s / 列表 {float(perf.get('sessions_list_avg_s') or 0.0):.1f}s",
                    "tone": experience_tone,
                },
                {
                    "label": "治理健康度",
                    "value": _fmt_score(governance_score),
                    "note": f"route_mismatch {_fmt_pct(route_mismatch_rate * 100.0)} / callback_to_invalid {_fmt_int(callback_invalid)}",
                    "tone": governance_tone,
                },
                {
                    "label": "是否需要优化",
                    "value": optimization_value,
                    "note": "结论是需要，而且不能用裁剪可见内容的方式去换速度。",
                    "tone": optimization_tone,
                },
            ],
            "health_panels": health_panels,
            "comparison_panels": [
                {
                    "title": "最近 7 天活跃趋势",
                    "description": "先看系统有没有真的在跑，再谈功能做得好不好。",
                    "rows": recent.get("daily_rows") or [],
                },
                {
                    "title": "最近 7 天运行来源",
                    "description": "用户直发、Agent 协作、系统回执三类输入的当前分布。",
                    "rows": sender_mix_rows,
                },
                {
                    "title": "最近 7 天运行状态",
                    "description": "done 率很高，但体验层的等待感并不会自动体现在 status 上。",
                    "rows": status_mix_rows,
                },
                {
                    "title": "消息治理噪音",
                    "description": "这些不是全部都是真故障，但会持续增加排查和验收成本。",
                    "rows": degrade_reason_rows,
                },
                {
                    "title": "近 7 天项目活跃面",
                    "description": "当前热区主要还是 task_dashboard 和 culture 两个项目在承接大部分对话 Agent 运行。",
                    "rows": top_projects_rows,
                },
                {
                    "title": "高频报错通道",
                    "description": "先看错误更集中在哪里，避免平均发力。",
                    "rows": top_error_channels,
                },
            ],
            "findings": findings,
            "actions": actions,
            "references": references,
        },
    }
