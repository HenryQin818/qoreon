import shutil
import subprocess
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("node"), "node is required for UI logic regression checks")
class TaskObservatoryMainViewUiLogicTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.project_modes_source = (REPO_ROOT / "web" / "task_parts" / "77-project-modes.js").read_text(encoding="utf-8")

    def test_build_task_observatory_model_groups_recent_timeline_rows(self) -> None:
        script = textwrap.dedent(
            r"""
            const assert = require("node:assert/strict");
            const fs = require("node:fs");
            const path = require("node:path");

            const repoRoot = process.argv[1];

            function extractConst(file, name) {
              const text = fs.readFileSync(path.join(repoRoot, file), "utf8");
              const match = text.match(new RegExp(`const ${name} = [^;]+;`));
              if (!match) throw new Error(`missing const ${name} in ${file}`);
              return match[0];
            }

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

            global.taskStatusFlags = (item) => ({
              blocked: Boolean(item && item.blocked),
            });

            const file = "web/task_parts/77-project-modes.js";
            eval(extractConst(file, "TASK_OBSERVATORY_PAGE_SIZE"));
            eval(extractFunction(file, "taskObservatoryTimelineDateKey"));
            eval(extractFunction(file, "taskObservatoryGroupHasBlocked"));
            eval(extractFunction(file, "buildTaskObservatoryModel"));

            const groups = [
              {
                lane: "进行中",
                total: 5,
                latestTs: 300,
                latestAt: "2026-04-17T20:10:00+08:00",
                master: { blocked: false },
                children: [{ blocked: false }],
              },
              {
                lane: "待验收",
                total: 3,
                latestTs: 200,
                latestAt: "2026-04-17T09:00:00+08:00",
                master: { blocked: true },
                children: [{ blocked: false }],
              },
              {
                lane: "已完成",
                total: 4,
                latestTs: 100,
                latestAt: "2026-04-16T18:00:00+08:00",
                master: { blocked: false },
                children: [{ blocked: true }],
              },
            ];

            const model = buildTaskObservatoryModel(groups, { laneFilter: "全部", visibleLimit: 2 });
            assert.equal(model.totalTaskCount, 12);
            assert.equal(model.totalGroupCount, 3);
            assert.equal(model.visibleGroupCount, 2);
            assert.equal(model.hasMore, true);
            assert.equal(model.days.length, 1);
            assert.equal(model.days[0].label, "2026-04-17");
            assert.equal(model.days[0].items.length, 2);
            assert.equal(model.counts.running, 1);
            assert.equal(model.counts.acceptance, 1);
            assert.equal(model.counts.done, 1);
            assert.equal(model.counts.blocked, 2);

            const blockedOnly = buildTaskObservatoryModel(groups, { laneFilter: "全部", specialFilter: "blocked", visibleLimit: 10 });
            assert.equal(blockedOnly.filteredGroupCount, 2);
            assert.equal(blockedOnly.visibleGroupCount, 2);
            assert.equal(blockedOnly.days.length, 2);
            assert.equal(blockedOnly.days[0].label, "2026-04-17");
            assert.equal(blockedOnly.days[1].label, "2026-04-16");
            """
        )
        proc = subprocess.run(
            ["node", "-e", script, str(REPO_ROOT)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            self.fail(proc.stderr or proc.stdout or "node task observatory regression script failed")

    def test_task_home_header_source_removes_brief_and_multiline_stat_copy(self) -> None:
        self.assertNotIn("task-observatory-brief", self.project_modes_source)
        self.assertNotIn("task-observatory-stat-sub", self.project_modes_source)
        self.assertNotIn("当前恢复 `tm=tasks` 的正式首页语义", self.project_modes_source)
        self.assertIn("task-observatory-head", self.project_modes_source)
        self.assertNotIn('label: "当前范围"', self.project_modes_source)
        self.assertIn("width:fit-content;", self.project_modes_source)
        self.assertIn("justify-content:flex-start;", self.project_modes_source)

    def test_task_observatory_stat_card_keeps_compact_label_and_value_only(self) -> None:
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

            function makeNode(tag, attrs = {}) {
              return {
                tag,
                className: attrs.class || "",
                type: attrs.type,
                textContent: attrs.text || "",
                title: attrs.title || "",
                children: [],
                appendChild(child) {
                  this.children.push(child);
                  return child;
                },
                addEventListener() {},
                setAttribute(name, value) {
                  this[name] = value;
                },
              };
            }

            global.el = (tag, attrs = {}) => makeNode(tag, attrs);

            const file = "web/task_parts/77-project-modes.js";
            eval(extractFunction(file, "buildTaskObservatoryStatCard"));

            const node = buildTaskObservatoryStatCard({
              label: "全部",
              value: 42,
              sub: "总任务 21 条",
              clickable: false,
            });

            assert.equal(node.children.length, 2);
            assert.equal(node.children[0].textContent, "全部");
            assert.equal(node.children[1].textContent, "42");
            assert.equal(node.title, "总任务 21 条");
            """
        )
        proc = subprocess.run(
            ["node", "-e", script, str(REPO_ROOT)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            self.fail(proc.stderr or proc.stdout or "node task observatory stat-card regression script failed")

    def test_task_single_canvas_panel_mode_toggles_body_classes(self) -> None:
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

            function createClassList() {
              const set = new Set();
              return {
                toggle(name, force) {
                  if (force === undefined) {
                    if (set.has(name)) set.delete(name);
                    else set.add(name);
                    return set.has(name);
                  }
                  if (force) set.add(name);
                  else set.delete(name);
                  return set.has(name);
                },
                contains(name) {
                  return set.has(name);
                },
              };
            }

            global.STATE = {
              panelMode: "task",
              taskModule: "tasks",
              taskCanvasDetailOpen: false,
            };
            global.normalizePanelMode = (value) => String(value || "").trim() || "channel";
            global.normalizeTaskModule = (value) => String(value || "").trim() || "tasks";
            global.document = {
              body: { classList: createClassList() },
              querySelectorAll() { return []; },
              getElementById() { return { style: {} }; },
            };

            const file = "web/task_parts/79-panel-wire-upload.js";
            eval(extractFunction(file, "isTaskSingleCanvasMode"));
            eval(extractFunction(file, "syncTaskCanvasDetailState"));
            eval(extractFunction(file, "openTaskCanvasDetail"));
            eval(extractFunction(file, "closeTaskCanvasDetail"));
            eval(extractFunction(file, "applyPanelMode"));

            applyPanelMode();
            assert.equal(document.body.classList.contains("panel-task-single-canvas"), true);
            assert.equal(document.body.classList.contains("task-canvas-detail-open"), false);

            openTaskCanvasDetail();
            assert.equal(document.body.classList.contains("task-canvas-detail-open"), true);

            STATE.taskModule = "schedule";
            applyPanelMode();
            assert.equal(document.body.classList.contains("panel-task-single-canvas"), false);
            assert.equal(document.body.classList.contains("task-canvas-detail-open"), false);
            assert.equal(STATE.taskCanvasDetailOpen, false);
            """
        )
        proc = subprocess.run(
            ["node", "-e", script, str(REPO_ROOT)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            self.fail(proc.stderr or proc.stdout or "node task single canvas regression script failed")
