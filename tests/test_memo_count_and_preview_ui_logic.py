import shutil
import subprocess
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("node"), "node is required for UI logic regression checks")
class MemoCountAndPreviewUiLogicTests(unittest.TestCase):
    def test_left_list_memo_badge_uses_total_count_from_memo_summary(self) -> None:
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

            function makeNode(tag, props = {}) {
              return {
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
            }

            global.STATE = { project: "task_dashboard" };
            global.PCONV = {};
            global.el = makeNode;
            global.getSessionId = (row) => String((row && (row.sessionId || row.id)) || "").trim();
            global.conversationDraftMetaBySession = () => ({ hasDraft: false });
            global.convComposerDraftKey = (projectId, sessionId) => `${projectId}::${sessionId}`;
            global.countUnreadConversationMessagesByKey = () => 0;
            global.getConversationMemoStateByKey = () => ({ count: 1, items: [{ id: "memo-1" }] });
            global.countUnreadConversationMemosByKey = () => 1;

            eval(extractFunction("web/task_parts/75-conversation-composer.js", "memoCountText"));
            eval(extractFunction("web/task_parts/75-conversation-composer.js", "conversationMemoSummary"));
            eval(extractFunction("web/task_parts/75-conversation-composer.js", "conversationMemoSummaryCount"));
            eval(extractFunction("web/task_parts/75-conversation-composer.js", "resolveConversationMemoDisplayCount"));
            eval(extractFunction("web/task_parts/75-conversation-composer.js", "conversationMemoCountTitle"));
            eval(extractFunction("web/task.js", "buildConversationCountBadges"));

            const wrap = buildConversationCountBadges({
              id: "sid-1",
              memo_summary: { memo_count: 4 },
            }, {
              projectId: "task_dashboard",
              showUnread: true,
            });

            assert.ok(wrap);
            const memoBadge = wrap.children.find((child) => String(child.className || "").includes("conv-count-dot memo"));
            assert.ok(memoBadge);
            assert.equal(memoBadge.text, "4");
            assert.equal(memoBadge.title, "备忘共 4 条，未消费 1 条");
            """
        )
        proc = subprocess.run(
            ["node", "-e", script, str(REPO_ROOT)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            self.fail(proc.stderr or proc.stdout or "node memo badge regression script failed")

    def test_left_list_memo_badge_falls_back_to_conversation_list_metrics_summary(self) -> None:
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

            function makeNode(tag, props = {}) {
              return {
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
            }

            global.STATE = { project: "task_dashboard" };
            global.PCONV = {};
            global.el = makeNode;
            global.getSessionId = (row) => String((row && (row.sessionId || row.id)) || "").trim();
            global.conversationDraftMetaBySession = () => ({ hasDraft: false });
            global.convComposerDraftKey = (projectId, sessionId) => `${projectId}::${sessionId}`;
            global.countUnreadConversationMessagesByKey = () => 0;
            global.getConversationMemoStateByKey = () => ({ count: 0, items: [] });
            global.countUnreadConversationMemosByKey = () => 0;

            eval(extractFunction("web/task_parts/75-conversation-composer.js", "memoCountText"));
            eval(extractFunction("web/task_parts/75-conversation-composer.js", "conversationMemoSummary"));
            eval(extractFunction("web/task_parts/75-conversation-composer.js", "conversationMemoSummaryCount"));
            eval(extractFunction("web/task_parts/75-conversation-composer.js", "resolveConversationMemoDisplayCount"));
            eval(extractFunction("web/task_parts/75-conversation-composer.js", "conversationMemoCountTitle"));
            eval(extractFunction("web/task.js", "buildConversationCountBadges"));

            const wrap = buildConversationCountBadges({
              id: "sid-2",
              conversation_list_metrics: {
                memo_summary: { memo_count: 6 },
              },
            }, {
              projectId: "task_dashboard",
              showUnread: true,
            });

            assert.ok(wrap);
            const memoBadge = wrap.children.find((child) => String(child.className || "").includes("conv-count-dot memo"));
            assert.ok(memoBadge);
            assert.equal(memoBadge.text, "6");
            assert.equal(memoBadge.title, "备忘共 6 条");
            """
        )
        proc = subprocess.run(
            ["node", "-e", script, str(REPO_ROOT)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            self.fail(proc.stderr or proc.stdout or "node memo badge metrics regression script failed")

    def test_detail_memo_entry_uses_total_count_from_light_summary(self) -> None:
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

            const nodes = {
              detailMemoBtn: { style: { display: "none" }, title: "", onclick: null },
              detailMemoCountDot: { style: { display: "none" }, textContent: "", title: "" },
            };

            global.document = {
              getElementById(id) {
                return nodes[id] || null;
              },
            };
            global.PCONV = { memoDrawerOpen: false, memoDrawerSessionKey: "" };
            global.convComposerDraftKey = (projectId, sessionId) => `${projectId}::${sessionId}`;
            global.getConversationMemoStateByKey = () => ({ count: 0, items: [] });
            global.countUnreadConversationMemosByKey = () => 0;
            global.findConversationSessionById = () => ({ id: "sid-1", memo_summary: { memo_count: 3 } });
            global.hideConversationMemoEntry = () => {};

            eval(extractFunction("web/task_parts/75-conversation-composer.js", "memoCountText"));
            eval(extractFunction("web/task_parts/75-conversation-composer.js", "conversationMemoSummary"));
            eval(extractFunction("web/task_parts/75-conversation-composer.js", "conversationMemoSummaryCount"));
            eval(extractFunction("web/task_parts/75-conversation-composer.js", "resolveConversationMemoDisplayCount"));
            eval(extractFunction("web/task_parts/75-conversation-composer.js", "conversationMemoCountTitle"));
            eval(extractFunction("web/task_parts/75-conversation-composer.js", "renderConversationMemoEntry"));

            renderConversationMemoEntry({
              projectId: "task_dashboard",
              sessionId: "sid-1",
            });

            assert.equal(nodes.detailMemoBtn.style.display, "");
            assert.equal(nodes.detailMemoBtn.title, "会话需求暂存与备忘 · 备忘共 3 条");
            assert.equal(nodes.detailMemoCountDot.style.display, "inline-flex");
            assert.equal(nodes.detailMemoCountDot.textContent, "3");
            assert.equal(nodes.detailMemoCountDot.title, "备忘共 3 条");
            """
        )
        proc = subprocess.run(
            ["node", "-e", script, str(REPO_ROOT)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            self.fail(proc.stderr or proc.stdout or "node memo entry regression script failed")

    def test_normalize_conversation_session_keeps_memo_summary(self) -> None:
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

            global.STATE = { project: "task_dashboard" };
            global.looksLikeSessionId = () => true;
            global.firstNonEmptyText = (values, fallback = "") => {
              for (const value of Array.isArray(values) ? values : [values]) {
                const text = String(value == null ? "" : value).trim();
                if (text) return text;
              }
              return fallback;
            };
            global.resolveConversationSessionPresentation = (raw, channelName, sid) => ({
              alias: String(raw.alias || ""),
              displayChannel: channelName || sid,
              displayName: String(raw.display_name || channelName || sid),
              displayNameSource: "channel_name",
              agentDisplayName: "",
              agentDisplayNameSource: "",
              agentNameState: "",
              agentDisplayIssue: "",
            });
            global.normalizeHeartbeatTaskItemsClient = () => [];
            global.normalizeHeartbeatSummaryClient = () => ({});
            global.normalizeConversationTeamExpansionHint = () => null;
            global.normalizeSessionEnvironmentValue = (value) => String(value || "stable");
            global.normalizeSessionModel = (value) => String(value || "");
            global.normalizeReasoningEffort = (value) => String(value || "");
            global.boolLike = (value) => !!value;
            global.normalizeDisplayState = (value, fallback = "idle") => String(value || fallback || "idle");
            global.normalizeLatestRunSummary = (value) => value || {};
            global.normalizeLatestEffectiveRunSummary = (value) => value || {};
            global.normalizeRuntimeState = (value) => value || {};
            global.normalizeProjectExecutionContext = (value) => value || null;
            global.normalizeTaskTrackingClient = (value) => value || null;
            global.normalizeConversationListMetricsClient = (value) => value || null;

            eval(extractFunction("web/task_parts/74-session-bootstrap-and-sessions.js", "normalizeConversationSession"));

            const normalized = normalizeConversationSession({
              id: "sid-3",
              project_id: "task_dashboard",
              channel_name: "子级04",
              memo_summary: { memo_count: 3, memo_summary_source: "conversation_memos" },
            });

            assert.ok(normalized);
            assert.equal(normalized.memo_summary.memo_count, 3);
            assert.equal(normalized.memoSummary.memo_count, 3);
            """
        )
        proc = subprocess.run(
            ["node", "-e", script, str(REPO_ROOT)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            self.fail(proc.stderr or proc.stdout or "node normalize memo summary regression script failed")

    def test_typing_does_not_rerender_attachment_preview_nodes(self) -> None:
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

            global.PCONV = { composerBoundDraftKey: "task_dashboard::sid-1" };
            global.currentConvComposerDraftKey = () => "task_dashboard::sid-1";
            let syncCalls = 0;
            let mentionRenderCalls = 0;
            let replyRenderCalls = 0;
            let attachmentRenderCalls = 0;
            let sendButtonSyncCalls = 0;
            global.syncConvComposerMentionsByKeyFromText = (key, text) => {
              assert.equal(key, "task_dashboard::sid-1");
              assert.equal(text, "继续输入");
              syncCalls += 1;
              return [];
            };
            global.renderConvComposerMentionsByKey = () => { mentionRenderCalls += 1; };
            global.renderConvComposerReplyContextByKey = () => { replyRenderCalls += 1; };
            global.renderAttachments = () => { attachmentRenderCalls += 1; };
            global.syncConversationComposerSendButtonByDraft = () => { sendButtonSyncCalls += 1; };

            eval(extractFunction("web/task_parts/75-conversation-composer.js", "setConvComposerTextForCurrentSession"));

            setConvComposerTextForCurrentSession("继续输入");

            assert.equal(syncCalls, 1);
            assert.equal(mentionRenderCalls, 1);
            assert.equal(replyRenderCalls, 1);
            assert.equal(sendButtonSyncCalls, 1);
            assert.equal(attachmentRenderCalls, 0);
            """
        )
        proc = subprocess.run(
            ["node", "-e", script, str(REPO_ROOT)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            self.fail(proc.stderr or proc.stdout or "node composer preview stability regression script failed")


if __name__ == "__main__":
    unittest.main()
