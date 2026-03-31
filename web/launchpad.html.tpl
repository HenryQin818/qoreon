<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Qoreon · 启动中转页</title>
  <style>__INLINE_CSS__</style>
</head>
<body>
  <main class="shell">
    <section class="hero">
      <div class="hero-copy">
        <p class="eyebrow">Qoreon Launchpad</p>
        <h1 id="title">项目启动中转页</h1>
        <p class="subtitle" id="subtitle"></p>
      </div>
      <div class="hero-side">
        <div class="health-card">
          <div class="health-head">
            <span>服务状态</span>
            <button id="refreshHealthBtn" class="ghost-btn" type="button">刷新</button>
          </div>
          <div class="health-status" id="healthStatus">检测中</div>
          <div class="health-meta" id="healthMeta"></div>
        </div>
      </div>
    </section>

    <section class="panel">
      <div class="panel-head">
        <h2>项目入口</h2>
        <p>启动后默认先看这里，再按需进入具体页面。</p>
      </div>
      <div class="project-list" id="projectList"></div>
    </section>

    <section class="panel">
      <div class="panel-head">
        <h2>常用页面</h2>
        <p>把原来分散的页面入口集中到一个页面里。</p>
      </div>
      <div class="link-grid" id="linkGrid"></div>
    </section>

    <section class="panel quick-panel">
      <div class="panel-head">
        <h2>快速操作</h2>
        <p>健康检查、协作视图和辅助页面都从这里跳转。</p>
      </div>
      <div class="quick-actions" id="quickActions"></div>
    </section>
  </main>

  <script id="data" type="application/json">__PAYLOAD__</script>
  <script>__INLINE_JS__</script>
</body>
</html>
