# -*- coding: utf-8 -*-

from __future__ import annotations

from pathlib import Path
from typing import Any

from task_dashboard.session_store import session_binding_is_available


_ELIGIBLE_PROJECT_IDS = {"task_dashboard_open_source_execution"}
_STATE_HIDDEN = "hidden"
_STATE_PENDING = "first_agent_ready_pending_team_setup"
_STATE_IN_PROGRESS = "team_setup_in_progress"
_STATE_DONE = "team_setup_done"
_STATE_BLOCKED = "blocked"

_PENDING_PROMPT = (
    "请按当前项目的标准启动批次继续扩建团队并完成初始化：先读取当前项目的 AI bootstrap 指引和启动批次模板，"
    "创建或复用剩余团队会话，补齐初始化培训、通讯录生成与启动回执；完成后只按“当前结论 / 是否通过或放行 / "
    "唯一阻塞 / 关键路径或 run_id / 下一步动作”回复。"
)
_PENDING_SUMMARY = (
    "当前项目已完成基础安装，发送下方提示词后，当前 Agent 会按标准模板继续扩团队、补培训并生成启动回执。"
)
_IN_PROGRESS_SUMMARY = "当前 Agent 已接手团队扩建与初始化，等待启动回执闭环后自动退场。"
_DONE_SUMMARY = "当前项目的扩建团队与初始化已完成。"


def _safe_text(value: Any, limit: int = 4000) -> str:
    return str(value or "").strip()[:limit]


def _resolve_project_root(session: Any) -> Path | None:
    row = session if isinstance(session, dict) else {}
    context = row.get("project_execution_context") if isinstance(row.get("project_execution_context"), dict) else {}
    refs = []
    for source in (
        context.get("target") if isinstance(context.get("target"), dict) else {},
        context.get("source") if isinstance(context.get("source"), dict) else {},
        row,
    ):
        if not isinstance(source, dict):
            continue
        refs.extend(
            [
                source.get("workdir"),
                source.get("worktree_root"),
                source.get("workdir_rel"),
                source.get("worktree_root_rel"),
            ]
        )
    for candidate in refs:
        text = _safe_text(candidate)
        if not text:
            continue
        try:
            path = Path(text).expanduser()
            return path.resolve() if path.exists() else path
        except Exception:
            continue
    return None


def _eligible_project(project_id: str) -> bool:
    return str(project_id or "").strip() in _ELIGIBLE_PROJECT_IDS


def _registry_exists(project_root: Path | None) -> bool:
    if project_root is None:
        return False
    try:
        return (project_root / "registry" / "collab-registry.v1.json").is_file()
    except Exception:
        return False


def _sort_session_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def _key(item: dict[str, Any]) -> tuple[int, str, str]:
        return (
            0 if bool(item.get("is_primary")) else 1,
            _safe_text(item.get("created_at")),
            _safe_text(item.get("id")),
        )

    return sorted(rows, key=_key)


def _hidden_hint() -> dict[str, str]:
    return {
        "state": _STATE_HIDDEN,
        "prompt": "",
        "summary": "",
        "blocked_summary": "",
    }


def _blocked_hint(summary: str) -> dict[str, str]:
    return {
        "state": _STATE_BLOCKED,
        "prompt": "",
        "summary": "",
        "blocked_summary": _safe_text(summary, 1000),
    }


def build_session_team_expansion_hint(
    *,
    session_store: Any,
    project_id: str,
    session: Any,
) -> dict[str, str]:
    pid = _safe_text(project_id, 200)
    row = session if isinstance(session, dict) else {}
    session_id = _safe_text(row.get("id") or row.get("session_id") or row.get("sessionId"), 200)
    if not pid or not session_id or not _eligible_project(pid):
        return _hidden_hint()

    project_root = _resolve_project_root(row)
    if project_root is None:
        return _blocked_hint("当前项目工作区上下文缺失，无法判断是否应继续扩建团队。")

    try:
        all_sessions = session_store.list_sessions(pid, include_deleted=False)
    except Exception:
        return _blocked_hint("当前项目会话真源不可读，暂时无法判断扩团队提示状态。")

    available = [
        dict(item)
        for item in (all_sessions if isinstance(all_sessions, list) else [])
        if isinstance(item, dict) and session_binding_is_available(item)
    ]
    if not available:
        return _blocked_hint("当前项目尚未识别到可用主会话，无法生成扩团队提示。")

    anchor = _sort_session_rows(available)[0]
    anchor_session_id = _safe_text(anchor.get("id"), 200)
    if session_id != anchor_session_id:
        return _hidden_hint()

    active_count = len(available)
    registry_exists = _registry_exists(project_root)
    if active_count == 1:
        return {
            "state": _STATE_PENDING,
            "prompt": _PENDING_PROMPT,
            "summary": _PENDING_SUMMARY,
            "blocked_summary": "",
        }
    if registry_exists and active_count > 1:
        return {
            "state": _STATE_DONE,
            "prompt": "",
            "summary": _DONE_SUMMARY,
            "blocked_summary": "",
        }
    if registry_exists or active_count > 1:
        return {
            "state": _STATE_IN_PROGRESS,
            "prompt": "",
            "summary": _IN_PROGRESS_SUMMARY,
            "blocked_summary": "",
        }
    return _blocked_hint("当前项目团队扩建状态不可判定，请先检查项目会话真源。")
