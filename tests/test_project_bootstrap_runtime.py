import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import server

from task_dashboard.runtime.project_admin import (
    bootstrap_project_response,
    build_project_bootstrap_completion_gate,
    build_project_bootstrap_onboarding_gate,
)


def _apply_session_work_context(row, **kwargs):
    out = dict(row or {})
    environment = str(out.get("environment") or kwargs.get("environment_name") or "stable")
    worktree_root = str(out.get("worktree_root") or kwargs.get("worktree_root") or "")
    workdir = str(out.get("workdir") or worktree_root)
    branch = str(out.get("branch") or "main")
    out.update(
        {
            "environment": environment,
            "worktree_root": worktree_root,
            "workdir": workdir,
            "branch": branch,
            "project_execution_context": {
                "target": {
                    "environment": environment,
                    "worktree_root": worktree_root,
                    "workdir": workdir,
                    "branch": branch,
                },
                "override": {"applied": False, "fields": []},
            },
        }
    )
    return out


class ProjectBootstrapRuntimeTests(unittest.TestCase):
    def test_bootstrap_creates_config_scaffold_and_session_store(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo_root = Path(td)
            config_path = repo_root / "config.toml"
            config_path.write_text('version = 1\n\n[runtime]\nmax_concurrency = 4\n', encoding="utf-8")
            session_store = server.SessionStore(repo_root / ".runtime" / "stable")

            code, payload = bootstrap_project_response(
                body={
                    "project_id": "demo_project",
                    "project_name": "演示项目",
                    "project_root_rel": "projects/demo-project",
                    "task_root_rel": "projects/demo-project/任务规划",
                    "channels": [
                        {"name": "主体-总控", "desc": "总控通道", "cli_type": "codex"},
                    ],
                    "bootstrap": {
                        "create_primary_sessions": False,
                        "generate_registry": False,
                        "run_dedup": False,
                        "run_visibility_check": False,
                    },
                },
                config_path=config_path,
                repo_root=repo_root,
                session_store=session_store,
                create_cli_session=lambda **kwargs: {"ok": True, "sessionId": "unused", "sessionPath": "", "workdir": str(repo_root)},
                detect_git_branch=lambda _root: "main",
                build_session_seed_prompt=lambda **_kwargs: "seed",
                decorate_session_display_fields=lambda row: row,
                apply_session_work_context=_apply_session_work_context,
                read_task_dashboard_generated_at=lambda: "",
                rebuild_dashboard_static=lambda timeout_s: {"ok": True, "timeout_s": timeout_s},
                clear_dashboard_cfg_cache=lambda: None,
            )

            self.assertEqual(code, 200)
            self.assertTrue(payload["ok"])
            self.assertFalse(payload["reused"])
            self.assertEqual(payload["project_id"], "demo_project")
            project_root = repo_root / "projects" / "demo-project"
            channel_root = project_root / "任务规划" / "主体-总控"
            self.assertTrue((project_root / "README.md").exists())
            self.assertTrue((project_root / "AGENTS.md").exists())
            self.assertTrue((channel_root / "README.md").exists())
            self.assertTrue((channel_root / "AGENTS.md").exists())
            self.assertEqual(payload["project_agents_md"]["path"], str((project_root / "AGENTS.md").resolve()))
            self.assertEqual(len(payload["channel_agents_md"]), 1)
            self.assertEqual(payload["channel_agents_md"][0]["channel_name"], "主体-总控")
            self.assertTrue(payload["creation_ok"])
            self.assertFalse(payload["collaboration_ready"])
            self.assertEqual(payload["completion_state"], "blocked")
            missing_codes = {item.get("code") for item in payload["completion_gate"]["missing_items"]}
            self.assertIn("ccr_generated", missing_codes)
            self.assertFalse(payload["onboarding_ready"])
            self.assertEqual(payload["onboarding_state"], "blocked")
            onboarding_missing_codes = {item.get("code") for item in payload["onboarding_gate"]["missing_items"]}
            self.assertIn("p0_completion_ready", onboarding_missing_codes)
            self.assertIn("--project demo_project", (project_root / "AGENTS.md").read_text(encoding="utf-8"))
            self.assertIn("主体-总控", (channel_root / "AGENTS.md").read_text(encoding="utf-8"))
            session_store_path = repo_root / ".runtime" / "stable" / ".sessions" / "demo_project.json"
            self.assertTrue(session_store_path.exists())
            session_data = json.loads(session_store_path.read_text(encoding="utf-8"))
            self.assertEqual(session_data["project_id"], "demo_project")
            self.assertEqual(session_data["sessions"], [])
            updated_config = config_path.read_text(encoding="utf-8")
            self.assertIn('[[projects]]', updated_config)
            self.assertIn('id = "demo_project"', updated_config)
            self.assertIn('cli_type = "codex"', updated_config)

    def test_bootstrap_creates_codebuddy_static_instruction_mirror_for_first_channel(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo_root = Path(td)
            config_path = repo_root / "config.toml"
            config_path.write_text('version = 1\n', encoding="utf-8")
            session_store = server.SessionStore(repo_root / ".runtime" / "stable")

            code, payload = bootstrap_project_response(
                body={
                    "project_id": "demo_project",
                    "project_name": "演示项目",
                    "project_root_rel": "projects/demo-project",
                    "task_root_rel": "projects/demo-project/任务规划",
                    "channels": [
                        {"name": "辅助01-项目管理", "desc": "项目管理", "cli_type": "codebuddy"},
                        {"name": "业务01-规划", "desc": "规划通道", "cli_type": "codex"},
                    ],
                    "bootstrap": {
                        "create_primary_sessions": False,
                        "generate_registry": False,
                        "run_dedup": False,
                        "run_visibility_check": False,
                    },
                },
                config_path=config_path,
                repo_root=repo_root,
                session_store=session_store,
                create_cli_session=lambda **kwargs: {"ok": True, "sessionId": "unused", "sessionPath": "", "workdir": str(repo_root)},
                detect_git_branch=lambda _root: "main",
                build_session_seed_prompt=lambda **_kwargs: "seed",
                decorate_session_display_fields=lambda row: row,
                apply_session_work_context=_apply_session_work_context,
                read_task_dashboard_generated_at=lambda: "",
                rebuild_dashboard_static=lambda timeout_s: {"ok": True, "timeout_s": timeout_s},
                clear_dashboard_cfg_cache=lambda: None,
            )

            self.assertEqual(code, 200)
            self.assertTrue(payload["ok"])
            channel_root = repo_root / "projects" / "demo-project" / "任务规划" / "辅助01-项目管理"
            self.assertTrue((channel_root / "AGENTS.md").exists())
            self.assertTrue((channel_root / "CODEBUDDY.md").exists())
            self.assertEqual(len(payload["channel_agents_md"]), 1)
            static_files = payload["channel_agents_md"][0].get("static_instruction_files") or {}
            mirror = (static_files.get("mirrors") or [])[0]
            self.assertEqual(mirror.get("fileName"), "CODEBUDDY.md")
            self.assertEqual(mirror.get("syncStatus"), "synced")

    def test_bootstrap_rejects_channel_name_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo_root = Path(td)
            config_path = repo_root / "config.toml"
            config_path.write_text('version = 1\n', encoding="utf-8")
            session_store = server.SessionStore(repo_root / ".runtime" / "stable")

            code, payload = bootstrap_project_response(
                body={
                    "project_id": "demo_project",
                    "project_name": "演示项目",
                    "project_root_rel": "projects/demo-project",
                    "task_root_rel": "projects/demo-project/任务规划",
                    "channels": [{"name": "../escape", "desc": "越界", "cli_type": "codex"}],
                    "bootstrap": {
                        "create_primary_sessions": False,
                        "generate_registry": False,
                        "run_dedup": False,
                        "run_visibility_check": False,
                    },
                },
                config_path=config_path,
                repo_root=repo_root,
                session_store=session_store,
                create_cli_session=lambda **kwargs: {"ok": True, "sessionId": "unused", "sessionPath": "", "workdir": str(repo_root)},
                detect_git_branch=lambda _root: "main",
                build_session_seed_prompt=lambda **_kwargs: "seed",
                decorate_session_display_fields=lambda row: row,
                apply_session_work_context=_apply_session_work_context,
                read_task_dashboard_generated_at=lambda: "",
                rebuild_dashboard_static=lambda timeout_s: {"ok": True, "timeout_s": timeout_s},
                clear_dashboard_cfg_cache=lambda: None,
            )

            self.assertEqual(code, 400)
            self.assertEqual(payload["resume_from_step"], "validate")
            self.assertIn("invalid channel name path segment", payload["error"])
            self.assertFalse((repo_root / "projects" / "escape").exists())

    def test_bootstrap_is_idempotent_when_request_matches(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo_root = Path(td)
            config_path = repo_root / "config.toml"
            config_path.write_text('version = 1\n', encoding="utf-8")
            session_store = server.SessionStore(repo_root / ".runtime" / "stable")
            body = {
                "project_id": "demo_project",
                "project_name": "演示项目",
                "project_root_rel": "projects/demo-project",
                "task_root_rel": "projects/demo-project/任务规划",
                "channels": [{"name": "主体-总控", "desc": "总控通道", "cli_type": "codex"}],
                "bootstrap": {
                    "create_primary_sessions": False,
                    "generate_registry": False,
                    "run_dedup": False,
                    "run_visibility_check": False,
                },
            }

            first_code, first_payload = bootstrap_project_response(
                body=body,
                config_path=config_path,
                repo_root=repo_root,
                session_store=session_store,
                create_cli_session=lambda **kwargs: {"ok": True, "sessionId": "unused", "sessionPath": "", "workdir": str(repo_root)},
                detect_git_branch=lambda _root: "main",
                build_session_seed_prompt=lambda **_kwargs: "seed",
                decorate_session_display_fields=lambda row: row,
                apply_session_work_context=_apply_session_work_context,
                read_task_dashboard_generated_at=lambda: "",
                rebuild_dashboard_static=lambda timeout_s: {"ok": True, "timeout_s": timeout_s},
                clear_dashboard_cfg_cache=lambda: None,
            )
            second_code, second_payload = bootstrap_project_response(
                body=body,
                config_path=config_path,
                repo_root=repo_root,
                session_store=session_store,
                create_cli_session=lambda **kwargs: {"ok": True, "sessionId": "unused", "sessionPath": "", "workdir": str(repo_root)},
                detect_git_branch=lambda _root: "main",
                build_session_seed_prompt=lambda **_kwargs: "seed",
                decorate_session_display_fields=lambda row: row,
                apply_session_work_context=_apply_session_work_context,
                read_task_dashboard_generated_at=lambda: "",
                rebuild_dashboard_static=lambda timeout_s: {"ok": True, "timeout_s": timeout_s},
                clear_dashboard_cfg_cache=lambda: None,
            )

            self.assertEqual(first_code, 200)
            self.assertTrue(first_payload["ok"])
            self.assertEqual(second_code, 200)
            self.assertTrue(second_payload["ok"])
            self.assertTrue(second_payload["reused"])

    def test_bootstrap_uses_active_session_store_for_generated_project(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo_root = Path(td) / "workspace"
            repo_root.mkdir(parents=True, exist_ok=True)
            active_runtime_root = Path(td) / "active-runtime"
            config_path = repo_root / "config.toml"
            config_path.write_text('version = 1\n', encoding="utf-8")
            session_store = server.SessionStore(active_runtime_root)
            created_sid = "019dc54c-9ebd-7ca2-9694-4e04671b60be"
            body = {
                "project_id": "demo_project",
                "project_name": "演示项目",
                "project_root_rel": "projects/demo-project",
                "task_root_rel": "projects/demo-project/任务规划",
                "channels": [{"name": "主体-总控", "desc": "总控通道", "cli_type": "codex"}],
                "bootstrap": {
                    "create_primary_sessions": True,
                    "primary_channel_names": ["主体-总控"],
                    "generate_registry": False,
                    "run_dedup": False,
                    "run_visibility_check": False,
                },
            }

            code, payload = bootstrap_project_response(
                body=body,
                config_path=config_path,
                repo_root=repo_root,
                session_store=session_store,
                create_cli_session=lambda **kwargs: {
                    "ok": True,
                    "sessionId": created_sid,
                    "sessionPath": str(repo_root / "sessions" / "rollout.jsonl"),
                    "workdir": str(repo_root / "projects" / "demo-project"),
                    "cliType": "codex",
                },
                detect_git_branch=lambda _root: "main",
                build_session_seed_prompt=lambda **_kwargs: "seed",
                decorate_session_display_fields=lambda row: row,
                apply_session_work_context=_apply_session_work_context,
                read_task_dashboard_generated_at=lambda: "",
                rebuild_dashboard_static=lambda timeout_s: {"ok": True, "timeout_s": timeout_s},
                clear_dashboard_cfg_cache=lambda: None,
            )

            self.assertEqual(code, 200)
            self.assertTrue(payload["ok"])
            active_session_path = session_store.sessions_dir / "demo_project.json"
            default_session_path = repo_root / ".runtime" / "stable" / ".sessions" / "demo_project.json"
            self.assertTrue(active_session_path.exists())
            self.assertFalse(default_session_path.exists())
            self.assertEqual(payload["session_store_path"], str(active_session_path.resolve()))
            updated_config = config_path.read_text(encoding="utf-8")
            self.assertIn(f'sessions_root = "{session_store.sessions_dir.resolve()}"', updated_config)
            stored = session_store.list_sessions("demo_project", "主体-总控", include_deleted=False)
            self.assertEqual(len(stored), 1)
            self.assertEqual(stored[0]["id"], created_sid)
            self.assertEqual(stored[0]["alias"], "演示项目-主体-总控")
            self.assertEqual(stored[0]["purpose"], "演示项目 / 主体-总控 primary 协作会话")
            self.assertEqual(payload["created_sessions"][0]["alias"], "演示项目-主体-总控")
            self.assertEqual(payload["created_sessions"][0]["purpose"], "演示项目 / 主体-总控 primary 协作会话")
            self.assertEqual(payload["completion_state"], "blocked")
            self.assertEqual(payload["onboarding_state"], "blocked")

    def test_bootstrap_recovers_timeout_created_primary_session(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo_root = Path(td)
            config_path = repo_root / "config.toml"
            config_path.write_text('version = 1\n', encoding="utf-8")
            session_store = server.SessionStore(repo_root / ".runtime" / "stable")
            recovered_sid = "019dc50f-2ec6-77e0-b0c5-491e62c31eb7"
            body = {
                "project_id": "demo_project",
                "project_name": "演示项目",
                "project_root_rel": "projects/demo-project",
                "task_root_rel": "projects/demo-project/任务规划",
                "channels": [{"name": "主体-总控", "desc": "总控通道", "cli_type": "codex"}],
                "bootstrap": {
                    "create_primary_sessions": True,
                    "primary_channel_names": ["主体-总控"],
                    "generate_registry": False,
                    "run_dedup": False,
                    "run_visibility_check": False,
                },
            }

            code, payload = bootstrap_project_response(
                body=body,
                config_path=config_path,
                repo_root=repo_root,
                session_store=session_store,
                create_cli_session=lambda **kwargs: {
                    "ok": False,
                    "error": "timeout",
                    "sessionId": recovered_sid,
                    "sessionPath": str(repo_root / "sessions" / "rollout.jsonl"),
                    "workdir": str(repo_root / "projects" / "demo-project"),
                    "cliType": "codex",
                },
                detect_git_branch=lambda _root: "main",
                build_session_seed_prompt=lambda **_kwargs: "seed",
                decorate_session_display_fields=lambda row: row,
                apply_session_work_context=_apply_session_work_context,
                read_task_dashboard_generated_at=lambda: "",
                rebuild_dashboard_static=lambda timeout_s: {"ok": True, "timeout_s": timeout_s},
                clear_dashboard_cfg_cache=lambda: None,
            )

            self.assertEqual(code, 200)
            self.assertTrue(payload["ok"])
            created_sessions = payload["created_sessions"]
            self.assertEqual(len(created_sessions), 1)
            self.assertTrue(created_sessions[0]["timeout_recovered"])
            self.assertEqual(created_sessions[0]["session_id"], recovered_sid)
            stored = session_store.list_sessions("demo_project", "主体-总控", include_deleted=False)
            self.assertEqual(len(stored), 1)
            self.assertEqual(stored[0]["id"], recovered_sid)
            self.assertEqual(stored[0]["alias"], "演示项目-主体-总控")
            self.assertEqual(stored[0]["purpose"], "演示项目 / 主体-总控 primary 协作会话")

    def test_bootstrap_completion_gate_reports_missing_items(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo_root = Path(td)
            project_root = repo_root / "projects" / "demo-project"
            task_root = project_root / "任务规划"
            registry_path = project_root / "registry" / "collab-registry.v1.json"

            class DummyStore:
                def list_sessions(self, *_args, **_kwargs):
                    return [
                        {
                            "channel_name": "主体-总控",
                            "is_primary": True,
                            "alias": "",
                            "purpose": "总控协作",
                        }
                    ]

            gate = build_project_bootstrap_completion_gate(
                spec={
                    "project_id": "demo_project",
                    "project_root": str(project_root),
                    "task_root": str(task_root),
                    "channels": [{"name": "主体-总控"}],
                    "bootstrap": {"create_primary_sessions": True, "primary_channel_names": ["主体-总控"]},
                    "registry_paths": [str(registry_path)],
                },
                session_store=DummyStore(),
                created_sessions=[],
                verify_result={"registry": {"skipped": False}},
            )

            self.assertFalse(gate["ok"])
            self.assertEqual(gate["state"], "blocked")
            missing_codes = {item.get("code") for item in gate["missing_items"]}
            self.assertIn("project_agents_md", missing_codes)
            self.assertIn("first_channel_agents_md", missing_codes)
            self.assertIn("primary_identity", missing_codes)
            self.assertIn("ccr_generated", missing_codes)

    def test_bootstrap_completion_gate_ready_when_agents_primary_and_registry_exist(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo_root = Path(td)
            (repo_root / "scripts").mkdir(parents=True, exist_ok=True)
            (repo_root / "scripts" / "bootstrap_project_collab.py").write_text(
                "#!/usr/bin/env python3\nprint('ok')\n",
                encoding="utf-8",
            )
            config_path = repo_root / "config.toml"
            config_path.write_text('version = 1\n', encoding="utf-8")
            session_store = server.SessionStore(repo_root / ".runtime" / "stable")
            created_sid = "019dc54c-9ebd-7ca2-9694-4e04671b60be"

            def fake_registry_run(args, **_kwargs):
                for flag in ("--output", "--view-output", "--html-output"):
                    path = Path(args[args.index(flag) + 1])
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text("{}\n" if path.suffix == ".json" else "ok\n", encoding="utf-8")
                return mock.Mock(returncode=0, stdout="ok", stderr="")

            with mock.patch("task_dashboard.runtime.project_admin.subprocess.run", side_effect=fake_registry_run):
                code, payload = bootstrap_project_response(
                    body={
                        "project_id": "demo_project",
                        "project_name": "演示项目",
                        "project_root_rel": "projects/demo-project",
                        "task_root_rel": "projects/demo-project/任务规划",
                        "channels": [
                            {
                                "name": "主体-总控",
                                "desc": "总控通道",
                                "cli_type": "codex",
                                "primary_alias": "演示总控",
                                "primary_purpose": "负责演示项目总控协作",
                            }
                        ],
                        "bootstrap": {
                            "create_primary_sessions": True,
                            "primary_channel_names": ["主体-总控"],
                            "generate_registry": True,
                            "run_dedup": False,
                            "run_visibility_check": False,
                        },
                    },
                    config_path=config_path,
                    repo_root=repo_root,
                    session_store=session_store,
                    create_cli_session=lambda **kwargs: {
                        "ok": True,
                        "sessionId": created_sid,
                        "sessionPath": str(repo_root / "sessions" / "rollout.jsonl"),
                        "workdir": str(repo_root / "projects" / "demo-project"),
                        "cliType": "codex",
                    },
                    detect_git_branch=lambda _root: "main",
                    build_session_seed_prompt=lambda **_kwargs: "seed",
                    decorate_session_display_fields=lambda row: row,
                    apply_session_work_context=_apply_session_work_context,
                    read_task_dashboard_generated_at=lambda: "",
                    rebuild_dashboard_static=lambda timeout_s: {"ok": True, "timeout_s": timeout_s},
                    clear_dashboard_cfg_cache=lambda: None,
                )

            self.assertEqual(code, 200)
            self.assertTrue(payload["ok"])
            self.assertTrue(payload["creation_ok"])
            self.assertTrue(payload["collaboration_ready"])
            self.assertEqual(payload["completion_state"], "ready")
            self.assertEqual(payload["completion_gate"]["missing_items"], [])
            self.assertFalse(payload["onboarding_ready"])
            self.assertEqual(payload["onboarding_state"], "pending")
            onboarding_missing_codes = {item.get("code") for item in payload["onboarding_gate"]["missing_items"]}
            self.assertIn("first_visible_message", onboarding_missing_codes)
            self.assertIn("init_training", onboarding_missing_codes)
            self.assertIn("delivery_evidence", onboarding_missing_codes)
            self.assertEqual(payload["created_sessions"][0]["alias"], "演示总控")
            self.assertEqual(payload["created_sessions"][0]["purpose"], "负责演示项目总控协作")

    def test_bootstrap_onboarding_gate_ready_with_verified_delivery_evidence(self) -> None:
        session_id = "019dc54c-9ebd-7ca2-9694-4e04671b60be"

        class DummyStore:
            def list_sessions(self, *_args, **_kwargs):
                return [
                    {
                        "id": session_id,
                        "channel_name": "主体-总控",
                        "is_primary": True,
                        "alias": "演示总控",
                        "purpose": "总控协作",
                    }
                ]

        gate = build_project_bootstrap_onboarding_gate(
            spec={
                "project_id": "demo_project",
                "channels": [{"name": "主体-总控"}],
                "bootstrap": {"primary_channel_names": ["主体-总控"]},
            },
            session_store=DummyStore(),
            created_sessions=[],
            completion_gate={"ok": True, "state": "ready", "collaboration_ready": True},
            verify_result={
                "onboarding": {
                    "first_visible_message": {
                        "announce_run_id": "20260618-170000-abcdef12",
                        "target_session_id": session_id,
                        "visible_in_channel_chat": True,
                    },
                    "init_training": {
                        "announce_run_id": "20260618-170010-abcdef34",
                        "target_session_id": session_id,
                        "visible_in_channel_chat": True,
                    },
                }
            },
        )

        self.assertTrue(gate["ok"])
        self.assertTrue(gate["onboarding_ready"])
        self.assertEqual(gate["state"], "ready")
        self.assertEqual(gate["missing_items"], [])

    def test_bootstrap_onboarding_gate_pending_when_delivery_target_mismatches(self) -> None:
        session_id = "019dc54c-9ebd-7ca2-9694-4e04671b60be"

        class DummyStore:
            def list_sessions(self, *_args, **_kwargs):
                return [
                    {
                        "id": session_id,
                        "channel_name": "主体-总控",
                        "is_primary": True,
                        "alias": "演示总控",
                        "purpose": "总控协作",
                    }
                ]

        gate = build_project_bootstrap_onboarding_gate(
            spec={
                "project_id": "demo_project",
                "channels": [{"name": "主体-总控"}],
                "bootstrap": {"primary_channel_names": ["主体-总控"]},
            },
            session_store=DummyStore(),
            created_sessions=[],
            completion_gate={"ok": True, "state": "ready", "collaboration_ready": True},
            verify_result={
                "onboarding": {
                    "first_visible_message": {
                        "announce_run_id": "20260618-170000-abcdef12",
                        "target_session_id": "019dc54c-9ebd-7ca2-9694-4e04671b60bf",
                        "visible_in_channel_chat": True,
                    },
                    "init_training": {
                        "announce_run_id": "20260618-170010-abcdef34",
                        "target_session_id": session_id,
                        "visible_in_channel_chat": True,
                    },
                }
            },
        )

        self.assertFalse(gate["ok"])
        self.assertFalse(gate["onboarding_ready"])
        self.assertEqual(gate["state"], "pending")
        first_visible = next(item for item in gate["missing_items"] if item.get("code") == "first_visible_message")
        self.assertIn("target_session_id_mismatch", first_visible["missing_fields"])

    def test_bootstrap_sends_onboarding_messages_for_isolated_test_project(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo_root = Path(td)
            (repo_root / "scripts").mkdir(parents=True, exist_ok=True)
            (repo_root / "scripts" / "bootstrap_project_collab.py").write_text(
                "#!/usr/bin/env python3\nprint('ok')\n",
                encoding="utf-8",
            )
            config_path = repo_root / "config.toml"
            config_path.write_text('version = 1\n', encoding="utf-8")
            session_store = server.SessionStore(repo_root / ".runtime" / "stable")
            created_sid = "019dc54c-9ebd-7ca2-9694-4e04671b60be"
            sent_payloads: list[dict] = []

            def fake_registry_run(args, **_kwargs):
                for flag in ("--output", "--view-output", "--html-output"):
                    path = Path(args[args.index(flag) + 1])
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text("{}\n" if path.suffix == ".json" else "ok\n", encoding="utf-8")
                return mock.Mock(returncode=0, stdout="ok", stderr="")

            def fake_sender(payload):
                sent_payloads.append(payload)
                run_suffix = "abc00100" if len(sent_payloads) == 1 else "abc00101"
                return {
                    "ok": True,
                    "run": {
                        "id": f"20260618-17000{len(sent_payloads)}-{run_suffix}",
                        "sessionId": payload["sessionId"],
                        "extra_meta": {"visible_in_channel_chat": True},
                    },
                }

            with mock.patch("task_dashboard.runtime.project_admin.subprocess.run", side_effect=fake_registry_run):
                code, payload = bootstrap_project_response(
                    body={
                        "project_id": "test_demo_project",
                        "project_name": "演示项目",
                        "project_root_rel": "projects/demo-project",
                        "task_root_rel": "projects/demo-project/任务规划",
                        "channels": [
                            {
                                "name": "主体-总控",
                                "desc": "总控通道",
                                "cli_type": "codex",
                                "primary_alias": "演示总控",
                                "primary_purpose": "负责演示项目总控协作",
                            }
                        ],
                        "bootstrap": {
                            "create_primary_sessions": True,
                            "primary_channel_names": ["主体-总控"],
                            "generate_registry": True,
                            "run_dedup": False,
                            "run_visibility_check": False,
                            "send_bootstrap_message": True,
                            "send_init_training": True,
                            "onboarding_isolated_test_project": True,
                            "onboarding_source_ref": {
                                "project_id": "test_demo_project",
                                "channel_name": "辅助04",
                                "session_id": "019db997-36c9-73c3-b660-7e291474b3da",
                            },
                            "onboarding_callback_to": {
                                "channel_name": "辅助04",
                                "session_id": "019db997-36c9-73c3-b660-7e291474b3da",
                            },
                        },
                    },
                    config_path=config_path,
                    repo_root=repo_root,
                    session_store=session_store,
                    create_cli_session=lambda **kwargs: {
                        "ok": True,
                        "sessionId": created_sid,
                        "sessionPath": str(repo_root / "sessions" / "rollout.jsonl"),
                        "workdir": str(repo_root / "projects" / "demo-project"),
                        "cliType": "codex",
                    },
                    detect_git_branch=lambda _root: "main",
                    build_session_seed_prompt=lambda **_kwargs: "seed",
                    decorate_session_display_fields=lambda row: row,
                    apply_session_work_context=_apply_session_work_context,
                    read_task_dashboard_generated_at=lambda: "",
                    rebuild_dashboard_static=lambda timeout_s: {"ok": True, "timeout_s": timeout_s},
                    clear_dashboard_cfg_cache=lambda: None,
                    announce_onboarding_message=fake_sender,
                )

            self.assertEqual(code, 200)
            self.assertTrue(payload["onboarding_ready"])
            self.assertEqual(payload["onboarding_state"], "ready")
            self.assertEqual(len(sent_payloads), 2)
            self.assertEqual(payload["onboarding_delivery"]["state"], "sent")
            self.assertEqual(payload["onboarding_delivery"]["first_visible_messages"][0]["target_session_id"], created_sid)
            self.assertEqual(payload["onboarding_delivery"]["init_training_messages"][0]["target_session_id"], created_sid)
            training_payload = sent_payloads[1]
            self.assertEqual(training_payload["interaction_mode"], "task_with_receipt")
            self.assertEqual(training_payload["source_ref"]["session_id"], "019db997-36c9-73c3-b660-7e291474b3da")
            self.assertEqual(training_payload["callback_to"]["session_id"], "019db997-36c9-73c3-b660-7e291474b3da")
            self.assertIn("announce_run_id + target_session_id一致 + visible_in_channel_chat=true", training_payload["message"])

    def test_bootstrap_onboarding_blocks_non_test_project_without_sending(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo_root = Path(td)
            (repo_root / "scripts").mkdir(parents=True, exist_ok=True)
            (repo_root / "scripts" / "bootstrap_project_collab.py").write_text(
                "#!/usr/bin/env python3\nprint('ok')\n",
                encoding="utf-8",
            )
            config_path = repo_root / "config.toml"
            config_path.write_text('version = 1\n', encoding="utf-8")
            session_store = server.SessionStore(repo_root / ".runtime" / "stable")
            created_sid = "019dc54c-9ebd-7ca2-9694-4e04671b60be"
            sent_payloads: list[dict] = []

            def fake_registry_run(args, **_kwargs):
                for flag in ("--output", "--view-output", "--html-output"):
                    path = Path(args[args.index(flag) + 1])
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text("{}\n" if path.suffix == ".json" else "ok\n", encoding="utf-8")
                return mock.Mock(returncode=0, stdout="ok", stderr="")

            with mock.patch("task_dashboard.runtime.project_admin.subprocess.run", side_effect=fake_registry_run):
                code, payload = bootstrap_project_response(
                    body={
                        "project_id": "demo_project",
                        "project_name": "演示项目",
                        "project_root_rel": "projects/demo-project",
                        "task_root_rel": "projects/demo-project/任务规划",
                        "channels": [
                            {
                                "name": "主体-总控",
                                "desc": "总控通道",
                                "cli_type": "codex",
                                "primary_alias": "演示总控",
                                "primary_purpose": "负责演示项目总控协作",
                            }
                        ],
                        "bootstrap": {
                            "create_primary_sessions": True,
                            "primary_channel_names": ["主体-总控"],
                            "generate_registry": True,
                            "run_dedup": False,
                            "run_visibility_check": False,
                            "send_bootstrap_message": True,
                            "send_init_training": True,
                            "onboarding_isolated_test_project": True,
                        },
                    },
                    config_path=config_path,
                    repo_root=repo_root,
                    session_store=session_store,
                    create_cli_session=lambda **kwargs: {
                        "ok": True,
                        "sessionId": created_sid,
                        "sessionPath": str(repo_root / "sessions" / "rollout.jsonl"),
                        "workdir": str(repo_root / "projects" / "demo-project"),
                        "cliType": "codex",
                    },
                    detect_git_branch=lambda _root: "main",
                    build_session_seed_prompt=lambda **_kwargs: "seed",
                    decorate_session_display_fields=lambda row: row,
                    apply_session_work_context=_apply_session_work_context,
                    read_task_dashboard_generated_at=lambda: "",
                    rebuild_dashboard_static=lambda timeout_s: {"ok": True, "timeout_s": timeout_s},
                    clear_dashboard_cfg_cache=lambda: None,
                    announce_onboarding_message=lambda payload: sent_payloads.append(payload) or {"ok": True},
                )

            self.assertEqual(code, 200)
            self.assertEqual(sent_payloads, [])
            self.assertFalse(payload["onboarding_ready"])
            self.assertEqual(payload["onboarding_state"], "pending")
            self.assertEqual(payload["onboarding_delivery"]["state"], "blocked")
            missing_codes = {item.get("code") for item in payload["onboarding_delivery"]["missing_items"]}
            self.assertIn("onboarding_isolation_required", missing_codes)

    def test_bootstrap_returns_resume_from_step_when_registry_fails(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo_root = Path(td)
            config_path = repo_root / "config.toml"
            config_path.write_text('version = 1\n', encoding="utf-8")
            session_store = server.SessionStore(repo_root / ".runtime" / "stable")
            body = {
                "project_id": "demo_project",
                "project_name": "演示项目",
                "project_root_rel": "projects/demo-project",
                "task_root_rel": "projects/demo-project/任务规划",
                "channels": [{"name": "主体-总控", "desc": "总控通道", "cli_type": "codex"}],
                "bootstrap": {
                    "create_primary_sessions": False,
                    "generate_registry": True,
                    "run_dedup": False,
                    "run_visibility_check": False,
                },
            }

            with mock.patch(
                "task_dashboard.runtime.project_admin.subprocess.run",
                return_value=mock.Mock(returncode=1, stdout="", stderr="registry failed"),
            ):
                code, payload = bootstrap_project_response(
                    body=body,
                    config_path=config_path,
                    repo_root=repo_root,
                    session_store=session_store,
                    create_cli_session=lambda **kwargs: {"ok": True, "sessionId": "unused", "sessionPath": "", "workdir": str(repo_root)},
                    detect_git_branch=lambda _root: "main",
                    build_session_seed_prompt=lambda **_kwargs: "seed",
                    decorate_session_display_fields=lambda row: row,
                    apply_session_work_context=_apply_session_work_context,
                    read_task_dashboard_generated_at=lambda: "",
                    rebuild_dashboard_static=lambda timeout_s: {"ok": True, "timeout_s": timeout_s},
                    clear_dashboard_cfg_cache=lambda: None,
                )

            self.assertEqual(code, 500)
            self.assertEqual(payload["resume_from_step"], "generate_registry")
            self.assertTrue((repo_root / "projects" / "demo-project" / "README.md").exists())
            self.assertTrue((repo_root / ".runtime" / "stable" / ".sessions" / "demo_project.json").exists())

    def test_bootstrap_registry_uses_dashboard_repo_root_for_script_lookup(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workspace_root = Path(td)
            dashboard_repo = workspace_root / "dashboard"
            dashboard_repo.mkdir(parents=True, exist_ok=True)
            (dashboard_repo / "scripts").mkdir(parents=True, exist_ok=True)
            (dashboard_repo / "scripts" / "bootstrap_project_collab.py").write_text(
                "#!/usr/bin/env python3\nprint('ok')\n",
                encoding="utf-8",
            )
            config_path = dashboard_repo / "config.toml"
            config_path.write_text('version = 1\n', encoding="utf-8")
            session_store = server.SessionStore(dashboard_repo / ".runtime" / "stable")
            body = {
                "project_id": "demo_project",
                "project_name": "演示项目",
                "project_root_rel": "projects/demo-project",
                "task_root_rel": "projects/demo-project/任务规划",
                "channels": [{"name": "主体-总控", "desc": "总控通道", "cli_type": "codex"}],
                "bootstrap": {
                    "create_primary_sessions": False,
                    "generate_registry": True,
                    "run_dedup": False,
                    "run_visibility_check": False,
                },
            }

            with mock.patch(
                "task_dashboard.runtime.project_admin.subprocess.run",
                return_value=mock.Mock(returncode=0, stdout="ok", stderr=""),
            ) as mocked_run:
                code, payload = bootstrap_project_response(
                    body=body,
                    config_path=config_path,
                    repo_root=workspace_root,
                    session_store=session_store,
                    create_cli_session=lambda **kwargs: {"ok": True, "sessionId": "unused", "sessionPath": "", "workdir": str(workspace_root)},
                    detect_git_branch=lambda _root: "main",
                    build_session_seed_prompt=lambda **_kwargs: "seed",
                    decorate_session_display_fields=lambda row: row,
                    apply_session_work_context=_apply_session_work_context,
                    read_task_dashboard_generated_at=lambda: "",
                    rebuild_dashboard_static=lambda timeout_s: {"ok": True, "timeout_s": timeout_s},
                    clear_dashboard_cfg_cache=lambda: None,
                )

            self.assertEqual(code, 200)
            self.assertTrue(payload["ok"])
            called_args, called_kwargs = mocked_run.call_args
            self.assertEqual(Path(called_args[0][1]).resolve(), (dashboard_repo / "scripts" / "bootstrap_project_collab.py").resolve())
            self.assertEqual(Path(called_kwargs["cwd"]).resolve(), dashboard_repo.resolve())
            self.assertTrue((workspace_root / "projects" / "demo-project" / "README.md").exists())


if __name__ == "__main__":
    unittest.main()
