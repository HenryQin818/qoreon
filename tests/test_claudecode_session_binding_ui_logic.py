import shutil
import subprocess
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("node"), "node is required for UI logic regression checks")
class ClaudeCodeSessionBindingUiLogicTests(unittest.TestCase):
    def test_session_binding_failure_is_detected_from_existing_fields(self) -> None:
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
                if (ch === "{") depth += 1;
                else if (ch === "}") {
                  depth -= 1;
                  if (depth === 0) return text.slice(start, i + 1);
                }
              }
              throw new Error(`unterminated function ${name} in ${file}`);
            }

            function firstNonEmptyText(values) {
              for (const value of values || []) {
                const text = String(value || "").trim();
                if (text) return text;
              }
              return "";
            }
            function normalizeDisplayState(raw, fallback = "idle") {
              const text = String(raw || "").trim().toLowerCase();
              return text || String(fallback || "idle").trim().toLowerCase();
            }
            function getSessionRuntimeState(session) {
              return (session && session.runtime_state) || { display_state: "idle", active_run_id: "", queued_run_id: "" };
            }
            function isExplicitIdleRuntimeState() { return false; }

            const file = "web/task_parts/55-session-display-state.js";
            const helperSource = [
              "normalizeSessionDisplayState",
              "normalizeRunSummaryBool",
              "normalizeSessionHealthState",
              "normalizeRunOutcomeState",
              "normalizeRunErrorClass",
              "normalizeLatestRunSummary",
              "normalizeLatestEffectiveRunSummary",
              "getSessionLatestRunSummary",
              "getSessionHealthState",
              "getSessionLatestEffectiveRunSummary",
              "getSessionDisplayState",
              "sessionBindingErrorClassMatches",
              "sessionBindingErrorTextMatches",
              "conversationCliTypeForSession",
              "conversationSessionBindingBlockMeta",
              "isConversationSessionBindingBlocked",
              "conversationSessionBindingBlockMessage",
            ].map((name) => extractFunction(file, name)).join("\n\n");
            eval(helperSource);

            const blocked = {
              cli_type: "claude",
              session_health_state: "blocked",
              latest_effective_run_summary: {
                run_id: "20260611-err",
                outcome_state: "failed_config",
                error_class: "session_binding",
                preview: "error: No conversation found with session ID: 75213c43-c884-4a42-903c-c4961927a2da",
              },
            };
            const meta = conversationSessionBindingBlockMeta(blocked);
            assert.equal(isConversationSessionBindingBlocked(blocked), true);
            assert.equal(meta.reason, "session_binding");
            assert.match(meta.body, /ClaudeCode conversation/);
            assert.match(conversationSessionBindingBlockMessage(blocked), /会话绑定失败/);

            const textOnlyBlocked = {
              cli_type: "claude",
              session_health_state: "blocked",
              latest_run_summary: {
                status: "error",
                error: "No conversation found with session ID abc",
              },
            };
            assert.equal(isConversationSessionBindingBlocked(textOnlyBlocked), true);

            const genericConfigError = {
              cli_type: "claude",
              session_health_state: "blocked",
              latest_effective_run_summary: {
                outcome_state: "failed_config",
                preview: "workspace path missing",
              },
            };
            assert.equal(isConversationSessionBindingBlocked(genericConfigError), false);

            const healthyCodex = {
              cli_type: "codex",
              session_health_state: "healthy",
              latest_effective_run_summary: {
                outcome_state: "success",
                preview: "任务完成",
              },
            };
            assert.equal(isConversationSessionBindingBlocked(healthyCodex), false);
            """
        )
        proc = subprocess.run(
            ["node", "-e", script, str(REPO_ROOT)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            self.fail(proc.stderr or proc.stdout or "node session binding helper regression script failed")

    def test_detail_and_send_path_use_binding_guard_before_announce(self) -> None:
        conversation_js = (REPO_ROOT / "web" / "task_parts" / "60-conversation.js").read_text(encoding="utf-8")
        composer_js = (REPO_ROOT / "web" / "task_parts" / "75-conversation-composer.js").read_text(encoding="utf-8")
        css = (REPO_ROOT / "web" / "task_parts" / "60-conversation.css").read_text(encoding="utf-8")

        self.assertIn("function buildConversationSessionBindingBlockCard", conversation_js)
        self.assertIn("conversationSessionBindingBlockMeta(currentSession)", conversation_js)
        self.assertIn("input.disabled = !!sessionBindingBlockMeta;", conversation_js)
        self.assertIn("sendBtn.disabled = !!sessionBindingBlockMeta || PCONV.sending;", conversation_js)
        self.assertIn("普通发送已暂停", conversation_js)
        self.assertIn("点击重试状态", conversation_js)

        guard_index = composer_js.index("conversationSessionBindingBlockMeta(currentSessionForSend)")
        announce_index = composer_js.index('fetch("/api/codex/announce"')
        self.assertLess(guard_index, announce_index)
        self.assertIn("会话绑定失败，未发送", composer_js)
        self.assertIn("return false;", composer_js[guard_index:announce_index])

        self.assertIn(".conv-projection-explain-action", css)


if __name__ == "__main__":
    unittest.main()
