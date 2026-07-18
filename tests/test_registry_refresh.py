import tempfile
import unittest
from pathlib import Path
from unittest import mock

from task_dashboard.runtime.registry_refresh import (
    read_registry_refresh_status,
    schedule_registry_refresh,
    should_refresh_for_update,
)
from task_dashboard.runtime.request_parsing import parse_session_update_fields
from task_dashboard.runtime.session_admin import (
    create_session_response,
    delete_session_response,
    manage_channel_sessions_response,
    update_session_response,
)
from task_dashboard.session_store import SessionStore


class RegistryRefreshTests(unittest.TestCase):
    def test_should_refresh_only_for_contact_fields(self) -> None:
        before = {"alias": "旧 Agent", "last_used_at": "2026-01-01T00:00:00Z"}

        no_refresh, no_fields = should_refresh_for_update(before, {"last_used_at": "2026-01-02T00:00:00Z"})
        refresh, fields = should_refresh_for_update(before, {"alias": "新 Agent"})

        self.assertFalse(no_refresh)
        self.assertEqual(no_fields, [])
        self.assertTrue(refresh)
        self.assertEqual(fields, ["alias"])

    def test_schedule_registry_refresh_records_done_without_forking(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            calls = []

            def fake_runner(**kwargs):
                calls.append(kwargs)
                return {"ok": True, "source": "fake"}

            result = schedule_registry_refresh(
                project_id="task_dashboard",
                reason="session_create",
                session_id="sid-1",
                channel_name="子级02",
                changed_fields=["alias"],
                workspace_root=base,
                runtime_base_dir=base,
                synchronous=True,
                runner=fake_runner,
            )

            self.assertEqual(result["state"], "done")
            self.assertFalse(result["degraded"])
            self.assertEqual(len(calls), 1)
            status = read_registry_refresh_status("task_dashboard", runtime_base_dir=base)
            self.assertEqual(status["state"], "done")
            self.assertEqual(status["result"]["source"], "fake")

    def test_schedule_registry_refresh_records_degraded_on_generator_failure(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)

            def failing_runner(**_kwargs):
                raise RuntimeError("registry generator failed")

            result = schedule_registry_refresh(
                project_id="task_dashboard",
                reason="session_update_identity",
                workspace_root=base,
                runtime_base_dir=base,
                synchronous=True,
                runner=failing_runner,
            )

            self.assertEqual(result["state"], "degraded")
            self.assertTrue(result["degraded"])
            self.assertEqual(result["degraded_reason"], "registry_refresh_failed")
            self.assertTrue(result["repair_items"])

    def test_create_with_agent_name_only_syncs_alias_and_schedules_refresh(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            workdir = base / "work"
            workdir.mkdir()

            def fake_create_cli_session(**_kwargs):
                return {
                    "ok": True,
                    "sessionId": "019c0000-0000-7000-8000-00000000c001",
                    "sessionPath": "",
                    "workdir": str(workdir),
                }

            with mock.patch(
                "task_dashboard.runtime.session_admin.schedule_registry_refresh",
                return_value={"state": "scheduled", "scheduled": True, "degraded": False},
            ) as refresh:
                result = create_session_response(
                    payload={
                        "project_id": "task_dashboard",
                        "channel_name": "子级02",
                        "cli_type": "codex",
                        "agentName": "后端-通讯能力",
                    },
                    session_store=SessionStore(base),
                    environment_name="refactor",
                    worktree_root=str(base),
                    create_cli_session=fake_create_cli_session,
                    resolve_project_workdir=lambda _pid: workdir,
                    detect_git_branch=lambda _root: "main",
                    build_session_seed_prompt=lambda **_kwargs: "seed",
                    decorate_session_display_fields=lambda row: row,
                    apply_session_work_context=lambda row, **_kwargs: row,
                    load_project_execution_context=lambda *_args, **_kwargs: {},
                    project_exists=lambda _pid: True,
                    channel_exists=lambda _pid, _channel: True,
                )

            session = result["session"]
            self.assertEqual(session["alias"], "后端-通讯能力")
            self.assertEqual(session["agent_name"], "后端-通讯能力")
            self.assertEqual(result["registry_refresh"]["state"], "scheduled")
            self.assertEqual(refresh.call_args.kwargs["reason"], "session_create")

    def test_update_agent_name_syncs_alias_and_schedules_refresh(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            store = SessionStore(base)
            created = store.create_session(
                "task_dashboard",
                "子级02",
                session_id="019c0000-0000-7000-8000-00000000c002",
                alias="旧通讯能力",
            )
            body = {"agentName": "新通讯能力"}

            with mock.patch(
                "task_dashboard.runtime.session_admin.schedule_registry_refresh",
                return_value={"state": "scheduled", "scheduled": True, "degraded": False},
            ) as refresh:
                result = update_session_response(
                    session_store=store,
                    session_id=str(created["id"]),
                    update_fields=parse_session_update_fields(body),
                    body=body,
                    store=None,
                    environment_name="refactor",
                    worktree_root=str(base),
                    infer_project_id_for_session=lambda *_args: "task_dashboard",
                    apply_session_work_context=lambda row, **_kwargs: row,
                    session_context_write_requires_guard=lambda *_args, **_kwargs: False,
                    stable_write_ack_requested=lambda _body: False,
                    coerce_bool=lambda value, default=False: bool(value) if value is not None else default,
                    heartbeat_session_payload_for_write=lambda *_args, **_kwargs: {},
                    build_session_detail_response=lambda **_kwargs: store.get_session(str(created["id"])),
                    heartbeat_runtime=None,
                    apply_effective_primary_flags=lambda _store, _project_id, rows: rows,
                    decorate_session_display_fields=lambda row: row,
                    build_session_detail_payload=lambda row, **_kwargs: row,
                    build_project_session_runtime_index=lambda *_args: {},
                    build_session_runtime_state_for_row=lambda *_args: {},
                    load_session_heartbeat_config=lambda _session: {},
                    heartbeat_summary_payload=lambda _payload: {},
                )

            updated = store.get_session(str(created["id"])) or {}
            self.assertEqual(updated["alias"], "新通讯能力")
            self.assertEqual(updated["agent_name"], "新通讯能力")
            self.assertEqual(result["registry_refresh"]["state"], "scheduled")
            self.assertEqual(refresh.call_args.kwargs["changed_fields"], ["agent_name", "alias"])

    def test_update_non_contact_field_does_not_schedule_refresh(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            store = SessionStore(base)
            created = store.create_session(
                "task_dashboard",
                "子级02",
                session_id="019c0000-0000-7000-8000-00000000c003",
                alias="后端-通讯能力",
            )

            with mock.patch("task_dashboard.runtime.session_admin.schedule_registry_refresh") as refresh:
                result = update_session_response(
                    session_store=store,
                    session_id=str(created["id"]),
                    update_fields={"last_used_at": "2026-06-30T00:00:00Z"},
                    body={"last_used_at": "2026-06-30T00:00:00Z"},
                    store=None,
                    environment_name="refactor",
                    worktree_root=str(base),
                    infer_project_id_for_session=lambda *_args: "task_dashboard",
                    apply_session_work_context=lambda row, **_kwargs: row,
                    session_context_write_requires_guard=lambda *_args, **_kwargs: False,
                    stable_write_ack_requested=lambda _body: False,
                    coerce_bool=lambda value, default=False: bool(value) if value is not None else default,
                    heartbeat_session_payload_for_write=lambda *_args, **_kwargs: {},
                    build_session_detail_response=lambda **_kwargs: store.get_session(str(created["id"])),
                    heartbeat_runtime=None,
                    apply_effective_primary_flags=lambda _store, _project_id, rows: rows,
                    decorate_session_display_fields=lambda row: row,
                    build_session_detail_payload=lambda row, **_kwargs: row,
                    build_project_session_runtime_index=lambda *_args: {},
                    build_session_runtime_state_for_row=lambda *_args: {},
                    load_session_heartbeat_config=lambda _session: {},
                    heartbeat_summary_payload=lambda _payload: {},
                )

            self.assertNotIn("registry_refresh", result)
            refresh.assert_not_called()

    def test_manage_and_delete_schedule_refresh_without_rolling_back(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            store = SessionStore(base)
            first = store.create_session(
                "task_dashboard",
                "子级02",
                session_id="019c0000-0000-7000-8000-00000000c004",
                alias="第一会话",
                is_primary=True,
            )
            second = store.create_session(
                "task_dashboard",
                "子级02",
                session_id="019c0000-0000-7000-8000-00000000c005",
                alias="第二会话",
            )

            with mock.patch(
                "task_dashboard.runtime.session_admin.schedule_registry_refresh",
                return_value={"state": "scheduled", "scheduled": True, "degraded": False},
            ) as refresh:
                managed = manage_channel_sessions_response(
                    session_store=store,
                    project_id="task_dashboard",
                    channel_name="子级02",
                    primary_session_id=str(second["id"]),
                    updates=[],
                    decorate_sessions_display_fields=lambda rows: rows,
                    workspace_root=base,
                )
                deleted = delete_session_response(
                    session_store=store,
                    session_id=str(first["id"]),
                    workspace_root=base,
                )

            self.assertEqual(managed["registry_refresh"]["state"], "scheduled")
            self.assertEqual(deleted["registry_refresh"]["state"], "scheduled")
            self.assertEqual(refresh.call_count, 2)


if __name__ == "__main__":
    unittest.main()
