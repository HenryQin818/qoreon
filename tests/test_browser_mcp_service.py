import tempfile
import unittest
from pathlib import Path

from task_dashboard.browser_mcp_service import (
    BrowserConfigurationError,
    browser_capabilities,
    build_browser_run_meta,
    effective_browser_mode,
    normalize_browser_mode,
    prepare_playwright_profile_dir,
    resolve_playwright_profile_dir,
    resolve_browser_plugin_command,
)


class BrowserMcpServiceTests(unittest.TestCase):
    @staticmethod
    def _plugin_env(root: Path) -> dict[str, str]:
        command = root / "node_repl"
        command.write_text("placeholder", encoding="utf-8")
        command.chmod(0o755)
        config_root = root / "codex"
        config_root.mkdir()
        (config_root / "config.toml").write_text(
            f'[mcp_servers.node_repl]\ncommand = "{command}"\n',
            encoding="utf-8",
        )
        return {"CODEX_HOME": str(config_root), "TASK_DASHBOARD_CODEX_BROWSER_PLUGIN": "1"}

    def test_browser_mode_defaults_to_project_collab_and_keeps_auto_compatible(self) -> None:
        self.assertEqual("collab", normalize_browser_mode(""))
        self.assertEqual("auto", normalize_browser_mode("agent-choice"))
        self.assertEqual("collab", effective_browser_mode("auto"))
        self.assertEqual("collab", normalize_browser_mode("visible"))

    def test_auto_mode_resolves_to_single_persistent_playwright_backend(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            env = self._plugin_env(Path(td))
            meta = build_browser_run_meta(
                project_id="task_dashboard",
                cli_type="codex",
                requested_mode="auto",
                env=env,
            )
            self.assertEqual("collab", meta["browser_effective_mode"])
            self.assertEqual("playwright", meta["browser_backend"])
            self.assertEqual(["playwright"], meta["browser_available_backends"])
            self.assertTrue(meta["browser_persistent"])
            self.assertTrue(meta["browser_headed"])
            self.assertEqual("project", meta["browser_profile_scope"])

    def test_default_mode_uses_project_collab_when_plugin_is_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            meta = build_browser_run_meta(
                project_id="task_dashboard",
                cli_type="codex",
                requested_mode=None,
                env={"CODEX_HOME": td, "TASK_DASHBOARD_CODEX_PLAYWRIGHT_MCP": "1"},
            )
            self.assertEqual("collab", meta["browser_mode"])
            self.assertEqual("collab", meta["browser_effective_mode"])
            self.assertEqual("playwright", meta["browser_backend"])
            self.assertEqual(["playwright"], meta["browser_available_backends"])

    def test_collab_profile_path_is_opaque_stable_and_project_scoped(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            env = {"TASK_DASHBOARD_CODEX_PLAYWRIGHT_PROFILE_ROOT": td}
            alpha_first = resolve_playwright_profile_dir("Project-A", env)
            alpha_second = resolve_playwright_profile_dir("project-a", env)
            beta = resolve_playwright_profile_dir("project-b", env)
            self.assertEqual(alpha_first, alpha_second)
            self.assertNotEqual(alpha_first, beta)
            self.assertEqual(Path(td).resolve(), alpha_first.parent)
            self.assertNotIn("project-a", alpha_first.name)

    def test_collab_requires_project_and_absolute_profile_root(self) -> None:
        with self.assertRaises(BrowserConfigurationError) as missing:
            resolve_playwright_profile_dir("")
        self.assertEqual("browser_project_required", missing.exception.code)
        with self.assertRaises(BrowserConfigurationError) as relative:
            resolve_playwright_profile_dir(
                "project-a",
                {"TASK_DASHBOARD_CODEX_PLAYWRIGHT_PROFILE_ROOT": "relative/path"},
            )
        self.assertEqual("browser_profile_root_invalid", relative.exception.code)

    def test_collab_profile_is_created_with_user_only_permissions(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            profile = prepare_playwright_profile_dir(
                "project-a",
                {"TASK_DASHBOARD_CODEX_PLAYWRIGHT_PROFILE_ROOT": str(Path(td) / "profiles")},
            )
            self.assertTrue(profile.is_dir())
            self.assertEqual(0o700, profile.stat().st_mode & 0o777)
            self.assertEqual(0o700, profile.parent.stat().st_mode & 0o777)

    def test_ephemeral_remains_headless_and_non_persistent(self) -> None:
        meta = build_browser_run_meta(
            project_id="task_dashboard",
            cli_type="codex",
            requested_mode="ephemeral",
            env={"TASK_DASHBOARD_CODEX_PLAYWRIGHT_MCP": "1", "TASK_DASHBOARD_CODEX_BROWSER_PLUGIN": "0"},
        )
        self.assertEqual("ephemeral", meta["browser_effective_mode"])
        self.assertFalse(meta["browser_persistent"])
        self.assertFalse(meta["browser_headed"])
        self.assertEqual("temporary", meta["browser_profile_scope"])

    def test_explicit_plugin_mode_requires_valid_node_repl_config(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            env = self._plugin_env(root)
            self.assertEqual(str((root / "node_repl").resolve()), resolve_browser_plugin_command(env))
            meta = build_browser_run_meta(
                project_id="task_dashboard",
                cli_type="codex",
                requested_mode="plugin",
                env=env,
            )
            self.assertEqual("plugin", meta["browser_effective_mode"])
            self.assertEqual("browser_plugin", meta["browser_backend"])

        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(BrowserConfigurationError) as missing:
                build_browser_run_meta(
                    project_id="task_dashboard",
                    cli_type="codex",
                    requested_mode="plugin",
                    env={"CODEX_HOME": td},
                )
            self.assertEqual("browser_plugin_unavailable", missing.exception.code)

    def test_plugin_command_must_be_executable(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            command = root / "node_repl"
            command.write_text("placeholder", encoding="utf-8")
            config_root = root / "codex"
            config_root.mkdir()
            (config_root / "config.toml").write_text(
                f'[mcp_servers.node_repl]\ncommand = "{command}"\n',
                encoding="utf-8",
            )
            env = {"CODEX_HOME": str(config_root), "TASK_DASHBOARD_CODEX_BROWSER_PLUGIN": "1"}
            with self.assertRaises(BrowserConfigurationError) as unavailable:
                resolve_browser_plugin_command(env)
            self.assertEqual("browser_plugin_unavailable", unavailable.exception.code)

    def test_capabilities_advertise_collab_as_default_without_dual_backend_choice(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            env = self._plugin_env(root)
            capabilities = browser_capabilities(env=env)
            self.assertFalse(capabilities["agent_choice"])
            self.assertEqual("collab", capabilities["default_mode"])
            self.assertEqual("collab", capabilities["auto_compatibility_mode"])
            self.assertEqual(["playwright", "browser_plugin"], capabilities["available_backends"])
            self.assertIn("auto", capabilities["available_modes"])
            self.assertIn("collab", capabilities["available_modes"])


if __name__ == "__main__":
    unittest.main()
