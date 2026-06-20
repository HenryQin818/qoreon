import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import server
from task_dashboard.claude_permissions import (
    apply_claude_permission_mode_to_runner_command,
    normalize_claude_permission_mode,
)
from task_dashboard.runtime.request_parsing import parse_session_create_request
from task_dashboard.runtime.scheduler_helpers import _extract_run_extra_fields, _sanitize_run_extra_meta


class ClaudePermissionModeTests(unittest.TestCase):
    def test_permission_mode_whitelist_and_command_projection(self) -> None:
        self.assertEqual(normalize_claude_permission_mode(""), "bypassPermissions")
        self.assertEqual(normalize_claude_permission_mode("bypassPermissions"), "bypassPermissions")
        self.assertEqual(normalize_claude_permission_mode("--dangerously-skip-permissions"), "bypassPermissions")
        self.assertEqual(normalize_claude_permission_mode("accept-edits"), "acceptEdits")
        self.assertEqual(normalize_claude_permission_mode("plan"), "plan")
        self.assertEqual(normalize_claude_permission_mode("--dangerously-allow-anything"), "bypassPermissions")

        cmd = apply_claude_permission_mode_to_runner_command(
            [
                "python3",
                "-m",
                "task_dashboard.adapters.claude_runner",
                "--permission-mode",
                "bypassPermissions",
                "resume",
            ],
            "plan",
        )
        self.assertEqual(cmd[-3:], ["--permission-mode", "plan", "resume"])

        default_cmd = apply_claude_permission_mode_to_runner_command(cmd, "not-allowed")
        self.assertIn("--permission-mode", default_cmd)
        self.assertEqual(default_cmd[default_cmd.index("--permission-mode") + 1], "bypassPermissions")

    def test_run_extra_meta_routes_common_permission_mode_to_claude_only_when_cli_is_claude(self) -> None:
        extra = _extract_run_extra_fields(
            {
                "cliType": "claude",
                "permissionMode": "plan",
                "runExtraMeta": {
                    "codebuddyPermissionMode": "bypassPermissions",
                    "model": "claude-sonnet-4-20250514",
                },
            }
        )
        self.assertEqual(extra.get("claude_permission_mode"), "plan")
        self.assertEqual(extra.get("model"), "claude-sonnet-4-6")
        self.assertNotIn("codebuddy_permission_mode", extra)

        sanitized = _sanitize_run_extra_meta(
            {"cliType": "claude", "permissionMode": "acceptEdits", "model": "辅助04-原型设计"}
        )
        self.assertEqual(sanitized.get("claude_permission_mode"), "acceptEdits")
        self.assertEqual(sanitized.get("model"), "claude-opus-4-8")
        self.assertNotIn("codebuddy_permission_mode", sanitized)

    def test_parse_session_create_request_tracks_claude_permission_explicitness(self) -> None:
        missing_payload = parse_session_create_request(
            {
                "project_id": "task_dashboard",
                "channel_name": "子级02",
                "cliType": "claude",
            }
        )
        self.assertEqual(missing_payload["cli_type"], "claude")
        self.assertEqual(missing_payload["claude_permission_mode"], "")
        self.assertIs(missing_payload["_claude_permission_mode_explicit"], False)

        explicit_payload = parse_session_create_request(
            {
                "project_id": "task_dashboard",
                "channel_name": "子级02",
                "cliType": "claude",
                "permissionMode": "accept-edits",
            }
        )
        self.assertEqual(explicit_payload["claude_permission_mode"], "acceptEdits")
        self.assertIs(explicit_payload["_claude_permission_mode_explicit"], True)

    def test_claude_run_meta_env_and_command_use_session_permission_mode_and_model(self) -> None:
        class _FakeAdapter:
            @classmethod
            def supports_model(cls) -> bool:
                return True

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
                _ = message, output_path, profile_label, reasoning_effort, permission_mode
                cmd = [
                    "python3",
                    "-m",
                    "task_dashboard.adapters.claude_runner",
                ]
                if model:
                    cmd.extend(["--model", model])
                cmd.extend(["resume", "--resume", session_id])
                return cmd

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
            sid = "44444444-4444-4444-4444-444444444444"
            session_store.create_session(
                "task_dashboard",
                "子级02",
                cli_type="claude",
                session_id=sid,
                model="claude-sonnet-4-20250514",
                claude_permission_mode="plan",
            )
            run = store.create_run("task_dashboard", "子级02", sid, "hello", cli_type="claude")

            with patch.object(server, "get_adapter", return_value=_FakeAdapter):
                with patch.object(server.subprocess, "Popen", _FakeProc):
                    server.run_cli_exec(store, str(run.get("id")), timeout_s=5, cli_type="claude", scheduler=None)

            meta = store.load_meta(str(run.get("id"))) or {}
            self.assertEqual(meta.get("claude_permission_mode"), "plan")
            self.assertEqual(meta.get("model"), "claude-opus-4-8")
            self.assertEqual(_FakeProc.seen_env.get("TASK_DASHBOARD_CLAUDE_PERMISSION_MODE"), "plan")
            self.assertIn("--permission-mode", _FakeProc.seen_cmd)
            self.assertEqual(_FakeProc.seen_cmd[_FakeProc.seen_cmd.index("--permission-mode") + 1], "plan")
            self.assertIn("--model", _FakeProc.seen_cmd)
            self.assertEqual(_FakeProc.seen_cmd[_FakeProc.seen_cmd.index("--model") + 1], "claude-opus-4-8")


if __name__ == "__main__":
    unittest.main()
