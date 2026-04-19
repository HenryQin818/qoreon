import unittest

from task_dashboard.runtime.active_session_projection import build_active_session_projection


class ActiveSessionProjectionTests(unittest.TestCase):
    def test_projection_merges_session_summary_history_and_memos(self) -> None:
        payload = build_active_session_projection(
            project_id="task_dashboard",
            session_id="019d684a-cbb6-7eb3-b95b-7ec9c30ecfd3",
            session_detail={
                "session_display_state": "done",
                "session_display_reason": "latest_run_summary:done",
                "latest_run_summary": {
                    "run_id": "20260410-021239-716ffb41",
                    "status": "done",
                    "preview": "已完成",
                },
            },
            history_lite_payload={
                "items": [
                    {
                        "item_id": "run:20260410-021239-716ffb41",
                        "entity_type": "run_message",
                        "run_id": "20260410-021239-716ffb41",
                        "status": "done",
                        "preview": "历史摘要",
                    }
                ]
            },
            memo_payload={
                "count": 1,
                "items": [
                    {
                        "id": "memo_1",
                        "text": "待发要点",
                        "attachments": [],
                        "createdAt": "2026-04-10T16:00:00+0800",
                        "updatedAt": "2026-04-10T16:00:00+0800",
                    }
                ],
            },
        )

        self.assertEqual(payload.get("version"), "v1")
        self.assertEqual(payload.get("source"), "runtime_active_projection")
        self.assertTrue(payload.get("focused_session_only"))
        self.assertGreater(int(payload.get("last_seq") or 0), 0)
        self.assertTrue(str(payload.get("resume_token") or "").endswith(f":{payload.get('last_seq')}"))
        items = payload.get("items") or []
        self.assertEqual([item.get("entity_type") for item in items], ["session_summary", "run_message", "memo"])
        summary = payload.get("summary") or {}
        self.assertEqual(summary.get("display_state"), "done")
        self.assertEqual(summary.get("history_lite_count"), 1)
        self.assertEqual(summary.get("memo_count"), 1)


if __name__ == "__main__":
    unittest.main()
