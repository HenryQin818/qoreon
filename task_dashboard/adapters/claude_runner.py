#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Thin Claude Code subprocess wrapper for CCB runs.

Claude stream-json contains provider-specific system/user/tool records. CCB
only persists public assistant text in `.last.txt` and emits normalized process
events for the run detail drawer.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

from task_dashboard.adapters.base import resolve_cli_executable
from task_dashboard.adapters.codebuddy_output import (
    extract_final_text,
    is_unsafe_raw_output_text,
    normalize_process_events,
)
from task_dashboard.claude_models import normalize_claude_model
from task_dashboard.claude_permissions import normalize_claude_permission_mode


_GENERAL_ERROR_EXIT_CODE = 1
def normalize_permission_mode(value: Any) -> str:
    return normalize_claude_permission_mode(value)


def build_claude_command(args: argparse.Namespace) -> list[str]:
    cmd = [
        resolve_cli_executable("claude"),
        "-p",
        "--output-format",
        "stream-json",
        "--verbose",
    ]
    session_id = str(args.resume or args.session_id or "").strip()
    if args.mode == "resume":
        cmd.extend(["--resume", session_id])
    elif session_id:
        cmd.extend(["--session-id", session_id])

    model = normalize_claude_model(args.model)
    cmd.extend(["--model", model])

    permission_mode = normalize_permission_mode(
        args.permission_mode or os.environ.get("TASK_DASHBOARD_CLAUDE_PERMISSION_MODE")
    )
    if permission_mode == "bypassPermissions":
        cmd.append("--dangerously-skip-permissions")
    elif permission_mode:
        cmd.extend(["--permission-mode", permission_mode])

    cmd.append(str(args.message or "Please reply with: OK"))
    return cmd


def _load_stream_json_output(stdout: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for line in str(stdout or "").splitlines():
        text = line.strip()
        if not text or not text.startswith("{"):
            continue
        try:
            obj = json.loads(text)
        except Exception:
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out


def _load_stream_json_line(line: str) -> dict[str, Any] | None:
    text = str(line or "").strip()
    if not text or not text.startswith("{"):
        return None
    try:
        obj = json.loads(text)
    except Exception:
        return None
    return obj if isinstance(obj, dict) else None


def _tool_result_text(item: dict[str, Any]) -> str:
    content = item.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict):
                text = str(part.get("text") or part.get("content") or "").strip()
                if text:
                    parts.append(text)
            elif isinstance(part, str) and part.strip():
                parts.append(part.strip())
        return "\n".join(parts).strip()
    if content is not None:
        return str(content).strip()
    return ""


class ClaudeStreamTransformer:
    """Stateful Claude stream-json transformer for per-line emission."""

    def __init__(self) -> None:
        self.tool_names: dict[str, str] = {}

    def transform_one(self, item: dict[str, Any]) -> list[dict[str, Any]]:
        if not isinstance(item, dict):
            return []
        out: list[dict[str, Any]] = []
        raw_type = str(item.get("type") or "").strip()
        timestamp = item.get("timestamp")
        if raw_type == "result":
            result = str(item.get("result") or "").strip()
            if result and not is_unsafe_raw_output_text(result):
                event = {
                    "type": "result",
                    "subtype": item.get("subtype") or "success",
                    "is_error": bool(item.get("is_error")),
                    "result": result,
                }
                if timestamp:
                    event["timestamp"] = timestamp
                out.append(event)
            return out

        message = item.get("message") if isinstance(item.get("message"), dict) else item
        role = str(message.get("role") or "").strip()
        content = message.get("content")
        if raw_type == "assistant" or role == "assistant":
            _append_assistant_content(out, content, timestamp=timestamp, tool_names=self.tool_names)
        elif raw_type == "user" or role == "user":
            _append_tool_results(out, content, timestamp=timestamp, tool_names=self.tool_names)
        return out


def _append_assistant_content(
    out: list[dict[str, Any]],
    content: Any,
    *,
    timestamp: Any = None,
    tool_names: dict[str, str],
) -> None:
    if not isinstance(content, list):
        return
    text_parts: list[str] = []

    def flush_text() -> None:
        if not text_parts:
            return
        event = {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "\n".join(text_parts).strip()}],
        }
        if timestamp:
            event["timestamp"] = timestamp
        out.append(event)
        text_parts.clear()

    for item in content:
        if not isinstance(item, dict):
            continue
        item_type = str(item.get("type") or "").strip()
        if item_type == "text":
            text = str(item.get("text") or "").strip()
            if text and not is_unsafe_raw_output_text(text):
                text_parts.append(text)
        elif item_type == "tool_use":
            flush_text()
            call_id = str(item.get("id") or "").strip()
            name = str(item.get("name") or "").strip() or "工具"
            if call_id:
                tool_names[call_id] = name
            args_value = item.get("input")
            try:
                arguments = json.dumps(args_value, ensure_ascii=False) if not isinstance(args_value, str) else args_value
            except Exception:
                arguments = str(args_value or "")
            event = {
                "type": "function_call",
                "callId": call_id,
                "name": name,
                "arguments": arguments,
            }
            if timestamp:
                event["timestamp"] = timestamp
            out.append(event)
    flush_text()


def _append_tool_results(
    out: list[dict[str, Any]],
    content: Any,
    *,
    timestamp: Any = None,
    tool_names: dict[str, str],
) -> None:
    if not isinstance(content, list):
        return
    for item in content:
        if not isinstance(item, dict) or str(item.get("type") or "").strip() != "tool_result":
            continue
        call_id = str(item.get("tool_use_id") or item.get("id") or "").strip()
        name = tool_names.get(call_id) or "工具"
        text = _tool_result_text(item)
        event = {
            "type": "function_call_result",
            "callId": call_id,
            "name": name,
            "status": "error" if item.get("is_error") else "completed",
            "output": {"type": "text", "text": text},
        }
        if timestamp:
            event["timestamp"] = timestamp
        out.append(event)


def transform_claude_stream_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert Claude stream-json records to the normalizer's event shape."""
    out: list[dict[str, Any]] = []
    transformer = ClaudeStreamTransformer()
    for item in events:
        out.extend(transformer.transform_one(item))
    return out


def _write_output(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    clean = str(text or "").strip()
    path.write_text(clean + ("\n" if clean else ""), encoding="utf-8")


def _emit_process_events(events: list[dict[str, Any]], *, final_text: str) -> None:
    for event in normalize_process_events(events, final_text=final_text):
        safe_event = dict(event)
        safe_event["source"] = "claude"
        print(json.dumps(safe_event, ensure_ascii=False, separators=(",", ":")), flush=True)


def _drain_stderr(stream: Any, sink: list[str]) -> None:
    try:
        for line in iter(stream.readline, ""):
            sink.append(str(line))
    finally:
        try:
            stream.close()
        except Exception:
            pass


def _run_claude_streaming(cmd: list[str]) -> tuple[int, list[dict[str, Any]], str]:
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    stderr_lines: list[str] = []
    stderr_thread: threading.Thread | None = None
    if proc.stderr is not None:
        stderr_thread = threading.Thread(target=_drain_stderr, args=(proc.stderr, stderr_lines), daemon=True)
        stderr_thread.start()

    transformer = ClaudeStreamTransformer()
    normalized_input: list[dict[str, Any]] = []
    try:
        if proc.stdout is not None:
            for line in iter(proc.stdout.readline, ""):
                item = _load_stream_json_line(line)
                if not item:
                    continue
                transformed = transformer.transform_one(item)
                if not transformed:
                    continue
                normalized_input.extend(transformed)
                _emit_process_events(transformed, final_text="")
    finally:
        try:
            if proc.stdout is not None:
                proc.stdout.close()
        except Exception:
            pass

    returncode = int(proc.wait() or 0)
    if stderr_thread is not None:
        stderr_thread.join(timeout=1.5)
    return returncode, normalized_input, "".join(stderr_lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Claude Code and write CCB final output.")
    parser.add_argument("mode", choices=["create", "resume"])
    parser.add_argument("--resume", default="", help="Claude session id for resume mode.")
    parser.add_argument("--session-id", default="", help="Optional Claude session id for create mode.")
    parser.add_argument("--message", required=True)
    parser.add_argument("--output-path", required=True)
    parser.add_argument("--model", default="")
    parser.add_argument("--permission-mode", default="")
    ns = parser.parse_args(argv)

    if ns.mode == "resume" and not str(ns.resume or ns.session_id or "").strip():
        print("missing Claude session id for resume", file=sys.stderr)
        return 2

    output_path = Path(ns.output_path).expanduser()
    cmd = build_claude_command(ns)
    returncode, normalized_input, stderr_text = _run_claude_streaming(cmd)
    final_text = extract_final_text(normalized_input)

    if final_text:
        _write_output(output_path, final_text)
        print(final_text)

    if stderr_text:
        print(stderr_text, file=sys.stderr, end="" if stderr_text.endswith("\n") else "\n")

    if not final_text:
        if not str(stderr_text or "").strip():
            print("Claude did not return a public result event; raw stream-json stdout was suppressed.", file=sys.stderr)
        return returncode or _GENERAL_ERROR_EXIT_CODE
    return returncode


if __name__ == "__main__":
    raise SystemExit(main())
