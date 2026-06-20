from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .runstore_health import (
    build_runstore_health_response,
    create_runstore_archive_dry_run,
    execute_runstore_archive_plan,
    list_runstore_hot_runs_response,
)
from .utils import repo_root_from_here


class RunStorePathView:
    """Minimal RunStore view for health CLI; it never creates or deletes data."""

    def __init__(self, runs_dir: Path) -> None:
        self.runs_dir = runs_dir
        self.hot_dir = runs_dir / "hot"
        self.archive_dir = runs_dir / "archive"

    def _remove_live_run_index_entry(self, _run_id: str) -> None:
        return None


def _as_str(value: Any) -> str:
    return "" if value is None else str(value)


def _runs_dir(args: argparse.Namespace) -> Path:
    raw = _as_str(getattr(args, "runs_dir", "")).strip()
    if raw:
        path = Path(raw).expanduser()
        return path.resolve() if path.is_absolute() else (Path.cwd() / path).resolve()
    root = Path(getattr(args, "root", "") or repo_root_from_here(__file__)).expanduser().resolve()
    return (root / ".runtime" / "stable" / ".runs").resolve()


def _print_payload(code: int, payload: dict[str, Any]) -> int:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if 200 <= int(code) < 300 and bool(payload.get("ok", True)) else 1


def _query_from_args(args: argparse.Namespace) -> dict[str, list[str]]:
    pairs = {
        "projectId": _as_str(getattr(args, "project_id", "")).strip(),
        "session_id": _as_str(getattr(args, "session_id", "")).strip(),
        "status": _as_str(getattr(args, "status", "")).strip(),
        "state_group": _as_str(getattr(args, "state_group", "")).strip(),
        "older_than_hours": _as_str(getattr(args, "older_than_hours", "")).strip(),
        "older_than_days": _as_str(getattr(args, "older_than_days", "")).strip(),
        "limit": _as_str(getattr(args, "limit", "")).strip(),
        "offset": _as_str(getattr(args, "offset", "")).strip(),
    }
    return {key: [value] for key, value in pairs.items() if value}


def _cmd_health(args: argparse.Namespace) -> int:
    store = RunStorePathView(_runs_dir(args))
    code, payload = build_runstore_health_response(store, project_id=args.project_id)
    return _print_payload(code, payload)


def _cmd_hot_runs(args: argparse.Namespace) -> int:
    store = RunStorePathView(_runs_dir(args))
    code, payload = list_runstore_hot_runs_response(store, query=_query_from_args(args))
    return _print_payload(code, payload)


def _cmd_archive_dry_run(args: argparse.Namespace) -> int:
    store = RunStorePathView(_runs_dir(args))
    body = {
        "scope": args.scope,
        "session_id": args.session_id,
        "older_than_hours": args.older_than_hours,
        "older_than_days": args.older_than_days,
        "statuses": [item.strip() for item in _as_str(args.statuses).split(",") if item.strip()],
        "limit": args.limit,
        "reason": args.reason,
        "projectId": args.project_id,
    }
    code, payload = create_runstore_archive_dry_run(store, body=body)
    return _print_payload(code, payload)


def _cmd_archive_execute(args: argparse.Namespace) -> int:
    store = RunStorePathView(_runs_dir(args))
    body = {
        "job_id": args.job_id,
        "confirm": bool(args.confirm),
        "expected_eligible_count": args.expected_eligible_count,
        "sender_type": "user",
        "sender_name": "runstore_cli",
    }
    code, payload = execute_runstore_archive_plan(store, body=body)
    return _print_payload(code, payload)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="runstore_cli")
    parser.add_argument("--root", default=str(repo_root_from_here(__file__)), help="task-dashboard repo root")
    parser.add_argument("--runs-dir", default="", help="RunStore .runs directory; default: <root>/.runtime/stable/.runs")
    parser.add_argument("--project-id", default="", help="optional project id filter")
    sub = parser.add_subparsers(dest="command", required=True)

    health = sub.add_parser("health", help="print RunStore hot/archive health summary")
    health.set_defaults(func=_cmd_health)

    hot = sub.add_parser("hot-runs", help="list hot run summaries")
    hot.add_argument("--session-id", default="")
    hot.add_argument("--status", default="")
    hot.add_argument("--state-group", default="")
    hot.add_argument("--older-than-hours", type=int, default=0)
    hot.add_argument("--older-than-days", type=int, default=0)
    hot.add_argument("--limit", type=int, default=50)
    hot.add_argument("--offset", type=int, default=0)
    hot.set_defaults(func=_cmd_hot_runs)

    dry = sub.add_parser("archive-dry-run", help="create an archive plan without moving files")
    dry.add_argument("--scope", choices=["all", "session"], default="all")
    dry.add_argument("--session-id", default="")
    dry.add_argument("--older-than-hours", type=int, default=48)
    dry.add_argument("--older-than-days", type=int, default=0)
    dry.add_argument("--statuses", default="done,error,interrupted")
    dry.add_argument("--limit", type=int, default=500)
    dry.add_argument("--reason", default="runstore_cli_dry_run")
    dry.set_defaults(func=_cmd_archive_dry_run)

    execute = sub.add_parser("archive-execute", help="execute a prior archive dry-run job")
    execute.add_argument("--job-id", required=True)
    execute.add_argument("--confirm", action="store_true")
    execute.add_argument("--expected-eligible-count", type=int, default=None)
    execute.set_defaults(func=_cmd_archive_execute)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
