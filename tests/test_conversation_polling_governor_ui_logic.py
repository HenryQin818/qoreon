import shutil
import subprocess
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("node"), "node is required for UI logic regression checks")
class ConversationPollingGovernorUiLogicTests(unittest.TestCase):
    def test_runtime_polling_hints_drive_frontend_policy_and_cross_tab_gate(self) -> None:
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

            global.STATE = { project: "task_dashboard" };
            global.PCONV = { sessionDirectoryMetaByProject: Object.create(null) };
            global.document = { hidden: false };
            global.window = {};
            global.FEATURE_SESSIONS_CROSS_TAB_LEADER_KEY = "__feature_sessions_cross_tab_leader_v1__";
            global.readWindowFeatureFlag = (_flagName, defaultValue) => defaultValue;

            eval(extractFunction("web/task_parts/74-session-bootstrap-and-sessions.js", "ensureConversationSessionDirectoryStateMaps"));
            eval(extractFunction("web/task_parts/74-session-bootstrap-and-sessions.js", "markConversationSessionDirectoryMeta"));
            eval(extractFunction("web/task_parts/74-session-bootstrap-and-sessions.js", "normalizeConversationPollingNumber"));
            eval(extractFunction("web/task_parts/74-session-bootstrap-and-sessions.js", "normalizeConversationSessionsPollingHints"));
            eval(extractFunction("web/task_parts/74-session-bootstrap-and-sessions.js", "updateConversationProjectPollingMeta"));
            eval(extractFunction("web/task_parts/74-session-bootstrap-and-sessions.js", "conversationProjectPollingHints"));
            eval(extractFunction("web/task_parts/01-polling-governor.js", "isSessionsCrossTabLeaderEnabled"));
            eval(extractFunction("web/task_parts/01-polling-governor.js", "shouldUseSessionDirectoryLeader"));
            eval(extractFunction("web/task_parts/75-conversation-composer.js", "ensureConversationPollingGovernanceStateMaps"));
            eval(extractFunction("web/task_parts/75-conversation-composer.js", "getConversationPollingPolicy"));
            eval(extractFunction("web/task_parts/75-conversation-composer.js", "conversationPollDelay"));

            updateConversationProjectPollingMeta("task_dashboard", {
              perf_governance: { enabled: true },
              polling_hints: {
                version: "v1",
                sessions: {
                  enabled: true,
                  cache_ttl_ms: 2500,
                  inflight_wait_ms: 7000,
                  poll_interval_ms: 3000,
                  hidden_poll_interval_ms: 15000,
                  backoff_step_ms: 2000,
                  backoff_max_ms: 15000,
                  pause_when_hidden: true,
                  cross_tab_dedupe_enabled: true,
                },
              },
            });

            const hints = conversationProjectPollingHints("task_dashboard");
            assert.ok(hints);
            assert.equal(hints.cache_ttl_ms, 2500);
            assert.equal(hints.poll_interval_ms, 3000);
            assert.equal(hints.hidden_poll_interval_ms, 15000);
            assert.equal(hints.backoff_step_ms, 2000);
            assert.equal(hints.backoff_max_ms, 15000);
            assert.equal(conversationPollDelay("task_dashboard", false), 3000);
            assert.equal(shouldUseSessionDirectoryLeader("task_dashboard", "", { source: "poll" }), true);

            ensureConversationPollingGovernanceStateMaps();
            PCONV.pollFailureCountByProject.task_dashboard = 2;
            assert.equal(conversationPollDelay("task_dashboard", false), 7000);

            document.hidden = true;
            assert.equal(conversationPollDelay("task_dashboard", false), 0);
            document.hidden = false;

            updateConversationProjectPollingMeta("task_dashboard", {
              perf_governance: { enabled: true },
              polling_hints: {
                version: "v1",
                sessions: {
                  enabled: true,
                  cross_tab_dedupe_enabled: false,
                },
              },
            });
            assert.equal(shouldUseSessionDirectoryLeader("task_dashboard", "", { source: "poll" }), false);
            """
        )
        proc = subprocess.run(
            ["node", "-e", script, str(REPO_ROOT)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            self.fail(proc.stderr or proc.stdout or "node polling governor regression script failed")

    def test_explicit_sid_live_directory_meta_recovers_to_api_after_live_sessions_arrive(self) -> None:
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

            eval(extractFunction("web/task_parts/74-session-bootstrap-and-sessions.js", "shouldDeferConversationSessionDirectoryLiveLoad"));
            eval(extractFunction("web/task_parts/74-session-bootstrap-and-sessions.js", "resolveConversationSessionDirectoryLiveMeta"));

            const deferred = resolveConversationSessionDirectoryLiveMeta({
              canSeedSelectedSession: true,
              hasSelectedTimelineCache: false,
              hasServerDirectorySessions: false,
              existingMeta: null,
            });
            assert.equal(deferred.liveLoaded, false);
            assert.equal(deferred.source, "explicit-sid-deferred");

            const recovered = resolveConversationSessionDirectoryLiveMeta({
              canSeedSelectedSession: true,
              hasSelectedTimelineCache: true,
              hasServerDirectorySessions: true,
              existingMeta: {
                liveLoaded: false,
                source: "explicit-sid-deferred",
              },
            });
            assert.equal(recovered.liveLoaded, true);
            assert.equal(recovered.source, "api");
            """
        )
        proc = subprocess.run(
            ["node", "-e", script, str(REPO_ROOT)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            self.fail(proc.stderr or proc.stdout or "node explicit sid live directory regression script failed")
