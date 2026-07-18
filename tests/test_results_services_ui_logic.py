import shutil
import subprocess
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("node"), "node is required for UI logic regression checks")
class ResultsServicesUiLogicTests(unittest.TestCase):
    def _run_node(self, script: str) -> None:
        proc = subprocess.run(
            ["node", "-e", script, str(REPO_ROOT)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            self.fail(proc.stderr or proc.stdout or "node results services ui logic script failed")

    def test_type_status_payload_and_api_base(self) -> None:
        script = textwrap.dedent(
            r"""
            const assert = require("node:assert/strict");
            const fs = require("node:fs");
            const path = require("node:path");

            const repoRoot = process.argv[1];
            global.STATE = { project: "task_dashboard" };
            global.DATA = {};
            global.location = { origin: "http://127.0.0.1:18770" };
            global.window = {};
            global.document = {
              readyState: "loading",
              addEventListener() {},
            };

            const source = fs.readFileSync(path.join(repoRoot, "web/task_entry_parts/83-results-services.js"), "utf8");
            eval(source);
            const api = window.__resultsServicesPanelV1__;

            assert.equal(api.apiBase(), "/api/projects/task_dashboard/resources");
            assert.equal(api.defaultType, "service");
            assert.equal(api.state.activeTab, "service");
            assert.deepEqual(Object.keys(api.resourceTypes), ["service", "doc_page"]);
            assert.equal(api.panelType(), "service");
            assert.equal(api.panelType({ type: "doc_page" }), "doc_page");
            assert.equal(api.normalizeType("service"), "service");
            assert.equal(api.normalizeType("doc"), "doc_page");
            assert.deepEqual(api.normalizeStatus("running"), { key: "up", label: "UP" });
            assert.deepEqual(api.normalizeStatus({ key: "up", label: "UP" }), { key: "up", label: "UP" });
            assert.deepEqual(api.normalizeStatus("stopped"), { key: "not_started", label: "未启" });
            assert.deepEqual(api.normalizeStatus("missing"), { key: "unknown", label: "未知" });

            assert.equal(api.inferType("http://127.0.0.1:18770", { serviceStatus: "running" }), "service");
            assert.equal(api.inferType("http://127.0.0.1:18770"), "doc_page");
            assert.equal(api.inferType("docs/spec.md"), "doc_page");
            assert.equal(api.inferType("/tmp/report.html"), "doc_page");

            const rows = api.normalizeListPayload({
              resources: [
                { id: "r1", title: "看板", type: "service", url: "http://127.0.0.1:18770", service_status: "up" },
                { id: "r2", name: "说明", type: "doc", path: "docs/readme.md" },
              ],
            });
            assert.equal(rows.length, 2);
            assert.equal(rows[0].type, "service");
            assert.deepEqual(rows[0].service_status, { key: "up", label: "UP" });
            assert.equal(rows[1].type, "doc_page");
            assert.equal(rows[1].url, "docs/readme.md");
            """
        )
        self._run_node(script)

    def test_quick_add_only_enhances_rendered_message_objects(self) -> None:
        script = textwrap.dedent(
            r"""
            const assert = require("node:assert/strict");
            const fs = require("node:fs");
            const path = require("node:path");

            const repoRoot = process.argv[1];
            global.STATE = { project: "task_dashboard" };
            global.DATA = {};
            global.location = { origin: "http://127.0.0.1:18770" };
            global.window = {};

            function makeElement(tag) {
              return {
                tagName: String(tag || "").toUpperCase(),
                className: "",
                children: [],
                attributes: Object.create(null),
                style: {},
                appendChild(child) {
                  this.children.push(child);
                  child.parentNode = this;
                  return child;
                },
                setAttribute(key, value) {
                  this.attributes[key] = String(value);
                },
                getAttribute(key) {
                  return this.attributes[key] || "";
                },
                addEventListener() {},
              };
            }

            global.document = {
              readyState: "loading",
              addEventListener() {},
              createElement: makeElement,
            };

            const source = fs.readFileSync(path.join(repoRoot, "web/task_entry_parts/83-results-services.js"), "utf8");
            eval(source);
            const api = window.__resultsServicesPanelV1__;

            const inserted = [];
            const renderedLink = {
              __messageObject: { value: "docs/report.md", label: "验收报告" },
              textContent: "验收报告",
              getAttribute() { return ""; },
              closest() { return null; },
              parentNode: {
                insertBefore(node, next) {
                  inserted.push({ node, next });
                },
              },
            };
            const plainTextLikeNode = {
              textContent: "http://127.0.0.1:18770",
              getAttribute() { return ""; },
              closest() { return null; },
              parentNode: {
                insertBefore() {
                  throw new Error("plain text should not be enhanced");
                },
              },
            };
            const root = {
              querySelectorAll(selector) {
                assert.equal(selector, ".msg-object-link, .msg-object-code-target");
                return [renderedLink];
              },
            };

            const seed = api.quickAddTargetFromNode(renderedLink);
            assert.deepEqual(seed, {
              title: "验收报告",
              url: "docs/report.md",
              type: "doc_page",
              source: "message_quick_add",
            });
            assert.equal(api.quickAddTargetFromNode(plainTextLikeNode), null);

            api.enhanceQuickAdd(root);
            assert.equal(inserted.length, 1);
            assert.equal(renderedLink.__resultsServicesQuickAddBound, true);
            assert.equal(inserted[0].node.className, "results-services-quickadd-wrap");

            api.enhanceQuickAdd(root);
            assert.equal(inserted.length, 1);
            """
        )
        self._run_node(script)

    def test_drawer_open_modes_reuse_viewer_for_local_and_new_tab_for_http(self) -> None:
        script = textwrap.dedent(
            r"""
            const assert = require("node:assert/strict");
            const fs = require("node:fs");
            const path = require("node:path");

            const repoRoot = process.argv[1];
            global.STATE = { project: "task_dashboard" };
            global.DATA = {};
            global.location = { origin: "http://127.0.0.1:18770" };
            global.window = {
              __messageObjectViewer__: {
                open() {},
                classify(raw) {
                  if (String(raw || "").startsWith("docs/")) {
                    return { kind: "fs_path", path: raw, value: raw, label: raw, defaultAction: "preview_path" };
                  }
                  return null;
                },
              },
            };
            global.document = {
              readyState: "loading",
              addEventListener() {},
            };

            const source = fs.readFileSync(path.join(repoRoot, "web/task_entry_parts/83-results-services.js"), "utf8");
            eval(source);
            const api = window.__resultsServicesPanelV1__;

            const service = api.openModeForItem({ title: "本机服务", url: "http://127.0.0.1:18770", type: "service" });
            assert.equal(service.mode, "new_tab");
            assert.equal(service.href, "http://127.0.0.1:18770");
            assert.equal(api.shouldShowNewTabButton(service), false);

            const external = api.openModeForItem({ title: "外部网页", url: "https://example.test/page.html", type: "doc_page" });
            assert.equal(external.mode, "new_tab");
            assert.equal(external.href, "https://example.test/page.html");
            assert.equal(api.shouldShowNewTabButton(external), false);

            const markdown = api.openModeForItem({ title: "说明", url: "docs/spec.md", type: "doc_page" });
            assert.equal(markdown.mode, "viewer");
            assert.equal(markdown.target.path, "docs/spec.md");
            assert.equal(api.shouldShowNewTabButton(markdown), true);

            const image = api.openModeForItem({ title: "图片", url: "docs/screenshot.png", type: "doc_page" });
            assert.equal(image.mode, "viewer");
            assert.equal(image.target.path, "docs/screenshot.png");
            assert.equal(api.shouldShowNewTabButton(image), true);

            const distPage = api.openModeForItem({ title: "看板", url: "dist/project-task-dashboard.html", type: "doc_page" });
            assert.equal(distPage.mode, "viewer");
            assert.equal(distPage.target.path, "dist/project-task-dashboard.html");
            assert.equal(api.shouldShowNewTabButton(distPage), true);
            assert.equal(api.newTabHrefForItem({ url: "dist/project-task-dashboard.html" }), "/api/fs/open?path=dist%2Fproject-task-dashboard.html");

            const sharePage = api.openModeForItem({ title: "分享页", url: "/share/demo.html", type: "doc_page" });
            assert.equal(sharePage.mode, "viewer");
            assert.equal(sharePage.target.path, "static_sites/share/demo.html");
            assert.equal(api.shouldShowNewTabButton(sharePage), true);

            const fsApi = api.openModeForItem({ title: "文件", url: "/api/fs/open?path=docs%2Fspec.md", type: "doc_page" });
            assert.equal(fsApi.mode, "viewer");
            assert.equal(fsApi.target.path, "docs/spec.md");
            assert.equal(api.shouldShowNewTabButton(fsApi), true);
            """
        )
        self._run_node(script)

    def test_v11_action_copy_uses_new_window_and_stops_propagation(self) -> None:
        source = (REPO_ROOT / "web/task_entry_parts/83-results-services.js").read_text(encoding="utf-8")

        self.assertIn('text: "新窗口打开"', source)
        self.assertNotIn('text: "打开"', source)
        self.assertIn('if (resultsServicesShouldShowNewTabButton(mode))', source)
        self.assertIn("resultsServicesStopEvent(event);", source)
        self.assertIn('window.open(href, "_blank", "noopener,noreferrer")', source)
