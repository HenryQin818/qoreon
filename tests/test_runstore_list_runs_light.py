import tempfile
import unittest
from pathlib import Path
from unittest import mock

import server


class RunStoreListRunsLightModeTests(unittest.TestCase):
    def _store(self, td: str) -> server.RunStore:
        return server.RunStore(Path(td))

    def _meta(
        self,
        run_id: str,
        *,
        channel_id: str = "channel-a",
        project_id: str = "task_dashboard",
        session_id: str = "session-a",
        cli_type: str | None = "codex",
        created_at: str = "2026-05-14T10:00:00+08:00",
        hidden: bool = False,
    ) -> dict[str, object]:
        meta: dict[str, object] = {
            "id": run_id,
            "channelId": channel_id,
            "projectId": project_id,
            "sessionId": session_id,
            "status": "done",
            "createdAt": created_at,
        }
        if cli_type is not None:
            meta["cliType"] = cli_type
        if hidden:
            meta["hidden"] = True
        return meta

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

    def test_list_runs_summary_payload_skips_preview_reads(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            run = store.create_run(
                project_id="task_dashboard",
                channel_name="子级02-CCB运行时（server-并发-安全-启动）",
                session_id="019c560f-62ba-7652-a667-19c1a5249b41",
                message="hello summary",
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
                rows = store.list_runs(project_id="task_dashboard", limit=10, payload_mode="summary")

            self.assertEqual(1, len(rows))
            self.assertEqual(0, read_msg.call_count)
            self.assertEqual(0, read_last.call_count)
            self.assertEqual(0, read_log.call_count)
            self.assertNotIn("messagePreview", rows[0])
            self.assertNotIn("lastPreview", rows[0])
            self.assertNotIn("logPreview", rows[0])

    def test_list_runs_filters_session_and_hidden_before_reconcile(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = self._store(td)
            snapshot = [
                self._meta("hidden-match", session_id="target-session", hidden=True),
                self._meta("session-miss", session_id="other-session"),
                self._meta("session-match", session_id="target-session"),
            ]
            reconciled: list[str] = []

            def reconcile(meta: dict[str, object]) -> tuple[dict[str, object], bool]:
                reconciled.append(str(meta.get("id") or ""))
                return dict(meta), False

            with (
                mock.patch.object(store, "_snapshot_live_run_index", return_value=snapshot),
                mock.patch.object(store, "reconcile_meta", side_effect=reconcile),
            ):
                rows = store.list_runs(session_id="target-session", limit=10, payload_mode="none")

            self.assertEqual(["session-match"], [row.get("id") for row in rows])
            self.assertEqual(["session-match"], reconciled)

    def test_list_runs_prefilters_project_channel_cli_type_and_created_at(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = self._store(td)
            snapshot = [
                self._meta("project-match", project_id="project-a", channel_id="channel-a"),
                self._meta("channel-match", project_id="project-b", channel_id="channel-b"),
                self._meta("gemini-match", project_id="project-c", channel_id="channel-c", cli_type="gemini"),
                self._meta("default-codex-match", project_id="project-d", channel_id="channel-d", cli_type=None),
                self._meta("time-before", created_at="2026-05-14T09:00:00+08:00"),
                self._meta("time-match", created_at="2026-05-14T10:00:00+08:00"),
                self._meta("time-after", created_at="2026-05-14T11:00:00+08:00"),
            ]

            with (
                mock.patch.object(store, "_snapshot_live_run_index", return_value=snapshot),
                mock.patch.object(store, "reconcile_meta", side_effect=lambda meta: (dict(meta), False)),
            ):
                cases = [
                    (
                        {"project_id": "project-a", "payload_mode": "none"},
                        ["project-match"],
                    ),
                    (
                        {"channel_id": "channel-b", "payload_mode": "none"},
                        ["channel-match"],
                    ),
                    (
                        {"cli_type": "gemini", "payload_mode": "none"},
                        ["gemini-match"],
                    ),
                    (
                        {"project_id": "project-d", "cli_type": "codex", "payload_mode": "none"},
                        ["default-codex-match"],
                    ),
                    (
                        {
                            "after_created_at": "2026-05-14T09:30:00+08:00",
                            "before_created_at": "2026-05-14T10:30:00+08:00",
                            "payload_mode": "none",
                        },
                        [
                            "project-match",
                            "channel-match",
                            "gemini-match",
                            "default-codex-match",
                            "time-match",
                        ],
                    ),
                ]
                for kwargs, expected_ids in cases:
                    with self.subTest(kwargs=kwargs):
                        rows = store.list_runs(limit=10, **kwargs)
                        self.assertEqual(expected_ids, [row.get("id") for row in rows])

    def test_list_runs_reconciles_and_saves_only_filter_matches(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = self._store(td)
            snapshot = [
                self._meta("project-miss", project_id="other-project"),
                self._meta("project-match", project_id="task_dashboard"),
            ]

            def reconcile(meta: dict[str, object]) -> tuple[dict[str, object], bool]:
                updated = dict(meta)
                updated["lastPreview"] = "reconciled"
                return updated, True

            with (
                mock.patch.object(store, "_snapshot_live_run_index", return_value=snapshot),
                mock.patch.object(store, "reconcile_meta", side_effect=reconcile) as reconcile_meta,
                mock.patch.object(store, "save_meta") as save_meta,
            ):
                rows = store.list_runs(project_id="task_dashboard", limit=10, payload_mode="none")

            self.assertEqual(["project-match"], [row.get("id") for row in rows])
            self.assertEqual(["project-match"], [call.args[0].get("id") for call in reconcile_meta.call_args_list])
            save_meta.assert_called_once()
            self.assertEqual("project-match", save_meta.call_args.args[0])
            self.assertEqual("reconciled", save_meta.call_args.args[1].get("lastPreview"))

    def test_list_runs_limit_counts_after_prefilter(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = self._store(td)
            snapshot = [
                self._meta("skip-project", project_id="other-project"),
                self._meta("match-1", project_id="task_dashboard"),
                self._meta("match-2", project_id="task_dashboard"),
                self._meta("match-3", project_id="task_dashboard"),
            ]
            reconciled: list[str] = []

            def reconcile(meta: dict[str, object]) -> tuple[dict[str, object], bool]:
                reconciled.append(str(meta.get("id") or ""))
                return dict(meta), False

            with (
                mock.patch.object(store, "_snapshot_live_run_index", return_value=snapshot),
                mock.patch.object(store, "reconcile_meta", side_effect=reconcile),
            ):
                rows = store.list_runs(project_id="task_dashboard", limit=2, payload_mode="none")

            self.assertEqual(["match-1", "match-2"], [row.get("id") for row in rows])
            self.assertEqual(["match-1", "match-2"], reconciled)


if __name__ == "__main__":
    unittest.main()
