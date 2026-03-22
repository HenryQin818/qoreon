# GitHub Homepage Kit

这份文件用于把 Qoreon 的 GitHub 仓首页一次性配齐。

当前正式线上仓库：

- `https://github.com/HenryQin818/qoreon`

## 1. 仓名建议

截至 2026-03-20，本地核查与 GitHub 页面观察结果是：

- `github.com/Qoreon` 当前返回 404，说明 `Qoreon` 这个 GitHub 用户名/组织名当前看未被占用
- 若你创建了 `Qoreon` 组织或用户，就可以使用 `github.com/Qoreon/qoreon`

因此建议按两种情况处理：

- 你能创建 `Qoreon` 组织：优先使用 `Qoreon/qoreon`
- 你已有其他组织：优先使用该组织下的 `qoreon`
- 若要保守过渡：用 `qoreon-oss`、`qoreon-system`、`qoreon-agents`

## 2. GitHub About 区建议

### 名称

`Qoreon`

### 简短描述

`The control layer between human intent and AI execution. Organize and run an AI team locally.`

### Website

- 首发前可以先留空
- 若后续有官网，建议放产品官网而不是文档深链

### Topics

`ai-agents`
`multi-agent`
`orchestration`
`local-first`
`developer-tools`
`taskboard`
`agent-runtime`
`codex`
`claude-code`

## 3. Social Preview 文案

### 标题

`Qoreon`

### 副标题

`The core system between human intent and AI execution`

### 说明

`Run an AI team locally. Organize channels, tasks, seed packs, and execution in one control layer.`

## 4. 首页核心图片资源

当前 GitHub 首页与发布说明只使用这 4 张核心图片：

- 品牌主图：`assets/brand/qoreon-logo-primary.png`
- 首页项目清单：`assets/screenshots/home-project-list.png`
- 项目对话详情：`assets/screenshots/project-dialog-detail.png`
- 消息发送情况：`assets/screenshots/message-flow-board.png`

约束：

- 不再混用旧的横幅草图、流程图、结构图
- 首页最多展示 `1` 张 Logo + `3` 张系统截图
- 截图顺序固定为：项目清单 -> 对话详情 -> 消息发送

## 5. README 首屏目标

GitHub 首页首屏只做 4 件事：

1. 用一句话说清 Qoreon 是什么
2. 让人理解它不是“又一个 prompt 工具”
3. 给出 3 步试跑路径
4. 让外部 AI 或开发者知道先看 `ai-bootstrap`

## 6. 首屏必须保留的内容

- 品牌图
- 一句话定位
- 3 行价值说明
- Quick Start
- 文档阅读顺序
- 公开边界声明

## 7. 不建议放在首页首屏的内容

- 长篇背景故事
- 复杂架构图
- 过多运行截图
- 大段中文培训历史
- 内部协作命名来源
