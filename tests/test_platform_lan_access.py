import json
import tempfile
import unittest
from pathlib import Path

from task_dashboard.runtime.platform_lan_access import (
    CONFIG_REL_PATH,
    build_state,
    config_path,
    is_trusted_lan_client_address,
    load_config,
    save_config,
    update_response,
)


class PlatformLanAccessTests(unittest.TestCase):
    def test_default_config_is_disabled_and_runtime_local(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime_base = Path(tmp)
            self.assertEqual(config_path(runtime_base), runtime_base.resolve() / CONFIG_REL_PATH)
            self.assertFalse(load_config(runtime_base)["enabled"])

    def test_save_and_load_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime_base = Path(tmp)
            saved = save_config(runtime_base, enabled=True, updated_by="unit-test")
            loaded = load_config(runtime_base)
            self.assertTrue(saved["enabled"])
            self.assertTrue(loaded["enabled"])
            self.assertEqual(loaded["updatedBy"], "unit-test")
            self.assertTrue((runtime_base / CONFIG_REL_PATH).exists())

    def test_state_reports_enable_requires_restart_when_bound_to_loopback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime_base = Path(tmp)
            save_config(runtime_base, enabled=True, updated_by="unit-test")
            state = build_state(
                runtime_base_dir=runtime_base,
                current_bind="127.0.0.1",
                port=18770,
                local_origin="http://localhost:18770",
                public_origin="http://192.168.0.102:18770",
                local_addresses={"127.0.0.1", "192.168.0.102"},
            )
            self.assertTrue(state["enabled"])
            self.assertFalse(state["effectiveEnabled"])
            self.assertTrue(state["requiresRestart"])
            self.assertEqual(state["listen"]["desiredBind"], "0.0.0.0")

    def test_state_reports_disable_requires_restart_when_bound_to_wildcard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime_base = Path(tmp)
            state = build_state(
                runtime_base_dir=runtime_base,
                current_bind="0.0.0.0",
                port=18770,
                local_origin="http://localhost:18770",
                public_origin="http://192.168.0.102:18770",
                local_addresses={"127.0.0.1", "192.168.0.102"},
            )
            self.assertFalse(state["enabled"])
            self.assertFalse(state["effectiveEnabled"])
            self.assertTrue(state["requiresRestart"])
            self.assertEqual(state["listen"]["desiredBind"], "127.0.0.1")

    def test_update_response_writes_config_and_returns_restart_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime_base = Path(tmp)
            code, payload = update_response(
                runtime_base_dir=runtime_base,
                payload={"enabled": True},
                current_bind="127.0.0.1",
                port=18770,
                local_origin="http://localhost:18770",
                public_origin="http://192.168.0.102:18770",
                local_addresses={"127.0.0.1", "192.168.0.102"},
                updated_by="unit-test",
            )
            self.assertEqual(code, 200)
            self.assertTrue(payload["enabled"])
            self.assertTrue(payload["requiresRestart"])
            data = json.loads((runtime_base / CONFIG_REL_PATH).read_text(encoding="utf-8"))
            self.assertTrue(data["enabled"])

    def test_trusted_lan_client_requires_same_private_subnet(self) -> None:
        local_addresses = {"127.0.0.1", "192.168.0.102"}
        self.assertTrue(
            is_trusted_lan_client_address(
                ("192.168.0.103", 54321),
                local_addresses=local_addresses,
            )
        )
        self.assertFalse(
            is_trusted_lan_client_address(
                ("192.168.1.103", 54321),
                local_addresses=local_addresses,
            )
        )
        self.assertFalse(
            is_trusted_lan_client_address(
                ("8.8.8.8", 54321),
                local_addresses=local_addresses,
            )
        )


if __name__ == "__main__":
    unittest.main()
