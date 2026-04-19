import shutil
import subprocess
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("node"), "node is required for UI logic regression checks")
class TaskMainGroupingUiLogicTests(unittest.TestCase):
    def test_build_task_groups_prefers_explicit_parent_task_fields(self) -> None:
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

            const tasks = [
              {
                title: "【已完成】【任务】20260419-任务首页顶部精简与主子任务默认展示校正编排",
                path: "任务规划/辅助04/已完成/任务/master.md",
                task_id: "task_master",
                primary_status: "已完成",
                updated_at: "2026-04-19T20:37:00+08:00",
              },
              {
                title: "【已完成】【任务】20260419-任务首页顶部精简与主子任务默认展示前端实施",
                path: "任务规划/子级04/已完成/任务/frontend.md",
                task_id: "task_frontend",
                parent_task_id: "task_master",
                primary_status: "已完成",
                updated_at: "2026-04-19T20:37:00+08:00",
              },
              {
                title: "【已完成】【任务】20260419-任务首页顶部精简与主子任务默认展示回归验收",
                path: "任务规划/子级08/已完成/任务/qa.md",
                task_id: "task_qa",
                parent_task_id: "task_master",
                primary_status: "已完成",
                updated_at: "2026-04-19T20:38:00+08:00",
              },
            ];

            global.STATE = { q: "" };
            global.firstNonEmptyText = (list, fallback = "") => {
              const arr = Array.isArray(list) ? list : [];
              for (const item of arr) {
                const text = String(item == null ? "" : item).trim();
                if (text) return text;
              }
              return String(fallback || "").trim();
            };
            global.itemsForProject = () => tasks.slice();
            global.isTaskItem = () => true;
            global.matchesQuery = (it) => {
              const q = String(global.STATE.q || "").trim().toLowerCase();
              if (!q) return true;
              return String((it && it.title) || "").toLowerCase().includes(q);
            };
            global.taskPrimaryStatus = (it) => String((it && (it.primary_status || it.status)) || "待办").trim() || "待办";
            global.normalizeScheduleTaskPathForProject = (_projectId, value) => String(value || "").trim();
            global.toTimeNum = (value) => {
              const ts = Date.parse(String(value || ""));
              return Number.isFinite(ts) ? ts : 0;
            };

            const file = "web/task.js";
            eval(extractFunction(file, "normalizeTaskStableId"));
            eval(extractFunction(file, "taskStableIdOfItem"));
            eval(extractFunction(file, "taskTitleBase"));
            eval(extractFunction(file, "taskParentStableIdOfItem"));
            eval(extractFunction(file, "taskParentPathOfItem"));
            eval(extractFunction(file, "itemDeclaresExplicitTaskParent"));
            eval(extractFunction(file, "inferTaskGroupMeta"));
            eval(extractFunction(file, "taskLaneFromMasterBucket"));
            eval(extractFunction(file, "buildTaskGroups"));

            const groups = buildTaskGroups("task_dashboard");
            assert.equal(groups.length, 1);
            assert.equal(groups[0].master.title, tasks[0].title);
            assert.deepEqual(
              groups[0].children.map((item) => item.title).slice().sort(),
              [tasks[1].title, tasks[2].title].slice().sort()
            );
            assert.equal(groups[0].childTotal, 2);

            global.STATE.q = "前端实施";
            const filtered = buildTaskGroups("task_dashboard");
            assert.equal(filtered.length, 1);
            assert.equal(filtered[0].master.title, tasks[0].title);
            assert.equal(filtered[0].children.length, 2);
          """
        )
        proc = subprocess.run(
            ["node", "-e", script, str(REPO_ROOT)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            self.fail(proc.stderr or proc.stdout or "node task main grouping regression script failed")
