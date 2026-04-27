from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable

from .model import Item
from .task_identity import extract_task_identity_from_markdown, strip_markdown_front_matter
from .task_harness import parse_task_harness
from .utils import file_mtime_iso, is_channel_dir_name, norm_relpath, safe_read_text


RE_LEADING_TAGS = re.compile(r"^(?P<tags>(?:【[^】]+】)+)(?P<rest>.*)$")
RE_HEADING = re.compile(r"^#\s+(.*)\s*$")


def parse_leading_tags(filename: str) -> tuple[list[str], str]:
    m = RE_LEADING_TAGS.match(filename)
    if not m:
        return [], filename
    tags = re.findall(r"【([^】]+)】", m.group("tags"))
    rest = m.group("rest")
    return tags, rest


def guess_type_from_name(rest: str) -> str:
    if rest.startswith("需求-") or rest.startswith("需求"):
        return "需求"
    if rest.startswith("讨论-") or rest.startswith("讨论"):
        return "讨论"
    if rest.startswith("模板-"):
        return "模板"
    return ""


def guess_type_from_relpath(relpath: str) -> str:
    if "/需求/" in relpath:
        return "需求"
    if "/产出物/沉淀/" in relpath:
        return "沉淀"
    if "/产出物/材料/" in relpath:
        return "材料"
    if "/产出物/证据/" in relpath:
        return "证据"
    if "/讨论空间/" in relpath:
        return "讨论"
    return ""


def is_channel_knowledge_path(relpath: str) -> bool:
    return (
        "/产出物/沉淀/" in relpath
        or "/产出物/材料/" in relpath
        or "/产出物/证据/" in relpath
    )


def extract_heading_title(md: str) -> str:
    body = strip_markdown_front_matter(md)
    for line in body.splitlines():
        m = RE_HEADING.match(line)
        if m:
            return m.group(1).strip()
    return ""


def extract_field(md: str, field_name: str) -> str:
    body = strip_markdown_front_matter(md)
    lines = body.splitlines()
    header = f"## {field_name}".strip()
    for i, line in enumerate(lines):
        if line.strip() == header:
            for j in range(i + 1, min(i + 40, len(lines))):
                v = lines[j].strip()
                if not v:
                    continue
                if v.startswith("#"):
                    break
                v = re.sub(r"^[\-\*\u2022]\s+", "", v)
                return v[:200]
    inline = re.search(rf"{re.escape(field_name)}\s*[:：]\s*(.+)", body)
    if inline:
        return inline.group(1).strip()[:200]
    return ""


def extract_excerpt(md: str, max_lines: int = 26, max_chars: int = 1600) -> str:
    body = strip_markdown_front_matter(md)
    out: list[str] = []
    for line in body.splitlines():
        s = line.rstrip()
        if not s:
            continue
        if s.startswith("```"):
            continue
        out.append(s)
        if len(out) >= max_lines:
            break
    excerpt = "\n".join(out).strip()
    if len(excerpt) > max_chars:
        excerpt = excerpt[: max_chars - 1] + "…"
    return excerpt


def excerpt_limits_for_type(item_type: str) -> tuple[int, int]:
    typ = str(item_type or "").strip()
    if typ == "任务":
        return 26, 1200
    if typ == "需求":
        return 20, 900
    if typ in {"反馈", "答复", "问题"}:
        return 14, 520
    if typ in {"沉淀", "材料", "证据", "讨论"}:
        return 10, 260
    return 12, 420


def should_include_md(relpath: str, filename: str, tags: list[str], inferred_type: str) -> bool:
    if "/node_modules/" in relpath or "/.git/" in relpath:
        return False
    if inferred_type == "模板":
        return False
    if filename.startswith("README"):
        return False
    if is_channel_knowledge_path(relpath):
        return True
    if tags:
        if len(tags) >= 2 and tags[1] in {"任务", "反馈", "答复", "问题", "需求"}:
            return True
        if len(tags) == 1 and inferred_type in {"讨论", "需求"}:
            return True
        return False
    if "/讨论空间/" in relpath and inferred_type == "讨论":
        return True
    if "/需求/" in relpath and inferred_type == "需求":
        return True
    return False


def iter_items(
    *,
    root: Path,
    project_id: str,
    project_name: str,
    task_root_rel: str,
    exclude_rel_prefixes: Iterable[str] = (),
) -> list[Item]:
    task_root = root / task_root_rel
    if not task_root.exists():
        return []

    items: list[Item] = []
    symlink_dir_names: set[str] = set()
    try:
        for child in task_root.iterdir():
            if child.is_symlink() and child.is_dir():
                symlink_dir_names.add(child.name)
    except Exception:
        pass
    seen_real_files: set[Path] = set()

    for p in task_root.rglob("*.md"):
        try:
            rel_to_task = p.relative_to(task_root)
            if rel_to_task.parts and rel_to_task.parts[0] in symlink_dir_names:
                continue
            if rel_to_task.parts and not is_channel_dir_name(rel_to_task.parts[0]):
                continue
        except Exception:
            pass
        try:
            rp = p.resolve()
            if rp in seen_real_files:
                continue
            seen_real_files.add(rp)
        except Exception:
            pass

        rel = norm_relpath(root, p)
        if any(rel.startswith(prefix) for prefix in exclude_rel_prefixes):
            continue

        fn = p.name
        tags, rest = parse_leading_tags(fn.replace(".md", ""))
        inferred_type = guess_type_from_name(rest) or guess_type_from_relpath(rel)
        if not should_include_md(rel, fn, tags, inferred_type):
            continue

        status = tags[0] if len(tags) >= 1 else ""
        typ = tags[1] if len(tags) >= 2 else (inferred_type or "文档")
        extra_tags = tags[2:] if len(tags) > 2 else []
        code = rest.split("-", 1)[0].strip() if "-" in rest else ""
        title_from_name = rest.strip()

        md = safe_read_text(p)
        identity = extract_task_identity_from_markdown(md)
        body_md = strip_markdown_front_matter(md)
        title_from_h1 = extract_heading_title(body_md)
        title = title_from_h1 or title_from_name

        owner = extract_field(body_md, "负责人")
        due = extract_field(body_md, "截止日期") or extract_field(body_md, "截止")
        task_harness = parse_task_harness(
            root=root,
            task_root_rel=task_root_rel,
            project_id=project_id,
            item_type=typ,
            markdown=body_md,
        )

        ex_lines, ex_chars = excerpt_limits_for_type(typ)
        excerpt = extract_excerpt(body_md, max_lines=ex_lines, max_chars=ex_chars)

        channel = "未归类"
        try:
            rel_to_task = p.relative_to(task_root)
            channel = rel_to_task.parts[0] if len(rel_to_task.parts) >= 2 else "未归类"
        except Exception:
            # fallback: best-effort
            parts = rel.strip("/").split("/")
            channel = parts[-2] if len(parts) >= 2 else "未归类"

        items.append(
            Item(
                project_id=project_id,
                project_name=project_name,
                channel=channel,
                status=status or "未知",
                type=typ,
                title=title,
                code=code,
                path=rel,
                task_id=str(identity.get("task_id") or "").strip(),
                parent_task_id=str(identity.get("parent_task_id") or "").strip(),
                created_at=str(identity.get("created_at") or "").strip(),
                updated_at=file_mtime_iso(p),
                owner=owner,
                due=due,
                excerpt=excerpt,
                tags=extra_tags,
                main_owner=task_harness.get("main_owner"),
                collaborators=task_harness.get("collaborators") or [],
                validators=task_harness.get("validators") or [],
                challengers=task_harness.get("challengers") or [],
                backup_owners=task_harness.get("backup_owners") or [],
                management_slot=task_harness.get("management_slot") or [],
                custom_roles=task_harness.get("custom_roles") or [],
                executors=task_harness.get("executors") or [],
                acceptors=task_harness.get("acceptors") or [],
                reviewers=task_harness.get("reviewers") or [],
                visual_reviewers=task_harness.get("visual_reviewers") or [],
            )
        )

    items.sort(key=lambda x: (x.project_id, x.channel, x.status, x.type, x.title))
    return items
