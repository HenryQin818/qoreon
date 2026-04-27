from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from task_dashboard.task_identity import normalize_task_id, normalize_task_path, record_task_identity, render_task_front_matter, resolve_task_reference


class TaskIdentityResolutionTests(unittest.TestCase):
    def test_normalize_task_id_treats_placeholder_values_as_empty(self) -> None:
        for raw in ["", "-", "—", '""', "''", "none", "null", "undefined", "未关联任务"]:
            self.assertEqual(normalize_task_id(raw), "")
        self.assertEqual(normalize_task_id("task_20260423_main"), "task_20260423_main")

    def test_normalize_task_path_decodes_percent_and_repairs_users_prefix(self) -> None:
        repo = Path("/tmp/qoreon-demo/examples/standard-project")
        encoded = "/tmp/qoreon-demo/examples/standard-project/任务规划/子级04-前端体验（task-overview%20页面交互）/任务/【已完成】【任务】20260326-通道阶段工作总结与存量知识梳理.md"
        self.assertEqual(
            normalize_task_path(encoded, repo_root=repo),
            "任务规划/子级04-前端体验（task-overview 页面交互）/任务/【已完成】【任务】20260326-通道阶段工作总结与存量知识梳理.md",
        )

    def test_resolve_prefers_existing_task_path_over_task_id_state(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            runtime_base = repo / ".runtime" / "stable"
            task_root = repo / "任务规划"
            parent_dir = task_root / "辅助04"
            child_dir = task_root / "子级04"
            parent_dir.mkdir(parents=True, exist_ok=True)
            child_dir.mkdir(parents=True, exist_ok=True)

            shared_task_id = "task_20260404_dup"
            parent_rel = "任务规划/辅助04/【进行中】【任务】主任务.md"
            child_rel = "任务规划/子级04/【已完成】【任务】子任务.md"
            parent_file = repo / parent_rel
            child_file = repo / child_rel

            parent_file.write_text(
                render_task_front_matter(
                    task_id=shared_task_id,
                    parent_task_id="",
                    created_at="2026-04-04T00:10:00+0800",
                )
                + "# parent\n",
                encoding="utf-8",
            )
            child_file.write_text(
                render_task_front_matter(
                    task_id=shared_task_id,
                    parent_task_id='""',
                    created_at="2026-04-04T00:11:00+0800",
                )
                + "# child\n",
                encoding="utf-8",
            )

            record_task_identity(
                repo_root=repo,
                runtime_base_dir=runtime_base,
                project_id="task_dashboard",
                task_path=child_rel,
                task_id=shared_task_id,
                parent_task_id='""',
            )

            resolved = resolve_task_reference(
                repo_root=repo,
                runtime_base_dir=runtime_base,
                project_id="task_dashboard",
                task_path=parent_rel,
                task_id=shared_task_id,
            )

            self.assertEqual(resolved["task_path"], parent_rel)
            self.assertEqual(resolved["created_at"], "2026-04-04T00:10:00+0800")
            self.assertEqual(resolved["matched_by"], "task_path")


if __name__ == "__main__":
    unittest.main()
