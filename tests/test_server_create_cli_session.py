import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from task_dashboard.adapters.base import SessionInfo

import server


_SESSION_ID = "019d6839-8145-7412-b0cf-d1ef6c2dca3a"


class _FakeAdapter:
    session_path = Path("/tmp/fake-session.json")
    scan_calls = 0

    @classmethod
    def get_home_path(cls) -> Path:
        return cls.session_path.parent

    @classmethod
    def build_create_command(cls, **kwargs):
        return ["fake-cli", "exec"]

    @classmethod
    def supports_model(cls) -> bool:
        return False

    @classmethod
    def scan_sessions(cls, after_ts: float = 0.0):
        cls.scan_calls += 1
        if cls.scan_calls == 1:
            return []
        return [SessionInfo(session_id=_SESSION_ID, path=cls.session_path, modified_ts=after_ts + 1.0)]

    @classmethod
    def extract_session_id_from_output(cls, text: str) -> str:
        raw = str(text or "")
        marker = f"session id: {_SESSION_ID}"
        return _SESSION_ID if marker in raw.lower() else ""


class CreateCliSessionTests(unittest.TestCase):
    def test_timeout_recovers_session_id_from_output(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp_root = Path(td)
            _FakeAdapter.session_path = tmp_root / "session.json"
            _FakeAdapter.scan_calls = 0
            with (
                mock.patch("server.get_adapter_or_error", return_value=_FakeAdapter),
                mock.patch(
                    "server.runtime_prepare_process_spawn",
                    return_value={"cmd": ["fake-cli", "exec"], "spawn_cwd": str(tmp_root)},
                ),
                mock.patch("server._find_new_session_id", return_value=("", "")),
                mock.patch(
                    "server.subprocess.run",
                    side_effect=subprocess.TimeoutExpired(
                        cmd=["fake-cli", "exec"],
                        timeout=10,
                        stderr=f"warning\nsession id: {_SESSION_ID}\n",
                    ),
                ),
            ):
                result = server.create_cli_session(
                    seed_prompt="请回复 OK。",
                    timeout_s=10,
                    cli_type="codex",
                    workdir=tmp_root,
                )

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "timeout")
        self.assertEqual(result["sessionId"], _SESSION_ID)
        self.assertEqual(result["sessionPath"], str(_FakeAdapter.session_path))


if __name__ == "__main__":
    unittest.main()
