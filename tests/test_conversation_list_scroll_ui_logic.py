import shutil
import subprocess
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("node"), "node is required for UI logic regression checks")
class ConversationListScrollUiLogicTests(unittest.TestCase):
    def test_scroll_position_is_remembered_and_restored_after_list_rerender(self) -> None:
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

            global.STATE = { project: "ndt", convListLayout: "channel" };
            global.PCONV = { listScrollTopByKey: Object.create(null) };
            global.normalizeConversationListLayout = (value) => {
              const text = String(value || "").trim().toLowerCase();
              return text === "flat" ? "flat" : "channel";
            };
            let scrollBox = {
              scrollTop: 480,
              scrollHeight: 1600,
              clientHeight: 400,
            };
            const leftList = {
              closest: () => scrollBox,
            };
            global.document = {
              getElementById(id) {
                if (id === "leftList") return leftList;
                return null;
              },
              querySelector(selector) {
                if (selector === "#channelAside .aside-scroll") return scrollBox;
                return null;
              },
            };
            global.requestAnimationFrame = (cb) => {
              cb();
              return 1;
            };

            const file = "web/task_parts/79-panel-wire-upload.js";
            eval(extractFunction(file, "conversationListScrollKey"));
            eval(extractFunction(file, "readConversationListStoredScrollTop"));
            eval(extractFunction(file, "rememberConversationListScrollTop"));
            eval(extractFunction(file, "conversationListScrollBox"));
            eval(extractFunction(file, "captureConversationListScrollTop"));
            eval(extractFunction(file, "restoreConversationListScrollTop"));

            assert.equal(captureConversationListScrollTop("ndt", "channel"), 480);
            assert.equal(readConversationListStoredScrollTop("ndt", "channel"), 480);

            scrollBox.scrollTop = 0;
            restoreConversationListScrollTop(480, "ndt", "channel");
            assert.equal(scrollBox.scrollTop, 480);
          """
        )
        proc = subprocess.run(
            ["node", "-e", script, str(REPO_ROOT)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            self.fail(proc.stderr or proc.stdout or "node scroll restore regression script failed")

    def test_select_session_captures_list_scroll_before_rebuild(self) -> None:
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

            const callOrder = [];
            global.STATE = {
              panelMode: "conv",
              selectedSessionId: "sid-old",
              selectedSessionExplicit: false,
              project: "ndt",
              convListLayout: "channel",
            };
            global.captureConversationListScrollTop = (...args) => {
              callOrder.push(["capture", ...args]);
              return 420;
            };
            global.normalizeConversationListLayout = (value) => String(value || "").trim().toLowerCase() === "flat" ? "flat" : "channel";
            global.localStorage = { setItem() {}, removeItem() {} };
            global.buildConversationLeftList = () => { callOrder.push(["buildLeft"]); };
            global.buildConversationMainList = () => { callOrder.push(["buildMain"]); };
            global.renderConversationDetail = () => { callOrder.push(["renderDetail"]); };
            global.refreshConversationTimeline = () => { callOrder.push(["refreshTimeline"]); };
            global.buildChannelConversationList = () => { callOrder.push(["buildChannel"]); };
            global.renderDetail = () => { callOrder.push(["renderChannelDetail"]); };
            global.updateSelectionUI = () => {};
            global.setHash = () => { callOrder.push(["setHash"]); };
            global.document = { getElementById() { return null; } };

            const file = "web/task_parts/76-runs-and-drawer.js";
            eval(extractFunction(file, "setSelectedSessionId"));

            setSelectedSessionId("sid-new", true, { explicit: true });

            assert.equal(callOrder[0][0], "capture");
            assert.deepEqual(callOrder[0].slice(1), ["ndt", "channel"]);
            assert.equal(callOrder[1][0], "buildLeft");
            assert.equal(global.STATE.selectedSessionId, "sid-new");
            assert.equal(global.STATE.selectedSessionExplicit, true);
          """
        )
        proc = subprocess.run(
            ["node", "-e", script, str(REPO_ROOT)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            self.fail(proc.stderr or proc.stdout or "node session select scroll capture regression script failed")
