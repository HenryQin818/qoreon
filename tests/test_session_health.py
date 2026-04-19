import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from task_dashboard.session_health import analyze_codex_session_logs, build_session_health_page, index_codex_log_files
from task_dashboard.runtime.session_health_registry import SessionHealthRuntimeRegistry


class SessionHealthTests(unittest.TestCase):
    def test_analyze_codex_session_logs_counts_turns_and_compactions(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            log_path = root / "sessions" / "2026" / "03" / "11" / "rollout-2026-03-11T12-00-00-019c561b-22a1-7632-a667-19c1a5249b41.jsonl"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text(
                "\n".join(
                    [
                        '{"timestamp":"2026-03-10T10:00:00Z","type":"turn_context","payload":{}}',
                        '{"timestamp":"2026-03-10T11:00:00Z","type":"compacted","payload":{}}',
                        '{"timestamp":"2026-03-10T12:00:00Z","type":"turn_context","payload":{}}',
                    ]
                ),
                encoding="utf-8",
            )
            index = index_codex_log_files([root / "sessions"])
            data = analyze_codex_session_logs("019c561b-22a1-7632-a667-19c1a5249b41", index)
            self.assertTrue(data["has_log"])
            self.assertEqual(data["turn_context_count"], 2)
            self.assertEqual(data["compacted_count"], 1)
            self.assertTrue(str(data["last_compacted_at"]).startswith("2026-03-10T"))

    def test_analyze_codex_session_logs_observes_compaction_before_after_usage(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            log_path = root / "sessions" / "2026" / "03" / "12" / "rollout-2026-03-12T00-55-36-019cddd3-454e-7140-9881-0b7f6e936847.jsonl"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text(
                "\n".join(
                    [
                        '{"timestamp":"2026-03-12T00:56:00Z","type":"event_msg","payload":{"type":"token_count","info":{"last_token_usage":{"total_tokens":209304},"model_context_window":258400}}}',
                        '{"timestamp":"2026-03-12T00:56:10Z","type":"event_msg","payload":{"type":"context_compacted"}}',
                        '{"timestamp":"2026-03-12T00:56:12Z","type":"event_msg","payload":{"type":"token_count","info":{"last_token_usage":{"total_tokens":178296},"model_context_window":258400}}}',
                    ]
                ),
                encoding="utf-8",
            )
            index = index_codex_log_files([root / "sessions"])
            data = analyze_codex_session_logs("019cddd3-454e-7140-9881-0b7f6e936847", index)
            self.assertEqual(data["compacted_count"], 1)
            self.assertEqual(data["recent_after_usage_pcts"], [69.0])
            self.assertEqual(data["last_after_usage_pct"], 69.0)
            self.assertEqual(len(data["compaction_observations"]), 1)
            self.assertEqual(data["compaction_observations"][0]["before_pct"], 81.0)
            self.assertEqual(data["compaction_observations"][0]["after_pct"], 69.0)

    def test_analyze_codex_session_logs_prefers_recent_tail_when_log_is_truncated(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            log_path = root / "sessions" / "2026" / "04" / "13" / "rollout-2026-04-13T00-00-00-019d75f8-a187-75d2-a118-c1a187ae2a76.jsonl"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            filler = [
                f'{{"timestamp":"2026-04-10T10:{i:02d}:00Z","type":"turn_context","payload":{{"idx":{i}}}}}'
                for i in range(30)
            ]
            tail = [
                '{"timestamp":"2026-04-13T07:55:00Z","type":"event_msg","payload":{"type":"token_count","info":{"last_token_usage":{"total_tokens":206720},"model_context_window":258400}}}',
                '{"timestamp":"2026-04-13T07:56:00Z","type":"event_msg","payload":{"type":"context_compacted"}}',
                '{"timestamp":"2026-04-13T07:56:05Z","type":"event_msg","payload":{"type":"token_count","info":{"last_token_usage":{"total_tokens":103360},"model_context_window":258400}}}',
            ]
            log_path.write_text("\n".join(filler + tail), encoding="utf-8")
            index = index_codex_log_files([root / "sessions"])
            with mock.patch.dict("os.environ", {"TASK_DASHBOARD_SESSION_HEALTH_MAX_LOG_BYTES": "512"}):
                data = analyze_codex_session_logs("019d75f8-a187-75d2-a118-c1a187ae2a76", index)
            self.assertTrue(data["log_truncated"])
            self.assertEqual(data["compacted_count"], 1)
            self.assertTrue(str(data["last_compacted_at"]).startswith("2026-04-13T15:56:00+08:00"))
            self.assertEqual(data["recent_after_usage_pcts"], [40.0])
            self.assertEqual(data["compaction_observations"][0]["before_pct"], 80.0)
            self.assertEqual(data["compaction_observations"][0]["after_pct"], 40.0)

    def test_build_session_health_page_marks_overloaded_session_high_risk(self) -> None:
        fake_metrics = {
            "has_log": True,
            "log_paths": ["/tmp/one.jsonl"],
            "log_paths_count": 1,
            "log_size_bytes": 5_000_000,
            "log_size_mb": 512.0,
            "turn_context_count": 1500,
            "compacted_count": 42,
            "first_event_at": "2026-03-01T10:00:00+08:00",
            "last_event_at": "2026-03-11T09:00:00+08:00",
            "last_compacted_at": "2026-03-11T08:00:00+08:00",
            "compaction_timestamps": [
                "2026-03-10T12:00:00+08:00",
                "2026-03-11T02:00:00+08:00",
                "2026-03-11T05:00:00+08:00",
                "2026-03-11T08:00:00+08:00",
            ],
            "compaction_observations": [
                {
                    "compacted_at": "2026-03-10T12:00:00+08:00",
                    "before_pct": 76.0,
                    "after_pct": 64.0,
                    "before_observed_at": "2026-03-10T11:59:58+08:00",
                    "after_observed_at": "2026-03-10T12:00:03+08:00",
                },
                {
                    "compacted_at": "2026-03-11T02:00:00+08:00",
                    "before_pct": 79.0,
                    "after_pct": 67.0,
                    "before_observed_at": "2026-03-11T01:59:58+08:00",
                    "after_observed_at": "2026-03-11T02:00:02+08:00",
                },
                {
                    "compacted_at": "2026-03-11T05:00:00+08:00",
                    "before_pct": 80.0,
                    "after_pct": 68.0,
                    "before_observed_at": "2026-03-11T04:59:58+08:00",
                    "after_observed_at": "2026-03-11T05:00:02+08:00",
                },
                {
                    "compacted_at": "2026-03-11T08:00:00+08:00",
                    "before_pct": 81.0,
                    "after_pct": 69.0,
                    "before_observed_at": "2026-03-11T07:59:58+08:00",
                    "after_observed_at": "2026-03-11T08:00:02+08:00",
                },
            ],
            "recent_after_usage_pcts": [64.0, 67.0, 68.0, 69.0],
            "last_after_usage_pct": 69.0,
            "avg_turns_between_compactions": 6.0,
            "avg_hours_between_compactions": 4.0,
            "turns_since_last_compaction": 3,
        }
        projects = [
            {
                "id": "task_dashboard",
                "name": "Task Dashboard",
                "channel_sessions": [
                    {
                        "name": "子级02-CCB运行时（server-并发-安全-启动）",
                        "alias": "子级02-链路守门",
                        "session_id": "019c561b-22a1-7632-a667-19c1a5249b41",
                        "cli_type": "codex",
                        "source": "session_store",
                        "created_at": "2026-03-01T10:00:00+08:00",
                        "last_used_at": "2026-03-11T09:30:00+08:00",
                        "status": "active",
                        "is_primary": True,
                    },
                    {
                        "name": "子级04-前端体验（task-overview 页面交互）",
                        "alias": "子级04A-页面实现",
                        "session_id": "019c561c-8b6c-7c60-b66f-63096d1a4de9",
                        "cli_type": "codex",
                        "source": "session_store",
                        "created_at": "2026-03-08T10:00:00+08:00",
                        "last_used_at": "2026-03-11T09:30:00+08:00",
                        "status": "active",
                        "is_primary": False,
                    },
                ],
            }
        ]
        with mock.patch("task_dashboard.session_health.index_codex_log_files", return_value={}), mock.patch(
            "task_dashboard.session_health.analyze_codex_session_logs",
            side_effect=[
                fake_metrics,
                dict(
                    fake_metrics,
                    compacted_count=0,
                    turn_context_count=10,
                    log_size_mb=1.0,
                    last_compacted_at="",
                    compaction_timestamps=[],
                    compaction_observations=[],
                    recent_after_usage_pcts=[],
                    last_after_usage_pct=None,
                ),
            ],
        ):
            payload = build_session_health_page(
                projects,
                generated_at="2026-03-11T17:10:00+08:00",
                task_page_link="project-task-dashboard.html",
                overview_page_link="project-overview-dashboard.html",
                communication_page_link="project-communication-audit.html",
                agent_curtain_page_link="project-agent-curtain.html",
                session_health_page_link="project-session-health-dashboard.html",
            )
        self.assertEqual(payload["summary"]["risk_counts"]["high"], 1)
        self.assertEqual(payload["summary"]["multi_active_channel_count"], 0)
        row = payload["top_high_risk"][0]
        self.assertEqual(row["risk_level"], "high")
        self.assertEqual(row["health_action"], "高优先级轮换")
        self.assertTrue(row["recent_compaction"])
        self.assertGreaterEqual(row["baseline_floor_pct"], 60)
        self.assertTrue(row["sustained_high_floor"])
        self.assertEqual(row["baseline_floor_status"], "高优先级轮换")
        self.assertEqual(row["baseline_floor_source"], "observed")
        self.assertFalse(row["baseline_floor_estimated"])
        self.assertEqual(row["recent_after_usage_pcts"], [64.0, 67.0, 68.0, 69.0])

    def test_build_session_health_page_skips_deleted_sessions(self) -> None:
        projects = [
            {
                "id": "task_dashboard",
                "name": "Task Dashboard",
                "channel_sessions": [
                    {
                        "name": "子级02-CCB运行时（server-并发-安全-启动）",
                        "alias": "服务开发",
                        "session_id": "019c561b-22a1-7632-a667-19c1a5249b41",
                        "cli_type": "codex",
                        "source": "session_store",
                        "created_at": "2026-03-01T10:00:00+08:00",
                        "last_used_at": "2026-03-11T09:30:00+08:00",
                        "status": "active",
                        "is_primary": False,
                        "is_deleted": True,
                    },
                    {
                        "name": "子级02-CCB运行时（server-并发-安全-启动）",
                        "alias": "服务开发",
                        "session_id": "019cddd3-454e-7140-9881-0b7f6e936847",
                        "cli_type": "codex",
                        "source": "session_store",
                        "created_at": "2026-03-12T00:55:52+08:00",
                        "last_used_at": "2026-03-12T00:56:16+08:00",
                        "status": "active",
                        "is_primary": True,
                        "is_deleted": False,
                    },
                ],
            }
        ]
        with mock.patch("task_dashboard.session_health.index_codex_log_files", return_value={}), mock.patch(
            "task_dashboard.session_health.analyze_codex_session_logs",
            return_value={
                "has_log": True,
                "log_paths": ["/tmp/new.jsonl"],
                "log_paths_count": 1,
                "log_size_bytes": 1024,
                "log_size_mb": 1.0,
                "turn_context_count": 2,
                "compacted_count": 0,
                "first_event_at": "2026-03-12T00:55:47+08:00",
                "last_event_at": "2026-03-12T00:56:30+08:00",
                "last_compacted_at": "",
                "compaction_timestamps": [],
                "compaction_observations": [],
                "recent_after_usage_pcts": [],
                "last_after_usage_pct": None,
                "avg_turns_between_compactions": None,
                "avg_hours_between_compactions": None,
                "turns_since_last_compaction": None,
            },
        ):
            payload = build_session_health_page(
                projects,
                generated_at="2026-03-12T01:10:00+08:00",
                task_page_link="project-task-dashboard.html",
                overview_page_link="project-overview-dashboard.html",
                communication_page_link="project-communication-audit.html",
                agent_curtain_page_link="project-agent-curtain.html",
                session_health_page_link="project-session-health-dashboard.html",
            )
        self.assertEqual(payload["summary"]["session_count"], 1)
        self.assertEqual(payload["summary"]["deleted_skipped_count"], 1)
        self.assertEqual(payload["sessions"][0]["session_id"], "019cddd3-454e-7140-9881-0b7f6e936847")
        self.assertEqual(payload["project_id"], "task_dashboard")
        self.assertEqual(payload["live_sessions_endpoint"], "/api/sessions?project_id=task_dashboard")
        self.assertEqual(payload["live_health_endpoint"], "/api/session-health?project_id=task_dashboard")
        self.assertEqual(payload["thresholds"]["reset_button_threshold_pct"], 20)
        self.assertEqual(payload["thresholds"]["reset_button_rule"], ">=20%")

    def test_build_session_health_page_keeps_multiple_projects_and_session_health_config(self) -> None:
        projects = [
            {
                "id": "website_work",
                "name": "网站工作",
                "session_health_config": {
                    "enabled": False,
                    "interval_minutes": 240,
                },
                "channel_sessions": [
                    {
                        "name": "00-主体-总任务批次",
                        "alias": "网站工作总控",
                        "session_id": "11111111-1111-1111-1111-111111111111",
                        "cli_type": "codex",
                        "status": "active",
                        "is_primary": True,
                    }
                ],
            },
            {
                "id": "task_dashboard",
                "name": "任务看板",
                "session_health_config": {
                    "enabled": True,
                    "interval_minutes": 120,
                },
                "channel_sessions": [
                    {
                        "name": "主体-总控",
                        "alias": "总控-项目经理",
                        "session_id": "019cdb7f-1c8f-7280-970e-a50c2e114cef",
                        "cli_type": "codex",
                        "status": "active",
                        "is_primary": True,
                    }
                ],
            },
        ]
        with mock.patch("task_dashboard.session_health.index_codex_log_files", return_value={}), mock.patch(
            "task_dashboard.session_health.analyze_codex_session_logs",
            return_value={
                "has_log": False,
                "log_paths": [],
                "log_paths_count": 0,
                "log_size_bytes": 0,
                "log_size_mb": 0.0,
                "turn_context_count": 0,
                "compacted_count": 0,
                "first_event_at": "",
                "last_event_at": "",
                "last_compacted_at": "",
                "compaction_timestamps": [],
                "compaction_observations": [],
                "recent_after_usage_pcts": [],
                "last_after_usage_pct": None,
                "avg_turns_between_compactions": None,
                "avg_hours_between_compactions": None,
                "turns_since_last_compaction": None,
            },
        ):
            payload = build_session_health_page(
                projects,
                generated_at="2026-03-16T09:30:00+08:00",
                task_page_link="project-task-dashboard.html",
                overview_page_link="project-overview-dashboard.html",
                communication_page_link="project-communication-audit.html",
                agent_curtain_page_link="project-agent-curtain.html",
                session_health_page_link="project-session-health-dashboard.html",
            )
        self.assertEqual(payload["summary"]["project_count"], 2)
        self.assertEqual(payload["summary"]["session_count"], 2)
        self.assertEqual(len(payload["projects"]), 2)
        self.assertEqual(payload["project_id"], "task_dashboard")
        self.assertEqual(payload["global_automation"]["project_count"], 2)
        self.assertEqual(payload["global_automation"]["enabled_count"], 1)
        website = next(item for item in payload["projects"] if item["project_id"] == "website_work")
        self.assertFalse(website["session_health"]["enabled"])
        self.assertEqual(website["session_health"]["interval_minutes"], 240)

    def test_session_health_runtime_registry_decorates_payload(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = SimpleNamespace(runs_dir=Path(td) / ".runs")
            base_payload = {
                "generated_at": "2026-03-16T09:30:00+08:00",
                "project_id": "task_dashboard",
                "project_name": "任务看板",
                "summary": {},
                "projects": [],
                "sessions": [],
                "links": {},
            }
            registry = SessionHealthRuntimeRegistry(
                store=store,
                build_payload=lambda project_id: dict(base_payload, project_id=project_id),
                config_loader=lambda: {
                    "projects": [
                        {
                            "id": "task_dashboard",
                            "name": "任务看板",
                            "session_health": {
                                "enabled": True,
                                "interval_minutes": 120,
                            },
                        },
                        {
                            "id": "website_work",
                            "name": "网站工作",
                            "session_health": {
                                "enabled": False,
                                "interval_minutes": 240,
                            },
                        },
                    ]
                },
            )
            with mock.patch(
                "task_dashboard.runtime.session_health_registry.load_project_session_health_config",
                side_effect=lambda project_id: {
                    "project_id": project_id,
                    "project_name": "任务看板" if project_id == "task_dashboard" else "网站工作",
                    "enabled": project_id == "task_dashboard",
                    "interval_minutes": 120 if project_id == "task_dashboard" else 240,
                    "configured": True,
                },
            ):
                payload = registry.get_payload("task_dashboard", refresh=False)
        self.assertIn("session_health", payload)
        self.assertIn("global_automation", payload)
        self.assertEqual(payload["session_health"]["project_id"], "task_dashboard")
        self.assertEqual(payload["global_automation"]["project_count"], 2)


if __name__ == "__main__":
    unittest.main()
