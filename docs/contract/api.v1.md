# Qoreon API 增量契约 v1

本文记录当前公开候选新增或调整的 API 契约。示例只使用公开占位标识、同源路径和公开预览端口。

## Run Detail 展示投影

运行详情可返回以下 additive 字段：

```json
{
  "logTail": "末尾日志展示片段",
  "logTailChars": 120000,
  "logTailReturnedChars": 24000,
  "logTailTruncated": true,
  "processRows": [],
  "processRowsTotal": 120,
  "processRowsReturned": 80,
  "processRowsTruncated": true,
  "processEvents": [],
  "processEventsTotal": 120,
  "processEventsReturned": 80,
  "processEventsTruncated": true
}
```

截断只影响详情响应，不改写运行元数据或原始日志。`process` 与 `logTail` 使用相同展示片段。

## Conversation Memos

### POST /api/conversation-memos/reorder

```json
{
  "projectId": "standard_project",
  "sessionId": "session_demo_01",
  "orderedIds": ["memo_b", "memo_a"]
}
```

`ordered_ids` 可作为兼容键。未知 ID 忽略，未列出的现有条目保留在末尾。

## Sessions

### POST /api/sessions

- `alias` 必填，并在当前项目的活跃会话范围内唯一。
- `agent_name` 为 additive 身份字段，兼容 `agentName`；缺少 `alias` 时可镜像为 canonical alias。
- `reuse_strategy=rotate` 创建继任会话后，原子归档同通道同名旧会话；创建或写入失败不得把旧会话误标为已替换。
- 响应可返回 `registry_refresh`，只表示公开协作索引的派生刷新状态，不改变 SessionStore 主写结果。

### PUT /api/sessions/{session_id}

- 支持更新 `alias`、`agent_name`、`channel_name`、`session_role` 和 `set_as_primary`。
- 跨通道迁移同步更新工作上下文和主会话角色。
- 迁移失败返回 `session_migration_failed`；补偿失败返回 `session_migration_rollback_failed`，调用方不得视为迁移完成。

### POST /api/codex/session/new

该旧入口已停用，返回 `410 legacy_session_new_retired`；新建会话统一使用 `POST /api/sessions`。

## Announce 忙碌感知

`task_with_receipt` 和 `dialog_now` 在目标忙碌时可返回 `409 target_busy`，首发不创建 run。具有真实 `source_ref.session_id` 的同一发送方可在确认窗口内二次发送以确认入队。

`notify_only` 不触发忙碌回弹，可合并到同一目标的未消费通知容器；响应通过 `notification_merge` 描述 `created|appended|idempotent_replay`。

忙碌或未形成 run 的响应不得写成已送达。

## Project Resources

资源清单存储在项目本地运行目录。服务状态只读取由 `QOREON_RESOURCE_REGISTRY` 或 `TASK_DASHBOARD_RESOURCE_REGISTRY` 显式指定的本机服务清单，不内置用户目录。

### GET /api/projects/{project_id}/resources

```json
{
  "project_id": "standard_project",
  "schema_version": "project_resources.v1",
  "storage_mode": "runtime_local",
  "count": 1,
  "items": [
    {
      "id": "res_demo",
      "title": "本机预览",
      "type": "service",
      "url": "http://127.0.0.1:18770",
      "source": "manual",
      "service_status": {
        "state": "up|stopped|unknown",
        "source": "configured_registry|not_found"
      }
    }
  ]
}
```

### POST /api/projects/{project_id}/resources

新增 `doc_page|service` 资源。`source` 支持 `manual|message_quick_add`。

```json
{
  "title": "成果页",
  "type": "doc_page",
  "url": "dist/project-task-dashboard.html",
  "note": "公开示例",
  "source": "message_quick_add",
  "sort_order": 10
}
```

### PATCH /api/projects/{project_id}/resources/{id}

允许局部更新 `title/type/url/note/source/sort_order`，不改变 `created_at`。

### DELETE /api/projects/{project_id}/resources/{id}

只删除资源清单项，不删除目标文件、网页或服务。

## Message CLI 目标解析

同通道存在多条活跃会话或按通道寻址歧义时返回 `agent_ambiguous`，并提示通过会话治理入口设置主会话、归档冗余会话。不得随机选择，也不得绕过 SessionStore 从旧索引猜测目标。
