import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class RemovedConversationNagUiLogicTests(unittest.TestCase):
    def test_frontend_runtime_has_no_removed_training_nag_markers(self) -> None:
        files = [
            "web/task.html.tpl",
            "web/task_parts/00-state.js",
            "web/task_parts/60-conversation.js",
            "web/task_parts/60-conversation.css",
            "web/task_parts/75-conversation-composer.js",
            "web/task_parts/79-panel-wire-upload.js",
        ]
        tokens = [
            "conv" + "training",
            "conv-" + "training",
            "CONV_" + "TRAINING",
            "Agent" + "培训",
            "新人" + "培训",
            "buildConversation" + "Training",
            "Conversation" + "Training",
            "conversation" + "Training",
            "conv" + "Training",
            "Training" + "Sent",
            "Training" + "Dismissed",
            "Training" + "ManualOpen",
        ]
        pattern = re.compile("|".join(re.escape(token) for token in tokens))
        hits: list[str] = []
        for rel in files:
            text = (REPO_ROOT / rel).read_text(encoding="utf-8")
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                hits.append(f"{rel}:{line}:{match.group(0)}")
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
