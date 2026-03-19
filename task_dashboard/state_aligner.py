from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RunEvidence:
    run_id: str
    status: str
    channel_name: str
    created_at: str
    error: str
    message: str
    last_message: str
    log_tail: str


def _now_local() -> datetime:
    return datetime.now().astimezone()


def _fmt_update_time(dt: datetime | None = None) -> str:
    x = dt or _now_local()
    return x.strftime("%Y-%m-%d %H:%M:%S %z")


def _read_text(path: Path, limit: int = 120_000) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")[:limit]


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _extract_latest_processed_ids(ledger_path: Path, watermark_path: Path) -> list[str]:
    if ledger_path.exists():
        lines = ledger_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        for line in reversed(lines):
            s = line.strip()
            if not s:
                continue
            try:
                obj = json.loads(s)
            except Exception:
                continue
            ids = obj.get("processed_run_ids")
            if isinstance(ids, list):
                return [str(x).strip() for x in ids if str(x).strip()]
    if watermark_path.exists():
        try:
            obj = _read_json(watermark_path)
        except Exception:
            return []
        ids = obj.get("processed_run_ids")
        if isinstance(ids, list):
            return [str(x).strip() for x in ids if str(x).strip()]
    return []


def _load_alignment_state(path: Path) -> dict[str, Any]:
    default = {"version": 1, "aligned_run_ids": [], "last_aligned_at": ""}
    if not path.exists():
        return default
    try:
        raw = _read_json(path)
    except Exception:
        return default
    ids = raw.get("aligned_run_ids")
    if not isinstance(ids, list):
        ids = []
    return {
        "version": int(raw.get("version") or 1),
        "aligned_run_ids": [str(x).strip() for x in ids if str(x).strip()],
        "last_aligned_at": str(raw.get("last_aligned_at") or ""),
    }


def _resolve_channel_dir(task_root: Path, channel_name: str) -> Path | None:
    target = (task_root / channel_name).resolve()
    if target.exists() and target.is_dir():
        return target
    # fallback: fuzzy match when aliases exist
    for p in task_root.iterdir():
        if p.is_dir() and channel_name in p.name:
            return p.resolve()
    return None


def _short_text(s: str, limit: int = 220) -> str:
    t = " ".join(str(s or "").replace("\r", "\n").split())
    return t[:limit]


def _make_slug(s: str, fallback: str = "自动补录") -> str:
    base = _short_text(s, limit=40)
    base = re.sub(r"[`~!@#$%^&*()+={}\[\]|\\:;\"'<>,.?/]+", " ", base)
    base = re.sub(r"\s+", "-", base).strip("-")
    base = re.sub(r"-{2,}", "-", base)
    return (base[:28] or fallback).strip("-")


_NOISE_CONTROL_PATTERNS = (
    r"仅回复[:：]?\s*ok",
    r"只回复[:：]?\s*ok",
    r"连通性验收",
    r"初始化阶段",
    r"全局职责通知",
    r"协同派单",
    r"监督式执行通知",
    r"监督式讨论通知",
    r"系统讨论征询",
    r"启动跟催",
    r"回收续跑",
    r"硬门槛督办",
    r"来源通道-",
    r"系统主动回执",
    r"请先熟悉项目并确认你的职责边界",
    r"你觉得这个工作安排",
)
_NOISE_CONTROL_RE = re.compile("|".join(f"(?:{p})" for p in _NOISE_CONTROL_PATTERNS), re.IGNORECASE)


def _should_skip_issue_alignment(ev: RunEvidence, reason: str) -> tuple[bool, str]:
    reason_code = str(reason or "").split(";", 1)[0].strip()
    if reason_code not in {"done-insufficient-evidence", "error-needs-followup"}:
        return False, ""

    text = f"{ev.message}\n{ev.last_message}"
    if _NOISE_CONTROL_RE.search(text):
        return True, "control-message-noise"

    compact_last = _short_text(ev.last_message, limit=64).lower()
    if reason_code == "done-insufficient-evidence" and compact_last in {"ok", "收到", "已收到"}:
        return True, "low-signal-ack"

    if "[来源通道: 系统]" in text and "回执任务" in text:
        return True, "system-callback-noise"

    return False, ""


def _run_evidence(runs_dir: Path, run_id: str) -> RunEvidence | None:
    meta_path = runs_dir / f"{run_id}.json"
    if not meta_path.exists():
        return None
    try:
        meta = _read_json(meta_path)
    except Exception:
        return None

    base = runs_dir / run_id
    msg = _read_text(base.with_suffix(".msg.txt"), limit=120_000)
    last = _read_text(base.with_suffix(".last.txt"), limit=120_000)
    log = _read_text(base.with_suffix(".log.txt"), limit=120_000)
    return RunEvidence(
        run_id=run_id,
        status=str(meta.get("status") or "").strip().lower(),
        channel_name=str(meta.get("channelName") or "").strip(),
        created_at=str(meta.get("createdAt") or "").strip(),
        error=str(meta.get("error") or "").strip(),
        message=msg,
        last_message=last,
        log_tail=log[-50_000:],
    )


def _confidence(ev: RunEvidence) -> tuple[str, int, str]:
    text = f"{ev.last_message}\n{ev.message}\n{ev.log_tail}"
    text_l = text.lower()
    completion_keywords = ["已完成", "已处理", "已修复", "已落地", "处理完成", "完成了", "已按"]
    has_completion = any(k in text for k in completion_keywords)
    has_file_ref = bool(re.search(r"(web/|task_dashboard/|server\.py|run_local\.sh|docs/|tests/)", text))
    has_error_hint = any(
        k in text_l
        for k in [
            "timeout",
            "interrupted",
            "transport channel closed",
            "stream disconnected",
            "error sending request",
        ]
    )
    score = 0
    if ev.status == "done":
        score += 35
        if ev.last_message.strip():
            score += 25
        if has_completion:
            score += 25
        if has_file_ref:
            score += 15
        if score >= 70:
            return "high", score, "done-high-confidence"
        return "medium", score, "done-insufficient-evidence"
    if ev.status == "error":
        score += 40
        if ev.error.strip() or has_error_hint:
            score += 35
        if has_file_ref:
            score += 10
        return "medium", score, "error-needs-followup"
    return "low", 20, "non-terminal-or-unknown"


def _render_archive_md(ev: RunEvidence, reason: str) -> str:
    title = _make_slug(ev.message, fallback="反向补录")
    return (
        f"# 反向补录-{title}\n"
        f"更新时间：{_fmt_update_time()}\n\n"
        "## 目标\n"
        "- 基于巡检结果补录执行留痕，并归档保存，避免进度证据丢失。\n\n"
        "## 范围/对象\n"
        f"- 通道：{ev.channel_name}\n"
        f"- run：`{ev.run_id}`\n\n"
        "## 输入/依赖\n"
        f"- `.runs/{ev.run_id}.json`\n"
        f"- `.runs/{ev.run_id}.msg.txt`\n"
        f"- `.runs/{ev.run_id}.last.txt`\n\n"
        "## 干系方（通道）\n"
        f"- {ev.channel_name}\n"
        "- 子级05-任务巡检与留痕（自动化）\n\n"
        "## 步骤\n"
        "1. 读取run结果并抽取完成证据。\n"
        "2. 将事项反向补录为归档资料（不计入任务统计）。\n"
        "3. 留痕后等待通道核对。\n\n"
        "## 交付物\n"
        "- 补录归档文档（本文件）。\n\n"
        "## 风险/注意事项\n"
        "- 自动补录仅做归档留痕，最终业务验收结论以人工复核为准。\n\n"
        "## 需要总控确认\n"
        "- 是否将本条补录并入对应阶段任务清单。\n\n"
        "## 证据\n"
        f"- 置信规则：`{reason}`\n"
        f"- 用户输入摘要：{_short_text(ev.message)}\n"
        f"- 最后回复摘要：{_short_text(ev.last_message)}\n"
        f"- 错误信息：{_short_text(ev.error)}\n"
    )


def _render_issue_md(ev: RunEvidence, reason: str) -> str:
    title = _make_slug(ev.message, fallback="巡检异常")
    return (
        f"# 问题-{title}\n"
        f"更新时间：{_fmt_update_time()}\n\n"
        "## 问题描述\n"
        "- 巡检发现当前run不满足“高置信度补录任务”条件，需人工核对。\n\n"
        "## 影响范围\n"
        f"- 通道：{ev.channel_name}\n"
        f"- run：`{ev.run_id}`\n\n"
        "## 来源/触发\n"
        f"- 场景/来源路径：`.runs/{ev.run_id}.json|.msg.txt|.last.txt|.log.txt`\n"
        f"- 触发描述：`{reason}`\n\n"
        "## 讨论关联（可选）\n"
        "- （可补充）\n\n"
        "## 关联任务/反馈\n"
        "- （待关联）\n\n"
        "## 干系方（通道）\n"
        f"- {ev.channel_name}\n"
        "- 子级05-任务巡检与留痕（自动化）\n\n"
        "## 需要资源/答复\n"
        "- 需要通道负责人确认该run应归类为“已完成任务”还是“问题/阻塞”。\n\n"
        "## 处理出口\n"
        "- 转任务/反馈/答复：待确认\n"
        "- 目标通道/路径：待确认\n\n"
        "## 当前结论\n"
        f"- 当前判定：`{reason}`\n"
        f"- run状态：`{ev.status}`\n"
        f"- run错误：{_short_text(ev.error)}\n\n"
        "## 下一步\n"
        "- 人工复核后再进行正式补录或关闭。\n"
    )


def _issue_aggregate_meta(reason: str) -> tuple[str, str, str]:
    reason_code = str(reason or "").split(";", 1)[0].strip() or "unknown"
    if reason_code == "error-needs-followup":
        return (
            reason_code,
            "自动巡检执行异常待跟进",
            "run执行异常或中断，需通道负责人确认处理结论并决定重试/转任务/转阻塞。",
        )
    if reason_code == "done-insufficient-evidence":
        return (
            reason_code,
            "自动巡检完成证据不足待确认",
            "run显示完成但证据不足，需人工确认是否满足“已完成任务”补录条件。",
        )
    return (
        reason_code,
        "自动巡检状态待人工确认",
        "run状态未满足自动补录条件，需人工确认归类与后续动作。",
    )


def _issue_aggregate_filename(reason: str) -> str:
    _, title, _ = _issue_aggregate_meta(reason)
    return f"【待处理】【问题】问题-{title}（聚合）.md"


def _extract_existing_issue_history(md_text: str) -> list[str]:
    lines = md_text.splitlines()
    in_hist = False
    out: list[str] = []
    for line in lines:
        s = line.rstrip("\n")
        if s.strip() == "## 最新巡检记录（最近30条）":
            in_hist = True
            continue
        if not in_hist:
            continue
        if s.startswith("## "):
            break
        if s.startswith("- `"):
            out.append(s)
    return out


def _history_run_id(line: str) -> str:
    m = re.search(r"run=`([^`]+)`", line)
    return str(m.group(1)).strip() if m else ""


def _issue_history_line(ev: RunEvidence, reason_code: str, score: int) -> str:
    return (
        f"- `{_fmt_update_time()}` run=`{ev.run_id}` 状态=`{ev.status or 'unknown'}` "
        f"判定=`{reason_code}` 分数=`{score}` 摘要：{_short_text(ev.message, limit=120)}"
    )


def _render_issue_aggregate_md(ev: RunEvidence, reason: str, score: int, existing_text: str = "") -> str:
    reason_code, title, desc = _issue_aggregate_meta(reason)
    current = _issue_history_line(ev, reason_code, score)
    old_lines = _extract_existing_issue_history(existing_text)
    merged: list[str] = [current]
    seen = {ev.run_id}
    for line in old_lines:
        rid = _history_run_id(line)
        if rid and rid in seen:
            continue
        if rid:
            seen.add(rid)
        merged.append(line)
    merged = merged[:30]
    return (
        f"# 问题-{title}\n"
        f"更新时间：{_fmt_update_time()}\n\n"
        "## 问题描述\n"
        f"- {desc}\n\n"
        "## 影响范围\n"
        f"- 通道：{ev.channel_name}\n"
        f"- 最新run：`{ev.run_id}`\n\n"
        "## 来源/触发\n"
        "- 场景/来源路径：`.runs/<runId>.json|.msg.txt|.last.txt|.log.txt`\n"
        f"- 最新触发描述：`{reason_code};score={score}`\n\n"
        "## 当前结论\n"
        f"- 当前判定：`{reason_code}`\n"
        f"- 最新run状态：`{ev.status}`\n"
        f"- 最新run错误：{_short_text(ev.error)}\n\n"
        "## 最新巡检记录（最近30条）\n"
        + ("\n".join(merged) if merged else "- （暂无）")
        + "\n\n"
        "## 下一步\n"
        "- 由通道负责人复核后，转任务/反馈/答复之一；禁止继续拆分同类问题新文件。\n"
    )


def _next_archive_filename(archive_dir: Path, dt: datetime, slug: str) -> str:
    date_part = dt.strftime("%Y%m%d")
    exists = list(archive_dir.glob(f"【已归档】【归档】{date_part}-*-反向补录-*.md"))
    max_seq = 0
    for p in exists:
        m = re.match(rf"^【已归档】【归档】{date_part}-(\d+)-反向补录-.*\.md$", p.name)
        if not m:
            continue
        max_seq = max(max_seq, int(m.group(1)))
    seq = max_seq + 1
    return f"【已归档】【归档】{date_part}-{seq:02d}-反向补录-{slug}.md"


def align_runs(
    *,
    task_root: Path,
    runs_dir: Path,
    ledger_path: Path,
    watermark_path: Path,
    state_path: Path,
    limit: int = 0,
) -> dict[str, Any]:
    latest_ids = _extract_latest_processed_ids(ledger_path, watermark_path)
    state = _load_alignment_state(state_path)
    aligned_set = set(state.get("aligned_run_ids") or [])
    pending = [rid for rid in latest_ids if rid not in aligned_set]
    if limit and limit > 0:
        pending = pending[:limit]

    created_archives: list[str] = []
    created_issues: list[str] = []
    updated_issues: list[str] = []
    skipped: list[str] = []
    skipped_noise: list[dict[str, str]] = []
    new_aligned: list[str] = []

    for rid in pending:
        ev = _run_evidence(runs_dir, rid)
        if ev is None:
            skipped.append(rid)
            continue
        if not ev.channel_name:
            skipped.append(rid)
            continue
        ch_dir = _resolve_channel_dir(task_root, ev.channel_name)
        if ch_dir is None:
            skipped.append(rid)
            continue

        level, score, reason = _confidence(ev)
        stamp = _now_local()
        slug = _make_slug(ev.message, fallback=f"run-{rid[-6:]}")
        if level == "high" and ev.status == "done":
            out_dir = ch_dir / "归档" / "反向补录"
            out_dir.mkdir(parents=True, exist_ok=True)
            fn = _next_archive_filename(out_dir, stamp, slug)
            out_path = out_dir / fn
            out_path.write_text(_render_archive_md(ev, f"{reason};score={score}"), encoding="utf-8")
            created_archives.append(str(out_path))
            new_aligned.append(rid)
            continue

        skip_issue, skip_reason = _should_skip_issue_alignment(ev, reason)
        if skip_issue:
            skipped_noise.append(
                {
                    "run_id": rid,
                    "channel_name": ev.channel_name,
                    "reason": skip_reason,
                    "original_reason": f"{reason};score={score}",
                }
            )
            new_aligned.append(rid)
            continue

        out_dir = ch_dir / "问题"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / _issue_aggregate_filename(reason)
        existed = out_path.exists()
        old = _read_text(out_path, limit=200_000) if existed else ""
        out_path.write_text(_render_issue_aggregate_md(ev, reason, score, old), encoding="utf-8")
        if existed:
            updated_issues.append(str(out_path))
        else:
            created_issues.append(str(out_path))
        new_aligned.append(rid)

    aligned_next = sorted(set(aligned_set).union(new_aligned))
    summary = {
        "scan_at": _fmt_update_time(),
        "input_processed_ids": len(latest_ids),
        "pending_ids": len(pending),
        # Backward compatibility: keep created_tasks/created_task_paths as aliases.
        "created_tasks": len(created_archives),
        "created_archives": len(created_archives),
        "created_issues": len(created_issues),
        "updated_issues": len(updated_issues),
        "skipped_noise": len(skipped_noise),
        "skipped": len(skipped),
        "created_task_paths": created_archives,
        "created_archive_paths": created_archives,
        "created_issue_paths": created_issues,
        "updated_issue_paths": updated_issues,
        "skipped_run_ids": skipped,
        "skipped_noise_items": skipped_noise,
        "aligned_run_ids_added": new_aligned,
        "backfill_write_mode": "archive_only_v2",
    }
    state_out = {
        "version": 1,
        "last_aligned_at": summary["scan_at"],
        "aligned_run_ids": aligned_next,
    }
    _write_json(state_path, state_out)
    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Align incremental run results into task/problem backfill docs")
    ap.add_argument("--task-root", default="任务规划", help="task planning root directory")
    ap.add_argument("--runs-dir", default=".runs", help="runs directory")
    ap.add_argument("--ledger-path", default=".run/inspection/ledger.jsonl", help="incremental scan ledger path")
    ap.add_argument("--watermark-path", default=".run/inspection/watermark.json", help="watermark path")
    ap.add_argument("--state-path", default=".run/inspection/alignment_state.json", help="alignment state path")
    ap.add_argument("--limit", type=int, default=0, help="max run count for this alignment round (0=unlimited)")
    args = ap.parse_args(argv)

    summary = align_runs(
        task_root=Path(args.task_root).resolve(),
        runs_dir=Path(args.runs_dir).resolve(),
        ledger_path=Path(args.ledger_path).resolve(),
        watermark_path=Path(args.watermark_path).resolve(),
        state_path=Path(args.state_path).resolve(),
        limit=max(0, int(args.limit or 0)),
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
