# Dashboard Payload Schema (v1)

规则：
- v1 字段允许新增，但禁止改名/改语义。
- `dist/*.html` 是构建产物，不进入 git；契约以本文为准。
- 全局数据规格总览（含组织架构）：`docs/contract/data-spec.global.v1.md`

## 顶层字段
- `generated_at` string：生成时间（本地时区）
- `dashboard` object
  - `title` string
  - `subtitle` string
- `projects` array
- `items` array
- `links` object
  - `task_page` string
  - `overview_page` string
  - `communication_page` string（可选）
  - `status_report_page` string（可选）
  - `agent_directory_page` string（可选）
- `agent_curtain_page` string（可选）
- `agent_relationship_board_page` string（可选）
- `session_health_page` string（可选）
- `communication_page` string（可选）
- `status_report_page` string（可选）
- `agent_directory_page` string（可选）
- `overview` object

## projects[]
- `id` string：项目主键
- `name` string
- `color` string：HEX
- `description` string
- `links` array
  - `label` string
  - `url` string
- `sessions` array：来自会话 Markdown 清单（可空）
- `sessions_json` array：来自会话 JSON 清单（可空）
- `channels` array：业务通道定义
  - `name` string
  - `desc` string
- `channel_sessions` array：通道会话合并结果
  - `name` string
  - `alias` string
  - `session_id` string（可空）
  - `desc` string
  - `cli_type` string（`codex|claude|opencode|gemini|trae|codebuddy`）
  - `model` string（可空）
  - `reasoning_effort` string（可空；仅 codex 生效）
  - `source` string（`session_store|config|json|list`）

## items[]
- `project_id` string
- `project_name` string
- `channel` string
- `channel_name` string（可选，兼容别名，语义同 `channel`）
- `status` string
- `type` string
- `title` string
- `code` string
- `path` string：工作区相对路径（用于详情与 reveal）
- `updated_at` string
- `owner` string
- `due` string
- `excerpt` string
- `tags` array[string]
- `primary_status` string（可选；当前主要对 `type="任务"` 返回，规范化主状态：`待办|进行中|待验收|已完成|暂缓`）
- `lifecycle_state` string（可选；当前主要对 `type="任务"` 返回，规范化生命周期：`todo|in_progress|pending_acceptance|done|paused|unknown`）
- `counts_as_wip` boolean（可选；当前主要对 `type="任务"` 返回，表示是否计入进行中 WIP）
- `status_flags` object（可选；当前主要对 `type="任务"` 返回）
  - `supervised` boolean
  - `blocked` boolean
- `session` object|null
  - `name` string
  - `alias` string
  - `session_id` string（可空）
  - `desc` string
  - `cli_type` string
  - `model` string（可空）
  - `reasoning_effort` string（可空）
  - `source` string

## overview
口径说明（V1 增量）：
- `overview.totals` 与 `overview.projects[].totals` 的主统计字段（`total/active/done/supervised/in_progress/todo/paused`）按 `type="任务"` 口径计算。
- 全事项（任务+沉淀+材料+反馈+答复+问题+讨论）统计通过新增可选字段 `items_*` 提供。
- 知识类辅助统计通过新增可选字段 `knowledge_total` 提供；仅统计 `type in {"沉淀","材料","证据"}`，不并入任务主统计。
- 极简 5 状态展示口径通过可选字段 `primary_status_counts` 提供；它不替代旧字段，只用于新前端优先展示 `待办|进行中|待验收|已完成|暂缓`。

### overview.totals
- `projects` number
- `channels` number
- `total` number
- `active` number
- `in_progress` number
- `supervised` number
- `done` number
- `updated_at` string
- `knowledge_total` number（可选，知识类事项总量：`沉淀|材料|证据`）
- `items_total` number（可选，全事项总量）
- `items_active` number（可选，全事项活跃量）
- `items_done` number（可选，全事项完成量）
- `primary_status_counts` object（可选，规范化 5 状态计数）
  - `todo` number
  - `in_progress` number
  - `pending_acceptance` number
  - `done` number
  - `paused` number

### overview.projects[]
- `project_id` string
- `project_name` string
- `color` string
- `description` string
- `totals` object
  - `total` number
  - `channels` number
  - `active` number
  - `done` number
  - `supervised` number
  - `in_progress` number
  - `todo` number
  - `paused` number
  - `knowledge_total` number（可选，知识类事项总量：`沉淀|材料|证据`）
  - `items_total` number（可选，全事项总量）
  - `items_active` number（可选，全事项活跃量）
  - `items_done` number（可选，全事项完成量）
  - `primary_status_counts` object（可选，同 `overview.totals.primary_status_counts`）
- `updated_at` string
- `score` number
- `channels_data` array
  - `name` string
  - `totals` object（同上）
  - `updated_at` string
  - `score` number
  - `session_configured` boolean
