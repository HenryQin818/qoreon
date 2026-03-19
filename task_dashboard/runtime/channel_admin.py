from __future__ import annotations

from pathlib import Path
import shutil
from typing import Any, Callable
import re


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

    if f'name = "{channel_name}"' in config_content or f"name = '{channel_name}'" in config_content:
        raise ValueError(f"Channel '{channel_name}' already exists")

    project_block = match.group(1)
    last_channel_match = None
    for found in re.finditer(r'\[\[projects\.(?:channels|links)\]\]', project_block):
        last_channel_match = found

    if last_channel_match:
        insert_pos = match.start(1) + last_channel_match.end()
        remaining = config_content[insert_pos:]
        next_block = re.search(r"\n\s*\[\[", remaining)
        if next_block:
            insert_pos += next_block.start()
    else:
        insert_pos = match.end(1)

    new_channel = f"""

[[projects.channels]]
name = "{channel_name}"
desc = "{channel_desc or channel_name}"
"""

    new_config = config_content[:insert_pos] + new_channel + config_content[insert_pos:]
    atomic_write_text(config_path, new_config)

    task_root_match = re.search(r'task_root_rel\s*=\s*[\'"]([^\'"]+)[\'"]', project_block)
    if task_root_match:
        task_root_rel = task_root_match.group(1)
        task_root = resolve_task_root_path(repo_root=repo_root, task_root_rel=task_root_rel) / channel_name
        subdirs = ["产出物/沉淀", "任务", "已完成", "暂缓", "答复", "反馈", "讨论空间", "问题"]
        for subdir in subdirs:
            (task_root / subdir).mkdir(parents=True, exist_ok=True)

        readme_content = f"""# {channel_name}

{channel_desc or '通道说明'}

## 目录结构

- 任务/ - 任务文件
- 产出物/ - 产出物和沉淀
- 已完成/ - 已完成任务
- 暂缓/ - 暂缓任务
- 答复/ - 答复文件
- 反馈/ - 反馈文件
- 讨论空间/ - 讨论文档
- 问题/ - 问题记录
- 需求/ - 可选需求暂存与梳理（按需启用）
"""
        (task_root / "README.md").write_text(readme_content, encoding="utf-8")
        (task_root / "沟通-收件箱.md").write_text("", encoding="utf-8")

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
    - Runtime run history under .runtime/.runs is intentionally kept.
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

    return {
        "ok": True,
        "old_path": task_path,
        "new_path": new_rel_path,
        "old_filename": old_filename,
        "new_filename": new_filename,
        "old_status": old_status,
        "new_status": new_status,
    }
