#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Thin CodeBuddy subprocess wrapper for CCB runs.

CodeBuddy's JSON output is an event array that includes user/system/reasoning
records. CCB only needs the final assistant result in `.last.txt`.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from task_dashboard.adapters.base import resolve_cli_executable
from task_dashboard.adapters.codebuddy_output import (
    extract_final_text,
    is_unsafe_raw_output_text,
    normalize_process_events,
)
from task_dashboard.codebuddy_permissions import codebuddy_permission_mode_cli_arg


_TEMPFAIL_EXIT_CODE = 75
_CONFIG_EXIT_CODE = 78
_GENERAL_ERROR_EXIT_CODE = 1

_PROVIDER_TRANSIENT_RE = re.compile(
    r"\b429\b|too many requests|rate limit(?:ed|ing)?"
    r"|\b(?:500|502|503|504)\b"
    r"|bad gateway|service unavailable|gateway timeout"
    r"|etimedout|econnreset|socket hang up|connection reset"
    r"|copilot\.tencent\.com",
    re.IGNORECASE,
)
_UNSUPPORTED_MODEL_RE = re.compile(
    r"\b400\b.*\bmodel\b.*\bservice info not found\b"
    r"|\bmodel\s+\[[^\]]+\]\s+service info not found\b",
    re.IGNORECASE | re.DOTALL,
)


def normalize_permission_mode(value: Any) -> str:
    """Return a CodeBuddy CLI permission mode that is allowed for CCB runs."""
    return codebuddy_permission_mode_cli_arg(value)


def _codebuddy_home() -> Path:
    raw = str(os.environ.get("CODEBUDDY_HOME") or "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".codebuddy"


def _find_session_jsonl(session_id: str) -> Path | None:
    sid = str(session_id or "").strip()
    if not sid:
        return None
    projects_root = _codebuddy_home() / "projects"
    if not projects_root.exists():
        return None
    try:
        matches = sorted(
            projects_root.glob(f"*/{sid}.jsonl"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    except Exception:
        return None
    return matches[0] if matches else None


def _snapshot_session_jsonl(session_id: str) -> tuple[Path | None, int]:
    path = _find_session_jsonl(session_id)
    if not path:
        return None, 0
    try:
        return path, max(0, int(path.stat().st_size))
    except Exception:
        return path, 0


def _load_jsonl_value(line: str) -> list[Any]:
    text = str(line or "").strip()
    if not text:
        return []
    try:
        obj = json.loads(text)
    except Exception:
        return []
    if isinstance(obj, list):
        return list(obj)
    return [obj]


def _load_new_session_jsonl_events(
    session_id: str,
    *,
    before_path: Path | None,
    before_size: int,
    min_timestamp_s: float,
) -> list[Any]:
    path = _find_session_jsonl(session_id)
    if not path:
        return []
    start_offset = 0
    if before_path and path == before_path:
        try:
            current_size = int(path.stat().st_size)
            if current_size >= before_size:
                start_offset = max(0, before_size)
        except Exception:
            start_offset = 0

    out: list[Any] = []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            if start_offset > 0:
                f.seek(start_offset)
            for line in f:
                out.extend(_load_jsonl_value(line))
    except Exception:
        return []

    # If no reliable append offset exists, timestamp filtering in the normalizer
    # prevents old session history from being projected into this run.
    _ = min_timestamp_s
    return out


def _load_json_output(stdout: str) -> Any:
    text = str(stdout or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        pass

    # Be tolerant of update notices or banners around the JSON payload.
    candidates: list[str] = []
    if "[" in text and "]" in text:
        candidates.append(text[text.find("[") : text.rfind("]") + 1])
    if "{" in text and "}" in text:
        candidates.append(text[text.find("{") : text.rfind("}") + 1])
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except Exception:
            continue
    return None


def _write_output(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(text or "").strip() + ("\n" if str(text or "").strip() else ""), encoding="utf-8")


def _empty_output_error_exit_code(stderr: str, returncode: int) -> int:
    err = str(stderr or "").strip()
    if not err:
        return int(returncode or 0)
    if _UNSUPPORTED_MODEL_RE.search(err):
        return _CONFIG_EXIT_CODE
    if _PROVIDER_TRANSIENT_RE.search(err):
        return _TEMPFAIL_EXIT_CODE
    return int(returncode or 0) or _GENERAL_ERROR_EXIT_CODE


def _safe_plain_stdout(stdout: str, parsed_output: Any) -> str:
    text = str(stdout or "").strip()
    if not text or parsed_output is not None:
        return ""
    if is_unsafe_raw_output_text(text):
        return ""
    return text


def build_codebuddy_command(args: argparse.Namespace) -> list[str]:
    cmd = [
        resolve_cli_executable("codebuddy"),
        "-p",
        "--output-format",
        "json",
    ]
    if args.mode == "resume":
        cmd.extend(["--resume", str(args.session_id or "").strip()])
    elif str(args.session_id or "").strip():
        cmd.extend(["--session-id", str(args.session_id).strip()])

    model = str(args.model or "").strip()
    if model:
        cmd.extend(["--model", model])

    permission_mode = normalize_permission_mode(
        args.permission_mode or os.environ.get("TASK_DASHBOARD_CODEBUDDY_PERMISSION_MODE")
    )
    if permission_mode:
        cmd.extend(["--permission-mode", permission_mode])

    max_turns = str(args.max_turns or "").strip()
    if max_turns:
        cmd.extend(["--max-turns", max_turns])

    tools = str(args.tools or "").strip()
    if tools:
        cmd.extend(["--tools", tools])

    cmd.append(str(args.message or "Please reply with: OK"))
    return cmd


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run CodeBuddy and write CCB final output.")
    parser.add_argument("mode", choices=["create", "resume"])
    parser.add_argument("--session-id", default="")
    parser.add_argument("--message", required=True)
    parser.add_argument("--output-path", required=True)
    parser.add_argument("--model", default="")
    parser.add_argument("--permission-mode", default="")
    parser.add_argument("--max-turns", default="")
    parser.add_argument("--tools", default="")
    ns = parser.parse_args(argv)

    output_path = Path(ns.output_path).expanduser()
    if ns.mode == "resume" and not str(ns.session_id or "").strip():
        print("missing CodeBuddy session id for resume", file=sys.stderr)
        return 2

    start_ts = time.time()
    before_jsonl_path, before_jsonl_size = _snapshot_session_jsonl(ns.session_id)
    cmd = build_codebuddy_command(ns)
    proc = subprocess.run(cmd, capture_output=True, text=True)
    data = _load_json_output(proc.stdout)
    new_jsonl_events = _load_new_session_jsonl_events(
        ns.session_id,
        before_path=before_jsonl_path,
        before_size=before_jsonl_size,
        min_timestamp_s=start_ts - 5.0,
    )
    final_text = extract_final_text(data, min_timestamp_s=start_ts - 5.0)
    if not final_text:
        final_text = extract_final_text(new_jsonl_events, min_timestamp_s=start_ts - 5.0)
    if not final_text:
        final_text = _safe_plain_stdout(proc.stdout, data)
    event_items = data if isinstance(data, list) else ([data] if data is not None else [])
    event_items.extend(new_jsonl_events)
    for event in normalize_process_events(event_items, final_text=final_text, min_timestamp_s=start_ts - 5.0):
        print(json.dumps(event, ensure_ascii=False, separators=(",", ":")), flush=True)
    if final_text:
        _write_output(output_path, final_text)
        print(final_text)

    if proc.stderr:
        print(proc.stderr, file=sys.stderr, end="" if proc.stderr.endswith("\n") else "\n")
    if not final_text:
        safe_err = str(proc.stderr or "").strip()
        if not str(proc.stderr or "").strip():
            safe_err = "CodeBuddy did not return a public assistant result; raw stdout was suppressed."
            print(safe_err, file=sys.stderr)
        return _empty_output_error_exit_code(safe_err, int(proc.returncode or 0))
    return int(proc.returncode or 0)


if __name__ == "__main__":
    raise SystemExit(main())
