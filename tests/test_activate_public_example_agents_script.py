import io
import runpy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "activate_public_example_agents.py"


class ActivatePublicExampleAgentsScriptTests(unittest.TestCase):
    def test_all_channels_alias_enables_include_optional(self) -> None:
        captured: dict[str, object] = {}

        def fake_activate(repo_root: Path, **kwargs: object) -> dict[str, object]:
            captured["repo_root"] = repo_root
            captured.update(kwargs)
            return {"ok": True, "project_id": kwargs.get("project_id", "standard_project")}

        with patch(
            "task_dashboard.public_agent_activation.activate_public_example_agents",
            side_effect=fake_activate,
        ):
            with patch.object(
                sys,
                "argv",
                [str(SCRIPT_PATH), "--all-channels", "--sessions-only"],
            ):
                with patch("sys.stdout", new=io.StringIO()):
                    with self.assertRaises(SystemExit) as exc:
                        runpy.run_path(str(SCRIPT_PATH), run_name="__main__")

        self.assertEqual(exc.exception.code, 0)
        self.assertEqual(captured["repo_root"], REPO_ROOT)
        self.assertTrue(captured["include_optional"])
        self.assertFalse(captured["run_sample_actions"])
