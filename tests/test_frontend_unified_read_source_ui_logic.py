import shutil
import subprocess
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("node"), "node is required for UI logic regression checks")
class FrontendUnifiedReadSourceUiLogicTests(unittest.TestCase):
    def test_regular_paths_use_unified_light_sources_and_request_dedupe(self) -> None:
        script = textwrap.dedent(
            r"""
            const assert = require("node:assert/strict");
            const fs = require("node:fs");
            const path = require("node:path");

            const repoRoot = process.argv[1];

            (async () => {
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

            global.STATE = { project: "task_dashboard", panelMode: "conv", selectedSessionId: "sid-1" };
            global.PCONV = {
              sessionDirectoryMetaByProject: Object.create(null),
              memoDrawerOpen: false,
              memoDrawerSessionKey: "",
              memoBySessionKey: Object.create(null),
              memoRequestSeqBySessionKey: Object.create(null),
              memoLoadingBySessionKey: Object.create(null),
            };
            global.document = { hidden: false };
            global.pushPollingTrace = () => {};
            global.conversationProjectPollingHints = () => ({
              enabled: true,
              cache_ttl_ms: 2500,
              inflight_wait_ms: 7000,
              poll_interval_ms: 3000,
            });
            global.pollingGovernorPageHidden = () => false;
            global.looksLikeSessionId = () => true;

            eval(extractFunction("web/task_parts/74-session-bootstrap-and-sessions.js", "shouldForceConversationSessionDirectoryLiveFetch"));
            eval(extractFunction("web/task_parts/74-session-bootstrap-and-sessions.js", "normalizeConversationPollingNumber"));
            eval(extractFunction("web/task_parts/74-session-bootstrap-and-sessions.js", "conversationProjectPollingCadenceMs"));
            eval(extractFunction("web/task_parts/74-session-bootstrap-and-sessions.js", "resolveConversationSessionsFreshnessMs"));

            const sessionsSource = fs.readFileSync(path.join(repoRoot, "web/task_parts/74-session-bootstrap-and-sessions.js"), "utf8");
            assert.equal(sessionsSource.includes("Math.max(freshnessMs, 18000"), true);
            assert.equal(
              resolveConversationSessionsFreshnessMs("task_dashboard", "", { source: "poll", freshnessMs: 2500 }),
              18000
            );

            let memoFetchCount = 0;
            global.convComposerDraftKey = (projectId, sessionId) => `${projectId}::${sessionId}`;
            global.getConversationMemoStateByKey = () => ({ fetchedAt: 0 });
            global.renderConversationMemoUi = () => {};
            global.setConversationMemoHintByKey = () => {};
            global.cleanConversationMemoConsumedByKey = () => {};
            global.normalizeConversationMemoItem = (item) => item;
            global.loadConversationMemos = async () => {
              memoFetchCount += 1;
              return { items: [], count: 0 };
            };

            eval(extractFunction("web/task_parts/75-conversation-composer.js", "isConversationMemoDrawerOpenForKey"));
            eval(extractFunction("web/task_parts/75-conversation-composer.js", "ensureConversationMemosLoaded"));

            await ensureConversationMemosLoaded("task_dashboard", "sid-1", { maxAgeMs: 1000 });
            assert.equal(memoFetchCount, 0);

            PCONV.memoDrawerOpen = true;
            PCONV.memoDrawerSessionKey = "task_dashboard::sid-1";
            await Promise.all([
              ensureConversationMemosLoaded("task_dashboard", "sid-1", { maxAgeMs: 1000, source: "memo-drawer" }),
              ensureConversationMemosLoaded("task_dashboard", "sid-1", { maxAgeMs: 1000, source: "memo-drawer" }),
            ]);
            assert.equal(memoFetchCount, 1);

            let runDetailWarmCount = 0;
            global.ensureConversationRunDetail = () => { runDetailWarmCount += 1; };
            global.getRunDisplayState = () => "running";
            global.isRunWorking = (st) => String(st) === "running";
            eval(extractFunction("web/task_parts/60-conversation.js", "warmConversationTimelineWorkingRunDetails"));
            warmConversationTimelineWorkingRunDetails("task_dashboard", "sid-1", [{ id: "run-1", status: "running" }]);
            assert.equal(runDetailWarmCount, 0);
            const timelineSource = fs.readFileSync(path.join(repoRoot, "web/task_parts/70-conversation-timeline.js"), "utf8");
            assert.equal(timelineSource.includes("assistant-body-prefetch-disabled"), true);
            assert.equal(timelineSource.includes("auto-process-drawer-uses-light-payload"), true);

            eval(extractFunction("web/task_parts/10-codex-api.js", "taskDashboardCodexApiReadState"));
            eval(extractFunction("web/task_parts/10-codex-api.js", "loadRuns"));
            eval(extractFunction("web/task_parts/10-codex-api.js", "loadRun"));

            const fetchCounts = Object.create(null);
            global.fetch = async (url) => {
              fetchCounts[url] = Number(fetchCounts[url] || 0) + 1;
              await new Promise((resolve) => setTimeout(resolve, 5));
              return {
                ok: true,
                json: async () => String(url).includes("/api/codex/run/")
                  ? ({ run: { id: "run-1" } })
                  : ({ runs: [] }),
              };
            };

            await Promise.all([
              loadRuns({ projectId: "task_dashboard", sessionId: "sid-1", limit: 30, payloadMode: "light" }),
              loadRuns({ projectId: "task_dashboard", sessionId: "sid-1", limit: 30, payloadMode: "light" }),
            ]);
            assert.equal(fetchCounts["/api/codex/runs?limit=30&projectId=task_dashboard&sessionId=sid-1&payloadMode=light"], 1);

            await Promise.all([loadRun("run-1"), loadRun("run-1")]);
            assert.equal(fetchCounts["/api/codex/run/run-1"], 1);
            })().catch((err) => {
              console.error(err && err.stack ? err.stack : err);
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
            self.fail(proc.stderr or proc.stdout or "node unified read source regression script failed")


if __name__ == "__main__":
    unittest.main()
