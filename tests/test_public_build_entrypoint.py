import runpy
import unittest
from pathlib import Path
from unittest import mock


class PublicBuildEntrypointTests(unittest.TestCase):
    def test_entrypoint_uses_repo_root_and_dist_defaults(self) -> None:
        entry = Path(__file__).resolve().parents[1] / "build_project_task_dashboard.py"
        with mock.patch("task_dashboard.cli.main", return_value=0) as main_mock, mock.patch(
            "sys.argv",
            [str(entry)],
        ):
            with self.assertRaises(SystemExit) as cm:
                runpy.run_path(str(entry), run_name="__main__")
        self.assertEqual(cm.exception.code, 0)
        args = main_mock.call_args[0][0]
        self.assertEqual(args[:2], ["--root", str(entry.resolve().parent)])
        self.assertEqual(args[args.index("--out-task") + 1], "dist/project-task-dashboard.html")
        self.assertEqual(args[args.index("--out-overview") + 1], "dist/project-overview-dashboard.html")
        self.assertEqual(args[args.index("--out-status-report") + 1], "dist/project-status-report.html")


if __name__ == "__main__":
    unittest.main()
