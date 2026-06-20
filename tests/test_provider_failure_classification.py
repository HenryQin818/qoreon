import os
import tempfile
import unittest
import uuid
from unittest.mock import patch

import server
from task_dashboard.runtime.provider_failure import (
    apply_run_failure_classification,
    classify_provider_error_text,
    classify_run_failure,
)


class _FakeAdapter:
    @classmethod
    def supports_model(cls) -> bool:
        return False

    @classmethod
    def build_resume_command(
        cls,
        session_id: str,
        message: str,
        output_path,
        profile_label: str = "",
        model: str = "",
        reasoning_effort: str = "",
    ) -> list[str]:
        return ["fake-cli", "resume", session_id, message, str(output_path)]


class _FakeStream:
    def __init__(self, text: str) -> None:
        self._lines = [line + "\n" for line in text.splitlines()] if text else []
        self._idx = 0

    def readline(self) -> str:
        if self._idx >= len(self._lines):
            return ""
        value = self._lines[self._idx]
        self._idx += 1
        return value

    def close(self) -> None:
        return


class _FakeProc:
    def __init__(self, stderr: str) -> None:
        self.returncode = 1
        self.stdout = _FakeStream("")
        self.stderr = _FakeStream(stderr)

    def poll(self) -> int:
        return 1

    def kill(self) -> None:
        return


class _FakeScheduler:
    def __init__(self) -> None:
        self.waiting: list[tuple[str, str, float, str]] = []

    def schedule_retry_waiting(
        self,
        run_id: str,
        session_id: str,
        due_ts: float,
        cli_type: str = "codex",
    ) -> bool:
        self.waiting.append((run_id, session_id, due_ts, cli_type))
        return True


class ProviderFailureClassificationTests(unittest.TestCase):
    def test_high_demand_temporary_error_is_provider_transient(self) -> None:
        meta = {
            "status": "error",
            "error": "turn.failed: We're currently experiencing high demand, which may cause temporary errors.",
        }

        fields = classify_run_failure(meta)

        self.assertEqual(fields["failure_class"], "provider_transient")
        self.assertEqual(fields["provider_error"]["kind"], "high_demand")
        self.assertTrue(fields["provider_error"]["retryable"])
        self.assertEqual(fields["side_effect_risk"], "none")
        self.assertEqual(fields["recovery_mode"], "auto_retry")
        self.assertFalse(fields["recovery_required"])
        self.assertTrue(fields["auto_retry_eligible"])
        self.assertEqual(fields["retry_eligibility_reason"], "provider_transient_no_side_effect_evidence")

    def test_provider_variants_are_retryable_without_marking_plain_exit_one(self) -> None:
        variants = {
            "rate_limit": "OpenAI request failed with HTTP 429 Too Many Requests",
            "model_capacity": "Gemini returned RESOURCE_EXHAUSTED: MODEL_CAPACITY_EXHAUSTED. No capacity available for model gemini-3.1-pro-preview on the server.",
            "server_error": "provider returned 503 service unavailable",
            "network_timeout": "responses_websocket request timed out",
            "network_reset": "stream disconnected before completion: error sending request for url",
        }
        for expected_kind, text in variants.items():
            with self.subTest(expected_kind=expected_kind):
                provider_error = classify_provider_error_text(text)
                self.assertEqual(provider_error["kind"], expected_kind)
                self.assertTrue(provider_error["retryable"])

        plain = classify_run_failure({"status": "error", "error": "exit=1: pytest failed"})
        self.assertEqual(plain["failure_class"], "business")
        self.assertFalse(plain["provider_error"]["retryable"])
        self.assertEqual(plain["provider_error"]["kind"], "")
        self.assertFalse(plain["auto_retry_eligible"])

    def test_interrupted_user_is_not_provider_transient(self) -> None:
        fields = classify_run_failure({"status": "error", "error": "interrupted by user"})

        self.assertEqual(fields["failure_class"], "interrupted")
        self.assertFalse(fields["provider_error"]["retryable"])
        self.assertFalse(fields["auto_retry_eligible"])

    def test_plain_business_model_capacity_text_is_not_provider_transient(self) -> None:
        fields = classify_run_failure(
            {
                "status": "error",
                "error": "业务分析失败：model capacity planning section missing required data",
            }
        )

        self.assertEqual(fields["failure_class"], "business")
        self.assertEqual(fields["provider_error"]["kind"], "")
        self.assertFalse(fields["provider_error"]["retryable"])
        self.assertFalse(fields["auto_retry_eligible"])

    def test_infra_restart_error_is_classified_as_interrupted(self) -> None:
        fields = classify_run_failure(
            {
                "status": "error",
                "error": "run interrupted (server restarted or process exited)",
            }
        )

        self.assertEqual(fields["failure_class"], "interrupted")
        self.assertFalse(fields["provider_error"]["retryable"])
        self.assertEqual(fields["provider_error"]["kind"], "")

    def test_side_effect_possible_requires_manual_recovery_for_provider_transient(self) -> None:
        meta = {
            "status": "error",
            "error": "HTTP 500 from provider",
            "partialPreview": "已写入方案草案，随后 provider 失败",
        }

        fields = classify_run_failure(meta)

        self.assertEqual(fields["failure_class"], "provider_transient")
        self.assertEqual(fields["side_effect_risk"], "possible")
        self.assertEqual(fields["recovery_mode"], "manual_recovery")
        self.assertTrue(fields["recovery_required"])
        self.assertFalse(fields["auto_retry_eligible"])
        self.assertEqual(fields["retry_eligibility_reason"], "side_effect_risk_possible")

    def test_confirmed_side_effect_blocks_auto_retry_for_provider_transient(self) -> None:
        fields = classify_run_failure(
            {
                "status": "error",
                "error": "HTTP 503 from provider",
            },
            log_text="announce_run_id=20260515-demo; target_session_id=sid; visible_in_channel_chat=true",
        )

        self.assertEqual(fields["failure_class"], "provider_transient")
        self.assertEqual(fields["side_effect_risk"], "confirmed")
        self.assertEqual(fields["recovery_mode"], "manual_recovery")
        self.assertTrue(fields["recovery_required"])
        self.assertFalse(fields["auto_retry_eligible"])
        self.assertEqual(fields["retry_eligibility_reason"], "side_effect_risk_confirmed")

    def test_visible_channel_message_blocks_auto_retry_for_provider_transient(self) -> None:
        fields = classify_run_failure(
            {
                "status": "error",
                "error": "HTTP 503 from provider",
                "visible_in_channel_chat": True,
            }
        )

        self.assertEqual(fields["failure_class"], "provider_transient")
        self.assertEqual(fields["side_effect_risk"], "confirmed")
        self.assertEqual(fields["recovery_mode"], "manual_recovery")
        self.assertFalse(fields["auto_retry_eligible"])

    def test_destructive_or_deploy_markers_block_auto_retry(self) -> None:
        previews = (
            "deployed service and then provider returned 504 gateway timeout",
            "deleted temporary artifacts before upstream unavailable",
            "archived hot run before HTTP 500",
            "apply_patch updated server.py before stream disconnected before completion",
        )
        for preview in previews:
            with self.subTest(preview=preview):
                fields = classify_run_failure(
                    {
                        "status": "error",
                        "error": "provider returned 504 gateway timeout",
                        "partialPreview": preview,
                    }
                )
                self.assertEqual(fields["failure_class"], "provider_transient")
                self.assertEqual(fields["side_effect_risk"], "possible")
                self.assertEqual(fields["recovery_mode"], "manual_recovery")
                self.assertFalse(fields["auto_retry_eligible"])

    @patch.dict(
        os.environ,
        {"CCB_NETWORK_RETRY_MAX": "0", "CCB_PROVIDER_RETRY_DELAY_S": "60", "CCB_PROVIDER_RETRY_MAX": "2"},
        clear=False,
    )
    def test_run_cli_exec_schedules_low_risk_provider_auto_retry(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(runs_dir=server.Path(td))
            sid = f"s1-{uuid.uuid4().hex[:8]}"
            source_sid = str(uuid.uuid4())
            source_ref = {"project_id": "p", "channel_name": "source", "session_id": source_sid}
            callback_to = {"channel_name": "source", "session_id": source_sid}
            run = store.create_run(
                "p",
                "c",
                sid,
                "m1",
                extra_meta={
                    "source_ref": source_ref,
                    "callback_to": callback_to,
                    "environment": "stable",
                    "workdir": "/tmp/work",
                },
            )
            run_id = str(run["id"])
            sched = _FakeScheduler()

            with patch.object(server, "get_adapter", return_value=_FakeAdapter):
                with patch.object(
                    server.subprocess,
                    "Popen",
                    return_value=_FakeProc(
                        "turn.failed: We're currently experiencing high demand, which may cause temporary errors."
                    ),
                ):
                    server.run_cli_exec(store, run_id, timeout_s=30, cli_type="codex", scheduler=sched)

            meta = store.load_meta(run_id) or {}
            self.assertEqual(meta.get("status"), "error")
            self.assertEqual(meta.get("failure_class"), "provider_transient")
            self.assertEqual((meta.get("provider_error") or {}).get("kind"), "high_demand")
            self.assertTrue(bool((meta.get("provider_error") or {}).get("retryable")))
            self.assertEqual(meta.get("side_effect_risk"), "none")
            self.assertEqual(meta.get("recovery_mode"), "auto_retry")
            self.assertFalse(bool(meta.get("recovery_required")))
            self.assertTrue(bool(meta.get("auto_retry_eligible")))
            self.assertEqual(meta.get("retry_eligibility_reason"), "provider_transient_no_side_effect_evidence")
            self.assertFalse(str(meta.get("networkResumeRunId") or ""))
            retry_id = str(meta.get("providerRetryRunId") or "")
            self.assertTrue(retry_id)
            self.assertEqual(meta.get("superseded_by"), retry_id)
            self.assertEqual(meta.get("superseded_by_run_id"), retry_id)

            retry_meta = store.load_meta(retry_id) or {}
            self.assertEqual(retry_meta.get("status"), "retry_waiting")
            self.assertEqual(retry_meta.get("retry_of"), run_id)
            self.assertEqual(retry_meta.get("retryOf"), run_id)
            self.assertEqual(retry_meta.get("retry_attempt"), 1)
            self.assertEqual(retry_meta.get("retry_reason"), "provider_high_demand")
            self.assertEqual(retry_meta.get("retryKind"), "provider_transient_auto_retry")
            self.assertEqual(retry_meta.get("side_effect_risk"), "none")
            self.assertEqual(retry_meta.get("recovery_mode"), "auto_retry")
            self.assertFalse(bool(retry_meta.get("visible_in_channel_chat")))
            self.assertEqual(retry_meta.get("source_ref"), source_ref)
            self.assertEqual(retry_meta.get("callback_to"), callback_to)
            self.assertEqual(len(sched.waiting), 1)
            self.assertEqual(sched.waiting[0][0], retry_id)

            msg_path = (retry_meta.get("paths") or {}).get("msg")
            self.assertTrue(msg_path)
            self.assertEqual(server.Path(msg_path).read_text(encoding="utf-8"), "m1")

    @patch.dict(
        os.environ,
        {"CCB_NETWORK_RETRY_MAX": "0", "CCB_PROVIDER_RETRY_DELAY_S": "60", "CCB_PROVIDER_RETRY_MAX": "2"},
        clear=False,
    )
    def test_visible_channel_run_does_not_schedule_provider_auto_retry(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(runs_dir=server.Path(td))
            sid = f"s1-{uuid.uuid4().hex[:8]}"
            run = store.create_run("p", "c", sid, "m1", extra_meta={"visible_in_channel_chat": True})
            run_id = str(run["id"])
            sched = _FakeScheduler()

            with patch.object(server, "get_adapter", return_value=_FakeAdapter):
                with patch.object(server.subprocess, "Popen", return_value=_FakeProc("provider returned HTTP 503")):
                    server.run_cli_exec(store, run_id, timeout_s=30, cli_type="codex", scheduler=sched)

            meta = store.load_meta(run_id) or {}
            self.assertEqual(meta.get("failure_class"), "provider_transient")
            self.assertEqual(meta.get("side_effect_risk"), "confirmed")
            self.assertEqual(meta.get("recovery_mode"), "manual_recovery")
            self.assertFalse(bool(meta.get("auto_retry_eligible")))
            self.assertFalse(str(meta.get("providerRetryRunId") or ""))
            self.assertEqual(sched.waiting, [])

    @patch.dict(
        os.environ,
        {"CCB_NETWORK_RETRY_MAX": "0", "CCB_PROVIDER_RETRY_DELAY_S": "60", "CCB_PROVIDER_RETRY_MAX": "2"},
        clear=False,
    )
    def test_provider_auto_retry_stops_after_two_attempts(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(runs_dir=server.Path(td))
            sid = f"s1-{uuid.uuid4().hex[:8]}"
            run = store.create_run(
                "p",
                "c",
                sid,
                "m1",
                extra_meta={
                    "retry_of": "root-run",
                    "retry_attempt": 2,
                    "trigger_type": "provider_auto_retry",
                },
            )
            run_id = str(run["id"])
            # create_run sanitizes unknown retry fields, so persist retry fields as execution metadata.
            meta = store.load_meta(run_id) or {}
            meta["retry_of"] = "root-run"
            meta["retry_attempt"] = 2
            meta["trigger_type"] = "provider_auto_retry"
            store.save_meta(run_id, meta)
            sched = _FakeScheduler()

            with patch.object(server, "get_adapter", return_value=_FakeAdapter):
                with patch.object(server.subprocess, "Popen", return_value=_FakeProc("provider returned HTTP 503")):
                    server.run_cli_exec(store, run_id, timeout_s=30, cli_type="codex", scheduler=sched)

            meta = store.load_meta(run_id) or {}
            self.assertEqual(meta.get("failure_class"), "provider_transient")
            self.assertTrue(bool(meta.get("retry_exhausted")))
            self.assertEqual(meta.get("retry_eligibility_reason"), "retry_exhausted")
            self.assertEqual(meta.get("recovery_mode"), "manual_recovery")
            self.assertTrue(bool(meta.get("recovery_required")))
            self.assertFalse(bool(meta.get("auto_retry_eligible")))
            self.assertFalse(str(meta.get("providerRetryRunId") or ""))
            self.assertEqual(sched.waiting, [])

    def test_apply_run_failure_classification_mutates_meta_additively(self) -> None:
        meta = {"status": "error", "error": "provider returned 502 bad gateway", "existing": "kept"}

        changed = apply_run_failure_classification(meta)

        self.assertTrue(changed)
        self.assertEqual(meta["existing"], "kept")
        self.assertEqual(meta["failure_class"], "provider_transient")
        self.assertEqual(meta["provider_error"]["kind"], "server_error")
        self.assertEqual(meta["recovery_mode"], "auto_retry")


if __name__ == "__main__":
    unittest.main()
