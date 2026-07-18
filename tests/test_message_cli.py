# -*- coding: utf-8 -*-

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from task_dashboard import message_cli
from task_dashboard.runtime.scheduler_helpers import _extract_run_extra_fields, _sanitize_run_extra_meta
from task_dashboard.session_store import SessionStore


SID_TARGET = "019d232f-02f1-7781-9de8-2333f2417e73"
SID_TARGET_2 = "019d232f-02f1-7781-9de8-2333f2417e74"
SID_SOURCE = "019dbd03-829b-78e1-8816-ab73c2f01071"


class MessageCliTests(unittest.TestCase):
    def _store(self, root: Path) -> SessionStore:
        return SessionStore(root)

    def _create_session(
        self,
        root: Path,
        *,
        project_id: str = "task_dashboard",
        channel_name: str = "目标通道",
        session_id: str = SID_TARGET,
        alias: str = "目标Agent",
    ) -> None:
        self._store(root).create_session(
            project_id,
            channel_name,
            session_id=session_id,
            alias=alias,
        )

    def _create_source(self, root: Path) -> None:
        self._store(root).create_session(
            "task_dashboard",
            "来源通道",
            session_id=SID_SOURCE,
            alias="产品-通讯能力",
        )

    def _run(self, argv: list[str]) -> tuple[int, dict]:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = message_cli.main(argv + ["--json"])
        return code, json.loads(buf.getvalue())

    def test_dry_run_send_builds_payload_without_posting(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._create_session(root)
            self._create_source(root)
            with mock.patch("task_dashboard.message_cli.post_announce") as post:
                code, payload = self._run(
                    [
                        "send",
                        "--root",
                        str(root),
                        "--project",
                        "task_dashboard",
                        "--to-agent",
                        "目标Agent",
                        "--mode",
                        "task_with_receipt",
                        "--message",
                        "请处理。",
                        "--callback-session-id",
                        SID_SOURCE,
                        "--client-message-id",
                        "cmid-1",
                        "--dry-run",
                    ]
                )
            self.assertEqual(code, 0)
            post.assert_not_called()
            self.assertEqual(payload["state"], "drafted")
            draft = payload["payload"]
            self.assertEqual(draft["sessionId"], SID_TARGET)
            self.assertEqual(draft["interaction_mode"], "task_with_receipt")
            self.assertEqual(draft["client_message_id"], "cmid-1")
            self.assertNotIn("visible_in_channel_chat", draft)
            self.assertNotIn("announce_run_id", draft)

    def test_three_interaction_modes_build_structured_fields(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._create_session(root)
            self._create_source(root)
            for mode in ("dialog_now", "task_with_receipt", "notify_only"):
                argv = [
                    "draft",
                    "--root",
                    str(root),
                    "--session-id",
                    SID_TARGET,
                    "--mode",
                    mode,
                    "--message",
                    "hello",
                    "--callback-session-id",
                    SID_SOURCE,
                ]
                code, payload = self._run(argv)
                self.assertEqual(code, 0)
                draft = payload["payload"]
                self.assertEqual(draft["message_kind"], "collab_update")
                self.assertEqual(draft["interaction_mode"], mode)
                self.assertEqual(draft["target_ref"]["session_id"], SID_TARGET)
                self.assertEqual(draft["callback_to"]["session_id"], SID_SOURCE)
                self.assertEqual(draft["sender_agent_ref"]["role"], "执行位")
                self.assertEqual(draft["owner_ref"]["role"], "主负责位")

    def test_task_with_receipt_requires_callback(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._create_session(root)
            code, payload = self._run(
                [
                    "draft",
                    "--root",
                    str(root),
                    "--session-id",
                    SID_TARGET,
                    "--mode",
                    "task_with_receipt",
                    "--message",
                    "需要回执。",
                ]
            )
            self.assertEqual(code, 1)
            self.assertEqual(payload["state"], "blocked")
            self.assertEqual(payload["blocking_error"]["code"], "callback_missing")

    def test_doctor_and_receipt_commands_are_available(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._create_session(root)
            code, payload = self._run(
                [
                    "doctor",
                    "--root",
                    str(root),
                    "--session-id",
                    SID_TARGET,
                    "--mode",
                    "notify_only",
                ]
            )
            self.assertEqual(code, 0)
            self.assertEqual(payload["state"], "ready")

            code, payload = self._run(
                [
                    "receipt",
                    "--root",
                    str(root),
                    "--session-id",
                    SID_TARGET,
                    "--message",
                    "当前结论 / 是否通过或放行 / 唯一阻塞 / 关键路径或 run_id / 下一步动作",
                    "--dry-run",
                ]
            )
            self.assertEqual(code, 0)
            self.assertEqual(payload["payload"]["interaction_mode"], "notify_only")

    def test_multiple_matching_agents_are_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._create_session(root, session_id=SID_TARGET, alias="同名Agent")
            self._create_session(root, session_id=SID_TARGET_2, alias="同名Agent", channel_name="另一个通道")
            code, payload = self._run(
                [
                    "resolve",
                    "--root",
                    str(root),
                    "--to-agent",
                    "同名Agent",
                ]
            )
            self.assertEqual(code, 1)
            self.assertEqual(payload["blocking_error"]["code"], "agent_ambiguous")
            self.assertEqual(len(payload["candidates"]), 2)

    def test_channel_multi_active_returns_primary_governance_item(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._create_session(root, session_id=SID_TARGET, alias="主 Agent", channel_name="同通道")
            self._create_session(root, session_id=SID_TARGET_2, alias="子 Agent", channel_name="同通道")
            code, payload = self._run(
                [
                    "resolve",
                    "--root",
                    str(root),
                    "--channel",
                    "同通道",
                ]
            )

            self.assertEqual(code, 1)
            self.assertEqual(payload["blocking_error"]["code"], "agent_ambiguous")
            governance_items = payload["blocking_error"].get("governance_items") or []
            self.assertEqual(governance_items[0]["code"], "channel_primary_disambiguation_required")
            self.assertEqual(governance_items[0]["endpoint"], "POST /api/channel-sessions/manage")
            self.assertIn("primary_session_id", governance_items[0]["suggested_action"])

    def test_deleted_context_exhausted_and_project_mismatch_are_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            store = self._store(root)
            store.create_session("task_dashboard", "目标通道", session_id=SID_TARGET, alias="已删除")
            store.delete_session(SID_TARGET)
            code, payload = self._run(["resolve", "--root", str(root), "--session-id", SID_TARGET])
            self.assertEqual(code, 1)
            self.assertEqual(payload["blocking_error"]["code"], "target_session_inactive")

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._create_session(root, session_id=SID_TARGET)
            path = root / ".sessions" / "task_dashboard.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            data["sessions"][0]["context_binding_state"] = "context_exhausted"
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            code, payload = self._run(["resolve", "--root", str(root), "--session-id", SID_TARGET])
            self.assertEqual(code, 1)
            self.assertEqual(payload["blocking_error"]["code"], "context_exhausted")

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._create_session(root, project_id="other_project", session_id=SID_TARGET)
            code, payload = self._run(
                [
                    "resolve",
                    "--root",
                    str(root),
                    "--project",
                    "task_dashboard",
                    "--session-id",
                    SID_TARGET,
                ]
            )
            self.assertEqual(code, 1)
            self.assertEqual(payload["blocking_error"]["code"], "project_mismatch")

    def test_send_posts_only_to_announce(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._create_session(root)
            self._create_source(root)
            seen: list[tuple[str, str]] = []

            def fake_http(url: str, *, method: str = "GET", body=None, token: str = "", timeout: float = 20.0):
                seen.append((method, url))
                self.assertEqual(method, "POST")
                self.assertTrue(url.endswith("/api/codex/announce"))
                self.assertNotIn("resume", url)
                return 200, {
                    "ok": True,
                    "run": {
                        "id": "20260517-000000-abcdef12",
                        "projectId": "task_dashboard",
                        "channelName": "目标通道",
                        "sessionId": SID_TARGET,
                        "visible_in_channel_chat": True,
                        "target_ref": {
                            "project_id": "task_dashboard",
                            "channel_name": "目标通道",
                            "session_id": SID_TARGET,
                        },
                    },
                }

            with mock.patch("task_dashboard.message_cli._http_json", side_effect=fake_http):
                code, payload = self._run(
                    [
                        "send",
                        "--root",
                        str(root),
                        "--session-id",
                        SID_TARGET,
                        "--mode",
                        "notify_only",
                        "--message",
                        "正式通知。",
                    ]
                )
            self.assertEqual(code, 0)
            self.assertEqual(payload["state"], "delivered")
            self.assertEqual(payload["announce_run_id"], "20260517-000000-abcdef12")
            self.assertEqual(len(seen), 1)

    def test_send_wait_verify_polls_until_delivered(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._create_session(root)
            run_id = "20260517-000000-abcdef12"

            def fake_http(url: str, *, method: str = "GET", body=None, token: str = "", timeout: float = 20.0):
                return 200, {
                    "ok": True,
                    "run": {
                        "id": run_id,
                        "projectId": "task_dashboard",
                        "channelName": "目标通道",
                        "sessionId": SID_TARGET,
                        "visible_in_channel_chat": False,
                        "target_ref": {
                            "project_id": "task_dashboard",
                            "channel_name": "目标通道",
                            "session_id": SID_TARGET,
                        },
                    },
                }

            delivered_meta = {
                "id": run_id,
                "projectId": "task_dashboard",
                "channelName": "目标通道",
                "sessionId": SID_TARGET,
                "status": "done",
                "visible_in_channel_chat": True,
                "target_ref": {
                    "project_id": "task_dashboard",
                    "channel_name": "目标通道",
                    "session_id": SID_TARGET,
                },
            }
            with (
                mock.patch("task_dashboard.message_cli._http_json", side_effect=fake_http),
                mock.patch("task_dashboard.message_cli._load_local_run", side_effect=[None, delivered_meta]),
                mock.patch("task_dashboard.message_cli._load_remote_run", return_value=None),
            ):
                code, payload = self._run(
                    [
                        "send",
                        "--root",
                        str(root),
                        "--session-id",
                        SID_TARGET,
                        "--mode",
                        "notify_only",
                        "--message",
                        "正式通知。",
                        "--wait-verify",
                        "--verify-timeout",
                        "0.2",
                        "--verify-interval",
                        "0",
                    ]
                )
            self.assertEqual(code, 0)
            self.assertEqual(payload["state"], "delivered")
            self.assertTrue(payload["wait_verify"])
            self.assertEqual(payload["delivery"]["target_session_id"], SID_TARGET)
            self.assertIn("当前结论: 已完成证据闭环", payload["receipt_block"])

    def test_wait_verify_returns_unverified_when_evidence_missing(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._create_session(root)
            run_id = "20260517-000000-abcdef12"

            def fake_http(url: str, *, method: str = "GET", body=None, token: str = "", timeout: float = 20.0):
                return 200, {
                    "ok": True,
                    "run": {
                        "id": run_id,
                        "projectId": "task_dashboard",
                        "channelName": "目标通道",
                        "sessionId": SID_TARGET,
                    },
                }

            with (
                mock.patch("task_dashboard.message_cli._http_json", side_effect=fake_http),
                mock.patch("task_dashboard.message_cli._load_local_run", return_value=None),
                mock.patch("task_dashboard.message_cli._load_remote_run", return_value=None),
            ):
                code, payload = self._run(
                    [
                        "send",
                        "--root",
                        str(root),
                        "--session-id",
                        SID_TARGET,
                        "--mode",
                        "notify_only",
                        "--message",
                        "正式通知。",
                        "--wait-verify",
                        "--verify-timeout",
                        "0",
                    ]
                )
            self.assertEqual(code, 1)
            self.assertEqual(payload["state"], "delivery_unverified")
            self.assertEqual(payload["blocking_error"]["code"], "delivery_unverified")
            self.assertIn("不判定已送达", payload["receipt_block"])

    def test_missing_target_guides_agents_to_session_governance_not_manual_lookup(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            code, payload = self._run(
                [
                    "resolve",
                    "--root",
                    str(root),
                    "--to-agent",
                    "不存在的Agent",
                ]
            )
            self.assertEqual(code, 1)
            self.assertEqual(payload["blocking_error"]["code"], "target_session_missing")
            self.assertEqual(payload["blocking_error"]["lookup_scope"], "active_session_store")
            self.assertIn("不要通过读源码", payload["blocking_error"]["next_action"])

    def test_resolve_prefers_live_stable_session_store_before_repo_compat_store(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            stable_root = root / ".runtime" / "stable"
            self._create_session(
                stable_root,
                project_id="ndt",
                channel_name="业务01-沙盘推演与沙盘建立",
                session_id=SID_TARGET,
                alias="沙盘-业务规划",
            )
            code, payload = self._run(
                [
                    "resolve",
                    "--root",
                    str(root),
                    "--project",
                    "ndt",
                    "--to-agent",
                    "沙盘-业务规划",
                ]
            )
            self.assertEqual(code, 0)
            self.assertEqual(payload["state"], "resolved")
            self.assertEqual(payload["target_ref"]["session_id"], SID_TARGET)
            self.assertEqual(payload["target_ref"]["channel_name"], "业务01-沙盘推演与沙盘建立")
            self.assertEqual(Path(payload["session_store_root"]).resolve(), stable_root.resolve())

    def test_status_ignores_prefilled_delivery_state_without_run_evidence(self) -> None:
        result = message_cli.classify_delivery(
            {
                "announce_run_id": "20260517-prefill",
                "delivery_state": "delivered",
                "visible_in_channel_chat": True,
                "sessionId": SID_TARGET,
            },
            expected_session_id=SID_TARGET,
            run_id="20260517-prefill",
        )
        self.assertEqual(result["state"], "delivery_unverified")

    def test_status_delivered_from_local_run_meta(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            runs_dir = root / ".runtime" / "stable" / ".runs"
            hot = runs_dir / "hot"
            hot.mkdir(parents=True)
            run_id = "20260517-000000-abcdef12"
            (hot / f"{run_id}.json").write_text(
                json.dumps(
                    {
                        "id": run_id,
                        "projectId": "task_dashboard",
                        "channelName": "目标通道",
                        "sessionId": SID_TARGET,
                        "visible_in_channel_chat": True,
                        "target_ref": {
                            "project_id": "task_dashboard",
                            "channel_name": "目标通道",
                            "session_id": SID_TARGET,
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            code, payload = self._run(
                [
                    "status",
                    "--root",
                    str(root),
                    "--run-id",
                    run_id,
                    "--session-id",
                    SID_TARGET,
                    "--base-url",
                    "",
                ]
            )
            self.assertEqual(code, 0)
            self.assertEqual(payload["state"], "delivered")
            self.assertIn("当前结论: 已完成证据闭环", payload["receipt_block"])
            self.assertNotIn("证据不足", payload["receipt_block"])

    def test_announce_extra_meta_preserves_cli_fields(self) -> None:
        extra = _extract_run_extra_fields(
            {
                "message_kind": "collab_update",
                "interaction_mode": "notify_only",
                "client_message_id": "cmid-preserve",
                "sender_agent_ref": {
                    "alias": "后端-通讯能力",
                    "session_id": SID_SOURCE,
                    "role": "执行位",
                },
                "owner_ref": {
                    "alias": "产品-通讯能力",
                    "session_id": SID_SOURCE,
                    "role": "主负责位",
                    "channel_name": "辅助04",
                },
            }
        )
        self.assertEqual(extra["client_message_id"], "cmid-preserve")
        self.assertEqual(extra["sender_agent_ref"]["role"], "执行位")
        self.assertEqual(extra["owner_ref"]["role"], "主负责位")

        sanitized = _sanitize_run_extra_meta(extra)
        self.assertEqual(sanitized["client_message_id"], "cmid-preserve")
        self.assertEqual(sanitized["sender_agent_ref"]["role"], "执行位")
        self.assertEqual(sanitized["owner_ref"]["role"], "主负责位")


if __name__ == "__main__":
    unittest.main()
