import unittest

from task_dashboard.runtime.reload_handoff import (
    build_reload_handoff_payload,
    evaluate_reload_handoff_health,
)
from task_dashboard.runtime_identity import build_health_runtime_identity


class ReloadHandoffTests(unittest.TestCase):
    def test_build_reload_handoff_payload_marks_ready_when_components_ready(self) -> None:
        payload = build_reload_handoff_payload(
            runtime_role="prod",
            component_statuses={
                "scheduler": {"state": "ready"},
                "task_plan_runtime": {"state": "ready"},
                "heartbeat_task_runtime": {"state": "ready"},
                "session_health_runtime": {"state": "disabled"},
            },
            startup_started_at="2026-04-09T15:40:00+08:00",
            startup_ready_at="2026-04-09T15:40:02+08:00",
        )

        reload_handoff = payload.get("reload_handoff") or {}
        startup_chain = payload.get("startup_chain") or {}
        self.assertEqual(reload_handoff.get("state"), "ready")
        self.assertTrue(bool(reload_handoff.get("ready_for_cutover")))
        self.assertEqual(startup_chain.get("waiting_components"), [])
        self.assertEqual(startup_chain.get("failed_components"), [])

    def test_evaluate_reload_handoff_health_blocks_on_warming_chain(self) -> None:
        expected = build_health_runtime_identity(
            project_id="task_dashboard",
            runtime_role="prod",
            environment="stable",
            port=18765,
            runs_dir="/tmp/main/.runtime/stable/.runs",
            sessions_file="/tmp/main/.runtime/stable/.sessions/task_dashboard.json",
            static_root="/tmp/main/static_sites",
            worktree_root="/tmp/main/task-dashboard",
            config_path="/tmp/main/task-dashboard/config.toml",
        )
        actual = {
            **expected,
            "ok": True,
            **build_reload_handoff_payload(
                runtime_role="prod",
                component_statuses={
                    "scheduler": {"state": "ready"},
                    "task_plan_runtime": {"state": "warming"},
                    "heartbeat_task_runtime": {"state": "ready"},
                    "session_health_runtime": {"state": "ready"},
                },
            ),
        }

        verdict = evaluate_reload_handoff_health(expected, actual)

        self.assertFalse(bool(verdict.get("ok")))
        self.assertEqual(verdict.get("state"), "warming")
        self.assertFalse(bool(verdict.get("ready_for_cutover")))
        self.assertIn("task_plan_runtime", str(verdict.get("summary") or ""))

    def test_evaluate_reload_handoff_health_reports_runtime_identity_mismatch(self) -> None:
        expected = build_health_runtime_identity(
            project_id="task_dashboard",
            runtime_role="prod",
            environment="stable",
            port=18765,
            runs_dir="/tmp/main/.runtime/stable/.runs",
            sessions_file="/tmp/main/.runtime/stable/.sessions/task_dashboard.json",
            static_root="/tmp/main/static_sites",
            worktree_root="/tmp/main/task-dashboard",
            config_path="/tmp/main/task-dashboard/config.toml",
        )
        actual = {
            **build_health_runtime_identity(
                project_id="task_dashboard",
                runtime_role="compat_shell",
                environment="stable",
                port=18765,
                runs_dir="/tmp/main/.runtime/stable/.runs",
                sessions_file="/tmp/main/.runtime/stable/.sessions/task_dashboard.json",
                static_root="/tmp/main/static_sites",
                worktree_root="/tmp/main/task-dashboard",
                config_path="/tmp/main/task-dashboard/config.toml",
            ),
            "ok": True,
            **build_reload_handoff_payload(
                runtime_role="compat_shell",
                component_statuses={
                    "scheduler": {"state": "ready"},
                    "task_plan_runtime": {"state": "ready"},
                    "heartbeat_task_runtime": {"state": "ready"},
                    "session_health_runtime": {"state": "ready"},
                },
            ),
        }

        verdict = evaluate_reload_handoff_health(expected, actual)

        self.assertFalse(bool(verdict.get("ok")))
        self.assertEqual(verdict.get("state"), "mismatch")
        self.assertIn("runtime_role", str(verdict.get("summary") or ""))


if __name__ == "__main__":
    unittest.main()
