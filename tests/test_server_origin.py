import os
import unittest
from unittest import mock

from server import _build_local_server_origin


class ServerOriginTests(unittest.TestCase):
    def test_build_local_server_origin_defaults_to_loopback_for_wildcard_bind(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            self.assertEqual(
                _build_local_server_origin("0.0.0.0", 18765),
                "http://127.0.0.1:18765",
            )

    def test_build_local_server_origin_prefers_public_origin_override(self) -> None:
        with mock.patch.dict(
            os.environ,
            {"TASK_DASHBOARD_PUBLIC_ORIGIN": "http://192.168.0.102:18765"},
            clear=False,
        ):
            self.assertEqual(
                _build_local_server_origin("0.0.0.0", 18765),
                "http://192.168.0.102:18765",
            )


if __name__ == "__main__":
    unittest.main()
