#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from task_dashboard.public_agent_activation import activate_public_example_agents
from task_dashboard.public_bootstrap import DEFAULT_PROJECT_ID, PUBLIC_EXAMPLE_ROOTS


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create public example sessions and run lightweight collaboration actions."
    )
    parser.add_argument(
        "--repo-root",
        default=str(REPO_ROOT),
        help="Repository root. Defaults to the current qoreon repo root.",
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:18770",
        help="Local Qoreon server base URL.",
    )
    parser.add_argument(
        "--project-id",
        default=DEFAULT_PROJECT_ID,
        choices=tuple(PUBLIC_EXAMPLE_ROOTS.keys()),
        help="Which public example project to activate.",
    )
    parser.add_argument(
        "--token",
        default="",
        help="Optional task-dashboard token.",
    )
    parser.add_argument(
        "--include-optional",
        action="store_true",
        help="Also activate optional extension channels and agents.",
    )
    parser.add_argument(
        "--sessions-only",
        action="store_true",
        help="Only create/reuse channel sessions, without sending the first round of sample actions.",
    )
    parser.add_argument(
        "--wait-timeout",
        type=float,
        default=240.0,
        help="How long to wait for sample runs to finish.",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=2.0,
        help="Polling interval for run status.",
    )
    args = parser.parse_args()

    result = activate_public_example_agents(
        Path(str(args.repo_root)).expanduser().resolve(),
        base_url=str(args.base_url),
        project_id=str(args.project_id),
        token=str(args.token or ""),
        include_optional=bool(args.include_optional),
        run_sample_actions=not bool(args.sessions_only),
        wait_timeout_s=float(args.wait_timeout),
        poll_interval_s=float(args.poll_interval),
    )
    sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
