# -*- coding: utf-8 -*-
"""Controlled Claude Opus 5 SessionStore migration primitives."""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import subprocess
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator, Sequence

try:
    import fcntl
except ImportError:  # pragma: no cover - task-dashboard production is POSIX.
    fcntl = None  # type: ignore[assignment]

try:
    import tomllib
except ImportError:  # pragma: no cover - Python 3.11+ is required in production.
    tomllib = None  # type: ignore[assignment]

from task_dashboard.claude_models import DEFAULT_CLAUDE_MODEL, LEGACY_CLAUDE_OPUS_MODEL


MIGRATION_SCHEMA_VERSION = "claude-opus5-session-migration.v1"
MIGRATION_LOCK_NAME = "claude-opus5-migration.lock"
WORKING_RUN_STATUSES = {
    "queued",
    "retry_waiting",
    "running",
    "dispatching",
    "collecting",
    "scanning",
    "active",
    "finalizing",
}
ROLLBACK_RETRYABLE_JOURNAL_STATUSES = frozenset({"applied", "rollback_compensated"})


class ClaudeModelMigrationError(RuntimeError):
    """Base error carrying a stable code and diagnostics."""

    def __init__(self, code: str, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = str(code or "migration_error")
        self.details = dict(details or {})


class ClaudeModelMigrationBlocked(ClaudeModelMigrationError):
    """Raised when a migration safety stop line is not satisfied."""


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _sha256_path(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def migration_lock_path(runtime_root: Path) -> Path:
    return Path(runtime_root).expanduser().resolve() / ".locks" / MIGRATION_LOCK_NAME


@contextmanager
def claude_model_migration_lock(
    runtime_root: Path,
    *,
    exclusive: bool,
    timeout_s: float = 10.0,
) -> Iterator[Path]:
    """Acquire the cross-process migration read/write lock."""
    if fcntl is None:
        raise ClaudeModelMigrationBlocked(
            "migration_lock_unavailable",
            "POSIX flock is unavailable; refusing an unlocked Claude model write",
        )
    lock_path = migration_lock_path(runtime_root)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+", encoding="utf-8")
    operation = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
    deadline = time.monotonic() + max(0.0, float(timeout_s))
    try:
        while True:
            try:
                fcntl.flock(handle.fileno(), operation | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise ClaudeModelMigrationBlocked(
                        "migration_lock_timeout",
                        "timed out waiting for the Claude model migration lock",
                        details={"lock_path": str(lock_path), "exclusive": bool(exclusive)},
                    )
                time.sleep(0.05)
        yield lock_path
    finally:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ClaudeModelMigrationError(
            "invalid_json",
            f"failed to parse JSON: {path}",
            details={"path": str(path), "error": str(exc)},
        ) from exc
    if not isinstance(payload, dict):
        raise ClaudeModelMigrationError(
            "invalid_json_shape",
            f"expected a JSON object: {path}",
            details={"path": str(path)},
        )
    return payload


def _fsync_parent(path: Path) -> None:
    try:
        fd = os.open(str(path.parent), os.O_RDONLY)
    except Exception:
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _atomic_write_json(
    path: Path,
    payload: dict[str, Any],
    *,
    on_replaced: Callable[[], None] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp-{secrets.token_hex(6)}")
    encoded = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    try:
        with tmp.open("wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        if on_replaced is not None:
            on_replaced()
        _fsync_parent(path)
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass


def _project_file_ref(runtime_root: Path, path: Path) -> str:
    return str(path.resolve().relative_to(runtime_root.resolve()))


def _session_store_path(runtime_root: Path, file_ref: Any) -> Path:
    sessions_dir = (Path(runtime_root).expanduser().resolve() / ".sessions").resolve()
    path = (Path(runtime_root).expanduser().resolve() / _safe_text(file_ref)).resolve()
    if path.parent != sessions_dir or path.suffix.lower() != ".json":
        raise ClaudeModelMigrationBlocked(
            "manifest_session_path_invalid",
            "manifest project path must be a direct .sessions/*.json file",
            details={"file": _safe_text(file_ref), "resolved_path": str(path)},
        )
    return path


def _candidate_record(project_id: str, file_ref: str, row: dict[str, Any]) -> dict[str, Any]:
    return {
        "project_id": project_id,
        "file": file_ref,
        "session_id": _safe_text(row.get("id")),
        "channel_name": _safe_text(row.get("channel_name")),
        "status": _safe_text(row.get("status")),
        "is_primary": bool(row.get("is_primary")),
        "is_deleted": bool(row.get("is_deleted")),
        "before": LEGACY_CLAUDE_OPUS_MODEL,
        "after": DEFAULT_CLAUDE_MODEL,
    }


def _protected_record(project_id: str, file_ref: str, row: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "project_id": project_id,
        "file": file_ref,
        "session_id": _safe_text(row.get("id")),
        "channel_name": _safe_text(row.get("channel_name")),
        "model": _safe_text(row.get("model")),
        "is_deleted": bool(row.get("is_deleted")),
        "skip_reason": reason,
    }


def _scan_session_store(runtime_root: Path) -> dict[str, Any]:
    sessions_dir = runtime_root / ".sessions"
    candidates: list[dict[str, Any]] = []
    protected_rows: list[dict[str, Any]] = []
    project_entries: dict[str, dict[str, Any]] = {}
    totals = {
        "project_files": 0,
        "sessions": 0,
        "claude_sessions": 0,
        "claude_not_deleted": 0,
        "candidate_sessions": 0,
        "deleted_legacy_opus_skipped": 0,
        "other_claude_model_skipped": 0,
        "other_cli_skipped": 0,
    }
    errors: list[dict[str, str]] = []
    for path in sorted(sessions_dir.glob("*.json")):
        try:
            payload = _load_json_object(path)
        except ClaudeModelMigrationError as exc:
            errors.append({"path": str(path), "error": str(exc)})
            continue
        if "sessions" not in payload:
            continue
        rows = payload.get("sessions")
        if not isinstance(rows, list):
            errors.append({"path": str(path), "error": "sessions is not a list"})
            continue
        totals["project_files"] += 1
        project_id = _safe_text(payload.get("project_id")) or path.stem
        file_ref = _project_file_ref(runtime_root, path)
        file_candidates: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            totals["sessions"] += 1
            cli_type = _safe_text(row.get("cli_type") or "codex").lower()
            if cli_type != "claude":
                totals["other_cli_skipped"] += 1
                continue
            totals["claude_sessions"] += 1
            is_deleted = bool(row.get("is_deleted"))
            if not is_deleted:
                totals["claude_not_deleted"] += 1
            model = _safe_text(row.get("model"))
            if model == LEGACY_CLAUDE_OPUS_MODEL and not is_deleted:
                item = _candidate_record(project_id, file_ref, row)
                candidates.append(item)
                file_candidates.append(item)
                totals["candidate_sessions"] += 1
                continue
            if model == LEGACY_CLAUDE_OPUS_MODEL and is_deleted:
                reason = "deleted_legacy_opus"
                totals["deleted_legacy_opus_skipped"] += 1
            else:
                reason = "other_claude_model"
                totals["other_claude_model_skipped"] += 1
            protected_rows.append(_protected_record(project_id, file_ref, row, reason))
        if file_candidates:
            project_entries[file_ref] = {
                "project_id": project_id,
                "file": file_ref,
                "sha256_before": _sha256_path(path),
                "candidate_count": len(file_candidates),
                "session_ids": [item["session_id"] for item in file_candidates],
            }
    return {
        "totals": totals,
        "candidates": candidates,
        "protected_rows": protected_rows,
        "projects": list(project_entries.values()),
        "errors": errors,
    }


def _walk_config_models(
    node: Any,
    *,
    path: str = "$",
    inherited_cli_type: str = "",
) -> Iterator[dict[str, str]]:
    if isinstance(node, dict):
        cli_type = _safe_text(node.get("cli_type") or node.get("cliType") or inherited_cli_type).lower()
        if "model" in node and cli_type == "claude":
            yield {
                "path": f"{path}.model",
                "cli_type": cli_type,
                "model": _safe_text(node.get("model")),
            }
        for key, value in node.items():
            yield from _walk_config_models(
                value,
                path=f"{path}.{key}",
                inherited_cli_type=cli_type,
            )
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _walk_config_models(
                value,
                path=f"{path}[{index}]",
                inherited_cli_type=inherited_cli_type,
            )


def scan_config_models(config_paths: Sequence[Path]) -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    claude_models: list[dict[str, str]] = []
    errors: list[dict[str, str]] = []
    for raw_path in config_paths:
        path = Path(raw_path).expanduser().resolve()
        if not path.exists():
            files.append({"path": str(path), "exists": False, "sha256": ""})
            continue
        entry = {"path": str(path), "exists": True, "sha256": _sha256_path(path)}
        files.append(entry)
        if tomllib is None:
            errors.append({"path": str(path), "error": "tomllib unavailable"})
            continue
        try:
            payload = tomllib.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append({"path": str(path), "error": str(exc)})
            continue
        for item in _walk_config_models(payload):
            claude_models.append({"file": str(path), **item})
    legacy = [item for item in claude_models if item.get("model") == LEGACY_CLAUDE_OPUS_MODEL]
    return {
        "files": files,
        "claude_models": claude_models,
        "claude_model_count": len(claude_models),
        "legacy_opus_4_8_count": len(legacy),
        "legacy_opus_4_8": legacy,
        "errors": errors,
    }


def build_dry_run_manifest(
    runtime_root: Path,
    *,
    repo_root: Path,
    config_paths: Sequence[Path],
) -> dict[str, Any]:
    runtime = Path(runtime_root).expanduser().resolve()
    repo = Path(repo_root).expanduser().resolve()
    session_scan = _scan_session_store(runtime)
    config_scan = scan_config_models(config_paths)
    return {
        "schema_version": MIGRATION_SCHEMA_VERSION,
        "migration_id": "claude-opus5-" + datetime.now().strftime("%Y%m%d-%H%M%S"),
        "generated_at": _utc_now_iso(),
        "mode": "dry-run",
        "runtime_root": str(runtime),
        "repo_root": str(repo),
        "source_model": LEGACY_CLAUDE_OPUS_MODEL,
        "target_model": DEFAULT_CLAUDE_MODEL,
        "session_scan": session_scan,
        "config_scan": config_scan,
        "apply_allowed": not session_scan["errors"] and not config_scan["errors"] and not config_scan["legacy_opus_4_8"],
    }


def write_manifest(path: Path, manifest: dict[str, Any]) -> Path:
    target = Path(path).expanduser().resolve()
    _atomic_write_json(target, manifest)
    return target


def load_manifest(path: Path) -> dict[str, Any]:
    manifest = _load_json_object(Path(path).expanduser().resolve())
    if manifest.get("schema_version") != MIGRATION_SCHEMA_VERSION:
        raise ClaudeModelMigrationError(
            "manifest_schema_mismatch",
            "unsupported Claude model migration manifest",
            details={"schema_version": manifest.get("schema_version")},
        )
    if manifest.get("source_model") != LEGACY_CLAUDE_OPUS_MODEL:
        raise ClaudeModelMigrationError("manifest_source_mismatch", "manifest source model mismatch")
    if manifest.get("target_model") != DEFAULT_CLAUDE_MODEL:
        raise ClaudeModelMigrationError("manifest_target_mismatch", "manifest target model mismatch")
    if manifest.get("mode") != "dry-run":
        raise ClaudeModelMigrationError("manifest_mode_mismatch", "migration manifest must originate from dry-run")
    return manifest


def _runtime_root_from_manifest(manifest: dict[str, Any]) -> Path:
    runtime = Path(_safe_text(manifest.get("runtime_root"))).expanduser().resolve()
    if not runtime.is_dir():
        raise ClaudeModelMigrationError(
            "runtime_root_missing",
            "manifest runtime root does not exist",
            details={"runtime_root": str(runtime)},
        )
    return runtime


def _candidate_session_ids(manifest: dict[str, Any]) -> set[str]:
    scan = manifest.get("session_scan") if isinstance(manifest.get("session_scan"), dict) else {}
    return {
        _safe_text(item.get("session_id"))
        for item in (scan.get("candidates") or [])
        if isinstance(item, dict) and _safe_text(item.get("session_id"))
    }


def _iter_live_run_meta(runtime_root: Path) -> Iterator[dict[str, Any]]:
    runs_dir = runtime_root / ".runs"
    paths = list((runs_dir / "hot").glob("*.json")) + list(runs_dir.glob("*.json"))
    seen: set[str] = set()
    for path in paths:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        run_id = _safe_text(payload.get("id")) or path.stem
        if run_id in seen:
            continue
        seen.add(run_id)
        yield payload


def _scan_process_table() -> tuple[list[tuple[int, str]], str]:
    try:
        env = dict(os.environ)
        env["LC_ALL"] = "C"
        proc = subprocess.run(
            ["ps", "-axww", "-o", "pid=,command="],
            capture_output=True,
            text=True,
            timeout=3.0,
            env=env,
            check=False,
        )
    except Exception as exc:
        return [], str(exc)
    if proc.returncode != 0:
        return [], _safe_text(proc.stderr) or f"ps exited {proc.returncode}"
    rows: list[tuple[int, str]] = []
    for line in proc.stdout.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) != 2:
            continue
        try:
            pid = int(parts[0])
        except ValueError:
            continue
        if pid == os.getpid():
            continue
        rows.append((pid, parts[1]))
    return rows, ""


def inspect_runtime_stop_line(runtime_root: Path, session_ids: set[str]) -> dict[str, Any]:
    working_runs = []
    for meta in _iter_live_run_meta(runtime_root):
        if _safe_text(meta.get("cliType") or meta.get("cli_type")).lower() != "claude":
            continue
        status = _safe_text(meta.get("status")).lower()
        if status not in WORKING_RUN_STATUSES:
            continue
        working_runs.append(
            {
                "run_id": _safe_text(meta.get("id")),
                "session_id": _safe_text(meta.get("sessionId") or meta.get("session_id")),
                "status": status,
            }
        )
    process_rows, process_scan_error = _scan_process_table()
    external_busy = []
    for session_id in sorted(session_ids):
        escaped = re.escape(session_id)
        resume_pattern = re.compile(rf"(?:^|\s)--resume(?:=|\s+){escaped}(?:\s|$)")
        for pid, command in process_rows:
            if not resume_pattern.search(command.replace("\\012", " ")):
                continue
            if "claude_runner" not in command and not re.search(r"(?:^|/|\s)claude(?:\s|$)", command):
                continue
            external_busy.append({"session_id": session_id, "pid": pid})
    blocked = bool(working_runs or external_busy or process_scan_error)
    return {
        "blocked": blocked,
        "working_runs": working_runs,
        "external_busy": external_busy,
        "process_scan_error": process_scan_error,
        "checked_at": _utc_now_iso(),
    }


def _validate_config_cas(manifest: dict[str, Any]) -> None:
    config_scan = manifest.get("config_scan") if isinstance(manifest.get("config_scan"), dict) else {}
    if config_scan.get("errors"):
        raise ClaudeModelMigrationBlocked(
            "config_scan_error",
            "manifest contains config scan errors",
            details={"errors": config_scan.get("errors")},
        )
    if int(config_scan.get("legacy_opus_4_8_count") or 0) > 0:
        raise ClaudeModelMigrationBlocked(
            "config_legacy_model_present",
            "Claude Opus 4.8 remains explicitly configured",
            details={"matches": config_scan.get("legacy_opus_4_8")},
        )
    mismatches = []
    for item in config_scan.get("files") or []:
        if not isinstance(item, dict):
            continue
        path = Path(_safe_text(item.get("path")))
        expected_exists = bool(item.get("exists"))
        actual_exists = path.exists()
        actual = _sha256_path(path) if actual_exists else ""
        expected = _safe_text(item.get("sha256"))
        if actual_exists != expected_exists or actual != expected:
            mismatches.append(
                {
                    "path": str(path),
                    "expected_exists": expected_exists,
                    "actual_exists": actual_exists,
                    "expected": expected,
                    "actual": actual,
                }
            )
    if mismatches:
        raise ClaudeModelMigrationBlocked(
            "config_cas_mismatch",
            "configuration changed after dry-run; generate a new manifest",
            details={"mismatches": mismatches},
        )


def _manifest_projects(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    scan = manifest.get("session_scan") if isinstance(manifest.get("session_scan"), dict) else {}
    return [dict(item) for item in (scan.get("projects") or []) if isinstance(item, dict)]


def _validate_project_cas(runtime_root: Path, projects: Sequence[dict[str, Any]], hash_key: str) -> None:
    mismatches = []
    for item in projects:
        path = _session_store_path(runtime_root, item.get("file"))
        actual = _sha256_path(path) if path.exists() else ""
        expected = _safe_text(item.get(hash_key))
        if actual != expected:
            mismatches.append({"path": str(path), "expected": expected, "actual": actual})
    if mismatches:
        raise ClaudeModelMigrationBlocked(
            "session_store_cas_mismatch",
            "SessionStore changed after the migration checkpoint",
            details={"mismatches": mismatches},
        )


def _journal_path(manifest_path: Path) -> Path:
    path = Path(manifest_path).expanduser().resolve()
    return path.with_name(path.stem + ".journal.json")


def _load_optional_journal(manifest_path: Path) -> dict[str, Any]:
    path = _journal_path(manifest_path)
    return _load_json_object(path) if path.exists() else {}


def _candidate_map_for_file(manifest: dict[str, Any], file_ref: str) -> dict[str, dict[str, Any]]:
    scan = manifest.get("session_scan") if isinstance(manifest.get("session_scan"), dict) else {}
    return {
        _safe_text(item.get("session_id")): dict(item)
        for item in (scan.get("candidates") or [])
        if isinstance(item, dict)
        and _safe_text(item.get("file")) == file_ref
        and _safe_text(item.get("session_id"))
    }


def _rewrite_candidate_models(
    path: Path,
    candidate_map: dict[str, dict[str, Any]],
    *,
    expected_model: str,
    target_model: str,
    on_replaced: Callable[[], None] | None = None,
) -> None:
    payload = _load_json_object(path)
    rows = payload.get("sessions")
    if not isinstance(rows, list):
        raise ClaudeModelMigrationError("invalid_session_store", f"sessions is not a list: {path}")
    found: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        session_id = _safe_text(row.get("id"))
        if session_id not in candidate_map:
            continue
        found.add(session_id)
        if _safe_text(row.get("cli_type")).lower() != "claude" or bool(row.get("is_deleted")):
            raise ClaudeModelMigrationBlocked(
                "candidate_scope_changed",
                "candidate no longer satisfies the migration scope",
                details={"path": str(path), "session_id": session_id},
            )
        current_model = _safe_text(row.get("model"))
        if current_model != expected_model:
            raise ClaudeModelMigrationBlocked(
                "candidate_value_changed",
                "candidate model changed after the migration checkpoint",
                details={
                    "path": str(path),
                    "session_id": session_id,
                    "expected": expected_model,
                    "actual": current_model,
                },
            )
        row["model"] = target_model
    missing = sorted(set(candidate_map) - found)
    if missing:
        raise ClaudeModelMigrationBlocked(
            "candidate_missing",
            "candidate sessions are missing from SessionStore",
            details={"path": str(path), "session_ids": missing},
        )
    _atomic_write_json(path, payload, on_replaced=on_replaced)


def _compensate_projects(
    runtime_root: Path,
    manifest: dict[str, Any],
    completed: Sequence[dict[str, Any]],
    *,
    expected_model: str,
    target_model: str,
) -> list[dict[str, Any]]:
    failures = []
    for item in reversed(list(completed)):
        file_ref = _safe_text(item.get("file"))
        path = _session_store_path(runtime_root, file_ref)
        try:
            _rewrite_candidate_models(
                path,
                _candidate_map_for_file(manifest, file_ref),
                expected_model=expected_model,
                target_model=target_model,
            )
        except Exception as exc:
            failures.append({"file": file_ref, "error": str(exc)})
    return failures


def _verify_compensation_state(
    manifest_file: Path,
    *,
    expected_state: str,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    try:
        return (
            verify_manifest(
                manifest_file,
                _lock_held=True,
                expected_state=expected_state,
            ),
            None,
        )
    except Exception as exc:
        return (
            {},
            {
                "stage": "compensation_verification",
                "error": str(exc),
            },
        )


def apply_manifest(manifest_path: Path) -> dict[str, Any]:
    manifest_file = Path(manifest_path).expanduser().resolve()
    manifest = load_manifest(manifest_file)
    runtime_root = _runtime_root_from_manifest(manifest)
    projects = _manifest_projects(manifest)
    if manifest.get("session_scan", {}).get("errors"):
        raise ClaudeModelMigrationBlocked("session_scan_error", "manifest contains SessionStore scan errors")
    completed: list[dict[str, Any]] = []
    journal = {
        "schema_version": MIGRATION_SCHEMA_VERSION,
        "migration_id": manifest.get("migration_id"),
        "operation": "apply",
        "status": "started",
        "started_at": _utc_now_iso(),
        "projects": [],
    }
    with claude_model_migration_lock(runtime_root, exclusive=True, timeout_s=30.0):
        stop_line = inspect_runtime_stop_line(runtime_root, _candidate_session_ids(manifest))
        if stop_line["blocked"]:
            raise ClaudeModelMigrationBlocked(
                "runtime_busy",
                "Claude runs or external processes are active",
                details=stop_line,
            )
        _validate_config_cas(manifest)
        _validate_project_cas(runtime_root, projects, "sha256_before")
        write_manifest(_journal_path(manifest_file), journal)
        try:
            for project in projects:
                file_ref = _safe_text(project.get("file"))
                path = _session_store_path(runtime_root, file_ref)
                completed_item = {
                    "project_id": project.get("project_id"),
                    "file": file_ref,
                    "sha256_before": project.get("sha256_before"),
                    "candidate_count": project.get("candidate_count"),
                }
                _rewrite_candidate_models(
                    path,
                    _candidate_map_for_file(manifest, file_ref),
                    expected_model=LEGACY_CLAUDE_OPUS_MODEL,
                    target_model=DEFAULT_CLAUDE_MODEL,
                    on_replaced=lambda item=completed_item: completed.append(item),
                )
                completed_item["sha256_after"] = _sha256_path(path)
                journal["projects"] = list(completed)
                write_manifest(_journal_path(manifest_file), journal)
            verification = verify_manifest(manifest_file, _lock_held=True, expected_state="applied")
            journal.update(
                {
                    "status": "applied",
                    "finished_at": _utc_now_iso(),
                    "verification": verification,
                }
            )
            write_manifest(_journal_path(manifest_file), journal)
            return journal
        except Exception as exc:
            compensation_failures = _compensate_projects(
                runtime_root,
                manifest,
                completed,
                expected_model=DEFAULT_CLAUDE_MODEL,
                target_model=LEGACY_CLAUDE_OPUS_MODEL,
            )
            compensation_verification: dict[str, Any] = {}
            if not compensation_failures:
                compensation_verification, verification_failure = _verify_compensation_state(
                    manifest_file,
                    expected_state="compensated",
                )
                if verification_failure:
                    compensation_failures.append(verification_failure)
            journal.update(
                {
                    "status": "compensated" if not compensation_failures else "compensation_failed",
                    "finished_at": _utc_now_iso(),
                    "error": str(exc),
                    "compensation_failures": compensation_failures,
                    "compensation_verification": compensation_verification,
                }
            )
            write_manifest(_journal_path(manifest_file), journal)
            raise


def _verify_candidate_state(
    runtime_root: Path,
    manifest: dict[str, Any],
    *,
    expected_model: str,
) -> list[dict[str, Any]]:
    mismatches = []
    for project in _manifest_projects(manifest):
        file_ref = _safe_text(project.get("file"))
        payload = _load_json_object(_session_store_path(runtime_root, file_ref))
        rows = {
            _safe_text(row.get("id")): row
            for row in (payload.get("sessions") or [])
            if isinstance(row, dict) and _safe_text(row.get("id"))
        }
        for session_id in _candidate_map_for_file(manifest, file_ref):
            row = rows.get(session_id)
            actual = _safe_text((row or {}).get("model"))
            if actual != expected_model:
                mismatches.append(
                    {
                        "file": file_ref,
                        "session_id": session_id,
                        "expected": expected_model,
                        "actual": actual,
                    }
                )
    return mismatches


def _verify_protected_rows(runtime_root: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    scan = manifest.get("session_scan") if isinstance(manifest.get("session_scan"), dict) else {}
    by_file: dict[str, list[dict[str, Any]]] = {}
    for item in scan.get("protected_rows") or []:
        if isinstance(item, dict):
            by_file.setdefault(_safe_text(item.get("file")), []).append(item)
    mismatches = []
    for file_ref, expected_rows in by_file.items():
        payload = _load_json_object(_session_store_path(runtime_root, file_ref))
        rows = {
            _safe_text(row.get("id")): row
            for row in (payload.get("sessions") or [])
            if isinstance(row, dict) and _safe_text(row.get("id"))
        }
        for expected in expected_rows:
            session_id = _safe_text(expected.get("session_id"))
            row = rows.get(session_id)
            actual = _safe_text((row or {}).get("model"))
            if actual != _safe_text(expected.get("model")):
                mismatches.append(
                    {
                        "file": file_ref,
                        "session_id": session_id,
                        "expected": expected.get("model"),
                        "actual": actual,
                        "skip_reason": expected.get("skip_reason"),
                    }
                )
    return mismatches


def verify_manifest(
    manifest_path: Path,
    *,
    _lock_held: bool = False,
    expected_state: str = "",
) -> dict[str, Any]:
    manifest_file = Path(manifest_path).expanduser().resolve()
    manifest = load_manifest(manifest_file)
    runtime_root = _runtime_root_from_manifest(manifest)
    journal = _load_optional_journal(manifest_file)
    state = expected_state or _safe_text(journal.get("status"))
    expected_model = (
        LEGACY_CLAUDE_OPUS_MODEL
        if state in {"rolled_back", "compensated"}
        else DEFAULT_CLAUDE_MODEL
    )

    def _run() -> dict[str, Any]:
        candidate_mismatches = _verify_candidate_state(
            runtime_root,
            manifest,
            expected_model=expected_model,
        )
        protected_mismatches = _verify_protected_rows(runtime_root, manifest)
        rescan = _scan_session_store(runtime_root)
        remaining_active_legacy = int(rescan["totals"]["candidate_sessions"])
        expected_remaining = len(_candidate_session_ids(manifest)) if expected_model == LEGACY_CLAUDE_OPUS_MODEL else 0
        count_matches = remaining_active_legacy == expected_remaining
        return {
            "ok": not candidate_mismatches and not protected_mismatches and count_matches,
            "expected_state": state or "applied",
            "expected_model": expected_model,
            "candidate_mismatches": candidate_mismatches,
            "protected_mismatches": protected_mismatches,
            "remaining_active_legacy_opus_4_8": remaining_active_legacy,
            "expected_remaining_active_legacy_opus_4_8": expected_remaining,
            "checked_at": _utc_now_iso(),
        }

    if _lock_held:
        result = _run()
    else:
        with claude_model_migration_lock(runtime_root, exclusive=True, timeout_s=10.0):
            result = _run()
    if not result["ok"]:
        raise ClaudeModelMigrationError(
            "migration_verify_failed",
            "Claude model migration verification failed",
            details=result,
        )
    return result


def rollback_manifest(manifest_path: Path) -> dict[str, Any]:
    manifest_file = Path(manifest_path).expanduser().resolve()
    manifest = load_manifest(manifest_file)
    runtime_root = _runtime_root_from_manifest(manifest)
    journal = _load_optional_journal(manifest_file)
    journal_status = _safe_text(journal.get("status"))
    if journal_status not in ROLLBACK_RETRYABLE_JOURNAL_STATUSES:
        raise ClaudeModelMigrationBlocked(
            "rollback_state_invalid",
            "rollback requires an applied or rollback-compensated migration journal",
            details={
                "journal_status": journal_status,
                "retryable_statuses": sorted(ROLLBACK_RETRYABLE_JOURNAL_STATUSES),
            },
        )
    applied_projects = [dict(item) for item in (journal.get("projects") or []) if isinstance(item, dict)]
    completed: list[dict[str, Any]] = []
    rollback_journal = dict(journal)
    for stale_key in (
        "rollback_projects",
        "rollback_finished_at",
        "rollback_verification",
        "rollback_error",
        "rollback_compensation_failures",
        "rollback_compensation_verification",
    ):
        rollback_journal.pop(stale_key, None)
    rollback_journal.update(
        {
            "operation": "rollback",
            "status": "rollback_started",
            "rollback_started_at": _utc_now_iso(),
            "rollback_attempt": int(journal.get("rollback_attempt") or 0) + 1,
        }
    )
    with claude_model_migration_lock(runtime_root, exclusive=True, timeout_s=30.0):
        stop_line = inspect_runtime_stop_line(runtime_root, _candidate_session_ids(manifest))
        if stop_line["blocked"]:
            raise ClaudeModelMigrationBlocked(
                "runtime_busy",
                "Claude runs or external processes are active",
                details=stop_line,
            )
        _validate_project_cas(runtime_root, applied_projects, "sha256_after")
        write_manifest(_journal_path(manifest_file), rollback_journal)
        try:
            for project in applied_projects:
                file_ref = _safe_text(project.get("file"))
                path = _session_store_path(runtime_root, file_ref)
                completed_item = dict(project)
                _rewrite_candidate_models(
                    path,
                    _candidate_map_for_file(manifest, file_ref),
                    expected_model=DEFAULT_CLAUDE_MODEL,
                    target_model=LEGACY_CLAUDE_OPUS_MODEL,
                    on_replaced=lambda item=completed_item: completed.append(item),
                )
                completed_item["sha256_rollback"] = _sha256_path(path)
                rollback_journal["rollback_projects"] = list(completed)
                write_manifest(_journal_path(manifest_file), rollback_journal)
            verification = verify_manifest(manifest_file, _lock_held=True, expected_state="rolled_back")
            rollback_journal.update(
                {
                    "status": "rolled_back",
                    "rollback_finished_at": _utc_now_iso(),
                    "rollback_verification": verification,
                }
            )
            write_manifest(_journal_path(manifest_file), rollback_journal)
            return rollback_journal
        except Exception as exc:
            compensation_failures = _compensate_projects(
                runtime_root,
                manifest,
                completed,
                expected_model=LEGACY_CLAUDE_OPUS_MODEL,
                target_model=DEFAULT_CLAUDE_MODEL,
            )
            rollback_compensation_verification: dict[str, Any] = {}
            if not compensation_failures:
                (
                    rollback_compensation_verification,
                    verification_failure,
                ) = _verify_compensation_state(
                    manifest_file,
                    expected_state="rollback_compensated",
                )
                if verification_failure:
                    compensation_failures.append(verification_failure)
            rollback_journal.update(
                {
                    "status": "rollback_compensated" if not compensation_failures else "rollback_compensation_failed",
                    "rollback_finished_at": _utc_now_iso(),
                    "rollback_error": str(exc),
                    "rollback_compensation_failures": compensation_failures,
                    "rollback_compensation_verification": rollback_compensation_verification,
                }
            )
            write_manifest(_journal_path(manifest_file), rollback_journal)
            raise
