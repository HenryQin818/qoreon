import shutil
import subprocess
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class FileViewerSequenceDiagramCssTests(unittest.TestCase):
    def test_sequence_diagram_layers_do_not_stack_under_parent_grid(self) -> None:
        css = (REPO_ROOT / "web" / "task_parts" / "69-diagram-preview.css").read_text(encoding="utf-8")

        self.assertIn(".seq-diagram-stage", css)
        self.assertIn("display: block;", css)
        self.assertIn(".seq-diagram-lane", css)
        self.assertIn("grid-row: 1;", css)
        self.assertIn(".seq-diagram-message", css)
        self.assertIn("z-index: 4;", css)
        self.assertIn(".seq-diagram-participants", css)
        self.assertIn("z-index: 8;", css)

    def test_message_object_viewer_uses_wider_responsive_dialog(self) -> None:
        css = (REPO_ROOT / "web" / "task.css").read_text(encoding="utf-8")

        self.assertIn(".msgobj-viewer-dialog", css)
        self.assertIn("width: min(1440px, calc(100vw - 40px));", css)
        self.assertNotIn("width: min(980px, 94vw);", css)

    def test_flowchart_architecture_diagram_styles_are_available(self) -> None:
        css = (REPO_ROOT / "web" / "task_parts" / "69-diagram-preview.css").read_text(encoding="utf-8")

        self.assertIn(".flow-diagram-card", css)
        self.assertIn(".flow-diagram-svg", css)
        self.assertIn(".flow-diagram-group-box", css)
        self.assertIn(".flow-diagram-node-box", css)
        self.assertIn(".flow-diagram-edge", css)


@unittest.skipUnless(shutil.which("node"), "node is required for UI logic regression checks")
class FileViewerSequenceDiagramUiLogicTests(unittest.TestCase):
    def _run_node(self, script: str) -> None:
        proc = subprocess.run(
            ["node", "-e", script, str(REPO_ROOT)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            self.fail(proc.stderr or proc.stdout or "node sequence diagram ui logic script failed")

    def test_fenced_mermaid_sequence_diagram_is_detected(self) -> None:
        script = textwrap.dedent(
            r"""
            const assert = require("node:assert/strict");
            const fs = require("node:fs");
            const path = require("node:path");

            const repoRoot = process.argv[1];
            const source = fs.readFileSync(path.join(repoRoot, "web/task_parts/69-diagram-preview.js"), "utf8");
            eval(source);

            const markdown = [
              "# 正常链路时序图",
              "",
              "```mermaid",
              "sequenceDiagram",
              "  autonumber",
              "  participant Sender as 用户或Agent",
              "  participant API as POST /api/codex/announce",
              "  Sender->>API: 发送 message",
              "  API-->>Sender: 返回 announce_run_id",
              "```",
            ].join("\n");

            const detected = globalThis.detectSequenceDiagramSource(markdown, { sourceKind: "markdown_fenced" });
            assert.equal(detected.sourceKind, "markdown_fenced");
            assert.match(detected.source, /^sequenceDiagram/);

            const parsed = globalThis.parseSequenceDiagramSource(detected.source);
            assert.equal(parsed.ok, true);
            assert.equal(parsed.autonumber, true);
            assert.equal(parsed.participants.length, 2);
            assert.equal(parsed.items.length, 2);
            """
        )
        self._run_node(script)

    def test_plain_sequence_diagram_is_detected_and_rendered_without_inner_html(self) -> None:
        script = textwrap.dedent(
            r"""
            const assert = require("node:assert/strict");
            const fs = require("node:fs");
            const path = require("node:path");

            const repoRoot = process.argv[1];

            class FakeElement {
              constructor(tag) {
                this.tagName = String(tag || "").toUpperCase();
                this.children = [];
                this.attributes = {};
                this.className = "";
                this.textContent = "";
                this.hidden = false;
                this.style = {
                  values: {},
                  setProperty: (key, value) => { this.style.values[key] = String(value); },
                };
                this.classList = {
                  add: (...names) => {
                    const set = new Set(String(this.className || "").split(/\s+/).filter(Boolean));
                    names.forEach((name) => set.add(name));
                    this.className = Array.from(set).join(" ");
                  },
                  toggle: (name, force) => {
                    const set = new Set(String(this.className || "").split(/\s+/).filter(Boolean));
                    const shouldAdd = force === undefined ? !set.has(name) : !!force;
                    if (shouldAdd) set.add(name);
                    else set.delete(name);
                    this.className = Array.from(set).join(" ");
                    return shouldAdd;
                  },
                };
              }
              set innerHTML(value) {
                FakeElement.innerHtmlWrites += 1;
                throw new Error("sequence diagram renderer must not use innerHTML");
              }
              appendChild(child) {
                this.children.push(child);
                child.parentElement = this;
                return child;
              }
              setAttribute(key, value) {
                this.attributes[key] = String(value);
              }
              addEventListener() {}
              querySelector(selector) {
                if (selector === "code") return this.children.find((child) => child.tagName === "CODE") || null;
                return null;
              }
              replaceWith(node) {
                this.replacedWith = node;
              }
            }
            FakeElement.innerHtmlWrites = 0;

            global.document = {
              createElement: (tag) => new FakeElement(tag),
            };

            const source = fs.readFileSync(path.join(repoRoot, "web/task_parts/69-diagram-preview.js"), "utf8");
            eval(source);

            const diagram = [
              "sequenceDiagram",
              "participant A as <script>用户</script>",
              "participant B as API",
              "A->>B: <script>alert(1)</script>",
              "Note over A,B: <img src=x onerror=alert(1)>",
            ].join("\n");

            const detected = globalThis.detectSequenceDiagramSource(diagram, { sourceKind: "plain_text" });
            assert.equal(detected.sourceKind, "plain_text");

            const node = globalThis.buildSequenceDiagramViewer(diagram, { sourceKind: "plain_text" });
            assert.ok(node);
            assert.equal(node.className.includes("seq-diagram-card"), true);
            assert.equal(FakeElement.innerHtmlWrites, 0);

            function collectText(el) {
              if (!el) return "";
              return String(el.textContent || "") + (el.children || []).map(collectText).join("");
            }

            const text = collectText(node);
            assert.match(text, /<script>alert\(1\)<\/script>/);
            assert.match(text, /<img src=x onerror=alert\(1\)>/);
            """
        )
        self._run_node(script)

    def test_unknown_mermaid_and_over_limit_inputs_fall_back(self) -> None:
        script = textwrap.dedent(
            r"""
            const assert = require("node:assert/strict");
            const fs = require("node:fs");
            const path = require("node:path");

            const repoRoot = process.argv[1];
            const source = fs.readFileSync(path.join(repoRoot, "web/task_parts/69-diagram-preview.js"), "utf8");
            eval(source);

            const flowchart = [
              "```mermaid",
              "flowchart TD",
              "  A --> B",
              "```",
            ].join("\n");
            assert.equal(globalThis.detectSequenceDiagramSource(flowchart, { sourceKind: "markdown_fenced" }), null);

            const unsupported = "sequenceDiagram\nA->B: unsupported arrow";
            const parsed = globalThis.parseSequenceDiagramSource(unsupported);
            assert.equal(parsed.ok, false);
            assert.equal(globalThis.buildSequenceDiagramViewer(unsupported, { sourceKind: "plain_text" }), null);

            const valid = "sequenceDiagram\nA->>B: ok";
            assert.equal(globalThis.buildSequenceDiagramViewer(valid, {
              sourceKind: "plain_text",
              limits: { maxSourceChars: 8 },
            }), null);
            """
        )
        self._run_node(script)

    def test_fenced_mermaid_flowchart_is_detected_and_rendered_without_inner_html(self) -> None:
        script = textwrap.dedent(
            r"""
            const assert = require("node:assert/strict");
            const fs = require("node:fs");
            const path = require("node:path");

            const repoRoot = process.argv[1];

            class FakeElement {
              constructor(tag) {
                this.tagName = String(tag || "").toUpperCase();
                this.children = [];
                this.attributes = {};
                this.className = "";
                this.textContent = "";
                this.hidden = false;
                this.style = {
                  minWidth: "",
                  values: {},
                  setProperty: (key, value) => { this.style.values[key] = String(value); },
                };
                this.classList = {
                  add: (...names) => {
                    const set = new Set(String(this.className || "").split(/\s+/).filter(Boolean));
                    names.forEach((name) => set.add(name));
                    this.className = Array.from(set).join(" ");
                  },
                  toggle: (name, force) => {
                    const set = new Set(String(this.className || "").split(/\s+/).filter(Boolean));
                    const shouldAdd = force === undefined ? !set.has(name) : !!force;
                    if (shouldAdd) set.add(name);
                    else set.delete(name);
                    this.className = Array.from(set).join(" ");
                    return shouldAdd;
                  },
                };
              }
              set innerHTML(value) {
                FakeElement.innerHtmlWrites += 1;
                throw new Error("flowchart renderer must not use innerHTML");
              }
              appendChild(child) {
                this.children.push(child);
                child.parentElement = this;
                return child;
              }
              setAttribute(key, value) {
                this.attributes[key] = String(value);
              }
              addEventListener() {}
              querySelector(selector) {
                if (selector === "code") return this.children.find((child) => child.tagName === "CODE") || null;
                return null;
              }
              replaceWith(node) {
                this.replacedWith = node;
              }
            }
            FakeElement.innerHtmlWrites = 0;

            global.document = {
              createElement: (tag) => new FakeElement(tag),
              createElementNS: (_ns, tag) => new FakeElement(tag),
            };

            const source = fs.readFileSync(path.join(repoRoot, "web/task_parts/69-diagram-preview.js"), "utf8");
            eval(source);

            const markdown = [
              "# 业务架构图",
              "",
              "```mermaid",
              "flowchart LR",
              "  subgraph A[\"数据来源\"]",
              "    A1[\"舆情系统文字稿<br/>Excel / CSV 导出\"]",
              "    A2[\"<script>alert(1)</script>\"]",
              "  end",
              "  subgraph B[\"数据标准化\"]",
              "    B1[\"数据批次\"]",
              "    B2[\"事件范围\"]",
              "  end",
              "  A1 --> B1",
              "  A2 -.产品化阶段.-> B1",
              "  B1 -->|升级| B2",
              "```",
            ].join("\n");

            const detected = globalThis.detectFlowchartDiagramSource(markdown, { sourceKind: "markdown_fenced" });
            assert.equal(detected.sourceKind, "markdown_fenced");
            assert.match(detected.source, /^flowchart LR/);

            const parsed = globalThis.parseFlowchartDiagramSource(detected.source);
            assert.equal(parsed.ok, true);
            assert.equal(parsed.direction, "LR");
            assert.equal(parsed.groups.length, 2);
            assert.equal(parsed.nodes.length, 4);
            assert.equal(parsed.edges.length, 3);

            const node = globalThis.buildFlowchartDiagramViewer(markdown, { sourceKind: "markdown_fenced" });
            assert.ok(node);
            assert.equal(node.className.includes("flow-diagram-card"), true);
            assert.equal(FakeElement.innerHtmlWrites, 0);

            const plainNode = globalThis.buildSequenceDiagramViewer(detected.source, { sourceKind: "plain_text" });
            assert.ok(plainNode);
            assert.equal(plainNode.className.includes("flow-diagram-card"), true);

            function collectText(el) {
              if (!el) return "";
              return String(el.textContent || "") + (el.children || []).map(collectText).join("");
            }
            const text = collectText(node);
            assert.match(text, /架构图预览/);
            assert.match(text, /数据来源/);
            assert.match(text, /舆情系统文字稿/);
            assert.match(text, /<script>alert\(1\)<\/script>/);
          """
        )
        self._run_node(script)

    def test_markdown_mermaid_code_block_can_be_replaced_in_viewer_scope(self) -> None:
        script = textwrap.dedent(
            r"""
            const assert = require("node:assert/strict");
            const fs = require("node:fs");
            const path = require("node:path");

            const repoRoot = process.argv[1];

            class FakeElement {
              constructor(tag) {
                this.tagName = String(tag || "").toUpperCase();
                this.children = [];
                this.attributes = {};
                this.className = "";
                this.textContent = "";
                this.hidden = false;
                this.style = {
                  values: {},
                  setProperty: (key, value) => { this.style.values[key] = String(value); },
                };
                this.classList = {
                  add: (...names) => {
                    const set = new Set(String(this.className || "").split(/\s+/).filter(Boolean));
                    names.forEach((name) => set.add(name));
                    this.className = Array.from(set).join(" ");
                  },
                  toggle: (name, force) => {
                    const set = new Set(String(this.className || "").split(/\s+/).filter(Boolean));
                    const shouldAdd = force === undefined ? !set.has(name) : !!force;
                    if (shouldAdd) set.add(name);
                    else set.delete(name);
                    this.className = Array.from(set).join(" ");
                    return shouldAdd;
                  },
                };
              }
              appendChild(child) {
                this.children.push(child);
                child.parentElement = this;
                return child;
              }
              setAttribute(key, value) {
                this.attributes[key] = String(value);
              }
              addEventListener() {}
              querySelector(selector) {
                if (selector === "code") return this.children.find((child) => child.tagName === "CODE") || null;
                return null;
              }
              replaceWith(node) {
                this.replacedWith = node;
              }
            }

            global.document = {
              createElement: (tag) => new FakeElement(tag),
            };

            const source = fs.readFileSync(path.join(repoRoot, "web/task_parts/69-diagram-preview.js"), "utf8");
            eval(source);

            const code = new FakeElement("code");
            code.textContent = "sequenceDiagram\nA->>B: ping\nB-->>A: pong";
            const pre = new FakeElement("pre");
            pre.className = "md-code";
            pre.attributes["data-lang"] = "mermaid";
            pre.appendChild(code);
            const root = {
              querySelectorAll(selector) {
                return selector === "pre.md-code[data-lang=\"mermaid\"]" ? [pre] : [];
              },
            };

            globalThis.enhanceDiagramTypedBlocks(root, { scope: "message_object_viewer" });
            assert.ok(pre.replacedWith);
            assert.equal(pre.replacedWith.className.includes("seq-diagram-card"), true);
            """
        )
        self._run_node(script)

    def test_markdown_mermaid_flowchart_block_can_be_replaced_in_viewer_scope(self) -> None:
        script = textwrap.dedent(
            r"""
            const assert = require("node:assert/strict");
            const fs = require("node:fs");
            const path = require("node:path");

            const repoRoot = process.argv[1];

            class FakeElement {
              constructor(tag) {
                this.tagName = String(tag || "").toUpperCase();
                this.children = [];
                this.attributes = {};
                this.className = "";
                this.textContent = "";
                this.hidden = false;
                this.style = {
                  minWidth: "",
                  values: {},
                  setProperty: (key, value) => { this.style.values[key] = String(value); },
                };
                this.classList = {
                  add: (...names) => {
                    const set = new Set(String(this.className || "").split(/\s+/).filter(Boolean));
                    names.forEach((name) => set.add(name));
                    this.className = Array.from(set).join(" ");
                  },
                  toggle: (name, force) => {
                    const set = new Set(String(this.className || "").split(/\s+/).filter(Boolean));
                    const shouldAdd = force === undefined ? !set.has(name) : !!force;
                    if (shouldAdd) set.add(name);
                    else set.delete(name);
                    this.className = Array.from(set).join(" ");
                    return shouldAdd;
                  },
                };
              }
              appendChild(child) {
                this.children.push(child);
                child.parentElement = this;
                return child;
              }
              setAttribute(key, value) {
                this.attributes[key] = String(value);
              }
              addEventListener() {}
              querySelector(selector) {
                if (selector === "code") return this.children.find((child) => child.tagName === "CODE") || null;
                return null;
              }
              replaceWith(node) {
                this.replacedWith = node;
              }
            }

            global.document = {
              createElement: (tag) => new FakeElement(tag),
              createElementNS: (_ns, tag) => new FakeElement(tag),
            };

            const source = fs.readFileSync(path.join(repoRoot, "web/task_parts/69-diagram-preview.js"), "utf8");
            eval(source);

            const code = new FakeElement("code");
            code.textContent = "flowchart LR\nA[\"数据来源\"] --> B[\"标准化\"]";
            const pre = new FakeElement("pre");
            pre.className = "md-code";
            pre.attributes["data-lang"] = "mermaid";
            pre.appendChild(code);
            const root = {
              querySelectorAll(selector) {
                return selector === "pre.md-code[data-lang=\"mermaid\"]" ? [pre] : [];
              },
            };

            globalThis.enhanceDiagramTypedBlocks(root, { scope: "message_object_viewer" });
            assert.ok(pre.replacedWith);
            assert.equal(pre.replacedWith.className.includes("flow-diagram-card"), true);
            """
        )
        self._run_node(script)


if __name__ == "__main__":
    unittest.main()
