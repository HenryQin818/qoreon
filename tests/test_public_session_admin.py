import tempfile
import unittest
from pathlib import Path

from task_dashboard.runtime.session_admin import create_session_response


class _FakeSessionStore:
    def __init__(self) -> None:
        self.created_payload = {}

    def list_sessions(self, project_id: str, channel_name: str, include_deleted: bool = True):
        return []

    def create_session(self, **kwargs):
        self.created_payload = dict(kwargs)
        return {
            "id": kwargs["session_id"],
            "project_id": kwargs["project_id"],
            "channel_name": kwargs["channel_name"],
            "cli_type": kwargs["cli_type"],
            "workdir": kwargs["workdir"],
        }


class PublicSessionAdminTests(unittest.TestCase):
    def test_timeout_with_detected_session_id_is_accepted(self) -> None:
        store = _FakeSessionStore()
        with tempfile.TemporaryDirectory() as td:
            workdir = Path(td)

            response = create_session_response(
                payload={
                    "project_id": "standard_project",
                    "channel_name": "主体-总控",
                    "cli_type": "codex",
                    "create_timeout_s": 240,
                },
                session_store=store,
                environment_name="stable",
                worktree_root=str(workdir),
                create_cli_session=lambda **kwargs: {
                    "ok": False,
                    "error": "timeout",
                    "sessionId": "019d1083-83bc-7631-8de2-34f5ca97edd5",
                    "sessionPath": str(workdir / "session.json"),
                    "workdir": str(workdir),
                },
                resolve_project_workdir=lambda project_id: workdir,
                detect_git_branch=lambda root: "main",
                build_session_seed_prompt=lambda **kwargs: "seed",
                decorate_session_display_fields=lambda row: row,
                apply_session_work_context=lambda row, **kwargs: row,
                load_project_execution_context=lambda **kwargs: {},
                project_exists=lambda project_id: True,
                channel_exists=lambda project_id, channel_name: True,
            )

        self.assertTrue(response["created"])
        self.assertTrue(response["timeoutRecovered"])
        self.assertEqual(response["session"]["id"], "019d1083-83bc-7631-8de2-34f5ca97edd5")
        self.assertEqual(
            store.created_payload.get("created_via"),
            "api.create_session_v2.timeout_recovered",
        )


if __name__ == "__main__":
    unittest.main()
