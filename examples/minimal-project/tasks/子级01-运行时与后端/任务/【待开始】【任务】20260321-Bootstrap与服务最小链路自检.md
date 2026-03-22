# Bootstrap 与服务最小链路自检

## 当前状态

- 状态：待开始
- 通道：子级01-运行时与后端

## 当前目标

- 跑通 bootstrap
- 跑通 build 与 server
- 验证 `__health` 和最小 API 正常

## 下一步动作

- 执行 `python3 scripts/bootstrap_public_example.py`
- 执行 `python3 build_project_task_dashboard.py`
- 启动 `python3 server.py --port 18770 --static-root dist`
