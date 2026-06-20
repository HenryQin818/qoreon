import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib import request as url_request

import server
from task_dashboard.codebuddy_permissions import (
    apply_codebuddy_permission_mode_to_runner_command,
    normalize_codebuddy_permission_mode,
)
from task_dashboard.runtime.scheduler_helpers import _extract_run_extra_fields, _sanitize_run_extra_meta


class CodeBuddyPermissionModeTests(unittest.TestCase):
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
        httpd.environment_name = "stable"  # type: ignore[attr-defined]
        httpd.worktree_root = str(base)  # type: ignore[attr-defined]
        httpd.project_scheduler_runtime = server.ProjectSchedulerRuntimeRegistry(store=run_store, session_store=session_store)  # type: ignore[attr-defined]
        httpd.task_push_runtime = server.TaskPushRuntimeRegistry(store=run_store, session_store=session_store)  # type: ignore[attr-defined]
        httpd.task_plan_runtime = server.TaskPlanRuntimeRegistry(  # type: ignore[attr-defined]
            store=run_store,
            session_store=session_store,
            task_push_runtime=httpd.task_push_runtime,
        )
        httpd.assist_request_runtime = server.AssistRequestRuntimeRegistry(store=run_store, session_store=session_store)  # type: ignore[attr-defined]
        return httpd, run_store, session_store

    def test_permission_mode_whitelist_and_command_projection(self) -> None:
        self.assertEqual(normalize_codebuddy_permission_mode(""), "default")
        self.assertEqual(normalize_codebuddy_permission_mode("bypassPermissions"), "bypassPermissions")
        self.assertEqual(normalize_codebuddy_permission_mode("bypass_permissions"), "bypassPermissions")
        self.assertEqual(normalize_codebuddy_permission_mode("accept-edits"), "acceptEdits")
        self.assertEqual(normalize_codebuddy_permission_mode("plan"), "plan")
        self.assertEqual(normalize_codebuddy_permission_mode("--dangerously-allow-anything"), "default")

        cmd = apply_codebuddy_permission_mode_to_runner_command(
            ["python3", "-m", "task_dashboard.adapters.codebuddy_runner", "--permission-mode", "bypassPermissions", "resume"],
            "plan",
        )
        self.assertEqual(cmd[-3:], ["--permission-mode", "plan", "resume"])

        default_cmd = apply_codebuddy_permission_mode_to_runner_command(cmd, "not-allowed")
        self.assertNotIn("--permission-mode", default_cmd)

    def test_run_extra_meta_preserves_business_permission_mode_only(self) -> None:
        extra = _extract_run_extra_fields(
            {
                "permissionMode": "bypassPermissions",
                "runExtraMeta": {"codebuddyPermissionMode": "plan"},
            }
        )
        self.assertEqual(extra.get("codebuddy_permission_mode"), "bypassPermissions")

        sanitized = _sanitize_run_extra_meta({"permissionMode": "plan"})
        self.assertEqual(sanitized.get("codebuddy_permission_mode"), "plan")

    def test_put_session_permission_mode_saves_and_echoes(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            httpd, _store, session_store = self._start_server(base)
            sid = "11111111-1111-1111-1111-111111111111"
            session_store.create_session("task_dashboard", "子级03", cli_type="codebuddy", session_id=sid)

            t = threading.Thread(target=httpd.serve_forever, daemon=True)
            t.start()
            port = int(httpd.server_address[1])
            try:
                req = url_request.Request(
                    f"http://127.0.0.1:{port}/api/sessions/{sid}",
                    data=json.dumps({"codebuddy_permission_mode": "bypassPermissions"}).encode("utf-8"),
                    method="PUT",
                    headers={"Content-Type": "application/json"},
                )
                with url_request.urlopen(req, timeout=3) as resp:
                    self.assertEqual(resp.status, 200)
                    body = json.loads(resp.read().decode("utf-8"))
                self.assertEqual((body.get("session") or {}).get("codebuddy_permission_mode"), "bypassPermissions")
                self.assertEqual((session_store.get_session(sid) or {}).get("codebuddy_permission_mode"), "bypassPermissions")

                req_invalid = url_request.Request(
                    f"http://127.0.0.1:{port}/api/sessions/{sid}",
                    data=json.dumps({"codebuddyPermissionMode": "rm -rf"}).encode("utf-8"),
                    method="PUT",
                    headers={"Content-Type": "application/json"},
                )
                with url_request.urlopen(req_invalid, timeout=3) as resp:
                    self.assertEqual(resp.status, 200)
                    invalid_body = json.loads(resp.read().decode("utf-8"))
                self.assertEqual((invalid_body.get("session") or {}).get("codebuddy_permission_mode"), "default")
            finally:
                httpd.shutdown()
                t.join(timeout=2)
                httpd.server_close()

    def test_codebuddy_run_meta_and_env_use_session_permission_mode(self) -> None:
        class _FakeAdapter:
            @classmethod
            def supports_model(cls) -> bool:
                return False

            @classmethod
            def build_resume_command(
                cls,
                session_id: str,
                message: str,
                output_path,
                profile_label: str = "",
                model: str = "",
                reasoning_effort: str = "",
                permission_mode: str = "",
            ) -> list[str]:
                _ = permission_mode
                return [
                    "python3",
                    "-m",
                    "task_dashboard.adapters.codebuddy_runner",
                    "resume",
                    "--session-id",
                    session_id,
                ]

        class _FakeStream:
            def readline(self) -> str:
                return ""

            def close(self) -> None:
                return

        class _FakeProc:
            seen_cmd: list[str] = []
            seen_env: dict[str, str] = {}

            def __init__(self, cmd, **kwargs) -> None:
                type(self).seen_cmd = list(cmd)
                type(self).seen_env = dict(kwargs.get("env") or {})
                self.returncode = 0
                self.stdout = _FakeStream()
                self.stderr = _FakeStream()

            def poll(self) -> int:
                return 0

            def kill(self) -> None:
                return

        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            store = server.RunStore(base / ".runs")
            session_store = server.SessionStore(base_dir=base)
            sid = "22222222-2222-2222-2222-222222222222"
            session_store.create_session(
                "task_dashboard",
                "子级03",
                cli_type="codebuddy",
                session_id=sid,
                codebuddy_permission_mode="bypassPermissions",
            )
            run = store.create_run("task_dashboard", "子级03", sid, "hello", cli_type="codebuddy")

            with patch.object(server, "get_adapter", return_value=_FakeAdapter):
                with patch.object(server.subprocess, "Popen", _FakeProc):
                    server.run_cli_exec(store, str(run.get("id")), timeout_s=5, cli_type="codebuddy", scheduler=None)

            meta = store.load_meta(str(run.get("id"))) or {}
            self.assertEqual(meta.get("codebuddy_permission_mode"), "bypassPermissions")
            self.assertEqual(_FakeProc.seen_env.get("TASK_DASHBOARD_CODEBUDDY_PERMISSION_MODE"), "bypassPermissions")
            self.assertIn("--permission-mode", _FakeProc.seen_cmd)
            self.assertEqual(_FakeProc.seen_cmd[_FakeProc.seen_cmd.index("--permission-mode") + 1], "bypassPermissions")

    def test_non_codebuddy_run_does_not_consume_permission_mode(self) -> None:
        class _FakeAdapter:
            @classmethod
            def supports_model(cls) -> bool:
                return False

            @classmethod
            def build_resume_command(
                cls,
                session_id: str,
                message: str,
                output_path,
                profile_label: str = "",
                model: str = "",
                reasoning_effort: str = "",
            ) -> list[str]:
                return ["fake-codex", "resume", session_id]

        class _FakeStream:
            def readline(self) -> str:
                return ""

            def close(self) -> None:
                return

        class _FakeProc:
            seen_env: dict[str, str] = {}

            def __init__(self, _cmd, **kwargs) -> None:
                type(self).seen_env = dict(kwargs.get("env") or {})
                self.returncode = 0
                self.stdout = _FakeStream()
                self.stderr = _FakeStream()

            def poll(self) -> int:
                return 0

            def kill(self) -> None:
                return

        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            store = server.RunStore(base / ".runs")
            session_store = server.SessionStore(base_dir=base)
            sid = "33333333-3333-3333-3333-333333333333"
            session_store.create_session(
                "task_dashboard",
                "子级02",
                cli_type="codex",
                session_id=sid,
                codebuddy_permission_mode="bypassPermissions",
            )
            run = store.create_run("task_dashboard", "子级02", sid, "hello", cli_type="codex")

            with patch.object(server, "get_adapter", return_value=_FakeAdapter):
                with patch.object(server.subprocess, "Popen", _FakeProc):
                    server.run_cli_exec(store, str(run.get("id")), timeout_s=5, cli_type="codex", scheduler=None)

            meta = store.load_meta(str(run.get("id"))) or {}
            self.assertNotIn("codebuddy_permission_mode", meta)
            self.assertNotIn("TASK_DASHBOARD_CODEBUDDY_PERMISSION_MODE", _FakeProc.seen_env)


if __name__ == "__main__":
    unittest.main()
