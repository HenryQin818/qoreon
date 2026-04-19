import base64
import io
import unittest

from task_dashboard.runtime.realtime_session_gateway import write_snapshot_websocket_response


class _FakeHandler:
    def __init__(self, *, upgrade: bool) -> None:
        self.headers = {}
        if upgrade:
            self.headers = {
                "Upgrade": "websocket",
                "Connection": "Upgrade",
                "Sec-WebSocket-Key": base64.b64encode(b"test-key-1234567").decode("ascii"),
                "Sec-WebSocket-Version": "13",
            }
        self.status = 0
        self.reason = ""
        self.response_headers: list[tuple[str, str]] = []
        self.wfile = io.BytesIO()

    def send_response(self, status: int, reason: str = "") -> None:
        self.status = status
        self.reason = reason

    def send_header(self, key: str, value: str) -> None:
        self.response_headers.append((key, value))

    def end_headers(self) -> None:
        return None


class RealtimeSessionGatewayTests(unittest.TestCase):
    def test_gateway_returns_hint_without_websocket_upgrade(self) -> None:
        handled, code, payload = write_snapshot_websocket_response(
            _FakeHandler(upgrade=False),
            project_id="task_dashboard",
            session_id="019d684a-cbb6-7eb3-b95b-7ec9c30ecfd3",
            projection={"last_seq": 42},
        )
        self.assertFalse(handled)
        self.assertEqual(code, 200)
        hint = payload.get("realtime") or {}
        self.assertEqual(hint.get("transport"), "websocket")
        self.assertEqual(hint.get("after_seq"), 42)

    def test_gateway_writes_snapshot_websocket_frames(self) -> None:
        handler = _FakeHandler(upgrade=True)
        handled, code, payload = write_snapshot_websocket_response(
            handler,
            project_id="task_dashboard",
            session_id="019d684a-cbb6-7eb3-b95b-7ec9c30ecfd3",
            projection={"last_seq": 42, "items": []},
        )
        self.assertTrue(handled)
        self.assertEqual(code, 101)
        self.assertEqual(handler.status, 101)
        self.assertEqual(handler.reason, "Switching Protocols")
        self.assertIn(("Upgrade", "websocket"), handler.response_headers)
        self.assertTrue(handler.wfile.getvalue().startswith(b"\x81"))
        self.assertIn(b"session.snapshot", handler.wfile.getvalue())
        self.assertEqual(payload.get("event"), "session.snapshot")


if __name__ == "__main__":
    unittest.main()
