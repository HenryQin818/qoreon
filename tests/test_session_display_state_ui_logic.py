import shutil
import subprocess
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("node"), "node is required for UI logic regression checks")
class SessionDisplayStateUiLogicTests(unittest.TestCase):
    def test_runtime_active_or_queued_run_overrides_stale_done_summary(self) -> None:
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

            function firstNonEmptyText(values) {
              const list = Array.isArray(values) ? values : [values];
              for (const value of list) {
                const text = String(value || "").trim();
                if (text) return text;
              }
              return "";
            }

            function normalizeDisplayState(raw, fallback = "idle") {
              const s = String(raw || "").trim().toLowerCase();
              if (["running", "queued", "retry_waiting", "done", "error", "idle", "external_busy"].includes(s)) {
                return s;
              }
              return String(fallback || "idle").trim().toLowerCase() || "idle";
            }

            function normalizeRuntimeState(raw) {
              const src = raw && typeof raw === "object" ? raw : {};
              const internal = normalizeDisplayState(firstNonEmptyText([src.internal_state, src.internalState, src.status]), "idle");
              const display = normalizeDisplayState(firstNonEmptyText([src.display_state, src.displayState]), internal);
              return {
                internal_state: internal,
                external_busy: !!src.external_busy,
                display_state: display,
                active_run_id: String(firstNonEmptyText([src.active_run_id, src.activeRunId]) || "").trim(),
                queued_run_id: String(firstNonEmptyText([src.queued_run_id, src.queuedRunId]) || "").trim(),
                queue_depth: Math.max(0, Number(firstNonEmptyText([src.queue_depth, src.queueDepth, 0])) || 0),
                updated_at: String(firstNonEmptyText([src.updated_at, src.updatedAt]) || "").trim(),
              };
            }

            function getSessionRuntimeState(session) {
              return normalizeRuntimeState((session && (session.runtime_state || session.runtimeState)) || null);
            }

            function isExplicitIdleRuntimeState(raw) {
              const rs = normalizeRuntimeState(raw);
              return rs.display_state === "idle"
                && rs.internal_state === "idle"
                && !rs.external_busy
                && !rs.active_run_id
                && !rs.queued_run_id
                && rs.queue_depth <= 0;
            }

            eval(extractFunction("web/task_parts/55-session-display-state.js", "normalizeSessionDisplayState"));
            eval(extractFunction("web/task_parts/55-session-display-state.js", "normalizeSessionHealthState"));
            eval(extractFunction("web/task_parts/55-session-display-state.js", "normalizeRunOutcomeState"));
            eval(extractFunction("web/task_parts/55-session-display-state.js", "normalizeRunSummaryBool"));
            eval(extractFunction("web/task_parts/55-session-display-state.js", "normalizeLatestRunSummary"));
            eval(extractFunction("web/task_parts/55-session-display-state.js", "normalizeLatestEffectiveRunSummary"));
            eval(extractFunction("web/task_parts/55-session-display-state.js", "getSessionLatestRunSummary"));
            eval(extractFunction("web/task_parts/55-session-display-state.js", "getSessionHealthState"));
            eval(extractFunction("web/task_parts/55-session-display-state.js", "getSessionLatestEffectiveRunSummary"));
            eval(extractFunction("web/task_parts/55-session-display-state.js", "getSessionDisplayState"));

            assert.equal(getSessionDisplayState({
              session_display_state: "done",
              runtime_state: {
                display_state: "idle",
                internal_state: "idle",
                active_run_id: "run-active",
              },
              latest_run_summary: {
                run_id: "run-old",
                status: "done",
              },
            }), "running");

            assert.equal(getSessionDisplayState({
              session_display_state: "done",
              runtime_state: {
                display_state: "idle",
                internal_state: "idle",
                queued_run_id: "run-next",
              },
              latest_run_summary: {
                run_id: "run-old",
                status: "done",
              },
            }), "queued");

            assert.equal(getSessionDisplayState({
              session_display_state: "done",
              runtime_state: {
                display_state: "idle",
                internal_state: "idle",
              },
              latest_run_summary: {
                run_id: "run-old",
                status: "done",
              },
            }), "done");

            assert.equal(getSessionDisplayState({
              session_health_state: "attention",
              runtime_state: {
                display_state: "idle",
                internal_state: "idle",
              },
              latest_run_summary: {
                run_id: "run-active",
                status: "running",
              },
              latest_effective_run_summary: {
                run_id: "run-old-interrupted",
                outcome_state: "interrupted_infra",
              },
            }), "running");

            assert.equal(getSessionDisplayState({
              session_health_state: "attention",
              runtime_state: {
                display_state: "idle",
                internal_state: "idle",
              },
              latest_run_summary: {
                run_id: "run-success",
                status: "done",
              },
              latest_effective_run_summary: {
                run_id: "run-old-interrupted",
                outcome_state: "interrupted_infra",
              },
            }), "done");

            assert.equal(getSessionDisplayState({
              session_health_state: "attention",
              runtime_state: {
                display_state: "idle",
                internal_state: "idle",
              },
              latest_run_summary: {
                run_id: "run-interrupted",
                status: "error",
              },
              latest_effective_run_summary: {
                run_id: "run-interrupted",
                outcome_state: "interrupted_infra",
              },
            }), "interrupted");
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

    def test_working_session_prefers_active_run_preview(self) -> None:
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

            function firstNonEmptyText(values) {
              const list = Array.isArray(values) ? values : [values];
              for (const value of list) {
                const text = String(value == null ? "" : value).trim();
                if (text) return text;
              }
              return "";
            }

            function normalizeSessionDisplayState(raw, fallback = "idle") {
              const text = String(raw || "").trim().toLowerCase();
              return text || String(fallback || "").trim().toLowerCase();
            }

            function getSessionLatestRunSummary(session) {
              return session.latestRunSummary || {};
            }

            function getSessionLatestEffectiveRunSummary(session) {
              return session.latestEffectiveRunSummary || {};
            }

            function getSessionDisplayState(session) {
              return session.displayState || "idle";
            }

            eval(extractFunction("web/task_parts/55-session-display-state.js", "getSessionPrimaryPreviewText"));

            const runningPreview = getSessionPrimaryPreviewText({
              displayState: "running",
              lastPreview: "旧有效摘要",
              latestEffectiveRunSummary: {
                run_id: "run-old",
                preview: "上一条已完成摘要",
              },
              latestRunSummary: {
                run_id: "run-active",
                preview: "当前 active run 的最新进展",
              },
            });
            assert.equal(runningPreview, "当前 active run 的最新进展");

            const queuedPreview = getSessionPrimaryPreviewText({
              displayState: "queued",
              lastPreview: "排队中的新消息",
              latestEffectiveRunSummary: {
                run_id: "run-old",
                preview: "上一条已完成摘要",
              },
              latestRunSummary: {
                run_id: "run-queued",
                preview: "",
              },
            });
            assert.equal(queuedPreview, "排队中的新消息");

            const idlePreview = getSessionPrimaryPreviewText({
              displayState: "done",
              lastPreview: "系统回执预览",
              latestEffectiveRunSummary: {
                run_id: "run-effective",
                preview: "最终有效业务摘要",
              },
              latestRunSummary: {
                run_id: "run-system",
                preview: "系统回执预览",
              },
            });
            assert.equal(idlePreview, "最终有效业务摘要");
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

    def test_latest_run_summary_preserves_provider_failure_fields(self) -> None:
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

            function firstNonEmptyText(values) {
              const list = Array.isArray(values) ? values : [values];
              for (const value of list) {
                const text = String(value || "").trim();
                if (text) return text;
              }
              return "";
            }

            function normalizeSessionDisplayState(raw, fallback = "idle") {
              const text = String(raw || "").trim().toLowerCase();
              return text || String(fallback || "idle").trim().toLowerCase();
            }

            function normalizeRunOutcomeState(raw, fallback = "") {
              const text = String(raw || "").trim().toLowerCase();
              if (text === "success" || text === "interrupted_infra" || text === "interrupted_user" || text === "failed_config" || text === "failed_business" || text === "provider_transient_failed" || text === "recovered_notice") return text;
              return String(fallback || "").trim().toLowerCase();
            }

            eval(extractFunction("web/task_parts/55-session-display-state.js", "normalizeRunSummaryBool"));
            eval(extractFunction("web/task_parts/55-session-display-state.js", "normalizeLatestRunSummary"));
            eval(extractFunction("web/task_parts/55-session-display-state.js", "normalizeLatestEffectiveRunSummary"));

            const latest = normalizeLatestRunSummary({
              run_id: "run-provider",
              status: "error",
              preview: "临时失败预览",
              failure_class: "provider_transient",
              provider_error: {
                kind: "rate_limit",
                retryable: true,
                matched_patterns: ["429"],
              },
              side_effect_risk: "possible",
              recovery_mode: "manual_recovery",
              recovery_required: true,
            });
            assert.equal(latest.failure_class, "provider_transient");
            assert.equal(latest.provider_error.kind, "rate_limit");
            assert.equal(latest.provider_error.retryable, true);
            assert.equal(latest.side_effect_risk, "possible");
            assert.equal(latest.recovery_mode, "manual_recovery");
            assert.equal(latest.recovery_required, true);

            const effective = normalizeLatestEffectiveRunSummary({
              run_id: "run-provider",
              outcome_state: "provider_transient_failed",
              preview: "临时失败预览",
              failure_class: "provider_transient",
              provider_error: {
                kind: "rate_limit",
                retryable: true,
              },
              side_effect_risk: "possible",
              recovery_mode: "manual_recovery",
              recovery_required: true,
            });
            assert.equal(effective.failure_class, "provider_transient");
            assert.equal(effective.provider_error.kind, "rate_limit");
            assert.equal(effective.provider_error.retryable, true);
            assert.equal(effective.recovery_required, true);

            const noRecovery = normalizeLatestRunSummary({
              provider_error: { retryable: "false" },
              recovery_required: "false",
              retry_exhausted: "false",
            });
            assert.equal(noRecovery.provider_error.retryable, false);
            assert.equal(noRecovery.recovery_required, false);
            assert.equal(noRecovery.retry_exhausted, false);
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

    def test_light_session_list_does_not_downgrade_active_state(self) -> None:
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

            function firstNonEmptyText(values) {
              const list = Array.isArray(values) ? values : [values];
              for (const value of list) {
                const text = String(value || "").trim();
                if (text) return text;
              }
              return "";
            }

            function normalizeDisplayState(raw, fallback = "idle") {
              const s = String(raw || "").trim().toLowerCase();
              if (["running", "queued", "retry_waiting", "done", "error", "idle", "external_busy"].includes(s)) {
                return s;
              }
              return String(fallback || "idle").trim().toLowerCase() || "idle";
            }

            function normalizeRuntimeState(raw) {
              const src = raw && typeof raw === "object" ? raw : {};
              const internal = normalizeDisplayState(firstNonEmptyText([src.internal_state, src.internalState, src.status]), "idle");
              const display = normalizeDisplayState(firstNonEmptyText([src.display_state, src.displayState]), internal);
              return {
                internal_state: internal,
                external_busy: !!src.external_busy,
                display_state: display,
                active_run_id: String(firstNonEmptyText([src.active_run_id, src.activeRunId]) || "").trim(),
                queued_run_id: String(firstNonEmptyText([src.queued_run_id, src.queuedRunId]) || "").trim(),
                queue_depth: Math.max(0, Number(firstNonEmptyText([src.queue_depth, src.queueDepth, 0])) || 0),
                updated_at: String(firstNonEmptyText([src.updated_at, src.updatedAt]) || "").trim(),
              };
            }

            function getSessionRuntimeState(session) {
              return normalizeRuntimeState((session && (session.runtime_state || session.runtimeState)) || null);
            }

            eval(extractFunction("web/task_parts/74-session-bootstrap-and-sessions.js", "conversationSessionStateSources"));
            eval(extractFunction("web/task_parts/74-session-bootstrap-and-sessions.js", "conversationSessionHasRuntimeStateSource"));
            eval(extractFunction("web/task_parts/74-session-bootstrap-and-sessions.js", "conversationSessionHasDisplayStateSource"));
            eval(extractFunction("web/task_parts/74-session-bootstrap-and-sessions.js", "isConversationActiveDisplayState"));
            eval(extractFunction("web/task_parts/74-session-bootstrap-and-sessions.js", "conversationSessionLatestRunSummaryForActivePreserve"));
            eval(extractFunction("web/task_parts/74-session-bootstrap-and-sessions.js", "conversationSessionHasTerminalSummaryForPreviousActive"));
            eval(extractFunction("web/task_parts/74-session-bootstrap-and-sessions.js", "conversationShouldPreserveActiveSessionState"));
            eval(extractFunction("web/task_parts/74-session-bootstrap-and-sessions.js", "preserveConversationActiveSessionStateFields"));

            const prevActive = {
              session_display_state: "running",
              session_display_reason: "runstore_active",
              runtime_state: {
                display_state: "running",
                internal_state: "running",
                active_run_id: "run-active",
              },
              latest_run_summary: {
                run_id: "run-active",
                status: "running",
                preview: "运行中预览",
              },
              latest_effective_run_summary: {
                preview: "有效运行中预览",
              },
              lastPreview: "上一轮预览",
            };
            const nextLightDirectoryRow = {
              _state_sources: {
                runtime_state: false,
                session_display_state: false,
                latest_run_summary: false,
                latest_effective_run_summary: false,
              },
              session_display_state: "idle",
              runtime_state: {
                display_state: "idle",
                internal_state: "idle",
              },
            };
            assert.equal(conversationShouldPreserveActiveSessionState(nextLightDirectoryRow, prevActive), true);
            const preservedLight = preserveConversationActiveSessionStateFields(nextLightDirectoryRow, prevActive);
            assert.equal(preservedLight.session_display_state, "running");
            assert.equal(preservedLight.session_display_reason, "runstore_active");
            assert.equal(preservedLight.runtime_state.active_run_id, "run-active");
            assert.equal(preservedLight.lastStatus, "running");
            assert.equal(preservedLight.lastPreview, "有效运行中预览");
            assert.equal(preservedLight.latest_run_summary.run_id, "run-active");

            const nextSyntheticIdleWithoutSourceMeta = {
              session_display_state: "idle",
              runtime_state: {
                display_state: "idle",
                internal_state: "idle",
              },
            };
            assert.equal(conversationShouldPreserveActiveSessionState(nextSyntheticIdleWithoutSourceMeta, prevActive), true);
            const preservedSyntheticIdle = preserveConversationActiveSessionStateFields(nextSyntheticIdleWithoutSourceMeta, prevActive);
            assert.equal(preservedSyntheticIdle.session_display_state, "running");
            assert.equal(preservedSyntheticIdle.runtime_state.active_run_id, "run-active");

            const nextRuntimeIdle = {
              _state_sources: {
                runtime_state: true,
                session_display_state: true,
              },
              session_display_state: "idle",
              runtime_state: {
                display_state: "idle",
                internal_state: "idle",
                },
            };
            assert.equal(conversationShouldPreserveActiveSessionState(nextRuntimeIdle, prevActive), true);

            const nextTerminalSameRun = {
              _state_sources: {
                runtime_state: true,
                session_display_state: true,
                latest_run_summary: true,
              },
              session_display_state: "done",
              runtime_state: {
                display_state: "idle",
                internal_state: "idle",
              },
              latest_run_summary: {
                run_id: "run-active",
                status: "done",
              },
            };
            assert.equal(conversationShouldPreserveActiveSessionState(nextTerminalSameRun, prevActive), false);
            const terminalResult = preserveConversationActiveSessionStateFields(nextTerminalSameRun, prevActive);
            assert.equal(terminalResult.session_display_state, "done");
            assert.equal(terminalResult.runtime_state.display_state, "idle");

            const nextStillActive = {
              _state_sources: {
                runtime_state: false,
                session_display_state: true,
              },
              session_display_state: "queued",
            };
            assert.equal(conversationShouldPreserveActiveSessionState(nextStillActive, prevActive), false);
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

    def test_project_runs_overlay_marks_directory_sessions_active(self) -> None:
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

            function firstNonEmptyText(values) {
              const list = Array.isArray(values) ? values : [values];
              for (const value of list) {
                const text = String(value || "").trim();
                if (text) return text;
              }
              return "";
            }

            function normalizeDisplayState(raw, fallback = "idle") {
              const s = String(raw || "").trim().toLowerCase();
              if (["running", "queued", "retry_waiting", "done", "error", "idle", "external_busy"].includes(s)) {
                return s;
              }
              return String(fallback || "idle").trim().toLowerCase() || "idle";
            }

            function getSessionRuntimeState(session) {
              const src = (session && typeof session === "object" && session.runtime_state && typeof session.runtime_state === "object")
                ? session.runtime_state
                : {};
              return {
                display_state: normalizeDisplayState(src.display_state || src.displayState, "idle"),
                internal_state: normalizeDisplayState(src.internal_state || src.internalState, "idle"),
                external_busy: !!src.external_busy,
                active_run_id: String(src.active_run_id || src.activeRunId || "").trim(),
                queued_run_id: String(src.queued_run_id || src.queuedRunId || "").trim(),
                queue_depth: Math.max(0, Number(src.queue_depth || src.queueDepth || 0) || 0),
                updated_at: String(src.updated_at || src.updatedAt || "").trim(),
              };
            }

            eval(extractFunction("web/task_parts/74-session-bootstrap-and-sessions.js", "conversationSessionStateSources"));
            eval(extractFunction("web/task_parts/74-session-bootstrap-and-sessions.js", "isConversationActiveDisplayState"));
            eval(extractFunction("web/task_parts/74-session-bootstrap-and-sessions.js", "conversationRunStatusForRuntimeOverlay"));
            eval(extractFunction("web/task_parts/74-session-bootstrap-and-sessions.js", "conversationRunIdForRuntimeOverlay"));
            eval(extractFunction("web/task_parts/74-session-bootstrap-and-sessions.js", "conversationRunIsTerminalForRuntimeOverlay"));
            eval(extractFunction("web/task_parts/74-session-bootstrap-and-sessions.js", "conversationRunSessionIdForRuntimeOverlay"));
            eval(extractFunction("web/task_parts/74-session-bootstrap-and-sessions.js", "conversationRunUpdatedAtForRuntimeOverlay"));
            eval(extractFunction("web/task_parts/74-session-bootstrap-and-sessions.js", "conversationRunTimeForRuntimeOverlay"));
            eval(extractFunction("web/task_parts/74-session-bootstrap-and-sessions.js", "conversationLatestRunBySessionFromRuns"));
            eval(extractFunction("web/task_parts/74-session-bootstrap-and-sessions.js", "conversationRuntimeOverlayBySessionFromRuns"));
            eval(extractFunction("web/task_parts/74-session-bootstrap-and-sessions.js", "conversationRuntimeOverlayStateFromEntry"));
            eval(extractFunction("web/task_parts/74-session-bootstrap-and-sessions.js", "conversationShouldClearRuntimeOverlayFromRun"));
            eval(extractFunction("web/task_parts/74-session-bootstrap-and-sessions.js", "conversationClearedRuntimeOverlayStateFromRun"));
            eval(extractFunction("web/task_parts/74-session-bootstrap-and-sessions.js", "applyConversationRuntimeOverlayFromRuns"));

            const sessions = [{
              sessionId: "session-a",
              displayName: "项目总控",
              session_display_state: "idle",
              runtime_state: {
                display_state: "idle",
                internal_state: "idle",
              },
              _state_sources: {
                runtime_state: false,
                session_display_state: false,
                latest_run_summary: false,
              },
            }];
            const runs = [{
              id: "run-active",
              sessionId: "session-a",
              status: "running",
              display_state: "running",
              updatedAt: "2026-05-14T15:02:14+0800",
              lastPreview: "正在执行",
            }, {
              id: "run-queued",
              sessionId: "session-a",
              status: "queued",
              display_state: "queued",
              updatedAt: "2026-05-14T15:04:52+0800",
              messagePreview: "下一条消息",
            }];
            const out = applyConversationRuntimeOverlayFromRuns(sessions, runs);
            assert.equal(out.length, 1);
            assert.equal(out[0].session_display_state, "running");
            assert.equal(out[0].lastStatus, "running");
            assert.equal(out[0].runtime_state.display_state, "running");
            assert.equal(out[0].runtime_state.active_run_id, "run-active");
            assert.equal(out[0].runtime_state.queued_run_id, "run-queued");
            assert.equal(out[0].runtime_state.queue_depth, 1);
            assert.equal(out[0]._state_sources.runtime_state, true);
            assert.equal(out[0]._state_sources.session_display_state, true);
            assert.equal(out[0]._state_sources.latest_run_summary, true);
            assert.equal(out[0].latest_run_summary.run_id, "run-active");

            const staleSessions = [{
              sessionId: "session-b",
              displayName: "沙盘-业务规划",
              session_display_state: "running",
              runtime_state: {
                display_state: "running",
                internal_state: "running",
                active_run_id: "run-old",
                updated_at: "2026-05-14T15:59:00+0800",
              },
              latest_run_summary: {
                run_id: "run-old",
                status: "running",
              },
              _state_sources: {
                runtime_state: true,
                session_display_state: true,
                latest_run_summary: true,
              },
            }];
            const terminalRuns = [{
              id: "run-old",
              sessionId: "session-b",
              status: "done",
              createdAt: "2026-05-14T16:03:59+0800",
              lastPreview: "已完成",
            }];
            const cleared = applyConversationRuntimeOverlayFromRuns(staleSessions, terminalRuns);
            assert.equal(cleared.length, 1);
            assert.equal(cleared[0].session_display_state, "idle");
            assert.equal(cleared[0].runtime_state.display_state, "idle");
            assert.equal(cleared[0].runtime_state.active_run_id, "");
            assert.equal(cleared[0].lastStatus, "idle");
            assert.equal(cleared[0].latest_run_summary.run_id, "run-old");
            assert.equal(cleared[0].latest_run_summary.status, "done");
            assert.equal(cleared[0]._state_sources.runtime_state, true);
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

    def test_detail_merge_does_not_mutate_session_directory_for_left_list(self) -> None:
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

            function firstNonEmptyText(values, fallback = "") {
              const list = Array.isArray(values) ? values : [values];
              for (const value of list) {
                const text = String(value || "").trim();
                if (text) return text;
              }
              return fallback;
            }

            global.STATE = { project: "ndt", selectedSessionId: "session-a" };
            global.PCONV = {
              sessions: [{
                sessionId: "session-a",
                id: "session-a",
                project_id: "ndt",
                channel_name: "开发01",
                session_display_state: "idle",
                runtime_state: { display_state: "idle", internal_state: "idle" },
              }],
              sessionDirectoryByProject: {
                ndt: [{
                  sessionId: "session-a",
                  id: "session-a",
                  project_id: "ndt",
                  channel_name: "开发01",
                  session_display_state: "idle",
                  runtime_state: { display_state: "idle", internal_state: "idle" },
                }],
              },
              sessionDirectoryMetaByProject: {},
            };
            function getSessionId(s) { return String((s && (s.sessionId || s.id)) || ""); }
            function findConversationSessionById(sid) {
              return PCONV.sessions.find((row) => getSessionId(row) === sid) || null;
            }
            function normalizeSessionModel(raw) { return String(raw || ""); }
            function normalizeReasoningEffort(raw) { return String(raw || ""); }
            function hasConversationTaskTrackingData() { return false; }
            function ensureConversationSessionDetailStateMaps() {
              PCONV.sessionDetailLoadedAtById = PCONV.sessionDetailLoadedAtById || {};
              PCONV.sessionDetailErrorById = PCONV.sessionDetailErrorById || {};
            }
            function ensureConversationSessionDirectoryStateMaps() {
              PCONV.sessionDirectoryByProject = PCONV.sessionDirectoryByProject || {};
              PCONV.sessionDirectoryMetaByProject = PCONV.sessionDirectoryMetaByProject || {};
            }
            function normalizeConversationSession(raw) {
              const src = raw && typeof raw === "object" ? raw : {};
              const sid = String(src.sessionId || src.id || "");
              return { ...src, sessionId: sid, id: sid };
            }
            function preserveConversationSessionDetailFields(next, prev) {
              return { ...(prev || {}), ...(next || {}) };
            }

            eval(extractFunction("web/task_parts/74-session-bootstrap-and-sessions.js", "mergeConversationSessionDetailIntoStore"));

            const merged = mergeConversationSessionDetailIntoStore({
              id: "session-a",
              project_id: "ndt",
              channel_name: "开发01",
              session_display_state: "running",
              session_display_reason: "runtime_state:running",
              runtime_state: {
                display_state: "running",
                internal_state: "running",
                active_run_id: "run-active",
              },
            }, "session-a");

            assert.equal(merged.session_display_state, "running");
            assert.equal(PCONV.sessions[0].runtime_state.active_run_id, "run-active");
            assert.equal(PCONV.sessionDirectoryByProject.ndt[0].session_display_state, "idle");
            assert.equal(PCONV.sessionDirectoryByProject.ndt[0].runtime_state.active_run_id, undefined);
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
