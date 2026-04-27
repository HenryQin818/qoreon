import shutil
import subprocess
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("node"), "node is required for UI logic regression checks")
class ConversationDetailHeaderUiLogicTests(unittest.TestCase):
    def test_session_meta_renders_copy_button_and_copies_session_id(self) -> None:
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

            function createNode(tag, attrs = {}) {
              const listeners = Object.create(null);
              return {
                tag,
                attrs: { ...attrs },
                children: [],
                innerHTML: attrs.html || "",
                textContent: attrs.text || "",
                appendChild(child) {
                  this.children.push(child);
                  return child;
                },
                addEventListener(type, handler) {
                  listeners[type] = handler;
                },
                dispatch(type) {
                  const handler = listeners[type];
                  if (!handler) return;
                  handler({
                    preventDefault() {},
                    stopPropagation() {},
                  });
                },
              };
            }

            global.el = (tag, attrs = {}, ...children) => {
              const node = createNode(tag, attrs);
              for (const child of children) {
                if (child != null) node.appendChild(child);
              }
              return node;
            };

            const hints = [];
            global.setHintText = (...args) => hints.push(args);
            const helperCalls = [];
            global.copyText = (text) => {
              helperCalls.push(String(text));
              return true;
            };

            const file = "web/task_parts/60-conversation.js";
            eval(extractFunction(file, "copyConversationSessionId"));
            eval(extractFunction(file, "buildConversationDetailSessionMeta"));

            (async () => {
              const meta = buildConversationDetailSessionMeta("019d-abc");
              assert.ok(meta);
              assert.equal(meta.attrs.class, "detail-title-meta");
              assert.equal(meta.children.length, 2);
              assert.equal(meta.children[0].attrs.class, "detail-inline-id");
              assert.equal(meta.children[0].textContent, "019d-abc");
              assert.equal(meta.children[1].attrs.class, "detail-inline-copy-btn");

              meta.children[1].dispatch("click");
              await Promise.resolve();

              assert.deepEqual(helperCalls, ["019d-abc"]);
              assert.deepEqual(hints[hints.length - 1], ["conv", "已复制 session ID"]);
            })().catch((err) => {
              console.error(err && err.stack ? err.stack : String(err));
              process.exit(1);
            });
          """
        )
        proc = subprocess.run(
            ["node", "-e", script, str(REPO_ROOT)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            self.fail(proc.stderr or proc.stdout or "node conversation detail header regression script failed")

    def test_copy_text_falls_back_when_clipboard_api_is_not_secure(self) -> None:
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

            const appended = [];
            const removed = [];
            const textarea = {
              value: "",
              style: {},
              focusCalled: false,
              selectCalled: false,
              setAttribute() {},
              focus() { this.focusCalled = true; },
              select() { this.selectCalled = true; },
              remove() { removed.push(this.value); },
            };
            global.window = { isSecureContext: false };
            global.navigator = {
              clipboard: {
                writeText() {
                  throw new Error("clipboard api should not be used outside secure context");
                },
              },
            };
            global.document = {
              body: {
                appendChild(node) {
                  appended.push(node);
                  return node;
                },
              },
              createElement(tag) {
                assert.equal(tag, "textarea");
                return textarea;
              },
              execCommand(cmd) {
                assert.equal(cmd, "copy");
                return true;
              },
            };

            const file = "web/task_entry_parts/80-project-ops.js";
            eval(extractFunction(file, "copyText"));

            (async () => {
              const ok = await copyText("019d-xyz");
              assert.equal(ok, true);
              assert.equal(appended.length, 1);
              assert.equal(textarea.value, "019d-xyz");
              assert.equal(textarea.focusCalled, true);
              assert.equal(textarea.selectCalled, true);
              assert.deepEqual(removed, ["019d-xyz"]);
            })().catch((err) => {
              console.error(err && err.stack ? err.stack : String(err));
              process.exit(1);
            });
          """
        )
        proc = subprocess.run(
            ["node", "-e", script, str(REPO_ROOT)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            self.fail(proc.stderr or proc.stdout or "node copyText fallback regression script failed")
