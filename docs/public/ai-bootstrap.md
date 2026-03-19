# AI Bootstrap

这是公开版的一体化初始化入口。让外部 AI 接手时，先按这个顺序执行，不要跳步。

## 0. 先确认目标

你的目标不是直接改“生产项目”，而是先在示例项目里完成一轮最小协作闭环：

- 看板能构建
- 服务能启动
- 示例任务能被扫描
- 种子包和技能包能被理解
- 至少能承接一条总控任务和一条执行任务

## 1. 先读这 4 个文件

1. `AGENTS.md`
2. `README.md`
3. `examples/minimal-project/README.md`
4. `examples/minimal-project/seed/seed-inventory.json`

## 2. 初始化规则

- 把 `examples/minimal-project/seed/project_seed.json` 视为项目真源
- 把 `channels_seed.json` 视为通道真源
- 把 `agents_seed.json` 视为 Agent 初始化真源
- 把 `tasks_seed.json` 视为首批任务真源
- 把 `skills-manifest.json` 视为技能装配真源

## 3. 默认安全边界

- 默认 `sandboxed`
- 默认本机端口 `18770`
- `辅助02-Git桥接与发布同步` 默认 `default_enabled=false`
- `辅助02-Git桥接与发布同步` 默认 `default_mode=read_only`
- 未获得明确许可前，不做真实远端写操作

## 4. 最小启动动作

```bash
python3 build_project_task_dashboard.py
python3 server.py --port 18770
```

## 5. 成功标准

- `GET /__health` 正常
- `dist/project-task-dashboard.html` 已生成
- 页面里能看到 `minimal_project`
- 页面里能看到首批 6 个通道
- 页面里能扫描到示例任务

## 6. 遇到问题先查哪里

- 配置问题：`config.toml`
- 页面问题：`web/`
- 构建问题：`task_dashboard/cli.py`
- 服务问题：`server.py`
- 示例数据问题：`examples/minimal-project/`
- 种子或技能问题：`examples/minimal-project/seed/`、`examples/minimal-project/skills/`

## 7. 回执建议

- 当前结论
- 是否通过或放行
- 唯一阻塞
- 下一步动作
