# -*- coding: utf-8 -*-

from __future__ import annotations

from collections import deque
import json
from pathlib import Path
import re
from typing import Any, Optional

from task_dashboard.adapters import CodexAdapter, get_adapter


def _safe_text(s: Any, max_len: int) -> str:
    s2 = "" if s is None else str(s)
    if len(s2) > max_len:
        return s2[: max_len - 1] + "…"
    return s2


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


def extract_terminal_message_text(log_text: str, *, cli_type: str = "codex") -> str:
    cli = str(cli_type or "").strip().lower()
    if not log_text or cli != "claude":
        return ""
    adapter_cls = get_adapter(cli) or CodexAdapter
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
    return "\n".join(part for part in out if str(part or "").strip()).strip()


def extract_terminal_message_from_file(path: Path, *, cli_type: str = "codex") -> str:
    if not path.exists():
        return ""
    try:
        return extract_terminal_message_text(path.read_text(encoding="utf-8", errors="replace"), cli_type=cli_type)
    except Exception:
        return ""


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
    if low.endswith("/skill.md") or "/.codex/skills/" in low:
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
