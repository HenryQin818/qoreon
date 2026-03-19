# Architecture

## 组成

- `build_project_task_dashboard.py`: 统一构建入口
- `task_dashboard/cli.py`: 扫描任务与生成静态页面
- `server.py`: 本机服务与 CCB API
- `task_dashboard/runtime/`: 运行时、会话、run、调度与路由
- `web/`: 页面模板与脚本

## 数据层

- Markdown 任务空间是看板真源
- `.runtime/.sessions/.runs` 是运行产物真源
- `examples/minimal-project/seed/*.json` 是公开种子包真源
- `docs/public/ai-bootstrap.md` 是 AI 初始化唯一入口

## 公开版一体包

公开版不是单纯代码导出，还包括：

- 示例项目目录
- 初始任务
- 通道/Agent 种子
- 技能包与 manifest
- AI 初始化说明
- 最小状态汇报页数据
