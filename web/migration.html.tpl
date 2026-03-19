<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>跨项目单源化改造追踪</title>
  <style>__INLINE_CSS__</style>
</head>
<body>
  <div class="page-shell">
    <header class="hero">
      <div class="eyebrow">Project Migration Tracker</div>
      <h1>跨项目单源化改造追踪</h1>
      <p class="hero-sub" id="generatedAt">更新时间：-</p>
      <div class="hero-tags">
        <span class="tag danger" id="tagNeeds">待适配 0</span>
        <span class="tag warn" id="tagDual">双源 0</span>
        <span class="tag good" id="tagReady">单源 0</span>
        <span class="tag muted" id="tagBuilder">构建旧源兼容：-</span>
      </div>
    </header>

    <main class="content-grid">
      <section class="panel summary-panel">
        <div class="panel-head">
          <h2>改造概览</h2>
        </div>
        <div class="summary-grid" id="summaryGrid"></div>
      </section>

      <section class="panel board-panel">
        <div class="panel-head panel-head-inline">
          <div>
            <h2>项目清单</h2>
            <p class="panel-desc">按优先级排序，直接展示当前来源结构与下一步动作。</p>
          </div>
          <input class="search" id="searchInput" type="search" placeholder="搜索项目或状态..." />
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>项目</th>
                <th>状态</th>
                <th>来源结构</th>
                <th>摘要</th>
                <th>下一步</th>
              </tr>
            </thead>
            <tbody id="rows"></tbody>
          </table>
        </div>
      </section>
    </main>
  </div>
  <script id="data" type="application/json">__PAYLOAD__</script>
  <script>__INLINE_JS__</script>
</body>
</html>
