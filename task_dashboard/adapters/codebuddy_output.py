#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""CodeBuddy output normalization helpers."""

from __future__ import annotations

from datetime import datetime
import json
import re
from typing import Any


_CCB_PROCESS_EVENT_TYPES = {
    "tool_call.started",
    "tool_call.completed",
    "runtime_event.completed",
}
_RAW_OUTPUT_SENSITIVE_NEEDLES = (
    "system-reminder",
    "data-role=\"memory\"",
    "<memory>",
    "\"role\":\"user\"",
    "\"role\": \"user\"",
    "\"input_text\"",
    "\"rawContent\"",
    "\"rawContent\":",
    "\"type\":\"reasoning\"",
    "\"type\": \"reasoning\"",
    "file-history-snapshot",
)


def _trim_text(value: Any, max_len: int = 240) -> str:
    text = str(value or "").replace("\r\n", "\n").strip()
    text = " ".join(part for part in text.split())
    if len(text) > max_len:
        return text[: max_len - 1] + "…"
    return text


def _extract_text_from_content(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                txt = str(item.get("text") or "").strip()
                if txt and str(item.get("type") or "") in {"output_text", "text"}:
                    parts.append(txt)
        return "\n".join(parts).strip()
    return ""


def _timestamp_to_iso(value: Any) -> str:
    raw = _timestamp_to_seconds(value)
    if raw <= 0:
        return ""
    try:
        return datetime.fromtimestamp(raw).astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")
    except Exception:
        return ""


def _timestamp_to_seconds(value: Any) -> float:
    try:
        raw = float(value)
    except Exception:
        return 0.0
    if raw > 10_000_000_000:
        raw = raw / 1000.0
    return raw


def _json_snippet(value: Any, max_len: int = 180) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        except Exception:
            text = str(value)
    return _trim_text(text, max_len=max_len)


def _looks_like_structured_payload(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    if text[0] in {"{", "["}:
        return True
    compact = "".join(text.split()).lower()
    return any(marker in compact for marker in ('"questions":', '"prompt":', '"rawcontent":', '"type":"reasoning"'))


def _collection_count(value: Any) -> int:
    if isinstance(value, list):
        return len(value)
    if value:
        return 1
    return 0


def _argument_summary_from_parsed(tool_name: str, parsed: Any) -> str:
    tool = str(tool_name or "").strip().lower()
    if isinstance(parsed, list):
        return f"列表参数 {len(parsed)} 项"
    if not isinstance(parsed, dict):
        return ""

    questions = parsed.get("questions")
    if questions is not None:
        count = _collection_count(questions)
        prefix = "向用户提问 / " if "ask" in tool or "question" in tool or "user" in tool else ""
        return f"{prefix}问题 {count} 项"

    for key in ("description", "pattern", "query", "file_path", "path"):
        text = _trim_text(parsed.get(key), max_len=120)
        if text and not is_unsafe_raw_output_text(text) and not _looks_like_structured_payload(text):
            return f"{key}: {text}"

    sensitive_keys = {
        "prompt",
        "system_prompt",
        "rawContent",
        "raw_content",
        "reasoning",
        "messages",
        "input_text",
    }
    if any(key in parsed for key in sensitive_keys):
        return "参数已隐藏"

    if any(key in parsed for key in ("command", "cmd")):
        return "命令参数已隐藏"

    return f"参数 {len(parsed)} 项" if parsed else ""


def sanitize_process_event_text(
    value: Any,
    *,
    title: str = "",
    item_type: str = "",
    event_type: str = "",
) -> str:
    text = _trim_text(value, max_len=3000)
    if not text:
        return ""
    if is_unsafe_raw_output_text(text):
        return "内容已隐藏"

    lower = text.lower()
    if "rawcontent" in lower or "raw_content" in lower or '"type":"reasoning"' in lower or '"type": "reasoning"' in lower:
        return "内容已隐藏"

    json_match = re.search(r"[\{\[]", text)
    prompt_like = re.search(r"\b(prompt|rawcontent|raw_content|reasoning)\b\s*[:=]", text, flags=re.IGNORECASE)
    if not json_match and not prompt_like:
        return text

    prefix = text[: json_match.start()].strip() if json_match else text[: prompt_like.start()].strip()
    raw_payload = text[json_match.start() :].strip() if json_match else ""
    parsed: Any = None
    if raw_payload:
        try:
            parsed = json.loads(raw_payload)
        except Exception:
            parsed = None

    summary = _argument_summary_from_parsed(title, parsed)
    if not summary:
        if str(item_type or "").strip() == "function_call" or str(event_type or "").strip() == "tool_started":
            summary = "参数已隐藏"
        else:
            summary = "内容已隐藏"
    return (f"{prefix} {summary}" if prefix else summary).strip()


def _extract_arguments_display(item: dict[str, Any]) -> str:
    provider_data = item.get("providerData") if isinstance(item.get("providerData"), dict) else {}
    display = _trim_text(provider_data.get("argumentsDisplayText"), max_len=180)
    if display and not is_unsafe_raw_output_text(display) and not _looks_like_structured_payload(display):
        return display

    raw_args = item.get("arguments")
    tool_name = _trim_text(item.get("name"), max_len=120)
    parsed: Any = None
    if isinstance(raw_args, str) and raw_args.strip():
        try:
            parsed = json.loads(raw_args)
        except Exception:
            text = _trim_text(raw_args, max_len=120)
            if not text or is_unsafe_raw_output_text(text) or _looks_like_structured_payload(text):
                return "参数已隐藏"
            return text
    elif isinstance(raw_args, dict):
        parsed = raw_args
    elif isinstance(raw_args, list):
        parsed = raw_args

    return _argument_summary_from_parsed(tool_name, parsed)


def _extract_result_summary(item: dict[str, Any]) -> str:
    provider_data = item.get("providerData") if isinstance(item.get("providerData"), dict) else {}
    tool_result = provider_data.get("toolResult") if isinstance(provider_data.get("toolResult"), dict) else {}
    title = _trim_text(tool_result.get("title"), max_len=180)
    if title:
        return title

    output = item.get("output")
    if isinstance(output, dict):
        text = _trim_text(output.get("text"), max_len=180)
        if text and not is_unsafe_raw_output_text(text) and not _looks_like_structured_payload(text):
            return text
        return f"结果 {len(output)} 项" if output else ""
    if isinstance(output, list):
        return f"结果 {len(output)} 项"
    text = _trim_text(output, max_len=180)
    if text and not is_unsafe_raw_output_text(text) and not _looks_like_structured_payload(text):
        return text
    return "结果已隐藏" if text else ""


def _same_text(left: str, right: str) -> bool:
    return _trim_text(left, max_len=4000) == _trim_text(right, max_len=4000)


def is_unsafe_raw_output_text(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    compact = "".join(text.split())
    compact_lower = compact.lower()
    if any(needle.lower().replace(" ", "") in compact_lower for needle in _RAW_OUTPUT_SENSITIVE_NEEDLES):
        return True
    if text.startswith(("[", "{")):
        json_markers = ("\"role\"", "\"content\"", "\"type\"", "\"parentId\"", "\"timestamp\"")
        if any(marker.lower() in compact_lower for marker in json_markers):
            return True
    return False


def _event_ref(item: dict[str, Any]) -> str:
    for key in ("callId", "id"):
        text = _trim_text(item.get(key), max_len=120)
        if text:
            return text
    return ""


def is_ccb_process_event(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    event_type = str(value.get("type") or "").strip()
    if event_type not in _CCB_PROCESS_EVENT_TYPES:
        return False
    return str(value.get("source") or "").strip() == "codebuddy"


def normalize_process_event(item: Any, *, final_text: str = "", min_timestamp_s: float = 0.0) -> dict[str, Any]:
    """Map a CodeBuddy JSON event into one CCB process event row."""
    if not isinstance(item, dict):
        return {}
    if is_ccb_process_event(item):
        return dict(item)

    raw_type = str(item.get("type") or "").strip()
    item_ts = _timestamp_to_seconds(item.get("timestamp"))
    if min_timestamp_s > 0 and item_ts > 0 and item_ts < min_timestamp_s:
        return {}
    if raw_type == "function_call":
        name = _trim_text(item.get("name"), max_len=120) or "工具"
        detail = _extract_arguments_display(item)
        text = f"调用工具: {name}" + (f" {detail}" if detail else "")
        out = {
            "type": "tool_call.started",
            "event_type": "tool_started",
            "item_type": "function_call",
            "title": name,
            "text": text,
            "source": "codebuddy",
        }
    elif raw_type == "function_call_result":
        name = _trim_text(item.get("name"), max_len=120) or "工具"
        summary = _extract_result_summary(item)
        status = _trim_text(item.get("status"), max_len=60)
        suffix = summary or status
        text = f"工具完成: {name}" + (f" {suffix}" if suffix else "")
        out = {
            "type": "tool_call.completed",
            "event_type": "tool_completed",
            "item_type": "function_call_result",
            "title": name,
            "text": text,
            "source": "codebuddy",
        }
    elif raw_type == "message" and str(item.get("role") or "") == "assistant":
        text = _extract_text_from_content(item.get("content"))
        if not text or (final_text and _same_text(text, final_text)):
            return {}
        out = {
            "type": "runtime_event.completed",
            "event_type": "assistant_progress",
            "item_type": "assistant_progress",
            "title": "助手进展",
            "text": f"助手进展: {_trim_text(text, max_len=220)}",
            "source": "codebuddy",
        }
    else:
        return {}

    at = _timestamp_to_iso(item.get("timestamp"))
    if at:
        out["at"] = at
    raw_ref = _event_ref(item)
    if raw_ref:
        out["raw_ref"] = raw_ref
    call_id = _trim_text(item.get("callId"), max_len=120)
    if call_id:
        out["call_id"] = call_id
    return out


def normalize_process_events(
    value: Any,
    *,
    final_text: str = "",
    max_items: int = 120,
    min_timestamp_s: float = 0.0,
) -> list[dict[str, Any]]:
    items = value if isinstance(value, list) else [value]
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        event = normalize_process_event(item, final_text=final_text, min_timestamp_s=min_timestamp_s)
        if not event:
            continue
        key = "|".join(
            [
                str(event.get("type") or ""),
                str(event.get("call_id") or event.get("raw_ref") or ""),
                str(event.get("text") or ""),
            ]
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(event)
    if len(out) > max_items:
        return out[-max_items:]
    return out


def extract_final_text(value: Any, *, min_timestamp_s: float = 0.0) -> str:
    """Extract the user-facing final answer from CodeBuddy JSON output."""
    items = value if isinstance(value, list) else [value]

    for item in reversed(items):
        if not isinstance(item, dict):
            continue
        item_ts = _timestamp_to_seconds(item.get("timestamp"))
        if min_timestamp_s > 0 and item_ts > 0 and item_ts < min_timestamp_s:
            continue
        if str(item.get("type") or "") == "result":
            text = str(item.get("result") or "").strip()
            if text and not is_unsafe_raw_output_text(text):
                return text

    for item in reversed(items):
        if not isinstance(item, dict):
            continue
        item_ts = _timestamp_to_seconds(item.get("timestamp"))
        if min_timestamp_s > 0 and item_ts > 0 and item_ts < min_timestamp_s:
            continue
        if str(item.get("type") or "") != "message":
            continue
        if str(item.get("role") or "") != "assistant":
            continue
        text = _extract_text_from_content(item.get("content"))
        if text and not is_unsafe_raw_output_text(text):
            return text

    return ""
