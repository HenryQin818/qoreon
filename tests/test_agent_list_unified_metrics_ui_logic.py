import shutil
import subprocess
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("node"), "node is required for UI logic regression checks")
class AgentListUnifiedMetricsUiLogicTests(unittest.TestCase):
    def test_agent_list_consumes_unified_metrics_without_detail_hydration(self) -> None:
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

            global.firstNonEmptyText = (values, fallback = "") => {
              for (const value of values || []) {
                const text = String(value || "").trim();
                if (text) return text;
              }
              return fallback;
            };
            global.getSessionId = (session) => String((session && (session.id || session.sessionId || session.session_id)) || "");
            global.getSessionRuntimeState = (session) => (session && session.runtime_state) || {
              display_state: "idle",
              queue_depth: 0,
              active_run_id: "",
              queued_run_id: "",
              updated_at: "",
            };
            global.getSessionStatus = (session) => String((session && session.__status) || "idle");
            global.getSessionHealthState = () => "";
            global.getSessionLatestRunSummary = () => ({});
            global.getSessionLatestEffectiveRunSummary = () => ({});
            global.normalizeRunOutcomeState = () => "";
            global.normalizeDisplayState = (value, fallback = "idle") => String(value || fallback || "idle");
            global.sessionHasTimeoutState = () => false;
            global.statusLabel = (value) => ({
              running: "处理中",
              queued: "排队",
              retry_waiting: "等待重试",
              external_busy: "外部占用",
            }[String(value || "")] || String(value || ""));
            global.shortId = (value) => String(value || "").slice(0, 6);
            global.compactDateTime = (value) => String(value || "");
            global.getSessionDisplayReason = () => "";
            global.sessionTimeoutHint = () => "";
            global.PCONV = { sessionDetailLoadedAtById: Object.create(null) };
            global.STATE = { project: "task_dashboard" };
            global.hasConversationTaskTrackingData = () => false;
            global.countConversationAssociatedTasks = () => {
              throw new Error("detail task tracking should not be used when list metrics exist");
            };

            const helperFile = "web/task_parts/55-session-display-state.js";
            eval(extractFunction(helperFile, "getConversationListMetrics"));
            eval(extractFunction(helperFile, "getConversationListTaskCounts"));
            eval(extractFunction(helperFile, "getConversationListCurrentTaskSummary"));
            eval(extractFunction(helperFile, "normalizeConversationListMetricBadge"));
            eval(extractFunction(helperFile, "conversationListMetricBadges"));
            eval(extractFunction(helperFile, "conversationListMetricBadgeTone"));
            eval(extractFunction(helperFile, "pickConversationListPrimaryStatusBadge"));
            eval(extractFunction(helperFile, "conversationListMetricBadgeStatusMeta"));
            eval(extractFunction(helperFile, "conversationListCurrentTaskSummaryMeta"));
            eval(extractFunction(helperFile, "conversationListDetailHydrationCanSkip"));

            const bootstrapFile = "web/task_parts/74-session-bootstrap-and-sessions.js";
            eval(extractFunction(bootstrapFile, "normalizeConversationListMetricsClient"));
            eval(extractFunction(bootstrapFile, "hasConversationListMetricsClientData"));
            eval(extractFunction(bootstrapFile, "mergeConversationListMetricsClient"));

            eval(extractFunction("web/task.js", "conversationTaskCountsKnownForSession"));
            eval(extractFunction("web/task.js", "conversationTaskCountsForSession"));
            eval(extractFunction("web/task.js", "conversationStatusMeta"));

            const session = {
              id: "sid-1",
              conversation_list_metrics: {
                task_counts: { total: 2, current: 1, in_progress: 1, pending: 1 },
                current_task_summary: {
                  task_id: "TASK-1",
                  task_title: "【进行中】【任务】统一指标恢复",
                  task_primary_status: "进行中",
                  status_bucket: "in_progress",
                  task_path: "任务规划/x.md",
                },
                status_badges: [
                  { kind: "current_task", state: "in_progress", label: "进行中", severity: "info" },
                  { kind: "task_count", state: "in_progress", label: "中1", severity: "info", count: 1 },
                  { kind: "task_count", state: "pending", label: "待1", severity: "warning", count: 1 },
                ],
                detail_hydration: { can_skip_detail_for_list: true },
              },
            };

            assert.equal(conversationTaskCountsKnownForSession(session), true);
            assert.deepEqual(conversationTaskCountsForSession(session, "task_dashboard"), {
              in_progress: 1,
              pending: 1,
            });
            assert.equal(conversationListDetailHydrationCanSkip(session), true);
            assert.equal(conversationStatusMeta(session).text, "进行中");
            assert.equal(conversationStatusMeta(session).source, "conversation_list_metrics");
            assert.deepEqual(
              mergeConversationListMetricsClient(null, session.conversation_list_metrics).task_counts,
              session.conversation_list_metrics.task_counts
            );

            const activeSession = {
              ...session,
              __status: "running",
              runtime_state: {
                display_state: "running",
                queue_depth: 0,
                active_run_id: "run-active",
                queued_run_id: "",
                updated_at: "2026-04-12T01:00:00+08:00",
              },
              conversation_list_metrics: {
                ...session.conversation_list_metrics,
                status_badges: [
                  { kind: "current_task", state: "done", label: "已完成", severity: "success" },
                ],
              },
            };
            assert.equal(conversationStatusMeta(activeSession).text, "处理中");

            const taskSource = fs.readFileSync(path.join(repoRoot, "web/task.js"), "utf8");
            const bootstrapSource = fs.readFileSync(path.join(repoRoot, bootstrapFile), "utf8");
            assert.equal(taskSource.includes("getConversationListTaskCounts(s)"), true);
            assert.equal(taskSource.includes("conversationListMetricBadgeStatusMeta(s)"), true);
            assert.equal(taskSource.includes("appendConversationListMetricSubchips(metaRow, session)"), true);
            assert.equal(bootstrapSource.includes("conversation_list_metrics: normalizeConversationListMetricsClient"), true);
            assert.equal(bootstrapSource.includes("conversation_list_metrics: mergeConversationListMetricsClient"), true);
            """
        )
        proc = subprocess.run(
            ["node", "-e", script, str(REPO_ROOT)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            self.fail(proc.stderr or proc.stdout or "node agent list unified metrics regression script failed")


if __name__ == "__main__":
    unittest.main()
