import shutil
import subprocess
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("node"), "node is required for UI logic regression checks")
class ChannelManageMenuUiLogicTests(unittest.TestCase):
    def test_toggle_channel_manage_menu_marks_layer_root_open(self) -> None:
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

            class ClassList {
              constructor(init = []) { this.values = new Set(init); }
              add(...items) { items.forEach((item) => this.values.add(item)); }
              remove(...items) { items.forEach((item) => this.values.delete(item)); }
              contains(item) { return this.values.has(item); }
            }

            function createNode(classes = [], root = null) {
              const attrs = Object.create(null);
              return {
                classList: new ClassList(classes),
                closest(selector) {
                  if (selector === ".channel-row, .conv-channel-group") return root;
                  return null;
                },
                setAttribute(name, value) {
                  attrs[name] = String(value);
                },
                getAttribute(name) {
                  return Object.prototype.hasOwnProperty.call(attrs, name) ? attrs[name] : null;
                },
              };
            }

            const menuRoot = createNode(["conv-channel-group"]);
            const menu = createNode(["channel-row-menu"], menuRoot);
            const btn = createNode(["channel-row-menu-trigger"], menuRoot);

            global.CHANNEL_MANAGE_UI = { menuChannelName: "" };
            global.CSS = { escape: (value) => String(value) };
            global.document = {
              querySelectorAll(selector) {
                if (selector === ".channel-row-menu") return [menu];
                if (selector === ".channel-row-menu-trigger") return [btn];
                if (selector === ".channel-row.menu-open, .conv-channel-group.menu-open") {
                  return menuRoot.classList.contains("menu-open") ? [menuRoot] : [];
                }
                return [];
              },
              querySelector(selector) {
                if (selector === '.channel-row-menu[data-channel-name="项目助理"]') return menu;
                if (selector === '.channel-row-menu-trigger[data-channel-name="项目助理"]') return btn;
                return null;
              },
            };

            const file = "web/task_parts/52-channel-manage.js";
            eval(extractFunction(file, "channelManageNormalizeText"));
            eval(extractFunction(file, "channelManageResolveMenuLayerRoot"));
            eval(extractFunction(file, "closeChannelManageMenus"));
            eval(extractFunction(file, "toggleChannelManageMenu"));

            toggleChannelManageMenu("项目助理", true);

            assert.equal(global.CHANNEL_MANAGE_UI.menuChannelName, "项目助理");
            assert.equal(menu.classList.contains("show"), true);
            assert.equal(btn.getAttribute("aria-expanded"), "true");
            assert.equal(menuRoot.classList.contains("menu-open"), true);
          """
        )
        proc = subprocess.run(
            ["node", "-e", script, str(REPO_ROOT)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            self.fail(proc.stderr or proc.stdout or "node channel manage menu open regression script failed")

    def test_close_channel_manage_menus_clears_layer_root_state(self) -> None:
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

            class ClassList {
              constructor(init = []) { this.values = new Set(init); }
              add(...items) { items.forEach((item) => this.values.add(item)); }
              remove(...items) { items.forEach((item) => this.values.delete(item)); }
              contains(item) { return this.values.has(item); }
            }

            function createNode(classes = []) {
              const attrs = Object.create(null);
              return {
                classList: new ClassList(classes),
                setAttribute(name, value) {
                  attrs[name] = String(value);
                },
                getAttribute(name) {
                  return Object.prototype.hasOwnProperty.call(attrs, name) ? attrs[name] : null;
                },
              };
            }

            const menuA = createNode(["channel-row-menu", "show"]);
            const menuB = createNode(["channel-row-menu", "show"]);
            const btnA = createNode(["channel-row-menu-trigger"]);
            const btnB = createNode(["channel-row-menu-trigger"]);
            btnA.setAttribute("aria-expanded", "true");
            btnB.setAttribute("aria-expanded", "true");
            const rootA = createNode(["channel-row", "menu-open"]);
            const rootB = createNode(["conv-channel-group", "menu-open"]);

            global.CHANNEL_MANAGE_UI = { menuChannelName: "任意值" };
            global.document = {
              querySelectorAll(selector) {
                if (selector === ".channel-row-menu") return [menuA, menuB];
                if (selector === ".channel-row-menu-trigger") return [btnA, btnB];
                if (selector === ".channel-row.menu-open, .conv-channel-group.menu-open") return [rootA, rootB];
                return [];
              },
            };

            const file = "web/task_parts/52-channel-manage.js";
            eval(extractFunction(file, "closeChannelManageMenus"));

            closeChannelManageMenus();

            assert.equal(global.CHANNEL_MANAGE_UI.menuChannelName, "");
            assert.equal(menuA.classList.contains("show"), false);
            assert.equal(menuB.classList.contains("show"), false);
            assert.equal(btnA.getAttribute("aria-expanded"), "false");
            assert.equal(btnB.getAttribute("aria-expanded"), "false");
            assert.equal(rootA.classList.contains("menu-open"), false);
            assert.equal(rootB.classList.contains("menu-open"), false);
          """
        )
        proc = subprocess.run(
            ["node", "-e", script, str(REPO_ROOT)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            self.fail(proc.stderr or proc.stdout or "node channel manage menu close regression script failed")
