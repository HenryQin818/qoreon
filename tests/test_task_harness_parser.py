import tempfile
import unittest
from pathlib import Path

from task_dashboard.parser_md import iter_items
from task_dashboard.task_harness import normalize_task_harness_roles
from task_dashboard.task_identity import render_task_front_matter


class TaskHarnessParserTests(unittest.TestCase):
    def test_iter_items_outputs_task_harness_roles_and_management_inheritance(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            task_root = root / "任务规划"
            registry = task_root / "全局资源" / "task-harness-project-registry.task_dashboard.v1.json"
            registry.parent.mkdir(parents=True, exist_ok=True)
            registry.write_text(
                """
{
  "project_id": "task_dashboard",
  "defaults": {
    "inherit_management_slot_to_tasks": true
  },
  "management_slot": {
    "default_members": [
      {
        "name": "总控",
        "channel_name": "主体-总控（合并与验收）",
        "agent_alias": "总控-项目经理",
        "session_id": "019d107a-a5ad-7912-8797-d23c58013449",
        "responsibility": "项目级编排"
      },
      {
        "name": "架构师",
        "channel_name": "子级01-Build引擎（扫描-解析-聚合-渲染）",
        "agent_alias": "架构师",
        "session_id": "019ce5e2-fb66-7420-92e8-5ce0ae2c43b1",
        "responsibility": "结构边界判断"
      }
    ]
  }
}
                """.strip(),
                encoding="utf-8",
            )

            task_file = (
                task_root
                / "子级01-Build引擎（扫描-解析-聚合-渲染）"
                / "任务"
                / "【待开始】【任务】20260330-Task Harness责任位读模型解析与聚合输出实现.md"
            )
            task_file.parent.mkdir(parents=True, exist_ok=True)
            task_file.write_text(
                """
# 【待开始】【任务】20260330-Task Harness责任位读模型解析与聚合输出实现

## Harness责任位
- 主负责位：`架构师`
- 协同位：`产品策划-任务派发`
- 验证位：空
- 质疑位：空
- 备份位：空
- 管理位：继承项目级默认管理位
- 自定义责任位：`读模型实现`
                """.strip(),
                encoding="utf-8",
            )

            items = iter_items(
                root=root,
                project_id="task_dashboard",
                project_name="Task Dashboard",
                task_root_rel="任务规划",
            )
            self.assertEqual(len(items), 1)
            item = items[0]
            self.assertEqual((item.main_owner or {}).get("agent_name"), "架构师")
            self.assertEqual((item.main_owner or {}).get("alias"), "架构师")
            self.assertEqual(len(item.collaborators), 1)
            self.assertEqual(item.collaborators[0].get("agent_name"), "产品策划-任务派发")
            self.assertEqual(item.validators, [])
            self.assertEqual(item.challengers, [])
            self.assertEqual(item.backup_owners, [])
            self.assertEqual(len(item.management_slot), 2)
            self.assertEqual(item.management_slot[0].get("source"), "project_registry")
            self.assertEqual(item.management_slot[0].get("name"), "总控")
            self.assertEqual(item.management_slot[1].get("agent_name"), "架构师")
            self.assertEqual(len(item.custom_roles), 1)
            self.assertEqual(item.custom_roles[0].get("name"), "读模型实现")
            self.assertEqual(item.custom_roles[0].get("source"), "task_doc")
            self.assertEqual(item.executors, item.collaborators)
            self.assertEqual(item.acceptors, [])
            self.assertEqual(len(item.reviewers), 2)
            self.assertEqual(item.reviewers[0].get("name"), "总控")
            self.assertEqual(item.reviewers[1].get("agent_name"), "架构师")
            self.assertEqual(item.visual_reviewers, [])

    def test_normalize_task_harness_roles_projects_additive_fields_from_legacy_roles(self) -> None:
        roles = normalize_task_harness_roles(
            {
                "main_owner": {"agent_name": "产品-任务板块", "source": "task_doc"},
                "collaborators": [{"agent_name": "后端-任务业务", "source": "task_doc"}],
                "validators": [{"agent_name": "测试验收", "source": "task_doc"}],
                "challengers": [],
                "backup_owners": [],
                "management_slot": [{"name": "架构门禁位", "agent_name": "架构师", "source": "task_override"}],
                "custom_roles": [
                    {"name": "用户审核位", "agent_name": "用户镜像", "source": "task_doc"},
                    {"name": "视觉审核位", "agent_name": "视觉验收", "source": "task_doc"},
                    {"name": "读模型实现", "agent_name": "后端-任务业务", "source": "task_doc"},
                ],
            }
        )

        self.assertEqual(roles["collaborators"], [{"agent_name": "后端-任务业务", "source": "task_doc"}])
        self.assertEqual(roles["validators"], [{"agent_name": "测试验收", "source": "task_doc"}])
        self.assertEqual(roles["executors"], roles["collaborators"])
        self.assertEqual(roles["acceptors"], roles["validators"])
        self.assertEqual([row.get("name") for row in roles["reviewers"]], ["架构门禁位", "用户审核位"])
        self.assertEqual([row.get("name") for row in roles["visual_reviewers"]], ["视觉审核位"])

    def test_iter_items_parses_heading_style_harness_roles(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            task_root = root / "任务规划"

            task_file = (
                task_root
                / "辅助04-原型设计与Demo可视化（静态数据填充-业务规格确认）"
                / "任务"
                / "【进行中】【任务】20260331-Task Harness任务列表摘要与详情阅读层升级编排.md"
            )
            task_file.parent.mkdir(parents=True, exist_ok=True)
            task_file.write_text(
                """
# 【进行中】【任务】20260331-Task Harness任务列表摘要与详情阅读层升级编排

## Harness责任位
### 主负责位
- `产品策划-任务派发`
- 通道：`辅助04-原型设计与Demo可视化（静态数据填充-业务规格确认）`
- session_id：`019d3f2e-0958-7a03-b639-ad13aaac6a2a`
- 职责：负责本任务编排。

### 协同位
1. `前端页面-规范策划`
- 通道：`子级04-前端体验（task-overview 页面交互）`
- session_id：`019d0501-11f6-7b73-ab49-ecb47b8b7a93`
- 职责：评估前端可实施范围。

2. `数据治理-任务监控`
- 通道：`子级06-数据治理与契约（规格-校验-修复）`
- session_id：`019d2a61-38e0-72e2-aa87-03e6e5d17209`
- 职责：评估契约边界。
                """.strip(),
                encoding="utf-8",
            )

            items = iter_items(
                root=root,
                project_id="task_dashboard",
                project_name="Task Dashboard",
                task_root_rel="任务规划",
            )
            self.assertEqual(len(items), 1)
            item = items[0]
            self.assertEqual((item.main_owner or {}).get("agent_name"), "产品策划-任务派发")
            self.assertEqual((item.main_owner or {}).get("session_id"), "019d3f2e-0958-7a03-b639-ad13aaac6a2a")
            self.assertEqual((item.main_owner or {}).get("channel_name"), "辅助04-原型设计与Demo可视化（静态数据填充-业务规格确认）")
            self.assertEqual(len(item.collaborators), 2)
            self.assertEqual(item.collaborators[0].get("agent_name"), "前端页面-规范策划")
            self.assertEqual(item.collaborators[1].get("agent_name"), "数据治理-任务监控")

    def test_iter_items_extracts_task_id_and_ignores_front_matter_in_excerpt(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            task_root = root / "任务规划"
            task_file = (
                task_root
                / "子级02-CCB运行时（server-并发-安全-启动）"
                / "任务"
                / "【进行中】【任务】20260331-task_id兼容实现.md"
            )
            task_file.parent.mkdir(parents=True, exist_ok=True)
            task_file.write_text(
                render_task_front_matter(
                    task_id="task_20260331_ab12cd34",
                    parent_task_id="task_parent_01",
                )
                + "# 【进行中】【任务】20260331-task_id兼容实现\n\n"
                + "## 任务目标\n"
                + "- 为运行时补齐稳定身份层。\n",
                encoding="utf-8",
            )

            items = iter_items(
                root=root,
                project_id="task_dashboard",
                project_name="Task Dashboard",
                task_root_rel="任务规划",
            )

            self.assertEqual(len(items), 1)
            item = items[0]
            self.assertEqual(item.task_id, "task_20260331_ab12cd34")
            self.assertEqual(item.parent_task_id, "task_parent_01")
            self.assertNotIn("task_id:", item.excerpt)
            self.assertEqual(item.title, "【进行中】【任务】20260331-task_id兼容实现")


if __name__ == "__main__":
    unittest.main()
