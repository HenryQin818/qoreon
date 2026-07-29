import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class BrowserModeFrontendUiLogicTests(unittest.TestCase):
    def test_composer_does_not_require_per_message_browser_selection(self) -> None:
        template = (REPO_ROOT / "web" / "task.html.tpl").read_text(encoding="utf-8")
        controls = (REPO_ROOT / "web" / "task_parts" / "75-00-conversation-cli-controls.js").read_text(encoding="utf-8")
        composer = (REPO_ROOT / "web" / "task_parts" / "75-conversation-composer.js").read_text(encoding="utf-8")
        self.assertNotIn('id="convCodexBrowserSelect"', template)
        self.assertNotIn("renderConversationComposerBrowserMode", controls)
        self.assertNotIn("conversationBrowserSelection", composer)
        self.assertNotIn("browser_mode", composer)


if __name__ == "__main__":
    unittest.main()
