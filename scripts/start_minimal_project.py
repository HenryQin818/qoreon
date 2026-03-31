#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from task_dashboard.public_install import install_public_bundle, _terminate_server_on_port


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Recommended init/start entrypoint for minimal_project."
    )
    parser.add_argument(
        "--with-agents",
        action="store_true",
        help="After creating the default core sessions, also run the first-wave training/sample actions.",
    )
    parser.add_argument(
        "--include-optional",
        action="store_true",
        help="Also activate the optional support channels.",
    )
    parser.add_argument(
        "--background",
        action="store_true",
        help="Keep the current behavior and leave the local server running in the background.",
    )
    args = parser.parse_args()

    result = install_public_bundle(
        REPO_ROOT,
        bootstrap_projects=["minimal_project"],
        build_pages=True,
        start_server=True,
        port=18770,
        activate_project="minimal_project",
        include_optional=bool(args.include_optional),
        activation_run_samples=bool(args.with_agents),
        wait_timeout_s=900.0,
        poll_interval_s=2.0,
    )
    result["default_entry"] = "http://127.0.0.1:18770/"
    result["project_home"] = "http://127.0.0.1:18770/"
    if bool(args.background):
        sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        return 0

    server_result = result.get("server") if isinstance(result.get("server"), dict) else {}
    if bool(server_result.get("reused")):
        result["server_mode"] = "reused_existing"
        result["message"] = "检测到 18770 端口已有服务在运行，直接复用，不再额外拉起前台服务。"
        sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        return 0

    if server_result.get("pid"):
        try:
            _terminate_server_on_port(18770, base_url="http://127.0.0.1:18770")
        except Exception as exc:
            raise RuntimeError(f"failed to switch background server to foreground mode: {exc}") from exc

    summary = {
        "ok": True,
        "project_id": "minimal_project",
        "default_entry": "http://127.0.0.1:18770/",
        "agent_activation_state": result.get("agent_activation_state"),
        "message": "初始化已完成，下面开始以前台方式运行 server.py。按 Ctrl+C 可停止服务。",
    }
    sys.stdout.write(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    sys.stdout.flush()

    cmd = [
        sys.executable,
        "server.py",
        "--bind",
        "127.0.0.1",
        "--port",
        "18770",
        "--static-root",
        "dist",
    ]
    return subprocess.run(cmd, cwd=REPO_ROOT, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
