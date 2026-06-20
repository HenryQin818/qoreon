import shutil
import subprocess
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("node"), "node is required for UI logic regression checks")
class AgentListTwoLineCompactUiLogicTests(unittest.TestCase):
    def test_agent_row_uses_two_line_layout_and_activity_overlay(self) -> None:
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

            function makeNode(tag, props = {}, children = []) {
              const node = {
                tag,
                className: String(props.class || ""),
                text: String(props.text || ""),
                title: String(props.title || ""),
                children: [],
                appendChild(child) {
                  this.children.push(child);
                  return child;
                },
                addEventListener() {},
                setAttribute(key, value) {
                  this[key] = value;
                },
              };
              Object.keys(props).forEach((key) => {
                if (key !== "class") node[key] = props[key];
              });
              (Array.isArray(children) ? children : [children]).filter(Boolean).forEach((child) => node.appendChild(child));
              return node;
            }

            function hasClass(node, className) {
              return String(node && node.className || "").split(/\s+/).includes(className);
            }

            function findAll(node, className, out = []) {
              if (!node) return out;
              if (hasClass(node, className)) out.push(node);
              (node.children || []).forEach((child) => findAll(child, className, out));
              return out;
            }

            let countBadgeOpts = null;

            global.el = makeNode;
            global.STATE = { project: "task_dashboard" };
            global.isConversationPendingCreateSession = () => false;
            global.getSessionId = (row) => String((row && (row.sessionId || row.id)) || "").trim();
            global.conversationAgentName = (row) => String((row && row.displayName) || "产品原型");
            global.conversationPreviewLine = (row) => String((row && row.preview) || "系统：暂无消息");
            global.conversationStatusMeta = () => ({ text: "处理中", tone: "running", title: "运行中" });
            global.conversationHeatMeta = () => null;
            global.buildConversationCountBadges = (_session, opts) => {
              countBadgeOpts = opts;
              const wrap = makeNode("div", { class: "conv-counts" });
              if (opts.includeDraft !== false) wrap.appendChild(makeNode("span", { class: "conv-count-dot draft", text: "草" }));
              wrap.appendChild(makeNode("span", { class: "conv-count-dot new", text: "3" }));
              wrap.appendChild(makeNode("span", { class: "conv-count-dot memo", text: "1" }));
              return wrap;
            };
            global.buildConversationAvatarNode = () => makeNode("div", { class: "conv-avatar", text: "产" });
            global.buildConversationRoleBadge = () => makeNode("span", { class: "conv-role-badge primary", text: "主" });
            global.buildConversationCliBadge = () => makeNode("span", { class: "conv-type-badge cli-codex", text: "Codex" });
            global.compactDateTime = () => "05-15 09:34";
            global.bindConversationMentionDragSource = () => {};
            global.bindQueuedForwardDropTarget = () => {};
            global.consumeQueuedForwardDropHandled = () => false;
            global.openConversationSessionInfoModal = () => {};

            eval(extractFunction("web/task.js", "buildConversationListActivityOverlay"));
            eval(extractFunction("web/task.js", "buildConversationRow"));

            const row = buildConversationRow({
              id: "sid-1",
              sessionId: "sid-1",
              displayName: "产品原型",
              preview: "系统：暂无消息",
              lastActiveAt: "2026-05-15T09:34:00+0800",
            }, false, () => {}, {
              showCountDots: true,
              projectId: "task_dashboard",
            });

            assert.equal(hasClass(row, "is-compact-two-line"), true);
            assert.equal(hasClass(row, "is-status-running"), true);
            assert.equal(countBadgeOpts.includeDraft, true);
            assert.equal(countBadgeOpts.showUnread, true);

            assert.equal(findAll(row, "conv-card-submeta").length, 0);
            assert.equal(findAll(row, "conv-role-badge").length, 1);
            assert.equal(findAll(row, "conv-type-badge").length, 1);

            const side = findAll(row, "conv-card-side")[0];
            assert.equal(findAll(side, "conv-status-badge").length, 0);
            assert.equal(findAll(side, "conv-row-menu-btn").length, 1);

            const overlay = findAll(row, "conv-card-activity-overlay")[0];
            assert.ok(overlay);
            assert.equal(findAll(overlay, "conv-status-badge").length, 1);
            assert.equal(findAll(overlay, "conv-count-dot").length, 3);
            assert.equal(findAll(overlay, "draft").length, 1);
            assert.equal(findAll(row, "conv-card-foot").length, 1);
            """
        )
        proc = subprocess.run(
            ["node", "-e", script, str(REPO_ROOT)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            self.fail(proc.stderr or proc.stdout or "node agent list compact row regression script failed")

    def test_count_badges_renders_single_character_draft_marker(self) -> None:
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

            function makeNode(tag, props = {}, children = []) {
              const node = {
                tag,
                className: String(props.class || ""),
                text: String(props.text || ""),
                title: String(props.title || ""),
                children: [],
                appendChild(child) {
                  this.children.push(child);
                  return child;
                },
              };
              Object.keys(props).forEach((key) => {
                if (key !== "class") node[key] = props[key];
              });
              (Array.isArray(children) ? children : [children]).filter(Boolean).forEach((child) => node.appendChild(child));
              return node;
            }

            function hasClass(node, className) {
              return String(node && node.className || "").split(/\s+/).includes(className);
            }

            function findAll(node, className, out = []) {
              if (!node) return out;
              if (hasClass(node, className)) out.push(node);
              (node.children || []).forEach((child) => findAll(child, className, out));
              return out;
            }

            global.el = makeNode;
            global.STATE = { project: "task_dashboard" };
            global.getSessionId = (row) => String((row && (row.sessionId || row.id)) || "").trim();
            global.conversationDraftMetaBySession = () => ({ hasDraft: true, hasText: true, attachmentCount: 0, mentionCount: 0 });
            global.conversationDraftTitle = () => "未发送草稿：含文本";

            eval(extractFunction("web/task.js", "buildConversationCountBadges"));

            const wrap = buildConversationCountBadges({ sessionId: "sid-1" }, {
              projectId: "task_dashboard",
              showUnread: false,
            });

            const drafts = findAll(wrap, "draft");
            assert.equal(drafts.length, 1);
            assert.equal(drafts[0].text, "草");
            assert.equal(drafts[0].title, "未发送草稿：含文本");
            """
        )
        proc = subprocess.run(
            ["node", "-e", script, str(REPO_ROOT)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            self.fail(proc.stderr or proc.stdout or "node draft marker regression script failed")


if __name__ == "__main__":
    unittest.main()
