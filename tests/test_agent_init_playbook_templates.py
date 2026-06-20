import importlib.util
import sys
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "send_agent_init_playbook.py"
SPEC = importlib.util.spec_from_file_location("send_agent_init_playbook", SCRIPT_PATH)
init_playbook = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = init_playbook
SPEC.loader.exec_module(init_playbook)


class AgentInitPlaybookTemplateTests(unittest.TestCase):
    def _assert_message_cli_guidance(self, text: str) -> None:
        self.assertIn("task_dashboard.message_cli", text)
        self.assertIn("send --to-agent", text)
        self.assertIn("receipt --to-agent", text)
        self.assertIn("--wait-verify", text)
        self.assertIn("announce_run_id + target_session_id一致 + visible_in_channel_chat=true", text)
        self.assertIn("blocking_error.next_action", text)
        self.assertIn("message_cli.py", text)
        self.assertIn("旧 registry", text)
        self.assertIn(".sessions", text)

    def test_fresh_init_message_includes_message_cli_short_path(self) -> None:
        text = init_playbook._build_fresh_message(
            agent_name="产品-通讯能力",
            session_id="019c-fresh",
            channel_name="辅助04",
            channel_folder="任务规划/辅助04",
            role="主负责位",
            current_workstream="通讯能力",
            out_of_scope="不做外部网关",
            first_action="先回初始化",
            skills=[],
            callback_session_id="019c-callback",
        )
        self._assert_message_cli_guidance(text)

    def test_fresh_gemini_init_message_uses_tool_limited_guidance(self) -> None:
        text = init_playbook._build_fresh_message(
            agent_name="Gemini通讯能力",
            session_id="019c-gemini",
            channel_name="辅助04",
            channel_folder="任务规划/辅助04",
            role="执行位",
            current_workstream="Gemini 初始化",
            out_of_scope="不做外部网关",
            first_action="先回初始化",
            skills=[],
            callback_session_id="019c-callback",
            target_cli_type="gemini",
        )
        self.assertIn("cli_type=gemini", text)
        self.assertIn("read_file", text)
        self.assertIn("grep_search", text)
        self.assertIn("cli_help", text)
        self.assertIn("不要调用不存在的 `run_shell_command`", text)
        self.assertIn("不强制发送“通讯录验证消息”", text)
        self.assertIn("唯一阻塞和所需协同", text)
        self.assertIn("announce_run_id + target_session_id一致 + visible_in_channel_chat=true", text)

    def test_rotation_init_message_includes_message_cli_short_path(self) -> None:
        text = init_playbook._build_rotation_message(
            agent_name="产品-通讯能力",
            session_id="019c-new",
            channel_name="辅助04",
            channel_folder="任务规划/辅助04",
            role="主负责位",
            current_workstream="通讯能力",
            out_of_scope="不做外部网关",
            first_action="先继承再初始化",
            skills=[],
            callback_session_id="019c-callback",
            old_session_id="019c-old",
            new_session_id="019c-new",
        )
        self._assert_message_cli_guidance(text)


if __name__ == "__main__":
    unittest.main()
