from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _read_optional_bundle(dir_path: Path, pattern: str) -> str:
    if not dir_path.exists():
        return ""
    parts = [_read_text(p) for p in sorted(dir_path.glob(pattern)) if p.is_file()]
    return "\n\n".join(part for part in parts if part)


def _split_task_bootstrap(js_text: str) -> tuple[str, str]:
    lines = js_text.splitlines()
    if len(lines) < 3:
        return "", js_text
    first = lines[0].strip()
    second = lines[1].strip()
    if not first.startswith("const DATA = JSON.parse("):
        return "", js_text
    if not second.startswith("const OVERVIEW_PAGE = "):
        return "", js_text
    bootstrap = "\n".join(lines[:2])
    body = "\n".join(lines[2:])
    return bootstrap, body


def render_from_template(script_dir: Path, template_name: str, data: dict[str, Any]) -> str:
    payload = json.dumps(data, ensure_ascii=False)

    # Prefer new web/* sources when present.
    web_dir = script_dir / "web"
    if template_name == "template.html" and (web_dir / "task.html.tpl").exists():
        tpl = _read_text(web_dir / "task.html.tpl")
        css = _read_text(web_dir / "task.css") if (web_dir / "task.css").exists() else ""
        task_parts_css = _read_optional_bundle(web_dir / "task_parts", "*.css")
        task_entry_parts_css = _read_optional_bundle(web_dir / "task_entry_parts", "*.css")
        css_suffix = "\n\n".join(
            part for part in [task_parts_css, task_entry_parts_css] if part
        )
        if css_suffix:
            css = css + "\n\n" + css_suffix if css else css_suffix
        shared = _read_text(web_dir / "shared.js") if (web_dir / "shared.js").exists() else ""
        js = _read_text(web_dir / "task.js") if (web_dir / "task.js").exists() else ""
        task_bootstrap, task_body = _split_task_bootstrap(js)
        if task_bootstrap:
            js = task_body
        task_parts_js = _read_optional_bundle(web_dir / "task_parts", "*.js")
        task_entry_parts_js = _read_optional_bundle(web_dir / "task_entry_parts", "*.js")
        js_prefix = "\n\n".join(
            part for part in [task_parts_js, task_entry_parts_js] if part
        )
        if js_prefix:
            js = js_prefix + "\n\n" + js
        if shared:
            js = shared + "\n\n" + js
        if task_bootstrap:
            js = shared + "\n\n" + task_bootstrap + "\n\n" + js_prefix + "\n\n" + task_body if shared else task_bootstrap + "\n\n" + js_prefix + "\n\n" + task_body
        tpl = tpl.replace("__INLINE_CSS__", css).replace("__INLINE_JS__", js)
        return tpl.replace("__PAYLOAD__", payload)
    if template_name == "template_overview.html" and (web_dir / "overview.html.tpl").exists():
        tpl = _read_text(web_dir / "overview.html.tpl")
        css = _read_text(web_dir / "overview.css") if (web_dir / "overview.css").exists() else ""
        shared = _read_text(web_dir / "shared.js") if (web_dir / "shared.js").exists() else ""
        js = _read_text(web_dir / "overview.js") if (web_dir / "overview.js").exists() else ""
        overview_parts_js = _read_optional_bundle(web_dir / "overview_parts", "*.js")
        js = "\n\n".join(part for part in [js, overview_parts_js] if part)
        if shared:
            js = shared + "\n\n" + js
        tpl = tpl.replace("__INLINE_CSS__", css).replace("__INLINE_JS__", js)
        return tpl.replace("__PAYLOAD__", payload)
    if template_name == "template_migration.html" and (web_dir / "migration.html.tpl").exists():
        tpl = _read_text(web_dir / "migration.html.tpl")
        css = _read_text(web_dir / "migration.css") if (web_dir / "migration.css").exists() else ""
        js = _read_text(web_dir / "migration.js") if (web_dir / "migration.js").exists() else ""
        tpl = tpl.replace("__INLINE_CSS__", css).replace("__INLINE_JS__", js)
        return tpl.replace("__PAYLOAD__", payload)
    if template_name == "template_communication.html" and (web_dir / "communication.html.tpl").exists():
        tpl = _read_text(web_dir / "communication.html.tpl")
        css = _read_text(web_dir / "communication.css") if (web_dir / "communication.css").exists() else ""
        shared = _read_text(web_dir / "shared.js") if (web_dir / "shared.js").exists() else ""
        js = _read_text(web_dir / "communication.js") if (web_dir / "communication.js").exists() else ""
        if shared:
            js = shared + "\n\n" + js
        tpl = tpl.replace("__INLINE_CSS__", css).replace("__INLINE_JS__", js)
        return tpl.replace("__PAYLOAD__", payload)
    if template_name == "template_project_chat.html" and (web_dir / "project_chat.html.tpl").exists():
        tpl = _read_text(web_dir / "project_chat.html.tpl")
        css = _read_text(web_dir / "task.css") if (web_dir / "task.css").exists() else ""
        task_parts_css = _read_optional_bundle(web_dir / "task_parts", "*.css")
        project_chat_css = _read_text(web_dir / "project_chat.css") if (web_dir / "project_chat.css").exists() else ""
        css = "\n\n".join(part for part in [css, task_parts_css, project_chat_css] if part)
        js = _read_text(web_dir / "project_chat.js") if (web_dir / "project_chat.js").exists() else ""
        tpl = tpl.replace("__INLINE_CSS__", css).replace("__INLINE_JS__", js)
        return tpl.replace("__PAYLOAD__", payload)
    if template_name == "template_message_risk_dashboard.html" and (web_dir / "message_risk_dashboard.html.tpl").exists():
        tpl = _read_text(web_dir / "message_risk_dashboard.html.tpl")
        css = _read_text(web_dir / "message_risk_dashboard.css") if (web_dir / "message_risk_dashboard.css").exists() else ""
        shared = _read_text(web_dir / "shared.js") if (web_dir / "shared.js").exists() else ""
        js = _read_text(web_dir / "message_risk_dashboard.js") if (web_dir / "message_risk_dashboard.js").exists() else ""
        if shared:
            js = shared + "\n\n" + js
        tpl = tpl.replace("__INLINE_CSS__", css).replace("__INLINE_JS__", js)
        return tpl.replace("__PAYLOAD__", payload)
    if template_name == "template_agent_capability_report.html" and (web_dir / "agent_capability_report.html.tpl").exists():
        tpl = _read_text(web_dir / "agent_capability_report.html.tpl")
        css = _read_text(web_dir / "agent_capability_report.css") if (web_dir / "agent_capability_report.css").exists() else ""
        shared = _read_text(web_dir / "shared.js") if (web_dir / "shared.js").exists() else ""
        js = _read_text(web_dir / "agent_capability_report.js") if (web_dir / "agent_capability_report.js").exists() else ""
        if shared:
            js = shared + "\n\n" + js
        tpl = tpl.replace("__INLINE_CSS__", css).replace("__INLINE_JS__", js)
        return tpl.replace("__PAYLOAD__", payload)
    if template_name == "template_status_report.html" and (web_dir / "status_report.html.tpl").exists():
        tpl = _read_text(web_dir / "status_report.html.tpl")
        css = _read_text(web_dir / "status_report.css") if (web_dir / "status_report.css").exists() else ""
        shared = _read_text(web_dir / "shared.js") if (web_dir / "shared.js").exists() else ""
        js = _read_text(web_dir / "status_report.js") if (web_dir / "status_report.js").exists() else ""
        if shared:
            js = shared + "\n\n" + js
        tpl = tpl.replace("__INLINE_CSS__", css).replace("__INLINE_JS__", js)
        return tpl.replace("__PAYLOAD__", payload)
    if template_name == "template_open_source_sync.html" and (web_dir / "open_source_sync.html.tpl").exists():
        tpl = _read_text(web_dir / "open_source_sync.html.tpl")
        css = _read_text(web_dir / "open_source_sync.css") if (web_dir / "open_source_sync.css").exists() else ""
        shared = _read_text(web_dir / "shared.js") if (web_dir / "shared.js").exists() else ""
        js = _read_text(web_dir / "open_source_sync.js") if (web_dir / "open_source_sync.js").exists() else ""
        if shared:
            js = shared + "\n\n" + js
        tpl = tpl.replace("__INLINE_CSS__", css).replace("__INLINE_JS__", js)
        return tpl.replace("__PAYLOAD__", payload)
    if template_name == "template_platform_architecture_board.html" and (web_dir / "platform_architecture_board.html.tpl").exists():
        tpl = _read_text(web_dir / "platform_architecture_board.html.tpl")
        css = _read_text(web_dir / "platform_architecture_board.css") if (web_dir / "platform_architecture_board.css").exists() else ""
        shared = _read_text(web_dir / "shared.js") if (web_dir / "shared.js").exists() else ""
        js = _read_text(web_dir / "platform_architecture_board.js") if (web_dir / "platform_architecture_board.js").exists() else ""
        if shared:
            js = shared + "\n\n" + js
        tpl = tpl.replace("__INLINE_CSS__", css).replace("__INLINE_JS__", js)
        return tpl.replace("__PAYLOAD__", payload)
    if template_name == "template_session_health.html" and (web_dir / "session_health.html.tpl").exists():
        tpl = _read_text(web_dir / "session_health.html.tpl")
        css = _read_text(web_dir / "session_health.css") if (web_dir / "session_health.css").exists() else ""
        shared = _read_text(web_dir / "shared.js") if (web_dir / "shared.js").exists() else ""
        js = _read_text(web_dir / "session_health.js") if (web_dir / "session_health.js").exists() else ""
        if shared:
            js = shared + "\n\n" + js
        tpl = tpl.replace("__INLINE_CSS__", css).replace("__INLINE_JS__", js)
        return tpl.replace("__PAYLOAD__", payload)
    if template_name == "template_agent_directory.html" and (web_dir / "agent_directory.html.tpl").exists():
        tpl = _read_text(web_dir / "agent_directory.html.tpl")
        css = _read_text(web_dir / "agent_directory.css") if (web_dir / "agent_directory.css").exists() else ""
        shared = _read_text(web_dir / "shared.js") if (web_dir / "shared.js").exists() else ""
        js = _read_text(web_dir / "agent_directory.js") if (web_dir / "agent_directory.js").exists() else ""
        if shared:
            js = shared + "\n\n" + js
        tpl = tpl.replace("__INLINE_CSS__", css).replace("__INLINE_JS__", js)
        return tpl.replace("__PAYLOAD__", payload)
    if template_name == "template_agent_curtain.html" and (web_dir / "agent_curtain.html.tpl").exists():
        tpl = _read_text(web_dir / "agent_curtain.html.tpl")
        css = _read_text(web_dir / "agent_curtain.css") if (web_dir / "agent_curtain.css").exists() else ""
        shared = _read_text(web_dir / "shared.js") if (web_dir / "shared.js").exists() else ""
        js = _read_text(web_dir / "agent_curtain.js") if (web_dir / "agent_curtain.js").exists() else ""
        if shared:
            js = shared + "\n\n" + js
        tpl = tpl.replace("__INLINE_CSS__", css).replace("__INLINE_JS__", js)
        return tpl.replace("__PAYLOAD__", payload)
    if template_name == "template_agent_relationship_board.html" and (web_dir / "agent_relationship_board.html.tpl").exists():
        tpl = _read_text(web_dir / "agent_relationship_board.html.tpl")
        css = _read_text(web_dir / "agent_relationship_board.css") if (web_dir / "agent_relationship_board.css").exists() else ""
        shared = _read_text(web_dir / "shared.js") if (web_dir / "shared.js").exists() else ""
        js = _read_text(web_dir / "agent_relationship_board.js") if (web_dir / "agent_relationship_board.js").exists() else ""
        if shared:
            js = shared + "\n\n" + js
        tpl = tpl.replace("__INLINE_CSS__", css).replace("__INLINE_JS__", js)
        return tpl.replace("__PAYLOAD__", payload)

    tpl_path = script_dir / template_name
    if not tpl_path.exists():
        raise FileNotFoundError(f"template not found: {tpl_path}")
    template = _read_text(tpl_path)
    return template.replace("__PAYLOAD__", payload)
