from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock
from urllib import request as url_request

import server


class TestPerformanceDiagnosticsApi(unittest.TestCase):
    def _start_server(self, base: Path) -> ThreadingHTTPServer:
        static_root = base / "static"
        static_root.mkdir(parents=True, exist_ok=True)
        (static_root / "index.html").write_text("ok", encoding="utf-8")

        run_store = server.RunStore(base / ".runtime" / "stable" / ".runs")
        session_store = server.SessionStore(base_dir=base)
        session_binding_store = server.SessionBindingStore(runs_dir=run_store.runs_dir)

        httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        httpd.static_root = static_root  # type: ignore[attr-defined]
        httpd.allow_root = base  # type: ignore[attr-defined]
        httpd.store = run_store  # type: ignore[attr-defined]
        httpd.runs_dir = run_store.runs_dir  # type: ignore[attr-defined]
        httpd.worktree_root = base  # type: ignore[attr-defined]
        httpd.environment_name = "stable"  # type: ignore[attr-defined]
        httpd.session_store = session_store  # type: ignore[attr-defined]
        httpd.session_binding_store = session_binding_store  # type: ignore[attr-defined]
        httpd.http_log = base / ".run" / "task-dashboard-server.http.log"  # type: ignore[attr-defined]
        httpd.scheduler = None  # type: ignore[attr-defined]
        httpd.project_id = "task_dashboard"  # type: ignore[attr-defined]
        httpd.runtime_role = "compat_shell"  # type: ignore[attr-defined]
        return httpd

    def test_get_perf_snapshot_returns_payload(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            httpd = self._start_server(base)
            t = threading.Thread(target=httpd.serve_forever, daemon=True)
            t.start()
            try:
                port = int(httpd.server_address[1])
                fake_payload = {
                    "ok": True,
                    "generated_at": "2026-04-07T18:00:00+08:00",
                    "environment": "stable",
                    "port": 18765,
                    "project_id": "task_dashboard",
                    "diagnosis": {"headline": "浏览器/GPU 压力", "severity": "danger"},
                    "summary_cards": [],
                    "panels": [],
                    "windows": [],
                    "top_endpoints": [],
                    "top_projects": [],
                    "top_sessions": [],
                    "top_processes": [],
                    "automation_processes": [],
                    "recommendations": [],
                    "references": [],
                }
                with mock.patch("task_dashboard.routes.main.build_runtime_perf_snapshot", return_value=fake_payload):
                    with url_request.urlopen(f"http://127.0.0.1:{port}/api/runtime/perf-snapshot", timeout=3) as resp:
                        self.assertEqual(resp.status, 200)
                        body = json.loads(resp.read().decode("utf-8"))
                self.assertTrue(body.get("ok"))
                self.assertEqual(body.get("project_id"), "task_dashboard")
                self.assertEqual((body.get("diagnosis") or {}).get("headline"), "浏览器/GPU 压力")
            finally:
                httpd.shutdown()
                t.join(timeout=2)
                httpd.server_close()


if __name__ == "__main__":
    unittest.main()
