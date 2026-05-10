import tempfile
import unittest
from pathlib import Path

import server
from task_dashboard.runtime.run_state_semantics import classify_media_run_monitoring


class RunStateSemanticsTests(unittest.TestCase):
    def test_media_run_monitoring_marks_running_imagegen_as_pending(self) -> None:
        meta = {
            "status": "running",
            "cliType": "codex",
            "skills_used": ["imagegen"],
            "processRows": [
                {
                    "text": "Image Gen 工具已启动，正在生成图片。",
                    "at": "2026-05-08T10:00:00+0800",
                }
            ],
            "lastProgressAt": "2026-05-08T10:00:00+0800",
        }

        fields = classify_media_run_monitoring(meta)

        self.assertTrue(fields["media_run_candidate"])
        self.assertTrue(fields["media_result_pending"])
        self.assertEqual(fields["media_monitor_status"], "media_result_pending")
        self.assertEqual(fields["media_false_stop_exempt_reason"], "media_generation_in_progress")
        self.assertIn("imagegen_skill", fields["media_monitor_evidence"])

    def test_media_run_monitoring_accepts_generated_attachment_as_result(self) -> None:
        meta = {
            "status": "done",
            "cliType": "codex",
            "lastPreview": "",
            "generated_media_count": 1,
            "generated_media_summary": "已生成1张图片",
            "attachments": [
                {
                    "filename": "ig_demo.png",
                    "source": "generated",
                    "generatedBy": "codex_imagegen",
                    "attachment_role": "assistant",
                }
            ],
        }

        fields = classify_media_run_monitoring(meta)

        self.assertTrue(fields["media_run_candidate"])
        self.assertFalse(fields["media_result_pending"])
        self.assertTrue(fields["media_terminal_result_present"])
        self.assertEqual(fields["media_monitor_status"], "generated_media_ready")
        self.assertEqual(fields["media_false_stop_exempt_reason"], "generated_media_result_present")

    def test_media_run_monitoring_downgrades_metadata_without_attachment(self) -> None:
        meta = {
            "status": "done",
            "cliType": "codex",
            "generated_media_count": 1,
            "generated_media_summary": "已生成1张图片",
            "attachments": [],
        }

        fields = classify_media_run_monitoring(meta)

        self.assertTrue(fields["media_run_candidate"])
        self.assertTrue(fields["media_result_pending"])
        self.assertTrue(fields["media_terminal_result_present"])
        self.assertEqual(fields["media_monitor_status"], "generated_media_metadata_pending_attachment")
        self.assertEqual(fields["media_false_stop_exempt_reason"], "generated_media_metadata_present")

    def test_media_run_monitoring_keeps_terminal_error_failed_without_result(self) -> None:
        meta = {
            "status": "error",
            "cliType": "codex",
            "skills_used": ["imagegen"],
            "partialPreview": "准备使用 imagegen 生成设计图。",
            "error": "exit=1",
        }

        fields = classify_media_run_monitoring(meta)

        self.assertTrue(fields["media_run_candidate"])
        self.assertFalse(fields["media_result_pending"])
        self.assertFalse(fields["media_false_stop_exempt"])
        self.assertEqual(fields["media_monitor_status"], "media_generation_failed")

    def test_media_run_monitoring_accepts_output_imagegen_fallback_signal(self) -> None:
        meta = {
            "status": "done",
            "cliType": "codex",
            "processRows": [
                {
                    "text": "已导出本地 fallback 产物 output/imagegen/result.png，等待后端回收附件。",
                    "at": "2026-05-08T10:20:00+0800",
                }
            ],
        }

        fields = classify_media_run_monitoring(meta)

        self.assertTrue(fields["media_run_candidate"])
        self.assertTrue(fields["media_result_pending"])
        self.assertEqual(fields["media_monitor_status"], "media_result_missing")
        self.assertIn("output_imagegen_fallback", fields["media_monitor_evidence"])

    def test_media_run_monitoring_does_not_touch_plain_text_run(self) -> None:
        meta = {
            "status": "running",
            "cliType": "codex",
            "partialPreview": "正在整理任务报告。",
            "processRows": [{"text": "读取任务文件。"}],
        }

        fields = classify_media_run_monitoring(meta)

        self.assertFalse(fields["media_run_candidate"])
        self.assertFalse(fields["media_result_pending"])
        self.assertEqual(fields["media_monitor_status"], "")

    def test_build_run_observability_fields_classifies_permission_and_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            run_store = server.RunStore(Path(td) / ".runtime" / "stable" / ".runs")

            source_run = run_store.create_run(
                project_id="task_dashboard",
                channel_name="子级03-多CLI适配器（codex-claude-opencode）",
                session_id="ses_demo_recovery",
                message="source run",
                cli_type="claude",
            )
            source_meta = run_store.load_meta(source_run["id"]) or {}
            source_meta["status"] = "error"
            source_meta["createdAt"] = "2026-04-01T10:00:00+08:00"
            source_meta["finishedAt"] = "2026-04-01T10:00:10+08:00"
            source_meta["error"] = "run interrupted (server restarted or process exited)"
            run_store.save_meta(source_run["id"], source_meta)

            recovery_run = run_store.create_run(
                project_id="task_dashboard",
                channel_name="子级03-多CLI适配器（codex-claude-opencode）",
                session_id="ses_demo_recovery",
                message="recovery run",
                cli_type="claude",
                sender_type="system",
                sender_name="系统",
                extra_meta={
                    "trigger_type": "restart_recovery_summary",
                    "restartRecoveryOf": source_run["id"],
                },
            )
            recovery_meta = run_store.load_meta(recovery_run["id"]) or {}
            recovery_meta["status"] = "done"
            recovery_meta["createdAt"] = "2026-04-01T10:01:00+08:00"
            recovery_meta["finishedAt"] = "2026-04-01T10:01:05+08:00"
            recovery_meta["lastPreview"] = "系统恢复摘要"
            run_store.save_meta(recovery_run["id"], recovery_meta)

            source_meta["restartRecoveryRunId"] = recovery_run["id"]
            run_store.save_meta(source_run["id"], source_meta)

            blocked_run = run_store.create_run(
                project_id="task_dashboard",
                channel_name="子级03-多CLI适配器（codex-claude-opencode）",
                session_id="ses_demo_blocked",
                message="blocked run",
                cli_type="opencode",
            )
            blocked_meta = run_store.load_meta(blocked_run["id"]) or {}
            blocked_meta["status"] = "error"
            blocked_meta["createdAt"] = "2026-04-01T11:00:00+08:00"
            blocked_meta["finishedAt"] = "2026-04-01T11:00:10+08:00"
            blocked_meta["error"] = "external_directory permission denied: /tmp/outside"
            run_store.save_meta(blocked_run["id"], blocked_meta)

            source_fields = server._build_run_observability_fields(run_store, source_meta, infer_blocked=False)
            recovery_fields = server._build_run_observability_fields(run_store, recovery_meta, infer_blocked=False)
            blocked_fields = server._build_run_observability_fields(run_store, blocked_meta, infer_blocked=False)

            self.assertEqual(source_fields["outcome_state"], "interrupted_infra")
            self.assertEqual(source_fields["error_class"], "infra_restart")
            self.assertFalse(source_fields["effective_for_session_health"])
            self.assertEqual(source_fields["superseded_by_run_id"], recovery_run["id"])

            self.assertEqual(recovery_fields["outcome_state"], "recovered_notice")
            self.assertEqual(recovery_fields["error_class"], "infra_restart_recovered")
            self.assertTrue(recovery_fields["effective_for_session_health"])
            self.assertFalse(recovery_fields["effective_for_session_preview"])
            self.assertEqual(recovery_fields["recovery_of_run_id"], source_run["id"])

            self.assertEqual(blocked_fields["outcome_state"], "failed_config")
            self.assertEqual(blocked_fields["error_class"], "workspace_permission")
            self.assertTrue(blocked_fields["effective_for_session_health"])
            self.assertFalse(blocked_fields["effective_for_session_preview"])


if __name__ == "__main__":
    unittest.main()
