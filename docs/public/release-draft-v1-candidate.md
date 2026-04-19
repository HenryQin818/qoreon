# Qoreon v1 Preview 20260420-a

![Qoreon Logo](../../assets/brand/qoreon-logo-primary.png)

Qoreon 是连接人类意图与 AI 执行的控制层。
这份页面是 Qoreon v1 公开候选版的对外说明。

Qoreon is the control layer between human intent and AI execution.

It turns AI work from isolated chats into a visible local system:

- channels
- agents
- task spaces
- startup batches
- receipts and review loops

## What This Repository Is Trying To Prove

这个仓库当前要证明的不是“云平台是否成立”，而是更基础的一件事：
别人能否下载这个包，在自己的电脑上把一个带标准项目、带 AI 接管路径的本地系统跑起来。

Qoreon v1 is not trying to be a hosted platform.

The first thing it is trying to prove is simpler:

1. you can download a public package
2. run one command on a new computer
3. open a working local project
4. hand the startup docs to the local AI
5. let that AI continue a real standard project instead of a blank sandbox

## What It Looks Like

### Home Project List

![Home Project List](../../assets/screenshots/home-project-list.png)

这是用户第一次看到的项目清单视角。

This is the first “understand the public project” page.

### Project Dialog Detail

![Project Dialog Detail](../../assets/screenshots/project-dialog-detail.png)

这是任务、对话、回执和协作都汇聚到一起的主工作面。

This is where channels, task files, receipts, and AI execution meet.

### Message Flow Board

![Message Flow Board](../../assets/screenshots/message-flow-board.png)

这是消息派发与协同流转视角。

This is where the public project shows dispatch, blocked states, and cross-channel message movement.

## The Public Install Path

推荐安装路径如下：

Recommended path on a new computer:

```bash
python3 scripts/start_standard_project.py
```

这是默认完整安装命令。
它默认保证页面、`standard_project` 和 startup-batch 一次准备好；如果你还要自动建 Agent，会话激活改走显式命令。
对外默认完成态可理解为：`startup_batch_ready`。

If Codex is ready and you also want the default AI startup batch:

```bash
python3 scripts/start_standard_project.py --with-agents
```

Add `--all-channels` if you explicitly want the full 12-channel activation attempt. Public docs now converge on `--all-channels` as the canonical 12-channel flag, while the manual activation script still accepts legacy `--include-optional` for compatibility.

Then open:

- `http://127.0.0.1:18770/project-task-dashboard.html`
- `http://127.0.0.1:18770/project-overview-dashboard.html`
- `http://127.0.0.1:18770/__health`

## Why The Public Package Converges To `standard_project`

公开包只收敛到一个默认项目：

This repository intentionally converges to one default public project:

- `standard_project`

That choice keeps the first-run path stable:

- one install command
- one CCR roster
- one default startup batch path
- one AI bootstrap path
- one public governance structure

Inside `standard_project`, the public package already ships:

- governance channels
- execution channels
- public-safe seed packs
- skills manifest
- startup order
- communication roster
- task / feedback / sediment structure

## What Ships In This Candidate

本候选版已经包含：

- core runtime and build pipeline
- local server and static page generation
- public docs in `docs/public/`
- standard project in `examples/standard-project/`
- install and startup scripts
- AI bootstrap instructions
- screenshots and brand assets for GitHub presentation
- core display assets:
  - `assets/brand/qoreon-logo-primary.png`
  - `assets/screenshots/home-project-list.png`
  - `assets/screenshots/project-dialog-detail.png`
  - `assets/screenshots/message-flow-board.png`

## What Does Not Ship

本候选版不会附带：

- real internal sessions
- private runtime data
- internal registry truth
- private worklog evidence chains
- production-side sync authority by default

## The Intended AI Handoff

这个公开包的核心不是“代码压缩包”，而是“代码 + 项目模板 + AI 接管路径”。

The public package is designed so that another AI can continue the setup with minimal confusion.

The handoff bundle is:

- `docs/public/ai-bootstrap.md`
- `docs/public/quick-start.md`
- `examples/standard-project/README.md`
- `examples/standard-project/seed/ccr_roster_seed.json`
- `examples/standard-project/tasks/主体-总控/产出物/沉淀/02-标准项目启动顺序.md`
- `examples/standard-project/tasks/主体-总控/产出物/沉淀/03-标准项目通讯录与分工表.md`

That means the “product” is not only code. It is:

- the local runtime
- the public project shape
- the AI continuation path

## Current Preview Status

当前状态：

Current packaging direction:

- remote GitHub repository is already created
- `origin` is already bound
- public homepage assets and docs are included
- preview package and install docs are aligned to `standard_project`
- install path now degrades safely when background Codex session creation is blocked

Current public preview baseline:

- repo commit: `2df37dc`
- repo preview tag: `qoreon-v1-preview-20260420-a`
- repo candidate tag: `qoreon-v1-candidate-20260420-a`
- delivery: GitHub release source archives for `qoreon-v1-preview-20260420-a`
- verification: see the `qoreon-v1-preview-20260420-a` release page and public-safe test results

This means:

- GitHub can already host a shareable preview release
- the current preview is meant for install-and-try validation, not long-term compatibility guarantees

## Suggested GitHub About

- Name: `Qoreon`
- Description: `The control layer between human intent and AI execution. Run and organize an AI team locally.`
- Topics: `ai-agents`, `multi-agent`, `orchestration`, `local-first`, `developer-tools`, `taskboard`, `agent-runtime`, `codex`, `claude-code`

## Suggested First Links

If this goes to GitHub soon, the first three links should be:

1. `README.md`
2. `docs/public/quick-start.md`
3. `docs/public/ai-bootstrap.md`

And if you want one “long-form” explanation link for people who need more context, use this file.
