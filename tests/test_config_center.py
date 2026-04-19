import os
import tomllib
import unittest
from types import SimpleNamespace
from unittest import mock

import server
from task_dashboard.local_cli_bins import set_runtime_cli_bins_in_config_text


class TestConfigCenterHelpers(unittest.TestCase):
    def test_set_runtime_max_concurrency_in_config_text_insert(self) -> None:
        raw = "version = 1\n\n[dashboard]\ntitle = \"x\"\n"
        out = server._set_runtime_max_concurrency_in_config_text(raw, 12)
        self.assertIn("[runtime]", out)
        self.assertIn("max_concurrency = 12", out)

    def test_set_runtime_max_concurrency_in_config_text_update(self) -> None:
        raw = "version = 1\n[runtime]\nmax_concurrency = 8\n\n[dashboard]\ntitle = \"x\"\n"
        out = server._set_runtime_max_concurrency_in_config_text(raw, 16)
        self.assertIn("max_concurrency = 16", out)
        self.assertEqual(out.count("max_concurrency ="), 1)

    def test_set_project_scheduler_contract_in_config_text(self) -> None:
        raw = """
[[projects]]
id = "task_dashboard"
name = "Task Dashboard"

[projects.scheduler]
enabled = false
scan_interval_seconds = 300
max_concurrency_override = 2

[projects.reminder]
enabled = false
interval_minutes = 20
cron = "*/20 * * * *"
summary_window_minutes = 5

[[projects]]
id = "other"
name = "Other"
""".lstrip()
        out = server._set_project_scheduler_contract_in_config_text(
            raw,
            "task_dashboard",
            scheduler_patch={
                "enabled": True,
                "scan_interval_seconds": 180,
                "max_concurrency_override": None,
            },
            reminder_patch={
                "enabled": True,
                "interval_minutes": 30,
                "cron": None,
                "summary_window_minutes": 10,
            },
        )
        self.assertIn("enabled = true", out)
        self.assertIn("scan_interval_seconds = 180", out)
        self.assertIn("interval_minutes = 30", out)
        self.assertIn("summary_window_minutes = 10", out)
        self.assertNotIn("max_concurrency_override = 2", out)
        self.assertNotIn("cron = \"*/20 * * * *\"", out)
        self.assertIn("id = \"other\"", out)

    def test_set_project_scheduler_contract_supports_auto_inspection_targets_list(self) -> None:
        raw = """
[[projects]]
id = "task_dashboard"
name = "Task Dashboard"

[projects.auto_inspection]
enabled = true
prompt_template = "巡查"
""".lstrip()
        out = server._set_project_scheduler_contract_in_config_text(
            raw,
            "task_dashboard",
            auto_inspection_patch={
                "inspection_targets": ["todo", "in_progress", "pending"],
            },
        )
        self.assertIn("[projects.auto_inspection]", out)
        self.assertIn('inspection_targets = ["todo", "in_progress", "pending"]', out)

    def test_set_project_scheduler_contract_supports_auto_inspections_objects(self) -> None:
        raw = """
[[projects]]
id = "task_dashboard"
name = "Task Dashboard"

[projects.auto_inspection]
enabled = true
prompt_template = "巡查"
""".lstrip()
        out = server._set_project_scheduler_contract_in_config_text(
            raw,
            "task_dashboard",
            auto_inspection_patch={
                "auto_inspections": [
                    {
                        "object_key": "ins-in_progress",
                        "object_type": "in_progress",
                        "display_name": "进行中任务",
                        "enabled": True,
                        "source": "auto_inspections",
                        "match_values": [],
                    }
                ],
            },
        )
        parsed = tomllib.loads(out)
        projects = parsed.get("projects") or []
        p0 = projects[0] if projects else {}
        ai = p0.get("auto_inspection") if isinstance(p0, dict) else {}
        self.assertTrue(isinstance(ai, dict))
        objs = (ai or {}).get("auto_inspections") or []
        self.assertEqual(len(objs), 1)
        self.assertEqual(objs[0].get("object_key"), "ins-in_progress")

    def test_set_runtime_cli_bins_in_config_text_insert(self) -> None:
        raw = "version = 1\n\n[dashboard]\ntitle = \"x\"\n"
        out = set_runtime_cli_bins_in_config_text(raw, {"codex": "/usr/local/bin/codex", "trae": "/usr/local/bin/trae-cli"})
        parsed = tomllib.loads(out)
        runtime = parsed.get("runtime") or {}
        cli_bins = runtime.get("cli_bins") if isinstance(runtime, dict) else {}
        self.assertEqual((cli_bins or {}).get("codex"), "/usr/local/bin/codex")
        self.assertEqual((cli_bins or {}).get("trae_cli"), "/usr/local/bin/trae-cli")

    def test_set_runtime_cli_bins_in_config_text_remove_section_when_cleared(self) -> None:
        raw = """
[runtime.cli_bins]
codex = "/usr/local/bin/codex"
claude = "/usr/local/bin/claude"

[dashboard]
title = "x"
""".lstrip()
        out = set_runtime_cli_bins_in_config_text(raw, {})
        self.assertNotIn("[runtime.cli_bins]", out)
        self.assertIn("[dashboard]", out)

    def test_set_project_scheduler_contract_supports_session_health(self) -> None:
        raw = """
[[projects]]
id = "task_dashboard"
name = "Task Dashboard"
""".lstrip()
        out = server._set_project_scheduler_contract_in_config_text(
            raw,
            "task_dashboard",
            session_health_patch={
                "enabled": True,
                "interval_minutes": 180,
            },
        )
        parsed = tomllib.loads(out)
        projects = parsed.get("projects") or []
        p0 = projects[0] if projects else {}
        sh = p0.get("session_health") if isinstance(p0, dict) else {}
        self.assertTrue(isinstance(sh, dict))
        self.assertTrue(bool(sh.get("enabled")))
        self.assertEqual(sh.get("interval_minutes"), 180)

    def test_set_project_scheduler_contract_supports_execution_context(self) -> None:
        raw = """
[[projects]]
id = "task_dashboard"
name = "Task Dashboard"
""".lstrip()
        out = server._set_project_scheduler_contract_in_config_text(
            raw,
            "task_dashboard",
            execution_context_patch={
                "profile": "project_privileged_full",
                "environment": "refactor",
                "worktree_root": "/tmp/task-dashboard-refactor",
                "workdir": "/tmp/task-dashboard-refactor/runtime",
                "branch": "refactor/project-context",
            },
        )
        parsed = tomllib.loads(out)
        projects = parsed.get("projects") or []
        p0 = projects[0] if projects else {}
        ec = p0.get("execution_context") if isinstance(p0, dict) else {}
        self.assertTrue(isinstance(ec, dict))
        self.assertEqual(ec.get("profile"), "project_privileged_full")
        self.assertEqual(ec.get("environment"), "refactor")
        self.assertEqual(ec.get("worktree_root"), "/tmp/task-dashboard-refactor")
        self.assertEqual(ec.get("workdir"), "/tmp/task-dashboard-refactor/runtime")
        self.assertEqual(ec.get("branch"), "refactor/project-context")

    def test_set_project_scheduler_contract_supports_extended_execution_context(self) -> None:
        raw = """
[[projects]]
id = "task_dashboard"
name = "Task Dashboard"
""".lstrip()
        out = server._set_project_scheduler_contract_in_config_text(
            raw,
            "task_dashboard",
            execution_context_patch={
                "environment": "stable",
                "worktree_root": "/tmp/task-dashboard",
                "workdir": "/tmp/task-dashboard",
                "branch": "main",
                "runtime_root": "/tmp/task-dashboard/.runtime/stable",
                "sessions_root": "/tmp/task-dashboard/.runtime/stable/.sessions",
                "runs_root": "/tmp/task-dashboard/.runtime/stable/.runs",
                "server_port": "18765",
                "health_source": "/__health",
            },
        )
        parsed = tomllib.loads(out)
        projects = parsed.get("projects") or []
        p0 = projects[0] if projects else {}
        ec = p0.get("execution_context") if isinstance(p0, dict) else {}
        self.assertEqual(ec.get("runtime_root"), "/tmp/task-dashboard/.runtime/stable")
        self.assertEqual(ec.get("sessions_root"), "/tmp/task-dashboard/.runtime/stable/.sessions")
        self.assertEqual(ec.get("runs_root"), "/tmp/task-dashboard/.runtime/stable/.runs")
        self.assertEqual(ec.get("server_port"), "18765")
        self.assertEqual(ec.get("health_source"), "/__health")

    def test_get_project_config_response_includes_extended_execution_context(self) -> None:
        code, payload = server.get_project_config_response(
            project_id="task_dashboard",
            store=SimpleNamespace(),
            find_project_cfg=lambda pid: {
                "id": pid,
                "execution_context": {
                    "profile": "project_privileged_full",
                    "environment": "stable",
                    "worktree_root": "/tmp/task-dashboard",
                    "workdir": "/tmp/task-dashboard",
                    "branch": "main",
                    "runtime_root": "/tmp/task-dashboard/.runtime/stable",
                    "sessions_root": "/tmp/task-dashboard/.runtime/stable/.sessions",
                    "runs_root": "/tmp/task-dashboard/.runtime/stable/.runs",
                    "server_port": "18765",
                    "health_source": "/__health",
                },
            },
            load_project_scheduler_contract_config=lambda pid: {},
            load_project_auto_dispatch_config=lambda pid: {"enabled": False},
            load_project_auto_inspection_config=lambda pid: {"enabled": False},
            load_project_heartbeat_config=lambda pid: {"enabled": False, "tasks": []},
            build_project_scheduler_status=lambda store, pid: {"project_id": pid},
            ensure_auto_scheduler_status_shape=lambda status: status,
            project_scheduler_runtime=None,
            heartbeat_runtime=None,
            normalize_inspection_targets=lambda raw, default=None: list(default or []),
            normalize_auto_inspections=lambda raw, fallback_targets=None: [],
            normalize_auto_inspection_tasks=lambda raw, has_explicit_field=False: [],
            normalize_heartbeat_tasks=lambda raw: [],
            default_inspection_targets=[],
            config_path_getter=lambda: "/tmp/config.toml",
        )
        self.assertEqual(code, 200)
        ec = (((payload.get("project") or {}).get("execution_context")) or {})
        self.assertEqual(ec.get("profile"), "project_privileged_full")
        self.assertEqual(ec.get("runtime_root"), "/tmp/task-dashboard/.runtime/stable")
        self.assertEqual(ec.get("sessions_root"), "/tmp/task-dashboard/.runtime/stable/.sessions")
        self.assertEqual(ec.get("runs_root"), "/tmp/task-dashboard/.runtime/stable/.runs")
        self.assertEqual(ec.get("server_port"), "18765")
        self.assertEqual(ec.get("health_source"), "/__health")
        self.assertEqual((ec.get("permissions") or {}).get("profile"), "project_privileged_full")
        profiles = ec.get("available_profiles") or []
        self.assertIn("project_privileged_full", [row.get("profile") for row in profiles if isinstance(row, dict)])

    def test_update_project_session_health_config_returns_payload(self) -> None:
        fake_server = SimpleNamespace(session_health_runtime=None)
        with mock.patch.object(server, "_SERVER_HOLDER", {"server": fake_server}, create=True), mock.patch.object(
            server,
            "_find_project_cfg",
            return_value={"id": "task_dashboard", "name": "Task Dashboard"},
        ), mock.patch.object(
            server,
            "_set_project_scheduler_contract_in_config",
            return_value="/tmp/config.toml",
        ), mock.patch.object(
            server,
            "_clear_dashboard_cfg_cache",
            return_value=None,
        ), mock.patch.object(
            server,
            "load_project_session_health_config",
            return_value={
                "project_id": "task_dashboard",
                "project_name": "Task Dashboard",
                "enabled": True,
                "interval_minutes": 120,
                "configured": True,
            },
        ):
            code, payload = server._update_project_session_health_config(
                "task_dashboard",
                {"enabled": True, "interval_minutes": 120},
            )
        self.assertEqual(code, 200)
        self.assertTrue(payload.get("ok"))
        self.assertEqual(payload.get("project_id"), "task_dashboard")

    def test_set_project_scheduler_contract_supports_inspection_tasks(self) -> None:
        raw = """
[[projects]]
id = "task_dashboard"
name = "Task Dashboard"

[projects.auto_inspection]
enabled = true
prompt_template = "巡查"
""".lstrip()
        out = server._set_project_scheduler_contract_in_config_text(
            raw,
            "task_dashboard",
            auto_inspection_patch={
                "active_inspection_task_id": "board-a",
                "inspection_tasks": [
                    {
                        "inspection_task_id": "board-a",
                        "title": "板块A",
                        "enabled": True,
                        "channel_name": "子级04-前端体验（task-overview 页面交互）",
                        "session_id": "019c561c-8b6c-7c60-b66f-63096d1a4de9",
                        "interval_minutes": 30,
                        "prompt_template": "巡查A",
                        "inspection_targets": ["in_progress"],
                        "auto_inspections": [],
                    }
                ],
            },
        )
        parsed = tomllib.loads(out)
        projects = parsed.get("projects") or []
        p0 = projects[0] if projects else {}
        ai = p0.get("auto_inspection") if isinstance(p0, dict) else {}
        tasks = (ai or {}).get("inspection_tasks") or []
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].get("inspection_task_id"), "board-a")
        self.assertEqual((ai or {}).get("active_inspection_task_id"), "board-a")

    def test_set_project_scheduler_contract_prompt_template_preserves_newline_escape(self) -> None:
        raw = """
[[projects]]
id = "task_dashboard"
name = "Task Dashboard"

[projects.auto_inspection]
enabled = true
prompt_template = "old"
inspection_targets = ["todo"]
""".lstrip()
        out1 = server._set_project_scheduler_contract_in_config_text(
            raw,
            "task_dashboard",
            auto_inspection_patch={"prompt_template": "line1\nline2"},
        )
        parsed1 = tomllib.loads(out1)
        projects1 = parsed1.get("projects") or []
        p1 = projects1[0] if projects1 else {}
        ai1 = p1.get("auto_inspection") if isinstance(p1, dict) else {}
        self.assertEqual((ai1 or {}).get("prompt_template"), "line1\nline2")
        self.assertEqual(out1.count("prompt_template ="), 1)

        out2 = server._set_project_scheduler_contract_in_config_text(
            out1,
            "task_dashboard",
            auto_inspection_patch={"prompt_template": "lineA\nlineB"},
        )
        parsed2 = tomllib.loads(out2)
        projects2 = parsed2.get("projects") or []
        p2 = projects2[0] if projects2 else {}
        ai2 = p2.get("auto_inspection") if isinstance(p2, dict) else {}
        self.assertEqual((ai2 or {}).get("prompt_template"), "lineA\nlineB")
        self.assertEqual(out2.count("prompt_template ="), 1)

    def test_resolve_effective_max_concurrency_priority(self) -> None:
        cfg = {"runtime": {"max_concurrency": 10}}
        with mock.patch.dict(os.environ, {"CCB_MAX_CONCURRENCY": "14"}, clear=False):
            n, src = server._resolve_effective_max_concurrency(cfg=cfg)
        self.assertEqual((n, src), (14, "env"))

        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CCB_MAX_CONCURRENCY", None)
            n2, src2 = server._resolve_effective_max_concurrency(cfg=cfg)
        self.assertEqual((n2, src2), (10, "config"))

        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CCB_MAX_CONCURRENCY", None)
            n3, src3 = server._resolve_effective_max_concurrency(cfg={})
        self.assertEqual((n3, src3), (8, "default"))

    def test_collect_cli_tools_snapshot(self) -> None:
        cfg = {
            "projects": [
                {
                    "id": "task_dashboard",
                    "channels": [
                        {"name": "A"},
                        {"name": "B", "cli_type": "claude"},
                    ],
                }
            ]
        }

        class _FakeSessionStore:
            def list_sessions(self, project_id: str):
                if project_id == "task_dashboard":
                    return [{"id": "s1", "cli_type": "opencode"}]
                return []

        infos = [
            SimpleNamespace(id="codex", name="Codex CLI", description="", enabled=True),
            SimpleNamespace(id="claude", name="Claude Code", description="", enabled=True),
            SimpleNamespace(id="opencode", name="OpenCode", description="", enabled=True),
        ]
        with mock.patch("server.list_cli_types", return_value=infos), \
             mock.patch("server._load_local_cli_bin_overrides", return_value={"codex": "/usr/local/bin/codex"}), \
             mock.patch(
                 "server.resolve_cli_executable_details",
                 side_effect=lambda command: {
                     "path": f"/resolved/{command}",
                     "source": "local_config" if command == "codex" else "PATH",
                     "exists": True,
                     "executable": True,
                     "env_key": f"TASK_DASHBOARD_{str(command).upper().replace('-', '_')}_BIN",
                 },
             ):
            snap = server._collect_cli_tools_snapshot(cfg, session_store=_FakeSessionStore())

        available = snap.get("available") or []
        self.assertEqual(len(available), 3)
        by_cli = (snap.get("configured") or {}).get("by_cli") or []
        index = {str(x.get("id")): x for x in by_cli}
        self.assertTrue(index["codex"]["configured"])
        self.assertEqual(index["codex"]["effective_channel_count"], 1)
        self.assertEqual(index["claude"]["effective_channel_count"], 1)
        self.assertEqual(index["opencode"]["session_binding_count"], 1)
        self.assertEqual(index["codex"]["effective_bin"], "/resolved/codex")
        self.assertEqual(index["codex"]["local_bin"], "/usr/local/bin/codex")
        self.assertEqual(index["codex"]["bin_source"], "local_config")


if __name__ == "__main__":
    unittest.main()
