import shutil
import subprocess
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("node"), "node is required for UI logic regression checks")
class AgentListCommRecoveryBadgesUiLogicTests(unittest.TestCase):
    def test_aux_badges_are_derived_from_loaded_session_summary_only(self) -> None:
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
              const node = {
                tag,
                attrs: { ...attrs },
                children: [],
                className: String(attrs.class || ""),
                textContent: String(attrs.text || ""),
                appendChild(child) {
                  this.children.push(child);
                  return child;
                },
              };
              return node;
            }

            function findAll(node, className, out = []) {
              if (!node) return out;
              if (String(node.className || "").split(/\s+/).includes(className)) out.push(node);
              (node.children || []).forEach((child) => findAll(child, className, out));
              return out;
            }

            global.firstNonEmptyText = (values, fallback = "") => {
              for (const value of values || []) {
                const text = String(value == null ? "" : value).trim();
                if (text) return text;
              }
              return fallback;
            };
            global.normalizeSessionDisplayState = (value, fallback = "idle") => String(value || fallback || "idle");
            global.el = makeNode;

            const displayStateFile = "web/task_parts/55-session-display-state.js";
            eval(extractFunction(displayStateFile, "normalizeRunSummaryBool"));
            eval(extractFunction(displayStateFile, "normalizeRunOutcomeState"));
            eval(extractFunction(displayStateFile, "normalizeLatestRunSummary"));
            eval(extractFunction(displayStateFile, "normalizeLatestEffectiveRunSummary"));
            eval(extractFunction(displayStateFile, "getSessionLatestRunSummary"));
            eval(extractFunction(displayStateFile, "getSessionLatestEffectiveRunSummary"));

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
            eval(extractFunction(helperFile, "conversationRecoveryAuxStatusMeta"));
            eval(extractFunction(helperFile, "conversationCommunicationAuxStatusMeta"));
            eval(extractFunction(helperFile, "conversationAuxStatusMeta"));
            eval(extractFunction(helperFile, "buildConversationAuxStatusBadges"));

            assert.equal(conversationAuxStatusMeta({
              latest_run_summary: { recovery_required: true },
            })[0].text, "需补链");
            assert.equal(conversationAuxStatusMeta({
              latest_run_summary: { retry_exhausted: true, recovery_required: true },
            })[0].text, "重试耗尽");
            assert.equal(conversationAuxStatusMeta({
              latest_run_summary: { retry_exhausted: false, recovery_required: false },
              latest_effective_run_summary: { retry_exhausted: "false", recovery_required: "false" },
            }).length, 0);
            assert.equal(conversationAuxStatusMeta({
              latest_run_summary: { retry_exhausted: "true" },
            })[0].text, "重试耗尽");

            const cases = [
              [{ delivery_state: "delivery_unverified" }, "送达待核验"],
              [{ receipt_state: "receipt_pending" }, "待回执"],
              [{ receipt_state: "receipt_done" }, "已回执"],
              [{ receipt_state: "receipt_timeout" }, "回执超时"],
            ];
            for (const [summary, label] of cases) {
              assert.equal(conversationAuxStatusMeta({
                communication_status_summary: summary,
              })[0].text, label);
            }

            const combined = conversationAuxStatusMeta({
              latest_effective_run_summary: { recovery_mode: "manual_recovery" },
              communication_status_summary: { receipt_state: "receipt_pending" },
            });
            assert.deepEqual(combined.map((item) => item.text), ["需补链", "待回执"]);

            const idleDegraded = conversationAuxStatusMeta({
              session_display_state: "idle",
              runtime_state: { display_state: "idle" },
              communication_status_summary: {
                projection_summary: { reason: "cache_hit_no_runtime", degraded: true },
              },
            });
            assert.deepEqual(idleDegraded.map((item) => item.text), []);

            const idleDegradedBusySource = conversationAuxStatusMeta({
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
            });
            assert.deepEqual(idleDegradedBusySource.map((item) => item.text), []);

            const queuedDegraded = conversationAuxStatusMeta({
              session_display_state: "idle",
              runtime_state: {
                display_state: "idle",
                busy_source: "degraded_unknown",
                queued_run_id: "run-queued",
                active_run_projection_reason: "degraded_runtime_index",
              },
            });
            assert.deepEqual(queuedDegraded.map((item) => item.text), ["状态降级"]);

            const runningDegradedWithReceipt = conversationAuxStatusMeta({
              session_display_state: "running",
              runtime_state: { display_state: "running" },
              communication_status_summary: {
                receipt_state: "receipt_pending",
                projection_summary: { reason: "cache_hit_no_runtime", degraded: true },
              },
            });
            assert.deepEqual(runningDegradedWithReceipt.map((item) => item.text), ["待回执", "状态降级"]);

            const degradedNode = buildConversationAuxStatusBadges({
              session_display_state: "running",
              runtime_state: { display_state: "running" },
              communication_status_summary: {
                projection_summary: { reason: "cache_hit_no_runtime", degraded: true },
              },
            });
            const degradedBadge = findAll(degradedNode, "conv-aux-badge")[0];
            assert.equal(degradedBadge.textContent, "!");
            assert.equal(degradedBadge.attrs["aria-label"], "状态降级");
            assert.equal(degradedBadge.attrs.title.includes("当前状态来自降级数据"), true);
            assert.equal(String(degradedBadge.className).includes("is-icon-only"), true);

            const node = buildConversationAuxStatusBadges({
              communication_status_summary: { receipt_state: "receipt_pending" },
            });
            assert.equal(findAll(node, "conv-aux-badge").length, 1);
            assert.equal(findAll(node, "conv-aux-badge")[0].textContent, "待回执");

            assert.equal(hasCommunicationStatusSummaryClientData({
              receipt_state: "receipt_pending",
            }), true);
            assert.equal(mergeCommunicationStatusSummaryClient(
              { receipt_state: "receipt_pending", source_run_id: "run-a" },
              { delivery_state: "delivery_unverified" }
            ).receipt_state, "receipt_pending");

            const bootstrapSource = fs.readFileSync(path.join(repoRoot, "web/task_parts/74-session-bootstrap-and-sessions.js"), "utf8");
            assert.equal(bootstrapSource.includes("communication_status_summary"), true);
            assert.equal(bootstrapSource.includes("mergeCommunicationStatusSummaryClient"), true);
            """
        )
        proc = subprocess.run(
            ["node", "-e", script, str(REPO_ROOT)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            self.fail(proc.stderr or proc.stdout or "node agent list aux badge regression script failed")


if __name__ == "__main__":
    unittest.main()
