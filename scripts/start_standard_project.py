#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import argparse
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from task_dashboard.public_install import install_public_bundle


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Recommended install/start entrypoint for the public Qoreon bundle on a new computer."
    )
    parser.add_argument(
        "--with-agents",
        action="store_true",
        help="After creating all standard_project sessions, also run the first-wave training and sample coordination actions.",
    )
    parser.add_argument(
        "--core-only",
        action="store_true",
        help="Only create the core channels. By default this command creates all standard_project channel sessions.",
    )
    args = parser.parse_args()
    include_optional = not bool(args.core_only)

    result = install_public_bundle(
        REPO_ROOT,
        bootstrap_projects=["standard_project"],
        build_pages=True,
        start_server=True,
        port=18770,
        activate_project="standard_project",
        include_optional=include_optional,
        activation_run_samples=bool(args.with_agents),
        wait_timeout_s=900.0,
        poll_interval_s=2.0,
    )
    batches = result.get("startup_batches") if isinstance(result.get("startup_batches"), list) else []
    result["agent_startup_mode"] = "activated" if bool(args.with_agents) else "sessions_ready"
    result["agent_startup_batch"] = batches[0] if batches else {}
    sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
