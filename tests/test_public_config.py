import unittest
from pathlib import Path

from task_dashboard.config import load_dashboard_config


class PublicConfigTests(unittest.TestCase):
    def test_config_has_only_standard_public_project(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        cfg = load_dashboard_config(repo_root)
        projects = cfg.get("projects")
        self.assertIsInstance(projects, list)
        self.assertEqual(len(projects), 1)
        by_id = {str(project.get("id")): project for project in projects if isinstance(project, dict)}

        standard = by_id.get("standard_project")
        self.assertIsNotNone(standard)

        self.assertEqual(standard.get("task_root_rel"), "examples/standard-project/tasks")

        standard_context = standard.get("execution_context") or {}
        self.assertEqual(standard_context.get("server_port"), "18770")

        standard_channels = standard.get("channels")
        self.assertIsInstance(standard_channels, list)
        self.assertEqual(len(standard_channels), 12)


if __name__ == "__main__":
    unittest.main()
