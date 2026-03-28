from __future__ import annotations

import argparse
import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

from .config import load_dashboard_config
from .domain import normalize_task_status
from .model import Item
from .open_source_sync import build_open_source_sync_page_data
from .overview import build_overview
from .parser_md import iter_items
from .project_source import resolve_project_source
from .render import render_from_template
from .runtime.project_execution_context import (
    build_project_execution_context,
    diff_override_fields,
)
from .runtime.session_context import detect_git_branch
from .session_health import build_session_health_page, normalize_project_session_health_config
from .session_store import SessionStore
from .sessions import channel_session_map, parse_session_id_list, parse_session_json
from .status_report import build_status_report_page_data
from .utils import iso_now_local, repo_root_from_here


def _as_list(v: Any) -> list[Any]:
    if v is None:
        return []
    if isinstance(v, list):
        return v
    return [v]


def _as_str(v: Any) -> str:
    return "" if v is None else str(v)


def _as_optional_bool(v: Any) -> bool | None:
    if isinstance(v, bool):
        return v
    if v is None:
        return None
    txt = str(v).strip().lower()
    if txt in {"1", "true", "yes", "on"}:
        return True
    if txt in {"0", "false", "no", "off"}:
        return False
    return None


def _write_json_file(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


def _replace_path_with_symlink(link_path: Path, target_path: Path) -> None:
    link_path.parent.mkdir(parents=True, exist_ok=True)
    if link_path.is_symlink() or link_path.exists():
        if link_path.is_dir() and not link_path.is_symlink():
            shutil.rmtree(link_path)
        else:
            link_path.unlink()
    relative_target = os.path.relpath(target_path, start=link_path.parent)
    link_path.symlink_to(relative_target, target_is_directory=target_path.is_dir())


def _sync_public_share_links(root: Path, dist_root: Path) -> None:
    worklog_root = (root / "docs" / "worklog").resolve()
    share_worklog_link = dist_root / "share" / "worklog"
    if not worklog_root.exists():
        if share_worklog_link.is_symlink() or share_worklog_link.exists():
            if share_worklog_link.is_dir() and not share_worklog_link.is_symlink():
                shutil.rmtree(share_worklog_link)
            else:
                share_worklog_link.unlink()
        return
    _replace_path_with_symlink(share_worklog_link, worklog_root)


def _resolve_optional_path(root: Path, raw: str) -> Path | None:
    value = _as_str(raw).strip()
    if not value:
        return None
    path = Path(value)
    return path.resolve() if path.is_absolute() else (root / value).resolve()


def _resolve_project_runs_root(root: Path, project_cfg: dict[str, Any]) -> Path | None:
    raw_context = (
        project_cfg.get("execution_context")
        if isinstance(project_cfg.get("execution_context"), dict)
        else {}
    )
    project_root_rel = _as_str(project_cfg.get("project_root_rel")).strip()
    environment = _as_str(raw_context.get("environment")).strip() or "stable"
    candidates: list[Path] = []
    for raw in (
        _as_str(raw_context.get("runs_root")).strip(),
        "",
    ):
        resolved = _resolve_optional_path(root, raw)
        if resolved:
            candidates.append(resolved)
    runtime_root = _resolve_optional_path(root, _as_str(raw_context.get("runtime_root")).strip())
    if runtime_root:
        candidates.append((runtime_root / ".runs").resolve())
    runtime_root_rel = _as_str(project_cfg.get("runtime_root_rel")).strip()
    runtime_root_from_rel = _resolve_optional_path(root, runtime_root_rel)
    if runtime_root_from_rel:
        candidates.append((runtime_root_from_rel / ".runs").resolve())
    project_root = _resolve_optional_path(root, project_root_rel)
    if project_root:
        candidates.append((project_root / ".runtime" / environment / ".runs").resolve())
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        if candidate.exists() and candidate.is_dir():
            return candidate
    return candidates[0] if candidates else None


def _normalize_preview_text(raw: Any, *, limit: int = 220) -> str:
    value = _as_str(raw).strip()
    if not value:
        return ""
    value = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", value)
    value = re.sub(r"`([^`]+)`", r"\1", value)
    value = re.sub(r"\s+", " ", value).strip()
    if limit > 0 and len(value) > limit:
        return value[: max(0, limit - 1)].rstrip() + "…"
    return value


def _run_day_key(run_id: str, created_at: str) -> str:
    value = _as_str(created_at).strip()
    if len(value) >= 10 and value[4:5] == "-" and value[7:8] == "-":
        return value[:10]
    match = re.match(r"^(\d{4})(\d{2})(\d{2})-", _as_str(run_id).strip())
    if match:
        return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
    return ""


def _parse_iso_datetime(raw: Any) -> datetime | None:
    value = _as_str(raw).strip()
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    if re.match(r".*[+-]\d{4}$", normalized):
        normalized = normalized[:-2] + ":" + normalized[-2:]
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _pick_run_summary(payload: dict[str, Any]) -> tuple[str, str]:
    for key in ("partialPreview", "lastPreview", "messagePreview", "current_conclusion", "next_action"):
        summary = _normalize_preview_text(payload.get(key))
        if summary:
            return summary, key
    return "", ""


def _build_agent_directory_summary(
    root: Path,
    project_cfg: dict[str, Any],
    *,
    registry: dict[str, Any],
    channel_sessions: list[dict[str, Any]],
) -> dict[str, Any]:
    project_id = _as_str(project_cfg.get("id")).strip()
    runs_root = _resolve_project_runs_root(root, project_cfg)
    today = iso_now_local()[:10]
    agents_from_registry = registry.get("all_agents") if isinstance(registry.get("all_agents"), list) else []
    known_session_ids: set[str] = set()
    known_channels: set[str] = set()
    active_session_ids: set[str] = set()
    for row in channel_sessions:
        session_id = _as_str((row or {}).get("session_id")).strip()
        channel_name = _as_str((row or {}).get("name") or (row or {}).get("channel_name")).strip()
        status = _as_str((row or {}).get("status")).strip().lower()
        if session_id:
            known_session_ids.add(session_id)
            if status == "active":
                active_session_ids.add(session_id)
        if channel_name:
            known_channels.add(channel_name)
    for row in agents_from_registry:
        if not isinstance(row, dict):
            continue
        session_id = _as_str(row.get("session_id")).strip()
        channel_name = _as_str(row.get("channel_name")).strip()
        status = _as_str(row.get("status")).strip().lower()
        if session_id:
            known_session_ids.add(session_id)
            if status == "active":
                active_session_ids.add(session_id)
        if channel_name:
            known_channels.add(channel_name)

    by_session_id: dict[str, dict[str, Any]] = {}
    today_channel_counts: dict[str, int] = {}
    today_run_count = 0
    if runs_root and runs_root.exists() and runs_root.is_dir():
        for run_file in sorted(runs_root.glob("*.json")):
            try:
                payload = json.loads(run_file.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(payload, dict):
                continue
            run_project_id = _as_str(payload.get("projectId")).strip()
            session_id = _as_str(payload.get("sessionId")).strip()
            channel_name = _as_str(payload.get("channelName")).strip()
            if run_project_id and project_id and run_project_id != project_id:
                continue
            if not run_project_id and known_session_ids and session_id and session_id not in known_session_ids and channel_name not in known_channels:
                continue
            if not session_id:
                continue
            run_id = _as_str(payload.get("id")).strip() or run_file.stem
            created_at = _as_str(payload.get("createdAt")).strip()
            finished_at = _as_str(payload.get("finishedAt")).strip()
            last_progress_at = _as_str(payload.get("lastProgressAt")).strip()
            latest_at = last_progress_at or finished_at or created_at
            summary, summary_field = _pick_run_summary(payload)
            row = by_session_id.setdefault(
                session_id,
                {
                    "today_active": False,
                    "today_run_count": 0,
                    "total_run_count": 0,
                    "latest_run_id": "",
                    "latest_status": "",
                    "latest_created_at": "",
                    "latest_channel_name": "",
                    "latest_summary": "",
                    "latest_conclusion": "",
                    "next_action": "",
                    "source_run_id": "",
                    "summary_source": "",
                    "_latest_dt": None,
                },
            )
            row["total_run_count"] = int(row.get("total_run_count") or 0) + 1
            run_day = _run_day_key(run_id, created_at or latest_at)
            if run_day == today:
                row["today_active"] = True
                row["today_run_count"] = int(row.get("today_run_count") or 0) + 1
                today_run_count += 1
                if channel_name:
                    today_channel_counts[channel_name] = int(today_channel_counts.get(channel_name) or 0) + 1
            sort_dt = _parse_iso_datetime(latest_at) or _parse_iso_datetime(created_at)
            latest_known_dt = row.get("_latest_dt")
            should_update_latest = latest_known_dt is None or (
                sort_dt is not None and (latest_known_dt is None or sort_dt >= latest_known_dt)
            )
            if latest_known_dt is None and sort_dt is None and not row.get("latest_run_id"):
                should_update_latest = True
            if should_update_latest:
                row["_latest_dt"] = sort_dt
                row["latest_run_id"] = run_id
                row["latest_status"] = _as_str(payload.get("status")).strip()
                row["latest_created_at"] = latest_at or created_at
                row["latest_channel_name"] = channel_name
                row["latest_summary"] = summary
                row["latest_conclusion"] = _normalize_preview_text(payload.get("current_conclusion"), limit=120)
                row["next_action"] = _normalize_preview_text(payload.get("next_action"), limit=120)
                row["source_run_id"] = _as_str(payload.get("source_run_id")).strip()
                row["summary_source"] = "today" if run_day == today else "history"
                if not row["latest_summary"] and row["latest_conclusion"]:
                    row["latest_summary"] = row["latest_conclusion"]
                elif not row["latest_summary"] and row["next_action"]:
                    row["latest_summary"] = row["next_action"]
                if not row["summary_source"] and summary_field:
                    row["summary_source"] = "history"
    for row in by_session_id.values():
        row.pop("_latest_dt", None)

    active_today_agents = 0
    for session_id in active_session_ids:
        summary_row = by_session_id.get(session_id) or {}
        if bool(summary_row.get("today_active")):
            active_today_agents += 1
    top_channels = sorted(
        (
            {"channel_name": name, "run_count": count}
            for name, count in today_channel_counts.items()
            if name and count > 0
        ),
        key=lambda item: (-int(item.get("run_count") or 0), _as_str(item.get("channel_name")).strip()),
    )[:5]
    return {
        "today": today,
        "generated_at": iso_now_local(),
        "runs_root": str(runs_root) if runs_root else "",
        "today_run_count": today_run_count,
        "active_agent_total": len(active_session_ids),
        "active_today_agents": active_today_agents,
        "inactive_today_agents": max(0, len(active_session_ids) - active_today_agents),
        "top_channels": top_channels,
        "by_session_id": by_session_id,
    }


def _task_item_bundle_dir_name(out_task_path: Path) -> str:
    return f"{out_task_path.stem}.data"


def _task_item_bundle_url(bundle_dir_name: str, file_name: str) -> str:
    return f"{quote(bundle_dir_name)}/items/{quote(file_name)}"


def _unique_existing_paths(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    out: list[Path] = []
    for path in paths:
        try:
            resolved = path.resolve()
        except Exception:
            resolved = path
        key = str(resolved)
        if key in seen:
            continue
        if not resolved.exists() or not resolved.is_dir():
            continue
        seen.add(key)
        out.append(resolved)
    return out


def _project_session_store_dirs(root: Path, script_dir: Path, project_root_rel: str) -> list[Path]:
    candidates: list[Path] = []
    if project_root_rel:
        candidates.append((root / project_root_rel).resolve())
    candidates.append(script_dir)
    candidates.append(root)
    return _unique_existing_paths(candidates)


def _load_project_session_rows(
    root: Path,
    script_dir: Path,
    *,
    project_id: str,
    project_root_rel: str,
) -> list[dict[str, Any]]:
    for base_dir in _project_session_store_dirs(root, script_dir, project_root_rel):
        rows = SessionStore(base_dir).list_sessions(project_id)
        if rows:
            return rows
    return []


def _load_project_registry(root: Path, project_root_rel: str) -> dict[str, Any]:
    if not project_root_rel:
        return {}
    registry_path = (root / project_root_rel / "registry" / "collab-registry.v1.json").resolve()
    if not registry_path.exists():
        return {}
    try:
        payload = json.loads(registry_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _project_execution_context_from_config(
    root: Path,
    project_cfg: dict[str, Any],
) -> dict[str, Any]:
    project_root_rel = _as_str(project_cfg.get("project_root_rel")).strip()
    raw_context = (
        project_cfg.get("execution_context")
        if isinstance(project_cfg.get("execution_context"), dict)
        else {}
    )
    project_root_path = (root / project_root_rel).resolve() if project_root_rel else None
    worktree_root = _as_str(raw_context.get("worktree_root")).strip() or str(project_root_path or "")
    workdir = _as_str(raw_context.get("workdir")).strip() or worktree_root
    branch = _as_str(raw_context.get("branch")).strip()
    if not branch and worktree_root:
        branch = detect_git_branch(worktree_root)
    environment = _as_str(raw_context.get("environment")).strip() or "stable"
    source_ref = {
        "project_id": _as_str(project_cfg.get("id")).strip(),
        "environment": environment,
        "worktree_root": worktree_root,
        "workdir": workdir,
        "branch": branch,
    }
    return build_project_execution_context(
        target=source_ref,
        source=source_ref,
        context_source="project",
    )


def _session_project_execution_context(
    session_row: dict[str, Any],
    project_context: dict[str, Any],
) -> dict[str, Any]:
    existing = (
        dict(session_row.get("project_execution_context") or {})
        if isinstance(session_row.get("project_execution_context"), dict)
        else {}
    )
    if existing.get("target") or existing.get("source"):
        return existing
    target = {
        "project_id": _as_str(session_row.get("project_id")).strip(),
        "channel_name": _as_str(session_row.get("channel_name") or session_row.get("name")).strip(),
        "session_id": _as_str(session_row.get("id") or session_row.get("session_id")).strip(),
        "environment": _as_str(session_row.get("environment")).strip(),
        "worktree_root": _as_str(session_row.get("worktree_root")).strip(),
        "workdir": _as_str(session_row.get("workdir")).strip(),
        "branch": _as_str(session_row.get("branch")).strip(),
    }
    source = dict(project_context.get("target") or {})
    return build_project_execution_context(
        target=target,
        source=source,
        context_source=_as_str(project_context.get("context_source")).strip() or "project",
        override_fields=diff_override_fields(target, source),
        override_source="session",
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=str, default=str(repo_root_from_here(__file__)), help="repo root")
    ap.add_argument("--out", type=str, default="", help="(deprecated) task page output html path (relative to root)")
    ap.add_argument(
        "--out-task",
        type=str,
        default="项目管理-小秘书/项目看板/task-dashboard/dist/project-task-dashboard.html",
        help="task page output html path (relative to root)",
    )
    ap.add_argument(
        "--out-overview",
        type=str,
        default="项目管理-小秘书/项目看板/task-dashboard/dist/project-overview-dashboard.html",
        help="overview page output html path (relative to root)",
    )
    ap.add_argument(
        "--out-communication",
        type=str,
        default="项目管理-小秘书/项目看板/task-dashboard/dist/project-communication-audit.html",
        help="communication audit page output html path (relative to root)",
    )
    ap.add_argument(
        "--out-session-health",
        type=str,
        default="项目管理-小秘书/项目看板/task-dashboard/dist/project-session-health-dashboard.html",
        help="session health page output html path (relative to root)",
    )
    ap.add_argument(
        "--out-status-report",
        type=str,
        default="项目管理-小秘书/项目看板/task-dashboard/dist/project-status-report.html",
        help="status report page output html path (relative to root)",
    )
    ap.add_argument(
        "--out-open-source-sync",
        type=str,
        default="项目管理-小秘书/项目看板/task-dashboard/dist/project-open-source-sync-board.html",
        help="open-source sync board output html path (relative to root)",
    )
    ap.add_argument(
        "--out-agent-directory",
        type=str,
        default="项目管理-小秘书/项目看板/task-dashboard/dist/project-agent-directory.html",
        help="agent directory page output html path (relative to root)",
    )
    ap.add_argument(
        "--out-agent-curtain",
        type=str,
        default="项目管理-小秘书/项目看板/task-dashboard/dist/project-agent-curtain.html",
        help="agent curtain page output html path (relative to root)",
    )
    ap.add_argument(
        "--out-agent-relationship-board",
        type=str,
        default="项目管理-小秘书/项目看板/task-dashboard/dist/project-agent-relationship-board.html",
        help="agent relationship board page output html path (relative to root)",
    )
    ap.add_argument(
        "--with-local-config",
        action="store_true",
        help="explicitly merge config.local.toml (local-only; ignored by git)",
    )
    args = ap.parse_args(argv)

    with_local = bool(args.with_local_config) or str(os.environ.get("TASK_DASHBOARD_WITH_LOCAL_CONFIG") or "").strip() in {
        "1",
        "true",
        "yes",
    }
    task_page_link = str(os.environ.get("TASK_DASHBOARD_TASK_PAGE_LINK") or "project-task-dashboard.html").strip() or "project-task-dashboard.html"
    overview_page_link = str(os.environ.get("TASK_DASHBOARD_OVERVIEW_PAGE_LINK") or "project-overview-dashboard.html").strip() or "project-overview-dashboard.html"
    communication_page_link = str(
        os.environ.get("TASK_DASHBOARD_COMMUNICATION_PAGE_LINK") or "project-communication-audit.html"
    ).strip() or "project-communication-audit.html"
    status_report_page_link = str(
        os.environ.get("TASK_DASHBOARD_STATUS_REPORT_PAGE_LINK") or "project-status-report.html"
    ).strip() or "project-status-report.html"
    open_source_sync_page_link = str(
        os.environ.get("TASK_DASHBOARD_OPEN_SOURCE_SYNC_PAGE_LINK") or "project-open-source-sync-board.html"
    ).strip() or "project-open-source-sync-board.html"
    agent_directory_page_link = str(
        os.environ.get("TASK_DASHBOARD_AGENT_DIRECTORY_PAGE_LINK") or "project-agent-directory.html"
    ).strip() or "project-agent-directory.html"
    agent_curtain_page_link = str(
        os.environ.get("TASK_DASHBOARD_AGENT_CURTAIN_PAGE_LINK") or "project-agent-curtain.html"
    ).strip() or "project-agent-curtain.html"
    agent_relationship_board_page_link = str(
        os.environ.get("TASK_DASHBOARD_AGENT_RELATIONSHIP_BOARD_PAGE_LINK") or "project-agent-relationship-board.html"
    ).strip() or "project-agent-relationship-board.html"
    session_health_page_link = str(
        os.environ.get("TASK_DASHBOARD_SESSION_HEALTH_PAGE_LINK") or "project-session-health-dashboard.html"
    ).strip() or "project-session-health-dashboard.html"

    root = Path(args.root).resolve()
    out_task_rel = args.out.strip() or args.out_task
    out_task_path = (root / out_task_rel).resolve()
    out_overview_path = (root / args.out_overview).resolve()
    out_communication_path = (root / args.out_communication).resolve()
    out_status_report_path = (root / args.out_status_report).resolve()
    out_open_source_sync_path = (root / args.out_open_source_sync).resolve()
    out_agent_directory_path = (root / args.out_agent_directory).resolve()
    out_agent_relationship_board_path = (root / args.out_agent_relationship_board).resolve()
    out_session_health_path = (root / args.out_session_health).resolve()
    out_agent_curtain_path = (root / args.out_agent_curtain).resolve()
    out_task_path.parent.mkdir(parents=True, exist_ok=True)
    out_overview_path.parent.mkdir(parents=True, exist_ok=True)
    out_communication_path.parent.mkdir(parents=True, exist_ok=True)
    out_status_report_path.parent.mkdir(parents=True, exist_ok=True)
    out_open_source_sync_path.parent.mkdir(parents=True, exist_ok=True)
    out_agent_directory_path.parent.mkdir(parents=True, exist_ok=True)
    out_agent_relationship_board_path.parent.mkdir(parents=True, exist_ok=True)
    out_session_health_path.parent.mkdir(parents=True, exist_ok=True)
    out_agent_curtain_path.parent.mkdir(parents=True, exist_ok=True)

    script_dir = Path(__file__).resolve().parent.parent
    cfg = load_dashboard_config(script_dir, with_local=with_local)

    projects_cfg = cfg.get("projects")
    if not isinstance(projects_cfg, list) or not projects_cfg:
        projects_cfg = []

    projects_meta: list[dict[str, Any]] = []
    session_maps: dict[str, dict[str, dict[str, Any]]] = {}

    items: list[Item] = []
    for pc in projects_cfg:
        pid = _as_str((pc or {}).get("id")).strip()
        pname = _as_str((pc or {}).get("name")).strip() or pid
        if not pid:
            continue
        runtime_root_rel = _as_str((pc or {}).get("runtime_root_rel")).strip()
        project_root_rel = _as_str((pc or {}).get("project_root_rel")).strip()
        task_root_rel = _as_str((pc or {}).get("task_root_rel")).strip()
        if not task_root_rel:
            continue
        project_execution_context = _project_execution_context_from_config(root, pc)

        map_from_store: dict[str, dict[str, Any]] = {}
        sessions_from_store = _load_project_session_rows(
            root,
            script_dir,
            project_id=pid,
            project_root_rel=project_root_rel,
        )
        for sess in sessions_from_store:
            ch_name = _as_str(sess.get("channel_name")).strip()
            if not ch_name:
                continue
            session_context = _session_project_execution_context(sess, project_execution_context)
            map_from_store[ch_name] = {
                "name": ch_name,
                "display_name": _as_str(sess.get("display_name")).strip(),
                "display_name_source": _as_str(sess.get("display_name_source")).strip(),
                "alias": _as_str(sess.get("alias")).strip(),
                "session_id": _as_str(sess.get("id")).strip(),
                "desc": "",
                "cli_type": _as_str(sess.get("cli_type")).strip() or "codex",
                "model": _as_str(sess.get("model")).strip(),
                "reasoning_effort": _as_str(sess.get("reasoning_effort")).strip(),
                "environment": _as_str(sess.get("environment")).strip(),
                "branch": _as_str(sess.get("branch")).strip(),
                "worktree_root": _as_str(sess.get("worktree_root")).strip(),
                "workdir": _as_str(sess.get("workdir")).strip(),
                "status": _as_str(sess.get("status")).strip(),
                "session_role": _as_str(sess.get("session_role")).strip(),
                "context_binding_state": _as_str(sess.get("context_binding_state")).strip(),
                "project_execution_context": session_context,
                "is_primary": bool(sess.get("is_primary")),
                "source": "session_store",
            }

        map_from_session_file: dict[str, dict[str, Any]] = {}
        session_json_rel = _as_str((pc or {}).get("session_json_rel")).strip()
        if session_json_rel:
            map_from_session_file = channel_session_map(parse_session_json(root / session_json_rel))
        session_list_rel = _as_str((pc or {}).get("session_list_rel")).strip()
        if session_list_rel:
            list_map = channel_session_map(parse_session_id_list(root / session_list_rel))
            for k, v in list_map.items():
                map_from_session_file.setdefault(k, v)

        channels_cfg = (pc or {}).get("channels")
        if not isinstance(channels_cfg, list):
            channels_cfg = []

        # channels from config: only read name and desc
        channels_out: list[dict[str, Any]] = []
        for ch in channels_cfg:
            if not isinstance(ch, dict):
                continue
            ch_name = _as_str(ch.get("name")).strip()
            if not ch_name:
                continue
            desc = _as_str(ch.get("desc")).strip()
            channels_out.append({"name": ch_name, "desc": desc})

        # Build channel desc lookup from config
        channel_desc_map: dict[str, str] = {}
        for ch in channels_cfg:
            if not isinstance(ch, dict):
                continue
            ch_name = _as_str(ch.get("name")).strip()
            if ch_name:
                channel_desc_map[ch_name] = _as_str(ch.get("desc")).strip()

        # Merge with priority: SessionStore > config.toml(channel metadata only) > legacy session files.
        merged: dict[str, dict[str, Any]] = {}

        # config.toml provides channel metadata only; session binding must come from SessionStore.
        for ch in channels_cfg:
            if not isinstance(ch, dict):
                continue
            ch_name = _as_str(ch.get("name")).strip()
            if not ch_name:
                continue
            base = merged.get(
                ch_name,
                {"name": ch_name, "alias": "", "session_id": "", "cli_type": "codex", "model": "", "reasoning_effort": ""},
            )
            cli_type = _as_str(ch.get("cli_type")).strip()
            desc = _as_str(ch.get("desc")).strip()
            req_raw = ch.get("enable_requirements") if "enable_requirements" in ch else ch.get("enableRequirements")
            req_explicit = _as_optional_bool(req_raw)
            if cli_type:
                base["cli_type"] = cli_type
            if desc:
                base["desc"] = desc
            if req_explicit is not None:
                base["enable_requirements"] = bool(req_explicit)
            if base.get("source") != "session_store":
                base["source"] = "config"
            merged[ch_name] = base

        # Runtime single source: .sessions. Legacy files only backfill channels missing from SessionStore.
        for k, v in map_from_store.items():
            base = merged.get(
                k,
                {"name": k, "alias": "", "session_id": "", "cli_type": "codex", "model": "", "reasoning_effort": ""},
            )
            if v.get("session_id"):
                base["session_id"] = v["session_id"]
            if v.get("alias"):
                base["alias"] = v["alias"]
            if v.get("cli_type"):
                base["cli_type"] = v["cli_type"]
            if v.get("model"):
                base["model"] = _as_str(v.get("model")).strip()
            if v.get("reasoning_effort"):
                base["reasoning_effort"] = _as_str(v.get("reasoning_effort")).strip()
            for field in (
                "display_name",
                "display_name_source",
                "environment",
                "branch",
                "worktree_root",
                "workdir",
                "status",
                "session_role",
                "context_binding_state",
                "project_execution_context",
            ):
                if v.get(field) and not base.get(field):
                    base[field] = v[field]
            if "is_primary" in v:
                base["is_primary"] = bool(v.get("is_primary"))
            if v.get("desc") and not base.get("desc"):
                base["desc"] = _as_str(v.get("desc")).strip()
            base["source"] = "session_store"
            merged[k] = base

        for k, v in map_from_session_file.items():
            base = merged.get(
                k,
                {"name": k, "alias": "", "session_id": "", "cli_type": "codex", "model": "", "reasoning_effort": ""},
            )
            existing_sid = _as_str(base.get("session_id")).strip()
            incoming_sid = _as_str(v.get("session_id")).strip()
            can_fill_primary = not existing_sid
            if can_fill_primary and incoming_sid:
                base["session_id"] = v["session_id"]
            if can_fill_primary and v.get("alias"):
                base["alias"] = v["alias"]
            if can_fill_primary and v.get("cli_type"):
                base["cli_type"] = v["cli_type"]
            if can_fill_primary and v.get("model"):
                base["model"] = _as_str(v.get("model")).strip()
            if can_fill_primary and v.get("reasoning_effort"):
                base["reasoning_effort"] = _as_str(v.get("reasoning_effort")).strip()
            if can_fill_primary:
                base["source"] = "session_json"
            merged[k] = base

        # Ensure all channels from config have entries (even without sessions)
        for ch_name, desc in channel_desc_map.items():
            if ch_name not in merged:
                merged[ch_name] = {
                    "name": ch_name,
                    "alias": "",
                    "session_id": "",
                    "desc": desc,
                    "cli_type": "codex",
                    "model": "",
                    "reasoning_effort": "",
                    "enable_requirements": False,
                    "source": "config",
                }

        session_maps[pid] = merged

        exclude_prefixes: list[str] = []
        items.extend(
            iter_items(
                root=root,
                project_id=pid,
                project_name=pname,
                task_root_rel=task_root_rel,
                exclude_rel_prefixes=exclude_prefixes,
            )
        )
        project_items = [it for it in items if str(getattr(it, "project_id", "") or "") == pid]
        requirement_channels = {
            str(getattr(it, "channel", "") or "").strip()
            for it in project_items
            if str(getattr(it, "type", "") or "").strip() == "需求"
        }

        channel_sessions = []
        for ch_name, s in merged.items():
            req_explicit = _as_optional_bool((s or {}).get("enable_requirements"))
            if req_explicit is not None:
                req_effective = bool(req_explicit)
                req_source = "config"
                req_config_value = bool(req_explicit)
            else:
                req_effective = ch_name in requirement_channels
                req_source = "legacy_detect" if req_effective else "default_false"
                req_config_value = False
            row = {
                "name": ch_name,
                "alias": _as_str((s or {}).get("alias")).strip(),
                "display_name": _as_str((s or {}).get("display_name")).strip(),
                "display_name_source": _as_str((s or {}).get("display_name_source")).strip(),
                "session_id": _as_str((s or {}).get("session_id")).strip(),
                "desc": _as_str((s or {}).get("desc")).strip(),
                "cli_type": _as_str((s or {}).get("cli_type")).strip() or "codex",
                "model": _as_str((s or {}).get("model")).strip(),
                "reasoning_effort": _as_str((s or {}).get("reasoning_effort")).strip(),
                "source": _as_str((s or {}).get("source")).strip(),
                "environment": _as_str((s or {}).get("environment")).strip(),
                "branch": _as_str((s or {}).get("branch")).strip(),
                "worktree_root": _as_str((s or {}).get("worktree_root")).strip(),
                "workdir": _as_str((s or {}).get("workdir")).strip(),
                "status": _as_str((s or {}).get("status")).strip(),
                "session_role": _as_str((s or {}).get("session_role")).strip(),
                "context_binding_state": _as_str((s or {}).get("context_binding_state")).strip(),
                "project_execution_context": dict((s or {}).get("project_execution_context") or {})
                if isinstance((s or {}).get("project_execution_context"), dict)
                else {},
                "is_primary": bool((s or {}).get("is_primary")),
                "enable_requirements": bool(req_config_value),
                "requirements_enabled_effective": bool(req_effective),
                "requirements_source": req_source,
            }
            channel_sessions.append(row)
            # Keep item-level session snapshot aligned with channel-level effective requirements switch.
            s["enable_requirements"] = row["enable_requirements"]
            s["requirements_enabled_effective"] = row["requirements_enabled_effective"]
            s["requirements_source"] = row["requirements_source"]
        channel_sessions.sort(key=lambda x: x.get("name") or "")

        links = []
        for lk in _as_list((pc or {}).get("links")):
            if not isinstance(lk, dict):
                continue
            label = _as_str(lk.get("label")).strip()
            url = _as_str(lk.get("url")).strip()
            if label and url:
                links.append({"label": label, "url": url})

        registry_payload = _load_project_registry(root, project_root_rel)
        agent_directory_summary = _build_agent_directory_summary(
            root,
            pc,
            registry=registry_payload,
            channel_sessions=channel_sessions,
        )

        projects_meta.append(
            {
                "id": pid,
                "name": pname,
                "color": _as_str((pc or {}).get("color")).strip(),
                "description": _as_str((pc or {}).get("description")).strip(),
                "runtime_root_rel": runtime_root_rel,
                "project_root_rel": project_root_rel,
                "task_root_rel": task_root_rel,
                **resolve_project_source(
                    {
                        "project_root_rel": project_root_rel,
                        "task_root_rel": task_root_rel,
                        "runtime_root_rel": runtime_root_rel,
                    }
                ),
                "links": links,
                "project_execution_context": project_execution_context,
                "registry": registry_payload,
                "sessions": [],
                "sessions_json": [],
                "channels": channels_out,
                "channel_sessions": channel_sessions,
                "agent_directory_summary": agent_directory_summary,
                "session_health_config": normalize_project_session_health_config(
                    pid,
                    project_name=pname,
                    raw=(pc or {}).get("session_health"),
                ),
            }
        )

    items_payload = []
    for it in items:
        sess = session_maps.get(it.project_id, {}).get(it.channel)
        row = {
            "project_id": it.project_id,
            "project_name": it.project_name,
            "channel": it.channel,
            "channel_name": it.channel,
            "status": it.status,
            "type": it.type,
            "title": it.title,
            "code": it.code,
            "path": it.path,
            "updated_at": it.updated_at,
            "owner": it.owner,
            "due": it.due,
            "excerpt": it.excerpt,
            "tags": it.tags,
            "session": sess or None,
        }
        if _as_str(it.type).strip() == "任务":
            task_status = normalize_task_status(it.status)
            row.update(
                {
                    "primary_status": task_status.get("primary_status"),
                    "lifecycle_state": task_status.get("lifecycle_state"),
                    "counts_as_wip": bool(task_status.get("counts_as_wip")),
                    "status_flags": task_status.get("status_flags") or {},
                }
            )
        items_payload.append(row)

    overview_items_payload = []
    for it in items_payload:
        if str(it.get("type") or "").strip() != "任务":
            continue
        overview_items_payload.append(
            {
                "project_id": it.get("project_id"),
                "project_name": it.get("project_name"),
                "channel": it.get("channel"),
                "channel_name": it.get("channel_name"),
                "status": it.get("status"),
                "type": it.get("type"),
                "title": it.get("title"),
                "path": it.get("path"),
                "updated_at": it.get("updated_at"),
            }
        )

    overview_data = build_overview(projects_meta, items_payload)

    bundle_dir_name = _task_item_bundle_dir_name(out_task_path)
    bundle_dir_path = out_task_path.parent / bundle_dir_name
    if bundle_dir_path.exists():
        shutil.rmtree(bundle_dir_path)
    item_bundle_projects: dict[str, str] = {}
    items_by_project: dict[str, list[dict[str, Any]]] = {}
    for row in items_payload:
        pid = _as_str(row.get("project_id")).strip()
        if not pid:
            continue
        items_by_project.setdefault(pid, []).append(row)
    for project in projects_meta:
        pid = _as_str(project.get("id")).strip()
        if not pid:
            continue
        file_name = f"{pid}.json"
        _write_json_file(
            bundle_dir_path / "items" / file_name,
            {
                "project_id": pid,
                "items": items_by_project.get(pid, []),
            },
        )
        item_bundle_projects[pid] = _task_item_bundle_url(bundle_dir_name, file_name)
    overview_bundle_file = "overview.json"
    _write_json_file(
        bundle_dir_path / "items" / overview_bundle_file,
        {
            "project_id": "overview",
            "items": items_payload,
        },
    )

    task_data: dict[str, Any] = {
        "generated_at": iso_now_local(),
        "dashboard": {
            "title": _as_str(cfg.get("dashboard", {}).get("title") if isinstance(cfg.get("dashboard"), dict) else "")
            or "项目任务看板",
            "subtitle": _as_str(cfg.get("dashboard", {}).get("subtitle") if isinstance(cfg.get("dashboard"), dict) else "") or "",
        },
        "projects": projects_meta,
        "items": [],
        "item_bundle": {
            "kind": "split_by_project",
            "projects": item_bundle_projects,
            "overview": _task_item_bundle_url(bundle_dir_name, overview_bundle_file),
        },
        "links": {
            "task_page": task_page_link,
            "overview_page": overview_page_link,
            "communication_page": communication_page_link,
            "status_report_page": status_report_page_link,
            "open_source_sync_page": open_source_sync_page_link,
            "agent_directory_page": agent_directory_page_link,
            "agent_curtain_page": agent_curtain_page_link,
            "agent_relationship_board_page": agent_relationship_board_page_link,
            "session_health_page": session_health_page_link,
        },
        "agent_directory_page": agent_directory_page_link,
        "agent_curtain_page": agent_curtain_page_link,
        "agent_relationship_board_page": agent_relationship_board_page_link,
        "communication_page": communication_page_link,
        "status_report_page": status_report_page_link,
        "open_source_sync_page": open_source_sync_page_link,
        "session_health_page": session_health_page_link,
        "overview": overview_data,
    }
    overview_page_data: dict[str, Any] = {
        "generated_at": task_data["generated_at"],
        "dashboard": task_data["dashboard"],
        "projects": projects_meta,
        "items": overview_items_payload,
        "links": task_data["links"],
        "overview": overview_data,
    }
    agent_directory_page_data: dict[str, Any] = {
        "generated_at": task_data["generated_at"],
        "dashboard": task_data["dashboard"],
        "projects": projects_meta,
        "links": {
            **task_data["links"],
            "communication_page": communication_page_link,
            "session_health_page": session_health_page_link,
        },
        "task_page": task_page_link,
        "agent_directory_page": agent_directory_page_link,
    }
    agent_curtain_page_data: dict[str, Any] = {
        "generated_at": task_data["generated_at"],
        "dashboard": task_data["dashboard"],
        "projects": projects_meta,
        "links": {
            **task_data["links"],
            "communication_page": communication_page_link,
            "session_health_page": session_health_page_link,
            "agent_directory_page": agent_directory_page_link,
            "agent_curtain_page": agent_curtain_page_link,
        },
        "task_page": task_page_link,
        "agent_curtain_page": agent_curtain_page_link,
        "environment": str(os.environ.get("TASK_DASHBOARD_ENV_NAME") or "stable").strip() or "stable",
        "overview": overview_data,
    }
    agent_relationship_board_page_data: dict[str, Any] = {
        "generated_at": task_data["generated_at"],
        "dashboard": task_data["dashboard"],
        "projects": projects_meta,
        "links": {
            **task_data["links"],
            "communication_page": communication_page_link,
            "session_health_page": session_health_page_link,
            "agent_directory_page": agent_directory_page_link,
            "agent_curtain_page": agent_curtain_page_link,
            "agent_relationship_board_page": agent_relationship_board_page_link,
        },
        "task_page": task_page_link,
        "agent_curtain_page": agent_curtain_page_link,
        "agent_relationship_board_page": agent_relationship_board_page_link,
        "environment": str(os.environ.get("TASK_DASHBOARD_ENV_NAME") or "stable").strip() or "stable",
        "overview": overview_data,
    }
    communication_page_data: dict[str, Any] = {
        "generated_at": task_data["generated_at"],
        "dashboard": task_data["dashboard"],
        "links": task_data["links"],
        "communication_page": communication_page_link,
        "status_report_page": status_report_page_link,
        "session_health_page": session_health_page_link,
        "environment": str(os.environ.get("TASK_DASHBOARD_ENV_NAME") or "stable").strip() or "stable",
    }
    session_health_page_data = build_session_health_page(
        projects_meta,
        generated_at=task_data["generated_at"],
        task_page_link=task_page_link,
        overview_page_link=overview_page_link,
        communication_page_link=communication_page_link,
        agent_curtain_page_link=agent_curtain_page_link,
        session_health_page_link=session_health_page_link,
        agent_directory_page_link=agent_directory_page_link,
    )
    session_health_page_data["status_report_page"] = status_report_page_link
    session_health_links = session_health_page_data.get("links")
    if isinstance(session_health_links, dict):
        session_health_links["status_report_page"] = status_report_page_link
    status_report_page_data = build_status_report_page_data(
        script_dir,
        generated_at=task_data["generated_at"],
        dashboard=task_data["dashboard"],
        links=task_data["links"],
    )
    open_source_sync_page_data = build_open_source_sync_page_data(
        script_dir,
        generated_at=task_data["generated_at"],
        dashboard=task_data["dashboard"],
        links=task_data["links"],
    )
    task_html = render_from_template(script_dir, "template.html", task_data)
    out_task_path.write_text(task_html, encoding="utf-8")
    print(f"Wrote: {out_task_path}")

    overview_html = render_from_template(script_dir, "template_overview.html", overview_page_data)
    out_overview_path.write_text(overview_html, encoding="utf-8")
    print(f"Wrote: {out_overview_path}")

    communication_html = render_from_template(script_dir, "template_communication.html", communication_page_data)
    out_communication_path.write_text(communication_html, encoding="utf-8")
    print(f"Wrote: {out_communication_path}")

    status_report_html = render_from_template(script_dir, "template_status_report.html", status_report_page_data)
    out_status_report_path.write_text(status_report_html, encoding="utf-8")
    print(f"Wrote: {out_status_report_path}")

    open_source_sync_html = render_from_template(
        script_dir,
        "template_open_source_sync.html",
        open_source_sync_page_data,
    )
    out_open_source_sync_path.write_text(open_source_sync_html, encoding="utf-8")
    print(f"Wrote: {out_open_source_sync_path}")

    agent_directory_html = render_from_template(script_dir, "template_agent_directory.html", agent_directory_page_data)
    out_agent_directory_path.write_text(agent_directory_html, encoding="utf-8")
    print(f"Wrote: {out_agent_directory_path}")

    agent_curtain_html = render_from_template(script_dir, "template_agent_curtain.html", agent_curtain_page_data)
    out_agent_curtain_path.write_text(agent_curtain_html, encoding="utf-8")
    print(f"Wrote: {out_agent_curtain_path}")

    agent_relationship_board_html = render_from_template(
        script_dir,
        "template_agent_relationship_board.html",
        agent_relationship_board_page_data,
    )
    out_agent_relationship_board_path.write_text(agent_relationship_board_html, encoding="utf-8")
    print(f"Wrote: {out_agent_relationship_board_path}")

    session_health_html = render_from_template(script_dir, "template_session_health.html", session_health_page_data)
    out_session_health_path.write_text(session_health_html, encoding="utf-8")
    print(f"Wrote: {out_session_health_path}")
    _sync_public_share_links(root, out_task_path.parent)
    return 0
