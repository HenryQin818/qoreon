# Quick Start

## 1. 准备环境

- Python 3.11+
- Qoreon 不会内置 AI CLI，本机需要自己安装可用的 CLI
- 当前支持适配的类型包括：`codex`、`claude`、`opencode`、`gemini`、`trae`
- 但当前预览版的默认与推荐路径是：优先使用 `codex`
- 如果你只想先把页面和标准项目跑起来，Python 就够了
- 如果你还想激活内置 Agent，当前公开示例默认使用 `codex`
- 激活前请确认：
  - `codex` 已安装并完成登录
  - `~/.codex/sessions` 可写
  - 若你要改成 `claude` / `gemini` / `opencode` / `trae`，先修改标准项目对应通道的 `cli_type`
  - 其他 CLI 可以接入，但这版对外文档、默认种子和主要验证链路都优先按 `codex` 给出

## 2. 新电脑推荐路径

默认只保留一个公开项目：`standard_project`。

推荐直接执行：

```bash
python3 scripts/start_standard_project.py
```

这是“完整安装”入口。目标结果是：页面启动后，`standard_project` 里直接带默认通道 Agent 会话。

这里的“默认 Agent 会话”依赖本机 `codex` CLI 可用，不是 Qoreon 自带了一个内置执行器。

这条命令会完成：

- bootstrap `standard_project`
- 自动清理旧机器留下来的 `codex` 路径覆盖，并重写为当前电脑可用路径
- build `dist/`
- 启动 `18770` 本地服务
- 如果当前电脑的 `codex` 已安装并可用，默认创建 `standard_project` 的 12 个通道 Agent 会话
- 如果当前电脑还没准备好 `codex`，会保留页面安装结果，并在结果文件里明确提示稍后补激活

第一次在新电脑上创建 12 个真实 CLI 会话会比单纯起页面慢，这是正常现象；安装器会等待这批会话创建完成后再结束。

如果当前电脑的 `codex` 已安装并完成登录，再执行：

```bash
python3 scripts/start_standard_project.py --with-agents
```

这条命令会在默认创建会话的基础上，再跑首轮培训、职责复述和示例协作动作，并生成标准项目完整启动批次文件：

- `examples/standard-project/.runtime/demo/startup-batch.json`
- `examples/standard-project/.runtime/demo/startup-batch.md`

然后把这两份文件和 `docs/public/ai-bootstrap.md` 一起交给安装电脑上的 AI，让它按启动批次继续接管已经建好的 12 个通道。

补充说明：

- `python3 scripts/start_standard_project.py` 会先尝试创建第一个后台 Codex 会话，作为“这台电脑是否能无交互建会话”的真实探测。
- 如果这个探测通过，就继续把默认 12 个通道会话建出来。
- 如果这个探测被认证/环境阻塞，安装器不会一直卡住；它会保留页面安装结果，并明确提示你把 `startup-batch.md` 交给本机 AI 接手。
- 所以“能打开 codex CLI”是一个好信号，但不等于“后台无交互批量建会话”一定没问题。
- 如果你后面要切到 Claude Code、OpenCode、Gemini CLI 或 Trae CLI，请把它视为“进阶接入”，不要当成当前预览版的默认路径。

## 2.1 页面模式和完整模式的区别

如果你执行的是下面这条：

```bash
python3 scripts/install_public_bundle.py --start-server --skip-agent-activation
```

那它只是“页面模式/排障模式”：

- 会有 `standard_project`
- 页面能打开
- 但不会创建默认 Agent 会话

所以如果你打开后看到项目存在、但里面没有 Agent，这通常不是安装失败，而是执行了 `--skip-agent-activation`。

## 3. 手动拆步路径

如果你想手动执行，再按下面走：

```bash
python3 scripts/bootstrap_public_example.py --project-id standard_project
python3 build_project_task_dashboard.py
python3 server.py --port 18770 --static-root dist
python3 scripts/activate_public_example_agents.py --project-id standard_project --base-url http://127.0.0.1:18770 --include-optional
```

如果你的电脑还没有可用的 `codex` 环境，先不要执行第 4 步；只完成前 3 步，页面和标准项目也可以正常打开。等 `codex` 环境就绪后，再补第 4 步把 12 个通道会话建出来。

## 4. 打开页面

- `http://127.0.0.1:18770/project-task-dashboard.html`
- `http://127.0.0.1:18770/project-overview-dashboard.html`
- `http://127.0.0.1:18770/project-status-report.html`

## 5. 如果要让 AI 接手

直接把 `docs/public/ai-bootstrap.md` 发给 AI，并要求它优先执行：

- `python3 scripts/start_standard_project.py`

然后让它读取：

- `AGENTS.md`
- `docs/onboarding/project-worksplit-playbook.md`
- `examples/standard-project/README.md`
- `examples/standard-project/seed/seed-inventory.json`
- `examples/standard-project/.runtime/demo/startup-batch.md`
- `examples/standard-project/tasks/辅助05-团队协作Skills治理/产出物/沉淀/03-公开公共技能包清单.md`
- 它自己负责通道下的 `任务/`、`反馈/`、`产出物/材料/`、`产出物/沉淀/`

这套公开包现在只有一条默认入口：

- `standard-project`：安装、启动、激活和长期治理都围绕它展开

它只保留一层公共技能：

- 8 个公共 skill：告诉 AI 怎么做启动、培训、协作、巡检和轮换
- 各通道负责什么，不靠 role skill，而是靠通道目录、通讯录和知识沉淀
