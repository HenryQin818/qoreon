import shutil
import subprocess
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("node"), "node is required for UI logic regression checks")
class ConversationRunDetailPollingUiLogicTests(unittest.TestCase):
    def test_terminal_run_detail_count_gap_does_not_force_refresh(self) -> None:
        script = textwrap.dedent(
            r"""
            const assert = require("node:assert/strict");
            const fs = require("node:fs");
            const path = require("node:path");

            const repoRoot = process.argv[1];

            function extractFunction(file, name) {
              const text = fs.readFileSync(path.join(repoRoot, file), "utf8");
              const signature = new RegExp(`(?:async\s+)?function ${name}\\(`);
              const match = signature.exec(text);
              if (!match) throw new Error(`missing function ${name} in ${file}`);
              const start = match.index;
              const headerMatch = text
                .slice(start)
                .match(new RegExp(`(?:async\s+)?function ${name}\\([^\\n]*\\)\\s*\\{`));
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

            global.isRunWorking = (state) => ["running", "queued", "retry_waiting"].includes(String(state || "").toLowerCase());
            eval(extractFunction("web/task_parts/70-conversation-timeline.js", "conversationRunDetailRefreshPolicy"));

            const terminalPolicy = conversationRunDetailRefreshPolicy("done", {
              reportedCount: 6,
              items: ["one", "two", "three", "four", "five"],
            });
            assert.equal(terminalPolicy.terminal, true);
            assert.equal(terminalPolicy.processDetailLagging, true);
            assert.equal(terminalPolicy.force, false);
            assert.equal(terminalPolicy.maxAgeMs, 0);

            const runningPolicy = conversationRunDetailRefreshPolicy("running", {
              reportedCount: 6,
              items: ["one", "two", "three", "four", "five"],
            });
            assert.equal(runningPolicy.terminal, false);
            assert.equal(runningPolicy.processDetailLagging, true);
            assert.equal(runningPolicy.force, true);
            assert.equal(runningPolicy.maxAgeMs, 1200);

            const syncedRunningPolicy = conversationRunDetailRefreshPolicy("running", {
              reportedCount: 5,
              items: ["one", "two", "three", "four", "five"],
            });
            assert.equal(syncedRunningPolicy.force, false);
            assert.equal(syncedRunningPolicy.maxAgeMs, 1200);
            """
        )
        proc = subprocess.run(
            ["node", "-e", script, str(REPO_ROOT)],
            text=True,
            capture_output=True,
            check=False,
        )
        if proc.returncode != 0:
            self.fail(proc.stderr or proc.stdout or "node conversation run detail polling regression script failed")


if __name__ == "__main__":
    unittest.main()
