import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import server

from task_dashboard.routes.main import RouteDispatcher
from task_dashboard.runtime.project_resources import (
    ProjectResourceStore,
    project_resources_store_path,
)


def _json_response(handler, status, payload):
    handler.status = status
    handler.payload = payload


class ProjectResourcesApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._old_registry = os.environ.get("TASK_DASHBOARD_RESOURCE_REGISTRY")

    def tearDown(self) -> None:
        if self._old_registry is None:
            os.environ.pop("TASK_DASHBOARD_RESOURCE_REGISTRY", None)
        else:
            os.environ["TASK_DASHBOARD_RESOURCE_REGISTRY"] = self._old_registry

    def test_project_resource_store_crud_is_project_isolated(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            store = ProjectResourceStore(base, environment_name="stable")

            first = store.create(
                "task_dashboard",
                {
                    "title": "需求说明",
                    "type": "doc_page",
                    "url": "docs/spec.md",
                    "note": "v1",
                    "source": "message_quick_add",
                },
            )
            other = store.create("qoreon_v2", {"title": "外部服务", "type": "service", "url": "http://127.0.0.1:65530"})

            self.assertEqual("task_dashboard", first["project_id"])
            self.assertEqual("qoreon_v2", other["project_id"])
            self.assertTrue(project_resources_store_path(base, "stable", "task_dashboard").exists())
            self.assertTrue(project_resources_store_path(base, "stable", "qoreon_v2").exists())
            self.assertEqual(1, store.list("task_dashboard")["count"])
            self.assertEqual(1, store.list("qoreon_v2")["count"])

            patched = store.update("task_dashboard", first["id"], {"title": "需求说明-改", "sort_order": 3})
            self.assertIsNotNone(patched)
            self.assertEqual("需求说明-改", patched["title"])
            self.assertEqual(3, patched["sort_order"])

            deleted, count = store.delete("task_dashboard", first["id"])
            self.assertTrue(deleted)
            self.assertEqual(0, count)
            self.assertEqual(0, store.list("task_dashboard")["count"])
            self.assertEqual(1, store.list("qoreon_v2")["count"])

    def test_field_cleaning_limits_and_invalid_type(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = ProjectResourceStore(Path(td), environment_name="stable")
            item = store.create(
                "../escape",
                {
                    "title": "标题" * 200,
                    "type": "doc_page",
                    "url": "https://example.test/page.html\x00",
                    "note": "备注" * 2000,
                    "source": "unknown_source",
                    "sort_order": 9_999_999,
                },
            )

            self.assertLessEqual(len(item["title"]), 240)
            self.assertLessEqual(len(item["note"]), 2000)
            self.assertNotIn("\x00", item["url"])
            self.assertEqual("manual", item["source"])
            self.assertEqual(1_000_000, item["sort_order"])
            path = store.path_for_project("../escape").resolve()
            self.assertEqual((Path(td) / ".runtime" / "stable" / ".resources").resolve(), path.parent)

            with self.assertRaises(ValueError):
                store.create("task_dashboard", {"title": "Bad", "type": "binary", "url": "x"})

    def test_delete_only_removes_list_item_not_target_file(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            real_file = base / "deliverable.md"
            real_file.write_text("keep", encoding="utf-8")
            store = ProjectResourceStore(base, environment_name="stable")
            item = store.create("task_dashboard", {"title": "交付物", "type": "doc_page", "url": str(real_file)})

            deleted, count = store.delete("task_dashboard", item["id"])

            self.assertTrue(deleted)
            self.assertEqual(0, count)
            self.assertTrue(real_file.exists())
            self.assertEqual("keep", real_file.read_text(encoding="utf-8"))

    def test_service_status_unknown_when_registry_has_no_match(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            registry = base / "missing-registry.json"
            os.environ["TASK_DASHBOARD_RESOURCE_REGISTRY"] = str(registry)
            store = ProjectResourceStore(base, environment_name="stable")
            store.create("task_dashboard", {"title": "未登记服务", "type": "service", "url": "http://127.0.0.1:65530"})

            item = store.list("task_dashboard")["items"][0]

            self.assertEqual("unknown", item["service_status"]["state"])
            self.assertEqual("未知", item["service_status"]["label"])
            self.assertEqual("not_found", item["service_status"]["source"])

    def test_service_status_reads_configured_registry_without_writing_it(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            registry = base / "service-registry.json"
            payload = {
                "version": 1,
                "services": {
                    "demo-service": {
                        "id": "demo-service",
                        "name": "Demo 服务",
                        "url": "http://127.0.0.1:45678",
                        "pid": os.getpid(),
                        "updated_at": "2026-07-01T12:00:00+0800",
                    }
                },
            }
            registry.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            before = registry.read_text(encoding="utf-8")
            os.environ["TASK_DASHBOARD_RESOURCE_REGISTRY"] = str(registry)
            store = ProjectResourceStore(base, environment_name="stable")
            store.create("task_dashboard", {"title": "Demo 服务", "type": "service", "url": "http://127.0.0.1:45678"})

            item = store.list("task_dashboard")["items"][0]

            self.assertEqual("up", item["service_status"]["state"])
            self.assertEqual("Demo 服务", item["service_status"]["service_name"])
            self.assertNotIn("registry_path", item["service_status"])
            self.assertEqual(before, registry.read_text(encoding="utf-8"))

    def test_routes_dispatch_get_post_patch_delete(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            body_holder = {
                "body": {
                    "title": "成果页",
                    "type": "doc_page",
                    "url": "dist/result.html",
                    "source": "manual",
                }
            }
            ctx = SimpleNamespace(
                require_token=lambda: True,
                read_body_json=lambda _handler, max_bytes=0: body_holder["body"],
                json_response=_json_response,
                worktree_root=Path(td),
                environment_name="stable",
            )
            dispatcher = RouteDispatcher(ctx)

            handler = SimpleNamespace(path="/api/projects/task_dashboard/resources", status=None, payload=None)
            self.assertTrue(dispatcher.dispatch_post(handler))
            self.assertEqual(200, handler.status)
            resource_id = handler.payload["item"]["id"]

            get_handler = SimpleNamespace(path="/api/projects/task_dashboard/resources", status=None, payload=None)
            self.assertTrue(dispatcher.dispatch_get(get_handler))
            self.assertEqual(200, get_handler.status)
            self.assertEqual(1, get_handler.payload["count"])

            body_holder["body"] = {"title": "成果页-编辑", "note": "已确认"}
            patch_handler = SimpleNamespace(path=f"/api/projects/task_dashboard/resources/{resource_id}", status=None, payload=None)
            self.assertTrue(dispatcher.dispatch_patch(patch_handler))
            self.assertEqual(200, patch_handler.status)
            self.assertEqual("成果页-编辑", patch_handler.payload["item"]["title"])

            delete_handler = SimpleNamespace(path=f"/api/projects/task_dashboard/resources/{resource_id}", status=None, payload=None)
            self.assertTrue(dispatcher.dispatch_delete(delete_handler))
            self.assertEqual(200, delete_handler.status)
            self.assertTrue(delete_handler.payload["deleted"])


if __name__ == "__main__":
    unittest.main()
