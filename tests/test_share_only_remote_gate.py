import unittest

from server import (
    _is_local_client_address,
    _is_loopback_client_address,
    _is_remote_share_only_request_blocked,
)


class ShareOnlyRemoteGateTests(unittest.TestCase):
    def test_loopback_client_detection_supports_ipv4_ipv6_and_mapped_ipv4(self) -> None:
        self.assertTrue(_is_loopback_client_address(("127.0.0.1", 0)))
        self.assertTrue(_is_loopback_client_address(("::1", 0)))
        self.assertTrue(_is_loopback_client_address(("::ffff:127.0.0.1", 0)))
        self.assertFalse(_is_loopback_client_address(("192.168.0.102", 0)))

    def test_local_client_detection_accepts_same_machine_lan_address(self) -> None:
        local_addresses = {"127.0.0.1", "::1", "192.168.0.102"}
        self.assertTrue(_is_local_client_address(("127.0.0.1", 0), local_addresses=local_addresses))
        self.assertTrue(_is_local_client_address(("::1", 0), local_addresses=local_addresses))
        self.assertTrue(_is_local_client_address(("192.168.0.102", 0), local_addresses=local_addresses))
        self.assertFalse(_is_local_client_address(("192.168.0.103", 0), local_addresses=local_addresses))

    def test_non_loopback_request_is_limited_to_share_pages_share_api_and_attachments(self) -> None:
        remote = ("192.168.0.103", 54321)
        local_addresses = {"127.0.0.1", "::1", "192.168.0.102"}

        allowed_cases = [
            ("GET", "/share/project-task-dashboard.html?project_id=task_dashboard&share_id=room-1"),
            ("GET", "/share/project-chat.html?project_id=task_dashboard&share_id=room-1"),
            ("GET", "/share/project-share-space.html?project_id=task_dashboard&share_id=room-1"),
            ("GET", "/api/share-spaces/room-1/bootstrap?project_id=task_dashboard&token=token-1"),
            ("GET", "/api/share-spaces/room-1/sessions/019d1111-1111-7111-8111-111111111111?project_id=task_dashboard&token=token-1"),
            ("POST", "/api/share-spaces/room-1/announce"),
            ("GET", "/.runs/attachments/demo.png"),
        ]
        for method, path in allowed_cases:
            with self.subTest(method=method, path=path):
                self.assertFalse(
                    _is_remote_share_only_request_blocked(
                        remote,
                        method,
                        path,
                        local_addresses=local_addresses,
                    )
                )

        blocked_cases = [
            ("GET", "/__health"),
            ("GET", "/api/codex/runs?projectId=task_dashboard&limit=5"),
            ("GET", "/api/sessions?project_id=task_dashboard"),
            ("GET", "/api/agent-candidates?project_id=task_dashboard"),
            ("GET", "/api/channel-sessions?project_id=task_dashboard&channel_name=子级02"),
            ("POST", "/api/codex/announce"),
            ("GET", "/share/project-overview-dashboard.html"),
            ("GET", "/share/any-other-page.html"),
            ("GET", "/.runs/hot/demo.log.txt"),
        ]
        for method, path in blocked_cases:
            with self.subTest(method=method, path=path):
                self.assertTrue(
                    _is_remote_share_only_request_blocked(
                        remote,
                        method,
                        path,
                        local_addresses=local_addresses,
                    )
                )

    def test_platform_lan_access_allows_full_platform_for_same_lan_client(self) -> None:
        remote = ("192.168.0.103", 54321)
        local_addresses = {"127.0.0.1", "::1", "192.168.0.102"}

        self.assertFalse(
            _is_remote_share_only_request_blocked(
                remote,
                "GET",
                "/api/sessions?project_id=task_dashboard",
                local_addresses=local_addresses,
                platform_lan_access_enabled=True,
            )
        )
        self.assertFalse(
            _is_remote_share_only_request_blocked(
                remote,
                "POST",
                "/api/codex/announce",
                local_addresses=local_addresses,
                platform_lan_access_enabled=True,
            )
        )

    def test_platform_lan_access_does_not_allow_non_lan_client(self) -> None:
        remote = ("8.8.8.8", 54321)
        local_addresses = {"127.0.0.1", "::1", "192.168.0.102"}

        self.assertTrue(
            _is_remote_share_only_request_blocked(
                remote,
                "GET",
                "/api/sessions?project_id=task_dashboard",
                local_addresses=local_addresses,
                platform_lan_access_enabled=True,
            )
        )

    def test_same_machine_lan_request_keeps_ops_surface(self) -> None:
        same_machine_lan = ("192.168.0.102", 54321)
        local_addresses = {"127.0.0.1", "::1", "192.168.0.102"}
        self.assertFalse(
            _is_remote_share_only_request_blocked(
                same_machine_lan,
                "GET",
                "/__health",
                local_addresses=local_addresses,
            )
        )
        self.assertFalse(
            _is_remote_share_only_request_blocked(
                same_machine_lan,
                "GET",
                "/api/codex/runs",
                local_addresses=local_addresses,
            )
        )

    def test_loopback_requests_keep_ops_surface(self) -> None:
        loopback = ("127.0.0.1", 54321)
        self.assertFalse(_is_remote_share_only_request_blocked(loopback, "GET", "/__health"))
        self.assertFalse(_is_remote_share_only_request_blocked(loopback, "GET", "/api/codex/runs"))
        self.assertFalse(_is_remote_share_only_request_blocked(loopback, "POST", "/api/codex/announce"))


if __name__ == "__main__":
    unittest.main()
