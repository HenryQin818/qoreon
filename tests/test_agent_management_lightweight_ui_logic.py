import shutil
import subprocess
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("node"), "node is required for UI logic regression checks")
class AgentManagementLightweightUiLogicTests(unittest.TestCase):
    def test_session_detail_hydration_is_deferred_and_reports_slow_state(self) -> None:
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

            global.PCONV = {};
            global.looksLikeSessionId = (sid) => !!String(sid || "").trim();
            global.hasConversationTaskTrackingData = (raw) => !!(raw && raw.current_task_ref);
            const calls = [];
            global.ensureConversationSessionDetailLoaded = (sid, opts = {}) => {
              calls.push({ sid, opts });
              return Promise.resolve({ sessionId: sid });
            };

            const helperFile = "web/task_parts/74-session-bootstrap-and-sessions.js";
            eval(extractFunction(helperFile, "ensureConversationSessionDetailStateMaps"));
            eval(extractFunction(helperFile, "isConversationSessionDetailLoading"));
            eval(extractFunction(helperFile, "getConversationSessionDetailError"));
            eval(extractFunction(helperFile, "conversationSessionHasDetailPayload"));
            eval(extractFunction(helperFile, "conversationSessionDetailLoadedRecently"));
            eval(extractFunction(helperFile, "conversationSessionDetailHydrationStatus"));
            eval(extractFunction(helperFile, "clearConversationSessionDetailHydrationTimer"));
            eval(extractFunction(helperFile, "requestConversationSessionDetailHydration"));
            eval(extractFunction(helperFile, "scheduleConversationSessionDetailHydration"));

            assert.equal(scheduleConversationSessionDetailHydration("sid-1", { delayMs: 25, maxAgeMs: 60000 }), true);
            assert.equal(calls.length, 0);
            const deferred = conversationSessionDetailHydrationStatus("sid-1", {});
            assert.equal(deferred.state, "deferred");
            assert.match(deferred.message, /后台补全中/);
            assert.equal(deferred.canRetry, true);

            setTimeout(() => {
              try {
                assert.equal(calls.length, 1);
                assert.equal(calls[0].sid, "sid-1");
                assert.equal(calls[0].opts.force, false);
                process.exit(0);
              } catch (err) {
                console.error(err && err.stack ? err.stack : err);
                process.exit(1);
              }
            }, 60);
            """
        )
        proc = subprocess.run(
            ["node", "-e", script, str(REPO_ROOT)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if proc.returncode != 0:
            self.fail(proc.stderr or proc.stdout or "node lightweight hydration regression script failed")

    def test_conversation_detail_keeps_send_path_lightweight(self) -> None:
        conv_js = (REPO_ROOT / "web" / "task_parts" / "60-conversation.js").read_text(encoding="utf-8")
        bootstrap_js = (REPO_ROOT / "web" / "task_parts" / "74-session-bootstrap-and-sessions.js").read_text(encoding="utf-8")
        css = (REPO_ROOT / "web" / "task_parts" / "60-conversation.css").read_text(encoding="utf-8")

        self.assertIn("function renderConversationDetailHydrationHint", conv_js)
        self.assertIn("scheduleConversationSessionDetailHydration(currentSessionId", conv_js)
        self.assertNotIn("ensureConversationSessionDetailLoaded(currentSessionId, { maxAgeMs: 15_000 })", conv_js)
        self.assertIn("input.disabled = !!sessionBindingBlockMeta;", conv_js)
        self.assertIn("sendBtn.disabled = !!sessionBindingBlockMeta || PCONV.sending;", conv_js)
        self.assertIn('reason: "task_drawer"', conv_js)

        self.assertIn("function conversationSessionDetailHydrationStatus", bootstrap_js)
        self.assertIn("状态更新中", bootstrap_js)
        self.assertIn("状态可能延迟", bootstrap_js)
        self.assertIn("后台补全中", bootstrap_js)
        self.assertIn("点击重试状态", conv_js)

        self.assertIn(".conv-detail-hydration", css)
        self.assertIn(".conv-detail-hydration-retry", css)


if __name__ == "__main__":
    unittest.main()
