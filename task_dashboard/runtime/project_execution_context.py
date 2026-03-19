# -*- coding: utf-8 -*-

from __future__ import annotations

from pathlib import Path
from typing import Any


_CONTEXT_KEYS = ("environment", "worktree_root", "workdir", "branch")
_REF_KEYS = ("project_id", "channel_name", "session_id", "run_id")
_CONTEXT_SOURCE_VALUES = {"project", "server_default", "server_runtime"}
_OVERRIDE_SOURCE_VALUES = {"session", "request", "run"}


def _safe_text(value: Any, max_len: int) -> str:
    text = "" if value is None else str(value)
    if len(text) > max_len:
        return text[: max_len - 1] + "…"
    return text


def _normalize_context_ref(src: Any) -> dict[str, str]:
    row = src if isinstance(src, dict) else {}
    out: dict[str, str] = {}
    for key in _REF_KEYS:
        val = _safe_text(row.get(key), 4000).strip()
        if val:
            out[key] = val
    for key in _CONTEXT_KEYS:
        val = _safe_text(row.get(key), 4000).strip()
        if val:
            out[key] = val
    return out


def _normalize_context_source(value: Any) -> str:
    txt = _safe_text(value, 80).strip().lower()
    if txt in _CONTEXT_SOURCE_VALUES:
        return txt
    return ""


def _normalize_override_source(value: Any) -> str:
    txt = _safe_text(value, 80).strip().lower()
    if txt in _OVERRIDE_SOURCE_VALUES:
        return txt
    return ""


def _normalize_path_identity(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    path = Path(text).expanduser()
    try:
        if path.exists():
            return str(path.resolve())
        return str(path)
    except Exception:
        return text


def _context_values_equal(key: str, target: str, source: str) -> bool:
    if target == source:
        return True
    if key not in {"worktree_root", "workdir"}:
        return False
    return _normalize_path_identity(target) == _normalize_path_identity(source)


def diff_override_fields(target: Any, source: Any) -> list[str]:
    normalized_target = _normalize_context_ref(target)
    normalized_source = _normalize_context_ref(source)
    fields: list[str] = []
    for key in _CONTEXT_KEYS:
        t_val = str(normalized_target.get(key) or "").strip()
        s_val = str(normalized_source.get(key) or "").strip()
        if t_val and s_val and not _context_values_equal(key, t_val, s_val):
            fields.append(key)
    return fields


def merge_work_context_overrides(
    source: Any,
    override: Any,
    *,
    override_source: str = "",
) -> tuple[dict[str, str], list[str], str]:
    effective = _normalize_context_ref(source)
    override_ref = _normalize_context_ref(override)
    fields: list[str] = []
    for key in _CONTEXT_KEYS:
        value = str(override_ref.get(key) or "").strip()
        if not value:
            continue
        if not _context_values_equal(key, value, str(effective.get(key) or "").strip()):
            fields.append(key)
        effective[key] = value
    resolved_override_source = _normalize_override_source(override_source) if fields else ""
    return effective, fields, resolved_override_source


def build_project_execution_context(
    *,
    target: Any,
    source: Any,
    context_source: str = "",
    override_fields: list[str] | None = None,
    override_source: str = "",
) -> dict[str, Any]:
    normalized_target = _normalize_context_ref(target)
    normalized_source = _normalize_context_ref(source)
    resolved_context_source = _normalize_context_source(context_source)
    resolved_override_fields = list(override_fields or diff_override_fields(normalized_target, normalized_source))
    resolved_override_source = _normalize_override_source(override_source)
    return {
        "target": normalized_target,
        "source": normalized_source,
        "context_source": resolved_context_source,
        "override": {
            "applied": bool(resolved_override_fields),
            "fields": resolved_override_fields,
            "source": resolved_override_source,
        },
    }


def build_context_override_values(
    project_execution_context: Any,
    *,
    fallback_target: Any = None,
) -> tuple[dict[str, str], list[str]]:
    context = project_execution_context if isinstance(project_execution_context, dict) else {}
    target = _normalize_context_ref(
        (context.get("target") if isinstance(context.get("target"), dict) else {}) or fallback_target
    )
    source = _normalize_context_ref(context.get("source"))
    override_obj = context.get("override") if isinstance(context.get("override"), dict) else {}
    override_fields = [
        str(item or "").strip()
        for item in (override_obj.get("fields") if isinstance(override_obj.get("fields"), list) else [])
        if str(item or "").strip() in _CONTEXT_KEYS
    ]
    explicit_applied = override_obj.get("applied") if "applied" in override_obj else None
    if override_fields:
        resolved_fields = override_fields
    elif isinstance(explicit_applied, bool) and not explicit_applied:
        resolved_fields = []
    else:
        resolved_fields = diff_override_fields(target, source)
    values: dict[str, str] = {}
    for key in _CONTEXT_KEYS:
        values[key] = str(target.get(key) or "").strip() if key in resolved_fields else ""
    return values, resolved_fields


def normalize_project_execution_context(
    project_execution_context: Any,
    *,
    fallback_target: Any = None,
) -> dict[str, Any]:
    context = project_execution_context if isinstance(project_execution_context, dict) else {}
    if not context:
        return {}
    fallback = _normalize_context_ref(fallback_target)
    target_ref = _normalize_context_ref(context.get("target"))
    source_ref = _normalize_context_ref(context.get("source"))
    override_values, override_fields = build_context_override_values(
        context,
        fallback_target=fallback,
    )
    effective_context: dict[str, str] = {}
    for key in _CONTEXT_KEYS:
        override_value = str(override_values.get(key) or "").strip()
        if key in override_fields and override_value:
            effective_context[key] = override_value
            continue
        source_value = str(source_ref.get(key) or "").strip()
        if source_value:
            effective_context[key] = source_value
            continue
        target_value = str(target_ref.get(key) or fallback.get(key) or "").strip()
        if target_value:
            effective_context[key] = target_value
    normalized_target: dict[str, str] = {}
    for key in _REF_KEYS:
        if key == "project_id":
            value = str(target_ref.get(key) or fallback.get(key) or source_ref.get(key) or "").strip()
        else:
            value = str(target_ref.get(key) or fallback.get(key) or "").strip()
        if value:
            normalized_target[key] = value
    normalized_target.update(effective_context)
    resolved_override_fields: list[str] = []
    for key in override_fields:
        target_value = str(effective_context.get(key) or "").strip()
        source_value = str(source_ref.get(key) or "").strip()
        if not target_value:
            continue
        if source_value and _context_values_equal(key, target_value, source_value):
            continue
        resolved_override_fields.append(key)
    override_obj = context.get("override") if isinstance(context.get("override"), dict) else {}
    resolved_override_source = (
        _normalize_override_source(override_obj.get("source")) if resolved_override_fields else ""
    )
    return build_project_execution_context(
        target=normalized_target,
        source=source_ref,
        context_source=_normalize_context_source(context.get("context_source")),
        override_fields=resolved_override_fields,
        override_source=resolved_override_source,
    )


def infer_project_execution_context_source(
    *,
    project_context: Any = None,
    stored_context_source: Any = None,
) -> str:
    stored = _normalize_context_source(stored_context_source)
    if stored:
        return stored
    project = _normalize_context_ref(project_context)
    if any(str(project.get(key) or "").strip() for key in _CONTEXT_KEYS):
        return "project"
    return "server_default"
