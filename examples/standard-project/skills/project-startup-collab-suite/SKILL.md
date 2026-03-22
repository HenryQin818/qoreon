# project-startup-collab-suite

## 用途

用于 `standard_project` 的首轮启动编排：确认真源、读取通讯录、决定先点亮哪些通道、生成首轮启动顺序。

## 适用场景

- 新电脑第一次安装后，需要把项目从“能打开”推进到“能协作”
- 要把 `startup-batch.md` 交给本机 AI 接手
- 需要确认核心通道和扩展治理通道的启动顺序

## 先读

1. `examples/standard-project/seed/project_seed.json`
2. `examples/standard-project/seed/ccr_roster_seed.json`
3. `examples/standard-project/tasks/主体-总控/产出物/沉淀/02-标准项目启动顺序.md`
4. `examples/standard-project/tasks/主体-总控/产出物/沉淀/03-标准项目通讯录与分工表.md`

## 步骤

1. 先确认当前目标是“启动标准项目”，不是改生产环境
2. 先点亮 6 个核心通道，再视情况点亮扩展治理通道
3. 为每个通道确认主 Agent、职责边界、默认协作入口
4. 生成或刷新 `startup-batch.md`
5. 把启动批次和 `docs/public/ai-bootstrap.md` 一起交给本机 AI

## 产出

- 当前结论
- 是否通过或放行
- 唯一阻塞
- 关键路径或 run_id
- 下一步动作

## 边界

- 不直接实现业务功能
- 不替代结构治理修改真源
- 不默认做远端写操作
