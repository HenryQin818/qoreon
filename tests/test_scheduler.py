import threading
import time
import unittest
from unittest import mock

import server


class TestScheduler(unittest.TestCase):
    def test_scan_process_table_rows_uses_wide_ps_output(self) -> None:
        proc = mock.Mock()
        proc.returncode = 0
        proc.stdout = "123 /usr/local/bin/codex exec --json -o /tmp/x.last.txt resume sid hello\n"
        with mock.patch("server.subprocess.run", return_value=proc) as mocked:
            rows = server._scan_process_table_rows()
        self.assertEqual(rows, [(123, "/usr/local/bin/codex exec --json -o /tmp/x.last.txt resume sid hello")])
        mocked.assert_called_once()
        args, kwargs = mocked.call_args
        self.assertEqual(args[0], ["ps", "-axww", "-o", "pid=,command="])
        self.assertEqual(kwargs.get("timeout"), 2.0)

    def test_per_session_serial(self) -> None:
        calls: list[str] = []
        lock = threading.Lock()
        run_ids = ["ps1", "ps2", "ps3"]

        def fake_run(
            _store: object,
            run_id: str,
            timeout_s: object = None,
            cli_type: str = "codex",
            scheduler: object = None,
        ) -> None:
            # Record start order; sleep to allow any accidental parallelism.
            with lock:
                calls.append(run_id)
            time.sleep(0.05)

        old = server.run_cli_exec
        server.run_cli_exec = fake_run  # type: ignore[assignment]
        try:
            sched = server.RunScheduler(store=object(), max_concurrency=4)
            sid = "s1"
            for rid in run_ids:
                sched.enqueue(rid, sid)
            # Wait up to 2s for completion.
            t0 = time.time()
            while True:
                with lock:
                    ordered = [x for x in calls if x in run_ids]
                    if ordered == run_ids:
                        break
                if time.time() - t0 > 2:
                    self.fail(f"unexpected call order: {calls}")
                time.sleep(0.01)
        finally:
            server.run_cli_exec = old  # type: ignore[assignment]

    def test_global_concurrency_limit(self) -> None:
        running = 0
        peak = 0
        lock = threading.Lock()
        started = threading.Event()

        def fake_run(
            _store: object,
            run_id: str,
            timeout_s: object = None,
            cli_type: str = "codex",
            scheduler: object = None,
        ) -> None:
            nonlocal running, peak
            with lock:
                running += 1
                peak = max(peak, running)
            started.set()
            time.sleep(0.08)
            with lock:
                running -= 1

        old = server.run_cli_exec
        server.run_cli_exec = fake_run  # type: ignore[assignment]
        try:
            sched = server.RunScheduler(store=object(), max_concurrency=2)
            # Different sessions => eligible to run concurrently, but capped by max_concurrency.
            for i in range(6):
                sched.enqueue(f"r{i}", f"s{i}")
            self.assertTrue(started.wait(timeout=1.0))
            time.sleep(0.25)
            self.assertLessEqual(peak, 2)
        finally:
            server.run_cli_exec = old  # type: ignore[assignment]

    def test_cancel_queued_run(self) -> None:
        calls: list[str] = []
        lock = threading.Lock()

        def fake_run(
            _store: object,
            run_id: str,
            timeout_s: object = None,
            cli_type: str = "codex",
            scheduler: object = None,
        ) -> None:
            with lock:
                calls.append(run_id)
            time.sleep(0.2)

        old = server.run_cli_exec
        server.run_cli_exec = fake_run  # type: ignore[assignment]
        try:
            sched = server.RunScheduler(store=object(), max_concurrency=2)
            sid = "s1"
            sched.enqueue("cq1", sid)
            sched.enqueue("cq2", sid)
            t0 = time.time()
            while True:
                with lock:
                    if "cq1" in calls:
                        break
                if time.time() - t0 > 1.0:
                    self.fail(f"cq1 not started, calls={calls}")
                time.sleep(0.01)
            removed = sched.cancel_queued_run("cq2", session_id=sid)
            self.assertTrue(removed)
            time.sleep(0.25)
            self.assertEqual([x for x in calls if x.startswith("cq")], ["cq1"])
        finally:
            server.run_cli_exec = old  # type: ignore[assignment]

    def test_retry_waiting_blocks_then_cancel_releases(self) -> None:
        calls: list[str] = []
        lock = threading.Lock()

        def fake_run(
            _store: object,
            run_id: str,
            timeout_s: object = None,
            cli_type: str = "codex",
            scheduler: object = None,
        ) -> None:
            with lock:
                calls.append(run_id)
            time.sleep(0.02)

        class _Store:
            def __init__(self) -> None:
                self.metas = {
                    "rw_wait": {"id": "rw_wait", "status": "retry_waiting"},
                    "rw_next": {"id": "rw_next", "status": "queued"},
                }

            def load_meta(self, rid: str) -> dict:
                return dict(self.metas.get(rid) or {})

            def save_meta(self, rid: str, meta: dict) -> None:
                self.metas[rid] = dict(meta)

        old = server.run_cli_exec
        server.run_cli_exec = fake_run  # type: ignore[assignment]
        try:
            store = _Store()
            sched = server.RunScheduler(store=store, max_concurrency=2)
            due = time.time() + 60
            self.assertTrue(sched.schedule_retry_waiting("rw_wait", "s1", due, cli_type="codex"))
            sched.enqueue("rw_next", "s1")
            time.sleep(0.08)
            self.assertEqual(calls, [])

            removed = sched.cancel_retry_waiting("rw_wait", session_id="s1")
            self.assertTrue(removed)
            time.sleep(0.12)
            self.assertEqual([x for x in calls if x.startswith("rw")], ["rw_next"])
        finally:
            server.run_cli_exec = old  # type: ignore[assignment]

    def test_multiple_retry_waiting_same_session_activate_in_order(self) -> None:
        calls: list[str] = []
        lock = threading.Lock()
        rw1_done = threading.Event()
        rw2_started = threading.Event()

        def fake_run(
            _store: object,
            run_id: str,
            timeout_s: object = None,
            cli_type: str = "codex",
            scheduler: object = None,
        ) -> None:
            with lock:
                calls.append(run_id)
            time.sleep(0.02)
            if run_id == "rw1":
                rw1_done.set()
            if run_id == "rw2":
                rw2_started.set()

        class _Store:
            def __init__(self) -> None:
                self.metas = {
                    "rw1": {"id": "rw1", "status": "retry_waiting"},
                    "rw2": {"id": "rw2", "status": "retry_waiting"},
                }

            def load_meta(self, rid: str) -> dict:
                return dict(self.metas.get(rid) or {})

            def save_meta(self, rid: str, meta: dict) -> None:
                self.metas[rid] = dict(meta)

        old = server.run_cli_exec
        server.run_cli_exec = fake_run  # type: ignore[assignment]
        try:
            store = _Store()
            sched = server.RunScheduler(store=store, max_concurrency=2)
            due = time.time() + 60
            self.assertTrue(sched.schedule_retry_waiting("rw1", "s1", due, cli_type="codex"))
            self.assertTrue(sched.schedule_retry_waiting("rw2", "s1", due + 60, cli_type="codex"))
            self.assertEqual(str(sched._retry_waiting["s1"][0]), "rw1")
            self.assertEqual([item[0] for item in sched._q["s1"]], ["rw2"])

            timer1 = sched._retry_timers.pop("rw1", None)
            if timer1:
                timer1.cancel()
            sched._activate_retry_waiting("s1", "rw1", "codex")
            if not rw1_done.wait(timeout=1.0):
                self.fail(f"rw1 did not complete, calls={calls}")
            self.assertEqual([x for x in calls if x.startswith("rw")], ["rw1"])
            t0 = time.time()
            while True:
                with sched._lock:  # type: ignore[attr-defined]
                    waiting = str((sched._retry_waiting.get("s1") or ("",))[0] or "")  # type: ignore[attr-defined]
                if waiting == "rw2":
                    break
                if time.time() - t0 > 1:
                    self.fail(f"rw2 was not moved to retry_waiting, calls={calls}")
                time.sleep(0.01)

            timer2 = sched._retry_timers.pop("rw2", None)
            if timer2:
                timer2.cancel()
            sched._activate_retry_waiting("s1", "rw2", "codex")
            if not rw2_started.wait(timeout=1.0):
                self.fail(f"rw2 did not start, calls={calls}")
            self.assertEqual([x for x in calls if x.startswith("rw")], ["rw1", "rw2"])
        finally:
            server.run_cli_exec = old  # type: ignore[assignment]

    def test_cancel_pending_retry_waiting_behind_active_wait(self) -> None:
        class _Store:
            def __init__(self) -> None:
                self.metas = {
                    "rw1": {"id": "rw1", "status": "retry_waiting"},
                    "rw2": {"id": "rw2", "status": "retry_waiting"},
                }

            def load_meta(self, rid: str) -> dict:
                return dict(self.metas.get(rid) or {})

            def save_meta(self, rid: str, meta: dict) -> None:
                self.metas[rid] = dict(meta)

        store = _Store()
        sched = server.RunScheduler(store=store, max_concurrency=2)
        due = time.time() + 60
        self.assertTrue(sched.schedule_retry_waiting("rw1", "s1", due, cli_type="codex"))
        self.assertTrue(sched.schedule_retry_waiting("rw2", "s1", due + 60, cli_type="codex"))
        self.assertEqual(str(sched._retry_waiting["s1"][0]), "rw1")
        self.assertEqual([item[0] for item in sched._q["s1"]], ["rw2"])

        removed = sched.cancel_retry_waiting("rw2", session_id="s1")
        self.assertTrue(removed)
        self.assertNotIn("rw2", sched._retry_timers)
        self.assertFalse(bool(sched._q.get("s1")))
        self.assertEqual(str(sched._retry_waiting["s1"][0]), "rw1")

    def test_exception_releases_session_queue(self) -> None:
        calls: list[str] = []
        lock = threading.Lock()

        def fake_run(
            _store: object,
            run_id: str,
            timeout_s: object = None,
            cli_type: str = "codex",
            scheduler: object = None,
        ) -> None:
            with lock:
                calls.append(run_id)
            if run_id == "ex1":
                raise RuntimeError("boom")
            time.sleep(0.02)

        old = server.run_cli_exec
        server.run_cli_exec = fake_run  # type: ignore[assignment]
        try:
            sched = server.RunScheduler(store=object(), max_concurrency=2)
            sid = "s1"
            sched.enqueue("ex1", sid)
            sched.enqueue("ex2", sid)
            t0 = time.time()
            while True:
                with lock:
                    ordered = [x for x in calls if x.startswith("ex")]
                    if ordered == ["ex1", "ex2"]:
                        break
                if time.time() - t0 > 2:
                    self.fail(f"queue not released after exception, calls={calls}")
                time.sleep(0.01)
        finally:
            server.run_cli_exec = old  # type: ignore[assignment]

    def test_heal_stale_running_when_meta_missing(self) -> None:
        calls: list[str] = []
        lock = threading.Lock()

        def fake_run(
            _store: object,
            run_id: str,
            timeout_s: object = None,
            cli_type: str = "codex",
            scheduler: object = None,
        ) -> None:
            with lock:
                calls.append(run_id)
            time.sleep(0.02)

        class _Store:
            def load_meta(self, _rid: str) -> None:
                return None

        old = server.run_cli_exec
        server.run_cli_exec = fake_run  # type: ignore[assignment]
        try:
            sched = server.RunScheduler(store=_Store(), max_concurrency=2)
            # Simulate stale in-memory running slot left by abnormal path.
            with sched._lock:  # type: ignore[attr-defined]
                sched._running["s1"] = "ghost-run"  # type: ignore[attr-defined]
            sched.enqueue("heal2", "s1")
            t0 = time.time()
            while True:
                with lock:
                    if "heal2" in calls:
                        break
                if time.time() - t0 > 2:
                    self.fail(f"stale running slot not healed, calls={calls}")
                time.sleep(0.01)
        finally:
            server.run_cli_exec = old  # type: ignore[assignment]

    def test_urgent_priority_runs_before_normal_queue_items(self) -> None:
        calls: list[str] = []
        lock = threading.Lock()
        n1_started = threading.Event()
        release_n1 = threading.Event()

        def fake_run(
            _store: object,
            run_id: str,
            timeout_s: object = None,
            cli_type: str = "codex",
            scheduler: object = None,
        ) -> None:
            with lock:
                calls.append(run_id)
            if run_id == "n1":
                n1_started.set()
                release_n1.wait(timeout=1.0)
                return
            time.sleep(0.02)

        old = server.run_cli_exec
        server.run_cli_exec = fake_run  # type: ignore[assignment]
        try:
            sched = server.RunScheduler(store=object(), max_concurrency=2)
            sid = "s1"
            sched.enqueue("n1", sid, priority="normal")
            sched.enqueue("n2", sid, priority="normal")
            # n1 running期间，urgent入队应插到队首，保证下一个执行。
            if not n1_started.wait(timeout=1.0):
                self.fail(f"n1 did not start, calls={calls}")
            sched.enqueue("u1", sid, priority="urgent")
            release_n1.set()
            t0 = time.time()
            while True:
                with lock:
                    ordered = [x for x in calls if x in {"n1", "n2", "u1"}]
                    if ordered == ["n1", "u1", "n2"]:
                        break
                if time.time() - t0 > 2:
                    self.fail(f"unexpected priority order: {calls}")
                time.sleep(0.01)
        finally:
            server.run_cli_exec = old  # type: ignore[assignment]

    def test_external_busy_session_keeps_queued_then_dispatches(self) -> None:
        calls: list[str] = []
        lock = threading.Lock()

        def fake_run(
            _store: object,
            run_id: str,
            timeout_s: object = None,
            cli_type: str = "codex",
            scheduler: object = None,
        ) -> None:
            with lock:
                calls.append(run_id)
            time.sleep(0.02)

        class _Store:
            def __init__(self) -> None:
                self.metas = {"busy1": {"id": "busy1", "status": "queued"}}

            def load_meta(self, rid: str) -> dict:
                return dict(self.metas.get(rid) or {})

            def save_meta(self, rid: str, meta: dict) -> None:
                self.metas[rid] = dict(meta)

        state = {"n": 0}

        def fake_session_busy(_session_id: str, cli_type: str = "codex") -> bool:
            state["n"] += 1
            # First dispatch probe sees external session busy; second probe releases.
            return state["n"] == 1

        old_run = server.run_cli_exec
        old_busy = server._scan_session_busy_rows_effective
        server.run_cli_exec = fake_run  # type: ignore[assignment]
        server._scan_session_busy_rows_effective = lambda _store, session_id, cli_type="codex", rows=None: [  # type: ignore[assignment]
            (1, f"busy:{session_id}")
        ] if fake_session_busy(session_id, cli_type=cli_type) else []
        try:
            store = _Store()
            sched = server.RunScheduler(store=store, max_concurrency=1, busy_probe_delay_s=0.2)
            sched.enqueue("busy1", "s-busy")
            time.sleep(0.05)
            with lock:
                self.assertEqual(calls, [])
            self.assertEqual(store.metas["busy1"].get("status"), "queued")
            self.assertEqual(store.metas["busy1"].get("queueReason"), "session_busy_external")

            t0 = time.time()
            while True:
                with lock:
                    if "busy1" in calls:
                        break
                if time.time() - t0 > 2:
                    self.fail(f"run not dispatched after busy released, calls={calls}")
                time.sleep(0.01)
            self.assertNotIn("queueReason", store.metas["busy1"])
            self.assertNotIn("queueReasonAt", store.metas["busy1"])
        finally:
            server.run_cli_exec = old_run  # type: ignore[assignment]
            server._scan_session_busy_rows_effective = old_busy  # type: ignore[assignment]

    def test_external_busy_session_times_out_and_marks_error(self) -> None:
        calls: list[str] = []
        lock = threading.Lock()

        def fake_run(
            _store: object,
            run_id: str,
            timeout_s: object = None,
            cli_type: str = "codex",
            scheduler: object = None,
        ) -> None:
            with lock:
                calls.append(run_id)

        class _Store:
            def __init__(self) -> None:
                self.metas = {"busy_timeout_1": {"id": "busy_timeout_1", "status": "queued"}}

            def load_meta(self, rid: str) -> dict:
                return dict(self.metas.get(rid) or {})

            def save_meta(self, rid: str, meta: dict) -> None:
                self.metas[rid] = dict(meta)

        def fake_session_busy(_session_id: str, cli_type: str = "codex") -> bool:
            return True

        old_run = server.run_cli_exec
        old_busy = server._scan_session_busy_rows_effective
        server.run_cli_exec = fake_run  # type: ignore[assignment]
        server._scan_session_busy_rows_effective = lambda _store, session_id, cli_type="codex", rows=None: [  # type: ignore[assignment]
            (1, f"busy:{session_id}")
        ] if fake_session_busy(session_id, cli_type=cli_type) else []
        try:
            store = _Store()
            sched = server.RunScheduler(store=store, max_concurrency=1, busy_probe_delay_s=0.1, busy_timeout_s=0.3)
            sched.enqueue("busy_timeout_1", "s-busy-timeout")

            t0 = time.time()
            while True:
                meta = store.metas.get("busy_timeout_1") or {}
                if str(meta.get("status") or "").strip().lower() == "error":
                    break
                if time.time() - t0 > 2:
                    self.fail(f"run not timed out from busy queue, meta={meta}")
                time.sleep(0.02)

            meta = store.metas.get("busy_timeout_1") or {}
            self.assertEqual(str(meta.get("queueReason") or ""), "session_busy_timeout")
            self.assertIn("timeout>session_busy_external>", str(meta.get("error") or ""))
            self.assertEqual(calls, [])
        finally:
            server.run_cli_exec = old_run  # type: ignore[assignment]
            server._scan_session_busy_rows_effective = old_busy  # type: ignore[assignment]

    def test_external_busy_session_timeout_marks_error(self) -> None:
        calls: list[str] = []
        lock = threading.Lock()

        def fake_run(
            _store: object,
            run_id: str,
            timeout_s: object = None,
            cli_type: str = "codex",
            scheduler: object = None,
        ) -> None:
            with lock:
                calls.append(run_id)

        class _Store:
            def __init__(self) -> None:
                self.metas = {"busy_to": {"id": "busy_to", "status": "queued"}}

            def load_meta(self, rid: str) -> dict:
                return dict(self.metas.get(rid) or {})

            def save_meta(self, rid: str, meta: dict) -> None:
                self.metas[rid] = dict(meta)

        def always_busy(_session_id: str, cli_type: str = "codex") -> bool:
            return True

        old_run = server.run_cli_exec
        old_busy = server._scan_session_busy_rows_effective
        server.run_cli_exec = fake_run  # type: ignore[assignment]
        server._scan_session_busy_rows_effective = lambda _store, session_id, cli_type="codex", rows=None: [  # type: ignore[assignment]
            (1, f"busy:{session_id}")
        ] if always_busy(session_id, cli_type=cli_type) else []
        try:
            store = _Store()
            sched = server.RunScheduler(
                store=store,
                max_concurrency=1,
                busy_probe_delay_s=0.2,
                busy_timeout_s=1,
            )
            sched.enqueue("busy_to", "s-busy-timeout")
            t0 = time.time()
            while True:
                meta = dict(store.metas.get("busy_to") or {})
                if str(meta.get("status") or "").strip().lower() == "error":
                    break
                if time.time() - t0 > 3:
                    self.fail(f"busy timeout not triggered, meta={meta}")
                time.sleep(0.05)
            self.assertEqual(store.metas["busy_to"].get("queueReason"), "session_busy_timeout")
            self.assertIn("timeout>session_busy_external>", str(store.metas["busy_to"].get("error") or ""))
            with lock:
                self.assertEqual(calls, [])
        finally:
            server.run_cli_exec = old_run  # type: ignore[assignment]
            server._scan_session_busy_rows_effective = old_busy  # type: ignore[assignment]

    def test_terminal_bound_orphan_process_does_not_block_dispatch(self) -> None:
        calls: list[str] = []
        lock = threading.Lock()

        def fake_run(
            _store: object,
            run_id: str,
            timeout_s: object = None,
            cli_type: str = "codex",
            scheduler: object = None,
        ) -> None:
            with lock:
                calls.append(run_id)

        class _Store:
            def __init__(self) -> None:
                self.metas = {
                    "old_terminal": {
                        "id": "old_terminal",
                        "sessionId": "s-orphan",
                        "status": "done",
                        "finishedAt": "2026-03-28T19:32:50+0800",
                        "cliType": "codex",
                    },
                    "new_run": {
                        "id": "new_run",
                        "sessionId": "s-orphan",
                        "status": "queued",
                    },
                }

            def load_meta(self, rid: str) -> dict:
                return dict(self.metas.get(rid) or {})

            def save_meta(self, rid: str, meta: dict) -> None:
                self.metas[rid] = dict(meta)

        fake_rows = [
            (
                44364,
                "/usr/local/bin/codex exec --json -o "
                "/tmp/task-dashboard/.runs/hot/old_terminal.last.txt resume s-orphan hello",
            )
        ]

        old_run = server.run_cli_exec
        server.run_cli_exec = fake_run  # type: ignore[assignment]
        try:
            store = _Store()
            sched = server.RunScheduler(store=store, max_concurrency=1, busy_probe_delay_s=0.1)
            with mock.patch("server._scan_process_table_rows", return_value=fake_rows):
                sched.enqueue("new_run", "s-orphan")
                t0 = time.time()
                while True:
                    with lock:
                        if "new_run" in calls:
                            break
                    if time.time() - t0 > 2:
                        self.fail(f"terminal-bound orphan process still blocked dispatch, calls={calls}")
                    time.sleep(0.01)
            self.assertNotIn("queueReason", store.metas["new_run"])
        finally:
            server.run_cli_exec = old_run  # type: ignore[assignment]
