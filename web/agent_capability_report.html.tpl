<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>对话Agent功能体检看板 · Qoreon</title>
  <style>__INLINE_CSS__</style>
</head>
<body>
  <div class="page-shell">
    <header class="hero">
      <div class="hero-copy">
        <div class="hero-kicker" id="heroKicker">Agent Capability Check</div>
        <h1 id="heroTitle">对话Agent功能体检看板</h1>
        <p class="hero-sub" id="heroSubtitle">-</p>
      </div>
      <div class="hero-meta">
        <span class="hero-chip hero-chip-strong" id="generatedAtChip">生成中</span>
        <span class="hero-chip" id="overallChip">总体 -</span>
        <span class="hero-chip" id="scopeChip">范围 -</span>
      </div>
    </header>

    <nav class="quick-links" aria-label="快捷入口">
      <a class="link-chip" id="overviewLink" href="/share/project-overview-dashboard.html">项目总览</a>
      <a class="link-chip" id="taskLink" href="/share/project-task-dashboard.html">任务页</a>
      <a class="link-chip" id="statusReportLink" href="/share/project-status-report.html">情况汇报</a>
      <a class="link-chip" id="sessionHealthLink" href="/share/project-session-health-dashboard.html">会话健康</a>
      <a class="link-chip" id="messageRiskLink" href="/share/project-message-risk-dashboard.html">消息风险</a>
      <a class="link-chip" id="performanceLink" href="/share/project-performance-diagnostics.html">性能诊断</a>
    </nav>

    <main class="content">
      <section class="summary-grid" id="summaryGrid"></section>

      <section class="section-block">
        <div class="section-head">
          <div>
            <h2>四维健康度</h2>
            <p>业务、功能、体验、治理分开看，避免一个高分掩盖另一个短板。</p>
          </div>
        </div>
        <div class="health-grid" id="healthGrid"></div>
      </section>

      <section class="section-block">
        <div class="section-head">
          <div>
            <h2>关键对比</h2>
            <p>把运行活跃度、状态、治理噪音和项目分布放在同一页里看。</p>
          </div>
        </div>
        <div class="comparison-grid" id="comparisonGrid"></div>
      </section>

      <section class="section-block">
        <div class="section-head">
          <div>
            <h2>核心结论</h2>
            <p>只保留最影响决策的发现，包含结论、影响、建议和证据。</p>
          </div>
        </div>
        <div class="finding-grid" id="findingGrid"></div>
      </section>

      <section class="section-block split-block">
        <article class="panel">
          <div class="section-head">
            <div>
              <h2>优化动作</h2>
              <p>按优先级排，先解决会直接影响日常使用体感的问题。</p>
            </div>
          </div>
          <div class="action-list" id="actionList"></div>
        </article>
        <article class="panel">
          <div class="section-head">
            <div>
              <h2>参考真源</h2>
              <p>这轮判断依赖的关键产物、日志范围和配置真源。</p>
            </div>
          </div>
          <div class="reference-list" id="referenceList"></div>
        </article>
      </section>
    </main>
  </div>

  <script id="data" type="application/json">__PAYLOAD__</script>
  <script>__INLINE_JS__</script>
</body>
</html>
