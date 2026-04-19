import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib import error as url_error
from urllib import request as url_request

import server


class ScheduleQueueRetiredApiTests(unittest.TestCase):
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
        httpd.project_scheduler_runtime = server.ProjectSchedulerRuntimeRegistry(store=run_store, session_store=session_store)  # type: ignore[attr-defined]
        return httpd

    def test_schedule_queue_routes_removed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            httpd = self._start_server(base)
            t = threading.Thread(target=httpd.serve_forever, daemon=True)
            t.start()
            port = int(httpd.server_address[1])
            try:
                url = f"http://127.0.0.1:{port}/api/projects/task_dashboard/schedule-queue"

                with self.assertRaises(url_error.HTTPError) as get_err:
                    url_request.urlopen(url, timeout=3)
                self.assertEqual(get_err.exception.code, 404)

                req = url_request.Request(
                    url,
                    data=json.dumps({"action": "replace", "task_paths": []}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with self.assertRaises(url_error.HTTPError) as post_err:
                    url_request.urlopen(req, timeout=3)
                self.assertEqual(post_err.exception.code, 404)
            finally:
                httpd.shutdown()
                t.join(timeout=2)
                httpd.server_close()


if __name__ == "__main__":
    unittest.main()
