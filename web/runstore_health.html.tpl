<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>RunStore Health · 运行记录治理</title>
  <link rel="icon" href="data:," />
  <style>__INLINE_CSS__</style>
</head>
<body>
  <div class="page-shell">
    <header class="hero">
      <div class="hero-copy">
        <div class="hero-kicker">RunStore Health</div>
        <h1>运行记录治理</h1>
        <p class="hero-sub">独立查看 hot 运行记录健康、会话分布和受控归档入口。归档不是删除，P1 不移动 attachments。</p>
      </div>
      <div class="hero-actions">
        <div class="hero-meta-grid">
          <div class="hero-meta-card">
            <span class="meta-label">当前项目</span>
            <strong class="meta-value" id="projectNameBadge">读取中</strong>
            <span class="meta-note" id="projectIdMeta">-</span>
          </div>
          <div class="hero-meta-card">
            <span class="meta-label">最新统计时间</span>
            <strong class="meta-value" id="generatedAtBadge">等待刷新</strong>
            <span class="meta-note" id="apiStateText">同源 RunStore API</span>
          </div>
        </div>
        <div class="hero-control-row">
          <button class="refresh-btn" id="refreshButton" type="button">刷新健康摘要</button>
          <button class="ghost-btn" id="loadRunsButton" type="button">查看 hot run</button>
        </div>
      </div>
    </header>

    <nav class="quick-links" aria-label="快捷入口">
      <a class="link-chip" id="overviewLink" href="/share/project-overview-dashboard.html">返回总览</a>
      <a class="link-chip" id="taskLink" href="/share/project-task-dashboard.html">打开任务页</a>
      <a class="link-chip" id="sessionHealthLink" href="/share/project-session-health-dashboard.html">会话健康</a>
    </nav>

    <section class="notice-panel" id="noticePanel"></section>
    <section class="metric-grid" id="metricGrid"></section>
    <section class="risk-panel" id="riskPanel"></section>

    <main class="content">
      <section class="table-panel">
        <div class="section-head">
          <div>
            <h2>会话分布</h2>
            <p>优先按 hot 数量和终态数量排序，定位最应该归档的会话。</p>
          </div>
          <div class="filters">
            <input class="search-input" id="sessionSearchInput" type="search" placeholder="搜索通道 / session_id" />
            <select class="sort-select" id="sessionSortSelect" aria-label="会话排序">
              <option value="hot">hot 数量</option>
              <option value="terminal">终态数量</option>
              <option value="bytes">估算体积</option>
              <option value="oldest">最老终态</option>
            </select>
          </div>
        </div>
        <div class="table-wrap">
          <table class="runstore-table">
            <thead>
              <tr>
                <th>会话</th>
                <th>hot</th>
                <th>终态</th>
                <th>保护态</th>
                <th>体积</th>
                <th>最老终态</th>
                <th>建议</th>
              </tr>
            </thead>
            <tbody id="sessionTableBody"></tbody>
          </table>
        </div>
      </section>

      <section class="archive-panel">
        <div class="section-head">
          <div>
            <h2>手动受控归档</h2>
            <p>必须先 dry-run，再执行归档。只移动 hot 中终态 run 文件组，不删除、不移动附件。</p>
          </div>
        </div>
        <div class="archive-form">
          <label class="field-card">
            <span class="meta-label">范围</span>
            <select class="sort-select" id="archiveScopeSelect">
              <option value="all">全量 hot</option>
              <option value="session">指定会话</option>
            </select>
          </label>
          <label class="field-card">
            <span class="meta-label">会话</span>
            <select class="sort-select" id="archiveSessionSelect"></select>
          </label>
          <label class="field-card">
            <span class="meta-label">时间窗口</span>
            <select class="sort-select" id="archiveWindowSelect">
              <option value="24h">24 小时前</option>
              <option value="48h" selected>48 小时前</option>
              <option value="7d">7 天前</option>
              <option value="custom">自定义 N 天前</option>
            </select>
          </label>
          <label class="field-card compact-number">
            <span class="meta-label">N 天</span>
            <input class="search-input" id="customDaysInput" type="number" min="1" max="365" value="3" />
          </label>
          <button class="refresh-btn" id="dryRunButton" type="button">预检查 dry-run</button>
        </div>
        <div class="dry-run-result" id="dryRunResult"></div>
        <div class="execute-box" id="executeBox">
          <label class="confirm-line">
            <input id="executeConfirmInput" type="checkbox" />
            <span>我确认本次操作是归档，不删除文件，不移动 attachments，并已核对 dry-run 结果。</span>
          </label>
          <button class="danger-btn" id="executeButton" type="button" disabled>执行归档</button>
        </div>
        <div class="execute-result" id="executeResult"></div>
      </section>

      <section class="table-panel">
        <div class="section-head">
          <div>
            <h2>hot run 摘要</h2>
            <p>只显示 run 摘要，不读取完整 msg / last / log 正文。</p>
          </div>
          <div class="filters">
            <select class="sort-select" id="runSessionFilter"></select>
            <select class="sort-select" id="runStatusFilter">
              <option value="">全部状态</option>
              <option value="done">done</option>
              <option value="error">error</option>
              <option value="interrupted">interrupted</option>
              <option value="running">running</option>
              <option value="queued">queued</option>
            </select>
            <select class="sort-select" id="runGroupFilter">
              <option value="">全部状态组</option>
              <option value="terminal">终态</option>
              <option value="protected">保护态</option>
              <option value="unknown">未知</option>
            </select>
          </div>
        </div>
        <div class="table-wrap">
          <table class="runstore-table run-table">
            <thead>
              <tr>
                <th>run</th>
                <th>状态</th>
                <th>会话</th>
                <th>锚点时间</th>
                <th>体积</th>
                <th>归档判断</th>
              </tr>
            </thead>
            <tbody id="runTableBody"></tbody>
          </table>
        </div>
        <div class="load-more-row">
          <button class="ghost-btn" id="loadMoreRunsButton" type="button">加载更多</button>
        </div>
      </section>
    </main>
  </div>

  <script id="data" type="application/json">__PAYLOAD__</script>
  <script>__INLINE_JS__</script>
</body>
</html>
