# AGENTS

这个仓库面向“AI 先读说明，再接手执行”的使用方式。

## 开始前先读

1. `README.md`
2. `docs/public/ai-bootstrap.md`
3. `examples/minimal-project/README.md`
4. `examples/minimal-project/seed/seed-inventory.json`

## 默认执行规则

- 优先在示例项目内工作，不要假设存在外部私有目录。
- 以 `examples/minimal-project/seed/*.json` 作为初始化真源。
- 以 `docs/public/ai-bootstrap.md` 作为唯一初始化入口。
- 默认使用 `sandboxed`；只有明确需要时才切到 `privileged`。
- `辅助02-Git桥接与发布同步` 默认是只读预检位，不允许默认写远端。

## 回执建议

- 当前结论
- 是否通过或放行
- 唯一阻塞
- 下一步动作

## 禁止事项

- 不写入真实 token
- 不硬编码个人绝对路径
- 不提交真实会话或运行日志
- 不把示例项目误当成生产项目
