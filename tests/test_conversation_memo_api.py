import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib import error as url_error
from urllib import request as url_request
from unittest import mock

from http.server import ThreadingHTTPServer

import server


class ConversationMemoApiTests(unittest.TestCase):
    def test_memo_api_crud_and_token(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            static_root = base / "static"
            static_root.mkdir(parents=True, exist_ok=True)
            (static_root / "index.html").write_text("ok", encoding="utf-8")

            run_store = server.RunStore(base / ".runs")
            session_store = server.SessionStore(base_dir=base)
            session_binding_store = server.SessionBindingStore(runs_dir=run_store.runs_dir)
            memo_store = server.ConversationMemoStore(base_dir=base / ".run" / "conversation-memos")

            httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
            httpd.static_root = static_root  # type: ignore[attr-defined]
            httpd.allow_root = static_root  # type: ignore[attr-defined]
            httpd.store = run_store  # type: ignore[attr-defined]
            httpd.session_store = session_store  # type: ignore[attr-defined]
            httpd.session_binding_store = session_binding_store  # type: ignore[attr-defined]
            httpd.conversation_memo_store = memo_store  # type: ignore[attr-defined]
            httpd.http_log = base / ".run" / "test.http.log"  # type: ignore[attr-defined]
            httpd.project_scheduler_runtime = server.ProjectSchedulerRuntimeRegistry(store=run_store)  # type: ignore[attr-defined]
            httpd.task_push_runtime = server.TaskPushRuntimeRegistry(store=run_store, session_store=session_store)  # type: ignore[attr-defined]
            httpd.assist_request_runtime = server.AssistRequestRuntimeRegistry(store=run_store, session_store=session_store)  # type: ignore[attr-defined]
            httpd.scheduler = None  # type: ignore[attr-defined]

            t = threading.Thread(target=httpd.serve_forever, daemon=True)
            t.start()
            port = int(httpd.server_address[1])
            base_url = f"http://127.0.0.1:{port}"
            pid = "task_dashboard"
            sid = "019c560f-62ba-7652-b714-d462b4335225"

            try:
                with mock.patch.dict("os.environ", {"TASK_DASHBOARD_TOKEN": "memo-token"}, clear=False):
                    create_url = f"{base_url}/api/conversation-memos"
                    payload = {
                        "projectId": pid,
                        "sessionId": sid,
                        "text": "待跟进事项",
                        "attachments": [{"filename": "a.png", "url": "/.runs/attachments/a.png"}],
                    }
                    req_no_token = url_request.Request(
                        create_url,
                        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    with self.assertRaises(url_error.HTTPError) as cm:
                        url_request.urlopen(req_no_token, timeout=3)
                    self.assertEqual(cm.exception.code, 403)

                    req = url_request.Request(
                        create_url,
                        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                        headers={
                            "Content-Type": "application/json",
                            "X-TaskDashboard-Token": "memo-token",
                        },
                        method="POST",
                    )
                    with url_request.urlopen(req, timeout=3) as resp:
                        self.assertEqual(resp.status, 200)
                        body = json.loads(resp.read().decode("utf-8"))
                    self.assertTrue(body.get("ok"))
                    memo_id = str((body.get("item") or {}).get("id") or "")
                    self.assertTrue(memo_id)
                    item2, _ = memo_store.create(
                        pid,
                        sid,
                        text="第二条待跟进事项",
                        attachments=[],
                    )
                    memo_id2 = str(item2.get("id") or "")
                    self.assertTrue(memo_id2)

                    with url_request.urlopen(
                        f"{base_url}/api/conversation-memos?projectId={pid}&sessionId={sid}",
                        timeout=3,
                    ) as resp2:
                        self.assertEqual(resp2.status, 200)
                        body2 = json.loads(resp2.read().decode("utf-8"))
                    self.assertEqual(body2.get("count"), 2)
                    self.assertEqual([it.get("id") for it in body2.get("items") or []], [memo_id2, memo_id])

                    reorder_req = url_request.Request(
                        f"{base_url}/api/conversation-memos/reorder",
                        data=json.dumps(
                            {"projectId": pid, "sessionId": sid, "orderedIds": [memo_id, memo_id2]},
                            ensure_ascii=False,
                        ).encode("utf-8"),
                        headers={
                            "Content-Type": "application/json",
                            "X-TaskDashboard-Token": "memo-token",
                        },
                        method="POST",
                    )
                    with url_request.urlopen(reorder_req, timeout=3) as reorder_resp:
                        self.assertEqual(reorder_resp.status, 200)
                        reorder_body = json.loads(reorder_resp.read().decode("utf-8"))
                    self.assertTrue(reorder_body.get("ok"))
                    self.assertEqual(reorder_body.get("reordered"), 2)
                    self.assertEqual(reorder_body.get("count"), 2)

                    with url_request.urlopen(
                        f"{base_url}/api/conversation-memos?projectId={pid}&sessionId={sid}",
                        timeout=3,
                    ) as resp_reordered:
                        self.assertEqual(resp_reordered.status, 200)
                        body_reordered = json.loads(resp_reordered.read().decode("utf-8"))
                    self.assertEqual([it.get("id") for it in body_reordered.get("items") or []], [memo_id, memo_id2])

                    del_req = url_request.Request(
                        f"{base_url}/api/conversation-memos/delete",
                        data=json.dumps(
                            {"projectId": pid, "sessionId": sid, "ids": [memo_id]},
                            ensure_ascii=False,
                        ).encode("utf-8"),
                        headers={
                            "Content-Type": "application/json",
                            "X-TaskDashboard-Token": "memo-token",
                        },
                        method="POST",
                    )
                    with url_request.urlopen(del_req, timeout=3) as resp3:
                        self.assertEqual(resp3.status, 200)
                        body3 = json.loads(resp3.read().decode("utf-8"))
                    self.assertEqual(body3.get("deleted"), 1)
                    self.assertEqual(body3.get("count"), 1)

                    clear_req = url_request.Request(
                        f"{base_url}/api/conversation-memos/clear",
                        data=json.dumps({"projectId": pid, "sessionId": sid}, ensure_ascii=False).encode("utf-8"),
                        headers={
                            "Content-Type": "application/json",
                            "X-TaskDashboard-Token": "memo-token",
                        },
                        method="POST",
                    )
                    with url_request.urlopen(clear_req, timeout=3) as resp4:
                        self.assertEqual(resp4.status, 200)
                        body4 = json.loads(resp4.read().decode("utf-8"))
                    self.assertTrue(body4.get("ok"))
                    self.assertEqual(body4.get("count"), 0)
            finally:
                httpd.shutdown()
                t.join(timeout=2)
                httpd.server_close()


if __name__ == "__main__":
    unittest.main()
