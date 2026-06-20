# -*- coding: utf-8 -*-
"""Internal message CLI for the task-dashboard CCB announce path.

The CLI is intentionally a thin wrapper around ``POST /api/codex/announce``.
It resolves targets from SessionStore, builds the same structured payload used
by the UI, and never falls back to direct resume or file-based inboxes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import error as url_error
from urllib import request as url_request

from .runtime.project_id_aliases import canonicalize_runtime_project_id
from .session_store import SessionStore, session_binding_sort_key
from .utils import iso_now_local, repo_root_from_here


VALID_MODES = {"dialog_now", "task_with_receipt", "notify_only"}
EVIDENCE_FIELDS = {
    "announce_run_id",
    "announceRunId",
    "visible_in_channel_chat",
    "visibleInChannelChat",
    "delivery_state",
    "deliveryState",
    "delivery_checked_at",
    "deliveryCheckedAt",
}


def _as_str(value: Any) -> str:
    return "" if value is None else str(value)


def _normalize_key(value: Any) -> str:
    return _as_str(value).strip().casefold()


def _repo_root(args: argparse.Namespace) -> Path:
    raw = _as_str(getattr(args, "root", "")).strip()
    if raw:
        path = Path(raw).expanduser()
        return path.resolve() if path.is_absolute() else (Path.cwd() / path).resolve()
    return repo_root_from_here(__file__).resolve()


def _is_runtime_stable_root(path: Path) -> bool:
    return path.name == "stable" and path.parent.name == ".runtime"


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    seen: set[Path] = set()
    out: list[Path] = []
    for path in paths:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        out.append(resolved)
    return out


def _session_store_roots(args: argparse.Namespace) -> list[Path]:
    root = _repo_root(args)
    if _is_runtime_stable_root(root):
        return [root]
    stable_root = root / ".runtime" / "stable"
    candidates = [stable_root, root] if stable_root.exists() else [root]
    return _dedupe_paths(candidates)


def _runs_dir(args: argparse.Namespace) -> Path:
    raw = _as_str(getattr(args, "runs_dir", "")).strip()
    if raw:
        path = Path(raw).expanduser()
        return path.resolve() if path.is_absolute() else (Path.cwd() / path).resolve()
    root = _repo_root(args)
    if _is_runtime_stable_root(root):
        return (root / ".runs").resolve()
    return (root / ".runtime" / "stable" / ".runs").resolve()


def _normalize_project_id(value: Any) -> str:
    return canonicalize_runtime_project_id(_as_str(value).strip() or "task_dashboard")


def _is_uuidish(value: Any) -> bool:
    text = _as_str(value).strip()
    return len(text) >= 8 and all(ch.isalnum() or ch == "-" for ch in text)


def _session_block_code(session: dict[str, Any]) -> str:
    if bool(session.get("is_deleted")):
        return "target_session_inactive"
    status = _normalize_key(session.get("status") or "active")
    if status and status not in {"active"}:
        if status in {"context_exhausted", "exhausted"}:
            return "context_exhausted"
        return "target_session_inactive"
    binding_state = _normalize_key(
        session.get("context_binding_state")
        or session.get("binding_state")
        or session.get("context_state")
    )
    if binding_state in {"context_exhausted", "exhausted"}:
        return "context_exhausted"
    if bool(session.get("context_exhausted")):
        return "context_exhausted"
    return ""


def _session_display_name(session: dict[str, Any]) -> str:
    for key in ("alias", "display_name", "agent_name", "channel_name", "id"):
        value = _as_str(session.get(key)).strip()
        if value:
            return value
    return ""


def _session_summary(session: dict[str, Any]) -> dict[str, Any]:
    return {
        "project_id": _as_str(session.get("project_id")).strip(),
        "channel_name": _as_str(session.get("channel_name")).strip(),
        "session_id": _as_str(session.get("id")).strip(),
        "alias": _as_str(session.get("alias")).strip(),
        "display_name": _as_str(session.get("display_name")).strip(),
        "agent_name": _as_str(session.get("agent_name")).strip(),
        "status": _as_str(session.get("status")).strip() or "active",
        "is_deleted": bool(session.get("is_deleted")),
        "is_primary": bool(session.get("is_primary")),
        "context_binding_state": _as_str(session.get("context_binding_state")).strip(),
    }


def _blocking(code: str, message: str, **extra: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"code": code, "message": message}
    out.update({k: v for k, v in extra.items() if v not in (None, "", [], {})})
    return out


def _resolution_next_action(code: str) -> str:
    if code == "target_session_missing":
        return (
            "CLI 只以项目 SessionStore 中的 active 会话为正式发送真源；"
            "请先用 message_cli resolve/doctor 确认目标，若目标未注册或不可用，转会话治理更新主绑定，"
            "不要通过读源码、旧 registry 或 direct resume 旁路发送。"
        )
    if code == "agent_ambiguous":
        return "目标命中多个 active Agent；请补 --channel 或使用 resolve 返回的候选 session_id 后重试。"
    if code == "context_exhausted":
        return "目标会话上下文已耗尽；请先走会话轮换/主绑定替换，再发送正式协作消息。"
    if code == "target_session_inactive":
        return "目标会话不可发送；请先恢复/替换目标会话，或联系主负责位确认新 session。"
    if code == "route_mismatch":
        return "显式路由字段不一致；请以 resolve/doctor 输出的 target_ref 为准，修正 --channel/--to-agent/--session-id。"
    return ""


@dataclass
class TargetResolution:
    ok: bool
    project_id: str
    channel_name: str = ""
    session_id: str = ""
    target_session: dict[str, Any] | None = None
    blocking_error: dict[str, Any] | None = None
    candidates: list[dict[str, Any]] | None = None
    session_store_root: str = ""

    def as_payload(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "project_id": self.project_id,
            "session_store_root": self.session_store_root,
            "target_ref": {
                "project_id": self.project_id,
                "channel_name": self.channel_name,
                "session_id": self.session_id,
            },
            "target_session": _session_summary(self.target_session or {}) if self.target_session else None,
            "candidates": self.candidates or [],
            "blocking_error": self.blocking_error,
        }


def _active_session(session: dict[str, Any], project_id: str) -> tuple[bool, str]:
    if _as_str(session.get("project_id")).strip() != project_id:
        return False, "project_mismatch"
    code = _session_block_code(session)
    if code:
        return False, code
    return True, ""


def _candidate_match(session: dict[str, Any], token: str) -> bool:
    expected = _normalize_key(token)
    if not expected:
        return False
    values = [
        session.get("alias"),
        session.get("display_name"),
        session.get("agent_name"),
        session.get("name"),
        session.get("channel_name"),
        session.get("id"),
    ]
    return any(_normalize_key(value) == expected for value in values)


def _resolve_target_from_store(
    args: argparse.Namespace,
    store: SessionStore,
    *,
    store_root: Path | None = None,
) -> TargetResolution:
    project_id = _normalize_project_id(getattr(args, "project", ""))
    store_root_text = str(store_root.resolve()) if store_root else ""
    explicit_session_id = _as_str(getattr(args, "session_id", "")).strip()
    channel_name = _as_str(getattr(args, "channel", "")).strip()
    to_agent = _as_str(getattr(args, "to_agent", "")).strip()

    if explicit_session_id:
        session = store.get_session(explicit_session_id)
        if not session:
            return TargetResolution(
                ok=False,
                project_id=project_id,
                session_id=explicit_session_id,
                session_store_root=store_root_text,
                blocking_error=_blocking(
                    "target_session_missing",
                    "显式 session_id 未在 SessionStore 中找到",
                    lookup_scope="active_session_store",
                    next_action=_resolution_next_action("target_session_missing"),
                ),
            )
        active, code = _active_session(session, project_id)
        if not active:
            return TargetResolution(
                ok=False,
                project_id=project_id,
                channel_name=_as_str(session.get("channel_name")).strip(),
                session_id=explicit_session_id,
                target_session=session,
                session_store_root=store_root_text,
                blocking_error=_blocking(code, "目标 session 不满足发送前置条件", next_action=_resolution_next_action(code)),
            )
        if channel_name and _as_str(session.get("channel_name")).strip() != channel_name:
            return TargetResolution(
                ok=False,
                project_id=project_id,
                channel_name=channel_name,
                session_id=explicit_session_id,
                target_session=session,
                session_store_root=store_root_text,
                blocking_error=_blocking(
                    "route_mismatch",
                    "显式 session_id 与目标 channel 不一致",
                    next_action=_resolution_next_action("route_mismatch"),
                ),
            )
        if to_agent and not _candidate_match(session, to_agent):
            return TargetResolution(
                ok=False,
                project_id=project_id,
                channel_name=_as_str(session.get("channel_name")).strip(),
                session_id=explicit_session_id,
                target_session=session,
                session_store_root=store_root_text,
                blocking_error=_blocking(
                    "route_mismatch",
                    "显式 session_id 与目标 Agent 不一致",
                    next_action=_resolution_next_action("route_mismatch"),
                ),
            )
        return TargetResolution(
            ok=True,
            project_id=project_id,
            channel_name=_as_str(session.get("channel_name")).strip(),
            session_id=explicit_session_id,
            target_session=session,
            session_store_root=store_root_text,
        )

    sessions = store.list_sessions(project_id, channel_name if channel_name else None, include_deleted=True)
    if to_agent:
        sessions = [session for session in sessions if _candidate_match(session, to_agent)]

    if not sessions:
        return TargetResolution(
            ok=False,
            project_id=project_id,
            channel_name=channel_name,
            session_store_root=store_root_text,
            blocking_error=_blocking(
                "target_session_missing",
                "未解析到目标 session",
                lookup_scope="active_session_store",
                next_action=_resolution_next_action("target_session_missing"),
            ),
        )

    active_rows: list[dict[str, Any]] = []
    inactive_codes: set[str] = set()
    for session in sessions:
        active, code = _active_session(session, project_id)
        if active:
            active_rows.append(session)
        elif code:
            inactive_codes.add(code)

    if not active_rows:
        code = "context_exhausted" if "context_exhausted" in inactive_codes else "target_session_inactive"
        return TargetResolution(
            ok=False,
            project_id=project_id,
            channel_name=channel_name,
            candidates=[_session_summary(row) for row in sessions],
            session_store_root=store_root_text,
            blocking_error=_blocking(code, "候选目标存在但均不可发送", next_action=_resolution_next_action(code)),
        )

    if len(active_rows) > 1:
        active_rows.sort(key=session_binding_sort_key, reverse=True)
        return TargetResolution(
            ok=False,
            project_id=project_id,
            channel_name=channel_name,
            candidates=[_session_summary(row) for row in active_rows],
            session_store_root=store_root_text,
            blocking_error=_blocking(
                "agent_ambiguous",
                "目标解析命中多个 active 候选，请显式指定 session_id",
                next_action=_resolution_next_action("agent_ambiguous"),
            ),
        )

    target = active_rows[0]
    return TargetResolution(
        ok=True,
        project_id=project_id,
        channel_name=_as_str(target.get("channel_name")).strip(),
        session_id=_as_str(target.get("id")).strip(),
        target_session=target,
        session_store_root=store_root_text,
    )


def resolve_target(args: argparse.Namespace, store: SessionStore | None = None) -> TargetResolution:
    if store is not None:
        return _resolve_target_from_store(args, store)

    roots = _session_store_roots(args)
    last_missing: TargetResolution | None = None
    lookup_roots: list[str] = []
    for root in roots:
        lookup_roots.append(str(root))
        resolution = _resolve_target_from_store(args, SessionStore(root), store_root=root)
        if resolution.ok:
            return resolution
        code = _as_str((resolution.blocking_error or {}).get("code")).strip()
        if code != "target_session_missing":
            return resolution
        last_missing = resolution

    if last_missing is not None:
        blocking = dict(last_missing.blocking_error or {})
        blocking["lookup_roots"] = lookup_roots
        last_missing.blocking_error = blocking
        return last_missing

    project_id = _normalize_project_id(getattr(args, "project", ""))
    return TargetResolution(
        ok=False,
        project_id=project_id,
        blocking_error=_blocking(
            "target_session_missing",
            "未解析到目标 session",
            lookup_scope="active_session_store",
            lookup_roots=lookup_roots,
            next_action=_resolution_next_action("target_session_missing"),
        ),
    )


def _read_message(args: argparse.Namespace, *, required: bool) -> tuple[str, dict[str, Any] | None]:
    message = _as_str(getattr(args, "message", ""))
    message_file = _as_str(getattr(args, "message_file", "")).strip()
    if message and message_file:
        return "", _blocking("payload_builder_mismatch", "--message 与 --message-file 只能二选一")
    if message_file:
        path = Path(message_file).expanduser()
        if not path.is_file():
            return "", _blocking("payload_builder_mismatch", "message-file 不存在或不是文件")
        message = path.read_text(encoding="utf-8")
    if required and not message.strip():
        return "", _blocking("payload_builder_mismatch", "缺少消息正文")
    return message.strip(), None


def _source_session(args: argparse.Namespace, store: SessionStore) -> dict[str, Any] | None:
    source_session_id = (
        _as_str(getattr(args, "source_session_id", "")).strip()
        or _as_str(getattr(args, "callback_session_id", "")).strip()
        or _as_str(os.environ.get("TASK_DASHBOARD_SOURCE_SESSION_ID")).strip()
    )
    if not source_session_id:
        return None
    return store.get_session(source_session_id)


def _callback_ref(args: argparse.Namespace, source_session: dict[str, Any] | None) -> dict[str, str]:
    callback_session_id = _as_str(getattr(args, "callback_session_id", "")).strip()
    callback_channel = _as_str(getattr(args, "callback_channel", "")).strip()
    if not callback_session_id and source_session:
        callback_session_id = _as_str(source_session.get("id")).strip()
    if not callback_channel and source_session:
        callback_channel = _as_str(source_session.get("channel_name")).strip()
    out: dict[str, str] = {}
    if callback_channel:
        out["channel_name"] = callback_channel
    if callback_session_id:
        out["session_id"] = callback_session_id
    return out


def _source_ref(args: argparse.Namespace, project_id: str, source_session: dict[str, Any] | None) -> dict[str, str]:
    source_channel = (
        _as_str(getattr(args, "source_channel", "")).strip()
        or _as_str((source_session or {}).get("channel_name")).strip()
        or _as_str(os.environ.get("TASK_DASHBOARD_SOURCE_CHANNEL")).strip()
    )
    source_session_id = (
        _as_str(getattr(args, "source_session_id", "")).strip()
        or _as_str((source_session or {}).get("id")).strip()
        or _as_str(getattr(args, "callback_session_id", "")).strip()
        or _as_str(os.environ.get("TASK_DASHBOARD_SOURCE_SESSION_ID")).strip()
    )
    source_run_id = _as_str(getattr(args, "source_run_id", "")).strip() or "none"
    out = {"project_id": project_id}
    if source_channel:
        out["channel_name"] = source_channel
    if source_session_id:
        out["session_id"] = source_session_id
    if source_run_id:
        out["run_id"] = source_run_id
    return out


def build_message_payload(
    args: argparse.Namespace,
    *,
    resolution: TargetResolution | None = None,
    message_required: bool = True,
) -> dict[str, Any]:
    resolution = resolution or resolve_target(args)
    store_root_text = _as_str(resolution.session_store_root).strip()
    store_root = Path(store_root_text).expanduser().resolve() if store_root_text else _session_store_roots(args)[0]
    store = SessionStore(store_root)
    if not resolution.ok:
        return {
            "ok": False,
            "state": "blocked",
            "project_id": resolution.project_id,
            "target_ref": resolution.as_payload().get("target_ref"),
            "blocking_error": resolution.blocking_error,
        }

    message, message_error = _read_message(args, required=message_required)
    if message_error:
        return {
            "ok": False,
            "state": "blocked",
            "project_id": resolution.project_id,
            "target_ref": resolution.as_payload().get("target_ref"),
            "blocking_error": message_error,
        }

    mode = _as_str(getattr(args, "mode", "")).strip().lower() or "notify_only"
    if mode not in VALID_MODES:
        return {
            "ok": False,
            "state": "blocked",
            "project_id": resolution.project_id,
            "target_ref": resolution.as_payload().get("target_ref"),
            "blocking_error": _blocking("payload_builder_mismatch", "interaction_mode 非法"),
        }

    source_session = _source_session(args, store)
    callback_to = _callback_ref(args, source_session)
    if mode == "task_with_receipt" and not callback_to.get("session_id"):
        return {
            "ok": False,
            "state": "blocked",
            "project_id": resolution.project_id,
            "target_ref": resolution.as_payload().get("target_ref"),
            "blocking_error": _blocking("callback_missing", "task_with_receipt 必须提供 callback-session-id"),
        }

    source_ref = _source_ref(args, resolution.project_id, source_session)
    sender_session_id = _as_str(source_ref.get("session_id")).strip() or "message_cli"
    sender_name = (
        _as_str(getattr(args, "sender_name", "")).strip()
        or _as_str(os.environ.get("TASK_DASHBOARD_AGENT_ALIAS")).strip()
        or _session_display_name(source_session or {})
        or "message_cli"
    )
    sender_role = _as_str(getattr(args, "sender_role", "")).strip() or "执行位"
    owner_name = _as_str(getattr(args, "owner_agent", "")).strip() or sender_name
    owner_session_id = _as_str(getattr(args, "owner_session_id", "")).strip() or sender_session_id
    owner_channel = _as_str(getattr(args, "owner_channel", "")).strip() or _as_str(source_ref.get("channel_name")).strip()
    owner_role = _as_str(getattr(args, "owner_role", "")).strip() or "主负责位"
    client_message_id = _as_str(getattr(args, "client_message_id", "")).strip()

    target_ref = {
        "project_id": resolution.project_id,
        "channel_name": resolution.channel_name,
        "session_id": resolution.session_id,
    }
    payload: dict[str, Any] = {
        "projectId": resolution.project_id,
        "channelName": resolution.channel_name,
        "sessionId": resolution.session_id,
        "message": message,
        "sender_type": "agent",
        "sender_id": sender_session_id,
        "sender_name": sender_name,
        "message_kind": "collab_update",
        "interaction_mode": mode,
        "source_ref": source_ref,
        "target_ref": target_ref,
        "sender_agent_ref": {
            "agent_name": sender_name,
            "alias": sender_name,
            "role": sender_role,
            "session_id": sender_session_id,
        },
        "owner_ref": {
            "agent_name": owner_name,
            "alias": owner_name,
            "role": owner_role,
            "session_id": owner_session_id,
        },
    }
    if owner_channel:
        payload["owner_ref"]["channel_name"] = owner_channel
    if callback_to:
        payload["callback_to"] = callback_to
    if client_message_id:
        payload["client_message_id"] = client_message_id
    return {
        "ok": True,
        "state": "drafted",
        "project_id": resolution.project_id,
        "target_ref": target_ref,
        "source_ref": source_ref,
        "callback_to": callback_to or None,
        "interaction_mode": mode,
        "message_kind": "collab_update",
        "receipt_required": mode == "task_with_receipt",
        "payload": payload,
        "blocking_error": None,
    }


def _run_meta_candidates(runs_dir: Path, run_id: str | None = None) -> list[Path]:
    roots = [runs_dir / "hot", runs_dir, runs_dir / "archive"]
    paths: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        if run_id:
            if root.name == "archive":
                paths.extend(root.glob(f"*/{run_id}.json"))
            else:
                candidate = root / f"{run_id}.json"
                if candidate.exists():
                    paths.append(candidate)
        else:
            if root.name == "archive":
                paths.extend(root.glob("*/*.json"))
            else:
                paths.extend(root.glob("*.json"))
    seen: set[Path] = set()
    out: list[Path] = []
    for path in paths:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        out.append(path)
    return out


def _load_meta_path(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _load_local_run(runs_dir: Path, run_id: str) -> dict[str, Any] | None:
    for path in _run_meta_candidates(runs_dir, run_id):
        meta = _load_meta_path(path)
        if meta:
            return meta
    return None


def _read_run_message(meta_path: Path, meta: dict[str, Any]) -> str:
    raw_paths = meta.get("paths") if isinstance(meta.get("paths"), dict) else {}
    msg_path = _as_str(raw_paths.get("msg")).strip()
    candidates = []
    if msg_path:
        candidates.append(Path(msg_path))
    candidates.append(meta_path.with_suffix(".msg.txt"))
    for path in candidates:
        try:
            if path.exists():
                return path.read_text(encoding="utf-8")
        except Exception:
            continue
    return ""


def _fingerprint_for_payload(payload: dict[str, Any]) -> str:
    relevant = {
        "projectId": payload.get("projectId"),
        "channelName": payload.get("channelName"),
        "sessionId": payload.get("sessionId"),
        "message": payload.get("message"),
        "sender_id": payload.get("sender_id"),
        "client_message_id": payload.get("client_message_id"),
        "source_ref": payload.get("source_ref"),
        "target_ref": payload.get("target_ref"),
    }
    text = json.dumps(relevant, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _fingerprint_for_meta(meta_path: Path, meta: dict[str, Any]) -> str:
    relevant = {
        "projectId": meta.get("projectId"),
        "channelName": meta.get("channelName"),
        "sessionId": meta.get("sessionId"),
        "message": _read_run_message(meta_path, meta),
        "sender_id": meta.get("sender_id"),
        "client_message_id": meta.get("client_message_id") or meta.get("clientMessageId"),
        "source_ref": meta.get("source_ref"),
        "target_ref": meta.get("target_ref"),
    }
    text = json.dumps(relevant, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def find_idempotent_run(args: argparse.Namespace, payload: dict[str, Any]) -> dict[str, Any] | None:
    client_message_id = _as_str(payload.get("client_message_id") or payload.get("clientMessageId")).strip()
    if not client_message_id:
        return None
    expected_fp = _fingerprint_for_payload(payload)
    conflicts: list[str] = []
    for path in _run_meta_candidates(_runs_dir(args)):
        meta = _load_meta_path(path)
        if not meta:
            continue
        if _as_str(meta.get("client_message_id") or meta.get("clientMessageId")).strip() != client_message_id:
            continue
        if _fingerprint_for_meta(path, meta) == expected_fp:
            return {"state": "matched", "run": meta}
        conflicts.append(_as_str(meta.get("id")).strip() or path.stem)
    if conflicts:
        return {"state": "conflict", "run_ids": conflicts}
    return None


def classify_delivery(
    run: dict[str, Any],
    *,
    expected_session_id: str = "",
    run_id: str = "",
) -> dict[str, Any]:
    meta = run if isinstance(run, dict) else {}
    actual_run_id = _as_str(meta.get("id") or meta.get("run_id") or meta.get("runId")).strip()
    expected_run_id = _as_str(run_id).strip() or actual_run_id
    actual_session_id = _as_str(meta.get("sessionId") or meta.get("session_id")).strip()
    target_ref = meta.get("target_ref") if isinstance(meta.get("target_ref"), dict) else {}
    target_session_id = _as_str((target_ref or {}).get("session_id")).strip() or actual_session_id
    expected_target = _as_str(expected_session_id).strip() or target_session_id
    visible = bool(meta.get("visible_in_channel_chat") or meta.get("visibleInChannelChat"))

    evidence = {
        "announce_run_id": actual_run_id,
        "target_session_id": target_session_id,
        "visible_in_channel_chat": visible,
        "delivery_checked_at": iso_now_local(),
    }
    run_matches = bool(actual_run_id and expected_run_id and actual_run_id == expected_run_id)
    session_matches = bool(actual_session_id and expected_target and actual_session_id == expected_target)
    if run_matches and session_matches and visible:
        state = "delivered"
        blocking_error = None
    else:
        state = "delivery_unverified"
        blocking_error = _blocking("delivery_unverified", "run 回看证据未闭环")
    return {
        "state": state,
        "announce_run_id": actual_run_id,
        "project_id": _as_str(meta.get("projectId") or meta.get("project_id")).strip(),
        "target_ref": {
            "channel_name": _as_str(meta.get("channelName") or (target_ref or {}).get("channel_name")).strip(),
            "session_id": target_session_id,
        },
        **evidence,
        "blocking_error": blocking_error,
    }


def _receipt_block(delivery: dict[str, Any], *, run_status: str = "") -> str:
    if not isinstance(delivery, dict):
        return ""
    state = _as_str(delivery.get("state")).strip()
    run_id = _as_str(delivery.get("announce_run_id")).strip()
    target_session_id = _as_str(delivery.get("target_session_id")).strip()
    visible = bool(delivery.get("visible_in_channel_chat"))
    if state == "delivered":
        conclusion = "已完成证据闭环"
        blocking = "无"
    else:
        conclusion = "已提交发送，待验证" if run_id else "证据不足，未完成送达判定"
        blocking = "送达证据未闭环"
    parts = [
        f"当前结论: {conclusion}",
        f"是否通过或放行: {'已送达目标通道' if state == 'delivered' else '不判定已送达'}",
        f"唯一阻塞: {blocking}",
        (
            "关键路径或 run_id: "
            f"announce_run_id={run_id or 'none'}; "
            f"target_session_id={target_session_id or 'none'}; "
            f"visible_in_channel_chat={str(visible).lower()}"
            + (f"; run_status={run_status}" if run_status else "")
        ),
        "下一步动作: 按 interaction_mode 继续等待业务回执或人工处理",
    ]
    return "\n".join(parts)


def _wait_for_delivery(args: argparse.Namespace, run_id: str, expected_session_id: str) -> tuple[dict[str, Any], str]:
    timeout_raw = getattr(args, "verify_timeout", 30.0)
    interval_raw = getattr(args, "verify_interval", 1.0)
    timeout_s = 30.0 if timeout_raw is None else float(timeout_raw)
    interval = 1.0 if interval_raw is None else float(interval_raw)
    deadline = time.monotonic() + max(0.0, timeout_s)
    interval = max(0.0, interval)
    last_delivery: dict[str, Any] = {}
    last_status = ""
    while True:
        run = _load_local_run(_runs_dir(args), run_id) or _load_remote_run(args, run_id)
        if run:
            last_status = _as_str(run.get("status")).strip()
            last_delivery = classify_delivery(run, expected_session_id=expected_session_id, run_id=run_id)
            if last_delivery.get("state") == "delivered":
                return last_delivery, last_status
        else:
            last_delivery = {
                "state": "delivery_unverified",
                "announce_run_id": run_id,
                "target_session_id": expected_session_id,
                "visible_in_channel_chat": False,
                "delivery_checked_at": iso_now_local(),
                "blocking_error": _blocking("delivery_unverified", "未找到 run 回看证据"),
            }
        if time.monotonic() >= deadline:
            return last_delivery, last_status
        time.sleep(min(interval, max(0.0, deadline - time.monotonic())))


def _with_receipt_block(result: dict[str, Any], *, run_status: str = "") -> dict[str, Any]:
    delivery = result.get("delivery") if isinstance(result.get("delivery"), dict) else {}
    if not delivery and any(key in result for key in ("state", "announce_run_id", "visible_in_channel_chat")):
        delivery = result
    block = _receipt_block(delivery, run_status=run_status)
    if block:
        result["receipt_block"] = block
    return result


def _apply_wait_verify(args: argparse.Namespace, result: dict[str, Any], expected_session_id: str) -> dict[str, Any]:
    if not bool(getattr(args, "wait_verify", False)):
        return _with_receipt_block(result)
    run_id = _as_str(result.get("announce_run_id")).strip()
    if not run_id or not bool(result.get("ok", False)):
        return _with_receipt_block(result)
    delivery, run_status = _wait_for_delivery(args, run_id, expected_session_id)
    result["delivery"] = delivery
    result["state"] = _as_str(delivery.get("state")).strip() or _as_str(result.get("state")).strip() or "submitted"
    result["wait_verify"] = True
    result["run_status"] = run_status
    result["ok"] = result["state"] == "delivered"
    result["blocking_error"] = delivery.get("blocking_error")
    return _with_receipt_block(result, run_status=run_status)


def _http_json(url: str, *, method: str = "GET", body: dict[str, Any] | None = None, token: str = "", timeout: float = 20.0) -> tuple[int, dict[str, Any]]:
    headers = {"Accept": "application/json"}
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    if token:
        headers["X-TaskDashboard-Token"] = token
        headers["Authorization"] = f"Bearer {token}"
    req = url_request.Request(url, data=data, headers=headers, method=method)
    try:
        with url_request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            payload = json.loads(raw) if raw else {}
            return int(resp.status), payload if isinstance(payload, dict) else {"value": payload}
    except url_error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw) if raw else {}
        except Exception:
            payload = {"error": raw}
        return int(exc.code), payload if isinstance(payload, dict) else {"value": payload}


def post_announce(args: argparse.Namespace, payload: dict[str, Any]) -> dict[str, Any]:
    base_url = _as_str(getattr(args, "base_url", "")).strip().rstrip("/") or "http://localhost:18770"
    token = _as_str(getattr(args, "token", "")).strip() or _as_str(os.environ.get("TASK_DASHBOARD_TOKEN")).strip()
    try:
        code, response = _http_json(
            f"{base_url}/api/codex/announce",
            method="POST",
            body=payload,
            token=token,
            timeout=float(getattr(args, "timeout", 20.0) or 20.0),
        )
    except Exception as exc:
        return {
            "ok": False,
            "state": "failed",
            "blocking_error": _blocking("announce_failed", f"announce 请求失败: {exc}"),
        }
    if code < 200 or code >= 300 or not bool(response.get("ok", True)):
        error_code = "token_required" if code in {401, 403} else "announce_failed"
        return {
            "ok": False,
            "state": "failed",
            "http_status": code,
            "response": response,
            "blocking_error": _blocking(error_code, "announce 接口返回失败"),
        }
    run = response.get("run") if isinstance(response.get("run"), dict) else {}
    run_id = _as_str(run.get("id")).strip()
    delivery = classify_delivery(run, expected_session_id=_as_str(payload.get("sessionId")).strip(), run_id=run_id) if run else {}
    state = _as_str(delivery.get("state")).strip() or "submitted"
    if state == "delivery_unverified" and run_id:
        state = "submitted"
    return {
        "ok": True,
        "state": state,
        "announce_run_id": run_id,
        "project_id": _as_str(payload.get("projectId")).strip(),
        "target_ref": payload.get("target_ref"),
        "response": response,
        "delivery": delivery or None,
        "blocking_error": None,
    }


def _print_result(args: argparse.Namespace, payload: dict[str, Any]) -> int:
    ok = bool(payload.get("ok", payload.get("state") not in {"blocked", "failed"}))
    if bool(getattr(args, "json", False)):
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        state = _as_str(payload.get("state")).strip() or ("ok" if ok else "failed")
        print(f"state={state}")
        blocking = payload.get("blocking_error") if isinstance(payload.get("blocking_error"), dict) else {}
        if blocking:
            print(f"blocking_error={blocking.get('code')}: {blocking.get('message')}")
        run_id = _as_str(payload.get("announce_run_id")).strip()
        if run_id:
            print(f"announce_run_id={run_id}")
        receipt = _as_str(payload.get("receipt_block")).strip()
        if receipt:
            print(receipt)
    return 0 if ok else 1


def _cmd_resolve(args: argparse.Namespace) -> int:
    resolution = resolve_target(args)
    payload = resolution.as_payload()
    payload["state"] = "resolved" if resolution.ok else "blocked"
    return _print_result(args, payload)


def _cmd_doctor(args: argparse.Namespace) -> int:
    resolution = resolve_target(args)
    if not resolution.ok:
        payload = resolution.as_payload()
        payload["state"] = "blocked"
        return _print_result(args, payload)
    draft = build_message_payload(args, resolution=resolution, message_required=False)
    if draft.get("ok"):
        draft["state"] = "ready"
        draft.pop("payload", None)
    return _print_result(args, draft)


def _cmd_draft(args: argparse.Namespace) -> int:
    payload = build_message_payload(args)
    return _print_result(args, payload)


def _cmd_send(args: argparse.Namespace) -> int:
    draft = build_message_payload(args)
    if not draft.get("ok"):
        return _print_result(args, draft)
    payload = draft.get("payload") if isinstance(draft.get("payload"), dict) else {}
    if bool(getattr(args, "dry_run", False)):
        draft["dry_run"] = True
        return _print_result(args, draft)
    idem = find_idempotent_run(args, payload)
    if isinstance(idem, dict) and idem.get("state") == "matched":
        run = idem.get("run") if isinstance(idem.get("run"), dict) else {}
        delivery = classify_delivery(run, expected_session_id=_as_str(payload.get("sessionId")).strip())
        out = {
            "ok": True,
            "state": delivery.get("state") or "submitted",
            "idempotent_replay": True,
            "announce_run_id": _as_str(run.get("id")).strip(),
            "project_id": _as_str(payload.get("projectId")).strip(),
            "target_ref": payload.get("target_ref"),
            "delivery": delivery,
            "blocking_error": None,
        }
        out = _apply_wait_verify(args, out, _as_str(payload.get("sessionId")).strip())
        return _print_result(args, out)
    if isinstance(idem, dict) and idem.get("state") == "conflict":
        out = {
            "ok": False,
            "state": "blocked",
            "project_id": _as_str(payload.get("projectId")).strip(),
            "target_ref": payload.get("target_ref"),
            "blocking_error": _blocking(
                "idempotency_conflict",
                "client_message_id 已存在但请求摘要不一致",
                run_ids=idem.get("run_ids"),
            ),
        }
        return _print_result(args, out)
    out = _apply_wait_verify(args, post_announce(args, payload), _as_str(payload.get("sessionId")).strip())
    return _print_result(args, out)


def _cmd_receipt(args: argparse.Namespace) -> int:
    if not _as_str(getattr(args, "mode", "")).strip():
        args.mode = "notify_only"
    return _cmd_send(args)


def _load_remote_run(args: argparse.Namespace, run_id: str) -> dict[str, Any] | None:
    base_url = _as_str(getattr(args, "base_url", "")).strip().rstrip("/")
    if not base_url:
        return None
    token = _as_str(getattr(args, "token", "")).strip() or _as_str(os.environ.get("TASK_DASHBOARD_TOKEN")).strip()
    try:
        code, response = _http_json(
            f"{base_url}/api/codex/run/{run_id}",
            token=token,
            timeout=float(getattr(args, "timeout", 20.0) or 20.0),
        )
    except Exception:
        return None
    if code < 200 or code >= 300:
        return None
    run = response.get("run") if isinstance(response.get("run"), dict) else response
    return run if isinstance(run, dict) else None


def _cmd_status(args: argparse.Namespace) -> int:
    run_id = _as_str(getattr(args, "run_id", "") or getattr(args, "announce_run_id", "")).strip()
    if not run_id:
        return _print_result(
            args,
            {
                "ok": False,
                "state": "blocked",
                "blocking_error": _blocking("payload_builder_mismatch", "status/verify 需要 --run-id"),
            },
        )
    run = _load_local_run(_runs_dir(args), run_id) or _load_remote_run(args, run_id)
    if not run:
        return _print_result(
            args,
            {
                "ok": False,
                "state": "failed",
                "announce_run_id": run_id,
                "blocking_error": _blocking("delivery_unverified", "未找到 run 回看证据"),
            },
        )
    delivery = classify_delivery(run, expected_session_id=_as_str(getattr(args, "session_id", "")).strip(), run_id=run_id)
    out = {
        "ok": delivery.get("state") == "delivered",
        **delivery,
        "run_status": _as_str(run.get("status")).strip(),
    }
    out = _with_receipt_block(out, run_status=_as_str(run.get("status")).strip())
    return _print_result(args, out)


def _cmd_verify(args: argparse.Namespace) -> int:
    return _cmd_status(args)


def _add_common_options(parser: argparse.ArgumentParser, *, include_message: bool = False) -> None:
    parser.add_argument(
        "--root",
        default=str(repo_root_from_here(__file__)),
        help="task-dashboard repo root; defaults to live stable SessionStore when available",
    )
    parser.add_argument("--runs-dir", default="", help="RunStore .runs directory for status and idempotency checks")
    parser.add_argument("--project", default="task_dashboard", help="project id or alias")
    parser.add_argument("--to-agent", default="", help="target agent alias/name")
    parser.add_argument("--channel", default="", help="target channel name")
    parser.add_argument("--session-id", default="", help="target session id")
    parser.add_argument("--mode", choices=sorted(VALID_MODES), default="", help="interaction mode")
    parser.add_argument("--callback-session-id", default="", help="required for task_with_receipt")
    parser.add_argument("--callback-channel", default="", help="callback channel name")
    parser.add_argument("--source-session-id", default="", help="sender/source session id")
    parser.add_argument("--source-channel", default="", help="sender/source channel name")
    parser.add_argument("--source-run-id", default="none", help="source run id, default: none")
    parser.add_argument("--sender-name", default="", help="sender agent alias/name")
    parser.add_argument("--sender-role", default="执行位", help="sender role")
    parser.add_argument("--owner-agent", default="", help="owner agent alias/name")
    parser.add_argument("--owner-session-id", default="", help="owner agent session id")
    parser.add_argument("--owner-channel", default="", help="owner channel name")
    parser.add_argument("--owner-role", default="主负责位", help="owner role")
    parser.add_argument("--client-message-id", default="", help="optional idempotency key")
    parser.add_argument("--base-url", default="http://localhost:18770", help="local dashboard origin for send")
    parser.add_argument("--token", default="", help="TASK_DASHBOARD_TOKEN override")
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    if include_message:
        msg = parser.add_mutually_exclusive_group()
        msg.add_argument("--message", default="", help="message text")
        msg.add_argument("--message-file", default="", help="read message text from local file")


def _add_wait_verify_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--wait-verify", action="store_true", help="after send, poll run evidence until delivered or timeout")
    parser.add_argument("--verify-timeout", type=float, default=30.0, help="seconds to wait for delivery evidence")
    parser.add_argument("--verify-interval", type=float, default=1.0, help="seconds between delivery evidence checks")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="qoreon message")
    sub = parser.add_subparsers(dest="command", required=True)

    resolve = sub.add_parser("resolve", help="resolve a target agent/session without sending")
    _add_common_options(resolve)
    resolve.set_defaults(func=_cmd_resolve)

    doctor = sub.add_parser("doctor", help="validate target and route prerequisites")
    _add_common_options(doctor, include_message=True)
    doctor.set_defaults(func=_cmd_doctor)

    draft = sub.add_parser("draft", help="build announce payload without sending")
    _add_common_options(draft, include_message=True)
    draft.set_defaults(func=_cmd_draft)

    send = sub.add_parser("send", help="send via POST /api/codex/announce")
    _add_common_options(send, include_message=True)
    send.add_argument("--dry-run", action="store_true", help="build and validate only; never call announce")
    _add_wait_verify_options(send)
    send.set_defaults(func=_cmd_send)

    verify = sub.add_parser("verify", help="verify delivery from run evidence")
    _add_common_options(verify)
    verify.add_argument("--run-id", default="", help="announce run id")
    verify.add_argument("--announce-run-id", default="", help="alias for --run-id")
    verify.set_defaults(func=_cmd_verify)

    status = sub.add_parser("status", help="print delivery status from run evidence")
    _add_common_options(status)
    status.add_argument("--run-id", default="", help="announce run id")
    status.add_argument("--announce-run-id", default="", help="alias for --run-id")
    status.set_defaults(func=_cmd_status)

    receipt = sub.add_parser("receipt", help="send a formal receipt through announce")
    _add_common_options(receipt, include_message=True)
    receipt.add_argument("--dry-run", action="store_true", help="build and validate only; never call announce")
    _add_wait_verify_options(receipt)
    receipt.set_defaults(func=_cmd_receipt)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
