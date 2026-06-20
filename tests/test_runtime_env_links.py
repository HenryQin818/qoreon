import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from task_dashboard import cli


class RuntimeEnvLinkTests(unittest.TestCase):
    def test_cli_injects_project_source_fields_into_task_and_overview_data(self) -> None:
        captured = {}

        def fake_render(_script_dir, template_name, data):  # type: ignore[no-untyped-def]
            captured[template_name] = data
            return f"<html>{template_name}</html>"

        project_cfg = {
            "id": "website_work",
            "name": "网站工作",
            "project_root_rel": "qoreon-demo/项目看板/task-dashboard-refactor/sandbox_projects/website_work",
            "task_root_rel": "qoreon-demo/项目看板/task-dashboard-refactor/sandbox_projects/website_work/任务规划",
            "channels": [],
        }

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with mock.patch(
                "task_dashboard.cli.load_dashboard_config",
                return_value={"projects": [project_cfg], "dashboard": {}},
            ), mock.patch("task_dashboard.cli.iter_items", return_value=[]), mock.patch(
                "task_dashboard.cli.render_from_template",
                side_effect=fake_render,
            ):
                rc = cli.main(
                    [
                        "--root",
                        str(root),
                        "--out-task",
                        "dist/project-task-dashboard.html",
                        "--out-overview",
                        "dist/project-overview-dashboard.html",
                        "--out-agent-directory",
                        "dist/project-agent-directory.html",
                        "--out-agent-relationship-board",
                        "dist/project-agent-relationship-board.html",
                    ]
                )

            self.assertEqual(rc, 0)
            task_projects = (captured.get("template.html") or {}).get("projects") or []
            overview_projects = ((captured.get("template_overview.html") or {}).get("overview") or {}).get("projects") or []
            self.assertEqual(task_projects[0]["source_kind"], "sandbox")
            self.assertEqual(task_projects[0]["source_label"], "sandbox_projects")
            self.assertEqual(overview_projects[0]["source_kind"], "sandbox")
            self.assertEqual(overview_projects[0]["source_label"], "sandbox_projects")

    def test_cli_uses_environment_specific_page_links(self) -> None:
        captured = {}

        def fake_render(_script_dir, template_name, data):  # type: ignore[no-untyped-def]
            captured[template_name] = data
            return f"<html>{template_name}</html>"

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with mock.patch.dict(
                os.environ,
                {
                    "TASK_DASHBOARD_TASK_PAGE_LINK": "project-task-dashboard-refactor.html",
                    "TASK_DASHBOARD_OVERVIEW_PAGE_LINK": "project-overview-dashboard-refactor.html",
                    "TASK_DASHBOARD_OPEN_SOURCE_SYNC_PAGE_LINK": "project-open-source-sync-board-refactor.html",
                },
                clear=False,
            ), mock.patch("task_dashboard.cli.load_dashboard_config", return_value={"projects": [], "dashboard": {}}), mock.patch(
                "task_dashboard.cli.build_overview",
                return_value={"totals": {}, "projects": []},
            ), mock.patch("task_dashboard.cli.render_from_template", side_effect=fake_render):
                rc = cli.main(
                    [
                        "--root",
                        str(root),
                        "--out-task",
                        "dist/project-task-dashboard.html",
                        "--out-overview",
                        "dist/project-overview-dashboard.html",
                        "--out-agent-directory",
                        "dist/project-agent-directory.html",
                        "--out-agent-relationship-board",
                        "dist/project-agent-relationship-board.html",
                    ]
                )

            self.assertEqual(rc, 0)
            task_data = captured.get("template.html") or {}
            overview_data = captured.get("template_overview.html") or {}
            self.assertEqual(
                task_data.get("links"),
                {
                    "task_page": "project-task-dashboard-refactor.html",
                    "overview_page": "project-overview-dashboard-refactor.html",
                    "communication_page": "project-communication-audit.html",
                    "project_chat_page": "project-task-dashboard.html",
                    "status_report_page": "project-status-report.html",
                    "open_source_sync_page": "project-open-source-sync-board-refactor.html",
                    "platform_architecture_board_page": "project-platform-architecture-board.html",
                    "agent_directory_page": "project-agent-directory.html",
                    "agent_curtain_page": "project-agent-curtain.html",
                    "agent_relationship_board_page": "project-agent-relationship-board.html",
                    "session_health_page": "project-session-health-dashboard.html",
                    "runstore_health_page": "project-runstore-health.html",
                    "agent_capability_page": "project-agent-capability-dashboard.html",
                },
            )
            self.assertEqual(overview_data.get("links"), task_data.get("links"))


if __name__ == "__main__":
    unittest.main()
