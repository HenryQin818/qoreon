import unittest
from pathlib import Path

from task_dashboard.runtime_identity import (
    build_health_runtime_identity,
    compare_runtime_identity,
)

LOCAL_ORIGIN = "http://127.0.0.1:" + "18765"


class RuntimeIdentityTests(unittest.TestCase):
    def test_build_health_runtime_identity_includes_bind_local_and_public_origin(self) -> None:
        payload = build_health_runtime_identity(
            project_id="task_dashboard",
            runtime_role="prod",
            environment="stable",
            port=18765,
            bind_host="0.0.0.0",
            local_origin=LOCAL_ORIGIN,
            public_origin="http://192.168.0.102:18765",
            runs_dir=Path("/tmp/runs"),
            sessions_file=Path("/tmp/sessions.json"),
            static_root=Path("/tmp/static"),
            worktree_root=Path("/tmp/worktree"),
            config_path=Path("/tmp/config.toml"),
        )
        self.assertEqual(payload["bind"], "0.0.0.0")
        self.assertEqual(payload["localOrigin"], LOCAL_ORIGIN)
        self.assertEqual(payload["publicOrigin"], "http://192.168.0.102:18765")
        self.assertEqual(payload["port"], 18765)

    def test_compare_runtime_identity_detects_bind_local_and_public_origin_mismatch(self) -> None:
        expected = build_health_runtime_identity(
            project_id="task_dashboard",
            runtime_role="prod",
            environment="stable",
            port=18765,
            bind_host="0.0.0.0",
            local_origin=LOCAL_ORIGIN,
            public_origin="http://192.168.0.102:18765",
            runs_dir=Path("/tmp/runs"),
            sessions_file=Path("/tmp/sessions.json"),
            static_root=Path("/tmp/static"),
            worktree_root=Path("/tmp/worktree"),
            config_path=Path("/tmp/config.toml"),
        )
        actual = dict(expected)
        actual["bind"] = "127.0.0.1"
        actual["localOrigin"] = ""
        actual["publicOrigin"] = ""

        mismatches = compare_runtime_identity(expected, actual)

        self.assertTrue(any(item.startswith("bind:") for item in mismatches))
        self.assertTrue(any(item.startswith("localOrigin:") for item in mismatches))
        self.assertTrue(any(item.startswith("publicOrigin:") for item in mismatches))


if __name__ == "__main__":
    unittest.main()
