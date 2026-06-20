import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

import server
from task_dashboard.runtime import callback_runtime as callback_runtime_module
from task_dashboard.task_identity import record_task_move, render_task_front_matter


class _NoopTimer:
    def __init__(self, _delay, fn, args=None, kwargs=None):
        self.fn = fn
        self.args = tuple(args or ())
        self.kwargs = dict(kwargs or {})
        self.daemon = True
        self.started = False

    def start(self):
        self.started = True

    def cancel(self):
        return None


class CallbackFeedbackTests(unittest.TestCase):
    def setUp(self) -> None:
        with server._CALLBACK_WINDOW_LOCK:
            server._CALLBACK_WINDOWS.clear()

    def tearDown(self) -> None:
        with server._CALLBACK_WINDOW_LOCK:
            server._CALLBACK_WINDOWS.clear()

    def test_explicit_callback_to_done_dispatches_system_callback(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            session_store = server.SessionStore(Path(td))
            session_store.create_session(
                "task_dashboard",
                "主体-总控（合并与验收）",
                cli_type="claude",
                session_id="22222222-2222-2222-2222-222222222222",
            )
            source = store.create_run(
                "task_dashboard",
                "子级05-任务巡检与留痕（自动化）",
                "11111111-1111-1111-1111-111111111111",
                "执行任务",
                sender_type="agent",
                sender_id="主体-总控（合并与验收）",
                sender_name="主体-总控（合并与验收）",
                extra_meta={
                    "callback_to": {
                        "channel_name": "主体-总控（合并与验收）",
                        "session_id": "22222222-2222-2222-2222-222222222222",
                    },
                    "task_path": "任务规划/子级05/任务/xx.md",
                    "execution_mode": "supervised",
                    "trigger_type": "manual_dispatch",
                },
            )
            meta = store.load_meta(source["id"]) or {}
            meta["status"] = "done"
            meta["finishedAt"] = server._now_iso()
            meta["lastPreview"] = "执行完成"
            store.save_meta(source["id"], meta)

            enq = []
            with mock.patch("server._enqueue_run_execution", side_effect=lambda *args, **kwargs: enq.append(args)):
                cb_run_id = server._dispatch_terminal_callback_for_run(store, source["id"], meta=meta)

            self.assertTrue(cb_run_id)
            self.assertEqual(len(enq), 1)
            cb_meta = store.load_meta(cb_run_id) or {}
            self.assertEqual(cb_meta.get("sender_type"), "system")
            self.assertEqual(cb_meta.get("trigger_type"), "callback_auto")
            self.assertEqual(cb_meta.get("event_type"), "done")
            self.assertEqual(cb_meta.get("cliType"), "claude")
            self.assertEqual(cb_meta.get("source_run_id"), source["id"])

    def test_terminal_callback_source_marker_kept_across_cli_types(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            session_store = server.SessionStore(Path(td))
            source_channel = "子级03-多CLI适配器（codex-claude-opencode）"
            target_channel = "主体-总控（合并与验收）"

            for idx, cli in enumerate(("codex", "claude", "opencode"), start=1):
                target_session_id = f"22222222-2222-2222-2222-22222222222{idx}"
                session_store.create_session(
                    "task_dashboard",
                    target_channel,
                    cli_type=cli,
                    session_id=target_session_id,
                )

                source = store.create_run(
                    "task_dashboard",
                    source_channel,
                    "11111111-1111-1111-1111-111111111111",
                    f"{cli} 回执",
                    sender_type="agent",
                    sender_id=target_channel,
                    sender_name=target_channel,
                    extra_meta={
                        "callback_to": {
                            "channel_name": target_channel,
                            "session_id": target_session_id,
                        },
                        "task_path": f"任务规划/子级03/任务/{cli}.md",
                    },
                    cli_type=cli,
                )
                meta = store.load_meta(source["id"]) or {}
                meta["status"] = "done"
                meta["finishedAt"] = server._now_iso()
                meta["lastPreview"] = "已完成"
                store.save_meta(source["id"], meta)

                with mock.patch("server._enqueue_run_execution"):
                    cb_run_id = server._dispatch_terminal_callback_for_run(store, source["id"], meta=meta)

                self.assertTrue(cb_run_id)
                msg = store.read_msg(cb_run_id, limit_chars=120000)
                self.assertIn(f"[来源通道: {source_channel}]", msg)
                cb_meta = store.load_meta(cb_run_id) or {}
                self.assertEqual(str(cb_meta.get("cliType") or ""), cli)

    def test_terminal_callback_source_marker_falls_back_to_channel_name_field(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            target = {
                "channel_name": "主体-总控（合并与验收）",
                "session_id": "23232323-2323-2323-2323-232323232323",
            }
            session_store = server.SessionStore(Path(td))
            session_store.create_session(
                "task_dashboard",
                target["channel_name"],
                cli_type="codex",
                session_id=target["session_id"],
            )

            source = store.create_run(
                "task_dashboard",
                "子级02-CCB运行时（server-并发-安全-启动）",
                "12121212-1212-1212-1212-121212121212",
                "source fallback",
                sender_type="agent",
                sender_id=target["channel_name"],
                sender_name=target["channel_name"],
                extra_meta={
                    "callback_to": target,
                    "task_path": "任务规划/子级02/任务/fallback.md",
                },
            )
            meta = store.load_meta(source["id"]) or {}
            meta["status"] = "done"
            meta["finishedAt"] = server._now_iso()
            meta["lastPreview"] = "执行完成"
            # Simulate legacy/variant payload: missing channelName but has channel_name.
            meta.pop("channelName", None)
            meta["channel_name"] = "子级02-CCB运行时（server-并发-安全-启动）"
            store.save_meta(source["id"], meta)

            with mock.patch("server._enqueue_run_execution"):
                cb_run_id = server._dispatch_terminal_callback_for_run(store, source["id"], meta=meta)

            self.assertTrue(cb_run_id)
            msg = store.read_msg(cb_run_id, limit_chars=120000)
            self.assertIn("[来源通道: 子级02-CCB运行时（server-并发-安全-启动）]", msg)
            cb_meta = store.load_meta(cb_run_id) or {}
            rr = cb_meta.get("route_resolution") or {}
            self.assertEqual(rr.get("source"), "callback_to")
            summary = cb_meta.get("receipt_summary") or {}
            self.assertEqual(summary.get("message_kind"), "system_callback")
            self.assertFalse(bool(summary.get("late_callback")))
            self.assertEqual((summary.get("technical") or {}).get("source_run_id"), source["id"])
            src_after = store.load_meta(source["id"]) or {}
            dispatches = src_after.get("callback_dispatches") or []
            self.assertEqual(len(dispatches), 1)
            self.assertEqual(dispatches[0].get("status"), "sent")

    def test_terminal_callback_success_records_communication_view(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            source = store.create_run(
                "task_dashboard",
                "子级02-CCB运行时（server-并发-安全-启动）",
                "22222222-2222-2222-2222-222222222222",
                "执行完成",
                sender_type="agent",
                sender_id="主体-总控（合并与验收）",
                sender_name="主体-总控（合并与验收）",
                extra_meta={
                    "callback_to": {
                        "channel_name": "主体-总控（合并与验收）",
                        "session_id": "22222222-2222-2222-2222-222222222222",
                    },
                    "source_ref": {
                        "project_id": "task_dashboard",
                        "channel_name": "子级02-CCB运行时（server-并发-安全-启动）",
                        "session_id": "22222222-2222-2222-2222-222222222222",
                        "run_id": "source-run-demo",
                    },
                    "execution_mode": "managed",
                    "task_path": "任务规划/子级02-CCB运行时（server-并发-安全-启动）/任务/xx.md",
                },
            )
            meta = store.load_meta(source["id"]) or {}
            meta["status"] = "done"
            meta["finishedAt"] = server._now_iso()
            meta["lastPreview"] = "执行完成"
            store.save_meta(source["id"], meta)

            enq = []
            with mock.patch("server._enqueue_run_execution", side_effect=lambda *args, **kwargs: enq.append(args)):
                cb_run_id = server._dispatch_terminal_callback_for_run(store, source["id"], meta=meta)

            self.assertTrue(cb_run_id)
            self.assertEqual(len(enq), 1)
            cb_meta = store.load_meta(cb_run_id) or {}
            cv = cb_meta.get("communication_view") or {}
            self.assertEqual(cb_meta.get("trigger_type"), "callback_auto")
            self.assertEqual(cv.get("message_kind"), "system_callback")
            self.assertEqual(cv.get("event_reason"), "success")
            self.assertEqual(cv.get("dispatch_state"), "resolved")
            self.assertEqual(cv.get("dispatch_run_id"), cb_run_id)
            self.assertFalse(bool(cv.get("route_mismatch")))
            self.assertEqual(cv.get("source_project_id"), "task_dashboard")
            self.assertEqual(cv.get("source_session_id"), "22222222-2222-2222-2222-222222222222")
            self.assertEqual(cv.get("target_project_id"), "task_dashboard")
            self.assertEqual(cv.get("target_channel"), "主体-总控（合并与验收）")
            self.assertEqual(cv.get("target_session_id"), "22222222-2222-2222-2222-222222222222")
            self.assertEqual((cv.get("delivery_summary") or {}).get("delivery_state"), "delivered")
            self.assertTrue(bool((cv.get("delivery_summary") or {}).get("delivery_verified")))
            self.assertEqual((cv.get("receipt_summary_v2") or {}).get("receipt_state"), "received")
            self.assertTrue(bool((cv.get("receipt_summary_v2") or {}).get("receipt_received")))
            self.assertEqual((cv.get("callback_route_summary") or {}).get("receipt_route_state"), "expected_callback_route")
            rr = cv.get("route_resolution") or {}
            self.assertEqual((rr.get("source_ref") or {}).get("project_id"), "task_dashboard")
            self.assertEqual((rr.get("source_ref") or {}).get("session_id"), "22222222-2222-2222-2222-222222222222")

            summary = cb_meta.get("receipt_summary") or {}
            self.assertEqual(summary.get("source_project_id"), "task_dashboard")
            self.assertEqual(summary.get("source_session_id"), "22222222-2222-2222-2222-222222222222")
            self.assertEqual(summary.get("target_project_id"), "task_dashboard")
            self.assertEqual(summary.get("target_channel"), "主体-总控（合并与验收）")
            self.assertEqual(summary.get("target_session_id"), "22222222-2222-2222-2222-222222222222")

            src_after = store.load_meta(source["id"]) or {}
            src_cv = src_after.get("communication_view") or {}
            self.assertEqual(src_cv.get("event_reason"), "success")
            self.assertEqual(src_cv.get("dispatch_state"), "resolved")
            self.assertEqual(src_cv.get("dispatch_run_id"), cb_run_id)
            self.assertFalse(bool(src_cv.get("route_mismatch")))
            self.assertEqual(src_cv.get("source_project_id"), "task_dashboard")
            self.assertEqual(src_cv.get("source_session_id"), "22222222-2222-2222-2222-222222222222")
            self.assertEqual(src_cv.get("target_project_id"), "task_dashboard")
            self.assertEqual(src_cv.get("target_channel"), "主体-总控（合并与验收）")
            self.assertEqual(src_cv.get("target_session_id"), "22222222-2222-2222-2222-222222222222")
            self.assertEqual((src_cv.get("delivery_summary") or {}).get("delivery_state"), "delivered")
            self.assertEqual((src_cv.get("receipt_summary_v2") or {}).get("receipt_callback_run_id"), cb_run_id)
            self.assertEqual((src_cv.get("callback_route_summary") or {}).get("receipt_route_state"), "expected_callback_route")

    def test_done_callback_downgrades_self_referential_running_preview(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            target = {
                "channel_name": "辅助04-原型设计与Demo可视化（静态数据填充-业务规格确认）",
                "session_id": "24242424-2424-2424-2424-242424242424",
            }
            session_store = server.SessionStore(Path(td))
            session_store.create_session(
                "task_dashboard",
                target["channel_name"],
                cli_type="codex",
                session_id=target["session_id"],
            )

            source = store.create_run(
                "task_dashboard",
                "子级08-测试与验收（功能-回归-发布）",
                "11111111-1111-1111-1111-111111111111",
                "QA 终验",
                sender_type="agent",
                sender_id=target["channel_name"],
                sender_name=target["channel_name"],
                extra_meta={
                    "callback_to": target,
                    "task_path": "任务规划/子级08/任务/qa.md",
                },
            )
            meta = store.load_meta(source["id"]) or {}
            meta["status"] = "done"
            meta["finishedAt"] = server._now_iso()
            meta["lastPreview"] = (
                f"当前结论：纠偏复跑 `{source['id']}` 仍在 running，"
                "未形成本主线最终终验结果。"
            )
            store.save_meta(source["id"], meta)

            with mock.patch("server._enqueue_run_execution"):
                cb_run_id = server._dispatch_terminal_callback_for_run(store, source["id"], meta=meta)

            self.assertTrue(cb_run_id)
            cb_meta = store.load_meta(cb_run_id) or {}
            summary = cb_meta.get("receipt_summary") or {}
            self.assertEqual(summary.get("conclusion"), "执行结果无效，需最小复验")
            self.assertEqual(
                str((summary.get("technical") or {}).get("invalid_terminal_preview_reason") or ""),
                "self_referential_running",
            )
            message = store.read_msg(cb_run_id, limit_chars=120000)
            self.assertIn("执行结果无效，需最小复验", message)
            self.assertIn("请按当前主线重发最小复验", message)
            self.assertNotIn(f"{source['id']}` 仍在 running", message)
            self.assertNotIn(f"{source['id']} 仍在 running", message)

    def test_done_callback_marks_late_when_task_already_archived(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            session_store = server.SessionStore(Path(td))
            session_store.create_session(
                "task_dashboard",
                "主体-总控（合并与验收）",
                cli_type="claude",
                session_id="21212121-2121-2121-2121-212121212121",
            )
            source = store.create_run(
                "task_dashboard",
                "子级05-任务巡检与留痕（自动化）",
                "11111111-1111-1111-1111-111111111111",
                "执行任务",
                sender_type="agent",
                sender_id="主体-总控（合并与验收）",
                sender_name="主体-总控（合并与验收）",
                extra_meta={
                    "callback_to": {
                        "channel_name": "主体-总控（合并与验收）",
                        "session_id": "21212121-2121-2121-2121-212121212121",
                    },
                    "task_path": "任务规划/子级05/已完成/xx.md",
                    "execution_mode": "supervised",
                    "trigger_type": "manual_dispatch",
                },
            )
            meta = store.load_meta(source["id"]) or {}
            meta["status"] = "done"
            meta["finishedAt"] = server._now_iso()
            store.save_meta(source["id"], meta)

            with mock.patch("server._enqueue_run_execution"):
                cb_run_id = server._dispatch_terminal_callback_for_run(store, source["id"], meta=meta)

            self.assertTrue(cb_run_id)
            cb_meta = store.load_meta(cb_run_id) or {}
            summary = cb_meta.get("receipt_summary") or {}
            self.assertTrue(bool(summary.get("late_callback")))
            self.assertEqual(summary.get("need_confirm"), "无")
            self.assertIn("已归档", str(summary.get("need_peer") or ""))

    def test_inspect_callback_task_activity_resolves_moved_task_by_task_id(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            old_path = "任务规划/子级02/任务/【进行中】【任务】20260331-old.md"
            new_path = "任务规划/子级02/任务/【进行中】【任务】20260331-new.md"
            task_id = "task_20260331_callback_demo"
            new_file = root / new_path
            new_file.parent.mkdir(parents=True, exist_ok=True)
            new_file.write_text(
                render_task_front_matter(task_id=task_id)
                + "# 【进行中】【任务】20260331-new\n\n## 任务目标\n- test\n",
                encoding="utf-8",
            )
            record_task_move(
                repo_root=root,
                runtime_base_dir=root,
                project_id="task_dashboard",
                old_path=old_path,
                new_path=new_path,
                task_id=task_id,
            )

            with mock.patch("server._repo_root", return_value=root):
                activity = callback_runtime_module._inspect_callback_task_activity(
                    old_path,
                    project_id="task_dashboard",
                    task_id=task_id,
                )

            self.assertEqual(activity.get("task_path"), new_path)
            self.assertEqual(activity.get("task_id"), task_id)
            self.assertEqual(activity.get("state"), "active")

    def test_sender_agent_fallback_routes_to_primary_channel(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            store = server.RunStore(root)
            session_store = server.SessionStore(root)
            session_store.create_session(
                "task_dashboard",
                "主体-总控（合并与验收）",
                cli_type="codex",
                session_id="44444444-4444-4444-4444-444444444444",
            )
            source = store.create_run(
                "task_dashboard",
                "子级02-CCB运行时（server-并发-安全-启动）",
                "33333333-3333-3333-3333-333333333333",
                "执行中断",
                sender_type="agent",
                sender_id="主体-总控（合并与验收）",
                sender_name="主体-总控（合并与验收）",
            )
            meta = store.load_meta(source["id"]) or {}
            meta["status"] = "error"
            meta["error"] = "interrupted by user"
            meta["finishedAt"] = server._now_iso()
            store.save_meta(source["id"], meta)

            enq = []
            with mock.patch("server._repo_root", return_value=root), \
                mock.patch("server._enqueue_run_execution", side_effect=lambda *args, **kwargs: enq.append(args)):
                cb_run_id = server._dispatch_terminal_callback_for_run(store, source["id"], meta=meta)

            self.assertTrue(cb_run_id)
            self.assertEqual(len(enq), 1)
            cb_meta = store.load_meta(cb_run_id) or {}
            self.assertEqual(cb_meta.get("event_type"), "interrupted")
            self.assertEqual(cb_meta.get("event_reason"), "user_interrupt")
            rr = cb_meta.get("route_resolution") or {}
            self.assertEqual(rr.get("source"), "sender_agent")
            src_after = store.load_meta(source["id"]) or {}
            src_rr = src_after.get("route_resolution") or {}
            self.assertEqual(src_rr.get("source"), "sender_agent")
            self.assertEqual((src_rr.get("final_target") or {}).get("session_id"), "44444444-4444-4444-4444-444444444444")

    def test_user_interrupt_with_manual_origin_suppresses_auto_callback(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            target = {
                "channel_name": "主体-总控（合并与验收）",
                "session_id": "44444444-4444-4444-4444-444444444444",
            }
            source = store.create_run(
                "task_dashboard",
                "子级02-CCB运行时（server-并发-安全-启动）",
                "33333333-3333-3333-3333-333333333333",
                "执行中断",
                sender_type="agent",
                sender_id="主体-总控（合并与验收）",
                sender_name="主体-总控（合并与验收）",
                extra_meta={
                    "callback_to": target,
                    "interaction_mode": "task_with_receipt",
                },
            )
            meta = store.load_meta(source["id"]) or {}
            meta["status"] = "error"
            meta["error"] = "interrupted by user"
            meta["interrupt_origin"] = "user"
            meta["finishedAt"] = server._now_iso()
            meta["callback_dispatches"] = [
                {"status": "pending", "target": target},
                {"status": "sent", "callback_run_id": "already-sent"},
            ]
            store.save_meta(source["id"], meta)

            enq = []
            with mock.patch("server._enqueue_run_execution", side_effect=lambda *args, **kwargs: enq.append(args)):
                cb_run_id = server._dispatch_terminal_callback_for_run(store, source["id"], meta=meta)

            self.assertEqual(cb_run_id, "")
            self.assertEqual(enq, [])
            src_after = store.load_meta(source["id"]) or {}
            self.assertTrue(src_after.get("receipt_suppressed"))
            self.assertEqual(src_after.get("receipt_suppressed_reason"), "user_interrupt")
            self.assertEqual(src_after.get("auto_receipt_policy"), "suppressed_by_user_interrupt")
            self.assertEqual(src_after.get("chain_state"), "cancelled_by_user")
            self.assertEqual(src_after.get("suppressed_callback_to"), target)
            dispatches = src_after.get("callback_dispatches") or []
            self.assertEqual(dispatches[0].get("status"), "receipt_suppressed")
            self.assertEqual(dispatches[1].get("status"), "sent")

    def test_timeout_interrupt_still_dispatches_callback(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            target = {
                "channel_name": "主体-总控（合并与验收）",
                "session_id": "44444444-4444-4444-4444-444444444444",
            }
            source = store.create_run(
                "task_dashboard",
                "子级02-CCB运行时（server-并发-安全-启动）",
                "33333333-3333-3333-3333-333333333333",
                "执行超时",
                sender_type="agent",
                sender_id="主体-总控（合并与验收）",
                sender_name="主体-总控（合并与验收）",
                extra_meta={"callback_to": target},
            )
            meta = store.load_meta(source["id"]) or {}
            meta["status"] = "error"
            meta["error"] = "timeout>1200s"
            meta["finishedAt"] = server._now_iso()
            store.save_meta(source["id"], meta)

            enq = []
            with mock.patch("server._enqueue_run_execution", side_effect=lambda *args, **kwargs: enq.append(args)):
                cb_run_id = server._dispatch_terminal_callback_for_run(store, source["id"], meta=meta)

            self.assertTrue(cb_run_id)
            self.assertEqual(len(enq), 1)
            cb_meta = store.load_meta(cb_run_id) or {}
            self.assertEqual(cb_meta.get("event_type"), "interrupted")
            self.assertEqual(cb_meta.get("event_reason"), "timeout_interrupt")
            src_after = store.load_meta(source["id"]) or {}
            self.assertFalse(bool(src_after.get("receipt_suppressed")))

    def test_callback_auto_run_does_not_recurse(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            run = store.create_run(
                "task_dashboard",
                "主体-总控（合并与验收）",
                "55555555-5555-5555-5555-555555555555",
                "系统回执",
                sender_type="system",
                sender_id="system",
                sender_name="系统",
                extra_meta={"trigger_type": "callback_auto", "event_type": "done"},
            )
            meta = store.load_meta(run["id"]) or {}
            meta["status"] = "done"
            meta["finishedAt"] = server._now_iso()
            store.save_meta(run["id"], meta)

            with mock.patch("server._enqueue_run_execution") as m_enq:
                cb_run_id = server._dispatch_terminal_callback_for_run(store, run["id"], meta=meta)
            self.assertEqual(cb_run_id, "")
            m_enq.assert_not_called()
            metas = list(Path(td).glob("*.json"))
            self.assertEqual(len(metas), 1)

    def test_done_callback_self_target_same_channel_session_is_suppressed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            source = store.create_run(
                "task_dashboard",
                "主体-总控（合并与验收）",
                "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "执行完成",
                sender_type="agent",
                sender_id="legacy",
                sender_name="子级07-可视化看板（全局任务-通道-agent资源关系）",
            )
            meta = store.load_meta(source["id"]) or {}
            meta["status"] = "done"
            meta["finishedAt"] = server._now_iso()
            meta["lastPreview"] = "执行完成"
            store.save_meta(source["id"], meta)

            with mock.patch("server._resolve_master_control_target", return_value={
                "channel_name": "主体-总控（合并与验收）",
                "session_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            }), mock.patch("server._enqueue_run_execution") as m_enq:
                cb_run_id = server._dispatch_terminal_callback_for_run(store, source["id"], meta=meta)

            self.assertEqual(cb_run_id, "")
            m_enq.assert_not_called()
            src_after = store.load_meta(source["id"]) or {}
            dispatches = src_after.get("callback_dispatches") or []
            self.assertEqual(len(dispatches), 1)
            self.assertEqual(dispatches[0].get("status"), "self_suppressed")
            self.assertEqual(dispatches[0].get("note"), "self_target_same_channel_session")
            cv = src_after.get("communication_view") or {}
            self.assertEqual((cv.get("callback_route_summary") or {}).get("receipt_route_state"), "self_suppressed")
            self.assertEqual((cv.get("receipt_summary_v2") or {}).get("receipt_state"), "missing")
            self.assertEqual((cv.get("receipt_summary_v2") or {}).get("receipt_missing_reason"), "self_suppressed")

    def test_error_interrupted_uses_window_summary_after_first_immediate(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            target = {"channel_name": "主体-总控（合并与验收）", "session_id": "66666666-6666-6666-6666-666666666666"}
            route = {"source": "callback_to", "resolved_target": target}
            enq = []
            session_store = server.SessionStore(Path(td))
            session_store.create_session(
                "task_dashboard",
                "主体-总控（合并与验收）",
                cli_type="opencode",
                session_id=target["session_id"],
            )

            with mock.patch.dict(os.environ, {"CCB_CALLBACK_QUEUE_AGGREGATOR": "0"}, clear=False), \
                mock.patch("server.threading.Timer", _NoopTimer), \
                mock.patch("server._enqueue_run_execution", side_effect=lambda *args, **kwargs: enq.append(args)):
                # first error -> immediate callback
                r1 = store.create_run(
                    "task_dashboard",
                    "子级02-CCB运行时（server-并发-安全-启动）",
                    "77777777-7777-7777-7777-777777777777",
                    "err1",
                    sender_type="agent",
                    sender_id="主体-总控（合并与验收）",
                    sender_name="主体-总控（合并与验收）",
                    extra_meta={"callback_to": target},
                )
                m1 = store.load_meta(r1["id"]) or {}
                m1["status"] = "error"
                m1["error"] = "boom"
                m1["finishedAt"] = server._now_iso()
                store.save_meta(r1["id"], m1)
                rid1 = server._dispatch_terminal_callback_for_run(store, r1["id"], meta=m1)
                self.assertTrue(rid1)

                # second error same channel/target within window -> suppress + aggregate
                r2 = store.create_run(
                    "task_dashboard",
                    "子级02-CCB运行时（server-并发-安全-启动）",
                    "77777777-7777-7777-7777-777777777777",
                    "err2",
                    sender_type="agent",
                    sender_id="主体-总控（合并与验收）",
                    sender_name="主体-总控（合并与验收）",
                    extra_meta={"callback_to": target},
                )
                m2 = store.load_meta(r2["id"]) or {}
                m2["status"] = "error"
                m2["error"] = "boom2"
                m2["finishedAt"] = server._now_iso()
                store.save_meta(r2["id"], m2)
                rid2 = server._dispatch_terminal_callback_for_run(store, r2["id"], meta=m2)
                self.assertEqual(rid2, "")

                key = server._callback_throttle_key(
                    "task_dashboard",
                    "子级02-CCB运行时（server-并发-安全-启动）",
                    "未关联任务",
                    "error",
                    "error",
                )
                with server._CALLBACK_WINDOW_LOCK:
                    self.assertIn(key, server._CALLBACK_WINDOWS)
                    self.assertEqual(len(server._CALLBACK_WINDOWS[key].get("pending") or []), 1)

                # manually flush summary
                server._flush_callback_summary_window(store, None, key)

            self.assertGreaterEqual(len(enq), 2)  # first immediate + summary
            # verify second source run marked suppressed
            src2 = store.load_meta(r2["id"]) or {}
            dispatches2 = src2.get("callback_dispatches") or []
            self.assertEqual(dispatches2[0].get("status"), "suppressed_window")
            # verify summary run exists
            summary_runs = []
            for p in Path(td).glob("*.json"):
                meta = store.load_meta(p.stem) or {}
                if str(meta.get("trigger_type") or "") == "callback_auto_summary":
                    summary_runs.append(meta)
            self.assertEqual(len(summary_runs), 1)
            self.assertEqual(summary_runs[0].get("event_type"), "error")
            self.assertEqual(summary_runs[0].get("cliType"), "opencode")
            summary = summary_runs[0].get("receipt_summary") or {}
            self.assertEqual(summary.get("message_kind"), "system_callback_summary")
            self.assertTrue(bool((summary.get("technical") or {}).get("source_run_ids")))

    def test_unverified_callback_keeps_view_pending(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            source = store.create_run(
                "task_dashboard",
                "子级02-CCB运行时（server-并发-安全-启动）",
                "99999999-9999-9999-9999-999999999999",
                "执行完成",
                sender_type="agent",
                sender_id="legacy",
                sender_name="历史脚本",
                extra_meta={"execution_mode": "managed"},
            )
            meta = store.load_meta(source["id"]) or {}
            meta["status"] = "done"
            meta["finishedAt"] = server._now_iso()
            meta["lastPreview"] = "执行完成"
            store.save_meta(source["id"], meta)

            with mock.patch("server._resolve_primary_target_by_channel", return_value=None), \
                    mock.patch("server._resolve_master_control_target", return_value=None):
                cb_run_id = server._dispatch_terminal_callback_for_run(store, source["id"], meta=meta)

            self.assertEqual(cb_run_id, "")
            src_after = store.load_meta(source["id"]) or {}
            cv = src_after.get("communication_view") or {}
            self.assertEqual(cv.get("event_reason"), "unverified")
            self.assertEqual(cv.get("dispatch_state"), "pending")
            self.assertEqual(cv.get("dispatch_run_id"), "")
            self.assertFalse(bool(cv.get("route_mismatch")))
            self.assertEqual((cv.get("delivery_summary") or {}).get("delivery_state"), "pending")

    def test_callback_to_cross_session_marks_expected_callback_route(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            source = store.create_run(
                "task_dashboard",
                "子级02-CCB运行时（server-并发-安全-启动）",
                "aaaa1111-1111-1111-1111-111111111111",
                "执行完成",
                sender_type="agent",
                sender_id="主体-总控（合并与验收）",
                sender_name="主体-总控（合并与验收）",
                extra_meta={
                    "callback_to": {
                        "channel_name": "子级04-前端体验（task-overview 页面交互）",
                        "session_id": "bbbb2222-2222-2222-2222-222222222222",
                    },
                    "execution_mode": "managed",
                    "task_path": "任务规划/子级02-CCB运行时（server-并发-安全-启动）/任务/xx.md",
                },
            )
            meta = store.load_meta(source["id"]) or {}
            meta["status"] = "done"
            meta["finishedAt"] = server._now_iso()
            meta["lastPreview"] = "执行完成"
            store.save_meta(source["id"], meta)

            enq = []
            with mock.patch("server._enqueue_run_execution", side_effect=lambda *args, **kwargs: enq.append(args)):
                cb_run_id = server._dispatch_terminal_callback_for_run(store, source["id"], meta=meta)

            self.assertTrue(cb_run_id)
            self.assertEqual(len(enq), 1)
            cb_meta = store.load_meta(cb_run_id) or {}
            cv = cb_meta.get("communication_view") or {}
            self.assertEqual(cv.get("event_reason"), "success")
            self.assertEqual(cv.get("dispatch_state"), "resolved")
            self.assertFalse(bool(cv.get("route_mismatch")))
            self.assertEqual(cv.get("dispatch_run_id"), cb_run_id)
            self.assertEqual((cv.get("callback_route_summary") or {}).get("receipt_route_state"), "expected_callback_route")

            src_after = store.load_meta(source["id"]) or {}
            src_cv = src_after.get("communication_view") or {}
            self.assertEqual(src_cv.get("event_reason"), "success")
            self.assertEqual(src_cv.get("dispatch_state"), "resolved")
            self.assertFalse(bool(src_cv.get("route_mismatch")))
            self.assertEqual(src_cv.get("dispatch_run_id"), cb_run_id)
            self.assertEqual((src_cv.get("callback_route_summary") or {}).get("receipt_route_state"), "expected_callback_route")

    def test_sender_agent_fallback_keeps_route_mismatch_in_callback_route_summary(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            source = store.create_run(
                "task_dashboard",
                "子级02-CCB运行时（server-并发-安全-启动）",
                "aaaa1111-1111-1111-1111-111111111111",
                "执行异常",
                sender_type="agent",
                sender_id="主体-总控（合并与验收）",
                sender_name="主体-总控（合并与验收）",
            )
            meta = store.load_meta(source["id"]) or {}
            meta["status"] = "error"
            meta["error"] = "boom"
            meta["finishedAt"] = server._now_iso()
            store.save_meta(source["id"], meta)

            with mock.patch(
                "server._resolve_primary_target_by_channel",
                return_value={
                    "channel_name": "主体-总控（合并与验收）",
                    "session_id": "bbbb2222-2222-2222-2222-222222222222",
                },
            ), mock.patch("server._enqueue_run_execution"):
                cb_run_id = server._dispatch_terminal_callback_for_run(store, source["id"], meta=meta)

            self.assertTrue(cb_run_id)
            src_after = store.load_meta(source["id"]) or {}
            cv = src_after.get("communication_view") or {}
            self.assertEqual(cv.get("event_reason"), "route_mismatch")
            self.assertEqual(cv.get("dispatch_state"), "route_mismatch")
            self.assertTrue(bool(cv.get("route_mismatch")))
            self.assertEqual((cv.get("callback_route_summary") or {}).get("receipt_route_state"), "route_mismatch")
            self.assertEqual((cv.get("delivery_summary") or {}).get("delivery_state"), "delivered")
            self.assertEqual((cv.get("receipt_summary_v2") or {}).get("receipt_state"), "not_required")

    def test_task_with_receipt_without_callback_to_marks_missing_callback_to(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            source = store.create_run(
                "task_dashboard",
                "子级02-CCB运行时（server-并发-安全-启动）",
                "99999999-9999-9999-9999-999999999999",
                "执行完成",
                sender_type="agent",
                sender_id="legacy",
                sender_name="历史脚本",
                extra_meta={"interaction_mode": "task_with_receipt"},
            )
            meta = store.load_meta(source["id"]) or {}
            meta["status"] = "done"
            meta["finishedAt"] = server._now_iso()
            meta["lastPreview"] = "执行完成"
            store.save_meta(source["id"], meta)

            with mock.patch("server._resolve_primary_target_by_channel", return_value=None), \
                    mock.patch("server._resolve_master_control_target", return_value=None):
                cb_run_id = server._dispatch_terminal_callback_for_run(store, source["id"], meta=meta)

            self.assertEqual(cb_run_id, "")
            src_after = store.load_meta(source["id"]) or {}
            cv = src_after.get("communication_view") or {}
            self.assertEqual((cv.get("callback_route_summary") or {}).get("receipt_route_state"), "missing_callback_to")
            self.assertEqual((cv.get("receipt_summary_v2") or {}).get("receipt_state"), "missing")
            self.assertEqual((cv.get("receipt_summary_v2") or {}).get("receipt_missing_reason"), "missing_callback_to")

    def test_provider_transient_failure_stays_separate_from_missing_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            target = {
                "channel_name": "主体-总控（合并与验收）",
                "session_id": "bbbb2222-2222-2222-2222-222222222222",
            }
            session_store = server.SessionStore(Path(td))
            session_store.create_session(
                "task_dashboard",
                target["channel_name"],
                cli_type="codex",
                session_id=target["session_id"],
            )
            source = store.create_run(
                "task_dashboard",
                "子级02-CCB运行时（server-并发-安全-启动）",
                "aaaa1111-1111-1111-1111-111111111111",
                "provider error",
                sender_type="agent",
                sender_id=target["channel_name"],
                sender_name=target["channel_name"],
                extra_meta={"callback_to": target},
            )
            meta = store.load_meta(source["id"]) or {}
            meta["status"] = "error"
            meta["error"] = "status 429 provider temporarily unavailable"
            meta["finishedAt"] = server._now_iso()
            meta["failure_class"] = "provider_transient"
            meta["provider_error"] = {"kind": "rate_limit", "retryable": True, "matched_patterns": ["429"]}
            meta["side_effect_risk"] = "none"
            meta["recovery_mode"] = "auto_retry"
            meta["recovery_required"] = False
            meta["retry_exhausted"] = False
            store.save_meta(source["id"], meta)

            with mock.patch("server._enqueue_run_execution"):
                cb_run_id = server._dispatch_terminal_callback_for_run(store, source["id"], meta=meta)

            self.assertTrue(cb_run_id)
            src_after = store.load_meta(source["id"]) or {}
            receipt_v2 = (src_after.get("communication_view") or {}).get("receipt_summary_v2") or {}
            self.assertEqual(receipt_v2.get("receipt_state"), "received")
            self.assertNotEqual(receipt_v2.get("receipt_state"), "missing")
            self.assertEqual(receipt_v2.get("failure_class"), "provider_transient")
            self.assertEqual((receipt_v2.get("provider_error") or {}).get("kind"), "rate_limit")
            self.assertEqual(receipt_v2.get("side_effect_risk"), "none")
            self.assertEqual(receipt_v2.get("recovery_mode"), "auto_retry")

    def test_callback_window_bypasses_on_need_confirmation_change(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            target = {"channel_name": "主体-总控（合并与验收）", "session_id": "66666666-6666-6666-6666-666666666666"}
            session_store = server.SessionStore(Path(td))
            session_store.create_session(
                "task_dashboard",
                "主体-总控（合并与验收）",
                cli_type="codex",
                session_id=target["session_id"],
            )
            enq = []
            with mock.patch.dict(os.environ, {"CCB_CALLBACK_QUEUE_AGGREGATOR": "0"}, clear=False), \
                mock.patch("server.threading.Timer", _NoopTimer), \
                mock.patch("server._enqueue_run_execution", side_effect=lambda *args, **kwargs: enq.append(args)):
                r1 = store.create_run(
                    "task_dashboard",
                    "子级05-任务巡检与留痕（自动化）",
                    "77777777-7777-7777-7777-777777777777",
                    "error-1",
                    sender_type="agent",
                    sender_id="主体-总控（合并与验收）",
                    sender_name="主体-总控（合并与验收）",
                    extra_meta={
                        "callback_to": target,
                        "task_path": "任务规划/子级05/任务/xx.md",
                        "execution_stage": "联调",
                        "need_confirmation": "无",
                    },
                )
                m1 = store.load_meta(r1["id"]) or {}
                m1["status"] = "error"
                m1["error"] = "boom-1"
                m1["finishedAt"] = server._now_iso()
                store.save_meta(r1["id"], m1)
                rid1 = server._dispatch_terminal_callback_for_run(store, r1["id"], meta=m1)
                self.assertTrue(rid1)

                r2 = store.create_run(
                    "task_dashboard",
                    "子级05-任务巡检与留痕（自动化）",
                    "77777777-7777-7777-7777-777777777777",
                    "error-2",
                    sender_type="agent",
                    sender_id="主体-总控（合并与验收）",
                    sender_name="主体-总控（合并与验收）",
                    extra_meta={
                        "callback_to": target,
                        "task_path": "任务规划/子级05/任务/xx.md",
                        "execution_stage": "联调",
                        "need_confirmation": "需总控确认",
                    },
                )
                m2 = store.load_meta(r2["id"]) or {}
                m2["status"] = "error"
                m2["error"] = "boom-2"
                m2["finishedAt"] = server._now_iso()
                store.save_meta(r2["id"], m2)
                rid2 = server._dispatch_terminal_callback_for_run(store, r2["id"], meta=m2)
                self.assertTrue(rid2)

            # first + second should both be immediate dispatches (bypass suppression on change)
            self.assertGreaterEqual(len(enq), 2)
            src2 = store.load_meta(r2["id"]) or {}
            dispatches = src2.get("callback_dispatches") or []
            self.assertTrue(dispatches)
            self.assertEqual(dispatches[0].get("status"), "sent")
            self.assertIn("summary_window_bypass", str(dispatches[0].get("note") or ""))

    def test_classify_timeout_error_as_interrupted_timeout_interrupt(self) -> None:
        ev, reason = server._classify_terminal_callback_event({"status": "error", "error": "timeout>1200s"})
        self.assertEqual(ev, "interrupted")
        self.assertEqual(reason, "timeout_interrupt")

    def test_route_resolution_records_degrade_reason_on_master_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            source = store.create_run(
                "task_dashboard",
                "子级02-CCB运行时（server-并发-安全-启动）",
                "88888888-8888-8888-8888-888888888888",
                "执行完成",
                sender_type="agent",
                sender_id="主体-总控（合并与验收）",
                sender_name="主体-总控（合并与验收）",
                extra_meta={
                    "callback_to": {
                        "channel_name": "不存在的通道",
                    }
                },
            )
            meta = store.load_meta(source["id"]) or {}
            meta["status"] = "done"
            meta["finishedAt"] = server._now_iso()
            store.save_meta(source["id"], meta)

            with mock.patch("server._resolve_primary_target_by_channel", return_value=None), \
                mock.patch(
                    "server._resolve_master_control_target",
                    return_value={
                        "channel_name": "主体-总控（合并与验收）",
                        "session_id": "99999999-9999-9999-9999-999999999999",
                    },
                ), \
                mock.patch("server._enqueue_run_execution"):
                cb_run_id = server._dispatch_terminal_callback_for_run(store, source["id"], meta=meta)

            self.assertTrue(cb_run_id)
            src_after = store.load_meta(source["id"]) or {}
            rr = src_after.get("route_resolution") or {}
            self.assertEqual(rr.get("source"), "master_fallback")
            self.assertEqual(rr.get("fallback_stage"), "fallback_to_master")
            self.assertEqual(rr.get("degrade_reason"), "callback_to_channel_unresolved")
            self.assertEqual((rr.get("final_target") or {}).get("session_id"), "99999999-9999-9999-9999-999999999999")

    def test_callback_projects_receipt_fields_to_source_ref_host_run(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            session_store = server.SessionStore(Path(td))
            target = {
                "channel_name": "主体-总控（合并与验收）",
                "session_id": "81818181-8181-8181-8181-818181818181",
            }
            session_store.create_session(
                "task_dashboard",
                target["channel_name"],
                cli_type="codex",
                session_id=target["session_id"],
            )
            host = store.create_run(
                "task_dashboard",
                target["channel_name"],
                target["session_id"],
                "原始协作消息",
                sender_type="agent",
                sender_id="主体-总控（合并与验收）",
                sender_name="主体-总控（合并与验收）",
                extra_meta={
                    "interaction_mode": "task_with_receipt",
                    "target_ref": {
                        "project_id": "task_dashboard",
                        "channel_name": "子级02-CCB运行时（server-并发-安全-启动）",
                        "session_id": "71717171-7171-7171-7171-717171717171",
                    },
                    "visible_in_channel_chat": True,
                },
            )
            source = store.create_run(
                "task_dashboard",
                "子级02-CCB运行时（server-并发-安全-启动）",
                "71717171-7171-7171-7171-717171717171",
                "执行完成",
                sender_type="agent",
                sender_id="主体-总控（合并与验收）",
                sender_name="主体-总控（合并与验收）",
                extra_meta={
                    "callback_to": target,
                    "owner_ref": {
                        "channel_name": "子级02-CCB运行时（server-并发-安全-启动）",
                        "agent_name": "服务开发-通讯能力",
                        "alias": "服务开发-通讯能力",
                        "session_id": "71717171-7171-7171-7171-717171717171",
                    },
                    "source_ref": {
                        "project_id": "task_dashboard",
                        "channel_name": target["channel_name"],
                        "session_id": target["session_id"],
                        "run_id": host["id"],
                    },
                    "task_path": "任务规划/子级02/任务/receipt-host.md",
                },
            )
            meta = store.load_meta(source["id"]) or {}
            meta["status"] = "done"
            meta["finishedAt"] = server._now_iso()
            meta["lastPreview"] = "执行完成"
            store.save_meta(source["id"], meta)

            with mock.patch("server._enqueue_run_execution"):
                cb_run_id = server._dispatch_terminal_callback_for_run(store, source["id"], meta=meta)

            self.assertTrue(cb_run_id)
            host_after = store.load_meta(host["id"]) or {}
            items = host_after.get("receipt_items") or []
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0].get("source_run_id"), source["id"])
            self.assertEqual(items[0].get("callback_run_id"), cb_run_id)
            self.assertEqual(items[0].get("host_run_id"), host["id"])
            self.assertEqual(items[0].get("host_reason"), "source_ref_run_id")
            self.assertEqual(items[0].get("event_type"), "done")
            self.assertEqual(items[0].get("runtime_status"), "queued")
            self.assertEqual(items[0].get("source_agent_name"), "服务开发-通讯能力")
            rollup = host_after.get("receipt_rollup") or {}
            self.assertEqual(rollup.get("total_callbacks"), 1)
            self.assertEqual(rollup.get("host_run_id"), host["id"])
            self.assertEqual(rollup.get("latest_status"), "queued")
            self.assertEqual(rollup.get("agents"), ["服务开发-通讯能力"])
            host_cv = host_after.get("communication_view") or {}
            self.assertEqual((host_cv.get("delivery_summary") or {}).get("delivery_state"), "delivered")
            self.assertEqual((host_cv.get("receipt_summary_v2") or {}).get("receipt_state"), "received")
            self.assertEqual((host_cv.get("receipt_summary_v2") or {}).get("receipt_callback_run_id"), cb_run_id)
            self.assertEqual((host_cv.get("callback_route_summary") or {}).get("receipt_route_state"), "expected_callback_route")

    def test_queue_aggregator_merges_into_earliest_queued_anchor(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            target = {"channel_name": "主体-总控（合并与验收）", "session_id": "21212121-2121-2121-2121-212121212121"}
            session_store = server.SessionStore(Path(td))
            session_store.create_session(
                "task_dashboard",
                target["channel_name"],
                cli_type="codex",
                session_id=target["session_id"],
            )

            with mock.patch.dict(os.environ, {"CCB_CALLBACK_QUEUE_AGGREGATOR": "1"}, clear=False), \
                mock.patch("server._enqueue_run_execution"):
                src1 = store.create_run(
                    "task_dashboard",
                    "子级04-前端体验（task-overview 页面交互）",
                    "11111111-1111-1111-1111-111111111111",
                    "第一次回执",
                    sender_type="agent",
                    sender_id="主体-总控（合并与验收）",
                    sender_name="主体-总控（合并与验收）",
                    extra_meta={"callback_to": target, "task_path": "任务规划/子级04/任务/xx.md"},
                )
                m1 = store.load_meta(src1["id"]) or {}
                m1["status"] = "error"
                m1["error"] = "boom-1"
                m1["finishedAt"] = server._now_iso()
                store.save_meta(src1["id"], m1)
                cb1 = server._dispatch_terminal_callback_for_run(store, src1["id"], meta=m1)
                self.assertTrue(cb1)

                src2 = store.create_run(
                    "task_dashboard",
                    "子级04-前端体验（task-overview 页面交互）",
                    "11111111-1111-1111-1111-111111111111",
                    "第二次回执",
                    sender_type="agent",
                    sender_id="主体-总控（合并与验收）",
                    sender_name="主体-总控（合并与验收）",
                    extra_meta={"callback_to": target, "task_path": "任务规划/子级04/任务/xx.md"},
                )
                m2 = store.load_meta(src2["id"]) or {}
                m2["status"] = "error"
                m2["error"] = "boom-2"
                m2["finishedAt"] = server._now_iso()
                store.save_meta(src2["id"], m2)
                cb2 = server._dispatch_terminal_callback_for_run(store, src2["id"], meta=m2)

            self.assertEqual(cb2, cb1)
            anchor = store.load_meta(cb1) or {}
            self.assertEqual(anchor.get("callback_merge_mode"), "queue_anchor_v2")
            self.assertEqual(int(anchor.get("callback_aggregate_count") or 0), 2)
            source_ids = anchor.get("callback_aggregate_source_run_ids") or []
            self.assertIn(src1["id"], source_ids)
            self.assertIn(src2["id"], source_ids)
            src2_after = store.load_meta(src2["id"]) or {}
            dispatches2 = src2_after.get("callback_dispatches") or []
            self.assertTrue(dispatches2)
            self.assertEqual(dispatches2[0].get("status"), "merged_anchor")
            src2_cv = src2_after.get("communication_view") or {}
            self.assertEqual((src2_cv.get("callback_route_summary") or {}).get("receipt_route_state"), "merged_anchor")
            self.assertEqual((src2_cv.get("receipt_summary_v2") or {}).get("receipt_state"), "received")

    def test_queue_aggregator_projects_multiple_receipts_to_same_host_run(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            target = {"channel_name": "主体-总控（合并与验收）", "session_id": "20202020-2020-2020-2020-202020202020"}
            session_store = server.SessionStore(Path(td))
            session_store.create_session(
                "task_dashboard",
                target["channel_name"],
                cli_type="codex",
                session_id=target["session_id"],
            )
            host = store.create_run(
                "task_dashboard",
                target["channel_name"],
                target["session_id"],
                "原始协作消息",
                sender_type="agent",
                sender_id="主体-总控（合并与验收）",
                sender_name="主体-总控（合并与验收）",
            )

            with mock.patch.dict(os.environ, {"CCB_CALLBACK_QUEUE_AGGREGATOR": "1"}, clear=False), \
                mock.patch("server._enqueue_run_execution"):
                src1 = store.create_run(
                    "task_dashboard",
                    "子级04-前端体验（task-overview 页面交互）",
                    "11111111-1111-1111-1111-111111111111",
                    "第一次回执",
                    sender_type="agent",
                    sender_id="主体-总控（合并与验收）",
                    sender_name="主体-总控（合并与验收）",
                    extra_meta={
                        "callback_to": target,
                        "source_ref": {
                            "project_id": "task_dashboard",
                            "channel_name": target["channel_name"],
                            "session_id": target["session_id"],
                            "run_id": host["id"],
                        },
                        "task_path": "任务规划/子级04/任务/alpha.md",
                    },
                )
                m1 = store.load_meta(src1["id"]) or {}
                m1["status"] = "error"
                m1["error"] = "boom-1"
                m1["finishedAt"] = server._now_iso()
                store.save_meta(src1["id"], m1)
                cb1 = server._dispatch_terminal_callback_for_run(store, src1["id"], meta=m1)
                self.assertTrue(cb1)

                src2 = store.create_run(
                    "task_dashboard",
                    "子级02-CCB运行时（server-并发-安全-启动）",
                    "12121212-1212-1212-1212-121212121212",
                    "第二次回执",
                    sender_type="agent",
                    sender_id="主体-总控（合并与验收）",
                    sender_name="主体-总控（合并与验收）",
                    extra_meta={
                        "callback_to": target,
                        "source_ref": {
                            "project_id": "task_dashboard",
                            "channel_name": target["channel_name"],
                            "session_id": target["session_id"],
                            "run_id": host["id"],
                        },
                        "task_path": "任务规划/子级02/任务/beta.md",
                    },
                )
                m2 = store.load_meta(src2["id"]) or {}
                m2["status"] = "error"
                m2["error"] = "boom-2"
                m2["finishedAt"] = server._now_iso()
                store.save_meta(src2["id"], m2)
                cb2 = server._dispatch_terminal_callback_for_run(store, src2["id"], meta=m2)

            self.assertEqual(cb2, cb1)
            host_after = store.load_meta(host["id"]) or {}
            items = host_after.get("receipt_items") or []
            self.assertEqual(len(items), 2)
            by_source = {str(item.get("source_run_id") or ""): item for item in items}
            self.assertEqual(str((by_source.get(src1["id"]) or {}).get("source_channel") or ""), "子级04-前端体验（task-overview 页面交互）")
            self.assertEqual(str((by_source.get(src2["id"]) or {}).get("source_channel") or ""), "子级02-CCB运行时（server-并发-安全-启动）")
            self.assertEqual(str((by_source.get(src2["id"]) or {}).get("callback_run_id") or ""), cb1)
            self.assertEqual(str((by_source.get(src2["id"]) or {}).get("dispatch_status") or ""), "merged_anchor")
            self.assertEqual(str((by_source.get(src2["id"]) or {}).get("receipt_route_state") or ""), "merged_anchor")
            rollup = host_after.get("receipt_rollup") or {}
            self.assertEqual(rollup.get("total_callbacks"), 2)
            self.assertEqual(rollup.get("error_count"), 2)

    def test_summary_window_projects_suppressed_receipt_to_same_host_run(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            target = {"channel_name": "主体-总控（合并与验收）", "session_id": "30303030-3030-3030-3030-303030303030"}
            session_store = server.SessionStore(Path(td))
            session_store.create_session(
                "task_dashboard",
                target["channel_name"],
                cli_type="codex",
                session_id=target["session_id"],
            )
            host = store.create_run(
                "task_dashboard",
                target["channel_name"],
                target["session_id"],
                "原始协作消息",
                sender_type="agent",
                sender_id="主体-总控（合并与验收）",
                sender_name="主体-总控（合并与验收）",
            )

            with mock.patch.dict(os.environ, {"CCB_CALLBACK_QUEUE_AGGREGATOR": "0"}, clear=False), \
                mock.patch("server.threading.Timer", _NoopTimer), \
                mock.patch("server._enqueue_run_execution"):
                src1 = store.create_run(
                    "task_dashboard",
                    "子级02-CCB运行时（server-并发-安全-启动）",
                    "40404040-4040-4040-4040-404040404040",
                    "error-1",
                    sender_type="agent",
                    sender_id="主体-总控（合并与验收）",
                    sender_name="主体-总控（合并与验收）",
                    extra_meta={
                        "callback_to": target,
                        "source_ref": {
                            "project_id": "task_dashboard",
                            "channel_name": target["channel_name"],
                            "session_id": target["session_id"],
                            "run_id": host["id"],
                        },
                        "task_path": "任务规划/子级02/任务/summary-host.md",
                    },
                )
                m1 = store.load_meta(src1["id"]) or {}
                m1["status"] = "error"
                m1["error"] = "boom-1"
                m1["finishedAt"] = server._now_iso()
                store.save_meta(src1["id"], m1)
                rid1 = server._dispatch_terminal_callback_for_run(store, src1["id"], meta=m1)
                self.assertTrue(rid1)

                src2 = store.create_run(
                    "task_dashboard",
                    "子级02-CCB运行时（server-并发-安全-启动）",
                    "40404040-4040-4040-4040-404040404040",
                    "error-2",
                    sender_type="agent",
                    sender_id="主体-总控（合并与验收）",
                    sender_name="主体-总控（合并与验收）",
                    extra_meta={
                        "callback_to": target,
                        "source_ref": {
                            "project_id": "task_dashboard",
                            "channel_name": target["channel_name"],
                            "session_id": target["session_id"],
                            "run_id": host["id"],
                        },
                        "task_path": "任务规划/子级02/任务/summary-host.md",
                    },
                )
                m2 = store.load_meta(src2["id"]) or {}
                m2["status"] = "error"
                m2["error"] = "boom-2"
                m2["finishedAt"] = server._now_iso()
                store.save_meta(src2["id"], m2)
                rid2 = server._dispatch_terminal_callback_for_run(store, src2["id"], meta=m2)
                self.assertEqual(rid2, "")

                key = server._callback_throttle_key(
                    "task_dashboard",
                    "子级02-CCB运行时（server-并发-安全-启动）",
                    "任务规划/子级02/任务/summary-host.md",
                    "error",
                    "error",
                )
                server._flush_callback_summary_window(store, None, key)

            summary_run_id = ""
            for meta in store.list_runs(project_id="task_dashboard", session_id=target["session_id"], limit=50):
                if str(meta.get("trigger_type") or "").strip().lower() == "callback_auto_summary":
                    summary_run_id = str(meta.get("id") or "").strip()
                    break
            self.assertTrue(summary_run_id)
            summary_meta = store.load_meta(summary_run_id) or {}
            self.assertEqual(summary_meta.get("display_host_run_id"), host["id"])
            host_after = store.load_meta(host["id"]) or {}
            items = host_after.get("receipt_items") or []
            self.assertEqual(len(items), 2)
            by_source = {str(item.get("source_run_id") or ""): item for item in items}
            self.assertEqual(str((by_source.get(src2["id"]) or {}).get("callback_run_id") or ""), summary_run_id)
            self.assertEqual(str((by_source.get(src2["id"]) or {}).get("trigger_type") or ""), "callback_auto_summary")
            self.assertEqual(str((by_source.get(src2["id"]) or {}).get("dispatch_status") or ""), "summary_window_member")
            rollup = host_after.get("receipt_rollup") or {}
            self.assertEqual(rollup.get("total_callbacks"), 2)

    def test_queue_aggregator_merges_across_event_and_task_and_appends_receipt_text(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            target = {"channel_name": "主体-总控（合并与验收）", "session_id": "26262626-2626-2626-2626-262626262626"}
            session_store = server.SessionStore(Path(td))
            session_store.create_session(
                "task_dashboard",
                target["channel_name"],
                cli_type="codex",
                session_id=target["session_id"],
            )

            with mock.patch.dict(os.environ, {"CCB_CALLBACK_QUEUE_AGGREGATOR": "1"}, clear=False), \
                mock.patch("server._enqueue_run_execution"):
                src1 = store.create_run(
                    "task_dashboard",
                    "子级04-前端体验（task-overview 页面交互）",
                    "11111111-1111-1111-1111-111111111111",
                    "第一次回执",
                    sender_type="agent",
                    sender_id="主体-总控（合并与验收）",
                    sender_name="主体-总控（合并与验收）",
                    extra_meta={"callback_to": target, "task_path": "任务规划/子级04/任务/alpha.md"},
                )
                m1 = store.load_meta(src1["id"]) or {}
                m1["status"] = "done"
                m1["lastPreview"] = "alpha 完成"
                m1["finishedAt"] = server._now_iso()
                store.save_meta(src1["id"], m1)
                cb1 = server._dispatch_terminal_callback_for_run(store, src1["id"], meta=m1)
                self.assertTrue(cb1)

                src2 = store.create_run(
                    "task_dashboard",
                    "子级02-CCB运行时（server-并发-安全-启动）",
                    "12121212-1212-1212-1212-121212121212",
                    "第二次回执",
                    sender_type="agent",
                    sender_id="主体-总控（合并与验收）",
                    sender_name="主体-总控（合并与验收）",
                    extra_meta={"callback_to": target, "task_path": "任务规划/子级02/任务/beta.md"},
                )
                m2 = store.load_meta(src2["id"]) or {}
                m2["status"] = "error"
                m2["error"] = "beta failed"
                m2["finishedAt"] = server._now_iso()
                store.save_meta(src2["id"], m2)
                cb2 = server._dispatch_terminal_callback_for_run(store, src2["id"], meta=m2)

            self.assertEqual(cb2, cb1)
            anchor = store.load_meta(cb1) or {}
            self.assertEqual(int(anchor.get("callback_aggregate_count") or 0), 2)
            msg = store.read_msg(cb1, limit_chars=300000)
            self.assertIn("[并入回执]", msg)
            self.assertIn(f"source_run_id={src2['id']}", msg)
            self.assertIn("[来源通道: 子级02-CCB运行时（server-并发-安全-启动）]", msg)
            self.assertIn("回执任务: 任务规划/子级02/任务/beta.md", msg)
            src2_after = store.load_meta(src2["id"]) or {}
            dispatches2 = src2_after.get("callback_dispatches") or []
            self.assertTrue(dispatches2)
            self.assertEqual(dispatches2[0].get("status"), "merged_anchor")

    def test_queue_aggregator_overflow_rotates_to_new_anchor(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            target = {"channel_name": "主体-总控（合并与验收）", "session_id": "31313131-3131-3131-3131-313131313131"}
            session_store = server.SessionStore(Path(td))
            session_store.create_session(
                "task_dashboard",
                target["channel_name"],
                cli_type="codex",
                session_id=target["session_id"],
            )

            with mock.patch.dict(
                os.environ,
                {
                    "CCB_CALLBACK_QUEUE_AGGREGATOR": "1",
                    "CCB_CALLBACK_ANCHOR_MAX_MERGES": "10",
                },
                clear=False,
            ), mock.patch("server._enqueue_run_execution"):
                src1 = store.create_run(
                    "task_dashboard",
                    "子级04-前端体验（task-overview 页面交互）",
                    "11111111-1111-1111-1111-111111111111",
                    "第一次回执",
                    sender_type="agent",
                    sender_id="主体-总控（合并与验收）",
                    sender_name="主体-总控（合并与验收）",
                    extra_meta={"callback_to": target, "task_path": "任务规划/子级04/任务/xx.md"},
                )
                m1 = store.load_meta(src1["id"]) or {}
                m1["status"] = "error"
                m1["error"] = "boom-1"
                m1["finishedAt"] = server._now_iso()
                store.save_meta(src1["id"], m1)
                cb1 = server._dispatch_terminal_callback_for_run(store, src1["id"], meta=m1)
                self.assertTrue(cb1)
                anchor = store.load_meta(cb1) or {}
                anchor["callback_aggregate_count"] = 10
                store.save_meta(cb1, anchor)

                src2 = store.create_run(
                    "task_dashboard",
                    "子级04-前端体验（task-overview 页面交互）",
                    "11111111-1111-1111-1111-111111111111",
                    "第二次回执",
                    sender_type="agent",
                    sender_id="主体-总控（合并与验收）",
                    sender_name="主体-总控（合并与验收）",
                    extra_meta={"callback_to": target, "task_path": "任务规划/子级04/任务/xx.md"},
                )
                m2 = store.load_meta(src2["id"]) or {}
                m2["status"] = "error"
                m2["error"] = "boom-2"
                m2["finishedAt"] = server._now_iso()
                store.save_meta(src2["id"], m2)
                cb2 = server._dispatch_terminal_callback_for_run(store, src2["id"], meta=m2)

            self.assertTrue(cb2)
            self.assertNotEqual(cb2, cb1)
            src2_after = store.load_meta(src2["id"]) or {}
            dispatches2 = src2_after.get("callback_dispatches") or []
            self.assertTrue(dispatches2)
            self.assertIn("anchor_overflow_new_anchor", str(dispatches2[0].get("note") or ""))
            new_anchor = store.load_meta(cb2) or {}
            self.assertEqual(new_anchor.get("callback_anchor_action"), "overflow_new_anchor")

    def test_queue_aggregator_merge_failure_degrades_to_new_anchor(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            target = {"channel_name": "主体-总控（合并与验收）", "session_id": "41414141-4141-4141-4141-414141414141"}
            session_store = server.SessionStore(Path(td))
            session_store.create_session(
                "task_dashboard",
                target["channel_name"],
                cli_type="codex",
                session_id=target["session_id"],
            )

            with mock.patch.dict(os.environ, {"CCB_CALLBACK_QUEUE_AGGREGATOR": "1"}, clear=False), \
                mock.patch("server._enqueue_run_execution"):
                src1 = store.create_run(
                    "task_dashboard",
                    "子级04-前端体验（task-overview 页面交互）",
                    "11111111-1111-1111-1111-111111111111",
                    "第一次回执",
                    sender_type="agent",
                    sender_id="主体-总控（合并与验收）",
                    sender_name="主体-总控（合并与验收）",
                    extra_meta={"callback_to": target, "task_path": "任务规划/子级04/任务/xx.md"},
                )
                m1 = store.load_meta(src1["id"]) or {}
                m1["status"] = "error"
                m1["error"] = "boom-1"
                m1["finishedAt"] = server._now_iso()
                store.save_meta(src1["id"], m1)
                cb1 = server._dispatch_terminal_callback_for_run(store, src1["id"], meta=m1)
                self.assertTrue(cb1)

                src2 = store.create_run(
                    "task_dashboard",
                    "子级04-前端体验（task-overview 页面交互）",
                    "11111111-1111-1111-1111-111111111111",
                    "第二次回执",
                    sender_type="agent",
                    sender_id="主体-总控（合并与验收）",
                    sender_name="主体-总控（合并与验收）",
                    extra_meta={"callback_to": target, "task_path": "任务规划/子级04/任务/xx.md"},
                )
                m2 = store.load_meta(src2["id"]) or {}
                m2["status"] = "error"
                m2["error"] = "boom-2"
                m2["finishedAt"] = server._now_iso()
                store.save_meta(src2["id"], m2)
                with mock.patch("server._merge_callback_into_anchor", return_value=(False, {}, "forced")):
                    cb2 = server._dispatch_terminal_callback_for_run(store, src2["id"], meta=m2)

            self.assertTrue(cb2)
            self.assertNotEqual(cb2, cb1)
            src2_after = store.load_meta(src2["id"]) or {}
            dispatches2 = src2_after.get("callback_dispatches") or []
            self.assertTrue(dispatches2)
            self.assertIn("merge_failed_new_anchor:forced", str(dispatches2[0].get("note") or ""))
            new_anchor = store.load_meta(cb2) or {}
            self.assertEqual(new_anchor.get("callback_anchor_action"), "degraded_new_anchor")

    def test_callback_anchor_sets_display_host_run_id_for_target_side_sender_match(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            target = {"channel_name": "主体-总控（合并与验收）", "session_id": "61616161-6161-6161-6161-616161616161"}
            session_store = server.SessionStore(Path(td))
            session_store.create_session(
                "task_dashboard",
                target["channel_name"],
                cli_type="codex",
                session_id=target["session_id"],
            )
            host = store.create_run(
                "task_dashboard",
                target["channel_name"],
                target["session_id"],
                "总控宿主消息",
                sender_type="agent",
                sender_id="startup_director",
                sender_name="启动总协调",
            )
            src = store.create_run(
                "task_dashboard",
                "辅助06-项目运维",
                "71717171-7171-7171-7171-717171717171",
                "来源回执消息",
                sender_type="agent",
                sender_id="startup_director",
                sender_name="启动总协调",
                extra_meta={"callback_to": target},
            )
            meta = store.load_meta(src["id"]) or {}
            meta["status"] = "done"
            meta["finishedAt"] = server._now_iso()
            store.save_meta(src["id"], meta)

            with mock.patch("server._enqueue_run_execution"):
                cb_run_id = server._dispatch_terminal_callback_for_run(store, src["id"], meta=meta)

            self.assertTrue(cb_run_id)
            callback_meta = store.load_meta(cb_run_id) or {}
            self.assertEqual(callback_meta.get("display_host_run_id"), host["id"])

    def test_queue_aggregator_concurrent_same_second_creates_single_anchor(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            target = {"channel_name": "主体-总控（合并与验收）", "session_id": "51515151-5151-5151-5151-515151515151"}
            session_store = server.SessionStore(Path(td))
            session_store.create_session(
                "task_dashboard",
                target["channel_name"],
                cli_type="codex",
                session_id=target["session_id"],
            )

            source_ids: list[str] = []
            for idx in range(3):
                src = store.create_run(
                    "task_dashboard",
                    "子级04-前端体验（task-overview 页面交互）",
                    f"11111111-1111-1111-1111-11111111111{idx}",
                    f"并发回执-{idx}",
                    sender_type="agent",
                    sender_id="主体-总控（合并与验收）",
                    sender_name="主体-总控（合并与验收）",
                    extra_meta={"callback_to": target, "task_path": "任务规划/子级04/任务/xx.md"},
                )
                meta = store.load_meta(src["id"]) or {}
                meta["status"] = "error"
                meta["error"] = f"boom-{idx}"
                meta["finishedAt"] = server._now_iso()
                store.save_meta(src["id"], meta)
                source_ids.append(src["id"])

            callback_run_ids: list[str] = []
            with mock.patch.dict(os.environ, {"CCB_CALLBACK_QUEUE_AGGREGATOR": "1"}, clear=False), \
                mock.patch("server._enqueue_run_execution"):
                def _dispatch_one(src_id: str) -> str:
                    meta = store.load_meta(src_id) or {}
                    return server._dispatch_terminal_callback_for_run(store, src_id, meta=meta)

                with ThreadPoolExecutor(max_workers=3) as pool:
                    callback_run_ids = list(pool.map(_dispatch_one, source_ids))

            non_empty = {x for x in callback_run_ids if str(x or "").strip()}
            self.assertEqual(len(non_empty), 1)
            anchor_run_id = next(iter(non_empty))
            self.assertTrue(anchor_run_id)

            anchor_candidates = []
            for meta in store.list_runs(project_id="task_dashboard", session_id=target["session_id"], limit=200):
                if not isinstance(meta, dict):
                    continue
                if str(meta.get("trigger_type") or "").strip().lower() != "callback_auto":
                    continue
                if str(meta.get("event_type") or "").strip().lower() != "error":
                    continue
                anchor_candidates.append(meta)
            self.assertEqual(len(anchor_candidates), 1)
            self.assertEqual(str(anchor_candidates[0].get("id") or "").strip(), anchor_run_id)
            self.assertEqual(int(anchor_candidates[0].get("callback_aggregate_count") or 0), 3)

            for src_id in source_ids:
                src_meta = store.load_meta(src_id) or {}
                dispatches = src_meta.get("callback_dispatches") or []
                self.assertTrue(dispatches)
                self.assertEqual(str(dispatches[0].get("callback_run_id") or "").strip(), anchor_run_id)

    def test_queue_aggregator_concurrent_same_source_dispatch_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            target = {"channel_name": "主体-总控（合并与验收）", "session_id": "52525252-5252-5252-5252-525252525252"}
            session_store = server.SessionStore(Path(td))
            session_store.create_session(
                "task_dashboard",
                target["channel_name"],
                cli_type="codex",
                session_id=target["session_id"],
            )

            src = store.create_run(
                "task_dashboard",
                "子级04-前端体验（task-overview 页面交互）",
                "11111111-1111-1111-1111-111111111111",
                "并发同源回执",
                sender_type="agent",
                sender_id="主体-总控（合并与验收）",
                sender_name="主体-总控（合并与验收）",
                extra_meta={"callback_to": target, "task_path": "任务规划/子级04/任务/xx.md"},
            )
            meta = store.load_meta(src["id"]) or {}
            meta["status"] = "error"
            meta["error"] = "boom-same-source"
            meta["finishedAt"] = server._now_iso()
            store.save_meta(src["id"], meta)

            with mock.patch.dict(os.environ, {"CCB_CALLBACK_QUEUE_AGGREGATOR": "1"}, clear=False), \
                mock.patch("server._enqueue_run_execution"):
                def _dispatch_one() -> str:
                    m = store.load_meta(src["id"]) or {}
                    return server._dispatch_terminal_callback_for_run(store, src["id"], meta=m)

                with ThreadPoolExecutor(max_workers=3) as pool:
                    callback_run_ids = list(pool.map(lambda _x: _dispatch_one(), range(3)))

            non_empty_ids = {str(x or "").strip() for x in callback_run_ids if str(x or "").strip()}
            self.assertEqual(len(non_empty_ids), 1)
            callback_run_id = next(iter(non_empty_ids))

            callback_runs = []
            for m in store.list_runs(project_id="task_dashboard", session_id=target["session_id"], limit=200):
                if str(m.get("trigger_type") or "").strip().lower() != "callback_auto":
                    continue
                if str(m.get("source_run_id") or "").strip() != src["id"]:
                    continue
                callback_runs.append(m)
            self.assertEqual(len(callback_runs), 1)
            self.assertEqual(str(callback_runs[0].get("id") or "").strip(), callback_run_id)

            src_after = store.load_meta(src["id"]) or {}
            dispatches = src_after.get("callback_dispatches") or []
            self.assertEqual(len(dispatches), 1)
            self.assertEqual(str(dispatches[0].get("callback_run_id") or "").strip(), callback_run_id)

    def test_concurrent_same_source_callback_is_idempotent_without_queue_aggregator(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            target = {"channel_name": "主体-总控（合并与验收）", "session_id": "53535353-5353-5353-5353-535353535353"}
            session_store = server.SessionStore(Path(td))
            session_store.create_session(
                "task_dashboard",
                target["channel_name"],
                cli_type="codex",
                session_id=target["session_id"],
            )

            src = store.create_run(
                "task_dashboard",
                "子级02-CCB运行时（server-并发-安全-启动）",
                "11111111-1111-1111-1111-111111111111",
                "并发同源回执",
                sender_type="agent",
                sender_id="主体-总控（合并与验收）",
                sender_name="主体-总控（合并与验收）",
                extra_meta={"callback_to": target, "task_path": "任务规划/子级02/任务/xx.md"},
            )
            meta = store.load_meta(src["id"]) or {}
            meta["status"] = "done"
            meta["finishedAt"] = server._now_iso()
            meta["lastPreview"] = "执行完成"
            store.save_meta(src["id"], meta)

            with mock.patch("server._enqueue_run_execution"):
                def _dispatch_one() -> str:
                    m = store.load_meta(src["id"]) or {}
                    return server._dispatch_terminal_callback_for_run(store, src["id"], meta=m)

                with ThreadPoolExecutor(max_workers=4) as pool:
                    callback_run_ids = list(pool.map(lambda _x: _dispatch_one(), range(4)))

            non_empty_ids = {str(x or "").strip() for x in callback_run_ids if str(x or "").strip()}
            self.assertEqual(len(non_empty_ids), 1)
            callback_run_id = next(iter(non_empty_ids))

            callback_runs = []
            for m in store.list_runs(project_id="task_dashboard", session_id=target["session_id"], limit=200):
                if str(m.get("trigger_type") or "").strip().lower() != "callback_auto":
                    continue
                if str(m.get("source_run_id") or "").strip() != src["id"]:
                    continue
                callback_runs.append(m)
            self.assertEqual(len(callback_runs), 1)
            self.assertEqual(str(callback_runs[0].get("id") or "").strip(), callback_run_id)

            src_after = store.load_meta(src["id"]) or {}
            dispatches = src_after.get("callback_dispatches") or []
            self.assertEqual(len(dispatches), 1)
            self.assertEqual(str(dispatches[0].get("callback_run_id") or "").strip(), callback_run_id)

    def test_receipt_need_confirm_no_action_phrases_do_not_require_action(self) -> None:
        for phrase in ("无", "无需回执", "无需回复", "无需处理", "仅知悉", "知悉即可", "已知悉"):
            self.assertEqual(callback_runtime_module._classify_receipt_need_confirm(phrase), "no_action")
            self.assertFalse(
                callback_runtime_module._receipt_item_requires_action(
                    {
                        "event_type": "done",
                        "need_confirm": phrase,
                    }
                )
            )

        items = [
            {
                "source_run_id": "src-no-action",
                "callback_run_id": "cb-no-action",
                "event_type": "done",
                "need_confirm": "无需回执",
                "current_conclusion": "专项结构与联系方式已刷新",
                "need_peer": "请主负责确认是否进入验收/收口",
                "callback_at": "2026-03-25T23:03:44+08:00",
            }
        ]
        pending_actions = callback_runtime_module._build_receipt_pending_actions(items)
        self.assertEqual(pending_actions, [])
        rollup = callback_runtime_module._derive_receipt_rollup(items, pending_actions, host_run_id="host-no-action")
        self.assertEqual(rollup.get("pending_action_count"), 0)
        self.assertEqual(rollup.get("need_confirm_count"), 0)

    def test_receipt_need_confirm_action_phrases_and_error_states_still_require_action(self) -> None:
        for phrase in ("请确认", "需确认", "待确认", "请回复", "请处理", "请继续推进", "请继续执行", "请跟进"):
            self.assertEqual(callback_runtime_module._classify_receipt_need_confirm(phrase), "action")
            self.assertTrue(
                callback_runtime_module._receipt_item_requires_action(
                    {
                        "event_type": "done",
                        "need_confirm": phrase,
                    }
                )
            )

        confirm_items = [
            {
                "source_run_id": "src-confirm",
                "callback_run_id": "cb-confirm",
                "event_type": "done",
                "need_confirm": "请确认是否进入验收/收口",
                "current_conclusion": "已完成，可进入验收/收口",
                "need_peer": "请主负责确认是否进入验收/收口",
                "callback_at": "2026-03-25T23:10:00+08:00",
            }
        ]
        confirm_pending = callback_runtime_module._build_receipt_pending_actions(confirm_items)
        self.assertEqual(len(confirm_pending), 1)
        self.assertEqual(confirm_pending[0].get("title"), "请确认是否进入验收/收口")
        confirm_rollup = callback_runtime_module._derive_receipt_rollup(confirm_items, confirm_pending, host_run_id="host-confirm")
        self.assertEqual(confirm_rollup.get("pending_action_count"), 1)
        self.assertEqual(confirm_rollup.get("need_confirm_count"), 1)

        for event_type in ("error", "interrupted"):
            self.assertTrue(
                callback_runtime_module._receipt_item_requires_action(
                    {
                        "event_type": event_type,
                        "need_confirm": "无需回执",
                    }
                )
            )


if __name__ == "__main__":
    unittest.main()
