import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib import error as url_error
from urllib import request as url_request

import server

from task_dashboard.runtime.share_space import (
    build_share_announce_request,
    build_share_bootstrap_response,
    build_share_session_response,
    load_project_share_space_config,
    share_space_store_path,
    update_project_share_space_config_response,
)


class ShareSpaceRuntimeTests(unittest.TestCase):
    def _start_http_server(self, base: Path, static_root: Path) -> tuple[ThreadingHTTPServer, threading.Thread]:
        run_store = server.RunStore(base / ".runtime" / "stable" / ".runs")
        session_store = server.SessionStore(base_dir=run_store.runs_dir.parent)
        session_binding_store = server.SessionBindingStore(runs_dir=run_store.runs_dir)

        httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        httpd.static_root = static_root  # type: ignore[attr-defined]
        httpd.allow_root = base  # type: ignore[attr-defined]
        httpd.store = run_store  # type: ignore[attr-defined]
        httpd.session_store = session_store  # type: ignore[attr-defined]
        httpd.session_binding_store = session_binding_store  # type: ignore[attr-defined]
        httpd.http_log = base / ".run" / "test.http.log"  # type: ignore[attr-defined]
        httpd.scheduler = None  # type: ignore[attr-defined]
        httpd.environment_name = "stable"  # type: ignore[attr-defined]
        httpd.project_id = "task_dashboard"  # type: ignore[attr-defined]
        httpd.runtime_role = "prod"  # type: ignore[attr-defined]
        httpd.runs_dir = run_store.runs_dir  # type: ignore[attr-defined]
        httpd.worktree_root = base / "task-dashboard"  # type: ignore[attr-defined]
        httpd.sessions_file = run_store.runs_dir.parent / ".sessions" / "task_dashboard.json"  # type: ignore[attr-defined]
        httpd.project_scheduler_runtime = server.ProjectSchedulerRuntimeRegistry(store=run_store, session_store=session_store)  # type: ignore[attr-defined]
        httpd.task_push_runtime = server.TaskPushRuntimeRegistry(store=run_store, session_store=session_store)  # type: ignore[attr-defined]
        httpd.task_plan_runtime = server.TaskPlanRuntimeRegistry(  # type: ignore[attr-defined]
            store=run_store,
            session_store=session_store,
            task_push_runtime=httpd.task_push_runtime,
        )
        httpd.heartbeat_task_runtime = server.HeartbeatTaskRuntimeRegistry(  # type: ignore[attr-defined]
            store=run_store,
            session_store=session_store,
            task_push_runtime=httpd.task_push_runtime,
        )
        httpd.assist_request_runtime = server.AssistRequestRuntimeRegistry(store=run_store, session_store=session_store)  # type: ignore[attr-defined]

        t = threading.Thread(target=httpd.serve_forever, daemon=True)
        t.start()
        return httpd, t

    def test_share_space_config_round_trip_uses_runtime_local_store(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            code, payload = update_project_share_space_config_response(
                worktree_root=base,
                environment_name="stable",
                project_id="task_dashboard",
                raw_share_space={
                    "enabled": True,
                    "spaces": [
                        {
                            "share_id": "qoreon-client",
                            "title": "Qoreon Client Room",
                            "allowed_session_ids": ["019d1111-1111-7111-8111-111111111111"],
                            "access_token": "token-1",
                            "passcode": "2468",
                        }
                    ],
                },
            )

            self.assertEqual(200, code)
            share_space = payload["share_space"]
            self.assertTrue(share_space["enabled"])
            self.assertEqual("runtime_local", share_space["storage_mode"])
            self.assertEqual("qoreon-client", share_space["spaces"][0]["share_id"])
            self.assertEqual("token-1", share_space["spaces"][0]["access_token"])
            self.assertTrue(share_space_store_path(base, "stable", "task_dashboard").exists())

            loaded = load_project_share_space_config(
                worktree_root=base,
                environment_name="stable",
                project_id="task_dashboard",
            )
            self.assertEqual("qoreon-client", loaded["spaces"][0]["share_id"])

    def test_share_space_v2_action_patch_and_state_fields(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            code, payload = update_project_share_space_config_response(
                worktree_root=base,
                environment_name="stable",
                project_id="task_dashboard",
                raw_share_space={
                    "enabled": True,
                    "action": "upsert",
                    "space": {
                        "share_id": "business-a",
                        "name": "业务方A",
                        "allowed_session_ids": ["019d1111-1111-7111-8111-111111111111"],
                        "access_token": "token-a",
                    },
                },
            )
            self.assertEqual(200, code)
            space = payload["share_space"]["spaces"][0]
            self.assertEqual("业务方A", space["name"])
            self.assertEqual("业务方A", space["title"])
            self.assertTrue(space["enabled"])
            self.assertEqual("active", payload["share_space"]["summaries"][0]["status"])

            patch_code, patch_payload = update_project_share_space_config_response(
                worktree_root=base,
                environment_name="stable",
                project_id="task_dashboard",
                raw_share_space={
                    "action": "patch",
                    "share_id": "business-a",
                    "name": "业务方A-编辑后",
                    "permission": "read",
                },
            )
            self.assertEqual(200, patch_code)
            patched = patch_payload["share_space"]["spaces"][0]
            self.assertEqual("业务方A-编辑后", patched["name"])
            self.assertEqual("read", patched["permission"])
            self.assertEqual(["019d1111-1111-7111-8111-111111111111"], patched["allowed_session_ids"])
            self.assertEqual("token-a", patched["access_token"])
            self.assertEqual("read_only", patch_payload["share_space"]["summaries"][0]["status"])

    def test_share_bootstrap_filters_allowed_sessions_and_rejects_bad_token(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            run_store = server.RunStore(base / ".runtime" / "stable" / ".runs")
            session_store = server.SessionStore(base_dir=run_store.runs_dir.parent)
            allowed = session_store.create_session(
                "task_dashboard",
                "子级02-CCB运行时（server-并发-安全-启动）",
                cli_type="codex",
                alias="服务开发-分享协同",
                session_id="019d1111-1111-7111-8111-111111111111",
            )
            session_store.create_session(
                "task_dashboard",
                "子级04-前端体验（task-overview-交互）",
                cli_type="codex",
                alias="前端体验",
                session_id="019d1111-1111-7111-8111-222222222222",
            )
            update_project_share_space_config_response(
                worktree_root=base,
                environment_name="stable",
                project_id="task_dashboard",
                raw_share_space={
                    "enabled": True,
                    "spaces": [
                        {
                            "share_id": "qoreon-client",
                            "allowed_session_ids": [allowed["id"], "missing-session"],
                            "access_token": "token-1",
                            "passcode": "2468",
                        }
                    ],
                },
            )

            code, payload = build_share_bootstrap_response(
                worktree_root=base,
                environment_name="stable",
                project_id="task_dashboard",
                share_id="qoreon-client",
                access_token="token-1",
                passcode="2468",
                session_store=session_store,
                decorate_session_display_fields=lambda row: row,
            )

            self.assertEqual(200, code)
            self.assertEqual(1, payload["count"])
            self.assertEqual(allowed["id"], payload["agents"][0]["session_id"])
            self.assertEqual("服务开发-分享协同", payload["agents"][0]["agent_display_name"])
            self.assertEqual([{"session_id": "missing-session", "reason": "missing"}], payload["skipped"])

            bad_code, bad_payload = build_share_bootstrap_response(
                worktree_root=base,
                environment_name="stable",
                project_id="task_dashboard",
                share_id="qoreon-client",
                access_token="bad-token",
                passcode="2468",
                session_store=session_store,
            )
            self.assertEqual(401, bad_code)
            self.assertEqual("invalid share token", bad_payload["error"])

    def test_share_bootstrap_v4_payload_exposes_main_task_shell_allowlist_only(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            run_store = server.RunStore(base / ".runtime" / "stable" / ".runs")
            session_store = server.SessionStore(base_dir=run_store.runs_dir.parent)
            primary = session_store.create_session(
                "task_dashboard",
                "子级02-CCB运行时（server-并发-安全-启动）",
                alias="服务开发-分享协同",
                session_id="019d1111-1111-7111-8111-121212121212",
                is_primary=True,
            )
            session_store.create_session(
                "task_dashboard",
                "子级04-前端体验（task-overview-交互）",
                alias="分享协同界面",
                session_id="019d1111-1111-7111-8111-343434343434",
            )
            update_project_share_space_config_response(
                worktree_root=base,
                environment_name="stable",
                project_id="task_dashboard",
                raw_share_space={
                    "enabled": True,
                    "spaces": [
                        {
                            "share_id": "v4-room",
                            "name": "V4 业务方",
                            "allowed_session_ids": [primary["id"], "019d1111-1111-7111-8111-343434343434"],
                            "access_token": "token-v4",
                        }
                    ],
                },
            )

            code, payload = build_share_bootstrap_response(
                worktree_root=base,
                environment_name="stable",
                project_id="task_dashboard",
                share_id="v4-room",
                access_token="token-v4",
                passcode="",
                session_store=session_store,
            )
            self.assertEqual(200, code)
            self.assertEqual(primary["id"], payload["default_session_id"])
            self.assertEqual(primary["id"], payload["default_session"]["session_id"])
            share_mode = payload["share_mode"]
            self.assertEqual("share_mode.v4", share_mode["schema_version"])
            self.assertEqual("/share/project-task-dashboard.html", share_mode["entry"]["canonical_path"])
            self.assertEqual("/share/project-chat.html", share_mode["entry"]["legacy_path"])
            self.assertEqual(
                "redirect_task_shell_preserve_credentials",
                share_mode["entry"]["legacy_strategy"]["mode"],
            )
            self.assertEqual(
                [
                    "/api/share-spaces/v4-room/bootstrap",
                    "/api/share-spaces/v4-room/sessions/:session_id",
                    "/api/share-spaces/v4-room/announce",
                ],
                share_mode["endpoints"]["allowlist"],
            )
            self.assertEqual(
                {
                    "shell": "current_task_page",
                    "hide_top_tabs": True,
                    "hide_project_controls": True,
                    "hide_non_share_panels": True,
                    "agent_scope": "authorized_only",
                    "data_scope": "share_scoped_only",
                },
                share_mode["ui_contract"],
            )
            self.assertNotIn("display", share_mode)
            self.assertNotIn("permissions", share_mode)
            encoded = json.dumps(payload, ensure_ascii=False)
            self.assertNotIn("/api/sessions", encoded)
            self.assertNotIn("/api/channel-sessions", encoded)
            self.assertNotIn("/api/agent-candidates", encoded)
            self.assertNotIn("/api/fs/reveal", encoded)
            self.assertNotIn("/api/codex/announce", encoded)
            self.assertNotIn("viewer_role_label", encoded)
            self.assertNotIn("access_scope_text", encoded)
            self.assertNotIn("share_mode_intro", encoded)
            self.assertNotIn("permission_summary", encoded)
            self.assertNotIn("share_status_card", encoded)
            self.assertNotIn("capability_matrix", encoded)

    def test_share_bootstrap_isolates_multiple_share_objects(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            run_store = server.RunStore(base / ".runtime" / "stable" / ".runs")
            session_store = server.SessionStore(base_dir=run_store.runs_dir.parent)
            session_a = session_store.create_session(
                "task_dashboard",
                "子级02-CCB运行时（server-并发-安全-启动）",
                alias="后端协同",
                session_id="019d1111-1111-7111-8111-aaaaaaaaaaaa",
            )
            session_b = session_store.create_session(
                "task_dashboard",
                "子级04-前端体验（task-overview-交互）",
                alias="前端协同",
                session_id="019d1111-1111-7111-8111-bbbbbbbbbbbb",
            )
            update_project_share_space_config_response(
                worktree_root=base,
                environment_name="stable",
                project_id="task_dashboard",
                raw_share_space={
                    "enabled": True,
                    "spaces": [
                        {
                            "share_id": "business-a",
                            "name": "业务方A",
                            "allowed_session_ids": [session_a["id"]],
                            "access_token": "token-a",
                        },
                        {
                            "share_id": "business-b",
                            "name": "业务方B",
                            "allowed_session_ids": [session_b["id"]],
                            "access_token": "token-b",
                        },
                    ],
                },
            )

            code_a, payload_a = build_share_bootstrap_response(
                worktree_root=base,
                environment_name="stable",
                project_id="task_dashboard",
                share_id="business-a",
                access_token="token-a",
                passcode="",
                session_store=session_store,
            )
            code_b, payload_b = build_share_bootstrap_response(
                worktree_root=base,
                environment_name="stable",
                project_id="task_dashboard",
                share_id="business-b",
                access_token="token-b",
                passcode="",
                session_store=session_store,
            )
            self.assertEqual(200, code_a)
            self.assertEqual([session_a["id"]], [row["session_id"] for row in payload_a["agents"]])
            self.assertEqual("业务方A", payload_a["share_space"]["name"])
            self.assertEqual(1, payload_a["agent_groups"][0]["count"])
            self.assertEqual(200, code_b)
            self.assertEqual([session_b["id"]], [row["session_id"] for row in payload_b["agents"]])
            self.assertEqual("业务方B", payload_b["share_space"]["name"])

            blocked_code, blocked_payload = build_share_session_response(
                worktree_root=base,
                environment_name="stable",
                project_id="task_dashboard",
                share_id="business-a",
                session_id=session_b["id"],
                access_token="token-a",
                passcode="",
                session_store=session_store,
                store=run_store,
            )
            self.assertEqual(403, blocked_code)
            self.assertEqual("session not allowed by share_space", blocked_payload["error"])

    def test_share_space_state_rejects_disabled_revoked_and_deleted_objects(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            run_store = server.RunStore(base / ".runtime" / "stable" / ".runs")
            session_store = server.SessionStore(base_dir=run_store.runs_dir.parent)
            session = session_store.create_session(
                "task_dashboard",
                "子级02-CCB运行时（server-并发-安全-启动）",
                session_id="019d1111-1111-7111-8111-cccccccccccc",
            )
            update_project_share_space_config_response(
                worktree_root=base,
                environment_name="stable",
                project_id="task_dashboard",
                raw_share_space={
                    "enabled": True,
                    "spaces": [
                        {
                            "share_id": "disabled-room",
                            "enabled": False,
                            "allowed_session_ids": [session["id"]],
                            "access_token": "token-disabled",
                        },
                        {
                            "share_id": "revoked-room",
                            "revoked_at": "2026-04-16T00:00:00Z",
                            "allowed_session_ids": [session["id"]],
                            "access_token": "token-revoked",
                        },
                        {
                            "share_id": "deleted-room",
                            "deleted_at": "2026-04-16T00:00:00Z",
                            "allowed_session_ids": [session["id"]],
                            "access_token": "token-deleted",
                        },
                    ],
                },
            )

            disabled_code, disabled_payload = build_share_bootstrap_response(
                worktree_root=base,
                environment_name="stable",
                project_id="task_dashboard",
                share_id="disabled-room",
                access_token="token-disabled",
                passcode="",
                session_store=session_store,
            )
            self.assertEqual(403, disabled_code)
            self.assertEqual("disabled", disabled_payload["status"])

            revoked_code, revoked_payload = build_share_bootstrap_response(
                worktree_root=base,
                environment_name="stable",
                project_id="task_dashboard",
                share_id="revoked-room",
                access_token="token-revoked",
                passcode="",
                session_store=session_store,
            )
            self.assertEqual(403, revoked_code)
            self.assertEqual("revoked", revoked_payload["status"])

            deleted_code, deleted_payload = build_share_bootstrap_response(
                worktree_root=base,
                environment_name="stable",
                project_id="task_dashboard",
                share_id="deleted-room",
                access_token="token-deleted",
                passcode="",
                session_store=session_store,
            )
            self.assertEqual(404, deleted_code)
            self.assertEqual("deleted", deleted_payload["status"])

            delete_action_code, delete_action_payload = update_project_share_space_config_response(
                worktree_root=base,
                environment_name="stable",
                project_id="task_dashboard",
                raw_share_space={"action": "delete", "share_id": "disabled-room"},
            )
            self.assertEqual(200, delete_action_code)
            rows = {row["share_id"]: row for row in delete_action_payload["share_space"]["summaries"]}
            self.assertEqual("deleted", rows["disabled-room"]["status"])

    def test_share_space_delete_action_invalidates_all_share_gateways(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            run_store = server.RunStore(base / ".runtime" / "stable" / ".runs")
            session_store = server.SessionStore(base_dir=run_store.runs_dir.parent)
            session = session_store.create_session(
                "task_dashboard",
                "子级02-CCB运行时（server-并发-安全-启动）",
                session_id="019d1111-1111-7111-8111-dddddddddddd",
            )

            create_code, _create_payload = update_project_share_space_config_response(
                worktree_root=base,
                environment_name="stable",
                project_id="task_dashboard",
                raw_share_space={
                    "enabled": True,
                    "action": "upsert",
                    "space": {
                        "share_id": "delete-room",
                        "allowed_session_ids": [session["id"]],
                        "access_token": "token-delete",
                        "permission": "read_send",
                    },
                },
            )
            self.assertEqual(200, create_code)

            before_bootstrap_code, _before_bootstrap_payload = build_share_bootstrap_response(
                worktree_root=base,
                environment_name="stable",
                project_id="task_dashboard",
                share_id="delete-room",
                access_token="token-delete",
                passcode="",
                session_store=session_store,
            )
            before_session_code, _before_session_payload = build_share_session_response(
                worktree_root=base,
                environment_name="stable",
                project_id="task_dashboard",
                share_id="delete-room",
                session_id=session["id"],
                access_token="token-delete",
                passcode="",
                session_store=session_store,
                store=run_store,
            )
            before_announce_code, _before_announce_payload = build_share_announce_request(
                worktree_root=base,
                environment_name="stable",
                project_id="task_dashboard",
                share_id="delete-room",
                access_token="token-delete",
                passcode="",
                body={"session_id": session["id"], "message": "hello"},
                session_store=session_store,
            )
            self.assertEqual(200, before_bootstrap_code)
            self.assertEqual(200, before_session_code)
            self.assertEqual(200, before_announce_code)

            delete_code, delete_payload = update_project_share_space_config_response(
                worktree_root=base,
                environment_name="stable",
                project_id="task_dashboard",
                raw_share_space={"action": "delete", "share_id": "delete-room"},
            )
            self.assertEqual(200, delete_code)
            deleted_rows = {row["share_id"]: row for row in delete_payload["share_space"]["summaries"]}
            self.assertEqual("deleted", deleted_rows["delete-room"]["status"])

            bootstrap_code, bootstrap_payload = build_share_bootstrap_response(
                worktree_root=base,
                environment_name="stable",
                project_id="task_dashboard",
                share_id="delete-room",
                access_token="token-delete",
                passcode="",
                session_store=session_store,
            )
            session_code, session_payload = build_share_session_response(
                worktree_root=base,
                environment_name="stable",
                project_id="task_dashboard",
                share_id="delete-room",
                session_id=session["id"],
                access_token="token-delete",
                passcode="",
                session_store=session_store,
                store=run_store,
            )
            announce_code, announce_payload = build_share_announce_request(
                worktree_root=base,
                environment_name="stable",
                project_id="task_dashboard",
                share_id="delete-room",
                access_token="token-delete",
                passcode="",
                body={"session_id": session["id"], "message": "hello"},
                session_store=session_store,
            )
            self.assertEqual(404, bootstrap_code)
            self.assertEqual("deleted", bootstrap_payload["status"])
            self.assertNotEqual(200, session_code)
            self.assertEqual("deleted", session_payload["status"])
            self.assertNotEqual(200, announce_code)
            self.assertEqual("deleted", announce_payload["status"])

            stale_write_code, stale_write_payload = update_project_share_space_config_response(
                worktree_root=base,
                environment_name="stable",
                project_id="task_dashboard",
                raw_share_space={
                    "enabled": True,
                    "spaces": [
                        {
                            "share_id": "delete-room",
                            "enabled": True,
                            "deleted_at": "",
                            "allowed_session_ids": [session["id"]],
                            "access_token": "token-delete",
                            "permission": "read_send",
                        }
                    ],
                },
            )
            self.assertEqual(200, stale_write_code)
            stale_rows = {row["share_id"]: row for row in stale_write_payload["share_space"]["summaries"]}
            self.assertEqual("deleted", stale_rows["delete-room"]["status"])

            stale_bootstrap_code, stale_bootstrap_payload = build_share_bootstrap_response(
                worktree_root=base,
                environment_name="stable",
                project_id="task_dashboard",
                share_id="delete-room",
                access_token="token-delete",
                passcode="",
                session_store=session_store,
            )
            self.assertEqual(404, stale_bootstrap_code)
            self.assertEqual("deleted", stale_bootstrap_payload["status"])

    def test_share_session_response_returns_light_runs_without_internal_paths(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            run_store = server.RunStore(base / ".runtime" / "stable" / ".runs")
            session_store = server.SessionStore(base_dir=run_store.runs_dir.parent)
            session = session_store.create_session(
                "task_dashboard",
                "子级02-CCB运行时（server-并发-安全-启动）",
                cli_type="codex",
                alias="服务开发-分享协同",
                session_id="019d1111-1111-7111-8111-333333333333",
            )
            update_project_share_space_config_response(
                worktree_root=base,
                environment_name="stable",
                project_id="task_dashboard",
                raw_share_space={
                    "enabled": True,
                    "spaces": [
                        {
                            "share_id": "qoreon-client",
                            "allowed_session_ids": [session["id"]],
                            "access_token": "token-1",
                        }
                    ],
                },
            )
            run = run_store.create_run(
                project_id="task_dashboard",
                channel_name="子级02-CCB运行时（server-并发-安全-启动）",
                session_id=session["id"],
                message="hello from share session",
            )
            run_store._paths(str(run["id"]))["last"].write_text("assistant reply", encoding="utf-8")

            code, payload = build_share_session_response(
                worktree_root=base,
                environment_name="stable",
                project_id="task_dashboard",
                share_id="qoreon-client",
                session_id=session["id"],
                access_token="token-1",
                passcode="",
                session_store=session_store,
                store=run_store,
            )

            self.assertEqual(200, code)
            self.assertEqual(session["id"], payload["session"]["session_id"])
            self.assertEqual(1, payload["count"])
            self.assertEqual("hello from share session", payload["runs"][0]["messagePreview"])
            self.assertEqual("assistant reply", payload["runs"][0]["lastPreview"])
            self.assertNotIn("paths", payload["runs"][0])
            self.assertEqual(payload["runs"], payload["run_summaries"])
            self.assertEqual(2, len(payload["messages"]))
            self.assertEqual(session["id"], payload["share_mode"]["selected_session_id"])
            self.assertEqual(
                "/api/share-spaces/qoreon-client/announce",
                payload["share_mode"]["endpoints"]["announce_path"],
            )
            self.assertEqual(
                "/share/project-task-dashboard.html",
                payload["share_mode"]["entry"]["canonical_path"],
            )
            self.assertTrue(payload["composer"]["enabled"])
            self.assertEqual(2, len(payload["chat"]["messages"]))
            encoded = json.dumps(payload, ensure_ascii=False)
            self.assertNotIn("/api/sessions", encoded)
            self.assertNotIn("/api/channel-sessions", encoded)
            self.assertNotIn("/api/agent-candidates", encoded)
            self.assertNotIn("/api/fs/reveal", encoded)
            self.assertNotIn("/api/codex/announce", encoded)
            self.assertNotIn("share_status_card", encoded)

    def test_legacy_share_pages_redirect_to_task_shell_when_canonical_exists(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            static_root = base / "static"
            share_dir = static_root / "share"
            dist_dir = base / "dist"
            share_dir.mkdir(parents=True, exist_ok=True)
            dist_dir.mkdir(parents=True, exist_ok=True)
            (dist_dir / "project-task-dashboard.html").write_text("canonical", encoding="utf-8")
            (share_dir / "project-task-dashboard.html").symlink_to(dist_dir / "project-task-dashboard.html")

            httpd, t = self._start_http_server(base, static_root)
            port = int(httpd.server_address[1])
            try:
                class NoRedirect(url_request.HTTPRedirectHandler):
                    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
                        return None

                opener = url_request.build_opener(NoRedirect)
                for legacy_path in ("project-chat.html", "project-share-space.html"):
                    with self.assertRaises(url_error.HTTPError) as cm:
                        opener.open(
                            f"http://127.0.0.1:{port}/share/{legacy_path}?project_id=task_dashboard&share_id=v4-room&token=token-v4",
                            timeout=3,
                        )
                    self.assertEqual(302, cm.exception.code)
                    self.assertEqual(
                        "/share/project-task-dashboard.html?project_id=task_dashboard&share_id=v4-room&token=token-v4",
                        cm.exception.headers.get("Location"),
                    )
            finally:
                httpd.shutdown()
                t.join(timeout=2)
                httpd.server_close()

    def test_share_session_response_includes_native_timeline_fields(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            run_store = server.RunStore(base / ".runtime" / "stable" / ".runs")
            session_store = server.SessionStore(base_dir=run_store.runs_dir.parent)
            session = session_store.create_session(
                "task_dashboard",
                "子级02-CCB运行时（server-并发-安全-启动）",
                cli_type="codex",
                alias="服务开发-分享协同",
                session_id="019d1111-1111-7111-8111-999999999991",
            )
            update_project_share_space_config_response(
                worktree_root=base,
                environment_name="stable",
                project_id="task_dashboard",
                raw_share_space={
                    "enabled": True,
                    "spaces": [
                        {
                            "share_id": "qoreon-client",
                            "allowed_session_ids": [session["id"]],
                            "access_token": "token-1",
                        }
                    ],
                },
            )
            run = run_store.create_run(
                project_id="task_dashboard",
                channel_name="子级02-CCB运行时（server-并发-安全-启动）",
                session_id=session["id"],
                message="hello from share session",
                attachments=[
                    {
                        "filename": "demo.png",
                        "originalName": "demo.png",
                        "url": "/.runs/attachments/demo.png",
                    }
                ],
                extra_meta={
                    "mention_targets": [
                        {
                            "channel_name": "子级04-前端体验（task-overview-交互）",
                            "session_id": "019d1111-1111-7111-8111-999999999992",
                            "display_name": "前端协同",
                        }
                    ],
                    "reply_to_run_id": "20260417-000001-abcd1234",
                    "reply_to_sender_name": "产品策划-远程协作",
                    "reply_to_created_at": "2026-04-17T17:00:00+08:00",
                    "reply_to_preview": "请按当前页面原生能力继续纠偏。",
                    "communication_view": {"message_kind": "manual_update"},
                    "trigger_type": "manual_dispatch",
                },
            )
            run_store._paths(str(run["id"]))["last"].write_text("assistant reply", encoding="utf-8")

            code, payload = build_share_session_response(
                worktree_root=base,
                environment_name="stable",
                project_id="task_dashboard",
                share_id="qoreon-client",
                session_id=session["id"],
                access_token="token-1",
                passcode="",
                session_store=session_store,
                store=run_store,
            )

            self.assertEqual(200, code)
            row = payload["runs"][0]
            self.assertEqual(1, len(row["attachments"]))
            self.assertEqual("/.runs/attachments/demo.png", row["attachments"][0]["url"])
            self.assertEqual("前端协同", row["mention_targets"][0]["display_name"])
            self.assertEqual("20260417-000001-abcd1234", row["reply_to_run_id"])
            self.assertEqual("产品策划-远程协作", row["reply_to_sender_name"])
            self.assertEqual("2026-04-17T17:00:00+08:00", row["reply_to_created_at"])
            self.assertEqual("请按当前页面原生能力继续纠偏。", row["reply_to_preview"])
            self.assertEqual("manual_update", row["communication_view"]["message_kind"])
            self.assertEqual("manual_dispatch", row["trigger_type"])

    def test_share_announce_request_requires_read_send_and_whitelisted_session(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            run_store = server.RunStore(base / ".runtime" / "stable" / ".runs")
            session_store = server.SessionStore(base_dir=run_store.runs_dir.parent)
            session = session_store.create_session(
                "task_dashboard",
                "子级02-CCB运行时（server-并发-安全-启动）",
                cli_type="codex",
                alias="服务开发-分享协同",
                session_id="019d1111-1111-7111-8111-444444444444",
            )
            mentioned = session_store.create_session(
                "task_dashboard",
                "子级04-前端体验（task-overview-交互）",
                cli_type="codex",
                alias="前端协同",
                session_id="019d1111-1111-7111-8111-444444444445",
            )
            update_project_share_space_config_response(
                worktree_root=base,
                environment_name="stable",
                project_id="task_dashboard",
                raw_share_space={
                    "enabled": True,
                    "spaces": [
                        {
                            "share_id": "readonly-room",
                            "allowed_session_ids": [session["id"]],
                            "access_token": "token-1",
                            "permission": "read",
                        }
                    ],
                },
            )

            readonly_code, readonly_payload = build_share_announce_request(
                worktree_root=base,
                environment_name="stable",
                project_id="task_dashboard",
                share_id="readonly-room",
                access_token="token-1",
                passcode="",
                body={"sessionId": session["id"], "message": "hello"},
                session_store=session_store,
            )
            self.assertEqual(403, readonly_code)
            self.assertEqual("share_space send not allowed", readonly_payload["error"])

            update_project_share_space_config_response(
                worktree_root=base,
                environment_name="stable",
                project_id="task_dashboard",
                raw_share_space={
                    "enabled": True,
                    "spaces": [
                        {
                            "share_id": "send-room",
                            "allowed_session_ids": [session["id"], mentioned["id"]],
                            "access_token": "token-2",
                            "permission": "read_send",
                        }
                    ],
                },
            )
            send_code, send_payload = build_share_announce_request(
                worktree_root=base,
                environment_name="stable",
                project_id="task_dashboard",
                share_id="send-room",
                access_token="token-2",
                passcode="",
                body={
                    "session_id": session["id"],
                    "message": "hello",
                    "sender_name": "客户A",
                    "reply_to_run_id": "20260417-111111-aaaa1111",
                    "mention_targets": [
                        {
                            "channel_name": "待修正",
                            "session_id": mentioned["id"],
                            "display_name": "前端协同",
                        }
                    ],
                },
                session_store=session_store,
            )

            self.assertEqual(200, send_code)
            self.assertEqual(session["id"], send_payload["session_id"])
            self.assertEqual("客户A", send_payload["sender_name"])
            self.assertEqual("share:send-room", send_payload["sender_id"])
            self.assertEqual(
                "send-room",
                send_payload["extra_meta"]["share_space"]["share_id"],
            )
            self.assertEqual(
                "share_mode.v4",
                send_payload["extra_meta"]["share_mode"]["schema_version"],
            )
            self.assertEqual(
                session["id"],
                send_payload["extra_meta"]["share_mode"]["selected_session_id"],
            )
            self.assertEqual(
                [
                    {
                        "channel_name": "子级04-前端体验（task-overview-交互）",
                        "session_id": mentioned["id"],
                        "display_name": "前端协同",
                        "cli_type": "codex",
                        "project_id": "task_dashboard",
                    }
                ],
                send_payload["extra_meta"]["mention_targets"],
            )
            self.assertEqual(
                "20260417-111111-aaaa1111",
                send_payload["extra_meta"]["reply_to_run_id"],
            )

            blocked_code, blocked_payload = build_share_announce_request(
                worktree_root=base,
                environment_name="stable",
                project_id="task_dashboard",
                share_id="send-room",
                access_token="token-2",
                passcode="",
                body={"session_id": "019d1111-1111-7111-8111-555555555555", "message": "hello"},
                session_store=session_store,
            )
            self.assertEqual(403, blocked_code)
            self.assertEqual("session not allowed by share_space", blocked_payload["error"])

    def test_share_announce_request_rejects_unauthorized_mention_targets(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            run_store = server.RunStore(base / ".runtime" / "stable" / ".runs")
            session_store = server.SessionStore(base_dir=run_store.runs_dir.parent)
            session = session_store.create_session(
                "task_dashboard",
                "子级02-CCB运行时（server-并发-安全-启动）",
                cli_type="codex",
                alias="服务开发-分享协同",
                session_id="019d1111-1111-7111-8111-666666666666",
            )
            outsider = session_store.create_session(
                "task_dashboard",
                "子级08-专项验收（联调-验证-准出）",
                cli_type="codex",
                alias="专项验收",
                session_id="019d1111-1111-7111-8111-777777777777",
            )
            update_project_share_space_config_response(
                worktree_root=base,
                environment_name="stable",
                project_id="task_dashboard",
                raw_share_space={
                    "enabled": True,
                    "spaces": [
                        {
                            "share_id": "send-room",
                            "allowed_session_ids": [session["id"]],
                            "access_token": "token-2",
                            "permission": "read_send",
                        }
                    ],
                },
            )

            code, payload = build_share_announce_request(
                worktree_root=base,
                environment_name="stable",
                project_id="task_dashboard",
                share_id="send-room",
                access_token="token-2",
                passcode="",
                body={
                    "session_id": session["id"],
                    "message": "hello",
                    "mentionTargets": [
                        {
                            "channelName": "子级08-专项验收（联调-验证-准出）",
                            "sessionId": outsider["id"],
                            "displayName": "专项验收",
                        }
                    ],
                },
                session_store=session_store,
            )
            self.assertEqual(403, code)
            self.assertEqual("mention target not allowed by share_space", payload["error"])

    def test_share_announce_request_without_mention_targets_keeps_legacy_compatibility(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            run_store = server.RunStore(base / ".runtime" / "stable" / ".runs")
            session_store = server.SessionStore(base_dir=run_store.runs_dir.parent)
            session = session_store.create_session(
                "task_dashboard",
                "子级02-CCB运行时（server-并发-安全-启动）",
                cli_type="codex",
                alias="服务开发-分享协同",
                session_id="019d1111-1111-7111-8111-888888888888",
            )
            update_project_share_space_config_response(
                worktree_root=base,
                environment_name="stable",
                project_id="task_dashboard",
                raw_share_space={
                    "enabled": True,
                    "spaces": [
                        {
                            "share_id": "send-room",
                            "allowed_session_ids": [session["id"]],
                            "access_token": "token-2",
                            "permission": "read_send",
                        }
                    ],
                },
            )

            code, payload = build_share_announce_request(
                worktree_root=base,
                environment_name="stable",
                project_id="task_dashboard",
                share_id="send-room",
                access_token="token-2",
                passcode="",
                body={"session_id": session["id"], "message": "legacy payload"},
                session_store=session_store,
            )
            self.assertEqual(200, code)
            self.assertNotIn("mention_targets", payload["extra_meta"])


if __name__ == "__main__":
    unittest.main()
