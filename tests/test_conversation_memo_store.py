import tempfile
import unittest
from pathlib import Path

from task_dashboard.conversation_memo_store import ConversationMemoStore


class ConversationMemoStoreTests(unittest.TestCase):
    def test_create_list_delete_clear(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = ConversationMemoStore(Path(td), max_items_per_session=5)
            pid = "task_dashboard"
            sid = "019c560f-62ba-7652-b714-d462b4335225"

            item1, count1 = store.create(
                pid,
                sid,
                text="第一条备忘",
                attachments=[{"filename": "a.png", "url": "/.runs/attachments/a.png"}],
            )
            self.assertTrue(item1.get("id", "").startswith("memo_"))
            self.assertEqual(count1, 1)

            item2, count2 = store.create(
                pid,
                sid,
                text="第二条备忘",
                attachments=[],
            )
            self.assertEqual(count2, 2)

            payload = store.list(pid, sid)
            self.assertEqual(payload.get("count"), 2)
            items = payload.get("items") or []
            self.assertEqual(items[0].get("id"), item2.get("id"))
            self.assertEqual(items[1].get("id"), item1.get("id"))

            deleted, left = store.delete(pid, sid, [str(item2.get("id") or "")])
            self.assertEqual(deleted, 1)
            self.assertEqual(left, 1)

            cleared = store.clear(pid, sid)
            self.assertEqual(cleared, 1)
            payload2 = store.list(pid, sid)
            self.assertEqual(payload2.get("count"), 0)
            self.assertEqual(payload2.get("items"), [])

    def test_create_rejects_empty_memo(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = ConversationMemoStore(Path(td))
            with self.assertRaises(ValueError):
                store.create(
                    "task_dashboard",
                    "019c560f-62ba-7652-b714-d462b4335225",
                    text="",
                    attachments=[],
                )

    def test_trims_old_items_by_limit(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = ConversationMemoStore(Path(td), max_items_per_session=3)
            pid = "task_dashboard"
            sid = "019c560f-62ba-7652-b714-d462b4335225"
            for i in range(6):
                store.create(pid, sid, text=f"memo-{i}", attachments=[])
            payload = store.list(pid, sid)
            self.assertEqual(payload.get("count"), 3)
            items = payload.get("items") or []
            self.assertEqual(len(items), 3)
            self.assertEqual(items[0].get("text"), "memo-5")
            self.assertEqual(items[-1].get("text"), "memo-3")

    def test_reorder_preserves_unmentioned_items_at_tail(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = ConversationMemoStore(Path(td), max_items_per_session=5)
            pid = "task_dashboard"
            sid = "019c560f-62ba-7652-b714-d462b4335225"
            item1, _ = store.create(pid, sid, text="第一条", attachments=[])
            item2, _ = store.create(pid, sid, text="第二条", attachments=[])
            item3, _ = store.create(pid, sid, text="第三条", attachments=[])

            reordered, count = store.reorder(
                pid,
                sid,
                [
                    str(item1.get("id") or ""),
                    "missing_memo",
                    str(item3.get("id") or ""),
                    str(item1.get("id") or ""),
                ],
            )

            self.assertEqual(reordered, 2)
            self.assertEqual(count, 3)
            payload = store.list(pid, sid)
            items = payload.get("items") or []
            self.assertEqual([it.get("id") for it in items], [item1.get("id"), item3.get("id"), item2.get("id")])


if __name__ == "__main__":
    unittest.main()
