import re
import shutil
import subprocess
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class CodexFrontendSelectorsUiLogicTests(unittest.TestCase):
    def test_codex_model_and_reasoning_controls_cover_three_entrypoints(self) -> None:
        html = (REPO_ROOT / "web" / "task.html.tpl").read_text(encoding="utf-8")
        options_js = (REPO_ROOT / "web" / "task_parts" / "08-cli-model-options.js").read_text(encoding="utf-8")
        controls_js = (REPO_ROOT / "web" / "task_parts" / "75-00-conversation-cli-controls.js").read_text(encoding="utf-8")
        composer_js = (REPO_ROOT / "web" / "task_parts" / "75-conversation-composer.js").read_text(encoding="utf-8")
        bootstrap_js = (REPO_ROOT / "web" / "task_parts" / "74-session-bootstrap-and-sessions.js").read_text(encoding="utf-8")
        session_info_js = (REPO_ROOT / "web" / "task_entry_parts" / "81-session-info-and-bindings.js").read_text(encoding="utf-8")

        self.assertIn('const CODEX_DEFAULT_MODEL = "";', options_js)
        model_match = re.search(r"const CODEX_MODEL_OPTIONS = \[([\s\S]*?)\];", options_js)
        self.assertIsNotNone(model_match)
        for model in (
            "gpt-5.6-sol",
            "gpt-5.6-terra",
            "gpt-5.6-luna",
            "gpt-5.5",
            "gpt-5.4",
            "gpt-5.4-mini",
            "gpt-5.3-codex-spark",
        ):
            self.assertIn(f'"{model}"', model_match.group(1))
            self.assertIn(f'value="{model}"', html)
        self.assertIn("API 兼容受限", options_js)
        self.assertIn('const CODEX_REASONING_EFFORT_DEFAULT = "";', options_js)
        for value, label in (("low", "轻度"), ("medium", "中"), ("high", "高"), ("xhigh", "极高")):
            self.assertIn(f'{{ value: "{value}", label: "{label}" }}', options_js)

        sender_meta = re.search(r'<div class="convsendermeta">([\s\S]*?)</div>', html)
        self.assertIsNotNone(sender_meta)
        sender_block = sender_meta.group(1)
        self.assertLess(sender_block.index("convCodexModelControl"), sender_block.index("convCodexReasoningControl"))
        self.assertLess(sender_block.index("convCodexReasoningControl"), sender_block.index("convSenderHint"))
        self.assertIn('id="convCodexModelInput"', sender_block)
        self.assertIn('id="convCodexReasoningSelect"', sender_block)
        self.assertNotIn("convCodexPermission", sender_block)

        self.assertIn('id="newConvReasoningEffort"', html)
        self.assertIn("selectedNewConvModelValue", session_info_js)
        self.assertIn("selectedNewConvReasoningEffortValue", session_info_js)
        self.assertIn("convSessionCodexModelOptions", session_info_js)
        self.assertIn("populateCodexReasoningEffortSelect(reasoningSel", session_info_js)
        self.assertIn("留空继续继承现有设置", session_info_js)
        self.assertIn("function renderConversationComposerCodexModel", controls_js)
        self.assertIn("function renderConversationComposerCodexReasoningEffort", controls_js)
        self.assertIn("Codex 模型切换失败，已回退原值", controls_js)
        self.assertIn("Codex 思考强度切换失败，已回退原值", controls_js)
        self.assertIn("function tryUpdateSessionReasoningEffort", bootstrap_js)
        self.assertIn("跟随 Codex CLI 默认", options_js)
        self.assertIn("if (!looksLikeSessionId(sid)) return false;", bootstrap_js)
        self.assertIn("const conversationReasoningPayload = resolveConversationComposerReasoningPayload(ctx);", composer_js)
        self.assertIn("...conversationReasoningPayload", composer_js)
        self.assertNotIn("codex_permission_mode", html + options_js + controls_js)

    def test_blank_cli_defaults_only_save_explicit_user_choices(self) -> None:
        if not shutil.which("node"):
            self.skipTest("node is required for UI logic regression checks")
        script = textwrap.dedent(
            r"""
            const assert = require("node:assert/strict");
            const fs = require("node:fs");
            const path = require("node:path");
            const root = process.argv[1];
            const source = fs.readFileSync(path.join(root, "web/task_entry_parts/81-session-info-and-bindings.js"), "utf8");

            function extractFunction(name) {
              const match = new RegExp(`function ${name}\\(`).exec(source);
              if (!match) throw new Error(`missing ${name}`);
              const start = match.index;
              const header = source.slice(start).match(new RegExp(`function ${name}\\([^\\n]*\\)\\s*\\{`));
              if (!header) throw new Error(`missing header ${name}`);
              const brace = start + header[0].lastIndexOf("{");
              let depth = 0;
              for (let i = brace; i < source.length; i += 1) {
                if (source[i] === "{") depth += 1;
                if (source[i] === "}" && --depth === 0) return source.slice(start, i + 1);
              }
              throw new Error(`unterminated ${name}`);
            }

            function isCodexCliType(raw) { return String(raw || "").trim().toLowerCase() === "codex"; }
            function isCodeBuddyCliType(raw) { return String(raw || "").trim().toLowerCase() === "codebuddy"; }
            function normalizeSessionModel(raw) { return String(raw || "").trim(); }
            function normalizeReasoningEffort(raw) {
              const value = String(raw || "").trim();
              return value === "extra_high" ? "xhigh" : (["low", "medium", "high", "xhigh"].includes(value) ? value : "");
            }
            function normalizeNewConvMode(raw) { return String(raw || "").trim() === "attach" ? "attach" : "create"; }
            function codexDefaultModel() { return ""; }
            function codexDefaultReasoningEffort() { return ""; }
            function codeBuddyDefaultModel() { return "deepseek-v4-pro"; }

            eval(extractFunction("selectedNewConvModelValue"));
            eval(extractFunction("selectedNewConvReasoningEffortValue"));

            const inheritedModel = { value: "gpt-5.6-sol", dataset: { modelSource: "inherit" } };
            const inheritedEffort = { value: "xhigh", dataset: { reasoningSource: "inherit" } };
            assert.equal(selectedNewConvModelValue("codex", inheritedModel, null, { mode: "create", reuseStrategy: "create_new" }), "");
            assert.equal(selectedNewConvReasoningEffortValue("codex", inheritedEffort, { mode: "create", reuseStrategy: "create_new" }), "");
            assert.equal(selectedNewConvModelValue("codex", inheritedModel, null, { mode: "attach", reuseStrategy: "attach_existing" }), "");
            assert.equal(selectedNewConvReasoningEffortValue("codex", inheritedEffort, { mode: "attach", reuseStrategy: "attach_existing" }), "");
            assert.equal(selectedNewConvModelValue("codex", inheritedModel, null, { mode: "create", reuseStrategy: "reuse_active" }), "");
            assert.equal(selectedNewConvReasoningEffortValue("codex", inheritedEffort, { mode: "create", reuseStrategy: "reuse_active" }), "");

            inheritedModel.dataset.modelSource = "user";
            inheritedModel.value = "custom-codex-model";
            inheritedEffort.dataset.reasoningSource = "user";
            inheritedEffort.value = "high";
            assert.equal(selectedNewConvModelValue("codex", inheritedModel, null, { mode: "attach", reuseStrategy: "attach_existing" }), "custom-codex-model");
            assert.equal(selectedNewConvReasoningEffortValue("codex", inheritedEffort, { mode: "attach", reuseStrategy: "attach_existing" }), "high");
            """
        )
        proc = subprocess.run(["node", "-e", script, str(REPO_ROOT)], cwd=REPO_ROOT, capture_output=True, text=True)
        if proc.returncode != 0:
            self.fail(proc.stderr or proc.stdout or "node create defaults regression failed")

    def test_composer_payload_and_failed_save_rollback(self) -> None:
        if not shutil.which("node"):
            self.skipTest("node is required for UI logic regression checks")
        script = textwrap.dedent(
            r"""
            const assert = require("node:assert/strict");
            const fs = require("node:fs");
            const path = require("node:path");
            const root = process.argv[1];
            const file = "web/task_parts/75-00-conversation-cli-controls.js";
            const source = fs.readFileSync(path.join(root, file), "utf8");

            function extractFunction(name) {
              const match = new RegExp(`(?:async\\s+)?function ${name}\\(`).exec(source);
              if (!match) throw new Error(`missing ${name}`);
              const start = match.index;
              const brace = source.indexOf("{", start);
              let depth = 0;
              for (let i = brace; i < source.length; i += 1) {
                if (source[i] === "{") depth += 1;
                if (source[i] === "}" && --depth === 0) return source.slice(start, i + 1);
              }
              throw new Error(`unterminated ${name}`);
            }

            function firstNonEmptyText(values) {
              for (const value of values || []) {
                const text = String(value || "").trim();
                if (text) return text;
              }
              return "";
            }
            function normalizeSessionModel(raw) { return String(raw || "").trim(); }
            function normalizeReasoningEffort(raw) {
              const value = String(raw || "").trim();
              return value === "extra_high" ? "xhigh" : (["low", "medium", "high", "xhigh"].includes(value) ? value : "");
            }
            function isCodexCliType(raw) { return String(raw || "").trim().toLowerCase() === "codex"; }
            function isCodeBuddyCliType(raw) { return String(raw || "").trim().toLowerCase() === "codebuddy"; }
            function isClaudeCliType(raw) { return String(raw || "").trim().toLowerCase() === "claude"; }
            function codexDefaultModel() { return ""; }
            function codexDefaultReasoningEffort() { return ""; }
            function codexModelSelectionHint() { return ""; }
            function codexModelDisplayName(raw) { return String(raw || ""); }
            function codexReasoningEffortDisplayName(raw) { return String(raw || ""); }
            function codeBuddyDefaultModel() { return "deepseek-v4-pro"; }
            function claudeDefaultModel() { return "claude-opus-4-8"; }
            function currentConversationCtx() { return null; }
            function resolveConversationSendCtx() { return null; }
            function setHintText() {}
            function getSessionId(row) { return String((row && (row.id || row.sessionId)) || ""); }
            let saveSucceeds = false;
            const modelSaves = [];
            const reasoningSaves = [];
            async function tryUpdateSessionModel(_sid, value) { modelSaves.push(value); return saveSucceeds; }
            async function tryUpdateSessionReasoningEffort(_sid, value) { reasoningSaves.push(value); return saveSucceeds; }
            function renderConversationComposerCodexModel() {}
            function renderConversationComposerCodexReasoningEffort() {}

            global.STATE = { selectedSessionId: "codex-a", project: "task_dashboard" };
            global.PCONV = {
              sessions: [{ id: "codex-a", sessionId: "codex-a", cli_type: "codex", model: "gpt-5.6-sol", reasoning_effort: "xhigh" }],
              codexModelBySessionId: { "codex-a": "gpt-5.6-terra" },
              codexReasoningEffortBySessionId: { "codex-a": "high" },
              sessionDetailLoadedAtById: { "codex-a": Date.now() },
            };
            const modelInput = { hidden: false, value: "gpt-5.6-terra", disabled: false, dataset: { sessionId: "codex-a", projectId: "task_dashboard", model: "gpt-5.6-sol", saving: "" } };
            const reasoningSelect = { hidden: false, value: "high", disabled: false, dataset: { sessionId: "codex-a", projectId: "task_dashboard", reasoningEffort: "xhigh", saving: "" } };
            const modelStatus = { textContent: "" };
            const reasoningStatus = { textContent: "" };
            global.document = { getElementById(id) {
              if (id === "convCodexModelInput") return modelInput;
              if (id === "convCodexReasoningSelect") return reasoningSelect;
              if (id === "convCodexModelStatus") return modelStatus;
              if (id === "convCodexReasoningStatus") return reasoningStatus;
              return null;
            }};
            function findConversationSessionById(sid) { return PCONV.sessions.find((row) => row.id === sid) || null; }

            for (const name of [
              "conversationComposerCliType", "conversationComposerSupportsModelSwitch", "conversationComposerCliTypesMatch",
              "conversationComposerDefaultModelForCli", "conversationComposerModelSelectForCli", "conversationComposerCachedModelForCli",
              "conversationComposerSessionDetailLoadedForModel", "conversationComposerModelReadiness", "conversationComposerModelCanUseDefault",
              "conversationComposerSessionModel", "conversationComposerSelectedModel", "resolveConversationComposerPayloadModel",
              "conversationComposerSessionReasoningEffort", "conversationComposerSelectedReasoningEffort",
              "resolveConversationComposerReasoningEffort", "resolveConversationComposerReasoningPayload",
              "syncConversationComposerCodexSettingsToLocal", "syncConversationComposerCodexModelToLocal",
              "syncConversationComposerCodexReasoningEffortToLocal",
              "handleConversationComposerCodexModelChange", "handleConversationComposerCodexReasoningEffortChange",
            ]) eval(extractFunction(name));

            const ctx = { sessionId: "codex-a", cliType: "codex" };
            assert.equal(resolveConversationComposerPayloadModel(ctx), "gpt-5.6-terra");
            assert.deepEqual(resolveConversationComposerReasoningPayload(ctx), { reasoning_effort: "high" });

            modelInput.value = "gpt-5.6-luna";
            reasoningSelect.value = "low";
            (async () => {
              await handleConversationComposerCodexModelChange();
              await handleConversationComposerCodexReasoningEffortChange();
              assert.equal(modelInput.value, "gpt-5.6-sol");
              assert.equal(reasoningSelect.value, "xhigh");
              assert.equal(modelInput.disabled, false);
              assert.equal(reasoningSelect.disabled, false);
              assert.match(modelStatus.textContent, /保存失败/);
              assert.match(reasoningStatus.textContent, /保存失败/);

              saveSucceeds = true;
              modelInput.value = "";
              reasoningSelect.value = "";
              await handleConversationComposerCodexModelChange();
              await handleConversationComposerCodexReasoningEffortChange();
              assert.equal(modelSaves.at(-1), "");
              assert.equal(reasoningSaves.at(-1), "");
              assert.equal(modelInput.dataset.model, "");
              assert.equal(reasoningSelect.dataset.reasoningEffort, "");
              assert.equal(PCONV.sessions[0].model, "");
              assert.equal(PCONV.sessions[0].reasoning_effort, "");
              assert.match(modelStatus.textContent, /跟随 CLI/);
              assert.match(reasoningStatus.textContent, /跟随 CLI/);

              PCONV.sessions = [{ id: "codex-a", sessionId: "codex-a", cli_type: "claude", model: "claude-opus-4-8" }];
              PCONV.codexModelBySessionId = {};
              PCONV.codexReasoningEffortBySessionId = {};
              PCONV.sessionDetailLoadedAtById = {};
              modelInput.value = "";
              modelInput.dataset.model = "";
              reasoningSelect.value = "";
              reasoningSelect.dataset.reasoningEffort = "";
              assert.equal(resolveConversationComposerPayloadModel(ctx), "");
              assert.deepEqual(resolveConversationComposerReasoningPayload(ctx), {});
            })().catch((err) => { console.error(err); process.exit(1); });
            """
        )
        proc = subprocess.run(["node", "-e", script, str(REPO_ROOT)], cwd=REPO_ROOT, capture_output=True, text=True)
        if proc.returncode != 0:
            self.fail(proc.stderr or proc.stdout or "node composer regression failed")


if __name__ == "__main__":
    unittest.main()
