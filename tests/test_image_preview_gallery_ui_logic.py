import shutil
import subprocess
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("node"), "node is required for UI logic regression checks")
class ImagePreviewGalleryUiLogicTests(unittest.TestCase):
    def _run_node(self, script: str) -> None:
        proc = subprocess.run(
            ["node", "-e", script, str(REPO_ROOT)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            self.fail(proc.stderr or proc.stdout or "node image preview gallery regression script failed")

    def test_preview_gallery_normalization_keeps_single_image_compatibility(self) -> None:
        script = textwrap.dedent(
            r"""
            const assert = require("node:assert/strict");
            const fs = require("node:fs");
            const path = require("node:path");

            const repoRoot = process.argv[1];

            function extractFunction(file, name) {
              const text = fs.readFileSync(path.join(repoRoot, file), "utf8");
              const signature = new RegExp(`(?:async\\s+)?function ${name}\\(`);
              const match = signature.exec(text);
              if (!match) throw new Error(`missing function ${name} in ${file}`);
              const start = match.index;
              const headerMatch = text
                .slice(start)
                .match(new RegExp(`(?:async\\s+)?function ${name}\\([^\\n]*\\)\\s*\\{`));
              if (!headerMatch) throw new Error(`missing function header for ${name} in ${file}`);
              let i = start + headerMatch[0].length;
              let depth = 1;
              let inSingle = false;
              let inDouble = false;
              let inTemplate = false;
              let inLineComment = false;
              let inBlockComment = false;
              let escape = false;
              for (; i < text.length; i += 1) {
                const ch = text[i];
                const next = text[i + 1];
                if (inLineComment) {
                  if (ch === "\n") inLineComment = false;
                  continue;
                }
                if (inBlockComment) {
                  if (ch === "*" && next === "/") {
                    inBlockComment = false;
                    i += 1;
                  }
                  continue;
                }
                if (inSingle) {
                  if (!escape && ch === "'") inSingle = false;
                  escape = !escape && ch === "\\";
                  continue;
                }
                if (inDouble) {
                  if (!escape && ch === '"') inDouble = false;
                  escape = !escape && ch === "\\";
                  continue;
                }
                if (inTemplate) {
                  if (!escape && ch === "`") inTemplate = false;
                  escape = !escape && ch === "\\";
                  continue;
                }
                escape = false;
                if (ch === "/" && next === "/") {
                  inLineComment = true;
                  i += 1;
                  continue;
                }
                if (ch === "/" && next === "*") {
                  inBlockComment = true;
                  i += 1;
                  continue;
                }
                if (ch === "'") {
                  inSingle = true;
                  continue;
                }
                if (ch === '"') {
                  inDouble = true;
                  continue;
                }
                if (ch === "`") {
                  inTemplate = true;
                  continue;
                }
                if (ch === "{") {
                  depth += 1;
                  continue;
                }
                if (ch === "}") {
                  depth -= 1;
                  if (depth === 0) return text.slice(start, i + 1);
                }
              }
              throw new Error(`unterminated function ${name} in ${file}`);
            }

            const file = "web/task_parts/79-panel-wire-upload.js";
            eval(extractFunction(file, "normalizeImagePreviewItem"));
            eval(extractFunction(file, "normalizeImagePreviewGallery"));

            const single = normalizeImagePreviewGallery("/a.png", "A");
            assert.equal(single.items.length, 1);
            assert.equal(single.items[0].src, "/a.png");
            assert.equal(single.items[0].caption, "A");
            assert.equal(single.index, 0);

            const gallery = normalizeImagePreviewGallery("/b.png", "fallback", [
              { src: "/a.png", caption: "A" },
              { url: "/b.png", name: "B" },
              { href: "" },
            ], 1);
            assert.equal(gallery.items.length, 2);
            assert.equal(gallery.items[1].src, "/b.png");
            assert.equal(gallery.items[1].caption, "B");
            assert.equal(gallery.index, 1);

            const byFallback = normalizeImagePreviewGallery("/b.png", "fallback", [
              { src: "/a.png", caption: "A" },
              { src: "/b.png", caption: "B" },
            ], -1);
            assert.equal(byFallback.index, 1);

            const insertedFallback = normalizeImagePreviewGallery("/fallback.png", "Fallback", [
              { src: "/a.png", caption: "A" },
            ], 0);
            assert.equal(insertedFallback.items.length, 2);
            assert.equal(insertedFallback.items[0].src, "/fallback.png");
            assert.equal(insertedFallback.index, 0);
            """
        )
        self._run_node(script)

    def test_message_images_render_bottom_pack_and_reuse_preview_gallery(self) -> None:
        timeline_text = (REPO_ROOT / "web" / "task_parts" / "70-conversation-timeline.js").read_text(encoding="utf-8")
        preview_text = (REPO_ROOT / "web" / "task_parts" / "79-panel-wire-upload.js").read_text(encoding="utf-8")
        preview_css_text = (REPO_ROOT / "web" / "task_parts" / "71-image-preview-gallery.css").read_text(encoding="utf-8")
        pack_css_text = (REPO_ROOT / "web" / "task_parts" / "71-message-image-pack.css").read_text(encoding="utf-8")

        self.assertIn("function collectConversationMessageImagePreviewItems(attachments)", timeline_text)
        self.assertIn("function collectConversationMessageBodyImagePreviewItems(text)", timeline_text)
        self.assertIn("function mergeConversationMessageImagePreviewItems(lists, opts = {})", timeline_text)
        self.assertIn("function renderConversationMessageImagePack(items, opts = {})", timeline_text)
        self.assertIn("const imagePreviewItems = collectConversationMessageImagePreviewItems(attachments);", timeline_text)
        self.assertIn("const bodyImagePreviewItems = collectConversationMessageBodyImagePreviewItems(safeTxt || safeFallback || \"\");", timeline_text)
        self.assertIn("const imagePreviewPack = mergeConversationMessageImagePreviewItems([imagePreviewItems, bodyImagePreviewItems]);", timeline_text)
        self.assertIn("if (isImageAttachment(att)) continue;", timeline_text)
        self.assertIn("openImagePreview(item.src, caption, rows, index);", timeline_text)
        self.assertIn('function openImagePreview(src, caption = "", galleryItems = null, activeIndex = 0)', preview_text)
        self.assertIn('if (e.key === "ArrowLeft")', preview_text)
        self.assertIn('if (e.key === "ArrowRight")', preview_text)
        self.assertIn(".img-preview-strip", preview_css_text)
        self.assertIn(".img-preview-thumbbtn.active", preview_css_text)
        self.assertIn(".msg-image-pack", pack_css_text)
        self.assertIn(".msg-image-pack-grid", pack_css_text)
        self.assertIn(".msg-image-pack-more", pack_css_text)

    def test_message_image_pack_collects_only_image_attachments(self) -> None:
        script = textwrap.dedent(
            r"""
            const assert = require("node:assert/strict");
            const fs = require("node:fs");
            const path = require("node:path");

            const repoRoot = process.argv[1];

            function extractFunction(file, name) {
              const text = fs.readFileSync(path.join(repoRoot, file), "utf8");
              const signature = new RegExp(`(?:async\\s+)?function ${name}\\(`);
              const match = signature.exec(text);
              if (!match) throw new Error(`missing function ${name} in ${file}`);
              const start = match.index;
              const headerMatch = text
                .slice(start)
                .match(new RegExp(`(?:async\\s+)?function ${name}\\([^\\n]*\\)\\s*\\{`));
              if (!headerMatch) throw new Error(`missing function header for ${name} in ${file}`);
              let i = start + headerMatch[0].length;
              let depth = 1;
              let inSingle = false;
              let inDouble = false;
              let inTemplate = false;
              let inLineComment = false;
              let inBlockComment = false;
              let escape = false;
              for (; i < text.length; i += 1) {
                const ch = text[i];
                const next = text[i + 1];
                if (inLineComment) {
                  if (ch === "\n") inLineComment = false;
                  continue;
                }
                if (inBlockComment) {
                  if (ch === "*" && next === "/") {
                    inBlockComment = false;
                    i += 1;
                  }
                  continue;
                }
                if (inSingle) {
                  if (!escape && ch === "'") inSingle = false;
                  escape = !escape && ch === "\\";
                  continue;
                }
                if (inDouble) {
                  if (!escape && ch === '"') inDouble = false;
                  escape = !escape && ch === "\\";
                  continue;
                }
                if (inTemplate) {
                  if (!escape && ch === "`") inTemplate = false;
                  escape = !escape && ch === "\\";
                  continue;
                }
                escape = false;
                if (ch === "/" && next === "/") {
                  inLineComment = true;
                  i += 1;
                  continue;
                }
                if (ch === "/" && next === "*") {
                  inBlockComment = true;
                  i += 1;
                  continue;
                }
                if (ch === "'") {
                  inSingle = true;
                  continue;
                }
                if (ch === '"') {
                  inDouble = true;
                  continue;
                }
                if (ch === "`") {
                  inTemplate = true;
                  continue;
                }
                if (ch === "{") {
                  depth += 1;
                  continue;
                }
                if (ch === "}") {
                  depth -= 1;
                  if (depth === 0) return text.slice(start, i + 1);
                }
              }
              throw new Error(`unterminated function ${name} in ${file}`);
            }

            global.isImageAttachment = (att) => String((att && att.mimeType) || "").startsWith("image/");
            global.resolveAttachmentUrl = (att) => String((att && att.url) || "").trim();

            const file = "web/task_parts/70-conversation-timeline.js";
            const timeline = fs.readFileSync(path.join(repoRoot, file), "utf8");
            const start = timeline.indexOf("function conversationMessageImagePreviewLimit()");
            const end = timeline.indexOf("function renderConversationMessageImagePack");
            if (start < 0 || end < 0 || end <= start) throw new Error("missing message image preview section");
            eval(timeline.slice(start, end));

            const rows = collectConversationMessageImagePreviewItems([
              { url: "/a.png", mimeType: "image/png", originalName: "A.png" },
              { url: "/b.pdf", mimeType: "application/pdf", originalName: "B.pdf" },
              { url: "", mimeType: "image/png", originalName: "empty.png" },
              { url: "/c.webp", mimeType: "image/webp", filename: "C.webp" },
            ]);

            assert.equal(rows.length, 2);
            assert.deepEqual(rows[0], { src: "/a.png", caption: "A.png" });
            assert.deepEqual(rows[1], { src: "/c.webp", caption: "C.webp" });
            """
        )
        self._run_node(script)

    def test_message_body_image_paths_join_bottom_pack_with_safety_dedupe_and_limit(self) -> None:
        script = textwrap.dedent(
            r"""
            const assert = require("node:assert/strict");
            const fs = require("node:fs");
            const path = require("node:path");

            const repoRoot = process.argv[1];

            function extractFunction(file, name) {
              const text = fs.readFileSync(path.join(repoRoot, file), "utf8");
              const signature = new RegExp(`(?:async\\s+)?function ${name}\\(`);
              const match = signature.exec(text);
              if (!match) throw new Error(`missing function ${name} in ${file}`);
              const start = match.index;
              const headerMatch = text
                .slice(start)
                .match(new RegExp(`(?:async\\s+)?function ${name}\\([^\\n]*\\)\\s*\\{`));
              if (!headerMatch) throw new Error(`missing function header for ${name} in ${file}`);
              let i = start + headerMatch[0].length;
              let depth = 1;
              let inSingle = false;
              let inDouble = false;
              let inTemplate = false;
              let inLineComment = false;
              let inBlockComment = false;
              let escape = false;
              for (; i < text.length; i += 1) {
                const ch = text[i];
                const next = text[i + 1];
                if (inLineComment) {
                  if (ch === "\n") inLineComment = false;
                  continue;
                }
                if (inBlockComment) {
                  if (ch === "*" && next === "/") {
                    inBlockComment = false;
                    i += 1;
                  }
                  continue;
                }
                if (inSingle) {
                  if (!escape && ch === "'") inSingle = false;
                  escape = !escape && ch === "\\";
                  continue;
                }
                if (inDouble) {
                  if (!escape && ch === '"') inDouble = false;
                  escape = !escape && ch === "\\";
                  continue;
                }
                if (inTemplate) {
                  if (!escape && ch === "`") inTemplate = false;
                  escape = !escape && ch === "\\";
                  continue;
                }
                escape = false;
                if (ch === "/" && next === "/") {
                  inLineComment = true;
                  i += 1;
                  continue;
                }
                if (ch === "/" && next === "*") {
                  inBlockComment = true;
                  i += 1;
                  continue;
                }
                if (ch === "'") {
                  inSingle = true;
                  continue;
                }
                if (ch === '"') {
                  inDouble = true;
                  continue;
                }
                if (ch === "`") {
                  inTemplate = true;
                  continue;
                }
                if (ch === "{") {
                  depth += 1;
                  continue;
                }
                if (ch === "}") {
                  depth -= 1;
                  if (depth === 0) return text.slice(start, i + 1);
                }
              }
              throw new Error(`unterminated function ${name} in ${file}`);
            }

            global.location = { origin: "http://localhost:18770" };
            global.isImageAttachment = (att) => String((att && att.mimeType) || "").startsWith("image/");
            global.resolveAttachmentUrl = (att) => String((att && att.url) || "").trim();

            const channelRoot = "/tmp/qoreon-demo/task-dashboard/任务规划/子级04-前端体验（task-overview 页面交互）";
            global.messageObjectChannelRootPath = () => channelRoot;
            global.resolveMessageObjectPath = (value) => {
              const raw = String(value || "").trim().replace(/^\/+/, "");
              if (raw.startsWith("材料/")) return channelRoot + "/产出物/" + raw;
              if (raw.startsWith("产出物/")) return channelRoot + "/" + raw;
              return String(value || "").trim();
            };

            const file = "web/task_parts/70-conversation-timeline.js";
            const timeline = fs.readFileSync(path.join(repoRoot, file), "utf8");
            const start = timeline.indexOf("function conversationMessageImagePreviewLimit()");
            const end = timeline.indexOf("function renderConversationMessageImagePack");
            if (start < 0 || end < 0 || end <= start) throw new Error("missing message image preview section");
            eval(timeline.slice(start, end));

            const channelImage = channelRoot + "/产出物/材料/d.svg";
            const body = [
              "裸附件 /.runs/run-1/attachments/a.png",
              "重复 [same](/.runs/run-1/attachments/a.png)",
              "Markdown: ![b](产出物/材料/b.webp)",
              "短路径: /材料/c.jpg",
              "当前通道绝对路径: " + channelImage,
              "越界路径: /etc/passwd.png",
              "外部 URL: http://evil.example/x.png",
              "非图片: 产出物/材料/readme.md",
              "纯目录: 产出物/材料",
            ].join("\n");

            const attachmentItems = collectConversationMessageImagePreviewItems([
              { url: "/.runs/run-1/attachments/a.png", mimeType: "image/png", originalName: "a.png" },
            ]);
            const bodyItems = collectConversationMessageBodyImagePreviewItems(body);
            const merged = mergeConversationMessageImagePreviewItems([attachmentItems, bodyItems]);

            assert.equal(attachmentItems.length, 1);
            assert.equal(bodyItems.length, 4);
            assert.equal(merged.totalCount, 4);
            assert.equal(merged.overflowCount, 0);
            assert.equal(merged.items[0].src, "/.runs/run-1/attachments/a.png");
            assert.ok(merged.items.some((item) => item.src === "/api/fs/open?path=" + encodeURIComponent(channelRoot + "/产出物/材料/b.webp")));
            assert.ok(merged.items.some((item) => item.src === "/api/fs/open?path=" + encodeURIComponent(channelRoot + "/产出物/材料/c.jpg")));
            assert.ok(merged.items.some((item) => item.src === "/api/fs/open?path=" + encodeURIComponent(channelImage)));
            assert.equal(merged.items.some((item) => item.src.includes("/etc/passwd.png")), false);
            assert.equal(merged.items.some((item) => item.src.includes("evil.example")), false);
            assert.equal(merged.items.some((item) => item.src.includes("readme.md")), false);

            const many = Array.from({ length: 14 }, (_v, index) => ({
              src: "/.runs/run-many/attachments/" + index + ".png",
              caption: String(index),
            }));
            const capped = mergeConversationMessageImagePreviewItems([many]);
            assert.equal(capped.items.length, 12);
            assert.equal(capped.totalCount, 14);
            assert.equal(capped.overflowCount, 2);
            """
        )
        self._run_node(script)
