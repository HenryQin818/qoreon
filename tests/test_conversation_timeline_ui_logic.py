import shutil
import subprocess
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("node"), "node is required for UI logic regression checks")
class ConversationTimelineUiLogicTests(unittest.TestCase):
    def test_timeline_render_signature_reuses_dom_when_history_is_unchanged(self) -> None:
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

            const file = "web/task_parts/60-conversation.js";
            const source = fs.readFileSync(path.join(repoRoot, file), "utf8");
            assert.ok(source.includes("shouldReuseConversationTimelineDom(timeline, timelineRenderSignature"));

            global.STATE = { project: "task_dashboard" };
            global.PCONV = {
              detailMap: Object.create(null),
              processTrailByRun: Object.create(null),
              runActionBusy: Object.create(null),
              bubbleExpanded: new Set(),
              bubblePendingExpand: new Set(),
            };
            global.firstNonEmptyText = (values) => {
              for (const value of values || []) {
                const text = String(value || "").trim();
                if (text) return text;
              }
              return "";
            };

            eval(extractFunction(file, "compactConversationTimelineSignatureText"));
            eval(extractFunction(file, "conversationAttachmentSignature"));
            eval(extractFunction(file, "buildConversationTimelineRenderSignature"));
            eval(extractFunction(file, "shouldReuseConversationTimelineDom"));
            eval(extractFunction(file, "markConversationTimelineRenderSignature"));

            const ctx = { projectId: "task_dashboard", sessionId: "sid-1" };
            const runs = [{
              id: "run-1",
              status: "done",
              createdAt: "2026-04-11T19:00:00+0800",
              messagePreview: "用户消息",
              lastPreview: "助手消息",
              attachments: [{ url: "/.runs/r/attachments/a.png", originalName: "a.png" }],
            }];
            const timeline = { dataset: {} };
            const sig1 = buildConversationTimelineRenderSignature(ctx, {
              displayRuns: runs,
              runtimeState: { status: "done" },
            });
            assert.equal(shouldReuseConversationTimelineDom(timeline, sig1), false);
            markConversationTimelineRenderSignature(timeline, sig1);
            assert.equal(shouldReuseConversationTimelineDom(timeline, sig1), true);
            assert.equal(shouldReuseConversationTimelineDom(timeline, sig1, { forceScroll: true }), false);

            PCONV.detailMap["run-1"] = {
              loading: false,
              fetchedAt: Date.now() + 9999,
              full: { run: { status: "done" }, lastMessage: "助手消息" },
            };
            const sig2 = buildConversationTimelineRenderSignature(ctx, {
              displayRuns: runs,
              runtimeState: { status: "done" },
            });
            assert.notEqual(sig2, sig1);
            markConversationTimelineRenderSignature(timeline, sig2);
            PCONV.detailMap["run-1"].fetchedAt = Date.now() + 19999;
            const sig2b = buildConversationTimelineRenderSignature(ctx, {
              displayRuns: runs,
              runtimeState: { status: "done" },
            });
            assert.equal(sig2b, sig2);
            assert.equal(shouldReuseConversationTimelineDom(timeline, sig2b), true);

            PCONV.processTrailByRun["run-1"] = {
              status: "running",
              updatedAt: 1,
              rows: [{ text: "新的执行进展" }],
            };
            const sig3 = buildConversationTimelineRenderSignature(ctx, {
              displayRuns: runs,
              runtimeState: { status: "running", active_run_id: "run-1" },
            });
            assert.notEqual(sig3, sig1);
            assert.equal(shouldReuseConversationTimelineDom(timeline, sig3), false);
            """
        )
        proc = subprocess.run(
            ["node", "-e", script, str(REPO_ROOT)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            self.fail(proc.stderr or proc.stdout or "node timeline render reuse regression script failed")

    def test_stable_history_rows_keep_attachment_dom_identity(self) -> None:
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
            global.PCONV = {
              bubbleExpanded: new Set(),
              bubblePendingExpand: new Set(),
            };
            global.firstNonEmptyText = (values) => {
              for (const value of values || []) {
                const text = String(value || "").trim();
                if (text) return text;
              }
              return "";
            };
            global.resolveAttachmentUrl = (att) => String((att && (att.url || att.dataUrl || att.preview_url || att.path)) || "");
            global.getRunDisplayState = (run) => String((run && run.status) || "idle");
            global.isRunWorking = (status) => ["running", "queued", "retry_waiting"].includes(String(status || ""));

            const file = "web/task_parts/60-conversation.js";
            eval(extractFunction(file, "compactConversationTimelineSignatureText"));
            eval(extractFunction(file, "conversationTimelineStableAttachmentKey"));
            eval(extractFunction(file, "conversationStableAttachmentSignature"));
            eval(extractFunction(file, "buildConversationStableAttachmentPatchMap"));
            eval(extractFunction(file, "syncConversationStableTimelineRowAttachments"));
            eval(extractFunction(file, "conversationTimelineBubbleExpansionSignature"));
            eval(extractFunction(file, "conversationTimelineStableRowSignature"));
            eval(extractFunction(file, "isConversationTimelineTerminalStatus"));
            eval(extractFunction(file, "canReuseConversationStableTimelineRow"));
            eval(extractFunction(file, "buildConversationStableTimelineRowKey"));
            eval(extractFunction(file, "markConversationStableTimelineRow"));
            eval(extractFunction(file, "buildConversationStableTimelineRowReuseMap"));
            eval(extractFunction(file, "reuseConversationStableTimelineRow"));
            eval(extractFunction(file, "syncConversationTimelineChildren"));

            const localAttachment = {
              localId: "local-attachment-1",
              dataUrl: "blob:local-image",
              originalName: "demo.png",
              mimeType: "image/png",
              uploadState: "uploading",
            };
            const confirmedAttachment = {
              local_id: "local-attachment-1",
              attachment_id: "server-attachment-9",
              url: "/.runs/run-1/attachments/demo.png",
              filename: "demo.png",
              mime_type: "image/png",
              status: "done",
            };
            assert.equal(conversationTimelineStableAttachmentKey(localAttachment, 0), "local-attachment-1");
            assert.equal(conversationTimelineStableAttachmentKey(confirmedAttachment, 0), "local-attachment-1");
            assert.equal(
              conversationStableAttachmentSignature([localAttachment]),
              conversationStableAttachmentSignature([confirmedAttachment]),
            );

            const ctx = { projectId: "task_dashboard", sessionId: "sid-1" };
            const baseRun = { id: "run-1", status: "done", createdAt: "2026-04-11T20:00:00+0800" };
            const sigA = conversationTimelineStableRowSignature({
              kind: "user",
              runId: "run-1",
              run: baseRun,
              status: "done",
              text: "上传图片",
              attachments: [localAttachment],
              bubbleKeys: ["run-1:user"],
            });
            const sigB = conversationTimelineStableRowSignature({
              kind: "user",
              runId: "run-1",
              run: { ...baseRun, status: "done" },
              status: "done",
              text: "上传图片",
              attachments: [confirmedAttachment],
              bubbleKeys: ["run-1:user"],
            });
            assert.equal(sigA, sigB);
            assert.equal(canReuseConversationStableTimelineRow(baseRun, null, "done", {}), true);
            assert.equal(canReuseConversationStableTimelineRow({ ...baseRun, status: "running" }, null, "running", {}), false);

            const img = {
              tagName: "IMG",
              attrs: { src: "blob:local-image", alt: "" },
              dataset: { conversationAttachmentKey: "local-attachment-1", conversationAttachmentSrc: "blob:local-image" },
              getAttribute(name) { return this.attrs[name] || ""; },
              setAttribute(name, value) { this.attrs[name] = String(value); },
            };
            const row = { querySelectorAll: () => [img] };
            syncConversationStableTimelineRowAttachments(row, [confirmedAttachment]);
            assert.equal(img.attrs.src, "/.runs/run-1/attachments/demo.png");
            assert.equal(img.dataset.conversationAttachmentSrc, "/.runs/run-1/attachments/demo.png");
            assert.equal(img.attrs.alt, "demo.png");

            const stableKey = buildConversationStableTimelineRowKey("user", "run-1");
            const stableRow = {
              dataset: {},
              querySelectorAll: () => [img],
            };
            markConversationStableTimelineRow(stableRow, stableKey, sigB);

            function relink(host) {
              host.firstChild = host.children[0] || null;
              for (let i = 0; i < host.children.length; i += 1) {
                host.children[i].nextSibling = host.children[i + 1] || null;
              }
            }

            const staleRow = { dataset: {}, querySelectorAll: () => [] };
            const timeline = {
              children: [stableRow, staleRow],
              firstChild: stableRow,
              querySelectorAll(selector) {
                if (selector !== ".msgrow[data-conversation-stable-row-key]") return [];
                return this.children.filter((item) => String((item && item.dataset && item.dataset.conversationStableRowKey) || "").trim());
              },
              insertBefore(node, cursor) {
                const currentIndex = this.children.indexOf(node);
                if (currentIndex >= 0) this.children.splice(currentIndex, 1);
                const cursorIndex = cursor ? this.children.indexOf(cursor) : -1;
                if (cursorIndex >= 0) this.children.splice(cursorIndex, 0, node);
                else this.children.push(node);
                relink(this);
                return node;
              },
              removeChild(node) {
                const currentIndex = this.children.indexOf(node);
                if (currentIndex >= 0) this.children.splice(currentIndex, 1);
                relink(this);
                return node;
              },
            };
            relink(timeline);

            const reuseMap = buildConversationStableTimelineRowReuseMap(timeline);
            const reusedRow = reuseConversationStableTimelineRow(reuseMap, stableKey, sigB, [confirmedAttachment]);
            assert.equal(reusedRow, stableRow);
            assert.equal(reuseMap.has(stableKey), false);

            const freshRow = { dataset: {}, querySelectorAll: () => [] };
            syncConversationTimelineChildren(timeline, [reusedRow, freshRow]);
            assert.equal(timeline.children[0], stableRow);
            assert.equal(timeline.children[1], freshRow);
            assert.equal(img.attrs.src, "/.runs/run-1/attachments/demo.png");
            """
        )
        proc = subprocess.run(
            ["node", "-e", script, str(REPO_ROOT)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            self.fail(proc.stderr or proc.stdout or "node stable attachment reuse regression script failed")

    def test_running_assistant_progress_stays_visible(self) -> None:
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

            function firstNonEmptyText(values) {
              const list = Array.isArray(values) ? values : [values];
              for (const value of list) {
                const text = String(value || "").trim();
                if (text) return text;
              }
              return "";
            }

            function isRunWorking(raw) {
              const value = String(raw || "").trim().toLowerCase();
              return value === "running" || value === "queued" || value === "retry_waiting" || value === "external_busy";
            }

            eval(extractFunction("web/task_parts/70-conversation-timeline.js", "resolveConversationAssistantBodyMeta"));

            const runningVisible = resolveConversationAssistantBodyMeta({
              status: "running",
              displayAssistantText: "",
              processInfo: {
                latest: "我先直接核架构师这条的真实状态。",
                count: 1,
                items: ["我先直接核架构师这条的真实状态。"],
                reportedCount: 1,
              },
              error: "",
              detailLoading: false,
            });
            assert.equal(runningVisible.inlineText, "我先直接核架构师这条的真实状态。");
            assert.equal(runningVisible.bodyTitle, "最新进展");
            assert.equal(runningVisible.showBody, true);
            assert.equal(runningVisible.placeholder, "");
            assert.equal(runningVisible.needsDetailPrefetch, false);

            const runningNeedsPrefetch = resolveConversationAssistantBodyMeta({
              status: "running",
              displayAssistantText: "",
              processInfo: {
                latest: "",
                count: 0,
                items: [],
                reportedCount: 2,
              },
              error: "",
              detailLoading: false,
            });
            assert.equal(runningNeedsPrefetch.showBody, false);
            assert.equal(runningNeedsPrefetch.needsDetailPrefetch, true);
            assert.equal(runningNeedsPrefetch.bodyTitle, "最新进展");

            const donePlaceholder = resolveConversationAssistantBodyMeta({
              status: "done",
              displayAssistantText: "",
              processInfo: {
                latest: "",
                count: 0,
                items: [],
                reportedCount: 0,
              },
              error: "",
              detailLoading: false,
            });
            assert.equal(donePlaceholder.bodyTitle, "正文");
            assert.equal(donePlaceholder.showBody, true);
            assert.match(donePlaceholder.placeholder, /未生成可展示正文/);
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

    def test_restart_recovery_runs_anchor_after_source_run(self) -> None:
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

            function mergeRunForDisplay(detailRun, row) {
              return Object.assign({}, row || {}, detailRun || {});
            }

            function readRunRestartRecoveryMeta(run) {
              const r = (run && typeof run === "object") ? run : {};
              const triggerType = String(r.trigger_type || r.triggerType || "").trim().toLowerCase();
              if (triggerType !== "restart_recovery_summary" && triggerType !== "restart_recovery") return null;
              const sourceRunIds = Array.isArray(r.restartRecoverySourceRunIds)
                ? r.restartRecoverySourceRunIds.map((item) => String(item || "").trim()).filter(Boolean)
                : [];
              if (!sourceRunIds.length && String(r.restartRecoveryOf || "").trim()) {
                sourceRunIds.push(String(r.restartRecoveryOf || "").trim());
              }
              return {
                sourceRunIds,
              };
            }

            eval(extractFunction("web/task_parts/60-conversation.js", "resolveConversationRestartRecoveryAnchorRunId"));
            eval(extractFunction("web/task_parts/60-conversation.js", "reorderConversationDisplayRunsForTimeline"));

            const source = {
              id: "20260407-163046-a535b1ef",
              createdAt: "2026-04-07T16:30:46+0800",
              status: "error",
              sender_type: "agent",
            };
            const queued = {
              id: "20260407-170855-1eb736be",
              createdAt: "2026-04-07T17:08:55+0800",
              status: "queued",
              sender_type: "agent",
            };
            const recovery = {
              id: "20260407-164800-c8200139",
              createdAt: "2026-04-07T16:48:00+0800",
              status: "done",
              sender_type: "system",
              trigger_type: "restart_recovery_summary",
              restartRecoveryOf: "20260407-163046-a535b1ef",
              restartRecoverySourceRunIds: ["20260407-163046-a535b1ef"],
              restartRecoveryBatchId: "20260407-164800-c8200139",
            };

            const ordered = reorderConversationDisplayRunsForTimeline(
              [source, queued, recovery],
              {},
              { sessionId: "019ce08e-7025-73b3-b62d-35299fac2d87" }
            ).map((row) => row.id);

            assert.deepEqual(ordered, [
              "20260407-163046-a535b1ef",
              "20260407-164800-c8200139",
              "20260407-170855-1eb736be",
            ]);
            """
        )
        proc = subprocess.run(
            ["node", "-e", script, str(REPO_ROOT)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            self.fail(proc.stderr or proc.stdout or "node restart recovery regression script failed")

    def test_receipt_projection_prefers_source_compact_card(self) -> None:
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

            eval(extractFunction("web/task_parts/70-conversation-timeline.js", "conversationReceiptProjectionPendingCount"));
            eval(extractFunction("web/task_parts/70-conversation-timeline.js", "resolveConversationReceiptProjectionPresentation"));

            const projection = {
              items: [
                {
                  sourceRunId: "src-1",
                  callbackRunId: "cb-1",
                },
              ],
              pendingActions: [
                {
                  sourceRunId: "src-1",
                  callbackRunId: "cb-1",
                  title: "请继续收口",
                },
              ],
              rollup: {
                totalCallbacks: 1,
                pendingActionCount: 1,
              },
            };

            const ordinary = resolveConversationReceiptProjectionPresentation({
              projection,
              callbackEventMeta: null,
              restartRecoveryMeta: null,
              receiptCardVisible: false,
            });
            assert.equal(ordinary.hasProjection, true);
            assert.equal(ordinary.pendingCount, 1);
            assert.equal(ordinary.totalCount, 1);
            assert.equal(ordinary.sourceCompact, true);
            assert.equal(ordinary.assistantStack, false);

            const receiptInbound = resolveConversationReceiptProjectionPresentation({
              projection,
              callbackEventMeta: null,
              restartRecoveryMeta: null,
              receiptCardVisible: true,
            });
            assert.equal(receiptInbound.sourceCompact, false);

            const systemCallback = resolveConversationReceiptProjectionPresentation({
              projection,
              callbackEventMeta: { eventType: "done" },
              restartRecoveryMeta: null,
              receiptCardVisible: false,
            });
            assert.equal(systemCallback.sourceCompact, false);
            assert.equal(systemCallback.assistantStack, false);
            """
        )
        proc = subprocess.run(
            ["node", "-e", script, str(REPO_ROOT)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            self.fail(proc.stderr or proc.stdout or "node receipt projection regression script failed")

    def test_assistant_generated_image_attachments_use_strict_truth_filter(self) -> None:
        conversation_text = (REPO_ROOT / "web" / "task_parts" / "60-conversation.js").read_text(encoding="utf-8")
        timeline_text = (REPO_ROOT / "web" / "task_parts" / "70-conversation-timeline.js").read_text(encoding="utf-8")
        self.assertIn("const aiRow = renderConversationAssistantFamily({", conversation_text)
        self.assertIn("const userInputAttachments = collectConversationUserInputAttachments(attachments);", conversation_text)
        self.assertIn("attachments: userInputAttachments", conversation_text)
        self.assertIn("attachments: assistantGeneratedAttachments", conversation_text)
        self.assertIn("attachments: visibleGeneratedAttachments", timeline_text)

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

            const file = "web/task_parts/70-conversation-timeline.js";
            global.firstNonEmptyText = (values) => {
              for (const value of values || []) {
                const text = String(value || "").trim();
                if (text) return text;
              }
              return "";
            };
            global.isImageAttachment = (att) => String((att && att.mimeType) || "").toLowerCase().startsWith("image/");
            global.resolveAttachmentUrl = (att) => String((att && att.url) || "").trim();

            eval(extractFunction(file, "conversationAttachmentRole"));
            eval(extractFunction(file, "isConversationAssistantGeneratedMediaAttachment"));
            eval(extractFunction(file, "isConversationAssistantGeneratedImageAttachment"));
            eval(extractFunction(file, "isConversationUserInputAttachment"));
            eval(extractFunction(file, "conversationAttachmentIdentityKey"));
            eval(extractFunction(file, "mergeConversationAttachmentLists"));
            eval(extractFunction(file, "filterConversationBubbleAttachments"));
            eval(extractFunction(file, "firstConversationGeneratedMediaAttachmentUrl"));
            eval(extractFunction(file, "firstConversationGeneratedMediaCount"));
            eval(extractFunction(file, "conversationGeneratedMediaTextHasSignal"));
            eval(extractFunction(file, "resolveConversationGeneratedMediaUiMeta"));

            const generatedImage = {
              url: "/.runs/r/attachments/generated.png",
              mimeType: "image/png",
              source: "generated",
              generatedBy: "codex_imagegen",
              attachment_role: "assistant",
            };
            const generatedLegacyImage = {
              url: "/.runs/r/attachments/generated-legacy.png",
              mimeType: "image/png",
              source: "generated",
              generatedBy: "codex_imagegen",
            };
            const ordinaryAssistantImage = {
              url: "/.runs/r/attachments/plain.png",
              mimeType: "image/png",
              attachment_role: "assistant",
            };
            const userUploadImage = {
              url: "/.runs/r/attachments/user-upload.png",
              mimeType: "image/png",
              attachment_role: "user",
              source: "upload",
            };
            const legacyUserUploadImage = {
              url: "/.runs/r/attachments/legacy-user-upload.png",
              mimeType: "image/png",
              source: "upload",
            };
            const generatedNonImage = {
              url: "/.runs/r/attachments/generated.txt",
              mimeType: "text/plain",
              source: "generated",
              attachment_role: "assistant",
            };
            const foreignRoleImage = {
              url: "/.runs/r/attachments/foreign.png",
              mimeType: "image/png",
              source: "generated",
              attachment_role: "user",
            };

            assert.equal(isConversationAssistantGeneratedMediaAttachment(generatedImage), true);
            assert.equal(isConversationAssistantGeneratedMediaAttachment(generatedLegacyImage), true);
            assert.equal(isConversationAssistantGeneratedMediaAttachment(ordinaryAssistantImage), false);
            assert.equal(isConversationAssistantGeneratedImageAttachment(generatedNonImage), false);
            assert.equal(isConversationAssistantGeneratedImageAttachment(foreignRoleImage), false);
            assert.equal(isConversationUserInputAttachment(generatedImage), false);
            assert.equal(isConversationUserInputAttachment(generatedLegacyImage), false);
            assert.equal(isConversationUserInputAttachment(ordinaryAssistantImage), false);
            assert.equal(isConversationUserInputAttachment(userUploadImage), true);
            assert.equal(isConversationUserInputAttachment(legacyUserUploadImage), true);

            assert.deepEqual(
              filterConversationBubbleAttachments("assistant", [
                generatedImage,
                generatedLegacyImage,
                ordinaryAssistantImage,
                generatedNonImage,
                foreignRoleImage,
              ]),
              [generatedImage, generatedLegacyImage],
            );
            assert.deepEqual(
              filterConversationBubbleAttachments("user", [
                ordinaryAssistantImage,
                generatedImage,
                generatedLegacyImage,
                userUploadImage,
                legacyUserUploadImage,
              ]),
              [userUploadImage, legacyUserUploadImage],
            );
            assert.equal(
              firstConversationGeneratedMediaAttachmentUrl([
                ordinaryAssistantImage,
                generatedNonImage,
                generatedImage,
              ]),
              "/.runs/r/attachments/generated.txt",
            );
            assert.deepEqual(
              mergeConversationAttachmentLists([
                [ordinaryAssistantImage],
                [{ ...ordinaryAssistantImage }, generatedImage],
              ]),
              [ordinaryAssistantImage, generatedImage],
            );
            assert.deepEqual(
              resolveConversationGeneratedMediaUiMeta({
                status: "running",
                processInfo: { latest: "Codex Image Gen 正在生成图片", count: 1, items: [] },
                attachments: [],
              }),
              {
                isGeneratedMediaRun: true,
                phase: "generating",
                stateSubText: "图片生成中，结果通常以附件返回",
                interruptText: "打断生成",
              },
            );
            assert.deepEqual(
              resolveConversationGeneratedMediaUiMeta({
                status: "done",
                generatedMediaCount: 1,
                generatedMediaSummary: "已生成1张图片",
                attachments: [],
              }),
              {
                isGeneratedMediaRun: true,
                phase: "generated",
                stateSubText: "图片结果已生成，可查看图片结果",
                interruptText: "打断生成",
              },
            );
            assert.deepEqual(
              resolveConversationGeneratedMediaUiMeta({
                status: "done",
                generatedMediaStatus: "failed",
                generatedMediaSummary: "图片生成未完成",
                attachments: [],
              }),
              {
                isGeneratedMediaRun: true,
                phase: "failed",
                stateSubText: "图片生成未完成，可查看过程并重试",
                interruptText: "打断生成",
              },
            );
            assert.deepEqual(
              resolveConversationGeneratedMediaUiMeta({
                status: "done",
                attachments: [generatedImage],
              }),
              {
                isGeneratedMediaRun: true,
                phase: "generated",
                stateSubText: "图片结果已生成，可查看图片结果",
                interruptText: "打断生成",
              },
            );
            assert.deepEqual(
              resolveConversationGeneratedMediaUiMeta({
                status: "interrupted",
                processInfo: { latest: "output/imagegen 本轮生成被中断", count: 1, items: [] },
                attachments: [],
              }),
              {
                isGeneratedMediaRun: true,
                phase: "interrupted",
                stateSubText: "图片生成已中断，可查看过程并重试",
                interruptText: "打断生成",
              },
            );
            assert.deepEqual(
              resolveConversationGeneratedMediaUiMeta({
                status: "running",
                processInfo: { latest: "正在执行普通 shell 命令", count: 1, items: [] },
                attachments: [userUploadImage],
              }),
              {
                isGeneratedMediaRun: false,
                phase: "",
                stateSubText: "",
                interruptText: "打断执行",
              },
            );
            """
        )
        proc = subprocess.run(
            ["node", "-e", script, str(REPO_ROOT)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            self.fail(proc.stderr or proc.stdout or "node assistant generated attachment filter regression script failed")

    def test_run_process_rows_render_actions_as_independent_nodes(self) -> None:
        script = textwrap.dedent(
            r"""
            const assert = require("node:assert/strict");
            const fs = require("node:fs");
            const path = require("node:path");
            const repoRoot = process.argv[1];
            const file = "web/task_parts/76-runs-and-drawer.js";
            const source = fs.readFileSync(path.join(repoRoot, file), "utf8");

            function extractFunction(name) {
              const signature = new RegExp(`function ${name}\\(`);
              const match = signature.exec(source);
              if (!match) throw new Error(`missing function ${name}`);
              const start = match.index;
              const braceStart = source.indexOf("{", start);
              let depth = 0;
              for (let i = braceStart; i < source.length; i += 1) {
                const ch = source[i];
                if (ch === "{") depth += 1;
                else if (ch === "}") {
                  depth -= 1;
                  if (depth === 0) return source.slice(start, i + 1);
                }
              }
              throw new Error(`unterminated function ${name}`);
            }

            function firstNonEmptyText(values) {
              for (const value of values || []) {
                const text = String(value == null ? "" : value).trim();
                if (text) return text;
              }
              return "";
            }
            function normalizeProcessTimestamp(value) {
              return String(value == null ? "" : value).trim();
            }
            eval(extractFunction("isUnsafeProcessRowKind"));
            eval(extractFunction("containsUnsafeProcessMarker"));
            eval(extractFunction("normalizeProcessMessageText"));
            eval(extractFunction("extractStructuredProcessRowTime"));
            eval(extractFunction("firstProcessMetaText"));
            eval(extractFunction("clampRunProcessDisplayText"));
            eval(extractFunction("looksLikeRawProcessJsonText"));
            eval(extractFunction("isLowValueRunProcessActionTarget"));
            eval(extractFunction("firstRunProcessActionTargetText"));
            eval(extractFunction("structuredProcessRowFallbackText"));
            eval(extractFunction("normalizeRunProcessTimelineRow"));
            eval(extractFunction("isRunProcessActionRow"));
            eval(extractFunction("normalizeRunProcessActionType"));
            eval(extractFunction("runProcessActionLabel"));
            eval(extractFunction("runProcessRowCallId"));
            eval(extractFunction("runProcessActionEventText"));
            eval(extractFunction("isAssistantProgressProcessRow"));
            eval(extractFunction("isRunProcessToolStartRow"));
            eval(extractFunction("isRunProcessToolFailedClosingRow"));
            eval(extractFunction("isRunProcessToolCompletedClosingRow"));
            eval(extractFunction("buildRunProcessCallStatusIndex"));
            eval(extractFunction("normalizeRunProcessActionStatus"));
            eval(extractFunction("runProcessActionStatusLabel"));
            eval(extractFunction("runProcessActionTarget"));
            eval(extractFunction("runProcessActionErrorSummary"));
            eval(extractFunction("buildRunProcessActionNode"));
            eval(extractFunction("buildRunProcessStepGroups"));

            const mixed = buildRunProcessStepGroups([
              { text: "读取任务规格", at: "2026-05-09T10:00:00+08:00" },
              { text: "执行命令: rg processRows", event_type: "command_execution", item_type: "command_execution" },
              { text: "更新文件", event_type: "file_change", item_type: "file_change" },
              { text: "完成抽屉渲染调整" },
              { text: "调用工具: apply_patch", event_type: "collab_tool_call", item_type: "tool_call" },
            ]);
            assert.equal(mixed.stepCount, 2);
            assert.equal(mixed.actionCount, 3);
            assert.equal(mixed.groups.length, 5);
            assert.equal(mixed.groups[0].kind, "step");
            assert.equal(mixed.groups[1].kind, "action");
            assert.equal(mixed.groups[1].action.label, "命令");
            assert.equal(mixed.groups[1].action.typeKey, "command");
            assert.equal(mixed.groups[2].action.label, "编辑");
            assert.equal(mixed.groups[4].action.label, "消息");

            const actionOnly = buildRunProcessStepGroups([
              { text: "执行命令: build", event_type: "command_execution", item_type: "command_execution" },
              { text: "工具完成: node --check", event_type: "tool_completed", item_type: "tool_call" },
            ]);
            assert.equal(actionOnly.stepCount, 0);
            assert.equal(actionOnly.actionCount, 2);
            assert.equal(actionOnly.groups.length, 2);
            assert.equal(actionOnly.groups[0].kind, "action");
            assert.equal(actionOnly.groups[0].synthetic, undefined);
            assert.equal(actionOnly.groups[0].text.includes("启动与准备动作"), false);
            assert.equal(actionOnly.groups[0].action.status, "running");
            assert.equal(actionOnly.groups[1].action.status, "completed");

            const pairedActions = buildRunProcessStepGroups([
              { text: "Bash: node --check", event_type: "tool_started", item_type: "function_call", call_id: "call_bash", title: "Bash" },
              { text: "Bash 完成", event_type: "tool_completed", item_type: "function_call_result", call_id: "call_bash" },
              { text: "Read: server.py", event_type: "tool_started", item_type: "function_call", call_id: "call_read", title: "Read" },
              { text: "进展：正在整理结果", event_type: "assistant_progress" },
              { text: "Write: bad.py", event_type: "tool_started", item_type: "function_call", call_id: "call_write", title: "Write" },
              { text: "Write 失败", event_type: "tool_failed", item_type: "function_call_result", call_id: "call_write", error_summary: "permission denied" },
            ]);
            assert.equal(pairedActions.groups[0].action.callId, "call_bash");
            assert.equal(pairedActions.groups[0].action.status, "completed");
            assert.equal(pairedActions.groups[0].action.statusLabel, "已完成");
            assert.equal(pairedActions.groups[2].action.status, "running");
            assert.equal(pairedActions.groups[2].action.statusLabel, "进行中");
            assert.equal(pairedActions.groups[3].action.status, "completed");
            assert.equal(pairedActions.groups[3].action.statusLabel, "进展记录");
            assert.equal(pairedActions.groups[4].action.status, "failed");
            assert.equal(pairedActions.groups[4].action.statusLabel, "失败");

            const typeCases = [
              [{ text: "Read web/task.js", event_type: "file_read" }, "read"],
              [{ text: "更新文件", event_type: "file_change" }, "edit"],
              [{ text: "执行命令", event_type: "command_started" }, "command"],
              [{ text: "检索资料", event_type: "search_query" }, "search"],
              [{ text: "打开页面", event_type: "browser_open" }, "web"],
              [{ text: "发送回执", event_type: "collab_receipt" }, "message"],
              [{ text: "调用工具", event_type: "tool_started", item_type: "function_call" }, "tool"],
              [{ text: "系统事件", event_type: "runtime_event" }, "system"],
              [{ text: "自定义事件", event_type: "custom_event" }, "unknown"],
            ];
            assert.deepEqual(typeCases.map(([row]) => normalizeRunProcessActionType(row)), typeCases.map(([, key]) => key));

            const statusRows = [
              { text: "等待", event_type: "tool_call", status: "pending" },
              { text: "开始", event_type: "tool_started" },
              { text: "完成", event_type: "tool_completed" },
              { text: "失败", event_type: "tool_error" },
              { text: "取消", event_type: "tool_cancelled" },
              { text: "跳过", event_type: "tool_skipped" },
            ];
            assert.deepEqual(statusRows.map((row) => normalizeRunProcessActionStatus(row)), [
              "pending",
              "running",
              "completed",
              "failed",
              "cancelled",
              "skipped",
            ]);

            const noRawJson = buildRunProcessStepGroups([
              { event_type: "tool_started", item_type: "function_call", title: "Read server.py", rawContent: [{ text: "hidden reasoning" }] },
            ]);
            assert.equal(noRawJson.groups[0].kind, "action");
            assert.equal(noRawJson.groups[0].text.includes("rawContent"), false);
            assert.equal(noRawJson.groups[0].text.includes("hidden reasoning"), false);
            assert.equal(noRawJson.groups[0].action.target, "Read server.py");

            const claudeActions = buildRunProcessStepGroups([
              {
                event_type: "file_read",
                item_type: "file_read",
                source: "claude",
                path: "web/task_parts/70-conversation-timeline.js",
                text: "读取文件",
              },
              {
                event_type: "tool_started",
                item_type: "function_call",
                source: "claude",
                title: "AskUserQuestion",
                text: "claude",
              },
              {
                event_type: "tool_started",
                item_type: "function_call",
                source: "claude",
              },
            ]);
            assert.equal(claudeActions.groups[0].action.target, "web/task_parts/70-conversation-timeline.js");
            assert.equal(claudeActions.groups[1].action.target, "AskUserQuestion");
            assert.notEqual(claudeActions.groups[0].action.target, "claude");
            assert.notEqual(claudeActions.groups[1].action.target, "claude");
            assert.notEqual(claudeActions.groups[2].action.target, "claude");
            assert.equal(claudeActions.groups[2].text.includes("claude"), false);

            const failedLong = buildRunProcessStepGroups([
              {
                text: "执行命令: " + "node ".repeat(120),
                event_type: "command_failed",
                item_type: "command_execution",
                command: "node " + "very-long-command ".repeat(80),
                error_summary: "provider temporary error",
              },
            ]);
            assert.equal(failedLong.groups[0].action.status, "failed");
            assert.equal(failedLong.groups[0].action.statusLabel, "失败");
            assert.equal(failedLong.groups[0].action.text.length <= 180, true);
            assert.equal(failedLong.groups[0].action.detailText.length <= 640, true);
            assert.equal(failedLong.groups[0].action.target.length <= 120, true);
            assert.equal(failedLong.groups[0].action.errorSummary, "provider temporary error");

            const plain = buildRunProcessStepGroups([
              { text: "普通过程消息一" },
              { text: "普通过程消息二", kind: "agent_message" },
              "普通字符串过程消息三",
            ]);
            assert.equal(plain.actionCount, 0);
            assert.equal(plain.stepCount, 3);
            assert.equal(plain.groups.some((group) => group.actions.length > 0), false);
            """
        )
        proc = subprocess.run(
            ["node", "-e", script, str(REPO_ROOT)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            self.fail(proc.stderr or proc.stdout or "node process grouping regression script failed")

    def test_process_step_meta_keeps_action_with_time_on_right(self) -> None:
        timeline_js = (REPO_ROOT / "web/task_parts/70-conversation-timeline.js").read_text()
        timeline_css = (REPO_ROOT / "web/task_parts/70-conversation-timeline.css").read_text()

        self.assertIn('class: "process-step-meta"', timeline_js)
        self.assertIn('meta.appendChild(el("span", {', timeline_js)
        self.assertIn("meta.appendChild(toggle);", timeline_js)
        self.assertNotIn("head.appendChild(toggle);", timeline_js)
        self.assertIn('grid-template-areas: "idx text meta";', timeline_css)
        self.assertIn(".process-step-meta", timeline_css)
        self.assertIn("border: 0;", timeline_css)
        self.assertIn("background: transparent;", timeline_css)
        self.assertNotIn('". action time"', timeline_css)
        self.assertIn("renderRunProcessActionNode", timeline_js)
        self.assertIn('class: "process-panel inline-live"', timeline_js)
        self.assertIn(".process-action-node", timeline_css)
        self.assertIn("overflow-wrap: anywhere;", timeline_css)

    def test_process_action_node_is_collapsed_clickable_and_safe(self) -> None:
        timeline_js = (REPO_ROOT / "web/task_parts/70-conversation-timeline.js").read_text()
        timeline_css = (REPO_ROOT / "web/task_parts/70-conversation-timeline.css").read_text()

        self.assertIn('role: "button"', timeline_js)
        self.assertIn('"aria-expanded": expanded ? "true" : "false"', timeline_js)
        self.assertIn('node.addEventListener("click", toggle);', timeline_js)
        self.assertIn('node.addEventListener("keydown"', timeline_js)
        self.assertIn("toggleProcessActionGroupExpanded(runId, step);", timeline_js)
        self.assertIn("process-action-node-detail", timeline_js)
        self.assertIn("appendProcessActionDetailRow(detail, \"错误\"", timeline_js)
        self.assertIn("appendProcessActionDetailRow(detail, \"来源\"", timeline_js)
        self.assertIn('expanded ? "收起" : "展开"', timeline_js)
        self.assertIn("grid-template-columns: auto minmax(0, 1fr) auto auto;", timeline_css)
        self.assertIn("text-overflow: ellipsis;", timeline_css)
        self.assertIn("white-space: nowrap;", timeline_css)
        self.assertIn(".process-action-node.status-failed", timeline_css)
        self.assertIn(".process-action-node-detail-row.is-error", timeline_css)

    def test_inline_process_entry_shows_count_with_unit(self) -> None:
        timeline_js = (REPO_ROOT / "web/task_parts/70-conversation-timeline.js").read_text()

        self.assertIn('"过程 " + processInfo.count + " 条"', timeline_js)
        self.assertIn('"过程 " + Math.max(processInfo.count, processInfo.items.length) + " 条"', timeline_js)
        self.assertNotIn('"过程 " + processInfo.count) : "展开过程"', timeline_js)
        self.assertNotIn('text: processInfo.count > 0 ? ("过程 " + processInfo.count) : "过程"', timeline_js)

    def test_stale_interrupted_card_is_suppressed_by_latest_done_run(self) -> None:
        conversation_js = (REPO_ROOT / "web/task_parts/60-conversation.js").read_text()
        timeline_js = (REPO_ROOT / "web/task_parts/70-conversation-timeline.js").read_text()

        self.assertIn("const currentLatestDoneRunId = (() => {", conversation_js)
        self.assertIn("currentLatestDoneRunId,", conversation_js)
        self.assertIn("const currentLatestDoneRunId = String(payload.currentLatestDoneRunId || \"\").trim();", timeline_js)
        self.assertIn("const staleErrorWithDoneRun = staleProblemState", timeline_js)
        self.assertIn("最新 run \" + shortId(currentLatestDoneRunId) + \" 已完成", timeline_js)
        self.assertIn("const allowRecoveryOps = !staleErrorNote &&", timeline_js)
        self.assertIn("if (!staleErrorNote && (st === \"error\"", timeline_js)


if __name__ == "__main__":
    unittest.main()
