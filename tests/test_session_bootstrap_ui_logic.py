import shutil
import subprocess
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("node"), "node is required for UI logic regression checks")
class SessionBootstrapUiLogicTests(unittest.TestCase):
    def test_timeout_recovered_create_auto_attaches_existing_session(self) -> None:
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
            const dom = {
              newConvProject: { value: "task_dashboard" },
              newConvChannel: { value: "辅助06-项目运维（运行巡检-异常告警-会话修复）" },
              newConvCliType: { value: "codex" },
              newConvCreateBtn: { textContent: "创建并绑定", disabled: false },
              newConvSessionId: { value: "" },
              newConvModel: { value: "gpt-5.3-codex" },
              newConvPurpose: { value: "启动验收" },
              newConvAlias: { value: "运维执行位" },
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
            global.NEW_CONV_UI = { mode: "create_new" };
            global.STATE = { panelMode: "conversation" };
            global.normalizeNewConvMode = (value) => String(value || "").trim() || "create_new";
            global.normalizeSessionModel = (value) => String(value || "").trim();
            global.isCodexCliType = (value) => String(value || "").trim().toLowerCase() === "codex";
            global.normalizeReasoningEffort = (value) => String(value || "").trim();
            global.normalizeSessionEnvironmentValue = (value) => String(value || "stable").trim() || "stable";
            global.looksLikeSessionId = (value) => /^[0-9a-z_-]{10,}$/i.test(String(value || "").trim());
            global.buildProjectExecutionContextMeta = () => ({ available: false, sourceMeta: { text: "" } });
            global.buildBootstrapVisibleMessages = () => ["a", "b"];
            global.tryUpdateSessionModel = async () => false;
            global.sendNewConversationInitMessage = async () => ({ ok: true });
            global.verifySessionBindingVisibility = async () => ({ ok: false, hardRefreshRequired: false });
            global.closeNewConvModal = () => {};
            global.refreshConversationPanel = async () => {};
            let selectedSessionId = "";
            global.setSelectedSessionId = (value) => { selectedSessionId = String(value || ""); };
            let hintText = "";
            global.setHintText = (_panel, value) => { hintText = String(value || ""); };
            global.render = () => {};
            let errorText = "";
            global.newConvModalError = (value) => { errorText = String(value || ""); };

            const bindingCalls = [];
            global.setBinding = async (projectId, channelName, sessionId, cliType) => {
              bindingCalls.push({ projectId, channelName, sessionId, cliType });
              return true;
            };

            const requests = [];
            const timeoutSessionId = "019d4c36-07a9-7aa0-9001-19a41ca74567";
            global.postSessionCreateWithChannelRetry = async (payload) => {
              requests.push(JSON.parse(JSON.stringify(payload)));
              if (requests.length === 1) {
                return {
                  resp: { ok: false },
                  json: {
                    error: "create session timeout",
                    detail: {
                      error: "create session timeout",
                      sessionId: timeoutSessionId,
                    },
                  },
                  retried: false,
                };
              }
              return {
                resp: { ok: true },
                json: {
                  session: {
                    id: timeoutSessionId,
                    cli_type: "codex",
                    project_execution_context: {
                      context_source: "project",
                      source: { environment: "stable" },
                    },
                  },
                  imported: true,
                },
                retried: false,
              };
            };

            eval(extractFunction(file, "buildExistingSessionAttachPayload"));
            eval(extractFunction(file, "recoverTimeoutCreatedSession"));
            eval(extractFunction(file, "createNewConversation"));

            (async () => {
              await createNewConversation();
              assert.equal(errorText, "");
              assert.equal(requests.length, 2);
              assert.equal(requests[0].mode || "", "");
              assert.equal(requests[1].mode, "attach_existing");
              assert.equal(requests[1].session_id, timeoutSessionId);
              assert.equal(requests[1].project_id, "task_dashboard");
              assert.equal(requests[1].channel_name, "辅助06-项目运维（运行巡检-异常告警-会话修复）");
              assert.equal(requests[1].reuse_strategy, "attach_existing");
              assert.equal(requests[1].environment, "stable");
              assert.equal(requests[1].worktree_root, "/tmp/task-dashboard");
              assert.equal(requests[1].workdir, "/tmp/task-dashboard");
              assert.equal(requests[1].branch, "main");
              assert.equal(bindingCalls.length, 1);
              assert.equal(bindingCalls[0].sessionId, timeoutSessionId);
              assert.equal(selectedSessionId, timeoutSessionId);
              assert.match(hintText, /timeout-recovered 补登记并绑定/);
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

    def test_new_conversation_init_message_is_optional(self) -> None:
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

            eval(extractFunction("web/task_entry_parts/81-session-info-and-bindings.js", "buildNewConvInitMessage"));
            eval(extractFunction("web/task_entry_parts/81-session-info-and-bindings.js", "syncNewConvInitMessage"));
            eval(extractFunction("web/task_entry_parts/81-session-info-and-bindings.js", "selectedNewConvModelValue"));
            eval(extractFunction("web/task_parts/74-session-bootstrap-and-sessions.js", "createNewConversation"));

            assert.equal(buildNewConvInitMessage("子级04-前端体验（task-overview 页面交互）"), "");

            let dom = {};
            global.document = {
              getElementById(id) {
                return Object.prototype.hasOwnProperty.call(dom, id) ? dom[id] : null;
              },
            };
            global.NEW_CONV_UI = {
              mode: "create",
              channelName: "子级04-前端体验（task-overview 页面交互）",
              initMessageDirty: false,
            };
            dom.newConvInitMessage = { value: "旧默认首发消息" };
            syncNewConvInitMessage(true);
            assert.equal(dom.newConvInitMessage.value, "");
            assert.equal(global.NEW_CONV_UI.initMessageDirty, false);

            function makeDom(initMessage) {
              return {
                newConvProject: { value: "task_dashboard" },
                newConvChannel: { value: "子级04-前端体验（task-overview 页面交互）" },
                newConvCliType: { value: "codex" },
                newConvCreateBtn: { textContent: "创建并绑定", disabled: false },
                newConvSessionId: { value: "" },
                newConvModel: { value: "gpt-5.3-codex" },
                newConvPurpose: { value: "前端实现" },
                newConvAlias: { value: "前端-Agent" },
                newConvSessionRole: { value: "child" },
                newConvReuseStrategy: { value: "create_new" },
                newConvEnvironment: { value: "stable" },
                newConvWorktreeRoot: { value: "/tmp/task-dashboard" },
                newConvWorkdir: { value: "/tmp/task-dashboard" },
                newConvBranch: { value: "main" },
                newConvInitMessage: { value: initMessage },
              };
            }

            global.STATE = { panelMode: "conversation" };
            global.normalizeNewConvMode = (value) => String(value || "").trim() || "create";
            global.normalizeSessionModel = (value) => String(value || "").trim();
            global.isCodexCliType = (value) => String(value || "").trim().toLowerCase() === "codex";
            global.isCodeBuddyCliType = (value) => String(value || "").trim().toLowerCase() === "codebuddy";
            global.isClaudeCliType = (value) => String(value || "").trim().toLowerCase() === "claude";
            global.claudeDefaultModel = () => "claude-opus-5";
            global.normalizeReasoningEffort = (value) => String(value || "").trim();
            global.normalizeSessionEnvironmentValue = (value) => String(value || "stable").trim() || "stable";
            global.looksLikeSessionId = (value) => /^[0-9a-z_-]{10,}$/i.test(String(value || "").trim());
            global.buildProjectExecutionContextMeta = () => ({ available: false, sourceMeta: { text: "" } });
            global.buildBootstrapVisibleMessages = () => ["a", "b"];
            global.tryUpdateSessionModel = async () => false;
            global.verifySessionBindingVisibility = async () => ({ ok: true, hardRefreshRequired: false });
            global.closeNewConvModal = () => {};
            global.refreshConversationPanel = async () => {};
            global.setSelectedSessionId = () => {};
            global.render = () => {};

            async function runCase(initMessage, expectedSendCount, expectedTipRe) {
              dom = makeDom(initMessage);
              global.NEW_CONV_UI.mode = "create";
              const sendCalls = [];
              const bindingCalls = [];
              let hintText = "";
              let errorText = "";
              global.setHintText = (_panel, value) => { hintText = String(value || ""); };
              global.newConvModalError = (value) => { errorText = String(value || ""); };
              global.setBinding = async (projectId, channelName, sessionId, cliType) => {
                bindingCalls.push({ projectId, channelName, sessionId, cliType });
                return true;
              };
              global.postSessionCreateWithChannelRetry = async (payload) => ({
                resp: { ok: true },
                json: {
                  session: {
                    id: "019f7009-0009-7009-8009-000000000009",
                    cli_type: payload.cli_type,
                  },
                },
                retried: false,
              });
              global.sendNewConversationInitMessage = async (projectId, channelName, sessionId, cliType, message, model) => {
                sendCalls.push({ projectId, channelName, sessionId, cliType, message, model });
                return { ok: true };
              };

              await createNewConversation();
              assert.equal(errorText, "");
              assert.equal(bindingCalls.length, 1);
              assert.equal(sendCalls.length, expectedSendCount);
              assert.match(hintText, expectedTipRe);
              return sendCalls;
            }

            (async () => {
              await runCase("", 0, /已创建并绑定新对话。/);
              const sendCalls = await runCase("请按 AGENTS.md 开始。", 1, /并发送一次性启动消息。/);
              assert.equal(sendCalls[0].message, "请按 AGENTS.md 开始。");
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

    def test_codebuddy_model_payload_uses_dropdown_and_default(self) -> None:
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

            eval(extractFunction("web/task_parts/74-session-bootstrap-and-sessions.js", "createNewConversation"));

            let dom = {};
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
            global.looksLikeSessionId = (value) => /^[0-9a-z_-]{10,}$/i.test(String(value || "").trim());
            global.buildProjectExecutionContextMeta = () => ({ available: false, sourceMeta: { text: "" } });
            global.buildBootstrapVisibleMessages = () => ["a", "b"];
            global.tryUpdateSessionModel = async () => false;
            global.verifySessionBindingVisibility = async () => ({ ok: true, hardRefreshRequired: false });
            global.closeNewConvModal = () => {};
            global.refreshConversationPanel = async () => {};
            global.setSelectedSessionId = () => {};
            global.render = () => {};
            global.setHintText = () => {};
            global.newConvModalError = (value) => {
              if (value) throw new Error(String(value));
            };
            global.setBinding = async () => true;
            global.sendNewConversationInitMessage = async () => ({ ok: true });

            function makeDom(cliType, modelValue, codeBuddyValue, reuseStrategy = "create_new") {
              return {
                newConvProject: { value: "task_dashboard" },
                newConvChannel: { value: "子级04-前端体验（task-overview 页面交互）" },
                newConvCliType: { value: cliType },
                newConvCreateBtn: { textContent: "创建并绑定", disabled: false },
                newConvSessionId: { value: "" },
                newConvModel: {
                  value: modelValue,
                  dataset: { modelSource: modelValue ? "user" : "default" },
                },
                newConvCodeBuddyModel: { value: codeBuddyValue },
                newConvPurpose: { value: "前端实现" },
                newConvAlias: { value: "前端-Agent" },
                newConvSessionRole: { value: "child" },
                newConvReuseStrategy: { value: reuseStrategy },
                newConvEnvironment: { value: "stable" },
                newConvWorktreeRoot: { value: "/tmp/task-dashboard" },
                newConvWorkdir: { value: "/tmp/task-dashboard" },
                newConvBranch: { value: "main" },
                newConvInitMessage: { value: "" },
              };
            }

            async function runCase(cliType, modelValue, codeBuddyValue, reuseStrategy = "create_new") {
              dom = makeDom(cliType, modelValue, codeBuddyValue, reuseStrategy);
              let capturedPayload = null;
              global.postSessionCreateWithChannelRetry = async (payload) => {
                capturedPayload = JSON.parse(JSON.stringify(payload));
                return {
                  resp: { ok: true },
                  json: {
                    session: {
                      id: "019f7009-0009-7009-8009-000000000009",
                      cli_type: payload.cli_type,
                    },
                  },
                  retried: false,
                };
              };
              await createNewConversation();
              return capturedPayload;
            }

            (async () => {
              const defaultPayload = await runCase("codebuddy", "", "");
              assert.equal(defaultPayload.model, "deepseek-v4-pro");

              const selectedPayload = await runCase("codebuddy", "", "glm-5.1");
              assert.equal(selectedPayload.model, "glm-5.1");

              const codexPayload = await runCase("codex", "gpt-5.3-codex", "glm-5.1");
              assert.equal(codexPayload.model, "gpt-5.3-codex");

              const claudePayload = await runCase("claude", "claude-opus-5", "");
              assert.equal(claudePayload.model, "claude-opus-5");

              const claudeReusePayload = await runCase("claude", "", "", "reuse_active");
              assert.equal(claudeReusePayload.model, "");
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
