from __future__ import annotations

from typing import Any

from task_dashboard.runtime.channel_admin import (
    StaticInstructionFileConflict,
    read_channel_agents_md,
    repair_channel_static_instruction_files,
    write_channel_agents_md,
)
from task_dashboard.runtime.heartbeat_registry import _clear_dashboard_cfg_cache


def _enabled_cli_types_from_query(qs: dict[str, list[str]]) -> list[str]:
    enabled: list[str] = []
    for key in ("cliType", "cli_type", "enabledCliTypes", "enabled_cli_types"):
        enabled.extend([str(item or "").strip() for item in (qs.get(key) or []) if str(item or "").strip()])
    return enabled


def handle_channel_agents_md_get(handler: Any, ctx: Any, qs: dict[str, list[str]]) -> None:
    if not ctx.require_token():
        return
    project_id = ctx.safe_text((qs.get("projectId") or qs.get("project_id") or [""])[0], 120).strip()
    channel_name = ctx.safe_text((qs.get("channelName") or qs.get("channel_name") or [""])[0], 240).strip()
    role = ctx.safe_text((qs.get("role") or qs.get("agentRole") or [""])[0], 80).strip()
    channel_type = ctx.safe_text((qs.get("channelType") or qs.get("channel_type") or qs.get("channelKind") or [""])[0], 80).strip()
    channel_desc = ctx.safe_text((qs.get("channelDesc") or qs.get("channel_desc") or [""])[0], 1000).strip()
    if not project_id or not channel_name:
        ctx.json_response(handler, 400, {"error": "missing projectId or channelName"})
        return
    try:
        payload = read_channel_agents_md(
            project_id=project_id,
            channel_name=channel_name,
            config_path=ctx.config_toml_path(),
            repo_root=ctx.repo_root(),
            role=role,
            channel_type=channel_type,
            channel_desc=channel_desc,
            enabled_cli_types=_enabled_cli_types_from_query(qs),
        )
    except PermissionError as e:
        ctx.json_response(handler, 403, {"error": str(e)})
        return
    except ValueError as e:
        ctx.json_response(handler, 404, {"error": str(e)})
        return
    except Exception as e:
        ctx.json_response(handler, 500, {"error": "read AGENTS.md failed", "message": str(e)})
        return
    ctx.json_response(handler, 200, payload)


def handle_channel_agents_md_post(handler: Any, ctx: Any) -> None:
    if not ctx.require_token():
        return
    try:
        body = ctx.read_body_json(handler, max_bytes=280_000)
    except Exception as e:
        ctx.json_response(handler, 400, {"error": "bad json", "message": str(e)})
        return
    project_id = ctx.safe_text(body.get("projectId") or body.get("project_id"), 120).strip()
    channel_name = ctx.safe_text(body.get("channelName") or body.get("channel_name"), 240).strip()
    content = str(body.get("content") if "content" in body else body.get("agentsMdContent") or "")
    enabled_cli_types = body.get("enabledCliTypes") if "enabledCliTypes" in body else body.get("enabled_cli_types")
    if enabled_cli_types in (None, ""):
        enabled_cli_types = body.get("cliType") if "cliType" in body else body.get("cli_type")
    if not project_id or not channel_name:
        ctx.json_response(handler, 400, {"error": "missing projectId or channelName"})
        return
    try:
        payload = write_channel_agents_md(
            project_id=project_id,
            channel_name=channel_name,
            content=content,
            config_path=ctx.config_toml_path(),
            repo_root=ctx.repo_root(),
            enabled_cli_types=enabled_cli_types,
        )
        _clear_dashboard_cfg_cache()
    except StaticInstructionFileConflict as e:
        ctx.json_response(handler, 409, {"error": "static instruction file conflict", "message": str(e)})
        return
    except PermissionError as e:
        ctx.json_response(handler, 403, {"error": str(e)})
        return
    except ValueError as e:
        ctx.json_response(handler, 400, {"error": str(e)})
        return
    except Exception as e:
        ctx.json_response(handler, 500, {"error": "write AGENTS.md failed", "message": str(e)})
        return
    ctx.json_response(handler, 200, payload)


def handle_static_instruction_files_repair_post(handler: Any, ctx: Any) -> None:
    if not ctx.require_token():
        return
    try:
        body = ctx.read_body_json(handler, max_bytes=20_000)
    except Exception as e:
        ctx.json_response(handler, 400, {"error": "bad json", "message": str(e)})
        return
    project_id = ctx.safe_text(body.get("projectId") or body.get("project_id"), 120).strip()
    channel_name = ctx.safe_text(body.get("channelName") or body.get("channel_name"), 240).strip()
    cli_type = ctx.safe_text(body.get("cliType") or body.get("cli_type") or "codebuddy", 80).strip() or "codebuddy"
    if not project_id or not channel_name:
        ctx.json_response(handler, 400, {"error": "missing projectId or channelName"})
        return
    try:
        static_instruction_files = repair_channel_static_instruction_files(
            project_id=project_id,
            channel_name=channel_name,
            cli_type=cli_type,
            config_path=ctx.config_toml_path(),
            repo_root=ctx.repo_root(),
        )
        _clear_dashboard_cfg_cache()
    except StaticInstructionFileConflict as e:
        ctx.json_response(handler, 409, {"error": "static instruction file conflict", "message": str(e)})
        return
    except FileNotFoundError as e:
        ctx.json_response(handler, 404, {"error": str(e)})
        return
    except PermissionError as e:
        ctx.json_response(handler, 403, {"error": str(e)})
        return
    except ValueError as e:
        ctx.json_response(handler, 400, {"error": str(e)})
        return
    except Exception as e:
        ctx.json_response(handler, 500, {"error": "repair static instruction files failed", "message": str(e)})
        return
    ctx.json_response(
        handler,
        200,
        {
            "ok": True,
            "projectId": project_id,
            "channelName": channel_name,
            "cliType": cli_type,
            "static_instruction_files": static_instruction_files,
        },
    )
