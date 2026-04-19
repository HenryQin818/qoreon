import unittest

from task_dashboard.overview import build_overview


class OverviewMetricsTests(unittest.TestCase):
    def test_overview_totals_use_task_items_only_and_keep_items_totals(self) -> None:
        projects_meta = [
            {
                "id": "p1",
                "name": "P1",
                "channels": [{"name": "子级01"}],
                "channel_sessions": [{"name": "子级01", "session_id": "019c0000-0000-7000-8000-000000000000"}],
            }
        ]
        items_payload = [
            {
                "project_id": "p1",
                "channel": "子级01",
                "status": "进行中",
                "type": "任务",
                "updated_at": "2026-03-03T10:00:00+08:00",
            },
            {
                "project_id": "p1",
                "channel": "子级01",
                "status": "已完成",
                "type": "任务",
                "updated_at": "2026-03-03T09:00:00+08:00",
            },
            {
                "project_id": "p1",
                "channel": "子级01",
                "status": "进行中",
                "type": "沉淀",
                "updated_at": "2026-03-03T08:00:00+08:00",
            },
            {
                "project_id": "p1",
                "channel": "子级01",
                "status": "需求暂存",
                "type": "需求",
                "updated_at": "2026-03-03T07:00:00+08:00",
            },
        ]

        out = build_overview(projects_meta, items_payload)
        totals = out["totals"]
        self.assertEqual(totals["total"], 2)
        self.assertEqual(totals["active"], 1)
        self.assertEqual(totals["done"], 1)
        self.assertEqual(totals["requirements_total"], 1)
        self.assertEqual(totals["requirements_active"], 1)
        self.assertEqual(totals["knowledge_total"], 1)
        self.assertEqual(totals["items_total"], 4)
        self.assertEqual(totals["items_active"], 3)
        self.assertEqual(totals["items_done"], 1)
        self.assertEqual(totals["primary_status_counts"]["in_progress"], 1)
        self.assertEqual(totals["primary_status_counts"]["done"], 1)
        self.assertEqual(totals["primary_status_counts"]["todo"], 0)

        p = out["projects"][0]
        self.assertEqual(p["totals"]["total"], 2)
        self.assertEqual(p["totals"]["requirements_total"], 1)
        self.assertEqual(p["totals"]["knowledge_total"], 1)
        self.assertEqual(p["totals"]["items_total"], 4)
        self.assertEqual(p["totals"]["primary_status_counts"]["in_progress"], 1)

        c = p["channels_data"][0]
        self.assertEqual(c["totals"]["total"], 2)
        self.assertEqual(c["totals"]["requirements_total"], 1)
        self.assertEqual(c["totals"]["knowledge_total"], 1)
        self.assertEqual(c["totals"]["items_total"], 4)
        self.assertEqual(c["totals"]["primary_status_counts"]["done"], 1)

    def test_channel_with_only_knowledge_keeps_zero_task_total(self) -> None:
        projects_meta = [{"id": "p1", "name": "P1", "channels": [{"name": "知识通道"}], "channel_sessions": []}]
        items_payload = [
            {
                "project_id": "p1",
                "channel": "知识通道",
                "status": "进行中",
                "type": "沉淀",
                "updated_at": "2026-03-03T08:00:00+08:00",
            },
            {
                "project_id": "p1",
                "channel": "知识通道",
                "status": "需求暂存",
                "type": "需求",
                "updated_at": "2026-03-03T09:00:00+08:00",
            }
        ]
        out = build_overview(projects_meta, items_payload)
        p = out["projects"][0]
        self.assertEqual(p["totals"]["total"], 0)
        self.assertEqual(p["totals"]["requirements_total"], 1)
        self.assertEqual(p["totals"]["knowledge_total"], 1)
        self.assertEqual(p["totals"]["items_total"], 2)
        self.assertEqual(p["channels_data"][0]["totals"]["total"], 0)
        self.assertEqual(p["channels_data"][0]["totals"]["requirements_total"], 1)
        self.assertEqual(p["channels_data"][0]["totals"]["knowledge_total"], 1)
        self.assertEqual(p["channels_data"][0]["totals"]["items_total"], 2)
        self.assertEqual(p["channels_data"][0]["totals"]["primary_status_counts"]["todo"], 0)

    def test_requirements_totals_respect_explicit_disabled_switch(self) -> None:
        projects_meta = [
            {
                "id": "p1",
                "name": "P1",
                "channels": [{"name": "子级01"}],
                "channel_sessions": [{"name": "子级01", "enable_requirements": False}],
            }
        ]
        items_payload = [
            {
                "project_id": "p1",
                "channel": "子级01",
                "status": "进行中",
                "type": "需求",
                "updated_at": "2026-03-03T10:00:00+08:00",
            }
        ]
        out = build_overview(projects_meta, items_payload)
        self.assertEqual(out["totals"]["requirements_total"], 0)
        self.assertEqual(out["totals"]["requirements_active"], 0)
        p = out["projects"][0]
        self.assertEqual(p["totals"]["requirements_total"], 0)
        self.assertEqual(p["channels_data"][0]["totals"]["requirements_total"], 0)
        self.assertEqual(p["channels_data"][0]["requirements_source"], "config")
        self.assertFalse(bool(p["channels_data"][0]["requirements_enabled_effective"]))

    def test_requirements_switch_supports_camel_case_field(self) -> None:
        projects_meta = [
            {
                "id": "p1",
                "name": "P1",
                "channels": [{"name": "子级01"}],
                "channel_sessions": [{"name": "子级01", "enableRequirements": True}],
            }
        ]
        items_payload = [
            {
                "project_id": "p1",
                "channel": "子级01",
                "status": "进行中",
                "type": "需求",
                "updated_at": "2026-03-03T10:00:00+08:00",
            }
        ]
        out = build_overview(projects_meta, items_payload)
        self.assertEqual(out["totals"]["requirements_total"], 1)
        p = out["projects"][0]
        self.assertEqual(p["channels_data"][0]["requirements_source"], "config")
        self.assertTrue(bool(p["channels_data"][0]["requirements_enabled_effective"]))

    def test_primary_status_counts_separate_pending_acceptance_and_paused(self) -> None:
        projects_meta = [
            {
                "id": "p1",
                "name": "P1",
                "channels": [{"name": "子级01"}],
                "channel_sessions": [{"name": "子级01", "session_id": "019c0000-0000-7000-8000-000000000000"}],
            }
        ]
        items_payload = [
            {
                "project_id": "p1",
                "channel": "子级01",
                "status": "督办",
                "type": "任务",
                "updated_at": "2026-03-03T10:00:00+08:00",
            },
            {
                "project_id": "p1",
                "channel": "子级01",
                "status": "待验收",
                "type": "任务",
                "updated_at": "2026-03-03T09:00:00+08:00",
            },
            {
                "project_id": "p1",
                "channel": "子级01",
                "status": "暂缓",
                "type": "任务",
                "updated_at": "2026-03-03T08:00:00+08:00",
            },
        ]

        out = build_overview(projects_meta, items_payload)
        counts = out["totals"]["primary_status_counts"]
        self.assertEqual(counts["todo"], 1)
        self.assertEqual(counts["pending_acceptance"], 1)
        self.assertEqual(counts["paused"], 1)
        self.assertEqual(out["totals"]["supervised"], 1)


if __name__ == "__main__":
    unittest.main()
