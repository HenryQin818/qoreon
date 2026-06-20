import runpy
import unittest
from pathlib import Path
from unittest import mock


class BuildEntrypointTests(unittest.TestCase):
    def test_entrypoint_forwards_cli_arguments(self) -> None:
        entry = Path(__file__).resolve().parents[1] / "build_project_task_dashboard.py"
        with mock.patch("task_dashboard.cli.main", return_value=0) as main_mock, mock.patch(
            "sys.argv",
            [str(entry), "--out-task", "custom/task.html", "--with-local-config"],
        ):
            with self.assertRaises(SystemExit) as cm:
                runpy.run_path(str(entry), run_name="__main__")
        self.assertEqual(cm.exception.code, 0)
        args = main_mock.call_args[0][0]
        self.assertTrue(args[:2] == ["--root", str(entry.resolve().parent)])
        self.assertIn("--out-task", args)
        self.assertIn("custom/task.html", args)
        self.assertIn("--with-local-config", args)

    def test_entrypoint_defaults_output_to_current_worktree_dist(self) -> None:
        entry = Path(__file__).resolve().parents[1] / "build_project_task_dashboard.py"
        repo_root = entry.resolve().parent
        repo_rel = Path(".")
        with mock.patch("task_dashboard.cli.main", return_value=0) as main_mock, mock.patch(
            "sys.argv",
            [str(entry)],
        ):
            with self.assertRaises(SystemExit) as cm:
                runpy.run_path(str(entry), run_name="__main__")
        self.assertEqual(cm.exception.code, 0)
        args = main_mock.call_args[0][0]
        out_task = args[args.index("--out-task") + 1]
        out_overview = args[args.index("--out-overview") + 1]
        out_status_report = args[args.index("--out-status-report") + 1]
        out_open_source_sync = args[args.index("--out-open-source-sync") + 1]
        out_agent_directory = args[args.index("--out-agent-directory") + 1]
        out_agent_relationship_board = args[args.index("--out-agent-relationship-board") + 1]
        out_runstore_health = args[args.index("--out-runstore-health") + 1]
        self.assertEqual(
            out_task,
            str(repo_rel / "dist" / "project-task-dashboard.html"),
        )
        self.assertEqual(
            out_overview,
            str(repo_rel / "dist" / "project-overview-dashboard.html"),
        )
        self.assertEqual(
            out_status_report,
            str(repo_rel / "dist" / "project-status-report.html"),
        )
        self.assertEqual(
            out_open_source_sync,
            str(repo_rel / "dist" / "project-open-source-sync-board.html"),
        )
        self.assertEqual(
            out_agent_directory,
            str(repo_rel / "dist" / "project-agent-directory.html"),
        )
        self.assertEqual(
            out_agent_relationship_board,
            str(repo_rel / "dist" / "project-agent-relationship-board.html"),
        )
        self.assertEqual(
            out_runstore_health,
            str(repo_rel / "dist" / "project-runstore-health.html"),
        )


if __name__ == "__main__":
    unittest.main()
