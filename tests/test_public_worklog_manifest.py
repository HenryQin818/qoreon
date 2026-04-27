from __future__ import annotations

import json
import unittest
from pathlib import Path


class PublicWorklogManifestTest(unittest.TestCase):
    def test_manifest_uses_public_share_paths_and_existing_local_files(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        manifest_path = repo_root / "docs" / "worklog" / "task_dashboard" / "worklog-index.json"
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        items = payload.get("items")
        self.assertIsInstance(items, list)
        self.assertGreater(len(items), 0)
        for item in items:
            self.assertIsInstance(item, dict)
            url = str(item.get("url") or "")
            cover = str(item.get("cover") or "")
            local_path = str(item.get("local_path") or "")
            self.assertTrue(url.startswith("/share/worklog/"), url)
            self.assertTrue(cover.startswith("/share/worklog/"), cover)
            self.assertTrue(local_path, item)
            self.assertTrue((repo_root / local_path).exists(), local_path)


if __name__ == "__main__":
    unittest.main()
