import unittest
from pathlib import Path


class PublicSafeStringTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[1]

    def _read(self, rel_path: str) -> str:
        return (self.repo_root / rel_path).read_text(encoding="utf-8")

    def test_public_config_strips_internal_workspace_details(self) -> None:
        text = self._read("config.toml")
        for forbidden in [
            "/" + "Users/",
            "127.0.0.1:17373",
            "18765",
            "18768",
            "18769",
            "Service " + "Hub",
            "launch" + "d",
        ]:
            self.assertNotIn(forbidden, text)

    def test_server_no_longer_hardcodes_internal_export_paths(self) -> None:
        text = self._read("server.py")
        self.assertNotIn("项目管理" + "-小秘书/项目看板/task-dashboard", text)
        self.assertNotIn("/.codex/" + "skills/", text)

    def test_public_task_page_uses_public_default_origin(self) -> None:
        text = self._read("web/task.js")
        self.assertNotIn("http://127.0.0.1:" + "18765", text)

    def test_public_task_template_hides_runtime_directory_names(self) -> None:
        text = self._read("web/task.html.tpl")
        self.assertNotIn(".runtime/" + ".runs", text)


if __name__ == "__main__":
    unittest.main()
