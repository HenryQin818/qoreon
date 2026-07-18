import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import server
from task_dashboard.runtime import run_routes
from task_dashboard.runtime.run_routes import get_run_detail_response, list_runs_response


class TestRunRoutes(unittest.TestCase):
    def setUp(self) -> None:
        run_routes._RUNS_LIST_CACHE.clear()
        run_routes._RUNS_LIST_CACHE_INFLIGHT.clear()
        run_routes._RUNS_LIST_CACHE_INVALIDATED_AT.clear()
        run_routes._RUN_DETAIL_CACHE.clear()

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

    def test_cancel_edit_terminalizes_hidden_queued_run(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            created = store.create_run(
                project_id="task_dashboard",
                channel_name="子级02-CCB运行时（server-并发-安全-启动）",
                session_id="session-1",
                message="撤回这条消息",
            )
            run_id = str(created.get("id") or "").strip()
            audits: list[dict[str, object]] = []

            code, payload = run_routes.perform_run_action_response(
                run_id=run_id,
                body={"action": "cancel_edit"},
                store=store,
                scheduler=None,
                run_process_registry=None,
                audit_action=lambda **kwargs: audits.append(kwargs),
                now_iso=lambda: "2026-06-10T16:37:55+0800",
                require_scheduler_enabled=lambda: False,
                dispatch_terminal_callback_for_run=lambda **_kwargs: None,
            )

            self.assertEqual(code, 200)
            self.assertTrue(payload.get("ok"))
            meta = store.load_meta(run_id) or {}
            self.assertTrue(meta.get("hidden"))
            self.assertEqual(meta.get("cancelAction"), "cancel_edit")
            self.assertEqual(meta.get("cancelledAt"), "2026-06-10T16:37:55+0800")
            self.assertEqual(meta.get("status"), "interrupted")
            self.assertEqual(meta.get("display_state"), "interrupted")
            self.assertEqual(meta.get("outcome_state"), "interrupted_user")
            self.assertEqual(meta.get("failure_class"), "interrupted")
            self.assertEqual(meta.get("error_class"), "user_cancelled")
            self.assertEqual(meta.get("finishedAt"), "2026-06-10T16:37:55+0800")
            self.assertEqual(meta.get("error"), "cancelled by user before start")
            self.assertEqual(meta.get("recovery_required"), False)
            self.assertEqual(meta.get("recovery_mode"), "")
            self.assertTrue(audits)

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

    def test_list_runs_response_light_reuses_response_cache(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            store.create_run(
                project_id="task_dashboard",
                channel_name="子级02-CCB运行时（server-并发-安全-启动）",
                session_id="session-1",
                message="ping",
            )
            calls = {"observability": 0}

            def _fake_build(*_args, **_kwargs):
                calls["observability"] += 1
                return {"display_state": "queued"}

            query = "projectId=task_dashboard&sessionId=session-1&limit=10&payloadMode=light"
            code1, payload1 = list_runs_response(
                query_string=query,
                store=store,
                scheduler=None,
                maybe_trigger_restart_recovery_lazy=lambda *_args, **_kwargs: 0,
                maybe_trigger_queued_recovery_lazy=lambda *_args, **_kwargs: 0,
                build_run_observability_fields=_fake_build,
            )
            code2, payload2 = list_runs_response(
                query_string=query,
                store=store,
                scheduler=None,
                maybe_trigger_restart_recovery_lazy=lambda *_args, **_kwargs: 0,
                maybe_trigger_queued_recovery_lazy=lambda *_args, **_kwargs: 0,
                build_run_observability_fields=_fake_build,
            )

            self.assertEqual(code1, 200)
            self.assertEqual(code2, 200)
            self.assertEqual(calls["observability"], 1)
            self.assertEqual(payload1.get("payloadMode"), "light")
            self.assertEqual(payload2.get("payloadMode"), "light")
            self.assertEqual((payload2.get("runs_read_model") or {}).get("delivery_mode"), "fresh_cache")

    def test_list_runs_response_summary_is_independent_lightweight_mode(self) -> None:
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
            meta["messagePreview"] = "stored message"
            meta["lastPreview"] = "stored last"
            meta["partialPreview"] = "stored partial"
            meta["logPreview"] = "stored log"
            meta["skills_used"] = ["skill-a"]
            meta["business_refs"] = [{"type": "任务", "title": "x"}]
            meta["processRows"] = [{"text": "row"}]
            store.save_meta(run_id, meta)

            calls = {"observability": 0}

            def _fake_build(_store, row, **kwargs):
                calls["observability"] += 1
                self.assertFalse(bool(kwargs.get("include_session_semantics")))
                return {"display_state": str(row.get("status") or "").strip().lower()}

            query = "projectId=task_dashboard&sessionId=session-1&limit=10&payloadMode=summary"
            code1, payload1 = list_runs_response(
                query_string=query,
                store=store,
                scheduler=None,
                maybe_trigger_restart_recovery_lazy=lambda *_args, **_kwargs: 0,
                maybe_trigger_queued_recovery_lazy=lambda *_args, **_kwargs: 0,
                build_run_observability_fields=_fake_build,
            )
            code2, payload2 = list_runs_response(
                query_string=query,
                store=store,
                scheduler=None,
                maybe_trigger_restart_recovery_lazy=lambda *_args, **_kwargs: 0,
                maybe_trigger_queued_recovery_lazy=lambda *_args, **_kwargs: 0,
                build_run_observability_fields=_fake_build,
            )

            self.assertEqual(code1, 200)
            self.assertEqual(code2, 200)
            self.assertEqual(calls["observability"], 1)
            self.assertEqual(payload1.get("payloadMode"), "summary")
            self.assertEqual(payload2.get("payloadMode"), "summary")
            self.assertEqual((payload2.get("runs_read_model") or {}).get("delivery_mode"), "fresh_cache")
            self.assertEqual((payload2.get("runs_read_model") or {}).get("cache_strategy"), "ttl_inflight_stale_fallback")
            row = (payload1.get("runs") or [{}])[0]
            self.assertNotIn("messagePreview", row)
            self.assertNotIn("lastPreview", row)
            self.assertNotIn("partialPreview", row)
            self.assertNotIn("logPreview", row)
            self.assertNotIn("skills_used", row)
            self.assertNotIn("business_refs", row)
            self.assertNotIn("processRows", row)

    def test_list_runs_response_light_cache_invalidated_after_meta_write(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            created = store.create_run(
                project_id="task_dashboard",
                channel_name="子级02-CCB运行时（server-并发-安全-启动）",
                session_id="session-1",
                message="ping",
            )
            run_id = str(created.get("id") or "").strip()
            query = "projectId=task_dashboard&sessionId=session-1&limit=10&payloadMode=light"
            _code1, payload1 = list_runs_response(
                query_string=query,
                store=store,
                scheduler=None,
                maybe_trigger_restart_recovery_lazy=lambda *_args, **_kwargs: 0,
                maybe_trigger_queued_recovery_lazy=lambda *_args, **_kwargs: 0,
                build_run_observability_fields=lambda *_args, **_kwargs: {},
            )
            self.assertEqual(str((payload1.get("runs") or [{}])[0].get("status") or ""), "queued")

            meta = store.load_meta(run_id) or {}
            meta["status"] = "done"
            meta["finishedAt"] = "2026-04-30T12:00:00+0800"
            store.save_meta(run_id, meta)

            _code2, payload2 = list_runs_response(
                query_string=query,
                store=store,
                scheduler=None,
                maybe_trigger_restart_recovery_lazy=lambda *_args, **_kwargs: 0,
                maybe_trigger_queued_recovery_lazy=lambda *_args, **_kwargs: 0,
                build_run_observability_fields=lambda *_args, **_kwargs: {},
            )
            self.assertEqual(str((payload2.get("runs") or [{}])[0].get("status") or ""), "done")
            self.assertEqual((payload2.get("runs_read_model") or {}).get("delivery_mode"), "fresh_build")

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

    def test_get_run_detail_response_compacts_large_process_payload_for_display(self) -> None:
        with tempfile.TemporaryDirectory() as td, mock.patch.dict(
            "os.environ",
            {
                "CCB_RUN_DETAIL_PROCESS_ITEM_LIMIT": "20",
                "CCB_RUN_DETAIL_PROCESS_TEXT_LIMIT": "240",
                "CCB_RUN_DETAIL_LOG_TAIL_LIMIT": "4000",
            },
            clear=False,
        ):
            store = server.RunStore(Path(td))
            created = store.create_run(
                project_id="task_dashboard",
                channel_name="辅助06-项目运维（运行巡检-异常告警-会话修复）",
                session_id="session-1",
                message="ping",
            )
            run_id = str(created.get("id") or "").strip()
            long_text = "x" * 800
            long_output = "y" * 900
            process_rows = [
                *[
                    {"text": f"旧过程 {idx}", "at": "2026-07-01T17:00:00+0800"}
                    for idx in range(19)
                ],
                {
                    "text": long_text,
                    "item": {
                        "type": "command_execution",
                        "aggregated_output": long_output,
                    },
                    "at": "2026-07-01T17:01:00+0800",
                },
                {"text": "最后过程", "at": "2026-07-01T17:02:00+0800"},
            ]
            meta = store.load_meta(run_id) or {}
            meta["status"] = "done"
            meta["processRows"] = process_rows
            meta["process_events"] = process_rows
            meta["processEvents"] = process_rows
            store.save_meta(run_id, meta)
            store._paths(run_id)["log"].write_text("LOGSTART\n" + ("z" * 6000) + "\nLOGEND", encoding="utf-8")

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
            self.assertEqual(payload.get("processRowsTotal"), 21)
            self.assertEqual(payload.get("processRowsReturned"), 20)
            self.assertTrue(payload.get("processRowsTruncated"))
            self.assertEqual(payload.get("processEventsTotal"), 21)
            self.assertEqual(payload.get("processEventsReturned"), 20)
            self.assertTrue(payload.get("processEventsTruncated"))
            self.assertEqual(payload.get("logTailChars"), 6016)
            self.assertEqual(payload.get("logTailReturnedChars"), 4000)
            self.assertTrue(payload.get("logTailTruncated"))
            self.assertLessEqual(len(payload.get("logTail") or ""), 4000)
            self.assertEqual(payload.get("logTail"), payload.get("process"))
            self.assertTrue(str(payload.get("logTail") or "").endswith("LOGEND"))

            compact_rows = payload.get("processRows") or []
            self.assertEqual(len(compact_rows), 20)
            self.assertEqual(compact_rows[0]["text"], "旧过程 1")
            self.assertNotEqual(compact_rows[-2]["text"], long_text)
            self.assertLessEqual(len(compact_rows[-2]["text"]), 240)
            self.assertLessEqual(len(compact_rows[-2]["item"]["aggregated_output"]), 240)
            self.assertEqual(compact_rows[-1]["text"], "最后过程")

            detail_run = payload.get("run") or {}
            self.assertTrue(detail_run.get("processRowsTruncated"))
            self.assertEqual(len(detail_run.get("processRows") or []), 20)
            self.assertLessEqual(
                len((detail_run.get("processEvents") or [])[-2]["item"]["aggregated_output"]),
                240,
            )

            persisted = store.load_meta(run_id) or {}
            self.assertEqual(persisted.get("processRows"), process_rows)
            self.assertEqual(len(persisted["processRows"][-2]["text"]), 800)
            self.assertEqual(len(persisted["processRows"][-2]["item"]["aggregated_output"]), 900)

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

    def test_get_run_detail_response_for_claude_prefers_terminal_message_and_preserves_process(self) -> None:
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
            self.assertEqual(
                payload.get("processRows"),
                [{"text": "1. 已完成恢复: 是", "at": "2026-03-20T00:43:32+0800"}],
            )
            self.assertEqual(
                payload.get("processEvents"),
                [{"text": "1. 已完成恢复: 是", "at": "2026-03-20T00:43:32+0800"}],
            )
            self.assertEqual((payload.get("run") or {}).get("agentMessagesCount"), 0)

            persisted = store.load_meta(run_id) or {}
            self.assertEqual(persisted.get("agentMessagesCount"), 0)
            self.assertEqual(
                persisted.get("processRows"),
                [{"text": "1. 已完成恢复: 是", "at": "2026-03-20T00:43:32+0800"}],
            )
            self.assertEqual(
                persisted.get("lastPreview"),
                "1. 已完成恢复: 是\n2. 当前主线: 等待用户指示当前任务\n3. 唯一阻塞: 无",
            )

    def test_get_run_detail_response_for_claude_recovers_process_events_from_log(self) -> None:
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
            meta["partialPreview"] = "旧终端过程"
            store.save_meta(run_id, meta)
            started = {
                "type": "tool_call.started",
                "event_type": "tool_started",
                "item_type": "function_call",
                "title": "Read",
                "text": "调用工具: Read task_dashboard/runtime/run_routes.py",
                "source": "claude",
                "raw_ref": "call_claude_001",
                "call_id": "call_claude_001",
            }
            completed = {
                "type": "tool_call.completed",
                "event_type": "tool_completed",
                "item_type": "function_call_result",
                "title": "Read",
                "text": "工具完成: Read 读取完成",
                "source": "claude",
                "raw_ref": "call_claude_001",
                "call_id": "call_claude_001",
            }
            store._paths(run_id)["log"].write_text(
                "\n".join(
                    [
                        "# command header",
                        f"[stdout] {json.dumps(started, ensure_ascii=False)}",
                        "[stdout] Claude 正文",
                        f"[stdout] {json.dumps(completed, ensure_ascii=False)}",
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

            expected_events = [
                {
                    "event_type": "tool_started",
                    "item_type": "function_call",
                    "title": "Read",
                    "text": "调用工具: Read task_dashboard/runtime/run_routes.py",
                    "source": "claude",
                    "raw_ref": "call_claude_001",
                    "call_id": "call_claude_001",
                },
                {
                    "event_type": "tool_completed",
                    "item_type": "function_call_result",
                    "title": "Read",
                    "text": "工具完成: Read 读取完成",
                    "source": "claude",
                    "raw_ref": "call_claude_001",
                    "call_id": "call_claude_001",
                },
            ]
            self.assertEqual(code, 200)
            self.assertEqual(payload.get("lastMessage"), "Claude 正文")
            self.assertEqual(payload.get("agentMessages"), [])
            self.assertEqual(payload.get("processRows"), expected_events)
            self.assertEqual(payload.get("processEvents"), expected_events)

            persisted = store.load_meta(run_id) or {}
            self.assertEqual(persisted.get("processRows"), expected_events)
            self.assertEqual(persisted.get("process_events"), expected_events)
            self.assertEqual(persisted.get("processEvents"), expected_events)
            self.assertEqual(persisted.get("agentMessagesCount"), 0)

    def test_get_run_detail_response_for_claude_syncs_process_events_aliases(self) -> None:
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
            process_events = [
                {
                    "event_type": "tool_started",
                    "item_type": "function_call",
                    "title": "Read",
                    "text": "调用工具: Read task_dashboard/runtime/run_routes.py",
                    "source": "claude",
                    "raw_ref": "call_claude_001",
                    "call_id": "call_claude_001",
                    "reasoning": "hidden",
                    "rawContent": "hidden",
                },
                {
                    "event_type": "tool_completed",
                    "item_type": "function_call_result",
                    "title": "Read",
                    "text": "工具完成: Read 读取完成",
                    "source": "claude",
                    "raw_ref": "call_claude_001",
                    "call_id": "call_claude_001",
                },
                {
                    "event_type": "tool_started",
                    "item_type": "function_call",
                    "title": "AskUserQuestion",
                    "text": (
                        '调用工具: AskUserQuestion {"questions":[{"question":"第一条完整问题正文不应出现在过程轨"},'
                        '{"question":"第二条完整问题正文不应出现在过程轨"}],"prompt":"完整 prompt 不应出现在过程轨"}'
                    ),
                    "source": "claude",
                    "raw_ref": "call_claude_ask",
                    "call_id": "call_claude_ask",
                },
            ]
            meta = store.load_meta(run_id) or {}
            meta["status"] = "done"
            meta["processRows"] = []
            meta["process_events"] = []
            meta["processEvents"] = process_events
            store.save_meta(run_id, meta)
            store._paths(run_id)["log"].write_text("[stdout] Claude 正文\n", encoding="utf-8")

            code, payload = get_run_detail_response(
                run_id=run_id,
                store=store,
                scheduler=None,
                maybe_trigger_restart_recovery_lazy=lambda *_args, **_kwargs: 0,
                maybe_trigger_queued_recovery_lazy=lambda *_args, **_kwargs: 0,
                build_run_observability_fields=lambda *_args, **_kwargs: {},
                error_hint=lambda _err: "",
            )

            expected_events = [
                {key: value for key, value in process_events[0].items() if key not in {"reasoning", "rawContent"}},
                dict(process_events[1]),
                {
                    "text": "调用工具: AskUserQuestion 向用户提问 / 问题 2 项",
                    "event_type": "tool_started",
                    "item_type": "function_call",
                    "title": "AskUserQuestion",
                    "source": "claude",
                    "raw_ref": "call_claude_ask",
                    "call_id": "call_claude_ask",
                },
            ]
            self.assertEqual(code, 200)
            self.assertEqual(payload.get("processRows"), expected_events)
            self.assertEqual(payload.get("processEvents"), expected_events)

            persisted = store.load_meta(run_id) or {}
            self.assertEqual(persisted.get("processRows"), expected_events)
            self.assertEqual(persisted.get("process_events"), expected_events)
            self.assertEqual(persisted.get("processEvents"), expected_events)
            process_blob = json.dumps(
                {
                    "processRows": persisted.get("processRows"),
                    "process_events": persisted.get("process_events"),
                    "processEvents": persisted.get("processEvents"),
                },
                ensure_ascii=False,
            )
            self.assertNotIn('{"questions"', process_blob)
            self.assertNotIn("完整 prompt", process_blob)
            self.assertNotIn("完整问题正文", process_blob)
            self.assertNotIn("rawContent", process_blob)
            self.assertNotIn('"reasoning"', process_blob)

    def test_get_run_detail_response_caches_terminal_payload_when_files_unchanged(self) -> None:
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
            meta["status"] = "done"
            meta["finishedAt"] = "2026-05-03T11:20:00+0800"
            store.save_meta(run_id, meta)
            store._paths(run_id)["last"].write_text("已完成", encoding="utf-8")
            store._paths(run_id)["log"].write_text("[assistant] 已完成\n", encoding="utf-8")

            code, first = get_run_detail_response(
                run_id=run_id,
                store=store,
                scheduler=None,
                maybe_trigger_restart_recovery_lazy=lambda *_args, **_kwargs: 0,
                maybe_trigger_queued_recovery_lazy=lambda *_args, **_kwargs: 0,
                build_run_observability_fields=lambda *_args, **_kwargs: {},
                error_hint=lambda _err: "",
            )

            self.assertEqual(code, 200)
            self.assertEqual(first.get("lastMessage"), "已完成")

            with (
                mock.patch.object(store, "read_msg", side_effect=AssertionError("terminal detail should be cached")),
                mock.patch.object(store, "read_last", side_effect=AssertionError("terminal detail should be cached")),
                mock.patch.object(store, "read_log", side_effect=AssertionError("terminal detail should be cached")),
            ):
                code, second = get_run_detail_response(
                    run_id=run_id,
                    store=store,
                    scheduler=None,
                    maybe_trigger_restart_recovery_lazy=lambda *_args, **_kwargs: 0,
                    maybe_trigger_queued_recovery_lazy=lambda *_args, **_kwargs: 0,
                    build_run_observability_fields=lambda *_args, **_kwargs: {},
                    error_hint=lambda _err: "",
                )

            self.assertEqual(code, 200)
            self.assertEqual(second.get("lastMessage"), "已完成")

    def test_list_runs_response_for_claude_preserves_process_preview(self) -> None:
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
            self.assertEqual(row.get("processRows"), [{"text": "旧过程", "at": "2026-03-20T00:08:15+0800"}])
            self.assertEqual(row.get("lastPreview"), "Claude 正文第一行\nClaude 正文第二行")

            persisted = store.load_meta(run_id) or {}
            self.assertEqual(persisted.get("agentMessagesCount"), 0)
            self.assertEqual(persisted.get("partialPreview"), "")
            self.assertEqual(persisted.get("processRows"), [{"text": "旧过程", "at": "2026-03-20T00:08:15+0800"}])
            self.assertEqual(persisted.get("lastPreview"), "Claude 正文第一行\nClaude 正文第二行")

    def test_list_runs_response_for_claude_syncs_process_event_aliases(self) -> None:
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
            process_events = [
                {
                    "event_type": "tool_started",
                    "item_type": "function_call",
                    "title": "Read",
                    "text": "调用工具: Read task_dashboard/runtime/run_routes.py",
                    "source": "claude",
                    "raw_ref": "call_claude_001",
                    "call_id": "call_claude_001",
                    "rawContent": "hidden",
                },
                {
                    "event_type": "tool_started",
                    "item_type": "function_call",
                    "title": "AskUserQuestion",
                    "text": (
                        '调用工具: AskUserQuestion {"questions":[{"question":"第一条完整问题正文不应出现在过程轨"}],'
                        '"prompt":"完整 prompt 不应出现在过程轨"}'
                    ),
                    "source": "claude",
                    "raw_ref": "call_claude_ask",
                    "call_id": "call_claude_ask",
                },
            ]
            meta = store.load_meta(run_id) or {}
            meta["status"] = "done"
            meta["processRows"] = []
            meta["process_events"] = []
            meta["processEvents"] = process_events
            store.save_meta(run_id, meta)

            code, payload = list_runs_response(
                query_string="limit=1",
                store=store,
                scheduler=None,
                maybe_trigger_restart_recovery_lazy=lambda *_args, **_kwargs: 0,
                maybe_trigger_queued_recovery_lazy=lambda *_args, **_kwargs: 0,
                build_run_observability_fields=lambda *_args, **_kwargs: {},
            )

            expected_events = [
                {key: value for key, value in process_events[0].items() if key != "rawContent"},
                {
                    "text": "调用工具: AskUserQuestion 向用户提问 / 问题 1 项",
                    "event_type": "tool_started",
                    "item_type": "function_call",
                    "title": "AskUserQuestion",
                    "source": "claude",
                    "raw_ref": "call_claude_ask",
                    "call_id": "call_claude_ask",
                },
            ]
            self.assertEqual(code, 200)
            row = payload["runs"][0]
            self.assertEqual(row.get("processRows"), expected_events)
            self.assertEqual(row.get("process_events"), expected_events)
            self.assertEqual(row.get("processEvents"), expected_events)

            persisted = store.load_meta(run_id) or {}
            self.assertEqual(persisted.get("processRows"), expected_events)
            self.assertEqual(persisted.get("process_events"), expected_events)
            self.assertEqual(persisted.get("processEvents"), expected_events)
            persisted_blob = json.dumps(persisted, ensure_ascii=False)
            self.assertNotIn("rawContent", persisted_blob)
            self.assertNotIn('{"questions"', persisted_blob)
            self.assertNotIn("完整 prompt", persisted_blob)
            self.assertNotIn("完整问题正文", persisted_blob)

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

    def test_get_run_detail_response_for_gemini_extracts_pretty_json_response(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            created = store.create_run(
                project_id="task_dashboard",
                channel_name="子级03-多CLI适配器（codex-claude-opencode）",
                session_id="b4136799-1826-40b6-8e0e-27500175c542",
                message="ping",
                cli_type="gemini",
            )
            run_id = str(created.get("id") or "").strip()
            meta = store.load_meta(run_id) or {}
            meta["agentMessagesCount"] = 161
            meta["partialPreview"] = "}"
            meta["processRows"] = [
                {"text": "{", "at": "2026-05-20T09:18:43+0800"},
                {"text": '"response": "旧片段",', "at": "2026-05-20T09:18:43+0800"},
                {"text": "}", "at": "2026-05-20T09:18:43+0800"},
            ]
            store.save_meta(run_id, meta)
            store._paths(run_id)["log"].write_text(
                "\n".join(
                    [
                        "# command header",
                        "[stderr] Loaded cached credentials.",
                        "[stdout] {",
                        '[stdout]   "session_id": "b4136799-1826-40b6-8e0e-27500175c542",',
                        '[stdout]   "response": "已完成初始化\\n当前职责边界: 总控分工",',
                        '[stdout]   "stats": {"tokens": {"total": 120}}',
                        "[stdout] }",
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
            self.assertEqual(payload.get("lastMessage"), "已完成初始化\n当前职责边界: 总控分工")
            self.assertEqual(payload.get("partialMessage"), "")
            self.assertEqual(payload.get("agentMessages"), [])
            self.assertEqual(payload.get("processRows"), [])
            self.assertEqual((payload.get("run") or {}).get("agentMessagesCount"), 0)
            self.assertEqual((payload.get("run") or {}).get("partialPreview"), "")

            persisted = store.load_meta(run_id) or {}
            self.assertEqual(persisted.get("agentMessagesCount"), 0)
            self.assertEqual(persisted.get("partialPreview"), "")
            self.assertEqual(persisted.get("processRows"), [])
            self.assertEqual(persisted.get("lastPreview"), "已完成初始化\n当前职责边界: 总控分工")

    def test_list_runs_response_for_gemini_clears_json_fragment_process_preview(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            created = store.create_run(
                project_id="task_dashboard",
                channel_name="子级03-多CLI适配器（codex-claude-opencode）",
                session_id="b4136799-1826-40b6-8e0e-27500175c542",
                message="ping",
                cli_type="gemini",
            )
            run_id = str(created.get("id") or "").strip()
            meta = store.load_meta(run_id) or {}
            meta["status"] = "done"
            meta["agentMessagesCount"] = 161
            meta["partialPreview"] = "}"
            meta["lastPreview"] = ""
            meta["processRows"] = [{"text": "}", "at": "2026-05-20T09:18:43+0800"}]
            store.save_meta(run_id, meta)
            store._paths(run_id)["log"].write_text(
                "\n".join(
                    [
                        "# command header",
                        "[stdout] {",
                        '[stdout]   "response": "Gemini 正文第一行\\nGemini 正文第二行",',
                        '[stdout]   "stats": {"tokens": {"total": 120}}',
                        "[stdout] }",
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
            self.assertEqual(row.get("lastPreview"), "Gemini 正文第一行\nGemini 正文第二行")

            persisted = store.load_meta(run_id) or {}
            self.assertEqual(persisted.get("agentMessagesCount"), 0)
            self.assertEqual(persisted.get("partialPreview"), "")
            self.assertEqual(persisted.get("processRows"), [])
            self.assertEqual(persisted.get("lastPreview"), "Gemini 正文第一行\nGemini 正文第二行")

    def test_get_run_detail_response_for_codebuddy_preserves_normalized_process_fields(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            created = store.create_run(
                project_id="task_dashboard",
                channel_name="子级03-多CLI适配器（codex-claude-opencode）",
                session_id="codebuddy-session-001",
                message="ping",
                cli_type="codebuddy",
            )
            run_id = str(created.get("id") or "").strip()
            process_rows = [
                {
                    "event_type": "command_started",
                    "item_type": "command_execution",
                    "title": "rg processRows",
                    "text": "执行命令: rg processRows",
                    "at": "2026-06-08T10:00:00+0800",
                    "source": "codebuddy",
                },
            ]
            process_events = [
                {
                    "event_type": "command_started",
                    "item_type": "command_execution",
                    "title": "rg processRows",
                    "text": "执行命令: rg processRows",
                    "at": "2026-06-08T10:00:00+0800",
                    "source": "codebuddy",
                },
            ]
            meta = store.load_meta(run_id) or {}
            meta["agentMessagesCount"] = 3
            meta["partialPreview"] = "旧终端过程"
            meta["processRows"] = process_rows
            meta["process_events"] = process_events
            store.save_meta(run_id, meta)
            store._paths(run_id)["log"].write_text(
                "\n".join(
                    [
                        "# command header",
                        "[stdout] CodeBuddy 正文第一行",
                        "[stdout] CodeBuddy 正文第二行",
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
            self.assertEqual(payload.get("lastMessage"), "CodeBuddy 正文第一行\nCodeBuddy 正文第二行")
            self.assertEqual(payload.get("agentMessages"), [])
            self.assertEqual(payload.get("processRows"), process_rows)
            self.assertEqual(payload.get("processEvents"), process_events)
            self.assertEqual((payload.get("run") or {}).get("agentMessagesCount"), 0)

            persisted = store.load_meta(run_id) or {}
            self.assertEqual(persisted.get("processRows"), process_rows)
            self.assertEqual(persisted.get("process_events"), process_events)
            self.assertEqual(persisted.get("lastPreview"), "CodeBuddy 正文第一行\nCodeBuddy 正文第二行")

    def test_get_run_detail_response_for_codebuddy_recovers_process_events_from_log(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            created = store.create_run(
                project_id="task_dashboard",
                channel_name="子级03-多CLI适配器（codex-claude-opencode）",
                session_id="codebuddy-session-002",
                message="ping",
                cli_type="codebuddy",
            )
            run_id = str(created.get("id") or "").strip()
            meta = store.load_meta(run_id) or {}
            meta["status"] = "done"
            meta["agentMessagesCount"] = 2
            meta["partialPreview"] = "旧终端过程"
            store.save_meta(run_id, meta)
            started = {
                "type": "tool_call.started",
                "event_type": "tool_started",
                "item_type": "function_call",
                "title": "Bash",
                "text": "调用工具: Bash ls -la",
                "source": "codebuddy",
                "raw_ref": "call_001",
                "call_id": "call_001",
            }
            completed = {
                "type": "tool_call.completed",
                "event_type": "tool_completed",
                "item_type": "function_call_result",
                "title": "Bash",
                "text": "工具完成: Bash exitCode:0",
                "source": "codebuddy",
                "raw_ref": "call_001",
                "call_id": "call_001",
            }
            store._paths(run_id)["log"].write_text(
                "\n".join(
                    [
                        "# command header",
                        f"[stdout] {json.dumps(started, ensure_ascii=False)}",
                        "[stdout] CodeBuddy 正文",
                        f"[stdout] {json.dumps(completed, ensure_ascii=False)}",
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

            expected_events = [
                {
                    "event_type": "tool_started",
                    "item_type": "function_call",
                    "title": "Bash",
                    "text": "调用工具: Bash ls -la",
                    "source": "codebuddy",
                    "raw_ref": "call_001",
                    "call_id": "call_001",
                },
                {
                    "event_type": "tool_completed",
                    "item_type": "function_call_result",
                    "title": "Bash",
                    "text": "工具完成: Bash exitCode:0",
                    "source": "codebuddy",
                    "raw_ref": "call_001",
                    "call_id": "call_001",
                },
            ]
            self.assertEqual(code, 200)
            self.assertEqual(payload.get("lastMessage"), "CodeBuddy 正文")
            self.assertEqual(payload.get("agentMessages"), [])
            self.assertEqual(payload.get("processRows"), expected_events)
            self.assertEqual(payload.get("processEvents"), expected_events)

            persisted = store.load_meta(run_id) or {}
            self.assertEqual(persisted.get("processRows"), expected_events)
            self.assertEqual(persisted.get("process_events"), expected_events)
            self.assertEqual(persisted.get("processEvents"), expected_events)
            self.assertEqual(persisted.get("agentMessagesCount"), 0)

    def test_list_runs_response_for_codebuddy_preserves_process_rows(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            created = store.create_run(
                project_id="task_dashboard",
                channel_name="子级03-多CLI适配器（codex-claude-opencode）",
                session_id="codebuddy-session-001",
                message="ping",
                cli_type="codebuddy",
            )
            run_id = str(created.get("id") or "").strip()
            process_rows = [
                {
                    "event_type": "tool_started",
                    "item_type": "tool_call",
                    "title": "read_file",
                    "text": "调用工具: read_file",
                    "at": "2026-06-08T10:00:00+0800",
                    "source": "codebuddy",
                },
            ]
            meta = store.load_meta(run_id) or {}
            meta["status"] = "done"
            meta["agentMessagesCount"] = 2
            meta["partialPreview"] = "旧终端过程"
            meta["lastPreview"] = ""
            meta["processRows"] = process_rows
            store.save_meta(run_id, meta)
            store._paths(run_id)["log"].write_text(
                "\n".join(
                    [
                        "# command header",
                        "[stdout] CodeBuddy 正文第一行",
                        "[stdout] CodeBuddy 正文第二行",
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
            self.assertEqual(row.get("processRows"), process_rows)
            self.assertEqual(row.get("lastPreview"), "CodeBuddy 正文第一行\nCodeBuddy 正文第二行")

            persisted = store.load_meta(run_id) or {}
            self.assertEqual(persisted.get("agentMessagesCount"), 0)
            self.assertEqual(persisted.get("partialPreview"), "")
            self.assertEqual(persisted.get("processRows"), process_rows)
            self.assertEqual(persisted.get("lastPreview"), "CodeBuddy 正文第一行\nCodeBuddy 正文第二行")

    def test_list_runs_response_includes_codex_generated_image_monitoring_fields(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            store = server.RunStore(root / ".runtime" / "stable" / ".runs")
            project_id = "task_dashboard"
            channel_name = "主体03-视觉主题与展示规范"
            session_id = "019d86a8-d013-73b0-934a-a792cea97041"

            run = store.create_run(
                project_id=project_id,
                channel_name=channel_name,
                session_id=session_id,
                message="请生成一张首页视觉图",
                cli_type="codex",
            )
            meta = store.load_meta(run["id"]) or {}
            meta["status"] = "done"
            meta["createdAt"] = "2026-04-23T23:32:26+08:00"
            meta["startedAt"] = "2026-04-23T23:32:27+08:00"
            meta["finishedAt"] = "2026-04-23T23:32:45+08:00"
            meta["lastPreview"] = "使用 `imagegen` 技能，直接生成首页第一屏视觉稿。"
            meta["skills_used"] = ["imagegen"]
            meta["generated_media_summary"] = "已生成1张图片"
            meta["generated_media_kind"] = "image"
            meta["generated_media_count"] = 1
            meta["attachments"] = [
                {
                    "filename": "ig_demo.png",
                    "originalName": "ig_demo.png",
                    "url": f"/.runs/{run['id']}/attachments/ig_demo.png",
                    "generatedBy": "codex_imagegen",
                    "attachment_role": "assistant",
                }
            ]
            store.save_meta(run["id"], meta)

            code, payload = list_runs_response(
                query_string=f"projectId={project_id}&limit=10&payloadMode=light",
                store=store,
                scheduler=None,
                maybe_trigger_restart_recovery_lazy=lambda *_args, **_kwargs: 0,
                maybe_trigger_queued_recovery_lazy=lambda *_args, **_kwargs: 0,
                build_run_observability_fields=server._build_run_observability_fields,
            )

            self.assertEqual(code, 200)
            rows = payload.get("runs") or []
            self.assertEqual(len(rows), 1)
            row = rows[0]
            self.assertEqual(row.get("generated_media_summary"), "已生成1张图片")
            self.assertEqual(row.get("generated_media_kind"), "image")
            self.assertEqual(row.get("generated_media_count"), 1)
            self.assertTrue(row.get("media_run_candidate"))
            self.assertFalse(row.get("media_result_pending"))
            self.assertEqual(row.get("media_monitor_status"), "generated_media_ready")
            self.assertEqual(row.get("media_false_stop_exempt_reason"), "generated_media_result_present")
            attachments = row.get("attachments") or []
            self.assertEqual(len(attachments), 1)
            self.assertEqual(attachments[0].get("generatedBy"), "codex_imagegen")
            self.assertEqual(attachments[0].get("attachment_role"), "assistant")


if __name__ == "__main__":
    unittest.main()
