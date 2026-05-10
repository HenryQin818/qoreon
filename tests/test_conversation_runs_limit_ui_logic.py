import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class ConversationRunsLimitUiLogicTests(unittest.TestCase):
    def test_conversation_timeline_initial_runs_limit_is_8_only(self) -> None:
        state_text = (REPO_ROOT / "web" / "task_parts" / "00-state.js").read_text(encoding="utf-8")
        conversation_text = (REPO_ROOT / "web" / "task_parts" / "60-conversation.js").read_text(encoding="utf-8")

        self.assertIn("timelineInitial: 8", state_text)
        self.assertIn("timelineIncremental: 20", state_text)
        self.assertIn("timelineBefore: 24", state_text)
        self.assertIn("? CONV_PAGE.timelineIncremental", conversation_text)
        self.assertIn(": CONV_PAGE.timelineInitial", conversation_text)
        self.assertIn("afterCreatedAt: cursor", conversation_text)
        self.assertIn("const beforeLimit = CONV_PAGE.timelineBefore;", conversation_text)


if __name__ == "__main__":
    unittest.main()
