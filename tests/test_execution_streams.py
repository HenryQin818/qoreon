import json
import tempfile
import unittest
from pathlib import Path

from task_dashboard.runtime.execution_streams import capture_agent_text
from task_dashboard.runtime.run_detail_fields import extract_process_events_from_file


class TestExecutionStreams(unittest.TestCase):
    def test_capture_agent_text_appends_structured_process_rows(self) -> None:
        process_state = {}
        meta = {}

        def _parse(_adapter_cls, payload: str):
            return json.loads(payload)

        def _extract(parsed):
            item = parsed.get("item") or {}
            return str(item.get("text") or "")

        capture_agent_text(
            '{"type":"item.completed","item":{"type":"agent_message","text":"第一条过程消息"}}',
            adapter_cls=object(),
            process_state=process_state,
            meta=meta,
            parse_adapter_output_line=_parse,
            extract_agent_message_text_from_parsed=_extract,
            safe_text=lambda value, max_len: str(value)[:max_len],
            now_iso=lambda: "2026-03-20T00:08:15+0800",
        )

        self.assertEqual(process_state["count"], 1)
        self.assertEqual(process_state["latest"], "第一条过程消息")
        self.assertEqual(
            meta["processRows"],
            [{"text": "第一条过程消息", "at": "2026-03-20T00:08:15+0800"}],
        )

    def test_capture_agent_text_skips_duplicate_last_text(self) -> None:
        process_state = {
            "count": 1,
            "latest": "第一条过程消息",
            "last_text": "第一条过程消息",
            "rows": [{"text": "第一条过程消息", "at": "2026-03-20T00:08:15+0800"}],
        }
        meta = {"processRows": list(process_state["rows"]), "agentMessagesCount": 1}

        def _parse(_adapter_cls, payload: str):
            return json.loads(payload)

        def _extract(parsed):
            item = parsed.get("item") or {}
            return str(item.get("text") or "")

        capture_agent_text(
            '{"type":"item.completed","item":{"type":"agent_message","text":"第一条过程消息"}}',
            adapter_cls=object(),
            process_state=process_state,
            meta=meta,
            parse_adapter_output_line=_parse,
            extract_agent_message_text_from_parsed=_extract,
            safe_text=lambda value, max_len: str(value)[:max_len],
            now_iso=lambda: "2026-03-20T00:09:15+0800",
        )

        self.assertEqual(process_state["count"], 1)
        self.assertEqual(
            meta["processRows"],
            [{"text": "第一条过程消息", "at": "2026-03-20T00:08:15+0800"}],
        )

    def test_capture_command_event_appends_process_event(self) -> None:
        process_state = {}
        meta = {}

        def _parse(_adapter_cls, payload: str):
            return json.loads(payload)

        def _extract(_parsed):
            return ""

        capture_agent_text(
            '{"type":"item.started","item":{"type":"command_execution","command":"mkdir -p output/imagegen"}}',
            adapter_cls=object(),
            process_state=process_state,
            meta=meta,
            parse_adapter_output_line=_parse,
            extract_agent_message_text_from_parsed=_extract,
            safe_text=lambda value, max_len: str(value)[:max_len],
            now_iso=lambda: "2026-05-08T10:00:00+0800",
        )

        self.assertEqual(process_state["event_count"], 1)
        self.assertEqual(meta["process_events"][0]["event_type"], "command_started")
        self.assertEqual(meta["processEvents"], meta["process_events"])
        self.assertEqual(meta["processRows"][0]["text"], "执行命令: mkdir -p output/imagegen")

    def test_capture_codebuddy_process_event_preserves_explicit_text_and_refs(self) -> None:
        process_state = {}
        meta = {}

        def _parse(_adapter_cls, payload: str):
            return json.loads(payload)

        def _extract(_parsed):
            return ""

        capture_agent_text(
            json.dumps(
                {
                    "type": "tool_call.started",
                    "event_type": "tool_started",
                    "item_type": "function_call",
                    "title": "Agent",
                    "text": "调用工具: Agent description: Explore project structure",
                    "source": "codebuddy",
                    "call_id": "call_001",
                    "raw_ref": "call_001",
                },
                ensure_ascii=False,
            ),
            adapter_cls=object(),
            process_state=process_state,
            meta=meta,
            parse_adapter_output_line=_parse,
            extract_agent_message_text_from_parsed=_extract,
            safe_text=lambda value, max_len: str(value)[:max_len],
            now_iso=lambda: "2026-06-08T10:00:00+0800",
        )

        self.assertEqual(process_state["event_count"], 1)
        row = meta["processRows"][0]
        self.assertEqual(row["event_type"], "tool_started")
        self.assertEqual(row["text"], "调用工具: Agent description: Explore project structure")
        self.assertEqual(row["source"], "codebuddy")
        self.assertEqual(row["call_id"], "call_001")

    def test_capture_process_event_sanitizes_raw_tool_arguments(self) -> None:
        process_state = {}
        meta = {}

        def _parse(_adapter_cls, payload: str):
            return json.loads(payload)

        def _extract(_parsed):
            return ""

        capture_agent_text(
            json.dumps(
                {
                    "type": "tool_call.started",
                    "event_type": "tool_started",
                    "item_type": "function_call",
                    "title": "AskUserQuestion",
                    "text": (
                        '调用工具: AskUserQuestion {"questions":[{"question":"第一条完整问题正文不应出现在过程轨"}],'
                        '"prompt":"完整 prompt 不应出现在过程轨"}'
                    ),
                    "source": "claude",
                    "call_id": "call_ask_001",
                    "raw_ref": "call_ask_001",
                },
                ensure_ascii=False,
            ),
            adapter_cls=object(),
            process_state=process_state,
            meta=meta,
            parse_adapter_output_line=_parse,
            extract_agent_message_text_from_parsed=_extract,
            safe_text=lambda value, max_len: str(value)[:max_len],
            now_iso=lambda: "2026-06-08T10:00:00+0800",
        )

        row = meta["processRows"][0]
        self.assertEqual(row["text"], "调用工具: AskUserQuestion 向用户提问 / 问题 1 项")
        blob = json.dumps(meta, ensure_ascii=False)
        self.assertNotIn('{"questions"', blob)
        self.assertNotIn("完整 prompt", blob)
        self.assertNotIn("完整问题正文", blob)

    def test_extract_codebuddy_process_events_from_stdout_log_file(self) -> None:
        log_text = "\n".join(
            [
                "$ codebuddy -p --output-format json",
                '[stdout] {"type":"tool_call.started","event_type":"tool_started","item_type":"function_call",'
                '"title":"Read","text":"调用工具: Read config.toml","source":"codebuddy",'
                '"at":"2026-06-09T09:23:53+0800","raw_ref":"call_001","call_id":"call_001"}',
                '[stdout] {"type":"tool_call.completed","event_type":"tool_completed","item_type":"function_call_result",'
                '"title":"Read","text":"工具完成: Read Read 81 lines","source":"codebuddy",'
                '"at":"2026-06-09T09:23:54+0800","raw_ref":"call_001","call_id":"call_001"}',
                "[stdout] OK-codebuddy-final",
            ]
        )

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "run.log.txt"
            path.write_text(log_text, encoding="utf-8")
            events = extract_process_events_from_file(path, cli_type="codebuddy")

        self.assertEqual([event["event_type"] for event in events], ["tool_started", "tool_completed"])
        self.assertEqual(events[0]["text"], "调用工具: Read config.toml")
        self.assertEqual(events[0]["at"], "2026-06-09T09:23:53+0800")
        self.assertEqual(events[1]["source"], "codebuddy")


if __name__ == "__main__":
    unittest.main()
