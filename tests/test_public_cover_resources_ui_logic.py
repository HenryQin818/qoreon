import unittest
from pathlib import Path

from task_dashboard.render import render_from_template


REPO_ROOT = Path(__file__).resolve().parents[1]


class PublicCoverResourcesUiLogicTests(unittest.TestCase):
    def test_public_cover_flow_is_local_only(self) -> None:
        source = (REPO_ROOT / "web" / "overview.js").read_text(encoding="utf-8")

        self.assertNotIn("/api/project-card-" + "covers", source)
        self.assertNotIn("/share/assets/project-covers/" + "registry.v1.json", source)
        self.assertIn("applyProjectCoverSelectionLocally(projectId, selectedCoverId)", source)
        self.assertIn("persistProjectCoverLocalCustomItems()", source)
        self.assertIn("applyProjectCoverSelectionLocally(projectId, customCover.id)", source)
        self.assertIn("applyProjectCoverAssignments(loadLocalProjectCoverAssignments())", source)

    def test_acceptance_pages_render_without_network_favicon(self) -> None:
        template_names = [
            "template.html",
            "template_overview.html",
            "template_status_report.html",
            "template_agent_directory.html",
            "template_session_health.html",
        ]

        for template_name in template_names:
            with self.subTest(template_name=template_name):
                rendered = render_from_template(REPO_ROOT, template_name, {})
                self.assertIn('<link rel="icon" href="data:," />', rendered)
                self.assertNotIn('href="/' + 'favicon.ico"', rendered)


if __name__ == "__main__":
    unittest.main()
