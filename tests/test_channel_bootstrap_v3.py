# -*- coding: utf-8 -*-

import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

try:
    import tomllib
except Exception:  # pragma: no cover
    import tomli as tomllib  # type: ignore

import server
from task_dashboard.runtime import heartbeat_registry
from task_dashboard.runtime.channel_workflow import (
    build_channel_assist_message_payload,
    normalize_channel_bootstrap_v3_request,
)
from task_dashboard.runtime.channel_admin import (
    channel_type_templates,
    create_channel as runtime_create_channel,
    read_channel_agents_md,
    resolve_task_root_path,
    validate_agents_md_content,
    write_channel_agents_md,
)
from task_dashboard.runtime.scheduler_helpers import _enqueue_run_for_dispatch


class _CaptureStore:
    def __init__(self) -> None:
        self.created_runs: list[tuple[tuple, dict]] = []

    def create_run(self, *args, **kwargs):
        self.created_runs.append((args, kwargs))
        return {"id": f"run-{len(self.created_runs)}", "status": "queued"}


class _CaptureContext:
    def __init__(
        self,
        *,
        tmpdir: Path,
        body: dict,
        target_session: dict | None = None,
        create_channel_error: Exception | None = None,
        project_channel_exists: bool = False,
    ) -> None:
        self.tmpdir = tmpdir
        self.body = body
        self.target_session = target_session
        self.create_channel_error = create_channel_error
        self.project_channel_exists_value = bool(project_channel_exists)
        self.store = _CaptureStore()
        self.session_store = SimpleNamespace(get_session=lambda session_id: self.target_session)
        self.scheduler = object()
        self.port = 18765
        self.responses: list[tuple[int, dict]] = []
        self.created_channels: list[tuple[str, str, str, str]] = []
        self.config_path = tmpdir / "config.toml"
        self.config_path.write_text(
            """
[[projects]]
id = "task_dashboard"
task_root_rel = "qoreon-demo/项目看板/task-dashboard/任务规划"
""".strip()
            + "\n",
            encoding="utf-8",
        )

    def require_token(self) -> bool:
        return True

    def read_body_json(self, handler, max_bytes: int = 64_000):  # noqa: ARG002
        return self.body

    def json_response(self, handler, status: int, payload: dict, send_body: bool = True):  # noqa: ARG002
        self.responses.append((status, payload))

    def safe_text(self, value, max_len: int):
        text = "" if value is None else str(value)
        return text[:max_len]

    def coerce_bool(self, value, default: bool = False):
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    def create_channel(self, project_id: str, channel_name: str, channel_desc: str, cli_type: str, **kwargs):
        if self.create_channel_error is not None:
            raise self.create_channel_error
        self.created_channels.append((project_id, channel_name, channel_desc, cli_type))
        return {"ok": True, "cli_type": cli_type, "agents_md": {"path": "", **kwargs}}

    def find_project_cfg(self, project_id: str):
        if project_id == "task_dashboard":
            return {"task_root_rel": "qoreon-demo/项目看板/task-dashboard/任务规划"}
        return None

    def repo_root(self) -> Path:
        return self.tmpdir

    def config_toml_path(self) -> Path:
        return self.config_path

    def looks_like_uuid(self, value: str) -> bool:
        return bool(value)

    def project_channel_exists(self, project_id: str, channel_name: str) -> bool:  # noqa: ARG002
        return self.project_channel_exists_value


class TestChannelBootstrapV3Helpers(unittest.TestCase):
    def test_resolve_task_root_path_handles_repo_prefixed_task_root_rel(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo_root = Path(td) / "task-dashboard"
            repo_root.mkdir(parents=True, exist_ok=True)
            resolved = resolve_task_root_path(
                repo_root=repo_root,
                task_root_rel="qoreon-demo/项目看板/task-dashboard/任务规划",
            )
        self.assertEqual(resolved, (repo_root / "任务规划").resolve())

    def test_normalize_request_supports_mode_aliases_and_defaults(self) -> None:
        out = normalize_channel_bootstrap_v3_request(
            {
                "projectId": "task_dashboard",
                "workflowMode": "agent-assist",
                "channelKind": "业务",
                "channelIndex": "02",
                "channelName": "运行时",
                "businessRequirement": "需要独立弹框并分流 direct / assist",
                "sourceAgentName": "项目运维-会话健康管理",
            }
        )
        self.assertEqual(out["project_id"], "task_dashboard")
        self.assertEqual(out["mode"], "agent_assist")
        self.assertEqual(out["channel_theme"], "运行时")
        self.assertEqual(out["channel_name"], "业务02-运行时")
        self.assertEqual(out["prompt_preset"], "channel_create_assist_v1")
        self.assertEqual(out["source_agent_name"], "项目运维-会话健康管理")
        self.assertEqual(out["source_agent_id"], "task_dashboard")

    def test_normalize_request_supports_custom_channel_kind(self) -> None:
        out = normalize_channel_bootstrap_v3_request(
            {
                "projectId": "task_dashboard",
                "mode": "direct",
                "channelKind": "__custom__",
                "channelKindMode": "custom",
                "channelKindCustom": "产品",
                "channelIndex": "02",
                "channelName": "需求规划",
            }
        )
        self.assertEqual(out["channel_kind"], "产品")
        self.assertEqual(out["channel_theme"], "需求规划")
        self.assertEqual(out["channel_name"], "产品02-需求规划")

    def test_normalize_request_accepts_already_prefixed_channel_name(self) -> None:
        out = normalize_channel_bootstrap_v3_request(
            {
                "projectId": "task_dashboard",
                "mode": "direct",
                "channelKind": "业务",
                "channelIndex": "02",
                "channelName": "业务02-运行时",
            }
        )
        self.assertEqual(out["channel_theme"], "运行时")
        self.assertEqual(out["channel_name"], "业务02-运行时")

    def test_build_channel_assist_message_payload_includes_formal_dispatch_refs(self) -> None:
        payload = build_channel_assist_message_payload(
            project_id="task_dashboard",
            created_channel_name="子级02-CCB运行时（server-并发-安全-启动）",
            created_channel_theme="CCB运行时（server-并发-安全-启动）",
            created_channel_desc="运行时专项",
            target_session={
                "sessionId": "019cfee1-b75a-71c2-8146-f1d04ee96daf",
                "channel_name": "子级02-CCB运行时（server-并发-安全-启动）",
                "alias": "服务开发",
                "cli_type": "codex",
                "model": "gpt-5.3-codex",
                "reasoning_effort": "medium",
                "project_id": "task_dashboard",
            },
            business_requirement="只改后端/文档/测试文件，不碰前端。",
            prompt_preset="channel_create_assist_v1",
            source_session_id="019cdc3a-52a5-70d1-88e0-caa7865595ff",
            source_channel_name="辅助06-项目运维（运行巡检-异常告警-会话修复）",
            source_agent_name="项目运维-会话健康管理",
            source_agent_alias="项目运维-会话健康管理",
            source_agent_id="task_dashboard",
        )
        self.assertIn("[新增通道 v3 - Agent辅助创建]", payload["message"])
        self.assertIn("已创建空通道框架: 子级02-CCB运行时（server-并发-安全-启动）", payload["message"])
        self.assertIn("通道主题: CCB运行时（server-并发-安全-启动）", payload["message"])
        self.assertIn("文件维度:", payload["message"])
        self.assertIn("边界:", payload["message"])
        self.assertIn("只改后端/文档/测试文件，不碰前端。", payload["message"])
        self.assertEqual(payload["sender_fields"]["sender_type"], "agent")
        self.assertEqual(payload["sender_fields"]["sender_id"], "019cdc3a-52a5-70d1-88e0-caa7865595ff")
        self.assertEqual(payload["sender_fields"]["sender_name"], "项目运维-会话健康管理")
        extra = payload["run_extra_fields"]
        self.assertEqual(extra["message_kind"], "collab_update")
        self.assertEqual(extra["interaction_mode"], "task_with_receipt")
        self.assertEqual(extra["dispatch_mode"], "agent_assist")
        self.assertEqual(extra["channel_bootstrap"]["mode"], "agent_assist")
        self.assertEqual(extra["source_ref"]["session_id"], "019cdc3a-52a5-70d1-88e0-caa7865595ff")
        self.assertEqual(extra["target_ref"]["session_id"], "019cfee1-b75a-71c2-8146-f1d04ee96daf")
        self.assertEqual(extra["callback_to"]["channel_name"], "辅助06-项目运维（运行巡检-异常告警-会话修复）")
        self.assertEqual(extra["sender_agent_ref"]["alias"], "项目运维-会话健康管理")
        self.assertEqual(extra["target_agent_ref"]["alias"], "服务开发")

    def test_build_channel_assist_message_payload_accepts_session_store_id_field(self) -> None:
        payload = build_channel_assist_message_payload(
            project_id="task_dashboard",
            created_channel_name="辅助95-live-agent验收",
            created_channel_theme="live-agent验收",
            created_channel_desc="live agent assist 受控验收样本",
            target_session={
                "id": "019cfee1-b75a-71c2-8146-f1d04ee96daf",
                "channel_name": "子级02-CCB运行时（server-并发-安全-启动）",
                "alias": "服务开发",
                "cli_type": "codex",
                "project_id": "task_dashboard",
            },
            business_requirement="受控 live 验收样本，仅验证 agent_assist 路径创建空框架并正式派发。",
            prompt_preset="channel_create_assist_v1",
            source_session_id="019cfee1-b75a-71c2-8146-f1d04ee96daf",
            source_channel_name="辅助95-live-agent验收",
            source_agent_name="服务开发",
            source_agent_alias="服务开发",
            source_agent_id="task_dashboard",
        )
        self.assertEqual(payload["target_session_id"], "019cfee1-b75a-71c2-8146-f1d04ee96daf")
        self.assertEqual(payload["sender_fields"]["sender_id"], "019cfee1-b75a-71c2-8146-f1d04ee96daf")
        self.assertEqual(payload["sender_fields"]["sender_name"], "服务开发")
        extra = payload["run_extra_fields"]
        self.assertEqual(extra["target_ref"]["session_id"], "019cfee1-b75a-71c2-8146-f1d04ee96daf")
        self.assertEqual(extra["target_agent_ref"]["session_id"], "019cfee1-b75a-71c2-8146-f1d04ee96daf")

    def test_build_channel_assist_message_payload_does_not_use_display_name_as_target_alias(self) -> None:
        payload = build_channel_assist_message_payload(
            project_id="task_dashboard",
            created_channel_name="辅助95-live-agent验收",
            created_channel_theme="live-agent验收",
            created_channel_desc="live agent assist 受控验收样本",
            target_session={
                "id": "019cfee1-b75a-71c2-8146-f1d04ee96daf",
                "channel_name": "子级02-CCB运行时（server-并发-安全-启动）",
                "display_name": "会话展示衍生名",
                "cli_type": "codex",
            },
            business_requirement="受控 live 验收样本，仅验证 agent_assist 路径创建空框架并正式派发。",
            prompt_preset="channel_create_assist_v1",
            source_session_id="019cfee1-b75a-71c2-8146-f1d04ee96daf",
            source_channel_name="辅助95-live-agent验收",
            source_agent_name="服务开发",
            source_agent_alias="服务开发",
            source_agent_id="task_dashboard",
        )
        self.assertEqual(payload["target_session_alias"], "")
        self.assertEqual(payload["target_session_channel_name"], "子级02-CCB运行时（server-并发-安全-启动）")
        self.assertEqual(
            payload["run_extra_fields"]["target_agent_ref"]["agent_name"],
            "子级02-CCB运行时（server-并发-安全-启动）",
        )
        self.assertEqual(payload["run_extra_fields"]["target_agent_ref"]["alias"], "")

    def test_create_channel_uses_resolved_task_root(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo_root = Path(td) / "task-dashboard"
            repo_root.mkdir(parents=True, exist_ok=True)
            config_path = repo_root / "config.toml"
            config_path.write_text(
                """
[[projects]]
id = "task_dashboard"
task_root_rel = "qoreon-demo/项目看板/task-dashboard/任务规划"
""".strip()
                + "\n",
                encoding="utf-8",
            )
            runtime_create_channel(
                project_id="task_dashboard",
                channel_name="辅助98-新增通道真实验收（v3-direct）",
                channel_desc="受控真实创建演练样本",
                cli_type="codex",
                config_path=config_path,
                repo_root=repo_root,
                atomic_write_text=lambda path, text: path.write_text(text, encoding="utf-8"),
            )
            correct_root = (repo_root / "任务规划" / "辅助98-新增通道真实验收（v3-direct）").resolve()
            wrong_root = (repo_root / "qoreon-demo/项目看板/task-dashboard/任务规划/辅助98-新增通道真实验收（v3-direct）").resolve()
            self.assertTrue(correct_root.exists())
            self.assertTrue((correct_root / "README.md").exists())
            self.assertTrue((correct_root / "AGENTS.md").exists())
            self.assertFalse(wrong_root.exists())

    def test_create_channel_writes_agents_md_from_role_template(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo_root = Path(td) / "task-dashboard"
            repo_root.mkdir(parents=True, exist_ok=True)
            config_path = repo_root / "config.toml"
            config_path.write_text(
                """
[[projects]]
id = "task_dashboard"
task_root_rel = "任务规划"
""".strip()
                + "\n",
                encoding="utf-8",
            )

            result = runtime_create_channel(
                project_id="task_dashboard",
                channel_name="业务03-规划样本",
                channel_desc="规划通道",
                cli_type="codex",
                config_path=config_path,
                repo_root=repo_root,
                atomic_write_text=lambda path, text: path.write_text(text, encoding="utf-8"),
                agents_md_role="planner",
            )

            agents_path = repo_root / "任务规划" / "业务03-规划样本" / "AGENTS.md"
            self.assertTrue(agents_path.exists())
            text = agents_path.read_text(encoding="utf-8")
            self.assertIn("标准角色：业务/规划", text)
            self.assertIn("本文件只保存长期协作规则", text)
            self.assertIn("## 1. 先读规则", text)
            self.assertIn("## 3. 消息发送与回执", text)
            self.assertIn("task_dashboard.message_cli send|receipt", text)
            self.assertIn("announce_run_id + target_session_id一致 + visible_in_channel_chat=true", text)
            self.assertIn("## 4. 任务推进", text)
            self.assertIn("task_dashboard.task_cli validate --stage review --mode strict", text)
            self.assertIn("## 6. 常用 Skills 入口", text)
            self.assertIn("collab-message-send", text)
            self.assertIn("已写入 AGENTS.md 不等于旧会话已加载", text)
            self.assertIn("服务动作必须转服务管理", text)
            self.assertTrue(result["agents_md"]["created"])
            self.assertEqual(result["agents_md"]["role"], "planner")

    def test_channel_type_templates_cover_v1_short_names(self) -> None:
        short_names = {row["channelType"] for row in channel_type_templates()}
        self.assertEqual(
            {"总控", "助理", "产品", "镜像", "前端", "后端", "测试", "服务", "通讯", "任务", "技能", "资料", "视觉"},
            short_names,
        )

    def test_create_channel_uses_channel_type_template_before_role_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo_root = Path(td) / "task-dashboard"
            repo_root.mkdir(parents=True, exist_ok=True)
            config_path = repo_root / "config.toml"
            config_path.write_text(
                """
[[projects]]
id = "task_dashboard"
task_root_rel = "任务规划"
""".strip()
                + "\n",
                encoding="utf-8",
            )

            result = runtime_create_channel(
                project_id="task_dashboard",
                channel_name="后端01-CCB运行时",
                channel_desc="运行时专项",
                cli_type="codex",
                config_path=config_path,
                repo_root=repo_root,
                atomic_write_text=lambda path, text: path.write_text(text, encoding="utf-8"),
                channel_type="后端",
                agents_md_role="planner",
            )

            agents_path = repo_root / "任务规划" / "后端01-CCB运行时" / "AGENTS.md"
            text = agents_path.read_text(encoding="utf-8")
            self.assertIn("通道类型：后端（后端模板）", text)
            self.assertIn("标准角色：执行/研发", text)
            self.assertIn("默认 workdir：默认使用通道目录；显式 workdir 仍优先。", text)
            self.assertIn("不绕过同 session 串行", text)
            self.assertEqual(result["agents_md"]["role"], "developer")
            self.assertEqual(result["agents_md"]["channelType"], "后端")
            self.assertTrue(result["agents_md"]["dryRun"]["ok"])

    def test_agents_md_dry_run_blocks_sensitive_runtime_fields(self) -> None:
        dry_run = validate_agents_md_content(
            "Authorization: Bearer abcdefghijklmnopqrstuvwxyz\n"
            "session_id=019f700a-000a-700a-800a-00000000000a\n"
            "允许直接重启服务\n"
        )
        self.assertFalse(dry_run["ok"])
        codes = {row["code"] for row in dry_run["blockingIssues"]}
        self.assertIn("bearer_token", codes)
        self.assertIn("concrete_session_id", codes)
        self.assertIn("service_or_session_grant", codes)

    def test_write_channel_agents_md_blocks_sensitive_content_before_backup(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo_root = Path(td) / "task-dashboard"
            repo_root.mkdir(parents=True, exist_ok=True)
            config_path = repo_root / "config.toml"
            config_path.write_text(
                """
[[projects]]
id = "task_dashboard"
task_root_rel = "任务规划"

[[projects.channels]]
name = "后端01-CCB运行时"
desc = "运行时专项"
""".strip()
                + "\n",
                encoding="utf-8",
            )
            channel_root = repo_root / "任务规划" / "后端01-CCB运行时"
            channel_root.mkdir(parents=True, exist_ok=True)
            (channel_root / "AGENTS.md").write_text("old rules\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "dry-run blocked"):
                write_channel_agents_md(
                    project_id="task_dashboard",
                    channel_name="后端01-CCB运行时",
                    content="允许直接重启服务\n",
                    config_path=config_path,
                    repo_root=repo_root,
                )
            self.assertEqual((channel_root / "AGENTS.md").read_text(encoding="utf-8"), "old rules\n")

    def test_create_channel_preserves_existing_agents_md_file(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo_root = Path(td) / "task-dashboard"
            repo_root.mkdir(parents=True, exist_ok=True)
            config_path = repo_root / "config.toml"
            config_path.write_text(
                """
[[projects]]
id = "task_dashboard"
task_root_rel = "任务规划"
""".strip()
                + "\n",
                encoding="utf-8",
            )
            channel_root = repo_root / "任务规划" / "业务03-规划样本"
            channel_root.mkdir(parents=True, exist_ok=True)
            agents_path = channel_root / "AGENTS.md"
            agents_path.write_text("custom existing rules\n", encoding="utf-8")

            result = runtime_create_channel(
                project_id="task_dashboard",
                channel_name="业务03-规划样本",
                channel_desc="规划通道",
                cli_type="codex",
                config_path=config_path,
                repo_root=repo_root,
                atomic_write_text=lambda path, text: path.write_text(text, encoding="utf-8"),
                agents_md_role="planner",
            )

            self.assertEqual(agents_path.read_text(encoding="utf-8"), "custom existing rules\n")
            self.assertFalse(result["agents_md"]["created"])

    def test_write_channel_agents_md_creates_backup(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo_root = Path(td) / "task-dashboard"
            repo_root.mkdir(parents=True, exist_ok=True)
            config_path = repo_root / "config.toml"
            config_path.write_text(
                """
[[projects]]
id = "task_dashboard"
task_root_rel = "任务规划"

[[projects.channels]]
name = "业务03-规划样本"
desc = "规划通道"
""".strip()
                + "\n",
                encoding="utf-8",
            )
            channel_root = repo_root / "任务规划" / "业务03-规划样本"
            channel_root.mkdir(parents=True, exist_ok=True)
            (channel_root / "AGENTS.md").write_text("old rules\n", encoding="utf-8")

            result = write_channel_agents_md(
                project_id="task_dashboard",
                channel_name="业务03-规划样本",
                content="new rules",
                config_path=config_path,
                repo_root=repo_root,
            )

            self.assertEqual((channel_root / "AGENTS.md").read_text(encoding="utf-8"), "new rules\n")
            self.assertTrue(result["backupPath"])
            self.assertTrue(Path(result["backupPath"]).exists())

    def test_read_channel_agents_md_blocks_path_escape(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo_root = Path(td) / "task-dashboard"
            repo_root.mkdir(parents=True, exist_ok=True)
            config_path = repo_root / "config.toml"
            config_path.write_text(
                """
[[projects]]
id = "task_dashboard"
task_root_rel = "任务规划"

[[projects.channels]]
name = "../越界"
desc = "bad"
""".strip()
                + "\n",
                encoding="utf-8",
            )

            with self.assertRaises(PermissionError):
                read_channel_agents_md(
                    project_id="task_dashboard",
                    channel_name="../越界",
                    config_path=config_path,
                    repo_root=repo_root,
                )

    def test_create_channel_allows_same_name_in_other_project(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo_root = Path(td) / "task-dashboard"
            repo_root.mkdir(parents=True, exist_ok=True)
            config_path = repo_root / "config.toml"
            config_path.write_text(
                """
[[projects]]
id = "alpha"
task_root_rel = "alpha/任务规划"

[[projects.channels]]
name = "辅助01-项目管理"
desc = "alpha keep"

[[projects]]
id = "beta"
task_root_rel = "beta/任务规划"

[[projects.channels]]
name = "主体-总控"
desc = "beta keep"

[projects.execution_context]
profile = "project_privileged_full"
environment = "stable"
""".strip()
                + "\n",
                encoding="utf-8",
            )

            runtime_create_channel(
                project_id="beta",
                channel_name="辅助01-项目管理",
                channel_desc="beta add",
                cli_type="codex",
                config_path=config_path,
                repo_root=repo_root,
                atomic_write_text=lambda path, text: path.write_text(text, encoding="utf-8"),
            )

            updated = config_path.read_text(encoding="utf-8")
            self.assertEqual(updated.count('name = "辅助01-项目管理"'), 2)
            self.assertIn('id = "beta"', updated)
            self.assertTrue((repo_root / "beta" / "任务规划" / "辅助01-项目管理" / "README.md").exists())

    def test_create_channel_preserves_execution_context_block_order(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo_root = Path(td) / "task-dashboard"
            repo_root.mkdir(parents=True, exist_ok=True)
            config_path = repo_root / "config.toml"
            config_path.write_text(
                """
[[projects]]
id = "clitools"
name = "工具集合（CLI）"
task_root_rel = "projects/CLItools/任务规划"

[[projects.channels]]
name = "主体-总控"
desc = "总控通道"
cli_type = "codex"

[projects.execution_context]
profile = "project_privileged_full"
environment = "stable"
""".strip()
                + "\n",
                encoding="utf-8",
            )

            runtime_create_channel(
                project_id="clitools",
                channel_name="辅助01-项目管理",
                channel_desc="管理项目架构，打杂",
                cli_type="codex",
                config_path=config_path,
                repo_root=repo_root,
                atomic_write_text=lambda path, text: path.write_text(text, encoding="utf-8"),
            )

            updated = config_path.read_text(encoding="utf-8")
            new_channel_idx = updated.index('name = "辅助01-项目管理"')
            exec_ctx_idx = updated.index("[projects.execution_context]")
            self.assertLess(new_channel_idx, exec_ctx_idx)
            parsed = tomllib.loads(updated)
            project = (parsed.get("projects") or [])[0]
            self.assertEqual(project["channels"][1]["name"], "辅助01-项目管理")
            self.assertEqual(project["channels"][1]["cli_type"], "codex")
            self.assertEqual(project["execution_context"]["environment"], "stable")

    def test_create_channel_without_existing_channel_stays_before_execution_context(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo_root = Path(td) / "task-dashboard"
            repo_root.mkdir(parents=True, exist_ok=True)
            config_path = repo_root / "config.toml"
            config_path.write_text(
                """
[[projects]]
id = "clitools"
name = "工具集合（CLI）"
task_root_rel = "projects/CLItools/任务规划"

[projects.execution_context]
profile = "project_privileged_full"
environment = "stable"
""".strip()
                + "\n",
                encoding="utf-8",
            )

            runtime_create_channel(
                project_id="clitools",
                channel_name="辅助01-项目管理",
                channel_desc="管理项目架构，打杂",
                cli_type="codex",
                config_path=config_path,
                repo_root=repo_root,
                atomic_write_text=lambda path, text: path.write_text(text, encoding="utf-8"),
            )

            updated = config_path.read_text(encoding="utf-8")
            self.assertLess(updated.index('name = "辅助01-项目管理"'), updated.index("[projects.execution_context]"))
            parsed = tomllib.loads(updated)
            project = (parsed.get("projects") or [])[0]
            self.assertEqual(project["channels"][0]["name"], "辅助01-项目管理")
            self.assertEqual(project["execution_context"]["profile"], "project_privileged_full")

    def test_runtime_registry_create_channel_allows_same_name_in_other_project(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo_root = Path(td) / "task-dashboard"
            repo_root.mkdir(parents=True, exist_ok=True)
            config_path = repo_root / "config.toml"
            config_path.write_text(
                """
[[projects]]
id = "alpha"
task_root_rel = "alpha/任务规划"

[[projects.channels]]
name = "辅助01-项目管理"
desc = "alpha keep"

[[projects]]
id = "beta"
task_root_rel = "beta/任务规划"

[[projects.channels]]
name = "主体-总控"
desc = "beta keep"
""".strip()
                + "\n",
                encoding="utf-8",
            )

            with mock.patch.object(heartbeat_registry, "_config_toml_path", return_value=config_path):
                with mock.patch.object(heartbeat_registry, "_repo_root", return_value=repo_root):
                    with mock.patch.object(heartbeat_registry, "_clear_dashboard_cfg_cache"):
                        with mock.patch.object(
                            heartbeat_registry,
                            "_atomic_write_text",
                            side_effect=lambda path, text: path.write_text(text, encoding="utf-8"),
                        ):
                            heartbeat_registry._create_channel(
                                "beta",
                                "辅助01-项目管理",
                                "beta add",
                                "codex",
                            )

            updated = config_path.read_text(encoding="utf-8")
            self.assertEqual(updated.count('name = "辅助01-项目管理"'), 2)
            self.assertTrue((repo_root / "beta" / "任务规划" / "辅助01-项目管理" / "README.md").exists())


class TestChannelBootstrapV3Route(unittest.TestCase):
    def test_direct_mode_only_creates_framework(self) -> None:
        body = {
            "projectId": "task_dashboard",
            "mode": "direct",
            "channelKind": "业务",
            "channelIndex": "02",
            "channelName": "CCB运行时（server-并发-安全-启动）",
            "channelDesc": "运行时专项",
        }
        with tempfile.TemporaryDirectory() as td:
            ctx = _CaptureContext(tmpdir=Path(td), body=body)
            dispatcher = server.RouteDispatcher(ctx)  # type: ignore[arg-type]
            handler = SimpleNamespace(path="/api/channels/bootstrap-v3", headers={}, client_address=("127.0.0.1", 0))

            handled = dispatcher._handle_channel_bootstrap_v3_post(handler)

        self.assertIsNone(handled)
        self.assertEqual(len(ctx.created_channels), 1)
        self.assertEqual(ctx.created_channels[0][1], "业务02-CCB运行时（server-并发-安全-启动）")
        self.assertEqual(len(ctx.store.created_runs), 0)
        self.assertEqual(ctx.responses[0][0], 200)
        payload = ctx.responses[0][1]
        self.assertEqual(payload["mode"], "direct")
        self.assertEqual(payload["channelTheme"], "CCB运行时（server-并发-安全-启动）")
        self.assertTrue(payload["framework"]["created"])
        self.assertNotIn("dispatch", payload)
        self.assertNotIn("targetSession", payload)

    def test_direct_mode_accepts_custom_channel_kind(self) -> None:
        body = {
            "projectId": "task_dashboard",
            "mode": "direct",
            "channelKind": "__custom__",
            "channelKindMode": "custom",
            "channelKindCustom": "产品",
            "channelIndex": "02",
            "channelName": "需求规划",
            "channelDesc": "产品规划专项",
        }
        with tempfile.TemporaryDirectory() as td:
            ctx = _CaptureContext(tmpdir=Path(td), body=body)
            dispatcher = server.RouteDispatcher(ctx)  # type: ignore[arg-type]
            handler = SimpleNamespace(path="/api/channels/bootstrap-v3", headers={}, client_address=("127.0.0.1", 0))

            handled = dispatcher._handle_channel_bootstrap_v3_post(handler)

        self.assertIsNone(handled)
        self.assertEqual(ctx.responses[0][0], 200)
        self.assertEqual(ctx.created_channels[0][1], "产品02-需求规划")
        self.assertEqual(ctx.responses[0][1]["channelName"], "产品02-需求规划")

    def test_agent_assist_mode_dispatches_formal_run(self) -> None:
        body = {
            "projectId": "task_dashboard",
            "mode": "agent_assist",
            "channelKind": "子级",
            "channelIndex": "02",
            "channelName": "CCB运行时（server-并发-安全-启动）",
            "channelDesc": "运行时专项",
            "targetSessionId": "019cfee1-b75a-71c2-8146-f1d04ee96daf",
            "businessRequirement": "只改后端/文档/测试文件，不碰前端。",
            "promptPreset": "channel_create_assist_v1",
            "sourceSessionId": "019cdc3a-52a5-70d1-88e0-caa7865595ff",
            "sourceChannelName": "辅助06-项目运维（运行巡检-异常告警-会话修复）",
            "sourceAgentName": "项目运维-会话健康管理",
            "sourceAgentAlias": "项目运维-会话健康管理",
            "sourceAgentId": "task_dashboard",
        }
        target_session = {
            "sessionId": "019cfee1-b75a-71c2-8146-f1d04ee96daf",
            "channel_name": "子级02-CCB运行时（server-并发-安全-启动）",
            "alias": "服务开发",
            "cli_type": "codex",
            "model": "gpt-5.3-codex",
            "reasoning_effort": "medium",
            "project_id": "task_dashboard",
        }
        with tempfile.TemporaryDirectory() as td:
            ctx = _CaptureContext(tmpdir=Path(td), body=body, target_session=target_session)
            dispatcher = server.RouteDispatcher(ctx)  # type: ignore[arg-type]
            handler = SimpleNamespace(path="/api/channels/bootstrap-v3", headers={}, client_address=("127.0.0.1", 0))

            with mock.patch("task_dashboard.routes.main.runtime_enqueue_run_for_dispatch") as enqueue:
                handled = dispatcher._handle_channel_bootstrap_v3_post(handler)

        self.assertIsNone(handled)
        self.assertEqual(len(ctx.created_channels), 1)
        self.assertEqual(len(ctx.store.created_runs), 1)
        self.assertEqual(ctx.responses[0][0], 200)
        payload = ctx.responses[0][1]
        self.assertEqual(payload["mode"], "agent_assist")
        self.assertEqual(payload["channelName"], "子级02-CCB运行时（server-并发-安全-启动）")
        self.assertEqual(payload["channelTheme"], "CCB运行时（server-并发-安全-启动）")
        self.assertIn("dispatch", payload)
        self.assertEqual(payload["dispatch"]["runId"], "run-1")
        self.assertEqual(payload["dispatch"]["sessionId"], "019cfee1-b75a-71c2-8146-f1d04ee96daf")
        self.assertEqual(payload["dispatch"]["senderName"], "项目运维-会话健康管理")
        self.assertEqual(payload["targetSession"]["alias"], "服务开发")
        enqueue.assert_called_once()

    def test_agent_assist_mode_response_accepts_target_session_id_field(self) -> None:
        body = {
            "projectId": "task_dashboard",
            "mode": "agent_assist",
            "channelKind": "辅助",
            "channelIndex": "95",
            "channelName": "live-agent验收",
            "channelDesc": "live agent assist 受控验收样本",
            "targetSessionId": "019cfee1-b75a-71c2-8146-f1d04ee96daf",
            "businessRequirement": "受控 live 验收样本，仅验证 agent_assist 路径创建空框架并正式派发。",
        }
        target_session = {
            "id": "019cfee1-b75a-71c2-8146-f1d04ee96daf",
            "channel_name": "子级02-CCB运行时（server-并发-安全-启动）",
            "alias": "服务开发",
            "cli_type": "codex",
            "project_id": "task_dashboard",
        }
        with tempfile.TemporaryDirectory() as td:
            ctx = _CaptureContext(tmpdir=Path(td), body=body, target_session=target_session)
            dispatcher = server.RouteDispatcher(ctx)  # type: ignore[arg-type]
            handler = SimpleNamespace(path="/api/channels/bootstrap-v3", headers={}, client_address=("127.0.0.1", 0))

            with mock.patch("task_dashboard.routes.main.runtime_enqueue_run_for_dispatch"):
                handled = dispatcher._handle_channel_bootstrap_v3_post(handler)

        self.assertIsNone(handled)
        payload = ctx.responses[0][1]
        self.assertEqual(payload["targetSession"]["sessionId"], "019cfee1-b75a-71c2-8146-f1d04ee96daf")
        self.assertEqual(payload["dispatch"]["sessionId"], "019cfee1-b75a-71c2-8146-f1d04ee96daf")

    def test_agent_assist_mode_rejects_missing_target_before_creating_channel(self) -> None:
        body = {
            "projectId": "task_dashboard",
            "mode": "agent_assist",
            "channelKind": "子级",
            "channelIndex": "02",
            "channelName": "CCB运行时（server-并发-安全-启动）",
            "channelDesc": "运行时专项",
            "targetSessionId": "019cfee1-b75a-71c2-8146-f1d04ee96daf",
            "businessRequirement": "先做空通道框架，再派发给处理 Agent。",
        }
        with tempfile.TemporaryDirectory() as td:
            ctx = _CaptureContext(tmpdir=Path(td), body=body, target_session=None)
            dispatcher = server.RouteDispatcher(ctx)  # type: ignore[arg-type]
            handler = SimpleNamespace(path="/api/channels/bootstrap-v3", headers={}, client_address=("127.0.0.1", 0))

            handled = dispatcher._handle_channel_bootstrap_v3_post(handler)

        self.assertIsNone(handled)
        self.assertEqual(len(ctx.created_channels), 0)
        self.assertEqual(len(ctx.store.created_runs), 0)
        self.assertEqual(ctx.responses[0][0], 404)
        payload = ctx.responses[0][1]
        self.assertEqual(payload["error"], "target session not found")
        self.assertEqual(payload["step"], "resolve_target_session")

    def test_direct_mode_returns_409_when_channel_already_exists(self) -> None:
        body = {
            "projectId": "task_dashboard",
            "mode": "direct",
            "channelKind": "主体",
            "channelIndex": "01",
            "channelName": "业务联络",
            "channelDesc": "重复样本",
        }
        with tempfile.TemporaryDirectory() as td:
            ctx = _CaptureContext(
                tmpdir=Path(td),
                body=body,
                create_channel_error=ValueError("Channel '主体01-业务联络' already exists"),
                project_channel_exists=True,
            )
            dispatcher = server.RouteDispatcher(ctx)  # type: ignore[arg-type]
            handler = SimpleNamespace(path="/api/channels/bootstrap-v3", headers={}, client_address=("127.0.0.1", 0))

            handled = dispatcher._handle_channel_bootstrap_v3_post(handler)

        self.assertIsNone(handled)
        self.assertEqual(len(ctx.created_channels), 0)
        self.assertEqual(len(ctx.store.created_runs), 0)
        self.assertEqual(ctx.responses[0][0], 409)
        payload = ctx.responses[0][1]
        self.assertEqual(payload["error"], "channel already exists")
        self.assertEqual(payload["step"], "create_channel")
        self.assertEqual(payload["projectId"], "task_dashboard")
        self.assertEqual(payload["channelName"], "主体01-业务联络")
        self.assertTrue(payload["channelExistsInProject"])


class TestChannelBootstrapV3DispatchHelpers(unittest.TestCase):
    def test_enqueue_run_for_dispatch_uses_runtime_executor_when_scheduler_disabled(self) -> None:
        fake_thread = mock.Mock()
        scheduler = object()
        store = object()
        with mock.patch.dict(os.environ, {"CCB_SCHEDULER": "0"}, clear=False):
            with mock.patch("task_dashboard.runtime.execution_runtime.run_cli_exec") as run_cli_exec:
                with mock.patch("task_dashboard.runtime.scheduler_helpers.threading.Thread", return_value=fake_thread) as thread_cls:
                    _enqueue_run_for_dispatch(store, "run-1", "session-1", "codex", scheduler)

        thread_cls.assert_called_once()
        kwargs = thread_cls.call_args.kwargs
        self.assertIs(kwargs["target"], run_cli_exec)
        self.assertEqual(kwargs["args"], (store, "run-1", None, "codex"))
        self.assertTrue(kwargs["daemon"])
        fake_thread.start.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
