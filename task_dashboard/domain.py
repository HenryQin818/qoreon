from __future__ import annotations

import datetime as dt
import re
from typing import Iterable


RE_SESSION_ID = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

DONE_STATUSES = {"已完成", "已验收通过", "已消费", "已解决", "已关闭", "已停止"}
PAUSE_STATUSES = {"已暂停", "暂缓"}


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

