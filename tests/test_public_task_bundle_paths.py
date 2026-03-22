import unittest

from task_dashboard.cli import _task_item_bundle_url


class PublicTaskBundlePathTests(unittest.TestCase):
    def test_task_item_bundle_url_is_relative_to_dist_root(self) -> None:
        self.assertEqual(
            _task_item_bundle_url("project-task-dashboard.data", "overview.json"),
            "project-task-dashboard.data/items/overview.json",
        )


if __name__ == "__main__":
    unittest.main()
