import re
import shutil
import subprocess
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
EASTER_EGGS_JS = REPO_ROOT / "web" / "task_parts" / "72-conversation-easter-eggs.js"
EASTER_EGGS_CSS = REPO_ROOT / "web" / "task_parts" / "72-conversation-easter-eggs.css"
TASK_CSS = REPO_ROOT / "web" / "task.css"


@unittest.skipUnless(shutil.which("node"), "node is required for UI logic regression checks")
class ConversationEasterEggUiLogicTests(unittest.TestCase):
    def _run_node(self, script: str) -> None:
        proc = subprocess.run(
            ["node", "-e", script, str(REPO_ROOT)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            self.fail(proc.stderr or proc.stdout or "node ui logic regression script failed")

    def test_start_keywords_match_short_command_messages(self) -> None:
        script = textwrap.dedent(
            r"""
            const assert = require("node:assert/strict");
            const fs = require("node:fs");
            const path = require("node:path");

            const repoRoot = process.argv[1];
            eval(fs.readFileSync(path.join(repoRoot, "web/task_parts/72-conversation-easter-eggs.js"), "utf8"));

            assert.equal(globalThis.matchConversationEasterEgg("开工").id, "start");
            assert.equal(globalThis.matchConversationEasterEgg("开工").iconSet, "tools");
            assert.equal(globalThis.matchConversationEasterEgg("好的，请开始").id, "start");
            assert.equal(globalThis.matchConversationEasterEgg("启动这轮任务").id, "start");
            assert.equal(globalThis.matchConversationEasterEgg("执行").id, "start");
            assert.equal(globalThis.matchConversationEasterEgg("开工大吉").title, "开工大吉");
            """
        )
        self._run_node(script)

    def test_high_frequency_start_keywords_do_not_match_long_body_text(self) -> None:
        script = textwrap.dedent(
            r"""
            const assert = require("node:assert/strict");
            const fs = require("node:fs");
            const path = require("node:path");

            const repoRoot = process.argv[1];
            eval(fs.readFileSync(path.join(repoRoot, "web/task_parts/72-conversation-easter-eggs.js"), "utf8"));

            const longBody = "当前任务执行阶段已经进入验收前复核，需要继续确认消息体系中的文件预览、图片预览、回执卡片、附件展示与发送链路是否全部正常。";
            assert.equal(globalThis.matchConversationEasterEgg(longBody), null);
            """
        )
        self._run_node(script)

    def test_praise_keywords_keep_distinct_copy(self) -> None:
        script = textwrap.dedent(
            r"""
            const assert = require("node:assert/strict");
            const fs = require("node:fs");
            const path = require("node:path");

            const repoRoot = process.argv[1];
            eval(fs.readFileSync(path.join(repoRoot, "web/task_parts/72-conversation-easter-eggs.js"), "utf8"));

            assert.equal(globalThis.matchConversationEasterEgg("干得漂亮").title, "干得漂亮");
            assert.equal(globalThis.matchConversationEasterEgg("干得漂亮").iconSet, "celebration");
            assert.equal(globalThis.matchConversationEasterEgg("做得好").title, "做得好");
            assert.equal(globalThis.matchConversationEasterEgg("做得不错").title, "做得不错");
            assert.equal(globalThis.matchConversationEasterEgg("辛苦了").title, "辛苦了");
            assert.equal(globalThis.matchConversationEasterEgg("太棒了").title, "太棒了");
            """
        )
        self._run_node(script)

    def test_easter_egg_layer_stays_below_image_lightbox(self) -> None:
        easter_css = EASTER_EGGS_CSS.read_text(encoding="utf-8")
        task_css = TASK_CSS.read_text(encoding="utf-8")
        easter_match = re.search(r"\.conv-easteregg-layer\s*\{[^}]*z-index:\s*(\d+)", easter_css, re.S)
        image_match = re.search(r"\.img-preview-mask\s*\{[^}]*z-index:\s*(\d+)", task_css, re.S)

        self.assertIsNotNone(easter_match)
        self.assertIsNotNone(image_match)
        self.assertLess(int(easter_match.group(1)), int(image_match.group(1)))

    def test_easter_egg_uses_icon_field_without_center_text_card(self) -> None:
        js_text = EASTER_EGGS_JS.read_text(encoding="utf-8")
        css_text = EASTER_EGGS_CSS.read_text(encoding="utf-8")

        self.assertIn("conv-easteregg-icon-field", js_text)
        self.assertIn("iconset-tools", css_text)
        self.assertIn("iconset-celebration", css_text)
        self.assertNotIn("conv-easteregg-card", js_text)
        self.assertNotIn(".conv-easteregg-card", css_text)
