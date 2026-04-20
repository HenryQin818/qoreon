# Qoreon

<div align="center">
  <img src="assets/brand/qoreon-logo-horizontal-light.png" alt="Qoreon" width="720" />
  <p><strong>The multi-agent work platform for local-first execution.</strong></p>
  <p>Qoreon 把项目、任务、消息和组织关系放进同一个工作现场。<br />Qoreon keeps projects, tasks, messages, and team structure in one operating surface.</p>
  <p>
    <a href="#中文">中文</a> ·
    <a href="#english">English</a> ·
    <a href="docs/public/quick-start.md">Quick Start</a> ·
    <a href="docs/public/ai-bootstrap.md">Docs</a>
  </p>
</div>

- 把多 Agent 协作收进一个工作现场
- 让标准项目、启动批次和 AI 接管路径一起交付
- 默认保持 local-first、可见、可验证

- Organize multi-agent work around projects, channels, tasks, and receipts
- Ship a standard project, startup batch, and AI handoff path together
- Keep execution local-first, visible, and verifiable

## Product Views / 产品界面

### Home Project List

![Home Project List](assets/screenshots/home-project-list.png)

用户第一次进入项目时看到的项目清单页，展示默认公开项目 `standard_project` 和最先应打开的入口。  
The first project list page a new user sees, showing the default public project `standard_project` and the main entry points.

### Project Dialog Detail

![Project Dialog Detail](assets/screenshots/project-dialog-detail.png)

通道、任务、回执、培训提示和 AI 协作过程汇聚到一起的主工作面。  
The main working surface where channels, tasks, receipts, training prompts, and AI collaboration stay visible together.

### Message Flow Board

![Message Flow Board](assets/screenshots/message-flow-board.png)

展示多 Agent 派发、回执、阻塞状态和跨通道协同的消息流转视图。  
The message flow view that makes multi-agent dispatch, receipts, blocked states, and cross-channel coordination visible at a glance.

## 中文

### 为什么是 Qoreon

大多数 AI 工具停留在“一次提问，一次回答”。Qoreon 面向的是另一种工作方式：把项目、通道、任务、协作回执和 Agent 执行组织成一个可见、可接管、可继续优化的本地系统。

它不是单个聊天窗口的增强版，而是一个本地控制层：

- 用项目和通道组织多 Agent 协作
- 让任务、消息、回执和沉淀形成工作链路
- 让另一个人或另一台电脑上的 AI 可以继续接手已经启动的标准项目

### 首版证明什么

这版首要证明的不是“云平台是否已经完备”，而是更基础的一件事：别人是否能下载公开包，在自己的电脑上把一个带标准项目、带 AI 接管路径的本地系统跑起来。

首版的目标是把三件事跑通：

1. 启动公开包和本地页面
2. 启动默认标准项目 `standard_project`
3. 把 startup batch 和文档交给本机 AI 继续接管

### 快速开始

推荐安装路径如下：

```bash
cp config.example.toml config.toml
python3 scripts/start_standard_project.py
```

这条默认命令会启动 `standard_project`，生成 `dist/`，启动本地页面所需的产物，并把可继续接手的 startup batch 一并准备出来。

如果本机已经准备好 Codex CLI，并且你想显式尝试自动创建默认 Agent 会话，再执行：

```bash
python3 scripts/start_standard_project.py --with-agents
```

如果你明确要尝试完整 12 通道激活，再追加：

```bash
python3 scripts/start_standard_project.py --with-agents --all-channels
```

启动后可打开：

- `http://127.0.0.1:18770/project-task-dashboard.html`
- `http://127.0.0.1:18770/project-overview-dashboard.html`
- `http://127.0.0.1:18770/project-status-report.html`
- `http://127.0.0.1:18770/__health`

### 环境要求与 CLI 依赖

- Python `3.11+`
- 若只运行页面和标准项目，Python 即可
- 若还要激活内置示例 Agent，需要本机已安装可用的 AI CLI
- 当前公开安装文档和默认示例项目优先按 `Codex CLI` 验证
- 若要改用其他 CLI，需要调整 `examples/standard-project/` 中相关通道的 `cli_type`

Qoreon 本身不会内置 `codex`、Claude Code、OpenCode、Gemini CLI 或 Trae CLI。它依赖目标电脑本地已经安装并可用的 AI CLI。

### 技术概览

这个仓库当前包含：

- Python runtime 与构建主线：`task_dashboard/`、`server.py`、`build_project_task_dashboard.py`
- 静态页面模板与浏览器脚本：`web/`
- 默认公开标准项目：`examples/standard-project/`
- 安装、启动与 AI 接管文档：`docs/public/`
- 公共品牌图和 public-safe 截图：`assets/brand/`、`assets/screenshots/`

### 默认标准项目 `standard_project`

公开包只保留一个默认项目：`standard_project`。

这样做是为了让安装路径、AI 接管路径、治理结构和验收口径全部指向同一个工作区，避免第一次使用就分叉。

当前 `standard_project` 已经内置：

- 治理通道与执行通道
- 默认 Agent roster
- 任务 / 反馈 / 沉淀结构
- AI startup batch 路径
- 安装与 bootstrap 文档

### AI 接管路径

这个公开包的核心不是“代码压缩包”，而是“代码 + 标准项目模板 + AI 接管路径”。

推荐把以下文件交给本机 AI：

- `docs/public/ai-bootstrap.md`
- `docs/public/quick-start.md`
- `examples/standard-project/README.md`
- `examples/standard-project/seed/ccr_roster_seed.json`
- `examples/standard-project/tasks/主体-总控/产出物/沉淀/02-标准项目启动顺序.md`
- `examples/standard-project/tasks/主体-总控/产出物/沉淀/03-标准项目通讯录与分工表.md`

### 仓库结构

- `task_dashboard/`: Python build engine and runtime
- `web/`: page templates and browser scripts
- `examples/standard-project/`: public standard project template
- `assets/brand/`: brand assets for README and launch material
- `assets/screenshots/`: public-safe screenshots used in docs and GitHub presentation
- `docs/public/`: public install, bootstrap, architecture, and launch docs
- `tests/`: public verification tests

### 公开边界

默认边界如下：

- 默认本地绑定地址是 `127.0.0.1`
- 包内不带真实内部会话、真实 runs 或私有 runtime 数据
- 仅附带 public-safe seed packs、skills、文档和截图
- 不默认附带生产侧同步权限

### 验证方式

构建与公开口径验证可用以下命令：

```bash
python3 build_project_task_dashboard.py
python3 -m unittest discover -s tests -p 'test_public_*.py' -v
```

### 下一步阅读

建议按以下顺序继续：

1. `docs/public/quick-start.md`
2. `docs/public/ai-bootstrap.md`
3. `docs/public/architecture.md`
4. `examples/standard-project/README.md`
5. `examples/standard-project/tasks/主体-总控/产出物/沉淀/02-标准项目启动顺序.md`

## English

### Why Qoreon

Most AI tooling stops at "one prompt, one answer". Qoreon is built for a different operating model: it organizes projects, channels, tasks, receipts, and agent execution into a visible local system that can be handed off and continued.

It is not just a better chat window. It is a local control layer that:

- organizes multi-agent work around projects and channels
- turns tasks, messages, receipts, and sediment into a visible working chain
- lets another person or another machine's AI continue a standard project that has already been started

### What This First Release Proves

This release is not trying to prove a fully finished cloud platform. It is proving something more basic first: someone else can download the public package and run a local system with a standard project and a clear AI handoff path on their own machine.

The first release is meant to prove three things:

1. the public package and local pages can run
2. the default project `standard_project` can start cleanly
3. the local AI can continue from the startup batch and docs

### Quick Start

Recommended path:

```bash
cp config.example.toml config.toml
python3 scripts/start_standard_project.py
```

This starts `standard_project`, builds `dist/`, prepares the local pages, and generates the startup batch that the local AI can continue from.

If Codex CLI is already ready on that machine and you also want to explicitly try automatic session creation:

```bash
python3 scripts/start_standard_project.py --with-agents
```

If you explicitly want the full 12-channel activation attempt:

```bash
python3 scripts/start_standard_project.py --with-agents --all-channels
```

Then open:

- `http://127.0.0.1:18770/project-task-dashboard.html`
- `http://127.0.0.1:18770/project-overview-dashboard.html`
- `http://127.0.0.1:18770/project-status-report.html`
- `http://127.0.0.1:18770/__health`

### Requirements & CLI Dependency

- Python `3.11+`
- If you only want the pages and the standard project, Python is enough
- If you want to activate the built-in example agents, a usable local AI CLI is required
- The current public install path is primarily validated against `Codex CLI`
- If you want another CLI, update the relevant `cli_type` values inside `examples/standard-project/`

Qoreon does not bundle `codex`, Claude Code, OpenCode, Gemini CLI, or Trae CLI. It depends on AI CLIs already installed and usable on the target computer.

### Technical Overview

This repository currently ships:

- the Python runtime and build pipeline: `task_dashboard/`, `server.py`, `build_project_task_dashboard.py`
- static page templates and browser scripts: `web/`
- the default public standard project: `examples/standard-project/`
- install, startup, and AI handoff docs: `docs/public/`
- public-safe brand assets and screenshots: `assets/brand/`, `assets/screenshots/`

### The Default Standard Project

The public package intentionally converges to one default project: `standard_project`.

That keeps installation, AI handoff, governance, and validation pointed at the same workspace instead of splitting the first-run path too early.

`standard_project` already includes:

- governance and execution channels
- the default agent roster
- task / feedback / sediment structure
- the AI startup batch path
- install and bootstrap docs

### AI Handoff

The product here is not only source code. It is source code plus a standard project template plus a continuation path for the local AI.

The key handoff bundle is:

- `docs/public/ai-bootstrap.md`
- `docs/public/quick-start.md`
- `examples/standard-project/README.md`
- `examples/standard-project/seed/ccr_roster_seed.json`
- `examples/standard-project/tasks/主体-总控/产出物/沉淀/02-标准项目启动顺序.md`
- `examples/standard-project/tasks/主体-总控/产出物/沉淀/03-标准项目通讯录与分工表.md`

### Repo Structure

- `task_dashboard/`: Python build engine and runtime
- `web/`: page templates and browser scripts
- `examples/standard-project/`: public standard project template
- `assets/brand/`: brand assets for README and launch material
- `assets/screenshots/`: public-safe screenshots used in docs and GitHub presentation
- `docs/public/`: public install, bootstrap, architecture, and launch docs
- `tests/`: public verification tests

### Public Boundaries

The default public boundary is:

- default local bind on `127.0.0.1`
- no real internal sessions, real runs, or private runtime data in the package
- only public-safe seed packs, skills, docs, and screenshots are included
- no production-side sync authority is bundled by default

### Validation

Use the following commands for build and public-scope verification:

```bash
python3 build_project_task_dashboard.py
python3 -m unittest discover -s tests -p 'test_public_*.py' -v
```

### Read Next

Recommended reading order:

1. `docs/public/quick-start.md`
2. `docs/public/ai-bootstrap.md`
3. `docs/public/architecture.md`
4. `examples/standard-project/README.md`
5. `examples/standard-project/tasks/主体-总控/产出物/沉淀/02-标准项目启动顺序.md`

## License

MIT. See `LICENSE`.
