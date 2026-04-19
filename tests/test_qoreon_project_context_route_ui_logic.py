import shutil
import subprocess
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("node"), "node is required for UI logic regression checks")
class QoreonProjectContextRouteUiLogicTests(unittest.TestCase):
    def test_explicit_hash_project_survives_health_fallback(self) -> None:
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

            global.DATA = {
              projects: [
                { id: "overview", name: "总览", color: "#999999" },
                { id: "task_dashboard", name: "任务看板", color: "#2f6fed" },
              ],
            };
            global.STATE = {
              project: "",
              channel: "",
              q: "",
              type: "全部",
              status: "待办",
              taskModule: "all",
              taskLane: "全部",
              convListLayout: "session",
              selectedSessionId: "",
              selectedSessionExplicit: false,
              view: "work",
              panelMode: "channel",
            };
            global.HASH_BOOTSTRAP = { projectOnly: false };
            global.location = { hash: "#p=qoreon" };
            global.taskLaneOrderList = () => [];
            global.normalizeTaskModule = (value) => String(value || "").trim() || "all";
            global.normalizeConversationListLayout = (value) => String(value || "").trim() || "session";
            global.ensureChannel = () => {
              STATE.channel = "";
            };
            global.unionChannelNames = () => [];

            eval(extractFunction("web/task.js", "explicitProjectIdFromHash"));
            eval(extractFunction("web/task.js", "resolveImplicitProjectPageId"));
            eval(extractFunction("web/task.js", "buildImplicitProjectPage"));
            eval(extractFunction("web/task.js", "pages"));
            eval(extractFunction("web/task.js", "projectById"));
            eval(extractFunction("web/task_parts/79-panel-wire-upload.js", "parseHash"));

            parseHash({ preferredProjectId: "task_dashboard" });

            assert.equal(STATE.project, "qoreon");
            assert.equal(HASH_BOOTSTRAP.projectOnly, true);
            assert.ok(pages().some((item) => item.id === "qoreon"));
            assert.equal(projectById("qoreon").id, "qoreon");
            assert.equal(projectById("qoreon").name, "qoreon");
            assert.equal(projectById("task_dashboard").name, "任务看板");
            assert.equal(projectById("missing_project"), null);
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

    def test_health_fallback_still_applies_without_explicit_hash_project(self) -> None:
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

            global.DATA = {
              projects: [
                { id: "overview", name: "总览", color: "#999999" },
                { id: "task_dashboard", name: "任务看板", color: "#2f6fed" },
              ],
            };
            global.STATE = {
              project: "",
              channel: "",
              q: "",
              type: "全部",
              status: "待办",
              taskModule: "all",
              taskLane: "全部",
              convListLayout: "session",
              selectedSessionId: "",
              selectedSessionExplicit: false,
              view: "work",
              panelMode: "channel",
            };
            global.HASH_BOOTSTRAP = { projectOnly: false };
            global.location = { hash: "" };
            global.taskLaneOrderList = () => [];
            global.normalizeTaskModule = (value) => String(value || "").trim() || "all";
            global.normalizeConversationListLayout = (value) => String(value || "").trim() || "session";
            global.ensureChannel = () => {
              STATE.channel = "";
            };
            global.unionChannelNames = () => [];

            eval(extractFunction("web/task.js", "explicitProjectIdFromHash"));
            eval(extractFunction("web/task.js", "resolveImplicitProjectPageId"));
            eval(extractFunction("web/task.js", "buildImplicitProjectPage"));
            eval(extractFunction("web/task.js", "pages"));
            eval(extractFunction("web/task.js", "projectById"));
            eval(extractFunction("web/task_parts/79-panel-wire-upload.js", "parseHash"));

            parseHash({ preferredProjectId: "task_dashboard" });

            assert.equal(STATE.project, "task_dashboard");
            assert.equal(HASH_BOOTSTRAP.projectOnly, false);
            assert.equal(projectById("qoreon"), null);
            assert.equal(pages().some((item) => item.id === "qoreon"), false);
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
