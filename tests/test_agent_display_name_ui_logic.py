import shutil
import subprocess
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("node"), "node is required for UI logic regression checks")
class AgentDisplayNameUiLogicTests(unittest.TestCase):
    def test_final_agent_name_prefers_contract_and_blocks_sid_fallbacks(self) -> None:
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
                const text = String(value == null ? "" : value).trim();
                if (text) return text;
              }
              return "";
            };
            global.looksLikeSessionId = (value) => /^[0-9a-f]{8}-[0-9a-f-]{27}$/i.test(String(value || "").trim());
            global.getSessionId = (session) => String((session && (session.sessionId || session.id || session.session_id)) || "").trim();
            global.getSessionChannelName = (session) => String((session && (session.channel_name || session.primaryChannel || session.channelName)) || "").trim();

            const displayFile = "web/task_parts/55-session-display-state.js";
            for (const name of [
              "normalizeAgentNameState",
              "agentNameStateLabel",
              "compactAgentDisplayId",
              "isSessionDerivedAgentDisplayName",
              "hasAgentDisplayContractFields",
              "readAgentDisplayContract",
              "fallbackAgentIdentityName",
              "resolveAgentDisplayName",
            ]) {
              eval(extractFunction(displayFile, name));
            }
            eval(extractFunction("web/task_parts/74-session-bootstrap-and-sessions.js", "resolveConversationSessionPresentation"));
            eval(extractFunction("web/task_parts/60-conversation.js", "buildExplicitConversationSessionStub"));
            eval(extractFunction("web/task.js", "conversationAgentName"));
            eval(extractFunction("web/task.js", "agentDisplayTitle"));

            const sid = "019d75f8-a187-75d2-a118-c1a187ae2a76";
            const resolved = {
              sessionId: sid,
              displayName: "会话 a18775",
              displayNameSource: "legacy",
              agent_display_name: "项目运维-异常修复",
              agent_display_name_source: "alias",
              agent_name_state: "resolved",
              agent_display_issue: "none",
            };
            assert.equal(resolveAgentDisplayName(resolved), "项目运维-异常修复");
            assert.equal(conversationAgentName(resolved), "项目运维-异常修复");
            assert.equal(agentDisplayTitle(resolved, "-"), "项目运维-异常修复");

            const polluted = {
              sessionId: sid,
              alias: "会话 a18775",
              displayName: "会话 a18775",
              agent_name_state: "polluted",
              agent_display_issue: "polluted_short_id",
            };
            assert.equal(conversationAgentName(polluted), "名称异常");
            assert.doesNotMatch(conversationAgentName(polluted), /会话\s+[0-9a-f]{6,}/i);

            const legacy = {
              sessionId: sid,
              alias: "会话 a18775",
              displayName: "会话 a18775",
              displayNameSource: "explicit_sid_fallback",
              channel_name: "辅助06-项目运维（运行巡检-异常告警-会话修复）",
            };
            assert.equal(conversationAgentName(legacy), "身份未解析");
            assert.equal(agentDisplayTitle(legacy, "-"), "身份未解析");

            const registryOnly = {
              sessionId: sid,
              channel_name: "辅助06-项目运维（运行巡检-异常告警-会话修复）",
              agent_registry: { alias: "项目运维-问题诊断和处理" },
            };
            assert.equal(conversationAgentName(registryOnly), "项目运维-问题诊断和处理");

            const presentation = resolveConversationSessionPresentation(resolved, "", sid);
            assert.equal(presentation.agentDisplayName, "项目运维-异常修复");
            assert.equal(presentation.displayName, "项目运维-异常修复");
            assert.equal(presentation.agentNameState, "resolved");

            const legacyPresentation = resolveConversationSessionPresentation(legacy, legacy.channel_name, sid);
            assert.equal(legacyPresentation.displayName, "");
            assert.equal(legacyPresentation.displayNameSource, "");

            const explicitOnly = buildExplicitConversationSessionStub("task_dashboard", "", sid);
            assert.equal(explicitOnly.displayName, "会话 019d75f8");
            assert.equal(conversationAgentName(explicitOnly), "身份解析中");
            assert.doesNotMatch(conversationAgentName(explicitOnly), /会话\s+[0-9a-f]{6,}/i);

            const explicitWithChannel = buildExplicitConversationSessionStub("task_dashboard", "子级04-前端体验（task-overview 页面交互）", sid);
            assert.equal(conversationAgentName(explicitWithChannel), "身份解析中");
            """
        )
        proc = subprocess.run(
            ["node", "-e", script, str(REPO_ROOT)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            self.fail(proc.stderr or proc.stdout or "node agent display-name UI regression script failed")

    def test_mention_target_normalization_uses_identity_contract_or_abnormal_state(self) -> None:
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
                const text = String(value == null ? "" : value).trim();
                if (text) return text;
              }
              return "";
            };
            global.looksLikeSessionId = (value) => /^[0-9a-f]{8}-[0-9a-f-]{27}$/i.test(String(value || "").trim());
            global.getSessionId = (session) => String((session && (session.sessionId || session.id || session.session_id)) || "").trim();
            global.getSessionChannelName = (session) => String((session && (session.channel_name || session.primaryChannel || session.channelName)) || "").trim();

            const displayFile = "web/task_parts/55-session-display-state.js";
            for (const name of [
              "normalizeAgentNameState",
              "agentNameStateLabel",
              "compactAgentDisplayId",
              "isSessionDerivedAgentDisplayName",
            ]) {
              eval(extractFunction(displayFile, name));
            }

            eval(extractFunction("web/task_parts/79-panel-wire-upload.js", "normalizeMentionTargetItem"));
            eval(extractFunction("web/task_parts/75-conversation-composer.js", "mentionBaseLabel"));
            eval(extractFunction("web/task_parts/75-conversation-composer.js", "mentionInsertLabel"));

            const resolved = normalizeMentionTargetItem({
              channel_name: "辅助06-项目运维（运行巡检-异常告警-会话修复）",
              session_id: "019d75f8-a187-75d2-a118-c1a187ae2a76",
              agent_display_name: "项目运维-问题诊断和处理",
              agent_name_state: "resolved",
            });
            assert.equal(resolved.display_name, "项目运维-问题诊断和处理");
            assert.equal(mentionInsertLabel(resolved), "项目运维-问题诊断和处理");

            const unresolved = normalizeMentionTargetItem({
              channel_name: "辅助06-项目运维（运行巡检-异常告警-会话修复）",
              session_id: "019d75f8-a187-75d2-a118-c1a187ae2a76",
              display_name: "辅助06-项目运维（运行巡检-异常告警-会话修复）",
              agent_name_state: "identity_unresolved",
            });
            assert.equal(unresolved.display_name, "身份未解析");
            assert.equal(mentionInsertLabel(unresolved), "身份未解析");

            const polluted = normalizeMentionTargetItem({
              channel_name: "辅助06-项目运维（运行巡检-异常告警-会话修复）",
              session_id: "019d75f8-a187-75d2-a118-c1a187ae2a76",
              display_name: "会话 a18775",
              agent_display_issue: "polluted_short_id",
            });
            assert.equal(polluted.display_name, "名称异常");
            assert.equal(mentionInsertLabel(polluted), "名称异常");
          """
        )
        proc = subprocess.run(
            ["node", "-e", script, str(REPO_ROOT)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            self.fail(proc.stderr or proc.stdout or "node mention target display-name regression script failed")


if __name__ == "__main__":
    unittest.main()
