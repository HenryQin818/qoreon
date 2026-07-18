import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "create_codex_channel_bootstrap.py"
SPEC = importlib.util.spec_from_file_location("create_codex_channel_bootstrap", SCRIPT_PATH)
bootstrap_script = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = bootstrap_script
SPEC.loader.exec_module(bootstrap_script)


class BootstrapScriptTests(unittest.TestCase):
    def test_resolve_runtime_sessions_project_path_uses_live_sessions_dir(self):
        health = {
            "sessionsFile": "/tmp/task-dashboard/.runtime/stable/.sessions/task_dashboard.json",
            "runsDir": "/tmp/task-dashboard/.runtime/stable/.runs",
        }
        path = bootstrap_script._resolve_runtime_sessions_project_path(health, "task_dashboard_dev_control")
        self.assertIsNotNone(path)
        self.assertEqual(path.name, "task_dashboard_dev_control.json")
        self.assertEqual(path.parent.name, ".sessions")

    def test_append_project_session_store_local_writes_root_and_runtime_store(self):
        with tempfile.TemporaryDirectory() as td:
            root_path = Path(td) / ".sessions" / "task_dashboard.json"
            runtime_path = Path(td) / ".runtime" / "stable" / ".sessions" / "task_dashboard.json"
            channel_root = Path(td) / "任务规划" / "子级99-创建通道链路检查"
            bs = bootstrap_script.Bootstrapper.__new__(bootstrap_script.Bootstrapper)
            bs.project_id = "task_dashboard"
            bs.sessions_project_path = root_path
            bs.runtime_sessions_project_path = runtime_path
            bs.channel_root = channel_root
            bs.desktop_cwd = str(Path(td))
            bs.names = SimpleNamespace(session_title="创建通道链路检查主会话")

            bs._append_project_session_store_local(
                session_id="019c-test-bootstrap-session",
                alias="",
                cli_type="codex",
                channel_name="子级99-创建通道链路检查",
            )

            for target in (root_path, runtime_path):
                self.assertTrue(target.exists(), msg=str(target))
                data = json.loads(target.read_text(encoding="utf-8"))
                sessions = data.get("sessions") or []
                self.assertEqual(len(sessions), 1)
                self.assertEqual(sessions[0].get("id"), "019c-test-bootstrap-session")
                self.assertEqual(sessions[0].get("channel_name"), "子级99-创建通道链路检查")
                self.assertTrue(sessions[0].get("is_primary"))
                self.assertEqual(sessions[0].get("session_role"), "primary")
                self.assertEqual(sessions[0].get("workdir"), str(channel_root))
                self.assertEqual(sessions[0].get("alias"), "创建通道链路检查主会话")
                self.assertEqual(sessions[0].get("agent_name"), "创建通道链路检查主会话")

    def test_ensure_scripts_exist_skips_desktopize_dependency_when_disabled(self):
        bs = bootstrap_script.Bootstrapper.__new__(bootstrap_script.Bootstrapper)
        bs.args = SimpleNamespace(no_desktopize=True)
        bs.desktopize_script = Path("/tmp/missing-desktopize-taskboard-session.py")

        with mock.patch.object(bootstrap_script, "_die", side_effect=AssertionError("_die should not be called")):
            bs._ensure_scripts_exist()

    def test_create_session_retries_channel_not_found_until_ready(self):
        bs = bootstrap_script.Bootstrapper.__new__(bootstrap_script.Bootstrapper)
        bs.project_id = "task_dashboard"
        bs.base_url = "http://localhost:18770"
        bs.token = ""
        bs.args = SimpleNamespace(session_alias="", api_session_timeout_s=7)
        bs.names = SimpleNamespace(channel_dir_name="子级99-创建通道链路检查")
        bs._build_seed_message = lambda: "seed"
        bs._create_session_via_local_codex = lambda **kwargs: "fallback-session"

        side_effects = [
            RuntimeError('POST http://localhost:18770/api/sessions -> HTTP 404: {"error":"channel not found"}'),
            RuntimeError('POST http://localhost:18770/api/sessions -> HTTP 404: {"error":"channel not found"}'),
            {"session": {"id": "019c-retry-session"}},
        ]
        with mock.patch.object(bootstrap_script, "_http_request_json", side_effect=side_effects) as m_http, \
             mock.patch.object(bootstrap_script.time, "sleep") as m_sleep:
            sid = bs._create_session()

        self.assertEqual(sid, "019c-retry-session")
        self.assertEqual(m_http.call_count, 3)
        self.assertEqual((m_http.call_args.kwargs.get("payload") or {}).get("agent_name"), "子级99-创建通道链路检查")
        self.assertEqual(m_sleep.call_count, 2)

    def test_seed_and_training_messages_include_message_cli_guidance(self):
        bs = bootstrap_script.Bootstrapper.__new__(bootstrap_script.Bootstrapper)
        bs.args = SimpleNamespace(goal="建立协作入口", target_cli_type="")
        bs.names = SimpleNamespace(channel_dir_name="辅助04-原型设计")

        seed = bs._build_seed_message()
        training = bs._build_training_message("019c-session")

        for text in (seed, training):
            self.assertIn("task_dashboard.message_cli", text)
            self.assertIn("--wait-verify", text)
            self.assertIn("blocking_error.next_action", text)
            self.assertIn("旧 registry", text)
            self.assertIn(".sessions", text)
        self.assertIn("send --to-agent", training)
        self.assertIn("receipt --to-agent", training)

    def test_gemini_seed_and_training_messages_use_tool_limited_guidance(self):
        bs = bootstrap_script.Bootstrapper.__new__(bootstrap_script.Bootstrapper)
        bs.args = SimpleNamespace(goal="建立协作入口", target_cli_type="gemini")
        bs.names = SimpleNamespace(channel_dir_name="辅助04-原型设计")

        seed = bs._build_seed_message()
        training = bs._build_training_message("019c-session")

        for text in (seed, training):
            self.assertIn("cli_type=gemini", text)
            self.assertIn("read_file", text)
            self.assertIn("grep_search", text)
            self.assertIn("cli_help", text)
            self.assertIn("run_shell_command", text)
            self.assertIn("不强制发送", text)
            self.assertIn("announce_run_id + target_session_id一致 + visible_in_channel_chat=true", text)
        self.assertIn("唯一阻塞", seed)

    def test_create_session_via_local_codex_uses_session_id_from_output_when_scan_misses(self):
        from task_dashboard.adapters.codex_adapter import CodexAdapter

        bs = bootstrap_script.Bootstrapper.__new__(bootstrap_script.Bootstrapper)
        bs.repo_root = Path.cwd()
        bs.desktop_cwd = str(Path.cwd())
        bs.project_id = "task_dashboard"
        bs.args = SimpleNamespace(session_create_timeout_s=15)
        bs.names = SimpleNamespace(channel_dir_name="子级99-创建通道链路检查")

        proc = subprocess.CompletedProcess(
            args=["codex"],
            returncode=0,
            stdout="OK",
            stderr="session id: 44444444-4444-4444-4444-444444444444",
        )

        with mock.patch.object(bootstrap_script.subprocess, "run", return_value=proc), \
             mock.patch.object(bootstrap_script, "_die", side_effect=AssertionError("_die should not be called")), \
             mock.patch.object(CodexAdapter, "build_create_command", return_value=["/usr/bin/true"]), \
             mock.patch.object(CodexAdapter, "find_new_session_id", return_value=("", "")), \
             mock.patch.object(
                 CodexAdapter,
                 "extract_session_id_from_output",
                 return_value="44444444-4444-4444-4444-444444444444",
             ), \
             mock.patch.object(bs, "_append_project_session_store_local") as m_append:
            sid = bs._create_session_via_local_codex(alias="", seed_message="seed")

        self.assertEqual(sid, "44444444-4444-4444-4444-444444444444")
        m_append.assert_called_once()

    def test_desktopize_session_retries_until_session_file_visible(self):
        bs = bootstrap_script.Bootstrapper.__new__(bootstrap_script.Bootstrapper)
        bs.desktopize_script = Path("/tmp/desktopize_taskboard_session.py")
        bs.desktop_cwd = "/tmp"
        bs.names = SimpleNamespace(session_title="【小秘书】测试主会话")
        bs._warnings = []

        pending = subprocess.CompletedProcess(
            args=["python3"],
            returncode=3,
            stdout='{"ok": false, "error": "session file not found"}',
            stderr="",
        )
        success = subprocess.CompletedProcess(
            args=["python3"],
            returncode=0,
            stdout='{"ok": true, "sessionId": "019c-ok"}',
            stderr="",
        )

        with mock.patch.object(bootstrap_script.subprocess, "run", side_effect=[pending, success]) as m_run, \
             mock.patch.object(bootstrap_script.time, "sleep") as m_sleep:
            bs._desktopize_session("019c-ok")

        self.assertEqual(m_run.call_count, 2)
        m_sleep.assert_called_once_with(bootstrap_script.DESKTOPIZE_SESSION_FILE_RETRY_DELAY_S)
        self.assertEqual(bs._warnings, [])

    def test_desktopize_session_warns_and_continues_when_session_file_never_appears(self):
        bs = bootstrap_script.Bootstrapper.__new__(bootstrap_script.Bootstrapper)
        bs.desktopize_script = Path("/tmp/desktopize_taskboard_session.py")
        bs.desktop_cwd = "/tmp"
        bs.names = SimpleNamespace(session_title="【小秘书】测试主会话")
        bs._warnings = []

        pending = subprocess.CompletedProcess(
            args=["python3"],
            returncode=3,
            stdout='{"ok": false, "error": "session file not found"}',
            stderr="",
        )

        with mock.patch.object(
            bootstrap_script.subprocess,
            "run",
            side_effect=[pending] * bootstrap_script.DESKTOPIZE_SESSION_FILE_MAX_ATTEMPTS,
        ) as m_run, mock.patch.object(bootstrap_script.time, "sleep") as m_sleep, mock.patch.object(
            bootstrap_script, "_die", side_effect=AssertionError("_die should not be called")
        ):
            bs._desktopize_session("019c-pending")

        self.assertEqual(
            m_run.call_count,
            bootstrap_script.DESKTOPIZE_SESSION_FILE_MAX_ATTEMPTS,
        )
        self.assertEqual(
            m_sleep.call_count,
            bootstrap_script.DESKTOPIZE_SESSION_FILE_MAX_ATTEMPTS - 1,
        )
        self.assertEqual(len(bs._warnings), 1)
        self.assertIn("已降级跳过", bs._warnings[0])


if __name__ == "__main__":
    unittest.main()
