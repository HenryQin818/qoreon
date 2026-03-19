import unittest
from pathlib import Path

from task_dashboard.config import load_dashboard_config


class PublicConfigTests(unittest.TestCase):
    def test_config_has_minimal_public_project(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        cfg = load_dashboard_config(repo_root)
        projects = cfg.get("projects")
        self.assertIsInstance(projects, list)
        self.assertEqual(len(projects), 1)
        project = projects[0]
        self.assertEqual(project.get("id"), "minimal_project")
        self.assertEqual(project.get("task_root_rel"), "examples/minimal-project/tasks")
        execution_context = project.get("execution_context") or {}
        self.assertEqual(execution_context.get("server_port"), "18770")
        channels = project.get("channels")
        self.assertIsInstance(channels, list)
        self.assertEqual(len(channels), 6)


if __name__ == "__main__":
    unittest.main()
