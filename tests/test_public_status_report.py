import json
import tempfile
import unittest
from pathlib import Path

from task_dashboard.status_report import build_status_report_page_data


class PublicStatusReportTests(unittest.TestCase):
    def test_build_status_report_page_data_reads_public_json_source(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            script_dir = Path(td)
            source_path = script_dir / "docs" / "status-report" / "task-dashboard-status-report.json"
            source_path.parent.mkdir(parents=True, exist_ok=True)
            source_path.write_text(
                json.dumps(
                    {
                        "page": {"title": "公开状态页"},
                        "hero": {"headline": "公开候选包"},
                        "summary_cards": [{"label": "范围", "value": "V1"}]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            payload = build_status_report_page_data(
                script_dir,
                generated_at="2026-03-20T12:00:00+08:00",
                dashboard={"title": "Task Dashboard OSS", "subtitle": ""},
                links={"task_page": "project-task-dashboard.html"},
            )
        report = payload["status_report"]
        self.assertEqual(report["title"], "公开状态页")
        self.assertEqual(report["hero"]["headline"], "公开候选包")
        self.assertEqual(report["summary_cards"][0]["value"], "V1")
        self.assertEqual(report["source_file"], "docs/status-report/task-dashboard-status-report.json")


if __name__ == "__main__":
    unittest.main()
