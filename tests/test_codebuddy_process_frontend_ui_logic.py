import shutil
import subprocess
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("node"), "node is required for UI logic regression checks")
class CodeBuddyProcessFrontendUiLogicTests(unittest.TestCase):
    def test_process_events_are_safe_fallback_for_codebuddy_and_claude(self) -> None:
        script = textwrap.dedent(
            r"""
            const assert = require("node:assert/strict");
            const fs = require("node:fs");
            const path = require("node:path");

            const repoRoot = process.argv[1];
            const source = fs.readFileSync(path.join(repoRoot, "web/task_parts/76-runs-and-drawer.js"), "utf8");

            function extractFunction(name) {
              const signature = new RegExp(`function ${name}\\(`);
              const match = signature.exec(source);
              if (!match) throw new Error(`missing function ${name}`);
              const start = match.index;
              const braceStart = source.indexOf("{", start);
              let depth = 0;
              let inSingle = false;
              let inDouble = false;
              let inTemplate = false;
              let inLineComment = false;
              let inBlockComment = false;
              let escape = false;
              for (let i = braceStart; i < source.length; i += 1) {
                const ch = source[i];
                const next = source[i + 1];
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

            eval(extractFunction("isTerminalTextCli"));
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
            eval(extractFunction("normalizeRunProcessEventRow"));
            eval(extractFunction("extractDetailProcessMessages"));
            eval(extractFunction("processListCount"));
            eval(extractFunction("reportedProcessCountFromRunAndDetail"));

            const detail = {
              processEvents: [
                {
                  text: "调用工具: Agent Explore project structure",
                  event_type: "tool_call",
                  item_type: "tool_call",
                  rawContent: [{ text: "hidden reasoning" }],
                },
                {
                  text: "工具完成: Agent 项目结构摘要",
                  event_type: "tool_result",
                  item_type: "tool_call_result",
                },
              ],
            };
            const parsed = extractDetailProcessMessages(detail, "codebuddy");
            assert.equal(parsed.exact, true);
            assert.deepEqual(parsed.items, [
              "调用工具: Agent Explore project structure",
              "工具完成: Agent 项目结构摘要",
            ]);
            assert.equal(parsed.rows[0].eventType, "tool_call");
            assert.equal(parsed.rows[1].itemType, "tool_call_result");
            assert.equal(parsed.items.join("\n").includes("hidden reasoning"), false);

            const claudeParsed = extractDetailProcessMessages(detail, "claude");
            assert.deepEqual(claudeParsed.items, [
              "调用工具: Agent Explore project structure",
              "工具完成: Agent 项目结构摘要",
            ]);
            assert.equal(claudeParsed.rows[0].eventType, "tool_call");
            assert.equal(claudeParsed.items.join("\n").includes("hidden reasoning"), false);

            const reasoningOnly = extractDetailProcessMessages({
              processEvents: [
                { type: "reasoning", rawContent: [{ text: "do not expose" }] },
              ],
            }, "claude");
            assert.equal(reasoningOnly.items.length, 0);
            assert.equal(reasoningOnly.exact, false);

            const unsafeRows = extractDetailProcessMessages({
              processRows: [
                { type: "reasoning", rawContent: [{ text: "do not expose from row" }] },
              ],
            }, "codebuddy");
            assert.equal(unsafeRows.items.length, 0);
            assert.equal(unsafeRows.exact, false);

            const reasoningTextRows = extractDetailProcessMessages({
              processRows: [
                { type: "reasoning", text: "do not expose reasoning text" },
              ],
            }, "codebuddy");
            assert.equal(reasoningTextRows.items.length, 0);
            assert.equal(reasoningTextRows.exact, false);

            const fileHistoryRows = extractDetailProcessMessages({
              processEvents: [
                {
                  text: "file-history-snapshot",
                  event_type: "file-history-snapshot",
                  item_type: "file-history-snapshot",
                },
                {
                  text: "调用工具: Read server.py",
                  event_type: "tool_started",
                  item_type: "function_call",
                },
              ],
            }, "codebuddy");
            assert.equal(fileHistoryRows.items.join("\n").includes("file-history-snapshot"), false);
            assert.deepEqual(fileHistoryRows.items, ["调用工具: Read server.py"]);

            const nestedRunRows = extractDetailProcessMessages({
              run: {
                processRows: [
                  {
                    text: "调用工具: Read server.py",
                    event_type: "tool_started",
                    item_type: "function_call",
                  },
                ],
              },
            }, "codebuddy");
            assert.equal(nestedRunRows.exact, true);
            assert.deepEqual(nestedRunRows.items, ["调用工具: Read server.py"]);
            assert.equal(nestedRunRows.rows[0].eventType, "tool_started");

            const nestedRunEvents = extractDetailProcessMessages({
              run: {
                processEvents: [
                  {
                    text: "工具完成: Read server.py",
                    event_type: "tool_completed",
                    item_type: "function_call_result",
                  },
                ],
              },
            }, "codebuddy");
            assert.equal(nestedRunEvents.exact, true);
            assert.deepEqual(nestedRunEvents.items, ["工具完成: Read server.py"]);
            assert.equal(nestedRunEvents.rows[0].itemType, "function_call_result");

            const topLevelWinsWithoutDuplicatingNestedRows = extractDetailProcessMessages({
              processRows: [
                {
                  text: "调用工具: Read server.py",
                  event_type: "tool_started",
                  item_type: "function_call",
                },
              ],
              run: {
                processRows: [
                  {
                    text: "调用工具: Read server.py",
                    event_type: "tool_started",
                    item_type: "function_call",
                  },
                ],
              },
            }, "codebuddy");
            assert.equal(topLevelWinsWithoutDuplicatingNestedRows.exact, true);
            assert.deepEqual(topLevelWinsWithoutDuplicatingNestedRows.items, ["调用工具: Read server.py"]);
            assert.equal(topLevelWinsWithoutDuplicatingNestedRows.rows.length, 1);

            const claudeStandardRows = Array.from({ length: 28 }, (_, idx) => ({
              text: `调用工具: Claude tool ${idx + 1}`,
              event_type: "tool_call",
              item_type: "function_call",
            }));
            const claudeDetailWithEmptySnakeEvents = {
              processRows: claudeStandardRows,
              processEvents: [],
              process_events: [],
              run: {
                processRows: claudeStandardRows,
                processEvents: [],
                process_events: [],
              },
            };
            const claudeRowsParsed = extractDetailProcessMessages(claudeDetailWithEmptySnakeEvents, "claude");
            assert.equal(claudeRowsParsed.exact, true);
            assert.equal(claudeRowsParsed.items.length, 28);
            assert.equal(claudeRowsParsed.items[0], "调用工具: Claude tool 1");
            assert.equal(
              reportedProcessCountFromRunAndDetail(
                { cli_type: "claude", processRows: claudeStandardRows, process_events: [] },
                claudeDetailWithEmptySnakeEvents
              ),
              28
            );
            assert.match(source, /const reportedProcessCount = reportedProcessCountFromRunAndDetail\(run, detailFull\);/);
            assert.match(source, /const reportedCount = Math\.max\(countFromRun, reportedProcessCount\);/);
            assert.match(source, /const count = Math\.max\(items\.length, reportedCount\);/);
            """
        )
        proc = subprocess.run(
            ["node", "-e", script, str(REPO_ROOT)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            self.fail(proc.stderr or proc.stdout or "node codebuddy process frontend regression script failed")

    def test_codebuddy_process_safety_note_is_present(self) -> None:
        timeline_js = (REPO_ROOT / "web" / "task_parts" / "70-conversation-timeline.js").read_text(encoding="utf-8")
        self.assertIn("CodeBuddy 过程仅展示工具调用和可公开步骤，思考内容不展示。", timeline_js)

    def test_codebuddy_empty_process_detail_forces_one_refresh(self) -> None:
        timeline_js = (REPO_ROOT / "web" / "task_parts" / "70-conversation-timeline.js").read_text(encoding="utf-8")
        self.assertIn("codebuddyEmptyProcessRefreshByRun", timeline_js)
        self.assertIn('String(processInfo.cliType || "").trim().toLowerCase() === "codebuddy"', timeline_js)
        self.assertIn("shouldForceCodeBuddyEmptyProcessRefresh", timeline_js)
        self.assertIn("force: true", timeline_js)

    def test_codebuddy_raw_context_final_text_is_hidden(self) -> None:
        script = textwrap.dedent(
            r"""
            const assert = require("node:assert/strict");
            const fs = require("node:fs");
            const path = require("node:path");

            const repoRoot = process.argv[1];
            const source = fs.readFileSync(path.join(repoRoot, "web/task_parts/76-runs-and-drawer.js"), "utf8");

            const guardStart = source.indexOf("const CODEBUDDY_RAW_CONTEXT_HIDDEN_TEXT");
            const guardEnd = source.indexOf("function renderRuns", guardStart);
            if (guardStart < 0 || guardEnd < 0) throw new Error("missing CodeBuddy raw context guard block");
            eval(source.slice(guardStart, guardEnd));

            const leaked = '[{"role":"user","content":[{"type":"input_text","text":"secret user prompt"}]},{"type":"system-reminder","data-role":"memory","text":"private memory"}]';
            const safe = safeCodeBuddyTextForDisplay(leaked, "20260609-raw", { cliType: "codebuddy" });
            assert.match(safe, /CodeBuddy 返回了原始结构化上下文，已隐藏/);
            assert.match(safe, /run_id: 20260609-raw/);
            assert.equal(safe.includes("secret user prompt"), false);
            assert.equal(safe.includes("input_text"), false);
            assert.equal(safeCodeBuddyTextForDisplay(leaked, "codex-run", { cliType: "codex" }), leaked);
            assert.equal(safeCodeBuddyTextForDisplay("普通 CodeBuddy 正文", "run-ok", { cliType: "codebuddy" }), "普通 CodeBuddy 正文");
            assert.equal(isCodeBuddyRawContextLeakText('{"answer":"ok"}'), false);
            assert.equal(isCodeBuddyRawContextLeakText('<system-reminder data-role="memory">hidden</system-reminder>'), true);
            assert.equal(isCodeBuddyRawContextLeakText('{"rawContent":[{"text":"hidden reasoning"}]}'), true);
            assert.equal(isCodeBuddyRunMeta(null, { full: { run: { cli_type: "codebuddy" } } }, {}), true);
            """
        )
        proc = subprocess.run(
            ["node", "-e", script, str(REPO_ROOT)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            self.fail(proc.stderr or proc.stdout or "node codebuddy raw context guard script failed")

    def test_codebuddy_raw_context_guard_is_wired_to_display_entrypoints(self) -> None:
        runs_js = (REPO_ROOT / "web" / "task_parts" / "76-runs-and-drawer.js").read_text(encoding="utf-8")
        timeline_js = (REPO_ROOT / "web" / "task_parts" / "70-conversation-timeline.js").read_text(encoding="utf-8")
        ops_js = (REPO_ROOT / "web" / "task_entry_parts" / "80-project-ops.js").read_text(encoding="utf-8")

        self.assertIn("CODEBUDDY_RAW_CONTEXT_HIDDEN_TEXT", runs_js)
        self.assertIn("safeCodeBuddyTextForDisplay(r.lastPreview", runs_js)
        self.assertIn("safeCodeBuddyTextForDisplay(d.last", runs_js)
        self.assertIn("safeCodeBuddyTextForDisplay(fullLast", runs_js)
        self.assertIn("safeCodeBuddyTextForDisplay(text, previewRunId", ops_js)
        self.assertIn("resolveConversationBubbleCopyText", timeline_js)
        self.assertIn("safeCodeBuddyTextForDisplay(text, runId", timeline_js)
        self.assertIn("safeCodeBuddyTextForDisplay(\n            txt", timeline_js)


if __name__ == "__main__":
    unittest.main()
