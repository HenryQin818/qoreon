import shutil
import subprocess
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("node"), "node is required for UI logic regression checks")
class AgentBusyProjectionUiLogicTests(unittest.TestCase):
    def test_busy_projection_badges_and_explanation_are_summary_only(self) -> None:
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

            function firstNonEmptyText(values, fallback = "") {
              for (const value of values || []) {
                const text = String(value == null ? "" : value).trim();
                if (text) return text;
              }
              return fallback;
            }

            function getSessionRuntimeState(session) {
              const runtime = (session && session.runtime_state && typeof session.runtime_state === "object")
                ? session.runtime_state
                : {};
              return {
                display_state: String(runtime.display_state || session.session_display_state || "idle").trim().toLowerCase(),
                external_busy: !!runtime.external_busy,
                active_run_id: String(runtime.active_run_id || ""),
                queued_run_id: String(runtime.queued_run_id || ""),
                queue_depth: Number(runtime.queue_depth || 0) || 0,
                updated_at: String(runtime.updated_at || ""),
                busy_source: String(runtime.busy_source || "").trim().toLowerCase(),
                display_secondary_state: String(runtime.display_secondary_state || "").trim().toLowerCase(),
                external_busy_reason: String(runtime.external_busy_reason || ""),
                active_run_message_kind: String(runtime.active_run_message_kind || "").trim().toLowerCase(),
                active_run_sender_type: String(runtime.active_run_sender_type || "").trim().toLowerCase(),
                active_run_trigger_type: String(runtime.active_run_trigger_type || "").trim().toLowerCase(),
                active_run_visibility: String(runtime.active_run_visibility || "").trim().toLowerCase(),
                active_run_projection_reason: String(runtime.active_run_projection_reason || "").trim().toLowerCase(),
                degraded: !!runtime.degraded,
                degraded_reason: String(runtime.degraded_reason || ""),
              };
            }

            function getSessionStatus(session) {
              const runtime = getSessionRuntimeState(session || {});
              return String((session && session.session_display_state) || runtime.display_state || "idle").trim().toLowerCase();
            }

            function getSessionLatestRunSummary(session) {
              return (session && session.latest_run_summary) || {};
            }

            function getSessionLatestEffectiveRunSummary(session) {
              return (session && session.latest_effective_run_summary) || {};
            }

            function el(tag, attrs = {}) {
              return {
                tag,
                attrs,
                childNodes: [],
                appendChild(child) {
                  this.childNodes.push(child);
                  return child;
                },
              };
            }

            function collectNodesByClass(node, className, out = []) {
              if (!node) return out;
              const cls = String((node.attrs && node.attrs.class) || "");
              if (cls.split(/\s+/).includes(className)) out.push(node);
              for (const child of node.childNodes || []) collectNodesByClass(child, className, out);
              return out;
            }

            const helperFile = "web/task_parts/56-session-communication-status.js";
            eval(extractFunction(helperFile, "sessionStatusBool"));
            eval(extractFunction(helperFile, "normalizeCommunicationProjectionSummaryClient"));
            eval(extractFunction(helperFile, "hasCommunicationProjectionSummaryClientData"));
            eval(extractFunction(helperFile, "normalizeCommunicationStatusSummaryClient"));
            eval(extractFunction(helperFile, "hasCommunicationStatusSummaryClientData"));
            eval(extractFunction(helperFile, "mergeCommunicationStatusSummaryClient"));
            eval(extractFunction(helperFile, "getSessionCommunicationStatusSummary"));
            eval(extractFunction(helperFile, "readConversationBusyProjectionFields"));
            eval(extractFunction(helperFile, "normalizeAgentBusyProjectionMeta"));
            eval(extractFunction(helperFile, "conversationBusyProjectionAuxStatusMeta"));
            eval(extractFunction(helperFile, "conversationProjectionExplanationMeta"));
            eval(extractFunction(helperFile, "conversationRecoveryAuxStatusMeta"));
            eval(extractFunction(helperFile, "conversationCommunicationAuxStatusMeta"));
            eval(extractFunction(helperFile, "conversationAuxStatusMeta"));
            eval(extractFunction("web/task_parts/60-conversation.js", "buildConversationProjectionExplanationCard"));

            const standard = {
              session_display_state: "running",
              runtime_state: {
                display_state: "running",
                active_run_id: "run-standard",
              },
              communication_status_summary: {
                projection_summary: { reason: "" },
              },
            };
            assert.equal(normalizeAgentBusyProjectionMeta(standard), null);
            assert.equal(conversationProjectionExplanationMeta(standard, null, [{ id: "run-standard" }]), null);

            const external = {
              session_display_state: "external_busy",
              runtime_state: {
                display_state: "external_busy",
                external_busy: true,
                busy_source: "external_cli",
                display_secondary_state: "external_busy",
                external_busy_reason: "本机 CLI 正在占用会话",
              },
              communication_status_summary: {
                projection_summary: { reason: "external_busy_no_run" },
              },
            };
            assert.equal(conversationBusyProjectionAuxStatusMeta(external).text, "外部占用");
            assert.equal(conversationProjectionExplanationMeta(external).heading, "会话被外部 CLI 占用");

            const providerTransient = {
              session_display_state: "error",
              runtime_state: {
                display_state: "error",
                busy_source: "external_cli",
                display_secondary_state: "provider_transient",
                active_run_projection_reason: "provider_transient_failure",
                active_run_id: "run-provider",
              },
            };
            assert.equal(normalizeAgentBusyProjectionMeta(providerTransient).text, "远端临时失败");
            assert.equal(conversationProjectionExplanationMeta(providerTransient).heading, "模型服务临时不可用");

            const systemCallback = {
              session_display_state: "running",
              runtime_state: {
                display_state: "running",
                busy_source: "system_callback",
                active_run_message_kind: "system_callback",
                active_run_sender_type: "system",
                active_run_projection_reason: "system_callback_projection_gap",
                active_run_id: "run-callback",
              },
            };
            assert.equal(conversationBusyProjectionAuxStatusMeta(systemCallback).text, "系统回执");
            assert.equal(conversationProjectionExplanationMeta(systemCallback).heading, "当前为系统回执或自动回调");

            const missingSourceRef = {
              session_display_state: "running",
              runtime_state: {
                display_state: "running",
                busy_source: "legacy_run",
                active_run_message_kind: "collab_update",
                active_run_projection_reason: "missing_source_ref",
                active_run_id: "run-missing-source",
              },
            };
            const missingSourceMeta = normalizeAgentBusyProjectionMeta(missingSourceRef);
            assert.equal(missingSourceMeta.key, "missing_source_ref");
            assert.equal(missingSourceMeta.text, "来源缺失");
            assert.equal(missingSourceMeta.heading, "消息来源字段不完整");
            assert.equal(missingSourceMeta.details.length, 3);
            assert.equal(missingSourceMeta.details[0].label, "发生什么");
            assert.match(missingSourceMeta.details[1].text, /回执追踪/);
            assert.match(missingSourceMeta.details[2].text, /source_ref\/callback_to/);
            assert.equal(conversationBusyProjectionAuxStatusMeta(missingSourceRef).text, "来源缺失");
            const missingSourceExplanation = conversationProjectionExplanationMeta(missingSourceRef);
            assert.equal(missingSourceExplanation.heading, "消息来源字段不完整");
            assert.equal(missingSourceExplanation.details.length, 3);
            assert.equal(missingSourceExplanation.chips.includes("原因 missing_source_ref"), true);
            const missingSourceCard = buildConversationProjectionExplanationCard(missingSourceExplanation);
            const detailRows = collectNodesByClass(missingSourceCard, "conv-projection-explain-detail");
            assert.equal(detailRows.length, 3);
            assert.equal(collectNodesByClass(missingSourceCard, "conv-projection-explain-detail-k")[0].attrs.text, "发生什么");

            const legacy = {
              session_display_state: "running",
              runtime_state: {
                display_state: "running",
                busy_source: "legacy_run",
                display_secondary_state: "missing_projection",
                active_run_projection_reason: "legacy_missing_refs",
              },
              communication_status_summary: { receipt_state: "receipt_pending" },
            };
            assert.deepEqual(conversationAuxStatusMeta(legacy).map((item) => item.text), ["待回执", "旧链路"]);

            const hidden = {
              session_display_state: "running",
              runtime_state: {
                display_state: "running",
                active_run_visibility: "hidden",
                active_run_projection_reason: "hidden_message",
                active_run_id: "run-hidden",
              },
            };
            assert.equal(conversationBusyProjectionAuxStatusMeta(hidden).text, "无消息投影");
            assert.equal(conversationProjectionExplanationMeta(hidden).heading, "当前 run 不作为普通正文展示");

            const queued = {
              session_display_state: "queued",
              runtime_state: {
                display_state: "queued",
                queued_run_id: "run-queued",
                active_run_projection_reason: "queued_no_active_run",
              },
            };
            assert.equal(conversationBusyProjectionAuxStatusMeta(queued), null);
            assert.equal(conversationProjectionExplanationMeta(queued).heading, "消息仍在排队");
            assert.equal(conversationProjectionExplanationMeta(queued, null, [], { timelineLoading: true }), null);

            const degraded = {
              session_display_state: "running",
              runtime_state: { display_state: "running" },
              communication_status_summary: {
                projection_summary: { reason: "cache_hit_no_runtime", degraded: true },
              },
            };
            assert.equal(conversationBusyProjectionAuxStatusMeta(degraded).text, "状态降级");
            assert.equal(conversationProjectionExplanationMeta(degraded).heading, "当前状态来自降级数据");

            const idleDegraded = {
              session_display_state: "idle",
              runtime_state: { display_state: "idle" },
              communication_status_summary: {
                projection_summary: { reason: "cache_hit_no_runtime", degraded: true },
              },
            };
            assert.equal(conversationBusyProjectionAuxStatusMeta(idleDegraded), null);
            assert.equal(conversationProjectionExplanationMeta(idleDegraded).heading, "当前状态来自降级数据");

            const idleDegradedBusySource = {
              session_display_state: "idle",
              runtime_state: {
                display_state: "idle",
                busy_source: "degraded_unknown",
                display_secondary_state: "degraded_unknown",
                active_run_projection_reason: "degraded_runtime_index",
              },
              communication_status_summary: {
                projection_summary: { reason: "degraded_runtime_index", degraded: true },
              },
            };
            assert.equal(conversationBusyProjectionAuxStatusMeta(idleDegradedBusySource), null);
            assert.equal(conversationProjectionExplanationMeta(idleDegradedBusySource).heading, "运行时索引缺失或已降级");
            assert.equal(conversationProjectionExplanationMeta(idleDegradedBusySource).details[0].label, "发生什么");
            assert.match(conversationProjectionExplanationMeta(idleDegradedBusySource).details[2].text, /重建通讯录\/运行时索引/);

            const activeRunDegraded = {
              session_display_state: "idle",
              runtime_state: {
                display_state: "idle",
                busy_source: "degraded_unknown",
                active_run_id: "run-degraded",
                active_run_projection_reason: "degraded_runtime_index",
              },
            };
            assert.equal(conversationBusyProjectionAuxStatusMeta(activeRunDegraded).text, "状态降级");

            const degradedExternal = {
              session_display_state: "external_busy",
              runtime_state: {
                display_state: "external_busy",
                external_busy: true,
                busy_source: "external_cli",
                active_run_projection_reason: "external_busy_no_run",
                degraded: true,
              },
            };
            assert.equal(conversationBusyProjectionAuxStatusMeta(degradedExternal).text, "外部占用");

            const merged = mergeCommunicationStatusSummaryClient(
              { receipt_state: "receipt_pending", projection_summary: { reason: "legacy_missing_refs", source_run_id: "run-a" } },
              { delivery_state: "delivery_unverified" }
            );
            assert.equal(merged.projection_summary.reason, "legacy_missing_refs");
            assert.equal(hasCommunicationStatusSummaryClientData({ projection_summary: { reason: "missing_projection" } }), true);

            const source = fs.readFileSync(path.join(repoRoot, "web/task_parts/60-conversation.js"), "utf8");
            assert.equal(source.includes("conversationProjectionExplanationMeta(currentSession, currentRuntimeState, runs"), true);
            assert.equal(source.includes("agentIdentityExplanationMeta(currentSession)"), true);
            assert.equal(source.includes("active_run_projection_reason"), true);
            """
        )
        proc = subprocess.run(
            ["node", "-e", script, str(REPO_ROOT)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            self.fail(proc.stderr or proc.stdout or "node agent busy projection regression script failed")


if __name__ == "__main__":
    unittest.main()
