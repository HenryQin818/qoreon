import shutil
import subprocess
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _node_extract_helper() -> str:
    return r"""
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
    """


@unittest.skipUnless(shutil.which("node"), "node is required for UI logic regression checks")
class ChannelFileViewUiLogicTests(unittest.TestCase):
    def run_node_assert(self, script: str) -> None:
        proc = subprocess.run(
            ["node", "-e", script, str(REPO_ROOT)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            self.fail(proc.stderr or proc.stdout or "node regression script failed")

    def test_scope_items_in_channel_mode_keeps_only_channel_files(self) -> None:
        script = textwrap.dedent(
            rf"""
            const assert = require("node:assert/strict");
            const fs = require("node:fs");
            const path = require("node:path");
            const repoRoot = process.argv[1];
            {_node_extract_helper()}

            global.STATE = {{
              panelMode: "channel",
              project: "task_dashboard",
              channel: "子级04",
              view: "comms",
              q: "文件",
              type: "任务",
              status: "进行中",
            }};
            const rows = [
              {{ path: "任务规划/子级04/任务/任务A.md", channel: "子级04", type: "任务", title: "任务A" }},
              {{ path: "任务规划/子级04/产出物/材料/文件资料A.md", channel: "子级04", type: "文档", title: "文件资料A" }},
              {{ path: "任务规划/子级04/讨论空间/讨论记录.md", channel: "子级04", type: "讨论", title: "文件沟通记录" }},
              {{ path: "任务规划/子级05/产出物/材料/文件资料B.md", channel: "子级05", type: "文档", title: "文件资料B" }},
            ];

            global.itemsForProject = () => rows.slice();
            global.filteredItemsForProject = () => {{
              throw new Error("channel mode should not fallback to filteredItemsForProject");
            }};
            global.matchesQuery = (it) => {{
              const q = String(global.STATE.q || "").trim();
              if (!q) return true;
              return String((it && it.title) || "").includes(q) || String((it && it.path) || "").includes(q);
            }};
            global.isTaskItem = (it) => String((it && it.type) || "") === "任务";
            global.isKnowledgeItem = (it) => !!it && !global.isTaskItem(it);
            global.isDiscussionSpaceItem = (it) => String((it && it.path) || "").includes("/讨论空间/") || String((it && it.type) || "") === "讨论";

            eval(extractFunction("web/task_parts/50-main-list.js", "channelFileItems"));
            eval(extractFunction("web/task_parts/50-main-list.js", "scopeItems"));

            const scoped = scopeItems();
            assert.deepEqual(scoped.map((item) => item.path), [
              "任务规划/子级04/产出物/材料/文件资料A.md",
            ]);
            """
        )
        self.run_node_assert(script)
