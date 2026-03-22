import json
import tempfile
import unittest
from pathlib import Path

from task_dashboard.public_agent_activation import build_public_example_activation_plan


class PublicAgentActivationPlanTests(unittest.TestCase):
    def _write_seed(self, root: Path, *, project_id: str = "minimal_project") -> None:
        example_dir = {
            "minimal_project": "minimal-project",
            "standard_project": "standard-project",
        }[project_id]
        seed_root = root / "examples" / example_dir / "seed"
        seed_root.mkdir(parents=True, exist_ok=True)
        files = {
            "project_seed.json": {
                "schema_version": "1.0",
                "public_safe": True,
                "project": {"id": project_id, "name": project_id},
            },
            "channels_seed.json": {
                "schema_version": "1.0",
                "public_safe": True,
                "channels": [
                    {"name": "主体-总控", "default_enabled": True, "capabilities": ["dispatch"]},
                    {"name": "辅助03-用户镜像与业务判断", "default_enabled": False, "capabilities": ["business_judgement"]},
                ],
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
                        "capabilities": ["dispatch"],
                    },
                    {
                        "agent_id": "user_mirror",
                        "channel_name": "辅助03-用户镜像与业务判断",
                        "default_enabled": False,
                        "role": "用户镜像",
                        "capabilities": ["business_judgement"],
                    },
                ],
            },
            "tasks_seed.json": {
                "schema_version": "1.0",
                "public_safe": True,
                "tasks": [
                    {
                        "code": "master",
                        "channel_name": "主体-总控",
                        "title": "总控任务",
                        "status": "进行中",
                        "path": "examples/minimal-project/tasks/主体-总控/任务/【进行中】【任务】总控任务.md",
                    }
                ],
            },
        }
        for name, payload in files.items():
            (seed_root / name).write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

    def test_activation_plan_uses_default_enabled_set(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo_root = Path(td)
            self._write_seed(repo_root)
            plan = build_public_example_activation_plan(repo_root, project_id="minimal_project")
            self.assertEqual(plan["project_id"], "minimal_project")
            self.assertEqual(plan["enabled_channel_names"], ["主体-总控"])
            self.assertEqual(len(plan["session_specs"]), 1)
            self.assertEqual(plan["session_specs"][0]["channel_name"], "主体-总控")
            self.assertEqual(len(plan["sample_actions"]), 1)
            self.assertIn("任务/", plan["sample_actions"][0]["message"])
            self.assertIn("当前结论 / 是否通过或放行", plan["sample_actions"][0]["message"])

    def test_activation_plan_can_include_optional_channels(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo_root = Path(td)
            self._write_seed(repo_root)
            plan = build_public_example_activation_plan(repo_root, project_id="minimal_project", include_optional=True)
            self.assertEqual(len(plan["enabled_channel_names"]), 2)
            self.assertEqual(len(plan["session_specs"]), 2)

    def test_activation_plan_supports_standard_project(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo_root = Path(td)
            self._write_seed(repo_root, project_id="standard_project")
            plan = build_public_example_activation_plan(repo_root, project_id="standard_project")
            self.assertEqual(plan["project_id"], "standard_project")
            self.assertEqual(plan["enabled_channel_names"], ["主体-总控"])
            self.assertEqual(plan["session_specs"][0]["channel_name"], "主体-总控")
            self.assertIn("project-startup-collab-suite", plan["session_specs"][0]["first_message"])


if __name__ == "__main__":
    unittest.main()
