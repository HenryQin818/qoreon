from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from .incremental_inspector import inspect_incremental_runs
from .session_model_audit import audit_session_model_integrity
from .sender_identity_audit import audit_run_sender_integrity
from .source_channel_audit import audit_source_channel_markers
from .state_aligner import align_runs

FAILURE_ISSUE_FILENAME = "【待处理】【问题】问题-巡检调度连续失败告警（聚合）.md"
SOURCE_CHANNEL_ISSUE_FILENAME = "【待处理】【问题】问题-来源通道标识缺失巡检告警（聚合）.md"
SENDER_IDENTITY_ISSUE_FILENAME = "【待处理】【问题】问题-发送者身份字段完整性巡检告警（聚合）.md"

_GUARD_POLICY_VERSION = "v1-48-1-freeze"
_GUARD_P1_WINDOW_MINUTES = 15
_GUARD_P1_HIT_THRESHOLD = 3
_GUARD_P0_CONSECUTIVE_THRESHOLD = 2
_GUARD_HISTORY_RETENTION_HOURS = 24
_GUARD_SLA_MINUTES = {
    "P0": 15,
    "P1": 60,
    "P2": 24 * 60,
}
_GUARD_RULE_META: dict[str, dict[str, Any]] = {
    "inspection_scheduler_failure": {
        "level": "P0",
        "owner_channel": "子级02-CCB运行时（server-并发-安全-启动）",
        "fatal_condition": "自动巡查链路失效",
    },
    "source_channel_marker_integrity": {
        "level": "P1",
        "owner_channel": "子级05-任务巡检与留痕（自动化）",
        "fatal_condition": "",
    },
    "sender_identity_integrity": {
        "level": "P2",
        "owner_channel": "子级02-CCB运行时（server-并发-安全-启动）",
        "fatal_condition": "",
    },
}


def _now_local_iso() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _load_health_state(path: Path) -> dict[str, Any]:
    default = {
        "version": 1,
        "consecutive_failures": 0,
        "last_status": "unknown",
        "last_run_at": "",
        "last_error": "",
        "total_runs": 0,
        "guard_state": {
            "version": 1,
            "open_since": {},
            "rule_hits": {},
            "last_updated_at": "",
        },
    }
    if not path.exists():
        return default
    try:
        raw = _read_json(path)
    except Exception:
        return default
    return {
        "version": int(raw.get("version") or 1),
        "consecutive_failures": int(raw.get("consecutive_failures") or 0),
        "last_status": str(raw.get("last_status") or "unknown"),
        "last_run_at": str(raw.get("last_run_at") or ""),
        "last_error": str(raw.get("last_error") or ""),
        "total_runs": int(raw.get("total_runs") or 0),
        "guard_state": _normalize_guard_state(raw.get("guard_state")),
    }


def _parse_local_iso(raw: Any) -> datetime | None:
    s = str(raw or "").strip()
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S%z")
    except Exception:
        pass
    try:
        dt = datetime.fromisoformat(s)
    except Exception:
        return None
    if dt.tzinfo is None:
        return None
    return dt


def _iso_after_minutes(base_iso: str, minutes: int, *, fallback_now: datetime | None = None) -> str:
    base_dt = _parse_local_iso(base_iso) or fallback_now or datetime.now().astimezone()
    return (base_dt + timedelta(minutes=max(0, int(minutes or 0)))).strftime("%Y-%m-%dT%H:%M:%S%z")


def _normalize_guard_state(raw: Any) -> dict[str, Any]:
    obj = raw if isinstance(raw, dict) else {}
    open_since_raw = obj.get("open_since")
    open_since: dict[str, str] = {}
    if isinstance(open_since_raw, dict):
        for k, v in open_since_raw.items():
            key = str(k or "").strip()
            val = str(v or "").strip()
            if key and val:
                open_since[key] = val

    rule_hits_raw = obj.get("rule_hits")
    rule_hits: dict[str, list[str]] = {}
    if isinstance(rule_hits_raw, dict):
        for k, vals in rule_hits_raw.items():
            key = str(k or "").strip()
            if not key or not isinstance(vals, list):
                continue
            out: list[str] = []
            for item in vals:
                ts = str(item or "").strip()
                if ts:
                    out.append(ts)
            if out:
                rule_hits[key] = out[-120:]

    return {
        "version": 1,
        "open_since": open_since,
        "rule_hits": rule_hits,
        "last_updated_at": str(obj.get("last_updated_at") or ""),
    }


def _prune_hits(raw_hits: list[str], *, now: datetime, within_minutes: int) -> list[str]:
    keep_after = now - timedelta(minutes=max(1, int(within_minutes or 1)))
    out: list[str] = []
    for item in raw_hits:
        ts = _parse_local_iso(item)
        if ts is None:
            continue
        if ts >= keep_after:
            out.append(ts.strftime("%Y-%m-%dT%H:%M:%S%z"))
    return out[-120:]


def _guard_policy_payload() -> dict[str, Any]:
    return {
        "policy_version": _GUARD_POLICY_VERSION,
        "levels": ["P0", "P1", "P2"],
        "fatal_hits": [
            "服务不可用",
            "调度不可保存或不可执行",
            "自动巡查链路失效",
            "关键run持续中断且无法自动恢复",
        ],
        "upgrade_rules": [
            "P0连续2周期未恢复升级",
            "P1在15分钟窗口连续3次命中升级",
            "超时未回执提级",
        ],
        "sla_minutes": dict(_GUARD_SLA_MINUTES),
    }


def _build_guard_runtime(
    *,
    health: dict[str, Any],
    active_rules: list[dict[str, Any]],
    now_iso: str,
) -> dict[str, Any]:
    now_dt = _parse_local_iso(now_iso) or datetime.now().astimezone()
    guard_state = _normalize_guard_state(health.get("guard_state"))
    open_since = dict(guard_state.get("open_since") or {})
    rule_hits = dict(guard_state.get("rule_hits") or {})
    active_keys: set[str] = set()
    events: list[dict[str, Any]] = []

    for item in active_rules:
        if not isinstance(item, dict):
            continue
        rule_key = str(item.get("rule_key") or "").strip()
        if not rule_key:
            continue
        meta = _GUARD_RULE_META.get(rule_key) or {}
        level = str(meta.get("level") or item.get("level") or "P2").strip().upper()
        if level not in {"P0", "P1", "P2"}:
            level = "P2"
        active_keys.add(rule_key)
        first_seen = str(open_since.get(rule_key) or "").strip() or now_iso
        open_since[rule_key] = first_seen

        merged_hits = list(rule_hits.get(rule_key) or [])
        merged_hits.append(now_iso)
        merged_hits = _prune_hits(merged_hits, now=now_dt, within_minutes=_GUARD_HISTORY_RETENTION_HOURS * 60)
        rule_hits[rule_key] = merged_hits
        window_hits = len(_prune_hits(merged_hits, now=now_dt, within_minutes=_GUARD_P1_WINDOW_MINUTES))

        sla_minutes = int(_GUARD_SLA_MINUTES.get(level, 24 * 60))
        response_due_at = _iso_after_minutes(first_seen, sla_minutes, fallback_now=now_dt)
        due_dt = _parse_local_iso(response_due_at) or now_dt
        overdue = now_dt > due_dt

        upgrade_reasons: list[str] = []
        if level == "P0" and int(health.get("consecutive_failures") or 0) >= _GUARD_P0_CONSECUTIVE_THRESHOLD:
            upgrade_reasons.append("p0_consecutive_2_cycles")
        if level == "P1" and window_hits >= _GUARD_P1_HIT_THRESHOLD:
            upgrade_reasons.append("p1_hits_3_in_15m")
        if overdue:
            upgrade_reasons.append("sla_timeout_no_ack")
        upgrade = bool(upgrade_reasons)

        issue_path = str(item.get("issue_path") or "").strip()
        evidence_refs: list[str] = []
        for ref in item.get("evidence_refs") or []:
            txt = str(ref or "").strip()
            if txt:
                evidence_refs.append(txt)
        if issue_path and issue_path not in evidence_refs:
            evidence_refs.append(issue_path)
        events.append(
            {
                "time": now_iso,
                "level": level,
                "status": "escalated" if upgrade else "open",
                "summary": str(item.get("summary") or meta.get("fatal_condition") or rule_key),
                "owner_channel": str(item.get("owner_channel") or meta.get("owner_channel") or ""),
                "related_run_id": str(item.get("related_run_id") or ""),
                "rule_key": rule_key,
                "action_state": "escalated" if upgrade else "dispatched",
                "updated_at": now_iso,
                "fatal_hit": bool(item.get("fatal_hit") or bool(meta.get("fatal_condition"))),
                "fatal_condition": str(item.get("fatal_condition") or meta.get("fatal_condition") or ""),
                "sla_minutes": sla_minutes,
                "response_due_at": response_due_at,
                "hit_count_15m": window_hits,
                "upgrade_triggered": upgrade,
                "upgrade_reasons": upgrade_reasons,
                "issue_path": issue_path,
                "evidence_refs": evidence_refs[:20],
            }
        )

    recovered_rules = sorted(set(open_since.keys()) - active_keys)
    for key in recovered_rules:
        open_since.pop(key, None)

    # Keep latest hit windows for currently open rules and recent history.
    kept_hits: dict[str, list[str]] = {}
    for key, vals in rule_hits.items():
        pruned = _prune_hits(list(vals or []), now=now_dt, within_minutes=_GUARD_HISTORY_RETENTION_HOURS * 60)
        if pruned:
            kept_hits[key] = pruned

    guard_state = {
        "version": 1,
        "open_since": open_since,
        "rule_hits": kept_hits,
        "last_updated_at": now_iso,
    }
    health["guard_state"] = guard_state

    events.sort(key=lambda x: str(x.get("level") or "P2"))
    escalated_count = sum(1 for x in events if bool(x.get("upgrade_triggered")))
    return {
        "policy": _guard_policy_payload(),
        "events": events[:20],
        "stats": {
            "open_count": len(events),
            "escalated_count": escalated_count,
            "recovered_rules": recovered_rules[:20],
            "updated_at": now_iso,
        },
    }


def _issue_dir(task_root: Path) -> Path:
    return task_root / "子级05-任务巡检与留痕（自动化）" / "问题"


def _clear_issue_file(task_root: Path, filename: str) -> str:
    path = _issue_dir(task_root) / filename
    if path.exists():
        path.unlink()
        return str(path)
    return ""


def _render_failure_issue(err: str, threshold: int, health: dict[str, Any]) -> str:
    return (
        f"# 问题-巡检调度连续失败告警\n"
        f"更新时间：{datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S %z')}\n\n"
        "## 问题描述\n"
        "- 自动巡检调度连续失败，已达到升级阈值。\n\n"
        "## 影响范围\n"
        "- 子级05巡检链路（增量巡检、状态对齐、自动留痕）\n\n"
        "## 来源/触发\n"
        "- 场景/来源路径：`.run/inspection/health.json`、`.run/inspection/daemon.*.log`\n"
        f"- 触发描述：连续失败 `>= {threshold}` 次\n\n"
        "## 关联任务/反馈\n"
        "- `任务规划/子级05-任务巡检与留痕（自动化）/任务/【待开始】【任务】08-4-自动执行调度（每2小时）与健康告警.md`\n\n"
        "## 干系方（通道）\n"
        "- 子级05-任务巡检与留痕（自动化）\n"
        "- 子级02-CCB运行时（server-并发-安全-启动）\n"
        "- 主体-总控（合并与验收）\n\n"
        "## 当前结论\n"
        "- 告警等级：P0\n"
        "- 回执SLA：15分钟内首回执\n"
        f"- 连续失败次数：{int(health.get('consecutive_failures') or 0)}\n"
        f"- 最近错误：{err}\n\n"
        "## 下一步\n"
        "- 人工检查日志与运行环境，确认后恢复调度。\n"
        "- 若连续2个巡检周期未恢复，自动升级总控。\n"
    )


def _write_failure_issue(task_root: Path, err: str, threshold: int, health: dict[str, Any]) -> str | None:
    sub05 = task_root / "子级05-任务巡检与留痕（自动化）"
    if not sub05.exists():
        return None
    issue_dir = _issue_dir(task_root)
    issue_dir.mkdir(parents=True, exist_ok=True)
    path = issue_dir / FAILURE_ISSUE_FILENAME
    path.write_text(_render_failure_issue(err, threshold, health), encoding="utf-8")
    return str(path)


def _render_source_channel_issue(audit: dict[str, Any]) -> str:
    missing_paths = audit.get("missing_paths") or []
    invalid_paths = audit.get("invalid_paths") or []
    show_missing = missing_paths[:20]
    show_invalid = invalid_paths[:20]
    lines: list[str] = []
    for p in show_missing:
        lines.append(f"- 缺失：`{p}`")
    for p in show_invalid:
        lines.append(f"- 无效：`{p}`")
    details = "\n".join(lines) if lines else "- （无详情）"

    return (
        "# 问题-来源通道标识缺失巡检告警\n"
        f"更新时间：{datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S %z')}\n\n"
        "## 问题描述\n"
        "- 巡检发现回执类文档缺少或无效来源通道标识`[来源通道: ...]`。\n\n"
        "## 影响范围\n"
        "- 子级05巡检规则合规性\n"
        "- 总控消费回执时的来源可追溯性\n\n"
        "## 来源/触发\n"
        "- 场景/来源路径：`任务规划/*/{反馈,答复}/*.md`\n"
        "- 触发描述：本轮巡检统计缺失/无效项 > 0\n\n"
        "## 关联任务/反馈\n"
        "- `任务规划/子级05-任务巡检与留痕（自动化）/任务/【进行中】【任务】10-1-来源通道标识巡检规则接入.md`\n\n"
        "## 干系方（通道）\n"
        "- 子级05-任务巡检与留痕（自动化）\n"
        "- 主体-总控（合并与验收）\n\n"
        "## 当前结论\n"
        "- 告警等级：P1\n"
        "- 回执SLA：60分钟内首回执\n"
        f"- 通过数：{int(audit.get('pass_count') or 0)}\n"
        f"- 缺失数：{int(audit.get('missing_count') or 0)}\n"
        f"- 无效数：{int(audit.get('invalid_count') or 0)}\n"
        f"- 遗留数：{int(audit.get('legacy_count') or 0)}\n\n"
        "## 缺失样例（截断）\n"
        f"{details}\n\n"
        "## 下一步\n"
        "- 对新增回执强制补齐来源通道标识；历史文档按遗留标记处理，不做批量改写。\n"
        "- 若15分钟窗口内同类命中达到3次，自动升级总控复核。\n"
    )


def _write_source_channel_issue(task_root: Path, audit: dict[str, Any]) -> str | None:
    sub05 = task_root / "子级05-任务巡检与留痕（自动化）"
    if not sub05.exists():
        return None
    issue_dir = _issue_dir(task_root)
    issue_dir.mkdir(parents=True, exist_ok=True)
    path = issue_dir / SOURCE_CHANNEL_ISSUE_FILENAME
    path.write_text(_render_source_channel_issue(audit), encoding="utf-8")
    return str(path)


def _render_sender_identity_issue(audit: dict[str, Any]) -> str:
    missing_items = audit.get("missing_items") or []
    invalid_items = audit.get("invalid_items") or []
    show_missing = missing_items[:20]
    show_invalid = invalid_items[:20]
    lines: list[str] = []
    for item in show_missing:
        rid = str(item.get("run_id") or "").strip()
        reasons = ",".join(item.get("reasons") or [])
        lines.append(f"- 缺失：`{rid}`（{reasons or 'missing'}）")
    for item in show_invalid:
        rid = str(item.get("run_id") or "").strip()
        reason = str(item.get("reason") or "invalid")
        lines.append(f"- 无效：`{rid}`（{reason}）")
    details = "\n".join(lines) if lines else "- （无详情）"

    return (
        "# 问题-发送者身份字段完整性巡检告警\n"
        f"更新时间：{datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S %z')}\n\n"
        "## 问题描述\n"
        "- 巡检发现 run 元数据 sender 字段缺失或无效，存在发送者身份不可追溯风险。\n\n"
        "## 影响范围\n"
        "- 消息发送者身份识别与展示改造（任务11）\n"
        "- 子级05巡检链路与留痕可靠性\n\n"
        "## 来源/触发\n"
        "- 场景/来源路径：`.runs/*.json`\n"
        "- 触发描述：本轮巡检统计 sender 缺失/无效项 > 0\n\n"
        "## 关联任务/反馈\n"
        "- `任务规划/子级05-任务巡检与留痕（自动化）/任务/【进行中】【任务】11-4-发送者身份完整性巡检与遗留统计.md`\n\n"
        "## 干系方（通道）\n"
        "- 子级05-任务巡检与留痕（自动化）\n"
        "- 子级02-CCB运行时（server-并发-安全-启动）\n\n"
        "## 当前结论\n"
        "- 告警等级：P2\n"
        "- 回执SLA：24小时内给出处理计划\n"
        f"- 通过数：{int(audit.get('pass_count') or 0)}\n"
        f"- 缺失数：{int(audit.get('missing_count') or 0)}\n"
        f"- 无效数：{int(audit.get('invalid_count') or 0)}\n"
        f"- 遗留数：{int(audit.get('legacy_count') or 0)}\n\n"
        "## 缺失/无效样例（截断）\n"
        f"{details}\n\n"
        "## 下一步\n"
        "- 先同步子级02确认 sender 字段写入口与命名口径，再复跑巡检验证收敛。\n"
    )


def _write_sender_identity_issue(task_root: Path, audit: dict[str, Any]) -> str | None:
    sub05 = task_root / "子级05-任务巡检与留痕（自动化）"
    if not sub05.exists():
        return None
    issue_dir = _issue_dir(task_root)
    issue_dir.mkdir(parents=True, exist_ok=True)
    path = issue_dir / SENDER_IDENTITY_ISSUE_FILENAME
    path.write_text(_render_sender_identity_issue(audit), encoding="utf-8")
    return str(path)


def run_once(
    *,
    task_root: Path,
    runs_dir: Path,
    watermark_path: Path,
    ledger_path: Path,
    alignment_state_path: Path,
    health_path: Path,
    retention_days: int = 90,
    fail_threshold: int = 2,
    source_channel_legacy_cutoff_iso: str = "2026-02-21T01:08:00+0800",
    source_channel_include_task_docs: bool = False,
    sender_legacy_cutoff_iso: str = "2026-02-21T04:01:00+0800",
    inspect_fn: Callable[..., dict[str, Any]] = inspect_incremental_runs,
    align_fn: Callable[..., dict[str, Any]] = align_runs,
    source_channel_audit_fn: Callable[..., dict[str, Any]] = audit_source_channel_markers,
    sender_audit_fn: Callable[..., dict[str, Any]] = audit_run_sender_integrity,
    session_model_audit_fn: Callable[..., dict[str, Any]] = audit_session_model_integrity,
) -> dict[str, Any]:
    health = _load_health_state(health_path)
    summary: dict[str, Any] = {"started_at": _now_local_iso()}

    try:
        inspect_summary = inspect_fn(
            runs_dir=runs_dir,
            state_path=watermark_path,
            ledger_path=ledger_path,
            retention_days=retention_days,
        )
        align_summary = align_fn(
            task_root=task_root,
            runs_dir=runs_dir,
            ledger_path=ledger_path,
            watermark_path=watermark_path,
            state_path=alignment_state_path,
        )
        source_channel_audit = source_channel_audit_fn(
            task_root=task_root,
            legacy_cutoff_iso=source_channel_legacy_cutoff_iso,
            include_task_docs=source_channel_include_task_docs,
        )
        sender_identity_audit = sender_audit_fn(
            runs_dir=runs_dir,
            legacy_cutoff_iso=sender_legacy_cutoff_iso,
        )
        session_model_audit = session_model_audit_fn(base_dir=runs_dir.parent)
        source_channel_issue = ""
        sender_identity_issue = ""
        source_channel_issue_cleared = ""
        sender_identity_issue_cleared = ""
        if int(source_channel_audit.get("missing_count") or 0) > 0 or int(
            source_channel_audit.get("invalid_count") or 0
        ) > 0:
            source_channel_issue = _write_source_channel_issue(task_root, source_channel_audit) or ""
        else:
            source_channel_issue_cleared = _clear_issue_file(task_root, SOURCE_CHANNEL_ISSUE_FILENAME)
        if int(sender_identity_audit.get("missing_count") or 0) > 0 or int(
            sender_identity_audit.get("invalid_count") or 0
        ) > 0:
            sender_identity_issue = _write_sender_identity_issue(task_root, sender_identity_audit) or ""
        else:
            sender_identity_issue_cleared = _clear_issue_file(task_root, SENDER_IDENTITY_ISSUE_FILENAME)
        now_iso = _now_local_iso()
        active_guard_rules: list[dict[str, Any]] = []
        if source_channel_issue:
            active_guard_rules.append(
                {
                    "rule_key": "source_channel_marker_integrity",
                    "summary": "来源通道标识缺失/无效，需要修复回执可追溯性",
                    "issue_path": source_channel_issue,
                    "evidence_refs": [source_channel_issue],
                }
            )
        if sender_identity_issue:
            active_guard_rules.append(
                {
                    "rule_key": "sender_identity_integrity",
                    "summary": "发送者身份字段缺失/无效，需要修复发送者可追溯性",
                    "issue_path": sender_identity_issue,
                    "evidence_refs": [sender_identity_issue],
                }
            )
        guard_runtime = _build_guard_runtime(
            health=health,
            active_rules=active_guard_rules,
            now_iso=now_iso,
        )
        health["consecutive_failures"] = 0
        health["last_status"] = "ok"
        health["last_error"] = ""
        health["total_runs"] = int(health.get("total_runs") or 0) + 1
        health["last_run_at"] = now_iso
        _write_json(health_path, health)
        summary.update(
            {
                "ok": True,
                "inspect": inspect_summary,
                "align": align_summary,
                "source_channel_audit": source_channel_audit,
                "sender_identity_audit": sender_identity_audit,
                "session_model_audit": session_model_audit,
                "health": health,
                "escalated_issue_path": "",
                "source_channel_issue_path": source_channel_issue,
                "sender_identity_issue_path": sender_identity_issue,
                "source_channel_issue_cleared_path": source_channel_issue_cleared,
                "sender_identity_issue_cleared_path": sender_identity_issue_cleared,
                "guard_runtime": guard_runtime,
                "finished_at": now_iso,
            }
        )
        return summary
    except Exception as exc:
        err = f"{type(exc).__name__}: {exc}"
        now_iso = _now_local_iso()
        health["consecutive_failures"] = int(health.get("consecutive_failures") or 0) + 1
        health["last_status"] = "error"
        health["last_error"] = err
        health["total_runs"] = int(health.get("total_runs") or 0) + 1
        health["last_run_at"] = now_iso

        issue_path = ""
        if int(health["consecutive_failures"]) >= max(1, int(fail_threshold or 1)):
            issue_path = _write_failure_issue(task_root, err, max(1, int(fail_threshold or 1)), health) or ""
        guard_runtime = _build_guard_runtime(
            health=health,
            active_rules=[
                {
                    "rule_key": "inspection_scheduler_failure",
                    "summary": "自动巡查链路失效，调度不可保存或不可执行",
                    "issue_path": issue_path,
                    "fatal_hit": True,
                    "fatal_condition": "自动巡查链路失效",
                    "evidence_refs": [issue_path, str(health_path)],
                }
            ],
            now_iso=now_iso,
        )
        _write_json(health_path, health)

        summary.update(
            {
                "ok": False,
                "error": err,
                "health": health,
                "escalated_issue_path": issue_path,
                "source_channel_issue_path": "",
                "sender_identity_issue_path": "",
                "guard_runtime": guard_runtime,
                "finished_at": now_iso,
            }
        )
        return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run incremental inspector + state aligner with health tracking")
    ap.add_argument("--task-root", default="任务规划", help="task planning root")
    ap.add_argument("--runs-dir", default=".runs", help="runs directory")
    ap.add_argument("--watermark-path", default=".run/inspection/watermark.json", help="watermark path")
    ap.add_argument("--ledger-path", default=".run/inspection/ledger.jsonl", help="ledger jsonl path")
    ap.add_argument("--alignment-state-path", default=".run/inspection/alignment_state.json", help="align state path")
    ap.add_argument("--health-path", default=".run/inspection/health.json", help="scheduler health state path")
    ap.add_argument("--retention-days", type=int, default=90, help="processed runs retention days")
    ap.add_argument("--fail-threshold", type=int, default=2, help="consecutive failure threshold for escalation")
    ap.add_argument(
        "--source-channel-legacy-cutoff",
        default="2026-02-21T01:08:00+0800",
        help="docs older than this cutoff are counted as legacy for source-channel marker audit",
    )
    ap.add_argument(
        "--source-channel-include-task-docs",
        action="store_true",
        help="also audit 任务/*.md for source-channel marker",
    )
    ap.add_argument(
        "--sender-legacy-cutoff",
        default="2026-02-21T04:01:00+0800",
        help="runs older than this cutoff without sender fields are counted as legacy",
    )
    args = ap.parse_args(argv)

    summary = run_once(
        task_root=Path(args.task_root).resolve(),
        runs_dir=Path(args.runs_dir).resolve(),
        watermark_path=Path(args.watermark_path).resolve(),
        ledger_path=Path(args.ledger_path).resolve(),
        alignment_state_path=Path(args.alignment_state_path).resolve(),
        health_path=Path(args.health_path).resolve(),
        retention_days=max(1, int(args.retention_days or 1)),
        fail_threshold=max(1, int(args.fail_threshold or 1)),
        source_channel_legacy_cutoff_iso=str(args.source_channel_legacy_cutoff or "").strip()
        or "2026-02-21T01:08:00+0800",
        source_channel_include_task_docs=bool(args.source_channel_include_task_docs),
        sender_legacy_cutoff_iso=str(args.sender_legacy_cutoff or "").strip() or "2026-02-21T04:01:00+0800",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
