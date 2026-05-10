import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib import request as url_request
from unittest import mock

import server


class _FakeProjectSchedulerRuntime:
    def __init__(self, project_id: str) -> None:
        self.project_id = project_id

    def get_status(self, project_id: str) -> dict:
        if project_id != self.project_id:
            return {}
        return {
            "project_id": project_id,
            "scheduler_enabled": True,
            "scheduler_state": "idle",
            "reminder_enabled": True,
            "reminder_state": "idle",
            "auto_inspection_enabled": True,
            "auto_inspection_state": "idle",
            "inspection_tasks": [{"inspection_task_id": "runtime-heavy"}],
            "inspection_records": [{"record_id": "inspection-heavy"}],
            "reminder_records": [{"record_id": "reminder-heavy"}],
        }


class _FakeHeartbeatRuntime:
    def __init__(self) -> None:
        self.list_calls = 0

    def list_tasks(self, project_id: str) -> dict:
        self.list_calls += 1
        return {
            "project_id": project_id,
            "enabled": True,
            "scan_interval_seconds": 30,
            "ready": True,
            "errors": [],
            "count": 1,
            "items": [
                {
                    "heartbeat_task_id": "ops-watch",
                    "title": "运维巡查",
                    "enabled": True,
                    "ready": True,
                    "pending_job": True,
                    "last_status": "running",
                }
            ],
        }


class ProjectAutomationStatusApiTests(unittest.TestCase):
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
        httpd.scheduler = None  # type: ignore[attr-defined]
        httpd.task_push_runtime = server.TaskPushRuntimeRegistry(store=run_store, session_store=session_store)  # type: ignore[attr-defined]
        httpd.task_plan_runtime = server.TaskPlanRuntimeRegistry(  # type: ignore[attr-defined]
            store=run_store,
            session_store=session_store,
            task_push_runtime=httpd.task_push_runtime,
        )
        httpd.assist_request_runtime = server.AssistRequestRuntimeRegistry(store=run_store, session_store=session_store)  # type: ignore[attr-defined]
        return httpd

    def test_automation_status_summary_omits_details_and_avoids_heartbeat_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            pid = "task_dashboard"
            heartbeat_runtime = _FakeHeartbeatRuntime()
            httpd = self._start_server(base)
            httpd.project_scheduler_runtime = _FakeProjectSchedulerRuntime(pid)  # type: ignore[attr-defined]
            httpd.heartbeat_task_runtime = heartbeat_runtime  # type: ignore[attr-defined]
            t = threading.Thread(target=httpd.serve_forever, daemon=True)
            t.start()
            port = int(httpd.server_address[1])
            try:
                with mock.patch.object(server.Handler, "_require_token", return_value=True), mock.patch(
                    "server._find_project_cfg",
                    return_value={"id": pid, "name": "Task Dashboard"},
                ), mock.patch(
                    "server._load_project_auto_inspection_config",
                    return_value={
                        "enabled": True,
                        "ready": True,
                        "active_inspection_task_id": "default",
                        "errors": [],
                        "inspection_tasks": [
                            {"inspection_task_id": "default", "enabled": True, "ready": True}
                        ],
                    },
                ), mock.patch(
                    "server._load_project_heartbeat_config",
                    return_value={
                        "enabled": True,
                        "ready": True,
                        "scan_interval_seconds": 30,
                        "errors": [],
                        "tasks": [
                            {"heartbeat_task_id": "ops-watch", "enabled": True, "ready": True}
                        ],
                    },
                ):
                    url = f"http://127.0.0.1:{port}/api/projects/{pid}/automation-status"
                    with url_request.urlopen(url, timeout=3) as resp:
                        self.assertEqual(resp.status, 200)
                        payload = json.loads(resp.read().decode("utf-8"))
                self.assertFalse(payload.get("include_details"))
                self.assertEqual((payload.get("inspection") or {}).get("task_count"), 1)
                self.assertEqual((payload.get("heartbeat") or {}).get("task_count"), 1)
                self.assertNotIn("inspection_tasks", payload)
                self.assertNotIn("heartbeat_tasks", payload)
                status = payload.get("status") or {}
                self.assertNotIn("inspection_records", status)
                self.assertNotIn("reminder_records", status)
                self.assertEqual(heartbeat_runtime.list_calls, 0)
            finally:
                httpd.shutdown()
                t.join(timeout=2)
                httpd.server_close()

    def test_automation_status_details_returns_task_lists(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            pid = "task_dashboard"
            heartbeat_runtime = _FakeHeartbeatRuntime()
            httpd = self._start_server(base)
            httpd.project_scheduler_runtime = _FakeProjectSchedulerRuntime(pid)  # type: ignore[attr-defined]
            httpd.heartbeat_task_runtime = heartbeat_runtime  # type: ignore[attr-defined]
            t = threading.Thread(target=httpd.serve_forever, daemon=True)
            t.start()
            port = int(httpd.server_address[1])
            try:
                with mock.patch.object(server.Handler, "_require_token", return_value=True), mock.patch(
                    "server._find_project_cfg",
                    return_value={"id": pid, "name": "Task Dashboard"},
                ), mock.patch(
                    "server._load_project_auto_inspection_config",
                    return_value={
                        "enabled": True,
                        "ready": True,
                        "active_inspection_task_id": "default",
                        "errors": [],
                        "inspection_tasks": [
                            {"inspection_task_id": "default", "enabled": True, "ready": True}
                        ],
                    },
                ), mock.patch(
                    "server._load_project_heartbeat_config",
                    return_value={
                        "enabled": True,
                        "ready": True,
                        "scan_interval_seconds": 30,
                        "errors": [],
                        "tasks": [
                            {"heartbeat_task_id": "ops-watch", "enabled": True, "ready": True}
                        ],
                    },
                ):
                    url = f"http://127.0.0.1:{port}/api/projects/{pid}/automation-status?include=details"
                    with url_request.urlopen(url, timeout=3) as resp:
                        self.assertEqual(resp.status, 200)
                        payload = json.loads(resp.read().decode("utf-8"))
                self.assertTrue(payload.get("include_details"))
                self.assertEqual(len(payload.get("inspection_tasks") or []), 1)
                self.assertEqual(len(payload.get("heartbeat_tasks") or []), 1)
                self.assertEqual((payload.get("heartbeat") or {}).get("running_count"), 1)
                self.assertEqual(heartbeat_runtime.list_calls, 1)
            finally:
                httpd.shutdown()
                t.join(timeout=2)
                httpd.server_close()


if __name__ == "__main__":
    unittest.main()
