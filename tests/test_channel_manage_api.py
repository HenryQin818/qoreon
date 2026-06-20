import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import server

from task_dashboard.helpers import atomic_write_text
from task_dashboard.routes.main import RouteDispatcher
from task_dashboard.runtime.channel_admin import delete_channel
from task_dashboard.runtime.channel_workflow import build_channel_edit_request_message_payload


def _json_response(handler, status, payload):
    handler.status = status
    handler.payload = payload


class ChannelManageApiTests(unittest.TestCase):
    def test_build_channel_edit_request_payload_includes_formal_dispatch_refs(self) -> None:
        payload = build_channel_edit_request_message_payload(
            project_id="task_dashboard",
            channel_name="辅助04-原型设计与Demo可视化（静态数据填充-业务规格确认）",
            channel_desc="产品方案与原型协同",
            target_session={
                "id": "019cfee1-b75a-71c2-8146-f1d04ee96daf",
                "channel_name": "子级02-CCB运行时（server-并发-安全-启动）",
                "alias": "服务开发",
                "cli_type": "codex",
                "model": "gpt-5.3-codex",
                "reasoning_effort": "medium",
            },
            business_requirement="请补齐通道说明与边界，不要改名。",
            source_session_id="019cddd3-454e-7140-9881-0b7f6e936847",
            source_channel_name="子级02-CCB运行时（server-并发-安全-启动）",
            source_agent_name="任务看板",
            source_agent_alias="通道管理",
            source_agent_id="task_dashboard",
        )

        self.assertIn("[通道管理 - 找 Agent 编辑]", payload["message"])
        self.assertIn("当前通道: 辅助04-原型设计与Demo可视化（静态数据填充-业务规格确认）", payload["message"])
        self.assertIn("处理Agent会话: 019cfee1-b75a-71c2-8146-f1d04ee96daf", payload["message"])
        self.assertIn("业务要求:", payload["message"])

        extra = payload["run_extra_fields"]
        self.assertEqual(extra["message_kind"], "collab_update")
        self.assertEqual(extra["interaction_mode"], "task_with_receipt")
        self.assertEqual(extra["dispatch_mode"], "channel_request_edit")
        self.assertEqual(extra["workflow_mode"], "channel_manage_v1")
        self.assertEqual(extra["channel_management"]["action"], "request_edit")
        self.assertEqual(payload["sender_fields"]["sender_id"], "019cddd3-454e-7140-9881-0b7f6e936847")
        self.assertEqual(payload["sender_fields"]["sender_name"], "通道管理")
        self.assertEqual(extra["target_ref"]["session_id"], "019cfee1-b75a-71c2-8146-f1d04ee96daf")
        self.assertEqual(extra["callback_to"]["session_id"], "019cddd3-454e-7140-9881-0b7f6e936847")

    def test_build_channel_edit_request_payload_does_not_use_display_name_as_target_alias(self) -> None:
        payload = build_channel_edit_request_message_payload(
            project_id="task_dashboard",
            channel_name="辅助04-原型设计与Demo可视化（静态数据填充-业务规格确认）",
            channel_desc="产品方案与原型协同",
            target_session={
                "id": "019cfee1-b75a-71c2-8146-f1d04ee96daf",
                "channel_name": "子级02-CCB运行时（server-并发-安全-启动）",
                "display_name": "会话展示衍生名",
                "cli_type": "codex",
            },
            business_requirement="请补齐通道说明与边界，不要改名。",
            source_session_id="019cddd3-454e-7140-9881-0b7f6e936847",
            source_channel_name="子级02-CCB运行时（server-并发-安全-启动）",
            source_agent_name="任务看板",
            source_agent_alias="通道管理",
            source_agent_id="task_dashboard",
        )
        extra = payload["run_extra_fields"]
        self.assertEqual(payload["target_session_alias"], "")
        self.assertEqual(
            extra["target_agent_ref"]["agent_name"],
            "子级02-CCB运行时（server-并发-安全-启动）",
        )
        self.assertEqual(extra["target_agent_ref"]["alias"], "")

    def test_delete_channel_removes_config_entry_and_root(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo_root = Path(td)
            config_path = repo_root / "config.toml"
            task_root = repo_root / "任务规划"
            task_root.mkdir(parents=True, exist_ok=True)
            delete_root = task_root / "辅助98-删除样本"
            keep_root = task_root / "辅助01-保留样本"
            delete_root.mkdir(parents=True, exist_ok=True)
            keep_root.mkdir(parents=True, exist_ok=True)
            (delete_root / "README.md").write_text("delete me", encoding="utf-8")
            (keep_root / "README.md").write_text("keep me", encoding="utf-8")
            config_path.write_text(
                """
[[projects]]
id = "task_dashboard"
task_root_rel = "任务规划"

[[projects.channels]]
name = "辅助01-保留样本"
desc = "keep"

[[projects.channels]]
name = "辅助98-删除样本"
desc = "delete"

[[projects.links]]
name = "示例"
path = "docs/example.md"
""".strip()
                + "\n",
                encoding="utf-8",
            )

            result = delete_channel(
                project_id="task_dashboard",
                channel_name="辅助98-删除样本",
                config_path=config_path,
                repo_root=repo_root,
                task_root_rel="任务规划",
                atomic_write_text=atomic_write_text,
            )

            self.assertTrue(result["removed_from_config"])
            self.assertTrue(result["channel_root_deleted"])
            self.assertTrue(result["kept_runtime_runs"])
            self.assertFalse(delete_root.exists())
            self.assertTrue(keep_root.exists())
            updated = config_path.read_text(encoding="utf-8")
            self.assertIn('name = "辅助01-保留样本"', updated)
            self.assertNotIn('name = "辅助98-删除样本"', updated)
            self.assertIn("[[projects.links]]", updated)

    def test_request_edit_dispatches_formal_run(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            run_store = server.RunStore(base / ".runtime" / "stable" / ".runs")
            session_store = server.SessionStore(base_dir=run_store.runs_dir.parent)
            target = session_store.create_session(
                "task_dashboard",
                "子级02-CCB运行时（server-并发-安全-启动）",
                cli_type="codex",
                alias="服务开发",
                session_id="019cfee1-b75a-71c2-8146-f1d04ee96daf",
                model="gpt-5.3-codex",
                reasoning_effort="medium",
            )

            ctx = SimpleNamespace(
                require_token=lambda: True,
                read_body_json=lambda _handler, max_bytes=0: {
                    "projectId": "task_dashboard",
                    "channelName": "辅助04-原型设计与Demo可视化（静态数据填充-业务规格确认）",
                    "channelDesc": "产品方案与原型协同",
                    "targetSessionId": target["id"],
                    "businessRequirement": "请补齐通道说明与边界，不要改名。",
                    "sourceSessionId": "019cddd3-454e-7140-9881-0b7f6e936847",
                    "sourceChannelName": "子级02-CCB运行时（server-并发-安全-启动）",
                    "sourceAgentName": "任务看板",
                    "sourceAgentAlias": "通道管理",
                    "sourceAgentId": "task_dashboard",
                },
                json_response=_json_response,
                session_store=session_store,
                store=run_store,
                scheduler=None,
            )
            handler = SimpleNamespace(status=None, payload=None)

            with patch("task_dashboard.routes.main.runtime_enqueue_run_for_dispatch") as enqueue_mock:
                RouteDispatcher(ctx)._handle_channel_request_edit_post(handler)

            self.assertEqual(handler.status, 200)
            self.assertTrue(handler.payload["ok"])
            self.assertEqual(handler.payload["action"], "request_edit")
            self.assertEqual(handler.payload["targetSession"]["sessionId"], target["id"])
            self.assertEqual(handler.payload["dispatch"]["sessionId"], target["id"])
            self.assertEqual(handler.payload["dispatch"]["messageKind"], "collab_update")
            self.assertEqual(handler.payload["dispatch"]["interactionMode"], "task_with_receipt")
            self.assertEqual(
                handler.payload["dispatch"]["senderAgentRef"]["alias"],
                "通道管理",
            )
            self.assertEqual(handler.payload["dispatch"]["senderName"], "通道管理")
            run_id = handler.payload["dispatch"]["runId"]
            self.assertTrue(run_id)
            meta = run_store.load_meta(run_id) or {}
            self.assertEqual(meta.get("sessionId"), target["id"])
            self.assertEqual(meta.get("senderType") or meta.get("sender_type"), "agent")
            self.assertEqual(meta.get("senderId") or meta.get("sender_id"), "019cddd3-454e-7140-9881-0b7f6e936847")
            self.assertEqual(meta.get("senderName") or meta.get("sender_name"), "通道管理")
            self.assertEqual(meta.get("message_kind"), "collab_update")
            self.assertEqual((meta.get("target_ref") or {}).get("session_id"), target["id"])
            self.assertEqual((meta.get("callback_to") or {}).get("session_id"), "019cddd3-454e-7140-9881-0b7f6e936847")
            enqueue_mock.assert_called_once()

    def test_static_instruction_repair_route_creates_codebuddy_mirror(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo_root = Path(td)
            config_path = repo_root / "config.toml"
            channel_root = repo_root / "任务规划" / "子级02-运行时样本"
            channel_root.mkdir(parents=True, exist_ok=True)
            (channel_root / "AGENTS.md").write_text("# AGENTS\n\n规则\n", encoding="utf-8")
            config_path.write_text(
                """
[[projects]]
id = "task_dashboard"
task_root_rel = "任务规划"

[[projects.channels]]
name = "子级02-运行时样本"
desc = "运行时样本"
cli_type = "codex"
""".strip()
                + "\n",
                encoding="utf-8",
            )
            ctx = SimpleNamespace(
                require_token=lambda: True,
                read_body_json=lambda _handler, max_bytes=0: {
                    "projectId": "task_dashboard",
                    "channelName": "子级02-运行时样本",
                    "cliType": "codebuddy",
                },
                json_response=_json_response,
                safe_text=lambda value, max_len: ("" if value is None else str(value))[:max_len],
                config_toml_path=lambda: config_path,
                repo_root=lambda: repo_root,
            )
            handler = SimpleNamespace(
                path="/api/channels/static-instruction-files/repair",
                status=None,
                payload=None,
            )

            handled = RouteDispatcher(ctx).dispatch_post(handler)

            self.assertTrue(handled)
            self.assertEqual(handler.status, 200)
            self.assertTrue((channel_root / "CODEBUDDY.md").exists())
            mirror = ((handler.payload.get("static_instruction_files") or {}).get("mirrors") or [])[0]
            self.assertEqual(mirror.get("syncStatus"), "synced")

    def test_delete_channel_soft_deletes_sessions_and_binding(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo_root = Path(td)
            config_path = repo_root / "config.toml"
            task_root = repo_root / "任务规划"
            channel_name = "辅助98-删除样本"
            channel_root = task_root / channel_name
            channel_root.mkdir(parents=True, exist_ok=True)
            (channel_root / "README.md").write_text("delete me", encoding="utf-8")
            config_path.write_text(
                """
[[projects]]
id = "task_dashboard"
task_root_rel = "任务规划"

[[projects.channels]]
name = "辅助98-删除样本"
desc = "delete"
""".strip()
                + "\n",
                encoding="utf-8",
            )

            run_store = server.RunStore(repo_root / ".runtime" / "stable" / ".runs")
            session_store = server.SessionStore(base_dir=run_store.runs_dir.parent)
            binding_store = server.SessionBindingStore(runs_dir=run_store.runs_dir)
            session = session_store.create_session(
                "task_dashboard",
                channel_name,
                cli_type="codex",
                alias="删除样本主会话",
                session_id="019caaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            )
            binding_store.save_binding(session["id"], "task_dashboard", channel_name, "codex")

            ctx = SimpleNamespace(
                require_token=lambda: True,
                read_body_json=lambda _handler, max_bytes=0: {
                    "projectId": "task_dashboard",
                    "channelName": channel_name,
                    "confirmChannelName": channel_name,
                },
                json_response=_json_response,
                safe_text=server._safe_text,
                find_project_cfg=lambda pid: {"id": pid, "task_root_rel": "任务规划"} if pid == "task_dashboard" else None,
                project_channel_exists=lambda pid, cname: pid == "task_dashboard" and cname == channel_name,
                session_store=session_store,
                session_binding_store=binding_store,
                config_toml_path=lambda: config_path,
                repo_root=lambda: repo_root,
                decorate_sessions_display_fields=lambda rows: rows,
            )
            handler = SimpleNamespace(status=None, payload=None)

            with patch("task_dashboard.routes.main.runtime_clear_dashboard_cfg_cache", lambda: None):
                RouteDispatcher(ctx)._handle_channel_delete_post(handler)

            self.assertEqual(handler.status, 200)
            self.assertTrue(handler.payload["ok"])
            self.assertEqual(handler.payload["action"], "delete_channel")
            self.assertTrue(handler.payload["deleted"]["configEntry"])
            self.assertTrue(handler.payload["deleted"]["channelRootDeleted"])
            self.assertTrue(handler.payload["deleted"]["keptRuntimeRuns"])
            self.assertEqual(handler.payload["sessions"]["count"], 1)
            self.assertEqual(handler.payload["bindings"]["count"], 1)
            self.assertFalse(channel_root.exists())
            self.assertIsNone(binding_store.get_binding(session["id"]))

            remaining = session_store.list_sessions("task_dashboard", channel_name, include_deleted=True)
            self.assertEqual(len(remaining), 1)
            self.assertTrue(remaining[0]["is_deleted"])
            self.assertEqual(remaining[0]["deleted_reason"], "channel_deleted")
            self.assertNotIn(channel_name, config_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
