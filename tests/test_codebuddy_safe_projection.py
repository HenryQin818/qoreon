import json
import tempfile
import unittest
from pathlib import Path

import server
from task_dashboard.runtime.heartbeat_registry import (
    _build_session_latest_run_summary,
    _build_session_summary_from_meta,
)
from task_dashboard.runtime.run_detail_fields import (
    CODEBUDDY_UNSAFE_FINAL_PLACEHOLDER,
    extract_terminal_message_text,
    safe_codebuddy_visible_text,
)
from task_dashboard.runtime.run_routes import get_run_detail_response


def _raw_codebuddy_history_json() -> str:
    return json.dumps(
        [
            {
                "id": "raw-user-message",
                "type": "message",
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": '<system-reminder data-role="memory"><memory>secret</memory></system-reminder>',
                    }
                ],
            }
        ],
        ensure_ascii=False,
        indent=2,
    )


class CodeBuddySafeProjectionTests(unittest.TestCase):
    def test_safe_codebuddy_visible_text_hides_raw_user_memory_json(self) -> None:
        raw = _raw_codebuddy_history_json()

        visible = safe_codebuddy_visible_text(raw)

        self.assertEqual(visible, CODEBUDDY_UNSAFE_FINAL_PLACEHOLDER)
        self.assertNotIn("system-reminder", visible)
        self.assertNotIn("role", visible)

    def test_safe_codebuddy_visible_text_extracts_safe_result_from_event_array(self) -> None:
        raw = json.dumps(
            [
                {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "hello"}]},
                {"type": "result", "subtype": "success", "is_error": False, "result": "安全最终正文"},
            ],
            ensure_ascii=False,
        )

        self.assertEqual(safe_codebuddy_visible_text(raw), "安全最终正文")

    def test_extract_terminal_message_text_for_codebuddy_hides_pretty_raw_json(self) -> None:
        raw = _raw_codebuddy_history_json()
        log_text = "\n".join(f"[stdout] {line}" for line in raw.splitlines())

        visible = extract_terminal_message_text(log_text, cli_type="codebuddy")

        self.assertEqual(visible, CODEBUDDY_UNSAFE_FINAL_PLACEHOLDER)

    def test_run_detail_for_codebuddy_hides_raw_last_message(self) -> None:
        raw = _raw_codebuddy_history_json()
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            created = store.create_run(
                project_id="task_dashboard",
                channel_name="子级03-多CLI适配器（codex-claude-opencode）",
                session_id="codebuddy-session-raw",
                message="ping",
                cli_type="codebuddy",
            )
            run_id = str(created.get("id") or "").strip()
            meta = store.load_meta(run_id) or {}
            meta["status"] = "done"
            meta["lastPreview"] = raw
            store.save_meta(run_id, meta)
            store._paths(run_id)["last"].write_text(raw, encoding="utf-8")
            store._paths(run_id)["log"].write_text("", encoding="utf-8")

            code, payload = get_run_detail_response(
                run_id=run_id,
                store=store,
                scheduler=None,
                maybe_trigger_restart_recovery_lazy=lambda *_args, **_kwargs: 0,
                maybe_trigger_queued_recovery_lazy=lambda *_args, **_kwargs: 0,
                build_run_observability_fields=lambda *_args, **_kwargs: {},
                error_hint=lambda _err: "",
            )

        self.assertEqual(code, 200)
        self.assertEqual(payload.get("lastMessage"), CODEBUDDY_UNSAFE_FINAL_PLACEHOLDER)
        self.assertEqual((payload.get("run") or {}).get("lastPreview"), CODEBUDDY_UNSAFE_FINAL_PLACEHOLDER)
        self.assertNotIn("system-reminder", str(payload.get("lastMessage") or ""))

    def test_run_detail_for_codex_keeps_existing_last_message_semantics(self) -> None:
        raw = _raw_codebuddy_history_json()
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            created = store.create_run(
                project_id="task_dashboard",
                channel_name="子级02-CCB运行时（server-并发-安全-启动）",
                session_id="codex-session-raw",
                message="ping",
                cli_type="codex",
            )
            run_id = str(created.get("id") or "").strip()
            meta = store.load_meta(run_id) or {}
            meta["status"] = "done"
            store.save_meta(run_id, meta)
            store._paths(run_id)["last"].write_text(raw, encoding="utf-8")

            code, payload = get_run_detail_response(
                run_id=run_id,
                store=store,
                scheduler=None,
                maybe_trigger_restart_recovery_lazy=lambda *_args, **_kwargs: 0,
                maybe_trigger_queued_recovery_lazy=lambda *_args, **_kwargs: 0,
                build_run_observability_fields=lambda *_args, **_kwargs: {},
                error_hint=lambda _err: "",
            )

        self.assertEqual(code, 200)
        self.assertIn('"role": "user"', str(payload.get("lastMessage") or ""))

    def test_list_runs_for_codebuddy_hides_raw_last_preview(self) -> None:
        raw = _raw_codebuddy_history_json()
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            created = store.create_run(
                project_id="task_dashboard",
                channel_name="子级03-多CLI适配器（codex-claude-opencode）",
                session_id="codebuddy-session-list",
                message="ping",
                cli_type="codebuddy",
            )
            run_id = str(created.get("id") or "").strip()
            meta = store.load_meta(run_id) or {}
            meta["status"] = "done"
            store.save_meta(run_id, meta)
            store._paths(run_id)["last"].write_text(raw, encoding="utf-8")

            rows = store.list_runs(project_id="task_dashboard", limit=10, payload_mode="light")

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].get("lastPreview"), CODEBUDDY_UNSAFE_FINAL_PLACEHOLDER)

    def test_session_summary_for_codebuddy_hides_raw_latest_ai_msg(self) -> None:
        raw = _raw_codebuddy_history_json()
        meta = {
            "id": "run-codebuddy-raw",
            "status": "done",
            "cliType": "codebuddy",
            "createdAt": "2026-06-09T11:41:03+0800",
            "lastPreview": raw,
            "messagePreview": "请处理",
        }

        summary = _build_session_summary_from_meta(meta)
        latest = _build_session_latest_run_summary(summary, {})

        self.assertEqual(summary.get("latest_ai_msg"), CODEBUDDY_UNSAFE_FINAL_PLACEHOLDER)
        self.assertEqual(latest.get("latest_ai_msg"), CODEBUDDY_UNSAFE_FINAL_PLACEHOLDER)
        self.assertEqual(latest.get("preview"), CODEBUDDY_UNSAFE_FINAL_PLACEHOLDER)


if __name__ == "__main__":
    unittest.main()
