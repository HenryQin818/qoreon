from __future__ import annotations

from pathlib import Path
import shutil
from typing import Any, Callable
import re

from task_dashboard.task_identity import (
    extract_task_identity_from_file,
    record_task_move,
)


STATUS_DIR_MAP = {
    "待开始": "任务",
    "待处理": "任务",
    "进行中": "任务",
    "已完成": "已完成",
    "已验收通过": "已完成",
    "暂缓": "暂缓",
    "答复": "答复",
    "反馈": "反馈",
}

_DEFAULT_CHANNEL_SCAFFOLD_SUBDIRS = [
    "任务",
    "问题",
    "产出物/材料",
    "产出物/沉淀",
    "已完成",
    "暂缓",
]
_DEFAULT_CHANNEL_MARKER_FILES = {
    "已完成/目录.md": "# 已完成目录\n\n用于归档本分工下已完成且完成收口的任务文档。\n",
    "产出物/沉淀/目录.md": "# 沉淀目录\n\n用于沉淀可复用的方法、规范、结论与经验。\n",
}

_PROJECT_CHILD_SECTION_RE = re.compile(
    r"(?m)^(?P<header>\[\[projects\.(?P<array_kind>[^\]]+)\]\]|\[projects\.(?P<table_kind>[^\]]+)\])\s*$"
)


def resolve_task_root_path(*, repo_root: Path, task_root_rel: str) -> Path:
    """Resolve task_root_rel against repo_root, tolerating repo-prefixed config values."""
    root = Path(repo_root).resolve()
    raw_rel = str(task_root_rel or "").strip()
    if not raw_rel:
        return root
    rel_path = Path(raw_rel)
    if rel_path.is_absolute():
        return rel_path.resolve()

    norm_rel = raw_rel.replace("\\", "/").strip("/")
    marker = f"{root.name}/"
    idx = norm_rel.find(marker)
    if idx >= 0:
        tail = norm_rel[idx + len(marker):].strip("/")
        return (root / tail).resolve() if tail else root
    return (root / rel_path).resolve()


def _iter_project_child_sections(project_block: str) -> list[dict[str, Any]]:
    matches = list(_PROJECT_CHILD_SECTION_RE.finditer(project_block))
    sections: list[dict[str, Any]] = []
    for idx, found in enumerate(matches):
        start = found.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(project_block)
        header = str(found.group("header") or "").strip()
        sections.append(
            {
                "header": header,
                "array_kind": str(found.group("array_kind") or "").strip(),
                "table_kind": str(found.group("table_kind") or "").strip(),
                "start": start,
                "end": end,
                "block": project_block[start:end],
            }
        )
    return sections


def create_channel(
    *,
    project_id: str,
    channel_name: str,
    channel_desc: str,
    cli_type: str,
    config_path: Path,
    repo_root: Path,
    atomic_write_text: Callable[[Path, str], None],
) -> dict[str, Any]:
    """
    Create a new channel for a project:
    1. Update config with new channel configuration
    2. Create channel directory structure
    """
    if not config_path.exists():
        raise ValueError("config.toml not found")

    config_content = config_path.read_text(encoding="utf-8")

    project_pattern = (
        rf'(\[\[projects\]\]\s*\nid\s*=\s*[\'"]?{re.escape(project_id)}[\'"]?\s*'
        rf'(?:.*?\n)*?)(?=\[\[projects\]\]|\Z)'
    )
    match = re.search(project_pattern, config_content, re.DOTALL)
    if not match:
        raise ValueError(f"Project '{project_id}' not found in config.toml")

    project_block = match.group(1)
    child_sections = _iter_project_child_sections(project_block)

    for section in child_sections:
        if section["header"] != "[[projects.channels]]":
            continue
        block = str(section["block"] or "")
        name_match = re.search(r'(?m)^\s*name\s*=\s*[\'"]([^\'"]+)[\'"]\s*$', block)
        block_name = str(name_match.group(1) or "").strip() if name_match else ""
        if block_name == channel_name:
            raise ValueError(f"Channel '{channel_name}' already exists")

    channel_sections = [row for row in child_sections if row["header"] == "[[projects.channels]]"]
    link_sections = [row for row in child_sections if row["header"] == "[[projects.links]]"]
    if channel_sections:
        insert_rel = int(channel_sections[-1]["end"])
    elif link_sections:
        insert_rel = int(link_sections[-1]["end"])
    elif child_sections:
        insert_rel = int(child_sections[0]["start"])
    else:
        insert_rel = len(project_block)
    insert_pos = match.start(1) + insert_rel

    new_channel_lines = [
        "[[projects.channels]]",
        f'name = "{channel_name}"',
        f'desc = "{channel_desc or channel_name}"',
        f'cli_type = "{str(cli_type or "codex").strip() or "codex"}"',
        "",
    ]
    prefix = "" if insert_pos <= 0 or config_content[:insert_pos].endswith("\n\n") else "\n"
    new_channel = prefix + "\n".join(new_channel_lines)

    new_config = config_content[:insert_pos] + new_channel + config_content[insert_pos:]
    atomic_write_text(config_path, new_config)

    task_root_match = re.search(r'task_root_rel\s*=\s*[\'"]([^\'"]+)[\'"]', project_block)
    if task_root_match:
        task_root_rel = task_root_match.group(1)
        task_root = resolve_task_root_path(repo_root=repo_root, task_root_rel=task_root_rel) / channel_name
        for subdir in _DEFAULT_CHANNEL_SCAFFOLD_SUBDIRS:
            (task_root / subdir).mkdir(parents=True, exist_ok=True)
        for rel_path, content in _DEFAULT_CHANNEL_MARKER_FILES.items():
            marker_file = task_root / rel_path
            if not marker_file.exists():
                marker_file.write_text(content, encoding="utf-8")

        readme_content = f"""# {channel_name}

{channel_desc or '通道说明'}

## 目录结构

- 任务/ - 任务文件
- 问题/ - 问题记录
- 产出物/材料/ - 材料与交付件
- 产出物/沉淀/ - 可复用沉淀
- 已完成/ - 已完成任务
- 暂缓/ - 暂缓任务
"""
        (task_root / "README.md").write_text(readme_content, encoding="utf-8")

    return {
        "ok": True,
        "name": channel_name,
        "desc": channel_desc,
        "cli_type": cli_type,
    }


def delete_channel(
    *,
    project_id: str,
    channel_name: str,
    config_path: Path,
    repo_root: Path,
    task_root_rel: str,
    atomic_write_text: Callable[[Path, str], None],
) -> dict[str, Any]:
    """
    Delete one channel's config entry and task directory.

    Notes:
    - Only the channel directory under task_root_rel is removed.
    - Runtime history records are intentionally kept.
    """
    if not config_path.exists():
        raise ValueError("config.toml not found")

    config_content = config_path.read_text(encoding="utf-8")
    project_pattern = (
        rf'(\[\[projects\]\]\s*\nid\s*=\s*[\'"]?{re.escape(project_id)}[\'"]?\s*'
        rf'(?:.*?\n)*?)(?=\[\[projects\]\]|\Z)'
    )
    match = re.search(project_pattern, config_content, re.DOTALL)
    if not match:
        raise ValueError(f"Project '{project_id}' not found in config.toml")

    project_block = match.group(1)
    section_pattern = re.compile(r"(?m)^\[\[projects\.(channels|links)\]\]\s*$")
    section_matches = list(section_pattern.finditer(project_block))
    removed_from_config = False

    if section_matches:
        prefix = project_block[: section_matches[0].start()]
        kept_sections: list[str] = []
        for idx, found in enumerate(section_matches):
            start = found.start()
            end = section_matches[idx + 1].start() if idx + 1 < len(section_matches) else len(project_block)
            block = project_block[start:end]
            section_kind = str(found.group(1) or "").strip()
            if section_kind == "channels":
                name_match = re.search(r'(?m)^\s*name\s*=\s*[\'"]([^\'"]+)[\'"]\s*$', block)
                block_name = str(name_match.group(1) or "").strip() if name_match else ""
                if block_name == channel_name:
                    removed_from_config = True
                    continue
            kept_sections.append(block)
        if removed_from_config:
            updated_project_block = prefix + "".join(kept_sections)
            new_config = config_content[: match.start(1)] + updated_project_block + config_content[match.end(1):]
            atomic_write_text(config_path, new_config)

    task_root = resolve_task_root_path(repo_root=repo_root, task_root_rel=task_root_rel)
    channel_root = (task_root / channel_name).resolve()
    root_deleted = False
    if channel_root.exists():
        shutil.rmtree(channel_root)
        root_deleted = True

    return {
        "ok": True,
        "project_id": project_id,
        "channel_name": channel_name,
        "removed_from_config": removed_from_config,
        "channel_root_path": str(channel_root),
        "channel_root_deleted": root_deleted,
        "kept_runtime_runs": True,
    }


def change_task_status(*, task_path: str, new_status: str, repo_root: Path) -> dict[str, Any]:
    """
    Change task status by:
    1. Modifying the status tag in filename
    2. Moving file to corresponding directory based on status
    """
    file_path = repo_root / task_path
    if not file_path.exists():
        raise ValueError(f"Task file not found: {task_path}")

    if new_status not in STATUS_DIR_MAP:
        raise ValueError(f"Invalid status: {new_status}")

    old_filename = file_path.name
    stem = old_filename.rsplit(".md", 1)[0] if old_filename.endswith(".md") else old_filename

    tag_pattern = r"^(【[^】]+】)+"
    tag_match = re.match(tag_pattern, stem)
    if tag_match:
        tags = re.findall(r"【([^】]+)】", tag_match.group(0))
        rest = stem[tag_match.end():]
        old_status = tags[0] if tags else ""
        if tags:
            tags[0] = new_status
        else:
            tags = [new_status]
    else:
        old_status = ""
        tags = [new_status, "任务"]
        rest = stem

    new_tags_str = "".join(f"【{tag}】" for tag in tags)
    new_filename = f"{new_tags_str}{rest}.md"

    target_subdir = STATUS_DIR_MAP[new_status]
    current_dir = file_path.parent
    channel_dir = current_dir.parent

    if current_dir.name in ["任务", "已完成", "暂缓", "答复", "反馈", "讨论空间", "问题", "产出物"]:
        target_dir = channel_dir / target_subdir
    else:
        target_dir = current_dir

    target_dir.mkdir(parents=True, exist_ok=True)
    new_file_path = target_dir / new_filename
    file_path.rename(new_file_path)
    new_rel_path = str(new_file_path.relative_to(repo_root))
    identity = extract_task_identity_from_file(new_file_path)

    try:
        from task_dashboard.runtime.heartbeat_registry import _resolve_task_project_channel

        project_id, _, _ = _resolve_task_project_channel(new_rel_path)
    except Exception:
        project_id = ""
    record_task_move(
        repo_root=repo_root,
        project_id=project_id,
        old_path=task_path,
        new_path=new_rel_path,
        task_id=identity.get("task_id") or "",
        parent_task_id=identity.get("parent_task_id") or "",
    )

    return {
        "ok": True,
        "old_path": task_path,
        "new_path": new_rel_path,
        "task_id": str(identity.get("task_id") or "").strip(),
        "parent_task_id": str(identity.get("parent_task_id") or "").strip(),
        "old_filename": old_filename,
        "new_filename": new_filename,
        "old_status": old_status,
        "new_status": new_status,
    }
