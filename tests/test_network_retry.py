import os
import tempfile
import unittest
import uuid
from unittest.mock import patch

import server
from task_dashboard.runtime import execution_runtime
from task_dashboard.runtime.execution_retry import apply_profile_fallback_retry_result


class TestNetworkRetryHelpers(unittest.TestCase):
    def test_is_transient_network_error_true(self) -> None:
        msg = (
            "ERROR rmcp::transport::worker: worker quit with fatal: Transport channel closed; "
            "stream disconnected before completion: error sending request for url"
        )
        self.assertTrue(server._is_transient_network_error(msg))

    def test_is_transient_network_error_websocket_timeout(self) -> None:
        msg = (
            "ERROR codex_api::endpoint::responses_websocket: failed to connect to websocket: "
            "IO error: Operation timed out (os error 60)"
        )
        self.assertTrue(server._is_transient_network_error(msg))

    def test_is_transient_network_error_false(self) -> None:
        msg = "invalid session id format"
        self.assertFalse(server._is_transient_network_error(msg))

    def test_error_hint_network(self) -> None:
        msg = "stream disconnected before completion: error sending request for url"
        hint = server._error_hint(msg)
        self.assertIn("自动重试", hint)

    def test_error_hint_missing_cli_bin_guides_to_system_settings(self) -> None:
        msg = "[Errno 2] No such file or directory: '/tmp/qoreon-demo/.npm-global/bin/codex'"
        hint = server._error_hint(msg)
        self.assertIn("codex 启动路径无效", hint)
        self.assertIn("系统设置", hint)
        self.assertIn("CLI 联通", hint)
        self.assertIn("自动发现", hint)

    @patch.dict(os.environ, {"CCB_NETWORK_RETRY_MAX": "3"}, clear=False)
    def test_default_network_retry_max_env(self) -> None:
        self.assertEqual(server._default_network_retry_max(), 3)

    @patch.dict(os.environ, {"CCB_NETWORK_RETRY_MAX": "99"}, clear=False)
    def test_default_network_retry_max_cap(self) -> None:
        self.assertEqual(server._default_network_retry_max(), 5)

    @patch.dict(os.environ, {"CCB_NETWORK_RETRY_BASE_S": "2.5"}, clear=False)
    def test_default_network_retry_base_env(self) -> None:
        self.assertAlmostEqual(server._default_network_retry_base_s(), 2.5, places=4)

    @patch.dict(os.environ, {"CCB_NETWORK_RESUME_DELAY_S": "90"}, clear=False)
    def test_default_network_resume_delay_env(self) -> None:
        self.assertEqual(server._default_network_resume_delay_s(), 90)

    @patch.dict(os.environ, {"CCB_NETWORK_RESUME_MESSAGE": "网络断开，请继续"}, clear=False)
    def test_default_network_resume_message_env(self) -> None:
        self.assertEqual(server._default_network_resume_message(), "网络断开，请继续")

    @patch.dict(os.environ, {"CCB_NO_PROGRESS_TIMEOUT_S": "180"}, clear=False)
    def test_default_no_progress_timeout_env(self) -> None:
        self.assertEqual(server._default_run_no_progress_timeout_s(), 180)

    @patch.dict(os.environ, {"CCB_NO_PROGRESS_TIMEOUT_S": "0"}, clear=False)
    def test_default_no_progress_timeout_disable(self) -> None:
        self.assertIsNone(server._default_run_no_progress_timeout_s())

    def test_default_no_progress_timeout_claude_disabled_by_default(self) -> None:
        self.assertIsNone(server._default_run_no_progress_timeout_s(cli_type="claude"))

    def test_default_no_progress_timeout_codex_keeps_default(self) -> None:
        self.assertEqual(server._default_run_no_progress_timeout_s(cli_type="codex"), 30 * 60)

    def test_profile_fallback_retry_returncode_zero_marks_done(self) -> None:
        class _Retry:
            returncode = 0
            stderr = ""

        meta = {"status": "error", "error": "exit=0"}
        result = apply_profile_fallback_retry_result(
            meta,
            _Retry(),
            safe_text=server._safe_text,
            is_auth_error=server._is_auth_error,
            is_transient_network_error=server._is_transient_network_error,
        )
        self.assertEqual(meta["status"], "done")
        self.assertEqual(meta["error"], "")
        self.assertFalse(result["detected_auth_error"])
        self.assertFalse(result["network_failed_persist"])

    @patch.dict(
        os.environ,
        {
            "CCB_NETWORK_RETRY_MAX": "1",
            "CCB_NETWORK_RETRY_BASE_S": "0",
            "CCB_NETWORK_RESUME_DELAY_S": "60",
        },
        clear=False,
    )
    def test_network_failure_schedules_retry_waiting_run(self) -> None:
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

        class _FakeStream:
            def __init__(self, text: str) -> None:
                self._lines = [line + "\n" for line in text.splitlines()] if text else []
                self._idx = 0

            def readline(self) -> str:
                if self._idx >= len(self._lines):
                    return ""
                s = self._lines[self._idx]
                self._idx += 1
                return s

            def close(self) -> None:
                return

        class _FakeProc:
            def __init__(self) -> None:
                self.returncode = 1
                self.stdout = _FakeStream("")
                self.stderr = _FakeStream("stream disconnected before completion")

            def poll(self) -> int:
                return 1

            def kill(self) -> None:
                return

        with tempfile.TemporaryDirectory() as td:
            runs_dir = server.Path(td)
            store = server.RunStore(runs_dir=runs_dir)
            sid = f"s1-{uuid.uuid4().hex[:8]}"
            run = store.create_run("p", "c", sid, "m1")
            run_id = str(run["id"])
            sched = _FakeScheduler()

            with patch.object(server, "get_adapter", return_value=_FakeAdapter):
                with patch.object(server.subprocess, "Popen", return_value=_FakeProc()):
                    with patch.object(
                        server.subprocess,
                        "run",
                        return_value=server.subprocess.CompletedProcess(
                            args=["fake-cli"],
                            returncode=1,
                            stdout="",
                            stderr="stream disconnected before completion",
                        ),
                    ):
                        server.run_cli_exec(store, run_id, timeout_s=30, cli_type="codex", scheduler=sched)

            source_meta = store.load_meta(run_id) or {}
            self.assertEqual(source_meta.get("status"), "error")
            retry_id = str(source_meta.get("networkResumeRunId") or "")
            self.assertTrue(retry_id)
            self.assertTrue(str(source_meta.get("networkResumeScheduledAt") or ""))

            retry_meta = store.load_meta(retry_id) or {}
            self.assertEqual(retry_meta.get("status"), "retry_waiting")
            self.assertTrue(bool(retry_meta.get("retryCancelable")))
            self.assertEqual(str(retry_meta.get("retryOf") or ""), run_id)
            self.assertEqual(len(sched.waiting), 1)
            self.assertEqual(sched.waiting[0][0], retry_id)

    def test_live_auth_warning_does_not_force_stop_when_cli_succeeds(self) -> None:
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

        class _ImmediateThread:
            def __init__(self, target=None, args=(), daemon=None):
                self._target = target
                self._args = args

            def start(self) -> None:
                if self._target:
                    self._target(*self._args)

            def join(self, timeout=None) -> None:
                return

        class _FakeStream:
            def __init__(self, lines: list[str]) -> None:
                self._lines = [line + "\n" for line in lines]
                self._idx = 0

            def readline(self) -> str:
                if self._idx >= len(self._lines):
                    return ""
                s = self._lines[self._idx]
                self._idx += 1
                return s

            def close(self) -> None:
                return

        class _FakeProc:
            def __init__(self) -> None:
                self.returncode = 0
                self.stdout = _FakeStream(
                    [
                        '{"type":"thread.started","thread_id":"s1"}',
                        '{"type":"turn.started"}',
                        '{"type":"agent_message","text":"ok"}',
                    ]
                )
                self.stderr = _FakeStream(
                    [
                        "ERROR rmcp::transport::worker: worker quit with fatal: Transport channel closed, "
                        "when AuthRequired(AuthRequiredError { error_description=\"Missing or invalid access token\" })"
                    ]
                )
                self.terminate_called = 0

            def poll(self):
                return self.returncode

            def terminate(self) -> None:
                self.terminate_called += 1
                self.returncode = 1

            def kill(self) -> None:
                self.returncode = 1

        with tempfile.TemporaryDirectory() as td:
            runs_dir = server.Path(td)
            store = server.RunStore(runs_dir=runs_dir)
            run = store.create_run("p", "c", "s1", "m1")
            run_id = str(run["id"])
            fake_proc = _FakeProc()

            with patch.object(server, "get_adapter", return_value=_FakeAdapter):
                with patch.object(server.subprocess, "Popen", return_value=fake_proc):
                    with patch.object(server.threading, "Thread", _ImmediateThread):
                        with patch.object(server.time, "sleep", return_value=None):
                            server.run_cli_exec(store, run_id, timeout_s=10, cli_type="codex", scheduler=None)

            meta = store.load_meta(run_id) or {}
            self.assertEqual(meta.get("status"), "done")
            self.assertEqual(str(meta.get("error") or ""), "")
            self.assertNotEqual(meta.get("errorType"), "auth_error")
            self.assertEqual(fake_proc.terminate_called, 0)

    @patch.dict(os.environ, {"CCB_NO_PROGRESS_TIMEOUT_S": "5"}, clear=False)
    def test_no_progress_timeout_marks_error(self) -> None:
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
            def readline(self) -> str:
                return ""

            def close(self) -> None:
                return

        class _FakeProc:
            def __init__(self) -> None:
                self.returncode = None
                self.stdout = _FakeStream()
                self.stderr = _FakeStream()
                self.terminate_called = 0
                self.kill_called = 0

            def poll(self):  # type: ignore[no-untyped-def]
                return self.returncode

            def terminate(self) -> None:
                self.terminate_called += 1

            def kill(self) -> None:
                self.kill_called += 1
                self.returncode = -9

        with tempfile.TemporaryDirectory() as td:
            runs_dir = server.Path(td)
            store = server.RunStore(runs_dir=runs_dir)
            run = store.create_run("p", "c", "s1", "m1")
            run_id = str(run["id"])
            fake_proc = _FakeProc()
            fake_clock = {"t": 1000.0}

            def _fake_time() -> float:
                return float(fake_clock["t"])

            def _fake_sleep(seconds: float) -> None:
                fake_clock["t"] = float(fake_clock["t"]) + max(0.0, float(seconds or 0.0))

            with patch.object(server, "get_adapter", return_value=_FakeAdapter):
                with patch.object(server.subprocess, "Popen", return_value=fake_proc):
                    with patch.object(server.time, "time", side_effect=_fake_time):
                        with patch.object(server.time, "sleep", side_effect=_fake_sleep):
                            server.run_cli_exec(store, run_id, timeout_s=60, cli_type="codex", scheduler=None)

            meta = store.load_meta(run_id) or {}
            self.assertEqual(meta.get("status"), "error")
            self.assertIn("timeout>no_progress>5s", str(meta.get("error") or ""))
            self.assertGreaterEqual(fake_proc.terminate_called, 1)
            self.assertGreaterEqual(fake_proc.kill_called, 1)

    def test_run_model_takes_priority_over_session_model(self) -> None:
        class _FakeAdapter:
            seen_models: list[str] = []

            @classmethod
            def supports_model(cls) -> bool:
                return True

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
                cls.seen_models.append(str(model or ""))
                return ["fake-cli", "resume", session_id, message, str(output_path)]

        class _FakeStream:
            def readline(self) -> str:
                return ""

            def close(self) -> None:
                return

        class _FakeProc:
            def __init__(self) -> None:
                self.returncode = 0
                self.stdout = _FakeStream()
                self.stderr = _FakeStream()

            def poll(self) -> int:
                return 0

            def kill(self) -> None:
                return

        with tempfile.TemporaryDirectory() as td:
            base = server.Path(td)
            store = server.RunStore(runs_dir=base / ".runs")
            session_store = server.SessionStore(base_dir=base)
            sid = "11111111-1111-1111-1111-111111111111"
            session_store.create_session("p", "c", session_id=sid, model="codex-spark")
            run = store.create_run("p", "c", sid, "m1", model="codex-pro")
            run_id = str(run["id"])

            with patch.object(server, "get_adapter", return_value=_FakeAdapter):
                with patch.object(server.subprocess, "Popen", return_value=_FakeProc()):
                    server.run_cli_exec(store, run_id, timeout_s=10, cli_type="codex", scheduler=None)

            self.assertTrue(_FakeAdapter.seen_models)
            self.assertEqual(_FakeAdapter.seen_models[-1], "codex-pro")

    def test_session_model_is_used_when_run_model_missing(self) -> None:
        class _FakeAdapter:
            seen_models: list[str] = []

            @classmethod
            def supports_model(cls) -> bool:
                return True

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
                cls.seen_models.append(str(model or ""))
                return ["fake-cli", "resume", session_id, message, str(output_path)]

        class _FakeStream:
            def readline(self) -> str:
                return ""

            def close(self) -> None:
                return

        class _FakeProc:
            def __init__(self) -> None:
                self.returncode = 0
                self.stdout = _FakeStream()
                self.stderr = _FakeStream()

            def poll(self) -> int:
                return 0

            def kill(self) -> None:
                return

        with tempfile.TemporaryDirectory() as td:
            base = server.Path(td)
            store = server.RunStore(runs_dir=base / ".runs")
            session_store = server.SessionStore(base_dir=base)
            sid = "11111111-1111-1111-1111-111111111111"
            session_store.create_session("p", "c", session_id=sid, model="codex-spark")
            run = store.create_run("p", "c", sid, "m1")
            run_id = str(run["id"])

            with patch.object(server, "get_adapter", return_value=_FakeAdapter):
                with patch.object(server.subprocess, "Popen", return_value=_FakeProc()):
                    server.run_cli_exec(store, run_id, timeout_s=10, cli_type="codex", scheduler=None)

            self.assertTrue(_FakeAdapter.seen_models)
            self.assertEqual(_FakeAdapter.seen_models[-1], "codex-spark")

    def test_primary_channel_model_is_used_when_session_model_missing(self) -> None:
        class _FakeAdapter:
            seen_models: list[str] = []

            @classmethod
            def supports_model(cls) -> bool:
                return True

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
                cls.seen_models.append(str(model or ""))
                return ["fake-cli", "resume", session_id, message, str(output_path)]

        class _FakeStream:
            def readline(self) -> str:
                return ""

            def close(self) -> None:
                return

        class _FakeProc:
            def __init__(self) -> None:
                self.returncode = 0
                self.stdout = _FakeStream()
                self.stderr = _FakeStream()

            def poll(self) -> int:
                return 0

            def kill(self) -> None:
                return

        with tempfile.TemporaryDirectory() as td:
            base = server.Path(td)
            store = server.RunStore(runs_dir=base / ".runs")
            sid = "11111111-1111-1111-1111-111111111111"
            run = store.create_run("p", "c", sid, "m1")
            run_id = str(run["id"])

            with patch.object(server, "get_adapter", return_value=_FakeAdapter):
                with patch.object(server, "_project_channel_model", return_value="gpt-5.3-codex"):
                    with patch.object(server.subprocess, "Popen", return_value=_FakeProc()):
                        server.run_cli_exec(store, run_id, timeout_s=10, cli_type="codex", scheduler=None)

            self.assertTrue(_FakeAdapter.seen_models)
            self.assertEqual(_FakeAdapter.seen_models[-1], "gpt-5.3-codex")

    def test_run_reasoning_takes_priority_over_session_and_channel(self) -> None:
        class _FakeAdapter:
            seen_reasoning: list[str] = []

            @classmethod
            def supports_model(cls) -> bool:
                return True

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
                cls.seen_reasoning.append(str(reasoning_effort or ""))
                return ["fake-cli", "resume", session_id, message, str(output_path)]

        class _FakeStream:
            def readline(self) -> str:
                return ""

            def close(self) -> None:
                return

        class _FakeProc:
            def __init__(self) -> None:
                self.returncode = 0
                self.stdout = _FakeStream()
                self.stderr = _FakeStream()

            def poll(self) -> int:
                return 0

            def kill(self) -> None:
                return

        with tempfile.TemporaryDirectory() as td:
            base = server.Path(td)
            store = server.RunStore(runs_dir=base / ".runs")
            session_store = server.SessionStore(base_dir=base)
            sid = "33333333-3333-3333-3333-333333333333"
            session_store.create_session("p", "c", session_id=sid, model="gpt-5.3-codex", reasoning_effort="low")
            run = store.create_run("p", "c", sid, "m1", model="gpt-5.3-codex", reasoning_effort="high")
            run_id = str(run["id"])

            with patch.object(server, "get_adapter", return_value=_FakeAdapter):
                with patch.object(server, "_project_channel_reasoning_effort", return_value="extra_high"):
                    with patch.object(server.subprocess, "Popen", return_value=_FakeProc()):
                        server.run_cli_exec(store, run_id, timeout_s=10, cli_type="codex", scheduler=None)

            self.assertTrue(_FakeAdapter.seen_reasoning)
            self.assertEqual(_FakeAdapter.seen_reasoning[-1], "high")

    def test_channel_reasoning_is_used_when_run_and_session_missing(self) -> None:
        class _FakeAdapter:
            seen_reasoning: list[str] = []

            @classmethod
            def supports_model(cls) -> bool:
                return True

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
                cls.seen_reasoning.append(str(reasoning_effort or ""))
                return ["fake-cli", "resume", session_id, message, str(output_path)]

        class _FakeStream:
            def readline(self) -> str:
                return ""

            def close(self) -> None:
                return

        class _FakeProc:
            def __init__(self) -> None:
                self.returncode = 0
                self.stdout = _FakeStream()
                self.stderr = _FakeStream()

            def poll(self) -> int:
                return 0

            def kill(self) -> None:
                return

        with tempfile.TemporaryDirectory() as td:
            base = server.Path(td)
            store = server.RunStore(runs_dir=base / ".runs")
            sid = "44444444-4444-4444-4444-444444444444"
            run = store.create_run("p", "c", sid, "m1")
            run_id = str(run["id"])

            with patch.object(server, "get_adapter", return_value=_FakeAdapter):
                with patch.object(server, "_project_channel_reasoning_effort", return_value="extra_high"):
                    with patch.object(server.subprocess, "Popen", return_value=_FakeProc()):
                        server.run_cli_exec(store, run_id, timeout_s=10, cli_type="codex", scheduler=None)

            self.assertTrue(_FakeAdapter.seen_reasoning)
            self.assertEqual(_FakeAdapter.seen_reasoning[-1], "extra_high")

    @patch.dict(os.environ, {"CCB_PROFILE_NOT_FOUND_SUPPRESS_S": "3600"}, clear=False)
    def test_profile_not_found_recently_skips_profile_flag(self) -> None:
        class _FakeAdapter:
            seen_cmds: list[list[str]] = []

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
                cmd = ["fake-cli", "resume", session_id, message, str(output_path)]
                if profile_label:
                    cmd.extend(["-p", profile_label])
                cls.seen_cmds.append(list(cmd))
                return cmd

        class _FakeStream:
            def readline(self) -> str:
                return ""

            def close(self) -> None:
                return

        class _FakeProc:
            def __init__(self) -> None:
                self.returncode = 0
                self.stdout = _FakeStream()
                self.stderr = _FakeStream()

            def poll(self) -> int:
                return 0

            def kill(self) -> None:
                return

        with tempfile.TemporaryDirectory() as td:
            runs_dir = server.Path(td)
            store = server.RunStore(runs_dir=runs_dir)
            run = store.create_run("p", "c", "11111111-1111-1111-1111-111111111111", "m1", profile_label="ccb")
            run_id = str(run["id"])
            server._record_profile_not_found("codex", "ccb")

            with patch.object(server, "get_adapter", return_value=_FakeAdapter):
                with patch.object(server.subprocess, "Popen", return_value=_FakeProc()):
                    server.run_cli_exec(store, run_id, timeout_s=10, cli_type="codex", scheduler=None)

        self.assertGreaterEqual(len(_FakeAdapter.seen_cmds), 1)
        final_cmd = _FakeAdapter.seen_cmds[-1]
        self.assertNotIn("-p", final_cmd)

    def test_interrupt_requested_without_completion_evidence_marks_error(self) -> None:
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

        class _ImmediateThread:
            def __init__(self, target=None, args=(), daemon=None):
                self._target = target
                self._args = args

            def start(self) -> None:
                if self._target:
                    self._target(*self._args)

            def join(self, timeout=None) -> None:
                return

        class _FakeStream:
            def __init__(self, lines: list[str]) -> None:
                self._lines = [line + "\n" for line in lines]
                self._idx = 0

            def readline(self) -> str:
                if self._idx >= len(self._lines):
                    return ""
                s = self._lines[self._idx]
                self._idx += 1
                return s

            def close(self) -> None:
                return

        class _FakeProc:
            def __init__(self) -> None:
                self.returncode = 0
                self.stdout = _FakeStream(
                    [
                        '{"type":"thread.started","thread_id":"s1"}',
                        '{"type":"turn.started"}',
                    ]
                )
                self.stderr = _FakeStream([])

            def poll(self):
                return self.returncode

            def terminate(self) -> None:
                return

            def kill(self) -> None:
                return

        class _FakeRegistry:
            def register(self, run_id, proc) -> None:
                return

            def unregister(self, run_id) -> None:
                return

            def consume_interrupted(self, run_id) -> bool:
                return False

        with tempfile.TemporaryDirectory() as td:
            runs_dir = server.Path(td)
            store = server.RunStore(runs_dir=runs_dir)
            sid = f"s1-{uuid.uuid4().hex[:8]}"
            run = store.create_run("p", "c", sid, "m1")
            run_id = str(run["id"])
            meta = store.load_meta(run_id) or {}
            meta["interruptRequestedAt"] = server._now_iso()
            store.save_meta(run_id, meta)

            with patch.object(server, "get_adapter", return_value=_FakeAdapter):
                with patch.object(execution_runtime.subprocess, "Popen", return_value=_FakeProc()):
                    with patch.object(execution_runtime.threading, "Thread", _ImmediateThread):
                        with patch.object(server, "RUN_PROCESS_REGISTRY", _FakeRegistry()):
                            server.run_cli_exec(store, run_id, timeout_s=10, cli_type="codex", scheduler=None)

            after = store.load_meta(run_id) or {}
            self.assertEqual(after.get("status"), "error")
            self.assertEqual(after.get("error"), "interrupted by user")

    def test_interrupt_requested_with_completion_evidence_keeps_done(self) -> None:
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

        class _ImmediateThread:
            def __init__(self, target=None, args=(), daemon=None):
                self._target = target
                self._args = args

            def start(self) -> None:
                if self._target:
                    self._target(*self._args)

            def join(self, timeout=None) -> None:
                return

        class _FakeStream:
            def __init__(self, lines: list[str]) -> None:
                self._lines = [line + "\n" for line in lines]
                self._idx = 0

            def readline(self) -> str:
                if self._idx >= len(self._lines):
                    return ""
                s = self._lines[self._idx]
                self._idx += 1
                return s

            def close(self) -> None:
                return

        class _FakeProc:
            def __init__(self) -> None:
                self.returncode = 0
                self.stdout = _FakeStream(
                    [
                        '{"type":"thread.started","thread_id":"s1"}',
                        '{"type":"turn.started"}',
                        '{"type":"item.completed","item":{"type":"agent_message","text":"ok"}}',
                    ]
                )
                self.stderr = _FakeStream([])

            def poll(self):
                return self.returncode

            def terminate(self) -> None:
                return

            def kill(self) -> None:
                return

        class _FakeRegistry:
            def register(self, run_id, proc) -> None:
                return

            def unregister(self, run_id) -> None:
                return

            def consume_interrupted(self, run_id) -> bool:
                return False

        with tempfile.TemporaryDirectory() as td:
            runs_dir = server.Path(td)
            store = server.RunStore(runs_dir=runs_dir)
            sid = f"s1-{uuid.uuid4().hex[:8]}"
            run = store.create_run("p", "c", sid, "m1")
            run_id = str(run["id"])
            meta = store.load_meta(run_id) or {}
            meta["interruptRequestedAt"] = server._now_iso()
            store.save_meta(run_id, meta)

            with patch.object(server, "get_adapter", return_value=_FakeAdapter):
                with patch.object(execution_runtime.subprocess, "Popen", return_value=_FakeProc()):
                    with patch.object(execution_runtime.threading, "Thread", _ImmediateThread):
                        with patch.object(server, "RUN_PROCESS_REGISTRY", _FakeRegistry()):
                            server.run_cli_exec(store, run_id, timeout_s=10, cli_type="codex", scheduler=None)

            after = store.load_meta(run_id) or {}
            self.assertEqual(after.get("status"), "done")
            self.assertEqual(after.get("error"), "")


if __name__ == "__main__":
    unittest.main()
