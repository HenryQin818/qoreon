#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Backward-compatible entrypoint.

Implementation moved to `task_dashboard/` to keep responsibilities separated
and to enable safer parallel iteration (build engine vs server vs UI).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from task_dashboard.cli import main


def _restore_env(previous: dict[str, str | None]) -> None:
    for key, value in previous.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


if __name__ == "__main__":
    build_env_keys = ("TASK_DASHBOARD_SESSION_HEALTH_SKIP_LOG_SCAN", "TASK_DASHBOARD_STATIC_BUILD_FAST")
    previous_build_env = {key: os.environ.get(key) for key in build_env_keys}
    os.environ.setdefault("TASK_DASHBOARD_SESSION_HEALTH_SKIP_LOG_SCAN", "1")
    os.environ.setdefault("TASK_DASHBOARD_STATIC_BUILD_FAST", "1")
    script_path = Path(__file__).resolve()
    repo_root = script_path.parent
    repo_rel = Path(".")
    default_out_task = str(repo_rel / "dist" / "project-task-dashboard.html")
    default_out_overview = str(repo_rel / "dist" / "project-overview-dashboard.html")
    default_out_communication = str(repo_rel / "dist" / "project-communication-audit.html")
    default_out_project_chat = str(repo_rel / "dist" / "project-chat.html")
    default_out_message_risk_dashboard = str(repo_rel / "dist" / "project-message-risk-dashboard.html")
    default_out_agent_capability_report = str(repo_rel / "dist" / "project-agent-capability-dashboard.html")
    default_out_status_report = str(repo_rel / "dist" / "project-status-report.html")
    default_out_open_source_sync = str(repo_rel / "dist" / "project-open-source-sync-board.html")
    default_out_platform_architecture_board = str(repo_rel / "dist" / "project-platform-architecture-board.html")
    default_out_agent_directory = str(repo_rel / "dist" / "project-agent-directory.html")
    default_out_agent_curtain = str(repo_rel / "dist" / "project-agent-curtain.html")
    default_out_agent_relationship_board = str(repo_rel / "dist" / "project-agent-relationship-board.html")
    default_out_session_health = str(repo_rel / "dist" / "project-session-health-dashboard.html")
    forwarded = [
        "--root",
        str(repo_root),
        "--out-task",
        default_out_task,
        "--out-overview",
        default_out_overview,
        "--out-communication",
        default_out_communication,
        "--out-project-chat",
        default_out_project_chat,
        "--out-message-risk-dashboard",
        default_out_message_risk_dashboard,
        "--out-agent-capability-report",
        default_out_agent_capability_report,
        "--out-status-report",
        default_out_status_report,
        "--out-open-source-sync",
        default_out_open_source_sync,
        "--out-platform-architecture-board",
        default_out_platform_architecture_board,
        "--out-agent-directory",
        default_out_agent_directory,
        "--out-agent-curtain",
        default_out_agent_curtain,
        "--out-agent-relationship-board",
        default_out_agent_relationship_board,
        "--out-session-health",
        default_out_session_health,
        *sys.argv[1:],
    ]
    try:
        exit_code = main(forwarded)
    finally:
        _restore_env(previous_build_env)
    raise SystemExit(exit_code)
