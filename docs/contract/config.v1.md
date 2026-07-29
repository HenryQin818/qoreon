# Qoreon 公开配置增量契约 v1

以下环境变量只控制 Codex 浏览器能力，不保存 Profile、Cookie、登录态或浏览历史。

- `TASK_DASHBOARD_CODEX_PLAYWRIGHT_MCP`
  - 布尔值，默认启用。
  - `collab` 使用项目隔离的持久 Playwright Profile；`ephemeral` 使用无持久状态的隔离浏览器。
- `TASK_DASHBOARD_CODEX_PLAYWRIGHT_PROFILE_ROOT`
  - 可选绝对路径。
  - 默认使用 `~/Library/Application Support/Qoreon/browser-profiles`。
  - 项目子目录由服务端生成，不接受调用方传入实际 Profile 路径。
- `TASK_DASHBOARD_CODEX_BROWSER_PLUGIN`
  - 布尔值，默认启用。
  - 仅允许显式 `browser_mode=plugin` 使用已配置的桌面浏览器插件。
  - 插件不参与默认或 `auto` 路由，也不作为 Playwright 失败后的自动回退。

配置变更只影响后续新运行；是否重载或重启由部署环境的服务管理流程决定。
