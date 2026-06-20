import tempfile
import unittest
from pathlib import Path

import server
from task_dashboard.runtime.run_state_semantics import (
    build_session_semantics,
    classify_media_run_monitoring,
    classify_run_semantics,
)


class RunStateSemanticsTests(unittest.TestCase):
    def test_provider_transient_failure_is_not_business_failure(self) -> None:
        fields = classify_run_semantics({
            "status": "error",
            "failure_class": "provider_transient",
            "provider_error": {
                "kind": "high_demand",
                "retryable": True,
                "matched_patterns": ["high demand", "temporary errors"],
            },
            "error": "turn.failed: We're currently experiencing high demand, which may cause temporary errors.",
        })

        self.assertEqual(fields["outcome_state"], "provider_transient_failed")
        self.assertEqual(fields["error_class"], "provider_transient")
        self.assertTrue(fields["effective_for_session_health"])
        self.assertFalse(fields["effective_for_session_preview"])
        self.assertEqual(fields["failure_class"], "provider_transient")
        self.assertEqual(fields["provider_error"]["kind"], "high_demand")
        self.assertTrue(fields["provider_error"]["retryable"])
        self.assertEqual(fields["side_effect_risk"], "none")
        self.assertEqual(fields["recovery_mode"], "auto_retry")
        self.assertFalse(fields["recovery_required"])
        self.assertTrue(fields["auto_retry_eligible"])

    def test_existing_provider_outcome_is_not_downgraded_to_business(self) -> None:
        fields = classify_run_semantics({
            "status": "error",
            "outcome_state": "provider_transient_failed",
            "error_class": "provider_transient",
            "failure_class": "business",
            "provider_error": {"kind": "", "retryable": False, "matched_patterns": []},
            "error": "options: [Object], response: [Object]",
            "visible_in_channel_chat": True,
        })

        self.assertEqual(fields["outcome_state"], "provider_transient_failed")
        self.assertEqual(fields["error_class"], "provider_transient")
        self.assertEqual(fields["failure_class"], "provider_transient")
        self.assertEqual(fields["provider_error"]["kind"], "unknown")
        self.assertTrue(fields["provider_error"]["retryable"])
        self.assertEqual(fields["recovery_mode"], "manual_recovery")
        self.assertTrue(fields["recovery_required"])

    def test_session_summary_carries_provider_failure_fields(self) -> None:
        meta = {
            "id": "run-provider",
            "status": "error",
            "error": "OpenAI request failed with HTTP 429 Too Many Requests",
            "createdAt": "2026-05-15T10:00:00+08:00",
            "finishedAt": "2026-05-15T10:00:10+08:00",
        }

        summary = server._build_session_summary_from_meta(meta)
        self.assertEqual(summary["latest_run_id"], "run-provider")
        self.assertEqual(summary["failure_class"], "provider_transient")
        self.assertEqual((summary.get("provider_error") or {}).get("kind"), "rate_limit")
        self.assertTrue(bool((summary.get("provider_error") or {}).get("retryable")))
        self.assertEqual(summary["side_effect_risk"], "none")
        self.assertEqual(summary["recovery_mode"], "auto_retry")
        self.assertFalse(bool(summary["recovery_required"]))
        self.assertTrue(bool(summary["auto_retry_eligible"]))

        semantics = build_session_semantics([meta])
        run_fields = semantics["run_fields"]["run-provider"]
        self.assertEqual(run_fields["failure_class"], "provider_transient")
        self.assertEqual((run_fields.get("provider_error") or {}).get("kind"), "rate_limit")
        self.assertFalse(bool(run_fields.get("recovery_required")))
        self.assertTrue(bool(run_fields.get("auto_retry_eligible")))

    def test_session_binding_error_class_reaches_session_summaries(self) -> None:
        meta = {
            "id": "run-claude-missing",
            "status": "error",
            "error": "No conversation found with session ID abc-123",
            "createdAt": "2026-06-11T16:01:15+08:00",
            "finishedAt": "2026-06-11T16:01:18+08:00",
        }

        fields = classify_run_semantics(meta)
        self.assertEqual(fields["outcome_state"], "failed_config")
        self.assertEqual(fields["error_class"], "session_binding")
        self.assertEqual(fields["failure_class"], "business")

        latest = server._build_session_summary_from_meta(meta)
        self.assertEqual(latest["error_class"], "session_binding")

        semantics = build_session_semantics([meta])
        effective = semantics["latest_effective_run_summary"]
        self.assertEqual(effective["run_id"], "run-claude-missing")
        self.assertEqual(effective["outcome_state"], "failed_config")
        self.assertEqual(effective["error_class"], "session_binding")
        self.assertEqual(effective["failure_class"], "business")

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
