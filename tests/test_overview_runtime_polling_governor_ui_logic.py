import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class OverviewRuntimePollingGovernorUiLogicTests(unittest.TestCase):
    def test_runtime_bubbles_polling_uses_timeout_visibility_gate(self) -> None:
        source = (REPO_ROOT / "web" / "overview.js").read_text(encoding="utf-8")
        self.assertIn("runtimePollVisibilityBound", source)
        self.assertIn("function overviewRuntimePageHidden()", source)
        self.assertIn("document.addEventListener(\"visibilitychange\"", source)
        self.assertIn("scheduleRuntimeBubblesPoll(pid, runtimeBubblesPollDelayMs())", source)
        self.assertNotIn("GRAPH.runtimePollTimer = setInterval", source)
        self.assertNotIn("clearInterval(GRAPH.runtimePollTimer)", source)


if __name__ == "__main__":
    unittest.main()
