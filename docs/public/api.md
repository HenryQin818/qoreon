# API

## Health

- `GET /__health`

返回服务状态、工作区信息和基础运行上下文。

## Run

- `POST /api/codex/announce`
- `GET /api/codex/runs`
- `GET /api/codex/run/<id>`

## Session

- `GET /api/sessions`
- `GET /api/sessions/<session_id>`

## CLI Types

- `GET /api/cli/types`

## 兼容原则

- 只新增字段，不破坏已有字段语义
- 默认同一 `session_id` 严格串行
- 默认仅监听 `127.0.0.1`
