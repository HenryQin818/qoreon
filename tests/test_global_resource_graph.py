import json
import tempfile
import unittest
from pathlib import Path

import server
from task_dashboard.global_resource_graph import build_global_resource_graph
from task_dashboard.session_store import SessionStore


class GlobalResourceGraphTests(unittest.TestCase):
    def _write_md(self, path: Path, title: str, body: str = "用于测试。") -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {title}\n\n{body}\n", encoding="utf-8")

    def _prepare_cfg(self) -> dict:
        return {
            "projects": [
                {
                    "id": "task_dashboard",
                    "name": "小秘书-项目管理",
                    "task_root_rel": "任务规划",
                    "channels": [
                        {"name": "子级01-通道A", "desc": "A通道", "cli_type": "codex"},
                        {"name": "子级02-通道B", "desc": "B通道", "cli_type": "codex"},
                    ],
                }
            ]
        }

    def _prepare_cfg_with_legacy_session_ids(self) -> dict:
        cfg = self._prepare_cfg()
        channels = cfg["projects"][0]["channels"]
        channels[0]["session_id"] = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        channels[1]["session_id"] = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
        return cfg

    def test_build_graph_contains_core_nodes_and_queues(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            task_root = root / "任务规划"
            self._write_md(
                task_root / "子级01-通道A" / "任务" / "【进行中】【任务】A1-推进事项.md",
                "A1推进",
                body=(
                    "## Harness责任位\n"
                    "- 主负责位：`架构师`\n"
                    "- 协同位：`产品策划-任务派发`\n"
                    "- 验证位：空\n"
                    "- 质疑位：空\n"
                    "- 备份位：空\n"
                    "- 管理位：继承项目级默认管理位\n"
                    "- 自定义责任位：`读模型实现`\n"
                ),
            )
            self._write_md(task_root / "子级01-通道A" / "反馈" / "【待验收】【反馈】A1-回执.md", "A1回执")
            self._write_md(task_root / "子级02-通道B" / "任务" / "【待处理】【任务】B1-待处理事项.md", "B1事项")
            registry = task_root / "全局资源" / "task-harness-project-registry.task_dashboard.v1.json"
            registry.parent.mkdir(parents=True, exist_ok=True)
            registry.write_text(
                json.dumps(
                    {
                        "project_id": "task_dashboard",
                        "defaults": {"inherit_management_slot_to_tasks": True},
                        "management_slot": {
                            "default_members": [
                                {
                                    "name": "总控",
                                    "channel_name": "主体-总控（合并与验收）",
                                    "agent_alias": "总控-项目经理",
                                    "session_id": "019d107a-a5ad-7912-8797-d23c58013449",
                                    "responsibility": "项目级编排",
                                }
                            ]
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            sid_a = "11111111-1111-1111-1111-111111111111"
            sid_b = "22222222-2222-2222-2222-222222222222"
            session_store = SessionStore(base_dir=root)
            session_store.create_session(
                project_id="task_dashboard",
                channel_name="子级01-通道A",
                cli_type="codex",
                alias="A-运行会话",
                session_id=sid_a,
            )

            run_store = server.RunStore(root / ".runs")
            run_ok = run_store.create_run(
                "task_dashboard",
                "子级01-通道A",
                sid_a,
                "run ok",
                extra_meta={
                    "task_path": "任务规划/子级01-通道A/任务/【进行中】【任务】A1-推进事项.md",
                    "feedback_file_path": "任务规划/子级01-通道A/反馈/【待验收】【反馈】A1-回执.md",
                    "callback_to": {"channel_name": "子级02-通道B", "session_id": sid_b},
                },
            )
            run_ok_meta = run_store.load_meta(run_ok["id"]) or {}
            run_ok_meta["status"] = "done"
            run_ok_meta["finishedAt"] = "2026-02-23T18:00:00+0800"
            run_store.save_meta(run_ok["id"], run_ok_meta)

            run_err = run_store.create_run(
                "task_dashboard",
                "子级01-通道A",
                sid_a,
                "run error",
                extra_meta={"task_path": "任务规划/子级01-通道A/任务/【进行中】【任务】A1-推进事项.md"},
            )
            run_err_meta = run_store.load_meta(run_err["id"]) or {}
            run_err_meta["status"] = "error"
            run_err_meta["error"] = "simulated error"
            run_err_meta["finishedAt"] = "2026-02-23T18:05:00+0800"
            run_store.save_meta(run_err["id"], run_err_meta)

            assist_root = root / ".run" / "assist_requests" / "task_dashboard"
            assist_root.mkdir(parents=True, exist_ok=True)
            (assist_root / "asr-old.json").write_text(
                json.dumps(
                    {
                        "task_path": "任务规划/子级01-通道A/任务/【进行中】【任务】A1-推进事项.md",
                        "status": "resolved",
                        "support_score": 88,
                        "support_level": "sufficient",
                        "threshold_triggered": False,
                        "updated_at": "2026-02-23T17:59:00+08:00",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (assist_root / "asr-new.json").write_text(
                json.dumps(
                    {
                        "task_path": "任务规划/子级01-通道A/任务/【进行中】【任务】A1-推进事项.md",
                        "status": "pending_reply",
                        "support_score": 52,
                        "support_level": "insufficient",
                        "threshold_triggered": True,
                        "updated_at": "2026-02-23T18:06:00+08:00",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            payload = build_global_resource_graph(
                cfg=self._prepare_cfg(),
                root=root,
                session_store=session_store,
                run_store=run_store,
                project_id="task_dashboard",
                run_limit=200,
            )

            self.assertEqual(payload["version"], "v1")
            self.assertEqual(payload["stats"]["projects"], 1)
            self.assertGreaterEqual(payload["stats"]["channels"], 2)
            self.assertGreaterEqual(payload["stats"]["feedback_pending_acceptance"], 1)
            self.assertIn("org_snapshot", payload)
            snapshot = payload.get("org_snapshot") or {}
            self.assertTrue(str(snapshot.get("snapshot_id") or "").startswith("org_snapshot:"))
            self.assertIsInstance(snapshot.get("nodes"), list)
            self.assertIsInstance(snapshot.get("edges"), list)
            if snapshot.get("nodes"):
                first_node = (snapshot.get("nodes") or [])[0]
                self.assertIn("node_id", first_node)
                self.assertIn("x", first_node)
                self.assertIn("y", first_node)
            model = payload.get("unified_model") or {}
            self.assertEqual(str(model.get("model_version") or ""), "v1")
            self.assertIn("runtime", model)
            self.assertIn("structure", model)

            node_types = {str(n.get("type")) for n in payload["nodes"]}
            self.assertIn("project", node_types)
            self.assertIn("channel", node_types)
            self.assertIn("task", node_types)
            self.assertIn("feedback", node_types)
            self.assertIn("agent", node_types)
            self.assertIn("run", node_types)

            missing_feedback = payload["queues"]["missing_feedback"]
            self.assertTrue(any(str(x.get("run_id")) == str(run_err["id"]) for x in missing_feedback))

            missing_session = payload["queues"]["missing_session"]
            self.assertTrue(any(str(x.get("channel_name")) == "子级02-通道B" for x in missing_session))

            self.assertIn("task_dashboard", payload["index"]["project_channels"])
            self.assertGreaterEqual(len(payload["edges"]), 1)

            channel_a = next(
                (
                    n
                    for n in payload["nodes"]
                    if str(n.get("type")) == "channel" and str(n.get("channel_name")) == "子级01-通道A"
                ),
                {},
            )
            risk_reasons = channel_a.get("risk_reasons")
            self.assertIsInstance(risk_reasons, list)
            self.assertTrue(any(str(x.get("code")) in {"runs_error", "missing_feedback"} for x in risk_reasons if isinstance(x, dict)))

            agent_a = next(
                (
                    n
                    for n in payload["nodes"]
                    if str(n.get("type")) == "agent" and str(n.get("session_id")) == sid_a
                ),
                {},
            )
            self.assertEqual(
                str(agent_a.get("current_task_path")),
                "任务规划/子级01-通道A/任务/【进行中】【任务】A1-推进事项.md",
            )
            self.assertIn(str(agent_a.get("current_run_status")), {"done", "error"})
            self.assertTrue(str(agent_a.get("current_run_id")))
            self.assertEqual(str(agent_a.get("display_name")), "A-运行会话")
            self.assertEqual(str(agent_a.get("agent_display_name")), "A-运行会话")
            self.assertEqual(str(agent_a.get("agent_display_name_source")), "alias")
            self.assertEqual(str(agent_a.get("agent_name_state")), "resolved")
            self.assertEqual(str(agent_a.get("channel_display_name")), "子级01-通道A")
            self.assertEqual(str(agent_a.get("parent_node_id")), "channel:task_dashboard:子级01-通道A")
            self.assertIn(str(agent_a.get("agent_state")), {"active", "idle"})
            snapshot_agent_a = next(
                (
                    n
                    for n in snapshot.get("nodes") or []
                    if str(n.get("agent_id")) == sid_a
                ),
                {},
            )
            self.assertEqual(str(snapshot_agent_a.get("label")), "A-运行会话")
            self.assertEqual(str(snapshot_agent_a.get("parent_node_id")), "channel:task_dashboard:子级01-通道A")

            task_a = next(
                (
                    n
                    for n in payload["nodes"]
                    if str(n.get("type")) == "task"
                    and str(n.get("path")) == "任务规划/子级01-通道A/任务/【进行中】【任务】A1-推进事项.md"
                ),
                {},
            )
            self.assertEqual(str(task_a.get("primary_status")), "进行中")
            self.assertEqual(str(task_a.get("lifecycle_state")), "in_progress")
            self.assertEqual(bool(task_a.get("counts_as_wip")), True)
            self.assertEqual(bool((task_a.get("status_flags") or {}).get("blocked")), False)
            self.assertEqual(str(task_a.get("status_bucket")), "in_progress")
            self.assertEqual(int(task_a.get("assist_total") or 0), 2)
            self.assertEqual(int(task_a.get("assist_pending_reply_count") or 0), 1)
            self.assertEqual(int(task_a.get("assist_resolved_count") or 0), 1)
            self.assertEqual(str(task_a.get("assist_state")), "pending_reply")
            self.assertEqual(str(task_a.get("support_level")), "insufficient")
            self.assertEqual(int(task_a.get("support_score") or 0), 52)
            self.assertEqual(bool(task_a.get("threshold_triggered")), True)
            self.assertEqual(str((task_a.get("main_owner") or {}).get("agent_name") or ""), "架构师")
            self.assertEqual(len(task_a.get("collaborators") or []), 1)
            self.assertEqual(str(((task_a.get("collaborators") or [{}])[0]).get("agent_name") or ""), "产品策划-任务派发")
            self.assertEqual(len(task_a.get("management_slot") or []), 1)
            self.assertEqual(str(((task_a.get("management_slot") or [{}])[0]).get("name") or ""), "总控")
            self.assertEqual(len(task_a.get("custom_roles") or []), 1)
            self.assertEqual(str(((task_a.get("custom_roles") or [{}])[0]).get("name") or ""), "读模型实现")
            self.assertEqual(len(task_a.get("executors") or []), 1)
            self.assertEqual(str(((task_a.get("executors") or [{}])[0]).get("agent_name") or ""), "产品策划-任务派发")
            self.assertEqual(task_a.get("acceptors") or [], [])
            self.assertEqual(len(task_a.get("reviewers") or []), 1)
            self.assertEqual(str(((task_a.get("reviewers") or [{}])[0]).get("name") or ""), "总控")
            self.assertEqual(task_a.get("visual_reviewers") or [], [])
            self.assertGreaterEqual(int(payload["stats"].get("tasks_with_assist") or 0), 1)
            self.assertGreaterEqual(int(payload["stats"].get("assist_pending_reply") or 0), 1)
            self.assertGreaterEqual(int(payload["stats"].get("support_insufficient") or 0), 1)

    def test_channel_filter_excludes_other_channels(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            task_root = root / "任务规划"
            self._write_md(task_root / "子级01-通道A" / "任务" / "【进行中】【任务】A1-推进事项.md", "A1推进")
            self._write_md(task_root / "子级02-通道B" / "任务" / "【待处理】【任务】B1-待处理事项.md", "B1事项")

            session_store = SessionStore(base_dir=root)
            run_store = server.RunStore(root / ".runs")

            payload = build_global_resource_graph(
                cfg=self._prepare_cfg(),
                root=root,
                session_store=session_store,
                run_store=run_store,
                project_id="task_dashboard",
                channel_name="子级01-通道A",
            )

            channels = {
                str(n.get("channel_name"))
                for n in payload["nodes"]
                if str(n.get("type")) == "channel"
            }
            self.assertIn("子级01-通道A", channels)
            self.assertNotIn("子级02-通道B", channels)

    def test_config_channel_session_id_is_not_used_as_agent_source(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._write_md(root / "任务规划" / "子级01-通道A" / "任务" / "【进行中】【任务】A1-推进事项.md", "A1推进")

            sid_store = "11111111-1111-1111-1111-111111111111"
            session_store = SessionStore(base_dir=root)
            session_store.create_session(
                project_id="task_dashboard",
                channel_name="子级01-通道A",
                cli_type="codex",
                alias="A-运行会话",
                session_id=sid_store,
            )

            payload = build_global_resource_graph(
                cfg=self._prepare_cfg_with_legacy_session_ids(),
                root=root,
                session_store=session_store,
                run_store=server.RunStore(root / ".runs"),
                project_id="task_dashboard",
                run_limit=50,
            )

            channel_a = next(
                (
                    n
                    for n in payload["nodes"]
                    if str(n.get("type")) == "channel" and str(n.get("channel_name")) == "子级01-通道A"
                ),
                {},
            )
            self.assertEqual(str(channel_a.get("session_id")), sid_store)
            self.assertEqual(str(channel_a.get("session_source")), "session_store")
            self.assertFalse(
                any(
                    str(n.get("type")) == "agent"
                    and str(n.get("session_id")) == "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
                    for n in payload["nodes"]
                )
            )

    def test_agent_without_identity_source_does_not_fallback_to_channel_name(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._write_md(root / "任务规划" / "子级02-通道B" / "任务" / "【进行中】【任务】B1-推进事项.md", "B1推进")

            sid_b = "22222222-2222-2222-2222-222222222222"
            session_store = SessionStore(base_dir=root)
            session_store.create_session(
                project_id="task_dashboard",
                channel_name="子级02-通道B",
                cli_type="codex",
                alias="",
                session_id=sid_b,
            )

            payload = build_global_resource_graph(
                cfg=self._prepare_cfg(),
                root=root,
                session_store=session_store,
                run_store=server.RunStore(root / ".runs"),
                project_id="task_dashboard",
                run_limit=50,
            )

            agent_b = next(
                (
                    n
                    for n in payload["nodes"]
                    if str(n.get("type")) == "agent" and str(n.get("session_id")) == sid_b
                ),
                {},
            )
            self.assertEqual(str(agent_b.get("agent_display_name")), "")
            self.assertEqual(str(agent_b.get("agent_name_state")), "identity_unresolved")
            self.assertEqual(str(agent_b.get("display_name")), "身份未解析")
            self.assertNotEqual(str(agent_b.get("display_name")), "子级02-通道B")
            self.assertEqual(str(agent_b.get("parent_node_id")), "channel:task_dashboard:子级02-通道B")

            snapshot_agent_b = next(
                (
                    n
                    for n in (payload.get("org_snapshot") or {}).get("nodes") or []
                    if str(n.get("agent_id")) == sid_b
                ),
                {},
            )
            self.assertEqual(str(snapshot_agent_b.get("label")), "身份未解析")
            self.assertEqual(str(snapshot_agent_b.get("parent_node_id")), "channel:task_dashboard:子级02-通道B")

    def test_supervised_task_is_not_counted_as_in_progress(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            task_root = root / "任务规划"
            self._write_md(task_root / "子级01-通道A" / "任务" / "【督办】【任务】A1-督办事项.md", "A1督办")

            session_store = SessionStore(base_dir=root)
            run_store = server.RunStore(root / ".runs")

            payload = build_global_resource_graph(
                cfg=self._prepare_cfg(),
                root=root,
                session_store=session_store,
                run_store=run_store,
                project_id="task_dashboard",
                run_limit=50,
            )

            task_node = next(
                (
                    n
                    for n in payload["nodes"]
                    if str(n.get("type")) == "task"
                    and str(n.get("path")) == "任务规划/子级01-通道A/任务/【督办】【任务】A1-督办事项.md"
                ),
                {},
            )
            self.assertEqual(str(task_node.get("primary_status")), "待办")
            self.assertEqual(str(task_node.get("lifecycle_state")), "todo")
            self.assertFalse(bool(task_node.get("counts_as_wip")))
            self.assertEqual(bool((task_node.get("status_flags") or {}).get("supervised")), True)
            self.assertEqual(str(task_node.get("status_bucket")), "other")

            channel_link = next(
                (
                    row
                    for row in payload["links"]
                    if str(row.get("channel_name")) == "子级01-通道A"
                ),
                {},
            )
            counts = channel_link.get("counts") or {}
            self.assertEqual(int(counts.get("task_supervised") or 0), 1)
            self.assertEqual(int(counts.get("task_in_progress") or 0), 0)


if __name__ == "__main__":
    unittest.main()
