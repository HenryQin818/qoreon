import unittest

from task_dashboard.runtime.request_parsing import parse_session_create_request


class PublicSessionRequestDefaultsTests(unittest.TestCase):
    def test_session_create_defaults_to_reuse_active(self) -> None:
        payload = parse_session_create_request(
            {
                "project_id": "standard_project",
                "channel_name": "辅助01-结构治理与项目接入",
                "cli_type": "codex",
            }
        )
        self.assertEqual(payload["reuse_strategy"], "reuse_active")

    def test_session_create_accepts_create_timeout(self) -> None:
        payload = parse_session_create_request(
            {
                "project_id": "standard_project",
                "channel_name": "辅助01-结构治理与项目接入",
                "cli_type": "codex",
                "createTimeoutS": 240,
            }
        )
        self.assertEqual(payload["create_timeout_s"], 240)


if __name__ == "__main__":
    unittest.main()
