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
        cls.create_entry_source = (REPO_ROOT / "web" / "task_parts" / "57-task-create-entry.js").read_text(encoding="utf-8")
        cls.create_entry_css = (REPO_ROOT / "web" / "task_parts" / "57-task-create-entry.css").read_text(encoding="utf-8")
        cls.list_card_source = (REPO_ROOT / "web" / "task_parts" / "43-unified-task-list-card.js").read_text(encoding="utf-8")
        cls.list_card_css = (REPO_ROOT / "web" / "task_parts" / "43-unified-task-list-card.css").read_text(encoding="utf-8")
        cls.project_ops_source = (REPO_ROOT / "web" / "task_entry_parts" / "80-project-ops.js").read_text(encoding="utf-8")
        cls.task_source = (REPO_ROOT / "web" / "task.js").read_text(encoding="utf-8")
        cls.task_css = (REPO_ROOT / "web" / "task.css").read_text(encoding="utf-8")

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

    def test_task_observatory_cards_wire_existing_agent_avatar_groups(self) -> None:
        self.assertIn("buildTaskRoleAvatar(member", self.list_card_source)
        self.assertIn('label: "执"', self.list_card_source)
        self.assertIn("const maxVisible = 5", self.list_card_source)
        self.assertIn("unified-task-list-role-more", self.list_card_source)
        self.assertIn("unifiedTaskListRoleMembers(group.members)", self.list_card_source)
        self.assertIn("unifiedTaskListIsMeaningfulRoleText", self.list_card_source)
        self.assertIn("normalizeTaskRoleMemberDisplayText", self.task_source)
        self.assertIn('buildUnifiedTaskListCard({', self.project_modes_source)
        self.assertIn("buildUnifiedTaskChildGrid(children", self.project_modes_source)

    def test_task_observatory_exposes_manual_dashboard_refresh(self) -> None:
        self.assertIn("task-observatory-refresh-btn", self.project_modes_source)
        self.assertIn("刷新任务数据", self.project_modes_source)
        self.assertIn("triggerProjectDashboardRebuild()", self.project_modes_source)
        self.assertIn("padding:8px 10px;", self.project_modes_source)
        self.assertIn("background:rgba(255,255,255,0.82);", self.project_modes_source)
        self.assertIn("border-top-color:rgba(47,111,237,0.78);", self.project_modes_source)
        self.assertIn("window.PROJECT_REBUILD_UI = PROJECT_REBUILD_UI", self.project_ops_source)

    def test_task_observatory_create_entry_uses_safe_backend_workflow(self) -> None:
        self.assertIn("buildTaskCreateEntryAction(pid)", self.project_modes_source)
        self.assertIn("/api/projects/\" + encodeURIComponent(pid) + \"/tasks/\" + (isCreate ? \"create\" : \"validate\")", self.create_entry_source)
        self.assertIn("TASK_CREATE_REQUIRED_ROLES", self.create_entry_source)
        self.assertIn("[\"owner\", \"主负责位\"]", self.create_entry_source)
        self.assertIn("[\"executor\", \"执行位\"]", self.create_entry_source)
        self.assertIn("[\"validator\", \"验收位\"]", self.create_entry_source)
        self.assertIn("validation_failed", self.create_entry_source)
        self.assertIn("dryRun: !!form.dryRun", self.create_entry_source)
        self.assertIn("includeMarkdown: !!form.includeMarkdown", self.create_entry_source)
        self.assertIn("triggerProjectDashboardRebuild()", self.create_entry_source)
        self.assertNotIn("writeFile", self.create_entry_source)
        self.assertIn(".task-create-entry-btn", self.create_entry_css)
        self.assertIn("z-index: 120;", self.create_entry_css)

    def test_task_observatory_visual_density_guardrails(self) -> None:
        self.assertIn("gap:14px;", self.project_modes_source)
        self.assertIn("display:none !important;", self.project_modes_source)
        self.assertIn("aside { display: none !important; }", self.task_css)
        self.assertIn(".memo-drawer-mask.show > aside.memo-drawer.conv-task-drawer", self.task_css)
        self.assertIn("display: grid !important;", self.task_css)
        self.assertIn("grid-template-columns: repeat(auto-fill, minmax(min(284px, 100%), 1fr));", self.list_card_css)
        self.assertIn("max-width: min(100%, 1280px);", self.list_card_css)
        self.assertIn("-webkit-line-clamp: 2;", self.list_card_css)
        self.assertIn("grid-template-rows: auto auto;", self.list_card_css)
        self.assertIn(".unified-task-list-card.is-parent > .unified-task-list-top", self.list_card_css)
        self.assertIn(".unified-task-list-card.is-parent > .unified-task-list-main", self.list_card_css)
        self.assertIn(".unified-task-list-card.is-parent > .unified-task-list-roles", self.list_card_css)
        self.assertIn(".unified-task-list-card.is-parent > .unified-task-list-meta", self.list_card_css)
        self.assertIn(".unified-task-list-card.is-parent > .unified-task-list-foot", self.list_card_css)
        self.assertIn("grid-column: 3;", self.list_card_css)
        self.assertIn("grid-row: 2;", self.list_card_css)
        self.assertIn("justify-self: end;", self.list_card_css)
        self.assertIn("max-width: 180px;", self.list_card_css)
        self.assertIn(".conv-task-drawer .unified-task-list-card.is-parent > .unified-task-list-meta", self.list_card_css)
        self.assertIn("grid-template-rows: auto;", self.list_card_css)

    def test_task_role_avatar_resolution_reuses_registry_session_candidates(self) -> None:
        self.assertIn("function resolveTaskRoleMemberSession", self.task_source)
        self.assertIn("registry_candidate", self.task_source)
        self.assertIn("sessionForChannel(projectId, fallbackChannel)", self.task_source)
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

            global.STATE = { project: "ndt" };
            global.DATA = { project_id: "task_dashboard" };
            global.PCONV = {};
            global.boolLike = (value) => {
              if (typeof value === "boolean") return value;
              const text = String(value == null ? "" : value).trim().toLowerCase();
              return ["1", "true", "yes", "y"].includes(text);
            };
            global.firstNonEmptyText = (list, fallback = "") => {
              for (const raw of (Array.isArray(list) ? list : [])) {
                const text = String(raw == null ? "" : raw).trim();
                if (text) return text;
              }
              return String(fallback || "");
            };
            global.looksLikeSessionId = (value) => /^[0-9a-f]{8}-[0-9a-f-]{27}$/i.test(String(value || "").trim());
            global.conversationRuntimeSessionsForProject = () => [];
            global.projectById = (pid) => pid === "ndt" ? {
              id: "ndt",
              channels: [],
              channel_sessions: [],
              registry: {
                channels: [
                  {
                    channel_name: "业务01-赛事场景与演示规划",
                    primary_session_id: "019d9c63-2aa4-7a32-9c06-c062f3db808e",
                    primary_session_alias: "赛事-演示规划",
                    primary_cli_type: "codex",
                    session_candidates: [
                      {
                        session_id: "019d9c63-2aa4-7a32-9c06-c062f3db808e",
                        display_name: "赛事-演示规划",
                        desc: "赛事-演示规划",
                        session_role: "primary",
                        is_primary: true,
                      },
                    ],
                  },
                  {
                    channel_name: "开发01-前端Demo与可视化实现",
                    primary_session_id: "019d76d8-e589-7780-96f4-2ceddabf3d6f",
                    primary_session_alias: "前端-框架和页面",
                    primary_cli_type: "codex",
                    session_candidates: [
                      {
                        session_id: "019d76d8-e589-7780-96f4-2ceddabf3d6f",
                        display_name: "前端-框架和页面",
                        desc: "前端-框架和页面",
                        session_role: "primary",
                        is_primary: true,
                      },
                      {
                        session_id: "019d8459-2188-7690-a972-06726e3cd706",
                        display_name: "前端-沙盘推演",
                        desc: "前端-沙盘推演",
                        session_role: "child",
                        is_primary: false,
                      },
                    ],
                  },
                ],
              },
            } : null;
            global.sessionForChannel = (pid, channelName) => ({
              project_id: pid,
              channel_name: channelName,
              session_id: "fallback-primary-session-id",
              display_name: "fallback-primary",
              alias: "fallback-primary",
              session_role: "primary",
              is_primary: true,
            });

            const file = "web/task.js";
            eval(extractFunction(file, "normalizeTaskRoleLookupText"));
            eval(extractFunction(file, "uniqueTaskRoleValues"));
            eval(extractFunction(file, "taskRoleMemberIdentityHints"));
            eval(extractFunction(file, "getTaskRoleProjectSessionCandidates"));
            eval(extractFunction(file, "resolveTaskRoleMemberSession"));
            eval(extractFunction(file, "normalizeTaskRoleMemberDisplayText"));
            eval(extractFunction(file, "taskRoleMemberDisplayMeta"));

            const frontendMember = {
              agent_name: "开发01-前端Demo与可视化实现 / 前端-沙盘推演",
              alias: "开发01-前端Demo与可视化实现 / 前端-沙盘推演",
              session_id: "",
            };
            const frontendResolved = resolveTaskRoleMemberSession(frontendMember);
            assert.equal(frontendResolved.session_id, "019d8459-2188-7690-a972-06726e3cd706");
            assert.equal(frontendResolved.channel_name, "开发01-前端Demo与可视化实现");
            const frontendMeta = taskRoleMemberDisplayMeta(frontendMember);
            assert.equal(frontendMeta.sessionId, "019d8459-2188-7690-a972-06726e3cd706");
            assert.equal(frontendMeta.channelName, "开发01-前端Demo与可视化实现");
            const visualMeta = taskRoleMemberDisplayMeta({ display_name: "`视觉设计`" });
            assert.equal(visualMeta.text, "视觉设计");
            const noisyMeta = taskRoleMemberDisplayMeta("`");
            assert.equal(noisyMeta.text, "");

            const productMember = {
              agent_name: "业务01-赛事场景与演示规划 / 赛事-演示规划",
              alias: "业务01-赛事场景与演示规划 / 赛事-演示规划",
              session_id: "",
            };
            const productResolved = resolveTaskRoleMemberSession(productMember);
            assert.equal(productResolved.session_id, "019d9c63-2aa4-7a32-9c06-c062f3db808e");

            const fallbackResolved = resolveTaskRoleMemberSession({ channel_name: "业务01-赛事场景与演示规划" });
            assert.equal(fallbackResolved.session_id, "019d9c63-2aa4-7a32-9c06-c062f3db808e");
            """
        )
        proc = subprocess.run(
            ["node", "-e", script, str(REPO_ROOT)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            self.fail(proc.stderr or proc.stdout or "node task role avatar resolution regression script failed")

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
