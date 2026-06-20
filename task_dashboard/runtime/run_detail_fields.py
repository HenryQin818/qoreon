# -*- coding: utf-8 -*-

from __future__ import annotations

from collections import deque
import json
from pathlib import Path
import re
import shutil
from typing import Any, Optional

from task_dashboard.adapters import CodexAdapter, get_adapter
from task_dashboard.adapters.codebuddy_output import extract_final_text as extract_codebuddy_final_text
from task_dashboard.helpers import parse_iso_ts
from task_dashboard.runtime.execution_streams import extract_process_event_from_parsed


_TERMINAL_TEXT_CLIS = {"claude", "opencode", "gemini", "codebuddy"}
CODEBUDDY_UNSAFE_FINAL_PLACEHOLDER = "CodeBuddy 最终正文包含原始事件内容，已隐藏；请查看过程摘要或重新发起结果收口。"
_CODEBUDDY_UNSAFE_FINAL_TEXT_NEEDLES = (
    "<system-reminder",
    'data-role="memory"',
    "data-role='memory'",
    "<memory>",
    '"role": "user"',
    '"role":"user"',
    '"role": "system"',
    '"role":"system"',
    '"type": "input_text"',
    '"type":"input_text"',
    "rawcontent",
    "raw_content",
    "providerdata",
)
_CODEBUDDY_UNSAFE_FINAL_KEYS = {
    "rawcontent",
    "raw_content",
    "providerdata",
    "provider_data",
    "reasoning",
    "reasoningcontent",
    "reasoning_content",
}
_CODEBUDDY_EVENT_TYPES = {
    "function_call",
    "function_call_result",
    "tool_call.started",
    "tool_call.completed",
    "runtime_event.completed",
}
_IMAGE_FILE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
_HTML_FILE_EXTS = {".html", ".htm"}
_MEDIA_FILE_EXTS = _IMAGE_FILE_EXTS | _HTML_FILE_EXTS
_CODEX_GENERATED_MEDIA_SOURCE = "codex_imagegen"
_LOCAL_IMAGEGEN_FALLBACK_SOURCE = "local_imagegen_fallback"
_GENERATED_MEDIA_SOURCES = {
    _CODEX_GENERATED_MEDIA_SOURCE,
    _LOCAL_IMAGEGEN_FALLBACK_SOURCE,
}
_MEDIA_RUN_NEEDLES = (
    "imagegen",
    "image_gen",
    "image gen",
    "generated_images",
    "generated media",
    "output/imagegen",
)


def _safe_text(s: Any, max_len: int) -> str:
    s2 = "" if s is None else str(s)
    if len(s2) > max_len:
        return s2[: max_len - 1] + "…"
    return s2


def _codebuddy_text_has_unsafe_final_projection(text: str) -> bool:
    low = str(text or "").lower()
    return any(needle in low for needle in _CODEBUDDY_UNSAFE_FINAL_TEXT_NEEDLES)


def _codebuddy_parsed_has_unsafe_final_projection(value: Any, depth: int = 0) -> bool:
    if depth > 24:
        return False
    if isinstance(value, dict):
        lowered_keys = {str(key or "").strip().lower() for key in value.keys()}
        if lowered_keys & _CODEBUDDY_UNSAFE_FINAL_KEYS:
            return True
        role = str(value.get("role") or "").strip().lower()
        if role in {"user", "system", "developer"}:
            return True
        item_type = str(value.get("type") or value.get("item_type") or "").strip().lower()
        if item_type in _CODEBUDDY_EVENT_TYPES:
            return True
        if item_type == "input_text":
            return True
        text_value = value.get("text")
        if isinstance(text_value, str) and _codebuddy_text_has_unsafe_final_projection(text_value):
            return True
        return any(_codebuddy_parsed_has_unsafe_final_projection(item, depth + 1) for item in value.values())
    if isinstance(value, list):
        return any(_codebuddy_parsed_has_unsafe_final_projection(item, depth + 1) for item in value)
    if isinstance(value, str):
        return _codebuddy_text_has_unsafe_final_projection(value)
    return False


def safe_codebuddy_visible_text(value: Any, *, placeholder: str = CODEBUDDY_UNSAFE_FINAL_PLACEHOLDER) -> str:
    """Return a user-visible CodeBuddy final message, never raw event JSON."""
    text = str(value or "").replace("\r\n", "\n").strip()
    if not text:
        return ""
    parsed: Any = None
    parsed_ok = False
    if text.startswith(("{", "[")):
        try:
            parsed = json.loads(text)
            parsed_ok = True
        except Exception:
            parsed_ok = False
    if parsed_ok:
        extracted = str(extract_codebuddy_final_text(parsed) or "").strip()
        if extracted and not _codebuddy_text_has_unsafe_final_projection(extracted):
            return extracted
        if _codebuddy_parsed_has_unsafe_final_projection(parsed):
            return placeholder
        return text
    if _codebuddy_text_has_unsafe_final_projection(text):
        return placeholder
    return text


def safe_terminal_visible_text(value: Any, *, cli_type: str = "codex") -> str:
    cli = str(cli_type or "").strip().lower()
    text = str(value or "").replace("\r\n", "\n").strip()
    if cli == "codebuddy":
        return safe_codebuddy_visible_text(text)
    return text


def _parse_adapter_output_line(adapter_cls: Any, payload: str) -> Optional[dict[str, Any]]:
    txt = str(payload or "").strip()
    if not txt:
        return None
    parse_fn = getattr(adapter_cls, "parse_output_line", None)
    if callable(parse_fn):
        try:
            parsed = parse_fn(txt)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
    if txt.startswith("{"):
        try:
            obj = json.loads(txt)
            if isinstance(obj, dict):
                return obj
        except Exception:
            return None
    return None


def fallback_log_from_meta(meta: dict[str, Any]) -> str:
    err = str(meta.get("error") or "").strip()
    if not err:
        return ""
    parts = [
        "[system] no captured process log for this run",
        f"[system] status={meta.get('status')}",
        f"[system] error={err}",
        f"[system] started_at={meta.get('startedAt')}",
        f"[system] finished_at={meta.get('finishedAt')}",
    ]
    return "\n".join(parts)


def extract_agent_message_text_from_parsed(parsed: dict[str, Any]) -> str:
    if not isinstance(parsed, dict):
        return ""
    msg_type = str(parsed.get("type") or "")
    if msg_type == "item.completed":
        item = parsed.get("item") or {}
        if str(item.get("type") or "") == "agent_message":
            return str(item.get("text") or "").strip()
        return ""
    if msg_type == "text":
        return str(parsed.get("text") or "").strip()
    if msg_type == "message":
        return str(parsed.get("content") or parsed.get("text") or "").strip()
    if msg_type == "agent_message":
        return str(parsed.get("text") or parsed.get("content") or "").strip()
    return ""


def extract_agent_messages(log_text: str, max_items: int = 12, cli_type: str = "codex") -> list[str]:
    out: list[str] = []
    if not log_text:
        return out
    adapter_cls = get_adapter(cli_type) or CodexAdapter
    for raw in log_text.splitlines():
        line = raw.strip()
        payload = ""
        if line.startswith("[stdout] "):
            payload = line[len("[stdout] ") :].strip()
        elif line.startswith("{") and '"type"' in line:
            payload = line
        if not payload:
            continue
        parsed = _parse_adapter_output_line(adapter_cls, payload)
        if not parsed:
            continue
        txt = extract_agent_message_text_from_parsed(parsed)
        if txt:
            out.append(txt)
    if len(out) > max_items:
        return out[-max_items:]
    return out


def extract_agent_messages_from_file(path: Path, max_items: int = 12, cli_type: str = "codex") -> list[str]:
    out: deque[str] = deque(maxlen=max(1, int(max_items or 1)))
    if not path.exists():
        return []
    adapter_cls = get_adapter(cli_type) or CodexAdapter
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            for raw in f:
                line = raw.strip()
                payload = ""
                if line.startswith("[stdout] "):
                    payload = line[len("[stdout] ") :].strip()
                elif line.startswith("{") and '"type"' in line:
                    payload = line
                if not payload:
                    continue
                parsed = _parse_adapter_output_line(adapter_cls, payload)
                if not parsed:
                    continue
                txt = extract_agent_message_text_from_parsed(parsed)
                if txt:
                    out.append(txt)
    except Exception:
        return []
    return list(out)


def extract_process_events_from_file(path: Path, max_items: int = 240, cli_type: str = "codex") -> list[dict[str, str]]:
    out: deque[dict[str, str]] = deque(maxlen=max(1, int(max_items or 1)))
    if not path.exists():
        return []
    adapter_cls = get_adapter(cli_type) or CodexAdapter
    last_key = ""
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            for raw in f:
                line = raw.strip()
                payload = ""
                if line.startswith("[stdout] "):
                    payload = line[len("[stdout] ") :].strip()
                elif line.startswith("{") and '"type"' in line:
                    payload = line
                if not payload:
                    continue
                parsed = _parse_adapter_output_line(adapter_cls, payload)
                if not parsed:
                    continue
                event = extract_process_event_from_parsed(parsed)
                if not event:
                    continue
                at = _safe_text(parsed.get("at"), 80).strip()
                if at:
                    event["at"] = at
                key = "|".join(
                    [
                        str(event.get("event_type") or ""),
                        str(event.get("item_type") or ""),
                        str(event.get("title") or ""),
                        str(event.get("text") or ""),
                        str(event.get("call_id") or event.get("raw_ref") or ""),
                    ]
                )
                if key and key == last_key:
                    continue
                last_key = key
                out.append(dict(event))
    except Exception:
        return []
    return list(out)


def extract_terminal_message_text(log_text: str, *, cli_type: str = "codex") -> str:
    cli = str(cli_type or "").strip().lower()
    if not log_text or cli not in _TERMINAL_TEXT_CLIS:
        return ""
    adapter_cls = get_adapter(cli) or CodexAdapter
    if cli == "gemini":
        return _extract_gemini_terminal_message_text(log_text, adapter_cls=adapter_cls)
    out: list[str] = []
    for raw in log_text.splitlines():
        line = raw.strip()
        payload = ""
        from_stdout = False
        if line.startswith("[stdout] "):
            payload = line[len("[stdout] ") :].strip()
            from_stdout = True
        elif line.startswith("{") and '"type"' in line:
            payload = line
        if not payload:
            continue
        if payload.startswith("{"):
            parsed = _parse_adapter_output_line(adapter_cls, payload)
            txt = extract_agent_message_text_from_parsed(parsed or {})
            if txt:
                out.append(txt)
            continue
        if from_stdout:
            out.append(payload)
    text = "\n".join(part for part in out if str(part or "").strip()).strip()
    if cli == "codebuddy":
        return safe_codebuddy_visible_text(text)
    return text


def _extract_gemini_terminal_message_text(log_text: str, *, adapter_cls: Any) -> str:
    stdout_lines: list[str] = []
    collecting_json = False
    for raw in str(log_text or "").splitlines():
        line = raw.strip()
        payload = ""
        if line.startswith("[stdout] "):
            payload = line[len("[stdout] ") :].strip()
        elif collecting_json and not line.startswith("[") and line:
            payload = line
        if not payload:
            continue
        if payload.startswith(("{", "[")):
            collecting_json = True
        if collecting_json or stdout_lines:
            stdout_lines.append(payload)

    stdout_text = "\n".join(stdout_lines).strip()
    if not stdout_text:
        return ""

    parsed = _parse_adapter_output_line(adapter_cls, stdout_text)
    text = extract_agent_message_text_from_parsed(parsed or {})
    if text:
        return text

    # Last-resort fallback for non-JSON stdout; avoid returning raw braces from pretty JSON.
    if stdout_text in {"{", "}", "[", "]"}:
        return ""
    try:
        json.loads(stdout_text)
        return ""
    except Exception:
        return stdout_text


def extract_terminal_message_from_file(path: Path, *, cli_type: str = "codex") -> str:
    if not path.exists():
        return ""
    try:
        return extract_terminal_message_text(path.read_text(encoding="utf-8", errors="replace"), cli_type=cli_type)
    except Exception:
        return ""


def _normalize_run_attachments(raw: Any) -> list[dict[str, Any]]:
    items = raw if isinstance(raw, list) else []
    out: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, dict):
            out.append(dict(item))
    return out


def _attachment_filename(att: dict[str, Any]) -> str:
    return str(att.get("filename") or att.get("originalName") or "").strip()


def _attachment_ext(att: dict[str, Any]) -> str:
    name = _attachment_filename(att)
    if not name:
        name = str(att.get("url") or "").split("?", 1)[0].rsplit("/", 1)[-1]
    return str(Path(name).suffix or "").strip().lower()


def _attachment_content_type(path: Path) -> str:
    suffix = str(path.suffix or "").strip().lower()
    if suffix == ".png":
        return "image/png"
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".webp":
        return "image/webp"
    if suffix == ".gif":
        return "image/gif"
    if suffix in _HTML_FILE_EXTS:
        return "text/html"
    return ""


def _is_image_attachment(att: dict[str, Any]) -> bool:
    return _attachment_ext(att) in _IMAGE_FILE_EXTS


def _is_generated_media_attachment(att: dict[str, Any]) -> bool:
    if not isinstance(att, dict):
        return False
    generated_by = str(att.get("generatedBy") or att.get("generated_by") or "").strip().lower()
    attachment_role = str(att.get("attachment_role") or att.get("attachmentRole") or "").strip().lower()
    source = str(att.get("source") or "").strip().lower()
    return (
        _attachment_ext(att) in _MEDIA_FILE_EXTS
        and (
            generated_by in _GENERATED_MEDIA_SOURCES
            or source == "generated"
            or attachment_role == "assistant"
        )
    )


def _is_generated_image_attachment(att: dict[str, Any]) -> bool:
    return _is_generated_media_attachment(att) and _is_image_attachment(att)


def _generated_media_attachments(meta: dict[str, Any]) -> list[dict[str, Any]]:
    attachments = _normalize_run_attachments(meta.get("attachments"))
    return [att for att in attachments if _is_generated_media_attachment(att)]


def _generated_image_attachments(meta: dict[str, Any]) -> list[dict[str, Any]]:
    attachments = _normalize_run_attachments(meta.get("attachments"))
    return [att for att in attachments if _is_generated_image_attachment(att)]


def synthesize_generated_media_summary(meta: dict[str, Any]) -> str:
    generated = _generated_image_attachments(meta)
    count = len(generated)
    if count <= 0:
        try:
            count = max(0, int(meta.get("generated_media_count") or 0))
        except Exception:
            count = 0
    if count <= 0:
        return ""
    if count == 1:
        return "已生成1张图片"
    return f"已生成{count}张图片"


def _text_looks_like_imagegen(value: Any) -> bool:
    low = str(value or "").strip().lower()
    return bool(low and any(needle in low for needle in _MEDIA_RUN_NEEDLES))


def _log_looks_like_imagegen(log_path: Path) -> bool:
    if not log_path.exists():
        return False
    try:
        with log_path.open("r", encoding="utf-8", errors="replace") as fh:
            for raw in fh:
                if _text_looks_like_imagegen(raw):
                    return True
    except Exception:
        return False
    return False


def run_looks_like_generated_media(
    meta: dict[str, Any],
    log_path: Path | None = None,
    *,
    extra_texts: list[Any] | tuple[Any, ...] | None = None,
) -> bool:
    row = meta if isinstance(meta, dict) else {}
    if str(row.get("cliType") or row.get("cli_type") or "").strip().lower() != "codex":
        return False
    if _generated_media_attachments(row):
        return True
    if str(row.get("generated_media_summary") or "").strip():
        return True
    try:
        if int(row.get("generated_media_count") or 0) > 0:
            return True
    except Exception:
        pass
    skills = normalize_skills_used_value(row.get("skills_used"), max_items=20)
    if any(skill in {"imagegen", "image_gen"} for skill in skills):
        return True
    text_values: list[Any] = [
        row.get("messagePreview"),
        row.get("lastPreview"),
        row.get("partialPreview"),
    ]
    if extra_texts:
        text_values.extend(list(extra_texts))
    if any(_text_looks_like_imagegen(item) for item in text_values):
        return True
    if log_path is not None and _log_looks_like_imagegen(log_path):
        return True
    return False


def _run_looks_like_generated_image(meta: dict[str, Any], log_path: Path) -> bool:
    if str(meta.get("cliType") or meta.get("cli_type") or "").strip().lower() != "codex":
        return False
    status = str(meta.get("status") or "").strip().lower()
    if status != "done":
        return False
    return run_looks_like_generated_media(meta, log_path)


def _candidate_generated_image_files(session_id: str, meta: dict[str, Any]) -> list[Path]:
    sid = str(session_id or "").strip()
    if not sid:
        return []
    root = CodexAdapter.get_home_path() / "generated_images" / sid
    if not root.exists() or not root.is_dir():
        return []
    start_ts = (
        parse_iso_ts(meta.get("startedAt"))
        or parse_iso_ts(meta.get("createdAt"))
        or 0.0
    )
    end_ts = (
        parse_iso_ts(meta.get("finishedAt"))
        or parse_iso_ts(meta.get("lastProgressAt"))
        or start_ts
        or 0.0
    )
    lower = start_ts - 30.0 if start_ts > 0 else 0.0
    upper = end_ts + 180.0 if end_ts > 0 else 0.0
    matched: list[tuple[float, Path]] = []
    try:
        for path in root.iterdir():
            if not path.is_file():
                continue
            if str(path.suffix or "").strip().lower() not in _IMAGE_FILE_EXTS:
                continue
            try:
                mtime = float(path.stat().st_mtime)
            except Exception:
                continue
            if lower > 0 and mtime < lower:
                continue
            if upper > 0 and mtime > upper:
                continue
            matched.append((mtime, path))
    except Exception:
        return []
    matched.sort(key=lambda item: (item[0], str(item[1])))
    return [item[1] for item in matched[-8:]]


def _meta_workdirs(meta: dict[str, Any]) -> list[Path]:
    row = meta if isinstance(meta, dict) else {}
    raw_values: list[Any] = [
        row.get("workdir"),
        row.get("run_cwd"),
        row.get("worktree_root"),
    ]
    context = row.get("project_execution_context")
    if isinstance(context, dict):
        for key in ("target", "source"):
            ref = context.get(key)
            if isinstance(ref, dict):
                raw_values.extend([ref.get("workdir"), ref.get("worktree_root")])
    out: list[Path] = []
    seen: set[str] = set()
    for raw in raw_values:
        text = str(raw or "").strip()
        if not text:
            continue
        try:
            path = Path(text).expanduser()
        except Exception:
            continue
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        out.append(path)
    return out


def candidate_local_imagegen_files(
    meta: dict[str, Any],
    *,
    now_ts: float = 0.0,
    max_items: int = 16,
) -> list[Path]:
    row = meta if isinstance(meta, dict) else {}
    start_ts = parse_iso_ts(row.get("startedAt")) or parse_iso_ts(row.get("createdAt")) or 0.0
    end_ts = (
        parse_iso_ts(row.get("finishedAt"))
        or parse_iso_ts(row.get("lastProgressAt"))
        or float(now_ts or 0.0)
        or start_ts
        or 0.0
    )
    lower = start_ts - 30.0 if start_ts > 0 else 0.0
    upper = end_ts + 180.0 if end_ts > 0 else 0.0
    matched: list[tuple[float, Path]] = []
    for base in _meta_workdirs(row):
        root = base / "output" / "imagegen"
        if not root.exists() or not root.is_dir():
            continue
        try:
            paths = root.rglob("*")
            for path in paths:
                if not path.is_file():
                    continue
                if str(path.suffix or "").strip().lower() not in _MEDIA_FILE_EXTS:
                    continue
                try:
                    mtime = float(path.stat().st_mtime)
                except Exception:
                    continue
                if lower > 0 and mtime < lower:
                    continue
                if upper > 0 and mtime > upper:
                    continue
                matched.append((mtime, path))
        except Exception:
            continue
    matched.sort(key=lambda item: (item[0], str(item[1])))
    limit = max(1, int(max_items or 16))
    return [item[1] for item in matched[-limit:]]


def latest_local_imagegen_mtime(meta: dict[str, Any], *, now_ts: float = 0.0) -> float:
    latest = 0.0
    for path in candidate_local_imagegen_files(meta, now_ts=now_ts, max_items=32):
        try:
            latest = max(latest, float(path.stat().st_mtime))
        except Exception:
            continue
    return latest


def _candidate_generated_media_files(session_id: str, meta: dict[str, Any]) -> list[tuple[Path, str]]:
    candidates: list[tuple[Path, str]] = []
    candidates.extend((path, _CODEX_GENERATED_MEDIA_SOURCE) for path in _candidate_generated_image_files(session_id, meta))
    candidates.extend((path, _LOCAL_IMAGEGEN_FALLBACK_SOURCE) for path in candidate_local_imagegen_files(meta))
    deduped: list[tuple[Path, str]] = []
    seen: set[str] = set()
    for path, source in candidates:
        key = f"{source}:{path}"
        if key in seen:
            continue
        seen.add(key)
        deduped.append((path, source))
    return deduped


def refresh_generated_media_status(
    meta: dict[str, Any],
    *,
    log_path: Path | None = None,
    extra_texts: list[Any] | tuple[Any, ...] | None = None,
) -> bool:
    row = meta if isinstance(meta, dict) else {}
    if str(row.get("cliType") or row.get("cli_type") or "").strip().lower() != "codex":
        return False
    generated = _generated_media_attachments(row)
    generated_count = 0
    try:
        generated_count = max(0, int(row.get("generated_media_count") or 0))
    except Exception:
        generated_count = 0
    status = str(row.get("status") or "").strip().lower()
    candidate = run_looks_like_generated_media(row, log_path, extra_texts=extra_texts)
    next_status = ""
    if generated or str(row.get("generated_media_summary") or "").strip() or generated_count > 0:
        next_status = "generated"
    elif candidate and status in {"queued", "retry_waiting", "running"}:
        next_status = "generating"
    elif candidate and status in {"done", "error", "interrupted"}:
        next_status = "failed"
    if not next_status:
        return False
    if str(row.get("generated_media_status") or "").strip() == next_status:
        return False
    row["generated_media_status"] = next_status
    return True


def reconcile_generated_media_for_run(store: Any, run_id: str, meta: dict[str, Any], *, log_path: Path | None = None) -> bool:
    row = meta if isinstance(meta, dict) else {}
    rid = str(run_id or row.get("id") or "").strip()
    if not rid:
        return False
    if str(row.get("cliType") or row.get("cli_type") or "").strip().lower() != "codex":
        return False
    actual_log_path = log_path or store._paths(rid)["log"]
    attachments = _normalize_run_attachments(row.get("attachments"))
    changed = False

    if _run_looks_like_generated_image(row, actual_log_path):
        session_id = str(row.get("sessionId") or "").strip()
        candidates = _candidate_generated_media_files(session_id, row)
        if candidates:
            attach_dir = store.runs_dir / rid / "attachments"
            try:
                attach_dir.mkdir(parents=True, exist_ok=True)
            except Exception:
                attach_dir = None
            existing_keys = {
                (
                    str(att.get("generatedBy") or att.get("generated_by") or "").strip().lower(),
                    str(att.get("filename") or "").strip(),
                    str(att.get("path") or "").strip(),
                )
                for att in attachments
                if isinstance(att, dict)
            }
            for src, generated_by in candidates:
                if attach_dir is None:
                    break
                base_name = src.name
                target = attach_dir / base_name
                if not target.exists():
                    stem = target.stem
                    suffix = target.suffix
                    seq = 1
                    while target.exists():
                        target = attach_dir / f"{stem}-{seq}{suffix}"
                        seq += 1
                    try:
                        shutil.copy2(src, target)
                    except Exception:
                        continue
                key = (generated_by, target.name, str(target))
                if key in existing_keys:
                    continue
                existing_keys.add(key)
                item = {
                    "filename": target.name,
                    "originalName": src.name,
                    "url": f"/.runs/{rid}/attachments/{target.name}",
                    "path": str(target),
                    "source": "generated",
                    "generatedBy": generated_by,
                    "attachment_role": "assistant",
                }
                content_type = _attachment_content_type(target)
                if content_type:
                    item["contentType"] = content_type
                attachments.append(
                    item
                )
                changed = True

    generated = [att for att in attachments if _is_generated_image_attachment(att)]
    generated_media = [att for att in attachments if _is_generated_media_attachment(att)]
    summary = synthesize_generated_media_summary(
        {
            "attachments": attachments,
            "generated_media_count": len(generated),
        }
    )
    if attachments != row.get("attachments"):
        row["attachments"] = attachments
        changed = True
    if generated:
        if summary and summary != str(row.get("generated_media_summary") or "").strip():
            row["generated_media_summary"] = summary
            changed = True
        if str(row.get("generated_media_kind") or "").strip() != "image":
            row["generated_media_kind"] = "image"
            changed = True
        if int(row.get("generated_media_count") or 0) != len(generated):
            row["generated_media_count"] = len(generated)
            changed = True
    if generated_media and not generated:
        if str(row.get("generated_media_kind") or "").strip() != "artifact":
            row["generated_media_kind"] = "artifact"
            changed = True
        if int(row.get("generated_media_count") or 0) != len(generated_media):
            row["generated_media_count"] = len(generated_media)
            changed = True
    if refresh_generated_media_status(row, log_path=actual_log_path):
        changed = True
    return changed


_SKILL_TOKEN_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,80}$")
_UUID_TOKEN_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)
_SKILL_INLINE_RE = re.compile(r"`([A-Za-z0-9][A-Za-z0-9._-]{2,80})`")
_SKILL_DOLLAR_RE = re.compile(r"\$([A-Za-z0-9][A-Za-z0-9._-]{1,80})")
_SKILL_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+?SKILL\.md[^)]*)\)", re.IGNORECASE)
_SKILL_PATH_RE = re.compile(r"/([^/]+)/SKILL\.md", re.IGNORECASE)
_SKILL_BLOCKED = {
    "task.js",
    "task.css",
    "task.html.tpl",
    "server.py",
    "task-dashboard",
    "codex",
}


def _get_known_skill_names() -> set[str]:
    names: set[str] = set()
    roots = [
        Path(__file__).resolve().parents[2] / ".codex" / "skills",
        Path.home() / ".codex" / "skills",
    ]
    for root in roots:
        if not root.exists():
            continue
        try:
            for skill_file in root.rglob("SKILL.md"):
                nm = skill_file.parent.name.strip().lower()
                if nm and _SKILL_TOKEN_RE.match(nm):
                    names.add(nm)
        except Exception:
            continue
    return names


def _normalize_skill_token(raw: Any) -> str:
    t = str(raw or "").strip().strip("`").strip()
    if not t:
        return ""
    if t.startswith("$"):
        t = t[1:].strip()
    if "/" in t:
        t = t.rstrip("/").rsplit("/", 1)[-1].strip()
    if t.lower().endswith(".md"):
        t = t[:-3].strip()
    t = t.lower()
    if not t or not _SKILL_TOKEN_RE.match(t):
        return ""
    if _UUID_TOKEN_RE.match(t):
        return ""
    if t in _SKILL_BLOCKED:
        return ""
    return t


def _is_skill_candidate(token: str, known: set[str]) -> bool:
    if not token:
        return False
    if token in known:
        return True
    if "skill" in token:
        return True
    if token.count("-") >= 2:
        return True
    return False


def extract_skills_used_from_texts(texts: list[str], max_items: int = 20) -> list[str]:
    if not texts:
        return []
    known = _get_known_skill_names()
    out: list[str] = []
    seen: set[str] = set()

    def _push(raw: Any) -> None:
        tok = _normalize_skill_token(raw)
        if not tok or tok in seen:
            return
        if not _is_skill_candidate(tok, known):
            return
        seen.add(tok)
        out.append(tok)

    for txt0 in texts:
        txt = str(txt0 or "")
        if not txt:
            continue
        for label, path in _SKILL_LINK_RE.findall(txt):
            _push(label)
            if path:
                m = _SKILL_PATH_RE.search(path)
                if m:
                    _push(m.group(1))
        for tok in _SKILL_DOLLAR_RE.findall(txt):
            _push(tok)
        for tok in _SKILL_INLINE_RE.findall(txt):
            _push(tok)
        if len(out) >= max_items:
            return out[:max_items]
    return out[:max_items]


def normalize_skills_used_value(raw: Any, max_items: int = 20) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        tok = _normalize_skill_token(item)
        if not tok or tok in seen:
            continue
        seen.add(tok)
        out.append(tok)
        if len(out) >= max_items:
            break
    return out


_BUSINESS_ALLOWED_TYPES = {"任务", "问题", "讨论", "反馈", "沉淀", "材料", "其他"}
_BUSINESS_PATH_SEGMENTS = [
    "/任务规划/",
    "/协同空间/",
    "/产出物/",
    "/任务/",
    "/问题/",
    "/讨论空间/",
    "/反馈/",
    "/沉淀/",
    "/材料/",
]
_BUSINESS_PATH_RE = re.compile(r"(/[^\s\"'`<>]+?\.(?:md|markdown|html?|pdf|png|jpe?g|webp|gif|svg|docx?|xlsx?|pptx?|txt|json|csv|toml|ya?ml))", re.IGNORECASE)
_BUSINESS_MARKER_RE = re.compile(r"(?:\[|【)\s*(任务|问题|讨论|反馈|沉淀|材料)\s*(?:\]|】)\s*[:：]?\s*([^\n\[\]【】]{1,120})")


def _clean_business_path(raw: Any) -> str:
    p = str(raw or "").strip().strip("`").strip()
    if not p:
        return ""
    while p and p[-1] in ").,;:，。；：】]>}":
        p = p[:-1]
    if not p.startswith("/"):
        return ""
    low = p.lower()
    m = re.search(r"\.(md|markdown|html?|pdf|png|jpe?g|webp|gif|svg|docx?|xlsx?|pptx?|txt|json|csv|toml|ya?ml)", low)
    if not m:
        return ""
    p = p[: m.end()]
    low = p.lower()
    if low.endswith("/skill.md") or ("/.codex/" + "skills/") in low:
        return ""
    if not any(seg in p for seg in _BUSINESS_PATH_SEGMENTS):
        return ""
    return p


def _strip_business_title_ext(name: str) -> str:
    t = str(name or "").strip()
    if not t:
        return ""
    return re.sub(r"\.(md|markdown|html?|pdf|png|jpe?g|webp|gif|svg|docx?|xlsx?|pptx?|txt|json|csv|toml|ya?ml)$", "", t, flags=re.IGNORECASE)


def _business_type_from_path(path: str, title: str = "") -> str:
    p = str(path or "")
    if "/任务/" in p:
        return "任务"
    if "/问题/" in p:
        return "问题"
    if "/讨论空间/" in p:
        return "讨论"
    if "/反馈/" in p:
        return "反馈"
    if "/产出物/沉淀/" in p or "/沉淀/" in p:
        return "沉淀"
    if "/产出物/材料/" in p or "/材料/" in p:
        return "材料"
    t = str(title or "")
    if "【任务】" in t:
        return "任务"
    if "【问题】" in t:
        return "问题"
    if "讨论" in t:
        return "讨论"
    if "【反馈】" in t or "反馈" in t:
        return "反馈"
    if "沉淀" in t:
        return "沉淀"
    if "材料" in t:
        return "材料"
    return "其他"


def _normalize_business_ref_item(raw: Any) -> Optional[dict[str, str]]:
    if not isinstance(raw, dict):
        return None
    path = _clean_business_path(raw.get("path"))
    title = _safe_text(raw.get("title"), 200).strip()
    if not title and path:
        title = _strip_business_title_ext(path.rsplit("/", 1)[-1])
    if not title:
        return None
    typ = _safe_text(raw.get("type"), 20).strip()
    if typ not in _BUSINESS_ALLOWED_TYPES:
        typ = _business_type_from_path(path, title)
    return {
        "type": typ if typ in _BUSINESS_ALLOWED_TYPES else "其他",
        "title": title,
        "path": path,
    }


def normalize_business_refs_value(raw: Any, max_items: int = 24) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        return []
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in raw:
        norm = _normalize_business_ref_item(item)
        if not norm:
            continue
        key = f"{norm.get('type','')}|{norm.get('path','')}|{norm.get('title','')}"
        if key in seen:
            continue
        seen.add(key)
        out.append(norm)
        if len(out) >= max_items:
            break
    return out


def extract_business_refs_from_texts(texts: list[str], max_items: int = 24) -> list[dict[str, str]]:
    if not texts:
        return []
    out: list[dict[str, str]] = []
    seen: set[str] = set()

    def _push(ref_type: str, title_raw: Any, path_raw: Any = "") -> None:
        path = _clean_business_path(path_raw)
        title = _safe_text(title_raw, 200).strip()
        if not title and path:
            title = _strip_business_title_ext(path.rsplit("/", 1)[-1])
        if not title:
            return
        typ = str(ref_type or "").strip()
        if typ not in _BUSINESS_ALLOWED_TYPES:
            typ = _business_type_from_path(path, title)
        if typ not in _BUSINESS_ALLOWED_TYPES:
            typ = "其他"
        key = f"{typ}|{path}|{title}"
        if key in seen:
            return
        seen.add(key)
        out.append({"type": typ, "title": title, "path": path})

    for txt0 in texts:
        txt = str(txt0 or "")
        if not txt:
            continue
        for raw_path in _BUSINESS_PATH_RE.findall(txt):
            path = _clean_business_path(raw_path)
            if not path:
                continue
            title = _strip_business_title_ext(path.rsplit("/", 1)[-1])
            _push(_business_type_from_path(path, title), title, path)
            if len(out) >= max_items:
                return out[:max_items]
        txt_for_markers = _BUSINESS_PATH_RE.sub(" ", txt)
        for typ, title_raw in _BUSINESS_MARKER_RE.findall(txt_for_markers):
            title = str(title_raw or "").strip()
            if not title:
                continue
            for sep in ["。", "；", ";", "，", ",", "\n"]:
                if sep in title:
                    title = title.split(sep, 1)[0].strip()
            if len(title) > 80:
                title = title[:80].strip()
            _push(typ, title, "")
            if len(out) >= max_items:
                return out[:max_items]
    return out[:max_items]
