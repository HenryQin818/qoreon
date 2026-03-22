# ccr-update-playbook

## 用途

用于更新标准项目的通讯录、通道真源、会话入口和项目接入边界。

## 适用场景

- 通道新增、删减、改名
- 默认协作入口变化
- 需要刷新 `ccr_roster_seed.json`
- 需要确认某条通道是否应默认启用

## 先读

1. `examples/standard-project/seed/channels_seed.json`
2. `examples/standard-project/seed/ccr_roster_seed.json`
3. `examples/standard-project/tasks/主体-总控/产出物/沉淀/03-标准项目通讯录与分工表.md`

## 步骤

1. 先冻结目标结构
2. 再更新机器读真源
3. 再更新人读通讯录和分工表
4. 最后通知总控和相关通道消费

## 边界

- 不直接删历史沉淀
- 不把运行态当真源
