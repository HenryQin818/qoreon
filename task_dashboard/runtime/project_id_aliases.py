# -*- coding: utf-8 -*-

from __future__ import annotations

from typing import Any


_READ_PROJECT_ID_ALIASES = {
    "qoreon": "task_dashboard",
}


def canonicalize_runtime_project_id(project_id: Any) -> str:
    pid = str(project_id or "").strip()
    if not pid:
        return ""
    return str(_READ_PROJECT_ID_ALIASES.get(pid, pid))


def rewrite_payload_project_id_fields(
    payload: dict[str, Any],
    *,
    project_id: str,
    row_keys: tuple[str, ...] = (),
    nested_row_keys: tuple[str, ...] = (),
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return payload
    target_project_id = str(project_id or "").strip()
    if not target_project_id:
        return payload

    rewritten = dict(payload)
    if "project_id" in rewritten:
        rewritten["project_id"] = target_project_id
    if "projectId" in rewritten:
        rewritten["projectId"] = target_project_id

    for key in row_keys:
        rows = rewritten.get(key)
        if not isinstance(rows, list):
            continue
        next_rows: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row) if isinstance(row, dict) else {}
            if "project_id" in item:
                item["project_id"] = target_project_id
            if "projectId" in item:
                item["projectId"] = target_project_id
            for nested_key in nested_row_keys:
                nested_value = item.get(nested_key)
                if not isinstance(nested_value, dict):
                    continue
                next_nested = dict(nested_value)
                if "project_id" in next_nested:
                    next_nested["project_id"] = target_project_id
                if "projectId" in next_nested:
                    next_nested["projectId"] = target_project_id
                item[nested_key] = next_nested
            next_rows.append(item)
        rewritten[key] = next_rows

    audit = rewritten.get("agent_identity_audit")
    if isinstance(audit, dict):
        next_audit = dict(audit)
        if "project_id" in next_audit:
            next_audit["project_id"] = target_project_id
        manual_rows = next_audit.get("manual_backfill_required")
        if isinstance(manual_rows, list):
            next_manual_rows: list[dict[str, Any]] = []
            for raw in manual_rows:
                item = dict(raw) if isinstance(raw, dict) else {}
                if "project_id" in item:
                    item["project_id"] = target_project_id
                if "projectId" in item:
                    item["projectId"] = target_project_id
                next_manual_rows.append(item)
            next_audit["manual_backfill_required"] = next_manual_rows
        rewritten["agent_identity_audit"] = next_audit

    return rewritten
