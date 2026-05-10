import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
OPS_JS = REPO_ROOT / "web" / "task_entry_parts" / "80-project-ops.js"
CONVERSATION_JS = REPO_ROOT / "web" / "task_parts" / "60-conversation.js"
TIMELINE_JS = REPO_ROOT / "web" / "task_parts" / "70-conversation-timeline.js"
TIMELINE_CSS = REPO_ROOT / "web" / "task_parts" / "70-conversation-timeline.css"
TASK_CSS = REPO_ROOT / "web" / "task.css"


def _slice_between(text: str, start: str, end: str) -> str:
    start_idx = text.index(start)
    end_idx = text.index(end, start_idx)
    return text[start_idx:end_idx]


class ConversationDebugLogUiLogicTests(unittest.TestCase):
    def test_debug_drawer_keeps_cached_log_visible_while_refreshing(self) -> None:
        text = TIMELINE_JS.read_text(encoding="utf-8")
        debug_branch = _slice_between(
            text,
            'if (activeDetailTab === "debug") {',
            '} else {\n          const processPanel = el("div", { class: "process-panel show embedded" });',
        )

        self.assertIn("if (d && d.full)", debug_branch)
        self.assertIn("renderDebugPanel(d.full", debug_branch)
        self.assertIn("syncing: !!d.loading", debug_branch)
        self.assertLess(debug_branch.index("if (d && d.full)"), debug_branch.index("加载调试日志中"))

    def test_debug_panel_paginates_loaded_log_tail(self) -> None:
        text = OPS_JS.read_text(encoding="utf-8")
        panel = _slice_between(
            text,
            "function renderDebugPanel(full, opts = {})",
            "function firstNonEmptyText(values)",
        )

        self.assertIn("const defaultVisibleLines = 300;", panel)
        self.assertIn("const pageLines = 300;", panel)
        self.assertIn("PCONV.debugLogVisibleLines[runId]", panel)
        self.assertIn("mdebug-morebar", panel)
        self.assertIn("加载更多日志", panel)
        self.assertIn("当前内容来自运行时 logTail 片段", panel)
        self.assertIn("PCONV.debugLogScrollTop[runId]", panel)
        self.assertIn("pre.scrollTop = savedTop", panel)
        self.assertNotIn("mdebug-log-wrap", panel)

    def test_debug_log_user_interaction_blocks_outer_stick_to_bottom(self) -> None:
        text = CONVERSATION_JS.read_text(encoding="utf-8")

        self.assertIn("PCONV.debugLogScrollTop[runId] = Number.isFinite(top) && top >= 0 ? top : 0;", text)
        self.assertIn("const debugLogInteracting = Number(PCONV.debugLogUserInteractingUntil || 0) > Date.now();", text)
        self.assertIn("if ((forceScroll || wasNearBottom) && !debugLogInteracting)", text)

    def test_debug_log_uses_high_stable_scroll_container(self) -> None:
        css = TIMELINE_CSS.read_text(encoding="utf-8")
        block = _slice_between(css, ".mdebug-log {", "    .mdebug-morebar")

        self.assertIn("height: clamp(520px, 64vh, 760px);", block)
        self.assertIn("min-height: 420px;", block)
        self.assertIn("overflow: auto;", block)
        self.assertIn("overscroll-behavior: contain;", block)
        self.assertNotIn("max-height: 220px;", block)

    def test_debug_panel_root_does_not_clip_log_container(self) -> None:
        for css_path in (TIMELINE_CSS, TASK_CSS):
            css = css_path.read_text(encoding="utf-8")
            end_marker = "    .mdebug-head" if "    .mdebug-head" in css else "    .conv-historybar"
            block = _slice_between(css, ".mdebug {", end_marker)

            self.assertIn("max-height: none;", block)
            self.assertIn("overflow: visible;", block)
            self.assertIn("white-space: normal;", block)
            self.assertNotIn("max-height: 260px;", block)
            self.assertNotIn("overflow: auto;", block)


if __name__ == "__main__":
    unittest.main()
