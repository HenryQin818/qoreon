import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class OverviewLanAccessUiLogicTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = (REPO_ROOT / "web" / "overview.html.tpl").read_text(encoding="utf-8")
        cls.css = (REPO_ROOT / "web" / "overview.css").read_text(encoding="utf-8")
        cls.js = (REPO_ROOT / "web" / "overview_parts" / "10-lan-access.js").read_text(encoding="utf-8")
        cls.render_source = (REPO_ROOT / "task_dashboard" / "render.py").read_text(encoding="utf-8")

    def test_header_exposes_lan_access_entry_in_top_actions(self) -> None:
        head_actions_start = self.html.index('<div class="head-actions">')
        lan_index = self.html.index('id="lanAccessBtn"', head_actions_start)
        config_index = self.html.index('id="configBtn"', head_actions_start)
        self.assertLess(lan_index, config_index)
        self.assertIn("局域网访问", self.html)
        self.assertIn('id="lanAccessBadge"', self.html)
        self.assertIn('id="lanAccessPop"', self.html)
        self.assertIn('id="lanAccessSwitch"', self.html)
        self.assertIn('id="lanAccessCopyBtn"', self.html)
        self.assertIn('id="lanAccessRestart"', self.html)

    def test_lan_access_logic_uses_runtime_contract_only(self) -> None:
        self.assertIn('fetchJson("/api/runtime/lan-access", { cache: "no-store" })', self.js)
        self.assertIn('fetchJson("/api/runtime/lan-access", {', self.js)
        self.assertIn("body: JSON.stringify({ enabled: !!enabled })", self.js)
        self.assertIn("effectiveEnabled", self.js)
        self.assertIn("requiresRestart", self.js)
        self.assertIn("frontEndAction", self.js)
        self.assertIn("重启 task-dashboard 服务后生效", self.js)
        self.assertNotIn("token", self.js.lower())
        self.assertNotIn("rbac", self.js.lower())
        self.assertNotIn("authorized", self.js.lower())

    def test_lan_access_styles_match_header_popover_pattern(self) -> None:
        self.assertIn(".lan-access-wrap", self.css)
        self.assertIn(".lan-access-trigger", self.css)
        self.assertIn(".lan-access-pop", self.css)
        self.assertIn(".lan-access-switch", self.css)
        self.assertIn(".lan-access-restart", self.css)
        self.assertIn("position: absolute;", self.css)
        self.assertIn("width: min(360px, calc(100vw - 32px));", self.css)
        self.assertIn("position: fixed;", self.css)

    def test_overview_parts_are_bundled_after_main_script(self) -> None:
        self.assertIn('_read_optional_bundle(web_dir / "overview_parts", "*.js")', self.render_source)
        self.assertIn("overview_parts_js", self.render_source)


if __name__ == "__main__":
    unittest.main()
