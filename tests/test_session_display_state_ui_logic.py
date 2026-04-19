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
                const text = String(value || "").trim();
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

            const prevActive = {
              session_display_state: "running",
              runtime_state: {
                display_state: "running",
                internal_state: "running",
                active_run_id: "run-active",
              },
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


if __name__ == "__main__":
    unittest.main()
