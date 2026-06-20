import shutil
import subprocess
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("node"), "node is required for UI logic regression checks")
class ProviderTransientFailureUiLogicTests(unittest.TestCase):
    def test_provider_transient_failure_copy_does_not_read_as_business_failure(self) -> None:
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
                const text = String(value || "").trim();
                if (text) return text;
              }
              return "";
            };
            global.normalizeDisplayState = (raw, fallback = "idle") => {
              const text = String(raw || "").trim().toLowerCase();
              if (["running", "queued", "retry_waiting", "done", "error", "idle", "external_busy"].includes(text)) return text;
              return String(fallback || "idle").trim().toLowerCase() || "idle";
            };
            global.parseDateTime = (raw) => {
              const d = new Date(String(raw || ""));
              return Number.isNaN(d.getTime()) ? null : d;
            };
            global.toTimeNum = (raw) => {
              const d = new Date(String(raw || ""));
              const ts = d.getTime();
              return Number.isFinite(ts) ? ts : -1;
            };
            var RUN_PROGRESS_STALE_THRESHOLD_MS = 5 * 60 * 1000;

            eval(extractFunction("web/task_parts/55-session-display-state.js", "normalizeRunOutcomeState"));
            eval(extractFunction("web/task_parts/55-session-display-state.js", "normalizeRunErrorClass"));
            eval(extractFunction("web/task_parts/76-runs-and-drawer.js", "normalizeProcessTimestamp"));
            eval(extractFunction("web/task_parts/76-runs-and-drawer.js", "extractProcessItemTimestamp"));
            eval(extractFunction("web/task_parts/76-runs-and-drawer.js", "isProgressStale"));
            eval(extractFunction("web/task_parts/76-runs-and-drawer.js", "deriveRunStateFromSource"));
            eval(extractFunction("web/task_parts/76-runs-and-drawer.js", "runSourceProgressTs"));
            eval(extractFunction("web/task_parts/76-runs-and-drawer.js", "processRowProgressTs"));
            eval(extractFunction("web/task_parts/76-runs-and-drawer.js", "runSourceProcessProgressTs"));
            eval(extractFunction("web/task_parts/76-runs-and-drawer.js", "runSourceContinuingProgressTs"));
            eval(extractFunction("web/task_parts/76-runs-and-drawer.js", "latestRunProgressTs"));
            eval(extractFunction("web/task_parts/76-runs-and-drawer.js", "latestRunTerminalTs"));
            eval(extractFunction("web/task_parts/76-runs-and-drawer.js", "runSourceFinishedTs"));
            eval(extractFunction("web/task_parts/76-runs-and-drawer.js", "detailFetchedTs"));
            eval(extractFunction("web/task_parts/76-runs-and-drawer.js", "shouldPreferDetailSnapshot"));
            eval(extractFunction("web/task_parts/76-runs-and-drawer.js", "isRunWorking"));
            eval(extractFunction("web/task_parts/76-runs-and-drawer.js", "isWorkingLikeState"));
            eval(extractFunction("web/task_parts/76-runs-and-drawer.js", "isInterruptedByUserText"));
            eval(extractFunction("web/task_parts/76-runs-and-drawer.js", "isRunInterruptedByUser"));
            eval(extractFunction("web/task_parts/76-runs-and-drawer.js", "getRunOutcomeState"));
            eval(extractFunction("web/task_parts/76-runs-and-drawer.js", "getRunErrorClass"));
            eval(extractFunction("web/task_parts/76-runs-and-drawer.js", "getRunFailureClass"));
            eval(extractFunction("web/task_parts/76-runs-and-drawer.js", "getRunProviderError"));
            eval(extractFunction("web/task_parts/76-runs-and-drawer.js", "getRunProviderFailureDisplay"));
            eval(extractFunction("web/task_parts/76-runs-and-drawer.js", "shouldSuppressRunInterruptedInfra"));
            eval(extractFunction("web/task_parts/76-runs-and-drawer.js", "buildRunOutcomeMeta"));
            eval(extractFunction("web/task_parts/76-runs-and-drawer.js", "getRunDisplayStateSourceMeta"));
            eval(extractFunction("web/task_parts/76-runs-and-drawer.js", "getRunDisplayState"));
            eval(extractFunction("web/task_parts/76-runs-and-drawer.js", "runErrorDisplayText"));
            eval(extractFunction("web/task_parts/76-runs-and-drawer.js", "runStateHeadline"));

            const providerRun = {
              status: "error",
              outcome_state: "provider_transient_failed",
              error_class: "provider_transient",
              failure_class: "provider_transient",
              provider_error: {
                kind: "high_demand",
                retryable: true,
                matched_patterns: ["high demand", "temporary errors"],
              },
              error: "turn.failed: We're currently experiencing high demand, which may cause temporary errors.",
            };
            const meta = buildRunOutcomeMeta(providerRun, null);
            assert.equal(meta.label, "模型服务高负载");
            assert.equal(meta.providerTransient, true);
            assert.match(meta.subtitle, /不是业务处理失败/);
            assert.match(meta.subtitle, /补链恢复/);
            assert.equal(runStateHeadline("error", { outcomeState: meta.outcomeState, providerHeadline: meta.headline }), "模型服务高负载");
            assert.match(runErrorDisplayText(providerRun.error, meta), /模型服务高负载/);
            assert.match(runErrorDisplayText(providerRun.error, meta), /不是业务处理失败/);

            const businessMeta = buildRunOutcomeMeta({
              status: "error",
              outcome_state: "failed_business",
              error_class: "",
              error: "pytest failed",
            }, null);
            assert.equal(businessMeta.label, "业务失败");
            assert.equal(runStateHeadline("error", { outcomeState: businessMeta.outcomeState }), "业务失败");
            assert.match(runErrorDisplayText("pytest failed", businessMeta), /^error: pytest failed/);

            const nowIso = new Date().toISOString();
            const oldIso = new Date(Date.now() - 10 * 60 * 1000).toISOString();
            const runningInterruptedInfra = {
              status: "running",
              outcome_state: "interrupted_infra",
              error_class: "infra_restart",
              updatedAt: nowIso,
            };
            assert.equal(getRunDisplayState(runningInterruptedInfra, null), "running");
            assert.equal(buildRunOutcomeMeta(runningInterruptedInfra, null), null);

            const recentProgressInterruptedInfra = {
              status: "error",
              outcome_state: "interrupted_infra",
              error_class: "infra_restart",
              finishedAt: oldIso,
              processRows: [
                { text: "执行命令: node --check", at: nowIso, event_type: "command_execution" },
              ],
            };
            assert.equal(getRunDisplayState(recentProgressInterruptedInfra, null), "running");
            assert.equal(buildRunOutcomeMeta(recentProgressInterruptedInfra, null), null);

            const terminalInterruptedInfra = {
              status: "error",
              outcome_state: "interrupted_infra",
              error_class: "infra_restart",
              finishedAt: oldIso,
              updatedAt: oldIso,
            };
            assert.equal(getRunDisplayState(terminalInterruptedInfra, null), "interrupted");
            assert.equal(buildRunOutcomeMeta(terminalInterruptedInfra, null).label, "环境中断");

            const freshTerminalWithoutProgress = {
              status: "error",
              outcome_state: "interrupted_infra",
              error_class: "infra_restart",
              createdAt: nowIso,
            };
            assert.equal(getRunDisplayState(freshTerminalWithoutProgress, null), "interrupted");
            assert.equal(buildRunOutcomeMeta(freshTerminalWithoutProgress, null).label, "环境中断");

            const terminalClaudeRun = {
              id: "20260616-140857-4ec798c9",
              cliType: "claude",
              status: "done",
              display_state: "done",
              outcome_state: "success",
              finishedAt: "2026-06-16T14:10:54+08:00",
              updatedAt: "2026-06-16T14:10:54+08:00",
            };
            const staleRunningDetail = {
              fetchedAt: Date.parse("2026-06-16T14:11:12+08:00"),
              full: {
                run: {
                  status: "running",
                  display_state: "running",
                  updatedAt: "2026-06-16T14:10:53+08:00",
                },
              },
            };
            assert.equal(shouldPreferDetailSnapshot(terminalClaudeRun, staleRunningDetail.full.run, staleRunningDetail), true);
            assert.equal(getRunDisplayState(terminalClaudeRun, staleRunningDetail), "done");
            assert.equal(getRunDisplayStateSourceMeta(terminalClaudeRun, staleRunningDetail).text, "状态来源: 时间线");

            const terminalProviderRun = {
              status: "error",
              display_state: "error",
              outcome_state: "provider_transient_failed",
              error_class: "provider_transient",
              finishedAt: "2026-06-16T14:12:54+08:00",
            };
            assert.equal(getRunDisplayState(terminalProviderRun, staleRunningDetail), "error");

            const providerVariants = [
              ["model_capacity", "模型容量不足", {
                status: "error",
                outcome_state: "provider_transient_failed",
                error_class: "provider_transient",
                failure_class: "provider_transient",
                provider_error: { kind: "model_capacity", retryable: true, matched_patterns: ["MODEL_CAPACITY_EXHAUSTED"] },
                error: "Gemini returned RESOURCE_EXHAUSTED: MODEL_CAPACITY_EXHAUSTED",
              }],
              ["rate_limit", "模型服务限流", {
                status: "error",
                outcome_state: "provider_transient_failed",
                error_class: "provider_transient",
                failure_class: "provider_transient",
                provider_error: { kind: "rate_limit", retryable: true, matched_patterns: ["429"] },
                error: "OpenAI request failed with HTTP 429 Too Many Requests",
              }],
              ["server_error", "模型服务 5xx", {
                status: "error",
                outcome_state: "provider_transient_failed",
                error_class: "provider_transient",
                failure_class: "provider_transient",
                provider_error: { kind: "server_error", retryable: true, matched_patterns: ["503 service unavailable"] },
                error: "provider returned 503 service unavailable",
              }],
              ["network_timeout", "网络超时", {
                status: "error",
                outcome_state: "provider_transient_failed",
                error_class: "provider_transient",
                failure_class: "provider_transient",
                provider_error: { kind: "network_timeout", retryable: true, matched_patterns: ["request timed out"] },
                error: "responses_websocket request timed out",
              }],
              ["network_reset", "网络中断", {
                status: "error",
                outcome_state: "provider_transient_failed",
                error_class: "provider_transient",
                failure_class: "provider_transient",
                provider_error: { kind: "network_reset", retryable: true, matched_patterns: ["connection reset by peer"] },
                error: "stream disconnected before completion: connection reset by peer",
              }],
              ["upstream_unavailable", "上游不可用", {
                status: "error",
                outcome_state: "provider_transient_failed",
                error_class: "provider_transient",
                failure_class: "provider_transient",
                provider_error: { kind: "upstream_unavailable", retryable: true, matched_patterns: ["temporarily unavailable"] },
                error: "upstream temporarily unavailable",
              }],
            ];
            for (const [kind, expectedLabel, run] of providerVariants) {
              const variantMeta = buildRunOutcomeMeta(run, null);
              assert.equal(variantMeta.providerTransient, true, kind);
              assert.equal(variantMeta.label, expectedLabel, kind);
              assert.equal(runStateHeadline("error", { outcomeState: variantMeta.outcomeState, providerHeadline: variantMeta.headline }), expectedLabel, kind);
              assert.ok(runErrorDisplayText(run.error, variantMeta).includes(expectedLabel), kind);
              assert.match(runErrorDisplayText(run.error, variantMeta), /不是业务处理失败/);
            }
            """
        )
        proc = subprocess.run(
            ["node", "-e", script, str(REPO_ROOT)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            self.fail(proc.stderr or proc.stdout or "node provider transient UI regression script failed")


if __name__ == "__main__":
    unittest.main()
