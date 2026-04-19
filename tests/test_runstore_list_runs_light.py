import tempfile
import unittest
from pathlib import Path
from unittest import mock

import server


class RunStoreListRunsLightModeTests(unittest.TestCase):
    def test_list_runs_include_payload_false_skips_preview_reads(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            run = store.create_run(
                project_id="task_dashboard",
                channel_name="子级02-CCB运行时（server-并发-安全-启动）",
                session_id="019c560f-62ba-7652-b714-d462b4335225",
                message="hello",
            )
            rid = str(run.get("id") or "")
            paths = store._paths(rid)
            paths["last"].write_text("last output", encoding="utf-8")
            paths["log"].write_text("log output", encoding="utf-8")

            with (
                mock.patch.object(store, "read_msg", wraps=store.read_msg) as read_msg,
                mock.patch.object(store, "read_last", wraps=store.read_last) as read_last,
                mock.patch.object(store, "read_log", wraps=store.read_log) as read_log,
            ):
                rows = store.list_runs(project_id="task_dashboard", limit=10, include_payload=False)

            self.assertEqual(1, len(rows))
            self.assertEqual(0, read_msg.call_count)
            self.assertEqual(0, read_last.call_count)
            self.assertEqual(0, read_log.call_count)
            self.assertNotIn("messagePreview", rows[0])
            self.assertNotIn("logPreview", rows[0])

    def test_list_runs_default_keeps_payload_enrichment(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            run = store.create_run(
                project_id="task_dashboard",
                channel_name="子级02-CCB运行时（server-并发-安全-启动）",
                session_id="019c560f-62ba-7652-b714-d462b4335225",
                message="hello",
            )
            rid = str(run.get("id") or "")
            paths = store._paths(rid)
            paths["last"].write_text("last output", encoding="utf-8")
            paths["log"].write_text("log output", encoding="utf-8")

            rows = store.list_runs(project_id="task_dashboard", limit=10)
            self.assertEqual(1, len(rows))
            self.assertTrue(str(rows[0].get("messagePreview") or "").strip())
            self.assertTrue(str(rows[0].get("lastPreview") or "").strip())

    def test_list_runs_light_payload_keeps_basic_previews_but_skips_log_reads(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            run = store.create_run(
                project_id="task_dashboard",
                channel_name="子级02-CCB运行时（server-并发-安全-启动）",
                session_id="019c560f-62ba-7652-a667-19c1a5249b41",
                message="hello light",
            )
            rid = str(run.get("id") or "")
            paths = store._paths(rid)
            paths["last"].write_text("assistant preview", encoding="utf-8")
            paths["log"].write_text("log output", encoding="utf-8")

            with (
                mock.patch.object(store, "read_msg", wraps=store.read_msg) as read_msg,
                mock.patch.object(store, "read_last", wraps=store.read_last) as read_last,
                mock.patch.object(store, "read_log", wraps=store.read_log) as read_log,
            ):
                rows = store.list_runs(project_id="task_dashboard", limit=10, payload_mode="light")

            self.assertEqual(1, len(rows))
            self.assertGreaterEqual(read_msg.call_count, 1)
            self.assertGreaterEqual(read_last.call_count, 1)
            self.assertEqual(0, read_log.call_count)
            self.assertTrue(str(rows[0].get("messagePreview") or "").strip())
            self.assertTrue(str(rows[0].get("lastPreview") or "").strip())
            self.assertNotIn("logPreview", rows[0])


if __name__ == "__main__":
    unittest.main()
