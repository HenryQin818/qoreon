from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

from task_dashboard.public_bootstrap import (
    DEFAULT_PROJECT_ID,
    bootstrap_public_example,
    resolve_public_example_paths,
)


def _load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} root must be object")
    return data


def _load_optional_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return _load_json(path)


def _ensure_public_safe(path: Path, payload: dict[str, Any]) -> None:
    if not payload.get("public_safe"):
        raise ValueError(f"{path} must declare public_safe=true")
    if not str(payload.get("schema_version") or "").strip():
        raise ValueError(f"{path} must declare schema_version")


def _safe_rel(path: Path, repo_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except Exception:
        return str(path)


def _http_json(
    *,
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
    token: str = "",
    timeout_s: float = 120.0,
) -> dict[str, Any]:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    if token:
        headers["Authorization"] = f"Bearer {token}"
        headers["X-TaskDashboard-Token"] = token
    req = urllib_request.Request(url, data=data, headers=headers, method=method.upper())
    try:
        with urllib_request.urlopen(req, timeout=timeout_s) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib_error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw)
        except Exception:
            payload = {"error": raw or str(exc)}
        raise RuntimeError(
            f"{method.upper()} {url} failed: {exc.code} {payload.get('error') or payload.get('detail') or raw}"
        ) from exc
    except urllib_error.URLError as exc:
        raise RuntimeError(f"{method.upper()} {url} failed: {exc}") from exc
    try:
        parsed = json.loads(raw)
    except Exception as exc:
        raise RuntimeError(f"{method.upper()} {url} returned non-json payload") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError(f"{method.upper()} {url} returned invalid payload")
    return parsed


def _channel_key(channel_name: str) -> str:
    return str(channel_name or "").strip()


def _unique_nonempty(items: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        value = str(item or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _build_learning_paths(
    *,
    channel_name: str,
    default_collaboration_entry: str = "",
    default_read_order: list[str] | None = None,
) -> list[str]:
    task_root = f"examples/standard-project/tasks/{channel_name}"
    return _unique_nonempty(
        [
            *(default_read_order or []),
            f"{task_root}/任务/",
            f"{task_root}/反馈/",
            f"{task_root}/产出物/材料/",
            f"{task_root}/产出物/沉淀/",
            default_collaboration_entry,
            "examples/standard-project/tasks/辅助05-团队协作Skills治理/产出物/沉淀/03-公开公共技能包清单.md",
            "examples/standard-project/skills/INDEX.md",
        ]
    )


def _build_session_first_message(
    project_name: str,
    channel: dict[str, Any],
    agent: dict[str, Any],
) -> str:
    channel_name = str(channel.get("name") or "").strip()
    role = str(agent.get("role") or "协作 Agent").strip() or "协作 Agent"
    return (
        f"[qoreon-demo] new session · {project_name} · {channel_name}\n\n"
        f"角色：{role}。只处理公开安全的示例内容。\n"
        "先查看你负责通道下的 `任务/`、`反馈/`、`产出物/材料/`、`产出物/沉淀/`，"
        "并重点学习公共技能 `project-startup-collab-suite`、`agent-init-training-playbook`、`collab-message-send`。\n"
        f"请仅回复：OK（{channel_name}-{role}）"
    )


def _build_training_action_message(
    *,
    channel_name: str,
    role: str,
    learning_paths: list[str],
    skills: list[str],
) -> str:
    path_lines = "\n".join(f"- `{row}`" for row in learning_paths)
    skill_lines = "\n".join(f"- `{row}`" for row in skills) or "- `collab-message-send`"
    return (
        f"你现在负责 `{channel_name}`，角色是 `{role}`。先完成首轮培训，不要直接进入实现。\n\n"
        "请先阅读这些文件和知识沉淀：\n"
        f"{path_lines}\n\n"
        "重点学习这些公共技能：\n"
        f"{skill_lines}\n\n"
        "阅读完成后，只回一条最小回执，必须包含：\n"
        "`当前结论 / 是否通过或放行 / 唯一阻塞 / 关键路径或 run_id / 下一步动作`\n\n"
        "并在回执里补充：\n"
        "1. 你已经阅读了哪些通道资料\n"
        "2. 你的职责边界复述\n"
        "3. 你当前不负责什么\n"
        "4. 你下一步准备协同谁\n\n"
        "一般情况下都要回给原发送 Agent。"
    )


def build_public_example_activation_plan(
    repo_root: Path,
    *,
    project_id: str = DEFAULT_PROJECT_ID,
    example_root_rel: str | Path | None = None,
    include_optional: bool = False,
) -> dict[str, Any]:
    paths = resolve_public_example_paths(
        repo_root,
        project_id=project_id,
        example_root_rel=example_root_rel,
    )
    repo_root = paths["repo_root"]
    seed_root = paths["seed_root"]
    project_seed = _load_json(seed_root / "project_seed.json")
    channels_seed = _load_json(seed_root / "channels_seed.json")
    agents_seed = _load_json(seed_root / "agents_seed.json")
    tasks_seed = _load_json(seed_root / "tasks_seed.json")
    ccr_seed = _load_optional_json(seed_root / "ccr_roster_seed.json")
    for path, payload in (
        (seed_root / "project_seed.json", project_seed),
        (seed_root / "channels_seed.json", channels_seed),
        (seed_root / "agents_seed.json", agents_seed),
        (seed_root / "tasks_seed.json", tasks_seed),
    ):
        _ensure_public_safe(path, payload)
    if ccr_seed:
        _ensure_public_safe(seed_root / "ccr_roster_seed.json", ccr_seed)

    project = project_seed.get("project") if isinstance(project_seed.get("project"), dict) else {}
    project_id = str(project.get("id") or "").strip()
    project_name = str(project.get("name") or "").strip() or project_id
    if not project_id:
        raise ValueError("project_seed.json missing project.id")

    channels = [row for row in (channels_seed.get("channels") or []) if isinstance(row, dict)]
    agents = [row for row in (agents_seed.get("agents") or []) if isinstance(row, dict)]
    tasks = [row for row in (tasks_seed.get("tasks") or []) if isinstance(row, dict)]
    channel_by_name = {_channel_key(str(row.get("name") or "")): row for row in channels if _channel_key(str(row.get("name") or ""))}
    ccr_channels = [row for row in (ccr_seed.get("channels") or []) if isinstance(row, dict)]
    ccr_by_name = {_channel_key(str(row.get("channel_name") or "")): row for row in ccr_channels if _channel_key(str(row.get("channel_name") or ""))}
    default_read_order = [str(row).strip() for row in (ccr_seed.get("default_read_order") or []) if str(row).strip()]

    enabled_channels = [
        row for row in channels
        if include_optional or bool(row.get("default_enabled"))
    ]
    enabled_channel_names = {_channel_key(str(row.get("name") or "")) for row in enabled_channels}
    enabled_agents = [
        row for row in agents
        if _channel_key(str(row.get("channel_name") or "")) in enabled_channel_names
        and (include_optional or bool(row.get("default_enabled")))
    ]

    session_specs: list[dict[str, Any]] = []
    for agent in enabled_agents:
        channel_name = _channel_key(str(agent.get("channel_name") or ""))
        channel = channel_by_name.get(channel_name)
        if not channel:
            raise ValueError(f"agent references unknown channel: {channel_name}")
        ccr_row = ccr_by_name.get(channel_name, {})
        learning_paths = _build_learning_paths(
            channel_name=channel_name,
            default_collaboration_entry=str(ccr_row.get("default_collaboration_entry") or "").strip(),
            default_read_order=default_read_order,
        )
        skills = [str(row).strip() for row in (agent.get("skills") or []) if str(row).strip()]
        session_specs.append(
            {
                "agent_id": str(agent.get("agent_id") or "").strip(),
                "channel_name": channel_name,
                "role": str(agent.get("role") or "").strip(),
                "cli_type": str(agent.get("cli_type") or "codex").strip() or "codex",
                "skills": skills,
                "learning_paths": learning_paths,
                "first_message": _build_session_first_message(project_name, channel, agent),
            }
        )

    task_by_channel: dict[str, str] = {}
    for task in tasks:
        channel_name = _channel_key(str(task.get("channel_name") or ""))
        if channel_name and channel_name not in task_by_channel:
            task_by_channel[channel_name] = str(task.get("title") or "").strip()

    sample_actions: list[dict[str, Any]] = []
    for spec in session_specs:
        sample_actions.append(
            {
                "channel_name": spec["channel_name"],
                "title": task_by_channel.get(spec["channel_name"], ""),
                "message": _build_training_action_message(
                    channel_name=spec["channel_name"],
                    role=str(spec.get("role") or ""),
                    learning_paths=list(spec.get("learning_paths") or []),
                    skills=list(spec.get("skills") or []),
                ),
            }
        )

    return {
        "schema_version": "1.0",
        "public_safe": True,
        "project_id": project_id,
        "project_name": project_name,
        "include_optional": bool(include_optional),
        "enabled_channel_names": [str(row.get("name") or "").strip() for row in enabled_channels],
        "session_specs": session_specs,
        "sample_actions": sample_actions,
    }


def write_public_example_startup_batch(
    repo_root: Path,
    *,
    project_id: str = DEFAULT_PROJECT_ID,
    example_root_rel: str | Path | None = None,
    include_optional: bool = False,
) -> dict[str, Any]:
    paths = resolve_public_example_paths(
        repo_root,
        project_id=project_id,
        example_root_rel=example_root_rel,
    )
    repo_root = paths["repo_root"]
    runtime_root = paths["runtime_root"]
    bootstrap_public_example(
        repo_root,
        project_id=project_id,
        example_root_rel=example_root_rel,
    )
    plan = build_public_example_activation_plan(
        repo_root,
        project_id=project_id,
        example_root_rel=example_root_rel,
        include_optional=include_optional,
    )
    json_path = runtime_root / "startup-batch.json"
    md_path = runtime_root / "startup-batch.md"
    payload = {
        "schema_version": "1.0",
        "public_safe": True,
        "project_id": plan["project_id"],
        "project_name": plan["project_name"],
        "include_optional": bool(include_optional),
        "session_specs": plan["session_specs"],
        "sample_actions": plan["sample_actions"],
        "next_steps": [
            "把 docs/public/ai-bootstrap.md 与本文件一起交给安装电脑上的 AI",
            "让 AI 按 session_specs 顺序创建或复用默认通道会话",
            "创建完成后，让每个通道先阅读自己目录下的任务与沉淀，再由 主体-总控 派发首轮启动消息并开始接管项目",
        ],
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        f"# {plan['project_name']} 启动批次",
        "",
        "把本文件和 `docs/public/ai-bootstrap.md` 一起交给安装电脑上的 AI。",
        "",
        "## 启动目标",
        "",
        f"- 目标项目：`{plan['project_id']}`",
        f"- 默认通道数：`{len(plan['enabled_channel_names'])}`",
        f"- 默认会话数：`{len(plan['session_specs'])}`",
        "",
        "## AI 要做的事",
        "",
        "1. 确认 `standard_project` 已能在页面中看到。",
        "2. 按下方会话顺序，逐个创建或复用默认通道会话。",
        "3. 完成后，在 `主体-总控` 中发起首轮启动协调。",
        "",
        "## 默认会话顺序",
        "",
    ]
    for idx, spec in enumerate(plan["session_specs"], start=1):
        lines.extend(
            [
                f"{idx}. `{spec['channel_name']}` / `{spec['role']}` / `{spec['cli_type']}`",
                f"   公共技能：`{', '.join(spec.get('skills') or [])}`",
                f"   首发消息：`{spec['first_message']}`",
            ]
        )
        learning_paths = [str(row).strip() for row in (spec.get("learning_paths") or []) if str(row).strip()]
        if learning_paths:
            lines.append("   学习入口：")
            for path in learning_paths:
                lines.append(f"   - `{path}`")
    if plan["sample_actions"]:
        lines.extend(["", "## 首轮建议动作", ""])
        for idx, row in enumerate(plan["sample_actions"], start=1):
            lines.extend(
                [
                    f"{idx}. `{row['channel_name']}`",
                    f"   目标：{row['message']}",
                ]
            )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {
        "project_id": plan["project_id"],
        "json_path": str(json_path),
        "markdown_path": str(md_path),
        "session_count": len(plan["session_specs"]),
        "channel_count": len(plan["enabled_channel_names"]),
    }


def _poll_run_status(
    *,
    base_url: str,
    run_id: str,
    token: str,
    timeout_s: float,
    poll_interval_s: float,
) -> dict[str, Any]:
    deadline = time.time() + max(5.0, float(timeout_s))
    last_payload: dict[str, Any] = {}
    while time.time() < deadline:
        payload = _http_json(
            method="GET",
            url=f"{base_url.rstrip('/')}/api/codex/run/{run_id}",
            token=token,
            timeout_s=max(5.0, poll_interval_s + 5.0),
        )
        last_payload = payload
        run = payload.get("run") if isinstance(payload.get("run"), dict) else {}
        status = str(run.get("status") or "").strip().lower()
        if status in {"done", "error", "cancelled", "canceled", "timeout"}:
            return payload
        time.sleep(max(0.5, float(poll_interval_s)))
    return last_payload


def activate_public_example_agents(
    repo_root: Path,
    *,
    base_url: str,
    project_id: str = DEFAULT_PROJECT_ID,
    example_root_rel: str | Path | None = None,
    token: str = "",
    include_optional: bool = False,
    run_sample_actions: bool = True,
    wait_timeout_s: float = 240.0,
    poll_interval_s: float = 2.0,
) -> dict[str, Any]:
    paths = resolve_public_example_paths(
        repo_root,
        project_id=project_id,
        example_root_rel=example_root_rel,
    )
    repo_root = paths["repo_root"]
    runtime_root = paths["runtime_root"]
    bootstrap_public_example(
        repo_root,
        project_id=project_id,
        example_root_rel=example_root_rel,
    )
    plan = build_public_example_activation_plan(
        repo_root,
        project_id=project_id,
        example_root_rel=example_root_rel,
        include_optional=include_optional,
    )
    activation_result_path = runtime_root / "activation-result.json"
    created_sessions: list[dict[str, Any]] = []
    session_id_by_channel: dict[str, str] = {}

    for index, spec in enumerate(plan["session_specs"]):
        # The first session doubles as a real non-interactive Codex probe on a
        # new computer. Keep it bounded so installs do not hang for a very long
        # time when the local CLI is present but background session creation is
        # still blocked by auth or environment gating.
        if index == 0:
            create_timeout_s = int(min(max(wait_timeout_s, 60.0), 120.0))
        else:
            create_timeout_s = int(min(max(wait_timeout_s, 180.0), 1800.0))
        payload = {
            "project_id": plan["project_id"],
            "channel_name": spec["channel_name"],
            "cli_type": spec["cli_type"],
            "reuse_strategy": "reuse_active",
            "create_timeout_s": create_timeout_s,
            "first_message": spec["first_message"],
        }
        response = _http_json(
            method="POST",
            url=f"{base_url.rstrip('/')}/api/sessions",
            payload=payload,
            token=token,
            timeout_s=max(float(create_timeout_s) + 30.0, 120.0),
        )
        session = response.get("session") if isinstance(response.get("session"), dict) else {}
        session_id = str(session.get("id") or session.get("sessionId") or "").strip()
        if not session_id:
            raise RuntimeError(f"session create returned empty session id for {spec['channel_name']}")
        session_id_by_channel[spec["channel_name"]] = session_id
        created_sessions.append(
            {
                "channel_name": spec["channel_name"],
                "agent_id": spec["agent_id"],
                "session_id": session_id,
                "created": bool(response.get("created")),
                "reused": bool(response.get("reused")),
                "attached": bool(response.get("attached")),
                "workdir": str(response.get("workdir") or ""),
                "session_path": str(response.get("sessionPath") or ""),
            }
        )

    announced_runs: list[dict[str, Any]] = []
    if run_sample_actions:
        for action in plan["sample_actions"]:
            channel_name = str(action["channel_name"])
            session_id = session_id_by_channel.get(channel_name, "")
            if not session_id:
                continue
            response = _http_json(
                method="POST",
                url=f"{base_url.rstrip('/')}/api/codex/announce",
                payload={
                    "projectId": plan["project_id"],
                    "channelName": channel_name,
                    "sessionId": session_id,
                    "message": action["message"],
                    "senderType": "system",
                    "senderId": "public_example_activation",
                    "senderName": "开源示例激活器",
                },
                token=token,
                timeout_s=max(30.0, poll_interval_s + 10.0),
            )
            run = response.get("run") if isinstance(response.get("run"), dict) else {}
            run_id = str(run.get("id") or "").strip()
            if not run_id:
                raise RuntimeError(f"announce returned empty run id for {channel_name}")
            announced_runs.append(
                {
                    "channel_name": channel_name,
                    "session_id": session_id,
                    "run_id": run_id,
                    "title": str(action.get("title") or ""),
                    "message": str(action["message"]),
                    "status": str(run.get("status") or "").strip(),
                }
            )

    observed_runs: list[dict[str, Any]] = []
    if run_sample_actions:
        for row in announced_runs:
            payload = _poll_run_status(
                base_url=base_url,
                run_id=row["run_id"],
                token=token,
                timeout_s=wait_timeout_s,
                poll_interval_s=poll_interval_s,
            )
            run = payload.get("run") if isinstance(payload.get("run"), dict) else {}
            observed_runs.append(
                {
                    **row,
                    "status": str(run.get("status") or "").strip(),
                    "last_message": str(payload.get("lastMessage") or "").strip(),
                    "error": str(run.get("error") or payload.get("error") or "").strip(),
                }
            )

    completed_runs = [row for row in observed_runs if row["status"].lower() == "done"]
    manifest = {
        "schema_version": "1.0",
        "public_safe": True,
        "activated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime()),
        "project_id": plan["project_id"],
        "project_name": plan["project_name"],
        "base_url": base_url,
        "include_optional": bool(include_optional),
        "run_sample_actions": bool(run_sample_actions),
        "counts": {
            "channels": len(plan["enabled_channel_names"]),
            "sessions": len(created_sessions),
            "sample_runs": len(observed_runs),
            "completed_runs": len(completed_runs),
        },
        "artifacts": {
            "runtime_root": _safe_rel(runtime_root, repo_root),
            "activation_result_path": _safe_rel(activation_result_path, repo_root),
        },
        "channels": plan["enabled_channel_names"],
        "sessions": created_sessions,
        "runs": observed_runs,
        "next_steps": [
            f"打开 project-task-dashboard 页面确认 {plan['project_id']} 的会话与运行痕迹可见",
            "把 docs/public/ai-bootstrap.md 提供给你的 AI，让它按推荐结构继续推进",
        ],
    }
    if not run_sample_actions:
        manifest["next_steps"].insert(
            1,
            "当前只完成默认启动批次的会话拉起；后续协作动作由主体-总控继续派发",
        )
    activation_result_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        "ok": True,
        "activation_result_path": str(activation_result_path),
        "project_id": plan["project_id"],
        "counts": manifest["counts"],
        "sessions": created_sessions,
        "runs": observed_runs,
    }
