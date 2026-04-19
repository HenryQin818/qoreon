import shutil
import subprocess
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("node"), "node is required for UI logic regression checks")
class ConversationSendEchoUiLogicTests(unittest.TestCase):
    def test_mark_session_pending_promotes_runtime_state_and_latest_user_msg(self) -> None:
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
              sessions: [{
                id: "sid-1",
                project_id: "task_dashboard",
                latest_run_summary: { status: "done" },
                runtime_state: { display_state: "idle", queue_depth: 0 },
              }],
            };
            global.getSessionId = (row) => String((row && (row.sessionId || row.id)) || "").trim();
            let upsertPayload = null;
            let upsertMeta = null;
            global.conversationStoreUpsertSession = (row, meta) => {
              upsertPayload = JSON.parse(JSON.stringify(row));
              upsertMeta = meta;
            };

            eval(extractFunction("web/task.js", "markSessionPending"));

            markSessionPending("sid-1", "当前消息待回执");

            const row = global.PCONV.sessions[0];
            assert.equal(row.session_display_state, "queued");
            assert.equal(row.runtime_state.display_state, "queued");
            assert.equal(row.runtime_state.queue_depth, 1);
            assert.equal(row.latestUserMsg, "当前消息待回执");
            assert.equal(row.latest_run_summary.status, "queued");
            assert.equal(row.latest_run_summary.latest_user_msg, "当前消息待回执");
            assert.equal(upsertPayload.latestUserMsg, "当前消息待回执");
            assert.equal(upsertMeta.source, "local-pending");
          """
        )
        proc = subprocess.run(
            ["node", "-e", script, str(REPO_ROOT)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            self.fail(proc.stderr or proc.stdout or "node markSessionPending regression script failed")

    def test_inject_ack_run_to_timeline_materializes_local_preview(self) -> None:
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
              sessionTimelineMap: Object.create(null),
              runsBySession: Object.create(null),
            };
            global.firstNonEmptyText = (values, fallback = "") => {
              for (const value of values || []) {
                const text = String(value || "").trim();
                if (text) return text;
              }
              return fallback;
            };
            global.normalizeDisplayState = (value, fallback = "idle") => {
              const text = String(value || "").trim().toLowerCase();
              if (["running", "queued", "retry_waiting", "done", "error", "idle", "external_busy"].includes(text)) return text;
              return String(fallback || "idle").trim().toLowerCase() || "idle";
            };
            global.conversationStoreNowIso = () => "2026-04-12T14:10:00+0800";
            global.mergeRunsById = (existingRuns, incomingRuns) => {
              const map = new Map();
              for (const run of existingRuns || []) map.set(String(run.id || ""), { ...run });
              for (const run of incomingRuns || []) {
                const key = String(run.id || "");
                map.set(key, { ...(map.get(key) || {}), ...run });
              }
              return Array.from(map.values());
            };
            let upsertRun = null;
            global.conversationStoreUpsertRun = (_projectId, _sessionId, run, meta) => {
              upsertRun = { run: JSON.parse(JSON.stringify(run)), meta };
            };

            eval(extractFunction("web/task_parts/75-conversation-composer.js", "injectConversationAckRunToTimeline"));

            const injected = injectConversationAckRunToTimeline(
              {
                projectId: "task_dashboard",
                sessionId: "sid-1",
                channelName: "子级04",
                cliType: "codex",
              },
              {
                clientMessageId: "cmid-1",
                message: "请继续处理当前问题",
                attachments: [{ localId: "att-1", originalName: "a.png", url: "/tmp/a.png" }],
                createdAt: "2026-04-12T14:09:00+0800",
              },
              {
                run: {
                  id: "run-1",
                  status: "queued",
                },
              },
              { source: "composer-send" }
            );

            assert.equal(injected.id, "run-1");
            assert.equal(injected.messagePreview, "请继续处理当前问题");
            assert.equal(injected.client_message_id, "cmid-1");
            assert.equal(global.PCONV.sessionTimelineMap["task_dashboard::sid-1"][0].id, "run-1");
            assert.equal(global.PCONV.runsBySession["sid-1"][0].messagePreview, "请继续处理当前问题");
            assert.equal(upsertRun.run.id, "run-1");
            assert.equal(upsertRun.meta.source, "composer-send");
          """
        )
        proc = subprocess.run(
            ["node", "-e", script, str(REPO_ROOT)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            self.fail(proc.stderr or proc.stdout or "node injectConversationAckRunToTimeline regression script failed")

    def test_receipt_anchor_accepts_related_working_source_run(self) -> None:
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

            global.firstNonEmptyText = (values, fallback = "") => {
              for (const value of values || []) {
                const text = String(value || "").trim();
                if (text) return text;
              }
              return fallback;
            };
            global.collectConversationReceiptHostRunIds = () => [];
            global.readConversationTimelineAnchorInfo = (run) => ({
              senderType: String(run.senderType || "").trim(),
              triggerType: String(run.triggerType || "").trim(),
              messageKind: String(run.messageKind || "").trim(),
              sourceChannel: String(run.sourceChannel || "").trim(),
              sourceSessionId: String(run.sourceSessionId || "").trim(),
              targetSessionId: String(run.targetSessionId || "").trim(),
            });
            global.getRunDisplayState = (run) => String((run && run.status) || "").trim().toLowerCase();
            global.isRunWorking = (value) => ["running", "queued", "retry_waiting", "external_busy"].includes(String(value || "").trim().toLowerCase());

            eval(extractFunction("web/task_parts/60-conversation.js", "resolveConversationLocalReceiptAnchorRunId"));

            const anchorRunId = resolveConversationLocalReceiptAnchorRunId({
              callbackRunId: "callback-1",
              currentSessionId: "sid-1",
              callbackEventMeta: {
                sourceRunId: "run-src",
                comm: { sourceChannel: "辅助06" },
              },
              runs: [
                {
                  id: "run-old",
                  status: "done",
                  senderType: "agent",
                  sourceChannel: "辅助06",
                },
                {
                  id: "run-src",
                  status: "running",
                  senderType: "agent",
                  sourceChannel: "辅助06",
                  targetSessionId: "sid-1",
                },
                {
                  id: "callback-1",
                  status: "done",
                  senderType: "system",
                  messageKind: "system_callback",
                },
              ],
            });

            assert.equal(anchorRunId, "run-src");
          """
        )
        proc = subprocess.run(
            ["node", "-e", script, str(REPO_ROOT)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            self.fail(proc.stderr or proc.stdout or "node resolveConversationLocalReceiptAnchorRunId regression script failed")


if __name__ == "__main__":
    unittest.main()
