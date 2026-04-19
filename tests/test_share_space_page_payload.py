import json
import unittest

from task_dashboard.cli import _build_project_chat_static_page_data


class ShareSpacePagePayloadTests(unittest.TestCase):
    def test_static_payload_does_not_embed_project_control_plane_data(self) -> None:
        payload = _build_project_chat_static_page_data(
            generated_at="2026-04-15T22:28:00+0800",
            primary_project_id="task_dashboard",
            project_chat_page_link="project-task-dashboard.html",
            projects_meta=[
                {
                    "id": "task_dashboard",
                    "name": "Qoreon",
                    "sessions": [{"session_id": "internal"}],
                    "channel_sessions": {"secret": "internal"},
                    "links": [{"label": "runs", "url": "/api/codex/runs"}],
                    "agent_directory_summary": {"secret": True},
                }
            ],
        )

        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertEqual(
            sorted(payload.keys()),
            ["dashboard", "generated_at", "links", "project_chat_page", "project_id", "projects"],
        )
        self.assertEqual(payload["projects"], [{"id": "task_dashboard", "name": "Qoreon"}])
        self.assertEqual(payload["links"], {"project_chat_page": "project-task-dashboard.html"})
        self.assertNotIn("sessions", encoded)
        self.assertNotIn("channel_sessions", encoded)
        self.assertNotIn("/api/codex/runs", encoded)
        self.assertNotIn("agent_directory_summary", encoded)


if __name__ == "__main__":
    unittest.main()
