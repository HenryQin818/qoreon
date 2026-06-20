import argparse
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from task_dashboard.adapters import claude_runner


class ClaudeRunnerTests(unittest.TestCase):
    def _command_args(self, permission_mode: str = "", model: str = "") -> argparse.Namespace:
        return argparse.Namespace(
            mode="resume",
            resume="claude-session-001",
            session_id="",
            model=model,
            permission_mode=permission_mode,
            message="只回复 OK",
        )

    def test_build_command_defaults_to_stream_json_and_full_permissions(self) -> None:
        cmd = claude_runner.build_claude_command(self._command_args(model="claude-opus-4-8"))

        self.assertEqual(Path(cmd[0]).name, "claude")
        self.assertIn("-p", cmd)
        self.assertIn("--output-format", cmd)
        self.assertEqual(cmd[cmd.index("--output-format") + 1], "stream-json")
        self.assertIn("--verbose", cmd)
        self.assertIn("--resume", cmd)
        self.assertEqual(cmd[cmd.index("--resume") + 1], "claude-session-001")
        self.assertIn("--model", cmd)
        self.assertEqual(cmd[cmd.index("--model") + 1], "claude-opus-4-8")
        self.assertIn("--dangerously-skip-permissions", cmd)

    def test_build_command_normalizes_current_full_ids_and_aliases(self) -> None:
        supported_values = {
            "claude-fable-5": "claude-fable-5",
            "claude-opus-4-8": "claude-opus-4-8",
            "claude-sonnet-4-6": "claude-sonnet-4-6",
            "claude-haiku-4-5": "claude-haiku-4-5",
            "default": "claude-opus-4-8",
            "fable": "claude-fable-5",
            "fable5": "claude-fable-5",
            "fable-5": "claude-fable-5",
            "claude-fable": "claude-fable-5",
            "sonnet": "claude-sonnet-4-6",
            "opus": "claude-opus-4-8",
            "haiku": "claude-haiku-4-5",
            "best": "claude-opus-4-8",
            "opusplan": "claude-opus-4-8",
            "claude-sonnet-4-20250514": "claude-sonnet-4-6",
            "not-a-real-model": "claude-opus-4-8",
        }

        for model, expected in supported_values.items():
            with self.subTest(model=model):
                cmd = claude_runner.build_claude_command(self._command_args(model=model))
                self.assertIn("--model", cmd)
                self.assertEqual(cmd[cmd.index("--model") + 1], expected)

    def test_build_command_projects_optional_tighter_permission_mode(self) -> None:
        default_cmd = claude_runner.build_claude_command(self._command_args("default"))
        plan_cmd = claude_runner.build_claude_command(self._command_args("plan"))
        invalid_cmd = claude_runner.build_claude_command(self._command_args("; rm -rf /"))

        self.assertNotIn("--dangerously-skip-permissions", default_cmd)
        self.assertIn("--permission-mode", default_cmd)
        self.assertEqual(default_cmd[default_cmd.index("--permission-mode") + 1], "default")
        self.assertIn("--permission-mode", plan_cmd)
        self.assertEqual(plan_cmd[plan_cmd.index("--permission-mode") + 1], "plan")
        self.assertIn("--dangerously-skip-permissions", invalid_cmd)
        self.assertNotIn("; rm -rf /", invalid_cmd)

    def _run_main_with_process(
        self,
        *,
        stdout: str = "",
        stderr: str = "",
        returncode: int = 0,
    ) -> tuple[int, str, str, Path]:
        td = tempfile.TemporaryDirectory(prefix="td-claude-runner-")
        self.addCleanup(td.cleanup)
        output_path = Path(td.name) / "last.txt"

        class _FakePopen:
            def __init__(self, *args, **kwargs) -> None:
                self.args = args
                self.kwargs = kwargs
                self.stdout = io.StringIO(stdout)
                self.stderr = io.StringIO(stderr)
                self.returncode = returncode

            def wait(self) -> int:
                return self.returncode

        out_buf = io.StringIO()
        err_buf = io.StringIO()
        argv = [
            "--message",
            "只回复 OK",
            "--output-path",
            str(output_path),
            "--model",
            "claude-opus-4-8",
            "resume",
            "--resume",
            "claude-session-001",
        ]
        with mock.patch.object(claude_runner.subprocess, "run", side_effect=AssertionError("subprocess.run must not be used")):
            with mock.patch.object(claude_runner.subprocess, "Popen", _FakePopen):
                with contextlib.redirect_stdout(out_buf), contextlib.redirect_stderr(err_buf):
                    exit_code = claude_runner.main(argv)
        return int(exit_code), out_buf.getvalue(), err_buf.getvalue(), output_path

    def test_success_stream_json_writes_result_and_emits_process_events(self) -> None:
        stdout_payload = "\n".join(
            [
                json.dumps({"type": "system", "subtype": "init", "cwd": "/tmp/hidden"}, ensure_ascii=False),
                json.dumps(
                    {
                        "type": "assistant",
                        "message": {
                            "role": "assistant",
                            "content": [
                                {"type": "text", "text": "准备读取配置。"},
                                {"type": "tool_use", "id": "toolu_001", "name": "Read", "input": {"file_path": "config.toml"}},
                            ],
                        },
                    },
                    ensure_ascii=False,
                ),
                json.dumps(
                    {
                        "type": "user",
                        "message": {
                            "role": "user",
                            "content": [
                                {"type": "tool_result", "tool_use_id": "toolu_001", "content": "Read 10 lines"}
                            ],
                        },
                    },
                    ensure_ascii=False,
                ),
                json.dumps({"type": "result", "subtype": "success", "result": "OK-claude-final"}, ensure_ascii=False),
            ]
        )

        exit_code, stdout, stderr, output_path = self._run_main_with_process(stdout=stdout_payload)

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        lines = [line for line in stdout.splitlines() if line.strip()]
        self.assertEqual(lines[-1], "OK-claude-final")
        event_lines = [json.loads(line) for line in lines[:-1]]
        self.assertEqual(
            [event["event_type"] for event in event_lines],
            ["assistant_progress", "tool_started", "tool_completed"],
        )
        self.assertEqual({event["source"] for event in event_lines}, {"claude"})
        self.assertIn("调用工具: Read file_path: config.toml", stdout)
        self.assertIn("工具完成: Read Read 10 lines", stdout)
        self.assertNotIn("/tmp/hidden", stdout)
        self.assertEqual(output_path.read_text(encoding="utf-8").strip(), "OK-claude-final")

    def test_tool_arguments_are_summarized_without_raw_json_or_prompt(self) -> None:
        stdout_payload = "\n".join(
            [
                json.dumps(
                    {
                        "type": "assistant",
                        "message": {
                            "role": "assistant",
                            "content": [
                                {
                                    "type": "tool_use",
                                    "id": "toolu_ask_001",
                                    "name": "AskUserQuestion",
                                    "input": {
                                        "questions": [
                                            {"question": "第一条完整问题正文不应出现在过程轨"},
                                            {"question": "第二条完整问题正文不应出现在过程轨"},
                                        ],
                                        "prompt": "完整 prompt 不应出现在过程轨",
                                    },
                                }
                            ],
                        },
                    },
                    ensure_ascii=False,
                ),
                json.dumps({"type": "result", "subtype": "success", "result": "OK-claude-final"}, ensure_ascii=False),
            ]
        )

        exit_code, stdout, stderr, output_path = self._run_main_with_process(stdout=stdout_payload)

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("调用工具: AskUserQuestion 向用户提问 / 问题 2 项", stdout)
        self.assertNotIn('{"questions"', stdout)
        self.assertNotIn("完整 prompt", stdout)
        self.assertNotIn("完整问题正文", stdout)
        self.assertEqual(output_path.read_text(encoding="utf-8").strip(), "OK-claude-final")

    def test_user_only_stream_json_is_suppressed_and_exits_error(self) -> None:
        stdout_payload = json.dumps(
            {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": [{"type": "text", "text": '<system-reminder data-role="memory">hidden</system-reminder>'}],
                },
            },
            ensure_ascii=False,
        )

        exit_code, stdout, stderr, output_path = self._run_main_with_process(stdout=stdout_payload)

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout, "")
        self.assertIn("raw stream-json stdout was suppressed", stderr)
        self.assertNotIn("system-reminder", stderr)
        self.assertFalse(output_path.exists())


if __name__ == "__main__":
    unittest.main()
