import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import server

from task_dashboard.runtime.project_admin import bootstrap_project_response


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
            self.assertTrue((repo_root / "projects" / "demo-project" / "README.md").exists())
            self.assertTrue((repo_root / "projects" / "demo-project" / "任务规划" / "主体-总控" / "README.md").exists())
            session_store_path = repo_root / ".runtime" / "stable" / ".sessions" / "demo_project.json"
            self.assertTrue(session_store_path.exists())
            session_data = json.loads(session_store_path.read_text(encoding="utf-8"))
            self.assertEqual(session_data["project_id"], "demo_project")
            self.assertEqual(session_data["sessions"], [])
            updated_config = config_path.read_text(encoding="utf-8")
            self.assertIn('[[projects]]', updated_config)
            self.assertIn('id = "demo_project"', updated_config)
            self.assertIn('cli_type = "codex"', updated_config)

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
