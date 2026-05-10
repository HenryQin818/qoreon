import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from task_dashboard.runtime.execution_command import prepare_process_spawn


class PrepareProcessSpawnTests(unittest.TestCase):
    def test_prepare_process_spawn_keeps_direct_mode_for_ascii_path(self) -> None:
        with tempfile.TemporaryDirectory(prefix="td-ascii-") as td:
            cwd = Path(td)
            result = prepare_process_spawn(
                cli_type="codex",
                requested_cwd=cwd,
                cmd=["/usr/local/bin/codex", "exec", "resume", "sid", "hello"],
            )
            self.assertEqual(result.get("mode"), "direct")
            self.assertEqual(Path(result.get("spawn_cwd") or ""), cwd)
            self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", list(result.get("cmd") or []))

    def test_prepare_process_spawn_uses_ascii_mirror_for_codex_non_ascii_path(self) -> None:
        with tempfile.TemporaryDirectory(prefix="td-root-") as td:
            source_root = Path(td) / "中文项目"
            nested = source_root / "subdir"
            nested.mkdir(parents=True, exist_ok=True)
            (source_root / ".git").mkdir()
            (source_root / "server.py").write_text("print('ok')\n", encoding="utf-8")
            result = prepare_process_spawn(
                cli_type="codex",
                requested_cwd=nested,
                cmd=["/usr/local/bin/codex", "exec", "resume", "sid", "hello"],
            )
            spawn_cwd = Path(result.get("spawn_cwd") or "")
            self.assertEqual(result.get("mode"), "codex_ascii_workspace_mirror")
            str(spawn_cwd).encode("ascii")
            self.assertTrue(spawn_cwd.exists())
            self.assertTrue((spawn_cwd.parent / ".task_dashboard_source_root").exists())
            self.assertTrue((spawn_cwd.parent / "server.py").is_symlink())
            self.assertEqual(str(result.get("mirrored_from") or ""), str(source_root.resolve()))
            self.assertFalse(spawn_cwd.is_symlink())
            str(spawn_cwd.resolve()).encode("ascii")
            cmd = list(result.get("cmd") or [])
            self.assertIn("-C", cmd)
            self.assertEqual(cmd[cmd.index("-C") + 1], str(spawn_cwd))

    def test_prepare_process_spawn_uses_ascii_mirror_for_project_privileged_full(self) -> None:
        with tempfile.TemporaryDirectory(prefix="td-root-") as td:
            source_root = Path(td) / "中文项目"
            nested = source_root / "subdir"
            nested.mkdir(parents=True, exist_ok=True)
            (source_root / ".git").mkdir()
            result = prepare_process_spawn(
                cli_type="codex",
                requested_cwd=nested,
                cmd=["/usr/local/bin/codex", "exec", "resume", "sid", "hello"],
                execution_profile="project_privileged_full",
            )
            spawn_cwd = Path(result.get("spawn_cwd") or "")
            self.assertEqual(result.get("mode"), "codex_ascii_workspace_mirror")
            self.assertNotEqual(spawn_cwd, nested)
            str(spawn_cwd).encode("ascii")
            str(spawn_cwd.resolve()).encode("ascii")
            self.assertEqual(str(result.get("execution_profile") or ""), "project_privileged_full")
            cmd = list(result.get("cmd") or [])
            self.assertIn("--dangerously-bypass-approvals-and-sandbox", cmd)
            self.assertIn("-C", cmd)
            self.assertEqual(cmd[cmd.index("-C") + 1], str(spawn_cwd))

    def test_prepare_process_spawn_uses_workspace_write_for_privileged(self) -> None:
        with tempfile.TemporaryDirectory(prefix="td-ascii-") as td:
            cwd = Path(td)
            result = prepare_process_spawn(
                cli_type="codex",
                requested_cwd=cwd,
                cmd=["/usr/local/bin/codex", "exec", "resume", "sid", "hello"],
                execution_profile="privileged",
            )
            cmd = list(result.get("cmd") or [])
            self.assertIn("--sandbox", cmd)
            self.assertIn("workspace-write", cmd)
            self.assertIn("--add-dir", cmd)
            self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", cmd)

    def test_prepare_process_spawn_prefers_codex_bin_dir_in_path(self) -> None:
        with tempfile.TemporaryDirectory(prefix="td-codex-bin-") as td:
            cwd = Path(td)
            bin_dir = cwd / "bin"
            bin_dir.mkdir(parents=True, exist_ok=True)
            fake_codex = bin_dir / "codex"
            fake_codex.write_text("#!/bin/sh\n", encoding="utf-8")
            result = prepare_process_spawn(
                cli_type="codex",
                requested_cwd=cwd,
                cmd=[str(fake_codex), "exec", "resume", "sid", "hello"],
            )
            spawn_env = dict(result.get("spawn_env") or {})
            path_parts = [item for item in str(spawn_env.get("PATH") or "").split(":") if item]
            self.assertTrue(path_parts)
            self.assertEqual(path_parts[0], str(bin_dir))

    def test_prepare_process_spawn_adds_codex_only_vps_proxy_env(self) -> None:
        with tempfile.TemporaryDirectory(prefix="td-ascii-") as td:
            with patch.dict("os.environ", {"PATH": "/usr/bin", "TASK_DASHBOARD_CODEX_ROUTE_MODE": "strict_vps"}, clear=True):
                result = prepare_process_spawn(
                    cli_type="codex",
                    requested_cwd=Path(td),
                    cmd=["/usr/local/bin/codex", "exec", "resume", "sid", "hello"],
                )
            spawn_env = dict(result.get("spawn_env") or {})
            self.assertEqual(spawn_env.get("HTTP_PROXY"), "http://127.0.0.1:10809")
            self.assertEqual(spawn_env.get("HTTPS_PROXY"), "http://127.0.0.1:10809")
            self.assertEqual(spawn_env.get("ALL_PROXY"), "socks5h://127.0.0.1:10808")
            self.assertEqual(spawn_env.get("http_proxy"), "http://127.0.0.1:10809")
            self.assertEqual(spawn_env.get("all_proxy"), "socks5h://127.0.0.1:10808")
            self.assertIn("127.0.0.1", str(spawn_env.get("NO_PROXY") or ""))
            self.assertEqual(spawn_env.get("CODEX_VPS_PROXY_MODE"), "strict-vps")

    def test_prepare_process_spawn_can_disable_codex_vps_proxy_env(self) -> None:
        with tempfile.TemporaryDirectory(prefix="td-ascii-") as td:
            with patch.dict(
                "os.environ",
                {
                    "PATH": "/usr/bin",
                    "TASK_DASHBOARD_CODEX_ROUTE_MODE": "direct",
                    "HTTP_PROXY": "http://127.0.0.1:10809",
                    "HTTPS_PROXY": "http://127.0.0.1:10809",
                    "ALL_PROXY": "socks5h://127.0.0.1:10808",
                },
                clear=True,
            ):
                result = prepare_process_spawn(
                    cli_type="codex",
                    requested_cwd=Path(td),
                    cmd=["/usr/local/bin/codex", "exec", "resume", "sid", "hello"],
                )
            spawn_env = dict(result.get("spawn_env") or {})
            self.assertNotIn("HTTP_PROXY", spawn_env)
            self.assertNotIn("HTTPS_PROXY", spawn_env)
            self.assertNotIn("ALL_PROXY", spawn_env)
            self.assertEqual(spawn_env.get("CODEX_VPS_PROXY_MODE"), "direct")

    def test_prepare_process_spawn_does_not_add_vps_proxy_env_for_non_codex(self) -> None:
        with tempfile.TemporaryDirectory(prefix="td-ascii-") as td:
            with patch.dict("os.environ", {"PATH": "/usr/bin"}, clear=True):
                result = prepare_process_spawn(
                    cli_type="gemini",
                    requested_cwd=Path(td),
                    cmd=["/usr/local/bin/gemini", "hello"],
                )
            spawn_env = dict(result.get("spawn_env") or {})
            self.assertNotIn("HTTP_PROXY", spawn_env)
            self.assertNotIn("HTTPS_PROXY", spawn_env)
            self.assertNotIn("ALL_PROXY", spawn_env)
            self.assertNotIn("CODEX_VPS_PROXY_MODE", spawn_env)


if __name__ == "__main__":
    unittest.main()
