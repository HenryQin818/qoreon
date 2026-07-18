# -*- coding: utf-8 -*-

from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib import error as url_error
from urllib import request as url_request
from unittest import mock

import server
from task_dashboard import message_cli
from task_dashboard.runtime.message_delivery_control import MessageDeliveryRuntime


PROJECT_ID = "task_dashboard"
CHANNEL = "目标通道"
TARGET_SESSION = "019d232f-02f1-7781-9de8-2333f2417e73"
SOURCE_SESSION = "019dbd03-829b-78e1-8816-ab73c2f01071"


class _CountingScheduler:
    def __init__(self) -> None:
        self.enqueued: list[tuple[str, str, str]] = []
        self.lock = threading.Lock()

    def enqueue(self, run_id: str, session_id: str, cli_type: str = "codex", priority: str = "normal") -> bool:
        with self.lock:
            self.enqueued.append((run_id, session_id, cli_type))
        return True


class BusyAwareDeliveryTests(unittest.TestCase):
    def _start_server(self, base: Path):
        static_root = base / "static"
        static_root.mkdir(parents=True, exist_ok=True)
        (static_root / "index.html").write_text("ok", encoding="utf-8")

        run_store = server.RunStore(base / ".runs")
        session_store = server.SessionStore(base_dir=base)
        session_binding_store = server.SessionBindingStore(runs_dir=run_store.runs_dir)
        scheduler = _CountingScheduler()

        httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        httpd.static_root = static_root  # type: ignore[attr-defined]
        httpd.allow_root = static_root  # type: ignore[attr-defined]
        httpd.store = run_store  # type: ignore[attr-defined]
        httpd.session_store = session_store  # type: ignore[attr-defined]
        httpd.session_binding_store = session_binding_store  # type: ignore[attr-defined]
        httpd.http_log = base / ".run" / "test.http.log"  # type: ignore[attr-defined]
        httpd.scheduler = scheduler  # type: ignore[attr-defined]
        httpd.project_scheduler_runtime = server.ProjectSchedulerRuntimeRegistry(store=run_store, session_store=session_store)  # type: ignore[attr-defined]
        httpd.task_push_runtime = server.TaskPushRuntimeRegistry(store=run_store, session_store=session_store)  # type: ignore[attr-defined]
        httpd.task_plan_runtime = server.TaskPlanRuntimeRegistry(  # type: ignore[attr-defined]
            store=run_store,
            session_store=session_store,
            task_push_runtime=httpd.task_push_runtime,
        )
        httpd.assist_request_runtime = server.AssistRequestRuntimeRegistry(store=run_store, session_store=session_store)  # type: ignore[attr-defined]
        httpd.message_delivery_runtime = MessageDeliveryRuntime.for_store(run_store)  # type: ignore[attr-defined]
        httpd.environment_name = "stable"  # type: ignore[attr-defined]
        httpd.worktree_root = base  # type: ignore[attr-defined]
        return httpd, run_store, session_store, scheduler

    def _create_target_session(self, session_store: server.SessionStore) -> None:
        session_store.create_session(
            PROJECT_ID,
            CHANNEL,
            cli_type="codex",
            session_id=TARGET_SESSION,
            alias="目标Agent",
        )

    def _mark_target_busy(self, run_store: server.RunStore) -> str:
        run = run_store.create_run(
            PROJECT_ID,
            CHANNEL,
            TARGET_SESSION,
            "正在处理的任务",
            sender_type="agent",
            sender_id=SOURCE_SESSION,
            sender_name="产品-通讯能力",
            extra_meta={
                "source_ref": {
                    "project_id": PROJECT_ID,
                    "channel_name": "来源通道",
                    "session_id": SOURCE_SESSION,
                }
            },
        )
        run["status"] = "running"
        run["startedAt"] = run.get("createdAt")
        run_store.save_meta(str(run["id"]), run)
        return str(run["id"])

    def _post(self, port: int, body: dict) -> tuple[int, dict]:
        req = url_request.Request(
            f"http://127.0.0.1:{port}/api/codex/announce",
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "X-TaskDashboard-Token": "test-token",
            },
            method="POST",
        )
        try:
            with url_request.urlopen(req, timeout=5) as resp:
                return int(resp.status), json.loads(resp.read().decode("utf-8"))
        except url_error.HTTPError as exc:
            return int(exc.code), json.loads(exc.read().decode("utf-8"))

    def _base_payload(self, *, mode: str = "task_with_receipt", source_ref: dict | None = None) -> dict:
        payload = {
            "projectId": PROJECT_ID,
            "channelName": CHANNEL,
            "sessionId": TARGET_SESSION,
            "message": "请协助处理。",
            "sender_type": "agent",
            "sender_id": source_ref.get("session_id") if isinstance(source_ref, dict) else "message_cli",
            "sender_name": "产品-通讯能力",
            "message_kind": "collab_update",
            "interaction_mode": mode,
        }
        if source_ref is not None:
            payload["source_ref"] = source_ref
        if mode == "task_with_receipt":
            payload["callback_to"] = {"session_id": SOURCE_SESSION, "channel_name": "来源通道"}
        return payload

    def test_busy_task_with_receipt_first_bounces_then_ttl_confirm_enqueues(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            httpd, run_store, session_store, scheduler = self._start_server(base)
            self._create_target_session(session_store)
            busy_run_id = self._mark_target_busy(run_store)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            port = int(httpd.server_address[1])
            payload = self._base_payload(
                source_ref={"project_id": PROJECT_ID, "channel_name": "来源通道", "session_id": SOURCE_SESSION}
            )
            try:
                with mock.patch.dict("os.environ", {"TASK_DASHBOARD_TOKEN": "test-token"}, clear=False):
                    status1, body1 = self._post(port, payload)
                    first_enqueue_count = len(scheduler.enqueued)
                    httpd.message_delivery_runtime = MessageDeliveryRuntime.for_store(run_store)  # type: ignore[attr-defined]
                    status2, body2 = self._post(port, payload)
            finally:
                httpd.shutdown()
                thread.join(timeout=2)
                httpd.server_close()

            self.assertEqual(409, status1)
            self.assertFalse(body1["ok"])
            self.assertEqual("target_busy", body1["blocking_error"]["code"])
            self.assertEqual(busy_run_id, body1["target_busy"]["active_run_id"])
            self.assertTrue(body1["pending_confirm_available"])
            self.assertEqual(0, first_enqueue_count)

            self.assertEqual(200, status2)
            confirmed = body2.get("busy_confirm") or {}
            self.assertTrue(confirmed.get("confirmed"))
            run = body2.get("run") or {}
            self.assertEqual(TARGET_SESSION, run.get("sessionId"))
            self.assertTrue(bool(run.get("visible_in_channel_chat")))
            self.assertEqual(1, len(scheduler.enqueued))

    def test_missing_real_source_ref_only_bounces_and_never_confirms(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            httpd, run_store, session_store, scheduler = self._start_server(base)
            self._create_target_session(session_store)
            self._mark_target_busy(run_store)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            port = int(httpd.server_address[1])
            payload = self._base_payload(source_ref=None)
            try:
                with mock.patch.dict("os.environ", {"TASK_DASHBOARD_TOKEN": "test-token"}, clear=False):
                    status1, body1 = self._post(port, payload)
                    status2, body2 = self._post(port, payload)
            finally:
                httpd.shutdown()
                thread.join(timeout=2)
                httpd.server_close()

            self.assertEqual(409, status1)
            self.assertEqual(409, status2)
            self.assertFalse(body1["pending_confirm_available"])
            self.assertFalse(body2["pending_confirm_available"])
            self.assertNotIn("busy_confirm", {k: v for k, v in body1.items() if v})
            self.assertIn("source_ref.session_id", body1["blocking_error"]["message"])
            self.assertEqual(0, len(scheduler.enqueued))

    def test_expired_busy_confirm_window_rebounces_without_enqueue(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            httpd, run_store, session_store, scheduler = self._start_server(base)
            self._create_target_session(session_store)
            self._mark_target_busy(run_store)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            port = int(httpd.server_address[1])
            payload = self._base_payload(
                source_ref={"project_id": PROJECT_ID, "channel_name": "来源通道", "session_id": SOURCE_SESSION}
            )
            confirm_path = run_store.runs_dir.parent / ".run" / "message_delivery" / "busy_confirmations.json"
            try:
                with mock.patch.dict("os.environ", {"TASK_DASHBOARD_TOKEN": "test-token"}, clear=False):
                    status1, _body1 = self._post(port, payload)
                    state = json.loads(confirm_path.read_text(encoding="utf-8"))
                    for row in (state.get("pending") or {}).values():
                        row["expires_at_ts"] = 0
                    confirm_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
                    status2, body2 = self._post(port, payload)
            finally:
                httpd.shutdown()
                thread.join(timeout=2)
                httpd.server_close()

            self.assertEqual(409, status1)
            self.assertEqual(409, status2)
            self.assertEqual("target_busy", body2["blocking_error"]["code"])
            self.assertEqual(0, len(scheduler.enqueued))

    def test_dialog_now_is_gated_while_internal_retry_is_exempt(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            httpd, run_store, session_store, scheduler = self._start_server(base)
            self._create_target_session(session_store)
            self._mark_target_busy(run_store)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            port = int(httpd.server_address[1])
            dialog_payload = self._base_payload(
                mode="dialog_now",
                source_ref={"project_id": PROJECT_ID, "channel_name": "来源通道", "session_id": SOURCE_SESSION},
            )
            retry_payload = dict(dialog_payload)
            retry_payload["trigger_type"] = "provider_auto_retry"
            try:
                with mock.patch.dict("os.environ", {"TASK_DASHBOARD_TOKEN": "test-token"}, clear=False):
                    dialog_status, dialog_body = self._post(port, dialog_payload)
                    retry_status, retry_body = self._post(port, retry_payload)
            finally:
                httpd.shutdown()
                thread.join(timeout=2)
                httpd.server_close()

            self.assertEqual(409, dialog_status)
            self.assertEqual("target_busy", dialog_body["blocking_error"]["code"])
            self.assertEqual(200, retry_status)
            self.assertIn("run", retry_body)
            self.assertEqual(1, len(scheduler.enqueued))

    def test_notify_only_merges_into_one_visible_container_without_busy_bounce(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            httpd, run_store, session_store, scheduler = self._start_server(base)
            self._create_target_session(session_store)
            self._mark_target_busy(run_store)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            port = int(httpd.server_address[1])
            first = self._base_payload(
                mode="notify_only",
                source_ref={"project_id": PROJECT_ID, "channel_name": "来源通道A", "session_id": SOURCE_SESSION},
            )
            first["message"] = "通知 A"
            second = self._base_payload(
                mode="notify_only",
                source_ref={"project_id": PROJECT_ID, "channel_name": "来源通道B", "session_id": SOURCE_SESSION},
            )
            second["message"] = "通知 B"
            try:
                with mock.patch.dict("os.environ", {"TASK_DASHBOARD_TOKEN": "test-token"}, clear=False):
                    status1, body1 = self._post(port, first)
                    status2, body2 = self._post(port, second)
            finally:
                httpd.shutdown()
                thread.join(timeout=2)
                httpd.server_close()

            self.assertEqual(200, status1)
            self.assertEqual(200, status2)
            run1 = body1.get("run") or {}
            run2 = body2.get("run") or {}
            self.assertEqual(run1.get("id"), run2.get("id"))
            self.assertEqual("created", body1["notification_merge"]["action"])
            self.assertEqual("appended", body2["notification_merge"]["action"])
            self.assertEqual(1, len(scheduler.enqueued))
            msg = run_store.read_msg(str(run1.get("id")), limit_chars=10_000)
            self.assertIn("通知 A", msg)
            self.assertIn("通知 B", msg)
            meta = run_store.load_meta(str(run1.get("id"))) or {}
            self.assertEqual(2, (meta.get("notification_merge") or {}).get("item_count"))
            self.assertTrue(bool(meta.get("visible_in_channel_chat")))

    def test_notify_merge_concurrency_keeps_single_unconsumed_container(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            run_store = server.RunStore(base / ".runs")
            runtime = MessageDeliveryRuntime.for_store(run_store)
            created: list[str] = []
            enqueued: list[str] = []

            def create_run(message: str, extra_meta: dict) -> dict:
                run = run_store.create_run(
                    PROJECT_ID,
                    CHANNEL,
                    TARGET_SESSION,
                    message,
                    sender_type="agent",
                    sender_id=SOURCE_SESSION,
                    sender_name="产品-通讯能力",
                    extra_meta=extra_meta,
                )
                created.append(str(run["id"]))
                return run

            def enqueue_run(run: dict) -> None:
                enqueued.append(str(run.get("id") or ""))

            def worker(index: int) -> None:
                runtime.merge_notify_only(
                    store=run_store,
                    project_id=PROJECT_ID,
                    channel_name=CHANNEL,
                    target_session_id=TARGET_SESSION,
                    message=f"并发通知 {index}",
                    profile_label="",
                    model="",
                    cli_type="codex",
                    attachments=None,
                    sender_fields={"sender_type": "agent", "sender_id": SOURCE_SESSION, "sender_name": "产品-通讯能力"},
                    run_extra_fields={
                        "interaction_mode": "notify_only",
                        "visible_in_channel_chat": True,
                        "source_ref": {"project_id": PROJECT_ID, "channel_name": "来源通道", "session_id": SOURCE_SESSION},
                    },
                    reasoning_effort="",
                    create_run=create_run,
                    enqueue_run=enqueue_run,
                )

            threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=3)

            self.assertEqual(1, len(set(created)))
            self.assertEqual(1, len(enqueued))
            meta = run_store.load_meta(created[0]) or {}
            self.assertEqual(8, (meta.get("notification_merge") or {}).get("item_count"))

    def test_notify_merge_soft_limit_folds_older_items(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            run_store = server.RunStore(base / ".runs")
            runtime = MessageDeliveryRuntime.for_store(run_store)
            created: list[str] = []

            def create_run(message: str, extra_meta: dict) -> dict:
                run = run_store.create_run(
                    PROJECT_ID,
                    CHANNEL,
                    TARGET_SESSION,
                    message,
                    sender_type="agent",
                    sender_id=SOURCE_SESSION,
                    sender_name="产品-通讯能力",
                    extra_meta=extra_meta,
                )
                created.append(str(run["id"]))
                return run

            def enqueue_run(_run: dict) -> None:
                return None

            for index in range(22):
                runtime.merge_notify_only(
                    store=run_store,
                    project_id=PROJECT_ID,
                    channel_name=CHANNEL,
                    target_session_id=TARGET_SESSION,
                    message=f"通知 {index}",
                    profile_label="",
                    model="",
                    cli_type="codex",
                    attachments=None,
                    sender_fields={"sender_type": "agent", "sender_id": SOURCE_SESSION, "sender_name": "产品-通讯能力"},
                    run_extra_fields={
                        "interaction_mode": "notify_only",
                        "visible_in_channel_chat": True,
                        "source_ref": {"project_id": PROJECT_ID, "channel_name": "来源通道", "session_id": SOURCE_SESSION},
                    },
                    reasoning_effort="",
                    create_run=create_run,
                    enqueue_run=enqueue_run,
                )

            meta = run_store.load_meta(created[0]) or {}
            merge = meta.get("notification_merge") or {}
            self.assertGreater(int(merge.get("folded_count") or 0), 0)
            self.assertLessEqual(int(merge.get("item_count") or 0), 20)
            self.assertIn("已折叠较早通知", run_store.read_msg(created[0], limit_chars=20_000))

    def test_message_cli_transparently_reports_target_busy_without_wait_polling(self) -> None:
        response = {
            "ok": False,
            "state": "blocked",
            "blocking_error": {"code": "target_busy", "message": "目标 Agent 正忙"},
            "target_busy": {"target_session_id": TARGET_SESSION, "display_state": "running"},
            "pending_confirm_available": False,
        }
        args = type("Args", (), {"base_url": "http://127.0.0.1:18770", "token": "", "timeout": 1.0})()
        with mock.patch("task_dashboard.message_cli._http_json", return_value=(409, response)):
            out = message_cli.post_announce(args, {"projectId": PROJECT_ID, "sessionId": TARGET_SESSION})
        self.assertFalse(out["ok"])
        self.assertEqual("blocked", out["state"])
        self.assertEqual("target_busy", out["blocking_error"]["code"])
        self.assertEqual("running", out["target_busy"]["display_state"])


if __name__ == "__main__":
    unittest.main()
