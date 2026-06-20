import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class StaticInstructionFilesUiLogicTests(unittest.TestCase):
    def test_channel_agents_md_modal_explains_source_and_mirrors(self) -> None:
        html = (REPO_ROOT / "web" / "task.html.tpl").read_text(encoding="utf-8")
        manage_js = (REPO_ROOT / "web" / "task_parts" / "52-channel-manage.js").read_text(encoding="utf-8")
        manage_css = (REPO_ROOT / "web" / "task_parts" / "52-channel-manage.css").read_text(encoding="utf-8")

        self.assertIn("channelAgentsMdStaticFiles", html)
        self.assertIn("AGENTS.md 是唯一可编辑真源", html)
        self.assertIn("CLI 镜像文件", html)
        self.assertIn("按 AGENTS.md 修复镜像", html)

        self.assertIn("static_instruction_files", manage_js)
        self.assertIn("staticInstructionFiles", manage_js)
        self.assertIn("CODEBUDDY.md", manage_js)
        self.assertIn("AGENTS.md 已保存；服务端尚未返回 CLI 镜像同步结果，不能判定已同步", manage_js)
        self.assertIn("/api/channels/static-instruction-files/repair", manage_js)
        self.assertNotIn("CODEBUDDY.md 已同步。", manage_js)

        self.assertIn(".channel-static-instruction-section", manage_css)
        self.assertIn(".channel-static-instruction-status.bad", manage_css)

    def test_codebuddy_create_and_session_detail_copy_are_visible(self) -> None:
        html = (REPO_ROOT / "web" / "task.html.tpl").read_text(encoding="utf-8")
        bindings_js = (REPO_ROOT / "web" / "task_entry_parts" / "81-session-info-and-bindings.js").read_text(encoding="utf-8")
        ops_js = (REPO_ROOT / "web" / "task_entry_parts" / "80-project-ops.js").read_text(encoding="utf-8")

        self.assertIn("newConvStaticInstructionHint", html)
        self.assertIn("AGENTS.md 仍是唯一编辑真源", bindings_js)
        self.assertIn("CODEBUDDY.md 受管镜像", bindings_js)
        self.assertIn("静态规则文件（只读）", bindings_js)
        self.assertIn("规则真源", bindings_js)
        self.assertIn("CLI 镜像", bindings_js)
        self.assertIn("同步状态", bindings_js)
        self.assertIn("存在冲突，请回通道配置页使用受控修复入口", bindings_js)

        self.assertIn("normalizeStaticInstructionFilesPayload", ops_js)
        self.assertIn("staticInstructionStatusText", ops_js)
        self.assertIn("staticInstructionDefaultMirrorFileName", ops_js)


if __name__ == "__main__":
    unittest.main()
