import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock
from urllib import error as url_error
from urllib import request as url_request

import server


SESSION_ID_OWNER = "019da4c6-9cdf-7453-b068-299fe16f0d5c"
SESSION_ID_EXECUTOR = "019d8f23-3ac2-7ac2-934e-53e3507d3118"


def _write_config(root: Path) -> dict:
    project_cfg = {
        "id": "task_dashboard",
        "name": "Task Dashboard",
        "project_root_rel": ".",
        "task_root_rel": "任务规划",
        "channels": [
            {"name": "辅助04-原型设计与Demo可视化（静态数据填充-业务规格确认）"},
            {"name": "子级02-CCB运行时（server-并发-安全-启动）"},
        ],
    }
    (root / "config.toml").write_text(
        """
version = 1

[[projects]]
id = "task_dashboard"
name = "Task Dashboard"
project_root_rel = "."
task_root_rel = "任务规划"

[[projects.channels]]
name = "辅助04-原型设计与Demo可视化（静态数据填充-业务规格确认）"

[[projects.channels]]
name = "子级02-CCB运行时（server-并发-安全-启动）"
        """.strip(),
        encoding="utf-8",
    )
    return project_cfg


def _write_sessions(root: Path) -> None:
    sessions_dir = root / ".runtime" / "stable" / ".sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    (sessions_dir / "task_dashboard.json").write_text(
        json.dumps(
            {
                "project_id": "task_dashboard",
                "sessions": [
                    {
                        "id": SESSION_ID_OWNER,
                        "channel_name": "辅助04-原型设计与Demo可视化（静态数据填充-业务规格确认）",
                        "alias": "产品-任务板块",
                        "agent_name": "产品-任务板块",
                        "is_primary": True,
                        "is_deleted": False,
                    },
                    {
                        "id": SESSION_ID_EXECUTOR,
                        "channel_name": "子级02-CCB运行时（server-并发-安全-启动）",
                        "alias": "后端-任务业务",
                        "agent_name": "后端-任务业务",
                        "is_primary": True,
                        "is_deleted": False,
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


class TaskWorkflowApiTests(unittest.TestCase):
    def _start_server(self, base: Path) -> ThreadingHTTPServer:
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
        return httpd

    def test_task_create_api_writes_standard_task_and_blocks_dispatch_gate(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            project_cfg = _write_config(base)
            _write_sessions(base)
            httpd = self._start_server(base)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            port = int(httpd.server_address[1])
            try:
                with mock.patch.object(server, "_repo_root", return_value=base), mock.patch.object(
                    server,
                    "_find_project_cfg",
                    side_effect=lambda pid: project_cfg if pid == "task_dashboard" else None,
                ):
                    output_path = (
                        base
                        / "任务规划"
                        / "辅助04-原型设计与Demo可视化（静态数据填充-业务规格确认）"
                        / "任务"
                        / "【待开始】【任务】20260427-api路由样例.md"
                    )
                    create_req = url_request.Request(
                        f"http://127.0.0.1:{port}/api/projects/task_dashboard/tasks/create",
                        data=json.dumps(
                            {
                                "title": "api路由样例",
                                "stage": "draft",
                                "owner": {"agentName": "产品-任务板块"},
                                "executor": {"agentName": "后端-任务业务"},
                                "outputPath": str(output_path),
                            },
                            ensure_ascii=False,
                        ).encode("utf-8"),
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    with url_request.urlopen(create_req, timeout=5) as resp:
                        self.assertEqual(resp.status, 201)
                        payload = json.loads(resp.read().decode("utf-8"))
                    self.assertTrue(payload.get("ok"))
                    self.assertTrue(output_path.exists())
                    self.assertEqual(payload.get("parsed_roles", {}).get("executors", [{}])[0].get("session_id"), SESSION_ID_EXECUTOR)

                    blocked_path = (
                        base
                        / "任务规划"
                        / "子级02-CCB运行时（server-并发-安全-启动）"
                        / "任务"
                        / "【进行中】【任务】20260427-api派发阻断.md"
                    )
                    blocked_req = url_request.Request(
                        f"http://127.0.0.1:{port}/api/projects/task_dashboard/tasks/create",
                        data=json.dumps(
                            {
                                "title": "api派发阻断",
                                "stage": "dispatch",
                                "owner": {"agentName": "产品-任务板块"},
                                "executor": {"agentName": "后端-任务业务"},
                                "outputPath": str(blocked_path),
                            },
                            ensure_ascii=False,
                        ).encode("utf-8"),
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    with self.assertRaises(url_error.HTTPError) as err:
                        url_request.urlopen(blocked_req, timeout=5)
                    self.assertEqual(err.exception.code, 422)
                    error_payload = json.loads(err.exception.read().decode("utf-8"))
                    self.assertEqual(error_payload.get("error"), "validation_failed")
                    self.assertFalse(blocked_path.exists())
            finally:
                httpd.shutdown()
                thread.join(timeout=2)
                httpd.server_close()


if __name__ == "__main__":
    unittest.main()
