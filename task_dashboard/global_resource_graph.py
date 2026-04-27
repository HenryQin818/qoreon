from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .domain import normalize_task_status
from .parser_md import iter_items
from .runtime.agent_display_name import attach_agent_display_fields
from .session_store import session_binding_sort_key
from .utils import iso_now_local


TERMINAL_RUN_STATUSES = {"done", "error"}
ACTIVE_RUN_STATUSES = {"queued", "running", "retry_waiting"}
ASSIST_OPEN_STATUSES = {"open", "pending_reply", "acknowledged", "in_progress", "replied"}
ASSIST_PENDING_REPLY_STATUSES = {"pending_reply"}
ASSIST_IN_PROGRESS_STATUSES = {"acknowledged", "in_progress", "replied"}
ASSIST_RESOLVED_STATUSES = {"resolved", "closed", "canceled"}


def _as_str(v: Any) -> str:
    return "" if v is None else str(v)


def _is_blank_attr(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, str):
        return not v.strip()
    if isinstance(v, (list, tuple, set, dict)):
        return not v
    return False


def _norm_ts(v: Any) -> float:
    raw = _as_str(v).strip()
    if not raw:
        return 0.0
    s = raw
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    if len(s) >= 5 and (s[-5] in {"+", "-"}) and s[-3] != ":":
        # +0800 -> +08:00
        s = s[:-2] + ":" + s[-2:]
    try:
        return datetime.fromisoformat(s).timestamp()
    except Exception:
        pass
    try:
        return datetime.fromisoformat(raw.replace(" ", "T")).timestamp()
    except Exception:
        return 0.0


def _freshness_level(ts: float) -> str:
    if ts <= 0:
        return "stale"
    age_h = max(0.0, (datetime.now().timestamp() - ts) / 3600.0)
    if age_h <= 2:
        return "hot"
    if age_h <= 24:
        return "warm"
    if age_h <= 72:
        return "cold"
    return "stale"


def _normalize_callback_to(v: Any) -> dict[str, str]:
    if not isinstance(v, dict):
        return {}
    channel_name = _as_str(v.get("channel_name") if "channel_name" in v else v.get("channelName")).strip()
    session_id = _as_str(v.get("session_id") if "session_id" in v else v.get("sessionId")).strip()
    out: dict[str, str] = {}
    if channel_name:
        out["channel_name"] = channel_name
    if session_id:
        out["session_id"] = session_id
    return out


def _append_unique(dst: list[str], value: str) -> None:
    v = _as_str(value).strip()
    if not v:
        return
    if v not in dst:
        dst.append(v)


def _task_title_from_path(path: str) -> str:
    raw = _as_str(path).strip()
    if not raw:
        return ""
    name = raw.split("/")[-1]
    if name.endswith(".md"):
        name = name[:-3]
    return name


def _task_status_bucket(status: Any) -> str:
    normalized = normalize_task_status(_as_str(status).strip())
    return _as_str(normalized.get("status_bucket")).strip() or "other"


def _normalize_task_path(value: Any) -> str:
    s = _as_str(value).replace("\\", "/").strip()
    if not s:
        return ""
    if s.startswith("task:"):
        s = s[5:]
    return s.strip()


def _normalize_assist_status(value: Any) -> str:
    s = _as_str(value).strip().lower()
    allowed = ASSIST_OPEN_STATUSES | ASSIST_RESOLVED_STATUSES | {"error"}
    if s in allowed:
        return s
    return "open"


def _normalize_support_level(value: Any) -> str:
    s = _as_str(value).strip().lower()
    if s in {"sufficient", "watch", "insufficient"}:
        return s
    return ""


def _derive_support_level(score: int) -> str:
    if score < 60:
        return "insufficient"
    if score < 80:
        return "watch"
    return "sufficient"


def _load_assist_request_index(*, run_store: Any, project_id: str) -> dict[str, list[dict[str, Any]]]:
    pid = _as_str(project_id).strip()
    if not pid:
        return {}
    runs_dir = getattr(run_store, "runs_dir", None)
    if not isinstance(runs_dir, Path):
        return {}
    root = runs_dir.parent / ".run" / "assist_requests" / pid
    if not root.exists() or not root.is_dir():
        return {}

    out: dict[str, list[dict[str, Any]]] = {}
    for path in sorted(root.glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(raw, dict):
            continue
        task_path = _normalize_task_path(raw.get("task_path"))
        if not task_path:
            continue
        status = _normalize_assist_status(raw.get("status"))
        support_score = -1
        try:
            support_score = int(raw.get("support_score"))
        except Exception:
            support_score = -1
        if support_score < 0:
            support_score = -1
        if support_score > 100:
            support_score = 100
        support_level = _normalize_support_level(raw.get("support_level"))
        threshold_triggered = bool(raw.get("threshold_triggered"))
        ts = max(_norm_ts(raw.get("updated_at")), _norm_ts(raw.get("created_at")))
        row = {
            "status": status,
            "support_score": support_score,
            "support_level": support_level,
            "threshold_triggered": threshold_triggered,
            "ts": ts,
        }
        out.setdefault(task_path, []).append(row)

    for key, rows in out.items():
        rows.sort(key=lambda x: float(x.get("ts") or 0.0), reverse=True)
        out[key] = rows
    return out


def _build_task_support_snapshot(task_path: Any, assist_index: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    key = _normalize_task_path(task_path)
    rows = assist_index.get(key, [])
    total = len(rows)
    if total <= 0:
        return {
            "assist_total": 0,
            "assist_open_count": 0,
            "assist_pending_reply_count": 0,
            "assist_in_progress_count": 0,
            "assist_resolved_count": 0,
            "assist_state": "none",
            "support_score": "",
            "support_level": "unknown",
            "threshold_triggered": False,
        }

    open_count = 0
    pending_reply_count = 0
    in_progress_count = 0
    resolved_count = 0
    threshold_triggered = False
    for row in rows:
        status = _normalize_assist_status(row.get("status"))
        if status in ASSIST_OPEN_STATUSES:
            open_count += 1
        if status in ASSIST_PENDING_REPLY_STATUSES:
            pending_reply_count += 1
        if status in ASSIST_IN_PROGRESS_STATUSES:
            in_progress_count += 1
        if status in ASSIST_RESOLVED_STATUSES:
            resolved_count += 1
        threshold_triggered = threshold_triggered or bool(row.get("threshold_triggered"))

    latest = rows[0] if rows else {}
    score = int(latest.get("support_score") or -1)
    if score < 0:
        if pending_reply_count > 0:
            score = 45
        elif open_count > 0:
            score = 65
        else:
            score = 85
    score = max(0, min(100, score))
    level = _normalize_support_level(latest.get("support_level")) or _derive_support_level(score)

    if pending_reply_count > 0:
        assist_state = "pending_reply"
    elif in_progress_count > 0:
        assist_state = "in_progress"
    elif open_count > 0:
        assist_state = "open"
    elif resolved_count > 0:
        assist_state = "resolved"
    else:
        assist_state = "none"

    threshold_triggered = threshold_triggered or level == "insufficient" or score < 60

    return {
        "assist_total": total,
        "assist_open_count": open_count,
        "assist_pending_reply_count": pending_reply_count,
        "assist_in_progress_count": in_progress_count,
        "assist_resolved_count": resolved_count,
        "assist_state": assist_state,
        "support_score": score,
        "support_level": level,
        "threshold_triggered": bool(threshold_triggered),
    }


def _status_from_title_or_path(text: Any) -> str:
    raw = _as_str(text).strip()
    if not raw:
        return ""
    left = raw.find("【")
    right = raw.find("】", left + 1) if left >= 0 else -1
    if left >= 0 and right > left + 1:
        token = raw[left + 1 : right].strip()
        if token:
            return token
    return ""


def _layout_level_for_node(row: dict[str, Any]) -> int:
    t = _as_str(row.get("type")).strip()
    if t == "project":
        return 0
    if t == "channel":
        return 1
    if t == "agent":
        return 2
    return 3


def _layout_xy(*, level: int, idx: int) -> tuple[int, int]:
    col = idx % 6
    row = idx // 6
    x = 180 + col * 240
    y = 120 + level * 180 + row * 120
    return x, y


def _agent_snapshot_label(name_state: Any) -> str:
    state = _as_str(name_state).strip().lower()
    if state == "polluted":
        return "名称异常"
    return "身份未解析"


def _build_org_snapshot(
    *,
    nodes: dict[str, dict[str, Any]],
    edges: list[dict[str, Any]],
    generated_at: str,
    project_id_filter: str,
) -> dict[str, Any]:
    included_types = {"project", "channel", "agent"}
    included_edge_types = {"project_channel", "channel_agent"}

    source_nodes = [
        row
        for row in nodes.values()
        if _as_str(row.get("type")).strip() in included_types
    ]
    source_nodes.sort(
        key=lambda x: (
            _layout_level_for_node(x),
            _as_str(x.get("project_id")).strip(),
            _as_str(x.get("channel_name")).strip(),
            _as_str(x.get("id")).strip(),
        )
    )

    level_counts: dict[int, int] = {}
    layout_nodes: list[dict[str, Any]] = []
    valid_node_ids: set[str] = set()
    project_ids: set[str] = set()

    for row in source_nodes:
        node_id = _as_str(row.get("id")).strip()
        if not node_id:
            continue
        level = _layout_level_for_node(row)
        idx = int(level_counts.get(level) or 0)
        level_counts[level] = idx + 1
        x, y = _layout_xy(level=level, idx=idx)

        node_type = _as_str(row.get("type")).strip()
        pid = _as_str(row.get("project_id")).strip()
        if pid:
            project_ids.add(pid)

        display = (
            _as_str(row.get("display_name")).strip()
            or _as_str(row.get("channel_display_name")).strip()
            or _as_str(row.get("label")).strip()
            or node_id
        )
        session_id = _as_str(row.get("session_id")).strip()
        layout_nodes.append(
            {
                "node_id": node_id,
                "agent_id": session_id if node_type == "agent" else "",
                "label": display,
                "x": x,
                "y": y,
                "meta": {
                    "node_type": node_type,
                    "project_id": pid,
                    "channel_name": _as_str(row.get("channel_name")).strip(),
                    "session_id": session_id,
                    "cli_type": _as_str(row.get("cli_type")).strip(),
                    "agent_state": _as_str(row.get("agent_state")).strip(),
                    "source": _as_str(row.get("source")).strip(),
                    "level": f"L{level}",
                },
            }
        )
        valid_node_ids.add(node_id)

    layout_edges: list[dict[str, Any]] = []
    edge_seen: set[str] = set()
    parent_by_node_id: dict[str, str] = {}
    for row in edges:
        edge_type = _as_str(row.get("type")).strip()
        if edge_type not in included_edge_types:
            continue
        source_node_id = _as_str(row.get("source")).strip()
        target_node_id = _as_str(row.get("target")).strip()
        if source_node_id not in valid_node_ids or target_node_id not in valid_node_ids:
            continue
        edge_id = _as_str(row.get("id")).strip() or f"{source_node_id}|{edge_type}|{target_node_id}"
        if edge_id in edge_seen:
            continue
        edge_seen.add(edge_id)
        parent_by_node_id.setdefault(target_node_id, source_node_id)
        layout_edges.append(
            {
                "edge_id": edge_id,
                "source_node_id": source_node_id,
                "target_node_id": target_node_id,
                "direction": "forward",
                "meta": {
                    "edge_type": edge_type,
                },
            }
        )

    snapshot_scope = project_id_filter or ("all" if len(project_ids) != 1 else next(iter(project_ids)))
    snapshot_id = f"org_snapshot:{snapshot_scope}:{generated_at}"
    for layout_node in layout_nodes:
        node_id = _as_str(layout_node.get("node_id")).strip()
        if node_id:
            layout_node["parent_node_id"] = parent_by_node_id.get(node_id, "")
    return {
        "snapshot_id": snapshot_id,
        "project_id": project_id_filter,
        "project_ids": sorted(project_ids),
        "generated_at": generated_at,
        "nodes": layout_nodes,
        "edges": layout_edges,
        "meta": {
            "model_version": "v1",
            "compatible_views": ["3d", "2d"],
            "fallback": "legacy_nodes_edges",
        },
    }


def _make_channel_meta_map(
    *,
    root: Path,
    project_cfg: dict[str, Any],
    project_id: str,
    session_store: Any,
) -> dict[str, dict[str, Any]]:
    channels_cfg = project_cfg.get("channels")
    if not isinstance(channels_cfg, list):
        channels_cfg = []

    out: dict[str, dict[str, Any]] = {}

    for ch in channels_cfg:
        if not isinstance(ch, dict):
            continue
        name = _as_str(ch.get("name")).strip()
        if not name:
            continue
        out[name] = {
            "name": name,
            "desc": _as_str(ch.get("desc")).strip(),
            "cli_type": _as_str(ch.get("cli_type")).strip() or "codex",
            "session_id": _as_str(ch.get("session_id")).strip(),
            "alias": _as_str(ch.get("alias")).strip(),
            "agent_name": _as_str(ch.get("agent_name") if "agent_name" in ch else ch.get("agentName")).strip(),
            "session_source": "config" if _as_str(ch.get("session_id")).strip() else "none",
        }

    try:
        sess_rows = session_store.list_sessions(project_id)
    except Exception:
        sess_rows = []
    if isinstance(sess_rows, list):
        for row in sorted(
            [x for x in sess_rows if isinstance(x, dict)],
            key=session_binding_sort_key,
            reverse=True,
        ):
            name = _as_str(row.get("channel_name")).strip()
            if not name:
                continue
            base = out.get(
                name,
                {
                    "name": name,
                    "desc": "",
                    "cli_type": "codex",
                    "session_id": "",
                    "alias": "",
                    "agent_name": "",
                },
            )
            sid = _as_str(row.get("id")).strip()
            if sid:
                base["session_id"] = sid
                base["alias"] = _as_str(row.get("alias")).strip() or _as_str(base.get("alias")).strip()
                base["agent_name"] = (
                    _as_str(row.get("agent_name") if "agent_name" in row else row.get("agentName")).strip()
                    or _as_str(base.get("agent_name")).strip()
                )
                base["cli_type"] = _as_str(row.get("cli_type")).strip() or _as_str(base.get("cli_type")).strip() or "codex"
                base["session_source"] = "session_store"
            out[name] = base
    return out


def build_global_resource_graph(
    *,
    cfg: dict[str, Any],
    root: Path,
    session_store: Any,
    run_store: Any,
    project_id: str = "",
    channel_name: str = "",
    run_limit: int = 600,
) -> dict[str, Any]:
    pid_filter = _as_str(project_id).strip()
    ch_filter = _as_str(channel_name).strip()
    max_runs = max(50, min(int(run_limit or 600), 5000))

    projects = cfg.get("projects")
    if not isinstance(projects, list):
        projects = []
    selected = []
    for p in projects:
        if not isinstance(p, dict):
            continue
        pid = _as_str(p.get("id")).strip()
        if not pid:
            continue
        if pid_filter and pid != pid_filter:
            continue
        selected.append(p)

    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    edge_seen: set[str] = set()

    index_project_channels: dict[str, list[str]] = {}
    index_channel_tasks: dict[str, list[str]] = {}
    index_channel_agents: dict[str, list[str]] = {}
    index_agent_runs: dict[str, list[str]] = {}

    queues: dict[str, list[dict[str, Any]]] = {
        "missing_session": [],
        "missing_feedback": [],
        "high_risk": [],
        "naming_issues": [],
    }

    channel_stats: dict[str, dict[str, Any]] = {}
    links: list[dict[str, Any]] = []

    feedback_pending_acceptance = 0
    active_agent_ids: set[str] = set()
    agent_latest_ctx: dict[str, dict[str, Any]] = {}

    def add_node(node_id: str, node_type: str, label: str, **attrs: Any) -> None:
        nid = _as_str(node_id).strip()
        if not nid:
            return
        cur = nodes.get(nid)
        if cur is None:
            row = {"id": nid, "type": node_type, "label": _as_str(label).strip() or nid}
            row.update(attrs)
            nodes[nid] = row
            return
        if not _as_str(cur.get("label")).strip() and _as_str(label).strip():
            cur["label"] = _as_str(label).strip()
        for k, v in attrs.items():
            if k not in cur or _is_blank_attr(cur.get(k)):
                cur[k] = v

    def add_edge(source: str, target: str, edge_type: str, **attrs: Any) -> None:
        src = _as_str(source).strip()
        dst = _as_str(target).strip()
        et = _as_str(edge_type).strip()
        if not src or not dst or not et:
            return
        eid = f"{src}|{et}|{dst}"
        if eid in edge_seen:
            return
        edge_seen.add(eid)
        row = {"id": eid, "source": src, "target": dst, "type": et}
        row.update(attrs)
        edges.append(row)

    def ensure_channel(project: str, channel: str, ch_meta: dict[str, dict[str, Any]]) -> tuple[str, dict[str, Any]]:
        cname = _as_str(channel).strip() or "未归类"
        channel_id = f"channel:{project}:{cname}"
        meta = ch_meta.get(
            cname,
            {
                "name": cname,
                "desc": "",
                "cli_type": "codex",
                "session_id": "",
                "alias": "",
                "agent_name": "",
                "session_source": "none",
            },
        )
        add_node(
            channel_id,
            "channel",
            cname,
            project_id=project,
            channel_name=cname,
            desc=_as_str(meta.get("desc")).strip(),
            cli_type=_as_str(meta.get("cli_type")).strip() or "codex",
            session_id=_as_str(meta.get("session_id")).strip(),
            session_alias=_as_str(meta.get("alias")).strip(),
            session_source=_as_str(meta.get("session_source")).strip() or "none",
        )
        stats = channel_stats.get(channel_id)
        if not isinstance(stats, dict):
            stats = {
                "project_id": project,
                "channel_name": cname,
                "session_id": _as_str(meta.get("session_id")).strip(),
                "task_total": 0,
                "task_active": 0,
                "task_supervised": 0,
                "task_in_progress": 0,
                "runs_total": 0,
                "runs_running": 0,
                "runs_queued": 0,
                "runs_retry": 0,
                "runs_error": 0,
                "runs_done": 0,
                "missing_feedback": 0,
                "latest_ts": 0.0,
            }
            channel_stats[channel_id] = stats
        return channel_id, stats

    for p in selected:
        pid = _as_str(p.get("id")).strip()
        pname = _as_str(p.get("name")).strip() or pid
        if not pid:
            continue

        project_node_id = f"project:{pid}"
        add_node(project_node_id, "project", pname, project_id=pid, project_name=pname)
        index_project_channels.setdefault(pid, [])

        channel_meta = _make_channel_meta_map(root=root, project_cfg=p, project_id=pid, session_store=session_store)

        for ch_name in sorted(channel_meta.keys()):
            if ch_filter and ch_name != ch_filter:
                continue
            ch_id, _ = ensure_channel(pid, ch_name, channel_meta)
            add_edge(project_node_id, ch_id, "project_channel")
            _append_unique(index_project_channels[pid], ch_id)

            session_id = _as_str(channel_meta.get(ch_name, {}).get("session_id")).strip()
            session_source = _as_str(channel_meta.get(ch_name, {}).get("session_source")).strip() or "unknown"
            if session_id and session_source != "config":
                session_alias = _as_str(channel_meta.get(ch_name, {}).get("alias")).strip()
                agent_id = f"agent:{pid}:{session_id}"
                add_node(
                    agent_id,
                    "agent",
                    session_alias or _as_str(channel_meta.get(ch_name, {}).get("agent_name")).strip() or session_id,
                    project_id=pid,
                    channel_name=ch_name,
                    channel_display_name=ch_name,
                    session_id=session_id,
                    alias=session_alias,
                    session_alias=session_alias,
                    agent_name=_as_str(channel_meta.get(ch_name, {}).get("agent_name")).strip(),
                    cli_type=_as_str(channel_meta.get(ch_name, {}).get("cli_type")).strip() or "codex",
                    source=session_source,
                )
                add_edge(ch_id, agent_id, "channel_agent")
                index_channel_agents.setdefault(ch_id, [])
                _append_unique(index_channel_agents[ch_id], agent_id)

        task_root_rel = _as_str(p.get("task_root_rel")).strip()
        if task_root_rel:
            items = iter_items(
                root=root,
                project_id=pid,
                project_name=pname,
                task_root_rel=task_root_rel,
                exclude_rel_prefixes=[],
            )
        else:
            items = []

        assist_index = _load_assist_request_index(run_store=run_store, project_id=pid)

        task_code_map: dict[str, list[str]] = {}
        feedback_code_map: dict[str, list[str]] = {}

        for it in items:
            cname = _as_str(it.channel).strip() or "未归类"
            if ch_filter and cname != ch_filter:
                continue
            ch_id, st = ensure_channel(pid, cname, channel_meta)
            add_edge(project_node_id, ch_id, "project_channel")
            _append_unique(index_project_channels[pid], ch_id)

            node_type = "feedback" if _as_str(it.type).strip() == "反馈" else "task"
            node_id = f"{node_type}:{_as_str(it.path).strip()}"
            item_status = _as_str(it.status).strip()
            normalized_status = normalize_task_status(item_status)
            add_node(
                node_id,
                node_type,
                _as_str(it.title).strip() or _as_str(it.path).strip(),
                project_id=pid,
                channel_name=cname,
                status=item_status,
                primary_status=_as_str(normalized_status.get("primary_status")).strip(),
                lifecycle_state=_as_str(normalized_status.get("lifecycle_state")).strip(),
                counts_as_wip=bool(normalized_status.get("counts_as_wip")),
                status_flags=normalized_status.get("status_flags") or {},
                status_bucket=_as_str(normalized_status.get("status_bucket")).strip() or "other",
                item_type=_as_str(it.type).strip(),
                code=_as_str(it.code).strip(),
                path=_as_str(it.path).strip(),
                updated_at=_as_str(it.updated_at).strip(),
                owner=_as_str(it.owner).strip(),
                due=_as_str(it.due).strip(),
                main_owner=it.main_owner,
                collaborators=it.collaborators,
                validators=it.validators,
                challengers=it.challengers,
                backup_owners=it.backup_owners,
                management_slot=it.management_slot,
                custom_roles=it.custom_roles,
                executors=it.executors,
                acceptors=it.acceptors,
                reviewers=it.reviewers,
                visual_reviewers=it.visual_reviewers,
                **(_build_task_support_snapshot(it.path, assist_index) if node_type == "task" else {}),
            )
            add_edge(ch_id, node_id, "channel_item")

            if node_type == "task":
                index_channel_tasks.setdefault(ch_id, [])
                _append_unique(index_channel_tasks[ch_id], node_id)

            st["task_total"] += 1
            if bool(normalized_status.get("is_active")):
                st["task_active"] += 1
            status_flags = normalized_status.get("status_flags") if isinstance(normalized_status.get("status_flags"), dict) else {}
            if bool(status_flags.get("supervised")):
                st["task_supervised"] += 1
            if bool(normalized_status.get("counts_as_wip")):
                st["task_in_progress"] += 1
            status = _as_str(it.status).strip()
            if node_type == "feedback" and status == "待验收":
                feedback_pending_acceptance += 1

            ts = _norm_ts(it.updated_at)
            if ts > st["latest_ts"]:
                st["latest_ts"] = ts

            code = _as_str(it.code).strip()
            if code:
                ckey = f"{pid}::{cname}::{code}"
                if node_type == "feedback":
                    feedback_code_map.setdefault(ckey, [])
                    _append_unique(feedback_code_map[ckey], node_id)
                else:
                    task_code_map.setdefault(ckey, [])
                    _append_unique(task_code_map[ckey], node_id)

            if not status:
                queues["naming_issues"].append(
                    {
                        "project_id": pid,
                        "channel_name": cname,
                        "path": _as_str(it.path).strip(),
                        "reason": "missing_status_tag",
                    }
                )

        for ckey, task_ids in task_code_map.items():
            fb_ids = feedback_code_map.get(ckey, [])
            for tid in task_ids:
                for fid in fb_ids:
                    add_edge(tid, fid, "task_feedback")

        try:
            runs = run_store.list_runs(project_id=pid, limit=max_runs)
        except Exception:
            runs = []
        project_agent_ids: set[str] = set()
        for meta in channel_meta.values():
            if not isinstance(meta, dict):
                continue
            sid_cfg = _as_str(meta.get("session_id")).strip()
            session_source = _as_str(meta.get("session_source")).strip()
            if sid_cfg and session_source != "config":
                project_agent_ids.add(sid_cfg)
        for run_meta in runs:
            if not isinstance(run_meta, dict):
                continue
            sid_run = _as_str(run_meta.get("sessionId")).strip()
            if sid_run:
                project_agent_ids.add(sid_run)

        for run in runs:
            if not isinstance(run, dict):
                continue
            run_id = _as_str(run.get("id")).strip()
            if not run_id:
                continue
            cname = _as_str(run.get("channelName")).strip() or "未归类"
            if ch_filter and cname != ch_filter:
                continue
            ch_id, st = ensure_channel(pid, cname, channel_meta)
            add_edge(project_node_id, ch_id, "project_channel")
            _append_unique(index_project_channels[pid], ch_id)

            r_status = _as_str(run.get("status")).strip().lower()
            run_node_id = f"run:{run_id}"
            add_node(
                run_node_id,
                "run",
                run_id,
                project_id=pid,
                channel_name=cname,
                run_id=run_id,
                status=r_status,
                session_id=_as_str(run.get("sessionId")).strip(),
                sender_type=_as_str(run.get("sender_type")).strip(),
                sender_id=_as_str(run.get("sender_id")).strip(),
                sender_name=_as_str(run.get("sender_name")).strip(),
                created_at=_as_str(run.get("createdAt")).strip(),
                started_at=_as_str(run.get("startedAt")).strip(),
                finished_at=_as_str(run.get("finishedAt")).strip(),
                error=_as_str(run.get("error")).strip(),
                task_path=_as_str(run.get("task_path")).strip(),
            )
            add_edge(ch_id, run_node_id, "channel_run")

            run_ts = 0.0
            for ts_raw in (run.get("finishedAt"), run.get("startedAt"), run.get("createdAt")):
                ts = _norm_ts(ts_raw)
                if ts > run_ts:
                    run_ts = ts

            st["runs_total"] += 1
            if r_status == "running":
                st["runs_running"] += 1
            elif r_status == "queued":
                st["runs_queued"] += 1
            elif r_status == "retry_waiting":
                st["runs_retry"] += 1
            elif r_status == "error":
                st["runs_error"] += 1
            elif r_status == "done":
                st["runs_done"] += 1

            if run_ts > st["latest_ts"]:
                st["latest_ts"] = run_ts

            sid = _as_str(run.get("sessionId")).strip()
            task_path = _as_str(run.get("task_path")).strip()
            if sid:
                session_alias = _as_str(channel_meta.get(cname, {}).get("alias")).strip()
                agent_id = f"agent:{pid}:{sid}"
                add_node(
                    agent_id,
                    "agent",
                    session_alias or _as_str(channel_meta.get(cname, {}).get("agent_name")).strip() or sid,
                    project_id=pid,
                    channel_name=cname,
                    channel_display_name=cname,
                    session_id=sid,
                    alias=session_alias,
                    session_alias=session_alias,
                    agent_name=_as_str(channel_meta.get(cname, {}).get("agent_name")).strip(),
                    cli_type=_as_str(run.get("cliType")).strip() or "codex",
                    source="run_meta",
                )
                add_edge(ch_id, agent_id, "channel_agent")
                add_edge(agent_id, run_node_id, "agent_run")
                index_channel_agents.setdefault(ch_id, [])
                _append_unique(index_channel_agents[ch_id], agent_id)
                index_agent_runs.setdefault(agent_id, [])
                _append_unique(index_agent_runs[agent_id], run_node_id)
                if r_status in ACTIVE_RUN_STATUSES:
                    active_agent_ids.add(agent_id)
                if task_path:
                    prev = agent_latest_ctx.get(agent_id)
                    prev_ts = float(prev.get("ts") or 0.0) if isinstance(prev, dict) else 0.0
                    if run_ts >= prev_ts:
                        agent_latest_ctx[agent_id] = {
                            "ts": run_ts,
                            "task_path": task_path,
                            "task_title": _task_title_from_path(task_path),
                            "run_id": run_id,
                            "run_status": r_status,
                            "run_at": datetime.fromtimestamp(run_ts).astimezone().isoformat(timespec="seconds") if run_ts > 0 else "",
                        }

            if task_path:
                task_node_id = f"task:{task_path}"
                add_node(
                    task_node_id,
                    "task",
                    task_path.split("/")[-1].replace(".md", ""),
                    project_id=pid,
                    channel_name=cname,
                    path=task_path,
                    status="",
                    primary_status="",
                    lifecycle_state="unknown",
                    counts_as_wip=False,
                    status_flags={},
                    status_bucket="other",
                    item_type="任务",
                    source="run_meta",
                    **_build_task_support_snapshot(task_path, assist_index),
                )
                add_edge(task_node_id, run_node_id, "task_run")
                index_channel_tasks.setdefault(ch_id, [])
                _append_unique(index_channel_tasks[ch_id], task_node_id)

            callback_to = _normalize_callback_to(run.get("callback_to"))
            if callback_to:
                target_channel = _as_str(callback_to.get("channel_name")).strip()
                target_sid = _as_str(callback_to.get("session_id")).strip()
                if target_sid and target_sid in project_agent_ids:
                    target_alias = _as_str(channel_meta.get(target_channel, {}).get("alias")).strip()
                    target_agent_id = f"agent:{pid}:{target_sid}"
                    add_node(
                        target_agent_id,
                        "agent",
                        target_alias or _as_str(channel_meta.get(target_channel, {}).get("agent_name")).strip() or target_sid,
                        project_id=pid,
                        channel_name=target_channel,
                        channel_display_name=target_channel,
                        session_id=target_sid,
                        alias=target_alias,
                        session_alias=target_alias,
                        agent_name=_as_str(channel_meta.get(target_channel, {}).get("agent_name")).strip(),
                        cli_type="codex",
                        source="callback_to",
                    )
                    add_edge(run_node_id, target_agent_id, "run_callback")
                    if target_channel:
                        t_ch_id, _ = ensure_channel(pid, target_channel, channel_meta)
                        add_edge(project_node_id, t_ch_id, "project_channel")
                        _append_unique(index_project_channels[pid], t_ch_id)
                        add_edge(t_ch_id, target_agent_id, "channel_agent")
                        index_channel_agents.setdefault(t_ch_id, [])
                        _append_unique(index_channel_agents[t_ch_id], target_agent_id)
                elif target_channel and target_channel in channel_meta:
                    t_ch_id, _ = ensure_channel(pid, target_channel, channel_meta)
                    add_edge(project_node_id, t_ch_id, "project_channel")
                    _append_unique(index_project_channels[pid], t_ch_id)
                    add_edge(run_node_id, t_ch_id, "run_callback")

            feedback_path = _as_str(run.get("feedback_file_path")).strip()
            if feedback_path:
                fb_node_id = f"feedback:{feedback_path}"
                add_node(
                    fb_node_id,
                    "feedback",
                    feedback_path.split("/")[-1].replace(".md", ""),
                    project_id=pid,
                    channel_name=cname,
                    path=feedback_path,
                    status="",
                    source="run_meta",
                )
                add_edge(run_node_id, fb_node_id, "run_feedback")
            elif r_status in TERMINAL_RUN_STATUSES:
                st["missing_feedback"] += 1
                queues["missing_feedback"].append(
                    {
                        "project_id": pid,
                        "channel_name": cname,
                        "run_id": run_id,
                        "run_status": r_status,
                        "reason": "terminal_without_feedback_file",
                    }
                )

    for channel_id, st in channel_stats.items():
        pid = _as_str(st.get("project_id")).strip()
        cname = _as_str(st.get("channel_name")).strip()
        session_id = _as_str(st.get("session_id")).strip()
        task_active = int(st.get("task_active") or 0)
        task_supervised = int(st.get("task_supervised") or 0)
        task_in_progress = int(st.get("task_in_progress") or 0)
        runs_error = int(st.get("runs_error") or 0)
        runs_retry = int(st.get("runs_retry") or 0)
        runs_running = int(st.get("runs_running") or 0)
        runs_queued = int(st.get("runs_queued") or 0)
        missing_feedback = int(st.get("missing_feedback") or 0)
        latest_ts = float(st.get("latest_ts") or 0.0)

        missing_session = bool(task_active > 0 and not session_id)
        risk_score = (
            task_supervised * 16
            + runs_error * 35
            + runs_retry * 22
            + missing_feedback * 18
            + (30 if missing_session else 0)
            + (8 if task_in_progress > 0 else 0)
        )
        risk_score = max(0, min(100, int(risk_score)))
        activity_score = (
            runs_running * 38
            + runs_queued * 20
            + task_in_progress * 8
            + min(20, task_active * 2)
        )
        activity_score = max(0, min(100, int(activity_score)))
        freshness = _freshness_level(latest_ts)

        risk_reasons: list[dict[str, Any]] = []
        if runs_error > 0:
            risk_reasons.append({"code": "runs_error", "label": "运行报错", "value": runs_error, "score": runs_error * 35})
        if runs_retry > 0:
            risk_reasons.append({"code": "runs_retry_waiting", "label": "重试等待", "value": runs_retry, "score": runs_retry * 22})
        if missing_feedback > 0:
            risk_reasons.append({"code": "missing_feedback", "label": "终态缺反馈", "value": missing_feedback, "score": missing_feedback * 18})
        if missing_session:
            risk_reasons.append({"code": "missing_session", "label": "活跃任务缺会话绑定", "value": 1, "score": 30})
        if task_supervised > 0:
            risk_reasons.append({"code": "task_supervised", "label": "督办任务", "value": task_supervised, "score": task_supervised * 16})
        if task_in_progress > 0:
            risk_reasons.append({"code": "task_in_progress", "label": "进行中任务", "value": task_in_progress, "score": 8})
        risk_reasons = sorted(risk_reasons, key=lambda x: int(x.get("score") or 0), reverse=True)[:3]

        if missing_session:
            queues["missing_session"].append(
                {
                    "project_id": pid,
                    "channel_name": cname,
                    "channel_id": channel_id,
                    "reason": "active_tasks_without_session",
                }
            )

        link_status = "complete"
        if missing_session:
            link_status = "missing_session"
        elif missing_feedback > 0:
            link_status = "missing_feedback"
        elif runs_error > 0:
            link_status = "at_risk"
        elif task_active > 0 and int(st.get("runs_total") or 0) == 0:
            link_status = "missing_run"

        cur = nodes.get(channel_id, {})
        if isinstance(cur, dict):
            cur["risk_score"] = risk_score
            cur["activity_score"] = activity_score
            cur["freshness_level"] = freshness
            cur["link_status"] = link_status
            cur["risk_reasons"] = risk_reasons
            cur["latest_at"] = datetime.fromtimestamp(latest_ts).astimezone().isoformat(timespec="seconds") if latest_ts > 0 else ""

        link_item = {
            "channel_id": channel_id,
            "project_id": pid,
            "channel_name": cname,
            "session_id": session_id,
            "risk_score": risk_score,
            "activity_score": activity_score,
            "freshness_level": freshness,
            "link_status": link_status,
            "risk_reasons": risk_reasons,
            "latest_at": datetime.fromtimestamp(latest_ts).astimezone().isoformat(timespec="seconds") if latest_ts > 0 else "",
            "counts": {
                "task_total": int(st.get("task_total") or 0),
                "task_active": task_active,
                "task_supervised": task_supervised,
                "task_in_progress": task_in_progress,
                "runs_total": int(st.get("runs_total") or 0),
                "runs_running": runs_running,
                "runs_queued": runs_queued,
                "runs_retry": runs_retry,
                "runs_error": runs_error,
                "runs_done": int(st.get("runs_done") or 0),
                "missing_feedback": missing_feedback,
            },
        }
        links.append(link_item)
        if risk_score >= 70:
            queues["high_risk"].append(link_item)

    for agent_id, ctx in agent_latest_ctx.items():
        cur = nodes.get(agent_id)
        if not isinstance(cur, dict):
            continue
        cur["current_task_path"] = _as_str(ctx.get("task_path")).strip()
        cur["current_task_title"] = _as_str(ctx.get("task_title")).strip()
        cur["current_run_id"] = _as_str(ctx.get("run_id")).strip()
        cur["current_run_status"] = _as_str(ctx.get("run_status")).strip()
        cur["current_run_at"] = _as_str(ctx.get("run_at")).strip()

    parent_by_node_id: dict[str, str] = {}
    for edge in edges:
        edge_type = _as_str(edge.get("type")).strip()
        if edge_type not in {"project_channel", "channel_agent"}:
            continue
        source_id = _as_str(edge.get("source")).strip()
        target_id = _as_str(edge.get("target")).strip()
        if source_id and target_id:
            parent_by_node_id.setdefault(target_id, source_id)
    for node_id, row in nodes.items():
        row["parent_node_id"] = parent_by_node_id.get(node_id, "")

    for row in nodes.values():
        if _as_str(row.get("type")).strip() != "agent":
            continue
        resolved = attach_agent_display_fields(row)
        row.update(
            {
                "agent_display_name": _as_str(resolved.get("agent_display_name")).strip(),
                "agent_display_name_source": _as_str(resolved.get("agent_display_name_source")).strip(),
                "agent_name_state": _as_str(resolved.get("agent_name_state")).strip(),
                "agent_display_issue": _as_str(resolved.get("agent_display_issue")).strip(),
            }
        )
        channel_name = _as_str(row.get("channel_name")).strip()
        display_name = _as_str(row.get("agent_display_name")).strip()
        if not display_name:
            display_name = _agent_snapshot_label(row.get("agent_name_state"))
        if display_name:
            row["display_name"] = display_name
            row["label"] = display_name
        if channel_name:
            row["channel_display_name"] = channel_name

        run_status = _as_str(row.get("current_run_status") or "").strip().lower()
        active = str(row.get("id") or "") in active_agent_ids
        if run_status in ACTIVE_RUN_STATUSES:
            active = True
        row["agent_state"] = "active" if active else "idle"
        row["status"] = "active" if active else "idle"

    for row in nodes.values():
        if _as_str(row.get("type")).strip() != "task":
            continue
        status = _as_str(row.get("status")).strip()
        if not status:
            status = _status_from_title_or_path(row.get("label")) or _status_from_title_or_path(row.get("path"))
            if status:
                row["status"] = status
        normalized_status = normalize_task_status(status)
        should_refresh_normalized = (
            not _as_str(row.get("primary_status")).strip()
            or not isinstance(row.get("status_flags"), dict)
            or not _as_str(row.get("status_bucket")).strip()
            or _as_str(row.get("status_bucket")).strip() == "other"
        )
        if should_refresh_normalized:
            row["primary_status"] = _as_str(normalized_status.get("primary_status")).strip()
            row["lifecycle_state"] = _as_str(normalized_status.get("lifecycle_state")).strip()
            row["counts_as_wip"] = bool(normalized_status.get("counts_as_wip"))
            row["status_flags"] = normalized_status.get("status_flags") or {}
            row["status_bucket"] = _as_str(normalized_status.get("status_bucket")).strip() or "other"

    queues["high_risk"] = sorted(queues["high_risk"], key=lambda x: int(x.get("risk_score") or 0), reverse=True)[:200]

    type_counts: dict[str, int] = {}
    for n in nodes.values():
        t = _as_str(n.get("type")).strip() or "unknown"
        type_counts[t] = int(type_counts.get(t) or 0) + 1

    run_status_counts: dict[str, int] = {}
    for n in nodes.values():
        if _as_str(n.get("type")).strip() != "run":
            continue
        st = _as_str(n.get("status")).strip() or "unknown"
        run_status_counts[st] = int(run_status_counts.get(st) or 0) + 1

    assist_stats = {
        "tasks_with_assist": 0,
        "assist_pending_reply": 0,
        "assist_in_progress": 0,
        "assist_resolved": 0,
        "support_insufficient": 0,
    }
    for n in nodes.values():
        if _as_str(n.get("type")).strip() != "task":
            continue
        assist_total = int(n.get("assist_total") or 0)
        if assist_total > 0:
            assist_stats["tasks_with_assist"] += 1
        assist_state = _as_str(n.get("assist_state")).strip()
        if assist_state == "pending_reply":
            assist_stats["assist_pending_reply"] += 1
        elif assist_state in {"in_progress", "open"}:
            assist_stats["assist_in_progress"] += 1
        elif assist_state == "resolved":
            assist_stats["assist_resolved"] += 1
        support_level = _as_str(n.get("support_level")).strip()
        support_score = n.get("support_score")
        score_n = -1
        try:
            score_n = int(support_score)
        except Exception:
            score_n = -1
        if support_level == "insufficient" or (score_n >= 0 and score_n < 60):
            assist_stats["support_insufficient"] += 1

    generated_at = iso_now_local()
    org_snapshot = _build_org_snapshot(
        nodes=nodes,
        edges=edges,
        generated_at=generated_at,
        project_id_filter=pid_filter,
    )

    out = {
        "version": "v1",
        "generated_at": generated_at,
        "filters": {
            "project_id": pid_filter,
            "channel_name": ch_filter,
            "run_limit": max_runs,
        },
        "stats": {
            "projects": len({str(n.get("project_id") or "") for n in nodes.values() if n.get("type") == "project"}),
            "channels": int(type_counts.get("channel") or 0),
            "tasks": int(type_counts.get("task") or 0),
            "feedback": int(type_counts.get("feedback") or 0),
            "agents_total": int(type_counts.get("agent") or 0),
            "agents_active": len(active_agent_ids),
            "runs_total": int(type_counts.get("run") or 0),
            "runs_running": int(run_status_counts.get("running") or 0),
            "feedback_pending_acceptance": int(feedback_pending_acceptance),
            "links_high_risk": len(queues["high_risk"]),
            "edges_total": len(edges),
            "tasks_with_assist": int(assist_stats["tasks_with_assist"]),
            "assist_pending_reply": int(assist_stats["assist_pending_reply"]),
            "assist_in_progress": int(assist_stats["assist_in_progress"]),
            "assist_resolved": int(assist_stats["assist_resolved"]),
            "support_insufficient": int(assist_stats["support_insufficient"]),
        },
        "schema": {
            "node_types": ["project", "channel", "task", "agent", "run", "feedback"],
            "edge_types": ["project_channel", "channel_item", "channel_agent", "channel_run", "agent_run", "run_feedback", "run_callback", "task_feedback", "task_run"],
        },
        "nodes": sorted(nodes.values(), key=lambda x: (_as_str(x.get("type")), _as_str(x.get("id")))),
        "edges": sorted(edges, key=lambda x: _as_str(x.get("id"))),
        "links": sorted(links, key=lambda x: (str(x.get("project_id") or ""), -int(x.get("risk_score") or 0), str(x.get("channel_name") or ""))),
        "queues": queues,
        "index": {
            "project_channels": {k: sorted(v) for k, v in index_project_channels.items()},
            "channel_tasks": {k: sorted(v) for k, v in index_channel_tasks.items()},
            "channel_agents": {k: sorted(v) for k, v in index_channel_agents.items()},
            "agent_runs": {k: sorted(v) for k, v in index_agent_runs.items()},
        },
        "org_snapshot": org_snapshot,
        "unified_model": {
            "model_version": "v1",
            "compatible_views": ["3d", "2d"],
            "structure": {
                "snapshot_ref": "org_snapshot",
                "node_fields": ["node_id", "agent_id", "label", "x", "y", "meta"],
                "edge_fields": ["edge_id", "source_node_id", "target_node_id", "direction", "meta"],
            },
            "runtime": {
                "source_api": "/api/projects/{project_id}/runtime-bubbles",
                "relation_fields": [
                    "runtime_id",
                    "project_id",
                    "source_agent_id",
                    "target_agent_id",
                    "reason",
                    "started_at",
                    "ttl_seconds",
                    "expires_at",
                    "related_run_id",
                ],
            },
        },
    }
    return out
