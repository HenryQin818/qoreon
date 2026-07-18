import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock
from urllib import request as url_request
from urllib.error import HTTPError

import server
from task_dashboard.runtime.project_execution_context import build_project_execution_context


class SessionAtomicMigrationTests(unittest.TestCase):
    PROJECT_ID = "task_dashboard"
    OLD_CHANNEL = "主体-总控（范围-排期-验收）"
    NEW_CHANNEL = "主体04-项目专家（需求分析-范围评审-验收咨询）"
    OLD_PRIMARY_ID = "019f1111-1111-7111-8111-111111111111"
    TARGET_ID = "019f2222-2222-7222-8222-222222222222"
    NEW_PRIMARY_ID = "019f3333-3333-7333-8333-333333333333"

    def _start_server(self, base: Path):
        static_root = base / "static"
        static_root.mkdir(parents=True, exist_ok=True)
        (static_root / "index.html").write_text("ok", encoding="utf-8")
        run_store = server.RunStore(base / ".runs")
        session_store = server.SessionStore(base_dir=base)
        binding_store = server.SessionBindingStore(runs_dir=run_store.runs_dir)
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        httpd.static_root = static_root  # type: ignore[attr-defined]
        httpd.allow_root = static_root  # type: ignore[attr-defined]
        httpd.store = run_store  # type: ignore[attr-defined]
        httpd.session_store = session_store  # type: ignore[attr-defined]
        httpd.session_binding_store = binding_store  # type: ignore[attr-defined]
        httpd.http_log = base / ".run" / "test.http.log"  # type: ignore[attr-defined]
        httpd.scheduler = None  # type: ignore[attr-defined]
        httpd.environment_name = "refactor"  # type: ignore[attr-defined]
        httpd.worktree_root = str(base / "worktree-refactor")  # type: ignore[attr-defined]
        return httpd, session_store, binding_store

    def _seed_migration(self, base: Path, session_store, binding_store) -> dict[str, str]:
        root = base / "worktree-refactor"
        source_workdir = root / "project"
        old_workdir = root / "channels" / "control"
        new_workdir = root / "channels" / "expert"
        for path in (root, source_workdir, old_workdir, new_workdir):
            path.mkdir(parents=True, exist_ok=True)

        session_store.create_session(
            self.PROJECT_ID,
            self.OLD_CHANNEL,
            session_id=self.OLD_PRIMARY_ID,
            alias="项目总控",
            environment="refactor",
            worktree_root=str(root),
            workdir=str(source_workdir),
            branch="main",
            is_primary=True,
        )
        old_context = build_project_execution_context(
            target={
                "project_id": self.PROJECT_ID,
                "channel_name": self.OLD_CHANNEL,
                "session_id": self.TARGET_ID,
                "environment": "refactor",
                "worktree_root": str(root),
                "workdir": str(old_workdir),
                "branch": "main",
            },
            source={
                "project_id": self.PROJECT_ID,
                "environment": "refactor",
                "worktree_root": str(root),
                "workdir": str(source_workdir),
                "branch": "main",
            },
            context_source="project",
            override_fields=["workdir"],
            override_source="session",
        )
        session_store.create_session(
            self.PROJECT_ID,
            self.OLD_CHANNEL,
            session_id=self.TARGET_ID,
            alias="项目专家",
            environment="refactor",
            worktree_root=str(root),
            workdir=str(old_workdir),
            branch="main",
            project_execution_context=old_context,
            is_primary=False,
        )
        session_store.create_session(
            self.PROJECT_ID,
            self.NEW_CHANNEL,
            session_id=self.NEW_PRIMARY_ID,
            alias="项目专家旧主位",
            environment="refactor",
            worktree_root=str(root),
            workdir=str(new_workdir),
            branch="main",
            is_primary=True,
        )
        binding_store.save_binding(
            self.TARGET_ID,
            self.PROJECT_ID,
            self.OLD_CHANNEL,
            "codex",
        )
        binding_store.save_binding(
            self.NEW_PRIMARY_ID,
            self.PROJECT_ID,
            self.NEW_CHANNEL,
            "codex",
        )
        return {
            "root": str(root),
            "source_workdir": str(source_workdir),
            "old_workdir": str(old_workdir),
            "new_workdir": str(new_workdir),
        }

    def _put(self, httpd, session_id: str, payload: dict):
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        port = int(httpd.server_address[1])
        try:
            req = url_request.Request(
                f"http://127.0.0.1:{port}/api/sessions/{session_id}",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="PUT",
            )
            with url_request.urlopen(req, timeout=3) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        finally:
            httpd.shutdown()
            thread.join(timeout=2)
            httpd.server_close()

    def _migration_payload(self, paths: dict[str, str]) -> dict:
        return {
            "channel_name": self.NEW_CHANNEL,
            "workdir": paths["new_workdir"],
            "session_role": "primary",
            "set_as_primary": True,
            "allow_stable_write": True,
        }

    def test_put_cross_channel_replaces_old_override_and_rebuilds_context(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            httpd, session_store, binding_store = self._start_server(base)
            paths = self._seed_migration(base, session_store, binding_store)

            status, body = self._put(httpd, self.TARGET_ID, self._migration_payload(paths))

            self.assertEqual(status, 200)
            session = body.get("session") or {}
            context = session.get("project_execution_context") or {}
            self.assertEqual(session.get("channel_name"), self.NEW_CHANNEL)
            self.assertEqual(session.get("workdir"), paths["new_workdir"])
            self.assertEqual((context.get("target") or {}).get("channel_name"), self.NEW_CHANNEL)
            self.assertEqual((context.get("target") or {}).get("workdir"), paths["new_workdir"])
            self.assertEqual((context.get("override") or {}).get("fields"), ["workdir"])
            self.assertEqual((context.get("override") or {}).get("source"), "request")
            self.assertEqual(session.get("context_binding_state"), "override")

    def test_put_cross_channel_syncs_binding_and_both_channel_primaries(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            httpd, session_store, binding_store = self._start_server(base)
            paths = self._seed_migration(base, session_store, binding_store)

            self._put(httpd, self.TARGET_ID, self._migration_payload(paths))

            target = session_store.get_session(self.TARGET_ID) or {}
            old_primary = session_store.get_session(self.OLD_PRIMARY_ID) or {}
            displaced_primary = session_store.get_session(self.NEW_PRIMARY_ID) or {}
            self.assertTrue(bool(target.get("is_primary")))
            self.assertEqual(target.get("session_role"), "primary")
            self.assertTrue(bool(old_primary.get("is_primary")))
            self.assertEqual(old_primary.get("session_role"), "primary")
            self.assertFalse(bool(displaced_primary.get("is_primary")))
            self.assertEqual(displaced_primary.get("session_role"), "child")
            self.assertEqual(
                (binding_store.get_binding(self.TARGET_ID) or {}).get("channelName"),
                self.NEW_CHANNEL,
            )
            self.assertEqual(
                (binding_store.get_binding(self.OLD_PRIMARY_ID) or {}).get("channelName"),
                self.OLD_CHANNEL,
            )
            self.assertIsNone(binding_store.get_binding(self.NEW_PRIMARY_ID))

    def test_binding_failure_rolls_back_sessions_bindings_and_primary(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            httpd, session_store, binding_store = self._start_server(base)
            paths = self._seed_migration(base, session_store, binding_store)
            session_path = session_store._project_path(self.PROJECT_ID)
            before_sessions = json.loads(session_path.read_text(encoding="utf-8"))
            before_bindings = sorted(
                binding_store.list_bindings(self.PROJECT_ID),
                key=lambda row: str(row.get("sessionId") or ""),
            )
            real_save = binding_store.save_binding
            call_count = 0

            def _flaky_save(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count == 2:
                    raise OSError("injected binding write failure")
                return real_save(*args, **kwargs)

            with mock.patch.object(binding_store, "save_binding", side_effect=_flaky_save):
                thread = threading.Thread(target=httpd.serve_forever, daemon=True)
                thread.start()
                port = int(httpd.server_address[1])
                try:
                    req = url_request.Request(
                        f"http://127.0.0.1:{port}/api/sessions/{self.TARGET_ID}",
                        data=json.dumps(self._migration_payload(paths)).encode("utf-8"),
                        headers={"Content-Type": "application/json"},
                        method="PUT",
                    )
                    with self.assertRaises(HTTPError) as raised:
                        url_request.urlopen(req, timeout=3)
                    self.assertEqual(raised.exception.code, 500)
                    body = json.loads(raised.exception.read().decode("utf-8"))
                    self.assertEqual(body.get("error_code"), "session_migration_failed")
                    self.assertTrue(bool(body.get("rollback_complete")))
                finally:
                    httpd.shutdown()
                    thread.join(timeout=2)
                    httpd.server_close()

            after_sessions = json.loads(session_path.read_text(encoding="utf-8"))
            after_bindings = sorted(
                binding_store.list_bindings(self.PROJECT_ID),
                key=lambda row: str(row.get("sessionId") or ""),
            )
            self.assertEqual(after_sessions, before_sessions)
            self.assertEqual(after_bindings, before_bindings)

    def test_moving_old_primary_promotes_remaining_old_channel_session(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            httpd, session_store, binding_store = self._start_server(base)
            paths = self._seed_migration(base, session_store, binding_store)
            session_store.update_session(self.TARGET_ID, is_primary=True)
            self.assertFalse(bool((session_store.get_session(self.OLD_PRIMARY_ID) or {}).get("is_primary")))

            self._put(httpd, self.TARGET_ID, self._migration_payload(paths))

            fallback = session_store.get_session(self.OLD_PRIMARY_ID) or {}
            self.assertTrue(bool(fallback.get("is_primary")))
            self.assertEqual(fallback.get("session_role"), "primary")

    def test_regular_put_remains_compatible_and_does_not_create_binding(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            httpd, session_store, binding_store = self._start_server(base)
            session_store.create_session(
                self.PROJECT_ID,
                self.OLD_CHANNEL,
                session_id=self.TARGET_ID,
                alias="旧名称",
                environment="refactor",
                is_primary=True,
            )

            status, body = self._put(
                httpd,
                self.TARGET_ID,
                {"alias": "新名称", "purpose": "普通字段更新"},
            )

            self.assertEqual(status, 200)
            self.assertEqual((body.get("session") or {}).get("alias"), "新名称")
            self.assertEqual((session_store.get_session(self.TARGET_ID) or {}).get("purpose"), "普通字段更新")
            self.assertIsNone(binding_store.get_binding(self.TARGET_ID))


if __name__ == "__main__":
    unittest.main()
