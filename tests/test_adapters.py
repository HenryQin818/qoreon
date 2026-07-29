import json
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
    CodeBuddyAdapter,
)
from task_dashboard.adapters.codebuddy_output import extract_final_text, normalize_process_events
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

    def test_codex_adapter_build_resume_command_separates_prompt_args(self) -> None:
        """Protect Markdown frontmatter prompts from CLI option parsing."""
        session_id = "019bde9b-4793-70e0-b18a-a437279b2d18"
        message = "---\ntask_id: demo\n---\nbody"

        cmd = CodexAdapter.build_resume_command(
            session_id=session_id,
            message=message,
            output_path=Path("/tmp/output.json"),
        )

        resume_index = cmd.index("resume")
        self.assertEqual(cmd[resume_index + 1], session_id)
        self.assertEqual(cmd[resume_index + 2], "--")
        self.assertEqual(cmd[resume_index + 3], message)

    def test_codex_adapter_build_resume_command_adds_image_args_before_session(self) -> None:
        """D24 image passthrough uses Codex native image argv, not prompt text."""
        session_id = "019bde9b-4793-70e0-b18a-a437279b2d18"
        image_path = "/tmp/qoreon-d24-image.png"
        message = "请识别图片内容"

        cmd = CodexAdapter.build_resume_command(
            session_id=session_id,
            message=message,
            output_path=Path("/tmp/output.json"),
            attachments=[
                {
                    "kind": "image",
                    "content_type": "image/png",
                    "resolved_local_path": image_path,
                },
                {
                    "kind": "document",
                    "content_type": "text/plain",
                    "resolved_local_path": "/tmp/not-image.txt",
                },
            ],
        )

        resume_index = cmd.index("resume")
        session_index = cmd.index(session_id)
        self.assertIn("-i", cmd[resume_index + 1 : session_index])
        image_flag_index = cmd.index("-i")
        self.assertEqual(cmd[image_flag_index + 1], image_path)
        self.assertNotIn("/tmp/not-image.txt", cmd)
        self.assertNotIn("--last", cmd)
        self.assertEqual(cmd[session_index + 1], "--")
        self.assertEqual(cmd[session_index + 2], message)

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

    def test_codex_adapter_passes_current_model_catalog_ids_through(self) -> None:
        model_ids = (
            "gpt-5.6-sol",
            "gpt-5.6-terra",
            "gpt-5.6-luna",
            "gpt-5.5",
            "gpt-5.4",
            "gpt-5.4-mini",
            "gpt-5.3-codex-spark",
        )
        for model_id in model_ids:
            with self.subTest(command="resume", model=model_id):
                cmd = CodexAdapter.build_resume_command(
                    session_id="019bde9b-4793-70e0-b18a-a437279b2d18",
                    message="hi",
                    output_path=Path("/tmp/output.json"),
                    model=model_id,
                )
                self.assertEqual(cmd[cmd.index("-m") + 1], model_id)
            with self.subTest(command="create", model=model_id):
                cmd = CodexAdapter.build_create_command(
                    seed_prompt="Please reply with OK",
                    output_path=Path("/tmp/output.json"),
                    model=model_id,
                )
                self.assertEqual(cmd[cmd.index("-m") + 1], model_id)

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

    def test_codex_adapter_passes_supported_reasoning_efforts_through(self) -> None:
        for effort in ("low", "medium", "high", "xhigh"):
            with self.subTest(effort=effort):
                cmd = CodexAdapter.build_resume_command(
                    session_id="019bde9b-4793-70e0-b18a-a437279b2d18",
                    message="hi",
                    output_path=Path("/tmp/output.json"),
                    reasoning_effort=effort,
                )
                self.assertIn(f'model_reasoning_effort="{effort}"', cmd)

    def test_codex_adapter_uses_ccb_http_provider_by_default(self) -> None:
        """Verify CCB Codex turns avoid WebSocket transport and app preload by default."""
        with mock.patch.dict(
            os.environ,
            {"TASK_DASHBOARD_CODEX_BROWSER_PLUGIN": "0"},
            clear=False,
        ):
            cmd = CodexAdapter.build_resume_command(
                session_id="019bde9b-4793-70e0-b18a-a437279b2d18",
                message="hi",
                output_path=Path("/tmp/output.json"),
                browser_mode="ephemeral",
            )
        self.assertIn("features.apps=false", cmd)
        self.assertIn('model_provider="openai_ccb_http"', cmd)
        self.assertIn("model_providers.openai_ccb_http.supports_websockets=false", cmd)
        self.assertIn("model_providers.openai_ccb_http.stream_max_retries=0", cmd)
        self.assertIn("model_providers.openai_ccb_http.request_max_retries=1", cmd)
        playwright_config = next(
            value for value in cmd if value.startswith("mcp_servers.playwright=")
        )
        self.assertIn('command="npx"', playwright_config)
        self.assertIn('"@playwright/mcp@0.0.78"', playwright_config)
        self.assertIn('"--browser=chrome"', playwright_config)
        self.assertIn('"--headless"', playwright_config)
        self.assertIn('"--isolated"', playwright_config)
        self.assertIn("enabled=true", playwright_config)
        self.assertIn('mcp_servers.chrome-devtools={command="",enabled=false}', cmd)
        self.assertIn('mcp_servers.agent-browser={command="",enabled=false}', cmd)
        self.assertIn('mcp_servers.agent-browser-headed={command="",enabled=false}', cmd)
        self.assertIn('mcp_servers.node_repl={command="",enabled=false}', cmd)
        self.assertIn('mcp_servers.computer-use={command="",enabled=false}', cmd)

    def test_codex_adapter_can_disable_ccb_playwright_mcp(self) -> None:
        """Verify isolated Playwright MCP remains opt-out for non-browser CCB runs."""
        with mock.patch.dict(
            "os.environ",
            {
                "TASK_DASHBOARD_CODEX_PLAYWRIGHT_MCP": "0",
                "TASK_DASHBOARD_CODEX_BROWSER_PLUGIN": "0",
            },
            clear=False,
        ):
            cmd = CodexAdapter.build_resume_command(
                session_id="019bde9b-4793-70e0-b18a-a437279b2d18",
                message="hi",
                output_path=Path("/tmp/output.json"),
            )
        playwright_config = next(
            value for value in cmd if value.startswith("mcp_servers.playwright=")
        )
        self.assertIn('command="npx"', playwright_config)
        self.assertIn('"@playwright/mcp@0.0.78"', playwright_config)
        self.assertIn("enabled=false", playwright_config)
        self.assertIn('mcp_servers.node_repl={command="",enabled=false}', cmd)

    def test_codex_adapter_create_command_disables_browser_by_default(self) -> None:
        cmd = CodexAdapter.build_create_command(
            seed_prompt="Please reply with OK",
            output_path=Path("/tmp/output.json"),
        )
        playwright_config = next(
            value for value in cmd if value.startswith("mcp_servers.playwright=")
        )
        self.assertIn('command="npx"', playwright_config)
        self.assertIn('"@playwright/mcp@0.0.78"', playwright_config)
        self.assertIn("enabled=false", playwright_config)

    def test_codex_adapter_auto_mode_uses_only_project_persistent_playwright(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            command = root / "node_repl"
            command.write_text("placeholder", encoding="utf-8")
            command.chmod(0o755)
            (root / "config.toml").write_text(
                f'[mcp_servers.node_repl]\ncommand = "{command}"\n',
                encoding="utf-8",
            )
            with mock.patch.dict(
                os.environ,
                {
                    "CODEX_HOME": str(root),
                    "TASK_DASHBOARD_CODEX_PLAYWRIGHT_MCP": "1",
                    "TASK_DASHBOARD_CODEX_BROWSER_PLUGIN": "1",
                    "TASK_DASHBOARD_CODEX_PLAYWRIGHT_PROFILE_ROOT": str(root / "profiles"),
                },
                clear=False,
            ):
                resume = CodexAdapter.build_resume_command(
                    session_id="019bde9b-4793-70e0-b18a-a437279b2d18",
                    message="hi",
                    output_path=Path("/tmp/output.json"),
                    browser_mode="auto",
                    project_id="task-dashboard",
                )
                create = CodexAdapter.build_create_command(
                    seed_prompt="Please reply with OK",
                    output_path=Path("/tmp/output.json"),
                    browser_mode="auto",
                    project_id="task-dashboard",
                )
        for command in (resume, create):
            playwright_config = next(value for value in command if value.startswith("mcp_servers.playwright="))
            self.assertIn('command="npx"', playwright_config)
            self.assertIn("enabled=true", playwright_config)
            self.assertIn('"--offline"', playwright_config)
            self.assertIn('"--user-data-dir"', playwright_config)
            self.assertNotIn('"--headless"', playwright_config)
            self.assertNotIn('"--isolated"', playwright_config)
            self.assertIn('mcp_servers.node_repl={command="",enabled=false}', command)

    def test_codex_adapter_collab_and_ephemeral_use_distinct_playwright_profiles(self) -> None:
        with tempfile.TemporaryDirectory() as td, mock.patch.dict(
            os.environ,
            {
                "TASK_DASHBOARD_CODEX_PLAYWRIGHT_PROFILE_ROOT": td,
                "TASK_DASHBOARD_CODEX_BROWSER_PLUGIN": "0",
            },
            clear=False,
        ):
            collab = CodexAdapter.build_resume_command(
                session_id="019bde9b-4793-70e0-b18a-a437279b2d18",
                message="login",
                output_path=Path("/tmp/output.json"),
                browser_mode="collab",
                project_id="project-a",
            )
            ephemeral = CodexAdapter.build_resume_command(
                session_id="019bde9b-4793-70e0-b18a-a437279b2d18",
                message="public check",
                output_path=Path("/tmp/output.json"),
                browser_mode="ephemeral",
                project_id="project-a",
            )
        collab_config = next(value for value in collab if value.startswith("mcp_servers.playwright="))
        ephemeral_config = next(value for value in ephemeral if value.startswith("mcp_servers.playwright="))
        self.assertIn('"--user-data-dir"', collab_config)
        self.assertNotIn('"--headless"', collab_config)
        self.assertNotIn('"--isolated"', collab_config)
        self.assertNotIn('"--user-data-dir"', ephemeral_config)
        self.assertIn('"--headless"', ephemeral_config)
        self.assertIn('"--isolated"', ephemeral_config)

    def test_codex_adapter_off_mode_disables_playwright_and_conflicting_mcps(self) -> None:
        cmd = CodexAdapter.build_resume_command(
            session_id="019bde9b-4793-70e0-b18a-a437279b2d18",
            message="hi",
            output_path=Path("/tmp/output.json"),
            browser_mode="off",
        )
        playwright_config = next(value for value in cmd if value.startswith("mcp_servers.playwright="))
        self.assertIn("enabled=false", playwright_config)
        self.assertIn('mcp_servers.node_repl={command="",enabled=false}', cmd)

    def test_codex_adapter_plugin_mode_enables_only_node_repl_browser_bridge(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            command = root / "node_repl"
            command.write_text("placeholder", encoding="utf-8")
            command.chmod(0o755)
            (root / "config.toml").write_text(
                f'[mcp_servers.node_repl]\ncommand = "{command}"\n',
                encoding="utf-8",
            )
            with mock.patch.dict(
                os.environ,
                {"CODEX_HOME": str(root), "TASK_DASHBOARD_CODEX_BROWSER_PLUGIN": "1"},
                clear=False,
            ):
                cmd = CodexAdapter.build_resume_command(
                    session_id="019d232f-02f1-7781-9de8-2333f2417e71",
                    message="use browser plugin",
                    output_path=str(root / "last.txt"),
                    browser_mode="plugin",
                )
        playwright_config = next(value for value in cmd if value.startswith("mcp_servers.playwright="))
        self.assertIn("enabled=false", playwright_config)
        self.assertIn("mcp_servers.node_repl.enabled=true", cmd)
        self.assertIn('mcp_servers.chrome-devtools={command="",enabled=false}', cmd)
        self.assertIn('mcp_servers.agent-browser={command="",enabled=false}', cmd)
        self.assertIn('mcp_servers.agent-browser-headed={command="",enabled=false}', cmd)
        self.assertIn('mcp_servers.computer-use={command="",enabled=false}', cmd)

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
            local_cfg = Path(td) / "config.test.toml"
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
        self.assertIn("task_dashboard.adapters.claude_runner", cmd)
        self.assertIn("resume", cmd)
        self.assertIn("--resume", cmd)
        self.assertIn("019bde9b-4793-70e0-b18a-a437279b2d18", cmd)
        self.assertIn("--output-path", cmd)
        self.assertIn("/tmp/claude-output.txt", cmd)

    def test_claude_adapter_build_create_command_uses_full_permissions(self) -> None:
        cmd = ClaudeAdapter.build_create_command(
            seed_prompt="Please reply with: OK",
            output_path=Path("/tmp/claude-create.txt"),
        )
        self.assertIn("task_dashboard.adapters.claude_runner", cmd)
        self.assertIn("create", cmd)
        self.assertIn("--output-path", cmd)
        self.assertIn("/tmp/claude-create.txt", cmd)

    def test_claude_adapter_build_resume_command_supports_model(self) -> None:
        cmd = ClaudeAdapter.build_resume_command(
            session_id="019bde9b-4793-70e0-b18a-a437279b2d18",
            message="Hello, Claude!",
            output_path=Path("/tmp/claude-output.txt"),
            model="claude-fable-5",
        )

        self.assertIn("--model", cmd)
        self.assertEqual(cmd[cmd.index("--model") + 1], "claude-fable-5")

    def test_claude_adapter_build_resume_command_normalizes_fable_alias(self) -> None:
        cmd = ClaudeAdapter.build_resume_command(
            session_id="019bde9b-4793-70e0-b18a-a437279b2d18",
            message="Hello, Claude!",
            output_path=Path("/tmp/claude-output.txt"),
            model="fable",
        )

        self.assertIn("--model", cmd)
        self.assertEqual(cmd[cmd.index("--model") + 1], "claude-fable-5")

    def test_claude_adapter_build_resume_command_normalizes_deprecated_model(self) -> None:
        cmd = ClaudeAdapter.build_resume_command(
            session_id="019bde9b-4793-70e0-b18a-a437279b2d18",
            message="Hello, Claude!",
            output_path=Path("/tmp/claude-output.txt"),
            model="claude-opus-4-20250514",
        )

        self.assertIn("--model", cmd)
        self.assertEqual(cmd[cmd.index("--model") + 1], "claude-opus-5")

    def test_claude_adapter_defaults_invalid_model(self) -> None:
        cmd = ClaudeAdapter.build_resume_command(
            session_id="019bde9b-4793-70e0-b18a-a437279b2d18",
            message="Hello, Claude!",
            output_path=Path("/tmp/claude-output.txt"),
            model="辅助04-原型设计",
        )

        self.assertIn("--model", cmd)
        self.assertEqual(cmd[cmd.index("--model") + 1], "claude-opus-5")

    def test_claude_adapter_supports_model(self) -> None:
        self.assertTrue(ClaudeAdapter.supports_model())

    def test_claude_adapter_parse_output_line_ignores_plain_text(self) -> None:
        self.assertIsNone(ClaudeAdapter.parse_output_line("这是 Claude 的普通正文"))

    def test_claude_adapter_parse_output_line_extracts_process_event(self) -> None:
        parsed = ClaudeAdapter.parse_output_line(
            '{"type":"tool_call.started","event_type":"tool_started",'
            '"title":"Read","text":"调用工具: Read path: config.toml","source":"claude"}'
        )

        self.assertEqual((parsed or {}).get("event_type"), "tool_started")
        self.assertEqual((parsed or {}).get("source"), "claude")


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

    def test_gemini_adapter_build_resume_command_supports_model(self) -> None:
        cmd = GeminiAdapter.build_resume_command(
            session_id="019bde9b-4793-70e0-b18a-a437279b2d18",
            message="Hello, Gemini!",
            output_path=Path("/tmp/output.json"),
            model="gemini-2.5-flash",
        )
        self.assertIn("--model", cmd)
        self.assertIn("gemini-2.5-flash", cmd)

    def test_gemini_adapter_build_create_command_supports_model(self) -> None:
        cmd = GeminiAdapter.build_create_command(
            seed_prompt="Hello, Gemini!",
            output_path=Path("/tmp/output.json"),
            model="gemini-2.5-flash",
        )
        self.assertIn("--model", cmd)
        self.assertIn("gemini-2.5-flash", cmd)

    def test_gemini_adapter_supports_model(self) -> None:
        self.assertTrue(GeminiAdapter.supports_model())

    def test_gemini_adapter_extracts_pretty_json_response(self) -> None:
        parsed = GeminiAdapter.parse_output_line(
            '{\n'
            '  "session_id": "b4136799-1826-40b6-8e0e-27500175c542",\n'
            '  "response": "已完成初始化\\n当前职责边界: 总控分工",\n'
            '  "stats": {"tokens": {"total": 120}}\n'
            '}'
        )
        self.assertEqual((parsed or {}).get("type"), "message")
        self.assertEqual((parsed or {}).get("content"), "已完成初始化\n当前职责边界: 总控分工")

    def test_gemini_adapter_ignores_pretty_json_fragments(self) -> None:
        self.assertIsNone(GeminiAdapter.parse_output_line("{"))
        self.assertIsNone(GeminiAdapter.parse_output_line('  "response": "正文",'))
        self.assertIsNone(GeminiAdapter.parse_output_line("}"))


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


class TestCodeBuddyAdapter(unittest.TestCase):
    """Tests for CodeBuddyAdapter."""

    def test_codebuddy_adapter_info(self) -> None:
        info = CodeBuddyAdapter.info()
        self.assertEqual(info.id, "codebuddy")
        self.assertEqual(info.name, "CodeBuddy Code")
        self.assertTrue(info.enabled)

    def test_codebuddy_adapter_build_resume_command(self) -> None:
        cmd = CodeBuddyAdapter.build_resume_command(
            session_id="ccb-smoke-001",
            message="Hello, CodeBuddy!",
            output_path=Path("/tmp/codebuddy-output.txt"),
            model="deepseek-v4-pro",
        )
        joined = " ".join(cmd)
        self.assertIn("task_dashboard.adapters.codebuddy_runner", cmd)
        self.assertIn("resume", cmd)
        self.assertIn("--session-id", cmd)
        self.assertIn("ccb-smoke-001", cmd)
        self.assertIn("--output-path", cmd)
        self.assertIn("/tmp/codebuddy-output.txt", cmd)
        self.assertIn("--model", cmd)
        self.assertIn("deepseek-v4-pro", cmd)
        self.assertIn("Hello, CodeBuddy!", cmd)
        self.assertIn("codebuddy_runner", joined)

    def test_codebuddy_adapter_permission_mode_runtime_whitelist(self) -> None:
        cmd = CodeBuddyAdapter.build_resume_command(
            session_id="ccb-smoke-001",
            message="Hello, CodeBuddy!",
            output_path=Path("/tmp/codebuddy-output.txt"),
            permission_mode="bypassPermissions",
        )
        self.assertIn("--permission-mode", cmd)
        self.assertEqual(cmd[cmd.index("--permission-mode") + 1], "bypassPermissions")

        default_cmd = CodeBuddyAdapter.build_resume_command(
            session_id="ccb-smoke-001",
            message="Hello, CodeBuddy!",
            output_path=Path("/tmp/codebuddy-output.txt"),
            permission_mode="default",
        )
        self.assertNotIn("--permission-mode", default_cmd)

        plan_cmd = CodeBuddyAdapter.build_resume_command(
            session_id="ccb-smoke-001",
            message="Hello, CodeBuddy!",
            output_path=Path("/tmp/codebuddy-output.txt"),
            permission_mode="plan",
        )
        self.assertIn("--permission-mode", plan_cmd)
        self.assertEqual(plan_cmd[plan_cmd.index("--permission-mode") + 1], "plan")

        invalid_cmd = CodeBuddyAdapter.build_resume_command(
            session_id="ccb-smoke-001",
            message="Hello, CodeBuddy!",
            output_path=Path("/tmp/codebuddy-output.txt"),
            permission_mode="not-allowed",
        )
        self.assertNotIn("--permission-mode", invalid_cmd)

    def test_codebuddy_adapter_permission_mode_env_fallback_and_runtime_priority(self) -> None:
        with mock.patch.dict("os.environ", {"TASK_DASHBOARD_CODEBUDDY_PERMISSION_MODE": "bypassPermissions"}, clear=False):
            env_cmd = CodeBuddyAdapter.build_resume_command(
                session_id="ccb-smoke-001",
                message="Hello, CodeBuddy!",
                output_path=Path("/tmp/codebuddy-output.txt"),
            )
            priority_cmd = CodeBuddyAdapter.build_resume_command(
                session_id="ccb-smoke-001",
                message="Hello, CodeBuddy!",
                output_path=Path("/tmp/codebuddy-output.txt"),
                permission_mode="default",
            )

        self.assertIn("--permission-mode", env_cmd)
        self.assertEqual(env_cmd[env_cmd.index("--permission-mode") + 1], "bypassPermissions")
        self.assertNotIn("--permission-mode", priority_cmd)

    def test_codebuddy_adapter_build_create_command(self) -> None:
        cmd = CodeBuddyAdapter.build_create_command(
            seed_prompt="Please reply with OK",
            output_path=Path("/tmp/codebuddy-create.txt"),
            model="kimi-k2.6",
        )
        self.assertIn("create", cmd)
        self.assertIn("--output-path", cmd)
        self.assertIn("/tmp/codebuddy-create.txt", cmd)
        self.assertIn("--model", cmd)
        self.assertIn("kimi-k2.6", cmd)

    def test_codebuddy_adapter_supports_model(self) -> None:
        self.assertTrue(CodeBuddyAdapter.supports_model())

    def test_codebuddy_extracts_final_result_from_event_array(self) -> None:
        data = [
            {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "prompt"}]},
            {
                "type": "reasoning",
                "rawContent": [{"type": "reasoning_text", "text": "do not expose"}],
            },
            {
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": "assistant text"}],
            },
            {"type": "result", "subtype": "success", "is_error": False, "result": "final text"},
        ]
        self.assertEqual(extract_final_text(data), "final text")

    def test_codebuddy_extract_final_text_rejects_raw_user_json_result(self) -> None:
        data = [
            {
                "type": "result",
                "subtype": "success",
                "is_error": False,
                "result": '[{"type":"message","role":"user","content":[{"type":"input_text","text":"prompt"}]}]',
            }
        ]
        self.assertEqual(extract_final_text(data), "")

    def test_codebuddy_parse_output_line_ignores_plain_text(self) -> None:
        self.assertIsNone(CodeBuddyAdapter.parse_output_line("普通正文由 runner 写入 last，不进入过程轨"))

    def test_codebuddy_parse_output_line_extracts_compact_json_result(self) -> None:
        parsed = CodeBuddyAdapter.parse_output_line(
            '[{"type":"reasoning","rawContent":[{"text":"hidden"}]},'
            '{"type":"result","subtype":"success","is_error":false,"result":"OK"}]'
        )
        self.assertEqual((parsed or {}).get("type"), "message")
        self.assertEqual((parsed or {}).get("content"), "OK")

    def test_codebuddy_normalizes_process_events_without_final_duplication(self) -> None:
        events = normalize_process_events(
            [
                {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "prompt"}]},
                {"type": "reasoning", "rawContent": [{"type": "reasoning_text", "text": "hidden"}]},
                {
                    "type": "function_call",
                    "callId": "call_001",
                    "name": "Agent",
                    "arguments": '{"description":"Explore project structure","prompt":"long prompt"}',
                },
                {
                    "type": "function_call_result",
                    "callId": "call_001",
                    "name": "Agent",
                    "status": "completed",
                    "output": {"type": "text", "text": "Project structure explored"},
                },
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "Final answer"}],
                },
            ],
            final_text="Final answer",
        )

        self.assertEqual([event["event_type"] for event in events], ["tool_started", "tool_completed"])
        self.assertEqual(events[0]["source"], "codebuddy")
        self.assertIn("调用工具: Agent description: Explore project structure", events[0]["text"])
        self.assertIn("工具完成: Agent Project structure explored", events[1]["text"])

    def test_codebuddy_normalizes_tool_arguments_without_raw_json_or_prompt(self) -> None:
        events = normalize_process_events(
            [
                {
                    "type": "function_call",
                    "callId": "call_ask_001",
                    "name": "AskUserQuestion",
                    "arguments": json.dumps(
                        {
                            "questions": [
                                {"question": "第一条完整问题正文不应出现在过程轨"},
                                {"question": "第二条完整问题正文不应出现在过程轨"},
                            ],
                            "prompt": "完整 prompt 不应出现在过程轨",
                        },
                        ensure_ascii=False,
                    ),
                }
            ]
        )

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event_type"], "tool_started")
        self.assertEqual(events[0]["text"], "调用工具: AskUserQuestion 向用户提问 / 问题 2 项")
        blob = json.dumps(events, ensure_ascii=False)
        self.assertNotIn('{"questions"', blob)
        self.assertNotIn("完整 prompt", blob)
        self.assertNotIn("完整问题正文", blob)

    def test_codebuddy_parse_output_line_extracts_normalized_process_event(self) -> None:
        parsed = CodeBuddyAdapter.parse_output_line(
            '{"type":"tool_call.started","event_type":"tool_started","item_type":"function_call",'
            '"title":"Agent","text":"调用工具: Agent Explore project structure","source":"codebuddy"}'
        )

        self.assertEqual((parsed or {}).get("type"), "tool_call.started")
        self.assertEqual((parsed or {}).get("event_type"), "tool_started")
        self.assertEqual((parsed or {}).get("source"), "codebuddy")


class TestAdapterRegistry(unittest.TestCase):
    """Tests for the adapter registry functions."""

    def test_adapter_registry(self) -> None:
        """Verify that get_adapter returns correct adapters for known CLI types."""
        self.assertEqual(get_adapter("codex"), CodexAdapter)
        self.assertEqual(get_adapter("claude"), ClaudeAdapter)
        self.assertEqual(get_adapter("opencode"), OpenCodeAdapter)
        self.assertEqual(get_adapter("gemini"), GeminiAdapter)
        self.assertEqual(get_adapter("trae"), TraeAdapter)
        self.assertEqual(get_adapter("codebuddy"), CodeBuddyAdapter)

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
