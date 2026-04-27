import tempfile
import unittest
from pathlib import Path
from unittest import mock

from task_dashboard.runtime import session_task_tracking


class SessionTaskTrackingCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        session_task_tracking._clear_task_tracking_file_caches()

    def _task_file(self, repo_root: Path) -> Path:
        task_path = (
            repo_root
            / "任务规划"
            / "辅助04-原型设计与Demo可视化（静态数据填充-业务规格确认）"
            / "任务"
            / "【进行中】【任务】20260402-session-detail-cache-smoke.md"
        )
        task_path.parent.mkdir(parents=True, exist_ok=True)
        task_path.write_text("# 任务目标\n- 验证缓存\n", encoding="utf-8")
        return task_path

    def test_load_task_summary_text_reuses_file_cache_across_requests(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo_root = Path(td)
            task_file = self._task_file(repo_root)
            session = {"worktree_root": str(repo_root)}
            rel_path = str(task_file.relative_to(repo_root))

            with mock.patch(
                "task_dashboard.runtime.session_task_tracking.safe_read_text",
                return_value="# 任务目标\n- 验证缓存\n",
            ) as read_mock:
                first = session_task_tracking._load_task_summary_text(
                    session=session,
                    project_id="task_dashboard",
                    task_path=rel_path,
                    cache={},
                    resolve_cache={},
                )
                second = session_task_tracking._load_task_summary_text(
                    session=session,
                    project_id="task_dashboard",
                    task_path=rel_path,
                    cache={},
                    resolve_cache={},
                )

        self.assertEqual(first, "验证缓存")
        self.assertEqual(second, "验证缓存")
        self.assertEqual(read_mock.call_count, 1)

    def test_load_task_harness_roles_reuses_file_cache_across_requests(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo_root = Path(td)
            task_file = self._task_file(repo_root)
            session = {"worktree_root": str(repo_root)}
            rel_path = str(task_file.relative_to(repo_root))
            harness_roles = {
                "main_owner": {"agent_name": "产品策划-任务派发"},
                "collaborators": [],
                "validators": [],
                "challengers": [],
                "backup_owners": [],
                "management_slot": [],
                "custom_roles": [],
            }

            with mock.patch(
                "task_dashboard.runtime.session_task_tracking.safe_read_text",
                return_value="# 任务目标\n- 验证缓存\n",
            ) as read_mock, mock.patch(
                "task_dashboard.runtime.session_task_tracking.parse_task_harness",
                return_value=harness_roles,
            ) as parse_mock:
                first = session_task_tracking._load_task_harness_roles(
                    session=session,
                    project_id="task_dashboard",
                    task_path=rel_path,
                    cache={},
                    resolve_cache={},
                )
                second = session_task_tracking._load_task_harness_roles(
                    session=session,
                    project_id="task_dashboard",
                    task_path=rel_path,
                    cache={},
                    resolve_cache={},
                )

        self.assertEqual(first.get("main_owner"), {"agent_name": "产品策划-任务派发"})
        self.assertEqual(second.get("main_owner"), {"agent_name": "产品策划-任务派发"})
        self.assertEqual(read_mock.call_count, 1)
        self.assertEqual(parse_mock.call_count, 1)

    def test_task_tracking_prefers_project_workdir_over_dashboard_worktree(self) -> None:
        class FakeStore:
            def list_runs(self, *args, **kwargs):
                return [
                    {
                        "id": "run-1",
                        "status": "done",
                        "finishedAt": "2026-04-27T19:40:00+0800",
                    }
                ]

            def load_meta(self, run_id):
                return {}

        with tempfile.TemporaryDirectory() as project_td, tempfile.TemporaryDirectory() as dashboard_td:
            project_root = Path(project_td)
            dashboard_root = Path(dashboard_td)
            channel_name = "主体01-产品方案与业务结构"
            task_file = (
                project_root
                / "任务规划"
                / channel_name
                / "任务"
                / "【进行中】【任务】20260422-会后任务05-NDT沙盘推演与预案组合配置业务规格建立.md"
            )
            task_file.parent.mkdir(parents=True, exist_ok=True)
            task_file.write_text("# 任务目标\n- 继续推进沙盘推演与预案组合配置。\n", encoding="utf-8")

            session = {
                "id": "019dce85-d87a-7163-82ac-1a09911b0242",
                "channel_name": channel_name,
                "worktree_root": str(dashboard_root),
                "workdir": str(project_root),
                "project_execution_context": {
                    "target": {
                        "worktree_root": str(dashboard_root),
                        "workdir": str(project_root),
                    }
                },
            }

            tracking = session_task_tracking.build_session_task_tracking(
                session=session,
                store=FakeStore(),
                project_id="ndt",
                session_id="019dce85-d87a-7163-82ac-1a09911b0242",
                runtime_state={"updated_at": "2026-04-27T19:40:00+0800"},
            )

        current = tracking.get("current_task_ref") or {}
        self.assertEqual(
            current.get("task_path"),
            str(task_file.relative_to(project_root)),
        )
        self.assertEqual(current.get("task_primary_status"), "进行中")
        self.assertEqual(
            current.get("task_summary_text"),
            "继续推进沙盘推演与预案组合配置。",
        )


if __name__ == "__main__":
    unittest.main()
