# -*- coding: utf-8 -*-

import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib import request as url_request
from unittest import mock

import server


class _NoopScheduler:
    def enqueue(self, run_id: str, session_id: str, cli_type: str = "codex", priority: str = "normal") -> bool:
        return True


class CompatSessionBindingTests(unittest.TestCase):
    def _start_server(self, base: Path):
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
        httpd.scheduler = _NoopScheduler()  # type: ignore[attr-defined]
        httpd.project_scheduler_runtime = server.ProjectSchedulerRuntimeRegistry(store=run_store, session_store=session_store)  # type: ignore[attr-defined]
        httpd.task_push_runtime = server.TaskPushRuntimeRegistry(store=run_store, session_store=session_store)  # type: ignore[attr-defined]
        httpd.task_plan_runtime = server.TaskPlanRuntimeRegistry(  # type: ignore[attr-defined]
            store=run_store,
            session_store=session_store,
            task_push_runtime=httpd.task_push_runtime,
        )
        httpd.assist_request_runtime = server.AssistRequestRuntimeRegistry(store=run_store, session_store=session_store)  # type: ignore[attr-defined]
        httpd.environment_name = "stable"  # type: ignore[attr-defined]
        httpd.worktree_root = base / "stable-root"  # type: ignore[attr-defined]
        httpd.worktree_root.mkdir(parents=True, exist_ok=True)  # type: ignore[attr-defined]
        return httpd, session_store

    def test_announce_allows_legacy_task_dashboard_with_prod_mirror_session(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            httpd, session_store = self._start_server(base)
            sid = "019cbbb5-c1db-7ed3-aa19-97febec83728"
            session_store.create_session(
                "task_dashboard_prod_mirror",
                "子级04-前端体验（task-overview 页面交互）",
                cli_type="codex",
                session_id=sid,
                alias="前端页面-对话管理",
            )
            t = threading.Thread(target=httpd.serve_forever, daemon=True)
            t.start()
            port = int(httpd.server_address[1])
            req = url_request.Request(
                f"http://127.0.0.1:{port}/api/codex/announce",
                data=json.dumps(
                    {
                        "projectId": "task_dashboard",
                        "channelName": "子级04-前端体验（task-overview 页面交互）",
                        "sessionId": sid,
                        "message": "兼容壳发送测试",
                    },
                    ensure_ascii=False,
                ).encode("utf-8"),
                headers={
                    "Content-Type": "application/json; charset=utf-8",
                    "X-TaskDashboard-Token": "test-token",
                },
                method="POST",
            )
            try:
                with mock.patch.dict("os.environ", {"TASK_DASHBOARD_TOKEN": "test-token"}, clear=False):
                    with url_request.urlopen(req, timeout=5) as resp:
                        body = json.loads(resp.read().decode("utf-8"))
                self.assertIn("run", body)
                self.assertEqual(body["run"]["projectId"], "task_dashboard")
                self.assertEqual(body["run"]["channelName"], "子级04-前端体验（task-overview 页面交互）")
            finally:
                httpd.shutdown()
                t.join(timeout=2)
                httpd.server_close()

    def test_announce_allows_project_id_case_variant_session_binding(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            httpd, session_store = self._start_server(base)
            sid = "019d86a8-d013-73b0-934a-a792cea97041"
            channel_name = "主体03-视觉主题与展示规范"
            session_store.create_session(
                "NDT",
                channel_name,
                cli_type="codex",
                session_id=sid,
                alias="视觉-规范助理",
            )
            t = threading.Thread(target=httpd.serve_forever, daemon=True)
            t.start()
            port = int(httpd.server_address[1])
            req = url_request.Request(
                f"http://127.0.0.1:{port}/api/codex/announce",
                data=json.dumps(
                    {
                        "projectId": "ndt",
                        "channelName": channel_name,
                        "sessionId": sid,
                        "message": "项目ID大小写兼容发送测试",
                    },
                    ensure_ascii=False,
                ).encode("utf-8"),
                headers={
                    "Content-Type": "application/json; charset=utf-8",
                    "X-TaskDashboard-Token": "test-token",
                },
                method="POST",
            )
            try:
                with mock.patch.dict("os.environ", {"TASK_DASHBOARD_TOKEN": "test-token"}, clear=False):
                    with url_request.urlopen(req, timeout=5) as resp:
                        body = json.loads(resp.read().decode("utf-8"))
                self.assertIn("run", body)
                self.assertEqual(body["run"]["projectId"], "ndt")
                self.assertEqual(body["run"]["channelName"], channel_name)
            finally:
                httpd.shutdown()
                t.join(timeout=2)
                httpd.server_close()
