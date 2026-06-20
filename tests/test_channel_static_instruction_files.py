import tempfile
import unittest
from pathlib import Path

from task_dashboard.runtime.channel_admin import (
    StaticInstructionFileConflict,
    create_channel,
    read_channel_agents_md,
    repair_channel_static_instruction_files,
    write_channel_agents_md,
)


def _write_config(config_path: Path, *, channel_name: str | None = "子级02-运行时样本") -> None:
    channel_block = ""
    if channel_name:
        channel_block = f"""

[[projects.channels]]
name = "{channel_name}"
desc = "运行时样本"
cli_type = "codex"
"""
    config_path.write_text(
        f"""
[[projects]]
id = "task_dashboard"
task_root_rel = "任务规划"
{channel_block}
""".strip()
        + "\n",
        encoding="utf-8",
    )


class ChannelStaticInstructionFilesTests(unittest.TestCase):
    def test_read_model_marks_codebuddy_mirror_skipped_when_not_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo_root = Path(td)
            config_path = repo_root / "config.toml"
            channel_root = repo_root / "任务规划" / "子级02-运行时样本"
            channel_root.mkdir(parents=True, exist_ok=True)
            (channel_root / "AGENTS.md").write_text("# AGENTS\n\n规则\n", encoding="utf-8")
            _write_config(config_path)

            payload = read_channel_agents_md(
                project_id="task_dashboard",
                channel_name="子级02-运行时样本",
                config_path=config_path,
                repo_root=repo_root,
            )

            files = payload.get("static_instruction_files") or {}
            self.assertEqual((files.get("source") or {}).get("fileName"), "AGENTS.md")
            mirror = (files.get("mirrors") or [])[0]
            self.assertEqual(mirror.get("cliType"), "codebuddy")
            self.assertEqual(mirror.get("fileName"), "CODEBUDDY.md")
            self.assertEqual(mirror.get("syncStatus"), "skipped")
            self.assertFalse((channel_root / "CODEBUDDY.md").exists())

    def test_repair_creates_managed_codebuddy_mirror_from_agents_md(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo_root = Path(td)
            config_path = repo_root / "config.toml"
            channel_root = repo_root / "任务规划" / "子级02-运行时样本"
            channel_root.mkdir(parents=True, exist_ok=True)
            (channel_root / "AGENTS.md").write_text("# AGENTS\n\n长期规则\n", encoding="utf-8")
            _write_config(config_path)

            payload = repair_channel_static_instruction_files(
                project_id="task_dashboard",
                channel_name="子级02-运行时样本",
                cli_type="codebuddy",
                config_path=config_path,
                repo_root=repo_root,
            )

            mirror_path = channel_root / "CODEBUDDY.md"
            self.assertTrue(mirror_path.exists())
            text = mirror_path.read_text(encoding="utf-8")
            self.assertIn("task_dashboard:managed-mirror", text)
            self.assertIn("source=AGENTS.md", text)
            self.assertIn("cli_type=codebuddy", text)
            self.assertIn("本文件由 task_dashboard 根据 AGENTS.md 自动同步生成", text)
            self.assertIn("# AGENTS\n\n长期规则\n", text)
            mirror = (payload.get("mirrors") or [])[0]
            self.assertEqual(mirror.get("syncStatus"), "synced")
            self.assertTrue(mirror.get("managed"))

    def test_write_agents_md_updates_managed_mirror_and_returns_backup_path(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo_root = Path(td)
            config_path = repo_root / "config.toml"
            channel_root = repo_root / "任务规划" / "子级02-运行时样本"
            channel_root.mkdir(parents=True, exist_ok=True)
            (channel_root / "AGENTS.md").write_text("# AGENTS\n\n旧规则\n", encoding="utf-8")
            _write_config(config_path)
            repair_channel_static_instruction_files(
                project_id="task_dashboard",
                channel_name="子级02-运行时样本",
                cli_type="codebuddy",
                config_path=config_path,
                repo_root=repo_root,
            )

            payload = write_channel_agents_md(
                project_id="task_dashboard",
                channel_name="子级02-运行时样本",
                content="# AGENTS\n\n新规则\n",
                config_path=config_path,
                repo_root=repo_root,
            )

            mirror = ((payload.get("static_instruction_files") or {}).get("mirrors") or [])[0]
            self.assertEqual(mirror.get("syncStatus"), "synced")
            self.assertTrue(mirror.get("backupPath"))
            self.assertTrue(Path(mirror["backupPath"]).exists())
            text = (channel_root / "CODEBUDDY.md").read_text(encoding="utf-8")
            self.assertIn("新规则", text)
            self.assertNotIn("旧规则", text)

    def test_unmanaged_codebuddy_file_blocks_repair_and_agents_save(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo_root = Path(td)
            config_path = repo_root / "config.toml"
            channel_root = repo_root / "任务规划" / "子级02-运行时样本"
            channel_root.mkdir(parents=True, exist_ok=True)
            agents_path = channel_root / "AGENTS.md"
            agents_path.write_text("# AGENTS\n\n旧规则\n", encoding="utf-8")
            (channel_root / "CODEBUDDY.md").write_text("# 手工 CodeBuddy 规则\n", encoding="utf-8")
            _write_config(config_path)

            with self.assertRaises(StaticInstructionFileConflict):
                repair_channel_static_instruction_files(
                    project_id="task_dashboard",
                    channel_name="子级02-运行时样本",
                    cli_type="codebuddy",
                    config_path=config_path,
                    repo_root=repo_root,
                )

            with self.assertRaises(StaticInstructionFileConflict):
                write_channel_agents_md(
                    project_id="task_dashboard",
                    channel_name="子级02-运行时样本",
                    content="# AGENTS\n\n新规则\n",
                    config_path=config_path,
                    repo_root=repo_root,
                )
            self.assertEqual(agents_path.read_text(encoding="utf-8"), "# AGENTS\n\n旧规则\n")

    def test_create_channel_with_codebuddy_creates_managed_mirror(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo_root = Path(td)
            (repo_root / "任务规划").mkdir(parents=True, exist_ok=True)
            config_path = repo_root / "config.toml"
            _write_config(config_path, channel_name=None)

            result = create_channel(
                project_id="task_dashboard",
                channel_name="子级03-CodeBuddy样本",
                channel_desc="CodeBuddy 样本",
                cli_type="codebuddy",
                config_path=config_path,
                repo_root=repo_root,
                atomic_write_text=lambda path, text: path.write_text(text, encoding="utf-8"),
                agents_md_role="developer",
            )

            channel_root = repo_root / "任务规划" / "子级03-CodeBuddy样本"
            self.assertTrue((channel_root / "AGENTS.md").exists())
            self.assertTrue((channel_root / "CODEBUDDY.md").exists())
            self.assertEqual(
                ((result.get("static_instruction_files") or {}).get("mirrors") or [])[0].get("syncStatus"),
                "synced",
            )


if __name__ == "__main__":
    unittest.main()
