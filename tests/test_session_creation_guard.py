import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import server


class _FakeAdapter:
    home_path = Path('.')
    before_sessions = []
    after_sessions = []
    extracted_session_id = ""
    received_browser_mode = ""

    @classmethod
    def get_home_path(cls):
        return cls.home_path

    @classmethod
    def supports_model(cls):
        return True

    @classmethod
    def build_create_command(
        cls,
        seed_prompt,
        output_path,
        model="",
        reasoning_effort="",
        sandbox_mode="read-only",
        browser_mode="auto",
    ):
        _ = sandbox_mode
        cls.received_browser_mode = browser_mode
        return ["/usr/bin/true"]

    @classmethod
    def scan_sessions(cls, after_ts=0.0):
        if float(after_ts or 0.0) <= 0.0:
            return list(cls.before_sessions)
        return list(cls.after_sessions)

    @classmethod
    def extract_session_id_from_output(cls, text):
        return str(cls.extracted_session_id or "").strip()


class SessionCreationGuardTests(unittest.TestCase):
    def test_create_cli_session_disables_browser_for_seed_turn(self):
        with tempfile.TemporaryDirectory() as td:
            _FakeAdapter.home_path = Path(td)
            _FakeAdapter.before_sessions = []
            _FakeAdapter.after_sessions = []
            _FakeAdapter.extracted_session_id = ""
            _FakeAdapter.received_browser_mode = ""
            with mock.patch("server.get_adapter_or_error", return_value=_FakeAdapter), \
                 mock.patch("server.get_adapter", return_value=_FakeAdapter), \
                 mock.patch("server.subprocess.run", return_value=subprocess.CompletedProcess(args=["x"], returncode=0, stdout="", stderr="")):
                server.create_cli_session("seed", timeout_s=30, cli_type="codex")

            self.assertEqual(_FakeAdapter.received_browser_mode, "off")

    def test_create_cli_session_uses_new_session_delta_not_recent_old(self):
        with tempfile.TemporaryDirectory() as td:
            _FakeAdapter.home_path = Path(td)
            old_sid = "11111111-1111-1111-1111-111111111111"
            new_sid = "22222222-2222-2222-2222-222222222222"
            _FakeAdapter.before_sessions = [
                SimpleNamespace(session_id=old_sid, path=Path(td) / "old.jsonl", modified_ts=10.0),
            ]
            # old session is still being written and has newer mtime than new session.
            _FakeAdapter.after_sessions = [
                SimpleNamespace(session_id=old_sid, path=Path(td) / "old.jsonl", modified_ts=200.0),
                SimpleNamespace(session_id=new_sid, path=Path(td) / "new.jsonl", modified_ts=190.0),
            ]

            with mock.patch("server.get_adapter_or_error", return_value=_FakeAdapter), \
                 mock.patch("server.get_adapter", return_value=_FakeAdapter), \
                 mock.patch("server.subprocess.run", return_value=subprocess.CompletedProcess(args=["x"], returncode=0, stdout="", stderr="")), \
                 mock.patch("server.time.time", return_value=100.0):
                result = server.create_cli_session("seed", timeout_s=30, cli_type="codex")

            self.assertTrue(result.get("ok"))
            self.assertEqual(result.get("sessionId"), new_sid)

    def test_create_cli_session_timeout_does_not_fallback_to_old_session(self):
        with tempfile.TemporaryDirectory() as td:
            _FakeAdapter.home_path = Path(td)
            _FakeAdapter.extracted_session_id = ""
            old_sid = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
            _FakeAdapter.before_sessions = [
                SimpleNamespace(session_id=old_sid, path=Path(td) / "old.jsonl", modified_ts=10.0),
            ]
            _FakeAdapter.after_sessions = [
                SimpleNamespace(session_id=old_sid, path=Path(td) / "old.jsonl", modified_ts=200.0),
            ]

            with mock.patch("server.get_adapter_or_error", return_value=_FakeAdapter), \
                 mock.patch("server.get_adapter", return_value=_FakeAdapter), \
                 mock.patch("server.subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=["x"], timeout=30)), \
                 mock.patch("server.time.time", return_value=100.0):
                result = server.create_cli_session("seed", timeout_s=30, cli_type="codex")

            self.assertFalse(result.get("ok"))
            self.assertEqual(result.get("error"), "timeout")
            self.assertEqual(str(result.get("sessionId") or ""), "")

    def test_create_cli_session_uses_ascii_spawn_cwd_for_codex_non_ascii_workdir(self):
        with tempfile.TemporaryDirectory() as td:
            _FakeAdapter.home_path = Path(td)
            _FakeAdapter.before_sessions = []
            _FakeAdapter.after_sessions = []
            _FakeAdapter.extracted_session_id = ""
            non_ascii_workdir = Path(td) / "中文目录"
            non_ascii_workdir.mkdir(parents=True, exist_ok=True)
            (non_ascii_workdir / ".git").mkdir()
            called: dict[str, object] = {}

            def _fake_run(cmd, capture_output, text, timeout, cwd, env=None):
                called["cmd"] = list(cmd)
                called["cwd"] = str(cwd)
                if env is not None:
                    called["env"] = dict(env)
                return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

            with mock.patch("server.get_adapter_or_error", return_value=_FakeAdapter), \
                 mock.patch("server.get_adapter", return_value=_FakeAdapter), \
                 mock.patch("server.subprocess.run", side_effect=_fake_run), \
                 mock.patch("server.time.time", return_value=100.0):
                server.create_cli_session("seed", timeout_s=30, cli_type="codex", workdir=non_ascii_workdir)

            spawn_cwd = str(called.get("cwd") or "")
            self.assertTrue(spawn_cwd)
            spawn_cwd.encode("ascii")
            self.assertNotEqual(spawn_cwd, str(non_ascii_workdir))

    def test_create_cli_session_uses_ascii_spawn_cwd_for_full_profile(self):
        with tempfile.TemporaryDirectory() as td:
            _FakeAdapter.home_path = Path(td)
            _FakeAdapter.before_sessions = []
            _FakeAdapter.after_sessions = []
            _FakeAdapter.extracted_session_id = ""
            non_ascii_workdir = Path(td) / "中文目录"
            non_ascii_workdir.mkdir(parents=True, exist_ok=True)
            (non_ascii_workdir / ".git").mkdir()
            called: dict[str, object] = {}

            def _fake_run(cmd, capture_output, text, timeout, cwd, env=None):
                called["cmd"] = list(cmd)
                called["cwd"] = str(cwd)
                if env is not None:
                    called["env"] = dict(env)
                return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

            with mock.patch("server.get_adapter_or_error", return_value=_FakeAdapter), \
                 mock.patch("server.get_adapter", return_value=_FakeAdapter), \
                 mock.patch("server.subprocess.run", side_effect=_fake_run), \
                 mock.patch("server.time.time", return_value=100.0):
                server.create_cli_session(
                    "seed",
                    timeout_s=30,
                    cli_type="codex",
                    workdir=non_ascii_workdir,
                    execution_profile="project_privileged_full",
                )

            spawn_cwd = str(called.get("cwd") or "")
            self.assertTrue(spawn_cwd)
            spawn_cwd.encode("ascii")
            self.assertNotEqual(spawn_cwd, str(non_ascii_workdir))

    def test_create_cli_session_uses_spawn_env_for_codex_path(self):
        with tempfile.TemporaryDirectory() as td:
            _FakeAdapter.home_path = Path(td)
            _FakeAdapter.before_sessions = []
            _FakeAdapter.after_sessions = []
            _FakeAdapter.extracted_session_id = ""
            bin_dir = Path(td) / "bin"
            bin_dir.mkdir(parents=True, exist_ok=True)
            fake_codex = bin_dir / "codex"
            fake_codex.write_text("#!/bin/sh\n", encoding="utf-8")
            called: dict[str, object] = {}

            def _fake_run(cmd, capture_output, text, timeout, cwd, env):
                called["cmd"] = list(cmd)
                called["cwd"] = str(cwd)
                called["env"] = dict(env)
                return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

            with mock.patch("server.get_adapter_or_error", return_value=_FakeAdapter), \
                 mock.patch("server.get_adapter", return_value=_FakeAdapter), \
                 mock.patch.object(_FakeAdapter, "build_create_command", return_value=[str(fake_codex)]), \
                 mock.patch("server.subprocess.run", side_effect=_fake_run), \
                 mock.patch("server.time.time", return_value=100.0):
                server.create_cli_session("seed", timeout_s=30, cli_type="codex")

            env = dict(called.get("env") or {})
            path_parts = [item for item in str(env.get("PATH") or "").split(":") if item]
            self.assertTrue(path_parts)
            self.assertEqual(path_parts[0], str(bin_dir))

    def test_create_cli_session_falls_back_to_session_id_in_output_when_scan_misses(self):
        with tempfile.TemporaryDirectory() as td:
            _FakeAdapter.home_path = Path(td)
            _FakeAdapter.before_sessions = []
            _FakeAdapter.after_sessions = []
            _FakeAdapter.extracted_session_id = "33333333-3333-3333-3333-333333333333"

            proc = subprocess.CompletedProcess(
                args=["x"],
                returncode=0,
                stdout="OK",
                stderr="session id: 33333333-3333-3333-3333-333333333333",
            )

            with mock.patch("server.get_adapter_or_error", return_value=_FakeAdapter), \
                 mock.patch("server.get_adapter", return_value=_FakeAdapter), \
                 mock.patch("server.subprocess.run", return_value=proc), \
                 mock.patch("server.time.time", return_value=100.0):
                result = server.create_cli_session("seed", timeout_s=30, cli_type="codex")

            self.assertTrue(result.get("ok"))
            self.assertEqual(result.get("sessionId"), _FakeAdapter.extracted_session_id)


class SessionBindingStoreTests(unittest.TestCase):
    def test_save_binding_keeps_only_latest_per_project_channel(self):
        with tempfile.TemporaryDirectory() as td:
            runs_dir = Path(td) / ".runs"
            runs_dir.mkdir(parents=True, exist_ok=True)
            store = server.SessionBindingStore(runs_dir=runs_dir)

            sid_old = "33333333-3333-3333-3333-333333333333"
            sid_new = "44444444-4444-4444-4444-444444444444"
            pid = "task_dashboard"
            ch = "子级04-前端体验（task-overview 页面交互）"

            store.save_binding(sid_old, pid, ch, "codex")
            store.save_binding(sid_new, pid, ch, "codex")

            rows = [
                r for r in store.list_bindings(project_id=pid)
                if str(r.get("channelName") or "") == ch
            ]
            self.assertEqual(len(rows), 1)
            self.assertEqual(str(rows[0].get("sessionId") or ""), sid_new)


if __name__ == "__main__":
    unittest.main()
