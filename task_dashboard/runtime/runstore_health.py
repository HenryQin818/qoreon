from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Iterable


TERMINAL_STATUSES = {"done", "error", "interrupted"}
PROTECTED_STATUSES = {"queued", "retry_waiting", "running", "active", "finalizing"}


def _as_str(value: Any) -> str:
    return "" if value is None else str(value)


def _parse_iso_ts(value: Any) -> float:
    text = _as_str(value).strip()
    if not text:
        return 0.0
    try:
        from datetime import datetime

        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except Exception:
        pass
    try:
        from datetime import datetime

        return datetime.strptime(text, "%Y-%m-%dT%H:%M:%S%z").timestamp()
    except Exception:
        return 0.0


def _now_iso() -> str:
    try:
        from datetime import datetime

        return datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")
    except Exception:
        return time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime())


def _read_json_dict(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _safe_stat_size(path: Path) -> int:
    try:
        return int(path.stat().st_size)
    except Exception:
        return 0


def _dir_file_summary(path: Path) -> dict[str, Any]:
    file_count = 0
    json_count = 0
    total_bytes = 0
    if not path.exists():
        return {
            "path": str(path),
            "exists": False,
            "file_count": 0,
            "json_count": 0,
            "total_bytes": 0,
        }
    try:
        children = list(path.iterdir())
    except Exception:
        children = []
    for child in children:
        if not child.is_file():
            continue
        file_count += 1
        if child.suffix == ".json":
            json_count += 1
        total_bytes += _safe_stat_size(child)
    return {
        "path": str(path),
        "exists": True,
        "file_count": file_count,
        "json_count": json_count,
        "total_bytes": total_bytes,
    }


def _archive_bucket_summary(archive_dir: Path, *, max_buckets: int = 24) -> dict[str, Any]:
    if not archive_dir.exists():
        return {"path": str(archive_dir), "exists": False, "bucket_count": 0, "buckets": []}
    buckets: list[dict[str, Any]] = []
    try:
        children = [p for p in archive_dir.iterdir() if p.is_dir()]
    except Exception:
        children = []
    for child in sorted(children, key=lambda p: p.name, reverse=True)[: max(1, int(max_buckets or 1))]:
        buckets.append({"bucket": child.name, "path": str(child)})
    return {
        "path": str(archive_dir),
        "exists": True,
        "bucket_count": len(children),
        "buckets": buckets,
    }


def _iter_live_meta_paths(store: Any) -> list[Path]:
    fn = getattr(store, "_iter_live_meta_paths", None)
    if callable(fn):
        try:
            return [Path(p) for p in fn()]
        except Exception:
            return []
    hot_dir = Path(getattr(store, "hot_dir", Path()))
    if hot_dir.exists():
        return list(hot_dir.glob("*.json"))
    runs_dir = Path(getattr(store, "runs_dir", Path()))
    return list(runs_dir.glob("*.json")) if runs_dir.exists() else []


def _location_for_meta(store: Any, meta_path: Path) -> str:
    try:
        if meta_path.parent.resolve() == Path(getattr(store, "hot_dir")).resolve():
            return "hot"
    except Exception:
        pass
    try:
        if meta_path.parent.resolve() == Path(getattr(store, "runs_dir")).resolve():
            return "legacy_root"
    except Exception:
        pass
    return "live"


def _anchor_ts(meta: dict[str, Any]) -> float:
    for key in ("finishedAt", "createdAt", "startedAt"):
        ts = _parse_iso_ts(meta.get(key))
        if ts > 0:
            return ts
    return 0.0


def _archive_bucket_for_meta(store: Any, meta: dict[str, Any]) -> str:
    fn = getattr(store, "_archive_bucket_for_meta", None)
    if callable(fn):
        try:
            return str(fn(meta) or "").strip() or time.strftime("%Y-%m", time.localtime())
        except Exception:
            pass
    for key in ("finishedAt", "createdAt", "startedAt"):
        raw = _as_str(meta.get(key)).strip()
        if len(raw) >= 7 and raw[4] == "-":
            return raw[:7]
    return time.strftime("%Y-%m", time.localtime())


def _normalize_project_filter(project_id: str) -> str:
    return _as_str(project_id).strip()


def _normalize_protected_run_ids(values: Iterable[str] | None) -> set[str]:
    return {_as_str(v).strip() for v in (values or []) if _as_str(v).strip()}


def _run_candidate_row(
    store: Any,
    meta_path: Path,
    meta: dict[str, Any],
    *,
    now_ts: float,
    older_than_s: float,
    protected_run_ids: set[str],
) -> dict[str, Any]:
    run_id = _as_str(meta.get("id")).strip() or meta_path.stem
    status = _as_str(meta.get("status")).strip().lower() or "unknown"
    anchor = _anchor_ts(meta)
    age_s = max(0, int(now_ts - anchor)) if anchor > 0 else 0
    terminal = status in TERMINAL_STATUSES
    protected = status in PROTECTED_STATUSES or run_id in protected_run_ids
    eligible = terminal and not protected and anchor > 0 and age_s >= int(max(0, older_than_s))
    return {
        "run_id": run_id,
        "status": status,
        "project_id": _as_str(meta.get("projectId")).strip(),
        "channel_name": _as_str(meta.get("channelName")).strip(),
        "session_id": _as_str(meta.get("sessionId")).strip(),
        "created_at": _as_str(meta.get("createdAt")).strip(),
        "finished_at": _as_str(meta.get("finishedAt")).strip(),
        "age_s": age_s,
        "terminal": terminal,
        "protected": protected,
        "eligible": eligible,
        "bucket": _archive_bucket_for_meta(store, meta),
        "location": _location_for_meta(store, meta_path),
    }


def list_hot_run_candidates(
    store: Any,
    *,
    project_id: str = "",
    older_than_s: float = 86400.0,
    limit: int = 100,
    protected_run_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    pid = _normalize_project_filter(project_id)
    protected_ids = _normalize_protected_run_ids(protected_run_ids)
    now_ts = time.time()
    rows: list[dict[str, Any]] = []
    status_counts: dict[str, int] = {}
    eligible_count = 0
    protected_count = 0
    for meta_path in _iter_live_meta_paths(store):
        meta = _read_json_dict(meta_path)
        if not meta or bool(meta.get("hidden")):
            continue
        if pid and _as_str(meta.get("projectId")).strip() != pid:
            continue
        row = _run_candidate_row(
            store,
            meta_path,
            meta,
            now_ts=now_ts,
            older_than_s=older_than_s,
            protected_run_ids=protected_ids,
        )
        status = str(row.get("status") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
        if bool(row.get("eligible")):
            eligible_count += 1
        if bool(row.get("protected")):
            protected_count += 1
        rows.append(row)
    rows.sort(key=lambda item: (0 if item.get("eligible") else 1, -int(item.get("age_s") or 0), str(item.get("run_id") or "")))
    return {
        "schema_version": "runstore.hot_summary.v1",
        "generated_at": _now_iso(),
        "project_id": pid,
        "older_than_s": int(max(0, older_than_s)),
        "limit": max(1, int(limit or 1)),
        "status_counts": status_counts,
        "eligible_count": eligible_count,
        "protected_count": protected_count,
        "runs": rows[: max(1, int(limit or 1))],
    }


def build_runstore_health(
    store: Any,
    *,
    project_id: str = "",
    older_than_s: float = 86400.0,
    protected_run_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    hot_summary = list_hot_run_candidates(
        store,
        project_id=project_id,
        older_than_s=older_than_s,
        limit=25,
        protected_run_ids=protected_run_ids,
    )
    runs_dir = Path(getattr(store, "runs_dir", Path()))
    hot_dir = Path(getattr(store, "hot_dir", runs_dir / "hot"))
    archive_dir = Path(getattr(store, "archive_dir", runs_dir / "archive"))
    hot_files = _dir_file_summary(hot_dir)
    return {
        "schema_version": "runstore.health.v1",
        "generated_at": _now_iso(),
        "project_id": _normalize_project_filter(project_id),
        "runs_dir": str(runs_dir),
        "hot": {
            **hot_files,
            "status_counts": hot_summary.get("status_counts") or {},
            "eligible_count": int(hot_summary.get("eligible_count") or 0),
            "protected_count": int(hot_summary.get("protected_count") or 0),
            "older_than_s": int(max(0, older_than_s)),
        },
        "archive": _archive_bucket_summary(archive_dir),
        "policy": {
            "cleanup_definition": "archive_terminal_runs_only",
            "delete_data": False,
            "move_attachments": False,
            "terminal_statuses": sorted(TERMINAL_STATUSES),
            "protected_statuses": sorted(PROTECTED_STATUSES),
        },
    }


def _archive_manifest_path(store: Any) -> Path:
    runs_dir = Path(getattr(store, "runs_dir", Path()))
    return runs_dir.parent / ".run" / "runstore-archive-manifest.jsonl"


def _append_archive_manifest(store: Any, manifest: dict[str, Any]) -> str:
    path = _archive_manifest_path(store)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(manifest, ensure_ascii=False) + "\n")
    except Exception:
        return ""
    return str(path)


def archive_terminal_runs(
    store: Any,
    *,
    older_than_s: float = 86400.0,
    limit: int = 500,
    dry_run: bool = True,
    project_id: str = "",
    protected_run_ids: Iterable[str] | None = None,
    actor: str = "api",
    reason: str = "",
) -> dict[str, Any]:
    protected_ids = _normalize_protected_run_ids(protected_run_ids)
    pid = _normalize_project_filter(project_id)
    candidate_payload = list_hot_run_candidates(
        store,
        project_id=pid,
        older_than_s=older_than_s,
        limit=max(1, int(limit or 1)),
        protected_run_ids=protected_ids,
    )
    rows = [dict(item) for item in candidate_payload.get("runs") or [] if bool(item.get("eligible"))]
    rows = rows[: max(1, int(limit or 1))]
    manifest_id = f"{int(time.time() * 1000)}-{len(rows)}"
    moved_count = 0
    skipped_count = 0
    error_count = 0
    for row in rows:
        run_id = _as_str(row.get("run_id")).strip()
        row["manifest_id"] = manifest_id
        row["dry_run"] = bool(dry_run)
        if not run_id:
            row["outcome"] = "skipped"
            row["skip_reason"] = "missing_run_id"
            skipped_count += 1
            continue
        if dry_run:
            row["outcome"] = "dry_run"
            continue
        src = store._paths(run_id)  # noqa: SLF001 - RunStore keeps path policy in one place.
        dst = store._archive_paths(run_id, str(row.get("bucket") or ""))  # noqa: SLF001
        existing_targets = [str(path) for key, path in dst.items() if src.get(key) is not None and src[key].exists() and path.exists()]
        if existing_targets:
            row["outcome"] = "skipped"
            row["skip_reason"] = "archive_target_exists"
            row["existing_targets"] = existing_targets
            skipped_count += 1
            continue
        moved: list[tuple[Path, Path]] = []
        try:
            dst["meta"].parent.mkdir(parents=True, exist_ok=True)
            for key in ("meta", "msg", "last", "log"):
                source_path = src[key]
                target_path = dst[key]
                if not source_path.exists():
                    continue
                source_path.replace(target_path)
                moved.append((source_path, target_path))
            remove_index = getattr(store, "_remove_live_run_index_entry", None)
            if callable(remove_index):
                remove_index(run_id)
            row["outcome"] = "moved"
            row["src_meta"] = str(src["meta"])
            row["dst_meta"] = str(dst["meta"])
            moved_count += 1
        except Exception as exc:
            for source_path, target_path in reversed(moved):
                try:
                    if target_path.exists() and not source_path.exists():
                        target_path.replace(source_path)
                except Exception:
                    pass
            row["outcome"] = "error"
            row["error"] = _as_str(exc)[:500]
            error_count += 1
    manifest = {
        "schema_version": "runstore.archive_manifest.v1",
        "manifest_id": manifest_id,
        "generated_at": _now_iso(),
        "actor": _as_str(actor).strip()[:120],
        "reason": _as_str(reason).strip()[:500],
        "dry_run": bool(dry_run),
        "project_id": pid,
        "older_than_s": int(max(0, older_than_s)),
        "limit": max(1, int(limit or 1)),
        "counts": {
            "planned": len(rows),
            "moved": moved_count,
            "skipped": skipped_count,
            "error": error_count,
        },
        "runs": rows,
    }
    manifest_path = _append_archive_manifest(store, manifest)
    return {
        "ok": error_count == 0,
        "schema_version": "runstore.archive_result.v1",
        "manifest_id": manifest_id,
        "manifest_path": manifest_path,
        "dry_run": bool(dry_run),
        "project_id": pid,
        "older_than_s": int(max(0, older_than_s)),
        "limit": max(1, int(limit or 1)),
        "counts": manifest["counts"],
        "runs": rows,
    }
