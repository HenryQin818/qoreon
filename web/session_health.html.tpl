<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Agent 会话上下文健康表 · 小秘书</title>
  <style>__INLINE_CSS__</style>
</head>
<body>
  <div class="page-shell">
    <header class="hero">
      <div class="hero-copy">
        <div class="hero-kicker">Agent Context Health</div>
        <h1>Agent 会话上下文健康表</h1>
        <p class="hero-sub" id="heroSub">只看全部 agent 对话的压缩后占用基线，默认按最需要重置的对话排序。</p>
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
            <strong class="meta-value" id="generatedAtBadge">生成中</strong>
            <span class="meta-note" id="autoStatusText">-</span>
          </div>
        </div>
        <div class="hero-control-row">
          <label class="toggle-card" for="autoEnabledInput">
            <span class="meta-label">自动统计</span>
            <span class="toggle-switch">
              <input id="autoEnabledInput" type="checkbox" />
              <span class="toggle-slider"></span>
            </span>
          </label>
          <label class="field-card" for="intervalSelect">
            <span class="meta-label">自动频率</span>
            <select class="sort-select compact-select" id="intervalSelect" aria-label="自动分析频率">
              <option value="15">每 15 分钟</option>
              <option value="30">每 30 分钟</option>
              <option value="60">每 1 小时</option>
              <option value="120">每 2 小时</option>
              <option value="240">每 4 小时</option>
              <option value="360">每 6 小时</option>
              <option value="720">每 12 小时</option>
              <option value="1440">每 24 小时</option>
            </select>
          </label>
          <button class="save-btn" id="saveConfigButton" type="button">保存配置</button>
          <button class="refresh-btn" id="refreshButton" type="button">立即重算</button>
        </div>
      </div>
    </header>

    <nav class="quick-links" aria-label="快捷入口">
      <a class="link-chip" id="overviewLink" href="/share/project-overview-dashboard.html">返回总揽</a>
      <a class="link-chip" id="taskLink" href="/share/project-task-dashboard.html">打开任务页</a>
      <a class="link-chip" id="statusReportLink" href="/share/project-status-report.html">情况汇报</a>
      <a class="link-chip" id="communicationLink" href="/share/project-communication-audit.html">通讯分析</a>
      <a class="link-chip" id="agentCurtainLink" href="/share/project-agent-curtain.html">消息瀑布</a>
    </nav>

    <section class="notice-panel" id="summaryLine"></section>

    <main class="content">
      <section class="table-panel">
        <div class="section-head section-head-inline single-table-head">
          <div>
            <h2>全量 Agent 对话</h2>
            <p>主指标为“压缩后占用基线”；优先展示最近几次 compact 后的实测占用比例，缺少 token_count 时才退回估算。</p>
          </div>
          <div class="filters">
            <input class="search-input" id="searchInput" type="search" placeholder="搜索通道 / 别名 / session_id" />
            <select class="sort-select" id="sortSelect" aria-label="排序方式">
              <option value="baseline">占用基线</option>
              <option value="recent24h">24h压缩</option>
              <option value="recent">最近压缩</option>
              <option value="name">名称</option>
            </select>
            <div class="segmented" id="riskFilters">
              <button class="seg-btn active" data-risk="all" type="button">全部</button>
              <button class="seg-btn" data-risk="high" type="button">高风险</button>
              <button class="seg-btn" data-risk="medium" type="button">中风险</button>
              <button class="seg-btn" data-risk="low" type="button">低风险</button>
              <button class="seg-btn" data-risk="unsupported" type="button">未支持</button>
            </div>
          </div>
        </div>
        <div class="table-wrap">
          <table class="session-table agent-table">
            <thead>
              <tr>
                <th>排名</th>
                <th>Agent 对话</th>
                <th>通道</th>
                <th>压缩后占用基线</th>
                <th>24h压缩</th>
                <th>压缩后节奏</th>
                <th>建议</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody id="sessionTableBody"></tbody>
          </table>
        </div>
      </section>
    </main>
  </div>

  <script id="data" type="application/json">__PAYLOAD__</script>
  <script>__INLINE_JS__</script>
</body>
</html>
