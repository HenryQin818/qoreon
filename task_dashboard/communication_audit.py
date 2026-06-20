from __future__ import annotations

import argparse
import json
import re
import statistics
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

COLLABORATION_INTEGRITY_AUDIT_VERSION = "p2_ccr_delivery_audit_v1"

_KNOWN_INTERACTION_MODES = {"dialog_now", "task_with_receipt", "notify_only"}
_KNOWN_MESSAGE_KINDS = {"system_callback", "collab_update", "manual_update"}
_ONBOARDING_MESSAGE_TYPES = {"first_visible_message", "init_training"}
_ONBOARDING_TRIGGER_TYPES = {"project_bootstrap_first_visible", "agent_init_training"}
_ANNOUNCE_RUN_ID_RE = re.compile(r"^20\d{6}-\d{6}-[0-9A-Za-z_-]{6,}$")
_CCR_DEGRADED_CODES = {
    "ccr_registry_missing",
    "missing_ccr_validation",
    "missing_project_id",
    "missing_channel_name",
    "duplicate_channel_name",
    "invalid_formal_dispatch_entry",
    "primary_session_not_in_candidates",
    "missing_required_primary_session",
    "formal_dispatch_without_primary",
    "multiple_primary_sessions",
    "missing_session_id",
    "duplicate_session_id_in_channel",
    "duplicate_session_id",
}
_IDENTITY_UNRESOLVED_CODES = {
    "missing_readable_identity",
    "session_id_as_identity",
    "technical_identity",
    "invalid_user_visible_identity",
    "missing_session_purpose",
}


def _parse_iso_ts(raw: Any) -> datetime | None:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%dT%H:%M:%S%z")
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _pct(part: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round((float(part) / float(total)) * 100.0, 1)


def _counter_to_sorted_rows(counter: dict[str, int], total: int, *, limit: int) -> list[dict[str, Any]]:
    rows = sorted(counter.items(), key=lambda item: (-int(item[1]), str(item[0])))
    out: list[dict[str, Any]] = []
    for key, count in rows[: max(1, int(limit or 1))]:
        out.append(
            {
                "name": str(key or ""),
                "count": int(count),
                "percent": _pct(int(count), total),
            }
        )
    return out


def _load_run_rows(runs_dirs: list[Path], *, include_hidden: bool = False) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for runs_dir in runs_dirs:
        base = Path(runs_dir).expanduser().resolve()
        if not base.exists():
            continue
        if base.is_file() and base.suffix.lower() == ".json":
            paths = [base]
        else:
            paths = sorted(base.rglob("*.json"))
        for path in paths:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            if not include_hidden and bool(data.get("hidden")):
                continue
            run_id = str(data.get("id") or path.stem).strip() or path.stem
            created_at = _parse_iso_ts(data.get("createdAt"))
            row = dict(data)
            row["_run_id"] = run_id
            row["_path"] = str(path)
            row["_scope_root"] = str(base)
            row["_created_at_dt"] = created_at
            row["_created_at_sort"] = float(created_at.timestamp()) if isinstance(created_at, datetime) else 0.0
            rows.append(row)
    rows.sort(key=lambda item: (float(item.get("_created_at_sort") or 0.0), str(item.get("_run_id") or "")))
    return rows


def _as_text(value: Any) -> str:
    return str(value or "").strip()


def _read_json_dict(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _looks_like_announce_run_id(value: str) -> bool:
    text = _as_text(value)
    return bool(_ANNOUNCE_RUN_ID_RE.match(text))


def _ref_session_id(raw: Any) -> str:
    if not isinstance(raw, dict):
        return ""
    return _as_text(raw.get("session_id") or raw.get("sessionId"))


def _field_from_dicts(field: str, *sources: Any) -> str:
    for source in sources:
        if not isinstance(source, dict):
            continue
        value = _as_text(source.get(field))
        if value:
            return value
    return ""


def _classify_ccr_issue(code: str) -> str:
    if code == "readable_identity_conflict":
        return "readable_name_conflict"
    if code in _IDENTITY_UNRESOLVED_CODES:
        return "identity_unresolved"
    if code in _CCR_DEGRADED_CODES:
        return "ccr_degraded"
    return "ccr_degraded"


def _add_integrity_issue(
    issues: list[dict[str, Any]],
    category_counts: dict[str, int],
    *,
    category: str,
    code: str,
    message: str,
    source: str,
    project_id: str = "",
    channel_name: str = "",
    session_id: str = "",
    run_id: str = "",
    path: str = "",
    field: str = "",
    missing_fields: list[str] | None = None,
    details: dict[str, Any] | None = None,
    max_detail_items: int = 50,
) -> None:
    category_counts[category] = int(category_counts.get(category) or 0) + 1
    if len(issues) >= max(1, int(max_detail_items or 1)):
        return
    item: dict[str, Any] = {
        "category": category,
        "code": code,
        "message": message,
        "source": source,
    }
    for key, value in (
        ("project_id", project_id),
        ("channel_name", channel_name),
        ("session_id", session_id),
        ("run_id", run_id),
        ("path", path),
        ("field", field),
    ):
        if _as_text(value):
            item[key] = _as_text(value)
    if missing_fields:
        item["missing_fields"] = [str(x) for x in missing_fields if str(x or "").strip()]
    if details:
        item["details"] = details
    issues.append(item)


def audit_ccr_registry_rules(
    *,
    registry_paths: list[Path] | None = None,
    max_detail_items: int = 50,
) -> dict[str, Any]:
    """Audit CCR derived registries by consuming bootstrap ccr_validation output.

    This intentionally does not re-implement CCR generation rules. The single
    source remains scripts/bootstrap_project_collab.py -> registry.ccr_validation.
    """
    paths = [Path(p).expanduser() for p in registry_paths or [] if _as_text(p)]
    issues: list[dict[str, Any]] = []
    category_counts: dict[str, int] = {}
    checked = 0
    degraded = 0
    validation_issue_count = 0

    if not paths:
        return {
            "version": COLLABORATION_INTEGRITY_AUDIT_VERSION,
            "state": "not_configured",
            "ok": True,
            "checked_registry_count": 0,
            "issue_count": 0,
            "category_counts": {},
            "missing_items": [],
            "merge_source": "registry.ccr_validation",
        }

    for raw_path in paths:
        path = raw_path.resolve()
        checked += 1
        if not path.exists():
            degraded += 1
            _add_integrity_issue(
                issues,
                category_counts,
                category="ccr_degraded",
                code="ccr_registry_missing",
                message="CCR 派生通讯录不存在，无法执行同源校验",
                source="registry_path",
                path=str(path),
                field="registry/public-registry.v1.json",
                max_detail_items=max_detail_items,
            )
            continue

        payload = _read_json_dict(path)
        project = payload.get("project") if isinstance(payload.get("project"), dict) else {}
        project_id = _as_text(project.get("project_id") or payload.get("project_id"))
        validation = payload.get("ccr_validation") if isinstance(payload.get("ccr_validation"), dict) else {}
        if not validation:
            degraded += 1
            _add_integrity_issue(
                issues,
                category_counts,
                category="ccr_degraded",
                code="missing_ccr_validation",
                message="CCR 缺少 ccr_validation，需复用 bootstrap 校验规则重建派生通讯录",
                source="registry.ccr_validation",
                project_id=project_id,
                path=str(path),
                field="ccr_validation",
                max_detail_items=max_detail_items,
            )
            continue

        if bool(validation.get("blocking")) or not bool(validation.get("ok", True)):
            degraded += 1
        for item in validation.get("issues") or []:
            if not isinstance(item, dict):
                continue
            validation_issue_count += 1
            code = _as_text(item.get("code")) or "ccr_validation_issue"
            category = _classify_ccr_issue(code)
            _add_integrity_issue(
                issues,
                category_counts,
                category=category,
                code=code,
                message=_as_text(item.get("message")) or "CCR 校验异常",
                source="registry.ccr_validation",
                project_id=_as_text(item.get("project_id")) or project_id,
                channel_name=_as_text(item.get("channel_name")),
                session_id=_as_text(item.get("session_id")),
                path=str(path),
                field=_as_text(item.get("field")),
                details=item.get("details") if isinstance(item.get("details"), dict) else None,
                max_detail_items=max_detail_items,
            )

    issue_count = sum(category_counts.values())
    return {
        "version": COLLABORATION_INTEGRITY_AUDIT_VERSION,
        "state": "ready" if issue_count == 0 else "degraded",
        "ok": issue_count == 0,
        "checked_registry_count": checked,
        "degraded_registry_count": degraded,
        "validation_issue_count": validation_issue_count,
        "issue_count": issue_count,
        "category_counts": category_counts,
        "missing_items": issues,
        "merge_source": "registry.ccr_validation",
    }


def _run_extra(row: dict[str, Any]) -> dict[str, Any]:
    extra = row.get("extra_meta") if isinstance(row.get("extra_meta"), dict) else {}
    run_extra = row.get("run_extra_meta") if isinstance(row.get("run_extra_meta"), dict) else {}
    merged = dict(extra)
    merged.update(run_extra)
    return merged


def _communication_view(row: dict[str, Any]) -> dict[str, Any]:
    return row.get("communication_view") if isinstance(row.get("communication_view"), dict) else {}


def _delivery_summary(row: dict[str, Any]) -> dict[str, Any]:
    communication_view = _communication_view(row)
    summary = communication_view.get("delivery_summary") if isinstance(communication_view.get("delivery_summary"), dict) else {}
    if summary:
        return summary
    return row.get("delivery_summary") if isinstance(row.get("delivery_summary"), dict) else {}


def _is_formal_collaboration_run(row: dict[str, Any]) -> bool:
    communication_view = _communication_view(row)
    mode = _as_text(row.get("interaction_mode") or communication_view.get("interaction_mode")).lower()
    message_kind = _as_text(row.get("message_kind") or communication_view.get("message_kind")).lower()
    if mode in _KNOWN_INTERACTION_MODES or message_kind in _KNOWN_MESSAGE_KINDS:
        return True
    if any(isinstance(row.get(key), dict) for key in ("source_ref", "target_ref", "callback_to")):
        return True
    if bool(row.get("visible_in_channel_chat")):
        return True
    return False


def _is_onboarding_run(row: dict[str, Any]) -> bool:
    extra = _run_extra(row)
    message_type = _as_text(row.get("onboarding_message_type") or extra.get("onboarding_message_type")).lower()
    trigger_type = _as_text(row.get("trigger_type") or extra.get("trigger_type")).lower()
    return message_type in _ONBOARDING_MESSAGE_TYPES or trigger_type in _ONBOARDING_TRIGGER_TYPES


def _delivery_evidence_for_row(row: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
    communication_view = _communication_view(row)
    delivery_summary = _delivery_summary(row)
    target_ref = row.get("target_ref") if isinstance(row.get("target_ref"), dict) else {}
    actual_session_id = _as_text(row.get("sessionId") or row.get("session_id"))
    declared_target_session_id = (
        _field_from_dicts("target_session_id", delivery_summary, communication_view)
        or _ref_session_id(target_ref)
        or actual_session_id
    )
    run_id = (
        _field_from_dicts("announce_run_id", delivery_summary)
        or _field_from_dicts("dispatch_run_id", delivery_summary)
        or _as_text(row.get("announce_run_id") or row.get("_run_id") or row.get("id"))
    )
    visible = bool(row.get("visible_in_channel_chat") or delivery_summary.get("visible_in_channel_chat"))
    missing: list[str] = []
    if not _looks_like_announce_run_id(run_id):
        missing.append("announce_run_id")
    if not declared_target_session_id:
        missing.append("target_session_id")
    if actual_session_id and declared_target_session_id and actual_session_id != declared_target_session_id:
        missing.append("target_session_id_mismatch")
    if not visible:
        missing.append("visible_in_channel_chat")
    evidence = {
        "announce_run_id": run_id,
        "target_session_id": declared_target_session_id,
        "actual_session_id": actual_session_id,
        "target_session_match": bool(declared_target_session_id and (not actual_session_id or declared_target_session_id == actual_session_id)),
        "visible_in_channel_chat": visible,
    }
    return missing, evidence


def audit_delivery_evidence_rules(
    *,
    rows: list[dict[str, Any]],
    max_detail_items: int = 50,
) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    category_counts: dict[str, int] = {}
    formal_count = 0
    delivered_count = 0
    onboarding_count = 0

    for row in rows:
        if not isinstance(row, dict):
            continue
        run_id = _as_text(row.get("_run_id") or row.get("id"))
        path = _as_text(row.get("_path"))
        channel_name = _as_text(row.get("channelName") or row.get("channel_name"))
        session_id = _as_text(row.get("sessionId") or row.get("session_id"))

        if _is_formal_collaboration_run(row):
            formal_count += 1
            missing, evidence = _delivery_evidence_for_row(row)
            if missing:
                _add_integrity_issue(
                    issues,
                    category_counts,
                    category="delivery_evidence_missing",
                    code="delivery_evidence_missing",
                    message="正式协作消息缺少 announce_run_id + target_session_id一致 + visible_in_channel_chat=true 证据链",
                    source="run_meta.delivery_evidence",
                    channel_name=channel_name,
                    session_id=session_id,
                    run_id=run_id,
                    path=path,
                    missing_fields=missing,
                    details={"evidence": evidence},
                    max_detail_items=max_detail_items,
                )
            else:
                delivered_count += 1

        if _is_onboarding_run(row):
            onboarding_count += 1
            missing_refs: list[str] = []
            if not _ref_session_id(row.get("source_ref")):
                missing_refs.append("source_ref")
            if not _ref_session_id(row.get("callback_to")):
                missing_refs.append("callback_to")
            if missing_refs:
                code = "missing_source_ref" if "source_ref" in missing_refs else "missing_callback_to"
                _add_integrity_issue(
                    issues,
                    category_counts,
                    category="missing_source_ref",
                    code=code,
                    message="首发可见消息/Agent 启动培训缺少 source_ref 或 callback_to，可能造成投影 missing_source_ref",
                    source="run_meta.onboarding_refs",
                    channel_name=channel_name,
                    session_id=session_id,
                    run_id=run_id,
                    path=path,
                    missing_fields=missing_refs,
                    max_detail_items=max_detail_items,
                )

    issue_count = sum(category_counts.values())
    return {
        "version": COLLABORATION_INTEGRITY_AUDIT_VERSION,
        "state": "ready" if issue_count == 0 else "degraded",
        "ok": issue_count == 0,
        "formal_message_count": formal_count,
        "delivery_verified_count": delivered_count,
        "onboarding_message_count": onboarding_count,
        "issue_count": issue_count,
        "category_counts": category_counts,
        "missing_items": issues,
        "merge_source": "run_meta + communication_view.delivery_summary",
    }


def build_collaboration_integrity_audit(
    *,
    rows: list[dict[str, Any]],
    registry_paths: list[Path] | None = None,
    max_detail_items: int = 50,
) -> dict[str, Any]:
    ccr = audit_ccr_registry_rules(registry_paths=registry_paths or [], max_detail_items=max_detail_items)
    delivery = audit_delivery_evidence_rules(rows=rows, max_detail_items=max_detail_items)
    categories: dict[str, int] = {}
    for bucket in (ccr.get("category_counts") or {}, delivery.get("category_counts") or {}):
        if not isinstance(bucket, dict):
            continue
        for key, value in bucket.items():
            categories[str(key)] = int(categories.get(str(key)) or 0) + int(value or 0)
    missing_items = list(ccr.get("missing_items") or []) + list(delivery.get("missing_items") or [])
    issue_count = sum(categories.values())
    return {
        "version": COLLABORATION_INTEGRITY_AUDIT_VERSION,
        "ok": issue_count == 0,
        "state": "ready" if issue_count == 0 else "degraded",
        "issue_count": issue_count,
        "category_counts": categories,
        "missing_items": missing_items[: max(1, int(max_detail_items or 1))],
        "rules": [
            {
                "code": "ccr_system_uniqueness",
                "fields": ["project_id", "channel_name", "session_id", "primary_session_id", "formal_dispatch_entry"],
                "source": "registry.ccr_validation",
            },
            {
                "code": "ccr_readable_identity",
                "fields": ["alias", "display_name", "agent_name"],
                "source": "registry.ccr_validation",
            },
            {
                "code": "formal_delivery_evidence",
                "fields": ["announce_run_id", "target_session_id", "visible_in_channel_chat"],
                "source": "run_meta + communication_view.delivery_summary",
            },
            {
                "code": "onboarding_refs",
                "fields": ["source_ref", "callback_to"],
                "source": "run_meta.onboarding_refs",
            },
        ],
        "ccr": ccr,
        "delivery": delivery,
        "merge_strategy": {
            "ccr": "只消费 bootstrap_project_collab 生成的 registry.ccr_validation，不另起身份/唯一性判断真源。",
            "delivery": "只读 run meta 与 communication_view.delivery_summary，不改变 /api/codex/announce 发送语义。",
            "write_policy": "巡检只读，不写回 SessionStore/registry/COMMUNICATIONS，不补发历史消息。",
        },
    }


def audit_communication_patterns(
    *,
    runs_dirs: list[Path],
    registry_paths: list[Path] | None = None,
    response_window_hours: float = 2.0,
    top_limit: int = 8,
    include_hidden: bool = False,
    max_detail_items: int = 50,
) -> dict[str, Any]:
    rows = _load_run_rows(runs_dirs, include_hidden=include_hidden)
    total_runs = len(rows)
    response_window = timedelta(hours=max(0.0, float(response_window_hours or 0.0)))

    sender_type_counts: dict[str, int] = {}
    sender_name_counts: dict[str, int] = {}
    status_counts: dict[str, int] = {}
    environment_counts: dict[str, int] = {}
    channel_counts: dict[str, int] = {}
    source_channel_counts: dict[str, int] = {}
    source_project_counts: dict[str, int] = {}
    target_project_counts: dict[str, int] = {}
    target_session_counts: dict[str, int] = {}
    communication_message_kind_counts: dict[str, int] = {}
    receipt_message_kind_counts: dict[str, int] = {}
    dispatch_state_counts: dict[str, int] = {}
    event_reason_counts: dict[str, int] = {}
    degrade_reason_counts: dict[str, int] = {}
    error_text_counts: dict[str, int] = {}
    error_channel_counts: dict[str, int] = {}
    error_sender_type_counts: dict[str, int] = {}
    reply_pair_counts: dict[str, int] = {}
    mention_target_counts: dict[str, int] = {}

    by_run_id: dict[str, dict[str, Any]] = {}
    for row in rows:
        by_run_id[str(row.get("_run_id") or "")] = row

    reply_count = 0
    mention_count = 0
    communication_view_count = 0
    receipt_summary_count = 0
    route_mismatch_count = 0
    user_total = 0
    user_responded_same_channel = 0
    user_responded_same_session = 0
    agent_total = 0
    agent_system_follow_same_session = 0
    user_same_channel_latencies: list[float] = []
    user_same_session_latencies: list[float] = []
    agent_system_follow_latencies: list[float] = []
    explicit_reply_latencies: list[float] = []

    for idx, row in enumerate(rows):
        sender_type = str(row.get("sender_type") or "unknown").strip().lower() or "unknown"
        sender_name = str(row.get("sender_name") or "").strip() or "(empty)"
        status = str(row.get("status") or "unknown").strip().lower() or "unknown"
        environment = str(row.get("environment") or "").strip().lower() or "(empty)"
        channel_name = str(row.get("channelName") or "").strip() or "(empty)"
        sender_type_counts[sender_type] = int(sender_type_counts.get(sender_type) or 0) + 1
        sender_name_counts[sender_name] = int(sender_name_counts.get(sender_name) or 0) + 1
        status_counts[status] = int(status_counts.get(status) or 0) + 1
        environment_counts[environment] = int(environment_counts.get(environment) or 0) + 1
        channel_counts[channel_name] = int(channel_counts.get(channel_name) or 0) + 1

        communication_view = row.get("communication_view") if isinstance(row.get("communication_view"), dict) else None
        if communication_view:
            communication_view_count += 1
            message_kind = str(communication_view.get("message_kind") or "").strip().lower() or "(empty)"
            event_reason = str(communication_view.get("event_reason") or "").strip().lower() or "(empty)"
            dispatch_state = str(communication_view.get("dispatch_state") or "").strip().lower() or "(empty)"
            communication_message_kind_counts[message_kind] = int(communication_message_kind_counts.get(message_kind) or 0) + 1
            event_reason_counts[event_reason] = int(event_reason_counts.get(event_reason) or 0) + 1
            dispatch_state_counts[dispatch_state] = int(dispatch_state_counts.get(dispatch_state) or 0) + 1
            if bool(communication_view.get("route_mismatch")):
                route_mismatch_count += 1
            source_channel = str(communication_view.get("source_channel") or "").strip() or "(empty)"
            source_channel_counts[source_channel] = int(source_channel_counts.get(source_channel) or 0) + 1
            source_project = str(communication_view.get("source_project_id") or "").strip() or "(empty)"
            source_project_counts[source_project] = int(source_project_counts.get(source_project) or 0) + 1
            target_project = str(communication_view.get("target_project_id") or "").strip() or "(empty)"
            target_project_counts[target_project] = int(target_project_counts.get(target_project) or 0) + 1
            target_session = str(communication_view.get("target_session_id") or "").strip() or "(empty)"
            target_session_counts[target_session] = int(target_session_counts.get(target_session) or 0) + 1
            route_resolution = communication_view.get("route_resolution")
            if isinstance(route_resolution, dict):
                degrade_reason = str(route_resolution.get("degrade_reason") or "").strip() or "(empty)"
                degrade_reason_counts[degrade_reason] = int(degrade_reason_counts.get(degrade_reason) or 0) + 1

        receipt_summary = row.get("receipt_summary") if isinstance(row.get("receipt_summary"), dict) else None
        if receipt_summary:
            receipt_summary_count += 1
            message_kind = str(receipt_summary.get("message_kind") or "").strip().lower() or "(empty)"
            receipt_message_kind_counts[message_kind] = int(receipt_message_kind_counts.get(message_kind) or 0) + 1

        reply_to_run_id = str(row.get("reply_to_run_id") or "").strip()
        if reply_to_run_id:
            reply_count += 1
            source_row = by_run_id.get(reply_to_run_id)
            target_sender_name = str(row.get("sender_name") or "").strip() or "(empty)"
            source_sender_name = str(row.get("reply_to_sender_name") or "").strip() or "(empty)"
            pair_key = f"{source_sender_name} -> {target_sender_name}"
            reply_pair_counts[pair_key] = int(reply_pair_counts.get(pair_key) or 0) + 1
            if source_row is not None:
                src_ts = source_row.get("_created_at_dt")
                cur_ts = row.get("_created_at_dt")
                if isinstance(src_ts, datetime) and isinstance(cur_ts, datetime):
                    explicit_reply_latencies.append((cur_ts - src_ts).total_seconds())

        mention_targets = row.get("mention_targets") if isinstance(row.get("mention_targets"), list) else []
        if mention_targets:
            mention_count += 1
            for item in mention_targets:
                if not isinstance(item, dict):
                    continue
                target_name = (
                    str(item.get("channel_name") or item.get("channelName") or item.get("display_name") or "").strip()
                    or "(empty)"
                )
                mention_target_counts[target_name] = int(mention_target_counts.get(target_name) or 0) + 1

        if status == "error":
            error_sender_type_counts[sender_type] = int(error_sender_type_counts.get(sender_type) or 0) + 1
            error_channel_counts[channel_name] = int(error_channel_counts.get(channel_name) or 0) + 1
            error_text = str(row.get("error") or "").strip()
            if error_text:
                brief = error_text[:160]
                error_text_counts[brief] = int(error_text_counts.get(brief) or 0) + 1

        current_ts = row.get("_created_at_dt")
        if sender_type == "user":
            user_total += 1
            if isinstance(current_ts, datetime) and response_window.total_seconds() > 0:
                later_rows = rows[idx + 1 :]
                for later in later_rows:
                    later_ts = later.get("_created_at_dt")
                    if not isinstance(later_ts, datetime):
                        continue
                    if later_ts - current_ts > response_window:
                        break
                    later_sender_type = str(later.get("sender_type") or "").strip().lower()
                    if later_sender_type not in {"agent", "system", "legacy"}:
                        continue
                    if str(later.get("channelName") or "").strip() == channel_name:
                        user_responded_same_channel += 1
                        user_same_channel_latencies.append((later_ts - current_ts).total_seconds())
                        break
                for later in later_rows:
                    later_ts = later.get("_created_at_dt")
                    if not isinstance(later_ts, datetime):
                        continue
                    if later_ts - current_ts > response_window:
                        break
                    later_sender_type = str(later.get("sender_type") or "").strip().lower()
                    if later_sender_type not in {"agent", "system", "legacy"}:
                        continue
                    if str(later.get("sessionId") or "").strip() == str(row.get("sessionId") or "").strip():
                        user_responded_same_session += 1
                        user_same_session_latencies.append((later_ts - current_ts).total_seconds())
                        break

        if sender_type == "agent":
            agent_total += 1
            if isinstance(current_ts, datetime) and response_window.total_seconds() > 0:
                for later in rows[idx + 1 :]:
                    later_ts = later.get("_created_at_dt")
                    if not isinstance(later_ts, datetime):
                        continue
                    if later_ts - current_ts > response_window:
                        break
                    if str(later.get("sender_type") or "").strip().lower() != "system":
                        continue
                    if str(later.get("sessionId") or "").strip() != str(row.get("sessionId") or "").strip():
                        continue
                    agent_system_follow_same_session += 1
                    agent_system_follow_latencies.append((later_ts - current_ts).total_seconds())
                    break

    first_created_at = ""
    last_created_at = ""
    if rows:
        first_created_at = str(rows[0].get("createdAt") or "")
        last_created_at = str(rows[-1].get("createdAt") or "")

    def _median(values: list[float]) -> float | None:
        if not values:
            return None
        return round(float(statistics.median(values)), 1)

    total_errors = int(status_counts.get("error") or 0)
    current_scope = {
        "runs_dirs": [str(Path(p).expanduser().resolve()) for p in runs_dirs],
        "registry_paths": [str(Path(p).expanduser().resolve()) for p in registry_paths or []],
        "include_hidden": bool(include_hidden),
        "response_window_hours": float(response_window_hours or 0.0),
    }
    return {
        "scope": current_scope,
        "time_range": {"first_created_at": first_created_at, "last_created_at": last_created_at},
        "totals": {
            "runs": total_runs,
            "reply_to_runs": reply_count,
            "mention_target_runs": mention_count,
            "communication_view_runs": communication_view_count,
            "receipt_summary_runs": receipt_summary_count,
            "route_mismatch_runs": route_mismatch_count,
            "legacy_runs": int(sender_type_counts.get("legacy") or 0),
        },
        "rates": {
            "reply_to_rate_pct": _pct(reply_count, total_runs),
            "mention_target_rate_pct": _pct(mention_count, total_runs),
            "communication_view_rate_pct": _pct(communication_view_count, total_runs),
            "receipt_summary_rate_pct": _pct(receipt_summary_count, total_runs),
            "legacy_rate_pct": _pct(int(sender_type_counts.get("legacy") or 0), total_runs),
            "route_mismatch_rate_pct": _pct(route_mismatch_count, communication_view_count),
        },
        "sender_type_breakdown": _counter_to_sorted_rows(sender_type_counts, total_runs, limit=top_limit),
        "status_breakdown": _counter_to_sorted_rows(status_counts, total_runs, limit=top_limit),
        "environment_breakdown": _counter_to_sorted_rows(environment_counts, total_runs, limit=top_limit),
        "communication_message_kind_breakdown": _counter_to_sorted_rows(
            communication_message_kind_counts,
            communication_view_count,
            limit=top_limit,
        ),
        "receipt_summary_message_kind_breakdown": _counter_to_sorted_rows(
            receipt_message_kind_counts,
            receipt_summary_count,
            limit=top_limit,
        ),
        "dispatch_state_breakdown": _counter_to_sorted_rows(dispatch_state_counts, communication_view_count, limit=top_limit),
        "event_reason_breakdown": _counter_to_sorted_rows(event_reason_counts, communication_view_count, limit=top_limit),
        "top_channels": _counter_to_sorted_rows(channel_counts, total_runs, limit=top_limit),
        "top_source_channels": _counter_to_sorted_rows(source_channel_counts, communication_view_count, limit=top_limit),
        "top_source_projects": _counter_to_sorted_rows(source_project_counts, communication_view_count, limit=top_limit),
        "top_target_projects": _counter_to_sorted_rows(target_project_counts, communication_view_count, limit=top_limit),
        "top_target_sessions": _counter_to_sorted_rows(target_session_counts, communication_view_count, limit=top_limit),
        "top_sender_names": _counter_to_sorted_rows(sender_name_counts, total_runs, limit=top_limit),
        "top_degrade_reasons": _counter_to_sorted_rows(degrade_reason_counts, communication_view_count, limit=top_limit),
        "top_error_channels": _counter_to_sorted_rows(error_channel_counts, total_errors, limit=top_limit),
        "top_error_sender_types": _counter_to_sorted_rows(error_sender_type_counts, total_errors, limit=top_limit),
        "top_error_texts": _counter_to_sorted_rows(error_text_counts, total_errors, limit=top_limit),
        "top_reply_pairs": _counter_to_sorted_rows(reply_pair_counts, reply_count, limit=top_limit),
        "top_mention_targets": _counter_to_sorted_rows(mention_target_counts, mention_count, limit=top_limit),
        "response_metrics": {
            "user_total": user_total,
            "user_responded_same_channel_within_window": user_responded_same_channel,
            "user_responded_same_channel_rate_pct": _pct(user_responded_same_channel, user_total),
            "user_responded_same_session_within_window": user_responded_same_session,
            "user_responded_same_session_rate_pct": _pct(user_responded_same_session, user_total),
            "median_user_same_channel_latency_s": _median(user_same_channel_latencies),
            "median_user_same_session_latency_s": _median(user_same_session_latencies),
            "agent_total": agent_total,
            "agent_system_follow_same_session_within_window": agent_system_follow_same_session,
            "agent_system_follow_same_session_rate_pct": _pct(agent_system_follow_same_session, agent_total),
            "median_agent_system_follow_latency_s": _median(agent_system_follow_latencies),
            "explicit_reply_count": reply_count,
            "median_explicit_reply_latency_s": _median(explicit_reply_latencies),
        },
        "collaboration_integrity_audit": build_collaboration_integrity_audit(
            rows=rows,
            registry_paths=registry_paths or [],
            max_detail_items=max_detail_items,
        ),
    }


def render_communication_audit_markdown(summary: dict[str, Any]) -> str:
    lines: list[str] = []
    totals = summary.get("totals") or {}
    rates = summary.get("rates") or {}
    response = summary.get("response_metrics") or {}
    time_range = summary.get("time_range") or {}
    scope = summary.get("scope") or {}
    lines.append("# 通讯分析报告")
    lines.append("")
    lines.append(f"- 范围: {', '.join(scope.get('runs_dirs') or [])}")
    lines.append(
        f"- 时间: {time_range.get('first_created_at') or 'N/A'} -> {time_range.get('last_created_at') or 'N/A'}"
    )
    lines.append(f"- 样本数: {int(totals.get('runs') or 0)}")
    lines.append("")

    lines.append("## 核心指标")
    lines.append(
        f"- 显式回复率: {rates.get('reply_to_rate_pct', 0)}% ({int(totals.get('reply_to_runs') or 0)} / {int(totals.get('runs') or 0)})"
    )
    lines.append(
        f"- @协同对象使用率: {rates.get('mention_target_rate_pct', 0)}% ({int(totals.get('mention_target_runs') or 0)} / {int(totals.get('runs') or 0)})"
    )
    lines.append(
        f"- communication_view 覆盖率: {rates.get('communication_view_rate_pct', 0)}% ({int(totals.get('communication_view_runs') or 0)} / {int(totals.get('runs') or 0)})"
    )
    lines.append(
        f"- receipt_summary 覆盖率: {rates.get('receipt_summary_rate_pct', 0)}% ({int(totals.get('receipt_summary_runs') or 0)} / {int(totals.get('runs') or 0)})"
    )
    lines.append(f"- legacy 占比: {rates.get('legacy_rate_pct', 0)}%")
    lines.append(f"- callback 路由错配率: {rates.get('route_mismatch_rate_pct', 0)}%")
    lines.append("")

    integrity = summary.get("collaboration_integrity_audit") if isinstance(summary.get("collaboration_integrity_audit"), dict) else {}
    if integrity:
        lines.append("## CCR 与送达证据巡检")
        lines.append(f"- 状态: {integrity.get('state') or 'unknown'}")
        lines.append(f"- 异常数: {int(integrity.get('issue_count') or 0)}")
        categories = integrity.get("category_counts") if isinstance(integrity.get("category_counts"), dict) else {}
        if categories:
            joined = "，".join(f"{key}={int(value or 0)}" for key, value in sorted(categories.items()))
            lines.append(f"- 异常分类: {joined}")
        else:
            lines.append("- 异常分类: 无")
        lines.append("")

    lines.append("## 响应情况")
    lines.append(
        f"- 用户消息同通道响应率: {response.get('user_responded_same_channel_rate_pct', 0)}% (窗口 {scope.get('response_window_hours', 0)}h)"
    )
    lines.append(f"- 用户消息同通道中位响应时延: {response.get('median_user_same_channel_latency_s')}")
    lines.append(
        f"- Agent 消息后续收到系统跟进率: {response.get('agent_system_follow_same_session_rate_pct', 0)}%"
    )
    lines.append(f"- Agent 系统跟进中位时延: {response.get('median_agent_system_follow_latency_s')}")
    lines.append(f"- 显式 reply_to 中位时延: {response.get('median_explicit_reply_latency_s')}")
    lines.append("")

    sections = [
        ("发送主体分布", summary.get("sender_type_breakdown") or []),
        ("状态分布", summary.get("status_breakdown") or []),
        ("沟通类型分布", summary.get("communication_message_kind_breakdown") or []),
        ("回执摘要类型分布", summary.get("receipt_summary_message_kind_breakdown") or []),
        ("Top 通道", summary.get("top_channels") or []),
        ("Top 来源通道", summary.get("top_source_channels") or []),
        ("Top 来源项目", summary.get("top_source_projects") or []),
        ("Top 目标项目", summary.get("top_target_projects") or []),
        ("Top 目标会话", summary.get("top_target_sessions") or []),
        ("Top 发送者", summary.get("top_sender_names") or []),
        ("Top 降级原因", summary.get("top_degrade_reasons") or []),
    ]
    for title, rows in sections:
        lines.append(f"## {title}")
        if not rows:
            lines.append("- 无")
            lines.append("")
            continue
        for row in rows:
            lines.append(f"- {row.get('name')}: {row.get('count')} ({row.get('percent')}%)")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Audit communication patterns from task-dashboard run artifacts")
    ap.add_argument(
        "--runs-dir",
        action="append",
        dest="runs_dirs",
        default=[],
        help="runs directory to inspect; can be passed multiple times",
    )
    ap.add_argument("--response-window-hours", type=float, default=2.0, help="response correlation window")
    ap.add_argument("--top-limit", type=int, default=8, help="top rows to keep for ranked stats")
    ap.add_argument("--include-hidden", action="store_true", help="include hidden runs")
    ap.add_argument(
        "--registry",
        action="append",
        dest="registry_paths",
        default=[],
        help="CCR registry path to audit; can be passed multiple times",
    )
    ap.add_argument("--format", choices=("json", "markdown"), default="json", help="output format")
    args = ap.parse_args(argv)

    runs_dirs_raw = list(args.runs_dirs or [])
    if not runs_dirs_raw:
        runs_dirs_raw = [".runtime/stable/.runs/hot"]
    runs_dirs = [Path(item) for item in runs_dirs_raw if str(item or "").strip()]
    registry_paths_raw = list(args.registry_paths or [])
    if not registry_paths_raw:
        default_registry = Path("registry/public-registry.v1.json")
        if default_registry.exists():
            registry_paths_raw = [str(default_registry)]
    registry_paths = [Path(item) for item in registry_paths_raw if str(item or "").strip()]
    summary = audit_communication_patterns(
        runs_dirs=runs_dirs,
        registry_paths=registry_paths,
        response_window_hours=float(args.response_window_hours or 0.0),
        top_limit=max(1, int(args.top_limit or 1)),
        include_hidden=bool(args.include_hidden),
    )
    if args.format == "markdown":
        print(render_communication_audit_markdown(summary), end="")
    else:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
