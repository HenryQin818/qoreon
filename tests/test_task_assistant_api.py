import json
import tempfile
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib import request as url_request
from urllib.error import HTTPError
from unittest import mock

import server
from task_dashboard.runtime import session_routes, session_task_tracking
from task_dashboard.runtime.task_assistant_runtime import task_assistant_state_path


class _FakeScheduler:
    def __init__(self) -> None:
        self.enqueued: list[tuple[str, str, str]] = []

    def enqueue(self, run_id: str, session_id: str, cli_type: str = "codex") -> None:
        self.enqueued.append((str(run_id), str(session_id), str(cli_type)))


class TaskAssistantApiTests(unittest.TestCase):
    def _start_server(self, base: Path):
        with server._SESSION_RUNTIME_INDEX_CACHE_LOCK:
            server._SESSION_RUNTIME_INDEX_CACHE.clear()
            server._SESSION_RUNTIME_INDEX_INFLIGHT.clear()
            server._SESSION_RUNTIME_INDEX_INVALIDATED_AT.clear()
        with server._SESSION_EXTERNAL_BUSY_CACHE_LOCK:
            server._SESSION_EXTERNAL_BUSY_CACHE.clear()
        with session_routes._SESSIONS_PAYLOAD_CACHE_LOCK:
            session_routes._SESSIONS_PAYLOAD_CACHE.clear()
            session_routes._SESSIONS_PAYLOAD_CACHE_INFLIGHT.clear()
            session_routes._SESSIONS_PAYLOAD_CACHE_INVALIDATED_AT.clear()
        session_task_tracking._clear_task_tracking_file_caches()
        server._clear_dashboard_cfg_cache()

        static_root = base / "static"
        static_root.mkdir(parents=True, exist_ok=True)
        (static_root / "index.html").write_text("ok", encoding="utf-8")

        run_store = server.RunStore(base / ".runs")
        session_store = server.SessionStore(base_dir=base)
        session_binding_store = server.SessionBindingStore(runs_dir=run_store.runs_dir)

        httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        httpd.static_root = static_root  # type: ignore[attr-defined]
        httpd.allow_root = static_root  # type: ignore[attr-defined]
        httpd.worktree_root = base  # type: ignore[attr-defined]
        httpd.environment_name = "stable"  # type: ignore[attr-defined]
        httpd.store = run_store  # type: ignore[attr-defined]
        httpd.session_store = session_store  # type: ignore[attr-defined]
        httpd.session_binding_store = session_binding_store  # type: ignore[attr-defined]
        httpd.http_log = base / ".run" / "test.http.log"  # type: ignore[attr-defined]
        httpd.scheduler = _FakeScheduler()  # type: ignore[attr-defined]
        httpd.project_scheduler_runtime = server.ProjectSchedulerRuntimeRegistry(store=run_store, session_store=session_store)  # type: ignore[attr-defined]
        httpd.task_push_runtime = server.TaskPushRuntimeRegistry(store=run_store, session_store=session_store)  # type: ignore[attr-defined]
        httpd.task_push_runtime.set_scheduler(httpd.scheduler)  # type: ignore[attr-defined]
        httpd.task_plan_runtime = server.TaskPlanRuntimeRegistry(  # type: ignore[attr-defined]
            store=run_store,
            session_store=session_store,
            task_push_runtime=httpd.task_push_runtime,
        )
        httpd.heartbeat_task_runtime = server.HeartbeatTaskRuntimeRegistry(  # type: ignore[attr-defined]
            store=run_store,
            session_store=session_store,
            task_push_runtime=httpd.task_push_runtime,
        )
        httpd.assist_request_runtime = server.AssistRequestRuntimeRegistry(store=run_store, session_store=session_store)  # type: ignore[attr-defined]
        return httpd, run_store, session_store

    def _request_json(
        self,
        *,
        method: str,
        url: str,
        body: dict | None = None,
    ) -> tuple[int, dict]:
        data = None
        headers = {}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = url_request.Request(url, data=data, headers=headers, method=method)
        with url_request.urlopen(req, timeout=3) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))

    def _write_task_file(
        self,
        *,
        base: Path,
        channel_name: str,
        task_id: str,
        title: str,
    ) -> str:
        rel_path = f"任务规划/{channel_name}/任务/{title}.md"
        target = base / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            "---\n"
            f"task_id: {task_id}\n"
            "created_at: 2026-04-08T01:20:00+0800\n"
            "---\n\n"
            f"# {title}\n\n"
            "## 任务目标\n"
            "- 验证 task assistant read-back。\n",
            encoding="utf-8",
        )
        return rel_path

    def _create_task_run(
        self,
        *,
        store: server.RunStore,
        project_id: str,
        channel_name: str,
        session_id: str,
        task_id: str,
        task_path: str,
    ) -> str:
        run = store.create_run(
            project_id,
            channel_name,
            session_id,
            "请继续推进 task assistant 验证。",
            sender_type="user",
            sender_id="pm",
            sender_name="产品",
        )
        run_id = str(run.get("id") or "").strip()
        meta = store.load_meta(run_id) or {}
        now = time.time()
        meta["status"] = "done"
        meta["task_id"] = task_id
        meta["task_path"] = task_path
        meta["messagePreview"] = "请继续推进 task assistant 验证。"
        meta["lastPreview"] = "已完成一轮运行时验证。"
        meta["createdAt"] = time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(now - 20))
        meta["startedAt"] = time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(now - 15))
        meta["finishedAt"] = time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(now - 5))
        store.save_meta(run_id, meta)
        return run_id

    def test_task_assistant_put_get_and_task_tracking_read_back(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            httpd, store, session_store = self._start_server(base)
            pid = "task_dashboard"
            channel_name = "子级02-CCB运行时（server-并发-安全-启动）"
            sid = "019d62e5-e8e5-7b42-be88-db6f0e735118"
            task_id = "task_20260408_task_assistant_runtime_compile"
            title = "【进行中】【任务】20260408-task assistant 测试任务"
            task_path = self._write_task_file(
                base=base,
                channel_name=channel_name,
                task_id=task_id,
                title=title,
            )
            session_store.create_session(
                pid,
                channel_name,
                cli_type="codex",
                session_id=sid,
                alias="服务开发-任务维度",
                is_primary=True,
                worktree_root=str(base),
                workdir=str(base),
            )
            self._create_task_run(
                store=store,
                project_id=pid,
                channel_name=channel_name,
                session_id=sid,
                task_id=task_id,
                task_path=task_path,
            )

            t = threading.Thread(target=httpd.serve_forever, daemon=True)
            t.start()
            port = int(httpd.server_address[1])
            try:
                list_url = f"http://127.0.0.1:{port}/api/sessions?project_id={pid}"
                with url_request.urlopen(list_url, timeout=3) as resp:
                    before = json.loads(resp.read().decode("utf-8"))
                session_row = next(
                    row for row in (before.get("sessions") or [])
                    if str(row.get("id") or "").strip() == sid
                )
                before_summary = (((session_row.get("task_tracking") or {}).get("current_task_ref") or {}).get("task_assistant") or {})
                self.assertFalse(bool(before_summary.get("configured")))

                put_url = f"http://127.0.0.1:{port}/api/tasks/{task_id}/assistant-config"
                body = {
                    "project_id": pid,
                    "task_assistant": {
                        "enabled": True,
                        "mode": "pending_receipt",
                        "target_session_id": sid,
                        "schedule": {
                            "type": "interval",
                            "interval_minutes": 30,
                        },
                        "busy_policy": "skip_if_busy",
                        "max_execute_count": 2,
                    },
                }
                with mock.patch.object(server.Handler, "_require_token", return_value=True):
                    status, put_payload = self._request_json(method="PUT", url=put_url, body=body)
                self.assertEqual(status, 200)
                task_assistant = put_payload.get("task_assistant") or {}
                self.assertTrue(bool(task_assistant.get("configured")))
                self.assertEqual(str(task_assistant.get("state") or ""), "enabled")
                self.assertEqual(str(task_assistant.get("mode") or ""), "pending_receipt")
                self.assertEqual(str(task_assistant.get("target_session_id") or ""), sid)
                self.assertEqual(int(task_assistant.get("max_execute_count") or 0), 2)
                compiled = task_assistant.get("compiled") or {}
                self.assertTrue(bool(compiled.get("exists")))
                self.assertTrue(bool(compiled.get("ready")))

                status, get_payload = self._request_json(method="GET", url=f"{put_url}?project_id={pid}")
                self.assertEqual(status, 200)
                self.assertEqual(str((get_payload.get("task_assistant") or {}).get("mode") or ""), "pending_receipt")
                allowed = get_payload.get("allowed_target_sessions") or []
                self.assertEqual(len(allowed), 1)
                self.assertEqual(str(allowed[0].get("session_id") or ""), sid)

                with url_request.urlopen(list_url, timeout=3) as resp:
                    after = json.loads(resp.read().decode("utf-8"))
                updated_row = next(
                    row for row in (after.get("sessions") or [])
                    if str(row.get("id") or "").strip() == sid
                )
                current_task_ref = ((updated_row.get("task_tracking") or {}).get("current_task_ref") or {})
                summary = current_task_ref.get("task_assistant") or {}
                self.assertTrue(bool(summary.get("configured")))
                self.assertEqual(str(summary.get("state") or ""), "enabled")
                self.assertEqual(str(summary.get("mode") or ""), "pending_receipt")
                self.assertEqual(str(summary.get("target_session_id") or ""), sid)
            finally:
                httpd.shutdown()
                t.join(timeout=2)
                httpd.server_close()

    def test_task_assistant_put_rejects_invalid_target_session(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            httpd, _store, _session_store = self._start_server(base)
            pid = "task_dashboard"
            task_id = "task_20260408_invalid_target"

            t = threading.Thread(target=httpd.serve_forever, daemon=True)
            t.start()
            port = int(httpd.server_address[1])
            try:
                put_url = f"http://127.0.0.1:{port}/api/tasks/{task_id}/assistant-config"
                body = {
                    "project_id": pid,
                    "task_assistant": {
                        "enabled": True,
                        "mode": "stale_progress",
                        "target_session_id": "not-a-session",
                        "schedule": {"type": "interval", "interval_minutes": 30},
                    },
                }
                with mock.patch.object(server.Handler, "_require_token", return_value=True):
                    with self.assertRaises(HTTPError) as ctx:
                        self._request_json(method="PUT", url=put_url, body=body)
                self.assertEqual(ctx.exception.code, 422)
                payload = json.loads(ctx.exception.read().decode("utf-8"))
                self.assertEqual(str(payload.get("error") or ""), "invalid target_session_id")
                state_path = task_assistant_state_path(runtime_base_dir=base, project_id=pid)
                self.assertFalse(state_path.exists())
            finally:
                httpd.shutdown()
                t.join(timeout=2)
                httpd.server_close()

    def test_task_assistant_run_now_and_delete(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            httpd, _store, session_store = self._start_server(base)
            pid = "task_dashboard"
            channel_name = "子级02-CCB运行时（server-并发-安全-启动）"
            sid = "019d62e5-e8e5-7b42-be88-db6f0e735118"
            task_id = "task_20260408_run_now_and_delete"
            session_store.create_session(
                pid,
                channel_name,
                cli_type="codex",
                session_id=sid,
                alias="服务开发-任务维度",
                is_primary=True,
                worktree_root=str(base),
                workdir=str(base),
            )

            t = threading.Thread(target=httpd.serve_forever, daemon=True)
            t.start()
            port = int(httpd.server_address[1])
            try:
                base_url = f"http://127.0.0.1:{port}/api/tasks/{task_id}/assistant-config"
                put_body = {
                    "project_id": pid,
                    "task_assistant": {
                        "enabled": True,
                        "mode": "owner_inactive",
                        "target_session_id": sid,
                        "schedule": {
                            "type": "daily",
                            "daily_time": "09:30",
                            "weekdays": [1, 2, 3, 4, 5],
                        },
                        "busy_policy": "run_on_next_idle",
                        "max_execute_count": 1,
                    },
                }
                with mock.patch.object(server.Handler, "_require_token", return_value=True):
                    status, put_payload = self._request_json(method="PUT", url=base_url, body=put_body)
                    self.assertEqual(status, 200)

                    status, run_payload = self._request_json(
                        method="POST",
                        url=f"{base_url}/run-now",
                        body={"project_id": pid},
                    )
                    self.assertEqual(status, 200)
                    record = run_payload.get("record") or {}
                    self.assertEqual(str(record.get("status") or ""), "dispatched")
                    self.assertTrue(bool(str(record.get("run_id") or "")))
                    item = run_payload.get("item") or {}
                    self.assertEqual(str(item.get("last_status") or ""), "dispatched")

                    status, delete_payload = self._request_json(
                        method="DELETE",
                        url=f"{base_url}?project_id={pid}",
                    )
                self.assertEqual(status, 200)
                self.assertTrue(bool(delete_payload.get("removed")))
                summary = delete_payload.get("task_assistant") or {}
                self.assertFalse(bool(summary.get("configured")))
                self.assertEqual(str(summary.get("state") or ""), "disabled")

                status, get_payload = self._request_json(method="GET", url=f"{base_url}?project_id={pid}")
                self.assertEqual(status, 200)
                current_summary = get_payload.get("task_assistant") or {}
                self.assertFalse(bool(current_summary.get("configured")))
                self.assertEqual(str(current_summary.get("state") or ""), "disabled")
                self.assertFalse(bool((current_summary.get("compiled") or {}).get("exists")))
            finally:
                httpd.shutdown()
                t.join(timeout=2)
                httpd.server_close()


if __name__ == "__main__":
    unittest.main()
