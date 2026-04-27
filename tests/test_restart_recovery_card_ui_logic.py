import shutil
import subprocess
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("node"), "node is required for UI logic regression checks")
class RestartRecoveryCardUiLogicTests(unittest.TestCase):
    def test_running_recovery_card_renders_interrupt_next_to_reply(self) -> None:
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
              const children = [];
              return {
                tag,
                attrs: { ...attrs },
                children,
                childNodes: children,
                textContent: attrs.text || "",
                appendChild(child) {
                  children.push(child);
                  return child;
                },
                addEventListener(type, handler) {
                  listeners[type] = handler;
                },
                async dispatch(type) {
                  const handler = listeners[type];
                  if (!handler) return;
                  return await handler({
                    preventDefault() {},
                    stopPropagation() {},
                  });
                },
              };
            }

            function findByClass(node, className) {
              if (!node) return null;
              const cls = String((node.attrs && node.attrs.class) || "");
              if (cls.split(/\s+/).includes(className)) return node;
              for (const child of node.children || []) {
                const hit = findByClass(child, className);
                if (hit) return hit;
              }
              return null;
            }

            const calls = [];
            global.PCONV = { runActionBusy: Object.create(null) };
            global.el = (tag, attrs = {}, ...children) => {
              const node = createNode(tag, attrs);
              for (const child of children) {
                if (child != null) node.appendChild(child);
              }
              return node;
            };
            global.chip = (text, tone) => createNode("chip", { text: String(text), tone: String(tone || "") });
            global.renderConversationReplyQuote = () => null;
            global.compactDateTime = (value) => String(value || "");
            global.shortDateTime = (value) => String(value || "");
            global.firstNonEmptyText = (items) => {
              for (const item of (Array.isArray(items) ? items : [])) {
                const text = String(item || "").trim();
                if (text) return text;
              }
              return "";
            };
            global.buildRestartRecoveryProgressMeta = () => ({
              state: "running",
              isWorking: true,
              stateLabel: "处理中",
              stateTone: "warn",
              latestProgressAt: "",
              snippet: "",
              rows: [],
            });
            global.interruptRunningRun = async (runMeta) => calls.push(["interrupt", runMeta && runMeta.id]);
            global.cancelRetryWaitingRun = async (runMeta) => calls.push(["cancel", runMeta && runMeta.id]);

            const file = "web/task_parts/70-conversation-timeline.js";
            eval(extractFunction(file, "renderRestartRecoveryCard"));

            (async () => {
              const root = renderRestartRecoveryCard({}, {
                runId: "recovery-1",
                runMeta: { id: "recovery-1" },
                rawText: "请继续",
                onReply: ({ text }) => calls.push(["reply", text]),
              });
              const ops = findByClass(root, "callback-event-ops");
              assert.ok(ops);
              assert.equal(ops.children.length, 2);
              assert.equal(ops.children[0].textContent, "打断恢复");
              assert.equal(ops.children[1].textContent, "回复");
              await ops.children[0].dispatch("click");
              await ops.children[1].dispatch("click");
              assert.deepEqual(calls[0], ["interrupt", "recovery-1"]);
              assert.deepEqual(calls[1], ["reply", "请继续"]);
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
            self.fail(proc.stderr or proc.stdout or "node running restart recovery card regression script failed")

    def test_queued_recovery_card_renders_cancel_recovery_action(self) -> None:
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
              const children = [];
              return {
                tag,
                attrs: { ...attrs },
                children,
                childNodes: children,
                textContent: attrs.text || "",
                appendChild(child) {
                  children.push(child);
                  return child;
                },
                addEventListener(type, handler) {
                  listeners[type] = handler;
                },
                async dispatch(type) {
                  const handler = listeners[type];
                  if (!handler) return;
                  return await handler({
                    preventDefault() {},
                    stopPropagation() {},
                  });
                },
              };
            }

            function findByClass(node, className) {
              if (!node) return null;
              const cls = String((node.attrs && node.attrs.class) || "");
              if (cls.split(/\s+/).includes(className)) return node;
              for (const child of node.children || []) {
                const hit = findByClass(child, className);
                if (hit) return hit;
              }
              return null;
            }

            const calls = [];
            global.PCONV = { runActionBusy: Object.create(null) };
            global.el = (tag, attrs = {}, ...children) => {
              const node = createNode(tag, attrs);
              for (const child of children) {
                if (child != null) node.appendChild(child);
              }
              return node;
            };
            global.chip = (text, tone) => createNode("chip", { text: String(text), tone: String(tone || "") });
            global.renderConversationReplyQuote = () => null;
            global.compactDateTime = (value) => String(value || "");
            global.shortDateTime = (value) => String(value || "");
            global.firstNonEmptyText = (items) => {
              for (const item of (Array.isArray(items) ? items : [])) {
                const text = String(item || "").trim();
                if (text) return text;
              }
              return "";
            };
            global.buildRestartRecoveryProgressMeta = () => ({
              state: "queued",
              isWorking: true,
              stateLabel: "排队中",
              stateTone: "warn",
              latestProgressAt: "",
              snippet: "",
              rows: [],
            });
            global.interruptRunningRun = async (runMeta) => calls.push(["interrupt", runMeta && runMeta.id]);
            global.cancelRetryWaitingRun = async (runMeta) => calls.push(["cancel", runMeta && runMeta.id]);

            const file = "web/task_parts/70-conversation-timeline.js";
            eval(extractFunction(file, "renderRestartRecoveryCard"));

            (async () => {
              const root = renderRestartRecoveryCard({}, {
                runId: "recovery-2",
                runMeta: { id: "recovery-2" },
              });
              const ops = findByClass(root, "callback-event-ops");
              assert.ok(ops);
              assert.equal(ops.children.length, 1);
              assert.equal(ops.children[0].textContent, "取消恢复");
              await ops.children[0].dispatch("click");
              assert.deepEqual(calls, [["cancel", "recovery-2"]]);
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
            self.fail(proc.stderr or proc.stdout or "node queued restart recovery card regression script failed")
