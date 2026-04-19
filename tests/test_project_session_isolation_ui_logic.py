import shutil
import subprocess
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("node"), "node is required for UI logic regression checks")
class ProjectSessionIsolationUiLogicTests(unittest.TestCase):
    def test_cross_project_runtime_cache_is_not_used_for_new_project_fallback(self) -> None:
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

            global.PCONV = {
              lastProjectId: "new_project",
              sessions: [
                {
                  sessionId: "019d7000-0000-7000-8000-000000000001",
                  project_id: "other_project",
                  channel_name: "辅助06-项目运维",
                  primaryChannel: "辅助06-项目运维",
                  channels: ["辅助06-项目运维"],
                },
              ],
              sessionDirectoryByProject: Object.create(null),
              sessionDirectoryMetaByProject: Object.create(null),
            };
            global.STATE = { project: "new_project" };
            global.looksLikeSessionId = (value) => /^[0-9a-z_-]{10,}$/i.test(String(value || "").trim());
            global.normalizeSessionModel = (value) => String(value || "").trim();
            global.getBinding = () => null;
            global.projectById = (id) => {
              if (String(id || "") !== "new_project") return null;
              return {
                id: "new_project",
                channels: [{ name: "辅助06-项目运维", alias: "", session_id: "" }],
                channel_sessions: [],
              };
            };
            global.itemsForProject = () => [];
            global.isDeletedSession = () => false;
            global.conversationPendingCreateSessionsForProject = () => [];
            global.configuredProjectConversations = (pid) => [{
              sessionId: "019d7000-0000-7000-8000-000000000099",
              id: "019d7000-0000-7000-8000-000000000099",
              project_id: String(pid || ""),
              projectId: String(pid || ""),
              channel_name: "辅助06-项目运维",
              primaryChannel: "辅助06-项目运维",
              channels: ["辅助06-项目运维"],
            }];

            eval(extractFunction("web/task.js", "conversationRuntimeSessionsForProject"));
            eval(extractFunction("web/task.js", "sessionForChannel"));
            eval(extractFunction("web/task.js", "conversationSessionsForProject"));

            const scoped = conversationRuntimeSessionsForProject("new_project");
            assert.equal(scoped.length, 0);

            const channelSession = sessionForChannel("new_project", "辅助06-项目运维");
            assert.equal(channelSession.session_id, "");
            assert.equal(channelSession.project_id, "new_project");
            assert.equal(channelSession.projectId, "new_project");

            const sessions = conversationSessionsForProject("new_project");
            assert.equal(sessions.length, 1);
            assert.equal(sessions[0].sessionId, "019d7000-0000-7000-8000-000000000099");
            assert.equal(sessions[0].project_id, "new_project");
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

    def test_normalize_conversation_session_keeps_project_identity(self) -> None:
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

            global.STATE = { project: "new_project" };
            global.looksLikeSessionId = (value) => /^[0-9a-z_-]{10,}$/i.test(String(value || "").trim());
            global.resolveConversationSessionPresentation = (_raw, channelName, sid) => ({
              alias: channelName || sid,
              displayChannel: channelName || sid,
              displayName: channelName || sid,
              displayNameSource: channelName ? "channel" : "session",
            });
            global.normalizeHeartbeatTaskItemsClient = () => [];
            global.normalizeHeartbeatSummaryClient = (_summary, items) => ({ items });
            global.normalizeConversationTeamExpansionHint = () => null;
            global.normalizeSessionEnvironmentValue = (value) => String(value || "stable").trim() || "stable";
            global.normalizeSessionModel = (value) => String(value || "").trim();
            global.normalizeReasoningEffort = (value) => String(value || "").trim();
            global.boolLike = (value) => !!value;
            global.firstNonEmptyText = (values) => {
              const list = Array.isArray(values) ? values : [values];
              for (const value of list) {
                const text = String(value || "").trim();
                if (text) return text;
              }
              return "";
            };
            global.normalizeLatestEffectiveRunSummary = (value) => value || { preview: "" };
            global.normalizeLatestRunSummary = (value) => value || { preview: "" };
            global.normalizeDisplayState = (value, fallback = "idle") => String(value || fallback || "").trim() || String(fallback || "").trim();
            global.normalizeRuntimeState = (value) => value || {};
            global.normalizeProjectExecutionContext = (value) => value || null;
            global.normalizeTaskTrackingClient = (value) => value || null;

            eval(extractFunction("web/task_parts/74-session-bootstrap-and-sessions.js", "normalizeConversationSession"));

            const session = normalizeConversationSession({
              sessionId: "019d7000-0000-7000-8000-000000000123",
              project_id: "new_project",
              channel_name: "辅助06-项目运维",
            });
            assert.equal(session.project_id, "new_project");
            assert.equal(session.projectId, "new_project");
            assert.equal(session.channel_name, "辅助06-项目运维");
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
