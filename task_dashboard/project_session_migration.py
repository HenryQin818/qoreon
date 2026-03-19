from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import load_dashboard_config
from .sessions import parse_session_id_list, parse_session_json


STATUS_META: dict[str, dict[str, str]] = {
    "baseline_cleanup": {
        "label": "基准已完成，待清理旧配置",
        "tone": "warn",
        "priority": "P1",
    },
    "single_source_gap": {
        "label": "单源未补齐，待补会话",
        "tone": "warn",
        "priority": "P1",
    },
    "single_source_ready": {
        "label": "单源就绪",
        "tone": "good",
        "priority": "P3",
    },
    "dual_source_pending": {
        "label": "双源并存，待切换",
        "tone": "warn",
        "priority": "P1",
    },
    "legacy_only": {
        "label": "仅旧源，待迁移",
        "tone": "danger",
        "priority": "P0",
    },
    "untracked": {
        "label": "未接入，待确认",
        "tone": "muted",
        "priority": "P2",
    },
}


def _as_str(v: Any) -> str:
    return "" if v is None else str(v)


def _resolve_path(workspace_root: Path, rel: str) -> Path | None:
    rel = str(rel or "").strip()
    if not rel:
        return None
    return (workspace_root / rel).resolve()


def _load_store_sessions(store_path: Path) -> list[dict[str, Any]]:
    if not store_path.exists():
        return []
    try:
        obj = json.loads(store_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    rows = obj.get("sessions") if isinstance(obj, dict) else []
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _load_legacy_rows(legacy_path: Path | None, source_kind: str) -> list[dict[str, Any]]:
    if legacy_path is None:
        return []
    if source_kind == "session_list_rel":
        return parse_session_id_list(legacy_path)
    if source_kind == "session_json_rel":
        return parse_session_json(legacy_path)
    return []


def classify_project_status(
    project_id: str,
    *,
    store_exists: bool,
    config_channel_count: int,
    store_channel_count: int,
    legacy_configured: bool,
    legacy_exists: bool,
) -> dict[str, str]:
    if project_id == "task_dashboard" and store_exists and (legacy_configured or legacy_exists):
        return STATUS_META["baseline_cleanup"]
    if store_exists and store_channel_count < max(config_channel_count, 0):
        return STATUS_META["single_source_gap"]
    if store_exists and not legacy_configured:
        return STATUS_META["single_source_ready"]
    if store_exists and (legacy_configured or legacy_exists):
        return STATUS_META["dual_source_pending"]
    if legacy_exists:
        return STATUS_META["legacy_only"]
    return STATUS_META["untracked"]


def _derive_scope(status_label: str) -> str:
    if "单源未补齐" in status_label:
        return "按通道补齐缺失会话，并复核每个通道都有唯一 session"
    if "仅旧源" in status_label:
        return "补建 .sessions 主数据，并切断旧源运行时依赖"
    if "双源并存" in status_label:
        return "保留旧源作迁移输入，运行时改为只读 .sessions"
    if "基准已完成" in status_label:
        return "清理 config 中旧源配置，作为跨项目基准模板"
    if "未接入" in status_label:
        return "确认项目是否仍活跃；活跃则补接入，不活跃则清理配置"
    return "保持单源，只做例行巡检"


def _derive_summary(
    *,
    store_count: int,
    legacy_count: int,
    config_channel_count: int,
    store_channel_count: int,
    project_root_exists: bool,
    task_root_exists: bool,
    status_label: str,
) -> str:
    parts = [
        f"store={store_count}",
        f"channels={store_channel_count}/{config_channel_count}",
        f"legacy={legacy_count}",
        f"project_root={'Y' if project_root_exists else 'N'}",
        f"task_root={'Y' if task_root_exists else 'N'}",
    ]
    return f"{status_label}；" + ", ".join(parts)


def detect_builder_legacy_merge(repo_root: Path) -> bool:
    cli_path = repo_root / "task_dashboard" / "cli.py"
    if not cli_path.exists():
        return False
    text = cli_path.read_text(encoding="utf-8")
    return "parse_session_json" in text or "parse_session_id_list" in text


def build_project_session_migration_payload(workspace_root: Path, repo_root: Path) -> dict[str, Any]:
    cfg = load_dashboard_config(repo_root)
    projects = cfg.get("projects") if isinstance(cfg, dict) else []
    if not isinstance(projects, list):
        projects = []

    sessions_dir = repo_root / ".sessions"
    builder_legacy_merge = detect_builder_legacy_merge(repo_root)

    rows: list[dict[str, Any]] = []
    for pc in projects:
        if not isinstance(pc, dict):
            continue
        project_id = _as_str(pc.get("id")).strip()
        if not project_id:
            continue
        project_name = _as_str(pc.get("name")).strip() or project_id
        project_root_rel = _as_str(pc.get("project_root_rel")).strip()
        task_root_rel = _as_str(pc.get("task_root_rel")).strip()
        runtime_root_rel = _as_str(pc.get("runtime_root_rel")).strip()
        session_json_rel = _as_str(pc.get("session_json_rel")).strip()
        session_list_rel = _as_str(pc.get("session_list_rel")).strip()
        source_kind = "session_json_rel" if session_json_rel else ("session_list_rel" if session_list_rel else "")
        legacy_rel = session_json_rel or session_list_rel

        project_root = _resolve_path(workspace_root, project_root_rel)
        task_root = _resolve_path(workspace_root, task_root_rel)
        runtime_root = _resolve_path(workspace_root, runtime_root_rel)
        legacy_path = _resolve_path(workspace_root, legacy_rel)
        store_path = sessions_dir / f"{project_id}.json"

        store_sessions = _load_store_sessions(store_path)
        legacy_rows = _load_legacy_rows(legacy_path, source_kind)
        config_channels = [ch for ch in (pc.get("channels") or []) if isinstance(ch, dict)]
        config_channel_count = len([ch for ch in config_channels if _as_str(ch.get("name")).strip()])
        store_channel_count = len({str((row or {}).get("channel_name") or "").strip() for row in store_sessions if str((row or {}).get("channel_name") or "").strip()})
        legacy_channel_count = len({str((row or {}).get("name") or "").strip() for row in legacy_rows if str((row or {}).get("name") or "").strip()})

        status = classify_project_status(
            project_id,
            store_exists=store_path.exists(),
            config_channel_count=config_channel_count,
            store_channel_count=store_channel_count,
            legacy_configured=bool(legacy_rel),
            legacy_exists=bool(legacy_path and legacy_path.exists()),
        )
        status_label = status["label"]
        rows.append(
            {
                "project_id": project_id,
                "project_name": project_name,
                "status_code": next((k for k, v in STATUS_META.items() if v == status), ""),
                "status_label": status_label,
                "tone": status["tone"],
                "priority": status["priority"],
                "needs_adaptation": status_label != STATUS_META["single_source_ready"]["label"],
                "project_root_rel": project_root_rel,
                "task_root_rel": task_root_rel,
                "runtime_root_rel": runtime_root_rel,
                "project_root_exists": bool(project_root and project_root.exists()),
                "task_root_exists": bool(task_root and task_root.exists()),
                "runtime_root_exists": bool(runtime_root and runtime_root.exists()),
                "store_path": str(store_path),
                "store_exists": store_path.exists(),
                "store_session_count": len(store_sessions),
                "store_channel_count": store_channel_count,
                "config_channel_count": config_channel_count,
                "legacy_source_kind": source_kind,
                "legacy_source_rel": legacy_rel,
                "legacy_source_path": str(legacy_path) if legacy_path else "",
                "legacy_source_exists": bool(legacy_path and legacy_path.exists()),
                "legacy_session_count": len(legacy_rows),
                "legacy_channel_count": legacy_channel_count,
                "summary": _derive_summary(
                    store_count=len(store_sessions),
                    config_channel_count=config_channel_count,
                    store_channel_count=store_channel_count,
                    legacy_count=len(legacy_rows),
                    project_root_exists=bool(project_root and project_root.exists()),
                    task_root_exists=bool(task_root and task_root.exists()),
                    status_label=status_label,
                ),
                "next_action": _derive_scope(status_label),
            }
        )

    priority_rank = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    tone_rank = {"danger": 0, "warn": 1, "muted": 2, "good": 3}
    rows.sort(key=lambda row: (priority_rank.get(str(row.get("priority") or "P9"), 9), tone_rank.get(str(row.get("tone") or "muted"), 9), str(row.get("project_id") or "")))

    totals = {
        "projects": len(rows),
        "needs_adaptation": sum(1 for row in rows if bool(row.get("needs_adaptation"))),
        "store_ready": sum(1 for row in rows if bool(row.get("store_exists"))),
        "legacy_configured": sum(1 for row in rows if bool(row.get("legacy_source_rel"))),
        "legacy_existing": sum(1 for row in rows if bool(row.get("legacy_source_exists"))),
        "baseline_cleanup": sum(1 for row in rows if row.get("status_label") == STATUS_META["baseline_cleanup"]["label"]),
        "single_source_gap": sum(1 for row in rows if row.get("status_label") == STATUS_META["single_source_gap"]["label"]),
        "single_source_ready": sum(1 for row in rows if row.get("status_label") == STATUS_META["single_source_ready"]["label"]),
        "dual_source_pending": sum(1 for row in rows if row.get("status_label") == STATUS_META["dual_source_pending"]["label"]),
        "legacy_only": sum(1 for row in rows if row.get("status_label") == STATUS_META["legacy_only"]["label"]),
        "untracked": sum(1 for row in rows if row.get("status_label") == STATUS_META["untracked"]["label"]),
    }

    return {
        "generated_at": __import__("datetime").datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %z"),
        "workspace_root": str(workspace_root),
        "repo_root": str(repo_root),
        "builder_legacy_merge": builder_legacy_merge,
        "totals": totals,
        "projects": rows,
    }


def render_project_session_migration_markdown(payload: dict[str, Any]) -> str:
    totals = payload.get("totals") or {}
    rows = payload.get("projects") or []
    lines = [
        "# A20-跨项目单源化改造审计",
        "",
        f"更新时间：{_as_str(payload.get('generated_at'))}",
        "",
        "## 总览",
        f"1. 项目总数：`{totals.get('projects', 0)}`",
        f"2. 仍需适配：`{totals.get('needs_adaptation', 0)}`",
        f"3. 已有 .sessions 主数据：`{totals.get('store_ready', 0)}`",
        f"4. 仍保留旧源配置：`{totals.get('legacy_configured', 0)}`",
        f"5. 构建链仍存在旧源兼容读取：`{'是' if payload.get('builder_legacy_merge') else '否'}`",
        "",
        "## 状态分层",
        f"1. 基准已完成，待清理旧配置：`{totals.get('baseline_cleanup', 0)}`",
        f"2. 单源未补齐，待补会话：`{totals.get('single_source_gap', 0)}`",
        f"3. 单源就绪：`{totals.get('single_source_ready', 0)}`",
        f"4. 双源并存，待切换：`{totals.get('dual_source_pending', 0)}`",
        f"5. 仅旧源，待迁移：`{totals.get('legacy_only', 0)}`",
        f"6. 未接入，待确认：`{totals.get('untracked', 0)}`",
        "",
        "## 项目清单",
    ]
    for idx, row in enumerate(rows, start=1):
        lines.append(f"{idx}. `{row.get('project_id')}` / {row.get('project_name')}")
        lines.append(f"   - 状态：`{row.get('status_label')}` | 优先级：`{row.get('priority')}`")
        lines.append(f"   - 摘要：{row.get('summary')}")
        lines.append(f"   - 下一步：{row.get('next_action')}")
    lines.extend([
        "",
        "## 页面",
        "1. `dist/project-session-migration-dashboard.html`",
    ])
    return "\n".join(lines) + "\n"
