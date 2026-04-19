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


if __name__ == "__main__":
    unittest.main()
