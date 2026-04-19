import tempfile
import unittest
from pathlib import Path
from unittest import mock

import server
from task_dashboard.runtime.run_routes import get_run_detail_response, list_runs_response


class TestRunRoutes(unittest.TestCase):
    def test_run_store_list_runs_light_reuses_live_index_without_rescan(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            for idx in range(3):
                store.create_run(
                    project_id="task_dashboard",
                    channel_name="子级02-CCB运行时（server-并发-安全-启动）",
                    session_id=f"session-{idx}",
                    message=f"ping-{idx}",
                )

            first = store.list_runs(project_id="task_dashboard", limit=2, payload_mode="light")
            self.assertEqual(len(first), 2)

            with mock.patch.object(
                store,
                "_iter_live_meta_paths",
                side_effect=AssertionError("live index should serve hot list_runs without rescanning disk"),
            ):
                second = store.list_runs(project_id="task_dashboard", limit=2, payload_mode="light")

            self.assertEqual(len(second), 2)

    def test_run_store_list_runs_light_reflects_save_meta_after_index_built(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            created = store.create_run(
                project_id="task_dashboard",
                channel_name="子级02-CCB运行时（server-并发-安全-启动）",
                session_id="session-1",
                message="ping",
            )
            run_id = str(created.get("id") or "").strip()
            self.assertTrue(run_id)

            first = store.list_runs(project_id="task_dashboard", limit=1, payload_mode="light")
            self.assertEqual(len(first), 1)
            self.assertEqual(str(first[0].get("status") or ""), "queued")

            meta = store.load_meta(run_id) or {}
            meta["status"] = "error"
            meta["finishedAt"] = "2026-04-02T01:20:00+0800"
            meta["error"] = "run interrupted (server restarted or process exited)"
            store.save_meta(run_id, meta)

            with mock.patch.object(
                store,
                "_iter_live_meta_paths",
                side_effect=AssertionError("save_meta should refresh live index without full rescan"),
            ):
                second = store.list_runs(project_id="task_dashboard", limit=1, payload_mode="light")

            self.assertEqual(len(second), 1)
            self.assertEqual(str(second[0].get("status") or ""), "error")

    def test_list_runs_response_light_skips_session_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            created = store.create_run(
                project_id="task_dashboard",
                channel_name="子级02-CCB运行时（server-并发-安全-启动）",
                session_id="session-1",
                message="ping",
            )
            run_id = str(created.get("id") or "").strip()
            meta = store.load_meta(run_id) or {}
            meta["status"] = "error"
            meta["finishedAt"] = "2026-04-01T11:05:00+0800"
            meta["error"] = "run interrupted (server restarted or process exited)"
            store.save_meta(run_id, meta)

            captured: list[bool] = []

            def _fake_build(_store, row, **kwargs):
                captured.append(bool(kwargs.get("include_session_semantics")))
                return {
                    "display_state": str(row.get("status") or "").strip().lower(),
                    "queue_reason": "",
                    "blocked_by_run_id": "",
                    "outcome_state": "interrupted_infra",
                    "error_class": "infra_restart",
                    "effective_for_session_health": True,
                    "effective_for_session_preview": False,
                    "superseded_by_run_id": "",
                    "recovery_of_run_id": "",
                }

            with mock.patch("server._build_run_observability_fields", side_effect=_fake_build):
                code, payload = list_runs_response(
                    query_string="projectId=task_dashboard&sessionId=session-1&limit=10&payloadMode=light",
                    store=store,
                    scheduler=None,
                    maybe_trigger_restart_recovery_lazy=lambda *_args, **_kwargs: 0,
                    maybe_trigger_queued_recovery_lazy=lambda *_args, **_kwargs: 0,
                    build_run_observability_fields=server._build_run_observability_fields,
                )

            self.assertEqual(code, 200)
            self.assertGreaterEqual(len(captured), 1)
            self.assertTrue(all(flag is False for flag in captured))
            row = (payload.get("runs") or [])[0]
            self.assertEqual("interrupted_infra", row.get("outcome_state"))
            self.assertEqual("", row.get("superseded_by_run_id"))

    def test_list_runs_response_includes_first_batch_multicli_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            interrupted = store.create_run(
                project_id="task_dashboard",
                channel_name="子级03-多CLI适配器（codex-claude-opencode）",
                session_id="session-1",
                message="请恢复执行",
            )
            interrupted_id = str(interrupted.get("id") or "").strip()
            interrupted_meta = store.load_meta(interrupted_id) or {}
            interrupted_meta["status"] = "error"
            interrupted_meta["createdAt"] = "2026-04-01T11:00:44+0800"
            interrupted_meta["finishedAt"] = "2026-04-01T11:00:52+0800"
            interrupted_meta["error"] = "run interrupted (server restarted or process exited)"
            store.save_meta(interrupted_id, interrupted_meta)

            recovered = store.create_run(
                project_id="task_dashboard",
                channel_name="子级03-多CLI适配器（codex-claude-opencode）",
                session_id="session-1",
                message="系统恢复摘要",
                sender_type="system",
                sender_id="system",
                sender_name="系统",
            )
            recovered_id = str(recovered.get("id") or "").strip()
            recovered_meta = store.load_meta(recovered_id) or {}
            recovered_meta["status"] = "done"
            recovered_meta["createdAt"] = "2026-04-01T11:11:30+0800"
            recovered_meta["finishedAt"] = "2026-04-01T11:11:36+0800"
            recovered_meta["trigger_type"] = "restart_recovery_summary"
            recovered_meta["message_kind"] = "restart_recovery_summary"
            recovered_meta["lastPreview"] = "已恢复上次中断的队列，继续推进。"
            store.save_meta(recovered_id, recovered_meta)

            code, payload = list_runs_response(
                query_string="projectId=task_dashboard&sessionId=session-1&limit=10",
                store=store,
                scheduler=None,
                maybe_trigger_restart_recovery_lazy=lambda *_args, **_kwargs: 0,
                maybe_trigger_queued_recovery_lazy=lambda *_args, **_kwargs: 0,
                build_run_observability_fields=server._build_run_observability_fields,
            )

            self.assertEqual(code, 200)
            rows = {str(row.get("id") or ""): row for row in payload.get("runs") or [] if isinstance(row, dict)}
            interrupted_row = rows.get(interrupted_id) or {}
            recovered_row = rows.get(recovered_id) or {}
            self.assertEqual(interrupted_row.get("outcome_state"), "interrupted_infra")
            self.assertEqual(interrupted_row.get("error_class"), "infra_restart")
            self.assertFalse(bool(interrupted_row.get("effective_for_session_health")))
            self.assertFalse(bool(interrupted_row.get("effective_for_session_preview")))
            self.assertEqual(interrupted_row.get("superseded_by_run_id"), recovered_id)
            self.assertEqual(recovered_row.get("outcome_state"), "recovered_notice")
            self.assertEqual(recovered_row.get("error_class"), "infra_restart_recovered")
            self.assertTrue(bool(recovered_row.get("effective_for_session_health")))
            self.assertFalse(bool(recovered_row.get("effective_for_session_preview")))
            self.assertEqual(recovered_row.get("recovery_of_run_id"), interrupted_id)

    def test_list_runs_response_aligns_runtime_identity(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            created = store.create_run(
                project_id="task_dashboard",
                channel_name="子级02-CCB运行时（server-并发-安全-启动）",
                session_id="session-1",
                message="ping",
            )
            run_id = str(created.get("id") or "").strip()
            self.assertTrue(run_id)

            meta = store.load_meta(run_id) or {}
            meta["environment"] = "stable"
            meta.pop("localServerOrigin", None)
            meta["worktree_root"] = "/tmp/old-stable"
            store.save_meta(run_id, meta)

            code, payload = list_runs_response(
                query_string="limit=1",
                store=store,
                scheduler=None,
                maybe_trigger_restart_recovery_lazy=lambda *_args, **_kwargs: 0,
                maybe_trigger_queued_recovery_lazy=lambda *_args, **_kwargs: 0,
                build_run_observability_fields=lambda *_args, **_kwargs: {},
                environment_name="refactor",
                local_server_origin="http://127.0.0.1:18766",
                worktree_root="/tmp/refactor-root",
            )

            self.assertEqual(code, 200)
            row = payload["runs"][0]
            self.assertEqual(row["environment"], "refactor")
            self.assertEqual(row["localServerOrigin"], "http://127.0.0.1:18766")
            self.assertEqual(row["worktree_root"], "/tmp/refactor-root")
            ctx = row.get("project_execution_context") or {}
            self.assertEqual((ctx.get("source") or {}).get("environment"), "refactor")
            self.assertEqual((ctx.get("target") or {}).get("project_id"), "task_dashboard")
            self.assertFalse(bool(((ctx.get("override") or {}).get("applied"))))

            persisted = store.load_meta(run_id) or {}
            self.assertEqual(persisted.get("environment"), "refactor")
            self.assertEqual(persisted.get("localServerOrigin"), "http://127.0.0.1:18766")
            self.assertEqual(persisted.get("worktree_root"), "/tmp/refactor-root")

    def test_list_runs_response_does_not_trigger_restart_recovery_lazy(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            store.create_run(
                project_id="task_dashboard",
                channel_name="主体-总控（合并与验收）",
                session_id="session-1",
                message="ping",
            )

            called = {"restart": 0}

            def _unexpected_restart(*_args, **_kwargs):
                called["restart"] += 1
                raise AssertionError("restart recovery lazy should not be triggered by list read API")

            code, payload = list_runs_response(
                query_string="limit=1",
                store=store,
                scheduler=None,
                maybe_trigger_restart_recovery_lazy=_unexpected_restart,
                maybe_trigger_queued_recovery_lazy=lambda *_args, **_kwargs: 0,
                build_run_observability_fields=lambda *_args, **_kwargs: {},
            )

            self.assertEqual(code, 200)
            self.assertEqual(len(payload["runs"]), 1)
            self.assertEqual(called["restart"], 0)

    def test_get_run_detail_response_does_not_trigger_restart_recovery_lazy(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            created = store.create_run(
                project_id="task_dashboard",
                channel_name="主体-总控（合并与验收）",
                session_id="session-1",
                message="ping",
            )
            run_id = str(created.get("id") or "").strip()

            called = {"restart": 0}

            def _unexpected_restart(*_args, **_kwargs):
                called["restart"] += 1
                raise AssertionError("restart recovery lazy should not be triggered by detail read API")

            code, payload = get_run_detail_response(
                run_id=run_id,
                store=store,
                scheduler=None,
                maybe_trigger_restart_recovery_lazy=_unexpected_restart,
                maybe_trigger_queued_recovery_lazy=lambda *_args, **_kwargs: 0,
                build_run_observability_fields=lambda *_args, **_kwargs: {},
                error_hint=lambda _err: "",
            )

            self.assertEqual(code, 200)
            self.assertEqual(str((payload.get("run") or {}).get("id") or ""), run_id)
            self.assertEqual(called["restart"], 0)

    def test_get_run_detail_response_returns_process_aliases_and_persists_preview(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            created = store.create_run(
                project_id="task_dashboard",
                channel_name="主体-总控（合并与验收）",
                session_id="session-1",
                message="ping",
            )
            run_id = str(created.get("id") or "").strip()
            log_path = store._paths(run_id)["log"]
            log_path.write_text(
                "\n".join(
                    [
                        '[stdout] {"type":"item.completed","item":{"type":"agent_message","text":"第一条过程消息"}}',
                        '[stdout] {"type":"item.completed","item":{"type":"agent_message","text":"第二条过程消息"}}',
                    ]
                ),
                encoding="utf-8",
            )

            code, payload = get_run_detail_response(
                run_id=run_id,
                store=store,
                scheduler=None,
                maybe_trigger_restart_recovery_lazy=lambda *_args, **_kwargs: 0,
                maybe_trigger_queued_recovery_lazy=lambda *_args, **_kwargs: 0,
                build_run_observability_fields=lambda *_args, **_kwargs: {},
                error_hint=lambda _err: "",
            )

            self.assertEqual(code, 200)
            self.assertEqual(payload.get("process"), payload.get("logTail"))
            self.assertIn("第一条过程消息", str(payload.get("logPreview") or ""))
            self.assertEqual(payload.get("agentMessages"), ["第一条过程消息", "第二条过程消息"])
            ctx = ((payload.get("run") or {}).get("project_execution_context")) or {}
            self.assertEqual((ctx.get("target") or {}).get("project_id"), "task_dashboard")
            self.assertEqual((ctx.get("source") or {}).get("session_id"), "session-1")

            persisted = store.load_meta(run_id) or {}
            self.assertEqual(int(persisted.get("agentMessagesCount") or 0), 2)
            self.assertIn("第一条过程消息", str(persisted.get("logPreview") or ""))
            self.assertEqual(str(persisted.get("partialPreview") or ""), "第二条过程消息")

    def test_get_run_detail_response_includes_structured_process_rows(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            created = store.create_run(
                project_id="task_dashboard",
                channel_name="主体-总控（合并与验收）",
                session_id="session-1",
                message="ping",
            )
            run_id = str(created.get("id") or "").strip()
            meta = store.load_meta(run_id) or {}
            meta["processRows"] = [
                {"text": "第一条过程消息", "at": "2026-03-20T00:08:15+0800"},
                {"text": "第二条过程消息", "at": "2026-03-20T00:08:22+0800"},
            ]
            store.save_meta(run_id, meta)

            code, payload = get_run_detail_response(
                run_id=run_id,
                store=store,
                scheduler=None,
                maybe_trigger_restart_recovery_lazy=lambda *_args, **_kwargs: 0,
                maybe_trigger_queued_recovery_lazy=lambda *_args, **_kwargs: 0,
                build_run_observability_fields=lambda *_args, **_kwargs: {},
                error_hint=lambda _err: "",
            )

            self.assertEqual(code, 200)
            self.assertEqual(
                payload.get("processRows"),
                [
                    {"text": "第一条过程消息", "at": "2026-03-20T00:08:15+0800"},
                    {"text": "第二条过程消息", "at": "2026-03-20T00:08:22+0800"},
                ],
            )

    def test_get_run_detail_response_backfills_previews_from_process_rows(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            created = store.create_run(
                project_id="task_dashboard",
                channel_name="主体-总控（合并与验收）",
                session_id="session-1",
                message="请诊断当前详情为什么看起来像空白",
            )
            run_id = str(created.get("id") or "").strip()
            meta = store.load_meta(run_id) or {}
            meta["status"] = "running"
            meta["messagePreview"] = ""
            meta["lastPreview"] = ""
            meta["partialPreview"] = ""
            meta["processRows"] = [
                {"text": "已定位到 active run 仍在持续输出过程行", "at": "2026-03-30T15:19:20+0800"},
                {"text": "正在比对详情接口与列表摘要的聚合差异", "at": "2026-03-30T15:19:28+0800"},
            ]
            store.save_meta(run_id, meta)

            code, payload = get_run_detail_response(
                run_id=run_id,
                store=store,
                scheduler=None,
                maybe_trigger_restart_recovery_lazy=lambda *_args, **_kwargs: 0,
                maybe_trigger_queued_recovery_lazy=lambda *_args, **_kwargs: 0,
                build_run_observability_fields=lambda *_args, **_kwargs: {},
                error_hint=lambda _err: "",
            )

            self.assertEqual(code, 200)
            row = payload.get("run") or {}
            self.assertEqual(
                row.get("messagePreview"),
                "请诊断当前详情为什么看起来像空白",
            )
            self.assertEqual(
                row.get("partialPreview"),
                "正在比对详情接口与列表摘要的聚合差异",
            )
            self.assertEqual(
                row.get("lastPreview"),
                "正在比对详情接口与列表摘要的聚合差异",
            )

            persisted = store.load_meta(run_id) or {}
            self.assertEqual(
                persisted.get("messagePreview"),
                "请诊断当前详情为什么看起来像空白",
            )
            self.assertEqual(
                persisted.get("partialPreview"),
                "正在比对详情接口与列表摘要的聚合差异",
            )
            self.assertEqual(
                persisted.get("lastPreview"),
                "正在比对详情接口与列表摘要的聚合差异",
            )

    def test_get_run_detail_response_for_claude_prefers_terminal_message_and_clears_legacy_process(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            created = store.create_run(
                project_id="task_dashboard",
                channel_name="子级03-多CLI适配器（codex-claude-opencode）",
                session_id="session-claude",
                message="ping",
                cli_type="claude",
            )
            run_id = str(created.get("id") or "").strip()
            meta = store.load_meta(run_id) or {}
            meta["agentMessagesCount"] = 3
            meta["partialPreview"] = "3. 唯一阻塞: 无"
            meta["processRows"] = [
                {"text": "1. 已完成恢复: 是", "at": "2026-03-20T00:43:32+0800"},
            ]
            store.save_meta(run_id, meta)
            store._paths(run_id)["log"].write_text(
                "\n".join(
                    [
                        "# command header",
                        "[stdout] 1. 已完成恢复: 是",
                        "[stdout] 2. 当前主线: 等待用户指示当前任务",
                        "[stdout] 3. 唯一阻塞: 无",
                    ]
                ),
                encoding="utf-8",
            )

            code, payload = get_run_detail_response(
                run_id=run_id,
                store=store,
                scheduler=None,
                maybe_trigger_restart_recovery_lazy=lambda *_args, **_kwargs: 0,
                maybe_trigger_queued_recovery_lazy=lambda *_args, **_kwargs: 0,
                build_run_observability_fields=lambda *_args, **_kwargs: {},
                error_hint=lambda _err: "",
            )

            self.assertEqual(code, 200)
            self.assertEqual(
                payload.get("lastMessage"),
                "1. 已完成恢复: 是\n2. 当前主线: 等待用户指示当前任务\n3. 唯一阻塞: 无",
            )
            self.assertEqual(payload.get("partialMessage"), "")
            self.assertEqual(payload.get("agentMessages"), [])
            self.assertEqual(payload.get("processRows"), [])
            self.assertEqual((payload.get("run") or {}).get("agentMessagesCount"), 0)
            self.assertEqual((payload.get("run") or {}).get("partialPreview"), "")

            persisted = store.load_meta(run_id) or {}
            self.assertEqual(persisted.get("agentMessagesCount"), 0)
            self.assertEqual(persisted.get("partialPreview"), "")
            self.assertEqual(persisted.get("processRows"), [])
            self.assertEqual(
                persisted.get("lastPreview"),
                "1. 已完成恢复: 是\n2. 当前主线: 等待用户指示当前任务\n3. 唯一阻塞: 无",
            )

    def test_list_runs_response_for_claude_clears_legacy_process_preview(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            created = store.create_run(
                project_id="task_dashboard",
                channel_name="子级03-多CLI适配器（codex-claude-opencode）",
                session_id="session-claude",
                message="ping",
                cli_type="claude",
            )
            run_id = str(created.get("id") or "").strip()
            meta = store.load_meta(run_id) or {}
            meta["status"] = "done"
            meta["agentMessagesCount"] = 2
            meta["partialPreview"] = "最后一条旧过程"
            meta["lastPreview"] = ""
            meta["processRows"] = [{"text": "旧过程", "at": "2026-03-20T00:08:15+0800"}]
            store.save_meta(run_id, meta)
            store._paths(run_id)["log"].write_text(
                "\n".join(
                    [
                        "# command header",
                        "[stdout] Claude 正文第一行",
                        "[stdout] Claude 正文第二行",
                    ]
                ),
                encoding="utf-8",
            )

            code, payload = list_runs_response(
                query_string="limit=1",
                store=store,
                scheduler=None,
                maybe_trigger_restart_recovery_lazy=lambda *_args, **_kwargs: 0,
                maybe_trigger_queued_recovery_lazy=lambda *_args, **_kwargs: 0,
                build_run_observability_fields=lambda *_args, **_kwargs: {},
            )

            self.assertEqual(code, 200)
            row = payload["runs"][0]
            self.assertEqual(row.get("agentMessagesCount"), 0)
            self.assertEqual(row.get("partialPreview"), "")
            self.assertEqual(row.get("processRows"), [])
            self.assertEqual(row.get("lastPreview"), "Claude 正文第一行\nClaude 正文第二行")

            persisted = store.load_meta(run_id) or {}
            self.assertEqual(persisted.get("agentMessagesCount"), 0)
            self.assertEqual(persisted.get("partialPreview"), "")
            self.assertEqual(persisted.get("processRows"), [])
            self.assertEqual(persisted.get("lastPreview"), "Claude 正文第一行\nClaude 正文第二行")

    def test_get_run_detail_response_for_opencode_prefers_terminal_message_and_clears_legacy_process(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            created = store.create_run(
                project_id="task_dashboard",
                channel_name="子级03-多CLI适配器（codex-claude-opencode）",
                session_id="ses_test_opencode",
                message="ping",
                cli_type="opencode",
            )
            run_id = str(created.get("id") or "").strip()
            meta = store.load_meta(run_id) or {}
            meta["agentMessagesCount"] = 3
            meta["partialPreview"] = "最后一条旧过程"
            meta["processRows"] = [
                {"text": "OpenCode 正文第一行", "at": "2026-03-20T17:27:13+0800"},
            ]
            store.save_meta(run_id, meta)
            store._paths(run_id)["log"].write_text(
                "\n".join(
                    [
                        "# command header",
                        "[stderr] tool activity",
                        "[stdout] OpenCode 正文第一行",
                        "[stdout] OpenCode 正文第二行",
                        "[stdout] OpenCode 正文第三行",
                    ]
                ),
                encoding="utf-8",
            )

            code, payload = get_run_detail_response(
                run_id=run_id,
                store=store,
                scheduler=None,
                maybe_trigger_restart_recovery_lazy=lambda *_args, **_kwargs: 0,
                maybe_trigger_queued_recovery_lazy=lambda *_args, **_kwargs: 0,
                build_run_observability_fields=lambda *_args, **_kwargs: {},
                error_hint=lambda _err: "",
            )

            self.assertEqual(code, 200)
            self.assertEqual(
                payload.get("lastMessage"),
                "OpenCode 正文第一行\nOpenCode 正文第二行\nOpenCode 正文第三行",
            )
            self.assertEqual(payload.get("partialMessage"), "")
            self.assertEqual(payload.get("agentMessages"), [])
            self.assertEqual(payload.get("processRows"), [])
            self.assertEqual((payload.get("run") or {}).get("agentMessagesCount"), 0)
            self.assertEqual((payload.get("run") or {}).get("partialPreview"), "")

            persisted = store.load_meta(run_id) or {}
            self.assertEqual(persisted.get("agentMessagesCount"), 0)
            self.assertEqual(persisted.get("partialPreview"), "")
            self.assertEqual(persisted.get("processRows"), [])
            self.assertEqual(
                persisted.get("lastPreview"),
                "OpenCode 正文第一行\nOpenCode 正文第二行\nOpenCode 正文第三行",
            )

    def test_list_runs_response_for_opencode_clears_legacy_process_preview(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            created = store.create_run(
                project_id="task_dashboard",
                channel_name="子级03-多CLI适配器（codex-claude-opencode）",
                session_id="ses_test_opencode",
                message="ping",
                cli_type="opencode",
            )
            run_id = str(created.get("id") or "").strip()
            meta = store.load_meta(run_id) or {}
            meta["status"] = "done"
            meta["agentMessagesCount"] = 2
            meta["partialPreview"] = "最后一条旧过程"
            meta["lastPreview"] = ""
            meta["processRows"] = [{"text": "旧过程", "at": "2026-03-20T00:08:15+0800"}]
            store.save_meta(run_id, meta)
            store._paths(run_id)["log"].write_text(
                "\n".join(
                    [
                        "# command header",
                        "[stdout] OpenCode 正文第一行",
                        "[stdout] OpenCode 正文第二行",
                    ]
                ),
                encoding="utf-8",
            )

            code, payload = list_runs_response(
                query_string="limit=1",
                store=store,
                scheduler=None,
                maybe_trigger_restart_recovery_lazy=lambda *_args, **_kwargs: 0,
                maybe_trigger_queued_recovery_lazy=lambda *_args, **_kwargs: 0,
                build_run_observability_fields=lambda *_args, **_kwargs: {},
            )

            self.assertEqual(code, 200)
            row = payload["runs"][0]
            self.assertEqual(row.get("agentMessagesCount"), 0)
            self.assertEqual(row.get("partialPreview"), "")
            self.assertEqual(row.get("processRows"), [])
            self.assertEqual(row.get("lastPreview"), "OpenCode 正文第一行\nOpenCode 正文第二行")

            persisted = store.load_meta(run_id) or {}
            self.assertEqual(persisted.get("agentMessagesCount"), 0)
            self.assertEqual(persisted.get("partialPreview"), "")
            self.assertEqual(persisted.get("processRows"), [])
            self.assertEqual(persisted.get("lastPreview"), "OpenCode 正文第一行\nOpenCode 正文第二行")


if __name__ == "__main__":
    unittest.main()
