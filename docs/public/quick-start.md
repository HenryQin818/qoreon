# Quick Start

## 1. 准备环境

- Python 3.11+
- 任一受支持 CLI：`codex` / `claude` / `gemini` / `opencode` / `trae`

## 2. 生成页面

```bash
python3 build_project_task_dashboard.py
```

输出默认在 `dist/`。

## 3. 启动服务

```bash
python3 server.py --port 18770
```

## 4. 打开页面

- `http://127.0.0.1:18770/share/project-task-dashboard.html`
- `http://127.0.0.1:18770/share/project-overview-dashboard.html`
- `http://127.0.0.1:18770/share/project-status-report.html`

## 5. 如果要让 AI 接手

直接把 `docs/public/ai-bootstrap.md` 发给 AI，并要求它先读取：

- `AGENTS.md`
- `examples/minimal-project/README.md`
- `examples/minimal-project/seed/seed-inventory.json`
