import json
import unittest
from pathlib import Path


class PublicStandardProjectSkillsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[1]
        self.seed_root = self.repo_root / "examples" / "standard-project" / "seed"

    def _load(self, name: str) -> dict:
        return json.loads((self.seed_root / name).read_text(encoding="utf-8"))

    def test_public_common_skills_are_packaged(self) -> None:
        payload = self._load("skills-manifest.json")
        skills = payload.get("skills") or []
        names = {str(item.get("name") or "") for item in skills if isinstance(item, dict)}
        expected = {
            "project-startup-collab-suite",
            "agent-init-training-playbook",
            "collab-message-send",
            "ccr-update-playbook",
            "skills-governance-upgrade",
            "session-health-inspector",
            "session-rotation-handoff",
            "task-health-organizer",
        }
        self.assertEqual(names, expected)
        self.assertNotIn("master-control", names)
        self.assertNotIn("runtime-backend", names)
        for item in skills:
            if not isinstance(item, dict):
                continue
            rel = str(item.get("path") or "").strip()
            self.assertTrue(rel, item)
            self.assertTrue((self.repo_root / rel).exists(), rel)

    def test_agents_reference_required_public_skills(self) -> None:
        agents = self._load("agents_seed.json").get("agents") or []
        by_id = {str(item.get("agent_id") or ""): item for item in agents if isinstance(item, dict)}
        self.assertIn("project-startup-collab-suite", by_id["master_control"]["skills"])
        self.assertIn("collab-message-send", by_id["master_control"]["skills"])
        self.assertIn("ccr-update-playbook", by_id["structure_governor"]["skills"])
        self.assertIn("skills-governance-upgrade", by_id["skills_governor"]["skills"])
        self.assertIn("session-health-inspector", by_id["project_ops"]["skills"])
        self.assertIn("task-health-organizer", by_id["info_organizer"]["skills"])
        self.assertNotIn("master-control", by_id["master_control"]["skills"])


if __name__ == "__main__":
    unittest.main()
