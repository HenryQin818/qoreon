import os
import unittest
from unittest import mock

from server import _build_local_server_origin, _build_public_server_origin

LOCAL_ORIGIN = "http://127.0.0.1:" + "18765"


class ServerOriginTests(unittest.TestCase):
    def test_build_local_server_origin_uses_loopback_for_wildcard_bind(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False), mock.patch(
            "server._preferred_local_server_host",
            return_value="192.168.6.25",
        ):
            self.assertEqual(
                _build_local_server_origin("0.0.0.0", 18765),
                LOCAL_ORIGIN,
            )

    def test_build_local_server_origin_ignores_public_origin_override(self) -> None:
        with mock.patch.dict(
            os.environ,
            {"TASK_DASHBOARD_PUBLIC_ORIGIN": "http://192.168.6.25:18765"},
            clear=False,
        ):
            self.assertEqual(
                _build_local_server_origin("0.0.0.0", 18765),
                LOCAL_ORIGIN,
            )

    def test_build_public_server_origin_defaults_to_current_lan_for_wildcard_bind(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False), mock.patch(
            "server._preferred_local_server_host",
            return_value="192.168.6.25",
        ):
            self.assertEqual(
                _build_public_server_origin("0.0.0.0", 18765),
                "http://192.168.6.25:18765",
            )

    def test_build_public_server_origin_keeps_current_local_public_origin_override(self) -> None:
        with mock.patch.dict(
            os.environ,
            {"TASK_DASHBOARD_PUBLIC_ORIGIN": "http://192.168.6.25:18765"},
            clear=False,
        ), mock.patch(
            "server._local_client_addresses",
            return_value={"127.0.0.1", "::1", "192.168.6.25"},
        ):
            self.assertEqual(
                _build_public_server_origin("0.0.0.0", 18765),
                "http://192.168.6.25:18765",
            )

    def test_build_public_server_origin_refreshes_stale_private_public_origin(self) -> None:
        with mock.patch.dict(
            os.environ,
            {"TASK_DASHBOARD_PUBLIC_ORIGIN": "http://192.168.0.102:18765"},
            clear=False,
        ), mock.patch(
            "server._local_client_addresses",
            return_value={"127.0.0.1", "::1", "192.168.6.25"},
        ), mock.patch(
            "server._preferred_local_server_host",
            return_value="192.168.6.25",
        ):
            self.assertEqual(
                _build_public_server_origin("0.0.0.0", 18765),
                "http://192.168.6.25:18765",
            )

    def test_build_public_server_origin_preserves_explicit_domain_override(self) -> None:
        with mock.patch.dict(
            os.environ,
            {"TASK_DASHBOARD_PUBLIC_ORIGIN": "https://openclawbridge.work"},
            clear=False,
        ):
            self.assertEqual(
                _build_public_server_origin("0.0.0.0", 18765),
                "https://openclawbridge.work",
            )


if __name__ == "__main__":
    unittest.main()
