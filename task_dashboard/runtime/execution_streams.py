# -*- coding: utf-8 -*-

from __future__ import annotations

from typing import Any, Callable


def capture_auth_error(
    raw: str,
    *,
    live_auth_error: dict[str, str],
    is_auth_error: Callable[[str], bool],
    safe_text: Callable[[Any, int], str],
) -> None:
    txt = str(raw or "").strip()
    if not txt or live_auth_error.get("text"):
        return
    if is_auth_error(txt):
        live_auth_error["text"] = safe_text(txt, 1200)


def capture_agent_text(
    raw_line: str,
    *,
    adapter_cls: Any,
    process_state: dict[str, Any],
    meta: dict[str, Any],
    parse_adapter_output_line: Callable[[Any, str], Any],
    extract_agent_message_text_from_parsed: Callable[[Any], str],
    safe_text: Callable[[Any, int], str],
    now_iso: Callable[[], str],
) -> None:
    payload = str(raw_line or "").strip()
    if not payload:
        return
    parsed = parse_adapter_output_line(adapter_cls, payload)
    if not parsed:
        return
    txt = extract_agent_message_text_from_parsed(parsed)
    if not txt:
        return
    prev_txt = str(process_state.get("last_text") or "")
    if prev_txt and prev_txt == txt:
        return
    process_state["last_text"] = txt
    process_state["count"] = int(process_state.get("count") or 0) + 1
    process_state["latest"] = safe_text(txt, 300)
    rows = process_state.get("rows")
    if not isinstance(rows, list):
        rows = []
    rows.append(
        {
            "text": safe_text(txt, 3000),
            "at": str(now_iso() or "").strip(),
        }
    )
    if len(rows) > 240:
        rows = rows[-240:]
    process_state["rows"] = rows
    meta["agentMessagesCount"] = int(process_state["count"])
    meta["processRows"] = [dict(row) for row in rows]
    if not str(meta.get("lastPreview") or "").strip():
        meta["partialPreview"] = str(process_state["latest"] or "")


def pump_process_stream(
    stream: Any,
    *,
    label: str,
    lock: Any,
    logf: Any,
    err_buf: list[str],
    capture_auth_error_cb: Callable[[str], None],
    capture_agent_text_cb: Callable[[str], None],
) -> None:
    try:
        for line in iter(stream.readline, ""):
            with lock:
                logf.write(f"[{label}] {line}")
                logf.flush()
                if label == "stderr":
                    err_buf.append(line)
                    if len(err_buf) > 120:
                        del err_buf[:40]
                    capture_auth_error_cb(line)
                elif label == "stdout":
                    capture_agent_text_cb(line)
    finally:
        try:
            stream.close()
        except Exception:
            pass


def write_retry_process_output(
    retry: Any,
    *,
    lock: Any,
    logf: Any,
    capture_agent_text_cb: Callable[[str], None],
) -> None:
    stdout_text = str(getattr(retry, "stdout", "") or "")
    stderr_text = str(getattr(retry, "stderr", "") or "")
    if stdout_text:
        with lock:
            for raw_line in stdout_text.splitlines(keepends=True):
                line = str(raw_line)
                if line.endswith("\n"):
                    logf.write(f"[stdout] {line}")
                else:
                    logf.write(f"[stdout] {line}\n")
            for raw_line in stdout_text.splitlines():
                capture_agent_text_cb(raw_line)
    if stderr_text:
        with lock:
            for raw_line in stderr_text.splitlines(keepends=True):
                line = str(raw_line)
                if line.endswith("\n"):
                    logf.write(f"[stderr] {line}")
                else:
                    logf.write(f"[stderr] {line}\n")
