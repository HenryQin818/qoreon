# -*- coding: utf-8 -*-

import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
COMPOSER_JS = REPO_ROOT / "web" / "task_parts" / "75-conversation-composer.js"
CONVERSATION_CSS = REPO_ROOT / "web" / "task_parts" / "60-conversation.css"


class GlobalMentionSuggestUiLogicTests(unittest.TestCase):
    def test_global_mention_directory_is_cached_and_empty_query_is_bounded(self) -> None:
        text = COMPOSER_JS.read_text(encoding="utf-8")
        self.assertIn("CONV_MENTION_SUGGEST_RENDER_LIMIT = 48", text)
        self.assertIn("CONV_MENTION_GLOBAL_EMPTY_QUERY_LIMIT = 24", text)
        self.assertIn("function conversationGlobalMentionDirectorySignature", text)
        self.assertIn("PCONV.globalMentionDirectoryCache", text)
        self.assertRegex(
            text,
            r"if\s*\(\s*limit\s*>\s*0\s*&&\s*!forceFull\s*\)",
        )
        self.assertIn("buildConversationGlobalMentionDirectory(currentPid, { limit, query })", text)
        self.assertIn("limit: query ? CONV_MENTION_SUGGEST_RENDER_LIMIT : CONV_MENTION_GLOBAL_EMPTY_QUERY_LIMIT", text)

    def test_global_mention_hydration_refresh_is_debounced(self) -> None:
        text = COMPOSER_JS.read_text(encoding="utf-8")
        self.assertIn("CONV_MENTION_GLOBAL_REFRESH_DEBOUNCE_MS = 90", text)
        self.assertIn("function scheduleConvMentionSuggestRefresh", text)
        hydrate = re.search(
            r"function hydrateConversationGlobalMentionDirectory\(projectId\) \{(?P<body>.*?)\n    \}",
            text,
            re.S,
        )
        self.assertIsNotNone(hydrate)
        body = hydrate.group("body")
        self.assertIn("scheduleConvMentionSuggestRefresh();", body)
        self.assertNotIn("updateConvMentionSuggestByInput();", body)

    def test_draft_mention_sync_does_not_build_global_directory_for_plain_mentions(self) -> None:
        text = COMPOSER_JS.read_text(encoding="utf-8")
        self.assertIn('labels.some((label) => String(label || "").indexOf("/") >= 0)', text)
        self.assertIn("conversationGlobalMentionDirectory(projectId, { full: true }).forEach(register)", text)

    def test_global_mention_empty_state_has_visible_feedback(self) -> None:
        text = COMPOSER_JS.read_text(encoding="utf-8")
        css = CONVERSATION_CSS.read_text(encoding="utf-8")
        self.assertIn('emptyText: loading ? "正在加载全局 Agent..." : "未找到匹配 Agent"', text)
        self.assertIn('class: "convmention-empty"', text)
        self.assertIn(".convmention-empty", css)


if __name__ == "__main__":
    unittest.main()
