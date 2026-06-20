#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
向指定 Agent 会话发送标准化初始化训练消息。

适用：
1. 新建 Agent 首发初始化训练；
2. 已有通道新增专项 Agent 时补发统一培训消息；
3. 会话轮换/重置后的新主会话接管。

说明：
- 保留 send_agent_startup_training.py 作为旧入口；
- 本脚本对应 agent-init-training-playbook，补齐 fresh/rotation 两类场景、
  固定回执模板，以及 callback_to/source_ref 等结构化字段。
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any
from urllib import error as urlerror
from urllib import request as urlrequest

try:
    import tomllib  # py311+
except Exception:  # pragma: no cover
    tomllib = None  # type: ignore[assignment]


REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / "config.toml"
LEDGER_PATH = REPO_ROOT / ".codex" / "state" / "agent_init_training_ledger.v1.json"
DEFAULT_SKILLS_FRESH = ["codex-agent-collaboration", "webtag-ccb-bridge"]
DEFAULT_SKILLS_ROTATION = [
    "codex-agent-collaboration",
    "webtag-ccb-bridge",
    "agent-session-rotation-handoff",
]


def _json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)


def _http_request_json(
    *,
    method: str,
    url: str,
    payload: dict[str, Any],
    token: str = "",
    timeout_s: int = 30,
) -> dict[str, Any]:
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json; charset=utf-8",
    }
    if token:
        headers["X-TaskDashboard-Token"] = token
    req = urlrequest.Request(
        url=url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method=method.upper(),
    )
    try:
        with urlrequest.urlopen(req, timeout=timeout_s) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw else {}
    except urlerror.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url} -> HTTP {e.code}: {body}") from e
    except Exception as e:
        raise RuntimeError(f"{method} {url} failed: {e}") from e


def _http_get_json(
    *,
    url: str,
    token: str = "",
    timeout_s: int = 15,
) -> dict[str, Any]:
    headers = {"Accept": "application/json"}
    if token:
        headers["X-TaskDashboard-Token"] = token
    req = urlrequest.Request(url=url, headers=headers, method="GET")
    try:
        with urlrequest.urlopen(req, timeout=timeout_s) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw else {}
    except urlerror.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GET {url} -> HTTP {e.code}: {body}") from e
    except Exception as e:
        raise RuntimeError(f"GET {url} failed: {e}") from e


def _load_project_cfg(project_id: str) -> dict[str, Any]:
    if tomllib is None:
        return {}
    try:
        data = tomllib.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    for row in data.get("projects") or []:
        if isinstance(row, dict) and str(row.get("id") or "").strip() == project_id:
            return row
    return {}


def _load_ledger() -> dict[str, Any]:
    try:
        if not LEDGER_PATH.exists():
            return {"version": 1, "entries": {}}
        data = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"version": 1, "entries": {}}
        entries = data.get("entries")
        if not isinstance(entries, dict):
            data["entries"] = {}
        data.setdefault("version", 1)
        return data
    except Exception:
        return {"version": 1, "entries": {}}


def _save_ledger(data: dict[str, Any]) -> None:
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    LEDGER_PATH.write_text(_json_dumps(data), encoding="utf-8")


def _ledger_key(project_id: str, session_id: str) -> str:
    return f"{project_id}::{session_id}"


def _enforce_send_once_gate(
    *,
    project_id: str,
    session_id: str,
    allow_force_resend: bool,
) -> dict[str, Any]:
    ledger = _load_ledger()
    entries = ledger.setdefault("entries", {})
    key = _ledger_key(project_id, session_id)
    hit = entries.get(key)
    if hit and not allow_force_resend:
        raise SystemExit(
            "refuse_duplicate_init_training: "
            f"project_id={project_id} session_id={session_id} "
            f"existing_run_id={str(hit.get('run_id') or '').strip() or 'unknown'} "
            f"sent_at={str(hit.get('sent_at') or '').strip() or 'unknown'}; "
            "同一 Agent 初始化培训默认只允许发送一次。若确需重发，请显式传 --force-resend。"
        )
    return ledger


def _enforce_history_send_once_gate(
    *,
    base_url: str,
    project_id: str,
    session_id: str,
    token: str,
    allow_force_resend: bool,
    limit: int = 50,
) -> None:
    runs_data = _http_get_json(
        url=f"{base_url}/api/codex/runs?projectId={project_id}&sessionId={session_id}&limit={int(limit)}",
        token=token,
        timeout_s=20,
    )
    runs = runs_data.get("runs") if isinstance(runs_data, dict) else None
    if not isinstance(runs, list):
        raise SystemExit(
            "refuse_unknown_history_gate: "
            f"project_id={project_id} session_id={session_id}; "
            "无法确认该 Agent 是否已收过初始化培训，默认拒绝发送。"
        )
    if allow_force_resend:
        return
    for row in runs:
        if not isinstance(row, dict):
            continue
        message_preview = str(row.get("messagePreview") or "").strip()
        if message_preview.startswith("[Agent初始化训练]") or message_preview.startswith("[Agent启动培训]"):
            run_id = str(row.get("id") or "").strip() or "unknown"
            created_at = str(row.get("createdAt") or "").strip() or "unknown"
            raise SystemExit(
                "refuse_duplicate_init_training_by_history: "
                f"project_id={project_id} session_id={session_id} "
                f"existing_run_id={run_id} created_at={created_at}; "
                "该 Agent 历史上已经收过初始化培训，默认不再重复发送。若确需重发，请显式传 --force-resend。"
            )


def _resolve_channel_folder(project_id: str, channel_name: str) -> str:
    project_cfg = _load_project_cfg(project_id)
    task_root_rel = str(project_cfg.get("task_root_rel") or "").strip()
    if not task_root_rel:
        return f"任务规划/{channel_name}/"
    base = REPO_ROOT / task_root_rel
    try:
        if not base.is_absolute():
            base = base.resolve()
    except Exception:
        pass
    return str((base / channel_name).relative_to(REPO_ROOT))


def _pick_skills(mode: str, skills: list[str]) -> list[str]:
    if skills:
        return [str(v).strip() for v in skills if str(v).strip()]
    if mode == "rotation":
        return list(DEFAULT_SKILLS_ROTATION)
    return list(DEFAULT_SKILLS_FRESH)


def _build_skill_line(skills: list[str]) -> str:
    if not skills:
        return "无"
    return "、".join(skills)


def _is_gemini_cli(cli_type: str) -> bool:
    return str(cli_type or "").strip().lower() == "gemini"


def _build_message_cli_guidance(cli_type: str = "") -> str:
    if _is_gemini_cli(cli_type):
        return (
            "7. Gemini 工具降级口径：你是 `cli_type=gemini` Agent，只能使用当前实际可见工具，"
            "例如 `read_file`、`grep_search`、`cli_help`；不要调用不存在的 `run_shell_command`、"
            "`list_directory` 或 Codex/Claude 专属工具。\n"
            "8. 初始化阶段不强制发送“通讯录验证消息”；若能读取项目真源，请直接按固定结构完成初始化。"
            "若工具不可用或项目真源不可读，只回唯一阻塞和所需协同，不伪造已完成。\n"
            "9. 如后续需要正式发消息，可优先尝试 `python3 -m task_dashboard.message_cli send --to-agent <目标Agent> --mode dialog_now --wait-verify --json`；"
            "但 message CLI 只是 `POST /api/codex/announce` 的封装，不是第二套消息协议。\n"
            "10. `--wait-verify` 只等待送达证据，不等待目标 Agent 完成业务处理；"
            "送达证据必须是 `announce_run_id + target_session_id一致 + visible_in_channel_chat=true`。\n"
            "11. CLI 默认优先读取 live stable 真源 `.runtime/stable/.sessions`，再兼容回退根 `.sessions`；跨项目发送不要手工补复杂 root。\n"
            "12. 目标缺失、多候选、会话不可用或上下文耗尽时，按 CLI 输出的 "
            "`blocking_error.lookup_roots` 与 `blocking_error.next_action` 转会话治理/主负责位处理；不要手工翻 `message_cli.py`、旧 registry 或 `.sessions` 旁路发送。\n"
            "13. 你若回“已发出正式消息/已通知通道/已送达”，至少要带 `announce_run_id`；"
            "没有就只能写“已生成待发送正文”或“阻塞未发送”。\n"
            "14. 不允许只改文件不回消息，除非明确是 notify_only。\n"
        )
    return (
        "7. 正式发消息的最短路径优先用："
        "`python3 -m task_dashboard.message_cli send --to-agent <目标Agent> --mode dialog_now --wait-verify --json`；"
        "需要业务回执时改用 `--mode task_with_receipt --callback-session-id <回执会话>`。\n"
        "8. 回送结构化结果优先用 `python3 -m task_dashboard.message_cli receipt --to-agent <目标Agent> --wait-verify --json`；"
        "`send/receipt` 都只是 `POST /api/codex/announce` 的封装，不是第二套消息协议。\n"
        "9. `--wait-verify` 只等待送达证据，不等待目标 Agent 完成业务处理；"
        "送达证据必须是 `announce_run_id + target_session_id一致 + visible_in_channel_chat=true`。\n"
        "10. CLI 默认优先读取 live stable 真源 `.runtime/stable/.sessions`，再兼容回退根 `.sessions`；跨项目发送不要手工补复杂 root。\n"
        "11. 目标缺失、多候选、会话不可用或上下文耗尽时，按 CLI 输出的 "
        "`blocking_error.lookup_roots` 与 `blocking_error.next_action` 转会话治理/主负责位处理；不要手工翻 `message_cli.py`、旧 registry 或 `.sessions` 旁路发送。\n"
        "12. 你若回“已发出正式消息/已通知通道/已送达”，至少要带 `announce_run_id`；"
        "没有就只能写“已生成待发送正文”或“阻塞未发送”。\n"
        "13. 不允许只改文件不回消息，除非明确是 notify_only。\n"
    )


def _build_fresh_message(
    *,
    agent_name: str,
    session_id: str,
    channel_name: str,
    channel_folder: str,
    role: str,
    current_workstream: str,
    out_of_scope: str,
    first_action: str,
    skills: list[str],
    callback_session_id: str,
    target_cli_type: str = "",
) -> str:
    callback_line = (
        f"优先回给 callback_to.session_id={callback_session_id}。"
        if callback_session_id
        else "若消息中存在 callback_to.session_id，优先回给该 session。"
    )
    return (
        "[Agent初始化训练]\n"
        f"场景: 全新初始化\n"
        f"专项 Agent: {agent_name}\n"
        f"你的 session_id: {session_id}\n"
        f"所属通道: {channel_name}\n"
        f"角色边界: {role}\n\n"
        "请先完成 6 件事：\n"
        f"1. 明确职责边界：你当前只负责 `{role}`，不替代主位决策。\n"
        f"2. 对齐主线：当前唯一主线是 `{current_workstream}`；不做范围是 `{out_of_scope}`。\n"
        f"3. 阅读知识入口：优先阅读 `{channel_folder}` 下的 `README.md`、`任务/`、`问题/`、`反馈/`（如存在）、`产出物/材料/`、`产出物/沉淀/`。\n"
        "4. 若通道内已有任务、问题簇或冻结主线，先判断“并入现有主线”还是“新开独立线”，不要直接另起炉灶。\n"
        "5. 启动顺序固定为：先完成知识阅读并回复“已完成初始化”，再开始首个动作。\n"
        f"6. 学习建议技能：{_build_skill_line(skills)}。\n\n"
        "协作硬要求：\n"
        f"1. 你后续给任何 Agent 发消息时，必须带上自己的 session_id（{session_id}）。\n"
        f"2. {callback_line}\n"
        "3. 跨 Agent / 跨通道正式协作必须走系统正式发送链路；内部 spawn 或草稿整理不算“已通知”。\n"
        "4. 默认处理后回原发送 Agent；只有明确写“无需回执/仅接收”时才不回传。\n"
        "5. `task_with_receipt / dialog_now` 收到后要先首回执，处理完成后再回结构化结果；只有明确是 notify_only 才可不回。\n"
        "6. 回执至少包含：当前结论 / 是否通过或放行 / 唯一阻塞（若有） / 关键路径或 run_id / 下一步动作。\n"
        f"{_build_message_cli_guidance(target_cli_type)}\n"
        f"首个动作: {first_action}\n\n"
        "请仅按以下结构回复：\n"
        "已完成初始化\n"
        "职责边界: <一句话>\n"
        "当前主线: <一句话>\n"
        "唯一阻塞: <无/一句话>\n"
        "首个动作: <一句话>\n"
        "回执口径: <一句话>\n"
    )


def _build_rotation_message(
    *,
    agent_name: str,
    session_id: str,
    channel_name: str,
    channel_folder: str,
    role: str,
    current_workstream: str,
    out_of_scope: str,
    first_action: str,
    skills: list[str],
    callback_session_id: str,
    old_session_id: str,
    new_session_id: str,
    target_cli_type: str = "",
) -> str:
    callback_line = (
        f"优先回给 callback_to.session_id={callback_session_id}。"
        if callback_session_id
        else "若消息中存在 callback_to.session_id，优先回给该 session。"
    )
    return (
        "[Agent初始化训练]\n"
        "场景: 会话轮换/重置接管\n"
        f"专项 Agent: {agent_name}\n"
        f"所属通道: {channel_name}\n"
        f"旧 session_id: {old_session_id}\n"
        f"新 session_id: {new_session_id}\n"
        f"当前接管 session_id: {session_id}\n"
        f"角色边界: {role}\n\n"
        "请按以下顺序完成：\n"
        "1. 先继承旧会话交接资料；旧会话可用时优先采用旧会话自交接。\n"
        f"2. 对齐当前主线：`{current_workstream}`；不做范围：`{out_of_scope}`。\n"
        f"3. 阅读知识入口：`{channel_folder}` 下的 `README.md`、`任务/`、`问题/`、`反馈/`（如存在）、`产出物/材料/`、`产出物/沉淀/`。\n"
        "4. 若通道已有任务、问题簇或冻结主线，先判断“并入现有主线”还是“新开独立线”；至少核对当前任务链是否仍连续。\n"
        "5. 启动顺序固定为：先完成知识阅读并回复“已完成初始化”，再开始首个动作。\n"
        f"6. 学习建议技能：{_build_skill_line(skills)}。\n"
        f"7. 明确首个动作：{first_action}\n"
        "8. 大文件处理门禁：若交接涉及大 jsonl、完整日志、完整 msg/last、全量附件、上下文耗尽、`Codex ran out of room in the model's context window`、远端压缩失败、`remote compaction failed`、`Failed to run pre-sampling compact`、`failed to record rollout items: thread ... not found`、连续超时、长期 queued、external busy、服务重启后恢复仍失败或 resume 后 compact 仍失败，只读摘要、索引、最近 run meta、lastPreview/partialPreview 与截断预览；不得全量读取整段历史、大 jsonl、完整日志、完整 msg/last、全量附件，也不得要求从头复盘项目、全量扫描任务目录或回看所有 run。\n\n"
        "协作硬要求：\n"
        f"1. 你后续给任何 Agent 发消息时，必须带上自己的 session_id（{session_id}）。\n"
        f"2. {callback_line}\n"
        "3. 跨 Agent / 跨通道正式协作必须走系统正式发送链路；内部 spawn 或草稿整理不算“已通知”。\n"
        "4. 默认处理后回原发送 Agent；只有明确写“无需回执/仅接收”时才不回传。\n"
        "5. `task_with_receipt / dialog_now` 收到后要先首回执，处理完成后再回结构化结果；只有明确是 notify_only 才可不回。\n"
        "6. 轮换场景下，`OK` 只能作为最后的连通性验收，不能替代继承/初始化回执。\n"
        f"{_build_message_cli_guidance(target_cli_type)}\n"
        "请仅按以下结构回复：\n"
        "已完成继承\n"
        "当前主线: <一句话>\n"
        "唯一阻塞: <无/一句话>\n"
        "继续执行口径: <一句话>\n\n"
        "已完成初始化\n"
        "职责边界: <一句话>\n"
        "回执口径: <一句话>\n"
        "当前任务承接链路: <已核对，无需补口 / 待补口 + 一句话>\n"
        "首个动作: <一句话>\n"
    )


def _build_payload(args: argparse.Namespace) -> dict[str, Any]:
    project_id = str(args.project_id).strip()
    channel_name = str(args.channel_name).strip()
    session_id = str(args.session_id).strip()
    mode = str(args.mode).strip().lower()
    channel_folder = _resolve_channel_folder(project_id, channel_name)
    skills = _pick_skills(mode, list(args.skill or []))
    current_workstream = str(args.current_workstream).strip()
    out_of_scope = str(args.out_of_scope).strip()
    role = str(args.role).strip()
    first_action = str(args.first_action).strip()
    callback_session_id = str(args.callback_session_id or "").strip()
    target_cli_type = str(getattr(args, "target_cli_type", "") or "").strip()

    if mode == "rotation":
        old_session_id = str(args.old_session_id or "").strip()
        new_session_id = str(args.new_session_id or session_id).strip()
        if not old_session_id:
            raise SystemExit("--mode rotation 时必须提供 --old-session-id")
        message = _build_rotation_message(
            agent_name=str(args.agent_name).strip(),
            session_id=session_id,
            channel_name=channel_name,
            channel_folder=channel_folder,
            role=role,
            current_workstream=current_workstream,
            out_of_scope=out_of_scope,
            first_action=first_action,
            skills=skills,
            callback_session_id=callback_session_id,
            old_session_id=old_session_id,
            new_session_id=new_session_id,
            target_cli_type=target_cli_type,
        )
    else:
        message = _build_fresh_message(
            agent_name=str(args.agent_name).strip(),
            session_id=session_id,
            channel_name=channel_name,
            channel_folder=channel_folder,
            role=role,
            current_workstream=current_workstream,
            out_of_scope=out_of_scope,
            first_action=first_action,
            skills=skills,
            callback_session_id=callback_session_id,
            target_cli_type=target_cli_type,
        )

    payload: dict[str, Any] = {
        "projectId": project_id,
        "channelName": channel_name,
        "sessionId": session_id,
        "sender_type": "agent",
        "sender_id": str(args.sender_id).strip(),
        "sender_name": str(args.sender_name).strip(),
        "message": message,
        "interaction_mode": "task_with_receipt",
        "message_kind": str(args.message_kind).strip(),
    }
    source_channel_name = str(args.source_channel_name or "").strip()
    source_session_id = str(args.source_session_id or "").strip()
    source_run_id = str(args.source_run_id or "").strip()
    if source_channel_name or source_session_id or source_run_id:
        payload["source_ref"] = {
            "project_id": project_id,
            "channel_name": source_channel_name,
            "session_id": source_session_id,
            "run_id": source_run_id,
        }
    callback_channel_name = str(args.callback_channel_name or "").strip()
    if callback_channel_name or callback_session_id:
        payload["callback_to"] = {
            "channel_name": callback_channel_name,
            "session_id": callback_session_id,
        }
    if str(args.agent_name).strip() or str(args.agent_alias).strip():
        payload["owner_ref"] = {
            "channel_name": channel_name,
            "agent_name": str(args.agent_name).strip(),
            "session_id": session_id,
            "alias": str(args.agent_alias or args.agent_name).strip(),
        }
    if str(args.sender_session_id or "").strip():
        payload["sender_agent_ref"] = {
            "agent_name": str(args.sender_name).strip(),
            "session_id": str(args.sender_session_id).strip(),
            "alias": str(args.sender_alias or args.sender_name).strip(),
        }
    payload["run_extra_meta"] = {
        "trigger_type": "agent_init_training",
        "init_mode": mode,
        "current_workstream": current_workstream,
        "channel_folder": channel_folder,
        "recommended_skills": skills,
        "allow_non_primary": bool(getattr(args, "allow_non_primary", False)),
    }
    return payload


def _verify_training_target(
    *,
    base_url: str,
    session_id: str,
    token: str,
    allow_non_primary: bool,
) -> dict[str, Any]:
    detail = _http_get_json(
        url=f"{base_url}/api/sessions/{session_id}",
        token=token,
        timeout_s=15,
    )
    is_primary = bool(detail.get("is_primary"))
    session_role = str(detail.get("session_role") or "").strip().lower()
    if is_primary or session_role == "primary":
        return detail
    if allow_non_primary:
        return detail
    alias = str(detail.get("alias") or "").strip() or session_id
    channel_name = str(detail.get("channel_name") or "").strip()
    raise SystemExit(
        "refuse_non_primary_target: "
        f"session_id={session_id} alias={alias} channel={channel_name} "
        f"is_primary={is_primary} session_role={session_role or 'unknown'}; "
        "初始化培训默认只允许主会话。若确需对候选/child 会话单独培训，请显式传 --allow-non-primary。"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="向指定 Agent 会话发送标准化初始化训练消息")
    ap.add_argument("--project-id", default="task_dashboard")
    ap.add_argument("--channel-name", required=True)
    ap.add_argument("--session-id", required=True)
    ap.add_argument("--agent-name", required=True)
    ap.add_argument("--agent-alias", default="")
    ap.add_argument("--role", default="专项执行与回执收口")
    ap.add_argument("--mode", choices=("fresh", "rotation"), default="fresh")
    ap.add_argument("--current-workstream", required=True)
    ap.add_argument("--out-of-scope", default="不自行扩题，不替代主位决策")
    ap.add_argument("--first-action", default="先阅读通道知识入口，再按固定结构回复初始化回执")
    ap.add_argument("--old-session-id", default="")
    ap.add_argument("--new-session-id", default="")
    ap.add_argument("--skill", action="append", default=[])
    ap.add_argument("--message-kind", default="collab_update")
    ap.add_argument("--source-channel-name", default="")
    ap.add_argument("--source-session-id", default="")
    ap.add_argument("--source-run-id", default="")
    ap.add_argument("--callback-channel-name", default="")
    ap.add_argument("--callback-session-id", default="")
    ap.add_argument("--target-cli-type", default="", help="目标 Agent 的 CLI 类型；gemini 时使用 Gemini 初始化降级口径")
    ap.add_argument("--sender-id", default="agent:辅助01-结构治理")
    ap.add_argument("--sender-name", default="辅助01-结构治理")
    ap.add_argument("--sender-session-id", default="")
    ap.add_argument("--sender-alias", default="")
    ap.add_argument(
        "--allow-non-primary",
        action="store_true",
        help="显式允许对子会话/候选会话发送初始化培训；默认拒绝，避免批量误发。",
    )
    ap.add_argument(
        "--force-resend",
        action="store_true",
        help="显式允许对已发过初始化培训的 session 重发；默认拒绝重复发送。",
    )
    ap.add_argument("--port", type=int, default=18765)
    ap.add_argument("--base-url", default="")
    ap.add_argument("--token", default=os.environ.get("TASK_DASHBOARD_TOKEN", ""))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    base_url = str(args.base_url or f"http://127.0.0.1:{int(args.port)}").rstrip("/")
    project_id = str(args.project_id).strip()
    session_id = str(args.session_id).strip()
    ledger = _enforce_send_once_gate(
        project_id=project_id,
        session_id=session_id,
        allow_force_resend=bool(args.force_resend),
    )
    target_detail = _verify_training_target(
        base_url=base_url,
        session_id=session_id,
        token=str(args.token or "").strip(),
        allow_non_primary=bool(args.allow_non_primary),
    )
    _enforce_history_send_once_gate(
        base_url=base_url,
        project_id=project_id,
        session_id=session_id,
        token=str(args.token or "").strip(),
        allow_force_resend=bool(args.force_resend),
    )
    payload = _build_payload(args)
    result: dict[str, Any] = {
        "project_id": project_id,
        "channel_name": str(args.channel_name).strip(),
        "session_id": session_id,
        "agent_name": str(args.agent_name).strip(),
        "mode": str(args.mode).strip(),
        "dry_run": bool(args.dry_run),
        "target_session": {
            "alias": str(target_detail.get("alias") or "").strip(),
            "channel_name": str(target_detail.get("channel_name") or "").strip(),
            "is_primary": bool(target_detail.get("is_primary")),
            "session_role": str(target_detail.get("session_role") or "").strip(),
        },
        "send_once_gate": {
            "ledger_path": str(LEDGER_PATH),
            "force_resend": bool(args.force_resend),
        },
        "payload": payload,
    }
    if not args.dry_run:
        response = _http_request_json(
            method="POST",
            url=f"{base_url}/api/codex/announce",
            payload=payload,
            token=str(args.token or "").strip(),
            timeout_s=30,
        )
        result["response"] = response
        run_id = ""
        if isinstance(response, dict):
            run = response.get("run")
            if isinstance(run, dict):
                run_id = str(run.get("id") or "").strip()
        entries = ledger.setdefault("entries", {})
        entries[_ledger_key(project_id, session_id)] = {
            "project_id": project_id,
            "session_id": session_id,
            "channel_name": str(args.channel_name).strip(),
            "agent_name": str(args.agent_name).strip(),
            "run_id": run_id,
            "sent_at": entries.get(_ledger_key(project_id, session_id), {}).get("sent_at") or "",
            "mode": str(args.mode).strip(),
        }
        if not entries[_ledger_key(project_id, session_id)]["sent_at"]:
            from datetime import datetime

            entries[_ledger_key(project_id, session_id)]["sent_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
        _save_ledger(ledger)
    print(_json_dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
