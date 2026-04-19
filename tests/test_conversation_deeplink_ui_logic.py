import shutil
import subprocess
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("node"), "node is required for UI logic regression checks")
class ConversationDeepLinkUiLogicTests(unittest.TestCase):
    def test_session_detail_can_seed_restart_recovery_timeline_fallback(self) -> None:
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

            global.firstNonEmptyText = (values) => {
              for (const value of values || []) {
                const text = String(value || "").trim();
                if (text) return text;
              }
              return "";
            };
            global.normalizeDisplayState = (value, fallback = "") => {
              const text = String(value || "").trim().toLowerCase();
              if (text === "queued" || text === "running" || text === "retry_waiting" || text === "external_busy" || text === "done" || text === "error" || text === "interrupted" || text === "idle") return text;
              return String(fallback || "").trim().toLowerCase();
            };
            global.normalizeSessionDisplayState = global.normalizeDisplayState;
            global.normalizeRunOutcomeState = (value, fallback = "") => {
              const text = String(value || "").trim().toLowerCase();
              if (text === "success" || text === "interrupted_infra" || text === "interrupted_user" || text === "failed_config" || text === "failed_business" || text === "recovered_notice") return text;
              return String(fallback || "").trim().toLowerCase();
            };
            global.toTimeNum = (value) => {
              const text = String(value || "").trim();
              if (!text) return -1;
              const num = Date.parse(text.replace(/([+-]\d{2})(\d{2})$/, "$1:$2"));
              return Number.isFinite(num) ? num : -1;
            };

            eval(extractFunction("web/task_parts/55-session-display-state.js", "normalizeLatestRunSummary"));
            eval(extractFunction("web/task_parts/55-session-display-state.js", "normalizeLatestEffectiveRunSummary"));
            eval(extractFunction("web/task_parts/55-session-display-state.js", "getSessionLatestRunSummary"));
            eval(extractFunction("web/task_parts/55-session-display-state.js", "getSessionLatestEffectiveRunSummary"));
            eval(extractFunction("web/task_parts/60-conversation.js", "conversationSyntheticRunStatusFromOutcomeState"));
            eval(extractFunction("web/task_parts/60-conversation.js", "conversationSyntheticRunStatusFromAction"));
            eval(extractFunction("web/task_parts/60-conversation.js", "buildConversationSyntheticTimelineRunsFromSessionDetail"));

            const session = {
              cli_type: "codex",
              channel_name: "子级04-前端体验（task-overview 页面交互）",
              latest_run_summary: {
                run_id: "20260407-222025-21734b35",
                status: "done",
                updated_at: "2026-04-07T22:23:26+0800",
                preview: "恢复消息最终正文",
                latest_user_msg: "服务重启后，系统已自动恢复此前被打断的执行。",
                latest_ai_msg: "恢复消息最终正文",
              },
              latest_effective_run_summary: {
                run_id: "20260407-221458-a6f36e1c",
                outcome_state: "success",
                preview: "后续普通消息正文",
                created_at: "2026-04-07T22:12:57+0800",
              },
              task_tracking: {
                updated_at: "2026-04-07T22:23:26+0800",
                recent_task_actions: [
                  {
                    action_kind: "block",
                    action_text: "源消息正文",
                    status: "error",
                    source_run_id: "20260407-221457-671b9cc4",
                    source_channel: "子级04-前端体验（task-overview 页面交互）",
                    source_agent_name: "前端页面-对话管理",
                    at: "2026-04-07T22:16:30+0800",
                  },
                  {
                    action_kind: "update",
                    action_text: "恢复消息最终正文",
                    status: "done",
                    source_run_id: "20260407-222025-21734b35",
                    source_channel: "子级04-前端体验（task-overview 页面交互）",
                    source_agent_name: "系统",
                    at: "2026-04-07T22:23:26+0800",
                  },
                  {
                    action_kind: "update",
                    action_text: "后续普通消息正文",
                    status: "done",
                    source_run_id: "20260407-221458-a6f36e1c",
                    source_channel: "子级04-前端体验（task-overview 页面交互）",
                    source_agent_name: "前端页面-对话管理",
                    at: "2026-04-07T22:13:17+0800",
                  },
                ],
              },
            };

            const runs = buildConversationSyntheticTimelineRunsFromSessionDetail(session, {
              channelName: "子级04-前端体验（task-overview 页面交互）",
              cliType: "codex",
            });

            assert.deepEqual(runs.map((row) => row.id), [
              "20260407-221457-671b9cc4",
              "20260407-222025-21734b35",
              "20260407-221458-a6f36e1c",
            ]);
            const recovery = runs.find((row) => row.id === "20260407-222025-21734b35");
            assert.ok(recovery);
            assert.equal(recovery.trigger_type, "restart_recovery_summary");
            assert.deepEqual(recovery.restartRecoverySourceRunIds, ["20260407-221457-671b9cc4"]);
            assert.equal(recovery.lastPreview, "恢复消息最终正文");
            """
        )
        proc = subprocess.run(
            ["node", "-e", script, str(REPO_ROOT)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            self.fail(proc.stderr or proc.stdout or "node synthetic timeline regression script failed")

    def test_explicit_sid_defers_left_task_count_warmup_until_timeline_ready(self) -> None:
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

            eval(extractFunction("web/task.js", "shouldDeferConversationTaskCountWarmup"));

            global.looksLikeSessionId = (value) => /^[0-9a-f-]{8,}$/i.test(String(value || "").trim());
            global.getSessionId = (session) => String((session && (session.sessionId || session.id || session.session_id)) || "").trim();

            global.STATE = {
              project: "task_dashboard",
              panelMode: "conv",
              selectedSessionId: "019d684a-cbb6-7eb3-b95b-7ec9c30ecfd3",
              selectedSessionExplicit: true,
            };
            global.PCONV = {
              sessionDirectoryMetaByProject: {
                task_dashboard: { liveLoaded: true },
              },
              sessionTimelineMap: Object.create(null),
              timelineLoadingKey: "",
            };

            const sessions = [{
              sessionId: "019d684a-cbb6-7eb3-b95b-7ec9c30ecfd3",
              source: "live",
            }];

            assert.equal(shouldDeferConversationTaskCountWarmup("task_dashboard", sessions), true);

            PCONV.timelineLoadingKey = "task_dashboard::019d684a-cbb6-7eb3-b95b-7ec9c30ecfd3";
            assert.equal(shouldDeferConversationTaskCountWarmup("task_dashboard", sessions), true);

            PCONV.timelineLoadingKey = "";
            PCONV.sessionTimelineMap["task_dashboard::019d684a-cbb6-7eb3-b95b-7ec9c30ecfd3"] = [];
            assert.equal(shouldDeferConversationTaskCountWarmup("task_dashboard", sessions), false);
            """
        )
        proc = subprocess.run(
            ["node", "-e", script, str(REPO_ROOT)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            self.fail(proc.stderr or proc.stdout or "node regression script failed")

    def test_explicit_sid_survives_initial_fallback_and_context_lookup(self) -> None:
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

            eval(extractFunction("web/task_parts/60-conversation.js", "resolvePreferredConversationSelection"));
            eval(extractFunction("web/task_parts/76-runs-and-drawer.js", "currentConversationCtx"));

            global.pickDefaultConversationSessionId = (sessions) => String(((sessions || [])[0] || {}).sessionId || "");

            const selected = resolvePreferredConversationSelection(
              [
                { sessionId: "remembered-1" },
                { sessionId: "default-1" },
              ],
              [{ sessionId: "default-1" }],
              "explicit-hash-1",
              true,
              "remembered-1",
              "子级04-前端体验（task-overview 页面交互）",
            );
            assert.equal(selected.sessionId, "explicit-hash-1");
            assert.equal(selected.explicit, true);
            assert.equal(selected.rememberSelection, false);

            global.STATE = {
              project: "task_dashboard",
              panelMode: "conv",
              channel: "子级04-前端体验（task-overview 页面交互）",
              selectedSessionId: "explicit-hash-1",
              selectedSessionExplicit: true,
            };
            global.PCONV = {
              sessionDirectoryByProject: {
                task_dashboard: [
                  {
                    sessionId: "explicit-hash-1",
                    alias: "重启恢复验收样本",
                    channel_name: "子级04-前端体验（task-overview 页面交互）",
                    primaryChannel: "子级04-前端体验（task-overview 页面交互）",
                    cli_type: "codex",
                  },
                  {
                    sessionId: "remembered-1",
                    alias: "旧记忆会话",
                    channel_name: "子级04-前端体验（task-overview 页面交互）",
                    primaryChannel: "子级04-前端体验（task-overview 页面交互）",
                    cli_type: "codex",
                  },
                ],
              },
            };
            global.findConversationSessionById = () => null;
            global.readRememberedConversationSelection = () => "remembered-1";
            global.mergeConversationSessions = (a, b) => [].concat(a || [], b || []);
            global.configuredProjectConversations = () => [];
            global.firstNonEmptyText = (values) => {
              for (const value of values || []) {
                const text = String(value || "").trim();
                if (text) return text;
              }
              return "";
            };
            global.sessionMatchesChannel = (session, channelName) => String((session && (session.channel_name || session.primaryChannel)) || "") === String(channelName || "");
            global.getSessionChannelName = (session) => String((session && (session.channel_name || session.primaryChannel)) || "");
            global.conversationAgentName = (session) => String((session && session.alias) || "");

            const ctx = currentConversationCtx();
            assert.ok(ctx);
            assert.equal(ctx.sessionId, "explicit-hash-1");
            assert.equal(ctx.alias, "重启恢复验收样本");
            assert.equal(ctx.channelName, "子级04-前端体验（task-overview 页面交互）");
            """
        )
        proc = subprocess.run(
            ["node", "-e", script, str(REPO_ROOT)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            self.fail(proc.stderr or proc.stdout or "node regression script failed")

    def test_explicit_sid_fallback_label_does_not_override_channel_name(self) -> None:
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

            global.looksLikeSessionId = (value) => /^[0-9a-f-]{8,}$/i.test(String(value || "").trim());
            global.firstNonEmptyText = (values) => {
              for (const value of values || []) {
                const text = String(value || "").trim();
                if (text) return text;
              }
              return "";
            };
            global.getSessionId = (session) => String((session && (session.sessionId || session.id || session.session_id)) || "").trim();
            global.getSessionChannelName = (session) => String((session && (session.channel_name || session.primaryChannel || session.channelName)) || "").trim();

            eval(extractFunction("web/task_parts/60-conversation.js", "buildExplicitConversationSessionStub"));
            eval(extractFunction("web/task.js", "conversationAgentName"));

            const sid = "019d76d7-279b-76f0-8829-8cdb4183b227";
            const stub = buildExplicitConversationSessionStub("ndt", "", sid);
            assert.equal(stub.alias, "");
            assert.equal(stub.displayName, "会话 019d76d7");
            assert.equal(stub.displayNameSource, "explicit_sid_fallback");

            const channelStub = buildExplicitConversationSessionStub("ndt", "主体03-视觉主题与展示规范", sid);
            assert.equal(channelStub.alias, "");
            assert.equal(channelStub.displayName, "主体03-视觉主题与展示规范");
            assert.equal(channelStub.displayNameSource, "channel_name");

            const mergedLike = {
              sessionId: sid,
              alias: "会话 019d76d7",
              displayName: "会话 019d76d7",
              displayNameSource: "explicit_sid_fallback",
              displayChannel: "会话 019d76d7",
              channel_name: "主体03-视觉主题与展示规范",
            };
            assert.equal(conversationAgentName(mergedLike), "主体03-视觉主题与展示规范");

            const mergeSource = fs.readFileSync(path.join(repoRoot, "web/task_parts/74-session-bootstrap-and-sessions.js"), "utf8");
            assert.match(mergeSource, /prevIsExplicitSidFallback/);
            assert.ok(mergeSource.includes('prevIsExplicitSidFallback ? "" : prev.alias'));
            """
        )
        proc = subprocess.run(
            ["node", "-e", script, str(REPO_ROOT)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            self.fail(proc.stderr or proc.stdout or "node regression script failed")


if __name__ == "__main__":
    unittest.main()
