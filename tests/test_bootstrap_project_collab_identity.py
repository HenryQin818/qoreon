import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "bootstrap_project_collab.py"
REPO_ROOT = SCRIPT_PATH.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SPEC = importlib.util.spec_from_file_location("bootstrap_project_collab", SCRIPT_PATH)
bootstrap_project_collab = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = bootstrap_project_collab
SPEC.loader.exec_module(bootstrap_project_collab)

from task_dashboard.runtime.project_admin import build_project_registry_and_verify  # noqa: E402


class _EmptySessionStore:
    def list_sessions(self, *_args: object, **_kwargs: object) -> list[dict[str, object]]:
        return []


class BootstrapProjectCollabIdentityTests(unittest.TestCase):
    def _run_bootstrap(self, sessions: list[dict[str, object]], channels: list[str] | None = None) -> dict[str, object]:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            channel_names = channels or sorted({str(row.get("channel_name") or "") for row in sessions if row.get("channel_name")})
            channel_toml = "\n".join(
                f'[[projects.channels]]\nname = "{name}"\ndesc = "{name}"\n' for name in channel_names
            )
            config_path = root / "config.toml"
            config_path.write_text(
                "\n".join(
                    [
                        "version = 1",
                        "",
                        "[[projects]]",
                        'id = "demo_project"',
                        'name = "演示项目"',
                        'project_root_rel = "projects/demo-project"',
                        'task_root_rel = "projects/demo-project/任务规划"',
                        "",
                        channel_toml,
                    ]
                ),
                encoding="utf-8",
            )
            session_path = root / "sessions.json"
            session_path.write_text(json.dumps({"project_id": "demo_project", "sessions": sessions}, ensure_ascii=False), encoding="utf-8")
            output_path = root / "out" / "collab-registry.v1.json"
            view_path = root / "out" / "collab-registry.view.md"
            dispatch_path = root / "out" / "collab-registry.dispatch.view.md"
            html_path = root / "out" / "agent-directory.html"
            argv = [
                "bootstrap_project_collab.py",
                "--project-id",
                "demo_project",
                "--config",
                str(config_path),
                "--workspace-root",
                str(root),
                "--session-json",
                str(session_path),
                "--output",
                str(output_path),
                "--view-output",
                str(view_path),
                "--dispatch-output",
                str(dispatch_path),
                "--html-output",
                str(html_path),
            ]
            with mock.patch.object(sys, "argv", argv):
                self.assertEqual(bootstrap_project_collab.main(), 0)
            return json.loads(output_path.read_text(encoding="utf-8"))

    def test_session_id_alias_is_replaced_by_readable_fallback_and_blocks_gate(self) -> None:
        sid = "019dc54c-9ebd-7ca2-9694-4e04671b60be"
        payload = self._run_bootstrap(
            [
                {
                    "id": sid,
                    "channel_name": "主体-总控",
                    "alias": sid,
                    "purpose": "主控协作",
                    "is_primary": True,
                }
            ],
            channels=["主体-总控"],
        )

        candidate = payload["channels"][0]["session_candidates"][0]
        self.assertEqual(candidate["display_name"], "未命名Agent·主体-总控")
        self.assertEqual(candidate["agent_name"], "未命名Agent·主体-总控")
        self.assertNotEqual(candidate["display_name"], sid)
        validation = payload["ccr_validation"]
        self.assertTrue(validation["blocking"])
        self.assertIn("session_id_as_identity", {item["code"] for item in validation["issues"]})

    def test_empty_alias_and_purpose_are_reported_for_creation_gate(self) -> None:
        payload = self._run_bootstrap(
            [
                {
                    "id": "019dc54c-9ebd-7ca2-9694-4e04671b60be",
                    "channel_name": "主体-总控",
                    "alias": "",
                    "purpose": "",
                    "is_primary": True,
                }
            ],
            channels=["主体-总控"],
        )

        candidate = payload["channels"][0]["session_candidates"][0]
        self.assertEqual(candidate["display_name"], "未命名Agent·主体-总控")
        validation = payload["ccr_validation"]
        codes = {item["code"] for item in validation["issues"]}
        self.assertIn("missing_readable_identity", codes)
        self.assertIn("missing_session_purpose", codes)
        self.assertEqual(validation["summary"]["identity_issue_count"], 2)

    def test_same_channel_readable_identity_conflict_blocks_gate(self) -> None:
        payload = self._run_bootstrap(
            [
                {
                    "id": "019dc54c-9ebd-7ca2-9694-4e04671b60be",
                    "channel_name": "子级02-运行时",
                    "alias": "后端-通讯能力",
                    "purpose": "主控协作",
                    "is_primary": True,
                },
                {
                    "id": "019dc54d-1111-7ca2-9694-4e04671b60be",
                    "channel_name": "子级02-运行时",
                    "alias": "后端-通讯能力",
                    "purpose": "候选协作",
                    "is_primary": False,
                },
            ],
            channels=["子级02-运行时"],
        )

        validation = payload["ccr_validation"]
        self.assertTrue(validation["blocking"])
        self.assertIn("readable_identity_conflict", {item["code"] for item in validation["issues"]})

    def test_duplicate_session_id_across_channels_blocks_gate(self) -> None:
        sid = "019dc54c-9ebd-7ca2-9694-4e04671b60be"
        payload = self._run_bootstrap(
            [
                {
                    "id": sid,
                    "channel_name": "主体-总控",
                    "alias": "项目总控",
                    "purpose": "主控协作",
                    "is_primary": True,
                },
                {
                    "id": sid,
                    "channel_name": "子级02-运行时",
                    "alias": "后端-通讯能力",
                    "purpose": "运行时协作",
                    "is_primary": True,
                },
            ],
            channels=["主体-总控", "子级02-运行时"],
        )

        validation = payload["ccr_validation"]
        self.assertTrue(validation["blocking"])
        self.assertIn("duplicate_session_id", {item["code"] for item in validation["issues"]})

    def test_project_registry_verify_marks_blocking_ccr_validation_degraded(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            config_path = root / "config.toml"
            config_path.write_text("version = 1\n", encoding="utf-8")
            script_path = root / "scripts" / "bootstrap_project_collab.py"
            script_path.parent.mkdir(parents=True, exist_ok=True)
            script_path.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
            registry_path = root / "project" / "registry" / "collab-registry.v1.json"
            validation = {
                "version": "p0_identity_gate_v1",
                "ok": False,
                "blocking": True,
                "issue_count": 1,
                "blocking_issue_count": 1,
                "missing_items": [{"code": "missing_readable_identity", "field": "alias"}],
                "issues": [{"code": "missing_readable_identity", "blocking": True}],
                "summary": {"identity_issue_count": 1},
            }

            def fake_run(*_args: object, **_kwargs: object) -> mock.Mock:
                registry_path.parent.mkdir(parents=True, exist_ok=True)
                registry_path.write_text(json.dumps({"ccr_validation": validation}, ensure_ascii=False), encoding="utf-8")
                return mock.Mock(returncode=0, stdout="ok", stderr="")

            with mock.patch("task_dashboard.runtime.project_admin.subprocess.run", side_effect=fake_run):
                result = build_project_registry_and_verify(
                    spec={
                        "bootstrap": {"generate_registry": True, "run_dedup": False, "run_visibility_check": False},
                        "project_id": "demo_project",
                        "project_root": str(root / "project"),
                        "registry_paths": [
                            str(registry_path),
                            str(root / "project" / "registry" / "collab-registry.view.md"),
                            str(root / "project" / "artifacts" / "agent-directory.html"),
                        ],
                        "session_store_path": str(root / "sessions.json"),
                        "channels": [],
                    },
                    repo_root=root,
                    config_path=config_path,
                    session_store=_EmptySessionStore(),
                    read_task_dashboard_generated_at=lambda: "",
                    rebuild_dashboard_static=lambda _timeout_s: {"ok": True},
                )

        registry = result["registry"]
        self.assertTrue(registry["degraded"])
        self.assertEqual(registry["state"], "degraded")
        self.assertEqual(registry["degraded_reason"], "ccr_validation_blocking")
        self.assertEqual(registry["ccr_validation"], validation)


if __name__ == "__main__":
    unittest.main()
