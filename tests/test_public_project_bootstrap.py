import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class PublicProjectBootstrapTests(unittest.TestCase):
    def test_public_repo_ships_registry_bootstrap_script(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        script_path = repo_root / "scripts" / "bootstrap_project_collab.py"
        self.assertTrue(script_path.exists(), "公开仓缺少 scripts/bootstrap_project_collab.py")

    def test_registry_bootstrap_script_runs_against_public_config(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        script_path = repo_root / "scripts" / "bootstrap_project_collab.py"
        config_path = repo_root / "config.toml"

        with tempfile.TemporaryDirectory() as td:
            temp_dir = Path(td)
            session_json = temp_dir / "standard_project.json"
            session_json.write_text(
                json.dumps({"project_id": "standard_project", "sessions": []}, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            json_out = temp_dir / "registry.json"
            view_out = temp_dir / "registry.md"
            html_out = temp_dir / "registry.html"

            proc = subprocess.run(
                [
                    sys.executable,
                    str(script_path),
                    "--project-id",
                    "standard_project",
                    "--config",
                    str(config_path),
                    "--workspace-root",
                    str(repo_root),
                    "--session-json",
                    str(session_json),
                    "--output",
                    str(json_out),
                    "--view-output",
                    str(view_out),
                    "--html-output",
                    str(html_out),
                ],
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                timeout=180,
            )

            self.assertEqual(proc.returncode, 0, proc.stderr or proc.stdout)
            self.assertTrue(json_out.exists())
            self.assertTrue(view_out.exists())
            self.assertTrue(html_out.exists())

            payload = json.loads(json_out.read_text(encoding="utf-8"))
            project = payload.get("project") or {}
            summary = payload.get("summary") or {}
            self.assertEqual(project.get("project_id"), "standard_project")
            self.assertEqual(summary.get("channel_count"), 12)


if __name__ == "__main__":
    unittest.main()
