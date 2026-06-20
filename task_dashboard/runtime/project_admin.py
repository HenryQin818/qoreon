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
from task_dashboard.runtime.channel_admin import (
    render_agents_md_template,
    validate_agents_md_content,
    write_channel_agents_md,
)
from task_dashboard.runtime.session_admin import create_session_response
from task_dashboard.runtime.session_routes import dedup_session_channel_response


_VALID_PROJECT_ID_RE = re.compile(r"^[a-z][a-z0-9_]{1,79}$")
_VALID_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
_KNOWN_CLI_TYPES = {"codex", "claude", "opencode", "gemini", "trae", "codebuddy"}
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
_ONBOARDING_TEST_PROJECT_PREFIXES = ("test_", "qa_", "sandbox_", "tmp_", "bootstrap_test_")


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


def _path_within(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except Exception:
        return False


def _validate_channel_name_path_segment(name: str) -> None:
    text = str(name or "").strip()
    if not text or text in {".", ".."} or "/" in text or "\\" in text or "\x00" in text:
        raise ValueError(f"invalid channel name path segment: {text or '<empty>'}")


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
        _validate_channel_name_path_segment(name)
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
                "primary_alias": _safe_text(
                    item.get("primary_alias")
                    if "primary_alias" in item
                    else (
                        item.get("primaryAlias")
                        if "primaryAlias" in item
                        else (item.get("agentAlias") if "agentAlias" in item else item.get("alias"))
                    ),
                    200,
                ),
                "primary_purpose": _safe_text(
                    item.get("primary_purpose")
                    if "primary_purpose" in item
                    else (
                        item.get("primaryPurpose")
                        if "primaryPurpose" in item
                        else (item.get("agentPurpose") if "agentPurpose" in item else item.get("purpose"))
                    ),
                    200,
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


def _normalize_message_ref_option(raw: Any) -> dict[str, str]:
    source = raw if isinstance(raw, dict) else {}
    out = {
        "project_id": _safe_text(source.get("project_id") if "project_id" in source else source.get("projectId"), 80),
        "channel_name": _safe_text(source.get("channel_name") if "channel_name" in source else source.get("channelName"), 240),
        "session_id": _safe_text(source.get("session_id") if "session_id" in source else source.get("sessionId"), 120),
        "run_id": _safe_text(source.get("run_id") if "run_id" in source else source.get("runId"), 120),
    }
    return {key: value for key, value in out.items() if value}


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
        "onboarding_isolated_test_project": _coerce_bool(
            source.get("onboarding_isolated_test_project")
            if "onboarding_isolated_test_project" in source
            else source.get("onboardingIsolatedTestProject"),
            False,
        ),
        "onboarding_source_ref": _normalize_message_ref_option(
            source.get("onboarding_source_ref") if "onboarding_source_ref" in source else source.get("onboardingSourceRef")
        ),
        "onboarding_callback_to": _normalize_message_ref_option(
            source.get("onboarding_callback_to") if "onboarding_callback_to" in source else source.get("onboardingCallbackTo")
        ),
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


def _render_project_agents_md_template(spec: dict[str, Any]) -> str:
    channels = list(spec.get("channels") or [])
    channel_lines = "\n".join(
        f"- `{row.get('name')}`：{row.get('desc') or row.get('name')}（cli_type={row.get('cli_type') or 'codex'}）"
        for row in channels
        if isinstance(row, dict)
    )
    if not channel_lines:
        channel_lines = "- 暂无通道；以 `config.toml` 和项目启动蓝图为准。"
    project_id = str(spec.get("project_id") or "").strip()
    project_name = str(spec.get("project_name") or "").strip() or project_id
    description = str(spec.get("description") or "").strip() or "项目说明待补充。"
    task_root_rel = str(spec.get("task_root_rel") or "").strip()
    return f"""# {project_name} Agent 快速卡

## 项目定位

{description}

## 真源入口

- 项目说明：`README.md`
- 任务真源：`{task_root_rel}/<通道>/任务/`
- 问题留痕：`{task_root_rel}/<通道>/问题/`
- 产出物：`{task_root_rel}/<通道>/产出物/`
- 协作通讯录：`registry/public-registry.v1.json`

## 首批通道

{channel_lines}

## 消息与回执

- 正式协作消息使用 `task_dashboard.message_cli`，必须显式带 `--project {project_id}`。
- 优先从 task-dashboard 根目录执行；不在根目录时设置 `PYTHONPATH=<task-dashboard根目录>`。
- 标准顺序：`resolve -> doctor -> send/receipt --wait-verify --json`。
- 已送达只认三件套：`announce_run_id + target_session_id一致 + visible_in_channel_chat=true`。
- `--wait-verify` 只代表送达证据，不代表业务完成；业务完成仍需结果回执。

## AGENTS 分层

- 根级 `AGENTS.md` 负责项目硬规则：真源入口、消息证据链、任务规则、服务门禁和安全禁区。
- 通道级 `任务规划/<通道>/AGENTS.md` 负责本通道职责、固定阅读入口、常用路径、推荐 skills 和停止线。
- `AGENTS.md` 是长期规则快速卡，不是业务真源、授权证据或当前状态证据。
- 写入 `AGENTS.md` 不等于旧会话已加载；只有后续新会话或真实 resume 进入对应 workdir 后才会读取。

## 任务与产出物

- 项目采用“目录即分工、文件名即状态”；任务状态以任务文件、正式回执和验收证据为准。
- 任务需要写清主负责位、执行位、验收位、审核或门禁位；不得只写通道不写具体 Agent。
- 草稿、待授权、已提交发送、只读方案包、AGENTS 草稿包都不等于任务完成。
- 材料放 `产出物/材料/`，可复用结论放 `产出物/沉淀/`。

## 安全边界

- 不在 `AGENTS.md` 写入 token、PID、端口、临时会话、一次性授权、瞬时 health 或历史消息结论。
- 不通过 `AGENTS.md` 授予服务启动、重启、注册、发布、service monitor 写入、会话创建、会话轮换或真实初始化消息权限。
- 涉及真实写入、真实消息、会话动作或服务动作时，必须另行确认 action_scope、回滚方式和验收口径。
"""


def _write_project_agents_md(*, spec: dict[str, Any]) -> dict[str, Any]:
    project_root = Path(spec["project_root"]).resolve()
    agents_path = (project_root / "AGENTS.md").resolve()
    if not _path_within(agents_path, project_root):
        raise PermissionError("project AGENTS.md path escapes project root")
    if agents_path.exists():
        return {
            "created": False,
            "path": str(agents_path),
            "source": "existing",
        }
    content = _render_project_agents_md_template(spec)
    dry_run = validate_agents_md_content(content)
    if not dry_run.get("ok"):
        messages = [
            str(item.get("message") or item.get("code") or "")
            for item in dry_run.get("blockingIssues") or []
            if isinstance(item, dict)
        ]
        raise ValueError("project AGENTS.md dry-run blocked: " + "; ".join([m for m in messages if m]))
    agents_path.write_text(content if content.endswith("\n") else content + "\n", encoding="utf-8")
    return {
        "created": True,
        "path": str(agents_path),
        "source": "template",
        "dryRun": dry_run,
        "contentLength": len(content),
    }


def _bootstrap_agents_channel_names(spec: dict[str, Any]) -> list[str]:
    channels = [row for row in spec.get("channels") or [] if isinstance(row, dict)]
    bootstrap = spec.get("bootstrap") if isinstance(spec.get("bootstrap"), dict) else {}
    primary_names = [str(item or "").strip() for item in bootstrap.get("primary_channel_names") or [] if str(item or "").strip()]
    if primary_names:
        return primary_names
    if bootstrap.get("create_primary_sessions", True):
        return [str(row.get("name") or "").strip() for row in channels if str(row.get("name") or "").strip()]
    if channels:
        first = str(channels[0].get("name") or "").strip()
        return [first] if first else []
    return []


def _write_bootstrap_channel_agents_md(
    *,
    spec: dict[str, Any],
    config_path: Path,
    repo_root: Path,
) -> list[dict[str, Any]]:
    by_name = {str(row.get("name") or "").strip(): row for row in spec.get("channels") or [] if isinstance(row, dict)}
    results: list[dict[str, Any]] = []
    task_root = Path(spec["task_root"]).resolve()
    for channel_name in _bootstrap_agents_channel_names(spec):
        channel = by_name.get(channel_name) or {}
        channel_root = (task_root / channel_name).resolve()
        if not _path_within(channel_root, task_root):
            raise PermissionError("channel path escapes task root")
        agents_path = (channel_root / "AGENTS.md").resolve()
        if not _path_within(agents_path, channel_root):
            raise PermissionError("channel AGENTS.md path escapes channel root")
        if agents_path.exists():
            results.append(
                {
                    "channel_name": channel_name,
                    "created": False,
                    "path": str(agents_path),
                    "source": "existing",
                    "cli_type": str(channel.get("cli_type") or "codex"),
                }
            )
            continue
        content = render_agents_md_template(
            role="",
            channel_type="",
            channel_name=channel_name,
            channel_desc=str(channel.get("desc") or channel_name),
        )
        result = write_channel_agents_md(
            project_id=str(spec["project_id"]),
            channel_name=channel_name,
            content=content,
            config_path=config_path,
            repo_root=repo_root,
            enabled_cli_types=[str(channel.get("cli_type") or "codex")],
        )
        results.append(
            {
                "channel_name": channel_name,
                "created": True,
                "path": str(result.get("agentsMdPath") or agents_path),
                "source": "template",
                "cli_type": str(channel.get("cli_type") or "codex"),
                "static_instruction_files": result.get("static_instruction_files"),
                "dryRun": result.get("dryRun"),
            }
        )
    return results


def _append_project_block(config_path: Path, block: str) -> None:
    raw = config_path.read_text(encoding="utf-8")
    updated = raw.rstrip() + "\n\n" + block
    atomic_write_text(config_path, updated)


def _primary_session_alias(*, spec: dict[str, Any], channel: dict[str, str]) -> str:
    explicit = _safe_text(channel.get("primary_alias"), 200)
    if explicit:
        return explicit
    project_name = _safe_text(spec.get("project_name"), 120)
    channel_name = _safe_text(channel.get("name"), 120)
    channel_desc = _safe_text(channel.get("desc"), 120)
    if project_name and channel_name:
        return _safe_text(f"{project_name}-{channel_name}", 200)
    return channel_desc or channel_name or "项目主会话"


def _primary_session_purpose(*, spec: dict[str, Any], channel: dict[str, str]) -> str:
    explicit = _safe_text(channel.get("primary_purpose"), 200)
    if explicit:
        return explicit
    project_name = _safe_text(spec.get("project_name"), 120) or _safe_text(spec.get("project_id"), 80)
    channel_name = _safe_text(channel.get("name"), 120)
    if project_name and channel_name:
        return _safe_text(f"{project_name} / {channel_name} primary 协作会话", 200)
    return "项目 primary 协作会话"


def _gate_check(code: str, ok: bool, message: str, **extra: Any) -> dict[str, Any]:
    item = {
        "code": code,
        "ok": bool(ok),
        "message": message,
    }
    item.update({k: v for k, v in extra.items() if v not in (None, "")})
    return item


def build_project_bootstrap_completion_gate(
    *,
    spec: dict[str, Any],
    session_store: Any,
    created_sessions: list[dict[str, Any]],
    verify_result: dict[str, Any],
) -> dict[str, Any]:
    """Evaluate whether a newly bootstrapped project is collaboration-ready."""
    project_id = _safe_text(spec.get("project_id"), 80)
    project_root = Path(spec.get("project_root") or "")
    task_root = Path(spec.get("task_root") or "")
    channels = spec.get("channels") if isinstance(spec.get("channels"), list) else []
    bootstrap = spec.get("bootstrap") if isinstance(spec.get("bootstrap"), dict) else {}

    checks: list[dict[str, Any]] = []

    project_agents_path = (project_root / "AGENTS.md").resolve()
    checks.append(
        _gate_check(
            "project_agents_md",
            project_agents_path.exists() and project_agents_path.is_file(),
            "项目根 AGENTS.md 必须存在",
            path=str(project_agents_path),
        )
    )

    first_channel_name = _safe_text((channels[0] or {}).get("name"), 240) if channels else ""
    first_channel_agents_path = (task_root / first_channel_name / "AGENTS.md").resolve() if first_channel_name else Path("")
    checks.append(
        _gate_check(
            "first_channel_agents_md",
            bool(first_channel_name) and first_channel_agents_path.exists() and first_channel_agents_path.is_file(),
            "首通道 AGENTS.md 必须存在",
            channel_name=first_channel_name,
            path=str(first_channel_agents_path) if first_channel_name else "",
        )
    )

    target_names = bootstrap.get("primary_channel_names") if isinstance(bootstrap.get("primary_channel_names"), list) else []
    if not target_names:
        target_names = [row.get("name") for row in channels if isinstance(row, dict)]
    if not bool(bootstrap.get("create_primary_sessions")):
        target_names = []
    target_name_set = {_safe_text(name, 240) for name in target_names if _safe_text(name, 240)}
    stored_sessions = session_store.list_sessions(project_id, include_deleted=False) if project_id else []
    primary_missing: list[str] = []
    identity_missing: list[dict[str, str]] = []
    for channel_name in sorted(target_name_set):
        channel_rows = [
            row for row in stored_sessions
            if _safe_text((row or {}).get("channel_name"), 240) == channel_name
            and bool((row or {}).get("is_primary"))
        ]
        if not channel_rows:
            primary_missing.append(channel_name)
            continue
        primary = channel_rows[0]
        missing_fields = []
        if not _safe_text(primary.get("alias"), 200):
            missing_fields.append("alias")
        if not _safe_text(primary.get("purpose"), 200):
            missing_fields.append("purpose")
        if missing_fields:
            identity_missing.append({"channel_name": channel_name, "missing_fields": ",".join(missing_fields)})
    checks.append(
        _gate_check(
            "primary_identity",
            not primary_missing and not identity_missing,
            "primary session 必须存在且 alias/purpose 非空",
            primary_missing=primary_missing,
            identity_missing=identity_missing,
            created_sessions=created_sessions,
        )
    )

    registry = verify_result.get("registry") if isinstance(verify_result.get("registry"), dict) else {}
    registry_paths = [str(path) for path in spec.get("registry_paths") or [] if str(path or "").strip()]
    registry_missing_paths = [path for path in registry_paths if not Path(path).exists()]
    registry_skipped = bool(registry.get("skipped"))
    registry_degraded = bool(registry.get("degraded")) or _safe_text(registry.get("state"), 80).lower() == "degraded"
    checks.append(
        _gate_check(
            "ccr_generated",
            not registry_skipped and not registry_degraded and not registry_missing_paths,
            "CCR 必须可生成且创建期不能降级",
            skipped=registry_skipped,
            degraded=registry_degraded,
            missing_paths=registry_missing_paths,
        )
    )

    missing_items = [dict(item) for item in checks if not bool(item.get("ok"))]
    passed = not missing_items
    return {
        "ok": passed,
        "state": "ready" if passed else "blocked",
        "collaboration_ready": passed,
        "missing_items": missing_items,
        "checks": checks,
    }


def _looks_like_announce_run_id(value: str) -> bool:
    return bool(re.match(r"^20\d{6}-\d{6}-[0-9A-Za-z_-]{6,}$", value or ""))


def _delivery_evidence_value(row: dict[str, Any], snake: str, camel: str = "") -> Any:
    if snake in row:
        return row.get(snake)
    if camel and camel in row:
        return row.get(camel)
    return ""


def _normalize_onboarding_evidence(raw: Any) -> dict[str, Any]:
    source = raw if isinstance(raw, dict) else {}
    first_visible = (
        source.get("first_visible_message")
        if isinstance(source.get("first_visible_message"), dict)
        or isinstance(source.get("first_visible_message"), list)
        else (
            source.get("first_visible_messages")
            if isinstance(source.get("first_visible_messages"), list)
            else (
            source.get("bootstrap_message")
            if isinstance(source.get("bootstrap_message"), dict)
            else source.get("first_message")
            )
        )
    )
    init_training = (
        source.get("init_training")
        if isinstance(source.get("init_training"), dict)
        or isinstance(source.get("init_training"), list)
        else (
            source.get("init_training_messages")
            if isinstance(source.get("init_training_messages"), list)
            else (
            source.get("startup_training")
            if isinstance(source.get("startup_training"), dict)
            else source.get("training_message")
            )
        )
    )
    return {
        "first_visible_message": first_visible if isinstance(first_visible, (dict, list)) else {},
        "init_training": init_training if isinstance(init_training, (dict, list)) else {},
    }


def _delivery_evidence_items(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, list):
        return [dict(item) for item in raw if isinstance(item, dict)]
    if isinstance(raw, dict) and raw:
        return [dict(raw)]
    return []


def _is_verified_delivery_item(item: dict[str, Any], expected_session_ids: set[str]) -> tuple[bool, str, list[str], dict[str, Any]]:
    run_id = _safe_text(
        _delivery_evidence_value(item, "announce_run_id", "announceRunId"),
        120,
    )
    target_session_id = _safe_text(
        _delivery_evidence_value(item, "target_session_id", "targetSessionId"),
        120,
    )
    visible = _coerce_bool(
        _delivery_evidence_value(item, "visible_in_channel_chat", "visibleInChannelChat"),
        False,
    )
    missing_fields: list[str] = []
    if not _looks_like_announce_run_id(run_id):
        missing_fields.append("announce_run_id")
    if not target_session_id:
        missing_fields.append("target_session_id")
    elif expected_session_ids and target_session_id not in expected_session_ids:
        missing_fields.append("target_session_id_mismatch")
    if not visible:
        missing_fields.append("visible_in_channel_chat")
    evidence = {
        "announce_run_id": run_id,
        "target_session_id": target_session_id,
        "target_session_match": bool(target_session_id and target_session_id in expected_session_ids),
        "visible_in_channel_chat": visible,
    }
    return not missing_fields, target_session_id, missing_fields, evidence


def _delivery_evidence_check(
    *,
    code: str,
    label: str,
    evidence: Any,
    expected_session_ids: set[str],
) -> dict[str, Any]:
    items = _delivery_evidence_items(evidence)
    delivered_session_ids: set[str] = set()
    item_evidence: list[dict[str, Any]] = []
    missing_fields: list[str] = []
    for item in items:
        ok, target_session_id, item_missing, normalized = _is_verified_delivery_item(item, expected_session_ids)
        item_evidence.append(normalized)
        for field in item_missing:
            if field not in missing_fields:
                missing_fields.append(field)
        if ok and target_session_id:
            delivered_session_ids.add(target_session_id)
    if not items:
        missing_fields.extend(["announce_run_id", "target_session_id", "visible_in_channel_chat"])
    missing_session_ids = sorted(expected_session_ids - delivered_session_ids) if expected_session_ids else []
    if missing_session_ids and "target_session_id_missing_for_expected_sessions" not in missing_fields:
        missing_fields.append("target_session_id_missing_for_expected_sessions")
    return _gate_check(
        code,
        not missing_fields and not missing_session_ids,
        f"{label}必须具备送达证据三件套",
        missing_fields=missing_fields,
        missing_session_ids=missing_session_ids,
        delivered_session_ids=sorted(delivered_session_ids),
        evidence=item_evidence[0] if len(item_evidence) == 1 else item_evidence,
    )


def build_project_bootstrap_onboarding_gate(
    *,
    spec: dict[str, Any],
    session_store: Any,
    created_sessions: list[dict[str, Any]],
    completion_gate: dict[str, Any],
    verify_result: dict[str, Any],
) -> dict[str, Any]:
    """Evaluate whether P0-ready project can be shown as collaboration-onboarded."""
    project_id = _safe_text(spec.get("project_id"), 80)
    channels = spec.get("channels") if isinstance(spec.get("channels"), list) else []
    bootstrap = spec.get("bootstrap") if isinstance(spec.get("bootstrap"), dict) else {}
    target_names = bootstrap.get("primary_channel_names") if isinstance(bootstrap.get("primary_channel_names"), list) else []
    if not target_names:
        target_names = [row.get("name") for row in channels if isinstance(row, dict)]
    target_name_set = {_safe_text(name, 240) for name in target_names if _safe_text(name, 240)}

    expected_session_ids: set[str] = set()
    for item in created_sessions:
        if not isinstance(item, dict):
            continue
        channel_name = _safe_text(item.get("channel_name"), 240)
        session_id = _safe_text(item.get("session_id"), 120)
        if session_id and (not target_name_set or channel_name in target_name_set):
            expected_session_ids.add(session_id)
    stored_sessions = session_store.list_sessions(project_id, include_deleted=False) if project_id else []
    for row in stored_sessions:
        if not isinstance(row, dict) or not bool(row.get("is_primary")):
            continue
        channel_name = _safe_text(row.get("channel_name"), 240)
        session_id = _safe_text(row.get("id") or row.get("session_id"), 120)
        if session_id and (not target_name_set or channel_name in target_name_set):
            expected_session_ids.add(session_id)

    p0_ready = bool(completion_gate.get("ok") or completion_gate.get("collaboration_ready"))
    checks: list[dict[str, Any]] = [
        _gate_check(
            "p0_completion_ready",
            p0_ready,
            "P0 completion gate 必须 ready 后才能进入上岗态",
            p0_state=_safe_text(completion_gate.get("state"), 40),
        ),
        _gate_check(
            "primary_onboarding_target",
            bool(expected_session_ids),
            "必须存在可承载首发消息和启动培训的 primary session",
            expected_session_ids=sorted(expected_session_ids),
        ),
    ]

    onboarding_evidence = _normalize_onboarding_evidence(
        verify_result.get("onboarding") if isinstance(verify_result.get("onboarding"), dict) else {}
    )
    first_check = _delivery_evidence_check(
        code="first_visible_message",
        label="首发可见消息",
        evidence=onboarding_evidence["first_visible_message"],
        expected_session_ids=expected_session_ids,
    )
    training_check = _delivery_evidence_check(
        code="init_training",
        label="Agent 启动培训",
        evidence=onboarding_evidence["init_training"],
        expected_session_ids=expected_session_ids,
    )
    checks.extend([first_check, training_check])
    checks.append(
        _gate_check(
            "delivery_evidence",
            bool(first_check.get("ok")) and bool(training_check.get("ok")),
            "首发可见消息与启动培训均必须满足 announce_run_id + target_session_id一致 + visible_in_channel_chat=true",
        )
    )

    missing_items = [dict(item) for item in checks if not bool(item.get("ok"))]
    if not p0_ready or not expected_session_ids:
        state = "blocked"
    elif missing_items:
        state = "pending"
    else:
        state = "ready"
    return {
        "ok": state == "ready",
        "state": state,
        "onboarding_ready": state == "ready",
        "missing_items": missing_items,
        "checks": checks,
        "requirements": [
            "first_visible_message",
            "init_training",
            "announce_run_id + target_session_id一致 + visible_in_channel_chat=true",
        ],
    }


def _is_onboarding_isolated_test_project(project_id: str, bootstrap: dict[str, Any]) -> tuple[bool, str]:
    pid = _safe_text(project_id, 80).lower()
    if not _coerce_bool(bootstrap.get("onboarding_isolated_test_project"), False):
        return False, "missing_onboarding_isolated_test_project"
    if pid.startswith(_ONBOARDING_TEST_PROJECT_PREFIXES) or pid.endswith("_test"):
        return True, ""
    return False, "project_id_not_test_scoped"


def _onboarding_target_sessions(
    *,
    spec: dict[str, Any],
    session_store: Any,
    created_sessions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    project_id = _safe_text(spec.get("project_id"), 80)
    channels = spec.get("channels") if isinstance(spec.get("channels"), list) else []
    bootstrap = spec.get("bootstrap") if isinstance(spec.get("bootstrap"), dict) else {}
    target_names = bootstrap.get("primary_channel_names") if isinstance(bootstrap.get("primary_channel_names"), list) else []
    if not target_names:
        target_names = [row.get("name") for row in channels if isinstance(row, dict)]
    target_name_set = {_safe_text(name, 240) for name in target_names if _safe_text(name, 240)}
    channel_by_name = {
        _safe_text(row.get("name"), 240): row
        for row in channels
        if isinstance(row, dict) and _safe_text(row.get("name"), 240)
    }
    by_channel: dict[str, dict[str, Any]] = {}
    for item in created_sessions:
        if not isinstance(item, dict):
            continue
        channel_name = _safe_text(item.get("channel_name"), 240)
        session_id = _safe_text(item.get("session_id"), 120)
        if not channel_name or not session_id:
            continue
        if target_name_set and channel_name not in target_name_set:
            continue
        channel = channel_by_name.get(channel_name) or {}
        by_channel[channel_name] = {
            "channel_name": channel_name,
            "session_id": session_id,
            "alias": _safe_text(item.get("alias"), 200) or _primary_session_alias(spec=spec, channel=channel),
            "purpose": _safe_text(item.get("purpose"), 200) or _primary_session_purpose(spec=spec, channel=channel),
            "cli_type": _safe_text(channel.get("cli_type"), 40) or "codex",
        }
    try:
        stored_sessions = session_store.list_sessions(project_id, include_deleted=False) if project_id else []
    except Exception:
        stored_sessions = []
    for row in stored_sessions:
        if not isinstance(row, dict) or not bool(row.get("is_primary")):
            continue
        channel_name = _safe_text(row.get("channel_name"), 240)
        session_id = _safe_text(row.get("id") or row.get("session_id"), 120)
        if not channel_name or not session_id:
            continue
        if target_name_set and channel_name not in target_name_set:
            continue
        channel = channel_by_name.get(channel_name) or {}
        by_channel.setdefault(
            channel_name,
            {
                "channel_name": channel_name,
                "session_id": session_id,
                "alias": _safe_text(row.get("alias"), 200) or _primary_session_alias(spec=spec, channel=channel),
                "purpose": _safe_text(row.get("purpose"), 200) or _primary_session_purpose(spec=spec, channel=channel),
                "cli_type": _safe_text(row.get("cli_type") or channel.get("cli_type"), 40) or "codex",
            },
        )
    ordered_names = [name for name in target_names if _safe_text(name, 240) in by_channel]
    return [by_channel[_safe_text(name, 240)] for name in ordered_names]


def _onboarding_refs(
    *,
    spec: dict[str, Any],
    target: dict[str, Any],
) -> tuple[dict[str, str], dict[str, str]]:
    bootstrap = spec.get("bootstrap") if isinstance(spec.get("bootstrap"), dict) else {}
    project_id = _safe_text(spec.get("project_id"), 80)
    channel_name = _safe_text(target.get("channel_name"), 240)
    session_id = _safe_text(target.get("session_id"), 120)
    source_ref = dict(bootstrap.get("onboarding_source_ref") or {})
    source_ref.setdefault("project_id", project_id)
    source_ref.setdefault("channel_name", channel_name)
    source_ref.setdefault("session_id", session_id)
    callback_to = dict(bootstrap.get("onboarding_callback_to") or {})
    callback_to.setdefault("channel_name", source_ref.get("channel_name") or channel_name)
    callback_to.setdefault("session_id", source_ref.get("session_id") or session_id)
    return source_ref, callback_to


def _build_first_visible_onboarding_payload(*, spec: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    project_id = _safe_text(spec.get("project_id"), 80)
    project_name = _safe_text(spec.get("project_name"), 200) or project_id
    channel_name = _safe_text(target.get("channel_name"), 240)
    session_id = _safe_text(target.get("session_id"), 120)
    alias = _safe_text(target.get("alias"), 200) or channel_name
    source_ref, callback_to = _onboarding_refs(spec=spec, target=target)
    message = (
        "[项目启动首发可见消息]\n"
        f"当前项目: {project_name}（{project_id}）\n"
        f"目标通道: {channel_name}\n"
        f"目标Agent: {alias}; session_id={session_id}\n"
        "本次目标: 验证新项目 primary Agent 可被正式 announce 触达，并在右侧聊天记录可见。\n"
        "请仅回复: OK\n"
    )
    return {
        "projectId": project_id,
        "channelName": channel_name,
        "sessionId": session_id,
        "sender_type": "system",
        "sender_id": "project_bootstrap_onboarding",
        "sender_name": "项目启动上岗门禁",
        "message": message,
        "interaction_mode": "dialog_now",
        "message_kind": "collab_update",
        "source_ref": source_ref,
        "callback_to": callback_to,
        "owner_ref": {
            "channel_name": channel_name,
            "agent_name": alias,
            "session_id": session_id,
            "alias": alias,
        },
        "run_extra_meta": {
            "trigger_type": "project_bootstrap_first_visible",
            "onboarding_message_type": "first_visible_message",
            "onboarding_project_id": project_id,
        },
    }


def _build_init_training_onboarding_payload(*, spec: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    project_id = _safe_text(spec.get("project_id"), 80)
    project_name = _safe_text(spec.get("project_name"), 200) or project_id
    channel_name = _safe_text(target.get("channel_name"), 240)
    session_id = _safe_text(target.get("session_id"), 120)
    alias = _safe_text(target.get("alias"), 200) or channel_name
    purpose = _safe_text(target.get("purpose"), 300) or "项目 primary 协作会话"
    source_ref, callback_to = _onboarding_refs(spec=spec, target=target)
    message = (
        "[Agent启动培训]\n"
        f"你是新项目首批 live 主 Agent：{alias}\n"
        f"你的 session_id：{session_id}\n"
        f"所属项目：{project_name}（{project_id}）\n"
        f"所属通道：{channel_name}\n"
        f"职责边界：{purpose}\n\n"
        "你先完成 4 件事：\n"
        "1. 阅读项目 README、通道 README、任务/、问题/、产出物/材料/、产出物/沉淀/。\n"
        "2. 核对当前通道职责边界，不自行扩题。\n"
        "3. 后续正式协作必须走 POST /api/codex/announce 或 message_cli 封装。\n"
        "4. 收到 task_with_receipt 或 dialog_now 后先回首回执，处理完成后再回结构化结果。\n\n"
        "协作硬要求：\n"
        "1. 你后续给任何 Agent 发消息时，必须带上自己的 session_id。\n"
        "2. 若消息中有 callback_to.session_id，优先回给该 session。\n"
        "3. 声称已送达必须具备 announce_run_id + target_session_id一致 + visible_in_channel_chat=true。\n"
        "4. 不能用 direct resume、草稿、任务文件或 CLI 退出码冒充已通知。\n\n"
        "请仅按以下结构回复：\n"
        "已完成初始化\n"
        "职责边界: <一句话>\n"
        "当前主线: <一句话>\n"
        "唯一阻塞: <无/一句话>\n"
        "首个动作: <一句话>\n"
        "回执口径: <一句话>\n"
        "闭环方式: <任务文件收口块|增强验收包>\n"
    )
    return {
        "projectId": project_id,
        "channelName": channel_name,
        "sessionId": session_id,
        "sender_type": "agent",
        "sender_id": "project_bootstrap_onboarding",
        "sender_name": "项目启动上岗门禁",
        "message": message,
        "interaction_mode": "task_with_receipt",
        "message_kind": "collab_update",
        "source_ref": source_ref,
        "callback_to": callback_to,
        "owner_ref": {
            "channel_name": channel_name,
            "agent_name": alias,
            "session_id": session_id,
            "alias": alias,
        },
        "sender_agent_ref": {
            "agent_name": "项目启动上岗门禁",
            "session_id": source_ref.get("session_id") or "",
            "alias": "项目启动上岗门禁",
        },
        "run_extra_meta": {
            "trigger_type": "agent_init_training",
            "init_mode": "fresh",
            "onboarding_message_type": "init_training",
            "current_workstream": "完成新项目启动培训并回初始化回执",
            "recommended_skills": ["collab-message-send", "agent-init-training-playbook"],
        },
    }


def _onboarding_evidence_from_result(
    *,
    result: dict[str, Any],
    expected_session_id: str,
    verify_delivery: Callable[..., dict[str, Any]] | None,
    payload: dict[str, Any],
    message_type: str,
) -> dict[str, Any]:
    verified: dict[str, Any] = {}
    if callable(verify_delivery):
        try:
            candidate = verify_delivery(
                message_type=message_type,
                payload=payload,
                announce_result=result,
                expected_session_id=expected_session_id,
            )
            if isinstance(candidate, dict):
                verified = dict(candidate)
        except TypeError:
            candidate = verify_delivery(result)
            if isinstance(candidate, dict):
                verified = dict(candidate)
    run = result.get("run") if isinstance(result.get("run"), dict) else {}
    run_extra = run.get("extra_meta") if isinstance(run.get("extra_meta"), dict) else {}
    communication_view = run.get("communication_view") if isinstance(run.get("communication_view"), dict) else {}
    out = {
        "announce_run_id": _safe_text(
            verified.get("announce_run_id")
            or verified.get("announceRunId")
            or result.get("announce_run_id")
            or result.get("announceRunId")
            or run.get("id"),
            120,
        ),
        "target_session_id": _safe_text(
            verified.get("target_session_id")
            or verified.get("targetSessionId")
            or result.get("target_session_id")
            or result.get("targetSessionId")
            or communication_view.get("target_session_id")
            or run.get("sessionId")
            or expected_session_id,
            120,
        ),
        "visible_in_channel_chat": _coerce_bool(
            verified.get("visible_in_channel_chat")
            if "visible_in_channel_chat" in verified
            else (
                verified.get("visibleInChannelChat")
                if "visibleInChannelChat" in verified
                else (
                    result.get("visible_in_channel_chat")
                    if "visible_in_channel_chat" in result
                    else (
                        result.get("visibleInChannelChat")
                        if "visibleInChannelChat" in result
                        else (
                            run_extra.get("visible_in_channel_chat")
                            if "visible_in_channel_chat" in run_extra
                            else run.get("visible_in_channel_chat")
                        )
                    )
                )
            ),
            False,
        ),
        "channel_name": _safe_text(payload.get("channelName") or payload.get("channel_name"), 240),
        "message_type": message_type,
    }
    return out


def dispatch_project_bootstrap_onboarding(
    *,
    spec: dict[str, Any],
    session_store: Any,
    created_sessions: list[dict[str, Any]],
    completion_gate: dict[str, Any],
    announce_onboarding_message: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    verify_onboarding_delivery: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    bootstrap = spec.get("bootstrap") if isinstance(spec.get("bootstrap"), dict) else {}
    send_first = bool(bootstrap.get("send_bootstrap_message"))
    send_training = bool(bootstrap.get("send_init_training"))
    project_id = _safe_text(spec.get("project_id"), 80)
    result: dict[str, Any] = {
        "ok": True,
        "state": "skipped",
        "skipped": True,
        "project_id": project_id,
        "isolation": {
            "required": send_first or send_training,
            "ok": False,
            "project_id": project_id,
            "test_project_only": True,
            "reason": "",
        },
        "first_visible_messages": [],
        "init_training_messages": [],
        "missing_items": [],
        "onboarding": {
            "first_visible_messages": [],
            "init_training_messages": [],
        },
    }
    if not (send_first or send_training):
        result["isolation"]["reason"] = "not_requested"
        return result
    result["skipped"] = False
    targets = _onboarding_target_sessions(
        spec=spec,
        session_store=session_store,
        created_sessions=created_sessions,
    )
    if not bool(completion_gate.get("ok") or completion_gate.get("collaboration_ready")):
        result["ok"] = False
        result["state"] = "blocked"
        result["missing_items"].append({"code": "p0_completion_not_ready", "message": "P0 completion gate 未 ready，禁止发送上岗消息"})
        return result
    if not targets:
        result["ok"] = False
        result["state"] = "blocked"
        result["missing_items"].append({"code": "primary_onboarding_target", "message": "缺少可承载上岗消息的 primary session"})
        return result
    isolation_ok, isolation_reason = _is_onboarding_isolated_test_project(project_id, bootstrap)
    result["isolation"]["ok"] = isolation_ok
    result["isolation"]["reason"] = isolation_reason or "isolated_test_project"
    if not isolation_ok:
        result["ok"] = False
        result["state"] = "blocked"
        result["missing_items"].append(
            {
                "code": "onboarding_isolation_required",
                "message": "真实上岗消息只允许隔离测试项目发送",
                "reason": isolation_reason,
            }
        )
        return result
    if not callable(announce_onboarding_message):
        result["ok"] = False
        result["state"] = "blocked"
        result["missing_items"].append({"code": "onboarding_sender_not_configured", "message": "缺少真实 announce sender，未发送"})
        return result

    has_failure = False
    for target in targets:
        for message_type, builder, bucket in (
            ("first_visible_message", _build_first_visible_onboarding_payload, "first_visible_messages"),
            ("init_training", _build_init_training_onboarding_payload, "init_training_messages"),
        ):
            if message_type == "first_visible_message" and not send_first:
                continue
            if message_type == "init_training" and not send_training:
                continue
            payload = builder(spec=spec, target=target)
            try:
                send_result = announce_onboarding_message(payload)
            except Exception as exc:
                send_result = {"ok": False, "error": _safe_text(exc, 1000)}
            if not isinstance(send_result, dict):
                send_result = {"ok": False, "error": "invalid announce sender result"}
            evidence = _onboarding_evidence_from_result(
                result=send_result,
                expected_session_id=_safe_text(target.get("session_id"), 120),
                verify_delivery=verify_onboarding_delivery,
                payload=payload,
                message_type=message_type,
            )
            evidence["ok"] = bool(send_result.get("ok", True)) and not bool(send_result.get("error"))
            if send_result.get("error"):
                evidence["error"] = _safe_text(send_result.get("error"), 1000)
            result[bucket].append(evidence)
            result["onboarding"][bucket].append(evidence)
            if not evidence["ok"]:
                has_failure = True
    if has_failure:
        result["ok"] = False
        result["state"] = "partial"
        result["missing_items"].append({"code": "onboarding_send_failed", "message": "至少一条上岗消息发送失败"})
    else:
        result["state"] = "sent"
    return result


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

    return spec, existing_project, []


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


def create_project_scaffold(
    *,
    spec: dict[str, Any],
    config_path: Path | None = None,
    repo_root: Path | None = None,
) -> dict[str, Any]:
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
        channel_root = (task_root / channel["name"]).resolve()
        if not _path_within(channel_root, task_root.resolve()):
            raise PermissionError("channel path escapes task root")
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

    project_agents_md = _write_project_agents_md(spec=spec)
    channel_agents_md: list[dict[str, Any]] = []
    if config_path is not None and repo_root is not None:
        channel_agents_md = _write_bootstrap_channel_agents_md(
            spec=spec,
            config_path=config_path,
            repo_root=repo_root,
        )

    return {
        "ok": True,
        "project_root": str(project_root),
        "task_root": str(task_root),
        "channel_root_count": len(created_channel_roots),
        "channel_roots": created_channel_roots,
        "project_agents_md": project_agents_md,
        "channel_agents_md": channel_agents_md,
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
        primary_alias = _primary_session_alias(spec=spec, channel=channel)
        primary_purpose = _primary_session_purpose(spec=spec, channel=channel)
        payload = {
            "project_id": spec["project_id"],
            "channel_name": channel["name"],
            "cli_type": channel["cli_type"],
            "model": channel["model"],
            "reasoning_effort": channel["reasoning_effort"],
            "alias": primary_alias,
            "purpose": primary_purpose,
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
                "alias": _safe_text(session.get("alias"), 200) or primary_alias,
                "purpose": _safe_text(session.get("purpose"), 200) or primary_purpose,
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
        registry_path = Path(registry_paths[0])
        if registry_path.exists():
            try:
                registry_data = json.loads(registry_path.read_text(encoding="utf-8"))
                ccr_validation = (
                    registry_data.get("ccr_validation")
                    if isinstance(registry_data, dict) and isinstance(registry_data.get("ccr_validation"), dict)
                    else {}
                )
                if ccr_validation:
                    registry_payload["ccr_validation"] = ccr_validation
                    if bool(ccr_validation.get("blocking")):
                        registry_payload["degraded"] = True
                        registry_payload["state"] = "degraded"
                        registry_payload["degraded_reason"] = "ccr_validation_blocking"
            except Exception as exc:
                registry_payload["ccr_validation_error"] = _safe_text(exc, 1000)

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
    announce_onboarding_message: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    verify_onboarding_delivery: Callable[..., dict[str, Any]] | None = None,
) -> tuple[int, dict[str, Any]]:
    step_results: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    spec: dict[str, Any] = {}

    def _base_payload() -> dict[str, Any]:
        return {
            "ok": False,
            "creation_ok": False,
            "project_id": _safe_text(spec.get("project_id"), 80),
            "reused": False,
            "completion_state": "",
            "collaboration_ready": False,
            "completion_gate": {},
            "onboarding_state": "",
            "onboarding_ready": False,
            "onboarding_gate": {},
            "onboarding_delivery": {},
            "resume_from_step": "",
            "config_path": str(config_path),
            "project_root": str(spec.get("project_root") or ""),
            "task_root": str(spec.get("task_root") or ""),
            "session_store_path": str(spec.get("session_store_path") or ""),
            "registry_paths": list(spec.get("registry_paths") or []),
            "created_sessions": [],
            "project_agents_md": {},
            "channel_agents_md": [],
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
                "creation_ok": False,
                "reused": bool(existing_project),
                "dry_run": True,
                "completion_state": "dry_run",
                "collaboration_ready": False,
                "completion_gate": {
                    "ok": False,
                    "state": "dry_run",
                    "collaboration_ready": False,
                    "skipped": True,
                    "missing_items": [],
                    "checks": [],
                },
                "onboarding_state": "dry_run",
                "onboarding_ready": False,
                "onboarding_gate": {
                    "ok": False,
                    "state": "dry_run",
                    "onboarding_ready": False,
                    "skipped": True,
                    "missing_items": [],
                    "checks": [],
                },
                "onboarding_delivery": {
                    "ok": True,
                    "state": "dry_run",
                    "skipped": True,
                },
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
        scaffold_result = create_project_scaffold(
            spec=spec,
            config_path=config_path,
            repo_root=repo_root,
        )
        step_results.append(
            {
                "step": "create_scaffold",
                "ok": True,
                "project_root": scaffold_result["project_root"],
                "task_root": scaffold_result["task_root"],
                "project_agents_md": scaffold_result.get("project_agents_md"),
                "channel_agents_md_count": len(scaffold_result.get("channel_agents_md") or []),
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

    completion_gate = build_project_bootstrap_completion_gate(
        spec=spec,
        session_store=session_store,
        created_sessions=created_sessions,
        verify_result=verify_result,
    )
    onboarding_delivery = dispatch_project_bootstrap_onboarding(
        spec=spec,
        session_store=session_store,
        created_sessions=created_sessions,
        completion_gate=completion_gate,
        announce_onboarding_message=announce_onboarding_message,
        verify_onboarding_delivery=verify_onboarding_delivery,
    )
    verify_result["onboarding"] = onboarding_delivery.get("onboarding") if isinstance(onboarding_delivery.get("onboarding"), dict) else {}
    step_results.append(
        {
            "step": "send_onboarding_messages",
            "ok": bool(onboarding_delivery.get("ok")),
            "state": _safe_text(onboarding_delivery.get("state"), 40),
            "skipped": bool(onboarding_delivery.get("skipped")),
            "missing_count": len(onboarding_delivery.get("missing_items") or []),
        }
    )
    onboarding_gate = build_project_bootstrap_onboarding_gate(
        spec=spec,
        session_store=session_store,
        created_sessions=created_sessions,
        completion_gate=completion_gate,
        verify_result=verify_result,
    )
    payload = _base_payload()
    payload.update(
        {
            "ok": True,
            "creation_ok": True,
            "reused": bool(existing_project),
            "completion_state": completion_gate["state"],
            "collaboration_ready": bool(completion_gate.get("collaboration_ready")),
            "completion_gate": completion_gate,
            "onboarding_state": onboarding_gate["state"],
            "onboarding_ready": bool(onboarding_gate.get("onboarding_ready")),
            "onboarding_gate": onboarding_gate,
            "onboarding_delivery": onboarding_delivery,
            "created_sessions": created_sessions,
            "project_agents_md": scaffold_result.get("project_agents_md"),
            "channel_agents_md": scaffold_result.get("channel_agents_md"),
            "registry": verify_result.get("registry"),
            "dedup_results": verify_result.get("dedup_results"),
            "visibility_check": verify_result.get("visibility_check"),
        }
    )
    return 200, payload


__all__ = [
    "bootstrap_project_response",
    "build_project_bootstrap_completion_gate",
    "build_project_bootstrap_onboarding_gate",
    "dispatch_project_bootstrap_onboarding",
    "build_project_registry_and_verify",
    "bootstrap_project_primary_sessions",
    "create_project_scaffold",
    "init_project_session_store",
    "validate_project_bootstrap_request",
    "write_project_config_block",
]
