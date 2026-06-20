import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

import server
from task_dashboard.runtime import heartbeat_registry
from task_dashboard.runtime import session_routes


class SessionRoutesCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        session_routes._SESSIONS_PAYLOAD_CACHE.clear()
        session_routes._SESSIONS_PAYLOAD_CACHE_INFLIGHT.clear()
        session_routes._SESSIONS_PAYLOAD_CACHE_INVALIDATED_AT.clear()

    def test_list_sessions_response_reuses_cached_payload(self) -> None:
        payload = {"sessions": [{"id": "session-a", "channel_name": "主体-总控（合并与验收）"}]}
        with mock.patch.object(session_routes, "build_sessions_list_payload", return_value=payload) as build_mock:
            code1, out1 = session_routes.list_sessions_response(
                query_string="project_id=task_dashboard",
                session_store=object(),
                store=object(),
                environment_name="stable",
                worktree_root="/tmp/task-dashboard",
                apply_effective_primary_flags=lambda *_args, **_kwargs: [],
                decorate_sessions_display_fields=lambda rows: rows,
                apply_session_context_rows=lambda rows, **_kwargs: rows,
                apply_session_work_context=lambda row, **_kwargs: row,
                attach_runtime_state_to_sessions=lambda _store, rows, **_kwargs: rows,
                heartbeat_runtime=None,
                load_session_heartbeat_config=lambda _row: {},
                heartbeat_summary_payload=lambda _row: {},
            )
            out1["sessions"][0]["id"] = "mutated"
            code2, out2 = session_routes.list_sessions_response(
                query_string="project_id=task_dashboard",
                session_store=object(),
                store=object(),
                environment_name="stable",
                worktree_root="/tmp/task-dashboard",
                apply_effective_primary_flags=lambda *_args, **_kwargs: [],
                decorate_sessions_display_fields=lambda rows: rows,
                apply_session_context_rows=lambda rows, **_kwargs: rows,
                apply_session_work_context=lambda row, **_kwargs: row,
                attach_runtime_state_to_sessions=lambda _store, rows, **_kwargs: rows,
                heartbeat_runtime=None,
                load_session_heartbeat_config=lambda _row: {},
                heartbeat_summary_payload=lambda _row: {},
            )

        self.assertEqual(code1, 200)
        self.assertEqual(code2, 200)
        self.assertEqual(build_mock.call_count, 1)
        self.assertEqual(out2["sessions"][0]["id"], "session-a")

    def test_list_sessions_response_respects_zero_ttl(self) -> None:
        with mock.patch.dict(os.environ, {"CCB_SESSIONS_LIST_CACHE_TTL_MS": "0"}, clear=False):
            with mock.patch.object(
                session_routes,
                "build_sessions_list_payload",
                side_effect=[
                    {"sessions": [{"id": "session-a"}]},
                    {"sessions": [{"id": "session-b"}]},
                ],
            ) as build_mock:
                _code1, out1 = session_routes.list_sessions_response(
                    query_string="project_id=task_dashboard",
                    session_store=object(),
                    store=object(),
                    environment_name="stable",
                    worktree_root="/tmp/task-dashboard",
                    apply_effective_primary_flags=lambda *_args, **_kwargs: [],
                    decorate_sessions_display_fields=lambda rows: rows,
                    apply_session_context_rows=lambda rows, **_kwargs: rows,
                    apply_session_work_context=lambda row, **_kwargs: row,
                    attach_runtime_state_to_sessions=lambda _store, rows, **_kwargs: rows,
                    heartbeat_runtime=None,
                    load_session_heartbeat_config=lambda _row: {},
                    heartbeat_summary_payload=lambda _row: {},
                )
                _code2, out2 = session_routes.list_sessions_response(
                    query_string="project_id=task_dashboard",
                    session_store=object(),
                    store=object(),
                    environment_name="stable",
                    worktree_root="/tmp/task-dashboard",
                    apply_effective_primary_flags=lambda *_args, **_kwargs: [],
                    decorate_sessions_display_fields=lambda rows: rows,
                    apply_session_context_rows=lambda rows, **_kwargs: rows,
                    apply_session_work_context=lambda row, **_kwargs: row,
                    attach_runtime_state_to_sessions=lambda _store, rows, **_kwargs: rows,
                    heartbeat_runtime=None,
                    load_session_heartbeat_config=lambda _row: {},
                    heartbeat_summary_payload=lambda _row: {},
                )

        self.assertEqual(build_mock.call_count, 2)
        self.assertEqual(out1["sessions"][0]["id"], "session-a")
        self.assertEqual(out2["sessions"][0]["id"], "session-b")

    def test_list_sessions_response_summary_mode_uses_light_rows(self) -> None:
        class _SessionStore:
            def list_sessions(self, *_args, **_kwargs):
                return [
                    {
                        "id": "session-a",
                        "project_id": "task_dashboard",
                        "channel_name": "子级02-CCB运行时（server-并发-安全-启动）",
                        "alias": "后端-任务业务",
                        "model": "claude-fable-5",
                        "project_execution_context": {"target": {"project_id": "task_dashboard"}},
                        "task_tracking": {"current_task_ref": {"task_id": "heavy-task"}},
                    }
                ]

        context_calls = []
        runtime_kwargs = {}
        with mock.patch.object(
            session_routes,
            "build_sessions_list_payload",
            side_effect=AssertionError("summary mode should not use the full sessions builder"),
        ):
            code, out = session_routes.list_sessions_response(
                query_string="project_id=task_dashboard&payloadMode=summary",
                session_store=_SessionStore(),
                store=object(),
                environment_name="stable",
                worktree_root="/tmp/task-dashboard",
                apply_effective_primary_flags=lambda _store, _pid, rows: rows,
                decorate_sessions_display_fields=lambda rows: rows,
                apply_session_context_rows=lambda rows, **_kwargs: context_calls.append(_kwargs) or rows,
                apply_session_work_context=lambda row, **_kwargs: row,
                attach_runtime_state_to_sessions=lambda _store, rows, **_kwargs: runtime_kwargs.update(_kwargs) or [
                    {
                        **row,
                        "runtime_state": {"display_state": "idle"},
                        "session_display_state": "idle",
                    }
                    for row in rows
                ],
                heartbeat_runtime=None,
                load_session_heartbeat_config=lambda _row: {},
                heartbeat_summary_payload=lambda _row: {},
            )

        self.assertEqual(code, 200)
        self.assertEqual(out.get("payloadMode"), "summary")
        self.assertEqual((out.get("sessions_read_model") or {}).get("payload_mode"), "summary")
        row = (out.get("sessions") or [])[0]
        self.assertEqual(row.get("id"), "session-a")
        self.assertEqual(row.get("model"), "claude-fable-5")
        self.assertEqual(row.get("runtime_state"), {"display_state": "idle"})
        self.assertEqual(row.get("agent_display_name"), "后端-任务业务")
        self.assertNotIn("task_tracking", row)
        self.assertNotIn("project_execution_context", row)
        self.assertEqual(context_calls, [])
        self.assertTrue(runtime_kwargs.get("runtime_index_allow_stale"))
        self.assertFalse(runtime_kwargs.get("runtime_index_wait_for_inflight"))
        self.assertFalse(runtime_kwargs.get("probe_external_when_idle"))
        read_model = out.get("sessions_read_model") or {}
        self.assertTrue(read_model.get("isPartial"))
        self.assertIn("model", read_model.get("summary_fields") or [])
        self.assertIn("project_execution_context", read_model.get("deferred_fields") or [])
        self.assertEqual(out.get("statusFreshness"), "partial")

    def test_list_sessions_response_light_mode_skips_context_and_runtime(self) -> None:
        class _SessionStore:
            def list_sessions(self, *_args, **_kwargs):
                return [
                    {
                        "id": "session-a",
                        "project_id": "task_dashboard",
                        "channel_name": "子级02-CCB运行时（server-并发-安全-启动）",
                        "alias": "后端-light",
                        "model": "claude-fable-5",
                        "project_execution_context": {"target": {"project_id": "task_dashboard"}},
                    }
                ]

        code, out = session_routes.list_sessions_response(
            query_string="project_id=task_dashboard&payloadMode=light",
            session_store=_SessionStore(),
            store=object(),
            environment_name="stable",
            worktree_root="/tmp/task-dashboard",
            apply_effective_primary_flags=lambda _store, _pid, rows: rows,
            decorate_sessions_display_fields=lambda rows: rows,
            apply_session_context_rows=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("light mode must not build project_execution_context")
            ),
            apply_session_work_context=lambda row, **_kwargs: row,
            attach_runtime_state_to_sessions=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("light mode must not synchronously attach runtime state")
            ),
            heartbeat_runtime=None,
            load_session_heartbeat_config=lambda _row: {},
            heartbeat_summary_payload=lambda _row: {},
        )

        self.assertEqual(code, 200)
        self.assertEqual(out.get("payloadMode"), "light")
        self.assertTrue(out.get("isPartial"))
        self.assertEqual(out.get("statusFreshness"), "degraded")
        row = (out.get("sessions") or [])[0]
        self.assertEqual(row.get("model"), "claude-fable-5")
        self.assertEqual(row.get("agent_display_name"), "后端-light")
        self.assertNotIn("project_execution_context", row)
        runtime_state = row.get("runtime_state") or {}
        self.assertTrue(runtime_state.get("degraded"))
        self.assertEqual(runtime_state.get("degraded_reason"), "runtime_not_attached")
        hints = out.get("loadingHints") or {}
        self.assertIn("project_execution_context", hints.get("deferredFields") or [])
        self.assertIn("model", (out.get("sessions_read_model") or {}).get("summary_fields") or [])

    def test_list_sessions_allow_stale_returns_expired_cache_without_rebuild(self) -> None:
        cache_key = session_routes._sessions_payload_cache_key(
            scope="sessions",
            project_id="task_dashboard",
            channel_name="",
            include_deleted=False,
            environment_name="stable",
            worktree_root="/tmp/task-dashboard",
            payload_mode="summary",
        )
        old_mono = time.monotonic() - 3600
        inflight_event = threading.Event()
        session_routes._SESSIONS_PAYLOAD_CACHE[cache_key] = {
            "checked_at_mono": old_mono,
            "build_started_at_mono": old_mono,
            "project_id": "task_dashboard",
            "payload": {"sessions": [{"id": "cached-session"}], "count": 1},
        }
        session_routes._SESSIONS_PAYLOAD_CACHE_INFLIGHT[cache_key] = {
            "event": inflight_event,
            "started_at_mono": time.monotonic(),
            "project_id": "task_dashboard",
        }

        with mock.patch.object(
            session_routes,
            "build_sessions_summary_payload",
            side_effect=AssertionError("allow_stale should not rebuild while stale cache exists"),
        ):
            code, out = session_routes.list_sessions_response(
                query_string="project_id=task_dashboard&payloadMode=summary&allow_stale=1",
                session_store=object(),
                store=object(),
                environment_name="stable",
                worktree_root="/tmp/task-dashboard",
                apply_effective_primary_flags=lambda *_args, **_kwargs: [],
                decorate_sessions_display_fields=lambda rows: rows,
                apply_session_context_rows=lambda rows, **_kwargs: rows,
                apply_session_work_context=lambda row, **_kwargs: row,
                attach_runtime_state_to_sessions=lambda _store, rows, **_kwargs: rows,
                heartbeat_runtime=None,
                load_session_heartbeat_config=lambda _row: {},
                heartbeat_summary_payload=lambda _row: {},
        )

        self.assertEqual(code, 200)
        row = (out.get("sessions") or [])[0]
        self.assertEqual(row.get("id"), "cached-session")
        self.assertTrue(bool((row.get("runtime_state") or {}).get("degraded")))
        self.assertEqual((row.get("communication_status_summary") or {}).get("degraded_reason"), "stale_cache_inflight")
        read_model = out.get("sessions_read_model") or {}
        self.assertTrue(read_model.get("allow_stale"))
        self.assertTrue(read_model.get("stale"))
        self.assertTrue(read_model.get("from_cache"))
        self.assertEqual(read_model.get("degraded_reason"), "stale_cache_inflight")
        self.assertGreaterEqual(int(read_model.get("cache_age_ms") or 0), 1)

    def test_list_sessions_allow_stale_cache_hit_skips_runtime_state(self) -> None:
        cache_key = session_routes._sessions_payload_cache_key(
            scope="sessions",
            project_id="task_dashboard",
            channel_name="",
            include_deleted=False,
            environment_name="stable",
            worktree_root="/tmp/task-dashboard",
            payload_mode="light",
        )
        now_mono = time.monotonic()
        session_routes._SESSIONS_PAYLOAD_CACHE[cache_key] = {
            "checked_at_mono": now_mono,
            "build_started_at_mono": now_mono,
            "project_id": "task_dashboard",
            "payload": {"sessions": [{"id": "cached-session", "alias": "缓存会话"}], "count": 1},
        }
        with mock.patch.object(
            session_routes,
            "build_sessions_summary_payload",
            side_effect=AssertionError("allow_stale should return cache without rebuilding"),
        ):
            code, out = session_routes.list_sessions_response(
                query_string="project_id=task_dashboard&payloadMode=light&allow_stale=1",
                session_store=object(),
                store=object(),
                environment_name="stable",
                worktree_root="/tmp/task-dashboard",
                apply_effective_primary_flags=lambda *_args, **_kwargs: [],
                decorate_sessions_display_fields=lambda rows: rows,
                apply_session_context_rows=lambda rows, **_kwargs: rows,
                apply_session_work_context=lambda row, **_kwargs: row,
                attach_runtime_state_to_sessions=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                    AssertionError("allow_stale cache hit must not touch runtime state")
                ),
                heartbeat_runtime=None,
                load_session_heartbeat_config=lambda _row: {},
                heartbeat_summary_payload=lambda _row: {},
            )

        self.assertEqual(code, 200)
        row = (out.get("sessions") or [])[0]
        self.assertEqual(row.get("id"), "cached-session")
        runtime_state = row.get("runtime_state") or {}
        self.assertEqual(runtime_state.get("display_state"), "idle")
        self.assertTrue(runtime_state.get("degraded"))
        self.assertEqual(runtime_state.get("degraded_reason"), "cache_hit_no_runtime")
        self.assertNotIn("session_display_state", row)
        self.assertEqual(row.get("latest_run_summary"), {})
        self.assertEqual(row.get("latest_effective_run_summary"), {})
        communication = row.get("communication_status_summary") or {}
        self.assertEqual(communication.get("delivery_state"), "unknown")
        self.assertTrue(communication.get("degraded"))
        self.assertEqual(communication.get("degraded_reason"), "cache_hit_no_runtime")
        projection = communication.get("projection_summary") or {}
        self.assertEqual(projection.get("reason"), "degraded_unknown")
        self.assertTrue(projection.get("degraded"))
        read_model = out.get("sessions_read_model") or {}
        self.assertTrue(read_model.get("allow_stale"))
        self.assertTrue(read_model.get("stale"))
        self.assertTrue(read_model.get("from_cache"))
        self.assertTrue(read_model.get("degraded"))
        self.assertEqual(read_model.get("degraded_reason"), "cache_hit_no_runtime")

    def test_list_sessions_allow_stale_no_cache_skips_runtime_state_and_caches_directory(self) -> None:
        class _SessionStore:
            def list_sessions(self, *_args, **_kwargs):
                return [
                    {
                        "id": "session-a",
                        "project_id": "task_dashboard",
                        "channel_name": "子级02-CCB运行时（server-并发-安全-启动）",
                        "alias": "后端-会话读链",
                    }
                ]

        cache_key = session_routes._sessions_payload_cache_key(
            scope="sessions",
            project_id="task_dashboard",
            channel_name="",
            include_deleted=False,
            environment_name="stable",
            worktree_root="/tmp/task-dashboard",
            payload_mode="light",
        )
        session_routes._SESSIONS_PAYLOAD_CACHE_INFLIGHT[cache_key] = {
            "event": threading.Event(),
            "started_at_mono": time.monotonic(),
            "project_id": "task_dashboard",
        }
        code, out = session_routes.list_sessions_response(
            query_string="project_id=task_dashboard&payloadMode=light&allow_stale=1",
            session_store=_SessionStore(),
            store=object(),
            environment_name="stable",
            worktree_root="/tmp/task-dashboard",
            apply_effective_primary_flags=lambda _store, _pid, rows: rows,
            decorate_sessions_display_fields=lambda rows: rows,
            apply_session_context_rows=lambda rows, **_kwargs: rows,
            apply_session_work_context=lambda row, **_kwargs: row,
            attach_runtime_state_to_sessions=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("allow_stale no-cache path must not touch runtime state")
            ),
            heartbeat_runtime=None,
            load_session_heartbeat_config=lambda _row: {},
            heartbeat_summary_payload=lambda _row: {},
        )

        self.assertEqual(code, 200)
        self.assertEqual(out.get("payloadMode"), "light")
        row = (out.get("sessions") or [])[0]
        self.assertEqual(row.get("id"), "session-a")
        self.assertEqual(row.get("agent_display_name"), "后端-会话读链")
        runtime_state = row.get("runtime_state") or {}
        self.assertEqual(runtime_state.get("display_state"), "idle")
        self.assertTrue(runtime_state.get("degraded"))
        self.assertNotIn("session_display_state", row)
        self.assertEqual(row.get("latest_run_summary"), {})
        self.assertEqual(row.get("latest_effective_run_summary"), {})
        communication = row.get("communication_status_summary") or {}
        self.assertEqual(communication.get("delivery_state"), "unknown")
        self.assertTrue(communication.get("degraded"))
        projection = communication.get("projection_summary") or {}
        self.assertEqual(projection.get("reason"), "degraded_unknown")
        self.assertTrue(projection.get("degraded"))
        read_model = out.get("sessions_read_model") or {}
        self.assertTrue(read_model.get("allow_stale"))
        self.assertTrue(read_model.get("stale"))
        self.assertFalse(read_model.get("from_cache"))
        self.assertTrue(read_model.get("degraded"))
        self.assertEqual(read_model.get("degraded_reason"), "inflight_no_cache")
        self.assertIn(cache_key, session_routes._SESSIONS_PAYLOAD_CACHE)

    def test_list_sessions_allow_stale_without_payload_mode_defaults_to_summary(self) -> None:
        class _SessionStore:
            def list_sessions(self, *_args, **_kwargs):
                return [
                    {
                        "id": "session-a",
                        "project_id": "task_dashboard",
                        "channel_name": "子级06-数据治理与契约（规格-校验-修复）",
                        "alias": "性能治理",
                    }
                ]

        with mock.patch.object(
            session_routes,
            "build_sessions_list_payload",
            side_effect=AssertionError("allow_stale without payloadMode should not use full builder"),
        ):
            code, out = session_routes.list_sessions_response(
                query_string="project_id=task_dashboard&allow_stale=1",
                session_store=_SessionStore(),
                store=object(),
                environment_name="stable",
                worktree_root="/tmp/task-dashboard",
                apply_effective_primary_flags=lambda _store, _pid, rows: rows,
                decorate_sessions_display_fields=lambda rows: rows,
                apply_session_context_rows=lambda rows, **_kwargs: rows,
                apply_session_work_context=lambda row, **_kwargs: row,
                attach_runtime_state_to_sessions=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                    AssertionError("allow_stale default summary path must not touch runtime state")
                ),
                heartbeat_runtime=None,
                load_session_heartbeat_config=lambda _row: {},
                heartbeat_summary_payload=lambda _row: {},
            )

        self.assertEqual(code, 200)
        self.assertEqual(out.get("payloadMode"), "summary")
        self.assertEqual((out.get("sessions") or [])[0].get("agent_display_name"), "性能治理")
        read_model = out.get("sessions_read_model") or {}
        self.assertTrue(read_model.get("allow_stale"))
        self.assertTrue(read_model.get("stale"))
        self.assertTrue(read_model.get("degraded"))

    def test_list_channel_sessions_response_reuses_cached_payload(self) -> None:
        payload = {
            "project_id": "task_dashboard",
            "channel_name": "子级02-CCB运行时（server-并发-安全-启动）",
            "primary_session_id": "session-a",
            "sessions": [{"id": "session-a"}],
            "count": 1,
        }
        with mock.patch.object(session_routes, "build_channel_sessions_payload", return_value=payload) as build_mock:
            code1, out1 = session_routes.list_channel_sessions_response(
                query_string="project_id=task_dashboard&channel_name=子级02-CCB运行时（server-并发-安全-启动）",
                session_store=object(),
                store=object(),
                environment_name="stable",
                worktree_root="/tmp/task-dashboard",
                apply_effective_primary_flags=lambda *_args, **_kwargs: [],
                decorate_sessions_display_fields=lambda rows: rows,
                apply_session_context_rows=lambda rows, **_kwargs: rows,
                apply_session_work_context=lambda row, **_kwargs: row,
                resolve_channel_primary_session_id=lambda *_args, **_kwargs: "session-a",
                heartbeat_runtime=None,
                load_session_heartbeat_config=lambda _row: {},
                heartbeat_summary_payload=lambda _row: {},
            )
            out1["sessions"][0]["id"] = "mutated"
            code2, out2 = session_routes.list_channel_sessions_response(
                query_string="project_id=task_dashboard&channel_name=子级02-CCB运行时（server-并发-安全-启动）",
                session_store=object(),
                store=object(),
                environment_name="stable",
                worktree_root="/tmp/task-dashboard",
                apply_effective_primary_flags=lambda *_args, **_kwargs: [],
                decorate_sessions_display_fields=lambda rows: rows,
                apply_session_context_rows=lambda rows, **_kwargs: rows,
                apply_session_work_context=lambda row, **_kwargs: row,
                resolve_channel_primary_session_id=lambda *_args, **_kwargs: "session-a",
                heartbeat_runtime=None,
                load_session_heartbeat_config=lambda _row: {},
                heartbeat_summary_payload=lambda _row: {},
            )

        self.assertEqual(code1, 200)
        self.assertEqual(code2, 200)
        self.assertEqual(build_mock.call_count, 1)
        self.assertEqual(out2["sessions"][0]["id"], "session-a")

    def test_get_session_detail_response_reuses_cached_payload(self) -> None:
        payload = {"id": "session-a", "task_tracking": {"version": "v1.1"}}

        class _SessionStore:
            def get_session(self, session_id: str):
                if session_id == "session-a":
                    return {"id": session_id, "project_id": "task_dashboard"}
                return None

        with mock.patch.object(session_routes, "build_session_detail_response", return_value=payload) as build_mock:
            code1, out1 = session_routes.get_session_detail_response(
                session_id="session-a",
                session_store=_SessionStore(),
                store=object(),
                environment_name="stable",
                worktree_root="/tmp/task-dashboard",
                heartbeat_runtime=None,
                infer_project_id_for_session=lambda *_args, **_kwargs: "task_dashboard",
                apply_effective_primary_flags=lambda *_args, **_kwargs: [],
                decorate_session_display_fields=lambda row: row,
                build_session_detail_payload=lambda *args, **kwargs: {},
                apply_session_work_context=lambda row, **_kwargs: row,
                build_project_session_runtime_index=lambda *_args, **_kwargs: {},
                build_session_runtime_state_for_row=lambda *_args, **_kwargs: {},
                load_session_heartbeat_config=lambda _row: {},
                heartbeat_summary_payload=lambda _row: {},
            )
            out1["task_tracking"]["version"] = "mutated"
            code2, out2 = session_routes.get_session_detail_response(
                session_id="session-a",
                session_store=_SessionStore(),
                store=object(),
                environment_name="stable",
                worktree_root="/tmp/task-dashboard",
                heartbeat_runtime=None,
                infer_project_id_for_session=lambda *_args, **_kwargs: "task_dashboard",
                apply_effective_primary_flags=lambda *_args, **_kwargs: [],
                decorate_session_display_fields=lambda row: row,
                build_session_detail_payload=lambda *args, **kwargs: {},
                apply_session_work_context=lambda row, **_kwargs: row,
                build_project_session_runtime_index=lambda *_args, **_kwargs: {},
                build_session_runtime_state_for_row=lambda *_args, **_kwargs: {},
                load_session_heartbeat_config=lambda _row: {},
                heartbeat_summary_payload=lambda _row: {},
            )

        self.assertEqual(code1, 200)
        self.assertEqual(code2, 200)
        self.assertEqual(build_mock.call_count, 1)
        self.assertEqual(out2["task_tracking"]["version"], "v1.1")

    def test_build_sessions_list_payload_restores_agent_display_fields_and_identity_audit(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = tempfile.mkdtemp(dir=td)
            run_store = server.RunStore(Path(base) / ".runtime" / "stable" / ".runs")
            session_store = server.SessionStore(base_dir=run_store.runs_dir.parent)

            resolved = session_store.create_session(
                "task_dashboard",
                "辅助06-项目运维（运行巡检-异常告警-会话修复）",
                cli_type="codex",
                alias="项目运维-异常修复",
                session_id="019d75f8-a187-75d2-a118-c1a187ae2a76",
            )
            unresolved = session_store.create_session(
                "task_dashboard",
                "子级08-测试与验收（功能-回归-发布）",
                cli_type="opencode",
                session_id="ses_2f56e1533ffeoQi7mS0iK1kMkP",
            )
            session_store.update_session(
                unresolved["id"],
                display_name="子级08-测试与验收（功能-回归-发布）",
                display_name_source="channel_name",
            )

            payload = session_routes.build_sessions_list_payload(
                session_store=session_store,
                store=run_store,
                project_id="task_dashboard",
                environment_name="stable",
                worktree_root=base,
                apply_effective_primary_flags=lambda _store, _pid, rows: rows,
                decorate_sessions_display_fields=heartbeat_registry._decorate_sessions_display_fields,
                apply_session_context_rows=lambda rows, **_kwargs: rows,
                apply_session_work_context=lambda row, **_kwargs: row,
                attach_runtime_state_to_sessions=lambda _store, rows, **_kwargs: rows,
                heartbeat_runtime=None,
                load_session_heartbeat_config=lambda _row: {},
                heartbeat_summary_payload=lambda _row: {},
            )

            rows = {row["id"]: row for row in payload["sessions"]}
            self.assertEqual(rows[resolved["id"]]["agent_display_name"], "项目运维-异常修复")
            self.assertEqual(rows[resolved["id"]]["agent_name_state"], "resolved")
            self.assertEqual(rows[unresolved["id"]]["agent_name_state"], "identity_unresolved")
            self.assertEqual(rows[unresolved["id"]]["agent_display_issue"], "missing_identity_source")
            audit = payload.get("agent_identity_audit") or {}
            self.assertEqual(int(audit.get("manual_backfill_required_count") or 0), 1)

    def test_get_session_detail_response_restores_agent_display_fields(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = tempfile.mkdtemp(dir=td)
            run_store = server.RunStore(Path(base) / ".runtime" / "stable" / ".runs")
            session_store = server.SessionStore(base_dir=run_store.runs_dir.parent)
            created = session_store.create_session(
                "task_dashboard",
                "辅助06-项目运维（运行巡检-异常告警-会话修复）",
                cli_type="codex",
                alias="项目运维-异常修复",
                session_id="019d75f8-a187-75d2-a118-c1a187ae2a76",
            )

            code, payload = session_routes.get_session_detail_response(
                session_id=created["id"],
                session_store=session_store,
                store=run_store,
                environment_name="stable",
                worktree_root=base,
                heartbeat_runtime=None,
                infer_project_id_for_session=lambda *_args, **_kwargs: "task_dashboard",
                apply_effective_primary_flags=lambda _store, _pid, rows: rows,
                decorate_session_display_fields=heartbeat_registry._decorate_session_display_fields,
                build_session_detail_payload=lambda session, **_kwargs: dict(session),
                apply_session_work_context=lambda row, **_kwargs: row,
                build_project_session_runtime_index=lambda *_args, **_kwargs: {},
                build_session_runtime_state_for_row=lambda *_args, **_kwargs: {},
                load_session_heartbeat_config=lambda _row: {},
                heartbeat_summary_payload=lambda _row: {},
            )

            self.assertEqual(code, 200)
            self.assertEqual(payload["agent_display_name"], "项目运维-异常修复")
            self.assertEqual(payload["agent_display_name_source"], "alias")
            self.assertEqual(payload["agent_name_state"], "resolved")
            self.assertEqual(payload["agent_display_issue"], "none")


if __name__ == "__main__":
    unittest.main()
