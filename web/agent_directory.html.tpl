<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>项目通讯录 · 小秘书</title>
  <style>__INLINE_CSS__</style>
</head>
<body>
  <div class="page-shell">
    <header class="page-header">
      <div class="title-wrap">
        <div class="eyebrow">协作通讯录</div>
        <h1 id="pageTitle">项目通讯录</h1>
        <p id="pageSubtitle">按项目查看通道与 Agent，并复制可直接粘贴到输入框的协同对象写法。</p>
      </div>
      <div class="header-actions">
        <a class="header-btn" id="backToTaskPage" href="project-task-dashboard.html">返回任务页</a>
        <input class="search-input" id="searchInput" type="search" placeholder="搜索通道 / Agent" />
      </div>
    </header>

    <main class="layout">
      <aside class="project-rail">
        <div class="rail-title">项目</div>
        <div class="project-list" id="projectList"></div>
      </aside>

      <section class="content">
        <div class="summary-bar" id="summaryBar"></div>
        <div class="channel-grid" id="channelGrid"></div>
        <div class="empty-state" id="emptyState" hidden>当前条件下没有匹配的通讯录项。</div>
      </section>
    </main>
  </div>

  <script id="data" type="application/json">__PAYLOAD__</script>
  <script>__INLINE_JS__</script>
</body>
</html>
