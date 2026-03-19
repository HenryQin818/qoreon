# -*- coding: utf-8 -*-

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Callable

from task_dashboard.runtime.execution_profiles import (
    normalize_execution_profile,
    resolve_execution_profile_permissions,
)


def _path_has_non_ascii(path: Path) -> bool:
    try:
        str(path).encode("ascii")
        return False
    except UnicodeEncodeError:
        return True


def _resolve_workspace_root(run_cwd: Path) -> tuple[Path, Path]:
    current = Path(run_cwd)
    try:
        current = current.resolve()
    except Exception:
        current = Path(run_cwd)
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            try:
                return candidate, current.relative_to(candidate)
            except Exception:
                return candidate, Path(".")
    return current, Path(".")


def _remove_mirror_child(child: Path) -> None:
    if child.is_dir() and not child.is_symlink():
        shutil.rmtree(child)
        return
    child.unlink(missing_ok=True)  # type: ignore[arg-type]


def _sync_mirror_directory(
    mirror_dir: Path,
    source_dir: Path,
    *,
    materialized_child: str = "",
) -> None:
    desired_names = {child.name for child in source_dir.iterdir()}
    for child in list(mirror_dir.iterdir()):
        if child.name == ".task_dashboard_source_root":
            continue
        if child.name not in desired_names:
            _remove_mirror_child(child)
            continue
        if child.name == materialized_child:
            if child.is_symlink() or (child.exists() and not child.is_dir()):
                _remove_mirror_child(child)
            continue
        source_child = source_dir / child.name
        if child.is_symlink():
            try:
                if child.resolve() == source_child.resolve():
                    continue
            except Exception:
                pass
            _remove_mirror_child(child)
        elif child.exists():
            continue
    for source_child in source_dir.iterdir():
        mirror_child = mirror_dir / source_child.name
        if source_child.name == materialized_child:
            mirror_child.mkdir(parents=True, exist_ok=True)
            continue
        if mirror_child.exists():
            continue
        mirror_child.symlink_to(source_child)


def _sync_ascii_workspace_mirror(
    mirror_root: Path,
    source_root: Path,
    *,
    relative_subpath: Path = Path("."),
) -> None:
    mirror_root.mkdir(parents=True, exist_ok=True)
    sentinel = mirror_root / ".task_dashboard_source_root"
    sentinel.write_text(str(source_root), encoding="utf-8")

    clean_parts = [part for part in relative_subpath.parts if part not in ("", ".")]
    current_mirror = mirror_root
    current_source = source_root

    if not clean_parts:
        _sync_mirror_directory(current_mirror, current_source)
        return

    for index, part in enumerate(clean_parts):
        _sync_mirror_directory(current_mirror, current_source, materialized_child=part)
        current_mirror = current_mirror / part
        current_source = current_source / part
        if not current_source.exists() or not current_source.is_dir():
            raise FileNotFoundError(f"workspace subpath missing for mirror: {current_source}")
        current_mirror.mkdir(parents=True, exist_ok=True)
        if index == len(clean_parts) - 1:
            _sync_mirror_directory(current_mirror, current_source)


def _prepend_path_entries(path_value: str, entries: list[str]) -> str:
    current = [item for item in str(path_value or "").split(os.pathsep) if item]
    prefix: list[str] = []
    for raw in entries:
        item = str(raw or "").strip()
        if not item or item in prefix:
            continue
        if item in current:
            current = [part for part in current if part != item]
        prefix.append(item)
    merged = prefix + current
    return os.pathsep.join(merged)


def _build_spawn_env(*, cli_type: str, cmd: list[str]) -> dict[str, str]:
    env = dict(os.environ)
    if str(cli_type or "").strip() != "codex":
        return env
    preferred_bins: list[str] = []
    if cmd:
        exe = Path(str(cmd[0] or "")).expanduser()
        if exe.is_absolute():
            parent = exe.parent
            if parent.exists():
                preferred_bins.append(str(parent))
    local_bin = (Path.home() / ".local" / "bin").expanduser()
    if local_bin.exists():
        preferred_bins.append(str(local_bin))
    if preferred_bins:
        env["PATH"] = _prepend_path_entries(env.get("PATH", ""), preferred_bins)
    return env


def _remove_flag(cmd: list[str], flag: str, *, takes_value: bool = False) -> list[str]:
    out: list[str] = []
    skip_next = False
    for item in cmd:
        if skip_next:
            skip_next = False
            continue
        if item == flag:
            if takes_value:
                skip_next = True
            continue
        out.append(item)
    return out


def _insert_after_exec(cmd: list[str], extra_args: list[str]) -> list[str]:
    if not extra_args:
        return list(cmd)
    out = list(cmd)
    try:
        exec_index = out.index("exec")
    except ValueError:
        exec_index = 0
    insert_at = exec_index + 1
    return out[:insert_at] + list(extra_args) + out[insert_at:]


def _augment_codex_command_for_execution_profile(
    cmd: list[str],
    *,
    execution_profile: str,
) -> list[str]:
    normalized_profile = normalize_execution_profile(execution_profile)
    if normalized_profile not in {"privileged", "project_privileged_full"}:
        return list(cmd)

    updated = list(cmd)
    updated = _remove_flag(updated, "--dangerously-bypass-approvals-and-sandbox")
    updated = _remove_flag(updated, "--full-auto")
    updated = _remove_flag(updated, "--sandbox", takes_value=True)
    updated = _remove_flag(updated, "-s", takes_value=True)
    while "--add-dir" in updated:
        updated = _remove_flag(updated, "--add-dir", takes_value=True)

    if normalized_profile == "project_privileged_full":
        return _insert_after_exec(
            updated,
            ["--dangerously-bypass-approvals-and-sandbox"],
        )

    permissions = resolve_execution_profile_permissions(normalized_profile)
    extra_args: list[str] = ["--sandbox", "workspace-write"]
    seen_roots: set[str] = set()
    for raw_root in list(permissions.get("writable_roots") or []):
        root = str(raw_root or "").strip()
        if not root or root in seen_roots:
            continue
        seen_roots.add(root)
        extra_args.extend(["--add-dir", root])
    return _insert_after_exec(updated, extra_args)


def prepare_process_spawn(
    *,
    cli_type: str,
    requested_cwd: Path,
    cmd: list[str],
    execution_profile: str = "sandboxed",
) -> dict[str, Any]:
    spawn_cwd = Path(requested_cwd)
    spawn_cmd = list(cmd)
    mode = "direct"
    mirrored_from = ""
    normalized_profile = normalize_execution_profile(execution_profile)
    if str(cli_type or "").strip() == "codex":
        spawn_cmd = _augment_codex_command_for_execution_profile(
            spawn_cmd,
            execution_profile=normalized_profile,
        )
    spawn_env = _build_spawn_env(cli_type=cli_type, cmd=spawn_cmd)
    if (
        str(cli_type or "").strip() == "codex"
        and normalized_profile == "sandboxed"
        and _path_has_non_ascii(spawn_cwd)
    ):
        source_root, relative_subpath = _resolve_workspace_root(spawn_cwd)
        digest = hashlib.sha1(str(source_root).encode("utf-8")).hexdigest()[:12]
        mirror_root = Path(tempfile.gettempdir()) / "task-dashboard-codex-runner" / digest
        _sync_ascii_workspace_mirror(
            mirror_root,
            source_root,
            relative_subpath=relative_subpath,
        )
        candidate_cwd = mirror_root / relative_subpath
        if candidate_cwd.exists() and candidate_cwd.is_dir():
            spawn_cwd = candidate_cwd
            mode = "codex_ascii_workspace_mirror"
            mirrored_from = str(source_root)
    return {
        "cmd": spawn_cmd,
        "spawn_cwd": spawn_cwd,
        "spawn_env": spawn_env,
        "mode": mode,
        "mirrored_from": mirrored_from,
        "execution_profile": normalized_profile,
    }


def build_execution_command(
    *,
    adapter_cls: Any,
    session_id: str,
    message: str,
    output_path: Path,
    profile_label: str,
    resolved_model: str,
    resolved_reasoning: str,
    cli_type: str,
    supports_model: bool,
    profile_not_found_recent: Callable[[str, str], tuple[bool, float]],
) -> dict[str, Any]:
    base_cmd = adapter_cls.build_resume_command(
        session_id=session_id,
        message=message,
        output_path=output_path,
        profile_label="",
        model=(resolved_model if supports_model else ""),
        reasoning_effort=(resolved_reasoning if cli_type == "codex" else ""),
    )
    cmd = list(base_cmd)
    profile_suppressed, profile_suppress_left_s = profile_not_found_recent(cli_type, profile_label)
    if profile_label and (not profile_suppressed):
        cmd = adapter_cls.build_resume_command(
            session_id=session_id,
            message=message,
            output_path=output_path,
            profile_label=profile_label,
            model=(resolved_model if supports_model else ""),
            reasoning_effort=(resolved_reasoning if cli_type == "codex" else ""),
        )
    return {
        "base_cmd": list(base_cmd),
        "cmd": list(cmd),
        "profile_suppressed": bool(profile_suppressed),
        "profile_suppress_left_s": float(profile_suppress_left_s or 0.0),
    }


def write_execution_log_header(
    logf: Any,
    *,
    meta: dict[str, Any],
    run_cwd: Path,
    spawn_cwd: Path,
    cmd: list[str],
    profile_label: str,
    profile_suppressed: bool,
    profile_suppress_left_s: float,
    spawn_mode: str = "direct",
    mirrored_from: str = "",
    execution_profile: str = "sandboxed",
) -> None:
    if str(meta.get("environment") or "").strip():
        logf.write(f"# environment: {meta.get('environment')}\n")
    if str(execution_profile or "").strip():
        logf.write(f"# execution_profile: {execution_profile}\n")
    if str(meta.get("worktree_root") or "").strip():
        logf.write(f"# worktree_root: {meta.get('worktree_root')}\n")
    logf.write(f"# workdir: {run_cwd}\n")
    if str(spawn_cwd) != str(run_cwd):
        logf.write(f"# spawn_cwd: {spawn_cwd}\n")
    if spawn_mode and spawn_mode != "direct":
        logf.write(f"# spawn_mode: {spawn_mode}\n")
    if mirrored_from:
        logf.write(f"# mirrored_from: {mirrored_from}\n")
    if str(meta.get("branch") or "").strip():
        logf.write(f"# branch: {meta.get('branch')}\n")
    logf.write(f"$ {' '.join(cmd)}\n\n")
    if profile_label and profile_suppressed:
        logf.write(
            f"[system] profile fallback suppressed ({int(profile_suppress_left_s)}s left), skip -p {profile_label}\n\n"
        )
    logf.flush()
