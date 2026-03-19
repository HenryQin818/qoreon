from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .sender_contract import validate_sender_consistency


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


def _sender_field(meta: dict[str, Any], snake: str, camel: str) -> str:
    return str(meta.get(snake) or meta.get(camel) or "").strip()


def _append_sender_sample(
    samples: dict[str, list[dict[str, str]]],
    sender_type: str,
    *,
    run_id: str,
    path: str,
    sender_id: str,
    sender_name: str,
    max_detail_items: int,
) -> None:
    if sender_type not in samples:
        return
    bucket = samples[sender_type]
    if len(bucket) >= max_detail_items:
        return
    bucket.append(
        {
            "run_id": run_id,
            "path": path,
            "sender_type": sender_type,
            "sender_id": sender_id,
            "sender_name": sender_name,
        }
    )


def _created_ts(meta: dict[str, Any], path: Path) -> float:
    ts = _parse_iso_ts(str(meta.get("createdAt") or ""))
    if ts > 0:
        return ts
    try:
        return float(path.stat().st_mtime)
    except Exception:
        return 0.0


def audit_run_sender_integrity(
    *,
    runs_dir: Path,
    legacy_cutoff_iso: str = "2026-02-21T04:01:00+0800",
    max_detail_items: int = 100,
    include_hidden: bool = False,
) -> dict[str, Any]:
    cutoff_ts = _parse_iso_ts(legacy_cutoff_iso)
    checked_runs = 0
    pass_count = 0
    missing_count = 0
    legacy_count = 0
    invalid_count = 0

    missing_items: list[dict[str, Any]] = []
    legacy_items: list[dict[str, Any]] = []
    invalid_items: list[dict[str, Any]] = []

    sender_type_counts: dict[str, int] = {}
    sender_samples: dict[str, list[dict[str, str]]] = {"user": [], "agent": [], "system": [], "legacy": []}

    for p in sorted(runs_dir.glob("*.json")):
        try:
            meta = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(meta, dict):
            continue
        if not include_hidden and bool(meta.get("hidden")):
            continue

        checked_runs += 1
        run_id = str(meta.get("id") or p.stem).strip() or p.stem

        raw_sender_type = _sender_field(meta, "sender_type", "senderType").lower()
        has_sender_key = any(
            k in meta for k in ("sender_type", "senderType", "sender_id", "senderId", "sender_name", "senderName")
        )

        # Backward compatibility: historical runs with no sender fields are legacy.
        run_created_ts = _created_ts(meta, p)
        if not has_sender_key and cutoff_ts > 0 and run_created_ts > 0 and run_created_ts < cutoff_ts:
            legacy_count += 1
            _append_sender_sample(
                sender_samples,
                "legacy",
                run_id=run_id,
                path=str(p),
                sender_id="legacy",
                sender_name="历史消息（来源未知）",
                max_detail_items=max_detail_items,
            )
            if len(legacy_items) < max_detail_items:
                legacy_items.append(
                    {
                        "run_id": run_id,
                        "path": str(p),
                        "sender_type": "legacy",
                        "sender_id": "legacy",
                        "sender_name": "历史消息（来源未知）",
                    }
                )
            continue

        checked = validate_sender_consistency(meta)
        normalized = checked.get("normalized") or {}
        norm_type = str(normalized.get("sender_type") or "").strip().lower()
        norm_id = str(normalized.get("sender_id") or "").strip()
        norm_name = str(normalized.get("sender_name") or "").strip()
        sender_type_counts[norm_type or "unknown"] = int(sender_type_counts.get(norm_type or "unknown") or 0) + 1

        issues = checked.get("issues") or []
        codes = {str(it.get("code") or "") for it in issues}
        if "invalid_sender_type" in codes:
            invalid_count += 1
            if len(invalid_items) < max_detail_items:
                invalid_items.append({"run_id": run_id, "path": str(p), "reason": "invalid_sender_type"})
            continue

        # Explicit legacy is always counted as legacy, including new data.
        if raw_sender_type == "legacy" or (norm_type == "legacy" and not raw_sender_type and cutoff_ts > 0 and run_created_ts < cutoff_ts):
            legacy_count += 1
            _append_sender_sample(
                sender_samples,
                "legacy",
                run_id=run_id,
                path=str(p),
                sender_id=norm_id,
                sender_name=norm_name,
                max_detail_items=max_detail_items,
            )
            if len(legacy_items) < max_detail_items:
                legacy_items.append(
                    {
                        "run_id": run_id,
                        "path": str(p),
                        "sender_type": norm_type,
                        "sender_id": norm_id,
                        "sender_name": norm_name,
                    }
                )
            continue

        error_codes = [c for c in codes if c]
        if error_codes or norm_type == "legacy":
            missing_count += 1
            if len(missing_items) < max_detail_items:
                reasons = error_codes if error_codes else ["missing_sender_type"]
                missing_items.append({"run_id": run_id, "path": str(p), "reasons": reasons})
            continue

        _append_sender_sample(
            sender_samples,
            norm_type,
            run_id=run_id,
            path=str(p),
            sender_id=norm_id,
            sender_name=norm_name,
            max_detail_items=max_detail_items,
        )
        pass_count += 1

    return {
        "legacy_cutoff_iso": legacy_cutoff_iso,
        "checked_runs": checked_runs,
        "pass_count": pass_count,
        "missing_count": missing_count,
        "legacy_count": legacy_count,
        "invalid_count": invalid_count,
        "sender_type_counts": sender_type_counts,
        "sender_samples": sender_samples,
        "missing_items": missing_items,
        "legacy_items": legacy_items,
        "invalid_items": invalid_items,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Audit run sender identity completeness")
    ap.add_argument("--runs-dir", default=".runs", help="runs directory")
    ap.add_argument(
        "--legacy-cutoff",
        default="2026-02-21T04:01:00+0800",
        help="runs older than this cutoff without sender fields are counted as legacy",
    )
    ap.add_argument("--max-detail-items", type=int, default=100, help="max detail items in result")
    ap.add_argument("--include-hidden", action="store_true", help="include hidden/cancelled runs in audit")
    args = ap.parse_args(argv)

    summary = audit_run_sender_integrity(
        runs_dir=Path(args.runs_dir).resolve(),
        legacy_cutoff_iso=str(args.legacy_cutoff or "").strip() or "2026-02-21T04:01:00+0800",
        max_detail_items=max(1, int(args.max_detail_items or 1)),
        include_hidden=bool(args.include_hidden),
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
