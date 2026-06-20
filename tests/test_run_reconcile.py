import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import server


class _TrackedProc:
    def poll(self):
        return 1


class RunReconcileTests(unittest.TestCase):
    def _running_meta(self, run_id: str) -> dict:
        return {
            "id": run_id,
            "status": "running",
            "createdAt": "2026-02-18T10:00:00+0800",
            "startedAt": "2026-02-18T10:00:10+0800",
            "finishedAt": "",
            "error": "",
            "lastPreview": "",
            "cliType": "codex",
        }

    def test_reconcile_keeps_running_when_registry_tracked(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            rid = "20260222-keep-running"
            meta = self._running_meta(rid)
            proc = _TrackedProc()
            with server.RUN_PROCESS_REGISTRY._lock:
                server.RUN_PROCESS_REGISTRY._procs[rid] = proc
            try:
                with mock.patch("server._run_process_alive", return_value=False):
                    out, changed = store.reconcile_meta(dict(meta))
                self.assertEqual("running", out.get("status"))
                self.assertFalse(changed)
            finally:
                with server.RUN_PROCESS_REGISTRY._lock:
                    server.RUN_PROCESS_REGISTRY._procs.pop(rid, None)

    def test_reconcile_clears_probe_misses_when_registry_tracked(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            rid = "20260222-clear-miss"
            meta = self._running_meta(rid)
            meta["probeMisses"] = 2
            proc = _TrackedProc()
            with server.RUN_PROCESS_REGISTRY._lock:
                server.RUN_PROCESS_REGISTRY._procs[rid] = proc
            try:
                with mock.patch("server._run_process_alive", return_value=False):
                    out, changed = store.reconcile_meta(dict(meta))
                self.assertEqual("running", out.get("status"))
                self.assertNotIn("probeMisses", out)
                self.assertTrue(changed)
            finally:
                with server.RUN_PROCESS_REGISTRY._lock:
                    server.RUN_PROCESS_REGISTRY._procs.pop(rid, None)

    def test_reconcile_promotes_queued_to_running_when_own_process_alive(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            rid = "20260304-queued-promote"
            meta = {
                "id": rid,
                "status": "queued",
                "createdAt": "2026-03-04T20:11:48+0800",
                "startedAt": "",
                "finishedAt": "",
                "error": "",
                "cliType": "codex",
                "queueReason": "session_busy_external",
                "queueReasonAt": "2026-03-04T20:11:48+0800",
            }
            with mock.patch("server._run_process_alive", return_value=True):
                out, changed = store.reconcile_meta(dict(meta))
            self.assertTrue(changed)
            self.assertEqual("running", out.get("status"))
            self.assertTrue(str(out.get("startedAt") or "").strip())
            self.assertNotIn("queueReason", out)
            self.assertNotIn("queueReasonAt", out)

    def test_reconcile_keeps_queued_when_process_not_alive(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            rid = "20260304-queued-keep"
            meta = {
                "id": rid,
                "status": "queued",
                "createdAt": "2026-03-04T20:11:48+0800",
                "startedAt": "",
                "finishedAt": "",
                "error": "",
                "cliType": "codex",
                "queueReason": "session_busy_external",
                "queueReasonAt": "2026-03-04T20:11:48+0800",
            }
            with mock.patch("server._run_process_alive", return_value=False):
                out, changed = store.reconcile_meta(dict(meta))
            self.assertFalse(changed)
            self.assertEqual("queued", out.get("status"))
            self.assertEqual("session_busy_external", out.get("queueReason"))

    def test_reconcile_syncs_terminal_display_state(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            meta = {
                "id": "20260316-sync-display",
                "status": "done",
                "display_state": "running",
                "queue_reason": "session_busy_external",
                "blocked_by_run_id": "old-run",
                "createdAt": "2026-03-16T09:00:00+0800",
                "finishedAt": "2026-03-16T09:01:00+0800",
            }
            out, changed = store.reconcile_meta(dict(meta))
            self.assertTrue(changed)
            self.assertEqual("done", out.get("status"))
            self.assertEqual("done", out.get("display_state"))
            self.assertEqual("", out.get("queue_reason"))
            self.assertEqual("", out.get("blocked_by_run_id"))

    def test_reconcile_marks_done_when_log_has_agent_message(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            rid = "20260316-agent-log-done"
            meta = self._running_meta(rid)
            meta["display_state"] = "running"
            log_path = store._paths(rid)["log"]
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text(
                '[stdout] {"type":"item.completed","item":{"type":"agent_message","text":"已完成，正在收口。"}}\n',
                encoding="utf-8",
            )
            with mock.patch("server._run_process_alive", return_value=False):
                out, changed = store.reconcile_meta(dict(meta))
                out, changed2 = store.reconcile_meta(dict(out))
                out, changed3 = store.reconcile_meta(dict(out))
            self.assertTrue(changed or changed2 or changed3)
            self.assertEqual("done", out.get("status"))
            self.assertEqual("done", out.get("display_state"))
            self.assertIn("已完成", str(out.get("lastPreview") or ""))

    def test_reconcile_marks_done_when_terminal_text_cli_has_stdout_message(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            rid = "20260401-claude-terminal-done"
            meta = self._running_meta(rid)
            meta["cliType"] = "claude"
            meta["display_state"] = "running"
            log_path = store._paths(rid)["log"]
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text(
                "[stdout] 初始化训练已全部完成。等待总控指令或任务派发。\n",
                encoding="utf-8",
            )
            with mock.patch("server._run_process_alive", return_value=False):
                out, _ = store.reconcile_meta(dict(meta))
                out, _ = store.reconcile_meta(dict(out))
                out, _ = store.reconcile_meta(dict(out))
            self.assertEqual("done", out.get("status"))
            self.assertEqual("done", out.get("display_state"))
            self.assertEqual("", str(out.get("error") or ""))
            self.assertIn("初始化训练已全部完成", str(out.get("lastPreview") or ""))

    def test_reconcile_keeps_claude_done_when_permission_denied_has_final_text(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            rid = "20260401-claude-permission-denied-done"
            meta = self._running_meta(rid)
            meta["status"] = "done"
            meta["cliType"] = "claude"
            meta["lastPreview"] = "任务已完成，这是 ClaudeCode 最终正文。"
            log_path = store._paths(rid)["log"]
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text(
                "\n".join(
                    [
                        "[stdout] 任务已完成，这是 ClaudeCode 最终正文。",
                        "[stderr] permission requested: external_directory (/tmp/qoreon-demo/workspace/project/*); auto-rejecting",
                        "[stderr] Error: The user rejected permission to use this specific tool call.",
                    ]
                ),
                encoding="utf-8",
            )

            out, _ = store.reconcile_meta(dict(meta))

            self.assertEqual("done", out.get("status"))
            self.assertEqual("done", out.get("display_state"))
            self.assertEqual("", str(out.get("error") or ""))
            self.assertIn("ClaudeCode 最终正文", str(out.get("lastPreview") or ""))

    def test_reconcile_reclassifies_opencode_done_when_permission_denied_after_preface(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            rid = "20260401-opencode-permission-denied"
            meta = self._running_meta(rid)
            meta["status"] = "done"
            meta["cliType"] = "opencode"
            meta["lastPreview"] = "我来深入分析这两个项目的结构和模式。"
            log_path = store._paths(rid)["log"]
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text(
                "\n".join(
                    [
                        "[stdout] 我来深入分析这两个项目的结构和模式。",
                        "[stderr] permission requested: external_directory (/tmp/qoreon-demo/workspace/project/*); auto-rejecting",
                        "[stderr] ✗ read failed",
                        "[stderr] Error: The user rejected permission to use this specific tool call.",
                    ]
                ),
                encoding="utf-8",
            )

            out, changed = store.reconcile_meta(dict(meta))

            self.assertTrue(changed)
            self.assertEqual("error", out.get("status"))
            self.assertEqual("error", out.get("display_state"))
            self.assertIn("external_directory permission denied", str(out.get("error") or ""))
            self.assertIn("工作区外目录", server._error_hint(str(out.get("error") or "")))

    def test_reconcile_terminal_run_skips_session_semantics_scan(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            rid = "20260401-terminal-fast-observability"
            meta = {
                "id": rid,
                "status": "error",
                "createdAt": "2026-04-01T11:00:00+0800",
                "finishedAt": "2026-04-01T11:00:05+0800",
                "error": "run interrupted (server restarted or process exited)",
                "projectId": "task_dashboard",
                "sessionId": "session-1",
            }
            captured: list[bool] = []

            def _fake_build(*_args, **kwargs):
                captured.append(bool(kwargs.get("include_session_semantics")))
                return {
                    "display_state": "error",
                    "queue_reason": "",
                    "blocked_by_run_id": "",
                    "outcome_state": "interrupted_infra",
                    "error_class": "infra_restart",
                    "effective_for_session_health": True,
                    "effective_for_session_preview": False,
                    "superseded_by_run_id": "",
                    "recovery_of_run_id": "",
                }

            with mock.patch("server._build_run_observability_fields", side_effect=_fake_build):
                out, changed = store.reconcile_meta(dict(meta))

            self.assertTrue(changed)
            self.assertEqual([False], captured)
            self.assertEqual("interrupted_infra", out.get("outcome_state"))
            self.assertEqual("infra_restart", out.get("error_class"))

    def test_run_process_alive_falls_back_for_quoted_codex_output_path(self) -> None:
        rid = "20260316-fallback-alive"
        rows = [
            (
                12345,
                'node /tmp/qoreon-test/.local/bin/codex exec --json -o '
                f'"/tmp/task-dashboard/.runs/hot/{rid}.last.txt" resume 019cf48c complex-message',
            )
        ]
        with mock.patch("server._scan_process_table_rows", return_value=rows):
            self.assertTrue(server._run_process_alive(rid, cli_type="codex"))

    def test_reconcile_keeps_running_when_codex_process_matches_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            rid = "20260316-fallback-running"
            meta = self._running_meta(rid)
            meta["display_state"] = "running"
            meta["probeMisses"] = 2
            log_path = store._paths(rid)["log"]
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text(
                '[stdout] {"type":"item.completed","item":{"type":"agent_message","text":"处理中，尚未结束。"}}\n',
                encoding="utf-8",
            )
            rows = [
                (
                    12345,
                    'node /tmp/qoreon-test/.local/bin/codex exec --json -o '
                    f'"/tmp/task-dashboard/.runs/hot/{rid}.last.txt" resume 019cf48c complex-message',
                )
            ]
            with mock.patch("server._scan_process_table_rows", return_value=rows):
                out, changed = store.reconcile_meta(dict(meta))
            self.assertTrue(changed)
            self.assertEqual("running", out.get("status"))
            self.assertEqual("running", out.get("display_state"))
            self.assertNotIn("probeMisses", out)

    def test_reconcile_keeps_running_when_recent_progress_exists_after_probe_misses(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            rid = "20260613-recent-progress-running"
            now_ts = time.time()
            meta = self._running_meta(rid)
            meta["cliType"] = "claude"
            meta["display_state"] = "running"
            meta["probeMisses"] = 2
            meta["lastProgressAt"] = time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(now_ts - 60))
            meta["processEvents"] = [{"text": "正在读取文件"}]

            with (
                mock.patch("server.time.time", return_value=now_ts),
                mock.patch("server._run_process_alive", return_value=False),
            ):
                out, changed = store.reconcile_meta(dict(meta))

            self.assertTrue(changed)
            self.assertEqual("running", out.get("status"))
            self.assertEqual("running", out.get("display_state"))
            self.assertEqual("", str(out.get("error") or ""))
            self.assertEqual(3, out.get("probeMisses"))
            self.assertEqual(1, out.get("probeProcessEventCount"))

    def test_reconcile_keeps_running_when_process_events_grow_during_probe_cycle(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            rid = "20260613-process-growth-running"
            now_ts = time.time()
            meta = self._running_meta(rid)
            meta["cliType"] = "claude"
            meta["display_state"] = "running"
            meta["probeMisses"] = 2
            meta["probeProcessEventCount"] = 1
            meta["lastProgressAt"] = time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(now_ts - 300))
            meta["processEvents"] = [
                {"text": "读取文件"},
                {"text": "分析结果"},
            ]

            with (
                mock.patch("server.time.time", return_value=now_ts),
                mock.patch("server._run_process_alive", return_value=False),
            ):
                out, changed = store.reconcile_meta(dict(meta))

            self.assertTrue(changed)
            self.assertEqual("running", out.get("status"))
            self.assertEqual("running", out.get("display_state"))
            self.assertEqual("", str(out.get("error") or ""))
            self.assertEqual(3, out.get("probeMisses"))
            self.assertEqual(2, out.get("probeProcessEventCount"))

    def test_reconcile_marks_interrupted_when_probe_misses_have_no_recent_progress(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            rid = "20260613-stale-progress-interrupted"
            now_ts = time.time()
            meta = self._running_meta(rid)
            meta["cliType"] = "claude"
            meta["display_state"] = "running"
            meta["probeMisses"] = 2
            meta["probeProcessEventCount"] = 1
            meta["lastProgressAt"] = time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(now_ts - 300))
            meta["processEvents"] = [{"text": "旧过程"}]

            with (
                mock.patch("server.time.time", return_value=now_ts),
                mock.patch("server._run_process_alive", return_value=False),
            ):
                out, changed = store.reconcile_meta(dict(meta))

            self.assertTrue(changed)
            self.assertEqual("error", out.get("status"))
            self.assertEqual("interrupted_infra", out.get("outcome_state"))
            self.assertIn("run interrupted", str(out.get("error") or ""))
            self.assertNotIn("probeMisses", out)
            self.assertNotIn("probeProcessEventCount", out)

    def test_save_meta_updates_existing_legacy_copy(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            run_id = "20260316-legacy-sync"
            hot_meta = {
                "id": run_id,
                "status": "done",
                "display_state": "done",
                "queue_reason": "",
                "blocked_by_run_id": "",
                "createdAt": "2026-03-16T11:00:00+0800",
                "finishedAt": "2026-03-16T11:01:00+0800",
            }
            legacy_path = store._legacy_paths(run_id)["meta"]
            legacy_path.write_text(
                json.dumps({
                    "id": run_id,
                    "status": "done",
                    "display_state": "queued",
                }, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            store.save_meta(run_id, dict(hot_meta))
            legacy = json.loads(legacy_path.read_text(encoding="utf-8"))
            self.assertEqual("done", legacy.get("display_state"))
            self.assertEqual("", legacy.get("queue_reason"))

    def test_repair_legacy_hot_meta_consistency_backfills_existing_terminal_drift(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            run_id = "20260316-repair-legacy"
            hot_path = store._hot_paths(run_id)["meta"]
            hot_path.write_text(
                json.dumps({
                    "id": run_id,
                    "status": "done",
                    "display_state": "done",
                    "queue_reason": "",
                    "blocked_by_run_id": "",
                    "createdAt": "2026-03-16T11:00:00+0800",
                    "finishedAt": "2026-03-16T11:01:00+0800",
                }, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            legacy_path = store._legacy_paths(run_id)["meta"]
            legacy_path.write_text(
                json.dumps({
                    "id": run_id,
                    "status": "done",
                    "display_state": "running",
                    "queue_reason": "",
                    "blocked_by_run_id": "",
                    "createdAt": "2026-03-16T11:00:00+0800",
                    "finishedAt": "2026-03-16T11:01:00+0800",
                }, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            repaired = store.repair_legacy_hot_meta_consistency(limit=10)
            self.assertEqual(1, len(repaired))
            legacy = json.loads(legacy_path.read_text(encoding="utf-8"))
            self.assertEqual("done", legacy.get("display_state"))
            self.assertEqual(run_id, repaired[0].get("run_id"))

    def test_repair_legacy_hot_meta_consistency_uses_raw_hot_meta_without_reconcile(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            run_id = "20260401-repair-fast-path"
            hot_path = store._hot_paths(run_id)["meta"]
            hot_path.write_text(
                json.dumps({
                    "id": run_id,
                    "status": "done",
                    "display_state": "done",
                    "queue_reason": "",
                    "blocked_by_run_id": "",
                }, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            legacy_path = store._legacy_paths(run_id)["meta"]
            legacy_path.write_text(
                json.dumps({
                    "id": run_id,
                    "status": "done",
                    "display_state": "running",
                }, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            with mock.patch.object(store, "load_meta", side_effect=AssertionError("repair should not call load_meta")):
                repaired = store.repair_legacy_hot_meta_consistency(limit=10)
            self.assertEqual([run_id], [str(row.get("run_id") or "") for row in repaired])
            legacy = json.loads(legacy_path.read_text(encoding="utf-8"))
            self.assertEqual("done", legacy.get("display_state"))


if __name__ == "__main__":
    unittest.main()
