import shutil
import subprocess
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def extract_function_source(text: str, name: str) -> str:
    signature = f"function {name}("
    start = text.find(signature)
    if start < 0:
        raise AssertionError(f"missing function {name}")
    header_end = text.find("{", start)
    if header_end < 0:
        raise AssertionError(f"missing function body {name}")
    depth = 1
    i = header_end + 1
    in_single = False
    in_double = False
    in_template = False
    in_line_comment = False
    in_block_comment = False
    escape = False
    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""
        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
            i += 1
            continue
        if in_block_comment:
            if ch == "*" and nxt == "/":
                in_block_comment = False
                i += 2
                continue
            i += 1
            continue
        if in_single:
            if not escape and ch == "'":
                in_single = False
            escape = (not escape and ch == "\\")
            i += 1
            continue
        if in_double:
            if not escape and ch == '"':
                in_double = False
            escape = (not escape and ch == "\\")
            i += 1
            continue
        if in_template:
            if not escape and ch == "`":
                in_template = False
            escape = (not escape and ch == "\\")
            i += 1
            continue
        escape = False
        if ch == "/" and nxt == "/":
            in_line_comment = True
            i += 2
            continue
        if ch == "/" and nxt == "*":
            in_block_comment = True
            i += 2
            continue
        if ch == "'":
            in_single = True
            i += 1
            continue
        if ch == '"':
            in_double = True
            i += 1
            continue
        if ch == "`":
            in_template = True
            i += 1
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
        i += 1
    raise AssertionError(f"unterminated function {name}")


@unittest.skipUnless(shutil.which("node"), "node is required for UI logic regression checks")
class ConversationMemoDrawerUpgradeUiLogicTests(unittest.TestCase):
    def test_memo_image_preview_and_drag_order_helpers(self) -> None:
        source = (REPO_ROOT / "web" / "task_parts" / "75-conversation-composer.js").read_text(encoding="utf-8")
        functions = [
            "conversationMemoAttachmentUrl",
            "isConversationMemoImageAttachment",
            "conversationMemoImagePreviewItems",
            "moveConversationMemoItem",
        ]
        script = textwrap.dedent(
            """
            const assert = require("node:assert/strict");
            global.resolveAttachmentUrl = (att) => String((att && (att.url || att.dataUrl)) || "");
            %s

            const images = conversationMemoImagePreviewItems([
              { filename: "a.png", originalName: "截图A.png", url: "/.runs/attachments/a.png" },
              { filename: "note.md", originalName: "note.md", url: "/.runs/attachments/note.md" },
              { filename: "b", originalName: "b", mimeType: "image/webp", dataUrl: "data:image/webp;base64,abc" },
            ]);
            assert.equal(images.length, 2);
            assert.equal(images[0].src, "/.runs/attachments/a.png");
            assert.equal(images[0].caption, "截图A.png");
            assert.equal(images[1].caption, "b");

            const rows = [{ id: "a" }, { id: "b" }, { id: "c" }];
            assert.deepEqual(moveConversationMemoItem(rows, "a", "c", "after").map((it) => it.id), ["b", "c", "a"]);
            assert.deepEqual(moveConversationMemoItem(rows, "c", "a", "before").map((it) => it.id), ["c", "a", "b"]);
            """
            % "\n".join(extract_function_source(source, name) for name in functions)
        )
        proc = subprocess.run(["node", "-e", script], cwd=REPO_ROOT, capture_output=True, text=True)
        if proc.returncode != 0:
            self.fail(proc.stderr or proc.stdout or "node memo drawer upgrade regression script failed")

    def test_memo_drawer_source_keeps_upgrade_contract(self) -> None:
        source = (REPO_ROOT / "web" / "task_parts" / "75-conversation-composer.js").read_text(encoding="utf-8")
        css = (REPO_ROOT / "web" / "task.css").read_text(encoding="utf-8")
        apply_fn = extract_function_source(source, "applyConversationMemosToComposer")

        self.assertIn('fetch("/api/conversation-memos/reorder"', source)
        self.assertIn("renderConversationMemoAttachments(item)", source)
        self.assertIn("openImagePreview(image.src, caption, images, index);", source)
        self.assertIn("if (memoText) row.appendChild", source)
        self.assertIn('class: "memo-drag-handle"', source)
        self.assertIn('class: "memo-text-action"', source)
        self.assertNotIn('text: item.text || "(空文本)"', source)
        self.assertNotIn("rows.sort(", apply_fn)

        self.assertIn(".memo-image-grid", css)
        self.assertIn(".memo-image-thumb", css)
        self.assertIn(".memo-text-action", css)
        self.assertIn(".memo-drag-handle", css)
        self.assertNotIn("max-height: 140px;", css)


if __name__ == "__main__":
    unittest.main()
