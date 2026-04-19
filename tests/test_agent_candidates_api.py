import tempfile
import unittest
from pathlib import Path

import server

from task_dashboard.runtime.agent_candidates import (
    build_agent_candidates_payload,
    list_agent_candidates_response,
)


class AgentCandidatesApiTests(unittest.TestCase):
    def test_build_agent_candidates_payload_collapses_to_one_recommended_session_per_channel(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            run_store = server.RunStore(base / ".runtime" / "stable" / ".runs")
            session_store = server.SessionStore(base_dir=run_store.runs_dir.parent)

            primary = session_store.create_session(
                "task_dashboard",
                "辅助01-项目结构治理（配置-目录-契约-迁移）",
                cli_type="codex",
                alias="结构治理主会话",
                session_id="019d1111-1111-7111-8111-111111111111",
            )
            session_store.update_session(primary["id"], is_primary=True, last_used_at="2026-03-19T10:00:00Z")
            child = session_store.create_session(
                "task_dashboard",
                "辅助01-项目结构治理（配置-目录-契约-迁移）",
                cli_type="codex",
                alias="结构治理旧子会话",
                session_id="019d1111-1111-7111-8111-222222222222",
            )
            session_store.update_session(child["id"], last_used_at="2026-03-19T12:00:00Z")

            older = session_store.create_session(
                "task_dashboard",
                "辅助04-原型设计与Demo可视化（静态数据填充-业务规格确认）",
                cli_type="codex",
                alias="原型旧会话",
                session_id="019d1111-1111-7111-8111-333333333333",
            )
            session_store.update_session(older["id"], is_primary=False, last_used_at="2026-03-19T09:00:00Z")
            newer = session_store.create_session(
                "task_dashboard",
                "辅助04-原型设计与Demo可视化（静态数据填充-业务规格确认）",
                cli_type="codex",
                alias="原型新会话",
                session_id="019d1111-1111-7111-8111-444444444444",
            )
            session_store.update_session(newer["id"], is_primary=False, last_used_at="2026-03-19T13:00:00Z")

            payload = build_agent_candidates_payload(
                session_store=session_store,
                store=run_store,
                project_id="task_dashboard",
                environment_name="stable",
                worktree_root=base,
                apply_effective_primary_flags=lambda _store, _pid, rows: rows,
                decorate_sessions_display_fields=lambda rows: rows,
                apply_session_context_rows=lambda sessions, **kwargs: sessions,
                apply_session_work_context=lambda row, **kwargs: row,
                attach_runtime_state_to_sessions=lambda _store, sessions, project_id="": sessions,
                heartbeat_runtime=None,
                load_session_heartbeat_config=lambda _row: {},
                heartbeat_summary_payload=lambda _row: {},
            )

            self.assertEqual(payload["raw_session_count"], 4)
            self.assertEqual(payload["count"], 2)
            self.assertEqual(
                (payload.get("agent_identity_audit") or {}).get("manual_backfill_required_count"),
                0,
            )
            rows = {str(row.get("channel_name") or ""): row for row in payload["agent_targets"]}
            self.assertEqual(rows["辅助01-项目结构治理（配置-目录-契约-迁移）"]["id"], primary["id"])
            self.assertEqual(rows["辅助01-项目结构治理（配置-目录-契约-迁移）"]["selection_reason"], "effective_primary")
            self.assertEqual(rows["辅助01-项目结构治理（配置-目录-契约-迁移）"]["candidate_count_for_channel"], 2)
            self.assertEqual(rows["辅助01-项目结构治理（配置-目录-契约-迁移）"]["agent_display_name"], "结构治理主会话")
            self.assertEqual(rows["辅助01-项目结构治理（配置-目录-契约-迁移）"]["agent_display_name_source"], "alias")
            self.assertEqual(rows["辅助01-项目结构治理（配置-目录-契约-迁移）"]["agent_name_state"], "resolved")
            self.assertEqual(rows["辅助04-原型设计与Demo可视化（静态数据填充-业务规格确认）"]["id"], newer["id"])
            self.assertEqual(rows["辅助04-原型设计与Demo可视化（静态数据填充-业务规格确认）"]["selection_reason"], "latest_last_used_at")
            self.assertEqual(rows["辅助04-原型设计与Demo可视化（静态数据填充-业务规格确认）"]["candidate_count_for_channel"], 2)
            self.assertEqual(rows["辅助04-原型设计与Demo可视化（静态数据填充-业务规格确认）"]["agent_display_name"], "原型新会话")

    def test_build_agent_candidates_payload_exposes_identity_audit_for_non_codex_missing_identity(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            run_store = server.RunStore(base / ".runtime" / "stable" / ".runs")
            session_store = server.SessionStore(base_dir=run_store.runs_dir.parent)

            created = session_store.create_session(
                "task_dashboard",
                "子级08-测试与验收（功能-回归-发布）",
                cli_type="opencode",
                session_id="ses_2f56e1533ffeoQi7mS0iK1kMkP",
            )

            payload = build_agent_candidates_payload(
                session_store=session_store,
                store=run_store,
                project_id="task_dashboard",
                environment_name="stable",
                worktree_root=base,
                apply_effective_primary_flags=lambda _store, _pid, rows: rows,
                decorate_sessions_display_fields=lambda rows: rows,
                apply_session_context_rows=lambda sessions, **kwargs: sessions,
                apply_session_work_context=lambda row, **kwargs: row,
                attach_runtime_state_to_sessions=lambda _store, sessions, project_id="": sessions,
                heartbeat_runtime=None,
                load_session_heartbeat_config=lambda _row: {},
                heartbeat_summary_payload=lambda _row: {},
            )

            audit = payload.get("agent_identity_audit") or {}
            self.assertEqual(int(audit.get("manual_backfill_required_count") or 0), 1)
            entry = (audit.get("manual_backfill_required") or [])[0]
            self.assertEqual(entry.get("session_id"), "ses_2f56e1533ffeoQi7mS0iK1kMkP")
            self.assertEqual(entry.get("action"), "needs_owner_confirmation")

    def test_list_agent_candidates_response_requires_project_id(self) -> None:
        code, payload = list_agent_candidates_response(
            query_string="",
            session_store=object(),
            store=object(),
            environment_name="stable",
            worktree_root=".",
            apply_effective_primary_flags=lambda *_args, **_kwargs: [],
            decorate_sessions_display_fields=lambda rows: rows,
            apply_session_context_rows=lambda sessions, **kwargs: sessions,
            apply_session_work_context=lambda row, **kwargs: row,
            attach_runtime_state_to_sessions=lambda _store, sessions, project_id="": sessions,
            heartbeat_runtime=None,
            load_session_heartbeat_config=lambda _row: {},
            heartbeat_summary_payload=lambda _row: {},
        )
        self.assertEqual(code, 400)
        self.assertEqual(payload["error"], "missing project_id")


if __name__ == "__main__":
    unittest.main()
