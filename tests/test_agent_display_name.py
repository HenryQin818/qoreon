import unittest

from task_dashboard.runtime.agent_display_name import (
    build_agent_display_fields,
    build_agent_identity_audit,
    detect_agent_display_name_issue,
)


class AgentDisplayNameTests(unittest.TestCase):
    def test_resolves_alias_as_agent_display_name(self) -> None:
        fields = build_agent_display_fields(
            {
                "id": "019d75f8-a187-75d2-a118-c1a187ae2a76",
                "alias": "项目运维-异常修复",
                "display_name": "会话 a18775",
                "display_name_source": "legacy",
            }
        )

        self.assertEqual(fields["agent_display_name"], "项目运维-异常修复")
        self.assertEqual(fields["agent_display_name_source"], "alias")
        self.assertEqual(fields["agent_name_state"], "resolved")
        self.assertEqual(fields["agent_display_issue"], "none")

    def test_detects_session_id_and_short_id_pollution(self) -> None:
        sid = "019d75f8-a187-75d2-a118-c1a187ae2a76"

        self.assertEqual(detect_agent_display_name_issue(sid, session_id=sid), "polluted_session_id")
        self.assertEqual(detect_agent_display_name_issue("a18775", session_id=sid), "polluted_short_id")
        self.assertEqual(detect_agent_display_name_issue("会话 a18775", session_id=sid), "polluted_short_id")
        self.assertEqual(detect_agent_display_name_issue("ses_abcd1234", session_id=sid), "polluted_session_id")

    def test_reports_polluted_legacy_display_fallback_without_identity(self) -> None:
        fields = build_agent_display_fields(
            {
                "id": "019d75f8-a187-75d2-a118-c1a187ae2a76",
                "display_name": "会话 a18775",
                "display_name_source": "legacy",
            }
        )

        self.assertEqual(fields["agent_display_name"], "")
        self.assertEqual(fields["agent_display_name_source"], "")
        self.assertEqual(fields["agent_name_state"], "polluted")
        self.assertEqual(fields["agent_display_issue"], "polluted_short_id")

    def test_does_not_use_channel_or_display_name_as_agent_fallback(self) -> None:
        fields = build_agent_display_fields(
            {
                "id": "019d75f8-a187-75d2-a118-c1a187ae2a76",
                "channel_name": "辅助06-项目运维（运行巡检-异常告警-会话修复）",
                "display_name": "辅助06-项目运维 · 主会话",
                "display_name_source": "channel_name",
            }
        )

        self.assertEqual(fields["agent_display_name"], "")
        self.assertEqual(fields["agent_display_name_source"], "")
        self.assertEqual(fields["agent_name_state"], "identity_unresolved")
        self.assertEqual(fields["agent_display_issue"], "missing_identity_source")

    def test_resolves_nested_identity_sources(self) -> None:
        fields = build_agent_display_fields(
            {
                "id": "019d75f8-a187-75d2-a118-c1a187ae2a76",
                "agent_registry": {"agent_name": "服务开发-任务维度"},
                "owner_ref": {"agent_name": "不应覆盖"},
            }
        )

        self.assertEqual(fields["agent_display_name"], "服务开发-任务维度")
        self.assertEqual(fields["agent_display_name_source"], "agent_registry")
        self.assertEqual(fields["agent_name_state"], "resolved")
        self.assertEqual(fields["agent_display_issue"], "none")

    def test_reports_random_or_missing_names_as_polluted(self) -> None:
        fields = build_agent_display_fields(
            {
                "id": "019d75f8-a187-75d2-a118-c1a187ae2a76",
                "alias": "未命名会话",
            }
        )

        self.assertEqual(fields["agent_display_name"], "")
        self.assertEqual(fields["agent_display_name_source"], "")
        self.assertEqual(fields["agent_name_state"], "polluted")
        self.assertEqual(fields["agent_display_issue"], "polluted_random_name")

    def test_resolves_non_codex_agent_name_source(self) -> None:
        fields = build_agent_display_fields(
            {
                "id": "ses_2f5d8b87cffekbHfJtB5IXE0DX",
                "cli_type": "opencode",
                "agent_name": "测试验收-OpenCode",
                "channel_name": "子级08-测试与验收（功能-回归-发布）",
            }
        )

        self.assertEqual(fields["agent_display_name"], "测试验收-OpenCode")
        self.assertEqual(fields["agent_display_name_source"], "agent_name")
        self.assertEqual(fields["agent_name_state"], "resolved")
        self.assertEqual(fields["agent_display_issue"], "none")

    def test_non_codex_missing_identity_enters_manual_backfill_audit(self) -> None:
        row = {
            "project_id": "task_dashboard",
            "id": "ses_2f56e1533ffeoQi7mS0iK1kMkP",
            "cli_type": "opencode",
            "channel_name": "子级08-测试与验收（功能-回归-发布）",
            "display_name": "子级08-测试与验收（功能-回归-发布）",
            "display_name_source": "channel_name",
        }

        fields = build_agent_display_fields(row)
        audit = build_agent_identity_audit([row], project_id="task_dashboard")

        self.assertEqual(fields["agent_display_name"], "")
        self.assertEqual(fields["agent_display_name_source"], "")
        self.assertEqual(fields["agent_name_state"], "identity_unresolved")
        self.assertEqual(fields["agent_display_issue"], "missing_identity_source")
        self.assertEqual(audit["manual_backfill_required_count"], 1)
        self.assertEqual(audit["manual_backfill_required"][0]["session_id"], row["id"])
        self.assertEqual(audit["manual_backfill_required"][0]["action"], "needs_owner_confirmation")


if __name__ == "__main__":
    unittest.main()
