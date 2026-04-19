import unittest
from unittest import mock

from task_dashboard.runtime import session_directory_snapshot as snapshot


class SessionDirectorySnapshotTests(unittest.TestCase):
    def setUp(self) -> None:
        snapshot.invalidate_session_directory_snapshot("")

    def _build(
        self,
        *,
        light_builder,
        fallback_builder,
        config=None,
        channel_name: str = "",
        include_deleted: bool = False,
    ):
        return snapshot.build_session_directory_snapshot_payload(
            project_id="task_dashboard",
            channel_name=channel_name,
            include_deleted=include_deleted,
            environment_name="stable",
            worktree_root="/tmp/task-dashboard",
            light_builder=light_builder,
            fallback_builder=fallback_builder,
            config=config
            if config is not None
            else snapshot.SessionDirectorySnapshotConfig(enabled=True, ttl_ms=1000, prewarm_enabled=True),
        )

    def test_snapshot_hit_returns_deep_copy_and_skips_fallback(self) -> None:
        light_builder = mock.Mock(return_value={"sessions": [{"id": "session-a"}]})
        fallback_builder = mock.Mock(return_value={"sessions": [{"id": "fallback"}]})

        with mock.patch.object(
            snapshot.time,
            "monotonic",
            side_effect=[100.0, 100.0, 100.0, 100.01, 100.01, 100.2, 100.2],
        ):
            first = self._build(light_builder=light_builder, fallback_builder=fallback_builder)
            first["sessions"][0]["id"] = "mutated"
            second = self._build(light_builder=light_builder, fallback_builder=fallback_builder)

        self.assertEqual(light_builder.call_count, 1)
        self.assertEqual(fallback_builder.call_count, 0)
        self.assertEqual(second["sessions"][0]["id"], "session-a")
        metadata = second.get("directory_snapshot") or {}
        self.assertTrue(metadata.get("enabled"))
        self.assertTrue(metadata.get("hit"))
        self.assertEqual(metadata.get("build_source"), "snapshot")

    def test_snapshot_ttl_expired_rebuilds_light_payload(self) -> None:
        light_builder = mock.Mock(
            side_effect=[
                {"sessions": [{"id": "session-a"}]},
                {"sessions": [{"id": "session-b"}]},
            ]
        )
        fallback_builder = mock.Mock(return_value={"sessions": [{"id": "fallback"}]})

        with mock.patch.object(
            snapshot.time,
            "monotonic",
            side_effect=[100.0, 100.0, 100.0, 100.01, 100.01, 102.0, 102.0, 102.0, 102.02, 102.02],
        ):
            first = self._build(light_builder=light_builder, fallback_builder=fallback_builder)
            second = self._build(
                light_builder=light_builder,
                fallback_builder=fallback_builder,
                config=snapshot.SessionDirectorySnapshotConfig(enabled=True, ttl_ms=1000, prewarm_enabled=False),
            )

        self.assertEqual(light_builder.call_count, 2)
        self.assertEqual(fallback_builder.call_count, 0)
        self.assertEqual(first["sessions"][0]["id"], "session-a")
        self.assertEqual(second["sessions"][0]["id"], "session-b")
        metadata = second.get("directory_snapshot") or {}
        self.assertFalse(metadata.get("hit"))
        self.assertEqual(metadata.get("fallback_reason"), "expired")

    def test_expired_snapshot_serves_stale_and_starts_prewarm(self) -> None:
        light_builder = mock.Mock(return_value={"sessions": [{"id": "session-a"}]})
        fallback_builder = mock.Mock(return_value={"sessions": [{"id": "fallback"}]})

        with mock.patch.object(
            snapshot.time,
            "monotonic",
            side_effect=[100.0, 100.0, 100.0, 100.01, 100.01],
        ):
            self._build(light_builder=light_builder, fallback_builder=fallback_builder)
        with mock.patch.object(snapshot, "_start_snapshot_refresh", return_value="started") as refresh_mock:
            with mock.patch.object(snapshot.time, "monotonic", return_value=102.0):
                payload = self._build(light_builder=light_builder, fallback_builder=fallback_builder)

        self.assertEqual(light_builder.call_count, 1)
        self.assertEqual(fallback_builder.call_count, 0)
        self.assertEqual(refresh_mock.call_count, 1)
        self.assertEqual(payload["sessions"][0]["id"], "session-a")
        metadata = payload.get("directory_snapshot") or {}
        self.assertTrue(metadata.get("hit"))
        self.assertEqual(metadata.get("build_source"), "stale_snapshot")
        self.assertEqual(metadata.get("fallback_reason"), "expired")

    def test_query_key_not_eligible_falls_back_to_full_builder(self) -> None:
        light_builder = mock.Mock(return_value={"sessions": [{"id": "light"}]})
        fallback_builder = mock.Mock(return_value={"sessions": [{"id": "fallback"}]})

        with mock.patch.object(snapshot.time, "monotonic", side_effect=[100.0, 100.03]):
            payload = self._build(
                light_builder=light_builder,
                fallback_builder=fallback_builder,
                include_deleted=True,
            )

        self.assertEqual(light_builder.call_count, 0)
        self.assertEqual(fallback_builder.call_count, 1)
        self.assertEqual(payload["sessions"][0]["id"], "fallback")
        metadata = payload.get("directory_snapshot") or {}
        self.assertEqual(metadata.get("build_source"), "fallback")
        self.assertEqual(metadata.get("fallback_reason"), "include_deleted")

    def test_ttl_zero_falls_back_to_full_builder(self) -> None:
        light_builder = mock.Mock(return_value={"sessions": [{"id": "light"}]})
        fallback_builder = mock.Mock(return_value={"sessions": [{"id": "fallback"}]})
        config = snapshot.SessionDirectorySnapshotConfig(enabled=True, ttl_ms=0, prewarm_enabled=True)

        with mock.patch.object(snapshot.time, "monotonic", side_effect=[100.0, 100.01]):
            payload = self._build(light_builder=light_builder, fallback_builder=fallback_builder, config=config)

        self.assertEqual(light_builder.call_count, 0)
        self.assertEqual(fallback_builder.call_count, 1)
        self.assertEqual(payload["sessions"][0]["id"], "fallback")
        metadata = payload.get("directory_snapshot") or {}
        self.assertFalse(metadata.get("enabled"))
        self.assertEqual(metadata.get("fallback_reason"), "ttl_zero")

    def test_light_builder_error_falls_back_to_full_builder(self) -> None:
        light_builder = mock.Mock(side_effect=RuntimeError("boom"))
        fallback_builder = mock.Mock(return_value={"sessions": [{"id": "fallback"}]})

        with mock.patch.object(snapshot.time, "monotonic", side_effect=[100.0, 100.0, 100.0, 100.04]):
            payload = self._build(light_builder=light_builder, fallback_builder=fallback_builder)

        self.assertEqual(light_builder.call_count, 1)
        self.assertEqual(fallback_builder.call_count, 1)
        metadata = payload.get("directory_snapshot") or {}
        self.assertEqual(metadata.get("build_source"), "fallback")
        self.assertEqual(metadata.get("fallback_reason"), "build_error")

    def test_invalidate_clears_project_snapshot(self) -> None:
        light_builder = mock.Mock(
            side_effect=[
                {"sessions": [{"id": "session-a"}]},
                {"sessions": [{"id": "session-b"}]},
            ]
        )
        fallback_builder = mock.Mock(return_value={"sessions": [{"id": "fallback"}]})

        with mock.patch.object(snapshot.time, "monotonic", side_effect=[100.0, 100.0, 100.0, 100.01, 100.01]):
            self._build(light_builder=light_builder, fallback_builder=fallback_builder)
        snapshot.invalidate_session_directory_snapshot("task_dashboard")
        with mock.patch.object(snapshot.time, "monotonic", side_effect=[100.2, 100.2, 100.2, 100.21, 100.21]):
            payload = self._build(
                light_builder=light_builder,
                fallback_builder=fallback_builder,
                config=snapshot.SessionDirectorySnapshotConfig(enabled=True, ttl_ms=1000, prewarm_enabled=False),
            )

        self.assertEqual(light_builder.call_count, 2)
        self.assertEqual(payload["sessions"][0]["id"], "session-b")

    def test_light_payload_passes_memo_store_to_list_metrics(self) -> None:
        class _SessionStore:
            def list_sessions(self, *_args, **_kwargs):
                return [{"id": "session-a", "project_id": "task_dashboard"}]

        memo_store = object()
        metrics_mock = mock.Mock(side_effect=lambda rows, **_kwargs: rows)
        payload = snapshot.build_session_directory_light_payload(
            session_store=_SessionStore(),
            store=object(),
            project_id="task_dashboard",
            environment_name="stable",
            worktree_root="/tmp/task-dashboard",
            apply_effective_primary_flags=lambda _store, _project_id, rows: rows,
            decorate_sessions_display_fields=lambda rows: rows,
            apply_session_context_rows=lambda rows, **_kwargs: rows,
            apply_session_work_context=lambda row, **_kwargs: row,
            heartbeat_runtime=None,
            load_session_heartbeat_config=lambda _row: {},
            heartbeat_summary_payload=lambda _row: {},
            apply_session_heartbeat_summary_rows=lambda rows, **_kwargs: rows,
            apply_session_conversation_list_metrics_rows=metrics_mock,
            perf_payload_builder=lambda _project_id: {},
            conversation_memo_store=memo_store,
        )

        self.assertEqual(payload["sessions"][0]["id"], "session-a")
        self.assertIs(metrics_mock.call_args.kwargs.get("conversation_memo_store"), memo_store)

    def test_light_payload_includes_agent_display_fields_and_identity_audit(self) -> None:
        class _SessionStore:
            def list_sessions(self, *_args, **_kwargs):
                return [
                    {
                        "id": "session-a",
                        "project_id": "task_dashboard",
                        "channel_name": "子级02-CCB运行时（server-并发-安全-启动）",
                        "cli_type": "codex",
                        "alias": "服务开发-任务维度",
                    }
                ]

        payload = snapshot.build_session_directory_light_payload(
            session_store=_SessionStore(),
            store=object(),
            project_id="task_dashboard",
            environment_name="stable",
            worktree_root="/tmp/task-dashboard",
            apply_effective_primary_flags=lambda _store, _project_id, rows: rows,
            decorate_sessions_display_fields=lambda rows: rows,
            apply_session_context_rows=lambda rows, **_kwargs: rows,
            apply_session_work_context=lambda row, **_kwargs: row,
            heartbeat_runtime=None,
            load_session_heartbeat_config=lambda _row: {},
            heartbeat_summary_payload=lambda _row: {},
            apply_session_heartbeat_summary_rows=lambda rows, **_kwargs: rows,
            apply_session_conversation_list_metrics_rows=lambda rows, **_kwargs: rows,
            perf_payload_builder=lambda _project_id: {},
            conversation_memo_store=None,
        )

        session = (payload.get("sessions") or [{}])[0]
        self.assertEqual(session.get("agent_display_name"), "服务开发-任务维度")
        self.assertEqual(session.get("agent_display_name_source"), "alias")
        self.assertEqual(session.get("agent_name_state"), "resolved")
        self.assertEqual(session.get("agent_display_issue"), "none")
        audit = payload.get("agent_identity_audit") or {}
        self.assertEqual(audit.get("manual_backfill_required_count"), 0)


if __name__ == "__main__":
    unittest.main()
