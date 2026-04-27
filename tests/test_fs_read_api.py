import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import server
from task_dashboard.routes.main import RouteDispatcher


def _json_response(handler, status, payload):
    handler.status = status
    handler.payload = payload


class FsReadApiTests(unittest.TestCase):
    def test_fs_read_dir_entries_include_structured_image_fields(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            image_path = root / "diagram.png"
            image_path.write_bytes(b"\x89PNG\r\n\x1a\n")
            text_path = root / "notes.txt"
            text_path.write_text("# notes\n", encoding="utf-8")
            child_dir = root / "assets"
            child_dir.mkdir()

            ctx = SimpleNamespace(
                safe_text=lambda value, _max_len=4000: str(value or ""),
                resolve_allowed_fs_path=lambda raw: Path(str(raw or "")).resolve(),
                relative_path_to_repo_root=lambda _path: "",
                is_text_preview_path=lambda _path, _mime: False,
                read_text_preview=lambda _path: ("", False),
                preview_mode_for_path=lambda _path: "text",
                fs_preview_dir_limit=50,
                json_response=_json_response,
            )
            handler = SimpleNamespace(status=None, payload=None)

            RouteDispatcher(ctx)._handle_fs_read_get(handler, {"path": [str(root)]})

            self.assertEqual(handler.status, 200)
            item = (handler.payload or {}).get("item") or {}
            self.assertEqual(item.get("kind"), "dir")
            entries = {str(row.get("name") or ""): row for row in item.get("entries") or [] if isinstance(row, dict)}

            image_row = entries.get("diagram.png") or {}
            self.assertEqual(image_row.get("kind"), "file")
            self.assertEqual(image_row.get("path"), str(image_path.resolve()))
            self.assertIn("relative_path", image_row)
            self.assertEqual(image_row.get("relative_path"), "")
            self.assertEqual(image_row.get("extension"), ".png")
            self.assertEqual(image_row.get("mime_type"), "image/png")
            self.assertTrue(bool(image_row.get("is_image")))

            text_row = entries.get("notes.txt") or {}
            self.assertEqual(text_row.get("kind"), "file")
            self.assertEqual(text_row.get("extension"), ".txt")
            self.assertEqual(text_row.get("mime_type"), "text/plain")
            self.assertFalse(bool(text_row.get("is_image")))

            dir_row = entries.get("assets") or {}
            self.assertEqual(dir_row.get("kind"), "dir")
            self.assertEqual(dir_row.get("path"), str(child_dir.resolve()))
            self.assertIn("relative_path", dir_row)
            self.assertEqual(dir_row.get("relative_path"), "")
            self.assertEqual(dir_row.get("extension"), "")
            self.assertEqual(dir_row.get("mime_type"), "inode/directory")
            self.assertFalse(bool(dir_row.get("is_image")))


if __name__ == "__main__":
    unittest.main()
