import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class OverviewOfficialSiteEntryUiLogicTests(unittest.TestCase):
    def test_overview_header_places_official_site_link_after_logo(self) -> None:
        html = (REPO_ROOT / "web" / "overview.html.tpl").read_text(encoding="utf-8")

        brand_start = html.index('<div class="brand-row">')
        title_index = html.index('id="title"', brand_start)
        link_index = html.index('id="officialSiteLink"', brand_start)
        self.assertLess(title_index, link_index)
        self.assertIn('href="https://qoreon.com"', html)
        self.assertIn('target="_blank"', html)
        self.assertIn('rel="noopener noreferrer"', html)

    def test_overview_header_has_official_site_link_style(self) -> None:
        css = (REPO_ROOT / "web" / "overview.css").read_text(encoding="utf-8")

        self.assertIn(".brand-row", css)
        self.assertIn(".official-site-link", css)
        self.assertIn("height: 32px;", css)

    def test_task_page_does_not_keep_project_header_website_entry(self) -> None:
        task_html = (REPO_ROOT / "web" / "task.html.tpl").read_text(encoding="utf-8")
        task_js = (REPO_ROOT / "web" / "task.js").read_text(encoding="utf-8")

        self.assertNotIn("projectWebsiteLink", task_html)
        self.assertNotIn("updateProjectWebsiteLink", task_js)


if __name__ == "__main__":
    unittest.main()
