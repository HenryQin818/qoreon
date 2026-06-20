from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from task_dashboard.communication_audit import (
    audit_communication_patterns,
    render_communication_audit_markdown,
)


def _write_meta(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


class TestCommunicationAudit(unittest.TestCase):
    def test_audit_communication_patterns_collects_key_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            runs = Path(td) / ".runs"
            runs.mkdir(parents=True, exist_ok=True)

            _write_meta(
                runs / "user-1.json",
                {
                    "id": "user-1",
                    "channelName": "子级01",
                    "sessionId": "s-1",
                    "status": "done",
                    "createdAt": "2026-03-09T10:00:00+0800",
                    "sender_type": "user",
                    "sender_id": "web-user",
                    "sender_name": "我",
                },
            )
            _write_meta(
                runs / "agent-1.json",
                {
                    "id": "agent-1",
                    "channelName": "子级01",
                    "sessionId": "s-1",
                    "status": "done",
                    "createdAt": "2026-03-09T10:05:00+0800",
                    "sender_type": "agent",
                    "sender_id": "agent:sub01",
                    "sender_name": "子级01-构建聚合",
                    "reply_to_run_id": "user-1",
                    "reply_to_sender_name": "我",
                },
            )
            _write_meta(
                runs / "system-1.json",
                {
                    "id": "system-1",
                    "channelName": "子级01",
                    "sessionId": "s-1",
                    "status": "done",
                    "createdAt": "2026-03-09T10:20:00+0800",
                    "sender_type": "system",
                    "sender_id": "system",
                    "sender_name": "系统",
                    "communication_view": {
                        "message_kind": "system_callback",
                        "event_reason": "success",
                        "dispatch_state": "resolved",
                        "source_project_id": "task_dashboard",
                        "source_channel": "主体-总控",
                        "source_session_id": "s-1",
                        "target_project_id": "task_dashboard",
                        "target_channel": "子级01",
                        "target_session_id": "s-1",
                        "route_mismatch": False,
                        "route_resolution": {"degrade_reason": ""},
                    },
                    "receipt_summary": {
                        "version": "v1",
                        "message_kind": "system_callback",
                    },
                },
            )
            _write_meta(
                runs / "legacy-1.json",
                {
                    "id": "legacy-1",
                    "channelName": "子级02",
                    "sessionId": "s-2",
                    "status": "error",
                    "createdAt": "2026-03-09T10:30:00+0800",
                    "sender_type": "legacy",
                    "sender_id": "legacy",
                    "sender_name": "历史消息（来源未知）",
                    "mention_targets": [{"channel_name": "子级01", "session_id": "s-1"}],
                    "error": "run interrupted",
                },
            )

            summary = audit_communication_patterns(runs_dirs=[runs], response_window_hours=2.0, top_limit=5)
            self.assertEqual(summary["totals"]["runs"], 4)
            self.assertEqual(summary["totals"]["reply_to_runs"], 1)
            self.assertEqual(summary["totals"]["mention_target_runs"], 1)
            self.assertEqual(summary["totals"]["communication_view_runs"], 1)
            self.assertEqual(summary["totals"]["receipt_summary_runs"], 1)
            self.assertEqual(summary["totals"]["legacy_runs"], 1)
            self.assertEqual(summary["response_metrics"]["user_total"], 1)
            self.assertEqual(summary["response_metrics"]["user_responded_same_channel_within_window"], 1)
            self.assertEqual(summary["response_metrics"]["agent_system_follow_same_session_within_window"], 1)
            self.assertEqual(summary["rates"]["reply_to_rate_pct"], 25.0)
            self.assertEqual(summary["rates"]["legacy_rate_pct"], 25.0)
            self.assertEqual(summary["top_source_projects"][0]["name"], "task_dashboard")
            self.assertEqual(summary["top_target_projects"][0]["name"], "task_dashboard")
            self.assertEqual(summary["top_target_sessions"][0]["name"], "s-1")
            self.assertIn("collaboration_integrity_audit", summary)

    def test_collaboration_integrity_audit_classifies_ccr_and_delivery_issues(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            runs = root / ".runs"
            runs.mkdir(parents=True, exist_ok=True)
            registry = root / "registry" / "collab-registry.v1.json"
            registry.parent.mkdir(parents=True, exist_ok=True)
            registry.write_text(
                json.dumps(
                    {
                        "project": {"project_id": "demo_project"},
                        "ccr_validation": {
                            "version": "p0_identity_gate_v1",
                            "ok": False,
                            "blocking": True,
                            "issues": [
                                {
                                    "code": "duplicate_session_id",
                                    "message": "同一 session_id 出现在多个通道",
                                    "project_id": "demo_project",
                                    "channel_name": "主体-总控",
                                    "session_id": "sid-a",
                                    "field": "session_id",
                                },
                                {
                                    "code": "missing_readable_identity",
                                    "message": "Agent 可读身份缺失",
                                    "project_id": "demo_project",
                                    "channel_name": "主体-总控",
                                    "session_id": "sid-a",
                                    "field": "alias",
                                },
                                {
                                    "code": "readable_identity_conflict",
                                    "message": "同通道可读名冲突",
                                    "project_id": "demo_project",
                                    "channel_name": "主体-总控",
                                    "field": "alias/display_name",
                                },
                            ],
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            _write_meta(
                runs / "20260618-120000-bad001.json",
                {
                    "id": "20260618-120000-bad001",
                    "channelName": "主体-总控",
                    "sessionId": "sid-a",
                    "status": "done",
                    "createdAt": "2026-06-18T12:00:00+0800",
                    "sender_type": "agent",
                    "sender_id": "agent:source",
                    "sender_name": "来源Agent",
                    "interaction_mode": "task_with_receipt",
                    "message_kind": "collab_update",
                    "target_ref": {"session_id": "sid-other"},
                    "visible_in_channel_chat": False,
                },
            )
            _write_meta(
                runs / "20260618-121000-bad002.json",
                {
                    "id": "20260618-121000-bad002",
                    "channelName": "主体-总控",
                    "sessionId": "sid-a",
                    "status": "done",
                    "createdAt": "2026-06-18T12:10:00+0800",
                    "sender_type": "system",
                    "sender_id": "project_bootstrap_onboarding",
                    "sender_name": "项目启动上岗门禁",
                    "interaction_mode": "dialog_now",
                    "message_kind": "collab_update",
                    "visible_in_channel_chat": True,
                    "onboarding_message_type": "first_visible_message",
                },
            )

            summary = audit_communication_patterns(
                runs_dirs=[runs],
                registry_paths=[registry],
                response_window_hours=2.0,
                top_limit=5,
            )
            audit = summary["collaboration_integrity_audit"]
            self.assertFalse(audit["ok"])
            categories = audit["category_counts"]
            self.assertEqual(categories["ccr_degraded"], 1)
            self.assertEqual(categories["identity_unresolved"], 1)
            self.assertEqual(categories["readable_name_conflict"], 1)
            self.assertEqual(categories["delivery_evidence_missing"], 1)
            self.assertEqual(categories["missing_source_ref"], 1)
            delivery_item = next(
                item for item in audit["missing_items"] if item.get("category") == "delivery_evidence_missing"
            )
            self.assertIn("target_session_id_mismatch", delivery_item["missing_fields"])
            self.assertIn("visible_in_channel_chat", delivery_item["missing_fields"])
            refs_item = next(item for item in audit["missing_items"] if item.get("category") == "missing_source_ref")
            self.assertEqual(refs_item["missing_fields"], ["source_ref", "callback_to"])

    def test_collaboration_integrity_audit_passes_verified_delivery(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            runs = root / ".runs"
            runs.mkdir(parents=True, exist_ok=True)
            registry = root / "registry" / "collab-registry.v1.json"
            registry.parent.mkdir(parents=True, exist_ok=True)
            registry.write_text(
                json.dumps(
                    {
                        "project": {"project_id": "demo_project"},
                        "ccr_validation": {"version": "p0_identity_gate_v1", "ok": True, "blocking": False, "issues": []},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            _write_meta(
                runs / "20260618-130000-good01.json",
                {
                    "id": "20260618-130000-good01",
                    "channelName": "主体-总控",
                    "sessionId": "sid-a",
                    "status": "done",
                    "createdAt": "2026-06-18T13:00:00+0800",
                    "sender_type": "system",
                    "sender_id": "project_bootstrap_onboarding",
                    "sender_name": "项目启动上岗门禁",
                    "interaction_mode": "dialog_now",
                    "message_kind": "collab_update",
                    "target_ref": {"session_id": "sid-a"},
                    "source_ref": {"session_id": "sid-source"},
                    "callback_to": {"session_id": "sid-source"},
                    "visible_in_channel_chat": True,
                    "onboarding_message_type": "init_training",
                },
            )

            summary = audit_communication_patterns(runs_dirs=[runs], registry_paths=[registry])
            audit = summary["collaboration_integrity_audit"]
            self.assertTrue(audit["ok"])
            self.assertEqual(audit["issue_count"], 0)
            self.assertEqual(audit["delivery"]["delivery_verified_count"], 1)

    def test_render_markdown_contains_core_sections(self) -> None:
        summary = {
            "scope": {"runs_dirs": ["/tmp/runs"], "response_window_hours": 2.0},
            "time_range": {"first_created_at": "2026-03-09T10:00:00+0800", "last_created_at": "2026-03-09T11:00:00+0800"},
            "totals": {"runs": 10, "reply_to_runs": 2, "mention_target_runs": 1, "communication_view_runs": 4, "receipt_summary_runs": 3},
            "rates": {
                "reply_to_rate_pct": 20.0,
                "mention_target_rate_pct": 10.0,
                "communication_view_rate_pct": 40.0,
                "receipt_summary_rate_pct": 30.0,
                "legacy_rate_pct": 0.0,
                "route_mismatch_rate_pct": 0.0,
            },
            "response_metrics": {
                "user_responded_same_channel_rate_pct": 80.0,
                "median_user_same_channel_latency_s": 600.0,
                "agent_system_follow_same_session_rate_pct": 50.0,
                "median_agent_system_follow_latency_s": 300.0,
                "median_explicit_reply_latency_s": 120.0,
            },
            "sender_type_breakdown": [{"name": "system", "count": 4, "percent": 40.0}],
            "status_breakdown": [{"name": "done", "count": 9, "percent": 90.0}],
            "communication_message_kind_breakdown": [{"name": "system_callback", "count": 4, "percent": 100.0}],
            "receipt_summary_message_kind_breakdown": [{"name": "system_callback", "count": 3, "percent": 100.0}],
            "top_channels": [{"name": "主体-总控", "count": 3, "percent": 30.0}],
            "top_source_channels": [{"name": "主体-总控", "count": 3, "percent": 75.0}],
            "top_source_projects": [{"name": "task_dashboard", "count": 3, "percent": 75.0}],
            "top_target_projects": [{"name": "task_dashboard", "count": 3, "percent": 75.0}],
            "top_target_sessions": [{"name": "sid-1", "count": 2, "percent": 50.0}],
            "top_sender_names": [{"name": "我", "count": 2, "percent": 20.0}],
            "top_degrade_reasons": [{"name": "sender_agent_unresolved", "count": 2, "percent": 50.0}],
            "collaboration_integrity_audit": {
                "state": "degraded",
                "issue_count": 2,
                "category_counts": {"delivery_evidence_missing": 1, "missing_source_ref": 1},
            },
        }
        out = render_communication_audit_markdown(summary)
        self.assertIn("# 通讯分析报告", out)
        self.assertIn("## 核心指标", out)
        self.assertIn("## CCR 与送达证据巡检", out)
        self.assertIn("## 发送主体分布", out)
        self.assertIn("主体-总控", out)
        self.assertIn("## Top 来源项目", out)


if __name__ == "__main__":
    unittest.main()
