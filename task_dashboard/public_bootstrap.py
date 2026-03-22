from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


DEFAULT_PROJECT_ID = "standard_project"
PUBLIC_EXAMPLE_ROOTS = {
    "minimal_project": Path("examples/minimal-project"),
    "standard_project": Path("examples/standard-project"),
}

REQUIRED_CHANNEL_DIRS = ("任务", "反馈", "产出物/沉淀")


def _load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} root must be object")
    return data


def _ensure_public_safe(path: Path, payload: dict[str, Any]) -> None:
    if not payload.get("public_safe"):
        raise ValueError(f"{path} must declare public_safe=true")
    if not str(payload.get("schema_version") or "").strip():
        raise ValueError(f"{path} must declare schema_version")


def _slug_channel(name: str) -> str:
    return str(name or "").strip().replace("/", "-")


def _task_template(title: str, channel_name: str, status: str) -> str:
    return (
        f"# {title}\n\n"
        "## 当前状态\n\n"
        f"- 状态：{status}\n"
        f"- 通道：{channel_name}\n\n"
        "## 当前目标\n\n"
        "- 完成公开版最小任务样例。\n\n"
        "## 下一步动作\n\n"
        "- 按示例项目规则推进并回执。\n"
    )


def resolve_public_example_root_rel(
    *,
    project_id: str | None = None,
    example_root_rel: str | Path | None = None,
) -> Path:
    if example_root_rel is not None:
        return Path(str(example_root_rel).strip())
    selected_project_id = str(project_id or DEFAULT_PROJECT_ID).strip() or DEFAULT_PROJECT_ID
    selected_root_rel = PUBLIC_EXAMPLE_ROOTS.get(selected_project_id)
    if selected_root_rel is None:
        supported = ", ".join(sorted(PUBLIC_EXAMPLE_ROOTS))
        raise ValueError(f"unknown public example project_id={selected_project_id!r}; supported: {supported}")
    return selected_root_rel


def resolve_public_example_paths(
    repo_root: Path,
    *,
    project_id: str | None = None,
    example_root_rel: str | Path | None = None,
) -> dict[str, Path]:
    repo_root = repo_root.resolve()
    selected_root_rel = resolve_public_example_root_rel(
        project_id=project_id,
        example_root_rel=example_root_rel,
    )
    example_root = (repo_root / selected_root_rel).resolve()
    seed_root = (example_root / "seed").resolve()
    runtime_root = (example_root / ".runtime" / "demo").resolve()
    runtime_sessions = runtime_root / ".sessions"
    runtime_runs = runtime_root / ".runs"
    return {
        "repo_root": repo_root,
        "selected_root_rel": selected_root_rel,
        "example_root": example_root,
        "seed_root": seed_root,
        "runtime_root": runtime_root,
        "runtime_sessions": runtime_sessions,
        "runtime_runs": runtime_runs,
    }


def bootstrap_public_example(
    repo_root: Path,
    *,
    project_id: str | None = None,
    example_root_rel: str | Path | None = None,
) -> dict[str, Any]:
    paths = resolve_public_example_paths(
        repo_root,
        project_id=project_id,
        example_root_rel=example_root_rel,
    )
    repo_root = paths["repo_root"]
    selected_root_rel = paths["selected_root_rel"]
    example_root = paths["example_root"]
    seed_root = paths["seed_root"]
    runtime_root = paths["runtime_root"]
    runtime_sessions = paths["runtime_sessions"]
    runtime_runs = paths["runtime_runs"]

    inventory_path = seed_root / "seed-inventory.json"
    inventory = _load_json(inventory_path)
    _ensure_public_safe(inventory_path, inventory)

    required_files = [str(item).strip() for item in inventory.get("files") or [] if str(item).strip()]
    if not required_files:
        raise ValueError("seed-inventory.json files list is empty")
    missing_required = [item for item in required_files if not (repo_root / item).exists()]
    if missing_required:
        raise FileNotFoundError(f"missing seed files: {', '.join(missing_required)}")

    project_seed_path = seed_root / "project_seed.json"
    channels_seed_path = seed_root / "channels_seed.json"
    agents_seed_path = seed_root / "agents_seed.json"
    tasks_seed_path = seed_root / "tasks_seed.json"
    skills_manifest_path = seed_root / "skills-manifest.json"

    project_seed = _load_json(project_seed_path)
    channels_seed = _load_json(channels_seed_path)
    agents_seed = _load_json(agents_seed_path)
    tasks_seed = _load_json(tasks_seed_path)
    skills_manifest = _load_json(skills_manifest_path)

    for path, payload in (
        (project_seed_path, project_seed),
        (channels_seed_path, channels_seed),
        (agents_seed_path, agents_seed),
        (tasks_seed_path, tasks_seed),
        (skills_manifest_path, skills_manifest),
    ):
        _ensure_public_safe(path, payload)

    channels = channels_seed.get("channels") or []
    agents = agents_seed.get("agents") or []
    tasks = tasks_seed.get("tasks") or []
    skills = skills_manifest.get("skills") or []
    if not isinstance(channels, list) or not isinstance(agents, list) or not isinstance(tasks, list) or not isinstance(skills, list):
        raise ValueError("seed files must contain list fields")

    created_dirs: list[str] = []
    for rel in (selected_root_rel, runtime_root.relative_to(repo_root), runtime_sessions.relative_to(repo_root), runtime_runs.relative_to(repo_root)):
        path = repo_root / rel
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)
            created_dirs.append(str(path.relative_to(repo_root)))

    created_channel_dirs: list[str] = []
    for raw in channels:
        if not isinstance(raw, dict):
            continue
        channel_name = _slug_channel(str(raw.get("name") or ""))
        if not channel_name:
            raise ValueError("channel name cannot be empty")
        channel_root = example_root / "tasks" / channel_name
        for sub in REQUIRED_CHANNEL_DIRS:
            path = channel_root / sub
            if not path.exists():
                path.mkdir(parents=True, exist_ok=True)
                created_channel_dirs.append(str(path.relative_to(repo_root)))

    created_tasks: list[str] = []
    for raw in tasks:
        if not isinstance(raw, dict):
            continue
        rel_path = str(raw.get("path") or "").strip()
        title = str(raw.get("title") or "示例任务").strip() or "示例任务"
        channel_name = str(raw.get("channel_name") or "").strip() or "未命名通道"
        status = str(raw.get("status") or "待开始").strip() or "待开始"
        if not rel_path:
            raise ValueError("task path cannot be empty")
        task_path = (repo_root / rel_path).resolve()
        if not task_path.exists():
            task_path.parent.mkdir(parents=True, exist_ok=True)
            task_path.write_text(_task_template(title, channel_name, status), encoding="utf-8")
            created_tasks.append(str(task_path.relative_to(repo_root)))

    missing_skills: list[str] = []
    for raw in skills:
        if not isinstance(raw, dict):
            continue
        skill_path = str(raw.get("path") or "").strip()
        if not skill_path:
            raise ValueError("skills-manifest path cannot be empty")
        if not (repo_root / skill_path).exists():
            missing_skills.append(skill_path)
    if missing_skills:
        raise FileNotFoundError(f"missing skill files: {', '.join(missing_skills)}")

    channel_names = {
        _slug_channel(str(item.get("name") or ""))
        for item in channels
        if isinstance(item, dict)
    }
    agent_channels = {
        _slug_channel(str(item.get("channel_name") or ""))
        for item in agents
        if isinstance(item, dict)
    }
    missing_agent_channels = sorted(name for name in agent_channels if name and name not in channel_names)
    if missing_agent_channels:
        raise ValueError(f"agents reference unknown channels: {', '.join(missing_agent_channels)}")

    bootstrap_manifest = {
        "schema_version": "1.0",
        "public_safe": True,
        "bootstrapped_at": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime()),
        "project_id": str(project_seed.get("project", {}).get("id") or "").strip(),
        "project_name": str(project_seed.get("project", {}).get("name") or "").strip(),
        "seed_inventory": str(inventory_path.relative_to(repo_root)),
        "counts": {
            "channels": len(channel_names),
            "agents": len([item for item in agents if isinstance(item, dict)]),
            "tasks": len([item for item in tasks if isinstance(item, dict)]),
            "skills": len([item for item in skills if isinstance(item, dict)]),
        },
        "artifacts": {
            "runtime_root": str(runtime_root.relative_to(repo_root)),
            "runtime_sessions_root": str(runtime_sessions.relative_to(repo_root)),
            "runtime_runs_root": str(runtime_runs.relative_to(repo_root)),
        },
        "created": {
            "dirs": created_dirs,
            "channel_dirs": created_channel_dirs,
            "tasks": created_tasks,
        },
        "next_steps": [
            "python3 scripts/start_standard_project.py",
            "把 docs/public/ai-bootstrap.md 提供给你的 AI，并要求它按 standard_project 的默认启动批次推进",
            "python3 build_project_task_dashboard.py",
            "python3 server.py --port 18770 --static-root dist",
            "python3 scripts/activate_public_example_agents.py --project-id standard_project --base-url http://127.0.0.1:18770",
            "打开 /__health 与项目页面确认 standard_project 可见",
        ],
    }

    bootstrap_result_path = runtime_root / "bootstrap-result.json"
    bootstrap_result_path.write_text(
        json.dumps(bootstrap_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        "ok": True,
        "bootstrap_result_path": str(bootstrap_result_path),
        "project_id": bootstrap_manifest["project_id"],
        "counts": bootstrap_manifest["counts"],
        "created": bootstrap_manifest["created"],
    }
