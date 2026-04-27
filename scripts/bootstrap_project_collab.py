#!/usr/bin/env python3
"""Generate project-level collaboration registry (CCR v1) from config + sessions."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import tomllib  # py311+
except Exception:  # pragma: no cover
    import tomli as tomllib  # type: ignore


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _safe_text(v: Any) -> str:
    return str(v or "").strip()


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


def _render_view(payload: dict[str, Any]) -> str:
    project = payload.get("project") if isinstance(payload.get("project"), dict) else {}
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    channels = payload.get("channels") if isinstance(payload.get("channels"), list) else []
    playbook = (
        payload.get("communication_playbook")
        if isinstance(payload.get("communication_playbook"), dict)
        else {}
    )

    lines: list[str] = []
    lines.append("# 协作通讯录视图（CCR v1）")
    lines.append("")
    lines.append(f"- generated_at: `{payload.get('generated_at')}`")
    lines.append(f"- project_id: `{project.get('project_id', '-')}`")
    lines.append(f"- project_name: `{project.get('project_name', '-')}`")
    lines.append(f"- source: `{payload.get('source', '-')}`")
    lines.append("")
    lines.append("## 汇总")
    lines.append(f"- 通道总数: `{summary.get('channel_count', 0)}`")
    lines.append(f"- Agent 总数: `{summary.get('agent_count', 0)}`")
    lines.append(f"- 已具备主会话: `{summary.get('with_primary_session', 0)}`")
    lines.append(f"- 缺少主会话: `{summary.get('without_primary_session', 0)}`")
    lines.append("")
    lines.append("## 通道清单")
    lines.append("| 通道 | 角色 | 主会话名称 | 主会话 | CLI | 候选会话数 | 状态 |")
    lines.append("| --- | --- | --- | --- | --- | ---: | --- |")
    for it in channels:
        if not isinstance(it, dict):
            continue
        lines.append(
            "| {channel} | {role} | {alias} | `{sid}` | `{cli}` | {cnt} | {status} |".format(
                channel=_safe_text(it.get("channel_name")) or "-",
                role=_safe_text(it.get("channel_role")) or "-",
                alias=_safe_text(it.get("primary_session_alias")) or "-",
                sid=_safe_text(it.get("primary_session_id")) or "-",
                cli=_safe_text(it.get("primary_cli_type")) or "-",
                cnt=int(it.get("session_candidates_count") or 0),
                status="ready" if it.get("startup_ready") else "pending",
            )
        )
    lines.append("")
    missing = summary.get("missing_primary_channels")
    if isinstance(missing, list) and missing:
        lines.append("## 待补齐")
        for name in missing:
            lines.append(f"- `{_safe_text(name)}` 缺少主会话，请先绑定后再执行通道派发。")
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
    lines.append("## 通道内 Agent 明细")
    for it in channels:
        if not isinstance(it, dict):
            continue
        channel_name = _safe_text(it.get("channel_name")) or "-"
        lines.append(f"### {channel_name}")
        lines.append("| Agent | session_id | 主/候选 | 状态 | CLI |")
        lines.append("| --- | --- | --- | --- | --- |")
        candidates = it.get("session_candidates") if isinstance(it.get("session_candidates"), list) else []
        if not candidates:
            lines.append("| - | - | - | - | - |")
        for cand in candidates:
            if not isinstance(cand, dict):
                continue
            lines.append(
                "| {agent} | `{sid}` | {kind} | `{status}` | `{cli}` |".format(
                    agent=_safe_text(cand.get("display_name")) or _safe_text(cand.get("desc")) or "-",
                    sid=_safe_text(cand.get("session_id")) or "-",
                    kind="primary" if bool(cand.get("is_primary")) else "candidate",
                    status=_safe_text(cand.get("status")) or "-",
                    cli=_safe_text(cand.get("cli_type")) or "-",
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
    cards: list[str] = []
    for channel in channels:
        if not isinstance(channel, dict):
            continue
        channel_name = _html_escape(channel.get("channel_name"))
        channel_role = _html_escape(channel.get("channel_role"))
        channel_desc = _html_escape(channel.get("channel_desc"))
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
            badges = [
                '<span class="badge primary">主会话</span>' if _safe_text(candidate.get("session_id")) == primary_sid else "",
                f'<span class="badge">{cli_type or "codex"}</span>',
                f'<span class="badge">{environment}</span>' if environment else "",
                f'<span class="badge">{session_role}</span>' if session_role else "",
            ]
            meta_items = [
                f"<div><span>session_id</span><code>{session_id}</code></div>",
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
                  <span class="pill">{channel_role}</span>
                  <span class="pill">{count} agents</span>
                </div>
              </div>
              <div class="agents">{agent_items}</div>
            </section>
            """.format(
                channel_name=channel_name,
                channel_desc=channel_desc or "未填写通道说明",
                channel_role=channel_role or "other",
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
      grid-template-columns: repeat(4, 1fr);
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
          <div class="stat"><div class="k">主会话齐备</div><div class="v">{int(summary.get("with_primary_session") or 0)}</div></div>
        </div>
      </div>
      <div class="hero-card hero-note">
        <div>
          <h2>当前口径</h2>
          <ul>
            <li>底层真源：stable `.runtime/stable/.sessions/task_dashboard.json`</li>
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
            "生成 project metadata files 与可读视图",
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
    session_alias_map = {
        _safe_text(row.get("session_id")): _safe_text(row.get("alias"))
        for row in store_session_rows
        if _safe_text(row.get("session_id")) and _safe_text(row.get("alias"))
    }
    store_channels_map: dict[str, list[dict[str, str]]] = {}
    for row in store_session_rows:
        cname = _safe_text(row.get("channel_name"))
        sid = _safe_text(row.get("session_id"))
        if not (cname and sid):
            continue
        store_channels_map.setdefault(cname, []).append(row)

    configured_channels = project.get("channels") if isinstance(project.get("channels"), list) else []
    channel_cfg_by_name: dict[str, dict[str, Any]] = {}
    for it in configured_channels:
        if not isinstance(it, dict):
            continue
        name = _safe_text(it.get("name"))
        if not name:
            continue
        channel_cfg_by_name[name] = it

    all_channel_names = sorted(set(channel_cfg_by_name.keys()) | set(store_channels_map.keys()))

    channel_rows: list[dict[str, Any]] = []
    for name in all_channel_names:
        cfg_row = channel_cfg_by_name.get(name, {})
        session_rows: list[dict[str, str]] = []
        for store_row in store_channels_map.get(name, []):
            sid = _safe_text(store_row.get("session_id"))
            if not sid:
                continue
            session_rows.append(
                {
                    "session_id": sid,
                    "desc": _safe_text(store_row.get("alias")) or sid,
                    "status": _safe_text(store_row.get("status")) or "active",
                    "model": _safe_text(store_row.get("model")),
                    "cli_type": _safe_text(store_row.get("cli_type")) or "codex",
                    "environment": _safe_text(store_row.get("environment")),
                    "workdir": _safe_text(store_row.get("workdir")),
                    "branch": _safe_text(store_row.get("branch")),
                    "session_role": _safe_text(store_row.get("session_role")),
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

        candidates: list[dict[str, Any]] = []
        for row in session_rows:
            sid = row["session_id"]
            display_name = session_alias_map.get(sid) or row["desc"]
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
                    "is_primary": bool(primary_sid and sid == primary_sid),
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
                "channel_role": _infer_channel_role(name),
                "primary_session_id": primary_sid,
                "primary_session_alias": primary_alias,
                "primary_cli_type": primary_cli,
                "session_candidates_count": len(candidates),
                "session_candidates": candidates,
                "startup_ready": bool(primary_sid),
            }
        )

    with_primary = sum(1 for row in channel_rows if row.get("startup_ready"))
    missing_primary = [str(row.get("channel_name")) for row in channel_rows if not row.get("startup_ready")]
    all_agents = [
        {
            "channel_name": row.get("channel_name"),
            "channel_role": row.get("channel_role"),
            **candidate,
        }
        for row in channel_rows
        for candidate in row.get("session_candidates", [])
    ]

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
        },
        "channels": channel_rows,
        "all_agents": all_agents,
        "communication_playbook": _build_communication_playbook(),
    }

    default_output = (project_root / "registry" / "collab-registry.v1.json").resolve()
    default_view_output = (project_root / "registry" / "collab-registry.view.md").resolve()
    default_html_output = (project_root / "artifacts" / "agent-directory" / f"{_safe_text(project.get('id'))}-agent-directory.html").resolve()
    output_path = _resolve_path(_safe_text(args.output), workspace_root) if _safe_text(args.output) else default_output
    view_output_path = (
        _resolve_path(_safe_text(args.view_output), workspace_root)
        if _safe_text(args.view_output)
        else default_view_output
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
        html_output_path.parent.mkdir(parents=True, exist_ok=True)
        html_output_path.write_text(_render_agent_directory_html(payload), encoding="utf-8")

    print(f"[ok] project_id={_safe_text(project.get('id'))}")
    print(f"[ok] channels={len(channel_rows)} with_primary={with_primary} missing={len(missing_primary)}")
    print(f"[ok] session_store={session_store_path}")
    print(f"[ok] output={output_path}")
    print(f"[ok] view_output={view_output_path}")
    print(f"[ok] html_output={html_output_path}")
    if missing_primary:
        print("[warn] missing_primary_channels:")
        for name in missing_primary:
            print(f"  - {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
