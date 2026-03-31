#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from task_dashboard.public_agent_activation import write_public_example_startup_batch
from task_dashboard.public_bootstrap import bootstrap_public_example
from task_dashboard.public_install import _run_build


def main() -> int:
    bootstrap_result = bootstrap_public_example(REPO_ROOT, project_id="minimal_project")
    startup_batch = write_public_example_startup_batch(
        REPO_ROOT,
        project_id="minimal_project",
        include_optional=False,
    )
    build_result = _run_build(REPO_ROOT)
    result = {
        "ok": True,
        "project_id": "minimal_project",
        "bootstrap": bootstrap_result,
        "build": build_result,
        "startup_batch": startup_batch,
        "default_entry": "dist/index.html",
        "next_steps": [
            "python scripts/start_minimal_project.py",
            "打开 http://127.0.0.1:18770/",
        ],
    }
    sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
