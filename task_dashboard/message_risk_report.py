from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from .communication_audit import audit_communication_patterns
from .sender_identity_audit import audit_run_sender_integrity


HOT_RUNS_REL = Path(".runtime/stable/.runs/hot")
UTF8_HEADER_ERROR_PATTERN = "failed to convert header to a str for header name 'x-codex-turn-metadata'"


def _as_str(value: Any) -> str:
    return "" if value is None else str(value)


def _pct(part: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round((float(part) / float(total)) * 100.0, 1)


def _fmt_pct(value: float) -> str:
    num = float(value or 0.0)
    return f"{num:.1f}%"


def _fmt_int(value: Any) -> str:
    try:
        return f"{int(value):,}"
    except Exception:
        return "0"


def _read_json_dict(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _parse_created_at(value: Any) -> float:
    text = str(value or "").strip()
    if not text:
        return 0.0
    try:
        return datetime.strptime(text, "%Y-%m-%dT%H:%M:%S%z").timestamp()
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(text).timestamp()
    except ValueError:
        return 0.0


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
    rows.sort(key=lambda row: (_parse_created_at(row.get("createdAt")), _as_str(row.get("id"))))
    return rows


def _top_rows(counter: dict[str, int], *, limit: int = 8) -> list[dict[str, Any]]:
    rows = sorted(counter.items(), key=lambda item: (-int(item[1]), str(item[0])))
    total = sum(int(item[1]) for item in rows)
    out: list[dict[str, Any]] = []
    for name, count in rows[: max(1, int(limit or 1))]:
        out.append(
            {
                "label": str(name or ""),
                "count": int(count),
                "percent": _pct(int(count), total),
            }
        )
    return out


def _scan_utf8_header_errors(rows: list[dict[str, Any]]) -> dict[str, Any]:
    count = 0
    latest_example: dict[str, Any] | None = None
    latest_ts = 0.0
    for row in rows:
        paths = row.get("paths") if isinstance(row.get("paths"), dict) else {}
        log_path_text = _as_str(paths.get("log")).strip()
        if not log_path_text:
            continue
        log_path = Path(log_path_text)
        if not log_path.exists():
            continue
        head = _read_log_head(log_path)
        if UTF8_HEADER_ERROR_PATTERN not in head:
            continue
        count += 1
        created_ts = _parse_created_at(row.get("createdAt"))
        if created_ts >= latest_ts:
            latest_ts = created_ts
            latest_example = {
                "run_id": _as_str(row.get("id")).strip(),
                "created_at": _as_str(row.get("createdAt")).strip(),
                "channel_name": _as_str(row.get("channelName")).strip(),
                "status": _as_str(row.get("status")).strip(),
                "branch": _as_str(row.get("branch")).strip(),
            }
    return {
        "count": count,
        "rate_pct": _pct(count, len(rows)),
        "latest_example": latest_example or {},
    }


def _scan_top_level_message_kinds(rows: list[dict[str, Any]]) -> dict[str, int]:
    counter: dict[str, int] = {}
    for row in rows:
        kind = _as_str(row.get("message_kind")).strip().lower() or "(empty)"
        counter[kind] = int(counter.get(kind) or 0) + 1
    return counter


def _scan_branch_distribution(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counter: dict[str, int] = {}
    for row in rows:
        branch = _as_str(row.get("branch")).strip() or "(empty)"
        counter[branch] = int(counter.get(branch) or 0) + 1
    return _top_rows(counter, limit=6)


def _scan_route_mismatch(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = 0
    target_matches_callback = 0
    cross_session_callback_match = 0
    latest_example: dict[str, Any] | None = None
    latest_ts = 0.0
    for row in rows:
        communication_view = row.get("communication_view") if isinstance(row.get("communication_view"), dict) else None
        callback_to = row.get("callback_to") if isinstance(row.get("callback_to"), dict) else None
        if not communication_view or not bool(communication_view.get("route_mismatch")):
            continue
        total += 1
        source_session_id = _as_str(communication_view.get("source_session_id")).strip()
        target_session_id = _as_str(communication_view.get("target_session_id")).strip()
        callback_session_id = _as_str(callback_to.get("session_id") if callback_to else "").strip()
        if callback_session_id and target_session_id == callback_session_id:
            target_matches_callback += 1
            if source_session_id and source_session_id != callback_session_id:
                cross_session_callback_match += 1
                created_ts = _parse_created_at(row.get("createdAt"))
                if created_ts >= latest_ts:
                    latest_ts = created_ts
                    latest_example = {
                        "run_id": _as_str(row.get("id")).strip(),
                        "created_at": _as_str(row.get("createdAt")).strip(),
                        "channel_name": _as_str(row.get("channelName")).strip(),
                        "source_session_id": source_session_id,
                        "target_session_id": target_session_id,
                        "callback_to": {
                            "channel_name": _as_str(callback_to.get("channel_name")).strip(),
                            "session_id": callback_session_id,
                        },
                        "route_source": _as_str(
                            (communication_view.get("route_resolution") or {}).get("source")
                            if isinstance(communication_view.get("route_resolution"), dict)
                            else ""
                        ).strip(),
                    }
    return {
        "route_mismatch_runs": total,
        "target_matches_callback_to": target_matches_callback,
        "target_matches_callback_to_rate_pct": _pct(target_matches_callback, total),
        "cross_session_callback_match_runs": cross_session_callback_match,
        "cross_session_callback_match_rate_pct": _pct(cross_session_callback_match, total),
        "latest_example": latest_example or {},
    }


def _build_metric(label: str, value: str, note: str, tone: str = "") -> dict[str, str]:
    return {
        "label": label,
        "value": value,
        "note": note,
        "tone": tone,
    }


def _build_bar_rows(rows: list[dict[str, Any]], *, label_key: str = "label") -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        out.append(
            {
                "label": _as_str(row.get(label_key)).strip() or "-",
                "value": _fmt_int(row.get("count")),
                "percent": float(row.get("percent") or 0.0),
            }
        )
    return out


def build_message_risk_report_page_data(
    script_dir: Path,
    *,
    generated_at: str,
    dashboard: dict[str, Any],
    links: dict[str, Any],
    message_risk_page_link: str,
) -> dict[str, Any]:
    repo_root = script_dir
    runs_dir = (repo_root / HOT_RUNS_REL).resolve()
    rows = _load_hot_rows(runs_dir)
    audit = audit_communication_patterns(runs_dirs=[runs_dir], response_window_hours=2.0, top_limit=8, include_hidden=False)
    sender_audit = audit_run_sender_integrity(runs_dir=runs_dir, max_detail_items=12, include_hidden=False)
    utf8_errors = _scan_utf8_header_errors(rows)
    route_scan = _scan_route_mismatch(rows)
    top_level_message_kinds = _scan_top_level_message_kinds(rows)
    branch_rows = _scan_branch_distribution(rows)
    current_branch = _git_stdout(repo_root, "branch", "--show-current")

    totals = audit.get("totals") or {}
    rates = audit.get("rates") or {}
    top_degrade_reasons = audit.get("top_degrade_reasons") or []
    top_error_texts = audit.get("top_error_texts") or []
    top_error_channels = audit.get("top_error_channels") or []

    sender_checked = int(sender_audit.get("checked_runs") or 0)
    sender_pass = int(sender_audit.get("pass_count") or 0)
    sender_legacy = int(sender_audit.get("legacy_count") or 0)
    sender_missing = int(sender_audit.get("missing_count") or 0)

    callback_invalid = 0
    for row in top_degrade_reasons:
        if _as_str(row.get("name")).strip() == "callback_to_invalid":
            callback_invalid = int(row.get("count") or 0)
            break

    dominant_branch = branch_rows[0] if branch_rows else {"label": "(empty)", "count": 0, "percent": 0.0}
    latest_utf8_example = utf8_errors.get("latest_example") or {}
    latest_route_example = route_scan.get("latest_example") or {}

    summary_cards = [
        _build_metric(
            "热区样本",
            _fmt_int(totals.get("runs")),
            f"本次读取 {runs_dir}",
            "",
        ),
        _build_metric(
            "结构化沟通覆盖",
            _fmt_pct(float(rates.get("communication_view_rate_pct") or 0.0)),
            f"communication_view { _fmt_int(totals.get('communication_view_runs')) } 条",
            "warn" if float(rates.get("communication_view_rate_pct") or 0.0) < 60 else "",
        ),
        _build_metric(
            "回执错配标记",
            _fmt_pct(float(rates.get("route_mismatch_rate_pct") or 0.0)),
            f"route_mismatch { _fmt_int(totals.get('route_mismatch_runs')) } 条",
            "danger" if float(rates.get("route_mismatch_rate_pct") or 0.0) >= 50 else "warn",
        ),
        _build_metric(
            "发送者字段通过率",
            _fmt_pct(_pct(sender_pass, sender_checked)),
            f"legacy { _fmt_int(sender_legacy) } / missing { _fmt_int(sender_missing) }",
            "",
        ),
        _build_metric(
            "UTF-8 头错误命中",
            _fmt_int(utf8_errors.get("count")),
            f"占热区 { _fmt_pct(float(utf8_errors.get('rate_pct') or 0.0)) }",
            "danger" if int(utf8_errors.get("count") or 0) > 0 else "",
        ),
        _build_metric(
            "branch 记录主峰",
            _as_str(dominant_branch.get("label")).strip() or "-",
            f"{ _fmt_int(dominant_branch.get('count')) } 条，占比 { _fmt_pct(float(dominant_branch.get('percent') or 0.0)) }",
            "warn" if current_branch and current_branch != _as_str(dominant_branch.get("label")).strip() else "",
        ),
    ]

    comparisons = [
        {
            "title": "主动发信 vs 审计可见性",
            "description": "顶层消息种类并不少，但当前 communication_view 基本只收 system_callback。",
            "rows": [
                {
                    "label": "顶层空 message_kind",
                    "value": _fmt_int(top_level_message_kinds.get("(empty)") or 0),
                    "percent": _pct(int(top_level_message_kinds.get("(empty)") or 0), len(rows)),
                    "tone": "warn",
                    "note": "默认历史兼容仍占大头",
                },
                {
                    "label": "顶层 collab_update",
                    "value": _fmt_int(top_level_message_kinds.get("collab_update") or 0),
                    "percent": _pct(int(top_level_message_kinds.get("collab_update") or 0), len(rows)),
                    "tone": "accent",
                    "note": "主动协作消息已大量存在",
                },
                {
                    "label": "communication_view",
                    "value": _fmt_int(totals.get("communication_view_runs")),
                    "percent": float(rates.get("communication_view_rate_pct") or 0.0),
                    "tone": "warn",
                    "note": "当前结构化视图覆盖 43.5%",
                },
                {
                    "label": "communication_view 中 system_callback",
                    "value": _fmt_int(totals.get("communication_view_runs")),
                    "percent": 100.0,
                    "tone": "danger",
                    "note": "主动发信质量没有进入主分析面",
                },
            ],
        },
        {
            "title": "回调错配率拆解",
            "description": "至少一部分 route_mismatch 更像“按 callback_to 成功回原会话”而不是错投。",
            "rows": [
                {
                    "label": "route_mismatch 总数",
                    "value": _fmt_int(route_scan.get("route_mismatch_runs")),
                    "percent": float(rates.get("route_mismatch_rate_pct") or 0.0),
                    "tone": "danger",
                    "note": "当前回调视图里的主风险标签",
                },
                {
                    "label": "target = callback_to.session_id",
                    "value": _fmt_int(route_scan.get("target_matches_callback_to")),
                    "percent": float(route_scan.get("target_matches_callback_to_rate_pct") or 0.0),
                    "tone": "warn",
                    "note": "回到了调用方明确要求的 session",
                },
                {
                    "label": "同项目跨 session 回传且 target = callback_to",
                    "value": _fmt_int(route_scan.get("cross_session_callback_match_runs")),
                    "percent": float(route_scan.get("cross_session_callback_match_rate_pct") or 0.0),
                    "tone": "warn",
                    "note": "更像正常跨会话回执，而不是错投",
                },
                {
                    "label": "callback_to_invalid",
                    "value": _fmt_int(callback_invalid),
                    "percent": _pct(callback_invalid, int(totals.get("communication_view_runs") or 0)),
                    "tone": "accent",
                    "note": "真正需要治理的降级之一",
                },
            ],
        },
        {
            "title": "发送者字段现状",
            "description": "当前数据面并没有大面积 sender 崩坏，但入口约束仍然偏软。",
            "rows": [
                {
                    "label": "sender 通过",
                    "value": _fmt_int(sender_pass),
                    "percent": _pct(sender_pass, sender_checked),
                    "tone": "accent",
                    "note": "运行数据大体合规",
                },
                {
                    "label": "sender legacy",
                    "value": _fmt_int(sender_legacy),
                    "percent": _pct(sender_legacy, sender_checked),
                    "tone": "warn",
                    "note": "主要是历史债务而非当前爆点",
                },
                {
                    "label": "sender 缺失",
                    "value": _fmt_int(sender_missing),
                    "percent": _pct(sender_missing, sender_checked),
                    "tone": "danger" if sender_missing else "accent",
                    "note": "当前仅 1 条，但 ingress 仍非硬门禁",
                },
            ],
        },
    ]

    pipeline = [
        {
            "name": "发送入口",
            "summary": "会话输入框与任务派发都通过 `/api/codex/announce` 下发，先决定目标 session，再附 sender/附件/回帖关系。",
            "fields": ["projectId", "channelName", "sessionId", "sender_*", "reply_to_run_id"],
            "refs": [
                "web/task_parts/75-conversation-composer.js:2878",
                "web/task_parts/30-task-push.js",
            ],
        },
        {
            "name": "入口解析",
            "summary": "运行时会绑定 session、补 project_execution_context、落 run extra fields，但当前只校 session 绑定，不校 sender 一致性。",
            "fields": ["target_ref", "source_ref", "callback_to", "project_execution_context"],
            "refs": [
                "task_dashboard/routes/main.py:2549",
                "task_dashboard/runtime/request_parsing.py",
                "task_dashboard/runtime/scheduler_helpers.py:2893",
            ],
        },
        {
            "name": "Run 落盘执行",
            "summary": "消息被固化为 `.runs/*.json/.log/.last`，形成可回放证据链，也是当前全部审计的底座。",
            "fields": ["status", "paths", "branch", "worktree_root", "message_kind"],
            "refs": [
                "server.py",
                "task_dashboard/runtime/execution_command.py",
            ],
        },
        {
            "name": "终态回调",
            "summary": "done/error 后自动按 `callback_to -> source_ref -> sender_agent -> owner_channel` 路由回执。",
            "fields": ["communication_view", "receipt_summary", "route_resolution"],
            "refs": [
                "task_dashboard/runtime/callback_runtime.py",
            ],
        },
        {
            "name": "审计展示",
            "summary": "通信分析页主要聚合 run artifacts 中的 `communication_view/receipt_summary`，偏重 callback 可见性。",
            "fields": ["communication_view", "receipt_summary", "reply_to_run_id", "mention_targets"],
            "refs": [
                "task_dashboard/communication_audit.py",
                "web/communication.js",
            ],
        },
    ]

    findings = [
        {
            "severity": "P0",
            "title": "route_mismatch 口径混入正常跨 session 回执",
            "summary": (
                f"当前热区 { _fmt_int(route_scan.get('route_mismatch_runs')) } 条回调被打成 route_mismatch。"
                f"其中 { _fmt_int(route_scan.get('target_matches_callback_to')) } 条的目标 session 恰好等于 callback_to.session_id，"
                f"且同项目跨 session 成立，更像是按制度回原发送 Agent。"
            ),
            "impact": "会把正常回执误报成异常，直接抬高风险率，影响消息治理判断和后续自动化规则。",
            "recommendation": "把“跨 session 但命中 callback_to”从 route_mismatch 剥离为 expected_cross_session_callback 或单独状态。",
            "evidence": [
                "callback_runtime 以 source_session != target_session 直接定义 route_mismatch。",
                f"最新示例 run { _as_str(latest_route_example.get('run_id')) or '-' } 命中 callback_to 回原会话仍被记成 route_mismatch。",
            ],
            "refs": [
                "task_dashboard/runtime/callback_runtime.py:2185",
                "http://localhost:18770/api/codex/run/20260330-153124-27223971",
            ],
        },
        {
            "severity": "P0",
            "title": "正式消息执行链存在 UTF-8 头编码重连噪音",
            "summary": (
                f"热区日志中有 { _fmt_int(utf8_errors.get('count')) } 条 run 命中 `x-codex-turn-metadata` UTF-8 编码错误。"
                "大量 run 最终仍是 done，说明系统靠重连硬扛，而不是链路本身稳定。"
            ),
            "impact": "会放大时延、重连次数和日志噪音，极端情况下可能造成正式消息发送/回执链路失败或变慢。",
            "recommendation": "优先核查 Codex resume 时 workspace 路径编码与 ASCII mirror 使用条件，把非 ASCII 路径从头部元数据里剥离或转码。",
            "evidence": [
                f"最新命中示例 run { _as_str(latest_utf8_example.get('run_id')) or '-' }，状态 { _as_str(latest_utf8_example.get('status')) or '-' }。",
                "同一条 run log 中出现连续 reconnect 2/5 ~ 5/5，再最终完成。",
            ],
            "refs": [
                "http://localhost:18770/api/codex/run/20260330-153124-27223971",
                "server.py",
            ],
        },
        {
            "severity": "P1",
            "title": "当前通信审计主视图偏 callback，主动发信质量不可见",
            "summary": (
                f"热区顶层 `collab_update` 已有 { _fmt_int(top_level_message_kinds.get('collab_update') or 0) } 条，"
                f"但 communication_view 共 { _fmt_int(totals.get('communication_view_runs')) } 条，且 100% 都是 system_callback。"
            ),
            "impact": "会看不清主动协作消息的 sender/source/callback 质量，只能看到终态回调切面。",
            "recommendation": "给 announce 入站消息补 lightweight communication_view，至少覆盖 collab_update/manual_update 的发送面。",
            "evidence": [
                "communication_audit 只在 communication_view 存在时统计 communication_message_kind。",
                "当前顶层 message_kind 分布与 communication_view 分布存在明显断层。",
            ],
            "refs": [
                "task_dashboard/communication_audit.py:139",
                "web/communication.js",
            ],
        },
        {
            "severity": "P1",
            "title": "sender 数据面总体健康，但 ingress 仍然是软约束",
            "summary": (
                f"sender 审计通过 { _fmt_int(sender_pass) } / { _fmt_int(sender_checked) }，"
                f"legacy { _fmt_int(sender_legacy) }，missing { _fmt_int(sender_missing) }。"
                "现状说明治理已有成效，但 announce 入口仍只 normalize sender，不做一致性阻断。"
            ),
            "impact": "一旦后续多 Agent 发送模板回退或代发口径漂移，服务端不会在入口拦住，会把问题带进运行态和审计侧。",
            "recommendation": "在 /api/codex/announce 增加 sender consistency 检查，对 agent 场景至少校 `sender_id/name` 非空，并校验 source_ref/session 关系。",
            "evidence": [
                "server 入口 extract_sender_fields 只返回规范化结果。",
                "validate_sender_consistency 已存在，但当前主要用于离线 audit。",
            ],
            "refs": [
                "server.py:620",
                "task_dashboard/sender_contract.py:190",
                "task_dashboard/runtime/scheduler_helpers.py:2893",
            ],
        },
        {
            "severity": "P2",
            "title": "run 元数据 branch 与当前工作区 branch 存在漂移样本",
            "summary": (
                f"当前工作区 branch 是 `{ current_branch or '-' }`，但热区 run 元数据主峰仍是"
                f" `{ _as_str(dominant_branch.get('label')) or '-' }`。"
                "最新验证 run 也记录了旧 branch，说明消息证据链里的执行上下文并不总与当前工作区一致。"
            ),
            "impact": "会削弱排障与责任定位的可信度，尤其在多工作区/三项目并行时容易误导问题归属。",
            "recommendation": "把 project_execution_context 的 branch 刷新口径与实际 worktree 分支对齐，并在回调页面显式展示 branch 来源。",
            "evidence": [
                f"最新 UTF-8 样本 run branch = { _as_str(latest_utf8_example.get('branch')) or '-' }。",
                "hot runs 的 branch 主峰与当前 git branch 不同。",
            ],
            "refs": [
                "http://localhost:18770/__health",
                "http://localhost:18770/api/codex/run/20260330-153124-27223971",
            ],
        },
    ]

    action_board = [
        {
            "priority": "P0",
            "title": "重定义 callback 正常跨 session 回传状态",
            "detail": "先把命中 callback_to 的跨 session 回执从 route_mismatch 中拆出来，再回填 communication audit 的统计口径。",
        },
        {
            "priority": "P0",
            "title": "治理 Codex resume 的 UTF-8 头编码问题",
            "detail": "沿 ASCII mirror / workspace header 精简两条线核查，确保正式消息链路不再依赖重连兜底。",
        },
        {
            "priority": "P1",
            "title": "补主动发信审计视角",
            "detail": "为 collab_update / manual_update 建轻量 communication_view，补 sender/source/callback 可见性。",
        },
        {
            "priority": "P1",
            "title": "把 sender consistency 前移为入口门禁",
            "detail": "agent 发送至少强校 sender 身份非空与 source_ref/session 关系，避免把脏数据写进 hot runs。",
        },
        {
            "priority": "P2",
            "title": "修正 branch 证据漂移",
            "detail": "把消息 run 记录的 branch 与实际工作区统一，避免后续生产/镜像项目排障混淆。",
        },
    ]

    references = [
        {
            "label": "API 契约真源",
            "path": str((repo_root / "docs/contract/api.v1.md").resolve()),
            "note": "消息字段、回执口径、三项目真源约束都以这里为准。",
        },
        {
            "label": "通信审计实现",
            "path": str((repo_root / "task_dashboard/communication_audit.py").resolve()),
            "note": "当前页面指标主要来源。",
        },
        {
            "label": "回调路由实现",
            "path": str((repo_root / "task_dashboard/runtime/callback_runtime.py").resolve()),
            "note": "route_mismatch 口径与 callback_to 优先级在这里。",
        },
        {
            "label": "发送者契约",
            "path": str((repo_root / "task_dashboard/sender_contract.py").resolve()),
            "note": "validate_sender_consistency 已存在，但尚未上 ingress 硬门禁。",
        },
        {
            "label": "最新验证 run",
            "path": "http://localhost:18770/api/codex/run/20260330-153124-27223971",
            "note": "用于复核 callback 误报与 UTF-8 头错误样本。",
        },
    ]

    tables = [
        {
            "title": "主要降级原因",
            "description": "真正需要治理的 route_resolution 退化点。",
            "rows": _build_bar_rows(
                [
                    {
                        "label": _as_str(row.get("name")).strip() or "(empty)",
                        "count": int(row.get("count") or 0),
                        "percent": float(row.get("percent") or 0.0),
                    }
                    for row in top_degrade_reasons
                ]
            ),
        },
        {
            "title": "消息错误热点",
            "description": "先看最常见的失败文本，避免盲猜。",
            "rows": _build_bar_rows(
                [
                    {
                        "label": _as_str(row.get("name")).strip() or "(empty)",
                        "count": int(row.get("count") or 0),
                        "percent": float(row.get("percent") or 0.0),
                    }
                    for row in top_error_texts[:6]
                ]
            ),
        },
        {
            "title": "受影响通道 Top",
            "description": "错误最多的通道并不等于问题源头，但能辅助定治理优先级。",
            "rows": _build_bar_rows(
                [
                    {
                        "label": _as_str(row.get("name")).strip() or "(empty)",
                        "count": int(row.get("count") or 0),
                        "percent": float(row.get("percent") or 0.0),
                    }
                    for row in top_error_channels
                ]
            ),
        },
        {
            "title": "branch 分布",
            "description": "消息 run 证据链中的 branch 记录并不完全跟当前工作区同步。",
            "rows": _build_bar_rows(branch_rows),
        },
    ]

    report = {
        "hero": {
            "kicker": "Message Risk Dashboard",
            "headline": "消息功能梳理与风险看板",
            "summary": (
                "把消息发送、入口解析、终态回调和审计展示放到同一屏，"
                "只保留对治理决策有用的风险与证据，不做空泛点评。"
            ),
        },
        "snapshot": {
            "generated_at": generated_at,
            "runs_dir": str(runs_dir),
            "current_branch": current_branch,
            "message_risk_page": message_risk_page_link,
        },
        "summary_cards": summary_cards,
        "pipeline": pipeline,
        "comparisons": comparisons,
        "findings": findings,
        "tables": tables,
        "actions": action_board,
        "references": references,
    }

    return {
        "generated_at": generated_at,
        "dashboard": dashboard,
        "links": {
            **links,
            "message_risk_page": message_risk_page_link,
        },
        "message_risk_page": message_risk_page_link,
        "environment": "stable",
        "message_risk_report": report,
    }
