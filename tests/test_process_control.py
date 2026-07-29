import signal
import unittest
from unittest import mock

from task_dashboard.runtime import process_control


class _FakeProc:
    def __init__(self, *, pid: int | None = None, running: bool = True) -> None:
        if pid is not None:
            self.pid = pid
        self.running = running
        self.terminated = False
        self.killed = False

    def poll(self):  # noqa: ANN001
        return None if self.running else 0

    def terminate(self) -> None:
        self.terminated = True
        self.running = False

    def kill(self) -> None:
        self.killed = True
        self.running = False


class _CommunicatingProc(_FakeProc):
    def __init__(self, *, returncode: int = 0) -> None:
        super().__init__(pid=4321, running=True)
        self.returncode = returncode

    def communicate(self, timeout=None):  # noqa: ANN001
        self.running = False
        return "stdout", "stderr"


class TestProcessControl(unittest.TestCase):
    def test_posix_spawn_uses_dedicated_session(self) -> None:
        with mock.patch.object(process_control.os, "name", "posix"):
            self.assertEqual(process_control.process_group_spawn_kwargs(), {"start_new_session": True})

    def test_graceful_group_cleanup_sends_term_then_kill(self) -> None:
        proc = _FakeProc(pid=4321)
        with mock.patch.object(process_control.os, "name", "posix"):
            process_control.mark_process_group(proc)
            with mock.patch.object(process_control.os, "killpg") as killpg:
                with mock.patch.object(process_control.time, "sleep"):
                    ok = process_control.terminate_process_tree(proc, graceful=True)

        self.assertTrue(ok)
        self.assertEqual(
            killpg.call_args_list,
            [mock.call(4321, signal.SIGTERM), mock.call(4321, signal.SIGKILL)],
        )
        self.assertFalse(proc.terminated)
        self.assertFalse(proc.killed)

    def test_force_group_cleanup_sends_kill_only(self) -> None:
        proc = _FakeProc(pid=4321)
        with mock.patch.object(process_control.os, "name", "posix"):
            process_control.mark_process_group(proc)
            with mock.patch.object(process_control.os, "killpg") as killpg:
                ok = process_control.terminate_process_tree(proc, graceful=False)

        self.assertTrue(ok)
        killpg.assert_called_once_with(4321, signal.SIGKILL)

    def test_fake_process_without_group_uses_direct_fallback(self) -> None:
        proc = _FakeProc()
        with mock.patch.object(process_control.os, "name", "posix"):
            with mock.patch.object(process_control.time, "sleep"):
                ok = process_control.terminate_process_tree(proc, graceful=True)

        self.assertTrue(ok)
        self.assertTrue(proc.terminated)
        self.assertFalse(proc.killed)

    def test_short_lived_retry_uses_group_and_cleans_descendants(self) -> None:
        proc = _CommunicatingProc(returncode=0)
        with mock.patch.object(process_control.subprocess, "Popen", return_value=proc) as popen:
            with mock.patch.object(process_control, "terminate_process_tree", return_value=True) as cleanup:
                with mock.patch.object(process_control.os, "name", "posix"):
                    result = process_control.run_process_in_group(
                        ["fake-cli"],
                        cwd="/tmp",
                        capture_output=True,
                        text=True,
                        timeout=10,
                        env={},
                    )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "stdout")
        self.assertTrue(popen.call_args.kwargs.get("start_new_session"))
        cleanup.assert_called_once_with(proc, graceful=True, sleep_s=0.05)


if __name__ == "__main__":
    unittest.main()
