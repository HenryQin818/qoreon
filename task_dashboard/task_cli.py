from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import load_dashboard_config
from .helpers import atomic_write_text, now_iso
from .parser_md import extract_heading_title, iter_items, parse_leading_tags
from .runtime.channel_admin import resolve_task_root_path
from .session_store import SessionStore, session_binding_sort_key
from .sessions import channel_session_map, parse_session_json
from .task_harness import parse_task_harness
from .task_identity import generate_task_id, render_task_front_matter, strip_markdown_front_matter
from .utils import repo_root_from_here, safe_read_text


STAGE_ALIASES = {
    "draft": "draft",
    "草稿": "draft",
    "review": "review",
    "评审": "review",
    "dispatch": "dispatch",
    "派发": "dispatch",
    "in_progress": "dispatch",
    "进行中": "dispatch",
    "acceptance": "acceptance",
    "验收": "acceptance",
    "done": "done",
    "complete": "done",
    "completed": "done",
    "完成": "done",
}

STAGE_STATUS = {
    "draft": "待开始",
    "review": "待开始",
    "dispatch": "进行中",
    "acceptance": "待验收",
    "done": "已完成",
}

ACTIVE_STATUSES = {"待开始", "待处理", "进行中", "待验收"}
INACTIVE_STATUSES = {"已完成", "已验收通过", "暂缓", "已暂停"}
PAGE_EXPERIENCE_KEYWORDS = ("页面", "界面", "UI", "前端", "布局", "视觉", "信息密度", "可读性", "交互", "样式")
ROLE_PAYLOAD_KEYS = {
    "owner": ("owner", "mainOwner", "main_owner"),
    "executor": ("executor", "executors", "collaborator", "collaborators"),
    "validator": ("validator", "validators", "acceptor", "acceptors"),
    "reviewer": ("reviewer", "reviewers", "managementSlot", "management_slot"),
    "visual_reviewer": ("visualReviewer", "visual_reviewer", "visualReviewers", "visual_reviewers"),
}


def _as_str(value: Any) -> str:
    return "" if value is None else str(value)


def _normalize_stage(value: Any) -> str:
    text = _as_str(value).strip().lower().replace("-", "_").replace(" ", "_")
    return STAGE_ALIASES.get(text, STAGE_ALIASES.get(_as_str(value).strip(), "draft"))


def _coerce_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = _as_str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _resolve_config_path(root: Path, raw: str) -> Path:
    text = _as_str(raw).strip()
    if not text:
        return root
    path = Path(text)
    if path.is_absolute():
        return path.resolve()
    norm = text.replace("\\", "/").strip("/")
    marker = f"{root.name}/"
    idx = norm.find(marker)
    if idx >= 0:
        tail = norm[idx + len(marker) :].strip("/")
        return (root / tail).resolve() if tail else root
    return (root / path).resolve()


def _load_config(root: Path) -> dict[str, Any]:
    try:
        return load_dashboard_config(root)
    except Exception:
        return {}


def _project_cfg(root: Path, project_id: str) -> dict[str, Any]:
    cfg = _load_config(root)
    projects = cfg.get("projects") if isinstance(cfg.get("projects"), list) else []
    for project in projects:
        if isinstance(project, dict) and _as_str(project.get("id")).strip() == project_id:
            return project
    return {"id": project_id, "name": project_id, "task_root_rel": "任务规划"}


def _task_root(root: Path, project: dict[str, Any]) -> Path:
    task_root_rel = _as_str(project.get("task_root_rel")).strip() or "任务规划"
    return resolve_task_root_path(repo_root=root, task_root_rel=task_root_rel)


def _task_root_rel(root: Path, task_root: Path) -> str:
    try:
        return str(task_root.resolve().relative_to(root.resolve()))
    except Exception:
        return _as_str(task_root)


def _session_store_base_dirs(root: Path, project: dict[str, Any]) -> list[Path]:
    out: list[Path] = []

    def add(path: Path) -> None:
        try:
            resolved = path.expanduser().resolve()
        except Exception:
            resolved = path.expanduser()
        if resolved not in out:
            out.append(resolved)

    execution_context = project.get("execution_context") if isinstance(project.get("execution_context"), dict) else {}
    sessions_root = _as_str(execution_context.get("sessions_root")).strip()
    if sessions_root:
        sessions_path = Path(sessions_root).expanduser()
        add(sessions_path.parent if sessions_path.name == ".sessions" else sessions_path)
    runtime_root = _as_str(execution_context.get("runtime_root")).strip()
    if runtime_root:
        add(Path(runtime_root).expanduser())
    runtime_root_rel = _as_str(project.get("runtime_root_rel")).strip()
    if runtime_root_rel:
        add(_resolve_config_path(root, runtime_root_rel))
    add(root / ".runtime" / "stable")
    add(root)
    return out


def _load_session_rows(root: Path, project: dict[str, Any], project_id: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for base_dir in _session_store_base_dirs(root, project):
        store = SessionStore(base_dir)
        for row in store.list_sessions(project_id):
            sid = _as_str(row.get("id") or row.get("session_id")).strip()
            channel_name = _as_str(row.get("channel_name")).strip()
            key = (sid, channel_name)
            if key in seen:
                continue
            seen.add(key)
            rows.append(dict(row))

    session_json_rel = _as_str(project.get("session_json_rel")).strip()
    if session_json_rel:
        legacy_map = channel_session_map(parse_session_json(_resolve_config_path(root, session_json_rel)))
        for channel_name, row in legacy_map.items():
            sid = _as_str(row.get("session_id")).strip()
            key = (sid, channel_name)
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                {
                    "id": sid,
                    "channel_name": channel_name,
                    "alias": _as_str(row.get("alias")).strip(),
                    "agent_name": _as_str(row.get("alias") or row.get("name")).strip(),
                    "is_primary": True,
                    "source": "session_json",
                }
            )
    return rows


def _agent_match_values(row: dict[str, Any]) -> set[str]:
    values = {
        _as_str(row.get("agent_name")).strip(),
        _as_str(row.get("alias")).strip(),
        _as_str(row.get("display_name")).strip(),
        _as_str(row.get("channel_name")).strip(),
        _as_str(row.get("name")).strip(),
    }
    return {value for value in values if value}


def _resolve_agent(
    *,
    root: Path,
    project: dict[str, Any],
    project_id: str,
    agent_name: str,
    channel_name: str = "",
    session_id: str = "",
    alias: str = "",
) -> dict[str, str]:
    raw_agent = _as_str(agent_name).strip()
    raw_channel = _as_str(channel_name).strip()
    raw_session = _as_str(session_id).strip()
    raw_alias = _as_str(alias).strip()
    if raw_session and raw_channel:
        return {
            "agent_name": raw_agent or raw_alias,
            "channel_name": raw_channel,
            "session_id": raw_session,
            "alias": raw_alias or raw_agent,
        }
    rows = _load_session_rows(root, project, project_id)
    matches: list[dict[str, Any]] = []
    for row in rows:
        if raw_session and _as_str(row.get("id") or row.get("session_id")).strip() != raw_session:
            continue
        if raw_channel and _as_str(row.get("channel_name")).strip() != raw_channel:
            continue
        if raw_agent and raw_agent not in _agent_match_values(row):
            continue
        matches.append(row)
    matches.sort(key=session_binding_sort_key, reverse=True)
    if matches:
        picked = matches[0]
        picked_alias = _as_str(picked.get("alias") or picked.get("display_name")).strip()
        picked_agent = _as_str(picked.get("agent_name") or picked_alias or raw_agent).strip()
        return {
            "agent_name": raw_agent or picked_agent,
            "channel_name": _as_str(picked.get("channel_name") or raw_channel).strip(),
            "session_id": _as_str(picked.get("id") or picked.get("session_id") or raw_session).strip(),
            "alias": raw_alias or picked_alias or picked_agent or raw_agent,
        }
    return {
        "agent_name": raw_agent or raw_alias,
        "channel_name": raw_channel,
        "session_id": raw_session,
        "alias": raw_alias or raw_agent,
    }


def _role_entry_lines(index: int | None, role: dict[str, str], responsibility: str) -> list[str]:
    prefix = f"{index}. " if index is not None else "- "
    agent_name = _as_str(role.get("agent_name") or role.get("alias") or role.get("name")).strip()
    lines = [f"{prefix}`{agent_name}`"]
    channel_name = _as_str(role.get("channel_name")).strip()
    session_id = _as_str(role.get("session_id")).strip()
    alias = _as_str(role.get("alias")).strip()
    if channel_name:
        lines.append(f"- 通道：`{channel_name}`")
    if agent_name:
        lines.append(f"- Agent：`{agent_name}`")
    if session_id or alias:
        value = session_id if not alias or alias == agent_name else f"{session_id} / {alias}".strip(" /")
        lines.append(f"- session_id / alias：`{value}`")
    if responsibility:
        lines.append(f"- 职责：{responsibility}")
    return lines


def _custom_role_lines(index: int, name: str, role: dict[str, str], responsibility: str) -> list[str]:
    lines = [f"{index}. `{name}`"]
    lines.append(f"- 名称：`{name}`")
    channel_name = _as_str(role.get("channel_name")).strip()
    agent_name = _as_str(role.get("agent_name") or role.get("alias")).strip()
    session_id = _as_str(role.get("session_id")).strip()
    alias = _as_str(role.get("alias")).strip()
    if channel_name:
        lines.append(f"- 通道：`{channel_name}`")
    if agent_name:
        lines.append(f"- Agent：`{agent_name}`")
    if session_id or alias:
        value = session_id if not alias or alias == agent_name else f"{session_id} / {alias}".strip(" /")
        lines.append(f"- session_id / alias：`{value}`")
    lines.append(f"- 职责：{responsibility}")
    return lines


def _render_harness_roles(
    *,
    owner: dict[str, str],
    executor: dict[str, str] | None,
    validator: dict[str, str] | None,
    reviewer: dict[str, str] | None,
    visual_reviewer: dict[str, str] | None,
) -> str:
    out: list[str] = ["## Harness责任位", "### 主负责位"]
    out.extend(_role_entry_lines(None, owner, "推动任务、编排协作、回收回执并完成最终收口。"))
    out.append("")
    out.append("### 协同位")
    if executor and (executor.get("agent_name") or executor.get("alias")):
        out.extend(_role_entry_lines(1, executor, "执行位：实际实现、修复或产出交付。"))
    else:
        out.append("- 空")
    out.append("")
    out.append("### 验证位")
    if validator and (validator.get("agent_name") or validator.get("alias")):
        out.extend(_role_entry_lines(1, validator, "验收位：按冻结口径给出通过或不通过裁决并提供证据。"))
    else:
        out.append("- 空")
    out.append("")
    out.append("- 质疑位：空")
    out.append("- 备份位：空")
    out.append("")
    if reviewer and (reviewer.get("agent_name") or reviewer.get("alias")):
        out.append("### 管理位")
        out.extend(_custom_role_lines(1, "审核或门禁位", reviewer, "管理审核、边界复核和阶段门禁。"))
    else:
        out.append("- 管理位：继承项目级默认管理位")
    out.append("")
    if visual_reviewer and (visual_reviewer.get("agent_name") or visual_reviewer.get("alias")):
        out.append("### 自定义责任位")
        out.extend(_custom_role_lines(1, "视觉审核位", visual_reviewer, "页面布局、信息密度、视觉一致性与极限数据可读性审核。"))
    else:
        out.append("- 自定义责任位：空")
    return "\n".join(out).rstrip() + "\n"


def _slug_title(title: str) -> str:
    text = re.sub(r"^【[^】]+】+", "", _as_str(title)).strip()
    text = re.sub(r"[\\/:*?\"<>|#\[\]\n\r\t]+", "-", text)
    text = re.sub(r"\s+", "-", text).strip(" .-")
    return (text or "未命名任务")[:96]


def _default_task_path(task_root: Path, channel_name: str, status: str, title: str) -> Path:
    channel = _as_str(channel_name).strip() or "未归类"
    subdir = "已完成" if status == "已完成" else "任务"
    date_prefix = now_iso()[:10].replace("-", "")
    return task_root / channel / subdir / f"【{status}】【任务】{date_prefix}-{_slug_title(title)}.md"


def _render_task_markdown(
    *,
    project_id: str,
    task_id: str,
    parent_task_id: str,
    title: str,
    stage: str,
    status: str,
    kind: str,
    owner: dict[str, str],
    executor: dict[str, str] | None,
    validator: dict[str, str] | None,
    reviewer: dict[str, str] | None,
    visual_reviewer: dict[str, str] | None,
) -> str:
    heading = f"# 【{status}】【任务】{now_iso()[:10].replace('-', '')}-{title.strip()}"
    front_matter = render_task_front_matter(
        task_id=task_id,
        parent_task_id=parent_task_id,
        extra_fields={
            "status_gate": stage,
            "delivery_state": "active" if status != "已完成" else "done",
        },
    )
    harness = _render_harness_roles(
        owner=owner,
        executor=executor,
        validator=validator,
        reviewer=reviewer,
        visual_reviewer=visual_reviewer,
    )
    return (
        front_matter
        + heading
        + "\n\n"
        + f"## 当前项目\n{project_id}\n\n"
        + f"## 任务类型\n{kind}\n\n"
        + "## 闭环方式\n任务文件收口块 + 正式协作消息 + run 证据\n\n"
        + harness
        + "\n## 任务目标\n"
        + f"- {title.strip()}\n\n"
        + "## 当前结论\n待推进。\n\n"
        + "## 唯一阻塞\n无。\n\n"
        + "## 关键路径\n待补。\n\n"
        + "## 下一步动作\n按当前阶段门禁补齐协作与证据。\n\n"
        + "## Announce草稿\n"
        + "- 未正式发送；拿到 `announce_run_id` 后才可写入已派发/已送达。\n"
    )


@dataclass
class ValidationResult:
    path: str
    stage: str
    strict: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    gaps: list[dict[str, str]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def _role_has_identity(role: dict[str, str] | None, *, require_session: bool = False) -> bool:
    row = role if isinstance(role, dict) else {}
    has_agent = bool(_as_str(row.get("agent_name") or row.get("alias") or row.get("name")).strip())
    if not has_agent:
        return False
    if require_session and not _as_str(row.get("session_id")).strip():
        return False
    return True


def _any_role_has_identity(rows: list[dict[str, str]], *, require_session: bool = False) -> bool:
    return any(_role_has_identity(row, require_session=require_session) for row in rows)


def _add_gap(
    result: ValidationResult,
    *,
    code: str,
    gap_type: str,
    group: str,
    role_label: str,
    severity: str,
    message: str,
) -> None:
    row = {
        "code": code,
        "type": gap_type,
        "group": group,
        "role_label": role_label,
        "severity": severity,
        "message": message,
    }
    result.gaps.append(row)
    if severity == "error":
        result.errors.append(message)
    else:
        result.warnings.append(message)


def _contains_announce_run_id(markdown: str) -> bool:
    return bool(re.search(r"\bannounce_run_id\s*=\s*[0-9]{8}-[0-9]{6}-[0-9a-fA-F]{8}\b", markdown))


def _contains_path_or_evidence(markdown: str) -> bool:
    text = str(markdown or "")
    if re.search(r"\brun_id\s*[=:]|announce_run_id\s*=|任务规划/|docs/|artifacts/|\.runtime/|https?://", text):
        return True
    evidence_labels = ("证据", "检查证据", "验收证据", "报告路径", "live 检查", "live检查")
    empty_markers = ("待补", "暂无", "无", "未提供")
    for line in text.splitlines():
        if not any(label in line for label in evidence_labels):
            continue
        if any(marker in line for marker in empty_markers):
            continue
        if "/" in line or "live" in line.lower() or "报告" in line:
            return True
    return False


def _contains_review_input(markdown: str) -> bool:
    text = str(markdown or "")
    return bool(re.search(r"(方案|需求|输入|评审对象).*(任务规划/|docs/|\.md|REQ-)", text, re.S))


def _has_visual_reviewer(harness: dict[str, Any], markdown: str) -> bool:
    custom_roles = harness.get("custom_roles") if isinstance(harness.get("custom_roles"), list) else []
    for row in custom_roles:
        text = " ".join(_as_str(value) for value in row.values())
        if "视觉审核" in text:
            return True
    return "不启用视觉审核位" in markdown or "无需视觉审核" in markdown


def _status_from_path(path: Path) -> str:
    tags, _rest = parse_leading_tags(path.name.replace(".md", ""))
    return tags[0] if tags else ""


def _infer_stage_from_status(status: str) -> str:
    if status in {"进行中"}:
        return "dispatch"
    if status in {"待验收"}:
        return "acceptance"
    if status in {"已完成", "已验收通过"}:
        return "done"
    return "draft"


def validate_markdown(
    *,
    root: Path,
    project_id: str,
    task_root_rel: str,
    path_label: str,
    markdown: str,
    stage: str,
    strict: bool,
) -> ValidationResult:
    body = strip_markdown_front_matter(markdown)
    harness = parse_task_harness(
        root=root,
        task_root_rel=task_root_rel,
        project_id=project_id,
        item_type="任务",
        markdown=body,
    )
    result = ValidationResult(path=path_label, stage=stage, strict=strict)
    title = extract_heading_title(body)
    if stage == "draft" and not title:
        _add_gap(
            result,
            code="missing_title",
            gap_type="task_identity_missing",
            group="task_identity",
            role_label="任务标题",
            severity="error",
            message="缺少任务标题或一级标题。",
        )
    if not _role_has_identity(harness.get("main_owner")):
        _add_gap(
            result,
            code="missing_main_owner",
            gap_type="role_missing",
            group="main_owner",
            role_label="主负责位",
            severity="error",
            message="缺少主负责位，或主负责位未落到具体 Agent/alias。",
        )
    if stage in {"review"}:
        has_review_gate = bool(harness.get("management_slot") or harness.get("custom_roles"))
        if not has_review_gate:
            _add_gap(
                result,
                code="missing_review_gate",
                gap_type="role_missing",
                group="review_gate",
                role_label="审核或门禁位",
                severity="error",
                message="评审阶段缺少审核或门禁位。",
            )
        if not _contains_review_input(body):
            _add_gap(
                result,
                code="missing_review_input",
                gap_type="stage_evidence_missing",
                group="review_input",
                role_label="评审对象",
                severity="error",
                message="评审阶段缺少方案/需求路径或评审对象。",
            )
    if stage in {"dispatch"}:
        if not _any_role_has_identity(harness.get("collaborators") or [], require_session=True):
            _add_gap(
                result,
                code="missing_executor_session",
                gap_type="role_incomplete",
                group="collaborators",
                role_label="执行位",
                severity="error",
                message="派发/进行中阶段缺少执行位，或执行位未落到具体 Agent 和 session_id。",
            )
        if not _contains_announce_run_id(body):
            _add_gap(
                result,
                code="missing_announce_run_id",
                gap_type="dispatch_evidence_missing",
                group="dispatch_evidence",
                role_label="正式派发证据",
                severity="error",
                message="派发/进行中阶段缺少正式 announce 产生的 announce_run_id。",
            )
    if stage in {"acceptance", "done"}:
        if not _any_role_has_identity(harness.get("validators") or [], require_session=True):
            _add_gap(
                result,
                code="missing_validator_session",
                gap_type="role_incomplete",
                group="validators",
                role_label="验收位",
                severity="error",
                message="验收/完成阶段缺少验收位，或验收位未落到具体 Agent 和 session_id。",
            )
        if "验收口径" not in body:
            _add_gap(
                result,
                code="missing_acceptance_criteria",
                gap_type="stage_evidence_missing",
                group="acceptance_criteria",
                role_label="验收口径",
                severity="error",
                message="验收/完成阶段缺少冻结验收口径。",
            )
        if not _contains_path_or_evidence(body):
            _add_gap(
                result,
                code="missing_acceptance_evidence",
                gap_type="stage_evidence_missing",
                group="acceptance_evidence",
                role_label="验收证据",
                severity="error",
                message="验收/完成阶段缺少证据路径、live 检查证据或报告路径。",
            )
    if stage == "done":
        if "当前结论" not in body and "完成结论" not in body:
            _add_gap(
                result,
                code="missing_completion_conclusion",
                gap_type="completion_evidence_missing",
                group="completion_conclusion",
                role_label="完成结论",
                severity="error",
                message="完成阶段缺少完成结论。",
            )
        if "收口" not in body and "结果回执" not in body:
            _add_gap(
                result,
                code="missing_closeout_receipt",
                gap_type="completion_evidence_missing",
                group="closeout_receipt",
                role_label="收口回执",
                severity="error",
                message="完成阶段缺少结果回执或任务文件收口块。",
            )
        if not re.search(r"\brun_id\s*[=:]|announce_run_id\s*=|报告", body):
            _add_gap(
                result,
                code="missing_completion_run_or_report",
                gap_type="completion_evidence_missing",
                group="completion_evidence",
                role_label="完成证据",
                severity="error",
                message="完成阶段缺少关键 run_id 或报告路径。",
            )
    if any(keyword in body for keyword in PAGE_EXPERIENCE_KEYWORDS) and not _has_visual_reviewer(harness, body):
        _add_gap(
            result,
            code="missing_visual_reviewer_notice",
            gap_type="role_suggested",
            group="visual_reviewer",
            role_label="视觉审核位",
            severity="warning",
            message="页面体验类任务建议启用视觉审核位，或写明不启用原因。",
        )
    if not strict and result.errors:
        error_messages = list(result.errors)
        for gap in result.gaps:
            if gap.get("severity") == "error":
                gap["severity"] = "warning"
        result.warnings.extend(f"历史报告项：{message}" for message in error_messages)
        result.errors = []
    return result


def validation_result_payload(result: ValidationResult) -> dict[str, Any]:
    return {
        "ok": result.ok,
        "path": result.path,
        "stage": result.stage,
        "strict": result.strict,
        "errors": list(result.errors),
        "warnings": list(result.warnings),
        "gaps": [dict(gap) for gap in result.gaps],
    }


def _first_payload_value(payload: dict[str, Any], *keys: str, default: Any = "") -> Any:
    for key in keys:
        if key in payload:
            return payload.get(key)
    return default


def _first_role_payload(payload: dict[str, Any], role_name: str) -> dict[str, Any]:
    for key in ROLE_PAYLOAD_KEYS.get(role_name, (role_name,)):
        raw = payload.get(key)
        if isinstance(raw, list):
            raw = raw[0] if raw else {}
        if isinstance(raw, dict):
            return dict(raw)
    return {}


def _role_field(role_payload: dict[str, Any], *keys: str) -> str:
    return _as_str(_first_payload_value(role_payload, *keys)).strip()


def _resolve_role_from_payload(
    *,
    root: Path,
    project: dict[str, Any],
    project_id: str,
    payload: dict[str, Any],
    role_name: str,
    fallback_prefix: str,
) -> dict[str, str] | None:
    role_payload = _first_role_payload(payload, role_name)
    agent_name = _role_field(role_payload, "agentName", "agent_name", "agent", "name")
    channel_name = _role_field(role_payload, "channelName", "channel_name", "channel")
    session_id = _role_field(role_payload, "sessionId", "session_id", "id")
    alias = _role_field(role_payload, "alias", "displayName", "display_name")
    agent_name = agent_name or _as_str(_first_payload_value(payload, f"{fallback_prefix}Agent", f"{fallback_prefix}_agent")).strip()
    channel_name = channel_name or _as_str(_first_payload_value(payload, f"{fallback_prefix}Channel", f"{fallback_prefix}_channel")).strip()
    session_id = session_id or _as_str(_first_payload_value(payload, f"{fallback_prefix}SessionId", f"{fallback_prefix}_session_id")).strip()
    alias = alias or _as_str(_first_payload_value(payload, f"{fallback_prefix}Alias", f"{fallback_prefix}_alias")).strip()
    if role_name == "visual_reviewer":
        agent_name = agent_name or _as_str(_first_payload_value(payload, "visualReviewerAgent", "visual_reviewer_agent")).strip()
        channel_name = channel_name or _as_str(_first_payload_value(payload, "visualReviewerChannel", "visual_reviewer_channel")).strip()
        session_id = session_id or _as_str(_first_payload_value(payload, "visualReviewerSessionId", "visual_reviewer_session_id")).strip()
        alias = alias or _as_str(_first_payload_value(payload, "visualReviewerAlias", "visual_reviewer_alias")).strip()
    if not any((agent_name, channel_name, session_id, alias)):
        return None
    return _resolve_agent(
        root=root,
        project=project,
        project_id=project_id,
        agent_name=agent_name,
        channel_name=channel_name,
        session_id=session_id,
        alias=alias,
    )


def _relative_to_root(root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except Exception:
        return str(path)


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except Exception:
        return False


def _resolve_task_output_path(
    *,
    root: Path,
    task_root: Path,
    owner_channel: str,
    status: str,
    title: str,
    output: Any,
) -> tuple[Path | None, dict[str, Any] | None]:
    raw_output = _as_str(output).strip()
    if raw_output:
        out_path = Path(raw_output).expanduser()
        if not out_path.is_absolute():
            out_path = (root / out_path).resolve()
        else:
            out_path = out_path.resolve()
    else:
        out_path = _default_task_path(task_root, owner_channel, status, title).resolve()
    if out_path.suffix.lower() != ".md":
        return None, {
            "ok": False,
            "error": "invalid_output_path",
            "message": "outputPath must point to a Markdown .md file",
            "step": "request_validate",
        }
    if not _is_relative_to(out_path, task_root):
        return None, {
            "ok": False,
            "error": "output_path_outside_task_root",
            "message": "outputPath must stay under the configured task root",
            "step": "request_validate",
        }
    return out_path, None


def create_task_from_payload(
    *,
    root: Path,
    project_id: str,
    payload: dict[str, Any],
    dry_run: bool | None = None,
) -> tuple[int, dict[str, Any]]:
    """Create or preview a standard task file through the same task_harness rules used by task_cli."""
    root = root.expanduser().resolve()
    project_id = _as_str(project_id).strip() or "task_dashboard"
    project = _project_cfg(root, project_id)
    task_root = _task_root(root, project)
    task_root_rel = _task_root_rel(root, task_root)
    title = _as_str(_first_payload_value(payload, "title", "taskTitle", "task_title")).strip()
    if not title:
        return 400, {
            "ok": False,
            "error": "missing_required_fields",
            "message": "missing: title",
            "step": "request_validate",
            "missing": ["title"],
        }
    stage = _normalize_stage(_first_payload_value(payload, "stage", "statusGate", "status_gate", default="draft"))
    status = STAGE_STATUS.get(stage, "待开始")
    kind = _as_str(_first_payload_value(payload, "kind", "taskKind", "task_kind", default="实施任务")).strip() or "实施任务"
    owner = _resolve_role_from_payload(
        root=root,
        project=project,
        project_id=project_id,
        payload=payload,
        role_name="owner",
        fallback_prefix="owner",
    )
    if not owner or not owner.get("agent_name"):
        return 400, {
            "ok": False,
            "error": "missing_main_owner",
            "message": "缺少主负责位，或主负责位未落到具体 Agent/alias。",
            "step": "request_validate",
            "missing": ["owner.agentName"],
        }
    output_path, output_error = _resolve_task_output_path(
        root=root,
        task_root=task_root,
        owner_channel=owner.get("channel_name", ""),
        status=status,
        title=title,
        output=_first_payload_value(payload, "outputPath", "output_path", "path"),
    )
    if output_error:
        return 400, output_error
    assert output_path is not None
    if not owner.get("channel_name") and not _as_str(_first_payload_value(payload, "outputPath", "output_path", "path")).strip():
        return 400, {
            "ok": False,
            "error": "missing_owner_channel",
            "message": "无法从会话真源解析主负责通道，请补 owner.channelName 或 outputPath。",
            "step": "resolve_owner",
        }
    force = _coerce_bool(_first_payload_value(payload, "force"), False)
    is_dry_run = _coerce_bool(_first_payload_value(payload, "dryRun", "dry_run"), False) if dry_run is None else bool(dry_run)
    if output_path.exists() and not force and not is_dry_run:
        return 409, {
            "ok": False,
            "error": "task_file_exists",
            "message": f"目标任务文件已存在：{output_path}",
            "step": "write_file",
            "path": _relative_to_root(root, output_path),
            "absolute_path": str(output_path),
        }
    executor = _resolve_role_from_payload(
        root=root,
        project=project,
        project_id=project_id,
        payload=payload,
        role_name="executor",
        fallback_prefix="executor",
    )
    validator = _resolve_role_from_payload(
        root=root,
        project=project,
        project_id=project_id,
        payload=payload,
        role_name="validator",
        fallback_prefix="validator",
    )
    reviewer = _resolve_role_from_payload(
        root=root,
        project=project,
        project_id=project_id,
        payload=payload,
        role_name="reviewer",
        fallback_prefix="reviewer",
    )
    visual_reviewer = _resolve_role_from_payload(
        root=root,
        project=project,
        project_id=project_id,
        payload=payload,
        role_name="visual_reviewer",
        fallback_prefix="visualReviewer",
    )
    task_id = _as_str(_first_payload_value(payload, "taskId", "task_id")).strip() or generate_task_id()
    parent_task_id = _as_str(_first_payload_value(payload, "parentTaskId", "parent_task_id")).strip()
    markdown = _render_task_markdown(
        project_id=project_id,
        task_id=task_id,
        parent_task_id=parent_task_id,
        title=title,
        stage=stage,
        status=status,
        kind=kind,
        owner=owner,
        executor=executor,
        validator=validator,
        reviewer=reviewer,
        visual_reviewer=visual_reviewer,
    )
    validation = validate_markdown(
        root=root,
        project_id=project_id,
        task_root_rel=task_root_rel,
        path_label=_relative_to_root(root, output_path),
        markdown=markdown,
        stage=stage,
        strict=True,
    )
    roles = parse_task_harness(
        root=root,
        task_root_rel=task_root_rel,
        project_id=project_id,
        item_type="任务",
        markdown=markdown,
    )
    base_payload: dict[str, Any] = {
        "ok": validation.ok,
        "schema_version": "task_workflow.create.v1",
        "action": "create",
        "dry_run": is_dry_run,
        "project_id": project_id,
        "task_id": task_id,
        "parent_task_id": parent_task_id,
        "stage": stage,
        "status": status,
        "kind": kind,
        "path": _relative_to_root(root, output_path),
        "absolute_path": str(output_path),
        "validation": validation_result_payload(validation),
        "parsed_roles": roles,
        "safety": {
            "writer": "task_cli.create_task_from_payload",
            "task_root": _relative_to_root(root, task_root),
            "direct_page_write_allowed": False,
            "requires_announce_run_id_for_dispatch": True,
        },
    }
    if _coerce_bool(_first_payload_value(payload, "includeMarkdown", "include_markdown"), is_dry_run):
        base_payload["markdown"] = markdown
    if not validation.ok:
        base_payload.update(
            {
                "ok": False,
                "error": "validation_failed",
                "message": "任务责任位或阶段门禁校验未通过，未写入任务文件。",
                "step": "validate",
            }
        )
        return 422, base_payload
    if not is_dry_run:
        atomic_write_text(output_path, markdown)
        base_payload["created"] = True
    else:
        base_payload["created"] = False
    return (200 if is_dry_run else 201), base_payload


def validate_task_from_payload(
    *,
    root: Path,
    project_id: str,
    payload: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    root = root.expanduser().resolve()
    project_id = _as_str(project_id).strip() or "task_dashboard"
    project = _project_cfg(root, project_id)
    task_root = _task_root(root, project)
    task_root_rel = _task_root_rel(root, task_root)
    path_raw = _as_str(_first_payload_value(payload, "path", "taskPath", "task_path")).strip()
    markdown = _as_str(_first_payload_value(payload, "markdown", "content")).strip()
    stage_arg = _as_str(_first_payload_value(payload, "stage", "statusGate", "status_gate")).strip()
    if not path_raw and not markdown:
        create_code, create_payload = create_task_from_payload(
            root=root,
            project_id=project_id,
            payload={**payload, "dryRun": True, "includeMarkdown": _coerce_bool(_first_payload_value(payload, "includeMarkdown", "include_markdown"), False)},
            dry_run=True,
        )
        create_payload["action"] = "validate_create_payload"
        return (200 if create_payload.get("ok") else create_code), create_payload
    path_label = "<inline>"
    if path_raw:
        path = Path(path_raw).expanduser()
        if not path.is_absolute():
            path = (root / path).resolve()
        else:
            path = path.resolve()
        if not _is_relative_to(path, task_root):
            return 400, {
                "ok": False,
                "error": "path_outside_task_root",
                "message": "path must stay under the configured task root",
                "step": "request_validate",
            }
        if not path.is_file():
            return 404, {
                "ok": False,
                "error": "task_file_not_found",
                "message": f"任务文件不存在：{path}",
                "step": "read_file",
                "path": _relative_to_root(root, path),
            }
        markdown = safe_read_text(path)
        path_label = _relative_to_root(root, path)
        status = _status_from_path(path)
    else:
        status = ""
    stage = _normalize_stage(stage_arg) if stage_arg else _infer_stage_from_status(status)
    strict = _coerce_bool(_first_payload_value(payload, "strict"), bool(stage_arg) or not path_raw or status not in INACTIVE_STATUSES)
    result = validate_markdown(
        root=root,
        project_id=project_id,
        task_root_rel=task_root_rel,
        path_label=path_label,
        markdown=markdown,
        stage=stage,
        strict=strict,
    )
    response = {
        "ok": result.ok,
        "schema_version": "task_workflow.validate.v1",
        "action": "validate",
        "project_id": project_id,
        "validation": validation_result_payload(result),
        "parsed_roles": parse_task_harness(
            root=root,
            task_root_rel=task_root_rel,
            project_id=project_id,
            item_type="任务",
            markdown=markdown,
        ),
    }
    if not result.ok:
        response.update(
            {
                "error": "validation_failed",
                "message": "任务责任位或阶段门禁校验未通过。",
                "step": "validate",
            }
        )
    return (200 if result.ok else 422), response


def _print_validation_result(result: ValidationResult) -> None:
    status = "OK" if result.ok else "FAIL"
    print(f"{status}: {result.path} stage={result.stage} strict={str(result.strict).lower()}")
    for message in result.errors:
        print(f"ERROR: {message}")
    for message in result.warnings:
        print(f"WARNING: {message}")


def _group_counts(rows: list[dict[str, str]], field_name: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        key = _as_str(row.get(field_name)).strip() or "unknown"
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def _parsed_roles_from_item(item: Any) -> dict[str, Any]:
    return {
        "main_owner": item.main_owner or None,
        "collaborators": item.collaborators or [],
        "validators": item.validators or [],
        "challengers": item.challengers or [],
        "backup_owners": item.backup_owners or [],
        "management_slot": item.management_slot or [],
        "custom_roles": item.custom_roles or [],
        "executors": item.executors or [],
        "acceptors": item.acceptors or [],
        "reviewers": item.reviewers or [],
        "visual_reviewers": item.visual_reviewers or [],
    }


def _scan_item_payload(item: Any, result: ValidationResult) -> dict[str, Any]:
    gaps = list(result.gaps)
    role_gap_groups = sorted(
        {
            _as_str(gap.get("group")).strip()
            for gap in gaps
            if _as_str(gap.get("type")).strip().startswith("role_")
        }
    )
    return {
        "path": item.path,
        "task_id": item.task_id,
        "parent_task_id": item.parent_task_id,
        "title": item.title,
        "channel": item.channel,
        "status": item.status,
        "stage": result.stage,
        "strict": result.strict,
        "ok": result.ok,
        "errors": result.errors,
        "warnings": result.warnings,
        "gap_types": sorted({_as_str(gap.get("type")).strip() for gap in gaps if _as_str(gap.get("type")).strip()}),
        "missing_groups": sorted({_as_str(gap.get("group")).strip() for gap in gaps if _as_str(gap.get("group")).strip()}),
        "role_missing_groups": role_gap_groups,
        "gaps": gaps,
        "parsed_roles": _parsed_roles_from_item(item),
    }


def _scan_payload(
    *,
    project_id: str,
    active_only: bool,
    items: list[Any],
    results: list[ValidationResult],
) -> dict[str, Any]:
    item_payloads = [_scan_item_payload(item, result) for item, result in zip(items, results)]
    all_gaps = [gap for item in item_payloads for gap in item.get("gaps", [])]
    error_count = sum(len(item.get("errors") or []) for item in item_payloads)
    warning_count = sum(len(item.get("warnings") or []) for item in item_payloads)
    return {
        "schema_version": "task_cli.scan.v1",
        "project_id": project_id,
        "active_only": active_only,
        "summary": {
            "task_count": len(item_payloads),
            "ok_count": sum(1 for item in item_payloads if item.get("ok")),
            "issue_task_count": sum(1 for item in item_payloads if item.get("errors") or item.get("warnings")),
            "error_count": error_count,
            "warning_count": warning_count,
            "gap_type_counts": _group_counts(all_gaps, "type"),
            "missing_group_counts": _group_counts(all_gaps, "group"),
            "severity_counts": _group_counts(all_gaps, "severity"),
        },
        "items": item_payloads,
    }


def _cmd_create(args: argparse.Namespace) -> int:
    root = Path(args.root).expanduser().resolve()
    project_id = _as_str(args.project_id).strip() or "task_dashboard"
    project = _project_cfg(root, project_id)
    task_root = _task_root(root, project)
    task_root_rel = _task_root_rel(root, task_root)
    stage = _normalize_stage(args.stage)
    status = STAGE_STATUS.get(stage, "待开始")
    owner = _resolve_agent(
        root=root,
        project=project,
        project_id=project_id,
        agent_name=args.owner_agent,
        channel_name=args.owner_channel,
        session_id=args.owner_session_id,
        alias=args.owner_alias,
    )
    if not owner.get("agent_name"):
        print("ERROR: 缺少主负责 Agent。", file=sys.stderr)
        return 2
    if not owner.get("channel_name") and not args.output:
        print("ERROR: 无法从会话真源解析主负责通道，请补 --owner-channel 或 --output。", file=sys.stderr)
        return 2
    executor = None
    if args.executor_agent or args.executor_channel or args.executor_session_id:
        executor = _resolve_agent(
            root=root,
            project=project,
            project_id=project_id,
            agent_name=args.executor_agent,
            channel_name=args.executor_channel,
            session_id=args.executor_session_id,
            alias=args.executor_alias,
        )
    validator = None
    if args.validator_agent or args.validator_channel or args.validator_session_id:
        validator = _resolve_agent(
            root=root,
            project=project,
            project_id=project_id,
            agent_name=args.validator_agent,
            channel_name=args.validator_channel,
            session_id=args.validator_session_id,
            alias=args.validator_alias,
        )
    reviewer = None
    if args.reviewer_agent or args.reviewer_channel or args.reviewer_session_id:
        reviewer = _resolve_agent(
            root=root,
            project=project,
            project_id=project_id,
            agent_name=args.reviewer_agent,
            channel_name=args.reviewer_channel,
            session_id=args.reviewer_session_id,
            alias=args.reviewer_alias,
        )
    visual_reviewer = None
    if args.visual_reviewer_agent or args.visual_reviewer_channel or args.visual_reviewer_session_id:
        visual_reviewer = _resolve_agent(
            root=root,
            project=project,
            project_id=project_id,
            agent_name=args.visual_reviewer_agent,
            channel_name=args.visual_reviewer_channel,
            session_id=args.visual_reviewer_session_id,
            alias=args.visual_reviewer_alias,
        )
    task_id = _as_str(args.task_id).strip() or generate_task_id()
    markdown = _render_task_markdown(
        project_id=project_id,
        task_id=task_id,
        parent_task_id=args.parent_task_id,
        title=args.title,
        stage=stage,
        status=status,
        kind=args.kind,
        owner=owner,
        executor=executor,
        validator=validator,
        reviewer=reviewer,
        visual_reviewer=visual_reviewer,
    )
    out_path = Path(args.output).expanduser() if args.output else _default_task_path(task_root, owner.get("channel_name", ""), status, args.title)
    if not out_path.is_absolute():
        out_path = (root / out_path).resolve()
    structural_validation = validate_markdown(
        root=root,
        project_id=project_id,
        task_root_rel=task_root_rel,
        path_label=str(out_path),
        markdown=markdown,
        stage="draft",
        strict=True,
    )
    if structural_validation.errors:
        _print_validation_result(structural_validation)
        return 1
    gate_preview = validate_markdown(
        root=root,
        project_id=project_id,
        task_root_rel=task_root_rel,
        path_label=str(out_path),
        markdown=markdown,
        stage=stage,
        strict=False,
    )
    if args.print_only:
        print(markdown)
        if gate_preview.warnings:
            _print_validation_result(gate_preview)
        return 0
    if out_path.exists() and not args.force:
        print(f"ERROR: 目标文件已存在：{out_path}", file=sys.stderr)
        return 2
    atomic_write_text(out_path, markdown)
    print(f"created: {out_path}")
    print(f"task_id: {task_id}")
    print(f"stage: {stage}")
    if gate_preview.warnings:
        print("check:")
        for message in gate_preview.warnings:
            print(f"WARNING: {message}")
    print("next: validate 通过；若进入派发，需正式 announce 后补 announce_run_id。")
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    root = Path(args.root).expanduser().resolve()
    project_id = _as_str(args.project_id).strip() or "task_dashboard"
    project = _project_cfg(root, project_id)
    task_root = _task_root(root, project)
    task_root_rel = _task_root_rel(root, task_root)
    path = Path(args.path).expanduser()
    if not path.is_absolute():
        path = (root / path).resolve()
    if not path.is_file():
        print(f"ERROR: 任务文件不存在：{path}", file=sys.stderr)
        return 2
    markdown = safe_read_text(path)
    status = _status_from_path(path)
    stage_arg = _as_str(args.stage).strip()
    stage = _normalize_stage(stage_arg) if stage_arg else _infer_stage_from_status(status)
    strict = args.mode == "strict" or (args.mode == "auto" and (bool(stage_arg) or status not in INACTIVE_STATUSES))
    result = validate_markdown(
        root=root,
        project_id=project_id,
        task_root_rel=task_root_rel,
        path_label=str(path),
        markdown=markdown,
        stage=stage,
        strict=strict,
    )
    _print_validation_result(result)
    return 0 if result.ok else 1


def _cmd_scan(args: argparse.Namespace) -> int:
    root = Path(args.root).expanduser().resolve()
    project_id = _as_str(args.project_id).strip() or "task_dashboard"
    project = _project_cfg(root, project_id)
    task_root = _task_root(root, project)
    task_root_rel = _task_root_rel(root, task_root)
    project_name = _as_str(project.get("name")).strip() or project_id
    items = iter_items(root=root, project_id=project_id, project_name=project_name, task_root_rel=task_root_rel)
    task_items = [item for item in items if item.type == "任务"]
    if args.active_only:
        task_items = [item for item in task_items if item.status in ACTIVE_STATUSES]
    results: list[ValidationResult] = []
    for item in task_items:
        path = (root / item.path).resolve()
        markdown = safe_read_text(path)
        stage = _infer_stage_from_status(item.status)
        strict = item.status in ACTIVE_STATUSES
        results.append(
            validate_markdown(
                root=root,
                project_id=project_id,
                task_root_rel=task_root_rel,
                path_label=item.path,
                markdown=markdown,
                stage=stage,
                strict=strict,
            )
        )
    error_count = sum(len(result.errors) for result in results)
    warning_count = sum(len(result.warnings) for result in results)
    if args.format == "json":
        payload = _scan_payload(project_id=project_id, active_only=args.active_only, items=task_items, results=results)
        text = json.dumps(payload, ensure_ascii=False, indent=2)
        if args.output:
            output_path = Path(args.output).expanduser()
            if not output_path.is_absolute():
                output_path = (root / output_path).resolve()
            atomic_write_text(output_path, text + "\n")
        else:
            print(text)
        return 1 if error_count else 0
    print(f"scan: tasks={len(results)} errors={error_count} warnings={warning_count} active_only={str(args.active_only).lower()}")
    for result in results:
        if result.errors or result.warnings:
            _print_validation_result(result)
    return 1 if error_count else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="task_cli")
    parser.add_argument("--root", default=str(repo_root_from_here(__file__)), help="task-dashboard repo root")
    parser.add_argument("--project-id", default="task_dashboard")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create", help="create a standard task markdown file")
    create.add_argument("--kind", default="实施任务")
    create.add_argument("--title", required=True)
    create.add_argument("--stage", default="draft")
    create.add_argument("--task-id", default="")
    create.add_argument("--parent-task-id", default="")
    create.add_argument("--owner-agent", required=True)
    create.add_argument("--owner-channel", default="")
    create.add_argument("--owner-session-id", default="")
    create.add_argument("--owner-alias", default="")
    create.add_argument("--executor-agent", default="")
    create.add_argument("--executor-channel", default="")
    create.add_argument("--executor-session-id", default="")
    create.add_argument("--executor-alias", default="")
    create.add_argument("--validator-agent", default="")
    create.add_argument("--validator-channel", default="")
    create.add_argument("--validator-session-id", default="")
    create.add_argument("--validator-alias", default="")
    create.add_argument("--reviewer-agent", default="")
    create.add_argument("--reviewer-channel", default="")
    create.add_argument("--reviewer-session-id", default="")
    create.add_argument("--reviewer-alias", default="")
    create.add_argument("--visual-reviewer-agent", default="")
    create.add_argument("--visual-reviewer-channel", default="")
    create.add_argument("--visual-reviewer-session-id", default="")
    create.add_argument("--visual-reviewer-alias", default="")
    create.add_argument("--output", default="")
    create.add_argument("--force", action="store_true")
    create.add_argument("--print-only", action="store_true")
    create.set_defaults(func=_cmd_create)

    validate = sub.add_parser("validate", help="validate task role gates")
    validate.add_argument("--path", required=True)
    validate.add_argument("--stage", default="")
    validate.add_argument("--mode", choices=["auto", "strict", "report-only"], default="auto")
    validate.set_defaults(func=_cmd_validate)

    scan = sub.add_parser("scan", help="scan task role gate gaps")
    scan.add_argument("--active-only", action="store_true")
    scan.add_argument("--format", choices=["text", "json"], default="text")
    scan.add_argument("--output", default="", help="write structured JSON output to file")
    scan.set_defaults(func=_cmd_scan)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "validate" and args.mode == "report-only":
        args.mode = "report-only"
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
