# AI Bootstrap

这是公开版的一体化初始化入口。它默认是写给“用户自己电脑上的 AI”看的，不要求 AI 预先了解内部协作历史。接手时，先按这个顺序执行，不要跳步。

## 0. 先确认目标

你的目标不是直接改“生产项目”，而是在用户电脑上把 `standard_project` 拉起成一个可运行、可继续协作的标准项目。

这次公开包只保留一个默认项目：

- `standard_project`

你要达成的结果是：

- 看板能构建
- 服务能启动
- `standard_project` 能被扫描
- 种子包和技能包能被理解
- 默认启动批次文件能指导 AI 继续拉起标准项目 Agent
- 每个通道的 Agent 知道先去看自己负责通道中的文件和知识沉淀

补充边界：

- Qoreon 本身不内置 AI CLI
- 它依赖用户电脑本地已经安装可用的 CLI
- 当前预览版默认和推荐优先使用 `codex`
- 其他适配类型如 `claude` / `opencode` / `gemini` / `trae` 属于可扩展路径，不是当前默认启动路径

## 1. 先读这几份文件

1. `AGENTS.md`
2. `README.md`
3. `docs/public/quick-start.md`
4. `docs/onboarding/project-worksplit-playbook.md`
5. `examples/standard-project/README.md`
6. `examples/standard-project/seed/seed-inventory.json`
7. `examples/standard-project/tasks/辅助05-团队协作Skills治理/产出物/沉淀/03-公开公共技能包清单.md`
8. `examples/standard-project/skills/INDEX.md`

进入某个通道开始工作前，再补读：

- `examples/standard-project/tasks/<你的通道>/任务/`
- `examples/standard-project/tasks/<你的通道>/反馈/`
- `examples/standard-project/tasks/<你的通道>/产出物/材料/`
- `examples/standard-project/tasks/<你的通道>/产出物/沉淀/`

## 2. 优先执行这一条

如果你要帮助用户在新电脑上自动安装，先执行：

```bash
python3 scripts/start_standard_project.py
```

这是默认的完整安装入口。目标不是“只把页面起起来”，而是让 `standard_project`、页面和 startup-batch 在安装完成后一起就位。
这是默认的可靠安装入口。目标不是“只把页面起起来”，而是让 `standard_project`、页面和 startup-batch 一次准备好，然后由本机 AI 在自己的正常工作上下文里继续接手。

这条命令会做 5 件事：

1. bootstrap `standard_project`
2. 自动清理旧机器留下来的 `codex` 路径覆盖
3. build 页面
4. 启动 `18770` 服务
5. 生成 `startup-batch.json` / `startup-batch.md` 和 `.run/public-install-result.json`

注意：

- 默认命令不再把“后台批量创建多通道会话”作为安装完成门槛。
- 先把页面、标准项目和 startup-batch 稳定落地，再由本机 AI 接手，是当前公开预览版的推荐路径。
- 如果你只是要确认公开包能装起来，执行到这一步就足够了。

如果当前电脑的 `codex` 已准备好，而且你明确希望 Qoreon 自动尝试创建默认 Agent，再执行：

```bash
python3 scripts/start_standard_project.py --with-agents
```

这条命令会在默认安装完成后，先尝试创建 6 个核心通道 Agent 会话，再运行首轮培训、职责复述和示例协作动作，并生成标准项目的默认启动批次文件。
然后把下面两份文件一起交给本机 AI：

- `docs/public/ai-bootstrap.md`
- `examples/standard-project/.runtime/demo/startup-batch.md`

由 AI 按启动批次接管已经建好的核心通道，后续协作动作由 `主体-总控` 继续编排。若你明确需要 12 个通道一起自动激活，再追加 `--all-channels`。

不要默认把下面这条当成完整安装：

```bash
python3 scripts/install_public_bundle.py --start-server --skip-agent-activation
```

这只是页面模式。它适合排障或先验证静态页，不适合“安装后就要拿到 startup-batch 或让本机 AI继续接手”的目标。

如果你不想一把做完，也可以手动拆步：

```bash
python3 scripts/bootstrap_public_example.py --project-id standard_project
python3 build_project_task_dashboard.py
python3 server.py --port 18770 --static-root dist
python3 scripts/activate_public_example_agents.py --project-id standard_project --base-url http://127.0.0.1:18770
```

## 3. 初始化规则

- 把 `examples/standard-project/seed/project_seed.json` 视为项目真源
- 把 `channels_seed.json` 视为通道真源
- 把 `agents_seed.json` 视为 Agent 初始化真源
- 把 `tasks_seed.json` 视为首批任务真源
- 把 `skills-manifest.json` 视为技能装配真源
- 把 `03-公开公共技能包清单.md` 视为技能使用顺序说明
- 把 `docs/onboarding/project-worksplit-playbook.md` 视为推荐结构解释真源
- 角色边界不要去找 role skill，直接从自己负责通道的目录和通讯录中学习

## 4. 默认安全边界

- 默认 `sandboxed`
- 默认本机端口 `18770`
- `辅助04-Git桥接与发布同步` 默认 `default_enabled=false`
- `辅助04-Git桥接与发布同步` 默认 `default_mode=read_only`
- 未获得明确许可前，不做真实远端写操作
- `辅助03-用户镜像与业务判断` 可以给业务建议，但不替代总控直接发版

## 5. 默认启动批次

标准项目完整启动批次覆盖 12 个通道：

- `主体-总控`
- `辅助01-结构治理与项目接入`
- `子级01-运行时与后端`
- `子级02-前端与交互`
- `子级03-数据与契约`
- `子级04-测试与验收`
- `辅助02-文档与知识沉淀`
- `辅助03-用户镜像与业务判断`
- `辅助04-Git桥接与发布同步`
- `辅助05-团队协作Skills治理`
- `辅助06-项目运维`
- `系统01-信息梳理`

## 6. 成功标准

- `examples/standard-project/.runtime/demo/bootstrap-result.json` 已生成
- `examples/standard-project/.runtime/demo/startup-batch.md` 已生成
- 如果你显式执行了 `python3 scripts/start_standard_project.py --with-agents`，则 `examples/standard-project/.runtime/demo/activation-result.json` 也应生成
- `GET /__health` 正常
- `dist/project-task-dashboard.html` 已生成
- 页面里能看到 `standard_project`
- 页面里能看到标准项目与默认种子结构
- 页面里能扫描到标准项目任务

## 7. 遇到问题先查哪里

- 新电脑安装失败：`scripts/start_standard_project.py`
- bootstrap 失败：`scripts/bootstrap_public_example.py`
- AI 启动批次文件缺失：`scripts/start_standard_project.py --with-agents`
- Agent 激活失败：`scripts/activate_public_example_agents.py`
- 本机 `codex` 路径错误：`config.local.toml`
- 页面问题：`web/`
- 构建问题：`task_dashboard/cli.py`
- 服务问题：`server.py`
- 示例数据问题：`examples/standard-project/`
- 种子或技能问题：`examples/standard-project/seed/`、`examples/standard-project/skills/`

## 8. 推荐的第一个动作

启动完成后，先让 `主体-总控` 读取：

- `examples/standard-project/tasks/主体-总控/`
- `examples/standard-project/tasks/主体-总控/产出物/沉淀/02-标准项目启动顺序.md`
- `examples/standard-project/tasks/辅助01-结构治理与项目接入/产出物/沉淀/`
- `examples/standard-project/tasks/辅助05-团队协作Skills治理/产出物/沉淀/`
- `examples/standard-project/tasks/辅助06-项目运维/产出物/沉淀/`
- `examples/standard-project/tasks/系统01-信息梳理/产出物/沉淀/`

然后由总控决定是否继续点亮扩展治理通道。

## 9. 公共技能优先顺序

如果你是安装电脑上的 AI，不要只看角色名。默认优先理解这 4 个公共技能：

1. `project-startup-collab-suite`
2. `agent-init-training-playbook`
3. `collab-message-send`
4. `ccr-update-playbook`

进入长期使用阶段后，再按需启用：

- `skills-governance-upgrade`
- `session-health-inspector`
- `session-rotation-handoff`
- `task-health-organizer`

## 10. 培训与消息沟通要求

每个通道 Agent 在首轮培训里都要做到：

1. 先阅读自己负责通道中的文件和知识沉淀。
2. 复述自己的职责边界和不负责范围。
3. 重点学习公共技能中的消息沟通规则。
4. 一般情况下都要回给原发送 Agent。
5. 默认最小回执结构固定为：
   `当前结论 / 是否通过或放行 / 唯一阻塞 / 关键路径或 run_id / 下一步动作`
