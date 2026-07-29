import json
import os
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError
from urllib import request as url_request

import server
from task_dashboard.adapters import SessionInfo
from task_dashboard.runtime.request_parsing import parse_session_create_request, parse_session_update_fields
from task_dashboard.runtime.session_context import apply_session_work_context
from task_dashboard.runtime.session_admin import SessionIdentityError, create_session_response


class SessionCreateV2Tests(unittest.TestCase):
    def _start_server(self, base: Path):
        static_root = base / "static"
        static_root.mkdir(parents=True, exist_ok=True)
        (static_root / "index.html").write_text("ok", encoding="utf-8")

        run_store = server.RunStore(base / ".runs")
        session_store = server.SessionStore(base_dir=base)
        session_binding_store = server.SessionBindingStore(runs_dir=run_store.runs_dir)

        httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        httpd.static_root = static_root  # type: ignore[attr-defined]
        httpd.allow_root = static_root  # type: ignore[attr-defined]
        httpd.store = run_store  # type: ignore[attr-defined]
        httpd.session_store = session_store  # type: ignore[attr-defined]
        httpd.session_binding_store = session_binding_store  # type: ignore[attr-defined]
        httpd.http_log = base / ".run" / "test.http.log"  # type: ignore[attr-defined]
        httpd.scheduler = None  # type: ignore[attr-defined]
        httpd.environment_name = "refactor"  # type: ignore[attr-defined]
        httpd.worktree_root = str(base / "worktree-refactor")  # type: ignore[attr-defined]
        return httpd, session_store

    def test_parse_session_create_request_reads_v2_fields(self) -> None:
        payload = parse_session_create_request(
            {
                "project_id": "task_dashboard",
                "channel_name": "子级07",
                "cli_type": "codex",
                "model": "gpt-5.3-codex",
                "reasoningEffort": "high",
                "alias": "服务开发-通讯能力",
                "agentName": "服务开发-通讯能力",
                "environmentName": "refactor",
                "worktreeRoot": "/tmp/worktree",
                "workdir": "/tmp/worktree",
                "branch": "feature/v2",
                "sessionRole": "sub",
                "purpose": "验证创建",
                "reuseStrategy": "reuse_active",
                "setAsPrimary": False,
                "firstMessage": "hello",
            }
        )
        self.assertEqual(payload["environment"], "refactor")
        self.assertEqual(payload["worktree_root"], "/tmp/worktree")
        self.assertEqual(payload["branch"], "feature/v2")
        self.assertEqual(payload["alias"], "服务开发-通讯能力")
        self.assertEqual(payload["agent_name"], "服务开发-通讯能力")
        self.assertEqual(payload["session_role"], "child")
        self.assertEqual(payload["purpose"], "验证创建")
        self.assertEqual(payload["reuse_strategy"], "reuse_active")
        self.assertIs(payload["set_as_primary"], False)

        agent_name_only = parse_session_create_request(
            {
                "project_id": "task_dashboard",
                "channel_name": "子级07",
                "agentName": "只传 AgentName",
            }
        )
        self.assertEqual(agent_name_only["agent_name"], "只传 AgentName")
        self.assertEqual(agent_name_only["alias"], "只传 AgentName")

    def test_codex_model_and_reasoning_empty_values_preserve_inheritance(self) -> None:
        create_payload = parse_session_create_request(
            {
                "project_id": "task_dashboard",
                "channel_name": "子级03",
                "cli_type": "codex",
                "model": "  ",
                "reasoningEffort": "",
            }
        )
        update_fields = parse_session_update_fields(
            {
                "model": "",
                "reasoningEffort": "",
            }
        )

        self.assertEqual(create_payload["model"], "")
        self.assertEqual(create_payload["reasoning_effort"], "")
        self.assertEqual(update_fields["model"], "")
        self.assertEqual(update_fields["reasoning_effort"], "")

    def test_parse_session_create_request_tracks_codebuddy_permission_explicitness(self) -> None:
        missing_payload = parse_session_create_request(
            {
                "project_id": "task_dashboard",
                "channel_name": "子级07",
                "cli_type": "codebuddy",
            }
        )
        self.assertEqual(missing_payload["codebuddy_permission_mode"], "")
        self.assertIs(missing_payload["_codebuddy_permission_mode_explicit"], False)

        explicit_payload = parse_session_create_request(
            {
                "project_id": "task_dashboard",
                "channel_name": "子级07",
                "cli_type": "codebuddy",
                "codebuddyPermissionMode": "bypass_permissions",
            }
        )
        self.assertEqual(explicit_payload["codebuddy_permission_mode"], "bypassPermissions")
        self.assertIs(explicit_payload["_codebuddy_permission_mode_explicit"], True)

    def test_parse_session_create_request_routes_claude_permission_mode(self) -> None:
        payload = parse_session_create_request(
            {
                "project_id": "task_dashboard",
                "channel_name": "子级02",
                "cliType": "claude",
                "permissionMode": "plan",
                "codebuddyPermissionMode": "bypassPermissions",
            }
        )

        self.assertEqual(payload["cli_type"], "claude")
        self.assertEqual(payload["claude_permission_mode"], "plan")
        self.assertIs(payload["_claude_permission_mode_explicit"], True)
        self.assertEqual(payload["codebuddy_permission_mode"], "")
        self.assertIs(payload["_codebuddy_permission_mode_explicit"], False)

    def test_parse_session_create_request_normalizes_claude_model(self) -> None:
        legacy_payload = parse_session_create_request(
            {
                "project_id": "task_dashboard",
                "channel_name": "子级02",
                "cliType": "claude",
                "model": "claude-sonnet-4-20250514",
            }
        )
        invalid_payload = parse_session_create_request(
            {
                "project_id": "task_dashboard",
                "channel_name": "子级02",
                "cliType": "claude",
                "model": "辅助04-原型设计",
            }
        )
        fable_payload = parse_session_create_request(
            {
                "project_id": "task_dashboard",
                "channel_name": "子级02",
                "cliType": "claude",
                "model": "fable-5",
            }
        )
        non_claude_payload = parse_session_create_request(
            {
                "project_id": "task_dashboard",
                "channel_name": "子级02",
                "cliType": "codebuddy",
                "model": "deepseek-v4-pro",
            }
        )
        inherited_payload = parse_session_create_request(
            {
                "project_id": "task_dashboard",
                "channel_name": "子级02",
                "cliType": "claude",
            }
        )

        self.assertEqual(legacy_payload["model"], "claude-sonnet-4-6")
        self.assertEqual(invalid_payload["model"], "claude-opus-5")
        self.assertEqual(fable_payload["model"], "claude-fable-5")
        self.assertEqual(non_claude_payload["model"], "deepseek-v4-pro")
        self.assertIs(legacy_payload["_model_explicit"], True)
        self.assertEqual(inherited_payload["model"], "claude-opus-5")
        self.assertIs(inherited_payload["_model_explicit"], False)

    def test_parse_session_update_fields_normalizes_claude_model_when_cli_type_present(self) -> None:
        fields = parse_session_update_fields(
            {
                "cliType": "claude",
                "model": "claude-haiku",
                "agentName": "Claude 子会话",
            }
        )

        self.assertEqual(fields["model"], "claude-haiku-4-5")
        self.assertEqual(fields["agent_name"], "Claude 子会话")

    def test_session_store_normalizes_existing_claude_model_on_update(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.SessionStore(base_dir=Path(td))
            created = store.create_session(
                "task_dashboard",
                "子级02",
                cli_type="claude",
                model="claude-opus-4-20250514",
            )
            self.assertEqual(created.get("model"), "claude-opus-5")

            updated = store.update_session(str(created.get("id") or ""), model="辅助04-原型设计")

            self.assertEqual((updated or {}).get("model"), "claude-opus-5")

    def test_create_session_response_preserves_copy_reuse_strategy(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            workdir = base / "wt"
            workdir.mkdir(parents=True, exist_ok=True)

            def _fake_create_cli_session(**_kwargs):
                return {
                    "ok": True,
                    "sessionId": "019c0000-0000-7000-8000-000000000099",
                    "sessionPath": "/tmp/fake-session.json",
                    "workdir": str(workdir),
                }

            result = create_session_response(
                payload={
                    "project_id": "task_dashboard",
                    "channel_name": "子级07",
                    "cli_type": "codex",
                    "alias": "复制会话",
                    "environment": "refactor",
                    "worktree_root": str(workdir),
                    "workdir": str(workdir),
                    "branch": "feature/copy",
                    "session_role": "child",
                    "purpose": "session_copy_clone",
                    "reuse_strategy": "copy",
                },
                session_store=server.SessionStore(base),
                environment_name="refactor",
                worktree_root=str(workdir),
                create_cli_session=_fake_create_cli_session,
                resolve_project_workdir=lambda _pid: workdir,
                detect_git_branch=lambda _root: "feature/fallback",
                build_session_seed_prompt=lambda **_kwargs: "seed",
                decorate_session_display_fields=lambda row: row,
                apply_session_work_context=lambda row, **_kwargs: row,
                load_project_execution_context=lambda *_args, **_kwargs: {"profile": "project_privileged_full"},
                project_exists=lambda _pid: True,
                channel_exists=lambda _pid, _channel: True,
            )
            session = result.get("session") or {}
            self.assertEqual(session.get("reuse_strategy"), "copy")
            self.assertEqual(session.get("purpose"), "session_copy_clone")

    def test_create_session_response_requires_alias_for_new_agent(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            with self.assertRaises(SessionIdentityError) as ctx:
                create_session_response(
                    payload={
                        "project_id": "task_dashboard",
                        "channel_name": "子级07",
                        "cli_type": "codex",
                    },
                    session_store=server.SessionStore(base),
                    environment_name="refactor",
                    worktree_root=str(base),
                    create_cli_session=lambda **_kwargs: {"ok": True},
                    resolve_project_workdir=lambda _pid: base,
                    detect_git_branch=lambda _root: "main",
                    build_session_seed_prompt=lambda **_kwargs: "seed",
                    decorate_session_display_fields=lambda row: row,
                    apply_session_work_context=lambda row, **_kwargs: row,
                    load_project_execution_context=lambda *_args, **_kwargs: {},
                    project_exists=lambda _pid: True,
                    channel_exists=lambda _pid, _channel: True,
                )

            self.assertEqual(ctx.exception.error_code, "alias_required")

    def test_create_session_response_rejects_active_alias_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            store = server.SessionStore(base)
            store.create_session(
                "task_dashboard",
                "子级07",
                session_id="019c0000-0000-7000-8000-000000000011",
                alias="重名 Agent",
            )
            with self.assertRaises(SessionIdentityError) as ctx:
                create_session_response(
                    payload={
                        "project_id": "task_dashboard",
                        "channel_name": "子级08",
                        "cli_type": "codex",
                        "alias": "重名 Agent",
                    },
                    session_store=store,
                    environment_name="refactor",
                    worktree_root=str(base),
                    create_cli_session=lambda **_kwargs: {"ok": True},
                    resolve_project_workdir=lambda _pid: base,
                    detect_git_branch=lambda _root: "main",
                    build_session_seed_prompt=lambda **_kwargs: "seed",
                    decorate_session_display_fields=lambda row: row,
                    apply_session_work_context=lambda row, **_kwargs: row,
                    load_project_execution_context=lambda *_args, **_kwargs: {},
                    project_exists=lambda _pid: True,
                    channel_exists=lambda _pid, _channel: True,
                )

            self.assertEqual(ctx.exception.error_code, "alias_conflict")
            self.assertEqual((ctx.exception.payload.get("conflict") or {}).get("session_id"), "019c0000-0000-7000-8000-000000000011")

    def test_create_session_response_ignores_inactive_alias_for_identity_gate(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            workdir = base / "wt"
            workdir.mkdir(parents=True, exist_ok=True)
            store = server.SessionStore(base)
            old = store.create_session(
                "task_dashboard",
                "子级07",
                session_id="019c0000-0000-7000-8000-000000000012",
                alias="可复用 Agent 名",
            )
            store.update_session(str(old.get("id") or ""), status="inactive")

            result = create_session_response(
                payload={
                    "project_id": "task_dashboard",
                    "channel_name": "子级08",
                    "cli_type": "codex",
                    "alias": "可复用 Agent 名",
                },
                session_store=store,
                environment_name="refactor",
                worktree_root=str(workdir),
                create_cli_session=lambda **_kwargs: {
                    "ok": True,
                    "sessionId": "019c0000-0000-7000-8000-000000000013",
                    "sessionPath": "/tmp/fake-session.json",
                    "workdir": str(workdir),
                },
                resolve_project_workdir=lambda _pid: workdir,
                detect_git_branch=lambda _root: "main",
                build_session_seed_prompt=lambda **_kwargs: "seed",
                decorate_session_display_fields=lambda row: row,
                apply_session_work_context=lambda row, **_kwargs: row,
                load_project_execution_context=lambda *_args, **_kwargs: {},
                project_exists=lambda _pid: True,
                channel_exists=lambda _pid, _channel: True,
            )

            self.assertTrue(bool(result.get("created")))
            self.assertEqual((result.get("session") or {}).get("alias"), "可复用 Agent 名")

    def test_create_session_response_rotate_replaces_same_channel_alias(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            workdir = base / "wt"
            workdir.mkdir(parents=True, exist_ok=True)
            store = server.SessionStore(base)
            old = store.create_session(
                "task_dashboard",
                "子级02",
                cli_type="codex",
                session_id="019c0000-0000-7000-8000-000000000021",
                alias="后端-任务业务",
                agent_name="后端-任务业务",
                purpose="旧主会话",
                session_role="primary",
                is_primary=True,
            )

            result = create_session_response(
                payload={
                    "project_id": "task_dashboard",
                    "channel_name": "子级02",
                    "cli_type": "codex",
                    "alias": "后端-任务业务",
                    "agent_name": "后端-任务业务",
                    "purpose": "轮替后主会话",
                    "reuse_strategy": "rotate",
                    "environment": "refactor",
                    "worktree_root": str(workdir),
                    "workdir": str(workdir),
                },
                session_store=store,
                environment_name="refactor",
                worktree_root=str(workdir),
                create_cli_session=lambda **_kwargs: {
                    "ok": True,
                    "sessionId": "019c0000-0000-7000-8000-000000000022",
                    "sessionPath": "/tmp/fake-session.json",
                    "workdir": str(workdir),
                },
                resolve_project_workdir=lambda _pid: workdir,
                detect_git_branch=lambda _root: "main",
                build_session_seed_prompt=lambda **_kwargs: "seed",
                decorate_session_display_fields=lambda row: row,
                apply_session_work_context=lambda row, **_kwargs: row,
                load_project_execution_context=lambda *_args, **_kwargs: {},
                project_exists=lambda _pid: True,
                channel_exists=lambda _pid, _channel: True,
            )

            session = result.get("session") or {}
            old_after = store.get_session(str(old.get("id") or "")) or {}
            new_after = store.get_session(str(session.get("id") or "")) or {}
            self.assertTrue(bool(result.get("rotated")))
            self.assertEqual(result.get("replaced_session_ids"), [old["id"]])
            self.assertEqual(session.get("alias"), "后端-任务业务")
            self.assertEqual(session.get("purpose"), "轮替后主会话")
            self.assertTrue(bool(session.get("is_primary")))
            self.assertTrue(bool(new_after.get("is_primary")))
            self.assertTrue(bool(old_after.get("is_deleted")))
            self.assertEqual(old_after.get("deleted_reason"), "session_rotate_alias_takeover")
            self.assertFalse(bool(old_after.get("is_primary")))

    def test_create_session_response_rotate_follows_context_exhausted_identity(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            workdir = base / "wt"
            workdir.mkdir(parents=True, exist_ok=True)
            store = server.SessionStore(base)
            old = store.create_session(
                "task_dashboard",
                "子级02",
                cli_type="codex",
                session_id="019c0000-0000-7000-8000-000000000023",
                alias="任务维度运行时",
                agent_name="后端-任务业务",
                purpose="CCB 运行时主会话",
                session_role="primary",
                is_primary=True,
                context_binding_state="context_exhausted",
            )

            result = create_session_response(
                payload={
                    "project_id": "task_dashboard",
                    "channel_name": "子级02",
                    "cli_type": "codex",
                    "reuse_strategy": "rotate",
                    "environment": "refactor",
                    "worktree_root": str(workdir),
                    "workdir": str(workdir),
                },
                session_store=store,
                environment_name="refactor",
                worktree_root=str(workdir),
                create_cli_session=lambda **_kwargs: {
                    "ok": True,
                    "sessionId": "019c0000-0000-7000-8000-000000000024",
                    "sessionPath": "/tmp/fake-session.json",
                    "workdir": str(workdir),
                },
                resolve_project_workdir=lambda _pid: workdir,
                detect_git_branch=lambda _root: "main",
                build_session_seed_prompt=lambda **_kwargs: "seed",
                decorate_session_display_fields=lambda row: row,
                apply_session_work_context=lambda row, **_kwargs: row,
                load_project_execution_context=lambda *_args, **_kwargs: {},
                project_exists=lambda _pid: True,
                channel_exists=lambda _pid, _channel: True,
            )

            session = result.get("session") or {}
            old_after = store.get_session(str(old.get("id") or "")) or {}
            self.assertTrue(bool(result.get("rotated")))
            self.assertEqual(session.get("alias"), "任务维度运行时")
            self.assertEqual(session.get("agent_name"), "后端-任务业务")
            self.assertEqual(session.get("purpose"), "CCB 运行时主会话")
            self.assertTrue(bool(session.get("is_primary")))
            self.assertTrue(bool(old_after.get("is_deleted")))
            self.assertFalse(bool(old_after.get("is_primary")))

    def test_create_session_response_defaults_workdir_to_channel_root(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            project_root = base / "project"
            channel_root = project_root / "任务规划" / "业务03-规划样本"
            channel_root.mkdir(parents=True, exist_ok=True)
            create_calls: list[dict[str, object]] = []

            def _fake_create_cli_session(**kwargs):
                create_calls.append(kwargs)
                return {
                    "ok": True,
                    "sessionId": "019c0000-0000-7000-8000-000000000123",
                    "sessionPath": "/tmp/fake-session.json",
                    "workdir": str(kwargs.get("workdir") or ""),
                }

            result = create_session_response(
                payload={
                    "project_id": "task_dashboard",
                    "channel_name": "业务03-规划样本",
                    "cli_type": "codex",
                    "alias": "业务03-规划样本主会话",
                    "environment": "refactor",
                    "worktree_root": str(project_root),
                    "branch": "feature/channel-workdir",
                },
                session_store=server.SessionStore(base),
                environment_name="refactor",
                worktree_root=str(project_root),
                create_cli_session=_fake_create_cli_session,
                resolve_project_workdir=lambda _pid: project_root,
                resolve_channel_workdir=lambda _pid, _channel: channel_root,
                detect_git_branch=lambda _root: "feature/fallback",
                build_session_seed_prompt=lambda **_kwargs: "seed",
                decorate_session_display_fields=lambda row: row,
                apply_session_work_context=lambda row, **_kwargs: row,
                load_project_execution_context=lambda *_args, **_kwargs: {"profile": "project_privileged_full"},
                project_exists=lambda _pid: True,
                channel_exists=lambda _pid, _channel: True,
            )

            self.assertEqual(Path(create_calls[0]["workdir"]).resolve(), channel_root.resolve())
            self.assertEqual(Path(result["workdir"]).resolve(), channel_root.resolve())
            self.assertEqual(Path((result.get("session") or {}).get("workdir")).resolve(), channel_root.resolve())

    def test_parse_session_create_request_normalizes_legacy_extra_high_reasoning(self) -> None:
        payload = parse_session_create_request(
            {
                "project_id": "task_dashboard",
                "channel_name": "子级07",
                "cli_type": "codex",
                "reasoningEffort": "extra_high",
            }
        )
        self.assertEqual(payload["reasoning_effort"], "xhigh")

    def test_create_session_response_reuses_active_session(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            store = server.SessionStore(base)
            existing = store.create_session(
                "task_dashboard",
                "子级07",
                cli_type="codex",
                session_id="019c0000-0000-7000-8000-000000000007",
                alias="旧会话",
                environment="refactor",
                worktree_root=str(base / "wt"),
                workdir=str(base / "wt"),
                branch="feature/old",
                session_role="primary",
                is_primary=True,
            )
            create_calls: list[dict[str, object]] = []

            def _fake_create_cli_session(**kwargs):
                create_calls.append(kwargs)
                return {"ok": True, "sessionId": "unexpected", "sessionPath": "", "workdir": str(base / "wt")}

            payload = {
                "project_id": "task_dashboard",
                "channel_name": "子级07",
                "cli_type": "codex",
                "alias": "复用后别名",
                "environment": "refactor",
                "worktree_root": str(base / "wt"),
                "workdir": str(base / "wt"),
                "branch": "feature/new",
                "session_role": "child",
                "purpose": "复用验证",
                "reuse_strategy": "reuse_active",
            }
            result = create_session_response(
                payload=payload,
                session_store=store,
                environment_name="refactor",
                worktree_root=str(base / "wt"),
                create_cli_session=_fake_create_cli_session,
                resolve_project_workdir=lambda _pid: base / "wt",
                detect_git_branch=lambda _root: "feature/fallback",
                build_session_seed_prompt=lambda **_kwargs: "seed",
                decorate_session_display_fields=lambda row: row,
                apply_session_work_context=lambda row, **_kwargs: row,
                load_project_execution_context=lambda *_args, **_kwargs: {"profile": "project_privileged_full"},
                project_exists=lambda _pid: True,
                channel_exists=lambda _pid, _channel: True,
            )
            self.assertFalse(bool(create_calls))
            self.assertTrue(bool(result.get("reused")))
            session = result.get("session") or {}
            self.assertEqual(session.get("id"), existing["id"])
            self.assertEqual(session.get("alias"), "复用后别名")
            self.assertEqual(session.get("purpose"), "复用验证")
            self.assertEqual(session.get("schema_version"), "session.create.v2")
            self.assertEqual(session.get("created_via"), "api.create_session_v2.reuse")
            self.assertEqual(session.get("context_binding_state"), "bound")

    def test_reuse_active_claude_session_inherits_existing_model_when_omitted(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            workdir = base / "wt"
            workdir.mkdir()
            store = server.SessionStore(base)
            existing = store.create_session(
                "task_dashboard",
                "子级02",
                cli_type="claude",
                session_id="019c0000-0000-7000-8000-00000000005a",
                alias="Claude Fable",
                model="claude-fable-5",
                environment="refactor",
                worktree_root=str(workdir),
                workdir=str(workdir),
                is_primary=True,
            )
            payload = parse_session_create_request(
                {
                    "project_id": "task_dashboard",
                    "channel_name": "子级02",
                    "cli_type": "claude",
                    "reuse_strategy": "reuse_active",
                }
            )

            result = create_session_response(
                payload=payload,
                session_store=store,
                environment_name="refactor",
                worktree_root=str(workdir),
                create_cli_session=lambda **_kwargs: self.fail("reuse_active 不应创建新 CLI 会话"),
                resolve_project_workdir=lambda _pid: workdir,
                detect_git_branch=lambda _root: "main",
                build_session_seed_prompt=lambda **_kwargs: "seed",
                decorate_session_display_fields=lambda row: row,
                apply_session_work_context=lambda row, **_kwargs: row,
                load_project_execution_context=lambda *_args, **_kwargs: {"profile": "project_privileged_full"},
                project_exists=lambda _pid: True,
                channel_exists=lambda _pid, _channel: True,
            )

            self.assertTrue(bool(result.get("reused")))
            self.assertEqual((result.get("session") or {}).get("id"), existing["id"])
            self.assertEqual((result.get("session") or {}).get("model"), "claude-fable-5")
            self.assertEqual((store.get_session(existing["id"]) or {}).get("model"), "claude-fable-5")

    def test_create_session_response_reuse_active_preserves_codebuddy_permission_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            workdir = base / "wt"
            workdir.mkdir(parents=True, exist_ok=True)
            store = server.SessionStore(base)
            existing = store.create_session(
                "task_dashboard",
                "子级07",
                cli_type="codebuddy",
                session_id="019c0000-0000-7000-8000-0000000000cb",
                alias="旧 CodeBuddy 会话",
                codebuddy_permission_mode="bypassPermissions",
                environment="refactor",
                worktree_root=str(workdir),
                workdir=str(workdir),
                branch="feature/codebuddy-permission",
                session_role="primary",
                is_primary=True,
            )

            def _unexpected_create_cli_session(**_kwargs):
                raise AssertionError("reuse_active 不应创建新 CLI 会话")

            result = create_session_response(
                payload={
                    "project_id": "task_dashboard",
                    "channel_name": "子级07",
                    "cli_type": "codebuddy",
                    "alias": "复用 CodeBuddy 会话",
                    "environment": "refactor",
                    "worktree_root": str(workdir),
                    "workdir": str(workdir),
                    "branch": "feature/codebuddy-permission",
                    "reuse_strategy": "reuse_active",
                },
                session_store=store,
                environment_name="refactor",
                worktree_root=str(workdir),
                create_cli_session=_unexpected_create_cli_session,
                resolve_project_workdir=lambda _pid: workdir,
                detect_git_branch=lambda _root: "feature/fallback",
                build_session_seed_prompt=lambda **_kwargs: "seed",
                decorate_session_display_fields=lambda row: row,
                apply_session_work_context=lambda row, **_kwargs: row,
                load_project_execution_context=lambda *_args, **_kwargs: {"profile": "project_privileged_full"},
                project_exists=lambda _pid: True,
                channel_exists=lambda _pid, _channel: True,
            )

            self.assertTrue(bool(result.get("reused")))
            session = result.get("session") or {}
            self.assertEqual(session.get("id"), existing["id"])
            self.assertEqual(session.get("codebuddy_permission_mode"), "bypassPermissions")
            stored = store.get_session(str(existing.get("id"))) or {}
            self.assertEqual(stored.get("codebuddy_permission_mode"), "bypassPermissions")

    def test_create_session_response_reuse_active_accepts_explicit_codebuddy_default_permission(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            workdir = base / "wt"
            workdir.mkdir(parents=True, exist_ok=True)
            store = server.SessionStore(base)
            existing = store.create_session(
                "task_dashboard",
                "子级07",
                cli_type="codebuddy",
                session_id="019c0000-0000-7000-8000-0000000000cd",
                alias="旧 CodeBuddy 会话",
                codebuddy_permission_mode="bypassPermissions",
                environment="refactor",
                worktree_root=str(workdir),
                workdir=str(workdir),
                branch="feature/codebuddy-permission",
                session_role="primary",
                is_primary=True,
            )

            def _unexpected_create_cli_session(**_kwargs):
                raise AssertionError("reuse_active 不应创建新 CLI 会话")

            result = create_session_response(
                payload={
                    "project_id": "task_dashboard",
                    "channel_name": "子级07",
                    "cli_type": "codebuddy",
                    "alias": "CodeBuddy 静态文件会话",
                    "environment": "refactor",
                    "worktree_root": str(workdir),
                    "workdir": str(workdir),
                    "branch": "feature/codebuddy-permission",
                    "reuse_strategy": "reuse_active",
                    "codebuddyPermissionMode": "default",
                    "_codebuddy_permission_mode_explicit": True,
                },
                session_store=store,
                environment_name="refactor",
                worktree_root=str(workdir),
                create_cli_session=_unexpected_create_cli_session,
                resolve_project_workdir=lambda _pid: workdir,
                detect_git_branch=lambda _root: "feature/fallback",
                build_session_seed_prompt=lambda **_kwargs: "seed",
                decorate_session_display_fields=lambda row: row,
                apply_session_work_context=lambda row, **_kwargs: row,
                load_project_execution_context=lambda *_args, **_kwargs: {"profile": "project_privileged_full"},
                project_exists=lambda _pid: True,
                channel_exists=lambda _pid, _channel: True,
            )

            self.assertTrue(bool(result.get("reused")))
            session = result.get("session") or {}
            self.assertEqual(session.get("id"), existing["id"])
            self.assertEqual(session.get("codebuddy_permission_mode"), "default")
            stored = store.get_session(str(existing.get("id"))) or {}
            self.assertEqual(stored.get("codebuddy_permission_mode"), "default")

    def test_create_session_response_ensures_codebuddy_static_instruction_files(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            workdir = base / "wt"
            workdir.mkdir(parents=True, exist_ok=True)
            ensure_calls: list[dict[str, object]] = []
            create_calls: list[dict[str, object]] = []

            def _ensure_static_instruction_files(**kwargs):
                ensure_calls.append(kwargs)
                return {
                    "mirrors": [
                        {
                            "cliType": "codebuddy",
                            "fileName": "CODEBUDDY.md",
                            "syncStatus": "synced",
                        }
                    ],
                    "summary": {"synced": 1},
                }

            def _fake_create_cli_session(**kwargs):
                create_calls.append(kwargs)
                self.assertEqual(len(ensure_calls), 1)
                return {
                    "ok": True,
                    "sessionId": "019c0000-0000-7000-8000-0000000000ce",
                    "sessionPath": "/tmp/codebuddy-session.json",
                    "workdir": str(workdir),
                }

            result = create_session_response(
                payload={
                    "project_id": "task_dashboard",
                    "channel_name": "子级07",
                    "cli_type": "codebuddy",
                    "alias": "CodeBuddy 静态文件会话",
                    "environment": "refactor",
                    "worktree_root": str(workdir),
                    "workdir": str(workdir),
                    "branch": "feature/codebuddy-static",
                    "reuse_strategy": "create_new",
                },
                session_store=server.SessionStore(base),
                environment_name="refactor",
                worktree_root=str(workdir),
                create_cli_session=_fake_create_cli_session,
                resolve_project_workdir=lambda _pid: workdir,
                detect_git_branch=lambda _root: "feature/fallback",
                build_session_seed_prompt=lambda **_kwargs: "seed",
                decorate_session_display_fields=lambda row: row,
                apply_session_work_context=lambda row, **_kwargs: row,
                load_project_execution_context=lambda *_args, **_kwargs: {"profile": "project_privileged_full"},
                project_exists=lambda _pid: True,
                channel_exists=lambda _pid, _channel: True,
                ensure_static_instruction_files=_ensure_static_instruction_files,
            )

            self.assertEqual(len(create_calls), 1)
            self.assertEqual(ensure_calls[0]["project_id"], "task_dashboard")
            self.assertEqual(ensure_calls[0]["channel_name"], "子级07")
            self.assertEqual(ensure_calls[0]["cli_type"], "codebuddy")
            self.assertEqual(
                ((result.get("static_instruction_files") or {}).get("mirrors") or [])[0].get("syncStatus"),
                "synced",
            )

    def test_create_session_response_reuses_legacy_inactive_session(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            store = server.SessionStore(base)
            existing = store.create_session(
                "task_dashboard",
                "子级07",
                cli_type="codex",
                session_id="019c0000-0000-7000-8000-000000000017",
                alias="旧会话",
                environment="refactor",
                worktree_root=str(base / "wt"),
                workdir=str(base / "wt"),
                branch="feature/old",
                session_role="primary",
                is_primary=True,
            )
            project_file = base / ".sessions" / "task_dashboard.json"
            payload = json.loads(project_file.read_text(encoding="utf-8"))
            sessions = payload.get("sessions") or []
            sessions[0]["status"] = "inactive"
            project_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

            create_calls: list[dict[str, object]] = []

            def _fake_create_cli_session(**kwargs):
                create_calls.append(kwargs)
                return {"ok": True, "sessionId": "unexpected", "sessionPath": "", "workdir": str(base / "wt")}

            result = create_session_response(
                payload={
                    "project_id": "task_dashboard",
                    "channel_name": "子级07",
                    "cli_type": "codex",
                    "alias": "复用后别名",
                    "environment": "refactor",
                    "worktree_root": str(base / "wt"),
                    "workdir": str(base / "wt"),
                    "branch": "feature/new",
                    "session_role": "child",
                    "purpose": "复用验证",
                    "reuse_strategy": "reuse_active",
                },
                session_store=store,
                environment_name="refactor",
                worktree_root=str(base / "wt"),
                create_cli_session=_fake_create_cli_session,
                resolve_project_workdir=lambda _pid: base / "wt",
                detect_git_branch=lambda _root: "feature/fallback",
                build_session_seed_prompt=lambda **_kwargs: "seed",
                decorate_session_display_fields=lambda row: row,
                apply_session_work_context=lambda row, **_kwargs: row,
                load_project_execution_context=lambda *_args, **_kwargs: {"profile": "project_privileged_full"},
                project_exists=lambda _pid: True,
                channel_exists=lambda _pid, _channel: True,
            )

            self.assertFalse(bool(create_calls))
            self.assertTrue(bool(result.get("reused")))
            session = result.get("session") or {}
            self.assertEqual(session.get("id"), existing["id"])
            self.assertEqual(session.get("alias"), "复用后别名")

    def test_attach_existing_session_rebuilds_context_from_project_source(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            store = server.SessionStore(base)
            stable_root = base / "task-dashboard-stable"
            stable_workdir = stable_root / "runtime"
            stable_workdir.mkdir(parents=True, exist_ok=True)
            sid = "019c0000-0000-7000-8000-000000000010"
            (base / ".sessions").mkdir(parents=True, exist_ok=True)
            (base / ".sessions" / "task_dashboard.json").write_text(
                json.dumps(
                    {
                        "project_id": "task_dashboard",
                        "sessions": [
                            {
                                "id": sid,
                                "cli_type": "codex",
                                "channel_name": "子级07",
                                "status": "active",
                                "is_primary": True,
                                "is_deleted": False,
                                "created_at": "2026-03-17T00:00:00Z",
                                "last_used_at": "2026-03-17T00:00:00Z",
                                "environment": "stable",
                                "worktree_root": str(base / "legacy-task-dashboard"),
                                "workdir": str(base / "legacy-task-dashboard"),
                                "branch": "legacy-branch",
                                "project_execution_context": {
                                    "target": {
                                        "project_id": "task_dashboard",
                                        "channel_name": "子级07",
                                        "session_id": sid,
                                        "environment": "stable",
                                        "worktree_root": str(base / "legacy-task-dashboard"),
                                        "workdir": str(base / "legacy-task-dashboard"),
                                        "branch": "legacy-branch",
                                    },
                                    "source": {
                                        "project_id": "task_dashboard",
                                        "environment": "stable",
                                        "worktree_root": str(stable_root),
                                        "workdir": str(stable_workdir),
                                        "branch": "release/live",
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

            def _load_project_execution_context(*_args, **_kwargs):
                return {
                    "project_id": "task_dashboard",
                    "environment": "stable",
                    "worktree_root": str(stable_root),
                    "workdir": str(stable_workdir),
                    "branch": "release/live",
                }

            def _apply_row_context(row, **kwargs):
                return apply_session_work_context(
                    row,
                    resolve_project_workdir=lambda _pid: stable_workdir,
                    load_project_execution_context=_load_project_execution_context,
                    **kwargs,
                )

            result = create_session_response(
                payload={
                    "project_id": "task_dashboard",
                    "channel_name": "子级07",
                    "session_id": sid,
                    "mode": "attach_existing",
                    "cli_type": "codex",
                    "alias": "恢复上下文会话",
                },
                session_store=store,
                environment_name="stable",
                worktree_root=str(stable_root),
                create_cli_session=lambda **_kwargs: {"ok": True},
                resolve_project_workdir=lambda _pid: stable_workdir,
                detect_git_branch=lambda _root: "release/live",
                build_session_seed_prompt=lambda **_kwargs: "seed",
                decorate_session_display_fields=lambda row: row,
                apply_session_work_context=_apply_row_context,
                load_project_execution_context=_load_project_execution_context,
                project_exists=lambda _pid: True,
                channel_exists=lambda _pid, _channel: True,
            )

            session = result.get("session") or {}
            self.assertTrue(bool(result.get("attached")))
            self.assertEqual(session.get("environment"), "stable")
            self.assertEqual(session.get("worktree_root"), str(stable_root))
            self.assertEqual(session.get("workdir"), str(stable_workdir))
            self.assertEqual(session.get("branch"), "release/live")

            stored = store.get_session(sid) or {}
            self.assertEqual(stored.get("environment"), "")
            self.assertEqual(stored.get("worktree_root"), "")
            self.assertEqual(stored.get("workdir"), "")
            self.assertEqual(stored.get("branch"), "")
            stored_ctx = stored.get("project_execution_context") or {}
            self.assertEqual((stored_ctx.get("target") or {}).get("worktree_root"), str(stable_root))
            self.assertEqual((stored_ctx.get("target") or {}).get("workdir"), str(stable_workdir))
            self.assertEqual((stored_ctx.get("source") or {}).get("worktree_root"), str(stable_root))
            self.assertFalse(bool((stored_ctx.get("override") or {}).get("applied")))

    def test_attach_existing_claude_session_inherits_existing_model_when_omitted(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            workdir = base / "wt"
            workdir.mkdir()
            store = server.SessionStore(base)
            sid = "019c0000-0000-7000-8000-00000000005b"
            store.create_session(
                "task_dashboard",
                "子级02",
                cli_type="claude",
                session_id=sid,
                alias="Claude Sonnet",
                model="claude-sonnet-4-6",
                environment="refactor",
                worktree_root=str(workdir),
                workdir=str(workdir),
            )
            payload = parse_session_create_request(
                {
                    "project_id": "task_dashboard",
                    "channel_name": "子级02",
                    "cli_type": "claude",
                    "mode": "attach_existing",
                    "session_id": sid,
                }
            )

            with mock.patch(
                "task_dashboard.runtime.session_admin._cli_session_exists_for_attach",
                return_value=True,
            ):
                result = create_session_response(
                    payload=payload,
                    session_store=store,
                    environment_name="refactor",
                    worktree_root=str(workdir),
                    create_cli_session=lambda **_kwargs: self.fail("attach_existing 不应创建新 CLI 会话"),
                    resolve_project_workdir=lambda _pid: workdir,
                    detect_git_branch=lambda _root: "main",
                    build_session_seed_prompt=lambda **_kwargs: "seed",
                    decorate_session_display_fields=lambda row: row,
                    apply_session_work_context=lambda row, **_kwargs: row,
                    load_project_execution_context=lambda *_args, **_kwargs: {"profile": "project_privileged_full"},
                    project_exists=lambda _pid: True,
                    channel_exists=lambda _pid, _channel: True,
                )

            self.assertTrue(bool(result.get("attached")))
            self.assertEqual((result.get("session") or {}).get("model"), "claude-sonnet-4-6")
            self.assertEqual((store.get_session(sid) or {}).get("model"), "claude-sonnet-4-6")

    def test_attach_existing_session_accepts_opencode_session_id(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            store = server.SessionStore(base)
            sid = "ses_2f5d8b87cffekbHfJtB5IXE0DX"
            result = create_session_response(
                payload={
                    "project_id": "task_dashboard",
                    "channel_name": "子级07",
                    "session_id": sid,
                    "mode": "attach_existing",
                    "cli_type": "opencode",
                    "alias": "OpenCode 接入会话",
                },
                session_store=store,
                environment_name="refactor",
                worktree_root=str(base / "worktree-refactor"),
                create_cli_session=lambda **_kwargs: {"ok": True},
                resolve_project_workdir=lambda _pid: base,
                detect_git_branch=lambda _root: "feature/opencode",
                build_session_seed_prompt=lambda **_kwargs: "seed",
                decorate_session_display_fields=lambda row: row,
                apply_session_work_context=lambda row, **_kwargs: row,
                load_project_execution_context=lambda *_args, **_kwargs: {},
                project_exists=lambda _pid: True,
                channel_exists=lambda _pid, _channel: True,
            )

            session = result.get("session") or {}
            self.assertTrue(bool(result.get("attached")))
            self.assertEqual(session.get("id"), sid)
            self.assertEqual(session.get("cli_type"), "opencode")

    def test_attach_existing_claude_session_rejects_missing_conversation(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            store = server.SessionStore(base)
            sid = "019c0000-0000-7000-8000-0000000000aa"

            def _unexpected_create_cli_session(**_kwargs):
                raise AssertionError("attach_existing 不应创建新 CLI 会话")

            with mock.patch("task_dashboard.adapters.claude_adapter.ClaudeAdapter.scan_sessions", return_value=[]):
                with self.assertRaisesRegex(ValueError, "claude session_id not found"):
                    create_session_response(
                        payload={
                            "project_id": "task_dashboard",
                            "channel_name": "子级07",
                            "session_id": sid,
                            "mode": "attach_existing",
                            "cli_type": "claude",
                            "alias": "Claude 缺失会话",
                        },
                        session_store=store,
                        environment_name="refactor",
                        worktree_root=str(base / "worktree-refactor"),
                        create_cli_session=_unexpected_create_cli_session,
                        resolve_project_workdir=lambda _pid: base,
                        detect_git_branch=lambda _root: "feature/claude-attach",
                        build_session_seed_prompt=lambda **_kwargs: "seed",
                        decorate_session_display_fields=lambda row: row,
                        apply_session_work_context=lambda row, **_kwargs: row,
                        load_project_execution_context=lambda *_args, **_kwargs: {},
                        project_exists=lambda _pid: True,
                        channel_exists=lambda _pid, _channel: True,
                    )

            self.assertEqual(store.get_session(sid), None)

    def test_attach_existing_claude_session_accepts_discovered_conversation(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            store = server.SessionStore(base)
            sid = "019c0000-0000-7000-8000-0000000000ab"
            claude_session = SessionInfo(
                session_id=sid,
                path=base / "claude-session.jsonl",
                cli_type="claude",
            )

            with mock.patch(
                "task_dashboard.adapters.claude_adapter.ClaudeAdapter.scan_sessions",
                return_value=[claude_session],
            ):
                result = create_session_response(
                    payload={
                        "project_id": "task_dashboard",
                        "channel_name": "子级07",
                        "session_id": sid,
                        "mode": "attach_existing",
                        "cli_type": "claude",
                        "alias": "Claude 接入会话",
                    },
                    session_store=store,
                    environment_name="refactor",
                    worktree_root=str(base / "worktree-refactor"),
                    create_cli_session=lambda **_kwargs: {"ok": True},
                    resolve_project_workdir=lambda _pid: base,
                    detect_git_branch=lambda _root: "feature/claude-attach",
                    build_session_seed_prompt=lambda **_kwargs: "seed",
                    decorate_session_display_fields=lambda row: row,
                    apply_session_work_context=lambda row, **_kwargs: row,
                    load_project_execution_context=lambda *_args, **_kwargs: {},
                    project_exists=lambda _pid: True,
                    channel_exists=lambda _pid, _channel: True,
                )

            session = result.get("session") or {}
            self.assertTrue(bool(result.get("attached")))
            self.assertEqual(session.get("id"), sid)
            self.assertEqual(session.get("cli_type"), "claude")

    def test_attach_existing_session_preserves_codebuddy_permission_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            workdir = base / "wt"
            workdir.mkdir(parents=True, exist_ok=True)
            store = server.SessionStore(base)
            sid = "019c0000-0000-7000-8000-0000000000cc"
            store.create_session(
                "task_dashboard",
                "子级07",
                cli_type="codebuddy",
                session_id=sid,
                alias="已有 CodeBuddy 会话",
                codebuddy_permission_mode="bypassPermissions",
                environment="refactor",
                worktree_root=str(workdir),
                workdir=str(workdir),
                branch="feature/codebuddy-permission",
            )

            result = create_session_response(
                payload={
                    "project_id": "task_dashboard",
                    "channel_name": "子级07",
                    "session_id": sid,
                    "mode": "attach_existing",
                    "cli_type": "codebuddy",
                    "environment": "refactor",
                    "worktree_root": str(workdir),
                    "workdir": str(workdir),
                    "branch": "feature/codebuddy-permission",
                },
                session_store=store,
                environment_name="refactor",
                worktree_root=str(workdir),
                create_cli_session=lambda **_kwargs: {"ok": True},
                resolve_project_workdir=lambda _pid: workdir,
                detect_git_branch=lambda _root: "feature/fallback",
                build_session_seed_prompt=lambda **_kwargs: "seed",
                decorate_session_display_fields=lambda row: row,
                apply_session_work_context=lambda row, **_kwargs: row,
                load_project_execution_context=lambda *_args, **_kwargs: {"profile": "project_privileged_full"},
                project_exists=lambda _pid: True,
                channel_exists=lambda _pid, _channel: True,
            )

            self.assertTrue(bool(result.get("attached")))
            self.assertFalse(bool(result.get("imported")))
            session = result.get("session") or {}
            self.assertEqual(session.get("id"), sid)
            self.assertEqual(session.get("codebuddy_permission_mode"), "bypassPermissions")
            stored = store.get_session(sid) or {}
            self.assertEqual(stored.get("codebuddy_permission_mode"), "bypassPermissions")

    def test_create_session_without_worktree_override_uses_project_execution_context(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            server_root = base / "task-dashboard"
            project_root = base / "ynwxfx"
            server_root.mkdir(parents=True, exist_ok=True)
            project_root.mkdir(parents=True, exist_ok=True)
            create_calls: list[dict[str, object]] = []

            def _load_project_execution_context(*_args, **_kwargs):
                return {
                    "project_id": "ynwxfx",
                    "profile": "project_privileged_full",
                    "environment": "stable",
                    "worktree_root": str(project_root),
                    "workdir": str(project_root),
                    "branch": "main",
                    "context_source": "project",
                }

            def _apply_row_context(row, **kwargs):
                return apply_session_work_context(
                    row,
                    resolve_project_workdir=lambda _pid: project_root,
                    load_project_execution_context=_load_project_execution_context,
                    **kwargs,
                )

            def _fake_create_cli_session(**kwargs):
                create_calls.append(kwargs)
                return {
                    "ok": True,
                    "sessionId": "019c0000-0000-7000-8000-0000000000bb",
                    "sessionPath": "/tmp/gemini-session.json",
                    "workdir": str(kwargs.get("workdir") or ""),
                }

            store = server.SessionStore(base)
            result = create_session_response(
                payload={
                    "project_id": "ynwxfx",
                    "channel_name": "研发04-Demo展示",
                    "cli_type": "gemini",
                    "alias": "gemini-视觉开发",
                    "reuse_strategy": "create_new",
                },
                session_store=store,
                environment_name="stable",
                worktree_root=str(server_root),
                create_cli_session=_fake_create_cli_session,
                resolve_project_workdir=lambda _pid: project_root,
                detect_git_branch=lambda _root: "server-branch",
                build_session_seed_prompt=lambda **_kwargs: "seed",
                decorate_session_display_fields=lambda row: row,
                apply_session_work_context=_apply_row_context,
                load_project_execution_context=_load_project_execution_context,
                project_exists=lambda pid: pid == "ynwxfx",
                channel_exists=lambda pid, channel: pid == "ynwxfx" and channel == "研发04-Demo展示",
            )

            self.assertTrue(bool(result.get("created")))
            self.assertEqual(len(create_calls), 1)
            self.assertEqual(Path(create_calls[0].get("workdir")).resolve(), project_root.resolve())
            session = result.get("session") or {}
            self.assertEqual(session.get("cli_type"), "gemini")
            self.assertEqual(Path(session.get("worktree_root") or "").resolve(), project_root.resolve())
            self.assertEqual(Path(session.get("workdir") or "").resolve(), project_root.resolve())
            self.assertEqual(session.get("context_binding_state"), "bound")
            self.assertFalse(bool(((session.get("project_execution_context") or {}).get("override") or {}).get("applied")))

            stored = store.get_session("019c0000-0000-7000-8000-0000000000bb") or {}
            self.assertEqual(stored.get("worktree_root"), "")
            self.assertEqual(stored.get("workdir"), "")
            stored_context = stored.get("project_execution_context") or {}
            self.assertEqual((stored_context.get("source") or {}).get("worktree_root"), str(project_root))
            self.assertEqual((stored_context.get("target") or {}).get("workdir"), str(project_root))
            self.assertFalse(bool((stored_context.get("override") or {}).get("applied")))

    def test_post_api_sessions_respects_context_and_role(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            worktree = base / "sandbox" / "task-dashboard-refactor"
            worktree.mkdir(parents=True, exist_ok=True)
            resolved_worktree = str(worktree.resolve())
            httpd, session_store = self._start_server(base)
            t = threading.Thread(target=httpd.serve_forever, daemon=True)
            t.start()
            port = int(httpd.server_address[1])
            try:
                with mock.patch.object(
                    server,
                    "_load_dashboard_cfg_current",
                    return_value={
                        "projects": [
                            {
                                "id": "task_dashboard",
                                "channels": [{"name": "子级07"}],
                            }
                        ]
                    },
                ), mock.patch.object(
                    server,
                    "create_cli_session",
                    return_value={
                        "ok": True,
                        "sessionId": "019c0000-0000-7000-8000-000000000008",
                        "sessionPath": "/tmp/session",
                        "workdir": resolved_worktree,
                    },
                ):
                    req = url_request.Request(
                        f"http://127.0.0.1:{port}/api/sessions",
                        data=json.dumps(
                            {
                                "project_id": "task_dashboard",
                                "channel_name": "子级07",
                                "cli_type": "codex",
                                "alias": "HTTP 创建会话",
                                "agentName": "HTTP 创建会话",
                                "model": "gpt-5.3-codex",
                                "reasoning_effort": "medium",
                                "environment": "refactor",
                                "worktree_root": str(worktree),
                                "workdir": str(worktree),
                                "branch": "refactor/session-v2",
                                "session_role": "child",
                                "purpose": "创建验证",
                                "reuse_strategy": "create_new",
                                "set_as_primary": False,
                            }
                        ).encode("utf-8"),
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    with url_request.urlopen(req, timeout=3) as resp:
                        self.assertEqual(resp.status, 200)
                        body = json.loads(resp.read().decode("utf-8"))
                session = (body.get("session") or {})
                self.assertEqual(session.get("id"), "019c0000-0000-7000-8000-000000000008")
                self.assertEqual(session.get("environment"), "refactor")
                self.assertEqual(os.path.realpath(session.get("worktree_root") or ""), resolved_worktree)
                self.assertEqual(os.path.realpath(session.get("workdir") or ""), resolved_worktree)
                self.assertEqual(session.get("branch"), "refactor/session-v2")
                self.assertEqual(session.get("session_role"), "child")
                self.assertEqual(session.get("purpose"), "创建验证")
                self.assertEqual(session.get("reuse_strategy"), "create_new")
                self.assertEqual(session.get("schema_version"), "session.create.v2")
                self.assertEqual(session.get("created_via"), "api.create_session_v2")
                self.assertEqual(session.get("context_binding_state"), "override")
                self.assertFalse(bool(session.get("is_primary")))

                stored = session_store.get_session("019c0000-0000-7000-8000-000000000008") or {}
                self.assertEqual(stored.get("purpose"), "创建验证")
                self.assertEqual(stored.get("session_role"), "child")
            finally:
                httpd.shutdown()
                t.join(timeout=2)
                httpd.server_close()

    def test_post_api_sessions_returns_409_for_alias_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            httpd, session_store = self._start_server(base)
            session_store.create_session(
                "task_dashboard",
                "子级07",
                session_id="019c0000-0000-7000-8000-000000000021",
                alias="冲突 Agent",
            )
            t = threading.Thread(target=httpd.serve_forever, daemon=True)
            t.start()
            port = int(httpd.server_address[1])
            try:
                with mock.patch.object(
                    server,
                    "_load_dashboard_cfg_current",
                    return_value={
                        "projects": [
                            {
                                "id": "task_dashboard",
                                "channels": [{"name": "子级07"}, {"name": "子级08"}],
                            }
                        ]
                    },
                ):
                    req = url_request.Request(
                        f"http://127.0.0.1:{port}/api/sessions",
                        data=json.dumps(
                            {
                                "project_id": "task_dashboard",
                                "channel_name": "子级08",
                                "cli_type": "codex",
                                "alias": "冲突 Agent",
                            }
                        ).encode("utf-8"),
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    with self.assertRaises(HTTPError) as ctx:
                        url_request.urlopen(req, timeout=3)
                    self.assertEqual(ctx.exception.code, 409)
                    body = json.loads(ctx.exception.read().decode("utf-8"))
                    self.assertEqual(body.get("error_code"), "alias_conflict")
                    self.assertEqual((body.get("conflict") or {}).get("session_id"), "019c0000-0000-7000-8000-000000000021")
            finally:
                httpd.shutdown()
                t.join(timeout=2)
                httpd.server_close()

    def test_put_api_sessions_returns_409_for_alias_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            httpd, session_store = self._start_server(base)
            session_store.create_session(
                "task_dashboard",
                "子级07",
                session_id="019c0000-0000-7000-8000-000000000031",
                alias="已有 Agent",
                environment="refactor",
            )
            session_store.create_session(
                "task_dashboard",
                "子级08",
                session_id="019c0000-0000-7000-8000-000000000032",
                alias="待改名 Agent",
                environment="refactor",
            )
            t = threading.Thread(target=httpd.serve_forever, daemon=True)
            t.start()
            port = int(httpd.server_address[1])
            try:
                req = url_request.Request(
                    f"http://127.0.0.1:{port}/api/sessions/019c0000-0000-7000-8000-000000000032",
                    data=json.dumps({"alias": "已有 Agent"}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="PUT",
                )
                with self.assertRaises(HTTPError) as ctx:
                    url_request.urlopen(req, timeout=3)
                self.assertEqual(ctx.exception.code, 409)
                body = json.loads(ctx.exception.read().decode("utf-8"))
                self.assertEqual(body.get("error_code"), "alias_conflict")
                self.assertEqual((body.get("conflict") or {}).get("session_id"), "019c0000-0000-7000-8000-000000000031")
            finally:
                httpd.shutdown()
                t.join(timeout=2)
                httpd.server_close()

    def test_put_api_sessions_switches_and_clears_codex_reasoning_override(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            httpd, session_store = self._start_server(base)
            session_id = "019c0000-0000-7000-8000-000000000041"
            session_store.create_session(
                "task_dashboard",
                "子级03",
                session_id=session_id,
                alias="Codex 实时切换",
                cli_type="codex",
                model="gpt-5.4",
                reasoning_effort="medium",
                environment="refactor",
            )
            t = threading.Thread(target=httpd.serve_forever, daemon=True)
            t.start()
            port = int(httpd.server_address[1])
            try:
                switch_req = url_request.Request(
                    f"http://127.0.0.1:{port}/api/sessions/{session_id}",
                    data=json.dumps({"reasoningEffort": "xhigh"}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="PUT",
                )
                with url_request.urlopen(switch_req, timeout=3) as resp:
                    self.assertEqual(resp.status, 200)
                switched = session_store.get_session(session_id) or {}
                self.assertEqual(switched.get("reasoning_effort"), "extra_high")
                self.assertEqual(switched.get("model"), "gpt-5.4")

                clear_req = url_request.Request(
                    f"http://127.0.0.1:{port}/api/sessions/{session_id}",
                    data=json.dumps({"model": "", "reasoning_effort": ""}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="PUT",
                )
                with url_request.urlopen(clear_req, timeout=3) as resp:
                    self.assertEqual(resp.status, 200)
                cleared = session_store.get_session(session_id) or {}
                self.assertEqual(cleared.get("model"), "")
                self.assertEqual(cleared.get("reasoning_effort"), "")
            finally:
                httpd.shutdown()
                t.join(timeout=2)
                httpd.server_close()

    def test_put_api_sessions_echoes_canonical_claude_opus5_model(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            httpd, session_store = self._start_server(base)
            session_id = "019c0000-0000-7000-8000-000000000042"
            session_store.create_session(
                "task_dashboard",
                "子级02",
                session_id=session_id,
                alias="Claude 模型切换",
                cli_type="claude",
                model="claude-fable-5",
                environment="refactor",
            )
            t = threading.Thread(target=httpd.serve_forever, daemon=True)
            t.start()
            port = int(httpd.server_address[1])
            try:
                for requested_model in ("claude-opus-4-8", "not-a-real-model"):
                    req = url_request.Request(
                        f"http://127.0.0.1:{port}/api/sessions/{session_id}",
                        data=json.dumps({"model": requested_model}).encode("utf-8"),
                        headers={"Content-Type": "application/json"},
                        method="PUT",
                    )
                    with url_request.urlopen(req, timeout=3) as resp:
                        self.assertEqual(resp.status, 200)
                        body = json.loads(resp.read().decode("utf-8"))
                    self.assertEqual((body.get("session") or {}).get("model"), "claude-opus-5")
                    self.assertEqual((session_store.get_session(session_id) or {}).get("model"), "claude-opus-5")
            finally:
                httpd.shutdown()
                t.join(timeout=2)
                httpd.server_close()

    def test_legacy_session_new_endpoint_is_retired(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            httpd, _session_store = self._start_server(base)
            t = threading.Thread(target=httpd.serve_forever, daemon=True)
            t.start()
            port = int(httpd.server_address[1])
            try:
                req = url_request.Request(
                    f"http://127.0.0.1:{port}/api/codex/session/new",
                    data=json.dumps(
                        {
                            "projectId": "task_dashboard",
                            "channelName": "子级07",
                        }
                    ).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with self.assertRaises(HTTPError) as ctx:
                    url_request.urlopen(req, timeout=3)
                self.assertEqual(ctx.exception.code, 410)
                body = json.loads(ctx.exception.read().decode("utf-8"))
                self.assertEqual(body.get("error_code"), "legacy_session_new_retired")
                self.assertEqual(body.get("replacement"), "/api/sessions")
            finally:
                httpd.shutdown()
                t.join(timeout=2)
                httpd.server_close()

    def test_create_session_response_passes_execution_profile_to_cli_session(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            create_calls: list[dict[str, object]] = []

            def _fake_create_cli_session(**kwargs):
                create_calls.append(kwargs)
                return {
                    "ok": True,
                    "sessionId": "019c0000-0000-7000-8000-0000000000aa",
                    "sessionPath": "/tmp/session",
                    "workdir": str(base),
                }

            result = create_session_response(
                payload={
                    "project_id": "task_dashboard",
                    "channel_name": "子级07",
                    "cli_type": "codex",
                    "alias": "执行 profile 会话",
                    "reuse_strategy": "create_new",
                },
                session_store=server.SessionStore(base),
                environment_name="stable",
                worktree_root=str(base),
                create_cli_session=_fake_create_cli_session,
                resolve_project_workdir=lambda _pid: base,
                detect_git_branch=lambda _root: "main",
                build_session_seed_prompt=lambda **_kwargs: "seed",
                decorate_session_display_fields=lambda row: row,
                apply_session_work_context=lambda row, **_kwargs: {
                    **row,
                    "environment": "stable",
                    "worktree_root": str(base),
                    "workdir": str(base),
                    "branch": "main",
                    "project_execution_context": {},
                },
                load_project_execution_context=lambda *_args, **_kwargs: {"profile": "project_privileged_full"},
                project_exists=lambda _pid: True,
                channel_exists=lambda _pid, _channel: True,
            )

            self.assertTrue(bool(result.get("created")))
            self.assertEqual(len(create_calls), 1)
            self.assertEqual(create_calls[0].get("execution_profile"), "project_privileged_full")

    def test_post_api_sessions_reuse_active_avoids_cli_spawn(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            worktree = base / "sandbox" / "task-dashboard-refactor"
            worktree.mkdir(parents=True, exist_ok=True)
            resolved_worktree = str(worktree.resolve())
            httpd, session_store = self._start_server(base)
            session_store.create_session(
                "task_dashboard",
                "子级07",
                cli_type="codex",
                session_id="019c0000-0000-7000-8000-000000000009",
                alias="已有会话",
                environment="refactor",
                worktree_root=resolved_worktree,
                workdir=resolved_worktree,
                branch="refactor/existing",
                session_role="primary",
                purpose="旧用途",
                is_primary=True,
            )
            t = threading.Thread(target=httpd.serve_forever, daemon=True)
            t.start()
            port = int(httpd.server_address[1])
            try:
                with mock.patch.object(
                    server,
                    "_load_dashboard_cfg_current",
                    return_value={
                        "projects": [
                            {
                                "id": "task_dashboard",
                                "channels": [{"name": "子级07"}],
                            }
                        ]
                    },
                ), mock.patch.object(
                    server,
                    "create_cli_session",
                    side_effect=AssertionError("reuse_active 不应创建新 CLI 会话"),
                ):
                    req = url_request.Request(
                        f"http://127.0.0.1:{port}/api/sessions",
                        data=json.dumps(
                            {
                                "project_id": "task_dashboard",
                                "channel_name": "子级07",
                                "cli_type": "codex",
                                "environment": "refactor",
                                "worktree_root": str(worktree),
                                "workdir": str(worktree),
                                "branch": "refactor/existing",
                                "session_role": "child",
                                "purpose": "复用用途",
                                "reuse_strategy": "reuse_active",
                            }
                        ).encode("utf-8"),
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    with url_request.urlopen(req, timeout=3) as resp:
                        body = json.loads(resp.read().decode("utf-8"))
                session = body.get("session") or {}
                self.assertTrue(bool(body.get("reused")))
                self.assertFalse(bool(body.get("created")))
                self.assertEqual(session.get("id"), "019c0000-0000-7000-8000-000000000009")
                self.assertEqual(session.get("purpose"), "复用用途")
            finally:
                httpd.shutdown()
                t.join(timeout=2)
                httpd.server_close()


if __name__ == "__main__":
    unittest.main()
