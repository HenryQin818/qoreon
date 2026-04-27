import tempfile
import unittest
from pathlib import Path
from unittest import mock

from task_dashboard import cli as cli_module
from task_dashboard.session_store import SessionStore


class CliSessionSourcePriorityTests(unittest.TestCase):
    def test_cli_prefers_session_store_over_legacy_session_file(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            legacy_path = root / "legacy-sessions.json"
            legacy_path.write_text(
                '{"channels":{"子级07":[{"sessionId":"019c0000-0000-7000-8000-000000000010","alias":"旧主会话"}]}}',
                encoding="utf-8",
            )
            store = SessionStore(root)
            store.create_session(
                "task_dashboard",
                "子级07",
                cli_type="codex",
                session_id="019c0000-0000-7000-8000-000000000011",
                alias="真源会话",
                model="gpt-5.3-codex",
                reasoning_effort="medium",
                is_primary=True,
            )

            captured: list[dict] = []

            def _fake_render(_script_dir, template_name, data):
                if template_name == "template.html":
                    captured.append(data)
                return "<html></html>"

            cfg = {
                "projects": [
                    {
                        "id": "task_dashboard",
                        "name": "Task Dashboard",
                        "task_root_rel": "任务规划",
                        "session_json_rel": legacy_path.name,
                        "channels": [{"name": "子级07", "cli_type": "codex"}],
                    }
                ]
            }

            with mock.patch.object(cli_module, "load_dashboard_config", return_value=cfg), \
                mock.patch.object(cli_module, "iter_items", return_value=[]), \
                mock.patch.object(cli_module, "build_overview", return_value={}), \
                mock.patch.object(cli_module, "render_from_template", side_effect=_fake_render):
                rc = cli_module.main(
                    [
                        "--root",
                        str(root),
                        "--out-task",
                        "dist/task.html",
                        "--out-overview",
                        "dist/overview.html",
                        "--out-communication",
                        "dist/communication.html",
                    ]
                )
            self.assertEqual(rc, 0)
            self.assertTrue(bool(captured))
            projects = captured[0].get("projects") or []
            self.assertEqual(len(projects), 1)
            channel_sessions = projects[0].get("channel_sessions") or []
            self.assertEqual(len(channel_sessions), 1)
            session = channel_sessions[0]
            self.assertEqual(session.get("session_id"), "019c0000-0000-7000-8000-000000000011")
            self.assertEqual(session.get("alias"), "真源会话")
            self.assertEqual(session.get("source"), "session_store")

    def test_cli_reads_project_execution_context_sessions_root(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            runtime_root = root / "runtime" / "stable"
            store = SessionStore(runtime_root)
            store.create_session(
                "demo_project",
                "总控分工",
                cli_type="codex",
                session_id="019dc54c-9ebd-7ca2-9694-4e04671b60be",
                alias="项目经理",
                is_primary=True,
            )

            captured: list[dict] = []

            def _fake_render(_script_dir, template_name, data):
                if template_name == "template.html":
                    captured.append(data)
                return "<html></html>"

            cfg = {
                "projects": [
                    {
                        "id": "demo_project",
                        "name": "演示项目",
                        "project_root_rel": "projects/demo-project",
                        "task_root_rel": "projects/demo-project/任务规划",
                        "channels": [{"name": "总控分工", "cli_type": "codex"}],
                        "execution_context": {
                            "runtime_root": str(runtime_root),
                            "sessions_root": str(store.sessions_dir),
                        },
                    }
                ]
            }

            with mock.patch.object(cli_module, "load_dashboard_config", return_value=cfg), \
                mock.patch.object(cli_module, "iter_items", return_value=[]), \
                mock.patch.object(cli_module, "build_overview", return_value={}), \
                mock.patch.object(cli_module, "render_from_template", side_effect=_fake_render):
                rc = cli_module.main(
                    [
                        "--root",
                        str(root),
                        "--out-task",
                        "dist/task.html",
                        "--out-overview",
                        "dist/overview.html",
                        "--out-communication",
                        "dist/communication.html",
                    ]
                )

            self.assertEqual(rc, 0)
            projects = captured[0].get("projects") or []
            channel_sessions = projects[0].get("channel_sessions") or []
            self.assertEqual(channel_sessions[0].get("session_id"), "019dc54c-9ebd-7ca2-9694-4e04671b60be")
            self.assertEqual(channel_sessions[0].get("alias"), "项目经理")
            self.assertEqual(channel_sessions[0].get("source"), "session_store")


if __name__ == "__main__":
    unittest.main()
