import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from task_dashboard.runtime import avatar_assignments


class AvatarAssignmentsCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        avatar_assignments.invalidate_avatar_assignments_cache()

    def test_load_avatar_assignments_reuses_short_memory_cache(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            registry = root / "registry"
            registry.mkdir(parents=True, exist_ok=True)
            path = registry / avatar_assignments.AVATAR_ASSIGNMENTS_FILENAME
            path.write_text(
                json.dumps(
                    {
                        "version": 2,
                        "updated_at": "2026-04-11T18:00:00+0800",
                        "bySessionId": {"sid-a": "runtime"},
                        "clearedSessionIds": {},
                    }
                ),
                encoding="utf-8",
            )

            with mock.patch.object(
                avatar_assignments.time,
                "monotonic",
                side_effect=[100.0, 101.0],
            ):
                first = avatar_assignments.load_avatar_assignments(
                    project_id="task_dashboard",
                    project_cfg={"project_root_rel": str(root)},
                    repo_root=root,
                )
                second = avatar_assignments.load_avatar_assignments(
                    project_id="task_dashboard",
                    project_cfg={"project_root_rel": str(root)},
                    repo_root=root,
                )

        self.assertEqual((first.get("avatar_assignments_runtime") or {}).get("delivery_mode"), "fresh_disk")
        self.assertEqual((second.get("avatar_assignments_runtime") or {}).get("delivery_mode"), "memory_cache")
        self.assertEqual((second.get("bySessionId") or {}).get("sid-a"), "runtime")


if __name__ == "__main__":
    unittest.main()
