# -*- coding: utf-8 -*-

from __future__ import annotations

import time
from typing import Any

from task_dashboard.runtime.process_control import terminate_process_tree


def detect_execution_timeout(
    *,
    timeout_enabled: bool,
    timeout_value: int,
    start_ts: float,
    now_ts: float,
    no_progress_enabled: bool,
    no_progress_value: int,
    last_progress_ts: float,
) -> str:
    if timeout_enabled and (time.time() - start_ts) > timeout_value:
        return f"timeout>{timeout_value}s"
    if no_progress_enabled and (now_ts - last_progress_ts) > no_progress_value:
        return f"timeout>no_progress>{no_progress_value}s"
    return ""


def terminate_process_for_timeout(proc: Any, timeout_error: str, *, sleep_s: float = 0.25) -> None:
    terminate_process_tree(
        proc,
        graceful="no_progress" in str(timeout_error or ""),
        sleep_s=sleep_s,
    )
