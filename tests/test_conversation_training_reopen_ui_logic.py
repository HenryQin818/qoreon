import shutil
import subprocess
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("node"), "node is required for UI logic regression checks")
class ConversationTrainingReopenUiLogicTests(unittest.TestCase):
    def test_reopen_training_prompt_clears_dismissed_and_rerenders_current_runs(self) -> None:
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

            const calls = [];
            const runs = [{ id: "run-1" }, { id: "run-2" }];
            global.currentConversationCtx = () => ({
              projectId: "p1",
              sessionId: "s1",
            });
            global.convComposerDraftKey = (projectId, sessionId) => `${projectId}::${sessionId}`;
            global.getConversationTrainingSentAtByKey = () => "";
            global.currentConversationTrainingRuns = () => runs;
            global.conversationTrainingRemainingCount = (items) => 3 - items.length;
            global.setConversationTrainingManualOpenByKey = (...args) => calls.push(["manual", ...args]);
            global.setConversationTrainingDismissedByKey = (...args) => calls.push(["dismissed", ...args]);
            global.renderConversationTrainingPrompt = (...args) => calls.push(["render", ...args]);

            const file = "web/task_parts/75-conversation-composer.js";
            eval(extractFunction(file, "reopenConversationTrainingPrompt"));

            reopenConversationTrainingPrompt();

            assert.deepEqual(calls[0], ["manual", "p1::s1", true]);
            assert.deepEqual(calls[1], ["dismissed", "p1::s1", false]);
            assert.equal(calls[2][0], "render");
            assert.deepEqual(calls[2][1], { projectId: "p1", sessionId: "s1" });
            assert.equal(calls[2][2], runs);
            assert.deepEqual(calls[2][3], { timelineReady: true });
          """
        )
        proc = subprocess.run(
            ["node", "-e", script, str(REPO_ROOT)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            self.fail(proc.stderr or proc.stdout or "node reopen training prompt regression script failed")

    def test_render_training_reopen_button_state_controls_visibility_and_label(self) -> None:
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

            class ClassList {
              constructor() { this.values = new Set(); }
              add(name) { this.values.add(name); }
              remove(name) { this.values.delete(name); }
              toggle(name, force) {
                if (force) this.values.add(name);
                else this.values.delete(name);
              }
              contains(name) { return this.values.has(name); }
            }

            const attrs = Object.create(null);
            const button = {
              style: {},
              disabled: false,
              classList: new ClassList(),
              title: "",
              setAttribute(name, value) {
                attrs[name] = String(value);
              },
              getAttribute(name) {
                return Object.prototype.hasOwnProperty.call(attrs, name) ? attrs[name] : null;
              },
            };

            const file = "web/task_parts/75-conversation-composer.js";
            eval(extractFunction(file, "renderConversationTrainingReopenButtonState"));

            renderConversationTrainingReopenButtonState(button, {
              visible: true,
              dismissed: true,
              showing: false,
              sending: false,
            });
            assert.equal(button.style.display, "");
            assert.equal(button.disabled, false);
            assert.equal(button.classList.contains("active"), true);
            assert.equal(button.title, "重新显示 Agent 培训");
            assert.equal(button.getAttribute("aria-hidden"), "false");

            renderConversationTrainingReopenButtonState(button, { visible: false });
            assert.equal(button.style.display, "none");
            assert.equal(button.disabled, true);
            assert.equal(button.classList.contains("active"), false);
            assert.equal(button.getAttribute("aria-hidden"), "true");

            renderConversationTrainingReopenButtonState(button, {
              visible: true,
              completed: true,
              showing: false,
              sending: false,
            });
            assert.equal(button.style.display, "");
            assert.equal(button.disabled, false);
            assert.equal(button.title, "查看已发送的 Agent 培训");
          """
        )
        proc = subprocess.run(
            ["node", "-e", script, str(REPO_ROOT)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            self.fail(proc.stderr or proc.stdout or "node training reopen button state regression script failed")
