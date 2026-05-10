import json
import unittest

from task_dashboard.runtime.execution_streams import capture_agent_text


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
        self.assertEqual(meta["processRows"][0]["text"], "执行命令: mkdir -p output/imagegen")


if __name__ == "__main__":
    unittest.main()
