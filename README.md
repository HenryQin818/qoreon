# task-dashboard-oss

一个面向 AI 协作场景的本地任务看板与 CCB（CLI Control Bridge）实验项目。

它提供三类能力：

- 把目录里的任务/反馈/沉淀 Markdown 扫描成可视化看板。
- 通过同源本机 API 驱动 Codex、Claude、Gemini、OpenCode、Trae 等 CLI 会话。
- 交付一个可复制的最小示例项目，包含通道、Agent、任务种子、技能包和 AI 初始化说明。

## 当前首发范围

- 核心代码主链路：`task_dashboard/`、`server.py`、`build_project_task_dashboard.py`
- 页面：任务页、总览页、通讯页、状态页、Agent 目录页、Agent 幕帘页、关系页、会话健康页
- 示例项目：`examples/minimal-project/`
- 初始化资料：`docs/public/`、`examples/minimal-project/seed/`、`examples/minimal-project/skills/`

## 快速开始

1. 使用 Python 3.11+。
2. 如需自定义配置，先复制一份：

```bash
cp config.example.toml config.toml
```

3. 生成静态页面：

```bash
python3 build_project_task_dashboard.py
```

4. 启动本机服务：

```bash
python3 server.py --port 18770
```

5. 打开页面：

- `http://127.0.0.1:18770/project-task-dashboard.html`
- `http://127.0.0.1:18770/project-overview-dashboard.html`
- `http://127.0.0.1:18770/__health`

## 建议阅读顺序

- `docs/public/quick-start.md`
- `docs/public/ai-bootstrap.md`
- `examples/minimal-project/README.md`
- `examples/minimal-project/seed/seed-inventory.json`

## 目录说明

- `task_dashboard/`: Python 构建引擎与运行时
- `web/`: 前端模板与脚本
- `examples/minimal-project/`: 公开示例项目
- `docs/public/`: 外部使用文档
- `docs/status-report/`: 状态汇报页数据源
- `tests/`: 最小公开测试集

## 设计边界

- 默认只监听 `127.0.0.1`
- 默认不包含任何真实会话、真实 run、真实任务空间
- 公开版只内置公开安全的种子包与技能包
- Git 桥接能力默认是 `read_only / dry_run`

## 测试

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

## 许可

MIT，见 `LICENSE`。
