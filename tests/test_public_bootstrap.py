import json
import tempfile
import unittest
from pathlib import Path

from task_dashboard.public_bootstrap import bootstrap_public_example


class PublicBootstrapTests(unittest.TestCase):
    def test_bootstrap_public_example_creates_runtime_and_missing_task_files(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo_root = Path(td)
            seed_root = repo_root / "examples" / "minimal-project" / "seed"
            skills_root = repo_root / "examples" / "minimal-project" / "skills"
            seed_root.mkdir(parents=True, exist_ok=True)
            (skills_root / "master-control").mkdir(parents=True, exist_ok=True)

            (skills_root / "master-control" / "SKILL.md").write_text(
                "# master-control\n",
                encoding="utf-8",
            )

            files = {
                "project_seed.json": {
                    "schema_version": "1.0",
                    "public_safe": True,
                    "project": {
                        "id": "minimal_project",
                        "name": "Minimal Project",
                    },
                },
                "channels_seed.json": {
                    "schema_version": "1.0",
                    "public_safe": True,
                    "channels": [
                        {"name": "主体-总控"},
                    ],
                },
                "agents_seed.json": {
                    "schema_version": "1.0",
                    "public_safe": True,
                    "agents": [
                        {
                            "agent_id": "master_control",
                            "channel_name": "主体-总控",
                        }
                    ],
                },
                "tasks_seed.json": {
                    "schema_version": "1.0",
                    "public_safe": True,
                    "tasks": [
                        {
                            "title": "最小协作闭环启动",
                            "channel_name": "主体-总控",
                            "status": "进行中",
                            "path": "examples/minimal-project/tasks/主体-总控/任务/【进行中】【任务】20260320-最小协作闭环启动.md",
                        }
                    ],
                },
                "skills-manifest.json": {
                    "schema_version": "1.0",
                    "public_safe": True,
                    "skills": [
                        {
                            "name": "master-control",
                            "path": "examples/minimal-project/skills/master-control/SKILL.md",
                        }
                    ],
                },
                "seed-inventory.json": {
                    "schema_version": "1.0",
                    "public_safe": True,
                    "files": [
                        "examples/minimal-project/seed/project_seed.json",
                        "examples/minimal-project/seed/channels_seed.json",
                        "examples/minimal-project/seed/agents_seed.json",
                        "examples/minimal-project/seed/tasks_seed.json",
                        "examples/minimal-project/seed/skills-manifest.json",
                    ],
                },
            }

            for name, payload in files.items():
                (seed_root / name).write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )

            result = bootstrap_public_example(repo_root, project_id="minimal_project")

            result_path = repo_root / "examples" / "minimal-project" / ".runtime" / "demo" / "bootstrap-result.json"
            task_path = repo_root / "examples" / "minimal-project" / "tasks" / "主体-总控" / "任务" / "【进行中】【任务】20260320-最小协作闭环启动.md"

            self.assertTrue(result["ok"])
            self.assertEqual(Path(result["bootstrap_result_path"]).resolve(), result_path.resolve())
            self.assertTrue(result_path.exists())
            self.assertTrue(task_path.exists())
            self.assertTrue((repo_root / "examples" / "minimal-project" / ".runtime" / "demo" / ".sessions").exists())
            self.assertTrue((repo_root / "examples" / "minimal-project" / ".runtime" / "demo" / ".runs").exists())
            self.assertEqual(result["counts"]["channels"], 1)
            self.assertEqual(result["counts"]["agents"], 1)
            self.assertEqual(result["counts"]["tasks"], 1)
            self.assertEqual(result["counts"]["skills"], 1)
            manifest = json.loads(result_path.read_text(encoding="utf-8"))
            self.assertIn("python3 server.py --port 18770 --static-root dist", manifest.get("next_steps") or [])
            self.assertIn(
                "python3 scripts/activate_public_example_agents.py --project-id standard_project --base-url http://127.0.0.1:18770",
                manifest.get("next_steps") or [],
            )

    def test_bootstrap_public_example_supports_custom_example_root(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo_root = Path(td)
            seed_root = repo_root / "examples" / "standard-project" / "seed"
            skills_root = repo_root / "examples" / "standard-project" / "skills"
            seed_root.mkdir(parents=True, exist_ok=True)
            (skills_root / "master-control").mkdir(parents=True, exist_ok=True)

            (skills_root / "master-control" / "SKILL.md").write_text(
                "# master-control\n",
                encoding="utf-8",
            )

            files = {
                "project_seed.json": {
                    "schema_version": "1.0",
                    "public_safe": True,
                    "project": {
                        "id": "standard_project",
                        "name": "Standard Project",
                    },
                },
                "channels_seed.json": {
                    "schema_version": "1.0",
                    "public_safe": True,
                    "channels": [
                        {"name": "主体-总控"},
                    ],
                },
                "agents_seed.json": {
                    "schema_version": "1.0",
                    "public_safe": True,
                    "agents": [
                        {
                            "agent_id": "master_control",
                            "channel_name": "主体-总控",
                        }
                    ],
                },
                "tasks_seed.json": {
                    "schema_version": "1.0",
                    "public_safe": True,
                    "tasks": [
                        {
                            "title": "完整标准项目落位",
                            "channel_name": "主体-总控",
                            "status": "进行中",
                            "path": "examples/standard-project/tasks/主体-总控/任务/【进行中】【任务】20260321-完整标准项目落位.md",
                        }
                    ],
                },
                "skills-manifest.json": {
                    "schema_version": "1.0",
                    "public_safe": True,
                    "skills": [
                        {
                            "name": "master-control",
                            "path": "examples/standard-project/skills/master-control/SKILL.md",
                        }
                    ],
                },
                "seed-inventory.json": {
                    "schema_version": "1.0",
                    "public_safe": True,
                    "files": [
                        "examples/standard-project/seed/project_seed.json",
                        "examples/standard-project/seed/channels_seed.json",
                        "examples/standard-project/seed/agents_seed.json",
                        "examples/standard-project/seed/tasks_seed.json",
                        "examples/standard-project/seed/skills-manifest.json",
                    ],
                },
            }

            for name, payload in files.items():
                (seed_root / name).write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )

            result = bootstrap_public_example(repo_root, example_root_rel="examples/standard-project")

            result_path = repo_root / "examples" / "standard-project" / ".runtime" / "demo" / "bootstrap-result.json"
            self.assertTrue(result["ok"])
            self.assertEqual(Path(result["bootstrap_result_path"]).resolve(), result_path.resolve())
            self.assertTrue(result_path.exists())
            self.assertEqual(result["project_id"], "standard_project")


if __name__ == "__main__":
    unittest.main()
