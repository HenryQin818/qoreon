import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import server
from task_dashboard import runstore_cli
from task_dashboard.routes.main import RouteDispatcher
from task_dashboard.runstore_health import (
    build_runstore_health_response,
    create_runstore_archive_dry_run,
    execute_runstore_archive_plan,
    list_runstore_hot_runs_response,
)


class RunStoreHotArchiveTests(unittest.TestCase):
    def test_create_run_writes_into_hot_dir(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            run = store.create_run("p", "c", "s", "msg")
            rid = str(run.get("id") or "")
            hot_meta = store.hot_dir / f"{rid}.json"
            legacy_meta = store.runs_dir / f"{rid}.json"
            self.assertTrue(hot_meta.exists())
            self.assertFalse(legacy_meta.exists())

    def test_list_runs_skips_archive_dir(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            hot = store.create_run("p", "c", "s", "hot")
            hot_id = str(hot.get("id") or "")
            hot_meta = store.load_meta(hot_id) or {}
            hot_meta["status"] = "done"
            store.save_meta(hot_id, hot_meta)

            archived = store.create_run("p", "c", "s", "old")
            archived_id = str(archived.get("id") or "")
            archived_paths = store._paths(archived_id)
            archived_meta = store.load_meta(archived_id) or {}
            archived_meta["status"] = "done"
            archived_meta["createdAt"] = "2026-02-01T10:00:00+0800"
            archived_meta["finishedAt"] = "2026-02-01T10:05:00+0800"
            store.save_meta(archived_id, archived_meta)
            legacy_meta = store.runs_dir / f"{archived_id}.json"
            archived_paths["meta"].replace(legacy_meta)
            for key, suffix in (("msg", ".msg.txt"), ("last", ".last.txt"), ("log", ".log.txt")):
                p = archived_paths[key]
                if p.exists():
                    p.replace(store.runs_dir / f"{archived_id}{suffix}")
            moved = store.archive_terminal_runs(older_than_s=3600, limit=10, dry_run=False)
            self.assertEqual(1, len(moved))

            rows = store.list_runs(project_id="p", limit=10, include_payload=False)
            ids = {str(row.get("id") or "") for row in rows}
            self.assertIn(hot_id, ids)
            self.assertNotIn(archived_id, ids)

    def test_load_meta_can_read_archived_run(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            run = store.create_run("p", "c", "s", "old")
            rid = str(run.get("id") or "")
            hot_paths = store._paths(rid)
            meta = store.load_meta(rid) or {}
            meta["status"] = "done"
            meta["createdAt"] = "2026-02-01T10:00:00+0800"
            meta["finishedAt"] = "2026-02-01T10:05:00+0800"
            store.save_meta(rid, meta)
            legacy_meta = store.runs_dir / f"{rid}.json"
            hot_paths["meta"].replace(legacy_meta)
            for key, suffix in (("msg", ".msg.txt"), ("last", ".last.txt"), ("log", ".log.txt")):
                p = hot_paths[key]
                if p.exists():
                    p.replace(store.runs_dir / f"{rid}{suffix}")
            store.archive_terminal_runs(older_than_s=3600, limit=10, dry_run=False)

            got = store.load_meta(rid)
            self.assertIsNotNone(got)
            self.assertEqual(rid, str(got.get("id") or ""))

    def test_archive_terminal_runs_moves_old_hot_run(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            run = store.create_run("p", "c", "s", "old")
            rid = str(run.get("id") or "")
            meta = store.load_meta(rid) or {}
            meta["status"] = "done"
            meta["createdAt"] = "2026-02-01T10:00:00+0800"
            meta["finishedAt"] = "2026-02-01T10:05:00+0800"
            store.save_meta(rid, meta)

            moved = store.archive_terminal_runs(older_than_s=3600, limit=10, dry_run=False)

            self.assertEqual(1, len(moved))
            self.assertFalse((store.hot_dir / f"{rid}.json").exists())
            self.assertTrue((store.archive_dir / "2026-02" / f"{rid}.json").exists())
            self.assertEqual(rid, str((store.load_meta(rid) or {}).get("id") or ""))

    def test_runstore_health_response_summarizes_hot_runs(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            done = store.create_run("p", "c", "s1", "done")
            done_id = str(done.get("id") or "")
            done_meta = store.load_meta(done_id) or {}
            done_meta["status"] = "done"
            done_meta["createdAt"] = "2026-02-01T10:00:00+0800"
            done_meta["finishedAt"] = "2026-02-01T10:05:00+0800"
            store.save_meta(done_id, done_meta)
            running = store.create_run("p", "c", "s2", "running")
            running_id = str(running.get("id") or "")
            running_meta = store.load_meta(running_id) or {}
            running_meta["status"] = "running"
            store.save_meta(running_id, running_meta)

            code, payload = build_runstore_health_response(store, project_id="p")

            self.assertEqual(200, code)
            self.assertTrue(payload.get("ok"))
            self.assertEqual("runstore_health.v1", payload.get("schema_version"))
            self.assertEqual(2, (payload.get("hot_summary") or {}).get("run_count"))
            self.assertEqual(1, (payload.get("state_group_counts") or {}).get("terminal"))
            self.assertEqual(1, (payload.get("state_group_counts") or {}).get("protected"))
            self.assertEqual(1, (payload.get("status_counts") or {}).get("done"))

    def test_runstore_hot_runs_response_is_summary_only(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            run = store.create_run("p", "c", "s", "secret message")
            rid = str(run.get("id") or "")
            meta = store.load_meta(rid) or {}
            meta["status"] = "done"
            meta["createdAt"] = "2026-02-01T10:00:00+0800"
            meta["finishedAt"] = "2026-02-01T10:05:00+0800"
            store.save_meta(rid, meta)
            store._paths(rid)["log"].write_text("full log should not be returned", encoding="utf-8")

            code, payload = list_runstore_hot_runs_response(
                store,
                query={"projectId": ["p"], "state_group": ["terminal"], "limit": ["10"]},
            )

            self.assertEqual(200, code)
            rows = payload.get("runs") or []
            self.assertEqual(1, len(rows))
            row = rows[0]
            self.assertEqual(rid, row.get("run_id"))
            self.assertTrue(row.get("archive_eligible"))
            self.assertNotIn("log", row)
            self.assertNotIn("message", row)

    def test_runstore_hot_runs_response_paginates(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            for index, day in enumerate(("01", "02", "03"), start=1):
                run = store.create_run("p", "c", "s", f"run-{index}")
                rid = str(run.get("id") or "")
                meta = store.load_meta(rid) or {}
                meta["status"] = "done"
                meta["createdAt"] = f"2026-02-{day}T10:00:00+0800"
                meta["finishedAt"] = f"2026-02-{day}T10:05:00+0800"
                store.save_meta(rid, meta)

            code, payload = list_runstore_hot_runs_response(
                store,
                query={"projectId": ["p"], "state_group": ["terminal"], "limit": ["2"], "offset": ["0"]},
            )

            self.assertEqual(200, code)
            self.assertEqual({"limit": 2, "offset": 0, "returned": 2, "total": 3, "has_more": True}, payload.get("pagination"))

    def test_runstore_archive_dry_run_and_execute_keep_attachments_in_place(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            run = store.create_run("p", "c", "s", "old")
            rid = str(run.get("id") or "")
            meta = store.load_meta(rid) or {}
            meta["status"] = "done"
            meta["createdAt"] = "2026-02-01T10:00:00+0800"
            meta["finishedAt"] = "2026-02-01T10:05:00+0800"
            store.save_meta(rid, meta)
            attachment_dir = store.runs_dir / rid / "attachments"
            attachment_dir.mkdir(parents=True)
            (attachment_dir / "keep.png").write_bytes(b"img")

            code, plan = create_runstore_archive_dry_run(
                store,
                body={
                    "projectId": "p",
                    "scope": "all",
                    "older_than_hours": 1,
                    "limit": 10,
                    "reason": "unit_test",
                },
            )

            self.assertEqual(200, code)
            self.assertEqual(1, plan.get("eligible_count"))
            self.assertFalse(plan.get("will_move_attachments"))
            self.assertFalse(plan.get("will_delete_files"))
            self.assertTrue((store.hot_dir / f"{rid}.json").exists())
            self.assertIn("plan_fingerprint", plan)

            code, executed = execute_runstore_archive_plan(
                store,
                body={
                    "job_id": plan.get("job_id"),
                    "confirm": True,
                    "expected_eligible_count": 1,
                },
            )

            self.assertEqual(200, code)
            self.assertEqual("completed", executed.get("execute_state"))
            self.assertEqual(1, executed.get("archived_count"))
            self.assertFalse((store.hot_dir / f"{rid}.json").exists())
            self.assertTrue((store.archive_dir / "2026-02" / f"{rid}.json").exists())
            self.assertTrue((attachment_dir / "keep.png").exists())
            self.assertTrue(Path(str(executed.get("manifest_path") or "")).exists())

    def test_runstore_archive_execute_requires_confirm(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            run = store.create_run("p", "c", "s", "old")
            rid = str(run.get("id") or "")
            meta = store.load_meta(rid) or {}
            meta["status"] = "done"
            meta["createdAt"] = "2026-02-01T10:00:00+0800"
            meta["finishedAt"] = "2026-02-01T10:05:00+0800"
            store.save_meta(rid, meta)
            _, plan = create_runstore_archive_dry_run(
                store,
                body={"projectId": "p", "scope": "all", "older_than_hours": 1},
            )

            code, executed = execute_runstore_archive_plan(
                store,
                body={"job_id": plan.get("job_id"), "confirm": False},
            )

            self.assertEqual(400, code)
            self.assertEqual("confirm_required", executed.get("error"))
            self.assertTrue((store.hot_dir / f"{rid}.json").exists())

    def test_runstore_archive_execute_revalidates_non_terminal_status(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            run = store.create_run("p", "c", "s", "old")
            rid = str(run.get("id") or "")
            meta = store.load_meta(rid) or {}
            meta["status"] = "done"
            meta["createdAt"] = "2026-02-01T10:00:00+0800"
            meta["finishedAt"] = "2026-02-01T10:05:00+0800"
            store.save_meta(rid, meta)
            _, plan = create_runstore_archive_dry_run(
                store,
                body={"projectId": "p", "scope": "all", "older_than_hours": 1},
            )
            meta["status"] = "running"
            store.save_meta(rid, meta)

            code, executed = execute_runstore_archive_plan(
                store,
                body={"job_id": plan.get("job_id"), "confirm": True, "expected_eligible_count": 1},
            )

            self.assertEqual(200, code)
            self.assertEqual("blocked", executed.get("execute_state"))
            self.assertEqual(0, executed.get("archived_count"))
            self.assertEqual(1, executed.get("skipped_count"))
            self.assertEqual("status_changed_to_running", (executed.get("skipped") or [{}])[0].get("reason"))
            self.assertTrue((store.hot_dir / f"{rid}.json").exists())

    def test_runstore_archive_dry_run_excludes_runtime_protected_done_run(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            run = store.create_run("p", "c", "s", "old")
            rid = str(run.get("id") or "")
            meta = store.load_meta(rid) or {}
            meta["status"] = "done"
            meta["createdAt"] = "2026-02-01T10:00:00+0800"
            meta["finishedAt"] = "2026-02-01T10:05:00+0800"
            store.save_meta(rid, meta)

            code, plan = create_runstore_archive_dry_run(
                store,
                body={"projectId": "p", "scope": "all", "older_than_hours": 1},
                protected_run_ids={rid},
            )

            self.assertEqual(200, code)
            self.assertEqual(0, plan.get("eligible_count"))
            self.assertTrue((store.hot_dir / f"{rid}.json").exists())

    def test_runstore_cli_health_outputs_json(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            store.create_run("p", "c", "s", "msg")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = runstore_cli.main(["--runs-dir", str(store.runs_dir), "--project-id", "p", "health"])
            payload = json.loads(out.getvalue())
            self.assertEqual(0, code)
            self.assertEqual("runstore_health.v1", payload.get("schema_version"))

    def test_runstore_routes_expose_contract_paths(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            run = store.create_run("p", "c", "s", "old")
            rid = str(run.get("id") or "")
            meta = store.load_meta(rid) or {}
            meta["status"] = "done"
            meta["createdAt"] = "2026-02-01T10:00:00+0800"
            meta["finishedAt"] = "2026-02-01T10:05:00+0800"
            store.save_meta(rid, meta)
            response: dict[str, object] = {}
            body = {"projectId": "p", "scope": "all", "older_than_hours": 1}

            def _json_response(_handler, code, payload, **_kwargs):
                response["code"] = code
                response["payload"] = payload

            ctx = SimpleNamespace(
                store=store,
                scheduler=None,
                run_process_registry=SimpleNamespace(tracked_run_ids=lambda: set()),
                json_response=_json_response,
                require_token=lambda: True,
                read_body_json=lambda _handler, max_bytes=0: dict(body),
                coerce_bool=lambda value, default=False: default if value is None else bool(value),
                safe_text=lambda value, max_len=4000: str(value or "")[:max_len],
            )
            dispatcher = RouteDispatcher(ctx)

            get_handler = SimpleNamespace(path="/api/runstore/health?projectId=p")
            self.assertTrue(dispatcher.dispatch_get(get_handler))
            self.assertEqual(200, response.get("code"))
            self.assertEqual("runstore_health.v1", (response.get("payload") or {}).get("schema_version"))

            post_handler = SimpleNamespace(path="/api/runstore/archive/dry-run")
            self.assertTrue(dispatcher.dispatch_post(post_handler))
            self.assertEqual(200, response.get("code"))
            self.assertEqual("runstore_archive_plan.v1", (response.get("payload") or {}).get("schema_version"))

    def test_runtime_archive_terminal_rejects_legacy_write_modes(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = server.RunStore(Path(td))
            run = store.create_run("p", "c", "s", "old")
            rid = str(run.get("id") or "")
            meta = store.load_meta(rid) or {}
            meta["status"] = "done"
            meta["createdAt"] = "2026-02-01T10:00:00+0800"
            meta["finishedAt"] = "2026-02-01T10:05:00+0800"
            store.save_meta(rid, meta)
            response: dict[str, object] = {}
            body: dict[str, object] = {}

            def _json_response(_handler, code, payload, **_kwargs):
                response["code"] = code
                response["payload"] = payload

            ctx = SimpleNamespace(
                store=store,
                scheduler=None,
                run_process_registry=SimpleNamespace(tracked_run_ids=lambda: set()),
                json_response=_json_response,
                require_token=lambda: True,
                read_body_json=lambda _handler, max_bytes=0: dict(body),
                coerce_bool=server._coerce_bool,
                safe_text=lambda value, max_len=4000: str(value or "")[:max_len],
            )
            dispatcher = RouteDispatcher(ctx)
            post_handler = SimpleNamespace(path="/api/runtime/runstore/archive-terminal")

            for write_body in ({"execute": True}, {"dryRun": False}, {"dry_run": False}):
                response.clear()
                body.clear()
                body.update({"projectId": "p", "olderThanS": 1, "limit": 10, **write_body})

                self.assertTrue(dispatcher.dispatch_post(post_handler))

                self.assertEqual(409, response.get("code"))
                payload = response.get("payload") or {}
                self.assertEqual("legacy_archive_execute_disabled", payload.get("error"))
                self.assertTrue((store.hot_dir / f"{rid}.json").exists())
                self.assertFalse((store.archive_dir / "2026-02" / f"{rid}.json").exists())


if __name__ == "__main__":
    unittest.main()
