from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


ROLE_LABELS = {
    "主负责位": "main_owner",
    "协同位": "collaborators",
    "验证位": "validators",
    "质疑位": "challengers",
    "备份位": "backup_owners",
    "管理位": "management_slot",
    "自定义责任位": "custom_roles",
}

LEGACY_ROLE_FIELDS = (
    "main_owner",
    "collaborators",
    "validators",
    "challengers",
    "backup_owners",
    "management_slot",
    "custom_roles",
)

ADDITIVE_ROLE_FIELDS = (
    "executors",
    "acceptors",
    "reviewers",
    "visual_reviewers",
)

REVIEWER_KEYWORDS = ("审核", "门禁", "用户审核", "用户验收", "评审", "审查")
VISUAL_REVIEWER_KEYWORDS = ("视觉审核", "视觉审核位", "视觉验收", "视觉验收位")

EMPTY_MARKERS = {"", "空", "无", "暂无", "待补", "待定", "未定", "无此项"}
ROLE_LINE_RE = re.compile(
    r"^\s*-\s*(主负责位|协同位|验证位|质疑位|备份位|管理位|自定义责任位)(?:（[^）]*）)?\s*[:：]\s*(.*)\s*$"
)
ROLE_HEADING_RE = re.compile(r"^\s*#{3,6}\s*(主负责位|协同位|验证位|质疑位|备份位|管理位|自定义责任位)\s*$")
FIELD_LINE_RE = re.compile(r"^\s*-\s*(名称|通道|Agent|session_id(?: / alias)?|职责)\s*[:：]\s*(.*)\s*$")
LIST_ITEM_RE = re.compile(r"^\s*(?:[-*]|\d+[.)])\s*(.+?)\s*$")
UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)


def _as_str(value: Any) -> str:
    return "" if value is None else str(value)


def _clean_value(value: Any) -> str:
    return _as_str(value).strip()


def _normalize_role_name(raw: str) -> str:
    return _clean_value(raw).replace(" ", "")


def _extract_harness_section(md: str) -> list[str]:
    lines = md.splitlines()
    start = -1
    for idx, line in enumerate(lines):
        if line.strip() == "## Harness责任位":
            start = idx + 1
            break
    if start < 0:
        return []
    out: list[str] = []
    for line in lines[start:]:
        if line.startswith("## "):
            break
        out.append(line.rstrip("\n"))
    return out


def _extract_inline_tokens(raw: str) -> list[str]:
    text = _clean_value(raw)
    if not text or text in EMPTY_MARKERS:
        return []
    tokens = [tok.strip() for tok in re.findall(r"`([^`]+)`", text) if tok.strip()]
    if tokens:
        return tokens
    if "继承项目级默认管理位" in text:
        return [text]
    parts = [part.strip() for part in re.split(r"[，,、；;]", text) if part.strip()]
    return parts or [text]


def _extract_scalar_text(raw: str) -> str:
    tokens = _extract_inline_tokens(raw)
    if tokens:
        return _clean_value(tokens[0])
    return _clean_value(raw)


def _split_session_alias(raw: str) -> tuple[str, str]:
    text = _clean_value(raw)
    if not text or text in EMPTY_MARKERS:
        return "", ""
    match = UUID_RE.search(text)
    session_id = match.group(0) if match else ""
    alias = text
    if session_id:
        alias = text.replace(session_id, " ")
    alias = re.sub(r"[／/|]+", " ", alias)
    alias = re.sub(r"\s+", " ", alias).strip()
    return session_id, alias


def _build_role_entry(
    *,
    name: str = "",
    channel_name: str = "",
    agent_name: str = "",
    session_id: str = "",
    alias: str = "",
    responsibility: str = "",
    source: str = "task_doc",
) -> dict[str, str]:
    row: dict[str, str] = {
        "channel_name": _clean_value(channel_name),
        "agent_name": _clean_value(agent_name),
        "session_id": _clean_value(session_id),
        "alias": _clean_value(alias),
        "source": _clean_value(source),
    }
    if _clean_value(name):
        row["name"] = _clean_value(name)
    if _clean_value(responsibility):
        row["responsibility"] = _clean_value(responsibility)
    return row


def _build_inline_role_entries(role_name: str, inline_value: str) -> list[dict[str, str]]:
    values = _extract_inline_tokens(inline_value)
    entries: list[dict[str, str]] = []
    for value in values:
        if _clean_value(value) in EMPTY_MARKERS:
            continue
        if role_name == "自定义责任位":
            entries.append(_build_role_entry(name=value, source="task_doc"))
            continue
        if role_name == "管理位":
            entries.append(
                _build_role_entry(
                    name=value,
                    agent_name=value,
                    alias=value,
                    source="task_override",
                )
            )
            continue
        entries.append(
            _build_role_entry(
                agent_name=value,
                alias=value,
                source="task_doc",
            )
        )
    return entries


def _parse_role_field(entry: dict[str, str], key: str, raw_value: str) -> bool:
    value = _extract_scalar_text(raw_value)
    if value in EMPTY_MARKERS:
        return False
    if key == "名称":
        entry["name"] = value
        return True
    if key == "通道":
        entry["channel_name"] = value
        return True
    if key == "Agent":
        entry["agent_name"] = value
        if not entry.get("alias"):
            entry["alias"] = value
        return True
    if key in {"session_id / alias", "session_id"}:
        session_id, alias = _split_session_alias(raw_value)
        if session_id:
            entry["session_id"] = session_id
        if alias and key == "session_id / alias":
            entry["alias"] = alias
        return bool(session_id or alias)
    if key == "职责":
        entry["responsibility"] = value
        return True
    return False


def _extract_role_item_value(raw_line: str) -> str:
    match = LIST_ITEM_RE.match(raw_line.strip())
    if not match:
        return ""
    text = _clean_value(match.group(1))
    if not text:
        return ""
    tokens = _extract_inline_tokens(text)
    if tokens:
        return _clean_value(tokens[0])
    return text


def _parse_single_role_block(role_name: str, block_lines: list[str]) -> list[dict[str, str]]:
    entry = _build_role_entry(
        name=role_name if role_name in {"管理位", "自定义责任位"} else "",
        source="task_override" if role_name == "管理位" else "task_doc",
    )
    has_data = False
    for line in block_lines:
        stripped = line.strip()
        match = FIELD_LINE_RE.match(stripped)
        if match:
            has_data = _parse_role_field(entry, match.group(1), match.group(2)) or has_data
            continue
        item_value = _extract_role_item_value(stripped)
        if not item_value or item_value in EMPTY_MARKERS:
            continue
        if role_name in {"管理位", "自定义责任位"}:
            entry["name"] = item_value
        else:
            entry["agent_name"] = item_value
            if not entry.get("alias"):
                entry["alias"] = item_value
        has_data = True
    if not has_data:
        return []
    if role_name == "管理位" and not entry.get("name"):
        entry["name"] = "管理位"
    return [entry]


def _parse_multi_agent_role_block(role_name: str, block_lines: list[str]) -> list[dict[str, str]]:
    source = "task_doc"
    entries: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for line in block_lines:
        stripped = line.strip()
        match = FIELD_LINE_RE.match(stripped)
        if match:
            if current is None:
                current = _build_role_entry(source=source)
            _parse_role_field(current, match.group(1), match.group(2))
            continue
        item_value = _extract_role_item_value(stripped)
        if not item_value or item_value in EMPTY_MARKERS:
            continue
        if current:
            entries.append(current)
        current = _build_role_entry(
            agent_name=item_value,
            alias=item_value,
            source=source,
        )
    if current:
        entries.append(current)
    return [entry for entry in entries if any(_clean_value(v) for k, v in entry.items() if k != "source")]


def _parse_multi_named_role_block(role_name: str, block_lines: list[str]) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    source = "task_override" if role_name == "管理位" else "task_doc"
    for line in block_lines:
        match = FIELD_LINE_RE.match(line.strip())
        if not match:
            continue
        key = match.group(1)
        raw_value = match.group(2)
        if _clean_value(raw_value) in EMPTY_MARKERS:
            continue
        if key == "名称":
            if current:
                entries.append(current)
            current = _build_role_entry(name=raw_value, source=source)
            continue
        if current is None:
            current = _build_role_entry(source=source)
        if key == "通道":
            current["channel_name"] = _clean_value(raw_value)
        elif key == "Agent":
            current["agent_name"] = _clean_value(raw_value)
            if not current.get("alias"):
                current["alias"] = _clean_value(raw_value)
        elif key == "session_id / alias":
            session_id, alias = _split_session_alias(raw_value)
            if session_id:
                current["session_id"] = session_id
            if alias:
                current["alias"] = alias
        elif key == "职责":
            current["responsibility"] = _clean_value(raw_value)
    if current:
        entries.append(current)
    return [entry for entry in entries if any(_clean_value(v) for k, v in entry.items() if k != "source")]


def _load_project_registry(root: Path, task_root_rel: str, project_id: str) -> dict[str, Any]:
    task_root = root / Path(task_root_rel)
    resources_dir = task_root / "全局资源"
    exact = resources_dir / f"task-harness-project-registry.{project_id}.v1.json"
    candidates = [exact]
    candidates.extend(sorted(resources_dir.glob(f"task-harness-project-registry.{project_id}.v*.json")))
    for path in candidates:
        if not path.exists() or not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(payload, dict):
            return payload
    return {}


def _inherits_management_slot(registry: dict[str, Any], has_section: bool, explicit_inherit: bool) -> bool:
    defaults = registry.get("defaults") if isinstance(registry.get("defaults"), dict) else {}
    inherit_enabled = bool(defaults.get("inherit_management_slot_to_tasks"))
    if explicit_inherit:
        return True
    if not has_section:
        return False
    return inherit_enabled


def _build_registry_management_slot(registry: dict[str, Any]) -> list[dict[str, str]]:
    management_slot = registry.get("management_slot") if isinstance(registry.get("management_slot"), dict) else {}
    members = management_slot.get("default_members") if isinstance(management_slot.get("default_members"), list) else []
    out: list[dict[str, str]] = []
    for member in members:
        if not isinstance(member, dict):
            continue
        out.append(
            _build_role_entry(
                name=_clean_value(member.get("name")),
                channel_name=_clean_value(member.get("channel_name")),
                agent_name=_clean_value(member.get("agent_alias") or member.get("agent_name")),
                session_id=_clean_value(member.get("session_id")),
                alias=_clean_value(member.get("agent_alias") or member.get("alias")),
                responsibility=_clean_value(member.get("responsibility")),
                source="project_registry",
            )
        )
    return out


def _copy_role_entry(entry: Any) -> dict[str, str]:
    if not isinstance(entry, dict):
        return {}
    return {str(key): _clean_value(value) for key, value in entry.items()}


def _copy_role_entries(entries: Any) -> list[dict[str, str]]:
    if not isinstance(entries, list):
        return []
    return [row for row in (_copy_role_entry(entry) for entry in entries) if row]


def _role_entry_search_text(entry: dict[str, str]) -> str:
    return " ".join(
        _clean_value(entry.get(key))
        for key in ("name", "responsibility", "agent_name", "alias", "channel_name")
        if _clean_value(entry.get(key))
    )


def _is_visual_reviewer(entry: dict[str, str]) -> bool:
    text = _role_entry_search_text(entry)
    return any(keyword in text for keyword in VISUAL_REVIEWER_KEYWORDS)


def _is_custom_reviewer(entry: dict[str, str]) -> bool:
    if _is_visual_reviewer(entry):
        return False
    text = _role_entry_search_text(entry)
    return any(keyword in text for keyword in REVIEWER_KEYWORDS)


def _empty_task_harness_roles() -> dict[str, Any]:
    return {
        "main_owner": None,
        "collaborators": [],
        "validators": [],
        "challengers": [],
        "backup_owners": [],
        "management_slot": [],
        "custom_roles": [],
        "executors": [],
        "acceptors": [],
        "reviewers": [],
        "visual_reviewers": [],
    }


def normalize_task_harness_roles(parsed: dict[str, Any] | None) -> dict[str, Any]:
    """
    Return the unified task role read model.

    The first seven fields are the legacy contract. The additive fields are
    projections from those same parsed roles, not a second source of truth.
    """
    source = parsed if isinstance(parsed, dict) else {}
    out = _empty_task_harness_roles()
    main_owner = source.get("main_owner")
    out["main_owner"] = _copy_role_entry(main_owner) if isinstance(main_owner, dict) else None
    for field_name in LEGACY_ROLE_FIELDS:
        if field_name == "main_owner":
            continue
        out[field_name] = _copy_role_entries(source.get(field_name))
    out["executors"] = _copy_role_entries(out["collaborators"])
    out["acceptors"] = _copy_role_entries(out["validators"])
    out["reviewers"] = _copy_role_entries(out["management_slot"])
    out["reviewers"].extend(entry for entry in _copy_role_entries(out["custom_roles"]) if _is_custom_reviewer(entry))
    out["visual_reviewers"] = [
        entry for entry in _copy_role_entries(out["custom_roles"]) if _is_visual_reviewer(entry)
    ]
    return out


def parse_task_harness(
    *,
    root: Path,
    task_root_rel: str,
    project_id: str,
    item_type: str,
    markdown: str,
) -> dict[str, Any]:
    empty = _empty_task_harness_roles()
    if _clean_value(item_type) != "任务":
        return empty

    registry = _load_project_registry(root, task_root_rel, project_id)
    section_lines = _extract_harness_section(markdown)
    if not section_lines:
        return empty

    role_blocks: dict[str, dict[str, Any]] = {}
    current_role = ""
    current_inline = ""
    current_lines: list[str] = []

    def _flush_current() -> None:
        nonlocal current_role, current_inline, current_lines
        if current_role:
            role_blocks[current_role] = {
                "inline": current_inline,
                "lines": list(current_lines),
            }
        current_role = ""
        current_inline = ""
        current_lines = []

    for raw_line in section_lines:
        stripped = raw_line.strip()
        match = ROLE_LINE_RE.match(stripped)
        if match:
            _flush_current()
            current_role = match.group(1)
            current_inline = match.group(2).strip()
            continue
        heading_match = ROLE_HEADING_RE.match(stripped)
        if heading_match:
            _flush_current()
            current_role = heading_match.group(1)
            current_inline = ""
            continue
        if current_role:
            current_lines.append(raw_line)
    _flush_current()

    out = dict(empty)
    for role_name, field_name in ROLE_LABELS.items():
        block = role_blocks.get(role_name) or {}
        inline_value = _clean_value(block.get("inline"))
        block_lines = block.get("lines") if isinstance(block.get("lines"), list) else []
        entries: list[dict[str, str]] = []
        if inline_value:
            if role_name == "管理位" and "继承项目级默认管理位" in inline_value:
                entries = []
            else:
                entries = _build_inline_role_entries(role_name, inline_value)
        elif block_lines:
            if field_name == "main_owner":
                entries = _parse_single_role_block(role_name, block_lines)
            elif role_name in {"协同位", "验证位", "质疑位", "备份位"}:
                entries = _parse_multi_agent_role_block(role_name, block_lines)
            elif role_name in {"管理位", "自定义责任位"}:
                entries = _parse_multi_named_role_block(role_name, block_lines)
        if field_name == "main_owner":
            out[field_name] = entries[0] if entries else None
        else:
            out[field_name] = entries

    explicit_management = role_blocks.get("管理位") or {}
    explicit_inline = _clean_value(explicit_management.get("inline"))
    explicit_inherit = "继承项目级默认管理位" in explicit_inline
    if not out["management_slot"] and _inherits_management_slot(registry, bool(section_lines), explicit_inherit):
        out["management_slot"] = _build_registry_management_slot(registry)

    return normalize_task_harness_roles(out)
