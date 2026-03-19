# -*- coding: utf-8 -*-

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable


def _load_project_file(path: Path, project_id: str) -> dict[str, Any]:
    if not path.exists():
        return {"project_id": project_id, "sessions": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"project_id": project_id, "sessions": []}
    if not isinstance(data, dict):
        return {"project_id": project_id, "sessions": []}
    sessions = data.get("sessions")
    if not isinstance(sessions, list):
        sessions = []
    return {
        "project_id": str(data.get("project_id") or project_id).strip() or project_id,
        "sessions": [deepcopy(item) for item in sessions if isinstance(item, dict)],
    }


def _save_project_file(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _merge_session_rows(dst_row: dict[str, Any], src_row: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    merged = deepcopy(dst_row)
    changed = False
    for key, value in src_row.items():
        if key == "id":
            continue
        if key not in merged or merged.get(key) in (None, "", [], {}):
            merged[key] = deepcopy(value)
            changed = True
    return merged, changed


def sync_project_session_store(
    source_base_dir: Path,
    target_base_dir: Path,
    *,
    project_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    source_dir = source_base_dir / ".sessions"
    target_dir = target_base_dir / ".sessions"
    report: dict[str, Any] = {
        "source_dir": str(source_dir),
        "target_dir": str(target_dir),
        "copied_projects": [],
        "merged_projects": [],
        "created_sessions": 0,
        "patched_sessions": 0,
        "skipped_projects": [],
    }
    if not source_dir.exists():
        report["reason"] = "source_sessions_missing"
        return report

    if project_ids is None:
        project_names = sorted(
            path.stem
            for path in source_dir.glob("*.json")
            if path.is_file() and path.stem and path.stem != "session_index"
        )
    else:
        project_names = sorted({str(pid).strip() for pid in project_ids if str(pid).strip()})

    target_dir.mkdir(parents=True, exist_ok=True)

    for project_id in project_names:
        src_path = source_dir / f"{project_id}.json"
        if not src_path.exists():
            report["skipped_projects"].append({"project_id": project_id, "reason": "source_missing"})
            continue
        dst_path = target_dir / f"{project_id}.json"
        if not dst_path.exists():
            _save_project_file(dst_path, _load_project_file(src_path, project_id))
            report["copied_projects"].append(project_id)
            continue

        src_data = _load_project_file(src_path, project_id)
        dst_data = _load_project_file(dst_path, project_id)
        dst_sessions = [deepcopy(item) for item in dst_data.get("sessions", []) if isinstance(item, dict)]
        dst_index = {
            str(item.get("id") or "").strip(): idx
            for idx, item in enumerate(dst_sessions)
            if str(item.get("id") or "").strip()
        }
        created = 0
        patched = 0
        for src_row in src_data.get("sessions", []):
            session_id = str(src_row.get("id") or "").strip()
            if not session_id:
                continue
            idx = dst_index.get(session_id)
            if idx is None:
                dst_sessions.append(deepcopy(src_row))
                dst_index[session_id] = len(dst_sessions) - 1
                created += 1
                continue
            merged, changed = _merge_session_rows(dst_sessions[idx], src_row)
            if changed:
                dst_sessions[idx] = merged
                patched += 1
        if created or patched:
            dst_data["project_id"] = project_id
            dst_data["sessions"] = dst_sessions
            _save_project_file(dst_path, dst_data)
            report["merged_projects"].append(
                {
                    "project_id": project_id,
                    "created_sessions": created,
                    "patched_sessions": patched,
                }
            )
            report["created_sessions"] += created
            report["patched_sessions"] += patched

    return report
