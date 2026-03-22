#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from task_dashboard.public_bootstrap import PUBLIC_EXAMPLE_ROOTS
from task_dashboard.public_install import install_public_bundle


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Low-level installer for the public Qoreon bundle. For normal installs, prefer scripts/start_standard_project.py. This command is mainly for advanced control or troubleshooting."
    )
    parser.add_argument(
        "--repo-root",
        default=str(REPO_ROOT),
        help="Repository root. Defaults to the current qoreon repo root.",
    )
    parser.add_argument(
        "--bootstrap-profile",
        default="standard",
        choices=("standard",),
        help="Which bundled example projects to bootstrap. Public bundle defaults to the single standard project.",
    )
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="Skip build_project_task_dashboard.py.",
    )
    parser.add_argument(
        "--start-server",
        action="store_true",
        help="Start the local demo server and wait for /__health.",
    )
    parser.add_argument(
        "--bind",
        default="127.0.0.1",
        help="Server bind address when --start-server is used.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=18770,
        help="Server port when --start-server is used.",
    )
    parser.add_argument(
        "--base-url",
        default="",
        help="Override server base URL. Defaults to http://127.0.0.1:<port>.",
    )
    parser.add_argument(
        "--activate-project",
        default="",
        choices=("", *tuple(PUBLIC_EXAMPLE_ROOTS.keys())),
        help="Override which public example project to activate. Defaults to standard_project unless --skip-agent-activation is set.",
    )
    parser.add_argument(
        "--token",
        default="",
        help="Optional task-dashboard token for protected local services.",
    )
    parser.add_argument(
        "--include-optional",
        action="store_true",
        help="Also activate optional extension channels when activation is enabled. Standard install defaults to all channels unless --core-only is set.",
    )
    parser.add_argument(
        "--core-only",
        action="store_true",
        help="Only create the default core channels. By default standard install creates all standard_project channels.",
    )
    parser.add_argument(
        "--skip-agent-activation",
        action="store_true",
        help="Page-only/troubleshooting mode. Only bootstrap/build/start the project, without creating any default standard_project channel sessions.",
    )
    parser.add_argument(
        "--run-sample-actions",
        action="store_true",
        help="After creating the default sessions, also run the first-wave training/sample actions.",
    )
    parser.add_argument(
        "--wait-timeout",
        type=float,
        default=900.0,
        help="How long to wait for standard-project session creation and optional sample runs on a new computer.",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=2.0,
        help="Polling interval for activation sample runs.",
    )
    args = parser.parse_args()

    bootstrap_projects = {
        "standard": ["standard_project"],
    }[str(args.bootstrap_profile)]
    default_activate_project = ""
    if not bool(args.skip_agent_activation):
        default_activate_project = bootstrap_projects[0]
    activate_project = str(args.activate_project or default_activate_project or "")
    include_optional = bool(args.include_optional) or (activate_project == "standard_project" and not bool(args.core_only))

    result = install_public_bundle(
        Path(str(args.repo_root)).expanduser().resolve(),
        bootstrap_projects=bootstrap_projects,
        build_pages=not bool(args.skip_build),
        start_server=bool(args.start_server),
        bind=str(args.bind),
        port=int(args.port),
        base_url=str(args.base_url or ""),
        activate_project=activate_project,
        token=str(args.token or ""),
        include_optional=include_optional,
        activation_run_samples=bool(args.run_sample_actions),
        wait_timeout_s=float(args.wait_timeout),
        poll_interval_s=float(args.poll_interval),
    )
    sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
