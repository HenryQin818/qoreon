import unittest

from task_dashboard.runtime.request_parsing import parse_session_create_request


class PublicSessionRequestDefaultsTests(unittest.TestCase):
    def test_session_create_leaves_reuse_strategy_unspecified(self) -> None:
        payload = parse_session_create_request(
            {
                "project_id": "standard_project",
                "channel_name": "辅助01-结构治理与项目接入",
                "cli_type": "codex",
            }
        )
        self.assertEqual(payload["reuse_strategy"], "")

    def test_session_create_does_not_expose_transport_timeout(self) -> None:
        payload = parse_session_create_request(
            {
                "project_id": "standard_project",
                "channel_name": "辅助01-结构治理与项目接入",
                "cli_type": "codex",
                "createTimeoutS": 240,
            }
        )
        self.assertNotIn("create_timeout_s", payload)


if __name__ == "__main__":
    unittest.main()
