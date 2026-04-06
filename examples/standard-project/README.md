# Standard Project

这是 Qoreon 公开包中的唯一项目入口。

安装后默认就围绕它展开，不再要求用户在多个示例项目之间切换。

## 当前规划中的标准通道

1. `主体-总控`
2. `辅助01-结构治理与项目接入`
3. `子级01-运行时与后端`
4. `子级02-前端与交互`
5. `子级03-数据与契约`
6. `子级04-测试与验收`
7. `辅助02-文档与知识沉淀`
8. `辅助03-用户镜像与业务判断`
9. `辅助04-Git桥接与发布同步`
10. `辅助05-团队协作Skills治理`
11. `辅助06-项目运维`
12. `系统01-信息梳理`

## 启动时先读

1. `seed/seed-inventory.json`
2. `seed/ccr_roster_seed.json`
3. `tasks/主体-总控/产出物/沉淀/03-标准项目通讯录与分工表.md`
4. `tasks/README.md`
5. `tasks/主体-总控/产出物/沉淀/02-标准项目启动顺序.md`
6. `tasks/主体-总控/产出物/沉淀/01-治理通道来源映射.md`
7. `tasks/辅助05-团队协作Skills治理/产出物/沉淀/03-公开公共技能包清单.md`
8. `skills/INDEX.md`

## 当前状态

当前已创建第一版标准模板：

- 通道真源：12 条
- Agent 真源：12 条
- 任务真源：12 条
- 技能真源：8 条
- 新增治理通道已带最小知识卡片
- 只保留公开公共 skill，角色信息收敛在通道目录、通讯录和知识沉淀中

## 默认启动口径

- 默认只点亮前 6 个核心通道，方便先跑通安装与页面
- `seed/ccr_roster_seed.json` 记录 12 个通道的分工、边界和默认协作入口
- `tasks/主体-总控/产出物/沉淀/03-标准项目通讯录与分工表.md` 作为人读版总表
- 当用户电脑上的 AI 已准备好时，再按通讯录与启动顺序逐步点亮扩展治理通道

后续会继续把主项目中的公开安全知识提炼并复制进来，补成“完整标准项目”。

## 技能包结构

- `seed/skills-manifest.json`
  这是机器读真源
- `skills/`
  这里只放公共 skill：对应启动、培训、协作、会话健康、轮换和任务健康
- 角色职责不做 role skill，统一从 `tasks/`、`ccr_roster_seed.json` 和通讯录/分工表中学习

推荐先读：

1. `tasks/辅助05-团队协作Skills治理/产出物/沉淀/03-公开公共技能包清单.md`
2. `seed/skills-manifest.json`
3. `skills/INDEX.md`

## 推荐用途

- 作为完整项目模板复制给新用户
- 作为长期项目的标准起始结构
- 作为治理辅助能力的公开示例
- 作为安装后 AI 的默认工作面

## 推荐启动方式

```bash
python3 scripts/start_standard_project.py
```

这条默认命令优先把页面、标准项目和 startup-batch 稳定准备好。

如果你希望显式尝试自动创建默认 Agent，再执行：

```bash
python3 scripts/start_standard_project.py --with-agents
```

然后把这两份文件一起发给 AI：

- `docs/public/ai-bootstrap.md`
- `examples/standard-project/.runtime/demo/startup-batch.md`

默认 `--with-agents` 先覆盖 6 个核心通道；如果你明确需要 12 个通道一起自动激活，再追加 `--all-channels`。启动批次本身仍覆盖标准项目的 12 个通道。
启动后的 AI 先不要凭角色名直接行动，而是要先读自己负责通道下的 `任务/`、`反馈/`、`产出物/材料/`、`产出物/沉淀/`。

如果你想手动拆步，再执行：

```bash
python3 scripts/bootstrap_public_example.py --project-id standard_project
python3 build_project_task_dashboard.py
python3 server.py --port 18770 --static-root dist
python3 scripts/activate_public_example_agents.py --project-id standard_project --base-url http://127.0.0.1:18770
```

## 首轮使用建议

1. 先跑通 `standard_project` 的 bootstrap、build 和页面
2. 再确认 `startup-batch.md` 已生成，并交给本机 AI 接手
3. 需要扩编治理辅助能力时，再逐步点亮扩展治理通道
