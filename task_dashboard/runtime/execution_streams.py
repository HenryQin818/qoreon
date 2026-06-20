# -*- coding: utf-8 -*-

from __future__ import annotations

from typing import Any, Callable

from task_dashboard.adapters.codebuddy_output import sanitize_process_event_text


def _event_text(value: Any, max_len: int = 120) -> str:
    text = str(value or "").replace("\r\n", "\n").strip()
    if len(text) > max_len:
        return text[: max_len - 1] + "…"
    return text


def _event_name_from_item(item: dict[str, Any]) -> str:
    for key in ("name", "tool_name", "toolName", "command", "cmd"):
        text = _event_text(item.get(key), max_len=160)
        if text:
            return text
    return _event_text(item.get("type"), max_len=80)


def extract_process_event_from_parsed(parsed: dict[str, Any]) -> dict[str, str]:
    if not isinstance(parsed, dict):
        return {}
    message_type = str(parsed.get("type") or "").strip()
    item = parsed.get("item") if isinstance(parsed.get("item"), dict) else {}
    item_type = str((item or {}).get("type") or parsed.get("item_type") or "").strip()
    if not item_type or item_type == "agent_message":
        return {}

    is_started = message_type.endswith(".started") or message_type in {"tool_call.started", "command.started"}
    is_completed = message_type.endswith(".completed") or message_type in {"tool_call.completed", "command.completed"}
    if not (is_started or is_completed):
        return {}

    name = _event_text(parsed.get("title"), max_len=200) or _event_name_from_item(item)
    explicit_text = _event_text(parsed.get("text"), max_len=3000)
    explicit_event_type = _event_text(parsed.get("event_type"), max_len=80)
    low_type = item_type.lower()
    if low_type == "command_execution" or "command" in low_type:
        event_type = "command_started" if is_started else "command_completed"
        prefix = "执行命令" if is_started else "命令完成"
    elif "tool" in low_type or "mcp" in low_type or low_type in {"function_call", "function"}:
        event_type = "tool_started" if is_started else "tool_completed"
        prefix = "调用工具" if is_started else "工具完成"
    else:
        event_type = "runtime_event_started" if is_started else "runtime_event_completed"
        prefix = "运行事件" if is_started else "运行事件完成"
    out = {
        "event_type": explicit_event_type or event_type,
        "item_type": item_type,
        "title": name,
        "text": explicit_text or (f"{prefix}: {name}" if name else prefix),
    }
    at = _event_text(parsed.get("at"), max_len=80)
    if at:
        out["at"] = at
    for optional_key in ("path", "source", "raw_ref", "call_id"):
        optional_value = _event_text(parsed.get(optional_key), max_len=1000)
        if optional_value:
            out[optional_key] = optional_value
    return out


def append_process_event(
    process_state: dict[str, Any],
    meta: dict[str, Any],
    event: dict[str, Any],
    *,
    safe_text: Callable[[Any, int], str],
    now_iso: Callable[[], str],
) -> bool:
    if not isinstance(event, dict):
        return False
    event_type = safe_text(event.get("event_type"), 80).strip()
    item_type = safe_text(event.get("item_type"), 120).strip()
    title = safe_text(event.get("title"), 200).strip()
    text = safe_text(
        sanitize_process_event_text(
            event.get("text"),
            title=title,
            item_type=item_type,
            event_type=event_type,
        ),
        3000,
    ).strip()
    if not text:
        return False
    at = str(event.get("at") or now_iso() or "").strip()
    key = "|".join([event_type, item_type, title, text])
    if key and str(process_state.get("last_event_key") or "") == key:
        return False
    process_state["last_event_key"] = key

    event_row = {
        "event_type": event_type,
        "item_type": item_type,
        "title": title,
        "text": text,
        "at": at,
    }
    for optional_key in ("path", "source", "raw_ref", "call_id"):
        optional_value = safe_text(event.get(optional_key), 1000).strip()
        if optional_value:
            event_row[optional_key] = optional_value

    events = process_state.get("events")
    if not isinstance(events, list):
        events = []
    events.append(dict(event_row))
    if len(events) > 240:
        events = events[-240:]
    process_state["events"] = events
    process_state["event_count"] = int(process_state.get("event_count") or 0) + 1
    process_state["event_latest"] = text

    rows = process_state.get("rows")
    if not isinstance(rows, list):
        rows = []
    rows.append(dict(event_row))
    if len(rows) > 240:
        rows = rows[-240:]
    process_state["rows"] = rows
    meta["process_events"] = [dict(row) for row in events]
    meta["processEvents"] = [dict(row) for row in events]
    meta["processRows"] = [dict(row) for row in rows]
    if not str(meta.get("lastPreview") or "").strip():
        meta["partialPreview"] = text
    return True


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
        event = extract_process_event_from_parsed(parsed)
        if event:
            append_process_event(
                process_state,
                meta,
                event,
                safe_text=safe_text,
                now_iso=now_iso,
            )
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
