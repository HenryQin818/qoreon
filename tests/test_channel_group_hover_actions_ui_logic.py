# -*- coding: utf-8 -*-

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CSS_PATH = REPO_ROOT / "web" / "task_parts" / "76-channel-group-hover-actions.css"


class ChannelGroupHoverActionsUiLogicTests(unittest.TestCase):
    def test_channel_actions_are_overlay_not_layout_width(self) -> None:
        css = CSS_PATH.read_text(encoding="utf-8")
        self.assertIn(".conv-channel-group-actions", css)
        self.assertIn("position: absolute", css)
        self.assertIn("right: calc(100% + 8px)", css)
        self.assertIn("transform: translate(6px, -50%)", css)
        self.assertIn("transform: translate(0, -50%)", css)

    def test_channel_count_remains_fixed_right_anchor(self) -> None:
        css = CSS_PATH.read_text(encoding="utf-8")
        self.assertIn(".conv-channel-group-side", css)
        self.assertIn("flex: 0 0 auto", css)
        self.assertIn("min-width: max-content", css)
        self.assertIn(".conv-channel-group-count", css)
        self.assertIn("z-index: 7", css)

    def test_hover_focus_and_menu_open_reveal_overlay(self) -> None:
        css = CSS_PATH.read_text(encoding="utf-8")
        self.assertIn(".conv-channel-group-head:hover .conv-channel-group-actions", css)
        self.assertIn(".conv-channel-group-head:focus-within .conv-channel-group-actions", css)
        self.assertIn(".conv-channel-group.menu-open .conv-channel-group-actions", css)
        self.assertIn("pointer-events: auto", css)

    def test_touch_viewports_keep_actions_reachable_without_layout_space(self) -> None:
        css = CSS_PATH.read_text(encoding="utf-8")
        self.assertIn("@media (hover: none), (pointer: coarse)", css)
        self.assertIn("opacity: 1", css)
        self.assertIn("pointer-events: auto", css)


if __name__ == "__main__":
    unittest.main()
