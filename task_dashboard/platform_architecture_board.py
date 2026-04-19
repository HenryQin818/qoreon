from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PLATFORM_ARCHITECTURE_SOURCE_REL = Path("docs/status-report/platform-business-architecture-board.json")


def _as_str(value: Any) -> str:
    return "" if value is None else str(value)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _normalize_rows(rows: Any) -> list[dict[str, Any]]:
    return [_as_dict(row) for row in _as_list(rows) if isinstance(row, dict)]


def load_platform_architecture_source(script_dir: Path) -> tuple[Path, dict[str, Any], str]:
    source_path = (script_dir / PLATFORM_ARCHITECTURE_SOURCE_REL).resolve()
    if not source_path.exists():
        return source_path, {}, f"missing: {source_path}"
    try:
        payload = json.loads(source_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return source_path, {}, f"invalid_json: {exc}"
    if not isinstance(payload, dict):
        return source_path, {}, "invalid_payload: root must be object"
    return source_path, payload, ""


def build_platform_architecture_board_page_data(
    script_dir: Path,
    *,
    generated_at: str,
    dashboard: dict[str, Any],
    links: dict[str, Any],
) -> dict[str, Any]:
    source_path, source_payload, source_error = load_platform_architecture_source(script_dir)
    page = _as_dict(source_payload.get("page"))
    hero = _as_dict(source_payload.get("hero"))

    board = {
        "title": _as_str(page.get("title")).strip() or "Qoreon 平台业务架构画板",
        "subtitle": _as_str(page.get("subtitle")).strip()
        or "用一张图讲清上层协作者、中间平台和下层业务系统的关系。",
        "delivery_state": _as_str(source_payload.get("delivery_state")).strip() or "目标态",
        "positioning": _as_str(source_payload.get("positioning")).strip(),
        "freeze_note": _as_str(source_payload.get("freeze_note")).strip(),
        "hero": {
            "kicker": _as_str(hero.get("kicker")).strip() or "Platform Vision Board",
            "headline": _as_str(hero.get("headline")).strip() or "Qoreon 作为 AI-native 项目操作中台",
            "summary": _as_str(hero.get("summary")).strip(),
        },
        "summary_cards": _normalize_rows(source_payload.get("summary_cards")),
        "goal_points": [
            str(item).strip()
            for item in _as_list(source_payload.get("goal_points"))
            if str(item).strip()
        ],
        "scope_cards": _normalize_rows(source_payload.get("scope_cards")),
        "tracker": _as_dict(source_payload.get("tracker")),
        "milestones": _normalize_rows(source_payload.get("milestones")),
        "talk_track": [
            str(item).strip()
            for item in _as_list(source_payload.get("talk_track"))
            if str(item).strip()
        ],
        "drawer_layers": _normalize_rows(source_payload.get("drawer_layers")),
        "cross_layer_rails": _normalize_rows(source_payload.get("cross_layer_rails")),
        "flow_steps": _normalize_rows(source_payload.get("flow_steps")),
        "scenario_cards": _normalize_rows(source_payload.get("scenario_cards")),
        "boundary_cards": _normalize_rows(source_payload.get("boundary_cards")),
        "alignment_rules": [
            str(item).strip()
            for item in _as_list(source_payload.get("alignment_rules"))
            if str(item).strip()
        ],
        "references": _normalize_rows(source_payload.get("references")),
        "source_file": str(source_path),
        "source_error": source_error,
        "rebuild_command": f"python3 {script_dir / 'build_project_task_dashboard.py'}",
    }

    return {
        "generated_at": generated_at,
        "dashboard": dashboard,
        "links": links,
        "platform_architecture_board": board,
    }
