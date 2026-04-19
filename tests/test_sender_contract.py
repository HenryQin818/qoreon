# -*- coding: utf-8 -*-

import unittest

from task_dashboard.sender_contract import normalize_sender_fields, validate_sender_consistency
from task_dashboard.runtime.request_parsing import parse_announce_request
from task_dashboard.runtime.scheduler_helpers import _extract_run_extra_fields, _sanitize_run_extra_meta


class SenderContractTests(unittest.TestCase):
    def test_normalize_snake_case_agent(self) -> None:
        src = {
            "sender_type": "agent",
            "sender_id": "sub06",
            "sender_name": "子级06",
        }
        out = normalize_sender_fields(src)
        self.assertEqual(out["sender_type"], "agent")
        self.assertEqual(out["sender_id"], "sub06")
        self.assertEqual(out["sender_name"], "子级06")

    def test_normalize_camel_case_user_defaults(self) -> None:
        src = {"senderType": "user"}
        out = normalize_sender_fields(src)
        self.assertEqual(out["sender_type"], "user")
        self.assertEqual(out["sender_id"], "user")
        self.assertEqual(out["sender_name"], "用户")

    def test_validate_legacy_when_missing_all(self) -> None:
        out = validate_sender_consistency({})
        self.assertTrue(out["legacy"])
        self.assertTrue(out["ok"])  # warn only
        codes = {i["code"] for i in out["issues"]}
        self.assertIn("sender_type_missing", codes)
        self.assertIn("sender_identity_empty", codes)

    def test_validate_invalid_type_error(self) -> None:
        out = validate_sender_consistency({"sender_type": "robot"})
        self.assertFalse(out["ok"])
        codes = {i["code"] for i in out["issues"]}
        self.assertIn("invalid_sender_type", codes)
        self.assertEqual(out["normalized"]["sender_type"], "legacy")

    def test_validate_agent_without_identity_error(self) -> None:
        out = validate_sender_consistency({"sender_type": "agent"})
        self.assertFalse(out["ok"])
        codes = {i["code"] for i in out["issues"]}
        self.assertIn("agent_identity_missing", codes)

    def test_normalize_infers_agent_from_sender_agent_ref(self) -> None:
        out = normalize_sender_fields(
            {
                "message_kind": "collab_update",
                "sender_agent_ref": {
                    "alias": "服务开发-通讯能力",
                    "session_id": "019cfee1-ffc9-78c0-bf80-70470c772e2a",
                },
                "source_ref": {
                    "project_id": "task_dashboard",
                    "channel_name": "子级02-CCB运行时（server-并发-安全-启动）",
                    "session_id": "019cfee1-ffc9-78c0-bf80-70470c772e2a",
                },
                "callback_to": {
                    "channel_name": "子级02-CCB运行时（server-并发-安全-启动）",
                    "session_id": "019cfee1-ffc9-78c0-bf80-70470c772e2a",
                },
            }
        )
        self.assertEqual(out["sender_type"], "agent")
        self.assertEqual(out["sender_id"], "019cfee1-ffc9-78c0-bf80-70470c772e2a")
        self.assertEqual(out["sender_name"], "服务开发-通讯能力")

    def test_normalize_infers_agent_sender_name_from_source_agent_alias_before_channel_name(self) -> None:
        out = normalize_sender_fields(
            {
                "message_kind": "collab_update",
                "source_agent_alias": "服务开发",
                "source_ref": {
                    "project_id": "task_dashboard",
                    "channel_name": "子级02-CCB运行时（server-并发-安全-启动）",
                    "session_id": "019cfee1-b75a-71c2-8146-f1d04ee96daf",
                },
                "target_ref": {
                    "project_id": "task_dashboard",
                    "channel_name": "主体-总控（合并与验收）",
                },
                "callback_to": {
                    "session_id": "019cfee1-b75a-71c2-8146-f1d04ee96daf",
                },
            }
        )
        self.assertEqual(out["sender_type"], "agent")
        self.assertEqual(out["sender_id"], "019cfee1-b75a-71c2-8146-f1d04ee96daf")
        self.assertEqual(out["sender_name"], "服务开发")

    def test_normalize_infers_system_from_callback_message_kind(self) -> None:
        out = normalize_sender_fields({"message_kind": "system_callback"})
        self.assertEqual(out["sender_type"], "system")
        self.assertEqual(out["sender_id"], "system")
        self.assertEqual(out["sender_name"], "系统")

    def test_parse_announce_request_fills_target_ref_from_route_target(self) -> None:
        out = parse_announce_request(
            {
                "projectId": "task_dashboard",
                "channelName": "主体-总控（合并与验收）",
                "sessionId": "sid-target",
                "message": "hello",
            },
            extract_sender_fields=lambda payload: normalize_sender_fields(payload),
            extract_run_extra_fields=lambda payload: {
                "source_ref": {
                    "project_id": "task_dashboard",
                    "channel_name": "子级02-CCB运行时（server-并发-安全-启动）",
                    "session_id": "sid-source",
                    "run_id": "run-source",
                },
                "message_kind": "collab_update",
            },
            derive_session_work_context=lambda *args, **kwargs: {},
            coerce_bool=lambda value, default=False: bool(value) if value is not None else default,
            build_local_server_origin=lambda host, port: "",
            session_data=None,
            environment_name="stable",
            worktree_root="",
            local_server_host="127.0.0.1",
            local_server_port=18765,
        )
        extra = out["run_extra_fields"]
        self.assertEqual(extra["message_kind"], "collab_update")
        self.assertEqual(extra["source_ref"]["session_id"], "sid-source")
        self.assertEqual(
            extra["target_ref"],
            {
                "project_id": "task_dashboard",
                "channel_name": "主体-总控（合并与验收）",
                "session_id": "sid-target",
            },
        )
        context = extra["project_execution_context"]
        self.assertEqual(context["context_source"], "server_default")
        self.assertEqual((context["target"] or {}).get("session_id"), "sid-target")
        self.assertEqual((context["source"] or {}).get("project_id"), "task_dashboard")
        self.assertFalse(bool(((context.get("override") or {}).get("applied"))))

    def test_parse_announce_request_infers_agent_sender_from_structured_refs(self) -> None:
        out = parse_announce_request(
            {
                "projectId": "task_dashboard",
                "channelName": "子级04-前端体验（task-overview 页面交互）",
                "sessionId": "019c561c-8b6c-7c60-b66f-63096d1a4de9",
                "message": "请继续推进。",
                "message_kind": "collab_update",
                "source_ref": {
                    "project_id": "task_dashboard",
                    "channel_name": "子级02-CCB运行时（server-并发-安全-启动）",
                    "session_id": "019cfee1-ffc9-78c0-bf80-70470c772e2a",
                },
                "sender_agent_ref": {
                    "alias": "服务开发-通讯能力",
                    "session_id": "019cfee1-ffc9-78c0-bf80-70470c772e2a",
                },
                "callback_to": {
                    "channel_name": "子级02-CCB运行时（server-并发-安全-启动）",
                    "session_id": "019cfee1-ffc9-78c0-bf80-70470c772e2a",
                },
            },
            extract_sender_fields=lambda payload: normalize_sender_fields(payload),
            extract_run_extra_fields=lambda payload: _extract_run_extra_fields(payload),
            derive_session_work_context=lambda *args, **kwargs: {},
            coerce_bool=lambda value, default=False: bool(value) if value is not None else default,
            build_local_server_origin=lambda host, port: "",
            session_data=None,
            environment_name="stable",
            worktree_root="",
            local_server_host="127.0.0.1",
            local_server_port=18765,
        )
        sender = out["sender_fields"]
        self.assertEqual(sender["sender_type"], "agent")
        self.assertEqual(sender["sender_id"], "019cfee1-ffc9-78c0-bf80-70470c772e2a")
        self.assertEqual(sender["sender_name"], "服务开发-通讯能力")

    def test_parse_announce_request_adds_visible_flag_only(self) -> None:
        out = parse_announce_request(
            {
                "projectId": "task_dashboard",
                "channelName": "主体-总控（合并与验收）",
                "sessionId": "sid-target",
                "message": "\n".join(
                    [
                        "回执任务: 正式消息最小恢复",
                        "执行阶段: 启动",
                        "本次目标: 补轻量投影",
                        "当前结论: 已接手",
                        "需要对方: 回五段式结论",
                        "预期结果: 给出最小恢复顺序",
                    ]
                ),
                "message_kind": "collab_update",
                "interaction_mode": "task_with_receipt",
                "source_ref": {
                    "project_id": "task_dashboard",
                    "channel_name": "子级02-CCB运行时（server-并发-安全-启动）",
                    "session_id": "sid-source",
                },
                "sender_agent_ref": {
                    "alias": "服务开发-通讯能力",
                    "session_id": "sid-source",
                },
                "callback_to": {
                    "channel_name": "子级02-CCB运行时（server-并发-安全-启动）",
                    "session_id": "sid-source",
                },
            },
            extract_sender_fields=lambda payload: normalize_sender_fields(payload),
            extract_run_extra_fields=lambda payload: _extract_run_extra_fields(payload),
            derive_session_work_context=lambda *args, **kwargs: {},
            coerce_bool=lambda value, default=False: bool(value) if value is not None else default,
            build_local_server_origin=lambda host, port: "",
            session_data=None,
            environment_name="stable",
            worktree_root="",
            local_server_host="127.0.0.1",
            local_server_port=18765,
        )
        extra = out["run_extra_fields"]
        self.assertTrue(bool(extra.get("visible_in_channel_chat")))
        self.assertNotIn("communication_view", extra)
        self.assertNotIn("receipt_summary", extra)

    def test_extract_run_extra_fields_reads_run_extra_meta_upgrade_fields(self) -> None:
        extra = _extract_run_extra_fields(
            {
                "projectId": "task_dashboard",
                "runExtraMeta": {
                    "messageKind": "collab_update",
                    "sourceRef": {
                        "projectId": "task_dashboard",
                        "channelName": "主体-总控（合并与验收）",
                        "sessionId": "019c8bee-9dbf-7640-a774-1021d68fa6fe",
                        "runId": "run-source",
                    },
                    "callbackTo": {"sessionId": "none"},
                    "ownerRef": {
                        "channelName": "子级08-测试与验收（功能-回归-发布）",
                        "agentName": "测试验收",
                        "sessionId": "019c8bee-9dbf-7640-a774-1021d68fa6fe",
                        "alias": "测试验收",
                    },
                    "senderAgentRef": {
                        "agentName": "总控-项目经理",
                        "sessionId": "none",
                        "alias": "总控-项目经理",
                    },
                },
            }
        )
        self.assertEqual(extra["message_kind"], "collab_update")
        self.assertEqual(extra["source_ref"]["channel_name"], "主体-总控（合并与验收）")
        self.assertEqual(extra["callback_to"], {"channel_name": "主体-总控（合并与验收）"})
        self.assertEqual(extra["owner_ref"]["agent_name"], "测试验收")
        self.assertEqual(extra["sender_agent_ref"]["agent_name"], "总控-项目经理")
        self.assertNotIn("session_id", extra["sender_agent_ref"])

    def test_sanitize_run_extra_meta_persists_owner_and_sender_refs(self) -> None:
        meta = _sanitize_run_extra_meta(
            {
                "callbackTo": {"channelName": "主体-总控（合并与验收）", "sessionId": "019c8bee-9dbf-7640-a774-1021d68fa6fe"},
                "ownerRef": {
                    "channelName": "子级08-测试与验收（功能-回归-发布）",
                    "agentName": "测试验收",
                    "sessionId": "019c8bee-9dbf-7640-a774-1021d68fa6fe",
                    "alias": "测试验收",
                },
                "senderAgentRef": {
                    "agentName": "总控-项目经理",
                    "sessionId": "none",
                    "alias": "总控-项目经理",
                },
            }
        )
        self.assertEqual(meta["callback_to"]["channel_name"], "主体-总控（合并与验收）")
        self.assertEqual(meta["owner_ref"]["channel_name"], "子级08-测试与验收（功能-回归-发布）")
        self.assertEqual(meta["sender_agent_ref"]["alias"], "总控-项目经理")
        self.assertNotIn("session_id", meta["sender_agent_ref"])


if __name__ == "__main__":
    unittest.main()
