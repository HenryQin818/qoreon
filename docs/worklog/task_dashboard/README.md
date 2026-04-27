# task_dashboard 开发日志存放规范

## 目标
- 日志页面源码、相关图片、附属素材放在同一仓库目录内
- `share` 仅作为访问别名，不再作为日志真源存放位置
- 打包、备份、迁移项目时，日志内容不会因为 `static_sites/share` 单独丢失

## 当前固定目录
- 日志目录：`docs/worklog/task_dashboard/`
- 资源目录：`docs/worklog/task_dashboard/assets/`
- 列表清单：`docs/worklog/task_dashboard/worklog-index.json`

## 约定
1. 每篇日志 HTML 直接放在 `docs/worklog/task_dashboard/`
2. 该日志使用的图片、图标等素材放在同目录下的 `assets/` 子目录
3. 日志列表只登记标题和访问地址；可额外补 `local_path` 便于维护
4. 对外访问统一走：
   - `/share/worklog/task_dashboard/<日志文件名>.html`

## 现有别名
- `static_sites/share/worklog -> docs/worklog`
- 旧的顶层分享链接可继续保留为兼容跳转，但真源以仓库目录为准
