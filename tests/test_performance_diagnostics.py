import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

from task_dashboard.performance_diagnostics import (
    build_performance_diagnostics_page_data,
    build_runtime_perf_snapshot,
)


class PerformanceDiagnosticsTests(unittest.TestCase):
    def test_build_page_data_exposes_live_api_and_refresh_config(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            payload = build_performance_diagnostics_page_data(
                Path(td),
                generated_at="2026-04-07T17:20:00+08:00",
                dashboard={"title": "项目任务看板"},
                links={"overview_page": "project-overview-dashboard.html"},
                performance_page_link="project-performance-diagnostics.html",
            )

        board = payload["performance_diagnostics"]
        self.assertEqual(payload["generated_at"], "2026-04-07T17:20:00+08:00")
        self.assertEqual(board["api_path"], "/api/runtime/perf-snapshot")
        self.assertEqual(int(board["refresh_interval_seconds"]), 15)
        self.assertEqual(payload["links"]["performance_page"], "project-performance-diagnostics.html")

    def test_runtime_snapshot_surfaces_browser_and_polling_pressure(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            http_log = base / ".runtime" / "stable" / ".run" / "task-dashboard-server.http.log"
            http_log.parent.mkdir(parents=True, exist_ok=True)
            http_log.write_text(
                "\n".join(
                    [
                        '127.0.0.1 - - [2026-04-07T16:46:10+0800] "GET /api/conversation-memos?projectId=task_dashboard&sessionId=s-1 HTTP/1.1" 200 -',
                        '127.0.0.1 - - [2026-04-07T16:46:12+0800] "GET /api/codex/runs?projectId=qoreon_official_site&sessionId=s-2 HTTP/1.1" 200 -',
                        '127.0.0.1 - - [2026-04-07T16:46:15+0800] "GET /api/projects/task_dashboard/heartbeat-tasks HTTP/1.1" 200 -',
                        '127.0.0.1 - - [2026-04-07T16:46:16+0800] "GET /api/sessions?project_id=task_dashboard HTTP/1.1" 200 -',
                    ]
                ),
                encoding="utf-8",
            )

            def fake_run_text(*args: str) -> str:
                if args == ("sysctl", "vm.swapusage"):
                    return "vm.swapusage: total = 9216.00M  used = 8101.88M  free = 1114.12M  (encrypted)"
                if args == ("sysctl", "-n", "hw.memsize"):
                    return "68719476736"
                if args == ("vm_stat",):
                    return "\n".join(
                        [
                            "Mach Virtual Memory Statistics: (page size of 16384 bytes)",
                            "Pages free:                             1125704.",
                            "Pages active:                           1044954.",
                            "Pages inactive:                          960162.",
                            "Pages speculative:                        88082.",
                            "Pages wired down:                        376424.",
                        ]
                    )
                if args == ("ps", "-wwaxo", "pid=,pcpu=,pmem=,rss=,etime=,args="):
                    return "\n".join(
                        [
                            "100 118.7 0.4 289216 18-03:05:11 Google Chrome Helper --type=gpu-process --seatbelt-client=26",
                            "4242 95.8 2.7 1791456 01:19:37 python server.py --port 18765 --environment-name stable",
                            "476 62.4 0.4 266096 27-10:37:19 WindowServer -daemon",
                            "101 25.5 1.0 642320 27-10:37:20 Google Chrome",
                            "102 22.2 2.1 1423696 18:04:52 chrome-profile --enable-automation --remote-debugging-pipe",
                        ]
                    )
                return ""

            with mock.patch("task_dashboard.performance_diagnostics._run_text", side_effect=fake_run_text):
                snapshot = build_runtime_perf_snapshot(
                    repo_root=base,
                    environment_name="stable",
                    port=18765,
                    project_id="task_dashboard",
                    http_log_path=http_log,
                    current_pid=4242,
                    now=datetime.fromisoformat("2026-04-07T16:50:00+08:00"),
                    cache_ttl_s=0,
                )

        self.assertTrue(snapshot["ok"])
        self.assertEqual(snapshot["diagnosis"]["primary_type"], "browser_gpu_pressure")
        self.assertEqual(snapshot["port"], 18765)
        self.assertEqual(snapshot["project_id"], "task_dashboard")
        self.assertEqual(snapshot["windows"][1]["count"], 4)
        self.assertEqual(snapshot["top_projects"][0]["label"], "task_dashboard")
        self.assertGreaterEqual(len(snapshot["top_processes"]), 3)
        self.assertEqual(snapshot["summary_cards"][0]["label"], "当前诊断")


if __name__ == "__main__":
    unittest.main()
