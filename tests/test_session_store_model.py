import tempfile
import unittest
import json
from contextlib import nullcontext
from pathlib import Path
from unittest import mock

from task_dashboard.runtime.project_execution_context import build_project_execution_context
from task_dashboard.session_store import SessionStore


class SessionStoreModelTests(unittest.TestCase):
    def test_codex_session_write_uses_shared_migration_lock(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            with mock.patch(
                "task_dashboard.session_store.claude_model_migration_lock",
                side_effect=lambda *_args, **_kwargs: nullcontext(),
            ) as lock:
                SessionStore(base_dir=Path(td)).create_session(
                    project_id="task_dashboard",
                    channel_name="子级02-CCB运行时（server-并发-安全-启动）",
                    cli_type="codex",
                    session_id="01010101-0101-0101-0101-010101010101",
                    model="gpt-5.4",
                )

            self.assertGreater(lock.call_count, 0)
            for call in lock.call_args_list:
                self.assertFalse(call.kwargs["exclusive"])
                self.assertEqual(call.kwargs["timeout_s"], 30.0)

    def test_create_session_persists_model(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = SessionStore(base_dir=Path(td))
            sess = store.create_session(
                project_id="task_dashboard",
                channel_name="子级03-多CLI适配器（codex-claude-opencode）",
                cli_type="codex",
                session_id="11111111-1111-1111-1111-111111111111",
                model="codex-spark",
                reasoning_effort="high",
            )
            self.assertEqual(sess.get("model"), "codex-spark")
            self.assertEqual(sess.get("reasoning_effort"), "high")

            got = store.get_session("11111111-1111-1111-1111-111111111111") or {}
            self.assertEqual(got.get("model"), "codex-spark")
            self.assertEqual(got.get("reasoning_effort"), "high")

    def test_create_and_update_session_persists_agent_name(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = SessionStore(base_dir=Path(td))
            created = store.create_session(
                project_id="task_dashboard",
                channel_name="子级02-CCB运行时（server-并发-安全-启动）",
                cli_type="codex",
                session_id="10101010-1010-1010-1010-101010101010",
                alias="后端-任务业务",
                agent_name="后端-任务业务",
            )
            self.assertEqual(created.get("agent_name"), "后端-任务业务")

            updated = store.update_session(
                "10101010-1010-1010-1010-101010101010",
                agent_name="任务维度运行时",
            ) or {}
            self.assertEqual(updated.get("agent_name"), "任务维度运行时")

            got = store.get_session("10101010-1010-1010-1010-101010101010") or {}
            self.assertEqual(got.get("alias"), "后端-任务业务")
            self.assertEqual(got.get("agent_name"), "任务维度运行时")

    def test_update_session_supports_model(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = SessionStore(base_dir=Path(td))
            store.create_session(
                project_id="task_dashboard",
                channel_name="子级03-多CLI适配器（codex-claude-opencode）",
                cli_type="codex",
                session_id="11111111-1111-1111-1111-111111111111",
            )
            updated = store.update_session("11111111-1111-1111-1111-111111111111", model="codex-spark") or {}
            self.assertEqual(updated.get("model"), "codex-spark")

            got = store.get_session("11111111-1111-1111-1111-111111111111") or {}
            self.assertEqual(got.get("model"), "codex-spark")

    def test_legacy_claude_model_is_not_lazily_migrated_but_explicit_write_is(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            store = SessionStore(base_dir=base)
            sid = "15151515-1515-1515-1515-151515151515"
            store.create_session(
                project_id="task_dashboard",
                channel_name="子级02-CCB运行时（server-并发-安全-启动）",
                cli_type="claude",
                session_id=sid,
                model="claude-fable-5",
            )
            path = base / ".sessions" / "task_dashboard.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["sessions"][0]["model"] = "claude-opus-4-8"
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            before = path.read_bytes()

            listed = store.list_sessions("task_dashboard")
            fetched = store.get_session(sid) or {}

            self.assertEqual(listed[0].get("model"), "claude-opus-4-8")
            self.assertEqual(fetched.get("model"), "claude-opus-4-8")
            self.assertEqual(path.read_bytes(), before)

            heartbeat = store.update_session(sid, heartbeat={"enabled": True}) or {}
            self.assertEqual(heartbeat.get("model"), "claude-opus-4-8")
            persisted = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(persisted["sessions"][0].get("model"), "claude-opus-4-8")

            updated = store.update_session(sid, model="claude-opus-4-8") or {}
            self.assertEqual(updated.get("model"), "claude-opus-5")
            persisted = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(persisted["sessions"][0].get("model"), "claude-opus-5")

    def test_update_session_supports_status(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = SessionStore(base_dir=Path(td))
            store.create_session(
                project_id="task_dashboard",
                channel_name="辅助04-原型设计与Demo可视化（静态数据填充-业务规格确认）",
                cli_type="codex",
                session_id="12121212-1212-1212-1212-121212121212",
            )
            inactive = store.update_session(
                "12121212-1212-1212-1212-121212121212",
                status="inactive",
            ) or {}
            self.assertEqual(inactive.get("status"), "inactive")

            active = store.update_session(
                "12121212-1212-1212-1212-121212121212",
                status="active",
            ) or {}
            self.assertEqual(active.get("status"), "active")

            got = store.get_session("12121212-1212-1212-1212-121212121212") or {}
            self.assertEqual(got.get("status"), "active")

    def test_update_session_supports_reasoning_effort(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = SessionStore(base_dir=Path(td))
            store.create_session(
                project_id="task_dashboard",
                channel_name="子级03-多CLI适配器（codex-claude-opencode）",
                cli_type="codex",
                session_id="22222222-2222-2222-2222-222222222222",
            )
            updated = store.update_session(
                "22222222-2222-2222-2222-222222222222",
                reasoning_effort="extra_high",
            ) or {}
            self.assertEqual(updated.get("reasoning_effort"), "extra_high")

            got = store.get_session("22222222-2222-2222-2222-222222222222") or {}
            self.assertEqual(got.get("reasoning_effort"), "extra_high")

    def test_session_store_persists_work_context_fields(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = SessionStore(base_dir=Path(td))
            sess = store.create_session(
                project_id="task_dashboard",
                channel_name="子级01-Build引擎（扫描-解析-聚合-渲染）",
                cli_type="codex",
                session_id="23232323-2323-2323-2323-232323232323",
                environment="refactor",
                worktree_root="/tmp/task-dashboard-refactor",
                workdir="/tmp/task-dashboard-refactor/project",
                branch="refactor/p1-work-context",
            )
            self.assertEqual(sess.get("environment"), "refactor")
            self.assertEqual(sess.get("worktree_root"), "/tmp/task-dashboard-refactor")
            self.assertEqual(sess.get("workdir"), "/tmp/task-dashboard-refactor/project")
            self.assertEqual(sess.get("branch"), "refactor/p1-work-context")

            updated = store.update_session(
                "23232323-2323-2323-2323-232323232323",
                environment="stable",
                worktree_root="/tmp/task-dashboard",
                workdir="/tmp/task-dashboard/project",
                branch="main",
            ) or {}
            self.assertEqual(updated.get("environment"), "stable")
            self.assertEqual(updated.get("worktree_root"), "/tmp/task-dashboard")
            self.assertEqual(updated.get("workdir"), "/tmp/task-dashboard/project")
            self.assertEqual(updated.get("branch"), "main")

    def test_update_session_supports_heartbeat_config(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = SessionStore(base_dir=Path(td))
            store.create_session(
                project_id="task_dashboard",
                channel_name="子级02-CCB运行时（server-并发-安全-启动）",
                cli_type="codex",
                session_id="33333333-3333-3333-3333-333333333333",
            )
            heartbeat = {
                "enabled": True,
                "tasks": [
                    {
                        "heartbeat_task_id": "ops-daily",
                        "title": "每日巡查",
                    }
                ],
            }
            updated = store.update_session(
                "33333333-3333-3333-3333-333333333333",
                heartbeat=heartbeat,
            ) or {}
            self.assertEqual((updated.get("heartbeat") or {}).get("enabled"), True)
            got = store.get_session("33333333-3333-3333-3333-333333333333") or {}
            self.assertEqual((got.get("heartbeat") or {}).get("tasks")[0].get("heartbeat_task_id"), "ops-daily")
            self.assertEqual(got.get("project_id"), "task_dashboard")

    def test_create_session_strips_inherited_context_fields_when_context_matches_project(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = SessionStore(base_dir=Path(td))
            context = build_project_execution_context(
                target={
                    "project_id": "task_dashboard",
                    "environment": "stable",
                    "worktree_root": "/tmp/task-dashboard",
                    "workdir": "/tmp/task-dashboard",
                    "branch": "main",
                },
                source={
                    "project_id": "task_dashboard",
                    "environment": "stable",
                    "worktree_root": "/tmp/task-dashboard",
                    "workdir": "/tmp/task-dashboard",
                    "branch": "main",
                },
                context_source="project",
            )
            sess = store.create_session(
                project_id="task_dashboard",
                channel_name="主体-总控（合并与验收）",
                session_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                environment="stable",
                worktree_root="/tmp/task-dashboard",
                workdir="/tmp/task-dashboard",
                branch="main",
                project_execution_context=context,
            )
            self.assertEqual(sess.get("environment"), "")
            self.assertEqual(sess.get("worktree_root"), "")
            self.assertEqual(sess.get("workdir"), "")
            self.assertEqual(sess.get("branch"), "")

    def test_update_session_keeps_only_true_override_fields(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = SessionStore(base_dir=Path(td))
            base_context = build_project_execution_context(
                target={
                    "project_id": "task_dashboard",
                    "environment": "stable",
                    "worktree_root": "/tmp/task-dashboard",
                    "workdir": "/tmp/task-dashboard",
                    "branch": "main",
                },
                source={
                    "project_id": "task_dashboard",
                    "environment": "stable",
                    "worktree_root": "/tmp/task-dashboard",
                    "workdir": "/tmp/task-dashboard",
                    "branch": "main",
                },
                context_source="project",
            )
            store.create_session(
                project_id="task_dashboard",
                channel_name="主体-总控（合并与验收）",
                session_id="cccccccc-cccc-cccc-cccc-cccccccccccc",
                project_execution_context=base_context,
            )
            override_context = build_project_execution_context(
                target={
                    "project_id": "task_dashboard",
                    "environment": "stable",
                    "worktree_root": "/tmp/task-dashboard",
                    "workdir": "/tmp/task-dashboard/custom",
                    "branch": "feature/session-override",
                },
                source={
                    "project_id": "task_dashboard",
                    "environment": "stable",
                    "worktree_root": "/tmp/task-dashboard",
                    "workdir": "/tmp/task-dashboard",
                    "branch": "main",
                },
                context_source="project",
                override_fields=["workdir", "branch"],
                override_source="session",
            )
            updated = store.update_session(
                "cccccccc-cccc-cccc-cccc-cccccccccccc",
                environment="stable",
                worktree_root="/tmp/task-dashboard",
                workdir="/tmp/task-dashboard/custom",
                branch="feature/session-override",
                project_execution_context=override_context,
            ) or {}
            self.assertEqual(updated.get("environment"), "")
            self.assertEqual(updated.get("worktree_root"), "")
            self.assertEqual(updated.get("workdir"), "/tmp/task-dashboard/custom")
            self.assertEqual(updated.get("branch"), "feature/session-override")

    def test_get_session_ignores_stale_top_level_fields_when_context_has_no_override(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            store = SessionStore(base_dir=base)
            sid = "dddddddd-dddd-dddd-dddd-dddddddddddd"
            path = base / ".sessions" / "task_dashboard.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(
                    {
                        "project_id": "task_dashboard",
                        "sessions": [
                            {
                                "id": sid,
                                "cli_type": "codex",
                                "channel_name": "主体-总控（合并与验收）",
                                "status": "active",
                                "is_primary": True,
                                "is_deleted": False,
                                "created_at": "2026-03-17T00:00:00Z",
                                "last_used_at": "2026-03-17T00:00:00Z",
                                "environment": "stable",
                                "worktree_root": "/tmp/legacy-task-dashboard",
                                "workdir": "/tmp/legacy-task-dashboard",
                                "branch": "legacy-branch",
                                "project_execution_context": {
                                    "target": {
                                        "project_id": "task_dashboard",
                                        "channel_name": "主体-总控（合并与验收）",
                                        "session_id": sid,
                                        "environment": "stable",
                                        "worktree_root": "/tmp/legacy-task-dashboard",
                                        "workdir": "/tmp/legacy-task-dashboard",
                                        "branch": "legacy-branch",
                                    },
                                    "source": {
                                        "project_id": "task_dashboard",
                                        "environment": "stable",
                                        "worktree_root": "/tmp/live-task-dashboard",
                                        "workdir": "/tmp/live-task-dashboard",
                                        "branch": "main",
                                    },
                                    "context_source": "project",
                                    "override": {
                                        "applied": False,
                                        "fields": [],
                                        "source": "",
                                    },
                                },
                            }
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            got = store.get_session(sid) or {}
            self.assertEqual(got.get("environment"), "")
            self.assertEqual(got.get("worktree_root"), "")
            self.assertEqual(got.get("workdir"), "")
            self.assertEqual(got.get("branch"), "")
            ctx = got.get("project_execution_context") or {}
            target = ctx.get("target") or {}
            self.assertEqual(target.get("worktree_root"), "/tmp/live-task-dashboard")
            self.assertEqual(target.get("workdir"), "/tmp/live-task-dashboard")
            self.assertEqual(target.get("branch"), "main")

            saved = json.loads(path.read_text(encoding="utf-8"))
            saved_row = ((saved.get("sessions") or [])[0] or {})
            saved_target = ((saved_row.get("project_execution_context") or {}).get("target") or {})
            self.assertEqual(saved_target.get("worktree_root"), "/tmp/live-task-dashboard")
            self.assertEqual(saved_target.get("workdir"), "/tmp/live-task-dashboard")
            self.assertEqual(saved_target.get("branch"), "main")

    def test_first_session_in_channel_defaults_primary(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = SessionStore(base_dir=Path(td))
            first = store.create_session(
                project_id="task_dashboard",
                channel_name="子级04-前端体验（task-overview 页面交互）",
                cli_type="codex",
                session_id="44444444-4444-4444-4444-444444444444",
            )
            second = store.create_session(
                project_id="task_dashboard",
                channel_name="子级04-前端体验（task-overview 页面交互）",
                cli_type="codex",
                session_id="55555555-5555-5555-5555-555555555555",
            )
            self.assertTrue(bool(first.get("is_primary")))
            self.assertFalse(bool(second.get("is_primary")))

    def test_manage_channel_sessions_supports_primary_and_soft_delete(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = SessionStore(base_dir=Path(td))
            sid1 = "66666666-6666-6666-6666-666666666666"
            sid2 = "77777777-7777-7777-7777-777777777777"
            store.create_session(
                project_id="task_dashboard",
                channel_name="子级04-前端体验（task-overview 页面交互）",
                cli_type="codex",
                session_id=sid1,
            )
            store.create_session(
                project_id="task_dashboard",
                channel_name="子级04-前端体验（task-overview 页面交互）",
                cli_type="codex",
                session_id=sid2,
            )
            result = store.manage_channel_sessions(
                "task_dashboard",
                "子级04-前端体验（task-overview 页面交互）",
                primary_session_id=sid2,
                updates=[
                    {"session_id": sid1, "is_deleted": True, "deleted_reason": "archive"},
                    {"session_id": sid2, "is_deleted": False},
                ],
            )
            rows = result.get("sessions") or []
            row1 = next((row for row in rows if row.get("id") == sid1), {})
            row2 = next((row for row in rows if row.get("id") == sid2), {})
            self.assertTrue(bool(row1.get("is_deleted")))
            self.assertEqual(row1.get("deleted_reason"), "archive")
            self.assertTrue(bool(row2.get("is_primary")))
            visible = store.list_sessions("task_dashboard", "子级04-前端体验（task-overview 页面交互）")
            self.assertEqual(len(visible), 1)
            self.assertEqual((visible[0] or {}).get("id"), sid2)
            default_row = store.get_channel_default_session("task_dashboard", "子级04-前端体验（task-overview 页面交互）") or {}
            self.assertEqual(default_row.get("id"), sid2)

    def test_delete_session_marks_session_deleted_and_promotes_fallback_primary(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = SessionStore(base_dir=Path(td))
            sid1 = "67676767-6767-6767-6767-676767676767"
            sid2 = "78787878-7878-7878-7878-787878787878"
            channel_name = "辅助05-督办PMO（排期-巡查-催办-升级）"
            first = store.create_session(
                project_id="task_dashboard",
                channel_name=channel_name,
                cli_type="codex",
                session_id=sid1,
                session_role="primary",
                is_primary=True,
            )
            second = store.create_session(
                project_id="task_dashboard",
                channel_name=channel_name,
                cli_type="codex",
                session_id=sid2,
            )
            self.assertTrue(bool(first.get("is_primary")))
            self.assertFalse(bool(second.get("is_primary")))

            self.assertTrue(store.delete_session(sid1))

            deleted = store.get_session(sid1) or {}
            fallback = store.get_session(sid2) or {}
            self.assertTrue(bool(deleted.get("is_deleted")))
            self.assertEqual(str(deleted.get("deleted_reason") or ""), "api_delete_session")
            self.assertFalse(bool(deleted.get("is_primary")))
            self.assertTrue(str(deleted.get("deleted_at") or ""))
            self.assertTrue(bool(fallback.get("is_primary")))
            visible = store.list_sessions("task_dashboard", channel_name)
            self.assertEqual([row.get("id") for row in visible], [sid2])

    def test_channel_default_and_manage_skip_context_exhausted_primary(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = SessionStore(base_dir=Path(td))
            exhausted_sid = "68686868-6868-6868-6868-686868686868"
            replacement_sid = "79797979-7979-7979-7979-797979797979"
            channel_name = "子级02-CCB运行时（server-并发-安全-启动）"
            store.create_session(
                project_id="task_dashboard",
                channel_name=channel_name,
                cli_type="codex",
                session_id=exhausted_sid,
                alias="旧主 Agent",
                session_role="primary",
                is_primary=True,
                context_binding_state="context_exhausted",
            )
            store.create_session(
                project_id="task_dashboard",
                channel_name=channel_name,
                cli_type="codex",
                session_id=replacement_sid,
                alias="新主 Agent",
            )

            default_row = store.get_channel_default_session("task_dashboard", channel_name) or {}
            self.assertEqual(default_row.get("id"), replacement_sid)

            result = store.manage_channel_sessions(
                "task_dashboard",
                channel_name,
                primary_session_id=exhausted_sid,
            )
            rows = {row.get("id"): row for row in result.get("sessions") or []}
            self.assertEqual(result.get("primary_session_id"), replacement_sid)
            self.assertFalse(bool((rows.get(exhausted_sid) or {}).get("is_primary")))
            self.assertTrue(bool((rows.get(replacement_sid) or {}).get("is_primary")))

    def test_get_channel_default_session_ignores_legacy_status_field(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            store = SessionStore(base_dir=base)
            sid = "76767676-7676-7676-7676-767676767676"
            path = base / ".sessions" / "task_dashboard.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(
                    {
                        "project_id": "task_dashboard",
                        "sessions": [
                            {
                                "id": sid,
                                "cli_type": "codex",
                                "channel_name": "子级02-CCB运行时（server-并发-安全-启动）",
                                "alias": "legacy-inactive",
                                "status": "inactive",
                                "is_primary": True,
                                "is_deleted": False,
                                "created_at": "2026-03-19T00:00:00Z",
                                "last_used_at": "2026-03-19T01:00:00Z",
                            }
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            default_row = store.get_channel_default_session(
                "task_dashboard",
                "子级02-CCB运行时（server-并发-安全-启动）",
            ) or {}
            self.assertEqual(default_row.get("id"), sid)

    def test_create_session_supports_v2_metadata_and_explicit_primary(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = SessionStore(base_dir=Path(td))
            primary = store.create_session(
                project_id="task_dashboard",
                channel_name="子级02-CCB运行时（server-并发-安全-启动）",
                cli_type="codex",
                session_id="88888888-8888-8888-8888-888888888888",
                session_role="primary",
                purpose="master",
                reuse_strategy="reuse_or_create",
                is_primary=True,
            )
            child = store.create_session(
                project_id="task_dashboard",
                channel_name="子级02-CCB运行时（server-并发-安全-启动）",
                cli_type="codex",
                session_id="99999999-9999-9999-9999-999999999999",
                session_role="child",
                purpose="task_with_receipt",
                reuse_strategy="create_new",
                is_primary=False,
            )
            self.assertTrue(bool(primary.get("is_primary")))
            self.assertEqual(primary.get("session_role"), "primary")
            self.assertFalse(bool(child.get("is_primary")))
            self.assertEqual(child.get("session_role"), "child")
            self.assertEqual(child.get("purpose"), "task_with_receipt")
            self.assertEqual(child.get("reuse_strategy"), "create_new")

            promoted = store.create_session(
                project_id="task_dashboard",
                channel_name="子级02-CCB运行时（server-并发-安全-启动）",
                cli_type="codex",
                session_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                session_role="primary",
                purpose="takeover",
                reuse_strategy="create_new",
                is_primary=True,
            )
            got_primary = store.get_session("88888888-8888-8888-8888-888888888888") or {}
            got_child = store.get_session("99999999-9999-9999-9999-999999999999") or {}
            got_promoted = store.get_session("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa") or {}
            self.assertFalse(bool(got_primary.get("is_primary")))
            self.assertFalse(bool(got_child.get("is_primary")))
            self.assertTrue(bool(promoted.get("is_primary")))
            self.assertTrue(bool(got_promoted.get("is_primary")))


if __name__ == "__main__":
    unittest.main()
