#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import unittest

import server


COMMUNICATION_LINE = (
    "【通信规则】正式跨 Agent 消息优先使用 "
    "`python3 -m task_dashboard.message_cli send|receipt --to-agent <目标Agent> --wait-verify --json`；"
    "CLI 只是 `POST /api/codex/announce` 封装。`--wait-verify` 只等送达证据，"
    "不等业务回执；目标阻塞时按 `blocking_error.next_action` 转会话治理，"
    "不要翻源码、旧 registry 或 `.sessions` 旁路发送。"
)


class SessionSeedPromptTests(unittest.TestCase):
    def test_default_seed_with_dynamic_connectivity_suffix_for_sub_dialog(self) -> None:
        seed = server._build_session_seed_prompt(
            project_id="task_dashboard",
            channel_name="可视化看板",
        )
        self.assertEqual(
            seed,
            "[task-dashboard] new session · task_dashboard · 可视化看板\n\n"
            f"{COMMUNICATION_LINE}\n\n"
            "【连通性验收】通道：可视化看板；对话类型：子级对话。请仅回复：OK（可视化看板-子级）",
        )

    def test_custom_first_message_has_priority(self) -> None:
        first = "【小秘书】可视化看板（主会话）\n\n请先确认职责边界。"
        seed = server._build_session_seed_prompt(
            project_id="task_dashboard",
            channel_name="可视化看板",
            note="ignored-note",
            first_message=first,
        )
        self.assertEqual(seed, first)

    def test_note_included_when_using_default_seed(self) -> None:
        seed = server._build_session_seed_prompt(
            project_id="task_dashboard",
            channel_name="可视化看板",
            note="from-api",
        )
        self.assertEqual(
            seed,
            "[task-dashboard] new session · task_dashboard · 可视化看板 · from-api\n\n"
            f"{COMMUNICATION_LINE}\n\n"
            "【连通性验收】通道：可视化看板；对话类型：子级对话。请仅回复：OK（可视化看板-子级）",
        )

    def test_default_seed_marks_master_dialog_when_channel_is_master(self) -> None:
        seed = server._build_session_seed_prompt(
            project_id="task_dashboard",
            channel_name="主体-总控（合并与验收）",
        )
        self.assertEqual(
            seed,
            "[task-dashboard] new session · task_dashboard · 主体-总控（合并与验收）\n\n"
            f"{COMMUNICATION_LINE}\n\n"
            "【连通性验收】通道：主体-总控（合并与验收）；对话类型：主对话。请仅回复：OK（主体-总控（合并与验收）-主）",
        )

    def test_gemini_seed_uses_tool_limited_initialization_structure(self) -> None:
        seed = server._build_session_seed_prompt(
            project_id="task_dashboard",
            channel_name="Gemini专项",
            cli_type="gemini",
        )
        self.assertIn("【Gemini 通信与工具规则】", seed)
        self.assertIn("read_file", seed)
        self.assertIn("grep_search", seed)
        self.assertIn("cli_help", seed)
        self.assertIn("不要调用不存在的 `run_shell_command`", seed)
        self.assertIn("初始化阶段不强制发送通讯录验证消息", seed)
        self.assertIn("唯一阻塞: <无/一句话>", seed)
        self.assertNotIn("请仅回复：OK", seed)


if __name__ == "__main__":
    unittest.main()
