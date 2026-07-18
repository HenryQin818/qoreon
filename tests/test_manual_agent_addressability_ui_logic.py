import shutil
import subprocess
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("node"), "node is required for UI logic regression checks")
class ManualAgentAddressabilityUiLogicTests(unittest.TestCase):
    def test_alias_field_is_required_in_create_modal(self) -> None:
        template = (REPO_ROOT / "web/task.html.tpl").read_text(encoding="utf-8")
        self.assertIn('id="newConvAlias"', template)
        self.assertIn("newConvAlias", template)
        self.assertIn("required", template)
        self.assertIn("用于 Agent 通讯录按名寻址", template)

    def test_session_info_rename_uses_alias_validation_and_refresh_copy(self) -> None:
        script = (REPO_ROOT / "web/task_entry_parts/81-session-info-and-bindings.js").read_text(encoding="utf-8")
        self.assertIn("manualAgentAliasValidationMessage", script)
        self.assertIn("对话agent名称（alias，必填）", script)
        self.assertIn("SessionStore 身份真源", script)
        self.assertIn("PCONV.sessionDirectoryByProject", script)
        self.assertIn("联系人名和左侧列表已按 SessionStore 可读名刷新", script)

    def test_manual_agent_alias_validation_and_error_explainer(self) -> None:
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

            const file = "web/task_parts/74-session-bootstrap-and-sessions.js";
            global.firstNonEmptyText = (items, fallback = "") => {
              for (const item of items || []) {
                const value = String(item || "").trim();
                if (value) return value;
              }
              return fallback;
            };
            global.shortId = (value) => String(value || "").slice(0, 8);
            global.isVisibleConversationSession = (row) => String(row.status || "").toLowerCase() !== "archived";
            global.getSessionChannelName = (row) => row.channel_name || row.channelName || "";
            global.PCONV = {
              sessions: [
                {
                  sessionId: "sid-conflict-123456",
                  alias: "前端-Agent",
                  channel_name: "子级04-前端体验",
                  status: "active",
                },
                {
                  sessionId: "sid-archived-123456",
                  alias: "归档-Agent",
                  channel_name: "旧通道",
                  status: "archived",
                },
              ],
            };
            global.conversationSessionsForProject = () => global.PCONV.sessions;

            [
              "normalizeManualAgentReadableAlias",
              "manualAgentSessionId",
              "manualAgentReadableName",
              "manualAgentSessionOccupiesReadableName",
              "manualAgentConflictChannel",
              "findManualAgentAliasConflict",
              "manualAgentConflictLabel",
              "manualAgentAliasValidationMessage",
              "collectManualAgentErrorCodes",
              "manualAgentRawErrorText",
              "extractManualAgentConflict",
              "normalizeManualAgentAddressabilityError",
            ].forEach((name) => {
              globalThis[name] = eval("(" + extractFunction(file, name) + ")");
            });

            const empty = globalThis.manualAgentAliasValidationMessage("task_dashboard", "  ");
            assert.match(empty, /Agent 可读名（alias）不能为空/);
            assert.match(empty, /怎么修/);

            const conflict = globalThis.manualAgentAliasValidationMessage("task_dashboard", "前端-Agent");
            assert.match(conflict, /Agent 可读名冲突/);
            assert.match(conflict, /子级04-前端体验/);
            assert.match(conflict, /sid-conf/);
            assert.match(conflict, /设为非 active\/归档/);

            const ignored = globalThis.manualAgentAliasValidationMessage("task_dashboard", "前端-Agent", "sid-conflict-123456");
            assert.equal(ignored, "");

            const ambiguous = globalThis.normalizeManualAgentAddressabilityError({
              detail: {
                code: "agent_ambiguous",
                message: "multiple active sessions",
              },
            });
            assert.match(ambiguous, /Agent 寻址存在歧义/);
            assert.match(ambiguous, /设置唯一 primary/);
            assert.match(ambiguous, /归档或停用冗余 active 会话/);
            assert.match(ambiguous, /真实错误：multiple active sessions/);

            const degraded = globalThis.normalizeManualAgentAddressabilityError({
              error_code: "degraded_runtime_index",
              message: "registry refresh failed",
            });
            assert.match(degraded, /通讯录\/CCR 同步降级/);
            assert.match(degraded, /重建通讯录\/运行时索引/);
            assert.match(degraded, /真实错误：registry refresh failed/);
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

    def test_create_conversation_blocks_empty_alias_before_request(self) -> None:
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

            const dom = {
              newConvProject: { value: "task_dashboard" },
              newConvChannel: { value: "子级04-前端体验（task-overview 页面交互）" },
              newConvCliType: { value: "codex" },
              newConvCreateBtn: { textContent: "创建并绑定", disabled: false },
              newConvSessionId: { value: "" },
              newConvModel: { value: "gpt-5.3-codex" },
              newConvPurpose: { value: "前端实现" },
              newConvAlias: { value: "  " },
              newConvSessionRole: { value: "child" },
              newConvReuseStrategy: { value: "create_new" },
              newConvEnvironment: { value: "stable" },
              newConvWorktreeRoot: { value: "/tmp/task-dashboard" },
              newConvWorkdir: { value: "/tmp/task-dashboard" },
              newConvBranch: { value: "main" },
              newConvInitMessage: { value: "" },
            };

            global.document = {
              getElementById(id) {
                return Object.prototype.hasOwnProperty.call(dom, id) ? dom[id] : null;
              },
            };
            global.NEW_CONV_UI = { mode: "create" };
            global.STATE = { panelMode: "conversation" };
            global.normalizeNewConvMode = (value) => String(value || "").trim() || "create";
            global.normalizeSessionModel = (value) => String(value || "").trim();
            global.isCodexCliType = (value) => String(value || "").trim().toLowerCase() === "codex";
            global.normalizeReasoningEffort = (value) => String(value || "").trim();
            global.normalizeSessionEnvironmentValue = (value) => String(value || "stable").trim() || "stable";

            let errorText = "";
            global.newConvModalError = (value) => { errorText = String(value || ""); };
            let requestCount = 0;
            global.postSessionCreateWithChannelRetry = async () => {
              requestCount += 1;
              throw new Error("should not request");
            };

            eval(extractFunction("web/task_parts/74-session-bootstrap-and-sessions.js", "createNewConversation"));

            (async () => {
              await createNewConversation();
              assert.match(errorText, /Agent 可读名（alias）不能为空/);
              assert.equal(requestCount, 0);
            })().catch((err) => {
              console.error(err);
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
            self.fail(proc.stderr or proc.stdout or "node regression script failed")


if __name__ == "__main__":
    unittest.main()
