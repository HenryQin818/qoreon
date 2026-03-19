from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any


STATUS_REPORT_SOURCE_REL = Path("docs/status-report/task-dashboard-status-report.json")


def _as_str(value: Any) -> str:
    return "" if value is None else str(value)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _path_for_public(repo_root: Path, path: Path | None) -> str:
    if path is None:
        return ""
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except Exception:
        return ""


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


def _build_repo_snapshot(repo_root: Path) -> dict[str, Any]:
    dirty_output = _git_stdout(repo_root, "status", "--short")
    dirty_lines = [line for line in dirty_output.splitlines() if line.strip()]
    return {
        "repo_root": repo_root.name,
        "branch": _git_stdout(repo_root, "branch", "--show-current"),
        "head": _git_stdout(repo_root, "rev-parse", "--short", "HEAD"),
        "remote_origin": "",
        "dirty_count": len(dirty_lines),
        "dirty_preview": dirty_lines[:8],
    }


def load_status_report_source(script_dir: Path) -> tuple[Path, dict[str, Any], str]:
    source_path = (script_dir / STATUS_REPORT_SOURCE_REL).resolve()
    if not source_path.exists():
        return source_path, {}, f"missing: {source_path}"
    try:
        payload = json.loads(source_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return source_path, {}, f"invalid_json: {exc}"
    if not isinstance(payload, dict):
        return source_path, {}, "invalid_payload: root must be object"
    return source_path, payload, ""


def _normalize_rows(rows: Any) -> list[dict[str, Any]]:
    return [_as_dict(row) for row in _as_list(rows) if isinstance(row, dict)]


def build_status_report_page_data(
    script_dir: Path,
    *,
    generated_at: str,
    dashboard: dict[str, Any],
    links: dict[str, Any],
) -> dict[str, Any]:
    source_path, source_payload, source_error = load_status_report_source(script_dir)
    repo_snapshot = _build_repo_snapshot(script_dir)

    page = _as_dict(source_payload.get("page"))
    hero = _as_dict(source_payload.get("hero"))

    report = {
        "title": _as_str(page.get("title")).strip() or "项目情况汇报",
        "subtitle": _as_str(page.get("subtitle")).strip() or "把环境、仓库、当前主线和下一步统一收敛到一页里。",
        "hero": {
            "kicker": _as_str(hero.get("kicker")).strip() or "Project Status Brief",
            "headline": _as_str(hero.get("headline")).strip() or "当前项目状态总览",
            "summary": _as_str(hero.get("summary")).strip(),
        },
        "summary_cards": _normalize_rows(source_payload.get("summary_cards")),
        "workstreams": _normalize_rows(source_payload.get("workstreams")),
        "environment_matrix": _normalize_rows(source_payload.get("environment_matrix")),
        "milestones": _normalize_rows(source_payload.get("milestones")),
        "risks": _normalize_rows(source_payload.get("risks")),
        "next_actions": _normalize_rows(source_payload.get("next_actions")),
        "updates": _normalize_rows(source_payload.get("updates")),
        "references": _normalize_rows(source_payload.get("references")),
        "update_rules": [str(item).strip() for item in _as_list(source_payload.get("update_rules")) if str(item).strip()],
        "source_file": _path_for_public(script_dir, source_path),
        "source_error": source_error,
        "rebuild_command": "python3 build_project_task_dashboard.py",
        "repo_snapshot": repo_snapshot,
    }

    return {
        "generated_at": generated_at,
        "dashboard": dashboard,
        "links": links,
        "status_report": report,
    }
