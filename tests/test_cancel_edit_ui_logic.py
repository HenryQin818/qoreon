import shutil
import subprocess
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("node"), "node is required for UI logic regression checks")
class CancelEditUiLogicTests(unittest.TestCase):
    def test_cancel_edit_success_hides_run_before_background_refresh(self) -> None:
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

            global.PCONV = {
              runActionBusy: Object.create(null),
              locallyHiddenRunIds: new Set(),
            };
            const hints = [];
            const renders = [];
            const restored = [];
            let refreshCalled = false;
            global.setHintText = (...args) => hints.push(args);
            global.callRunAction = async (runId, action) => {
              assert.equal(runId, "run-1");
              assert.equal(action, "cancel_edit");
              return { restored: { message: "撤回内容" } };
            };
            global.restoreConversationDraft = (payload) => restored.push(payload);
            global.renderConversationDetail = (forceScroll) => {
              renders.push({
                forceScroll,
                hidden: isConversationRunLocallyHidden("run-1"),
                busy: String(PCONV.runActionBusy["run-1"] || ""),
                restoredCount: restored.length,
              });
            };
            global.refreshConversationPanel = () => {
              refreshCalled = true;
              return new Promise(() => {});
            };
            global.scheduleConversationPoll = () => {};

            eval(extractFunction("web/task_parts/60-conversation.js", "ensureConversationLocallyHiddenRunIds"));
            eval(extractFunction("web/task_parts/60-conversation.js", "markConversationRunLocallyHidden"));
            eval(extractFunction("web/task_parts/60-conversation.js", "isConversationRunLocallyHidden"));
            eval(extractFunction("web/task_parts/75-conversation-composer.js", "cancelQueuedRunForEdit"));

            (async () => {
              await cancelQueuedRunForEdit({ id: "run-1" });
              assert.equal(isConversationRunLocallyHidden("run-1"), true);
              assert.deepEqual(restored, [{ message: "撤回内容" }]);
              assert.equal(refreshCalled, true);
              assert.equal(String(PCONV.runActionBusy["run-1"] || ""), "");
              assert.equal(renders.length, 2);
              assert.deepEqual(renders[0], {
                forceScroll: undefined,
                hidden: false,
                busy: "cancel_edit",
                restoredCount: 0,
              });
              assert.deepEqual(renders[1], {
                forceScroll: false,
                hidden: true,
                busy: "cancel_edit",
                restoredCount: 1,
              });
              assert.deepEqual(hints[hints.length - 1], ["conv", "已撤回到输入框，可编辑后重新发送。"]);
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
            self.fail(proc.stderr or proc.stdout or "node cancel edit ui regression script failed")

    def test_timeline_filters_locally_hidden_runs(self) -> None:
        source = (REPO_ROOT / "web/task_parts/60-conversation.js").read_text(encoding="utf-8")
        self.assertIn("const visibleRuns = runs.filter((item) => !isConversationRunLocallyHidden(item && item.id));", source)
        self.assertIn("for (const r of visibleRuns)", source)
        self.assertIn("buildConversationLocalReceiptAnchorMaps(visibleRuns", source)
