# Contributing

## 基本原则

- 先改最小范围，再补验证。
- 默认保持 API 向后兼容，只新增字段，不改语义。
- 不提交 `dist/`、`.run/`、`.runs/`、`.runtime/` 等运行产物。
- 不提交真实 token、真实 session_id、真实 run_id、真实绝对路径。

## 本地开发

```bash
python3 build_project_task_dashboard.py
python3 server.py --port 18770 --static-root dist
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

## 提交前检查

- 页面可生成
- `__health` 正常
- 最小测试通过
- 无真实绝对路径、真实会话标识、历史环境端口或私有基础设施词汇泄露
