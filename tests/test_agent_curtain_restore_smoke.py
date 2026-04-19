import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class AgentCurtainRestoreSmokeTests(unittest.TestCase):
    def test_overview_keeps_agent_curtain_entry(self) -> None:
        text = (REPO_ROOT / "web" / "overview.html.tpl").read_text(encoding="utf-8")
        self.assertIn('id="agentCurtainBtn"', text)
        self.assertIn(">消息瀑布<", text)

    def test_agent_curtain_template_keeps_restored_controls(self) -> None:
        text = (REPO_ROOT / "web" / "agent_curtain.html.tpl").read_text(encoding="utf-8")
        self.assertIn('data-order="volume"', text)
        self.assertIn('id="timeScaleSlider"', text)
        self.assertIn('id="agentHeadsLayer"', text)
        self.assertIn('data-link-type="dispatch"', text)

    def test_agent_curtain_script_keeps_restored_layout_and_filter_logic(self) -> None:
        text = (REPO_ROOT / "web" / "agent_curtain.js").read_text(encoding="utf-8")
        self.assertIn("const CANVAS_RIGHT_GUTTER =", text)
        self.assertIn("const CANVAS_BOTTOM_GUTTER =", text)
        self.assertIn("function filterRunsByVisibleSessions", text)
        self.assertIn("function scheduleViewportSync", text)
        self.assertIn("agentHeadsLayer", text)
        self.assertIn("timeScaleSlider", text)

    def test_build_chain_keeps_agent_curtain_output(self) -> None:
        entry_text = (REPO_ROOT / "build_project_task_dashboard.py").read_text(encoding="utf-8")
        cli_text = (REPO_ROOT / "task_dashboard" / "cli.py").read_text(encoding="utf-8")
        self.assertIn('default_out_agent_curtain', entry_text)
        self.assertIn('--out-agent-curtain', cli_text)
        self.assertIn('project-agent-curtain.html', cli_text)


if __name__ == "__main__":
    unittest.main()
