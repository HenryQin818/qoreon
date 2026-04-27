import json
import os
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib import request as url_request
from unittest.mock import patch

import server


class HealthApiTests(unittest.TestCase):
    def test_session_health_refresh_endpoint_rebuilds_payload_without_runtime_error(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            static_root = base / "static"
            static_root.mkdir(parents=True, exist_ok=True)
            (static_root / "index.html").write_text("ok", encoding="utf-8")

            run_store = server.RunStore(base / ".runtime" / "stable" / ".runs")
            session_store = server.SessionStore(base_dir=run_store.runs_dir.parent)
            session_binding_store = server.SessionBindingStore(runs_dir=run_store.runs_dir)

            session_store.create_session(
                "task_dashboard",
                "主体-总控（合并与验收）",
                cli_type="codex",
                session_id="019d107a-a5ad-7912-8797-d23c58013449",
            )

            httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
            httpd.static_root = static_root  # type: ignore[attr-defined]
            httpd.allow_root = static_root  # type: ignore[attr-defined]
            httpd.store = run_store  # type: ignore[attr-defined]
            httpd.session_store = session_store  # type: ignore[attr-defined]
            httpd.session_binding_store = session_binding_store  # type: ignore[attr-defined]
            httpd.http_log = base / ".run" / "test.http.log"  # type: ignore[attr-defined]
            httpd.scheduler = None  # type: ignore[attr-defined]
            httpd.environment_name = "stable"  # type: ignore[attr-defined]
            httpd.project_id = "task_dashboard"  # type: ignore[attr-defined]
            httpd.runtime_role = "compat_shell"  # type: ignore[attr-defined]
            httpd.runs_dir = run_store.runs_dir  # type: ignore[attr-defined]
            httpd.worktree_root = base / "task-dashboard"  # type: ignore[attr-defined]
            httpd.sessions_file = run_store.runs_dir.parent / ".sessions" / "task_dashboard.json"  # type: ignore[attr-defined]
            httpd.project_scheduler_runtime = server.ProjectSchedulerRuntimeRegistry(store=run_store, session_store=session_store)  # type: ignore[attr-defined]
            httpd.task_push_runtime = server.TaskPushRuntimeRegistry(store=run_store, session_store=session_store)  # type: ignore[attr-defined]
            httpd.task_plan_runtime = server.TaskPlanRuntimeRegistry(  # type: ignore[attr-defined]
                store=run_store,
                session_store=session_store,
                task_push_runtime=httpd.task_push_runtime,
            )
            httpd.heartbeat_task_runtime = server.HeartbeatTaskRuntimeRegistry(  # type: ignore[attr-defined]
                store=run_store,
                session_store=session_store,
                task_push_runtime=httpd.task_push_runtime,
            )
            httpd.assist_request_runtime = server.AssistRequestRuntimeRegistry(store=run_store, session_store=session_store)  # type: ignore[attr-defined]
            httpd.session_health_runtime = server.SessionHealthRuntimeRegistry(  # type: ignore[attr-defined]
                store=run_store,
                environment_name="stable",
                build_payload=lambda project_id: server._build_session_health_payload(
                    project_id=project_id,
                    session_store=session_store,
                    store=run_store,
                    environment_name="stable",
                    worktree_root=base / "task-dashboard",
                    heartbeat_runtime=httpd.heartbeat_task_runtime,
                    load_session_heartbeat_config=server._load_session_heartbeat_config,
                    heartbeat_summary_payload=server._heartbeat_summary_payload,
                ),
                config_loader=lambda: {
                    "projects": [
                        {
                            "id": "task_dashboard",
                            "name": "任务看板",
                            "session_health": {
                                "enabled": True,
                                "interval_minutes": 120,
                            },
                        }
                    ]
                },
            )

            t = threading.Thread(target=httpd.serve_forever, daemon=True)
            t.start()
            port = int(httpd.server_address[1])
            try:
                with url_request.urlopen(
                    f"http://127.0.0.1:{port}/api/session-health?project_id=task_dashboard&refresh=1",
                    timeout=10,
                ) as resp:
                    self.assertEqual(resp.status, 200)
                    body = json.loads(resp.read().decode("utf-8"))
                self.assertEqual(body.get("project_id"), "task_dashboard")
                self.assertEqual(len(body.get("sessions") or []), 1)
                session_health = body.get("session_health") or {}
                self.assertEqual(session_health.get("state"), "idle")
                self.assertEqual(session_health.get("last_error"), "")
            finally:
                httpd.shutdown()
                t.join(timeout=2)
                httpd.server_close()

    def test_resolve_runtime_project_id_prefers_main_runtime_ports(self) -> None:
        cfg = {
            "projects": [
                {"id": "task_dashboard", "runtime_role": "compat_shell"},
                {"id": "task_dashboard_prod", "runtime_role": "prod"},
                {"id": "task_dashboard_dev_control", "runtime_role": "dev_control"},
                {"id": "task_dashboard_dev", "runtime_role": "dev"},
                {"id": "task_dashboard_prod_mirror", "runtime_role": "prod_mirror"},
                {"id": "task_dashboard_open_source", "runtime_role": "open_source"},
                {"id": "task_dashboard_prod_debug", "runtime_role": "prod_debug"},
            ]
        }
        with patch.dict(os.environ, {"TASK_DASHBOARD_PROJECT_ID": ""}, clear=False):
            self.assertEqual(
                server._resolve_runtime_project_id(cfg, environment_name="stable", port=18765),
                "task_dashboard",
            )
            self.assertEqual(
                server._resolve_runtime_project_id(cfg, environment_name="stable", port=18767),
                "task_dashboard_prod_mirror",
            )
            self.assertEqual(
                server._resolve_runtime_project_id(cfg, environment_name="stable", port=18768),
                "task_dashboard_dev_control",
            )
            self.assertEqual(
                server._resolve_runtime_project_id(cfg, environment_name="stable", port=18769),
                "task_dashboard_prod_debug",
            )
            self.assertEqual(
                server._resolve_runtime_project_id(cfg, environment_name="dev", port=0),
                "task_dashboard_dev_control",
            )
            self.assertEqual(
                server._resolve_runtime_project_id(cfg, environment_name="refactor", port=0),
                "task_dashboard_prod_debug",
            )
            self.assertEqual(
                server._resolve_runtime_project_id(cfg, environment_name="stable", port=18766),
                "task_dashboard_dev",
            )

    def test_health_exposes_environment_runtime_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            static_root = base / "static"
            config_path = base / "config.refactor.toml"
            static_root.mkdir(parents=True, exist_ok=True)
            (static_root / "index.html").write_text("ok", encoding="utf-8")
            config_path.write_text("[[projects]]\nid = \"task_dashboard_dev\"\n", encoding="utf-8")

            run_store = server.RunStore(base / ".runtime" / "refactor" / ".runs")
            session_store = server.SessionStore(base_dir=run_store.runs_dir.parent)
            session_binding_store = server.SessionBindingStore(runs_dir=run_store.runs_dir)

            httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
            httpd.static_root = static_root  # type: ignore[attr-defined]
            httpd.allow_root = static_root  # type: ignore[attr-defined]
            httpd.store = run_store  # type: ignore[attr-defined]
            httpd.session_store = session_store  # type: ignore[attr-defined]
            httpd.session_binding_store = session_binding_store  # type: ignore[attr-defined]
            httpd.http_log = base / ".run" / "test.http.log"  # type: ignore[attr-defined]
            httpd.scheduler = None  # type: ignore[attr-defined]
            httpd.environment_name = "refactor"  # type: ignore[attr-defined]
            httpd.project_id = "task_dashboard_dev"  # type: ignore[attr-defined]
            httpd.runtime_role = "dev"  # type: ignore[attr-defined]
            httpd.runs_dir = run_store.runs_dir  # type: ignore[attr-defined]
            httpd.worktree_root = base / "task-dashboard-refactor"  # type: ignore[attr-defined]
            httpd.sessions_file = run_store.runs_dir.parent / ".sessions" / "task_dashboard_dev.json"  # type: ignore[attr-defined]
            httpd.project_scheduler_runtime = server.ProjectSchedulerRuntimeRegistry(store=run_store, session_store=session_store)  # type: ignore[attr-defined]
            httpd.task_push_runtime = server.TaskPushRuntimeRegistry(store=run_store, session_store=session_store)  # type: ignore[attr-defined]
            httpd.task_plan_runtime = server.TaskPlanRuntimeRegistry(  # type: ignore[attr-defined]
                store=run_store,
                session_store=session_store,
                task_push_runtime=httpd.task_push_runtime,
            )
            httpd.heartbeat_task_runtime = server.HeartbeatTaskRuntimeRegistry(  # type: ignore[attr-defined]
                store=run_store,
                session_store=session_store,
                task_push_runtime=httpd.task_push_runtime,
            )
            httpd.assist_request_runtime = server.AssistRequestRuntimeRegistry(store=run_store, session_store=session_store)  # type: ignore[attr-defined]

            t = threading.Thread(target=httpd.serve_forever, daemon=True)
            t.start()
            port = int(httpd.server_address[1])
            try:
                with patch.dict(os.environ, {"TASK_DASHBOARD_CONFIG": str(config_path)}, clear=False):
                    with url_request.urlopen(f"http://127.0.0.1:{port}/__health", timeout=3) as resp:
                        self.assertEqual(resp.status, 200)
                        body = json.loads(resp.read().decode("utf-8"))
                    self.assertTrue(body.get("ok"))
                    self.assertEqual(body.get("project_id"), "task_dashboard_dev")
                    self.assertEqual(body.get("runtime_role"), "dev")
                    self.assertFalse(bool(body.get("compat_shell")))
                    self.assertEqual(body.get("environment"), "refactor")
                    self.assertEqual(int(body.get("port") or 0), port)
                    self.assertEqual(body.get("localOrigin"), f"http://127.0.0.1:{port}")
                    self.assertEqual(body.get("publicOrigin"), f"http://127.0.0.1:{port}")
                    self.assertEqual(body.get("runsDir"), str(run_store.runs_dir.resolve()))
                    self.assertEqual(body.get("sessionsFile"), str((run_store.runs_dir.parent / ".sessions" / "task_dashboard_dev.json").resolve()))
                    self.assertEqual(body.get("staticRoot"), str(static_root.resolve()))
                    self.assertEqual(body.get("worktreeRoot"), str((base / "task-dashboard-refactor").resolve()))
                    self.assertEqual(body.get("configPath"), str(config_path.resolve()))
                    ctx = body.get("project_execution_context") or {}
                    self.assertEqual(ctx.get("context_source"), "server_runtime")
                    self.assertEqual((ctx.get("target") or {}).get("environment"), "refactor")
                    self.assertEqual((ctx.get("target") or {}).get("project_id"), "task_dashboard_dev")
                    self.assertEqual(
                        str(Path((ctx.get("source") or {}).get("worktree_root") or "").resolve()),
                        str((base / "task-dashboard-refactor").resolve()),
                    )
                    self.assertFalse(bool(((ctx.get("override") or {}).get("applied"))))

                    req = url_request.Request(f"http://127.0.0.1:{port}/__health", method="HEAD")
                    with url_request.urlopen(req, timeout=3) as head_resp:
                        self.assertEqual(head_resp.status, 200)
                        self.assertEqual(head_resp.read(), b"")
            finally:
                httpd.shutdown()
                t.join(timeout=2)
                httpd.server_close()

    def test_sessions_and_runs_expose_runtime_identity_fields(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            static_root = base / "static"
            static_root.mkdir(parents=True, exist_ok=True)
            (static_root / "index.html").write_text("ok", encoding="utf-8")

            run_store = server.RunStore(base / ".runtime" / "stable" / ".runs")
            session_store = server.SessionStore(base_dir=run_store.runs_dir.parent)
            session_binding_store = server.SessionBindingStore(runs_dir=run_store.runs_dir)

            session_id = "019cddd3-454e-7140-9881-0b7f6e936847"
            channel_name = "子级02-CCB运行时（server-并发-安全-启动）"
            session_store.create_session(
                "task_dashboard",
                channel_name,
                cli_type="codex",
                session_id=session_id,
            )
            run_store.create_run(
                project_id="task_dashboard",
                channel_name=channel_name,
                session_id=session_id,
                message="ping",
            )

            httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
            httpd.static_root = static_root  # type: ignore[attr-defined]
            httpd.allow_root = static_root  # type: ignore[attr-defined]
            httpd.store = run_store  # type: ignore[attr-defined]
            httpd.session_store = session_store  # type: ignore[attr-defined]
            httpd.session_binding_store = session_binding_store  # type: ignore[attr-defined]
            httpd.http_log = base / ".run" / "test.http.log"  # type: ignore[attr-defined]
            httpd.scheduler = None  # type: ignore[attr-defined]
            httpd.environment_name = "stable"  # type: ignore[attr-defined]
            httpd.runs_dir = run_store.runs_dir  # type: ignore[attr-defined]
            httpd.worktree_root = base / "task-dashboard"  # type: ignore[attr-defined]
            httpd.project_id = "task_dashboard"  # type: ignore[attr-defined]
            httpd.runtime_role = "compat_shell"  # type: ignore[attr-defined]
            httpd.sessions_file = run_store.runs_dir.parent / ".sessions" / "task_dashboard.json"  # type: ignore[attr-defined]
            httpd.project_scheduler_runtime = server.ProjectSchedulerRuntimeRegistry(store=run_store, session_store=session_store)  # type: ignore[attr-defined]
            httpd.task_push_runtime = server.TaskPushRuntimeRegistry(store=run_store, session_store=session_store)  # type: ignore[attr-defined]
            httpd.task_plan_runtime = server.TaskPlanRuntimeRegistry(  # type: ignore[attr-defined]
                store=run_store,
                session_store=session_store,
                task_push_runtime=httpd.task_push_runtime,
            )
            httpd.heartbeat_task_runtime = server.HeartbeatTaskRuntimeRegistry(  # type: ignore[attr-defined]
                store=run_store,
                session_store=session_store,
                task_push_runtime=httpd.task_push_runtime,
            )
            httpd.assist_request_runtime = server.AssistRequestRuntimeRegistry(store=run_store, session_store=session_store)  # type: ignore[attr-defined]

            t = threading.Thread(target=httpd.serve_forever, daemon=True)
            t.start()
            port = int(httpd.server_address[1])
            try:
                with url_request.urlopen(
                    f"http://127.0.0.1:{port}/api/sessions?project_id=task_dashboard",
                    timeout=3,
                ) as resp:
                    sessions_body = json.loads(resp.read().decode("utf-8"))
                self.assertEqual(sessions_body.get("project_id"), "task_dashboard")
                self.assertEqual(sessions_body.get("runtime_role"), "compat_shell")
                self.assertTrue(bool(sessions_body.get("compat_shell")))
                self.assertEqual(len(sessions_body.get("sessions") or []), 1)

                with url_request.urlopen(
                    f"http://127.0.0.1:{port}/api/codex/runs?projectId=task_dashboard&limit=1",
                    timeout=3,
                ) as resp:
                    runs_body = json.loads(resp.read().decode("utf-8"))
                self.assertEqual(runs_body.get("project_id"), "task_dashboard")
                self.assertEqual(runs_body.get("runtime_role"), "compat_shell")
                self.assertTrue(bool(runs_body.get("compat_shell")))
                self.assertEqual(len(runs_body.get("runs") or []), 1)
            finally:
                httpd.shutdown()
                t.join(timeout=2)
                httpd.server_close()


if __name__ == "__main__":
    unittest.main()
