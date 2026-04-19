import json
import os
import tempfile
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote
from unittest import mock
from urllib import error as url_error
from urllib import request as url_request

import server
from task_dashboard.runtime.project_execution_context import build_project_execution_context
from task_dashboard.task_identity import render_task_front_matter


class SessionRuntimeStateApiTests(unittest.TestCase):
    def test_external_busy_probe_ignores_session_id_inside_message_text(self) -> None:
        with server._SESSION_EXTERNAL_BUSY_CACHE_LOCK:
            server._SESSION_EXTERNAL_BUSY_CACHE.clear()

        sid_target = "019cbbb5-c1db-7ed3-aa19-97febec83728"
        sid_real = "019c560f-62ba-7652-b714-d462b4335225"
        fake_rows = [
            (
                50101,
                f"/usr/local/bin/codex exec --json -o /tmp/xx.last.txt resume {sid_real} "
                f"[msg]session_id={sid_target}",
            )
        ]
        with mock.patch("server._scan_process_table_rows", return_value=fake_rows):
            res = server._probe_external_session_busy_batch_cached(
                [(sid_target, "codex"), (sid_real, "codex")]
            )
        self.assertFalse(bool((res.get(f"{sid_target}|codex") or (False, ""))[0]))
        self.assertTrue(bool((res.get(f"{sid_real}|codex") or (False, ""))[0]))

    def _start_server(self, base: Path):
        with server._SESSION_RUNTIME_INDEX_CACHE_LOCK:
            server._SESSION_RUNTIME_INDEX_CACHE.clear()
            server._SESSION_RUNTIME_INDEX_INFLIGHT.clear()
            server._SESSION_RUNTIME_INDEX_INVALIDATED_AT.clear()
        with server._SESSION_EXTERNAL_BUSY_CACHE_LOCK:
            server._SESSION_EXTERNAL_BUSY_CACHE.clear()
        from task_dashboard.runtime import session_routes

        with session_routes._SESSIONS_PAYLOAD_CACHE_LOCK:
            session_routes._SESSIONS_PAYLOAD_CACHE.clear()
            session_routes._SESSIONS_PAYLOAD_CACHE_INFLIGHT.clear()
            session_routes._SESSIONS_PAYLOAD_CACHE_INVALIDATED_AT.clear()
        server._clear_dashboard_cfg_cache()

        static_root = base / "static"
        static_root.mkdir(parents=True, exist_ok=True)
        (static_root / "index.html").write_text("ok", encoding="utf-8")

        run_store = server.RunStore(base / ".runs")
        session_store = server.SessionStore(base_dir=base)
        session_binding_store = server.SessionBindingStore(runs_dir=run_store.runs_dir)

        httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        httpd.static_root = static_root  # type: ignore[attr-defined]
        httpd.allow_root = static_root  # type: ignore[attr-defined]
        httpd.store = run_store  # type: ignore[attr-defined]
        httpd.session_store = session_store  # type: ignore[attr-defined]
        httpd.session_binding_store = session_binding_store  # type: ignore[attr-defined]
        httpd.http_log = base / ".run" / "test.http.log"  # type: ignore[attr-defined]
        httpd.scheduler = None  # type: ignore[attr-defined]
        httpd.project_scheduler_runtime = server.ProjectSchedulerRuntimeRegistry(store=run_store, session_store=session_store)  # type: ignore[attr-defined]
        httpd.task_push_runtime = server.TaskPushRuntimeRegistry(store=run_store, session_store=session_store)  # type: ignore[attr-defined]
        httpd.task_plan_runtime = server.TaskPlanRuntimeRegistry(  # type: ignore[attr-defined]
            store=run_store,
            session_store=session_store,
            task_push_runtime=httpd.task_push_runtime,
        )
        httpd.assist_request_runtime = server.AssistRequestRuntimeRegistry(store=run_store, session_store=session_store)  # type: ignore[attr-defined]
        return httpd, run_store, session_store

    def _create_run(self, store: server.RunStore, *, project_id: str, channel_name: str, session_id: str, status: str, queue_reason: str = "") -> str:
        run = store.create_run(project_id, channel_name, session_id, "msg", sender_type="user", sender_id="u", sender_name="U")
        rid = str(run.get("id") or "").strip()
        meta = store.load_meta(rid) or {}
        meta["status"] = status
        now = time.time()
        meta["createdAt"] = time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(now - 20))
        if status in {"running", "done", "error"}:
            meta["startedAt"] = time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(now - 15))
        if status in {"done", "error"}:
            meta["finishedAt"] = time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(now - 5))
        if queue_reason:
            meta["queueReason"] = queue_reason
        store.save_meta(rid, meta)
        return rid

    def test_get_sessions_includes_preview_summary_fields(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            httpd, store, session_store = self._start_server(base)
            pid = "task_dashboard"
            channel_name = "子级04-前端体验（task-overview 页面交互）"
            sid = "019c561c-8b6c-7c60-b66f-63096d1a4de7"
            session_store.create_session(pid, channel_name, cli_type="codex", session_id=sid)

            rid = self._create_run(
                store,
                project_id=pid,
                channel_name=channel_name,
                session_id=sid,
                status="done",
            )
            meta = store.load_meta(rid) or {}
            meta["messagePreview"] = "请继续推进"
            meta["lastPreview"] = "已完成首轮验收"
            meta["sender_type"] = "user"
            meta["sender_name"] = "我"
            store.save_meta(rid, meta)

            t = threading.Thread(target=httpd.serve_forever, daemon=True)
            t.start()
            port = int(httpd.server_address[1])
            try:
                with url_request.urlopen(
                    f"http://127.0.0.1:{port}/api/sessions?project_id={pid}",
                    timeout=3,
                ) as resp:
                    self.assertEqual(resp.status, 200)
                    body = json.loads(resp.read().decode("utf-8"))
                sessions = body.get("sessions") or []
                target = next((s for s in sessions if str(s.get("id") or "") == sid), {})
                self.assertTrue(bool(target))
                self.assertEqual(str(target.get("lastPreview") or ""), "已完成首轮验收")
                self.assertEqual(str(target.get("latestUserMsg") or ""), "请继续推进")
                self.assertEqual(str(target.get("latestAiMsg") or ""), "已完成首轮验收")
                self.assertEqual(str(target.get("lastSpeaker") or ""), "assistant")
                self.assertEqual(int(target.get("runCount") or 0), 1)
                self.assertTrue(str(target.get("lastActiveAt") or ""))
                self.assertEqual(str(target.get("session_display_state") or ""), "done")
                self.assertEqual(str(target.get("session_display_reason") or ""), "latest_run_summary:done")
                latest_summary = target.get("latest_run_summary") or {}
                self.assertEqual(str(latest_summary.get("run_id") or ""), rid)
                self.assertEqual(str(latest_summary.get("status") or ""), "done")
                self.assertEqual(str(latest_summary.get("preview") or ""), "已完成首轮验收")
                self.assertEqual(str(latest_summary.get("latest_user_msg") or ""), "请继续推进")
                self.assertEqual(str(latest_summary.get("latest_ai_msg") or ""), "已完成首轮验收")
            finally:
                httpd.shutdown()
                t.join(timeout=2)
                httpd.server_close()

    def test_get_sessions_and_detail_include_agent_display_fields(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            httpd, store, session_store = self._start_server(base)
            pid = "task_dashboard"
            channel_name = "子级02-CCB运行时（server-并发-安全-启动）"
            sid = "019d6211-1111-7111-8111-111111111111"
            session_store.create_session(
                pid,
                channel_name,
                cli_type="codex",
                session_id=sid,
                alias="服务开发-任务维度",
            )

            t = threading.Thread(target=httpd.serve_forever, daemon=True)
            t.start()
            port = int(httpd.server_address[1])
            try:
                with url_request.urlopen(
                    f"http://127.0.0.1:{port}/api/sessions?project_id={pid}",
                    timeout=3,
                ) as resp:
                    self.assertEqual(resp.status, 200)
                    body = json.loads(resp.read().decode("utf-8"))
                sessions = body.get("sessions") or []
                target = next((s for s in sessions if str(s.get("id") or "") == sid), {})
                self.assertTrue(bool(target))
                self.assertEqual(str(target.get("agent_display_name") or ""), "服务开发-任务维度")
                self.assertEqual(str(target.get("agent_display_name_source") or ""), "alias")
                self.assertEqual(str(target.get("agent_name_state") or ""), "resolved")
                self.assertEqual(str(target.get("agent_display_issue") or ""), "none")
                audit = body.get("agent_identity_audit") or {}
                self.assertEqual(int(audit.get("manual_backfill_required_count") or 0), 0)

                with url_request.urlopen(
                    f"http://127.0.0.1:{port}/api/sessions/{quote(sid)}",
                    timeout=3,
                ) as resp:
                    self.assertEqual(resp.status, 200)
                    detail = json.loads(resp.read().decode("utf-8"))
                self.assertEqual(str(detail.get("agent_display_name") or ""), "服务开发-任务维度")
                self.assertEqual(str(detail.get("agent_display_name_source") or ""), "alias")
                self.assertEqual(str(detail.get("agent_name_state") or ""), "resolved")
                self.assertEqual(str(detail.get("agent_display_issue") or ""), "none")
            finally:
                httpd.shutdown()
                t.join(timeout=2)
                httpd.server_close()

    def test_get_sessions_falls_back_to_archived_preview_summary(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            httpd, store, session_store = self._start_server(base)
            pid = "task_dashboard"
            channel_name = "子级04-前端体验（task-overview 页面交互）"
            sid = "019c561c-8b6c-7c60-b66f-63096d1a4de6"
            session_store.create_session(pid, channel_name, cli_type="codex", session_id=sid)

            rid = self._create_run(
                store,
                project_id=pid,
                channel_name=channel_name,
                session_id=sid,
                status="done",
            )
            meta = store.load_meta(rid) or {}
            meta["messagePreview"] = "旧用户消息"
            meta["lastPreview"] = "旧助手回复"
            meta["finishedAt"] = "2026-03-08T10:00:00+0800"
            meta["createdAt"] = "2026-03-08T09:59:00+0800"
            store.save_meta(rid, meta)

            bucket = "2026-03"
            src = store._paths(rid)
            dst_root = store.runs_dir / "archive" / bucket
            dst = {name: dst_root / f"{rid}.{name}.txt" for name in ("msg", "last", "log")}
            dst["meta"] = dst_root / f"{rid}.json"
            dst["meta"].parent.mkdir(parents=True, exist_ok=True)
            for key in ("meta", "msg", "last", "log"):
                if src[key].exists():
                    src[key].replace(dst[key])

            t = threading.Thread(target=httpd.serve_forever, daemon=True)
            t.start()
            port = int(httpd.server_address[1])
            try:
                with url_request.urlopen(
                    f"http://127.0.0.1:{port}/api/sessions?project_id={pid}",
                    timeout=3,
                ) as resp:
                    self.assertEqual(resp.status, 200)
                    body = json.loads(resp.read().decode("utf-8"))
                sessions = body.get("sessions") or []
                target = next((s for s in sessions if str(s.get("id") or "") == sid), {})
                self.assertTrue(bool(target))
                self.assertEqual(str(target.get("lastPreview") or ""), "旧助手回复")
                self.assertEqual(str(target.get("latestUserMsg") or ""), "旧用户消息")
                self.assertEqual(str(target.get("latestAiMsg") or ""), "旧助手回复")
                self.assertTrue(str(target.get("lastActiveAt") or ""))
            finally:
                httpd.shutdown()
                t.join(timeout=2)
                httpd.server_close()

    def test_get_sessions_includes_runtime_state(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            httpd, store, session_store = self._start_server(base)
            pid = "task_dashboard"
            channel_name = "子级04-前端体验（task-overview 页面交互）"
            sid = "019c561c-8b6c-7c60-b66f-63096d1a4de9"
            session_store.create_session(pid, channel_name, cli_type="codex", session_id=sid)

            queued_id = self._create_run(
                store,
                project_id=pid,
                channel_name=channel_name,
                session_id=sid,
                status="queued",
                queue_reason="session_busy_external",
            )

            t = threading.Thread(target=httpd.serve_forever, daemon=True)
            t.start()
            port = int(httpd.server_address[1])
            try:
                with url_request.urlopen(
                    f"http://127.0.0.1:{port}/api/sessions?project_id={pid}",
                    timeout=3,
                ) as resp:
                    self.assertEqual(resp.status, 200)
                    body = json.loads(resp.read().decode("utf-8"))
                sessions = body.get("sessions") or []
                target = next((s for s in sessions if str(s.get("id") or "") == sid), {})
                self.assertTrue(bool(target))
                rs = (target.get("runtime_state") or {})
                self.assertEqual(rs.get("internal_state"), "queued")
                self.assertTrue(bool(rs.get("external_busy")))
                self.assertEqual(rs.get("display_state"), "queued")
                self.assertEqual(rs.get("queued_run_id"), queued_id)
                self.assertEqual(int(rs.get("queue_depth") or 0), 1)
                self.assertTrue(str(rs.get("updated_at") or ""))
                self.assertEqual(str(target.get("session_display_state") or ""), "queued")
                self.assertEqual(str(target.get("session_display_reason") or ""), "runtime_state:queued")
                latest_summary = target.get("latest_run_summary") or {}
                self.assertEqual(str(latest_summary.get("run_id") or ""), queued_id)
                self.assertEqual(str(latest_summary.get("status") or ""), "queued")
            finally:
                httpd.shutdown()
                t.join(timeout=2)
                httpd.server_close()

    def test_get_sessions_and_detail_restore_agent_display_fields_and_identity_audit(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            httpd, store, session_store = self._start_server(base)
            pid = "task_dashboard"
            resolved_sid = "019d62e5-e8e5-7b42-be88-db6f0e735118"
            unresolved_sid = "ses_2f56e1533ffeoQi7mS0iK1kMkP"
            session_store.create_session(
                pid,
                "子级02-CCB运行时（server-并发-安全-启动）",
                cli_type="codex",
                alias="服务开发-任务维度",
                session_id=resolved_sid,
            )
            session_store.create_session(
                pid,
                "子级08-测试与验收（功能-回归-发布）",
                cli_type="opencode",
                session_id=unresolved_sid,
            )

            t = threading.Thread(target=httpd.serve_forever, daemon=True)
            t.start()
            port = int(httpd.server_address[1])
            try:
                with url_request.urlopen(
                    f"http://127.0.0.1:{port}/api/sessions?project_id={pid}",
                    timeout=3,
                ) as resp:
                    self.assertEqual(resp.status, 200)
                    body = json.loads(resp.read().decode("utf-8"))
                sessions = body.get("sessions") or []
                resolved = next((s for s in sessions if str(s.get("id") or "") == resolved_sid), {})
                unresolved = next((s for s in sessions if str(s.get("id") or "") == unresolved_sid), {})
                self.assertEqual(str(resolved.get("agent_display_name") or ""), "服务开发-任务维度")
                self.assertEqual(str(resolved.get("agent_display_name_source") or ""), "alias")
                self.assertEqual(str(resolved.get("agent_name_state") or ""), "resolved")
                self.assertEqual(str(resolved.get("agent_display_issue") or ""), "none")
                self.assertEqual(str(unresolved.get("agent_name_state") or ""), "identity_unresolved")
                self.assertEqual(str(unresolved.get("agent_display_issue") or ""), "missing_identity_source")
                audit = body.get("agent_identity_audit") or {}
                self.assertEqual(int(audit.get("manual_backfill_required_count") or 0), 1)

                with url_request.urlopen(
                    f"http://127.0.0.1:{port}/api/sessions/{quote(resolved_sid)}",
                    timeout=3,
                ) as resp:
                    self.assertEqual(resp.status, 200)
                    detail = json.loads(resp.read().decode("utf-8"))
                self.assertEqual(str(detail.get("agent_display_name") or ""), "服务开发-任务维度")
                self.assertEqual(str(detail.get("agent_display_name_source") or ""), "alias")
                self.assertEqual(str(detail.get("agent_name_state") or ""), "resolved")
                self.assertEqual(str(detail.get("agent_display_issue") or ""), "none")
            finally:
                httpd.shutdown()
                t.join(timeout=2)
                httpd.server_close()

    def test_get_sessions_includes_session_health_state_and_latest_effective_run_summary(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            httpd, store, session_store = self._start_server(base)
            pid = "task_dashboard"
            channel_name = "子级03-多CLI适配器（codex-claude-opencode）"
            healthy_sid = "019d10a7-3237-7543-816b-2320beabfff3"
            blocked_sid = "019d10a7-3237-7543-816b-2320beabfff4"
            session_store.create_session(pid, channel_name, cli_type="claude", session_id=healthy_sid)
            session_store.create_session(pid, channel_name, cli_type="claude", session_id=blocked_sid)

            success_id = self._create_run(
                store,
                project_id=pid,
                channel_name=channel_name,
                session_id=healthy_sid,
                status="done",
            )
            success_meta = store.load_meta(success_id) or {}
            success_meta["createdAt"] = "2026-04-01T10:52:17+0800"
            success_meta["finishedAt"] = "2026-04-01T10:52:30+0800"
            success_meta["lastPreview"] = "业务回执已完成，可进入下一步。"
            store.save_meta(success_id, success_meta)

            interrupted_id = self._create_run(
                store,
                project_id=pid,
                channel_name=channel_name,
                session_id=healthy_sid,
                status="error",
            )
            interrupted_meta = store.load_meta(interrupted_id) or {}
            interrupted_meta["createdAt"] = "2026-04-01T11:00:44+0800"
            interrupted_meta["finishedAt"] = "2026-04-01T11:00:52+0800"
            interrupted_meta["error"] = "run interrupted (server restarted or process exited)"
            store.save_meta(interrupted_id, interrupted_meta)

            recovery_id = self._create_run(
                store,
                project_id=pid,
                channel_name=channel_name,
                session_id=healthy_sid,
                status="done",
            )
            recovery_meta = store.load_meta(recovery_id) or {}
            recovery_meta["createdAt"] = "2026-04-01T11:11:30+0800"
            recovery_meta["finishedAt"] = "2026-04-01T11:11:36+0800"
            recovery_meta["trigger_type"] = "restart_recovery_summary"
            recovery_meta["message_kind"] = "restart_recovery_summary"
            recovery_meta["sender_type"] = "system"
            recovery_meta["lastPreview"] = "已恢复上次中断的队列，继续推进。"
            store.save_meta(recovery_id, recovery_meta)

            blocked_id = self._create_run(
                store,
                project_id=pid,
                channel_name=channel_name,
                session_id=blocked_sid,
                status="error",
            )
            blocked_meta = store.load_meta(blocked_id) or {}
            blocked_meta["createdAt"] = "2026-04-01T11:20:08+0800"
            blocked_meta["finishedAt"] = "2026-04-01T11:20:18+0800"
            blocked_meta["error"] = "No conversation found with session ID abc-123"
            store.save_meta(blocked_id, blocked_meta)

            t = threading.Thread(target=httpd.serve_forever, daemon=True)
            t.start()
            port = int(httpd.server_address[1])
            try:
                with url_request.urlopen(
                    f"http://127.0.0.1:{port}/api/sessions?project_id={pid}",
                    timeout=3,
                ) as resp:
                    self.assertEqual(resp.status, 200)
                    body = json.loads(resp.read().decode("utf-8"))
                sessions = body.get("sessions") or []
                healthy_row = next((s for s in sessions if str(s.get("id") or "") == healthy_sid), {})
                blocked_row = next((s for s in sessions if str(s.get("id") or "") == blocked_sid), {})
                self.assertEqual(str(healthy_row.get("session_health_state") or ""), "healthy")
                latest_effective = healthy_row.get("latest_effective_run_summary") or {}
                self.assertEqual(str(latest_effective.get("run_id") or ""), success_id)
                self.assertEqual(str(latest_effective.get("outcome_state") or ""), "success")
                self.assertEqual(str(latest_effective.get("preview") or ""), "业务回执已完成，可进入下一步。")
                latest_raw = healthy_row.get("latest_run_summary") or {}
                self.assertEqual(str(latest_raw.get("run_id") or ""), recovery_id)
                self.assertEqual(str(blocked_row.get("session_health_state") or ""), "blocked")
                self.assertFalse(bool(blocked_row.get("latest_effective_run_summary")))
            finally:
                httpd.shutdown()
                t.join(timeout=2)
                httpd.server_close()

    def test_get_sessions_runtime_index_invalidated_after_meta_write(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            httpd, store, session_store = self._start_server(base)
            pid = "task_dashboard"
            channel_name = "子级02-CCB运行时（server-并发-安全-启动）"
            sid = "019d231a-7de7-71d2-8af1-130329e4f535"
            session_store.create_session(pid, channel_name, cli_type="codex", session_id=sid)

            rid = self._create_run(
                store,
                project_id=pid,
                channel_name=channel_name,
                session_id=sid,
                status="queued",
            )

            t = threading.Thread(target=httpd.serve_forever, daemon=True)
            t.start()
            port = int(httpd.server_address[1])
            try:
                with mock.patch("task_dashboard.runtime.heartbeat_registry._session_runtime_index_cache_ttl_s", return_value=60.0):
                    with mock.patch(
                        "task_dashboard.runtime.heartbeat_registry._probe_external_session_busy_batch_cached",
                        return_value={},
                    ):
                        with url_request.urlopen(
                            f"http://127.0.0.1:{port}/api/sessions?project_id={pid}",
                            timeout=3,
                        ) as resp:
                            body = json.loads(resp.read().decode("utf-8"))
                        sessions = body.get("sessions") or []
                        target = next((s for s in sessions if str(s.get("id") or "") == sid), {})
                        self.assertEqual(str(target.get("session_display_state") or ""), "queued")

                        meta = store.load_meta(rid) or {}
                        meta["status"] = "done"
                        meta["queueReason"] = ""
                        meta["finishedAt"] = "2026-04-01T12:00:00+0800"
                        meta["lastPreview"] = "已切到 done"
                        store.save_meta(rid, meta)

                        with url_request.urlopen(
                            f"http://127.0.0.1:{port}/api/sessions?project_id={pid}",
                            timeout=3,
                        ) as resp:
                            body2 = json.loads(resp.read().decode("utf-8"))
                        sessions2 = body2.get("sessions") or []
                        target2 = next((s for s in sessions2 if str(s.get("id") or "") == sid), {})
                        self.assertEqual(str(target2.get("session_display_state") or ""), "done")
                        latest_summary = target2.get("latest_run_summary") or {}
                        self.assertEqual(str(latest_summary.get("status") or ""), "done")
                        self.assertEqual(str(latest_summary.get("preview") or ""), "已切到 done")
            finally:
                httpd.shutdown()
                t.join(timeout=2)
                httpd.server_close()

    def test_get_sessions_runtime_index_dedupes_concurrent_project_build(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            httpd, store, session_store = self._start_server(base)
            pid = "task_dashboard"
            channel_name = "子级02-CCB运行时（server-并发-安全-启动）"
            sid = "019d231a-7de7-71d2-8af1-130329e4f536"
            session_store.create_session(pid, channel_name, cli_type="codex", session_id=sid)
            self._create_run(
                store,
                project_id=pid,
                channel_name=channel_name,
                session_id=sid,
                status="done",
            )

            t = threading.Thread(target=httpd.serve_forever, daemon=True)
            t.start()
            port = int(httpd.server_address[1])
            try:
                original_list_runs = store.list_runs
                counter = {"project_calls": 0}
                counter_lock = threading.Lock()
                start_event = threading.Event()

                def slow_list_runs(*args, **kwargs):
                    if str(kwargs.get("project_id") or "").strip() == pid and not str(kwargs.get("session_id") or "").strip():
                        with counter_lock:
                            counter["project_calls"] += 1
                        time.sleep(0.25)
                    return original_list_runs(*args, **kwargs)

                results: list[int] = []

                def fetch_once() -> None:
                    start_event.wait()
                    with url_request.urlopen(
                        f"http://127.0.0.1:{port}/api/sessions?project_id={pid}",
                        timeout=5,
                    ) as resp:
                        body = json.loads(resp.read().decode("utf-8"))
                    results.append(len(body.get("sessions") or []))

                threads = [threading.Thread(target=fetch_once, daemon=True) for _ in range(3)]
                for th in threads:
                    th.start()
                with mock.patch.object(store, "list_runs", side_effect=slow_list_runs):
                    with mock.patch(
                        "task_dashboard.runtime.heartbeat_registry._probe_external_session_busy_batch_cached",
                        return_value={},
                    ):
                        start_event.set()
                        for th in threads:
                            th.join(timeout=3)

                self.assertEqual(results, [1, 1, 1])
                self.assertEqual(counter["project_calls"], 1)
            finally:
                httpd.shutdown()
                t.join(timeout=2)
                httpd.server_close()

    def test_get_session_detail_includes_task_tracking_and_next_owner(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            httpd, store, session_store = self._start_server(base)
            pid = "task_dashboard"
            channel_name = "子级02-CCB运行时（server-并发-安全-启动）"
            sid = "019d231a-7de7-71d2-8af1-130329e4f535"
            session_store.create_session(
                pid,
                channel_name,
                cli_type="codex",
                alias="服务开发",
                session_id=sid,
                worktree_root=str(base),
                workdir=str(base),
            )

            older_task = "任务规划/子级02-CCB运行时（server-并发-安全-启动）/任务/【待处理】【任务】会话内任务跟踪区最小真源补充.md"
            current_task = "任务规划/主体-总控（合并与验收）/任务/【进行中】【任务】任务功能收纳升级.md"
            older_task_file = base / older_task
            current_task_file = base / current_task
            older_task_file.parent.mkdir(parents=True, exist_ok=True)
            current_task_file.parent.mkdir(parents=True, exist_ok=True)
            registry_file = base / "任务规划" / "全局资源" / "task-harness-project-registry.task_dashboard.v1.json"
            registry_file.parent.mkdir(parents=True, exist_ok=True)
            registry_file.write_text(
                json.dumps(
                    {
                        "defaults": {"inherit_management_slot_to_tasks": True},
                        "management_slot": {
                            "default_members": [
                                {
                                    "name": "总控",
                                    "channel_name": "主体-总控（合并与验收）",
                                    "agent_alias": "总控",
                                    "session_id": "019d107a-a5ad-7912-8797-d23c58013449",
                                    "responsibility": "项目级督导",
                                }
                            ]
                        },
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            older_task_file.write_text(
                render_task_front_matter(task_id="task_20260328_older") +
                "# 【待处理】【任务】会话内任务跟踪区最小真源补充\n"
                "更新时间: 2026-03-28 21:50 +0800\n\n"
                "## 任务目标\n"
                "- 为会话内任务跟踪区补齐最小真源字段。\n\n"
                "## Harness责任位\n"
                "- 主负责位: `服务开发`\n"
                "- 协同位: `用户镜像`\n",
                encoding="utf-8",
            )
            current_task_file.write_text(
                render_task_front_matter(task_id="task_20260328_current") +
                "# 【进行中】【任务】任务功能收纳升级\n"
                "更新时间: 2026-03-28 22:00 +0800\n\n"
                "## 任务目标\n"
                "- 收敛任务状态与联调真源字段，保障本轮任务闭环。\n\n"
                "## Harness责任位\n"
                "- 主负责位: `服务开发`\n"
                "- 协同位: `用户镜像`\n"
                "- 管理位: 继承项目级默认管理位\n",
                encoding="utf-8",
            )

            older_run_id = self._create_run(
                store,
                project_id=pid,
                channel_name=channel_name,
                session_id=sid,
                status="done",
            )
            older_meta = store.load_meta(older_run_id) or {}
            older_meta["task_path"] = older_task
            older_meta["lastPreview"] = "会话内新增一条后端真源补充任务"
            older_meta["createdAt"] = "2026-03-28T21:50:00+0800"
            older_meta["finishedAt"] = "2026-03-28T21:56:00+0800"
            store.save_meta(older_run_id, older_meta)

            current_run_id = self._create_run(
                store,
                project_id=pid,
                channel_name=channel_name,
                session_id=sid,
                status="done",
            )
            current_meta = store.load_meta(current_run_id) or {}
            current_meta["task_path"] = current_task
            current_meta["lastPreview"] = "已冻结会话内任务跟踪区最小字段方向"
            current_meta["createdAt"] = "2026-03-28T22:00:00+0800"
            current_meta["finishedAt"] = "2026-03-28T22:10:00+0800"
            current_meta["receipt_items"] = [
                {
                    "source_run_id": "source-run-1",
                    "callback_run_id": "callback-run-1",
                    "callback_task": current_task,
                    "source_agent_name": "用户镜像",
                    "source_session_id": "019c8d4f-de2e-7e00-8d7c-fe501949fcad",
                    "callback_at": "2026-03-28T22:09:00+0800",
                    "need_confirm": "请确认",
                    "current_conclusion": "这版技术草案已可冻结",
                    "need_peer": "请确认按最小真源先行推进",
                    "event_type": "done",
                }
            ]
            current_meta["receipt_pending_actions"] = [
                {
                    "source_run_id": "source-run-1",
                    "action_kind": "confirm",
                    "action_text": "请确认按最小真源先行推进",
                    "callback_at": "2026-03-28T22:09:00+0800",
                }
            ]
            store.save_meta(current_run_id, current_meta)

            t = threading.Thread(target=httpd.serve_forever, daemon=True)
            t.start()
            port = int(httpd.server_address[1])
            try:
                detail_url = f"http://127.0.0.1:{port}/api/sessions/{sid}"
                with url_request.urlopen(detail_url, timeout=3) as resp:
                    self.assertEqual(resp.status, 200)
                    body = json.loads(resp.read().decode("utf-8"))

                tracking = body.get("task_tracking") or {}
                self.assertEqual(str(tracking.get("version") or ""), "v1.1")

                current_ref = tracking.get("current_task_ref") or {}
                self.assertEqual(str(current_ref.get("task_path") or ""), current_task)
                self.assertEqual(str(current_ref.get("task_id") or ""), "task_20260328_current")
                self.assertEqual(str(current_ref.get("parent_task_id") or ""), "")
                self.assertEqual(str(current_ref.get("relation") or ""), "current")
                self.assertEqual(
                    str(current_ref.get("task_summary_text") or ""),
                    "收敛任务状态与联调真源字段，保障本轮任务闭环。",
                )
                self.assertEqual(str((current_ref.get("main_owner") or {}).get("agent_name") or ""), "服务开发")
                self.assertEqual(len(current_ref.get("management_slot") or []), 1)
                self.assertEqual(
                    str(((current_ref.get("management_slot") or [{}])[0]).get("name") or ""),
                    "总控",
                )
                current_owner = current_ref.get("next_owner") or {}
                self.assertEqual(str(current_owner.get("session_id") or ""), sid)
                self.assertEqual(str(current_owner.get("state") or ""), "confirmed")
                self.assertEqual(str(current_owner.get("alias") or ""), "服务开发")

                refs = tracking.get("conversation_task_refs") or []
                refs_by_path = {
                    str(row.get("task_path") or ""): row
                    for row in refs
                    if isinstance(row, dict) and str(row.get("task_path") or "")
                }
                self.assertIn(current_task, refs_by_path)
                self.assertIn(older_task, refs_by_path)
                self.assertEqual(
                    str((refs_by_path.get(current_task) or {}).get("task_id") or ""),
                    "task_20260328_current",
                )
                self.assertEqual(
                    str((refs_by_path.get(older_task) or {}).get("task_id") or ""),
                    "task_20260328_older",
                )
                self.assertEqual(
                    str((refs_by_path.get(older_task) or {}).get("task_summary_text") or ""),
                    "为会话内任务跟踪区补齐最小真源字段。",
                )
                self.assertEqual(
                    str((((refs_by_path.get(older_task) or {}).get("main_owner") or {}).get("agent_name") or "")),
                    "服务开发",
                )
                self.assertEqual(len((refs_by_path.get(current_task) or {}).get("collaborators") or []), 1)
                older_owner = (refs_by_path.get(older_task) or {}).get("next_owner") or {}
                self.assertEqual(str(older_owner.get("state") or ""), "missing")

                actions = tracking.get("recent_task_actions") or []
                self.assertTrue(bool(actions))
                top_action = actions[0] if isinstance(actions[0], dict) else {}
                self.assertEqual(str(top_action.get("task_path") or ""), current_task)
                self.assertEqual(str(top_action.get("task_id") or ""), "task_20260328_current")
                self.assertEqual(str(top_action.get("action_kind") or ""), "confirm")
                self.assertEqual(str(top_action.get("status") or ""), "pending")
            finally:
                httpd.shutdown()
                t.join(timeout=2)
                httpd.server_close()

    def test_get_session_detail_prefers_channel_active_task_over_foreign_business_ref(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            httpd, store, session_store = self._start_server(base)
            pid = "task_dashboard"
            channel_name = "辅助04-原型设计与Demo可视化（静态数据填充-业务规格确认）"
            sid = "019d3f2e-0958-7a03-b639-ad13aaac6a2a"
            session_store.create_session(
                pid,
                channel_name,
                cli_type="codex",
                alias="产品策划-任务派发",
                session_id=sid,
                worktree_root=str(base),
                workdir=str(base),
            )

            current_task_file = (
                base
                / "任务规划"
                / channel_name
                / "任务"
                / "【进行中】【任务】20260331-Task Harness任务列表摘要与详情阅读层升级编排.md"
            )
            completed_channel_task_file = (
                base
                / "任务规划"
                / channel_name
                / "任务"
                / "【已完成】【任务】20260330-Task Harness正式定义文档化与工作交接准备.md"
            )
            foreign_task_file = (
                base
                / "任务规划"
                / "子级06-数据治理与契约（规格-校验-修复）"
                / "任务"
                / "【已完成】【任务】20260331-任务详情完整阅读层只读真源与契约边界评估.md"
            )
            current_task_file.parent.mkdir(parents=True, exist_ok=True)
            completed_channel_task_file.parent.mkdir(parents=True, exist_ok=True)
            foreign_task_file.parent.mkdir(parents=True, exist_ok=True)
            completed_channel_task_file.write_text(
                "# 【已完成】【任务】20260330-Task Harness正式定义文档化与工作交接准备\n"
                "更新时间: 2026-03-30 18:00 +0800\n\n"
                "## 任务目标\n"
                "- 沉淀 Task Harness 正式定义。\n",
                encoding="utf-8",
            )
            current_task_file.write_text(
                "# 【进行中】【任务】20260331-Task Harness任务列表摘要与详情阅读层升级编排\n"
                "更新时间: 2026-03-31 11:20 +0800\n\n"
                "## 任务目标\n"
                "- 升级任务列表摘要与详情阅读层，保障 QA 回看一致性。\n\n"
                "## Harness责任位\n"
                "### 主负责位\n"
                "- `产品策划-任务派发`\n"
                "- 通道：`辅助04-原型设计与Demo可视化（静态数据填充-业务规格确认）`\n"
                "- session_id：`019d3f2e-0958-7a03-b639-ad13aaac6a2a`\n"
                "- 职责：负责本任务编排。\n",
                encoding="utf-8",
            )
            foreign_task_file.write_text(
                "# 【已完成】【任务】20260331-任务详情完整阅读层只读真源与契约边界评估\n"
                "更新时间: 2026-03-31 10:50 +0800\n\n"
                "## 任务目标\n"
                "- 评估只读真源与契约边界。\n",
                encoding="utf-8",
            )

            run_id = self._create_run(
                store,
                project_id=pid,
                channel_name=channel_name,
                session_id=sid,
                status="done",
            )
            meta = store.load_meta(run_id) or {}
            meta["createdAt"] = "2026-03-31T11:10:00+0800"
            meta["finishedAt"] = "2026-03-31T11:18:00+0800"
            meta["business_refs"] = [
                {
                    "type": "任务",
                    "path": str(foreign_task_file.resolve()),
                    "title": "【已完成】【任务】20260331-任务详情完整阅读层只读真源与契约边界评估",
                }
            ]
            meta["lastPreview"] = "已完成详情阅读层边界评估。"
            store.save_meta(run_id, meta)

            t = threading.Thread(target=httpd.serve_forever, daemon=True)
            t.start()
            port = int(httpd.server_address[1])
            try:
                with url_request.urlopen(f"http://127.0.0.1:{port}/api/sessions/{sid}", timeout=3) as resp:
                    self.assertEqual(resp.status, 200)
                    body = json.loads(resp.read().decode("utf-8"))

                tracking = body.get("task_tracking") or {}
                current_ref = tracking.get("current_task_ref") or {}
                self.assertEqual(
                    str(current_ref.get("task_path") or ""),
                    str(current_task_file.relative_to(base)).replace("\\", "/"),
                )
                self.assertEqual(str(current_ref.get("relation") or ""), "current")
                self.assertEqual(
                    str(current_ref.get("task_summary_text") or ""),
                    "升级任务列表摘要与详情阅读层，保障 QA 回看一致性。",
                )
                self.assertEqual(
                    str(((current_ref.get("main_owner") or {}).get("agent_name") or "")),
                    "产品策划-任务派发",
                )

                refs = tracking.get("conversation_task_refs") or []
                refs_by_path = {
                    str(row.get("task_path") or ""): row
                    for row in refs
                    if isinstance(row, dict) and str(row.get("task_path") or "")
                }
                current_rel = str(current_task_file.relative_to(base)).replace("\\", "/")
                foreign_rel = str(foreign_task_file.relative_to(base)).replace("\\", "/")
                self.assertIn(current_rel, refs_by_path)
                self.assertIn(foreign_rel, refs_by_path)
                self.assertEqual(
                    str((refs_by_path.get(foreign_rel) or {}).get("source") or ""),
                    "business_ref",
                )
            finally:
                httpd.shutdown()
                t.join(timeout=2)
                httpd.server_close()

    def test_get_session_detail_resolves_moved_legacy_task_and_materializes_task_id(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            httpd, store, session_store = self._start_server(base)
            pid = "task_dashboard"
            channel_name = "子级08-测试与验收（功能-回归-发布）"
            sid = "019d2329-4e78-7152-bae2-fbcddadb32df"
            session_store.create_session(
                pid,
                channel_name,
                cli_type="codex",
                alias="测试验收",
                session_id=sid,
                worktree_root=str(base),
                workdir=str(base),
            )

            old_task = "任务规划/子级08-测试与验收（功能-回归-发布）/任务/【待开始】【任务】20260330-Task Harness责任位只读展示回归验收.md"
            current_task_file = (
                base
                / "任务规划"
                / "子级08-测试与验收（功能-回归-发布）"
                / "已完成"
                / "任务"
                / "【已完成】【任务】20260330-Task Harness责任位只读展示回归验收.md"
            )
            current_task_file.parent.mkdir(parents=True, exist_ok=True)
            current_task_file.write_text(
                "# 【已完成】【任务】20260330-Task Harness责任位只读展示回归验收\n"
                "更新时间: 2026-03-30 16:25 +0800\n\n"
                "## 任务目标\n"
                "- 验证责任位解析结果已进入页面只读展示。\n\n"
                "## Harness责任位\n"
                "- 主负责位：`测试验收`\n"
                "- 协同位：`产品策划-任务派发`\n",
                encoding="utf-8",
            )

            run_id = self._create_run(
                store,
                project_id=pid,
                channel_name=channel_name,
                session_id=sid,
                status="done",
            )
            meta = store.load_meta(run_id) or {}
            meta["task_path"] = old_task
            meta["lastPreview"] = "责任位只读展示回归验收已完成。"
            meta["createdAt"] = "2026-03-30T16:10:00+0800"
            meta["finishedAt"] = "2026-03-30T16:25:00+0800"
            store.save_meta(run_id, meta)

            t = threading.Thread(target=httpd.serve_forever, daemon=True)
            t.start()
            port = int(httpd.server_address[1])
            try:
                with url_request.urlopen(f"http://127.0.0.1:{port}/api/sessions/{sid}", timeout=3) as resp:
                    self.assertEqual(resp.status, 200)
                    body = json.loads(resp.read().decode("utf-8"))

                tracking = body.get("task_tracking") or {}
                current_ref = tracking.get("current_task_ref") or {}
                current_rel = str(current_task_file.relative_to(base)).replace("\\", "/")
                self.assertEqual(str(current_ref.get("task_path") or ""), current_rel)
                self.assertTrue(str(current_ref.get("task_id") or "").startswith("task_2026"))
                self.assertEqual(
                    str(current_ref.get("task_summary_text") or ""),
                    "验证责任位解析结果已进入页面只读展示。",
                )
                self.assertEqual(
                    str(((current_ref.get("main_owner") or {}).get("agent_name") or "")),
                    "测试验收",
                )

                refs = tracking.get("conversation_task_refs") or []
                self.assertTrue(bool(refs))
                ref_row = refs[0] if isinstance(refs[0], dict) else {}
                self.assertEqual(str(ref_row.get("task_path") or ""), current_rel)
                self.assertEqual(str(ref_row.get("task_id") or ""), str(current_ref.get("task_id") or ""))

                actions = tracking.get("recent_task_actions") or []
                self.assertTrue(bool(actions))
                top_action = actions[0] if isinstance(actions[0], dict) else {}
                self.assertEqual(str(top_action.get("task_path") or ""), current_rel)
                self.assertEqual(str(top_action.get("task_id") or ""), str(current_ref.get("task_id") or ""))

                updated_text = current_task_file.read_text(encoding="utf-8")
                self.assertIn("task_id:", updated_text)
            finally:
                httpd.shutdown()
                t.join(timeout=2)
                httpd.server_close()

    def test_get_session_detail_promotes_session_primary_task_when_seed_task_is_terminal(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            httpd, store, session_store = self._start_server(base)
            pid = "task_dashboard"
            channel_name = "子级08-测试与验收（功能-回归-发布）"
            sid = "019d2329-4e78-7152-bae2-fbcddadb32df"
            session_store.create_session(
                pid,
                channel_name,
                cli_type="codex",
                alias="测试验收",
                session_id=sid,
                worktree_root=str(base),
                workdir=str(base),
            )

            current_task = "任务规划/子级08-测试与验收（功能-回归-发布）/已完成/任务/【已完成】【任务】20260330-Task Harness责任位只读展示回归验收.md"
            newer_task = "任务规划/子级08-测试与验收（功能-回归-发布）/任务/【待开始】【任务】20260401-task_id稳定身份与跨状态路径解耦-最小回归验收.md"
            current_task_file = base / current_task
            newer_task_file = base / newer_task
            current_task_file.parent.mkdir(parents=True, exist_ok=True)
            newer_task_file.parent.mkdir(parents=True, exist_ok=True)
            current_task_file.write_text(
                render_task_front_matter(task_id="task_20260401_current") +
                "# 【已完成】【任务】20260330-Task Harness责任位只读展示回归验收\n"
                "更新时间: 2026-03-30 16:25 +0800\n\n"
                "## 任务目标\n"
                "- 验证责任位解析结果已进入页面只读展示。\n",
                encoding="utf-8",
            )
            newer_task_file.write_text(
                render_task_front_matter(task_id="task_20260401_newer") +
                "# 【待开始】【任务】20260401-task_id稳定身份与跨状态路径解耦-最小回归验收\n"
                "更新时间: 2026-04-01 01:30 +0800\n\n"
                "## 任务目标\n"
                "- 只做最小回归验收。\n",
                encoding="utf-8",
            )

            current_run_id = self._create_run(
                store,
                project_id=pid,
                channel_name=channel_name,
                session_id=sid,
                status="done",
            )
            current_meta = store.load_meta(current_run_id) or {}
            current_meta["task_path"] = current_task
            current_meta["lastPreview"] = "责任位只读展示回归验收已完成。"
            current_meta["createdAt"] = "2026-03-30T16:10:00+0800"
            current_meta["finishedAt"] = "2026-03-30T16:25:00+0800"
            store.save_meta(current_run_id, current_meta)

            newer_run_id = self._create_run(
                store,
                project_id=pid,
                channel_name=channel_name,
                session_id=sid,
                status="done",
            )
            newer_meta = store.load_meta(newer_run_id) or {}
            newer_meta["createdAt"] = "2026-04-01T01:44:35+0800"
            newer_meta["finishedAt"] = "2026-04-01T01:47:29+0800"
            newer_meta["business_refs"] = [
                {
                    "type": "任务",
                    "path": str(newer_task_file.resolve()),
                    "task_id": "task_20260401_newer",
                    "title": "【待开始】【任务】20260401-task_id稳定身份与跨状态路径解耦-最小回归验收",
                }
            ]
            newer_meta["lastPreview"] = "最新回归结论已更新。"
            store.save_meta(newer_run_id, newer_meta)

            t = threading.Thread(target=httpd.serve_forever, daemon=True)
            t.start()
            port = int(httpd.server_address[1])
            try:
                with url_request.urlopen(f"http://127.0.0.1:{port}/api/sessions/{sid}", timeout=3) as resp:
                    self.assertEqual(resp.status, 200)
                    body = json.loads(resp.read().decode("utf-8"))

                tracking = body.get("task_tracking") or {}
                current_ref = tracking.get("current_task_ref") or {}
                self.assertEqual(str(current_ref.get("task_id") or ""), "task_20260401_newer")
                self.assertEqual(str(current_ref.get("task_path") or ""), newer_task)
                self.assertEqual(str(current_ref.get("source") or ""), "business_ref")

                actions = tracking.get("recent_task_actions") or []
                self.assertTrue(bool(actions))
                top_action = actions[0] if isinstance(actions[0], dict) else {}
                self.assertEqual(str(top_action.get("task_id") or ""), "task_20260401_newer")
                self.assertEqual(str(top_action.get("source_run_id") or ""), newer_run_id)
            finally:
                httpd.shutdown()
                t.join(timeout=2)
                httpd.server_close()

    def test_get_run_detail_includes_queue_reason_and_blocked_by(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            httpd, store, session_store = self._start_server(base)
            pid = "task_dashboard"
            channel_name = "子级04-前端体验（task-overview 页面交互）"
            sid = "019c561c-8b6c-7c60-b66f-63096d1a4de9"
            session_store.create_session(pid, channel_name, cli_type="codex", session_id=sid)

            running_id = self._create_run(
                store,
                project_id=pid,
                channel_name=channel_name,
                session_id=sid,
                status="running",
            )
            queued_id = self._create_run(
                store,
                project_id=pid,
                channel_name=channel_name,
                session_id=sid,
                status="queued",
            )

            t = threading.Thread(target=httpd.serve_forever, daemon=True)
            t.start()
            port = int(httpd.server_address[1])
            try:
                with url_request.urlopen(
                    f"http://127.0.0.1:{port}/api/codex/run/{queued_id}",
                    timeout=3,
                ) as resp:
                    self.assertEqual(resp.status, 200)
                    body = json.loads(resp.read().decode("utf-8"))
                run = body.get("run") or {}
                self.assertEqual(run.get("display_state"), "queued")
                self.assertEqual(run.get("queue_reason"), "session_serial")
                self.assertEqual(run.get("blocked_by_run_id"), running_id)
            finally:
                httpd.shutdown()
                t.join(timeout=2)
                httpd.server_close()

    def test_get_sessions_batch_external_busy_probe_reuses_cache(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            httpd, store, session_store = self._start_server(base)
            pid = "task_dashboard"
            channel_name = "子级04-前端体验（task-overview 页面交互）"
            sid1 = "019c561c-8b6c-7c60-b66f-63096d1a4de9"
            sid2 = "019c561b-9b41-7632-a667-19c1a5249b41"
            session_store.create_session(pid, channel_name, cli_type="codex", session_id=sid1)
            session_store.create_session(pid, channel_name, cli_type="codex", session_id=sid2)

            fake_rows = [
                (
                    12345,
                    f"/usr/local/bin/codex exec --json -o /tmp/{sid1}.last.txt resume {sid1}",
                )
            ]
            t = threading.Thread(target=httpd.serve_forever, daemon=True)
            t.start()
            port = int(httpd.server_address[1])
            try:
                with mock.patch("server._scan_process_table_rows", return_value=fake_rows) as scan_once:
                    with url_request.urlopen(
                        f"http://127.0.0.1:{port}/api/sessions?project_id={pid}",
                        timeout=3,
                    ) as resp1:
                        body1 = json.loads(resp1.read().decode("utf-8"))
                    with url_request.urlopen(
                        f"http://127.0.0.1:{port}/api/sessions?project_id={pid}",
                        timeout=3,
                    ) as resp2:
                        body2 = json.loads(resp2.read().decode("utf-8"))

                self.assertEqual(scan_once.call_count, 1)
                sessions1 = body1.get("sessions") or []
                sessions2 = body2.get("sessions") or []
                row1_1 = next((s for s in sessions1 if str(s.get("id") or "") == sid1), {})
                row1_2 = next((s for s in sessions2 if str(s.get("id") or "") == sid1), {})
                row2_1 = next((s for s in sessions1 if str(s.get("id") or "") == sid2), {})
                self.assertTrue(bool((row1_1.get("runtime_state") or {}).get("external_busy")))
                self.assertEqual((row1_1.get("runtime_state") or {}).get("display_state"), "external_busy")
                self.assertEqual(str(row1_1.get("session_display_state") or ""), "external_busy")
                self.assertEqual(str(row1_1.get("session_display_reason") or ""), "runtime_state:external_busy")
                self.assertTrue(bool((row1_2.get("runtime_state") or {}).get("external_busy")))
                self.assertFalse(bool((row2_1.get("runtime_state") or {}).get("external_busy")))
            finally:
                httpd.shutdown()
                t.join(timeout=2)
                httpd.server_close()

    def test_get_sessions_prefers_active_run_progress_over_newer_queued_run(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            httpd, store, session_store = self._start_server(base)
            pid = "culture"
            channel_name = "诊断看板05-AI组织文化"
            sid = "019bdbdb-8e74-7bd3-8cf8-4ce701d4c431"
            session_store.create_session(pid, channel_name, cli_type="codex", session_id=sid)

            running_id = self._create_run(
                store,
                project_id=pid,
                channel_name=channel_name,
                session_id=sid,
                status="running",
            )
            running_meta = store.load_meta(running_id) or {}
            running_meta["createdAt"] = "2026-03-30T15:29:52+0800"
            running_meta["startedAt"] = "2026-03-30T15:29:53+0800"
            running_meta["lastProgressAt"] = "2026-03-30T16:23:24+0800"
            running_meta["messagePreview"] = "请继续分析 culture 智能看板 AI 适应力"
            running_meta["lastPreview"] = ""
            running_meta["partialPreview"] = "当前 active run 仍在持续推进员工体验模块接线。"
            running_meta["processRows"] = [
                {"text": "当前 active run 仍在持续推进员工体验模块接线。", "at": "2026-03-30T16:23:23+0800"},
            ]
            store.save_meta(running_id, running_meta)

            queued_id = self._create_run(
                store,
                project_id=pid,
                channel_name=channel_name,
                session_id=sid,
                status="queued",
            )
            queued_meta = store.load_meta(queued_id) or {}
            queued_meta["createdAt"] = "2026-03-30T16:01:11+0800"
            queued_meta["messagePreview"] = "这是一条后续串行排队消息"
            queued_meta["lastPreview"] = "旧协作消息摘要"
            store.save_meta(queued_id, queued_meta)

            t = threading.Thread(target=httpd.serve_forever, daemon=True)
            t.start()
            port = int(httpd.server_address[1])
            try:
                with url_request.urlopen(
                    f"http://127.0.0.1:{port}/api/sessions?project_id={pid}",
                    timeout=3,
                ) as resp:
                    self.assertEqual(resp.status, 200)
                    body = json.loads(resp.read().decode("utf-8"))
                sessions = body.get("sessions") or []
                target = next((s for s in sessions if str(s.get("id") or "") == sid), {})
                self.assertTrue(bool(target))
                rs = (target.get("runtime_state") or {})
                self.assertEqual(str(rs.get("display_state") or ""), "running")
                self.assertEqual(str(rs.get("active_run_id") or ""), running_id)
                self.assertEqual(str(rs.get("queued_run_id") or ""), queued_id)
                self.assertEqual(str(rs.get("updated_at") or ""), "2026-03-30T16:23:24+0800")
                latest_summary = target.get("latest_run_summary") or {}
                self.assertEqual(str(latest_summary.get("run_id") or ""), running_id)
                self.assertEqual(str(latest_summary.get("status") or ""), "running")
                self.assertEqual(str(latest_summary.get("updated_at") or ""), "2026-03-30T16:23:24+0800")
                self.assertEqual(
                    str(latest_summary.get("preview") or ""),
                    "当前 active run 仍在持续推进员工体验模块接线。",
                )
                self.assertEqual(
                    str(target.get("lastPreview") or ""),
                    "当前 active run 仍在持续推进员工体验模块接线。",
                )
            finally:
                httpd.shutdown()
                t.join(timeout=2)
                httpd.server_close()

    def test_get_sessions_ignores_terminal_run_bound_orphan_process(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            httpd, store, session_store = self._start_server(base)
            pid = "task_dashboard"
            channel_name = "子级04-前端体验（task-overview 页面交互）"
            sid = "019d25ee-9ae5-7121-af80-36fd6a3a6724"
            session_store.create_session(pid, channel_name, cli_type="codex", session_id=sid)

            rid = self._create_run(
                store,
                project_id=pid,
                channel_name=channel_name,
                session_id=sid,
                status="error",
            )
            meta = store.load_meta(rid) or {}
            meta["error"] = "run interrupted (server restarted or process exited)"
            meta["lastPreview"] = "本轮已异常收口"
            store.save_meta(rid, meta)

            fake_rows = [
                (
                    44364,
                    f"/usr/local/bin/codex exec --json -o /tmp/{rid}.last.txt resume {sid} continue",
                )
            ]

            t = threading.Thread(target=httpd.serve_forever, daemon=True)
            t.start()
            port = int(httpd.server_address[1])
            try:
                with mock.patch("server._scan_process_table_rows", return_value=fake_rows):
                    with url_request.urlopen(
                        f"http://127.0.0.1:{port}/api/sessions?project_id={pid}",
                        timeout=3,
                    ) as resp:
                        self.assertEqual(resp.status, 200)
                        body = json.loads(resp.read().decode("utf-8"))
                sessions = body.get("sessions") or []
                target = next((s for s in sessions if str(s.get("id") or "") == sid), {})
                self.assertTrue(bool(target))
                rs = (target.get("runtime_state") or {})
                self.assertEqual(rs.get("internal_state"), "error")
                self.assertFalse(bool(rs.get("external_busy")))
                self.assertEqual(rs.get("display_state"), "error")
                self.assertEqual(str(target.get("session_display_state") or ""), "error")
                self.assertEqual(str(target.get("session_display_reason") or ""), "runtime_state:error")
            finally:
                httpd.shutdown()
                t.join(timeout=2)
                httpd.server_close()

    def test_put_session_missing_session_returns_404_without_registry_materialization(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            httpd, _store, session_store = self._start_server(base)
            sid = "019c561c-8b6c-7c60-b66f-63096d1a4de9"

            t = threading.Thread(target=httpd.serve_forever, daemon=True)
            t.start()
            port = int(httpd.server_address[1])
            try:
                req = url_request.Request(
                    f"http://127.0.0.1:{port}/api/sessions/{sid}",
                    data=json.dumps({"alias": "已更新别名"}).encode("utf-8"),
                    method="PUT",
                    headers={"Content-Type": "application/json"},
                )
                with self.assertRaises(url_error.HTTPError) as cm:
                    url_request.urlopen(req, timeout=3)
                self.assertEqual(cm.exception.code, 404)
                stored = session_store.get_session(sid)
                self.assertIsNone(stored)
            finally:
                httpd.shutdown()
                t.join(timeout=2)
                httpd.server_close()

    def test_delete_session_returns_deleted_and_missing_404(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            httpd, _store, session_store = self._start_server(base)
            pid = "task_dashboard"
            channel_name = "子级02-CCB运行时（server-并发-安全-启动）"
            sid = "019c561c-8b6c-7c60-b66f-63096d1a4ded"
            session_store.create_session(pid, channel_name, cli_type="codex", session_id=sid)

            t = threading.Thread(target=httpd.serve_forever, daemon=True)
            t.start()
            port = int(httpd.server_address[1])
            try:
                req = url_request.Request(
                    f"http://127.0.0.1:{port}/api/sessions/{sid}",
                    method="DELETE",
                )
                with url_request.urlopen(req, timeout=3) as resp:
                    self.assertEqual(resp.status, 200)
                    body = json.loads(resp.read().decode("utf-8"))
                self.assertTrue(bool(body.get("deleted")))
                stored = session_store.get_session(sid) or {}
                self.assertTrue(bool(stored.get("is_deleted")))
                self.assertEqual(str(stored.get("deleted_reason") or ""), "api_delete_session")
            finally:
                httpd.shutdown()
                t.join(timeout=2)
                httpd.server_close()

    def test_get_session_includes_work_context_fields(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            httpd, _store, session_store = self._start_server(base)
            httpd.environment_name = "refactor"  # type: ignore[attr-defined]
            httpd.worktree_root = base / "task-dashboard-refactor"  # type: ignore[attr-defined]
            pid = "task_dashboard"
            channel_name = "子级01-Build引擎（扫描-解析-聚合-渲染）"
            sid = "019c561c-8b6c-7c60-b66f-63096d1a4de8"
            session_store.create_session(
                pid,
                channel_name,
                cli_type="codex",
                session_id=sid,
                environment="refactor",
                worktree_root=str(base / "task-dashboard-refactor"),
                workdir=str(base / "task-dashboard-refactor" / "project"),
                branch="refactor/p1-work-context",
            )

            t = threading.Thread(target=httpd.serve_forever, daemon=True)
            t.start()
            port = int(httpd.server_address[1])
            try:
                with url_request.urlopen(
                    f"http://127.0.0.1:{port}/api/sessions/{sid}",
                    timeout=3,
                ) as resp:
                    self.assertEqual(resp.status, 200)
                    body = json.loads(resp.read().decode("utf-8"))
                self.assertEqual(body.get("environment"), "refactor")
                self.assertEqual(body.get("worktree_root"), str(base / "task-dashboard-refactor"))
                self.assertEqual(body.get("workdir"), str(base / "task-dashboard-refactor" / "project"))
                self.assertEqual(body.get("branch"), "refactor/p1-work-context")
            finally:
                httpd.shutdown()
                t.join(timeout=2)
                httpd.server_close()

    def test_session_views_include_project_execution_context(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            httpd, _store, session_store = self._start_server(base)
            httpd.environment_name = "refactor"  # type: ignore[attr-defined]
            httpd.worktree_root = base / "task-dashboard-refactor"  # type: ignore[attr-defined]
            pid = "task_dashboard"
            channel_name = "子级01-Build引擎（扫描-解析-聚合-渲染）"
            sid = "019c561c-8b6c-7c60-b66f-63096d1a4dff"
            session_store.create_session(
                pid,
                channel_name,
                cli_type="codex",
                session_id=sid,
                environment="stable",
                worktree_root=str(base / "task-dashboard-stable"),
                workdir=str(base / "task-dashboard-stable" / "project"),
                branch="release/stable",
                context_binding_state="session",
            )

            t = threading.Thread(target=httpd.serve_forever, daemon=True)
            t.start()
            port = int(httpd.server_address[1])
            try:
                with mock.patch.object(server, "_load_project_execution_context", return_value={}):
                    with url_request.urlopen(
                        f"http://127.0.0.1:{port}/api/sessions/{sid}",
                        timeout=3,
                    ) as resp:
                        self.assertEqual(resp.status, 200)
                        detail = json.loads(resp.read().decode("utf-8"))
                    detail_ctx = detail.get("project_execution_context") or {}
                    self.assertEqual(
                        ((detail_ctx.get("target") or {}).get("environment") or ""),
                        "stable",
                    )
                    self.assertEqual(
                        ((detail_ctx.get("source") or {}).get("environment") or ""),
                        "refactor",
                    )
                    self.assertTrue(bool((detail_ctx.get("override") or {}).get("applied")))
                    override_fields = set((detail_ctx.get("override") or {}).get("fields") or [])
                    self.assertTrue({"environment", "worktree_root"} <= override_fields)
                    self.assertEqual(detail_ctx.get("context_source"), "server_default")
                    self.assertEqual((detail_ctx.get("override") or {}).get("source"), "session")

                    with url_request.urlopen(
                        f"http://127.0.0.1:{port}/api/channel-sessions?project_id={pid}&channel_name="
                        + quote(channel_name)
                        + "&include_deleted=1",
                        timeout=3,
                    ) as resp:
                        self.assertEqual(resp.status, 200)
                        payload = json.loads(resp.read().decode("utf-8"))
                    row = next(
                        (item for item in (payload.get("sessions") or []) if str(item.get("id") or "") == sid),
                        {},
                    )
                    row_ctx = row.get("project_execution_context") or {}
                    self.assertEqual(
                        ((row_ctx.get("target") or {}).get("session_id") or ""),
                        sid,
                    )
                    self.assertEqual(
                        ((row_ctx.get("source") or {}).get("worktree_root") or ""),
                        str(base / "task-dashboard-refactor"),
                    )
                    self.assertEqual(row_ctx.get("context_source"), "server_default")
                    self.assertEqual((row_ctx.get("override") or {}).get("source"), "session")
            finally:
                httpd.shutdown()
                t.join(timeout=2)
                httpd.server_close()

    def test_put_session_supports_work_context_fields(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            httpd, _store, session_store = self._start_server(base)
            httpd.environment_name = "refactor"  # type: ignore[attr-defined]
            httpd.worktree_root = base / "task-dashboard-refactor"  # type: ignore[attr-defined]
            pid = "task_dashboard"
            channel_name = "子级01-Build引擎（扫描-解析-聚合-渲染）"
            sid = "019c561c-8b6c-7c60-b66f-63096d1a4de7"
            session_store.create_session(pid, channel_name, cli_type="codex", session_id=sid, environment="refactor")

            t = threading.Thread(target=httpd.serve_forever, daemon=True)
            t.start()
            port = int(httpd.server_address[1])
            try:
                req = url_request.Request(
                    f"http://127.0.0.1:{port}/api/sessions/{sid}",
                    data=json.dumps(
                        {
                            "environment": "refactor",
                            "worktree_root": str(base / "task-dashboard-refactor"),
                            "workdir": str(base / "task-dashboard-refactor" / "project"),
                            "branch": "refactor/p1-work-context",
                        }
                    ).encode("utf-8"),
                    method="PUT",
                    headers={"Content-Type": "application/json"},
                )
                with url_request.urlopen(req, timeout=3) as resp:
                    self.assertEqual(resp.status, 200)
                    body = json.loads(resp.read().decode("utf-8"))
                session = body.get("session") or {}
                self.assertEqual(session.get("environment"), "refactor")
                self.assertEqual(session.get("worktree_root"), str(base / "task-dashboard-refactor"))
                self.assertEqual(session.get("workdir"), str(base / "task-dashboard-refactor" / "project"))
                self.assertEqual(session.get("branch"), "refactor/p1-work-context")
            finally:
                httpd.shutdown()
                t.join(timeout=2)
                httpd.server_close()

    def test_post_sessions_v2_persists_requested_work_context_and_child_role(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            custom_workdir = base / "task-dashboard-refactor" / "agents" / "child-01"
            custom_workdir.mkdir(parents=True, exist_ok=True)
            custom_root = base / "task-dashboard-refactor"
            custom_root.mkdir(parents=True, exist_ok=True)
            httpd, _store, session_store = self._start_server(base)
            httpd.environment_name = "refactor"  # type: ignore[attr-defined]
            httpd.worktree_root = custom_root  # type: ignore[attr-defined]
            pid = "task_dashboard"
            channel_name = "子级01-Build引擎（扫描-解析-聚合-渲染）"
            primary_sid = "019cd16f-6107-77d0-925a-fa79f94e9f40"
            session_store.create_session(
                pid,
                channel_name,
                cli_type="codex",
                session_id=primary_sid,
                environment="refactor",
                worktree_root=str(custom_root),
                workdir=str(base / "task-dashboard-refactor" / "main"),
                branch="refactor/main",
                session_role="primary",
                purpose="main",
                reuse_strategy="reuse_or_create",
                is_primary=True,
            )

            t = threading.Thread(target=httpd.serve_forever, daemon=True)
            t.start()
            port = int(httpd.server_address[1])
            try:
                new_sid = "019cd16f-6107-77d0-925a-fa79f94e9f41"
                with mock.patch(
                    "server.create_cli_session",
                    return_value={
                        "ok": True,
                        "sessionId": new_sid,
                        "sessionPath": "/tmp/fake-session.json",
                        "workdir": str(custom_workdir),
                    },
                ) as create_cli:
                    req = url_request.Request(
                        f"http://127.0.0.1:{port}/api/sessions",
                        data=json.dumps(
                            {
                                "project_id": pid,
                                "channel_name": channel_name,
                                "cli_type": "codex",
                                "model": "gpt-5.3-codex",
                                "reasoning_effort": "high",
                                "alias": "辅助01A-迁移补录",
                                "environment": "refactor",
                                "worktree_root": str(custom_root),
                                "workdir": str(custom_workdir),
                                "branch": "refactor/session-v2",
                                "session_role": "child",
                                "purpose": "task_with_receipt",
                                "reuse_strategy": "create_new",
                                "set_as_primary": False,
                                "first_message": "请回复 OK",
                            }
                        ).encode("utf-8"),
                        method="POST",
                        headers={"Content-Type": "application/json"},
                    )
                    with url_request.urlopen(req, timeout=3) as resp:
                        self.assertEqual(resp.status, 200)
                        body = json.loads(resp.read().decode("utf-8"))
                self.assertEqual(create_cli.call_args.kwargs.get("workdir"), custom_workdir.resolve())
                session = body.get("session") or {}
                self.assertEqual(session.get("id"), new_sid)
                self.assertEqual(session.get("environment"), "refactor")
                self.assertEqual(Path(str(session.get("worktree_root") or "")).resolve(), custom_root.resolve())
                self.assertEqual(Path(str(session.get("workdir") or "")).resolve(), custom_workdir.resolve())
                self.assertEqual(session.get("branch"), "refactor/session-v2")
                self.assertEqual(session.get("session_role"), "child")
                self.assertEqual(session.get("purpose"), "task_with_receipt")
                self.assertEqual(session.get("reuse_strategy"), "create_new")
                self.assertFalse(bool(session.get("is_primary")))

                stored = session_store.get_session(new_sid) or {}
                old_primary = session_store.get_session(primary_sid) or {}
                self.assertEqual(Path(str(stored.get("workdir") or "")).resolve(), custom_workdir.resolve())
                self.assertEqual(stored.get("session_role"), "child")
                self.assertEqual(stored.get("purpose"), "task_with_receipt")
                self.assertEqual(stored.get("reuse_strategy"), "create_new")
                self.assertFalse(bool(stored.get("is_primary")))
                self.assertTrue(bool(old_primary.get("is_primary")))
            finally:
                httpd.shutdown()
                t.join(timeout=2)
                httpd.server_close()

    def test_post_sessions_v2_can_promote_new_primary(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            custom_root = base / "task-dashboard-refactor"
            custom_root.mkdir(parents=True, exist_ok=True)
            workdir_a = custom_root / "main"
            workdir_b = custom_root / "takeover"
            workdir_a.mkdir(parents=True, exist_ok=True)
            workdir_b.mkdir(parents=True, exist_ok=True)
            httpd, _store, session_store = self._start_server(base)
            httpd.environment_name = "refactor"  # type: ignore[attr-defined]
            httpd.worktree_root = custom_root  # type: ignore[attr-defined]
            pid = "task_dashboard"
            channel_name = "子级02-CCB运行时（server-并发-安全-启动）"
            old_sid = "019cd16f-6107-77d0-925a-fa79f94e9f30"
            session_store.create_session(
                pid,
                channel_name,
                cli_type="codex",
                session_id=old_sid,
                environment="refactor",
                worktree_root=str(custom_root),
                workdir=str(workdir_a),
                branch="refactor/old",
                session_role="primary",
                is_primary=True,
            )

            t = threading.Thread(target=httpd.serve_forever, daemon=True)
            t.start()
            port = int(httpd.server_address[1])
            try:
                new_sid = "019cd16f-6107-77d0-925a-fa79f94e9f42"
                with mock.patch(
                    "server.create_cli_session",
                    return_value={
                        "ok": True,
                        "sessionId": new_sid,
                        "sessionPath": "/tmp/fake-session-promote.json",
                        "workdir": str(workdir_b),
                    },
                ):
                    req = url_request.Request(
                        f"http://127.0.0.1:{port}/api/sessions",
                        data=json.dumps(
                            {
                                "project_id": pid,
                                "channel_name": channel_name,
                                "cli_type": "codex",
                                "environment": "refactor",
                                "worktree_root": str(custom_root),
                                "workdir": str(workdir_b),
                                "session_role": "primary",
                                "set_as_primary": True,
                            }
                        ).encode("utf-8"),
                        method="POST",
                        headers={"Content-Type": "application/json"},
                    )
                    with url_request.urlopen(req, timeout=3) as resp:
                        self.assertEqual(resp.status, 200)
                        body = json.loads(resp.read().decode("utf-8"))
                session = body.get("session") or {}
                self.assertTrue(bool(session.get("is_primary")))
                self.assertEqual(session.get("session_role"), "primary")
                old_row = session_store.get_session(old_sid) or {}
                new_row = session_store.get_session(new_sid) or {}
                self.assertFalse(bool(old_row.get("is_primary")))
                self.assertTrue(bool(new_row.get("is_primary")))
            finally:
                httpd.shutdown()
                t.join(timeout=2)
                httpd.server_close()

    def test_put_session_stable_context_requires_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            httpd, _store, session_store = self._start_server(base)
            pid = "task_dashboard"
            channel_name = "子级01-Build引擎（扫描-解析-聚合-渲染）"
            sid = "019c561c-8b6c-7c60-b66f-63096d1a4de6"
            session_store.create_session(
                pid,
                channel_name,
                cli_type="codex",
                session_id=sid,
                environment="stable",
            )

            t = threading.Thread(target=httpd.serve_forever, daemon=True)
            t.start()
            port = int(httpd.server_address[1])
            try:
                req = url_request.Request(
                    f"http://127.0.0.1:{port}/api/sessions/{sid}",
                    data=json.dumps({"workdir": str(base / 'changed')}).encode("utf-8"),
                    method="PUT",
                    headers={"Content-Type": "application/json"},
                )
                with self.assertRaises(url_error.HTTPError) as cm:
                    url_request.urlopen(req, timeout=3)
                self.assertEqual(cm.exception.code, 409)
                body = json.loads(cm.exception.read().decode("utf-8"))
                self.assertEqual(body.get("error_code"), "stable_write_confirmation_required")
            finally:
                httpd.shutdown()
                t.join(timeout=2)
                httpd.server_close()

    def test_put_session_stable_unchanged_context_does_not_require_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            httpd, _store, session_store = self._start_server(base)
            httpd.environment_name = "stable"  # type: ignore[attr-defined]
            httpd.worktree_root = base  # type: ignore[attr-defined]
            pid = "task_dashboard"
            channel_name = "子级01-Build引擎（扫描-解析-聚合-渲染）"
            sid = "019c561c-8b6c-7c60-b66f-63096d1a4de4"
            session_store.create_session(
                pid,
                channel_name,
                cli_type="codex",
                session_id=sid,
                environment="stable",
                worktree_root=str(base),
                workdir=str(base / "stable"),
                branch="release/test",
            )

            t = threading.Thread(target=httpd.serve_forever, daemon=True)
            t.start()
            port = int(httpd.server_address[1])
            try:
                req = url_request.Request(
                    f"http://127.0.0.1:{port}/api/sessions/{sid}",
                    data=json.dumps(
                        {
                            "channel_name": channel_name,
                            "environment": "stable",
                            "worktree_root": str(base),
                            "workdir": str(base / "stable"),
                            "branch": "release/test",
                        }
                    ).encode("utf-8"),
                    method="PUT",
                    headers={"Content-Type": "application/json"},
                )
                with url_request.urlopen(req, timeout=3) as resp:
                    self.assertEqual(resp.status, 200)
                    body = json.loads(resp.read().decode("utf-8"))
                session = body.get("session") or {}
                self.assertEqual(session.get("environment"), "stable")
                self.assertEqual(session.get("worktree_root"), str(base))
                self.assertEqual(session.get("workdir"), str(base / "stable"))
                self.assertEqual(session.get("branch"), "release/test")
            finally:
                httpd.shutdown()
                t.join(timeout=2)
                httpd.server_close()

    def test_put_session_stable_effective_context_does_not_require_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            httpd, _store, session_store = self._start_server(base)
            httpd.environment_name = "stable"  # type: ignore[attr-defined]
            httpd.worktree_root = base  # type: ignore[attr-defined]
            pid = "task_dashboard"
            channel_name = "辅助01-项目结构治理（配置-目录-契约-迁移）"
            sid = "019cb671-e4ef-7461-8246-1058f80b3488"
            session_store.create_session(
                pid,
                channel_name,
                cli_type="codex",
                session_id=sid,
                environment="stable",
            )

            t = threading.Thread(target=httpd.serve_forever, daemon=True)
            t.start()
            port = int(httpd.server_address[1])
            try:
                with mock.patch.object(
                    server,
                    "_load_project_execution_context",
                    return_value={
                        "project_id": pid,
                        "environment": "stable",
                        "worktree_root": str(base),
                        "workdir": str(base / "stable"),
                        "branch": "",
                        "configured": False,
                        "context_source": "server_default",
                    },
                ):
                    req = url_request.Request(
                        f"http://127.0.0.1:{port}/api/sessions/{sid}",
                        data=json.dumps(
                            {
                                "channel_name": channel_name,
                                "environment": "stable",
                                "worktree_root": str(base),
                            }
                        ).encode("utf-8"),
                        method="PUT",
                        headers={"Content-Type": "application/json"},
                    )
                    with url_request.urlopen(req, timeout=3) as resp:
                        self.assertEqual(resp.status, 200)
                        body = json.loads(resp.read().decode("utf-8"))
                    session = body.get("session") or {}
                    self.assertEqual(session.get("environment"), "stable")
                    self.assertEqual(session.get("worktree_root"), str(base))
            finally:
                httpd.shutdown()
                t.join(timeout=2)
                httpd.server_close()

    def test_put_session_stable_context_accepts_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            httpd, _store, session_store = self._start_server(base)
            pid = "task_dashboard"
            channel_name = "子级01-Build引擎（扫描-解析-聚合-渲染）"
            sid = "019c561c-8b6c-7c60-b66f-63096d1a4de5"
            session_store.create_session(
                pid,
                channel_name,
                cli_type="codex",
                session_id=sid,
                environment="stable",
            )

            t = threading.Thread(target=httpd.serve_forever, daemon=True)
            t.start()
            port = int(httpd.server_address[1])
            try:
                req = url_request.Request(
                    f"http://127.0.0.1:{port}/api/sessions/{sid}",
                    data=json.dumps(
                        {
                            "workdir": str(base / "changed"),
                            "allow_stable_write": True,
                        }
                    ).encode("utf-8"),
                    method="PUT",
                    headers={"Content-Type": "application/json"},
                )
                with url_request.urlopen(req, timeout=3) as resp:
                    self.assertEqual(resp.status, 200)
                    body = json.loads(resp.read().decode("utf-8"))
                session = body.get("session") or {}
                self.assertEqual(session.get("workdir"), str(base / "changed"))
            finally:
                httpd.shutdown()
                t.join(timeout=2)
                httpd.server_close()

    def test_channel_session_management_supports_primary_and_soft_delete(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            httpd, _store, session_store = self._start_server(base)
            pid = "task_dashboard"
            channel_name = "子级04-前端体验（task-overview 页面交互）"
            sid1 = "019c561c-8b6c-7c60-b66f-63096d1a4de1"
            sid2 = "019c561c-8b6c-7c60-b66f-63096d1a4de2"
            session_store.create_session(pid, channel_name, cli_type="codex", session_id=sid1)
            session_store.create_session(pid, channel_name, cli_type="codex", session_id=sid2)

            t = threading.Thread(target=httpd.serve_forever, daemon=True)
            t.start()
            port = int(httpd.server_address[1])
            try:
                req = url_request.Request(
                    f"http://127.0.0.1:{port}/api/channel-sessions/manage",
                    data=json.dumps(
                        {
                            "project_id": pid,
                            "channel_name": channel_name,
                            "primary_session_id": sid2,
                            "updates": [
                                {"session_id": sid1, "is_deleted": True, "deleted_reason": "archive"},
                                {"session_id": sid2, "is_deleted": False},
                            ],
                        }
                    ).encode("utf-8"),
                    method="POST",
                    headers={"Content-Type": "application/json"},
                )
                with url_request.urlopen(req, timeout=3) as resp:
                    self.assertEqual(resp.status, 200)
                    body = json.loads(resp.read().decode("utf-8"))
                self.assertEqual(body.get("primary_session_id"), sid2)

                with url_request.urlopen(
                    f"http://127.0.0.1:{port}/api/channel-sessions?project_id={pid}&channel_name="
                    + quote(channel_name)
                    + "&include_deleted=1",
                    timeout=3,
                ) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
                self.assertEqual(payload.get("primary_session_id"), sid2)
                rows = payload.get("sessions") or []
                row1 = next((row for row in rows if str(row.get("id") or "") == sid1), {})
                row2 = next((row for row in rows if str(row.get("id") or "") == sid2), {})
                self.assertTrue(bool(row1.get("is_deleted")))
                self.assertTrue(bool(row2.get("is_primary")))

                with url_request.urlopen(
                    f"http://127.0.0.1:{port}/api/sessions?project_id={pid}&channel_name="
                    + quote(channel_name),
                    timeout=3,
                ) as resp:
                    visible = (json.loads(resp.read().decode("utf-8")).get("sessions") or [])
                self.assertEqual(len(visible), 1)
                self.assertEqual(str((visible[0] or {}).get("id") or ""), sid2)
                self.assertTrue(bool((visible[0] or {}).get("is_primary")))
            finally:
                httpd.shutdown()
                t.join(timeout=2)
                httpd.server_close()

    def test_post_session_bindings_save_and_delete(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            httpd, _store, _session_store = self._start_server(base)
            pid = "task_dashboard"
            channel_name = "子级02-CCB运行时（server-并发-安全-启动）"
            sid = "019c561c-8b6c-7c60-b66f-63096d1a4dea"

            t = threading.Thread(target=httpd.serve_forever, daemon=True)
            t.start()
            port = int(httpd.server_address[1])
            try:
                save_req = url_request.Request(
                    f"http://127.0.0.1:{port}/api/sessions/bindings/save",
                    data=json.dumps(
                        {
                            "sessionId": sid,
                            "projectId": pid,
                            "channelName": channel_name,
                            "cliType": "codex",
                        }
                    ).encode("utf-8"),
                    method="POST",
                    headers={"Content-Type": "application/json"},
                )
                with url_request.urlopen(save_req, timeout=3) as resp:
                    self.assertEqual(resp.status, 200)
                    save_body = json.loads(resp.read().decode("utf-8"))
                binding = save_body.get("binding") or {}
                self.assertEqual(binding.get("sessionId"), sid)
                self.assertEqual(binding.get("projectId"), pid)
                self.assertEqual(binding.get("channelName"), channel_name)
                self.assertTrue(bool(save_body.get("compatibility_entry")))
                self.assertEqual(str(save_body.get("entry_role") or ""), "compatibility_management")
                self.assertTrue(bool(httpd.session_binding_store.get_binding(sid)))  # type: ignore[attr-defined]

                delete_req = url_request.Request(
                    f"http://127.0.0.1:{port}/api/sessions/bindings/delete",
                    data=json.dumps({"sessionId": sid}).encode("utf-8"),
                    method="POST",
                    headers={"Content-Type": "application/json"},
                )
                with url_request.urlopen(delete_req, timeout=3) as resp:
                    self.assertEqual(resp.status, 200)
                    delete_body = json.loads(resp.read().decode("utf-8"))
                self.assertTrue(bool(delete_body.get("deleted")))
                self.assertTrue(bool(delete_body.get("compatibility_entry")))
                self.assertEqual(str(delete_body.get("entry_role") or ""), "compatibility_management")
                self.assertIsNone(httpd.session_binding_store.get_binding(sid))  # type: ignore[attr-defined]
            finally:
                httpd.shutdown()
                t.join(timeout=2)
                httpd.server_close()

    def test_delete_session_soft_deletes_session_and_clears_binding(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            httpd, _store, session_store = self._start_server(base)
            pid = "task_dashboard"
            channel_name = "辅助05-督办PMO（排期-巡查-催办-升级）"
            sid1 = "019ca897-461e-7d11-b077-819b27128de8"
            sid2 = "019d9a93-f1c1-77e2-a613-e1e793d6a11a"
            session_store.create_session(
                pid,
                channel_name,
                cli_type="codex",
                session_id=sid1,
                session_role="primary",
                is_primary=True,
            )
            session_store.create_session(
                pid,
                channel_name,
                cli_type="codex",
                session_id=sid2,
            )
            httpd.session_binding_store.save_binding(sid1, pid, channel_name, "codex")  # type: ignore[attr-defined]

            t = threading.Thread(target=httpd.serve_forever, daemon=True)
            t.start()
            port = int(httpd.server_address[1])
            try:
                delete_req = url_request.Request(
                    f"http://127.0.0.1:{port}/api/sessions/{sid1}",
                    method="DELETE",
                )
                with url_request.urlopen(delete_req, timeout=3) as resp:
                    self.assertEqual(resp.status, 200)
                    body = json.loads(resp.read().decode("utf-8"))
                self.assertTrue(bool(body.get("deleted")))
                self.assertTrue(bool(body.get("soft_deleted")))
                self.assertTrue(bool(body.get("binding_deleted")))

                with url_request.urlopen(
                    f"http://127.0.0.1:{port}/api/channel-sessions?project_id={pid}&channel_name="
                    + quote(channel_name)
                    + "&include_deleted=1",
                    timeout=3,
                ) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
                rows = payload.get("sessions") or []
                old_row = next((row for row in rows if str(row.get("id") or "") == sid1), {})
                new_row = next((row for row in rows if str(row.get("id") or "") == sid2), {})
                self.assertTrue(bool(old_row.get("is_deleted")))
                self.assertEqual(str(old_row.get("deleted_reason") or ""), "api_delete_session")
                self.assertTrue(str(old_row.get("deleted_at") or ""))
                self.assertTrue(bool(new_row.get("is_primary")))

                with url_request.urlopen(
                    f"http://127.0.0.1:{port}/api/sessions?project_id={pid}&channel_name="
                    + quote(channel_name),
                    timeout=3,
                ) as resp:
                    visible = (json.loads(resp.read().decode("utf-8")).get("sessions") or [])
                self.assertEqual([str((row or {}).get("id") or "") for row in visible], [sid2])
                self.assertIsNone(httpd.session_binding_store.get_binding(sid1))  # type: ignore[attr-defined]
            finally:
                httpd.shutdown()
                t.join(timeout=2)
                httpd.server_close()

    def test_post_session_bindings_accepts_opencode_session_id(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            httpd, _store, _session_store = self._start_server(base)
            pid = "task_dashboard"
            channel_name = "子级08-测试与验收（功能-回归-发布）"
            sid = "ses_2f5d8b87cffekbHfJtB5IXE0DX"

            t = threading.Thread(target=httpd.serve_forever, daemon=True)
            t.start()
            port = int(httpd.server_address[1])
            try:
                save_req = url_request.Request(
                    f"http://127.0.0.1:{port}/api/sessions/bindings/save",
                    data=json.dumps(
                        {
                            "sessionId": sid,
                            "projectId": pid,
                            "channelName": channel_name,
                            "cliType": "opencode",
                        }
                    ).encode("utf-8"),
                    method="POST",
                    headers={"Content-Type": "application/json"},
                )
                with url_request.urlopen(save_req, timeout=3) as resp:
                    self.assertEqual(resp.status, 200)
                    save_body = json.loads(resp.read().decode("utf-8"))
                binding = save_body.get("binding") or {}
                self.assertEqual(binding.get("sessionId"), sid)
                self.assertEqual(binding.get("cliType"), "opencode")

                with url_request.urlopen(
                    f"http://127.0.0.1:{port}/api/sessions/binding/{quote(sid)}",
                    timeout=3,
                ) as resp:
                    self.assertEqual(resp.status, 200)
                    detail = json.loads(resp.read().decode("utf-8"))
                self.assertEqual(str(detail.get("sessionId") or ""), sid)
                self.assertEqual(str(detail.get("cliType") or ""), "opencode")
                self.assertTrue(bool(detail.get("compatibility_entry")))
                self.assertEqual(str(detail.get("entry_role") or ""), "compatibility_management")
            finally:
                httpd.shutdown()
                t.join(timeout=2)
                httpd.server_close()

    def test_session_bindings_include_project_execution_context(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            httpd, _store, session_store = self._start_server(base)
            httpd.environment_name = "refactor"  # type: ignore[attr-defined]
            httpd.worktree_root = base / "task-dashboard-refactor"  # type: ignore[attr-defined]
            pid = "task_dashboard"
            channel_name = "子级02-CCB运行时（server-并发-安全-启动）"
            sid = "019c561c-8b6c-7c60-b66f-63096d1a4df0"
            session_store.create_session(
                pid,
                channel_name,
                cli_type="codex",
                session_id=sid,
                environment="stable",
                worktree_root=str(base / "task-dashboard-stable"),
                workdir=str(base / "task-dashboard-stable" / "ops"),
                branch="release/stable",
                context_binding_state="override",
            )

            t = threading.Thread(target=httpd.serve_forever, daemon=True)
            t.start()
            port = int(httpd.server_address[1])
            try:
                with mock.patch.object(server, "_load_project_execution_context", return_value={}):
                    save_req = url_request.Request(
                        f"http://127.0.0.1:{port}/api/sessions/bindings/save",
                        data=json.dumps(
                            {
                                "sessionId": sid,
                                "projectId": pid,
                                "channelName": channel_name,
                                "cliType": "codex",
                            }
                        ).encode("utf-8"),
                        method="POST",
                        headers={"Content-Type": "application/json"},
                    )
                    with url_request.urlopen(save_req, timeout=3) as resp:
                        self.assertEqual(resp.status, 200)

                    with url_request.urlopen(
                        f"http://127.0.0.1:{port}/api/sessions/bindings",
                        timeout=3,
                    ) as resp:
                        self.assertEqual(resp.status, 200)
                        body = json.loads(resp.read().decode("utf-8"))
                    self.assertTrue(bool(body.get("compatibility_entry")))
                    self.assertEqual(str(body.get("entry_role") or ""), "compatibility_management")
                    binding = next(
                        (item for item in (body.get("bindings") or []) if str(item.get("sessionId") or "") == sid),
                        {},
                    )
                    self.assertTrue(bool(binding.get("compatibility_entry")))
                    self.assertEqual(str(binding.get("entry_role") or ""), "compatibility_management")
                    binding_ctx = binding.get("project_execution_context") or {}
                    self.assertEqual(
                        ((binding_ctx.get("target") or {}).get("project_id") or ""),
                        pid,
                    )
                    self.assertEqual(
                        ((binding_ctx.get("target") or {}).get("environment") or ""),
                        "stable",
                    )
                    self.assertEqual(
                        ((binding_ctx.get("source") or {}).get("environment") or ""),
                        "refactor",
                    )
                    self.assertTrue(bool((binding_ctx.get("override") or {}).get("applied")))
                    self.assertEqual(binding_ctx.get("context_source"), "server_default")
                    self.assertEqual((binding_ctx.get("override") or {}).get("source"), "session")

                    with url_request.urlopen(
                        f"http://127.0.0.1:{port}/api/sessions/binding/{sid}",
                        timeout=3,
                    ) as resp:
                        self.assertEqual(resp.status, 200)
                        detail = json.loads(resp.read().decode("utf-8"))
                    detail_ctx = detail.get("project_execution_context") or {}
                    self.assertEqual(
                        ((detail_ctx.get("target") or {}).get("session_id") or ""),
                        sid,
                    )
                    self.assertEqual(
                        ((detail_ctx.get("source") or {}).get("worktree_root") or ""),
                        str(base / "task-dashboard-refactor"),
                    )
            finally:
                httpd.shutdown()
                t.join(timeout=2)
                httpd.server_close()

    def test_project_config_update_refreshes_session_execution_context_views(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            config_path = base / "config.toml"
            stable_root = base / "task-dashboard-stable"
            stable_workdir = stable_root / "project"
            refactor_root = base / "task-dashboard-refactor"
            refactor_workdir = refactor_root / "project"
            stable_workdir.mkdir(parents=True, exist_ok=True)
            refactor_workdir.mkdir(parents=True, exist_ok=True)
            config_path.write_text(
                f"""
version = 1

[[projects]]
id = "task_dashboard"
name = "Task Dashboard"

[projects.execution_context]
environment = "stable"
worktree_root = "{stable_root}"
workdir = "{stable_workdir}"
branch = "release/stable"
""".lstrip(),
                encoding="utf-8",
            )

            httpd, _store, session_store = self._start_server(base)
            pid = "task_dashboard"
            channel_name = "子级02-CCB运行时（server-并发-安全-启动）"
            sid = "019c561c-8b6c-7c60-b66f-63096d1a4df1"
            project_context = build_project_execution_context(
                target={
                    "project_id": pid,
                    "channel_name": channel_name,
                    "session_id": sid,
                    "environment": "stable",
                    "worktree_root": str(stable_root),
                    "workdir": str(stable_workdir),
                    "branch": "release/stable",
                },
                source={
                    "project_id": pid,
                    "environment": "stable",
                    "worktree_root": str(stable_root),
                    "workdir": str(stable_workdir),
                    "branch": "release/stable",
                },
                context_source="project",
                override_fields=[],
                override_source="",
            )
            session_store.create_session(
                pid,
                channel_name,
                cli_type="codex",
                session_id=sid,
                environment="stable",
                worktree_root=str(stable_root),
                workdir=str(stable_workdir),
                branch="release/stable",
                context_binding_state="project",
                project_execution_context=project_context,
            )

            t = threading.Thread(target=httpd.serve_forever, daemon=True)
            t.start()
            port = int(httpd.server_address[1])
            with mock.patch.dict(
                os.environ,
                {
                    "TASK_DASHBOARD_CONFIG": str(config_path),
                    "TASK_DASHBOARD_WITH_LOCAL_CONFIG": "0",
                },
                clear=False,
            ):
                server._clear_dashboard_cfg_cache()
                try:
                    save_req = url_request.Request(
                        f"http://127.0.0.1:{port}/api/sessions/bindings/save",
                        data=json.dumps(
                            {
                                "sessionId": sid,
                                "projectId": pid,
                                "channelName": channel_name,
                                "cliType": "codex",
                            }
                        ).encode("utf-8"),
                        method="POST",
                        headers={"Content-Type": "application/json"},
                    )
                    with url_request.urlopen(save_req, timeout=3) as resp:
                        self.assertEqual(resp.status, 200)

                    with url_request.urlopen(
                        f"http://127.0.0.1:{port}/api/sessions/{sid}",
                        timeout=3,
                    ) as resp:
                        self.assertEqual(resp.status, 200)
                        before_detail = json.loads(resp.read().decode("utf-8"))
                    before_ctx = before_detail.get("project_execution_context") or {}
                    self.assertEqual(((before_ctx.get("source") or {}).get("environment") or ""), "stable")
                    self.assertEqual(((before_ctx.get("target") or {}).get("worktree_root") or ""), str(stable_root))
                    self.assertFalse(bool((before_ctx.get("override") or {}).get("applied")))

                    update_req = url_request.Request(
                        f"http://127.0.0.1:{port}/api/projects/{pid}/config",
                        data=json.dumps(
                            {
                                "execution_context": {
                                    "environment": "refactor",
                                    "worktree_root": str(refactor_root),
                                    "workdir": str(refactor_workdir),
                                    "branch": "refactor/project-context",
                                }
                            }
                        ).encode("utf-8"),
                        method="POST",
                        headers={"Content-Type": "application/json"},
                    )
                    with url_request.urlopen(update_req, timeout=3) as resp:
                        self.assertEqual(resp.status, 200)

                    with url_request.urlopen(
                        f"http://127.0.0.1:{port}/api/sessions/{sid}",
                        timeout=3,
                    ) as resp:
                        self.assertEqual(resp.status, 200)
                        after_detail = json.loads(resp.read().decode("utf-8"))
                    after_ctx = after_detail.get("project_execution_context") or {}
                    self.assertEqual(((after_ctx.get("source") or {}).get("environment") or ""), "refactor")
                    self.assertEqual(
                        ((after_ctx.get("source") or {}).get("worktree_root") or ""),
                        str(refactor_root),
                    )
                    self.assertEqual(
                        ((after_ctx.get("target") or {}).get("workdir") or ""),
                        str(refactor_workdir),
                    )
                    self.assertEqual(
                        ((after_ctx.get("target") or {}).get("branch") or ""),
                        "refactor/project-context",
                    )
                    self.assertFalse(bool((after_ctx.get("override") or {}).get("applied")))
                    self.assertEqual(after_ctx.get("context_source"), "project")

                    with url_request.urlopen(
                        f"http://127.0.0.1:{port}/api/sessions/bindings",
                        timeout=3,
                    ) as resp:
                        self.assertEqual(resp.status, 200)
                        bindings_body = json.loads(resp.read().decode("utf-8"))
                    binding = next(
                        (item for item in (bindings_body.get("bindings") or []) if str(item.get("sessionId") or "") == sid),
                        {},
                    )
                    binding_ctx = binding.get("project_execution_context") or {}
                    self.assertEqual(
                        ((binding_ctx.get("source") or {}).get("environment") or ""),
                        "refactor",
                    )
                    self.assertEqual(
                        ((binding_ctx.get("target") or {}).get("worktree_root") or ""),
                        str(refactor_root),
                    )
                    self.assertFalse(bool((binding_ctx.get("override") or {}).get("applied")))
                finally:
                    httpd.shutdown()
                    t.join(timeout=2)
                    httpd.server_close()

    def test_post_sessions_dedup_keeps_latest_session(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            httpd, _store, session_store = self._start_server(base)
            pid = "task_dashboard"
            channel_name = "子级02-CCB运行时（server-并发-安全-启动）"
            sid1 = "019c561c-8b6c-7c60-b66f-63096d1a4deb"
            sid2 = "019c561c-8b6c-7c60-b66f-63096d1a4dec"
            session_store.create_session(pid, channel_name, cli_type="codex", session_id=sid1)
            session_store.create_session(pid, channel_name, cli_type="codex", session_id=sid2)
            session_store.update_session(sid1, last_used_at="2026-03-08T10:00:00Z")
            session_store.update_session(sid2, last_used_at="2026-03-08T10:05:00Z")

            t = threading.Thread(target=httpd.serve_forever, daemon=True)
            t.start()
            port = int(httpd.server_address[1])
            try:
                req = url_request.Request(
                    f"http://127.0.0.1:{port}/api/sessions/dedup",
                    data=json.dumps(
                        {
                            "project_id": pid,
                            "channel_name": channel_name,
                            "strategy": "latest",
                        }
                    ).encode("utf-8"),
                    method="POST",
                    headers={"Content-Type": "application/json"},
                )
                with url_request.urlopen(req, timeout=3) as resp:
                    self.assertEqual(resp.status, 200)
                    body = json.loads(resp.read().decode("utf-8"))
                result = body.get("result") or {}
                self.assertEqual(result.get("kept_session_id"), sid2)
                self.assertEqual(result.get("removed_count"), 1)
                self.assertIn(sid1, result.get("removed_session_ids") or [])

                visible = session_store.list_sessions(pid, channel_name)
                self.assertEqual(len(visible), 1)
                self.assertEqual(str((visible[0] or {}).get("id") or ""), sid2)
            finally:
                httpd.shutdown()
                t.join(timeout=2)
                httpd.server_close()

    def test_sessions_api_rewrites_stale_project_execution_target_without_override(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            httpd, _store, _session_store = self._start_server(base)
            pid = "task_dashboard"
            channel_name = "子级02-CCB运行时（server-并发-安全-启动）"
            sid = "019c561c-8b6c-7c60-b66f-63096d1a4df9"
            live_root = base / "live-task-dashboard"
            live_root.mkdir(parents=True, exist_ok=True)
            legacy_root = base / "Desktop-task-dashboard"
            legacy_root.mkdir(parents=True, exist_ok=True)
            (base / ".sessions").mkdir(parents=True, exist_ok=True)
            (base / ".sessions" / "task_dashboard.json").write_text(
                json.dumps(
                    {
                        "project_id": pid,
                        "sessions": [
                            {
                                "id": sid,
                                "cli_type": "codex",
                                "channel_name": channel_name,
                                "status": "active",
                                "is_primary": True,
                                "is_deleted": False,
                                "created_at": "2026-03-17T00:00:00Z",
                                "last_used_at": "2026-03-17T00:00:00Z",
                                "environment": "",
                                "worktree_root": "",
                                "workdir": "",
                                "branch": "",
                                "project_execution_context": {
                                    "target": {
                                        "project_id": pid,
                                        "channel_name": channel_name,
                                        "session_id": sid,
                                        "environment": "stable",
                                        "worktree_root": str(legacy_root),
                                        "workdir": str(legacy_root),
                                        "branch": "legacy-branch",
                                    },
                                    "source": {
                                        "project_id": pid,
                                        "environment": "stable",
                                        "worktree_root": str(live_root),
                                        "workdir": str(live_root),
                                        "branch": "release/live",
                                    },
                                    "context_source": "project",
                                    "override": {
                                        "applied": False,
                                        "fields": [],
                                        "source": "",
                                    },
                                },
                            }
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            t = threading.Thread(target=httpd.serve_forever, daemon=True)
            t.start()
            port = int(httpd.server_address[1])
            try:
                with mock.patch.object(
                    server,
                    "_load_project_execution_context",
                    return_value={
                        "project_id": pid,
                        "environment": "stable",
                        "worktree_root": str(live_root),
                        "workdir": str(live_root),
                        "branch": "release/live",
                        "configured": True,
                        "context_source": "project",
                    },
                ):
                    with url_request.urlopen(
                        f"http://127.0.0.1:{port}/api/sessions?project_id={pid}&include_deleted=1",
                        timeout=3,
                    ) as resp:
                        self.assertEqual(resp.status, 200)
                        body = json.loads(resp.read().decode("utf-8"))
                    row = next((item for item in (body.get("sessions") or []) if str(item.get("id") or "") == sid), {})
                    self.assertEqual(row.get("worktree_root"), str(live_root))
                    self.assertEqual(row.get("workdir"), str(live_root))
                    self.assertEqual(row.get("branch"), "release/live")
                    ctx = row.get("project_execution_context") or {}
                    target = ctx.get("target") or {}
                    self.assertEqual(target.get("worktree_root"), str(live_root))
                    self.assertEqual(target.get("workdir"), str(live_root))
                    self.assertEqual(target.get("branch"), "release/live")
            finally:
                httpd.shutdown()
                t.join(timeout=2)
                httpd.server_close()

    def test_session_list_reconciles_primary_flag_from_effective_channel_primary(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            httpd, _store, session_store = self._start_server(base)
            pid = "task_dashboard"
            channel_name = "子级02-CCB运行时（server-并发-安全-启动）"
            sid1 = "019c561b-22a1-7632-a667-19c1a5249b41"
            sid2 = "019ca7e6-81c9-7b51-a8ea-aab4b87dec06"
            session_store.create_session(pid, channel_name, cli_type="codex", session_id=sid1)
            session_store.create_session(pid, channel_name, cli_type="codex", session_id=sid2)
            session_store.update_session(sid1, is_primary=False, last_used_at="2026-03-08T10:00:00Z")
            session_store.update_session(sid2, is_primary=False, last_used_at="2026-03-08T10:05:00Z")

            t = threading.Thread(target=httpd.serve_forever, daemon=True)
            t.start()
            port = int(httpd.server_address[1])
            try:
                with url_request.urlopen(
                    f"http://127.0.0.1:{port}/api/channel-sessions?project_id={pid}&channel_name="
                    + quote(channel_name)
                    + "&include_deleted=1",
                    timeout=3,
                ) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
                self.assertEqual(payload.get("primary_session_id"), sid2)
                rows = payload.get("sessions") or []
                row1 = next((row for row in rows if str(row.get("id") or "") == sid1), {})
                row2 = next((row for row in rows if str(row.get("id") or "") == sid2), {})
                self.assertFalse(bool(row1.get("is_primary")))
                self.assertTrue(bool(row2.get("is_primary")))

                with url_request.urlopen(
                    f"http://127.0.0.1:{port}/api/sessions?project_id={pid}&channel_name="
                    + quote(channel_name)
                    + "&include_deleted=1",
                    timeout=3,
                ) as resp:
                    visible = (json.loads(resp.read().decode("utf-8")).get("sessions") or [])
                row1_visible = next((row for row in visible if str(row.get("id") or "") == sid1), {})
                row2_visible = next((row for row in visible if str(row.get("id") or "") == sid2), {})
                self.assertFalse(bool(row1_visible.get("is_primary")))
                self.assertTrue(bool(row2_visible.get("is_primary")))

                with url_request.urlopen(f"http://127.0.0.1:{port}/api/sessions/{sid2}", timeout=3) as resp:
                    detail = json.loads(resp.read().decode("utf-8"))
                self.assertTrue(bool(detail.get("is_primary")))
            finally:
                httpd.shutdown()
                t.join(timeout=2)
                httpd.server_close()

    def test_put_session_status_is_legacy_no_op(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            httpd, _store, session_store = self._start_server(base)
            pid = "task_dashboard"
            channel_name = "子级02-CCB运行时（server-并发-安全-启动）"
            sid = "019c561c-8b6c-7c60-b66f-63096d1a4dfe"
            session_store.create_session(pid, channel_name, cli_type="codex", session_id=sid)

            t = threading.Thread(target=httpd.serve_forever, daemon=True)
            t.start()
            port = int(httpd.server_address[1])
            try:
                req = url_request.Request(
                    f"http://127.0.0.1:{port}/api/sessions/{sid}",
                    data=json.dumps(
                        {
                            "alias": "兼容写入",
                            "status": "inactive",
                        }
                    ).encode("utf-8"),
                    method="PUT",
                    headers={"Content-Type": "application/json"},
                )
                with url_request.urlopen(req, timeout=3) as resp:
                    self.assertEqual(resp.status, 200)
                    body = json.loads(resp.read().decode("utf-8"))
                session = body.get("session") or {}
                self.assertEqual(session.get("alias"), "兼容写入")
                self.assertEqual(session.get("status"), "active")

                stored = session_store.get_session(sid) or {}
                self.assertEqual(stored.get("alias"), "兼容写入")
                self.assertEqual(stored.get("status"), "active")
            finally:
                httpd.shutdown()
                t.join(timeout=2)
                httpd.server_close()


if __name__ == "__main__":
    unittest.main()
