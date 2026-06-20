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
            const CONVERSATION_SESSIONS_VISIBLE_POLL_TARGET_MS = 12000;

            eval(extractFunction("web/task_parts/74-session-bootstrap-and-sessions.js", "ensureConversationSessionDirectoryStateMaps"));
            eval(extractFunction("web/task_parts/74-session-bootstrap-and-sessions.js", "markConversationSessionDirectoryMeta"));
            eval(extractFunction("web/task_parts/74-session-bootstrap-and-sessions.js", "normalizeConversationPollingNumber"));
            eval(extractFunction("web/task_parts/74-session-bootstrap-and-sessions.js", "defaultConversationSessionsPollingHints"));
            eval(extractFunction("web/task_parts/74-session-bootstrap-and-sessions.js", "normalizeConversationVisiblePollIntervalMs"));
            eval(extractFunction("web/task_parts/74-session-bootstrap-and-sessions.js", "normalizeConversationSessionsPollingHints"));
            eval(extractFunction("web/task_parts/74-session-bootstrap-and-sessions.js", "updateConversationProjectPollingMeta"));
            eval(extractFunction("web/task_parts/74-session-bootstrap-and-sessions.js", "conversationProjectPollingHints"));
            eval(extractFunction("web/task_parts/01-polling-governor.js", "isSessionsCrossTabLeaderEnabled"));
            eval(extractFunction("web/task_parts/01-polling-governor.js", "shouldUseSessionDirectoryLeader"));
            eval(extractFunction("web/task_parts/75-conversation-composer.js", "ensureConversationPollingGovernanceStateMaps"));
            eval(extractFunction("web/task_parts/75-conversation-composer.js", "getConversationPollingPolicy"));
            eval(extractFunction("web/task_parts/75-conversation-composer.js", "conversationPollDelay"));
            eval(extractFunction("web/task_parts/75-conversation-composer.js", "shouldUseConversationSelectedRuntimeFastPoll"));

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
            assert.equal(shouldUseConversationSelectedRuntimeFastPoll(true), false);
            document.hidden = false;
            assert.equal(shouldUseConversationSelectedRuntimeFastPoll(true), true);
            assert.equal(shouldUseConversationSelectedRuntimeFastPoll(false), false);

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

            updateConversationProjectPollingMeta("task_dashboard", {
              sessions_read_model: {
                payload_mode: "summary",
                cache_ttl_ms: 4000,
                inflight_wait_ms: 8000,
              },
            });
            const readModelHints = conversationProjectPollingHints("task_dashboard");
            assert.equal(readModelHints.poll_interval_ms, 12000);
            assert.equal(readModelHints.hidden_poll_interval_ms, 12000);
            assert.equal(readModelHints.pause_when_hidden, false);
            assert.equal(readModelHints.cross_tab_dedupe_enabled, false);
            assert.equal(shouldUseSessionDirectoryLeader("task_dashboard", "", { source: "poll" }), false);
            PCONV.pollFailureCountByProject.task_dashboard = 0;
            document.hidden = true;
            assert.equal(conversationPollDelay("task_dashboard", false), 12000);
            assert.equal(conversationPollDelay("task_dashboard", true), 12000);
            document.hidden = false;

            const sessionsSource = fs.readFileSync(path.join(repoRoot, "web/task_parts/74-session-bootstrap-and-sessions.js"), "utf8");
            assert.equal(sessionsSource.includes('qs.set("payloadMode", payloadMode);'), true);
            assert.equal(sessionsSource.includes("readSessionDirectorySnapshot(pid, channelName"), true);
            assert.equal(sessionsSource.includes("publishSessionDirectorySnapshot(pid, channelName"), true);
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

    def test_selected_conversation_fast_poll_uses_cached_working_runs(self) -> None:
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
            global.PCONV = {
              detailMap: Object.create(null),
              sessionTimelineMap: Object.create(null),
              runsBySession: Object.create(null),
            };

            function getRunDisplayState(run, detail) {
              if (detail && detail.status) return detail.status;
              return (run && (run.display_state || run.displayState || run.status || run.state)) || "";
            }

            eval(extractFunction("web/task_parts/60-conversation.js", "isConversationRunWorkingForPoll"));
            eval(extractFunction("web/task_parts/60-conversation.js", "conversationSelectedSessionHasWorkingRun"));

            PCONV.sessionTimelineMap["task_dashboard::sid-a"] = [{ id: "r-running", status: "running" }];
            assert.equal(conversationSelectedSessionHasWorkingRun("task_dashboard", "sid-a"), true);

            PCONV.sessionTimelineMap["task_dashboard::sid-a"] = [{ id: "r-done", status: "done" }];
            PCONV.runsBySession["sid-a"] = [];
            assert.equal(conversationSelectedSessionHasWorkingRun("task_dashboard", "sid-a"), false);

            PCONV.runsBySession["sid-a"] = [{ id: "r-queued", status: "queued" }];
            assert.equal(conversationSelectedSessionHasWorkingRun("task_dashboard", "sid-a"), true);

            PCONV.runsBySession["sid-a"] = [{ id: "r-retry", display_state: "retry_waiting" }];
            assert.equal(conversationSelectedSessionHasWorkingRun("task_dashboard", "sid-a"), true);

            PCONV.detailMap["r-detail"] = { status: "running" };
            PCONV.runsBySession["sid-a"] = [{ id: "r-detail", status: "done" }];
            assert.equal(conversationSelectedSessionHasWorkingRun("task_dashboard", "sid-a"), true);

            PCONV.detailMap["r-terminal"] = { status: "done" };
            PCONV.runsBySession["sid-a"] = [{ id: "r-terminal", status: "running" }];
            assert.equal(conversationSelectedSessionHasWorkingRun("task_dashboard", "sid-a"), false);

            PCONV.detailMap = Object.create(null);
            PCONV.runsBySession["sid-a"] = [{ id: "r-error", status: "error" }];
            assert.equal(conversationSelectedSessionHasWorkingRun("task_dashboard", "sid-a"), false);

            PCONV.runsBySession["sid-a"] = [{ id: "r-external", status: "external_busy" }];
            assert.equal(conversationSelectedSessionHasWorkingRun("task_dashboard", "sid-a"), false);

            const conversationSource = fs.readFileSync(path.join(repoRoot, "web/task_parts/60-conversation.js"), "utf8");
            const composerSource = fs.readFileSync(path.join(repoRoot, "web/task_parts/75-conversation-composer.js"), "utf8");
            assert.equal(composerSource.includes("var CONVERSATION_SELECTED_FAST_POLL_MS = 3500;"), true);
            assert.equal(/selectedFastPollAllowed\s*\?\s*1200/.test(conversationSource), false);
            assert.equal(/scheduleConversationPoll\(1200\)/.test(composerSource), false);
            """
        )
        proc = subprocess.run(
            ["node", "-e", script, str(REPO_ROOT)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            self.fail(proc.stderr or proc.stdout or "node selected conversation fast polling regression script failed")

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
