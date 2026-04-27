import re
import shutil
import subprocess
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("node"), "node is required for UI logic regression checks")
class MessageObjectImageUiLogicTests(unittest.TestCase):
    def _run_node(self, script: str) -> None:
        proc = subprocess.run(
            ["node", "-e", script, str(REPO_ROOT)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            self.fail(proc.stderr or proc.stdout or "node ui logic regression script failed")

    def test_generated_assistant_image_attachments_use_strict_truth_fields(self) -> None:
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

            global.firstNonEmptyText = (values) => {
              for (const value of values || []) {
                const text = String(value || "").trim();
                if (text) return text;
              }
              return "";
            };
            global.isImageAttachment = (att) => {
              if (!att || typeof att !== "object") return false;
              if (att.isImage === true) return true;
              const mime = String(att.mimeType || att.mime_type || "").toLowerCase();
              if (mime.startsWith("image/")) return true;
              const name = String(att.originalName || att.filename || "").toLowerCase();
              return /\.(png|jpe?g|gif|webp|bmp|svg)$/.test(name);
            };

            const file = "web/task_parts/60-conversation.js";
            eval(extractFunction(file, "conversationGeneratedAttachmentRole"));
            eval(extractFunction(file, "isConversationGeneratedAssistantMediaAttachment"));
            eval(extractFunction(file, "isConversationGeneratedAssistantImageAttachment"));
            eval(extractFunction(file, "collectConversationGeneratedAssistantImageAttachments"));
            eval(extractFunction(file, "isConversationUserInputAttachment"));
            eval(extractFunction(file, "collectConversationUserInputAttachments"));

            const rows = [
              { attachment_role: "assistant", source: "generated", originalName: "good-1.png" },
              { attachmentRole: "assistant", generatedBy: "codex_imagegen", originalName: "good-2.webp" },
              { source: "generated", generatedBy: "codex_imagegen", originalName: "good-legacy.png" },
              { attachment_role: "assistant", source: "generated", originalName: "notes.txt" },
              { attachment_role: "assistant", source: "upload", originalName: "normal.png" },
              { attachment_role: "user", source: "generated", originalName: "user.png" },
              { attachment_role: "assistant", generatedBy: "other_tool", originalName: "other.png" },
              { attachment_role: "user", source: "upload", originalName: "upload.png" },
              { source: "upload", originalName: "legacy-upload.png" },
            ];

            assert.equal(isConversationGeneratedAssistantImageAttachment(rows[0]), true);
            assert.equal(isConversationGeneratedAssistantImageAttachment(rows[1]), true);
            assert.equal(isConversationGeneratedAssistantImageAttachment(rows[2]), true);
            assert.equal(isConversationGeneratedAssistantImageAttachment(rows[3]), false);
            assert.equal(isConversationGeneratedAssistantImageAttachment(rows[4]), false);
            assert.equal(isConversationGeneratedAssistantImageAttachment(rows[5]), false);
            assert.equal(isConversationGeneratedAssistantImageAttachment(rows[6]), false);

            assert.equal(isConversationUserInputAttachment(rows[0]), false);
            assert.equal(isConversationUserInputAttachment(rows[2]), false);
            assert.equal(isConversationUserInputAttachment(rows[7]), true);
            assert.equal(isConversationUserInputAttachment(rows[8]), true);

            const kept = collectConversationGeneratedAssistantImageAttachments(rows);
            assert.equal(kept.length, 3);
            assert.equal(kept[0].originalName, "good-1.png");
            assert.equal(kept[1].originalName, "good-2.webp");
            assert.equal(kept[2].originalName, "good-legacy.png");

            const userKept = collectConversationUserInputAttachments(rows);
            assert.equal(userKept.length, 2);
            assert.equal(userKept[0].originalName, "upload.png");
            assert.equal(userKept[1].originalName, "legacy-upload.png");
            """
        )
        self._run_node(script)

    def test_directory_image_preview_depends_on_structured_image_fields(self) -> None:
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

            const file = "web/task_entry_parts/80-project-ops.js";
            eval(extractFunction(file, "isMessageObjectViewerImageEntry"));
            eval(extractFunction(file, "messageObjectViewerImageEntries"));

            const item = {
              entries: [
                { kind: "file", name: "cover.png", path: "/tmp/cover.png", is_image: true, mime_type: "image/png" },
                { kind: "file", name: "notes.png", path: "/tmp/notes.png", is_image: false, mime_type: "text/plain" },
                { kind: "file", name: "poster.jpg", path: "/tmp/poster.jpg", mime_type: "image/jpeg" },
                { kind: "dir", name: "assets", path: "/tmp/assets", is_image: true, mime_type: "inode/directory" },
              ],
            };

            assert.equal(isMessageObjectViewerImageEntry(item.entries[0]), true);
            assert.equal(isMessageObjectViewerImageEntry(item.entries[1]), false);
            assert.equal(isMessageObjectViewerImageEntry(item.entries[2]), true);
            assert.equal(isMessageObjectViewerImageEntry(item.entries[3]), false);

            const rows = messageObjectViewerImageEntries(item);
            assert.equal(rows.length, 2);
            assert.deepEqual(rows.map((row) => row.name), ["cover.png", "poster.jpg"]);
            """
        )
        self._run_node(script)

    def test_image_lightbox_stacks_above_message_object_viewer(self) -> None:
        css = (REPO_ROOT / "web" / "task.css").read_text(encoding="utf-8")

        def z_index_for(selector: str) -> int:
            pattern = re.compile(
                re.escape(selector) + r"\s*\{(?P<body>.*?)\}",
                re.DOTALL,
            )
            match = pattern.search(css)
            self.assertIsNotNone(match, f"missing CSS selector: {selector}")
            z_match = re.search(r"z-index:\s*(\d+)", match.group("body"))
            self.assertIsNotNone(z_match, f"missing z-index for selector: {selector}")
            return int(z_match.group(1))

        self.assertGreater(
            z_index_for(".img-preview-mask"),
            z_index_for(".msgobj-viewer-mask"),
        )


if __name__ == "__main__":
    unittest.main()
