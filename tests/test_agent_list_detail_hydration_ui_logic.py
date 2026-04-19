import shutil
import subprocess
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("node"), "node is required for UI logic regression checks")
class AgentListDetailHydrationUiLogicTests(unittest.TestCase):
    def test_task_observatory_uses_light_source_without_detail_hydration(self) -> None:
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

            const file = "web/task_parts/77-project-modes.js";
            const source = fs.readFileSync(path.join(repoRoot, file), "utf8");
            assert.equal(source.includes("* 4, 18"), false);

            global.STATE = { project: "task_dashboard", selectedSessionId: "sid-current" };
            const TASK_OBSERVATORY_DEFAULT_VISIBLE = 10;
            const TASK_OBSERVATORY_UI = { detailRequestedByProject: Object.create(null) };
            const loads = [];
            let renderCount = 0;
            global.firstNonEmptyText = (values, fallback = "") => {
              for (const value of values || []) {
                const text = String(value || "").trim();
                if (text) return text;
              }
              return fallback;
            };
            global.normalizeTaskTrackingClient = (raw) => {
              const src = raw && typeof raw === "object" ? raw : {};
              const current = src.current_task_ref || null;
              const refs = Array.isArray(src.conversation_task_refs) ? src.conversation_task_refs : [];
              const actions = Array.isArray(src.recent_task_actions) ? src.recent_task_actions : [];
              if (!current && !refs.length && !actions.length && !src.version) return null;
              return {
                version: src.version || "v1.1",
                current_task_ref: current,
                conversation_task_refs: refs,
                recent_task_actions: actions,
              };
            };
            global.hasConversationTaskTrackingData = (raw) => !!global.normalizeTaskTrackingClient(raw);
            global.render = () => { renderCount += 1; };
            global.ensureConversationSessionDetailLoaded = (sid, opts = {}) => {
              loads.push({ sid, opts });
              return Promise.resolve({ sid });
            };

            eval(extractFunction(file, "taskObservatoryProjectKey"));
            eval(extractFunction(file, "taskObservatorySessionNeedsCreatedAtHydration"));
            eval(extractFunction(file, "taskObservatoryShouldLoadDetailForSession"));
            eval(extractFunction(file, "taskObservatoryScheduleDetailLoads"));

            const sessions = [
              { id: "sid-other-missing" },
              { id: "sid-other-needs-created-at", task_tracking: { current_task_ref: { task_id: "TASK-1" } } },
              { id: "sid-current", task_tracking: { current_task_ref: { task_id: "TASK-2" } } },
              { id: "sid-ready", task_tracking: { current_task_ref: { task_id: "TASK-3", created_at: "2026-04-11T20:00:00+0800" } } },
            ];

            assert.equal(taskObservatoryShouldLoadDetailForSession(sessions[0], "task_dashboard"), false);
            assert.equal(taskObservatoryShouldLoadDetailForSession(sessions[1], "task_dashboard"), false);
            assert.equal(taskObservatoryShouldLoadDetailForSession(sessions[2], "task_dashboard"), false);

            taskObservatoryScheduleDetailLoads("task_dashboard", sessions, 10);

            setImmediate(() => {
              try {
                assert.deepEqual(loads.map((row) => row.sid), []);
                assert.equal(renderCount, 0);
              } catch (err) {
                console.error(err && err.stack ? err.stack : err);
                process.exit(1);
              }
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
            self.fail(proc.stderr or proc.stdout or "node agent list detail hydration regression script failed")


if __name__ == "__main__":
    unittest.main()
