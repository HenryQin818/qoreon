from __future__ import annotations

import datetime as dt
import re
from typing import Any, Iterable


RE_SESSION_ID = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

DONE_STATUSES = {"已完成", "已验收通过", "已消费", "已解决", "已关闭", "已停止", "已合并", "完成", "已归档"}
PAUSE_STATUSES = {"已暂停", "暂缓"}
TODO_STATUSES = {"待开始", "待处理", "待消费", "其他"}
PRIMARY_ACTIVE_TASK_STATUSES = {"待办", "进行中", "待验收"}


def looks_like_session_id(s: str) -> bool:
    return bool(RE_SESSION_ID.match((s or "").strip()))


def bucket_key_for_status(status: str) -> str:
    s = (status or "").strip()
    if "督办" in s:
        return "督办"
    if "进行中" in s:
        return "进行中"
    if "待开始" in s:
        return "待开始"
    if "待处理" in s:
        return "待处理"
    if "待验收" in s:
        return "待验收"
    if "待消费" in s:
        return "待消费"
    if s in DONE_STATUSES:
        return "已完成"
    if s in PAUSE_STATUSES:
        return "已暂停"
    return "其他"


def normalize_task_status(status: str) -> dict[str, Any]:
    s = (status or "").strip()
    supervised = "督办" in s
    blocked = any(token in s for token in ("阻塞", "异常"))

    primary_status = ""
    lifecycle_state = "unknown"
    if not s:
        primary_status = ""
        lifecycle_state = "unknown"
    elif s in DONE_STATUSES:
        primary_status = "已完成"
        lifecycle_state = "done"
    elif s in PAUSE_STATUSES:
        primary_status = "暂缓"
        lifecycle_state = "paused"
    elif "待验收" in s:
        primary_status = "待验收"
        lifecycle_state = "pending_acceptance"
    elif "进行中" in s or blocked:
        primary_status = "进行中"
        lifecycle_state = "in_progress"
    elif supervised or s in TODO_STATUSES:
        primary_status = "待办"
        lifecycle_state = "todo"
    else:
        primary_status = "待办"
        lifecycle_state = "todo"

    counts_as_wip = primary_status == "进行中"
    is_active = primary_status in PRIMARY_ACTIVE_TASK_STATUSES
    status_bucket = "other"
    if primary_status == "进行中":
        status_bucket = "blocked" if blocked else "in_progress"
    elif primary_status == "待验收":
        status_bucket = "pending_acceptance"
    elif primary_status == "已完成":
        status_bucket = "done"

    return {
        "raw_status": s,
        "primary_status": primary_status,
        "lifecycle_state": lifecycle_state,
        "counts_as_wip": counts_as_wip,
        "is_active": is_active,
        "status_bucket": status_bucket,
        "status_flags": {
            "supervised": supervised,
            "blocked": blocked,
        },
    }


def score_bucket(bucket: str) -> int:
    if bucket == "督办":
        return 1000
    if bucket == "进行中":
        return 300
    if bucket in {"待验收", "待消费", "待处理", "待开始"}:
        return 120
    if bucket == "其他":
        return 20
    if bucket == "已暂停":
        return 5
    if bucket == "已完成":
        return 1
    return 0


def _parse_iso(iso_s: str) -> dt.datetime:
    s = (iso_s or "").strip()
    if not s:
        return dt.datetime.fromtimestamp(0, tz=dt.timezone.utc)
    try:
        return dt.datetime.fromisoformat(s)
    except Exception:
        return dt.datetime.fromtimestamp(0, tz=dt.timezone.utc)


def max_updated_at(values: Iterable[str]) -> str:
    vals = [v for v in values if (v or "").strip()]
    if not vals:
        return ""
    return max(vals, key=lambda x: _parse_iso(x))
