#!/usr/bin/env python3
"""Generate project-level collaboration registry (CCR v1) from config + sessions."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import tomllib  # py311+
except Exception:  # pragma: no cover
    import tomli as tomllib  # type: ignore


STRUCTURE_LAYER_ORDER = {
    "现役主干": 0,
    "低频通道": 1,
    "待启用通道": 2,
    "历史壳": 3,
    "未分层": 9,
}
_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_OPENCODE_SESSION_RE = re.compile(r"^ses_[A-Za-z0-9_-]{6,}$")
_SESSION_LABEL_RE = re.compile(r"^(?:会话|Session)\s*[0-9a-fA-F-]{4,}$", re.IGNORECASE)
_PSEUDO_NAME_RE = re.compile(r"^(?:agent|user|session|tmp|temp|random)[_-]?[0-9a-fA-F]{4,}$", re.IGNORECASE)
_MISSING_IDENTITY_VALUES = {
    "",
    "-",
    "unknown",
    "unnamed",
    "none",
    "null",
    "n/a",
    "na",
    "未命名",
    "未命名会话",
    "身份未解析",
    "未解析",
}
_USER_VISIBLE_IDENTITY_FIELDS = ("display_name", "desc", "agent_name", "agent_alias")


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _safe_text(v: Any) -> str:
    return str(v or "").strip()


def _safe_bool(v: Any, default: bool = False) -> bool:
    if isinstance(v, bool):
        return v
    text = _safe_text(v).lower()
    if text in {"true", "1", "yes", "y", "on"}:
        return True
    if text in {"false", "0", "no", "n", "off"}:
        return False
    return default


def _resolve_path(raw: str, workspace_root: Path) -> Path:
    p = Path(raw).expanduser()
    if p.is_absolute():
        return p
    return (workspace_root / p).resolve()


def _resolve_config_rel_path(raw: str, workspace_root: Path) -> Path:
    p = Path(raw).expanduser()
    if p.is_absolute():
        return p.resolve()
    candidates: list[Path] = [(workspace_root / p).resolve()]
    for parent in workspace_root.parents:
        candidates.append((parent / p).resolve())
    existing = [cand for cand in candidates if cand.exists()]
    if existing:
        existing.sort(key=lambda it: len(it.parts))
        return existing[0]
    return candidates[0]


def _load_toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as f:
        data = tomllib.load(f)
    if not isinstance(data, dict):
        raise ValueError("config.toml 顶层结构非法")
    return data


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    raw = path.read_text(encoding="utf-8")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError(f"JSON 非对象结构: {path}")
    return data


def _resolve_project_session_store(
    project_id: str,
    project_root: Path,
    workspace_root: Path,
    explicit_path: str = "",
) -> Path:
    candidates: list[Path] = []
    if _safe_text(explicit_path):
        candidates.append(_resolve_path(_safe_text(explicit_path), workspace_root))
    candidates.extend(
        [
            (project_root / ".runtime" / "stable" / ".sessions" / f"{project_id}.json").resolve(),
            (workspace_root / ".runtime" / "stable" / ".sessions" / f"{project_id}.json").resolve(),
            (project_root / ".sessions" / f"{project_id}.json").resolve(),
            (workspace_root / ".sessions" / f"{project_id}.json").resolve(),
        ]
    )
    for path in candidates:
        if path.exists():
            return path
    return candidates[0] if candidates else (workspace_root / ".sessions" / f"{project_id}.json").resolve()


def _load_project_session_rows(session_store_path: Path) -> list[dict[str, str]]:
    path = session_store_path
    if path.exists():
        if not path.exists():
            return []
        data = _load_json(path)
        sessions = data.get("sessions")
        if not isinstance(sessions, list):
            return []
        out: list[dict[str, str]] = []
        for row in sessions:
            if not isinstance(row, dict):
                continue
            if bool(row.get("is_deleted")):
                continue
            sid = _safe_text(row.get("id") or row.get("session_id") or row.get("sessionId"))
            if not sid:
                continue
            out.append(
                {
                    "session_id": sid,
                    "alias": _safe_text(row.get("alias")),
                    "channel_name": _safe_text(row.get("channel_name") or row.get("channelName")),
                    "status": _safe_text(row.get("status")) or "active",
                    "cli_type": _safe_text(row.get("cli_type") or row.get("cliType")),
                    "model": _safe_text(row.get("model")),
                    "purpose": _safe_text(row.get("purpose")),
                    "environment": _safe_text(row.get("environment")),
                    "worktree_root": _safe_text(row.get("worktree_root")),
                    "workdir": _safe_text(row.get("workdir")),
                    "branch": _safe_text(row.get("branch")),
                    "session_role": _safe_text(row.get("session_role")),
                    "is_primary": bool(row.get("is_primary")),
                }
            )
        return out
    return []


def _find_project(cfg: dict[str, Any], project_id: str) -> dict[str, Any]:
    projects = cfg.get("projects")
    if not isinstance(projects, list):
        raise ValueError("config.toml 缺少 projects 数组")
    for it in projects:
        if isinstance(it, dict) and _safe_text(it.get("id")) == project_id:
            return it
    raise ValueError(f"未在 config.toml 找到项目: {project_id}")


def _infer_channel_role(channel_name: str) -> str:
    name = _safe_text(channel_name)
    if name.startswith("主体") or "总控" in name:
        return "main_control"
    if name.startswith("子级"):
        return "execution"
    if name.startswith("辅助"):
        return "support"
    if "测试" in name or "验收" in name:
        return "qa"
    return "other"


def _has_any(text: str, terms: list[str]) -> bool:
    return any(term and term in text for term in terms)


def _safe_text_list(value: Any) -> list[str]:
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            clean = _safe_text(item)
            if clean and clean not in out:
                out.append(clean)
        return out
    if isinstance(value, str):
        out = []
        for item in value.replace("，", ",").split(","):
            clean = _safe_text(item)
            if clean and clean not in out:
                out.append(clean)
        return out
    return []


def _compact_identity(value: str) -> str:
    return re.sub(r"[^0-9a-fA-F]", "", str(value or "")).lower()


def _identity_issue(value: Any, *, session_id: str = "") -> str:
    text = _safe_text(value)
    lowered = text.lower()
    if lowered in _MISSING_IDENTITY_VALUES:
        return "missing_readable_identity"
    sid = _safe_text(session_id)
    if sid and text == sid:
        return "session_id_as_identity"
    if _UUID_RE.match(text) or _OPENCODE_SESSION_RE.match(text):
        return "technical_identity"
    if _SESSION_LABEL_RE.match(text):
        return "technical_identity"
    if _PSEUDO_NAME_RE.match(text):
        return "technical_identity"
    if sid:
        compact_sid = _compact_identity(sid)
        compact_text = _compact_identity(text)
        if len(compact_sid) >= 8 and len(compact_text) >= 4 and compact_text in compact_sid:
            return "session_id_as_identity"
    return ""


def _agent_display_fallback(channel_name: str) -> str:
    channel = _safe_text(channel_name) or "未知通道"
    return f"未命名Agent·{channel}"


def _resolve_ccr_agent_identity(*, alias: str, channel_name: str, session_id: str) -> dict[str, Any]:
    clean_alias = _safe_text(alias)
    issue = _identity_issue(clean_alias, session_id=session_id) if clean_alias else "missing_readable_identity"
    if issue:
        return {
            "display_name": _agent_display_fallback(channel_name),
            "identity_source": "fallback_missing_alias" if issue == "missing_readable_identity" else "fallback_invalid_alias",
            "identity_issue": issue,
            "identity_fallback_used": True,
        }
    return {
        "display_name": clean_alias,
        "identity_source": "alias",
        "identity_issue": "",
        "identity_fallback_used": False,
    }


def _issue(
    code: str,
    message: str,
    *,
    severity: str = "error",
    project_id: str = "",
    channel_name: str = "",
    session_id: str = "",
    field: str = "",
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "severity": severity,
        "code": code,
        "message": message,
        "blocking": severity == "error",
    }
    for key, value in {
        "project_id": project_id,
        "channel_name": channel_name,
        "session_id": session_id,
        "field": field,
    }.items():
        clean = _safe_text(value)
        if clean:
            item[key] = clean
    if details:
        item["details"] = details
    return item


def _normal_identity_key(value: Any) -> str:
    return _safe_text(value).casefold()


def _validate_ccr_identity_gate(
    *,
    project_id: str,
    channel_rows: list[dict[str, Any]],
    preflight_issues: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return additive CCR validation for creation gate consumption.

    The generator still writes derived artifacts; callers decide whether
    blocking issues should stop a creation flow or be shown as runtime degraded.
    """
    issues: list[dict[str, Any]] = []
    missing_items: list[dict[str, Any]] = []

    def add(item: dict[str, Any]) -> None:
        issues.append(item)
        if bool(item.get("blocking")):
            missing_items.append(
                {
                    "code": item.get("code"),
                    "project_id": item.get("project_id") or project_id,
                    "channel_name": item.get("channel_name") or "",
                    "session_id": item.get("session_id") or "",
                    "field": item.get("field") or "",
                }
            )

    for item in preflight_issues or []:
        add(item)

    if not _safe_text(project_id):
        add(_issue("missing_project_id", "CCR 缺少 project_id", field="project_id"))

    seen_channels: set[str] = set()
    seen_session_ids: dict[str, str] = {}
    system_issue_count = 0
    identity_issue_count = 0
    conflict_issue_count = 0

    for row in channel_rows:
        if not isinstance(row, dict):
            continue
        channel_name = _safe_text(row.get("channel_name"))
        if not channel_name:
            system_issue_count += 1
            add(_issue("missing_channel_name", "CCR 通道缺少 channel_name", project_id=project_id, field="channel_name"))
            continue
        if channel_name in seen_channels:
            system_issue_count += 1
            add(
                _issue(
                    "duplicate_channel_name",
                    "CCR channel_name 重复",
                    project_id=project_id,
                    channel_name=channel_name,
                    field="channel_name",
                )
            )
        seen_channels.add(channel_name)

        if not isinstance(row.get("formal_dispatch_entry"), bool):
            system_issue_count += 1
            add(
                _issue(
                    "invalid_formal_dispatch_entry",
                    "formal_dispatch_entry 必须为布尔值",
                    project_id=project_id,
                    channel_name=channel_name,
                    field="formal_dispatch_entry",
                )
            )

        candidates = row.get("session_candidates") if isinstance(row.get("session_candidates"), list) else []
        candidate_ids = [_safe_text(cand.get("session_id")) for cand in candidates if isinstance(cand, dict)]
        primary_sid = _safe_text(row.get("primary_session_id"))
        if primary_sid and primary_sid not in candidate_ids:
            system_issue_count += 1
            add(
                _issue(
                    "primary_session_not_in_candidates",
                    "primary_session_id 未命中本通道候选会话",
                    project_id=project_id,
                    channel_name=channel_name,
                    session_id=primary_sid,
                    field="primary_session_id",
                )
            )
        if bool(row.get("requires_primary")) and not primary_sid:
            system_issue_count += 1
            add(
                _issue(
                    "missing_required_primary_session",
                    "必需主会话的通道缺少 primary_session_id",
                    project_id=project_id,
                    channel_name=channel_name,
                    field="primary_session_id",
                )
            )
        if bool(row.get("formal_dispatch_entry")) and not primary_sid:
            system_issue_count += 1
            add(
                _issue(
                    "formal_dispatch_without_primary",
                    "正式派发通道缺少 primary_session_id",
                    project_id=project_id,
                    channel_name=channel_name,
                    field="formal_dispatch_entry",
                )
            )
        primary_count = sum(1 for cand in candidates if isinstance(cand, dict) and bool(cand.get("is_primary")))
        if primary_count > 1:
            system_issue_count += 1
            add(
                _issue(
                    "multiple_primary_sessions",
                    "同一通道存在多个 is_primary 会话",
                    project_id=project_id,
                    channel_name=channel_name,
                    field="is_primary",
                    details={"primary_count": primary_count},
                )
            )

        readable_name_owners: dict[str, set[str]] = {}
        channel_session_ids: set[str] = set()
        for cand in candidates:
            if not isinstance(cand, dict):
                continue
            sid = _safe_text(cand.get("session_id"))
            if not sid:
                system_issue_count += 1
                add(
                    _issue(
                        "missing_session_id",
                        "CCR 候选会话缺少 session_id",
                        project_id=project_id,
                        channel_name=channel_name,
                        field="session_id",
                    )
                )
                continue
            if sid in channel_session_ids:
                system_issue_count += 1
                add(
                    _issue(
                        "duplicate_session_id_in_channel",
                        "同一通道内 session_id 重复",
                        project_id=project_id,
                        channel_name=channel_name,
                        session_id=sid,
                        field="session_id",
                    )
                )
            channel_session_ids.add(sid)
            previous_channel = seen_session_ids.get(sid)
            if previous_channel and previous_channel != channel_name:
                system_issue_count += 1
                add(
                    _issue(
                        "duplicate_session_id",
                        "同一 session_id 出现在多个通道",
                        project_id=project_id,
                        channel_name=channel_name,
                        session_id=sid,
                        field="session_id",
                        details={"previous_channel_name": previous_channel},
                    )
                )
            seen_session_ids.setdefault(sid, channel_name)

            source_issue = _safe_text(cand.get("identity_issue"))
            if source_issue:
                identity_issue_count += 1
                add(
                    _issue(
                        source_issue,
                        "Agent 可读身份缺失或被技术 ID 污染，已仅在派生层使用可读占位",
                        project_id=project_id,
                        channel_name=channel_name,
                        session_id=sid,
                        field="alias",
                    )
                )
            if not bool(cand.get("identity_purpose_present")):
                identity_issue_count += 1
                add(
                    _issue(
                        "missing_session_purpose",
                        "SessionStore 会话缺少 purpose，创建期 gate 应阻断",
                        project_id=project_id,
                        channel_name=channel_name,
                        session_id=sid,
                        field="purpose",
                    )
                )

            for field in _USER_VISIBLE_IDENTITY_FIELDS:
                value = _safe_text(cand.get(field))
                issue_code = _identity_issue(value, session_id=sid)
                if issue_code:
                    identity_issue_count += 1
                    add(
                        _issue(
                            "invalid_user_visible_identity",
                            "用户可见身份字段为空、未解析或包含技术 ID",
                            project_id=project_id,
                            channel_name=channel_name,
                            session_id=sid,
                            field=field,
                            details={"identity_issue": issue_code},
                        )
                    )
                    continue
                key = _normal_identity_key(value)
                if key:
                    readable_name_owners.setdefault(key, set()).add(sid)

        for key, owners in readable_name_owners.items():
            if len(owners) <= 1:
                continue
            conflict_issue_count += 1
            add(
                _issue(
                    "readable_identity_conflict",
                    "同通道内 alias/display_name/agent_name 可读名冲突",
                    project_id=project_id,
                    channel_name=channel_name,
                    field="alias/display_name/agent_name",
                    details={"identity_key": key, "session_ids": sorted(owners)},
                )
            )

    blocking_issues = [item for item in issues if bool(item.get("blocking"))]
    return {
        "version": "p0_identity_gate_v1",
        "ok": not blocking_issues,
        "blocking": bool(blocking_issues),
        "issue_count": len(issues),
        "blocking_issue_count": len(blocking_issues),
        "missing_items": missing_items,
        "issues": issues,
        "summary": {
            "channel_count": len(channel_rows),
            "session_count": len(seen_session_ids),
            "system_issue_count": system_issue_count,
            "identity_issue_count": identity_issue_count,
            "readable_conflict_count": conflict_issue_count,
        },
    }


def _agent_dispatch_profile(channel_name: str, display_name: str, *, is_primary: bool) -> dict[str, Any]:
    """Return additive Agent-level routing metadata for business dispatch.

    The registry remains generated from config + session truth. These fields are
    only a routing aid so task dispatch can target an Agent identity instead of
    falling back to a channel primary session.
    """
    channel = _safe_text(channel_name)
    agent = _safe_text(display_name)
    text = f"{channel} {agent}"
    domains: list[str] = []
    role = "执行位"
    scope = "按 Agent 名称与所在通道职责承接对应业务，不作为泛化兜底。"
    policy = "先按业务板块匹配；再看忙闲与连续性；主 Agent 不默认吃并行执行。"
    tags: list[str] = []

    def add(*items: str) -> None:
        for item in items:
            clean = _safe_text(item)
            if clean and clean not in domains:
                domains.append(clean)

    if channel == "图片生成服务平台" and _has_any(agent, ["专家"]):
        add("图片生成服务平台", "图片生成架构审查", "图片生成风险门禁", "provider策略", "成本安全存储项目模型")
        role = "架构/审查/门禁"
        scope = "负责图片生成服务平台架构策划、provider 策略、成本/安全/存储/项目模型审查与放行门禁，不替代开发执行。"
        policy = "开发完成后优先派给该 Agent 做门禁复核；涉及密钥、计费、底层命令面、服务动作时必须先审查。"
        tags.extend(["image_platform", "architecture_gate", "risk_gate", "provider_strategy"])
    elif channel == "图片生成服务平台" and _has_any(agent, ["服务平台-总"]):
        add("图片生成服务平台", "图片生成跨通道协调", "图片生成验收收口", "统一入口协同")
        role = "跨通道收口/协调/验收"
        scope = "负责图片生成服务平台跨通道协调、任务收口、验收材料和总控/统一入口协同，不替代专项开发执行。"
        policy = "跨通道协调、服务注册知会、验收收口优先派给该 Agent；具体实现派给开发 Agent。"
        tags.extend(["image_platform", "coordination", "acceptance_owner"])
    elif channel == "图片生成服务平台" and _has_any(agent, ["前端-生成大厅", "生成大厅"]):
        add("图片生成服务平台", "生成大厅", "前端UI", "模板交互", "CSS/JS", "作品墙", "图片详情页")
        role = "生成大厅前端/UI/模板/CSS/JS/交互专项执行位"
        scope = "负责 image-platform 生成大厅相关前端页面、Jinja 模板、CSS、原生 JS、交互体验、作品墙和图片详情页落地。"
        policy = "生成大厅、作品墙、图片详情页、前端交互和模板样式任务优先派给该 Agent；改 JS 后必须执行 node --check static/app.js。"
        tags.extend(["image_platform", "generation_hall", "frontend", "ui", "node_check_required"])
    elif channel == "图片生成服务平台" and agent == "图片生成-开发":
        add("图片生成服务平台", "核心后端", "生图链路", "数据模型", "集成编排")
        role = "核心后端/生图链路/数据模型/集成/编排主控"
        scope = "负责 image-platform 核心后端、生图 provider 链路、数据模型、服务集成与执行编排主控。"
        policy = "核心后端、生图链路、数据模型和跨模块集成优先派给该 Agent；前端/后台专项可拆给垂直开发位。"
        tags.extend(["image_platform", "backend_core", "generation_pipeline", "data_model", "integration_owner"])
    elif channel == "图片生成服务平台" and _has_any(agent, ["开发-前端"]):
        add("图片生成服务平台", "前端UI", "模板交互", "视觉系统", "即梦风深色系统")
        role = "前端/UI/模板/CSS/JS/交互/视觉执行位"
        scope = "负责 image-platform 前台页面、Jinja 模板、CSS、原生 JS、交互体验和即梦风深色视觉系统。"
        policy = "前端/UI/模板/CSS/JS/交互/视觉任务优先派给该 Agent；改 JS 后必须执行 node --check static/app.js。"
        tags.extend(["image_platform", "frontend", "ui", "visual_system", "node_check_required"])
    elif channel == "图片生成服务平台" and _has_any(agent, ["开发-后台"]):
        add("图片生成服务平台", "管理后台", "用户使用记录", "审计成本看板", "数据治理测试")
        role = "管理后台/数据治理/测试执行位"
        scope = "负责 image-platform 管理后台、用户管理、使用记录、审计、成本看板、数据治理和测试补强。"
        policy = "后台治理、审计、成本、使用记录、测试补强任务优先派给该 Agent；涉及敏感字段必须先做脱敏核查。"
        tags.extend(["image_platform", "admin_console", "audit", "cost_dashboard", "testing"])
    elif channel == "图片生成内容与风格资产":
        add("图片生成内容与风格资产", "图片资料收集", "分类标注", "风格规范", "风格板", "参考图", "提示词模板", "内容规范")
        role = "内容资产/风格规范/提示词模板执行位"
        scope = "专项负责图片生成服务平台的图片资料收集、分类标注、风格规范提炼、风格板、参考图、提示词模板和内容规范产出。"
        policy = "内容资产、风格体系、参考图、提示词模板和内容规范任务优先派给该 Agent；不确定授权或敏感内容必须先标记待确认并请求审查。"
        tags.extend(["image_platform", "content_assets", "style_assets", "prompt_templates", "reference_images"])
    elif channel == "图片生成服务启动管理":
        add("图片生成服务启动管理", "clitools-image-platform", "18877服务启动管理", "service monitor", "健康检查", "发布runbook", "回滚smoke")
        role = "服务启动/重启/发布运维执行位"
        scope = "专项负责 clitools-image-platform / 18877 本机服务启动、停止、重启、service monitor 接入、状态核验、日志回滚、smoke 执行和发布运维回执。"
        policy = "服务启动、重启、service monitor、健康检查、发布 runbook 和 smoke 验收优先派给该 Agent；没有 action_scope 时只做只读核验和 runbook 准备。"
        tags.extend(["image_platform", "service_ops", "service_hub", "restart_guard", "smoke"])
    elif _has_any(text, ["项目经理", "总控"]):
        add("总控门禁", "批次收口", "跨通道协调")
        role = "审核或门禁位"
        scope = "负责启动审查、边界冻结、跨板块协调、最终验收和收口裁决。"
        policy = "只处理管理门禁与收口，不替代执行位长期实现。"
        tags.extend(["management_gate", "acceptance_owner"])
    elif _has_any(text, ["架构"]):
        add("架构复核", "技术边界", "接口契约门禁")
        role = "审核或门禁位"
        scope = "负责技术路线、边界、兼容性和高风险改动门禁。"
        policy = "先给架构结论，再由对应业务执行位落地。"
        tags.extend(["architecture_gate", "contract_gate"])
    elif _has_any(text, ["测试", "验收", "冒烟"]):
        add("测试验收", "回归验证", "发布前放行")
        role = "验收位"
        scope = "负责专项验收、最小回归、live smoke 和通过/不通过裁决。"
        policy = "只按冻结范围验收；失败时只上抛单一主阻塞。"
        tags.extend(["qa", "smoke"])
    elif _has_any(text, ["用户镜像", "商业化判断", "项目安全判断", "宣传口径"]):
        add("用户视角复看", "业务判断", "价值与风险审查")
        role = "审核或门禁位"
        scope = "负责用户原始意见对账、价值判断、业务可理解性与风险复看。"
        policy = "用于业务复看与质疑，不替代产品或开发执行位。"
        tags.extend(["user_review", "business_review"])
    elif _has_any(channel, ["业务规划"]) and _has_any(agent, ["业务专家"]):
        add("业务目标规划", "用户场景分析", "需求拆解", "验收口径", "路线规划", "Demo叙事")
        role = "主负责位" if is_primary else "审核或门禁位"
        scope = "负责业务目标、用户场景、需求拆解、验收口径、路线规划和 Demo 叙事，不替代研发执行位。"
        policy = "用户反馈、需求澄清、路线取舍和验收口径优先派给该 Agent；需要实现时由总控再拆派执行通道。"
        tags.extend(["business_planning", "requirements", "acceptance_criteria", "demo_narrative"])
    elif _has_any(text, ["业务专家", "舆情分析师"]):
        add("政务舆情表达", "业务判断口径", "风险口径审核", "材料表达审核")
        role = "审核或门禁位"
        scope = "负责政务舆情分析师视角的业务表达、风险口径和材料表达审核。"
        policy = "涉及业务判断、风险表述和对外材料口径时优先复核，不替代研发执行位。"
        tags.extend(["public_opinion_expert", "business_review", "risk_wording"])
    elif _has_any(text, ["平台能力", "能力编排"]):
        add("平台能力服务化", "CLI工具化", "Agent工具调用", "能力接口契约")
        role = "执行位"
        scope = "负责平台能力服务化、CLI 化、能力制作维护和 Agent 工具调用支撑。"
        policy = "能力制作与工具调用落地优先派发；接口边界和高风险变更先经架构门禁。"
        tags.extend(["platform_capability", "cli_tooling", "agent_tools"])
    elif _has_any(text, ["视觉设计"]):
        add("视觉设计", "样式基线", "视觉一致性")
        role = "视觉审核位"
        scope = "负责视觉语言、样式基线、信息密度和页面观感审核。"
        policy = "涉及页面审美、设计系统或视觉跑偏时启用。"
        tags.extend(["visual_review", "style_baseline"])
    elif _has_any(text, ["产品-知识体系", "知识体系管理", "知识管理", "沉淀管理", "工作知识"]):
        add("知识体系管理", "沉淀索引", "方法论抽取", "工作知识复用")
        role = "主负责位" if channel.startswith("辅助04") else "执行位"
        scope = "负责辅助04产品知识、沉淀索引、方法论抽取与工作知识复用口径。"
        policy = "知识沉淀、方法复用和跨板块学习入口优先派给该 Agent。"
        tags.extend(["knowledge_system", "sedimentation", "methodology"])
    elif _has_any(text, ["产品-任务", "任务板块"]):
        add("任务业务产品", "任务详情", "任务首页", "责任位展示", "任务创建自动化")
        role = "主负责位"
        scope = "负责任务业务方案、任务详情标准、任务首页、责任位和任务创建口径。"
        policy = "任务类需求先找该 Agent 主责，再按前端/后端/QA补执行位。"
        tags.extend(["product_task", "task_owner"])
    elif _has_any(text, ["服务开发-任务维度", "后端-任务", "任务维度运行时"]):
        add("任务运行时", "任务接口", "任务责任位读链")
        role = "执行位"
        scope = "负责任务相关运行时、任务接口、任务责任位读取与后端协同。"
        policy = "任务后端问题固定优先派发。"
        tags.extend(["backend_task", "task_runtime"])
    elif _has_any(text, ["服务开发-分享协同", "后端-分享", "分享协同运行时"]):
        add("分享运行时", "share-scoped网关", "LAN发布边界")
        role = "执行位"
        scope = "负责 share_space、share-scoped 网关、LAN访问和分享发布边界。"
        policy = "分享/LAN 后端问题固定优先派发。"
        tags.extend(["backend_share", "share_gateway"])
    elif _has_any(text, ["服务开发-通讯", "服务开发-消息", "后端-通讯", "通讯能力开发"]):
        add("通讯运行时", "announce回执", "消息发送链")
        role = "执行位"
        scope = "负责 announce、callback、消息/会话通讯运行时。"
        policy = "通讯协议与回执链路问题优先派发。"
        tags.extend(["backend_message", "announce"])
    elif _has_any(text, ["远程协作", "共享", "分享"]):
        add("共享协作产品", "外部协作", "share-mode", "LAN分享")
        role = "主负责位" if channel.startswith("辅助04") else "执行位"
        scope = "负责共享空间、受限分享、LAN分享和外部协作链路。"
        policy = "分享业务先按产品/前端/后端分享协同三段拆派。"
        tags.extend(["share_collab", "lan_share"])
    elif _has_any(text, ["产品-项目", "项目维度", "项目板块", "项目和结构"]):
        add("项目首页", "项目配置", "项目卡片", "项目结构")
        role = "主负责位" if channel.startswith("辅助04") else "执行位"
        scope = "负责项目首页、项目卡、项目配置入口和项目结构相关体验。"
        policy = "项目页问题优先派给项目维度 Agent，不回落给通道主会话。"
        tags.extend(["project_surface", "overview"])
    elif _has_any(text, ["产品-通讯", "通讯能力", "消息对话", "对话管理"]):
        add("消息对话", "会话体验", "提及协作", "消息附件")
        role = "主负责位" if channel.startswith("辅助04") else "执行位"
        scope = "负责消息、会话、提及、附件展示与通讯链路体验。"
        policy = "消息/会话体验优先派给通讯能力 Agent。"
        tags.extend(["conversation", "message"])
    elif _has_any(text, ["前端-任务"]):
        add("任务页前端", "任务详情前端", "任务列表前端")
        role = "执行位"
        scope = "负责任务页、任务详情、任务列表、任务首页等前端实现。"
        policy = "任务前端实现固定优先派发，不因前端主会话在线而改派。"
        tags.extend(["frontend_task", "task_ui"])
    elif _has_any(text, ["前端-样式", "前端规范", "样式与规范"]):
        add("前端样式规范", "设计系统落地", "样式基座")
        role = "视觉审核位"
        scope = "负责样式规范、设计系统、CSS基线与视觉一致性，不默认承接任务业务实现。"
        policy = "仅在样式/规范/视觉一致性任务中作为执行或审核位。"
        tags.extend(["frontend_style", "style_baseline"])
    elif _has_any(text, ["前端-Agent", "Agent"]):
        add("Agent列表", "Agent身份展示", "Agent能力面板")
        role = "执行位"
        scope = "负责 Agent 列表、Agent 能力、身份展示和 Agent 侧栏体验。"
        policy = "Agent 展示类问题优先派给该 Agent。"
        tags.extend(["agent_ui", "agent_identity"])
    elif _has_any(text, ["页面框架"]):
        add("页面框架", "主壳体", "布局结构")
        role = "执行位"
        scope = "负责页面壳体、布局框架、导航结构和跨页面接线。"
        policy = "结构层任务优先派发；具体业务细节仍回业务 Agent。"
        tags.extend(["page_shell", "layout"])
    elif _has_any(text, ["界面问题修复", "问题修复"]):
        add("前端缺陷修复", "上线后小修", "界面异常")
        role = "执行位"
        scope = "负责已定位的界面问题、上线后小修和低风险前端缺陷。"
        policy = "只承接明确缺陷；新功能仍按业务板块派发。"
        tags.extend(["ui_bugfix"])
    elif _has_any(text, ["执行调度"]):
        add("执行调度", "并发队列", "run调度")
        role = "执行位"
        scope = "负责 CCB 调度、队列、同 session 串行与 run 执行策略。"
        policy = "调度/并发/执行链问题固定派发。"
        tags.extend(["scheduler", "run_queue"])
    elif _has_any(text, ["会话读链"]):
        add("会话读链", "sessions接口", "历史轻读")
        role = "执行位"
        scope = "负责 /api/sessions、会话详情、历史轻读和读链预算。"
        policy = "会话读取性能与语义问题固定派发。"
        tags.extend(["session_read", "history_light_read"])
    elif _has_any(text, ["启动发布", "环境边界"]):
        add("启动发布", "环境边界", "service monitor", "LAN绑定")
        role = "执行位"
        scope = "负责 run_local、service manager、bind/publicOrigin、service monitor 与本机/远端边界。"
        policy = "启动链、发布链和环境边界问题固定派发。"
        tags.extend(["startup", "release", "environment"])
    elif _has_any(text, ["运行时巡检", "诊断", "异常修复", "会话健康"]):
        add("运行巡检", "性能诊断", "异常告警", "会话健康")
        role = "执行位"
        scope = "负责运行巡检、性能诊断、异常收敛、会话健康与 live 证据回收。"
        policy = "生产异常先由运维诊断定位，再按业务责任位派发修复。"
        tags.extend(["ops_diagnosis", "health"])
    elif _has_any(text, ["数据治理", "契约", "消息监控", "任务监控", "性能治理"]):
        add("数据治理", "契约校验", "样本修复", "监控治理")
        role = "执行位"
        scope = "负责数据契约、历史样本治理、字段校验和治理口径。"
        policy = "真源/字段/历史样本问题优先派发。"
        tags.extend(["data_governance", "contract"])
    elif _has_any(text, ["内容治理", "结构治理", "项目结构", "主线编排", "通讯录", "通道治理", "Agent补建", "Agent级"]):
        add("结构治理", "目录规范", "通讯录维护", "Agent补建")
        role = "执行位"
        scope = "负责项目结构、目录规范、通讯录、Agent补建和治理编排。"
        policy = "结构/通讯录/Agent治理任务优先派发。"
        tags.extend(["structure_governance", "agent_registry"])
    elif _has_any(text, ["技能治理", "skills"]):
        add("技能治理", "协作规范", "模板升级")
        role = "执行位"
        scope = "负责项目 skills、协作模板、提示词规范和技能治理。"
        policy = "协作规范或技能升级问题优先派发。"
        tags.extend(["skills", "workflow"])
    elif _has_any(text, ["仓库", "Git", "开源"]):
        add("仓库管理", "开源同步", "分支治理")
        role = "执行位"
        scope = "负责 Git、本地/远程仓库、开源同步和分支治理。"
        policy = "仓库和发布分支问题优先派发。"
        tags.extend(["git", "repo"])
    elif _has_any(text, ["服务管理", "服务发布", "服务启动", "服务重启", "服务注册", "service monitor", "本机服务监控台"]):
        add("服务发布", "服务启动", "服务重启", "服务注册", "健康核查", "service monitor")
        role = "主负责位"
        scope = "负责项目服务启动、重启协调、健康核查、服务入口注册与本机服务监控台映射维护。"
        policy = "服务启动/重启/注册/service monitor 事项优先派发；生产重启仍需用户或总控门禁放行。"
        tags.extend(["service_management", "service_hub", "startup_restart"])
    elif _has_any(text, ["临时兜底", "复杂任务"]):
        add("临时兜底", "跨板块短期收口")
        role = "临时兜底位"
        scope = "仅用于跨板块短期救火或明确无法归口的复杂任务。"
        policy = "不得作为长期固定责任板块；使用前必须说明为何不能归口。"
        tags.extend(["fallback_only"])

    if not domains:
        add(channel.replace("（", "-").split("-")[0] or "通用协作")
        if is_primary:
            role = "主负责位"
            scope = "负责所在通道主线承接、协调和收口；不默认承担所有并行执行。"
        tags.append("channel_default")

    return {
        "agent_name": agent,
        "agent_alias": agent,
        "business_domains": domains,
        "dispatch_role": role,
        "dispatch_scope": scope,
        "dispatch_policy": policy,
        "routing_tags": tags,
        "busy_check_required": True,
    }


def _apply_dispatch_profile_overrides(
    profile: dict[str, Any],
    cfg_row: dict[str, Any],
    *,
    agent_name: str = "",
) -> dict[str, Any]:
    """Apply optional channel/session config metadata to generated dispatch profile."""
    if not isinstance(cfg_row, dict):
        return profile

    source = cfg_row
    agent_key = _safe_text(agent_name)
    agent_profiles = cfg_row.get("agent_dispatch_profiles") or cfg_row.get("agentDispatchProfiles")
    if agent_key and isinstance(agent_profiles, list):
        for item in agent_profiles:
            if not isinstance(item, dict):
                continue
            names = _safe_text_list(
                item.get("agent_names")
                or item.get("agentNames")
                or [
                    item.get("agent_name"),
                    item.get("agentName"),
                    item.get("agent_alias"),
                    item.get("agentAlias"),
                    item.get("display_name"),
                    item.get("displayName"),
                    item.get("alias"),
                ]
            )
            if agent_key in names:
                source = item
                break

    domains = _safe_text_list(source.get("business_domains") or source.get("businessDomains"))
    if domains:
        profile["business_domains"] = domains
    role = _safe_text(source.get("dispatch_role") or source.get("dispatchRole"))
    if role:
        profile["dispatch_role"] = role
    scope = _safe_text(source.get("dispatch_scope") or source.get("dispatchScope"))
    if scope:
        profile["dispatch_scope"] = scope
    policy = _safe_text(source.get("dispatch_policy") or source.get("dispatchPolicy"))
    if policy:
        profile["dispatch_policy"] = policy
    tags = _safe_text_list(source.get("routing_tags") or source.get("routingTags"))
    if tags:
        profile["routing_tags"] = tags
    busy_raw = source.get("busy_check_required")
    if busy_raw is None:
        busy_raw = source.get("busyCheckRequired")
    if busy_raw is not None:
        profile["busy_check_required"] = _safe_bool(busy_raw, default=True)
    return profile


def _build_business_dispatch_index(all_agents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    domain_map: dict[str, list[dict[str, Any]]] = {}
    for agent in all_agents:
        if _safe_text(agent.get("status")) != "active":
            continue
        for domain in agent.get("business_domains") if isinstance(agent.get("business_domains"), list) else []:
            key = _safe_text(domain)
            if not key:
                continue
            domain_map.setdefault(key, []).append(
                {
                    "channel_name": agent.get("channel_name"),
                    "agent_name": agent.get("agent_name") or agent.get("display_name"),
                    "session_id": agent.get("session_id"),
                    "dispatch_role": agent.get("dispatch_role"),
                    "dispatch_scope": agent.get("dispatch_scope"),
                    "is_primary": bool(agent.get("is_primary")),
                    "cli_type": agent.get("cli_type"),
                }
            )

    preferred_order = {
        "任务业务产品": 0,
        "任务页前端": 1,
        "任务运行时": 2,
        "共享协作产品": 3,
        "分享运行时": 4,
        "消息对话": 5,
        "通讯运行时": 6,
        "项目首页": 7,
        "前端样式规范": 8,
        "测试验收": 9,
        "架构复核": 10,
        "总控门禁": 11,
    }
    rows: list[dict[str, Any]] = []
    for domain, agents in domain_map.items():
        agents = sorted(
            agents,
            key=lambda row: (
                0 if not bool(row.get("is_primary")) else 1,
                _safe_text(row.get("channel_name")),
                _safe_text(row.get("agent_name")),
            ),
        )
        rows.append({"business_domain": domain, "agents": agents})
    return sorted(rows, key=lambda row: (preferred_order.get(_safe_text(row.get("business_domain")), 99), _safe_text(row.get("business_domain"))))


def _normalize_session_rows(rows: Any) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    normalized: list[dict[str, Any]] = []
    for it in rows:
        if not isinstance(it, dict):
            continue
        sid = _safe_text(it.get("sessionId") or it.get("session_id") or it.get("id"))
        if not sid:
            continue
        normalized.append(
            {
                "session_id": sid,
                "desc": _safe_text(it.get("desc")),
                "model": _safe_text(it.get("model")),
                "cli_type": _safe_text(it.get("cli_type") or it.get("cliType")),
            }
        )
    return normalized


def _normalize_structure_layer(value: Any) -> str:
    layer = _safe_text(value)
    return layer or "未分层"


def _channel_display_state(*, startup_ready: bool, structure_layer: str, requires_primary: bool) -> str:
    if startup_ready:
        return "ready"
    if structure_layer == "历史壳":
        return "shell"
    if structure_layer == "待启用通道":
        return "standby"
    if structure_layer == "低频通道" and not requires_primary:
        return "idle"
    return "pending"


def _render_view(payload: dict[str, Any]) -> str:
    project = payload.get("project") if isinstance(payload.get("project"), dict) else {}
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    channels = payload.get("channels") if isinstance(payload.get("channels"), list) else []

    lines: list[str] = []
    lines.append("# 协作通讯录视图（CCR v1）")
    lines.append("")
    lines.append(f"- generated_at: `{payload.get('generated_at')}`")
    lines.append(f"- project_id: `{project.get('project_id', '-')}`")
    lines.append(f"- project_name: `{project.get('project_name', '-')}`")
    lines.append(f"- source: `{payload.get('source', '-')}`")
    lines.append("- detailed_dispatch: [`collab-registry.dispatch.view.md`](collab-registry.dispatch.view.md)")
    lines.append("")
    lines.append("## 汇总")
    lines.append(f"- 通道总数: `{summary.get('channel_count', 0)}`")
    lines.append(f"- Agent 总数: `{summary.get('agent_count', 0)}`")
    lines.append(f"- 已具备主会话: `{summary.get('with_primary_session', 0)}`")
    lines.append(f"- 缺少主会话: `{summary.get('without_primary_session', 0)}`")
    formal_dispatch_count = int(summary.get("formal_dispatch_channel_count") or 0)
    lines.append(f"- 正式派发通道: `{formal_dispatch_count}`")
    lines.append(f"- 可路由业务域: `{summary.get('business_domain_count', 0)}`")
    layer_counts = summary.get("structure_layer_counts") if isinstance(summary.get("structure_layer_counts"), dict) else {}
    if layer_counts:
        lines.append("")
        lines.append("## 结构分层")
        for layer, count in layer_counts.items():
            lines.append(f"- {layer}: `{int(count or 0)}`")
    lines.append("")
    lines.append("## 通道清单")
    lines.append("| 通道 | 结构层级 | 角色 | 正式派发 | 主会话名称 | 主会话 | CLI | 候选会话数 | 状态 |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | ---: | --- |")
    for it in channels:
        if not isinstance(it, dict):
            continue
        lines.append(
            "| {channel} | {layer} | {role} | {dispatch} | {alias} | `{sid}` | `{cli}` | {cnt} | {status} |".format(
                channel=_safe_text(it.get("channel_name")) or "-",
                layer=_safe_text(it.get("structure_layer")) or "-",
                role=_safe_text(it.get("channel_role")) or "-",
                dispatch="是" if bool(it.get("formal_dispatch_entry")) else "否",
                alias=_safe_text(it.get("primary_session_alias")) or "-",
                sid=_safe_text(it.get("primary_session_id")) or "-",
                cli=_safe_text(it.get("primary_cli_type")) or "-",
                cnt=int(it.get("session_candidates_count") or 0),
                status=_safe_text(it.get("display_state")) or ("ready" if it.get("startup_ready") else "pending"),
            )
        )
    lines.append("")
    missing = summary.get("missing_required_primary_channels")
    if isinstance(missing, list) and missing:
        lines.append("## 需补主会话（现役/低频）")
        for name in missing:
            lines.append(f"- `{_safe_text(name)}` 缺少主会话，请先绑定后再执行通道派发。")
        lines.append("")
    lines.append("## 通道内 Agent 快速清单")
    for it in channels:
        if not isinstance(it, dict):
            continue
        channel_name = _safe_text(it.get("channel_name")) or "-"
        lines.append(f"### {channel_name}")
        lines.append("| Agent | session_id | 主/子 | 状态 | CLI |")
        lines.append("| --- | --- | --- | --- | --- |")
        candidates = it.get("session_candidates") if isinstance(it.get("session_candidates"), list) else []
        if not candidates:
            lines.append("| - | - | - | - | - |")
        for cand in candidates:
            if not isinstance(cand, dict):
                continue
            kind = "primary" if bool(cand.get("is_primary")) else (_safe_text(cand.get("session_role")) or "candidate")
            lines.append(
                "| {agent} | `{sid}` | {kind} | `{status}` | `{cli}` |".format(
                    agent=_safe_text(cand.get("display_name")) or _safe_text(cand.get("desc")) or "-",
                    sid=_safe_text(cand.get("session_id")) or "-",
                    kind=kind,
                    status=_safe_text(cand.get("status")) or "-",
                    cli=_safe_text(cand.get("cli_type")) or "-",
                )
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _render_dispatch_view(payload: dict[str, Any]) -> str:
    project = payload.get("project") if isinstance(payload.get("project"), dict) else {}
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    channels = payload.get("channels") if isinstance(payload.get("channels"), list) else []
    business_dispatch_index = (
        payload.get("business_dispatch_index")
        if isinstance(payload.get("business_dispatch_index"), list)
        else []
    )
    playbook = (
        payload.get("communication_playbook")
        if isinstance(payload.get("communication_playbook"), dict)
        else {}
    )

    lines: list[str] = []
    lines.append("# 协作通讯录分工索引（CCR v1）")
    lines.append("")
    lines.append(f"- generated_at: `{payload.get('generated_at')}`")
    lines.append(f"- project_id: `{project.get('project_id', '-')}`")
    lines.append(f"- project_name: `{project.get('project_name', '-')}`")
    lines.append(f"- source: `{payload.get('source', '-')}`")
    lines.append("- quick_directory: [`collab-registry.view.md`](collab-registry.view.md)")
    lines.append("")
    lines.append("## 汇总")
    lines.append(f"- 通道总数: `{summary.get('channel_count', 0)}`")
    lines.append(f"- Agent 总数: `{summary.get('agent_count', 0)}`")
    lines.append(f"- 可路由业务域: `{summary.get('business_domain_count', 0)}`")
    lines.append("")
    lines.append("## 使用原则")
    lines.append("- 先按业务域匹配，再看 Agent 名称职责、忙闲状态和任务连续性。")
    lines.append("- 主 Agent 负责通道主线承接、协调和收口，不默认承担所有并行执行。")
    lines.append("- 服务启动、重启、注册和健康核查事项优先路由到服务管理责任位。")
    lines.append("")
    if business_dispatch_index:
        lines.append("## Agent 级业务分工索引")
        lines.append("")
        lines.append("派发顺序固定为：业务域匹配 -> Agent 名称职责 -> 忙闲检查 -> 任务连续性。不要因为通道主 Agent 在线就默认派给主 Agent。")
        lines.append("")
        lines.append("| 业务域 | 可用 Agent（最多展示 4 个） | 派发说明 |")
        lines.append("| --- | --- | --- |")
        for row in business_dispatch_index:
            if not isinstance(row, dict):
                continue
            agents = row.get("agents") if isinstance(row.get("agents"), list) else []
            rendered_agents: list[str] = []
            scopes: list[str] = []
            for agent in agents[:4]:
                if not isinstance(agent, dict):
                    continue
                name = _safe_text(agent.get("agent_name")) or "-"
                channel = _safe_text(agent.get("channel_name")) or "-"
                sid = _safe_text(agent.get("session_id")) or "-"
                role = _safe_text(agent.get("dispatch_role")) or "-"
                primary = " primary" if bool(agent.get("is_primary")) else ""
                rendered_agents.append(f"{name}（{channel} / `{sid}` / {role}{primary}）")
                scope = _safe_text(agent.get("dispatch_scope"))
                if scope and scope not in scopes:
                    scopes.append(scope)
            if len(agents) > 4:
                rendered_agents.append(f"...另 {len(agents) - 4} 个")
            lines.append(
                "| {domain} | {agents} | {scope} |".format(
                    domain=_safe_text(row.get("business_domain")) or "-",
                    agents="<br>".join(rendered_agents) if rendered_agents else "-",
                    scope="<br>".join(scopes[:2]) if scopes else "按 Agent 职责与忙闲分派。",
                )
            )
        lines.append("")
    if playbook:
        lines.append("## 沟通使用方法（内置）")
        routing_baseline = playbook.get("routing_baseline") if isinstance(playbook.get("routing_baseline"), dict) else {}
        if routing_baseline:
            lines.append("### 新版发信口径（Agent级）")
            sender_identity = routing_baseline.get("sender_identity") if isinstance(routing_baseline.get("sender_identity"), list) else []
            if sender_identity:
                lines.append("- 发信时必须显式带上以下身份字段：")
                for item in sender_identity:
                    lines.append(f"  - `{_safe_text(item)}`")
            message_minimum_fields = routing_baseline.get("message_minimum_fields") if isinstance(routing_baseline.get("message_minimum_fields"), list) else []
            if message_minimum_fields:
                lines.append("- 最小发信字段：")
                for item in message_minimum_fields:
                    lines.append(f"  - `{_safe_text(item)}`")
            reply_priority = routing_baseline.get("reply_priority") if isinstance(routing_baseline.get("reply_priority"), list) else []
            if reply_priority:
                lines.append("- 默认回执优先级：")
                for idx, item in enumerate(reply_priority, start=1):
                    lines.append(f"  - `{idx}. {_safe_text(item)}`")
            lines.append("")
        interaction_modes = (
            playbook.get("interaction_modes")
            if isinstance(playbook.get("interaction_modes"), list)
            else []
        )
        if interaction_modes:
            lines.append("### 交互模式")
            for row in interaction_modes:
                if not isinstance(row, dict):
                    continue
                lines.append(
                    "- `{name}`：{when}；回执要求=`{receipt}`".format(
                        name=_safe_text(row.get("name")) or "-",
                        when=_safe_text(row.get("when_to_use")) or "-",
                        receipt="required" if bool(row.get("receipt_required")) else "not_required",
                    )
                )
            lines.append("")
        contact_types = playbook.get("contact_types") if isinstance(playbook.get("contact_types"), list) else []
        if contact_types:
            lines.append("### 联系类型")
            for row in contact_types:
                if not isinstance(row, dict):
                    continue
                lines.append(
                    "- `{name}`：{when}；可见性=`{visible}`".format(
                        name=_safe_text(row.get("name")) or "-",
                        when=_safe_text(row.get("when_to_use")) or "-",
                        visible=_safe_text(row.get("visible_in_channel_chat")) or "-",
                    )
                )
        templates = playbook.get("templates") if isinstance(playbook.get("templates"), list) else []
        if templates:
            lines.append("")
            lines.append("### 模板快照")
            for row in templates:
                if not isinstance(row, dict):
                    continue
                lines.append(f"- `{_safe_text(row.get('id'))}`：{_safe_text(row.get('title'))}")
        lines.append("")
        lines.append("### 推荐技能")
        for sk in (playbook.get("recommended_skills") or []):
            lines.append(f"- `{_safe_text(sk)}`")
        lines.append("")
    lines.append("## 通道内 Agent 详细分工")
    for it in channels:
        if not isinstance(it, dict):
            continue
        channel_name = _safe_text(it.get("channel_name")) or "-"
        lines.append(f"### {channel_name}")
        lines.append(
            "- 结构层级：`{layer}`；正式派发：`{dispatch}`；主会话要求：`{required}`".format(
                layer=_safe_text(it.get("structure_layer")) or "-",
                dispatch="是" if bool(it.get("formal_dispatch_entry")) else "否",
                required="是" if bool(it.get("requires_primary")) else "否",
            )
        )
        lines.append("| Agent | session_id | 主/候选 | 状态 | CLI | 责任位 | 业务域 | 派发范围 | 派发说明 |")
        lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
        candidates = it.get("session_candidates") if isinstance(it.get("session_candidates"), list) else []
        if not candidates:
            lines.append("| - | - | - | - | - | - | - | - | - |")
        for cand in candidates:
            if not isinstance(cand, dict):
                continue
            domains = cand.get("business_domains") if isinstance(cand.get("business_domains"), list) else []
            lines.append(
                "| {agent} | `{sid}` | {kind} | `{status}` | `{cli}` | {role} | {domains} | {scope} | {policy} |".format(
                    agent=_safe_text(cand.get("display_name")) or _safe_text(cand.get("desc")) or "-",
                    sid=_safe_text(cand.get("session_id")) or "-",
                    kind="primary" if bool(cand.get("is_primary")) else "candidate",
                    status=_safe_text(cand.get("status")) or "-",
                    cli=_safe_text(cand.get("cli_type")) or "-",
                    role=_safe_text(cand.get("dispatch_role")) or "-",
                    domains="<br>".join(_safe_text(item) for item in domains if _safe_text(item)) or "-",
                    scope=_safe_text(cand.get("dispatch_scope")) or "-",
                    policy=_safe_text(cand.get("dispatch_policy")) or "-",
                )
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _html_escape(text: Any) -> str:
    raw = _safe_text(text)
    return (
        raw.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _render_agent_directory_html(payload: dict[str, Any]) -> str:
    project = payload.get("project") if isinstance(payload.get("project"), dict) else {}
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    channels = payload.get("channels") if isinstance(payload.get("channels"), list) else []
    session_store_label = _html_escape(project.get("session_store_path") or payload.get("source"))
    cards: list[str] = []
    for channel in channels:
        if not isinstance(channel, dict):
            continue
        channel_name = _html_escape(channel.get("channel_name"))
        channel_role = _html_escape(channel.get("channel_role"))
        channel_desc = _html_escape(channel.get("channel_desc"))
        structure_layer = _html_escape(channel.get("structure_layer"))
        structure_layer_label = structure_layer or "未分层"
        primary_sid = _safe_text(channel.get("primary_session_id"))
        candidates = channel.get("session_candidates") if isinstance(channel.get("session_candidates"), list) else []
        agent_items: list[str] = []
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            session_id = _html_escape(candidate.get("session_id"))
            display_name = _html_escape(candidate.get("display_name") or candidate.get("desc"))
            cli_type = _html_escape(candidate.get("cli_type") or "codex")
            model = _html_escape(candidate.get("model"))
            environment = _html_escape(candidate.get("environment"))
            branch = _html_escape(candidate.get("branch"))
            workdir = _html_escape(candidate.get("workdir"))
            session_role = _html_escape(candidate.get("session_role"))
            business_domains = candidate.get("business_domains") if isinstance(candidate.get("business_domains"), list) else []
            business_domains_text = _html_escape(" / ".join(_safe_text(item) for item in business_domains if _safe_text(item)))
            dispatch_role = _html_escape(candidate.get("dispatch_role"))
            dispatch_scope = _html_escape(candidate.get("dispatch_scope"))
            badges = [
                '<span class="badge primary">主会话</span>' if _safe_text(candidate.get("session_id")) == primary_sid else "",
                f'<span class="badge">{cli_type or "codex"}</span>',
                f'<span class="badge">{dispatch_role}</span>' if dispatch_role else "",
                f'<span class="badge">{environment}</span>' if environment else "",
                f'<span class="badge">{session_role}</span>' if session_role else "",
            ]
            meta_items = [
                f"<div><span>session_id</span><code>{session_id}</code></div>",
                f"<div><span>业务域</span><span>{business_domains_text or '-'}</span></div>",
                f"<div><span>责任位</span><span>{dispatch_role or '-'}</span></div>",
                f"<div><span>派发范围</span><span>{dispatch_scope or '-'}</span></div>",
                f"<div><span>model</span><span>{model or '-'}</span></div>",
                f"<div><span>branch</span><span>{branch or '-'}</span></div>",
                f"<div><span>workdir</span><code>{workdir or '-'}</code></div>",
            ]
            agent_items.append(
                """
                <article class="agent">
                  <div class="agent-head">
                    <h3>{display_name}</h3>
                    <div class="badges">{badges}</div>
                  </div>
                  <div class="meta">
                    {meta}
                  </div>
                </article>
                """.format(display_name=display_name, badges="".join([x for x in badges if x]), meta="".join(meta_items))
            )
        cards.append(
            """
            <section class="channel-card">
              <div class="channel-head">
                <div>
                  <h2>{channel_name}</h2>
                  <p>{channel_desc}</p>
                </div>
                <div class="channel-side">
                  <span class="pill">{structure_layer}</span>
                  <span class="pill">{channel_role}</span>
                  <span class="pill">{dispatch}</span>
                  <span class="pill">{count} agents</span>
                </div>
              </div>
              <div class="agents">{agent_items}</div>
            </section>
            """.format(
                channel_name=channel_name,
                channel_desc=channel_desc or "未填写通道说明",
                structure_layer=structure_layer_label,
                channel_role=channel_role or "other",
                dispatch="正式派发" if bool(channel.get("formal_dispatch_entry")) else "非默认派发",
                count=len(candidates),
                agent_items="".join(agent_items),
            )
        )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_html_escape(project.get("project_name"))} - 通讯录 Agent 视图</title>
  <style>
    :root {{
      --bg: #f5f7fb;
      --card: rgba(255,255,255,.88);
      --line: #d8dfeb;
      --text: #1e2a36;
      --muted: #5f7083;
      --brand: #1f6feb;
      --accent: #0f766e;
      --warm: #a16207;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
      color: var(--text);
      background:
        radial-gradient(circle at top left, rgba(31,111,235,.16), transparent 28%),
        radial-gradient(circle at bottom right, rgba(15,118,110,.14), transparent 24%),
        var(--bg);
    }}
    .page {{
      width: min(1480px, calc(100vw - 32px));
      margin: 0 auto;
      padding: 28px 0 56px;
    }}
    .hero {{
      display: grid;
      grid-template-columns: 1.4fr .9fr;
      gap: 16px;
      margin-bottom: 20px;
    }}
    .hero-card, .channel-card {{
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 20px;
      box-shadow: 0 16px 40px rgba(15, 23, 42, .06);
      backdrop-filter: blur(10px);
    }}
    .hero-card {{
      padding: 22px 24px;
    }}
    h1, h2, h3, p {{ margin: 0; }}
    h1 {{ font-size: 28px; line-height: 1.2; }}
    .sub {{
      margin-top: 10px;
      color: var(--muted);
      line-height: 1.6;
      font-size: 14px;
    }}
    .stats {{
      display: grid;
      grid-template-columns: repeat(5, 1fr);
      gap: 10px;
      margin-top: 18px;
    }}
    .stat {{
      padding: 14px;
      border-radius: 16px;
      background: rgba(255,255,255,.72);
      border: 1px solid var(--line);
    }}
    .stat .k {{ font-size: 12px; color: var(--muted); }}
    .stat .v {{ margin-top: 6px; font-size: 24px; font-weight: 700; }}
    .hero-note {{
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      padding: 22px 24px;
    }}
    .hero-note ul {{
      margin: 12px 0 0;
      padding-left: 18px;
      color: var(--muted);
      line-height: 1.7;
    }}
    .grid {{
      display: grid;
      gap: 16px;
    }}
    .channel-card {{
      padding: 18px;
    }}
    .channel-head {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: flex-start;
      margin-bottom: 14px;
    }}
    .channel-head p {{
      margin-top: 8px;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.6;
    }}
    .channel-side {{
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }}
    .pill, .badge {{
      display: inline-flex;
      align-items: center;
      border-radius: 999px;
      padding: 4px 10px;
      font-size: 12px;
      line-height: 1;
      border: 1px solid var(--line);
      background: #fff;
      color: var(--muted);
      white-space: nowrap;
    }}
    .badge.primary {{
      color: var(--brand);
      border-color: rgba(31,111,235,.25);
      background: rgba(31,111,235,.08);
    }}
    .agents {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(290px, 1fr));
      gap: 12px;
    }}
    .agent {{
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 14px;
      background: rgba(255,255,255,.72);
    }}
    .agent-head {{
      display: flex;
      justify-content: space-between;
      gap: 8px;
      align-items: flex-start;
      margin-bottom: 12px;
    }}
    .agent-head h3 {{
      font-size: 16px;
      line-height: 1.4;
    }}
    .badges {{
      display: flex;
      gap: 6px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }}
    .meta {{
      display: grid;
      gap: 6px;
      font-size: 12px;
      color: var(--muted);
    }}
    .meta div {{
      display: grid;
      grid-template-columns: 72px 1fr;
      gap: 8px;
      align-items: start;
    }}
    code {{
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 11px;
      word-break: break-all;
      color: #334155;
    }}
    @media (max-width: 900px) {{
      .hero {{ grid-template-columns: 1fr; }}
      .stats {{ grid-template-columns: repeat(2, 1fr); }}
      .channel-head {{ flex-direction: column; }}
      .channel-side {{ justify-content: flex-start; }}
    }}
  </style>
</head>
<body>
  <main class="page">
    <section class="hero">
      <div class="hero-card">
        <h1>{_html_escape(project.get("project_name"))} Agent 通讯录</h1>
        <p class="sub">当前页直接从 stable 会话真源派生，展示每个通道下所有有效 Agent，会比旧版“通道一条记录”更完整直观。</p>
        <div class="stats">
          <div class="stat"><div class="k">项目</div><div class="v">{_html_escape(project.get("project_id"))}</div></div>
          <div class="stat"><div class="k">通道数</div><div class="v">{int(summary.get("channel_count") or 0)}</div></div>
          <div class="stat"><div class="k">Agent 数</div><div class="v">{int(summary.get("agent_count") or 0)}</div></div>
          <div class="stat"><div class="k">业务域</div><div class="v">{int(summary.get("business_domain_count") or 0)}</div></div>
          <div class="stat"><div class="k">主会话齐备</div><div class="v">{int(summary.get("with_primary_session") or 0)}</div></div>
        </div>
      </div>
      <div class="hero-card hero-note">
        <div>
          <h2>当前口径</h2>
          <ul>
            <li>底层真源：{session_store_label}</li>
            <li>通讯录：派生层，保留主责入口与协作索引</li>
            <li>本页：把通讯录里的全部 Agent 平铺展示</li>
          </ul>
        </div>
        <p class="sub">生成时间：{_html_escape(payload.get("generated_at"))}</p>
      </div>
    </section>
    <section class="grid">
      {''.join(cards)}
    </section>
  </main>
</body>
</html>
"""


def _build_communication_playbook() -> dict[str, Any]:
    templates: list[dict[str, Any]] = [
        {
            "id": "announce_to_channel_brief",
            "title": "跨通道通知（写入通道聊天）",
            "interaction_mode": "task_with_receipt",
            "template": (
                "[来源通道: <channel>]\n"
                "[目标通道: <channel>]\n"
                "联系类型: announce_to_channel\n"
                "交互模式: task_with_receipt\n"
                "回执任务: <task_or_topic>\n"
                "本次目标: <一句话>\n"
                "需要对方: <单动作>\n"
                "预期结果: <可验收结果>\n"
                "证据字段: target_session_id=<...>; announce_run_id=<...>; visible_in_channel_chat=true\n"
                "非必要问题: <无/列点>"
            ),
        },
        {
            "id": "spawn_agent_internal_brief",
            "title": "内部子agent协作（不写入通道聊天）",
            "interaction_mode": "task_with_receipt",
            "template": (
                "[来源通道: <channel>]\n"
                "[目标通道: <channel>]\n"
                "联系类型: spawn_agent_internal\n"
                "交互模式: task_with_receipt\n"
                "回执任务: <task_or_topic>\n"
                "本次目标: <一句话>\n"
                "当前进展: <已完成<=3>\n"
                "证据字段: agent_ids=<...>; visible_in_channel_chat=false\n"
                "下一步/需确认: <一句话>"
            ),
        },
        {
            "id": "requirement_survey_request",
            "title": "需求调查征询（产品/规划）",
            "interaction_mode": "dialog_now",
            "template": (
                "[来源通道: <channel>]\n"
                "[目标通道: <channel>]\n"
                "联系类型: announce_to_channel\n"
                "交互模式: dialog_now\n"
                "议题: <需求标题>\n"
                "需要你提供:\n"
                "1) 最担心风险(1条)\n"
                "2) 建议动作(<=2条)\n"
                "3) 依赖/阻塞(无则写无)\n"
                "回执要求: 结论前置，最多8行。"
            ),
        },
        {
            "id": "notify_only_brief",
            "title": "纯通知（无需回执）",
            "interaction_mode": "notify_only",
            "template": (
                "[来源通道: <channel>]\n"
                "[目标通道: <channel>]\n"
                "联系类型: announce_to_channel\n"
                "交互模式: notify_only\n"
                "通知事项: <一句话>\n"
                "动作要求: 仅确认收到，无需回执。\n"
                "证据字段: target_session_id=<...>; announce_run_id=<...>; visible_in_channel_chat=true"
            ),
        },
    ]
    return {
        "version": 1,
        "goal": "减少跨通道沟通熵增，保证通知可见性与回执可验收。",
        "routing_baseline": {
            "sender_identity": [
                "当前发信Agent",
                "source_ref.project_id",
                "source_ref.channel_name",
                "source_ref.session_id",
                "source_ref.run_id",
                "callback_to.session_id",
            ],
            "message_minimum_fields": [
                "projectId",
                "channelName",
                "sessionId",
                "sender_type",
                "sender_name",
                "message",
            ],
            "reply_priority": [
                "callback_to.session_id",
                "source_ref.session_id",
                "目标通道主会话",
            ],
            "note": "source_ref/callback_to 属于消息时态字段，不写入通讯录静态真源；通讯录只负责提供 Agent/session 可寻址信息与使用口径。",
        },
        "interaction_modes": [
            {
                "name": "dialog_now",
                "when_to_use": "需要当场快速确认或讨论，优先短来回",
                "receipt_required": False,
                "expected_response_sla": "immediate",
            },
            {
                "name": "task_with_receipt",
                "when_to_use": "需要对方处理后提交结构化回执",
                "receipt_required": True,
                "expected_response_sla": "within_agreed_sla",
            },
            {
                "name": "notify_only",
                "when_to_use": "仅传达信息，不阻塞对方流程",
                "receipt_required": False,
                "expected_response_sla": "none",
            },
        ],
        "contact_types": [
            {
                "name": "announce_to_channel",
                "when_to_use": "需要正式通知目标通道并留下聊天记录时",
                "required_evidence": ["target_session_id", "announce_run_id"],
                "visible_in_channel_chat": "true",
            },
            {
                "name": "spawn_agent_internal",
                "when_to_use": "仅内部并行处理，不要求写入通道聊天时",
                "required_evidence": ["agent_ids"],
                "visible_in_channel_chat": "false",
            },
        ],
        "recommended_skills": [
            "project-startup-collab-suite",
            "webtag-ccb-bridge",
            "codex-agent-collaboration",
            "prototype-requirement-planning-flow",
        ],
        "templates": templates,
        "self_test_checklist": [
            "生成 registry/public-registry.v1.json、registry/public-registry.view.md 与 registry/public-registry.dispatch.view.md",
            "执行一次 dialog_now 并确认能当场回复",
            "执行一次 task_with_receipt 并确认有结构化回执",
            "执行一次 notify_only 并确认不要求回执",
            "执行一次 announce_to_channel 并确认 visible_in_channel_chat=true",
            "执行一次 spawn_agent_internal 并确认 visible_in_channel_chat=false",
            "回执中附 target_session_id/announce_run_id 或 agent_ids 证据字段",
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="生成项目协作通讯录（CCR v1）")
    ap.add_argument("--project-id", required=True, help="config.toml 中的项目 id")
    ap.add_argument("--config", default="config.toml", help="配置文件路径（默认: config.toml）")
    ap.add_argument("--workspace-root", default=".", help="工作区根目录（默认: 当前目录）")
    ap.add_argument("--session-json", default="", help="覆盖 session json 路径（可选）")
    ap.add_argument("--output", default="", help="输出 JSON 路径（可选）")
    ap.add_argument("--view-output", default="", help="输出 Markdown 视图路径（可选）")
    ap.add_argument("--dispatch-output", default="", help="输出按分工查询 Markdown 视图路径（可选）")
    ap.add_argument("--html-output", default="", help="输出 HTML 视图路径（可选）")
    ap.add_argument("--dry-run", action="store_true", help="仅打印，不落盘")
    args = ap.parse_args()

    workspace_root = Path(args.workspace_root).expanduser().resolve()
    config_path = _resolve_path(args.config, workspace_root)
    cfg = _load_toml(config_path)
    project = _find_project(cfg, _safe_text(args.project_id))

    project_root_rel = _safe_text(project.get("project_root_rel"))
    task_root_rel = _safe_text(project.get("task_root_rel"))
    if not project_root_rel:
        raise ValueError("项目缺少 project_root_rel")
    if not task_root_rel:
        raise ValueError("项目缺少 task_root_rel")

    project_root = _resolve_config_rel_path(project_root_rel, workspace_root)
    task_root = _resolve_config_rel_path(task_root_rel, workspace_root)
    session_store_path = _resolve_project_session_store(
        _safe_text(args.project_id),
        project_root,
        workspace_root,
        explicit_path=_safe_text(args.session_json),
    )
    store_session_rows = _load_project_session_rows(session_store_path)
    store_channels_map: dict[str, list[dict[str, str]]] = {}
    for row in store_session_rows:
        cname = _safe_text(row.get("channel_name"))
        sid = _safe_text(row.get("session_id"))
        if not (cname and sid):
            continue
        store_channels_map.setdefault(cname, []).append(row)

    configured_channels = project.get("channels") if isinstance(project.get("channels"), list) else []
    channel_cfg_by_name: dict[str, dict[str, Any]] = {}
    preflight_issues: list[dict[str, Any]] = []
    for it in configured_channels:
        if not isinstance(it, dict):
            continue
        name = _safe_text(it.get("name"))
        if not name:
            continue
        if name in channel_cfg_by_name:
            preflight_issues.append(
                _issue(
                    "duplicate_channel_name",
                    "config.toml 中 channel name 重复，CCR 生成只能保留一个派生结果",
                    project_id=_safe_text(project.get("id")),
                    channel_name=name,
                    field="channel_name",
                )
            )
        channel_cfg_by_name[name] = it

    configured_channel_names = [name for name in channel_cfg_by_name.keys()]
    extra_channel_names = sorted(set(store_channels_map.keys()) - set(configured_channel_names))
    all_channel_names = configured_channel_names + extra_channel_names

    channel_rows: list[dict[str, Any]] = []
    for name in all_channel_names:
        cfg_row = channel_cfg_by_name.get(name, {})
        session_rows: list[dict[str, Any]] = []
        for store_row in store_channels_map.get(name, []):
            sid = _safe_text(store_row.get("session_id"))
            if not sid:
                continue
            identity = _resolve_ccr_agent_identity(
                alias=_safe_text(store_row.get("alias")),
                channel_name=name,
                session_id=sid,
            )
            session_rows.append(
                {
                    "session_id": sid,
                    "desc": _safe_text(identity.get("display_name")),
                    "status": _safe_text(store_row.get("status")) or "active",
                    "model": _safe_text(store_row.get("model")),
                    "cli_type": _safe_text(store_row.get("cli_type")) or "codex",
                    "purpose": _safe_text(store_row.get("purpose")),
                    "environment": _safe_text(store_row.get("environment")),
                    "workdir": _safe_text(store_row.get("workdir")),
                    "branch": _safe_text(store_row.get("branch")),
                    "session_role": _safe_text(store_row.get("session_role")),
                    "identity_source": _safe_text(identity.get("identity_source")),
                    "identity_issue": _safe_text(identity.get("identity_issue")),
                    "identity_fallback_used": bool(identity.get("identity_fallback_used")),
                }
            )

        primary_sid = ""
        primary_cli = "codex"
        for store_row in store_channels_map.get(name, []):
            if bool(store_row.get("is_primary")):
                primary_sid = _safe_text(store_row.get("session_id"))
                primary_cli = _safe_text(store_row.get("cli_type")) or "codex"
                break
        if not primary_sid and session_rows:
            primary_sid = session_rows[0]["session_id"]
            primary_cli = (session_rows[0]["cli_type"] if session_rows else "") or "codex"

        structure_layer = _normalize_structure_layer(cfg_row.get("structure_layer"))
        requires_primary = _safe_bool(
            cfg_row.get("requires_primary"),
            default=structure_layer not in {"待启用通道", "历史壳"},
        )
        formal_dispatch_entry = _safe_bool(
            cfg_row.get("formal_dispatch_entry"),
            default=structure_layer == "现役主干",
        )
        display_state = _channel_display_state(
            startup_ready=bool(primary_sid),
            structure_layer=structure_layer,
            requires_primary=requires_primary,
        )

        candidates: list[dict[str, Any]] = []
        for row in session_rows:
            sid = row["session_id"]
            display_name = row["desc"]
            is_primary = bool(primary_sid and sid == primary_sid)
            dispatch_profile = _agent_dispatch_profile(name, display_name, is_primary=is_primary)
            dispatch_profile = _apply_dispatch_profile_overrides(
                dispatch_profile,
                cfg_row,
                agent_name=display_name,
            )
            candidates.append(
                {
                    "session_id": sid,
                    "desc": row["desc"],
                    "display_name": display_name,
                    "model": row["model"],
                    "cli_type": row["cli_type"] or primary_cli,
                    "status": row["status"] or "active",
                    "environment": row.get("environment") or "",
                    "workdir": row.get("workdir") or "",
                    "branch": row.get("branch") or "",
                    "session_role": row.get("session_role") or "",
                    "identity_source": row.get("identity_source") or "",
                    "identity_issue": row.get("identity_issue") or "",
                    "identity_fallback_used": bool(row.get("identity_fallback_used")),
                    "identity_purpose_present": bool(_safe_text(row.get("purpose"))),
                    "is_primary": is_primary,
                    **dispatch_profile,
                }
            )

        primary_alias = ""
        for cand in candidates:
            if bool(cand.get("is_primary")):
                primary_alias = _safe_text(cand.get("display_name")) or _safe_text(cand.get("desc"))
                break

        channel_rows.append(
            {
                "channel_name": name,
                "channel_desc": _safe_text(cfg_row.get("desc")),
                "channel_role": _safe_text(cfg_row.get("channel_role") or cfg_row.get("channelRole"))
                or _infer_channel_role(name),
                "structure_layer": structure_layer,
                "requires_primary": requires_primary,
                "formal_dispatch_entry": formal_dispatch_entry,
                "primary_session_id": primary_sid,
                "primary_session_alias": primary_alias,
                "primary_cli_type": primary_cli,
                "session_candidates_count": len(candidates),
                "session_candidates": candidates,
                "startup_ready": bool(primary_sid),
                "display_state": display_state,
            }
        )

    with_primary = sum(1 for row in channel_rows if row.get("startup_ready"))
    missing_primary = [str(row.get("channel_name")) for row in channel_rows if not row.get("startup_ready")]
    missing_required_primary = [
        str(row.get("channel_name"))
        for row in channel_rows
        if not row.get("startup_ready") and bool(row.get("requires_primary"))
    ]
    layer_counts: dict[str, int] = {}
    for row in channel_rows:
        layer = _safe_text(row.get("structure_layer")) or "未分层"
        layer_counts[layer] = layer_counts.get(layer, 0) + 1
    layer_counts = dict(sorted(layer_counts.items(), key=lambda kv: STRUCTURE_LAYER_ORDER.get(kv[0], 99)))
    formal_dispatch_count = sum(1 for row in channel_rows if bool(row.get("formal_dispatch_entry")))
    all_agents = [
        {
            "channel_name": row.get("channel_name"),
            "channel_role": row.get("channel_role"),
            "structure_layer": row.get("structure_layer"),
            "formal_dispatch_entry": row.get("formal_dispatch_entry"),
            **candidate,
        }
        for row in channel_rows
        for candidate in row.get("session_candidates", [])
    ]
    business_dispatch_index = _build_business_dispatch_index(all_agents)
    ccr_validation = _validate_ccr_identity_gate(
        project_id=_safe_text(project.get("id")),
        channel_rows=channel_rows,
        preflight_issues=preflight_issues,
    )

    payload: dict[str, Any] = {
        "version": 1,
        "schema": "collab-registry.v1",
        "generated_at": _now_iso(),
        "source": f"config.toml(channel metadata) + {session_store_path}",
        "project": {
            "project_id": _safe_text(project.get("id")),
            "project_name": _safe_text(project.get("name")),
            "project_root": str(project_root),
            "task_root": str(task_root),
            "session_store_path": str(session_store_path),
        },
        "summary": {
            "channel_count": len(channel_rows),
            "agent_count": len(all_agents),
            "with_primary_session": with_primary,
            "without_primary_session": len(channel_rows) - with_primary,
            "missing_primary_channels": missing_primary,
            "missing_required_primary_channels": missing_required_primary,
            "formal_dispatch_channel_count": formal_dispatch_count,
            "structure_layer_counts": layer_counts,
            "business_domain_count": len(business_dispatch_index),
        },
        "channels": channel_rows,
        "all_agents": all_agents,
        "business_dispatch_index": business_dispatch_index,
        "ccr_validation": ccr_validation,
        "communication_playbook": _build_communication_playbook(),
    }

    default_output = (project_root / "registry" / "collab-registry.v1.json").resolve()
    default_view_output = (project_root / "registry" / "collab-registry.view.md").resolve()
    default_dispatch_output = (project_root / "registry" / "collab-registry.dispatch.view.md").resolve()
    default_html_output = (project_root / "artifacts" / "agent-directory" / f"{_safe_text(project.get('id'))}-agent-directory.html").resolve()
    output_path = _resolve_path(_safe_text(args.output), workspace_root) if _safe_text(args.output) else default_output
    view_output_path = (
        _resolve_path(_safe_text(args.view_output), workspace_root)
        if _safe_text(args.view_output)
        else default_view_output
    )
    dispatch_output_path = (
        _resolve_path(_safe_text(args.dispatch_output), workspace_root)
        if _safe_text(args.dispatch_output)
        else default_dispatch_output
    )
    html_output_path = (
        _resolve_path(_safe_text(args.html_output), workspace_root)
        if _safe_text(args.html_output)
        else default_html_output
    )

    if not args.dry_run:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        view_output_path.parent.mkdir(parents=True, exist_ok=True)
        view_output_path.write_text(_render_view(payload), encoding="utf-8")
        dispatch_output_path.parent.mkdir(parents=True, exist_ok=True)
        dispatch_output_path.write_text(_render_dispatch_view(payload), encoding="utf-8")
        html_output_path.parent.mkdir(parents=True, exist_ok=True)
        html_output_path.write_text(_render_agent_directory_html(payload), encoding="utf-8")

    print(f"[ok] project_id={_safe_text(project.get('id'))}")
    print(f"[ok] channels={len(channel_rows)} with_primary={with_primary} missing={len(missing_primary)}")
    print(f"[ok] session_store={session_store_path}")
    print(f"[ok] output={output_path}")
    print(f"[ok] view_output={view_output_path}")
    print(f"[ok] dispatch_output={dispatch_output_path}")
    print(f"[ok] html_output={html_output_path}")
    if missing_required_primary:
        print("[warn] missing_required_primary_channels:")
        for name in missing_required_primary:
            print(f"  - {name}")
    if bool(ccr_validation.get("blocking")):
        print(f"[warn] ccr_validation_blocking={int(ccr_validation.get('blocking_issue_count') or 0)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
