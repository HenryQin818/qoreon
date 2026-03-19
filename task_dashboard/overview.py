from __future__ import annotations

from typing import Any

from .domain import bucket_key_for_status, looks_like_session_id, max_updated_at, score_bucket
from .project_source import resolve_project_source


def _is_task_item(it: dict[str, Any]) -> bool:
    return str(it.get("type") or "").strip() == "任务"


def _is_requirement_item(it: dict[str, Any]) -> bool:
    return str(it.get("type") or "").strip() == "需求"


def _is_active_item(it: dict[str, Any]) -> bool:
    return bucket_key_for_status(str(it.get("status") or "")) not in {"已完成", "已暂停"}


def _is_done_item(it: dict[str, Any]) -> bool:
    return bucket_key_for_status(str(it.get("status") or "")) == "已完成"


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


def _resolve_requirements_switch(
    proj: dict[str, Any],
    channel_name: str,
    *,
    legacy_has_requirements: bool,
) -> tuple[bool, str, bool]:
    channel_sessions = proj.get("channel_sessions") if isinstance(proj, dict) else []
    if isinstance(channel_sessions, list):
        for row in channel_sessions:
            if not isinstance(row, dict):
                continue
            if str(row.get("name") or "").strip() != channel_name:
                continue
            effective = row.get("requirements_enabled_effective")
            if isinstance(effective, bool):
                source = str(row.get("requirements_source") or "").strip() or ("config" if "enable_requirements" in row else "")
                if not source:
                    source = "legacy_detect" if bool(effective) else "default_false"
                explicit_cfg = _as_optional_bool(
                    row.get("enable_requirements") if "enable_requirements" in row else row.get("enableRequirements")
                )
                return bool(effective), source, bool(explicit_cfg) if explicit_cfg is not None else False
            explicit = _as_optional_bool(
                row.get("enable_requirements") if "enable_requirements" in row else row.get("enableRequirements")
            )
            if explicit is not None:
                return bool(explicit), "config", bool(explicit)
            break
    if legacy_has_requirements:
        return True, "legacy_detect", False
    return False, "default_false", False


def build_overview(projects_meta: list[dict[str, Any]], items_payload: list[dict[str, Any]]) -> dict[str, Any]:
    projects_by_id = {str(p.get("id") or ""): p for p in projects_meta}
    buckets = ["督办", "进行中", "待开始", "待处理", "待验收", "待消费", "其他", "已暂停", "已完成"]

    project_cards: list[dict[str, Any]] = []
    for pid, proj in projects_by_id.items():
        if not pid:
            continue
        pitems_all = [it for it in items_payload if str(it.get("project_id") or "") == pid]
        pitems = [it for it in pitems_all if _is_task_item(it)]

        channel_names = set()
        for it in pitems_all:
            ch = str(it.get("channel") or "").strip()
            if ch:
                channel_names.add(ch)
        for ch in proj.get("channels") or []:
            name = str((ch or {}).get("name") or "").strip()
            if name:
                channel_names.add(name)
        for chs in proj.get("channel_sessions") or []:
            name = str((chs or {}).get("name") or "").strip()
            if name:
                channel_names.add(name)

        chan_cards = []
        for ch_name in sorted(channel_names):
            citems_all = [it for it in pitems_all if str(it.get("channel") or "") == ch_name]
            citems = [it for it in citems_all if _is_task_item(it)]
            req_items = [it for it in citems_all if _is_requirement_item(it)]
            req_enabled, req_source, req_config_value = _resolve_requirements_switch(
                proj,
                ch_name,
                legacy_has_requirements=bool(req_items),
            )
            counts = {k: 0 for k in buckets}
            score = 0
            for it in citems:
                b = bucket_key_for_status(str(it.get("status") or ""))
                counts[b] = counts.get(b, 0) + 1
                score += score_bucket(b)

            session_configured = False
            for s in (proj.get("channel_sessions") or []):
                if str((s or {}).get("name") or "") == ch_name:
                    sid = str((s or {}).get("session_id") or "").strip()
                    session_configured = looks_like_session_id(sid)
                    break

            chan_cards.append(
                {
                    "name": ch_name,
                    "totals": {
                        "total": len(citems),
                        "requirements_total": len(req_items) if req_enabled else 0,
                        "requirements_active": sum(
                            1 for it in req_items if _is_active_item(it)
                        ) if req_enabled else 0,
                        "active": sum(1 for it in citems if _is_active_item(it)),
                        "done": counts["已完成"],
                        "supervised": counts["督办"],
                        "in_progress": counts["进行中"],
                        "todo": counts["待开始"] + counts["待处理"] + counts["待验收"] + counts["待消费"] + counts["其他"],
                        "paused": counts["已暂停"],
                        "items_total": len(citems_all),
                        "items_active": sum(1 for it in citems_all if _is_active_item(it)),
                        "items_done": sum(1 for it in citems_all if _is_done_item(it)),
                    },
                    "updated_at": max_updated_at(str(it.get("updated_at") or "") for it in citems),
                    "score": score,
                    "session_configured": session_configured,
                    "enable_requirements": bool(req_config_value),
                    "requirements_enabled_effective": bool(req_enabled),
                    "requirements_source": req_source,
                }
            )

        # Sort high-score first, then latest update, then name.
        def _ts(v: str) -> float:
            from .domain import _parse_iso  # internal helper

            return _parse_iso(v).timestamp()

        chan_cards = sorted(
            chan_cards,
            key=lambda x: (-int(x.get("score") or 0), -_ts(str(x.get("updated_at") or "")), str(x.get("name") or "")),
        )

        p_counts = {k: 0 for k in buckets}
        p_score = 0
        for it in pitems:
            b = bucket_key_for_status(str(it.get("status") or ""))
            p_counts[b] = p_counts.get(b, 0) + 1
            p_score += score_bucket(b)
        p_requirements_total = sum(int((c.get("totals") or {}).get("requirements_total") or 0) for c in chan_cards)
        p_requirements_active = sum(int((c.get("totals") or {}).get("requirements_active") or 0) for c in chan_cards)

        project_cards.append(
            {
                "project_id": pid,
                "project_name": str(proj.get("name") or pid),
                "color": str(proj.get("color") or ""),
                "description": str(proj.get("description") or ""),
                **resolve_project_source(proj),
                "totals": {
                    "total": len(pitems),
                    "requirements_total": p_requirements_total,
                    "requirements_active": p_requirements_active,
                    "channels": len(chan_cards),
                    "active": sum(1 for it in pitems if _is_active_item(it)),
                    "done": p_counts["已完成"],
                    "supervised": p_counts["督办"],
                    "in_progress": p_counts["进行中"],
                    "todo": p_counts["待开始"] + p_counts["待处理"] + p_counts["待验收"] + p_counts["待消费"] + p_counts["其他"],
                    "paused": p_counts["已暂停"],
                    "items_total": len(pitems_all),
                    "items_active": sum(1 for it in pitems_all if _is_active_item(it)),
                    "items_done": sum(1 for it in pitems_all if _is_done_item(it)),
                },
                "updated_at": max_updated_at(str(it.get("updated_at") or "") for it in pitems),
                "score": p_score,
                "channels_data": chan_cards,
            }
        )

    def _ts2(v: str) -> float:
        from .domain import _parse_iso  # internal helper

        return _parse_iso(v).timestamp()

    project_cards = sorted(
        project_cards,
        key=lambda x: (-int(x.get("score") or 0), -_ts2(str(x.get("updated_at") or "")), str(x.get("project_name") or "")),
    )

    all_items = list(items_payload)
    task_items = [it for it in all_items if _is_task_item(it)]
    global_requirements_total = sum(int((p.get("totals") or {}).get("requirements_total") or 0) for p in project_cards)
    global_requirements_active = sum(int((p.get("totals") or {}).get("requirements_active") or 0) for p in project_cards)
    global_counts = {
        "projects": len(project_cards),
        "total": len(task_items),
        "requirements_total": global_requirements_total,
        "requirements_active": global_requirements_active,
        "active": sum(1 for it in task_items if _is_active_item(it)),
        "done": sum(1 for it in task_items if _is_done_item(it)),
        "supervised": sum(1 for it in task_items if bucket_key_for_status(str(it.get("status") or "")) == "督办"),
        "in_progress": sum(1 for it in task_items if bucket_key_for_status(str(it.get("status") or "")) == "进行中"),
        "channels": sum(len(p.get("channels_data") or []) for p in project_cards),
        "updated_at": max_updated_at(str(it.get("updated_at") or "") for it in all_items),
        "items_total": len(all_items),
        "items_active": sum(1 for it in all_items if _is_active_item(it)),
        "items_done": sum(1 for it in all_items if _is_done_item(it)),
    }
    return {"totals": global_counts, "projects": project_cards}
