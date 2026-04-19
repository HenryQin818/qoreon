# -*- coding: utf-8 -*-

from __future__ import annotations

from typing import Any, Mapping

from task_dashboard.runtime_identity import compare_runtime_identity


_COMPONENT_ORDER = (
    "scheduler",
    "task_plan_runtime",
    "heartbeat_task_runtime",
    "session_health_runtime",
)
_READY_STATES = {"ready", "disabled"}


def _norm_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_component_status(name: str, raw: Any) -> dict[str, Any]:
    payload = dict(raw) if isinstance(raw, Mapping) else {}
    state = _norm_text(payload.get("state")).lower()
    if state not in {"warming", "ready", "disabled", "error"}:
        state = "warming"
    error = _norm_text(payload.get("error"))
    updated_at = _norm_text(payload.get("updated_at") or payload.get("updatedAt"))
    summary = _norm_text(payload.get("summary"))
    if not summary:
        if state == "ready":
            summary = f"{name} 已就绪"
        elif state == "disabled":
            summary = f"{name} 已关闭"
        elif state == "error":
            summary = error or f"{name} 启动失败"
        else:
            summary = f"{name} 启动中"

    item: dict[str, Any] = {
        "name": name,
        "state": state,
        "summary": summary,
    }
    if error:
        item["error"] = error
    if updated_at:
        item["updated_at"] = updated_at
    return item


def build_reload_handoff_payload(
    *,
    runtime_role: str,
    component_statuses: Mapping[str, Any] | None,
    startup_started_at: str = "",
    startup_ready_at: str = "",
) -> dict[str, Any]:
    raw_statuses = dict(component_statuses or {})
    ordered_names = list(_COMPONENT_ORDER)
    for key in raw_statuses.keys():
        if key not in ordered_names:
            ordered_names.append(str(key))

    components = [_normalize_component_status(name, raw_statuses.get(name)) for name in ordered_names]
    failed_components = [item["name"] for item in components if item.get("state") == "error"]
    waiting_components = [item["name"] for item in components if item.get("state") not in _READY_STATES | {"error"}]

    if failed_components:
        state = "degraded"
        summary = "启动链失败: " + ", ".join(failed_components)
    elif waiting_components:
        state = "warming"
        summary = "等待启动链就绪: " + ", ".join(waiting_components)
    else:
        state = "ready"
        summary = "reload handoff 就绪"

    ready_for_cutover = state == "ready"
    started_at = _norm_text(startup_started_at)
    ready_at = _norm_text(startup_ready_at)

    return {
        "reload_handoff": {
            "state": state,
            "ready_for_cutover": ready_for_cutover,
            "summary": summary,
            "runtime_role": _norm_text(runtime_role),
            "components": components,
            "started_at": started_at,
            "ready_at": ready_at,
        },
        "health_recovery": {
            "state": state,
            "ready": ready_for_cutover,
            "summary": "health 已恢复" if ready_for_cutover else summary,
        },
        "startup_chain": {
            "state": state,
            "ready": ready_for_cutover,
            "summary": summary,
            "waiting_components": waiting_components,
            "failed_components": failed_components,
        },
    }


def evaluate_reload_handoff_health(
    expected_identity: Mapping[str, Any] | None,
    actual_health: Mapping[str, Any] | None,
) -> dict[str, Any]:
    expected = dict(expected_identity or {})
    actual = dict(actual_health or {})
    mismatches = compare_runtime_identity(expected, actual) if expected else []

    reload_handoff = dict(actual.get("reload_handoff") or {})
    startup_chain = dict(actual.get("startup_chain") or {})
    health_recovery = dict(actual.get("health_recovery") or {})

    ready_for_cutover = bool(reload_handoff.get("ready_for_cutover"))
    if not reload_handoff and not startup_chain and not health_recovery:
        ready_for_cutover = not mismatches

    state = _norm_text(
        reload_handoff.get("state") or startup_chain.get("state") or health_recovery.get("state")
    ).lower()
    if not state:
        state = "ready" if ready_for_cutover else "warming"
    if mismatches:
        state = "mismatch"

    summary_parts: list[str] = []
    if mismatches:
        summary_parts.append("身份不一致: " + " | ".join(mismatches))
    runtime_summary = _norm_text(
        reload_handoff.get("summary") or startup_chain.get("summary") or health_recovery.get("summary")
    )
    if runtime_summary:
        summary_parts.append(runtime_summary)
    summary = "；".join(summary_parts) if summary_parts else ("reload handoff 就绪" if ready_for_cutover else "等待启动链就绪")

    return {
        "ok": bool(actual.get("ok")) and not mismatches and ready_for_cutover,
        "state": state,
        "identity_ok": not mismatches,
        "ready_for_cutover": ready_for_cutover,
        "mismatches": mismatches,
        "summary": summary,
    }
