# -*- coding: utf-8 -*-

from __future__ import annotations

from typing import Any

from task_dashboard.runtime.message_consistency_runtime import build_conversation_memo_read_runtime


def _safe_text(value: Any, max_len: int = 160) -> str:
    text = "" if value is None else str(value)
    if len(text) > max_len:
        return text[: max_len - 1] + "…"
    return text


def _coerce_count(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except Exception:
        return 0


def build_memo_summary_payload(
    *,
    project_id: str,
    session_id: str,
    memo_count: Any = 0,
    memo_updated_at: Any = "",
    memo_summary_source: str = "",
    delivery_mode: str = "unavailable",
    cache_ttl_ms: int = 1500,
    completion_budget_ms: int = 800,
    cache_age_ms: int = 0,
) -> dict[str, Any]:
    count = _coerce_count(memo_count)
    updated_at = _safe_text(memo_updated_at, 80).strip()
    source = _safe_text(memo_summary_source, 80).strip()
    if not source:
        source = "conversation_memos" if (count > 0 or updated_at) else "none"
    runtime = build_conversation_memo_read_runtime(
        delivery_mode=_safe_text(delivery_mode, 80).strip() or "unavailable",
        cache_ttl_ms=max(0, int(cache_ttl_ms or 0)),
        completion_budget_ms=max(0, int(completion_budget_ms or 0)),
        cache_age_ms=max(0, int(cache_age_ms or 0)),
    )
    runtime["read_scope"] = "unified_read_source_light"
    runtime["summary_only"] = True
    return {
        "version": "v1",
        "projectId": _safe_text(project_id, 160).strip(),
        "sessionId": _safe_text(session_id, 160).strip(),
        "project_id": _safe_text(project_id, 160).strip(),
        "session_id": _safe_text(session_id, 160).strip(),
        "memo_count": count,
        "memo_updated_at": updated_at,
        "memo_has_items": count > 0,
        "memo_summary_source": source,
        "active_path_runtime": runtime,
    }


def memo_summary_from_list_payload(
    payload: dict[str, Any],
    *,
    project_id: str,
    session_id: str,
) -> dict[str, Any]:
    runtime = payload.get("active_path_runtime") if isinstance(payload.get("active_path_runtime"), dict) else {}
    return build_memo_summary_payload(
        project_id=project_id,
        session_id=session_id,
        memo_count=payload.get("count"),
        memo_updated_at=payload.get("updatedAt") or payload.get("updated_at"),
        memo_summary_source="conversation_memos"
        if _coerce_count(payload.get("count")) > 0 or _safe_text(payload.get("updatedAt") or payload.get("updated_at"), 80).strip()
        else "none",
        delivery_mode=_safe_text(runtime.get("delivery_mode"), 80).strip() or "fresh_disk",
        cache_ttl_ms=_coerce_count(runtime.get("cache_ttl_ms") or 1500),
        completion_budget_ms=_coerce_count(runtime.get("completion_budget_ms") or 800),
        cache_age_ms=_coerce_count(runtime.get("cache_age_ms")),
    )


def normalize_memo_summary(
    payload: Any,
    *,
    project_id: str,
    session_id: str,
    fallback_source: str = "unavailable",
    fallback_delivery_mode: str = "unavailable",
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return build_memo_summary_payload(
            project_id=project_id,
            session_id=session_id,
            memo_summary_source=fallback_source,
            delivery_mode=fallback_delivery_mode,
        )
    return build_memo_summary_payload(
        project_id=payload.get("project_id") or payload.get("projectId") or project_id,
        session_id=payload.get("session_id") or payload.get("sessionId") or session_id,
        memo_count=payload.get("memo_count") if "memo_count" in payload else payload.get("count"),
        memo_updated_at=payload.get("memo_updated_at") or payload.get("updatedAt") or payload.get("updated_at"),
        memo_summary_source=payload.get("memo_summary_source") or fallback_source,
        delivery_mode=(payload.get("active_path_runtime") or {}).get("delivery_mode")
        if isinstance(payload.get("active_path_runtime"), dict)
        else fallback_delivery_mode,
        cache_ttl_ms=(payload.get("active_path_runtime") or {}).get("cache_ttl_ms", 1500)
        if isinstance(payload.get("active_path_runtime"), dict)
        else 1500,
        completion_budget_ms=(payload.get("active_path_runtime") or {}).get("completion_budget_ms", 800)
        if isinstance(payload.get("active_path_runtime"), dict)
        else 800,
        cache_age_ms=(payload.get("active_path_runtime") or {}).get("cache_age_ms", 0)
        if isinstance(payload.get("active_path_runtime"), dict)
        else 0,
    )


def load_memo_summary(
    conversation_memo_store: Any,
    *,
    project_id: str,
    session_id: str,
) -> dict[str, Any]:
    if conversation_memo_store is None:
        return build_memo_summary_payload(
            project_id=project_id,
            session_id=session_id,
            memo_summary_source="unavailable",
            delivery_mode="unavailable",
        )
    try:
        summary_fn = getattr(conversation_memo_store, "summary", None)
        if callable(summary_fn):
            return normalize_memo_summary(summary_fn(project_id, session_id), project_id=project_id, session_id=session_id)
        list_fn = getattr(conversation_memo_store, "list", None)
        if callable(list_fn):
            payload = list_fn(project_id, session_id)
            if isinstance(payload, dict):
                return memo_summary_from_list_payload(payload, project_id=project_id, session_id=session_id)
    except Exception:
        return build_memo_summary_payload(
            project_id=project_id,
            session_id=session_id,
            memo_summary_source="error",
            delivery_mode="error",
        )
    return build_memo_summary_payload(
        project_id=project_id,
        session_id=session_id,
        memo_summary_source="unavailable",
        delivery_mode="unavailable",
    )


def load_memo_summaries(
    conversation_memo_store: Any,
    *,
    project_id: str,
    session_ids: list[str],
) -> dict[str, dict[str, Any]]:
    clean_ids = [sid for sid in (_safe_text(raw, 160).strip() for raw in session_ids) if sid]
    if not clean_ids:
        return {}
    if conversation_memo_store is None:
        return {
            sid: build_memo_summary_payload(
                project_id=project_id,
                session_id=sid,
                memo_summary_source="unavailable",
                delivery_mode="unavailable",
            )
            for sid in clean_ids
        }
    try:
        summaries_fn = getattr(conversation_memo_store, "summaries", None)
        if callable(summaries_fn):
            raw = summaries_fn(project_id, clean_ids)
            if isinstance(raw, dict):
                return {
                    sid: normalize_memo_summary(
                        raw.get(sid),
                        project_id=project_id,
                        session_id=sid,
                    )
                    for sid in clean_ids
                }
    except Exception:
        return {
            sid: build_memo_summary_payload(
                project_id=project_id,
                session_id=sid,
                memo_summary_source="error",
                delivery_mode="error",
            )
            for sid in clean_ids
        }
    return {
        sid: load_memo_summary(conversation_memo_store, project_id=project_id, session_id=sid)
        for sid in clean_ids
    }
