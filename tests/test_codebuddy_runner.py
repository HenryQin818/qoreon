import argparse
import contextlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from task_dashboard.adapters import codebuddy_runner


class CodeBuddyRunnerTests(unittest.TestCase):
    def _command_args(self, permission_mode: str = "") -> argparse.Namespace:
        return argparse.Namespace(
            mode="resume",
            session_id="codebuddy-session-001",
            model="glm-5.1",
            permission_mode=permission_mode,
            max_turns="",
            tools="",
            message="只回复 OK",
        )

    def test_build_command_projects_allowed_permission_mode(self) -> None:
        cmd = codebuddy_runner.build_codebuddy_command(self._command_args("bypassPermissions"))

        self.assertIn("--permission-mode", cmd)
        self.assertEqual(cmd[cmd.index("--permission-mode") + 1], "bypassPermissions")

    def test_build_command_omits_default_or_invalid_permission_mode(self) -> None:
        default_cmd = codebuddy_runner.build_codebuddy_command(self._command_args("default"))
        plan_cmd = codebuddy_runner.build_codebuddy_command(self._command_args("plan"))
        unsafe_cmd = codebuddy_runner.build_codebuddy_command(self._command_args("; rm -rf /"))

        self.assertNotIn("--permission-mode", default_cmd)
        self.assertIn("--permission-mode", plan_cmd)
        self.assertEqual(plan_cmd[plan_cmd.index("--permission-mode") + 1], "plan")
        self.assertNotIn("--permission-mode", unsafe_cmd)

    def _run_main_with_process(
        self,
        *,
        stdout: str = "",
        stderr: str = "",
        returncode: int = 0,
    ) -> tuple[int, str, str, Path]:
        td = tempfile.TemporaryDirectory(prefix="td-codebuddy-runner-")
        self.addCleanup(td.cleanup)
        output_path = Path(td.name) / "last.txt"
        proc = subprocess.CompletedProcess(
            args=["codebuddy"],
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
        )
        out_buf = io.StringIO()
        err_buf = io.StringIO()
        argv = [
            "--message",
            "只回复 OK",
            "--output-path",
            str(output_path),
            "--model",
            "glm-5.1",
            "resume",
            "--session-id",
            "codebuddy-session-001",
        ]
        with mock.patch.object(codebuddy_runner.time, "time", return_value=1780925538.0):
            run_patch = mock.patch.object(codebuddy_runner.subprocess, "run", return_value=proc)
            with run_patch:
                with contextlib.redirect_stdout(out_buf), contextlib.redirect_stderr(err_buf):
                    exit_code = codebuddy_runner.main(argv)
        return int(exit_code), out_buf.getvalue(), err_buf.getvalue(), output_path

    def _run_main_with_side_effect(self, side_effect, *, codebuddy_home: Path) -> tuple[int, str, str, Path]:
        td = tempfile.TemporaryDirectory(prefix="td-codebuddy-runner-")
        self.addCleanup(td.cleanup)
        output_path = Path(td.name) / "last.txt"
        out_buf = io.StringIO()
        err_buf = io.StringIO()
        argv = [
            "--message",
            "只回复 OK",
            "--output-path",
            str(output_path),
            "--model",
            "glm-5.1",
            "resume",
            "--session-id",
            "codebuddy-session-001",
        ]
        with mock.patch.dict("os.environ", {"CODEBUDDY_HOME": str(codebuddy_home)}):
            with mock.patch.object(codebuddy_runner.time, "time", return_value=1780925538.0):
                with mock.patch.object(codebuddy_runner.subprocess, "run", side_effect=side_effect):
                    with contextlib.redirect_stdout(out_buf), contextlib.redirect_stderr(err_buf):
                        exit_code = codebuddy_runner.main(argv)
        return int(exit_code), out_buf.getvalue(), err_buf.getvalue(), output_path

    def test_provider_timeout_without_final_text_returns_tempfail(self) -> None:
        exit_code, stdout, stderr, output_path = self._run_main_with_process(
            stderr=(
                "502 connect ETIMEDOUT 120.53.74.30:443 "
                "(target: https://copilot.tencent.com)"
            )
        )

        self.assertEqual(exit_code, 75)
        self.assertEqual(stdout, "")
        self.assertIn("ETIMEDOUT", stderr)
        self.assertFalse(output_path.exists())

    def test_unsupported_model_without_final_text_returns_config_error(self) -> None:
        exit_code, stdout, stderr, output_path = self._run_main_with_process(
            stderr="400 model [gpt-5.4-mini] service info not found"
        )

        self.assertEqual(exit_code, 78)
        self.assertEqual(stdout, "")
        self.assertIn("service info not found", stderr)
        self.assertFalse(output_path.exists())

    def test_empty_result_with_stderr_never_exits_successfully(self) -> None:
        exit_code, stdout, stderr, output_path = self._run_main_with_process(
            stderr="CodeBuddy returned an unexpected empty response"
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout, "")
        self.assertIn("unexpected empty response", stderr)
        self.assertFalse(output_path.exists())

    def test_success_json_result_writes_final_text_and_exits_zero(self) -> None:
        stdout_payload = json.dumps(
            [
                {"type": "reasoning", "rawContent": [{"text": "hidden"}]},
                {"type": "result", "subtype": "success", "is_error": False, "result": "OK-codebuddy"},
            ],
            ensure_ascii=False,
        )

        exit_code, stdout, stderr, output_path = self._run_main_with_process(stdout=stdout_payload)

        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout.strip(), "OK-codebuddy")
        self.assertEqual(stderr, "")
        self.assertEqual(output_path.read_text(encoding="utf-8").strip(), "OK-codebuddy")

    def test_user_only_json_stdout_is_suppressed_and_exits_error(self) -> None:
        stdout_payload = json.dumps(
            [
                {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": '<system-reminder data-role="memory">hidden user memory</system-reminder>',
                        }
                    ],
                },
                {"type": "reasoning", "rawContent": [{"text": "hidden reasoning"}]},
            ],
            ensure_ascii=False,
        )

        exit_code, stdout, stderr, output_path = self._run_main_with_process(stdout=stdout_payload)

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout, "")
        self.assertIn("raw stdout was suppressed", stderr)
        self.assertNotIn("system-reminder", stderr)
        self.assertFalse(output_path.exists())

    def test_raw_json_stdout_without_public_answer_never_writes_last_txt(self) -> None:
        stdout_payload = '[{"type":"message","role":"user","content":[{"type":"input_text","text":"prompt"}]}]'

        exit_code, stdout, stderr, output_path = self._run_main_with_process(stdout=stdout_payload)

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout, "")
        self.assertIn("public assistant result", stderr)
        self.assertFalse(output_path.exists())

    def test_process_events_are_emitted_before_final_text(self) -> None:
        stdout_payload = json.dumps(
            [
                {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "do work"}]},
                {"type": "reasoning", "rawContent": [{"text": "hidden reasoning"}]},
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "准备读取项目结构。"}],
                },
                {
                    "type": "function_call",
                    "timestamp": 1780925538890,
                    "callId": "call_001",
                    "name": "Agent",
                    "arguments": json.dumps({"description": "Explore project structure"}),
                },
                {
                    "type": "function_call_result",
                    "timestamp": 1780925541701,
                    "callId": "call_001",
                    "name": "Agent",
                    "status": "completed",
                    "providerData": {"toolResult": {"title": "Explored project structure"}},
                    "output": {"type": "text", "text": "very long report"},
                },
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "OK-codebuddy-final"}],
                },
                {"type": "result", "subtype": "success", "is_error": False, "result": "OK-codebuddy-final"},
            ],
            ensure_ascii=False,
        )

        exit_code, stdout, stderr, output_path = self._run_main_with_process(stdout=stdout_payload)

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        lines = [line for line in stdout.splitlines() if line.strip()]
        self.assertEqual(lines[-1], "OK-codebuddy-final")
        event_lines = [json.loads(line) for line in lines[:-1]]
        self.assertEqual([event["event_type"] for event in event_lines], ["assistant_progress", "tool_started", "tool_completed"])
        self.assertIn("调用工具: Agent description: Explore project structure", event_lines[1]["text"])
        self.assertIn("工具完成: Agent Explored project structure", event_lines[2]["text"])
        self.assertNotIn("hidden reasoning", stdout)
        self.assertNotIn("do work", stdout)
        self.assertEqual(output_path.read_text(encoding="utf-8").strip(), "OK-codebuddy-final")

    def test_stdout_session_history_events_are_filtered_by_invocation_time(self) -> None:
        stdout_payload = json.dumps(
            [
                {
                    "type": "function_call",
                    "timestamp": 1780920000000,
                    "callId": "old_call",
                    "name": "Glob",
                    "arguments": json.dumps({"pattern": "old/*"}),
                },
                {
                    "type": "function_call",
                    "timestamp": 1780925539000,
                    "callId": "new_call",
                    "name": "Read",
                    "arguments": json.dumps({"path": "config.toml"}),
                },
                {"type": "result", "subtype": "success", "is_error": False, "result": "OK-codebuddy-final"},
            ],
            ensure_ascii=False,
        )

        exit_code, stdout, stderr, output_path = self._run_main_with_process(stdout=stdout_payload)

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(output_path.read_text(encoding="utf-8").strip(), "OK-codebuddy-final")
        self.assertNotIn("old/*", stdout)
        self.assertIn("调用工具: Read path: config.toml", stdout)

    def test_jsonl_appended_events_are_emitted_when_stdout_only_has_final_text(self) -> None:
        td = tempfile.TemporaryDirectory(prefix="td-codebuddy-home-")
        self.addCleanup(td.cleanup)
        codebuddy_home = Path(td.name)
        jsonl_path = codebuddy_home / "projects" / "task-dashboard" / "codebuddy-session-001.jsonl"
        jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        jsonl_path.write_text(
            json.dumps(
                {
                    "type": "function_call",
                    "timestamp": 1780920000000,
                    "callId": "old_call",
                    "name": "Glob",
                    "arguments": json.dumps({"pattern": "old/*"}),
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        def _run(_cmd, **_kwargs):
            with jsonl_path.open("a", encoding="utf-8") as f:
                f.write(
                    json.dumps(
                        {
                            "type": "function_call",
                            "timestamp": 1780925539000,
                            "callId": "new_call",
                            "name": "Read",
                            "arguments": json.dumps({"path": "config.toml"}),
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                f.write(
                    json.dumps(
                        {
                            "type": "function_call_result",
                            "timestamp": 1780925540000,
                            "callId": "new_call",
                            "name": "Read",
                            "providerData": {"toolResult": {"title": "Read 81 lines"}},
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
            return subprocess.CompletedProcess(
                args=["codebuddy"],
                returncode=0,
                stdout=json.dumps(
                    [{"type": "result", "subtype": "success", "is_error": False, "result": "OK-codebuddy-final"}],
                    ensure_ascii=False,
                ),
                stderr="",
            )

        exit_code, stdout, stderr, output_path = self._run_main_with_side_effect(_run, codebuddy_home=codebuddy_home)

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(output_path.read_text(encoding="utf-8").strip(), "OK-codebuddy-final")
        self.assertNotIn("old/*", stdout)
        self.assertIn("调用工具: Read path: config.toml", stdout)
        self.assertIn("工具完成: Read Read 81 lines", stdout)

    def test_jsonl_assistant_fallback_writes_final_text_when_stdout_has_only_user_json(self) -> None:
        td = tempfile.TemporaryDirectory(prefix="td-codebuddy-home-")
        self.addCleanup(td.cleanup)
        codebuddy_home = Path(td.name)
        jsonl_path = codebuddy_home / "projects" / "task-dashboard" / "codebuddy-session-001.jsonl"
        jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        jsonl_path.write_text("", encoding="utf-8")

        def _run(_cmd, **_kwargs):
            with jsonl_path.open("a", encoding="utf-8") as f:
                f.write(
                    json.dumps(
                        {
                            "type": "message",
                            "role": "assistant",
                            "timestamp": 1780925539000,
                            "content": [{"type": "output_text", "text": "OK-jsonl-assistant"}],
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
            return subprocess.CompletedProcess(
                args=["codebuddy"],
                returncode=0,
                stdout=json.dumps(
                    [
                        {
                            "type": "message",
                            "role": "user",
                            "content": [
                                {
                                    "type": "input_text",
                                    "text": '<system-reminder data-role="memory">hidden</system-reminder>',
                                }
                            ],
                        }
                    ],
                    ensure_ascii=False,
                ),
                stderr="",
            )

        exit_code, stdout, stderr, output_path = self._run_main_with_side_effect(_run, codebuddy_home=codebuddy_home)

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(stdout.strip(), "OK-jsonl-assistant")
        self.assertEqual(output_path.read_text(encoding="utf-8").strip(), "OK-jsonl-assistant")


if __name__ == "__main__":
    unittest.main()
