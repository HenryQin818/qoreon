#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Backward-compatible entrypoint.

Implementation moved to `task_dashboard/` to keep responsibilities separated
and to enable safer parallel iteration (build engine vs server vs UI).
"""

from __future__ import annotations

import sys
from pathlib import Path

from task_dashboard.cli import main


if __name__ == "__main__":
    script_path = Path(__file__).resolve()
    repo_root = script_path.parent
    default_out_task = str(Path("dist") / "project-task-dashboard.html")
    default_out_overview = str(Path("dist") / "project-overview-dashboard.html")
    default_out_communication = str(Path("dist") / "project-communication-audit.html")
    default_out_status_report = str(Path("dist") / "project-status-report.html")
    default_out_agent_directory = str(Path("dist") / "project-agent-directory.html")
    default_out_agent_curtain = str(Path("dist") / "project-agent-curtain.html")
    default_out_agent_relationship_board = str(Path("dist") / "project-agent-relationship-board.html")
    default_out_session_health = str(Path("dist") / "project-session-health-dashboard.html")
    forwarded = [
        "--root",
        str(repo_root),
        "--out-task",
        default_out_task,
        "--out-overview",
        default_out_overview,
        "--out-communication",
        default_out_communication,
        "--out-status-report",
        default_out_status_report,
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
    raise SystemExit(main(forwarded))
