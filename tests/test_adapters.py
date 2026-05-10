import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from task_dashboard.adapters import (
    get_adapter,
    get_adapter_or_error,
    CodexAdapter,
    ClaudeAdapter,
    OpenCodeAdapter,
    GeminiAdapter,
    TraeAdapter,
)
from task_dashboard.adapters.base import resolve_cli_executable, resolve_cli_executable_details


class TestCodexAdapter(unittest.TestCase):
    """Tests for CodexAdapter."""

    @staticmethod
    def _assert_codex_prefix(cmd: list[str]) -> None:
        assert str(cmd[0] or "").strip()
        assert cmd[0] == resolve_cli_executable("codex")

    def test_codex_adapter_info(self) -> None:
        """Verify Codex adapter returns correct CLIInfo."""
        info = CodexAdapter.info()
        self.assertEqual(info.id, "codex")
        self.assertEqual(info.name, "Codex CLI")
        self.assertTrue(info.enabled)

    def test_codex_adapter_build_resume_command(self) -> None:
        """Verify resume command is built correctly with session_id and message."""
        session_id = "019bde9b-4793-70e0-b18a-a437279b2d18"
        message = "Hello, world!"
        output_path = Path("/tmp/output.json")

        cmd = CodexAdapter.build_resume_command(
            session_id=session_id,
            message=message,
            output_path=output_path,
        )

        self._assert_codex_prefix(cmd)
        self.assertIn("exec", cmd)
        self.assertIn("resume", cmd)
        self.assertIn(session_id, cmd)
        self.assertIn(message, cmd)
        self.assertIn(str(output_path), cmd)

    def test_codex_adapter_build_resume_command_with_model(self) -> None:
        """Verify model flag is passed through when provided."""
        cmd = CodexAdapter.build_resume_command(
            session_id="019bde9b-4793-70e0-b18a-a437279b2d18",
            message="hi",
            output_path=Path("/tmp/output.json"),
            model="codex-spark",
        )
        self.assertIn("-m", cmd)
        self.assertIn("codex-spark", cmd)

    def test_codex_adapter_build_resume_command_with_reasoning_effort(self) -> None:
        """Verify dashboard extra_high is mapped to the CLI-compatible xhigh value."""
        cmd = CodexAdapter.build_resume_command(
            session_id="019bde9b-4793-70e0-b18a-a437279b2d18",
            message="hi",
            output_path=Path("/tmp/output.json"),
            reasoning_effort="extra-high",
        )
        self.assertIn("-c", cmd)
        self.assertIn('model_reasoning_effort="xhigh"', cmd)

    def test_codex_adapter_uses_ccb_http_provider_by_default(self) -> None:
        """Verify CCB Codex turns avoid WebSocket transport and app preload by default."""
        cmd = CodexAdapter.build_resume_command(
            session_id="019bde9b-4793-70e0-b18a-a437279b2d18",
            message="hi",
            output_path=Path("/tmp/output.json"),
        )
        self.assertIn("features.apps=false", cmd)
        self.assertIn('model_provider="openai_ccb_http"', cmd)
        self.assertIn("model_providers.openai_ccb_http.supports_websockets=false", cmd)
        self.assertIn("model_providers.openai_ccb_http.stream_max_retries=0", cmd)
        self.assertIn("model_providers.openai_ccb_http.request_max_retries=1", cmd)

    def test_codex_adapter_can_disable_ccb_http_provider(self) -> None:
        """Verify HTTP-only provider is opt-out for sessions that need native transport."""
        with mock.patch.dict("os.environ", {"TASK_DASHBOARD_CODEX_FORCE_HTTP": "0"}, clear=False):
            cmd = CodexAdapter.build_resume_command(
                session_id="019bde9b-4793-70e0-b18a-a437279b2d18",
                message="hi",
                output_path=Path("/tmp/output.json"),
            )
        self.assertNotIn('model_provider="openai_ccb_http"', cmd)
        self.assertNotIn("model_providers.openai_ccb_http.supports_websockets=false", cmd)
        self.assertIn("features.apps=false", cmd)

    def test_codex_adapter_can_keep_apps_enabled(self) -> None:
        """Verify app preload can be restored when a CCB run explicitly needs apps."""
        with mock.patch.dict("os.environ", {"TASK_DASHBOARD_CODEX_DISABLE_APPS": "0"}, clear=False):
            cmd = CodexAdapter.build_resume_command(
                session_id="019bde9b-4793-70e0-b18a-a437279b2d18",
                message="hi",
                output_path=Path("/tmp/output.json"),
            )
        self.assertNotIn("features.apps=false", cmd)
        self.assertIn('model_provider="openai_ccb_http"', cmd)

    def test_codex_adapter_build_create_command(self) -> None:
        """Verify create command is built correctly."""
        seed_prompt = "Write a hello world program"
        output_path = Path("/tmp/output.json")

        cmd = CodexAdapter.build_create_command(
            seed_prompt=seed_prompt,
            output_path=output_path,
        )

        self._assert_codex_prefix(cmd)
        self.assertIn("exec", cmd)
        self.assertIn(str(output_path), cmd)
        self.assertIn(seed_prompt, cmd)
        self.assertIn("--sandbox", cmd)
        self.assertIn("read-only", cmd)

    def test_codex_adapter_build_create_command_can_skip_explicit_sandbox(self) -> None:
        cmd = CodexAdapter.build_create_command(
            seed_prompt="Please reply with OK",
            output_path=Path("/tmp/output.json"),
            sandbox_mode="",
        )
        self.assertNotIn("--sandbox", cmd)
        self.assertNotIn("read-only", cmd)

    def test_codex_adapter_build_create_command_with_reasoning_effort(self) -> None:
        """Verify reasoning effort is passed through when creating session."""
        cmd = CodexAdapter.build_create_command(
            seed_prompt="Please reply with OK",
            output_path=Path("/tmp/output.json"),
            reasoning_effort="high",
        )
        self.assertIn("-c", cmd)
        self.assertIn('model_reasoning_effort="high"', cmd)

    def test_codex_adapter_build_create_command_with_extra_high_reasoning_effort(self) -> None:
        """Verify create command also maps extra_high to xhigh for the CLI."""
        cmd = CodexAdapter.build_create_command(
            seed_prompt="Please reply with OK",
            output_path=Path("/tmp/output.json"),
            reasoning_effort="extra_high",
        )
        self.assertIn("-c", cmd)
        self.assertIn('model_reasoning_effort="xhigh"', cmd)

    def test_codex_adapter_supports_model(self) -> None:
        self.assertTrue(CodexAdapter.supports_model())

    def test_codex_adapter_scan_sessions(self) -> None:
        """Test that scan_sessions returns a list (may be empty if no sessions exist)."""
        sessions = CodexAdapter.scan_sessions()
        self.assertIsInstance(sessions, list)

    def test_resolve_cli_executable_prefers_local_config_over_env(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            local_cfg = Path(td) / "config.local.toml"
            local_cfg.write_text(
                """
[runtime.cli_bins]
codex = "/bin/echo"
""".strip()
                + "\n",
                encoding="utf-8",
            )
            resolve_cli_executable.cache_clear()
            resolve_cli_executable_details.cache_clear()
            with mock.patch.dict(
                os.environ,
                {
                    "TASK_DASHBOARD_CONFIG_LOCAL": str(local_cfg),
                    "TASK_DASHBOARD_CODEX_BIN": "/bin/cat",
                },
                clear=False,
            ):
                got = resolve_cli_executable("codex")
            resolve_cli_executable.cache_clear()
            resolve_cli_executable_details.cache_clear()

        self.assertEqual(got, "/bin/echo")


class TestClaudeAdapter(unittest.TestCase):
    """Tests for ClaudeAdapter."""

    def test_claude_adapter_info(self) -> None:
        """Verify Claude adapter returns correct CLIInfo."""
        info = ClaudeAdapter.info()
        self.assertEqual(info.id, "claude")
        self.assertEqual(info.name, "Claude Code")
        self.assertTrue(info.enabled)

    def test_claude_adapter_build_resume_command_uses_full_permissions(self) -> None:
        cmd = ClaudeAdapter.build_resume_command(
            session_id="019bde9b-4793-70e0-b18a-a437279b2d18",
            message="Hello, Claude!",
            output_path=Path("/tmp/claude-output.txt"),
        )
        self.assertEqual(Path(cmd[0]).name, "claude")
        self.assertIn("--dangerously-skip-permissions", cmd)
        self.assertIn("--resume", cmd)
        self.assertIn("--print", cmd)

    def test_claude_adapter_build_create_command_uses_full_permissions(self) -> None:
        cmd = ClaudeAdapter.build_create_command(
            seed_prompt="Please reply with: OK",
            output_path=Path("/tmp/claude-create.txt"),
        )
        self.assertEqual(Path(cmd[0]).name, "claude")
        self.assertIn("--dangerously-skip-permissions", cmd)
        self.assertIn("--print", cmd)

    def test_claude_adapter_parse_output_line_ignores_plain_text(self) -> None:
        self.assertIsNone(ClaudeAdapter.parse_output_line("这是 Claude 的普通正文"))


class TestOpenCodeAdapter(unittest.TestCase):
    """Tests for OpenCodeAdapter."""

    def test_opencode_adapter_info(self) -> None:
        """Verify OpenCode adapter returns correct CLIInfo."""
        info = OpenCodeAdapter.info()
        self.assertEqual(info.id, "opencode")
        self.assertEqual(info.name, "OpenCode")
        self.assertTrue(info.enabled)

    def test_opencode_adapter_parse_output_line_ignores_plain_text(self) -> None:
        self.assertIsNone(OpenCodeAdapter.parse_output_line("这是 OpenCode 的普通正文"))

    def test_opencode_adapter_scan_sessions_from_database(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            db_path = home / "opencode.db"
            conn = sqlite3.connect(str(db_path))
            try:
                conn.execute(
                    """
                    CREATE TABLE session (
                        id TEXT PRIMARY KEY,
                        project_id TEXT NOT NULL,
                        parent_id TEXT,
                        slug TEXT NOT NULL,
                        directory TEXT NOT NULL,
                        title TEXT NOT NULL,
                        version TEXT NOT NULL,
                        share_url TEXT,
                        summary_additions INTEGER,
                        summary_deletions INTEGER,
                        summary_files INTEGER,
                        summary_diffs TEXT,
                        revert TEXT,
                        permission TEXT,
                        time_created INTEGER NOT NULL,
                        time_updated INTEGER NOT NULL,
                        time_compacting INTEGER,
                        time_archived INTEGER,
                        workspace_id TEXT
                    )
                    """
                )
                conn.execute(
                    """
                    INSERT INTO session (
                        id, project_id, slug, directory, title, version, time_created, time_updated
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "ses_test_created_from_db",
                        "project-1",
                        "session-1",
                        "/tmp/project-1",
                        "DB Session",
                        "1",
                        1773131340727,
                        1773131341215,
                    ),
                )
                conn.commit()
            finally:
                conn.close()

            with unittest.mock.patch.dict(os.environ, {"OPENCODE_HOME": str(home)}, clear=False):
                sessions = OpenCodeAdapter.scan_sessions(after_ts=1773131340.0)

            self.assertEqual(len(sessions), 1)
            self.assertEqual(sessions[0].session_id, "ses_test_created_from_db")
            self.assertEqual(sessions[0].path.resolve(), db_path.resolve())


class TestGeminiAdapter(unittest.TestCase):
    """Tests for GeminiAdapter."""

    def test_gemini_adapter_info(self) -> None:
        """Verify Gemini adapter returns correct CLIInfo."""
        info = GeminiAdapter.info()
        self.assertEqual(info.id, "gemini")
        self.assertEqual(info.name, "Gemini CLI")
        self.assertTrue(info.enabled)

    def test_gemini_adapter_build_resume_command(self) -> None:
        """Verify Gemini resume command uses session_id and non-interactive prompt."""
        session_id = "019bde9b-4793-70e0-b18a-a437279b2d18"
        message = "Hello, Gemini!"
        output_path = Path("/tmp/output.json")
        cmd = GeminiAdapter.build_resume_command(
            session_id=session_id,
            message=message,
            output_path=output_path,
        )
        self.assertEqual(Path(cmd[0]).name, "gemini")
        self.assertIn("--resume", cmd)
        self.assertIn(session_id, cmd)
        self.assertIn("--prompt", cmd)
        self.assertIn(message, cmd)
        self.assertIn("--output-format", cmd)
        self.assertIn("json", cmd)


class TestTraeAdapter(unittest.TestCase):
    """Tests for TraeAdapter."""

    def test_trae_adapter_info(self) -> None:
        info = TraeAdapter.info()
        self.assertEqual(info.id, "trae")
        self.assertEqual(info.name, "Trae Agent CLI")
        self.assertTrue(info.enabled)

    def test_trae_adapter_build_resume_command(self) -> None:
        cmd = TraeAdapter.build_resume_command(
            session_id="019bde9b-4793-70e0-b18a-a437279b2d18",
            message="Hello, Trae!",
            output_path=Path("/tmp/trae-output.json"),
            model="gpt-4.1",
        )
        self.assertEqual(Path(cmd[0]).name, "trae-cli")
        self.assertIn("run", cmd)
        self.assertIn("--trajectory-file", cmd)
        self.assertIn("/tmp/trae-output.json", cmd)
        self.assertIn("--model", cmd)
        self.assertIn("gpt-4.1", cmd)

    def test_trae_adapter_supports_model(self) -> None:
        self.assertTrue(TraeAdapter.supports_model())


class TestAdapterRegistry(unittest.TestCase):
    """Tests for the adapter registry functions."""

    def test_adapter_registry(self) -> None:
        """Verify that get_adapter returns correct adapters for known CLI types."""
        self.assertEqual(get_adapter("codex"), CodexAdapter)
        self.assertEqual(get_adapter("claude"), ClaudeAdapter)
        self.assertEqual(get_adapter("opencode"), OpenCodeAdapter)
        self.assertEqual(get_adapter("gemini"), GeminiAdapter)
        self.assertEqual(get_adapter("trae"), TraeAdapter)

    def test_get_adapter_or_error(self) -> None:
        """Verify get_adapter_or_error raises ValueError for unknown CLI type."""
        with self.assertRaises(ValueError) as context:
            get_adapter_or_error("unknown_cli_type")

        self.assertIn("Unknown CLI type", str(context.exception))
        self.assertIn("unknown_cli_type", str(context.exception))


class TestAdapterExecutableResolve(unittest.TestCase):
    def test_resolve_cli_executable_override(self) -> None:
        from unittest.mock import patch

        resolve_cli_executable.cache_clear()
        with patch.dict("os.environ", {"TASK_DASHBOARD_CODEX_BIN": "/bin/echo"}, clear=False):
            got = resolve_cli_executable("codex")
        self.assertEqual(got, "/bin/echo")
        resolve_cli_executable.cache_clear()

    def test_resolve_cli_executable_override_with_hyphenated_command(self) -> None:
        from unittest.mock import patch

        resolve_cli_executable.cache_clear()
        with patch.dict("os.environ", {"TASK_DASHBOARD_TRAE_CLI_BIN": "/bin/echo"}, clear=False):
            got = resolve_cli_executable("trae-cli")
        self.assertEqual(got, "/bin/echo")
        resolve_cli_executable.cache_clear()


if __name__ == "__main__":
    unittest.main()
