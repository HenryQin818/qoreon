import os
import tempfile
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
