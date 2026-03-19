# Configuration

## 核心文件

- `config.toml`: 当前默认配置
- `config.example.toml`: 复制后可作为新的起点

## 最小项目字段

- `id`
- `name`
- `project_root_rel`
- `task_root_rel`
- `runtime_root_rel`
- `execution_context`
- `channels`

## execution_context 推荐字段

- `profile`
- `environment`
- `worktree_root`
- `workdir`
- `runtime_root`
- `sessions_root`
- `runs_root`
- `server_port`
- `health_source`

## 推荐默认值

- `profile = "sandboxed"`
- `environment = "demo"`
- `server_port = "18770"`

## 通道建议

V1 推荐先保留 6 个：

- `主体-总控`
- `子级01-执行`
- `子级02-文档`
- `子级03-测试`
- `辅助01-结构治理与项目接入`
- `辅助02-Git桥接与发布同步`
