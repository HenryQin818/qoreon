from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from .utils import iter_channel_dirs


MARKER_RE = re.compile(r"^\s*\[来源通道\s*:\s*([^\]]+?)\s*\]\s*$", re.MULTILINE)
LEADING_STATUS_RE = re.compile(r"^【([^】]+)】")


def _parse_iso_ts(raw: str) -> float:
    s = str(raw or "").strip()
    if not s:
        return 0.0
    try:
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S%z").timestamp()
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(s).timestamp()
    except ValueError:
        return 0.0


def _read_head(path: Path, lines: int = 20) -> str:
    out: list[str] = []
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as f:
            for idx, line in enumerate(f):
                out.append(line.rstrip("\n"))
                if idx + 1 >= lines:
                    break
    except Exception:
        return ""
    return "\n".join(out)


def _iter_target_docs(task_root: Path, include_task_docs: bool = False) -> list[Path]:
    targets: list[Path] = []
    subdirs = ["反馈", "答复"]
    if include_task_docs:
        subdirs.append("任务")

    for ch in iter_channel_dirs(task_root):
        for sub in subdirs:
            d = ch / sub
            if not d.exists() or not d.is_dir():
                continue
            targets.extend(sorted(d.glob("*.md")))
    return targets


def _status_from_filename(path: Path) -> str:
    m = LEADING_STATUS_RE.match(path.name or "")
    return str(m.group(1) or "").strip() if m else ""


def audit_source_channel_markers(
    *,
    task_root: Path,
    legacy_cutoff_iso: str = "2026-02-21T01:08:00+0800",
    include_task_docs: bool = False,
    whitelist_statuses: tuple[str, ...] = ("已验收通过",),
    max_detail_items: int = 50,
) -> dict[str, Any]:
    cutoff_ts = _parse_iso_ts(legacy_cutoff_iso)
    whitelist = {str(x or "").strip() for x in whitelist_statuses if str(x or "").strip()}
    checked_docs = 0
    pass_count = 0
    missing_count = 0
    legacy_count = 0
    invalid_count = 0
    whitelist_count = 0

    missing_paths: list[str] = []
    legacy_paths: list[str] = []
    invalid_paths: list[str] = []
    whitelist_paths: list[str] = []

    for p in _iter_target_docs(task_root, include_task_docs=include_task_docs):
        checked_docs += 1
        content = _read_head(p, lines=20)
        m = MARKER_RE.search(content)
        if m:
            channel = str(m.group(1) or "").strip()
            if channel:
                pass_count += 1
                continue
            invalid_count += 1
            if len(invalid_paths) < max_detail_items:
                invalid_paths.append(str(p))
            continue

        mtime = p.stat().st_mtime
        status = _status_from_filename(p)
        if status in whitelist:
            whitelist_count += 1
            legacy_count += 1
            if len(whitelist_paths) < max_detail_items:
                whitelist_paths.append(str(p))
            if len(legacy_paths) < max_detail_items:
                legacy_paths.append(str(p))
            continue
        if cutoff_ts > 0 and mtime < cutoff_ts:
            legacy_count += 1
            if len(legacy_paths) < max_detail_items:
                legacy_paths.append(str(p))
            continue
        missing_count += 1
        if len(missing_paths) < max_detail_items:
            missing_paths.append(str(p))

    return {
        "legacy_cutoff_iso": legacy_cutoff_iso,
        "include_task_docs": bool(include_task_docs),
        "whitelist_statuses": sorted(whitelist),
        "checked_docs": checked_docs,
        "pass_count": pass_count,
        "missing_count": missing_count,
        "legacy_count": legacy_count,
        "invalid_count": invalid_count,
        "whitelist_count": whitelist_count,
        "missing_paths": missing_paths,
        "legacy_paths": legacy_paths,
        "invalid_paths": invalid_paths,
        "whitelist_paths": whitelist_paths,
    }
