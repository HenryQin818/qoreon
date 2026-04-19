import json
import tempfile
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib import request as url_request

import server


class QoreonProjectAliasApiTests(unittest.TestCase):
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
        return httpd, run_store, session_store, session_binding_store

    def _create_running_run(
        self,
        store: server.RunStore,
        *,
        project_id: str,
        channel_name: str,
        session_id: str,
    ) -> str:
        run = store.create_run(
            project_id,
            channel_name,
            session_id,
            "qoreon alias probe",
            sender_type="user",
            sender_id="u",
            sender_name="U",
        )
        run_id = str(run.get("id") or "").strip()
        meta = store.load_meta(run_id) or {}
        now = time.time()
        meta["status"] = "running"
        meta["createdAt"] = time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(now - 20))
        meta["startedAt"] = time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(now - 15))
        meta["messagePreview"] = "Qoreon runtime alias smoke"
        store.save_meta(run_id, meta)
        return run_id

    def test_qoreon_read_alias_restores_sessions_runs_bindings_and_agent_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            httpd, store, session_store, binding_store = self._start_server(base)

            pid = "task_dashboard"
            sid = "019d7529-5944-74e2-999d-b87383434c44"
            channel_name = "子级02-CCB运行时（server-并发-安全-启动）"
            session_store.create_session(pid, channel_name, cli_type="codex", session_id=sid)
            binding_store.save_binding(sid, pid, channel_name, cli_type="codex")
            run_id = self._create_running_run(
                store,
                project_id=pid,
                channel_name=channel_name,
                session_id=sid,
            )

            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            port = int(httpd.server_address[1])
            try:
                with url_request.urlopen(
                    f"http://127.0.0.1:{port}/api/sessions?project_id=qoreon",
                    timeout=3,
                ) as resp:
                    self.assertEqual(resp.status, 200)
                    sessions_body = json.loads(resp.read().decode("utf-8"))
                sessions = sessions_body.get("sessions") or []
                self.assertEqual(len(sessions), 1)
                self.assertEqual(str(sessions[0].get("project_id") or ""), "qoreon")
                self.assertEqual(str(((sessions[0].get("runtime_state") or {}).get("display_state") or "")), "running")

                with url_request.urlopen(
                    f"http://127.0.0.1:{port}/api/codex/runs?projectId=qoreon&sessionId={sid}&limit=5&payloadMode=light",
                    timeout=3,
                ) as resp:
                    self.assertEqual(resp.status, 200)
                    runs_body = json.loads(resp.read().decode("utf-8"))
                runs = runs_body.get("runs") or []
                self.assertEqual(len(runs), 1)
                self.assertEqual(str(runs[0].get("id") or ""), run_id)
                self.assertEqual(str(runs[0].get("projectId") or ""), "qoreon")

                with url_request.urlopen(
                    f"http://127.0.0.1:{port}/api/sessions/bindings?projectId=qoreon",
                    timeout=3,
                ) as resp:
                    self.assertEqual(resp.status, 200)
                    bindings_body = json.loads(resp.read().decode("utf-8"))
                bindings = bindings_body.get("bindings") or []
                self.assertEqual(len(bindings), 1)
                self.assertEqual(str(bindings[0].get("projectId") or ""), "qoreon")

                with url_request.urlopen(
                    f"http://127.0.0.1:{port}/api/agent-candidates?project_id=qoreon",
                    timeout=3,
                ) as resp:
                    self.assertEqual(resp.status, 200)
                    candidates_body = json.loads(resp.read().decode("utf-8"))
                targets = candidates_body.get("agent_targets") or []
                self.assertEqual(str(candidates_body.get("project_id") or ""), "qoreon")
                self.assertEqual(len(targets), 1)
                self.assertEqual(str(targets[0].get("project_id") or ""), "qoreon")

                with url_request.urlopen(
                    f"http://127.0.0.1:{port}/api/sessions?project_id=qoreon_official_site",
                    timeout=3,
                ) as resp:
                    self.assertEqual(resp.status, 200)
                    unrelated_body = json.loads(resp.read().decode("utf-8"))
                self.assertEqual(len(unrelated_body.get("sessions") or []), 0)
            finally:
                httpd.shutdown()
                thread.join(timeout=2)
                httpd.server_close()
