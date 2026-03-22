import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from task_dashboard.public_install import install_public_bundle


class PublicInstallTests(unittest.TestCase):
    def _write_example_seed(self, repo_root: Path, *, project_id: str, example_dir: str) -> None:
        example_root = repo_root / "examples" / example_dir
        seed_root = example_root / "seed"
        skill_root = example_root / "skills" / "master-control"
        seed_root.mkdir(parents=True, exist_ok=True)
        skill_root.mkdir(parents=True, exist_ok=True)
        (skill_root / "SKILL.md").write_text("# master-control\n", encoding="utf-8")
        files = {
            "project_seed.json": {
                "schema_version": "1.0",
                "public_safe": True,
                "project": {"id": project_id, "name": project_id},
            },
            "channels_seed.json": {
                "schema_version": "1.0",
                "public_safe": True,
                "channels": [{"name": "主体-总控", "default_enabled": True}],
            },
            "agents_seed.json": {
                "schema_version": "1.0",
                "public_safe": True,
                "agents": [
                    {
                        "agent_id": "master_control",
                        "channel_name": "主体-总控",
                        "default_enabled": True,
                        "role": "主控",
                    }
                ],
            },
            "tasks_seed.json": {
                "schema_version": "1.0",
                "public_safe": True,
                "tasks": [
                    {
                        "code": "task",
                        "channel_name": "主体-总控",
                        "status": "待开始",
                        "title": "示例任务",
                        "path": f"examples/{example_dir}/tasks/主体-总控/任务/【待开始】【任务】示例任务.md",
                    }
                ],
            },
            "skills-manifest.json": {
                "schema_version": "1.0",
                "public_safe": True,
                "skills": [
                    {
                        "name": "master-control",
                        "path": f"examples/{example_dir}/skills/master-control/SKILL.md",
                    }
                ],
            },
        }
        inventory = {
            "schema_version": "1.0",
            "public_safe": True,
            "files": [
                f"examples/{example_dir}/seed/project_seed.json",
                f"examples/{example_dir}/seed/channels_seed.json",
                f"examples/{example_dir}/seed/agents_seed.json",
                f"examples/{example_dir}/seed/tasks_seed.json",
                f"examples/{example_dir}/seed/skills-manifest.json",
            ],
        }
        for name, payload in files.items():
            (seed_root / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (seed_root / "seed-inventory.json").write_text(
            json.dumps(inventory, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def test_install_public_bundle_bootstraps_both_examples(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo_root = Path(td)
            self._write_example_seed(repo_root, project_id="minimal_project", example_dir="minimal-project")
            self._write_example_seed(repo_root, project_id="standard_project", example_dir="standard-project")
            result = install_public_bundle(
                repo_root,
                bootstrap_projects=["minimal_project", "standard_project"],
                build_pages=False,
                start_server=False,
            )
            self.assertTrue(result["ok"])
            self.assertEqual(result["bootstrap_projects"], ["minimal_project", "standard_project"])
            startup_batches = result.get("startup_batches") if isinstance(result.get("startup_batches"), list) else []
            self.assertEqual(len(startup_batches), 2)
            result_path = repo_root / ".run" / "public-install-result.json"
            self.assertTrue(result_path.exists())
            payload = json.loads(result_path.read_text(encoding="utf-8"))
            self.assertEqual(len(payload["results"]["bootstrap"]), 2)
            self.assertEqual(len(payload["results"]["startup_batches"]), 2)
            minimal_runtime = repo_root / "examples" / "minimal-project" / ".runtime" / "demo" / "bootstrap-result.json"
            standard_runtime = repo_root / "examples" / "standard-project" / ".runtime" / "demo" / "bootstrap-result.json"
            self.assertTrue(minimal_runtime.exists())
            self.assertTrue(standard_runtime.exists())

    def test_install_public_bundle_defaults_to_standard_project_only(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo_root = Path(td)
            self._write_example_seed(repo_root, project_id="minimal_project", example_dir="minimal-project")
            self._write_example_seed(repo_root, project_id="standard_project", example_dir="standard-project")
            result = install_public_bundle(
                repo_root,
                build_pages=False,
                start_server=False,
            )
            self.assertTrue(result["ok"])
            self.assertEqual(result["bootstrap_projects"], ["standard_project"])
            startup_batches = result.get("startup_batches") if isinstance(result.get("startup_batches"), list) else []
            self.assertEqual(len(startup_batches), 1)
            self.assertTrue(Path(startup_batches[0]["json_path"]).exists())
            self.assertTrue(Path(startup_batches[0]["markdown_path"]).exists())
            minimal_runtime = repo_root / "examples" / "minimal-project" / ".runtime" / "demo" / "bootstrap-result.json"
            standard_runtime = repo_root / "examples" / "standard-project" / ".runtime" / "demo" / "bootstrap-result.json"
            self.assertFalse(minimal_runtime.exists())
            self.assertTrue(standard_runtime.exists())

    def test_install_public_bundle_skips_activation_when_server_not_ready(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo_root = Path(td)
            self._write_example_seed(repo_root, project_id="standard_project", example_dir="standard-project")
            with (
                mock.patch(
                    "task_dashboard.public_install._detect_codex_readiness",
                    return_value={
                        "codex_cli_found": True,
                        "codex_cli_path": "/usr/local/bin/codex",
                        "codex_sessions_root": "/tmp/codex-sessions",
                        "codex_sessions_writable": True,
                    },
                ),
                mock.patch(
                    "task_dashboard.public_install._wait_for_health",
                    side_effect=RuntimeError("server not ready"),
                ),
            ):
                result = install_public_bundle(
                    repo_root,
                    build_pages=False,
                    start_server=False,
                    activate_project="standard_project",
                    include_optional=True,
                )
            self.assertTrue(result["ok"])
            activation = result.get("activation") if isinstance(result.get("activation"), dict) else {}
            self.assertTrue(activation.get("skipped"))
            self.assertEqual(activation.get("reason"), "server_not_ready_for_activation")

    def test_install_public_bundle_activates_standard_project_when_server_ready(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo_root = Path(td)
            self._write_example_seed(repo_root, project_id="standard_project", example_dir="standard-project")
            with (
                mock.patch(
                    "task_dashboard.public_install._detect_codex_readiness",
                    return_value={
                        "codex_cli_found": True,
                        "codex_cli_path": "/usr/local/bin/codex",
                        "codex_sessions_root": "/tmp/codex-sessions",
                        "codex_sessions_writable": True,
                    },
                ),
                mock.patch(
                    "task_dashboard.public_install._wait_for_health",
                    return_value={"ok": True, "project_id": "standard_project"},
                ),
                mock.patch(
                    "task_dashboard.public_install.activate_public_example_agents",
                    return_value={
                        "ok": True,
                        "project_id": "standard_project",
                        "counts": {"channels": 1, "sessions": 1, "sample_runs": 0, "completed_runs": 0},
                    },
                ) as activation_mock,
            ):
                result = install_public_bundle(
                    repo_root,
                    build_pages=False,
                    start_server=False,
                    activate_project="standard_project",
                    include_optional=True,
                )
            self.assertTrue(result["ok"])
            activation = result.get("activation") if isinstance(result.get("activation"), dict) else {}
            self.assertTrue(activation.get("ok"))
            activation_mock.assert_called_once()
            _, kwargs = activation_mock.call_args
            self.assertEqual(kwargs["project_id"], "standard_project")
            self.assertTrue(kwargs["include_optional"])

    def test_install_public_bundle_defers_to_local_ai_on_auth_block(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo_root = Path(td)
            self._write_example_seed(repo_root, project_id="standard_project", example_dir="standard-project")
            with (
                mock.patch(
                    "task_dashboard.public_install._detect_codex_readiness",
                    return_value={
                        "codex_cli_found": True,
                        "codex_cli_path": "/usr/local/bin/codex",
                        "codex_sessions_root": "/tmp/codex-sessions",
                        "codex_sessions_writable": True,
                    },
                ),
                mock.patch(
                    "task_dashboard.public_install._wait_for_health",
                    return_value={"ok": True, "project_id": "standard_project"},
                ),
                mock.patch(
                    "task_dashboard.public_install.activate_public_example_agents",
                    side_effect=RuntimeError("401 unauthorized: please login first"),
                ),
            ):
                result = install_public_bundle(
                    repo_root,
                    build_pages=False,
                    start_server=False,
                    activate_project="standard_project",
                    include_optional=True,
                )
            self.assertTrue(result["ok"])
            self.assertEqual(result.get("agent_activation_state"), "deferred_to_local_ai")
            activation = result.get("activation") if isinstance(result.get("activation"), dict) else {}
            self.assertTrue(activation.get("deferred_to_local_ai"))
            self.assertEqual(activation.get("reason"), "codex_noninteractive_auth_blocked")

    def test_install_public_bundle_defers_to_local_ai_on_probe_failure(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo_root = Path(td)
            self._write_example_seed(repo_root, project_id="standard_project", example_dir="standard-project")
            with (
                mock.patch(
                    "task_dashboard.public_install._detect_codex_readiness",
                    return_value={
                        "codex_cli_found": True,
                        "codex_cli_path": "/usr/local/bin/codex",
                        "codex_sessions_root": "/tmp/codex-sessions",
                        "codex_sessions_writable": True,
                    },
                ),
                mock.patch(
                    "task_dashboard.public_install._wait_for_health",
                    return_value={"ok": True, "project_id": "standard_project"},
                ),
                mock.patch(
                    "task_dashboard.public_install.activate_public_example_agents",
                    side_effect=RuntimeError("session create returned empty session id"),
                ),
            ):
                result = install_public_bundle(
                    repo_root,
                    build_pages=False,
                    start_server=False,
                    activate_project="standard_project",
                    include_optional=True,
                )
            self.assertTrue(result["ok"])
            self.assertEqual(result.get("agent_activation_state"), "deferred_to_local_ai")
            activation = result.get("activation") if isinstance(result.get("activation"), dict) else {}
            self.assertTrue(activation.get("deferred_to_local_ai"))
            self.assertEqual(activation.get("reason"), "codex_noninteractive_probe_failed")


if __name__ == "__main__":
    unittest.main()
