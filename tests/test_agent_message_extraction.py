import tempfile
import unittest
from pathlib import Path

import server
from task_dashboard.runtime.run_detail_fields import (
    extract_terminal_message_from_file,
    extract_terminal_message_text,
)


class TestAgentMessageExtraction(unittest.TestCase):
    def test_extract_agent_messages_supports_unprefixed_json_continuation(self) -> None:
        log_text = "\n".join(
            [
                '[stdout] {"type":"thread.started","thread_id":"x"}',
                '{"type":"item.completed","item":{"type":"agent_message","text":"first"}}',
                '{"type":"item.completed","item":{"type":"agent_message","text":"second"}}',
            ]
        )
        got = server._extract_agent_messages(log_text, max_items=20, cli_type="codex")
        self.assertEqual(got, ["first", "second"])

    def test_extract_agent_messages_from_file_supports_unprefixed_json_continuation(self) -> None:
        content = "\n".join(
            [
                '[stdout] {"type":"thread.started","thread_id":"x"}',
                '{"type":"item.completed","item":{"type":"agent_message","text":"first"}}',
                '{"type":"item.completed","item":{"type":"agent_message","text":"second"}}',
            ]
        )
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "sample.log"
            p.write_text(content, encoding="utf-8")
            got = server._extract_agent_messages_from_file(p, max_items=20, cli_type="codex")
        self.assertEqual(got, ["first", "second"])

    def test_extract_terminal_message_text_for_claude_joins_stdout_lines(self) -> None:
        log_text = "\n".join(
            [
                "# command header",
                "[stdout] 收到",
                "[stdout] 这是 Claude 正文展示兼容验证。",
            ]
        )
        got = extract_terminal_message_text(log_text, cli_type="claude")
        self.assertEqual(got, "收到\n这是 Claude 正文展示兼容验证。")

    def test_extract_terminal_message_from_file_for_claude_joins_stdout_lines(self) -> None:
        content = "\n".join(
            [
                "# command header",
                "[stdout] 第一行",
                "[stdout] 第二行",
            ]
        )
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "sample.log"
            p.write_text(content, encoding="utf-8")
            got = extract_terminal_message_from_file(p, cli_type="claude")
        self.assertEqual(got, "第一行\n第二行")

    def test_extract_terminal_message_text_for_opencode_joins_stdout_lines(self) -> None:
        log_text = "\n".join(
            [
                "# command header",
                "[stderr] tool call ...",
                "[stdout] OpenCode 正文第一行",
                "[stdout] OpenCode 正文第二行",
            ]
        )
        got = extract_terminal_message_text(log_text, cli_type="opencode")
        self.assertEqual(got, "OpenCode 正文第一行\nOpenCode 正文第二行")

    def test_extract_terminal_message_from_file_for_opencode_joins_stdout_lines(self) -> None:
        content = "\n".join(
            [
                "# command header",
                "[stdout] 第一行",
                "[stdout] 第二行",
            ]
        )
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "sample.log"
            p.write_text(content, encoding="utf-8")
            got = extract_terminal_message_from_file(p, cli_type="opencode")
        self.assertEqual(got, "第一行\n第二行")

    def test_extract_terminal_message_text_for_gemini_pretty_json_response(self) -> None:
        log_text = "\n".join(
            [
                "# command header",
                "[stderr] Loaded cached credentials.",
                "[stdout] {",
                '[stdout]   "session_id": "b4136799-1826-40b6-8e0e-27500175c542",',
                '[stdout]   "response": "已完成初始化\\n当前职责边界: 总控分工",',
                '[stdout]   "stats": {"tokens": {"total": 120}}',
                "[stdout] }",
            ]
        )
        got = extract_terminal_message_text(log_text, cli_type="gemini")
        self.assertEqual(got, "已完成初始化\n当前职责边界: 总控分工")

    def test_extract_terminal_message_from_file_for_gemini_pretty_json_response(self) -> None:
        content = "\n".join(
            [
                "# command header",
                "[stdout] {",
                '[stdout]   "response": "Gemini 正文第一行\\nGemini 正文第二行",',
                '[stdout]   "stats": {"tokens": {"total": 120}}',
                "[stdout] }",
            ]
        )
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "sample.log"
            p.write_text(content, encoding="utf-8")
            got = extract_terminal_message_from_file(p, cli_type="gemini")
        self.assertEqual(got, "Gemini 正文第一行\nGemini 正文第二行")


if __name__ == "__main__":
    unittest.main()
