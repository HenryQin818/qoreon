import shutil
import subprocess
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("node"), "node is required for UI logic regression checks")
class NewChannelUiLogicTests(unittest.TestCase):
    def test_agents_md_channel_copy_and_guardrails_are_visible(self) -> None:
        html = (REPO_ROOT / "web" / "task.html.tpl").read_text(encoding="utf-8")
        task_js = (REPO_ROOT / "web" / "task.js").read_text(encoding="utf-8")
        channel_type_js = (REPO_ROOT / "web" / "task_parts" / "54-channel-type-templates.js").read_text(encoding="utf-8")
        channel_type_css = (REPO_ROOT / "web" / "task_parts" / "54-channel-type-templates.css").read_text(encoding="utf-8")
        manage_js = (REPO_ROOT / "web" / "task_parts" / "52-channel-manage.js").read_text(encoding="utf-8")
        runs_js = (REPO_ROOT / "web" / "task_parts" / "76-runs-and-drawer.js").read_text(encoding="utf-8")
        manage_css = (REPO_ROOT / "web" / "task_parts" / "52-channel-manage.css").read_text(encoding="utf-8")

        self.assertIn("通道类型（2字）", html)
        for channel_type in ["总控", "助理", "产品", "镜像", "前端", "后端", "测试", "服务", "通讯", "任务", "技能", "资料", "视觉"]:
            self.assertIn(f'<option value="{channel_type}"', html)
        self.assertNotIn("标准角色模板</label>", html)
        self.assertIn('id="newChannelAgentRole" type="hidden"', html)
        self.assertIn("继承自通道类型的标准配置", html)
        self.assertIn("newChannelTypeRole", html)
        self.assertIn("newChannelTypeSkills", html)
        self.assertIn("newChannelTypeWorkdir", html)
        self.assertIn("newChannelTypeGuardrails", html)
        self.assertIn("newConvChannelTypeSummary", html)
        self.assertIn("newChannelAgentRole", html)
        self.assertIn("newChannelCreateAgentsMd", html)
        self.assertIn("newChannelAgentsMdContent", html)
        self.assertIn("创建/保存会写入通道目录 AGENTS.md", html)
        self.assertIn("已运行会话不会自动刷新上下文", html)
        self.assertIn("已写入不等于已生效", html)
        self.assertIn("真实初始化消息", html)

        self.assertIn("编辑 AGENTS.md", manage_js)
        self.assertIn("编辑 AGENTS.md", runs_js)
        self.assertIn("openChannelAgentsMdModal(pid, channel)", runs_js)
        self.assertIn("/api/channels/agents-md", manage_js)
        self.assertIn('source === "template"', manage_js)
        self.assertIn("保存后写入该通道目录的 AGENTS.md", html)
        self.assertIn("保存前后端会自动生成备份", html)
        self.assertIn("不会发送初始化消息", html)

        self.assertIn("## 协作快速上手", task_js)
        self.assertIn("message_cli send|receipt", task_js)
        self.assertIn("dialog_now", task_js)
        self.assertIn("task_with_receipt", task_js)
        self.assertIn("notify_only", task_js)
        self.assertIn("announce_run_id + target_session_id一致 + visible_in_channel_chat=true", task_js)
        self.assertIn("送达不等于业务完成", task_js)
        self.assertIn("task_cli validate --stage review --mode strict", task_js)
        self.assertIn("skill 是触发入口和执行口径，不等于自动授权", task_js)
        self.assertIn("collab-message-send", task_js)
        self.assertIn("不通过本文件授予服务启动、重启、注册、发布", task_js)
        self.assertIn("真实初始化消息", task_js)
        self.assertIn("service monitor 写入", task_js)
        self.assertIn("AGENTS.md / 主任务 / 主对话 / Agent / 真实初始化消息", task_js)
        self.assertIn("newChannelAgentsMdContent", task_js)
        self.assertIn("aria-disabled", task_js)
        self.assertIn(".new-channel-agents-md:disabled", manage_css)
        self.assertIn("NEW_CHANNEL_TYPE_TEMPLATES", channel_type_js)
        self.assertIn("renderNewChannelTypeAgentsMdTemplate", channel_type_js)
        self.assertIn("buildNewConvChannelTypeInheritanceText", channel_type_js)
        self.assertIn(".new-channel-type-card", channel_type_css)
        self.assertIn(".newconv-inherit-summary", channel_type_css)

    def test_channel_type_templates_drive_agents_md_and_inheritance_copy(self) -> None:
        script = textwrap.dedent(
            r"""
            const assert = require("node:assert/strict");
            const fs = require("node:fs");
            const path = require("node:path");

            const repoRoot = process.argv[1];
            eval(fs.readFileSync(path.join(repoRoot, "web/task_parts/54-channel-type-templates.js"), "utf8"));

            const frontend = resolveNewChannelTypeTemplate("前端");
            assert.equal(frontend.agentRole, "developer");
            assert.equal(frontend.standardRole, "前端执行");
            assert.deepEqual(newChannelTypeList().map((row) => row.key), [
              "总控", "助理", "产品", "镜像", "前端", "后端", "测试", "服务", "通讯", "任务", "技能", "资料", "视觉",
            ]);

            global.buildNewChannelName = () => "前端01-任务页交互";
            const content = renderNewChannelTypeAgentsMdTemplate({
              channelKind: "前端",
              channelName: "任务页交互",
              channelDesc: "页面交互和体验验证",
            });
            assert.match(content, /通道类型：前端/);
            assert.match(content, /标准角色：前端执行/);
            assert.match(content, /task-dashboard-visual-refinement-support/);
            assert.match(content, /不改 API 语义/);
            assert.match(content, /复杂消息回到 `collab-message-send`/);
            assert.doesNotMatch(content, /完整手册/);

            const inheritance = buildNewConvChannelTypeInheritanceText("前端01-任务页交互");
            assert.match(inheritance, /标准角色：前端执行/);
            assert.match(inheritance, /项目 AGENTS.md \+ 通道 AGENTS.md/);

            const legacy = buildNewConvChannelTypeInheritanceText("子级04-前端体验（task-overview 页面交互）");
            assert.match(legacy, /未命中新版 2 字类型/);
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

    def test_duplicate_channel_heal_requires_backend_confirmation(self) -> None:
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
              const headerMatch = text.slice(start).match(new RegExp(`(?:async\\s+)?function ${name}\\([^\\n]*\\)\\s*\\{`));
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

            const projects = [{ id: "clitools", channels: [] }];
            function projectById(id) {
              return projects.find((item) => item.id === id) || null;
            }
            function unionChannelNames(projectId) {
              const project = projectById(projectId);
              return Array.isArray(project && project.channels)
                ? project.channels.map((row) => String((row && row.name) || "").trim()).filter(Boolean)
                : [];
            }

            let loadCount = 0;
            let renderCount = 0;
            let toastCount = 0;
            async function loadChannelSessions() {
              loadCount += 1;
            }
            function render() {
              renderCount += 1;
            }
            function toast() {
              toastCount += 1;
            }
            function buildNewChannelName(form) {
              return `${form.channelKind || "辅助"}${form.channelIndex || ""}-${form.channelName || ""}`;
            }

            eval(extractFunction("web/task_parts/53-ui-feedback.js", "upsertCreatedChannelIntoLocalState"));
            eval(extractFunction("web/task_parts/53-ui-feedback.js", "syncExistingChannelConflictToLocalState"));

            (async () => {
              const form = {
                projectId: "clitools",
                channelKind: "辅助",
                channelIndex: "01",
                channelName: "项目管理",
                channelDesc: "项目管理",
              };

              const healedFalse = await syncExistingChannelConflictToLocalState(form, {
                projectId: "clitools",
                channelName: "辅助01-项目管理",
                channelExistsInProject: false,
              });
              assert.equal(healedFalse, false);
              assert.equal(projects[0].channels.length, 0);
              assert.equal(loadCount, 0);
              assert.equal(renderCount, 0);
              assert.equal(toastCount, 0);

              const healedTrue = await syncExistingChannelConflictToLocalState(form, {
                projectId: "clitools",
                channelName: "辅助01-项目管理",
                channelExistsInProject: true,
              });
              assert.equal(healedTrue, true);
              assert.equal(projects[0].channels.length, 1);
              assert.equal(projects[0].channels[0].name, "辅助01-项目管理");
              assert.equal(loadCount, 1);
              assert.equal(renderCount, 1);
              assert.equal(toastCount, 1);
            })().catch((err) => {
              console.error(err);
              process.exit(1);
            });
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
