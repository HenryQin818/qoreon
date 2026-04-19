import shutil
import subprocess
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("node"), "node is required for UI logic regression checks")
class ActiveConversationStreamUiLogicTests(unittest.TestCase):
    def test_session_snapshot_projection_updates_active_session_and_timeline(self) -> None:
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

            global.PCONV = {
              sessionTimelineMap: Object.create(null),
              runsBySession: Object.create(null),
              processTrailByRun: Object.create(null),
            };
            global.STATE = { panelMode: "conv", project: "task_dashboard", selectedSessionId: "sid-1" };
            global.firstNonEmptyText = (values, fallback = "") => {
              for (const value of values || []) {
                const text = String(value || "").trim();
                if (text) return text;
              }
              return fallback;
            };
            global.normalizeDisplayState = (value, fallback = "idle") => {
              const text = String(value || "").trim().toLowerCase();
              if (["running", "queued", "retry_waiting", "done", "error", "idle", "external_busy"].includes(text)) return text;
              return String(fallback || "idle").trim().toLowerCase() || "idle";
            };
            global.isRunWorking = (value) => ["running", "queued", "retry_waiting", "external_busy"].includes(String(value || "").trim().toLowerCase());
            global.conversationStoreNowIso = () => "2026-04-12T12:30:00+0800";
            global.normalizeConversationTaskRef = (raw) => raw && raw.task_id ? { ...raw } : null;
            global.normalizeTaskTrackingClient = (raw) => raw && raw.current_task_ref ? { current_task_ref: { ...raw.current_task_ref }, updated_at: raw.updated_at || "" } : null;
            global.mergeRunsById = (existingRuns, incomingRuns) => {
              const map = new Map();
              for (const run of existingRuns || []) map.set(String(run.id || ""), { ...run });
              for (const run of incomingRuns || []) map.set(String(run.id || ""), { ...(map.get(String(run.id || "")) || {}), ...run });
              return Array.from(map.values()).sort((a, b) => String(b.createdAt || "").localeCompare(String(a.createdAt || "")));
            };
            let mergedSessionPatch = null;
            let leftListRefreshCount = 0;
            global.mergeConversationSessionDetailIntoStore = (patch) => {
              mergedSessionPatch = patch;
              return patch;
            };
            global.conversationStoreUpsertRuns = () => {};
            global.primeConversationHistoryFromRuns = () => {};
            global.conversationStoreUpsertSession = () => {};
            global.isFocusedConversationSession = () => true;
            global.buildConversationLeftList = () => { leftListRefreshCount += 1; };

            const file = "web/task_parts/64-conversation-stream.js";
            eval(extractFunction(file, "normalizeConversationProjectionRunItem"));
            eval(extractFunction(file, "buildConversationProjectionRuntimeState"));
            eval(extractFunction(file, "buildConversationProjectionTaskTracking"));
            eval(extractFunction(file, "installConversationProjectionRuns"));
            eval(extractFunction(file, "applyConversationProjectionSnapshot"));

            const ok = applyConversationProjectionSnapshot("task_dashboard", "sid-1", {
              summary: {
                display_state: "running",
                display_reason: "history_lite:running",
                latest_run_id: "run-1",
              },
              items: [
                {
                  entity_type: "session_summary",
                  status: "running",
                  run_id: "run-1",
                  current_task_ref: {
                    task_id: "TASK-1",
                    task_title: "【进行中】【任务】活跃状态修复",
                    task_primary_status: "进行中",
                    task_summary_text: "当前正在补前端活跃态接线",
                  },
                },
                {
                  entity_type: "run_message",
                  run_id: "run-1",
                  status: "running",
                  message_preview: "请继续处理",
                  response_preview: "第一条过程消息",
                  created_at: "2026-04-12T12:29:00+0800",
                  updated_at: "2026-04-12T12:30:00+0800",
                },
              ],
            }, { source: "ws-snapshot" });

            assert.equal(ok, true);
            assert.equal(mergedSessionPatch.runtime_state.display_state, "running");
            assert.equal(mergedSessionPatch.runtime_state.active_run_id, "run-1");
            assert.equal(mergedSessionPatch.task_tracking.current_task_ref.task_id, "TASK-1");
            assert.equal(PCONV.sessionTimelineMap["task_dashboard::sid-1"][0].partialPreview, "第一条过程消息");
            assert.equal(PCONV.processTrailByRun["run-1"].rows[0].text, "第一条过程消息");
            assert.equal(leftListRefreshCount, 1);
            """
        )
        proc = subprocess.run(
            ["node", "-e", script, str(REPO_ROOT)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            self.fail(proc.stderr or proc.stdout or "node session snapshot projection regression script failed")

    def test_current_task_payload_falls_back_to_unified_current_task_summary(self) -> None:
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

            global.normalizeConversationTaskRef = (raw, relation = "tracking") => {
              if (!raw || typeof raw !== "object" || !String(raw.task_id || raw.task_path || raw.task_title || "").trim()) return null;
              return {
                task_id: String(raw.task_id || ""),
                task_path: String(raw.task_path || ""),
                task_title: String(raw.task_title || ""),
                task_primary_status: String(raw.task_primary_status || ""),
                task_summary_text: String(raw.task_summary_text || ""),
                latest_action_at: String(raw.latest_action_at || ""),
                relation,
              };
            };
            global.firstNonEmptyText = (values, fallback = "") => {
              for (const value of values || []) {
                const text = String(value || "").trim();
                if (text) return text;
              }
              return fallback;
            };
            global.resolveTaskPrimaryStatusText = (value, fallback = "") => {
              const text = String(value || "").trim();
              if (!text) return String(fallback || "").trim();
              if (/(?:进行中|处理中|running|in[_-]?progress)/i.test(text)) return "进行中";
              if (/(?:待办|待开始|待处理|todo|pending|queued)/i.test(text)) return "待办";
              if (/(?:已完成|完成|done)/i.test(text)) return "已完成";
              return String(fallback || text).trim();
            };
            global.normalizeTaskTrackingClient = (raw) => {
              if (!raw || typeof raw !== "object") return null;
              const current = global.normalizeConversationTaskRef(raw.current_task_ref || null, "current");
              if (!current) return null;
              return {
                current_task_ref: current,
                conversation_task_refs: [],
                recent_task_actions: [],
                updated_at: String(raw.updated_at || ""),
              };
            };
            global.conversationTaskStableKey = (row) => String((row && (row.task_id || row.task_path || row.task_title)) || "");
            global.buildConversationTaskActionSummaryMap = () => new Map();
            global.mergeConversationTaskActivity = (row) => row;

            const file = "web/task_parts/60-conversation.js";
            eval(extractFunction(file, "resolveConversationTaskTrackingPayload"));

            const payload = resolveConversationTaskTrackingPayload({
              taskTracking: null,
              currentTaskSummary: {
                task_id: "TASK-2",
                task_title: "【进行中】【任务】统一读源当前任务条回退",
                task_primary_status: "进行中",
                task_summary_text: "当前任务状态来自 conversation_list_metrics.current_task_summary",
                latest_action_at: "2026-04-12T12:40:00+0800",
              },
              currentTaskUpdatedAt: "2026-04-12T12:40:00+0800",
            });

            assert.equal(payload.currentRef.task_id, "TASK-2");
            assert.equal(payload.currentRef.task_primary_status, "进行中");
            assert.equal(payload.tracking.current_task_ref.task_id, "TASK-2");
            assert.equal(payload.relatedRows.length, 0);
            """
        )
        proc = subprocess.run(
            ["node", "-e", script, str(REPO_ROOT)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            self.fail(proc.stderr or proc.stdout or "node current task summary fallback regression script failed")

    def test_unified_current_task_status_bucket_is_localized_for_task_strip_and_badge(self) -> None:
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
            global.resolveTaskPrimaryStatusText = (value, fallback = "") => {
              const text = String(value || "").trim();
              if (!text) return String(fallback || "").trim();
              if (/(?:进行中|处理中|running|in[_-]?progress)/i.test(text)) return "进行中";
              if (/(?:待办|待开始|待处理|todo|pending|queued)/i.test(text)) return "待办";
              if (/(?:已完成|完成|done)/i.test(text)) return "已完成";
              return String(fallback || text).trim();
            };

            const file = "web/task_parts/55-session-display-state.js";
            eval(extractFunction(file, "getConversationListMetrics"));
            eval(extractFunction(file, "getConversationListCurrentTaskSummary"));
            eval(extractFunction(file, "normalizeConversationListMetricBadge"));

            const session = {
              conversation_list_metrics: {
                current_task_summary: {
                  task_path: "任务规划/task_20260412_active_agent_status_and_incremental_message_display_fix",
                  task_title: "task_20260412_active_agent_status_and_incremental_message_display_fix",
                  status_bucket: "in_progress",
                },
                status_badges: [
                  {
                    kind: "current_task",
                    state: "in_progress",
                    label: "in_progress",
                    severity: "info",
                  },
                ],
              },
            };

            const summary = getConversationListCurrentTaskSummary(session);
            const badge = normalizeConversationListMetricBadge(session.conversation_list_metrics.status_badges[0]);

            assert.equal(summary.task_primary_status, "进行中");
            assert.equal(badge.label, "进行中");
            """
        )
        proc = subprocess.run(
            ["node", "-e", script, str(REPO_ROOT)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            self.fail(proc.stderr or proc.stdout or "node unified current task status bucket regression script failed")

    def test_current_task_summary_overrides_stale_detail_current_task_ref(self) -> None:
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
            global.resolveTaskPrimaryStatusText = (value, fallback = "") => {
              const text = String(value || "").trim();
              if (!text) return String(fallback || "").trim();
              if (/(?:进行中|处理中|running|in[_-]?progress)/i.test(text)) return "进行中";
              if (/(?:已完成|完成|done)/i.test(text)) return "已完成";
              if (/(?:待办|待开始|待处理|todo|pending|queued)/i.test(text)) return "待办";
              return String(fallback || text).trim();
            };
            global.normalizeConversationTaskRef = (raw, relation = "tracking") => {
              if (!raw || typeof raw !== "object" || !String(raw.task_id || raw.task_path || raw.task_title || "").trim()) return null;
              return {
                task_id: String(raw.task_id || ""),
                task_path: String(raw.task_path || ""),
                task_title: String(raw.task_title || ""),
                task_primary_status: String(raw.task_primary_status || ""),
                task_summary_text: String(raw.task_summary_text || ""),
                latest_action_at: String(raw.latest_action_at || ""),
                latest_action_kind: String(raw.latest_action_kind || ""),
                latest_action_text: String(raw.latest_action_text || ""),
                relation,
              };
            };
            global.normalizeTaskTrackingClient = (raw) => {
              if (!raw || typeof raw !== "object") return null;
              const current = global.normalizeConversationTaskRef(raw.current_task_ref || null, "current");
              return {
                version: String(raw.version || "v1.1"),
                current_task_ref: current,
                conversation_task_refs: Array.isArray(raw.conversation_task_refs) ? raw.conversation_task_refs.map((row) => global.normalizeConversationTaskRef(row, "tracking")).filter(Boolean) : [],
                recent_task_actions: Array.isArray(raw.recent_task_actions) ? raw.recent_task_actions.slice() : [],
                updated_at: String(raw.updated_at || ""),
              };
            };
            global.conversationTaskStableKey = (row) => {
              const taskId = String((row && row.task_id) || "").trim();
              if (taskId) return "task_id::" + taskId;
              const taskPath = String((row && row.task_path) || "").trim();
              if (taskPath) return "task_path::" + taskPath;
              return "";
            };
            global.buildConversationTaskActionSummaryMap = () => Object.create(null);
            global.mergeConversationTaskActivity = (row) => row;

            const file = "web/task_parts/60-conversation.js";
            eval(extractFunction(file, "resolveConversationTaskTrackingPayload"));

            const payload = resolveConversationTaskTrackingPayload({
              taskTracking: {
                version: "v1.1",
                current_task_ref: {
                  task_id: "TASK-OLD",
                  task_title: "【已完成】【任务】旧冻结任务",
                  task_primary_status: "已完成",
                  task_summary_text: "旧 detail 当前任务",
                  latest_action_at: "2026-04-10T23:32:02+0800",
                },
                updated_at: "2026-04-12T13:28:26+0800",
              },
              currentTaskSummary: {
                task_id: "TASK-NEW",
                task_title: "【进行中】【任务】当前Agent活跃状态与过程消息增量展示修复",
                task_primary_status: "进行中",
                task_summary_text: "统一读源已切到当前运行态任务",
                latest_action_at: "2026-04-12T13:23:07+0800",
              },
              currentTaskUpdatedAt: "2026-04-12T13:23:07+0800",
            });

            assert.equal(payload.currentRef.task_id, "TASK-NEW");
            assert.equal(payload.currentRef.task_primary_status, "进行中");
            assert.equal(payload.currentRef.task_summary_text, "统一读源已切到当前运行态任务");
            assert.equal(payload.tracking.current_task_ref.task_id, "TASK-NEW");
            assert.equal(payload.tracking.current_task_ref.relation, "current");
          """
        )
        proc = subprocess.run(
            ["node", "-e", script, str(REPO_ROOT)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            self.fail(proc.stderr or proc.stdout or "node stale detail current task override regression script failed")


if __name__ == "__main__":
    unittest.main()
