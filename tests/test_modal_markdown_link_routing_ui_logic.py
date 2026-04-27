import re
import shutil
import subprocess
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
OPS_JS = REPO_ROOT / "web" / "task_entry_parts" / "80-project-ops.js"
CONVERSATION_JS = REPO_ROOT / "web" / "task_parts" / "60-conversation.js"


class ModalMarkdownLinkRoutingUiLogicTests(unittest.TestCase):
    def test_markdown_links_keep_file_object_marker(self) -> None:
        text = OPS_JS.read_text(encoding="utf-8")

        self.assertIn("const obj = classifyMessageObjectToken(u);", text)
        self.assertIn('data-msg-object-href="', text)
        self.assertIn("bindMessageObjectActivator(anchor, obj);", text)

    @unittest.skipUnless(shutil.which("node"), "node is required for UI logic regression checks")
    def test_message_object_path_token_keeps_spaces_until_image_extension(self) -> None:
        script = textwrap.dedent(
            r"""
            const assert = require("node:assert/strict");
            const fs = require("node:fs");
            const path = require("node:path");

            const repoRoot = process.argv[1];
            const file = "web/task_entry_parts/80-project-ops.js";
            const text = fs.readFileSync(path.join(repoRoot, file), "utf8");
            const start = text.indexOf("const MESSAGE_OBJECT_TOKEN_RE");
            const end = text.indexOf("function ensureMessageObjectViewer()");
            if (start < 0 || end < 0 || end <= start) {
              throw new Error("missing message object parser section");
            }

            global.DATA = { projects: [] };
            global.STATE = { project: "task_dashboard" };
            global.location = { origin: "http://localhost:18770" };
            global.isHttpUrl = (value) => /^https?:\/\//i.test(String(value || ""));

            eval(text.slice(start, end) + `
              const imagePath = "/tmp/qoreon-demo/generated images/sample-public-object.png";
              const segments = splitTextByMessageObjects("路径：" + imagePath + " 后续说明");
              global.__messageObjectSegments = segments;
              global.__messageObjectImagePath = imagePath;
            `);

            const objects = global.__messageObjectSegments.filter((seg) => seg.type === "object");
            assert.equal(objects.length, 1);
            assert.equal(objects[0].value, global.__messageObjectImagePath);
            assert.equal(objects[0].object.path, global.__messageObjectImagePath);
            assert.equal(global.__messageObjectSegments.at(-1).value, " 后续说明");
            """
        )
        proc = subprocess.run(
            ["node", "-e", script, str(REPO_ROOT)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            self.fail(proc.stderr or proc.stdout or "node message object parser regression script failed")

    @unittest.skipUnless(shutil.which("node"), "node is required for UI logic regression checks")
    def test_message_object_path_strips_markdown_line_suffix_for_preview_lookup(self) -> None:
        script = textwrap.dedent(
            r"""
            const assert = require("node:assert/strict");
            const fs = require("node:fs");
            const path = require("node:path");

            const repoRoot = process.argv[1];
            const file = "web/task_entry_parts/80-project-ops.js";
            const text = fs.readFileSync(path.join(repoRoot, file), "utf8");
            const start = text.indexOf("const MESSAGE_OBJECT_TOKEN_RE");
            const end = text.indexOf("function ensureMessageObjectViewer()");
            if (start < 0 || end < 0 || end <= start) {
              throw new Error("missing message object parser section");
            }

            global.DATA = { projects: [] };
            global.STATE = { project: "task_dashboard" };
            global.location = { origin: "http://localhost:18770" };
            global.isHttpUrl = (value) => /^https?:\/\//i.test(String(value || ""));

            eval(text.slice(start, end) + `
              const docPath = "/tmp/qoreon-demo/examples/standard-project/tasks/public-demo/2026-04-23-task-detail-spec-v1.md:1";
              const segments = splitTextByMessageObjects("关键路径：" + docPath);
              global.__messageObjectSegments = segments;
              global.__messageObjectDocPath = docPath;
            `);

            const objects = global.__messageObjectSegments.filter((seg) => seg.type === "object");
            assert.equal(objects.length, 1);
            assert.equal(objects[0].value, global.__messageObjectDocPath);
            assert.equal(objects[0].object.label, global.__messageObjectDocPath);
            assert.equal(objects[0].object.path.endsWith(".md"), true);
            assert.equal(objects[0].object.path.includes(".md:1"), false);
            """
        )
        proc = subprocess.run(
            ["node", "-e", script, str(REPO_ROOT)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            self.fail(proc.stderr or proc.stdout or "node message object line suffix regression script failed")

    def test_markdown_rendering_forces_message_object_binding(self) -> None:
        text = OPS_JS.read_text(encoding="utf-8")

        set_markdown = self._slice_between(
            text,
            "function setMarkdown(elNode, text, fallback = \"\")",
            "const MESSAGE_OBJECT_TOKEN_RE",
        )
        self.assertIn("elNode.innerHTML = markdownToHtml(src);", set_markdown)
        self.assertIn("enhanceMessageInteractiveObjects(elNode, { force: true });", set_markdown)

        self.assertIn("function enhanceMessageInteractiveObjects(root, opts = {})", text)
        self.assertIn("const force = !!(opts && opts.force);", text)
        self.assertIn("(root.__messageObjectsEnhanced && !force)", text)

    @unittest.skipUnless(shutil.which("node"), "node is required for UI logic regression checks")
    def test_markdown_table_renders_as_safe_table(self) -> None:
        script = textwrap.dedent(
            r"""
            const assert = require("node:assert/strict");
            const fs = require("node:fs");
            const path = require("node:path");

            const repoRoot = process.argv[1];
            const file = "web/task_entry_parts/80-project-ops.js";
            const text = fs.readFileSync(path.join(repoRoot, file), "utf8");
            const start = text.indexOf("function escapeHtml(s)");
            const end = text.indexOf("const MESSAGE_OBJECT_TOKEN_RE");
            if (start < 0 || end < 0 || end <= start) {
              throw new Error("missing markdown renderer section");
            }

            eval(text.slice(start, end) + `
              global.__html = markdownToHtml("| 任务 | 状态 | 下一步 |\\n| --- | :---: | ---: |\\n| 表格兼容 | 进行中 | 验收 |");
            `);

            assert.match(global.__html, /<div class="md-table-wrap">/);
            assert.match(global.__html, /<table class="md-table">/);
            assert.match(global.__html, /<th class="md-table-align-left">任务<\/th>/);
            assert.match(global.__html, /<th class="md-table-align-center">状态<\/th>/);
            assert.match(global.__html, /<td class="md-table-align-right">验收<\/td>/);
            assert.equal(global.__html.includes("| --- |"), false);
            """
        )
        proc = subprocess.run(
            ["node", "-e", script, str(REPO_ROOT)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            self.fail(proc.stderr or proc.stdout or "node markdown table regression script failed")

    @unittest.skipUnless(shutil.which("node"), "node is required for UI logic regression checks")
    def test_markdown_task_list_code_lang_and_html_escape(self) -> None:
        script = textwrap.dedent(
            r"""
            const assert = require("node:assert/strict");
            const fs = require("node:fs");
            const path = require("node:path");

            const repoRoot = process.argv[1];
            const file = "web/task_entry_parts/80-project-ops.js";
            const text = fs.readFileSync(path.join(repoRoot, file), "utf8");
            const start = text.indexOf("function escapeHtml(s)");
            const end = text.indexOf("const MESSAGE_OBJECT_TOKEN_RE");
            if (start < 0 || end < 0 || end <= start) {
              throw new Error("missing markdown renderer section");
            }

            eval(text.slice(start, end) + `
              const md = "- [x] 已完成\\n- [ ] 待验收\\n\\n\\\`\\\`\\\`js\\nconsole.log('<safe>')\\n\\\`\\\`\\\`\\n\\n<script>alert(1)</script>";
              global.__html = markdownToHtml(md);
            `);

            assert.match(global.__html, /<li class="md-task-item"><input type="checkbox" disabled checked>/);
            assert.match(global.__html, /<li class="md-task-item"><input type="checkbox" disabled>/);
            assert.match(global.__html, /<pre class="md-code" data-lang="js"><code class="language-js">/);
            assert.equal(global.__html.includes("<script>"), false);
            assert.match(global.__html, /&lt;script&gt;alert\(1\)&lt;\/script&gt;/);
            """
        )
        proc = subprocess.run(
            ["node", "-e", script, str(REPO_ROOT)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            self.fail(proc.stderr or proc.stdout or "node markdown task/code regression script failed")

    @unittest.skipUnless(shutil.which("node"), "node is required for UI logic regression checks")
    def test_markdown_table_keeps_business_file_link_marker(self) -> None:
        script = textwrap.dedent(
            r"""
            const assert = require("node:assert/strict");
            const fs = require("node:fs");
            const path = require("node:path");

            const repoRoot = process.argv[1];
            const file = "web/task_entry_parts/80-project-ops.js";
            const text = fs.readFileSync(path.join(repoRoot, file), "utf8");
            const start = text.indexOf("function escapeHtml(s)");
            const end = text.indexOf("function ensureMessageObjectViewer()");
            if (start < 0 || end < 0 || end <= start) {
              throw new Error("missing markdown/message object parser section");
            }

            global.DATA = { projects: [] };
            global.STATE = { project: "task_dashboard" };
            global.location = { origin: "http://localhost:18770" };
            global.isHttpUrl = (value) => /^https?:\/\//i.test(String(value || ""));

            eval(text.slice(start, end) + `
              const docPath = "/tmp/qoreon-demo/examples/standard-project/tasks/public-demo/20260427-agent-message-markdown-regression.md";
              const md = "| 材料 | 状态 |\\n| --- | --- |\\n| [任务文件](<" + docPath + ">) | 可点击 |";
              global.__html = markdownToHtml(md);
              global.__docPath = docPath;
            `);

            assert.match(global.__html, /<table class="md-table">/);
            assert.match(global.__html, /data-msg-object-href="/);
            assert.equal(global.__html.includes(global.__docPath), true);
            assert.equal(global.__html.includes("&lt;"), false);
            assert.equal(global.__html.includes("&gt;"), false);
            """
        )
        proc = subprocess.run(
            ["node", "-e", script, str(REPO_ROOT)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            self.fail(proc.stderr or proc.stdout or "node markdown table object link regression script failed")

    @unittest.skipUnless(shutil.which("node"), "node is required for UI logic regression checks")
    def test_markdown_angle_file_link_keeps_clickable_object_href(self) -> None:
        script = textwrap.dedent(
            r"""
            const assert = require("node:assert/strict");
            const fs = require("node:fs");
            const path = require("node:path");

            const repoRoot = process.argv[1];
            const file = "web/task_entry_parts/80-project-ops.js";
            const text = fs.readFileSync(path.join(repoRoot, file), "utf8");
            const start = text.indexOf("function escapeHtml(s)");
            const end = text.indexOf("function ensureMessageObjectViewer()");
            if (start < 0 || end < 0 || end <= start) {
              throw new Error("missing markdown/message object parser section");
            }

            global.DATA = { projects: [] };
            global.STATE = { project: "task_dashboard" };
            global.location = { origin: "http://localhost:18770" };
            global.isHttpUrl = (value) => /^https?:\/\//i.test(String(value || ""));

            eval(text.slice(start, end) + `
              const docPath = "/tmp/qoreon-demo/examples/standard-project/tasks/public-demo/2026-04-24-task-detail-target-ui-v2.html:1";
              global.__html = markdownToHtml("[统一任务详情目标态 UI v2](<" + docPath + ">)");
              global.__docPath = docPath;
            `);

            assert.match(global.__html, /<a /);
            assert.match(global.__html, /data-msg-object-href="/);
            assert.equal(global.__html.includes("&lt;"), false);
            assert.equal(global.__html.includes("&gt;"), false);
            assert.equal(global.__html.includes(global.__docPath), true);
            """
        )
        proc = subprocess.run(
            ["node", "-e", script, str(REPO_ROOT)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            self.fail(proc.stderr or proc.stdout or "node markdown angle link regression script failed")

    def test_task_detail_modal_markdown_links_open_viewer(self) -> None:
        text = CONVERSATION_JS.read_text(encoding="utf-8")
        body = self._slice_between(
            text,
            "function buildConversationTaskDetailReadingBody(entry)",
            "function buildConversationTaskDetailReadingSection(detail)",
        )

        self.assertIn('mode === "markdown"', body)
        self.assertIn("body.innerHTML = markdownToHtml(String(item.content || \"\"));", body)
        self.assertIn("enhanceMessageInteractiveObjects(body, { force: true });", body)

    def test_file_viewer_markdown_links_open_nested_viewer(self) -> None:
        text = OPS_JS.read_text(encoding="utf-8")
        body = self._slice_between(
            text,
            "function renderMessageObjectViewerBody()",
            "function closeMessageObjectViewer()",
        )
        markdown_branch = self._slice_between(
            body,
            'if (mode === "markdown")',
            'if (mode === "html")',
        )

        self.assertIn("box.innerHTML = markdownToHtml(String(item.content || \"\"));", markdown_branch)
        self.assertIn("enhanceMessageInteractiveObjects(box, { force: true });", markdown_branch)

    def test_file_viewer_renders_image_stage_and_directory_image_grid(self) -> None:
        text = OPS_JS.read_text(encoding="utf-8")

        self.assertIn("function renderMessageObjectViewerImageStage(entry, opts = {})", text)
        self.assertIn("openImagePreview(src, caption);", text)
        self.assertIn("function renderMessageObjectViewerImageGrid(entries)", text)
        self.assertIn("const imageGrid = renderMessageObjectViewerImageGrid(messageObjectViewerImageEntries(item));", text)

        body = self._slice_between(
            text,
            "function renderMessageObjectViewerBody()",
            "function renderMessageObjectViewer()",
        )
        self.assertIn("if (item.is_image) {", body)
        self.assertIn("const imageStage = renderMessageObjectViewerImageStage(item, { target: MESSAGE_OBJECT_VIEWER.target, item });", body)
        self.assertIn("if (imageGrid) body.appendChild(imageGrid);", body)

    def _slice_between(self, text: str, start: str, end: str) -> str:
        pattern = re.compile(re.escape(start) + r"(?P<body>.*?)" + re.escape(end), re.DOTALL)
        match = pattern.search(text)
        self.assertIsNotNone(match, f"missing source section: {start}")
        return match.group("body")


if __name__ == "__main__":
    unittest.main()
