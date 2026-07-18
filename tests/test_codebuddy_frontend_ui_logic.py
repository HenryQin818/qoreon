import re
import shutil
import subprocess
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class CodeBuddyFrontendUiLogicTests(unittest.TestCase):
    def test_codebuddy_is_available_in_conversation_entrypoints(self) -> None:
        html = (REPO_ROOT / "web" / "task.html.tpl").read_text(encoding="utf-8")

        for select_id in ("bindCliType", "newConvCliType"):
            match = re.search(
                rf'<select[^>]+id="{select_id}"[\s\S]*?</select>',
                html,
            )
            self.assertIsNotNone(match, f"missing {select_id}")
            block = match.group(0)
            for cli_type in ("codex", "claude", "opencode", "gemini", "trae", "codebuddy"):
                self.assertIn(f'value="{cli_type}"', block)

        self.assertIn("CodeBuddy Code", html)
        self.assertIn("newConvCliHint", html)
        self.assertIn("newConvCodeBuddyModel", html)
        self.assertIn("deepseek-v4-pro", html)

    def test_codebuddy_has_guidance_labels_and_terminal_text_rule(self) -> None:
        options_js = (REPO_ROOT / "web" / "task_parts" / "08-cli-model-options.js").read_text(encoding="utf-8")
        session_js = (REPO_ROOT / "web" / "task_entry_parts" / "81-session-info-and-bindings.js").read_text(encoding="utf-8")
        bootstrap_js = (REPO_ROOT / "web" / "task_parts" / "74-session-bootstrap-and-sessions.js").read_text(encoding="utf-8")
        runs_js = (REPO_ROOT / "web" / "task_parts" / "76-runs-and-drawer.js").read_text(encoding="utf-8")
        task_css = (REPO_ROOT / "web" / "task.css").read_text(encoding="utf-8")
        timeline_css = (REPO_ROOT / "web" / "task_parts" / "70-conversation-timeline.css").read_text(encoding="utf-8")

        self.assertIn('if (t === "codebuddy") return "CodeBuddy";', options_js)
        self.assertIn('const CODEBUDDY_DEFAULT_MODEL = "deepseek-v4-pro";', options_js)
        self.assertIn("仅为创建预设，可改选", session_js)
        self.assertIn("实际保存值为模型 ID", session_js)
        self.assertIn("不代表所有环境已验收", session_js)
        self.assertIn("界面可读名如 DeepSeek V4 Pro", session_js)
        self.assertIn("实际保存值为模型 ID：deepseek-v4-pro", session_js)
        self.assertIn("权限模式与工具白名单由本机 CodeBuddy 配置控制", session_js)
        self.assertIn("dataset.standardModel", session_js)
        self.assertIn("dataset.codebuddyModel", session_js)
        self.assertNotIn('codeBuddyModelOptions().includes(current)) modelInput.value = "";', session_js)
        self.assertIn('codeBuddyModel || normalizeSessionModel(modelInput && modelInput.value) || "deepseek-v4-pro"', bootstrap_js)
        self.assertIn('normalized === "claude" || normalized === "opencode" || normalized === "codebuddy"', runs_js)
        self.assertIn(".conv-type-badge.cli-codebuddy", task_css)
        self.assertIn(".chip.cli-chip.cli-codebuddy", task_css)
        self.assertIn(".mdebug-cli.cli-codebuddy", timeline_css)

    def test_codebuddy_model_dropdown_contains_supported_models(self) -> None:
        options_js = (REPO_ROOT / "web" / "task_parts" / "08-cli-model-options.js").read_text(encoding="utf-8")
        html = (REPO_ROOT / "web" / "task.html.tpl").read_text(encoding="utf-8")
        session_js = (REPO_ROOT / "web" / "task_entry_parts" / "81-session-info-and-bindings.js").read_text(encoding="utf-8")

        for model in (
            "hy3",
            "glm-5.2",
            "glm-5.1",
            "glm-5.0",
            "glm-5.0-turbo",
            "glm-5v-turbo",
            "glm-4.7",
            "minimax-m3-pay",
            "minimax-m2.7",
            "kimi-k2.7",
            "kimi-k2.6",
            "deepseek-v4-pro",
            "deepseek-v4-flash",
            "deepseek-v3-2-volc",
        ):
            self.assertIn(model, options_js)
            self.assertIn(model, html)

        for retired_model in ("minimax-m3", "kimi-k2.5", "hy3-preview"):
            self.assertNotIn(f'"{retired_model}"', options_js)
            self.assertNotIn(f'value="{retired_model}"', html)

        self.assertIn("populateCodeBuddyModelSelect", session_js)
        self.assertIn("历史模型：", options_js)
        self.assertIn("当前不在账号支持快照中，保留原值，可改选", options_js)

    def test_codebuddy_composer_model_switch_precedes_sender_and_sends_model(self) -> None:
        html = (REPO_ROOT / "web" / "task.html.tpl").read_text(encoding="utf-8")
        composer_js = (REPO_ROOT / "web" / "task_parts" / "75-conversation-composer.js").read_text(encoding="utf-8")
        controls_js = (REPO_ROOT / "web" / "task_parts" / "75-00-conversation-cli-controls.js").read_text(encoding="utf-8")
        conversation_js = (REPO_ROOT / "web" / "task_parts" / "60-conversation.js").read_text(encoding="utf-8")
        runs_js = (REPO_ROOT / "web" / "task_parts" / "76-runs-and-drawer.js").read_text(encoding="utf-8")

        sender_meta_match = re.search(r'<div class="convsendermeta">([\s\S]*?)</div>', html)
        self.assertIsNotNone(sender_meta_match)
        sender_meta = sender_meta_match.group(1)
        self.assertLess(sender_meta.index("convCodeBuddyModelControl"), sender_meta.index("convSenderHint"))
        self.assertIn('id="convCodeBuddyModelSelect"', sender_meta)
        self.assertIn('aria-label="CodeBuddy 模型"', sender_meta)
        self.assertLess(sender_meta.index("convCodeBuddyModelControl"), sender_meta.index("convCodeBuddyPermissionControl"))
        self.assertLess(sender_meta.index("convCodeBuddyPermissionControl"), sender_meta.index("convSenderHint"))
        self.assertIn('id="convCodeBuddyPermissionSelect"', sender_meta)
        self.assertIn('aria-label="CodeBuddy 授权模式"', sender_meta)
        self.assertIn('value="default">默认授权', sender_meta)
        self.assertIn('value="bypassPermissions">全部授权', sender_meta)

        self.assertIn("function renderConversationComposerCodeBuddyModel", controls_js)
        self.assertIn("function resolveConversationComposerModel", controls_js)
        self.assertIn("function conversationComposerSelectedModel", controls_js)
        self.assertIn("function resolveConversationComposerPayloadModel", controls_js)
        self.assertIn('document.getElementById("convCodeBuddyModelSelect")', controls_js)
        self.assertIn('String(select.dataset.sessionId || "").trim() !== sid', controls_js)
        self.assertIn("if (canonicalSessionModel && saved && saved !== canonicalSessionModel) return \"\";", controls_js)
        self.assertIn("return selectedModel || sessionModel || fallback;", controls_js)
        self.assertIn("return selectedModel || sessionModel || \"\";", controls_js)
        self.assertIn("resolveConversationComposerModel(context, { preferSelected: false })", controls_js)
        self.assertIn('select.dataset.model = String(sessionModel || "");', controls_js)
        self.assertIn('select.dataset.modelSource = sessionModel ? "session" : "default";', controls_js)
        self.assertIn("tryUpdateSessionModel(sid, next)", controls_js)
        self.assertIn("syncConversationComposerCodeBuddyModelToLocal", controls_js)
        self.assertIn("下一次发送将使用", controls_js)
        self.assertIn("const conversationModel = resolveConversationComposerPayloadModel(ctx);", composer_js)
        self.assertIn("...(conversationModel ? { model: conversationModel } : {})", composer_js)
        self.assertIn("function renderConversationComposerCodeBuddyPermissionMode", controls_js)
        self.assertIn("function resolveConversationComposerCodeBuddyPermissionMode", controls_js)
        self.assertIn("tryUpdateSessionCodeBuddyPermissionMode(sid, next)", controls_js)
        self.assertIn("syncConversationComposerCodeBuddyPermissionModeToLocal", controls_js)
        self.assertIn("全部授权会绕过 CodeBuddy 权限确认，可能执行文件修改和命令。", controls_js)
        self.assertIn("保存失败，已保留原值", controls_js)
        self.assertIn("codebuddy_permission_mode: mode", controls_js)
        self.assertIn("codebuddyPermissionMode: mode", controls_js)
        self.assertIn("const conversationPermissionPayload = resolveConversationComposerPermissionPayload(ctx);", composer_js)
        self.assertIn("renderConversationComposerCodeBuddyModel(null)", conversation_js)
        self.assertIn("renderConversationComposerCodeBuddyModel(ctx)", conversation_js)
        self.assertIn("renderConversationComposerCodeBuddyPermissionMode(null)", conversation_js)
        self.assertIn("renderConversationComposerCodeBuddyPermissionMode(ctx)", conversation_js)
        self.assertIn("resolveConversationComposerPayloadModel(ctx)", runs_js)
        self.assertIn("...(conversationModel ? { model: conversationModel } : {})", runs_js)

    def test_codebuddy_saved_model_survives_stale_default_refresh(self) -> None:
        if not shutil.which("node"):
            self.skipTest("node is required for UI logic regression checks")
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
                if (escape) {
                  escape = false;
                  continue;
                }
                if (inSingle || inDouble || inTemplate) {
                  if (ch === "\\") {
                    escape = true;
                    continue;
                  }
                  if (inSingle && ch === "'") inSingle = false;
                  else if (inDouble && ch === '"') inDouble = false;
                  else if (inTemplate && ch === "`") inTemplate = false;
                  continue;
                }
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
                if (ch === "{") depth += 1;
                else if (ch === "}") {
                  depth -= 1;
                  if (depth === 0) return text.slice(start, i + 1);
                }
              }
              throw new Error(`unterminated function ${name} in ${file}`);
            }

            function firstNonEmptyText(values, fallback = "") {
              for (const value of values || []) {
                const text = String(value || "").trim();
                if (text) return text;
              }
              return String(fallback || "");
            }
            function normalizeSessionModel(raw) { return String(raw || "").trim(); }
            function isCodexCliType(raw) { return String(raw || "").trim().toLowerCase() === "codex"; }
            function isCodeBuddyCliType(raw) { return String(raw || "").trim().toLowerCase() === "codebuddy"; }
            function codexDefaultModel() { return ""; }
            function codeBuddyDefaultModel() { return "deepseek-v4-pro"; }
            function normalizeCodeBuddyPermissionMode(raw) {
              const text = String(raw || "").trim();
              if (text === "bypassPermissions" || text === "bypass_permissions") return "bypassPermissions";
              return "default";
            }
            function codeBuddyDefaultPermissionMode() { return "default"; }
            function currentConversationCtx() { return null; }
            function resolveConversationSendCtx() { return null; }
            function getSessionId(row) { return String((row && (row.sessionId || row.id)) || ""); }

            eval(extractFunction("web/task_parts/74-session-bootstrap-and-sessions.js", "codeBuddySessionDefaultModelValue"));
            eval(extractFunction("web/task_parts/74-session-bootstrap-and-sessions.js", "codeBuddySessionDefaultPermissionModeValue"));
            eval(extractFunction("web/task_parts/74-session-bootstrap-and-sessions.js", "conversationSessionModelMergeSource"));
            eval(extractFunction("web/task_parts/74-session-bootstrap-and-sessions.js", "conversationSessionPermissionModeMergeSource"));
            eval(extractFunction("web/task_parts/74-session-bootstrap-and-sessions.js", "conversationSessionModelMergeCliType"));
            eval(extractFunction("web/task_parts/74-session-bootstrap-and-sessions.js", "conversationSessionHasPermissionMode"));
            eval(extractFunction("web/task_parts/74-session-bootstrap-and-sessions.js", "conversationSessionModelMergeIsExplicit"));
            eval(extractFunction("web/task_parts/74-session-bootstrap-and-sessions.js", "conversationSessionPermissionModeMergeIsExplicit"));
            eval(extractFunction("web/task_parts/74-session-bootstrap-and-sessions.js", "normalizeConversationCodeBuddyPermissionMode"));
            eval(extractFunction("web/task_parts/74-session-bootstrap-and-sessions.js", "mergeConversationSessionModelValue"));
            eval(extractFunction("web/task_parts/74-session-bootstrap-and-sessions.js", "mergeConversationSessionPermissionModeValue"));

            assert.equal(
              mergeConversationSessionModelValue(
                { cli_type: "codebuddy", model: "deepseek-v4-pro", source: "run-summary" },
                { cli_type: "codebuddy", model: "minimax-m3-pay" }
              ),
              "minimax-m3-pay"
            );
            assert.equal(
              mergeConversationSessionModelValue(
                { cli_type: "codebuddy", model: "deepseek-v4-pro", source: "composer-model-switch" },
                { cli_type: "codebuddy", model: "minimax-m3-pay" }
              ),
              "deepseek-v4-pro"
            );
            assert.equal(
              mergeConversationSessionPermissionModeValue(
                { cli_type: "codebuddy", codebuddy_permission_mode: "default", source: "run-summary" },
                { cli_type: "codebuddy", codebuddy_permission_mode: "bypassPermissions" }
              ),
              "bypassPermissions"
            );
            assert.equal(
              mergeConversationSessionPermissionModeValue(
                { cli_type: "codebuddy", codebuddy_permission_mode: "default", source: "composer-permission-switch" },
                { cli_type: "codebuddy", codebuddy_permission_mode: "bypassPermissions" }
              ),
              "default"
            );

            global.STATE = { selectedSessionId: "session-a" };
            global.PCONV = {
              sessions: [{
                sessionId: "session-a",
                id: "session-a",
                cli_type: "codebuddy",
                model: "deepseek-v4-pro",
                codebuddy_permission_mode: "default",
              }],
              codeBuddyModelBySessionId: { "session-a": "minimax-m3-pay" },
              codeBuddyPermissionModeBySessionId: { "session-a": "bypassPermissions" },
            };
            global.document = {
              getElementById(id) {
                if (id === "convCodeBuddyPermissionSelect") {
                  return {
                    hidden: false,
                    value: "bypassPermissions",
                    dataset: { sessionId: "session-a", saving: "", mode: "bypassPermissions" },
                  };
                }
                if (id !== "convCodeBuddyModelSelect") return null;
                return {
                  hidden: false,
                  value: "minimax-m3-pay",
                  dataset: { sessionId: "session-a", saving: "", model: "minimax-m3-pay" },
                };
              },
            };
            function findConversationSessionById(sid) {
              return PCONV.sessions.find((row) => getSessionId(row) === sid) || null;
            }

            eval(extractFunction("web/task_parts/75-00-conversation-cli-controls.js", "conversationComposerCliType"));
            eval(extractFunction("web/task_parts/75-00-conversation-cli-controls.js", "conversationComposerSupportsModelSwitch"));
            eval(extractFunction("web/task_parts/75-00-conversation-cli-controls.js", "conversationComposerCliTypesMatch"));
            eval(extractFunction("web/task_parts/75-00-conversation-cli-controls.js", "conversationComposerDefaultModelForCli"));
            eval(extractFunction("web/task_parts/75-00-conversation-cli-controls.js", "conversationComposerModelSelectForCli"));
            eval(extractFunction("web/task_parts/75-00-conversation-cli-controls.js", "conversationComposerCachedModelForCli"));
            eval(extractFunction("web/task_parts/75-00-conversation-cli-controls.js", "conversationComposerSessionModel"));
            eval(extractFunction("web/task_parts/75-00-conversation-cli-controls.js", "conversationComposerSelectedModel"));
            eval(extractFunction("web/task_parts/75-00-conversation-cli-controls.js", "resolveConversationComposerPayloadModel"));
            eval(extractFunction("web/task_parts/75-00-conversation-cli-controls.js", "conversationComposerSessionPermissionMode"));
            eval(extractFunction("web/task_parts/75-00-conversation-cli-controls.js", "conversationComposerSelectedPermissionMode"));
            eval(extractFunction("web/task_parts/75-00-conversation-cli-controls.js", "resolveConversationComposerCodeBuddyPermissionMode"));

            const ctx = { sessionId: "session-a", cliType: "codebuddy", model: "deepseek-v4-pro" };
            assert.equal(conversationComposerSessionModel(ctx), "minimax-m3-pay");
            assert.equal(resolveConversationComposerPayloadModel(ctx), "minimax-m3-pay");
            assert.equal(conversationComposerSessionPermissionMode(ctx), "bypassPermissions");
            assert.equal(resolveConversationComposerCodeBuddyPermissionMode(ctx), "bypassPermissions");
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

    def test_codebuddy_composer_permission_mode_has_fixed_options_and_session_save(self) -> None:
        options_js = (REPO_ROOT / "web" / "task_parts" / "08-cli-model-options.js").read_text(encoding="utf-8")
        bootstrap_js = (REPO_ROOT / "web" / "task_parts" / "74-session-bootstrap-and-sessions.js").read_text(encoding="utf-8")
        controls_js = (REPO_ROOT / "web" / "task_parts" / "75-00-conversation-cli-controls.js").read_text(encoding="utf-8")
        runs_js = (REPO_ROOT / "web" / "task_parts" / "76-runs-and-drawer.js").read_text(encoding="utf-8")
        conversation_css = (REPO_ROOT / "web" / "task_parts" / "60-conversation.css").read_text(encoding="utf-8")
        session_js = (REPO_ROOT / "web" / "task_entry_parts" / "81-session-info-and-bindings.js").read_text(encoding="utf-8")

        self.assertIn('const CODEBUDDY_PERMISSION_MODE_DEFAULT = "default";', options_js)
        self.assertIn('{ value: "default", label: "默认授权" }', options_js)
        self.assertIn('{ value: "bypassPermissions", label: "全部授权" }', options_js)
        self.assertIn("function normalizeCodeBuddyPermissionMode", options_js)
        self.assertIn("function populateCodeBuddyPermissionModeSelect", options_js)
        codebuddy_options = re.search(
            r"const CODEBUDDY_PERMISSION_MODE_OPTIONS = \[([\s\S]*?)\];",
            options_js,
        )
        self.assertIsNotNone(codebuddy_options)
        self.assertNotIn("acceptEdits", codebuddy_options.group(1))
        self.assertNotIn("plan\", label", codebuddy_options.group(1))

        self.assertIn("function tryUpdateSessionCodeBuddyPermissionMode", bootstrap_js)
        self.assertIn("body: JSON.stringify({ codebuddy_permission_mode: normalized })", bootstrap_js)
        self.assertIn("codebuddy_permission_mode: typeof normalizeCodeBuddyPermissionMode", bootstrap_js)
        self.assertIn("mergeConversationSessionPermissionModeValue", session_js)
        self.assertIn("payload.codebuddy_permission_mode", session_js)
        self.assertIn("populateCodeBuddyPermissionModeSelect(codeBuddyPermissionSelect", session_js)
        self.assertIn("syncConversationComposerCodeBuddyPermissionModeToLocal", session_js)
        self.assertIn("syncConversationComposerCodeBuddyModelToLocal(", session_js)
        self.assertIn("codebuddyPermissionMode", runs_js)

        self.assertIn("hideConversationComposerCodeBuddyPermissionMode()", controls_js)
        self.assertIn('if (!context || !isCodeBuddyCliType(context.cliType))', controls_js)
        self.assertIn('control.classList.toggle("is-danger", select.value === "bypassPermissions")', controls_js)
        self.assertIn('setHintText("conv", "CodeBuddy 授权模式切换失败，已保留原值。")', controls_js)
        self.assertIn("CodeBuddy 授权模式已切换为 ", controls_js)
        self.assertIn(".conv-permission-switch.is-danger", conversation_css)
        self.assertIn(".conv-permission-switch-select", conversation_css)

    def test_codebuddy_permission_mode_save_requires_server_echo(self) -> None:
        script = textwrap.dedent(
            r"""
            const assert = require("assert");
            const fs = require("fs");
            const path = require("path");
            const root = process.argv[1];
            const source = fs.readFileSync(path.join(root, "web/task_parts/74-session-bootstrap-and-sessions.js"), "utf8");

            function extractFunction(name) {
              const markers = [`async function ${name}`, `function ${name}`];
              let start = -1;
              for (const marker of markers) {
                start = source.indexOf(marker);
                if (start >= 0) break;
              }
              if (start < 0) throw new Error(`missing function ${name}`);
              const brace = source.indexOf("{", start);
              let depth = 0;
              for (let i = brace; i < source.length; i++) {
                const ch = source[i];
                if (ch === "{") depth += 1;
                if (ch === "}") {
                  depth -= 1;
                  if (depth === 0) return source.slice(start, i + 1);
                }
              }
              throw new Error(`unterminated function ${name}`);
            }

            function normalizeCodeBuddyPermissionMode(raw) {
              const text = String(raw || "").trim();
              if (text === "bypassPermissions" || text === "bypass_permissions") return "bypassPermissions";
              return "default";
            }
            function looksLikeSessionId(value) {
              return /^[0-9a-f-]{36}$/i.test(String(value || ""));
            }
            function authHeaders(headers) {
              return headers || {};
            }

            eval(extractFunction("tryUpdateSessionCodeBuddyPermissionMode"));

            (async () => {
              const sid = "11111111-1111-1111-1111-111111111111";
              global.fetch = async () => ({
                ok: true,
                json: async () => ({ session: { codebuddy_permission_mode: "default" } }),
              });
              assert.equal(await tryUpdateSessionCodeBuddyPermissionMode(sid, "bypassPermissions"), false);

              global.fetch = async () => ({
                ok: true,
                json: async () => ({ session: { codebuddy_permission_mode: "bypassPermissions" } }),
              });
              assert.equal(await tryUpdateSessionCodeBuddyPermissionMode(sid, "bypassPermissions"), true);

              global.fetch = async () => ({
                ok: true,
                json: async () => ({ codebuddyPermissionMode: "bypassPermissions" }),
              });
              assert.equal(await tryUpdateSessionCodeBuddyPermissionMode(sid, "bypassPermissions"), true);

              global.fetch = async () => ({
                ok: false,
                json: async () => ({ session: { codebuddy_permission_mode: "bypassPermissions" } }),
              });
              assert.equal(await tryUpdateSessionCodeBuddyPermissionMode(sid, "bypassPermissions"), false);
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
