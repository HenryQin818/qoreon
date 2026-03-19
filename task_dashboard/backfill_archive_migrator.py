from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path


RE_BACKFILL_TASK_NAME = re.compile(r"^【已完成】【任务】(?P<date>\d{8})-(?P<seq>\d+)-反向补录-(?P<slug>.+)\.md$")


@dataclass(frozen=True)
class MigrationItem:
    src: Path
    dst: Path


def _unique_dst_path(dst: Path, reserved: set[Path]) -> Path:
    candidate = dst
    if candidate not in reserved and not candidate.exists():
        return candidate
    stem = candidate.stem
    suffix = candidate.suffix
    for idx in range(1, 10000):
        alt = candidate.with_name(f"{stem}-dup{idx:02d}{suffix}")
        if alt in reserved or alt.exists():
            continue
        return alt
    raise RuntimeError(f"cannot allocate unique archive path for: {dst}")


def plan_migration(task_root: Path) -> list[MigrationItem]:
    items: list[MigrationItem] = []
    for src in sorted(task_root.rglob("【已完成】【任务】*反向补录*.md")):
        m = RE_BACKFILL_TASK_NAME.match(src.name)
        if not m:
            continue
        if src.parent.name != "任务":
            continue
        channel_dir = src.parent.parent
        archive_dir = channel_dir / "归档" / "反向补录"
        seq = int(m.group("seq"))
        dst_name = f"【已归档】【归档】{m.group('date')}-{seq:02d}-反向补录-{m.group('slug')}.md"
        items.append(MigrationItem(src=src, dst=archive_dir / dst_name))
    return items


def migrate(task_root: Path, apply: bool = False, limit: int = 0, include_paths: bool = False) -> dict[str, object]:
    plans = plan_migration(task_root)
    if limit > 0:
        plans = plans[:limit]

    moved_paths: list[str] = []
    skipped_paths: list[str] = []
    reserved_dst: set[Path] = set()
    for item in plans:
        dst = _unique_dst_path(item.dst, reserved_dst)
        reserved_dst.add(dst)
        if item.src == dst:
            skipped_paths.append(str(item.src))
            continue
        if apply:
            dst.parent.mkdir(parents=True, exist_ok=True)
            item.src.rename(dst)
        moved_paths.append(f"{item.src} -> {dst}")

    summary: dict[str, object] = {
        "task_root": str(task_root),
        "apply": apply,
        "planned": len(plans),
        "moved": len(moved_paths),
        "skipped": len(skipped_paths),
    }
    if include_paths:
        summary["moves"] = moved_paths
        summary["skipped_paths"] = skipped_paths
    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Migrate reverse-backfill task docs into archive docs.")
    ap.add_argument("--task-root", default="任务规划", help="task planning root directory")
    ap.add_argument("--apply", action="store_true", help="apply file moves; default is dry-run")
    ap.add_argument("--limit", type=int, default=0, help="limit number of migrations")
    ap.add_argument("--with-paths", action="store_true", help="include moved/skipped path details")
    args = ap.parse_args(argv)

    summary = migrate(
        task_root=Path(args.task_root).resolve(),
        apply=bool(args.apply),
        limit=max(0, int(args.limit or 0)),
        include_paths=bool(args.with_paths),
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
