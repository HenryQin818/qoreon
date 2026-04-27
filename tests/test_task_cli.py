import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from task_dashboard import task_cli
from task_dashboard.task_harness import parse_task_harness


SESSION_ID_OWNER = "019da4c6-9cdf-7453-b068-299fe16f0d5c"
SESSION_ID_EXECUTOR = "019d8f23-3ac2-7ac2-934e-53e3507d3118"
SESSION_ID_VALIDATOR = "019d2329-4e78-7152-bae2-fbcddadb32df"


def _write_config(root: Path) -> None:
    (root / "config.toml").write_text(
        """
version = 1

[[projects]]
id = "task_dashboard"
name = "Task Dashboard"
project_root_rel = "."
task_root_rel = "任务规划"

[[projects.channels]]
name = "辅助04-原型设计与Demo可视化（静态数据填充-业务规格确认）"

[[projects.channels]]
name = "子级02-CCB运行时（server-并发-安全-启动）"

[[projects.channels]]
name = "子级08-测试与验收（功能-回归-发布）"
        """.strip(),
        encoding="utf-8",
    )


def _write_sessions(root: Path) -> None:
    sessions_dir = root / ".runtime" / "stable" / ".sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "project_id": "task_dashboard",
        "sessions": [
            {
                "id": SESSION_ID_OWNER,
                "channel_name": "辅助04-原型设计与Demo可视化（静态数据填充-业务规格确认）",
                "alias": "产品-任务板块",
                "agent_name": "产品-任务板块",
                "is_primary": True,
                "is_deleted": False,
                "last_used_at": "2026-04-27T00:00:00Z",
            },
            {
                "id": SESSION_ID_EXECUTOR,
                "channel_name": "子级02-CCB运行时（server-并发-安全-启动）",
                "alias": "后端-任务业务",
                "agent_name": "后端-任务业务",
                "is_primary": True,
                "is_deleted": False,
                "last_used_at": "2026-04-27T00:00:00Z",
            },
            {
                "id": SESSION_ID_VALIDATOR,
                "channel_name": "子级08-测试与验收（功能-回归-发布）",
                "alias": "测试验收",
                "agent_name": "测试验收",
                "is_primary": True,
                "is_deleted": False,
                "last_used_at": "2026-04-27T00:00:00Z",
            },
        ],
    }
    (sessions_dir / "task_dashboard.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


class TaskCliTests(unittest.TestCase):
    def test_create_writes_parseable_task_with_owner_from_session_store(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write_config(root)
            _write_sessions(root)
            out_path = (
                root
                / "任务规划"
                / "辅助04-原型设计与Demo可视化（静态数据填充-业务规格确认）"
                / "任务"
                / "【待开始】【任务】20260427-样例任务.md"
            )

            with redirect_stdout(io.StringIO()):
                rc = task_cli.main(
                    [
                        "--root",
                        str(root),
                        "create",
                        "--title",
                        "样例任务",
                        "--stage",
                        "draft",
                        "--owner-agent",
                        "产品-任务板块",
                        "--output",
                        str(out_path),
                    ]
                )

            self.assertEqual(rc, 0)
            markdown = out_path.read_text(encoding="utf-8")
            harness = parse_task_harness(
                root=root,
                task_root_rel="任务规划",
                project_id="task_dashboard",
                item_type="任务",
                markdown=markdown,
            )
            self.assertEqual((harness.get("main_owner") or {}).get("agent_name"), "产品-任务板块")
            self.assertEqual((harness.get("main_owner") or {}).get("session_id"), SESSION_ID_OWNER)

    def test_create_task_from_payload_writes_only_through_safe_call_layer(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write_config(root)
            _write_sessions(root)
            out_path = (
                root
                / "任务规划"
                / "辅助04-原型设计与Demo可视化（静态数据填充-业务规格确认）"
                / "任务"
                / "【待开始】【任务】20260427-api创建样例.md"
            )

            code, payload = task_cli.create_task_from_payload(
                root=root,
                project_id="task_dashboard",
                payload={
                    "title": "api创建样例",
                    "stage": "draft",
                    "owner": {"agentName": "产品-任务板块"},
                    "executor": {"agentName": "后端-任务业务"},
                    "validator": {"agentName": "测试验收"},
                    "outputPath": str(out_path),
                },
            )

            self.assertEqual(code, 201)
            self.assertTrue(payload.get("ok"))
            self.assertTrue(out_path.exists())
            self.assertEqual(payload.get("path"), "任务规划/辅助04-原型设计与Demo可视化（静态数据填充-业务规格确认）/任务/【待开始】【任务】20260427-api创建样例.md")
            self.assertEqual(payload.get("safety", {}).get("direct_page_write_allowed"), False)
            parsed_roles = payload.get("parsed_roles", {})
            self.assertEqual((parsed_roles.get("main_owner") or {}).get("session_id"), SESSION_ID_OWNER)
            self.assertEqual(parsed_roles.get("executors", [{}])[0].get("session_id"), SESSION_ID_EXECUTOR)
            self.assertEqual(parsed_roles.get("acceptors", [{}])[0].get("session_id"), SESSION_ID_VALIDATOR)

            validate_code, validate_payload = task_cli.validate_task_from_payload(
                root=root,
                project_id="task_dashboard",
                payload={"path": str(out_path), "stage": "draft"},
            )
            self.assertEqual(validate_code, 200)
            self.assertTrue(validate_payload.get("ok"))

    def test_create_task_from_payload_blocks_dispatch_without_announce_run_id(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write_config(root)
            _write_sessions(root)
            out_path = (
                root
                / "任务规划"
                / "子级02-CCB运行时（server-并发-安全-启动）"
                / "任务"
                / "【进行中】【任务】20260427-未派发阻断样例.md"
            )

            code, payload = task_cli.create_task_from_payload(
                root=root,
                project_id="task_dashboard",
                payload={
                    "title": "未派发阻断样例",
                    "stage": "dispatch",
                    "owner": {"agentName": "产品-任务板块"},
                    "executor": {"agentName": "后端-任务业务"},
                    "outputPath": str(out_path),
                },
            )

            self.assertEqual(code, 422)
            self.assertFalse(payload.get("ok"))
            self.assertFalse(out_path.exists())
            gaps = payload.get("validation", {}).get("gaps") or []
            self.assertTrue(any(gap.get("code") == "missing_announce_run_id" for gap in gaps))

    def test_create_task_from_payload_rejects_output_path_outside_task_root(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write_config(root)
            _write_sessions(root)
            outside = root / "outside.md"

            code, payload = task_cli.create_task_from_payload(
                root=root,
                project_id="task_dashboard",
                payload={
                    "title": "越界样例",
                    "stage": "draft",
                    "owner": {"agentName": "产品-任务板块"},
                    "outputPath": str(outside),
                },
            )

            self.assertEqual(code, 400)
            self.assertEqual(payload.get("error"), "output_path_outside_task_root")
            self.assertFalse(outside.exists())

    def test_create_review_stage_reports_missing_gate_fields_without_blocking_creation(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write_config(root)
            _write_sessions(root)
            out_path = root / "任务规划" / "辅助04-原型设计与Demo可视化（静态数据填充-业务规格确认）" / "任务" / "【待开始】【任务】20260427-评审样例.md"

            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = task_cli.main(
                    [
                        "--root",
                        str(root),
                        "create",
                        "--title",
                        "评审样例",
                        "--stage",
                        "review",
                        "--owner-agent",
                        "产品-任务板块",
                        "--output",
                        str(out_path),
                    ]
                )

            self.assertEqual(rc, 0)
            self.assertTrue(out_path.exists())
            self.assertIn("WARNING", buf.getvalue())

    def test_validate_dispatch_requires_executor_session_and_announce_run_id(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write_config(root)
            task_path = root / "任务规划" / "子级02-CCB运行时（server-并发-安全-启动）" / "任务" / "【进行中】【任务】20260427-缺派发证据.md"
            task_path.parent.mkdir(parents=True, exist_ok=True)
            task_path.write_text(
                """
# 【进行中】【任务】20260427-缺派发证据

## Harness责任位
### 主负责位
- `产品-任务板块`
- session_id：`019da4c6-9cdf-7453-b068-299fe16f0d5c`

### 协同位
- `后端-任务业务`
                """.strip(),
                encoding="utf-8",
            )

            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = task_cli.main(["--root", str(root), "validate", "--path", str(task_path), "--stage", "dispatch"])

            self.assertEqual(rc, 1)
            output = buf.getvalue()
            self.assertIn("执行位", output)
            self.assertIn("announce_run_id", output)

    def test_validate_dispatch_passes_with_executor_session_and_announce_run_id(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write_config(root)
            task_path = root / "任务规划" / "子级02-CCB运行时（server-并发-安全-启动）" / "任务" / "【进行中】【任务】20260427-派发证据齐全.md"
            task_path.parent.mkdir(parents=True, exist_ok=True)
            task_path.write_text(
                f"""
# 【进行中】【任务】20260427-派发证据齐全

## Harness责任位
### 主负责位
- `产品-任务板块`
- session_id：`{SESSION_ID_OWNER}`

### 协同位
1. `后端-任务业务`
- Agent：`后端-任务业务`
- session_id：`{SESSION_ID_EXECUTOR}`

## 当前推进留痕
announce_run_id=20260427-005446-7dcf0ef9
                """.strip(),
                encoding="utf-8",
            )

            with redirect_stdout(io.StringIO()):
                rc = task_cli.main(["--root", str(root), "validate", "--path", str(task_path), "--stage", "dispatch"])

            self.assertEqual(rc, 0)

    def test_validate_acceptance_requires_real_evidence_path(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write_config(root)
            task_path = root / "任务规划" / "子级08-测试与验收（功能-回归-发布）" / "任务" / "【待验收】【任务】20260427-缺验证据.md"
            task_path.parent.mkdir(parents=True, exist_ok=True)
            task_path.write_text(
                f"""
# 【待验收】【任务】20260427-缺验证据

## Harness责任位
### 主负责位
- `产品-任务板块`
- session_id：`{SESSION_ID_OWNER}`

### 验证位
1. `测试验收`
- Agent：`测试验收`
- session_id：`{SESSION_ID_VALIDATOR}`

## 验收口径
- 按冻结口径验收。

## 验收证据
待补
                """.strip(),
                encoding="utf-8",
            )

            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = task_cli.main(["--root", str(root), "validate", "--path", str(task_path), "--stage", "acceptance"])

            self.assertEqual(rc, 1)
            self.assertIn("证据路径", buf.getvalue())

    def test_scan_active_only_fails_for_active_task_without_main_owner(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write_config(root)
            task_path = root / "任务规划" / "子级02-CCB运行时（server-并发-安全-启动）" / "任务" / "【待开始】【任务】20260427-缺主负责.md"
            task_path.parent.mkdir(parents=True, exist_ok=True)
            task_path.write_text(
                """
# 【待开始】【任务】20260427-缺主负责

## Harness责任位
- 主负责位：空
                """.strip(),
                encoding="utf-8",
            )

            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = task_cli.main(["--root", str(root), "scan", "--active-only"])

            self.assertEqual(rc, 1)
            self.assertIn("缺少主负责位", buf.getvalue())

    def test_scan_json_outputs_gap_groups_and_same_source_roles(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write_config(root)
            task_dir = root / "任务规划" / "子级02-CCB运行时（server-并发-安全-启动）" / "任务"
            task_dir.mkdir(parents=True, exist_ok=True)
            missing_owner = task_dir / "【待开始】【任务】20260427-缺主负责.md"
            missing_owner.write_text(
                """
# 【待开始】【任务】20260427-缺主负责

## Harness责任位
- 主负责位：空
                """.strip(),
                encoding="utf-8",
            )
            dispatch_gap = task_dir / "【进行中】【任务】20260427-缺执行位session.md"
            dispatch_gap.write_text(
                f"""
# 【进行中】【任务】20260427-缺执行位session

## Harness责任位
### 主负责位
- `产品-任务板块`
- session_id：`{SESSION_ID_OWNER}`

### 协同位
1. `后端-任务业务`
- Agent：`后端-任务业务`
                """.strip(),
                encoding="utf-8",
            )

            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = task_cli.main(["--root", str(root), "scan", "--active-only", "--format", "json"])

            self.assertEqual(rc, 1)
            payload = json.loads(buf.getvalue())
            self.assertEqual(payload.get("schema_version"), "task_cli.scan.v1")
            self.assertEqual(payload.get("summary", {}).get("task_count"), 2)
            self.assertEqual(payload.get("summary", {}).get("missing_group_counts", {}).get("main_owner"), 1)
            self.assertEqual(payload.get("summary", {}).get("missing_group_counts", {}).get("collaborators"), 1)
            items = {item["path"]: item for item in payload.get("items", [])}
            dispatch_item = next(item for path, item in items.items() if path.endswith("缺执行位session.md"))
            self.assertEqual(dispatch_item.get("stage"), "dispatch")
            self.assertIn("collaborators", dispatch_item.get("role_missing_groups") or [])
            self.assertEqual(
                dispatch_item.get("parsed_roles", {}).get("collaborators", [{}])[0].get("agent_name"),
                "后端-任务业务",
            )
            parsed_roles = dispatch_item.get("parsed_roles", {})
            self.assertEqual(parsed_roles.get("executors", [{}])[0].get("agent_name"), "后端-任务业务")
            self.assertEqual(parsed_roles.get("acceptors"), [])
            self.assertEqual(parsed_roles.get("reviewers"), [])
            self.assertEqual(parsed_roles.get("visual_reviewers"), [])


if __name__ == "__main__":
    unittest.main()
