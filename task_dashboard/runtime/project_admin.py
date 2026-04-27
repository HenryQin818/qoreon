from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

try:
    import tomllib  # py311+
except Exception:  # pragma: no cover
    import tomli as tomllib  # type: ignore

from task_dashboard.helpers import atomic_write_text
from task_dashboard.runtime.session_admin import create_session_response
from task_dashboard.runtime.session_routes import dedup_session_channel_response


_VALID_PROJECT_ID_RE = re.compile(r"^[a-z][a-z0-9_]{1,79}$")
_VALID_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
_KNOWN_CLI_TYPES = {"codex", "claude", "opencode", "gemini", "trae"}
_DEFAULT_CHANNEL_BOOTSTRAP_SUBDIRS = [
    "任务",
    "问题",
    "产出物/材料",
    "产出物/沉淀",
    "已完成",
    "暂缓",
]
_DEFAULT_CHANNEL_BOOTSTRAP_MARKER_FILES = {
    "已完成/目录.md": "# 已完成目录\n\n用于归档本分工下已完成且完成收口的任务文档。\n",
    "产出物/沉淀/目录.md": "# 沉淀目录\n\n用于沉淀可复用的方法、规范、结论与经验。\n",
}


def _safe_text(value: Any, limit: int = 4000) -> str:
    return str(value or "").strip()[:limit]


def _coerce_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return bool(default)


def _normalize_reasoning_effort(value: Any) -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "xhigh": "extra_high",
        "very_high": "extra_high",
        "ultra": "extra_high",
        "extra": "extra_high",
    }
    text = aliases.get(text, text)
    if text in {"low", "medium", "high", "extra_high"}:
        return text
    return ""


def _normalize_rel_path_text(raw: Any) -> str:
    return str(raw or "").strip().replace("\\", "/")


def _resolve_project_path(raw: str, repo_root: Path) -> Path:
    text = _normalize_rel_path_text(raw)
    if not text:
        return repo_root.resolve()
    path = Path(text).expanduser()
    if path.is_absolute():
        return path.resolve()

    candidates = [(repo_root / path).resolve()]
    for parent in repo_root.parents:
        candidates.append((parent / path).resolve())
    existing = [item for item in candidates if item.exists()]
    if existing:
        existing.sort(key=lambda item: len(item.parts))
        return existing[0]

    norm = text.strip("/")
    for anchor in (repo_root,) + tuple(repo_root.parents):
        marker = anchor.name.strip()
        if not marker:
            continue
        if norm == marker or norm.startswith(marker + "/"):
            return (anchor.parent / norm).resolve()
    return candidates[0]


def _toml_scalar_literal(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return json.dumps(str(value), ensure_ascii=False)


def _load_toml(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    obj = tomllib.loads(raw.decode("utf-8"))
    return obj if isinstance(obj, dict) else {}


def _session_store_path_for(project_id: str, sessions_root: Path) -> Path:
    safe_id = project_id.replace("/", "_").replace("\\", "_").replace("..", "_")
    return (sessions_root / f"{safe_id}.json").resolve()


def _align_execution_context_to_session_store(*, spec: dict[str, Any], session_store: Any) -> None:
    sessions_dir = getattr(session_store, "sessions_dir", None)
    if not sessions_dir:
        return
    try:
        sessions_root = Path(sessions_dir).resolve()
    except Exception:
        return
    runtime_root = sessions_root.parent
    execution_context = spec.get("execution_context")
    if not isinstance(execution_context, dict):
        return
    execution_context["runtime_root"] = str(runtime_root)
    execution_context["sessions_root"] = str(sessions_root)
    execution_context["runs_root"] = str((runtime_root / ".runs").resolve())
    spec["session_store_path"] = _session_store_path_for(spec["project_id"], sessions_root)


def _default_links(
    *,
    project_id: str,
    project_root_rel: str,
    task_root_rel: str,
) -> list[dict[str, str]]:
    project_root_rel = _normalize_rel_path_text(project_root_rel)
    task_root_rel = _normalize_rel_path_text(task_root_rel)
    return [
        {"label": "工作空间", "url": f"file:{project_root_rel}"},
        {"label": "任务规划", "url": f"file:{task_root_rel}"},
        {"label": "README", "url": f"file:{project_root_rel}/README.md"},
        {"label": "项目会话真源", "url": f"file:.runtime/stable/.sessions/{project_id}.json"},
    ]


def _merge_links(
    default_links: list[dict[str, str]],
    extra_links: list[dict[str, str]],
) -> list[dict[str, str]]:
    ordered: list[dict[str, str]] = []
    by_label: dict[str, dict[str, str]] = {}

    for row in default_links + extra_links:
        label = _safe_text((row or {}).get("label"), 200)
        url = _safe_text((row or {}).get("url"), 4000)
        if not label or not url:
            continue
        normalized = {"label": label, "url": url}
        by_label[label] = normalized

    seen: set[str] = set()
    for row in default_links + extra_links:
        label = _safe_text((row or {}).get("label"), 200)
        if not label or label in seen or label not in by_label:
            continue
        ordered.append(by_label[label])
        seen.add(label)
    return ordered


def _normalize_channels(raw: Any) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        return []
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = _safe_text(item.get("name"), 240)
        if not name:
            continue
        if name in seen:
            raise ValueError(f"duplicate channel name: {name}")
        seen.add(name)
        cli_type = _safe_text(item.get("cli_type") if "cli_type" in item else item.get("cliType"), 40).lower() or "codex"
        if cli_type not in _KNOWN_CLI_TYPES:
            raise ValueError(f"invalid cli_type for channel '{name}': {cli_type}")
        rows.append(
            {
                "name": name,
                "desc": _safe_text(item.get("desc"), 500) or name,
                "cli_type": cli_type,
                "model": _safe_text(item.get("model"), 200),
                "reasoning_effort": _normalize_reasoning_effort(
                    item.get("reasoning_effort") if "reasoning_effort" in item else item.get("reasoningEffort")
                ),
            }
        )
    return rows


def _normalize_execution_context(
    raw: Any,
    *,
    project_root: Path,
    repo_root: Path,
) -> dict[str, str]:
    source = raw if isinstance(raw, dict) else {}
    server_port = _safe_text(source.get("server_port") if "server_port" in source else source.get("serverPort"), 80)
    runtime_root = Path(
        _safe_text(source.get("runtime_root") if "runtime_root" in source else source.get("runtimeRoot"), 4000)
        or str((repo_root / ".runtime" / "stable").resolve())
    )
    sessions_root = Path(
        _safe_text(source.get("sessions_root") if "sessions_root" in source else source.get("sessionsRoot"), 4000)
        or str((runtime_root / ".sessions").resolve())
    )
    runs_root = Path(
        _safe_text(source.get("runs_root") if "runs_root" in source else source.get("runsRoot"), 4000)
        or str((runtime_root / ".runs").resolve())
    )
    health_source = _safe_text(
        source.get("health_source") if "health_source" in source else source.get("healthSource"),
        4000,
    )
    if not health_source and server_port:
        health_source = f"http://127.0.0.1:{server_port}/__health"
    return {
        "profile": _safe_text(source.get("profile"), 80) or "project_privileged_full",
        "environment": _safe_text(source.get("environment"), 80) or "stable",
        "worktree_root": _safe_text(source.get("worktree_root") if "worktree_root" in source else source.get("worktreeRoot"), 4000)
        or str(project_root),
        "workdir": _safe_text(source.get("workdir"), 4000) or str(project_root),
        "branch": _safe_text(source.get("branch"), 240),
        "runtime_root": str(runtime_root.resolve()),
        "sessions_root": str(sessions_root.resolve()),
        "runs_root": str(runs_root.resolve()),
        "server_port": server_port,
        "health_source": health_source,
    }


def _normalize_links(raw: Any) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        return []
    rows: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        label = _safe_text(item.get("label"), 200)
        url = _safe_text(item.get("url"), 4000)
        if label and url:
            rows.append({"label": label, "url": url})
    return rows


def _normalize_bootstrap_options(raw: Any, channel_names: list[str]) -> dict[str, Any]:
    source = raw if isinstance(raw, dict) else {}
    primary_channel_names_raw = source.get("primary_channel_names") if "primary_channel_names" in source else source.get("primaryChannelNames")
    primary_channel_names: list[str] = []
    if isinstance(primary_channel_names_raw, list):
        for item in primary_channel_names_raw:
            name = _safe_text(item, 240)
            if not name:
                continue
            primary_channel_names.append(name)
    invalid = [name for name in primary_channel_names if name not in channel_names]
    if invalid:
        raise ValueError(f"unknown primary_channel_names: {', '.join(invalid)}")
    first_message = _safe_text(
        source.get("first_message") if "first_message" in source else source.get("firstMessage"),
        20_000,
    )
    return {
        "create_primary_sessions": _coerce_bool(source.get("create_primary_sessions") if "create_primary_sessions" in source else source.get("createPrimarySessions"), True),
        "primary_channel_names": primary_channel_names,
        "generate_registry": _coerce_bool(source.get("generate_registry") if "generate_registry" in source else source.get("generateRegistry"), True),
        "run_dedup": _coerce_bool(source.get("run_dedup") if "run_dedup" in source else source.get("runDedup"), True),
        "run_visibility_check": _coerce_bool(source.get("run_visibility_check") if "run_visibility_check" in source else source.get("runVisibilityCheck"), True),
        "send_bootstrap_message": _coerce_bool(source.get("send_bootstrap_message") if "send_bootstrap_message" in source else source.get("sendBootstrapMessage"), False),
        "send_init_training": _coerce_bool(source.get("send_init_training") if "send_init_training" in source else source.get("sendInitTraining"), False),
        "dry_run": _coerce_bool(source.get("dry_run") if "dry_run" in source else source.get("dryRun"), False),
        "first_message": first_message,
    }


def _normalize_existing_channels(project_cfg: dict[str, Any]) -> dict[str, dict[str, str]]:
    rows = project_cfg.get("channels") if isinstance(project_cfg.get("channels"), list) else []
    out: dict[str, dict[str, str]] = {}
    for item in rows:
        if not isinstance(item, dict):
            continue
        name = _safe_text(item.get("name"), 240)
        if not name:
            continue
        out[name] = {
            "desc": _safe_text(item.get("desc"), 500) or name,
            "cli_type": _safe_text(item.get("cli_type") if "cli_type" in item else item.get("cliType"), 40).lower() or "codex",
            "model": _safe_text(item.get("model"), 200),
            "reasoning_effort": _normalize_reasoning_effort(
                item.get("reasoning_effort") if "reasoning_effort" in item else item.get("reasoningEffort")
            ),
        }
    return out


def _project_conflict_reason(existing: dict[str, Any], spec: dict[str, Any]) -> str:
    if _safe_text(existing.get("name"), 200) != spec["project_name"]:
        return "project_name mismatch"
    if _normalize_rel_path_text(existing.get("project_root_rel")) != spec["project_root_rel"]:
        return "project_root_rel mismatch"
    if _normalize_rel_path_text(existing.get("task_root_rel")) != spec["task_root_rel"]:
        return "task_root_rel mismatch"
    if _safe_text(existing.get("color"), 32) != spec["color"]:
        return "color mismatch"
    if _safe_text(existing.get("description"), 4000) != spec["description"]:
        return "description mismatch"
    existing_channels = _normalize_existing_channels(existing)
    for channel in spec["channels"]:
        row = existing_channels.get(channel["name"])
        if not row:
            return f"missing channel: {channel['name']}"
        if row["desc"] != channel["desc"]:
            return f"channel desc mismatch: {channel['name']}"
        if row["cli_type"] != channel["cli_type"]:
            return f"channel cli_type mismatch: {channel['name']}"
        if row["model"] != channel["model"]:
            return f"channel model mismatch: {channel['name']}"
        if row["reasoning_effort"] != channel["reasoning_effort"]:
            return f"channel reasoning_effort mismatch: {channel['name']}"
    existing_ctx = existing.get("execution_context") if isinstance(existing.get("execution_context"), dict) else {}
    for key, value in spec["execution_context"].items():
        if _safe_text(existing_ctx.get(key), 4000) != _safe_text(value, 4000):
            return f"execution_context.{key} mismatch"
    return ""


def _build_project_block(spec: dict[str, Any]) -> str:
    lines = [
        "[[projects]]",
        f'id = {_toml_scalar_literal(spec["project_id"])}',
        f'name = {_toml_scalar_literal(spec["project_name"])}',
        f'color = {_toml_scalar_literal(spec["color"])}',
        f'project_root_rel = {_toml_scalar_literal(spec["project_root_rel"])}',
        f'task_root_rel = {_toml_scalar_literal(spec["task_root_rel"])}',
    ]
    if spec["description"]:
        lines.append(f'description = {_toml_scalar_literal(spec["description"])}')
    lines.append("")
    for link in spec["links"]:
        lines.extend(
            [
                "[[projects.links]]",
                f'label = {_toml_scalar_literal(link["label"])}',
                f'url = {_toml_scalar_literal(link["url"])}',
                "",
            ]
        )
    for channel in spec["channels"]:
        lines.extend(
            [
                "[[projects.channels]]",
                f'name = {_toml_scalar_literal(channel["name"])}',
                f'desc = {_toml_scalar_literal(channel["desc"])}',
                f'cli_type = {_toml_scalar_literal(channel["cli_type"])}',
            ]
        )
        if channel["model"]:
            lines.append(f'model = {_toml_scalar_literal(channel["model"])}')
        if channel["reasoning_effort"]:
            lines.append(f'reasoning_effort = {_toml_scalar_literal(channel["reasoning_effort"])}')
        lines.append("")
    lines.append("[projects.execution_context]")
    for key, value in spec["execution_context"].items():
        if not str(value or "").strip():
            continue
        lines.append(f"{key} = {_toml_scalar_literal(value)}")
    return "\n".join(lines).rstrip() + "\n"


def _append_project_block(config_path: Path, block: str) -> None:
    raw = config_path.read_text(encoding="utf-8")
    updated = raw.rstrip() + "\n\n" + block
    atomic_write_text(config_path, updated)


def validate_project_bootstrap_request(
    *,
    body: dict[str, Any],
    config_path: Path,
    repo_root: Path,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    if not config_path.exists():
        raise FileNotFoundError("config.toml not found")
    cfg = _load_toml(config_path)
    projects = cfg.get("projects") if isinstance(cfg.get("projects"), list) else []

    project_id = _safe_text(body.get("project_id") if "project_id" in body else body.get("projectId"), 80).lower()
    project_name = _safe_text(body.get("project_name") if "project_name" in body else body.get("projectName"), 200)
    project_root_rel = _normalize_rel_path_text(body.get("project_root_rel") if "project_root_rel" in body else body.get("projectRootRel"))
    task_root_rel = _normalize_rel_path_text(body.get("task_root_rel") if "task_root_rel" in body else body.get("taskRootRel"))
    description = _safe_text(body.get("description"), 4000)
    color = _safe_text(body.get("color"), 32) or "#0F63F2"

    if not project_id:
        raise ValueError("missing project_id")
    if not _VALID_PROJECT_ID_RE.match(project_id):
        raise ValueError("invalid project_id")
    if not project_name:
        raise ValueError("missing project_name")
    if not project_root_rel:
        raise ValueError("missing project_root_rel")
    if not task_root_rel:
        raise ValueError("missing task_root_rel")
    if not _VALID_COLOR_RE.match(color):
        raise ValueError("invalid color")

    channels = _normalize_channels(body.get("channels"))
    if not channels:
        raise ValueError("missing channels")
    channel_names = [row["name"] for row in channels]

    project_root = _resolve_project_path(project_root_rel, repo_root)
    task_root = _resolve_project_path(task_root_rel, repo_root)
    execution_context = _normalize_execution_context(
        body.get("execution_context") if "execution_context" in body else body.get("executionContext"),
        project_root=project_root,
        repo_root=repo_root,
    )
    bootstrap = _normalize_bootstrap_options(body.get("bootstrap"), channel_names)
    links = _merge_links(
        _default_links(
            project_id=project_id,
            project_root_rel=project_root_rel,
            task_root_rel=task_root_rel,
        ),
        _normalize_links(body.get("links")),
    )

    sessions_root = Path(execution_context["sessions_root"]).resolve()
    session_store_path = _session_store_path_for(project_id, sessions_root)
    registry_json = (project_root / "registry" / "collab-registry.v1.json").resolve()
    registry_view = (project_root / "registry" / "collab-registry.view.md").resolve()
    registry_html = (project_root / "artifacts" / "agent-directory" / f"{project_id}-agent-directory.html").resolve()

    spec = {
        "project_id": project_id,
        "project_name": project_name,
        "project_root_rel": project_root_rel,
        "task_root_rel": task_root_rel,
        "project_root": project_root,
        "task_root": task_root,
        "description": description,
        "color": color,
        "channels": channels,
        "links": links,
        "execution_context": execution_context,
        "session_store_path": session_store_path,
        "registry_paths": [str(registry_json), str(registry_view), str(registry_html)],
        "bootstrap": bootstrap,
    }

    existing_project: dict[str, Any] = {}
    for item in projects:
        if not isinstance(item, dict):
            continue
        existing_id = _safe_text(item.get("id"), 80)
        if existing_id == project_id:
            existing_project = item
            continue
        existing_root = _resolve_project_path(_normalize_rel_path_text(item.get("project_root_rel")), repo_root)
        if str(existing_root) == str(project_root):
            raise FileExistsError(f"project_root already used by project '{existing_id}'")
        existing_task_root = _resolve_project_path(_normalize_rel_path_text(item.get("task_root_rel")), repo_root)
        if str(existing_task_root) == str(task_root):
            raise FileExistsError(f"task_root already used by project '{existing_id}'")
        existing_ctx = item.get("execution_context") if isinstance(item.get("execution_context"), dict) else {}
        existing_port = _safe_text(existing_ctx.get("server_port"), 80)
        requested_port = _safe_text(execution_context.get("server_port"), 80)
        if existing_port and requested_port and existing_port == requested_port:
            raise FileExistsError(f"server_port already used by project '{existing_id}'")

    warnings: list[dict[str, Any]] = []
    if bootstrap["send_bootstrap_message"]:
        warnings.append({"code": "bootstrap_message_not_implemented", "message": "V1 暂未自动发送 bootstrap message，已跳过。"})
    if bootstrap["send_init_training"]:
        warnings.append({"code": "init_training_not_implemented", "message": "V1 暂未自动发送初始化培训消息，已跳过。"})
    return spec, existing_project, warnings


def write_project_config_block(
    *,
    config_path: Path,
    spec: dict[str, Any],
    existing_project: dict[str, Any],
) -> dict[str, Any]:
    if existing_project:
        reason = _project_conflict_reason(existing_project, spec)
        if reason:
            raise ValueError(reason)
        return {"ok": True, "reused": True, "config_path": str(config_path)}
    _append_project_block(config_path, _build_project_block(spec))
    return {"ok": True, "reused": False, "config_path": str(config_path)}


def create_project_scaffold(*, spec: dict[str, Any]) -> dict[str, Any]:
    project_root = Path(spec["project_root"])
    task_root = Path(spec["task_root"])
    project_root.mkdir(parents=True, exist_ok=True)
    task_root.mkdir(parents=True, exist_ok=True)
    (project_root / "registry").mkdir(parents=True, exist_ok=True)
    (project_root / "artifacts" / "agent-directory").mkdir(parents=True, exist_ok=True)

    readme = project_root / "README.md"
    if not readme.exists():
        readme.write_text(
            (
                f"# {spec['project_name']}\n\n"
                f"{spec['description'] or '项目说明待补充。'}\n\n"
                "## 目录\n\n"
                f"- 任务规划：`{spec['task_root_rel']}`\n"
                "- registry：协作通讯录与视图\n"
                "- artifacts：生成类静态产物\n"
            ),
            encoding="utf-8",
        )

    task_root_readme = task_root / "README.md"
    if not task_root_readme.exists():
        task_root_readme.write_text(
            f"# {spec['project_name']} / 任务规划\n\n本目录由 `POST /api/projects/bootstrap` 初始化。\n",
            encoding="utf-8",
        )

    created_channel_roots: list[str] = []
    for channel in spec["channels"]:
        channel_root = task_root / channel["name"]
        channel_root.mkdir(parents=True, exist_ok=True)
        created_channel_roots.append(str(channel_root))
        for subdir in _DEFAULT_CHANNEL_BOOTSTRAP_SUBDIRS:
            (channel_root / subdir).mkdir(parents=True, exist_ok=True)
        for rel_path, content in _DEFAULT_CHANNEL_BOOTSTRAP_MARKER_FILES.items():
            marker_file = channel_root / rel_path
            if not marker_file.exists():
                marker_file.write_text(content, encoding="utf-8")
        channel_readme = channel_root / "README.md"
        if not channel_readme.exists():
            channel_readme.write_text(
                (
                    f"# {channel['name']}\n\n"
                    f"{channel['desc']}\n\n"
                    "## 说明\n\n"
                    f"- CLI 类型：`{channel['cli_type']}`\n"
                    "- 本目录由项目 bootstrap 自动初始化。\n"
                ),
                encoding="utf-8",
            )

    return {
        "ok": True,
        "project_root": str(project_root),
        "task_root": str(task_root),
        "channel_root_count": len(created_channel_roots),
        "channel_roots": created_channel_roots,
    }


def init_project_session_store(*, spec: dict[str, Any]) -> dict[str, Any]:
    session_store_path = Path(spec["session_store_path"])
    if session_store_path.exists():
        try:
            raw = json.loads(session_store_path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("invalid session store shape")
        except Exception as exc:
            raise ValueError(f"invalid session store: {exc}") from exc
        return {"ok": True, "reused": True, "session_store_path": str(session_store_path)}

    session_store_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        session_store_path,
        json.dumps(
            {"project_id": spec["project_id"], "sessions": []},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
    )
    return {"ok": True, "reused": False, "session_store_path": str(session_store_path)}


def bootstrap_project_primary_sessions(
    *,
    spec: dict[str, Any],
    session_store: Any,
    create_cli_session: Callable[..., dict[str, Any]],
    detect_git_branch: Callable[[str], str],
    build_session_seed_prompt: Callable[..., str],
    decorate_session_display_fields: Callable[[dict[str, Any]], dict[str, Any]],
    apply_session_work_context: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    bootstrap = spec["bootstrap"]
    if not bootstrap["create_primary_sessions"]:
        return {"ok": True, "skipped": True, "created_sessions": []}

    channels = spec["channels"]
    target_names = bootstrap["primary_channel_names"] or [row["name"] for row in channels]
    target_name_set = set(target_names)
    created_sessions: list[dict[str, Any]] = []

    execution_context = spec["execution_context"]
    project_root = Path(spec["project_root"])
    requested_environment = execution_context["environment"] or "stable"
    custom_loader = lambda *args, **kwargs: dict(spec["execution_context"])
    resolve_project_workdir = lambda _pid: project_root
    project_exists = lambda pid: str(pid or "").strip() == spec["project_id"]
    channel_exists = lambda pid, cname: project_exists(pid) and str(cname or "").strip() in target_name_set

    for channel in channels:
        if channel["name"] not in target_name_set:
            continue
        payload = {
            "project_id": spec["project_id"],
            "channel_name": channel["name"],
            "cli_type": channel["cli_type"],
            "model": channel["model"],
            "reasoning_effort": channel["reasoning_effort"],
            "environment": requested_environment,
            "worktree_root": execution_context["worktree_root"] or str(project_root),
            "workdir": execution_context["workdir"] or str(project_root),
            "branch": execution_context["branch"],
            "session_role": "primary",
            "reuse_strategy": "reuse_active",
            "set_as_primary": True,
            "first_message": bootstrap["first_message"],
        }
        result = create_session_response(
            payload=payload,
            session_store=session_store,
            environment_name=requested_environment,
            worktree_root=execution_context["worktree_root"] or str(project_root),
            create_cli_session=create_cli_session,
            resolve_project_workdir=resolve_project_workdir,
            detect_git_branch=detect_git_branch,
            build_session_seed_prompt=build_session_seed_prompt,
            decorate_session_display_fields=decorate_session_display_fields,
            apply_session_work_context=apply_session_work_context,
            load_project_execution_context=custom_loader,
            project_exists=project_exists,
            channel_exists=channel_exists,
        )
        session = result.get("session") if isinstance(result.get("session"), dict) else {}
        created_sessions.append(
            {
                "channel_name": channel["name"],
                "session_id": _safe_text(session.get("id") or session.get("sessionId"), 120),
                "created": bool(result.get("created")),
                "reused": bool(result.get("reused")),
                "timeout_recovered": bool(result.get("timeout_recovered")),
                "create_warning": result.get("create_warning") if isinstance(result.get("create_warning"), dict) else {},
                "session_path": _safe_text(result.get("sessionPath"), 4000),
                "workdir": _safe_text(result.get("workdir"), 4000),
            }
        )
    return {"ok": True, "skipped": False, "created_sessions": created_sessions}


def build_project_registry_and_verify(
    *,
    spec: dict[str, Any],
    repo_root: Path,
    config_path: Path,
    session_store: Any,
    read_task_dashboard_generated_at: Callable[[], str],
    rebuild_dashboard_static: Callable[[int], dict[str, Any]],
) -> dict[str, Any]:
    bootstrap = spec["bootstrap"]
    project_id = spec["project_id"]
    project_root = Path(spec["project_root"])
    registry_paths = spec["registry_paths"]
    created_sessions = session_store.list_sessions(project_id, include_deleted=False)
    dashboard_repo_root = config_path.resolve().parent

    registry_payload: dict[str, Any] = {
        "ok": True,
        "skipped": not bootstrap["generate_registry"],
        "paths": registry_paths,
    }
    if bootstrap["generate_registry"]:
        script_path = dashboard_repo_root / "scripts" / "bootstrap_project_collab.py"
        if not script_path.exists():
            raise FileNotFoundError("scripts/bootstrap_project_collab.py not found")
        proc = subprocess.run(
            [
                sys.executable,
                str(script_path),
                "--project-id",
                project_id,
                "--config",
                str(config_path.resolve()),
                "--workspace-root",
                str(repo_root.resolve()),
                "--session-json",
                str(Path(spec["session_store_path"]).resolve()),
                "--output",
                registry_paths[0],
                "--view-output",
                registry_paths[1],
                "--html-output",
                registry_paths[2],
            ],
            cwd=str(dashboard_repo_root),
            capture_output=True,
            text=True,
            timeout=180,
        )
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "bootstrap_project_collab failed")
        registry_payload.update(
            {
                "stdout": _safe_text(proc.stdout, 12_000),
                "stderr": _safe_text(proc.stderr, 4000),
            }
        )

    dedup_results: list[dict[str, Any]] = []
    if bootstrap["run_dedup"]:
        target_names = bootstrap["primary_channel_names"] or [row["name"] for row in spec["channels"]]
        for channel_name in target_names:
            code, payload = dedup_session_channel_response(
                body={"project_id": project_id, "channel_name": channel_name, "strategy": "latest"},
                session_store=session_store,
                safe_text=_safe_text,
                now_iso=lambda: "",
                coerce_bool=_coerce_bool,
            )
            if code != 200:
                raise RuntimeError(f"dedup failed for channel '{channel_name}'")
            dedup_results.append(
                {
                    "channel_name": channel_name,
                    "result": payload.get("result") if isinstance(payload, dict) else {},
                }
            )

    visibility_payload: dict[str, Any] = {"ok": True, "skipped": True}
    if bootstrap["run_visibility_check"]:
        target_names = bootstrap["primary_channel_names"] or [row["name"] for row in spec["channels"]]
        target_session: dict[str, Any] | None = None
        for channel_name in target_names:
            rows = session_store.list_sessions(project_id, channel_name, include_deleted=False)
            if rows:
                target_session = rows[0]
                break
        if target_session:
            before = _safe_text(read_task_dashboard_generated_at(), 120)
            rebuild = rebuild_dashboard_static(timeout_s=150)
            after = _safe_text(read_task_dashboard_generated_at(), 120)
            visibility_payload = {
                "ok": True,
                "skipped": False,
                "project_id": project_id,
                "channel_name": _safe_text(target_session.get("channel_name"), 240),
                "session_id": _safe_text(target_session.get("id"), 120),
                "generated_at_before": before,
                "generated_at_after": after,
                "generated_at_fresh": bool(after and after != before),
                "rebuild": rebuild,
            }
        else:
            visibility_payload = {
                "ok": True,
                "skipped": True,
                "reason": "no_primary_session",
            }

    return {
        "ok": True,
        "project_root": str(project_root),
        "registry": registry_payload,
        "dedup_results": dedup_results,
        "visibility_check": visibility_payload,
        "session_count": len(created_sessions),
    }


def bootstrap_project_response(
    *,
    body: dict[str, Any],
    config_path: Path,
    repo_root: Path,
    session_store: Any,
    create_cli_session: Callable[..., dict[str, Any]],
    detect_git_branch: Callable[[str], str],
    build_session_seed_prompt: Callable[..., str],
    decorate_session_display_fields: Callable[[dict[str, Any]], dict[str, Any]],
    apply_session_work_context: Callable[..., dict[str, Any]],
    read_task_dashboard_generated_at: Callable[[], str],
    rebuild_dashboard_static: Callable[[int], dict[str, Any]],
    clear_dashboard_cfg_cache: Callable[[], None],
) -> tuple[int, dict[str, Any]]:
    step_results: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    spec: dict[str, Any] = {}

    def _base_payload() -> dict[str, Any]:
        return {
            "ok": False,
            "project_id": _safe_text(spec.get("project_id"), 80),
            "reused": False,
            "resume_from_step": "",
            "config_path": str(config_path),
            "project_root": str(spec.get("project_root") or ""),
            "task_root": str(spec.get("task_root") or ""),
            "session_store_path": str(spec.get("session_store_path") or ""),
            "registry_paths": list(spec.get("registry_paths") or []),
            "created_sessions": [],
            "warnings": warnings,
            "step_results": step_results,
        }

    def _error(status: int, step: str, error: str) -> tuple[int, dict[str, Any]]:
        if step:
            step_results.append({"step": step, "ok": False, "error": error})
        payload = _base_payload()
        payload.update({"error": error, "resume_from_step": step})
        return status, payload

    try:
        spec, existing_project, collected_warnings = validate_project_bootstrap_request(
            body=body,
            config_path=config_path,
            repo_root=repo_root,
        )
        warnings.extend(collected_warnings)
        _align_execution_context_to_session_store(spec=spec, session_store=session_store)
        step_results.append(
            {
                "step": "validate",
                "ok": True,
                "project_id": spec["project_id"],
                "dry_run": bool(spec["bootstrap"]["dry_run"]),
            }
        )
    except FileNotFoundError as exc:
        return _error(404, "validate", str(exc))
    except FileExistsError as exc:
        return _error(409, "validate", str(exc))
    except ValueError as exc:
        return _error(400, "validate", str(exc))
    except Exception as exc:  # pragma: no cover
        return _error(500, "validate", str(exc))

    if spec["bootstrap"]["dry_run"]:
        payload = _base_payload()
        payload.update(
            {
                "ok": True,
                "reused": bool(existing_project),
                "dry_run": True,
            }
        )
        return 200, payload

    try:
        write_result = write_project_config_block(
            config_path=config_path,
            spec=spec,
            existing_project=existing_project,
        )
        clear_dashboard_cfg_cache()
        step_results.append(
            {
                "step": "write_config",
                "ok": True,
                "reused": bool(write_result.get("reused")),
                "config_path": str(write_result.get("config_path") or config_path),
            }
        )
    except ValueError as exc:
        return _error(409, "write_config", str(exc))
    except Exception as exc:
        return _error(500, "write_config", str(exc))

    try:
        scaffold_result = create_project_scaffold(spec=spec)
        step_results.append(
            {
                "step": "create_scaffold",
                "ok": True,
                "project_root": scaffold_result["project_root"],
                "task_root": scaffold_result["task_root"],
            }
        )
    except Exception as exc:
        return _error(500, "create_scaffold", str(exc))

    try:
        session_store_result = init_project_session_store(spec=spec)
        step_results.append(
            {
                "step": "init_session_store",
                "ok": True,
                "reused": bool(session_store_result.get("reused")),
                "session_store_path": session_store_result["session_store_path"],
            }
        )
    except Exception as exc:
        return _error(500, "init_session_store", str(exc))

    created_sessions: list[dict[str, Any]] = []
    try:
        primary_result = bootstrap_project_primary_sessions(
            spec=spec,
            session_store=session_store,
            create_cli_session=create_cli_session,
            detect_git_branch=detect_git_branch,
            build_session_seed_prompt=build_session_seed_prompt,
            decorate_session_display_fields=decorate_session_display_fields,
            apply_session_work_context=apply_session_work_context,
        )
        created_sessions = list(primary_result.get("created_sessions") or [])
        step_results.append(
            {
                "step": "create_primary_sessions",
                "ok": True,
                "skipped": bool(primary_result.get("skipped")),
                "count": len(created_sessions),
            }
        )
    except LookupError as exc:
        return _error(404, "create_primary_sessions", str(exc))
    except ValueError as exc:
        return _error(400, "create_primary_sessions", str(exc))
    except RuntimeError as exc:
        detail = getattr(exc, "detail", None)
        message = str(detail or exc)
        return _error(500, "create_primary_sessions", message)
    except Exception as exc:
        return _error(500, "create_primary_sessions", str(exc))

    try:
        verify_result = build_project_registry_and_verify(
            spec=spec,
            repo_root=repo_root,
            config_path=config_path,
            session_store=session_store,
            read_task_dashboard_generated_at=read_task_dashboard_generated_at,
            rebuild_dashboard_static=rebuild_dashboard_static,
        )
        step_results.append(
            {
                "step": "generate_registry",
                "ok": True,
                "skipped": bool((verify_result.get("registry") or {}).get("skipped")),
                "paths": spec["registry_paths"],
            }
        )
        step_results.append(
            {
                "step": "run_visibility_check",
                "ok": True,
                "skipped": bool((verify_result.get("visibility_check") or {}).get("skipped")),
            }
        )
    except FileNotFoundError as exc:
        return _error(500, "generate_registry", str(exc))
    except RuntimeError as exc:
        return _error(500, "generate_registry", str(exc))
    except Exception as exc:
        return _error(500, "run_visibility_check", str(exc))

    payload = _base_payload()
    payload.update(
        {
            "ok": True,
            "reused": bool(existing_project),
            "created_sessions": created_sessions,
            "registry": verify_result.get("registry"),
            "dedup_results": verify_result.get("dedup_results"),
            "visibility_check": verify_result.get("visibility_check"),
        }
    )
    return 200, payload


__all__ = [
    "bootstrap_project_response",
    "build_project_registry_and_verify",
    "bootstrap_project_primary_sessions",
    "create_project_scaffold",
    "init_project_session_store",
    "validate_project_bootstrap_request",
    "write_project_config_block",
]
