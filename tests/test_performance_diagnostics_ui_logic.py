import shutil
import subprocess
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("node"), "node is required for UI logic regression checks")
class PerformanceDiagnosticsUiLogicTests(unittest.TestCase):
    def test_snapshot_diagnostics_view_model_maps_fields_and_limits_recent_events(self) -> None:
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

            global.LIVE = { error: "" };

            const file = "web/performance_diagnostics.js";
            eval(extractFunction(file, "text"));
            eval(extractFunction(file, "rows"));
            eval(extractFunction(file, "parseTime"));
            eval(extractFunction(file, "formatZhDateTime"));
            eval(extractFunction(file, "formatDurationMs"));
            eval(extractFunction(file, "snapshotDiagnosticTone"));
            eval(extractFunction(file, "buildSnapshotBackgroundSummaryMeta"));
            eval(extractFunction(file, "describeSnapshotDiagnosticEvent"));
            eval(extractFunction(file, "buildSnapshotDiagnosticsViewModel"));

            const vm = buildSnapshotDiagnosticsViewModel({
              sessions_snapshot_diagnostics: {
                enabled: true,
                default_query_mode: "snapshot_first",
                last_build_source: "stale_snapshot",
                last_hit: false,
                last_age_ms: 1800,
                ttl_ms: 3000,
                stale_ttl_ms: 30000,
                last_build_elapsed_ms: 82,
                refresh_state: "started",
                last_invalidated_at: "2026-04-12T20:00:00+0800",
                last_refresh_started_at: "2026-04-12T20:00:01+0800",
                last_refresh_finished_at: "2026-04-12T20:00:03+0800",
                recent_events: Array.from({ length: 22 }, (_, index) => ({
                  event_type: index === 0 ? "fallback" : "refresh",
                  title: `事件 ${index + 1}`,
                  occurred_at: `2026-04-12T20:${String(index).padStart(2, "0")}:00+0800`,
                  build_source: index === 0 ? "fallback" : "snapshot",
                  query_mode: "snapshot_first",
                  hit: index !== 0,
                  age_ms: 100 + index,
                  build_elapsed_ms: 50 + index,
                  refresh_state: index === 0 ? "started" : "done",
                  fallback_reason: index === 0 ? "build_error" : "",
                })),
              },
            });

            assert.equal(vm.available, true);
            assert.equal(vm.tone, "warn");
            const enabledCard = vm.cards.find((item) => item.label === "Snapshot 开关");
            const sourceCard = vm.cards.find((item) => item.label === "最近构建来源");
            const ageCard = vm.cards.find((item) => item.label === "快照年龄 / TTL");
            const elapsedCard = vm.cards.find((item) => item.label === "最近构建耗时");

            assert.ok(enabledCard);
            assert.equal(enabledCard.value, "已开启");
            assert.ok(sourceCard);
            assert.equal(sourceCard.value, "stale_snapshot");
            assert.ok(ageCard);
            assert.equal(ageCard.value, "1.8 s / 3 s");
            assert.ok(elapsedCard);
            assert.equal(elapsedCard.value, "82 ms");
            assert.equal(vm.timeline[0].value, "04/12 20:00:00");
            assert.equal(vm.events.length, 20);
            assert.equal(vm.events[0].tone, "danger");
            assert.ok(vm.events[0].chips.includes("来源 fallback"));
            assert.ok(vm.events[0].chips.includes("回退 build_error"));
          """
        )
        proc = subprocess.run(
            ["node", "-e", script, str(REPO_ROOT)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            self.fail(proc.stderr or proc.stdout or "node performance diagnostics regression script failed")

    def test_snapshot_diagnostics_view_model_handles_absent_additive_field(self) -> None:
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

            global.LIVE = { error: "" };

            const file = "web/performance_diagnostics.js";
            eval(extractFunction(file, "text"));
            eval(extractFunction(file, "rows"));
            eval(extractFunction(file, "parseTime"));
            eval(extractFunction(file, "formatZhDateTime"));
            eval(extractFunction(file, "formatDurationMs"));
            eval(extractFunction(file, "snapshotDiagnosticTone"));
            eval(extractFunction(file, "buildSnapshotBackgroundSummaryMeta"));
            eval(extractFunction(file, "describeSnapshotDiagnosticEvent"));
            eval(extractFunction(file, "buildSnapshotDiagnosticsViewModel"));

            const vm = buildSnapshotDiagnosticsViewModel({});
            assert.equal(vm.available, false);
            assert.equal(vm.cards.length, 0);
            assert.equal(vm.timeline.length, 0);
            assert.equal(vm.events.length, 0);
          """
        )
        proc = subprocess.run(
            ["node", "-e", script, str(REPO_ROOT)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            self.fail(proc.stderr or proc.stdout or "node performance diagnostics missing-field regression script failed")

    def test_snapshot_diagnostics_view_model_exposes_functional_logging_fields(self) -> None:
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

            global.LIVE = { error: "" };

            const file = "web/performance_diagnostics.js";
            eval(extractFunction(file, "text"));
            eval(extractFunction(file, "rows"));
            eval(extractFunction(file, "parseTime"));
            eval(extractFunction(file, "formatZhDateTime"));
            eval(extractFunction(file, "formatDurationMs"));
            eval(extractFunction(file, "snapshotDiagnosticTone"));
            eval(extractFunction(file, "buildSnapshotBackgroundSummaryMeta"));
            eval(extractFunction(file, "describeSnapshotDiagnosticEvent"));
            eval(extractFunction(file, "buildSnapshotDiagnosticsViewModel"));

            const vm = buildSnapshotDiagnosticsViewModel({
              sessions_snapshot_diagnostics: {
                enabled: true,
                default_query_mode: "plain_project_list_only",
                foreground_interval_ms: 5000,
                background_interval_ms: 10000,
                invalidation_window_ms: 10000,
                last_build_source: "stale_snapshot",
                last_hit: true,
                last_age_ms: 842,
                ttl_ms: 5000,
                stale_ttl_ms: 30000,
                last_build_elapsed_ms: 118,
                last_fallback_reason: "",
                last_delivery_mode: "stale_snapshot",
                last_refresh_trigger: "stale_first",
                refresh_state: "started",
                last_invalidated_at: "2026-04-12T20:05:12+0800",
                last_refresh_started_at: "2026-04-12T20:05:12+0800",
                last_refresh_finished_at: "2026-04-12T20:05:20+0800",
                background_summary: {
                  sessions_count: 68,
                  runtime_state_count: 68,
                  conversation_list_metrics_count: 68,
                  heartbeat_summary_count: 68,
                  generated_at: "2026-04-12T20:05:12+0800",
                },
                functional_log_mode: "structured_registry_only",
                recent_events: [],
              },
            });

            const cadence = vm.cards.find((item) => item.label === "前台 / 后台节奏");
            const delivery = vm.cards.find((item) => item.label === "最终交付模式");
            const background = vm.cards.find((item) => item.label === "后台摘要");
            const mode = vm.cards.find((item) => item.label === "功能日志模式");
            const generated = vm.timeline.find((item) => item.label === "后台摘要生成");

            assert.ok(cadence);
            assert.equal(cadence.value, "5 s / 10 s");
            assert.ok(cadence.note.includes("10 s"));
            assert.ok(delivery);
            assert.equal(delivery.value, "stale_snapshot");
            assert.ok(delivery.note.includes("stale_first"));
            assert.ok(background);
            assert.equal(background.value, "68 会话");
            assert.ok(background.note.includes("heartbeat 68"));
            assert.ok(mode);
            assert.equal(mode.value, "structured_registry_only");
            assert.ok(generated);
            assert.equal(generated.value, "04/12 20:05:12");
          """
        )
        proc = subprocess.run(
            ["node", "-e", script, str(REPO_ROOT)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            self.fail(proc.stderr or proc.stdout or "node performance diagnostics functional field regression failed")

    def test_snapshot_diagnostic_events_show_window_aggregation_and_delivery(self) -> None:
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

            const file = "web/performance_diagnostics.js";
            eval(extractFunction(file, "text"));
            eval(extractFunction(file, "parseTime"));
            eval(extractFunction(file, "formatZhDateTime"));
            eval(extractFunction(file, "formatDurationMs"));
            eval(extractFunction(file, "snapshotDiagnosticTone"));
            eval(extractFunction(file, "describeSnapshotDiagnosticEvent"));

            const event = describeSnapshotDiagnosticEvent({
              at: "2026-04-12T20:05:09+0800",
              kind: "invalidate",
              build_source: "snapshot",
              hit: true,
              age_ms: 221,
              build_elapsed_ms: 118,
              refresh_state: "started",
              count: 4,
              window_ms: 10000,
              first_at: "2026-04-12T20:05:00+0800",
              last_at: "2026-04-12T20:05:09+0800",
              delivery_mode: "stale_snapshot",
              refresh_trigger: "invalidate",
            }, 0);

            assert.ok(event.chips.includes("聚合 4 次"));
            assert.ok(event.chips.includes("窗口 10 s"));
            assert.ok(event.chips.includes("交付 stale_snapshot"));
            assert.ok(event.chips.includes("触发 invalidate"));
            assert.ok(event.note.includes("首条 04/12 20:05:00"));
            assert.ok(event.note.includes("末条 04/12 20:05:09"));
          """
        )
        proc = subprocess.run(
            ["node", "-e", script, str(REPO_ROOT)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            self.fail(proc.stderr or proc.stdout or "node performance diagnostics event aggregation regression failed")
