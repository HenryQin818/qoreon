from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Iterable


# Top-level folders under `任务规划/` that store assets/snapshots/templates, not real business channels.
# Keep this list centralized so build scan and inspections share the same behavior.
NON_CHANNEL_DIR_NAMES = frozenset(
    {
        "全局资源",
        "协作工作模板",
    }
)


def repo_root_from_here(anchor_file: str) -> Path:
    p = Path(anchor_file).resolve()
    for parent in [p.parent] + list(p.parents):
        if (parent / ".git").exists():
            return parent
    for parent in [p.parent] + list(p.parents):
        if (parent / "task_dashboard").exists() and (parent / "web").exists():
            return parent
    return p.parents[1]


def safe_read_text(p: Path, max_bytes: int = 256_000) -> str:
    with p.open("rb") as f:
        raw = f.read(max_bytes + 1)
    raw = raw[:max_bytes]
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("utf-8", errors="replace")


def iso_now_local() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def file_mtime_iso(p: Path) -> str:
    try:
        ts = p.stat().st_mtime
        return dt.datetime.fromtimestamp(ts).astimezone().isoformat(timespec="seconds")
    except Exception:
        return ""


def norm_relpath(root: Path, p: Path) -> str:
    try:
        return str(p.relative_to(root))
    except Exception:
        pass
    try:
        return str(p.resolve().relative_to(root.resolve()))
    except Exception:
        return str(p)


def is_channel_dir_name(name: str) -> bool:
    n = str(name or "").strip()
    if not n:
        return False
    if n in NON_CHANNEL_DIR_NAMES:
        return False
    return True


def iter_channel_dirs(task_root: Path) -> Iterable[Path]:
    for p in sorted(task_root.iterdir()):
        if not p.is_dir():
            continue
        if not is_channel_dir_name(p.name):
            continue
        yield p
