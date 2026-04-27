import tempfile
import time
import unittest
import threading
from pathlib import Path
from unittest import mock

import server


class TestProjectSchedulerSwitch(unittest.TestCase):
    def test_resolve_project_task_root_fallback_to_local_task_dashboard_dir(self) -> None:
        local_task_root = Path(server.__file__).resolve().parent / "任务规划"
        self.assertTrue(local_task_root.exists())
        with mock.patch(
            "server._find_project_cfg",
            return_value={
                "id": "task_dashboard",
                "task_root_rel": "项目管理" + "-小秘书/项目看板/task-dashboard/任务规划",
            },
        ), mock.patch("server._repo_root", return_value=Path("/tmp/non-existent-repo-root")):
            got = server._resolve_project_task_root("task_dashboard")
        self.assertEqual(got, local_task_root)

    def test_set_project_scheduler_enabled_in_config_text_inserts_block(self) -> None:
        raw = """
[[projects]]
id = "task_dashboard"
name = "Task Dashboard"

[[projects.channels]]
name = "子级02"
desc = "ccb"
""".lstrip()
        out = server._set_project_scheduler_enabled_in_config_text(raw, "task_dashboard", True)
        self.assertIn("[projects.scheduler]", out)
        self.assertIn("enabled = true", out)

    def test_set_project_scheduler_enabled_in_config_text_updates_existing_block(self) -> None:
        raw = """
[[projects]]
id = "task_dashboard"
name = "Task Dashboard"

[projects.scheduler]
enabled = false
scan_interval_seconds = 300
""".lstrip()
        out = server._set_project_scheduler_enabled_in_config_text(raw, "task_dashboard", True)
        self.assertIn("[projects.scheduler]", out)
        self.assertIn("enabled = true", out)
        self.assertEqual(out.count("enabled = true"), 1)

    def test_build_project_scheduler_status_defaults_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td) / ".runs")
            with mock.patch(
                "server._find_project_cfg",
                return_value={"id": "task_dashboard", "name": "Task Dashboard"},
            ):
                status = server._build_project_scheduler_status(store, "task_dashboard")
        self.assertEqual(status["project_id"], "task_dashboard")
        self.assertFalse(status["scheduler_enabled"])
        self.assertEqual(status["scheduler_state"], "disabled")
        self.assertFalse(status["reminder_enabled"])
        self.assertEqual(status["reminder_state"], "disabled")
        self.assertIn("reminder_records", status)
        self.assertEqual(status["reminder_records"], [])
        self.assertIn("auto_inspections", status)
        self.assertEqual(status["auto_inspections"], [])
        self.assertIn("inspection_records", status)
        self.assertEqual(status["inspection_records"], [])
        self.assertIn("auto_inspection_execution_state", status)
        self.assertEqual(status["auto_inspection_execution_state"], "pending")
        self.assertIn("auto_inspection_advice_only_streak", status)
        self.assertEqual(status["auto_inspection_advice_only_streak"], 0)
        self.assertIn("auto_inspection_escalation_level", status)
        self.assertEqual(status["auto_inspection_escalation_level"], 0)

    def test_project_scheduler_runtime_registry_sync_start_stop(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td) / ".runs")
            reg = server.ProjectSchedulerRuntimeRegistry(store=store)
            cfg_enabled = {
                "project_exists": True,
                "project_id": "task_dashboard",
                "scheduler": {
                    "enabled": True,
                    "scan_interval_seconds": 60,
                    "max_concurrency_override": None,
                    "retry_on_boot": True,
                    "errors": [],
                },
                "reminder": {
                    "enabled": False,
                    "interval_minutes": None,
                    "cron": "",
                    "in_progress_stale_after_minutes": 120,
                    "escalate_after_minutes": 480,
                    "summary_window_minutes": 5,
                    "errors": [],
                },
            }
            cfg_disabled = dict(cfg_enabled)
            cfg_disabled["scheduler"] = dict(cfg_enabled["scheduler"], enabled=False)
            try:
                with mock.patch("server._load_project_scheduler_contract_config", return_value=cfg_enabled):
                    status = reg.sync_project("task_dashboard")
                self.assertTrue(status["scheduler_enabled"])
                self.assertEqual(status["scheduler_state"], "idle")
                self.assertTrue(status.get("worker_running"))

                with mock.patch("server._load_project_scheduler_contract_config", return_value=cfg_disabled):
                    status2 = reg.sync_project("task_dashboard")
                self.assertFalse(status2["scheduler_enabled"])
                self.assertEqual(status2["scheduler_state"], "disabled")
            finally:
                reg.shutdown()

    def test_project_scheduler_runtime_registry_sync_project_no_change_no_deadlock(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td) / ".runs")
            reg = server.ProjectSchedulerRuntimeRegistry(store=store)
            cfg_enabled = {
                "project_exists": True,
                "project_id": "task_dashboard",
                "scheduler": {
                    "enabled": True,
                    "scan_interval_seconds": 60,
                    "max_concurrency_override": None,
                    "retry_on_boot": True,
                    "errors": [],
                },
                "reminder": {
                    "enabled": False,
                    "interval_minutes": None,
                    "cron": "",
                    "in_progress_stale_after_minutes": 120,
                    "escalate_after_minutes": 480,
                    "summary_window_minutes": 5,
                    "errors": [],
                },
            }
            try:
                with mock.patch("server._load_project_scheduler_contract_config", return_value=cfg_enabled):
                    reg.sync_project("task_dashboard")

                result = {}
                done = threading.Event()

                def runner() -> None:
                    try:
                        with mock.patch("server._load_project_scheduler_contract_config", return_value=cfg_enabled):
                            result["status"] = reg.sync_project("task_dashboard")
                    finally:
                        done.set()

                t = threading.Thread(target=runner, daemon=True)
                t.start()
                self.assertTrue(done.wait(1.0), "sync_project should not deadlock on unchanged enabled worker")
                status = result.get("status") or {}
                self.assertTrue(status.get("scheduler_enabled"))
            finally:
                reg.shutdown()

    def test_run_project_scheduler_once_bridge_uses_project_scoped_state_paths(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td) / ".runs")
            task_root = Path(td) / "任务规划"
            task_root.mkdir(parents=True, exist_ok=True)

            called = {}

            def fake_run_once(**kwargs):
                called.update(kwargs)
                return {"ok": True}

            with mock.patch("server._resolve_project_task_root", return_value=task_root), mock.patch(
                "task_dashboard.inspection_scheduler.run_once",
                side_effect=fake_run_once,
            ):
                out = server._run_project_scheduler_once_bridge(store, "task_dashboard")

            self.assertTrue(out.get("ok"))
            self.assertEqual(called["task_root"], task_root)
            self.assertEqual(called["runs_dir"], store.runs_dir)
            self.assertIn(".run/project_scheduler/task_dashboard", str(called["watermark_path"]))

    def test_build_project_scheduler_status_includes_reminder_records(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td) / ".runs")
            server._save_project_scheduler_runtime_snapshot(
                store,
                "task_dashboard",
                {
                    "reminder_records": [
                        {
                            "created_at": "2026-03-01T10:00:00+0800",
                            "status": "skipped_active",
                            "message_summary": "主办通道活跃，跳过本轮",
                            "target_task_path": "任务规划/子级02/任务/【进行中】【任务】x.md",
                            "target_channel": "子级02-CCB运行时（server-并发-安全-启动）",
                            "run_id": "",
                            "skip_reason": "owner_channel_active",
                        }
                    ]
                },
            )
            with mock.patch(
                "server._find_project_cfg",
                return_value={"id": "task_dashboard", "name": "Task Dashboard"},
            ):
                status = server._build_project_scheduler_status(store, "task_dashboard")
        self.assertIn("reminder_records", status)
        self.assertEqual(len(status["reminder_records"]), 1)
        row = status["reminder_records"][0]
        self.assertEqual(row["status"], "skipped_active")
        self.assertEqual(row["skip_reason"], "owner_channel_active")
        inspection_rows = status.get("inspection_records") or []
        self.assertEqual(len(inspection_rows), 1)
        self.assertEqual(inspection_rows[0]["summary"], "主办通道活跃，跳过本轮")
        self.assertIn("record_id", inspection_rows[0])

    def test_collect_auto_inspection_candidates_uses_status_targets_only(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            task_root = base / "任务规划"
            todo_dir = task_root / "子级04-前端体验（task-overview 页面交互）" / "任务"
            todo_dir.mkdir(parents=True, exist_ok=True)
            todo_path = todo_dir / "【待开始】【任务】P0-待开始候选验证.md"
            todo_path.write_text("# test\n", encoding="utf-8")
            pending_dir = task_root / "子级05-任务巡检与留痕（自动化）" / "任务"
            pending_dir.mkdir(parents=True, exist_ok=True)
            pending_path = pending_dir / "【待处理】【任务】P0-待处理候选验证.md"
            pending_path.write_text("# test\n", encoding="utf-8")
            store = server.RunStore(base / ".runs")
            fake_cfg = {"projects": [{"id": "task_dashboard", "task_root_rel": str(task_root)}]}

            with mock.patch("server._load_dashboard_cfg_current", return_value=fake_cfg), mock.patch(
                "server._resolve_project_task_root",
                return_value=task_root,
            ):
                out = server._collect_auto_inspection_candidates(
                    store,
                    "task_dashboard",
                    ["todo", "pending"],
                    limit=2,
                )
            rows = out.get("candidates") or []
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["target_source"], "todo")
            self.assertEqual(rows[1]["target_source"], "pending")

    def test_load_project_auto_inspection_config_prefers_auto_inspections_targets(self) -> None:
        with mock.patch(
            "server._find_project_cfg",
            return_value={
                "id": "task_dashboard",
                "auto_inspection": {
                    "enabled": True,
                    "channel_name": "辅助05-督办PMO（排期-巡查-催办-升级）",
                    "session_id": "019c8953-4c6a-7891-bd39-876543210abc",
                    "prompt_template": "巡查",
                    "inspection_targets": ["todo", "pending"],
                    "auto_inspections": [
                        {
                            "object_key": "ins-in_progress",
                            "object_type": "in_progress",
                            "display_name": "进行中任务",
                            "enabled": True,
                        },
                        {
                            "object_key": "ins-pending",
                            "object_type": "pending",
                            "display_name": "待处理任务",
                            "enabled": False,
                        },
                    ],
                },
            },
        ):
            cfg = server._load_project_auto_inspection_config("task_dashboard")
        self.assertEqual(cfg.get("inspection_targets"), ["in_progress"])
        objects = cfg.get("auto_inspections") or []
        self.assertEqual(len(objects), 2)
        self.assertTrue(cfg.get("ready"))

    def test_load_project_auto_inspection_config_migrates_legacy_to_default_task(self) -> None:
        with mock.patch(
            "server._find_project_cfg",
            return_value={
                "id": "task_dashboard",
                "auto_inspection": {
                    "enabled": True,
                    "channel_name": "辅助05-督办PMO（排期-巡查-催办-升级）",
                    "session_id": "019c8953-4c6a-7891-bd39-876543210abc",
                    "prompt_template": "巡查",
                    "inspection_targets": ["todo"],
                },
            },
        ):
            cfg = server._load_project_auto_inspection_config("task_dashboard")
        tasks = cfg.get("inspection_tasks") or []
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].get("inspection_task_id"), "default")
        self.assertEqual(cfg.get("active_inspection_task_id"), "default")

    def test_load_project_auto_inspection_config_respects_explicit_empty_tasks(self) -> None:
        with mock.patch(
            "server._find_project_cfg",
            return_value={
                "id": "task_dashboard",
                "auto_inspection": {
                    "enabled": True,
                    "inspection_tasks": [],
                },
            },
        ):
            cfg = server._load_project_auto_inspection_config("task_dashboard")
        self.assertEqual(cfg.get("inspection_tasks"), [])
        self.assertFalse(cfg.get("ready"))
        self.assertIn("auto_inspection.inspection_tasks_missing", cfg.get("errors") or [])

    def test_build_project_scheduler_status_selected_tasks_normalized_single(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td) / ".runs")
            server._save_project_scheduler_runtime_snapshot(
                store,
                "task_dashboard",
                {
                    "auto_inspection_last_selected_tasks": [
                        "任务规划/子级02/任务/【进行中】【任务】a.md",
                        "任务规划/子级03/任务/【进行中】【任务】b.md",
                    ]
                },
            )
            with mock.patch(
                "server._find_project_cfg",
                return_value={"id": "task_dashboard", "name": "Task Dashboard"},
            ):
                status = server._build_project_scheduler_status(store, "task_dashboard")
        selected = status.get("auto_inspection_last_selected_tasks") or []
        self.assertEqual(len(selected), 1)

    def test_attach_auto_inspection_candidate_preview(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            store = server.RunStore(base / ".runs")
            task_root = base / "任务规划"
            task_dir = task_root / "子级04-前端体验（task-overview 页面交互）" / "任务"
            task_dir.mkdir(parents=True, exist_ok=True)
            task_path = task_dir / "【待开始】【任务】P0-候选预览验证.md"
            task_path.write_text("# test\n", encoding="utf-8")
            fake_cfg = {"projects": [{"id": "task_dashboard", "task_root_rel": str(task_root)}]}
            with mock.patch(
                "server._load_project_scheduler_contract_config",
                return_value={
                    "project_exists": True,
                    "project_id": "task_dashboard",
                    "scheduler": {"enabled": True, "errors": []},
                    "reminder": {"enabled": False, "errors": []},
                },
            ), mock.patch(
                "server._load_project_auto_inspection_config",
                return_value={
                    "enabled": True,
                    "ready": True,
                    "inspection_targets": ["todo"],
                    "errors": [],
                },
            ), mock.patch(
                "server._load_project_auto_dispatch_config",
                return_value={"enabled": False},
            ), mock.patch(
                "server._resolve_project_task_root",
                return_value=task_root,
            ), mock.patch(
                "server._load_dashboard_cfg_current",
                return_value=fake_cfg,
            ):
                status = server._build_project_scheduler_status(store, "task_dashboard")
                status = server._attach_auto_inspection_candidate_preview(store, status)

        self.assertGreaterEqual(int(status.get("auto_inspection_candidate_count_preview") or 0), 1)

    def test_promote_auto_inspection_task_to_in_progress_updates_task_only(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            store = server.RunStore(base / ".runs")
            task_root = base / "任务规划"
            task_dir = task_root / "子级04-前端体验（task-overview 页面交互）" / "任务"
            task_dir.mkdir(parents=True, exist_ok=True)
            old_file = task_dir / "【待处理】【任务】P0-待处理自动转进行中.md"
            old_file.write_text("# test\n", encoding="utf-8")

            with mock.patch("server._repo_root", return_value=base), mock.patch(
                "server._resolve_project_task_root",
                return_value=task_root,
            ):
                out = server._promote_auto_inspection_task_to_in_progress(
                    store,
                    "task_dashboard",
                    str(old_file),
                )

            self.assertTrue(bool(out.get("changed")))
            self.assertEqual(str(out.get("new_status") or ""), "进行中")
            self.assertFalse(bool(out.get("queue_updated")))
            new_path = str(out.get("new_task_path") or "")
            self.assertIn("【进行中】", new_path)
            new_file = Path(new_path)
            if not new_file.is_absolute():
                new_file = base / new_file
            self.assertTrue(new_file.exists())

    def test_tick_auto_inspection_first_task_only_and_record_dispatched(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td) / ".runs")
            session_store = server.SessionStore(base_dir=Path(td))
            reg = server.ProjectSchedulerRuntimeRegistry(store=store, session_store=session_store)
            reg.set_scheduler(object())  # non-None marker, enqueue path mocked
            reg._workers["task_dashboard"] = {
                "running": True,
                "auto_inspection_next_due_at": "1970-01-01T00:00:00+0000",
            }
            candidates = [
                {
                    "task_path": "任务规划/子级04/任务/【进行中】【任务】A.md",
                    "title": "任务A",
                    "channel_name": "子级04-前端体验（task-overview 页面交互）",
                    "target_source": "todo",
                },
                {
                    "task_path": "任务规划/子级05/任务/【待处理】【任务】B.md",
                    "title": "任务B",
                    "channel_name": "子级05-任务巡检与留痕（自动化）",
                    "target_source": "in_progress",
                },
            ]
            cfg = {
                "enabled": True,
                "ready": True,
                "channel_name": "辅助01-项目结构治理（配置-目录-契约-迁移）",
                "session_id": "019c857a-3412-7e71-914b-b0c18d50f603",
                "prompt_template": "巡查提示词",
                "interval_minutes": 15,
                "inspection_targets": ["todo", "in_progress"],
                "inspection_tasks": [
                    {
                        "inspection_task_id": "board-a",
                        "title": "板块A",
                        "enabled": True,
                        "channel_name": "辅助01-项目结构治理（配置-目录-契约-迁移）",
                        "session_id": "019c857a-3412-7e71-914b-b0c18d50f603",
                        "prompt_template": "巡查提示词",
                        "interval_minutes": 15,
                        "inspection_targets": ["todo", "in_progress"],
                        "auto_inspections": [],
                        "ready": True,
                        "errors": [],
                    }
                ],
                "active_inspection_task_id": "board-a",
            }
            with mock.patch("server._load_project_auto_inspection_config", return_value=cfg), mock.patch(
                "server._collect_auto_inspection_candidates",
                return_value={"candidates": candidates, "summary": {"selected_count": 2}},
            ), mock.patch(
                "server._resolve_channel_primary_session_id",
                return_value="019c558e-8996-79d0-bdb0-1739867534ec",
            ), mock.patch(
                "server._task_push_active_state",
                return_value={"active": False, "status": "", "run_id": ""},
            ), mock.patch(
                "server._resolve_cli_type_for_session",
                return_value="codex",
            ), mock.patch(
                "server._enqueue_run_execution",
                return_value=None,
            ):
                reg._tick_auto_inspection_once("task_dashboard")

            status = reg.get_status("task_dashboard")
            selected = status.get("auto_inspection_last_selected_tasks") or []
            self.assertEqual(selected, [server._normalize_task_path_identity(candidates[0]["task_path"])])
            recs = status.get("reminder_records") or []
            self.assertTrue(recs)
            self.assertEqual(recs[0]["status"], "dispatched")
            self.assertEqual(recs[0]["inspection_task_id"], "board-a")
            self.assertEqual(recs[0]["target_task_path"], server._normalize_task_path_identity(candidates[0]["task_path"]))
            self.assertEqual(recs[0]["target_channel"], candidates[0]["channel_name"])
            self.assertTrue(str(recs[0]["run_id"]))
            inspections = status.get("inspection_records") or []
            self.assertTrue(inspections)
            self.assertEqual(inspections[0]["inspection_task_id"], "board-a")

    def test_tick_auto_inspection_skipped_active_record(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td) / ".runs")
            session_store = server.SessionStore(base_dir=Path(td))
            reg = server.ProjectSchedulerRuntimeRegistry(store=store, session_store=session_store)
            reg.set_scheduler(object())
            reg._workers["task_dashboard"] = {
                "running": True,
                "auto_inspection_next_due_at": "1970-01-01T00:00:00+0000",
            }
            candidates = [
                {
                    "task_path": "任务规划/子级02/任务/【进行中】【任务】C.md",
                    "title": "任务C",
                    "channel_name": "子级02-CCB运行时（server-并发-安全-启动）",
                    "target_source": "todo",
                }
            ]
            cfg = {
                "enabled": True,
                "ready": True,
                "channel_name": "辅助01-项目结构治理（配置-目录-契约-迁移）",
                "session_id": "019c857a-3412-7e71-914b-b0c18d50f603",
                "prompt_template": "巡查提示词",
                "interval_minutes": 15,
                "inspection_targets": ["todo"],
            }
            with mock.patch("server._load_project_auto_inspection_config", return_value=cfg), mock.patch(
                "server._collect_auto_inspection_candidates",
                return_value={"candidates": candidates, "summary": {"selected_count": 1}},
            ), mock.patch(
                "server._resolve_channel_primary_session_id",
                return_value="019c558e-8996-79d0-bdb0-1739867534ec",
            ), mock.patch(
                "server._task_push_active_state",
                return_value={"active": True, "status": "running", "run_id": "r-active"},
            ), mock.patch.object(store, "create_run", wraps=store.create_run) as create_run_mock:
                reg._tick_auto_inspection_once("task_dashboard")
                self.assertFalse(create_run_mock.called)

            status = reg.get_status("task_dashboard")
            recs = status.get("reminder_records") or []
            self.assertTrue(recs)
            self.assertEqual(recs[0]["status"], "skipped_active")
            self.assertEqual(recs[0]["skip_reason"], "owner_channel_active")
            self.assertEqual(recs[0]["target_task_path"], server._normalize_task_path_identity(candidates[0]["task_path"]))
            self.assertEqual(recs[0]["run_id"], "")

    def test_auto_inspection_prompt_execute_first(self) -> None:
        txt = server._build_auto_inspection_prompt(
            "请巡查",
            candidates=[{"task_path": "任务规划/x.md", "title": "任务X", "status_bucket": "进行中", "channel_name": "子级02"}],
            summary={"selected_count": 1},
        )
        self.assertEqual(txt, "请巡查")
        self.assertNotIn("本轮只看第1个候选任务", txt)
        self.assertNotIn("任务规划/x.md", txt)
        self.assertNotIn("【执行提示】", txt)
        self.assertNotIn("【筛选摘要】", txt)
        self.assertNotIn("请先回复：本轮推进顺序", txt)

    def test_auto_inspection_prompt_trim_duplicated_tail_sections(self) -> None:
        base = (
            "请执行自动巡查\\n"
            "核心目标：先推进\\n"
            "【对话方式】发送消息时使用 agent 主体标签：\\n"
            "- 首行...\\n"
            "【发送动作】需要发消息时调用 task_push.send_now\\n"
            "【输出格式】单个JSON对象...\\n"
            "请在本轮给出当前状态、阻塞点、下一步计划。"
        )
        txt = server._build_auto_inspection_prompt(
            base,
            candidates=[{"task_path": "任务规划/x.md", "title": "任务X", "status_bucket": "进行中", "channel_name": "子级02"}],
            summary={"selected_count": 1},
        )
        self.assertIn("核心目标：先推进", txt)
        self.assertNotIn("【对话方式】发送消息时使用 agent 主体标签", txt)
        self.assertNotIn("【输出格式】单个JSON对象", txt)
        self.assertNotIn("请在本轮给出当前状态、阻塞点、下一步计划。", txt)
        self.assertNotIn("固定督办句（仅此一处）", txt)
        self.assertNotIn("【发送动作】task_push.send_now", txt)
        self.assertNotIn("【筛选摘要】", txt)
        self.assertNotIn("【执行提示】", txt)

    def test_classify_auto_inspection_execution_result(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td) / ".runs")
            run1 = store.create_run("task_dashboard", "子级02", "019c558e-8996-79d0-bdb0-1739867534ec", "msg")
            run1_id = str(run1.get("id") or "")
            meta1 = store.load_meta(run1_id) or {}
            meta1["status"] = "done"
            store.save_meta(run1_id, meta1)
            store._paths(run1_id)["last"].write_text("建议你下一步推进并补充同步。", encoding="utf-8")
            out1 = server._classify_auto_inspection_execution_result(store, run1_id)
            self.assertEqual(out1["state"], "advice_only")

            run2 = store.create_run("task_dashboard", "子级02", "019c558e-8996-79d0-bdb0-1739867534ec", "msg")
            run2_id = str(run2.get("id") or "")
            meta2 = store.load_meta(run2_id) or {}
            meta2["status"] = "done"
            store.save_meta(run2_id, meta2)
            store._paths(run2_id)["last"].write_text("已执行并提交，run_id=20260301-120000-deadbeef", encoding="utf-8")
            out2 = server._classify_auto_inspection_execution_result(store, run2_id)
            self.assertEqual(out2["state"], "effective")

            run3 = store.create_run("task_dashboard", "子级02", "019c558e-8996-79d0-bdb0-1739867534ec", "msg")
            run3_id = str(run3.get("id") or "")
            meta3 = store.load_meta(run3_id) or {}
            meta3["status"] = "done"
            store.save_meta(run3_id, meta3)
            store._paths(run3_id)["log"].write_text("执行证据: job_id=job-1", encoding="utf-8")
            out3 = server._classify_auto_inspection_execution_result(store, run3_id)
            self.assertEqual(out3["state"], "effective")

            run4 = store.create_run("task_dashboard", "子级02", "019c558e-8996-79d0-bdb0-1739867534ec", "msg")
            run4_id = str(run4.get("id") or "")
            meta4 = store.load_meta(run4_id) or {}
            meta4["status"] = "done"
            store.save_meta(run4_id, meta4)
            store._paths(run4_id)["last"].write_text(
                "{"
                '"task_id":"任务规划/x.md",'
                '"current_state":"in_progress",'
                '"action_decision":"remind",'
                '"next_action_message":"已发督办消息",'
                '"next_followup":"下一轮复核反馈",'
                '"evidence_paths":["run_id=20260302-010101-abcdef12"]'
                "}",
                encoding="utf-8",
            )
            out4 = server._classify_auto_inspection_execution_result(store, run4_id)
            self.assertEqual(out4["state"], "effective")

    def test_dispatch_auto_inspection_gate_followup_has_run_id_without_scheduler(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td) / ".runs")
            reg = server.ProjectSchedulerRuntimeRegistry(store=store, session_store=None)
            reg.set_scheduler(None)
            with mock.patch("server._enqueue_run_execution", return_value=None):
                rid = reg._dispatch_auto_inspection_gate_followup(
                    project_id="task_dashboard",
                    target_channel="主体-总控（合并与验收）",
                    target_session_id="019c7906-cd4b-7e81-89d9-7b851b5d81ea",
                    message="gate followup",
                    source_run_id="20260301-000000-deadbeef",
                    action="escalate_master",
                )
            self.assertTrue(rid)
            meta = store.load_meta(rid) or {}
            self.assertEqual(str(meta.get("sender_id") or ""), "auto_inspection_gate")

    def test_auto_inspection_gate_escalation_on_consecutive_advice_only(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td) / ".runs")
            session_store = server.SessionStore(base_dir=Path(td))
            reg = server.ProjectSchedulerRuntimeRegistry(store=store, session_store=session_store)
            reg.set_scheduler(object())
            reg._workers["task_dashboard"] = {"running": True}
            cfg = {
                "channel_name": "子级02-CCB运行时（server-并发-安全-启动）",
                "session_id": "019c558e-8996-79d0-bdb0-1739867534ec",
            }

            def mk_done_run(last_text: str) -> str:
                row = store.create_run("task_dashboard", "子级02", "019c558e-8996-79d0-bdb0-1739867534ec", "msg")
                rid = str(row.get("id") or "")
                meta = store.load_meta(rid) or {}
                meta["status"] = "done"
                store.save_meta(rid, meta)
                store._paths(rid)["last"].write_text(last_text, encoding="utf-8")
                return rid

            # 第1轮 advice_only：只计数，不升级
            rid1 = mk_done_run("建议先推进下一步。")
            reg._set_worker_fields("task_dashboard", auto_inspection_last_run_id=rid1)
            with mock.patch.object(reg, "_dispatch_auto_inspection_gate_followup", return_value="") as followup1:
                reg._evaluate_previous_auto_inspection_gate("task_dashboard", cfg)
                self.assertFalse(followup1.called)
            s1 = reg.get_status("task_dashboard")
            self.assertEqual(int(s1.get("auto_inspection_advice_only_streak") or 0), 1)
            self.assertEqual(str(s1.get("auto_inspection_execution_state") or ""), "advice_only")

            # 第2轮 advice_only：触发L1补执行催办
            rid2 = mk_done_run("建议继续推进。")
            reg._set_worker_fields("task_dashboard", auto_inspection_last_run_id=rid2)
            with mock.patch.object(reg, "_dispatch_auto_inspection_gate_followup", return_value="gate-l1-run") as followup2:
                reg._evaluate_previous_auto_inspection_gate("task_dashboard", cfg)
                self.assertTrue(followup2.called)
            s2 = reg.get_status("task_dashboard")
            self.assertEqual(int(s2.get("auto_inspection_advice_only_streak") or 0), 2)
            self.assertEqual(int(s2.get("auto_inspection_escalation_level") or 0), 1)
            self.assertEqual(str(s2.get("auto_inspection_gate_action") or ""), "remedy_execute")
            self.assertEqual(str(s2.get("auto_inspection_gate_action_run_id") or ""), "gate-l1-run")

            # 第3轮 advice_only：触发L2升级总控
            rid3 = mk_done_run("建议拆解后处理。")
            reg._set_worker_fields("task_dashboard", auto_inspection_last_run_id=rid3)
            with mock.patch.object(reg, "_dispatch_auto_inspection_gate_followup", return_value="gate-l2-run") as followup3, mock.patch(
                "server._resolve_master_control_target",
                return_value={"channel_name": "主体-总控（合并与验收）", "session_id": "019c7906-cd4b-7e81-89d9-7b851b5d81ea"},
            ):
                reg._evaluate_previous_auto_inspection_gate("task_dashboard", cfg)
                self.assertTrue(followup3.called)
            s3 = reg.get_status("task_dashboard")
            self.assertEqual(int(s3.get("auto_inspection_advice_only_streak") or 0), 3)
            self.assertEqual(int(s3.get("auto_inspection_escalation_level") or 0), 2)
            self.assertEqual(str(s3.get("auto_inspection_gate_action") or ""), "escalate_master")
            self.assertEqual(str(s3.get("auto_inspection_gate_action_run_id") or ""), "gate-l2-run")


if __name__ == "__main__":
    unittest.main()
