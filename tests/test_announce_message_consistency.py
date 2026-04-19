# -*- coding: utf-8 -*-

import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock
from urllib import request as url_request

import server


class _NoopScheduler:
    def enqueue(self, run_id: str, session_id: str, cli_type: str = "codex", priority: str = "normal") -> bool:
        return True


class AnnounceMessageConsistencyTests(unittest.TestCase):
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
        return httpd, run_store, session_store

    def _create_bound_session(self, session_store: server.SessionStore, sid: str) -> None:
        session_store.create_session(
            "task_dashboard",
            "辅助02-团队协作Skills治理（审查-升级-规范）",
            cli_type="codex",
            session_id=sid,
        )

    def _post_announce(self, port: int, body: dict) -> dict:
        req = url_request.Request(
            f"http://127.0.0.1:{port}/api/codex/announce",
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "X-TaskDashboard-Token": "test-token",
            },
            method="POST",
        )
        with url_request.urlopen(req, timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            return json.loads(resp.read().decode("utf-8"))

    def _get_run(self, port: int, run_id: str) -> dict:
        with url_request.urlopen(f"http://127.0.0.1:{port}/api/codex/run/{run_id}", timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            return json.loads(resp.read().decode("utf-8"))

    def test_announce_persists_visible_flag_only(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            httpd, run_store, session_store = self._start_server(base)
            sid = "019d232f-02f1-7781-9de8-2333f2417e73"
            self._create_bound_session(session_store, sid)
            t = threading.Thread(target=httpd.serve_forever, daemon=True)
            t.start()
            port = int(httpd.server_address[1])
            try:
                with mock.patch.dict("os.environ", {"TASK_DASHBOARD_TOKEN": "test-token"}, clear=False):
                    payload = self._post_announce(
                        port,
                        {
                            "projectId": "task_dashboard",
                            "channelName": "辅助02-团队协作Skills治理（审查-升级-规范）",
                            "sessionId": sid,
                            "message": "\n".join(
                                [
                                    "回执任务: 正式消息证据链恢复",
                                    "执行阶段: 启动",
                                    "本次目标: 补轻量一致性",
                                    "当前结论: 已接手",
                                ]
                            ),
                            "message_kind": "collab_update",
                            "interaction_mode": "task_with_receipt",
                            "source_ref": {
                                "project_id": "task_dashboard",
                                "channel_name": "子级02-CCB运行时（server-并发-安全-启动）",
                                "session_id": "019d3d63-057a-7620-8f04-730f3488d0a5",
                            },
                            "callback_to": {
                                "channel_name": "子级02-CCB运行时（server-并发-安全-启动）",
                                "session_id": "019d3d63-057a-7620-8f04-730f3488d0a5",
                            },
                            "sender_agent_ref": {
                                "agent_name": "服务开发-通讯能力",
                                "session_id": "019d3d63-057a-7620-8f04-730f3488d0a5",
                                "alias": "服务开发-通讯能力",
                            },
                        },
                    )
                    run_id = str((payload.get("run") or {}).get("id") or "")
                    detail = self._get_run(port, run_id)
            finally:
                httpd.shutdown()
                t.join(timeout=2)
                httpd.server_close()

            run = payload.get("run") or {}
            self.assertTrue(bool(run.get("visible_in_channel_chat")))
            self.assertNotIn("communication_view", run)
            self.assertNotIn("receipt_summary", run)

            detail_run = detail.get("run") or {}
            self.assertTrue(bool(detail_run.get("visible_in_channel_chat")))
            self.assertNotIn("communication_view", detail_run)
            self.assertNotIn("receipt_summary", detail_run)

            meta = run_store.load_meta(run_id) or {}
            self.assertTrue(bool(meta.get("visible_in_channel_chat")))
            self.assertNotIn("communication_view", meta)
            self.assertNotIn("receipt_summary", meta)
