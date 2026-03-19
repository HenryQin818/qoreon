from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

from .domain import looks_like_session_id
from .utils import safe_read_text


def _as_str(v: Any) -> str:
    return "" if v is None else str(v)


def _normalize_reasoning_effort(v: Any) -> str:
    txt = _as_str(v).strip().lower().replace("-", "_").replace(" ", "_")
    alias = {
        "extra_high": "xhigh",
        "very_high": "xhigh",
        "ultra": "xhigh",
        "extra": "xhigh",
    }
    txt = alias.get(txt, txt)
    if txt in {"low", "medium", "high", "xhigh"}:
        return txt
    return ""


def parse_session_id_list(md_path: Path) -> list[dict[str, Any]]:
    """
    Parse a markdown session list with section headers:

    ## 使用规则
    - 子级01-...
      - alias：xxx
      - session_id：<uuid>

    We keep section association by scanning linearly (no block-splitting).
    """
    if not md_path.exists():
        return []
    md = safe_read_text(md_path)

    current_section = ""
    out: list[dict[str, Any]] = []

    cur_name: str = ""
    cur_alias: str = ""
    cur_sid: str = ""

    def flush() -> None:
        nonlocal cur_name, cur_alias, cur_sid, current_section, out
        sid = (cur_sid or "").strip()
        if sid and looks_like_session_id(sid):
            out.append(
                {
                    "section": current_section,
                    "name": (cur_name or cur_alias or sid).strip(),
                    "alias": (cur_alias or "").strip(),
                    "session_id": sid,
                }
            )
        cur_name = ""
        cur_alias = ""
        cur_sid = ""

    for raw in md.splitlines():
        s = raw.strip()
        if s.startswith("## "):
            flush()
            current_section = s[3:].strip()
            continue
        # Start of a new top-level entry: "- xxx"
        if s.startswith("- ") and not s.lower().startswith("- alias") and "session_id" not in s.lower():
            # New entry
            flush()
            cur_name = s[2:].strip()
            continue
        if "alias" in s and ("：" in s or ":" in s):
            cur_alias = re.split(r"[:：]", s, 1)[1].strip()
            continue
        if "session_id" in s and ("：" in s or ":" in s):
            cur_sid = re.split(r"[:：]", s, 1)[1].strip()
            continue

    flush()

    # Deduplicate
    seen: set[tuple[str, str]] = set()
    dedup: list[dict[str, Any]] = []
    for e in out:
        key = (str(e.get("name") or ""), str(e.get("session_id") or ""))
        if key in seen:
            continue
        seen.add(key)
        dedup.append(e)
    return dedup


def parse_session_json(json_path: Path) -> list[dict[str, Any]]:
    if not json_path.exists():
        return []
    try:
        obj = json.loads(safe_read_text(json_path))
    except Exception:
        return []
    if not isinstance(obj, dict):
        return []
    channels = obj.get("channels")
    if not isinstance(channels, dict):
        return []

    out: list[dict[str, Any]] = []
    for name_raw, sessions_raw in channels.items():
        ch_name = _as_str(name_raw).strip()
        if not ch_name:
            continue
        entries = sessions_raw if isinstance(sessions_raw, list) else [sessions_raw]
        picked: Optional[dict[str, Any]] = None
        for e in entries:
            if not isinstance(e, dict):
                continue
            sid = _as_str(e.get("sessionId") or e.get("session_id")).strip()
            if not sid or not looks_like_session_id(sid):
                continue
            picked = e
            break
        if not picked:
            continue
        alias = _as_str(picked.get("profileLabel") or picked.get("profile_label") or picked.get("alias")).strip()
        desc = _as_str(picked.get("desc") or picked.get("description")).strip()
        cli_type = _as_str(picked.get("cli_type") or picked.get("cliType") or "codex").strip()
        out.append(
            {
                "name": ch_name,
                "alias": alias,
                "session_id": _as_str(picked.get("sessionId") or picked.get("session_id")).strip(),
                "desc": desc,
                "cli_type": cli_type or "codex",
                "model": _as_str(picked.get("model")).strip(),
                "reasoning_effort": _normalize_reasoning_effort(
                    picked.get("reasoning_effort") if "reasoning_effort" in picked else picked.get("reasoningEffort")
                ),
            }
        )
    return out


def channel_session_map(sessions: list[dict[str, Any]], *, strip_leading_bracket: bool = True) -> dict[str, dict[str, Any]]:
    m: dict[str, dict[str, Any]] = {}
    for s in sessions:
        name = str((s or {}).get("name") or "").strip()
        if not name:
            continue
        name_norm = re.sub(r"^【[^】]+】\s*", "", name) if strip_leading_bracket else name
        m[name_norm] = s
    return m
