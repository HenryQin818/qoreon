import shutil
import subprocess
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("node"), "node is required for UI logic regression checks")
class SessionsPollingAbortTrialUiLogicTests(unittest.TestCase):
    def test_read_cadence_uses_runtime_hints_and_abort_helpers_are_removed(self) -> None:
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
            global.pushPollingTrace = () => {};
            global.pollingGovernorPageHidden = () => false;
            global.conversationProjectPollingHints = () => ({
              enabled: true,
              poll_interval_ms: 3000,
              hidden_poll_interval_ms: 15000,
              pause_when_hidden: true,
            });

            const file = "web/task_parts/74-session-bootstrap-and-sessions.js";
            const source = fs.readFileSync(path.join(repoRoot, file), "utf8");
            eval(extractFunction(file, "ensureConversationSessionDirectoryStateMaps"));
            eval(extractFunction(file, "ensureConversationSessionDetailStateMaps"));
            eval(extractFunction(file, "normalizeConversationPollingNumber"));
            eval(extractFunction(file, "conversationProjectPollingCadenceMs"));

            ensureConversationSessionDirectoryStateMaps();
            ensureConversationSessionDetailStateMaps();

            assert.equal(conversationProjectPollingCadenceMs("task_dashboard"), 3000);
            assert.equal(Object.prototype.hasOwnProperty.call(PCONV, "sessionFetchAbortControllerByKey"), false);
            assert.equal(Object.prototype.hasOwnProperty.call(PCONV, "sessionDetailAbortControllerById"), false);
            assert.equal(source.includes("sessionFetchAbortControllerByKey"), false);
            assert.equal(source.includes("sessionDetailAbortControllerById"), false);
            assert.equal(source.includes("isConversationAbortError"), false);
            assert.equal(source.includes("abortConversationRequestController"), false);
            assert.equal(source.includes("createConversationRequestController"), false);
            assert.equal(source.includes("visibleTrialIntervalMs"), false);
            """
        )
        proc = subprocess.run(
            ["node", "-e", script, str(REPO_ROOT)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            self.fail(proc.stderr or proc.stdout or "node sessions polling abort trial regression script failed")


if __name__ == "__main__":
    unittest.main()
