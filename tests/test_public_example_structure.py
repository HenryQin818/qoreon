import json
import unittest
from pathlib import Path


class PublicExampleStructureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[1]
        self.seed_root = self.repo_root / "examples" / "minimal-project" / "seed"

    def _load(self, name: str) -> dict:
        return json.loads((self.seed_root / name).read_text(encoding="utf-8"))

    def test_recommended_channel_structure_is_present(self) -> None:
        payload = self._load("channels_seed.json")
        names = [str(item.get("name") or "") for item in payload.get("channels") or [] if isinstance(item, dict)]
        expected = [
            "主体-总控",
            "辅助01-架构与结构治理",
            "子级01-运行时与后端",
            "子级02-前端与交互",
            "子级03-数据与契约",
            "子级04-测试与验收",
            "辅助02-文档与知识沉淀",
            "辅助03-用户镜像与业务判断",
            "辅助04-Git桥接与发布同步",
        ]
        self.assertEqual(names, expected)

    def test_agents_and_tasks_reference_existing_structure(self) -> None:
        channels = {
            str(item.get("name") or "")
            for item in (self._load("channels_seed.json").get("channels") or [])
            if isinstance(item, dict)
        }
        agents = self._load("agents_seed.json").get("agents") or []
        tasks = self._load("tasks_seed.json").get("tasks") or []
        for item in agents:
            if not isinstance(item, dict):
                continue
            self.assertIn(str(item.get("channel_name") or ""), channels)
        for item in tasks:
            if not isinstance(item, dict):
                continue
            self.assertIn(str(item.get("channel_name") or ""), channels)
            rel = str(item.get("path") or "").strip()
            self.assertTrue((self.repo_root / rel).exists(), rel)

    def test_required_knowledge_files_exist(self) -> None:
        expected = [
            "examples/minimal-project/tasks/主体-总控/产出物/沉淀/20260321-总控开箱路径收口基线.md",
            "examples/minimal-project/tasks/辅助01-架构与结构治理/产出物/沉淀/20260321-推荐结构边界与真源说明.md",
            "examples/minimal-project/tasks/子级01-运行时与后端/产出物/沉淀/20260321-最小运行链路说明.md",
            "examples/minimal-project/tasks/子级02-前端与交互/产出物/沉淀/20260321-示例项目可见结果清单.md",
            "examples/minimal-project/tasks/子级03-数据与契约/产出物/沉淀/20260321-示例项目契约检查清单.md",
            "examples/minimal-project/tasks/子级04-测试与验收/产出物/沉淀/20260321-双验收门禁说明.md",
            "examples/minimal-project/tasks/辅助02-文档与知识沉淀/产出物/沉淀/20260321-公开知识入口清单.md",
            "examples/minimal-project/tasks/辅助03-用户镜像与业务判断/产出物/沉淀/20260321-用户镜像业务判断卡片.md",
            "examples/minimal-project/tasks/辅助03-用户镜像与业务判断/产出物/沉淀/01-用户镜像定位与工作边界.md",
            "examples/minimal-project/tasks/辅助03-用户镜像与业务判断/产出物/沉淀/02-项目宏观概念与结构思想.md",
            "examples/minimal-project/tasks/辅助04-Git桥接与发布同步/产出物/沉淀/20260321-公开差异层与同步边界说明.md",
        ]
        for rel in expected:
            self.assertTrue((self.repo_root / rel).exists(), rel)


if __name__ == "__main__":
    unittest.main()
