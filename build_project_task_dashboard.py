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
from task_dashboard.helpers import _repo_root


if __name__ == "__main__":
    script_path = Path(__file__).resolve()
    repo_root = script_path.parent
    workspace_root = _repo_root().resolve()
    try:
        repo_rel = repo_root.relative_to(workspace_root)
    except Exception:
        repo_rel = Path(repo_root.name)
    default_out_task = str(repo_rel / "dist" / "project-task-dashboard.html")
    default_out_overview = str(repo_rel / "dist" / "project-overview-dashboard.html")
    default_out_communication = str(repo_rel / "dist" / "project-communication-audit.html")
    default_out_status_report = str(repo_rel / "dist" / "project-status-report.html")
    default_out_open_source_sync = str(repo_rel / "dist" / "project-open-source-sync-board.html")
    default_out_agent_directory = str(repo_rel / "dist" / "project-agent-directory.html")
    default_out_agent_curtain = str(repo_rel / "dist" / "project-agent-curtain.html")
    default_out_agent_relationship_board = str(repo_rel / "dist" / "project-agent-relationship-board.html")
    default_out_session_health = str(repo_rel / "dist" / "project-session-health-dashboard.html")
    forwarded = [
        "--root",
        str(workspace_root),
        "--out-task",
        default_out_task,
        "--out-overview",
        default_out_overview,
        "--out-communication",
        default_out_communication,
        "--out-status-report",
        default_out_status_report,
        "--out-open-source-sync",
        default_out_open_source_sync,
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
