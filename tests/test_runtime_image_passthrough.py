import tempfile
import unittest
from pathlib import Path

from task_dashboard.runtime.execution_runtime import (
    _build_claude_image_path_fallback_prompt,
    _build_claude_image_path_fallback_summary,
    _build_runtime_attachment_summary,
    _count_codex_image_args,
    _metadata_without_runtime_passthrough_attachments,
    _resolve_runtime_image_attachments,
)


class RuntimeImagePassthroughTests(unittest.TestCase):
    def test_resolves_controlled_image_attachment_and_excludes_prompt_copy(self) -> None:
        with tempfile.TemporaryDirectory(prefix="td-runs-") as td:
            runs_root = Path(td)
            attachment_dir = runs_root / "attachments"
            attachment_dir.mkdir(parents=True, exist_ok=True)
            image_path = attachment_dir / "demo.png"
            image_path.write_bytes(b"\x89PNG\r\n\x1a\n")
            meta = {
                "attachments": [
                    {
                        "attachment_id": "att-image-1",
                        "filename": "demo.png",
                        "originalName": "demo.png",
                        "url": "/.runs/attachments/demo.png",
                        "mimeType": "image/png",
                    },
                    {
                        "attachment_id": "att-text-1",
                        "filename": "note.txt",
                        "url": "/.runs/attachments/note.txt",
                    },
                ]
            }

            resolved = _resolve_runtime_image_attachments(meta, runs_root)
            self.assertEqual(len(resolved), 1)
            self.assertEqual(resolved[0]["resolved_local_path"], str(image_path.resolve()))
            self.assertEqual(resolved[0]["content_type"], "image/png")
            self.assertTrue(resolved[0]["sha256"])

            prompt_meta = _metadata_without_runtime_passthrough_attachments(meta, resolved)
            self.assertEqual(len(prompt_meta["attachments"]), 1)
            self.assertEqual(prompt_meta["attachments"][0]["attachment_id"], "att-text-1")

    def test_runtime_attachment_summary_is_redacted_until_cli_invoked(self) -> None:
        attachment = {
            "attachment_id": "att-image-1",
            "message_part_id": "part-1",
            "filename": "demo.png",
            "content_type": "image/png",
            "size_bytes": 8,
            "sha256": "hash-demo",
            "resolved_local_path": "/private/path/demo.png",
        }

        pending = _build_runtime_attachment_summary(
            [attachment],
            adapter_image_arg_count=1,
            actual_cli_invoked=False,
        )
        completed = _build_runtime_attachment_summary(
            [attachment],
            adapter_image_arg_count=1,
            actual_cli_invoked=True,
        )

        self.assertFalse(pending["image_passed"])
        self.assertTrue(completed["image_passed"])
        self.assertTrue(completed["path_redacted"])
        self.assertNotIn("resolved_local_path", completed["attachments"][0])

    def test_count_codex_image_args_supports_short_and_long_flags(self) -> None:
        self.assertEqual(
            _count_codex_image_args(["codex", "exec", "-i", "/tmp/a.png", "--image=/tmp/b.png"]),
            2,
        )

    def test_claude_image_fallback_prompt_uses_absolute_paths_and_read_hint(self) -> None:
        with tempfile.TemporaryDirectory(prefix="td-runs-") as td:
            image_path = Path(td) / "attachments" / "demo.png"
            image_path.parent.mkdir(parents=True, exist_ok=True)
            image_path.write_bytes(b"\x89PNG\r\n\x1a\n")
            attachment = {
                "attachment_id": "att-image-1",
                "filename": "demo.png",
                "content_type": "image/png",
                "size_bytes": 8,
                "sha256": "hash-demo",
                "resolved_local_path": str(image_path.resolve()),
            }

            prompt = _build_claude_image_path_fallback_prompt([attachment])

            self.assertIn("[CCB 图片附件读取提示]", prompt)
            self.assertIn(str(image_path.resolve()), prompt)
            self.assertIn("Read/读取工具", prompt)
            self.assertIn("基于图片内容作答", prompt)

    def test_claude_image_fallback_prompt_ignores_missing_paths(self) -> None:
        self.assertEqual(
            _build_claude_image_path_fallback_prompt([{"filename": "demo.png", "content_type": "image/png"}]),
            "",
        )

    def test_claude_image_fallback_summary_redacts_paths(self) -> None:
        summary = _build_claude_image_path_fallback_summary(
            [
                {
                    "attachment_id": "att-image-1",
                    "message_part_id": "part-1",
                    "filename": "demo.png",
                    "content_type": "image/png",
                    "size_bytes": 8,
                    "sha256": "hash-demo",
                    "resolved_local_path": "/private/path/demo.png",
                }
            ]
        )

        self.assertTrue(summary["enabled"])
        self.assertEqual(summary["adapter_arg_kind"], "claude_prompt_path_fallback")
        self.assertTrue(summary["prompt_contains_absolute_paths"])
        self.assertTrue(summary["requires_read_tool"])
        self.assertTrue(summary["path_redacted"])
        self.assertNotIn("resolved_local_path", summary["attachments"][0])


if __name__ == "__main__":
    unittest.main()
