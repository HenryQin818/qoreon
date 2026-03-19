from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


TERMINAL_STATUSES = {"done", "error"}


@dataclass(frozen=True)
class RunMeta:
    run_id: str
    status: str
    created_ts: float
    file_mtime_ts: float
    path: Path


def _now_local_iso() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")


def _parse_ts(raw: str) -> float:
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


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _load_state(state_path: Path) -> tuple[dict[str, Any], bool]:
    default_state: dict[str, Any] = {
        "version": 1,
        "last_checked_at": "",
        "processed_run_meta": {},
        "processed_run_ids": [],
    }
    if not state_path.exists():
        return default_state, False
    try:
        raw = _read_json(state_path)
    except Exception:
        backup = state_path.with_name(f"{state_path.name}.corrupt-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
        try:
            shutil.move(str(state_path), str(backup))
        except Exception:
            pass
        return default_state, True

    out = dict(default_state)
    out["version"] = int(raw.get("version") or 1)
    out["last_checked_at"] = str(raw.get("last_checked_at") or "")

    meta = raw.get("processed_run_meta")
    if isinstance(meta, dict):
        processed_map = {str(k): str(v) for k, v in meta.items() if str(k).strip()}
    else:
        processed_map = {}
        ids = raw.get("processed_run_ids")
        if isinstance(ids, list):
            for rid in ids:
                r = str(rid or "").strip()
                if r:
                    processed_map[r] = ""

    out["processed_run_meta"] = processed_map
    out["processed_run_ids"] = sorted(processed_map.keys())
    return out, False


def _list_run_meta(runs_dir: Path) -> tuple[list[RunMeta], int]:
    metas: list[RunMeta] = []
    invalid_json = 0
    for p in sorted(runs_dir.glob("*.json")):
        try:
            raw = _read_json(p)
        except Exception:
            invalid_json += 1
            continue

        run_id = str(raw.get("id") or p.stem).strip()
        if not run_id:
            continue
        status = str(raw.get("status") or "").strip().lower()
        created_ts = _parse_ts(str(raw.get("createdAt") or ""))
        mtime_ts = p.stat().st_mtime
        metas.append(
            RunMeta(
                run_id=run_id,
                status=status,
                created_ts=created_ts,
                file_mtime_ts=mtime_ts,
                path=p,
            )
        )
    metas.sort(key=lambda x: (x.created_ts, x.file_mtime_ts, x.run_id))
    return metas, invalid_json


def _prune_processed(processed_map: dict[str, str], retention_days: int) -> dict[str, str]:
    keep_after = datetime.now(timezone.utc) - timedelta(days=max(1, int(retention_days or 1)))
    out: dict[str, str] = {}
    for rid, ts in processed_map.items():
        pt = _parse_ts(ts)
        if pt <= 0:
            out[rid] = ts
            continue
        if datetime.fromtimestamp(pt, timezone.utc) >= keep_after:
            out[rid] = ts
    return out


def inspect_incremental_runs(
    *,
    runs_dir: Path,
    state_path: Path,
    ledger_path: Path,
    retention_days: int = 90,
    limit: int = 0,
    force_full_scan: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    scan_started_at = _now_local_iso()
    state, recovered_from_corruption = _load_state(state_path)
    last_checked_ts = _parse_ts(str(state.get("last_checked_at") or ""))
    processed_map = dict(state.get("processed_run_meta") or {})

    metas, invalid_json = _list_run_meta(runs_dir)
    mode = "full" if force_full_scan or last_checked_ts <= 0 else "incremental"

    if mode == "full":
        candidates = list(metas)
    else:
        candidates = [
            m
            for m in metas
            if (m.created_ts > last_checked_ts) or (m.file_mtime_ts > last_checked_ts)
        ]

    terminal = [m for m in candidates if m.status in TERMINAL_STATUSES]
    skipped_processed = 0
    to_process: list[RunMeta] = []
    for m in terminal:
        if m.run_id in processed_map:
            skipped_processed += 1
            continue
        to_process.append(m)

    if limit and limit > 0:
        to_process = to_process[:limit]

    status_counts: dict[str, int] = {}
    now_ts = _now_local_iso()
    for m in to_process:
        status_counts[m.status] = status_counts.get(m.status, 0) + 1
        processed_map[m.run_id] = now_ts

    processed_map = _prune_processed(processed_map, retention_days=retention_days)

    scan_finished_at = _now_local_iso()
    summary: dict[str, Any] = {
        "scan_started_at": scan_started_at,
        "scan_finished_at": scan_finished_at,
        "mode": mode,
        "recovered_from_corruption": recovered_from_corruption,
        "runs_dir": str(runs_dir),
        "state_path": str(state_path),
        "ledger_path": str(ledger_path),
        "totals": {
            "runs_json_files": len(metas),
            "invalid_json_files": invalid_json,
            "candidates_after_watermark": len(candidates),
            "terminal_candidates": len(terminal),
            "new_terminal_runs": len(to_process),
            "skipped_already_processed": skipped_processed,
        },
        "status_counts": status_counts,
        "processed_run_ids": [m.run_id for m in to_process],
    }

    if not dry_run:
        next_state = {
            "version": 1,
            "last_checked_at": scan_started_at,
            "last_scan_started_at": scan_started_at,
            "last_scan_finished_at": scan_finished_at,
            "processed_run_meta": processed_map,
            "processed_run_ids": sorted(processed_map.keys()),
        }
        _write_json(state_path, next_state)
        _append_jsonl(ledger_path, summary)

    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Incremental .runs inspector with watermark/ledger")
    ap.add_argument("--runs-dir", default=".runs", help="runs metadata directory")
    ap.add_argument("--state-path", default=".run/inspection/watermark.json", help="watermark state file path")
    ap.add_argument("--ledger-path", default=".run/inspection/ledger.jsonl", help="scan ledger file path")
    ap.add_argument("--retention-days", type=int, default=90, help="processed run ids retention")
    ap.add_argument("--limit", type=int, default=0, help="max new terminal runs to return (0=unlimited)")
    ap.add_argument("--force-full-scan", action="store_true", help="ignore watermark and rescan all runs")
    ap.add_argument("--dry-run", action="store_true", help="calculate summary only, do not persist state")
    args = ap.parse_args(argv)

    summary = inspect_incremental_runs(
        runs_dir=Path(args.runs_dir).resolve(),
        state_path=Path(args.state_path).resolve(),
        ledger_path=Path(args.ledger_path).resolve(),
        retention_days=max(1, int(args.retention_days or 1)),
        limit=max(0, int(args.limit or 0)),
        force_full_scan=bool(args.force_full_scan),
        dry_run=bool(args.dry_run),
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
