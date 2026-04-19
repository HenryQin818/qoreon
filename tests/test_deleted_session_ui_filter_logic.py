import shutil
import subprocess
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _node_extract_helper() -> str:
    return r"""
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
    """


@unittest.skipUnless(shutil.which("node"), "node is required for UI logic regression checks")
class DeletedSessionUiFilterLogicTests(unittest.TestCase):
    def run_node_assert(self, script: str) -> None:
        proc = subprocess.run(
            ["node", "-e", script, str(REPO_ROOT)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            self.fail(proc.stderr or proc.stdout or "node regression script failed")

    def test_merge_conversation_sessions_drops_deleted_rows(self) -> None:
        script = textwrap.dedent(
            rf"""
            const assert = require("node:assert/strict");
            const fs = require("node:fs");
            const path = require("node:path");
            const repoRoot = process.argv[1];
            {_node_extract_helper()}

            global.boolLike = (value) => {{
              if (typeof value === "boolean") return value;
              const text = String(value == null ? "" : value).trim().toLowerCase();
              return text === "1" || text === "true" || text === "yes" || text === "y";
            }};
            global.normalizeConversationSession = (raw) => {{
              if (!raw || typeof raw !== "object") return null;
              const sid = String(raw.sessionId || raw.id || raw.session_id || "").trim();
              if (!sid) return null;
              const channel = String(raw.channel_name || raw.primaryChannel || "").trim();
              const channels = Array.isArray(raw.channels) ? raw.channels.slice() : (channel ? [channel] : []);
              return Object.assign({{
                sessionId: sid,
                id: sid,
                channel_name: channel,
                primaryChannel: channel,
                channels,
                alias: "",
                displayChannel: channel,
                displayName: channel || sid,
                displayNameSource: "",
                agent_display_name: "",
                agentDisplayName: "",
                agent_display_name_source: "",
                agentDisplayNameSource: "",
                agent_name_state: "",
                agentNameState: "",
                agent_display_issue: "",
                agentDisplayIssue: "",
                codexTitle: "",
                cli_type: "codex",
                model: "",
                reasoning_effort: "",
                is_primary: false,
                is_deleted: false,
                deleted_at: "",
                deleted_reason: "",
                source: "",
                runtime_state: {{ display_state: "idle", internal_state: "idle", external_busy: false, active_run_id: "", queued_run_id: "", queue_depth: 0 }},
                session_display_state: "idle",
                session_display_reason: "",
                latest_run_summary: {{}},
                latest_effective_run_summary: {{}},
                lastError: "",
                lastSpeaker: "assistant",
                lastSenderType: "legacy",
                lastSenderName: "",
                lastSenderSource: "legacy",
                latestUserMsg: "",
                latestAiMsg: "",
                runCount: 0,
                lastActiveAt: "",
                lastPreview: "",
                last_used_at: "",
                heartbeat_summary: {{}},
                project_execution_context: null,
                team_expansion_hint: null,
                task_tracking: null,
                conversation_list_metrics: null,
                conversationListMetrics: null,
              }}, raw);
            }};
            global.normalizeRuntimeState = (value) => value || {{ display_state: "idle", internal_state: "idle", external_busy: false, active_run_id: "", queued_run_id: "", queue_depth: 0 }};
            global.buildProjectExecutionContextMeta = () => ({{ available: false }});
            global.hasConversationTeamExpansionHintData = () => false;
            global.hasConversationTaskTrackingData = () => false;
            global.mergeConversationListMetricsClient = (next) => next || null;
            global.firstNonEmptyText = (values) => {{
              for (const value of Array.isArray(values) ? values : []) {{
                const text = String(value || "").trim();
                if (text) return text;
              }}
              return "";
            }};
            global.normalizeDisplayState = (value, fallback = "idle") => String(value || fallback || "idle").trim() || "idle";
            global.resolveConversationSessionPresentation = (raw, channel, sid) => ({{
              displayChannel: String((raw && raw.displayChannel) || channel || sid || ""),
              displayName: String((raw && raw.displayName) || channel || sid || ""),
              displayNameSource: String((raw && raw.displayNameSource) || ""),
              agentDisplayName: String((raw && (raw.agent_display_name || raw.agentDisplayName)) || ""),
              agentDisplayNameSource: String((raw && (raw.agent_display_name_source || raw.agentDisplayNameSource)) || ""),
              agentNameState: String((raw && (raw.agent_name_state || raw.agentNameState)) || ""),
              agentDisplayIssue: String((raw && (raw.agent_display_issue || raw.agentDisplayIssue)) || ""),
            }});
            global.conversationShouldPreserveActiveSessionState = () => false;
            global.getSessionRuntimeState = (session) => session && session.runtime_state ? session.runtime_state : global.normalizeRuntimeState(null);
            global.getSessionDisplayState = (session) => String((session && session.session_display_state) || "idle");
            global.getSessionPrimaryPreviewText = () => "";
            global.conversationSessionStateSources = () => ({{ latest_run_summary: true, latest_effective_run_summary: true }});
            global.normalizeHeartbeatSummaryClient = (value) => value || {{}};

            eval(extractFunction("web/task_parts/74-session-bootstrap-and-sessions.js", "mergeConversationSessions"));

            const localMerged = mergeConversationSessions([
              {{ sessionId: "ses_active", channel_name: "A" }},
              {{ sessionId: "ses_deleted", channel_name: "A", is_deleted: true }},
              {{ sessionId: "ses_inactive", channel_name: "A", status: "inactive" }},
            ], []);
            assert.deepEqual(localMerged.map((item) => item.sessionId), ["ses_active"]);

            const deletedFromServer = mergeConversationSessions([
              {{ sessionId: "ses_active", channel_name: "A" }},
            ], [
              {{ sessionId: "ses_active", channel_name: "A", is_deleted: true }},
            ]);
            assert.equal(deletedFromServer.length, 0);

            const inactiveFromServer = mergeConversationSessions([
              {{ sessionId: "ses_active", channel_name: "A" }},
            ], [
              {{ sessionId: "ses_active", channel_name: "A", status: "inactive" }},
            ]);
            assert.equal(inactiveFromServer.length, 0);
            """
        )
        self.run_node_assert(script)

    def test_configured_project_conversations_skips_deleted_primary_entries(self) -> None:
        script = textwrap.dedent(
            rf"""
            const assert = require("node:assert/strict");
            const fs = require("node:fs");
            const path = require("node:path");
            const repoRoot = process.argv[1];
            {_node_extract_helper()}

            global.boolLike = (value) => {{
              if (typeof value === "boolean") return value;
              const text = String(value == null ? "" : value).trim().toLowerCase();
              return text === "1" || text === "true" || text === "yes" || text === "y";
            }};
            global.isDeletedSession = (session) => global.boolLike(session && (session.is_deleted || session.isDeleted));
            global.isInactiveSession = (session) => String((session && session.status) || "").trim().toLowerCase() === "inactive";
            global.isVisibleConversationSession = (session) => !global.isDeletedSession(session) && !global.isInactiveSession(session);
            global.looksLikeSessionId = (value) => /^ses_/i.test(String(value || "").trim()) || /^[0-9a-z_-]{{10,}}$/i.test(String(value || "").trim());
            global.normalizeSessionModel = (value) => String(value || "").trim();
            global.projectById = () => ({{
              channel_sessions: [
                {{
                  name: "辅助06-项目运维",
                  session_id: "ses_deleted_primary",
                  alias: "历史旧会话",
                  is_deleted: true,
                }},
                {{
                  name: "辅助06-项目运维",
                  session_id: "ses_inactive_primary",
                  alias: "历史旧会话2",
                  status: "inactive",
                }},
              ],
              channels: [
                {{ name: "辅助06-项目运维", alias: "", session_id: "" }},
              ],
            }});
            global.unionChannelNames = () => ["辅助06-项目运维"];
            global.sessionForChannel = () => null;

            eval(extractFunction("web/task_parts/76-runs-and-drawer.js", "configuredPrimarySessionEntry"));
            eval(extractFunction("web/task_parts/76-runs-and-drawer.js", "configuredProjectConversations"));

            const sessions = configuredProjectConversations("task_dashboard");
            assert.equal(sessions.length, 0);
            """
        )
        self.run_node_assert(script)

    def test_task_page_runtime_and_channel_fallback_ignore_deleted_sessions(self) -> None:
        script = textwrap.dedent(
            rf"""
            const assert = require("node:assert/strict");
            const fs = require("node:fs");
            const path = require("node:path");
            const repoRoot = process.argv[1];
            {_node_extract_helper()}

            global.PCONV = {{
              sessions: [
                {{
                  sessionId: "ses_deleted_runtime",
                  project_id: "task_dashboard",
                  channel_name: "辅助06-项目运维",
                  primaryChannel: "辅助06-项目运维",
                  channels: ["辅助06-项目运维"],
                  is_deleted: true,
                }},
                {{
                  sessionId: "ses_inactive_runtime",
                  project_id: "task_dashboard",
                  channel_name: "辅助06-项目运维",
                  primaryChannel: "辅助06-项目运维",
                  channels: ["辅助06-项目运维"],
                  status: "inactive",
                }},
              ],
            }};
            global.STATE = {{ project: "task_dashboard" }};
            global.looksLikeSessionId = (value) => /^ses_/i.test(String(value || "").trim()) || /^[0-9a-z_-]{{10,}}$/i.test(String(value || "").trim());
            global.normalizeSessionModel = (value) => String(value || "").trim();
            global.getBinding = () => null;
            global.projectById = () => ({{
              channel_sessions: [
                {{
                  name: "辅助06-项目运维",
                  session_id: "ses_deleted_row",
                  cli_type: "codex",
                  is_deleted: true,
                }},
                {{
                  name: "辅助06-项目运维",
                  session_id: "ses_inactive_row",
                  cli_type: "codex",
                  status: "inactive",
                }},
              ],
              channels: [
                {{
                  name: "辅助06-项目运维",
                  alias: "",
                  session_id: "",
                }},
              ],
            }});

            eval(extractFunction("web/task.js", "boolLike"));
            eval(extractFunction("web/task.js", "isDeletedSession"));
            eval(extractFunction("web/task.js", "isInactiveSession"));
            eval(extractFunction("web/task.js", "isVisibleConversationSession"));
            eval(extractFunction("web/task.js", "conversationRuntimeSessionsForProject"));
            eval(extractFunction("web/task.js", "sessionForChannel"));

            const runtimeSessions = conversationRuntimeSessionsForProject("task_dashboard");
            assert.equal(runtimeSessions.length, 0);

            const channelSession = sessionForChannel("task_dashboard", "辅助06-项目运维");
            assert.equal(channelSession.session_id, "");
            assert.equal(channelSession.source, "config");
            """
        )
        self.run_node_assert(script)


if __name__ == "__main__":
    unittest.main()
