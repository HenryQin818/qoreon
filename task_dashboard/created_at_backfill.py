from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from .helpers import atomic_write_text, now_iso
from .parser_md import iter_items
from .task_identity import ensure_task_created_at, extract_task_identity_from_markdown
from .utils import safe_read_text


_TASK_NAME_PREFIX_RE = re.compile(r"^(?:【[^】]+】)+")
_TASK_DATE_PREFIX_RE = re.compile(r"^(20\d{6})(?:[-_].*)?$")


def _strip_task_tags(filename: str) -> str:
    stem = Path(str(filename or "")).stem.strip()
    return _TASK_NAME_PREFIX_RE.sub("", stem).strip()


def _filename_date_prefix(task_path: str) -> str:
    name = _strip_task_tags(task_path)
    match = _TASK_DATE_PREFIX_RE.match(name)
    if not match:
        return ""
    return str(match.group(1) or "").strip()


def _date_prefix_to_iso(date_prefix: str) -> str:
    text = str(date_prefix or "").strip()
    if not text:
        return ""
    try:
        parsed = datetime.strptime(text, "%Y%m%d")
    except Exception:
        return ""
    return parsed.strftime("%Y-%m-%dT00:00:00+0800")


def _git_first_added_iso(repo_root: Path, task_path: str) -> str:
    root = Path(repo_root).expanduser().resolve()
    rel_path = str(task_path or "").strip()
    if not rel_path:
        return ""
    try:
        proc = subprocess.run(
            ["git", "log", "--diff-filter=A", "--follow", "--format=%aI", "--", rel_path],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:
        return ""
    if proc.returncode not in {0, 128}:
        return ""
    rows = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    return rows[-1] if rows else ""


def build_created_at_inventory(
    *,
    repo_root: Path,
    task_root_rel: str = "任务规划",
    project_id: str = "task_dashboard",
    project_name: str = "task_dashboard",
) -> dict[str, Any]:
    root = Path(repo_root).expanduser().resolve()
    items = iter_items(
        root=root,
        project_id=project_id,
        project_name=project_name,
        task_root_rel=task_root_rel,
    )
    task_items = [item for item in items if item.type == "任务"]
    missing = [item for item in task_items if not str(item.created_at or "").strip()]
    rows: list[dict[str, Any]] = []
    grade_counter: Counter[str] = Counter()
    channel_counter: Counter[str] = Counter()
    for item in missing:
        git_created_at = _git_first_added_iso(root, item.path)
        filename_date = _filename_date_prefix(item.path)
        filename_candidate = _date_prefix_to_iso(filename_date)
        evidence_grade = "NONE"
        evidence_source = ""
        evidence_ref = ""
        candidate_created_at = ""
        skip_reason = "no_reliable_evidence"
        auto_apply_eligible = False
        if git_created_at:
            evidence_grade = "A"
            evidence_source = "git_first_add"
            evidence_ref = item.path
            candidate_created_at = git_created_at
            skip_reason = ""
            auto_apply_eligible = True
        elif filename_candidate:
            evidence_grade = "C"
            evidence_source = "filename_date_prefix"
            evidence_ref = item.path
            candidate_created_at = filename_candidate
            skip_reason = "manual_review_only"
        row = {
            "task_path": item.path,
            "channel": item.channel,
            "status": item.status,
            "title": item.title,
            "task_id": str(item.task_id or "").strip(),
            "updated_at": str(item.updated_at or "").strip(),
            "filename_date_prefix": filename_date,
            "candidate_created_at": candidate_created_at,
            "evidence_grade": evidence_grade,
            "evidence_source": evidence_source,
            "evidence_ref": evidence_ref,
            "skip_reason": skip_reason,
            "auto_apply_eligible": auto_apply_eligible,
        }
        rows.append(row)
        grade_counter[evidence_grade] += 1
        channel_counter[item.channel] += 1
    rows.sort(
        key=lambda row: (
            str(row.get("evidence_grade") or ""),
            str(row.get("candidate_created_at") or ""),
            str(row.get("task_path") or ""),
        )
    )
    return {
        "generated_at": now_iso(),
        "repo_root": str(root),
        "task_root_rel": task_root_rel,
        "summary": {
            "task_total": len(task_items),
            "missing_created_at_total": len(rows),
            "grade_counts": dict(grade_counter),
            "channel_counts": dict(channel_counter),
        },
        "rows": rows,
    }


def render_created_at_inventory_markdown(payload: dict[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload, dict) else {}
    rows = payload.get("rows") if isinstance(payload, dict) else []
    grade_counts = dict(summary.get("grade_counts") or {})
    channel_counts = dict(summary.get("channel_counts") or {})
    lines = [
        "# 2026-04-06-历史任务created_at缺失样本与候选清单-v1",
        "",
        f"更新时间：{payload.get('generated_at') or ''}",
        "状态：已生成 / 待审阅",
        "",
        "## 盘点摘要",
        f"- 正式任务总数：{summary.get('task_total') or 0}",
        f"- created_at 缺失样本：{summary.get('missing_created_at_total') or 0}",
        f"- A档候选：{grade_counts.get('A', 0)}",
        f"- B档候选：{grade_counts.get('B', 0)}",
        f"- C档候选：{grade_counts.get('C', 0)}",
        f"- 无可靠证据：{grade_counts.get('NONE', 0)}",
        "",
        "## 证据口径",
        "- `A档`：git 首次入库时间，可直接进入后续 apply 审阅。",
        "- `C档`：仅根据文件名日期前缀生成，必须人工审阅，不进入自动写回。",
        "- `NONE`：当前没有可靠证据，继续保持空值。",
        "",
        "## 渠道分布",
        "| 通道 | 缺失数 |",
        "| --- | ---: |",
    ]
    for channel, count in sorted(channel_counts.items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"| {channel} | {count} |")
    lines.extend(
        [
            "",
            "## 候选清单",
            "| 证据等级 | 候选 created_at | 任务路径 | 标题 | skip_reason |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for row in rows:
        task_path = str(row.get("task_path") or "")
        title = str(row.get("title") or "").replace("|", "\\|")
        candidate = str(row.get("candidate_created_at") or "")
        grade = str(row.get("evidence_grade") or "")
        skip_reason = str(row.get("skip_reason") or "")
        lines.append(
            f"| {grade} | {candidate or '—'} | {task_path} | {title or '—'} | {skip_reason or '—'} |"
        )
    return "\n".join(lines).rstrip() + "\n"


def write_created_at_inventory(
    *,
    repo_root: Path,
    output_json: Path,
    output_md: Path,
    task_root_rel: str = "任务规划",
    project_id: str = "task_dashboard",
    project_name: str = "task_dashboard",
) -> dict[str, Any]:
    payload = build_created_at_inventory(
        repo_root=repo_root,
        task_root_rel=task_root_rel,
        project_id=project_id,
        project_name=project_name,
    )
    atomic_write_text(Path(output_json), json.dumps(payload, ensure_ascii=False, indent=2))
    atomic_write_text(Path(output_md), render_created_at_inventory_markdown(payload))
    return payload


def apply_created_at_candidates(
    *,
    repo_root: Path,
    payload: dict[str, Any],
    allowed_grades: tuple[str, ...] = ("A", "B", "C"),
) -> dict[str, Any]:
    root = Path(repo_root).expanduser().resolve()
    rows = payload.get("rows") if isinstance(payload, dict) else []
    applied: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    grade_set = {str(item or "").strip().upper() for item in allowed_grades if str(item or "").strip()}
    for row in rows if isinstance(rows, list) else []:
        task_path = str(row.get("task_path") or "").strip()
        grade = str(row.get("evidence_grade") or "").strip().upper()
        candidate_created_at = str(row.get("candidate_created_at") or "").strip()
        if not task_path or not candidate_created_at or grade not in grade_set:
            skipped.append(
                {
                    "task_path": task_path,
                    "candidate_created_at": candidate_created_at,
                    "reason": "candidate_not_allowed",
                }
            )
            continue
        try:
            target = (root / task_path).resolve()
            target.relative_to(root)
        except Exception:
            skipped.append(
                {
                    "task_path": task_path,
                    "candidate_created_at": candidate_created_at,
                    "reason": "path_outside_repo",
                }
            )
            continue
        if not target.is_file():
            skipped.append(
                {
                    "task_path": task_path,
                    "candidate_created_at": candidate_created_at,
                    "reason": "file_missing",
                }
            )
            continue
        original = safe_read_text(target)
        current_identity = extract_task_identity_from_markdown(original)
        current_created_at = str(current_identity.get("created_at") or "").strip()
        if current_created_at:
            skipped.append(
                {
                    "task_path": task_path,
                    "candidate_created_at": candidate_created_at,
                    "reason": "created_at_already_present",
                }
            )
            continue
        updated = ensure_task_created_at(original, created_at=candidate_created_at)
        if updated == original:
            skipped.append(
                {
                    "task_path": task_path,
                    "candidate_created_at": candidate_created_at,
                    "reason": "no_change",
                }
            )
            continue
        atomic_write_text(target, updated)
        applied.append(
            {
                "task_path": task_path,
                "candidate_created_at": candidate_created_at,
                "evidence_grade": grade,
            }
        )
    return {
        "generated_at": now_iso(),
        "repo_root": str(root),
        "summary": {
            "applied_total": len(applied),
            "skipped_total": len(skipped),
            "allowed_grades": sorted(grade_set),
        },
        "applied": applied,
        "skipped": skipped,
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="历史任务 created_at 缺失样本盘点与候选清单生成")
    parser.add_argument("--repo-root", default=".", help="仓库根目录")
    parser.add_argument("--task-root-rel", default="任务规划", help="任务根目录相对路径")
    parser.add_argument("--project-id", default="task_dashboard", help="项目 ID")
    parser.add_argument("--project-name", default="task_dashboard", help="项目名称")
    parser.add_argument("--output-json", required=True, help="JSON 输出路径")
    parser.add_argument("--output-md", required=True, help="Markdown 输出路径")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    payload = write_created_at_inventory(
        repo_root=Path(args.repo_root),
        output_json=Path(args.output_json),
        output_md=Path(args.output_md),
        task_root_rel=args.task_root_rel,
        project_id=args.project_id,
        project_name=args.project_name,
    )
    summary = payload.get("summary") if isinstance(payload, dict) else {}
    print(
        json.dumps(
            {
                "ok": True,
                "missing_created_at_total": summary.get("missing_created_at_total", 0),
                "grade_counts": summary.get("grade_counts", {}),
                "output_json": str(Path(args.output_json)),
                "output_md": str(Path(args.output_md)),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
