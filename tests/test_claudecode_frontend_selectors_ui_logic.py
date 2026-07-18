import re
import shutil
import subprocess
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class ClaudeCodeFrontendSelectorsUiLogicTests(unittest.TestCase):
    def test_claudecode_composer_has_model_and_permission_selectors(self) -> None:
        html = (REPO_ROOT / "web" / "task.html.tpl").read_text(encoding="utf-8")
        options_js = (REPO_ROOT / "web" / "task_parts" / "08-cli-model-options.js").read_text(encoding="utf-8")
        session_info_js = (REPO_ROOT / "web" / "task_entry_parts" / "81-session-info-and-bindings.js").read_text(encoding="utf-8")
        composer_js = (REPO_ROOT / "web" / "task_parts" / "75-conversation-composer.js").read_text(encoding="utf-8")
        controls_js = (REPO_ROOT / "web" / "task_parts" / "75-00-conversation-cli-controls.js").read_text(encoding="utf-8")
        conversation_js = (REPO_ROOT / "web" / "task_parts" / "60-conversation.js").read_text(encoding="utf-8")
        bootstrap_js = (REPO_ROOT / "web" / "task_parts" / "74-session-bootstrap-and-sessions.js").read_text(encoding="utf-8")

        sender_meta_match = re.search(r'<div class="convsendermeta">([\s\S]*?)</div>', html)
        self.assertIsNotNone(sender_meta_match)
        sender_meta = sender_meta_match.group(1)
        self.assertLess(sender_meta.index("convClaudeModelControl"), sender_meta.index("convSenderHint"))
        self.assertLess(sender_meta.index("convClaudePermissionControl"), sender_meta.index("convSenderHint"))
        self.assertIn('id="convClaudeModelSelect"', sender_meta)
        self.assertIn('aria-label="ClaudeCode 模型"', sender_meta)
        self.assertIn('id="convClaudePermissionSelect"', sender_meta)
        self.assertIn('aria-label="ClaudeCode 授权模式"', sender_meta)
        self.assertIn('value="bypassPermissions">最大授权', sender_meta)
        self.assertIn('value="default">默认授权', sender_meta)
        self.assertIn('value="acceptEdits">自动接受编辑', sender_meta)
        self.assertIn('value="plan">计划模式', sender_meta)

        self.assertIn('const CLAUDE_DEFAULT_MODEL = "claude-opus-4-8";', options_js)
        model_options_match = re.search(r"const CLAUDE_MODEL_OPTIONS = \[([\s\S]*?)\];", options_js)
        self.assertIsNotNone(model_options_match)
        model_options = model_options_match.group(1)
        self.assertIn('"claude-opus-4-8"', model_options)
        self.assertIn('"claude-sonnet-4-6"', model_options)
        self.assertIn('"claude-haiku-4-5"', model_options)
        self.assertIn('"claude-fable-5"', model_options)
        self.assertIn('"default"', model_options)
        self.assertIn('"sonnet"', model_options)
        self.assertIn('"opus"', model_options)
        self.assertIn('"haiku"', model_options)
        self.assertIn('"best"', model_options)
        self.assertIn('"opusplan"', model_options)
        self.assertNotIn("claude-sonnet-4-20250514", model_options)
        self.assertNotIn("claude-opus-4-20250514", model_options)
        self.assertNotIn('"claude-sonnet"', model_options)
        self.assertIn('const CLAUDE_PERMISSION_MODE_DEFAULT = "bypassPermissions";', options_js)
        self.assertIn("function isClaudeCliType", options_js)
        self.assertIn("function populateClaudeModelSelect", options_js)
        self.assertIn("function populateClaudePermissionModeSelect", options_js)
        self.assertIn('"claude-opus-4-8": "Claude Opus 4.8"', options_js)
        self.assertIn('"claude-fable-5": "Claude Fable 5"', options_js)
        self.assertIn('<option value="claude-fable-5"></option>', html)
        self.assertIn('"default": "Alias: default"', options_js)
        self.assertIn("默认 claude-opus-4-8；可选完整模型 ID 或 alias", options_js)
        self.assertNotIn('return typeof claudeDefaultModel === "function" ? claudeDefaultModel() : "claude-sonnet";', controls_js)

        self.assertIn("function renderConversationComposerClaudeModel", controls_js)
        self.assertIn("function conversationComposerModelReadiness", controls_js)
        self.assertIn("function hydrateConversationComposerModelIfNeeded", controls_js)
        self.assertIn("读取模型配置中", controls_js)
        self.assertIn("function renderConversationComposerClaudePermissionMode", controls_js)
        self.assertIn("function resolveConversationComposerClaudePermissionMode", controls_js)
        self.assertIn("function resolveConversationComposerPermissionPayload", controls_js)
        self.assertIn("tryUpdateSessionClaudePermissionMode(sid, next)", controls_js)
        self.assertIn("syncConversationComposerClaudeModelToLocal", controls_js)
        self.assertIn("syncConversationComposerClaudePermissionModeToLocal", controls_js)
        self.assertIn("permission_mode: mode", controls_js)
        self.assertIn("permissionMode: mode", controls_js)
        self.assertIn("claude_permission_mode: mode", controls_js)
        self.assertIn("claudePermissionMode: mode", controls_js)
        self.assertIn("最大授权会追加 --dangerously-skip-permissions", controls_js)

        self.assertIn("renderConversationComposerClaudeModel(null)", conversation_js)
        self.assertIn("renderConversationComposerClaudeModel(ctx)", conversation_js)
        self.assertIn("renderConversationComposerClaudePermissionMode(null)", conversation_js)
        self.assertIn("renderConversationComposerClaudePermissionMode(ctx)", conversation_js)

        self.assertIn("function tryUpdateSessionClaudePermissionMode", bootstrap_js)
        self.assertIn("claude_permission_mode: normalized", bootstrap_js)
        self.assertIn("permission_mode: normalized", bootstrap_js)
        self.assertIn("syncConversationComposerClaudeModelToLocal", session_info_js)
        self.assertIn("isClaudeCliType(cliType)", session_info_js)

    def test_claudecode_composer_resolves_model_and_permission_payload(self) -> None:
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
            function isClaudeCliType(raw) {
              const t = String(raw || "").trim().toLowerCase();
              return t === "claude" || t === "claudecode" || t === "claude_code" || t === "claude-code";
            }
            function codeBuddyDefaultModel() { return "deepseek-v4-pro"; }
            function codexDefaultModel() { return ""; }
            function claudeDefaultModel() { return "claude-opus-4-8"; }
            function normalizeCodeBuddyPermissionMode(raw) {
              const text = String(raw || "").trim();
              return text === "bypassPermissions" ? "bypassPermissions" : "default";
            }
            function codeBuddyDefaultPermissionMode() { return "default"; }
            function normalizeClaudePermissionMode(raw) {
              const text = String(raw || "").trim();
              if (!text) return "bypassPermissions";
              if (["default", "acceptEdits", "plan", "bypassPermissions"].includes(text)) return text;
              return "bypassPermissions";
            }
            function claudeDefaultPermissionMode() { return "bypassPermissions"; }
            function currentConversationCtx() { return null; }
            function resolveConversationSendCtx() { return null; }
            function getSessionId(row) { return String((row && (row.sessionId || row.id)) || ""); }

            global.STATE = { selectedSessionId: "session-a", project: "task_dashboard" };
            global.PCONV = {
              sessions: [{
                sessionId: "session-a",
                id: "session-a",
                cli_type: "claude",
                model: "claude-opus-4-8",
                claude_permission_mode: "default",
              }],
              claudeModelBySessionId: { "session-a": "claude-fable-5" },
              claudePermissionModeBySessionId: { "session-a": "bypassPermissions" },
            };
            let mockClaudeModelSelect = {
              hidden: false,
              value: "claude-fable-5",
              dataset: { sessionId: "session-a", saving: "", model: "claude-fable-5" },
            };
            let mockClaudePermissionSelect = {
              hidden: false,
              value: "bypassPermissions",
              dataset: { sessionId: "session-a", saving: "", mode: "bypassPermissions" },
            };
            global.document = {
              getElementById(id) {
                if (id === "convClaudeModelSelect") {
                  return mockClaudeModelSelect;
                }
                if (id === "convClaudePermissionSelect") {
                  return mockClaudePermissionSelect;
                }
                return null;
              },
            };
            function findConversationSessionById(sid) {
              return PCONV.sessions.find((row) => getSessionId(row) === sid) || null;
            }

            const functions = [
              "conversationComposerCliType",
              "conversationComposerSupportsModelSwitch",
              "conversationComposerCliTypesMatch",
              "conversationComposerDefaultModelForCli",
              "conversationComposerModelSelectForCli",
              "conversationComposerCachedModelForCli",
              "conversationComposerSessionDetailLoadedForModel",
              "conversationComposerModelReadiness",
              "conversationComposerModelCanUseDefault",
              "conversationComposerSessionModel",
              "conversationComposerSelectedModel",
              "resolveConversationComposerModel",
              "resolveConversationComposerPayloadModel",
              "conversationComposerSessionPermissionMode",
              "conversationComposerSelectedPermissionMode",
              "resolveConversationComposerCodeBuddyPermissionMode",
              "conversationComposerSessionClaudePermissionMode",
              "conversationComposerSelectedClaudePermissionMode",
              "resolveConversationComposerClaudePermissionMode",
              "resolveConversationComposerPermissionPayload",
            ];
            for (const name of functions) {
              eval(extractFunction("web/task_parts/75-00-conversation-cli-controls.js", name));
            }

            const ctx = { sessionId: "session-a", cliType: "claude", model: "claude-opus-4-8" };
            assert.equal(resolveConversationComposerPayloadModel(ctx), "claude-fable-5");
            assert.equal(resolveConversationComposerClaudePermissionMode(ctx), "bypassPermissions");
            assert.deepEqual(resolveConversationComposerPermissionPayload(ctx), {
              permission_mode: "bypassPermissions",
              permissionMode: "bypassPermissions",
              claude_permission_mode: "bypassPermissions",
              claudePermissionMode: "bypassPermissions",
            });
            assert.equal(resolveConversationComposerPayloadModel({ sessionId: "session-a", cliType: "codex" }), "");
            assert.deepEqual(resolveConversationComposerPermissionPayload({ sessionId: "session-a", cliType: "codex" }), {});

            STATE.selectedSessionId = "session-b";
            PCONV.sessions = [{
              sessionId: "session-b",
              id: "session-b",
              cli_type: "claude",
            }];
            PCONV.claudeModelBySessionId = {};
            PCONV.sessionDetailLoadedAtById = {};
            mockClaudeModelSelect = {
              hidden: false,
              value: "",
              dataset: { sessionId: "session-b", saving: "", model: "" },
            };
            mockClaudePermissionSelect = {
              hidden: false,
              value: "bypassPermissions",
              dataset: { sessionId: "session-b", saving: "", mode: "bypassPermissions" },
            };
            const lightCtx = { sessionId: "session-b", cliType: "claude", model: "" };
            assert.equal(resolveConversationComposerModel(lightCtx, { preferSelected: false }), "");
            assert.equal(resolveConversationComposerPayloadModel(lightCtx), "");

            PCONV.sessionDetailLoadedAtById["session-b"] = Date.now();
            PCONV.sessions[0].model = "claude-fable-5";
            assert.equal(resolveConversationComposerModel(lightCtx, { preferSelected: false }), "claude-fable-5");
            assert.equal(resolveConversationComposerPayloadModel(lightCtx), "claude-fable-5");
          """
        )
        proc = subprocess.run(
            ["node", "-e", script, str(REPO_ROOT)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            self.fail(proc.stderr or proc.stdout or "node claudecode selector regression script failed")


if __name__ == "__main__":
    unittest.main()
