from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from task_dashboard.created_at_backfill import (
    _date_prefix_to_iso,
    _filename_date_prefix,
    apply_created_at_candidates,
    build_created_at_inventory,
)
from task_dashboard.task_identity import extract_task_identity_from_markdown


class CreatedAtBackfillTests(unittest.TestCase):
    def test_filename_date_prefix_to_iso(self) -> None:
        self.assertEqual(_filename_date_prefix("【已完成】【任务】20260406-样例任务.md"), "20260406")
        self.assertEqual(_date_prefix_to_iso("20260406"), "2026-04-06T00:00:00+0800")

    def test_git_first_add_becomes_a_grade_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            task_dir = repo / "任务规划" / "子级02" / "任务"
            task_dir.mkdir(parents=True, exist_ok=True)
            task_file = task_dir / "【进行中】【任务】20260401-样例任务.md"
            task_file.write_text("# 【进行中】【任务】20260401-样例任务\n", encoding="utf-8")

            subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True, text=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
            subprocess.run(["git", "add", str(task_file.relative_to(repo))], cwd=repo, check=True)
            env = {
                **dict(),
                **{
                    "GIT_AUTHOR_DATE": "2026-04-01T09:10:11+0800",
                    "GIT_COMMITTER_DATE": "2026-04-01T09:10:11+0800",
                },
            }
            subprocess.run(
                ["git", "commit", "-m", "init task"],
                cwd=repo,
                check=True,
                capture_output=True,
                text=True,
                env={**env, **dict(**subprocess.os.environ)},
            )

            payload = build_created_at_inventory(repo_root=repo, project_id="task_dashboard", project_name="task_dashboard")
            self.assertEqual(payload["summary"]["missing_created_at_total"], 1)
            row = payload["rows"][0]
            self.assertEqual(row["evidence_grade"], "A")
            self.assertEqual(row["candidate_created_at"], "2026-04-01T09:10:11+08:00")
            self.assertEqual(row["skip_reason"], "")
            self.assertTrue(row["auto_apply_eligible"])

    def test_filename_date_falls_back_to_manual_review(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            task_dir = repo / "任务规划" / "子级04" / "任务"
            task_dir.mkdir(parents=True, exist_ok=True)
            task_file = task_dir / "【已完成】【任务】20260402-前端样例任务.md"
            task_file.write_text("# 【已完成】【任务】20260402-前端样例任务\n", encoding="utf-8")

            payload = build_created_at_inventory(repo_root=repo, project_id="task_dashboard", project_name="task_dashboard")
            self.assertEqual(payload["summary"]["missing_created_at_total"], 1)
            row = payload["rows"][0]
            self.assertEqual(row["evidence_grade"], "C")
            self.assertEqual(row["candidate_created_at"], "2026-04-02T00:00:00+0800")
            self.assertEqual(row["skip_reason"], "manual_review_only")
            self.assertFalse(row["auto_apply_eligible"])

    def test_apply_created_at_candidates_writes_front_matter_created_at_only(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            task_dir = repo / "任务规划" / "子级04" / "任务"
            task_dir.mkdir(parents=True, exist_ok=True)
            task_file = task_dir / "【已完成】【任务】20260402-前端样例任务.md"
            task_file.write_text("# 【已完成】【任务】20260402-前端样例任务\n", encoding="utf-8")

            payload = build_created_at_inventory(repo_root=repo, project_id="task_dashboard", project_name="task_dashboard")
            result = apply_created_at_candidates(repo_root=repo, payload=payload, allowed_grades=("C",))

            self.assertEqual(result["summary"]["applied_total"], 1)
            updated = task_file.read_text(encoding="utf-8")
            self.assertTrue(updated.startswith("---\ncreated_at: 2026-04-02T00:00:00+0800\n---\n\n"))
            self.assertNotIn("\ntask_id:", updated)
            identity = extract_task_identity_from_markdown(updated)
            self.assertEqual(identity["created_at"], "2026-04-02T00:00:00+0800")


if __name__ == "__main__":
    unittest.main()
