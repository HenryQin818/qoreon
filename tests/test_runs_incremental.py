import tempfile
import unittest
from pathlib import Path

import server


class RunsIncrementalFilterTests(unittest.TestCase):
    def _create_run_with_created_at(
        self,
        store: server.RunStore,
        *,
        created_at: str,
        project_id: str = "p",
        channel_name: str = "c",
        session_id: str = "s",
    ) -> str:
        run = store.create_run(project_id, channel_name, session_id, "msg")
        rid = str(run.get("id") or "")
        meta = store.load_meta(rid) or {}
        meta["createdAt"] = created_at
        meta["status"] = "done"
        store.save_meta(rid, meta)
        return rid

    def test_list_runs_after_created_at_filter(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            r1 = self._create_run_with_created_at(store, created_at="2026-02-27T10:00:00+0800")
            r2 = self._create_run_with_created_at(store, created_at="2026-02-27T10:05:00+0800")
            r3 = self._create_run_with_created_at(store, created_at="2026-02-27T10:10:00+0800")
            out = store.list_runs(
                project_id="p",
                session_id="s",
                limit=20,
                after_created_at="2026-02-27T10:05:00+0800",
            )
            got = {str(x.get("id") or "") for x in out}
            self.assertEqual(got, {r3})
            self.assertNotIn(r1, got)
            self.assertNotIn(r2, got)

    def test_list_runs_before_created_at_filter(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            r1 = self._create_run_with_created_at(store, created_at="2026-02-27T10:00:00+0800")
            r2 = self._create_run_with_created_at(store, created_at="2026-02-27T10:05:00+0800")
            r3 = self._create_run_with_created_at(store, created_at="2026-02-27T10:10:00+0800")
            out = store.list_runs(
                project_id="p",
                session_id="s",
                limit=20,
                before_created_at="2026-02-27T10:05:00+0800",
            )
            got = {str(x.get("id") or "") for x in out}
            self.assertEqual(got, {r1})
            self.assertNotIn(r2, got)
            self.assertNotIn(r3, got)

    def test_list_runs_after_before_range_filter(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            r1 = self._create_run_with_created_at(store, created_at="2026-02-27T10:00:00+0800")
            r2 = self._create_run_with_created_at(store, created_at="2026-02-27T10:05:00+0800")
            r3 = self._create_run_with_created_at(store, created_at="2026-02-27T10:10:00+0800")
            out = store.list_runs(
                project_id="p",
                session_id="s",
                limit=20,
                after_created_at="2026-02-27T10:00:00+0800",
                before_created_at="2026-02-27T10:10:00+0800",
            )
            got = {str(x.get("id") or "") for x in out}
            self.assertEqual(got, {r2})
            self.assertNotIn(r1, got)
            self.assertNotIn(r3, got)


if __name__ == "__main__":
    unittest.main()
