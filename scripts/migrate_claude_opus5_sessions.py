#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Dry-run-first Claude Opus 5 SessionStore migration CLI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from task_dashboard.config import (  # noqa: E402
    resolve_dashboard_config_path,
    resolve_dashboard_local_config_path,
)
from task_dashboard.runtime.claude_model_migration import (  # noqa: E402
    ClaudeModelMigrationError,
    apply_manifest,
    build_dry_run_manifest,
    rollback_manifest,
    verify_manifest,
    write_manifest,
)


WRITE_ACK = "APPLY_CLAUDE_OPUS5_SESSION_MIGRATION"


def _default_config_paths() -> list[Path]:
    candidates = [
        resolve_dashboard_config_path(REPO_ROOT),
        resolve_dashboard_local_config_path(REPO_ROOT),
        REPO_ROOT / "config.dev_control.toml",
    ]
    out: list[Path] = []
    seen: set[str] = set()
    for path in candidates:
        resolved = Path(path).expanduser().resolve()
        key = str(resolved)
        if key in seen:
            continue
        seen.add(key)
        out.append(resolved)
    return out


def _print_json(payload: dict[str, Any], *, stream=None) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2), file=stream or sys.stdout)


def _require_write_ack(args: argparse.Namespace) -> None:
    if str(args.write_ack or "").strip() != WRITE_ACK:
        raise ClaudeModelMigrationError(
            "write_ack_required",
            "apply/rollback requires the exact --write-ack token",
            details={"required": WRITE_ACK},
        )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Claude Opus 4.8 -> Opus 5 controlled migration")
    subparsers = parser.add_subparsers(dest="command", required=True)

    dry_run = subparsers.add_parser("dry-run", help="scan only and write a manifest outside SessionStore")
    dry_run.add_argument(
        "--runtime-root",
        type=Path,
        default=REPO_ROOT / ".runtime" / "stable",
    )
    dry_run.add_argument("--output", type=Path, required=True)
    dry_run.add_argument("--config", action="append", type=Path, default=[])

    for command in ("apply", "rollback"):
        write_parser = subparsers.add_parser(command)
        write_parser.add_argument("--manifest", type=Path, required=True)
        write_parser.add_argument("--write-ack", default="")

    verify = subparsers.add_parser("verify")
    verify.add_argument("--manifest", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "dry-run":
            config_paths = list(args.config or []) or _default_config_paths()
            manifest = build_dry_run_manifest(
                args.runtime_root,
                repo_root=REPO_ROOT,
                config_paths=config_paths,
            )
            output_path = write_manifest(args.output, manifest)
            _print_json(
                {
                    "ok": True,
                    "command": "dry-run",
                    "manifest": str(output_path),
                    "apply_allowed": bool(manifest.get("apply_allowed")),
                    "session_totals": manifest.get("session_scan", {}).get("totals", {}),
                    "config_scan": manifest.get("config_scan", {}),
                }
            )
            return 0
        if args.command == "apply":
            _require_write_ack(args)
            _print_json({"ok": True, "command": "apply", "journal": apply_manifest(args.manifest)})
            return 0
        if args.command == "verify":
            _print_json({"ok": True, "command": "verify", "verification": verify_manifest(args.manifest)})
            return 0
        if args.command == "rollback":
            _require_write_ack(args)
            _print_json({"ok": True, "command": "rollback", "journal": rollback_manifest(args.manifest)})
            return 0
        parser.error("unsupported command")
    except ClaudeModelMigrationError as exc:
        _print_json(
            {
                "ok": False,
                "error_code": exc.code,
                "error": str(exc),
                "details": exc.details,
            },
            stream=sys.stderr,
        )
        return 2
    except Exception as exc:
        _print_json(
            {
                "ok": False,
                "error_code": "unexpected_error",
                "error": str(exc),
            },
            stream=sys.stderr,
        )
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
