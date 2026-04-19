import shutil
import subprocess
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SESSION_UI_FILE = REPO_ROOT / "web" / "task_entry_parts" / "81-session-info-and-bindings.js"


@unittest.skipUnless(shutil.which("node"), "node is required for UI logic regression checks")
class SessionHeartbeatUiLogicTests(unittest.TestCase):
    def test_session_heartbeat_draft_roundtrip_keeps_session_scope(self) -> None:
        script = textwrap.dedent(
            r"""
            const assert = require("node:assert/strict");
            const fs = require("node:fs");
            const path = require("node:path");

            const repoRoot = process.argv[1];

            function extractFunction(file, name) {
              const text = fs.readFileSync(path.join(repoRoot, file), "utf8");
              const signature = `function ${name}(`;
              const start = text.indexOf(signature);
              if (start < 0) {
                throw new Error(`missing function ${name} in ${file}`);
              }
              const headerMatch = text
                .slice(start)
                .match(new RegExp(`function ${name}\\([^\\n]*\\)\\s*\\{`));
              if (!headerMatch) {
                throw new Error(`missing function header for ${name} in ${file}`);
              }
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
                  if (depth === 0) {
                    return text.slice(start, i + 1);
                  }
                }
              }
              throw new Error(`unterminated function ${name} in ${file}`);
            }

            function firstNonEmptyText(values) {
              const list = Array.isArray(values) ? values : [values];
              for (const value of list) {
                if (value == null) continue;
                const text = String(value).trim();
                if (text) return text;
              }
              return "";
            }

            function normalizeHeartbeatWeekdaysClient(raw) {
              if (!Array.isArray(raw)) return [];
              return raw
                .map((value) => Number(value))
                .filter((value) => Number.isFinite(value) && value >= 1 && value <= 7)
                .map((value) => Math.round(value));
            }

            function _coerceBoolClient(value, fallback = false) {
              if (value == null) return !!fallback;
              if (typeof value === "boolean") return value;
              const text = String(value).trim().toLowerCase();
              if (!text) return false;
              if (["1", "true", "yes", "on"].includes(text)) return true;
              if (["0", "false", "no", "off"].includes(text)) return false;
              return !!fallback;
            }

            const HEARTBEAT_BUSY_POLICY_OPTIONS = [
              ["run_on_next_idle", "run_on_next_idle"],
              ["skip_if_busy", "skip_if_busy"],
              ["queue_if_busy", "queue_if_busy"],
            ];
            const STATE = { project: "task_dashboard" };
            const SESSION_INFO_UI = {
              sessionId: "019d2a60-b8be-7b21-bed0-2c95ab2123ff",
              projectId: "task_dashboard",
              base: { channel_name: "子级06-数据治理与契约（规格-校验-修复）" },
              heartbeatTasks: [],
              heartbeatDraft: null,
            };

            eval(extractFunction("web/task_entry_parts/80-project-ops.js", "heartbeatTaskFieldPresent"));
            eval(extractFunction("web/task_entry_parts/80-project-ops.js", "heartbeatOptionalNonNegativeNumber"));
            eval(extractFunction("web/task_entry_parts/80-project-ops.js", "normalizeHeartbeatTaskClient"));
            eval(extractFunction("web/task_entry_parts/81-session-info-and-bindings.js", "inferConversationHeartbeatTaskSourceScope"));
            eval(extractFunction("web/task_entry_parts/81-session-info-and-bindings.js", "buildSessionHeartbeatPayloadFromDrafts"));
            eval(extractFunction("web/task_entry_parts/81-session-info-and-bindings.js", "buildSessionHeartbeatPayloadForSessionSave"));

            const sid = SESSION_INFO_UI.sessionId;
            const normalized = normalizeHeartbeatTaskClient(
              {
                heartbeat_task_id: "message-monitor-watch",
                title: "消息监控巡查",
                enabled: true,
                session_id: sid,
                channel_name: SESSION_INFO_UI.base.channel_name,
                preset_key: "ops_inspection",
                prompt_template: "请巡查消息链路。",
                schedule_type: "interval",
                interval_minutes: 120,
                busy_policy: "run_on_next_idle",
              },
              "task_dashboard"
            );
            assert.equal(normalized.source_scope, "session");

            SESSION_INFO_UI.heartbeatTasks = [normalized];
            SESSION_INFO_UI.heartbeatDraft = {
              heartbeatTaskId: "message-monitor-watch",
              title: "消息监控巡查",
              enabled: true,
              presetKey: "ops_inspection",
              promptTemplate: "请巡查最近消息链路异常、待处理回执与未消费正式通知，并输出结论、风险与下一步动作。",
              scheduleType: "interval",
              intervalMinutes: 120,
              weekdays: [1, 2, 3, 4, 5],
              busyPolicy: "run_on_next_idle",
              maxExecuteCount: 0,
              contextScope: {
                recentTasksLimit: 10,
                recentRunsLimit: 10,
                includeTaskCounts: true,
                includeRecentTasks: true,
                includeRecentRuns: true,
              },
            };

            const savePayload = buildSessionHeartbeatPayloadForSessionSave();
            assert.equal(savePayload.heartbeat.enabled, true);
            assert.equal(savePayload.heartbeat.tasks.length, 1);
            assert.equal(savePayload.heartbeat.tasks[0].heartbeat_task_id, "message-monitor-watch");
            assert.equal(savePayload.heartbeat.tasks[0].session_id, sid);
            assert.equal(savePayload.heartbeat.tasks[0].channel_name, SESSION_INFO_UI.base.channel_name);

            SESSION_INFO_UI.heartbeatTasks = [];
            SESSION_INFO_UI.heartbeatDraft = {
              heartbeatTaskId: "heartbeat-1776350248123",
              title: "",
              enabled: true,
              presetKey: "ops_inspection",
              promptTemplate: "",
              scheduleType: "interval",
              intervalMinutes: 120,
              weekdays: [1, 2, 3, 4, 5],
              busyPolicy: "run_on_next_idle",
              maxExecuteCount: 0,
              contextScope: {
                recentTasksLimit: 10,
                recentRunsLimit: 10,
                includeTaskCounts: true,
                includeRecentTasks: true,
                includeRecentRuns: true,
              },
            };
            const emptySavePayload = buildSessionHeartbeatPayloadForSessionSave();
            assert.equal(emptySavePayload.heartbeat.enabled, false);
            assert.equal(emptySavePayload.heartbeat.tasks.length, 0);

            SESSION_INFO_UI.heartbeatTasks = [normalized];
            SESSION_INFO_UI.heartbeatDraft = null;
            const listPayload = buildSessionHeartbeatPayloadFromDrafts();
            assert.equal(listPayload.heartbeat.tasks.length, 1);
            assert.equal(listPayload.heartbeat.tasks[0].heartbeat_task_id, "message-monitor-watch");
            assert.equal(listPayload.heartbeat.tasks[0].session_id, sid);
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

    def test_session_info_save_uses_session_save_heartbeat_builder(self) -> None:
        text = SESSION_UI_FILE.read_text(encoding="utf-8")
        self.assertIn(
            "const heartbeatPayload = buildSessionHeartbeatPayloadForSessionSave();",
            text,
        )
        self.assertIn(
            "自定义提示词不能为空",
            text,
        )


if __name__ == "__main__":
    unittest.main()
