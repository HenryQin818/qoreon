# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any, Mapping

from task_dashboard.helpers import looks_like_uuid, safe_text


def compose_channel_display_name(channel_kind: str, channel_index: str, channel_name: str) -> tuple[str, str]:
    kind = safe_text(channel_kind, 20).strip()
    index = safe_text(channel_index, 40).strip()
    theme = safe_text(channel_name, 200).strip()
    prefix = f"{kind}{index}-"
    if theme.startswith(prefix):
        return theme, theme[len(prefix) :]
    return f"{prefix}{theme}" if theme else prefix.rstrip("-"), theme


def normalize_channel_bootstrap_v3_request(body: Mapping[str, Any] | None) -> dict[str, str]:
    row = body if isinstance(body, Mapping) else {}
    mode = safe_text(row.get("mode") if "mode" in row else row.get("workflowMode"), 40).strip().lower()
    mode = mode.replace("-", "_").replace(" ", "_")
    if mode not in {"direct", "agent_assist"}:
        mode = "direct"
    channel_kind = safe_text(row.get("channelKind"), 20).strip()
    channel_index = safe_text(row.get("channelIndex"), 40).strip()
    channel_theme = safe_text(row.get("channelName"), 200).strip()
    channel_name, normalized_theme = compose_channel_display_name(channel_kind, channel_index, channel_theme)

    return {
        "project_id": safe_text(row.get("projectId"), 80).strip(),
        "mode": mode,
        "channel_kind": channel_kind,
        "channel_index": channel_index,
        "channel_theme": normalized_theme,
        "channel_name": channel_name,
        "channel_desc": safe_text(
            row.get("channelDesc") if "channelDesc" in row else row.get("desc"),
            500,
        ).strip(),
        "target_session_id": safe_text(
            row.get("targetSessionId") if "targetSessionId" in row else row.get("target_session_id"),
            80,
        ).strip(),
        "business_requirement": safe_text(
            row.get("businessRequirement")
            if "businessRequirement" in row
            else row.get("business_requirement"),
            20_000,
        ).strip(),
        "prompt_preset": safe_text(
            row.get("promptPreset") if "promptPreset" in row else row.get("prompt_preset"),
            80,
        ).strip() or "channel_create_assist_v1",
        "source_session_id": safe_text(
            row.get("sourceSessionId") if "sourceSessionId" in row else row.get("source_session_id"),
            80,
        ).strip(),
        "source_channel_name": safe_text(
            row.get("sourceChannelName") if "sourceChannelName" in row else row.get("source_channel_name"),
            200,
        ).strip(),
        "source_agent_name": safe_text(
            row.get("sourceAgentName") if "sourceAgentName" in row else row.get("source_agent_name"),
            200,
        ).strip() or "任务看板",
        "source_agent_alias": safe_text(
            row.get("sourceAgentAlias") if "sourceAgentAlias" in row else row.get("source_agent_alias"),
            200,
        ).strip(),
        "source_agent_id": safe_text(
            row.get("sourceAgentId") if "sourceAgentId" in row else row.get("source_agent_id"),
            80,
        ).strip() or "task_dashboard",
    }


def normalize_channel_request_edit_request(body: Mapping[str, Any] | None) -> dict[str, str]:
    row = body if isinstance(body, Mapping) else {}
    project_id = safe_text(row.get("projectId") if "projectId" in row else row.get("project_id"), 80).strip()
    channel_name = safe_text(row.get("channelName") if "channelName" in row else row.get("channel_name"), 200).strip()
    channel_desc = safe_text(row.get("channelDesc") if "channelDesc" in row else row.get("channel_desc"), 500).strip()
    target_session_id = safe_text(
        row.get("targetSessionId") if "targetSessionId" in row else row.get("target_session_id"),
        80,
    ).strip()
    business_requirement = safe_text(
        row.get("businessRequirement")
        if "businessRequirement" in row
        else row.get("business_requirement"),
        20_000,
    ).strip()
    return {
        "project_id": project_id,
        "channel_name": channel_name,
        "channel_desc": channel_desc,
        "target_session_id": target_session_id,
        "business_requirement": business_requirement,
        "source_session_id": safe_text(
            row.get("sourceSessionId") if "sourceSessionId" in row else row.get("source_session_id"),
            80,
        ).strip(),
        "source_channel_name": safe_text(
            row.get("sourceChannelName") if "sourceChannelName" in row else row.get("source_channel_name"),
            200,
        ).strip(),
        "source_agent_name": safe_text(
            row.get("sourceAgentName") if "sourceAgentName" in row else row.get("source_agent_name"),
            200,
        ).strip() or "任务看板",
        "source_agent_alias": safe_text(
            row.get("sourceAgentAlias") if "sourceAgentAlias" in row else row.get("source_agent_alias"),
            200,
        ).strip(),
        "source_agent_id": safe_text(
            row.get("sourceAgentId") if "sourceAgentId" in row else row.get("source_agent_id"),
            80,
        ).strip() or "task_dashboard",
    }


def _trim_text(value: Any, max_len: int = 4000) -> str:
    return safe_text(value, max_len).strip()


def build_channel_assist_message_payload(
    *,
    project_id: str,
    created_channel_name: str,
    created_channel_theme: str,
    created_channel_desc: str,
    target_session: Mapping[str, Any] | None,
    business_requirement: str,
    prompt_preset: str,
    source_session_id: str = "",
    source_channel_name: str = "",
    source_agent_name: str = "任务看板",
    source_agent_alias: str = "",
    source_agent_id: str = "task_dashboard",
) -> dict[str, Any]:
    session = target_session if isinstance(target_session, Mapping) else {}
    target_session_id = _trim_text(session.get("sessionId") or session.get("session_id") or session.get("id"), 80)
    target_channel_name = _trim_text(
        session.get("channel_name")
        or session.get("primaryChannel")
        or session.get("channelName")
        or session.get("displayChannel")
        or "",
        200,
    )
    target_alias = _trim_text(
        session.get("alias")
        or session.get("display_name")
        or session.get("displayName")
        or target_channel_name
        or target_session_id
        or "",
        200,
    )
    target_cli_type = _trim_text(session.get("cli_type") or session.get("cliType") or "codex", 40) or "codex"
    target_model = _trim_text(session.get("model") or "", 120)
    target_reasoning = _trim_text(session.get("reasoning_effort") or session.get("reasoningEffort") or "", 40)
    origin_channel_name = _trim_text(source_channel_name or created_channel_name, 200)
    origin_session_id = _trim_text(source_session_id, 80)
    origin_agent_name = _trim_text(source_agent_name, 200) or "任务看板"
    origin_agent_alias = _trim_text(source_agent_alias, 200) or origin_agent_name
    theme_name = _trim_text(created_channel_theme, 200) or created_channel_name
    created_desc = _trim_text(created_channel_desc, 500)
    req = _trim_text(business_requirement, 20_000)
    preset = _trim_text(prompt_preset, 80) or "channel_create_assist_v1"

    message = "\n".join(
        [
            "[新增通道 v3 - Agent辅助创建]",
            f"项目: {project_id}",
            f"已创建空通道框架: {created_channel_name}",
            f"通道主题: {theme_name}",
            f"通道说明: {created_desc or created_channel_name}",
            f"处理Agent: {target_alias or target_channel_name or target_session_id}",
            f"处理Agent会话: {target_session_id or '-'}",
            f"提示词预设: {preset}",
            "",
            "文件维度:",
            "- `README.md`：通道说明与目录结构索引",
            "- `沟通-收件箱.md`：通道沟通收件箱",
            "- `任务/`：后续任务拆解与执行",
            "- `产出物/沉淀/`：阶段成果与沉淀",
            "- `反馈/`：反馈与验收回执",
            "- `问题/`：问题留痕与聚合",
            "- `讨论空间/`：协作讨论与澄清",
            "",
            "边界:",
            "- 仅基于已创建的空框架继续补齐，不要把 direct 模式不该生成的主任务/主对话补出来。",
            "- 信息不足时先回执追问，不要擅自扩展到无关专项。",
            "- 回执请直接给出可执行建议、缺口与下一步。",
            "",
            "业务要求:",
            req or "-",
        ]
    )

    source_ref: dict[str, str] = {
        "project_id": project_id,
            "channel_name": origin_channel_name or created_channel_name,
            "channel_theme": theme_name,
        }
    if origin_session_id and looks_like_uuid(origin_session_id):
        source_ref["session_id"] = origin_session_id

    callback_to: dict[str, str] = {"channel_name": origin_channel_name or created_channel_name}
    if origin_session_id and looks_like_uuid(origin_session_id):
        callback_to["session_id"] = origin_session_id

    target_ref: dict[str, str] = {
        "project_id": project_id,
        "channel_name": target_channel_name or target_alias or created_channel_name,
    }
    if target_session_id and looks_like_uuid(target_session_id):
        target_ref["session_id"] = target_session_id

    sender_agent_ref: dict[str, str] = {
        "agent_name": origin_agent_name,
        "alias": origin_agent_alias,
    }
    if origin_session_id and looks_like_uuid(origin_session_id):
        sender_agent_ref["session_id"] = origin_session_id

    return {
        "message": message,
        "sender_fields": {
            "sender_type": "agent",
            "sender_id": source_agent_id or "task_dashboard",
            "sender_name": origin_agent_name or "任务看板",
        },
        "run_extra_fields": {
            "message_kind": "collab_update",
            "interaction_mode": "task_with_receipt",
            "dispatch_mode": "agent_assist",
            "workflow_mode": "bootstrap_v3",
            "prompt_preset": preset,
            "business_requirement": req,
            "channel_bootstrap": {
                "mode": "agent_assist",
                "project_id": project_id,
                "channel_name": created_channel_name,
                "channel_theme": theme_name,
                "channel_desc": created_desc or created_channel_name,
            },
            "source_ref": source_ref,
            "target_ref": target_ref,
            "callback_to": callback_to,
            "sender_agent_ref": sender_agent_ref,
            "target_agent_ref": {
                "agent_name": target_alias or target_channel_name or target_session_id,
                "alias": target_alias or target_channel_name or target_session_id,
                **({"session_id": target_session_id} if target_session_id and looks_like_uuid(target_session_id) else {}),
            },
        },
        "target_session_id": target_session_id,
        "target_session_channel_name": target_channel_name or target_alias or created_channel_name,
        "target_session_alias": target_alias or target_channel_name or target_session_id,
        "target_cli_type": target_cli_type,
        "target_model": target_model,
        "target_reasoning_effort": target_reasoning,
    }


def build_channel_edit_request_message_payload(
    *,
    project_id: str,
    channel_name: str,
    channel_desc: str,
    target_session: Mapping[str, Any] | None,
    business_requirement: str,
    source_session_id: str = "",
    source_channel_name: str = "",
    source_agent_name: str = "任务看板",
    source_agent_alias: str = "",
    source_agent_id: str = "task_dashboard",
) -> dict[str, Any]:
    session = target_session if isinstance(target_session, Mapping) else {}
    target_session_id = _trim_text(session.get("sessionId") or session.get("session_id") or session.get("id"), 80)
    target_channel_name = _trim_text(
        session.get("channel_name")
        or session.get("primaryChannel")
        or session.get("channelName")
        or session.get("displayChannel")
        or "",
        200,
    )
    target_alias = _trim_text(
        session.get("alias")
        or session.get("display_name")
        or session.get("displayName")
        or target_channel_name
        or target_session_id
        or "",
        200,
    )
    target_cli_type = _trim_text(session.get("cli_type") or session.get("cliType") or "codex", 40) or "codex"
    target_model = _trim_text(session.get("model") or "", 120)
    target_reasoning = _trim_text(session.get("reasoning_effort") or session.get("reasoningEffort") or "", 40)
    origin_channel_name = _trim_text(source_channel_name or channel_name, 200)
    origin_session_id = _trim_text(source_session_id, 80)
    origin_agent_name = _trim_text(source_agent_name, 200) or "任务看板"
    origin_agent_alias = _trim_text(source_agent_alias, 200) or origin_agent_name
    current_desc = _trim_text(channel_desc, 500)
    req = _trim_text(business_requirement, 20_000)

    message = "\n".join(
        [
            "[通道管理 - 找 Agent 编辑]",
            f"项目: {project_id}",
            f"当前通道: {channel_name}",
            f"当前说明: {current_desc or channel_name}",
            f"处理Agent: {target_alias or target_channel_name or target_session_id}",
            f"处理Agent会话: {target_session_id or '-'}",
            "",
            "边界:",
            "- 本次入口用于辅助处理通道说明/边界/配套内容，不直接删除通道。",
            "- 若涉及改名、改编号、改类型或目录迁移，请先回执确认，不要自行扩写。",
            "- 若信息不足，请先回执追问，再给出可执行建议。",
            "",
            "业务要求:",
            req or "-",
        ]
    )

    source_ref: dict[str, str] = {
        "project_id": project_id,
        "channel_name": origin_channel_name or channel_name,
    }
    if origin_session_id and looks_like_uuid(origin_session_id):
        source_ref["session_id"] = origin_session_id

    callback_to: dict[str, str] = {"channel_name": origin_channel_name or channel_name}
    if origin_session_id and looks_like_uuid(origin_session_id):
        callback_to["session_id"] = origin_session_id

    target_ref: dict[str, str] = {
        "project_id": project_id,
        "channel_name": target_channel_name or target_alias or channel_name,
    }
    if target_session_id and looks_like_uuid(target_session_id):
        target_ref["session_id"] = target_session_id

    sender_agent_ref: dict[str, str] = {
        "agent_name": origin_agent_name,
        "alias": origin_agent_alias,
    }
    if origin_session_id and looks_like_uuid(origin_session_id):
        sender_agent_ref["session_id"] = origin_session_id

    return {
        "message": message,
        "sender_fields": {
            "sender_type": "agent",
            "sender_id": source_agent_id or "task_dashboard",
            "sender_name": origin_agent_name or "任务看板",
        },
        "run_extra_fields": {
            "message_kind": "collab_update",
            "interaction_mode": "task_with_receipt",
            "dispatch_mode": "channel_request_edit",
            "workflow_mode": "channel_manage_v1",
            "business_requirement": req,
            "channel_management": {
                "action": "request_edit",
                "project_id": project_id,
                "channel_name": channel_name,
                "channel_desc": current_desc or channel_name,
            },
            "source_ref": source_ref,
            "target_ref": target_ref,
            "callback_to": callback_to,
            "sender_agent_ref": sender_agent_ref,
            "target_agent_ref": {
                "agent_name": target_alias or target_channel_name or target_session_id,
                "alias": target_alias or target_channel_name or target_session_id,
                **({"session_id": target_session_id} if target_session_id and looks_like_uuid(target_session_id) else {}),
            },
        },
        "target_session_id": target_session_id,
        "target_session_channel_name": target_channel_name or target_alias or channel_name,
        "target_session_alias": target_alias or target_channel_name or target_session_id,
        "target_cli_type": target_cli_type,
        "target_model": target_model,
        "target_reasoning_effort": target_reasoning,
    }
