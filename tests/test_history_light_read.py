import unittest

from task_dashboard.runtime.history_light_read import history_light_read_response


class _FakeSessionStore:
    def get_session(self, session_id: str, *, project_id: str = ""):
        if session_id != "019d684a-cbb6-7eb3-b95b-7ec9c30ecfd3":
            return None
        return {"id": session_id, "project_id": project_id or "task_dashboard"}


class _FakeRunStore:
    def list_runs(self, **kwargs):
        self.kwargs = kwargs
        return [
            {
                "id": "20260410-021239-716ffb41",
                "status": "done",
                "messagePreview": "请处理",
                "lastPreview": "已完成",
                "createdAt": "2026-04-10T02:12:39+0800",
                "finishedAt": "2026-04-10T02:12:47+0800",
            }
        ]


class _FakeMemoStore:
    def summary(self, project_id: str, session_id: str):
        return {
            "project_id": project_id,
            "session_id": session_id,
            "memo_count": 2,
            "memo_updated_at": "2026-04-12T00:00:00+0800",
            "memo_has_items": True,
            "memo_summary_source": "conversation_memos",
            "active_path_runtime": {
                "scope": "conversation_memos",
                "delivery_mode": "fresh_cache",
                "cache_ttl_ms": 1500,
                "completion_budget_ms": 800,
                "cache_age_ms": 0,
            },
        }


class HistoryLightReadTests(unittest.TestCase):
    def test_history_lite_uses_light_payload_mode(self) -> None:
        store = _FakeRunStore()
        code, payload = history_light_read_response(
            query_string="project_id=task_dashboard&limit=5",
            session_id="019d684a-cbb6-7eb3-b95b-7ec9c30ecfd3",
            session_store=_FakeSessionStore(),
            store=store,
            infer_project_id_for_session=lambda _store, _sid: "task_dashboard",
            conversation_memo_store=_FakeMemoStore(),
        )

        self.assertEqual(code, 200)
        self.assertEqual(store.kwargs.get("payload_mode"), "light")
        self.assertEqual(store.kwargs.get("limit"), 5)
        self.assertEqual(payload.get("count"), 1)
        item = (payload.get("items") or [{}])[0]
        self.assertEqual(item.get("run_id"), "20260410-021239-716ffb41")
        self.assertEqual(item.get("preview"), "已完成")
        self.assertEqual(item.get("detail_url"), "/api/codex/run/20260410-021239-716ffb41")
        runtime = payload.get("active_path_runtime") or {}
        self.assertEqual(runtime.get("scope"), "history_lite")
        self.assertEqual(runtime.get("delivery_mode"), "direct_http_light_read")
        memo_summary = payload.get("memo_summary") or {}
        self.assertEqual(memo_summary.get("memo_count"), 2)
        self.assertEqual(memo_summary.get("memo_summary_source"), "conversation_memos")
        self.assertTrue(memo_summary.get("memo_has_items"))


if __name__ == "__main__":
    unittest.main()
