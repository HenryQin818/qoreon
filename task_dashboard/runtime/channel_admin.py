from __future__ import annotations

from pathlib import Path
import hashlib
import shutil
from datetime import datetime, timezone
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

_AGENTS_MD_ROLE_TEMPLATES = [
    {
        "id": "coordinator",
        "label": "总控",
        "summary": "负责目标拆解、任务分派、回执合并、验收收口。",
        "focus": [
            "先确认目标、范围、责任位和验收口径，再安排执行。",
            "跨 Agent 协作默认要求回执，回执保留当前结论、是否放行、阻塞、证据和下一步。",
            "发现服务、会话、真实消息或写入动作时，先确认授权边界，不绕过门禁。",
        ],
    },
    {
        "id": "planner",
        "label": "业务/规划",
        "summary": "负责业务澄清、方案收敛、规格说明和用户视角验收。",
        "focus": [
            "优先用业务语言说明要解决的问题、用户收益和不做项。",
            "输出方案时同步写清输入、输出、状态、风险和验收方式。",
            "不把草稿、预览、待授权或 QA 结果误写成已生效结论。",
        ],
    },
    {
        "id": "developer",
        "label": "执行/研发",
        "summary": "负责工程实现、接口对接、代码验证和技术风险收口。",
        "focus": [
            "先读现有实现和契约，再做最小必要改动。",
            "新增或修改 API 时同步更新契约文档，并补相关测试。",
            "不直接执行服务启动、重启、发布、service monitor 写入或真实消息动作。",
        ],
    },
    {
        "id": "tester",
        "label": "检查/测试",
        "summary": "负责验收矩阵、测试用例、回归风险和失败证据整理。",
        "focus": [
            "把用户可见状态、边界状态、缺失态和错误态都纳入验收。",
            "测试通过只代表本轮验证通过，不代表真实初始化、真实送达或写入授权已完成。",
            "失败时给出复现条件、证据路径、影响范围和建议停止线。",
        ],
    },
    {
        "id": "general",
        "label": "通用协作",
        "summary": "适合暂未细分职责的新通道，保留通用协作和安全边界。",
        "focus": [
            "优先理解本通道职责，再推进任务。",
            "涉及其他通道时使用正式消息链路协作，并要求回执。",
            "不把运行态、临时授权或历史消息结论写成长期规则。",
        ],
    },
]

_AGENTS_MD_TEMPLATE_BY_ID = {str(row["id"]): row for row in _AGENTS_MD_ROLE_TEMPLATES}

_CHANNEL_TYPE_TEMPLATES = [
    {
        "type": "总控",
        "role": "coordinator",
        "template": "总控模板",
        "summary": "范围冻结、跨通道调度、最终裁定、验收收口。",
        "focus": ["先冻结目标、责任位和验收口径，再派发执行。", "高风险动作先收门禁，不用历史结论替代当前证据。"],
        "skills": ["codex-agent-collaboration", "collab-message-send", "task-workflow-create-validate"],
    },
    {
        "type": "助理",
        "role": "planner",
        "template": "项目助理模板",
        "summary": "项目资料整理、异常协调、跨通道提醒、轻量跟进。",
        "focus": ["整理事实、路径和待办，不代替责任位裁定。", "提醒和催办走正式消息链路，避免口头状态漂移。"],
        "skills": ["collab-message-send", "codex-agent-collaboration", "assist04-requirement-intake-gate"],
    },
    {
        "type": "产品",
        "role": "planner",
        "template": "产品规划模板",
        "summary": "需求收敛、产品方案、交互规格、任务拆解。",
        "focus": ["先说明用户目标、业务边界、不做项和验收方式。", "规格冻结前保留差异状态和停止线。"],
        "skills": ["prototype-requirement-planning-flow", "product-interface-planning-guardrails", "task-workflow-create-validate"],
    },
    {
        "type": "镜像",
        "role": "planner",
        "template": "用户镜像模板",
        "summary": "用户视角、误解风险、价值判断、业务偏差提醒。",
        "focus": ["从用户理解、可见性和误解风险出发给单一判断。", "不替代测试、服务或后端门禁。"],
        "skills": ["product-interface-planning-guardrails", "visual-requirement-review-board"],
    },
    {
        "type": "前端",
        "role": "developer",
        "template": "前端模板",
        "summary": "页面交互、前端实现、UI 状态、页面体验验证。",
        "focus": ["先确认只读真源、状态机和空态，再改页面。", "不从展示缓存、历史 run 正文或别名反推业务真源。"],
        "skills": ["task-dashboard-visual-refinement-support", "product-interface-planning-guardrails"],
    },
    {
        "type": "后端",
        "role": "developer",
        "template": "后端模板",
        "summary": "API、读写模型、运行时、安全、并发、适配器。",
        "focus": ["先读契约、现有实现和测试，再做兼容新增。", "不绕过同 session 串行、SessionStore 真源或 announce 证据链。"],
        "skills": ["task-workflow-create-validate", "codex-agent-collaboration"],
    },
    {
        "type": "测试",
        "role": "tester",
        "template": "测试验收模板",
        "summary": "测试计划、验收矩阵、回归、live 验收。",
        "focus": ["覆盖成功态、缺失态、错误态、授权态和停止线。", "验收结论必须带命令、报告、截图或 live 证据。"],
        "skills": ["task-workflow-create-validate", "sub05-issue-aggregation"],
    },
    {
        "type": "服务",
        "role": "developer",
        "template": "服务管理模板",
        "summary": "启动、重启、注册、健康、service monitor 门禁。",
        "focus": ["服务动作必须有明确 action_scope、回滚方式和验收清单。", "不把健康检查等同于发布、部署或迁移授权。"],
        "skills": ["local-service-hub"],
    },
    {
        "type": "通讯",
        "role": "coordinator",
        "template": "通讯能力模板",
        "summary": "消息模式、送达证据、通讯录、回执链路。",
        "focus": ["正式通知只认 announce_run_id、目标会话一致和可见性证据。", "direct resume、收件箱或只写文件不算正式送达。"],
        "skills": ["collab-message-send", "codex-agent-collaboration", "webtag-ccb-bridge"],
    },
    {
        "type": "任务",
        "role": "coordinator",
        "template": "任务管理模板",
        "summary": "任务创建、责任位、派发、验收、归档收口。",
        "focus": ["任务文件是主线，消息回执是闭环主链路。", "状态迁移要保留责任位、证据和下一步。"],
        "skills": ["task-workflow-create-validate", "codex-agent-collaboration"],
    },
    {
        "type": "技能",
        "role": "planner",
        "template": "技能治理模板",
        "summary": "skills 创建、审核、升级、冲突治理。",
        "focus": ["先判断技能是否真触发，再维护入口和冲突边界。", "不把 skill 触发当成自动授权。"],
        "skills": ["skill-creator", "project-skill-maintenance"],
    },
    {
        "type": "资料",
        "role": "planner",
        "template": "资料治理模板",
        "summary": "README、AGENTS、索引、项目资料真源维护。",
        "focus": ["长期规则写 AGENTS/README，运行证据放运行目录。", "不把临时状态、密钥或一次性授权沉淀为资料真源。"],
        "skills": ["legacy-project-agent-init-upgrade", "task-workflow-create-validate"],
    },
    {
        "type": "视觉",
        "role": "planner",
        "template": "视觉设计模板",
        "summary": "视觉系统、设计一致性、可读性、页面审美审核。",
        "focus": ["在既有设计系统内提升信息密度、层级和可读性。", "视觉建议不替代产品规格、测试验收或服务门禁。"],
        "skills": ["task-dashboard-visual-refinement-support", "visual-board-delivery-playbook"],
    },
]

_CHANNEL_TYPE_BY_ID = {str(row["type"]): row for row in _CHANNEL_TYPE_TEMPLATES}
_CHANNEL_TYPE_ALIASES = {
    "coordinator": "总控",
    "assistant": "助理",
    "product": "产品",
    "mirror": "镜像",
    "frontend": "前端",
    "backend": "后端",
    "tester": "测试",
    "service": "服务",
    "communication": "通讯",
    "task": "任务",
    "skill": "技能",
    "docs": "资料",
    "visual": "视觉",
}

_AGENTS_MD_BLOCKING_PATTERNS = [
    ("secret_token", re.compile(r"(?i)\b(?:sk-[A-Za-z0-9_-]{16,}|ghp_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}|xox[baprs]-[A-Za-z0-9-]{10,})\b"), "疑似真实密钥或 token"),
    ("bearer_token", re.compile(r"(?i)\bAuthorization\s*:\s*Bearer\s+[A-Za-z0-9._~+/=-]{12,}"), "疑似 Bearer 授权头"),
    ("concrete_run_id", re.compile(r"\b(?:run_id|runId|announce_run_id)\s*[:=]\s*['\"]?20\d{6}-\d{6}-[0-9a-fA-F]{6,}\b"), "疑似具体 run_id/announce_run_id"),
    ("concrete_session_id", re.compile(r"\b(?:session_id|sessionId|target_session_id)\s*[:=]\s*['\"]?[0-9a-fA-F]{4,}-[0-9a-fA-F-]{12,}\b"), "疑似具体 session_id"),
    ("concrete_pid", re.compile(r"(?i)(?:\bpid\s*[:=]\s*|进程\s*(?:PID)?\s*[:=]?\s*)[1-9]\d{1,6}\b"), "疑似具体 PID"),
    ("concrete_port", re.compile(r"(?i)(?:\bport\s*[:=]\s*|端口\s*[:=]\s*)[1-9]\d{1,4}\b"), "疑似具体端口运行态"),
    ("transient_health", re.compile(r"(?i)\b(?:health|status|健康)\s*[:=]\s*(?:ok|healthy|running|unhealthy|down)\b"), "疑似瞬时 health/status"),
    ("service_or_session_grant", re.compile(r"(?i)(允许|授权|可以|可直接|无需审批|无需门禁|自行).{0,24}(服务启动|服务重启|启动服务|重启服务|service monitor|会话创建|轮换会话|真实初始化消息|发送真实消息|announce|resume)"), "疑似越权服务/会话/真实消息授权"),
    ("truth_store_write_grant", re.compile(r"(?i)(允许|授权|可以|可直接|无需审批|自行).{0,24}(写入|修改).{0,12}(SessionStore|registry|COMMUNICATIONS|service monitor)"), "疑似越权真源写入授权"),
]

_STATIC_INSTRUCTION_SOURCE_FILE = "AGENTS.md"
_STATIC_INSTRUCTION_REPAIR_ENDPOINT = "/api/channels/static-instruction-files/repair"
_MANAGED_MIRROR_MARKER = "task_dashboard:managed-mirror"
_MANAGED_MIRROR_HEADER_RE = re.compile(
    r"\A<!--\s*task_dashboard:managed-mirror\s*\n(?P<meta>.*?)\n-->\s*\n\n(?P<body>.*)\Z",
    re.DOTALL,
)
_MANAGED_MIRROR_NOTICE = (
    "> 本文件由 task_dashboard 根据 AGENTS.md 自动同步生成。\n"
    "> 请编辑 AGENTS.md；不要直接编辑本文件。\n\n"
)
_STATIC_INSTRUCTION_FILE_MAPPINGS = {
    "codebuddy": {
        "cliType": "codebuddy",
        "sourceFileName": _STATIC_INSTRUCTION_SOURCE_FILE,
        "fileName": "CODEBUDDY.md",
    }
}


class StaticInstructionFileConflict(ValueError):
    """Raised when a CLI instruction mirror exists but is not safely managed."""


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


def _path_within(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except Exception:
        return False


def _project_block_for(config_content: str, project_id: str) -> str:
    project_pattern = (
        rf'(\[\[projects\]\]\s*\nid\s*=\s*[\'"]?{re.escape(project_id)}[\'"]?\s*'
        rf'(?:.*?\n)*?)(?=\[\[projects\]\]|\Z)'
    )
    match = re.search(project_pattern, config_content, re.DOTALL)
    if not match:
        raise ValueError(f"Project '{project_id}' not found in config.toml")
    return match.group(1)


def _project_task_root_from_config(
    *,
    project_id: str,
    config_path: Path,
    repo_root: Path,
) -> Path:
    if not config_path.exists():
        raise ValueError("config.toml not found")
    project_block = _project_block_for(config_path.read_text(encoding="utf-8"), project_id)
    task_root_match = re.search(r'task_root_rel\s*=\s*[\'"]([^\'"]+)[\'"]', project_block)
    if not task_root_match:
        raise ValueError("project task_root_rel not configured")
    return resolve_task_root_path(repo_root=repo_root, task_root_rel=task_root_match.group(1))


def project_channel_exists_in_config(*, project_block: str, channel_name: str) -> bool:
    target = str(channel_name or "").strip()
    if not target:
        return False
    for section in _iter_project_child_sections(project_block):
        if section["header"] != "[[projects.channels]]":
            continue
        block = str(section["block"] or "")
        name_match = re.search(r'(?m)^\s*name\s*=\s*[\'"]([^\'"]+)[\'"]\s*$', block)
        block_name = str(name_match.group(1) or "").strip() if name_match else ""
        if block_name == target:
            return True
    return False


def resolve_channel_root_path(
    *,
    project_id: str,
    channel_name: str,
    config_path: Path,
    repo_root: Path,
    require_channel: bool = True,
) -> Path:
    config_content = config_path.read_text(encoding="utf-8")
    project_block = _project_block_for(config_content, project_id)
    if require_channel and not project_channel_exists_in_config(
        project_block=project_block,
        channel_name=channel_name,
    ):
        raise ValueError(f"Channel '{channel_name}' not found")
    task_root_match = re.search(r'task_root_rel\s*=\s*[\'"]([^\'"]+)[\'"]', project_block)
    if not task_root_match:
        raise ValueError("project task_root_rel not configured")
    task_root = resolve_task_root_path(repo_root=repo_root, task_root_rel=task_root_match.group(1))
    channel_root = (task_root / str(channel_name or "").strip()).resolve()
    if not _path_within(channel_root, task_root):
        raise PermissionError("channel path escapes task root")
    return channel_root


def agents_md_role_templates() -> list[dict[str, str]]:
    return [
        {
            "id": str(row.get("id") or ""),
            "label": str(row.get("label") or ""),
            "summary": str(row.get("summary") or ""),
        }
        for row in _AGENTS_MD_ROLE_TEMPLATES
    ]


def channel_type_templates() -> list[dict[str, Any]]:
    return [
        {
            "channelType": str(row.get("type") or ""),
            "role": str(row.get("role") or ""),
            "template": str(row.get("template") or ""),
            "summary": str(row.get("summary") or ""),
            "recommendedSkills": list(row.get("skills") or []),
            "defaultWorkdir": "默认使用通道目录；显式 workdir 仍优先。",
            "forbiddenZones": [
                "SessionStore/registry/COMMUNICATIONS/service monitor 写入",
                "服务启动、重启、注册、发布或映射维护",
                "会话创建、会话轮换、真实初始化消息或硬跑 resume",
                "token、PID、端口、run_id、临时 session、一次性授权、瞬时 health",
            ],
        }
        for row in _CHANNEL_TYPE_TEMPLATES
    ]


def normalize_agents_md_role(value: Any) -> str:
    role = str(value or "").strip().lower().replace("-", "_")
    return role if role in _AGENTS_MD_TEMPLATE_BY_ID else "general"


def normalize_channel_type(value: Any) -> str:
    raw = str(value or "").strip()
    if raw in _CHANNEL_TYPE_BY_ID:
        return raw
    lowered = raw.lower().replace("-", "_").replace(" ", "_")
    return _CHANNEL_TYPE_ALIASES.get(lowered, "")


def infer_channel_type_from_name(channel_name: Any) -> str:
    name = str(channel_name or "").strip()
    for row in _CHANNEL_TYPE_TEMPLATES:
        short = str(row.get("type") or "")
        if short and name.startswith(short):
            return short
    return ""


def resolve_agents_md_template_meta(
    *,
    channel_type: Any = "",
    role: Any = "",
    channel_name: str = "",
) -> dict[str, Any]:
    resolved_type = normalize_channel_type(channel_type) or infer_channel_type_from_name(channel_name)
    if resolved_type:
        row = _CHANNEL_TYPE_BY_ID[resolved_type]
        role_id = normalize_agents_md_role(row.get("role"))
        role_template = _AGENTS_MD_TEMPLATE_BY_ID.get(role_id) or _AGENTS_MD_TEMPLATE_BY_ID["general"]
        return {
            "channelType": resolved_type,
            "role": role_id,
            "label": str(role_template.get("label") or ""),
            "summary": str(row.get("summary") or role_template.get("summary") or ""),
            "template": str(row.get("template") or ""),
            "focus": list(row.get("focus") or role_template.get("focus") or []),
            "recommendedSkills": list(row.get("skills") or []),
            "defaultWorkdir": "默认使用通道目录；显式 workdir 仍优先。",
            "source": "channel_type",
        }
    role_id = normalize_agents_md_role(role)
    template = _AGENTS_MD_TEMPLATE_BY_ID.get(role_id) or _AGENTS_MD_TEMPLATE_BY_ID["general"]
    return {
        "channelType": "",
        "role": role_id,
        "label": str(template.get("label") or ""),
        "summary": str(template.get("summary") or ""),
        "template": f"{template.get('label')}模板",
        "focus": list(template.get("focus") or []),
        "recommendedSkills": [],
        "defaultWorkdir": "默认使用通道目录；显式 workdir 仍优先。",
        "source": "agent_role",
    }


def validate_agents_md_content(content: str) -> dict[str, Any]:
    text = str(content or "")
    blocking: list[dict[str, str]] = []
    for code, pattern, message in _AGENTS_MD_BLOCKING_PATTERNS:
        found = pattern.search(text)
        if not found:
            continue
        blocking.append({"code": code, "message": message, "sample": found.group(0)[:120]})
    return {
        "ok": not blocking,
        "status": "pass" if not blocking else "blocked",
        "blockingIssues": blocking,
        "warnings": [],
        "willWriteSessionStore": False,
        "willWriteRegistry": False,
        "willWriteCommunications": False,
        "willWriteServiceHub": False,
        "willCreateSession": False,
        "willSendMessage": False,
        "willRunServiceAction": False,
    }


def _raise_if_agents_md_blocked(dry_run: dict[str, Any]) -> None:
    if dry_run.get("ok"):
        return
    messages = [str(item.get("message") or item.get("code") or "") for item in dry_run.get("blockingIssues") or []]
    raise ValueError("AGENTS.md dry-run blocked: " + "; ".join([m for m in messages if m]))


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")


def _utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _content_fingerprint(content: str) -> str:
    digest = hashlib.sha256(str(content or "").encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _normalise_cli_type(value: Any) -> str:
    return str(value or "").strip().lower()


def _normalize_cli_type_list(values: Any) -> set[str]:
    if values is None:
        return set()
    if isinstance(values, str):
        raw_items = [item.strip() for item in re.split(r"[,;\s]+", values) if item.strip()]
    elif isinstance(values, (list, tuple, set)):
        raw_items = [str(item or "").strip() for item in values]
    else:
        raw_items = [str(values or "").strip()]
    return {_normalise_cli_type(item) for item in raw_items if _normalise_cli_type(item)}


def static_instruction_file_mappings() -> list[dict[str, str]]:
    return [dict(row) for row in _STATIC_INSTRUCTION_FILE_MAPPINGS.values()]


def _mirror_path(channel_root: Path, file_name: str) -> Path:
    candidate = (channel_root / str(file_name or "")).resolve()
    if not _path_within(candidate, channel_root):
        raise PermissionError("static instruction file path escapes channel root")
    return candidate


def _parse_managed_mirror(content: str) -> dict[str, Any]:
    match = _MANAGED_MIRROR_HEADER_RE.match(str(content or ""))
    if not match:
        return {"managed": False, "meta": {}, "body": str(content or "")}
    meta: dict[str, str] = {}
    for line in str(match.group("meta") or "").splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        meta[str(key or "").strip()] = str(value or "").strip()
    return {"managed": True, "meta": meta, "body": str(match.group("body") or "")}


def _render_managed_mirror_content(
    source_content: str,
    *,
    cli_type: str,
    generated_at: str = "",
) -> str:
    source_text = str(source_content or "")
    if not source_text.endswith("\n"):
        source_text += "\n"
    generated = str(generated_at or "").strip() or _utc_iso()
    source_fingerprint = _content_fingerprint(source_text)
    return (
        f"<!-- {_MANAGED_MIRROR_MARKER}\n"
        f"source={_STATIC_INSTRUCTION_SOURCE_FILE}\n"
        f"cli_type={cli_type}\n"
        f"generated_at={generated}\n"
        f"source_fingerprint={source_fingerprint}\n"
        "-->\n\n"
        f"{_MANAGED_MIRROR_NOTICE}"
        f"{source_text}"
    )


def _managed_mirror_expected_body(source_content: str) -> str:
    source_text = str(source_content or "")
    if not source_text.endswith("\n"):
        source_text += "\n"
    return _MANAGED_MIRROR_NOTICE + source_text


def _source_payload(channel_root: Path, source_content: str, *, source_exists: bool = True) -> dict[str, Any]:
    source_path = _mirror_path(channel_root, _STATIC_INSTRUCTION_SOURCE_FILE)
    source_text = str(source_content or "")
    if source_text and not source_text.endswith("\n"):
        source_text += "\n"
    return {
        "fileName": _STATIC_INSTRUCTION_SOURCE_FILE,
        "path": str(source_path),
        "exists": bool(source_exists),
        "fingerprint": _content_fingerprint(source_text),
    }


def _inspect_static_instruction_mirror(
    *,
    channel_root: Path,
    cli_type: str,
    source_content: str,
    enabled: bool,
) -> dict[str, Any]:
    spec = _STATIC_INSTRUCTION_FILE_MAPPINGS.get(cli_type)
    if not spec:
        return {
            "cliType": cli_type,
            "fileName": "",
            "path": "",
            "exists": False,
            "managed": False,
            "syncStatus": "skipped",
            "backupPath": "",
            "blockingIssues": [],
        }

    file_name = str(spec.get("fileName") or "")
    path = _mirror_path(channel_root, file_name)
    exists = path.exists()
    source_text = str(source_content or "")
    if not source_text.endswith("\n"):
        source_text += "\n"
    source_fingerprint = _content_fingerprint(source_text)
    row: dict[str, Any] = {
        "cliType": cli_type,
        "fileName": file_name,
        "path": str(path),
        "exists": bool(exists),
        "managed": False,
        "syncStatus": "missing" if enabled else "skipped",
        "backupPath": "",
        "blockingIssues": [],
        "sourceFingerprint": source_fingerprint,
    }
    if not exists:
        return row

    content = path.read_text(encoding="utf-8")
    parsed = _parse_managed_mirror(content)
    row["managed"] = bool(parsed.get("managed"))
    if not parsed.get("managed"):
        row["syncStatus"] = "conflict"
        row["blockingIssues"] = [
            {
                "code": "unmanaged_mirror",
                "message": f"{file_name} exists but is not a task_dashboard managed mirror.",
            }
        ]
        return row

    meta = parsed.get("meta") if isinstance(parsed.get("meta"), dict) else {}
    expected_body = _managed_mirror_expected_body(source_text)
    meta_source = str(meta.get("source") or "").strip()
    meta_cli = _normalise_cli_type(meta.get("cli_type"))
    meta_fingerprint = str(meta.get("source_fingerprint") or "").strip()
    if meta_source != _STATIC_INSTRUCTION_SOURCE_FILE or meta_cli != cli_type:
        row["syncStatus"] = "conflict"
        row["blockingIssues"] = [
            {
                "code": "managed_header_mismatch",
                "message": f"{file_name} managed header does not match {cli_type}/{_STATIC_INSTRUCTION_SOURCE_FILE}.",
            }
        ]
        return row

    body = str(parsed.get("body") or "")
    if meta_fingerprint == source_fingerprint and body == expected_body:
        row["syncStatus"] = "synced"
        return row

    row["syncStatus"] = "stale"
    if meta_fingerprint == source_fingerprint and body != expected_body:
        row["blockingIssues"] = [
            {
                "code": "managed_mirror_modified",
                "message": f"{file_name} is managed but its visible body differs from AGENTS.md.",
            }
        ]
    return row


def _summarize_static_instruction_files(mirrors: list[dict[str, Any]]) -> dict[str, int]:
    summary = {key: 0 for key in ["synced", "missing", "stale", "conflict", "skipped", "blocked"]}
    for row in mirrors:
        status = str((row or {}).get("syncStatus") or "").strip().lower()
        if status in summary:
            summary[status] += 1
    return summary


def build_static_instruction_files_payload(
    *,
    channel_root: Path,
    source_content: str,
    source_exists: bool = True,
    enabled_cli_types: Any = None,
    include_known_mirrors: bool = True,
) -> dict[str, Any]:
    enabled = _normalize_cli_type_list(enabled_cli_types)
    mirrors: list[dict[str, Any]] = []
    for cli_type in sorted(_STATIC_INSTRUCTION_FILE_MAPPINGS):
        spec = _STATIC_INSTRUCTION_FILE_MAPPINGS[cli_type]
        path = _mirror_path(channel_root, str(spec.get("fileName") or ""))
        is_enabled = cli_type in enabled
        if path.exists():
            is_enabled = True
        if include_known_mirrors or is_enabled:
            mirrors.append(
                _inspect_static_instruction_mirror(
                    channel_root=channel_root,
                    cli_type=cli_type,
                    source_content=source_content,
                    enabled=is_enabled,
                )
            )
    return {
        "source": _source_payload(channel_root, source_content, source_exists=source_exists),
        "mirrors": mirrors,
        "summary": _summarize_static_instruction_files(mirrors),
        "repairEndpoint": _STATIC_INSTRUCTION_REPAIR_ENDPOINT,
        "mappings": static_instruction_file_mappings(),
    }


def _blocking_mirror_conflicts(payload: dict[str, Any]) -> list[dict[str, Any]]:
    blocked: list[dict[str, Any]] = []
    for row in payload.get("mirrors") or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("syncStatus") or "").strip().lower() != "conflict":
            continue
        blocked.append(row)
    return blocked


def _raise_if_static_instruction_conflict(payload: dict[str, Any]) -> None:
    blocked = _blocking_mirror_conflicts(payload)
    if not blocked:
        return
    names = ", ".join(str(row.get("fileName") or row.get("cliType") or "") for row in blocked)
    raise StaticInstructionFileConflict(f"static instruction file conflict: {names}")


def _sync_static_instruction_files(
    *,
    channel_root: Path,
    source_content: str,
    enabled_cli_types: Any,
    source_exists: bool = True,
) -> dict[str, Any]:
    source_text = str(source_content or "")
    if not source_text.endswith("\n"):
        source_text += "\n"
    preflight = build_static_instruction_files_payload(
        channel_root=channel_root,
        source_content=source_text,
        source_exists=source_exists,
        enabled_cli_types=enabled_cli_types,
    )
    _raise_if_static_instruction_conflict(preflight)

    backup_paths: dict[str, str] = {}
    for row in preflight.get("mirrors") or []:
        if not isinstance(row, dict):
            continue
        status = str(row.get("syncStatus") or "").strip().lower()
        cli_type = _normalise_cli_type(row.get("cliType"))
        if status not in {"missing", "stale"}:
            continue
        if not cli_type or cli_type not in _normalize_cli_type_list(enabled_cli_types) and not bool(row.get("exists")):
            continue
        mirror_path = Path(str(row.get("path") or "")).resolve()
        if not _path_within(mirror_path, channel_root):
            raise PermissionError("static instruction file path escapes channel root")
        backup_path = ""
        generated_at = ""
        if mirror_path.exists():
            old = mirror_path.read_text(encoding="utf-8")
            parsed = _parse_managed_mirror(old)
            meta = parsed.get("meta") if isinstance(parsed.get("meta"), dict) else {}
            generated_at = str(meta.get("generated_at") or "").strip()
            backup = channel_root / f"{mirror_path.name}.bak.{_utc_stamp()}"
            backup.write_text(old, encoding="utf-8")
            backup_path = str(backup)
        mirror_path.write_text(
            _render_managed_mirror_content(source_text, cli_type=cli_type, generated_at=generated_at),
            encoding="utf-8",
        )
        if backup_path:
            backup_paths[cli_type] = backup_path

    payload = build_static_instruction_files_payload(
        channel_root=channel_root,
        source_content=source_text,
        source_exists=source_exists,
        enabled_cli_types=enabled_cli_types,
    )
    if backup_paths:
        for row in payload.get("mirrors") or []:
            if not isinstance(row, dict):
                continue
            cli_type = _normalise_cli_type(row.get("cliType"))
            if cli_type in backup_paths:
                row["backupPath"] = backup_paths[cli_type]
    return payload


def ensure_channel_static_instruction_files(
    *,
    project_id: str,
    channel_name: str,
    cli_type: Any,
    config_path: Path,
    repo_root: Path,
) -> dict[str, Any]:
    cli = _normalise_cli_type(cli_type)
    channel_root = resolve_channel_root_path(
        project_id=project_id,
        channel_name=channel_name,
        config_path=config_path,
        repo_root=repo_root,
    )
    agents_path = _mirror_path(channel_root, _STATIC_INSTRUCTION_SOURCE_FILE)
    if not agents_path.exists():
        raise FileNotFoundError("AGENTS.md not found")
    source_content = agents_path.read_text(encoding="utf-8")
    if cli not in _STATIC_INSTRUCTION_FILE_MAPPINGS:
        return build_static_instruction_files_payload(
            channel_root=channel_root,
            source_content=source_content,
            source_exists=True,
            enabled_cli_types=[],
        )
    dry_run = validate_agents_md_content(source_content)
    _raise_if_agents_md_blocked(dry_run)
    return _sync_static_instruction_files(
        channel_root=channel_root,
        source_content=source_content,
        enabled_cli_types=[cli],
        source_exists=True,
    )


def repair_channel_static_instruction_files(
    *,
    project_id: str,
    channel_name: str,
    cli_type: Any = "codebuddy",
    config_path: Path,
    repo_root: Path,
) -> dict[str, Any]:
    return ensure_channel_static_instruction_files(
        project_id=project_id,
        channel_name=channel_name,
        cli_type=cli_type or "codebuddy",
        config_path=config_path,
        repo_root=repo_root,
    )


def render_agents_md_template(
    *,
    role: Any,
    channel_type: Any = "",
    channel_name: str,
    channel_desc: str = "",
) -> str:
    template = resolve_agents_md_template_meta(channel_type=channel_type, role=role, channel_name=channel_name)
    focus_lines = "\n".join(f"- {item}" for item in (template.get("focus") or []))
    skills = list(template.get("recommendedSkills") or [])
    skill_lines = "\n".join(f"- 推荐：`{item}`" for item in skills) or "- 暂无专属推荐；按任务文件和项目 AGENTS.md 判断是否触发 skill。"
    channel_type_line = f"- 通道类型：{template.get('channelType')}（{template.get('template')}）\n" if template.get("channelType") else ""
    desc = str(channel_desc or "").strip() or "请在通道编辑页补充本通道的长期职责、边界和协作方式。"
    return f"""# AGENTS.md - {channel_name}

## 1. 先读规则

- 通道名称：{channel_name}
- 通道说明：{desc}
- 默认 workdir：{template.get("defaultWorkdir")}
{channel_type_line}- 标准角色：{template.get("label")}（{template.get("summary")}）
- 本文件是通道目录下的长期协作规则，只对新进入该目录的 Agent 生效；已运行会话不会自动刷新。
- 开始任务前先读当前任务文件、项目契约、通道 AGENTS.md 和最近有效回执，不把历史草稿当当前结论。

## 2. 本通道职责

{focus_lines}
- 若收到不属于本通道职责的任务，先说明原因并建议转交责任位，不要自行扩大范围。

## 3. 消息发送与回执

- 跨 Agent 协作优先使用 `python3 -m task_dashboard.message_cli send|receipt --to-agent <目标Agent> --wait-verify --json`。
- 三种交互模式：`dialog_now` 用于快速确认，`task_with_receipt` 必须回执，`notify_only` 只通知。
- 已送达只认三件套：`announce_run_id + target_session_id一致 + visible_in_channel_chat=true`。
- `--wait-verify` 只代表送达证据，不代表对方业务完成；业务完成仍需对方结果回执。
- 回执建议使用最小结构：当前结论 / 是否通过或放行 / 唯一阻塞 / 关键路径或 run_id / 下一步动作。

## 4. 任务推进

- 项目采用“目录即分工、文件名即状态”；本通道任务优先放入 `任务/`，完成后按规则归档到 `已完成/` 或其他状态目录。
- 任务流转需写清主负责位、执行位、验收位、审核或门禁位；`task_with_receipt` 必须回原发 `callback_to`。
- 创建或评审任务时优先使用 `python3 -m task_dashboard.task_cli validate --stage review --mode strict <任务文件>` 做格式和责任位校验。
- 产出材料放入 `产出物/材料/`，可复用规范和经验放入 `产出物/沉淀/`。
- 修改项应尽量保持最小范围；涉及接口契约、测试或服务边界时同步说明验证结果。

## 5. 证据与状态

- 任务完成、阻塞或失败都要给证据：任务路径、run_id、测试命令、产出物路径或可复现实况。
- 送达不等于业务完成；已写入 AGENTS.md 不等于旧会话已加载；QA 通过不等于服务启动、发布或迁移授权。
- 不从展示别名、历史 run 正文、端口、PID、mtime、缓存或旧通讯录反推业务真源。

## 6. 常用 Skills 入口

{skill_lines}
- 协作消息：`collab-message-send`、`codex-agent-collaboration`、`webtag-ccb-bridge`。
- 任务与需求：`task-workflow-create-validate`、`prototype-requirement-planning-flow`、`assist04-requirement-intake-gate`。
- 项目启动与会话：`project-startup-blueprint-gate`、`project-startup-collab-suite`、`agent-init-training-playbook`、`agent-session-rotation-handoff`。
- 运行健康与心跳：`codex-session-health-inspector`、`heartbeat-task-control`。
- Skill 是触发入口和执行口径，不等于自动授权；不确定是否适用时先说明判断。

## 7. 写入、会话与服务边界

- 本文件只保存长期协作规则，不写入 token、PID、端口、run_id、临时 session、一次性授权、瞬时 health 或历史消息结论。
- 不通过本文件授予服务启动、重启、注册、发布、service monitor 写入、会话创建、真实初始化消息或 AGENTS 批量迁移权限。
- 涉及真实写入、真实消息、会话动作或服务动作时，必须另行确认 action_scope、回滚方式和验收口径；服务动作必须转服务管理。

## 8. 找不到规则时

- 先按当前任务文件和本项目 AGENTS.md 的硬边界执行；仍不确定时，回单一阻塞和需要谁确认。
- 不要用“可能已完成”“看起来送达”“历史上通过”补位；缺证据就明确缺证据。
"""


def read_channel_agents_md(
    *,
    project_id: str,
    channel_name: str,
    config_path: Path,
    repo_root: Path,
    role: Any = "",
    channel_type: Any = "",
    channel_desc: str = "",
    enabled_cli_types: Any = None,
) -> dict[str, Any]:
    channel_root = resolve_channel_root_path(
        project_id=project_id,
        channel_name=channel_name,
        config_path=config_path,
        repo_root=repo_root,
    )
    agents_path = (channel_root / "AGENTS.md").resolve()
    if not _path_within(agents_path, channel_root):
        raise PermissionError("AGENTS.md path escapes channel root")
    exists = agents_path.exists()
    template_meta = resolve_agents_md_template_meta(channel_type=channel_type, role=role, channel_name=channel_name)
    content = agents_path.read_text(encoding="utf-8") if exists else render_agents_md_template(
        role=role,
        channel_type=channel_type,
        channel_name=channel_name,
        channel_desc=channel_desc,
    )
    dry_run = validate_agents_md_content(content)
    static_instruction_files = build_static_instruction_files_payload(
        channel_root=channel_root,
        source_content=content,
        source_exists=exists,
        enabled_cli_types=enabled_cli_types,
    )
    return {
        "ok": True,
        "projectId": project_id,
        "channelName": channel_name,
        "channelRootPath": str(channel_root),
        "agentsMdPath": str(agents_path),
        "exists": bool(exists),
        "source": "file" if exists else "template",
        "role": str(template_meta.get("role") or normalize_agents_md_role(role)),
        "channelType": str(template_meta.get("channelType") or ""),
        "templateMeta": template_meta,
        "templates": agents_md_role_templates(),
        "channelTypeTemplates": channel_type_templates(),
        "dryRun": dry_run,
        "static_instruction_files": static_instruction_files,
        "content": content,
    }


def write_channel_agents_md(
    *,
    project_id: str,
    channel_name: str,
    content: str,
    config_path: Path,
    repo_root: Path,
    enabled_cli_types: Any = None,
) -> dict[str, Any]:
    channel_root = resolve_channel_root_path(
        project_id=project_id,
        channel_name=channel_name,
        config_path=config_path,
        repo_root=repo_root,
    )
    channel_root.mkdir(parents=True, exist_ok=True)
    agents_path = (channel_root / "AGENTS.md").resolve()
    if not _path_within(agents_path, channel_root):
        raise PermissionError("AGENTS.md path escapes channel root")
    text = str(content or "")
    if not text.strip():
        raise ValueError("AGENTS.md content is empty")
    if len(text.encode("utf-8")) > 256_000:
        raise ValueError("AGENTS.md content too large")
    dry_run = validate_agents_md_content(text)
    _raise_if_agents_md_blocked(dry_run)
    if not text.endswith("\n"):
        text += "\n"
    static_preflight = build_static_instruction_files_payload(
        channel_root=channel_root,
        source_content=text,
        source_exists=True,
        enabled_cli_types=enabled_cli_types,
    )
    _raise_if_static_instruction_conflict(static_preflight)
    backup_path = ""
    previous_fingerprint = ""
    if agents_path.exists():
        old = agents_path.read_text(encoding="utf-8")
        previous_fingerprint = _content_fingerprint(old)
        if old != text:
            stamp = _utc_stamp()
            backup = channel_root / f"AGENTS.md.bak.{stamp}"
            backup.write_text(old, encoding="utf-8")
            backup_path = str(backup)
    agents_path.write_text(text, encoding="utf-8")
    static_instruction_files = _sync_static_instruction_files(
        channel_root=channel_root,
        source_content=text,
        enabled_cli_types=enabled_cli_types,
        source_exists=True,
    )
    return {
        "ok": True,
        "projectId": project_id,
        "channelName": channel_name,
        "channelRootPath": str(channel_root),
        "agentsMdPath": str(agents_path),
        "backupPath": backup_path,
        "previousFingerprint": previous_fingerprint,
        "contentLength": len(text),
        "dryRun": dry_run,
        "static_instruction_files": static_instruction_files,
    }


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
    agents_md_role: Any = "",
    channel_type: Any = "",
    agents_md_content: str = "",
    create_agents_md: bool = True,
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

    template_meta = resolve_agents_md_template_meta(
        channel_type=channel_type,
        role=agents_md_role,
        channel_name=channel_name,
    )
    agents_md_preview = ""
    agents_md_dry_run: dict[str, Any] = {"ok": True, "status": "skipped", "blockingIssues": [], "warnings": []}
    if create_agents_md:
        agents_md_preview = str(agents_md_content or "").strip()
        if not agents_md_preview:
            agents_md_preview = render_agents_md_template(
                role=agents_md_role,
                channel_type=channel_type,
                channel_name=channel_name,
                channel_desc=channel_desc or channel_name,
            ).strip()
        agents_md_dry_run = validate_agents_md_content(agents_md_preview)
        _raise_if_agents_md_blocked(agents_md_dry_run)

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
        task_root_base = resolve_task_root_path(repo_root=repo_root, task_root_rel=task_root_rel)
        task_root = (task_root_base / channel_name).resolve()
        if not _path_within(task_root, task_root_base):
            raise PermissionError("channel path escapes task root")
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
        agents_md_result: dict[str, Any] = {
            "created": False,
            "path": str(task_root / "AGENTS.md"),
            "role": str(template_meta.get("role") or normalize_agents_md_role(agents_md_role)),
            "channelType": str(template_meta.get("channelType") or ""),
            "templateMeta": template_meta,
            "dryRun": agents_md_dry_run,
            "source": "disabled",
        }
        if create_agents_md:
            agents_path = (task_root / "AGENTS.md").resolve()
            if not _path_within(agents_path, task_root):
                raise PermissionError("AGENTS.md path escapes channel root")
            content = agents_md_preview
            source = "custom" if str(agents_md_content or "").strip() else "template"
            if not content.endswith("\n"):
                content += "\n"
            if not agents_path.exists():
                agents_path.write_text(content, encoding="utf-8")
                agents_md_result["created"] = True
            agents_md_result.update(
                {
                    "path": str(agents_path),
                    "role": str(template_meta.get("role") or normalize_agents_md_role(agents_md_role)),
                    "channelType": str(template_meta.get("channelType") or ""),
                    "templateMeta": template_meta,
                    "dryRun": agents_md_dry_run,
                    "source": source,
                }
            )
        agents_source = ""
        agents_exists = False
        agents_path_for_static = (task_root / "AGENTS.md").resolve()
        if _path_within(agents_path_for_static, task_root) and agents_path_for_static.exists():
            agents_source = agents_path_for_static.read_text(encoding="utf-8")
            agents_exists = True
        static_instruction_files = (
            _sync_static_instruction_files(
                channel_root=task_root,
                source_content=agents_source,
                enabled_cli_types=[cli_type],
                source_exists=agents_exists,
            )
            if agents_exists and _normalise_cli_type(cli_type) in _STATIC_INSTRUCTION_FILE_MAPPINGS
            else build_static_instruction_files_payload(
                channel_root=task_root,
                source_content=agents_source or agents_md_preview,
                source_exists=agents_exists,
                enabled_cli_types=[cli_type] if _normalise_cli_type(cli_type) in _STATIC_INSTRUCTION_FILE_MAPPINGS else [],
            )
        )
        agents_md_result["static_instruction_files"] = static_instruction_files
    else:
        static_instruction_files = {
            "source": {"fileName": _STATIC_INSTRUCTION_SOURCE_FILE, "path": "", "exists": False, "fingerprint": ""},
            "mirrors": [],
            "summary": _summarize_static_instruction_files([]),
            "repairEndpoint": _STATIC_INSTRUCTION_REPAIR_ENDPOINT,
            "mappings": static_instruction_file_mappings(),
        }
        agents_md_result = {
            "created": False,
            "path": "",
            "role": str(template_meta.get("role") or normalize_agents_md_role(agents_md_role)),
            "channelType": str(template_meta.get("channelType") or ""),
            "templateMeta": template_meta,
            "dryRun": agents_md_dry_run,
            "source": "no_task_root",
            "static_instruction_files": static_instruction_files,
        }

    return {
        "ok": True,
        "name": channel_name,
        "desc": channel_desc,
        "cli_type": cli_type,
        "agents_md": agents_md_result,
        "static_instruction_files": static_instruction_files,
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
    - Runtime run history under 运行历史记录 is intentionally kept.
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
