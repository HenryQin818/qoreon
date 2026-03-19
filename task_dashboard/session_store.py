# -*- coding: utf-8 -*-
"""
Session store for managing CLI session bindings.

Storage format: .sessions/{project_id}.json
{
  "project_id": "xxx",
  "sessions": [
    {
      "id": "uuid",
      "cli_type": "codex",
      "model": "codex-spark",
      "alias": "",
      "channel_name": "channel-name",
      "status": "active",
      "created_at": "ISO timestamp",
      "last_used_at": "ISO timestamp"
    }
  ]
}

`status` is kept only as a legacy compatibility field. Runtime routing,
reuse, and primary-session fallback must use `is_deleted/is_primary`
instead of this field.
"""

from __future__ import annotations

import json
import os
import secrets
import time
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from task_dashboard.runtime.project_execution_context import (
    build_context_override_values,
    normalize_project_execution_context,
)


def _utc_now_iso() -> str:
    """Return current UTC time in ISO format with timezone."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _atomic_write_text(path: Path, content: str) -> None:
    """Atomically write content to a file to avoid data corruption."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp-{secrets.token_hex(6)}")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)


def _normalize_reasoning_effort_value(value: Any) -> str:
    txt = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "xhigh": "extra_high",
        "very_high": "extra_high",
        "ultra": "extra_high",
        "extra": "extra_high",
    }
    txt = aliases.get(txt, txt)
    if txt in {"low", "medium", "high", "extra_high"}:
        return txt
    return ""


def session_binding_is_available(session: Any) -> bool:
    row = session if isinstance(session, dict) else {}
    return bool(str(row.get("id") or "").strip()) and not bool(row.get("is_deleted"))


def session_binding_sort_key(session: Any) -> tuple[int, str, str, str]:
    row = session if isinstance(session, dict) else {}
    return (
        1 if bool(row.get("is_primary")) and session_binding_is_available(row) else 0,
        str(row.get("last_used_at") or ""),
        str(row.get("created_at") or ""),
        str(row.get("id") or ""),
    )


class SessionStore:
    """
    Persistent session binding store for managing CLI sessions per project/channel.

    Each project has its own JSON file under .sessions/{project_id}.json.
    """

    def __init__(self, base_dir: Path) -> None:
        """
        Initialize the session store.

        Args:
            base_dir: The parent directory where .sessions folder will be created.
        """
        self.sessions_dir = base_dir / ".sessions"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

    def _project_path(self, project_id: str) -> Path:
        """Get the path to a project's session file."""
        # Sanitize project_id to avoid path traversal
        safe_id = project_id.replace("/", "_").replace("\\", "_").replace("..", "_")
        return self.sessions_dir / f"{safe_id}.json"

    def _load_project_data(self, project_id: str) -> dict[str, Any]:
        """Load project session data from file, return empty structure if not exists."""
        path = self._project_path(project_id)
        if not path.exists():
            return {"project_id": project_id, "sessions": []}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return {"project_id": project_id, "sessions": []}
            data, changed = self._normalize_project_data(project_id, data)
            if changed:
                self._save_project_data(project_id, data)
            return data
        except (json.JSONDecodeError, Exception):
            return {"project_id": project_id, "sessions": []}

    def _save_project_data(self, project_id: str, data: dict[str, Any]) -> None:
        """Save project session data to file atomically."""
        path = self._project_path(project_id)
        data["project_id"] = project_id
        _atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2))

    def _apply_project_context_storage_semantics_to_normalized(self, row: dict[str, Any]) -> dict[str, Any]:
        context = row.get("project_execution_context")
        if not isinstance(context, dict) or not context:
            return row
        override_values, _override_fields = build_context_override_values(
            context,
            fallback_target=row,
        )
        for key, value in override_values.items():
            row[key] = str(value or "").strip()
        return row

    def _normalize_project_data(self, project_id: str, data: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        out = deepcopy(data if isinstance(data, dict) else {})
        normalized_project_id = str(out.get("project_id") or project_id or "").strip() or project_id
        changed = str(out.get("project_id") or "") != normalized_project_id
        out["project_id"] = normalized_project_id
        raw_sessions = out.get("sessions")
        if not isinstance(raw_sessions, list):
            raw_sessions = []
            changed = True
        normalized_sessions: list[dict[str, Any]] = []
        for session in raw_sessions:
            if not isinstance(session, dict):
                changed = True
                continue
            normalized = self._normalize_session_record(session)
            if normalized != session:
                changed = True
            normalized_sessions.append(normalized)
        if normalized_sessions != raw_sessions:
            changed = True
        out["sessions"] = normalized_sessions
        return out, changed

    def _normalize_session_record(self, session: dict[str, Any]) -> dict[str, Any]:
        """Normalize additive session fields for backward compatibility."""
        out = deepcopy(session if isinstance(session, dict) else {})
        out["status"] = str(out.get("status") or "").strip() or "active"
        out["is_primary"] = bool(out.get("is_primary"))
        out["is_deleted"] = bool(out.get("is_deleted"))
        out["deleted_at"] = str(out.get("deleted_at") or "").strip()
        out["deleted_reason"] = str(out.get("deleted_reason") or "").strip()
        out["environment"] = str(out.get("environment") or "").strip()
        out["worktree_root"] = str(out.get("worktree_root") or "").strip()
        out["workdir"] = str(out.get("workdir") or "").strip()
        out["branch"] = str(out.get("branch") or "").strip()
        session_role = str(out.get("session_role") or "").strip().lower()
        if session_role not in {"primary", "child"}:
            session_role = "primary" if bool(out.get("is_primary")) else "child"
        out["session_role"] = session_role
        out["purpose"] = str(out.get("purpose") or "").strip()
        out["reuse_strategy"] = str(out.get("reuse_strategy") or "").strip()
        out["schema_version"] = str(out.get("schema_version") or "").strip()
        out["created_via"] = str(out.get("created_via") or "").strip()
        out["context_binding_state"] = str(out.get("context_binding_state") or "").strip().lower()
        project_execution_context = out.get("project_execution_context")
        out["project_execution_context"] = (
            normalize_project_execution_context(project_execution_context, fallback_target=out)
            if isinstance(project_execution_context, dict)
            else {}
        )
        out["reasoning_effort"] = _normalize_reasoning_effort_value(out.get("reasoning_effort"))
        return self._apply_project_context_storage_semantics_to_normalized(out)

    def _apply_project_context_storage_semantics(self, session: dict[str, Any]) -> dict[str, Any]:
        return self._normalize_session_record(session)

    def list_sessions(
        self,
        project_id: str,
        channel_name: str | None = None,
        *,
        include_deleted: bool = False,
    ) -> list[dict[str, Any]]:
        """
        List sessions for a project, optionally filtered by channel name.

        Args:
            project_id: The project identifier.
            channel_name: Optional channel name to filter by.

        Returns:
            List of session dictionaries.
        """
        data = self._load_project_data(project_id)
        sessions = [self._normalize_session_record(s) for s in data.get("sessions", []) if isinstance(s, dict)]
        if channel_name:
            sessions = [s for s in sessions if s.get("channel_name") == channel_name]
        if not include_deleted:
            sessions = [s for s in sessions if not bool(s.get("is_deleted"))]
        for session in sessions:
            session["project_id"] = project_id
        return sessions

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        """
        Get a single session by its ID.

        Args:
            session_id: The session identifier (UUID).

        Returns:
            Session dictionary or None if not found.
        """
        # Need to search across all project files
        for path in self.sessions_dir.glob("*.json"):
            try:
                data = self._load_project_data(path.stem)
                project_id = str(data.get("project_id") or path.stem)
                sessions = data.get("sessions", [])
                for session in sessions:
                    if session.get("id") == session_id:
                        out = self._normalize_session_record(session)
                        out["project_id"] = project_id
                        return out
            except Exception:
                continue
        return None

    def create_session(
        self,
        project_id: str,
        channel_name: str,
        cli_type: str = "codex",
        alias: str = "",
        session_id: str = "",
        model: str = "",
        reasoning_effort: str = "",
        environment: str = "",
        worktree_root: str = "",
        workdir: str = "",
        branch: str = "",
        session_role: str = "",
        purpose: str = "",
        reuse_strategy: str = "",
        schema_version: str = "",
        created_via: str = "",
        context_binding_state: str = "",
        project_execution_context: Optional[dict[str, Any]] = None,
        is_primary: Optional[bool] = None,
    ) -> dict[str, Any]:
        """
        Create a new session for a project/channel.

        Args:
            project_id: The project identifier.
            channel_name: The channel name.
            cli_type: The CLI type (default: "codex").
            alias: Optional alias for the session.
            session_id: Optional external session ID. If empty, generate UUID.
            model: Optional model identifier for this session.

        Returns:
            The created session dictionary.
        """
        now = _utc_now_iso()
        sid = str(session_id or "").strip() or str(uuid.uuid4())
        existing = self.list_sessions(project_id, channel_name, include_deleted=True)
        existing_active = [item for item in existing if not bool(item.get("is_deleted"))]
        effective_primary = is_primary if isinstance(is_primary, bool) else (not existing_active)
        normalized_role = "primary" if effective_primary else "child"
        session = {
            "id": sid,
            "cli_type": cli_type or "codex",
            "alias": alias or "",
            "model": str(model or "").strip(),
            "reasoning_effort": _normalize_reasoning_effort_value(reasoning_effort),
            "environment": str(environment or "").strip(),
            "worktree_root": str(worktree_root or "").strip(),
            "workdir": str(workdir or "").strip(),
            "branch": str(branch or "").strip(),
            "session_role": normalized_role,
            "purpose": str(purpose or "").strip(),
            "reuse_strategy": str(reuse_strategy or "").strip(),
            "schema_version": str(schema_version or "").strip(),
            "created_via": str(created_via or "").strip(),
            "context_binding_state": str(context_binding_state or "").strip().lower(),
            "project_execution_context": deepcopy(project_execution_context) if isinstance(project_execution_context, dict) else {},
            "channel_name": channel_name,
            "status": "active",
            "is_primary": bool(effective_primary),
            "is_deleted": False,
            "deleted_at": "",
            "deleted_reason": "",
            "created_at": now,
            "last_used_at": now,
        }
        session = self._apply_project_context_storage_semantics(session)

        data = self._load_project_data(project_id)
        if bool(effective_primary):
            normalized_sessions: list[dict[str, Any]] = []
            for row in data.get("sessions", []):
                if not isinstance(row, dict):
                    continue
                next_row = self._normalize_session_record(row)
                if (
                    str(next_row.get("channel_name") or "") == channel_name
                    and not bool(next_row.get("is_deleted"))
                ):
                    next_row["is_primary"] = False
                normalized_sessions.append(next_row)
            data["sessions"] = normalized_sessions
        data["sessions"].append(session)
        self._save_project_data(project_id, data)

        return session

    def attach_existing_session(
        self,
        project_id: str,
        channel_name: str,
        *,
        session_id: str,
        cli_type: str = "codex",
        alias: str = "",
        model: str = "",
        reasoning_effort: str = "",
        environment: str = "",
        worktree_root: str = "",
        workdir: str = "",
        branch: str = "",
        session_role: str = "",
        purpose: str = "",
        reuse_strategy: str = "",
        schema_version: str = "",
        created_via: str = "",
        context_binding_state: str = "",
        project_execution_context: Optional[dict[str, Any]] = None,
        is_primary: Optional[bool] = None,
    ) -> tuple[dict[str, Any], bool]:
        """
        Attach an existing external session id into the runtime session store.

        Returns:
            (session, imported)
            imported=True when the session did not previously exist in SessionStore.
        """
        sid = str(session_id or "").strip()
        if not sid:
            raise ValueError("missing session_id")
        existing = self.get_session(sid)
        if existing:
            existing_project_id = str(existing.get("project_id") or "").strip()
            if existing_project_id and existing_project_id != project_id:
                raise ValueError("session already belongs to another project")
            update_fields: dict[str, Any] = {
                "channel_name": channel_name,
                "is_deleted": False,
                "deleted_at": "",
                "deleted_reason": "",
                "schema_version": str(schema_version or existing.get("schema_version") or "").strip(),
                "created_via": str(created_via or existing.get("created_via") or "").strip(),
                "context_binding_state": str(
                    context_binding_state or existing.get("context_binding_state") or ""
                ).strip().lower(),
            }
            if cli_type:
                update_fields["cli_type"] = str(cli_type)
            if alias:
                update_fields["alias"] = str(alias).strip()
            if model:
                update_fields["model"] = str(model).strip()
            if reasoning_effort:
                update_fields["reasoning_effort"] = _normalize_reasoning_effort_value(reasoning_effort)
            if environment:
                update_fields["environment"] = str(environment).strip()
            if worktree_root:
                update_fields["worktree_root"] = str(worktree_root).strip()
            if workdir:
                update_fields["workdir"] = str(workdir).strip()
            if branch:
                update_fields["branch"] = str(branch).strip()
            if purpose:
                update_fields["purpose"] = str(purpose).strip()
            if reuse_strategy:
                update_fields["reuse_strategy"] = str(reuse_strategy).strip()
            if isinstance(project_execution_context, dict):
                update_fields["project_execution_context"] = deepcopy(project_execution_context)
            if isinstance(is_primary, bool):
                update_fields["is_primary"] = is_primary
            elif str(session_role or "").strip().lower() == "primary":
                update_fields["is_primary"] = True
            updated = self.update_session(sid, **update_fields)
            if not updated:
                raise LookupError("session not found")
            return updated, False

        created = self.create_session(
            project_id=project_id,
            channel_name=channel_name,
            cli_type=cli_type,
            alias=alias,
            session_id=sid,
            model=model,
            reasoning_effort=reasoning_effort,
            environment=environment,
            worktree_root=worktree_root,
            workdir=workdir,
            branch=branch,
            session_role=session_role,
            purpose=purpose,
            reuse_strategy=reuse_strategy,
            schema_version=schema_version,
            created_via=created_via,
            context_binding_state=context_binding_state,
            project_execution_context=project_execution_context,
            is_primary=is_primary,
        )
        return created, True

    def update_session(self, session_id: str, **kwargs) -> dict[str, Any] | None:
        """
        Update session attributes.

        Args:
            session_id: The session identifier.
            **kwargs: Attributes to update (alias, status, channel_name, cli_type, etc.).

        Returns:
            Updated session dictionary or None if not found.
        """
        # Find the session and its project
        for path in self.sessions_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                sessions = data.get("sessions", [])
                for i, session in enumerate(sessions):
                    if session.get("id") == session_id:
                        next_channel_name = str(kwargs.get("channel_name") or session.get("channel_name") or "").strip()
                        if bool(kwargs.get("is_primary")) and next_channel_name:
                            for j, other in enumerate(sessions):
                                if j == i or not isinstance(other, dict):
                                    continue
                                other_row = self._normalize_session_record(other)
                                if (
                                    str(other_row.get("channel_name") or "").strip() == next_channel_name
                                    and not bool(other_row.get("is_deleted"))
                                ):
                                    other_row["is_primary"] = False
                                    if str(other_row.get("session_role") or "").strip().lower() == "primary":
                                        other_row["session_role"] = "child"
                                    sessions[j] = other_row
                        # Update allowed fields
                        allowed_fields = {
                            "alias",
                            "channel_name",
                            "cli_type",
                            "model",
                            "reasoning_effort",
                            "environment",
                            "worktree_root",
                            "workdir",
                            "branch",
                            "session_role",
                            "purpose",
                            "reuse_strategy",
                            "schema_version",
                            "created_via",
                            "context_binding_state",
                            "project_execution_context",
                            "heartbeat",
                            "last_used_at",
                            "is_primary",
                            "is_deleted",
                            "deleted_at",
                            "deleted_reason",
                        }
                        for key, value in kwargs.items():
                            if key in allowed_fields:
                                session[key] = deepcopy(value)

                        session = self._normalize_session_record(session)
                        session = self._apply_project_context_storage_semantics(session)
                        session["session_role"] = "primary" if bool(session.get("is_primary")) else "child"

                        # Update last_used_at if not explicitly set
                        if "last_used_at" not in kwargs:
                            session["last_used_at"] = _utc_now_iso()

                        sessions[i] = session
                        data["sessions"] = sessions
                        self._save_project_data(data.get("project_id", ""), data)
                        out = self._normalize_session_record(session)
                        out["project_id"] = str(data.get("project_id") or path.stem)
                        return out
            except Exception:
                continue
        return None

    def delete_session(self, session_id: str) -> bool:
        """
        Delete a session by its ID.

        Args:
            session_id: The session identifier.

        Returns:
            True if deleted, False if not found.
        """
        for path in self.sessions_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                sessions = data.get("sessions", [])
                original_len = len(sessions)
                sessions = [s for s in sessions if s.get("id") != session_id]

                if len(sessions) < original_len:
                    data["sessions"] = sessions
                    self._save_project_data(data.get("project_id", ""), data)
                    return True
            except Exception:
                continue
        return False

    def get_channel_default_session(self, project_id: str, channel_name: str) -> dict[str, Any] | None:
        """
        Get the default session for a channel (most recently used or first one).

        Args:
            project_id: The project identifier.
            channel_name: The channel name.

        Returns:
            Default session dictionary or None if no sessions exist for the channel.
        """
        sessions = self.list_sessions(project_id, channel_name, include_deleted=True)
        if not sessions:
            return None

        available_sessions = [s for s in sessions if session_binding_is_available(s)]
        if not available_sessions:
            return None

        primary_sessions = [s for s in available_sessions if bool(s.get("is_primary"))]
        if primary_sessions:
            primary_sessions.sort(key=session_binding_sort_key, reverse=True)
            return primary_sessions[0]

        available_sessions.sort(key=session_binding_sort_key, reverse=True)
        return available_sessions[0]

    def manage_channel_sessions(
        self,
        project_id: str,
        channel_name: str,
        *,
        primary_session_id: str = "",
        updates: Optional[list[dict[str, Any]]] = None,
    ) -> dict[str, Any]:
        """
        Manage one channel's sessions in batch.

        Supported actions:
        - set one session as channel primary
        - soft-delete / restore sessions
        """
        data = self._load_project_data(project_id)
        sessions = [deepcopy(s) for s in data.get("sessions", []) if isinstance(s, dict)]
        channel_indexes = [idx for idx, row in enumerate(sessions) if str(row.get("channel_name") or "") == channel_name]
        if not channel_indexes:
            return {
                "project_id": project_id,
                "channel_name": channel_name,
                "primary_session_id": "",
                "sessions": [],
                "count": 0,
            }

        update_map: dict[str, dict[str, Any]] = {}
        for item in updates or []:
            if not isinstance(item, dict):
                continue
            sid = str(item.get("session_id") or item.get("id") or "").strip()
            if not sid:
                continue
            update_map[sid] = item

        now = _utc_now_iso()
        candidate_primary = str(primary_session_id or "").strip()
        existing_primary = ""
        valid_ids: list[str] = []
        for idx in channel_indexes:
            session = self._normalize_session_record(sessions[idx])
            sid = str(session.get("id") or "").strip()
            if not sid:
                continue
            valid_ids.append(sid)
            patch = update_map.get(sid) or {}
            if "is_deleted" in patch:
                next_deleted = bool(patch.get("is_deleted"))
                session["is_deleted"] = next_deleted
                session["deleted_at"] = now if next_deleted else ""
                if next_deleted:
                    session["deleted_reason"] = str(patch.get("deleted_reason") or session.get("deleted_reason") or "marked_deleted").strip()
                else:
                    session["deleted_reason"] = ""
            if bool(session.get("is_primary")):
                existing_primary = sid
            sessions[idx] = session

        if candidate_primary not in valid_ids:
            candidate_primary = existing_primary

        effective_primary = ""
        if candidate_primary:
            for idx in channel_indexes:
                session = self._normalize_session_record(sessions[idx])
                sid = str(session.get("id") or "").strip()
                if sid == candidate_primary and not bool(session.get("is_deleted")):
                    effective_primary = sid
                    break

        if not effective_primary:
            fallback = [
                self._normalize_session_record(sessions[idx])
                for idx in channel_indexes
                if not bool(self._normalize_session_record(sessions[idx]).get("is_deleted"))
            ]
            available_fallback = [row for row in fallback if session_binding_is_available(row)]
            if available_fallback:
                available_fallback.sort(key=session_binding_sort_key, reverse=True)
                effective_primary = str(available_fallback[0].get("id") or "").strip()
            elif fallback:
                fallback.sort(key=session_binding_sort_key, reverse=True)
                effective_primary = str(fallback[0].get("id") or "").strip()

        for idx in channel_indexes:
            session = self._normalize_session_record(sessions[idx])
            sid = str(session.get("id") or "").strip()
            session["is_primary"] = bool(effective_primary) and sid == effective_primary and not bool(session.get("is_deleted"))
            session["session_role"] = "primary" if bool(session.get("is_primary")) else "child"
            sessions[idx] = session

        data["sessions"] = sessions
        self._save_project_data(project_id, data)
        out_sessions = self.list_sessions(project_id, channel_name, include_deleted=True)
        return {
            "project_id": project_id,
            "channel_name": channel_name,
            "primary_session_id": effective_primary,
            "sessions": out_sessions,
            "count": len(out_sessions),
        }

    def touch_session(self, session_id: str) -> bool:
        """
        Update the last_used_at timestamp for a session.

        Args:
            session_id: The session identifier.

        Returns:
            True if updated, False if not found.
        """
        result = self.update_session(session_id)
        return result is not None

    def dedup_channel_sessions(
        self,
        project_id: str,
        channel_name: str,
        keep_session_id: str = "",
        strategy: str = "latest",
    ) -> dict[str, Any]:
        """
        Deduplicate sessions in one project/channel and keep only one active binding.

        Args:
            project_id: Project identifier.
            channel_name: Channel name.
            keep_session_id: Preferred session id to keep.
            strategy: Keep strategy when keep_session_id is empty/invalid.
                - "latest": keep the most recently used (fallback created_at).
                - "first": keep the first matched record in file order.

        Returns:
            Dict with dedup summary.
        """
        data = self._load_project_data(project_id)
        sessions = list(data.get("sessions") or [])
        if not sessions:
            return {
                "project_id": project_id,
                "channel_name": channel_name,
                "kept_session_id": "",
                "removed_session_ids": [],
                "removed_count": 0,
                "total_before": 0,
                "total_after": 0,
            }

        target = str(channel_name or "").strip()
        candidates = []
        for idx, row in enumerate(sessions):
            if not isinstance(row, dict):
                continue
            if str(row.get("channel_name") or "").strip() != target:
                continue
            candidates.append((idx, row))

        if len(candidates) <= 1:
            sid = ""
            if candidates:
                sid = str(candidates[0][1].get("id") or "").strip()
            return {
                "project_id": project_id,
                "channel_name": channel_name,
                "kept_session_id": sid,
                "removed_session_ids": [],
                "removed_count": 0,
                "total_before": len(candidates),
                "total_after": len(candidates),
            }

        keep_sid = str(keep_session_id or "").strip()
        keep_idx = -1
        if keep_sid:
            for idx, row in candidates:
                sid = str(row.get("id") or "").strip()
                if sid == keep_sid:
                    keep_idx = idx
                    break

        if keep_idx < 0:
            rule = str(strategy or "").strip().lower() or "latest"
            if rule == "first":
                keep_idx = candidates[0][0]
            else:
                # latest by last_used_at, fallback created_at
                sortable = []
                for idx, row in candidates:
                    ts = str(row.get("last_used_at") or row.get("created_at") or "")
                    sortable.append((ts, idx))
                sortable.sort(key=lambda x: x[0], reverse=True)
                keep_idx = sortable[0][1]

        removed_ids = []
        kept_sid = ""
        new_sessions = []
        for idx, row in enumerate(sessions):
            if not isinstance(row, dict):
                new_sessions.append(row)
                continue
            if str(row.get("channel_name") or "").strip() != target:
                new_sessions.append(row)
                continue
            sid = str(row.get("id") or "").strip()
            if idx == keep_idx:
                kept_sid = sid
                new_sessions.append(row)
            else:
                removed_ids.append(sid)

        data["sessions"] = new_sessions
        self._save_project_data(project_id, data)
        return {
            "project_id": project_id,
            "channel_name": channel_name,
            "kept_session_id": kept_sid,
            "removed_session_ids": removed_ids,
            "removed_count": len(removed_ids),
            "total_before": len(candidates),
            "total_after": len(candidates) - len(removed_ids),
        }

    def list_all_projects(self) -> list[str]:
        """
        List all project IDs that have session data.

        Returns:
            List of project IDs.
        """
        projects = []
        for path in self.sessions_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                project_id = data.get("project_id")
                if project_id and project_id not in projects:
                    projects.append(project_id)
            except Exception:
                continue
        return projects
