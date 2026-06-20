from __future__ import annotations

from typing import Any, Callable


RUN_PROGRESS_FRESHNESS_S = 120


def count_process_projection_events(meta: dict[str, Any]) -> int:
    count = 0
    for key in ("processEvents", "process_events", "processRows", "process_rows"):
        value = meta.get(key)
        if isinstance(value, list):
            count = max(count, len(value))
    return count


def has_recent_running_progress(
    meta: dict[str, Any],
    *,
    now_ts: float,
    parse_iso_ts: Callable[[Any], float],
    freshness_s: int = RUN_PROGRESS_FRESHNESS_S,
    previous_process_event_count: int | None = None,
) -> bool:
    try:
        last_progress_ts = float(parse_iso_ts(meta.get("lastProgressAt")) or 0.0)
    except Exception:
        last_progress_ts = 0.0
    if last_progress_ts > 0 and (now_ts - last_progress_ts) <= max(0, int(freshness_s)):
        return True

    current_process_event_count = count_process_projection_events(meta)
    if previous_process_event_count is not None and current_process_event_count > previous_process_event_count:
        return True
    return False
