# Minimal Project

这是公开版内置的推荐示例项目。

它的目标不是模拟真实生产业务，而是给外部使用者一个可直接运行、可直接训练 AI、可直接开展简单协作的起点。下载后，你可以把这整个目录交给你自己的 AI，让它按公开规则先跑通一轮最小闭环，再按同样结构扩成你的正式项目。

## 当前采用的推荐结构

示例项目默认采用 `2 + 4 + X` 范式：

- 2 个中央角色：`主体-总控`、`辅助01-架构与结构治理`
- 4 个核心执行通道：`子级01-运行时与后端`、`子级02-前端与交互`、`子级03-数据与契约`、`子级04-测试与验收`
- X 个常用支撑通道：`辅助02-文档与知识沉淀`、`辅助03-用户镜像与业务判断`、`辅助04-Git桥接与发布同步`

默认激活的是前 6 个核心通道：`总控 + 架构 + 4 个执行通道`。后 3 个支撑通道会保留结构、任务和知识文件，但不作为首轮默认激活集。

这套结构和公开版内置文章 [docs/onboarding/project-worksplit-playbook.md](../../docs/onboarding/project-worksplit-playbook.md) 保持一致。

## 包含内容

- 9 个首批通道
- 9 个对应 Agent 种子
- 一组可直接扫描的示例任务
- 一组公开安全技能包
- 一份 AI 初始化入口文档
- 每个通道至少 1 份最小知识沉淀

## 开箱路径

1. 先把 [docs/public/ai-bootstrap.md](../../docs/public/ai-bootstrap.md) 发给你的 AI。
2. 让它按文档执行 `python3 scripts/bootstrap_public_example.py`。
3. 启动服务：`python3 server.py --port 18770 --static-root dist`
4. 执行 `python3 scripts/activate_public_example_agents.py --base-url http://127.0.0.1:18770`
5. 再让它读取 `seed/` 下 5 份真源文件和本目录下的任务/沉淀。
6. 然后由 `主体-总控` 接着当前会话继续推进，先带着默认激活的 6 个核心通道跑一轮最小协作闭环。

执行完第 4 步后，你会在 `examples/minimal-project/.runtime/demo/activation-result.json` 里看到这轮真实激活出来的 session / run 留痕。

补充说明：

- 第 1 到第 3 步不依赖 AI CLI，可以先独立完成
- 第 4 步当前默认依赖 `codex`
- 如果你的电脑没有准备好 `codex`，先不要把“页面已能运行”和“Agent 已能激活”混为一件事

## 建议用途

- 验证页面是否能正确扫描任务
- 验证 AI 是否能理解 seed、skills 和推荐项目结构
- 用作你自己新项目的复制模板
- 让你的 AI 先在本机跑通 Qoreon，再接手更复杂的正式项目
