<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>消息风险看板 · Qoreon</title>
  <style>__INLINE_CSS__</style>
</head>
<body>
  <div class="page-shell">
    <header class="hero">
      <div class="hero-copy">
        <div class="hero-kicker" id="heroKicker">Message Risk Dashboard</div>
        <h1 id="heroTitle">消息功能梳理与风险看板</h1>
        <p class="hero-sub" id="heroSubtitle">-</p>
      </div>
      <div class="hero-meta">
        <span class="hero-chip hero-chip-strong" id="generatedAtChip">生成中</span>
        <span class="hero-chip" id="branchChip">branch -</span>
        <span class="hero-chip" id="scopeChip">样本 -</span>
      </div>
    </header>

    <nav class="quick-links" aria-label="快捷入口">
      <a class="link-chip" id="overviewLink" href="/share/project-overview-dashboard.html">项目总览</a>
      <a class="link-chip" id="taskLink" href="/share/project-task-dashboard.html">任务页</a>
      <a class="link-chip" id="communicationLink" href="/share/project-communication-audit.html">通讯分析</a>
      <a class="link-chip" id="statusReportLink" href="/share/project-status-report.html">情况汇报</a>
      <a class="link-chip" id="sessionHealthLink" href="/share/project-session-health-dashboard.html">会话健康</a>
    </nav>

    <main class="content">
      <section class="summary-grid" id="summaryGrid"></section>

      <section class="panel hero-panel">
        <div class="section-head">
          <div>
            <h2>消息链路全景</h2>
            <p>从发送入口到审计回看，先看链路，再看风险。</p>
          </div>
        </div>
        <div class="pipeline-grid" id="pipelineGrid"></div>
      </section>

      <section class="comparison-grid" id="comparisonGrid"></section>

      <section class="section-block">
        <div class="section-head">
          <div>
            <h2>核心隐患</h2>
            <p>先列结论，再给证据与建议，避免把时间花在低价值描述上。</p>
          </div>
        </div>
        <div class="finding-grid" id="findingGrid"></div>
      </section>

      <section class="section-block split-block">
        <article class="panel">
          <div class="section-head">
            <div>
              <h2>结构化证据</h2>
              <p>把高频降级、错误热点和 branch 记录放在一起看。</p>
            </div>
          </div>
          <div class="table-stack" id="tableStack"></div>
        </article>
        <article class="panel">
          <div class="section-head">
            <div>
              <h2>治理优先级</h2>
              <p>按 P0 / P1 / P2 排，不做平均用力。</p>
            </div>
          </div>
          <div class="action-list" id="actionList"></div>
        </article>
      </section>

      <section class="section-block">
        <div class="section-head">
          <div>
            <h2>参考资料</h2>
            <p>保留这次判断依赖的关键实现与真源文件。</p>
          </div>
        </div>
        <div class="reference-list" id="referenceList"></div>
      </section>
    </main>
  </div>

  <script id="data" type="application/json">__PAYLOAD__</script>
  <script>__INLINE_JS__</script>
</body>
</html>
