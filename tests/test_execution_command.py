import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from task_dashboard.adapters.claude_adapter import ClaudeAdapter
from task_dashboard.runtime.execution_command import build_execution_command, prepare_process_spawn


class BuildExecutionCommandTests(unittest.TestCase):
    def test_build_execution_command_passes_permission_mode_only_to_codebuddy(self) -> None:
        class _CodeBuddyAdapter:
            @classmethod
            def build_resume_command(cls, **kwargs):
                permission_mode = str(kwargs.get("permission_mode") or "")
                cmd = ["codebuddy-runner", "resume", kwargs["session_id"]]
                if permission_mode:
                    cmd.extend(["--permission-mode", permission_mode])
                return cmd

        bundle = build_execution_command(
            adapter_cls=_CodeBuddyAdapter,
            session_id="sid-codebuddy",
            message="hello",
            output_path=Path("/tmp/out.txt"),
            profile_label="",
            resolved_model="",
            resolved_reasoning="",
            cli_type="codebuddy",
            supports_model=False,
            permission_mode="bypassPermissions",
            profile_not_found_recent=lambda _cli_type, _profile: (False, 0.0),
        )

        self.assertIn("--permission-mode", bundle["cmd"])
        self.assertEqual(bundle["cmd"][bundle["cmd"].index("--permission-mode") + 1], "bypassPermissions")

    def test_build_execution_command_passes_permission_mode_to_claude(self) -> None:
        class _ClaudeAdapter:
            @classmethod
            def build_resume_command(cls, **kwargs):
                permission_mode = str(kwargs.get("permission_mode") or "")
                model = str(kwargs.get("model") or "")
                cmd = ["claude-runner", "resume", "--resume", kwargs["session_id"]]
                if model:
                    cmd.extend(["--model", model])
                if permission_mode:
                    cmd.extend(["--permission-mode", permission_mode])
                return cmd

        bundle = build_execution_command(
            adapter_cls=_ClaudeAdapter,
            session_id="sid-claude",
            message="hello",
            output_path=Path("/tmp/out.txt"),
            profile_label="",
            resolved_model="claude-sonnet-4-20250514",
            resolved_reasoning="",
            cli_type="claude",
            supports_model=True,
            permission_mode="plan",
            profile_not_found_recent=lambda _cli_type, _profile: (False, 0.0),
        )

        self.assertIn("--permission-mode", bundle["cmd"])
        self.assertEqual(bundle["cmd"][bundle["cmd"].index("--permission-mode") + 1], "plan")
        self.assertIn("--model", bundle["cmd"])
        self.assertEqual(bundle["cmd"][bundle["cmd"].index("--model") + 1], "claude-sonnet-4-6")

    def test_build_execution_command_defaults_invalid_claude_model(self) -> None:
        class _ClaudeAdapter:
            @classmethod
            def build_resume_command(cls, **kwargs):
                return ["claude-runner", "--model", str(kwargs.get("model") or ""), "resume"]

        bundle = build_execution_command(
            adapter_cls=_ClaudeAdapter,
            session_id="sid-claude",
            message="hello",
            output_path=Path("/tmp/out.txt"),
            profile_label="",
            resolved_model="辅助04-原型设计",
            resolved_reasoning="",
            cli_type="claude",
            supports_model=True,
            permission_mode="",
            profile_not_found_recent=lambda _cli_type, _profile: (False, 0.0),
        )

        self.assertEqual(bundle["cmd"][bundle["cmd"].index("--model") + 1], "claude-opus-4-8")

    def test_build_execution_command_normalizes_claude_fable_alias(self) -> None:
        class _ClaudeAdapter:
            @classmethod
            def build_resume_command(cls, **kwargs):
                return ["claude-runner", "--model", str(kwargs.get("model") or ""), "resume"]

        bundle = build_execution_command(
            adapter_cls=_ClaudeAdapter,
            session_id="sid-claude",
            message="hello",
            output_path=Path("/tmp/out.txt"),
            profile_label="",
            resolved_model="fable5",
            resolved_reasoning="",
            cli_type="claude",
            supports_model=True,
            permission_mode="",
            profile_not_found_recent=lambda _cli_type, _profile: (False, 0.0),
        )

        self.assertEqual(bundle["cmd"][bundle["cmd"].index("--model") + 1], "claude-fable-5")

    def test_build_execution_command_does_not_pass_permission_mode_to_other_cli(self) -> None:
        class _CodexAdapter:
            @classmethod
            def build_resume_command(
                cls,
                *,
                session_id,
                message,
                output_path,
                profile_label="",
                model="",
                reasoning_effort="",
            ):
                _ = message, output_path, profile_label, model, reasoning_effort
                return ["codex", "resume", session_id]

        bundle = build_execution_command(
            adapter_cls=_CodexAdapter,
            session_id="sid-codex",
            message="hello",
            output_path=Path("/tmp/out.txt"),
            profile_label="",
            resolved_model="",
            resolved_reasoning="",
            cli_type="codex",
            supports_model=False,
            permission_mode="bypassPermissions",
            profile_not_found_recent=lambda _cli_type, _profile: (False, 0.0),
        )

        self.assertNotIn("--permission-mode", bundle["cmd"])

    def test_build_execution_command_passes_attachments_only_to_codex(self) -> None:
        class _CodexAdapter:
            @classmethod
            def build_resume_command(cls, **kwargs):
                cmd = ["codex", "exec"]
                for item in kwargs.get("attachments") or []:
                    cmd.extend(["-i", item["resolved_local_path"]])
                cmd.extend(["resume", kwargs["session_id"], "--", kwargs["message"]])
                return cmd

        bundle = build_execution_command(
            adapter_cls=_CodexAdapter,
            session_id="sid-codex",
            message="hello",
            output_path=Path("/tmp/out.txt"),
            profile_label="",
            resolved_model="",
            resolved_reasoning="",
            cli_type="codex",
            supports_model=False,
            profile_not_found_recent=lambda _cli_type, _profile: (False, 0.0),
            attachments=[{"resolved_local_path": "/tmp/demo.png"}],
        )

        self.assertIn("-i", bundle["cmd"])
        self.assertEqual(bundle["cmd"][bundle["cmd"].index("-i") + 1], "/tmp/demo.png")

    def test_build_execution_command_does_not_pass_attachments_to_non_codex(self) -> None:
        class _GeminiAdapter:
            @classmethod
            def build_resume_command(
                cls,
                *,
                session_id,
                message,
                output_path,
                profile_label="",
                model="",
                reasoning_effort="",
            ):
                _ = message, output_path, profile_label, model, reasoning_effort
                return ["gemini", "--resume", session_id]

        bundle = build_execution_command(
            adapter_cls=_GeminiAdapter,
            session_id="sid-gemini",
            message="hello",
            output_path=Path("/tmp/out.txt"),
            profile_label="",
            resolved_model="",
            resolved_reasoning="",
            cli_type="gemini",
            supports_model=False,
            profile_not_found_recent=lambda _cli_type, _profile: (False, 0.0),
            attachments=[{"resolved_local_path": "/tmp/demo.png"}],
        )

        self.assertNotIn("-i", bundle["cmd"])


class PrepareProcessSpawnTests(unittest.TestCase):
    def test_claude_adapter_resolve_session_cwd_reads_jsonl_metadata(self) -> None:
        with tempfile.TemporaryDirectory(prefix="td-claude-home-") as home_td:
            with tempfile.TemporaryDirectory(prefix="td-claude-cwd-") as cwd_td:
                session_id = "019f700e-000e-700e-800e-00000000000e"
                session_dir = Path(home_td) / "projects" / "encoded-cwd"
                session_dir.mkdir(parents=True, exist_ok=True)
                session_file = session_dir / f"{session_id}.jsonl"
                session_file.write_text(
                    '{"type":"summary"}\n'
                    f'{{"type":"user","cwd":"{cwd_td}","sessionId":"{session_id}"}}\n',
                    encoding="utf-8",
                )

                with patch.dict("os.environ", {"CLAUDE_HOME": home_td}, clear=False):
                    self.assertEqual(ClaudeAdapter.resolve_session_cwd(session_id), cwd_td)

    def test_prepare_process_spawn_uses_claude_session_cwd_for_resume(self) -> None:
        with tempfile.TemporaryDirectory(prefix="td-requested-") as requested_td:
            with tempfile.TemporaryDirectory(prefix="td-claude-session-") as session_td:
                session_id = "019f700e-000e-700e-800e-00000000000e"
                with patch.object(ClaudeAdapter, "resolve_session_cwd", return_value=session_td):
                    result = prepare_process_spawn(
                        cli_type="claude",
                        requested_cwd=Path(requested_td),
                        cmd=["claude", "--resume", session_id, "--print", "hello"],
                    )

                self.assertEqual(result.get("mode"), "claude_session_cwd")
                self.assertEqual(Path(result.get("spawn_cwd") or ""), Path(session_td))
                self.assertEqual(list(result.get("cmd") or [])[2], session_id)

    def test_prepare_process_spawn_uses_claude_session_cwd_for_short_resume_flag(self) -> None:
        with tempfile.TemporaryDirectory(prefix="td-requested-") as requested_td:
            with tempfile.TemporaryDirectory(prefix="td-claude-session-") as session_td:
                session_id = "019f700e-000e-700e-800e-00000000000e"
                with patch.object(ClaudeAdapter, "resolve_session_cwd", return_value=session_td):
                    result = prepare_process_spawn(
                        cli_type="claude",
                        requested_cwd=Path(requested_td),
                        cmd=["claude", "-r", session_id, "--print", "hello"],
                    )

                self.assertEqual(result.get("mode"), "claude_session_cwd")
                self.assertEqual(Path(result.get("spawn_cwd") or ""), Path(session_td))

    def test_prepare_process_spawn_falls_back_when_claude_session_cwd_missing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="td-requested-") as requested_td:
            session_id = "019f700e-000e-700e-800e-00000000000e"
            with patch.object(ClaudeAdapter, "resolve_session_cwd", return_value=""):
                result = prepare_process_spawn(
                    cli_type="claude",
                    requested_cwd=Path(requested_td),
                    cmd=["claude", "--resume", session_id, "--print", "hello"],
                )

            self.assertEqual(result.get("mode"), "direct")
            self.assertEqual(Path(result.get("spawn_cwd") or ""), Path(requested_td))

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
            self.assertEqual(spawn_env.get("CODEX_VPS_PROXY_MODE"), "local-default")

    def test_prepare_process_spawn_local_default_keeps_non_vps_proxy_env(self) -> None:
        with tempfile.TemporaryDirectory(prefix="td-ascii-") as td:
            with patch.dict(
                "os.environ",
                {
                    "PATH": "/usr/bin",
                    "TASK_DASHBOARD_CODEX_ROUTE_MODE": "direct",
                    "HTTP_PROXY": "http://127.0.0.1:7897",
                    "HTTPS_PROXY": "http://127.0.0.1:7897",
                    "ALL_PROXY": "socks5h://127.0.0.1:7897",
                },
                clear=True,
            ):
                result = prepare_process_spawn(
                    cli_type="codex",
                    requested_cwd=Path(td),
                    cmd=["/usr/local/bin/codex", "exec", "resume", "sid", "hello"],
                )
            spawn_env = dict(result.get("spawn_env") or {})
            self.assertEqual(spawn_env.get("HTTP_PROXY"), "http://127.0.0.1:7897")
            self.assertEqual(spawn_env.get("HTTPS_PROXY"), "http://127.0.0.1:7897")
            self.assertEqual(spawn_env.get("ALL_PROXY"), "socks5h://127.0.0.1:7897")
            self.assertEqual(spawn_env.get("CODEX_VPS_PROXY_MODE"), "local-default")

    def test_prepare_process_spawn_can_follow_system_proxy_env(self) -> None:
        with tempfile.TemporaryDirectory(prefix="td-ascii-") as td:
            with patch.dict(
                "os.environ",
                {
                    "PATH": "/usr/bin",
                    "TASK_DASHBOARD_CODEX_ROUTE_MODE": "system_proxy",
                    "HTTP_PROXY": "http://127.0.0.1:7897",
                    "HTTPS_PROXY": "http://127.0.0.1:7897",
                    "ALL_PROXY": "http://127.0.0.1:7897",
                    "NO_PROXY": "127.0.0.1,localhost",
                },
                clear=True,
            ):
                result = prepare_process_spawn(
                    cli_type="codex",
                    requested_cwd=Path(td),
                    cmd=["/usr/local/bin/codex", "exec", "resume", "sid", "hello"],
                )
            spawn_env = dict(result.get("spawn_env") or {})
            self.assertEqual(spawn_env.get("HTTP_PROXY"), "http://127.0.0.1:7897")
            self.assertEqual(spawn_env.get("HTTPS_PROXY"), "http://127.0.0.1:7897")
            self.assertEqual(spawn_env.get("ALL_PROXY"), "http://127.0.0.1:7897")
            self.assertEqual(spawn_env.get("http_proxy"), "http://127.0.0.1:7897")
            self.assertEqual(spawn_env.get("all_proxy"), "http://127.0.0.1:7897")
            self.assertEqual(spawn_env.get("CODEX_VPS_PROXY_MODE"), "system-proxy")

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

    def test_prepare_process_spawn_adds_project_pythonpath_for_codebuddy_runner(self) -> None:
        with tempfile.TemporaryDirectory(prefix="td-codebuddy-") as td:
            with patch.dict("os.environ", {"PATH": "/usr/bin"}, clear=True):
                result = prepare_process_spawn(
                    cli_type="codebuddy",
                    requested_cwd=Path(td),
                    cmd=[
                        "python3",
                        "-m",
                        "task_dashboard.adapters.codebuddy_runner",
                        "create",
                    ],
                )
            spawn_env = dict(result.get("spawn_env") or {})
            pythonpath_parts = [
                item for item in str(spawn_env.get("PYTHONPATH") or "").split(":") if item
            ]
            self.assertTrue(pythonpath_parts)
            self.assertEqual(pythonpath_parts[0], str(Path(__file__).resolve().parents[1]))
            self.assertNotIn("CODEX_VPS_PROXY_MODE", spawn_env)

    def test_prepare_process_spawn_adds_project_pythonpath_for_claude_runner_session_cwd(self) -> None:
        with tempfile.TemporaryDirectory(prefix="td-requested-") as requested_td:
            with tempfile.TemporaryDirectory(prefix="td-claude-session-") as session_td:
                session_id = "019f700e-000e-700e-800e-00000000000e"
                with patch.dict("os.environ", {"PATH": "/usr/bin"}, clear=True):
                    with patch.object(ClaudeAdapter, "resolve_session_cwd", return_value=session_td):
                        result = prepare_process_spawn(
                            cli_type="claude",
                            requested_cwd=Path(requested_td),
                            cmd=[
                                "python3",
                                "-m",
                                "task_dashboard.adapters.claude_runner",
                                "--message",
                                "hello",
                                "resume",
                                "--resume",
                                session_id,
                            ],
                        )

                self.assertEqual(result.get("mode"), "claude_session_cwd")
                self.assertEqual(Path(result.get("spawn_cwd") or ""), Path(session_td))
                spawn_env = dict(result.get("spawn_env") or {})
                pythonpath_parts = [
                    item for item in str(spawn_env.get("PYTHONPATH") or "").split(":") if item
                ]
                self.assertTrue(pythonpath_parts)
                self.assertEqual(pythonpath_parts[0], str(Path(__file__).resolve().parents[1]))
                self.assertNotIn("CODEX_VPS_PROXY_MODE", spawn_env)


if __name__ == "__main__":
    unittest.main()
